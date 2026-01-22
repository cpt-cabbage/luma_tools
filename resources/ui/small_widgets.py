"""
Small reusable UI widgets and utilities.

Contains simple widgets and helper functions used across the application.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
from PySide6.QtWidgets import (
    QWidget, QMenu, QPushButton, QFileDialog, QHBoxLayout, QLabel, QSizePolicy
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont


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

    def __init__(self, stack_id: str, items: List[Dict], parent=None, gallery_tab=None):
        """Initialize the stacked thumbnail widget.

        Args:
            stack_id: Unique identifier for this stack (usually job_prefix)
            items: List of item dicts in this stack (first item is shown on top)
            parent: Parent widget
            gallery_tab: Reference to gallery tab for creating thumbnails
        """
        super().__init__(parent)
        self.stack_id = stack_id
        self._items = items
        self._count = len(items)
        self._thumbnail_loaded = False
        self._top_item = items[0] if items else None
        self._is_expanded = False
        self._is_selected = False  # Selection state for the whole stack
        self._expanded_widgets = []  # List of expanded thumbnail widgets
        self._expanded_background = None  # Background frame behind expanded items
        self._gallery_tab = gallery_tab
        # Check if items in this stack have metadata (source_images populated)
        self._has_metadata = self._check_items_have_metadata(items)
        # Check if top item is a 3D model (uses grey border, not blue)
        self._is_top_item_model = self._top_item and self._top_item.get('type') == 'model'

        self._setup_ui()
        self.setToolTip(f"{stack_id}\n{self._count} items - Click to expand")

    def _check_items_have_metadata(self, items):
        """Check if any item in the list has metadata."""
        for item in items:
            if item.get('has_metadata', False):
                return True
        return False

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

            # Style with gradient-like depth effect
            # 3D models use grey, images use blue/grey based on metadata
            if i == 0:
                # Top card (will show thumbnail)
                if self._is_top_item_model:
                    # Grey for 3D models (no blue border)
                    label.setStyleSheet("""
                        QLabel {
                            background-color: #2d3139;
                            border: 2px solid #4a4a4a;
                            border-radius: 8px;
                        }
                    """)
                elif self._has_metadata:
                    # Blue tinted background for images with metadata
                    label.setStyleSheet("""
                        QLabel {
                            background-color: #1e3a5f;
                            border: 2px solid #4a6d8c;
                            border-radius: 8px;
                        }
                    """)
                else:
                    # Grey background for images without metadata
                    label.setStyleSheet("""
                        QLabel {
                            background-color: #2d3139;
                            border: 2px solid #4a4a4a;
                            border-radius: 8px;
                        }
                    """)
            else:
                # Background cards with varying opacity effect
                alpha = max(180, 255 - i * 30)
                if self._is_top_item_model or not self._has_metadata:
                    # Grey shades for 3D models and non-metadata items
                    shade = max(35, 50 - i * 10)
                    label.setStyleSheet(f"""
                        QLabel {{
                            background-color: rgb({shade}, {shade + 3}, {shade + 8});
                            border: 1px solid rgba(80, 85, 95, {alpha});
                            border-radius: 8px;
                        }}
                    """)
                else:
                    # Blue tinted shades for images with metadata
                    shade_r = max(20, 30 - i * 5)
                    shade_g = max(45, 58 - i * 8)
                    shade_b = max(70, 95 - i * 12)
                    label.setStyleSheet(f"""
                        QLabel {{
                            background-color: rgb({shade_r}, {shade_g}, {shade_b});
                            border: 1px solid rgba(74, 109, 140, {alpha});
                            border-radius: 8px;
                        }}
                    """)
            self._stack_labels.append(label)

        # The top label shows the actual thumbnail
        self.thumbnail_label = self._stack_labels[-1] if self._stack_labels else None

        # Add drop shadow to top card for depth
        if self.thumbnail_label:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(12)
            shadow.setXOffset(3)
            shadow.setYOffset(3)
            shadow.setColor(QColor(0, 0, 0, 80))
            self.thumbnail_label.setGraphicsEffect(shadow)

        # Count badge (top-right corner) - pill style
        self.count_badge = QLabel(self.thumbnail_container)
        self.count_badge.setText(str(self._count))
        self.count_badge.setAlignment(Qt.AlignCenter)
        self.count_badge.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5ba3ff, stop:1 #3d8bff);
                color: white;
                border-radius: 10px;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 6px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
        """)
        # Size based on digit count
        badge_width = max(22, 10 + len(str(self._count)) * 8)
        self.count_badge.setFixedSize(badge_width, 20)
        # Position at top-right of the top card
        badge_x = self.THUMBNAIL_SIZE[0] - badge_width + 4
        self.count_badge.move(badge_x, -4)
        self.count_badge.raise_()

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
        from workers import Worker

        def load_scaled_image(image_path):
            from PySide6.QtGui import QPixmap
            from PySide6.QtCore import Qt

            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                return None
            return pixmap.scaled(
                *self.THUMBNAIL_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

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
        # Blue for items with metadata, grey for items without
        bg_color = "#1e3a5f" if self._has_metadata else "#2a3040"
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.THUMBNAIL_SIZE[0], self.THUMBNAIL_SIZE[1], 8, 8)
        painter.fillPath(path, QBrush(QColor(bg_color)))

        # Draw a simple 3D cube icon
        painter.setPen(QPen(QColor("#4a9eff"), 2))
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
            # Update style to match the fanned card design
            # 3D models use grey, images use blue/grey based on metadata
            if self._is_top_item_model:
                # Grey for 3D models
                self.thumbnail_label.setStyleSheet("""
                    QLabel {
                        background-color: #2d3139;
                        border: 2px solid #4a4a4a;
                        border-radius: 8px;
                    }
                """)
            elif self._has_metadata:
                # Blue for images with metadata
                self.thumbnail_label.setStyleSheet("""
                    QLabel {
                        background-color: #1e3a5f;
                        border: 2px solid #4a6d8c;
                        border-radius: 8px;
                    }
                """)
            else:
                # Grey for images without metadata
                self.thumbnail_label.setStyleSheet("""
                    QLabel {
                        background-color: #2d3139;
                        border: 2px solid #4a4a4a;
                        border-radius: 8px;
                    }
                """)

    def enterEvent(self, event):
        """Handle mouse enter - highlight the stack."""
        super().enterEvent(event)
        if self.thumbnail_label and not self._is_expanded:
            # Brighten the border on hover
            # 3D models use grey, images use blue/grey based on metadata
            if self._is_top_item_model:
                border_color = "#5a5f6a"  # Lighter grey for hover
            elif self._has_metadata:
                border_color = "#6bb3ff"  # Blue for images with metadata
            else:
                border_color = "#5a5f6a"  # Grey for images without metadata
            self.thumbnail_label.setStyleSheet(f"""
                QLabel {{
                    background-color: #353a45;
                    border: 2px solid {border_color};
                    border-radius: 8px;
                }}
            """)
            # Increase shadow intensity
            effect = self.thumbnail_label.graphicsEffect()
            if effect:
                from PySide6.QtGui import QColor
                effect.setBlurRadius(16)
                effect.setColor(QColor(74, 158, 255, 60))

    def leaveEvent(self, event):
        """Handle mouse leave - restore normal state."""
        super().leaveEvent(event)
        if self.thumbnail_label and not self._is_expanded:
            # Restore normal style based on type and metadata
            # 3D models use grey, images use blue/grey based on metadata
            if self._is_top_item_model:
                bg_color = "#2d3139"
                border_color = "#4a4a4a"  # Grey for 3D models
            elif self._has_metadata:
                bg_color = "#1e3a5f"
                border_color = "#4a6d8c"  # Blue for images with metadata
            else:
                bg_color = "#2d3139"
                border_color = "#4a4a4a"  # Grey for images without metadata
            self.thumbnail_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {bg_color};
                    border: 2px solid {border_color};
                    border-radius: 8px;
                }}
            """)
            # Restore normal shadow
            effect = self.thumbnail_label.graphicsEffect()
            if effect:
                from PySide6.QtGui import QColor
                effect.setBlurRadius(12)
                effect.setColor(QColor(0, 0, 0, 80))

    def mousePressEvent(self, event):
        """Handle click - toggle expansion."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.stack_id)
            self.toggle_expansion()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Show batch context menu for all items in the stack."""
        from PySide6.QtWidgets import QMenu

        if not self._gallery_tab or not self._items:
            return

        menu = QMenu(self)
        count = len(self._items)

        # Header showing stack info
        header_action = menu.addAction(f"Stack: {self.stack_id} ({count} items)")
        header_action.setEnabled(False)
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

        # Publish all to AYON
        menu.addSeparator()
        publish_action = menu.addAction(f"Publish All to AYON ({count} items)")
        publish_action.triggered.connect(self._publish_all_items)

        # Delete all
        menu.addSeparator()
        delete_action = menu.addAction(f"Delete All ({count} items)")
        delete_action.triggered.connect(self._delete_all_items)

        # Check if editable
        is_editable = self._gallery_tab._is_own_gallery() if hasattr(self._gallery_tab, '_is_own_gallery') else True
        if not is_editable:
            delete_action.setEnabled(False)
            delete_action.setText(f"Delete All (view only)")

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
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget
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

            # Create the appropriate thumbnail widget
            if file_type == 'model':
                thumb = GLBThumbnailWidget(
                    path, container,
                    output_dir=item_output_dir,
                    editable=is_editable,
                    is_new=False,
                    gallery_tab=self._gallery_tab
                )
                if hasattr(thumb, 'viewed'):
                    thumb.viewed.connect(self._gallery_tab._on_item_viewed)
            else:
                thumb = GalleryThumbnailWidget(
                    path, container,
                    output_dir=item_output_dir,
                    editable=is_editable,
                    is_new=False,
                    gallery_tab=self._gallery_tab
                )
                if hasattr(thumb, 'fullscreen_requested'):
                    thumb.fullscreen_requested.connect(
                        lambda img_path=path: self._gallery_tab._open_viewer(img_path, fullscreen=True)
                    )

            # Connect signals
            if hasattr(thumb, 'clicked'):
                thumb.clicked.connect(lambda p=path, i=item: self.thumbnail_clicked.emit(p, i))
            if hasattr(thumb, 'deleted'):
                thumb.deleted.connect(self._on_item_deleted_in_stack)
            if hasattr(thumb, 'selection_changed'):
                thumb.selection_changed.connect(self._gallery_tab._on_selection_changed)

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
        """Create a pale blue background behind all expanded thumbnails."""
        from shiboken6 import isValid
        from PySide6.QtWidgets import QFrame
        from PySide6.QtCore import QRect

        # Check if widget and gallery tab are still valid
        if not isValid(self) or not self._gallery_tab:
            return

        if not self._expanded_widgets:
            return

        container = self._gallery_tab.ui.galleryThumbnailContainer

        # Calculate bounding box of all expanded widgets
        min_x = float('inf')
        min_y = float('inf')
        max_x = 0
        max_y = 0

        for widget in self._expanded_widgets:
            if isValid(widget):
                geom = widget.geometry()
                min_x = min(min_x, geom.x())
                min_y = min(min_y, geom.y())
                max_x = max(max_x, geom.right())
                max_y = max(max_y, geom.bottom())

        if min_x == float('inf'):
            return

        # Add padding around the group
        padding = 6
        bg_rect = QRect(
            int(min_x - padding),
            int(min_y - padding),
            int(max_x - min_x + 2 * padding),
            int(max_y - min_y + 2 * padding)
        )

        # Create background frame
        self._expanded_background = QFrame(container)
        self._expanded_background.setGeometry(bg_rect)
        self._expanded_background.setStyleSheet("""
            QFrame {
                background-color: rgba(74, 158, 255, 0.12);
                border: 1px solid rgba(74, 158, 255, 0.3);
                border-radius: 6px;
            }
        """)

        # Lower z-order so it's behind thumbnails
        self._expanded_background.lower()
        self._expanded_background.show()

    def collapse(self):
        """Collapse the stack by removing the expanded thumbnails from the layout."""
        if not self._is_expanded:
            return

        self._is_expanded = False
        self.expanded.emit(self.stack_id, False)

        # Remove the background frame
        if self._expanded_background:
            self._expanded_background.setParent(None)
            self._expanded_background.deleteLater()
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

        # Update visual style to show selection
        if self.thumbnail_label:
            if selected:
                # Bright selection border
                self.thumbnail_label.setStyleSheet("""
                    QLabel {
                        background-color: #1e3a5f;
                        border: 3px solid #5ba3ff;
                        border-radius: 8px;
                    }
                """)
            else:
                # Restore normal style based on type and metadata
                if self._is_top_item_model:
                    self.thumbnail_label.setStyleSheet("""
                        QLabel {
                            background-color: #2d3139;
                            border: 2px solid #4a4a4a;
                            border-radius: 8px;
                        }
                    """)
                elif self._has_metadata:
                    self.thumbnail_label.setStyleSheet("""
                        QLabel {
                            background-color: #1e3a5f;
                            border: 2px solid #4a6d8c;
                            border-radius: 8px;
                        }
                    """)
                else:
                    self.thumbnail_label.setStyleSheet("""
                        QLabel {
                            background-color: #2d3139;
                            border: 2px solid #4a4a4a;
                            border-radius: 8px;
                        }
                    """)

        # Update gallery selection state
        if self._gallery_tab:
            for item in self._items:
                path = item['path']
                if selected:
                    self._gallery_tab._selected_items.add(path)
                else:
                    self._gallery_tab._selected_items.discard(path)

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
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget
        import os

        is_editable = False
        if self._gallery_tab:
            is_editable = self._gallery_tab._is_own_gallery()

        for item in self._items:
            path = item['path']
            file_type = item.get('type', 'image')
            item_output_dir = os.path.dirname(path)

            # Create the appropriate thumbnail widget
            if file_type == 'model':
                thumb = GLBThumbnailWidget(
                    path, self._thumb_container,
                    output_dir=item_output_dir,
                    editable=is_editable,
                    is_new=False,
                    gallery_tab=self._gallery_tab
                )
                if self._gallery_tab and hasattr(thumb, 'viewed'):
                    thumb.viewed.connect(self._gallery_tab._on_item_viewed)
            else:
                thumb = GalleryThumbnailWidget(
                    path, self._thumb_container,
                    output_dir=item_output_dir,
                    editable=is_editable,
                    is_new=False,
                    gallery_tab=self._gallery_tab
                )
                if self._gallery_tab and hasattr(thumb, 'fullscreen_requested'):
                    thumb.fullscreen_requested.connect(
                        lambda img_path=path: self._gallery_tab._open_viewer(img_path, fullscreen=True)
                    )

            # Connect signals
            if hasattr(thumb, 'clicked'):
                thumb.clicked.connect(lambda p=path, i=item: self.thumbnail_clicked.emit(p, i))
            if hasattr(thumb, 'deleted'):
                thumb.deleted.connect(self._on_thumb_deleted)
            if self._gallery_tab and hasattr(thumb, 'selection_changed'):
                thumb.selection_changed.connect(self._gallery_tab._on_selection_changed)

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


def browse_directory(
    parent: QWidget,
    title: str,
    context: str,
    callback: Callable[[str], None]
) -> bool:
    """
    Show a directory browser dialog with last-directory memory.

    Args:
        parent: Parent widget for the dialog
        title: Dialog title
        context: Settings key for remembering the last directory
        callback: Function to call with the selected path

    Returns:
        True if a directory was selected, False if cancelled
    """
    # Import here to avoid circular imports
    import sys
    sys.path.insert(0, str(parent.window().python_path) if hasattr(parent.window(), 'python_path') else '')
    try:
        from settings_manager import get_last_browse_directory, set_last_browse_directory
    except ImportError:
        # Fallback if settings_manager not available
        def get_last_browse_directory(ctx):
            return ""
        def set_last_browse_directory(ctx, path):
            pass

    last_dir = get_last_browse_directory(context)
    path = QFileDialog.getExistingDirectory(parent, title, last_dir or "")

    if path:
        set_last_browse_directory(context, path)
        callback(path)
        return True
    return False


def browse_file(
    parent: QWidget,
    title: str,
    context: str,
    file_filter: str,
    callback: Callable[[str], None]
) -> bool:
    """
    Show a file browser dialog with last-directory memory.

    Args:
        parent: Parent widget for the dialog
        title: Dialog title
        context: Settings key for remembering the last directory
        file_filter: File filter string (e.g., "JSON Files (*.json)")
        callback: Function to call with the selected path

    Returns:
        True if a file was selected, False if cancelled
    """
    import sys
    import os
    sys.path.insert(0, str(parent.window().python_path) if hasattr(parent.window(), 'python_path') else '')
    try:
        from settings_manager import get_last_browse_directory, set_last_browse_directory
    except ImportError:
        def get_last_browse_directory(ctx):
            return ""
        def set_last_browse_directory(ctx, path):
            pass

    last_dir = get_last_browse_directory(context)
    path, _ = QFileDialog.getOpenFileName(parent, title, last_dir or "", file_filter)

    if path:
        set_last_browse_directory(context, os.path.dirname(path))
        callback(path)
        return True
    return False
