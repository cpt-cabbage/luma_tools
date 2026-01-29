"""
Deadline utility functions.

Provides common functionality for Deadline job submission and management.
"""
import logging
from typing import Optional, Tuple, List

from core.subprocess_utils import run_command
from deadline.parser import extract_job_id

logger = logging.getLogger(__name__)


def run_deadline_command(deadline_command: List[str], log_prefix: str = "") -> Tuple[bool, str, str]:
    """
    Execute a Deadline command and return success status with output.

    Args:
        deadline_command: List of command arguments
        log_prefix: Optional prefix for log messages

    Returns:
        Tuple of (success: bool, output: str, error_message: str)
    """
    try:
        result = run_command(deadline_command)
        result_output = result.stdout.strip()

        prefix = f"{log_prefix} " if log_prefix else ""
        logger.info(f"{prefix}Deadline submission result: {result_output}")

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            logger.error(f"{prefix}Deadline submission error: {error_msg}")
            return False, result_output, error_msg

        return True, result_output, ""
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error submitting to Deadline: {error_msg}")
        return False, "", error_msg


def submit_deadline_job(deadline_command: List[str], log_prefix: str = "") -> Optional[str]:
    """
    Submit a job to Deadline and return the job ID.

    Args:
        deadline_command: List of command arguments for deadlinecommand
        log_prefix: Optional prefix for log messages

    Returns:
        Job ID if submission succeeded, None otherwise
    """
    success, output, error = run_deadline_command(deadline_command, log_prefix)
    if success:
        return extract_job_id(output)
    return None
