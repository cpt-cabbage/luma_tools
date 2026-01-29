"""
Recent Outputs Preview Panel for ComfyUI tab.

Shows a collapsible strip of recent output thumbnails below the submit buttons,
providing quick access to generated images without switching to the gallery.

Features:
- Thumbnail strip showing last 4 outputs
- Click thumbnail to open in gallery viewer
- Drag thumbnail to use as input image
- Session stats line (X generated today, avg time)
- Collapsible for users who prefer a cleaner interface
"""

import os
import logging
from typing import List, Optional
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QApplication
)
from PySide6.QtCore import Qt, Signal, QMimeData, QSize
from PySide6.QtGui import QPixmap, QDrag, QCursor

logger = logging.getLogger(__name__)


@dataclass
class OutputItem:
    """Data for a recent output item."""
    path: str
    thumbnail: Optional[QPixmap] = None


class RecentOutputThumbnail(QLabel):
    """Clickable thumbnail for a recent output image."""

    clicked = Signal(str)  # Emits path when clicked
    drag_started = Signal(str)  # Emits path when drag starts

    def __init__(self, path: str = "", parent=None):
        super().__init__(parent)
        self.path = path
        self._drag_start_position = None

        # Styling
        self.setFixedSize(80, 80)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #2c313a;
                border: 1px solid #3c414b;
                border-radius: 4px;
            }
            QLabel:hover {
                border-color: #4a9eff;
                background-color: #353b45;
            }
        """)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip("Click to view • Drag to use as input")

    def set_image(self, path: str):
        """Set the thumbnail image from a file path."""
        self.path = path
        if not path or not os.path.exists(path):
            self.setText("?")
            return

        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.setText("?")
            return

        # Scale to fit
        scaled = pixmap.scaled(
            self.size() - QSize(4, 4),  # Account for border
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.setPixmap(scaled)

    def mousePressEvent(self, event):
        """Handle mouse press - start potential drag."""
        if event.button() == Qt.LeftButton:
            self._drag_start_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move - start drag if moved enough."""
        if not self._drag_start_position:
            return

        if not (event.buttons() & Qt.LeftButton):
            return

        distance = (event.position().toPoint() - self._drag_start_position).manhattanLength()
        if distance < QApplication.startDragDistance():
            return

        # Start drag
        self.drag_started.emit(self.path)
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(self.path)
        mime_data.setUrls([Qt.QUrl.fromLocalFile(self.path)])
        drag.setMimeData(mime_data)

        # Set drag pixmap
        if self.pixmap():
            drag.setPixmap(self.pixmap().scaled(60, 60, Qt.KeepAspectRatio))

        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, event):
        """Handle mouse release - emit clicked if not a drag."""
        if event.button() == Qt.LeftButton and self._drag_start_position:
            distance = (event.position().toPoint() - self._drag_start_position).manhattanLength()
            if distance < QApplication.startDragDistance() and self.path:
                self.clicked.emit(self.path)
        self._drag_start_position = None
        super().mouseReleaseEvent(event)


class RecentOutputsPanel(QFrame):
    """
    Collapsible panel showing recent ComfyUI outputs.

    Displays up to 4 thumbnails of recent outputs with click/drag support.
    """

    # Signals
    thumbnail_clicked = Signal(str)  # Path of clicked thumbnail
    use_as_input = Signal(str)  # Path to use as input

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[OutputItem] = []
        self._thumbnails: List[RecentOutputThumbnail] = []
        self._is_collapsed = False
        self._max_thumbnails = 4

        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            RecentOutputsPanel {
                background-color: #282c34;
                border: 1px solid #3c414b;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        # Header with collapse toggle
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self._collapse_button = QPushButton("▼")
        self._collapse_button.setFixedSize(20, 20)
        self._collapse_button.setFlat(True)
        self._collapse_button.setStyleSheet("""
            QPushButton {
                color: #888888;
                font-size: 10px;
                border: none;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        self._collapse_button.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self._collapse_button)

        self._title_label = QLabel("Recent Outputs")
        self._title_label.setStyleSheet("color: #aaaaaa; font-size: 11px; font-weight: bold;")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color: #666666; font-size: 10px;")
        header_layout.addWidget(self._stats_label)

        layout.addLayout(header_layout)

        # Thumbnail container
        self._content_widget = QWidget()
        content_layout = QHBoxLayout(self._content_widget)
        content_layout.setContentsMargins(0, 4, 0, 0)
        content_layout.setSpacing(8)

        # Create thumbnail widgets
        for i in range(self._max_thumbnails):
            thumb = RecentOutputThumbnail()
            thumb.clicked.connect(self._on_thumbnail_clicked)
            thumb.drag_started.connect(self._on_drag_started)
            thumb.setVisible(False)
            self._thumbnails.append(thumb)
            content_layout.addWidget(thumb)

        # Empty state label
        self._empty_label = QLabel("No outputs yet")
        self._empty_label.setStyleSheet("color: #555555; font-style: italic; padding: 10px;")
        self._empty_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self._empty_label)

        content_layout.addStretch()

        layout.addWidget(self._content_widget)

    def _toggle_collapse(self):
        """Toggle collapsed state."""
        self._is_collapsed = not self._is_collapsed
        self._content_widget.setVisible(not self._is_collapsed)
        self._collapse_button.setText("▶" if self._is_collapsed else "▼")

    def _on_thumbnail_clicked(self, path: str):
        """Handle thumbnail click."""
        self.thumbnail_clicked.emit(path)

    def _on_drag_started(self, path: str):
        """Handle drag start from thumbnail."""
        self.use_as_input.emit(path)

    def update_outputs(self, paths: List[str]):
        """
        Update the displayed outputs.

        Args:
            paths: List of output file paths (most recent first)
        """
        self._items = [OutputItem(path=p) for p in paths[:self._max_thumbnails]]

        # Update thumbnails
        for i, thumb in enumerate(self._thumbnails):
            if i < len(self._items):
                thumb.set_image(self._items[i].path)
                thumb.setVisible(True)
            else:
                thumb.setVisible(False)

        # Show/hide empty label
        has_items = len(self._items) > 0
        self._empty_label.setVisible(not has_items)

    def update_stats(self, total_generated: int, avg_time_seconds: float):
        """
        Update the stats display.

        Args:
            total_generated: Total images generated this session
            avg_time_seconds: Average time per image
        """
        if total_generated == 0:
            self._stats_label.setText("")
            return

        if avg_time_seconds > 0:
            if avg_time_seconds < 60:
                time_str = f"{int(avg_time_seconds)}s avg"
            else:
                mins = int(avg_time_seconds // 60)
                secs = int(avg_time_seconds % 60)
                time_str = f"{mins}m{secs}s avg"
            self._stats_label.setText(f"{total_generated} generated • {time_str}")
        else:
            self._stats_label.setText(f"{total_generated} generated")

    def clear(self):
        """Clear all outputs."""
        self._items.clear()
        for thumb in self._thumbnails:
            thumb.setVisible(False)
        self._empty_label.setVisible(True)
        self._stats_label.setText("")
