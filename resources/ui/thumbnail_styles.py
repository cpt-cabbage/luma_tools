"""
Unified thumbnail styling for gallery widgets.

Centralizes all thumbnail styling logic to ensure consistency across:
- ThumbnailWidget (images, videos, audio, 3D models)
- StackedThumbnailWidget (grouped items)

Usage:
    from thumbnail_styles import ThumbnailStyler

    # In widget __init__:
    self._styler = ThumbnailStyler(has_metadata=True, is_model=False)

    # Apply styles:
    style = self._styler.get_style(selected=self._is_selected, hover=False, is_new=self._is_new)
    self.thumbnail_label.setStyleSheet(style)
"""


# ============================================================================
# TYPE INDICATOR CONFIG (shared between ThumbnailWidget and StackedThumbnailWidget)
# ============================================================================

# Maps item type → (icon character, rgba color string)
TYPE_INDICATOR_CONFIG = {
    'image': ('▣', 'rgba(16, 185, 129, 0.8)'),   # Green squares
    'video': ('▶', 'rgba(239, 68, 68, 0.8)'),    # Red play triangle
    'audio': ('♫', 'rgba(168, 85, 247, 0.8)'),   # Purple music note
    'model': ('⬣', 'rgba(74, 158, 255, 0.8)'),   # Blue hexagon/cube
}

TYPE_INDICATOR_DEFAULT = ('?', 'rgba(128, 128, 128, 0.8)')


def get_type_indicator_style(item_type: str) -> tuple:
    """Get the icon and stylesheet for a type indicator label.

    Args:
        item_type: One of 'image', 'video', 'audio', 'model'

    Returns:
        Tuple of (icon_text, stylesheet_string)
    """
    icon, color = TYPE_INDICATOR_CONFIG.get(item_type, TYPE_INDICATOR_DEFAULT)
    stylesheet = f"""
        QLabel {{
            background-color: rgba(0, 0, 0, 0.4);
            color: {color};
            border: 1px solid {color};
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
        }}
    """
    return icon, stylesheet


# ============================================================================
# COLOR UTILITIES (shared between thumbnail widgets)
# ============================================================================

