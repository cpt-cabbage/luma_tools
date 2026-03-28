"""
Collaborative infinite canvas for image generation workspace.

Provides a truly infinite 2D canvas with pan/zoom where generations live spatially,
synchronized across team members via the shared network drive.

Infinite canvas features:
- Dynamic scene expansion as items are added or moved
- Zoom range: 5% to 3200% (Photoshop-style)
- Origin marker at (0, 0) with coordinate display
- Grid with optional snapping
- Pixel density preservation at all zoom levels
"""

import os
import uuid
import logging
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QWheelEvent, QMouseEvent,
    QFont, QFontMetrics, QPainterPath, QKeyEvent, QImage, QClipboard,
    QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent, QDropEvent
)
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsEllipseItem,
    QMenu, QApplication, QToolTip, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton
)

# Drag-drop utilities
from drag_drop import (
    extract_files_from_mime_data, filter_files_by_category, IMAGE_EXTENSIONS,
    can_accept_browser_media, extract_browser_image_data,
    save_image_data_to_file, generate_image_filename, download_image_from_url,
)

from .canvas_items import ImageNode, VideoNode, ConnectionLine, StickyNote, GroupRegion
from .canvas_drawing import DrawingPath, DrawingRect, DrawingEllipse, DrawingLine, DrawingToolbar

logger = logging.getLogger(__name__)


