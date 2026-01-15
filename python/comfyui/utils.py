"""
ComfyUI Shared Utilities.

Common functions for ComfyUI server communication, workflow handling, and file operations.
Used by client.py, runner.py, and server.py.
"""

import sys
import os
import json
import time
import copy
import uuid
import shutil
import glob
import threading
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any, Union

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


def _normalize_server_url(server_url: str = None, port: int = None) -> str:
    """Convert port to server_url if needed."""
    if server_url:
        return server_url.rstrip('/')
    if port:
        return f"http://127.0.0.1:{port}"
    raise ValueError("Either server_url or port must be provided")


# =============================================================================
# Server Health & Connection
# =============================================================================

def check_server_health(server_url: str = None, port: int = None, timeout: int = 10) -> bool:
    """Check if ComfyUI server is healthy and ready."""
    url = f"{_normalize_server_url(server_url, port)}/system_stats"
    try:
        req = urllib.request.urlopen(url, timeout=timeout)
        return req.status == 200
    except Exception as e:
        print(f"Server health check failed: {e}")
        return False


def wait_for_server(server_url: str = None, port: int = None, timeout: int = 60) -> bool:
    """Wait for server to become available."""
    base_url = _normalize_server_url(server_url, port)
    start_time = time.time()
    print(f"Checking server at {base_url}...")

    while time.time() - start_time < timeout:
        if check_server_health(server_url=base_url):
            print("Server is ready")
            return True
        time.sleep(2)

    print(f"Server not available after {timeout}s")
    return False


# =============================================================================
# Workflow Submission & History
# =============================================================================

def submit_workflow(workflow: dict, server_url: str = None, port: int = None) -> Optional[str]:
    """Submit workflow to ComfyUI API and return prompt_id."""
    base_url = _normalize_server_url(server_url, port)
    prompt_data = {"prompt": workflow}
    url = f"{base_url}/prompt"
    data = json.dumps(prompt_data).encode('utf-8')

    print(f"Submitting workflow with {len(workflow)} nodes...")

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


def check_history_for_completion(prompt_id: str, server_url: str = None, port: int = None) -> dict:
    """Check history endpoint to see if prompt completed.

    Returns:
        dict with 'status' ('success', 'error', 'pending') and optional 'outputs'
    """
    base_url = _normalize_server_url(server_url, port)
    history_url = f"{base_url}/history/{prompt_id}"
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


# =============================================================================
# Completion Waiting (WebSocket + HTTP Polling)
# =============================================================================

def wait_for_completion_websocket(
    prompt_id: str,
    server_url: str = None,
    port: int = None,
    timeout: int = 3600,
    output_dir: str = None,
    on_image_output: callable = None
) -> bool:
    """Wait for workflow execution using WebSocket for progress + HTTP polling for completion."""
    base_url = _normalize_server_url(server_url, port)
    ws_url = base_url.replace('http://', 'ws://').replace('https://', 'wss://')
    client_id = str(uuid.uuid4())
    ws_url = f"{ws_url}/ws?clientId={client_id}"

    result = {'success': None, 'error': None, 'outputs': {}}
    start_time = time.time()
    last_progress = {'value': 0, 'max': 0}

    def on_message(ws, message):
        nonlocal result, last_progress
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
                if exec_data.get('prompt_id') == prompt_id:
                    print(f"Execution started", flush=True)

            elif msg_type == 'executing':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    node_id = exec_data.get('node')
                    if node_id is None:
                        elapsed = int(time.time() - start_time)
                        print(f"Execution completed in {elapsed}s", flush=True)
                        result['success'] = True
                        ws.close()
                    else:
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
        pass

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

    # Hybrid: WebSocket for progress, HTTP polling for completion
    last_poll = 0
    poll_interval = 2

    while result['success'] is None and result['error'] is None:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            print(f"Timeout after {int(elapsed)}s", flush=True)
            ws.close()
            return False

        if time.time() - last_poll >= poll_interval:
            last_poll = time.time()
            history_result = check_history_for_completion(prompt_id, server_url=base_url)

            if history_result['status'] == 'success':
                elapsed_int = int(elapsed)
                print(f"Workflow completed successfully ({elapsed_int}s)", flush=True)
                outputs = history_result.get('outputs', {})
                for node_id, output in outputs.items():
                    if 'images' in output:
                        for img in output['images']:
                            print(f"  Output: {img.get('filename', 'unknown')}", flush=True)
                            if output_dir and on_image_output:
                                on_image_output(img, base_url, output_dir)
                ws.close()
                return True
            elif history_result['status'] == 'error':
                print(f"Workflow failed", flush=True)
                for msg in history_result.get('messages', []):
                    print(f"  Error: {msg}", flush=True)
                ws.close()
                return False

        time.sleep(0.1)

    return result['success'] == True


