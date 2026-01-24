"""
Gallery Viewer Manager.

Handles embedded and fullscreen viewer lifecycle:
- Opening/closing embedded viewer
- Fullscreen viewer management
- Loading states and spinner display
- Image navigation
"""

from PySide6.QtCore import QTimer

from .base_manager import BaseGalleryManager


class ViewerManager(BaseGalleryManager):
    """Manages viewer lifecycle for the gallery."""

    def __init__(self, tab):
        """
        Initialize the viewer manager.

        Args:
            tab: Reference to the ComfyUIGalleryTab
        """
        super().__init__(tab)

        # Viewer state
        self._embedded_viewer = None
        self._fullscreen_viewer = None
        self._viewer_creation_pending = False
        self._pending_image_paths = []
        self._pending_start_index = 0
        self._viewer_loading_widget = None
        self._viewer_loading_spinner = None

    def open_viewer(self, start_image=None, fullscreen=False, image_paths=None):
        """
        Open the image viewer.

        Args:
            start_image: Path of image to start on (None = first image)
            fullscreen: If True, open in fullscreen mode
            image_paths: Optional list of specific image paths to show (for filtered view)
        """
        from ui_components import EmbeddedImageViewer, FullscreenImageViewer

        # Use provided image paths or collect all from gallery
        if image_paths is None:
            image_paths = self._get_image_paths()

        if not image_paths:
            self.tab.log("No images to display")
            return

        # Find start index
        start_index = 0
        if start_image and start_image in image_paths:
            start_index = image_paths.index(start_image)

        if fullscreen:
            self._open_fullscreen(image_paths, start_index)
        else:
            self._show_embedded(image_paths, start_index)

    def _open_fullscreen(self, image_paths, start_index):
        """Open fullscreen viewer as separate window."""
        from ui_components import FullscreenImageViewer

        # Don't pass output_dir - let viewer derive it from each image's path
        # (metadata is stored per-workflow subfolder, not at gallery root)
        self._fullscreen_viewer = FullscreenImageViewer(
            image_paths,
            start_index=start_index,
            output_dir=None,
            parent=None
        )
        self._fullscreen_viewer.copy_settings_requested.connect(self.tab._on_copy_settings_requested)
        self._fullscreen_viewer.image_viewed.connect(self.tab._on_item_viewed)
        self._fullscreen_viewer.show()

    def _show_embedded(self, image_paths, start_index):
        """Show the embedded image viewer, hiding the gallery grid."""
        # Hide the gallery splitter (contains scroll area and groups panel)
        if hasattr(self.tab, '_gallery_splitter'):
            self.tab._gallery_splitter.hide()
        else:
            # Fallback for layouts without splitter
            self.tab.ui.galleryScrollArea.hide()
            if hasattr(self.tab, '_groups_panel'):
                self.tab._groups_panel.hide()

        # Check if viewer creation is already in progress
        if self._viewer_creation_pending:
            # Update the pending parameters for when creation completes
            self._pending_image_paths = image_paths
            self._pending_start_index = start_index
            return

        # Create embedded viewer if not exists
        if self._embedded_viewer is None:
            # Mark creation as in progress to prevent duplicate creations
            self._viewer_creation_pending = True
            self._pending_image_paths = image_paths
            self._pending_start_index = start_index

            # Show loading indicator for first-time viewer creation
            self._show_loading()

            # Create viewer asynchronously to avoid UI freeze
            QTimer.singleShot(10, self._create_embedded_async)
        else:
            # Update existing viewer (fast path - no lag)
            self._embedded_viewer.image_paths = image_paths
            self._embedded_viewer.current_index = start_index
            self._embedded_viewer._load_current_image()
            self._embedded_viewer.show()
            self._embedded_viewer.setFocus()

    def _show_loading(self):
        """Show a loading indicator with spinner while the viewer is being created."""
        from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout
        from PySide6.QtCore import Qt
        from ui_components import SpinnerWidget

        # Create a temporary loading widget if not exists
        if self._viewer_loading_widget is None:
            self._viewer_loading_widget = QWidget(self.tab.ui)
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
            self.tab.ui.galleryMainLayout.insertWidget(1, self._viewer_loading_widget)
            # Set stretch factor so loading widget expands to fill available space
            self.tab.ui.galleryMainLayout.setStretch(1, 1)

        # Start spinner animation
        if self._viewer_loading_spinner:
            self._viewer_loading_spinner.start()

        self._viewer_loading_widget.show()

    def _create_embedded_async(self):
        """Create the embedded viewer (called after a short delay to let UI update)."""
        from ui_components import EmbeddedImageViewer

        # Get the most recent parameters (may have been updated by rapid clicks)
        image_paths = self._pending_image_paths
        start_index = self._pending_start_index

        # Stop spinner and hide loading widget
        if self._viewer_loading_spinner:
            self._viewer_loading_spinner.stop()
        if self._viewer_loading_widget:
            self._viewer_loading_widget.hide()

        # Create the viewer
        # Don't pass output_dir - let viewer derive it from each image's path
        # (metadata is stored per-workflow subfolder, not at gallery root)
        self._embedded_viewer = EmbeddedImageViewer(
            image_paths,
            start_index=start_index,
            output_dir=None,
            parent=self.tab.ui
        )
        self._embedded_viewer.closed.connect(self.close_embedded)
        self._embedded_viewer.view_fullscreen.connect(self._on_view_fullscreen)
        self._embedded_viewer.copy_settings_requested.connect(self.tab._on_copy_settings_requested)
        self._embedded_viewer.image_viewed.connect(self.tab._on_item_viewed)

        # Set favorites manager for like button functionality
        favorites_manager = getattr(self.tab, '_favorites_manager', None)
        if favorites_manager:
            self._embedded_viewer.set_favorites_manager(favorites_manager)
            self._embedded_viewer.like_toggled.connect(self._on_viewer_like_toggled)

        # Insert viewer into the main layout (after header, before footer)
        self.tab.ui.galleryMainLayout.insertWidget(1, self._embedded_viewer)
        # Set stretch factor so viewer expands to fill available space
        self.tab.ui.galleryMainLayout.setStretch(1, 1)

        self._embedded_viewer.show()
        self._embedded_viewer.setFocus()

        # Clear creation-in-progress flag
        self._viewer_creation_pending = False

    def _on_viewer_like_toggled(self, path, is_liked):
        """Handle like toggle from the viewer.

        Args:
            path: Path of the item
            is_liked: New like state
        """
        # Show status message
        if hasattr(self.tab, 'show_status_message'):
            if is_liked:
                self.tab.show_status_message("♥ Added to Likes")
            else:
                self.tab.show_status_message("Removed from Likes")

        # Update the thumbnail widget's like state if visible
        if hasattr(self.tab, '_widget_cache') and path in self.tab._widget_cache:
            from shiboken6 import isValid
            widget = self.tab._widget_cache[path]
            if isValid(widget) and hasattr(widget, 'update_favorites_state'):
                widget.update_favorites_state()

    def close_embedded(self):
        """Close the embedded viewer and show gallery grid."""
        # Clear any pending creation
        self._viewer_creation_pending = False

        # Hide loading widget if visible
        if self._viewer_loading_spinner:
            self._viewer_loading_spinner.stop()
        if self._viewer_loading_widget:
            self._viewer_loading_widget.hide()

        if self._embedded_viewer:
            self._embedded_viewer.hide()

        # Show the gallery splitter (contains scroll area and groups panel)
        if hasattr(self.tab, '_gallery_splitter'):
            self.tab._gallery_splitter.show()
        else:
            # Fallback for layouts without splitter
            self.tab.ui.galleryScrollArea.show()
            if hasattr(self.tab, '_groups_panel'):
                self.tab._groups_panel.show()

    def _on_view_fullscreen(self, image_path, index):
        """Handle request to view in fullscreen from embedded viewer."""
        self.open_viewer(image_path, fullscreen=True)

    def _get_image_paths(self):
        """Get list of all media paths (images, 3D models, videos) from current gallery."""
        from small_widgets import StackedThumbnailWidget

        media_paths = []
        for i in range(self.tab._flow_layout.count()):
            item = self.tab._flow_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                # Handle stacked thumbnail widgets - extract all paths from the stack
                if isinstance(widget, StackedThumbnailWidget):
                    for stack_item in widget._items:
                        if 'path' in stack_item:
                            media_paths.append(stack_item['path'])
                # Include all media: images and 3D models
                elif hasattr(widget, 'image_path'):
                    media_paths.append(widget.image_path)
                elif hasattr(widget, 'model_path'):
                    media_paths.append(widget.model_path)
        return media_paths

    def view_selected(self):
        """Open viewer showing only selected images."""
        if not self.tab._selected_items:
            return

        # Get sorted list of selected paths
        selected_paths = sorted(list(self.tab._selected_items))

        # Open viewer with filtered list
        self.open_viewer(start_image=selected_paths[0], image_paths=selected_paths)
