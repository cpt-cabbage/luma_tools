"""
Small reusable UI widgets and utilities.

Contains simple widgets and helper functions used across the application.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from PySide6.QtWidgets import (
    QWidget, QMenu, QPushButton, QHBoxLayout, QLabel
)
from PySide6.QtCore import Signal, Qt
from thumbnail_styles import (
    ThumbnailStyler, darken_color, lighten_color, color_with_alpha,
    derive_background_from_color, derive_border_from_color,
)
from dialog_helpers import get_active_window
from drag_drop import DraggableMixin, DropTargetMixin, create_drag_pixmap
from effects import create_property_animation


# ============================================================================
# STACKED THUMBNAIL WIDGET (Photo stack style grouping)
# ============================================================================

class StackedThumbnailWidget(DraggableMixin, DropTargetMixin, QWidget):
    """Stacked thumbnail widget showing a pile of images with count badge.

    Displays a representative thumbnail with stacked visual effect and a count
    badge. Clicking expands/collapses the stack with card-deck animation.

    Supports drag-and-drop: all items in the stack can be dragged to
    BatchImageSelector or other drop targets that accept files.

    Also acts as drop target for groups: dropping items onto a group stack
    adds them to that group.

    Signals:
        clicked(str): Emitted with stack_id when the stack is clicked
        expanded(str, bool): Emitted with (stack_id, is_expanded) when expansion state changes
        thumbnail_clicked(str, dict): Emitted when an expanded thumbnail is clicked (path, item)
        add_to_group_requested(str, list): Emitted with (group_id, [paths]) to add items to group
    """
    clicked = Signal(str)  # stack_id
    expanded = Signal(str, bool)  # stack_id, is_expanded
    thumbnail_clicked = Signal(str, dict)  # path, item dict
    add_to_group_requested = Signal(str, list)  # group_id, paths

    # Same thumbnail size as regular thumbnails
    THUMBNAIL_SIZE = (150, 150)
    WIDGET_SIZE = (160, 180)  # Full widget size including label
    # Offset for stacked visual effect
    STACK_OFFSET = 4

    def __init__(self, stack_id: str, items: List[Dict], parent=None, gallery_tab=None, group_color=None):
        """Initialize the stacked thumbnail widget.

        Args:
            stack_id: Unique identifier for this stack (usually job_prefix)
            items: List of item dicts in this stack (first item is shown on top)
            parent: Parent widget
            gallery_tab: Reference to gallery tab for creating thumbnails
            group_color: Optional hex color for group border styling
        """
        super().__init__(parent)
        self.stack_id = stack_id
        self._items = items
        self._count = len(items)
        self._thumbnail_loaded = False
        self._top_item = items[0] if items else None
        self._is_expanded = False
        self._is_selected = False  # Selection state for the whole stack
        self._is_hovered = False
        self._expanded_widgets = []  # List of expanded thumbnail widgets
        self._expanded_background = None  # Background frame behind expanded items
        self._gallery_tab = gallery_tab
        self._group_color = group_color  # Color for group stacking
        self._favorites_manager = None  # Will be set via set_favorites_manager
        self._is_all_liked = False  # Track if all items in stack are liked
        self._common_group_color = None  # Color if all items share a group
        # Check if items in this stack have metadata (source_images populated)
        self._has_metadata = self._check_items_have_metadata(items)
        # Check if top item is a 3D model (uses grey border, not blue)
        self._is_top_item_model = self._top_item and self._top_item.get('type') == 'model'
        # Create styler for consistent styling
        self._styler = ThumbnailStyler(
            has_metadata=self._has_metadata,
            is_model=self._is_top_item_model,
            is_stacked=True,
            border_radius=8,
            group_color=group_color
        )

        # Initialize drag support
        self._init_drag_state()

        # Initialize drop target support (accept images, videos, models)
        self._init_drop_target({'image', 'video', 'model'})

        self._setup_ui()
        self.setToolTip(f"{stack_id}\n{self._count} items - Click to expand")

    def _check_items_have_metadata(self, items):
        """Check if any item in the list has metadata."""
        for item in items:
            if item.get('has_metadata', False):
                return True
        return False

    def set_favorites_manager(self, manager):
        """Set the favorites manager for like/group tracking.

        Args:
            manager: FavoritesManager instance
        """
        self._favorites_manager = manager
        if manager:
            # Connect to like_changed signal to update when likes change
            manager.like_changed.connect(self._on_like_changed)
            # Connect to item_groups_changed signal to update when group membership changes
            manager.item_groups_changed.connect(self._on_item_groups_changed)
            # Check initial state
            self._update_favorites_state()

    def _on_like_changed(self, path, is_liked):
        """Handle like change signal from favorites manager."""
        # Check if this path is in our stack
        item_paths = [item['path'] for item in self._items]
        if path in item_paths:
            self._update_favorites_state()

    def _on_item_groups_changed(self, path):
        """Handle item group membership change signal from favorites manager."""
        # Check if this path is in our stack
        item_paths = [item['path'] for item in self._items]
        if path in item_paths:
            self._update_favorites_state()

    def _update_favorites_state(self):
        """Update like and group visual state from favorites manager."""
        self._check_all_liked()
        self._check_common_group()
        self._update_border_color()

    def _check_all_liked(self):
        """Check if all items in the stack are liked."""
        if not self._favorites_manager or not self._items:
            self._is_all_liked = False
            return

        # Check if every item in the stack is liked
        self._is_all_liked = all(
            self._favorites_manager.is_liked(item['path'])
            for item in self._items
        )

    def _check_common_group(self):
        """Check if all items in the stack belong to a common group.

        Sets self._common_group_color if all items share at least one group.
        """
        self._common_group_color = None

        if not self._favorites_manager or not self._items:
            return

        # Get groups for first item
        first_path = self._items[0]['path']
        first_groups = set(self._favorites_manager.get_item_groups(first_path))

        if not first_groups:
            return

        # Find groups common to ALL items
        common_groups = first_groups
        for item in self._items[1:]:
            item_groups = set(self._favorites_manager.get_item_groups(item['path']))
            common_groups = common_groups & item_groups
            if not common_groups:
                return

        # Use the first common group's color
        if common_groups:
            group_id = next(iter(common_groups))
            group = self._favorites_manager.get_group(group_id)
            if group:
                self._common_group_color = group.color

    def _get_current_custom_color(self):
        """Get the current custom color based on priority: group > stack.

        Liked state is shown only via individual thumbnail heart icons, not stack border.

        Returns:
            Hex color string or None if using default colors.
        """
        from core.settings_manager import get_setting

        # Priority 1: Common group color (all items share a group from favorites manager)
        common_group_color = getattr(self, '_common_group_color', None)
        if common_group_color:
            return common_group_color

        # Priority 2: Explicit group color (from group stacking mode at creation)
        if self._group_color:
            return self._group_color

        # Priority 3: Stack color (if has stack_id and custom stack color in settings)
        stack_colors = get_setting("gallery_stack_colors") or {}
        stack_color = stack_colors.get(self.stack_id)
        if stack_color:
            return stack_color

        return None

    def _update_border_color(self):
        """Update thumbnail border color with priority: group > liked > stack.

        Similar to ThumbnailWidget._update_group_border().
        """
        custom_color = self._get_current_custom_color()
        self._apply_stack_colors(custom_color)

    def _apply_stack_colors(self, custom_color=None):
        """Apply colors to all stack card labels.

        Args:
            custom_color: Optional hex color to use as base. If None, uses default blue/grey.
        """
        try:
            logger.debug(f"[StackedThumbnailWidget] _apply_stack_colors START custom_color={custom_color}")
            if not hasattr(self, '_stack_labels') or not self._stack_labels:
                logger.debug(f"[StackedThumbnailWidget] _apply_stack_colors no _stack_labels, returning")
                return

            # Check widget validity before proceeding
            from shiboken6 import isValid
            if not isValid(self):
                logger.debug(f"[StackedThumbnailWidget] _apply_stack_colors widget invalid, returning")
                return

            # Check if drop highlight is active
            drop_active = getattr(self, '_drop_highlight_active', False)
            logger.debug(f"[StackedThumbnailWidget] _apply_stack_colors drop_active={drop_active}")

            # Derive colors from custom_color or use defaults
            if custom_color:
                bg_color = derive_background_from_color(custom_color)
                border_color = derive_border_from_color(custom_color)
            elif self._is_top_item_model or not self._has_metadata:
                # Grey for 3D models and non-metadata items
                bg_color = "#2d3139"
                border_color = "#4a4a4a"
            else:
                # Blue for images with metadata
                bg_color = "#1e3a5f"
                border_color = "#4a6d8c"

            # Apply drop target styling when dropping items onto this stack
            # Use distinct green color for visibility
            if drop_active:
                from thumbnail_styles import ThumbnailColors
                bg_color = ThumbnailColors.BG_DROP_TARGET
                border_color = ThumbnailColors.BORDER_DROP_TARGET

            logger.debug(f"[StackedThumbnailWidget] _apply_stack_colors applying to {len(self._stack_labels)} labels")
            # Apply to all stack labels
            stack_depth = len(self._stack_labels) - 1
            for idx, label in enumerate(self._stack_labels):
                # Check label validity
                if not isValid(label):
                    logger.debug(f"[StackedThumbnailWidget] _apply_stack_colors label {idx} invalid, skipping")
                    continue
                # Labels are stored back-to-front, so index 0 is back card, last is top
                i = stack_depth - idx  # Reverse to get depth from back

                if i == 0:
                    # Top card - use full colors
                    label.setStyleSheet(f"""
                        QLabel {{
                            background-color: {bg_color};
                            border: 2px solid {border_color};
                            border-radius: 8px;
                        }}
                    """)
                else:
                    # Background cards - derive darker shades
                    alpha = max(180, 255 - i * 30)
                    darker_bg = darken_color(bg_color, 0.15 * i)
                    darker_border = darken_color(border_color, 0.1 * i)
                    label.setStyleSheet(f"""
                        QLabel {{
                            background-color: {darker_bg};
                            border: 1px solid {color_with_alpha(darker_border, alpha)};
                            border-radius: 8px;
                        }}
                    """)

            # Also update the styler for hover/selection states
            self._styler.group_color = custom_color
            logger.debug(f"[StackedThumbnailWidget] _apply_stack_colors calling _apply_thumbnail_style")
            self._apply_thumbnail_style()
            logger.debug(f"[StackedThumbnailWidget] _apply_stack_colors COMPLETE")
        except Exception as e:
            logger.error(f"[StackedThumbnailWidget] _apply_stack_colors error: {e}", exc_info=True)

    def _setup_ui(self):
        """Setup the widget UI with fanned card effect."""
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QVBoxLayout, QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor

        # Calculate size with room for fanned stack effect and label
        stack_depth = min(self._count - 1, 3)  # Show up to 3 stacked layers
        # Fanned effect needs more horizontal space
        fan_offset = 6  # Horizontal offset per card
        vertical_offset = 3  # Smaller vertical offset
        total_h_offset = stack_depth * fan_offset
        total_v_offset = stack_depth * vertical_offset
        width = self.THUMBNAIL_SIZE[0] + 16 + total_h_offset
        height = self.THUMBNAIL_SIZE[1] + 35 + total_v_offset

        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8 + total_h_offset, 5)
        layout.setSpacing(4)

        # Thumbnail container (holds the fanned stack effect)
        self.thumbnail_container = QWidget()
        self.thumbnail_container.setFixedSize(
            self.THUMBNAIL_SIZE[0] + total_h_offset,
            self.THUMBNAIL_SIZE[1] + total_v_offset
        )
        self.thumbnail_container.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.thumbnail_container)

        # Create fanned card labels (back to front)
        self._stack_labels = []
        for i in range(stack_depth, -1, -1):
            label = QLabel(self.thumbnail_container)
            label.setFixedSize(*self.THUMBNAIL_SIZE)
            # Fan out horizontally more than vertically
            x_offset = i * fan_offset
            y_offset = i * vertical_offset
            label.move(x_offset, y_offset)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._stack_labels.append(label)

        # The top label shows the actual thumbnail
        self.thumbnail_label = self._stack_labels[-1] if self._stack_labels else None

        # Apply initial colors (will use group_color if provided, else defaults)
        self._apply_stack_colors(self._group_color)

        # Add drop shadow to top card for depth
        if self.thumbnail_label:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(12)
            shadow.setXOffset(3)
            shadow.setYOffset(3)
            shadow.setColor(QColor(0, 0, 0, 80))
            self.thumbnail_label.setGraphicsEffect(shadow)

        # Count badge (top-right corner) - outline style
        self.count_badge = QLabel(self.thumbnail_container)
        self.count_badge.setText(str(self._count))
        self.count_badge.setAlignment(Qt.AlignCenter)
        self.count_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.5);
                color: rgba(91, 163, 255, 0.95);
                border-radius: 10px;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 6px;
                border: 2px solid rgba(91, 163, 255, 0.7);
            }
        """)
        # Size based on digit count
        badge_width = max(22, 10 + len(str(self._count)) * 8)
        self.count_badge.setFixedSize(badge_width, 20)
        # Position at top-right of the top card (keep inside container bounds)
        badge_x = self.THUMBNAIL_SIZE[0] - badge_width - 4
        self.count_badge.move(badge_x, 4)
        self.count_badge.raise_()
        self.count_badge.setAttribute(Qt.WA_TransparentForMouseEvents)

        # Filename label (shows stack name) - cleaner style
        display_name = self.stack_id if len(self.stack_id) <= 25 else self.stack_id[:22] + "..."
        self.filename_label = QLabel(display_name)
        self.filename_label.setAlignment(Qt.AlignCenter)
        self.filename_label.setStyleSheet("""
            color: #c0c0c0;
            font-size: 10px;
            padding: 2px 4px;
        """)
        self.filename_label.setWordWrap(True)
        self.filename_label.setMaximumWidth(self.THUMBNAIL_SIZE[0] + 10)
        self.filename_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.filename_label)

        # Set initial placeholder
        if self.thumbnail_label:
            self.thumbnail_label.setPixmap(self._create_placeholder("..."))

    def _create_placeholder(self, text):
        """Create a placeholder pixmap with modern styling."""
        from PySide6.QtGui import QPainter, QColor, QPixmap, QPainterPath, QBrush, QPen

        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw rounded rectangle background
        # Blue for items with metadata, grey for items without
        bg_color = "#1e3a5f" if self._has_metadata else "#2d3139"
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.THUMBNAIL_SIZE[0], self.THUMBNAIL_SIZE[1], 8, 8)
        painter.fillPath(path, QBrush(QColor(bg_color)))

        # Draw text
        painter.setPen(QColor("#666666"))
        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()
        return pixmap

    def showEvent(self, event):
        """Trigger thumbnail loading when widget becomes visible."""
        super().showEvent(event)
        # Load thumbnail shortly after becoming visible
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self.load_thumbnail_if_needed)

    def update_items(self, items):
        """Update the items in this stack without recreating the widget.

        Used for incremental updates when new items are added to the stack.

        Args:
            items: New list of item dicts
        """
        if not items:
            return

        # Check if anything actually changed
        new_paths = set(item['path'] for item in items)
        old_paths = set(item['path'] for item in self._items)
        if new_paths == old_paths:
            return

        # Update internal state
        self._items = items
        self._count = len(items)
        self._top_item = items[0]
        # Recalculate metadata status and model type
        self._has_metadata = self._check_items_have_metadata(items)
        self._is_top_item_model = self._top_item and self._top_item.get('type') == 'model'

        # Update count badge
        self.count_badge.setText(str(self._count))
        badge_width = max(22, 10 + len(str(self._count)) * 8)
        self.count_badge.setFixedSize(badge_width, 20)

        # Update tooltip
        self.setToolTip(f"{self.stack_id}\n{self._count} items - Click to expand")

        # If expanded, update the expanded view
        if self._is_expanded and self._expanded_widgets:
            # Close and reopen to refresh with new items
            self.collapse(animated=False)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self.expand)
        else:
            # Update top thumbnail if we have a new top item
            self._thumbnail_loaded = False
            self.load_thumbnail_if_needed()

    def load_thumbnail_if_needed(self):
        """Load the thumbnail for the top item if not already loaded."""
        from shiboken6 import isValid
        if not isValid(self) or self._thumbnail_loaded or not self._top_item:
            return

        self._thumbnail_loaded = True

        # Load thumbnail for the top item
        path = self._top_item['path']
        file_type = self._top_item.get('type', 'image')

        if file_type == 'model':
            # For 3D models, try to get cached thumbnail
            self._load_model_thumbnail(path)
        else:
            # For images, load scaled version
            self._load_image_thumbnail(path)

    def _load_image_thumbnail(self, path):
        """Load an image thumbnail."""
        from PySide6.QtCore import QThreadPool
        from PySide6.QtGui import QPixmap
        from workers import Worker

        # Check in-memory cache first (fast path)
        try:
            from ui_components import get_cached_image_thumbnail
            cached_data = get_cached_image_thumbnail(path)
            if cached_data:
                pixmap = QPixmap()
                pixmap.loadFromData(cached_data)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        *self.THUMBNAIL_SIZE,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self._on_thumbnail_loaded(scaled)
                    return
        except ImportError:
            pass  # Cache not available, load from disk

        def load_scaled_image(image_path):
            from PySide6.QtCore import QBuffer, QIODevice

            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                return None
            scaled = pixmap.scaled(
                *self.THUMBNAIL_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            # Also cache as bytes for ThumbnailWidget reuse
            try:
                from ui_components import cache_image_thumbnail, ThumbnailWidget
                buffer = QBuffer()
                buffer.open(QIODevice.WriteOnly)
                # Cache at ThumbnailWidget size for consistency
                cache_scaled = pixmap.scaled(
                    ThumbnailWidget.THUMBNAIL_SIZE[0],
                    ThumbnailWidget.THUMBNAIL_SIZE[1],
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                cache_scaled.save(buffer, "PNG")
                cache_image_thumbnail(image_path, buffer.data().data())
            except (ImportError, Exception):
                pass  # Caching failed, continue anyway
            return scaled

        # Load on worker thread - store reference to prevent GC
        self._load_worker = Worker(load_scaled_image, path)
        self._load_worker.signals.result.connect(self._on_thumbnail_loaded)
        QThreadPool.globalInstance().start(self._load_worker)

    def _load_model_thumbnail(self, path):
        """Load a 3D model thumbnail from cache or generate it."""
        try:
            from geo.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()

            # Try to get cached thumbnail (returns QPixmap)
            cached = service.get_cached_thumbnail(path)
            if cached and not cached.isNull():
                from PySide6.QtCore import Qt
                scaled = cached.scaled(
                    *self.THUMBNAIL_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._on_thumbnail_loaded(scaled)
                return

            # Show placeholder while generating
            self._show_model_placeholder()

            # Request async thumbnail generation
            self._generate_model_thumbnail_async(path, service)
        except ImportError:
            self._show_model_placeholder()

    def _generate_model_thumbnail_async(self, path, service):
        """Generate model thumbnail on main thread (Three.js viewer requires it)."""
        from PySide6.QtCore import QTimer

        # Check if already pending
        if service.is_pending(path):
            return

        service.set_pending(path, True)

        # Store path and service for the callback
        self._pending_model_path = path
        self._pending_model_service = service

        # Schedule generation on main thread after a short delay
        # This allows UI to remain responsive
        QTimer.singleShot(100, self._generate_model_thumbnail_on_main_thread)

    def _generate_model_thumbnail_on_main_thread(self):
        """Generate model thumbnail - must run on main thread for Three.js viewer."""
        from shiboken6 import isValid

        if not isValid(self):
            return

        path = getattr(self, '_pending_model_path', None)
        service = getattr(self, '_pending_model_service', None)

        if not path or not service:
            return

        try:
            pixmap = service.generate_thumbnail_sync(path)
            self._on_model_thumbnail_generated(pixmap, path, service)
        except Exception as e:
            self._on_model_thumbnail_error(path, service, str(e))

    def _on_model_thumbnail_generated(self, pixmap, path, service):
        """Handle model thumbnail generation completion."""
        from shiboken6 import isValid
        service.set_pending(path, False)

        # Check if widget is still valid
        if not isValid(self):
            return

        if pixmap and not pixmap.isNull():
            from PySide6.QtCore import Qt
            scaled = pixmap.scaled(
                *self.THUMBNAIL_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self._on_thumbnail_loaded(scaled)
        else:
            logger.warning("Model thumbnail generation returned null for: %s", path)

    def _on_model_thumbnail_error(self, path, service, error_msg=""):
        """Handle model thumbnail generation error."""
        service.set_pending(path, False)
        logger.error("Model thumbnail error for %s: %s", path, error_msg)

    def _show_model_placeholder(self):
        """Show a 3D model placeholder with modern styling."""
        from PySide6.QtGui import QPainter, QColor, QPen, QPixmap, QPainterPath, QBrush

        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw rounded rectangle background
        # Use dominant color if available, otherwise grey for models
        dominant = self._get_dominant_color() if hasattr(self, '_get_dominant_color') else None
        if dominant and dominant != "#4a9eff":  # Not default blue
            # Derive dark background from dominant color
            hex_color = dominant.lstrip('#')
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            bg_color = f"#{int(r*0.3):02x}{int(g*0.3):02x}{int(b*0.3):02x}"
            icon_color = dominant
        else:
            bg_color = "#2a3040"  # Grey for models
            icon_color = "#4a9eff"

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.THUMBNAIL_SIZE[0], self.THUMBNAIL_SIZE[1], 8, 8)
        painter.fillPath(path, QBrush(QColor(bg_color)))

        # Draw a simple 3D cube icon
        painter.setPen(QPen(QColor(icon_color), 2))
        center_x, center_y = 75, 65
        size = 28
        offset = 10
        # Front face
        painter.drawRect(center_x - size//2, center_y - size//2, size, size)
        # Top edge lines
        painter.drawLine(center_x - size//2, center_y - size//2,
                        center_x - size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x + size//2, center_y - size//2,
                        center_x + size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x - size//2 + offset, center_y - size//2 - offset,
                        center_x + size//2 + offset, center_y - size//2 - offset)
        # Side edge lines
        painter.drawLine(center_x + size//2, center_y + size//2,
                        center_x + size//2 + offset, center_y + size//2 - offset)
        painter.drawLine(center_x + size//2 + offset, center_y - size//2 - offset,
                        center_x + size//2 + offset, center_y + size//2 - offset)

        # Draw "3D" text
        painter.setPen(QColor("#666666"))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(0, 100, self.THUMBNAIL_SIZE[0], 25, Qt.AlignCenter, "3D Model")
        painter.end()

        if self.thumbnail_label:
            self.thumbnail_label.setPixmap(pixmap)

    def _on_thumbnail_loaded(self, pixmap):
        """Handle thumbnail load completion."""
        if pixmap and self.thumbnail_label:
            self.thumbnail_label.setPixmap(pixmap)
            # Apply current style state
            self._apply_thumbnail_style()

    def _apply_thumbnail_style(self):
        """Apply the appropriate style based on current state using unified styler."""
        try:
            logger.debug(f"[StackedThumbnailWidget] _apply_thumbnail_style START")
            from shiboken6 import isValid
            if not isValid(self):
                logger.debug(f"[StackedThumbnailWidget] _apply_thumbnail_style widget invalid, returning")
                return
            if self.thumbnail_label and not self._is_expanded:
                if not isValid(self.thumbnail_label):
                    logger.debug(f"[StackedThumbnailWidget] _apply_thumbnail_style thumbnail_label invalid, returning")
                    return
                drop_hover = getattr(self, '_drop_highlight_active', False)
                style = self._styler.get_style(
                    selected=self._is_selected,
                    hover=self._is_hovered,
                    drop_hover=drop_hover
                )
                logger.debug(f"[StackedThumbnailWidget] _apply_thumbnail_style setting stylesheet")
                self.thumbnail_label.setStyleSheet(style)
                logger.debug(f"[StackedThumbnailWidget] _apply_thumbnail_style stylesheet set")

                # Update shadow based on hover state
                effect = self.thumbnail_label.graphicsEffect()
                if effect:
                    from PySide6.QtGui import QColor
                    if self._is_hovered:
                        effect.setBlurRadius(16)
                        # Use dominant color for shadow if available
                        dominant = self._get_dominant_color() if hasattr(self, '_get_dominant_color') else "#4a9eff"
                        hex_color = dominant.lstrip('#')
                        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
                        effect.setColor(QColor(r, g, b, 60))
                    else:
                        effect.setBlurRadius(12)
                        effect.setColor(QColor(0, 0, 0, 80))
            logger.debug(f"[StackedThumbnailWidget] _apply_thumbnail_style COMPLETE")
        except Exception as e:
            logger.error(f"[StackedThumbnailWidget] _apply_thumbnail_style error: {e}", exc_info=True)

    def enterEvent(self, event):
        """Handle mouse enter - show hover state."""
        super().enterEvent(event)
        self._is_hovered = True
        self._apply_thumbnail_style()

    def leaveEvent(self, event):
        """Handle mouse leave - restore normal state."""
        super().leaveEvent(event)
        self._is_hovered = False
        self._apply_thumbnail_style()

    def mousePressEvent(self, event):
        """Handle click - selection based on modifiers, double-click for expansion."""
        from PySide6.QtWidgets import QApplication
        # Use QApplication.keyboardModifiers() for more reliable modifier detection
        mods = QApplication.keyboardModifiers()
        if event.button() == Qt.LeftButton:
            # Store drag start position for potential drag operation
            self._handle_drag_press(event)

            # Check for shift-click (range selection)
            if mods & Qt.ShiftModifier:
                if self._gallery_tab and self._top_item:
                    self._gallery_tab._on_shift_click_selection(self._top_item['path'])
            # Check for ctrl-click (toggle selection)
            elif mods & Qt.ControlModifier:
                self.set_selected(not self._is_selected)
            else:
                # Plain left-click: clear selection and select only this stack
                if self._gallery_tab:
                    self._gallery_tab._clear_selection()
                self.set_selected(True)
                self.clicked.emit(self.stack_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for drag initiation."""
        if self._handle_drag_move(event):
            return  # Drag was started
        super().mouseMoveEvent(event)

    def _get_drag_paths(self):
        """Return all paths in the stack for dragging."""
        return [item['path'] for item in self._items]

    def _get_drag_pixmap(self, paths):
        """Create drag pixmap using our thumbnail if available."""
        # Use our stacked thumbnail visualization
        if self.thumbnail_label:
            pixmap = self.thumbnail_label.pixmap()
            if pixmap and not pixmap.isNull():
                return pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return create_drag_pixmap(paths)

    # --- Drop target methods ---
    def _on_files_dropped(self, paths):
        """Handle files dropped on this stack - add to group if this is a group stack."""
        # Only emit if this is a group stack (stack_id starts with group indicator)
        if not self.stack_id.startswith('🏷'):
            # Not a group stack - ignore drops
            logger.debug(f"[StackedThumbnailWidget] Drop ignored, not a group stack: {self.stack_id}")
            return

        # Filter out items already in this stack
        existing_paths = set(item['path'] for item in self._items)
        new_paths = [p for p in paths if p not in existing_paths]
        if not new_paths:
            return

        # Extract group ID from stack_id (format: "🏷 GroupName")
        # The actual group_id is looked up by the handler
        logger.info(f"[StackedThumbnailWidget] Add to group requested: {self.stack_id}, {len(new_paths)} items")
        self.add_to_group_requested.emit(self.stack_id, new_paths)

    def _show_drop_highlight(self, show):
        """Show or hide drop highlight visual feedback."""
        try:
            logger.debug(f"[StackedThumbnailWidget] _show_drop_highlight START show={show} stack_id={self.stack_id}")
            from shiboken6 import isValid
            valid = isValid(self)
            logger.debug(f"[StackedThumbnailWidget] _show_drop_highlight isValid={valid}")
            if not valid:
                logger.debug(f"[StackedThumbnailWidget] _show_drop_highlight widget invalid, returning")
                return
            visible = self.isVisible()
            logger.debug(f"[StackedThumbnailWidget] _show_drop_highlight isVisible={visible}")
            # Skip style update if widget is not visible (e.g., tab switched)
            if not visible:
                logger.debug(f"[StackedThumbnailWidget] _show_drop_highlight not visible, skipping style update")
                self._drop_highlight_active = show
                return
            self._drop_highlight_active = show
            logger.debug(f"[StackedThumbnailWidget] _show_drop_highlight calling _apply_stack_colors")
            # Use cached group color instead of recalculating
            if hasattr(self, '_apply_stack_colors'):
                self._apply_stack_colors(self._group_color)
            logger.debug(f"[StackedThumbnailWidget] _show_drop_highlight COMPLETE")
        except Exception as e:
            logger.error(f"[StackedThumbnailWidget] _show_drop_highlight error: {e}", exc_info=True)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click - toggle expansion."""
        if event.button() == Qt.LeftButton:
            self.toggle_expansion()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Show batch context menu for all items in the stack."""
        from PySide6.QtWidgets import QMenu

        if not self._gallery_tab or not self._items:
            return

        menu = QMenu(self)
        count = len(self._items)

        # Check if there's a multi-selection active
        selected_count = len(self._gallery_tab._selected_items) if hasattr(self._gallery_tab, '_selected_items') else 0
        has_multi_selection = selected_count > count  # More selected than just this stack

        # Header showing stack info
        if has_multi_selection:
            header_action = menu.addAction(f"Selection: {selected_count} items selected")
        else:
            header_action = menu.addAction(f"Stack: {self.stack_id} ({count} items)")
        header_action.setEnabled(False)
        menu.addSeparator()

        # Like/Group options (for all items in the stack)
        favorites_manager = getattr(self._gallery_tab, '_favorites_manager', None)
        if favorites_manager:
            # Get paths to operate on (selected items or all items in stack)
            if has_multi_selection:
                target_paths = list(self._gallery_tab._selected_items)
            else:
                target_paths = [item['path'] for item in self._items]

            # Like toggle - check if all are liked
            all_liked = all(favorites_manager.is_liked(p) for p in target_paths)
            if all_liked:
                like_action = menu.addAction(f"♥ Unlike All ({len(target_paths)})")
                like_action.triggered.connect(lambda: self._unlike_items(target_paths))
            else:
                like_action = menu.addAction(f"♡ Like All ({len(target_paths)})")
                like_action.triggered.connect(lambda: self._like_items(target_paths))

            # Groups submenu
            groups_menu = menu.addMenu("Add to Group")
            groups = favorites_manager.get_groups()

            for group in groups:
                action = groups_menu.addAction(f"● {group.name}")
                action.triggered.connect(
                    lambda checked, gid=group.group_id, paths=target_paths: self._add_to_group(paths, gid)
                )

            if groups:
                groups_menu.addSeparator()

            new_group_action = groups_menu.addAction("+ New Group...")
            new_group_action.triggered.connect(lambda: self._create_new_group(target_paths))

            menu.addSeparator()

        # Expand/Collapse
        if self._is_expanded:
            collapse_action = menu.addAction("Collapse Stack")
            collapse_action.triggered.connect(self.collapse)
        else:
            expand_action = menu.addAction("Expand Stack")
            expand_action.triggered.connect(self.expand)

        menu.addSeparator()

        # View all items in stack
        view_action = menu.addAction(f"View All ({count} items)")
        view_action.triggered.connect(self._view_all_items)

        # Properties for top item
        menu.addSeparator()
        properties_action = menu.addAction("Properties (Top Item)")
        properties_action.triggered.connect(self._show_properties)

        # Publish all to AYON
        menu.addSeparator()
        if has_multi_selection:
            publish_action = menu.addAction(f"Publish Selected ({selected_count} items)")
            publish_action.triggered.connect(self._publish_selected_items)
        else:
            publish_action = menu.addAction(f"Publish All to AYON ({count} items)")
            publish_action.triggered.connect(self._publish_all_items)

        # Delete - use multi-selection if active
        menu.addSeparator()
        if has_multi_selection:
            delete_action = menu.addAction(f"Delete Selected ({selected_count} items)")
            delete_action.triggered.connect(self._delete_selected_items)
        else:
            delete_action = menu.addAction(f"Delete All ({count} items)")
            delete_action.triggered.connect(self._delete_all_items)

        # Check if editable
        is_editable = self._gallery_tab._is_own_gallery() if hasattr(self._gallery_tab, '_is_own_gallery') else True
        if not is_editable:
            delete_action.setEnabled(False)
            delete_action.setText(f"Delete (view only)")

        menu.exec_(self.mapToGlobal(event.pos()))
        event.accept()

    def _view_all_items(self):
        """Open viewer for all items in the stack."""
        if not self._gallery_tab or not self._items:
            return

        # Get all paths from stack items
        paths = [item['path'] for item in self._items]

        # Use gallery tab's viewer if available
        if hasattr(self._gallery_tab, '_open_viewer'):
            # Open first item, the viewer can navigate through the rest
            self._gallery_tab._open_viewer(paths[0])

    def _publish_all_items(self):
        """Publish all items in the stack to AYON."""
        if not self._gallery_tab or not self._items:
            return

        # Get all paths from stack items
        paths = [item['path'] for item in self._items]

        # Use gallery tab's publish handler if available
        if hasattr(self._gallery_tab, '_publish_items'):
            self._gallery_tab._publish_items(paths)
        elif hasattr(self._gallery_tab, '_on_publish_selected'):
            # Temporarily set selected items to our stack items
            original_selection = self._gallery_tab._selected_items.copy()
            self._gallery_tab._selected_items = set(paths)
            self._gallery_tab._on_publish_selected()
            self._gallery_tab._selected_items = original_selection

    def _delete_all_items(self):
        """Delete all items in the stack."""
        from PySide6.QtWidgets import QMessageBox

        if not self._gallery_tab or not self._items:
            return

        # Get all paths from stack items
        paths = [item['path'] for item in self._items]
        count = len(paths)

        # Confirm deletion
        parent_window = get_active_window()

        reply = QMessageBox.question(
            parent_window, "Delete Stack",
            f"Are you sure you want to delete all {count} items in this stack?\n\n"
            f"Stack: {self.stack_id}\n\n"
            "This will permanently delete the files from disk.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Use gallery tab's delete handler if available
        if hasattr(self._gallery_tab, '_delete_items'):
            self._gallery_tab._delete_items(paths)
        elif hasattr(self._gallery_tab, '_on_delete_selected'):
            # Temporarily set selected items to our stack items
            original_selection = self._gallery_tab._selected_items.copy()
            self._gallery_tab._selected_items = set(paths)
            self._gallery_tab._on_delete_selected()
            self._gallery_tab._selected_items = original_selection

    def _delete_selected_items(self):
        """Delete all selected items across all selected stacks."""
        if not self._gallery_tab:
            return

        # Use the gallery tab's delete selected handler
        if hasattr(self._gallery_tab, '_on_delete_selected'):
            self._gallery_tab._on_delete_selected()

    def _publish_selected_items(self):
        """Publish all selected items across all selected stacks."""
        if not self._gallery_tab:
            return

        # Use the gallery tab's publish selected handler
        if hasattr(self._gallery_tab, '_on_publish_selected'):
            self._gallery_tab._on_publish_selected()

    def _like_items(self, paths):
        """Like multiple items."""
        favorites_manager = getattr(self._gallery_tab, '_favorites_manager', None)
        if not favorites_manager:
            return

        favorites_manager.like_items(paths)
        self._gallery_tab._refresh_favorites_state()
        if hasattr(self._gallery_tab, 'show_status_message'):
            self._gallery_tab.show_status_message(f"♥ Liked {len(paths)} items")

    def _unlike_items(self, paths):
        """Unlike multiple items."""
        favorites_manager = getattr(self._gallery_tab, '_favorites_manager', None)
        if not favorites_manager:
            return

        favorites_manager.unlike_items(paths)
        self._gallery_tab._refresh_favorites_state()
        if hasattr(self._gallery_tab, 'show_status_message'):
            self._gallery_tab.show_status_message(f"Unliked {len(paths)} items")

    def _add_to_group(self, paths, group_id):
        """Add items to a group."""
        favorites_manager = getattr(self._gallery_tab, '_favorites_manager', None)
        if not favorites_manager:
            return

        favorites_manager.add_items_to_group(paths, group_id)
        group = favorites_manager.get_group(group_id)
        self._gallery_tab._refresh_favorites_state()
        if group and hasattr(self._gallery_tab, 'show_status_message'):
            self._gallery_tab.show_status_message(f"Added {len(paths)} items to {group.name}")

    def _create_new_group(self, paths):
        """Create a new group and add items to it."""
        favorites_manager = getattr(self._gallery_tab, '_favorites_manager', None)
        if not favorites_manager:
            return

        from dialogs import GroupEditorDialog
        dialog = GroupEditorDialog(parent=self)
        if dialog.exec_():
            name, color = dialog.get_result()
            if name:
                group_id = favorites_manager.create_group(name, color)
                favorites_manager.add_items_to_group(paths, group_id)
                self._gallery_tab._refresh_favorites_state()
                if hasattr(self._gallery_tab, 'show_status_message'):
                    self._gallery_tab.show_status_message(f"Created '{name}' with {len(paths)} items")

    def _show_properties(self):
        """Show properties for the top item in the stack."""
        if not self._top_item:
            return
        
        try:
            import os

            parent_window = get_active_window()

            # Import here to avoid circular imports
            from properties_dialog import PropertiesDialog
            
            # Get top item path and metadata
            item_path = self._top_item['path']
            output_dir = os.path.dirname(item_path)
            
            # Try to load metadata
            metadata = {}
            try:
                from comfyui.metadata import get_item_metadata
                filename = os.path.basename(item_path)
                metadata = get_item_metadata(output_dir, filename) or {}
            except Exception as e:
                logger.warning("Could not load metadata for stack top item: %s", e)
            
            dialog = PropertiesDialog(
                item_path, 
                output_dir, 
                metadata=metadata,
                parent=parent_window
            )
            
            dialog.exec()
        except Exception as e:
            logger.error("Error opening properties dialog for stack: %s", e, exc_info=True)

    def toggle_expansion(self):
        """Toggle between expanded and collapsed state."""
        if self._is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        """Expand the stack by inserting thumbnails directly into the main flow layout."""
        from shiboken6 import isValid
        if not isValid(self) or self._is_expanded:
            return

        self._cancel_animations()
        self._is_expanded = True
        self.expanded.emit(self.stack_id, True)

        # Hide the count badge when expanded
        self.count_badge.hide()

        # Get the flow layout from gallery tab
        if not self._gallery_tab or not hasattr(self._gallery_tab, '_flow_layout'):
            return

        flow_layout = self._gallery_tab._flow_layout

        # Find our position in the layout
        my_index = -1
        for i in range(flow_layout.count()):
            item = flow_layout.itemAt(i)
            if item and item.widget() == self:
                my_index = i
                break

        if my_index < 0:
            return

        # Record pre-insertion positions of all existing widgets
        self._pre_expand_positions = {}
        for i in range(flow_layout.count()):
            layout_item = flow_layout.itemAt(i)
            if layout_item and layout_item.widget():
                w = layout_item.widget()
                self._pre_expand_positions[w] = w.pos()

        # Create thumbnail widgets and insert them right after the stack
        from ui_components import ThumbnailWidget
        import os

        is_editable = False
        if self._gallery_tab:
            is_editable = self._gallery_tab._is_own_gallery()

        container = self._gallery_tab.ui.galleryThumbnailContainer
        self._expanded_widgets = []

        for idx, item in enumerate(self._items):
            path = item['path']
            file_type = item.get('type', 'image')
            item_output_dir = os.path.dirname(path)
            has_metadata = item.get('has_metadata', False)

            # Use unified ThumbnailWidget
            thumb = ThumbnailWidget(
                path,
                item_type=file_type,
                parent=container,
                output_dir=item_output_dir,
                editable=is_editable,
                is_new=False,
                gallery_tab=self._gallery_tab,
                has_metadata=has_metadata
            )

            # Set favorites manager so thumbnail knows about likes/groups
            if self._favorites_manager:
                thumb.set_favorites_manager(self._favorites_manager)

            # Connect common signals
            thumb.clicked.connect(lambda p=path, i=item: self.thumbnail_clicked.emit(p, i))
            thumb.deleted.connect(self._on_item_deleted_in_stack)
            thumb.viewed.connect(self._gallery_tab._on_item_viewed)
            thumb.selection_changed.connect(self._gallery_tab._on_selection_changed)

            # Connect image-specific signals
            if file_type == 'image':
                thumb.fullscreen_requested.connect(
                    lambda img_path=path: self._gallery_tab._open_viewer(img_path, fullscreen=True)
                )

            # Mark as expanded widget for tracking
            thumb._from_expanded_stack = self.stack_id

            # Insert right after the stack widget
            flow_layout.insertWidget(my_index + 1 + idx, thumb)
            self._expanded_widgets.append(thumb)

        # Make expanded widgets invisible immediately so they don't flash at final positions
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        for widget in self._expanded_widgets:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)

        # Trigger layout update so positions are calculated
        flow_layout.invalidate()
        container.updateGeometry()

        # Start slide animation after layout settles, load thumbnails immediately
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._start_expand_animation)
        QTimer.singleShot(0, self._load_expanded_thumbnails)

    def _load_expanded_thumbnails(self):
        """Load thumbnails for expanded widgets."""
        from shiboken6 import isValid
        if not isValid(self):
            return
        for thumb in getattr(self, '_expanded_widgets', []):
            if hasattr(thumb, 'load_thumbnail_if_needed'):
                thumb.load_thumbnail_if_needed()

    def _cancel_animations(self):
        """Cancel any running expand/collapse animations and reset layout guard."""
        for anim in getattr(self, '_expand_animations', []):
            anim.stop()
        self._expand_animations = []

        for anim in getattr(self, '_collapse_animations', []):
            anim.stop()
        self._collapse_animations = []

        for anim in getattr(self, '_bg_fade_animations', []):
            anim.stop()
        self._bg_fade_animations = []

        # Reset layout guard and replay any missed layout
        if self._gallery_tab and hasattr(self._gallery_tab, '_flow_layout'):
            self._gallery_tab._flow_layout.end_animation()

        # Remove leftover opacity effects from expanded widgets
        for widget in getattr(self, '_expanded_widgets', []):
            try:
                if widget.graphicsEffect():
                    widget.setGraphicsEffect(None)
            except RuntimeError:
                pass

    def _start_expand_animation(self):
        """Slide expanded widgets horizontally from the stack position to their layout positions."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer, QPoint
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from shiboken6 import isValid

        if not isValid(self) or not self._is_expanded or not self._expanded_widgets:
            return

        flow_layout = self._gallery_tab._flow_layout

        # Record post-layout positions of all widgets
        post_positions = {}
        for i in range(flow_layout.count()):
            layout_item = flow_layout.itemAt(i)
            if layout_item and layout_item.widget():
                w = layout_item.widget()
                post_positions[w] = w.pos()

        # Block layout from overriding positions during animation
        flow_layout.begin_animation()

        stack_pos = self.pos()
        duration = 300
        stagger = 40
        max_animated = 20
        self._expand_animations = []

        # Animate expanded widgets: slide horizontally from stack X to final X + fade in
        for idx, widget in enumerate(self._expanded_widgets[:max_animated]):
            final_pos = post_positions.get(widget, widget.pos())

            # Set initial state: at stack X but final Y (horizontal-only animation)
            opacity_effect = QGraphicsOpacityEffect(widget)
            opacity_effect.setOpacity(0.0)
            widget.setGraphicsEffect(opacity_effect)
            start_pos = QPoint(stack_pos.x(), final_pos.y())
            widget.move(start_pos)

            # Position animation (horizontal only - Y stays constant)
            pos_anim = create_property_animation(widget, b"pos", start_pos, final_pos, duration)

            # Opacity animation
            fade_anim = create_property_animation(opacity_effect, b"opacity", 0.0, 1.0, duration)

            self._expand_animations.extend([pos_anim, fade_anim])

            delay = idx * stagger
            QTimer.singleShot(delay, pos_anim.start)
            QTimer.singleShot(delay, fade_anim.start)

        # Animate existing widgets that shifted position (horizontal only)
        pre_positions = getattr(self, '_pre_expand_positions', {})
        for widget, old_pos in pre_positions.items():
            if widget in self._expanded_widgets or widget is self:
                continue
            new_pos = post_positions.get(widget)
            if new_pos and old_pos != new_pos:
                # Only animate if X position changed (same row)
                if old_pos.x() != new_pos.x():
                    # Keep Y constant, only animate X
                    start_pos = QPoint(old_pos.x(), new_pos.y())
                    widget.move(start_pos)
                    pos_anim = create_property_animation(widget, b"pos", start_pos, new_pos, duration)
                    pos_anim.start()
                    self._expand_animations.append(pos_anim)
                else:
                    # Y changed but X didn't - just snap to new position
                    widget.move(new_pos)

        # Schedule cleanup after all animations complete
        total_time = min(len(self._expanded_widgets), max_animated) * stagger + duration + 50
        QTimer.singleShot(total_time, self._cleanup_expand_animations)

    def _cleanup_expand_animations(self):
        """Clean up expand animation references and remove opacity effects."""
        from shiboken6 import isValid

        self._expand_animations = []
        self._pre_expand_positions = {}

        # Remove opacity effects so they don't interfere with rendering
        for widget in getattr(self, '_expanded_widgets', []):
            try:
                if isValid(widget) and widget.graphicsEffect():
                    widget.setGraphicsEffect(None)
            except RuntimeError:
                pass

        # Release layout guard and replay any missed layout
        if self._gallery_tab and hasattr(self._gallery_tab, '_flow_layout'):
            self._gallery_tab._flow_layout.end_animation()

        # Create backgrounds now that widgets are at their final positions
        if isValid(self) and self._is_expanded:
            self._create_expanded_background()

    def _create_expanded_background(self):
        """Create a background behind all expanded thumbnails using the stack's color."""
        from shiboken6 import isValid
        from PySide6.QtWidgets import QFrame
        from PySide6.QtCore import QRect

        # Check if widget and gallery tab are still valid
        if not isValid(self) or not self._gallery_tab:
            return

        # Clean up existing background first
        if self._expanded_background:
            self._expanded_background.setParent(None)
            self._expanded_background.deleteLater()
            self._expanded_background = None

        if not self._expanded_widgets:
            return

        # Check if we're still expanded (could have been collapsed during timer delay)
        if not self._is_expanded:
            return

        container = self._gallery_tab.ui.galleryThumbnailContainer

        # Create individual backgrounds for each expanded widget
        # This avoids the issue of a single bounding box covering neighboring stacks
        self._expanded_backgrounds = []
        self._bg_widget_map = {}  # widget -> bg_frame mapping for position tracking

        # Get the dominant color for this stack
        dominant_color = self._get_dominant_color()
        bg_rgba, border_rgba = self._get_background_colors(dominant_color)

        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer

        self._bg_fade_animations = []
        self._bg_padding = 4  # Store for use in eventFilter

        for idx, widget in enumerate(self._expanded_widgets):
            if not isValid(widget) or not widget.isVisible():
                continue

            geom = widget.geometry()

            # Add small padding around each widget
            padding = self._bg_padding
            bg_rect = QRect(
                int(geom.x() - padding),
                int(geom.y() - padding),
                int(geom.width() + 2 * padding),
                int(geom.height() + 2 * padding)
            )

            # Create background frame for this widget
            bg_frame = QFrame(container)
            bg_frame.setGeometry(bg_rect)
            bg_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_rgba};
                    border: 1px solid {border_rgba};
                    border-radius: 6px;
                }}
            """)

            # Lower z-order so it's behind the thumbnail
            bg_frame.lower()
            bg_frame.show()

            # Fade in from transparent
            opacity_effect = QGraphicsOpacityEffect(bg_frame)
            opacity_effect.setOpacity(0.0)
            bg_frame.setGraphicsEffect(opacity_effect)

            fade_anim = create_property_animation(opacity_effect, b"opacity", 0.0, 1.0, 200)
            self._bg_fade_animations.append(fade_anim)

            delay = idx * 30
            QTimer.singleShot(delay, fade_anim.start)

            self._expanded_backgrounds.append(bg_frame)
            self._bg_widget_map[widget] = bg_frame

            # Install event filter to track widget movement
            widget.installEventFilter(self)

        # Keep reference to first one for compatibility (collapse cleanup)
        self._expanded_background = self._expanded_backgrounds[0] if self._expanded_backgrounds else None

        # Clean up opacity effects after fade completes
        total_fade = min(len(self._expanded_backgrounds), 20) * 30 + 200 + 50
        QTimer.singleShot(total_fade, self._cleanup_bg_fade)

    def _cleanup_bg_fade(self):
        """Remove opacity effects from background frames after fade-in completes."""
        from shiboken6 import isValid
        self._bg_fade_animations = []
        for bg_frame in getattr(self, '_expanded_backgrounds', []):
            try:
                if isValid(bg_frame) and bg_frame.graphicsEffect():
                    bg_frame.setGraphicsEffect(None)
            except RuntimeError:
                pass

    def eventFilter(self, watched, event):
        """Track expanded widget movement and update background positions."""
        from PySide6.QtCore import QEvent, QRect
        from shiboken6 import isValid

        if event.type() == QEvent.Move:
            bg_frame = getattr(self, '_bg_widget_map', {}).get(watched)
            if bg_frame and isValid(bg_frame):
                padding = getattr(self, '_bg_padding', 4)
                geom = watched.geometry()
                bg_rect = QRect(
                    int(geom.x() - padding),
                    int(geom.y() - padding),
                    int(geom.width() + 2 * padding),
                    int(geom.height() + 2 * padding)
                )
                bg_frame.setGeometry(bg_rect)

        return super().eventFilter(watched, event)

    def _get_dominant_color(self):
        """Get the dominant color for this stack (group > liked > default blue)."""
        # Check common group color first
        if getattr(self, '_common_group_color', None):
            return self._common_group_color

        # Check explicit group color from stacking mode
        if self._group_color:
            return self._group_color

        # Check if all items are liked
        if getattr(self, '_is_all_liked', False):
            from core.settings_manager import get_setting
            liked_color = get_setting("gallery_liked_color")
            return liked_color or "#10b981"  # Default green

        # Default blue
        return "#4a9eff"

    def _get_background_colors(self, hex_color):
        """Convert a hex color to rgba background and border colors for the expanded background."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # Background: very transparent version of the color
        bg_rgba = f"rgba({r}, {g}, {b}, 0.12)"
        # Border: slightly more visible
        border_rgba = f"rgba({r}, {g}, {b}, 0.3)"

        return bg_rgba, border_rgba

    def collapse(self, animated=True):
        """Collapse the stack.

        Args:
            animated: If True, use slide-back animation. If False, collapse instantly
                      (used during programmatic cleanup to avoid blocking the layout).
        """
        if not self._is_expanded:
            return

        self._cancel_animations()
        self._is_expanded = False
        self.expanded.emit(self.stack_id, False)

        # Remove event filters from expanded widgets
        for widget in getattr(self, '_expanded_widgets', []):
            try:
                widget.removeEventFilter(self)
            except RuntimeError:
                pass
        self._bg_widget_map = {}

        # Remove backgrounds immediately
        for bg_frame in getattr(self, '_expanded_backgrounds', []):
            if bg_frame:
                bg_frame.setParent(None)
                bg_frame.deleteLater()
        self._expanded_backgrounds = []
        self._expanded_background = None

        if not animated or not self._gallery_tab or not hasattr(self._gallery_tab, '_flow_layout'):
            self._finish_collapse()
            return

        self._animate_collapse_slide()

    def _animate_collapse_slide(self):
        """Animate expanded widgets sliding horizontally back to the stack and other widgets reflowing."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer, QPoint
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from shiboken6 import isValid

        flow_layout = self._gallery_tab._flow_layout
        container = self._gallery_tab.ui.galleryThumbnailContainer

        # Record current positions of ALL widgets
        pre_positions = {}
        expanded_indices = []
        for i in range(flow_layout.count()):
            layout_item = flow_layout.itemAt(i)
            if layout_item and layout_item.widget():
                w = layout_item.widget()
                pre_positions[w] = w.pos()
                if w in self._expanded_widgets:
                    expanded_indices.append(i)

        # Remove expanded widgets from the layout (but keep them visible)
        for i in sorted(expanded_indices, reverse=True):
            flow_layout.takeAt(i)

        # Let layout recalculate positions for remaining widgets
        flow_layout.invalidate()
        container.updateGeometry()
        flow_layout.activate()

        # Record new positions of remaining widgets
        post_positions = {}
        for i in range(flow_layout.count()):
            layout_item = flow_layout.itemAt(i)
            if layout_item and layout_item.widget():
                w = layout_item.widget()
                post_positions[w] = w.pos()

        # Block layout during animation
        flow_layout.begin_animation()

        # Move remaining widgets back to their pre-collapse positions
        for w in post_positions:
            if w in pre_positions:
                w.move(pre_positions[w])

        stack_pos = self.pos()
        duration = 250
        self._collapse_animations = []

        # Animate expanded widgets: slide horizontally to stack X + fade out
        for widget in self._expanded_widgets:
            if not isValid(widget):
                continue

            current_pos = pre_positions.get(widget, widget.pos())
            widget.move(current_pos)
            widget.raise_()

            # Target position: stack X but keep current Y (horizontal-only animation)
            target_pos = QPoint(stack_pos.x(), current_pos.y())

            # Position animation (horizontal only, use InCubic for collapse)
            pos_anim = create_property_animation(
                widget, b"pos", current_pos, target_pos, duration, QEasingCurve.InCubic
            )

            # Opacity animation
            existing_effect = widget.graphicsEffect()
            if not isinstance(existing_effect, QGraphicsOpacityEffect):
                existing_effect = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(existing_effect)
            fade_anim = create_property_animation(
                existing_effect, b"opacity", existing_effect.opacity(), 0.0, duration, QEasingCurve.InCubic
            )

            pos_anim.start()
            fade_anim.start()
            self._collapse_animations.extend([pos_anim, fade_anim])

        # Animate remaining widgets: slide horizontally from old to new positions
        for w in post_positions:
            old_pos = pre_positions.get(w)
            new_pos = post_positions[w]
            if old_pos and old_pos != new_pos:
                # Only animate if X position changed
                if old_pos.x() != new_pos.x():
                    # Keep Y constant, only animate X
                    start_pos = QPoint(old_pos.x(), new_pos.y())
                    w.move(start_pos)
                    pos_anim = create_property_animation(w, b"pos", start_pos, new_pos, duration)
                    pos_anim.start()
                    self._collapse_animations.append(pos_anim)
                else:
                    # Y changed but X didn't - just snap to new position
                    w.move(new_pos)

        # Clean up after animation completes
        QTimer.singleShot(duration + 30, self._finish_collapse)

    def _finish_collapse(self):
        """Complete collapse by deleting expanded widgets and restoring layout."""
        from shiboken6 import isValid
        if not isValid(self):
            return
        self._collapse_animations = []

        # Delete expanded widgets
        for widget in getattr(self, '_expanded_widgets', []):
            widget.setParent(None)
            widget.deleteLater()
        self._expanded_widgets = []

        # Show the count badge again
        self.count_badge.show()

        # Release layout guard (replays any missed layout) and force fresh pass
        if self._gallery_tab and hasattr(self._gallery_tab, '_flow_layout'):
            flow_layout = self._gallery_tab._flow_layout
            container = self._gallery_tab.ui.galleryThumbnailContainer
            flow_layout.end_animation()
            flow_layout.invalidate()
            container.updateGeometry()

    def _on_item_deleted_in_stack(self, path):
        """Handle deletion of an item within the expanded stack.

        Args:
            path: Path to the deleted file
        """
        # Remove from items list
        self._items = [item for item in self._items if item['path'] != path]
        self._count = len(self._items)

        # Update count badge
        if self._count > 0:
            badge_width = max(24, 12 + len(str(self._count)) * 8)
            self.count_badge.setFixedSize(badge_width, 24)
            self.count_badge.setText(str(self._count))
            self.setToolTip(f"{self.stack_id}\n{self._count} items - Click to expand")

        # Forward to gallery tab's delete handler
        if self._gallery_tab and hasattr(self._gallery_tab, '_on_item_deleted'):
            self._gallery_tab._on_item_deleted(path)

        # If only one item left, collapse the stack
        if self._count <= 1 and self._is_expanded:
            self.collapse()

    def is_expanded(self) -> bool:
        """Return whether the stack is currently expanded."""
        return self._is_expanded

    def get_items(self) -> List[Dict]:
        """Return the list of items in this stack."""
        return self._items

    def get_count(self) -> int:
        """Return the number of items in the stack."""
        return self._count

    def get_expanded_widgets(self) -> list:
        """Return the list of expanded thumbnail widgets."""
        return getattr(self, '_expanded_widgets', [])

    def set_selected(self, selected: bool):
        """Set selection state for the entire stack.

        When selected, all items in the stack are added to the gallery's selection.
        Visual feedback is shown on the stack widget.
        """
        if self._is_selected == selected:
            return

        self._is_selected = selected

        # Update visual style using unified styler
        self._apply_thumbnail_style()

        # Update gallery selection state
        if self._gallery_tab:
            for item in self._items:
                path = item['path']
                if selected:
                    self._gallery_tab._selected_items.add(path)
                else:
                    self._gallery_tab._selected_items.discard(path)

            # Update last selected path for shift-select range functionality
            if selected and self._top_item:
                self._gallery_tab._last_selected_path = self._top_item['path']

            # Update toolbar and checkmarks
            if hasattr(self._gallery_tab, '_selection_manager'):
                self._gallery_tab._selection_manager._update_toolbar()

    def is_selected(self) -> bool:
        """Return whether the stack is currently selected."""
        return self._is_selected


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def show_popup_menu(
    parent: QWidget,
    button: QPushButton,
    items: List[Tuple[str, Any]],
    current: Any = None,
    submenus: Optional[Dict[str, List[Tuple[str, Any]]]] = None
) -> Optional[Any]:
    """
    Show a popup menu below a button and return the selected data.

    Args:
        parent: Parent widget for the menu
        button: Button to position the menu below
        items: List of (display_name, data) tuples for menu items
        current: Currently selected data value (will show checkmark)
        submenus: Optional dict of folder_name -> items for nested submenus

    Returns:
        Selected item's data, or None if cancelled
    """
    menu = QMenu(parent)

    for display, data in items:
        action = menu.addAction(display)
        action.setData(data)
        if data == current:
            action.setCheckable(True)
            action.setChecked(True)

    if submenus:
        for folder, folder_items in submenus.items():
            submenu = menu.addMenu(folder)
            for display, data in folder_items:
                action = submenu.addAction(display)
                action.setData(data)
                if data == current:
                    action.setCheckable(True)
                    action.setChecked(True)

    result = menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))
    return result.data() if result else None
