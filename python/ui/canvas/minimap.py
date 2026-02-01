"""
Canvas minimap widget for navigation overview.

Provides a bird's-eye view of the entire canvas with thumbnail previews
of image nodes and a viewport rectangle showing the current view.
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QImage
from PySide6.QtWidgets import QWidget, QGraphicsView

logger = logging.getLogger(__name__)


class CanvasMinimap(QWidget):
    """
    Minimap widget showing an overview of the canvas.

    Features:
    - Thumbnail previews of all image nodes
    - Viewport rectangle showing current view
    - Click to navigate to location
    - Drag to pan the main canvas
    - Auto-updates when canvas changes
    """

    # Signals
    navigate_requested = Signal(float, float)  # x, y in scene coordinates

    # Size constants
    MIN_WIDTH = 150
    MIN_HEIGHT = 100
    MAX_WIDTH = 250
    MAX_HEIGHT = 180

    # Colors
    BACKGROUND_COLOR = QColor(30, 30, 30, 220)
    BORDER_COLOR = QColor(80, 80, 80)
    VIEWPORT_FILL = QColor(255, 255, 255, 30)
    VIEWPORT_BORDER = QColor(100, 150, 255, 200)
    NODE_BORDER = QColor(100, 100, 100)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._canvas: Optional[QGraphicsView] = None
        self._scene_rect = QRectF()
        self._viewport_rect = QRectF()
        self._node_thumbnails = {}  # node_id -> QPixmap
        self._node_rects = {}  # node_id -> QRectF (in scene coords)

        # Interaction state
        self._is_dragging = False
        self._drag_start = QPointF()

        # Setup widget
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.setMaximumSize(self.MAX_WIDTH, self.MAX_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        # Update timer for smooth updates
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(100)  # Update every 100ms
        self._update_timer.timeout.connect(self._update_viewport)

    def set_canvas(self, canvas: QGraphicsView):
        """
        Connect the minimap to a canvas.

        Args:
            canvas: The CollaborativeCanvas instance to track
        """
        self._canvas = canvas

        # Connect to canvas signals
        if hasattr(canvas, 'canvas_modified'):
            canvas.canvas_modified.connect(self._on_canvas_changed)

        # Start viewport tracking
        self._update_timer.start()
        self._update_all()

    def _on_canvas_changed(self):
        """Handle canvas modification - update thumbnails."""
        self._update_all()

    def _update_all(self):
        """Update the entire minimap (thumbnails and viewport)."""
        if not self._canvas:
            return

        scene = self._canvas.scene()
        if not scene:
            return

        # Get scene bounds
        self._scene_rect = scene.itemsBoundingRect()
        if self._scene_rect.isEmpty():
            self._scene_rect = QRectF(-500, -500, 1000, 1000)

        # Update node thumbnails
        self._update_thumbnails()
        self._update_viewport()
        self.update()

    def _update_thumbnails(self):
        """Update thumbnail cache from canvas image nodes."""
        if not self._canvas:
            return

        self._node_thumbnails.clear()
        self._node_rects.clear()

        # Get image nodes from canvas
        if hasattr(self._canvas, '_image_nodes'):
            for node_id, node in self._canvas._image_nodes.items():
                try:
                    # Get node bounds
                    bounds = node.sceneBoundingRect()
                    self._node_rects[node_id] = bounds

                    # Create tiny thumbnail
                    if hasattr(node, 'image_path') and node.image_path:
                        # Use cached pixmap if available
                        if hasattr(node, '_pixmap') and node._pixmap and not node._pixmap.isNull():
                            # Scale down to minimap size
                            thumb_size = 20  # Small thumbnail
                            scaled = node._pixmap.scaled(
                                thumb_size, thumb_size,
                                Qt.KeepAspectRatio,
                                Qt.FastTransformation
                            )
                            self._node_thumbnails[node_id] = scaled
                except Exception as e:
                    logger.debug(f"Error getting thumbnail for {node_id}: {e}")

    def _update_viewport(self):
        """Update the viewport rectangle position."""
        if not self._canvas:
            return

        # Get visible rect in scene coordinates
        visible_rect = self._canvas.mapToScene(
            self._canvas.viewport().rect()
        ).boundingRect()
        self._viewport_rect = visible_rect
        self.update()

    def _scene_to_minimap(self, scene_point: QPointF) -> QPointF:
        """Convert scene coordinates to minimap widget coordinates."""
        if self._scene_rect.isEmpty():
            return QPointF()

        # Add padding to scene rect
        padding = 50
        padded_rect = self._scene_rect.adjusted(-padding, -padding, padding, padding)

        # Calculate scale factor
        scale_x = self.width() / padded_rect.width()
        scale_y = self.height() / padded_rect.height()
        scale = min(scale_x, scale_y)

        # Calculate offset to center
        scaled_width = padded_rect.width() * scale
        scaled_height = padded_rect.height() * scale
        offset_x = (self.width() - scaled_width) / 2
        offset_y = (self.height() - scaled_height) / 2

        # Transform point
        x = (scene_point.x() - padded_rect.left()) * scale + offset_x
        y = (scene_point.y() - padded_rect.top()) * scale + offset_y

        return QPointF(x, y)

    def _minimap_to_scene(self, minimap_point: QPointF) -> QPointF:
        """Convert minimap widget coordinates to scene coordinates."""
        if self._scene_rect.isEmpty():
            return QPointF()

        # Add padding to scene rect
        padding = 50
        padded_rect = self._scene_rect.adjusted(-padding, -padding, padding, padding)

        # Calculate scale factor
        scale_x = self.width() / padded_rect.width()
        scale_y = self.height() / padded_rect.height()
        scale = min(scale_x, scale_y)

        # Calculate offset to center
        scaled_width = padded_rect.width() * scale
        scaled_height = padded_rect.height() * scale
        offset_x = (self.width() - scaled_width) / 2
        offset_y = (self.height() - scaled_height) / 2

        # Inverse transform
        x = (minimap_point.x() - offset_x) / scale + padded_rect.left()
        y = (minimap_point.y() - offset_y) / scale + padded_rect.top()

        return QPointF(x, y)

    def _scene_rect_to_minimap(self, scene_rect: QRectF) -> QRectF:
        """Convert a scene rect to minimap widget rect."""
        top_left = self._scene_to_minimap(scene_rect.topLeft())
        bottom_right = self._scene_to_minimap(scene_rect.bottomRight())
        return QRectF(top_left, bottom_right)

    def paintEvent(self, event):
        """Paint the minimap."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.fillRect(self.rect(), self.BACKGROUND_COLOR)
        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if self._scene_rect.isEmpty():
            # Draw "No items" text
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(self.rect(), Qt.AlignCenter, "No items")
            return

        # Draw node thumbnails
        for node_id, scene_rect in self._node_rects.items():
            minimap_rect = self._scene_rect_to_minimap(scene_rect)

            # Draw node rectangle
            if node_id in self._node_thumbnails:
                thumb = self._node_thumbnails[node_id]
                # Scale thumbnail to fit rect
                target_rect = minimap_rect.toRect()
                if target_rect.width() > 2 and target_rect.height() > 2:
                    painter.drawPixmap(target_rect, thumb)
                    painter.setPen(QPen(self.NODE_BORDER, 1))
                    painter.drawRect(target_rect)
            else:
                # Draw placeholder rectangle
                painter.fillRect(minimap_rect, QColor(80, 80, 80))
                painter.setPen(QPen(self.NODE_BORDER, 1))
                painter.drawRect(minimap_rect)

        # Draw viewport rectangle
        if not self._viewport_rect.isEmpty():
            viewport_minimap = self._scene_rect_to_minimap(self._viewport_rect)
            painter.fillRect(viewport_minimap, self.VIEWPORT_FILL)
            painter.setPen(QPen(self.VIEWPORT_BORDER, 2))
            painter.drawRect(viewport_minimap)

    def mousePressEvent(self, event):
        """Handle mouse press - start navigation."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_start = event.position()
            self._navigate_to(event.position())
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move - drag navigation."""
        if self._is_dragging:
            self._navigate_to(event.position())
            event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release - end navigation."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            event.accept()

    def _navigate_to(self, minimap_pos: QPointF):
        """Navigate the main canvas to the clicked position."""
        if not self._canvas:
            return

        scene_pos = self._minimap_to_scene(minimap_pos)
        self.navigate_requested.emit(scene_pos.x(), scene_pos.y())

        # Center canvas on the clicked point
        self._canvas.centerOn(scene_pos)
