"""
ComfyUI Service Module.

Handles Deadline job submission, status polling, and gallery metadata management.

Workflow manipulation is split into separate modules:
- comfyui_workflow.py: Loading, format detection, conversion
- comfyui_editable.py: Editable node extraction
- comfyui_modifier.py: Workflow parameter modification
"""

import os
import json
import copy
import random
import subprocess
from typing import Optional, Callable, List, Dict, Any, Tuple

from core.config import (
    DEADLINE_PATH,
    DEADLINE_POOL,
    DEADLINE_GROUP_COMPFYUI,
    DEADLINE_PRIORITY_COMFYUI,
    DEADLINE_DEPARTMENT,
    COMFYUI_SUPPORTED_EXTENSIONS,
    COMFYUI_OUTPUT_EXTENSIONS,
)
from core.settings_manager import get_setting

# Re-export from split modules for backwards compatibility
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

    # Get ComfyUI paths and mode from settings
    comfyui_path = get_setting("comfyui_path")
    comfyui_mode = get_setting("comfyui_mode")
    comfyui_python = get_setting("comfyui_python_path")

    # Determine Python executable based on mode
    if comfyui_mode == "embedded":
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
    elif comfyui_mode == "portable":
        python_exe = os.path.join(comfyui_path, "venv", "Scripts", "python.exe")
    else:
        python_exe = comfyui_python if comfyui_python else "python"

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
            print(f"Copied {os.path.basename(src)} to: {dst}")

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

    print(f"Submitting Luma Tools job (server mode): {render_name}")
    print(f"Frames: 1-{generation_count} (each frame = different seed)")
    print(f"Server URL: {server_url}")

    from services.deadline_utils import submit_deadline_job

    job_id = submit_deadline_job(deadline_command, "[Server Mode]")
    if job_id:
        print(f"ComfyUI Deadline Job ID (server mode): {job_id}")

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

    comfyui_path = get_setting("comfyui_path")
    comfyui_mode = get_setting("comfyui_mode")
    comfyui_python = get_setting("comfyui_python_path")

    if comfyui_mode == "embedded":
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
    elif comfyui_mode == "portable":
        python_exe = os.path.join(comfyui_path, "venv", "Scripts", "python.exe")
    else:
        python_exe = comfyui_python if comfyui_python else "python"

    script_dir = os.path.dirname(__file__)
    runner_script_source = os.path.join(script_dir, "runner.py")
    utils_script_source = os.path.join(script_dir, "utils.py")
    runner_script = os.path.join(output_dir, "comfyui_runner.py")
    utils_script = os.path.join(output_dir, "comfyui_utils.py")

    # Copy scripts to output directory for farm access
    # Always copy to ensure latest version (files are small, no performance impact)
    for src, dst in [(runner_script_source, runner_script), (utils_script_source, utils_script)]:
        shutil.copy2(src, dst)
        print(f"Copied {os.path.basename(src)} to: {dst}")

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

    print(f"Submitting Luma Tools job: {render_name}")
    print(f"Frames: 1-{generation_count} (each frame = different seed)")

    deadline_command = [DEADLINE_PATH, job_info_path, plugin_info_path]

    from services.deadline_utils import submit_deadline_job

    job_id = submit_deadline_job(deadline_command)
    if job_id:
        print(f"ComfyUI Deadline Job ID: {job_id}")

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

    if progress_callback:
        progress_callback(5, "Loading workflow...")

    workflow = load_workflow(workflow_path)
    batch_files, input_node_id = _collect_batch_images(editable_values)

    if not batch_files and input_image and os.path.exists(input_image):
        batch_files = [input_image]

    if not batch_files:
        print("No input files found - submitting workflow as-is")
        batch_files = [None]

    total_files = len(batch_files)
    print(f"Batch submission: {total_files} file(s) x {generation_count} generations each")

    if progress_callback:
        progress_callback(10, f"Processing {total_files} file(s)...")

    working_base_dir = network_output_dir if network_output_dir else output_dir

    os.makedirs(output_dir, exist_ok=True)
    if network_output_dir:
        os.makedirs(network_output_dir, exist_ok=True)

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

        os.makedirs(current_working_dir, exist_ok=True)

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
            print(f"ERROR: {error_msg}")
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

        # Copy additional 3D models if present in editable values
        if current_editable_values:
            for _, data in current_editable_values.items():
                node_info = data.get('node')
                value = data.get('value')
                # Skip the primary input file (already copied above)
                if node_info and node_info.widget_type == '3d_model' and value and value != current_file:
                    if os.path.exists(value):
                        model_basename = os.path.basename(value)
                        model_dest = os.path.join(current_working_dir, model_basename)
                        if not os.path.exists(model_dest) or os.path.getmtime(value) > os.path.getmtime(model_dest):
                            shutil.copy2(value, model_dest)

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

        result = subprocess.run(
            [DEADLINE_PATH, "GetJob", job_id],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        output = result.stdout.strip()
        job_deleted = False

        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "not found" in stderr or "does not exist" in stderr or not result.stderr.strip():
                job_deleted = True
        elif not output or "Status=" not in output:
            job_deleted = True

        if job_deleted:
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

        status = "Unknown"
        completed_tasks = 0
        failed_tasks = 0
        total_tasks = 1
        queued_tasks = 0
        rendering_tasks = 0
        error_reports = 0
        error_message = ""
        job_name = ""

        for line in output.split('\n'):
            line = line.strip()
            if line.startswith("Status="):
                status = line.split('=', 1)[1]
            elif line.startswith("Name="):
                job_name = line.split('=', 1)[1]
            elif line.startswith("CompletedTasks=") or line.startswith("CompletedChunks="):
                completed_tasks = int(line.split('=', 1)[1])
            elif line.startswith("FailedTasks=") or line.startswith("FailedChunks="):
                failed_tasks = int(line.split('=', 1)[1])
            elif line.startswith("TaskCount=") or line.startswith("ChunkCount="):
                total_tasks = int(line.split('=', 1)[1])
            elif line.startswith("QueuedTasks=") or line.startswith("QueuedChunks="):
                queued_tasks = int(line.split('=', 1)[1])
            elif line.startswith("RenderingTasks=") or line.startswith("RenderingChunks="):
                rendering_tasks = int(line.split('=', 1)[1])
            elif line.startswith("ErrorReports="):
                error_reports = int(line.split('=', 1)[1])

        if failed_tasks > 0:
            error_message = f"{failed_tasks}/{total_tasks} task(s) failed"
            if error_reports > 0:
                error_message += f" ({error_reports} error report(s))"
        elif error_reports > 0:
            error_message = f"Job has {error_reports} error report(s)"

        progress = int((completed_tasks / max(total_tasks, 1)) * 100)

        # Debug: log raw status from Deadline
        print(f"[Poll Debug] Job {job_id}: raw_status='{status}', completed={completed_tasks}/{total_tasks}, failed={failed_tasks}")

        # Normalize "Complete" to "Completed" for consistency
        if status == "Complete":
            status = "Completed"

        if status == "Completed" and failed_tasks > 0:
            status = "Failed"

        if status == "Active":
            if rendering_tasks > 0:
                status = "Rendering"
            elif queued_tasks > 0 and completed_tasks == 0:
                status = "Queued"

        print(f"[Poll Debug] Job {job_id}: final_status='{status}'")

        # Get queue position info for queued/pending jobs
        queue_info = {}
        if status in ("Queued", "Pending"):
            queue_info = get_queue_info(job_id)
            if queue_info.get("queue_position", 0) > 0:
                print(f"[Poll Debug] Job {job_id}: position {queue_info['queue_position']}/{queue_info['total_queued']} in queue")

        # Try to get detailed progress for rendering tasks
        task_progress = None
        is_loading_model = False
        if status in ("Rendering", "Active") and rendering_tasks > 0:
            # First try to read the runner log from the network output directory
            # This is available immediately and contains all ComfyUI output
            log_content = None
            if output_dir and job_name:
                # Extract the output prefix from the job name (e.g., "LUMA TOOLS - luma_tools_job_xyz" -> "luma_tools_job_xyz")
                if job_name.startswith("LUMA TOOLS - "):
                    output_prefix = job_name[len("LUMA TOOLS - "):]
                    log_content = get_runner_log_from_network(output_dir, output_prefix)
                    if log_content:
                        print(f"[Poll Debug] Job {job_id}: Got {len(log_content)} bytes from network log")

            # Fall back to Deadline task log if network log not available
            if not log_content:
                active_task_id = completed_tasks
                log_content = get_task_log(job_id, active_task_id)
                if log_content:
                    print(f"[Poll Debug] Job {job_id} task {active_task_id}: Got {len(log_content)} bytes from Deadline log")

            if log_content:
                task_progress = extract_task_progress(log_content)
                if task_progress:
                    is_loading_model = task_progress.get('is_loading_model', False)
                    if is_loading_model:
                        print(f"[Poll Debug] Job {job_id}: Loading model...")
                    else:
                        print(f"[Poll Debug] Job {job_id}: {task_progress['progress_pct']}% ({task_progress['current_node']}/{task_progress['total_nodes']} nodes)")
                else:
                    print(f"[Poll Debug] Job {job_id}: No progress extracted from log")
            else:
                print(f"[Poll Debug] Job {job_id}: No log content available yet")

        return {
            "status": status,
            "progress": progress,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "queued_tasks": queued_tasks,
            "rendering_tasks": rendering_tasks,
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

        result = subprocess.run(
            [DEADLINE_PATH, "GetTaskLog", job_id, str(task_id)],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        if result.returncode == 0:
            return result.stdout
        return None
    except Exception:
        return None


def get_runner_log_from_network(output_dir: str, job_name: str) -> Optional[str]:
    """
    Get the ComfyUI runner log from the network output directory.

    The runner writes logs to the network output directory with pattern:
    comfyui_runner_{job_name}_{timestamp}.log

    Args:
        output_dir: Network output directory
        job_name: Job name/output prefix

    Returns:
        Log file contents, or None if not found/readable
    """
    import glob
    try:
        if not output_dir or not os.path.isdir(output_dir):
            print(f"[Debug] Output dir not valid: {output_dir}")
            return None

        # Find the most recent log file matching the job name
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_name)[:50]
        pattern = os.path.join(output_dir, f"comfyui_runner_{safe_name}_*.log")
        print(f"[Debug] Looking for log with pattern: {pattern}")
        log_files = glob.glob(pattern)
        print(f"[Debug] Found {len(log_files)} log files: {log_files[:3] if len(log_files) > 3 else log_files}")

        if not log_files:
            return None

        # Get the most recent log file
        latest_log = max(log_files, key=os.path.getmtime)
        print(f"[Debug] Reading log file: {latest_log}")

        # Read the log file
        with open(latest_log, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            print(f"[Debug] Read {len(content)} bytes from log file")
            return content

    except Exception as e:
        print(f"[Debug] Error reading runner log: {e}")
        import traceback
        traceback.print_exc()
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

    # Pattern: Progress: 42% (5/12) (15s) or Progress: 42% (5/12)
    pattern = r'Progress:\s*(\d+)%\s*\((\d+)/(\d+)\)(?:\s*\((\d+)s\))?'

    # Search from end of log (most recent progress)
    matches = list(re.finditer(pattern, log_content))
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
                'is_loading_model': is_loading_model or execution_started
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
        result = subprocess.run(
            [DEADLINE_PATH, "GetJobIdsFilter", "Status=Pending"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

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
            job_result = subprocess.run(
                [DEADLINE_PATH, "GetJob", pending_id],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if job_result.returncode == 0:
                priority = 50  # Default priority
                submit_date = ""
                job_name = ""
                job_user = ""

                for line in job_result.stdout.split('\n'):
                    line = line.strip()
                    if line.startswith("Priority="):
                        try:
                            priority = int(line.split('=', 1)[1])
                        except ValueError:
                            pass
                    elif line.startswith("SubmitDate="):
                        submit_date = line.split('=', 1)[1]
                    elif line.startswith("Name="):
                        job_name = line.split('=', 1)[1]
                    elif line.startswith("User="):
                        job_user = line.split('=', 1)[1]

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

        result = subprocess.run(
            [DEADLINE_PATH, "CompleteJob", job_id],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        if result.returncode == 0:
            return True, f"Job {job_id} completed"
        else:
            error = result.stderr.strip() or result.stdout.strip()
            if "not found" in error.lower() or "does not exist" in error.lower():
                return True, f"Job {job_id} already completed or deleted"
            return False, f"Failed to complete job: {error}"

    except Exception as e:
        return False, str(e)


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


def get_job_output_files(output_dir: str) -> List[str]:
    """Get the output files from a job's output directory."""
    if not output_dir or not os.path.isdir(output_dir):
        return []

    supported_extensions = set(COMFYUI_OUTPUT_EXTENSIONS)
    files = []

    for filename in os.listdir(output_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext in supported_extensions:
            full_path = os.path.join(output_dir, filename)
            mtime = os.path.getmtime(full_path)
            files.append((full_path, mtime))

    files.sort(key=lambda x: x[1], reverse=True)
    return [f[0] for f in files]


def cleanup_job_temp_files(output_dir: str) -> int:
    """Clean up temporary job files from the output directory."""
    import glob

    if not output_dir or not os.path.exists(output_dir):
        return 0

    temp_patterns = [
        "comfyui_workflow*.json",
        "comfyui_seeds.json",
        "comfyui_runner.py",
        "comfyui_client.py",
        "comfyui_utils.py",
        "comfyui_job_info.txt",
        "comfyui_plugin_info.txt",
    ]

    deleted_count = 0

    for pattern in temp_patterns:
        for file_path in glob.glob(os.path.join(output_dir, pattern)):
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception:
                pass

    return deleted_count


def scan_output_directory(output_dir: str) -> List[Dict[str, Any]]:
    """Scan directory for generated ComfyUI output files."""
    import glob
    from datetime import datetime

    if not output_dir or not os.path.exists(output_dir):
        return []

    output_files = []

    for ext in COMFYUI_OUTPUT_EXTENSIONS:
        pattern = os.path.join(output_dir, '**', f'*{ext}')
        for path in glob.glob(pattern, recursive=True):
            try:
                stat = os.stat(path)
                output_files.append({
                    'path': path,
                    'filename': os.path.basename(path),
                    'created': datetime.fromtimestamp(stat.st_ctime),
                    'size': stat.st_size,
                    'extension': ext,
                })
            except Exception:
                pass

    output_files.sort(key=lambda x: x['created'], reverse=True)
    return output_files


# ============================================================================
# GALLERY METADATA
# ============================================================================

GALLERY_METADATA_FILE = "comfyui_gallery_metadata.json"
_gallery_metadata_cache: Dict[str, Tuple[float, Dict[str, Dict[str, Any]]]] = {}


def _get_metadata_path(output_dir: str) -> str:
    """Get the path to the metadata file for a directory."""
    return os.path.join(output_dir, GALLERY_METADATA_FILE)


def clear_gallery_metadata_cache(output_dir: str = None) -> None:
    """Clear the gallery metadata cache."""
    global _gallery_metadata_cache
    if output_dir:
        _gallery_metadata_cache.pop(output_dir, None)
    else:
        _gallery_metadata_cache.clear()


def load_gallery_metadata(output_dir: str, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
    """Load gallery metadata from the output directory."""
    global _gallery_metadata_cache

    metadata_path = _get_metadata_path(output_dir)
    if not os.path.exists(metadata_path):
        return {}

    try:
        current_mtime = os.path.getmtime(metadata_path)

        if use_cache and output_dir in _gallery_metadata_cache:
            cached_mtime, cached_data = _gallery_metadata_cache[output_dir]
            if cached_mtime == current_mtime:
                return cached_data

        with open(metadata_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _gallery_metadata_cache[output_dir] = (current_mtime, data)
            return data
    except Exception as e:
        print(f"Error loading gallery metadata: {e}")
        return {}


def save_gallery_metadata(output_dir: str, metadata: Dict[str, Dict[str, Any]]) -> bool:
    """Save gallery metadata to the output directory."""
    metadata_path = _get_metadata_path(output_dir)

    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)
        clear_gallery_metadata_cache(output_dir)
        return True
    except Exception as e:
        print(f"Error saving gallery metadata: {e}")
        return False


def add_image_metadata(
    output_dir: str,
    output_prefix: str,
    prompt: Optional[str] = None,
    workflow_name: Optional[str] = None,
    input_image: Optional[str] = None,
    generation_count: int = 1,
    base_seed: Optional[int] = None,
    workflow_preset: Optional[str] = None,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None,
) -> bool:
    """Add metadata for images that will be generated with a given prefix."""
    from datetime import datetime

    metadata = load_gallery_metadata(output_dir)

    serialized_editable = {}
    if editable_values:
        for node_id, data in editable_values.items():
            node_info = data.get('node')
            value = data.get('value')

            if node_info and node_info.widget_type == 'image':
                continue

            serialized_editable[str(node_id)] = {
                "node_id": node_info.node_id if node_info else node_id,
                "display_name": node_info.display_name if node_info else "",
                "node_type": node_info.node_type if node_info else "",
                "widget_type": node_info.widget_type if node_info else "text",
                "value": value,
            }

    entry = {
        "prompt": prompt,
        "workflow": workflow_name,
        "workflow_preset": workflow_preset,
        "input_image": os.path.basename(input_image) if input_image else None,
        "timestamp": datetime.now().isoformat(),
        "generation_count": generation_count,
        "base_seed": base_seed,
        "editable_values": serialized_editable if serialized_editable else None,
    }

    prefix_key = output_prefix.rstrip('_')
    metadata[f"_prefix_{prefix_key}"] = entry

    return save_gallery_metadata(output_dir, metadata)


def get_image_metadata(output_dir: str, filename: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific image file."""
    metadata = load_gallery_metadata(output_dir)
    return _lookup_file_metadata(metadata, filename)


def _lookup_file_metadata(metadata: Dict[str, Dict[str, Any]], filename: str) -> Optional[Dict[str, Any]]:
    """Internal helper to look up metadata for a filename."""
    if filename in metadata:
        return metadata[filename]

    basename = os.path.splitext(filename)[0]

    for key, value in metadata.items():
        if key.startswith("_prefix_"):
            prefix = key[8:]
            if basename.startswith(prefix):
                return value

    return None


def get_workflow_preset_for_files(output_dir: str, filenames: List[str]) -> Dict[str, str]:
    """Get workflow preset names for multiple files efficiently."""
    metadata = load_gallery_metadata(output_dir)
    results = {}

    for filename in filenames:
        file_metadata = _lookup_file_metadata(metadata, filename)
        if file_metadata:
            results[filename] = file_metadata.get('workflow_preset', '') or ''
        else:
            results[filename] = ''

    return results


def extract_prompts_from_editable_values(
    editable_values: Optional[Dict[int, Dict[str, Any]]]
) -> str:
    """Extract prompt text from editable values dictionary."""
    if not editable_values:
        return ""

    prompts = []
    for data in editable_values.values():
        node_info = data.get('node')
        value = data.get('value')
        if node_info and node_info.widget_type == 'text' and value:
            prompts.append(str(value).strip())

    return "\n---\n".join(prompts) if prompts else ""


def get_model_note(output_dir: str, filename: str) -> str:
    """Get the user note for a specific model file."""
    metadata = load_gallery_metadata(output_dir)
    basename = os.path.splitext(filename)[0]
    note_key = f"_note_{basename}"
    return metadata.get(note_key, "")


def set_model_note(output_dir: str, filename: str, note: str) -> bool:
    """Set a user note for a specific model file."""
    metadata = load_gallery_metadata(output_dir)
    basename = os.path.splitext(filename)[0]
    note_key = f"_note_{basename}"

    if note.strip():
        metadata[note_key] = note.strip()
    elif note_key in metadata:
        del metadata[note_key]

    return save_gallery_metadata(output_dir, metadata)
