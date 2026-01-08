"""
ComfyUI Client Script.

Lightweight client that submits workflows to a running ComfyUI server.
Designed for Deadline jobs when using persistent server mode.

This script does NOT start ComfyUI - it expects a server to already be running.
Use comfyui_server.py to start a persistent server on the farm node.

Features:
- Connects to existing ComfyUI server
- Submits workflow and waits for completion
- Copies input images to server's input directory
- Supports seed modification per frame
- Fast startup (no model loading)

Usage:
    python comfyui_client.py --workflow "path/to/workflow.json" \\
        --server-url "http://localhost:8188" \\
        --input-directory "path/to/inputs" \\
        --output-directory "path/to/outputs" \\
        --frame 1 --seeds-file "path/to/seeds.json"
"""

import sys
import os
import json
import time
import copy
import shutil
import socket
import argparse
import urllib.request
import urllib.error
import uuid
import threading

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


def check_server_health(server_url: str, timeout: int = 10) -> bool:
    """Check if ComfyUI server is healthy and ready."""
    url = f"{server_url}/system_stats"
    try:
        req = urllib.request.urlopen(url, timeout=timeout)
        return req.status == 200
    except Exception as e:
        print(f"Server health check failed: {e}")
        return False


def wait_for_server(server_url: str, timeout: int = 60) -> bool:
    """Wait for server to become available."""
    start_time = time.time()
    print(f"Checking server at {server_url}...")

    while time.time() - start_time < timeout:
        if check_server_health(server_url):
            print("Server is ready")
            return True
        time.sleep(2)

    print(f"Server not available after {timeout}s")
    return False


def modify_workflow_seed(workflow: dict, seed: int, output_prefix: str) -> dict:
    """Modify workflow to use a specific seed and output prefix."""
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

    return modified


def submit_workflow(workflow: dict, server_url: str) -> str:
    """Submit workflow to ComfyUI API and return prompt_id."""
    prompt_data = {"prompt": workflow}
    url = f"{server_url}/prompt"
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


def check_history_for_completion(prompt_id: str, server_url: str) -> dict:
    """Check history endpoint to see if prompt completed.

    Returns:
        dict with 'status' ('success', 'error', 'pending') and optional 'outputs'
    """
    history_url = f"{server_url}/history/{prompt_id}"
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


def wait_for_completion_websocket(prompt_id: str, server_url: str, timeout: int = 3600) -> bool:
    """Wait for workflow execution using WebSocket for progress + HTTP polling for completion."""
    # Convert http://host:port to ws://host:port
    ws_url = server_url.replace('http://', 'ws://').replace('https://', 'wss://')
    client_id = str(uuid.uuid4())
    ws_url = f"{ws_url}/ws?clientId={client_id}"

    result = {'success': None, 'error': None}
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
                    output = exec_data.get('output', {})
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
            history_result = check_history_for_completion(prompt_id, server_url)

            if history_result['status'] == 'success':
                elapsed_int = int(elapsed)
                print(f"Workflow completed successfully ({elapsed_int}s)", flush=True)
                outputs = history_result.get('outputs', {})
                for node_id, output in outputs.items():
                    if 'images' in output:
                        for img in output['images']:
                            print(f"  Output: {img.get('filename', 'unknown')}", flush=True)
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


