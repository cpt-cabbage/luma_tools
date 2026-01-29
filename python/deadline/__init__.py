"""
Deadline integration package.

Centralizes all Deadline-related functionality:
- Job submission (submit_comfyui_to_deadline, submit_comfyui_to_deadline_server_mode)
- Job polling and status monitoring (poll_deadline_job_status, get_queue_info)
- Output parsing utilities (parse_deadline_output, extract_job_id)
- General Deadline command utilities (run_deadline_command, submit_deadline_job)
"""

from deadline.parser import (
    parse_deadline_output,
    parse_job_info,
    extract_job_id,
    is_job_not_found,
    get_task_counts,
    normalize_job_status,
    format_error_message,
)

from deadline.utils import (
    run_deadline_command,
    submit_deadline_job,
)

from deadline.poller import (
    poll_deadline_job_status,
    get_queue_info,
    get_task_log,
    get_runner_log_from_network,
    extract_task_progress,
    complete_deadline_job,
    find_user_running_jobs,
    cancel_deadline_jobs,
)

from deadline.submitter import (
    submit_comfyui_to_deadline,
    submit_comfyui_to_deadline_server_mode,
    submit_comfyui_job,
    validate_inputs,
    validate_comfyui_path,
)

__all__ = [
    # Parser
    'parse_deadline_output',
    'parse_job_info',
    'extract_job_id',
    'is_job_not_found',
    'get_task_counts',
    'normalize_job_status',
    'format_error_message',
    # Utils
    'run_deadline_command',
    'submit_deadline_job',
    # Poller
    'poll_deadline_job_status',
    'get_queue_info',
    'get_task_log',
    'get_runner_log_from_network',
    'extract_task_progress',
    'complete_deadline_job',
    'find_user_running_jobs',
    'cancel_deadline_jobs',
    # Submitter
    'submit_comfyui_to_deadline',
    'submit_comfyui_to_deadline_server_mode',
    'submit_comfyui_job',
    'validate_inputs',
    'validate_comfyui_path',
]
