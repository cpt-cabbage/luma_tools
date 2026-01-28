"""
Deadline Job Submission Module for ComfyUI.

Handles submission of ComfyUI workflows to Deadline farm in both:
- Server mode (persistent ComfyUI server)
- Standard mode (start/stop ComfyUI per task)

Includes validation and batch processing support.
"""

import os
import json
import copy
import random
import logging
from typing import Optional, Callable, List, Dict, Any, Tuple

from core.config import (
    DEADLINE_PATH,
    DEADLINE_POOL,
    DEADLINE_GROUP_COMPFYUI,
    DEADLINE_PRIORITY_COMFYUI,
    DEADLINE_DEPARTMENT,
    COMFYUI_SUPPORTED_EXTENSIONS,
)
from core.settings_manager import get_setting
from core.utils import ensure_directory
from comfyui.utils import resolve_comfyui_paths

logger = logging.getLogger(__name__)


def _get_comfyui_python_exe() -> str:
    """Get ComfyUI Python executable path from settings."""
    comfyui_path = get_setting("comfyui_path")
    comfyui_mode = get_setting("comfyui_mode")
    comfyui_python = get_setting("comfyui_python_path")
    python_exe, _ = resolve_comfyui_paths(comfyui_path, comfyui_mode, comfyui_python or "python")
    return python_exe


def submit_comfyui_to_deadline_server_mode(
    workflow_path: str,
    seeds_file: str,
    output_dir: str,
    batch_name: str,
    render_name: str,
    generation_count: int,
    server_url: str = "http://127.0.0.1:8188",
    priority: Optional[int] = None,
    pool: Optional[str] = None,
    group: Optional[str] = None,
) -> Optional[str]:
    """
    Submit ComfyUI job to Deadline using server mode (persistent ComfyUI).

    Uses a lightweight client script that connects to an already-running
    ComfyUI server. Much faster as models are already loaded in memory.

    Requires comfyui_server.py to be running on the farm node.

    Args:
        workflow_path: Path to workflow JSON file
        seeds_file: Path to JSON file containing seeds for each frame
        output_dir: Output directory for generated outputs
        batch_name: BatchName for Deadline job grouping
        render_name: Name for the job display
        generation_count: Number of generations (frames)
        server_url: URL of the ComfyUI server (default: http://127.0.0.1:8188)
        priority: Job priority (default from config)
        pool: Deadline pool (default from config)
        group: Deadline group (default from config)

    Returns:
        Deadline job ID or None if failed
    """
    if priority is None:
        priority = DEADLINE_PRIORITY_COMFYUI
    if pool is None:
        pool = DEADLINE_POOL
    if group is None:
        group = DEADLINE_GROUP_COMPFYUI

    import shutil

    python_exe = _get_comfyui_python_exe()

    # Get the script paths
    script_dir = os.path.dirname(__file__)
    client_script_source = os.path.join(script_dir, "comfyui_client.py")
    utils_script_source = os.path.join(script_dir, "comfyui_utils.py")
    client_script = os.path.join(output_dir, "comfyui_client.py")
    utils_script = os.path.join(output_dir, "comfyui_utils.py")

    # Copy scripts to output directory for farm access
    for src, dst in [(client_script_source, client_script), (utils_script_source, utils_script)]:
        if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
            shutil.copy2(src, dst)
            logger.info(f"Copied {os.path.basename(src)} to: {dst}")

    # Build arguments for the client script
    timeout = get_setting("comfyui_timeout")
    client_args = (
        f'"{client_script}" '
        f'--workflow "{workflow_path}" '
        f'--seeds-file "{seeds_file}" '
        f'--server-url "{server_url}" '
        f'--server-input-dir "{output_dir}" '
        f'--output-prefix "{render_name}" '
        f'--frame <STARTFRAME> '
        f'--timeout {timeout} '
        f'--wait-for-server 30'
    )

    deadline_command = [
        DEADLINE_PATH,
        '-SubmitCommandLineJob',
        '-executable', python_exe,
        '-arguments', client_args,
        '-frames', f'1-{generation_count}',
        '-chunksize', '1',
        '-pool', pool,
        '-group', group,
        '-priority', str(priority),
        '-prop', f'Department={DEADLINE_DEPARTMENT}',
        '-prop', f'BatchName={batch_name}',
        '-prop', f'OutputDirectory0={output_dir}',
        '-name', f'LUMA TOOLS - {render_name}',
    ]

    logger.info(f"Submitting Luma Tools job (server mode): {render_name}")
    logger.info(f"Frames: 1-{generation_count} (each frame = different seed)")
    logger.info(f"Server URL: {server_url}")

    from services.deadline_utils import submit_deadline_job

    job_id = submit_deadline_job(deadline_command, "[Server Mode]")
    if job_id:
        logger.info(f"ComfyUI Deadline Job ID (server mode): {job_id}")

    return job_id


