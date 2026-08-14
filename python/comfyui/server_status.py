"""Read ComfyUI server heartbeats from the shared network path.

server.py writes <network_output_path>/_server_status/heartbeat_<hostname>.json
every ~20s. The workstation cannot reach the farm directly (see CLAUDE.md,
ComfyUI Farm Architecture), so these files are its only view of which workers
have a live server.

Pure functions over files - no Qt, no Deadline - so the logic driving the
status banner can actually be tested. It previously lived inline in the
ComfyUI tab and collapsed every worker into a single "best" status, which
reads "online" even when the worker your job lands on has no server.
"""
import glob
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List

from core.utils import load_json

logger = logging.getLogger(__name__)

HEARTBEAT_DIRNAME = "_server_status"
DEFAULT_STALE_SECONDS = 60


def _hostname_from_filename(path: str) -> str:
    """heartbeat_<host>.json -> <host>, for files with no hostname field."""
    base = os.path.basename(path)
    if base.startswith("heartbeat_") and base.endswith(".json"):
        return base[len("heartbeat_"):-len(".json")]
    return base


def read_server_heartbeats(network_path: str,
                           stale_seconds: int = DEFAULT_STALE_SECONDS) -> Dict[str, dict]:
    """Return {lower-cased hostname: info} for every heartbeat file found.

    Stale entries are returned with stale=True rather than dropped, so the UI
    can report "last seen 4 minutes ago" instead of a server silently
    disappearing from the list.
    """
    if not network_path:
        return {}

    heartbeat_dir = os.path.join(network_path, HEARTBEAT_DIRNAME)
    if not os.path.isdir(heartbeat_dir):
        return {}

    now = datetime.now(timezone.utc)
    servers: Dict[str, dict] = {}

    for path in glob.glob(os.path.join(heartbeat_dir, "heartbeat_*.json")):
        data = load_json(path, {})
        if not isinstance(data, dict) or "timestamp" not in data:
            logger.debug(f"Skipping malformed heartbeat {path}")
            continue

        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (ValueError, TypeError):
            logger.debug(f"Skipping heartbeat with unreadable timestamp {path}")
            continue

        # Older servers wrote naive local time; assume UTC when naive so the
        # subtraction below never mixes aware and naive datetimes.
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age_seconds = (now - timestamp).total_seconds()

        hostname = str(data.get("hostname") or _hostname_from_filename(path))
        servers[hostname.lower()] = {
            "hostname": hostname,
            "status": data.get("status", "offline"),
            "uptime_seconds": data.get("uptime_seconds", 0),
            "jobs_completed": data.get("jobs_completed", 0),
            "age_seconds": age_seconds,
            "stale": age_seconds > stale_seconds,
        }

    return servers


def online_workers(heartbeats: Dict[str, dict]) -> List[str]:
    """Hostnames with a fresh 'online' heartbeat, sorted for stable display."""
    return sorted(
        info["hostname"] for info in heartbeats.values()
        if info["status"] == "online" and not info["stale"]
    )
