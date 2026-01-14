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

from config import (
    DEADLINE_PATH,
    DEADLINE_POOL,
    DEADLINE_GROUP_COMPFYUI,
    DEADLINE_PRIORITY_COMFYUI,
    DEADLINE_DEPARTMENT,
    COMFYUI_SUPPORTED_EXTENSIONS,
    COMFYUI_OUTPUT_EXTENSIONS,
)
from settings_manager import (
    get_comfyui_path, get_comfyui_mode, get_comfyui_python_path,
    get_comfyui_fast_mode, get_comfyui_fp16_accumulation, get_comfyui_timeout
)

# Re-export from split modules for backwards compatibility
from comfyui_workflow import (
    load_workflow,
    save_workflow,
    is_api_format,
    convert_to_api_format,
)
from comfyui_editable import (
    EditableNode,
    extract_editable_nodes,
)
from comfyui_modifier import (
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
    comfyui_path = get_comfyui_path()
    comfyui_mode = get_comfyui_mode()
    comfyui_python = get_comfyui_python_path()

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
    timeout = get_comfyui_timeout()
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

    try:
        result = subprocess.run(
            deadline_command,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        result_output = result.stdout.strip()
        print(f"Deadline submission result: {result_output}")

        if result.returncode != 0:
            print(f"Deadline submission error: {result.stderr}")
            return None

        job_id = None
        for line in result_output.split('\n'):
            if 'JobID=' in line:
                job_id = line.split('=')[-1].strip()
                break

        if job_id:
            print(f"ComfyUI Deadline Job ID (server mode): {job_id}")

        return job_id

    except Exception as e:
        print(f"Error submitting to Deadline: {e}")
        return None


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

    comfyui_path = get_comfyui_path()
    comfyui_mode = get_comfyui_mode()
    comfyui_python = get_comfyui_python_path()

    if comfyui_mode == "embedded":
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
    elif comfyui_mode == "portable":
        python_exe = os.path.join(comfyui_path, "venv", "Scripts", "python.exe")
    else:
        python_exe = comfyui_python if comfyui_python else "python"

    script_dir = os.path.dirname(__file__)
    runner_script_source = os.path.join(script_dir, "comfyui_runner.py")
    utils_script_source = os.path.join(script_dir, "comfyui_utils.py")
    runner_script = os.path.join(output_dir, "comfyui_runner.py")
    utils_script = os.path.join(output_dir, "comfyui_utils.py")

    # Copy scripts to output directory for farm access
    for src, dst in [(runner_script_source, runner_script), (utils_script_source, utils_script)]:
        if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
            shutil.copy2(src, dst)
            print(f"Copied {os.path.basename(src)} to: {dst}")

    input_dir = output_dir
    port = 8188 if use_server_mode else random.randint(8200, 8299)

    comfyui_path_clean = comfyui_path.rstrip('/\\')
    timeout = get_comfyui_timeout()
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
        from settings_manager import get_comfyui_server_not_found_behavior, get_comfyui_server_wait_timeout
        server_behavior = get_comfyui_server_not_found_behavior()
        runner_args += f' --server-not-found {server_behavior}'
        if server_behavior == 'wait':
            server_wait_timeout = get_comfyui_server_wait_timeout()
            runner_args += f' --server-wait-timeout {server_wait_timeout}'

    if full_restart:
        runner_args += ' --full-restart'

    if get_comfyui_fast_mode():
        runner_args += ' --fast'
    if get_comfyui_fp16_accumulation():
        runner_args += ' --fp16-accumulation'

    comfyui_default_output = os.path.join(comfyui_path, "ComfyUI", "output")
    runner_args += f' --comfyui-output-dir "{comfyui_default_output}"'

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

    try:
        result = subprocess.run(
            deadline_command,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        result_output = result.stdout.strip()
        print(f"Deadline submission result: {result_output}")

        if result.returncode != 0:
            print(f"Deadline submission error: {result.stderr}")
            return None

        job_id = None
        for line in result_output.split('\n'):
            if 'JobID=' in line:
                job_id = line.split('=')[-1].strip()
                break

        if job_id:
            print(f"ComfyUI Deadline Job ID: {job_id}")

        return job_id

    except Exception as e:
        print(f"Error submitting to Deadline: {e}")
        return None


def _collect_batch_images(editable_values: Optional[Dict[int, Dict[str, Any]]]) -> Tuple[List[str], int]:
    """Collect all batch images from editable values."""
    if not editable_values:
        return [], -1

    for node_id, data in editable_values.items():
        node_info = data.get('node')
        value = data.get('value')
        if node_info and node_info.widget_type == 'image':
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
    Submit ComfyUI job to Deadline. Supports batch image processing.

    If multiple images are selected, submits a separate job for each image.
    Each job runs generation_count generations with different seeds.

    Args:
        workflow_path: Path to original workflow JSON file
        input_image: Path to input image (legacy, can be None)
        prompt: Edit prompt text (legacy, can be None)
        output_dir: User's output directory
        generation_count: Number of generations per image
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
    batch_images, image_node_id = _collect_batch_images(editable_values)

    if not batch_images and input_image and os.path.exists(input_image):
        batch_images = [input_image]

    if not batch_images:
        print("No input images found - submitting workflow as-is")
        batch_images = [None]

    total_images = len(batch_images)
    print(f"Batch submission: {total_images} image(s) x {generation_count} generations each")

    if progress_callback:
        progress_callback(10, f"Processing {total_images} image(s)...")

    working_base_dir = network_output_dir if network_output_dir else output_dir

    os.makedirs(output_dir, exist_ok=True)
    if network_output_dir:
        os.makedirs(network_output_dir, exist_ok=True)

    all_job_ids = []
    errors = []

    for img_idx, current_image in enumerate(batch_images):
        base_progress = 10 + int((img_idx / total_images) * 80)

        if current_image:
            image_basename = os.path.basename(current_image)
            image_name = os.path.splitext(image_basename)[0]
            current_job_name = f"{job_name}_{image_name}" if total_images > 1 else job_name
            current_working_dir = os.path.join(working_base_dir, image_name) if total_images > 1 else working_base_dir
        else:
            image_basename = None
            current_job_name = job_name
            current_working_dir = working_base_dir

        os.makedirs(current_working_dir, exist_ok=True)

        if progress_callback:
            msg = f"Submitting {img_idx + 1}/{total_images}"
            if current_image:
                msg += f": {image_basename}"
            progress_callback(base_progress, msg)

        current_editable_values = None
        if editable_values:
            current_editable_values = copy.deepcopy(editable_values)
            if image_node_id >= 0 and image_node_id in current_editable_values:
                current_editable_values[image_node_id]['value'] = current_image

        modified, found_editable = modify_workflow(
            workflow,
            current_image,
            prompt,
            current_job_name,
            seed=12345,
            editable_values=current_editable_values,
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
        if prompt_text or current_image or current_editable_values:
            add_image_metadata(
                output_dir=current_working_dir,
                output_prefix=current_job_name,
                prompt=prompt_text,
                workflow_name=os.path.basename(workflow_path),
                input_image=current_image,
                generation_count=generation_count,
                base_seed=base_seed,
                workflow_preset=workflow_preset,
                editable_values=current_editable_values,
            )

        if current_image:
            image_dest = os.path.join(current_working_dir, image_basename)
            if not os.path.exists(image_dest) or os.path.getmtime(current_image) > os.path.getmtime(image_dest):
                shutil.copy2(current_image, image_dest)

        if current_editable_values:
            for _, data in current_editable_values.items():
                node_info = data.get('node')
                value = data.get('value')
                if node_info and node_info.widget_type == '3d_model' and value:
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
            errors.append(f"Failed to submit job for image: {image_basename or 'workflow'}")

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

        for line in output.split('\n'):
            line = line.strip()
            if line.startswith("Status="):
                status = line.split('=', 1)[1]
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

        if status in ("Complete", "Completed") and failed_tasks > 0:
            status = "Failed"

        if status == "Active":
            if rendering_tasks > 0:
                status = "Rendering"
            elif queued_tasks > 0 and completed_tasks == 0:
                status = "Queued"

        return {
            "status": status,
            "progress": progress,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "queued_tasks": queued_tasks,
            "rendering_tasks": rendering_tasks,
            "error_message": error_message
        }

    except Exception as e:
        return {"status": "Unknown", "progress": 0, "error_message": str(e)}


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
