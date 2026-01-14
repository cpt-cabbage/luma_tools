"""
Batch image selection widget.

Provides a widget for selecting multiple images with drag-and-drop support.
"""
import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QListWidget, QListWidgetItem, QFileDialog, QApplication
)
from PySide6.QtGui import QPixmap, QIcon


class BatchImageSelector(QWidget):
    """
    Custom widget for selecting multiple images with preview thumbnails.
    Supports drag and drop of image files.
    """
    images_changed = Signal(list)
    THUMBNAIL_SIZE = 48

    def __init__(self, supported_extensions=None, parent=None):
        super().__init__(parent)
        self.supported_extensions = supported_extensions or ['.png', '.jpg', '.jpeg', '.exr']
        self.selected_files = []
        self._last_browse_dir = ""
        self._thumbnail_cache = {}

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
                min-height: 100px;
            }
            QFrame:hover {
                border-color: #4a9eff;
            }
        """)
        self.drop_frame.setAcceptDrops(True)

        drop_layout = QVBoxLayout(self.drop_frame)
        drop_layout.setAlignment(Qt.AlignCenter)

        self.drop_label = QLabel("Drop images here\nor click 'Add Images...'")
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setStyleSheet("color: #888888; font-size: 11px; border: none;")
        drop_layout.addWidget(self.drop_label)

        # Image list
        self.image_list = QListWidget()
        self.image_list.setStyleSheet("""
            QListWidget {
                background-color: #2c313a;
                border: 1px solid #3c414b;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #3c414b;
            }
            QListWidget::item:selected {
                background-color: #4a9eff;
            }
        """)
        self.image_list.setIconSize(Qt.QSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE))
        self.image_list.hide()

        drop_layout.addWidget(self.image_list)
        self.main_layout.addWidget(self.drop_frame)

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

    def add_images(self, paths):
        """Add images to the selection."""
        for path in paths:
            if path not in self.selected_files:
                ext = os.path.splitext(path)[1].lower()
                if ext in self.supported_extensions:
                    self.selected_files.append(path)
                    self._add_list_item(path)

        self._update_display()
        self.images_changed.emit(self.selected_files)

    def _add_list_item(self, path):
        """Add an item to the list widget."""
        filename = os.path.basename(path)
        item = QListWidgetItem(filename)
        item.setData(Qt.UserRole, path)

        # Try to load thumbnail
        if path in self._thumbnail_cache:
            item.setIcon(self._thumbnail_cache[path])
        else:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                icon = QIcon(scaled)
                self._thumbnail_cache[path] = icon
                item.setIcon(icon)

        self.image_list.addItem(item)

    def clear_images(self):
        """Clear all selected images."""
        self.selected_files.clear()
        self.image_list.clear()
        self._update_display()
        self.images_changed.emit(self.selected_files)

    def _update_display(self):
        """Update the display based on selection count."""
        count = len(self.selected_files)
        if count == 0:
            self.count_label.setText("No images selected")
            self.drop_label.show()
            self.image_list.hide()
        else:
            self.count_label.setText(f"{count} image{'s' if count != 1 else ''} selected")
            self.drop_label.hide()
            self.image_list.show()

    def get_images(self):
        """Get list of selected image paths."""
        return self.selected_files.copy()

    def set_images(self, paths):
        """Set the selected images."""
        self.clear_images()
        self.add_images(paths)

    def dragEnterEvent(self, event):
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop."""
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                paths.append(path)
        if paths:
            self.add_images(paths)
