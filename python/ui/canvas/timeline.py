"""
Generation timeline widget for temporal view of image generations.

Provides a horizontal timeline showing generation history with:
- Time-based ordering (left to right)
- Branch visualization (main path + forks)
- Click navigation to canvas position
- Collapsible design (default collapsed)
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QFont, QWheelEvent
from PySide6.QtWidgets import (
    QWidget, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsPixmapItem, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea
)

logger = logging.getLogger(__name__)


class TimelineNode(QGraphicsItem):
    """
    A single node in the timeline representing a generated image.
    """

    NODE_SIZE = 60
    THUMBNAIL_SIZE = 50

    def __init__(self, file_path: str, timestamp: float, parent_id: str = None):
        super().__init__()

        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.timestamp = timestamp
        self.parent_id = parent_id
        self.node_id = self.filename  # Use filename as ID

        self._pixmap: Optional[QPixmap] = None
        self._is_liked = False
        self._is_hovered = False
        self._is_selected = False

        # Enable interaction
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        # Load thumbnail async
        self._load_thumbnail()

    def _load_thumbnail(self):
        """Load and cache thumbnail."""
        if os.path.exists(self.file_path):
            try:
                pixmap = QPixmap(self.file_path)
                if not pixmap.isNull():
                    self._pixmap = pixmap.scaled(
                        self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE,
                        Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
            except Exception as e:
                logger.debug(f"Failed to load thumbnail: {e}")

    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        return QRectF(0, 0, self.NODE_SIZE, self.NODE_SIZE + 20)

    def paint(self, painter, option, widget):
        """Paint the timeline node."""
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Background
        if self._is_selected:
            bg_color = QColor(74, 158, 255, 100)
        elif self._is_hovered:
            bg_color = QColor(60, 60, 60)
        else:
            bg_color = QColor(40, 40, 40)

        painter.fillRect(0, 0, self.NODE_SIZE, self.NODE_SIZE, bg_color)

        # Border
        if self._is_selected:
            painter.setPen(QPen(QColor(74, 158, 255), 2))
        else:
            painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawRect(0, 0, self.NODE_SIZE, self.NODE_SIZE)

        # Thumbnail
        if self._pixmap and not self._pixmap.isNull():
            x_offset = (self.NODE_SIZE - self._pixmap.width()) // 2
            y_offset = (self.NODE_SIZE - self._pixmap.height()) // 2
            painter.drawPixmap(x_offset, y_offset, self._pixmap)
        else:
            # Placeholder
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(
                QRectF(0, 0, self.NODE_SIZE, self.NODE_SIZE),
                Qt.AlignCenter,
                "?"
            )

        # Like badge
        if self._is_liked:
            painter.setPen(QPen(QColor(239, 68, 68)))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(self.NODE_SIZE - 15, 15, "♥")

        # Filename label
        painter.setPen(QColor(150, 150, 150))
        painter.setFont(QFont("Arial", 8))
        short_name = self.filename[:10] + "..." if len(self.filename) > 13 else self.filename
        painter.drawText(
            QRectF(0, self.NODE_SIZE + 2, self.NODE_SIZE, 18),
            Qt.AlignCenter,
            short_name
        )

    def set_liked(self, liked: bool):
        """Set liked state."""
        self._is_liked = liked
        self.update()

    def hoverEnterEvent(self, event):
        """Handle hover enter."""
        self._is_hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        """Handle hover leave."""
        self._is_hovered = False
        self.update()


class GenerationTimeline(QGraphicsView):
    """
    Horizontal timeline view of generation history.

    Features:
    - Chronological ordering (left = older, right = newer)
    - Branch visualization
    - Click to navigate/select
    - Scroll to pan
    """

    # Signals
    node_clicked = Signal(str)  # node_id (single click -> highlight on canvas)
    node_double_clicked = Signal(str)  # node_id (double click -> open in viewer)
    node_ctrl_clicked = Signal(str)  # node_id (ctrl+click -> add to comparison)

    # Layout constants
    NODE_SPACING = 80
    ROW_HEIGHT = 100
    BRANCH_OFFSET = 90

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._setup_view()

        # Timeline data
        self._nodes: Dict[str, TimelineNode] = {}
        self._node_positions: Dict[str, QPointF] = {}
        self._branches: Dict[str, List[str]] = {}  # parent_id -> [child_ids]

        # Track collapsed branches
        self._collapsed_branches: set = set()

    def _setup_view(self):
        """Configure the view."""
        from PySide6.QtGui import QPainter

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setMinimumHeight(120)
        self.setMaximumHeight(180)

    def set_items(self, items: List[Dict[str, Any]]):
        """
        Set timeline items from generation data.

        Args:
            items: List of dicts with keys:
                - path: file path
                - mtime: modification timestamp
                - parent_id: optional parent file_id
                - liked: optional liked state
        """
        self._scene.clear()
        self._nodes.clear()
        self._node_positions.clear()
        self._branches.clear()

        if not items:
            return

        # Sort by timestamp
        sorted_items = sorted(items, key=lambda x: x.get('mtime', 0))

        # Build branch structure
        for item in sorted_items:
            parent_id = item.get('parent_id')
            node_id = os.path.basename(item.get('path', ''))

            if parent_id:
                if parent_id not in self._branches:
                    self._branches[parent_id] = []
                self._branches[parent_id].append(node_id)

        # Layout nodes
        x_pos = 50
        main_y = 30

        for item in sorted_items:
            path = item.get('path', '')
            mtime = item.get('mtime', 0)
            parent_id = item.get('parent_id')
            liked = item.get('liked', False)

            node = TimelineNode(path, mtime, parent_id)
            node.set_liked(liked)

            # Determine y position (main line or branch)
            if parent_id and parent_id in self._nodes:
                # This is a branch - offset downward
                y_pos = main_y + self.BRANCH_OFFSET
            else:
                y_pos = main_y

            node.setPos(x_pos, y_pos)
            self._scene.addItem(node)

            self._nodes[node.node_id] = node
            self._node_positions[node.node_id] = QPointF(x_pos, y_pos)

            x_pos += self.NODE_SPACING

        # Draw connections
        self._draw_connections()

        # Fit scene
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))

    def _draw_connections(self):
        """Draw connection lines between related nodes."""
        from PySide6.QtWidgets import QGraphicsLineItem

        for parent_id, children in self._branches.items():
            if parent_id not in self._node_positions:
                continue

            parent_pos = self._node_positions[parent_id]
            parent_center = QPointF(
                parent_pos.x() + TimelineNode.NODE_SIZE / 2,
                parent_pos.y() + TimelineNode.NODE_SIZE / 2
            )

            for child_id in children:
                if child_id not in self._node_positions:
                    continue

                child_pos = self._node_positions[child_id]
                child_center = QPointF(
                    child_pos.x() + TimelineNode.NODE_SIZE / 2,
                    child_pos.y() + TimelineNode.NODE_SIZE / 2
                )

                # Draw line
                line = QGraphicsLineItem(
                    parent_center.x(), parent_center.y(),
                    child_center.x(), child_center.y()
                )
                line.setPen(QPen(QColor(80, 80, 80), 2))
                line.setZValue(-1)  # Behind nodes
                self._scene.addItem(line)

    def mousePressEvent(self, event):
        """Handle mouse press for node selection."""
        pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(pos, self.transform())

        if isinstance(item, TimelineNode):
            if event.modifiers() & Qt.ControlModifier:
                self.node_ctrl_clicked.emit(item.node_id)
            else:
                self.node_clicked.emit(item.node_id)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double click for viewer."""
        pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(pos, self.transform())

        if isinstance(item, TimelineNode):
            self.node_double_clicked.emit(item.node_id)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def highlight_node(self, node_id: str):
        """Highlight a specific node."""
        for nid, node in self._nodes.items():
            node._is_selected = (nid == node_id)
            node.update()

    def scroll_to_node(self, node_id: str):
        """Scroll to center on a specific node."""
        if node_id in self._nodes:
            node = self._nodes[node_id]
            self.centerOn(node)

    def clear(self):
        """Clear all timeline items."""
        self._scene.clear()
        self._nodes.clear()
        self._node_positions.clear()
        self._branches.clear()


