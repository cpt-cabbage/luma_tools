"""
Gallery Refresh Controller.

Handles gallery content refresh mechanisms:
- File system watcher for local paths
- Polling timer for network paths
- Scan operations and caching
"""

import os
import time
import logging
from PySide6.QtCore import QTimer, QThreadPool, QFileSystemWatcher

from .base_manager import BaseGalleryManager

logger = logging.getLogger(__name__)

# A scan that has been "in progress" longer than this is assumed dead (lost
# worker signal) — the flag is cleared so refreshes are not wedged forever.
SCAN_WATCHDOG_SECONDS = 120

DEFAULT_POLL_INTERVAL_SECONDS = 10


def _probe_directory(path):
    """Cheap change probe: top-level names + mtime + size.

    Runs on the worker thread (never the GUI thread). Returns a comparable
    snapshot tuple, or None when the directory could not be probed (in which
    case the caller must fall back to a full scan).
    """
    entries = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    stat_result = entry.stat()
                    entries.append((entry.name, stat_result.st_mtime, stat_result.st_size))
                except OSError:
                    # Entry vanished mid-probe — treat the directory as changed
                    return None
    except OSError as e:
        logger.debug(f"[Gallery] Poll probe failed for {path}: {e}")
        return None

    entries.sort()
    return tuple(entries)


