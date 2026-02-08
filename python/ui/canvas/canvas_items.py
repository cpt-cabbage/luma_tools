"""
Canvas items for the collaborative canvas.

Contains: ImageNode, ConnectionLine, StickyNote, GroupRegion

Infinite canvas with pixel density preservation:
- Images maintain full resolution at any zoom level
- LOD (Level of Detail) caching for large images to optimize performance
- Non-destructive transformations (crop, flip, rotate, opacity, grayscale)
"""

import os
import logging
from typing import Optional, List, Tuple, Dict
from enum import Enum

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QObject
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPixmap, QPainterPath,
    QFont, QFontMetrics, QCursor, QTransform, QImage
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPixmapItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsTextItem, QGraphicsSceneMouseEvent,
    QGraphicsProxyWidget, QStyleOptionGraphicsItem, QWidget,
    QMenu, QInputDialog, QColorDialog, QVBoxLayout
)

logger = logging.getLogger(__name__)


class ResizeHandle(Enum):
    """Resize handle positions."""
    NONE = 0
    TOP_LEFT = 1
    TOP_RIGHT = 2
    BOTTOM_LEFT = 3
    BOTTOM_RIGHT = 4


class ImageNode(QGraphicsItem):
    """
    A draggable, resizable image node for the canvas.

    Features:
    - Pixel density preservation: full resolution at any zoom level
    - LOD (Level of Detail) caching for large images
    - Non-destructive transformations (crop, flip, rotate, opacity, grayscale)
    - Resizable via corner handles
    - Selection highlight on hover/click
    - Like badge in corner
    - Missing file placeholder
    - Gallery integration (border colors from groups/likes)
    """

    # Class-level constants
    MIN_SIZE = 50
    DEFAULT_SIZE = 150
    HANDLE_SIZE = 10
    BADGE_SIZE = 20
    BORDER_WIDTH = 3

    # Scale modes for image rendering
    SCALE_FIT = "fit"        # Fit within bounds, preserve aspect ratio (letterbox)
    SCALE_FILL = "fill"      # Fill bounds, preserve aspect ratio (crop overflow)
    SCALE_STRETCH = "stretch"  # Stretch to fill bounds (distort)

    # LOD thresholds: (display_width_threshold, scale_factor)
    # When display width is below threshold, use scaled version
    LOD_LEVELS = [
        (100, 0.125),   # 12.5% when very small
        (200, 0.25),    # 25% when small
        (400, 0.5),     # 50% when medium-small
    ]
    # Large image threshold - only use LOD for images wider than this
    LOD_MIN_SOURCE_WIDTH = 2000

    def __init__(self, image_path: str, x: float = 0, y: float = 0,
                 width: float = None, height: float = None,
                 qimage: Optional[QImage] = None,
                 parent: QGraphicsItem = None,
                 content_hash: str = None):
        """
        Create an image node.

        Args:
            image_path: Path to the image file
            x, y: Position on canvas
            width, height: Size (None = use original image resolution)
            qimage: Optional pre-loaded QImage (for async loading - avoids disk I/O)
            parent: Parent graphics item
            content_hash: SHA-256 content hash for file identification
        """
        super().__init__(parent)

        self.image_path = image_path
        self.filename = os.path.basename(image_path)
        self.content_hash = content_hash
        self._requested_width = width
        self._requested_height = height
        self._width = width or self.DEFAULT_SIZE
        self._height = height or self.DEFAULT_SIZE
        self._liked = False
        self._missing = False
        self._pixmap: Optional[QPixmap] = None
        self._resize_handle = ResizeHandle.NONE
        self._resize_start_rect: Optional[QRectF] = None
        self._resize_start_pos: Optional[QPointF] = None
        self._resize_start_size: Optional[Tuple[float, float]] = None  # For undo support
        self._resize_start_item_pos: Optional[QPointF] = None  # For undo support

        # LOD cache: {scale_factor: QPixmap}
        self._lod_cache: Dict[float, QPixmap] = {}

        # Non-destructive transformation state
        self._crop_rect: Optional[QRectF] = None  # Crop rectangle in original image coords
        self._flip_h: bool = False  # Horizontal flip
        self._flip_v: bool = False  # Vertical flip
        self._rotation: float = 0.0  # Rotation in degrees
        self._opacity: float = 1.0  # 0.0 to 1.0
        self._grayscale: bool = False  # Grayscale toggle
        self._scale_mode: str = self.SCALE_FIT  # How image fills node bounds
        self._original_aspect: float = 1.0  # Original image aspect ratio (set after load)

        # Gallery integration
        self._show_gallery_border = True  # Toggle for showing group/like colors
        self._border_color: Optional[QColor] = None  # Cached border color from gallery
        self._group_ids: List[str] = []  # Group IDs this item belongs to

        # Setup item flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        # Position
        self.setPos(x, y)

        # Load image (use pre-loaded QImage if provided)
        self._load_image(qimage)

    def _load_image(self, qimage: Optional[QImage] = None):
        """Load the image from disk or pre-loaded QImage.

        Args:
            qimage: Optional pre-loaded QImage (from worker thread).
                    If provided, converts to QPixmap without disk I/O.
                    If None, loads from disk (original behavior).
        """
        # Use pre-loaded QImage if provided (async loading path)
        if qimage is not None and not qimage.isNull():
            self._pixmap = QPixmap.fromImage(qimage)
            self._missing = False
            # Clear LOD cache when loading new image
            self._lod_cache.clear()
            # Store original aspect ratio for constrained resize
            self._original_aspect = self._pixmap.width() / max(1, self._pixmap.height())
            # Use original image dimensions if no size was specified
            self._apply_dimensions_from_pixmap()
            return

        # Fallback: load from disk (sync loading path)
        if os.path.exists(self.image_path):
            self._pixmap = QPixmap(self.image_path)
            if self._pixmap.isNull():
                self._missing = True
                self._pixmap = None
            else:
                self._missing = False
                # Clear LOD cache when loading new image
                self._lod_cache.clear()
                # Store original aspect ratio for constrained resize
                self._original_aspect = self._pixmap.width() / max(1, self._pixmap.height())
                # Use original image dimensions if no size was specified
                self._apply_dimensions_from_pixmap()
        else:
            self._missing = True
            self._pixmap = None

    def _apply_dimensions_from_pixmap(self):
        """Apply dimensions based on loaded pixmap and requested size."""
        if not self._pixmap:
            return

        if self._requested_width is None and self._requested_height is None:
            self._width = float(self._pixmap.width())
            self._height = float(self._pixmap.height())
        elif self._requested_width is not None and self._requested_height is None:
            # Width specified, calculate height from aspect ratio
            aspect = self._pixmap.width() / max(1, self._pixmap.height())
            self._width = self._requested_width
            self._height = self._width / aspect
        elif self._requested_height is not None and self._requested_width is None:
            # Height specified, calculate width from aspect ratio
            aspect = self._pixmap.width() / max(1, self._pixmap.height())
            self._height = self._requested_height
            self._width = self._height * aspect
        else:
            # Both specified, use as-is
            self._width = self._requested_width
            self._height = self._requested_height

    def _get_lod_pixmap(self, lod: float) -> QPixmap:
        """
        Get an appropriate LOD pixmap for the current zoom level.

        Uses caching to avoid regenerating LOD versions repeatedly.

        Args:
            lod: Level of detail from Qt (1.0 = 100% zoom)

        Returns:
            The appropriate pixmap for rendering
        """
        if not self._pixmap or self._pixmap.isNull():
            return self._pixmap

        # Only use LOD for large images
        if self._pixmap.width() < self.LOD_MIN_SOURCE_WIDTH:
            return self._pixmap

        # Calculate display width at current zoom
        display_width = self._width * lod

        # Find appropriate LOD level
        scale_factor = 1.0
        for threshold, scale in self.LOD_LEVELS:
            if display_width < threshold:
                scale_factor = scale
                break

        # Use full resolution if scale is 1.0
        if scale_factor >= 1.0:
            return self._pixmap

        # Check cache
        if scale_factor in self._lod_cache:
            return self._lod_cache[scale_factor]

        # Generate LOD version
        lod_width = int(self._pixmap.width() * scale_factor)
        lod_height = int(self._pixmap.height() * scale_factor)
        lod_pixmap = self._pixmap.scaled(
            lod_width, lod_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # Cache it
        self._lod_cache[scale_factor] = lod_pixmap

        return lod_pixmap

    def _to_grayscale(self, pixmap: QPixmap) -> QPixmap:
        """Convert a pixmap to grayscale."""
        image = pixmap.toImage()
        gray_image = image.convertToFormat(QImage.Format_Grayscale8)
        # Convert back to ARGB for proper rendering
        gray_image = gray_image.convertToFormat(QImage.Format_ARGB32)
        return QPixmap.fromImage(gray_image)

    def clear_lod_cache(self):
        """Clear the LOD cache (call when image changes or on memory pressure)."""
        self._lod_cache.clear()

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle."""
        # Use a large fixed margin to account for screen-space elements
        # (handles, badge, border) at various zoom levels.
        # At 10% zoom, a 25px badge becomes 250 scene units, so we need
        # a generous margin. This is fine since Qt clips drawing anyway.
        margin = 300  # Large enough for zoom range 0.1x - 2x
        return QRectF(-margin, -margin,
                      self._width + 2 * margin,
                      self._height + 2 * margin)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        """
        Paint the image node with pixel density preservation.

        Uses LOD (Level of Detail) for large images when zoomed out,
        but always renders from original pixmap with SmoothPixmapTransform
        for maximum quality at any zoom level.
        """
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Get current level of detail from view transform
        lod = option.levelOfDetailFromTransform(painter.worldTransform())

        rect = QRectF(0, 0, self._width, self._height)

        if self._missing:
            # Draw placeholder for missing file
            painter.fillRect(rect, QColor(60, 60, 60))
            painter.setPen(QPen(QColor(100, 100, 100), 2, Qt.DashLine))
            painter.drawRect(rect)

            # Draw "missing" text
            painter.setPen(QColor(150, 150, 150))
            font = QFont()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "Missing")
        else:
            # Draw the image with pixel density preservation
            if self._pixmap and not self._pixmap.isNull():
                painter.save()

                # Apply opacity
                painter.setOpacity(self._opacity)

                # Get source pixmap (with LOD optimization for large images)
                pixmap = self._get_lod_pixmap(lod)

                # Apply grayscale if enabled
                if self._grayscale:
                    pixmap = self._to_grayscale(pixmap)

                # Calculate source rectangle (for crop)
                if self._crop_rect:
                    # Scale crop rect from original image coords to LOD pixmap coords
                    scale_x = pixmap.width() / self._pixmap.width()
                    scale_y = pixmap.height() / self._pixmap.height()
                    source_rect = QRectF(
                        self._crop_rect.x() * scale_x,
                        self._crop_rect.y() * scale_y,
                        self._crop_rect.width() * scale_x,
                        self._crop_rect.height() * scale_y
                    )
                else:
                    source_rect = QRectF(pixmap.rect())

                # Calculate destination rectangle based on scale mode
                img_aspect = source_rect.width() / max(1, source_rect.height())
                rect_aspect = self._width / max(1, self._height)

                if self._scale_mode == self.SCALE_STRETCH:
                    # Stretch to fill bounds (distort aspect ratio)
                    draw_width = self._width
                    draw_height = self._height
                    draw_rect = QRectF(0, 0, draw_width, draw_height)
                elif self._scale_mode == self.SCALE_FILL:
                    # Fill bounds, preserve aspect ratio (crop overflow)
                    if img_aspect > rect_aspect:
                        # Image is wider - fit to height, crop sides
                        draw_height = self._height
                        draw_width = self._height * img_aspect
                    else:
                        # Image is taller - fit to width, crop top/bottom
                        draw_width = self._width
                        draw_height = self._width / img_aspect
                    draw_rect = QRectF(
                        (self._width - draw_width) / 2,
                        (self._height - draw_height) / 2,
                        draw_width,
                        draw_height
                    )
                else:
                    # SCALE_FIT (default): Fit within bounds, preserve aspect ratio (letterbox)
                    if img_aspect > rect_aspect:
                        # Image is wider - fit to width
                        draw_width = self._width
                        draw_height = self._width / img_aspect
                    else:
                        # Image is taller - fit to height
                        draw_height = self._height
                        draw_width = self._height * img_aspect
                    draw_rect = QRectF(
                        (self._width - draw_width) / 2,
                        (self._height - draw_height) / 2,
                        draw_width,
                        draw_height
                    )

                # Apply rotation if needed
                if self._rotation != 0:
                    center = QPointF(self._width / 2, self._height / 2)
                    painter.translate(center)
                    painter.rotate(self._rotation)
                    painter.translate(-center)

                # Apply flip transforms
                if self._flip_h or self._flip_v:
                    flip_center = draw_rect.center()
                    painter.translate(flip_center)
                    painter.scale(-1 if self._flip_h else 1, -1 if self._flip_v else 1)
                    painter.translate(-flip_center)

                # Draw the pixmap from source rect to draw rect
                # This maintains full pixel density - Qt handles the scaling
                painter.drawPixmap(draw_rect, pixmap, source_rect)

                painter.restore()

        # Draw gallery border (group/like color) if enabled
        # Use cosmetic pen so border width stays constant in screen space
        if self._show_gallery_border and self._border_color:
            border_pen = QPen(self._border_color, self.BORDER_WIDTH)
            border_pen.setCosmetic(True)  # Screen-space width
            painter.setPen(border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # Selection highlight (on top of gallery border)
        # Use cosmetic pen so selection border stays constant in screen space
        if self.isSelected():
            select_pen = QPen(QColor(74, 158, 255), 2)
            select_pen.setCosmetic(True)  # Screen-space width
            painter.setPen(select_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))

            # Draw resize handles
            self._draw_resize_handles(painter)

        # Like badge
        if self._liked:
            self._draw_like_badge(painter)

    def _get_screen_space_size(self, size: float) -> float:
        """Convert a screen-space size to scene-space based on current zoom."""
        scene = self.scene()
        if scene and scene.views():
            view = scene.views()[0]
            # Get the zoom factor from the view's transform
            zoom = view.transform().m11()  # Assumes uniform scaling
            if zoom > 0:
                return size / zoom
        return size

    def _draw_resize_handles(self, painter: QPainter):
        """Draw resize handles at corners (screen-space size)."""
        handle_color = QColor(74, 158, 255)
        painter.setBrush(QBrush(handle_color))
        painter.setPen(Qt.NoPen)

        # Get screen-space handle size
        hs = self._get_screen_space_size(self.HANDLE_SIZE)

        # Corner handles
        handles = [
            QRectF(-hs/2, -hs/2, hs, hs),  # Top-left
            QRectF(self._width - hs/2, -hs/2, hs, hs),  # Top-right
            QRectF(-hs/2, self._height - hs/2, hs, hs),  # Bottom-left
            QRectF(self._width - hs/2, self._height - hs/2, hs, hs),  # Bottom-right
        ]

        for handle_rect in handles:
            painter.drawRect(handle_rect)

    def _draw_like_badge(self, painter: QPainter):
        """Draw the like heart badge in corner (screen-space size)."""
        # Get screen-space badge size
        badge_size = self._get_screen_space_size(self.BADGE_SIZE)
        margin = self._get_screen_space_size(5)

        badge_rect = QRectF(
            self._width - badge_size - margin,
            margin,
            badge_size,
            badge_size
        )

        # Red circle background
        painter.setBrush(QBrush(QColor(239, 68, 68)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(badge_rect)

        # Heart symbol - use screen-space font size
        painter.setPen(QColor(255, 255, 255))
        font = QFont()
        font_size = self._get_screen_space_size(12)
        font.setPointSizeF(max(6, font_size))  # Minimum readable size
        painter.setFont(font)
        painter.drawText(badge_rect, Qt.AlignCenter, "♥")

    def _get_handle_at(self, pos: QPointF) -> ResizeHandle:
        """Get the resize handle at the given position (screen-space hit detection)."""
        if not self.isSelected():
            return ResizeHandle.NONE

        # Use screen-space handle size for consistent hit detection
        hs = self._get_screen_space_size(self.HANDLE_SIZE)

        # Check each corner
        if QRectF(-hs/2, -hs/2, hs, hs).contains(pos):
            return ResizeHandle.TOP_LEFT
        if QRectF(self._width - hs/2, -hs/2, hs, hs).contains(pos):
            return ResizeHandle.TOP_RIGHT
        if QRectF(-hs/2, self._height - hs/2, hs, hs).contains(pos):
            return ResizeHandle.BOTTOM_LEFT
        if QRectF(self._width - hs/2, self._height - hs/2, hs, hs).contains(pos):
            return ResizeHandle.BOTTOM_RIGHT

        return ResizeHandle.NONE

    def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent):
        """Update cursor based on position."""
        handle = self._get_handle_at(event.pos())

        if handle in (ResizeHandle.TOP_LEFT, ResizeHandle.BOTTOM_RIGHT):
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in (ResizeHandle.TOP_RIGHT, ResizeHandle.BOTTOM_LEFT):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle mouse press for resize or move."""
        if event.button() == Qt.LeftButton:
            self._resize_handle = self._get_handle_at(event.pos())
            if self._resize_handle != ResizeHandle.NONE:
                self._resize_start_rect = QRectF(0, 0, self._width, self._height)
                self._resize_start_pos = event.pos()
                # Store initial size and position for undo support
                self._resize_start_size = (self._width, self._height)
                self._resize_start_item_pos = QPointF(self.x(), self.y())
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle mouse move for resize."""
        if self._resize_handle != ResizeHandle.NONE:
            self._do_resize(event.pos(), event.modifiers())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle mouse release after resize."""
        if self._resize_handle != ResizeHandle.NONE:
            # Push undo command if size actually changed
            if self._resize_start_size is not None:
                old_size = self._resize_start_size
                new_size = (self._width, self._height)
                # Only create undo command if size changed
                if old_size != new_size:
                    self._push_resize_undo_command(old_size, new_size)

            self._resize_handle = ResizeHandle.NONE
            self._resize_start_rect = None
            self._resize_start_pos = None
            self._resize_start_size = None
            self._resize_start_item_pos = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _push_resize_undo_command(self, old_size: Tuple[float, float], new_size: Tuple[float, float]):
        """Push a resize command to the undo stack.

        Args:
            old_size: (width, height) before resize
            new_size: (width, height) after resize
        """
        scene = self.scene()
        if not scene or not scene.views():
            return

        view = scene.views()[0]
        if not hasattr(view, '_undo_stack') or not view._undo_stack:
            return

        from .canvas_undo import ResizeItemCommand

        # Use filename as the item ID
        cmd = ResizeItemCommand(view, self.filename, old_size, new_size)
        # Don't execute - the resize already happened, just record it
        view._undo_stack._undo_stack.append(cmd)
        view._undo_stack._redo_stack.clear()
        view._undo_stack._emit_changes()
        logger.debug(f"Pushed resize command: {old_size} -> {new_size}")

    def _do_resize(self, pos: QPointF, modifiers: Qt.KeyboardModifiers = Qt.NoModifier):
        """Perform the resize operation.

        Args:
            pos: Current mouse position
            modifiers: Keyboard modifiers (Shift for aspect-ratio constrained)
        """
        if not self._resize_start_rect or not self._resize_start_pos:
            return

        delta = pos - self._resize_start_pos
        old_rect = self._resize_start_rect

        new_width = self._width
        new_height = self._height
        new_x = self.x()
        new_y = self.y()

        # Calculate new size based on which handle is being dragged
        if self._resize_handle == ResizeHandle.BOTTOM_RIGHT:
            new_width = max(self.MIN_SIZE, old_rect.width() + delta.x())
            new_height = max(self.MIN_SIZE, old_rect.height() + delta.y())
        elif self._resize_handle == ResizeHandle.TOP_LEFT:
            new_width = max(self.MIN_SIZE, old_rect.width() - delta.x())
            new_height = max(self.MIN_SIZE, old_rect.height() - delta.y())
            if new_width > self.MIN_SIZE:
                new_x = self.x() + delta.x()
            if new_height > self.MIN_SIZE:
                new_y = self.y() + delta.y()
        elif self._resize_handle == ResizeHandle.TOP_RIGHT:
            new_width = max(self.MIN_SIZE, old_rect.width() + delta.x())
            new_height = max(self.MIN_SIZE, old_rect.height() - delta.y())
            if new_height > self.MIN_SIZE:
                new_y = self.y() + delta.y()
        elif self._resize_handle == ResizeHandle.BOTTOM_LEFT:
            new_width = max(self.MIN_SIZE, old_rect.width() - delta.x())
            new_height = max(self.MIN_SIZE, old_rect.height() + delta.y())
            if new_width > self.MIN_SIZE:
                new_x = self.x() + delta.x()

        # If Shift is held, constrain to original aspect ratio
        if modifiers & Qt.ShiftModifier and self._original_aspect > 0:
            aspect = self._original_aspect
            # Determine which dimension to constrain based on the drag direction
            # Use the dimension that changed more as the driver
            width_change = abs(new_width - old_rect.width())
            height_change = abs(new_height - old_rect.height())

            if width_change >= height_change:
                # Width drives, adjust height
                constrained_height = new_width / aspect
                height_diff = constrained_height - new_height

                # Adjust position for handles that move the top edge
                if self._resize_handle in (ResizeHandle.TOP_LEFT, ResizeHandle.TOP_RIGHT):
                    new_y -= height_diff
                new_height = constrained_height
            else:
                # Height drives, adjust width
                constrained_width = new_height * aspect
                width_diff = constrained_width - new_width

                # Adjust position for handles that move the left edge
                if self._resize_handle in (ResizeHandle.TOP_LEFT, ResizeHandle.BOTTOM_LEFT):
                    new_x -= width_diff
                new_width = constrained_width

        # Apply changes
        self.prepareGeometryChange()
        self._width = max(self.MIN_SIZE, new_width)
        self._height = max(self.MIN_SIZE, new_height)
        self.setPos(new_x, new_y)
        self.update()

    def set_liked(self, liked: bool):
        """Set the liked state."""
        if self._liked != liked:
            self._liked = liked
            self.update()

    def is_liked(self) -> bool:
        """Check if node is liked."""
        return self._liked

    def get_size(self) -> Tuple[float, float]:
        """Get current size."""
        return (self._width, self._height)

    def set_size(self, width: float, height: float):
        """Set the size."""
        self.prepareGeometryChange()
        self._width = max(self.MIN_SIZE, width)
        self._height = max(self.MIN_SIZE, height)
        self.update()

    # -------------------------------------------------------------------------
    # Non-Destructive Transformations
    # -------------------------------------------------------------------------

    def set_crop(self, crop_rect: Optional[QRectF]):
        """
        Set the crop rectangle (in original image coordinates).

        Args:
            crop_rect: Crop rectangle, or None to reset
        """
        self._crop_rect = crop_rect
        self.update()

    def get_crop(self) -> Optional[QRectF]:
        """Get the current crop rectangle."""
        return self._crop_rect

    def reset_crop(self):
        """Reset crop to show full image."""
        self._crop_rect = None
        self.update()

    def flip_horizontal(self):
        """Toggle horizontal flip."""
        self._flip_h = not self._flip_h
        self.update()

    def flip_vertical(self):
        """Toggle vertical flip."""
        self._flip_v = not self._flip_v
        self.update()

    def set_flip(self, horizontal: bool, vertical: bool):
        """Set flip state."""
        self._flip_h = horizontal
        self._flip_v = vertical
        self.update()

    def get_flip(self) -> Tuple[bool, bool]:
        """Get flip state as (horizontal, vertical)."""
        return (self._flip_h, self._flip_v)

    def set_rotation(self, degrees: float):
        """Set rotation in degrees."""
        self._rotation = degrees % 360
        self.update()

    def rotate(self, degrees: float):
        """Add rotation in degrees."""
        self._rotation = (self._rotation + degrees) % 360
        self.update()

    def get_rotation(self) -> float:
        """Get rotation in degrees."""
        return self._rotation

    def set_opacity(self, opacity: float):
        """
        Set opacity (0.0 to 1.0).

        Args:
            opacity: Opacity value, clamped to 0.0-1.0
        """
        self._opacity = max(0.0, min(1.0, opacity))
        self.update()

    def adjust_opacity(self, delta: float):
        """
        Adjust opacity by delta.

        Args:
            delta: Amount to change (positive or negative)
        """
        self.set_opacity(self._opacity + delta)

    def get_opacity(self) -> float:
        """Get current opacity."""
        return self._opacity

    def set_grayscale(self, grayscale: bool):
        """Set grayscale mode."""
        self._grayscale = grayscale
        self.update()

    def toggle_grayscale(self):
        """Toggle grayscale mode."""
        self._grayscale = not self._grayscale
        self.update()

    def is_grayscale(self) -> bool:
        """Check if grayscale mode is enabled."""
        return self._grayscale

    def set_scale_mode(self, mode: str):
        """Set the scale mode for rendering.

        Args:
            mode: One of SCALE_FIT, SCALE_FILL, or SCALE_STRETCH
        """
        if mode in (self.SCALE_FIT, self.SCALE_FILL, self.SCALE_STRETCH):
            self._scale_mode = mode
            self.update()

    def get_scale_mode(self) -> str:
        """Get the current scale mode."""
        return self._scale_mode

    def cycle_scale_mode(self):
        """Cycle through scale modes: fit -> fill -> stretch -> fit."""
        modes = [self.SCALE_FIT, self.SCALE_FILL, self.SCALE_STRETCH]
        current_idx = modes.index(self._scale_mode) if self._scale_mode in modes else 0
        self._scale_mode = modes[(current_idx + 1) % len(modes)]
        self.update()

    def reset_transforms(self):
        """Reset all non-destructive transforms to default."""
        self._crop_rect = None
        self._flip_h = False
        self._flip_v = False
        self._rotation = 0.0
        self._opacity = 1.0
        self._grayscale = False
        self.update()

    def reset_crop(self):
        """Reset crop to show full image."""
        self._crop_rect = None
        self.update()

    def _reset_all_transforms(self):
        """Context menu handler to reset all transforms."""
        self.reset_transforms()

    def get_transform_state(self) -> dict:
        """Get all transform state as a dict for serialization."""
        return {
            'crop': [self._crop_rect.x(), self._crop_rect.y(),
                     self._crop_rect.width(), self._crop_rect.height()] if self._crop_rect else None,
            'flip_h': self._flip_h,
            'flip_v': self._flip_v,
            'rotation': self._rotation,
            'opacity': self._opacity,
            'grayscale': self._grayscale,
        }

    def set_transform_state(self, state: dict):
        """Restore transform state from a dict."""
        if state.get('crop'):
            c = state['crop']
            self._crop_rect = QRectF(c[0], c[1], c[2], c[3])
        else:
            self._crop_rect = None
        self._flip_h = state.get('flip_h', False)
        self._flip_v = state.get('flip_v', False)
        self._rotation = state.get('rotation', 0.0)
        self._opacity = state.get('opacity', 1.0)
        self._grayscale = state.get('grayscale', False)
        self.update()

    # -------------------------------------------------------------------------
    # Gallery Integration
    # -------------------------------------------------------------------------

    def set_border_color(self, color: Optional[QColor]):
        """Set the border color (from gallery group/like status)."""
        self._border_color = color
        self.update()

    def set_show_gallery_border(self, show: bool):
        """Toggle showing the gallery border."""
        self._show_gallery_border = show
        self.update()

    def set_group_ids(self, group_ids: List[str]):
        """Set the group IDs this item belongs to."""
        self._group_ids = group_ids

    def get_group_ids(self) -> List[str]:
        """Get the group IDs this item belongs to."""
        return self._group_ids

    def sync_from_gallery(self, favorites_manager):
        """
        Sync this node's state from the gallery FavoritesManager.

        Args:
            favorites_manager: The FavoritesManager instance from gallery tab
        """
        if not favorites_manager:
            return

        path = self.image_path
        content_hash = self.content_hash

        # Sync like status (with hash fallback for renamed files)
        self._liked = favorites_manager.is_liked(path, content_hash=content_hash)

        # Sync group membership (with hash fallback for renamed files)
        self._group_ids = list(favorites_manager.get_item_groups(path, content_hash=content_hash))

        # Get border color based on groups or like status
        self._border_color = self._get_gallery_border_color(favorites_manager)

        self.update()

    def _get_gallery_border_color(self, favorites_manager) -> Optional[QColor]:
        """Get the border color based on group membership or like status."""
        path = self.image_path
        content_hash = self.content_hash

        # Priority: group color > liked color
        groups = favorites_manager.get_item_groups(path, content_hash=content_hash)
        if groups:
            # Use the first group's color
            first_group_id = next(iter(groups))
            group_def = favorites_manager.get_group(first_group_id)
            if group_def:
                return QColor(group_def.color)

        # Fallback to like color
        if favorites_manager.is_liked(path, content_hash=content_hash):
            return QColor(239, 68, 68)  # Red for liked

        return None

    def itemChange(self, change, value):
        """Handle item changes for snapping and connection updates."""
        if change == QGraphicsItem.ItemPositionChange:
            # Apply snapping before position change
            new_pos = value
            scene = self.scene()
            if scene and scene.views():
                view = scene.views()[0]
                # Grid snapping
                if hasattr(view, 'snap_position_to_grid'):
                    new_pos = view.snap_position_to_grid(new_pos)
                # Neighbor snapping
                if hasattr(view, 'snap_to_neighbor_items'):
                    new_pos = view.snap_to_neighbor_items(self, new_pos)
            return new_pos

        if change == QGraphicsItem.ItemPositionHasChanged:
            # Notify connected lines to update
            scene = self.scene()
            if scene:
                for item in scene.items():
                    if isinstance(item, ConnectionLine):
                        if item.source_node == self or item.target_node == self:
                            item.update_path()

        return super().itemChange(change, value)

    def contextMenuEvent(self, event: QGraphicsSceneMouseEvent):
        """Show context menu with gallery integration."""
        menu = QMenu()

        # Like action (synced with gallery)
        like_action = menu.addAction("♥ Unlike" if self._liked else "♡ Like")
        like_action.triggered.connect(self._toggle_like)

        # Groups submenu
        groups_menu = menu.addMenu("Add to Group")
        self._populate_groups_menu(groups_menu)

        menu.addSeparator()

        # Gallery actions
        show_in_gallery = menu.addAction("Show in Gallery")
        show_in_gallery.triggered.connect(self._show_in_gallery)

        open_folder = menu.addAction("Open Containing Folder")
        open_folder.triggered.connect(self._open_folder)

        properties_action = menu.addAction("Properties...")
        properties_action.triggered.connect(self._show_properties)

        menu.addSeparator()

        # Image Transform submenu
        transform_menu = menu.addMenu("Transform")

        # Flip options
        flip_h_action = transform_menu.addAction("Flip Horizontal (F)")
        flip_h_action.triggered.connect(self.flip_horizontal)
        flip_v_action = transform_menu.addAction("Flip Vertical (Shift+F)")
        flip_v_action.triggered.connect(self.flip_vertical)

        transform_menu.addSeparator()

        # Rotation options
        rotate_cw_action = transform_menu.addAction("Rotate 90° CW (R)")
        rotate_cw_action.triggered.connect(lambda: self.rotate(90))
        rotate_ccw_action = transform_menu.addAction("Rotate 90° CCW (Shift+R)")
        rotate_ccw_action.triggered.connect(lambda: self.rotate(-90))
        reset_rot_action = transform_menu.addAction("Reset Rotation")
        reset_rot_action.triggered.connect(lambda: self.set_rotation(0))

        transform_menu.addSeparator()

        # Reset crop if active
        if self._crop_rect:
            reset_crop_action = transform_menu.addAction("Reset Crop")
            reset_crop_action.triggered.connect(self.reset_crop)
            transform_menu.addSeparator()

        # Reset all transforms
        reset_all_action = transform_menu.addAction("Reset All Transforms")
        reset_all_action.triggered.connect(self._reset_all_transforms)

        # Opacity submenu
        opacity_menu = menu.addMenu(f"Opacity ({int(self._opacity * 100)}%)")
        for pct in [100, 90, 75, 50, 25, 10]:
            opacity_action = opacity_menu.addAction(f"{pct}%")
            opacity_action.triggered.connect(lambda checked, p=pct: self.set_opacity(p / 100.0))

        # Grayscale toggle
        gs_text = "Color Mode" if self._grayscale else "Grayscale (Shift+G)"
        grayscale_action = menu.addAction(gs_text)
        grayscale_action.triggered.connect(self.toggle_grayscale)

        # Scale mode submenu
        mode_labels = {self.SCALE_FIT: "Fit", self.SCALE_FILL: "Fill", self.SCALE_STRETCH: "Stretch"}
        current_label = mode_labels.get(self._scale_mode, "Fit")
        scale_menu = menu.addMenu(f"Scale Mode ({current_label})")
        for mode, label in mode_labels.items():
            mode_action = scale_menu.addAction(label)
            mode_action.setCheckable(True)
            mode_action.setChecked(self._scale_mode == mode)
            mode_action.triggered.connect(lambda checked, m=mode: self.set_scale_mode(m))

        menu.addSeparator()

        # Display options
        border_action = menu.addAction("Hide Border Colors" if self._show_gallery_border else "Show Border Colors")
        border_action.triggered.connect(lambda: self.set_show_gallery_border(not self._show_gallery_border))

        menu.addSeparator()

        delete_action = menu.addAction("Remove from Canvas")
        delete_action.triggered.connect(self._remove_from_canvas)

        menu.exec_(event.screenPos())

    def _get_favorites_manager(self):
        """Get the FavoritesManager from the view."""
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if view and hasattr(view, '_get_favorites_manager'):
            return view._get_favorites_manager()
        return None

    def _populate_groups_menu(self, menu: QMenu):
        """Populate the groups submenu with available groups."""
        favorites_manager = self._get_favorites_manager()
        if not favorites_manager:
            no_groups = menu.addAction("(No groups available)")
            no_groups.setEnabled(False)
            return

        groups = favorites_manager.get_groups()
        if not groups:
            no_groups = menu.addAction("(No groups created)")
            no_groups.setEnabled(False)
            menu.addSeparator()
            create_action = menu.addAction("Create New Group...")
            create_action.triggered.connect(self._create_new_group)
            return

        # Get current group memberships
        current_groups = favorites_manager.get_item_groups(self.image_path)

        # Add each group as a checkable action
        for group in groups:
            # Show color indicator and name
            is_member = group.group_id in current_groups
            action_text = f"{'✓ ' if is_member else '   '}{group.name}"
            action = menu.addAction(action_text)
            # Use default argument to capture group_id by value
            action.triggered.connect(lambda checked, gid=group.group_id: self._toggle_group(gid))

        menu.addSeparator()

        # Remove from all groups option
        if current_groups:
            remove_all = menu.addAction("Remove from All Groups")
            remove_all.triggered.connect(self._remove_from_all_groups)

        menu.addSeparator()
        create_action = menu.addAction("Create New Group...")
        create_action.triggered.connect(self._create_new_group)

    def _toggle_group(self, group_id: str):
        """Toggle membership in a group."""
        favorites_manager = self._get_favorites_manager()
        if not favorites_manager:
            return

        current_groups = favorites_manager.get_item_groups(self.image_path)
        if group_id in current_groups:
            favorites_manager.remove_from_group(self.image_path, group_id)
        else:
            favorites_manager.add_to_group(self.image_path, group_id)

        # Refresh border color
        self.sync_from_gallery(favorites_manager)

    def _remove_from_all_groups(self):
        """Remove this item from all groups."""
        favorites_manager = self._get_favorites_manager()
        if not favorites_manager:
            return

        current_groups = list(favorites_manager.get_item_groups(self.image_path))
        for group_id in current_groups:
            favorites_manager.remove_from_group(self.image_path, group_id)

        # Refresh border color
        self.sync_from_gallery(favorites_manager)

    def _create_new_group(self):
        """Create a new group and add this item to it."""
        from PySide6.QtWidgets import QInputDialog
        from core.config import UIColors

        favorites_manager = self._get_favorites_manager()
        if not favorites_manager:
            return

        name, ok = QInputDialog.getText(
            None, "New Group",
            "Enter group name:"
        )
        if ok and name:
            # Use first available color
            group = favorites_manager.create_group(name)
            if group:
                favorites_manager.add_to_group(self.image_path, group.group_id)
                # Refresh border color
                self.sync_from_gallery(favorites_manager)

    def _toggle_like(self):
        """Toggle like status and sync with gallery."""
        new_liked = not self._liked
        self.set_liked(new_liked)

        # Sync to gallery if possible
        favorites_manager = self._get_favorites_manager()
        if favorites_manager:
            if new_liked:
                favorites_manager.like_item(self.image_path)
            else:
                favorites_manager.unlike_item(self.image_path)

    def _show_in_gallery(self):
        """Show this image in the gallery tab."""
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if view and hasattr(view, '_show_in_gallery'):
            view._show_in_gallery(self.image_path)

    def _open_folder(self):
        """Open the containing folder in the file explorer."""
        import subprocess
        folder = os.path.dirname(self.image_path)
        if os.path.exists(folder):
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.Popen(f'explorer /select,"{self.image_path}"', creationflags=creationflags)

    def _show_properties(self):
        """Show properties dialog for this image."""
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if view and hasattr(view, '_show_properties'):
            view._show_properties(self.image_path)

    def _remove_from_canvas(self):
        """Remove this node from the canvas."""
        scene = self.scene()
        if scene:
            # Remove connected lines first
            for item in list(scene.items()):
                if isinstance(item, ConnectionLine):
                    if item.source_node == self or item.target_node == self:
                        scene.removeItem(item)
            scene.removeItem(self)


class ConnectionLine(QGraphicsPathItem):
    """
    A bezier curve connection between two image nodes.

    Features:
    - Smooth bezier curves (like Blender/Nuke)
    - Arrow at destination
    - Double-click to add annotation
    - Auto-update when nodes move
    """

    # Colors for different connection types
    COLORS = {
        'auto': QColor(74, 158, 255),   # Blue for auto-detected from metadata
        'manual': QColor(255, 165, 0),  # Orange for manual connections
    }

    def __init__(self, source_node: ImageNode, target_node: ImageNode,
                 connection_type: str = 'manual', label: str = '',
                 connection_id: str = None, parent: QGraphicsItem = None):
        super().__init__(parent)

        self.source_node = source_node
        self.target_node = target_node
        self.connection_type = connection_type
        self.label = label
        self.connection_id = connection_id  # Set by canvas after creation

        # Setup
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)  # Draw behind nodes

        # Set pen
        color = self.COLORS.get(connection_type, self.COLORS['manual'])
        pen = QPen(color, 2)
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)

        # Initial path
        self.update_path()

    def update_path(self):
        """Update the bezier path between source and target."""
        if not self.source_node or not self.target_node:
            return

        # Get center points of nodes
        source_rect = self.source_node.boundingRect()
        target_rect = self.target_node.boundingRect()

        source_center = self.source_node.pos() + source_rect.center()
        target_center = self.target_node.pos() + target_rect.center()

        # Calculate control points for smooth bezier
        dx = target_center.x() - source_center.x()
        dy = target_center.y() - source_center.y()

        # Control point offset (creates nice curves)
        ctrl_offset = min(abs(dx), abs(dy)) * 0.5 + 50

        # Create bezier path
        path = QPainterPath()
        path.moveTo(source_center)

        # Control points
        ctrl1 = QPointF(source_center.x() + ctrl_offset, source_center.y())
        ctrl2 = QPointF(target_center.x() - ctrl_offset, target_center.y())

        path.cubicTo(ctrl1, ctrl2, target_center)

        self.setPath(path)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        """Paint the connection line with arrow."""
        # Draw the path
        super().paint(painter, option, widget)

        # Draw arrow at target
        self._draw_arrow(painter)

        # Draw label if present
        if self.label:
            self._draw_label(painter)

        # Selection highlight
        if self.isSelected():
            highlight_pen = QPen(QColor(255, 255, 255, 100), 6)
            painter.setPen(highlight_pen)
            painter.drawPath(self.path())

    def _draw_arrow(self, painter: QPainter):
        """Draw arrow head at the target end."""
        path = self.path()
        if path.isEmpty():
            return

        # Get the end point and direction
        end_point = path.pointAtPercent(1.0)
        near_end = path.pointAtPercent(0.95)

        # Calculate arrow direction
        dx = end_point.x() - near_end.x()
        dy = end_point.y() - near_end.y()

        import math
        angle = math.atan2(dy, dx)

        # Arrow size
        arrow_size = 12
        arrow_angle = math.pi / 6  # 30 degrees

        # Calculate arrow points
        p1 = QPointF(
            end_point.x() - arrow_size * math.cos(angle - arrow_angle),
            end_point.y() - arrow_size * math.sin(angle - arrow_angle)
        )
        p2 = QPointF(
            end_point.x() - arrow_size * math.cos(angle + arrow_angle),
            end_point.y() - arrow_size * math.sin(angle + arrow_angle)
        )

        # Draw arrow
        arrow_path = QPainterPath()
        arrow_path.moveTo(end_point)
        arrow_path.lineTo(p1)
        arrow_path.lineTo(p2)
        arrow_path.closeSubpath()

        color = self.COLORS.get(self.connection_type, self.COLORS['manual'])
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(arrow_path)

    def _draw_label(self, painter: QPainter):
        """Draw the label at the middle of the connection."""
        path = self.path()
        if path.isEmpty():
            return

        # Get midpoint
        mid_point = path.pointAtPercent(0.5)

        # Draw label background
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)

        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(self.label)

        bg_rect = QRectF(
            mid_point.x() - text_rect.width() / 2 - 4,
            mid_point.y() - text_rect.height() / 2 - 2,
            text_rect.width() + 8,
            text_rect.height() + 4
        )

        painter.setBrush(QBrush(QColor(40, 40, 40, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bg_rect, 3, 3)

        # Draw text
        painter.setPen(QColor(200, 200, 200))
        painter.drawText(bg_rect, Qt.AlignCenter, self.label)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle double-click to edit label."""
        text, ok = QInputDialog.getText(
            None, "Connection Label",
            "Enter label for this connection:",
            text=self.label
        )
        if ok:
            self.label = text
            self.update()

    def contextMenuEvent(self, event: QGraphicsSceneMouseEvent):
        """Show context menu."""
        menu = QMenu()

        edit_action = menu.addAction("Edit Label...")
        edit_action.triggered.connect(lambda: self.mouseDoubleClickEvent(event))

        menu.addSeparator()

        delete_action = menu.addAction("Delete Connection")
        delete_action.triggered.connect(self._remove)

        menu.exec_(event.screenPos())

    def _remove(self):
        """Remove this connection via the canvas for proper cleanup."""
        scene = self.scene()
        if scene and self.connection_id:
            # Get the canvas (view) to call remove_connection for proper cleanup
            views = scene.views()
            if views:
                canvas = views[0]
                if hasattr(canvas, 'remove_connection'):
                    canvas.remove_connection(self.connection_id)
                    return
        # Fallback: direct scene removal (won't update canvas dict or emit signals)
        if scene:
            scene.removeItem(self)


class StickyNote(QGraphicsItem):
    """
    A resizable sticky note for annotations.

    Features:
    - Resizable (drag corners)
    - 4 colors (yellow, green, red, blue)
    - Double-click to edit text
    """

    COLORS = {
        'yellow': QColor(255, 245, 157),
        'green': QColor(165, 214, 167),
        'red': QColor(239, 154, 154),
        'blue': QColor(144, 202, 249),
    }

    FONT_SIZES = {'Small': 8, 'Medium': 10, 'Large': 14, 'XL': 18}
    DEFAULT_FONT_SIZE = 10

    MIN_SIZE = 80
    DEFAULT_WIDTH = 150
    DEFAULT_HEIGHT = 100
    HANDLE_SIZE = 8

    def __init__(self, x: float, y: float, text: str = '',
                 color: str = 'yellow', font_size: int = 10,
                 parent: QGraphicsItem = None):
        super().__init__(parent)

        self.text = text
        self.color_name = color
        self.font_size = font_size
        self._width = self.DEFAULT_WIDTH
        self._height = self.DEFAULT_HEIGHT
        self._resize_handle = ResizeHandle.NONE
        self._resize_start_rect: Optional[QRectF] = None
        self._resize_start_pos: Optional[QPointF] = None

        # Setup flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        self.setPos(x, y)

    def itemChange(self, change, value):
        """Handle item changes for snapping."""
        if change == QGraphicsItem.ItemPositionChange:
            new_pos = value
            scene = self.scene()
            if scene and scene.views():
                view = scene.views()[0]
                if hasattr(view, 'snap_position_to_grid'):
                    new_pos = view.snap_position_to_grid(new_pos)
                if hasattr(view, 'snap_to_neighbor_items'):
                    new_pos = view.snap_to_neighbor_items(self, new_pos)
            return new_pos
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        margin = self.HANDLE_SIZE if self.isSelected() else 0
        return QRectF(-margin, -margin,
                      self._width + 2 * margin,
                      self._height + 2 * margin)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(0, 0, self._width, self._height)

        # Resolve color: preset name or hex string
        if self.color_name.startswith('#'):
            color = QColor(self.color_name)
        else:
            color = self.COLORS.get(self.color_name, self.COLORS['yellow'])

        # Draw note background
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(110), 1))
        painter.drawRoundedRect(rect, 5, 5)

        # Draw text
        text_rect = rect.adjusted(8, 8, -8, -8)
        painter.setPen(QColor(50, 50, 50))
        font = QFont()
        font.setPointSize(self.font_size)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.TextWordWrap, self.text)

        # Selection highlight and handles
        if self.isSelected():
            painter.setPen(QPen(QColor(74, 158, 255), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 5, 5)
            self._draw_resize_handles(painter)

    def _draw_resize_handles(self, painter: QPainter):
        """Draw resize handles at corners."""
        painter.setBrush(QBrush(QColor(74, 158, 255)))
        painter.setPen(Qt.NoPen)

        hs = self.HANDLE_SIZE
        handles = [
            QRectF(self._width - hs/2, self._height - hs/2, hs, hs),
        ]

        for handle_rect in handles:
            painter.drawRect(handle_rect)

    def _get_handle_at(self, pos: QPointF) -> ResizeHandle:
        """Get resize handle at position."""
        if not self.isSelected():
            return ResizeHandle.NONE

        hs = self.HANDLE_SIZE
        if QRectF(self._width - hs/2, self._height - hs/2, hs, hs).contains(pos):
            return ResizeHandle.BOTTOM_RIGHT

        return ResizeHandle.NONE

    def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent):
        handle = self._get_handle_at(event.pos())
        if handle == ResizeHandle.BOTTOM_RIGHT:
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.LeftButton:
            self._resize_handle = self._get_handle_at(event.pos())
            if self._resize_handle != ResizeHandle.NONE:
                self._resize_start_rect = QRectF(0, 0, self._width, self._height)
                self._resize_start_pos = event.pos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._resize_handle != ResizeHandle.NONE:
            delta = event.pos() - self._resize_start_pos
            self.prepareGeometryChange()
            self._width = max(self.MIN_SIZE, self._resize_start_rect.width() + delta.x())
            self._height = max(self.MIN_SIZE, self._resize_start_rect.height() + delta.y())
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._resize_handle != ResizeHandle.NONE:
            self._resize_handle = ResizeHandle.NONE
            self._resize_start_rect = None
            self._resize_start_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        """Edit text on double-click."""
        # Set editing flag on canvas to suppress shortcuts during text input
        canvas = None
        scene = self.scene()
        if scene:
            views = scene.views()
            if views:
                canvas = views[0]
                if hasattr(canvas, '_editing_text'):
                    canvas._editing_text = True

        try:
            text, ok = QInputDialog.getMultiLineText(
                None, "Edit Note",
                "Enter note text:",
                self.text
            )
            if ok:
                self.text = text
                self.update()
        finally:
            # Reset editing flag
            if canvas and hasattr(canvas, '_editing_text'):
                canvas._editing_text = False

    def _set_font_size(self, size: int):
        """Set the note font size and redraw."""
        self.font_size = size
        self.update()

    def _pick_custom_color(self):
        """Open a color picker dialog and set the note color."""
        # Start from current color
        if self.color_name.startswith('#'):
            initial = QColor(self.color_name)
        else:
            initial = self.COLORS.get(self.color_name, self.COLORS['yellow'])

        color = QColorDialog.getColor(initial, None, "Choose Note Color")
        if color.isValid():
            self.color_name = color.name()  # Store as hex string e.g. '#ff8800'
            self.update()

    def contextMenuEvent(self, event: QGraphicsSceneMouseEvent):
        """Show context menu."""
        menu = QMenu()

        edit_action = menu.addAction("Edit Text...")
        edit_action.triggered.connect(lambda: self.mouseDoubleClickEvent(event))

        # Color submenu with checkmarks and custom color option
        color_menu = menu.addMenu("Color")
        for color_name in self.COLORS.keys():
            action = color_menu.addAction(color_name.capitalize())
            action.setCheckable(True)
            action.setChecked(self.color_name == color_name)
            action.triggered.connect(lambda checked, c=color_name: self._set_color(c))
        color_menu.addSeparator()
        custom_color_action = color_menu.addAction("Custom Color...")
        custom_color_action.triggered.connect(self._pick_custom_color)

        # Text Size submenu with checkmarks
        size_menu = menu.addMenu("Text Size")
        for label, size in self.FONT_SIZES.items():
            action = size_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.font_size == size)
            action.triggered.connect(lambda checked, s=size: self._set_font_size(s))

        menu.addSeparator()

        delete_action = menu.addAction("Delete Note")
        delete_action.triggered.connect(self._remove)

        menu.exec_(event.screenPos())

    def _set_color(self, color_name: str):
        """Set the note color."""
        self.color_name = color_name
        self.update()

    def _remove(self):
        """Remove from scene."""
        scene = self.scene()
        if scene:
            scene.removeItem(self)


class GroupRegion(QGraphicsRectItem):
    """
    A colored region for grouping images.

    Features:
    - Semi-transparent background
    - Collapsible
    - Named with description
    """

    MIN_SIZE = 100
    HEADER_HEIGHT = 25

    def __init__(self, x: float, y: float, width: float, height: float,
                 name: str = 'Group', color: str = '#ff6b6b',
                 parent: QGraphicsItem = None):
        super().__init__(0, 0, width, height, parent)

        self.name = name
        self.color_hex = color
        self._collapsed = False
        self._expanded_height = height

        # Setup
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(-10)  # Draw behind everything

        self.setPos(x, y)
        self._update_appearance()

    def itemChange(self, change, value):
        """Handle item changes for snapping."""
        if change == QGraphicsItem.ItemPositionChange:
            new_pos = value
            scene = self.scene()
            if scene and scene.views():
                view = scene.views()[0]
                if hasattr(view, 'snap_position_to_grid'):
                    new_pos = view.snap_position_to_grid(new_pos)
                if hasattr(view, 'snap_to_neighbor_items'):
                    new_pos = view.snap_to_neighbor_items(self, new_pos)
            return new_pos
        return super().itemChange(change, value)

    def _update_appearance(self):
        """Update brush and pen based on color."""
        color = QColor(self.color_hex)
        color.setAlpha(50)  # 20% opacity
        self.setBrush(QBrush(color))

        border_color = QColor(self.color_hex)
        border_color.setAlpha(150)
        self.setPen(QPen(border_color, 2, Qt.DashLine))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        # Draw the rectangle
        super().paint(painter, option, widget)

        # Draw header with name
        rect = self.rect()
        header_rect = QRectF(rect.x(), rect.y(), rect.width(), self.HEADER_HEIGHT)

        header_color = QColor(self.color_hex)
        header_color.setAlpha(100)
        painter.fillRect(header_rect, header_color)

        # Collapse indicator
        indicator = "▼" if not self._collapsed else "▶"

        # Draw name
        painter.setPen(QColor(255, 255, 255))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            header_rect.adjusted(10, 0, -10, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            f"{indicator} {self.name}"
        )

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        """Toggle collapse or edit name."""
        # Check if click is in header
        if event.pos().y() < self.HEADER_HEIGHT:
            self._toggle_collapse()
        else:
            # Edit name
            text, ok = QInputDialog.getText(
                None, "Group Name",
                "Enter group name:",
                text=self.name
            )
            if ok:
                self.name = text
                self.update()

    def _toggle_collapse(self):
        """Toggle collapsed state."""
        rect = self.rect()
        if self._collapsed:
            # Expand
            self.setRect(rect.x(), rect.y(), rect.width(), self._expanded_height)
            self._collapsed = False
        else:
            # Collapse
            self._expanded_height = rect.height()
            self.setRect(rect.x(), rect.y(), rect.width(), self.HEADER_HEIGHT)
            self._collapsed = True
        self.update()

    def contextMenuEvent(self, event: QGraphicsSceneMouseEvent):
        """Show context menu."""
        menu = QMenu()

        rename_action = menu.addAction("Rename Group...")
        rename_action.triggered.connect(lambda: self._rename())

        collapse_action = menu.addAction("Expand" if self._collapsed else "Collapse")
        collapse_action.triggered.connect(self._toggle_collapse)

        menu.addSeparator()

        delete_action = menu.addAction("Delete Group")
        delete_action.triggered.connect(self._remove)

        menu.exec_(event.screenPos())

    def _rename(self):
        text, ok = QInputDialog.getText(
            None, "Group Name",
            "Enter group name:",
            text=self.name
        )
        if ok:
            self.name = text
            self.update()

    def _remove(self):
        scene = self.scene()
        if scene:
            scene.removeItem(self)


class VideoNode(QGraphicsItem):
    """
    A draggable, resizable video node for the canvas.

    Shows a thumbnail (first frame) by default with play icon and duration badge.
    Click activates inline playback with controls. Only one video plays at a time.

    Features:
    - Async thumbnail extraction via FFmpeg
    - Inline playback with VideoSinkWidget + VideoControlBar
    - Single-active-player policy (canvas deactivates others)
    - Resizable via corner handles
    - Gallery integration (border colors from groups/likes)
    - Like badge
    """

    # Class-level constants
    MIN_SIZE = 100
    DEFAULT_WIDTH = 320
    DEFAULT_HEIGHT = 180
    HANDLE_SIZE = 10
    BADGE_SIZE = 20
    BORDER_WIDTH = 3

    def __init__(self, video_path: str, x: float = 0, y: float = 0,
                 width: float = None, height: float = None,
                 parent: QGraphicsItem = None,
                 content_hash: str = None,
                 thumbnail_pixmap: Optional[QPixmap] = None):
        """
        Create a video node.

        Args:
            video_path: Path to the video file
            x, y: Position on canvas
            width, height: Size (None = use defaults)
            parent: Parent graphics item
            content_hash: SHA-256 content hash for file identification
            thumbnail_pixmap: Optional pre-loaded thumbnail pixmap
        """
        super().__init__(parent)

        self.video_path = video_path
        self.filename = os.path.basename(video_path)
        self.content_hash = content_hash
        self._width = width or self.DEFAULT_WIDTH
        self._height = height or self.DEFAULT_HEIGHT
        self._liked = False
        self._missing = not os.path.exists(video_path)

        # Thumbnail state
        self._thumbnail_pixmap: Optional[QPixmap] = thumbnail_pixmap
        self._thumbnail_loading = False
        self._duration_seconds: Optional[float] = None
        self._duration_text: str = ""

        # Inline playback state
        self._is_active = False
        self._player_proxy: Optional['QGraphicsProxyWidget'] = None
        self._media_player = None
        self._audio_output = None

        # Resize state
        self._resize_handle = ResizeHandle.NONE
        self._resize_start_rect: Optional[QRectF] = None
        self._resize_start_pos: Optional[QPointF] = None
        self._resize_start_size: Optional[Tuple[float, float]] = None

        # Gallery integration
        self._show_gallery_border = True
        self._border_color: Optional[QColor] = None
        self._group_ids: List[str] = []

        # Setup item flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        # Position
        self.setPos(x, y)

        # Start async thumbnail load if not provided
        if not self._thumbnail_pixmap and not self._missing:
            self._load_thumbnail_async()

    # -------------------------------------------------------------------------
    # Thumbnail Loading
    # -------------------------------------------------------------------------

    def _load_thumbnail_async(self):
        """Load thumbnail and duration in a worker thread."""
        if self._thumbnail_loading:
            return
        self._thumbnail_loading = True

        from PySide6.QtCore import QThreadPool

        def _worker():
            from ui_components import Worker
            self._thumb_worker = Worker(self._extract_thumbnail_and_duration, self.video_path)
            self._thumb_worker.signals.result.connect(self._on_thumbnail_loaded)
            self._thumb_worker.signals.error.connect(self._on_thumbnail_error)
            QThreadPool.globalInstance().start(self._thumb_worker)

        # Defer to avoid importing during __init__ in wrong thread context
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, _worker)

    @staticmethod
    def _extract_thumbnail_and_duration(video_path: str):
        """
        Extract first frame and duration from video (runs in worker thread).

        Returns:
            tuple: (QImage, duration_seconds: float)
        """
        import subprocess
        import tempfile
        from core.config import FFMPEG_PATH
        from core.utils import get_media_duration

        if not FFMPEG_PATH:
            return None

        # Extract duration
        duration = get_media_duration(video_path)

        # Extract first frame
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = [
                FFMPEG_PATH, '-i', video_path,
                '-vframes', '1', '-y', tmp_path
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.run(cmd, capture_output=True, timeout=10,
                           creationflags=creationflags)
            image = QImage(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        if image.isNull():
            return None

        return (image, duration)

    def _on_thumbnail_loaded(self, result):
        """Handle thumbnail extraction result (main thread)."""
        self._thumbnail_loading = False
        if result is None:
            return

        qimage, duration = result
        self._thumbnail_pixmap = QPixmap.fromImage(qimage)
        self._duration_seconds = duration

        if duration is not None:
            from core.utils import format_duration
            self._duration_text = format_duration(duration)
        else:
            self._duration_text = ""

        self.update()

    def _on_thumbnail_error(self, error):
        """Handle thumbnail extraction error."""
        self._thumbnail_loading = False
        logger.warning(f"Video thumbnail extraction failed for {self.filename}: {error}")

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        margin = 300
        return QRectF(-margin, -margin,
                      self._width + 2 * margin,
                      self._height + 2 * margin)

    def shape(self) -> QPainterPath:
        """Return the content rect as shape (used for clipping children)."""
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self._width, self._height))
        return path

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        """Paint the video node."""
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = QRectF(0, 0, self._width, self._height)

        if self._missing:
            self._paint_missing(painter, rect)
        elif self._is_active:
            # When active, the proxy widget handles video rendering.
            # Paint a dark background behind it for clean edges.
            painter.fillRect(rect, QColor(0, 0, 0))
        elif self._thumbnail_pixmap and not self._thumbnail_pixmap.isNull():
            self._paint_thumbnail(painter, rect)
        else:
            self._paint_placeholder(painter, rect)

        # Gallery border
        if self._show_gallery_border and self._border_color:
            border_pen = QPen(self._border_color, self.BORDER_WIDTH)
            border_pen.setCosmetic(True)
            painter.setPen(border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # Selection highlight
        if self.isSelected():
            select_pen = QPen(QColor(74, 158, 255), 2)
            select_pen.setCosmetic(True)
            painter.setPen(select_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))
            self._draw_resize_handles(painter)

        # Like badge
        if self._liked:
            self._draw_like_badge(painter)

    def _paint_missing(self, painter: QPainter, rect: QRectF):
        """Paint placeholder for missing video file."""
        painter.fillRect(rect, QColor(60, 60, 60))
        painter.setPen(QPen(QColor(100, 100, 100), 2, Qt.DashLine))
        painter.drawRect(rect)
        painter.setPen(QColor(150, 150, 150))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, "Missing Video")

    def _paint_thumbnail(self, painter: QPainter, rect: QRectF):
        """Paint video thumbnail with play icon and duration badge."""
        # Draw thumbnail scaled to fit
        pixmap = self._thumbnail_pixmap
        img_aspect = pixmap.width() / max(1, pixmap.height())
        rect_aspect = self._width / max(1, self._height)

        if img_aspect > rect_aspect:
            draw_width = self._width
            draw_height = self._width / img_aspect
        else:
            draw_height = self._height
            draw_width = self._height * img_aspect

        draw_rect = QRectF(
            (self._width - draw_width) / 2,
            (self._height - draw_height) / 2,
            draw_width, draw_height
        )
        painter.drawPixmap(draw_rect, pixmap, QRectF(pixmap.rect()))

        # Dark overlay for contrast
        overlay = QColor(0, 0, 0, 60)
        painter.fillRect(draw_rect, overlay)

        # Play icon (centered triangle)
        self._draw_play_icon(painter, rect)

        # Duration badge (bottom-right)
        if self._duration_text:
            self._draw_duration_badge(painter, rect)

    def _paint_placeholder(self, painter: QPainter, rect: QRectF):
        """Paint loading placeholder."""
        painter.fillRect(rect, QColor(40, 40, 40))

        # Draw play icon even on placeholder
        self._draw_play_icon(painter, rect)

        # Loading text
        if self._thumbnail_loading:
            painter.setPen(QColor(120, 120, 120))
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter, "Loading...")

    def _draw_play_icon(self, painter: QPainter, rect: QRectF):
        """Draw a centered play triangle icon (screen-space size)."""
        icon_size = self._get_screen_space_size(40)
        center = rect.center()

        # Semi-transparent circle background
        circle_rect = QRectF(
            center.x() - icon_size / 2,
            center.y() - icon_size / 2,
            icon_size, icon_size
        )
        painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(circle_rect)

        # Triangle
        tri_size = icon_size * 0.4
        # Offset slightly right to visually center the triangle
        tri_x = center.x() - tri_size * 0.35
        tri_y = center.y() - tri_size * 0.5

        triangle = QPainterPath()
        triangle.moveTo(tri_x, tri_y)
        triangle.lineTo(tri_x, tri_y + tri_size)
        triangle.lineTo(tri_x + tri_size * 0.85, tri_y + tri_size * 0.5)
        triangle.closeSubpath()

        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(Qt.NoPen)
        painter.drawPath(triangle)

    def _draw_duration_badge(self, painter: QPainter, rect: QRectF):
        """Draw duration text badge in bottom-right corner."""
        font = QFont()
        font_size = self._get_screen_space_size(9)
        font.setPointSizeF(max(6, font_size))
        font.setBold(True)
        painter.setFont(font)

        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(self._duration_text)
        padding = self._get_screen_space_size(4)
        margin = self._get_screen_space_size(6)

        badge_width = text_rect.width() + padding * 2
        badge_height = text_rect.height() + padding

        badge_rect = QRectF(
            self._width - badge_width - margin,
            self._height - badge_height - margin,
            badge_width, badge_height
        )

        # Dark background
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(Qt.NoPen)
        badge_radius = self._get_screen_space_size(3)
        painter.drawRoundedRect(badge_rect, badge_radius, badge_radius)

        # White text
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(badge_rect, Qt.AlignCenter, self._duration_text)

    def _get_screen_space_size(self, size: float) -> float:
        """Convert a screen-space size to scene-space based on current zoom."""
        scene = self.scene()
        if scene and scene.views():
            view = scene.views()[0]
            zoom = view.transform().m11()
            if zoom > 0:
                return size / zoom
        return size

    def _draw_resize_handles(self, painter: QPainter):
        """Draw resize handles at corners (screen-space size)."""
        handle_color = QColor(74, 158, 255)
        painter.setBrush(QBrush(handle_color))
        painter.setPen(Qt.NoPen)

        hs = self._get_screen_space_size(self.HANDLE_SIZE)

        handles = [
            QRectF(-hs/2, -hs/2, hs, hs),
            QRectF(self._width - hs/2, -hs/2, hs, hs),
            QRectF(-hs/2, self._height - hs/2, hs, hs),
            QRectF(self._width - hs/2, self._height - hs/2, hs, hs),
        ]

        for handle_rect in handles:
            painter.drawRect(handle_rect)

    def _draw_like_badge(self, painter: QPainter):
        """Draw the like heart badge in corner (screen-space size)."""
        badge_size = self._get_screen_space_size(self.BADGE_SIZE)
        margin = self._get_screen_space_size(5)

        badge_rect = QRectF(
            self._width - badge_size - margin,
            margin,
            badge_size, badge_size
        )

        painter.setBrush(QBrush(QColor(239, 68, 68)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(badge_rect)

        painter.setPen(QColor(255, 255, 255))
        font = QFont()
        font_size = self._get_screen_space_size(12)
        font.setPointSizeF(max(6, font_size))
        painter.setFont(font)
        painter.drawText(badge_rect, Qt.AlignCenter, "\u2665")

    # -------------------------------------------------------------------------
    # Inline Playback
    # -------------------------------------------------------------------------

    def activate_player(self):
        """Switch from thumbnail to inline video player."""
        if self._is_active or self._missing:
            return

        # Deactivate other video nodes first
        scene = self.scene()
        if scene and scene.views():
            canvas = scene.views()[0]
            if hasattr(canvas, 'deactivate_all_videos'):
                canvas.deactivate_all_videos(except_node=self)

        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl

            # Lazy import video components
            from image_viewers import VideoSinkWidget, VideoControlBar

            self._media_player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._media_player.setAudioOutput(self._audio_output)

            # Build container widget — set fixed size BEFORE embedding in proxy
            container = QWidget()
            container.setStyleSheet("background-color: #000000;")
            container.setFixedSize(int(self._width), int(self._height))
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            video_sink = VideoSinkWidget()
            control_bar = VideoControlBar(self._media_player)
            layout.addWidget(video_sink, 1)
            layout.addWidget(control_bar, 0)

            self._media_player.setVideoSink(video_sink.videoSink)

            # Embed via proxy widget, clip to node bounds
            self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)
            self._player_proxy = QGraphicsProxyWidget(self)
            self._player_proxy.setWidget(container)
            self._player_proxy.setPos(0, 0)

            # Start playback
            self._media_player.setSource(QUrl.fromLocalFile(self.video_path))
            self._media_player.play()

            self._is_active = True
            self.update()
            logger.debug(f"Activated video player for {self.filename}")

        except Exception as e:
            logger.error(f"Failed to activate video player for {self.filename}: {e}")
            self._cleanup_player()

    def deactivate_player(self):
        """Switch from inline player back to thumbnail."""
        if not self._is_active:
            return

        self._cleanup_player()
        self._is_active = False
        # Re-enable drawing outside bounds (handles, badges)
        self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, False)
        self.update()
        logger.debug(f"Deactivated video player for {self.filename}")

    def _cleanup_player(self):
        """Clean up all player resources."""
        if self._media_player:
            self._media_player.stop()
            from PySide6.QtCore import QUrl
            self._media_player.setSource(QUrl())
            self._media_player.deleteLater()
            self._media_player = None

        if self._audio_output:
            self._audio_output.deleteLater()
            self._audio_output = None

        if self._player_proxy:
            widget = self._player_proxy.widget()
            if widget:
                widget.deleteLater()
            self._player_proxy.deleteLater()
            self._player_proxy = None

    # -------------------------------------------------------------------------
    # Interaction
    # -------------------------------------------------------------------------

    def _get_handle_at(self, pos: QPointF) -> ResizeHandle:
        """Get the resize handle at the given position."""
        if not self.isSelected():
            return ResizeHandle.NONE

        hs = self._get_screen_space_size(self.HANDLE_SIZE)

        if QRectF(-hs/2, -hs/2, hs, hs).contains(pos):
            return ResizeHandle.TOP_LEFT
        if QRectF(self._width - hs/2, -hs/2, hs, hs).contains(pos):
            return ResizeHandle.TOP_RIGHT
        if QRectF(-hs/2, self._height - hs/2, hs, hs).contains(pos):
            return ResizeHandle.BOTTOM_LEFT
        if QRectF(self._width - hs/2, self._height - hs/2, hs, hs).contains(pos):
            return ResizeHandle.BOTTOM_RIGHT

        return ResizeHandle.NONE

    def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent):
        """Update cursor based on position."""
        handle = self._get_handle_at(event.pos())
        if handle in (ResizeHandle.TOP_LEFT, ResizeHandle.BOTTOM_RIGHT):
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in (ResizeHandle.TOP_RIGHT, ResizeHandle.BOTTOM_LEFT):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.PointingHandCursor if not self._is_active else Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle mouse press for resize or activation."""
        if event.button() == Qt.LeftButton:
            # Check resize first
            self._resize_handle = self._get_handle_at(event.pos())
            if self._resize_handle != ResizeHandle.NONE:
                self._resize_start_rect = QRectF(0, 0, self._width, self._height)
                self._resize_start_pos = event.pos()
                self._resize_start_size = (self._width, self._height)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle mouse move for resize."""
        if self._resize_handle != ResizeHandle.NONE:
            self._do_resize(event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle mouse release after resize."""
        if self._resize_handle != ResizeHandle.NONE:
            if self._resize_start_size is not None:
                old_size = self._resize_start_size
                new_size = (self._width, self._height)
                if old_size != new_size:
                    self._push_resize_undo_command(old_size, new_size)
                    # Update proxy widget size if active
                    if self._is_active and self._player_proxy:
                        widget = self._player_proxy.widget()
                        if widget:
                            widget.setFixedSize(int(self._width), int(self._height))

            self._resize_handle = ResizeHandle.NONE
            self._resize_start_rect = None
            self._resize_start_pos = None
            self._resize_start_size = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        """Toggle inline playback on double-click."""
        if event.button() == Qt.LeftButton:
            if self._is_active:
                self.deactivate_player()
            else:
                self.activate_player()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _do_resize(self, pos: QPointF):
        """Perform the resize operation."""
        if not self._resize_start_rect or not self._resize_start_pos:
            return

        delta = pos - self._resize_start_pos
        old_rect = self._resize_start_rect

        new_width = self._width
        new_height = self._height
        new_x = self.x()
        new_y = self.y()

        if self._resize_handle == ResizeHandle.BOTTOM_RIGHT:
            new_width = max(self.MIN_SIZE, old_rect.width() + delta.x())
            new_height = max(self.MIN_SIZE, old_rect.height() + delta.y())
        elif self._resize_handle == ResizeHandle.TOP_LEFT:
            new_width = max(self.MIN_SIZE, old_rect.width() - delta.x())
            new_height = max(self.MIN_SIZE, old_rect.height() - delta.y())
            if new_width > self.MIN_SIZE:
                new_x = self.x() + delta.x()
            if new_height > self.MIN_SIZE:
                new_y = self.y() + delta.y()
        elif self._resize_handle == ResizeHandle.TOP_RIGHT:
            new_width = max(self.MIN_SIZE, old_rect.width() + delta.x())
            new_height = max(self.MIN_SIZE, old_rect.height() - delta.y())
            if new_height > self.MIN_SIZE:
                new_y = self.y() + delta.y()
        elif self._resize_handle == ResizeHandle.BOTTOM_LEFT:
            new_width = max(self.MIN_SIZE, old_rect.width() - delta.x())
            new_height = max(self.MIN_SIZE, old_rect.height() + delta.y())
            if new_width > self.MIN_SIZE:
                new_x = self.x() + delta.x()

        self.prepareGeometryChange()
        self._width = max(self.MIN_SIZE, new_width)
        self._height = max(self.MIN_SIZE, new_height)
        self.setPos(new_x, new_y)
        self.update()

    def _push_resize_undo_command(self, old_size: Tuple[float, float],
                                   new_size: Tuple[float, float]):
        """Push a resize command to the undo stack."""
        scene = self.scene()
        if not scene or not scene.views():
            return
        view = scene.views()[0]
        if not hasattr(view, '_undo_stack') or not view._undo_stack:
            return

        from .canvas_undo import ResizeItemCommand
        cmd = ResizeItemCommand(view, self.filename, old_size, new_size)
        view._undo_stack._undo_stack.append(cmd)
        view._undo_stack._redo_stack.clear()
        view._undo_stack._emit_changes()

    # -------------------------------------------------------------------------
    # Size & State
    # -------------------------------------------------------------------------

    def get_size(self) -> Tuple[float, float]:
        return (self._width, self._height)

    def set_size(self, width: float, height: float):
        self.prepareGeometryChange()
        self._width = max(self.MIN_SIZE, width)
        self._height = max(self.MIN_SIZE, height)
        if self._is_active and self._player_proxy:
            widget = self._player_proxy.widget()
            if widget:
                widget.setFixedSize(int(self._width), int(self._height))
        self.update()

    def set_liked(self, liked: bool):
        if self._liked != liked:
            self._liked = liked
            self.update()

    def is_liked(self) -> bool:
        return self._liked

    # -------------------------------------------------------------------------
    # Gallery Integration
    # -------------------------------------------------------------------------

    def set_border_color(self, color: Optional[QColor]):
        self._border_color = color
        self.update()

    def set_show_gallery_border(self, show: bool):
        self._show_gallery_border = show
        self.update()

    def set_group_ids(self, group_ids: List[str]):
        self._group_ids = group_ids

    def get_group_ids(self) -> List[str]:
        return self._group_ids

    def sync_from_gallery(self, favorites_manager):
        """Sync this node's state from the gallery FavoritesManager."""
        if not favorites_manager:
            return

        path = self.video_path
        content_hash = self.content_hash

        self._liked = favorites_manager.is_liked(path, content_hash=content_hash)
        self._group_ids = list(favorites_manager.get_item_groups(path, content_hash=content_hash))
        self._border_color = self._get_gallery_border_color(favorites_manager)
        self.update()

    def _get_gallery_border_color(self, favorites_manager) -> Optional[QColor]:
        """Get the border color based on group membership or like status."""
        path = self.video_path
        content_hash = self.content_hash

        groups = favorites_manager.get_item_groups(path, content_hash=content_hash)
        if groups:
            first_group_id = next(iter(groups))
            group_def = favorites_manager.get_group(first_group_id)
            if group_def:
                return QColor(group_def.color)

        if favorites_manager.is_liked(path, content_hash=content_hash):
            return QColor(239, 68, 68)

        return None

    def _get_favorites_manager(self):
        """Get the FavoritesManager from the view."""
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if view and hasattr(view, '_get_favorites_manager'):
            return view._get_favorites_manager()
        return None

    # -------------------------------------------------------------------------
    # Snapping
    # -------------------------------------------------------------------------

    def itemChange(self, change, value):
        """Handle item changes for snapping and cleanup."""
        if change == QGraphicsItem.ItemPositionChange:
            new_pos = value
            scene = self.scene()
            if scene and scene.views():
                view = scene.views()[0]
                if hasattr(view, 'snap_position_to_grid'):
                    new_pos = view.snap_position_to_grid(new_pos)
                if hasattr(view, 'snap_to_neighbor_items'):
                    new_pos = view.snap_to_neighbor_items(self, new_pos)
            return new_pos

        if change == QGraphicsItem.ItemPositionHasChanged:
            # Update connected lines
            scene = self.scene()
            if scene:
                for item in scene.items():
                    if isinstance(item, ConnectionLine):
                        if item.source_node == self or item.target_node == self:
                            item.update_path()

        return super().itemChange(change, value)

    # -------------------------------------------------------------------------
    # Context Menu
    # -------------------------------------------------------------------------

    def contextMenuEvent(self, event: QGraphicsSceneMouseEvent):
        """Show context menu."""
        menu = QMenu()

        # Play/Stop action
        if self._is_active:
            stop_action = menu.addAction("\u25A0 Stop Playback")
            stop_action.triggered.connect(self.deactivate_player)
        else:
            play_action = menu.addAction("\u25B6 Play Video")
            play_action.triggered.connect(self.activate_player)

        menu.addSeparator()

        # Like action
        like_action = menu.addAction("\u2665 Unlike" if self._liked else "\u2661 Like")
        like_action.triggered.connect(self._toggle_like)

        # Groups submenu
        groups_menu = menu.addMenu("Add to Group")
        self._populate_groups_menu(groups_menu)

        menu.addSeparator()

        # Gallery actions
        show_in_gallery = menu.addAction("Show in Gallery")
        show_in_gallery.triggered.connect(self._show_in_gallery)

        open_folder = menu.addAction("Open Containing Folder")
        open_folder.triggered.connect(self._open_folder)

        menu.addSeparator()

        # Display options
        border_action = menu.addAction(
            "Hide Border Colors" if self._show_gallery_border else "Show Border Colors")
        border_action.triggered.connect(
            lambda: self.set_show_gallery_border(not self._show_gallery_border))

        menu.addSeparator()

        delete_action = menu.addAction("Remove from Canvas")
        delete_action.triggered.connect(self._remove_from_canvas)

        menu.exec_(event.screenPos())

    def _toggle_like(self):
        """Toggle like status and sync with gallery."""
        new_liked = not self._liked
        self.set_liked(new_liked)
        favorites_manager = self._get_favorites_manager()
        if favorites_manager:
            if new_liked:
                favorites_manager.like_item(self.video_path)
            else:
                favorites_manager.unlike_item(self.video_path)

    def _populate_groups_menu(self, menu: QMenu):
        """Populate the groups submenu."""
        favorites_manager = self._get_favorites_manager()
        if not favorites_manager:
            no_groups = menu.addAction("(No groups available)")
            no_groups.setEnabled(False)
            return

        groups = favorites_manager.get_groups()
        if not groups:
            no_groups = menu.addAction("(No groups created)")
            no_groups.setEnabled(False)
            return

        current_groups = favorites_manager.get_item_groups(self.video_path)
        for group in groups:
            is_member = group.group_id in current_groups
            action_text = f"{'✓ ' if is_member else '   '}{group.name}"
            action = menu.addAction(action_text)
            action.triggered.connect(
                lambda checked, gid=group.group_id: self._toggle_group(gid))

    def _toggle_group(self, group_id: str):
        """Toggle membership in a group."""
        favorites_manager = self._get_favorites_manager()
        if not favorites_manager:
            return
        current_groups = favorites_manager.get_item_groups(self.video_path)
        if group_id in current_groups:
            favorites_manager.remove_from_group(self.video_path, group_id)
        else:
            favorites_manager.add_to_group(self.video_path, group_id)
        self.sync_from_gallery(favorites_manager)

    def _show_in_gallery(self):
        """Show this video in the gallery tab."""
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if view and hasattr(view, '_show_in_gallery'):
            view._show_in_gallery(self.video_path)

    def _open_folder(self):
        """Open the containing folder in file explorer."""
        import subprocess
        folder = os.path.dirname(self.video_path)
        if os.path.exists(folder):
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.Popen(
                f'explorer /select,"{self.video_path}"',
                creationflags=creationflags)

    def _remove_from_canvas(self):
        """Remove this node from the canvas."""
        if self._is_active:
            self.deactivate_player()
        scene = self.scene()
        if scene:
            # Remove connected lines
            for item in list(scene.items()):
                if isinstance(item, ConnectionLine):
                    if item.source_node == self or item.target_node == self:
                        scene.removeItem(item)
            scene.removeItem(self)
