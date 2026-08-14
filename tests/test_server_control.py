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


class TestServerJobFiles:
    def test_job_info_whitelists_the_chosen_worker(self):
        from deadline.server_job import build_server_job_info

        text = build_server_job_info("ls-ws-sim003", "luma", "temp_compute", 50, 8, "tree")

        assert "Plugin=CommandLine\n" in text
        assert "Name=LUMA TOOLS SERVER - ls-ws-sim003\n" in text
        assert "Whitelist=ls-ws-sim003\n" in text
        assert "MachineLimit=1\n" in text
        assert "Pool=luma\n" in text
        assert "Group=temp_compute\n" in text

    def test_max_hours_becomes_a_task_timeout(self):
        from deadline.server_job import build_server_job_info

        text = build_server_job_info("w1", "luma", "temp_compute", 50, 8, "tree")

        assert "TaskTimeoutSeconds=28800\n" in text
        assert "OnTaskTimeout=Complete\n" in text

    def test_zero_hours_writes_no_timeout_at_all(self):
        # 0 means "no cap" - a TaskTimeoutSeconds=0 line would be read by
        # Deadline as an immediate timeout.
        from deadline.server_job import build_server_job_info

        text = build_server_job_info("w1", "luma", "temp_compute", 50, 0, "tree")

        assert "TaskTimeoutSeconds" not in text
        assert "OnTaskTimeout" not in text

    def test_the_comment_records_which_tree_submitted_it(self):
        # A dev submit puts dev server.py on a shared worker; that must never
        # be a silent surprise.
        from deadline.server_job import build_server_job_info

        text = build_server_job_info("w1", "luma", "temp_compute", 50, 8,
                                     "L:/tools/dev/luma_tools")

        assert "Comment=Started from L:/tools/dev/luma_tools\n" in text

    def test_plugin_info_uses_forward_slashes(self):
        from deadline.server_job import build_server_plugin_info

        text = build_server_plugin_info(
            r"D:\ComfyUI\python_embeded\python.exe",
            r"L:\tools\luma_tools\python\comfyui\server.py",
            r"D:\ComfyUI", "embedded", "", 8188, ["--lowvram"])

        arguments = [ln for ln in text.splitlines() if ln.startswith("Arguments=")][0]
        assert "\\" not in arguments
        assert "Executable=D:/ComfyUI/python_embeded/python.exe\n" in text
        assert '"L:/tools/luma_tools/python/comfyui/server.py"' in arguments
        assert '--comfyui-path "D:/ComfyUI"' in arguments
        assert "--port 8188" in arguments
        assert "--mode embedded" in arguments
        assert "--lowvram" in arguments

    def test_python_path_only_travels_in_standalone_mode(self):
        from deadline.server_job import build_server_plugin_info

        embedded = build_server_plugin_info(
            "py.exe", "s.py", "C:/ComfyUI", "embedded", "C:/py/python.exe", 8188, [])
        standalone = build_server_plugin_info(
            "py.exe", "s.py", "C:/ComfyUI", "standalone", "C:/py/python.exe", 8188, [])

        assert "--python-path" not in embedded
        assert '--python-path "C:/py/python.exe"' in standalone


class TestWorkerNameRoundTrip:
    def test_the_worker_survives_the_job_name(self):
        from deadline.server_job import build_server_job_info, worker_from_job_name

        text = build_server_job_info("ls-ws-sim003", "luma", "temp_compute", 50, 8, "t")
        name = [ln for ln in text.splitlines() if ln.startswith("Name=")][0][len("Name="):]

        assert worker_from_job_name(name) == "ls-ws-sim003"

    def test_unrelated_job_names_yield_nothing(self):
        from deadline.server_job import worker_from_job_name

        assert worker_from_job_name("LUMA TOOLS - my_render") is None
        assert worker_from_job_name("") is None


class TestServerScriptPath:
    def test_points_at_this_checkout(self):
        # The job runs server.py from whichever tree submitted it.
        from deadline.server_job import server_script_path

        path = server_script_path()

        assert path.replace("\\", "/").endswith("comfyui/server.py")
        assert os.path.isfile(path), path
