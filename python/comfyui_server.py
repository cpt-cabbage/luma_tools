"""
ComfyUI Persistent Server Script.

Keeps ComfyUI running with models loaded in memory to avoid reload time.
Run this script on a farm node to maintain a persistent ComfyUI instance
that can receive workflow submissions from Deadline jobs.

Features:
- Starts ComfyUI once and keeps it running
- Models stay loaded in GPU memory
- HTTP API for job submission and status
- Graceful shutdown on SIGTERM
- Heartbeat endpoint for health checks
- Queue status monitoring

Usage:
    python comfyui_server.py --comfyui-path "C:/ComfyUI" --port 8188

The server exposes these endpoints (proxied from ComfyUI):
    GET  /health          - Server health check
    GET  /system_stats    - ComfyUI system stats
    POST /prompt          - Submit workflow
    GET  /queue           - Queue status
    GET  /history/{id}    - Execution history
"""

import sys
import os
import json
import time
import signal
import argparse
import threading
import subprocess
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime


# Server state
server_state = {
    'comfyui_process': None,
    'comfyui_port': 8188,
    'start_time': None,
    'jobs_completed': 0,
    'jobs_failed': 0,
    'is_ready': False,
    'last_health_check': None,
    'shutdown_requested': False,
    'cache_models': False,
    'cache_dir': None,
    'comfyui_path': None,
}


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks and status."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            self._handle_health()
        elif self.path == '/status':
            self._handle_status()
        else:
            self.send_error(404, 'Not Found')

    def _handle_health(self):
        """Return health status."""
        if server_state['is_ready']:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                'status': 'healthy',
                'uptime_seconds': int(time.time() - server_state['start_time']) if server_state['start_time'] else 0,
                'jobs_completed': server_state['jobs_completed'],
                'jobs_failed': server_state['jobs_failed'],
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'not_ready'}).encode())

    def _handle_status(self):
        """Return detailed status."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        uptime = int(time.time() - server_state['start_time']) if server_state['start_time'] else 0

        response = {
            'is_ready': server_state['is_ready'],
            'comfyui_port': server_state['comfyui_port'],
            'uptime_seconds': uptime,
            'uptime_human': format_uptime(uptime),
            'jobs_completed': server_state['jobs_completed'],
            'jobs_failed': server_state['jobs_failed'],
            'start_time': server_state['start_time'],
            'last_health_check': server_state['last_health_check'],
        }
        self.wfile.write(json.dumps(response, default=str).encode())


def format_uptime(seconds: int) -> str:
    """Format uptime in human-readable form."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)


def wait_for_comfyui(port: int, timeout: int = 300) -> bool:
    """Wait for ComfyUI server to be ready."""
    url = f"http://127.0.0.1:{port}/system_stats"
    start_time = time.time()
    last_status = ""

    print(f"Waiting for ComfyUI to start on port {port}...")

    while time.time() - start_time < timeout:
        if server_state['shutdown_requested']:
            return False

        try:
            req = urllib.request.urlopen(url, timeout=5)
            if req.status == 200:
                elapsed = int(time.time() - start_time)
                print(f"ComfyUI ready after {elapsed}s")
                return True
        except urllib.error.URLError as e:
            elapsed = int(time.time() - start_time)
            status = f"Waiting... ({elapsed}s)"
            if status != last_status:
                print(status)
                last_status = status
        except Exception as e:
            print(f"Error checking ComfyUI: {e}")

        time.sleep(2)

    print(f"Timeout waiting for ComfyUI after {timeout}s")
    return False


def check_comfyui_health(port: int) -> bool:
    """Check if ComfyUI is still healthy."""
    url = f"http://127.0.0.1:{port}/system_stats"
    try:
        req = urllib.request.urlopen(url, timeout=10)
        return req.status == 200
    except Exception:
        return False


def health_monitor_thread(port: int):
    """Background thread to monitor ComfyUI health."""
    while not server_state['shutdown_requested']:
        time.sleep(30)  # Check every 30 seconds

        if server_state['is_ready']:
            healthy = check_comfyui_health(port)
            server_state['last_health_check'] = datetime.now().isoformat()

            if not healthy:
                print("WARNING: ComfyUI health check failed!")
                # Check if process is still alive
                if server_state['comfyui_process']:
                    ret = server_state['comfyui_process'].poll()
                    if ret is not None:
                        print(f"ERROR: ComfyUI process died with exit code {ret}")
                        server_state['is_ready'] = False


