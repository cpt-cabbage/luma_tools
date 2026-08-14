"""Deadline job that verifies the ComfyUI installation on a farm worker.

The workstation has no direct line to the farm (see CLAUDE.md, ComfyUI Farm
Architecture), so checking whether comfyui_path exists means submitting a tiny
job and reading its answer back off the shared network path.

Plugin=Python is used rather than CommandLine so the check runs under an
interpreter configured centrally in the Deadline repository - independent of
the ComfyUI install being tested. A broken comfyui_python_path then reports as
a specific failed check instead of an opaque job error.
"""
import getpass
import logging
import os
import shutil
import socket
import time
from typing import Any, Dict, Optional, Tuple

from core.config import (
    DEADLINE_PATH,
    DEADLINE_POOL,
    DEADLINE_GROUP_COMFYUI,
    DEADLINE_PRIORITY_COMFYUI,
    DEADLINE_DEPARTMENT,
    DEADLINE_JOB_NAME_PREFIX,
)
from core.utils import ensure_directory, load_json, normalize_path

logger = logging.getLogger(__name__)

# Must name a row configured under Configure Plugins -> Python -> Python
# Executables in the Deadline repository (3.9 / 3.10 / 3.11 are configured in
# this studio). The check script is stdlib-only, so any configured 3.x works.
DEADLINE_PYTHON_PLUGIN_VERSION = "3.10"

PATH_CHECK_DIRNAME = "_path_checks"
RESULT_FILENAME = "result.json"
RESULT_SCHEMA = 1

# (source basename in python/comfyui/, farm basename)
FARM_SCRIPTS = (
    ("path_check.py", "comfyui_path_check.py"),
    ("utils.py", "comfyui_utils.py"),
)


def _check_priority() -> int:
    """A five-second diagnostic should not queue behind a render."""
    return min(99, DEADLINE_PRIORITY_COMFYUI + 20)


def build_check_id(user: Optional[str] = None, host: Optional[str] = None,
                   timestamp: Optional[str] = None) -> str:
    """Directory name for one check: who asked, from where, when."""
    user = user or getpass.getuser()
    host = host or socket.gethostname()
    timestamp = timestamp or time.strftime("%Y%m%d_%H%M%S")
    return f"{user}_{host}_{timestamp}"


def build_job_info(job_dir: str, pool: str, group: str, priority: int) -> str:
    """Deadline job_info for a single-task check job."""
    return (
        "Plugin=Python\n"
        f"Name={DEADLINE_JOB_NAME_PREFIX}ComfyUI Path Check\n"
        f"Department={DEADLINE_DEPARTMENT}\n"
        f"Pool={pool}\n"
        f"Group={group}\n"
        f"Priority={priority}\n"
        "Frames=0\n"
        "ChunkSize=1\n"
        "MachineLimit=1\n"
        f"OutputDirectory0={normalize_path(job_dir)}\n"
        "OnJobComplete=Delete\n"
    )


def build_plugin_info(script_path: str, comfyui_path: str, comfyui_mode: str,
                      comfyui_python: str, result_path: str) -> str:
    """Deadline plugin_info for the Python plugin."""
    clean_path = normalize_path(comfyui_path.rstrip("/\\"))
    clean_python = normalize_path(comfyui_python) if comfyui_python else ""
    arguments = (
        f'--comfyui-path "{clean_path}" '
        f'--comfyui-mode {comfyui_mode} '
        f'--comfyui-python "{clean_python}" '
        f'--result-file "{normalize_path(result_path)}"'
    )
    return (
        f"Version={DEADLINE_PYTHON_PLUGIN_VERSION}\n"
        f"ScriptFile={normalize_path(script_path)}\n"
        f"Arguments={arguments}\n"
        "SingleFramesOnly=True\n"
    )


def cleanup_old_path_checks(root: str, keep_days: int = 1) -> int:
    """Delete check directories older than keep_days. Returns how many went."""
    if not os.path.isdir(root):
        return 0

    cutoff = time.time() - keep_days * 86400
    removed = 0
    for name in os.listdir(root):
        entry = os.path.join(root, name)
        try:
            if os.path.isdir(entry) and os.path.getmtime(entry) < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        except OSError as exc:
            logger.debug(f"Could not clean up {entry}: {exc}")
    return removed


def read_path_check_result(result_path: str) -> Optional[Dict[str, Any]]:
    """Read the worker's answer. None until the farm has written a valid one."""
    if not os.path.isfile(result_path):
        return None

    data = load_json(result_path, default=None)
    if not isinstance(data, dict) or data.get("schema") != RESULT_SCHEMA:
        logger.warning(f"Ignoring malformed path check result at {result_path}")
        return None
    return data


def submit_path_check(comfyui_path: str, comfyui_mode: str = "embedded",
                      comfyui_python: str = "", network_output_path: str = "",
                      pool: Optional[str] = None, group: Optional[str] = None,
                      priority: Optional[int] = None) -> Tuple[Optional[str], str]:
    """Submit the check job. Returns (job_id, result_path).

    Runs in a worker thread - it shells out to deadlinecommand.
    """
    if not comfyui_path.strip():
        raise ValueError("ComfyUI path is empty")
    if not DEADLINE_PATH:
        raise RuntimeError("Deadline is not available on this machine")
    if not network_output_path.strip():
        raise RuntimeError(
            "No network output path is configured - the farm has nowhere to write the result")

    root = os.path.join(network_output_path, PATH_CHECK_DIRNAME)
    cleanup_old_path_checks(root)

    job_dir = os.path.join(root, build_check_id())
    ensure_directory(job_dir)

    # Copy the farm scripts next to the job files, flattened with the
    # comfyui_ prefix the farm imports them under.
    comfyui_pkg = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "comfyui")
    for src_name, dst_name in FARM_SCRIPTS:
        shutil.copy2(os.path.join(comfyui_pkg, src_name), os.path.join(job_dir, dst_name))

    script_path = os.path.join(job_dir, "comfyui_path_check.py")
    result_path = os.path.join(job_dir, RESULT_FILENAME)

    job_info_path = os.path.join(job_dir, "path_check_job_info.txt")
    plugin_info_path = os.path.join(job_dir, "path_check_plugin_info.txt")
    with open(job_info_path, "w", encoding="utf-8") as handle:
        handle.write(build_job_info(
            job_dir,
            pool or DEADLINE_POOL,
            group or DEADLINE_GROUP_COMFYUI,
            _check_priority() if priority is None else priority,
        ))
    with open(plugin_info_path, "w", encoding="utf-8") as handle:
        handle.write(build_plugin_info(
            script_path, comfyui_path, comfyui_mode, comfyui_python, result_path))

    from deadline.utils import submit_deadline_job

    job_id = submit_deadline_job(
        [DEADLINE_PATH, job_info_path, plugin_info_path], log_prefix="[PathCheck]")
    logger.info(f"Path check job {job_id} submitted; result expected at {result_path}")
    return job_id, result_path
