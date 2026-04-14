"""
Batch image selection widget.

Provides a widget for selecting multiple images with drag-and-drop support.
"""
import os
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QMimeData
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QListWidget, QListWidgetItem, QFileDialog, QApplication, QGridLayout, QScrollArea
)
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QPen, QFont, QDrag


from core.config import VIDEO_EXTENSIONS


# Global registry for tracking active drags between BatchImageSelector widgets
# This allows the target to know which source widget to remove the image from
_active_drag_source = None  # (BatchImageSelector instance, image_path)


def _set_drag_source(selector, path):
    """Register an active drag operation from a BatchImageSelector."""
    global _active_drag_source
    _active_drag_source = (selector, path)


def _get_and_clear_drag_source():
    """Get and clear the active drag source. Returns (selector, path) or (None, None)."""
    global _active_drag_source
    result = _active_drag_source
    _active_drag_source = None
    return result if result else (None, None)


class BatchImageThumbnail(QLabel):
    """Thumbnail widget for batch image selection with drag/drop reordering.

    Supports gallery colors: if an image is dropped from the gallery with a
    group color or liked status, that color is displayed as a border.
    Order numbers are used to indicate image pairing for multiple LoadImage nodes.
    """
    clicked = Signal(str)
    remove_requested = Signal(str)
    drag_started = Signal(object)  # Emits self

    def __init__(self, image_path, order_num=None, parent=None, gallery_color=None):
        """Initialize thumbnail.

        Args:
            image_path: Path to the image file
            order_num: Order number to display (1-based) - used for pairing indication
            parent: Parent widget
            gallery_color: Hex color string from gallery (group color, liked color)
        """
        super().__init__(parent)
        self.image_path = image_path
        self.gallery_color = gallery_color  # Hex string or None (from gallery)
        self.order_num = order_num
        self.thumbnail_size = 120

        self.setFixedSize(self.thumbnail_size, self.thumbnail_size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            BatchImageThumbnail {
                background-color: #2c313a;
                border-radius: 4px;
            }
            BatchImageThumbnail:hover {
                background-color: #3c414b;
            }
        """)

        # Enable drag
        self.setAcceptDrops(False)  # Will be handled by parent
        self.drag_start_pos = None

        self._load_thumbnail()

    def _load_thumbnail(self):
        """Load and display the thumbnail with gallery color border and order number.

        For non-image files (videos etc.), shows a placeholder with play icon and filename.
        """
        ext = os.path.splitext(self.image_path)[1].lower()
        is_video = ext in VIDEO_EXTENSIONS

        if is_video:
            # Video file: show placeholder with play icon and filename
            result = QPixmap(self.thumbnail_size, self.thumbnail_size)
            result.fill(QColor('#2c313a'))

            painter = QPainter(result)
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw gallery color border if available
            if self.gallery_color:
                border_color = QColor(self.gallery_color)
                pen = QPen(border_color, 4)
                painter.setPen(pen)
                painter.drawRect(2, 2, self.thumbnail_size - 4, self.thumbnail_size - 4)

            # Draw play triangle icon centered
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(200, 200, 200, 180))
            cx, cy = self.thumbnail_size // 2, self.thumbnail_size // 2 - 10
            from PySide6.QtGui import QPolygon
            from PySide6.QtCore import QPoint as QP
            triangle = QPolygon([QP(cx - 14, cy - 18), QP(cx - 14, cy + 18), QP(cx + 18, cy)])
            painter.drawPolygon(triangle)

            # Draw filename at the bottom
            painter.setPen(QPen(QColor(180, 180, 180)))
            font = QFont()
            font.setPixelSize(10)
            painter.setFont(font)
            filename = os.path.basename(self.image_path)
            # Truncate long filenames
            if len(filename) > 16:
                filename = filename[:13] + '...'
            painter.drawText(4, self.thumbnail_size - 22, self.thumbnail_size - 8, 18,
                             Qt.AlignCenter, filename)
        else:
            # Image file: load and scale
            pixmap = QPixmap(self.image_path)
            if pixmap.isNull():
                self.setText("Invalid")
                return

            # Scale to fit while maintaining aspect ratio
            scaled = pixmap.scaled(
                self.thumbnail_size - 10, self.thumbnail_size - 10,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )

            # Create a new pixmap with border and order number
            result = QPixmap(self.thumbnail_size, self.thumbnail_size)
            result.fill(Qt.transparent)

            painter = QPainter(result)
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw gallery color border if available
            if self.gallery_color:
                border_color = QColor(self.gallery_color)
                pen = QPen(border_color, 4)
                painter.setPen(pen)
                painter.drawRect(2, 2, self.thumbnail_size - 4, self.thumbnail_size - 4)

            # Draw thumbnail centered
            x = (self.thumbnail_size - scaled.width()) // 2
            y = (self.thumbnail_size - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        # Draw order number in top-left corner (used for pairing indication)
        if self.order_num is not None:
            # Semi-transparent background
            bg_color = QColor(0, 0, 0, 180)
            painter.fillRect(4, 4, 24, 20, bg_color)

            # White text
            painter.setPen(QPen(QColor(255, 255, 255)))
            font = QFont()
            font.setPixelSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(4, 4, 24, 20, Qt.AlignCenter, str(self.order_num))

        painter.end()
        self.setPixmap(result)

    def update_display(self, order_num=None, gallery_color=None):
        """Update the thumbnail with new order number or gallery color."""
        if order_num is not None:
            self.order_num = order_num
        if gallery_color is not None:
            self.gallery_color = gallery_color
        self._load_thumbnail()

    def mousePressEvent(self, event):
        """Handle mouse press for drag initiation."""
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for drag operation."""
        if not (event.buttons() & Qt.LeftButton):
            return
        if not self.drag_start_pos:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        # Start drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        # Set both text (for internal reordering) and custom MIME type (for cross-widget drops)
        mime_data.setText(self.image_path)
        # Use a specific MIME type for BatchImageSelector drags (distinct from gallery drags)
        mime_data.setData("application/x-luma-batch-image", self.image_path.encode('utf-8'))
        # Also set the general luma-files type for compatibility
        mime_data.setData("application/x-luma-files", self.image_path.encode('utf-8'))
        drag.setMimeData(mime_data)
        drag.setPixmap(self.pixmap().scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        # Register this drag so the target can remove from source (for move operation)
        parent_selector = self._find_parent_selector()
        if parent_selector:
            _set_drag_source(parent_selector, self.image_path)

        self.drag_started.emit(self)
        drag.exec_(Qt.MoveAction)  # Use MoveAction for input-to-input drags

        # Drag ended (completed or cancelled) - clear state
        if parent_selector:
            parent_selector._clear_drag_state()
        # Also clear global drag source in case drop wasn't handled
        _get_and_clear_drag_source()

    def _find_parent_selector(self):
        """Find the parent BatchImageSelector widget."""
        parent = self.parentWidget()
        while parent:
            if isinstance(parent, BatchImageSelector):
                return parent
            parent = parent.parentWidget()
        return None

    def mouseReleaseEvent(self, event):
        """Handle mouse release for click."""
        if event.button() == Qt.LeftButton and self.drag_start_pos:
            if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
                # It was a click, not a drag
                self.clicked.emit(self.image_path)
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click for removal."""
        if event.button() == Qt.LeftButton:
            self.remove_requested.emit(self.image_path)
        super().mouseDoubleClickEvent(event)


class BatchImageSelector(QWidget):
    """
    Custom widget for selecting multiple images with preview thumbnails.
    Supports drag and drop of image files, order numbers for pairing indication
    with multiple LoadImage nodes, and drag reordering.
    """
    images_changed = Signal(list)
    THUMBNAIL_SIZE = 120

    def __init__(self, supported_extensions=None, parent=None, total_image_nodes=1, file_type_label="images"):
        super().__init__(parent)
        self.supported_extensions = supported_extensions or ['.png', '.jpg', '.jpeg', '.exr']
        self.selected_files = []
        self._last_browse_dir = ""
        self._thumbnail_widgets = {}  # path -> BatchImageThumbnail
        self._total_image_nodes = total_image_nodes  # Total number of LoadImage/LoadVideo nodes
        self._dragged_widget = None
        self._gallery_colors = {}  # path -> hex color string (from gallery likes/groups)
        self._file_type_label = file_type_label  # "images", "videos", etc.
        self._compact = total_image_nodes >= 3  # Compact toolbar when many nodes

        # Set size policy to expand vertically
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        self.toolbar = QWidget()
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)

        if self._compact:
            self.add_btn = QPushButton("Add...")
            self.clear_btn = QPushButton("Clear")
        else:
            self.add_btn = QPushButton(f"Add {self._file_type_label.title()}...")
            self.clear_btn = QPushButton("Clear All")
        self.add_btn.clicked.connect(self.browse_images)
        self.toolbar_layout.addWidget(self.add_btn)

        self.clear_btn.clicked.connect(self.clear_images)
        self.toolbar_layout.addWidget(self.clear_btn)

        self.count_label = QLabel(f"No {self._file_type_label} selected")
        self.count_label.setMinimumWidth(0)
        self.toolbar_layout.addWidget(self.count_label)
        self.toolbar_layout.addStretch()

        self.main_layout.addWidget(self.toolbar)

        # Drop zone frame - store base style for drag highlight toggling
        self._drop_frame_base_style = """
            QFrame {
                background-color: #2c313a;
                border: 2px dashed #3c414b;
                border-radius: 6px;
            }
            QFrame:hover {
                border-color: #4a9eff;
            }
        """
        self._drop_frame_highlight_style = """
            QFrame {
                background-color: rgba(74, 158, 255, 0.15);
                border: 2px solid #4a9eff;
                border-radius: 6px;
            }
        """
        self.drop_frame = QFrame()
        self.drop_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.drop_frame.setStyleSheet(self._drop_frame_base_style)
        # Set size policy to expand vertically
        self.drop_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.drop_frame.setAcceptDrops(True)

        drop_layout = QVBoxLayout(self.drop_frame)
        drop_layout.setContentsMargins(5, 5, 5, 5)

        _label_title = self._file_type_label.title()
        self.drop_label = QLabel(f"Drop {self._file_type_label} here or click 'Add {_label_title}...'\n(Drag thumbnails to reorder, double-click to remove)")
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setStyleSheet("color: #888888; font-size: 11px; border: none;")
        drop_layout.addWidget(self.drop_label)

        # Scroll area for grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)
        self.scroll_area.hide()

        # Grid container for thumbnails
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll_area.setWidget(self.grid_container)

        drop_layout.addWidget(self.scroll_area, 1)  # Stretch factor to expand
        self.main_layout.addWidget(self.drop_frame, 1)  # Stretch factor to expand

        # Enable drag and drop
        self.setAcceptDrops(True)

    def browse_images(self):
        """Open file dialog to select files."""
        label_title = self._file_type_label.title()
        ext_filter = f"{label_title} (" + " ".join(f"*{ext}" for ext in self.supported_extensions) + ")"
        files, _ = QFileDialog.getOpenFileNames(
            self, f"Select {label_title}",
            self._last_browse_dir or "",
            ext_filter
        )
        if files:
            self._last_browse_dir = os.path.dirname(files[0])
            self.add_images(files)

    def set_total_image_nodes(self, count):
        """Set the total number of LoadImage nodes for status display."""
        if self._total_image_nodes != count:
            self._total_image_nodes = count
            self._update_display()  # Update status label to show node count

    def add_images(self, paths):
        """Add images to the selection."""
        for path in paths:
            if path not in self.selected_files:
                ext = os.path.splitext(path)[1].lower()
                if ext in self.supported_extensions:
                    self.selected_files.append(path)

        self._rebuild_grid()
        self.images_changed.emit(self.selected_files)

    def remove_image(self, path):
        """Remove an image from the selection."""
        if path in self.selected_files:
            self.selected_files.remove(path)
            # Also remove gallery color if stored
            self._gallery_colors.pop(path, None)
            self._rebuild_grid()
            self.images_changed.emit(self.selected_files)

    def _rebuild_grid(self):
        """Rebuild the thumbnail grid with order numbers and gallery colors."""
        # Clear existing widgets
        for widget in list(self._thumbnail_widgets.values()):
            widget.deleteLater()
        self._thumbnail_widgets.clear()

        # Clear grid layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.selected_files:
            self._update_display()
            return

        # Create thumbnails with order numbers (for pairing indication)
        columns = 4  # Fixed 4-column grid
        for idx, path in enumerate(self.selected_files):
            order_num = idx + 1  # 1-based ordering

            # Get gallery color if available
            gallery_color = self._gallery_colors.get(path)

            thumbnail = BatchImageThumbnail(
                path, order_num, self.grid_container,
                gallery_color=gallery_color
            )
            thumbnail.clicked.connect(self._on_thumbnail_clicked)
            thumbnail.remove_requested.connect(self.remove_image)
            thumbnail.drag_started.connect(self._on_drag_started)

            self._thumbnail_widgets[path] = thumbnail

            row = idx // columns
            col = idx % columns
            self.grid_layout.addWidget(thumbnail, row, col)

        self._update_display()

    def clear_images(self):
        """Clear all selected images."""
        self.selected_files.clear()
        self._gallery_colors.clear()  # Also clear gallery colors
        self._rebuild_grid()
        self.images_changed.emit(self.selected_files)

    def _update_display(self):
        """Update the display based on selection count."""
        label = self._file_type_label  # e.g. "images", "videos"
        # Singular form: strip trailing 's' if present (images->image, videos->video)
        label_singular = label.rstrip('s') if label.endswith('s') else label
        count = len(self.selected_files)
        if count == 0:
            if self._compact:
                self.count_label.setText(f"None ({self._total_image_nodes} nodes)")
            elif self._total_image_nodes > 1:
                self.count_label.setText(f"No {label} selected ({self._total_image_nodes} load nodes detected)")
            else:
                self.count_label.setText(f"No {label} selected")
            self.drop_label.show()
            self.scroll_area.hide()
        else:
            count_text = f"{count} {label_singular if count == 1 else label}"
            if self._total_image_nodes > 1:
                # Show pairing info
                per_node = count // self._total_image_nodes
                remainder = count % self._total_image_nodes
                if remainder == 0:
                    pairing_text = f" - {per_node}/node" if self._compact else f" - {per_node} per node"
                else:
                    pairing_text = f" - {per_node}-{per_node+1}/node" if self._compact else f" - {per_node}-{per_node+1} per node"
                self.count_label.setText(f"{count_text} selected{pairing_text}")
            else:
                self.count_label.setText(f"{count_text} selected")
            self.drop_label.hide()
            self.scroll_area.show()

    def _on_thumbnail_clicked(self, path):
        """Handle thumbnail click (currently no action)."""
        pass

    def _on_drag_started(self, widget):
        """Handle drag started from a thumbnail (internal reordering)."""
        self._dragged_widget = widget

    def _clear_drag_state(self):
        """Clear drag state - call when drag ends or leaves."""
        self._dragged_widget = None

    def _move_image(self, from_idx, to_idx):
        """Move an image from one position to another."""
        if 0 <= from_idx < len(self.selected_files) and 0 <= to_idx < len(self.selected_files):
            path = self.selected_files.pop(from_idx)
            self.selected_files.insert(to_idx, path)
            self._rebuild_grid()
            self.images_changed.emit(self.selected_files)

    def get_images(self):
        """Get list of selected image paths."""
        return self.selected_files.copy()

    def set_images(self, paths):
        """Set the selected images."""
        self.clear_images()
        self.add_images(paths)

    def set_last_browse_dir(self, directory):
        """Set the last browse directory."""
        self._last_browse_dir = directory

    def _has_acceptable_drag_data(self, mime_data):
        """Check if mime data contains files we can accept."""
        # Check for drag from another BatchImageSelector (move operation)
        if mime_data.hasFormat("application/x-luma-batch-image"):
            return True
        # Check for our custom MIME type (drag from gallery - copy operation)
        if mime_data.hasFormat("application/x-luma-files"):
            return True
        # Check for URLs (file drops from explorer or other apps)
        if mime_data.hasUrls():
            return True
        # Check for text (internal reordering)
        if mime_data.hasText():
            return True
        return False

    def dragEnterEvent(self, event):
        """Handle drag enter - show visual feedback."""
        if self._has_acceptable_drag_data(event.mimeData()):
            event.acceptProposedAction()
            # Check if this is an external drag (not from our own thumbnails)
            # by checking if the drag source is from a different widget
            is_internal = self._dragged_widget is not None
            if not is_internal:
                self.drop_frame.setStyleSheet(self._drop_frame_highlight_style)

    def dragMoveEvent(self, event):
        """Handle drag move - for internal reordering."""
        if event.mimeData().hasText() and self._dragged_widget:
            event.acceptProposedAction()
        elif self._has_acceptable_drag_data(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        """Handle drag leave - remove visual feedback."""
        self.drop_frame.setStyleSheet(self._drop_frame_base_style)
        # Note: Don't clear _dragged_widget here - it might be leaving temporarily
        # (e.g., hovering over tab bar) and coming back
        event.accept()

    def dropEvent(self, event):
        """Handle drop - either external files or internal reordering."""
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"[BatchImageSelector] dropEvent START")
        try:
            # Restore base style
            self.drop_frame.setStyleSheet(self._drop_frame_base_style)

            # Check if it's an internal drag (reordering within this widget)
            if event.mimeData().hasText() and self._dragged_widget:
                dragged_path = event.mimeData().text()
                if dragged_path in self.selected_files:
                    # Find the target position based on drop location
                    drop_pos = event.position().toPoint() if hasattr(event.position(), 'toPoint') else event.pos()
                    target_widget = self.grid_container.childAt(drop_pos)

                    # Walk up to find BatchImageThumbnail if we hit a child widget
                    while target_widget and not isinstance(target_widget, BatchImageThumbnail):
                        target_widget = target_widget.parentWidget()

                    if target_widget and isinstance(target_widget, BatchImageThumbnail):
                        from_idx = self.selected_files.index(dragged_path)
                        to_idx = self.selected_files.index(target_widget.image_path)
                        if from_idx != to_idx:
                            self._move_image(from_idx, to_idx)

                    self._dragged_widget = None
                    event.acceptProposedAction()
                    return

            # Check for drag from another BatchImageSelector (move operation)
            if event.mimeData().hasFormat("application/x-luma-batch-image"):
                data = event.mimeData().data("application/x-luma-batch-image").data().decode('utf-8')
                path = data.strip()

                # Get the source selector and remove from it (move, not copy)
                source_selector, source_path = _get_and_clear_drag_source()

                if path and os.path.isfile(path):
                    ext = os.path.splitext(path)[1].lower()
                    if ext in self.supported_extensions:
                        # Only add if not already in this selector
                        if path not in self.selected_files:
                            self.add_images([path])

                        # Remove from source (if it's a different selector)
                        if source_selector and source_selector is not self:
                            source_selector.remove_image(source_path or path)
                            # Clear the source's drag state
                            source_selector._clear_drag_state()

                event.acceptProposedAction()
                return

            # Check for our custom MIME type (drag from gallery - copy, not move)
            if event.mimeData().hasFormat("application/x-luma-files"):
                logger.debug(f"[BatchImageSelector] dropEvent handling luma-files MIME type")
                data = event.mimeData().data("application/x-luma-files").data().decode('utf-8')
                paths = [p.strip() for p in data.split('\n') if p.strip()]
                logger.debug(f"[BatchImageSelector] dropEvent got {len(paths)} paths from drag")
                # Filter to only files that exist and match our extensions
                valid_paths = []
                for path in paths:
                    if os.path.isfile(path):
                        ext = os.path.splitext(path)[1].lower()
                        if ext in self.supported_extensions:
                            valid_paths.append(path)
                logger.debug(f"[BatchImageSelector] dropEvent {len(valid_paths)} valid paths")
                if valid_paths:
                    self.add_images(valid_paths)
                    logger.debug(f"[BatchImageSelector] dropEvent add_images done")
                event.acceptProposedAction()
                logger.debug(f"[BatchImageSelector] dropEvent COMPLETE (luma-files)")
                return

            # External file drop (from file explorer)
            if event.mimeData().hasUrls():
                paths = []
                for url in event.mimeData().urls():
                    path = url.toLocalFile()
                    if os.path.isfile(path):
                        paths.append(path)
                if paths:
                    self.add_images(paths)
                event.acceptProposedAction()
                logger.debug(f"[BatchImageSelector] dropEvent COMPLETE (urls)")
                return

            logger.debug(f"[BatchImageSelector] dropEvent COMPLETE (no handler)")
        except Exception as e:
            logger.error(f"[BatchImageSelector] dropEvent error: {e}", exc_info=True)
