"""
Deadline Job Submission Module for ComfyUI.

Handles submission of ComfyUI workflows to Deadline farm with batch processing support.
Each frame represents a different seed/generation, with optional server persistence
for faster model loading between jobs.
"""

import os
import copy
import random
import logging
from typing import Optional, Callable, List, Dict, Any, Tuple

from core.config import (
    DEADLINE_PATH,
    DEADLINE_POOL,
    DEADLINE_GROUP_COMFYUI,
    DEADLINE_PRIORITY_COMFYUI,
    DEADLINE_DEPARTMENT,
    DEADLINE_JOB_NAME_PREFIX,
)
from core.settings_manager import safe_get_setting
from core.utils import ensure_directory, normalize_path, save_json
from comfyui.utils import resolve_comfyui_paths
from comfyui.image_convert import copy_or_convert

logger = logging.getLogger(__name__)


def _get_comfyui_config() -> Tuple[str, str, str, str]:
    """Get all ComfyUI configuration from settings.

    Returns:
        Tuple of (comfyui_path, comfyui_mode, comfyui_python, python_exe)
    """
    comfyui_path = safe_get_setting("comfyui_path", "")
    comfyui_mode = safe_get_setting("comfyui_mode", "embedded")
    comfyui_python = safe_get_setting("comfyui_python_path", "")
    python_exe, _ = resolve_comfyui_paths(comfyui_path, comfyui_mode, comfyui_python or "python")
    return comfyui_path, comfyui_mode, comfyui_python, python_exe


def _build_server_mode_flags() -> str:
    """Build server connection flags from settings.

    Returns:
        String of flags for server connection behavior
    """
    flags = ""
    server_behavior = safe_get_setting("comfyui_server_not_found_behavior", "fail")
    flags += f" --server-not-found {server_behavior}"

    if server_behavior == "wait":
        server_wait_timeout = safe_get_setting("comfyui_server_wait_timeout", 300)
        flags += f" --server-wait-timeout {server_wait_timeout}"

    return flags


