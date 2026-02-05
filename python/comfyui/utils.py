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
import logging
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any, Union

logger = logging.getLogger(__name__)

# Try to import websocket for real-time progress
WEBSOCKET_AVAILABLE = False
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    # Try to install websocket-client automatically
    logger.info("websocket-client not found, attempting to install...")
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
            logger.info("Successfully installed websocket-client")
        else:
            logger.error(f"Failed to install websocket-client: {_result.stderr}")
    except Exception as _e:
        logger.error(f"Could not auto-install websocket-client: {_e}")


# =============================================================================
# ComfyUI Path Resolution
# =============================================================================

def resolve_comfyui_paths(comfyui_path: str, mode: str = "embedded",
                          python_path: Optional[str] = None) -> tuple:
    """
    Resolve ComfyUI Python executable and main.py paths based on installation mode.

    This centralizes the path resolution logic that was previously duplicated
    across runner.py, server.py, and deadline_submitter.py.

    Args:
        comfyui_path: Base path to ComfyUI installation
        mode: One of "embedded", "portable", or "standalone"
        python_path: Required for standalone mode - path to Python executable

    Returns:
        Tuple of (python_exe, main_py) paths

    Raises:
        ValueError: If mode is invalid or python_path not provided for standalone
    """
    if mode == "embedded":
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
        main_py = os.path.join(comfyui_path, "ComfyUI", "main.py")
    elif mode == "portable":
        # Check common venv locations
        venv_locations = [
            os.path.join(comfyui_path, "venv", "Scripts", "python.exe"),
            os.path.join(comfyui_path, ".venv", "Scripts", "python.exe"),
        ]
        main_py_locations = [
            os.path.join(comfyui_path, "ComfyUI", "main.py"),
        ]

        python_exe = next((p for p in venv_locations if os.path.exists(p)), venv_locations[0])
        main_py = next((p for p in main_py_locations if os.path.exists(p)), main_py_locations[0])
    elif mode == "standalone":
        if not python_path:
            raise ValueError("Python path required for standalone mode")
        python_exe = python_path
        main_py = os.path.join(comfyui_path, "main.py")
    else:
        raise ValueError(f"Invalid ComfyUI mode: {mode}. Must be 'embedded', 'portable', or 'standalone'")

    return python_exe, main_py


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
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except Exception as e:
        logger.warning(f"Server health check failed: {e}")
        return False


def wait_for_server(server_url: str = None, port: int = None, timeout: int = 60) -> bool:
    """Wait for server to become available."""
    base_url = _normalize_server_url(server_url, port)
    start_time = time.time()
    logger.info(f"Checking server at {base_url}...")

    while time.time() - start_time < timeout:
        if check_server_health(server_url=base_url):
            logger.info("Server is ready")
            return True
        time.sleep(2)

    logger.warning(f"Server not available after {timeout}s")
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

    logger.info(f"Submitting workflow with {len(workflow)} nodes...")

    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            prompt_id = result.get('prompt_id')
            logger.info(f"Workflow submitted, prompt_id: {prompt_id}")
            return prompt_id
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"HTTP Error {e.code}: {e.reason}")
        logger.error(f"Error details: {error_body}")
        return None
    except Exception as e:
        logger.error(f"Error submitting workflow: {e}")
        return None


