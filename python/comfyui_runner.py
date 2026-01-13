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

Logs are written to ~/.luma_tools/logs/comfyui_runner_<timestamp>.log
"""

import sys
import os
import json
import time
import copy
import uuid
import urllib.request
import urllib.error
import subprocess
import argparse
import signal
import threading
from datetime import datetime

# Try to import websocket for real-time progress
WEBSOCKET_AVAILABLE = False
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    # Try to install websocket-client automatically
    print("websocket-client not found, attempting to install...", flush=True)
    try:
        import subprocess as _sp
        _result = _sp.run(
            [sys.executable, '-m', 'pip', 'install', 'websocket-client', '--quiet'],
            capture_output=True,
            text=True,
            timeout=60
        )
        if _result.returncode == 0:
            import websocket
            WEBSOCKET_AVAILABLE = True
            print("Successfully installed websocket-client", flush=True)
        else:
            print(f"Failed to install websocket-client: {_result.stderr}", flush=True)
    except Exception as _e:
        print(f"Could not auto-install websocket-client: {_e}", flush=True)


# ============================================================================
# LOGGING SETUP - Tee stdout/stderr to log file
# ============================================================================

class TeeWriter:
    """
    Writes to both the original stream and a log file.
    This captures all print() output without modifying existing code.
    """

    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file
        self.timestamp_next = True

    def write(self, message):
        # Write to original stream (stdout/stderr for Deadline)
        self.original_stream.write(message)

        # Write to log file with timestamp for non-empty lines
        if message.strip():
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.log_file.write(f"{timestamp} | {message}")
            if not message.endswith('\n'):
                self.log_file.write('\n')
        elif message == '\n':
            self.log_file.write('\n')

        self.log_file.flush()

    def flush(self):
        self.original_stream.flush()
        self.log_file.flush()


def setup_logging(job_name: str = None) -> str:
    """
    Set up file logging by redirecting stdout/stderr to also write to a log file.

    Args:
        job_name: Optional job name to include in log filename

    Returns:
        Path to the log file
    """
    # Create logs directory in user's .luma_tools folder
    log_dir = os.path.join(os.path.expanduser("~"), ".luma_tools", "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Create timestamped log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if job_name:
        # Sanitize job name for filename
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_name)[:50]
        log_filename = f"comfyui_runner_{safe_name}_{timestamp}.log"
    else:
        log_filename = f"comfyui_runner_{timestamp}.log"

    log_path = os.path.join(log_dir, log_filename)

    # Open log file and set up tee writers
    log_file = open(log_path, 'w', encoding='utf-8')

    # Write header
    log_file.write(f"{'='*60}\n")
    log_file.write(f"ComfyUI Runner Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_file.write(f"{'='*60}\n\n")
    log_file.flush()

    # Redirect stdout and stderr to tee writers
    sys.stdout = TeeWriter(sys.__stdout__, log_file)
    sys.stderr = TeeWriter(sys.__stderr__, log_file)

    print(f"Log file: {log_path}")

    return log_path


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


def signal_server_restart(port: int, health_port: int = None) -> bool:
    """
    Signal the persistent ComfyUI server to perform a full restart.

    This sends a POST request to the server's /restart endpoint on the health port.
    The server will terminate ComfyUI and restart it with the same configuration.

    Args:
        port: ComfyUI server port
        health_port: Health check server port (default: port + 1000)

    Returns:
        True if restart was initiated, False on error
    """
    if health_port is None:
        health_port = port + 1000

    url = f"http://127.0.0.1:{health_port}/restart"
    print(f"\n{'='*60}")
    print("SIGNALING SERVER RESTART")
    print(f"Sending restart request to {url}")
    print(f"{'='*60}")

    try:
        req = urllib.request.Request(url, method='POST')
        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode('utf-8'))
        print(f"Restart response: {result.get('message', 'OK')}")
        return True
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"Error signaling restart: {e}")
        return False


def wait_for_server_restart(port: int, timeout: int = 300) -> bool:
    """
    Wait for server to complete restart and become ready again.

    First waits for server to go down, then waits for it to come back up.

    Args:
        port: ComfyUI server port
        timeout: Maximum time to wait in seconds

    Returns:
        True if server is ready again, False on timeout
    """
    url = f"http://127.0.0.1:{port}/system_stats"
    start_time = time.time()

    # First, wait for server to go down (or stay down if restart is fast)
    print("Waiting for server to restart...")
    down_detected = False
    while time.time() - start_time < 30:  # Max 30s to detect restart
        try:
            urllib.request.urlopen(url, timeout=2)
            time.sleep(0.5)
        except:
            down_detected = True
            break

    if not down_detected:
        print("Warning: Server may not have restarted (still responding)")

    # Now wait for it to come back up
    print("Waiting for server to become ready...")
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.urlopen(url, timeout=5)
            if req.status == 200:
                elapsed = int(time.time() - start_time)
                print(f"Server restart complete after {elapsed}s")
                return True
        except:
            pass
        time.sleep(2)

    print(f"Timeout waiting for server restart after {timeout}s")
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


def move_output_files(comfyui_output_dir: str, target_dir: str, filename_prefix: str,
                      extensions: tuple = (
                          # 3D model formats
                          '.glb', '.gltf', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz', '.dae',
                          # Video formats
                          '.mp4', '.mov', '.avi', '.webm',
                          # Audio formats
                          '.wav', '.mp3', '.flac', '.ogg',
                      ),
                      recent_minutes: int = 10) -> list:
    """
    Move output files from ComfyUI's default output directory to our target directory.

    Some ComfyUI nodes save directly to the default output folder or subdirectories
    without an option to specify a custom path. This function finds and moves those
    files after workflow completion.

    Files are renamed to include the job prefix for better identification.

    Args:
        comfyui_output_dir: ComfyUI's default output directory
        target_dir: Our target directory to move files to
        filename_prefix: Prefix for renamed files (e.g., 'sh0010_luma_tools')
        extensions: File extensions to look for (default: 3D models, videos, audio)
        recent_minutes: Only move files modified within this many minutes (default: 10)

    Returns:
        List of moved file paths in target directory
    """
    import shutil
    import glob

    moved_files = []

    if not comfyui_output_dir or not os.path.isdir(comfyui_output_dir):
        print(f"[move_output_files] Output dir doesn't exist: {comfyui_output_dir}")
        return moved_files

    if not target_dir:
        print(f"[move_output_files] No target dir specified")
        return moved_files

    os.makedirs(target_dir, exist_ok=True)

    # Calculate cutoff time for "recent" files
    cutoff_time = time.time() - (recent_minutes * 60)

    print(f"[move_output_files] Searching for {extensions} in {comfyui_output_dir}")
    print(f"[move_output_files] Target prefix: {filename_prefix}")
    print(f"[move_output_files] Looking for files modified in last {recent_minutes} minutes")

    # Find ALL files with matching extensions (not just by prefix)
    # This handles cases where nodes use their own prefixes (like "refined_" or "trellis2_")
    all_matches = []
    for ext in extensions:
        # Top-level search first
        top_pattern = os.path.join(comfyui_output_dir, f"*{ext}")
        top_matches = glob.glob(top_pattern)
        all_matches.extend(top_matches)
        print(f"[move_output_files] Top-level {ext}: found {len(top_matches)} files")

        # Recursive search in subdirectories
        recursive_pattern = os.path.join(comfyui_output_dir, "**", f"*{ext}")
        recursive_matches = glob.glob(recursive_pattern, recursive=True)
        all_matches.extend(recursive_matches)
        print(f"[move_output_files] Recursive {ext}: found {len(recursive_matches)} files")

    # Remove duplicates and filter to recent files only
    all_matches = list(set(all_matches))
    recent_files = []
    for file_path in all_matches:
        try:
            mtime = os.path.getmtime(file_path)
            if mtime > cutoff_time:
                recent_files.append((file_path, mtime))
        except Exception as e:
            print(f"[move_output_files] Error checking {file_path}: {e}")

    # Sort by modification time (most recent first)
    recent_files.sort(key=lambda x: x[1], reverse=True)

    print(f"[move_output_files] Found {len(recent_files)} recent files out of {len(all_matches)} total")
    for file_path, mtime in recent_files:
        age = int((time.time() - mtime) / 60)
        print(f"  - {os.path.basename(file_path)} ({age} min ago)")

    # Move each recent file with a renamed prefix
    for src_path, mtime in recent_files:
        original_filename = os.path.basename(src_path)
        ext = os.path.splitext(original_filename)[1]

        # Create new filename with our prefix
        # But skip adding prefix if file already starts with it (avoid double prefix)
        if original_filename.startswith(filename_prefix):
            # File already has our prefix (from workflow node settings)
            new_filename = original_filename
            print(f"[move_output_files] File already has prefix, keeping: {original_filename}")
        else:
            # Add our prefix for identification
            # Format: {our_prefix}_{original_filename}
            new_filename = f"{filename_prefix}_{original_filename}"
        dest_path = os.path.join(target_dir, new_filename)

        # Handle duplicate filenames by adding a counter
        counter = 1
        while os.path.exists(dest_path):
            base = os.path.splitext(new_filename)[0]
            new_filename = f"{base}_{counter}{ext}"
            dest_path = os.path.join(target_dir, new_filename)
            counter += 1

        try:
            # Check if file is still being written (wait for stable size)
            initial_size = os.path.getsize(src_path)
            time.sleep(0.5)
            final_size = os.path.getsize(src_path)

            if initial_size != final_size:
                print(f"[move_output_files] File still being written, waiting: {original_filename}")
                time.sleep(2)

            shutil.move(src_path, dest_path)
            print(f"[move_output_files] Moved: {original_filename} -> {new_filename}")
            moved_files.append(dest_path)
        except Exception as e:
            print(f"[move_output_files] Failed to move {original_filename}: {e}")

    return moved_files


def check_history_for_completion(prompt_id: str, port: int) -> dict:
    """Check history endpoint to see if prompt completed.

    Returns:
        dict with 'status' ('success', 'error', 'pending') and optional 'outputs'
    """
    history_url = f"http://127.0.0.1:{port}/history/{prompt_id}"
    try:
        response = urllib.request.urlopen(history_url, timeout=5)
        history = json.loads(response.read().decode('utf-8'))

        if prompt_id in history:
            prompt_data = history[prompt_id]
            status_data = prompt_data.get('status', {})
            outputs = prompt_data.get('outputs', {})

            if status_data.get('status_str') == 'success' or outputs:
                return {'status': 'success', 'outputs': outputs}
            elif status_data.get('status_str') == 'error':
                return {'status': 'error', 'messages': status_data.get('messages', [])}

        return {'status': 'pending'}
    except Exception:
        return {'status': 'pending'}


def wait_for_completion_websocket(prompt_id: str, port: int, timeout: int = 3600, output_dir: str = None) -> bool:
    """Wait for workflow execution using WebSocket for progress + HTTP polling for completion.

    Args:
        prompt_id: The prompt ID to wait for
        port: ComfyUI server port
        timeout: Timeout in seconds
        output_dir: If provided, download output images to this directory

    Returns:
        True if workflow completed successfully
    """
    ws_url = f"ws://127.0.0.1:{port}/ws?clientId={uuid.uuid4()}"

    result = {'success': None, 'error': None, 'outputs': {}}
    start_time = time.time()
    current_node = {'id': None}
    last_progress = {'value': 0, 'max': 0}

    def on_message(ws, message):
        nonlocal result, current_node, last_progress
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'status':
                status_data = data.get('data', {}).get('status', {})
                exec_info = status_data.get('exec_info', {})
                queue_remaining = exec_info.get('queue_remaining', 0)
                if queue_remaining > 0:
                    elapsed = int(time.time() - start_time)
                    print(f"Queue: {queue_remaining} remaining ({elapsed}s)", flush=True)

            elif msg_type == 'execution_start':
                exec_data = data.get('data', {})
                recv_prompt_id = exec_data.get('prompt_id')
                if recv_prompt_id == prompt_id:
                    print(f"Execution started", flush=True)

            elif msg_type == 'executing':
                exec_data = data.get('data', {})
                recv_prompt_id = exec_data.get('prompt_id')
                node_id = exec_data.get('node')
                if recv_prompt_id == prompt_id:
                    if node_id is None:
                        elapsed = int(time.time() - start_time)
                        print(f"Execution completed in {elapsed}s", flush=True)
                        result['success'] = True
                        ws.close()
                    else:
                        current_node['id'] = node_id
                        elapsed = int(time.time() - start_time)
                        print(f"Executing node {node_id}... ({elapsed}s)", flush=True)
                        last_progress = {'value': 0, 'max': 0}

            elif msg_type == 'progress':
                prog_data = data.get('data', {})
                value = prog_data.get('value', 0)
                max_val = prog_data.get('max', 100)
                if max_val > 0:
                    pct = int(100 * value / max_val)
                    last_pct = int(100 * last_progress['value'] / max(last_progress['max'], 1))
                    if pct >= last_pct + 10 or value == max_val:
                        elapsed = int(time.time() - start_time)
                        print(f"  Progress: {pct}% ({value}/{max_val}) ({elapsed}s)", flush=True)
                        last_progress = {'value': value, 'max': max_val}

            elif msg_type == 'executed':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    node_id = exec_data.get('node')
                    output = exec_data.get('output', {})
                    result['outputs'][node_id] = output
                    if 'images' in output:
                        for img in output['images']:
                            print(f"  Output: {img.get('filename', 'unknown')}", flush=True)
                    if 'gltf' in output or 'glb' in output:
                        for item in output.get('gltf', []) + output.get('glb', []):
                            print(f"  Output 3D: {item.get('filename', 'unknown')}", flush=True)

            elif msg_type == 'execution_cached':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    nodes = exec_data.get('nodes', [])
                    if nodes:
                        print(f"Cached: {len(nodes)} node(s)", flush=True)

            elif msg_type == 'execution_error':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    error = exec_data.get('exception_message', 'Unknown error')
                    node_id = exec_data.get('node_id')
                    node_type = exec_data.get('node_type')
                    print(f"ERROR in node {node_id} ({node_type}): {error}", flush=True)
                    result['error'] = error
                    result['success'] = False
                    ws.close()

        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"WebSocket message error: {e}", flush=True)

    def on_error(ws, error):
        print(f"WebSocket error: {error}", flush=True)

    def on_close(ws, close_status_code, close_msg):
        pass  # Don't treat close as error - we also poll HTTP

    def on_open(ws):
        print(f"Connected to ComfyUI WebSocket", flush=True)

    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws_thread = threading.Thread(target=lambda: ws.run_forever(ping_interval=30, ping_timeout=10))
    ws_thread.daemon = True
    ws_thread.start()

    # Hybrid approach: WebSocket for progress, HTTP polling for completion detection
    last_poll = 0
    poll_interval = 2  # Check history every 2 seconds

    while result['success'] is None and result['error'] is None:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            print(f"Timeout after {int(elapsed)}s", flush=True)
            ws.close()
            return False

        # Poll history endpoint periodically to catch completion
        if time.time() - last_poll >= poll_interval:
            last_poll = time.time()
            history_result = check_history_for_completion(prompt_id, port)

            if history_result['status'] == 'success':
                elapsed_int = int(elapsed)
                print(f"Workflow completed successfully ({elapsed_int}s)", flush=True)
                outputs = history_result.get('outputs', {})
                for node_id, output in outputs.items():
                    if 'images' in output:
                        for img in output['images']:
                            filename = img.get('filename', 'unknown')
                            print(f"  Output: {filename}", flush=True)
                            if output_dir:
                                subfolder = img.get('subfolder', '')
                                img_type = img.get('type', 'output')
                                download_image_from_server(filename, subfolder, img_type, port, output_dir)
                ws.close()
                return True
            elif history_result['status'] == 'error':
                print(f"Workflow failed", flush=True)
                for msg in history_result.get('messages', []):
                    print(f"  Error: {msg}", flush=True)
                ws.close()
                return False

        time.sleep(0.1)

    # Download images if completed via WebSocket signal
    if result['success'] and output_dir:
        for node_id, output in result['outputs'].items():
            if 'images' in output:
                for img in output['images']:
                    filename = img.get('filename', 'unknown')
                    subfolder = img.get('subfolder', '')
                    img_type = img.get('type', 'output')
                    download_image_from_server(filename, subfolder, img_type, port, output_dir)

    return result['success'] == True


def wait_for_completion_http(prompt_id: str, port: int, timeout: int = 3600, output_dir: str = None) -> bool:
    """Wait for workflow execution using HTTP polling (fallback).

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
    last_node = ""
    poll_count = 0
    consecutive_errors = 0

    while time.time() - start_time < timeout:
        poll_count += 1
        elapsed = int(time.time() - start_time)

        try:
            queue_response = urllib.request.urlopen(queue_url, timeout=5)
            queue_data = json.loads(queue_response.read().decode('utf-8'))

            running = queue_data.get('queue_running', [])
            pending = queue_data.get('queue_pending', [])

            # Find our prompt in the running queue to get current node info
            our_running_item = None
            for item in running:
                if len(item) > 1 and item[1] == prompt_id:
                    our_running_item = item
                    break

            our_prompt_pending = any(item[1] == prompt_id for item in pending if len(item) > 1)

            if our_running_item:
                # Extract currently executing node from the running item
                # Format: [queue_id, prompt_id, workflow_data, extra_data, output_node_ids]
                # The extra_data (index 3) sometimes contains execution state
                current_node_info = ""
                if len(our_running_item) > 3:
                    extra = our_running_item[3]
                    if isinstance(extra, dict):
                        # Check for current node being executed
                        if 'extra_pnginfo' in extra:
                            pass  # PNG info doesn't have current node
                        # Some versions include node info here
                        current_node = extra.get('current_node')
                        if current_node:
                            current_node_info = f" (node {current_node})"

                # Print status with node info if available
                status_msg = f"Executing{current_node_info}... ({elapsed}s)"
                if elapsed % 10 == 0 or last_status != status_msg:
                    print(status_msg, flush=True)
                    last_status = status_msg
            elif our_prompt_pending:
                queue_pos = 0
                for i, item in enumerate(pending):
                    if len(item) > 1 and item[1] == prompt_id:
                        queue_pos = i + 1
                        break
                status = f"Queued (position {queue_pos})... ({elapsed}s)"
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

                    if status_data.get('status_str') == 'success' or outputs:
                        print(f"Workflow completed successfully in {elapsed}s", flush=True)
                        for node_id, output in outputs.items():
                            if 'images' in output:
                                for img in output['images']:
                                    filename = img.get('filename', 'unknown')
                                    subfolder = img.get('subfolder', '')
                                    img_type = img.get('type', 'output')
                                    print(f"Output image: {filename}", flush=True)
                                    if output_dir:
                                        download_image_from_server(filename, subfolder, img_type, port, output_dir)
                            # Check for 3D model outputs
                            for key in ['gltf', 'glb', 'obj', 'fbx']:
                                if key in output:
                                    for item in output[key]:
                                        print(f"Output 3D ({key}): {item.get('filename', 'unknown')}", flush=True)
                        return True

                    if status_data.get('status_str') == 'error':
                        print(f"Workflow failed with error", flush=True)
                        messages = status_data.get('messages', [])
                        for msg in messages:
                            print(f"Error detail: {msg}", flush=True)
                        return False
                else:
                    # Not in queue and not in history - might be starting up
                    if elapsed % 10 == 0 and last_status != "waiting":
                        print(f"Waiting for execution to start... ({elapsed}s)", flush=True)
                        last_status = "waiting"

            consecutive_errors = 0

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            consecutive_errors += 1
            if consecutive_errors >= 10:
                print(f"ERROR: Lost connection to ComfyUI after {consecutive_errors} consecutive failures")
                print(f"Last error: {e}")
                return False
            if poll_count % 10 == 0:
                print(f"Connection check... ({elapsed}s) - {consecutive_errors} consecutive errors", flush=True)

        time.sleep(0.5)

    print(f"Timeout waiting for workflow completion after {timeout}s", flush=True)
    return False