def wait_for_completion_http(
    prompt_id: str,
    server_url: str = None,
    port: int = None,
    timeout: int = 3600,
    output_dir: str = None,
    on_image_output: callable = None
) -> bool:
    """Wait for workflow execution using HTTP polling (fallback when WebSocket unavailable)."""
    base_url = _normalize_server_url(server_url, port)
    history_url = f"{base_url}/history/{prompt_id}"
    queue_url = f"{base_url}/queue"
    start_time = time.time()
    last_status = ""
    last_print_time = 0
    consecutive_errors = 0

    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)

        try:
            queue_response = urllib.request.urlopen(queue_url, timeout=10)
            queue_data = json.loads(queue_response.read().decode('utf-8'))

            running = queue_data.get('queue_running', [])
            pending = queue_data.get('queue_pending', [])

            our_prompt_running = any(len(item) > 1 and item[1] == prompt_id for item in running)
            our_prompt_pending = any(len(item) > 1 and item[1] == prompt_id for item in pending)

            if our_prompt_running:
                consecutive_errors = 0
                if elapsed - last_print_time >= 10:
                    print(f"Executing... ({elapsed}s)", flush=True)
                    last_print_time = elapsed
            elif our_prompt_pending:
                consecutive_errors = 0
                status = f"Queued... ({elapsed}s)"
                if status != last_status:
                    print(status, flush=True)
                    last_status = status
            else:
                response = urllib.request.urlopen(history_url, timeout=10)
                history = json.loads(response.read().decode('utf-8'))

                if prompt_id in history:
                    consecutive_errors = 0
                    prompt_data = history[prompt_id]
                    status_data = prompt_data.get('status', {})
                    outputs = prompt_data.get('outputs', {})

                    if status_data.get('status_str') == 'success' or outputs:
                        print(f"Completed successfully in {elapsed}s", flush=True)
                        for node_id, output in outputs.items():
                            if 'images' in output:
                                for img in output['images']:
                                    print(f"Output: {img.get('filename', 'unknown')}", flush=True)
                                    if output_dir and on_image_output:
                                        on_image_output(img, base_url, output_dir)
                            for key in ['gltf', 'glb', 'obj', 'fbx']:
                                if key in output:
                                    for item in output[key]:
                                        print(f"Output 3D ({key}): {item.get('filename', 'unknown')}", flush=True)
                        return True

                    if status_data.get('status_str') == 'error':
                        print("Workflow failed with error", flush=True)
                        for msg in status_data.get('messages', []):
                            print(f"Error: {msg}", flush=True)
                        return False
                else:
                    consecutive_errors += 1
                    if consecutive_errors > 5 and elapsed - last_print_time >= 10:
                        print(f"Waiting for result... ({elapsed}s)", flush=True)
                        last_print_time = elapsed

            consecutive_errors = 0

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            consecutive_errors += 1
            if consecutive_errors >= 10:
                print(f"ERROR: Lost connection after {consecutive_errors} consecutive failures: {e}")
                return False
            if elapsed - last_print_time >= 30:
                print(f"Connection issue ({elapsed}s): {e}", flush=True)
                last_print_time = elapsed
        except Exception as e:
            print(f"Unexpected error ({elapsed}s): {type(e).__name__}: {e}", flush=True)

        time.sleep(0.5)

    print(f"Timeout after {timeout}s", flush=True)
    return False


