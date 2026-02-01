"""
Canvas synchronization manager for network-based collaboration.

Handles:
- Canvas state save/load to network path (per project/jobname)
- Auto-sync polling (2 second interval for canvas state)
- Cursor presence synchronization (100ms for real-time cursors)
- File locking for write coordination (last-write-wins)
"""

import os
import json
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Optional, Callable, Any

from PySide6.QtCore import QObject, Signal, QTimer

logger = logging.getLogger(__name__)


class CanvasSyncManager(QObject):
    """
    Manages network synchronization of canvas state.

    Syncs canvas state (positions, connections, groups) every 2 seconds.
    Uses file-based locking for write coordination.
    Implements last-write-wins conflict resolution.
    """

    # Signals
    state_changed = Signal(dict)  # Remote state changed, needs merge
    sync_error = Signal(str)  # Sync error occurred
    users_changed = Signal(list)  # List of active users changed

    # Sync intervals
    STATE_POLL_INTERVAL = 2000  # 2 seconds per plan
    LOCK_TIMEOUT = 5.0  # seconds to wait for lock

    def __init__(self, parent=None):
        super().__init__(parent)

        self._canvas_dir = ""
        self._jobname = "default"
        self._username = "unknown"

        self._last_state_mtime = 0.0
        self._last_local_save = 0.0
        self._is_dirty = False

        # Lock for thread-safe file operations (RLock for reentrant safety)
        self._file_lock = threading.RLock()

        # Setup state sync timer
        self._state_timer = QTimer(self)
        self._state_timer.setInterval(self.STATE_POLL_INTERVAL)
        self._state_timer.timeout.connect(self._poll_state)

        # Track active users (from presence files)
        self._active_users = []

    def configure(self, canvas_dir: str, jobname: str, username: str):
        """
        Configure the sync manager for a specific canvas.

        Args:
            canvas_dir: Base directory for canvas state (e.g., user's output folder)
            jobname: Project/shot name for canvas file naming
            username: Current user's name
        """
        self._canvas_dir = canvas_dir
        self._jobname = jobname
        self._username = username
        self._last_state_mtime = 0.0

        logger.info(f"Sync manager configured: {canvas_dir}, job={jobname}, user={username}")

    @property
    def state_file_path(self) -> str:
        """Get the full path to the canvas state file."""
        if not self._canvas_dir:
            return ""
        canvas_subdir = os.path.join(self._canvas_dir, "_canvas")
        return os.path.join(canvas_subdir, f"canvas_{self._jobname}.json")

    @property
    def lock_file_path(self) -> str:
        """Get the full path to the lock file."""
        if not self._canvas_dir:
            return ""
        canvas_subdir = os.path.join(self._canvas_dir, "_canvas")
        return os.path.join(canvas_subdir, f"canvas_{self._jobname}.lock")

    def start(self):
        """Start synchronization polling."""
        if not self._canvas_dir:
            logger.warning("Cannot start sync: no canvas directory configured")
            return

        self._state_timer.start()
        logger.info("Canvas sync started")

    def stop(self):
        """Stop synchronization polling."""
        self._state_timer.stop()
        logger.info("Canvas sync stopped")

    def is_running(self) -> bool:
        """Check if sync is currently active."""
        return self._state_timer.isActive()

    def _ensure_canvas_dir(self):
        """Ensure the canvas subdirectory exists."""
        if not self._canvas_dir:
            return False

        canvas_subdir = os.path.join(self._canvas_dir, "_canvas")
        try:
            os.makedirs(canvas_subdir, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to create canvas directory: {e}")
            return False

    def _acquire_lock(self, timeout: float = None) -> bool:
        """
        Acquire file lock for writing.

        Uses a simple lock file with timeout. If lock is stale (>30s old),
        it will be forcibly removed.

        Args:
            timeout: Max seconds to wait for lock (default: LOCK_TIMEOUT)

        Returns:
            True if lock acquired, False otherwise
        """
        if timeout is None:
            timeout = self.LOCK_TIMEOUT

        lock_path = self.lock_file_path
        if not lock_path:
            return False

        start_time = time.time()

        while True:
            try:
                # Check for stale lock (>30 seconds old)
                if os.path.exists(lock_path):
                    lock_age = time.time() - os.path.getmtime(lock_path)
                    if lock_age > 30:
                        logger.warning(f"Removing stale lock file ({lock_age:.1f}s old)")
                        os.remove(lock_path)

                # Try to create lock file (exclusive)
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{self._username}:{time.time()}".encode())
                os.close(fd)
                return True

            except FileExistsError:
                # Lock exists and is not stale - wait
                if time.time() - start_time > timeout:
                    logger.warning(f"Lock acquisition timed out after {timeout}s")
                    return False
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Lock acquisition error: {e}")
                return False

    def _release_lock(self):
        """Release file lock."""
        lock_path = self.lock_file_path
        if lock_path and os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception as e:
                logger.warning(f"Failed to release lock: {e}")

    def save_state(self, state: dict) -> bool:
        """
        Save canvas state to network file.

        Uses file locking to prevent concurrent writes.
        Implements last-write-wins - no merge on write.

        Args:
            state: Canvas state dictionary

        Returns:
            True if save successful
        """
        if not self._ensure_canvas_dir():
            return False

        state_path = self.state_file_path
        if not state_path:
            return False

        with self._file_lock:
            if not self._acquire_lock():
                self.sync_error.emit("Could not acquire write lock")
                return False

            try:
                # Add metadata
                state["version"] = "1.0"
                state["last_modified"] = datetime.now().isoformat()
                state["modified_by"] = self._username

                # Atomic write via temp file
                temp_path = state_path + ".tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2)

                # Replace original
                if os.path.exists(state_path):
                    os.remove(state_path)
                os.rename(temp_path, state_path)

                self._last_local_save = time.time()
                self._last_state_mtime = os.path.getmtime(state_path)
                self._is_dirty = False

                logger.debug(f"Canvas state saved: {state_path}")
                return True

            except Exception as e:
                logger.error(f"Failed to save canvas state: {e}")
                self.sync_error.emit(f"Save failed: {e}")
                return False

            finally:
                self._release_lock()

    def load_state(self) -> Optional[dict]:
        """
        Load canvas state from network file.

        Returns:
            State dictionary, or None if file doesn't exist or error
        """
        state_path = self.state_file_path
        if not state_path or not os.path.exists(state_path):
            return None

        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)

            self._last_state_mtime = os.path.getmtime(state_path)
            return state

        except Exception as e:
            logger.error(f"Failed to load canvas state: {e}")
            return None

    def _poll_state(self):
        """Poll for state changes from other users."""
        state_path = self.state_file_path
        if not state_path or not os.path.exists(state_path):
            return

        try:
            current_mtime = os.path.getmtime(state_path)

            # Check if file was modified by someone else
            if current_mtime > self._last_state_mtime:
                # Don't reload if we just saved (prevents self-triggering)
                if time.time() - self._last_local_save < 1.0:
                    self._last_state_mtime = current_mtime
                    return

                # Load remote state
                state = self.load_state()
                if state:
                    logger.info(f"Remote canvas change detected (by {state.get('modified_by', 'unknown')})")
                    self.state_changed.emit(state)

        except Exception as e:
            logger.warning(f"State poll error: {e}")

    def mark_dirty(self):
        """Mark local state as changed (needs save)."""
        self._is_dirty = True

    def needs_save(self) -> bool:
        """Check if local state has unsaved changes."""
        return self._is_dirty


