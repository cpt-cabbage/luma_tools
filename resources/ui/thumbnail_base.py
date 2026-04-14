"""
Base class for thumbnail widgets with shared placeholder functionality.
"""
import threading
from collections import OrderedDict
from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPixmap, QImage, QFont


def extract_video_frame_with_duration(video_path, thumb_width=150, thumb_height=150):
    """Extract first frame and duration from video using FFmpeg.

    Shared utility used by both SmallThumbnail and ThumbnailWidget to avoid
    duplicating the FFmpeg subprocess logic.

    Args:
        video_path: Path to the video file
        thumb_width: Thumbnail width for scaling
        thumb_height: Thumbnail height for scaling

    Returns:
        tuple: (image_data: bytes, duration: float) or None on error
    """
    import subprocess
    import tempfile
    import os
    from core.config import FFMPEG_PATH
    from core.utils import get_media_duration

    if not FFMPEG_PATH:
        return None

    tmp_path = None
    try:
        duration = get_media_duration(video_path)

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        cmd = [
            FFMPEG_PATH, '-i', video_path,
            '-vframes', '1', '-y', tmp_path
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        result = subprocess.run(
            cmd, capture_output=True, timeout=10, creationflags=creationflags
        )
        if result.returncode != 0:
            return None

        from PySide6.QtGui import QImage
        from PySide6.QtCore import QBuffer, QIODevice
        image = QImage(tmp_path)
        if image.isNull():
            return None

        scaled = image.scaled(
            thumb_width, thumb_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        try:
            scaled.save(buffer, "PNG")
            return (bytes(buffer.data()), duration)
        finally:
            buffer.close()
    except Exception:
        return None
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


class BaseThumbnailWidget(QWidget):
    """Base class for thumbnail widgets with shared placeholder caching logic.

    The placeholder *image* construction is thread-safe and pulled from a
    bounded LRU. The QPixmap conversion (and therefore _create_placeholder
    itself) must be called from the GUI thread.
    """

    THUMBNAIL_SIZE = (150, 150)
    _PLACEHOLDER_CACHE_MAX = 64
    _placeholder_cache: "OrderedDict[str, QImage]" = OrderedDict()
    _placeholder_cache_lock = threading.RLock()

    def _create_placeholder(self, text, bg_color="#3c414b", fg_color="#888888", font_size=14):
        """
        Create a placeholder QPixmap, cached by appearance.

        Must be called from the main (GUI) thread because QPixmap construction
        is GUI-thread-only. The underlying QImage cache is thread-safe and
        bounded so labels for arbitrary file extensions/categories don't grow
        the cache without bound over a long session.

        Args:
            text: Text to display in the placeholder
            bg_color: Background color (hex string)
            fg_color: Foreground/text color (hex string)
            font_size: Font size for the text

        Returns:
            QPixmap: Cached or newly created placeholder pixmap
        """
        cache_key = f"{text}_{bg_color}_{fg_color}_{font_size}"

        with BaseThumbnailWidget._placeholder_cache_lock:
            cached_image = BaseThumbnailWidget._placeholder_cache.get(cache_key)
            if cached_image is not None:
                # Mark as most recently used
                BaseThumbnailWidget._placeholder_cache.move_to_end(cache_key)

        if cached_image is None:
            w, h = self.THUMBNAIL_SIZE
            cached_image = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
            cached_image.fill(QColor(bg_color))
            painter = QPainter(cached_image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QColor(fg_color))
            font = QFont()
            font.setPointSize(font_size)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(0, 0, w, h), Qt.AlignCenter, text)
            painter.end()

            with BaseThumbnailWidget._placeholder_cache_lock:
                BaseThumbnailWidget._placeholder_cache[cache_key] = cached_image
                BaseThumbnailWidget._placeholder_cache.move_to_end(cache_key)
                while len(BaseThumbnailWidget._placeholder_cache) > self._PLACEHOLDER_CACHE_MAX:
                    BaseThumbnailWidget._placeholder_cache.popitem(last=False)

        return QPixmap.fromImage(cached_image)
