"""
ComfyUI Runner Script.

Submits workflows to ComfyUI via API and waits for completion.
This script is designed to be run on Deadline farm workers.

Connects to a persistent ComfyUI server (managed by server.py) that keeps
models loaded in GPU memory between job submissions for fast execution.
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
import uuid
import argparse
import signal
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
        has_output_suffix_nodes,
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
        has_output_suffix_nodes,
    )

# Try to use centralized utilities, fall back to local implementations for farm execution
try:
    from core.logging_utils import setup_file_logging as _setup_file_logging
    _USE_CENTRAL_LOGGING = True
except ImportError:
    _USE_CENTRAL_LOGGING = False

# Try to import image conversion (available when running with full package)
try:
    from comfyui.image_convert import needs_conversion, copy_or_convert
    _HAS_IMAGE_CONVERT = True
except ImportError:
    _HAS_IMAGE_CONVERT = False


# =============================================================================
# LOGGING SETUP - Uses centralized module when available, falls back for farm
# =============================================================================

def setup_logging(job_name: str = None, network_output_dir: str = None) -> str:
    """Set up file logging by redirecting stdout/stderr to also write to a log file.

    Logs are written to the network path from global settings
    (network_output_path/_logs/) for accessibility from all machines.
    Falls back to the job output directory, then ~/.luma_tools/logs/.

    Args:
        job_name: Optional job name for log filename
        network_output_dir: Optional network directory to write log (fallback)

    Returns:
        Path to the log file
    """
    # Use centralized logging module when available
    if _USE_CENTRAL_LOGGING:
        # Build log prefix from job name
        if job_name:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_name)
            log_prefix = f"comfyui_runner_{safe_name}"
        else:
            log_prefix = "comfyui_runner"

        return _setup_file_logging(
            log_prefix=log_prefix,
            subdirectory="runner",
            include_hostname=False,
            include_username=False,
            redirect_stdout=True,
            tee_mode="writer",
            fallback_dir=network_output_dir
        )

    # Fallback for standalone farm execution when core module unavailable
    return _setup_logging_fallback(job_name, network_output_dir)


def _setup_logging_fallback(job_name: str = None, network_output_dir: str = None) -> str:
    """Fallback logging setup when centralized module is unavailable (farm execution)."""

    # Local TeeWriter implementation
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

    def get_network_log_dir_local(subdirectory: str = "runner") -> str:
        """Get network log directory from global settings."""
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
                    network_path = settings.get('network_output_path', '')
                    if network_path and os.path.isdir(network_path):
                        log_dir = os.path.join(network_path, '_logs', subdirectory)
                        os.makedirs(log_dir, exist_ok=True)
                        return log_dir
                    break
        except Exception:
            pass
        return None

    # Determine log directory
    log_dir = get_network_log_dir_local("runner")

    if not log_dir and network_output_dir and os.path.isdir(network_output_dir):
        log_dir = os.path.join(network_output_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)

    if not log_dir:
        log_dir = os.path.join(os.path.expanduser("~"), ".luma_tools", "logs")
        os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if job_name:
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

    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.stream = sys.stderr

    logger.info(f"Log file: {log_path}")
    return log_path


# =============================================================================
# SERVER RESTART SUPPORT
# =============================================================================

def signal_server_restart(port: int, health_port: int = None, lowvram: bool = False) -> bool:
    """Signal the persistent ComfyUI server to perform a full restart.

    Args:
        port: ComfyUI server port.
        health_port: Health check server port (defaults to port + 1000).
        lowvram: If True, request server restart with --lowvram for this one restart.
    """
    import urllib.request
    import urllib.error

    if health_port is None:
        health_port = port + 1000

    url = f"http://127.0.0.1:{health_port}/restart"
    logger.info(f"\n{'='*60}")
    logger.info("SIGNALING SERVER RESTART")
    if lowvram:
        logger.info("  with --lowvram override")
    logger.info(f"Sending restart request to {url}")
    logger.info(f"{'='*60}")

    try:
        body = None
        headers = {}
        if lowvram:
            body = json.dumps({"lowvram": True}).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=body, method='POST', headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
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
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    elapsed = int(time.time() - start_time)
                    logger.info(f"Server restart complete after {elapsed}s")
                    return True
        except (urllib.error.URLError, OSError):
            pass  # Server not ready yet
        time.sleep(2)

    logger.error(f"Timeout waiting for server restart after {timeout}s")
    return False


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
    parser.add_argument('--comfyui-output-dir', help='ComfyUI default output directory (for moving 3D files)')
    parser.add_argument('--full-restart', action='store_true', help='Force full server restart between jobs')
    parser.add_argument('--restart-lowvram', action='store_true', help='Restart server with --lowvram (only used with --full-restart)')
    parser.add_argument('--server-not-found', choices=['fail', 'wait'], default='fail',
                        help='Behavior when server not found')
    parser.add_argument('--server-wait-timeout', type=int, default=300,
                        help='Timeout when waiting for server to start')

    # Deprecated args - kept for backward compat with in-flight Deadline jobs
    parser.add_argument('--persistent', action='store_true', help='(deprecated, always persistent)')
    parser.add_argument('--mode', choices=['embedded', 'portable', 'standalone'], default='embedded',
                       help='(deprecated, server manages ComfyUI process)')
    parser.add_argument('--python-path', help='(deprecated, server manages ComfyUI process)')
    parser.add_argument('--lowvram', action='store_true', help='(deprecated, server manages VRAM)')

    args = parser.parse_args()

    setup_logging(args.output_prefix, args.output_directory)

    # Verify workflow exists
    if not os.path.exists(args.workflow):
        logger.error(f"Workflow file not found: {args.workflow}")
        sys.exit(1)

    # Load workflow
    logger.info(f"Loading workflow from: {args.workflow}")
    with open(args.workflow, 'r', encoding='utf-8') as f:
        base_workflow = json.load(f)

    # Check if workflow uses _output suffix convention for primary output designation
    use_strict_prefix = has_output_suffix_nodes(base_workflow)
    if use_strict_prefix:
        logger.info("Workflow uses _output suffix - only designated output files will be moved")

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

    # Connect to persistent server
    logger.info(f"Connecting to persistent server on port {args.port}...")

    # Copy input images to ComfyUI's default input directory FIRST
    # This must happen before restart to ensure files are present
    # Some ComfyUI nodes ignore the server's configured input directory
    # and always look in the hardcoded default location
    images_to_upload = get_workflow_images(base_workflow)
    logger.debug(f"Found {len(images_to_upload) if images_to_upload else 0} images in workflow: {images_to_upload}")
    logger.debug(f"args.comfyui_path = {args.comfyui_path}")
    logger.debug(f"args.input_directory = {args.input_directory}")
    if images_to_upload:
        comfyui_input_dir = os.path.join(args.comfyui_path, "ComfyUI", "input")
        if os.path.isdir(comfyui_input_dir):
            logger.info(f"\nCopying {len(images_to_upload)} input image(s) to ComfyUI input directory...")
            for image_name in images_to_upload:
                src_path = os.path.join(args.input_directory, image_name)
                if os.path.exists(src_path):
                    try:
                        if _HAS_IMAGE_CONVERT and needs_conversion(src_path):
                            result = copy_or_convert(src_path, comfyui_input_dir)
                            if result:
                                logger.info(f"  Converted: {image_name} -> {os.path.basename(result)}")
                            else:
                                shutil.copy2(src_path, os.path.join(comfyui_input_dir, image_name))
                                logger.info(f"  Copied (conversion failed): {image_name}")
                        else:
                            dst_path = os.path.join(comfyui_input_dir, image_name)
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
        if signal_server_restart(args.port, lowvram=args.restart_lowvram):
            if not wait_for_server_restart(args.port, timeout=300):
                logger.error("Server restart failed")
                sys.exit(1)
            # Re-copy images after restart in case they were cleared
            if images_to_upload and os.path.isdir(comfyui_input_dir):
                logger.info(f"\nRe-copying {len(images_to_upload)} input image(s) after restart...")
                for image_name in images_to_upload:
                    src_path = os.path.join(args.input_directory, image_name)
                    if os.path.exists(src_path):
                        try:
                            if _HAS_IMAGE_CONVERT and needs_conversion(src_path):
                                copy_or_convert(src_path, comfyui_input_dir)
                            else:
                                dst_path = os.path.join(comfyui_input_dir, image_name)
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

    logger.info(f"Connected to server on port {args.port}")

    # Also upload via HTTP API as backup method
    logger.info("\nUploading input images to server via HTTP...")
    for image_name in images_to_upload:
        image_path = os.path.join(args.input_directory, image_name)
        if os.path.exists(image_path):
            if not upload_image_to_server(image_path, port=args.port):
                logger.warning(f"HTTP upload failed for {image_name} (but direct copy may have succeeded)")
        else:
            logger.warning(f"Image not found locally: {image_path}")

    # Cleanup handler
    def cleanup(signum=None, frame=None, exit_code=None):
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
        frame_results = []

        for i, (frame_num, workflow) in enumerate(workflows_to_run, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing generation {i}/{total_frames} (frame {frame_num})")
            logger.info(f"{'='*60}")

            # Track timing for per-file metadata
            frame_start_time = time.time()

            # Generate client_id for WebSocket event routing — ComfyUI sends
            # execution events (executing, executed) only to the client that
            # submitted the prompt, so both submit and wait must share the same ID.
            frame_client_id = str(uuid.uuid4())

            prompt_id = submit_workflow(workflow, port=args.port, client_id=frame_client_id)
            if not prompt_id:
                logger.error(f"Failed to submit workflow for frame {frame_num}")
                failed += 1
                continue

            download_dir = args.output_directory

            def on_image_output(img, base_url, output_dir):
                download_image_from_server(
                    img.get('filename', ''),
                    img.get('subfolder', ''),
                    img.get('type', 'output'),
                    server_url=base_url,
                    output_dir=output_dir
                )

            completion_result = wait_for_completion(
                prompt_id, port=args.port, timeout=args.timeout,
                output_dir=download_dir, on_image_output=on_image_output,
                track_node_timing=True, client_id=frame_client_id,
                workflow_dict=workflow
            )

            # Handle both dict result (with timing) and bool result (fallback)
            if isinstance(completion_result, dict):
                success = completion_result.get('success', False)
                node_execution_trace = completion_result.get('node_timing', [])
                total_duration_ms = completion_result.get('total_duration_ms')
            else:
                success = completion_result
                node_execution_trace = []
                total_duration_ms = None

            if success:
                # Calculate execution time
                frame_end_time = time.time()
                execution_time_ms = int((frame_end_time - frame_start_time) * 1000)

                logger.info(f"Frame {frame_num} completed successfully in {execution_time_ms}ms")
                successful += 1

                # Get the actual seed used for this frame
                actual_seed = None
                try:
                    # Extract seed from workflow - check common node types
                    for node_id, node_data in workflow.items():
                        if isinstance(node_data, dict):
                            inputs = node_data.get('inputs', {})
                            if 'seed' in inputs:
                                actual_seed = inputs['seed']
                                break
                            if 'noise_seed' in inputs:
                                actual_seed = inputs['noise_seed']
                                break
                except Exception as e:
                    logger.debug(f"Could not extract seed from workflow: {e}")

                moved = []
                if args.comfyui_output_dir:
                    moved = move_output_files(
                        args.comfyui_output_dir,
                        args.output_directory,
                        args.output_prefix,
                        recent_minutes=30,
                        strict_prefix=use_strict_prefix
                    )
                    if moved:
                        logger.info(f"Moved {len(moved)} output file(s)")

                # Store per-file metadata for each output file
                try:
                    from comfyui.metadata import add_per_file_metadata
                except ImportError:
                    # Farm execution - try local import
                    add_per_file_metadata = None

                # Try to import file hashing (available with full package)
                _compute_hash = None
                try:
                    from comfyui.utils import compute_file_hash as _compute_hash
                except ImportError:
                    try:
                        from comfyui_utils import compute_file_hash as _compute_hash
                    except (ImportError, AttributeError):
                        pass  # Hashing not available on this farm worker

                if add_per_file_metadata and moved:
                    for dest_path in moved:
                        try:
                            filename = os.path.basename(dest_path)
                            # Use server-reported total_duration_ms if available, else our measured time
                            file_execution_time = total_duration_ms if total_duration_ms else execution_time_ms
                            # Compute content hash for the output file
                            file_hash = None
                            if _compute_hash:
                                try:
                                    file_hash = _compute_hash(dest_path)
                                except Exception:
                                    pass
                            add_per_file_metadata(
                                output_dir=args.output_directory,
                                filename=filename,
                                frame_index=frame_num,
                                actual_seed=actual_seed,
                                execution_time_ms=file_execution_time,
                                node_execution_trace=node_execution_trace,
                                content_hash=file_hash,
                            )
                        except Exception:
                            pass  # Silently skip metadata storage failures

                # Collect frame result for analytics
                frame_results.append({
                    "frame_num": frame_num,
                    "success": True,
                    "execution_time_ms": total_duration_ms if total_duration_ms else execution_time_ms,
                    "node_timing": node_execution_trace or [],
                })
            else:
                logger.error(f"Frame {frame_num} failed or timed out")
                failed += 1
                frame_results.append({
                    "frame_num": frame_num,
                    "success": False,
                })

        logger.info(f"\n{'='*60}")
        logger.info(f"BATCH COMPLETE: {successful}/{total_frames} successful, {failed} failed")
        logger.info(f"{'='*60}")

        # Record execution analytics
        try:
            try:
                from comfyui.analytics import record_execution, aggregate_node_timing
            except ImportError:
                from comfyui_analytics import record_execution, aggregate_node_timing

            record_execution(
                output_directory=args.output_directory,
                workflow_file=args.workflow,
                output_prefix=args.output_prefix,
                total_frames=total_frames,
                successful=successful,
                failed=failed,
                frame_results=frame_results,
            )
            aggregate_node_timing()
        except ImportError:
            logger.debug("Analytics module not available, skipping")
        except Exception as e:
            logger.warning(f"Analytics recording failed (non-fatal): {e}")

        # Auto-establish lineage relationships based on source images
        try:
            from comfyui.metadata import auto_establish_lineage_from_job_metadata
            lineage_count = auto_establish_lineage_from_job_metadata(args.output_directory)
            if lineage_count > 0:
                logger.info(f"Established {lineage_count} lineage relationship(s)")
        except ImportError:
            logger.debug("Could not import lineage function (running on farm)")
        except Exception as e:
            logger.warning(f"Could not establish lineage: {e}")

        exit_code = 0 if failed == 0 else 1
        cleanup(exit_code=exit_code)

    except Exception as e:
        logger.error(f"Error: {e}")
        cleanup(exit_code=1)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
    main()
