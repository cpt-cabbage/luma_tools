"""
ComfyUI Shared Utilities.

Common functions for ComfyUI server communication, workflow handling, and file operations.
Used by runner.py and server.py.
"""

import sys
import os
import json
import time
import copy
import uuid
import shutil
import threading
import logging
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any, Union

logger = logging.getLogger(__name__)

# Lazy websocket import — avoid pip install at module import time
_websocket = None
_websocket_import_attempted = False


def _get_websocket():
    global _websocket, _websocket_import_attempted
    if _websocket is not None:
        return _websocket
    if _websocket_import_attempted:
        return None
    _websocket_import_attempted = True
    try:
        import websocket
        _websocket = websocket
        return websocket
    except ImportError:
        logger.warning(
            "websocket-client not installed. Install it with: "
            "pip install websocket-client"
        )
        return None


def _is_websocket_available():
    return _get_websocket() is not None


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

def submit_workflow(workflow: dict, server_url: str = None, port: int = None,
                    client_id: str = None, ui_workflow: dict = None) -> Optional[str]:
    """Submit workflow to ComfyUI API and return prompt_id.

    Args:
        workflow: The API-format workflow dict to execute.
        server_url: Server URL.
        port: Server port.
        client_id: WebSocket client ID for execution event routing.
            If provided, ComfyUI will send execution events (executing, executed,
            execution_start) to the WebSocket client with this ID.
        ui_workflow: Optional UI/nodes-format workflow to embed in the outputs
            via extra_data.extra_pnginfo. This is what ComfyUI's own frontend
            sends, and it's what lets SaveImage bake the graph into the PNG so
            an artist can drag a render back into ComfyUI to recover it.
    """
    base_url = _normalize_server_url(server_url, port)
    prompt_data = {"prompt": workflow}
    if client_id:
        prompt_data["client_id"] = client_id
    if ui_workflow:
        prompt_data["extra_data"] = {"extra_pnginfo": {"workflow": ui_workflow}}
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
        # ComfyUI returns a structured validation failure on 400. Unpacking it
        # turns "HTTP Error 400" into the actual node and input at fault, which
        # is the difference between a usable farm log and a dead end.
        try:
            payload = json.loads(error_body)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            err = payload.get('error')
            if isinstance(err, dict):
                logger.error(
                    f"  {err.get('type', 'error')}: {err.get('message', '')} "
                    f"{err.get('details', '')}".rstrip()
                )
            for node_id, node_err in (payload.get('node_errors') or {}).items():
                if not isinstance(node_err, dict):
                    continue
                logger.error(
                    f"  node {node_id} ({node_err.get('class_type', '?')}): "
                    f"{node_err.get('errors', node_err)}"
                )
        else:
            logger.error(f"Error details: {error_body}")
        return None
    except Exception as e:
        logger.error(f"Error submitting workflow: {e}")
        return None


def _post_json(url: str, payload: dict = None, timeout: int = 10) -> bool:
    """POST an optional JSON body, returning True on a 2xx response."""
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = {'Content-Type': 'application/json'} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception as e:
        logger.warning(f"POST {url} failed: {e}")
        return False


def interrupt_prompt(server_url: str = None, port: int = None,
                     prompt_id: str = None) -> bool:
    """Ask ComfyUI to stop executing.

    MUST be called from the farm worker — the artist's workstation has no
    network route to the ComfyUI server, only Deadline and the shared filesystem.
    Without this, cancelling a Deadline job removes the job but leaves the
    already-submitted prompt rendering to completion on the GPU.

    Args:
        prompt_id: Target a specific prompt where the server supports it.
            Older builds ignore the body and interrupt whatever is running.
    """
    base_url = _normalize_server_url(server_url, port)
    payload = {"prompt_id": prompt_id} if prompt_id else None
    ok = _post_json(f"{base_url}/interrupt", payload)
    logger.info(
        f"Interrupt {'sent' if ok else 'FAILED'}"
        + (f" for prompt {prompt_id}" if prompt_id else "")
    )
    return ok


def free_memory(server_url: str = None, port: int = None,
                unload_models: bool = True, free_memory_cache: bool = True) -> bool:
    """Release VRAM without restarting the ComfyUI process.

    A full process restart costs minutes of model reloading; this achieves the
    usual intent in seconds. Reach for the restart only when the process itself
    is in a bad state (a CUDA fault), not merely to reclaim memory.
    """
    base_url = _normalize_server_url(server_url, port)
    payload = {"unload_models": bool(unload_models),
               "free_memory": bool(free_memory_cache)}
    ok = _post_json(f"{base_url}/free", payload)
    logger.info(f"Free memory request {'sent' if ok else 'FAILED'}: {payload}")
    return ok