def wait_for_completion(
    prompt_id: str,
    server_url: str = None,
    port: int = None,
    timeout: int = 3600,
    output_dir: str = None,
    on_image_output: callable = None
) -> bool:
    """Wait for workflow execution to complete using WebSocket or HTTP polling."""
    if WEBSOCKET_AVAILABLE:
        print("Using WebSocket for real-time progress monitoring", flush=True)
        try:
            return wait_for_completion_websocket(
                prompt_id, server_url=server_url, port=port,
                timeout=timeout, output_dir=output_dir, on_image_output=on_image_output
            )
        except Exception as e:
            print(f"WebSocket failed, falling back to HTTP polling: {e}", flush=True)
            return wait_for_completion_http(
                prompt_id, server_url=server_url, port=port,
                timeout=timeout, output_dir=output_dir, on_image_output=on_image_output
            )
    else:
        print("=" * 60, flush=True)
        print("NOTE: Using HTTP polling (limited progress info)", flush=True)
        print("For node-level progress, install websocket-client:", flush=True)
        print(f"  {sys.executable} -m pip install websocket-client", flush=True)
        print("=" * 60, flush=True)
        return wait_for_completion_http(
            prompt_id, server_url=server_url, port=port,
            timeout=timeout, output_dir=output_dir, on_image_output=on_image_output
        )


# =============================================================================
# Workflow Modification
# =============================================================================

def modify_workflow_seed(workflow: dict, seed: int, output_prefix: str) -> dict:
    """Modify workflow to use a specific seed and output prefix.

    Handles:
    - KSampler nodes (seed)
    - RandomNoise nodes (noise_seed)
    - SaveImage nodes (filename_prefix)
    - HYMotionExportFBX nodes (output_dir, filename_prefix)
    - HYMotionGenerate nodes (seed)
    """
    modified = copy.deepcopy(workflow)

    for node_id, node_data in modified.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})

        if class_type == 'KSampler':
            inputs['seed'] = seed
            print(f"Set KSampler node {node_id} seed to: {seed}")

        elif class_type == 'RandomNoise':
            inputs['noise_seed'] = seed
            print(f"Set RandomNoise node {node_id} seed to: {seed}")

        elif class_type == 'SaveImage':
            inputs['filename_prefix'] = output_prefix
            print(f"Set SaveImage node {node_id} prefix to: {output_prefix}")

        elif class_type == 'HYMotionExportFBX':
            inputs['output_dir'] = ''
            inputs['filename_prefix'] = output_prefix
            print(f"Set HYMotionExportFBX node {node_id}: output_dir='', prefix={output_prefix}")

        elif class_type == 'HYMotionGenerate':
            inputs['seed'] = seed
            print(f"Set HYMotionGenerate node {node_id} seed to: {seed}")

    return modified


# =============================================================================
# Image Upload/Download
# =============================================================================

def upload_image_to_server(image_path: str, server_url: str = None, port: int = None) -> Optional[str]:
    """Upload an image to ComfyUI server's input directory.

    Returns:
        Filename as stored on server, or None on failure
    """
    if not os.path.exists(image_path):
        print(f"Image file not found: {image_path}")
        return None

    import mimetypes

    base_url = _normalize_server_url(server_url, port)
    filename = os.path.basename(image_path)
    url = f"{base_url}/upload/image"

    with open(image_path, 'rb') as f:
        file_data = f.read()

    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
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


