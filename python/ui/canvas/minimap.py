"""
Canvas minimap widget for navigation overview.

Provides a bird's-eye view of the entire canvas with colored outlines
of image nodes and a viewport rectangle showing the current view.
Floats over the canvas and auto-shows/hides on pan/zoom.
"""

import logging
from typing import Optional

from PySide6.QtCore import (
    Qt, QRectF, QPointF, Signal, QTimer,
    QPropertyAnimation, QEasingCurve
)
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
from PySide6.QtWidgets import QWidget, QGraphicsView

logger = logging.getLogger(__name__)


class CanvasMinimap(QWidget):
    """
    Floating minimap widget showing an overview of the canvas.

    Features:
    - Colored outlines of all image nodes (no thumbnails)
    - Viewport rectangle showing current view
    - Click to navigate to location
    - Drag to pan the main canvas
    - Auto show/hide on pan/zoom with fade animation
    - Nuke-style appearance
    """

    # Signals
    navigate_requested = Signal(float, float)  # x, y in scene coordinates

    # Size constants
    WIDTH = 200
    HEIGHT = 150

    # Timing
    VISIBILITY_DURATION = 2000  # ms to stay visible after interaction
    FADE_DURATION = 300  # ms for fade animation

    # Colors
    BACKGROUND_COLOR = QColor(20, 20, 20, 200)
    BORDER_COLOR = QColor(60, 60, 60)
    VIEWPORT_FILL = QColor(255, 255, 255, 20)
    VIEWPORT_BORDER = QColor(100, 150, 255, 200)
    DEFAULT_NODE_COLOR = QColor(180, 180, 180)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._canvas: Optional[QGraphicsView] = None
        self._scene_rect = QRectF()
        self._viewport_rect = QRectF()
        self._node_rects = {}  # node_id -> QRectF (in scene coords)
        self._node_colors = {}  # node_id -> QColor

        # Interaction state
        self._is_dragging = False

        # Setup as floating overlay
        self.setWindowFlags(
            Qt.Tool |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        # Visibility timer for auto-hide
        self._visibility_timer = QTimer(self)
        self._visibility_timer.setSingleShot(True)
        self._visibility_timer.timeout.connect(self._start_fade_out)

        # Fade animation
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(self.FADE_DURATION)
        self._fade_animation.setEasingCurve(QEasingCurve.OutCubic)

        # Update timer for tracking while visible (nodes + viewport)
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(50)  # 20 FPS update
        self._update_timer.timeout.connect(self._update_all)

        # Start hidden
        self.hide()

    def set_canvas(self, canvas: QGraphicsView):
        """
        Connect the minimap to a canvas.

        Args:
            canvas: The CollaborativeCanvas instance to track
        """
        self._canvas = canvas

        # Connect to canvas signals for content changes
        if hasattr(canvas, 'canvas_modified'):
            canvas.canvas_modified.connect(self._update_all)

    def show_temporarily(self):
        """Show the minimap and start the auto-hide timer."""
        # Stop any ongoing fade
        self._fade_animation.stop()
        self.setWindowOpacity(1.0)

        # Update content
        self._update_all()

        # Show and raise
        if not self.isVisible():
            self.show()
        self.raise_()

        # Start viewport updates
        self._update_timer.start()

        # Restart visibility timer
        self._visibility_timer.start(self.VISIBILITY_DURATION)

    def _start_fade_out(self):
        """Begin fade-out animation."""
        self._update_timer.stop()
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self._on_fade_complete)
        self._fade_animation.start()

    def _on_fade_complete(self):
        """Handle fade animation completion."""
        self._fade_animation.finished.disconnect(self._on_fade_complete)
        if self.windowOpacity() < 0.1:
            self.hide()

    def _update_all(self):
        """Update the entire minimap (node rects and viewport)."""
        if not self._canvas:
            return

        scene = self._canvas.scene()
        if not scene:
            return

        # Get items bounding rect
        items_rect = scene.itemsBoundingRect()

        # Get current viewport in scene coordinates
        viewport_rect = self._canvas.mapToScene(
            self._canvas.viewport().rect()
        ).boundingRect()

        # Use union of items and viewport so minimap expands when zoomed out
        if items_rect.isEmpty():
            self._scene_rect = viewport_rect if not viewport_rect.isEmpty() else QRectF(-500, -500, 1000, 1000)
        elif viewport_rect.isEmpty():
            self._scene_rect = items_rect
        else:
            self._scene_rect = items_rect.united(viewport_rect)

        # Update node information
        self._update_nodes()
        self._update_viewport()
        self.update()

    def _update_nodes(self):
        """Update node rectangles and colors from canvas."""
        if not self._canvas:
            return

        self._node_rects.clear()
        self._node_colors.clear()

        # Get image nodes from canvas
        if hasattr(self._canvas, '_image_nodes'):
            for node_id, node in self._canvas._image_nodes.items():
                try:
                    # Get actual image rect (not sceneBoundingRect which has 300px margin)
                    # ImageNode has _width/_height for actual dimensions
                    pos = node.pos()
                    width = getattr(node, '_width', 100)
                    height = getattr(node, '_height', 100)
                    bounds = QRectF(pos.x(), pos.y(), width, height)
                    self._node_rects[node_id] = bounds

                    # Get node color (from metadata or default)
                    color = self._get_node_color(node)
                    self._node_colors[node_id] = color
                except Exception as e:
                    logger.debug(f"Error getting node info for {node_id}: {e}")

    def _get_node_color(self, node) -> QColor:
        """Get the display color for a node."""
        # Check if node has a color attribute (from metadata/group)
        if hasattr(node, 'display_color') and node.display_color:
            return QColor(node.display_color)

        # Check for group color
        if hasattr(node, 'group_color') and node.group_color:
            return QColor(node.group_color)

        # Use a color based on node index for variety
        if hasattr(node, 'node_id'):
            # Generate a consistent color from node_id hash
            hash_val = hash(node.node_id)
            hue = (hash_val % 360)
            return QColor.fromHsv(hue, 150, 200)

        return self.DEFAULT_NODE_COLOR

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
        """Paint the minimap with colored outlines."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Rounded rectangle background
        painter.setBrush(QBrush(self.BACKGROUND_COLOR))
        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

        if self._scene_rect.isEmpty():
            # Draw "No items" text
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignCenter, "No items")
            return

        # Draw node outlines (no thumbnails, just colored rectangles)
        for node_id, scene_rect in self._node_rects.items():
            minimap_rect = self._scene_rect_to_minimap(scene_rect)
            target_rect = minimap_rect.toRect()

            # Ensure minimum visible size (at least 4x4 pixels)
            if target_rect.width() < 4:
                center_x = target_rect.center().x()
                target_rect.setLeft(center_x - 2)
                target_rect.setRight(center_x + 2)
            if target_rect.height() < 4:
                center_y = target_rect.center().y()
                target_rect.setTop(center_y - 2)
                target_rect.setBottom(center_y + 2)

            # Get node color
            color = self._node_colors.get(node_id, self.DEFAULT_NODE_COLOR)

            # Draw colored outline only (no fill)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color, 2))
            painter.drawRect(target_rect)

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
            self._navigate_to(event.position())
            # Reset visibility timer while interacting
            self._visibility_timer.start(self.VISIBILITY_DURATION)
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
