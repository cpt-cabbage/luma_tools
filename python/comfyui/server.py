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

Logs are written to the network path from global settings (_logs/ subdirectory)
for accessibility from all machines, falling back to ~/.luma_tools/logs/.

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

import time
import signal
import argparse
import threading
import subprocess
import json
import logging
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from core.subprocess_utils import run_command, start_process
from core.utils import load_json, ensure_directory

logger = logging.getLogger(__name__)


class ThreadSafeState:
    """Thread-safe wrapper around a state dict.

    Provides locked access for all reads/writes and an atomic
    increment() method for counters (server_state is accessed from
    the main thread, health_monitor_thread, stream_comfyui_output,
    and HTTP handler threads simultaneously).
    """

    def __init__(self, initial_state: dict):
        self._state = dict(initial_state)
        self._lock = threading.RLock()

    def __getitem__(self, key):
        with self._lock:
            return self._state[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._state[key] = value

    def get(self, key, default=None):
        with self._lock:
            return self._state.get(key, default)

    def increment(self, key, amount=1):
        """Atomically increment a counter."""
        with self._lock:
            self._state[key] += amount
            return self._state[key]

    def snapshot(self):
        """Return a point-in-time copy of all state for consistent reads."""
        with self._lock:
            return dict(self._state)

    def test_and_clear(self, key: str) -> bool:
        """Atomically test a boolean flag and clear it.

        Returns True if the flag was set (and clears it), False otherwise.
        Prevents multiple threads from both acting on the same flag.
        """
        with self._lock:
            value = bool(self._state.get(key, False))
            if value:
                self._state[key] = False
            return value


def kill_process_on_port(port: int) -> bool:
    """Kill any process using the specified port (Windows only).

    Args:
        port: The port number to free up

    Returns:
        True if a process was killed, False otherwise
    """
    if os.name != 'nt':
        logger.warning("kill_process_on_port only implemented for Windows")
        return False

    try:
        # Find PID using the port
        result = run_command(['netstat', '-ano', '-p', 'TCP'])

        target_pids = set()
        for line in result.stdout.splitlines():
            if f':{port}' in line and ('LISTENING' in line or 'ESTABLISHED' in line):
                parts = line.split()
                if parts:
                    try:
                        pid = int(parts[-1])
                        if pid > 0:
                            target_pids.add(pid)
                    except ValueError:
                        continue

        if not target_pids:
            return False

        for pid in target_pids:
            try:
                logger.info(f"Killing process {pid} using port {port}")
                run_command(['taskkill', '/F', '/PID', str(pid)])
            except Exception as e:
                logger.warning(f"Failed to kill PID {pid}: {e}")

        # Wait a moment for the port to be released
        time.sleep(1)
        return True

    except Exception as e:
        logger.error(f"Error killing process on port {port}: {e}")
        return False

# Import shared utilities
from comfyui.utils import check_server_health, wait_for_server, resolve_comfyui_paths

# Try to use centralized logging utilities when available
try:
    from core.logging_utils import setup_file_logging as _setup_file_logging, get_network_log_dir, get_local_log_dir
    _USE_CENTRAL_LOGGING = True
except ImportError:
    _USE_CENTRAL_LOGGING = False


def setup_logging(global_settings: dict = None, log_dir_override: str = None) -> str:
    """Set up file logging for the persistent server.

    Writes logs to the network path from global settings
    (network_output_path/_logs/) for accessibility from all machines.

    Args:
        global_settings: Loaded global settings dict
        log_dir_override: Optional CLI override for log directory

    Returns:
        Path to the log file
    """
    # Use centralized logging module when available
    if _USE_CENTRAL_LOGGING and not log_dir_override:
        return _setup_file_logging(
            log_prefix="comfyui_server",
            subdirectory="server",
            include_hostname=True,
            include_username=False,
            redirect_stdout=False,
            tee_mode="handlers"
        )

    # Fallback to local implementation
    import socket
    hostname = socket.gethostname()

    # Determine log directory
    log_dir = None

    # CLI override
    if log_dir_override and os.path.isdir(log_dir_override):
        log_dir = log_dir_override

    # From global settings network path
    if not log_dir and global_settings:
        network_path = global_settings.get('network_output_path', '')
        if network_path and os.path.isdir(network_path):
            log_dir = os.path.join(network_path, '_logs', 'server')
            ensure_directory(log_dir)

    # Last resort: local user directory
    if not log_dir:
        log_dir = os.path.join(os.path.expanduser("~"), ".luma_tools", "logs")
        ensure_directory(log_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"comfyui_server_{hostname}_{timestamp}.log"
    log_path = os.path.join(log_dir, log_filename)

    # Configure root logger with both file and console handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers from basicConfig
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler - network-accessible log
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.addHandler(file_handler)

    # Console handler - for terminal/Deadline output
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.addHandler(console_handler)

    logger.info(f"Log file: {log_path}")
    return log_path


# Server state — wrapped in ThreadSafeState for multi-thread access
server_state = ThreadSafeState({
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
    'self_restart_pending': False,  # Set when ComfyUI initiates its own restart
    'last_output_time': None,  # Timestamp of last stdout activity from ComfyUI
    'restart_lowvram_override': False,  # One-time --lowvram override for next restart (per-model)
})


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
        logger.info("\n" + "=" * 60)
        logger.info("RESTART REQUESTED via API")
        logger.info("=" * 60)

        # Parse optional JSON body for one-time overrides
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            try:
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))
                if data.get('lowvram'):
                    server_state['restart_lowvram_override'] = True
                    logger.info("Restart override: --lowvram enabled for this restart")
            except Exception as e:
                logger.warning(f"Could not parse restart request body: {e}")

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
        # Snapshot for consistent multi-value read across threads
        state = server_state.snapshot()
        if state['is_ready']:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                'status': 'healthy',
                'uptime_seconds': int(time.time() - state['start_time']) if state['start_time'] else 0,
                'jobs_completed': state['jobs_completed'],
                'jobs_failed': state['jobs_failed'],
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

        # Snapshot for consistent multi-value read across threads
        state = server_state.snapshot()
        uptime = int(time.time() - state['start_time']) if state['start_time'] else 0
        response = {
            'is_ready': state['is_ready'],
            'comfyui_port': state['comfyui_port'],
            'uptime_seconds': uptime,
            'uptime_human': format_uptime(uptime),
            'jobs_completed': state['jobs_completed'],
            'jobs_failed': state['jobs_failed'],
            'start_time': state['start_time'],
            'last_health_check': state['last_health_check'],
            'crash_count': state['crash_count'],
            'last_crash_time': state['last_crash_time'],
            'max_crash_restarts': state['max_crash_restarts'],
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

    logger.info(f"Waiting for ComfyUI to start on port {port}...")

    while time.time() - start_time < timeout:
        if server_state['shutdown_requested']:
            return False

        try:
            req = urllib.request.urlopen(url, timeout=5)
            if req.status == 200:
                elapsed = int(time.time() - start_time)
                logger.info(f"ComfyUI ready after {elapsed}s")
                return True
        except urllib.error.URLError:
            elapsed = int(time.time() - start_time)
            status = f"Waiting... ({elapsed}s)"
            if status != last_status:
                logger.info(status)
                last_status = status
        except Exception as e:
            logger.error(f"Error checking ComfyUI: {e}")

        time.sleep(2)

    logger.error(f"Timeout waiting for ComfyUI after {timeout}s")
    return False


def health_monitor_thread(port: int):
    """Background thread to monitor ComfyUI health."""
    consecutive_failures = 0
    max_consecutive_failures = 2  # Trigger restart after 2 consecutive failures
    activity_grace_period = 300  # Seconds — skip health check if ComfyUI produced output recently

    while not server_state['shutdown_requested']:
        time.sleep(20)

        # Snapshot for consistent multi-value read across threads
        state = server_state.snapshot()

        if state['is_ready']:
            # If ComfyUI has produced stdout output recently, it's alive and working.
            # Heavy operations (model loading, GPU inference) can block the HTTP
            # server from responding, causing false-positive health check failures.
            # Still perform occasional checks (every 2 min) to detect HTTP-specific failures.
            last_output = state.get('last_output_time')
            last_actual_check = state.get('last_actual_health_check', 0)
            if last_output and (time.time() - last_output) < activity_grace_period:
                if time.time() - last_actual_check < 120:
                    consecutive_failures = 0
                    server_state['last_health_check'] = datetime.now().isoformat()
                    continue

            server_state['last_actual_health_check'] = time.time()
            healthy = check_server_health(port=port)
            server_state['last_health_check'] = datetime.now().isoformat()

            if healthy:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logger.warning(f"ComfyUI health check failed ({consecutive_failures}/{max_consecutive_failures})")

                process = state['comfyui_process']
                if process:
                    ret = process.poll()
                    if ret is not None:
                        logger.error(f"ComfyUI process died with exit code {ret}")
                        server_state['is_ready'] = False
                        # Main loop will handle crash recovery
                    elif consecutive_failures >= max_consecutive_failures:
                        # Process is running but not responding - request restart
                        logger.warning("ComfyUI unresponsive after multiple health checks, requesting restart...")
                        server_state['restart_requested'] = True
                        consecutive_failures = 0


def check_comfyui_dependencies(python_exe: str, comfyui_path: str) -> tuple:
    """Check if required ComfyUI packages are installed."""
    required_packages = ['comfyui-frontend-package']

    missing = []
    for package in required_packages:
        try:
            result = run_command([python_exe, '-m', 'pip', 'show', package], timeout=30)
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
    # Use centralized path resolution
    python_exe, main_py = resolve_comfyui_paths(comfyui_path, mode, python_path)

    if not os.path.exists(python_exe):
        raise FileNotFoundError(f"Python not found: {python_exe}")
    if not os.path.exists(main_py):
        raise FileNotFoundError(f"ComfyUI main.py not found: {main_py}")

    if mode == "standalone" and not skip_dep_check:
        logger.info("Checking ComfyUI dependencies...")
        success, missing, error_msg = check_comfyui_dependencies(python_exe, comfyui_path)
        if not success:
            raise RuntimeError(error_msg)

    cmd = [
        python_exe,
        '-s',
        main_py,
        '--port', str(port),
        '--disable-auto-launch',
    ]

    # Embedded mode uses ComfyUI's bundled Python and expects this flag
    # (matches the included run_nvidia_gpu.bat / run_cpu.bat behavior)
    if mode == "embedded":
        cmd.append('--windows-standalone-build')

    if extra_args:
        cmd.extend(extra_args)

    working_dir = os.path.dirname(main_py)

    logger.info(f"Starting ComfyUI ({mode} mode): {' '.join(cmd)}")
    logger.info(f"Working directory: {working_dir}")

    # Set up clean environment to avoid interference with ComfyUI's embedded Python
    env = os.environ.copy()

    # Remove Python-related variables that could cause package conflicts
    # when server.py is launched from a different Python environment
    python_vars_to_remove = [
        'PYTHONPATH',      # Can cause wrong packages to be imported
        'PYTHONHOME',      # Can override Python installation location
        'VIRTUAL_ENV',     # Indicates venv is active
        'CONDA_PREFIX',    # Conda environment path
        'CONDA_DEFAULT_ENV',  # Conda environment name
        'CONDA_SHLVL',     # Conda shell level
        'PYTHONSTARTUP',   # Python startup script
        'PYTHONEXECUTABLE',  # Override Python executable
    ]

    removed_vars = []
    for var in python_vars_to_remove:
        if var in env:
            del env[var]
            removed_vars.append(var)

    if removed_vars:
        logger.debug(f"Cleaned environment variables: {', '.join(removed_vars)}")

    # Set UTF-8 encoding for proper Unicode handling
    env['PYTHONIOENCODING'] = 'utf-8'

    process = start_process(cmd, cwd=working_dir, env=env, hide_window=False)

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
                logger.info(f"[ComfyUI] {line}")
                server_state['last_output_time'] = time.time()

                if "Prompt executed in" in line:
                    server_state.increment('jobs_completed')
                elif "Error" in line and "node" in line.lower():
                    server_state.increment('jobs_failed')

                # Detect ComfyUI self-restart (e.g., from Manager or internal restart)
                # This prevents treating exit code 0 as a crash
                if "Restarting" in line and ("Legacy Mode" in line or "restarting" in line.lower()):
                    logger.info("ComfyUI self-restart detected, will handle gracefully")
                    server_state['self_restart_pending'] = True

                # Check for fatal CUDA/GPU errors that require restart
                for pattern in FATAL_ERROR_PATTERNS:
                    if pattern in line:
                        logger.error(f"\n{'!' * 60}")
                        logger.error(f"FATAL GPU ERROR DETECTED: {pattern}")
                        logger.error(f"Requesting immediate server restart...")
                        logger.error(f"{'!' * 60}\n")
                        server_state.increment('jobs_failed')
                        server_state['restart_requested'] = True
                        server_state['is_ready'] = False  # Mark as not ready immediately
                        # Fatal error detected, server is in bad state
                        break

    except Exception as e:
        logger.error(f"Output stream error: {e}")
    finally:
        ret = process.poll()
        if ret is not None:
            logger.info(f"ComfyUI process exited with code {ret}")
            server_state['is_ready'] = False


def restart_comfyui(reason: str = "manual"):
    """Restart the ComfyUI process using stored startup config.

    Args:
        reason: Why the restart is happening (manual, crash, health_check)
    """
    config = server_state.get('startup_config')
    if not config:
        logger.error("No startup config available for restart")
        return False

    logger.info("\n" + "=" * 60)
    logger.info(f"RESTARTING COMFYUI (reason: {reason})")
    logger.info("=" * 60)

    server_state['is_ready'] = False
    server_state['restart_requested'] = False
    server_state['self_restart_pending'] = False

    # Apply one-time lowvram override if requested (per-model restart setting)
    extra_args = list(config['extra_args'])
    if server_state.get('restart_lowvram_override'):
        server_state['restart_lowvram_override'] = False
        for flag in ('--highvram', '--normalvram'):
            if flag in extra_args:
                extra_args.remove(flag)
        if '--lowvram' not in extra_args:
            extra_args.append('--lowvram')
        logger.info("Applying one-time --lowvram override for this restart")
    else:
        extra_args = config['extra_args']

    if server_state['comfyui_process']:
        logger.info("Terminating existing ComfyUI process...")
        server_state['comfyui_process'].terminate()
        try:
            server_state['comfyui_process'].wait(timeout=30)
            logger.info("ComfyUI terminated gracefully")
        except subprocess.TimeoutExpired:
            logger.warning("Force killing ComfyUI...")
            server_state['comfyui_process'].kill()
            try:
                server_state['comfyui_process'].wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.error("ComfyUI process did not exit after kill")

    # Also kill any orphaned processes on the port (from self-restarts)
    kill_process_on_port(config['port'])

    time.sleep(2)

    try:
        process = start_comfyui(
            config['comfyui_path'],
            config['port'],
            extra_args,
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
            logger.info("\n" + "=" * 60)
            logger.info("COMFYUI RESTART COMPLETE")
            logger.info(f"ComfyUI API: http://127.0.0.1:{config['port']}")
            logger.info("=" * 60 + "\n")

            # Refresh node definitions on network after restart
            _save_node_info_to_network(config['port'])

            return True
        else:
            logger.error("ComfyUI failed to restart")
            return False

    except Exception as e:
        logger.error(f"Failed to restart ComfyUI: {e}")
        return False


def handle_crash_recovery(exit_code: int) -> bool:
    """Handle ComfyUI crash with automatic recovery.

    Args:
        exit_code: The exit code from the crashed process

    Returns:
        True if recovery was successful, False if we should give up
    """
    server_state.increment('crash_count')
    server_state['last_crash_time'] = datetime.now().isoformat()

    logger.error("\n" + "!" * 60)
    logger.error(f"COMFYUI CRASHED (exit code: {exit_code})")
    logger.error(f"Crash count: {server_state['crash_count']}/{server_state['max_crash_restarts']}")
    logger.error("!" * 60)

    # Check if crash recovery is disabled
    if server_state['max_crash_restarts'] <= 0:
        logger.info("Crash recovery is disabled. Server will exit.")
        return False

    # Check if we've exceeded max restarts
    if server_state['crash_count'] > server_state['max_crash_restarts']:
        logger.error(f"Exceeded maximum crash restarts ({server_state['max_crash_restarts']})")
        logger.error("Server will exit. Manual intervention required.")
        return False

    # Apply cooldown between restarts to avoid rapid restart loops
    cooldown = server_state['crash_cooldown_seconds']
    logger.info(f"Waiting {cooldown}s before restart attempt...")

    # Wait for cooldown, but check for shutdown during wait
    cooldown_start = time.time()
    while time.time() - cooldown_start < cooldown:
        if server_state['shutdown_requested']:
            return False
        time.sleep(1)

    # Attempt restart
    logger.info(f"Attempting automatic restart ({server_state['crash_count']}/{server_state['max_crash_restarts']})...")

    if restart_comfyui(reason="crash"):
        logger.info("Crash recovery successful!")
        return True
    else:
        logger.error("Crash recovery failed")
        # Don't increment crash count again since restart_comfyui handles its own failures
        return False


def reset_crash_counter():
    """Reset crash counter after successful uptime period.

    Called when ComfyUI has been running stably to reset the crash counter,
    allowing the server to handle future crashes.
    """
    if server_state['crash_count'] > 0:
        logger.info(f"Resetting crash counter (was {server_state['crash_count']})")
        server_state['crash_count'] = 0


def shutdown(signum=None, frame=None):
    """Graceful shutdown handler."""
    logger.info("\nShutdown requested...")
    server_state['shutdown_requested'] = True

    config = server_state.get('startup_config', {})
    port = config.get('port', 8188)

    if server_state['comfyui_process']:
        logger.info("Terminating ComfyUI...")
        server_state['comfyui_process'].terminate()
        try:
            server_state['comfyui_process'].wait(timeout=30)
            logger.info("ComfyUI terminated gracefully")
        except subprocess.TimeoutExpired:
            logger.warning("Force killing ComfyUI...")
            server_state['comfyui_process'].kill()
            try:
                server_state['comfyui_process'].wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.error("ComfyUI process did not exit after kill")

    # Also kill any orphaned ComfyUI processes on the port
    # (e.g., from self-restarts where we lost the process handle)
    logger.info(f"Checking for orphaned processes on port {port}...")
    kill_process_on_port(port)

    logger.info("Server shutdown complete")
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
                        result = load_json(settings_file)
                        if result:
                            return result
            elif os.path.exists(path):
                return load_json(path, {})

        logger.warning("Could not find global_settings.json, using defaults")
        return {}
    except Exception as e:
        logger.warning(f"Error loading global settings: {e}")
        return {}


def _save_node_info_to_network(port: int, global_settings: dict = None):
    """Fetch /object_info from ComfyUI and save to network path.

    This makes node definitions available to all luma_tools instances
    on the network, so artist workstations don't need direct access
    to the ComfyUI server.
    """
    try:
        from comfyui.node_info import fetch_object_info, save_cache_to_network, _cache

        server_url = f"http://127.0.0.1:{port}"
        raw_data = fetch_object_info(server_url, timeout=60)
        if not raw_data:
            logger.warning("Failed to fetch /object_info for network cache")
            return

        count = _cache.update_from_server(raw_data)
        logger.info(f"Fetched {count} node definitions from ComfyUI")

        # Save to network path
        if global_settings is None:
            global_settings = load_global_settings()

        network_path = global_settings.get('network_output_path', '')
        if network_path and os.path.isdir(network_path):
            if save_cache_to_network(network_path):
                logger.info("Node info saved to network for all clients")
            else:
                logger.warning("Failed to save node info to network path")
        else:
            logger.warning(f"Network output path not available: {network_path}")

    except Exception as e:
        logger.error(f"Error saving node info to network: {e}")


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
                        help='Enable --fast fp16_accumulation (default from global settings)')
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
    parser.add_argument('--log-dir', default=None,
                        help='Override log directory (default: network path from global settings)')

    args = parser.parse_args()

    # Set up file logging to network path
    setup_logging(global_settings, args.log_dir)

    # Validate required arguments
    if not args.comfyui_path:
        logger.error("--comfyui-path is required (not found in command line or global settings)")
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
        # Pass --fast fp16_accumulation (NOT bare --fast which also enables
        # dynamic_vram/aimdo — that forces a custom mmap safetensors loader
        # that can't handle misaligned model files like t5-base.safetensors)
        extra_args.extend(['--fast', 'fp16_accumulation'])

    if args.mode == "standalone" and not args.python_path:
        logger.error("--python-path is required for standalone mode")
        sys.exit(1)

    server_state['comfyui_port'] = args.port
    server_state['start_time'] = time.time()
    server_state['max_crash_restarts'] = args.max_crash_restarts
    server_state['crash_cooldown_seconds'] = args.crash_cooldown

    logger.info("=" * 60)
    logger.info("ComfyUI Persistent Server")
    logger.info("=" * 60)
    logger.info(f"ComfyUI Path: {args.comfyui_path}")
    logger.info(f"ComfyUI Port: {args.port}")
    logger.info(f"Mode: {args.mode}")
    if args.mode == "standalone":
        logger.info(f"Python Path: {args.python_path}")

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
        flags_enabled.append("--fast fp16_accumulation")
    if args.gpu_only:
        flags_enabled.append("--gpu-only")
    if flags_enabled:
        logger.info(f"Performance Flags: {', '.join(flags_enabled)}")

    if args.max_crash_restarts > 0:
        logger.info(f"Crash Recovery: enabled (max {args.max_crash_restarts} restarts, {args.crash_cooldown}s cooldown)")
    else:
        logger.info(f"Crash Recovery: disabled")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info("=" * 60)

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
        logger.error(f"Failed to start ComfyUI: {e}")
        sys.exit(1)

    output_thread = threading.Thread(target=stream_comfyui_output, args=(process,), daemon=True)
    output_thread.start()

    COMFYUI_STARTUP_TIMEOUT = 3000  # 50 minutes for initial model loading
    if not wait_for_comfyui(args.port, timeout=COMFYUI_STARTUP_TIMEOUT):
        logger.error("ComfyUI failed to start")
        shutdown()
        sys.exit(1)

    server_state['is_ready'] = True
    logger.info("\n" + "=" * 60)
    logger.info("SERVER READY")
    logger.info(f"ComfyUI API: http://127.0.0.1:{args.port}")
    logger.info("=" * 60 + "\n")

    # Save node definitions to network path for client machines
    _save_node_info_to_network(args.port, global_settings)

    health_thread = threading.Thread(target=health_monitor_thread, args=(args.port,), daemon=True)
    health_thread.start()

    health_port = args.health_port or (args.port + 1000)
    try:
        health_server = HTTPServer(('0.0.0.0', health_port), HealthCheckHandler)
        health_server_thread = threading.Thread(target=health_server.serve_forever, daemon=True)
        health_server_thread.start()
        logger.info(f"Health check endpoint: http://0.0.0.0:{health_port}/health")
    except Exception as e:
        logger.warning(f"Could not start health check server on port {health_port}: {e}")

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
                    logger.error("Restart failed, server will exit")
                    break

            # Always refresh process reference from server_state to stay in sync
            # with restarts triggered by other threads (health monitor, etc.)
            process = server_state['comfyui_process']

            # Check process status (may be None after self-restart)
            if process is not None:
                ret = process.poll()
            else:
                # No process handle - always validate health to detect dead processes
                # (not just when is_ready=False, since is_ready could be stale)
                ret = None
                config = server_state.get('startup_config', {})
                port = config.get('port', 8188)
                if not check_server_health(port):
                    logger.warning("No process handle and ComfyUI not responding, restarting...")
                    server_state['is_ready'] = False
                    if restart_comfyui(reason="orphaned"):
                        process = server_state['comfyui_process']
                        last_stable_check = time.time()
                    else:
                        logger.error("Failed to restart orphaned ComfyUI")
                        break

            if ret is not None:
                # ComfyUI exited - check if it was a self-restart or a crash
                server_state['is_ready'] = False

                # Handle ComfyUI self-restart (exit code 0 with restart pending)
                # ComfyUI already spawned a new process - just wait for it to be ready
                if ret == 0 and server_state.test_and_clear('self_restart_pending'):
                    logger.info("ComfyUI self-restart in progress, waiting for new instance...")
                    server_state['comfyui_process'] = None  # Old process is gone
                    process = None

                    config = server_state.get('startup_config', {})
                    port = config.get('port', 8188)

                    # Wait for the new ComfyUI instance that was spawned by the restart
                    if wait_for_comfyui(port, timeout=120):
                        logger.info("ComfyUI self-restart complete, new instance is ready")
                        server_state['is_ready'] = True
                        last_stable_check = time.time()

                        # Refresh node definitions on network after self-restart
                        _save_node_info_to_network(port)

                        # Note: We don't have a process handle for the new instance
                        # but we can still monitor via health checks
                    else:
                        logger.error("ComfyUI self-restart failed - new instance not responding")
                        # Kill any orphaned process and try a full restart
                        kill_process_on_port(port)
                        if restart_comfyui(reason="self_restart_failed"):
                            process = server_state['comfyui_process']
                            last_stable_check = time.time()
                        else:
                            logger.error("Failed to recover from self-restart failure")
                            break
                    continue  # Skip the crash recovery path
                elif handle_crash_recovery(ret):
                    # Recovery successful, update process reference
                    process = server_state['comfyui_process']
                    last_stable_check = time.time()
                else:
                    # Recovery failed or max retries exceeded
                    logger.error("Crash recovery failed, server will exit")
                    break

            # Reset crash counter after stable uptime period
            # Only count time while continuously ready (not time since last restart)
            if server_state['is_ready']:
                if server_state['crash_count'] > 0:
                    if time.time() - last_stable_check > stable_uptime_threshold:
                        reset_crash_counter()
                        last_stable_check = time.time()
            else:
                # Not ready — reset the stable timer so it must be ready for the
                # full threshold duration before crash counter resets
                last_stable_check = time.time()

            time.sleep(2)  # Check more frequently (was 5s)

    except KeyboardInterrupt:
        pass

    shutdown()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
    main()
