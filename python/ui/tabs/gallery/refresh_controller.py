"""
Gallery Refresh Controller.

Handles gallery content refresh mechanisms:
- File system watcher for local paths
- Polling timer for network paths
- Scan operations and caching
- Pre-warm cache handling from startup
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

        # Flag to skip first auto-refresh after prewarm (avoid duplicate scan)
        self._skip_next_auto_refresh = False

    def on_refresh(self, force=False, show_status=True):
        """
        Handle refresh request.

        Args:
            force: If True, bypass scan-in-progress check
            show_status: If True, show status bar feedback (False for auto-refreshes)
        """
        # Skip first automatic refresh after prewarm to avoid duplicate scan
        # Only skip non-forced, silent (automatic) refreshes
        if self._skip_next_auto_refresh and not force and not show_status:
            self._skip_next_auto_refresh = False
            self.tab.log("[Gallery] Skipping auto-refresh (prewarm cache active)")
            return

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

    def use_prewarm_cache_sync(self):
        """Use pre-warmed cache but defer display until after window is shown."""
        from ui.gallery_prewarm import get_prewarm_cache, clear_prewarm_cache
        from PySide6.QtCore import QTimer

        try:
            prewarm_cache = get_prewarm_cache()
            if prewarm_cache is not None and prewarm_cache.get('items'):
                # THREAD-SAFE: Lock during validation to prevent race conditions
                with self.tab._cache_lock:
                    # Normalize usernames: treat None and "" consistently
                    cached_username = prewarm_cache.get('username')
                    cached_username = cached_username.strip() if cached_username else None

                    current_username = self.tab._selected_user
                    current_username = current_username.strip() if current_username else None

                    # SECURITY: Validate that cache is for current user
                    if cached_username != current_username:
                        logger.warning(
                            f"[Gallery] Prewarm cache mismatch: cached for '{cached_username}', "
                            f"but current user is '{current_username}'. Discarding cache."
                        )
                        clear_prewarm_cache()
                        # Don't use the cache - let the gallery do a fresh scan
                        return

                    prewarm_items = prewarm_cache['items']
                    logger.info(f"[Gallery] Using pre-warmed cache for '{current_username}': {len(prewarm_items)} items")

                    # Mark initial scan as done IMMEDIATELY to prevent race condition
                    # with on_tab_activated() triggering a duplicate refresh
                    self.tab._initial_scan_done = True

                    # First real scan after prewarm should replace (not add incrementally)
                    # to avoid duplicates from any prewarm/full-scan output differences
                    self.tab._first_scan_after_prewarm = True

                    # Skip the next automatic refresh (network polling) since we have prewarm data
                    # This prevents the full scan from running and causing items to "pop up"
                    self._skip_next_auto_refresh = True

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
                logger.info("[Gallery] No pre-warmed cache available, will scan on tab activation")
        except Exception as e:
            logger.error(f"[Gallery] Error processing prewarm cache: {e}", exc_info=True)
            # CRITICAL: Always clear cache on error to prevent stale data reuse
            clear_prewarm_cache()

    def _process_deferred_prewarm(self):
        """Process deferred prewarm items (called after splash screen closes)."""
        if not hasattr(self, '_deferred_prewarm_items') or not self._deferred_prewarm_items:
            return

        items = self._deferred_prewarm_items
        del self._deferred_prewarm_items  # Free memory

        # Now it's safe to create widgets and display without blocking splash
        self._process_scan_results_sync(items)

        # _initial_scan_done already set in use_prewarm_cache_sync() to prevent race condition
        self.tab.log(f"[Gallery] Displayed {len(items)} pre-warmed items")

    def _enrich_prewarm_items(self, items):
        """Add missing data to pre-warmed items (job_prefix, is_input, metadata)."""
        if not items:
            return items

        try:
            from ui.tabs.gallery_loader import extract_job_prefix
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
                except Exception as e:
                    logger.debug(f"Could not load metadata for {dir_path}: {e}")
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
                        # Use allow_reverse_match=False for input/output detection
                        # to avoid matching input files to output job metadata
                        file_metadata = _lookup_file_metadata(full_metadata, filename, allow_reverse_match=False)
                        if file_metadata and isinstance(file_metadata, dict) and 'is_output' in file_metadata:
                            has_metadata = True
                            is_output = file_metadata.get('is_output', True)
                            job_prefix = file_metadata.get('job_prefix')
                            source_images = file_metadata.get('source_images', [])
                            if not isinstance(source_images, list):
                                source_images = []
                    except Exception as e:
                        logger.debug(f"Could not lookup metadata for {filename}: {e}")

                # Fall back to filename pattern detection
                # Note: is_output=False with job_prefix=None is valid for input files
                if is_output is None or (is_output and job_prefix is None):
                    try:
                        # Pass file_type so models/video/audio default to output correctly
                        file_type = item.get('type', 'image')
                        job_prefix, is_output = extract_job_prefix(filename, file_type)
                    except Exception as e:
                        logger.debug(f"Could not extract job prefix from {filename}: {e}")
                        job_prefix = None
                        # Models/video/audio default to output, images to input
                        file_type = item.get('type', 'image')
                        is_output = file_type in ('model', 'video', 'audio')

                    # Double-check: if pattern says output but file is a known source image,
                    # override to mark as input (handles files with misleading names like _001)
                    if is_output and item.get('type', 'image') == 'image':
                        try:
                            from comfyui.metadata import is_known_input_file
                            output_dir = os.path.dirname(item.get('path', ''))
                            if output_dir and is_known_input_file(output_dir, filename):
                                is_output = False
                                logger.debug(f"[Refresh] {filename} -> INPUT (known source image)")
                        except ImportError:
                            pass

                # Add enriched fields
                item['workflow'] = ''
                item['job_prefix'] = job_prefix
                item['is_input'] = not is_output
                item['source_images'] = source_images
                item['has_metadata'] = has_metadata

        # Bundle _view/_export pairs to match full scan behavior
        items = self._bundle_view_export_pairs(items)

        return items

    def _bundle_view_export_pairs(self, items):
        """Bundle _view and _export file pairs to match full scan behavior.

        This ensures prewarm items have the same structure as items from
        GalleryLoader.scan_directory(), preventing "new item" detection on refresh.
        """
        if not items:
            return items

        # Group items by directory
        items_by_dir = {}
        for item in items:
            dir_path = os.path.dirname(item['path'])
            if dir_path not in items_by_dir:
                items_by_dir[dir_path] = {}
            filename = os.path.basename(item['path'])
            items_by_dir[dir_path][filename] = item

        result = []
        for dir_path, items_dict in items_by_dir.items():
            bundled_files = set()

            for filename in list(items_dict.keys()):
                if filename in bundled_files:
                    continue

                base_name = None
                view_file = None
                export_file = None

                # Check if this is a _view or _export file
                if '_view' in filename:
                    parts = filename.rsplit('_view', 1)
                    if len(parts) == 2:
                        base_name = parts[0]
                        ext_part = parts[1]
                        view_file = filename
                        export_candidate = f"{base_name}_export{ext_part}"
                        if export_candidate in items_dict:
                            export_file = export_candidate
                elif '_export' in filename:
                    parts = filename.rsplit('_export', 1)
                    if len(parts) == 2:
                        base_name = parts[0]
                        ext_part = parts[1]
                        export_file = filename
                        view_candidate = f"{base_name}_view{ext_part}"
                        if view_candidate in items_dict:
                            view_file = view_candidate

                # If we found a pair, create a bundled item
                if base_name and view_file and export_file:
                    bundled_files.add(view_file)
                    bundled_files.add(export_file)

                    view_item = items_dict[view_file]
                    export_item = items_dict[export_file]

                    result.append({
                        'path': view_item['path'],
                        'export_path': export_item['path'],
                        'mtime': max(view_item['mtime'], export_item['mtime']),
                        'type': view_item['type'],
                        'name': view_item['name'],
                        'workflow': view_item.get('workflow', ''),
                        'job_prefix': view_item.get('job_prefix'),
                        'is_input': view_item.get('is_input', False),
                        'source_images': view_item.get('source_images', []),
                        'has_metadata': view_item.get('has_metadata', False),
                        'is_bundled': True
                    })
                else:
                    if filename not in bundled_files:
                        result.append(items_dict[filename])

        return result

    def _process_scan_results_sync(self, items):
        """Process scan results synchronously (for prewarm cache)."""
        # Store in cache
        self.tab._cached_items = items

        # Update known items for ALL items (not just filtered ones)
        # This prevents filtered-out items from being detected as "new" on every refresh
        # Paths are already normalized at scan source (os.path.normpath)
        for item in items:
            self.tab._known_items.add(item['path'])

        # Apply current filter and sort
        filtered_items = self.tab._filter_items(items)
        sorted_items = self.tab._manager.sort_items(filtered_items, self.tab._sort_mode)

        # Use display_items to properly create and display all widgets
        self.tab._manager.display_items(sorted_items, self.tab._view_mode)

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
