"""
Drawing tools for the collaborative canvas.

Contains:
- DrawingPath: Freehand pen strokes with pressure/tilt/rotation support
- DrawingRect: Rectangle shapes
- DrawingEllipse: Ellipse shapes
- DrawingLine: Line/arrow shapes
- DrawingToolbar: Floating toolbar for drawing tools
"""

import logging
from typing import Optional, List, Tuple
from enum import Enum

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QLineF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPainterPath, QFont,
    QTabletEvent, QPainterPathStroker
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem, QWidget, QMenu, QInputDialog,
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSlider,
    QColorDialog, QFrame, QComboBox, QSpinBox, QToolButton
)

logger = logging.getLogger(__name__)


class LineStyle(Enum):
    """Line style options."""
    SOLID = Qt.SolidLine
    DASH = Qt.DashLine
    DOT = Qt.DotLine
    DASH_DOT = Qt.DashDotLine
    DASH_DOT_DOT = Qt.DashDotDotLine


class LineCap(Enum):
    """Line cap options."""
    FLAT = Qt.FlatCap
    SQUARE = Qt.SquareCap
    ROUND = Qt.RoundCap


class DrawingItemBase(QGraphicsItem):
    """Base class for drawing items with common functionality."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Drawing properties
        self._pen_color = QColor(255, 0, 0)  # Default red
        self._pen_width = 3
        self._line_style = Qt.SolidLine
        self._line_cap = Qt.RoundCap
        self._fill_color: Optional[QColor] = None

        # Attachment to image
        self._attached_to: Optional[str] = None  # Image node ID

        # Setup flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

    def set_pen_color(self, color: QColor):
        """Set the pen color."""
        self._pen_color = color
        self.update()

    def get_pen_color(self) -> QColor:
        """Get the pen color."""
        return self._pen_color

    def set_pen_width(self, width: int):
        """Set the pen width."""
        self._pen_width = max(1, width)
        self.update()

    def get_pen_width(self) -> int:
        """Get the pen width."""
        return self._pen_width

    def set_line_style(self, style: Qt.PenStyle):
        """Set the line style."""
        self._line_style = style
        self.update()

    def set_line_cap(self, cap: Qt.PenCapStyle):
        """Set the line cap style."""
        self._line_cap = cap
        self.update()

    def set_fill_color(self, color: Optional[QColor]):
        """Set the fill color (None for no fill)."""
        self._fill_color = color
        self.update()

    def attach_to_image(self, image_id: Optional[str]):
        """Attach this drawing to an image node."""
        self._attached_to = image_id

    def get_attached_image(self) -> Optional[str]:
        """Get the ID of the attached image."""
        return self._attached_to

    def _create_pen(self) -> QPen:
        """Create a pen with current settings."""
        pen = QPen(self._pen_color, self._pen_width)
        pen.setStyle(self._line_style)
        pen.setCapStyle(self._line_cap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def _create_brush(self) -> QBrush:
        """Create a brush with current settings."""
        if self._fill_color:
            return QBrush(self._fill_color)
        return QBrush(Qt.NoBrush)

    def get_state(self) -> dict:
        """Get serializable state."""
        # Helper to safely convert Qt enums to int for JSON serialization
        def enum_to_int(val, default=0):
            if isinstance(val, int):
                return val
            if hasattr(val, 'value'):
                return val.value
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        return {
            'pen_color': self._pen_color.name(),
            'pen_width': self._pen_width,
            'line_style': enum_to_int(self._line_style, Qt.SolidLine.value),
            'line_cap': enum_to_int(self._line_cap, Qt.RoundCap.value),
            'fill_color': self._fill_color.name() if self._fill_color else None,
            'attached_to': self._attached_to,
            'x': self.x(),
            'y': self.y(),
        }

    def set_state(self, state: dict):
        """Restore from serialized state."""
        self._pen_color = QColor(state.get('pen_color', '#FF0000'))
        self._pen_width = state.get('pen_width', 3)
        # line_style/line_cap are stored as ints, convert back to Qt enums
        line_style = state.get('line_style', Qt.SolidLine)
        self._line_style = Qt.PenStyle(line_style) if isinstance(line_style, int) else line_style
        line_cap = state.get('line_cap', Qt.RoundCap)
        self._line_cap = Qt.PenCapStyle(line_cap) if isinstance(line_cap, int) else line_cap
        fill = state.get('fill_color')
        self._fill_color = QColor(fill) if fill else None
        self._attached_to = state.get('attached_to')
        self.setPos(state.get('x', 0), state.get('y', 0))


class PenPoint:
    """A point in a pen stroke with pressure data."""

    def __init__(self, pos: QPointF, pressure: float = 1.0,
                 tilt_x: float = 0.0, tilt_y: float = 0.0, rotation: float = 0.0):
        self.pos = pos
        self.pressure = pressure
        self.tilt_x = tilt_x
        self.tilt_y = tilt_y
        self.rotation = rotation


class DrawingPath(DrawingItemBase):
    """
    Freehand pen stroke with pressure sensitivity support.

    Supports pen tablet: pressure (width), tilt, rotation.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Path data
        self._points: List[PenPoint] = []
        self._path = QPainterPath()

        # Pressure settings
        self._use_pressure = True
        self._min_width = 1
        self._max_width = 20

    def add_point(self, pos: QPointF, pressure: float = 1.0,
                  tilt_x: float = 0.0, tilt_y: float = 0.0, rotation: float = 0.0):
        """
        Add a point to the path.

        Args:
            pos: Position in item coordinates
            pressure: Pressure value 0.0 to 1.0
            tilt_x, tilt_y: Tilt values -1.0 to 1.0
            rotation: Rotation in degrees
        """
        point = PenPoint(pos, pressure, tilt_x, tilt_y, rotation)
        self._points.append(point)
        self._rebuild_path()

    def _rebuild_path(self):
        """Rebuild the QPainterPath from points."""
        if len(self._points) < 2:
            self._path = QPainterPath()
            if self._points:
                self._path.moveTo(self._points[0].pos)
            return

        self.prepareGeometryChange()
        self._path = QPainterPath()
        self._path.moveTo(self._points[0].pos)

        # Use quadratic bezier curves for smooth path
        for i in range(1, len(self._points)):
            if i < len(self._points) - 1:
                # Use midpoint for control point
                p0 = self._points[i - 1].pos
                p1 = self._points[i].pos
                p2 = self._points[i + 1].pos
                mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                self._path.quadTo(p1, mid)
            else:
                self._path.lineTo(self._points[i].pos)

        self.update()

    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        if self._path.isEmpty():
            return QRectF()
        margin = self._max_width + 5
        return self._path.boundingRect().adjusted(-margin, -margin, margin, margin)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        """Paint the path with optional pressure-based width."""
        if len(self._points) < 2:
            return

        painter.setRenderHint(QPainter.Antialiasing)

        if self._use_pressure and any(p.pressure != 1.0 for p in self._points):
            # Draw with variable width based on pressure
            self._paint_variable_width(painter)
        else:
            # Draw with constant width
            pen = self._create_pen()
            painter.setPen(pen)
            painter.drawPath(self._path)

        # Selection highlight
        if self.isSelected():
            highlight_pen = QPen(QColor(74, 158, 255, 100), self._pen_width + 4)
            highlight_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(highlight_pen)
            painter.drawPath(self._path)

    def _paint_variable_width(self, painter: QPainter):
        """Paint path with pressure-based variable width."""
        if len(self._points) < 2:
            return

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._pen_color))

        for i in range(len(self._points) - 1):
            p0 = self._points[i]
            p1 = self._points[i + 1]

            # Calculate width based on average pressure
            avg_pressure = (p0.pressure + p1.pressure) / 2
            width = self._min_width + (self._max_width - self._min_width) * avg_pressure

            # Create line segment with width
            line = QLineF(p0.pos, p1.pos)
            stroker = QPainterPathStroker()
            stroker.setWidth(width)
            stroker.setCapStyle(Qt.RoundCap)
            stroker.setJoinStyle(Qt.RoundJoin)

            segment_path = QPainterPath()
            segment_path.moveTo(p0.pos)
            segment_path.lineTo(p1.pos)

            filled_path = stroker.createStroke(segment_path)
            painter.drawPath(filled_path)

    def set_use_pressure(self, use: bool):
        """Enable/disable pressure sensitivity."""
        self._use_pressure = use
        self.update()

    def set_width_range(self, min_width: int, max_width: int):
        """Set the width range for pressure sensitivity."""
        self._min_width = max(1, min_width)
        self._max_width = max(self._min_width, max_width)
        self.update()

    def get_state(self) -> dict:
        """Get serializable state."""
        state = super().get_state()
        state['type'] = 'path'
        state['points'] = [
            {
                'x': p.pos.x(), 'y': p.pos.y(),
                'pressure': p.pressure,
                'tilt_x': p.tilt_x, 'tilt_y': p.tilt_y,
                'rotation': p.rotation
            }
            for p in self._points
        ]
        state['use_pressure'] = self._use_pressure
        state['min_width'] = self._min_width
        state['max_width'] = self._max_width
        return state

    def set_state(self, state: dict):
        """Restore from serialized state."""
        super().set_state(state)
        self._use_pressure = state.get('use_pressure', True)
        self._min_width = state.get('min_width', 1)
        self._max_width = state.get('max_width', 20)

        points_data = state.get('points', [])
        logger.debug(f"DrawingPath.set_state: received {len(points_data)} points, item pos=({state.get('x')}, {state.get('y')})")

        self._points = []
        for p in points_data:
            self._points.append(PenPoint(
                QPointF(p['x'], p['y']),
                p.get('pressure', 1.0),
                p.get('tilt_x', 0.0),
                p.get('tilt_y', 0.0),
                p.get('rotation', 0.0)
            ))

        logger.debug(f"DrawingPath.set_state: created {len(self._points)} PenPoint objects")
        self._rebuild_path()
        logger.debug(f"DrawingPath.set_state: path rebuilt, isEmpty={self._path.isEmpty()}")

    def normalize_to_local(self):
        """Convert from scene coordinates to local coordinates for proper movement.

        After drawing, points are in scene coordinates while item pos is (0,0).
        This method calculates the bounding box, moves the item position to the
        top-left, and translates all points to be relative to that position.
        """
        if not self._points:
            return

        # Calculate bounding box of all points
        min_x = min(p.pos.x() for p in self._points)
        min_y = min(p.pos.y() for p in self._points)

        # Set item position to top-left of bounds
        self.setPos(min_x, min_y)

        # Translate all points to be relative to item position
        for p in self._points:
            p.pos = QPointF(p.pos.x() - min_x, p.pos.y() - min_y)

        # Rebuild path with new local coordinates
        self._rebuild_path()

    def erase_at(self, scene_pos: QPointF, radius: float) -> 'list[DrawingPath] | None':
        """Erase points within radius of scene_pos.

        This method removes points that fall within the eraser radius and
        potentially splits the path into multiple segments.

        Args:
            scene_pos: Position in scene coordinates
            radius: Eraser radius

        Returns:
            - None: No points were erased (path unchanged)
            - Empty list: All points erased (path should be deleted)
            - List of DrawingPath: Path was split into these new paths
        """
        if not self._points:
            return []

        # Convert scene position to local item coordinates
        local_pos = self.mapFromScene(scene_pos)

        # Find which points are within the eraser radius
        points_to_keep = []
        erased_any = False

        for point in self._points:
            dx = point.pos.x() - local_pos.x()
            dy = point.pos.y() - local_pos.y()
            distance = (dx * dx + dy * dy) ** 0.5

            if distance <= radius:
                erased_any = True
                # Mark gap by appending None
                if points_to_keep and points_to_keep[-1] is not None:
                    points_to_keep.append(None)
            else:
                points_to_keep.append(point)

        if not erased_any:
            return None  # No change

        # Remove trailing None
        while points_to_keep and points_to_keep[-1] is None:
            points_to_keep.pop()

        # If all points were erased
        if not points_to_keep or all(p is None for p in points_to_keep):
            return []  # Delete this path

        # Split into segments at None gaps
        segments = []
        current_segment = []

        for point in points_to_keep:
            if point is None:
                if len(current_segment) >= 2:  # Need at least 2 points for a path
                    segments.append(current_segment)
                current_segment = []
            else:
                current_segment.append(point)

        if len(current_segment) >= 2:
            segments.append(current_segment)

        # If no valid segments remain
        if not segments:
            return []  # Delete this path

        # If only one segment and it's the same as original (minus some points)
        if len(segments) == 1:
            # Update this path in place
            self._points = segments[0]
            self._rebuild_path()
            return None  # Path was modified but not split

        # Multiple segments - create new paths for each
        new_paths = []
        item_pos = self.pos()

        for segment_points in segments:
            new_path = DrawingPath()
            new_path.set_pen_color(self._pen_color)
            new_path.set_pen_width(self._pen_width)
            new_path._line_style = self._line_style
            new_path._line_cap = self._line_cap
            new_path._fill_color = self._fill_color
            new_path._use_pressure = self._use_pressure
            new_path._min_width = self._min_width
            new_path._max_width = self._max_width

            # Copy points (they're in local coordinates, need to convert to scene)
            for point in segment_points:
                # Convert local point to scene coordinates
                scene_point_pos = QPointF(point.pos.x() + item_pos.x(),
                                          point.pos.y() + item_pos.y())
                new_path._points.append(PenPoint(
                    scene_point_pos,
                    point.pressure,
                    point.tilt_x,
                    point.tilt_y,
                    point.rotation
                ))

            new_path._rebuild_path()
            new_path.normalize_to_local()

            # Set flags for proper selection/movement
            new_path.setFlag(QGraphicsItem.ItemIsMovable, True)
            new_path.setFlag(QGraphicsItem.ItemIsSelectable, True)

            new_paths.append(new_path)

        return new_paths