def check_history_for_completion(prompt_id: str, server_url: str = None, port: int = None) -> dict:
    """Check history endpoint to see if prompt completed.

    Returns:
        dict with 'status' ('success', 'error', 'pending') and optional 'outputs'
    """
    base_url = _normalize_server_url(server_url, port)
    history_url = f"{base_url}/history/{prompt_id}"
    try:
        with urllib.request.urlopen(history_url, timeout=5) as response:
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
    on_image_output: callable = None,
    track_node_timing: bool = False
) -> bool:
    """Wait for workflow execution using WebSocket for progress + HTTP polling for completion.

    Args:
        prompt_id: The prompt ID to wait for
        server_url: Server URL
        port: Server port
        timeout: Timeout in seconds
        output_dir: Directory for output files
        on_image_output: Callback for image outputs
        track_node_timing: If True, track node execution timing (returns dict instead of bool)

    Returns:
        bool if track_node_timing=False, otherwise dict with success and node_timing
    """
    base_url = _normalize_server_url(server_url, port)
    ws_url = base_url.replace('http://', 'ws://').replace('https://', 'wss://')
    client_id = str(uuid.uuid4())
    ws_url = f"{ws_url}/ws?clientId={client_id}"

    result = {'success': None, 'error': None, 'outputs': {}}
    start_time = time.time()
    last_progress = {'value': 0, 'max': 0}

    # Node execution timing tracking
    node_timing = {}  # node_id -> {start_time, end_time, duration_ms, node_type}
    current_node = {'id': None, 'start': None}

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
                    logger.info(f"Queue: {queue_remaining} remaining ({elapsed}s)")

            elif msg_type == 'execution_start':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    logger.info(f"Execution started")

            elif msg_type == 'executing':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    node_id = exec_data.get('node')
                    if node_id is None:
                        # Execution completed - finalize timing for last node
                        if track_node_timing and current_node['id'] is not None:
                            end_time = time.time()
                            duration_ms = int((end_time - current_node['start']) * 1000)
                            if current_node['id'] in node_timing:
                                node_timing[current_node['id']]['end_time'] = end_time
                                node_timing[current_node['id']]['duration_ms'] = duration_ms

                        elapsed = int(time.time() - start_time)
                        logger.info(f"Execution completed in {elapsed}s")
                        result['success'] = True
                        ws.close()
                    else:
                        # New node starting - finalize previous node timing
                        if track_node_timing:
                            now = time.time()
                            if current_node['id'] is not None:
                                duration_ms = int((now - current_node['start']) * 1000)
                                if current_node['id'] in node_timing:
                                    node_timing[current_node['id']]['end_time'] = now
                                    node_timing[current_node['id']]['duration_ms'] = duration_ms

                            # Start tracking new node
                            current_node['id'] = node_id
                            current_node['start'] = now
                            node_timing[node_id] = {
                                'node_id': node_id,
                                'start_time': now,
                                'end_time': None,
                                'duration_ms': None,
                                'node_type': None  # Will be filled from executed message
                            }

                        elapsed = int(time.time() - start_time)
                        logger.info(f"Executing node {node_id}... ({elapsed}s)")
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
                        logger.info(f"  Progress: {pct}% ({value}/{max_val}) ({elapsed}s)")
                        last_progress = {'value': value, 'max': max_val}

            elif msg_type == 'executed':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    node_id = exec_data.get('node')
                    output = exec_data.get('output', {})
                    result['outputs'][node_id] = output

                    # Update node timing with type info if available
                    if track_node_timing and node_id in node_timing:
                        # Try to extract node type from execution data
                        node_type = exec_data.get('node_type')
                        if node_type:
                            node_timing[node_id]['node_type'] = node_type

                    if 'images' in output:
                        for img in output['images']:
                            logger.info(f"  Output: {img.get('filename', 'unknown')}")
                    if 'gltf' in output or 'glb' in output:
                        for item in output.get('gltf', []) + output.get('glb', []):
                            logger.info(f"  Output 3D: {item.get('filename', 'unknown')}")

            elif msg_type == 'execution_cached':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    nodes = exec_data.get('nodes', [])
                    if nodes:
                        logger.info(f"Cached: {len(nodes)} node(s)")

            elif msg_type == 'execution_error':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    error = exec_data.get('exception_message', 'Unknown error')
                    node_id = exec_data.get('node_id')
                    node_type = exec_data.get('node_type')
                    logger.error(f"ERROR in node {node_id} ({node_type}): {error}")
                    result['error'] = error
                    result['success'] = False
                    ws.close()

        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"WebSocket message error: {e}")

    def on_error(ws, error):
        logger.error(f"WebSocket error: {error}")

    def on_close(ws, close_status_code, close_msg):
        pass

    def on_open(ws):
        logger.info(f"Connected to ComfyUI WebSocket")

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
            logger.warning(f"Timeout after {int(elapsed)}s")
            ws.close()
            return False

        if time.time() - last_poll >= poll_interval:
            last_poll = time.time()
            history_result = check_history_for_completion(prompt_id, server_url=base_url)

            if history_result['status'] == 'success':
                elapsed_int = int(elapsed)
                logger.info(f"Workflow completed successfully ({elapsed_int}s)")
                outputs = history_result.get('outputs', {})
                for node_id, output in outputs.items():
                    if 'images' in output:
                        for img in output['images']:
                            logger.info(f"  Output: {img.get('filename', 'unknown')}")
                            if output_dir and on_image_output:
                                on_image_output(img, base_url, output_dir)
                ws.close()
                return True
            elif history_result['status'] == 'error':
                logger.error(f"Workflow failed")
                for msg in history_result.get('messages', []):
                    logger.error(f"  Error: {msg}")
                ws.close()
                return False

        time.sleep(0.1)

    success = result['success'] == True

    if track_node_timing:
        # Return detailed result with node timing
        return {
            'success': success,
            'error': result.get('error'),
            'node_timing': list(node_timing.values()),
            'total_duration_ms': int((time.time() - start_time) * 1000) if success else None
        }

    return success


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
            with urllib.request.urlopen(queue_url, timeout=10) as queue_response:
                queue_data = json.loads(queue_response.read().decode('utf-8'))

            running = queue_data.get('queue_running', [])
            pending = queue_data.get('queue_pending', [])

            our_prompt_running = any(len(item) > 1 and item[1] == prompt_id for item in running)
            our_prompt_pending = any(len(item) > 1 and item[1] == prompt_id for item in pending)

            if our_prompt_running:
                consecutive_errors = 0
                if elapsed - last_print_time >= 10:
                    logger.info(f"Executing... ({elapsed}s)")
                    last_print_time = elapsed
            elif our_prompt_pending:
                consecutive_errors = 0
                status = f"Queued... ({elapsed}s)"
                if status != last_status:
                    logger.info(status)
                    last_status = status
            else:
                with urllib.request.urlopen(history_url, timeout=10) as response:
                    history = json.loads(response.read().decode('utf-8'))

                if prompt_id in history:
                    consecutive_errors = 0
                    prompt_data = history[prompt_id]
                    status_data = prompt_data.get('status', {})
                    outputs = prompt_data.get('outputs', {})

                    if status_data.get('status_str') == 'success' or outputs:
                        logger.info(f"Completed successfully in {elapsed}s")
                        for node_id, output in outputs.items():
                            if 'images' in output:
                                for img in output['images']:
                                    logger.info(f"Output: {img.get('filename', 'unknown')}")
                                    if output_dir and on_image_output:
                                        on_image_output(img, base_url, output_dir)
                            for key in ['gltf', 'glb', 'obj', 'fbx']:
                                if key in output:
                                    for item in output[key]:
                                        logger.info(f"Output 3D ({key}): {item.get('filename', 'unknown')}")
                        return True

                    if status_data.get('status_str') == 'error':
                        logger.error("Workflow failed with error")
                        for msg in status_data.get('messages', []):
                            logger.error(f"Error: {msg}")
                        return False
                else:
                    consecutive_errors += 1
                    # Only log waiting status after longer intervals to reduce noise
                    if consecutive_errors > 5 and elapsed - last_print_time >= 60:
                        logger.debug(f"Waiting for result... ({elapsed}s)")
                        last_print_time = elapsed

            consecutive_errors = 0

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            consecutive_errors += 1
            if consecutive_errors >= 10:
                logger.error(f"ERROR: Lost connection after {consecutive_errors} consecutive failures: {e}")
                return False
            if elapsed - last_print_time >= 30:
                logger.warning(f"Connection issue ({elapsed}s): {e}")
                last_print_time = elapsed
        except Exception as e:
            logger.error(f"Unexpected error ({elapsed}s): {type(e).__name__}: {e}")

        time.sleep(0.5)

    logger.warning(f"Timeout after {timeout}s")
    return False


