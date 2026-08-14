"""Run the persistent ComfyUI server as a Deadline job.

The server used to be started by hand over RDP. This submits the same command
as a long-lived CommandLine job pinned to one worker.

No farm script copying is needed, unlike the path check: server.py adds its own
parent directory to sys.path (comfyui/server.py:26-30) and L: is mapped on the
workers - the Deadline task log shows "Skipping L: because it is already
mapped". The job therefore runs server.py from whichever tree submitted it,
which is recorded in the job's Comment so a dev-submitted server is visible.
"""
import getpass
import logging
import os
from typing import Dict, List, Optional, Tuple

from core.config import (
    DEADLINE_PATH,
    DEADLINE_DEPARTMENT,
    DEADLINE_JOB_NAME_PREFIX_SERVER,
)
from core.settings_manager import safe_get_setting
from core.subprocess_utils import run_command
from core.utils import ensure_directory, normalize_path

logger = logging.getLogger(__name__)

SERVER_SCRIPT_RELPATH = "comfyui/server.py"


def server_script_path() -> str:
    """Absolute path to server.py in the tree this code is running from."""
    python_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(python_root, "comfyui", "server.py")


def submitting_tree() -> str:
    """Repo root of the submitting checkout, for the job Comment."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def list_group_workers(group: str) -> List[str]:
    """Deadline worker names in a group. Empty list if Deadline can't answer."""
    if not DEADLINE_PATH or not group:
        return []
    try:
        result = run_command([DEADLINE_PATH, "GetSlaveNamesInGroup", group], timeout=30)
    except Exception as exc:
        logger.warning(f"Could not list workers in group {group}: {exc}")
        return []
    if result.returncode != 0:
        logger.warning(f"GetSlaveNamesInGroup failed: {result.stderr.strip()}")
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def worker_from_job_name(job_name: str) -> Optional[str]:
    """Recover the worker a server job was started for, or None."""
    if not job_name or not job_name.startswith(DEADLINE_JOB_NAME_PREFIX_SERVER):
        return None
    worker = job_name[len(DEADLINE_JOB_NAME_PREFIX_SERVER):].strip()
    return worker or None


def build_server_job_info(worker: str, pool: str, group: str, priority: int,
                          max_hours: int, comment: str) -> str:
    """Deadline job_info for a server pinned to one worker."""
    lines = [
        "Plugin=CommandLine",
        f"Name={DEADLINE_JOB_NAME_PREFIX_SERVER}{worker}",
        f"Comment=Started from {comment}",
        f"Department={DEADLINE_DEPARTMENT}",
        f"Pool={pool}",
        f"Group={group}",
        f"Priority={priority}",
        "Frames=0",
        "ChunkSize=1",
        "MachineLimit=1",
        # Whitelist is what makes "start a server on THIS worker" deterministic
        # rather than "wherever Deadline feels like putting it".
        f"Whitelist={worker}",
    ]
    if max_hours:
        # 0 means no cap - and a TaskTimeoutSeconds=0 line would read as an
        # immediate timeout, so the keys are omitted entirely instead.
        lines.append(f"TaskTimeoutSeconds={int(max_hours) * 3600}")
        lines.append("OnTaskTimeout=Complete")
    lines.append("OnJobComplete=Delete")
    return "\n".join(lines) + "\n"


def build_server_plugin_info(python_exe: str, server_script: str, comfyui_path: str,
                             mode: str, python_path: str, port: int,
                             flags: List[str]) -> str:
    """Deadline plugin_info running server.py under the ComfyUI interpreter."""
    script = normalize_path(server_script)
    clean_comfyui_path = normalize_path(comfyui_path.rstrip("/\\"))
    arguments = (
        f'"{script}" '
        f'--comfyui-path "{clean_comfyui_path}" '
        f'--port {port} '
        f'--mode {mode}'
    )
    if mode == "standalone" and python_path:
        arguments += f' --python-path "{normalize_path(python_path)}"'
    for flag in flags:
        arguments += f" {flag}"

    return (
        f"Executable={normalize_path(python_exe)}\n"
        f"Arguments={arguments}\n"
        f"StartupDirectory={normalize_path(os.path.dirname(script))}\n"
    )