class RefreshController(BaseGalleryManager):
    """Manages refresh and file watching for the gallery."""

    def __init__(self, tab):
        """
        Initialize the refresh controller.

        Args:
            tab: Reference to the GalleryTab
        """
        super().__init__(tab)

        # File system watcher
        self._watcher = None
        self._watched_path = None
        self._watcher_setup_in_progress = False

        # Refresh debouncing
        self._refresh_timer = None

        # Polling for network paths
        self._poll_timer = None
        self._poll_interval = self._read_poll_interval()

        # Scan state
        self._scan_in_progress = False
        self._scan_started_at = None

        # Cheap change-detection snapshot for automatic polls
        self._probe_snapshot = None

        # mtime of the gallery metadata file the last time lineage was
        # auto-established (lineage only re-runs when this changes)
        self._last_lineage_mtime = None

    # =========================================================================
    # POLL INTERVAL
    # =========================================================================

    @staticmethod
    def _read_poll_interval():
        """Poll interval in milliseconds, from the user setting."""
        try:
            from core.settings_manager import safe_get_setting
            seconds = safe_get_setting("gallery_poll_interval", DEFAULT_POLL_INTERVAL_SECONDS)
            seconds = int(seconds)
        except Exception:
            seconds = DEFAULT_POLL_INTERVAL_SECONDS
        if seconds < 5:
            seconds = 5
        elif seconds > 300:
            seconds = 300
        return seconds * 1000

    def apply_poll_interval(self):
        """Re-read the poll interval setting and restart the timer if needed."""
        new_interval = self._read_poll_interval()
        if new_interval == self._poll_interval:
            return
        self._poll_interval = new_interval
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.start(self._poll_interval)
            self.tab.log(
                f"[Gallery] Poll interval changed to {self._poll_interval // 1000}s"
            )

    def _check_scan_watchdog(self):
        """Clear a wedged _scan_in_progress flag.

        A lost worker signal (crash in the result slot, thread pool hiccup)
        used to leave the flag set forever, silently killing every subsequent
        non-forced refresh for the lifetime of the app.

        Returns:
            bool: True if a stuck scan was cleared.
        """
        if not self._scan_in_progress:
            return False
        started = self._scan_started_at
        if started is None:
            return False
        elapsed = time.monotonic() - started
        if elapsed < SCAN_WATCHDOG_SECONDS:
            return False

        logger.warning(
            f"[Gallery] Scan appears stuck ({elapsed:.0f}s) — clearing "
            "in-progress flag and continuing"
        )
        self._scan_in_progress = False
        self._scan_started_at = None
        return True

    def on_refresh(self, force=False, show_status=True, auto=False):
        """
        Handle refresh request.

        Args:
            force: If True, bypass scan-in-progress check
            show_status: If True, show status bar feedback (False for auto-refreshes)
            auto: If True this is an automatic refresh (poll tick / watcher
                notification). Automatic refreshes run a cheap change probe
                first and skip content hashing; manual ones never do.
        """
        self._check_scan_watchdog()

        if self._scan_in_progress and not force:
            self.tab.log("[Gallery] Refresh already in progress, skipping...")
            # Only show status message for user-initiated refreshes, not auto-refreshes
            if show_status:
                self.show_status("Refresh already in progress", "info")
            return

        # Store flags for use in _do_refresh
        self._pending_show_status = show_status
        self._pending_auto = auto

        # For non-forced refreshes, debounce multiple rapid requests
        if not force:
            if self._refresh_timer is None:
                self._refresh_timer = QTimer()
                self._refresh_timer.setSingleShot(True)
                self._refresh_timer.timeout.connect(self._do_refresh)

            # Restart the timer (debounce)
            self._refresh_timer.start(500)  # 500ms debounce
        else:
            # Force refresh - do it immediately
            self._do_refresh()

    def _do_refresh(self):
        """Actually perform the refresh scan."""
        from ui_components import Worker

        if self._scan_in_progress:
            return

        self._scan_in_progress = True
        self._scan_started_at = time.monotonic()

        # Get show_status flag (default True for backward compatibility)
        show_status = getattr(self, '_pending_show_status', True)
        self._current_scan_show_status = show_status  # Store for completion handler
        is_auto = bool(getattr(self, '_pending_auto', False))

        # NOTE: _cached_items is deliberately NOT cleared here. scan_directory()
        # never consults it, and clearing it made redisplay a no-op (and lost
        # the item list entirely) whenever a scan errored or was skipped.

        # Get current path
        current_path = self.tab._current_path

        if not current_path or not os.path.exists(current_path):
            self.tab.log(f"[Gallery] Path not found: {current_path}")
            self._scan_in_progress = False
            self._scan_started_at = None
            return

        self.tab.log(f"[Gallery] Scanning: {current_path}")

        # Show status feedback only for user-initiated refreshes
        if show_status and self.tab.animator:
            self.tab.animator.start_activity(
                "gallery_scan", "Gallery: Scanning files"
            )

        previous_snapshot = self._probe_snapshot
        previous_lineage_mtime = self._last_lineage_mtime

        # Scan in background thread
        def scan():
            result = {"items": None, "snapshot": None, "lineage_mtime": None}

            # Cheap pre-check for automatic refreshes: if nothing at the top
            # level changed, skip the (recursive, metadata-loading) rescan.
            if is_auto:
                snapshot = _probe_directory(current_path)
                result["snapshot"] = snapshot
                if snapshot is not None and snapshot == previous_snapshot:
                    result["skipped"] = True
                    return result

            result["items"] = self.tab._loader.scan_directory(
                current_path, allow_hashing=not is_auto
            )

            # Auto-establish lineage relationships in the background. This walks
            # the whole directory and writes metadata, so only run it when the
            # metadata file actually changed (or on a manual refresh).
            try:
                from comfyui.metadata import (
                    auto_establish_lineage_from_job_metadata,
                    GALLERY_METADATA_FILE,
                )
                try:
                    metadata_mtime = os.path.getmtime(
                        os.path.join(current_path, GALLERY_METADATA_FILE)
                    )
                except OSError:
                    metadata_mtime = None

                should_run = (not is_auto) or metadata_mtime != previous_lineage_mtime
                if should_run:
                    lineage_count = auto_establish_lineage_from_job_metadata(current_path)
                    if lineage_count > 0:
                        logger.info(f"[Gallery] Established {lineage_count} lineage relationship(s)")
                    result["lineage_mtime"] = metadata_mtime
                    result["lineage_ran"] = True
            except Exception as e:
                logger.debug(f"[Gallery] Could not establish lineage: {e}")

            return result

        self._scan_worker = Worker(scan)
        self._scan_worker.signals.result.connect(self._on_scan_complete)
        self._scan_worker.signals.error.connect(self._on_scan_error)
        QThreadPool.globalInstance().start(self._scan_worker)

    def _on_scan_complete(self, result):
        """Handle scan completion (runs on the GUI thread)."""
        self._scan_in_progress = False
        self._scan_started_at = None

        if isinstance(result, dict):
            items = result.get("items")
            if result.get("snapshot") is not None:
                self._probe_snapshot = result["snapshot"]
            if result.get("lineage_ran"):
                self._last_lineage_mtime = result.get("lineage_mtime")
            skipped = bool(result.get("skipped"))
        else:
            # Defensive: older/plain list result
            items = result
            skipped = False

        # Show completion status only if we showed start status
        show_status = getattr(self, '_current_scan_show_status', True)

        if skipped:
            logger.debug("[Gallery] Poll probe unchanged — skipping rescan")
            if show_status and self.tab.animator:
                self.tab.animator.end_activity("gallery_scan", "Gallery: No changes")
            return

        if show_status and self.tab.animator:
            count = len(items) if items else 0
            self.tab.animator.end_activity(
                "gallery_scan", f"Gallery: Found {count} items"
            )

        self.tab._handle_scan_complete(items or [])

    def _on_scan_error(self, msg, tb):
        """Handle scan error."""
        self._scan_in_progress = False
        self._scan_started_at = None
        # A failed scan invalidates the probe snapshot — force a real rescan
        # on the next tick rather than trusting a stale comparison.
        self._probe_snapshot = None
        self.tab.log(f"[Gallery] Scan error: {msg}")

        # Hide loading overlay on error
        self.tab.hide_loading_overlay()

        # Show error status only if we showed start status
        show_status = getattr(self, '_current_scan_show_status', True)
        if show_status:
            if self.tab.animator:
                self.tab.animator.end_activity("gallery_scan")
            self.show_status(f"Gallery scan failed: {msg}", "error")

    # =========================================================================
    # FILE SYSTEM WATCHER
    # =========================================================================

    def start_watcher(self, output_dir):
        """Start or restart the file system watcher for auto-refresh."""
        from ui_components import Worker

        # Skip if already watching this path
        if self._watched_path == output_dir and self._watcher:
            return

        # Skip if setup already in progress
        if self._watcher_setup_in_progress:
            return

        self._watcher_setup_in_progress = True

        # Stop existing watcher
        self.stop_watcher()

        # For network paths, use polling instead of watcher
        if self._is_network_path(output_dir):
            self._start_network_polling()
            self._watcher_setup_in_progress = False
            return

        # Collect directories to watch (including subdirectories) in background
        def collect_directories():
            dirs_to_watch = [os.path.normpath(output_dir)]
            try:
                for root, dirs, files in os.walk(output_dir):
                    for d in dirs:
                        subdir = os.path.normpath(os.path.join(root, d))
                        dirs_to_watch.append(subdir)
            except Exception as e:
                self.tab.log(f"[Gallery] Error collecting watch directories: {e}")
            return dirs_to_watch

        # Capture the generation so a stop_watcher() while the collection
        # worker is in flight (user left the tab) cancels this setup —
        # otherwise the late result re-armed the watcher and kept rescanning
        # the share with the gallery hidden
        generation = self._watcher_generation

        self._watcher_setup_worker = Worker(collect_directories)
        self._watcher_setup_worker.signals.result.connect(
            lambda dirs, g=generation: self._on_watch_directories_collected(dirs, g)
        )
        self._watcher_setup_worker.signals.error.connect(self._on_watcher_setup_error)
        QThreadPool.globalInstance().start(self._watcher_setup_worker)

    def _on_watch_directories_collected(self, dirs_to_watch, generation=None):
        """Set up watcher with collected directories."""
        self._watcher_setup_in_progress = False

        if generation is not None and generation != self._watcher_generation:
            self.tab.log("[Gallery] Watcher setup cancelled (tab deactivated)")
            return

        if not dirs_to_watch:
            return

        output_dir = dirs_to_watch[0]

        # Create new watcher
        self._watcher = QFileSystemWatcher()
        self._watcher.directoryChanged.connect(self._on_directory_changed)

        # Add all directories
        added = self._watcher.addPaths(dirs_to_watch)
        if added:
            self._watched_path = output_dir
            self.tab.log(f"[Gallery] Watching {len(dirs_to_watch)} directories for changes")
        else:
            self.tab.log("[Gallery] Failed to add paths to file watcher")

    def _on_watcher_setup_error(self, msg, tb):
        """Handle watcher setup error."""
        self._watcher_setup_in_progress = False
        self.tab.log(f"[Gallery] Watcher setup error: {msg}")

    def reset_change_tracking(self):
        """Forget probe/lineage state (call when the gallery path changes)."""
        self._probe_snapshot = None
        self._last_lineage_mtime = None

    def _on_directory_changed(self, path):
        """Handle file system change notification."""
        self.tab.log(f"[Gallery] Directory changed: {path}")
        # Debounced refresh (silent - no status bar feedback for auto-refresh)
        self.on_refresh(show_status=False, auto=True)

    def stop_watcher(self):
        """Stop the file system watcher."""
        # Bump the generation token so any in-flight directory-collection
        # worker result is discarded instead of resurrecting the watcher
        self._watcher_generation = getattr(self, '_watcher_generation', 0) + 1
        if self._watcher:
            self._watcher.removePaths(self._watcher.directories())
            self._watcher = None
        self._watched_path = None

    # =========================================================================
    # NETWORK PATH POLLING
    # =========================================================================

    def _start_network_polling(self):
        """Start polling timer for network paths."""
        if self._poll_timer is None:
            self._poll_timer = QTimer()
            self._poll_timer.timeout.connect(self._on_poll_refresh)

        if not self._poll_timer.isActive():
            self._poll_timer.start(self._poll_interval)
            self.tab.log(f"[Gallery] Started network polling (every {self._poll_interval // 1000}s)")

    def stop_network_polling(self):
        """Stop the polling timer."""
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()
            self.tab.log("[Gallery] Stopped network polling")

    def _on_poll_refresh(self):
        """Handle polling timer tick."""
        # Only refresh if tab is visible (silent - no status bar feedback for auto-refresh)
        if self.tab.ui and self.tab.ui.isVisible():
            self.on_refresh(show_status=False, auto=True)

    def _is_network_path(self, path):
        """Check if a path is a network path (UNC or mapped drive pointing to network)."""
        if not path:
            return False

        # UNC paths
        if path.startswith('\\\\') or path.startswith('//'):
            return True

        # Check for mapped network drives (Windows)
        if os.name == 'nt' and len(path) >= 2 and path[1] == ':':
            import ctypes
            drive = path[0].upper() + ':'
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive + '\\')
            # DRIVE_REMOTE = 4
            return drive_type == 4

        return False