def wait_for_completion(
    prompt_id: str,
    server_url: str = None,
    port: int = None,
    timeout: int = 3600,
    output_dir: str = None,
    on_image_output: callable = None,
    track_node_timing: bool = False
):
    """Wait for workflow execution to complete using WebSocket or HTTP polling.

    Args:
        prompt_id: The prompt ID to wait for
        server_url: Server URL
        port: Server port
        timeout: Timeout in seconds
        output_dir: Directory for output files
        on_image_output: Callback for image outputs
        track_node_timing: If True, track node execution timing

    Returns:
        bool if track_node_timing=False
        dict with 'success', 'node_timing', 'total_duration_ms' if track_node_timing=True
    """
    if WEBSOCKET_AVAILABLE:
        try:
            return wait_for_completion_websocket(
                prompt_id, server_url=server_url, port=port,
                timeout=timeout, output_dir=output_dir, on_image_output=on_image_output,
                track_node_timing=track_node_timing
            )
        except Exception as e:
            logger.warning(f"WebSocket failed, falling back to HTTP polling: {e}")
            # HTTP polling doesn't support node timing, return basic result
            result = wait_for_completion_http(
                prompt_id, server_url=server_url, port=port,
                timeout=timeout, output_dir=output_dir, on_image_output=on_image_output
            )
            if track_node_timing:
                return {'success': result, 'node_timing': [], 'total_duration_ms': None}
            return result
    else:
        logger.info("=" * 60)
        logger.info("NOTE: Using HTTP polling (limited progress info)")
        logger.info("For node-level progress, install websocket-client:")
        logger.info(f"  {sys.executable} -m pip install websocket-client")
        logger.info("=" * 60)
        result = wait_for_completion_http(
            prompt_id, server_url=server_url, port=port,
            timeout=timeout, output_dir=output_dir, on_image_output=on_image_output
        )
        if track_node_timing:
            return {'success': result, 'node_timing': [], 'total_duration_ms': None}
        return result


