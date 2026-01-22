"""
Unified thumbnail styling for gallery widgets.

Centralizes all thumbnail styling logic to ensure consistency across:
- GalleryThumbnailWidget (images)
- GLBThumbnailWidget (3D models)
- StackedThumbnailWidget (grouped items)

Usage:
    from thumbnail_styles import ThumbnailStyler

    # In widget __init__:
    self._styler = ThumbnailStyler(has_metadata=True, is_model=False)

    # Apply styles:
    style = self._styler.get_style(selected=self._is_selected, hover=False, is_new=self._is_new)
    self.thumbnail_label.setStyleSheet(style)
"""


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

    # Special states
    BORDER_NEW = "#10b981"            # Green for new items


class ThumbnailStyler:
    """Generates consistent styles for thumbnail widgets."""

    def __init__(self, has_metadata=False, is_model=False, is_stacked=False, border_radius=4):
        """
        Initialize the styler.

        Args:
            has_metadata: Whether the item has ComfyUI metadata
            is_model: Whether the item is a 3D model
            is_stacked: Whether this is a stacked thumbnail widget
            border_radius: Border radius in pixels (4 for regular, 8 for stacked)
        """
        self.has_metadata = has_metadata
        self.is_model = is_model
        self.is_stacked = is_stacked
        self.border_radius = border_radius

    def get_background_color(self, hover=False, selected=False):
        """Get the appropriate background color."""
        if selected and hover:
            return ThumbnailColors.BG_HOVER_SELECTED
        if hover:
            return ThumbnailColors.BG_HOVER
        if self.is_model:
            return ThumbnailColors.BG_MODEL
        if self.has_metadata:
            return ThumbnailColors.BG_WITH_METADATA
        return ThumbnailColors.BG_WITHOUT_METADATA

    def get_border_color(self, selected=False, hover=False, is_new=False):
        """Get the appropriate border color."""
        if selected:
            if hover:
                return ThumbnailColors.BORDER_SELECTED_HOVER
            return ThumbnailColors.BORDER_SELECTED_STACK if self.is_stacked else ThumbnailColors.BORDER_SELECTED

        if is_new:
            return ThumbnailColors.BORDER_NEW

        if hover:
            if self.is_model:
                return ThumbnailColors.BORDER_HOVER_MODEL
            if self.has_metadata:
                return ThumbnailColors.BORDER_HOVER_METADATA
            return ThumbnailColors.BORDER_HOVER_NO_METADATA

        # Normal state
        if self.is_model:
            return ThumbnailColors.BORDER_MODEL
        if self.has_metadata:
            return ThumbnailColors.BORDER_WITH_METADATA
        return ThumbnailColors.BORDER_WITHOUT_METADATA

    def get_border_width(self, selected=False):
        """Get border width - 3px when selected, 2px otherwise."""
        return 3 if selected else 2

    def get_style(self, selected=False, hover=False, is_new=False):
        """
        Get the complete stylesheet for the thumbnail label.

        Args:
            selected: Whether the item is selected
            hover: Whether the mouse is hovering
            is_new: Whether this is a newly generated item

        Returns:
            QString stylesheet for QLabel
        """
        bg = self.get_background_color(hover=hover, selected=selected)
        border = self.get_border_color(selected=selected, hover=hover, is_new=is_new)
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
