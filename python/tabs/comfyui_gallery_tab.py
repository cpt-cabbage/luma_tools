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
        self.ui.GallerySortCombo.currentIndexChanged.connect(self._on_sort_changed)

    def initialize(self):
        """Initialize the gallery tab."""
        from ui_components import FlowLayout

        # Setup flow layout for thumbnails
        self._flow_layout = FlowLayout(margin=10, spacing=10)
        self.ui.galleryThumbnailContainer.setLayout(self._flow_layout)

        # File system watcher for auto-refresh
        self._watcher = None
        self._refresh_timer = None

        # Source mode: "network" or "custom"
        self._source_mode = "network"
        self._custom_path = ""
        self._current_path = ""

        # Sort mode
        self._sort_mode = "date_desc"  # Default: newest first
        self._setup_sort_options()

        # Track known images to detect new additions
        self._known_images = set()
        self._initial_scan_done = False

        # Cache for scanned items (to avoid rescanning when just changing sort)
        self._cached_items = None

        # Set initial output directory to network path with user subfolder
        self._update_gallery_path()

        # Check for pre-warmed cache from splash screen
        self._use_prewarm_cache()

    def _use_prewarm_cache(self):
        """Use pre-warmed cache from splash screen if available."""
        try:
            from gallery_prewarm import get_prewarm_cache, clear_prewarm_cache

            cache = get_prewarm_cache()
            if cache and cache.get('items'):
                self.log(f"[Gallery] Using pre-warmed cache with {len(cache['items'])} items")

                # Use the pre-warmed items directly
                items = cache['items']

                # Add workflow metadata (not included in basic prewarm scan)
                # This enriches items with workflow info for sorting
                from comfyui_service import get_image_metadata
                for item in items:
                    if 'workflow' not in item or not item['workflow']:
                        try:
                            output_dir = os.path.dirname(item['path'])
                            filename = os.path.basename(item['path'])
                            metadata = get_image_metadata(output_dir, filename)
                            if metadata:
                                item['workflow'] = metadata.get('workflow_preset', '') or ''
                        except Exception:
                            item['workflow'] = ''

                # Process items through normal flow
                self._on_scan_complete(items)

                # Clear the cache so it's not reused
                clear_prewarm_cache()
                return

        except ImportError:
            pass
        except Exception as e:
            self.log(f"[Gallery] Pre-warm cache error: {e}")

        # No cache available, do normal scan
        self._on_refresh()

    def _setup_sort_options(self):
        """Set up the sort dropdown options."""
        self.ui.GallerySortCombo.blockSignals(True)
        self.ui.GallerySortCombo.clear()
        self.ui.GallerySortCombo.addItem("Date (Newest)", "date_desc")
        self.ui.GallerySortCombo.addItem("Date (Oldest)", "date_asc")
        self.ui.GallerySortCombo.addItem("Name (A-Z)", "name_asc")
        self.ui.GallerySortCombo.addItem("Name (Z-A)", "name_desc")
        self.ui.GallerySortCombo.addItem("Workflow", "workflow")
        self.ui.GallerySortCombo.setCurrentIndex(0)
        self.ui.GallerySortCombo.blockSignals(False)

    def _on_sort_changed(self, index):
        """Handle sort mode change."""
        self._sort_mode = self.ui.GallerySortCombo.currentData()
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
        # Update path in case settings changed
        self._update_gallery_path(reset_tracking=False)

        # Only refresh if we have no items loaded yet
        # File watcher handles new files automatically
        if not hasattr(self, '_pending_items') or not self._pending_items:
            if self._flow_layout.count() == 0:
                self._on_refresh()

    def _get_network_user_path(self):
        """Get the network path with user subfolder."""
        from settings_manager import get_comfyui_network_output_path

        network_path = get_comfyui_network_output_path()
        if network_path:
            return os.path.join(network_path, self.app_state.user)
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
            self._known_images = set()
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
            self._update_gallery_path()
            self._on_refresh()

    # =========================================================================
    # REFRESH
    # =========================================================================

    def _on_refresh(self):
        """Refresh the gallery with images from the current directory."""
        from ui_components import Worker

        if not self._current_path or not os.path.isdir(self._current_path):
            self.ui.GalleryStatus.setText("Invalid directory")
            return

        # Run scan on worker thread
        worker = Worker(self._scan_directory, self._current_path)
        worker.signals.result.connect(self._on_scan_complete)
        worker.signals.error.connect(lambda msg, tb: self.log(f"Gallery scan error: {msg}"))
        QThreadPool.globalInstance().start(worker)

        self.ui.GalleryStatus.setText("Scanning...")

    def _scan_directory(self, output_dir):
        """Scan directory recursively for image and 3D model files (runs on worker thread)."""
        from comfyui_service import get_image_metadata

        items = []
        image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.exr'}
        model_extensions = {'.glb', '.gltf'}
        supported_extensions = image_extensions | model_extensions

        try:
            # Walk directory recursively to find files in subfolders
            for root, dirs, files in os.walk(output_dir):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in supported_extensions:
                        full_path = os.path.join(root, filename)
                        mtime = os.path.getmtime(full_path)
                        file_type = 'model' if ext in model_extensions else 'image'

                        # Get workflow preset from metadata (for sorting)
                        workflow = ""
                        try:
                            metadata = get_image_metadata(root, filename)
                            if metadata:
                                workflow = metadata.get('workflow_preset', '') or ''
                        except Exception:
                            pass

                        items.append({
                            'path': full_path,
                            'mtime': mtime,
                            'type': file_type,
                            'name': filename.lower(),
                            'workflow': workflow
                        })
        except Exception as e:
            print(f"Error scanning gallery directory: {e}")

        return items

    def _on_scan_complete(self, items):
        """Handle scan completion - prepare data and start async population.

        Args:
            items: List of dicts with keys: path, mtime, type, name, workflow
        """
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
        new_items = current_items - self._known_images

        self.log(f"[Gallery] Scan complete: {len(file_paths)} items, {len(new_items)} new")

        if self._initial_scan_done and new_items:
            # New items detected - request attention and show toast
            self.signals.request_attention.emit()
            # Count new images vs models
            new_images = sum(1 for item in items if item['path'] in new_items and item['type'] == 'image')
            new_models = sum(1 for item in items if item['path'] in new_items and item['type'] == 'model')
            self._show_new_items_toast(new_images, new_models)

        # Update known items
        self._known_images = current_items
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

        # Store items for async loading
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

        # Start async loading of thumbnails
        self._load_next_batch()

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

    def _load_next_batch(self):
        """Load the next batch of thumbnails asynchronously."""
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget

        if not hasattr(self, '_pending_items') or self._load_index >= len(self._pending_items):
            return

        # Ensure widget cache exists
        if not hasattr(self, '_widget_cache'):
            self._widget_cache = {}

        # Larger batch size for faster loading (thumbnails load async anyway)
        batch_size = 15
        end_index = min(self._load_index + batch_size, len(self._pending_items))

        # Block layout updates during batch insertion
        container = self.ui.galleryThumbnailContainer
        container.setUpdatesEnabled(False)

        try:
            for i in range(self._load_index, end_index):
                path, file_type = self._pending_items[i]

                if file_type == 'model':
                    thumbnail = GLBThumbnailWidget(
                        path,
                        container,
                        output_dir=self._current_path
                    )
                    thumbnail.clicked.connect(self._on_thumbnail_clicked)
                    thumbnail.deleted.connect(self._on_item_deleted)
                else:
                    thumbnail = GalleryThumbnailWidget(
                        path,
                        container,
                        output_dir=self._current_path
                    )
                    thumbnail.clicked.connect(self._on_thumbnail_clicked)
                    # Capture path in closure properly
                    thumbnail.fullscreen_requested.connect(
                        lambda img_path=path: self._open_viewer(img_path, fullscreen=True)
                    )
                    thumbnail.copy_settings_requested.connect(self._on_copy_settings_requested)
                    thumbnail.deleted.connect(self._on_item_deleted)

                # Cache widget by path for fast reordering
                self._widget_cache[path] = thumbnail
                self._flow_layout.addWidget(thumbnail)
        finally:
            container.setUpdatesEnabled(True)

        self._load_index = end_index

        # Schedule next batch if more items remain
        if self._load_index < len(self._pending_items):
            QTimer.singleShot(20, self._load_next_batch)

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
        if item_path in self._known_images:
            self._known_images.discard(item_path)

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
            self._fullscreen_viewer = FullscreenImageViewer(
                image_paths,
                start_index=start_index,
                output_dir=self._current_path,
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
        self._embedded_viewer = EmbeddedImageViewer(
            image_paths,
            start_index=start_index,
            output_dir=self._current_path,
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
        """
        from PySide2.QtCore import QFileSystemWatcher

        # Stop existing watcher
        if self._watcher:
            self._watcher.deleteLater()
            self._watcher = None

        # Start new watcher if directory is valid
        if output_dir and os.path.isdir(output_dir):
            # Collect all directories to watch (root + subfolders)
            dirs_to_watch = [output_dir]
            for root, dirs, files in os.walk(output_dir):
                for dir_name in dirs:
                    dirs_to_watch.append(os.path.join(root, dir_name))

            self._watcher = QFileSystemWatcher(dirs_to_watch, self.main_window)
            self._watcher.directoryChanged.connect(self._on_directory_changed)
            self.log(f"Started watching gallery directory: {output_dir} ({len(dirs_to_watch)} folders)")

    def _on_directory_changed(self, path):
        """Handle directory change notification."""
        # Debounce rapid changes with a short delay
        if self._refresh_timer is None:
            self._refresh_timer = QTimer(self.main_window)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._on_refresh)

        self._refresh_timer.start(500)  # 500ms debounce