# =============================================================================
# Workflow Modification
# =============================================================================

# Node types that accept a seed value, mapped to their seed parameter name
_SEED_NODES = {
    'KSampler': 'seed',
    'RandomNoise': 'noise_seed',
    'HYMotionGenerate': 'seed',
    'Trellis2MeshWithVoxelAdvancedGenerator': 'seed',
    'Trellis2ImageToShape': 'seed',
    'Trellis2ShapeToTexturedMesh': 'seed',
    'UltraShapeRefine': 'seed',
}

# Node types that accept an output filename prefix.
# Values are dicts of {input_key: value_template} where None means use output_prefix.
_PREFIX_NODES = {
    'SaveImage': {'filename_prefix': None},
    'HYMotionExportFBX': {'output_dir': '', 'filename_prefix': None},
    'Trellis2ExportMesh': {'filename_prefix': None},
    'Trellis2ExportGLB': {'filename_prefix': None},
    'UltraShapeSaveGLB': {'filename_prefix': None},
    'SaveAudioMP3': {'filename_prefix': None},
    'SaveAudioOpus': {'filename_prefix': None},
}

# Suffix for marking the primary output node (see node_configs.py for docs)
_OUTPUT_SUFFIX = '_output'


def has_output_suffix_nodes(workflow: dict) -> bool:
    """Check if any export node in the workflow has '_output' suffix in its title.

    When True, only export nodes with the suffix should receive the output prefix,
    and only their files should be moved to the output directory.
    """
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get('class_type', '')
        if class_type in _PREFIX_NODES:
            meta = node_data.get('_meta', {})
            title = meta.get('title', '')
            if title.endswith(_OUTPUT_SUFFIX):
                return True
    return False


