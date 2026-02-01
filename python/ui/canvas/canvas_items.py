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
    QStyleOptionGraphicsItem, QWidget, QMenu, QInputDialog
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
                 parent: QGraphicsItem = None):
        """
        Create an image node.

        Args:
            image_path: Path to the image file
            x, y: Position on canvas
            width, height: Size (None = use original image resolution)
            parent: Parent graphics item
        """
        super().__init__(parent)

        self.image_path = image_path
        self.filename = os.path.basename(image_path)
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

        # LOD cache: {scale_factor: QPixmap}
        self._lod_cache: Dict[float, QPixmap] = {}

        # Non-destructive transformation state
        self._crop_rect: Optional[QRectF] = None  # Crop rectangle in original image coords
        self._flip_h: bool = False  # Horizontal flip
        self._flip_v: bool = False  # Vertical flip
        self._rotation: float = 0.0  # Rotation in degrees
        self._opacity: float = 1.0  # 0.0 to 1.0
        self._grayscale: bool = False  # Grayscale toggle

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

        # Load image
        self._load_image()

    def _load_image(self):
        """Load the image from disk."""
        if os.path.exists(self.image_path):
            self._pixmap = QPixmap(self.image_path)
            if self._pixmap.isNull():
                self._missing = True
                self._pixmap = None
            else:
                self._missing = False
                # Clear LOD cache when loading new image
                self._lod_cache.clear()
                # Use original image dimensions if no size was specified
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
        else:
            self._missing = True
            self._pixmap = None

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
        logger.debug(f"Created LOD cache for {self.filename}: {scale_factor:.0%} ({lod_width}x{lod_height})")

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

                # Calculate destination rectangle
                # Center the image if aspect ratio differs
                img_aspect = source_rect.width() / max(1, source_rect.height())
                rect_aspect = self._width / max(1, self._height)

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
            self._resize_handle = ResizeHandle.NONE
            self._resize_start_rect = None
            self._resize_start_pos = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

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

        # Apply changes
        self.prepareGeometryChange()
        self._width = new_width
        self._height = new_height
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

        # Sync like status
        self._liked = favorites_manager.is_liked(path)

        # Sync group membership
        self._group_ids = list(favorites_manager.get_item_groups(path))

        # Get border color based on groups or like status
        self._border_color = self._get_gallery_border_color(favorites_manager)

        self.update()

    def _get_gallery_border_color(self, favorites_manager) -> Optional[QColor]:
        """Get the border color based on group membership or like status."""
        path = self.image_path

        # Priority: group color > liked color
        groups = favorites_manager.get_item_groups(path)
        if groups:
            # Use the first group's color
            first_group_id = next(iter(groups))
            group_def = favorites_manager.get_group(first_group_id)
            if group_def:
                return QColor(group_def.color)

        # Fallback to like color
        if favorites_manager.is_liked(path):
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
            subprocess.Popen(f'explorer /select,"{self.image_path}"')

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
                 parent: QGraphicsItem = None):
        super().__init__(parent)

        self.source_node = source_node
        self.target_node = target_node
        self.connection_type = connection_type
        self.label = label

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
        """Remove this connection from the scene."""
        scene = self.scene()
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

    MIN_SIZE = 80
    DEFAULT_WIDTH = 150
    DEFAULT_HEIGHT = 100
    HANDLE_SIZE = 8

    def __init__(self, x: float, y: float, text: str = '',
                 color: str = 'yellow', parent: QGraphicsItem = None):
        super().__init__(parent)

        self.text = text
        self.color_name = color
        self._width = self.DEFAULT_WIDTH
        self._height = self.DEFAULT_HEIGHT
        self._resize_handle = ResizeHandle.NONE
        self._resize_start_rect: Optional[QRectF] = None
        self._resize_start_pos: Optional[QPointF] = None

        # Setup flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self.setPos(x, y)

    def boundingRect(self) -> QRectF:
        margin = self.HANDLE_SIZE if self.isSelected() else 0
        return QRectF(-margin, -margin,
                      self._width + 2 * margin,
                      self._height + 2 * margin)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(0, 0, self._width, self._height)
        color = self.COLORS.get(self.color_name, self.COLORS['yellow'])

        # Draw note background
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(110), 1))
        painter.drawRoundedRect(rect, 5, 5)

        # Draw text
        text_rect = rect.adjusted(8, 8, -8, -8)
        painter.setPen(QColor(50, 50, 50))
        font = QFont()
        font.setPointSize(10)
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
        text, ok = QInputDialog.getMultiLineText(
            None, "Edit Note",
            "Enter note text:",
            self.text
        )
        if ok:
            self.text = text
            self.update()

    def contextMenuEvent(self, event: QGraphicsSceneMouseEvent):
        """Show context menu."""
        menu = QMenu()

        edit_action = menu.addAction("Edit Text...")
        edit_action.triggered.connect(lambda: self.mouseDoubleClickEvent(event))

        # Color submenu
        color_menu = menu.addMenu("Color")
        for color_name in self.COLORS.keys():
            action = color_menu.addAction(color_name.capitalize())
            action.triggered.connect(lambda checked, c=color_name: self._set_color(c))

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
        self.setAcceptHoverEvents(True)
        self.setZValue(-10)  # Draw behind everything

        self.setPos(x, y)
        self._update_appearance()

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