def check_comfyui_dependencies(python_exe: str, comfyui_path: str) -> tuple:
    """Check if required ComfyUI packages are installed.

    Args:
        python_exe: Path to Python executable
        comfyui_path: Path to ComfyUI installation

    Returns:
        Tuple of (success: bool, missing_packages: list, error_message: str)
    """
    # Required packages for ComfyUI 0.3.27+
    required_packages = [
        'comfyui-frontend-package',
    ]

    missing = []
    for package in required_packages:
        try:
            # Use pip show to check if package is installed
            result = subprocess.run(
                [python_exe, '-m', 'pip', 'show', package],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                missing.append(package)
        except Exception:
            missing.append(package)

    if missing:
        requirements_path = os.path.join(comfyui_path, 'requirements.txt')
        error_msg = (
            f"Missing required ComfyUI packages: {', '.join(missing)}\n\n"
            f"Since ComfyUI v0.3.27+, the frontend is distributed as separate pip packages.\n\n"
            f"To fix, run one of the following:\n\n"
            f"  Option 1 - Install all requirements:\n"
            f"    {python_exe} -m pip install -r \"{requirements_path}\"\n\n"
            f"  Option 2 - Install specific packages:\n"
            f"    {python_exe} -m pip install {' '.join(missing)}"
        )
        return False, missing, error_msg

    return True, [], ""


def start_comfyui(comfyui_path: str, port: int, extra_args: list = None,
                  mode: str = "embedded", python_path: str = None,
                  skip_dep_check: bool = False) -> subprocess.Popen:
    """Start ComfyUI process.

    Args:
        comfyui_path: Path to ComfyUI installation
        port: Port for ComfyUI server
        extra_args: Additional command line arguments
        mode: 'embedded' for portable install, 'portable' for venv-based install
              (e.g., comfy-cli), 'standalone' for system install
        python_path: Path to Python executable (required for standalone mode)
        skip_dep_check: Skip dependency check (useful for embedded mode)
    """
    if mode == "embedded":
        # Embedded/portable mode: python_embeded folder alongside ComfyUI
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
        main_py = os.path.join(comfyui_path, "ComfyUI", "main.py")
    elif mode == "portable":
        # Portable mode: venv-based install from various installers
        # Check for different venv and main.py locations used by different installers
        venv_locations = [
            os.path.join(comfyui_path, "venv", "Scripts", "python.exe"),  # comfy-cli
            os.path.join(comfyui_path, ".venv", "Scripts", "python.exe"),  # some installers use .venv
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
            # Default to venv if none found (will error later with helpful message)
            python_exe = venv_locations[0]

        main_py = None
        for main_path in main_py_locations:
            if os.path.exists(main_path):
                main_py = main_path
                break
        if not main_py:
            main_py = main_py_locations[0]
    else:
        # Standalone mode: use provided Python path
        if not python_path:
            raise ValueError("Python path required for standalone mode")
        python_exe = python_path
        main_py = os.path.join(comfyui_path, "main.py")

    if not os.path.exists(python_exe):
        raise FileNotFoundError(f"Python not found: {python_exe}")

    if not os.path.exists(main_py):
        raise FileNotFoundError(f"ComfyUI main.py not found: {main_py}")

    # Check dependencies for standalone mode (embedded typically has everything bundled)
    if mode == "standalone" and not skip_dep_check:
        print("Checking ComfyUI dependencies...")
        success, missing, error_msg = check_comfyui_dependencies(python_exe, comfyui_path)
        if not success:
            raise RuntimeError(error_msg)

    cmd = [
        python_exe,
        main_py,
        '--port', str(port),
        '--disable-auto-launch',
    ]

    if extra_args:
        cmd.extend(extra_args)

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


def stream_comfyui_output(process: subprocess.Popen):
    """Stream ComfyUI output to console and detect model loads for caching."""
    # Track models being loaded for background caching
    current_model_path = None

    try:
        for line in process.stdout:
            line = line.rstrip()
            if line:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] [ComfyUI] {line}", flush=True)

                # Track job completion
                if "Prompt executed in" in line:
                    server_state['jobs_completed'] += 1
                    # After job completes, cache any models that were loaded
                    if server_state.get('cache_models') and current_model_path:
                        trigger_background_cache(current_model_path)
                        current_model_path = None

                elif "Error" in line and "node" in line.lower():
                    server_state['jobs_failed'] += 1

                # Detect model loading - cache it after job completes
                # ComfyUI logs like: "Loading model from: /path/to/model.safetensors"
                elif "Loading" in line and ("model" in line.lower() or "checkpoint" in line.lower()):
                    # Try to extract path from common log formats
                    if ":" in line:
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            potential_path = parts[1].strip()
                            if os.path.exists(potential_path):
                                current_model_path = potential_path

    except Exception as e:
        print(f"Output stream error: {e}")
    finally:
        ret = process.poll()
        if ret is not None:
            print(f"ComfyUI process exited with code {ret}")
            server_state['is_ready'] = False


def trigger_background_cache(model_path: str):
    """Trigger background caching of a model after job completion."""
    cache_dir = server_state.get('cache_dir')
    if not cache_dir:
        return

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, script_dir)
        from comfyui_model_cache import cache_model_background

        print(f"Triggering background cache for: {os.path.basename(model_path)}")
        cache_model_background(model_path, cache_dir)

    except ImportError:
        pass
    except Exception as e:
        print(f"Background cache trigger failed: {e}")