def modify_workflow_seed(workflow: dict, seed: int, output_prefix: str) -> dict:
    """Modify workflow to use a specific seed and output prefix.

    Handles seed nodes (KSampler, RandomNoise, etc.), export/prefix nodes
    (SaveImage, HYMotionExportFBX, etc.), and converts PreviewImage to SaveImage.
    See _SEED_NODES and _PREFIX_NODES for the full list of supported node types.

    Respects '_output' suffix convention: if any export node has '_output' in its
    title, only that node gets the prefix. Others are left with their defaults.
    """
    modified = copy.deepcopy(workflow)

    # Convert PreviewImage nodes to SaveImage nodes so we can control the output filename
    # PreviewImage saves to temp folder with temp names, SaveImage allows filename_prefix
    for node_id, node_data in modified.items():
        if isinstance(node_data, dict) and node_data.get('class_type') == 'PreviewImage':
            node_data['class_type'] = 'SaveImage'
            if 'inputs' not in node_data:
                node_data['inputs'] = {}
            logger.info(f"Converted PreviewImage node {node_id} to SaveImage")

    # Check if any export node has _output suffix (primary output designation)
    has_output_nodes = has_output_suffix_nodes(modified)
    if has_output_nodes:
        logger.info("Detected _output suffix node(s) - only setting prefix on designated output nodes")

    for node_id, node_data in modified.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})

        # Apply seed to matching node types
        if class_type in _SEED_NODES:
            seed_param = _SEED_NODES[class_type]
            inputs[seed_param] = seed
            logger.info(f"Set {class_type} node {node_id} {seed_param} to: {seed}")

        # Apply output prefix to matching node types
        elif class_type in _PREFIX_NODES:
            # If _output nodes exist, only set prefix on those
            if has_output_nodes:
                meta = node_data.get('_meta', {})
                title = meta.get('title', '')
                if not title.endswith(_OUTPUT_SUFFIX):
                    logger.info(f"Skipping non-_output export node {node_id} ({class_type}, title='{title}')")
                    continue

            overrides = _PREFIX_NODES[class_type]
            for key, value in overrides.items():
                inputs[key] = output_prefix if value is None else value
            logger.info(f"Set {class_type} node {node_id} prefix to: {output_prefix}")

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
        logger.warning(f"Image file not found: {image_path}")
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
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            server_filename = result.get('name', filename)
            logger.info(f"Uploaded image to server: {filename} -> {server_filename}")
            return server_filename
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"Failed to upload image: HTTP {e.code} - {error_body}")
        return None
    except Exception as e:
        logger.error(f"Failed to upload image: {e}")
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
        with urllib.request.urlopen(url, timeout=30) as response:
            image_data = response.read()

            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                local_path = os.path.join(output_dir, filename)
                with open(local_path, 'wb') as f:
                    f.write(image_data)
                logger.info(f"Downloaded: {filename} -> {local_path}")
                return local_path
            return None

    except urllib.error.HTTPError as e:
        logger.error(f"Failed to download {filename}: HTTP {e.code}")
        return None
    except Exception as e:
        logger.error(f"Failed to download {filename}: {e}")
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
    recent_minutes: int = 10,
    strict_prefix: bool = False
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
        strict_prefix: If True, only move files that start with filename_prefix.
            Used with the '_output' suffix convention to avoid moving files
            from non-designated export nodes.

    Returns:
        List of moved file paths in target directory
    """
    moved_files = []

    if not comfyui_output_dir or not os.path.isdir(comfyui_output_dir):
        logger.warning(f"[move_output_files] Output dir doesn't exist: {comfyui_output_dir}")
        return moved_files

    if not target_dir:
        logger.warning(f"[move_output_files] No target dir specified")
        return moved_files

    os.makedirs(target_dir, exist_ok=True)
    cutoff_time = time.time() - (recent_minutes * 60)

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
        except Exception:
            pass  # Skip files that can't be accessed

    recent_files.sort(key=lambda x: x[1], reverse=True)

    for src_path, mtime in recent_files:
        original_filename = os.path.basename(src_path)
        ext = os.path.splitext(original_filename)[1]

        # When strict_prefix is True, only move files from _output designated nodes
        if strict_prefix and not original_filename.startswith(filename_prefix):
            logger.debug(f"[move_output_files] Skipping non-output file: {original_filename}")
            continue

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
                time.sleep(2)  # Wait for file to finish writing

            shutil.move(src_path, dest_path)
            moved_files.append(dest_path)
        except Exception as e:
            logger.error(f"[move_output_files] Failed to move {original_filename}: {e}")

    # Log summary instead of per-file
    if moved_files:
        logger.info(f"[move_output_files] Moved {len(moved_files)} files to {target_dir}")

    return moved_files


# Known file loading node types used for input file detection
_FILE_LOADER_TYPES = frozenset([
    # Images
    'LoadImage',
    'Trellis2LoadImageWithTransparency',
    'LoadImageMask',
    'LoadImageBatch',
    # Videos
    'VHS_LoadVideo',
    'VHS_LoadVideoPath',
    'LoadVideo',
    # 3D Models
    'Load3D',
    # Audio
    'LoadAudio',
])

# Input parameter names that indicate file inputs
_FILE_INPUT_NAMES = frozenset([
    'image', 'video', 'model_file', 'audio', 'file', 'path'
])


def _find_workflow_image_names(workflow: dict) -> List[str]:
    """Extract file names from all file loading nodes in a workflow.

    Returns raw file name strings (not resolved paths). Used internally
    by collect_input_images() and get_workflow_images().

    Note: Despite the name 'image_names', this now returns ALL file types
    (images, videos, models, audio) for backwards compatibility.
    """
    files = []
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue

        class_type = node_data.get('class_type', '')
        inputs = node_data.get('inputs', {})

        # Check known file loader types
        if class_type in _FILE_LOADER_TYPES:
            # Try all possible input parameter names
            for input_name in _FILE_INPUT_NAMES:
                file_value = inputs.get(input_name)
                if file_value and isinstance(file_value, str) and not file_value.startswith('['):
                    files.append(file_value)
                    break  # Only add one file per node
        else:
            # Fallback: check if any input name matches file parameter names
            for input_name in _FILE_INPUT_NAMES:
                if input_name in inputs:
                    file_value = inputs.get(input_name)
                    if file_value and isinstance(file_value, str) and not file_value.startswith('['):
                        files.append(file_value)
                        break  # Only add one file per node
    return files


def collect_input_images(workflow: dict, workflow_dir: str) -> List[str]:
    """Collect resolved input image paths from workflow image loading nodes.

    Resolves image names to full paths using workflow_dir. Only includes
    images that exist on disk.
    """
    resolved = []
    for image_name in _find_workflow_image_names(workflow):
        if os.path.isabs(image_name) and os.path.exists(image_name):
            resolved.append(image_name)
        else:
            local_path = os.path.join(workflow_dir, image_name)
            if os.path.exists(local_path):
                resolved.append(local_path)
    return resolved


def get_workflow_images(workflow: dict) -> List[str]:
    """Extract all image filenames from image loading nodes in a workflow.

    Returns raw filenames without path resolution.
    """
    return _find_workflow_image_names(workflow)


def copy_inputs_to_server(input_files: list, server_input_dir: str):
    """Copy input files to server's input directory."""
    if not input_files:
        return

    os.makedirs(server_input_dir, exist_ok=True)

    for src_file in input_files:
        if not os.path.exists(src_file):
            logger.warning(f"Warning: Input file not found: {src_file}")
            continue

        filename = os.path.basename(src_file)
        dst_file = os.path.join(server_input_dir, filename)

        if not os.path.exists(dst_file) or os.path.getmtime(src_file) > os.path.getmtime(dst_file):
            shutil.copy2(src_file, dst_file)
            logger.info(f"Copied: {filename}")
