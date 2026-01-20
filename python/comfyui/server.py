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
"""

import sys
import os

# Add parent directory to path when run directly (must be before comfyui imports)
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

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

# Import shared utilities
from comfyui.utils import check_server_health, wait_for_server


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
    'restart_requested': False,
    'startup_config': None,
    'crash_count': 0,
    'last_crash_time': None,
    'max_crash_restarts': 5,
    'crash_cooldown_seconds': 60,
}


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks and status."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/health':
            self._handle_health()
        elif self.path == '/status':
            self._handle_status()
        else:
            self.send_error(404, 'Not Found')

    def do_POST(self):
        if self.path == '/restart':
            self._handle_restart()
        else:
            self.send_error(404, 'Not Found')

    def _handle_restart(self):
        print("\n" + "=" * 60)
        print("RESTART REQUESTED via API")
        print("=" * 60)
        server_state['restart_requested'] = True

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        response = {
            'status': 'restart_initiated',
            'message': 'ComfyUI restart has been initiated.',
        }
        self.wfile.write(json.dumps(response).encode())

    def _handle_health(self):
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
            'crash_count': server_state['crash_count'],
            'last_crash_time': server_state['last_crash_time'],
            'max_crash_restarts': server_state['max_crash_restarts'],
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
        except urllib.error.URLError:
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


def health_monitor_thread(port: int):
    """Background thread to monitor ComfyUI health."""
    consecutive_failures = 0
    max_consecutive_failures = 2  # Trigger restart after 2 consecutive failures (was 3)

    while not server_state['shutdown_requested']:
        time.sleep(20)  # Check more frequently (was 30s)

        if server_state['is_ready']:
            healthy = check_server_health(port=port)
            server_state['last_health_check'] = datetime.now().isoformat()

            if healthy:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                print(f"WARNING: ComfyUI health check failed ({consecutive_failures}/{max_consecutive_failures})")

                if server_state['comfyui_process']:
                    ret = server_state['comfyui_process'].poll()
                    if ret is not None:
                        print(f"ERROR: ComfyUI process died with exit code {ret}")
                        server_state['is_ready'] = False
                        # Main loop will handle crash recovery
                    elif consecutive_failures >= max_consecutive_failures:
                        # Process is running but not responding - request restart
                        print("ComfyUI unresponsive after multiple health checks, requesting restart...")
                        server_state['restart_requested'] = True
                        consecutive_failures = 0


def check_comfyui_dependencies(python_exe: str, comfyui_path: str) -> tuple:
    """Check if required ComfyUI packages are installed."""
    required_packages = ['comfyui-frontend-package']

    missing = []
    for package in required_packages:
        try:
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
            f"To fix, run:\n"
            f"  {python_exe} -m pip install -r \"{requirements_path}\"\n"
        )
        return False, missing, error_msg

    return True, [], ""


def start_comfyui(comfyui_path: str, port: int, extra_args: list = None,
                  mode: str = "embedded", python_path: str = None,
                  skip_dep_check: bool = False) -> subprocess.Popen:
    """Start ComfyUI process."""
    if mode == "embedded":
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
        main_py = os.path.join(comfyui_path, "ComfyUI", "main.py")
    elif mode == "portable":
        venv_locations = [
            os.path.join(comfyui_path, "venv", "Scripts", "python.exe"),
            os.path.join(comfyui_path, ".venv", "Scripts", "python.exe"),
        ]
        main_py_locations = [
            os.path.join(comfyui_path, "ComfyUI", "main.py"),
        ]

        python_exe = next((p for p in venv_locations if os.path.exists(p)), venv_locations[0])
        main_py = next((p for p in main_py_locations if os.path.exists(p)), main_py_locations[0])
    else:
        if not python_path:
            raise ValueError("Python path required for standalone mode")
        python_exe = python_path
        main_py = os.path.join(comfyui_path, "main.py")

    if not os.path.exists(python_exe):
        raise FileNotFoundError(f"Python not found: {python_exe}")
    if not os.path.exists(main_py):
        raise FileNotFoundError(f"ComfyUI main.py not found: {main_py}")

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

    working_dir = os.path.dirname(main_py)

    print(f"Starting ComfyUI ({mode} mode): {' '.join(cmd)}")
    print(f"Working directory: {working_dir}")

    # Set up environment with UTF-8 encoding for proper Unicode handling
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',  # Replace invalid characters instead of crashing
        bufsize=1,
        cwd=working_dir,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )

    return process


# Fatal error patterns that require server restart
FATAL_ERROR_PATTERNS = [
    'CUDA error: an illegal memory access',
    'CUDA error: out of memory',
    'torch.AcceleratorError',
    'CUDA error: device-side assert',
    'CUDA error: unspecified launch failure',
    'RuntimeError: CUDA',
    'CUBLAS_STATUS_EXECUTION_FAILED',
    'CUDNN_STATUS_EXECUTION_FAILED',
    'NCCL error',
]


def stream_comfyui_output(process: subprocess.Popen):
    """Stream ComfyUI output to console."""
    try:
        for line in process.stdout:
            line = line.rstrip()
            if line:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] [ComfyUI] {line}", flush=True)

                if "Prompt executed in" in line:
                    server_state['jobs_completed'] += 1
                elif "Error" in line and "node" in line.lower():
                    server_state['jobs_failed'] += 1

                # Check for fatal CUDA/GPU errors that require restart
                for pattern in FATAL_ERROR_PATTERNS:
                    if pattern in line:
                        print(f"\n{'!' * 60}")
                        print(f"FATAL GPU ERROR DETECTED: {pattern}")
                        print(f"Requesting immediate server restart...")
                        print(f"{'!' * 60}\n")
                        server_state['jobs_failed'] += 1
                        server_state['restart_requested'] = True
                        server_state['is_ready'] = False  # Mark as not ready immediately
                        # Fatal error detected, server is in bad state
                        break

    except Exception as e:
        print(f"Output stream error: {e}")
    finally:
        ret = process.poll()
        if ret is not None:
            print(f"ComfyUI process exited with code {ret}")
            server_state['is_ready'] = False


def restart_comfyui(reason: str = "manual"):
    """Restart the ComfyUI process using stored startup config.

    Args:
        reason: Why the restart is happening (manual, crash, health_check)
    """
    config = server_state.get('startup_config')
    if not config:
        print("ERROR: No startup config available for restart")
        return False

    print("\n" + "=" * 60)
    print(f"RESTARTING COMFYUI (reason: {reason})")
    print("=" * 60)

    server_state['is_ready'] = False
    server_state['restart_requested'] = False

    if server_state['comfyui_process']:
        print("Terminating existing ComfyUI process...")
        server_state['comfyui_process'].terminate()
        try:
            server_state['comfyui_process'].wait(timeout=30)
            print("ComfyUI terminated gracefully")
        except subprocess.TimeoutExpired:
            print("Force killing ComfyUI...")
            server_state['comfyui_process'].kill()
            server_state['comfyui_process'].wait()

    time.sleep(2)

    try:
        process = start_comfyui(
            config['comfyui_path'],
            config['port'],
            config['extra_args'],
            mode=config['mode'],
            python_path=config['python_path'],
            skip_dep_check=True
        )
        server_state['comfyui_process'] = process
        server_state['start_time'] = time.time()

        output_thread = threading.Thread(target=stream_comfyui_output, args=(process,), daemon=True)
        output_thread.start()

        if wait_for_comfyui(config['port'], timeout=300):
            server_state['is_ready'] = True
            print("\n" + "=" * 60)
            print("COMFYUI RESTART COMPLETE")
            print(f"ComfyUI API: http://127.0.0.1:{config['port']}")
            print("=" * 60 + "\n")
            return True
        else:
            print("ERROR: ComfyUI failed to restart")
            return False

    except Exception as e:
        print(f"ERROR: Failed to restart ComfyUI: {e}")
        return False


def handle_crash_recovery(exit_code: int) -> bool:
    """Handle ComfyUI crash with automatic recovery.

    Args:
        exit_code: The exit code from the crashed process

    Returns:
        True if recovery was successful, False if we should give up
    """
    server_state['crash_count'] += 1
    server_state['last_crash_time'] = datetime.now().isoformat()

    print("\n" + "!" * 60)
    print(f"COMFYUI CRASHED (exit code: {exit_code})")
    print(f"Crash count: {server_state['crash_count']}/{server_state['max_crash_restarts']}")
    print("!" * 60)

    # Check if crash recovery is disabled
    if server_state['max_crash_restarts'] <= 0:
        print("Crash recovery is disabled. Server will exit.")
        return False

    # Check if we've exceeded max restarts
    if server_state['crash_count'] > server_state['max_crash_restarts']:
        print(f"ERROR: Exceeded maximum crash restarts ({server_state['max_crash_restarts']})")
        print("Server will exit. Manual intervention required.")
        return False

    # Apply cooldown between restarts to avoid rapid restart loops
    cooldown = server_state['crash_cooldown_seconds']
    print(f"Waiting {cooldown}s before restart attempt...")

    # Wait for cooldown, but check for shutdown during wait
    cooldown_start = time.time()
    while time.time() - cooldown_start < cooldown:
        if server_state['shutdown_requested']:
            return False
        time.sleep(1)

    # Attempt restart
    print(f"Attempting automatic restart ({server_state['crash_count']}/{server_state['max_crash_restarts']})...")

    if restart_comfyui(reason="crash"):
        print("Crash recovery successful!")
        return True
    else:
        print("ERROR: Crash recovery failed")
        # Don't increment crash count again since restart_comfyui handles its own failures
        return False


def reset_crash_counter():
    """Reset crash counter after successful uptime period.

    Called when ComfyUI has been running stably to reset the crash counter,
    allowing the server to handle future crashes.
    """
    if server_state['crash_count'] > 0:
        print(f"Resetting crash counter (was {server_state['crash_count']})")
        server_state['crash_count'] = 0


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


def load_global_settings() -> dict:
    """Load global settings to get default values for server flags."""
    try:
        # Try to find global_settings.json in common locations
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Try relative path from script location (../../global_settings/global_settings.json)
        possible_paths = [
            os.path.join(script_dir, '..', '..', 'global_settings', 'global_settings.json'),
            r'L:\tools\_studio_tools\luma_tools\global_settings\global_settings.json',
            # Fallback to home directory settings
            os.path.join(os.path.expanduser("~"), ".luma_tools", "global_settings_path.txt"),
        ]

        for path in possible_paths:
            if path.endswith('global_settings_path.txt'):
                # Read the path from the file
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        settings_dir = f.read().strip()
                        settings_file = os.path.join(settings_dir, 'global_settings.json')
                        if os.path.exists(settings_file):
                            with open(settings_file, 'r') as sf:
                                return json.load(sf)
            elif os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)

        print("Warning: Could not find global_settings.json, using defaults")
        return {}
    except Exception as e:
        print(f"Warning: Error loading global settings: {e}")
        return {}


def main():
    # Load global settings to get default values
    global_settings = load_global_settings()

    parser = argparse.ArgumentParser(description='Persistent ComfyUI Server')

    parser.add_argument('--comfyui-path',
                        default=global_settings.get('comfyui_path'),
                        help='Path to ComfyUI installation (default from global settings)')
    parser.add_argument('--port', type=int, default=8188, help='Port for ComfyUI server')
    parser.add_argument('--health-port', type=int, default=None, help='Port for health check server')
    parser.add_argument('--input-directory', default=None, help='Default input directory')
    parser.add_argument('--output-directory', default=None, help='Default output directory')
    parser.add_argument('--extra-model-paths', default=None, help='Extra model paths config file')
    parser.add_argument('--lowvram', action='store_true',
                        default=global_settings.get('comfyui_lowvram', False),
                        help='Enable low VRAM mode (default from global settings)')
    parser.add_argument('--highvram', action='store_true',
                        default=global_settings.get('comfyui_highvram', False),
                        help='Keep models in VRAM (default from global settings)')
    parser.add_argument('--normalvram', action='store_true',
                        default=global_settings.get('comfyui_normalvram', False),
                        help='Use normal VRAM mode (default from global settings)')
    parser.add_argument('--disable-smart-memory', action='store_true',
                        default=global_settings.get('comfyui_disable_smart_memory', False),
                        help='Disable smart memory management to keep models loaded (default from global settings)')
    parser.add_argument('--gpu-only', action='store_true', help='Run everything on GPU')
    parser.add_argument('--fast', action='store_true',
                        default=global_settings.get('comfyui_fast_mode', False),
                        help='Enable --fast flag (default from global settings)')
    parser.add_argument('--mode', choices=['embedded', 'portable', 'standalone'],
                        default=global_settings.get('comfyui_mode', 'embedded'),
                        help='ComfyUI installation mode (default from global settings)')
    parser.add_argument('--python-path',
                        default=global_settings.get('comfyui_python_path'),
                        help='Path to Python executable (default from global settings)')
    parser.add_argument('--skip-dep-check', action='store_true', help='Skip dependency check')
    parser.add_argument('--max-crash-restarts', type=int, default=5,
                        help='Max automatic restart attempts after crash (default: 5, 0 to disable)')
    parser.add_argument('--crash-cooldown', type=int, default=60,
                        help='Seconds to wait between crash restarts (default: 60)')

    args = parser.parse_args()

    # Validate required arguments
    if not args.comfyui_path:
        print("ERROR: --comfyui-path is required (not found in command line or global settings)")
        sys.exit(1)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    extra_args = []
    if args.input_directory:
        extra_args.extend(['--input-directory', args.input_directory])
    if args.output_directory:
        extra_args.extend(['--output-directory', args.output_directory])
    if args.extra_model_paths:
        extra_args.extend(['--extra-model-paths-config', args.extra_model_paths])
    if args.lowvram:
        extra_args.append('--lowvram')
    if args.highvram:
        extra_args.append('--highvram')
    if args.normalvram:
        extra_args.append('--normalvram')
    if args.disable_smart_memory:
        extra_args.append('--disable-smart-memory')
    if args.gpu_only:
        extra_args.append('--gpu-only')
    if args.fast:
        extra_args.append('--fast')

    if args.mode == "standalone" and not args.python_path:
        print("ERROR: --python-path is required for standalone mode")
        sys.exit(1)

    server_state['comfyui_port'] = args.port
    server_state['start_time'] = time.time()
    server_state['max_crash_restarts'] = args.max_crash_restarts
    server_state['crash_cooldown_seconds'] = args.crash_cooldown

    print("=" * 60)
    print("ComfyUI Persistent Server")
    print("=" * 60)
    print(f"ComfyUI Path: {args.comfyui_path}")
    print(f"ComfyUI Port: {args.port}")
    print(f"Mode: {args.mode}")
    if args.mode == "standalone":
        print(f"Python Path: {args.python_path}")

    # Show performance flags
    flags_enabled = []
    if args.lowvram:
        flags_enabled.append("--lowvram")
    if args.highvram:
        flags_enabled.append("--highvram")
    if args.normalvram:
        flags_enabled.append("--normalvram")
    if args.disable_smart_memory:
        flags_enabled.append("--disable-smart-memory")
    if args.fast:
        flags_enabled.append("--fast")
    if args.gpu_only:
        flags_enabled.append("--gpu-only")
    if flags_enabled:
        print(f"Performance Flags: {', '.join(flags_enabled)}")

    if args.max_crash_restarts > 0:
        print(f"Crash Recovery: enabled (max {args.max_crash_restarts} restarts, {args.crash_cooldown}s cooldown)")
    else:
        print(f"Crash Recovery: disabled")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    server_state['startup_config'] = {
        'comfyui_path': args.comfyui_path,
        'port': args.port,
        'extra_args': extra_args,
        'mode': args.mode,
        'python_path': args.python_path,
    }

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

    output_thread = threading.Thread(target=stream_comfyui_output, args=(process,), daemon=True)
    output_thread.start()

    if not wait_for_comfyui(args.port, timeout=3000):
        print("ERROR: ComfyUI failed to start")
        shutdown()
        sys.exit(1)

    server_state['is_ready'] = True
    print("\n" + "=" * 60)
    print("SERVER READY")
    print(f"ComfyUI API: http://127.0.0.1:{args.port}")
    print("=" * 60 + "\n")

    health_thread = threading.Thread(target=health_monitor_thread, args=(args.port,), daemon=True)
    health_thread.start()

    health_port = args.health_port or (args.port + 1000)
    try:
        health_server = HTTPServer(('0.0.0.0', health_port), HealthCheckHandler)
        health_server_thread = threading.Thread(target=health_server.serve_forever, daemon=True)
        health_server_thread.start()
        print(f"Health check endpoint: http://0.0.0.0:{health_port}/health")
    except Exception as e:
        print(f"Warning: Could not start health check server on port {health_port}: {e}")

    # Track uptime for crash counter reset
    stable_uptime_threshold = 300  # Reset crash counter after 5 min stable uptime
    last_stable_check = time.time()

    try:
        while not server_state['shutdown_requested']:
            # Handle restart requests (from fatal errors or health checks)
            if server_state['restart_requested']:
                reason = "fatal_error" if not server_state['is_ready'] else "health_check"
                if restart_comfyui(reason=reason):
                    process = server_state['comfyui_process']
                    last_stable_check = time.time()
                else:
                    print("ERROR: Restart failed, server will exit")
                    break

            ret = process.poll()
            if ret is not None:
                # ComfyUI crashed or exited unexpectedly
                server_state['is_ready'] = False

                if handle_crash_recovery(ret):
                    # Recovery successful, update process reference
                    process = server_state['comfyui_process']
                    last_stable_check = time.time()
                else:
                    # Recovery failed or max retries exceeded
                    print("ERROR: Crash recovery failed, server will exit")
                    break

            # Reset crash counter after stable uptime period
            if server_state['is_ready'] and server_state['crash_count'] > 0:
                if time.time() - last_stable_check > stable_uptime_threshold:
                    reset_crash_counter()
                    last_stable_check = time.time()

            time.sleep(2)  # Check more frequently (was 5s)

    except KeyboardInterrupt:
        pass

    shutdown()


if __name__ == '__main__':
    main()
