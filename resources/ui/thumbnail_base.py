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
    # Values are QImage (from _create_placeholder) or QPixmap (from the
    # video/audio/3D placeholder builders); keys are disjoint per builder.
    # Always access through _placeholder_cache_get/_placeholder_cache_put so
    # every entry gets the same LRU bookkeeping.
    _placeholder_cache: "OrderedDict[str, object]" = OrderedDict()
    _placeholder_cache_lock = threading.RLock()

    @classmethod
    def _placeholder_cache_get(cls, cache_key):
        """LRU-aware cache read (marks the entry most-recently-used)."""
        with cls._placeholder_cache_lock:
            value = cls._placeholder_cache.get(cache_key)
            if value is not None:
                cls._placeholder_cache.move_to_end(cache_key)
            return value

    @classmethod
    def _placeholder_cache_put(cls, cache_key, value):
        """LRU-aware cache write with bounded eviction."""
        with cls._placeholder_cache_lock:
            cls._placeholder_cache[cache_key] = value
            cls._placeholder_cache.move_to_end(cache_key)
            while len(cls._placeholder_cache) > cls._PLACEHOLDER_CACHE_MAX:
                cls._placeholder_cache.popitem(last=False)

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

        cached_image = BaseThumbnailWidget._placeholder_cache_get(cache_key)

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

            BaseThumbnailWidget._placeholder_cache_put(cache_key, cached_image)

        return QPixmap.fromImage(cached_image)