def _server_flags() -> List[str]:
    """Launch flags from global settings, matching server.py's own defaults.

    --normalvram is deliberately absent: ComfyUI removed it and passing it
    aborts startup.
    """
    flags = []
    if safe_get_setting("comfyui_lowvram", False):
        flags.append("--lowvram")
    elif safe_get_setting("comfyui_highvram", False):
        flags.append("--highvram")
    if safe_get_setting("comfyui_disable_smart_memory", False):
        flags.append("--disable-smart-memory")
    if safe_get_setting("comfyui_fast_mode", False):
        flags.append("--fast")
    return flags


def submit_server_job(worker: str, pool: Optional[str] = None,
                      group: Optional[str] = None,
                      priority: Optional[int] = None) -> Optional[str]:
    """Submit a ComfyUI server job pinned to `worker`. Returns the job id.

    Runs in a worker thread - it shells out to deadlinecommand.
    """
    if not worker:
        raise ValueError("No worker given for the server job")
    if not DEADLINE_PATH:
        raise RuntimeError("Deadline is not available on this machine")

    comfyui_path = safe_get_setting("comfyui_path", "")
    if not comfyui_path:
        raise RuntimeError("No ComfyUI path is configured")

    network_path = safe_get_setting("network_output_path", "")
    if not network_path:
        raise RuntimeError("No network output path is configured")

    from comfyui.utils import resolve_comfyui_paths
    from deadline.utils import resolve_comfyui_targeting

    mode = safe_get_setting("comfyui_mode", "embedded")
    python_path = safe_get_setting("comfyui_python_path", "")
    python_exe, _ = resolve_comfyui_paths(comfyui_path, mode, python_path or None)

    resolved_pool, resolved_group, resolved_priority = resolve_comfyui_targeting(
        pool, group, priority)
    max_hours = safe_get_setting("comfyui_server_max_hours", 8)
    port = safe_get_setting("comfyui_port", 8188)

    job_dir = os.path.join(network_path, "_server_jobs", worker)
    ensure_directory(job_dir)
    job_info_path = os.path.join(job_dir, "server_job_info.txt")
    plugin_info_path = os.path.join(job_dir, "server_plugin_info.txt")

    with open(job_info_path, "w", encoding="utf-8") as handle:
        handle.write(build_server_job_info(
            worker, resolved_pool, resolved_group, resolved_priority,
            max_hours, submitting_tree()))
    with open(plugin_info_path, "w", encoding="utf-8") as handle:
        handle.write(build_server_plugin_info(
            python_exe, server_script_path(), comfyui_path, mode,
            python_path, port, _server_flags()))

    from deadline.utils import submit_deadline_job

    job_id = submit_deadline_job(
        [DEADLINE_PATH, job_info_path, plugin_info_path], log_prefix="[ComfyUIServer]")
    logger.info(f"ComfyUI server job {job_id} submitted for {worker}")
    return job_id


def find_server_jobs(username: Optional[str] = None) -> Dict[str, str]:
    """Return {lower-cased worker: job_id} for this user's live server jobs."""
    from deadline.parser import parse_job_info

    if not DEADLINE_PATH:
        return {}
    username = username or getpass.getuser()

    jobs: Dict[str, str] = {}
    for status_filter in ("Active", "Pending"):
        try:
            result = run_command(
                [DEADLINE_PATH, "GetJobIdsFilter",
                 f"Status={status_filter}", f"UserName={username}"],
                timeout=20,
            )
        except Exception as exc:
            logger.warning(f"Could not list {status_filter} jobs: {exc}")
            continue
        if result.returncode != 0:
            continue

        for job_id in [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]:
            try:
                job_result = run_command([DEADLINE_PATH, "GetJob", job_id], timeout=15)
            except Exception:
                continue
            if job_result.returncode != 0:
                continue
            worker = worker_from_job_name(parse_job_info(job_result.stdout).get("Name", ""))
            if worker:
                jobs[worker.lower()] = job_id

    return jobs


def stop_server_job(job_id: str) -> Tuple[bool, str]:
    """Complete the server job, which terminates the process on the worker."""
    from deadline.poller import complete_deadline_job

    return complete_deadline_job(job_id)
