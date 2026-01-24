"""
Small reusable UI widgets and utilities.

Contains simple widgets and helper functions used across the application.
"""
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtWidgets import (
    QWidget, QMenu, QPushButton, QHBoxLayout, QLabel, QSizePolicy
)
from PySide6.QtCore import Signal, Qt
from thumbnail_styles import ThumbnailStyler


# ============================================================================
# GALLERY SECTION HEADER WIDGET (legacy - kept for compatibility)
# ============================================================================

class GallerySectionHeader(QWidget):
    """Collapsible section header for gallery grouping.

    Displays a clickable header with expand/collapse chevron, section title,
    and item count. Emits toggled signal when clicked.
    """
    toggled = Signal(str, bool)  # section_id, is_expanded

    def __init__(self, section_id: str, title: str, count: int, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.section_id = section_id
        self._expanded = expanded
        self._count = count

        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 16, 6)
        layout.setSpacing(10)

        # Chevron with animated-look icon
        self.chevron = QLabel()
        self.chevron.setFixedWidth(18)
        self._update_chevron()
        layout.addWidget(self.chevron)

        # Title - truncate long names
        display_title = title if len(title) <= 40 else title[:37] + "..."
        self.title_label = QLabel(display_title)
        self.title_label.setStyleSheet("""
            color: #d8d8d8;
            font-weight: 600;
            font-size: 12px;
        """)
        layout.addWidget(self.title_label)

        # Spacer
        layout.addStretch()

        # Count badge - pill style
        self.count_label = QLabel(str(count))
        self.count_label.setAlignment(Qt.AlignCenter)
        self.count_label.setStyleSheet("""
            QLabel {
                background-color: rgba(74, 158, 255, 0.15);
                color: #8ac4ff;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        self.count_label.setMinimumWidth(28)
        layout.addWidget(self.count_label)

        # Styling
        self._apply_style()

    def _apply_style(self):
        """Apply visual styling based on state."""
        if self._expanded:
            bg_color = "#2d3139"
            border_color = "#4a9eff"
            border_left = "3px"
        else:
            bg_color = "#252830"
            border_color = "#3c414b"
            border_left = "3px"

        self.setStyleSheet(f"""
            GallerySectionHeader {{
                background-color: {bg_color};
                border-radius: 6px;
                border: 1px solid {border_color};
                border-left: {border_left} solid {border_color};
            }}
            GallerySectionHeader:hover {{
                background-color: #353a45;
                border: 1px solid #5ba3ff;
                border-left: 3px solid #5ba3ff;
            }}
        """)

    def _update_chevron(self):
        """Update chevron direction based on expanded state."""
        # Use cleaner arrow icons
        arrow = "▾" if self._expanded else "▸"
        color = "#4a9eff" if self._expanded else "#666666"
        self.chevron.setText(arrow)
        self.chevron.setStyleSheet(f"color: {color}; font-size: 14px;")

    def mousePressEvent(self, event):
        """Handle click to toggle expansion."""
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self._update_chevron()
            self._apply_style()
            self.toggled.emit(self.section_id, self._expanded)
        super().mousePressEvent(event)

    def set_expanded(self, expanded: bool):
        """Set the expanded state without emitting signal."""
        if self._expanded != expanded:
            self._expanded = expanded
            self._update_chevron()
            self._apply_style()

    def is_expanded(self) -> bool:
        """Return current expanded state."""
        return self._expanded

    def update_count(self, count: int):
        """Update the item count display."""
        self._count = count
        self.count_label.setText(f"({count})")

    def sizeHint(self):
        """Return size hint with parent's width to take full row in FlowLayout."""
        from PySide6.QtCore import QSize
        # Use parent's width to take full row, with fallback to large value
        parent = self.parentWidget()
        if parent:
            # Subtract some margin for padding
            width = max(parent.width() - 20, 200)
        else:
            width = 10000  # Fallback to force full row
        return QSize(width, 32)


# ============================================================================
# STACKED THUMBNAIL WIDGET (Photo stack style grouping)
# ============================================================================

class StackedThumbnailWidget(QWidget):
    """Stacked thumbnail widget showing a pile of images with count badge.

    Displays a representative thumbnail with stacked visual effect and a count
    badge. Clicking expands/collapses the stack with card-deck animation.

    Signals:
        clicked(str): Emitted with stack_id when the stack is clicked
        expanded(str, bool): Emitted with (stack_id, is_expanded) when expansion state changes
        thumbnail_clicked(str, dict): Emitted when an expanded thumbnail is clicked (path, item)
    """
    clicked = Signal(str)  # stack_id
    expanded = Signal(str, bool)  # stack_id, is_expanded
    thumbnail_clicked = Signal(str, dict)  # path, item dict

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

    def _update_border_color(self):
        """Update thumbnail border color with priority: group > liked > stack.

        Similar to ThumbnailWidget._update_group_border().
        """
        from core.settings_manager import get_setting

        custom_color = None

        # Priority 1: Common group color (all items share a group from favorites manager)
        common_group_color = getattr(self, '_common_group_color', None)
        if common_group_color:
            custom_color = common_group_color

        # Priority 2: Explicit group color (from group stacking mode at creation)
        elif self._group_color:
            custom_color = self._group_color

        # Priority 3: Liked color (if ALL items are liked)
        elif self._is_all_liked:
            liked_color = get_setting("gallery_liked_color")
            # Default to green if no custom liked color is set
            custom_color = liked_color or "#10b981"

        # Priority 4: Stack color (if has stack_id and custom stack color in settings)
        else:
            stack_colors = get_setting("gallery_stack_colors") or {}
            stack_color = stack_colors.get(self.stack_id)
            if stack_color:
                custom_color = stack_color

        # Apply the color to all stack cards
        self._apply_stack_colors(custom_color)

    def _apply_stack_colors(self, custom_color=None):
        """Apply colors to all stack card labels.

        Args:
            custom_color: Optional hex color to use as base. If None, uses default blue/grey.
        """
        if not hasattr(self, '_stack_labels') or not self._stack_labels:
            return

        # Derive colors from custom_color or use defaults
        if custom_color:
            # Parse the custom color and create darker/lighter variants
            bg_color, border_color = self._derive_colors_from_hex(custom_color)
        elif self._is_top_item_model or not self._has_metadata:
            # Grey for 3D models and non-metadata items
            bg_color = "#2d3139"
            border_color = "#4a4a4a"
        else:
            # Blue for images with metadata
            bg_color = "#1e3a5f"
            border_color = "#4a6d8c"

        # Apply to all stack labels
        stack_depth = len(self._stack_labels) - 1
        for idx, label in enumerate(self._stack_labels):
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
                darker_bg = self._darken_color(bg_color, 0.15 * i)
                darker_border = self._darken_color(border_color, 0.1 * i)
                label.setStyleSheet(f"""
                    QLabel {{
                        background-color: {darker_bg};
                        border: 1px solid {self._color_with_alpha(darker_border, alpha)};
                        border-radius: 8px;
                    }}
                """)

        # Also update the styler for hover/selection states
        self._styler.group_color = custom_color
        self._apply_thumbnail_style()

    def _derive_colors_from_hex(self, hex_color):
        """Derive background and border colors from a hex color.

        Returns a darker background and the original as border.
        """
        # Parse hex
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # Background: darken significantly for a tinted look
        bg_r = int(r * 0.3)
        bg_g = int(g * 0.3)
        bg_b = int(b * 0.3)
        bg_color = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"

        # Border: slightly darkened original
        border_r = int(min(255, r * 0.7))
        border_g = int(min(255, g * 0.7))
        border_b = int(min(255, b * 0.7))
        border_color = f"#{border_r:02x}{border_g:02x}{border_b:02x}"

        return bg_color, border_color

    def _darken_color(self, hex_color, factor):
        """Darken a hex color by a factor (0-1)."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = max(0, int(r * (1 - factor)))
        g = max(0, int(g * (1 - factor)))
        b = max(0, int(b * (1 - factor)))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _color_with_alpha(self, hex_color, alpha):
        """Convert hex color to rgba string with alpha (0-255)."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

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

        # File type indicator (bottom-left corner)
        self.type_indicator = QLabel(self.thumbnail_container)
        self.type_indicator.setAlignment(Qt.AlignCenter)
        self.type_indicator.setFixedSize(20, 20)
        self.type_indicator.move(4, self.THUMBNAIL_SIZE[1] - 24)
        self.type_indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._apply_type_indicator()
        self.type_indicator.raise_()

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

        # Update type indicator for new top item
        self._apply_type_indicator()

        # Update count badge
        self.count_badge.setText(str(self._count))
        badge_width = max(22, 10 + len(str(self._count)) * 8)
        self.count_badge.setFixedSize(badge_width, 20)

        # Update tooltip
        self.setToolTip(f"{self.stack_id}\n{self._count} items - Click to expand")

        # If expanded, update the expanded view
        if self._is_expanded and self._expanded_widgets:
            # Close and reopen to refresh with new items
            self._collapse_stack()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._expand_stack)
        else:
            # Update top thumbnail if we have a new top item
            self._thumbnail_loaded = False
            self.load_thumbnail_if_needed()

    def load_thumbnail_if_needed(self):
        """Load the thumbnail for the top item if not already loaded."""
        if self._thumbnail_loaded or not self._top_item:
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
            from models.thumbnail_service import get_model_thumbnail_service
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
            print(f"[StackedThumbnail] Model thumbnail generation returned null for: {path}")

    def _on_model_thumbnail_error(self, path, service, error_msg=""):
        """Handle model thumbnail generation error."""
        service.set_pending(path, False)
        print(f"[StackedThumbnail] Model thumbnail error for {path}: {error_msg}")

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

    def _apply_type_indicator(self):
        """Apply the appropriate icon and style for the file type - outline style."""
        if not self._top_item:
            return
        item_type = self._top_item.get('type', 'image')
        # Type icon and color configuration (icon, border_color)
        type_config = {
            'image': ('▣', 'rgba(16, 185, 129, 0.8)'),   # Green squares
            'video': ('▶', 'rgba(239, 68, 68, 0.8)'),    # Red play triangle
            'audio': ('♫', 'rgba(168, 85, 247, 0.8)'),   # Purple music note
            'model': ('⬣', 'rgba(74, 158, 255, 0.8)'),   # Blue hexagon/cube
        }
        icon, border_color = type_config.get(item_type, ('?', 'rgba(128, 128, 128, 0.8)'))
        self.type_indicator.setText(icon)
        self.type_indicator.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(0, 0, 0, 0.4);
                color: {border_color};
                border: 1px solid {border_color};
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        self.type_indicator.show()

    def _apply_thumbnail_style(self):
        """Apply the appropriate style based on current state using unified styler."""
        if self.thumbnail_label and not self._is_expanded:
            style = self._styler.get_style(
                selected=self._is_selected,
                hover=self._is_hovered
            )
            self.thumbnail_label.setStyleSheet(style)

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
        from PySide6.QtWidgets import QMessageBox, QApplication

        if not self._gallery_tab or not self._items:
            return

        # Get all paths from stack items
        paths = [item['path'] for item in self._items]
        count = len(paths)

        # Confirm deletion
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break

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
            from PySide6.QtWidgets import QApplication
            import os
            
            parent_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'windowTitle'):
                    parent_window = widget
                    break
            
            # Import here to avoid circular imports
            from properties_dialog import PropertiesDialog
            
            # Get top item path and metadata
            item_path = self._top_item['path']
            output_dir = os.path.dirname(item_path)
            
            # Try to load metadata
            metadata = {}
            try:
                from comfyui.service import get_image_metadata
                filename = os.path.basename(item_path)
                metadata = get_image_metadata(output_dir, filename) or {}
            except Exception as e:
                print(f"Could not load metadata for stack top item: {e}")
            
            dialog = PropertiesDialog(
                item_path, 
                output_dir, 
                metadata=metadata,
                parent=parent_window
            )
            
            dialog.exec()
        except Exception as e:
            import traceback
            print(f"Error opening properties dialog for stack: {e}")
            traceback.print_exc()

    def toggle_expansion(self):
        """Toggle between expanded and collapsed state."""
        if self._is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        """Expand the stack by inserting thumbnails directly into the main flow layout."""
        if self._is_expanded:
            return

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

        # Trigger layout update
        flow_layout.invalidate()
        container.updateGeometry()

        # Create and position background after layout settles
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._load_expanded_thumbnails)
        QTimer.singleShot(150, self._create_expanded_background)

    def _load_expanded_thumbnails(self):
        """Load thumbnails for expanded widgets."""
        for thumb in getattr(self, '_expanded_widgets', []):
            if hasattr(thumb, 'load_thumbnail_if_needed'):
                thumb.load_thumbnail_if_needed()

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

        # Get the dominant color for this stack
        dominant_color = self._get_dominant_color()
        bg_rgba, border_rgba = self._get_background_colors(dominant_color)

        for widget in self._expanded_widgets:
            if not isValid(widget) or not widget.isVisible():
                continue

            geom = widget.geometry()

            # Add small padding around each widget
            padding = 4
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
            self._expanded_backgrounds.append(bg_frame)

        # Keep reference to first one for compatibility (collapse cleanup)
        self._expanded_background = self._expanded_backgrounds[0] if self._expanded_backgrounds else None

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

    def collapse(self):
        """Collapse the stack by removing the expanded thumbnails from the layout."""
        if not self._is_expanded:
            return

        self._is_expanded = False
        self.expanded.emit(self.stack_id, False)

        # Remove all background frames
        for bg_frame in getattr(self, '_expanded_backgrounds', []):
            if bg_frame:
                bg_frame.setParent(None)
                bg_frame.deleteLater()
        self._expanded_backgrounds = []
        self._expanded_background = None

        # Remove and delete expanded widgets
        for widget in getattr(self, '_expanded_widgets', []):
            widget.setParent(None)
            widget.deleteLater()
        self._expanded_widgets = []

        # Show the count badge again
        self.count_badge.show()

        # Trigger layout update
        if self._gallery_tab and hasattr(self._gallery_tab, '_flow_layout'):
            flow_layout = self._gallery_tab._flow_layout
            container = self._gallery_tab.ui.galleryThumbnailContainer
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
# EXPANDED STACK CONTAINER (Shows expanded thumbnails in a box)
# ============================================================================

