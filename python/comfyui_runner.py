"""
ComfyUI Runner Script.

Submits workflows to ComfyUI via API and waits for completion.
This script is designed to be run on Deadline farm workers.

Two modes of operation:
1. Normal mode: Starts ComfyUI, runs workflow, shuts down when done
2. Persistent mode (--persistent): Connects to user-started ComfyUI server
   - User must manually start ComfyUI on the farm node before submitting jobs
   - Models stay loaded in GPU memory between job submissions
   - Much faster since no model loading overhead per job
"""

import sys
import os
import json
import time
import copy
import urllib.request
import urllib.error
import subprocess
import argparse
import signal
import threading


def check_server_running(port: int, timeout: int = 5) -> bool:
    """Check if ComfyUI server is already running on the port."""
    url = f"http://127.0.0.1:{port}/system_stats"
    try:
        req = urllib.request.urlopen(url, timeout=timeout)
        return req.status == 200
    except Exception:
        return False


def upload_image_to_server(image_path: str, port: int) -> str:
    """
    Upload an image to ComfyUI server's input directory.

    Args:
        image_path: Local path to the image file
        port: ComfyUI server port

    Returns:
        Filename as stored on server, or None on failure
    """
    if not os.path.exists(image_path):
        print(f"Image file not found: {image_path}")
        return None

    import mimetypes

    filename = os.path.basename(image_path)
    url = f"http://127.0.0.1:{port}/upload/image"

    # Read the image file
    with open(image_path, 'rb') as f:
        file_data = f.read()

    # Build multipart form data
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'

    # Get mime type
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f'Content-Type: {mime_type}\r\n\r\n'
    ).encode('utf-8')
    body += file_data
    body += f'\r\n--{boundary}--\r\n'.encode('utf-8')

    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body))
    }

    req = urllib.request.Request(url, data=body, headers=headers, method='POST')

    try:
        response = urllib.request.urlopen(req, timeout=30)
        result = json.loads(response.read().decode('utf-8'))
        server_filename = result.get('name', filename)
        print(f"Uploaded image to server: {filename} -> {server_filename}")
        return server_filename
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"Failed to upload image: HTTP {e.code} - {error_body}")
        return None
    except Exception as e:
        print(f"Failed to upload image: {e}")
        return None


def get_workflow_images(workflow: dict) -> list:
    """
    Extract all image filenames from LoadImage nodes in a workflow.

    Returns:
        List of image filenames referenced in the workflow
    """
    images = []
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        if node_data.get('class_type') == 'LoadImage':
            inputs = node_data.get('inputs', {})
            image = inputs.get('image')
            if image:
                images.append(image)
    return images


def modify_workflow_seed(workflow: dict, seed: int, output_prefix: str) -> dict:
    """
    Modify workflow to use a specific seed and output prefix.

    Args:
        workflow: Workflow dict in API format
        seed: Seed value for random nodes
        output_prefix: Prefix for output filenames

    Returns:
        Modified workflow dict
    """
    modified = copy.deepcopy(workflow)

    for node_id, node_data in modified.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})

        # KSampler nodes - set seed
        if class_type == 'KSampler':
            inputs['seed'] = seed
            print(f"Set KSampler node {node_id} seed to: {seed}")

        # RandomNoise nodes - set seed
        elif class_type == 'RandomNoise':
            inputs['noise_seed'] = seed
            print(f"Set RandomNoise node {node_id} seed to: {seed}")

        # SaveImage nodes - set output prefix
        elif class_type == 'SaveImage':
            inputs['filename_prefix'] = output_prefix
            print(f"Set SaveImage node {node_id} prefix to: {output_prefix}")

        # HYMotionExportFBX nodes - clear output_dir so files go to main output, set prefix
        elif class_type == 'HYMotionExportFBX':
            inputs['output_dir'] = ''  # Empty = use ComfyUI's output directory directly
            inputs['filename_prefix'] = output_prefix
            print(f"Set HYMotionExportFBX node {node_id}: output_dir='', prefix={output_prefix}")

        # HYMotionGenerate nodes - set seed
        elif class_type == 'HYMotionGenerate':
            inputs['seed'] = seed
            print(f"Set HYMotionGenerate node {node_id} seed to: {seed}")

    return modified


