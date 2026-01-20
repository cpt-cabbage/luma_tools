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


class BatchImageThumbnail(QLabel):
    """Thumbnail widget for batch image selection with drag/drop reordering."""
    clicked = Signal(str)
    remove_requested = Signal(str)
    drag_started = Signal(object)  # Emits self

    def __init__(self, image_path, pairing_color=None, order_num=None, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.pairing_color = pairing_color  # QColor or None
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
        """Load and display the thumbnail with color border and order number."""
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

        # Draw color border if pairing color is set
        if self.pairing_color:
            pen = QPen(self.pairing_color, 4)
            painter.setPen(pen)
            painter.drawRect(2, 2, self.thumbnail_size - 4, self.thumbnail_size - 4)

        # Draw thumbnail centered
        x = (self.thumbnail_size - scaled.width()) // 2
        y = (self.thumbnail_size - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

        # Draw order number in top-left corner
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

    def update_display(self, pairing_color=None, order_num=None):
        """Update the thumbnail with new pairing color or order number."""
        self.pairing_color = pairing_color
        self.order_num = order_num
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
        mime_data.setText(self.image_path)
        drag.setMimeData(mime_data)
        drag.setPixmap(self.pixmap().scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.drag_started.emit(self)
        drag.exec_(Qt.MoveAction)

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
    Supports drag and drop of image files, visual pairing for multiple load nodes,
    and drag reordering.
    """
    images_changed = Signal(list)
    THUMBNAIL_SIZE = 120
    COLORS_FOR_PAIRING = [
        QColor("#4a9eff"),  # Blue
        QColor("#50c878"),  # Green
        QColor("#ff6b6b"),  # Red
        QColor("#ffd93d"),  # Yellow
        QColor("#a78bfa"),  # Purple
        QColor("#fb923c"),  # Orange
        QColor("#ec4899"),  # Pink
        QColor("#14b8a6"),  # Teal
    ]
    UNPAIRED_COLOR = QColor("#ff3b3b")  # Red for unpaired images

    def __init__(self, supported_extensions=None, parent=None, total_image_nodes=1):
        super().__init__(parent)
        self.supported_extensions = supported_extensions or ['.png', '.jpg', '.jpeg', '.exr']
        self.selected_files = []
        self._last_browse_dir = ""
        self._thumbnail_widgets = {}  # path -> BatchImageThumbnail
        self._total_image_nodes = total_image_nodes  # Total number of LoadImage nodes
        self._dragged_widget = None

        # Set size policy to expand vertically
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        self.toolbar = QWidget()
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)

        self.add_btn = QPushButton("Add Images...")
        self.add_btn.clicked.connect(self.browse_images)
        self.toolbar_layout.addWidget(self.add_btn)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self.clear_images)
        self.toolbar_layout.addWidget(self.clear_btn)

        self.count_label = QLabel("No images selected")
        self.toolbar_layout.addWidget(self.count_label)
        self.toolbar_layout.addStretch()

        self.main_layout.addWidget(self.toolbar)

        # Drop zone frame
        self.drop_frame = QFrame()
        self.drop_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.drop_frame.setStyleSheet("""
            QFrame {
                background-color: #2c313a;
                border: 2px dashed #3c414b;
                border-radius: 6px;
            }
            QFrame:hover {
                border-color: #4a9eff;
            }
        """)
        # Set size policy to expand vertically
        self.drop_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.drop_frame.setAcceptDrops(True)

        drop_layout = QVBoxLayout(self.drop_frame)
        drop_layout.setContentsMargins(5, 5, 5, 5)

        self.drop_label = QLabel("Drop images here or click 'Add Images...'\n(Drag thumbnails to reorder, double-click to remove)")
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
        """Open file dialog to select images."""
        ext_filter = "Images (" + " ".join(f"*{ext}" for ext in self.supported_extensions) + ")"
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images",
            self._last_browse_dir or "",
            ext_filter
        )
        if files:
            self._last_browse_dir = os.path.dirname(files[0])
            self.add_images(files)

    def set_total_image_nodes(self, count):
        """Set the total number of LoadImage nodes for pairing calculation."""
        if self._total_image_nodes != count:
            self._total_image_nodes = count
            self._rebuild_grid()  # Rebuild to recalculate colors

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
            self._rebuild_grid()
            self.images_changed.emit(self.selected_files)

    def _calculate_pairing(self):
        """Calculate color pairing for images based on total_image_nodes.

        Returns:
            dict: Mapping of image path to (color, group_index) or (None, None) if unpaired
        """
        pairing = {}
        total_images = len(self.selected_files)

        if self._total_image_nodes <= 1:
            # Single node or no pairing needed
            for path in self.selected_files:
                pairing[path] = (None, None)
            return pairing

        # Calculate how many images per node
        images_per_node = total_images // self._total_image_nodes
        remainder = total_images % self._total_image_nodes

        # Assign colors to groups
        current_idx = 0
        for node_idx in range(self._total_image_nodes):
            # Some nodes get an extra image if there's a remainder
            group_size = images_per_node + (1 if node_idx < remainder else 0)
            color = self.COLORS_FOR_PAIRING[node_idx % len(self.COLORS_FOR_PAIRING)]

            for i in range(group_size):
                if current_idx < total_images:
                    pairing[self.selected_files[current_idx]] = (color, node_idx)
                    current_idx += 1

        # Mark any unpaired images (shouldn't happen with above logic, but just in case)
        for path in self.selected_files:
            if path not in pairing:
                pairing[path] = (self.UNPAIRED_COLOR, None)

        return pairing

    def _rebuild_grid(self):
        """Rebuild the thumbnail grid with current pairing."""
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

        # Calculate pairing
        pairing = self._calculate_pairing()

        # Create thumbnails
        columns = 4  # Fixed 4-column grid
        for idx, path in enumerate(self.selected_files):
            color, group_idx = pairing.get(path, (None, None))
            order_num = idx + 1  # 1-based ordering

            thumbnail = BatchImageThumbnail(path, color, order_num, self.grid_container)
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
        self._rebuild_grid()
        self.images_changed.emit(self.selected_files)

    def _update_display(self):
        """Update the display based on selection count."""
        count = len(self.selected_files)
        if count == 0:
            if self._total_image_nodes > 1:
                self.count_label.setText(f"No images selected ({self._total_image_nodes} load nodes detected)")
            else:
                self.count_label.setText("No images selected")
            self.drop_label.show()
            self.scroll_area.hide()
        else:
            if self._total_image_nodes > 1:
                # Show pairing info
                images_per_node = count // self._total_image_nodes
                remainder = count % self._total_image_nodes
                if remainder == 0:
                    pairing_text = f" - {images_per_node} per node"
                else:
                    pairing_text = f" - {images_per_node}-{images_per_node+1} per node"
                self.count_label.setText(f"{count} image{'s' if count != 1 else ''} selected{pairing_text}")
            else:
                self.count_label.setText(f"{count} image{'s' if count != 1 else ''} selected")
            self.drop_label.hide()
            self.scroll_area.show()

    def _on_thumbnail_clicked(self, path):
        """Handle thumbnail click (currently no action)."""
        pass

    def _on_drag_started(self, widget):
        """Handle drag started from a thumbnail."""
        self._dragged_widget = widget

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

    def dragEnterEvent(self, event):
        """Handle drag enter."""
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Handle drag move - for internal reordering."""
        if event.mimeData().hasText() and self._dragged_widget:
            event.acceptProposedAction()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop - either external files or internal reordering."""
        # Check if it's an internal drag (reordering)
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

        # External file drop
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isfile(path):
                    paths.append(path)
            if paths:
                self.add_images(paths)
            event.acceptProposedAction()