def submit_comfyui_to_deadline(
    workflow_path: str,
    seeds_file: str,
    output_dir: str,
    batch_name: str,
    render_name: str,
    generation_count: int,
    job_data_dir: str,
    priority: Optional[int] = None,
    pool: Optional[str] = None,
    group: Optional[str] = None,
    full_restart: bool = False,
    restart_lowvram: bool = False,
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
        job_data_dir: Unique per-job directory for scripts, workflow, and Deadline files
        priority: Job priority (default from config)
        pool: Deadline pool (default from config)
        group: Deadline group (default from config)
        full_restart: If True, completely restart the ComfyUI server before processing.
        restart_lowvram: If True (and full_restart is True), restart server with --lowvram.

    Returns:
        Deadline job ID or None if failed
    """
    if not DEADLINE_PATH:
        logger.error("Deadline not available — DEADLINE_PATH is not set")
        return None

    if priority is None:
        priority = DEADLINE_PRIORITY_COMFYUI
    if pool is None:
        pool = DEADLINE_POOL
    if group is None:
        group = DEADLINE_GROUP_COMFYUI

    import shutil

    # Get settings needed for this function
    comfyui_path, comfyui_mode, comfyui_python, python_exe = _get_comfyui_config()

    # Scripts are in comfyui package — copy to job_data_dir for farm access
    ensure_directory(job_data_dir)

    python_root = os.path.dirname(os.path.dirname(__file__))
    comfyui_package_dir = os.path.join(python_root, "comfyui")
    core_package_dir = os.path.join(python_root, "core")
    runner_script_source = os.path.join(comfyui_package_dir, "runner.py")
    utils_script_source = os.path.join(comfyui_package_dir, "utils.py")
    analytics_script_source = os.path.join(comfyui_package_dir, "analytics.py")
    node_configs_script_source = os.path.join(comfyui_package_dir, "node_configs.py")
    metadata_script_source = os.path.join(comfyui_package_dir, "metadata.py")
    # core/metadata_file.py is farm-copied too: comfyui_metadata.py imports it
    # (as comfyui_metadata_file) so farm workers write gallery metadata with the
    # same locked, atomic implementation the workstation uses.
    metadata_file_script_source = os.path.join(core_package_dir, "metadata_file.py")
    runner_script = os.path.join(job_data_dir, "comfyui_runner.py")
    utils_script = os.path.join(job_data_dir, "comfyui_utils.py")
    analytics_script = os.path.join(job_data_dir, "comfyui_analytics.py")
    node_configs_script = os.path.join(job_data_dir, "comfyui_node_configs.py")
    metadata_script = os.path.join(job_data_dir, "comfyui_metadata.py")
    metadata_file_script = os.path.join(job_data_dir, "comfyui_metadata_file.py")

    # Copy scripts to output directory for farm access
    # Always copy to ensure latest version (files are small, no performance impact)
    try:
        for src, dst in [
            (runner_script_source, runner_script),
            (utils_script_source, utils_script),
            (analytics_script_source, analytics_script),
            (node_configs_script_source, node_configs_script),
            (metadata_script_source, metadata_script),
            (metadata_file_script_source, metadata_file_script),
        ]:
            shutil.copy2(src, dst)
            logger.info(f"Copied {os.path.basename(src)} to: {dst}")
    except (OSError, shutil.Error) as e:
        logger.error(f"Failed to copy farm script {src} -> {dst}: {e}")
        return None

    # Write farm config alongside scripts so farm modules can find network paths
    # without hardcoded production paths. This is the single source of truth for
    # farm-side settings discovery.
    farm_config = {"network_output_path": safe_get_setting("network_output_path", "")}
    farm_config_path = os.path.join(job_data_dir, "_farm_config.json")
    save_json(farm_config_path, farm_config)

    # All paths embedded in the Deadline job_info / plugin_info files must use
    # forward slashes, otherwise Deadline's CommandLine plugin parses them as
    # escape sequences inside quoted Arguments=.
    workflow_path_n = normalize_path(workflow_path)
    seeds_file_n = normalize_path(seeds_file)
    output_dir_n = normalize_path(output_dir)
    runner_script_n = normalize_path(runner_script)
    job_data_dir_n = normalize_path(job_data_dir)
    python_exe_n = normalize_path(python_exe)

    input_dir = output_dir_n
    port = safe_get_setting("comfyui_port", 8188)

    comfyui_path_clean = normalize_path(comfyui_path.rstrip('/\\'))
    timeout = safe_get_setting("comfyui_timeout", 3600)
    runner_args = (
        f'"{runner_script_n}" '
        f'--comfyui-path "{comfyui_path_clean}" '
        f'--workflow "{workflow_path_n}" '
        f'--seeds-file "{seeds_file_n}" '
        f'--input-directory "{input_dir}" '
        f'--output-directory "{output_dir_n}" '
        f'--output-prefix "{render_name}" '
        f'--frame <STARTFRAME> '
        f'--port {port} '
        f'--timeout {timeout}'
    )

    # Server connection flags
    runner_args += _build_server_mode_flags()

    if full_restart:
        runner_args += ' --full-restart'
        if restart_lowvram:
            runner_args += ' --restart-lowvram'

    comfyui_default_output = normalize_path(os.path.join(comfyui_path, "ComfyUI", "output"))
    runner_args += f' --comfyui-output-dir "{comfyui_default_output}"'

    job_info_path = os.path.join(job_data_dir, "comfyui_job_info.txt")
    job_info_content = f"""Plugin=CommandLine
Name={DEADLINE_JOB_NAME_PREFIX}{render_name}
Department={DEADLINE_DEPARTMENT}
BatchName={batch_name}
Pool={pool}
Group={group}
Priority={priority}
Frames=1-{generation_count}
ChunkSize=1
OutputDirectory0={output_dir_n}
OnJobComplete=Delete
OverrideTaskFailureDetection=True
FailureDetectionTaskErrors=1
"""

    plugin_info_path = os.path.join(job_data_dir, "comfyui_plugin_info.txt")
    plugin_info_content = f"""Executable={python_exe_n}
Arguments={runner_args}
StartupDirectory={job_data_dir_n}
ExitCodeTreatedAsFailure=1-255
"""

    with open(job_info_path, 'w', encoding='utf-8') as f:
        f.write(job_info_content)
    with open(plugin_info_path, 'w', encoding='utf-8') as f:
        f.write(plugin_info_content)

    logger.info(f"Submitting Luma Tools job: {render_name}")
    logger.info(f"Frames: 1-{generation_count} (each frame = different seed)")

    deadline_command = [DEADLINE_PATH, job_info_path, plugin_info_path]

    from deadline.utils import submit_deadline_job

    job_id = submit_deadline_job(deadline_command)
    if job_id:
        logger.info(f"ComfyUI Deadline Job ID: {job_id}")

    return job_id


def _collect_batch_images(editable_values: Optional[Dict[int, list]]) -> Tuple[List[str], int]:
    """
    Collect all batch input files (images, 3D models, etc.) from editable values.

    Returns:
        Tuple of (list of file paths, node_id of the input node)
    """
    if not editable_values:
        return [], -1

    # Priority order: images first, then videos, then 3D models
    input_types = ['image', 'video', '3d_model']

    for input_type in input_types:
        for node_id, entries in editable_values.items():
            entry_list = entries if isinstance(entries, list) else [entries]
            for data in entry_list:
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
    workflow_preset: Optional[str] = None,
    full_restart: bool = False,
    restart_lowvram: bool = False,
    output_type: Optional[str] = None,
    custom_name: Optional[str] = None,
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
        workflow_preset: Full preset name for metadata
        full_restart: If True, restart ComfyUI server before processing
        restart_lowvram: If True (and full_restart is True), restart server with --lowvram
        output_type: Type of output (image, video, 3d, audio, other)

    Returns:
        Tuple of (job_ids, error_message)
    """
    import uuid
    import shutil
    from datetime import datetime
    from comfyui.workflow import load_workflow, save_workflow
    from comfyui.modifier import modify_workflow
    from comfyui.metadata import add_item_metadata, extract_prompts_from_editable_values

    if progress_callback:
        progress_callback(5, "Loading workflow...")

    workflow = load_workflow(workflow_path)
    if not workflow:
        # load_workflow swallows JSONDecodeError and returns {} — without
        # this check a corrupt/missing workflow was submitted to the farm
        # as an empty job that "succeeded" while producing nothing
        error = (
            f"Workflow could not be loaded (missing or invalid JSON): {workflow_path}"
        )
        logger.error(error)
        return [], error

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
                # Update the image/3d_model entry's value to the current batch file
                entries = current_editable_values[input_node_id]
                entry_list = entries if isinstance(entries, list) else [entries]
                for data in entry_list:
                    node_info = data.get('node')
                    if node_info and node_info.widget_type in ('image', 'video', '3d_model'):
                        data['value'] = current_file
                        break

        modified, found_editable, workflow_files_to_copy = modify_workflow(
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

        # Generate unique directory ID and create isolated _job_data/<id>/ directory
        # Each submission gets its own directory to avoid race conditions
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        job_data_id = f"{timestamp}_{unique_suffix}"

        job_data_dir = os.path.join(current_working_dir, "_job_data", job_data_id)
        ensure_directory(job_data_dir)

        workflow_file = save_workflow(modified, job_data_dir, job_id=job_data_id)

        if base_seed is not None:
            seeds = [base_seed + i for i in range(generation_count)]
        else:
            seeds = [random.randint(0, 2**63 - 1) for _ in range(generation_count)]
        seeds_data = {"seeds": seeds, "count": generation_count}

        seeds_file = os.path.join(job_data_dir, f"comfyui_seeds_{job_data_id}.json")
        save_json(seeds_file, seeds_data)

        prompt_text = extract_prompts_from_editable_values(current_editable_values)

        # Compute hashes for source files (for content-based matching)
        source_image_hashes = {}
        try:
            from comfyui.utils import compute_file_hash

            # Hash the primary input file
            if current_file and os.path.exists(current_file):
                file_hash = compute_file_hash(current_file)
                if file_hash:
                    source_image_hashes[os.path.basename(current_file)] = file_hash

            # Hash all file-type editable values (images, videos, 3D models)
            _hashable_types = ('image', 'video', '3d_model')
            if current_editable_values:
                for _, entries in current_editable_values.items():
                    entry_list = entries if isinstance(entries, list) else [entries]
                    for data in entry_list:
                        node_info = data.get('node')
                        value = data.get('value')
                        if node_info and node_info.widget_type in _hashable_types:
                            files = value if isinstance(value, list) else ([value] if value else [])
                            for fpath in files:
                                if fpath and os.path.exists(fpath):
                                    fhash = compute_file_hash(fpath)
                                    if fhash:
                                        source_image_hashes[os.path.basename(fpath)] = fhash

            if source_image_hashes:
                logger.info(f"Computed {len(source_image_hashes)} source file hash(es)")
        except Exception as e:
            logger.warning(f"Could not compute source file hashes: {e}")

        if prompt_text or current_file or current_editable_values:
            add_item_metadata(
                output_dir=current_working_dir,
                output_prefix=current_job_name,
                prompt=prompt_text,
                workflow_name=os.path.basename(workflow_path),
                input_image=current_file,
                generation_count=generation_count,
                base_seed=base_seed,
                workflow_preset=workflow_preset,
                editable_values=current_editable_values,
                output_type=output_type,
                source_image_hashes=source_image_hashes if source_image_hashes else None,
                custom_name=custom_name,
            )

        # Copy input file to working directory for farm access (convert if needed)
        apply_cs = safe_get_setting("comfyui_convert_colorspace", True)
        if current_file and os.path.exists(current_file):
            copy_or_convert(current_file, current_working_dir, apply_colorspace=apply_cs)

        # Copy additional files (images, 3D models) from editable values
        if current_editable_values:
            for _, entries in current_editable_values.items():
                entry_list = entries if isinstance(entries, list) else [entries]
                for data in entry_list:
                    node_info = data.get('node')
                    value = data.get('value')

                    # Handle image, video, and 3D model widgets
                    if not (node_info and node_info.widget_type in ('image', 'video', '3d_model')):
                        continue
                    # Value might be a string or a list
                    files_to_copy = []
                    if isinstance(value, list):
                        files_to_copy = value
                    elif value:
                        files_to_copy = [value]

                    for file_path in files_to_copy:
                        # Skip the primary input file (already copied above)
                        if file_path and file_path != current_file and os.path.exists(file_path):
                            result_path = copy_or_convert(file_path, current_working_dir, apply_colorspace=apply_cs)
                            if result_path:
                                logger.info(f"Copied/converted {node_info.widget_type} file: {os.path.basename(result_path)}")

        # Copy all files detected in workflow (from automatic path normalization)
        if workflow_files_to_copy:
            logger.info(f"Copying {len(workflow_files_to_copy)} file(s) from workflow...")
            for full_path, basename in workflow_files_to_copy.items():
                # Skip if already copied (from current_file or editable values)
                if full_path == current_file:
                    continue
                if os.path.exists(full_path):
                    result_path = copy_or_convert(full_path, current_working_dir, apply_colorspace=apply_cs)
                    if result_path:
                        logger.info(f"Copied/converted workflow file: {os.path.basename(result_path)}")
                else:
                    logger.warning(f"File not found (skipping): {full_path}")

        job_id = submit_comfyui_to_deadline(
            workflow_path=workflow_file,
            seeds_file=seeds_file,
            output_dir=current_working_dir,
            batch_name=job_name,
            render_name=current_job_name,
            generation_count=generation_count,
            job_data_dir=job_data_dir,
            full_restart=full_restart,
            restart_lowvram=restart_lowvram,
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
