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
import argparse
import urllib.request
import urllib.error


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


def wait_for_completion(prompt_id: str, server_url: str, timeout: int = 600) -> bool:
    """Wait for workflow execution to complete."""
    history_url = f"{server_url}/history/{prompt_id}"
    queue_url = f"{server_url}/queue"
    start_time = time.time()
    last_status = ""

    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)

        try:
            # Check queue status
            queue_response = urllib.request.urlopen(queue_url, timeout=5)
            queue_data = json.loads(queue_response.read().decode('utf-8'))

            running = queue_data.get('queue_running', [])
            pending = queue_data.get('queue_pending', [])

            our_prompt_running = any(item[1] == prompt_id for item in running)
            our_prompt_pending = any(item[1] == prompt_id for item in pending)

            if our_prompt_running:
                if elapsed % 10 == 0:
                    print(f"Executing... ({elapsed}s)", flush=True)
            elif our_prompt_pending:
                status = f"Queued... ({elapsed}s)"
                if status != last_status:
                    print(status, flush=True)
                    last_status = status
            else:
                # Check history for completion
                response = urllib.request.urlopen(history_url, timeout=5)
                history = json.loads(response.read().decode('utf-8'))

                if prompt_id in history:
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

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            if elapsed % 30 == 0:
                print(f"Connection issue, retrying... ({elapsed}s)", flush=True)

        time.sleep(0.5)

    print(f"Timeout after {timeout}s", flush=True)
    return False


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
    parser.add_argument('--timeout', type=int, default=600,
                        help='Execution timeout in seconds (default: 600)')
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
