"""
Centralized logging utilities for Luma Tools.

Provides:
- Network path resolution for log files
- File-based logging with stdout/stderr tee
- TeeStream and TeeWriter for dual output

Consolidates logging setup duplicated across luma_tools.py, runner.py, server.py.

This module is used during early startup before settings_manager is available,
so it reads global settings directly from file for path resolution.
"""

import atexit
import sys
import os
import json
import socket
import getpass
import logging
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level tracking of TeeWriter instances for proper cleanup
# Protected by lock for thread safety
_active_tee_writers: list = []
_tee_writers_lock = threading.RLock()


def cleanup_tee_writers():
    """Clean up all active TeeWriter instances (close log files)."""
    global _active_tee_writers
    with _tee_writers_lock:
        for writer in _active_tee_writers:
            if hasattr(writer, 'close'):
                writer.close()
        _active_tee_writers.clear()


# Register cleanup on interpreter exit to prevent file handle leaks on Windows
atexit.register(cleanup_tee_writers)


# =============================================================================
# PATH RESOLUTION
# =============================================================================

# Cached values
_network_output_path_cache: Optional[str] = None
_network_negative_cache_time: float = 0.0  # time.monotonic() of last negative cache
_NEGATIVE_CACHE_TTL = 120.0  # Re-check after 2 minutes if network was unavailable
_network_cache_lock = threading.RLock()