class DrawingRect(DrawingItemBase):
    """Rectangle drawing item."""

    def __init__(self, rect: QRectF = None, parent=None):
        super().__init__(parent)
        self._rect = rect or QRectF(0, 0, 100, 100)

    def set_rect(self, rect: QRectF):
        """Set the rectangle."""
        self.prepareGeometryChange()
        self._rect = rect
        self.update()

    def get_rect(self) -> QRectF:
        """Get the rectangle."""
        return self._rect

    def boundingRect(self) -> QRectF:
        margin = self._pen_width + 5
        return self._rect.adjusted(-margin, -margin, margin, margin)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self._create_pen())
        painter.setBrush(self._create_brush())
        painter.drawRect(self._rect)

        if self.isSelected():
            highlight_pen = QPen(QColor(74, 158, 255), 2, Qt.DashLine)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._rect.adjusted(-3, -3, 3, 3))

    def get_state(self) -> dict:
        state = super().get_state()
        state['type'] = 'rect'
        state['rect'] = [self._rect.x(), self._rect.y(),
                         self._rect.width(), self._rect.height()]
        return state

    def set_state(self, state: dict):
        super().set_state(state)
        r = state.get('rect', [0, 0, 100, 100])
        self._rect = QRectF(r[0], r[1], r[2], r[3])

    def normalize_to_local(self):
        """Convert from scene coordinates to local coordinates for proper movement.

        After drawing, rect is in scene coordinates while item pos is (0,0).
        This method sets item position to rect's top-left and adjusts rect to local coords.
        """
        # Set item position to rect's top-left
        self.setPos(self._rect.x(), self._rect.y())

        # Adjust rect to be at (0, 0) relative to item position
        self._rect = QRectF(0, 0, self._rect.width(), self._rect.height())
        self.update()


