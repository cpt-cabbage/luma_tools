"""
Base class for thumbnail widgets with shared placeholder functionality.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPixmap


class BaseThumbnailWidget(QWidget):
    """Base class for thumbnail widgets with shared placeholder caching logic."""

    THUMBNAIL_SIZE = (150, 150)
    _placeholder_cache = {}

    def _create_placeholder(self, text, bg_color="#3c414b", fg_color="#888888", font_size=14):
        """
        Create a placeholder pixmap with cached results.

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

        # Return cached version if available
        if cache_key in BaseThumbnailWidget._placeholder_cache:
            return BaseThumbnailWidget._placeholder_cache[cache_key]

        # Create new placeholder
        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(QColor(bg_color))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(fg_color))
        font = painter.font()
        font.setPointSize(font_size)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()

        # Cache and return
        BaseThumbnailWidget._placeholder_cache[cache_key] = pixmap
        return pixmap