def _get_global_settings_paths() -> list:
    """Get ordered list of possible global settings file locations."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return [
        os.path.join(script_dir, '..', '..', 'global_settings', 'global_settings.json'),
    ]


def _load_global_settings_raw() -> dict:
    """Load global settings directly from file (bypasses settings_manager cache).

    This is used during early startup before settings_manager is available.
    """
    for settings_path in _get_global_settings_paths():
        norm_path = os.path.normpath(settings_path)
        if os.path.exists(norm_path):
            try:
                with open(norm_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                continue
    return {}


def get_network_output_path() -> Optional[str]:
    """
    Get the network output path from global settings.

    This is the central network location for ComfyUI outputs and logs
    (currently W:/LumaRND/tmp/ComfyUI_OUT).

    Uses caching to avoid repeated file reads.

    Returns:
        Network path string if available and exists, None otherwise
    """
    global _network_output_path_cache, _network_negative_cache_time

    with _network_cache_lock:
        if _network_output_path_cache is not None:
            if _network_output_path_cache:
                return _network_output_path_cache
            # Negative cache — re-check after TTL expires (network may have come online)
            import time as _time
            if (_time.monotonic() - _network_negative_cache_time) < _NEGATIVE_CACHE_TTL:
                return None
            # TTL expired, fall through to re-check

        settings = _load_global_settings_raw()
        path = settings.get('network_output_path', '')

        if path and os.path.isdir(path):
            _network_output_path_cache = path
            return path

        import time as _time
        _network_output_path_cache = ""  # Cache the negative result with TTL
        _network_negative_cache_time = _time.monotonic()
        return None


def get_network_log_dir(subdirectory: str = "users") -> Optional[str]:
    """
    Get network log directory from global settings.

    Reads network_output_path from global settings and returns
    the _logs/{subdirectory} path if available and writable.

    Args:
        subdirectory: Subdirectory under _logs/ (e.g., "users", "server", "runner")

    Returns:
        Path to network log directory, or None if unavailable
    """
    from .utils import ensure_directory
    network_path = get_network_output_path()
    if network_path:
        log_dir = os.path.join(network_path, '_logs', subdirectory)
        try:
            ensure_directory(log_dir)
            return log_dir
        except OSError:
            pass
    return None


def get_local_log_dir() -> str:
    """Get local fallback log directory (~/.luma_tools/logs/)."""
    from .utils import ensure_directory
    log_dir = os.path.join(os.path.expanduser("~"), ".luma_tools", "logs")
    ensure_directory(log_dir)
    return log_dir


def clear_path_cache():
    """Clear cached paths. Call after settings changes."""
    global _network_output_path_cache
    with _network_cache_lock:
        _network_output_path_cache = None


# =============================================================================
# TEE STREAMS
# =============================================================================

class TeeStream:
    """
    Stream that writes to both the original stream and a logging function.

    Used by luma_tools.py for the main app. Buffers lines for clean logging.

    Re-entrancy guard: when a logging handler fails (e.g. the network log
    file becomes unreachable), logging's error handling writes to stderr —
    which may be THIS stream. Feeding that back into log_func would recurse
    (write -> logging -> handler error -> stderr write -> logging -> ...),
    so writes that happen while we're already inside log_func on the same
    thread go to the original stream only.
    """

    def __init__(self, original_stream, log_func):
        self.original = original_stream
        self.log_func = log_func
        self.buffer = ""
        self._lock = threading.RLock()
        self._tls = threading.local()

    def write(self, text):
        with self._lock:
            if self.original:
                self.original.write(text)
            if getattr(self._tls, 'in_log_func', False):
                return  # re-entrant write from logging's own error handling
            self.buffer += text
            while '\n' in self.buffer:
                line, self.buffer = self.buffer.split('\n', 1)
                if line.strip():
                    self._tls.in_log_func = True
                    try:
                        self.log_func(line)
                    finally:
                        self._tls.in_log_func = False

    def flush(self):
        with self._lock:
            if self.original:
                self.original.flush()
            if getattr(self._tls, 'in_log_func', False):
                return
            if self.buffer.strip():
                self._tls.in_log_func = True
                try:
                    self.log_func(self.buffer)
                finally:
                    self._tls.in_log_func = False
                self.buffer = ""


class TeeWriter:
    """
    Stream that writes to both the original stream and a log file with timestamps.

    Used by runner.py for farm execution logging.
    Manages the log file handle and closes it properly on cleanup.
    Thread-safe: uses lock to prevent write/close races during shutdown.
    """

    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file
        self._closed = False
        self._lock = threading.RLock()

    def write(self, message):
        with self._lock:
            if self._closed:
                return
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
        with self._lock:
            if self._closed:
                return
            self.original_stream.flush()
            self.log_file.flush()

    def close(self):
        """Close the log file handle and restore original stream behavior."""
        with self._lock:
            if not self._closed:
                self._closed = True
                try:
                    self.log_file.close()
                except Exception:
                    pass


# =============================================================================
# RESILIENT FILE HANDLER
# =============================================================================

class ResilientFileHandler(logging.FileHandler):
    """FileHandler that self-disables after repeated I/O failures.

    Log files usually live on a network share; if the share drops, every
    emit raises OSError and logging's default error handling prints a
    multi-line traceback to stderr — which the app tees back into logging,
    amplifying the failure. This handler counts consecutive emit failures,
    disables itself after a threshold, and writes a single notice to the
    real stderr instead.
    """

    MAX_CONSECUTIVE_FAILURES = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._consecutive_failures = 0
        self._disabled = False
        self._emit_failed = False

    def emit(self, record):
        if self._disabled:
            return
        self._emit_failed = False
        super().emit(record)
        if not self._emit_failed:
            self._consecutive_failures = 0

    def handleError(self, record):
        # Deliberately do NOT call super().handleError() — it prints a
        # traceback to sys.stderr, which TeeStream feeds back into logging.
        self._emit_failed = True
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES and not self._disabled:
            self._disabled = True
            try:
                sys.__stderr__.write(
                    f"[luma_tools] Log file unreachable ({self.baseFilename}); "
                    f"file logging disabled for this session.\n"
                )
            except Exception:
                pass


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_file_logging(
    log_prefix: str = "luma_tools",
    subdirectory: str = "users",
    include_hostname: bool = True,
    include_username: bool = True,
    redirect_stdout: bool = True,
    tee_mode: str = "stream",
    fallback_dir: Optional[str] = None,
) -> str:
    """
    Setup file-based logging with optional stdout/stderr redirection.

    This is the main entry point for setting up logging in any Luma Tools module.
    Consolidates the patterns from luma_tools.py, runner.py, and server.py.

    Args:
        log_prefix: Prefix for log filename (e.g., "luma_tools", "comfyui_runner")
        subdirectory: Subdirectory under _logs/ (e.g., "users", "server", "runner")
        include_hostname: Include hostname in filename
        include_username: Include username in filename
        redirect_stdout: Whether to redirect stdout/stderr to log
        tee_mode: "stream" for TeeStream (app), "writer" for TeeWriter (runner),
                  "handlers" for file+console handlers (server), "none" for file-only
        fallback_dir: Optional fallback directory if network path unavailable

    Returns:
        Path to the log file
    """
    username = getpass.getuser() if include_username else ""
    hostname = socket.gethostname() if include_hostname else ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Build filename parts
    parts = [log_prefix]
    if username:
        parts.append(username)
    if hostname:
        parts.append(hostname)
    parts.append(timestamp)
    log_filename = "_".join(parts) + ".log"

    # Get log directory (network with fallback to local)
    from .utils import ensure_directory
    log_dir = get_network_log_dir(subdirectory)
    if not log_dir and fallback_dir and os.path.isdir(fallback_dir):
        log_dir = os.path.join(fallback_dir, "logs")
        ensure_directory(log_dir)
    if not log_dir:
        log_dir = get_local_log_dir()

    log_path = os.path.join(log_dir, log_filename)

    # Never let logging's internal error handling print tracebacks to
    # stderr — with the stderr tee active that feeds straight back into
    # logging and amplifies (see ResilientFileHandler).
    logging.raiseExceptions = False

    if tee_mode == "handlers":
        # Server-style: file + console handlers, no stdout redirect
        _setup_dual_handlers(log_path)
    else:
        # App/runner-style: file handler + stdout/stderr tee.
        # basicConfig silently no-ops when the root logger already has
        # handlers — a second caller would then believe it created a new log
        # file that is never written. Attach the handler explicitly instead.
        root_logger = logging.getLogger()
        if root_logger.handlers:
            logging.warning(
                f"setup_file_logging called again — adding additional log file: {log_path}"
            )
        else:
            root_logger.setLevel(logging.DEBUG)
        # GUI app ("stream" mode): the log file is a synchronous SMB write,
        # so route records through a queue and write on a background thread —
        # a stalled network share must never freeze the thread that logs.
        _attach_file_handler(log_path, root_logger, non_blocking=(tee_mode == "stream"))

        if redirect_stdout:
            # Clean up any existing tee writers before creating new ones
            # to prevent file handle leaks if setup_file_logging is called multiple times
            cleanup_tee_writers()

            if tee_mode == "stream":
                sys.stdout = TeeStream(sys.__stdout__, logging.info)
                sys.stderr = TeeStream(sys.__stderr__, logging.error)
            elif tee_mode == "writer":
                log_file = None
                try:
                    log_file = open(log_path, 'a', encoding='utf-8')
                    log_file.write(f"{'='*60}\n")
                    log_file.write(f"Log started - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    log_file.write(f"{'='*60}\n\n")
                    log_file.flush()
                    # Hold lock during both assignment and tracking to prevent
                    # cleanup_tee_writers() from missing these writers
                    with _tee_writers_lock:
                        stdout_tee = TeeWriter(sys.__stdout__, log_file)
                        stderr_tee = TeeWriter(sys.__stderr__, log_file)
                        sys.stdout = stdout_tee
                        sys.stderr = stderr_tee
                        _active_tee_writers.extend([stdout_tee, stderr_tee])
                except Exception:
                    # Clean up file handle if setup failed
                    if log_file:
                        try:
                            log_file.close()
                        except Exception:
                            pass
                    raise

                # Update logging StreamHandler to use the tee'd stderr
                for handler in logging.getLogger().handlers:
                    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                        handler.stream = sys.stderr

    logging.info(f"Log file: {log_path}")
    return log_path


def _attach_file_handler(log_path: str, root_logger, non_blocking: bool):
    """Attach a resilient file handler, optionally decoupled via a queue.

    non_blocking=True routes records through logging.handlers.QueueHandler /
    QueueListener so the actual file write happens on a background thread —
    the emitting thread (often the GUI thread) never blocks on network I/O.
    """
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    file_handler = ResilientFileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    if non_blocking:
        import queue as _queue
        from logging.handlers import QueueHandler, QueueListener
        log_queue = _queue.Queue(-1)
        listener = QueueListener(log_queue, file_handler, respect_handler_level=True)
        listener.start()
        atexit.register(listener.stop)
        root_logger.addHandler(QueueHandler(log_queue))
    else:
        root_logger.addHandler(file_handler)


def _setup_dual_handlers(log_path: str):
    """Set up logging with both file and console handlers (server style)."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler - network-accessible log
    file_handler = ResilientFileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.addHandler(file_handler)

    # Console handler - for terminal/Deadline output
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.addHandler(console_handler)