def wait_for_completion_http(prompt_id: str, server_url: str, timeout: int = 3600) -> bool:
    """Wait for workflow execution using HTTP polling (fallback when WebSocket unavailable)."""
    history_url = f"{server_url}/history/{prompt_id}"
    queue_url = f"{server_url}/queue"
    start_time = time.time()
    last_status = ""
    last_print_time = 0
    consecutive_not_found = 0

    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)

        try:
            # Check queue status
            queue_response = urllib.request.urlopen(queue_url, timeout=10)
            queue_data = json.loads(queue_response.read().decode('utf-8'))

            running = queue_data.get('queue_running', [])
            pending = queue_data.get('queue_pending', [])

            our_prompt_running = any(item[1] == prompt_id for item in running)
            our_prompt_pending = any(item[1] == prompt_id for item in pending)

            if our_prompt_running:
                consecutive_not_found = 0
                if elapsed - last_print_time >= 10:
                    print(f"Executing... ({elapsed}s)", flush=True)
                    last_print_time = elapsed
            elif our_prompt_pending:
                consecutive_not_found = 0
                status = f"Queued... ({elapsed}s)"
                if status != last_status:
                    print(status, flush=True)
                    last_status = status
            else:
                # Check history for completion
                response = urllib.request.urlopen(history_url, timeout=10)
                history = json.loads(response.read().decode('utf-8'))

                if prompt_id in history:
                    consecutive_not_found = 0
                    prompt_data = history[prompt_id]
                    status_data = prompt_data.get('status', {})
                    outputs = prompt_data.get('outputs', {})

                    if status_data.get('status_str') == 'success' or outputs:
                        print(f"Completed successfully in {elapsed}s", flush=True)
                        for node_id, output in outputs.items():
                            if 'images' in output:
                                for img in output['images']:
                                    print(f"Output: {img.get('filename', 'unknown')}", flush=True)
                        return True

                    if status_data.get('status_str') == 'error':
                        print("Workflow failed with error", flush=True)
                        for msg in status_data.get('messages', []):
                            print(f"Error: {msg}", flush=True)
                        return False
                else:
                    # Not in queue and not in history yet - might be processing
                    consecutive_not_found += 1
                    if consecutive_not_found > 5 and elapsed - last_print_time >= 10:
                        print(f"Waiting for result... ({elapsed}s)", flush=True)
                        last_print_time = elapsed

        except socket.timeout as e:
            print(f"Socket timeout while checking status ({elapsed}s): {e}", flush=True)
        except urllib.error.URLError as e:
            if elapsed - last_print_time >= 30:
                print(f"Connection issue ({elapsed}s): {e}", flush=True)
                last_print_time = elapsed
        except urllib.error.HTTPError as e:
            if elapsed - last_print_time >= 30:
                print(f"HTTP error ({elapsed}s): {e.code} {e.reason}", flush=True)
                last_print_time = elapsed
        except Exception as e:
            print(f"Unexpected error ({elapsed}s): {type(e).__name__}: {e}", flush=True)

        time.sleep(0.5)

    print(f"Timeout after {timeout}s", flush=True)
    return False


def wait_for_completion(prompt_id: str, server_url: str, timeout: int = 3600) -> bool:
    """Wait for workflow execution to complete using WebSocket or HTTP polling."""
    if WEBSOCKET_AVAILABLE:
        print("Using WebSocket for real-time progress monitoring", flush=True)
        try:
            return wait_for_completion_websocket(prompt_id, server_url, timeout)
        except Exception as e:
            print(f"WebSocket failed, falling back to HTTP polling: {e}", flush=True)
            return wait_for_completion_http(prompt_id, server_url, timeout)
    else:
        print("=" * 60, flush=True)
        print("NOTE: Using HTTP polling (limited progress info)", flush=True)
        print("For node-level progress, install websocket-client:", flush=True)
        print(f"  {sys.executable} -m pip install websocket-client", flush=True)
        print("=" * 60, flush=True)
        return wait_for_completion_http(prompt_id, server_url, timeout)


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

        # Only copy if newer or doesn't exist
        if not os.path.exists(dst_file) or os.path.getmtime(src_file) > os.path.getmtime(dst_file):
            shutil.copy2(src_file, dst_file)
            print(f"Copied: {filename}")


def collect_input_images(workflow: dict, workflow_dir: str) -> list:
    """Collect input image paths from workflow."""
    images = []

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})

        if class_type == 'LoadImage':
            image_name = inputs.get('image')
            if image_name:
                # Try to find the image
                if os.path.isabs(image_name) and os.path.exists(image_name):
                    images.append(image_name)
                else:
                    # Check in workflow directory
                    local_path = os.path.join(workflow_dir, image_name)
                    if os.path.exists(local_path):
                        images.append(local_path)

    return images


