"""
Deadline output parsing utilities.

Centralizes the line-by-line Key=Value parsing used across Deadline modules:
- deadline_poller.py
- deadline_submitter.py
- deadline_utils.py
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def parse_deadline_output(output: str) -> Dict[str, str]:
    """
    Parse Deadline command output into key-value dictionary.

    Handles the standard Deadline output format:
        Key1=Value1
        Key2=Value2

    Args:
        output: Raw stdout from Deadline command

    Returns:
        Dictionary of key-value pairs (all values as strings)
    """
    result = {}
    for line in output.split('\n'):
        line = line.strip()
        if '=' in line:
            key, _, value = line.partition('=')
            result[key.strip()] = value.strip()
    return result


# Fields that should be parsed as integers
INT_FIELDS = {
    'Priority', 'CompletedTasks', 'FailedTasks', 'TaskCount',
    'QueuedTasks', 'RenderingTasks', 'ErrorReports',
    'CompletedChunks', 'FailedChunks', 'ChunkCount',
    'QueuedChunks', 'RenderingChunks',
}


def parse_job_info(output: str) -> Dict[str, Any]:
    """
    Parse Deadline GetJob output into structured job info.

    Extracts common job properties with appropriate type conversions.
    Handles both Tasks and Chunks naming conventions.

    Args:
        output: Raw stdout from GetJob command

    Returns:
        Dictionary with typed job properties (ints converted from strings)
    """
    raw = parse_deadline_output(output)

    result = {}
    for key, value in raw.items():
        if key in INT_FIELDS:
            try:
                result[key] = int(value)
            except ValueError:
                result[key] = 0
        else:
            result[key] = value

    return result


def extract_job_id(output: str) -> Optional[str]:
    """
    Extract Deadline job ID from submission output.

    Moved from services/deadline_utils.py for centralization.

    Args:
        output: Raw stdout from job submission

    Returns:
        Job ID string if found, None otherwise
    """
    parsed = parse_deadline_output(output)
    return parsed.get('JobID')


def is_job_not_found(returncode: int, stderr: str, stdout: str) -> bool:
    """
    Check if Deadline command failed because job doesn't exist.

    Used to distinguish between "job deleted" and other errors.

    Args:
        returncode: Command return code
        stderr: Command stderr
        stdout: Command stdout

    Returns:
        True if job was not found (likely deleted)
    """
    if returncode != 0:
        stderr_lower = stderr.lower()
        if "not found" in stderr_lower or "does not exist" in stderr_lower:
            return True
        # Empty stderr with non-zero return code often means job not found
        if not stderr.strip():
            return True
    elif not stdout or "Status=" not in stdout:
        # Job query returned but no status - job doesn't exist
        return True
    return False


def get_task_counts(job_info: Dict[str, Any]) -> Dict[str, int]:
    """
    Extract task/chunk counts from job info, normalizing Tasks vs Chunks naming.

    Deadline uses either Tasks or Chunks naming depending on job type.
    This normalizes to a single set of keys.

    Args:
        job_info: Parsed job info dictionary from parse_job_info()

    Returns:
        Dictionary with normalized keys: completed, failed, total, queued, rendering
    """
    # Try Tasks first, fall back to Chunks
    return {
        'completed': job_info.get('CompletedTasks', job_info.get('CompletedChunks', 0)),
        'failed': job_info.get('FailedTasks', job_info.get('FailedChunks', 0)),
        'total': job_info.get('TaskCount', job_info.get('ChunkCount', 1)),
        'queued': job_info.get('QueuedTasks', job_info.get('QueuedChunks', 0)),
        'rendering': job_info.get('RenderingTasks', job_info.get('RenderingChunks', 0)),
    }


def normalize_job_status(status: str, task_counts: Dict[str, int]) -> str:
    """
    Normalize and refine Deadline job status.

    Handles status variants (Complete vs Completed) and refines Active status
    to Rendering or Queued based on task counts.

    Args:
        status: Raw status from Deadline
        task_counts: Task counts from get_task_counts()

    Returns:
        Normalized status string
    """
    # Normalize "Complete" to "Completed" for consistency
    if status == "Complete":
        status = "Completed"

    # If job completed but has failed tasks, mark as Failed
    if status == "Completed" and task_counts.get('failed', 0) > 0:
        return "Failed"

    # Refine "Active" status based on what's happening
    if status == "Active":
        if task_counts.get('rendering', 0) > 0:
            return "Rendering"
        elif task_counts.get('queued', 0) > 0 and task_counts.get('completed', 0) == 0:
            return "Queued"

    return status


def format_error_message(task_counts: Dict[str, int], error_reports: int = 0) -> str:
    """
    Format an error message based on task failure counts.

    Args:
        task_counts: Task counts from get_task_counts()
        error_reports: Number of error reports from job info

    Returns:
        Error message string, or empty string if no errors
    """
    failed = task_counts.get('failed', 0)
    total = task_counts.get('total', 1)

    if failed > 0:
        msg = f"{failed}/{total} task(s) failed"
        if error_reports > 0:
            msg += f" ({error_reports} error report(s))"
        return msg
    elif error_reports > 0:
        return f"Job has {error_reports} error report(s)"

    return ""