def setup_polling_logger() -> Optional[str]:
    """
    Set up a dedicated log file for polling modules.

    Routes deadline.poller and ui.tabs.comfyui.polling to a separate
    log file under _logs/polling/ to reduce noise in the main app log.
    Sets propagate=False so polling messages don't appear in the main log.

    Returns:
        Path to the polling log file, or None if setup failed
    """
    username = getpass.getuser()
    hostname = socket.gethostname()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"polling_{username}_{hostname}_{timestamp}.log"

    log_dir = get_network_log_dir("polling")
    if not log_dir:
        log_dir = get_local_log_dir()

    log_path = os.path.join(log_dir, log_filename)

    handler = ResilientFileHandler(log_path, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))

    for name in ("deadline.poller", "ui.tabs.comfyui.polling"):
        polling_logger = logging.getLogger(name)
        polling_logger.addHandler(handler)
        polling_logger.propagate = False

    # Cleanup old polling logs
    cleanup_old_logs(log_dir, f"polling_{username}_{hostname}_", keep_count=5)

    logging.info(f"Polling log file: {log_path}")
    return log_path


def cleanup_old_logs(log_dir: str, prefix: str, keep_count: int = 5):
    """
    Remove old log files, keeping only the most recent.

    Args:
        log_dir: Directory containing log files
        prefix: Filename prefix to match (e.g., "luma_tools_username_hostname_")
        keep_count: Number of recent files to keep
    """
    try:
        log_files = sorted(
            [f for f in os.listdir(log_dir)
             if f.startswith(prefix) and f.endswith(".log")],
            reverse=True
        )
        for old_file in log_files[keep_count:]:
            try:
                os.remove(os.path.join(log_dir, old_file))
            except OSError as e:
                logger.debug(f"Could not remove old log file {old_file}: {e}")
    except Exception as e:
        logger.debug(f"Error during log cleanup: {e}")


def setup_exception_hook():
    """Install global exception hook to log unhandled exceptions."""
    import traceback

    def exception_hook(exc_type, exc_value, exc_traceback):
        logging.error("=" * 60)
        logging.error("UNHANDLED EXCEPTION")
        logging.error("=" * 60)
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        for line in tb_lines:
            for subline in line.rstrip().split('\n'):
                logging.error(subline)
        logging.error("=" * 60)
        # Also print to stderr for visibility
        sys.__stderr__.write("".join(tb_lines))

    sys.excepthook = exception_hook