class DrawingEllipse(DrawingItemBase):
    """Ellipse drawing item."""

    def __init__(self, rect: QRectF = None, parent=None):
        super().__init__(parent)
        self._rect = rect or QRectF(0, 0, 100, 100)

    def set_rect(self, rect: QRectF):
        """Set the bounding rectangle of the ellipse."""
        self.prepareGeometryChange()
        self._rect = rect
        self.update()

    def get_rect(self) -> QRectF:
        """Get the bounding rectangle."""
        return self._rect

    def boundingRect(self) -> QRectF:
        margin = self._pen_width + 5
        return self._rect.adjusted(-margin, -margin, margin, margin)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self._create_pen())
        painter.setBrush(self._create_brush())
        painter.drawEllipse(self._rect)

        if self.isSelected():
            highlight_pen = QPen(QColor(74, 158, 255), 2, Qt.DashLine)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._rect.adjusted(-3, -3, 3, 3))

    def get_state(self) -> dict:
        state = super().get_state()
        state['type'] = 'ellipse'
        state['rect'] = [self._rect.x(), self._rect.y(),
                         self._rect.width(), self._rect.height()]
        return state

    def set_state(self, state: dict):
        super().set_state(state)
        r = state.get('rect', [0, 0, 100, 100])
        self._rect = QRectF(r[0], r[1], r[2], r[3])

    def normalize_to_local(self):
        """Convert from scene coordinates to local coordinates for proper movement.

        After drawing, rect is in scene coordinates while item pos is (0,0).
        This method sets item position to rect's top-left and adjusts rect to local coords.
        """
        # Set item position to rect's top-left
        self.setPos(self._rect.x(), self._rect.y())

        # Adjust rect to be at (0, 0) relative to item position
        self._rect = QRectF(0, 0, self._rect.width(), self._rect.height())
        self.update()