def main():
    parser = argparse.ArgumentParser(
        description='ComfyUI Client - Submit workflows to running server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Submit a single workflow
    python comfyui_client.py --workflow "workflow.json" \\
        --server-url "http://localhost:8188"

    # Submit with frame/seed from Deadline
    python comfyui_client.py --workflow "workflow.json" \\
        --server-url "http://localhost:8188" \\
        --frame 1 --seeds-file "seeds.json" \\
        --output-prefix "my_render"

    # Batch mode - process all frames in one run
    python comfyui_client.py --workflow "workflow.json" \\
        --server-url "http://localhost:8188" \\
        --seeds-file "seeds.json" --batch
        """
    )

    parser.add_argument('--workflow', required=True,
                        help='Path to workflow JSON file')
    parser.add_argument('--server-url', default='http://127.0.0.1:8188',
                        help='ComfyUI server URL (default: http://127.0.0.1:8188)')
    parser.add_argument('--server-input-dir', default=None,
                        help='Server input directory (for copying input images)')
    parser.add_argument('--output-directory', default=None,
                        help='Output directory (updates SaveImage nodes)')
    parser.add_argument('--frame', type=int, default=1,
                        help='Frame number (1-based)')
    parser.add_argument('--seeds-file', default=None,
                        help='Path to seeds JSON file')
    parser.add_argument('--output-prefix', default='comfyui_output',
                        help='Output filename prefix')
    parser.add_argument('--timeout', type=int, default=3600,
                        help='Execution timeout in seconds (default: 3600)')
    parser.add_argument('--batch', action='store_true',
                        help='Process all frames from seeds file')
    parser.add_argument('--wait-for-server', type=int, default=60,
                        help='Seconds to wait for server (default: 60)')

    args = parser.parse_args()

    # Verify workflow exists
    if not os.path.exists(args.workflow):
        print(f"ERROR: Workflow not found: {args.workflow}")
        sys.exit(1)

    # Load workflow
    print(f"Loading workflow: {args.workflow}")
    with open(args.workflow, 'r', encoding='utf-8') as f:
        base_workflow = json.load(f)

    workflow_dir = os.path.dirname(os.path.abspath(args.workflow))

    # Load seeds if provided
    seeds_data = None
    if args.seeds_file:
        if not os.path.exists(args.seeds_file):
            print(f"ERROR: Seeds file not found: {args.seeds_file}")
            sys.exit(1)

        with open(args.seeds_file, 'r', encoding='utf-8') as f:
            seeds_data = json.load(f)

    # Determine frames to process
    if args.batch and seeds_data:
        frames = list(range(1, len(seeds_data.get('seeds', [])) + 1))
        print(f"Batch mode: {len(frames)} frames to process")
    else:
        frames = [args.frame]

    # Wait for server to be ready
    if not wait_for_server(args.server_url, timeout=args.wait_for_server):
        print("ERROR: Server not available")
        sys.exit(1)

    # Collect and copy input images
    input_images = collect_input_images(base_workflow, workflow_dir)
    if input_images and args.server_input_dir:
        print(f"Copying {len(input_images)} input image(s) to server...")
        copy_inputs_to_server(input_images, args.server_input_dir)

    # Process frames
    successful = 0
    failed = 0

    for frame_num in frames:
        workflow = copy.deepcopy(base_workflow)

        # Apply seed and output prefix for this frame
        if seeds_data:
            frame_idx = frame_num - 1
            if frame_idx < 0 or frame_idx >= len(seeds_data.get('seeds', [])):
                print(f"ERROR: Frame {frame_num} out of range")
                failed += 1
                continue

            seed = seeds_data['seeds'][frame_idx]
            output_prefix = f"{args.output_prefix}_gen{frame_num:02d}"
            print(f"\nFrame {frame_num}: seed={seed}, prefix={output_prefix}")
            workflow = modify_workflow_seed(workflow, seed, output_prefix)
        else:
            output_prefix = args.output_prefix
            workflow = modify_workflow_seed(workflow, 12345, output_prefix)

        # Submit and wait
        prompt_id = submit_workflow(workflow, args.server_url)
        if not prompt_id:
            print(f"Failed to submit frame {frame_num}")
            failed += 1
            continue

        success = wait_for_completion(prompt_id, args.server_url, timeout=args.timeout)
        if success:
            successful += 1
        else:
            failed += 1

    # Summary
    total = len(frames)
    print(f"\n{'='*40}")
    print(f"Complete: {successful}/{total} successful, {failed} failed")
    print(f"{'='*40}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
