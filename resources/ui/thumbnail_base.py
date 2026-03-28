"""
Base class for thumbnail widgets with shared placeholder functionality.
"""
import threading
from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPixmap, QImage, QFont


class BaseThumbnailWidget(QWidget):
    """Base class for thumbnail widgets with shared placeholder caching logic.

    Thread-safe: Uses QImage for construction (safe on any thread),
    converts to QPixmap only on the main thread via cache.
    """

    THUMBNAIL_SIZE = (150, 150)
    _placeholder_cache = {}
    _placeholder_cache_lock = threading.RLock()

    def _create_placeholder(self, text, bg_color="#3c414b", fg_color="#888888", font_size=14):
        """
        Create a placeholder pixmap with cached results.

        Thread-safe: Uses QImage for rendering (safe on any thread),
        then converts to QPixmap for display.

        Args:
            text: Text to display in the placeholder
            bg_color: Background color (hex string)
            fg_color: Foreground/text color (hex string)
            font_size: Font size for the text

        Returns:
            QPixmap: Cached or newly created placeholder pixmap
        """
        # Create a cache key based on all parameters
        cache_key = f"{text}_{bg_color}_{fg_color}_{font_size}"

        # Return cached version if available (thread-safe)
        with BaseThumbnailWidget._placeholder_cache_lock:
            if cache_key in BaseThumbnailWidget._placeholder_cache:
                return BaseThumbnailWidget._placeholder_cache[cache_key]

        # Use QImage for thread-safe construction (QPixmap is not thread-safe)
        w, h = self.THUMBNAIL_SIZE
        image = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        image.fill(QColor(bg_color))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(fg_color))
        font = QFont()
        font.setPointSize(font_size)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(0, 0, w, h), Qt.AlignCenter, text)
        painter.end()

        # Convert to QPixmap and cache (thread-safe)
        pixmap = QPixmap.fromImage(image)
        with BaseThumbnailWidget._placeholder_cache_lock:
            # Double-check in case another thread added it while we were creating
            if cache_key not in BaseThumbnailWidget._placeholder_cache:
                BaseThumbnailWidget._placeholder_cache[cache_key] = pixmap
            return BaseThumbnailWidget._placeholder_cache[cache_key]