class DrawingLine(DrawingItemBase):
    """Line drawing item with optional arrow head."""

    ARROW_SIZE = 15

    def __init__(self, line: QLineF = None, parent=None):
        super().__init__(parent)
        self._line = line or QLineF(0, 0, 100, 100)
        self._show_arrow = False

    def set_line(self, line: QLineF):
        """Set the line."""
        self.prepareGeometryChange()
        self._line = line
        self.update()

    def get_line(self) -> QLineF:
        """Get the line."""
        return self._line

    def set_arrow(self, show: bool):
        """Show/hide arrow at end."""
        self._show_arrow = show
        self.update()

    def has_arrow(self) -> bool:
        """Check if arrow is shown."""
        return self._show_arrow

    def boundingRect(self) -> QRectF:
        margin = self._pen_width + self.ARROW_SIZE + 5
        return QRectF(
            min(self._line.x1(), self._line.x2()) - margin,
            min(self._line.y1(), self._line.y2()) - margin,
            abs(self._line.dx()) + 2 * margin,
            abs(self._line.dy()) + 2 * margin
        )

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        import math

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self._create_pen())

        # Draw line
        painter.drawLine(self._line)

        # Draw arrow if enabled
        if self._show_arrow:
            self._draw_arrow(painter)

        if self.isSelected():
            highlight_pen = QPen(QColor(74, 158, 255, 100), self._pen_width + 4)
            painter.setPen(highlight_pen)
            painter.drawLine(self._line)

    def _draw_arrow(self, painter: QPainter):
        """Draw arrow head at line end."""
        import math

        # Calculate angle
        angle = math.atan2(self._line.dy(), self._line.dx())
        arrow_angle = math.pi / 6  # 30 degrees

        end = self._line.p2()
        size = self.ARROW_SIZE

        # Arrow points
        p1 = QPointF(
            end.x() - size * math.cos(angle - arrow_angle),
            end.y() - size * math.sin(angle - arrow_angle)
        )
        p2 = QPointF(
            end.x() - size * math.cos(angle + arrow_angle),
            end.y() - size * math.sin(angle + arrow_angle)
        )

        # Draw filled arrow
        arrow_path = QPainterPath()
        arrow_path.moveTo(end)
        arrow_path.lineTo(p1)
        arrow_path.lineTo(p2)
        arrow_path.closeSubpath()

        painter.setBrush(QBrush(self._pen_color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(arrow_path)

    def get_state(self) -> dict:
        state = super().get_state()
        state['type'] = 'line'
        state['line'] = [self._line.x1(), self._line.y1(),
                         self._line.x2(), self._line.y2()]
        state['arrow'] = self._show_arrow
        return state

    def set_state(self, state: dict):
        super().set_state(state)
        l = state.get('line', [0, 0, 100, 100])
        self._line = QLineF(l[0], l[1], l[2], l[3])
        self._show_arrow = state.get('arrow', False)

    def normalize_to_local(self):
        """Convert from scene coordinates to local coordinates for proper movement.

        After drawing, line is in scene coordinates while item pos is (0,0).
        This method sets item position to line's bounding top-left and adjusts line to local coords.
        """
        # Get bounding box of the line
        min_x = min(self._line.x1(), self._line.x2())
        min_y = min(self._line.y1(), self._line.y2())

        # Set item position to bounding box top-left
        self.setPos(min_x, min_y)

        # Adjust line points to be relative to item position
        self._line = QLineF(
            self._line.x1() - min_x, self._line.y1() - min_y,
            self._line.x2() - min_x, self._line.y2() - min_y
        )
        self.update()


class DrawingToolbar(QFrame):
    """
    Floating toolbar for drawing tools.

    Shows when any draw tool is selected. Contains:
    - Tool buttons (pen, rect, ellipse, line, arrow)
    - Color picker with swatches
    - Width slider
    - Line style selector
    """

    # Signals
    tool_changed = Signal(str)  # pen, rect, ellipse, line, arrow
    color_changed = Signal(QColor)
    width_changed = Signal(int)
    style_changed = Signal(int)  # Qt.PenStyle value

    # Default swatches
    DEFAULT_SWATCHES = [
        '#FF0000', '#FF6600', '#FFCC00', '#00FF00',
        '#00FFFF', '#0066FF', '#9900FF', '#FF00FF',
        '#FFFFFF', '#808080', '#000000',
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_tool = 'pen'
        self._current_color = QColor(255, 0, 0)
        self._current_width = 3
        self._swatches = [QColor(c) for c in self.DEFAULT_SWATCHES]

        self._setup_ui()

    def _setup_ui(self):
        """Setup the toolbar UI."""
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 5px;
            }
            QPushButton, QToolButton {
                background-color: #3d3d3d;
                border: 1px solid #4d4d4d;
                border-radius: 3px;
                padding: 5px;
                min-width: 30px;
                min-height: 30px;
            }
            QPushButton:checked, QToolButton:checked {
                background-color: #4a9eff;
                border-color: #4a9eff;
            }
            QPushButton:hover, QToolButton:hover {
                background-color: #4d4d4d;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #3d3d3d;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -4px 0;
                background: #4a9eff;
                border-radius: 7px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Tool buttons
        tool_layout = QHBoxLayout()
        tool_layout.setSpacing(4)

        self._tool_buttons = {}
        tools = [
            ('pen', 'P', 'Pen (P)'),
            ('rect', 'R', 'Rectangle (U)'),
            ('ellipse', 'E', 'Ellipse (O)'),
            ('line', 'L', 'Line (L)'),
            ('arrow', '→', 'Arrow (Shift+L)'),
        ]

        for tool_id, icon, tooltip in tools:
            btn = QPushButton(icon)
            btn.setCheckable(True)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda checked, t=tool_id: self._on_tool_clicked(t))
            self._tool_buttons[tool_id] = btn
            tool_layout.addWidget(btn)

        self._tool_buttons['pen'].setChecked(True)
        layout.addLayout(tool_layout)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("background-color: #4d4d4d;")
        layout.addWidget(sep1)

        # Color button and swatches
        color_layout = QHBoxLayout()
        color_layout.setSpacing(4)

        self._color_button = QPushButton()
        self._color_button.setFixedSize(30, 30)
        self._update_color_button()
        self._color_button.clicked.connect(self._pick_color)
        self._color_button.setToolTip("Pick color")
        color_layout.addWidget(self._color_button)

        # Quick swatches (first 6)
        for i, color in enumerate(self._swatches[:6]):
            swatch = QPushButton()
            swatch.setFixedSize(20, 20)
            swatch.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #4d4d4d;")
            swatch.clicked.connect(lambda checked, c=color: self._set_color(c))
            color_layout.addWidget(swatch)

        layout.addLayout(color_layout)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("background-color: #4d4d4d;")
        layout.addWidget(sep2)

        # Width slider
        width_layout = QHBoxLayout()
        width_layout.setSpacing(4)

        width_label = QLabel("Width:")
        width_label.setStyleSheet("color: #aaa;")
        width_layout.addWidget(width_label)

        self._width_slider = QSlider(Qt.Horizontal)
        self._width_slider.setRange(1, 50)
        self._width_slider.setValue(self._current_width)
        self._width_slider.setFixedWidth(80)
        self._width_slider.valueChanged.connect(self._on_width_changed)
        width_layout.addWidget(self._width_slider)

        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 50)
        self._width_spin.setValue(self._current_width)
        self._width_spin.setFixedWidth(50)
        self._width_spin.valueChanged.connect(self._on_width_spin_changed)
        width_layout.addWidget(self._width_spin)

        layout.addLayout(width_layout)

        # Separator
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet("background-color: #4d4d4d;")
        layout.addWidget(sep3)

        # Line style combo
        style_layout = QHBoxLayout()
        style_layout.setSpacing(4)

        style_label = QLabel("Style:")
        style_label.setStyleSheet("color: #aaa;")
        style_layout.addWidget(style_label)

        self._style_combo = QComboBox()
        self._style_combo.addItem("Solid", Qt.SolidLine)
        self._style_combo.addItem("Dash", Qt.DashLine)
        self._style_combo.addItem("Dot", Qt.DotLine)
        self._style_combo.addItem("Dash-Dot", Qt.DashDotLine)
        self._style_combo.setFixedWidth(80)
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)
        style_layout.addWidget(self._style_combo)

        layout.addLayout(style_layout)

    def _on_tool_clicked(self, tool_id: str):
        """Handle tool button click."""
        self._current_tool = tool_id
        for tid, btn in self._tool_buttons.items():
            btn.setChecked(tid == tool_id)
        self.tool_changed.emit(tool_id)

    def _update_color_button(self):
        """Update the color button appearance."""
        self._color_button.setStyleSheet(
            f"background-color: {self._current_color.name()}; border: 1px solid #4d4d4d;"
        )

    def _pick_color(self):
        """Open color picker dialog."""
        color = QColorDialog.getColor(self._current_color, self, "Pick Color")
        if color.isValid():
            self._set_color(color)

    def _set_color(self, color: QColor):
        """Set the current color."""
        self._current_color = color
        self._update_color_button()
        self.color_changed.emit(color)

    def _on_width_changed(self, value: int):
        """Handle width slider change."""
        self._current_width = value
        self._width_spin.blockSignals(True)
        self._width_spin.setValue(value)
        self._width_spin.blockSignals(False)
        self.width_changed.emit(value)

    def _on_width_spin_changed(self, value: int):
        """Handle width spinbox change."""
        self._current_width = value
        self._width_slider.blockSignals(True)
        self._width_slider.setValue(value)
        self._width_slider.blockSignals(False)
        self.width_changed.emit(value)

    def _on_style_changed(self, index: int):
        """Handle style combo change."""
        style = self._style_combo.itemData(index)
        self.style_changed.emit(style)

    def get_current_tool(self) -> str:
        """Get the current tool."""
        return self._current_tool

    def get_current_color(self) -> QColor:
        """Get the current color."""
        return self._current_color

    def get_current_width(self) -> int:
        """Get the current width."""
        return self._current_width

    def get_current_style(self) -> int:
        """Get the current line style."""
        return self._style_combo.currentData()

    def set_tool(self, tool_id: str):
        """Set the current tool."""
        if tool_id in self._tool_buttons:
            self._on_tool_clicked(tool_id)

    def set_color(self, color: QColor):
        """Set the current color."""
        self._set_color(color)

    def set_width(self, width: int):
        """Set the current width."""
        self._width_slider.setValue(width)

    def add_swatch(self, color: QColor):
        """Add a color to the swatches."""
        if color not in self._swatches:
            self._swatches.insert(0, color)
            if len(self._swatches) > 20:
                self._swatches.pop()

    def get_swatches(self) -> List[QColor]:
        """Get the swatch colors."""
        return list(self._swatches)

    def set_swatches(self, colors: List[QColor]):
        """Set the swatch colors."""
        self._swatches = list(colors)
