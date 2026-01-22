"""
ComfyUI Service Module.

Orchestration layer that re-exports functionality from specialized modules.
This maintains backwards compatibility while providing better code organization.

Architecture:
- deadline_submitter.py: Job submission to Deadline farm
- deadline_poller.py: Status polling and queue management
- metadata.py: Gallery metadata and output file management
- workflow.py: Workflow loading, format detection, conversion
- editable.py: Editable node extraction
- modifier.py: Workflow parameter modification
"""

# Re-export workflow manipulation (already split in previous refactoring)
from comfyui.workflow import (
    load_workflow,
    save_workflow,
    is_api_format,
    convert_to_api_format,
    expand_subgraphs,
)
from comfyui.editable import (
    EditableNode,
    extract_editable_nodes,
)
from comfyui.modifier import (
    modify_workflow,
    modify_workflow_api_format,
)

# Re-export deadline submission functions
from comfyui.deadline_submitter import (
    submit_comfyui_to_deadline_server_mode,
    submit_comfyui_to_deadline,
    submit_comfyui_job,
    validate_inputs,
    validate_comfyui_path,
)

# Re-export deadline polling functions
from comfyui.deadline_poller import (
    poll_deadline_job_status,
    get_task_log,
    get_runner_log_from_network,
    extract_task_progress,
    get_queue_info,
    complete_deadline_job,
    cancel_deadline_jobs,
)

# Re-export metadata and output file functions
from comfyui.metadata import (
    get_job_output_files,
    cleanup_job_temp_files,
    scan_output_directory,
    GALLERY_METADATA_FILE,
    clear_gallery_metadata_cache,
    load_gallery_metadata,
    save_gallery_metadata,
    add_image_metadata,
    get_image_metadata,
    get_workflow_preset_for_files,
    extract_prompts_from_editable_values,
    get_model_note,
    set_model_note,
)

# List all public exports for easy discovery
__all__ = [
    # Workflow manipulation
    'load_workflow',
    'save_workflow',
    'is_api_format',
    'convert_to_api_format',
    'expand_subgraphs',
    'EditableNode',
    'extract_editable_nodes',
    'modify_workflow',
    'modify_workflow_api_format',
    # Deadline submission
    'submit_comfyui_to_deadline_server_mode',
    'submit_comfyui_to_deadline',
    'submit_comfyui_job',
    'validate_inputs',
    'validate_comfyui_path',
    # Deadline polling
    'poll_deadline_job_status',
    'get_task_log',
    'get_runner_log_from_network',
    'extract_task_progress',
    'get_queue_info',
    'complete_deadline_job',
    'cancel_deadline_jobs',
    # Metadata and output files
    'get_job_output_files',
    'cleanup_job_temp_files',
    'scan_output_directory',
    'GALLERY_METADATA_FILE',
    'clear_gallery_metadata_cache',
    'load_gallery_metadata',
    'save_gallery_metadata',
    'add_image_metadata',
    'get_image_metadata',
    'get_workflow_preset_for_files',
    'extract_prompts_from_editable_values',
    'get_model_note',
    'set_model_note',
]