def wait_for_server(port: int, timeout: int = 120) -> bool:
    """Wait for ComfyUI server to be ready."""
    url = f"http://127.0.0.1:{port}/system_stats"
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            req = urllib.request.urlopen(url, timeout=5)
            if req.status == 200:
                print(f"ComfyUI server ready on port {port}")
                return True
        except (urllib.error.URLError, urllib.error.HTTPError):
            pass
        time.sleep(1)

    print(f"Timeout waiting for ComfyUI server on port {port}")
    return False


def submit_workflow(workflow: dict, port: int) -> str:
    """Submit workflow to ComfyUI API and return prompt_id.

    Args:
        workflow: Workflow dict (already loaded and optionally modified)
        port: ComfyUI server port

    Returns:
        prompt_id string or None on failure
    """
    # Wrap workflow in prompt format
    prompt_data = {"prompt": workflow}

    url = f"http://127.0.0.1:{port}/prompt"
    data = json.dumps(prompt_data).encode('utf-8')

    print(f"Submitting workflow with {len(workflow)} nodes to {url}")

    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        response = urllib.request.urlopen(req, timeout=30)
        result = json.loads(response.read().decode('utf-8'))
        prompt_id = result.get('prompt_id')
        print(f"Workflow submitted, prompt_id: {prompt_id}")
        return prompt_id
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"HTTP Error {e.code}: {e.reason}")
        print(f"Error details: {error_body}")
        return None
    except Exception as e:
        print(f"Error submitting workflow: {e}")
        return None


