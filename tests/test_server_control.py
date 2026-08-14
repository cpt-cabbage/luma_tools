"""Tests for ComfyUI server control - heartbeat status and the Deadline job."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from comfyui.server_status import (
    HEARTBEAT_DIRNAME,
    online_workers,
    read_server_heartbeats,
)


def _write_heartbeat(network_path, hostname, status="online", age_seconds=0,
                     uptime_seconds=120, jobs_completed=3, timestamp=None):
    """Write one heartbeat file the way server.py does."""
    directory = os.path.join(str(network_path), HEARTBEAT_DIRNAME)
    os.makedirs(directory, exist_ok=True)
    if timestamp is None:
        stamp = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        timestamp = stamp.isoformat()
    payload = {
        "hostname": hostname,
        "status": status,
        "uptime_seconds": uptime_seconds,
        "jobs_completed": jobs_completed,
        "timestamp": timestamp,
    }
    path = os.path.join(directory, f"heartbeat_{hostname}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


class TestReadHeartbeats:
    def test_no_network_path_is_empty(self):
        assert read_server_heartbeats("") == {}

    def test_missing_directory_is_empty(self, tmp_path):
        assert read_server_heartbeats(str(tmp_path)) == {}

    def test_fresh_heartbeat_is_reported_online(self, tmp_path):
        _write_heartbeat(tmp_path, "ls-ws-sim003", age_seconds=5)

        servers = read_server_heartbeats(str(tmp_path))

        assert set(servers) == {"ls-ws-sim003"}
        entry = servers["ls-ws-sim003"]
        assert entry["hostname"] == "ls-ws-sim003"
        assert entry["status"] == "online"
        assert entry["stale"] is False
        assert entry["jobs_completed"] == 3
        assert entry["age_seconds"] < 60

    def test_stale_heartbeat_is_kept_and_flagged(self, tmp_path):
        # Kept, not dropped: the UI must be able to say "last seen 4 minutes
        # ago" rather than have a server silently vanish.
        _write_heartbeat(tmp_path, "ls-ws-sim003", age_seconds=600)

        entry = read_server_heartbeats(str(tmp_path))["ls-ws-sim003"]

        assert entry["stale"] is True
        assert entry["age_seconds"] > 500

    def test_several_workers_are_reported_separately(self, tmp_path):
        # The bug this replaces: the old code collapsed every worker into one
        # "best" status, so any server anywhere read as online.
        _write_heartbeat(tmp_path, "worker-a", status="online", age_seconds=2)
        _write_heartbeat(tmp_path, "worker-b", status="offline", age_seconds=2)

        servers = read_server_heartbeats(str(tmp_path))

        assert servers["worker-a"]["status"] == "online"
        assert servers["worker-b"]["status"] == "offline"

    def test_malformed_files_are_skipped(self, tmp_path):
        directory = tmp_path / HEARTBEAT_DIRNAME
        directory.mkdir()
        (directory / "heartbeat_broken.json").write_text("{not json", encoding="utf-8")
        (directory / "heartbeat_nots.json").write_text('{"hostname": "x"}', encoding="utf-8")
        _write_heartbeat(tmp_path, "good", age_seconds=1)

        assert set(read_server_heartbeats(str(tmp_path))) == {"good"}

    def test_naive_timestamps_are_treated_as_utc(self, tmp_path):
        # Older servers wrote naive local time; mixing aware and naive
        # datetimes raises TypeError on subtraction.
        naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        _write_heartbeat(tmp_path, "legacy", timestamp=naive)

        entry = read_server_heartbeats(str(tmp_path))["legacy"]

        assert entry["stale"] is False

    def test_hostname_falls_back_to_the_filename(self, tmp_path):
        directory = tmp_path / HEARTBEAT_DIRNAME
        directory.mkdir()
        stamp = datetime.now(timezone.utc).isoformat()
        (directory / "heartbeat_nohost.json").write_text(
            json.dumps({"status": "online", "timestamp": stamp}), encoding="utf-8")

        assert read_server_heartbeats(str(tmp_path))["nohost"]["hostname"] == "nohost"


class TestOnlineWorkers:
    def test_only_fresh_online_servers_count(self, tmp_path):
        _write_heartbeat(tmp_path, "fresh-online", status="online", age_seconds=1)
        _write_heartbeat(tmp_path, "stale-online", status="online", age_seconds=900)
        _write_heartbeat(tmp_path, "fresh-starting", status="starting", age_seconds=1)

        assert online_workers(read_server_heartbeats(str(tmp_path))) == ["fresh-online"]


class TestServerJobIsNotAGenerationJob:
    """A server job must never be adopted by ComfyUI crash recovery.

    Regression shape: the farm path check shipped with the plain
    "LUMA TOOLS - " prefix, so every app launch recovered the probe as a
    running generation job and announced phantom completions.
    """

    def test_server_prefix_is_excluded_from_recovery(self):
        from core.config import DEADLINE_JOB_NAME_PREFIX_SERVER
        from deadline.poller import is_recoverable_luma_job

        assert not is_recoverable_luma_job(f"{DEADLINE_JOB_NAME_PREFIX_SERVER}ls-ws-sim003")

    def test_real_generation_jobs_are_still_recovered(self):
        from deadline.poller import is_recoverable_luma_job

        assert is_recoverable_luma_job("LUMA TOOLS - my_render")


class TestMaxHoursSetting:
    def test_defaults_to_eight_hours(self):
        from core.settings_manager import SETTINGS_REGISTRY

        assert SETTINGS_REGISTRY["comfyui_server_max_hours"].default == 8

    def test_out_of_range_values_are_clamped(self):
        from core.settings_manager import SETTINGS_REGISTRY

        validate = SETTINGS_REGISTRY["comfyui_server_max_hours"].validator
        assert validate(-5) == 0        # 0 means "no cap"
        assert validate(9999) == 168
        assert validate("not a number") == 8