def check_history_for_completion(prompt_id: str, server_url: str = None, port: int = None) -> dict:
    """Check history endpoint to see if prompt completed.

    Returns:
        dict with 'status' and optional 'outputs':
        - 'success': prompt completed successfully
        - 'error': prompt failed with error messages
        - 'pending': prompt still executing (found in history, not finished)
        - 'not_found': server responded but prompt_id not in history
          (may indicate server restart cleared history)
        - 'unreachable': server not responding
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

            # Server is up but prompt_id not found — history may have been
            # cleared by a server restart
            return {'status': 'not_found'}
    except Exception:
        return {'status': 'unreachable'}


_queue_check_failures = 0
_queue_check_lock = threading.RLock()


def _is_prompt_in_queue(prompt_id: str, server_url: str) -> bool:
    """Check if a prompt is still in the ComfyUI queue (running or pending).

    Args:
        prompt_id: The prompt ID to look for
        server_url: Base server URL (e.g., 'http://127.0.0.1:8188')

    Returns:
        True if the prompt is found in running or pending queue
    """
    global _queue_check_failures
    try:
        queue_url = f"{server_url}/queue"
        with urllib.request.urlopen(queue_url, timeout=5) as response:
            queue_data = json.loads(response.read().decode('utf-8'))

        with _queue_check_lock:
            _queue_check_failures = 0  # Reset on success

        running = queue_data.get('queue_running', [])
        pending = queue_data.get('queue_pending', [])

        for item in running:
            if len(item) > 1 and item[1] == prompt_id:
                return True
        for item in pending:
            if len(item) > 1 and item[1] == prompt_id:
                return True

        return False
    except Exception as e:
        with _queue_check_lock:
            _queue_check_failures += 1
            failures = _queue_check_failures
        if failures < 3:
            # Conservative fallback — avoids false completion
            return True
        else:
            # Queue endpoint repeatedly failing — stop assuming it's running
            logger.warning(f"Queue endpoint failed {failures} times, assuming not in queue: {e}")
            return False


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
    track_node_timing: bool = False,
    client_id: str = None,
    workflow_dict: dict = None
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
        client_id: WebSocket client ID (must match the one used in submit_workflow
            for execution event routing)
        workflow_dict: API-format workflow dict for looking up node class_type

    Returns:
        bool if track_node_timing=False, otherwise dict with success and node_timing
    """
    # Reset queue check failure counter for each new prompt
    global _queue_check_failures
    with _queue_check_lock:
        _queue_check_failures = 0

    base_url = _normalize_server_url(server_url, port)
    ws_url = base_url.replace('http://', 'ws://').replace('https://', 'wss://')
    if not client_id:
        client_id = str(uuid.uuid4())
    ws_url = f"{ws_url}/ws?clientId={client_id}"

    result = {'success': None, 'error': None, 'outputs': {}}
    downloaded_files = set()  # Track files already downloaded via WebSocket
    start_time = time.time()
    last_progress = {'value': 0, 'max': 0}

    # Build node_id -> class_type lookup from workflow
    node_type_lookup = {}
    if workflow_dict:
        for nid, ndata in workflow_dict.items():
            if isinstance(ndata, dict) and 'class_type' in ndata:
                node_type_lookup[str(nid)] = ndata['class_type']

    # Node execution timing tracking
    node_timing = {}  # node_id -> {start_time, end_time, duration_ms, node_type}
    current_node = {'id': None, 'start': None}

    def _log_progress(value, max_val):
        """Emit the canonical progress line, throttled to ~10% steps.

        The exact wording matters: deadline.poller parses these lines out of the
        runner log to drive the tab's progress bar, so both the legacy
        'progress' message and the current 'progress_state' funnel through here.
        """
        nonlocal last_progress
        if not max_val or max_val <= 0:
            return
        pct = int(100 * value / max_val)
        last_pct = int(100 * last_progress['value'] / max(last_progress['max'], 1))
        if pct >= last_pct + 10 or value >= max_val:
            elapsed = int(time.time() - start_time)
            logger.info(
                f"  Progress: {pct}% ({int(value)}/{int(max_val)}) ({elapsed}s)"
            )
            last_progress = {'value': value, 'max': max_val}

    def _finalize_current_node():
        """Close out timing for the node that was executing, if any."""
        if not track_node_timing or current_node['id'] is None:
            return
        entry = node_timing.get(current_node['id'])
        if entry is not None and entry.get('end_time') is None:
            now = time.time()
            entry['end_time'] = now
            entry['duration_ms'] = int((now - current_node['start']) * 1000)

    def on_message(ws, message):
        nonlocal result, last_progress
        if isinstance(message, bytes):
            return  # Binary frame (image preview), not a JSON status message
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
                        # Legacy terminal signal (pre-execution_success builds)
                        _finalize_current_node()
                        elapsed = int(time.time() - start_time)
                        logger.info(f"Execution completed in {elapsed}s")
                        result['success'] = True
                        ws.close()
                    else:
                        # New node starting - finalize previous node timing
                        if track_node_timing:
                            now = time.time()
                            _finalize_current_node()

                            # Start tracking new node
                            current_node['id'] = node_id
                            current_node['start'] = now
                            node_timing[node_id] = {
                                'node_id': node_id,
                                'start_time': now,
                                'end_time': None,
                                'duration_ms': None,
                                'node_type': node_type_lookup.get(str(node_id)),
                            }

                        elapsed = int(time.time() - start_time)
                        logger.info(f"Executing node {node_id}... ({elapsed}s)")
                        last_progress = {'value': 0, 'max': 0}

            elif msg_type == 'progress':
                # Legacy per-node progress. Removed from ComfyUI in favour of
                # 'progress_state' — kept so an older pinned server still works.
                prog_data = data.get('data', {})
                _log_progress(prog_data.get('value', 0),
                              prog_data.get('max', 100))

            elif msg_type == 'progress_state':
                # Current ComfyUI progress message: a map of node_id -> state.
                # Collapse it to a single running/total pair so the runner log
                # keeps emitting the "Progress: N% (a/b)" line the Deadline
                # poller parses for the tab's progress bar.
                prog_data = data.get('data', {})
                if prog_data.get('prompt_id') not in (None, prompt_id):
                    pass
                else:
                    value = 0.0
                    max_val = 0.0
                    for node_state in (prog_data.get('nodes') or {}).values():
                        if not isinstance(node_state, dict):
                            continue
                        node_max = node_state.get('max') or 0
                        if node_max <= 0:
                            continue
                        max_val += node_max
                        value += min(node_state.get('value') or 0, node_max)
                    if max_val > 0:
                        _log_progress(value, max_val)

            elif msg_type == 'executed':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    node_id = exec_data.get('node')
                    output = exec_data.get('output', {})
                    result['outputs'][node_id] = output

                    # Update node timing with type info if available
                    if track_node_timing and node_id in node_timing:
                        node_type = exec_data.get('node_type') or node_type_lookup.get(str(node_id))
                        if node_type:
                            node_timing[node_id]['node_type'] = node_type

                    # Download images immediately via WebSocket event
                    # (don't wait for HTTP poll which may never run)
                    if 'images' in output:
                        for img in output['images']:
                            fname = img.get('filename', 'unknown')
                            logger.info(f"  Output: {fname}")
                            if output_dir and on_image_output:
                                on_image_output(img, base_url, output_dir)
                                downloaded_files.add(fname)
                    if 'gltf' in output or 'glb' in output:
                        for item in output.get('gltf', []) + output.get('glb', []):
                            logger.info(f"  Output 3D: {item.get('filename', 'unknown')}")

            elif msg_type == 'execution_cached':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    nodes = exec_data.get('nodes', [])
                    if nodes:
                        logger.info(f"Cached: {len(nodes)} node(s)")

            elif msg_type == 'execution_success':
                # Current ComfyUI's terminal success message. Older builds
                # instead sent executing(node=None), handled above; both paths
                # land here-equivalent, and the HTTP poll is the backstop.
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    _finalize_current_node()
                    elapsed = int(time.time() - start_time)
                    logger.info(f"Execution completed in {elapsed}s")
                    result['success'] = True
                    ws.close()

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

            elif msg_type == 'execution_interrupted':
                # Someone cancelled the prompt (or /interrupt was called).
                # Without this branch the prompt just vanishes from queue AND
                # history, which the not_found handler below reads as "server
                # restarted after finishing" — reporting a killed job as a
                # success and recording bogus timings for it.
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    node_id = exec_data.get('node_id')
                    node_type = exec_data.get('node_type')
                    logger.error(
                        f"Execution INTERRUPTED at node {node_id} ({node_type})"
                    )
                    result['error'] = 'execution_interrupted'
                    result['success'] = False
                    ws.close()

            elif msg_type == 'execution_blocked':
                exec_data = data.get('data', {})
                if exec_data.get('prompt_id') == prompt_id:
                    node_id = exec_data.get('node_id')
                    node_type = exec_data.get('node_type')
                    message_text = exec_data.get('exception_message', '')
                    logger.error(
                        f"Execution BLOCKED at node {node_id} ({node_type}): "
                        f"{message_text}"
                    )
                    result['error'] = f'execution_blocked: {message_text}'.strip(': ')
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

    _ws_mod = _get_websocket()
    if _ws_mod is None:
        logger.error("WebSocket module not available")
        if track_node_timing:
            return {'success': False, 'error': 'websocket_unavailable', 'node_timing': [], 'total_duration_ms': None}
        return False

    ws = _ws_mod.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws_thread = threading.Thread(target=lambda: ws.run_forever(ping_interval=30, ping_timeout=10))
    ws_thread.daemon = True
    ws_thread.start()

    def _cleanup_ws():
        """Close WebSocket and join thread to prevent resource leaks."""
        ws.close()
        ws_thread.join(timeout=5.0)

    # Hybrid: WebSocket for progress, HTTP polling for completion
    last_poll = 0
    poll_interval = 2
    not_found_count = 0

    try:
        while result['success'] is None and result['error'] is None:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"Timeout after {int(elapsed)}s")
                if track_node_timing:
                    return {
                        'success': False,
                        'error': 'timeout',
                        'node_timing': list(node_timing.values()),
                        'total_duration_ms': None
                    }
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
                                fname = img.get('filename', 'unknown')
                                if fname not in downloaded_files:
                                    logger.info(f"  Output: {fname}")
                                    if output_dir and on_image_output:
                                        on_image_output(img, base_url, output_dir)
                    result['success'] = True
                    break
                elif history_result['status'] == 'error':
                    logger.error(f"Workflow failed")
                    for msg in history_result.get('messages', []):
                        logger.error(f"  Error: {msg}")
                    result['error'] = '; '.join(history_result.get('messages', ['Unknown error']))
                    break
                elif history_result['status'] == 'not_found':
                    # Server is up but prompt_id gone from history.
                    # During NORMAL execution, the prompt is in the queue (not
                    # history) — so not_found is expected while nodes are running.
                    # Check the queue endpoint to see if the prompt is still active.
                    still_in_queue = _is_prompt_in_queue(prompt_id, base_url)
                    # Prefer hard evidence (a node actually reported an output)
                    # over "some node started". An interrupted or crashed
                    # prompt also leaves node_timing behind, and treating that
                    # as completion is how a killed job gets logged as success.
                    saw_outputs = bool(result.get('outputs'))
                    had_execution = saw_outputs or bool(node_timing)

                    if still_in_queue:
                        # Prompt is in the queue (running or pending) — not_found
                        # in history is completely normal during execution
                        not_found_count = 0
                        logger.debug(
                            f"Prompt not in history but still in queue, executing..."
                        )
                    elif had_execution:
                        # Prompt gone from both history AND queue, but we saw
                        # execution — server likely restarted after completion
                        not_found_count += 1
                        if not_found_count >= 3:
                            # Verify server is actually healthy before treating as completed
                            if check_server_health(server_url=base_url, timeout=5):
                                elapsed_int = int(elapsed)
                                if saw_outputs:
                                    logger.info(
                                        f"Server restarted after execution — treating as "
                                        f"completed ({elapsed_int}s, "
                                        f"{len(result['outputs'])} node(s) produced output)"
                                    )
                                else:
                                    # No node ever reported an output. This is
                                    # an inference, not a fact — say so, because
                                    # the alternative reading is a crash.
                                    logger.warning(
                                        f"Prompt vanished from queue and history after "
                                        f"{len(node_timing)} node(s) started but produced "
                                        f"no output ({elapsed_int}s). Assuming the server "
                                        f"restarted post-completion; if outputs are missing, "
                                        f"this job actually died mid-render."
                                    )
                                result['success'] = True
                                break
                            else:
                                # Server is down — reset and keep waiting
                                not_found_count = 0
                                logger.debug(
                                    "Server unreachable, resetting not_found counter"
                                )
                        else:
                            logger.debug(
                                f"Prompt gone from history and queue "
                                f"(count={not_found_count}), waiting..."
                            )
                    else:
                        not_found_count = 0
                else:
                    not_found_count = 0

            time.sleep(0.1)
    finally:
        _cleanup_ws()

    success = result['success'] == True

    if track_node_timing:
        # Finalize timing for the last node if HTTP polling detected completion
        # before the WebSocket received the executing(node=None) message
        if current_node['id'] is not None and current_node['id'] in node_timing:
            entry = node_timing[current_node['id']]
            if entry['end_time'] is None:
                end_time = time.time()
                entry['end_time'] = end_time
                entry['duration_ms'] = int((end_time - current_node['start']) * 1000)

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
    # Reset queue check failure counter for each new prompt to avoid leaking
    # state between prompts in the same process.
    global _queue_check_failures
    with _queue_check_lock:
        _queue_check_failures = 0

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
    track_node_timing: bool = False,
    client_id: str = None,
    workflow_dict: dict = None
) -> "Union[bool, dict]":
    """Wait for workflow execution to complete using WebSocket or HTTP polling.

    Args:
        prompt_id: The prompt ID to wait for
        server_url: Server URL
        port: Server port
        timeout: Timeout in seconds
        output_dir: Directory for output files
        on_image_output: Callback for image outputs
        track_node_timing: If True, track node execution timing
        client_id: WebSocket client ID (must match the one used in submit_workflow)
        workflow_dict: API-format workflow dict for node type lookup

    Returns:
        bool: Success/failure if track_node_timing=False
        dict: {'success': bool, 'node_timing': list, 'total_duration_ms': int|None}
              if track_node_timing=True
    """
    if _is_websocket_available():
        try:
            return wait_for_completion_websocket(
                prompt_id, server_url=server_url, port=port,
                timeout=timeout, output_dir=output_dir, on_image_output=on_image_output,
                track_node_timing=track_node_timing, client_id=client_id,
                workflow_dict=workflow_dict
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

# Input names that carry a generation seed. Applied to ANY node exposing one.
#
# This replaces a hardcoded node-type allow-list. That list covered seven types
# and silently missed everything else — most importantly KSamplerAdvanced,
# SamplerCustom and SamplerCustomAdvanced, which use `noise_seed`. A workflow
# built on those kept whatever seed the submitter baked in, so every frame of a
# multi-generation job rendered the identical image.
#
# Working from the node's own inputs is also self-maintaining: a new sampler
# node pack needs no code change here.
SEED_INPUT_NAMES = ('seed', 'noise_seed')


def _is_link_ref(value) -> bool:
    """True when an API-format input value is a ``[node_id, slot]`` reference.

    A seed driven by another node (a converted widget, a seed-generator node)
    must not be overwritten with a literal.
    """
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


def iter_seed_inputs(node_data: dict):
    """Yield the seed input names on one API-format node that we may set.

    Skips seeds wired to another node, since those are driven by the graph.
    """
    inputs = node_data.get('inputs', {})
    if not isinstance(inputs, dict):
        return
    for name in SEED_INPUT_NAMES:
        if name in inputs and not _is_link_ref(inputs[name]):
            yield name

# Node types that accept an output filename prefix.
# Derived from EXPORT_NODE_TYPES in node_configs.py to stay in sync.
# Values are dicts of {input_key: value_template} where None means use output_prefix.
try:
    from comfyui.node_configs import EXPORT_NODE_TYPES, OUTPUT_SUFFIX
except ImportError:
    # Standalone on farm — copied as comfyui_node_configs.py next to comfyui_utils.py
    from comfyui_node_configs import EXPORT_NODE_TYPES, OUTPUT_SUFFIX

_PREFIX_NODES = {}
for _nt, _pk in EXPORT_NODE_TYPES.items():
    _PREFIX_NODES[_nt] = {_pk: None}
# HYMotionExportFBX also needs output_dir cleared
_PREFIX_NODES.setdefault('HYMotionExportFBX', {})['output_dir'] = ''


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
            if title.lower().endswith(OUTPUT_SUFFIX):
                return True
    return False


def modify_workflow_seed(workflow: dict, seed: int, output_prefix: str) -> dict:
    """Modify workflow to use a specific seed and output prefix.

    Seeds are applied to every node exposing a `seed`/`noise_seed` input that
    isn't driven by a link (see iter_seed_inputs). Export/prefix nodes are
    matched by class_type via _PREFIX_NODES, and PreviewImage is rewritten to
    SaveImage so the output filename can be controlled.

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

    seeded_nodes = 0
    for node_id, node_data in modified.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})

        # Apply the seed to every node that exposes one (not just a known list)
        for seed_param in iter_seed_inputs(node_data):
            inputs[seed_param] = seed
            seeded_nodes += 1
            logger.info(f"Set {class_type} node {node_id} {seed_param} to: {seed}")

        # Apply output prefix to matching node types
        if class_type in _PREFIX_NODES:
            # If _output nodes exist, only set prefix on those
            if has_output_nodes:
                meta = node_data.get('_meta', {})
                title = meta.get('title', '')
                if not title.lower().endswith(OUTPUT_SUFFIX):
                    logger.info(f"Skipping non-_output export node {node_id} ({class_type}, title='{title}')")
                    continue

            overrides = _PREFIX_NODES[class_type]
            for key, value in overrides.items():
                inputs[key] = output_prefix if value is None else value
            logger.info(f"Set {class_type} node {node_id} prefix to: {output_prefix}")

    if not seeded_nodes:
        # Every frame of this job will be byte-identical. Almost always means
        # the seed input is named something we don't recognise, or is driven by
        # a link — either way the artist asked for variations and won't get any.
        logger.warning(
            "No seed input found in this workflow — all generations will be "
            "identical. Expected an unlinked input named one of: %s",
            ", ".join(SEED_INPUT_NAMES),
        )

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
        f'Content-Disposition: form-data; name="image"; filename="{filename.replace(chr(34), "_")}"\r\n'
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

# Default extensions for output files that need moving.
# Sourced from core.config so adding a new format updates every consumer.
try:
    from core.config import MODEL_EXTENSIONS as _MODEL_EXT
    from core.config import VIDEO_EXTENSIONS as _VIDEO_EXT
    from core.config import AUDIO_EXTENSIONS as _AUDIO_EXT
    OUTPUT_FILE_EXTENSIONS = tuple(sorted(_MODEL_EXT | _VIDEO_EXT | _AUDIO_EXT))
except ImportError:
    # Farm-isolation fallback (this module is copied to a flat _job_data dir
    # without the core package on path).
    OUTPUT_FILE_EXTENSIONS = (
        '.glb', '.gltf', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz', '.dae',
        '.stl', '.ply',
        '.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.wmv', '.m4v',
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
        strict_prefix: If True, never fall back to the recency sweep — move only
            files starting with filename_prefix. Used with the '_output' suffix
            convention to avoid moving files from non-designated export nodes.
            Note that prefix-matching files are preferred regardless of this
            flag; strict_prefix only controls what happens when none match.

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

    # Single walk of the output tree instead of two glob passes per
    # extension (which was 44 full tree walks for the 22 default extensions;
    # the non-recursive pattern was a strict subset of the recursive one)
    ext_suffixes = tuple(ext.lower() for ext in extensions)
    all_matches = []
    for root, _dirs, files in os.walk(comfyui_output_dir):
        for name in files:
            if name.lower().endswith(ext_suffixes):
                all_matches.append(os.path.join(root, name))
    recent_files = []
    for file_path in all_matches:
        try:
            mtime = os.path.getmtime(file_path)
            if mtime > cutoff_time:
                recent_files.append((file_path, mtime))
        except Exception:
            pass  # Skip files that can't be accessed

    recent_files.sort(key=lambda x: x[1], reverse=True)

    # Prefer files this job actually named. ComfyUI's output directory is shared
    # by every job on the worker, so the recency sweep can otherwise pick up a
    # concurrent job's renders — and rename them with THIS job's prefix, which
    # lands another artist's work in this artist's gallery under the wrong name.
    # Fall back to the sweep only when nothing carries our prefix (nodes that
    # ignore filename_prefix entirely, which is why the sweep exists).
    prefixed = [(p, m) for p, m in recent_files
                if os.path.basename(p).startswith(filename_prefix)]
    if prefixed:
        if len(prefixed) < len(recent_files):
            logger.info(
                f"[move_output_files] {len(recent_files) - len(prefixed)} recent "
                f"file(s) don't carry prefix '{filename_prefix}' — leaving them "
                f"alone (likely another job's output)"
            )
        recent_files = prefixed
    elif strict_prefix:
        logger.info(
            f"[move_output_files] No files matched prefix '{filename_prefix}' "
            f"and strict_prefix is set — moving nothing"
        )
        recent_files = []
    elif recent_files:
        logger.warning(
            f"[move_output_files] No file carries prefix '{filename_prefix}'; "
            f"falling back to moving {len(recent_files)} recent file(s) by "
            f"timestamp. If other jobs share this worker, their output may be "
            f"picked up here."
        )

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
            # Only wait for the size to settle when the file was modified
            # moments ago (may still be mid-write). The old unconditional
            # loop added >=0.5s latency per moved file, serially.
            if time.time() - mtime < 2.0:
                initial_size = os.path.getsize(src_path)
                for _ in range(5):
                    time.sleep(0.5)
                    current_size = os.path.getsize(src_path)
                    if current_size == initial_size:
                        break
                    initial_size = current_size

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
    """Copy input files to server's input directory, converting unsupported formats to PNG."""
    if not input_files:
        return

    os.makedirs(server_input_dir, exist_ok=True)

    # Lazy import to avoid circular deps (utils.py is used by runner.py on farm)
    try:
        from comfyui.image_convert import copy_or_convert
        from core.settings_manager import safe_get_setting
        apply_cs = safe_get_setting("comfyui_convert_colorspace", True)
        has_convert = True
    except ImportError:
        has_convert = False

    for src_file in input_files:
        if not os.path.exists(src_file):
            logger.warning(f"Warning: Input file not found: {src_file}")
            continue

        if has_convert:
            result = copy_or_convert(src_file, server_input_dir, apply_colorspace=apply_cs)
            if result:
                logger.info(f"Copied/converted: {os.path.basename(result)}")
        else:
            filename = os.path.basename(src_file)
            dst_file = os.path.join(server_input_dir, filename)
            if not os.path.exists(dst_file) or os.path.getmtime(src_file) > os.path.getmtime(dst_file):
                shutil.copy2(src_file, dst_file)
                logger.info(f"Copied: {filename}")


# =============================================================================
# File Hashing
# =============================================================================

# In-memory cache for file hashes: path -> (mtime, hash)
# Uses ThreadSafeCache when available, plain dict with lock as fallback.
# Sized for whole galleries: at 256 entries a directory of a few hundred files
# thrashed the cache and re-read every file's full content over SMB on every
# poll tick.
_HASH_CACHE_MAX = 4096

try:
    from core.caching import ThreadSafeCache
    _hash_cache = ThreadSafeCache(max_size=_HASH_CACHE_MAX)
    _HASH_CACHE_TYPE = "threadsafe"
except ImportError:
    # Farm environment — use OrderedDict with lock for LRU-like eviction
    from collections import OrderedDict
    _hash_cache = OrderedDict()
    _hash_cache_lock = threading.RLock()
    _HASH_CACHE_TYPE = "dict"


# =============================================================================
# Persistent (local) hash sidecar
# =============================================================================
# The in-memory cache dies with the process, so every app start re-read the
# full content of every gallery file over the network. A small LOCAL sidecar
# keyed by (mtime, size) survives restarts and never touches the share.

_HASH_SIDECAR_MAX_ENTRIES = 20000
_HASH_SIDECAR_FLUSH_EVERY = 50

_sidecar_lock = threading.RLock()
_sidecar_data = None          # dict: path -> [mtime, size, hash]
_sidecar_dirty = 0            # unflushed insert count
_sidecar_disabled = False     # set when the sidecar can't be used at all


def _hash_sidecar_path() -> Optional[str]:
    """Local path of the persistent hash sidecar (never on the network)."""
    try:
        return os.path.join(os.path.expanduser("~"), ".luma_tools", "hash_cache.json")
    except Exception:
        return None


def _load_hash_sidecar() -> dict:
    """Lazily load the persistent sidecar. Caller must hold _sidecar_lock."""
    global _sidecar_data, _sidecar_disabled

    if _sidecar_data is not None:
        return _sidecar_data

    _sidecar_data = {}
    path = _hash_sidecar_path()
    if not path or _sidecar_disabled:
        return _sidecar_data

    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _sidecar_data = {
                    k: v for k, v in loaded.items()
                    if isinstance(v, (list, tuple)) and len(v) == 3
                }
    except Exception as e:
        logger.debug(f"[hash] Could not read hash sidecar: {e}")
        _sidecar_data = {}

    return _sidecar_data


def _flush_hash_sidecar_locked() -> None:
    """Write the sidecar to disk atomically. Caller must hold _sidecar_lock."""
    global _sidecar_dirty, _sidecar_disabled

    if _sidecar_data is None or _sidecar_disabled:
        return

    path = _hash_sidecar_path()
    if not path:
        return

    try:
        # core.utils.save_json does the atomic temp-file + replace dance and
        # creates the parent directory. Lazily imported: utils.py also runs on
        # farm workers where the `core` package does not exist.
        from core.utils import save_json
        save_json(path, _sidecar_data, pretty=False)
        _sidecar_dirty = 0
    except ImportError:
        # Farm environment — no local sidecar there, stop trying.
        _sidecar_disabled = True
    except Exception as e:
        logger.debug(f"[hash] Could not write hash sidecar: {e}")
        _sidecar_dirty = 0


def flush_hash_cache() -> None:
    """Persist any pending hash sidecar entries (safe to call anytime)."""
    with _sidecar_lock:
        if _sidecar_dirty:
            _flush_hash_sidecar_locked()


def _sidecar_get(file_path: str, mtime: float, size: int) -> Optional[str]:
    """Look up a hash in the persistent sidecar by (mtime, size)."""
    with _sidecar_lock:
        entry = _load_hash_sidecar().get(file_path)
        if not entry:
            return None
        try:
            cached_mtime, cached_size, cached_hash = entry
        except (ValueError, TypeError):
            return None
        if cached_mtime == mtime and cached_size == size:
            return cached_hash
    return None


def _sidecar_put(file_path: str, mtime: float, size: int, file_hash: str) -> None:
    """Record a hash in the persistent sidecar (flushed in batches)."""
    global _sidecar_dirty

    with _sidecar_lock:
        if _sidecar_disabled:
            return
        data = _load_hash_sidecar()
        data[file_path] = [mtime, size, file_hash]

        # Bound growth: drop oldest inserted entries (dicts keep insert order)
        while len(data) > _HASH_SIDECAR_MAX_ENTRIES:
            try:
                data.pop(next(iter(data)))
            except StopIteration:
                break

        _sidecar_dirty += 1
        if _sidecar_dirty >= _HASH_SIDECAR_FLUSH_EVERY:
            _flush_hash_sidecar_locked()


try:
    import atexit
    atexit.register(flush_hash_cache)
except Exception:  # pragma: no cover - atexit is always available in CPython
    pass


def compute_file_hash(file_path: str, algorithm: str = "sha256") -> Optional[str]:
    """Compute a content hash for a file using streaming reads.

    Results are cached with mtime-based invalidation so repeated calls
    for the same unchanged file are fast.

    Args:
        file_path: Path to the file to hash
        algorithm: Hash algorithm (default: sha256)

    Returns:
        Hex digest string, or None on error
    """
    import hashlib

    if not file_path or not os.path.isfile(file_path):
        return None

    try:
        stat_result = os.stat(file_path)
        current_mtime = stat_result.st_mtime
        current_size = stat_result.st_size
    except OSError:
        return None

    # Check cache
    cache_key = file_path
    if _HASH_CACHE_TYPE == "threadsafe":
        cached = _hash_cache.get(cache_key)
        if cached is not None:
            cached_mtime, cached_hash = cached
            if cached_mtime == current_mtime:
                return cached_hash
    else:
        with _hash_cache_lock:
            cached = _hash_cache.get(cache_key)
            if cached is not None:
                # Move to end on access (LRU: most recently used at end)
                _hash_cache.move_to_end(cache_key)
        if cached is not None:
            cached_mtime, cached_hash = cached
            if cached_mtime == current_mtime:
                return cached_hash

    # Second chance: the LOCAL persistent sidecar. Survives app restarts, so a
    # cold start doesn't re-read every gallery file's full content over SMB.
    if algorithm == "sha256":
        sidecar_hash = _sidecar_get(file_path, current_mtime, current_size)
        if sidecar_hash:
            if _HASH_CACHE_TYPE == "threadsafe":
                _hash_cache.set(cache_key, (current_mtime, sidecar_hash))
            else:
                with _hash_cache_lock:
                    _hash_cache[cache_key] = (current_mtime, sidecar_hash)
                    _hash_cache.move_to_end(cache_key)
            return sidecar_hash

    # Compute hash
    try:
        h = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(65536)  # 64KB chunks
                if not chunk:
                    break
                h.update(chunk)
        file_hash = h.hexdigest()
    except Exception as e:
        logger.warning(f"[hash] Failed to hash {file_path}: {e}")
        return None

    # Store in cache
    if _HASH_CACHE_TYPE == "threadsafe":
        _hash_cache.set(cache_key, (current_mtime, file_hash))
    else:
        with _hash_cache_lock:
            # LRU eviction: remove oldest entries (first in OrderedDict)
            while len(_hash_cache) >= _HASH_CACHE_MAX:
                _hash_cache.popitem(last=False)
            _hash_cache[cache_key] = (current_mtime, file_hash)

    if algorithm == "sha256":
        _sidecar_put(file_path, current_mtime, current_size, file_hash)

    return file_hash