def download_image_from_server(filename: str, subfolder: str, image_type: str, port: int, output_dir: str) -> str:
    """
    Download an image from ComfyUI server to local output directory.

    Args:
        filename: Image filename on server
        subfolder: Subfolder on server (usually empty for output)
        image_type: Type of image ('output', 'input', 'temp')
        port: ComfyUI server port
        output_dir: Local directory to save the image

    Returns:
        Local path where image was saved, or None on failure
    """
    import urllib.parse

    # Build the view URL with query parameters
    params = urllib.parse.urlencode({
        'filename': filename,
        'subfolder': subfolder,
        'type': image_type
    })
    url = f"http://127.0.0.1:{port}/view?{params}"

    try:
        response = urllib.request.urlopen(url, timeout=30)
        image_data = response.read()

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Save to local file
        local_path = os.path.join(output_dir, filename)
        with open(local_path, 'wb') as f:
            f.write(image_data)

        print(f"Downloaded: {filename} -> {local_path}")
        return local_path

    except urllib.error.HTTPError as e:
        print(f"Failed to download {filename}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"Failed to download {filename}: {e}")
        return None


def wait_for_completion(prompt_id: str, port: int, timeout: int = 600, output_dir: str = None) -> bool:
    """Wait for workflow execution to complete.

    Args:
        prompt_id: The prompt ID to wait for
        port: ComfyUI server port
        timeout: Timeout in seconds
        output_dir: If provided, download output images to this directory

    Returns:
        True if workflow completed successfully
    """
    history_url = f"http://127.0.0.1:{port}/history/{prompt_id}"
    queue_url = f"http://127.0.0.1:{port}/queue"
    start_time = time.time()
    last_status = ""
    poll_count = 0
    consecutive_errors = 0

    while time.time() - start_time < timeout:
        poll_count += 1
        elapsed = int(time.time() - start_time)

        try:
            # Check queue status first - faster way to know if still running
            queue_response = urllib.request.urlopen(queue_url, timeout=5)
            queue_data = json.loads(queue_response.read().decode('utf-8'))

            running = queue_data.get('queue_running', [])
            pending = queue_data.get('queue_pending', [])

            # Check if our prompt is still in queue
            our_prompt_running = any(item[1] == prompt_id for item in running)
            our_prompt_pending = any(item[1] == prompt_id for item in pending)

            if our_prompt_running:
                # Print status every 10 seconds to show it's still alive
                if elapsed % 10 == 0 or last_status == "":
                    print(f"Executing... ({elapsed}s)", flush=True)
                last_status = f"running_{elapsed}"
            elif our_prompt_pending:
                status = f"Queued... ({elapsed}s)"
                if status != last_status:
                    print(status, flush=True)
                    last_status = status
            else:
                # Not in queue - check history for completion
                response = urllib.request.urlopen(history_url, timeout=5)
                history = json.loads(response.read().decode('utf-8'))

                if prompt_id in history:
                    prompt_data = history[prompt_id]
                    status_data = prompt_data.get('status', {})
                    outputs = prompt_data.get('outputs', {})

                    # Check for completion via status
                    if status_data.get('status_str') == 'success' or outputs:
                        print(f"Workflow completed successfully in {elapsed}s", flush=True)
                        # Print output info and download images if output_dir provided
                        for node_id, output in outputs.items():
                            if 'images' in output:
                                for img in output['images']:
                                    filename = img.get('filename', 'unknown')
                                    subfolder = img.get('subfolder', '')
                                    img_type = img.get('type', 'output')
                                    print(f"Output image: {filename}", flush=True)

                                    # Download image to our output directory
                                    if output_dir:
                                        download_image_from_server(
                                            filename, subfolder, img_type,
                                            port, output_dir
                                        )
                        return True

                    # Check for error
                    if status_data.get('status_str') == 'error':
                        print(f"Workflow failed with error", flush=True)
                        # Try to get more error details
                        messages = status_data.get('messages', [])
                        for msg in messages:
                            print(f"Error detail: {msg}", flush=True)
                        return False

            # Reset error counter on successful connection
            consecutive_errors = 0

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            consecutive_errors += 1

            if consecutive_errors >= 10:
                print(f"ERROR: Lost connection to ComfyUI after {consecutive_errors} consecutive failures")
                print(f"Last error: {e}")
                return False

            if poll_count % 10 == 0:  # Only log every 10th error
                print(f"Connection check... ({elapsed}s) - {consecutive_errors} consecutive errors", flush=True)

        # Poll faster (0.5s) for quicker completion detection
        time.sleep(0.5)

    print(f"Timeout waiting for workflow completion after {timeout}s", flush=True)
    return False


def start_comfyui_server(comfyui_path: str, input_dir: str, output_dir: str, port: int,
                         mode: str = "embedded", python_path: str = None,
                         fast_mode: bool = False, fp16_accumulation: bool = False) -> subprocess.Popen:
    """Start ComfyUI server process.

    Args:
        comfyui_path: Path to ComfyUI installation
        input_dir: Input directory for images
        output_dir: Output directory for generated images
        port: Port for ComfyUI server
        mode: 'embedded' for portable install, 'portable' for venv-based install
              (e.g., comfy-cli), 'standalone' for system install
        python_path: Path to Python executable (required for standalone mode)
        fast_mode: Enable --fast flag for faster execution (may reduce quality)
        fp16_accumulation: Enable --fp16-accumulation for faster FP16 math
    """
    if mode == "embedded":
        # Embedded/portable mode: python_embeded folder alongside ComfyUI
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
        main_py = os.path.join(comfyui_path, "ComfyUI", "main.py")
    elif mode == "portable":
        # Portable mode: venv-based install from various installers
        # Check for different venv and main.py locations
        venv_locations = [
            os.path.join(comfyui_path, "venv", "Scripts", "python.exe"),  # comfy-cli
            os.path.join(comfyui_path, ".venv", "Scripts", "python.exe"),  # some installers
        ]
        main_py_locations = [
            os.path.join(comfyui_path, "ComfyUI", "main.py"),  # comfy-cli structure
        ]

        python_exe = None
        for venv_path in venv_locations:
            if os.path.exists(venv_path):
                python_exe = venv_path
                break
        if not python_exe:
            python_exe = venv_locations[0]

        main_py = None
        for main_path in main_py_locations:
            if os.path.exists(main_path):
                main_py = main_path
                break
        if not main_py:
            main_py = main_py_locations[0]
    else:
        # Standalone mode: use provided Python path, ComfyUI path points directly to main.py location
        if not python_path:
            print("ERROR: Python path required for standalone mode")
            return None
        python_exe = python_path
        main_py = os.path.join(comfyui_path, "main.py")

    cmd = [
        python_exe,
        main_py,
        '--input-directory', input_dir,
        '--output-directory', output_dir,
        '--port', str(port),
        '--disable-auto-launch'
    ]

    # Add optional performance flags
    if fast_mode:
        cmd.append('--fast')
        print("Fast mode enabled (--fast)")
    # Note: --fp16-accumulation is not a valid ComfyUI flag
    # The fp16_accumulation parameter is kept for API compatibility but does nothing

    # Set working directory to where main.py is located
    # This ensures custom_nodes are found correctly
    working_dir = os.path.dirname(main_py)

    print(f"Starting ComfyUI ({mode} mode): {' '.join(cmd)}")
    print(f"Working directory: {working_dir}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=working_dir,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )

    return process


def stream_output(process: subprocess.Popen, process_died: threading.Event):
    """Stream ComfyUI stdout to our stdout for visibility."""
    try:
        for line in process.stdout:
            line = line.rstrip()
            if line:
                print(f"[ComfyUI] {line}", flush=True)
                if "Error" in line or "Exception" in line or "CUDA out of memory" in line:
                    print(f"WARNING: ComfyUI error detected: {line}", flush=True)
                if "Prompt executed in" in line:
                    print(f"[ComfyUI] Workflow execution complete: {line}", flush=True)
    except Exception as e:
        print(f"Output stream error: {e}", flush=True)
    finally:
        ret = process.poll()
        if ret is not None:
            print(f"ComfyUI process exited with code {ret}", flush=True)
            if ret != 0:
                process_died.set()


def main():
    parser = argparse.ArgumentParser(description='Run ComfyUI workflow')
    parser.add_argument('--comfyui-path', required=True, help='Path to ComfyUI installation')
    parser.add_argument('--workflow', required=True, help='Path to workflow JSON file')
    parser.add_argument('--input-directory', required=True, help='Input image directory')
    parser.add_argument('--output-directory', required=True, help='Output directory')
    parser.add_argument('--port', type=int, default=8188, help='Port for ComfyUI server')
    parser.add_argument('--timeout', type=int, default=600, help='Execution timeout in seconds per generation')
    parser.add_argument('--frame', type=int, default=1, help='Frame/generation number (1-based) - ignored in batch mode')
    parser.add_argument('--seeds-file', help='Path to JSON file with seeds for each frame')
    parser.add_argument('--output-prefix', default='comfyui_output', help='Base output filename prefix')
    parser.add_argument('--batch', action='store_true', help='Process all generations in a single session')
    parser.add_argument('--persistent', action='store_true', help='Keep server running between jobs (check workflow changes)')
    parser.add_argument('--mode', choices=['embedded', 'portable', 'standalone'], default='embedded',
                       help='ComfyUI installation mode: embedded (python_embeded), portable (venv), or standalone')
    parser.add_argument('--python-path', help='Path to Python executable (required for standalone mode)')
    parser.add_argument('--fast', action='store_true', help='Enable --fast flag for faster execution (may reduce quality)')
    parser.add_argument('--fp16-accumulation', action='store_true', help='Enable --fp16-accumulation for faster FP16 math')

    args = parser.parse_args()

    # Determine paths based on mode
    if args.mode == "embedded":
        python_exe = os.path.join(args.comfyui_path, "python_embeded", "python.exe")
        main_py = os.path.join(args.comfyui_path, "ComfyUI", "main.py")
    elif args.mode == "portable":
        # Portable mode: venv-based install from various installers
        venv_locations = [
            os.path.join(args.comfyui_path, "venv", "Scripts", "python.exe"),  # comfy-cli
            os.path.join(args.comfyui_path, ".venv", "Scripts", "python.exe"),  # some installers
        ]
        main_py_locations = [
            os.path.join(args.comfyui_path, "ComfyUI", "main.py"),  # comfy-cli structure
        ]

        python_exe = None
        for venv_path in venv_locations:
            if os.path.exists(venv_path):
                python_exe = venv_path
                break
        if not python_exe:
            python_exe = venv_locations[0]

        main_py = None
        for main_path in main_py_locations:
            if os.path.exists(main_path):
                main_py = main_path
                break
        if not main_py:
            main_py = main_py_locations[0]
    else:
        # Standalone mode
        if not args.python_path:
            print("ERROR: --python-path required for standalone mode")
            sys.exit(1)
        python_exe = args.python_path
        main_py = os.path.join(args.comfyui_path, "main.py")

    # Verify paths exist
    if not os.path.exists(python_exe):
        print(f"ERROR: Python executable not found: {python_exe}")
        sys.exit(1)

    if not os.path.exists(main_py):
        print(f"ERROR: ComfyUI main.py not found: {main_py}")
        sys.exit(1)

    if not os.path.exists(args.workflow):
        print(f"ERROR: Workflow file not found: {args.workflow}")
        sys.exit(1)

    # Load base workflow
    print(f"Loading workflow from: {args.workflow}")
    with open(args.workflow, 'r', encoding='utf-8') as f:
        base_workflow = json.load(f)

    # Load seeds data if provided
    seeds_data = None
    if args.seeds_file:
        if not os.path.exists(args.seeds_file):
            print(f"ERROR: Seeds file not found: {args.seeds_file}")
            sys.exit(1)

        with open(args.seeds_file, 'r', encoding='utf-8') as f:
            seeds_data = json.load(f)

    # Determine frames to process
    if args.batch and seeds_data:
        frames_to_process = list(range(1, len(seeds_data.get('seeds', [])) + 1))
        print(f"Batch mode: Processing {len(frames_to_process)} generations in single session")
    else:
        frames_to_process = [args.frame]

    # Prepare workflows for each frame
    workflows_to_run = []
    for frame_num in frames_to_process:
        workflow = copy.deepcopy(base_workflow)

        if seeds_data:
            frame_index = frame_num - 1
            if frame_index < 0 or frame_index >= len(seeds_data.get('seeds', [])):
                print(f"ERROR: Frame {frame_num} out of range (1-{len(seeds_data.get('seeds', []))})")
                sys.exit(1)

            seed = seeds_data['seeds'][frame_index]
            output_prefix = f"{args.output_prefix}_gen{frame_num:02d}"

            print(f"Frame {frame_num}: Using seed {seed}, output prefix: {output_prefix}")
            workflow = modify_workflow_seed(workflow, seed, output_prefix)

        workflows_to_run.append((frame_num, workflow))

    # Persistent mode: connect to user-started server (no auto-start)
    # Non-persistent mode: start our own server
    process = None
    process_died = threading.Event()
    server_started_by_us = False

    if args.persistent:
        # Persistent mode - expect server to be already running (user started it)
        print(f"Persistent mode: connecting to server on port {args.port}...")
        if not check_server_running(args.port):
            print(f"ERROR: No ComfyUI server found on port {args.port}")
            print("Please start ComfyUI manually on the farm node before submitting jobs.")
            print(f"Expected server URL: http://127.0.0.1:{args.port}")
            sys.exit(1)
        print(f"Connected to existing ComfyUI server on port {args.port}")
        print("Models should already be loaded - submissions will be fast")

        # In persistent mode, we need to upload input images to the server
        # since the server's input directory may be different from ours
        print("\nUploading input images to server...")
        images_to_upload = get_workflow_images(base_workflow)
        for image_name in images_to_upload:
            # Look for the image in our input directory
            image_path = os.path.join(args.input_directory, image_name)
            if os.path.exists(image_path):
                server_name = upload_image_to_server(image_path, args.port)
                if not server_name:
                    print(f"ERROR: Failed to upload image {image_name}")
                    sys.exit(1)
            else:
                print(f"WARNING: Image not found locally: {image_path}")
                print("  Will assume it already exists on the server")
    else:
        # Non-persistent mode: start fresh server for this job
        process = start_comfyui_server(
            args.comfyui_path,
            args.input_directory,
            args.output_directory,
            args.port,
            mode=args.mode,
            python_path=args.python_path,
            fast_mode=args.fast,
            fp16_accumulation=getattr(args, 'fp16_accumulation', False)
        )
        if process is None:
            print("ERROR: Failed to start ComfyUI server")
            sys.exit(1)
        server_started_by_us = True

        # Start output streaming thread
        output_thread = threading.Thread(
            target=stream_output,
            args=(process, process_died),
            daemon=True
        )
        output_thread.start()

        # Wait for server to be ready
        if not wait_for_server(args.port, timeout=120):
            print("Failed to start ComfyUI server")
            process.terminate()
            sys.exit(1)

    # Handle cleanup on exit
    def cleanup(signum=None, frame=None):
        # Only kill server if we started it (non-persistent mode)
        if server_started_by_us and process:
            print("Cleaning up - shutting down server...")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        elif args.persistent:
            print("Persistent mode - server stays running for next job")
        sys.exit(0 if signum is None else 1)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        # Process all workflows
        total_frames = len(workflows_to_run)
        successful = 0
        failed = 0

        for i, (frame_num, workflow) in enumerate(workflows_to_run, 1):
            # Check if ComfyUI process is still alive (only if we started it)
            if process and process.poll() is not None:
                print(f"ERROR: ComfyUI process died unexpectedly (exit code: {process.returncode})")
                print("Aborting remaining generations")
                failed += (total_frames - i + 1)
                break

            if process_died.is_set():
                print("ERROR: ComfyUI process crashed")
                print("Aborting remaining generations")
                failed += (total_frames - i + 1)
                break

            print(f"\n{'='*60}", flush=True)
            print(f"Processing generation {i}/{total_frames} (frame {frame_num})", flush=True)
            print(f"{'='*60}", flush=True)

            # Submit workflow
            prompt_id = submit_workflow(workflow, args.port)
            if not prompt_id:
                print(f"Failed to submit workflow for frame {frame_num}")
                if process and process.poll() is not None:
                    print(f"ComfyUI process exited (code: {process.returncode})")
                    failed += (total_frames - i + 1)
                    break
                failed += 1
                continue

            # Wait for completion
            # In persistent mode, download images to our output directory
            # since the server may have a different output directory configured
            download_dir = args.output_directory if args.persistent else None
            success = wait_for_completion(prompt_id, args.port, timeout=args.timeout, output_dir=download_dir)

            # Check process health after completion attempt
            if process and process.poll() is not None:
                print(f"ERROR: ComfyUI crashed during generation (exit code: {process.returncode})")
                failed += (total_frames - i + 1)
                break

            if success:
                print(f"Frame {frame_num} completed successfully", flush=True)
                successful += 1
            else:
                print(f"Frame {frame_num} failed or timed out", flush=True)
                failed += 1

        # Summary
        print(f"\n{'='*60}", flush=True)
        print(f"BATCH COMPLETE: {successful}/{total_frames} successful, {failed} failed", flush=True)
        print(f"{'='*60}", flush=True)

        cleanup()
        sys.exit(0 if failed == 0 else 1)

    except Exception as e:
        print(f"Error: {e}")
        cleanup()
        sys.exit(1)


if __name__ == '__main__':
    main()
