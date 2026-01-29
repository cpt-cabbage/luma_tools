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

Logs are written to the network path from global settings (_logs/ subdirectory)
for accessibility from all machines, falling back to ~/.luma_tools/logs/.
"""

import sys
import os

# Ensure script directory is in path for standalone farm execution
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import json
import time
import copy
import subprocess
import argparse
import signal
import threading
import shutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Import shared utilities
# Try package import first (for development), fall back to local file (for farm execution)
try:
    from comfyui.utils import (
        WEBSOCKET_AVAILABLE,
        check_server_health,
        wait_for_server,
        submit_workflow,
        wait_for_completion,
        modify_workflow_seed,
        upload_image_to_server,
        download_image_from_server,
        move_output_files,
        get_workflow_images,
        resolve_comfyui_paths,
    )
except ImportError:
    # When running standalone on farm, import from copied utils file
    from comfyui_utils import (
        WEBSOCKET_AVAILABLE,
        check_server_health,
        wait_for_server,
        submit_workflow,
        wait_for_completion,
        modify_workflow_seed,
        upload_image_to_server,
        download_image_from_server,
        move_output_files,
        get_workflow_images,
        resolve_comfyui_paths,
    )

# Try to use centralized logging utilities, fall back to local implementations for farm execution
try:
    from core.logging_utils import TeeWriter, get_network_log_dir, get_local_log_dir
    _USE_CENTRAL_LOGGING = True
except ImportError:
    _USE_CENTRAL_LOGGING = False


# =============================================================================
# LOGGING SETUP - Uses centralized module when available, falls back for farm
# =============================================================================

if not _USE_CENTRAL_LOGGING:
    # Local fallback implementations for standalone farm execution

    class TeeWriter:
        """Writes to both the original stream and a log file."""

        def __init__(self, original_stream, log_file):
            self.original_stream = original_stream
            self.log_file = log_file

        def write(self, message):
            self.original_stream.write(message)
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

    def get_network_log_dir(subdirectory: str = "runner") -> str:
        """Get network log directory from global settings (fallback for farm)."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            settings_paths = [
                os.path.join(script_dir, '..', '..', 'global_settings', 'global_settings.json'),
                r'L:\tools\_studio_tools\luma_tools\global_settings\global_settings.json',
            ]
            for settings_path in settings_paths:
                norm_path = os.path.normpath(settings_path)
                if os.path.exists(norm_path):
                    with open(norm_path, 'r') as f:
                        settings = json.load(f)
                    network_path = settings.get('comfyui_network_output_path', '')
                    if network_path and os.path.isdir(network_path):
                        log_dir = os.path.join(network_path, '_logs', subdirectory)
                        os.makedirs(log_dir, exist_ok=True)
                        return log_dir
                    break
        except Exception:
            pass
        return None

    def get_local_log_dir() -> str:
        """Get local fallback log directory."""
        log_dir = os.path.join(os.path.expanduser("~"), ".luma_tools", "logs")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir


