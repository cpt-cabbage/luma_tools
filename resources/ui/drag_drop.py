"""
Drag and Drop functionality for Luma Tools.

Provides mixins and utilities for enabling drag-and-drop between widgets:
- DraggableMixin: Add drag source capability to widgets
- DropTargetMixin: Add drop target capability to widgets
- Specialized drop handlers for images, videos, 3D models, and file paths

Supported MIME types:
- application/x-luma-files: Internal file paths (images, videos, models)
- text/uri-list: External file drops from file explorer
- text/plain: Fallback for file paths as text
"""
import os
import logging
from typing import List, Optional, Set, Callable

from PySide6.QtCore import Qt, QMimeData, QPoint
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


# ============================================================================
# MIME TYPE CONSTANTS
# ============================================================================

MIME_LUMA_FILES = "application/x-luma-files"
MIME_URI_LIST = "text/uri-list"
MIME_PLAIN_TEXT = "text/plain"

# Supported file extensions by category
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tif', '.exr'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
MODEL_EXTENSIONS = {'.glb', '.gltf', '.obj', '.fbx', '.usd', '.usda', '.usdc', '.usdz', '.ply', '.stl'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.aac'}


def get_file_category(path: str) -> str:
    """Get the category of a file based on its extension.

    Returns: 'image', 'video', 'model', 'audio', or 'unknown'
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    elif ext in MODEL_EXTENSIONS:
        return 'model'
    elif ext in AUDIO_EXTENSIONS:
        return 'audio'
    return 'unknown'


def filter_files_by_category(paths: List[str], categories: Set[str]) -> List[str]:
    """Filter file paths to only include specified categories.

    Args:
        paths: List of file paths
        categories: Set of categories to include ('image', 'video', 'model', 'audio')

    Returns:
        Filtered list of paths
    """
    return [p for p in paths if get_file_category(p) in categories]


# ============================================================================
# MIME DATA UTILITIES
# ============================================================================

def create_file_mime_data(paths: List[str]) -> QMimeData:
    """Create QMimeData for file paths.

    Sets multiple MIME types for maximum compatibility:
    - application/x-luma-files: Our internal format (newline-separated paths)
    - text/uri-list: Standard format for file drops
    - text/plain: Fallback as plain text
    """
    mime_data = QMimeData()

    # Internal format: newline-separated paths
    mime_data.setData(MIME_LUMA_FILES, "\n".join(paths).encode('utf-8'))

    # Standard URI list format
    from PySide6.QtCore import QUrl
    urls = [QUrl.fromLocalFile(p) for p in paths if os.path.exists(p)]
    mime_data.setUrls(urls)

    # Plain text fallback (first path only for simplicity)
    if paths:
        mime_data.setText(paths[0])

    return mime_data


def extract_files_from_mime_data(mime_data: QMimeData) -> List[str]:
    """Extract file paths from QMimeData.

    Tries multiple MIME types in order of preference:
    1. application/x-luma-files (internal format)
    2. text/uri-list (standard file drops)
    3. text/plain (fallback)

    Returns:
        List of valid file paths
    """
    paths = []

    # Try internal format first
    if mime_data.hasFormat(MIME_LUMA_FILES):
        data = mime_data.data(MIME_LUMA_FILES).data().decode('utf-8')
        paths = [p.strip() for p in data.split('\n') if p.strip()]

    # Try URL list (standard file drops)
    elif mime_data.hasUrls():
        for url in mime_data.urls():
            local_path = url.toLocalFile()
            if local_path:
                paths.append(local_path)

    # Try plain text
    elif mime_data.hasText():
        text = mime_data.text().strip()
        if text and os.path.exists(text):
            paths.append(text)

    # Filter to only existing files
    return [p for p in paths if os.path.isfile(p)]


def can_accept_files(mime_data: QMimeData, accepted_categories: Set[str]) -> bool:
    """Check if mime data contains files we can accept.

    Args:
        mime_data: The mime data to check
        accepted_categories: Set of categories we accept ('image', 'video', 'model', 'audio')

    Returns:
        True if at least one acceptable file is present
    """
    paths = extract_files_from_mime_data(mime_data)
    filtered = filter_files_by_category(paths, accepted_categories)
    return len(filtered) > 0


# ============================================================================
# DRAG VISUAL FEEDBACK
# ============================================================================

def create_drag_pixmap(paths: List[str], max_size: int = 80) -> QPixmap:
    """Create a pixmap representing dragged files.

    Shows a thumbnail for single files, or a stack effect for multiple files.
    """
    count = len(paths)

    if count == 0:
        return QPixmap()

    # Base size
    size = max_size

    if count == 1:
        # Single file - try to load thumbnail
        path = paths[0]
        category = get_file_category(path)

        if category == 'image':
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Fallback to icon-style placeholder
        return _create_placeholder_pixmap(category, size)

    else:
        # Multiple files - stack effect
        return _create_stack_pixmap(paths, size)


def _create_placeholder_pixmap(category: str, size: int) -> QPixmap:
    """Create a placeholder pixmap with an icon for the file category."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#2a3040"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Icon based on category
    icons = {
        'image': '🖼',
        'video': '🎬',
        'model': '📦',
        'audio': '🎵',
        'unknown': '📄',
    }

    painter.setPen(QColor("#4a9eff"))
    font = painter.font()
    font.setPointSize(24)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, icons.get(category, '📄'))
    painter.end()

    return pixmap