class CollaborativeCanvas(QGraphicsView):
    """
    An infinite pannable/zoomable canvas for collaborative image workspace.

    Features:
    - Infinite pan with middle mouse button
    - Zoom with scroll wheel (10% to 1000%)
    - Add image nodes, connections, sticky notes, groups
    - Network sync for collaboration
    - Minimap support

    Signals:
        item_added: Emitted when an item is added (item_type, data)
        item_removed: Emitted when an item is removed (item_type, item_id)
        item_moved: Emitted when an item is moved (item_type, item_id, x, y)
        selection_changed: Emitted when selection changes
        canvas_modified: Emitted when canvas state changes (for sync)
    """

    # Signals for canvas events
    item_added = Signal(str, dict)  # item_type, data
    item_removed = Signal(str, str)  # item_type, item_id
    item_moved = Signal(str, str, float, float)  # item_type, item_id, x, y
    selection_changed = Signal(list)  # list of selected items
    canvas_modified = Signal()  # general modification signal
    cursor_moved = Signal(float, float)  # x, y in scene coordinates
    zoom_changed = Signal(float)  # emitted when zoom level changes
    minimap_trigger = Signal()  # emitted when minimap should appear (pan/zoom)
    files_dropped_on_canvas = Signal(list)  # emitted when external files are dropped (for gallery integration)
    tool_changed = Signal(str)  # emitted when the current tool changes

    # Zoom limits (Photoshop-style: dynamic minimum to 3200%)
    ABSOLUTE_MIN_ZOOM = 0.01  # Absolute floor: 1%
    MIN_ZOOM = 0.05  # Default minimum: 5% (may go lower dynamically)
    MAX_ZOOM = 32.0

    # Grid settings
    GRID_SIZE = 50  # Fixed 50px grid

    # Scene expansion margin (how much to expand when approaching edge)
    # Larger values = less frequent expansion, smoother infinite feel
    SCENE_EXPANSION_MARGIN = 10000

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create scene with large initial bounds (will expand dynamically for infinite canvas)
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-100000, -100000, 200000, 200000)
        self.setScene(self._scene)

        # Setup view
        self._setup_view()

        # State
        self._is_panning = False
        self._pan_start = QPointF()
        self._current_zoom = 1.0
        self._current_tool = 'select'  # select, pan, connect, annotate, group, crop

        # Grid and snapping state
        self._show_grid = False
        self._snap_to_grid = False
        self._snap_to_neighbors = True  # Automatic neighbor snapping

        # Connection creation state
        self._connecting_from: Optional[ImageNode] = None
        self._temp_connection_line = None

        # Track items by ID for sync
        self._image_nodes: Dict[str, ImageNode] = {}
        self._video_nodes: Dict[str, 'VideoNode'] = {}
        self._connections: Dict[str, ConnectionLine] = {}
        self._sticky_notes: Dict[str, StickyNote] = {}
        self._groups: Dict[str, GroupRegion] = {}

        # Connect scene selection changes
        self._scene.selectionChanged.connect(self._on_selection_changed)

        # Remote cursor tracking
        self._remote_cursors: Dict[str, 'CursorItem'] = {}

        # Mouse tracking for cursor presence
        self.setMouseTracking(True)

        # Flag to suppress canvas_modified signals during load
        self._loading_state = False

        # Undo stack (set by set_undo_stack())
        self._undo_stack = None

        # Tab reference for gallery integration (set by CanvasTab)
        self._tab = None

        # Coordinate display (updated on mouse move)
        self._cursor_scene_pos = QPointF(0, 0)

        # Color sampler state
        self._is_sampling_color = False
        self._color_history: List[QColor] = []  # Max 5 colors
        self._color_history_panel: Optional['ColorHistoryPanel'] = None

        # Drawing tool state
        self._is_drawing = False
        self._is_erasing = False  # Eraser mode active
        self._draw_start_pos: Optional[QPointF] = None
        self._current_drawing_item = None  # Current shape being drawn
        self._drawings: Dict[str, Any] = {}  # Track drawing items by ID
        self._drawing_toolbar: Optional[DrawingToolbar] = None
        self._drawing_color = QColor(255, 0, 0)  # Default red
        self._drawing_width = 3

        # Brush size indicator (circle following cursor in pen/eraser mode)
        self._brush_indicator = QGraphicsEllipseItem()
        indicator_pen = QPen(QColor(100, 100, 100, 150), 1, Qt.DashLine)
        indicator_pen.setCosmetic(True)  # Keep outline visible at all zoom levels
        self._brush_indicator.setPen(indicator_pen)
        self._brush_indicator.setBrush(Qt.NoBrush)
        self._brush_indicator.setZValue(9999)  # Always on top
        self._brush_indicator.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self._brush_indicator.setFlag(QGraphicsItem.ItemIsMovable, False)
        self._brush_indicator.setAcceptedMouseButtons(Qt.NoButton)  # Pass through mouse events
        self._brush_indicator.hide()
        self._scene.addItem(self._brush_indicator)

        # Space+drag temporary pan state (Photoshop-style)
        self._space_pressed = False
        self._was_panning_with_space = False

        # Text editing state (skip shortcuts when editing)
        self._editing_text = False

        # Drag-drop state
        self._drop_highlight_active = False
        self._browser_download_workers = []  # Prevent GC of download workers
        self.setAcceptDrops(True)

    def set_tab(self, tab):
        """
        Set the tab reference for gallery integration.

        Args:
            tab: The CanvasTab instance that contains this canvas
        """
        self._tab = tab

        # Subscribe to event bus for favorites changes
        self._setup_event_bus_subscriptions()

    def _setup_event_bus_subscriptions(self):
        """Subscribe to event bus signals for cross-tab updates."""
        try:
            from core.event_bus import pipeline_events
            pipeline_events.favorites_changed.connect(self._on_favorites_changed)
            logger.debug("Canvas subscribed to event bus")
        except ImportError:
            logger.debug("Event bus not available for canvas")

    def _on_favorites_changed(self):
        """Handle favorites changed event from gallery.

        Syncs all image nodes when likes/groups change in gallery.
        """
        self.sync_all_from_gallery()

    def set_undo_stack(self, undo_stack):
        """
        Set the undo stack for this canvas.

        Args:
            undo_stack: The UndoStack instance to use
        """
        self._undo_stack = undo_stack

    def _emit_modified(self):
        """Emit canvas_modified signal if not currently loading state."""
        if not self._loading_state:
            self.canvas_modified.emit()

    def _setup_view(self):
        """Configure the view settings."""
        # Rendering
        self.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.TextAntialiasing
        )

        # Scrollbars (hidden - we use pan instead)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Transformation
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Frame
        self.setFrameShape(QGraphicsView.NoFrame)

        # Background - set to None, we'll draw it ourselves
        self.setBackgroundBrush(Qt.NoBrush)

        # Enable caching for better performance
        self.setCacheMode(QGraphicsView.CacheBackground)

        # Viewport updates
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)

        # Drag mode (rubber band for selection by default)
        self.setDragMode(QGraphicsView.RubberBandDrag)

        # Accept drops
        self.setAcceptDrops(True)

        # Accept keyboard focus (required for keyboard shortcuts)
        self.setFocusPolicy(Qt.StrongFocus)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """
        Draw the canvas background with optional grid.

        Args:
            painter: The painter to draw with
            rect: The exposed rectangle to draw
        """
        # Fill background
        painter.fillRect(rect, QColor(30, 30, 30))

        # Draw grid if enabled
        if self._show_grid:
            self._draw_grid(painter, rect)

    def _draw_grid(self, painter: QPainter, rect: QRectF):
        """Draw the grid lines."""
        grid_pen = QPen(QColor(50, 50, 50), 1)
        grid_pen.setCosmetic(True)  # Keep line width constant regardless of zoom
        painter.setPen(grid_pen)

        # Calculate grid bounds
        left = int(rect.left() / self.GRID_SIZE) * self.GRID_SIZE
        top = int(rect.top() / self.GRID_SIZE) * self.GRID_SIZE
        right = rect.right()
        bottom = rect.bottom()

        # Draw vertical lines
        x = left
        while x <= right:
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += self.GRID_SIZE

        # Draw horizontal lines
        y = top
        while y <= bottom:
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += self.GRID_SIZE

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """
        Draw foreground elements: origin marker and coordinate display.

        Args:
            painter: The painter to draw with
            rect: The exposed rectangle
        """
        # Draw origin marker at (0, 0)
        self._draw_origin_marker(painter)

        # Draw coordinate display in screen space
        self._draw_coordinate_display(painter)

    def _draw_origin_marker(self, painter: QPainter):
        """Draw the origin crosshair at (0, 0)."""
        # Only draw if origin is visible
        origin = QPointF(0, 0)
        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        if not view_rect.contains(origin):
            return

        # Draw crosshair
        crosshair_size = 20 / self._current_zoom  # Screen-space size
        origin_pen = QPen(QColor(100, 100, 100), 2)
        origin_pen.setCosmetic(True)
        painter.setPen(origin_pen)

        # Horizontal line
        painter.drawLine(
            QPointF(-crosshair_size, 0),
            QPointF(crosshair_size, 0)
        )
        # Vertical line
        painter.drawLine(
            QPointF(0, -crosshair_size),
            QPointF(0, crosshair_size)
        )

        # Small circle at center
        painter.drawEllipse(origin, 3 / self._current_zoom, 3 / self._current_zoom)

    def _draw_coordinate_display(self, painter: QPainter):
        """Draw the coordinate display in the corner of the viewport."""
        # Switch to viewport coordinates for overlay
        painter.save()
        painter.resetTransform()

        # Format coordinates compactly
        x = int(self._cursor_scene_pos.x())
        y = int(self._cursor_scene_pos.y())
        coord_text = f"({x}, {y})"

        # Draw background
        font = QFont("Consolas", 9)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(coord_text)

        # Position in bottom-left corner
        margin = 10
        bg_rect = QRectF(
            margin,
            self.viewport().height() - text_rect.height() - margin - 4,
            text_rect.width() + 12,
            text_rect.height() + 6
        )

        painter.fillRect(bg_rect, QColor(40, 40, 40, 200))
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(
            bg_rect.adjusted(6, 0, 0, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            coord_text
        )

        # Also draw zoom level
        zoom_text = f"{self._current_zoom * 100:.0f}%"
        zoom_rect = metrics.boundingRect(zoom_text)
        zoom_bg_rect = QRectF(
            margin,
            bg_rect.top() - zoom_rect.height() - 10,
            zoom_rect.width() + 12,
            zoom_rect.height() + 6
        )

        painter.fillRect(zoom_bg_rect, QColor(40, 40, 40, 200))
        painter.drawText(
            zoom_bg_rect.adjusted(6, 0, 0, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            zoom_text
        )

        # Draw drop highlight overlay when dragging files
        if self._drop_highlight_active:
            self._draw_drop_overlay(painter)

        painter.restore()

    def _draw_drop_overlay(self, painter: QPainter):
        """Draw a visual overlay when files are being dragged over the canvas."""
        viewport_rect = QRectF(self.viewport().rect())

        # Semi-transparent blue overlay
        painter.fillRect(viewport_rect, QColor(74, 158, 255, 40))

        # Dashed border
        border_pen = QPen(QColor(74, 158, 255), 3, Qt.DashLine)
        painter.setPen(border_pen)
        painter.drawRect(viewport_rect.adjusted(4, 4, -4, -4))

        # "Drop images here" text
        font = QFont("Segoe UI", 16, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(74, 158, 255))
        painter.drawText(viewport_rect, Qt.AlignCenter, "Drop images here")

    # -------------------------------------------------------------------------
    # Tool Management
    # -------------------------------------------------------------------------

    def set_tool(self, tool: str):
        """
        Set the current tool.

        Args:
            tool: One of 'select', 'select_drawings', 'pan', 'connect', 'annotate',
                  'group', 'pen', 'rect', 'ellipse', 'line', 'eraser', 'crop'
        """
        self._current_tool = tool

        if tool == 'pan':
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.OpenHandCursor)
        elif tool == 'select':
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.setCursor(Qt.ArrowCursor)
        elif tool == 'select_drawings':
            # Drawing selection mode - only drawings are selectable
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.setCursor(Qt.ArrowCursor)
        elif tool == 'connect':
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        elif tool == 'annotate':
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        elif tool == 'group':
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.setCursor(Qt.CrossCursor)
        elif tool == 'crop':
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        elif tool in ('pen', 'rect', 'ellipse', 'line', 'eraser'):
            # Drawing tools - disable drag mode so we can handle mouse events
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
            # Show drawing toolbar if we have one
            if hasattr(self, '_drawing_toolbar') and self._drawing_toolbar:
                self._drawing_toolbar.show()
                self._drawing_toolbar.set_tool(tool)

        # Hide brush indicator for non-brush tools
        if tool not in ('pen', 'eraser'):
            try:
                indicator = self._ensure_brush_indicator()
                indicator.hide()
            except RuntimeError:
                pass  # Indicator was deleted, ignore

        # Manage item selectability based on tool
        if tool == 'select_drawings':
            # Only drawings are selectable
            self._set_drawings_selectable(True)
            self._set_other_items_selectable(False)
        elif tool == 'select':
            # All items are selectable
            self._set_drawings_selectable(True)
            self._set_other_items_selectable(True)
        else:
            # Non-selection tools - nothing selectable (prevents accidental selection)
            self._set_drawings_selectable(False)
            self._set_other_items_selectable(False)

        # Emit signal so tab can respond (e.g., show/hide drawing panel)
        self.tool_changed.emit(tool)

    def current_tool(self) -> str:
        """Get the current tool."""
        return self._current_tool

    def _restore_cursor_for_tool(self):
        """Restore cursor to match the current tool (after space+drag pan ends)."""
        tool = self._current_tool
        if tool in ('select', 'select_drawings'):
            self.setCursor(Qt.ArrowCursor)
        elif tool == 'pan':
            self.setCursor(Qt.OpenHandCursor)
        elif tool in ('connect', 'annotate', 'crop', 'group', 'pen', 'rect', 'ellipse', 'line', 'eraser'):
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def _set_drawings_selectable(self, selectable: bool):
        """Enable/disable selection for drawing items.

        Args:
            selectable: Whether drawings should be selectable
        """
        for drawing in self._drawings.values():
            drawing.setFlag(QGraphicsItem.ItemIsSelectable, selectable)
            drawing.setFlag(QGraphicsItem.ItemIsMovable, selectable)

    def _set_other_items_selectable(self, selectable: bool):
        """Enable/disable selection for non-drawing items (images, notes, groups).

        Args:
            selectable: Whether items should be selectable
        """
        # Image nodes
        for node in self._image_nodes.values():
            node.setFlag(QGraphicsItem.ItemIsSelectable, selectable)
            node.setFlag(QGraphicsItem.ItemIsMovable, selectable)

        # Sticky notes
        for note in self._sticky_notes.values():
            note.setFlag(QGraphicsItem.ItemIsSelectable, selectable)
            note.setFlag(QGraphicsItem.ItemIsMovable, selectable)

        # Group regions
        for group in self._groups.values():
            group.setFlag(QGraphicsItem.ItemIsSelectable, selectable)
            group.setFlag(QGraphicsItem.ItemIsMovable, selectable)

    # -------------------------------------------------------------------------
    # Adding Items
    # -------------------------------------------------------------------------

    def add_image(self, image_path: str, x: float = None, y: float = None,
                  width: float = None, height: float = None,
                  liked: bool = False, node_id: str = None,
                  qimage: Optional[QImage] = None,
                  content_hash: str = None) -> ImageNode:
        """
        Add an image node to the canvas.

        Args:
            image_path: Path to the image file
            x, y: Position (defaults to center of view)
            width, height: Size (None = use original image resolution)
            liked: Initial liked state
            node_id: Optional ID for sync (defaults to filename)
            qimage: Optional pre-loaded QImage (for async loading - avoids disk I/O)
            content_hash: SHA-256 content hash for file identification

        Returns:
            The created ImageNode
        """
        # Compute content hash if not provided
        if content_hash is None:
            try:
                from comfyui.utils import compute_file_hash
                content_hash = compute_file_hash(image_path)
            except Exception:
                content_hash = None

        # Default position to center of current view
        if x is None or y is None:
            center = self.mapToScene(self.viewport().rect().center())
            x = x if x is not None else center.x()
            y = y if y is not None else center.y()

        # Create node - width/height can be None to use original resolution
        # Pass qimage to avoid disk I/O if pre-loaded
        node = ImageNode(image_path, x, y, width, height, qimage=qimage,
                         content_hash=content_hash)
        node.set_liked(liked)

        # Add to scene
        self._scene.addItem(node)

        # Track by ID
        node_id = node_id or os.path.basename(image_path)
        self._image_nodes[node_id] = node

        # Get actual size for signal (after image loaded)
        actual_width, actual_height = node.get_size()

        # Ensure scene contains this item (dynamic expansion)
        item_rect = QRectF(x, y, actual_width, actual_height)
        self._ensure_scene_contains(item_rect)

        # Emit signal
        self.item_added.emit('image', {
            'id': node_id,
            'path': image_path,
            'x': x, 'y': y,
            'width': actual_width, 'height': actual_height,
            'liked': liked
        })
        self._emit_modified()

        return node

    def add_video(self, video_path: str, x: float = None, y: float = None,
                  width: float = None, height: float = None,
                  node_id: str = None,
                  content_hash: str = None) -> 'VideoNode':
        """
        Add a video node to the canvas.

        Args:
            video_path: Path to the video file
            x, y: Position (defaults to center of view)
            width, height: Size (None = use defaults)
            node_id: Optional ID for sync (defaults to filename)
            content_hash: SHA-256 content hash for file identification

        Returns:
            The created VideoNode
        """
        # Compute content hash if not provided
        if content_hash is None:
            try:
                from comfyui.utils import compute_file_hash
                content_hash = compute_file_hash(video_path)
            except Exception:
                content_hash = None

        # Default position to center of current view
        if x is None or y is None:
            center = self.mapToScene(self.viewport().rect().center())
            x = x if x is not None else center.x()
            y = y if y is not None else center.y()

        # Create video node
        node = VideoNode(video_path, x, y, width, height,
                         content_hash=content_hash)

        # Add to scene
        self._scene.addItem(node)

        # Track by ID
        node_id = node_id or os.path.basename(video_path)
        self._video_nodes[node_id] = node

        # Ensure scene contains this item
        actual_width, actual_height = node.get_size()
        item_rect = QRectF(x, y, actual_width, actual_height)
        self._ensure_scene_contains(item_rect)

        # Sync from gallery
        favorites_manager = self._get_favorites_manager()
        if favorites_manager:
            node.sync_from_gallery(favorites_manager)

        # Emit signal
        self.item_added.emit('video', {
            'id': node_id,
            'path': video_path,
            'x': x, 'y': y,
            'width': actual_width, 'height': actual_height,
        })
        self._emit_modified()

        return node

    def remove_video(self, node_id: str):
        """Remove a video node by ID."""
        node = self._video_nodes.pop(node_id, None)
        if node:
            # Deactivate player if active
            if node._is_active:
                node.deactivate_player()

            # Remove connected lines
            for conn_id, conn in list(self._connections.items()):
                if conn.source_node == node or conn.target_node == node:
                    self._scene.removeItem(conn)
                    del self._connections[conn_id]

            self._scene.removeItem(node)
            self.item_removed.emit('video', node_id)
            self._emit_modified()

    def deactivate_all_videos(self, except_node: 'VideoNode' = None):
        """Deactivate all video players except the given node.

        Enforces single-active-player policy to save resources.
        """
        for node in self._video_nodes.values():
            if node != except_node and node._is_active:
                node.deactivate_player()

    def add_connection(self, source_id: str, target_id: str,
                       connection_type: str = 'manual', label: str = '',
                       connection_id: str = None) -> Optional[ConnectionLine]:
        """
        Add a connection between two image nodes.

        Args:
            source_id: ID of source image node
            target_id: ID of target image node
            connection_type: 'auto' or 'manual'
            label: Optional label text
            connection_id: Optional ID for sync

        Returns:
            The created ConnectionLine, or None if nodes not found
        """
        source = self._image_nodes.get(source_id)
        target = self._image_nodes.get(target_id)

        if not source or not target:
            logger.warning(f"Cannot create connection: nodes not found ({source_id} -> {target_id})")
            return None

        # Track by ID
        connection_id = connection_id or f"{source_id}_{target_id}"

        # Create connection with ID
        connection = ConnectionLine(source, target, connection_type, label, connection_id)
        self._scene.addItem(connection)

        self._connections[connection_id] = connection

        # Emit signal
        self.item_added.emit('connection', {
            'id': connection_id,
            'source': source_id,
            'target': target_id,
            'type': connection_type,
            'label': label
        })
        self._emit_modified()

        return connection

    def add_sticky_note(self, x: float, y: float, text: str = '',
                        color: str = 'yellow', font_size: int = 10,
                        note_id: str = None) -> StickyNote:
        """
        Add a sticky note to the canvas.

        Args:
            x, y: Position
            text: Note text
            color: One of 'yellow', 'green', 'red', 'blue' or hex string
            font_size: Font size in points (default 10)
            note_id: Optional ID for sync

        Returns:
            The created StickyNote
        """
        note = StickyNote(x, y, text, color, font_size=font_size)
        self._scene.addItem(note)

        # Track by ID
        note_id = note_id or f"note_{uuid.uuid4().hex[:8]}"
        self._sticky_notes[note_id] = note

        # Emit signal
        self.item_added.emit('sticky', {
            'id': note_id,
            'x': x, 'y': y,
            'text': text,
            'color': color,
            'font_size': font_size
        })
        self._emit_modified()

        return note

    def add_group(self, x: float, y: float, width: float, height: float,
                  name: str = 'Group', color: str = '#ff6b6b',
                  group_id: str = None) -> GroupRegion:
        """
        Add a group region to the canvas.

        Args:
            x, y: Position
            width, height: Size
            name: Group name
            color: Hex color string
            group_id: Optional ID for sync

        Returns:
            The created GroupRegion
        """
        group = GroupRegion(x, y, width, height, name, color)
        self._scene.addItem(group)

        # Track by ID
        group_id = group_id or f"group_{uuid.uuid4().hex[:8]}"
        self._groups[group_id] = group

        # Emit signal
        self.item_added.emit('group', {
            'id': group_id,
            'x': x, 'y': y,
            'width': width, 'height': height,
            'name': name,
            'color': color
        })
        self._emit_modified()

        return group

    # -------------------------------------------------------------------------
    # Removing Items
    # -------------------------------------------------------------------------

    def remove_image(self, node_id: str):
        """Remove an image node by ID."""
        node = self._image_nodes.pop(node_id, None)
        if node:
            # Remove connected lines
            for conn_id, conn in list(self._connections.items()):
                if conn.source_node == node or conn.target_node == node:
                    self._scene.removeItem(conn)
                    del self._connections[conn_id]

            self._scene.removeItem(node)
            self.item_removed.emit('image', node_id)
            self._emit_modified()

    def remove_connection(self, connection_id: str):
        """Remove a connection by ID."""
        conn = self._connections.pop(connection_id, None)
        if conn:
            self._scene.removeItem(conn)
            self.item_removed.emit('connection', connection_id)
            self._emit_modified()

    def remove_sticky_note(self, note_id: str):
        """Remove a sticky note by ID."""
        note = self._sticky_notes.pop(note_id, None)
        if note:
            self._scene.removeItem(note)
            self.item_removed.emit('sticky', note_id)
            self._emit_modified()

    def remove_group(self, group_id: str):
        """Remove a group by ID."""
        group = self._groups.pop(group_id, None)
        if group:
            self._scene.removeItem(group)
            self.item_removed.emit('group', group_id)
            self._emit_modified()

    def remove_drawing(self, drawing_id: str):
        """Remove a drawing by ID."""
        drawing = self._drawings.pop(drawing_id, None)
        if drawing:
            self._scene.removeItem(drawing)
            self.item_removed.emit('drawing', drawing_id)
            self._emit_modified()

    # -------------------------------------------------------------------------
    # View Navigation
    # -------------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent):
        """Handle zoom with mouse wheel."""
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        # Check zoom limits - use dynamic minimum based on content bounds
        min_zoom = self._get_content_min_zoom()
        new_zoom = self._current_zoom * zoom_factor
        if new_zoom < min_zoom:
            zoom_factor = min_zoom / self._current_zoom
            new_zoom = min_zoom
        elif new_zoom > self.MAX_ZOOM:
            zoom_factor = self.MAX_ZOOM / self._current_zoom
            new_zoom = self.MAX_ZOOM

        old_zoom = self._current_zoom
        self._current_zoom = new_zoom
        self.scale(zoom_factor, zoom_factor)

        # Emit signal if zoom actually changed
        if abs(old_zoom - new_zoom) > 0.001:
            self.zoom_changed.emit(self._current_zoom)
            self.minimap_trigger.emit()

        # Update brush indicator size to maintain screen-space appearance
        self._update_brush_indicator_for_zoom()

        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for pan and tool actions."""
        # Grab keyboard focus on click (for keyboard shortcuts)
        self.setFocus()

        # Space+left click for temporary pan (Photoshop-style)
        if event.button() == Qt.LeftButton and self._space_pressed:
            self._is_panning = True
            self._was_panning_with_space = True
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        # Middle mouse for pan
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        # Color sampling: S+click
        if event.button() == Qt.LeftButton and self._is_sampling_color:
            scene_pos = self.mapToScene(event.position().toPoint())
            screen_pos = event.globalPosition().toPoint()
            self.sample_color(scene_pos, screen_pos)
            event.accept()
            return

        # Tool-specific handling
        if self._current_tool == 'connect' and event.button() == Qt.LeftButton:
            self._start_connection(event)
            event.accept()
            return

        if self._current_tool == 'annotate' and event.button() == Qt.LeftButton:
            pos = self.mapToScene(event.position().toPoint())
            note = self.add_sticky_note(pos.x(), pos.y())
            # Switch to select tool after creating note (prevents continuous note creation)
            self.set_tool('select')
            # Select the new note so user can immediately edit it
            self._scene.clearSelection()
            note.setSelected(True)
            event.accept()
            return

        # Eraser tool
        if self._current_tool == 'eraser' and event.button() == Qt.LeftButton:
            self._is_erasing = True
            self._erase_at_position(event)
            event.accept()
            return

        # Drawing tools
        if self._current_tool in ('pen', 'rect', 'ellipse', 'line') and event.button() == Qt.LeftButton:
            self._start_drawing(event)
            event.accept()
            return

        # Shift-select: toggle item selection without clearing others
        if self._current_tool == 'select' and event.button() == Qt.LeftButton:
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.ShiftModifier:
                scene_pos = self.mapToScene(event.position().toPoint())
                item = self._scene.itemAt(scene_pos, self.transform())
                if item:
                    # Toggle selection of the clicked item
                    item.setSelected(not item.isSelected())
                    event.accept()
                    return
                # If no item clicked, let default behavior handle (rubber band starts)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for pan and cursor tracking."""
        # Track cursor position for coordinate display
        scene_pos = self.mapToScene(event.position().toPoint())
        self._cursor_scene_pos = scene_pos

        # Emit cursor position for presence sync
        self.cursor_moved.emit(scene_pos.x(), scene_pos.y())

        # Update coordinate display
        self.viewport().update()

        # Update brush indicator position when in brush tool mode
        if self._current_tool in ('pen', 'eraser'):
            indicator = self._ensure_brush_indicator()
            # Screen-space size: divide by zoom so indicator stays constant on screen
            size = self._drawing_width / self._current_zoom if self._current_zoom > 0 else self._drawing_width
            indicator.setRect(
                scene_pos.x() - size / 2, scene_pos.y() - size / 2, size, size
            )
            if not indicator.isVisible():
                indicator.show()

        if self._is_panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            # Expand scene if approaching edges (infinite canvas)
            self._expand_scene_if_needed()
            self.minimap_trigger.emit()
            event.accept()
            return

        # Connection preview
        if self._connecting_from and self._temp_connection_line:
            # Update temp line endpoint
            pass

        # Eraser dragging
        if self._is_erasing:
            self._erase_at_position(event)
            event.accept()
            return

        # Drawing preview
        if self._is_drawing and self._current_drawing_item is not None:
            self._update_drawing(event)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release after pan."""
        # Space+left click pan release
        if event.button() == Qt.LeftButton and self._was_panning_with_space:
            self._is_panning = False
            self._was_panning_with_space = False
            # If space still held, show open hand; otherwise restore tool cursor
            if self._space_pressed:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self._restore_cursor_for_tool()
            event.accept()
            return

        if event.button() == Qt.MiddleButton and self._is_panning:
            self._is_panning = False
            if self._current_tool == 'pan':
                self.setCursor(Qt.OpenHandCursor)
            elif self._current_tool in ('pen', 'rect', 'ellipse', 'line', 'eraser', 'connect', 'annotate', 'crop', 'group'):
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        # Complete connection
        if self._current_tool == 'connect' and event.button() == Qt.LeftButton:
            self._complete_connection(event)
            event.accept()
            return

        # Complete erasing
        if self._is_erasing and event.button() == Qt.LeftButton:
            self._is_erasing = False
            event.accept()
            return

        # Complete drawing
        if self._is_drawing and event.button() == Qt.LeftButton:
            self._finish_drawing(event)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------------------
    # Drag and Drop
    # -------------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter - accept local files or browser image data."""
        # Check local files first (fast path)
        paths = extract_files_from_mime_data(event.mimeData())
        media_paths = filter_files_by_category(paths, {'image', 'video'})
        if media_paths:
            event.acceptProposedAction()
            self._drop_highlight_active = True
            self.viewport().update()
            logger.debug(f"Canvas drag enter: {len(media_paths)} local file(s)")
            return

        # Check browser image data (raw images, HTTP URLs)
        if can_accept_browser_media(event.mimeData()):
            event.acceptProposedAction()
            self._drop_highlight_active = True
            self.viewport().update()
            logger.debug("Canvas drag enter: browser image data")
            return

        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        """Handle drag move - continue accepting if valid."""
        paths = extract_files_from_mime_data(event.mimeData())
        media_paths = filter_files_by_category(paths, {'image', 'video'})
        if media_paths or can_accept_browser_media(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        """Handle drag leave - hide drop highlight."""
        self._drop_highlight_active = False
        self.viewport().update()
        event.accept()

    def dropEvent(self, event: QDropEvent):
        """Handle drop - add images and videos to canvas.

        Handles local files (existing) and browser data (raw images, HTTP URLs).
        """
        self._drop_highlight_active = False
        self.viewport().update()

        drop_pos = self.mapToScene(event.position().toPoint())

        # Try local files first (existing behavior)
        paths = extract_files_from_mime_data(event.mimeData())
        media_paths = filter_files_by_category(paths, {'image', 'video'})

        if media_paths:
            logger.info(f"Dropped {len(media_paths)} file(s) at ({drop_pos.x():.0f}, {drop_pos.y():.0f})")

            from drag_drop import get_file_category
            offset = 0
            for path in media_paths:
                category = get_file_category(path)
                if category == 'video':
                    self.add_video(path, drop_pos.x() + offset, drop_pos.y() + offset)
                else:
                    self.add_image(path, drop_pos.x() + offset, drop_pos.y() + offset)
                offset += 50

            self.files_dropped_on_canvas.emit(media_paths)
            event.acceptProposedAction()
            return

        # Fallback: browser image data (raw images, HTTP URLs)
        if self._handle_browser_drop(event.mimeData(), drop_pos):
            event.acceptProposedAction()
            return

        event.ignore()

    # -------------------------------------------------------------------------
    # Browser Drag-Drop and Image Download
    # -------------------------------------------------------------------------

    def _get_gallery_save_dir(self) -> Optional[str]:
        """Get the gallery directory for saving pasted/dropped images.

        Returns the user's gallery folder (network_output_path/username).
        """
        try:
            from core.settings_manager import safe_get_setting
            from core.state_manager import app_state

            network_path = safe_get_setting("network_output_path", "")
            if not network_path:
                logger.warning("No network_output_path configured")
                return None

            username = app_state.user
            if not username or not username.strip():
                logger.warning("No username available for gallery save directory")
                return None

            save_dir = os.path.join(network_path, username.strip())

            from core.utils import ensure_directory
            ensure_directory(save_dir)
            return save_dir

        except Exception as e:
            logger.error(f"Error getting gallery save directory: {e}")
            return None

    def _handle_browser_drop(self, mime_data, drop_pos: QPointF) -> bool:
        """Handle browser-sourced drop data (raw images or HTTP URLs).

        Args:
            mime_data: QMimeData from the drop event
            drop_pos: Scene position where the drop occurred

        Returns:
            True if the drop was handled, False otherwise
        """
        data = extract_browser_image_data(mime_data)

        if data["type"] == "image_data":
            # Raw image data — save directly to gallery folder
            save_dir = self._get_gallery_save_dir()
            if not save_dir:
                logger.warning("Cannot save dropped image: no gallery directory")
                return False

            saved_path = save_image_data_to_file(
                data["image"], save_dir, generate_image_filename(prefix="canvas_drop")
            )
            if saved_path:
                self.add_image(saved_path, drop_pos.x(), drop_pos.y())
                self.files_dropped_on_canvas.emit([saved_path])
                logger.info(f"Added browser image to canvas at ({drop_pos.x():.0f}, {drop_pos.y():.0f})")
                return True
            return False

        elif data["type"] == "url":
            # HTTP URL — download in background worker
            save_dir = self._get_gallery_save_dir()
            if not save_dir:
                logger.warning("Cannot download dropped image: no gallery directory")
                return False

            for url in data["urls"]:
                self._download_and_add_image(url, save_dir, drop_pos)
            return True

        return False

    def _download_and_add_image(self, url: str, save_dir: str, position: QPointF):
        """Download an image from URL in a worker thread and add to canvas.

        Args:
            url: HTTP/HTTPS URL to download
            save_dir: Directory to save the downloaded image
            position: Scene position to place the image
        """
        from ui_components import Worker
        from PySide6.QtCore import QThreadPool

        logger.info(f"Starting download of: {url}")

        def _do_download():
            return download_image_from_url(url, save_dir)

        worker = Worker(_do_download)
        # Store position for callback via closure
        pos_x, pos_y = position.x(), position.y()

        def _on_result(saved_path):
            if worker in self._browser_download_workers:
                self._browser_download_workers.remove(worker)
            if saved_path:
                self.add_image(saved_path, pos_x, pos_y)
                self.files_dropped_on_canvas.emit([saved_path])
                logger.info(f"Downloaded and added image to canvas: {os.path.basename(saved_path)}")
            else:
                logger.warning(f"Failed to download image from: {url}")

        def _on_error(error_tuple):
            if worker in self._browser_download_workers:
                self._browser_download_workers.remove(worker)
            logger.error(f"Error downloading image from {url}: {error_tuple}")

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        self._browser_download_workers.append(worker)  # Prevent GC
        QThreadPool.globalInstance().start(worker)

    def _start_connection(self, event: QMouseEvent):
        """Start creating a connection from clicked node."""
        pos = self.mapToScene(event.position().toPoint())
        item = self._scene.itemAt(pos, self.transform())

        if isinstance(item, ImageNode):
            self._connecting_from = item
            # TODO: Add visual feedback for connection in progress

    def _complete_connection(self, event: QMouseEvent):
        """Complete the connection to target node."""
        if not self._connecting_from:
            return

        pos = self.mapToScene(event.position().toPoint())
        item = self._scene.itemAt(pos, self.transform())

        if isinstance(item, ImageNode) and item != self._connecting_from:
            # Find IDs
            source_id = None
            target_id = None
            for nid, node in self._image_nodes.items():
                if node == self._connecting_from:
                    source_id = nid
                if node == item:
                    target_id = nid

            if source_id and target_id:
                self.add_connection(source_id, target_id, 'manual')

        self._connecting_from = None

    # -------------------------------------------------------------------------
    # Drawing Tool Methods
    # -------------------------------------------------------------------------

    def _start_drawing(self, event: QMouseEvent):
        """Start drawing with the current tool."""
        pos = self.mapToScene(event.position().toPoint())
        self._is_drawing = True
        self._draw_start_pos = pos

        tool = self._current_tool

        if tool == 'pen':
            # Create a new path for freehand drawing
            self._current_drawing_item = DrawingPath()
            self._current_drawing_item.set_pen_color(self._drawing_color)
            self._current_drawing_item.set_pen_width(self._drawing_width)
            # Disable movable/selectable during drawing to prevent scene from intercepting events
            self._current_drawing_item.setFlag(QGraphicsItem.ItemIsMovable, False)
            self._current_drawing_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self._current_drawing_item.setAcceptedMouseButtons(Qt.NoButton)
            self._current_drawing_item.add_point(pos)
            self._scene.addItem(self._current_drawing_item)

        elif tool == 'rect':
            # Create a rectangle - hide until first update to prevent origin flash
            self._current_drawing_item = DrawingRect(QRectF(pos, pos))
            self._current_drawing_item.set_pen_color(self._drawing_color)
            self._current_drawing_item.set_pen_width(self._drawing_width)
            # Disable movable/selectable during drawing to prevent scene from intercepting events
            self._current_drawing_item.setFlag(QGraphicsItem.ItemIsMovable, False)
            self._current_drawing_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self._current_drawing_item.setAcceptedMouseButtons(Qt.NoButton)
            self._current_drawing_item.setOpacity(0)  # Hide until first mouse move
            self._scene.addItem(self._current_drawing_item)

        elif tool == 'ellipse':
            # Create an ellipse - hide until first update to prevent origin flash
            self._current_drawing_item = DrawingEllipse(QRectF(pos, pos))
            self._current_drawing_item.set_pen_color(self._drawing_color)
            self._current_drawing_item.set_pen_width(self._drawing_width)
            # Disable movable/selectable during drawing to prevent scene from intercepting events
            self._current_drawing_item.setFlag(QGraphicsItem.ItemIsMovable, False)
            self._current_drawing_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self._current_drawing_item.setAcceptedMouseButtons(Qt.NoButton)
            self._current_drawing_item.setOpacity(0)  # Hide until first mouse move
            self._scene.addItem(self._current_drawing_item)

        elif tool == 'line':
            # Create a line - hide until first update to prevent origin flash
            from PySide6.QtCore import QLineF
            self._current_drawing_item = DrawingLine(QLineF(pos, pos))
            self._current_drawing_item.set_pen_color(self._drawing_color)
            self._current_drawing_item.set_pen_width(self._drawing_width)
            # Disable movable/selectable during drawing to prevent scene from intercepting events
            self._current_drawing_item.setFlag(QGraphicsItem.ItemIsMovable, False)
            self._current_drawing_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self._current_drawing_item.setAcceptedMouseButtons(Qt.NoButton)
            self._current_drawing_item.setOpacity(0)  # Hide until first mouse move
            self._scene.addItem(self._current_drawing_item)

        logger.debug(f"Started drawing with tool: {tool}")

    def _update_drawing(self, event: QMouseEvent):
        """Update the current drawing as the mouse moves."""
        if not self._current_drawing_item or not self._draw_start_pos:
            return

        # Show the item on first update (fixes origin flash bug)
        if self._current_drawing_item.opacity() == 0:
            self._current_drawing_item.setOpacity(1)

        pos = self.mapToScene(event.position().toPoint())
        tool = self._current_tool

        # Check for Shift key to constrain proportions
        modifiers = event.modifiers()
        constrain = bool(modifiers & Qt.ShiftModifier)

        if tool == 'pen':
            # Add point to path
            # Get pressure if tablet event (default 1.0 for mouse)
            pressure = 1.0
            self._current_drawing_item.add_point(pos, pressure)

        elif tool == 'rect':
            # Update rectangle from start to current position
            rect = self._make_rect(self._draw_start_pos, pos, constrain)
            self._current_drawing_item.set_rect(rect)

        elif tool == 'ellipse':
            # Update ellipse from start to current position
            rect = self._make_rect(self._draw_start_pos, pos, constrain)
            self._current_drawing_item.set_rect(rect)

        elif tool == 'line':
            # Update line endpoint
            from PySide6.QtCore import QLineF
            end_pos = pos
            if constrain:
                # Snap to 45-degree angles
                end_pos = self._snap_to_angle(self._draw_start_pos, pos)
            self._current_drawing_item.set_line(QLineF(self._draw_start_pos, end_pos))

    def _finish_drawing(self, event: QMouseEvent):
        """Finish the current drawing."""
        if not self._current_drawing_item:
            self._is_drawing = False
            return

        # Final update
        self._update_drawing(event)

        # Normalize coordinates from scene to local for proper dragging
        if hasattr(self._current_drawing_item, 'normalize_to_local'):
            self._current_drawing_item.normalize_to_local()

        # Re-enable selection and movement flags now that drawing is complete
        self._current_drawing_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self._current_drawing_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self._current_drawing_item.setAcceptedMouseButtons(Qt.LeftButton)

        # Track the drawing with unique UUID-based ID
        drawing_id = f"drawing_{uuid.uuid4().hex[:8]}"
        self._drawings[drawing_id] = self._current_drawing_item

        # Record to undo stack (drawing already added to scene, don't re-execute)
        if self._undo_stack:
            from .canvas_undo import AddDrawingCommand
            cmd = AddDrawingCommand(self, self._current_drawing_item, drawing_id)
            self._undo_stack.record(cmd)

        # Emit modified signal
        self._emit_modified()

        logger.debug(f"Finished drawing: {drawing_id}")

        # Reset state
        self._is_drawing = False
        self._draw_start_pos = None
        self._current_drawing_item = None

    def _erase_at_position(self, event: QMouseEvent):
        """Erase drawings at the current mouse position.

        For DrawingPath: Partially erases by removing points within the eraser radius,
        potentially splitting the path into multiple segments.

        For shapes (DrawingRect, DrawingEllipse, DrawingLine): Removes the entire shape
        if it intersects with the eraser.

        Uses the brush size as the eraser radius.
        """
        pos = self.mapToScene(event.position().toPoint())
        radius = self._drawing_width / 2

        # Create an eraser rect around cursor position for quick intersection test
        erase_rect = QRectF(pos.x() - radius, pos.y() - radius, radius * 2, radius * 2)

        # Find all items that intersect with the erase rect
        items = self._scene.items(erase_rect)

        modified = False
        paths_to_process = []
        shapes_to_remove = []

        # Separate paths (partial erase) from shapes (full delete)
        for item in items:
            if isinstance(item, DrawingPath):
                paths_to_process.append(item)
            elif isinstance(item, (DrawingRect, DrawingEllipse, DrawingLine)):
                shapes_to_remove.append(item)

        # Process paths with partial erasing
        for path in paths_to_process:
            result = path.erase_at(pos, radius)

            if result is None:
                # Path was modified in place (some points removed but not split)
                modified = True
            elif isinstance(result, list):
                if len(result) == 0:
                    # All points erased - remove the path entirely
                    for drawing_id, drawing in list(self._drawings.items()):
                        if drawing is path:
                            del self._drawings[drawing_id]
                            break
                    self._scene.removeItem(path)
                    modified = True
                else:
                    # Path was split into multiple new paths
                    # Remove original
                    for drawing_id, drawing in list(self._drawings.items()):
                        if drawing is path:
                            del self._drawings[drawing_id]
                            break
                    self._scene.removeItem(path)

                    # Add new split paths
                    for new_path in result:
                        drawing_id = f"drawing_{uuid.uuid4().hex[:8]}"
                        self._drawings[drawing_id] = new_path
                        self._scene.addItem(new_path)

                    modified = True

        # Remove shapes entirely (they don't support partial erasing)
        for shape in shapes_to_remove:
            for drawing_id, drawing in list(self._drawings.items()):
                if drawing is shape:
                    del self._drawings[drawing_id]
                    break
            self._scene.removeItem(shape)
            modified = True

        if modified:
            self._emit_modified()
            logger.debug(f"Eraser action at ({pos.x():.0f}, {pos.y():.0f})")

    def _make_rect(self, start: QPointF, end: QPointF, constrain: bool = False) -> QRectF:
        """
        Create a rectangle from two corner points.

        Args:
            start: Starting corner
            end: Ending corner
            constrain: If True, make it a square

        Returns:
            QRectF with proper coordinates
        """
        x1, y1 = start.x(), start.y()
        x2, y2 = end.x(), end.y()

        if constrain:
            # Make square: use larger dimension
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            size = max(dx, dy)

            if x2 >= x1:
                x2 = x1 + size
            else:
                x2 = x1 - size

            if y2 >= y1:
                y2 = y1 + size
            else:
                y2 = y1 - size

        # Normalize to top-left, bottom-right
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        return QRectF(left, top, width, height)

    def _snap_to_angle(self, start: QPointF, end: QPointF, snap_angle: float = 45.0) -> QPointF:
        """
        Snap end point to nearest angle increment from start.

        Args:
            start: Starting point
            end: Current end point
            snap_angle: Angle increment to snap to (degrees)

        Returns:
            Snapped end point
        """
        import math

        dx = end.x() - start.x()
        dy = end.y() - start.y()

        if abs(dx) < 1 and abs(dy) < 1:
            return end

        # Get current angle
        angle = math.atan2(dy, dx)
        angle_deg = math.degrees(angle)

        # Snap to nearest increment
        snapped_deg = round(angle_deg / snap_angle) * snap_angle
        snapped_rad = math.radians(snapped_deg)

        # Get distance
        dist = math.sqrt(dx * dx + dy * dy)

        # Calculate snapped position
        snapped_x = start.x() + dist * math.cos(snapped_rad)
        snapped_y = start.y() + dist * math.sin(snapped_rad)

        return QPointF(snapped_x, snapped_y)

    def set_drawing_color(self, color: QColor):
        """Set the drawing color for new drawings."""
        self._drawing_color = color

    def _ensure_brush_indicator(self) -> QGraphicsEllipseItem:
        """Ensure brush indicator exists and is valid, recreating if needed.

        The brush indicator can be deleted when the scene is cleared.
        This method checks if it's still valid and recreates it if not.

        Returns:
            The valid brush indicator item.
        """
        need_recreate = False

        # Check if we need to recreate
        if not hasattr(self, '_brush_indicator') or self._brush_indicator is None:
            need_recreate = True
        else:
            # Check if C++ object is still valid
            try:
                # Accessing any property will raise RuntimeError if deleted
                self._brush_indicator.zValue()
            except RuntimeError:
                need_recreate = True

        if need_recreate:
            self._brush_indicator = QGraphicsEllipseItem()
            indicator_pen = QPen(QColor(100, 100, 100, 150), 1, Qt.DashLine)
            indicator_pen.setCosmetic(True)  # Keep outline visible at all zoom levels
            self._brush_indicator.setPen(indicator_pen)
            self._brush_indicator.setBrush(Qt.NoBrush)
            self._brush_indicator.setZValue(9999)  # Always on top
            self._brush_indicator.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self._brush_indicator.setFlag(QGraphicsItem.ItemIsMovable, False)
            self._brush_indicator.setAcceptedMouseButtons(Qt.NoButton)  # Pass through
            self._brush_indicator.hide()
            self._scene.addItem(self._brush_indicator)

        return self._brush_indicator

    def _update_brush_indicator_for_zoom(self):
        """Rescale the brush indicator after zoom changes to keep screen-space size."""
        try:
            indicator = self._ensure_brush_indicator()
            if indicator.isVisible():
                rect = indicator.rect()
                center_x = rect.center().x()
                center_y = rect.center().y()
                size = self._drawing_width / self._current_zoom if self._current_zoom > 0 else self._drawing_width
                indicator.setRect(
                    center_x - size / 2, center_y - size / 2, size, size
                )
        except RuntimeError:
            pass

    def set_drawing_width(self, width: int):
        """Set the drawing width for new drawings."""
        self._drawing_width = max(1, width)

        # Update brush indicator size if visible (screen-space)
        try:
            indicator = self._ensure_brush_indicator()
            if indicator.isVisible():
                rect = indicator.rect()
                center_x = rect.center().x()
                center_y = rect.center().y()
                size = width / self._current_zoom if self._current_zoom > 0 else width
                indicator.setRect(
                    center_x - size / 2, center_y - size / 2, size, size
                )
        except RuntimeError:
            # C++ object deleted mid-operation, ignore
            pass

    def get_drawing_color(self) -> QColor:
        """Get the current drawing color."""
        return self._drawing_color

    def get_drawing_width(self) -> int:
        """Get the current drawing width."""
        return self._drawing_width

    def set_brush_size(self, size: int):
        """Set the brush size for drawing tools (alias for set_drawing_width)."""
        self.set_drawing_width(size)

    def get_brush_size(self) -> int:
        """Get the current brush size (alias for get_drawing_width)."""
        return self.get_drawing_width()

    def fit_all(self):
        """Fit all items in view with padding, allowing zoom below MIN_ZOOM for large content."""
        items_rect = self._scene.itemsBoundingRect()
        if not items_rect.isEmpty():
            self.fitInView(items_rect.adjusted(-50, -50, 50, 50), Qt.KeepAspectRatio)
            self._current_zoom = self.transform().m11()
            # Clamp to absolute minimum and max only
            if self._current_zoom < self.ABSOLUTE_MIN_ZOOM:
                self.set_zoom_level(self.ABSOLUTE_MIN_ZOOM)
            elif self._current_zoom > self.MAX_ZOOM:
                self.set_zoom_level(self.MAX_ZOOM)
            self.zoom_changed.emit(self._current_zoom)
            self._update_brush_indicator_for_zoom()

    def reset_view(self):
        """Reset view to origin at 100% zoom."""
        self.resetTransform()
        self._current_zoom = 1.0
        self.centerOn(0, 0)
        self.zoom_changed.emit(self._current_zoom)
        self._update_brush_indicator_for_zoom()

    def center_on_origin(self):
        """Center view on the origin (0, 0) without changing zoom."""
        self.centerOn(0, 0)

    def zoom_in(self):
        """Zoom in by one step."""
        self.set_zoom_level(self._current_zoom * 1.25)

    def zoom_out(self):
        """Zoom out by one step."""
        self.set_zoom_level(self._current_zoom / 1.25)

    def _get_content_min_zoom(self) -> float:
        """
        Calculate the minimum zoom level needed to fit all content in the viewport.

        Returns:
            Minimum zoom level based on content bounds, clamped to ABSOLUTE_MIN_ZOOM.
        """
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isEmpty():
            return self.MIN_ZOOM

        # Add padding around content
        padding = 100
        content_width = items_rect.width() + padding * 2
        content_height = items_rect.height() + padding * 2

        # Get viewport size
        viewport = self.viewport()
        if not viewport:
            return self.MIN_ZOOM

        view_width = viewport.width()
        view_height = viewport.height()

        if view_width <= 0 or view_height <= 0:
            return self.MIN_ZOOM

        # Calculate zoom needed to fit content
        zoom_x = view_width / content_width if content_width > 0 else 1.0
        zoom_y = view_height / content_height if content_height > 0 else 1.0
        min_zoom_for_content = min(zoom_x, zoom_y)

        # Return the lower of default MIN_ZOOM or content-based minimum
        # but never below ABSOLUTE_MIN_ZOOM
        return max(self.ABSOLUTE_MIN_ZOOM, min(self.MIN_ZOOM, min_zoom_for_content))

    # -------------------------------------------------------------------------
    # Grid and Snapping
    # -------------------------------------------------------------------------

    def toggle_grid(self, show: bool = None):
        """Toggle grid visibility or set explicitly."""
        if show is None:
            self._show_grid = not self._show_grid
        else:
            self._show_grid = show
        # Clear cache to redraw background
        self.resetCachedContent()
        self.viewport().update()

    def set_show_grid(self, show: bool):
        """Set grid visibility."""
        if self._show_grid != show:
            self._show_grid = show
            self.resetCachedContent()
            self.viewport().update()

    def is_grid_visible(self) -> bool:
        """Check if grid is visible."""
        return self._show_grid

    def set_snap_to_grid(self, snap: bool):
        """Enable/disable grid snapping."""
        self._snap_to_grid = snap

    def toggle_snap_to_grid(self, snap: bool = None):
        """Toggle or set grid snapping."""
        if snap is None:
            self._snap_to_grid = not self._snap_to_grid
        else:
            self._snap_to_grid = snap

    def is_snap_to_grid(self) -> bool:
        """Check if grid snapping is enabled."""
        return self._snap_to_grid

    def set_snap_to_neighbors(self, snap: bool):
        """Enable/disable automatic neighbor snapping."""
        self._snap_to_neighbors = snap

    def toggle_snap_to_neighbors(self, snap: bool = None):
        """Toggle or set neighbor snapping."""
        if snap is None:
            self._snap_to_neighbors = not self._snap_to_neighbors
        else:
            self._snap_to_neighbors = snap

    def is_snap_to_neighbors(self) -> bool:
        """Check if neighbor snapping is enabled."""
        return self._snap_to_neighbors

    def snap_position_to_grid(self, pos: QPointF) -> QPointF:
        """
        Snap a position to the grid.

        Args:
            pos: The position to snap

        Returns:
            The snapped position
        """
        if not self._snap_to_grid:
            return pos

        x = round(pos.x() / self.GRID_SIZE) * self.GRID_SIZE
        y = round(pos.y() / self.GRID_SIZE) * self.GRID_SIZE
        return QPointF(x, y)

    def snap_to_neighbor_items(self, item: QGraphicsItem, pos: QPointF,
                                threshold: float = 15) -> QPointF:
        """
        Snap an item to nearby items (edge-to-edge snapping).

        Args:
            item: The item being moved
            pos: Proposed position
            threshold: Snap distance in screen pixels (scaled by zoom)

        Returns:
            Snapped position
        """
        if not self._snap_to_neighbors:
            return pos

        # Scale threshold by zoom level to maintain consistent screen distance
        # At 100% zoom, threshold is 15. At 50%, it's 30 scene units (still 15 screen px)
        zoom_level = self.transform().m11()
        if zoom_level > 0:
            threshold = threshold / zoom_level

        # Get item's bounds at proposed position
        item_rect = item.boundingRect()
        proposed_rect = QRectF(
            pos.x() + item_rect.x(),
            pos.y() + item_rect.y(),
            item_rect.width(),
            item_rect.height()
        )

        # Find snap targets using spatial query instead of iterating all scene items
        snap_x = None
        snap_y = None
        min_dx = threshold
        min_dy = threshold

        search_rect = proposed_rect.adjusted(-threshold, -threshold, threshold, threshold)
        for other in self._scene.items(search_rect):
            if other == item or not isinstance(other, (ImageNode, StickyNote, GroupRegion)):
                continue

            other_rect = other.sceneBoundingRect()

            # Check horizontal snaps (left-to-left, right-to-right, left-to-right, right-to-left)
            # Left edge to left edge
            dx = abs(proposed_rect.left() - other_rect.left())
            if dx < min_dx:
                min_dx = dx
                snap_x = other_rect.left() - item_rect.x()

            # Right edge to right edge
            dx = abs(proposed_rect.right() - other_rect.right())
            if dx < min_dx:
                min_dx = dx
                snap_x = other_rect.right() - item_rect.width() - item_rect.x()

            # Left edge to right edge (with gap)
            dx = abs(proposed_rect.left() - other_rect.right())
            if dx < min_dx:
                min_dx = dx
                snap_x = other_rect.right() - item_rect.x()

            # Right edge to left edge (with gap)
            dx = abs(proposed_rect.right() - other_rect.left())
            if dx < min_dx:
                min_dx = dx
                snap_x = other_rect.left() - item_rect.width() - item_rect.x()

            # Check vertical snaps (top-to-top, bottom-to-bottom, top-to-bottom, bottom-to-top)
            # Top edge to top edge
            dy = abs(proposed_rect.top() - other_rect.top())
            if dy < min_dy:
                min_dy = dy
                snap_y = other_rect.top() - item_rect.y()

            # Bottom edge to bottom edge
            dy = abs(proposed_rect.bottom() - other_rect.bottom())
            if dy < min_dy:
                min_dy = dy
                snap_y = other_rect.bottom() - item_rect.height() - item_rect.y()

            # Top edge to bottom edge
            dy = abs(proposed_rect.top() - other_rect.bottom())
            if dy < min_dy:
                min_dy = dy
                snap_y = other_rect.bottom() - item_rect.y()

            # Bottom edge to top edge
            dy = abs(proposed_rect.bottom() - other_rect.top())
            if dy < min_dy:
                min_dy = dy
                snap_y = other_rect.top() - item_rect.height() - item_rect.y()

        # Apply snaps
        result = QPointF(pos)
        if snap_x is not None:
            result.setX(snap_x)
        if snap_y is not None:
            result.setY(snap_y)

        return result

    # -------------------------------------------------------------------------
    # Dynamic Scene Expansion
    # -------------------------------------------------------------------------

    def _expand_scene_if_needed(self):
        """
        Expand the scene if the viewport is approaching the edges.

        This enables truly infinite panning by dynamically growing the scene
        as the user pans towards any edge.
        """
        # Get the currently visible area in scene coordinates
        visible_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        current_scene = self._scene.sceneRect()

        # Check if we're within the expansion threshold of any edge
        threshold = self.SCENE_EXPANSION_MARGIN / 2  # Expand when halfway to edge
        margin = self.SCENE_EXPANSION_MARGIN

        needs_expansion = False
        new_rect = QRectF(current_scene)

        # Check each edge
        if visible_rect.left() < current_scene.left() + threshold:
            new_rect.setLeft(current_scene.left() - margin)
            needs_expansion = True

        if visible_rect.right() > current_scene.right() - threshold:
            new_rect.setRight(current_scene.right() + margin)
            needs_expansion = True

        if visible_rect.top() < current_scene.top() + threshold:
            new_rect.setTop(current_scene.top() - margin)
            needs_expansion = True

        if visible_rect.bottom() > current_scene.bottom() - threshold:
            new_rect.setBottom(current_scene.bottom() + margin)
            needs_expansion = True

        if needs_expansion:
            self._scene.setSceneRect(new_rect)
            logger.debug(f"Scene expanded during pan to: {new_rect}")

    def _ensure_scene_contains(self, rect: QRectF):
        """
        Ensure the scene rect contains the given rectangle.

        Expands the scene dynamically as needed.

        Args:
            rect: The rectangle that must be contained
        """
        current = self._scene.sceneRect()

        # Check if expansion is needed
        if current.contains(rect):
            return

        # Expand in each direction as needed
        new_rect = current
        margin = self.SCENE_EXPANSION_MARGIN

        if rect.left() < current.left():
            new_rect.setLeft(rect.left() - margin)
        if rect.right() > current.right():
            new_rect.setRight(rect.right() + margin)
        if rect.top() < current.top():
            new_rect.setTop(rect.top() - margin)
        if rect.bottom() > current.bottom():
            new_rect.setBottom(rect.bottom() + margin)

        if new_rect != current:
            self._scene.setSceneRect(new_rect)
            logger.debug(f"Scene expanded to: {new_rect}")

    def optimize_scene_bounds(self):
        """
        Optimize scene bounds to fit current content.

        Call this periodically to reclaim unused scene space.
        Note: This is a user-triggered action, not automatic.
        """
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isEmpty():
            # Reset to default large bounds
            self._scene.setSceneRect(-100000, -100000, 200000, 200000)
        else:
            # Add generous margin around items
            margin = self.SCENE_EXPANSION_MARGIN
            self._scene.setSceneRect(items_rect.adjusted(-margin, -margin, margin, margin))

    def fit_selection(self):
        """Fit selected items in view."""
        selected = self._scene.selectedItems()
        if selected:
            rect = QRectF()
            for item in selected:
                rect = rect.united(item.sceneBoundingRect())
            if not rect.isEmpty():
                self.fitInView(rect.adjusted(-50, -50, 50, 50), Qt.KeepAspectRatio)
                self._current_zoom = self.transform().m11()
                self.zoom_changed.emit(self._current_zoom)
                self._update_brush_indicator_for_zoom()

    def center_on_item(self, item_id: str):
        """Center view on a specific item."""
        node = self._image_nodes.get(item_id)
        if node:
            self.centerOn(node)

    # -------------------------------------------------------------------------
    # Selection
    # -------------------------------------------------------------------------

    def _on_selection_changed(self):
        """Handle scene selection change."""
        selected = self._scene.selectedItems()
        self.selection_changed.emit(selected)

    def get_selected_images(self) -> List[ImageNode]:
        """Get list of selected image nodes."""
        return [item for item in self._scene.selectedItems()
                if isinstance(item, ImageNode)]

    def select_all(self):
        """Select all items."""
        for item in self._scene.items():
            item.setSelected(True)

    def clear_selection(self):
        """Clear selection."""
        self._scene.clearSelection()

    def delete_selected(self):
        """Delete all selected items."""
        for item in list(self._scene.selectedItems()):
            if isinstance(item, ImageNode):
                for nid, node in list(self._image_nodes.items()):
                    if node == item:
                        self.remove_image(nid)
                        break
            elif isinstance(item, ConnectionLine):
                for cid, conn in list(self._connections.items()):
                    if conn == item:
                        self.remove_connection(cid)
                        break
            elif isinstance(item, StickyNote):
                for sid, note in list(self._sticky_notes.items()):
                    if note == item:
                        self.remove_sticky_note(sid)
                        break
            elif isinstance(item, GroupRegion):
                for gid, group in list(self._groups.items()):
                    if group == item:
                        self.remove_group(gid)
                        break
            elif isinstance(item, (DrawingPath, DrawingRect, DrawingEllipse, DrawingLine)):
                for did, drawing in list(self._drawings.items()):
                    if drawing == item:
                        self.remove_drawing(did)
                        break

    # -------------------------------------------------------------------------
    # Context Menu
    # -------------------------------------------------------------------------

    def contextMenuEvent(self, event):
        """Show context menu."""
        # Check if clicking on an item
        pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(pos, self.transform())

        if item:
            # Let the item handle its own context menu
            super().contextMenuEvent(event)
            return

        # Canvas context menu (empty space)
        menu = QMenu(self)

        paste_action = menu.addAction("Paste Image (Ctrl+V)")
        paste_action.triggered.connect(lambda: self._paste_image(scene_pos=pos))

        menu.addSeparator()

        add_note_action = menu.addAction("Add Sticky Note")
        add_note_action.triggered.connect(
            lambda: self.add_sticky_note(pos.x(), pos.y())
        )

        menu.addSeparator()

        fit_all_action = menu.addAction("Fit All")
        fit_all_action.triggered.connect(self.fit_all)

        menu.exec_(event.globalPos())

    def _paste_image(self, scene_pos: QPointF = None):
        """Paste image from clipboard.

        Handles: raw image data (screenshots, copy-image), local file URLs,
        and HTTP image URLs. Saves to gallery folder and adds to canvas.

        Args:
            scene_pos: Scene position to place the image. If None, uses center of view.
        """
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        if scene_pos is None:
            scene_pos = self.mapToScene(self.viewport().rect().center())

        data = extract_browser_image_data(mime)

        if data["type"] == "image_data":
            # Raw image data (screenshots, browser "Copy image")
            save_dir = self._get_gallery_save_dir()
            if not save_dir:
                logger.warning("Cannot paste image: no gallery directory configured")
                return

            saved_path = save_image_data_to_file(
                data["image"], save_dir, generate_image_filename(prefix="canvas_paste")
            )
            if saved_path:
                self.add_image(saved_path, scene_pos.x(), scene_pos.y())
                self.files_dropped_on_canvas.emit([saved_path])
                logger.info(f"Pasted clipboard image to canvas")

        elif data["type"] == "local_files":
            # Local file URLs from clipboard
            from drag_drop import get_file_category
            offset = 0
            added_paths = []
            for path in data["local_paths"]:
                category = get_file_category(path)
                if category == 'image':
                    self.add_image(path, scene_pos.x() + offset, scene_pos.y() + offset)
                    added_paths.append(path)
                    offset += 50
                elif category == 'video':
                    self.add_video(path, scene_pos.x() + offset, scene_pos.y() + offset)
                    added_paths.append(path)
                    offset += 50
            if added_paths:
                self.files_dropped_on_canvas.emit(added_paths)

        elif data["type"] == "url":
            # HTTP URL — download in background
            save_dir = self._get_gallery_save_dir()
            if not save_dir:
                logger.warning("Cannot paste URL image: no gallery directory configured")
                return

            for url in data["urls"]:
                self._download_and_add_image(url, save_dir, scene_pos)

    # -------------------------------------------------------------------------
    # Keyboard Shortcuts
    # -------------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts."""
        key = event.key()
        modifiers = event.modifiers()

        # Skip shortcuts when editing text
        if self._editing_text:
            super().keyPressEvent(event)
            return

        # Space key for temporary pan mode (Photoshop-style)
        if key == Qt.Key_Space and not modifiers:
            # Ctrl+Space is fit all, so only handle plain Space
            if not self._space_pressed:
                self._space_pressed = True
                self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return

        # Delete selected
        if key == Qt.Key_Delete:
            self.delete_selected()
            return

        # Select all (Ctrl+A)
        if key == Qt.Key_A and modifiers & Qt.ControlModifier:
            self.select_all()
            return

        # Undo (Ctrl+Z)
        if key == Qt.Key_Z and modifiers == Qt.ControlModifier:
            if hasattr(self, '_undo_stack') and self._undo_stack:
                self._undo_stack.undo()
            return

        # Redo (Ctrl+Y or Ctrl+Shift+Z)
        if key == Qt.Key_Y and modifiers & Qt.ControlModifier:
            if hasattr(self, '_undo_stack') and self._undo_stack:
                self._undo_stack.redo()
            return
        if key == Qt.Key_Z and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
            if hasattr(self, '_undo_stack') and self._undo_stack:
                self._undo_stack.redo()
            return

        # Paste image (Ctrl+V)
        if key == Qt.Key_V and modifiers == Qt.ControlModifier:
            # Paste at mouse position if cursor is over the canvas, else center of view
            from PySide6.QtGui import QCursor
            global_pos = QCursor.pos()
            local_pos = self.viewport().mapFromGlobal(global_pos)
            if self.viewport().rect().contains(local_pos):
                scene_pos = self.mapToScene(local_pos)
            else:
                scene_pos = self.mapToScene(self.viewport().rect().center())
            self._paste_image(scene_pos=scene_pos)
            return

        # Fit all (Ctrl+Space)
        if key == Qt.Key_Space and modifiers & Qt.ControlModifier:
            self.fit_all()
            return

        # Reset zoom to 100% (Ctrl+0)
        if key == Qt.Key_0 and modifiers & Qt.ControlModifier:
            self.set_zoom_level(1.0)
            return

        # Reset view to origin (Home)
        if key == Qt.Key_Home:
            self.reset_view()
            return

        # Optimize canvas (Ctrl+Shift+O)
        if key == Qt.Key_O and modifiers & (Qt.ControlModifier | Qt.ShiftModifier):
            self.optimize_scene_bounds()
            return

        # Toggle grid (G)
        if key == Qt.Key_G and not modifiers:
            self.toggle_grid()
            return

        # Zoom in (+/=)
        if key in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_in()
            return

        # Zoom out (-)
        if key == Qt.Key_Minus:
            self.zoom_out()
            return

        # Color sampler (S key held)
        if key == Qt.Key_S and not modifiers:
            self._is_sampling_color = True
            self.setCursor(Qt.CrossCursor)
            self.show_color_history_panel()
            return

        # Tool shortcuts (toggle behavior - press again to return to select)
        # Note: Pan mode (H key) removed - use Space+drag instead (Photoshop-style)
        if key == Qt.Key_V and not modifiers:
            self.set_tool('select')
            return
        if key == Qt.Key_C and not modifiers:
            # Toggle connect mode
            self.set_tool('select' if self._current_tool == 'connect' else 'connect')
            return
        if key == Qt.Key_N and not modifiers:
            # Toggle annotate mode
            self.set_tool('select' if self._current_tool == 'annotate' else 'annotate')
            return
        if key == Qt.Key_D and not modifiers:
            # Enter drawing mode (pen tool) - only exits via V key
            if self._current_tool not in ('pen', 'rect', 'ellipse', 'line', 'eraser', 'select_drawings'):
                self.set_tool('pen')
            return
        if key == Qt.Key_E and not modifiers:
            # Enter eraser mode - only exits via V key
            if self._current_tool != 'eraser':
                self.set_tool('eraser')
            return
        if key == Qt.Key_P and not modifiers:
            # Pen tool
            self.set_tool('pen')
            return
        if key == Qt.Key_L and not modifiers:
            # Line tool
            self.set_tool('line')
            return
        if key == Qt.Key_U and not modifiers:
            # Rectangle (U for "rect" since R is rotate)
            self.set_tool('rect')
            return
        if key == Qt.Key_O and not modifiers:
            # Ellipse/Oval tool
            self.set_tool('ellipse')
            return

        # Brush size shortcuts ([ / ] like Photoshop) when in drawing mode
        if self._current_tool in ('pen', 'eraser'):
            if key == Qt.Key_BracketLeft:
                new_size = max(1, self._drawing_width - 1)
                self.set_drawing_width(new_size)
                if self._drawing_toolbar:
                    self._drawing_toolbar.set_brush_size(new_size)
                return
            if key == Qt.Key_BracketRight:
                new_size = min(50, self._drawing_width + 1)
                self.set_drawing_width(new_size)
                if self._drawing_toolbar:
                    self._drawing_toolbar.set_brush_size(new_size)
                return

        # Image manipulation shortcuts (when images selected)
        selected_images = self.get_selected_images()
        if selected_images:
            # Rotate 90° CW (R)
            if key == Qt.Key_R and not modifiers:
                for img in selected_images:
                    img.rotate(90)
                return

            # Rotate 90° CCW (Shift+R)
            if key == Qt.Key_R and modifiers & Qt.ShiftModifier:
                for img in selected_images:
                    img.rotate(-90)
                return

            # Flip horizontal (F)
            if key == Qt.Key_F and not modifiers:
                for img in selected_images:
                    img.flip_horizontal()
                return

            # Flip vertical (Shift+F)
            if key == Qt.Key_F and modifiers & Qt.ShiftModifier:
                for img in selected_images:
                    img.flip_vertical()
                return

            # Decrease opacity ([)
            if key == Qt.Key_BracketLeft:
                for img in selected_images:
                    img.adjust_opacity(-0.1)
                return

            # Increase opacity (])
            if key == Qt.Key_BracketRight:
                for img in selected_images:
                    img.adjust_opacity(0.1)
                return

            # Toggle grayscale (Shift+G)
            if key == Qt.Key_G and modifiers & Qt.ShiftModifier:
                for img in selected_images:
                    img.toggle_grayscale()
                return

        # Alignment shortcuts (Ctrl+Shift+Arrow)
        selected = self._scene.selectedItems()
        if len(selected) >= 2:
            if key == Qt.Key_Left and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
                self.align_selection('left')
                return
            if key == Qt.Key_Right and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
                self.align_selection('right')
                return
            if key == Qt.Key_Up and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
                self.align_selection('top')
                return
            if key == Qt.Key_Down and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
                self.align_selection('bottom')
                return
            # Auto-arrange (Ctrl+Shift+A)
            if key == Qt.Key_A and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
                self.arrange_selection('grid')
                return

        # Z-Order shortcuts
        selected = self._scene.selectedItems()
        if selected:
            # Bring forward (Ctrl+])
            if key == Qt.Key_BracketRight and modifiers == Qt.ControlModifier:
                self.bring_forward()
                return
            # Send backward (Ctrl+[)
            if key == Qt.Key_BracketLeft and modifiers == Qt.ControlModifier:
                self.send_backward()
                return
            # Bring to front (Ctrl+Shift+])
            if key == Qt.Key_BracketRight and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
                self.bring_to_front()
                return
            # Send to back (Ctrl+Shift+[)
            if key == Qt.Key_BracketLeft and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
                self.send_to_back()
                return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        """Handle key release events."""
        key = event.key()

        # Stop Space+drag pan mode when Space is released
        if key == Qt.Key_Space and self._space_pressed:
            self._space_pressed = False
            # Stop any space-initiated panning
            if self._was_panning_with_space:
                self._is_panning = False
                self._was_panning_with_space = False
            # Restore cursor to match current tool
            self._restore_cursor_for_tool()
            event.accept()
            return

        # Stop color sampling when S is released
        if key == Qt.Key_S and self._is_sampling_color:
            self._is_sampling_color = False
            self.setCursor(Qt.ArrowCursor)
            # Keep history panel visible for a moment
            return

        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        """Reset keyboard state when focus is lost to prevent stuck keys."""
        if self._space_pressed:
            self._space_pressed = False
            if self._was_panning_with_space:
                self._is_panning = False
                self._was_panning_with_space = False
            self._restore_cursor_for_tool()
        if self._is_sampling_color:
            self._is_sampling_color = False
            self.setCursor(Qt.ArrowCursor)
        super().focusOutEvent(event)

    # -------------------------------------------------------------------------
    # Alignment and Auto-Arrange
    # -------------------------------------------------------------------------

    def align_selection(self, alignment: str):
        """
        Align selected items.

        Works on any item types (images, notes, drawings).

        Args:
            alignment: One of 'left', 'right', 'top', 'bottom', 'center_h', 'center_v'
        """
        selected = self._scene.selectedItems()
        if len(selected) < 2:
            return

        # Get bounding boxes
        rects = [(item, item.sceneBoundingRect()) for item in selected]

        if alignment == 'left':
            min_x = min(r.left() for _, r in rects)
            for item, rect in rects:
                item.setX(item.x() + (min_x - rect.left()))

        elif alignment == 'right':
            max_x = max(r.right() for _, r in rects)
            for item, rect in rects:
                item.setX(item.x() + (max_x - rect.right()))

        elif alignment == 'top':
            min_y = min(r.top() for _, r in rects)
            for item, rect in rects:
                item.setY(item.y() + (min_y - rect.top()))

        elif alignment == 'bottom':
            max_y = max(r.bottom() for _, r in rects)
            for item, rect in rects:
                item.setY(item.y() + (max_y - rect.bottom()))

        elif alignment == 'center_h':
            # Horizontal center (align on vertical axis)
            centers = [r.center().x() for _, r in rects]
            avg_center = sum(centers) / len(centers)
            for item, rect in rects:
                item.setX(item.x() + (avg_center - rect.center().x()))

        elif alignment == 'center_v':
            # Vertical center (align on horizontal axis)
            centers = [r.center().y() for _, r in rects]
            avg_center = sum(centers) / len(centers)
            for item, rect in rects:
                item.setY(item.y() + (avg_center - rect.center().y()))

        self._emit_modified()

    def scale_selection_uniform(self, mode: str, target_value: float = None):
        """
        Scale selected images to uniform size, preserving aspect ratio.

        Args:
            mode: 'width', 'height', or 'area'
            target_value: Target value (if None, uses average of selection)
        """
        selected_images = self.get_selected_images()
        if len(selected_images) < 2:
            return

        # Collect current sizes
        sizes = [img.get_size() for img in selected_images]

        if mode == 'width':
            if target_value is None:
                target_value = sum(w for w, h in sizes) / len(sizes)
            for img in selected_images:
                w, h = img.get_size()
                aspect = w / max(1, h)
                new_h = target_value / aspect
                img.set_size(target_value, new_h)

        elif mode == 'height':
            if target_value is None:
                target_value = sum(h for w, h in sizes) / len(sizes)
            for img in selected_images:
                w, h = img.get_size()
                aspect = w / max(1, h)
                new_w = target_value * aspect
                img.set_size(new_w, target_value)

        elif mode == 'area':
            if target_value is None:
                target_value = sum(w * h for w, h in sizes) / len(sizes)
            import math
            for img in selected_images:
                w, h = img.get_size()
                aspect = w / max(1, h)
                # area = w * h, w = aspect * h, so area = aspect * h^2
                new_h = math.sqrt(target_value / aspect)
                new_w = aspect * new_h
                img.set_size(new_w, new_h)

        self._emit_modified()

    def arrange_selection(self, mode: str, gap: float = 10):
        """
        Auto-arrange selected items.

        Args:
            mode: 'grid', 'horizontal', 'vertical', or 'pack'
            gap: Spacing between items
        """
        selected = self._scene.selectedItems()
        if len(selected) < 2:
            return

        # Get bounding boxes and sort by position
        items_with_rects = [(item, item.sceneBoundingRect()) for item in selected]

        if mode == 'horizontal':
            # Arrange in a horizontal row
            items_with_rects.sort(key=lambda x: x[1].left())
            base_y = items_with_rects[0][1].top()
            current_x = items_with_rects[0][1].left()

            for item, rect in items_with_rects:
                item.setX(item.x() + (current_x - rect.left()))
                item.setY(item.y() + (base_y - rect.top()))
                current_x += rect.width() + gap

        elif mode == 'vertical':
            # Arrange in a vertical column
            items_with_rects.sort(key=lambda x: x[1].top())
            base_x = items_with_rects[0][1].left()
            current_y = items_with_rects[0][1].top()

            for item, rect in items_with_rects:
                item.setX(item.x() + (base_x - rect.left()))
                item.setY(item.y() + (current_y - rect.top()))
                current_y += rect.height() + gap

        elif mode == 'grid':
            # Arrange in a grid
            import math
            n = len(items_with_rects)
            cols = int(math.ceil(math.sqrt(n)))

            # Sort by original position
            items_with_rects.sort(key=lambda x: (x[1].top(), x[1].left()))

            # Find max width/height for uniform grid
            max_w = max(r.width() for _, r in items_with_rects)
            max_h = max(r.height() for _, r in items_with_rects)

            start_x = items_with_rects[0][1].left()
            start_y = items_with_rects[0][1].top()

            for i, (item, rect) in enumerate(items_with_rects):
                row = i // cols
                col = i % cols
                target_x = start_x + col * (max_w + gap)
                target_y = start_y + row * (max_h + gap)
                # Center in cell
                offset_x = (max_w - rect.width()) / 2
                offset_y = (max_h - rect.height()) / 2
                item.setX(item.x() + (target_x + offset_x - rect.left()))
                item.setY(item.y() + (target_y + offset_y - rect.top()))

        elif mode == 'pack':
            # Bin packing - simple left-to-right, top-to-bottom
            items_with_rects.sort(key=lambda x: -x[1].height())  # Tallest first

            start_x = items_with_rects[0][1].left()
            start_y = items_with_rects[0][1].top()

            # Simple shelf packing
            shelf_y = start_y
            shelf_height = 0
            current_x = start_x
            max_width = 2000  # Max row width before wrapping

            for item, rect in items_with_rects:
                if current_x + rect.width() > start_x + max_width and current_x != start_x:
                    # Start new shelf
                    shelf_y += shelf_height + gap
                    shelf_height = 0
                    current_x = start_x

                item.setX(item.x() + (current_x - rect.left()))
                item.setY(item.y() + (shelf_y - rect.top()))

                current_x += rect.width() + gap
                shelf_height = max(shelf_height, rect.height())

        self._emit_modified()

    def distribute_selection(self, direction: str):
        """
        Distribute selected items evenly.

        Args:
            direction: 'horizontal' or 'vertical'
        """
        selected = self._scene.selectedItems()
        logger.debug(f"distribute_selection({direction}): {len(selected)} items selected")

        if len(selected) < 3:
            logger.debug("distribute_selection: need at least 3 items")
            return

        # Filter to items with valid (non-empty) bounding rects
        items_with_rects = []
        for item in selected:
            rect = item.sceneBoundingRect()
            if not rect.isEmpty() and rect.width() > 0 and rect.height() > 0:
                items_with_rects.append((item, rect))
            else:
                logger.debug(f"distribute_selection: skipping item with invalid rect: {rect}")

        if len(items_with_rects) < 3:
            logger.debug(f"distribute_selection: only {len(items_with_rects)} items with valid rects")
            return

        if direction == 'horizontal':
            items_with_rects.sort(key=lambda x: x[1].left())
            first_rect = items_with_rects[0][1]
            last_rect = items_with_rects[-1][1]
            total_span = last_rect.right() - first_rect.left()
            total_item_width = sum(r.width() for _, r in items_with_rects)

            if len(items_with_rects) <= 1:
                return
            gap = (total_span - total_item_width) / (len(items_with_rects) - 1)
            logger.debug(f"distribute_selection horizontal: span={total_span}, gap={gap}")

            current_x = first_rect.left()
            for item, rect in items_with_rects:
                item.setX(item.x() + (current_x - rect.left()))
                current_x += rect.width() + gap

        elif direction == 'vertical':
            items_with_rects.sort(key=lambda x: x[1].top())
            first_rect = items_with_rects[0][1]
            last_rect = items_with_rects[-1][1]
            total_span = last_rect.bottom() - first_rect.top()
            total_item_height = sum(r.height() for _, r in items_with_rects)

            if len(items_with_rects) <= 1:
                return
            gap = (total_span - total_item_height) / (len(items_with_rects) - 1)
            logger.debug(f"distribute_selection vertical: span={total_span}, gap={gap}")

            current_y = first_rect.top()
            for item, rect in items_with_rects:
                item.setY(item.y() + (current_y - rect.top()))
                current_y += rect.height() + gap

        self._emit_modified()

    # -------------------------------------------------------------------------
    # Z-Order Control
    # -------------------------------------------------------------------------

    def bring_to_front(self):
        """Move selected items to the top of the z-order."""
        selected = self._scene.selectedItems()
        if not selected:
            return

        # Find current max z-value
        max_z = max(item.zValue() for item in self._scene.items())

        # Set selected items above max
        for i, item in enumerate(selected):
            item.setZValue(max_z + 1 + i)

        self._emit_modified()

    def send_to_back(self):
        """Move selected items to the bottom of the z-order."""
        selected = self._scene.selectedItems()
        if not selected:
            return

        # Find current min z-value (excluding GroupRegion which is always behind)
        min_z = min(item.zValue() for item in self._scene.items()
                    if not isinstance(item, GroupRegion))

        # Set selected items below min
        for i, item in enumerate(selected):
            item.setZValue(min_z - 1 - i)

        self._emit_modified()

    def bring_forward(self):
        """Move selected items one level up in z-order."""
        selected = self._scene.selectedItems()
        if not selected:
            return

        for item in selected:
            item.setZValue(item.zValue() + 1)

        self._emit_modified()

    def send_backward(self):
        """Move selected items one level down in z-order."""
        selected = self._scene.selectedItems()
        if not selected:
            return

        for item in selected:
            current_z = item.zValue()
            # Don't go below GroupRegion z-value (-10)
            item.setZValue(max(-9, current_z - 1))

        self._emit_modified()

    # -------------------------------------------------------------------------
    # State Serialization
    # -------------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """
        Get the current canvas state for saving/sync.

        Returns:
            Dict containing all canvas state
        """
        state = {
            'version': '1.0',
            'viewport': {
                'x': self.horizontalScrollBar().value(),
                'y': self.verticalScrollBar().value(),
                'zoom': self._current_zoom
            },
            'nodes': {},
            'videos': {},
            'connections': [],
            'annotations': [],
            'groups': []
        }

        # Image nodes — snapshot dict to prevent RuntimeError if items change during iteration
        for node_id, node in list(self._image_nodes.items()):
            width, height = node.get_size()
            state['nodes'][node_id] = {
                'x': node.x(),
                'y': node.y(),
                'z': node.zValue(),
                'width': width,
                'height': height,
                'liked': node.is_liked(),
                'path': node.image_path,
                'content_hash': node.content_hash,
                'transform': node.get_transform_state(),
            }

        # Video nodes — snapshot dict
        for node_id, node in list(self._video_nodes.items()):
            width, height = node.get_size()
            state['videos'][node_id] = {
                'x': node.x(),
                'y': node.y(),
                'z': node.zValue(),
                'width': width,
                'height': height,
                'liked': node.is_liked(),
                'path': node.video_path,
                'content_hash': node.content_hash,
            }

        # Connections — snapshot dict
        for conn_id, conn in list(self._connections.items()):
            try:
                source_id = target_id = None
                for nid, node in self._image_nodes.items():
                    if node == conn.source_node:
                        source_id = nid
                    if node == conn.target_node:
                        target_id = nid

                if source_id and target_id:
                    state['connections'].append({
                        'id': conn_id,
                        'from': source_id,
                        'to': target_id,
                        'label': conn.label,
                        'type': conn.connection_type
                    })
            except RuntimeError:
                # Skip orphaned connections where C++ node object was deleted
                logger.warning(f"Skipping orphaned connection {conn_id}")

        # Sticky notes — snapshot dict
        for note_id, note in list(self._sticky_notes.items()):
            state['annotations'].append({
                'id': note_id,
                'type': 'sticky',
                'x': note.x(),
                'y': note.y(),
                'z': note.zValue(),
                'text': note.text,
                'color': note.color_name,
                'font_size': note.font_size
            })

        # Groups — snapshot dict
        for group_id, group in list(self._groups.items()):
            rect = group.rect()
            state['groups'].append({
                'id': group_id,
                'name': group.name,
                'color': group.color_hex,
                'bounds': [group.x(), group.y(), rect.width(), rect.height()],
                'collapsed': group._collapsed,
                'z': group.zValue()
            })

        # Drawings
        state['drawings'] = []
        for drawing_id, drawing in list(self._drawings.items()):
            try:
                drawing_state = drawing.get_state()
                drawing_state['id'] = drawing_id
                drawing_state['z'] = drawing.zValue()
                state['drawings'].append(drawing_state)

                # Debug logging
                if drawing_state.get('type') == 'path':
                    points_count = len(drawing_state.get('points', []))
                    logger.debug(f"Saving drawing {drawing_id}: type=path, points={points_count}")
            except Exception as e:
                logger.warning(f"Failed to serialize drawing {drawing_id}: {e}")

        return state

    def _restore_drawing(self, drawing_data: dict):
        """
        Restore a drawing item from serialized state.

        Args:
            drawing_data: Dict containing drawing state from get_state()
        """
        from .canvas_drawing import DrawingPath, DrawingRect, DrawingEllipse, DrawingLine

        drawing_type = drawing_data.get('type')
        drawing_id = drawing_data.get('id', f"drawing_{uuid.uuid4().hex[:8]}")

        # Map drawing types to their classes
        drawing_classes = {
            'path': DrawingPath,
            'rect': DrawingRect,
            'ellipse': DrawingEllipse,
            'line': DrawingLine
        }

        if drawing_type not in drawing_classes:
            logger.warning(f"Unknown drawing type: {drawing_type}")
            return

        try:
            # Create and restore the drawing
            drawing = drawing_classes[drawing_type]()
            drawing.set_state(drawing_data)
            self._scene.addItem(drawing)
            self._drawings[drawing_id] = drawing

            # Restore z-order
            if 'z' in drawing_data:
                drawing.setZValue(drawing_data['z'])

            # Debug logging
            if drawing_type == 'path':
                points_count = len(drawing_data.get('points', []))
                logger.debug(f"Restored drawing {drawing_id}: type={drawing_type}, points={points_count}")
        except Exception as e:
            logger.warning(f"Failed to restore drawing {drawing_id}: {e}")

    def load_state(self, state: Dict[str, Any]):
        """
        Load canvas state from saved/synced data.

        Args:
            state: Dict containing canvas state
        """
        # Suppress canvas_modified signals during load to prevent save loops
        self._loading_state = True

        try:
            # Clear current state
            self.clear()

            # Clear undo stack since we're loading fresh state
            if hasattr(self, '_undo_stack') and self._undo_stack:
                self._undo_stack.clear()

            # Load nodes
            nodes_data = state.get('nodes', {})
            for node_id, node_data in nodes_data.items():
                image_path = node_data.get('path', '')
                content_hash = node_data.get('content_hash')

                # If file doesn't exist, try to find it by hash in the same directory
                if not os.path.exists(image_path) and content_hash:
                    recovered = self._find_file_by_hash(
                        os.path.dirname(image_path), content_hash)
                    if recovered:
                        image_path = recovered
                        logger.info(f"Canvas: recovered moved file by hash: {image_path}")

                node = self.add_image(
                    image_path,
                    x=node_data.get('x', 0),
                    y=node_data.get('y', 0),
                    width=node_data.get('width'),
                    height=node_data.get('height'),
                    liked=node_data.get('liked', False),
                    node_id=node_id,
                    content_hash=content_hash,
                )
                if 'z' in node_data:
                    node.setZValue(node_data['z'])
                transform_data = node_data.get('transform', {})
                if transform_data:
                    node.set_transform_state(transform_data)

            # Load video nodes
            videos_data = state.get('videos', {})
            for node_id, node_data in videos_data.items():
                video_path = node_data.get('path', '')
                content_hash = node_data.get('content_hash')

                if not os.path.exists(video_path) and content_hash:
                    recovered = self._find_file_by_hash(
                        os.path.dirname(video_path), content_hash)
                    if recovered:
                        video_path = recovered
                        logger.info(f"Canvas: recovered moved video by hash: {video_path}")

                node = self.add_video(
                    video_path,
                    x=node_data.get('x', 0),
                    y=node_data.get('y', 0),
                    width=node_data.get('width'),
                    height=node_data.get('height'),
                    node_id=node_id,
                    content_hash=content_hash,
                )
                node.set_liked(node_data.get('liked', False))
                if 'z' in node_data:
                    node.setZValue(node_data['z'])

            # Load connections
            for conn_data in state.get('connections', []):
                self.add_connection(
                    conn_data.get('from', ''),
                    conn_data.get('to', ''),
                    connection_type=conn_data.get('type', 'manual'),
                    label=conn_data.get('label', ''),
                    connection_id=conn_data.get('id')
                )

            # Load annotations
            for ann_data in state.get('annotations', []):
                if ann_data.get('type') == 'sticky':
                    note = self.add_sticky_note(
                        ann_data.get('x', 0),
                        ann_data.get('y', 0),
                        text=ann_data.get('text', ''),
                        color=ann_data.get('color', 'yellow'),
                        font_size=ann_data.get('font_size', 10),
                        note_id=ann_data.get('id')
                    )
                    if 'z' in ann_data:
                        note.setZValue(ann_data['z'])

            # Load groups
            for group_data in state.get('groups', []):
                bounds = group_data.get('bounds', [0, 0, 200, 150])
                group = self.add_group(
                    bounds[0], bounds[1], bounds[2], bounds[3],
                    name=group_data.get('name', 'Group'),
                    color=group_data.get('color', '#ff6b6b'),
                    group_id=group_data.get('id')
                )
                if group_data.get('collapsed', False):
                    group._toggle_collapse()
                if 'z' in group_data:
                    group.setZValue(group_data['z'])

            # Load drawings
            drawings_data = state.get('drawings', [])
            logger.debug(f"load_state: loading {len(drawings_data)} drawings")
            for drawing_data in drawings_data:
                if drawing_data.get('type') == 'path':
                    pts = drawing_data.get('points', [])
                    logger.debug(f"load_state: path drawing has {len(pts)} points")
                self._restore_drawing(drawing_data)

            # Restore viewport
            viewport = state.get('viewport', {})
            if 'zoom' in viewport:
                self.resetTransform()
                self.scale(viewport['zoom'], viewport['zoom'])
                self._current_zoom = viewport['zoom']
            if 'x' in viewport:
                self.horizontalScrollBar().setValue(viewport['x'])
            if 'y' in viewport:
                self.verticalScrollBar().setValue(viewport['y'])

        finally:
            # Re-enable canvas_modified signals
            self._loading_state = False

    def load_state_with_preloaded_images(
        self,
        state: Dict[str, Any],
        preloaded_images: Dict[str, QImage]
    ):
        """
        Load canvas state using pre-loaded QImage objects.

        This method is called on the main thread after images have been
        pre-loaded in a worker thread as QImage objects (thread-safe).
        QPixmap objects are created here on the main thread as required by Qt.

        Args:
            state: Canvas state dict (nodes, connections, annotations, groups, viewport)
            preloaded_images: Dict mapping node_id to QImage (from worker thread)
        """
        # Suppress canvas_modified signals during load to prevent save loops
        self._loading_state = True

        try:
            # Clear current state
            self.clear()

            # Clear undo stack since we're loading fresh state
            if hasattr(self, '_undo_stack') and self._undo_stack:
                self._undo_stack.clear()

            # Load nodes with pre-loaded images
            nodes_data = state.get('nodes', {})
            for node_id, node_data in nodes_data.items():
                image_path = node_data.get('path', '')
                content_hash = node_data.get('content_hash')

                # If file doesn't exist, try to find it by hash in the same directory
                if not os.path.exists(image_path) and content_hash:
                    recovered = self._find_file_by_hash(
                        os.path.dirname(image_path), content_hash)
                    if recovered:
                        image_path = recovered
                        logger.info(f"Canvas: recovered moved file by hash: {image_path}")

                qimage = preloaded_images.get(node_id)
                node = self.add_image(
                    image_path,
                    x=node_data.get('x', 0),
                    y=node_data.get('y', 0),
                    width=node_data.get('width'),
                    height=node_data.get('height'),
                    liked=node_data.get('liked', False),
                    node_id=node_id,
                    qimage=qimage,  # Use pre-loaded QImage to avoid disk I/O
                    content_hash=content_hash,
                )
                if 'z' in node_data:
                    node.setZValue(node_data['z'])
                transform_data = node_data.get('transform', {})
                if transform_data:
                    node.set_transform_state(transform_data)

            # Load video nodes (thumbnails loaded async, no preloading needed)
            videos_data = state.get('videos', {})
            for node_id, node_data in videos_data.items():
                video_path = node_data.get('path', '')
                content_hash = node_data.get('content_hash')

                if not os.path.exists(video_path) and content_hash:
                    recovered = self._find_file_by_hash(
                        os.path.dirname(video_path), content_hash)
                    if recovered:
                        video_path = recovered

                node = self.add_video(
                    video_path,
                    x=node_data.get('x', 0),
                    y=node_data.get('y', 0),
                    width=node_data.get('width'),
                    height=node_data.get('height'),
                    node_id=node_id,
                    content_hash=content_hash,
                )
                node.set_liked(node_data.get('liked', False))
                if 'z' in node_data:
                    node.setZValue(node_data['z'])

            # Load connections (same as load_state)
            for conn_data in state.get('connections', []):
                self.add_connection(
                    conn_data.get('from', ''),
                    conn_data.get('to', ''),
                    connection_type=conn_data.get('type', 'manual'),
                    label=conn_data.get('label', ''),
                    connection_id=conn_data.get('id')
                )

            # Load annotations (same as load_state)
            for ann_data in state.get('annotations', []):
                if ann_data.get('type') == 'sticky':
                    note = self.add_sticky_note(
                        ann_data.get('x', 0),
                        ann_data.get('y', 0),
                        text=ann_data.get('text', ''),
                        color=ann_data.get('color', 'yellow'),
                        font_size=ann_data.get('font_size', 10),
                        note_id=ann_data.get('id')
                    )
                    if 'z' in ann_data:
                        note.setZValue(ann_data['z'])

            # Load groups (same as load_state)
            for group_data in state.get('groups', []):
                bounds = group_data.get('bounds', [0, 0, 200, 150])
                group = self.add_group(
                    bounds[0], bounds[1], bounds[2], bounds[3],
                    name=group_data.get('name', 'Group'),
                    color=group_data.get('color', '#ff6b6b'),
                    group_id=group_data.get('id')
                )
                if group_data.get('collapsed', False):
                    group._toggle_collapse()
                if 'z' in group_data:
                    group.setZValue(group_data['z'])

            # Load drawings (same as load_state)
            drawings_data = state.get('drawings', [])
            logger.debug(f"load_state_with_preloaded_images: loading {len(drawings_data)} drawings")
            for drawing_data in drawings_data:
                if drawing_data.get('type') == 'path':
                    pts = drawing_data.get('points', [])
                    logger.debug(f"load_state_with_preloaded_images: path drawing has {len(pts)} points")
                self._restore_drawing(drawing_data)

            # Restore viewport (same as load_state)
            viewport = state.get('viewport', {})
            if 'zoom' in viewport:
                self.resetTransform()
                self.scale(viewport['zoom'], viewport['zoom'])
                self._current_zoom = viewport['zoom']
            if 'x' in viewport:
                self.horizontalScrollBar().setValue(viewport['x'])
            if 'y' in viewport:
                self.verticalScrollBar().setValue(viewport['y'])

        finally:
            # Re-enable canvas_modified signals
            self._loading_state = False

    def clear(self):
        """Clear all items from the canvas."""
        # Deactivate video players before clearing
        self.deactivate_all_videos()

        # Clear tracking dicts
        self._image_nodes.clear()
        self._video_nodes.clear()
        self._connections.clear()
        self._sticky_notes.clear()
        self._groups.clear()
        self._drawings.clear()
        self._remote_cursors.clear()  # Also clear remote cursors (they'll be recreated)

        # Clear scene (this deletes all items including brush indicator)
        self._scene.clear()

        # Recreate brush indicator (it was deleted with scene.clear())
        self._ensure_brush_indicator()

    # -------------------------------------------------------------------------
    # Accessors
    # -------------------------------------------------------------------------

    def get_image_node(self, node_id: str) -> Optional[ImageNode]:
        """Get an image node by ID."""
        return self._image_nodes.get(node_id)

    def get_all_image_nodes(self) -> Dict[str, ImageNode]:
        """Get all image nodes."""
        return dict(self._image_nodes)

    def get_video_node(self, node_id: str) -> Optional['VideoNode']:
        """Get a video node by ID."""
        return self._video_nodes.get(node_id)

    def get_all_video_nodes(self) -> Dict[str, 'VideoNode']:
        """Get all video nodes."""
        return dict(self._video_nodes)

    def get_zoom_level(self) -> float:
        """Get current zoom level."""
        return self._current_zoom

    def set_zoom_level(self, zoom: float):
        """
        Set zoom level directly (1.0 = 100%).

        Args:
            zoom: Zoom level where 1.0 = 100%, 0.5 = 50%, 2.0 = 200%
        """
        # Use dynamic minimum based on content bounds
        min_zoom = self._get_content_min_zoom()
        zoom = max(min_zoom, min(self.MAX_ZOOM, zoom))
        if abs(zoom - self._current_zoom) < 0.001:
            return  # No change needed

        # Reset transform and apply new zoom
        self.resetTransform()
        self.scale(zoom, zoom)
        self._current_zoom = zoom
        self.zoom_changed.emit(self._current_zoom)
        self._update_brush_indicator_for_zoom()

    def set_zoom(self, zoom: float):
        """
        Set zoom level (alias for set_zoom_level).

        Args:
            zoom: Zoom level where 1.0 = 100%
        """
        self.set_zoom_level(zoom)

    def _find_file_by_hash(self, directory: str, expected_hash: str) -> Optional[str]:
        """
        Search a directory for a file matching the expected content hash.

        Used to recover files that have been renamed but remain in the same directory.

        Args:
            directory: Directory to search in
            expected_hash: SHA-256 hash to match

        Returns:
            Path to the matching file, or None
        """
        if not directory or not expected_hash or not os.path.isdir(directory):
            return None

        try:
            from comfyui.utils import compute_file_hash
            from core.config import GALLERY_SUPPORTED_EXTENSIONS
        except ImportError:
            return None

        try:
            MAX_HASH_FILES = 50
            files_checked = 0
            for entry in os.scandir(directory):
                if files_checked >= MAX_HASH_FILES:
                    break
                if not entry.is_file():
                    continue
                ext = os.path.splitext(entry.name)[1].lower()
                if ext not in GALLERY_SUPPORTED_EXTENSIONS:
                    continue
                file_hash = compute_file_hash(entry.path)
                files_checked += 1
                if file_hash == expected_hash:
                    return os.path.normpath(entry.path)
        except Exception as e:
            logger.debug(f"Error searching for file by hash in {directory}: {e}")

        return None

    def find_node_by_file_id(self, file_id: str) -> Optional[ImageNode]:
        """
        Find an image node by its file_id (from metadata).

        Args:
            file_id: The file_id to search for

        Returns:
            The ImageNode if found, else None
        """
        # file_id might be the node_id or part of the path
        for node_id, node in self._image_nodes.items():
            if node_id == file_id:
                return node
            # Also check if file_id matches the filename
            if os.path.basename(node.image_path) == file_id:
                return node

        # Fallback: check content_hash
        for node_id, node in self._image_nodes.items():
            if node.content_hash and node.content_hash == file_id:
                return node
        return None

    # -------------------------------------------------------------------------
    # Remote Cursor Display
    # -------------------------------------------------------------------------

    def update_remote_cursors(self, cursors: Dict[str, dict]):
        """
        Update display of remote user cursors.

        Args:
            cursors: Dict of {username: {x, y, color, timestamp}}
        """
        # Remove cursors for users who are no longer present
        for username in list(self._remote_cursors.keys()):
            if username not in cursors:
                cursor_item = self._remote_cursors.pop(username)
                self._scene.removeItem(cursor_item)

        # Update or create cursors for active users
        for username, data in cursors.items():
            if username in self._remote_cursors:
                try:
                    cursor_item = self._remote_cursors[username]
                    # Update existing cursor position
                    cursor_item.setPos(data['x'], data['y'])
                except RuntimeError:
                    # C++ object was deleted (e.g., by scene.clear())
                    # Remove stale reference and recreate
                    self._remote_cursors.pop(username, None)
                    cursor_item = CursorItem(username, data['color'])
                    cursor_item.setPos(data['x'], data['y'])
                    self._scene.addItem(cursor_item)
                    self._remote_cursors[username] = cursor_item
            else:
                # Create new cursor item
                cursor_item = CursorItem(username, data['color'])
                cursor_item.setPos(data['x'], data['y'])
                self._scene.addItem(cursor_item)
                self._remote_cursors[username] = cursor_item

    # -------------------------------------------------------------------------
    # Gallery Integration Methods
    # -------------------------------------------------------------------------

    def _get_favorites_manager(self):
        """
        Get the FavoritesManager from the gallery tab.

        NOTE: This is a direct tab access for READ-ONLY data queries.
        This is acceptable because:
        - The canvas needs to query group colors and liked status for node styling
        - These are data reads, not actions (event bus is for actions)
        - The canvas listens to favorites_changed events to know when to re-query

        For a more decoupled architecture, FavoritesManager could be a shared
        service rather than owned by gallery_tab.

        Returns:
            FavoritesManager instance, or None if not available
        """
        if not self._tab:
            return None

        try:
            main_window = self._tab.main_window
            if not main_window:
                return None

            # Get gallery tab via main_window.get_tab() or tabs dict
            gallery_tab = None
            if hasattr(main_window, 'get_tab'):
                gallery_tab = main_window.get_tab('gallery')
            elif hasattr(main_window, 'tabs'):
                gallery_tab = main_window.tabs.get('gallery')

            if gallery_tab and hasattr(gallery_tab, '_favorites_manager'):
                return gallery_tab._favorites_manager
        except Exception as e:
            logger.debug(f"Could not get favorites manager: {e}")

        return None

    def _show_in_gallery(self, image_path: str):
        """
        Show an image in the gallery tab and navigate to it.

        Uses event bus for cross-tab communication.

        Args:
            image_path: Path to the image file
        """
        try:
            from core.event_bus import pipeline_events
            pipeline_events.gallery_navigate_to.emit(image_path)
        except ImportError:
            # Fallback to direct access if event bus unavailable
            if not self._tab:
                logger.warning("No tab reference, cannot show in gallery")
                return

            try:
                main_window = self._tab.main_window
                if not main_window:
                    return

                gallery_tab = None
                if hasattr(main_window, 'get_tab'):
                    gallery_tab = main_window.get_tab('gallery')

                if gallery_tab and hasattr(gallery_tab, 'select_and_scroll_to_item'):
                    if hasattr(main_window, 'select_tab_by_name'):
                        main_window.select_tab_by_name('gallery')
                    gallery_tab.select_and_scroll_to_item(image_path)
            except Exception as e:
                logger.warning(f"Could not navigate to gallery: {e}")

            logger.info(f"Showing in gallery: {image_path}")

        except Exception as e:
            logger.error(f"Failed to show in gallery: {e}")

    def _show_properties(self, image_path: str):
        """
        Show the properties dialog for an image.

        Args:
            image_path: Path to the image file
        """
        try:
            from properties_dialog import PropertiesDialog
            from core.state_manager import app_state

            parent_widget = self._tab.main_window if self._tab else None
            dialog = PropertiesDialog(
                image_path,
                parent=parent_widget,
                show_comfyui_features=app_state.has_elevated_access
            )
            dialog.exec_()

        except Exception as e:
            logger.error(f"Failed to show properties dialog: {e}")

    def sync_all_from_gallery(self):
        """
        Sync all image and video nodes from the gallery FavoritesManager.

        Call this after loading canvas state or when gallery data changes.
        """
        favorites_manager = self._get_favorites_manager()
        if not favorites_manager:
            return

        for node in self._image_nodes.values():
            node.sync_from_gallery(favorites_manager)

        for node in self._video_nodes.values():
            node.sync_from_gallery(favorites_manager)

        logger.debug("Synced all canvas nodes from gallery")

    def sync_node_from_gallery(self, media_path: str):
        """
        Sync a specific node from gallery.

        Args:
            media_path: Path of the node to sync
        """
        favorites_manager = self._get_favorites_manager()
        if not favorites_manager:
            return

        # Find node by exact path match first (images then videos)
        for node_id, node in self._image_nodes.items():
            if node.image_path == media_path:
                node.sync_from_gallery(favorites_manager)
                return

        for node_id, node in self._video_nodes.items():
            if node.video_path == media_path:
                node.sync_from_gallery(favorites_manager)
                return

        # Fallback: try hash-based match
        try:
            from comfyui.utils import compute_file_hash
            target_hash = compute_file_hash(media_path)
            if target_hash:
                for node_id, node in self._image_nodes.items():
                    if node.content_hash and node.content_hash == target_hash:
                        node.sync_from_gallery(favorites_manager)
                        return
                for node_id, node in self._video_nodes.items():
                    if node.content_hash and node.content_hash == target_hash:
                        node.sync_from_gallery(favorites_manager)
                        return
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Color Sampler
    # -------------------------------------------------------------------------

    def _sample_color_at(self, scene_pos: QPointF) -> Optional[QColor]:
        """
        Sample RGB color from image at position (ignores alpha).

        Args:
            scene_pos: Position in scene coordinates

        Returns:
            QColor if an image is at the position, else None
        """
        # Find image node at position
        item = self._scene.itemAt(scene_pos, self.transform())
        if not isinstance(item, ImageNode):
            return None

        # Get local position in image
        local_pos = item.mapFromScene(scene_pos)

        # Get the pixmap
        pixmap = item._pixmap
        if not pixmap or pixmap.isNull():
            return None

        # Convert local position to image coordinates
        # Account for the item's current size vs original image size
        width, height = item.get_size()
        img_x = int(local_pos.x() / width * pixmap.width())
        img_y = int(local_pos.y() / height * pixmap.height())

        # Clamp to image bounds
        img_x = max(0, min(pixmap.width() - 1, img_x))
        img_y = max(0, min(pixmap.height() - 1, img_y))

        # Sample color from image
        image = pixmap.toImage()
        pixel = image.pixelColor(img_x, img_y)

        # Return RGB only (ignore alpha)
        return QColor(pixel.red(), pixel.green(), pixel.blue())

    def _show_color_tooltip(self, color: QColor, screen_pos):
        """
        Show tooltip with color information.

        Args:
            color: The sampled color
            screen_pos: Position on screen for tooltip
        """
        # Format color info
        r, g, b = color.red(), color.green(), color.blue()
        h, s, v = color.hue(), color.saturation(), color.value()
        hex_color = color.name().upper()

        tooltip_text = f"""
        <div style='background-color: {hex_color}; padding: 10px; border-radius: 5px;'>
            <span style='color: {"#000" if v > 128 else "#FFF"};'>■■■■■</span>
        </div>
        <br>
        <b>RGB:</b> {r}, {g}, {b}<br>
        <b>HSV:</b> {h}°, {s}, {v}<br>
        <b>HEX:</b> {hex_color}
        """

        QToolTip.showText(screen_pos, tooltip_text, self)

    def _add_to_color_history(self, color: QColor):
        """
        Add color to history (max 5 colors).

        Args:
            color: The color to add
        """
        # Remove if already in history (will re-add at front)
        for i, c in enumerate(self._color_history):
            if c.name() == color.name():
                self._color_history.pop(i)
                break

        # Add at front
        self._color_history.insert(0, color)

        # Keep max 5
        if len(self._color_history) > 5:
            self._color_history.pop()

        # Update history panel if visible
        if self._color_history_panel:
            self._color_history_panel.update_colors(self._color_history)

    def sample_color(self, scene_pos: QPointF, screen_pos):
        """
        Sample color at position and show info.

        Args:
            scene_pos: Position in scene coordinates
            screen_pos: Position on screen for tooltip
        """
        color = self._sample_color_at(scene_pos)
        if color:
            # Show tooltip
            self._show_color_tooltip(color, screen_pos)

            # Copy HEX to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(color.name().upper())

            # Add to history
            self._add_to_color_history(color)

            logger.debug(f"Sampled color: {color.name()}")

    def show_color_history_panel(self):
        """Show the color history panel."""
        if not self._color_history_panel:
            self._color_history_panel = ColorHistoryPanel(self)
            self._color_history_panel.color_selected.connect(self._on_history_color_selected)

        self._color_history_panel.update_colors(self._color_history)

        # Position in top-left corner of the viewport (not screen)
        # Use viewport coordinates for proper positioning within canvas
        self._color_history_panel.move(10, 40)  # Leave room for toolbar
        self._color_history_panel.show()
        self._color_history_panel.raise_()

        # Start auto-hide timer (will hide after 2 seconds unless mouse enters)
        self._color_history_panel.start_auto_hide()

    def hide_color_history_panel(self):
        """Hide the color history panel."""
        if self._color_history_panel:
            self._color_history_panel.hide()

    def _on_history_color_selected(self, color: QColor):
        """Handle color selection from history panel."""
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(color.name().upper())

    def get_color_history(self) -> List[QColor]:
        """Get the color history."""
        return list(self._color_history)

    def clear_color_history(self):
        """Clear the color history."""
        self._color_history.clear()
        if self._color_history_panel:
            self._color_history_panel.update_colors([])


class ColorHistoryPanel(QFrame):
    """
    Floating panel showing the 5-color history.

    Clicking a color copies its HEX to clipboard.
    Positioned as a child widget of the canvas, not a top-level window.
    """

    color_selected = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Use FramelessWindowHint only - keep as child widget, not tool window
        # This ensures it stays within the canvas bounds
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._colors: List[QColor] = []
        self._buttons: List[QPushButton] = []
        self._auto_hide_timer: Optional[QTimer] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the panel UI."""
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(45, 45, 45, 230);
                border: 1px solid #3d3d3d;
                border-radius: 5px;
            }
            QPushButton {
                border: 2px solid #4d4d4d;
                border-radius: 3px;
                min-width: 30px;
                min-height: 30px;
            }
            QPushButton:hover {
                border-color: #4a9eff;
            }
            QLabel {
                color: #aaa;
                font-size: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Title
        title = QLabel("Color History")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Color buttons row
        colors_layout = QHBoxLayout()
        colors_layout.setSpacing(4)

        for i in range(5):
            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setStyleSheet("background-color: #2d2d2d;")
            btn.clicked.connect(lambda checked, idx=i: self._on_color_clicked(idx))
            btn.setToolTip("Click to copy HEX")
            colors_layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addLayout(colors_layout)

    def update_colors(self, colors: List[QColor]):
        """Update the displayed colors."""
        self._colors = list(colors)

        for i, btn in enumerate(self._buttons):
            if i < len(colors):
                color = colors[i]
                btn.setStyleSheet(f"background-color: {color.name()};")
                btn.setToolTip(f"{color.name().upper()}\nClick to copy")
                btn.setEnabled(True)
            else:
                btn.setStyleSheet("background-color: #2d2d2d;")
                btn.setToolTip("")
                btn.setEnabled(False)

    def _on_color_clicked(self, index: int):
        """Handle color button click."""
        if index < len(self._colors):
            self.color_selected.emit(self._colors[index])

    def start_auto_hide(self, delay_ms: int = 2000):
        """Start auto-hide timer.

        Args:
            delay_ms: Delay in milliseconds before hiding (default 2 seconds)
        """
        # Cancel any existing timer
        if self._auto_hide_timer:
            self._auto_hide_timer.stop()
            self._auto_hide_timer = None

        # Start new timer
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)
        self._auto_hide_timer.start(delay_ms)

    def cancel_auto_hide(self):
        """Cancel the auto-hide timer."""
        if self._auto_hide_timer:
            self._auto_hide_timer.stop()
            self._auto_hide_timer = None

    def enterEvent(self, event):
        """Cancel auto-hide when mouse enters the panel."""
        self.cancel_auto_hide()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Restart auto-hide when mouse leaves the panel."""
        self.start_auto_hide()
        super().leaveEvent(event)


class CursorItem(QGraphicsItem):
    """
    Visual representation of a remote user's cursor.

    Shows a colored cursor icon with username on hover.
    """

    CURSOR_SIZE = 20

    def __init__(self, username: str, color: str):
        super().__init__()
        self._username = username
        self._color = QColor(color)

        # Make sure cursor is always on top
        self.setZValue(10000)

        # Enable hover for showing username
        self.setAcceptHoverEvents(True)

        # State
        self._show_name = False

    def boundingRect(self) -> QRectF:
        """Return bounding rect for cursor."""
        return QRectF(-5, -5, self.CURSOR_SIZE + 10, self.CURSOR_SIZE + 30)

    def paint(self, painter, option, widget):
        """Paint the cursor."""
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw cursor arrow shape
        pen = QPen(self._color.darker(150), 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(self._color))

        # Simple arrow shape
        from PySide6.QtGui import QPolygonF
        arrow = QPolygonF([
            QPointF(0, 0),
            QPointF(0, self.CURSOR_SIZE),
            QPointF(self.CURSOR_SIZE * 0.35, self.CURSOR_SIZE * 0.65),
            QPointF(self.CURSOR_SIZE * 0.65, self.CURSOR_SIZE * 0.65),
        ])
        painter.drawPolygon(arrow)

        # Show username on hover or always
        if self._show_name:
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(painter.font())
            painter.drawText(
                QRectF(0, self.CURSOR_SIZE + 2, 100, 20),
                Qt.AlignLeft,
                self._username
            )

    def hoverEnterEvent(self, event):
        """Show username on hover."""
        self._show_name = True
        self.update()

    def hoverLeaveEvent(self, event):
        """Hide username after hover."""
        self._show_name = False
        self.update()