class CursorPresenceManager(QObject):
    """
    Manages real-time cursor presence for collaboration.

    Syncs cursor positions at 100ms interval for smooth real-time feel.
    Shows which users are currently active and where they're looking.
    """

    # Signals
    cursors_updated = Signal(dict)  # {username: {x, y, color, timestamp}}
    user_joined = Signal(str)  # username
    user_left = Signal(str)  # username

    # Presence intervals
    CURSOR_POLL_INTERVAL = 100  # 100ms per plan
    CURSOR_TIMEOUT = 5.0  # User considered gone after 5s of no updates
    CURSOR_WRITE_INTERVAL = 100  # Write our cursor every 100ms

    # User colors for cursor display
    USER_COLORS = [
        "#FF6B6B",  # Red
        "#4ECDC4",  # Teal
        "#45B7D1",  # Blue
        "#96CEB4",  # Green
        "#FFEAA7",  # Yellow
        "#DDA0DD",  # Plum
        "#98D8C8",  # Mint
        "#F7DC6F",  # Gold
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._canvas_dir = ""
        self._jobname = "default"
        self._username = "unknown"
        self._user_color = self.USER_COLORS[0]

        self._cursor_x = 0.0
        self._cursor_y = 0.0
        self._known_users: Dict[str, dict] = {}

        # Setup cursor sync timers
        self._read_timer = QTimer(self)
        self._read_timer.setInterval(self.CURSOR_POLL_INTERVAL)
        self._read_timer.timeout.connect(self._poll_cursors)

        self._write_timer = QTimer(self)
        self._write_timer.setInterval(self.CURSOR_WRITE_INTERVAL)
        self._write_timer.timeout.connect(self._write_cursor)

    def configure(self, canvas_dir: str, jobname: str, username: str):
        """
        Configure presence manager for a specific canvas.

        Args:
            canvas_dir: Base directory for presence files
            jobname: Project/shot name
            username: Current user's name
        """
        self._canvas_dir = canvas_dir
        self._jobname = jobname
        self._username = username

        # Assign color based on username hash
        color_index = hash(username) % len(self.USER_COLORS)
        self._user_color = self.USER_COLORS[color_index]

        logger.info(f"Cursor presence configured: user={username}, color={self._user_color}")

    @property
    def presence_dir(self) -> str:
        """Get directory for presence files."""
        if not self._canvas_dir:
            return ""
        return os.path.join(self._canvas_dir, "_canvas", "presence")

    @property
    def my_presence_file(self) -> str:
        """Get path to this user's presence file."""
        if not self.presence_dir:
            return ""
        return os.path.join(self.presence_dir, f"{self._jobname}_{self._username}.json")

    def start(self):
        """Start cursor presence updates."""
        if not self._canvas_dir:
            logger.warning("Cannot start presence: no canvas directory configured")
            return

        # Ensure presence directory exists
        try:
            os.makedirs(self.presence_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create presence directory: {e}")
            return

        self._read_timer.start()
        self._write_timer.start()
        logger.info("Cursor presence started")

    def stop(self):
        """Stop cursor presence updates and remove our presence file."""
        self._read_timer.stop()
        self._write_timer.stop()

        # Remove our presence file
        try:
            if os.path.exists(self.my_presence_file):
                os.remove(self.my_presence_file)
        except Exception as e:
            logger.warning(f"Failed to remove presence file: {e}")

        logger.info("Cursor presence stopped")

    def update_cursor(self, x: float, y: float):
        """Update local cursor position (called on mouse move)."""
        self._cursor_x = x
        self._cursor_y = y

    def get_user_color(self, username: str) -> str:
        """Get assigned color for a user."""
        if username == self._username:
            return self._user_color
        # Use consistent color based on username hash
        color_index = hash(username) % len(self.USER_COLORS)
        return self.USER_COLORS[color_index]

    def _write_cursor(self):
        """Write our cursor position to presence file."""
        presence_file = self.my_presence_file
        if not presence_file:
            return

        try:
            presence_data = {
                "username": self._username,
                "x": self._cursor_x,
                "y": self._cursor_y,
                "color": self._user_color,
                "timestamp": time.time()
            }

            with open(presence_file, 'w', encoding='utf-8') as f:
                json.dump(presence_data, f)

        except Exception as e:
            # Silently ignore write errors (non-critical)
            pass

    def _poll_cursors(self):
        """Poll for cursor updates from other users."""
        presence_dir = self.presence_dir
        if not presence_dir or not os.path.exists(presence_dir):
            return

        current_time = time.time()
        active_cursors = {}
        pattern = f"{self._jobname}_"

        try:
            for filename in os.listdir(presence_dir):
                if not filename.startswith(pattern) or not filename.endswith(".json"):
                    continue

                # Extract username from filename
                username = filename[len(pattern):-5]

                # Skip our own cursor
                if username == self._username:
                    continue

                filepath = os.path.join(presence_dir, filename)

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    timestamp = data.get("timestamp", 0)

                    # Check if cursor is still active
                    if current_time - timestamp < self.CURSOR_TIMEOUT:
                        active_cursors[username] = {
                            "x": data.get("x", 0),
                            "y": data.get("y", 0),
                            "color": data.get("color", self.USER_COLORS[0]),
                            "timestamp": timestamp
                        }

                        # Check for new user
                        if username not in self._known_users:
                            self.user_joined.emit(username)
                    else:
                        # Stale cursor - user might have left
                        if username in self._known_users:
                            self.user_left.emit(username)
                            # Clean up stale file
                            try:
                                os.remove(filepath)
                            except:
                                pass

                except Exception:
                    # Ignore individual file read errors
                    pass

            # Update known users
            self._known_users = active_cursors

            # Emit cursor updates
            if active_cursors:
                self.cursors_updated.emit(active_cursors)

        except Exception as e:
            logger.warning(f"Cursor poll error: {e}")

    def get_active_users(self) -> list:
        """Get list of currently active usernames."""
        return list(self._known_users.keys())
