"""
Icon Manager for Luma Tools UI
Provides SVG icon loading with color tinting support.
"""

import os
import logging
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QImage
from PySide6.QtSvg import QSvgRenderer

logger = logging.getLogger(__name__)


# Icon directory path
ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")


# Tab accent colors - monochromatic with blue accent
TAB_COLORS = {
    "pass_builder": "#4a9eff",  # Blue Accent (primary)
    "mp4_maker": "#9fa5b0",     # Slate Gray
    "republish": "#9fa5b0",     # Slate Gray
    "shot_cleaner": "#9fa5b0",  # Slate Gray
    "logs": "#9fa5b0",          # Slate Gray
    "comfyui": "#4a9eff",       # Blue Accent (AI feature)
    "gallery": "#9fa5b0",       # Slate Gray
    "settings": "#797e89",      # Dim Gray
}

# Status colors - Apple-style Vibrant
STATUS_COLORS = {
    "success": "#32d74b",
    "warning": "#ff9f0a",
    "error": "#ff453a",
    "info": "#0a84ff",
    "processing": "#bf5af2",
}

# Default icon color
DEFAULT_ICON_COLOR = "#9fa5b0"


class IconManager:
    """
    Manages SVG icon loading and tinting for consistent UI styling.

    Features:
    - Load SVG icons from the icons directory
    - Tint icons with custom colors
    - Cache rendered pixmaps for performance
    - Support multiple sizes

    Usage:
        icon = IconManager.get_icon("build", color="#22d3ee", size=24)
        pixmap = IconManager.get_pixmap("scan", color=TAB_COLORS["pass_builder"])
    """

    _cache = {}  # Cache for rendered pixmaps: (name, color, size) -> QPixmap

    @classmethod
    def get_icon_path(cls, name: str) -> str:
        """
        Get the full path to an icon file.

        Args:
            name: Icon name without extension

        Returns:
            Full path to the SVG file
        """
        return os.path.join(ICONS_DIR, f"{name}.svg")

    @classmethod
    def icon_exists(cls, name: str) -> bool:
        """Check if an icon file exists."""
        return os.path.exists(cls.get_icon_path(name))

    @classmethod
    def get_pixmap(cls, name: str, color: str = None, size: int = 24) -> QPixmap:
        """
        Get a pixmap for the specified icon, optionally tinted.

        Args:
            name: Icon name (without .svg extension)
            color: Hex color string to tint the icon (e.g., "#22d3ee")
            size: Icon size in pixels (icons are square)

        Returns:
            QPixmap of the icon, or empty pixmap if not found
        """
        if color is None:
            color = DEFAULT_ICON_COLOR

        cache_key = (name, color, size)

        # Check cache
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        icon_path = cls.get_icon_path(name)

        if not os.path.exists(icon_path):
            # Return empty pixmap if icon doesn't exist
            logger.warning(f"Icon not found: {icon_path}")
            return QPixmap(size, size)

        # Render SVG to pixmap
        pixmap = cls._render_svg(icon_path, color, size)

        # Cache result
        cls._cache[cache_key] = pixmap

        return pixmap

    @classmethod
    def get_icon(cls, name: str, color: str = None, size: int = 24) -> QIcon:
        """
        Get a QIcon for the specified icon, optionally tinted.

        Args:
            name: Icon name (without .svg extension)
            color: Hex color string to tint the icon
            size: Icon size in pixels

        Returns:
            QIcon containing the icon
        """
        pixmap = cls.get_pixmap(name, color, size)
        return QIcon(pixmap)

    @classmethod
    def _render_svg(cls, path: str, color: str, size: int) -> QPixmap:
        """
        Render an SVG file to a tinted pixmap.

        Args:
            path: Path to SVG file
            color: Hex color to tint with
            size: Target size in pixels

        Returns:
            Rendered and tinted QPixmap
        """
        # Create SVG renderer
        renderer = QSvgRenderer(path)

        if not renderer.isValid():
            logger.warning(f"Invalid SVG: {path}")
            return QPixmap(size, size)

        # Create image with transparency
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)

        # Render SVG to image
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        renderer.render(painter)
        painter.end()

        # Tint the image
        tinted = cls._tint_image(image, color)

        return QPixmap.fromImage(tinted)

    @classmethod
    def _tint_image(cls, image: QImage, color: str) -> QImage:
        """
        Tint an image with a color while preserving alpha.
        Uses fast QPainter composition instead of pixel-by-pixel.

        Args:
            image: Source QImage
            color: Hex color string

        Returns:
            Tinted QImage
        """
        tint_color = QColor(color)

        # Create result image - copy the original to preserve alpha
        result = QImage(image.size(), QImage.Format_ARGB32)
        result.fill(Qt.transparent)

        # Draw the original image
        painter = QPainter(result)
        painter.drawImage(0, 0, image)

        # Apply tint using SourceIn composition mode
        # This replaces color but keeps alpha from destination
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(result.rect(), tint_color)
        painter.end()

        return result

    @classmethod
    def clear_cache(cls):
        """Clear the icon cache."""
        cls._cache.clear()

    @classmethod
    def get_tab_icon(cls, tab_name: str, size: int = 20) -> QIcon:
        """
        Get the icon for a specific tab with its accent color.

        Args:
            tab_name: One of: pass_builder, mp4_maker, republish, shot_cleaner, comfyui, settings
            size: Icon size in pixels

        Returns:
            QIcon with appropriate color
        """
        # Map tab names to icon names
        tab_icons = {
            "pass_builder": "layers",
            "mp4_maker": "video",
            "republish": "upload",
            "shot_cleaner": "trash",
            "logs": "terminal",
            "comfyui": "sparkles",
            "gallery": "image",
            "settings": "settings",
        }

        icon_name = tab_icons.get(tab_name, "circle")

        return cls.get_icon(icon_name, DEFAULT_ICON_COLOR, size)

    @classmethod
    def get_action_icon(cls, action: str, color: str = None, size: int = 18) -> QIcon:
        """
        Get an icon for a common action.

        Args:
            action: Action name (scan, browse, refresh, add, remove, build, play, etc.)
            color: Optional custom color
            size: Icon size

        Returns:
            QIcon for the action
        """
        # Map actions to icon names
        action_icons = {
            "scan": "search",
            "browse": "folder",
            "refresh": "refresh",
            "add": "plus",
            "remove": "minus",
            "delete": "trash",
            "build": "hammer",
            "play": "play",
            "stop": "square",
            "check": "check",
            "warning": "alert-triangle",
            "error": "x-circle",
            "info": "info",
            "copy": "copy",
            "save": "save",
            "load": "download",
            "upload": "upload",
            "settings": "settings",
            "close": "x",
            "expand": "chevron-down",
            "collapse": "chevron-up",
        }

        icon_name = action_icons.get(action, action)
        return cls.get_icon(icon_name, color, size)

    @classmethod
    def get_status_icon(cls, status: str, size: int = 16) -> QIcon:
        """
        Get a status indicator icon.

        Args:
            status: One of: success, warning, error, info, processing
            size: Icon size

        Returns:
            QIcon with appropriate color
        """
        status_icons = {
            "success": "check-circle",
            "warning": "alert-triangle",
            "error": "x-circle",
            "info": "info",
            "processing": "loader",
        }

        icon_name = status_icons.get(status, "circle")

        return cls.get_icon(icon_name, DEFAULT_ICON_COLOR, size)


# Convenience functions for common use cases
def get_icon(name: str, color: str = None, size: int = 24) -> QIcon:
    """Convenience function to get an icon."""
    return IconManager.get_icon(name, color, size)


def get_pixmap(name: str, color: str = None, size: int = 24) -> QPixmap:
    """Convenience function to get a pixmap."""
    return IconManager.get_pixmap(name, color, size)


def get_tab_icon(tab_name: str, size: int = 20) -> QIcon:
    """Convenience function to get a tab icon."""
    return IconManager.get_tab_icon(tab_name, size)
