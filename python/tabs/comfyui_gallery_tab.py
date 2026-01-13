"""
ComfyUI Gallery tab module for Luma Tools.

Displays generated images and 3D models from ComfyUI in a gallery view.
"""

import os

from PySide2 import QtWidgets, QtCore
from PySide2.QtCore import Qt, QTimer, QThreadPool

from .base_tab import BaseTab


class ComfyUIGalleryTab(BaseTab):
    """Tab for viewing ComfyUI generated images."""

    @property
    def ui_file(self) -> str:
        return "comfyui_gallery.ui"

    @property
    def tab_name(self) -> str:
        return "ComfyUI Gallery"

    @property
    def tab_id(self) -> str:
        return "comfyui_gallery"

    def connect_signals(self):
        """Connect gallery tab signals."""
        self.ui.GallerySourceToggle.clicked.connect(self._on_source_toggle)
        self.ui.GalleryOpenExplorer.clicked.connect(self._on_open_explorer)
        self.ui.GalleryRefresh.clicked.connect(self._on_refresh)
        self.ui.GallerySortButton.clicked.connect(self._on_sort_button_clicked)
        self.ui.GalleryUserButton.clicked.connect(self._on_user_button_clicked)

    def initialize(self):
        """Initialize the gallery tab."""
        from ui_components import FlowLayout

        # Setup flow layout for thumbnails
        self._flow_layout = FlowLayout(margin=10, spacing=10)
        self.ui.galleryThumbnailContainer.setLayout(self._flow_layout)

        # File system watcher for auto-refresh
        self._watcher = None
        self._watched_path = None
        self._watcher_setup_in_progress = False
        self._refresh_timer = None

        # Source mode: "network" or "custom"
        self._source_mode = "network"
        self._custom_path = ""
        self._current_path = ""

        # Sort mode and options
        self._sort_mode = "date_desc"  # Default: newest first
        self._sort_options = [
            ("Date (Newest)", "date_desc"),
            ("Date (Oldest)", "date_asc"),
            ("Name (A-Z)", "name_asc"),
            ("Name (Z-A)", "name_desc"),
            ("Workflow", "workflow"),
        ]
        self._update_sort_button_text()

        # Track known images to detect new additions
        self._known_items = set()
        self._initial_scan_done = False

        # Track new (unviewed) items - these get highlighted until viewed
        self._new_items = set()

        # Cache for scanned items (to avoid rescanning when just changing sort)
        self._cached_items = None
        self._scan_in_progress = False

        # User selection for multi-user gallery viewing
        self._selected_user = self.app_state.user
        self._available_users = []

        # Cache for other users' gallery items (keyed by username)
        self._user_cache = {}
        self._precache_in_progress = set()  # Users currently being pre-cached

        # Initialize user selector and populate with available users
        self._populate_user_selector()

        # Hide "View Only" label initially (shown when viewing others' galleries)
        self.ui.GalleryViewOnlyLabel.hide()

        # Set initial output directory to network path with user subfolder
        self._update_gallery_path()

        # Check for pre-warmed cache from splash screen
        self._use_prewarm_cache()

    def _use_prewarm_cache(self):
        """Use pre-warmed cache from splash screen if available."""
        from ui_components import Worker

        try:
            from gallery_prewarm import get_prewarm_cache, clear_prewarm_cache

            cache = get_prewarm_cache()
            if cache and cache.get('items'):
                self.log(f"[Gallery] Using pre-warmed cache with {len(cache['items'])} items")

                # Clear the cache so it's not reused
                clear_prewarm_cache()

                # Enrich items with workflow metadata on worker thread
                self._scan_in_progress = True
                worker = Worker(self._enrich_prewarm_items, cache['items'])
                worker.signals.result.connect(self._on_scan_complete)
                worker.signals.error.connect(self._on_scan_error)
                QThreadPool.globalInstance().start(worker)
                return

        except ImportError:
            pass
        except Exception as e:
            self.log(f"[Gallery] Pre-warm cache error: {e}")

        # No cache available, do normal scan
        self._on_refresh()

    def _enrich_prewarm_items(self, items):
        """Enrich pre-warmed items with workflow metadata (runs on worker thread)."""
        from comfyui_service import get_workflow_preset_for_files

        # Group items by directory for batch metadata loading
        items_by_dir = {}  # dir_path -> [item, ...]
        for item in items:
            if 'workflow' not in item or not item['workflow']:
                output_dir = os.path.dirname(item['path'])
                if output_dir not in items_by_dir:
                    items_by_dir[output_dir] = []
                items_by_dir[output_dir].append(item)

        # Batch load metadata per directory
        for output_dir, dir_items in items_by_dir.items():
            try:
                filenames = [os.path.basename(item['path']) for item in dir_items]
                workflow_map = get_workflow_preset_for_files(output_dir, filenames)
                for item in dir_items:
                    filename = os.path.basename(item['path'])
                    item['workflow'] = workflow_map.get(filename, '')
            except Exception:
                for item in dir_items:
                    item['workflow'] = ''

        return items

    def _start_background_precache(self):
        """Start background pre-caching of other users' galleries."""
        if self._source_mode != "network":
            return

        # Get list of other users to pre-cache
        other_users = [u for u in self._available_users if u != self._selected_user]
        if not other_users:
            return

        # Start pre-caching each user's gallery in the background
        for username in other_users:
            self._precache_user(username)

    def _precache_user(self, username):
        """Pre-cache a single user's gallery in the background."""
        from ui_components import Worker

        # Skip if already cached or in progress
        if username in self._user_cache or username in self._precache_in_progress:
            return

        user_path = self._get_network_user_path(username)
        if not user_path:
            return

        self._precache_in_progress.add(username)

        worker = Worker(self._scan_directory, user_path)
        worker.signals.result.connect(lambda items, u=username: self._on_precache_complete(u, items))
        worker.signals.error.connect(lambda msg, tb, u=username: self._on_precache_error(u, msg))
        QThreadPool.globalInstance().start(worker)

    def _on_precache_complete(self, username, items):
        """Handle completion of background pre-cache for a user."""
        self._precache_in_progress.discard(username)

        if items:
            # Normalize items format
            if items and isinstance(items[0], tuple):
                items = [{'path': item[0], 'mtime': item[1], 'type': item[2] if len(item) > 2 else 'image',
                          'name': os.path.basename(item[0]).lower(), 'workflow': ''} for item in items]
            elif items and not isinstance(items[0], dict):
                items = [{'path': p, 'mtime': 0, 'type': 'image', 'name': os.path.basename(p).lower(),
                          'workflow': ''} for p in items]

            self._user_cache[username] = items
            self.log(f"[Gallery] Pre-cached {len(items)} items for user: {username}")

    def _on_precache_error(self, username, msg):
        """Handle pre-cache error for a user."""
        self._precache_in_progress.discard(username)
        # Silently ignore - pre-caching is best-effort

    def _update_sort_button_text(self):
        """Update the sort button text to show current selection."""
        for label, mode in self._sort_options:
            if mode == self._sort_mode:
                self.ui.GallerySortButton.setText(f"Sort: {label}")
                break

    def _on_sort_button_clicked(self):
        """Show popup menu with sort options."""
        from PySide2.QtWidgets import QMenu

        menu = QMenu(self.main_window)

        for label, mode in self._sort_options:
            action = menu.addAction(label)
            action.setData(mode)
            if mode == self._sort_mode:
                action.setCheckable(True)
                action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.GallerySortButton.mapToGlobal(
            self.ui.GallerySortButton.rect().bottomLeft()
        ))

        if action and action.data():
            self._select_sort_mode(action.data())

    def _select_sort_mode(self, mode):
        """Select a sort mode and update the gallery."""
        self._sort_mode = mode
        self._update_sort_button_text()
        self.log(f"[Gallery] Sort mode changed to: {self._sort_mode}")

        # Re-sort and redisplay using cached items if available
        if self._cached_items:
            sorted_items = self._sort_items(self._cached_items)
            # Use fast reorder if widgets are already loaded
            if hasattr(self, '_widget_cache') and self._widget_cache:
                self._reorder_widgets(sorted_items)
            else:
                self._display_items(sorted_items)
        else:
            # No cache, need to rescan
            self._on_refresh()

    def on_tab_activated(self):
        """Called when tab becomes visible - only refresh if needed."""
        # Refresh available users in case new users appeared
        self._populate_user_selector()

        # Update path in case settings changed
        self._update_gallery_path(reset_tracking=False)

        # Only refresh if we have no items loaded yet
        # File watcher handles new files automatically
        if not hasattr(self, '_pending_items') or not self._pending_items:
            if self._flow_layout.count() == 0:
                self._on_refresh()

    # =========================================================================
    # USER SELECTION (Multi-user gallery viewing)
    # =========================================================================

    def _discover_users(self):
        """Discover available users by scanning the network output path.

        Returns:
            list: Sorted list of usernames (folder names in network output path)
        """
        from settings_manager import get_comfyui_network_output_path

        network_path = get_comfyui_network_output_path()
        if not network_path or not os.path.isdir(network_path):
            return []

        users = []
        try:
            for entry in os.scandir(network_path):
                # Only include directories, skip hidden folders
                if entry.is_dir() and not entry.name.startswith('.'):
                    users.append(entry.name)
        except Exception as e:
            self.log(f"[Gallery] Error discovering users: {e}")
            return []

        return sorted(users, key=str.lower)

    def _populate_user_selector(self):
        """Populate the available users list and update button text."""
        # Discover available users
        self._available_users = self._discover_users()

        # Ensure current user is in the list
        current_user = self.app_state.user
        if current_user and current_user not in self._available_users:
            self._available_users.insert(0, current_user)

        # Update button text
        self._update_user_button_text()

        # Update visibility based on source mode
        self._update_user_selector_visibility()

    def _update_user_button_text(self):
        """Update the user button text to show current selection."""
        current_user = self.app_state.user
        if self._selected_user == current_user:
            self.ui.GalleryUserButton.setText(f"User: {self._selected_user} (You)")
        else:
            self.ui.GalleryUserButton.setText(f"User: {self._selected_user}")

    def _update_user_selector_visibility(self):
        """Show/hide user selector based on source mode."""
        # Only show user selector in network mode
        self.ui.GalleryUserButton.setVisible(self._source_mode == "network")

    def _on_user_button_clicked(self):
        """Show popup menu with user options."""
        from PySide2.QtWidgets import QMenu

        menu = QMenu(self.main_window)
        current_user = self.app_state.user

        for user in self._available_users:
            # Add "(You)" suffix for current user
            if user == current_user:
                action = menu.addAction(f"{user} (You)")
            else:
                action = menu.addAction(user)
            action.setData(user)
            if user == self._selected_user:
                action.setCheckable(True)
                action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.GalleryUserButton.mapToGlobal(
            self.ui.GalleryUserButton.rect().bottomLeft()
        ))

        if action and action.data():
            self._select_user(action.data())

    def _select_user(self, new_user):
        """Select a user and update the gallery.

        Args:
            new_user: The username to switch to
        """
        if new_user == self._selected_user:
            return

        # Store old user for potential caching
        old_user = self._selected_user

        self._selected_user = new_user
        self._update_user_button_text()
        self.log(f"[Gallery] Switched to user: {new_user}")

        # Update view-only indicator
        self._update_view_only_indicator()

        # Cache current user's items before switching (if we have them)
        if old_user and self._cached_items:
            self._user_cache[old_user] = self._cached_items

        # Clear widget cache (widgets need to be recreated)
        if hasattr(self, '_widget_cache'):
            self._widget_cache = {}
        self._known_items = set()
        self._new_items = set()
        self._initial_scan_done = False

        # Update path
        self._update_gallery_path()

        # Check if we have pre-cached data for this user
        if new_user in self._user_cache:
            self.log(f"[Gallery] Using pre-cached data for user: {new_user}")
            self._cached_items = self._user_cache[new_user]
            # Update known images from cache
            self._known_items = set(item['path'] for item in self._cached_items)
            self._initial_scan_done = True
            # Sort and display cached items
            sorted_items = self._sort_items(self._cached_items)
            self._display_items(sorted_items)
        else:
            # No cache, need to scan
            self._cached_items = None
            self._on_refresh()

    def _is_own_gallery(self):
        """Check if currently viewing own gallery.

        Returns:
            bool: True if viewing own gallery, False if viewing another user's
        """
        return self._selected_user == self.app_state.user

    def _update_view_only_indicator(self):
        """Update the view-only indicator visibility."""
        if self._is_own_gallery():
            self.ui.GalleryViewOnlyLabel.hide()
        else:
            self.ui.GalleryViewOnlyLabel.setText(f"Viewing {self._selected_user}'s gallery (View Only)")
            self.ui.GalleryViewOnlyLabel.show()

    def _get_network_user_path(self, username=None):
        """Get the network path with user subfolder.

        Args:
            username: Optional username override. If None, uses _selected_user.

        Returns:
            str: Full path to user's gallery folder, or empty string if not configured.
        """
        from settings_manager import get_comfyui_network_output_path

        network_path = get_comfyui_network_output_path()
        if network_path:
            user = username if username else self._selected_user
            return os.path.join(network_path, user)
        return ""

    def _update_gallery_path(self, reset_tracking=True):
        """Update the current gallery path based on source mode.

        Args:
            reset_tracking: If True, reset known images tracking. Set to False
                           when just refreshing the path without switching sources.
        """
        old_path = self._current_path

        if self._source_mode == "network":
            self._current_path = self._get_network_user_path()
            self.ui.GallerySourceToggle.setText("Network Folder")
        else:
            self._current_path = self._custom_path
            self.ui.GallerySourceToggle.setText("Custom Folder")

        # Only reset image tracking when path actually changes
        if reset_tracking and old_path != self._current_path:
            self.log(f"[Gallery] Path changed from {old_path} to {self._current_path} - resetting tracking")
            self._known_items = set()
            self._initial_scan_done = False

        # Start watcher on new path
        self._start_watcher(self._current_path)

    # =========================================================================
    # OPEN IN EXPLORER
    # =========================================================================

    def _on_open_explorer(self):
        """Open the current gallery folder in Windows Explorer."""
        # Refresh the path in case settings changed
        if self._source_mode == "network":
            self._current_path = self._get_network_user_path()

        if not self._current_path:
            self.log("No gallery path configured. Please configure the network output path in Settings.")
            return

        # Create the directory if it doesn't exist
        if not os.path.isdir(self._current_path):
            try:
                os.makedirs(self._current_path, exist_ok=True)
                self.log(f"Created gallery directory: {self._current_path}")
            except Exception as e:
                self.log(f"Could not create gallery directory: {self._current_path} - {e}")
                return

        try:
            # Use os.startfile for more reliable Windows Explorer opening
            os.startfile(self._current_path)
            self.log(f"Opened: {self._current_path}")
        except Exception as e:
            self.log(f"Error opening Explorer: {e}")

    # =========================================================================
    # SOURCE TOGGLE
    # =========================================================================

    def _on_source_toggle(self):
        """Toggle between network folder and custom folder."""
        if self._source_mode == "network":
            # Switch to custom - prompt for folder
            self._browse_custom_folder()
        else:
            # Switch back to network
            self._source_mode = "network"
            self._update_user_selector_visibility()
            self._update_view_only_indicator()
            self._update_gallery_path()
            self._on_refresh()

    def _browse_custom_folder(self):
        """Browse for a custom gallery folder."""
        from settings_manager import get_last_browse_directory, set_last_browse_directory

        current_path = self._custom_path or get_last_browse_directory("comfyui_gallery")

        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window,
            "Select Gallery Directory",
            current_path or ""
        )
        if directory:
            self._custom_path = directory
            self._source_mode = "custom"
            set_last_browse_directory("comfyui_gallery", directory)
            # Hide user selector and view-only label in custom mode
            self._update_user_selector_visibility()
            self.ui.GalleryViewOnlyLabel.hide()
            self._update_gallery_path()
            self._on_refresh()

    # =========================================================================
    # REFRESH
    # =========================================================================

    def _on_refresh(self):
        """Refresh the gallery with images from the current directory."""
        from ui_components import Worker

        # Skip if scan already in progress
        if self._scan_in_progress:
            return

        if not self._current_path:
            self.ui.GalleryStatus.setText("Invalid directory")
            return

        # Run scan on worker thread (includes isdir check)
        self._scan_in_progress = True
        worker = Worker(self._scan_directory, self._current_path)
        worker.signals.result.connect(self._on_scan_complete)
        worker.signals.error.connect(self._on_scan_error)
        QThreadPool.globalInstance().start(worker)

        self.ui.GalleryStatus.setText("Scanning...")

    def _scan_directory(self, output_dir):
        """Scan directory recursively for image and 3D model files (runs on worker thread)."""
        from comfyui_service import get_workflow_preset_for_files

        items = []

        # Check if directory exists (can be slow on network paths)
        if not os.path.isdir(output_dir):
            return items

        image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.exr'}
        model_extensions = {'.glb', '.gltf'}
        supported_extensions = image_extensions | model_extensions

        try:
            # First pass: collect all files grouped by directory
            # This allows us to batch load metadata per directory
            files_by_dir = {}  # dir_path -> [(filename, full_path, mtime, file_type), ...]

            for root, dirs, files in os.walk(output_dir):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in supported_extensions:
                        full_path = os.path.join(root, filename)
                        try:
                            mtime = os.path.getmtime(full_path)
                        except OSError:
                            continue
                        file_type = 'model' if ext in model_extensions else 'image'

                        if root not in files_by_dir:
                            files_by_dir[root] = []
                        files_by_dir[root].append((filename, full_path, mtime, file_type))

            # Second pass: batch load metadata per directory and create items
            for dir_path, file_list in files_by_dir.items():
                # Get workflow presets for all files in this directory at once
                filenames = [f[0] for f in file_list]
                try:
                    workflow_map = get_workflow_preset_for_files(dir_path, filenames)
                except Exception:
                    workflow_map = {}

                for filename, full_path, mtime, file_type in file_list:
                    items.append({
                        'path': full_path,
                        'mtime': mtime,
                        'type': file_type,
                        'name': filename.lower(),
                        'workflow': workflow_map.get(filename, '')
                    })
        except Exception as e:
            print(f"Error scanning gallery directory: {e}")

        return items

    def _on_scan_error(self, msg, tb):
        """Handle scan or prewarm enrichment error."""
        self._scan_in_progress = False
        self.log(f"[Gallery] Scan error: {msg}")

    def _on_scan_complete(self, items):
        """Handle scan completion - prepare data and start async population.

        Args:
            items: List of dicts with keys: path, mtime, type, name, workflow
        """
        self._scan_in_progress = False

        # Handle legacy format (tuples or plain paths)
        if items and isinstance(items[0], tuple):
            items = [{'path': item[0], 'mtime': item[1], 'type': item[2] if len(item) > 2 else 'image',
                      'name': os.path.basename(item[0]).lower(), 'workflow': ''} for item in items]
        elif items and not isinstance(items[0], dict):
            items = [{'path': p, 'mtime': 0, 'type': 'image', 'name': os.path.basename(p).lower(),
                      'workflow': ''} for p in items]

        # Cache items for re-sorting without rescanning
        self._cached_items = items

        # Check for new items (only after initial scan)
        file_paths = [item['path'] for item in items]
        current_items = set(file_paths)
        new_items = current_items - self._known_items

        self.log(f"[Gallery] Scan complete: {len(file_paths)} items, {len(new_items)} new")

        if self._initial_scan_done and new_items:
            # New items detected - request attention and show toast
            self.signals.request_attention.emit()
            # Count new images vs models
            new_images = sum(1 for item in items if item['path'] in new_items and item['type'] == 'image')
            new_models = sum(1 for item in items if item['path'] in new_items and item['type'] == 'model')
            self._show_new_items_toast(new_images, new_models)
            # Add to unviewed items set for highlighting
            self._new_items.update(new_items)

        # Update known items
        self._known_items = current_items

        # Start background pre-caching of other users on first scan
        if not self._initial_scan_done:
            # Delay pre-caching slightly to let the UI settle first
            QTimer.singleShot(1000, self._start_background_precache)

        self._initial_scan_done = True

        # Sort items based on current sort mode
        sorted_items = self._sort_items(items)

        # Display the sorted items
        self._display_items(sorted_items)

    def _sort_items(self, items):
        """Sort items based on current sort mode.

        Args:
            items: List of item dicts

        Returns:
            Sorted list of items
        """
        if self._sort_mode == "date_desc":
            return sorted(items, key=lambda x: x['mtime'], reverse=True)
        elif self._sort_mode == "date_asc":
            return sorted(items, key=lambda x: x['mtime'])
        elif self._sort_mode == "name_asc":
            return sorted(items, key=lambda x: x['name'])
        elif self._sort_mode == "name_desc":
            return sorted(items, key=lambda x: x['name'], reverse=True)
        elif self._sort_mode == "workflow":
            # Sort by workflow name, then by date within each workflow
            return sorted(items, key=lambda x: (x['workflow'] or 'zzz_unknown', -x['mtime']))
        else:
            return items

    def _display_items(self, items):
        """Display items in the gallery.

        Args:
            items: List of item dicts (already sorted)
        """
        # Clear existing thumbnails and widget cache
        container = self.ui.galleryThumbnailContainer
        container.setUpdatesEnabled(False)
        try:
            while self._flow_layout.count():
                item = self._flow_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        finally:
            container.setUpdatesEnabled(True)

        # Reset widget cache
        self._widget_cache = {}

        # Store items for widget creation
        self._pending_items = [(item['path'], item['type']) for item in items]
        self._load_index = 0

        # Count by type for status
        image_count = sum(1 for item in items if item['type'] == 'image')
        model_count = sum(1 for item in items if item['type'] == 'model')

        # Update status
        total_count = len(items)
        if total_count == 0:
            self.ui.GalleryStatus.setText("No files found")
        else:
            parts = []
            if image_count > 0:
                parts.append(f"{image_count} image{'s' if image_count != 1 else ''}")
            if model_count > 0:
                parts.append(f"{model_count} 3D model{'s' if model_count != 1 else ''}")
            self.ui.GalleryStatus.setText(" • ".join(parts) if parts else f"{total_count} files")

        # Create all widgets at once (with placeholders), then lazy load visible thumbnails
        self._create_all_widgets()

        # Connect scroll events for lazy loading (if not already connected)
        if not hasattr(self, '_scroll_connected') or not self._scroll_connected:
            scroll_area = self.ui.galleryScrollArea
            scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)
            scroll_area.horizontalScrollBar().valueChanged.connect(self._on_scroll)
            self._scroll_connected = True

        # Initial lazy load of visible thumbnails
        QTimer.singleShot(50, self._load_visible_thumbnails)

    def _reorder_widgets(self, items):
        """Reorder existing widgets without recreating them.

        This is much faster than _display_items when just changing sort order.

        Args:
            items: List of item dicts (already sorted)
        """
        container = self.ui.galleryThumbnailContainer
        container.setUpdatesEnabled(False)

        try:
            # Remove all widgets from layout (but don't delete them)
            while self._flow_layout.count():
                self._flow_layout.takeAt(0)

            # Add widgets back in sorted order using cache
            for item_dict in items:
                path = item_dict['path']
                if path in self._widget_cache:
                    widget = self._widget_cache[path]
                    self._flow_layout.addWidget(widget)

        finally:
            container.setUpdatesEnabled(True)

        # Force layout update
        self._flow_layout.invalidate()
        container.updateGeometry()

        # Trigger lazy loading for visible items after reorder
        QTimer.singleShot(50, self._load_visible_thumbnails)

    def _create_all_widgets(self):
        """Create all thumbnail widgets at once with placeholders (no thumbnail loading yet)."""
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget

        if not hasattr(self, '_pending_items') or not self._pending_items:
            return

        # Ensure widget cache exists
        if not hasattr(self, '_widget_cache'):
            self._widget_cache = {}

        # Block layout updates during batch insertion
        container = self.ui.galleryThumbnailContainer
        container.setUpdatesEnabled(False)

        # Check if viewing own gallery (for edit/delete permissions)
        is_editable = self._is_own_gallery()

        try:
            for path, file_type in self._pending_items:
                is_new = path in self._new_items
                # Use the file's parent directory for metadata lookup (not gallery root)
                # Metadata is stored per-workflow subfolder, not at the gallery root
                item_output_dir = os.path.dirname(path)

                if file_type == 'model':
                    thumbnail = GLBThumbnailWidget(
                        path,
                        container,
                        output_dir=item_output_dir,
                        editable=is_editable,
                        is_new=is_new
                    )
                    thumbnail.clicked.connect(self._on_thumbnail_clicked)
                    thumbnail.deleted.connect(self._on_item_deleted)
                    thumbnail.viewed.connect(self._on_item_viewed)
                else:
                    thumbnail = GalleryThumbnailWidget(
                        path,
                        container,
                        output_dir=item_output_dir,
                        editable=is_editable,
                        is_new=is_new
                    )
                    thumbnail.clicked.connect(self._on_thumbnail_clicked)
                    # Capture path in closure properly
                    thumbnail.fullscreen_requested.connect(
                        lambda img_path=path: self._open_viewer(img_path, fullscreen=True)
                    )
                    thumbnail.copy_settings_requested.connect(self._on_copy_settings_requested)
                    thumbnail.deleted.connect(self._on_item_deleted)
                    thumbnail.viewed.connect(self._on_item_viewed)

                # Cache widget by path for fast reordering
                self._widget_cache[path] = thumbnail
                self._flow_layout.addWidget(thumbnail)
        finally:
            container.setUpdatesEnabled(True)

    def _on_scroll(self, value=None):
        """Handle scroll events - trigger lazy loading of visible thumbnails."""
        # Debounce scroll events
        if not hasattr(self, '_scroll_timer'):
            self._scroll_timer = QTimer()
            self._scroll_timer.setSingleShot(True)
            self._scroll_timer.timeout.connect(self._load_visible_thumbnails)

        self._scroll_timer.start(100)  # 100ms debounce

    def _load_visible_thumbnails(self):
        """Load thumbnails for widgets that are currently visible in the viewport."""
        if not hasattr(self, '_widget_cache') or not self._widget_cache:
            return

        scroll_area = self.ui.galleryScrollArea
        viewport = scroll_area.viewport()
        viewport_rect = viewport.rect()

        # Get the visible area in container coordinates
        container = self.ui.galleryThumbnailContainer

        # Convert viewport rect to container coordinates
        visible_top = scroll_area.verticalScrollBar().value()
        visible_bottom = visible_top + viewport_rect.height()
        visible_left = scroll_area.horizontalScrollBar().value()
        visible_right = visible_left + viewport_rect.width()

        # Add buffer zone (load thumbnails slightly outside visible area for smoother scrolling)
        buffer = 200  # pixels
        visible_top = max(0, visible_top - buffer)
        visible_bottom += buffer
        visible_left = max(0, visible_left - buffer)
        visible_right += buffer

        # Check each widget's visibility and load if needed
        for widget in self._widget_cache.values():
            if not widget or not hasattr(widget, 'load_thumbnail_if_needed'):
                continue

            # Get widget position in container
            widget_rect = widget.geometry()

            # Check if widget intersects with visible area
            if (widget_rect.bottom() >= visible_top and
                widget_rect.top() <= visible_bottom and
                widget_rect.right() >= visible_left and
                widget_rect.left() <= visible_right):
                # Widget is visible - trigger lazy load
                widget.load_thumbnail_if_needed()

    def _show_new_items_toast(self, image_count, model_count):
        """Show a toast notification for new items added to gallery.

        Args:
            image_count: Number of new images
            model_count: Number of new 3D models
        """
        from ui_components import ToastNotification

        parts = []
        if image_count == 1:
            parts.append("1 new image")
        elif image_count > 1:
            parts.append(f"{image_count} new images")

        if model_count == 1:
            parts.append("1 new model")
        elif model_count > 1:
            parts.append(f"{model_count} new models")

        if parts:
            message = f"{' and '.join(parts)} added to Gallery"
            toast = ToastNotification(message, "success", self.main_window)
            toast.show_toast()

    def _on_thumbnail_clicked(self, image_path):
        """Handle thumbnail click - open embedded viewer."""
        self._open_viewer(image_path)

    def _on_item_deleted(self, item_path):
        """Handle item deletion - remove from caches."""
        # Remove from widget cache
        if hasattr(self, '_widget_cache') and item_path in self._widget_cache:
            del self._widget_cache[item_path]

        # Remove from cached items
        if self._cached_items:
            self._cached_items = [item for item in self._cached_items if item['path'] != item_path]

        # Remove from known images
        if item_path in self._known_items:
            self._known_items.discard(item_path)

        # Update status count
        if self._cached_items:
            image_count = sum(1 for item in self._cached_items if item['type'] == 'image')
            model_count = sum(1 for item in self._cached_items if item['type'] == 'model')
            total_count = len(self._cached_items)
            if total_count == 0:
                self.ui.GalleryStatus.setText("No files found")
            else:
                parts = []
                if image_count > 0:
                    parts.append(f"{image_count} image{'s' if image_count != 1 else ''}")
                if model_count > 0:
                    parts.append(f"{model_count} 3D model{'s' if model_count != 1 else ''}")
                self.ui.GalleryStatus.setText(" • ".join(parts) if parts else f"{total_count} files")

        self.log(f"[Gallery] Item deleted: {os.path.basename(item_path)}")

    def _on_item_viewed(self, item_path):
        """Handle item viewed - remove from new items set."""
        self._new_items.discard(item_path)

    def _on_copy_settings_requested(self, metadata):
        """Handle request to copy settings from an image to the ComfyUI tab."""
        comfyui_tab = self.main_window.get_tab("comfyui")
        if comfyui_tab:
            comfyui_tab.apply_settings_from_metadata(metadata)
        else:
            self.log("Could not find ComfyUI tab to apply settings")

    def _open_viewer(self, start_image=None, fullscreen=False):
        """Open the image viewer.

        Args:
            start_image: Path of image to start on (None = first image)
            fullscreen: If True, open in fullscreen mode
        """
        from ui_components import EmbeddedImageViewer, FullscreenImageViewer

        # Collect all image paths from the current gallery
        image_paths = self._get_image_paths()

        if not image_paths:
            self.log("No images to display")
            return

        # Find start index
        start_index = 0
        if start_image and start_image in image_paths:
            start_index = image_paths.index(start_image)

        if fullscreen:
            # Open fullscreen viewer as separate window
            # Don't pass output_dir - let viewer derive it from each image's path
            # (metadata is stored per-workflow subfolder, not at gallery root)
            self._fullscreen_viewer = FullscreenImageViewer(
                image_paths,
                start_index=start_index,
                output_dir=None,
                parent=None
            )
            self._fullscreen_viewer.copy_settings_requested.connect(self._on_copy_settings_requested)
            self._fullscreen_viewer.show()
        else:
            # Open embedded viewer within the tab
            self._show_embedded_viewer(image_paths, start_index)

    def _get_image_paths(self):
        """Get list of all media paths (images, 3D models, videos) from current gallery."""
        media_paths = []
        for i in range(self._flow_layout.count()):
            item = self._flow_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                # Include all media: images and 3D models
                if hasattr(widget, 'image_path'):
                    media_paths.append(widget.image_path)
                elif hasattr(widget, 'model_path'):
                    media_paths.append(widget.model_path)
        return media_paths

    def _show_embedded_viewer(self, image_paths, start_index):
        """Show the embedded image viewer, hiding the gallery grid."""
        # Hide gallery elements
        self.ui.galleryScrollArea.hide()

        # Create embedded viewer if not exists
        if not hasattr(self, '_embedded_viewer') or self._embedded_viewer is None:
            # Show loading indicator for first-time viewer creation
            self._show_viewer_loading()

            # Create viewer asynchronously to avoid UI freeze
            QTimer.singleShot(10, lambda: self._create_embedded_viewer_async(image_paths, start_index))
        else:
            # Update existing viewer (fast path - no lag)
            self._embedded_viewer.image_paths = image_paths
            self._embedded_viewer.current_index = start_index
            self._embedded_viewer._load_current_image()
            self._embedded_viewer.show()
            self._embedded_viewer.setFocus()

    def _show_viewer_loading(self):
        """Show a loading indicator with spinner while the viewer is being created."""
        from PySide2.QtWidgets import QLabel, QWidget, QVBoxLayout
        from PySide2.QtCore import Qt
        from ui_components import SpinnerWidget

        # Create a temporary loading widget if not exists
        if not hasattr(self, '_viewer_loading_widget'):
            self._viewer_loading_widget = QWidget(self.ui)
            self._viewer_loading_widget.setStyleSheet("background-color: #1a1a1a;")
            layout = QVBoxLayout(self._viewer_loading_widget)
            layout.setAlignment(Qt.AlignCenter)

            # Add spinner
            spinner = SpinnerWidget()
            spinner.setFixedSize(40, 40)
            layout.addWidget(spinner, alignment=Qt.AlignCenter)

            # Add label
            loading_label = QLabel("Loading viewer...")
            loading_label.setStyleSheet("color: #888888; font-size: 14px;")
            loading_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(loading_label)

            # Store spinner reference for starting animation
            self._viewer_loading_spinner = spinner

            # Insert into main layout
            self.ui.galleryMainLayout.insertWidget(1, self._viewer_loading_widget)

        # Start spinner animation
        if hasattr(self, '_viewer_loading_spinner'):
            self._viewer_loading_spinner.start()

        self._viewer_loading_widget.show()

    def _create_embedded_viewer_async(self, image_paths, start_index):
        """Create the embedded viewer (called after a short delay to let UI update)."""
        from ui_components import EmbeddedImageViewer

        # Stop spinner and hide loading widget
        if hasattr(self, '_viewer_loading_spinner'):
            self._viewer_loading_spinner.stop()
        if hasattr(self, '_viewer_loading_widget'):
            self._viewer_loading_widget.hide()

        # Create the viewer
        # Don't pass output_dir - let viewer derive it from each image's path
        # (metadata is stored per-workflow subfolder, not at gallery root)
        self._embedded_viewer = EmbeddedImageViewer(
            image_paths,
            start_index=start_index,
            output_dir=None,
            parent=self.ui
        )
        self._embedded_viewer.closed.connect(self._close_embedded_viewer)
        self._embedded_viewer.view_fullscreen.connect(self._on_view_fullscreen)
        self._embedded_viewer.copy_settings_requested.connect(self._on_copy_settings_requested)

        # Insert viewer into the main layout (after header, before footer)
        self.ui.galleryMainLayout.insertWidget(1, self._embedded_viewer)

        self._embedded_viewer.show()
        self._embedded_viewer.setFocus()

    def _close_embedded_viewer(self):
        """Close the embedded viewer and show gallery grid."""
        if hasattr(self, '_embedded_viewer') and self._embedded_viewer:
            self._embedded_viewer.hide()

        # Show gallery elements
        self.ui.galleryScrollArea.show()

    def _on_view_fullscreen(self, image_path, index):
        """Handle request to view in fullscreen from embedded viewer."""
        self._open_viewer(image_path, fullscreen=True)

    # =========================================================================
    # FILE SYSTEM WATCHER
    # =========================================================================

    def _start_watcher(self, output_dir):
        """Start or restart the file system watcher for auto-refresh.

        Watches the root directory and all existing subfolders recursively.
        Directory collection is done async to avoid blocking the UI.
        """
        from ui_components import Worker

        # Skip if already watching this directory or setup is in progress for same path
        if self._watched_path == output_dir and (self._watcher or self._watcher_setup_in_progress):
            return

        # Stop existing watcher
        if self._watcher:
            self._watcher.deleteLater()
            self._watcher = None

        # Track the path we're setting up (to avoid duplicate setups)
        self._watched_path = output_dir
        self._watcher_setup_in_progress = True

        # Start new watcher if directory is valid (check async to avoid network lag)
        if output_dir:
            # Collect directories async to avoid blocking UI (includes isdir check)
            worker = Worker(self._collect_watch_directories, output_dir)
            worker.signals.result.connect(self._on_watch_directories_collected)
            worker.signals.error.connect(self._on_watcher_setup_error)
            QThreadPool.globalInstance().start(worker)
        else:
            self._watcher_setup_in_progress = False

    def _collect_watch_directories(self, output_dir):
        """Collect all directories to watch (runs on worker thread)."""
        # Check if directory exists (can be slow on network paths)
        if not os.path.isdir(output_dir):
            return None

        dirs_to_watch = [output_dir]
        for root, dirs, files in os.walk(output_dir):
            for dir_name in dirs:
                dirs_to_watch.append(os.path.join(root, dir_name))
        return (output_dir, dirs_to_watch)

    def _on_watch_directories_collected(self, result):
        """Handle watch directory collection completion (runs on main thread)."""
        self._watcher_setup_in_progress = False

        if result is None:
            return

        from PySide2.QtCore import QFileSystemWatcher

        output_dir, dirs_to_watch = result

        # Verify we still want to watch this path (might have changed while async)
        if self._watched_path != output_dir:
            return

        # Create the watcher on the main thread
        self._watcher = QFileSystemWatcher(dirs_to_watch, self.main_window)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self.log(f"Started watching gallery directory: {output_dir} ({len(dirs_to_watch)} folders)")

    def _on_watcher_setup_error(self, msg, tb):
        """Handle watcher setup error."""
        self._watcher_setup_in_progress = False
        self.log(f"[Gallery] Watcher setup error: {msg}")

    def _on_directory_changed(self, path):
        """Handle directory change notification."""
        # Debounce rapid changes with a short delay
        if self._refresh_timer is None:
            self._refresh_timer = QTimer(self.main_window)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._on_refresh)

        self._refresh_timer.start(500)  # 500ms debounce