def download_image_from_server(
    filename: str,
    subfolder: str,
    image_type: str,
    server_url: str = None,
    port: int = None,
    output_dir: str = None
) -> Optional[str]:
    """Download an image from ComfyUI server to local output directory.

    Returns:
        Local path where image was saved, or None on failure
    """
    import urllib.parse

    base_url = _normalize_server_url(server_url, port)
    params = urllib.parse.urlencode({
        'filename': filename,
        'subfolder': subfolder,
        'type': image_type
    })
    url = f"{base_url}/view?{params}"

    try:
        response = urllib.request.urlopen(url, timeout=30)
        image_data = response.read()

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            local_path = os.path.join(output_dir, filename)
            with open(local_path, 'wb') as f:
                f.write(image_data)
            print(f"Downloaded: {filename} -> {local_path}")
            return local_path
        return None

    except urllib.error.HTTPError as e:
        print(f"Failed to download {filename}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"Failed to download {filename}: {e}")
        return None


# =============================================================================
# Output File Operations
# =============================================================================

# Default extensions for output files that need moving
OUTPUT_FILE_EXTENSIONS = (
    # 3D model formats
    '.glb', '.gltf', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz', '.dae',
    # Video formats
    '.mp4', '.mov', '.avi', '.webm',
    # Audio formats
    '.wav', '.mp3', '.flac', '.ogg',
)


def move_output_files(
    comfyui_output_dir: str,
    target_dir: str,
    filename_prefix: str,
    extensions: tuple = OUTPUT_FILE_EXTENSIONS,
    recent_minutes: int = 10
) -> List[str]:
    """Move output files from ComfyUI's output directory to target directory.

    Some ComfyUI nodes save directly to the default output folder without
    an option to specify a custom path. This function finds and moves those
    files after workflow completion.

    Args:
        comfyui_output_dir: ComfyUI's default output directory
        target_dir: Target directory to move files to
        filename_prefix: Prefix for renamed files
        extensions: File extensions to look for
        recent_minutes: Only move files modified within this many minutes

    Returns:
        List of moved file paths in target directory
    """
    moved_files = []

    if not comfyui_output_dir or not os.path.isdir(comfyui_output_dir):
        print(f"[move_output_files] Output dir doesn't exist: {comfyui_output_dir}")
        return moved_files

    if not target_dir:
        print(f"[move_output_files] No target dir specified")
        return moved_files

    os.makedirs(target_dir, exist_ok=True)
    cutoff_time = time.time() - (recent_minutes * 60)

    print(f"[move_output_files] Searching for {extensions} in {comfyui_output_dir}")
    print(f"[move_output_files] Target prefix: {filename_prefix}")
    print(f"[move_output_files] Looking for files modified in last {recent_minutes} minutes")

    all_matches = []
    for ext in extensions:
        top_pattern = os.path.join(comfyui_output_dir, f"*{ext}")
        top_matches = glob.glob(top_pattern)
        all_matches.extend(top_matches)

        recursive_pattern = os.path.join(comfyui_output_dir, "**", f"*{ext}")
        recursive_matches = glob.glob(recursive_pattern, recursive=True)
        all_matches.extend(recursive_matches)

    all_matches = list(set(all_matches))
    recent_files = []
    for file_path in all_matches:
        try:
            mtime = os.path.getmtime(file_path)
            if mtime > cutoff_time:
                recent_files.append((file_path, mtime))
        except Exception as e:
            print(f"[move_output_files] Error checking {file_path}: {e}")

    recent_files.sort(key=lambda x: x[1], reverse=True)

    print(f"[move_output_files] Found {len(recent_files)} recent files out of {len(all_matches)} total")
    for file_path, mtime in recent_files:
        age = int((time.time() - mtime) / 60)
        print(f"  - {os.path.basename(file_path)} ({age} min ago)")

    for src_path, mtime in recent_files:
        original_filename = os.path.basename(src_path)
        ext = os.path.splitext(original_filename)[1]

        if original_filename.startswith(filename_prefix):
            new_filename = original_filename
        else:
            new_filename = f"{filename_prefix}_{original_filename}"
        dest_path = os.path.join(target_dir, new_filename)

        counter = 1
        while os.path.exists(dest_path):
            base = os.path.splitext(new_filename)[0]
            new_filename = f"{base}_{counter}{ext}"
            dest_path = os.path.join(target_dir, new_filename)
            counter += 1

        try:
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


def collect_input_images(workflow: dict, workflow_dir: str) -> List[str]:
    """Collect input image paths from workflow LoadImage nodes."""
    images = []

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})

        if class_type == 'LoadImage':
            image_name = inputs.get('image')
            if image_name:
                if os.path.isabs(image_name) and os.path.exists(image_name):
                    images.append(image_name)
                else:
                    local_path = os.path.join(workflow_dir, image_name)
                    if os.path.exists(local_path):
                        images.append(local_path)

    return images


def get_workflow_images(workflow: dict) -> List[str]:
    """Extract all image filenames from LoadImage nodes in a workflow."""
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


def copy_inputs_to_server(input_files: list, server_input_dir: str):
    """Copy input files to server's input directory."""
    if not input_files:
        return

    os.makedirs(server_input_dir, exist_ok=True)

    for src_file in input_files:
        if not os.path.exists(src_file):
            print(f"Warning: Input file not found: {src_file}")
            continue

        filename = os.path.basename(src_file)
        dst_file = os.path.join(server_input_dir, filename)

        if not os.path.exists(dst_file) or os.path.getmtime(src_file) > os.path.getmtime(dst_file):
            shutil.copy2(src_file, dst_file)
            print(f"Copied: {filename}")
