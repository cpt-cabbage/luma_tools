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
import copy
import uuid
import logging
import argparse

logger = logging.getLogger(__name__)

# Import shared utilities. client.py is workstation-only — never copied to
# farm — so the bare `comfyui.*` import is intentional.
from comfyui.utils import (
    check_server_health,
    wait_for_server,
    submit_workflow,
    wait_for_completion,
    modify_workflow_seed,
    collect_input_images,
    copy_inputs_to_server,
)


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
        logger.error(f"Workflow not found: {args.workflow}")
        sys.exit(1)

    # Load workflow
    logger.info(f"Loading workflow: {args.workflow}")
    with open(args.workflow, 'r', encoding='utf-8') as f:
        base_workflow = json.load(f)

    workflow_dir = os.path.dirname(os.path.abspath(args.workflow))

    # Load seeds if provided
    seeds_data = None
    if args.seeds_file:
        if not os.path.exists(args.seeds_file):
            logger.error(f"Seeds file not found: {args.seeds_file}")
            sys.exit(1)

        with open(args.seeds_file, 'r', encoding='utf-8') as f:
            seeds_data = json.load(f)

    # Determine frames to process
    if args.batch and seeds_data:
        frames = list(range(1, len(seeds_data.get('seeds', [])) + 1))
        logger.info(f"Batch mode: {len(frames)} frames to process")
    else:
        frames = [args.frame]

    # Wait for server to be ready
    if not wait_for_server(server_url=args.server_url, timeout=args.wait_for_server):
        logger.error("Server not available")
        sys.exit(1)

    # Collect and copy input images
    input_images = collect_input_images(base_workflow, workflow_dir)
    if input_images and args.server_input_dir:
        logger.info(f"Copying {len(input_images)} input image(s) to server...")
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
                logger.error(f"Frame {frame_num} out of range")
                failed += 1
                continue

            seed = seeds_data['seeds'][frame_idx]
            output_prefix = f"{args.output_prefix}_gen{frame_num:02d}"
            logger.info(f"Frame {frame_num}: seed={seed}, prefix={output_prefix}")
            workflow = modify_workflow_seed(workflow, seed, output_prefix)
        else:
            output_prefix = args.output_prefix
            workflow = modify_workflow_seed(workflow, 12345, output_prefix)

        # Submit and wait — share client_id for WebSocket event routing
        frame_client_id = str(uuid.uuid4())
        prompt_id = submit_workflow(workflow, server_url=args.server_url, client_id=frame_client_id)
        if not prompt_id:
            logger.error(f"Failed to submit frame {frame_num}")
            failed += 1
            continue

        success = wait_for_completion(prompt_id, server_url=args.server_url, timeout=args.timeout, client_id=frame_client_id)
        if success:
            successful += 1
        else:
            failed += 1

    # Summary
    total = len(frames)
    logger.info(f"{'='*40}")
    logger.info(f"Complete: {successful}/{total} successful, {failed} failed")
    logger.info(f"{'='*40}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
