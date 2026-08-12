"""
Deadline Job Polling and Status Monitoring Module.

Handles querying Deadline for job status, progress, queue position,
and task log analysis for ComfyUI workflows.
"""

import os
import re
import time
import logging
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from core.config import DEADLINE_PATH, DEADLINE_JOB_NAME_PREFIX
from core.subprocess_utils import run_command
from core.caching import cached_with_ttl
from deadline.parser import (
    parse_job_info,
    get_task_counts,
    normalize_job_status,
    format_error_message,
    is_job_not_found,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Precompiled regexes
#
# extract_task_progress() runs on every poll tick for every in-flight job and
# scans up to 256 KB of log text against ~25 patterns. Compiling them once at
# import time keeps the hot path out of re's internal cache lookup entirely.
# ---------------------------------------------------------------------------

_RE_JOB_ID = re.compile(r'^[a-fA-F0-9]{24}$')

# Patterns that indicate ComfyUI is loading models into GPU memory.
_RE_MODEL_LOADING = [
    re.compile(p, re.IGNORECASE) for p in (
        r'Loading\s+model',
        r'Loading\s+checkpoint',
        r'Loading\s+CLIP',
        r'Loading\s+VAE',
        r'Loading\s+ControlNet',
        r'Loading\s+LoRA',
        r'Loading\s+UNET',
        r'model\s+loaded',
        r'models\s+loaded',
        r'Moving\s+model\s+to',
        r'weights\s+loaded',
        r'to_model.*loaded',
        r'Trellis.*Loading',
        r'Loading.*safetensors',
        r'Loading.*ckpt',
        r'CLIP/text encoder model load device',
        r'VAE load device',
        r'model_type\s+FLUX',
        r'Requested to load',
        r'Using.*Ops for text encoder',
        r'model weight dtype',
    )
]

# Runner format - "Progress: 42% (5/12) (15s)" or "Progress: 42% (5/12)"
_RE_PROGRESS_RUNNER = re.compile(r'Progress:\s*(\d+)%\s*\((\d+)/(\d+)\)(?:\s*\((\d+)s\))?')

# tqdm format - " 12%|<bar chars>| 1/8 [00:03<00:24,  3.46s/it]"
# Uses [^\|]* to match ANY characters between pipes (tqdm uses many unicode block chars)
_RE_PROGRESS_TQDM = re.compile(r'\s*(\d+)%\|[^\|]*\|\s*(\d+)/(\d+)\s*\[')

# Current node name - "Executing node 5: KSampler" / "Executing node 5, title: KSampler"
_RE_NODE_NAME_BASE = [
    re.compile(p, re.IGNORECASE) for p in (
        r'Executing node \d+[,:]?\s*(?:title:?\s*)?([^\n\r]+?)(?:\s*\(|$|\n)',
        r'Running node:\s*([^\n\r]+)',
    )
]
_RE_NODE_NAME_FULL = _RE_NODE_NAME_BASE + [
    re.compile(r'\[ComfyUI\]\s*Executing:\s*([^\n\r]+)', re.IGNORECASE)
]

_RE_EXECUTION_STARTED = re.compile(r'Execution\s+started|Executing\s+node', re.IGNORECASE)


def _parse_deadline_date(date_str: str) -> datetime:
    """Parse a Deadline SubmitDate string into a datetime for proper sorting.

    Falls back to ``datetime.min`` so jobs with missing/malformed dates sort
    last instead of crashing the lambda key.
    """
    if not date_str:
        return datetime.min
    for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return datetime.min


def poll_deadline_job_status(job_id: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Query Deadline for a job's current status.

    Args:
        job_id: The Deadline job ID to query
        output_dir: Optional output directory to check for output files

    Returns:
        Dict with status, progress, completed_tasks, total_tasks, error_message
    """
    # Validate job ID format (Deadline uses 24-character hex IDs)
    if not job_id or not _RE_JOB_ID.match(job_id):
        logger.error(f"Invalid Deadline job ID format: {job_id}")
        return {"status": "Unknown", "progress": 0}

    try:
        if not DEADLINE_PATH:
            return {"status": "Unknown", "progress": 0, "error_message": "Deadline not available"}

        result = run_command([DEADLINE_PATH, "GetJob", job_id], timeout=30)

        output = result.stdout.strip()

        # Check if job was not found (deleted, or transient Deadline error)
        # Always return "Unknown" — the caller (polling handler) decides whether
        # this means "completed and auto-deleted" or "still registering" based on
        # its own state (saw_active flag, poll count, output files with timestamp).
        if is_job_not_found(result.returncode, result.stderr, output):
            return {
                "status": "Unknown",
                "progress": 0,
                "completed_tasks": 0,
                "total_tasks": 1,
                "error_message": "Job not found in Deadline"
            }

        if result.returncode != 0:
            return {"status": "Unknown", "progress": 0, "error_message": result.stderr}

        # Parse job info using centralized parser
        job_info = parse_job_info(output)
        task_counts = get_task_counts(job_info)

        status = job_info.get("Status", "Unknown")
        job_name = job_info.get("Name", "")
        error_reports = job_info.get("ErrorReports", 0)

        # Format error message
        error_message = format_error_message(task_counts, error_reports)

        # Calculate progress
        progress = int((task_counts['completed'] / max(task_counts['total'], 1)) * 100)

        # Normalize status
        status = normalize_job_status(status, task_counts)

        # Get queue position info for queued/pending jobs
        queue_info = {}
        if status == "Pending":
            queue_info = get_queue_info(job_id)

        # Try to get detailed progress for rendering tasks
        task_progress = None
        is_loading_model = False
        if status in ("Rendering", "Active") and task_counts['rendering'] > 0:
            # First try to read the runner log from the network output directory
            # This is available immediately and contains all ComfyUI output
            log_content = None
            if output_dir and job_name:
                # Extract the output prefix from the job name (e.g., "LUMA TOOLS - luma_tools_job_xyz" -> "luma_tools_job_xyz")
                if job_name.startswith(DEADLINE_JOB_NAME_PREFIX):
                    output_prefix = job_name[len(DEADLINE_JOB_NAME_PREFIX):]
                    log_content = get_runner_log_from_network(
                        output_dir, output_prefix, job_id=job_id
                    )

            # Fall back to Deadline task log if network log not available
            if not log_content:
                active_task_id = task_counts['completed']
                log_content = get_task_log(job_id, active_task_id)

            if log_content:
                task_progress = extract_task_progress(log_content)
                if task_progress:
                    is_loading_model = task_progress.get('is_loading_model', False)

        return {
            "status": status,
            "progress": progress,
            "completed_tasks": task_counts['completed'],
            "total_tasks": task_counts['total'],
            "queued_tasks": task_counts['queued'],
            "rendering_tasks": task_counts['rendering'],
            "error_message": error_message,
            "queue_position": queue_info.get("queue_position", 0),
            "total_queued": queue_info.get("total_queued", 0),
            "jobs_ahead": queue_info.get("jobs_ahead", 0),
            "own_jobs_ahead": queue_info.get("own_jobs_ahead", 0),
            "other_jobs_ahead": queue_info.get("other_jobs_ahead", 0),
            "task_progress": task_progress,
            "is_loading_model": is_loading_model,
        }

    except Exception as e:
        # Log with traceback: callers treat "Unknown" as "job may have been
        # auto-deleted after completion", so a genuine polling/parsing bug
        # would otherwise be indistinguishable from normal job completion.
        logger.warning(f"poll_deadline_job_status failed for {job_id}: {e}", exc_info=True)
        return {"status": "Unknown", "progress": 0, "error_message": str(e)}


def get_task_log(job_id: str, task_id: int) -> Optional[str]:
    """
    Get stdout log for a specific Deadline task.

    Args:
        job_id: Deadline job ID
        task_id: Task number (0-based)

    Returns:
        Task log contents, or None if unavailable
    """
    try:
        if not DEADLINE_PATH:
            return None

        result = run_command(
            [DEADLINE_PATH, "GetTaskLog", job_id, str(task_id)],
            timeout=15
        )

        if result.returncode == 0:
            return result.stdout
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Runner-log path cache
#
# The runner-log directory lives on the network share and holds every job's log
# for every user. Globbing it on every poll tick (per job, every few seconds) is
# a remote directory listing we only need once: the resolved path for a given
# job never changes while that job runs. Cache it, drop the entry if the file
# disappears (log rotated / job cleaned up) so the next call re-resolves.
# ---------------------------------------------------------------------------
_RUNNER_LOG_PATH_CACHE: Dict[str, str] = {}
_RUNNER_LOG_PATH_CACHE_LOCK = threading.RLock()
_RUNNER_LOG_PATH_CACHE_MAX = 200


def _cache_runner_log_path(cache_key: str, path: str) -> None:
    """Store a resolved runner-log path, evicting oldest entries when full."""
    with _RUNNER_LOG_PATH_CACHE_LOCK:
        if len(_RUNNER_LOG_PATH_CACHE) >= _RUNNER_LOG_PATH_CACHE_MAX:
            # dicts preserve insertion order — drop the oldest quarter at once
            # so we don't pay the eviction cost on every single insert.
            for stale_key in list(_RUNNER_LOG_PATH_CACHE)[:_RUNNER_LOG_PATH_CACHE_MAX // 4]:
                _RUNNER_LOG_PATH_CACHE.pop(stale_key, None)
        _RUNNER_LOG_PATH_CACHE[cache_key] = path


def clear_runner_log_path_cache() -> None:
    """Drop all cached runner-log paths (used by tests and job cleanup)."""
    with _RUNNER_LOG_PATH_CACHE_LOCK:
        _RUNNER_LOG_PATH_CACHE.clear()


def get_runner_log_from_network(
    output_dir: str, job_name: str, job_id: Optional[str] = None
) -> Optional[str]:
    """
    Get the ComfyUI runner log from the network log directory.

    The runner writes logs to <network_path>/_logs/runner/ with pattern:
    comfyui_runner_{job_name}_{timestamp}.log

    The resolved log path is cached per job so repeated polls don't re-glob the
    shared network log directory. A cached entry is discarded automatically if
    the file no longer exists.

    Args:
        output_dir: Network output directory (used as fallback and to derive network path)
        job_name: Job name/output prefix
        job_id: Optional Deadline job ID — used as the cache key when available

    Returns:
        Log file contents, or None if not found/readable
    """
    import glob
    from core.logging_utils import get_network_log_dir

    try:
        cache_key = job_id or f"{output_dir}|{job_name}"

        with _RUNNER_LOG_PATH_CACHE_LOCK:
            cached_path = _RUNNER_LOG_PATH_CACHE.get(cache_key)
        if cached_path:
            if os.path.isfile(cached_path):
                return _read_log_tail(cached_path)
            # File vanished (rotated/cleaned up) — invalidate and re-resolve.
            with _RUNNER_LOG_PATH_CACHE_LOCK:
                _RUNNER_LOG_PATH_CACHE.pop(cache_key, None)

        # Find the most recent log file matching the job name
        # Don't truncate - UUIDs can be longer than 50 chars
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_name)

        # Primary location: network log directory (_logs/runner/)
        log_dir = get_network_log_dir("runner")

        if log_dir and os.path.isdir(log_dir):
            pattern = os.path.join(log_dir, f"comfyui_runner_{safe_name}_*.log")
            log_files = glob.glob(pattern)

            if log_files:
                latest_log = max(log_files, key=os.path.getmtime)
                _cache_runner_log_path(cache_key, latest_log)
                return _read_log_tail(latest_log)

        # Fallback: search in output directory itself (legacy location)
        if output_dir and os.path.isdir(output_dir):
            pattern = os.path.join(output_dir, "**", f"comfyui_runner_{safe_name}_*.log")
            log_files = glob.glob(pattern, recursive=True)

            if log_files:
                latest_log = max(log_files, key=os.path.getmtime)
                _cache_runner_log_path(cache_key, latest_log)
                return _read_log_tail(latest_log)

        return None

    except Exception:
        return None


# Runner logs grow to tens of MB over a job's lifetime and live on the network
# share; polling re-reads them every few seconds per job. Everything
# extract_task_progress needs (current progress, node name, loading state) is
# near the end of the file, so read only the tail instead of the whole log.
_LOG_TAIL_BYTES = 256 * 1024


def _read_log_tail(path: str, max_bytes: int = _LOG_TAIL_BYTES) -> str:
    """Read only the last max_bytes of a (potentially huge, remote) log file."""
    with open(path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - max_bytes))
        data = f.read()
    return data.decode('utf-8', errors='replace')


def extract_task_progress(log_content: str) -> Optional[Dict[str, Any]]:
    """
    Extract ComfyUI progress information from task log.

    Searches for patterns like:
    - "Progress: 42% (5/12) (15s)"
    - "[ComfyUI] Progress: 42% (5/12)"

    Also detects model loading state from log patterns.

    Args:
        log_content: Task log stdout text

    Returns:
        Dict with progress_pct, current_node, total_nodes, elapsed_seconds, is_loading_model
        or None if no progress found
    """
    if not log_content:
        return None

    # Check for model loading indicators (patterns precompiled at module level)
    is_loading_model = False
    for pattern in _RE_MODEL_LOADING:
        if pattern.search(log_content):
            is_loading_model = True
            break

    # Also detect server restart which means models need to reload
    if 'RESTART' in log_content.upper() or 'Server restart' in log_content:
        is_loading_model = True

    # Search from end of log (most recent progress) - try runner format first
    matches = list(_RE_PROGRESS_RUNNER.finditer(log_content))

    # If no runner format matches, try tqdm format
    if not matches:
        tqdm_matches = list(_RE_PROGRESS_TQDM.finditer(log_content))
        if tqdm_matches:
            last_tqdm = tqdm_matches[-1]
            # Try to extract node name for tqdm format as well
            current_node_name = None
            for pattern in _RE_NODE_NAME_BASE:
                name_matches = list(pattern.finditer(log_content))
                if name_matches:
                    current_node_name = name_matches[-1].group(1).strip().rstrip('.')
                    break

            return {
                'progress_pct': int(last_tqdm.group(1)),
                'current_node': int(last_tqdm.group(2)),
                'total_nodes': int(last_tqdm.group(3)),
                'elapsed_seconds': None,
                'is_loading_model': is_loading_model and int(last_tqdm.group(2)) == 0,
                'current_node_name': current_node_name
            }

    if not matches:
        # No progress yet - check if execution has started
        # If we see "Execution started" or "Executing node" but no progress,
        # we're likely in the model loading phase
        execution_started = bool(_RE_EXECUTION_STARTED.search(log_content))
        if execution_started or is_loading_model:
            return {
                'progress_pct': 0,
                'current_node': 0,
                'total_nodes': 0,
                'elapsed_seconds': None,
                'is_loading_model': is_loading_model or execution_started,
                'current_node_name': None
            }
        return None

    last_match = matches[-1]
    # Once we have actual progress (current_node > 0), models are loaded
    current_node = int(last_match.group(2))

    # Try to extract current node name from ComfyUI logs
    # Pattern: "Executing node 5: KSampler" or "Executing node 5, title: KSampler"
    current_node_name = None
    for pattern in _RE_NODE_NAME_FULL:
        name_matches = list(pattern.finditer(log_content))
        if name_matches:
            current_node_name = name_matches[-1].group(1).strip()
            # Clean up common suffixes
            if current_node_name:
                current_node_name = current_node_name.rstrip('.')
                break

    return {
        'progress_pct': int(last_match.group(1)),
        'current_node': current_node,
        'total_nodes': int(last_match.group(3)),
        'elapsed_seconds': int(last_match.group(4)) if last_match.group(4) else None,
        'is_loading_model': is_loading_model and current_node == 0,
        'current_node_name': current_node_name
    }


@cached_with_ttl(seconds=30)
def _fetch_pending_luma_jobs() -> Tuple[List[Dict[str, Any]], str]:
    """Fetch and sort the current set of pending luma_tools jobs on Deadline.

    Cached for 30 s so the poll-tick hot path doesn't spam the farm with up to
    101 sequential GetJob calls per tab refresh.

    Returns:
        Tuple of (sorted jobs_info, error_string). On error returns ([], err).
    """
    if not DEADLINE_PATH:
        return [], "Deadline not available"

    result = run_command([DEADLINE_PATH, "GetJobIdsFilter", "Status=Pending"], timeout=30)
    if result.returncode != 0:
        return [], result.stderr.strip()

    pending_job_ids = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    if not pending_job_ids:
        return [], ""

    # Bound both job count AND total wall time: this runs from per-job polling
    # workers, and on a busy farm 100 sequential GetJob calls at 15 s timeout
    # each could occupy a QThreadPool slot (and starve concurrent pollers
    # waiting on the cache) for minutes.
    MAX_JOBS_TO_CHECK = 100
    MAX_TOTAL_SECONDS = 30
    start_time = time.monotonic()
    jobs_info: List[Dict[str, Any]] = []
    for pending_id in pending_job_ids[:MAX_JOBS_TO_CHECK]:
        if time.monotonic() - start_time > MAX_TOTAL_SECONDS:
            logger.debug(
                f"_fetch_pending_luma_jobs: time budget exhausted after "
                f"{len(jobs_info)} job(s); queue info will be partial"
            )
            break
        job_result = run_command([DEADLINE_PATH, "GetJob", pending_id], timeout=15)
        if job_result.returncode != 0:
            continue
        job_info = parse_job_info(job_result.stdout)
        priority = job_info.get("Priority", 50)
        submit_date = job_info.get("SubmitDate", "")
        job_name = job_info.get("Name", "")
        job_user = job_info.get("User", "")
        if job_name.startswith(DEADLINE_JOB_NAME_PREFIX):
            jobs_info.append({
                "id": pending_id,
                "priority": priority,
                "submit_date": submit_date,
                "name": job_name,
                "user": job_user,
            })

    # Higher priority first, then earlier submit date first.
    # _parse_deadline_date converts MM/DD/YYYY strings to datetime so the
    # sort doesn't break across month/year boundaries.
    jobs_info.sort(key=lambda x: (-x["priority"], _parse_deadline_date(x["submit_date"])))
    return jobs_info, ""


def get_queue_info(job_id: str) -> Dict[str, Any]:
    """
    Get queue position information for a job.

    Queries Deadline for all pending/queued jobs and calculates the position
    of the specified job in the queue based on priority and submission time.

    Args:
        job_id: The Deadline job ID to find in the queue

    Returns:
        Dict with:
            - queue_position: Position in queue (1-based), 0 if not in queue
            - total_queued: Total number of queued jobs on the farm
            - jobs_ahead: Number of jobs ahead of this one
            - error: Error message if query failed
    """
    try:
        jobs_info, error = _fetch_pending_luma_jobs()
        if error:
            return {"queue_position": 0, "total_queued": 0, "jobs_ahead": 0, "error": error}
        if not jobs_info:
            return {"queue_position": 0, "total_queued": 0, "jobs_ahead": 0, "error": ""}

        # Get current user from environment (matches job submission user)
        current_user = os.environ.get("USERNAME", "").lower()

        # Find our job and count own vs other jobs ahead
        queue_position = 0
        own_jobs_ahead = 0
        other_jobs_ahead = 0
        target_job_user = ""

        for i, job in enumerate(jobs_info):
            if job["id"] == job_id:
                queue_position = i + 1  # 1-based position
                target_job_user = job["user"].lower()
                break

        # Count jobs ahead, separating own vs others
        if queue_position > 0:
            for i in range(queue_position - 1):
                job_user = jobs_info[i]["user"].lower()
                if job_user == current_user or job_user == target_job_user:
                    own_jobs_ahead += 1
                else:
                    other_jobs_ahead += 1

        total_queued = len(jobs_info)
        jobs_ahead = max(0, queue_position - 1) if queue_position > 0 else total_queued

        return {
            "queue_position": queue_position,
            "total_queued": total_queued,
            "jobs_ahead": jobs_ahead,
            "own_jobs_ahead": own_jobs_ahead,
            "other_jobs_ahead": other_jobs_ahead,
            "error": ""
        }

    except Exception as e:
        return {"queue_position": 0, "total_queued": 0, "jobs_ahead": 0, "error": str(e)}


def complete_deadline_job(job_id: str) -> Tuple[bool, str]:
    """Complete (mark as done) a Deadline job, causing it to be auto-deleted."""
    try:
        if not DEADLINE_PATH:
            return False, "Deadline not available"

        result = run_command([DEADLINE_PATH, "CompleteJob", job_id], timeout=30)

        if result.returncode == 0:
            return True, f"Job {job_id} completed"
        else:
            error = result.stderr.strip() or result.stdout.strip()
            if "not found" in error.lower() or "does not exist" in error.lower():
                return True, f"Job {job_id} already completed or deleted"
            return False, f"Failed to complete job: {error}"

    except Exception as e:
        return False, str(e)


def find_user_running_jobs(username: str) -> List[Dict[str, Any]]:
    """
    Find all running luma_tools jobs for a specific user on Deadline.

    Queries Deadline for Active and Pending jobs submitted by the specified
    user that match luma_tools naming conventions.  Uses Deadline's built-in
    UserName filter so only the user's jobs are returned (avoids querying
    every job on the farm).

    Args:
        username: The username to search for (case-insensitive)

    Returns:
        List of dicts with job info:
            - job_id: Deadline job ID
            - name: Job name
            - status: Current status (Active, Rendering, Pending, Queued)
            - submit_date: When the job was submitted
            - output_dir: Extracted output directory from job properties (if available)
    """
    import time

    running_jobs = []

    if not DEADLINE_PATH or not username:
        return running_jobs

    # Overall time budget to prevent blocking startup for too long
    MAX_TOTAL_SECONDS = 30
    start_time = time.monotonic()

    try:
        # Filter by both Status AND UserName so Deadline only returns this user's jobs
        for status_filter in ["Active", "Pending"]:
            if time.monotonic() - start_time > MAX_TOTAL_SECONDS:
                logger.warning("[Deadline] Recovery query exceeded time budget, returning partial results")
                break

            result = run_command(
                [DEADLINE_PATH, "GetJobIdsFilter",
                 f"Status={status_filter}", f"UserName={username}"],
                timeout=15,
            )

            if result.returncode != 0:
                continue

            job_ids = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]

            for job_id in job_ids:
                if time.monotonic() - start_time > MAX_TOTAL_SECONDS:
                    logger.warning("[Deadline] Recovery query exceeded time budget, returning partial results")
                    break

                try:
                    job_result = run_command([DEADLINE_PATH, "GetJob", job_id], timeout=10)
                except Exception as e:
                    logger.warning(f"[Deadline] Timeout/error fetching job {job_id}: {e}")
                    continue

                if job_result.returncode != 0:
                    continue

                job_info = parse_job_info(job_result.stdout)
                job_name = job_info.get("Name", "")
                job_status = job_info.get("Status", status_filter)
                submit_date = job_info.get("SubmitDate", "")
                output_dir = job_info.get("OutputDirectory0", "")

                # Check if this is a luma_tools job
                is_luma_job = (
                    job_name.startswith(DEADLINE_JOB_NAME_PREFIX) or
                    job_name.endswith("_luma_tools") or
                    job_name == "luma_tools_job"
                )

                if is_luma_job:
                    running_jobs.append({
                        "job_id": job_id,
                        "name": job_name,
                        "status": job_status,
                        "submit_date": submit_date,
                        "output_dir": output_dir,
                    })

        # Sort by submit date (oldest first) so we process in order.
        # Parse the MM/DD/YYYY string — sorting the raw string breaks
        # across month/year boundaries.
        running_jobs.sort(key=lambda x: _parse_deadline_date(x["submit_date"]))

        if running_jobs:
            logger.info(f"[Deadline] Found {len(running_jobs)} running jobs for user {username}")

    except Exception as e:
        logger.error(f"[Deadline] Error finding user jobs: {e}")

    return running_jobs


def cancel_deadline_jobs(job_ids: List[str]) -> Tuple[int, int, List[str]]:
    """Cancel multiple Deadline jobs by completing them."""
    succeeded = 0
    failed = 0
    errors = []

    for job_id in job_ids:
        success, message = complete_deadline_job(job_id)
        if success:
            succeeded += 1
        else:
            failed += 1
            errors.append(f"{job_id}: {message}")

    return succeeded, failed, errors
