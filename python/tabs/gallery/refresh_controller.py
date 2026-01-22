"""
Gallery Refresh Controller.

Handles gallery content refresh mechanisms:
- File system watcher for local paths
- Polling timer for network paths
- Scan operations and caching
- Pre-warm cache handling from startup
"""

import os
from PySide6.QtCore import QTimer, QThreadPool, QFileSystemWatcher


class RefreshController:
    """Manages refresh and file watching for the gallery."""

    def __init__(self, tab):
        """
        Initialize the refresh controller.

        Args:
            tab: Reference to the ComfyUIGalleryTab
        """
        self.tab = tab

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
            if hasattr(self.tab.main_window, 'animator'):
                self.tab.main_window.animator.show_info("Refresh already in progress")
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
        if show_status and hasattr(self.tab.main_window, 'animator'):
            self.tab.main_window.animator.start_activity(
                "gallery_scan", "Gallery: Scanning files"
            )

        # Scan in background thread
        def scan():
            return self.tab._loader.scan_directory(current_path)

        self._scan_worker = Worker(scan)
        self._scan_worker.signals.result.connect(self._on_scan_complete)
        self._scan_worker.signals.error.connect(self._on_scan_error)
        QThreadPool.globalInstance().start(self._scan_worker)

    def _on_scan_complete(self, items):
        """Handle scan completion."""
        self._scan_in_progress = False

        # Show completion status only if we showed start status
        show_status = getattr(self, '_current_scan_show_status', True)
        if show_status and hasattr(self.tab.main_window, 'animator'):
            count = len(items) if items else 0
            self.tab.main_window.animator.end_activity(
                "gallery_scan", f"Gallery: Found {count} items"
            )

        self.tab._on_scan_complete_impl(items)

    def _on_scan_error(self, msg, tb):
        """Handle scan error."""
        self._scan_in_progress = False
        self.tab.log(f"[Gallery] Scan error: {msg}")

        # Show error status only if we showed start status
        show_status = getattr(self, '_current_scan_show_status', True)
        if show_status and hasattr(self.tab.main_window, 'animator'):
            self.tab.main_window.animator.end_activity("gallery_scan")
            self.tab.main_window.animator.show_error(f"Gallery scan failed: {msg}")

    def use_prewarm_cache_sync(self):
        """Use pre-warmed cache but defer display until after window is shown."""
        from ui.gallery_prewarm import get_prewarm_cache, clear_prewarm_cache
        from PySide6.QtCore import QTimer

        prewarm_cache = get_prewarm_cache()
        if prewarm_cache is not None and prewarm_cache.get('items'):
            prewarm_items = prewarm_cache['items']
            self.tab.log(f"[Gallery] Using pre-warmed cache: {len(prewarm_items)} items")

            # Enrich items with additional data if needed
            items = self._enrich_prewarm_items(prewarm_items)

            # Store items for deferred processing after window is shown
            # This prevents blocking the splash screen
            self._deferred_prewarm_items = items

            # Clear the prewarm cache (one-time use)
            clear_prewarm_cache()

            # Schedule display for after splash screen closes (100ms delay)
            # This allows the main window to show first
            QTimer.singleShot(100, self._process_deferred_prewarm)
        else:
            self.tab.log("[Gallery] No pre-warmed cache available, will scan on tab activation")

    def _process_deferred_prewarm(self):
        """Process deferred prewarm items (called after splash screen closes)."""
        if not hasattr(self, '_deferred_prewarm_items') or not self._deferred_prewarm_items:
            return

        items = self._deferred_prewarm_items
        del self._deferred_prewarm_items  # Free memory

        # Now it's safe to create widgets and display without blocking splash
        self._process_scan_results_sync(items)

        # Mark initial scan as done
        self.tab._initial_scan_done = True
        self.tab.log(f"[Gallery] Displayed {len(items)} pre-warmed items")

    def _enrich_prewarm_items(self, items):
        """Add missing data to pre-warmed items (job_prefix, is_input, metadata)."""
        if not items:
            return items

        try:
            from tabs.comfyui_gallery_loader import extract_job_prefix
        except ImportError:
            # If can't import, return items as-is
            return items

        # Try to load metadata functions
        try:
            from comfyui.metadata import load_gallery_metadata, _lookup_file_metadata
            metadata_available = True
        except ImportError:
            load_gallery_metadata = None
            _lookup_file_metadata = None
            metadata_available = False

        # Group items by directory for metadata loading
        import os
        files_by_dir = {}
        for item in items:
            dir_path = os.path.dirname(item['path'])
            if dir_path not in files_by_dir:
                files_by_dir[dir_path] = []
            files_by_dir[dir_path].append(item)

        # Enrich each item
        for dir_path, dir_items in files_by_dir.items():
            # Load metadata for this directory if available
            full_metadata = {}
            if metadata_available and load_gallery_metadata:
                try:
                    full_metadata = load_gallery_metadata(dir_path)
                    if not isinstance(full_metadata, dict):
                        full_metadata = {}
                except Exception:
                    full_metadata = {}

            for item in dir_items:
                filename = os.path.basename(item['path'])

                # Check if already enriched
                if 'job_prefix' in item:
                    continue

                # Try metadata-based detection first
                is_output = None
                job_prefix = None
                source_images = []
                has_metadata = False

                if full_metadata and _lookup_file_metadata:
                    try:
                        file_metadata = _lookup_file_metadata(full_metadata, filename)
                        if file_metadata and isinstance(file_metadata, dict) and 'is_output' in file_metadata:
                            has_metadata = True
                            is_output = file_metadata.get('is_output', True)
                            job_prefix = file_metadata.get('job_prefix')
                            source_images = file_metadata.get('source_images', [])
                            if not isinstance(source_images, list):
                                source_images = []
                    except Exception:
                        pass

                # Fall back to filename pattern detection
                if is_output is None or job_prefix is None:
                    try:
                        job_prefix, is_output = extract_job_prefix(filename)
                    except Exception:
                        job_prefix = None
                        is_output = False

                # Add enriched fields
                item['workflow'] = ''
                item['job_prefix'] = job_prefix
                item['is_input'] = not is_output
                item['source_images'] = source_images
                item['has_metadata'] = has_metadata

        return items

    def _process_scan_results_sync(self, items):
        """Process scan results synchronously (for prewarm cache)."""
        # Store in cache
        self.tab._cached_items = items

        # Apply current filter and sort
        filtered_items = self.tab._filter_items(items)
        sorted_items = self.tab._manager.sort_items(filtered_items, self.tab._sort_mode)

        # Use display_items to properly create and display all widgets
        self.tab._manager.display_items(sorted_items, self.tab._view_mode)

        # Update known items for incremental refresh
        for item in sorted_items:
            self.tab._known_items.add(item['path'])

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
            dirs_to_watch = [output_dir]
            try:
                for root, dirs, files in os.walk(output_dir):
                    for d in dirs:
                        subdir = os.path.join(root, d)
                        dirs_to_watch.append(subdir)
            except Exception as e:
                self.tab.log(f"[Gallery] Error collecting watch directories: {e}")
            return dirs_to_watch

        self._watcher_setup_worker = Worker(collect_directories)
        self._watcher_setup_worker.signals.result.connect(self._on_watch_directories_collected)
        self._watcher_setup_worker.signals.error.connect(self._on_watcher_setup_error)
        QThreadPool.globalInstance().start(self._watcher_setup_worker)

    def _on_watch_directories_collected(self, dirs_to_watch):
        """Set up watcher with collected directories."""
        self._watcher_setup_in_progress = False

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