def submit_comfyui_to_deadline(
    workflow_path: str,
    seeds_file: str,
    output_dir: str,
    batch_name: str,
    render_name: str,
    generation_count: int,
    priority: Optional[int] = None,
    pool: Optional[str] = None,
    group: Optional[str] = None,
    use_server_mode: bool = False,
    full_restart: bool = False,
) -> Optional[str]:
    """
    Submit ComfyUI job to Deadline using CommandLine plugin.

    Uses a runner script that starts ComfyUI, submits the workflow via API,
    waits for completion, then exits. Submits as a multiframe job where each
    frame represents a different seed/generation.

    Args:
        workflow_path: Path to workflow JSON file
        seeds_file: Path to JSON file containing seeds for each frame
        output_dir: Output directory for generated outputs
        batch_name: BatchName for Deadline job grouping
        render_name: Name for the job display
        generation_count: Number of generations (frames)
        priority: Job priority (default from config)
        pool: Deadline pool (default from config)
        group: Deadline group (default from config)
        use_server_mode: If True, keep ComfyUI server running between jobs.
        full_restart: If True, completely restart the ComfyUI server before processing.

    Returns:
        Deadline job ID or None if failed
    """
    if priority is None:
        priority = DEADLINE_PRIORITY_COMFYUI
    if pool is None:
        pool = DEADLINE_POOL
    if group is None:
        group = DEADLINE_GROUP_COMPFYUI

    import shutil

    python_exe = _get_comfyui_python_exe()

    script_dir = os.path.dirname(__file__)
    runner_script_source = os.path.join(script_dir, "runner.py")
    utils_script_source = os.path.join(script_dir, "utils.py")
    runner_script = os.path.join(output_dir, "comfyui_runner.py")
    utils_script = os.path.join(output_dir, "comfyui_utils.py")

    # Copy scripts to output directory for farm access
    # Always copy to ensure latest version (files are small, no performance impact)
    for src, dst in [(runner_script_source, runner_script), (utils_script_source, utils_script)]:
        shutil.copy2(src, dst)
        logger.info(f"Copied {os.path.basename(src)} to: {dst}")

    input_dir = output_dir
    port = 8188 if use_server_mode else random.randint(8200, 8299)

    comfyui_path_clean = comfyui_path.rstrip('/\\')
    timeout = get_setting("comfyui_timeout")
    runner_args = (
        f'"{runner_script}" '
        f'--comfyui-path "{comfyui_path_clean}" '
        f'--workflow "{workflow_path}" '
        f'--seeds-file "{seeds_file}" '
        f'--input-directory "{input_dir}" '
        f'--output-directory "{output_dir}" '
        f'--output-prefix "{render_name}" '
        f'--frame <STARTFRAME> '
        f'--port {port} '
        f'--timeout {timeout} '
        f'--mode {comfyui_mode}'
    )

    if comfyui_mode == "standalone" and comfyui_python:
        runner_args += f' --python-path "{comfyui_python}"'

    if use_server_mode:
        runner_args += ' --persistent'
        server_behavior = get_setting("comfyui_server_not_found_behavior")
        runner_args += f' --server-not-found {server_behavior}'
        if server_behavior == 'wait':
            server_wait_timeout = get_setting("comfyui_server_wait_timeout")
            runner_args += f' --server-wait-timeout {server_wait_timeout}'

    if full_restart:
        runner_args += ' --full-restart'

    comfyui_default_output = os.path.join(comfyui_path, "ComfyUI", "output")
    runner_args += f' --comfyui-output-dir "{comfyui_default_output}"'

    # Add performance flags from global settings
    if get_setting("comfyui_lowvram"):
        runner_args += ' --lowvram'

    job_info_path = os.path.join(output_dir, "comfyui_job_info.txt")
    job_info_content = f"""Plugin=CommandLine
Name=LUMA TOOLS - {render_name}
Department={DEADLINE_DEPARTMENT}
BatchName={batch_name}
Pool={pool}
Group={group}
Priority={priority}
Frames=1-{generation_count}
ChunkSize=1
OutputDirectory0={output_dir}
OnJobComplete=Delete
OverrideTaskFailureDetection=True
FailureDetectionTaskErrors=1
"""

    plugin_info_path = os.path.join(output_dir, "comfyui_plugin_info.txt")
    plugin_info_content = f"""Executable={python_exe}
Arguments={runner_args}
StartupDirectory={output_dir}
ExitCodeTreatedAsFailure=1-255
"""

    with open(job_info_path, 'w') as f:
        f.write(job_info_content)
    with open(plugin_info_path, 'w') as f:
        f.write(plugin_info_content)

    logger.info(f"Submitting Luma Tools job: {render_name}")
    logger.info(f"Frames: 1-{generation_count} (each frame = different seed)")

    deadline_command = [DEADLINE_PATH, job_info_path, plugin_info_path]

    from services.deadline_utils import submit_deadline_job

    job_id = submit_deadline_job(deadline_command)
    if job_id:
        logger.info(f"ComfyUI Deadline Job ID: {job_id}")

    return job_id


