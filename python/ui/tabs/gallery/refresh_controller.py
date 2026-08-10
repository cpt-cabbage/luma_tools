"""
Gallery Refresh Controller.

Handles gallery content refresh mechanisms:
- File system watcher for local paths
- Polling timer for network paths
- Scan operations and caching
"""

import os
import logging
from PySide6.QtCore import QTimer, QThreadPool, QFileSystemWatcher

from .base_manager import BaseGalleryManager

logger = logging.getLogger(__name__)


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
        self._poll_interval = 10000  # 10 seconds

        # Scan state
        self._scan_in_progress = False

    def on_refresh(self, force=False, show_status=True):
        """
        Handle refresh request.

        Args:
            force: If True, bypass scan-in-progress check
            show_status: If True, show status bar feedback (False for auto-refreshes)
        """
        if self._scan_in_progress and not force:
            self.tab.log("[Gallery] Refresh already in progress, skipping...")
            # Only show status message for user-initiated refreshes, not auto-refreshes
            if show_status:
                self.show_status("Refresh already in progress", "info")
            return

        # Store show_status for use in _do_refresh
        self._pending_show_status = show_status

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

        # Get show_status flag (default True for backward compatibility)
        show_status = getattr(self, '_pending_show_status', True)
        self._current_scan_show_status = show_status  # Store for completion handler

        # Clear cached items to force fresh scan
        self.tab._cached_items = None

        # Get current path
        current_path = self.tab._current_path

        if not current_path or not os.path.exists(current_path):
            self.tab.log(f"[Gallery] Path not found: {current_path}")
            self._scan_in_progress = False
            return

        self.tab.log(f"[Gallery] Scanning: {current_path}")

        # Show status feedback only for user-initiated refreshes
        if show_status and self.tab.animator:
            self.tab.animator.start_activity(
                "gallery_scan", "Gallery: Scanning files"
            )

        # Scan in background thread
        def scan():
            items = self.tab._loader.scan_directory(current_path)

            # Auto-establish lineage relationships in the background
            try:
                from comfyui.metadata import auto_establish_lineage_from_job_metadata
                lineage_count = auto_establish_lineage_from_job_metadata(current_path)
                if lineage_count > 0:
                    logger.info(f"[Gallery] Established {lineage_count} lineage relationship(s)")
            except Exception as e:
                logger.debug(f"[Gallery] Could not establish lineage: {e}")

            return items

        self._scan_worker = Worker(scan)
        self._scan_worker.signals.result.connect(self._on_scan_complete)
        self._scan_worker.signals.error.connect(self._on_scan_error)
        QThreadPool.globalInstance().start(self._scan_worker)

    def _on_scan_complete(self, items):
        """Handle scan completion."""
        self._scan_in_progress = False

        # Show completion status only if we showed start status
        show_status = getattr(self, '_current_scan_show_status', True)
        if show_status and self.tab.animator:
            count = len(items) if items else 0
            self.tab.animator.end_activity(
                "gallery_scan", f"Gallery: Found {count} items"
            )

        self.tab._handle_scan_complete(items)

    def _on_scan_error(self, msg, tb):
        """Handle scan error."""
        self._scan_in_progress = False
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

    def _on_directory_changed(self, path):
        """Handle file system change notification."""
        self.tab.log(f"[Gallery] Directory changed: {path}")
        # Debounced refresh (silent - no status bar feedback for auto-refresh)
        self.on_refresh(show_status=False)

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
            self.on_refresh(show_status=False)

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