class ExpandedStackContainer(QWidget):
    """Container widget that displays expanded stack items in a styled box.

    This widget is inserted into the FlowLayout after the stack, pushing
    other items down. It shows all thumbnails in a wrapped flow with a
    visible border to indicate grouping.

    Signals:
        item_deleted(str): Emitted when an item is deleted (path)
        thumbnail_clicked(str, dict): Emitted when a thumbnail is clicked (path, item)
    """
    item_deleted = Signal(str)  # path
    thumbnail_clicked = Signal(str, dict)  # path, item

    def __init__(self, stack_id: str, items: List[Dict], gallery_tab=None, parent_stack=None, parent=None):
        """Initialize the expanded container.

        Args:
            stack_id: The stack identifier
            items: List of item dicts to display
            gallery_tab: Reference to the gallery tab
            parent_stack: Reference to the parent StackedThumbnailWidget
            parent: Parent widget
        """
        super().__init__(parent)
        self.stack_id = stack_id
        self._items = items
        self._gallery_tab = gallery_tab
        self._parent_stack = parent_stack
        self._thumbnail_widgets = []

        self._setup_ui()

    def _setup_ui(self):
        """Setup the container UI with styled box and flow layout."""
        from PySide6.QtWidgets import QVBoxLayout, QFrame
        from PySide6.QtCore import QSize
        from layouts import FlowLayout

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 4, 0, 8)
        main_layout.setSpacing(0)

        # Styled container frame
        self._frame = QFrame()
        self._frame.setStyleSheet("""
            QFrame {
                background-color: rgba(74, 158, 255, 0.08);
                border: 2px solid rgba(74, 158, 255, 0.4);
                border-radius: 8px;
            }
        """)

        # Flow layout inside the frame for thumbnails
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(4)

        # Header with stack name and close button
        header = self._create_header()
        frame_layout.addWidget(header)

        # Thumbnail container with flow layout
        self._thumb_container = QWidget()
        self._flow_layout = FlowLayout(self._thumb_container, margin=4, spacing=6)
        frame_layout.addWidget(self._thumb_container)

        main_layout.addWidget(self._frame)

        # Create thumbnail widgets
        self._create_thumbnails()

        # Calculate size based on content
        self._update_size()

    def _create_header(self):
        """Create the header with stack name and collapse button."""
        from PySide6.QtWidgets import QHBoxLayout, QPushButton

        header = QWidget()
        header.setFixedHeight(28)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 4, 4)
        header_layout.setSpacing(8)

        # Stack name label
        name_label = QLabel(f"{self.stack_id}")
        name_label.setStyleSheet("""
            QLabel {
                color: #4a9eff;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        header_layout.addWidget(name_label)

        # Item count
        count_label = QLabel(f"({len(self._items)} items)")
        count_label.setStyleSheet("color: #888888; font-size: 11px;")
        header_layout.addWidget(count_label)

        header_layout.addStretch()

        # Close/collapse button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        close_btn.setToolTip("Collapse stack")
        close_btn.clicked.connect(self._on_close_clicked)
        header_layout.addWidget(close_btn)

        return header

    def _on_close_clicked(self):
        """Handle close button click - collapse the parent stack."""
        if self._parent_stack:
            self._parent_stack.collapse()

    def _create_thumbnails(self):
        """Create thumbnail widgets for all items."""
        from ui_components import ThumbnailWidget
        import os

        is_editable = False
        if self._gallery_tab:
            is_editable = self._gallery_tab._is_own_gallery()

        for item in self._items:
            path = item['path']
            file_type = item.get('type', 'image')
            item_output_dir = os.path.dirname(path)
            has_metadata = item.get('has_metadata', False)

            # Use unified ThumbnailWidget
            thumb = ThumbnailWidget(
                path,
                item_type=file_type,
                parent=self._thumb_container,
                output_dir=item_output_dir,
                editable=is_editable,
                is_new=False,
                gallery_tab=self._gallery_tab,
                has_metadata=has_metadata
            )

            # Connect common signals
            thumb.clicked.connect(lambda p=path, i=item: self.thumbnail_clicked.emit(p, i))
            thumb.deleted.connect(self._on_thumb_deleted)
            if self._gallery_tab:
                thumb.viewed.connect(self._gallery_tab._on_item_viewed)
                thumb.selection_changed.connect(self._gallery_tab._on_selection_changed)

            # Connect image-specific signals
            if file_type == 'image' and self._gallery_tab:
                thumb.fullscreen_requested.connect(
                    lambda img_path=path: self._gallery_tab._open_viewer(img_path, fullscreen=True)
                )

            self._flow_layout.addWidget(thumb)
            self._thumbnail_widgets.append(thumb)

    def _on_thumb_deleted(self, path):
        """Handle thumbnail deletion."""
        # Remove from our list
        self._items = [item for item in self._items if item['path'] != path]

        # Forward the signal
        self.item_deleted.emit(path)

        # Update size
        self._update_size()

    def _update_size(self):
        """Update container size based on content."""
        from PySide6.QtCore import QSize

        # Calculate approximate size
        # Each thumbnail is about 160x180, with 6px spacing
        thumb_width = 166  # 160 + 6 spacing
        thumb_height = 186  # 180 + 6 spacing

        # Get parent width to determine how many thumbs per row
        parent = self.parentWidget()
        if parent:
            available_width = parent.width() - 40  # margins
        else:
            available_width = 800

        thumbs_per_row = max(1, available_width // thumb_width)
        num_rows = (len(self._items) + thumbs_per_row - 1) // thumbs_per_row

        # Calculate total height: header (28) + rows * thumb_height + padding
        total_height = 28 + num_rows * thumb_height + 24  # 24 for padding

        self.setMinimumHeight(total_height)

    def load_thumbnails(self):
        """Trigger thumbnail loading for all widgets."""
        for thumb in self._thumbnail_widgets:
            if hasattr(thumb, 'load_thumbnail_if_needed'):
                thumb.load_thumbnail_if_needed()

    def sizeHint(self):
        """Return size hint to take full row width in FlowLayout."""
        from PySide6.QtCore import QSize

        parent = self.parentWidget()
        if parent:
            width = max(parent.width() - 20, 400)
        else:
            width = 10000  # Large value to force full row

        # Height based on content
        return QSize(width, self.minimumHeight() or 200)


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