def _collect_batch_images(editable_values: Optional[Dict[int, Dict[str, Any]]]) -> Tuple[List[str], int]:
    """
    Collect all batch input files (images, 3D models, etc.) from editable values.

    Returns:
        Tuple of (list of file paths, node_id of the input node)
    """
    if not editable_values:
        return [], -1

    # Priority order: images first, then 3D models
    input_types = ['image', '3d_model']

    for input_type in input_types:
        for node_id, data in editable_values.items():
            node_info = data.get('node')
            value = data.get('value')
            if node_info and node_info.widget_type == input_type:
                if isinstance(value, list):
                    return [p for p in value if os.path.exists(p)], node_id
                elif value and os.path.exists(value):
                    return [value], node_id

    return [], -1


def submit_comfyui_job(
    workflow_path: str,
    input_image: Optional[str],
    prompt: Optional[str],
    output_dir: str,
    generation_count: int,
    job_name: str,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None,
    base_seed: Optional[int] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    network_output_dir: Optional[str] = None,
    use_server_mode: bool = True,
    workflow_preset: Optional[str] = None,
    full_restart: bool = False,
) -> Tuple[List[str], str]:
    """
    Submit ComfyUI job to Deadline. Supports batch input file processing.

    If multiple input files (images, 3D models, etc.) are selected, submits a separate
    job for each file. Each job runs generation_count generations with different seeds.
    Output filenames always include the input filename for traceability.

    Args:
        workflow_path: Path to original workflow JSON file
        input_image: Path to input image (legacy, can be None)
        prompt: Edit prompt text (legacy, can be None)
        output_dir: User's output directory
        generation_count: Number of generations per input file
        job_name: Base name for the job
        editable_values: Dict of node_id -> {'node': EditableNode, 'value': Any}
        base_seed: Optional starting seed (sequential if provided, random if None)
        progress_callback: Optional callback for progress updates
        network_output_dir: Network path where ComfyUI writes outputs
        use_server_mode: Deprecated - server mode is always enabled
        workflow_preset: Full preset name for metadata
        full_restart: If True, restart ComfyUI server before processing

    Returns:
        Tuple of (job_ids, error_message)
    """
    import shutil
    from comfyui.workflow import load_workflow, save_workflow
    from comfyui.modifier import modify_workflow
    from comfyui.metadata import add_image_metadata, extract_prompts_from_editable_values

    if progress_callback:
        progress_callback(5, "Loading workflow...")

    workflow = load_workflow(workflow_path)
    batch_files, input_node_id = _collect_batch_images(editable_values)

    if not batch_files and input_image and os.path.exists(input_image):
        batch_files = [input_image]

    if not batch_files:
        logger.info("No input files found - submitting workflow as-is")
        batch_files = [None]

    total_files = len(batch_files)
    logger.info(f"Batch submission: {total_files} file(s) x {generation_count} generations each")

    if progress_callback:
        progress_callback(10, f"Processing {total_files} file(s)...")

    working_base_dir = network_output_dir if network_output_dir else output_dir

    ensure_directory(output_dir)
    if network_output_dir:
        ensure_directory(network_output_dir)

    all_job_ids = []
    errors = []

    for file_idx, current_file in enumerate(batch_files):
        base_progress = 10 + int((file_idx / total_files) * 80)

        if current_file:
            file_basename = os.path.basename(current_file)
            file_name = os.path.splitext(file_basename)[0]
            # Always append input filename to output prefix for traceability
            current_job_name = f"{job_name}_{file_name}"
            current_working_dir = os.path.join(working_base_dir, file_name) if total_files > 1 else working_base_dir
        else:
            file_basename = None
            current_job_name = job_name
            current_working_dir = working_base_dir

        ensure_directory(current_working_dir)

        if progress_callback:
            msg = f"Submitting {file_idx + 1}/{total_files}"
            if current_file:
                msg += f": {file_basename}"
            progress_callback(base_progress, msg)

        current_editable_values = None
        if editable_values:
            current_editable_values = copy.deepcopy(editable_values)
            if input_node_id >= 0 and input_node_id in current_editable_values:
                current_editable_values[input_node_id]['value'] = current_file

        modified, found_editable = modify_workflow(
            workflow,
            current_file,
            prompt,
            current_job_name,
            seed=12345,
            editable_values=current_editable_values,
            output_dir=current_working_dir,
        )

        if prompt and not found_editable and not current_editable_values:
            error_msg = (
                "No editable prompt node found in workflow. "
                "The workflow must have a TextEncodeQwenImageEditPlus node "
                "with a title ending in '_editable' to accept custom prompts."
            )
            logger.error(error_msg)
            return [], error_msg

        workflow_file = save_workflow(modified, current_working_dir)

        if base_seed is not None:
            seeds = [base_seed + i for i in range(generation_count)]
        else:
            seeds = [random.randint(0, 2**63 - 1) for _ in range(generation_count)]
        seeds_data = {"seeds": seeds, "count": generation_count}

        seeds_file = os.path.join(current_working_dir, "comfyui_seeds.json")
        with open(seeds_file, 'w', encoding='utf-8') as f:
            json.dump(seeds_data, f, indent=2)

        prompt_text = extract_prompts_from_editable_values(current_editable_values)
        if prompt_text or current_file or current_editable_values:
            add_image_metadata(
                output_dir=current_working_dir,
                output_prefix=current_job_name,
                prompt=prompt_text,
                workflow_name=os.path.basename(workflow_path),
                input_image=current_file,
                generation_count=generation_count,
                base_seed=base_seed,
                workflow_preset=workflow_preset,
                editable_values=current_editable_values,
            )

        # Copy input file to working directory for farm access
        if current_file and os.path.exists(current_file):
            file_dest = os.path.join(current_working_dir, file_basename)
            if not os.path.exists(file_dest) or os.path.getmtime(current_file) > os.path.getmtime(file_dest):
                shutil.copy2(current_file, file_dest)

        # Copy additional files (images, 3D models) from editable values
        if current_editable_values:
            for _, data in current_editable_values.items():
                node_info = data.get('node')
                value = data.get('value')

                # Handle both image and 3D model widgets
                if node_info and node_info.widget_type in ('image', '3d_model'):
                    # Value might be a string or a list
                    files_to_copy = []
                    if isinstance(value, list):
                        files_to_copy = value
                    elif value:
                        files_to_copy = [value]

                    for file_path in files_to_copy:
                        # Skip the primary input file (already copied above)
                        if file_path and file_path != current_file and os.path.exists(file_path):
                            file_base = os.path.basename(file_path)
                            file_dest = os.path.join(current_working_dir, file_base)
                            if not os.path.exists(file_dest) or os.path.getmtime(file_path) > os.path.getmtime(file_dest):
                                shutil.copy2(file_path, file_dest)
                                logger.info(f"Copied {node_info.widget_type} file: {file_base}")

        job_id = submit_comfyui_to_deadline(
            workflow_path=workflow_file,
            seeds_file=seeds_file,
            output_dir=current_working_dir,
            batch_name=job_name,
            render_name=current_job_name,
            generation_count=generation_count,
            use_server_mode=True,
            full_restart=full_restart,
        )

        if job_id:
            all_job_ids.append(job_id)
        else:
            errors.append(f"Failed to submit job for file: {file_basename or 'workflow'}")

    if progress_callback:
        progress_callback(95, "Submission complete")

    if all_job_ids:
        return all_job_ids, ""
    else:
        return [], "; ".join(errors) if errors else "Failed to submit any jobs to Deadline"


def validate_inputs(
    workflow_path: str,
    input_image: str,
    prompt: str,
    output_path: str
) -> Tuple[bool, str]:
    """Validate all ComfyUI submission inputs."""
    if not workflow_path:
        return False, "No workflow file selected"
    if not os.path.exists(workflow_path):
        return False, f"Workflow file not found: {workflow_path}"
    if not input_image:
        return False, "No input image selected"
    if not os.path.exists(input_image):
        return False, f"Input image not found: {input_image}"

    ext = os.path.splitext(input_image)[1].lower()
    if ext not in COMFYUI_SUPPORTED_EXTENSIONS:
        return False, f"Unsupported image format: {ext}"

    if not output_path:
        return False, "No output path selected"

    return True, ""


def validate_comfyui_path(path: str) -> Tuple[bool, str]:
    """Validate that a ComfyUI path is configured."""
    if not path:
        return False, "ComfyUI path is not configured"
    return True, ""
