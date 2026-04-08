"""
Drag and Drop functionality for Luma Tools.

Provides mixins and utilities for enabling drag-and-drop between widgets:
- DraggableMixin: Add drag source capability to widgets
- DropTargetMixin: Add drop target capability to widgets
- Specialized drop handlers for images, videos, 3D models, and file paths
- Browser drag-drop and clipboard paste utilities

Supported MIME types:
- application/x-luma-files: Internal file paths (images, videos, models)
- text/uri-list: External file drops from file explorer
- text/plain: Fallback for file paths as text
- image/png, image/jpeg: Raw image data from clipboard/browser
- text/html: HTML with embedded image URLs from browser
"""
import os
import re
import logging
from datetime import datetime
from typing import List, Optional, Set, Callable, Dict, Any

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
# BROWSER / CLIPBOARD IMAGE UTILITIES
# ============================================================================

# Image URL extensions recognized when extracting from HTML or URLs
_IMAGE_URL_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff')

# Maximum download size (50 MB)
_MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024

# Download timeout in seconds
_DOWNLOAD_TIMEOUT = 15


def extract_browser_image_data(mime_data: QMimeData) -> Dict[str, Any]:
    """Inspect MIME data and return what browser image data is available.

    Priority order:
    1. Raw image data (mime.hasImage() / image/png format) — screenshots, copy-image
    2. HTTP/HTTPS URLs pointing to images
    3. Local file paths (existing behavior)

    Returns:
        Dict with keys:
        - "type": "image_data" | "url" | "local_files" | None
        - "image": QImage or None (only for type="image_data")
        - "urls": list of HTTP image URLs (only for type="url")
        - "local_paths": list of local file paths (only for type="local_files")
    """
    from PySide6.QtGui import QImage

    result = {"type": None, "image": None, "urls": [], "local_paths": []}

    # Priority 1: Raw image data (screenshots, browser "Copy image")
    if mime_data.hasImage():
        image = mime_data.imageData()
        if isinstance(image, QImage) and not image.isNull():
            result["type"] = "image_data"
            result["image"] = image
            return result

    # Priority 2: HTTP URLs (browser drag of image elements)
    if mime_data.hasUrls():
        http_urls = []
        local_paths = []
        for url in mime_data.urls():
            url_str = url.toString()
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if local_path and os.path.isfile(local_path):
                    local_paths.append(local_path)
            elif url_str.startswith(('http://', 'https://')):
                http_urls.append(url_str)

        if http_urls:
            result["type"] = "url"
            result["urls"] = http_urls
            return result

        if local_paths:
            result["type"] = "local_files"
            result["local_paths"] = local_paths
            return result

    # Priority 2b: Check text/html for <img src="..."> URLs
    if mime_data.hasHtml():
        img_url = extract_image_url_from_html(mime_data.html())
        if img_url:
            result["type"] = "url"
            result["urls"] = [img_url]
            return result

    # Priority 3: Plain text that looks like an image URL
    if mime_data.hasText():
        text = mime_data.text().strip()
        if text.startswith(('http://', 'https://')):
            # Check if URL looks like an image
            lower = text.split('?')[0].lower()
            if any(lower.endswith(ext) for ext in _IMAGE_URL_EXTENSIONS):
                result["type"] = "url"
                result["urls"] = [text]
                return result

    return result


def can_accept_browser_media(mime_data: QMimeData) -> bool:
    """Gate check for dragEnterEvent — True if any image data is present.

    This covers raw image data, HTTP image URLs, and local image files.
    More permissive than can_accept_files() which only checks local paths.
    """
    data = extract_browser_image_data(mime_data)
    return data["type"] is not None


