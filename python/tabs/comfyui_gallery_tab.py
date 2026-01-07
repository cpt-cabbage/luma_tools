"""
ComfyUI Gallery tab module for Luma Tools.

Displays generated images from ComfyUI in a gallery view.
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

        # Track known images to detect new additions
        self._known_images = set()
        self._initial_scan_done = False

        # Set initial output directory to network path with user subfolder
        self._update_gallery_path()

        # Do an initial scan to establish baseline for detecting new images
        # This runs in background so it won't block startup
        self._on_refresh()

    def on_tab_activated(self):
        """Called when tab becomes visible - refresh gallery."""
        # Don't reset tracking when just switching tabs
        self._update_gallery_path(reset_tracking=False)
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
        worker.signals.result.connect(self._populate_gallery)
        worker.signals.error.connect(lambda msg, tb: self.log(f"Gallery scan error: {msg}"))
        QThreadPool.globalInstance().start(worker)

        self.ui.GalleryStatus.setText("Scanning...")

    def _scan_directory(self, output_dir):
        """Scan directory for image files (runs on worker thread)."""
        images = []
        supported_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.exr'}

        try:
            for filename in os.listdir(output_dir):
                ext = os.path.splitext(filename)[1].lower()
                if ext in supported_extensions:
                    full_path = os.path.join(output_dir, filename)
                    mtime = os.path.getmtime(full_path)
                    images.append((full_path, mtime))

            # Sort by modification time, newest first
            images.sort(key=lambda x: x[1], reverse=True)
        except Exception as e:
            self.log(f"Error scanning gallery directory: {e}")

        return [img[0] for img in images]

    def _populate_gallery(self, image_paths):
        """Populate the gallery with thumbnail widgets."""
        from ui_components import GalleryThumbnailWidget

        # Check for new images (only after initial scan)
        current_images = set(image_paths)
        new_images = current_images - self._known_images

        self.log(f"[Gallery] Populate: {len(image_paths)} images, {len(new_images)} new, initial_scan_done={self._initial_scan_done}")

        if self._initial_scan_done and new_images:
            # New images detected - request attention
            self.log(f"[Gallery] New images detected: {len(new_images)} - emitting request_attention signal")
            self.signals.request_attention.emit()
            self.log(f"[Gallery] request_attention signal emitted")

        # Update known images
        self._known_images = current_images
        self._initial_scan_done = True

        # Clear existing thumbnails
        while self._flow_layout.count():
            item = self._flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new thumbnails
        for path in image_paths:
            thumbnail = GalleryThumbnailWidget(path, self.ui.galleryThumbnailContainer)
            thumbnail.clicked.connect(self._on_thumbnail_clicked)
            self._flow_layout.addWidget(thumbnail)

        # Update status
        count = len(image_paths)
        if count == 0:
            self.ui.GalleryStatus.setText("No images found")
        elif count == 1:
            self.ui.GalleryStatus.setText("1 image found")
        else:
            self.ui.GalleryStatus.setText(f"{count} images found")

    def _on_thumbnail_clicked(self, image_path):
        """Handle thumbnail click - open the image."""
        try:
            os.startfile(image_path)
        except Exception as e:
            self.log(f"Error opening image: {e}")

    # =========================================================================
    # FILE SYSTEM WATCHER
    # =========================================================================

    def _start_watcher(self, output_dir):
        """Start or restart the file system watcher for auto-refresh."""
        from PySide2.QtCore import QFileSystemWatcher

        # Stop existing watcher
        if self._watcher:
            self._watcher.deleteLater()
            self._watcher = None

        # Start new watcher if directory is valid
        if output_dir and os.path.isdir(output_dir):
            self._watcher = QFileSystemWatcher([output_dir], self.main_window)
            self._watcher.directoryChanged.connect(self._on_directory_changed)
            self.log(f"Started watching gallery directory: {output_dir}")

    def _on_directory_changed(self, path):
        """Handle directory change notification."""
        # Debounce rapid changes with a short delay
        if self._refresh_timer is None:
            self._refresh_timer = QTimer(self.main_window)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._on_refresh)

        self._refresh_timer.start(500)  # 500ms debounce