def darken_color(hex_color: str, factor: float) -> str:
    """Darken a hex color by a factor (0-1). Factor 0.3 = 30% darker."""
    hex_color = hex_color.lstrip('#')
    r = max(0, int(int(hex_color[0:2], 16) * (1 - factor)))
    g = max(0, int(int(hex_color[2:4], 16) * (1 - factor)))
    b = max(0, int(int(hex_color[4:6], 16) * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten_color(hex_color: str, factor: float = 0.2) -> str:
    """Lighten a hex color by a factor (0-1). Factor 0.2 = 20% lighter."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def color_with_alpha(hex_color: str, alpha: int) -> str:
    """Convert hex color to rgba string with alpha (0-255)."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def derive_background_from_color(hex_color: str) -> str:
    """Derive a dark tinted background color from a hex color (30% brightness)."""
    hex_color = hex_color.lstrip('#')
    r = int(int(hex_color[0:2], 16) * 0.3)
    g = int(int(hex_color[2:4], 16) * 0.3)
    b = int(int(hex_color[4:6], 16) * 0.3)
    return f"#{r:02x}{g:02x}{b:02x}"


def derive_border_from_color(hex_color: str) -> str:
    """Derive a border color from a hex color (70% brightness)."""
    hex_color = hex_color.lstrip('#')
    r = int(min(255, int(hex_color[0:2], 16) * 0.7))
    g = int(min(255, int(hex_color[2:4], 16) * 0.7))
    b = int(min(255, int(hex_color[4:6], 16) * 0.7))
    return f"#{r:02x}{g:02x}{b:02x}"


class ThumbnailColors:
    """Color constants for thumbnail styling."""

    # Background colors
    BG_WITH_METADATA = "#1e3a5f"      # Blue tint for items with metadata
    BG_WITHOUT_METADATA = "#2c313a"   # Grey for items without metadata
    BG_MODEL = "#2d3139"              # Grey for 3D models

    # Hover background colors
    BG_HOVER = "#353a45"              # Standard hover background
    BG_HOVER_SELECTED = "#2a4a6f"     # Brighter blue for selected + hover

    # Border colors - normal state
    BORDER_WITH_METADATA = "#4a6d8c"  # Blue border for metadata items
    BORDER_WITHOUT_METADATA = "#3c414b"  # Grey border for non-metadata
    BORDER_MODEL = "#4a4a4a"          # Grey border for 3D models

    # Border colors - hover state
    BORDER_HOVER_METADATA = "#6bb3ff"  # Bright blue for hover with metadata
    BORDER_HOVER_NO_METADATA = "#5a5f6a"  # Light grey for hover without metadata
    BORDER_HOVER_MODEL = "#5a5f6a"    # Light grey for model hover

    # Border colors - selected state
    BORDER_SELECTED = "#3b82f6"       # Blue for selected (non-stacked)
    BORDER_SELECTED_STACK = "#5ba3ff" # Slightly different blue for stacks
    BORDER_SELECTED_HOVER = "#7bc4ff" # Bright blue for selected + hover

    # Special states (unused - new items use pulsing indicator instead)
    # BORDER_NEW = "#10b981"          # Green for new items (deprecated)


class ThumbnailStyler:
    """Generates consistent styles for thumbnail widgets."""

    def __init__(self, has_metadata=False, is_model=False, is_stacked=False, border_radius=4, group_color=None):
        """
        Initialize the styler.

        Args:
            has_metadata: Whether the item has ComfyUI metadata
            is_model: Whether the item is a 3D model
            is_stacked: Whether this is a stacked thumbnail widget
            border_radius: Border radius in pixels (4 for regular, 8 for stacked)
            group_color: Hex color for group border (overrides default border color)
        """
        self.has_metadata = has_metadata
        self.is_model = is_model
        self.is_stacked = is_stacked
        self.border_radius = border_radius
        self.group_color = group_color

    def get_background_color(self, hover=False, selected=False, drop_hover=False):
        """Get the appropriate background color."""
        # Get base background color first
        if self.group_color:
            base_bg = derive_background_from_color(self.group_color)
        elif self.is_model:
            base_bg = ThumbnailColors.BG_MODEL
        elif self.has_metadata:
            base_bg = ThumbnailColors.BG_WITH_METADATA
        else:
            base_bg = ThumbnailColors.BG_WITHOUT_METADATA

        # Apply hover/selected modifications
        # Drop hover is brightest (like a more intense hover) - only for items with group_color
        if drop_hover and self.group_color:
            return lighten_color(base_bg, 0.4)
        if selected and hover:
            return lighten_color(base_bg, 0.25)
        if hover:
            return lighten_color(base_bg, 0.15)

        return base_bg

    def get_border_color(self, selected=False, hover=False, is_new=False, drop_hover=False):
        """Get the appropriate border color.

        Note: is_new parameter is kept for backwards compatibility but no longer
        affects border color. New items now use a pulsing indicator instead.
        """
        if selected:
            if hover or drop_hover:
                return ThumbnailColors.BORDER_SELECTED_HOVER
            return ThumbnailColors.BORDER_SELECTED_STACK if self.is_stacked else ThumbnailColors.BORDER_SELECTED

        # is_new no longer affects border - uses pulsing indicator instead

        # Get base border color
        if self.group_color:
            base_border = derive_border_from_color(self.group_color)
        elif self.is_model:
            base_border = ThumbnailColors.BORDER_MODEL
        elif self.has_metadata:
            base_border = ThumbnailColors.BORDER_WITH_METADATA
        else:
            base_border = ThumbnailColors.BORDER_WITHOUT_METADATA

        # Apply hover modification - brighten the current color
        # Drop hover is even brighter than normal hover - only for items with group_color
        if drop_hover and self.group_color:
            return lighten_color(base_border, 0.5)
        if hover:
            return lighten_color(base_border, 0.3)

        return base_border

    def get_border_width(self, selected=False):
        """Get border width - 3px when selected, 2px otherwise."""
        return 3 if selected else 2

    def get_style(self, selected=False, hover=False, is_new=False, drop_hover=False):
        """
        Get the complete stylesheet for the thumbnail label.

        Args:
            selected: Whether the item is selected
            hover: Whether the mouse is hovering
            is_new: Whether this is a newly generated item
            drop_hover: Whether items are being dragged over (brighter than normal hover)

        Returns:
            QString stylesheet for QLabel
        """
        bg = self.get_background_color(hover=hover, selected=selected, drop_hover=drop_hover)
        border = self.get_border_color(selected=selected, hover=hover, is_new=is_new, drop_hover=drop_hover)
        width = self.get_border_width(selected=selected)

        return f"""
            QLabel {{
                background-color: {bg};
                border: {width}px solid {border};
                border-radius: {self.border_radius}px;
            }}
        """

    def update_config(self, has_metadata=None, is_model=None):
        """Update configuration (e.g., when metadata status changes)."""
        if has_metadata is not None:
            self.has_metadata = has_metadata
        if is_model is not None:
            self.is_model = is_model
