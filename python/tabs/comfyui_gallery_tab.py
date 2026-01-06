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
        self.ui.GalleryBrowse.clicked.connect(self._on_browse)
        self.ui.GalleryRefresh.clicked.connect(self._on_refresh)
        self.ui.GalleryOutputDir.textChanged.connect(self._on_output_dir_changed)

    def initialize(self):
        """Initialize the gallery tab."""
        from ui_components import FlowLayout

        # Setup flow layout for thumbnails
        self._flow_layout = FlowLayout(margin=10, spacing=10)
        self.ui.galleryThumbnailContainer.setLayout(self._flow_layout)

        # File system watcher for auto-refresh
        self._watcher = None
        self._refresh_timer = None

        # Try to sync output dir from ComfyUI tab if available
        self._sync_output_dir_from_comfyui()

    def on_tab_activated(self):
        """Called when tab becomes visible - refresh gallery."""
        self._on_refresh()

    def _sync_output_dir_from_comfyui(self):
        """Try to get output directory from ComfyUI tab."""
        # This will be called during initialize, before main_window tabs are fully set up
        # So we defer the sync to when the tab is first activated
        pass

    # =========================================================================
    # BROWSE / REFRESH
    # =========================================================================

    def _on_browse(self):
        """Browse for gallery output directory."""
        from settings_manager import get_last_browse_directory, set_last_browse_directory

        current_path = self.ui.GalleryOutputDir.text()
        if not current_path:
            current_path = get_last_browse_directory("comfyui_output")

        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window,
            "Select Output Directory",
            current_path or ""
        )
        if directory:
            self.ui.GalleryOutputDir.setText(directory)
            set_last_browse_directory("comfyui_output", directory)
            self._on_refresh()

    def _on_refresh(self):
        """Refresh the gallery with images from the output directory."""
        from ui_components import Worker

        output_dir = self.ui.GalleryOutputDir.text()
        if not output_dir or not os.path.isdir(output_dir):
            self.ui.GalleryStatus.setText("Invalid directory")
            return

        # Run scan on worker thread
        worker = Worker(self._scan_directory, output_dir)
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

    def _on_output_dir_changed(self, output_dir):
        """Handle gallery output directory change - restart watcher."""
        self._start_watcher(output_dir)

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