def _create_stack_pixmap(paths: List[str], size: int) -> QPixmap:
    """Create a stacked pixmap showing multiple files."""
    offset = 4
    stack_count = min(len(paths), 3)
    total_size = size + (stack_count - 1) * offset

    pixmap = QPixmap(total_size, total_size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Draw stacked rectangles
    for i in range(stack_count - 1, -1, -1):
        x = i * offset
        y = i * offset

        # Darker shade for back cards
        shade = 255 - (stack_count - 1 - i) * 30
        painter.setBrush(QColor(42, 48, 64, shade))
        painter.setPen(QColor(74, 109, 140, shade))
        painter.drawRoundedRect(x, y, size, size, 6, 6)

    # Draw count badge
    count = len(paths)
    badge_text = str(count)
    badge_width = max(20, 8 + len(badge_text) * 8)
    badge_x = total_size - badge_width - 4
    badge_y = 4

    painter.setBrush(QColor(74, 158, 255, 220))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(badge_x, badge_y, badge_width, 18, 9, 9)

    painter.setPen(QColor(255, 255, 255))
    font = painter.font()
    font.setPointSize(10)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(badge_x, badge_y, badge_width, 18, Qt.AlignCenter, badge_text)

    painter.end()
    return pixmap


# ============================================================================
# DRAGGABLE MIXIN
# ============================================================================

class DraggableMixin:
    """Mixin to add drag source capability to a widget.

    Subclasses should:
    1. Call _init_drag_state() in __init__
    2. Call _handle_drag_press(event) in mousePressEvent
    3. Call _handle_drag_move(event) in mouseMoveEvent
    4. Override _get_drag_paths() to return paths to drag
    5. Optionally override _get_drag_pixmap() for custom drag visuals

    Example:
        class MyThumbnail(QWidget, DraggableMixin):
            def __init__(self):
                super().__init__()
                self._init_drag_state()

            def _get_drag_paths(self):
                return [self.file_path]

            def mousePressEvent(self, event):
                self._handle_drag_press(event)
                super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                if self._handle_drag_move(event):
                    return  # Drag started
                super().mouseMoveEvent(event)
    """

    def _init_drag_state(self):
        """Initialize drag state. Call this in __init__."""
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_in_progress = False

    def _handle_drag_press(self, event):
        """Handle mouse press for potential drag. Call in mousePressEvent."""
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_in_progress = False

    def _handle_drag_move(self, event) -> bool:
        """Handle mouse move for drag initiation. Call in mouseMoveEvent.

        Returns True if a drag was started, False otherwise.
        """
        try:
            if not (event.buttons() & Qt.LeftButton):
                return False

            if self._drag_start_pos is None:
                return False

            # Check if we've moved far enough to start a drag
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance < QApplication.startDragDistance():
                return False

            # Start drag
            self._drag_in_progress = True
            paths = self._get_drag_paths()

            if not paths:
                self._drag_in_progress = False
                return False

            drag = QDrag(self)
            mime_data = create_file_mime_data(paths)
            drag.setMimeData(mime_data)

            # Set drag pixmap
            try:
                pixmap = self._get_drag_pixmap(paths)
                if pixmap and not pixmap.isNull():
                    drag.setPixmap(pixmap)
                    drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
            except Exception as e:
                logger.debug(f"Error creating drag pixmap: {e}")

            logger.debug(f"Starting drag with {len(paths)} file(s)")
            drag.exec_(Qt.CopyAction | Qt.MoveAction)

            self._drag_start_pos = None
            self._drag_in_progress = False
            return True
        except Exception as e:
            logger.error(f"Error during drag operation: {e}")
            self._drag_start_pos = None
            self._drag_in_progress = False
            return False

    def _get_drag_paths(self) -> List[str]:
        """Override to return list of file paths to drag.

        This is called when a drag is initiated.
        """
        raise NotImplementedError("Subclasses must implement _get_drag_paths()")

    def _get_drag_pixmap(self, paths: List[str]) -> QPixmap:
        """Override to customize the drag pixmap.

        Default implementation creates a thumbnail or stack visualization.
        """
        return create_drag_pixmap(paths)


# ============================================================================
# DROP TARGET MIXIN
# ============================================================================

class DropTargetMixin:
    """Mixin to add drop target capability to a widget.

    Subclasses should:
    1. Call _init_drop_target(categories) in __init__
    2. Override _on_files_dropped(paths) to handle dropped files
    3. Optionally override _get_drop_highlight_style() for custom highlight

    Example:
        class MyImageInput(QWidget, DropTargetMixin):
            def __init__(self):
                super().__init__()
                self._init_drop_target({'image'})  # Only accept images

            def _on_files_dropped(self, paths):
                for path in paths:
                    self.add_image(path)
    """

    def _init_drop_target(self, accepted_categories: Set[str] = None):
        """Initialize drop target. Call this in __init__.

        Args:
            accepted_categories: Set of categories to accept.
                               Default is {'image', 'video', 'model'}.
        """
        self._accepted_categories = accepted_categories or {'image', 'video', 'model'}
        self._drop_highlight_active = False
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        """Handle drag enter - check if we can accept the data."""
        try:
            from shiboken6 import isValid
            if not isValid(self):
                event.ignore()
                return
            logger.debug(f"[DropTargetMixin] dragEnterEvent on {type(self).__name__}")
            if can_accept_files(event.mimeData(), self._accepted_categories):
                logger.debug(f"[DropTargetMixin] Accepting drop, calling _show_drop_highlight(True)")
                event.acceptProposedAction()
                self._show_drop_highlight(True)
            else:
                logger.debug(f"[DropTargetMixin] Rejecting drop - no acceptable files")
                event.ignore()
        except Exception as e:
            logger.debug(f"[DropTargetMixin] dragEnterEvent error: {e}")
            event.ignore()

    def dragMoveEvent(self, event):
        """Handle drag move - continue accepting if valid."""
        try:
            from shiboken6 import isValid
            if not isValid(self):
                event.ignore()
                return
            if can_accept_files(event.mimeData(), self._accepted_categories):
                event.acceptProposedAction()
            else:
                event.ignore()
        except Exception as e:
            logger.debug(f"[DropTargetMixin] dragMoveEvent error: {e}")
            event.ignore()

    def dragLeaveEvent(self, event):
        """Handle drag leave - remove highlight."""
        try:
            logger.debug(f"[DropTargetMixin] dragLeaveEvent START on {type(self).__name__}")
            from shiboken6 import isValid
            valid = isValid(self)
            logger.debug(f"[DropTargetMixin] dragLeaveEvent isValid={valid}")
            if not valid:
                logger.debug(f"[DropTargetMixin] dragLeaveEvent widget invalid, accepting and returning")
                event.accept()
                return
            visible = self.isVisible()
            logger.debug(f"[DropTargetMixin] dragLeaveEvent isVisible={visible}")
            logger.debug(f"[DropTargetMixin] dragLeaveEvent calling _show_drop_highlight(False)")
            self._show_drop_highlight(False)
            logger.debug(f"[DropTargetMixin] dragLeaveEvent _show_drop_highlight done, calling event.accept()")
            event.accept()
            logger.debug(f"[DropTargetMixin] dragLeaveEvent COMPLETE")
        except Exception as e:
            logger.error(f"[DropTargetMixin] dragLeaveEvent error: {e}", exc_info=True)
            event.accept()

    def dropEvent(self, event):
        """Handle drop - extract files and call handler."""
        try:
            from shiboken6 import isValid
            if not isValid(self):
                event.ignore()
                return
            self._show_drop_highlight(False)

            paths = extract_files_from_mime_data(event.mimeData())
            filtered_paths = filter_files_by_category(paths, self._accepted_categories)

            if filtered_paths:
                logger.debug(f"Dropped {len(filtered_paths)} file(s)")
                self._on_files_dropped(filtered_paths)
                event.acceptProposedAction()
            else:
                event.ignore()
        except Exception as e:
            logger.debug(f"[DropTargetMixin] dropEvent error: {e}")
            event.ignore()

    def _on_files_dropped(self, paths: List[str]):
        """Override to handle dropped files.

        Args:
            paths: List of file paths that were dropped (already filtered)
        """
        raise NotImplementedError("Subclasses must implement _on_files_dropped()")

    def _show_drop_highlight(self, show: bool):
        """Show or hide drop highlight visual feedback.

        Override for custom highlight behavior. Default does nothing.
        """
        self._drop_highlight_active = show

    def _get_drop_highlight_style(self) -> str:
        """Return stylesheet for drop highlight state.

        Override to customize the highlight appearance.
        """
        return """
            border: 2px dashed #4a9eff;
            background-color: rgba(74, 158, 255, 0.1);
        """


# ============================================================================
# DROP-ENABLED LINE EDIT WRAPPER
# ============================================================================

class DropEnabledLineEdit:
    """Wrapper to add drop capability to a QLineEdit for file paths.

    This is a non-invasive way to add drop support without subclassing.

    Usage:
        line_edit = QLineEdit()
        drop_wrapper = DropEnabledLineEdit(line_edit, {'image', 'video'})
    """

    def __init__(self, line_edit, accepted_categories: Set[str] = None):
        """Wrap a QLineEdit with drop support.

        Args:
            line_edit: The QLineEdit to wrap
            accepted_categories: Set of file categories to accept
        """
        self._line_edit = line_edit
        self._accepted_categories = accepted_categories or {'image', 'video', 'model'}
        self._original_style = line_edit.styleSheet()

        # Enable drops
        line_edit.setAcceptDrops(True)

        # Install event filter
        line_edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle drag/drop events on the line edit."""
        from PySide6.QtCore import QEvent

        if obj != self._line_edit:
            return False

        if event.type() == QEvent.DragEnter:
            if can_accept_files(event.mimeData(), self._accepted_categories):
                event.acceptProposedAction()
                self._show_highlight(True)
                return True
            return False

        elif event.type() == QEvent.DragMove:
            if can_accept_files(event.mimeData(), self._accepted_categories):
                event.acceptProposedAction()
                return True
            return False

        elif event.type() == QEvent.DragLeave:
            self._show_highlight(False)
            return False

        elif event.type() == QEvent.Drop:
            self._show_highlight(False)
            paths = extract_files_from_mime_data(event.mimeData())
            filtered = filter_files_by_category(paths, self._accepted_categories)
            if filtered:
                # Set the first path in the line edit
                self._line_edit.setText(filtered[0])
                event.acceptProposedAction()
                return True
            return False

        return False

    def _show_highlight(self, show: bool):
        """Show or hide drop highlight."""
        if show:
            self._line_edit.setStyleSheet(
                self._original_style +
                "border: 2px solid #4a9eff; background-color: rgba(74, 158, 255, 0.15);"
            )
        else:
            self._line_edit.setStyleSheet(self._original_style)
