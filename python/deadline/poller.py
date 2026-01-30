"""
Deadline Job Polling and Status Monitoring Module.

Handles querying Deadline for job status, progress, queue position,
and task log analysis for ComfyUI workflows.
"""

import os
import logging
from typing import Optional, List, Dict, Any, Tuple

from core.config import DEADLINE_PATH
from core.subprocess_utils import run_command
from deadline.parser import (
    parse_job_info,
    get_task_counts,
    normalize_job_status,
    format_error_message,
    is_job_not_found,
)

logger = logging.getLogger(__name__)


def poll_deadline_job_status(job_id: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Query Deadline for a job's current status.

    Args:
        job_id: The Deadline job ID to query
        output_dir: Optional output directory to check for output files

    Returns:
        Dict with status, progress, completed_tasks, total_tasks, error_message
    """
    try:
        if not DEADLINE_PATH:
            return {"status": "Unknown", "progress": 0, "error_message": "Deadline not available"}

        result = run_command([DEADLINE_PATH, "GetJob", job_id])

        output = result.stdout.strip()

        # Debug: Log raw Deadline response
        logger.info(f"[Poll Debug] Job {job_id}: returncode={result.returncode}, stderr='{result.stderr[:100] if result.stderr else ''}', stdout_len={len(output)}")
        if "Status=" in output:
            # Extract just the status line for debug
            for line in output.split('\n'):
                if line.startswith('Status='):
                    logger.info(f"[Poll Debug] Job {job_id}: {line}")
                    break

        # Check if job was deleted
        if is_job_not_found(result.returncode, result.stderr, output):
            # Import here to avoid circular dependency
            from comfyui.metadata import get_job_output_files

            if output_dir:
                output_files = get_job_output_files(output_dir)
                if output_files:
                    return {
                        "status": "Completed",
                        "progress": 100,
                        "completed_tasks": 1,
                        "total_tasks": 1,
                        "error_message": ""
                    }
                else:
                    return {
                        "status": "Failed",
                        "progress": 100,
                        "completed_tasks": 0,
                        "total_tasks": 1,
                        "error_message": "Job deleted but no output files found"
                    }
            else:
                return {
                    "status": "Completed",
                    "progress": 100,
                    "completed_tasks": 1,
                    "total_tasks": 1,
                    "error_message": ""
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

        # Debug: log raw status from Deadline
        logger.debug(f"[Poll Debug] Job {job_id}: raw_status='{status}', completed={task_counts['completed']}/{task_counts['total']}, failed={task_counts['failed']}")

        # Normalize status
        status = normalize_job_status(status, task_counts)

        logger.debug(f"[Poll Debug] Job {job_id}: final_status='{status}'")

        # Get queue position info for queued/pending jobs
        queue_info = {}
        if status in ("Queued", "Pending"):
            queue_info = get_queue_info(job_id)
            if queue_info.get("queue_position", 0) > 0:
                logger.debug(f"[Poll Debug] Job {job_id}: position {queue_info['queue_position']}/{queue_info['total_queued']} in queue")

        # Try to get detailed progress for rendering tasks
        task_progress = None
        is_loading_model = False
        if status in ("Rendering", "Active") and task_counts['rendering'] > 0:
            # First try to read the runner log from the network output directory
            # This is available immediately and contains all ComfyUI output
            log_content = None
            if output_dir and job_name:
                # Extract the output prefix from the job name (e.g., "LUMA TOOLS - luma_tools_job_xyz" -> "luma_tools_job_xyz")
                if job_name.startswith("LUMA TOOLS - "):
                    output_prefix = job_name[len("LUMA TOOLS - "):]
                    log_content = get_runner_log_from_network(output_dir, output_prefix)
                    if log_content:
                        logger.debug(f"[Poll Debug] Job {job_id}: Got {len(log_content)} bytes from network log")

            # Fall back to Deadline task log if network log not available
            if not log_content:
                active_task_id = task_counts['completed']
                log_content = get_task_log(job_id, active_task_id)
                if log_content:
                    logger.debug(f"[Poll Debug] Job {job_id} task {active_task_id}: Got {len(log_content)} bytes from Deadline log")

            if log_content:
                task_progress = extract_task_progress(log_content)
                if task_progress:
                    is_loading_model = task_progress.get('is_loading_model', False)
                    if is_loading_model:
                        logger.debug(f"[Poll Debug] Job {job_id}: Loading model...")
                    else:
                        logger.debug(f"[Poll Debug] Job {job_id}: {task_progress['progress_pct']}% ({task_progress['current_node']}/{task_progress['total_nodes']} nodes)")
                else:
                    logger.debug(f"[Poll Debug] Job {job_id}: No progress extracted from log")
            else:
                logger.debug(f"[Poll Debug] Job {job_id}: No log content available yet")

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
            timeout=5
        )

        if result.returncode == 0:
            return result.stdout
        return None
    except Exception:
        return None


def get_runner_log_from_network(output_dir: str, job_name: str) -> Optional[str]:
    """
    Get the ComfyUI runner log from the network log directory.

    The runner writes logs to <network_path>/_logs/runner/ with pattern:
    comfyui_runner_{job_name}_{timestamp}.log

    Args:
        output_dir: Network output directory (used as fallback and to derive network path)
        job_name: Job name/output prefix

    Returns:
        Log file contents, or None if not found/readable
    """
    import glob
    from core.logging_utils import get_network_log_dir

    try:
        # Find the most recent log file matching the job name
        # Don't truncate - UUIDs can be longer than 50 chars
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_name)

        # Primary location: network log directory (_logs/runner/)
        log_dir = get_network_log_dir("runner")

        if log_dir and os.path.isdir(log_dir):
            pattern = os.path.join(log_dir, f"comfyui_runner_{safe_name}_*.log")
            logger.debug(f"[Poll Debug] Looking for log with pattern: {pattern}")
            log_files = glob.glob(pattern)
            logger.debug(f"[Poll Debug] Found {len(log_files)} log files in runner dir")

            if log_files:
                latest_log = max(log_files, key=os.path.getmtime)
                logger.debug(f"[Poll Debug] Reading log file: {latest_log}")

                with open(latest_log, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    logger.debug(f"[Poll Debug] Read {len(content)} bytes from runner log")
                    return content

        # Fallback: search in output directory itself (legacy location)
        if output_dir and os.path.isdir(output_dir):
            pattern = os.path.join(output_dir, "**", f"comfyui_runner_{safe_name}_*.log")
            logger.debug(f"[Poll Debug] Fallback: looking in output_dir: {pattern}")
            log_files = glob.glob(pattern, recursive=True)

            if log_files:
                latest_log = max(log_files, key=os.path.getmtime)
                logger.debug(f"[Poll Debug] Reading fallback log file: {latest_log}")

                with open(latest_log, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    logger.debug(f"[Poll Debug] Read {len(content)} bytes from fallback log")
                    return content

        logger.debug(f"[Poll Debug] No log files found for job: {job_name}")
        return None

    except Exception as e:
        logger.error(f"[Poll Debug] Error reading runner log: {e}", exc_info=True)
        return None


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
    import re

    if not log_content:
        return None

    # Detect model loading patterns in ComfyUI logs
    # These patterns appear when ComfyUI is loading models into GPU memory
    model_loading_patterns = [
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
    ]

    # Check for model loading indicators
    is_loading_model = False
    for pattern in model_loading_patterns:
        if re.search(pattern, log_content, re.IGNORECASE):
            is_loading_model = True
            break

    # Also detect server restart which means models need to reload
    if 'RESTART' in log_content.upper() or 'Server restart' in log_content:
        is_loading_model = True

    # Pattern 1: Runner format - Progress: 42% (5/12) (15s) or Progress: 42% (5/12)
    pattern_runner = r'Progress:\s*(\d+)%\s*\((\d+)/(\d+)\)(?:\s*\((\d+)s\))?'

    # Pattern 2: tqdm format - " 12%|█▎        | 1/8 [00:03<00:24,  3.46s/it]"
    # Uses [^\|]* to match ANY characters between pipes (tqdm uses many unicode block chars)
    # Captures: percent, current, total
    pattern_tqdm = r'\s*(\d+)%\|[^\|]*\|\s*(\d+)/(\d+)\s*\['

    # Search from end of log (most recent progress) - try runner format first
    matches = list(re.finditer(pattern_runner, log_content))

    # If no runner format matches, try tqdm format
    if not matches:
        tqdm_matches = list(re.finditer(pattern_tqdm, log_content))
        if tqdm_matches:
            last_tqdm = tqdm_matches[-1]
            return {
                'progress_pct': int(last_tqdm.group(1)),
                'current_node': int(last_tqdm.group(2)),
                'total_nodes': int(last_tqdm.group(3)),
                'elapsed_seconds': None,
                'is_loading_model': is_loading_model and int(last_tqdm.group(2)) == 0
            }

    if not matches:
        # No progress yet - check if execution has started
        # If we see "Execution started" or "Executing node" but no progress,
        # we're likely in the model loading phase
        execution_started = bool(re.search(r'Execution\s+started|Executing\s+node', log_content, re.IGNORECASE))
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

    return {
        'progress_pct': int(last_match.group(1)),
        'current_node': current_node,
        'total_nodes': int(last_match.group(3)),
        'elapsed_seconds': int(last_match.group(4)) if last_match.group(4) else None,
        'is_loading_model': is_loading_model and current_node == 0
    }


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
        if not DEADLINE_PATH:
            return {"queue_position": 0, "total_queued": 0, "jobs_ahead": 0, "error": "Deadline not available"}

        # Get all pending (queued) jobs
        result = run_command([DEADLINE_PATH, "GetJobIdsFilter", "Status=Pending"])

        if result.returncode != 0:
            return {"queue_position": 0, "total_queued": 0, "jobs_ahead": 0, "error": result.stderr.strip()}

        # Parse job IDs from output (one per line)
        pending_job_ids = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]

        if not pending_job_ids:
            return {"queue_position": 0, "total_queued": 0, "jobs_ahead": 0, "error": ""}

        # Get job details for all pending jobs to sort by priority/submission time
        # Filter to only luma_tools ComfyUI jobs
        jobs_info = []
        for pending_id in pending_job_ids:
            job_result = run_command([DEADLINE_PATH, "GetJob", pending_id])

            if job_result.returncode == 0:
                job_info = parse_job_info(job_result.stdout)
                priority = job_info.get("Priority", 50)
                submit_date = job_info.get("SubmitDate", "")
                job_name = job_info.get("Name", "")
                job_user = job_info.get("User", "")

                # Only include luma_tools ComfyUI jobs (job names end with "_luma_tools" or equal "luma_tools_job")
                if job_name.endswith("_luma_tools") or job_name == "luma_tools_job":
                    jobs_info.append({
                        "id": pending_id,
                        "priority": priority,
                        "submit_date": submit_date,
                        "name": job_name,
                        "user": job_user
                    })

        # Sort by priority (higher first), then by submit date (earlier first)
        jobs_info.sort(key=lambda x: (-x["priority"], x["submit_date"]))

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

        result = run_command([DEADLINE_PATH, "CompleteJob", job_id])

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

    Queries Deadline for Active, Rendering, Pending, and Queued jobs
    submitted by the specified user that match luma_tools naming conventions.

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
    running_jobs = []

    logger.debug(f"[find_user_running_jobs] Looking for jobs from user: '{username}'")
    logger.debug(f"[find_user_running_jobs] DEADLINE_PATH: {DEADLINE_PATH}")

    if not DEADLINE_PATH:
        logger.debug("[find_user_running_jobs] No DEADLINE_PATH configured")
        return running_jobs

    if not username:
        logger.debug("[find_user_running_jobs] No username provided")
        return running_jobs

    username_lower = username.lower()

    try:
        # Get all active/pending jobs from Deadline
        for status_filter in ["Active", "Pending"]:
            logger.debug(f"[find_user_running_jobs] Querying Deadline for {status_filter} jobs...")
            result = run_command([DEADLINE_PATH, "GetJobIdsFilter", f"Status={status_filter}"])

            if result.returncode != 0:
                logger.error(f"[find_user_running_jobs] GetJobIdsFilter failed: {result.stderr}")
                continue

            job_ids = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            logger.debug(f"[find_user_running_jobs] Found {len(job_ids)} {status_filter} jobs on Deadline")

            for job_id in job_ids:
                job_result = run_command([DEADLINE_PATH, "GetJob", job_id])

                if job_result.returncode != 0:
                    continue

                job_info = parse_job_info(job_result.stdout)
                job_name = job_info.get("Name", "")
                job_user = job_info.get("UserName", job_info.get("User", ""))
                job_status = job_info.get("Status", status_filter)
                submit_date = job_info.get("SubmitDate", "")
                output_dir = job_info.get("OutputDirectory0", "")

                # Check if this is a luma_tools job from the specified user
                is_luma_job = (
                    job_name.startswith("LUMA TOOLS - ") or
                    job_name.endswith("_luma_tools") or
                    job_name == "luma_tools_job"
                )

                # Debug: show luma_tools jobs we're checking
                if is_luma_job:
                    logger.debug(f"[find_user_running_jobs] Job {job_id}: name='{job_name}', user='{job_user}', user_match={job_user.lower() == username_lower}")

                if is_luma_job and job_user.lower() == username_lower:
                    running_jobs.append({
                        "job_id": job_id,
                        "name": job_name,
                        "status": job_status,
                        "submit_date": submit_date,
                        "output_dir": output_dir,
                    })

        # Sort by submit date (oldest first) so we process in order
        running_jobs.sort(key=lambda x: x["submit_date"])
        logger.debug(f"[find_user_running_jobs] Total matching jobs found: {len(running_jobs)}")

    except Exception as e:
        logger.error(f"[find_user_running_jobs] Error: {e}", exc_info=True)

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