def save_image_data_to_file(image, directory: str, filename: str = None) -> Optional[str]:
    """Save a QImage to a PNG file.

    Args:
        image: QImage to save
        directory: Directory to save into
        filename: Filename (generated if None)

    Returns:
        Full path to saved file, or None on failure
    """
    from PySide6.QtGui import QImage

    if not isinstance(image, QImage) or image.isNull():
        logger.warning("Cannot save null or invalid QImage")
        return None

    if not filename:
        filename = generate_image_filename(prefix="image_paste")

    filepath = os.path.join(directory, filename)

    try:
        from core.utils import ensure_directory
        ensure_directory(directory)
    except Exception as e:
        logger.error(f"Cannot create directory {directory}: {e}")
        return None

    if image.save(filepath, "PNG"):
        logger.info(f"Saved image data to: {filepath}")
        return filepath
    else:
        logger.error(f"Failed to save QImage to: {filepath}")
        return None


def generate_image_filename(url: str = None, prefix: str = "image_paste") -> str:
    """Generate a timestamp-based filename for saved images.

    Args:
        url: Optional source URL (used to extract extension)
        prefix: Filename prefix

    Returns:
        Filename like 'image_paste_20260223_143052_123.png'
    """
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond // 1000:03d}"

    ext = ".png"
    if url:
        # Try to get extension from URL (strip query params)
        clean_url = url.split('?')[0].split('#')[0]
        url_ext = os.path.splitext(clean_url)[1].lower()
        if url_ext in _IMAGE_URL_EXTENSIONS:
            ext = url_ext

    return f"{prefix}_{timestamp}{ext}"


def download_image_from_url(url: str, save_directory: str) -> Optional[str]:
    """Download an image from a URL and save to directory.

    Designed for worker thread use. Validates content-type, enforces size limit.

    Args:
        url: HTTP/HTTPS URL to download
        save_directory: Directory to save the downloaded image

    Returns:
        Full path to saved file, or None on failure
    """
    import urllib.request
    import urllib.error

    if not url.startswith(('http://', 'https://')):
        logger.warning(f"Invalid URL scheme: {url}")
        return None

    filename = generate_image_filename(url=url, prefix="image_drop")
    filepath = os.path.join(save_directory, filename)

    try:
        from core.utils import ensure_directory
        ensure_directory(save_directory)
    except Exception as e:
        logger.error(f"Cannot create directory {save_directory}: {e}")
        return None

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LumaTools/1.0'
        })
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as response:
            # Check content type
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                logger.warning(f"Non-image content type: {content_type} from {url}")
                return None

            # Check content length if available
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > _MAX_DOWNLOAD_SIZE:
                logger.warning(f"Image too large: {content_length} bytes from {url}")
                return None

            # Read with size limit
            data = response.read(_MAX_DOWNLOAD_SIZE + 1)
            if len(data) > _MAX_DOWNLOAD_SIZE:
                logger.warning(f"Image exceeded {_MAX_DOWNLOAD_SIZE} bytes from {url}")
                return None

            # Determine extension from content-type if filename has generic .png
            ct_ext_map = {
                'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp',
                'image/gif': '.gif', 'image/bmp': '.bmp',
            }
            ct_base = content_type.split(';')[0].strip().lower()
            if ct_base in ct_ext_map:
                correct_ext = ct_ext_map[ct_base]
                base, current_ext = os.path.splitext(filepath)
                if current_ext != correct_ext:
                    filepath = base + correct_ext
                    filename = os.path.basename(filepath)

            with open(filepath, 'wb') as f:
                f.write(data)

            logger.info(f"Downloaded image from {url} -> {filepath}")
            return filepath

    except urllib.error.URLError as e:
        logger.error(f"URL error downloading {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error downloading image from {url}: {e}")
        return None


def extract_image_url_from_html(html: str) -> Optional[str]:
    """Extract the first image URL from an HTML fragment.

    Used for browser drags that provide text/html with <img> tags.

    Args:
        html: HTML string from MIME data

    Returns:
        First HTTP/HTTPS image URL found, or None
    """
    if not html:
        return None

    # Match <img src="..."> — handles single and double quotes
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if match:
        url = match.group(1)
        if url.startswith(('http://', 'https://')):
            return url

    return None


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
