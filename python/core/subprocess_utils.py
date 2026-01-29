"""
Subprocess utilities for consistent cross-platform command execution.

Provides Windows-compatible subprocess execution that hides console windows
and follows the existing patterns in deadline_poller.py, render_service.py, etc.

This centralizes the duplicated subprocess patterns found throughout the codebase:
- comfyui/deadline_poller.py (8 occurrences)
- comfyui/server.py (5 occurrences)
- services/deadline_utils.py
- services/render_service.py
- services/mp4_maker.py
- comfyui/runner.py
- ayon/service.py
"""

import os
import subprocess
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Windows flag for hiding console windows in GUI applications
WINDOWS_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def run_command(
    cmd: List[str],
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """
    Execute a command with Windows-compatible console hiding.

    This is the standard pattern used throughout the codebase for running
    external tools like Deadline, OIIO, and FFmpeg in GUI contexts.

    Args:
        cmd: Command and arguments as a list
        capture_output: Whether to capture stdout/stderr (default: True)
        text: Whether to decode output as text (default: True)
        timeout: Optional timeout in seconds
        cwd: Optional working directory
        shell: Whether to run through shell (default: False)

    Returns:
        subprocess.CompletedProcess with returncode, stdout, stderr

    Example:
        result = run_command(['deadlinecommand', 'GetJob', job_id])
        if result.returncode == 0:
            process_output(result.stdout)
    """
    return subprocess.run(
        cmd,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        cwd=cwd,
        shell=shell,
        creationflags=WINDOWS_NO_WINDOW,
    )


def run_command_with_result(
    cmd: List[str],
    log_prefix: str = "",
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Execute a command and return structured result (success, output, error).

    Provides consistent logging and error handling for Deadline commands.
    Extracted from services/deadline_utils.py:run_deadline_command().

    Args:
        cmd: Command and arguments as list
        log_prefix: Optional prefix for log messages
        timeout: Optional timeout in seconds
        cwd: Optional working directory

    Returns:
        Tuple of (success: bool, stdout: str, stderr: str)
    """
    try:
        result = run_command(cmd, timeout=timeout, cwd=cwd)
        prefix = f"{log_prefix} " if log_prefix else ""

        if result.returncode != 0:
            logger.error(f"{prefix}Command failed: {result.stderr.strip()}")
            return False, result.stdout.strip(), result.stderr.strip()

        return True, result.stdout.strip(), ""
    except subprocess.TimeoutExpired:
        timeout_str = timeout if timeout else "default"
        logger.error(f"Command timed out after {timeout_str}s")
        return False, "", f"Timeout after {timeout_str}s"
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return False, "", str(e)


def start_process(
    cmd: List[str],
    cwd: Optional[str] = None,
    stdout: int = subprocess.PIPE,
    stderr: int = subprocess.STDOUT,
    text: bool = True,
    encoding: str = 'utf-8',
    env: Optional[dict] = None,
    bufsize: int = 1,
) -> subprocess.Popen:
    """
    Start a long-running process with Windows-compatible console hiding.

    Used for starting servers or processes that need output streaming.
    Extracted from comfyui/server.py and comfyui/runner.py.

    Args:
        cmd: Command and arguments as list
        cwd: Working directory
        stdout: Stdout redirection (default: PIPE)
        stderr: Stderr redirection (default: STDOUT)
        text: Whether to decode as text
        encoding: Text encoding (default: utf-8)
        env: Optional environment dict (if None, uses os.environ.copy())
        bufsize: Buffer size for I/O (default: 1 for line buffered)

    Returns:
        subprocess.Popen instance
    """
    process_env = env if env is not None else os.environ.copy()
    if text:
        process_env['PYTHONIOENCODING'] = 'utf-8'

    return subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=stderr,
        text=text,
        encoding=encoding if text else None,
        errors='replace' if text else None,
        bufsize=bufsize,
        cwd=cwd,
        env=process_env,
        creationflags=WINDOWS_NO_WINDOW,
    )