class TimelinePanel(QWidget):
    """
    Collapsible timeline panel for the canvas tab.

    Wraps GenerationTimeline with collapse/expand controls.
    """

    # Signals (forwarded from timeline)
    node_clicked = Signal(str)
    node_double_clicked = Signal(str)
    node_ctrl_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_collapsed = True  # Default collapsed per plan
        self._setup_ui()

    def _setup_ui(self):
        """Setup the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Timeline widget
        self._timeline = GenerationTimeline()
        self._timeline.node_clicked.connect(self.node_clicked.emit)
        self._timeline.node_double_clicked.connect(self.node_double_clicked.emit)
        self._timeline.node_ctrl_clicked.connect(self.node_ctrl_clicked.emit)

        layout.addWidget(self._timeline)

        # Initial state
        self._timeline.setVisible(not self._is_collapsed)

    def set_collapsed(self, collapsed: bool):
        """Set collapsed state."""
        self._is_collapsed = collapsed
        self._timeline.setVisible(not collapsed)

    def is_collapsed(self) -> bool:
        """Check if panel is collapsed."""
        return self._is_collapsed

    def toggle_collapsed(self):
        """Toggle collapsed state."""
        self.set_collapsed(not self._is_collapsed)

    def set_items(self, items: List[Dict[str, Any]]):
        """Set timeline items."""
        self._timeline.set_items(items)

    def highlight_node(self, node_id: str):
        """Highlight a node in the timeline."""
        self._timeline.highlight_node(node_id)
        self._timeline.scroll_to_node(node_id)

    def clear(self):
        """Clear the timeline."""
        self._timeline.clear()