def setup_lazy_model_cache(comfyui_path: str, cache_dir: str = None) -> str:
    """
    Set up lazy model caching for the server.

    Creates a config that tells ComfyUI to:
    1. Check local cache first (fast if model is there from previous job)
    2. Fall back to network if not cached

    Returns:
        Path to extra_model_paths.yaml config, or None if setup failed
    """
    if cache_dir is None:
        import os as os_module
        cache_dir = os_module.path.join(
            os_module.environ.get('TEMP', 'C:/temp'),
            'comfyui_model_cache'
        )

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, script_dir)
        from comfyui_model_cache import setup_model_cache_for_comfyui

        print(f"\n{'='*60}")
        print("Model Cache: Setting up lazy caching for server")
        print(f"Cache dir: {cache_dir}")
        print("First load uses network, cached for subsequent loads")
        print(f"{'='*60}")

        config_path = setup_model_cache_for_comfyui(comfyui_path, cache_dir)
        return config_path

    except ImportError:
        print("Model caching module not available")
        return None
    except Exception as e:
        print(f"Model cache setup failed: {e}")
        return None


def shutdown(signum=None, frame=None):
    """Graceful shutdown handler."""
    print("\nShutdown requested...")
    server_state['shutdown_requested'] = True

    if server_state['comfyui_process']:
        print("Terminating ComfyUI...")
        server_state['comfyui_process'].terminate()
        try:
            server_state['comfyui_process'].wait(timeout=30)
            print("ComfyUI terminated gracefully")
        except subprocess.TimeoutExpired:
            print("Force killing ComfyUI...")
            server_state['comfyui_process'].kill()

    print("Server shutdown complete")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='Persistent ComfyUI Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Start server with default settings
    python comfyui_server.py --comfyui-path "C:/ComfyUI"

    # Start on custom port with extra model paths
    python comfyui_server.py --comfyui-path "C:/ComfyUI" --port 8189 \\
        --extra-model-paths "D:/models"

    # Run with specific input/output directories
    python comfyui_server.py --comfyui-path "C:/ComfyUI" \\
        --input-directory "W:/project/inputs" \\
        --output-directory "W:/project/outputs"
        """
    )

    parser.add_argument('--comfyui-path', required=True,
                        help='Path to ComfyUI installation')
    parser.add_argument('--port', type=int, default=8188,
                        help='Port for ComfyUI server (default: 8188)')
    parser.add_argument('--health-port', type=int, default=None,
                        help='Port for health check server (default: ComfyUI port + 1000)')
    parser.add_argument('--input-directory', default=None,
                        help='Default input directory for ComfyUI')
    parser.add_argument('--output-directory', default=None,
                        help='Default output directory for ComfyUI')
    parser.add_argument('--extra-model-paths', default=None,
                        help='Extra model paths config file')
    parser.add_argument('--cache-models', action='store_true',
                        help='Enable lazy model caching (cache first, network fallback)')
    parser.add_argument('--cache-dir', default=None,
                        help='Local directory for model cache (default: TEMP/comfyui_model_cache)')
    parser.add_argument('--lowvram', action='store_true',
                        help='Enable low VRAM mode')
    parser.add_argument('--gpu-only', action='store_true',
                        help='Run everything on GPU')
    parser.add_argument('--mode', choices=['embedded', 'portable', 'standalone'], default='embedded',
                        help='ComfyUI installation mode: embedded (python_embeded), portable (venv), or standalone')
    parser.add_argument('--python-path', default=None,
                        help='Path to Python executable (required for standalone mode)')
    parser.add_argument('--skip-dep-check', action='store_true',
                        help='Skip dependency check for standalone mode')

    args = parser.parse_args()

    # Setup signal handlers
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Build extra args for ComfyUI
    extra_args = []
    if args.input_directory:
        extra_args.extend(['--input-directory', args.input_directory])
    if args.output_directory:
        extra_args.extend(['--output-directory', args.output_directory])

    # Set up lazy model caching if requested
    # This generates a config that checks local cache first, then network
    # Also stores settings in server_state for background caching after jobs
    model_cache_config = None
    if args.cache_models:
        cache_dir = args.cache_dir or os.path.join(
            os.environ.get('TEMP', 'C:/temp'),
            'comfyui_model_cache'
        )
        model_cache_config = setup_lazy_model_cache(args.comfyui_path, cache_dir)

        # Store in server_state for background caching after each job
        server_state['cache_models'] = True
        server_state['cache_dir'] = cache_dir
        server_state['comfyui_path'] = args.comfyui_path
        if model_cache_config:
            extra_args.extend(['--extra-model-paths-config', model_cache_config])
    elif args.extra_model_paths:
        extra_args.extend(['--extra-model-paths-config', args.extra_model_paths])

    if args.lowvram:
        extra_args.append('--lowvram')
    if args.gpu_only:
        extra_args.append('--gpu-only')

    # Validate standalone mode requirements
    if args.mode == "standalone" and not args.python_path:
        print("ERROR: --python-path is required for standalone mode")
        sys.exit(1)

    # Initialize state
    server_state['comfyui_port'] = args.port
    server_state['start_time'] = time.time()

    print("=" * 60)
    print("ComfyUI Persistent Server")
    print("=" * 60)
    print(f"ComfyUI Path: {args.comfyui_path}")
    print(f"ComfyUI Port: {args.port}")
    print(f"Mode: {args.mode}")
    if args.mode == "standalone":
        print(f"Python Path: {args.python_path}")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # Start ComfyUI
    try:
        process = start_comfyui(
            args.comfyui_path, args.port, extra_args,
            mode=args.mode, python_path=args.python_path,
            skip_dep_check=args.skip_dep_check
        )
        server_state['comfyui_process'] = process
    except Exception as e:
        print(f"ERROR: Failed to start ComfyUI: {e}")
        sys.exit(1)

    # Start output streaming thread
    output_thread = threading.Thread(target=stream_comfyui_output, args=(process,), daemon=True)
    output_thread.start()

    # Wait for ComfyUI to be ready
    if not wait_for_comfyui(args.port, timeout=3000):
        print("ERROR: ComfyUI failed to start")
        shutdown()
        sys.exit(1)

    server_state['is_ready'] = True
    print("\n" + "=" * 60)
    print("SERVER READY")
    print(f"ComfyUI API: http://127.0.0.1:{args.port}")
    print("=" * 60 + "\n")

    # Start health monitor
    health_thread = threading.Thread(target=health_monitor_thread, args=(args.port,), daemon=True)
    health_thread.start()

    # Start health check HTTP server (optional)
    health_port = args.health_port or (args.port + 1000)
    try:
        health_server = HTTPServer(('0.0.0.0', health_port), HealthCheckHandler)
        health_server_thread = threading.Thread(target=health_server.serve_forever, daemon=True)
        health_server_thread.start()
        print(f"Health check endpoint: http://0.0.0.0:{health_port}/health")
    except Exception as e:
        print(f"Warning: Could not start health check server on port {health_port}: {e}")

    # Keep main thread alive, monitoring process health
    try:
        while not server_state['shutdown_requested']:
            # Check if ComfyUI process is still alive
            ret = process.poll()
            if ret is not None:
                print(f"ERROR: ComfyUI process exited unexpectedly with code {ret}")
                server_state['is_ready'] = False

                # Optionally restart ComfyUI here
                print("Server will exit. Use a process manager to restart if needed.")
                break

            time.sleep(5)

    except KeyboardInterrupt:
        pass

    shutdown()


if __name__ == '__main__':
    main()