def setup_logging(job_name: str = None, network_output_dir: str = None) -> str:
    """Set up file logging by redirecting stdout/stderr to also write to a log file.

    Logs are written to the network path from global settings
    (comfyui_network_output_path/_logs/) for accessibility from all machines.
    Falls back to the job output directory, then ~/.luma_tools/logs/.

    Args:
        job_name: Optional job name for log filename
        network_output_dir: Optional network directory to write log (fallback)

    Returns:
        Path to the log file
    """
    # Primary: network log directory from global settings
    log_dir = get_network_log_dir("runner")

    # Fallback: job output directory (also network-accessible)
    if not log_dir and network_output_dir and os.path.isdir(network_output_dir):
        log_dir = network_output_dir

    # Last resort: local user directory
    if not log_dir:
        log_dir = get_local_log_dir()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if job_name:
        # Don't truncate - UUIDs can be longer than 50 chars
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_name)
        log_filename = f"comfyui_runner_{safe_name}_{timestamp}.log"
    else:
        log_filename = f"comfyui_runner_{timestamp}.log"

    log_path = os.path.join(log_dir, log_filename)
    log_file = open(log_path, 'w', encoding='utf-8')

    log_file.write(f"{'='*60}\n")
    log_file.write(f"ComfyUI Runner Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_file.write(f"{'='*60}\n\n")
    log_file.flush()

    sys.stdout = TeeWriter(sys.__stdout__, log_file)
    sys.stderr = TeeWriter(sys.__stderr__, log_file)

    # Update the logging module's StreamHandler to use the tee'd stderr
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.stream = sys.stderr  # Now points to TeeWriter

    logger.info(f"Log file: {log_path}")
    return log_path


# =============================================================================
# SERVER RESTART SUPPORT
# =============================================================================

def signal_server_restart(port: int, health_port: int = None) -> bool:
    """Signal the persistent ComfyUI server to perform a full restart."""
    import urllib.request
    import urllib.error

    if health_port is None:
        health_port = port + 1000

    url = f"http://127.0.0.1:{health_port}/restart"
    logger.info(f"\n{'='*60}")
    logger.info("SIGNALING SERVER RESTART")
    logger.info(f"Sending restart request to {url}")
    logger.info(f"{'='*60}")

    try:
        req = urllib.request.Request(url, method='POST')
        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode('utf-8'))
        logger.info(f"Restart response: {result.get('message', 'OK')}")
        return True
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP Error {e.code}: {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Error signaling restart: {e}")
        return False


def wait_for_server_restart(port: int, timeout: int = 300) -> bool:
    """Wait for server to complete restart and become ready again."""
    import urllib.request

    url = f"http://127.0.0.1:{port}/system_stats"
    start_time = time.time()

    logger.info("Waiting for server to restart...")
    down_detected = False
    while time.time() - start_time < 30:
        try:
            urllib.request.urlopen(url, timeout=2)
            time.sleep(0.5)
        except (urllib.error.URLError, OSError):
            down_detected = True
            break

    if not down_detected:
        logger.warning("Server may not have restarted (still responding)")

    logger.info("Waiting for server to become ready...")
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.urlopen(url, timeout=5)
            if req.status == 200:
                elapsed = int(time.time() - start_time)
                logger.info(f"Server restart complete after {elapsed}s")
                return True
        except (urllib.error.URLError, OSError):
            pass  # Server not ready yet
        time.sleep(2)

    logger.error(f"Timeout waiting for server restart after {timeout}s")
    return False


# =============================================================================
# COMFYUI PROCESS MANAGEMENT
# =============================================================================

def start_comfyui_server(comfyui_path: str, input_dir: str, output_dir: str, port: int,
                         mode: str = "embedded", python_path: str = None, lowvram: bool = False) -> subprocess.Popen:
    """Start ComfyUI server process."""
    try:
        python_exe, main_py = resolve_comfyui_paths(comfyui_path, mode, python_path)
    except ValueError as e:
        logger.error(f"{e}")
        return None

    cmd = [
        python_exe,
        main_py,
        '--input-directory', input_dir,
        '--output-directory', output_dir,
        '--port', str(port),
        '--disable-auto-launch'
    ]

    if lowvram:
        cmd.append('--lowvram')

    working_dir = os.path.dirname(main_py)

    logger.info(f"Starting ComfyUI ({mode} mode): {' '.join(cmd)}")
    logger.info(f"Working directory: {working_dir}")

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
                logger.info(f"[ComfyUI] {line}")
                if "Error" in line or "Exception" in line or "CUDA out of memory" in line:
                    logger.warning(f"ComfyUI error detected: {line}")
    except Exception as e:
        logger.error(f"Output stream error: {e}")
    finally:
        ret = process.poll()
        if ret is not None:
            logger.info(f"ComfyUI process exited with code {ret}")
            if ret != 0:
                process_died.set()


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Run ComfyUI workflow')
    parser.add_argument('--comfyui-path', required=True, help='Path to ComfyUI installation')
    parser.add_argument('--workflow', required=True, help='Path to workflow JSON file')
    parser.add_argument('--input-directory', required=True, help='Input image directory')
    parser.add_argument('--output-directory', required=True, help='Output directory')
    parser.add_argument('--port', type=int, default=8188, help='Port for ComfyUI server')
    parser.add_argument('--timeout', type=int, default=3600, help='Execution timeout in seconds')
    parser.add_argument('--frame', type=int, default=1, help='Frame/generation number (1-based)')
    parser.add_argument('--seeds-file', help='Path to JSON file with seeds for each frame')
    parser.add_argument('--output-prefix', default='comfyui_output', help='Base output filename prefix')
    parser.add_argument('--batch', action='store_true', help='Process all generations in a single session')
    parser.add_argument('--persistent', action='store_true', help='Keep server running between jobs')
    parser.add_argument('--mode', choices=['embedded', 'portable', 'standalone'], default='embedded',
                       help='ComfyUI installation mode')
    parser.add_argument('--python-path', help='Path to Python executable (for standalone mode)')
    parser.add_argument('--comfyui-output-dir', help='ComfyUI default output directory (for moving 3D files)')
    parser.add_argument('--full-restart', action='store_true', help='Force full server restart between jobs')
    parser.add_argument('--server-not-found', choices=['fail', 'wait'], default='fail',
                       help='Behavior when server not found in persistent mode')
    parser.add_argument('--server-wait-timeout', type=int, default=300,
                       help='Timeout when waiting for server to start')
    parser.add_argument('--lowvram', action='store_true', help='Enable low VRAM mode')

    args = parser.parse_args()

    setup_logging(args.output_prefix, args.output_directory)

    # Determine paths based on mode (using centralized path resolution)
    try:
        python_exe, main_py = resolve_comfyui_paths(args.comfyui_path, args.mode, args.python_path)
    except ValueError as e:
        logger.error(f"{e}")
        sys.exit(1)

    # Verify paths
    if not os.path.exists(python_exe):
        logger.error(f"Python executable not found: {python_exe}")
        sys.exit(1)
    if not os.path.exists(main_py):
        logger.error(f"ComfyUI main.py not found: {main_py}")
        sys.exit(1)
    if not os.path.exists(args.workflow):
        logger.error(f"Workflow file not found: {args.workflow}")
        sys.exit(1)

    # Load workflow
    logger.info(f"Loading workflow from: {args.workflow}")
    with open(args.workflow, 'r', encoding='utf-8') as f:
        base_workflow = json.load(f)

    # Load seeds
    seeds_data = None
    if args.seeds_file:
        if not os.path.exists(args.seeds_file):
            logger.error(f"Seeds file not found: {args.seeds_file}")
            sys.exit(1)
        with open(args.seeds_file, 'r', encoding='utf-8') as f:
            seeds_data = json.load(f)

    # Determine frames to process
    if args.batch and seeds_data:
        frames_to_process = list(range(1, len(seeds_data.get('seeds', [])) + 1))
        logger.info(f"Batch mode: Processing {len(frames_to_process)} generations")
    else:
        frames_to_process = [args.frame]

    # Prepare workflows
    workflows_to_run = []
    for frame_num in frames_to_process:
        workflow = copy.deepcopy(base_workflow)
        if seeds_data:
            frame_index = frame_num - 1
            if frame_index < 0 or frame_index >= len(seeds_data.get('seeds', [])):
                logger.error(f"Frame {frame_num} out of range")
                sys.exit(1)
            seed = seeds_data['seeds'][frame_index]
            output_prefix = f"{args.output_prefix}_gen{frame_num:02d}"
            logger.info(f"Frame {frame_num}: Using seed {seed}, output prefix: {output_prefix}")
            workflow = modify_workflow_seed(workflow, seed, output_prefix)
        workflows_to_run.append((frame_num, workflow))

    # Server management
    process = None
    process_died = threading.Event()
    server_started_by_us = False

    if args.persistent:
        logger.info(f"Persistent mode: connecting to server on port {args.port}...")

        # Copy input images to ComfyUI's default input directory FIRST
        # This must happen before restart to ensure files are present
        # Some ComfyUI nodes ignore the server's configured input directory
        # and always look in the hardcoded default location
        images_to_upload = get_workflow_images(base_workflow)
        logger.info(f"DEBUG: Found {len(images_to_upload) if images_to_upload else 0} images in workflow: {images_to_upload}")
        logger.info(f"DEBUG: args.comfyui_path = {args.comfyui_path}")
        logger.info(f"DEBUG: args.input_directory = {args.input_directory}")
        if images_to_upload:
            comfyui_input_dir = os.path.join(args.comfyui_path, "ComfyUI", "input")
            if os.path.isdir(comfyui_input_dir):
                logger.info(f"\nCopying {len(images_to_upload)} input image(s) to ComfyUI input directory...")
                for image_name in images_to_upload:
                    src_path = os.path.join(args.input_directory, image_name)
                    dst_path = os.path.join(comfyui_input_dir, image_name)
                    if os.path.exists(src_path):
                        try:
                            shutil.copy2(src_path, dst_path)
                            logger.info(f"  Copied: {image_name} -> {comfyui_input_dir}")
                        except Exception as e:
                            logger.warning(f"Failed to copy {image_name}: {e}")
                    else:
                        logger.warning(f"Image not found: {src_path}")
            else:
                logger.warning(f"ComfyUI input directory not found: {comfyui_input_dir}")

        if args.full_restart:
            logger.info("\nFull restart requested")
            if signal_server_restart(args.port):
                if not wait_for_server_restart(args.port, timeout=300):
                    logger.error("Server restart failed")
                    sys.exit(1)
                # Re-copy images after restart in case they were cleared
                if images_to_upload and os.path.isdir(comfyui_input_dir):
                    logger.info(f"\nRe-copying {len(images_to_upload)} input image(s) after restart...")
                    for image_name in images_to_upload:
                        src_path = os.path.join(args.input_directory, image_name)
                        dst_path = os.path.join(comfyui_input_dir, image_name)
                        if os.path.exists(src_path):
                            try:
                                shutil.copy2(src_path, dst_path)
                                logger.info(f"  Copied: {image_name} -> {comfyui_input_dir}")
                            except Exception as e:
                                logger.warning(f"Failed to copy {image_name}: {e}")
            else:
                logger.warning("Could not signal server restart, continuing...")

        if not check_server_health(port=args.port):
            if args.server_not_found == 'wait':
                logger.info(f"Server not found - waiting up to {args.server_wait_timeout}s...")
                if not wait_for_server(port=args.port, timeout=args.server_wait_timeout):
                    logger.error(f"Server did not start within timeout")
                    sys.exit(1)
            else:
                logger.error(f"No ComfyUI server found on port {args.port}")
                sys.exit(1)

        logger.info(f"Connected to existing server on port {args.port}")

        # Also upload via HTTP API as backup method
        logger.info("\nUploading input images to server via HTTP...")
        for image_name in images_to_upload:
            image_path = os.path.join(args.input_directory, image_name)
            if os.path.exists(image_path):
                if not upload_image_to_server(image_path, port=args.port):
                    logger.warning(f"HTTP upload failed for {image_name} (but direct copy may have succeeded)")
            else:
                logger.warning(f"Image not found locally: {image_path}")
    else:
        # Copy input images to ComfyUI's default input directory
        # Some ComfyUI nodes ignore --input-directory and use hardcoded paths
        images_to_copy = get_workflow_images(base_workflow)
        if images_to_copy:
            comfyui_input_dir = os.path.join(args.comfyui_path, "ComfyUI", "input")
            if os.path.isdir(comfyui_input_dir):
                logger.info(f"\nCopying {len(images_to_copy)} input image(s) to ComfyUI input directory...")
                for image_name in images_to_copy:
                    src_path = os.path.join(args.input_directory, image_name)
                    dst_path = os.path.join(comfyui_input_dir, image_name)
                    if os.path.exists(src_path):
                        try:
                            shutil.copy2(src_path, dst_path)
                            logger.info(f"  Copied: {image_name} -> {comfyui_input_dir}")
                        except Exception as e:
                            logger.warning(f"Failed to copy {image_name}: {e}")
                    else:
                        logger.warning(f"Image not found: {src_path}")
            else:
                logger.warning(f"ComfyUI input directory not found: {comfyui_input_dir}")

        process = start_comfyui_server(
            args.comfyui_path,
            args.input_directory,
            args.output_directory,
            args.port,
            mode=args.mode,
            python_path=args.python_path,
            lowvram=args.lowvram
        )
        if process is None:
            logger.error("Failed to start ComfyUI server")
            sys.exit(1)
        server_started_by_us = True

        output_thread = threading.Thread(target=stream_output, args=(process, process_died), daemon=True)
        output_thread.start()

        if not wait_for_server(port=args.port, timeout=120):
            logger.error("Failed to start ComfyUI server")
            process.terminate()
            sys.exit(1)

    # Cleanup handler
    def cleanup(signum=None, frame=None, exit_code=None):
        if server_started_by_us and process:
            logger.info("Cleaning up - shutting down server...")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        elif args.persistent:
            logger.info("Persistent mode - server stays running")

        if signum is not None:
            sys.exit(1)
        elif exit_code is not None:
            sys.exit(exit_code)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Process workflows
    try:
        total_frames = len(workflows_to_run)
        successful = 0
        failed = 0

        for i, (frame_num, workflow) in enumerate(workflows_to_run, 1):
            if process and process.poll() is not None:
                logger.error(f"ComfyUI process died (exit code: {process.returncode})")
                failed += (total_frames - i + 1)
                break

            if process_died.is_set():
                logger.error("ComfyUI process crashed")
                failed += (total_frames - i + 1)
                break

            logger.info(f"\n{'='*60}")
            logger.info(f"Processing generation {i}/{total_frames} (frame {frame_num})")
            logger.info(f"{'='*60}")

            prompt_id = submit_workflow(workflow, port=args.port)
            if not prompt_id:
                logger.error(f"Failed to submit workflow for frame {frame_num}")
                if process and process.poll() is not None:
                    failed += (total_frames - i + 1)
                    break
                failed += 1
                continue

            download_dir = args.output_directory if args.persistent else None

            def on_image_output(img, base_url, output_dir):
                download_image_from_server(
                    img.get('filename', ''),
                    img.get('subfolder', ''),
                    img.get('type', 'output'),
                    server_url=base_url,
                    output_dir=output_dir
                )

            success = wait_for_completion(
                prompt_id, port=args.port, timeout=args.timeout,
                output_dir=download_dir, on_image_output=on_image_output if download_dir else None
            )

            if process and process.poll() is not None:
                logger.error(f"ComfyUI crashed during generation")
                failed += (total_frames - i + 1)
                break

            if success:
                logger.info(f"Frame {frame_num} completed successfully")
                successful += 1

                if args.comfyui_output_dir:
                    logger.info(f"[Runner] Checking for output files to move")
                    moved = move_output_files(
                        args.comfyui_output_dir,
                        args.output_directory,
                        args.output_prefix,
                        recent_minutes=30
                    )
                    if moved:
                        logger.info(f"Moved {len(moved)} output file(s)")
            else:
                logger.error(f"Frame {frame_num} failed or timed out")
                failed += 1

        logger.info(f"\n{'='*60}")
        logger.info(f"BATCH COMPLETE: {successful}/{total_frames} successful, {failed} failed")
        logger.info(f"{'='*60}")

        exit_code = 0 if failed == 0 else 1
        cleanup(exit_code=exit_code)

    except Exception as e:
        logger.error(f"Error: {e}")
        cleanup(exit_code=1)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
    main()