def wait_for_completion(prompt_id: str, port: int, timeout: int = 3600, output_dir: str = None) -> bool:
    """Wait for workflow execution to complete using WebSocket or HTTP polling.

    Args:
        prompt_id: The prompt ID to wait for
        port: ComfyUI server port
        timeout: Timeout in seconds
        output_dir: If provided, download output images to this directory

    Returns:
        True if workflow completed successfully
    """
    if WEBSOCKET_AVAILABLE:
        print("Using WebSocket for real-time progress monitoring", flush=True)
        try:
            return wait_for_completion_websocket(prompt_id, port, timeout, output_dir)
        except Exception as e:
            print(f"WebSocket failed, falling back to HTTP polling: {e}", flush=True)
            return wait_for_completion_http(prompt_id, port, timeout, output_dir)
    else:
        print("=" * 60, flush=True)
        print("NOTE: Using HTTP polling (limited progress info)", flush=True)
        print("For node-level progress, install websocket-client:", flush=True)
        print(f"  {sys.executable} -m pip install websocket-client", flush=True)
        print("=" * 60, flush=True)
        return wait_for_completion_http(prompt_id, port, timeout, output_dir)


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
    parser.add_argument('--timeout', type=int, default=3600, help='Execution timeout in seconds per generation')
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
    parser.add_argument('--comfyui-output-dir', help='ComfyUI default output directory (for moving 3D files that cannot specify output path)')
    parser.add_argument('--full-restart', action='store_true', help='Force full server restart between jobs (ignored in non-persistent mode)')
    parser.add_argument('--server-not-found', choices=['fail', 'wait'], default='fail',
                       help='Behavior when server not found in persistent mode: fail immediately or wait')
    parser.add_argument('--server-wait-timeout', type=int, default=300,
                       help='Timeout in seconds when waiting for server to start (default: 300 = 5 minutes)')

    args = parser.parse_args()

    # Set up logging - tee all stdout/stderr to a log file
    setup_logging(args.output_prefix)

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

        # Check if full restart is requested BEFORE connecting
        full_restart = getattr(args, 'full_restart', False)
        if full_restart:
            print("\nFull restart requested - will restart ComfyUI server before processing")
            # Signal the server to restart
            if signal_server_restart(args.port):
                # Wait for the restart to complete
                if not wait_for_server_restart(args.port, timeout=300):
                    print("ERROR: Server restart failed or timed out")
                    sys.exit(1)
                print("Server restart complete - continuing with job")
            else:
                print("WARNING: Could not signal server restart")
                print("The health server may not be running (port + 1000)")
                print("Continuing without restart...")

        if not check_server_running(args.port):
            if args.server_not_found == 'wait':
                # Wait for server to start
                wait_timeout = args.server_wait_timeout
                print(f"Server not found - waiting up to {wait_timeout}s for it to start...")
                print(f"Expected server URL: http://127.0.0.1:{args.port}")
                if wait_for_server(args.port, timeout=wait_timeout):
                    print(f"Server is now available on port {args.port}")
                else:
                    print(f"ERROR: Server did not start within {wait_timeout}s timeout")
                    print("Please ensure ComfyUI is configured to start on the farm node.")
                    sys.exit(1)
            else:
                # Fail immediately (default behavior)
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
    def cleanup(signum=None, frame=None, exit_code=None):
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

        # Only exit if called from signal handler or explicit exit_code provided
        if signum is not None:
            sys.exit(1)
        elif exit_code is not None:
            sys.exit(exit_code)

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

                # Move output files (3D models, videos, audio) from ComfyUI's default output to target
                # This handles nodes that can't specify custom output paths
                if args.comfyui_output_dir:
                    print(f"[Runner] Checking for output files to move (3D/video/audio)")
                    print(f"[Runner] ComfyUI output dir: {args.comfyui_output_dir}")
                    print(f"[Runner] Target directory: {args.output_directory}")
                    moved = move_output_files(
                        args.comfyui_output_dir,
                        args.output_directory,
                        args.output_prefix,
                        recent_minutes=30  # Increase to 30 minutes for longer jobs
                    )
                    if moved:
                        print(f"Moved {len(moved)} output file(s) to target directory")
                    else:
                        print(f"[Runner] No output files found to move")
                else:
                    print(f"[Runner] No comfyui_output_dir specified - skipping file move")
            else:
                print(f"Frame {frame_num} failed or timed out", flush=True)
                failed += 1

        # Summary
        print(f"\n{'='*60}", flush=True)
        print(f"BATCH COMPLETE: {successful}/{total_frames} successful, {failed} failed", flush=True)
        print(f"{'='*60}", flush=True)

        exit_code = 0 if failed == 0 else 1
        print(f"Exiting with code {exit_code}")
        cleanup(exit_code=exit_code)

    except Exception as e:
        print(f"Error: {e}")
        cleanup(exit_code=1)


if __name__ == '__main__':
    main()
