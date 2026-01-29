"""
UI Components for Luma Tools.

This module re-exports components from submodules for convenient importing.
The actual implementations are in:
- workers.py: Threading utilities (Worker, WorkerSignals)
- styles.py: Style constants (LoadingStyles, StatusColors)
- spinners.py: Loading animations (SpinnerWidget, InlineSpinner, PulsingDotsWidget)
- effects.py: Visual effects (TabGlowEffect, TabGlowManager, UIAnimations)
- layouts.py: Custom layouts (FlowLayout)
- dialogs.py: Edit dialogs (EditItemDialog, EditModelDialog)
- batch_selector.py: Image selection (BatchImageSelector)
- thumbnail_base.py: Base thumbnail widget (BaseThumbnailWidget)
- image_viewers.py: Image and model viewing widgets
"""
import os
import logging
logger = logging.getLogger(__name__)
from PySide6.QtCore import Qt, QTimer, Signal, QThreadPool, QFile, QTextStream
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QMenu, QDialog, QComboBox, QApplication
)
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap
from shiboken6 import isValid
from dialog_helpers import get_active_window

# Re-export from submodules (absolute imports since resources/ui is in path)
from workers import Worker, WorkerSignals, report_progress
from styles import LoadingStyles, StatusColors
from spinners import SpinnerWidget, InlineSpinner, PulsingDotsWidget, BaseSpinner
from effects import TabGlowEffect, TabGlowManager, UIAnimations
from thumbnail_styles import ThumbnailStyler
from layouts import FlowLayout
from dialogs import EditItemDialog, EditModelDialog, BaseEditDialog, GroupEditorDialog
from batch_selector import BatchImageSelector
from thumbnail_base import BaseThumbnailWidget
from image_viewers import ZoomableImageWidget, EmbeddedImageViewer, FullscreenImageViewer
from small_widgets import StackedThumbnailWidget, show_popup_menu
from drag_drop import DraggableMixin, DropTargetMixin, create_drag_pixmap


# ============================================================================
# METADATA COPY MIXIN
# ============================================================================

class MetadataCopyMixin:
    """
    Mixin providing unified copy functionality for image/model viewers.
    """

    def _get_current_metadata(self):
        """Get metadata for current item."""
        if hasattr(self, '_get_metadata'):
            return self._get_metadata()
        return getattr(self, '_metadata', None)

    def _show_feedback(self, message, duration=1500):
        """Show UI feedback. Override in subclass for custom feedback."""
        logger.info(message)

    def _copy_prompt(self):
        """Copy prompt to clipboard with feedback."""
        metadata = self._get_current_metadata()
        if not metadata:
            self._show_feedback("No metadata available")
            return

        prompt = metadata.get('prompt', '')
        if not prompt:
            self._show_feedback("No prompt available")
            return

        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(prompt, mode=clipboard.Mode.Clipboard)
            self._show_feedback(f"Prompt copied: {prompt[:50]}...")
        except Exception as e:
            logger.error(f"Error copying prompt: {e}")
            self._show_feedback("Error copying prompt")

    def _copy_settings(self):
        """Apply settings to ComfyUI tab (workflow, seed, editable values)."""
        metadata = self._get_current_metadata()
        if not metadata:
            self._show_feedback("No settings available")
            return

        if not hasattr(self, 'copy_settings_requested'):
            logger.error("copy_settings_requested signal not defined")
            return

        try:
            self.copy_settings_requested.emit(metadata)
            path = getattr(self, 'image_path', getattr(self, 'model_path', 'unknown'))
            self._show_feedback(f"Settings applied from {os.path.basename(path)}")
        except Exception as e:
            logger.error(f"Error applying settings: {e}")
            self._show_feedback("Error applying settings")

    def _copy_path(self, path=None):
        """Copy path to clipboard with feedback."""
        if path is None:
            path = getattr(self, 'image_path', getattr(self, 'model_path', None))

        if not path:
            self._show_feedback("No path available")
            return

        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(path)
            self._show_feedback(f"Path copied: {os.path.basename(path)}")
        except Exception as e:
            logger.error(f"Error copying path: {e}")
            self._show_feedback("Error copying path")


# ============================================================================
# IMAGE THUMBNAIL CACHE (memory + disk)
# ============================================================================

import hashlib
from core.utils import ensure_directory

# Disk cache directory (shared with model thumbnails)
_THUMBNAIL_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".luma_tools", "thumbnails")
ensure_directory(_THUMBNAIL_CACHE_DIR)

# In-memory cache for fast access within a session
# Key: image path, Value: PNG bytes data
_image_thumbnail_cache = {}
_IMAGE_THUMBNAIL_CACHE_MAX_SIZE = 500  # Limit cache size


def _get_thumbnail_disk_path(image_path):
    """Get the disk cache path for an image thumbnail."""
    path_hash = hashlib.md5(os.path.normpath(image_path).encode()).hexdigest()
    return os.path.join(_THUMBNAIL_CACHE_DIR, f"img_{path_hash}.png")


def get_cached_image_thumbnail(path):
    """Get cached image thumbnail bytes if available (memory then disk).

    Returns PNG bytes if cached, None otherwise.
    """
    # Check in-memory cache first
    data = _image_thumbnail_cache.get(path)
    if data:
        return data

    # Check disk cache
    cache_path = _get_thumbnail_disk_path(path)
    if os.path.exists(cache_path):
        try:
            # Validate cache freshness against original file
            if os.path.exists(path):
                if os.path.getmtime(cache_path) < os.path.getmtime(path):
                    # Cache is stale, remove it
                    os.remove(cache_path)
                    return None

            with open(cache_path, 'rb') as f:
                data = f.read()
            if data:
                # Promote to memory cache
                _image_thumbnail_cache[path] = data
                return data
        except (OSError, IOError):
            pass

    return None


def cache_image_thumbnail(path, data):
    """Cache image thumbnail bytes (memory + disk)."""
    if not data:
        return

    # Memory cache with LRU-like eviction
    if len(_image_thumbnail_cache) >= _IMAGE_THUMBNAIL_CACHE_MAX_SIZE:
        keys = list(_image_thumbnail_cache.keys())
        for key in keys[:len(keys) // 2]:
            del _image_thumbnail_cache[key]
    _image_thumbnail_cache[path] = data

    # Write to disk cache
    cache_path = _get_thumbnail_disk_path(path)
    try:
        with open(cache_path, 'wb') as f:
            f.write(data)
    except (OSError, IOError):
        pass  # Disk write failed, memory cache still works


# ============================================================================
# UNIFIED THUMBNAIL WIDGET (for images and 3D models)
# ============================================================================

class ThumbnailWidget(DraggableMixin, DropTargetMixin, MetadataCopyMixin, BaseThumbnailWidget):
    """
    Unified thumbnail widget for both images and 3D models.

    The widget type ('image' or 'model') determines:
    - How thumbnails are generated/loaded
    - Whether the cube icon is shown
    - Context menu options

    Supports drag-and-drop: items can be dragged to BatchImageSelector
    or other input widgets. Use hover-to-switch-tab to drag across tabs.

    Also acts as drop target: dropping items onto this thumbnail creates
    a new group containing this item and the dropped items.
    """
    clicked = Signal(str)
    fullscreen_requested = Signal(str)
    copy_settings_requested = Signal(dict)
    deleted = Signal(str)
    viewed = Signal(str)
    selection_changed = Signal(str, bool)  # path, is_selected
    like_toggled = Signal(str, bool)  # path, is_liked
    group_items_requested = Signal(list)  # [paths] - create new group with these items

    def __init__(self, path, item_type='image', parent=None, output_dir=None,
                 editable=True, is_new=False, gallery_tab=None, has_metadata=False,
                 job_prefix=None):
        """
        Initialize thumbnail widget.

        Args:
            path: Path to the image or model file
            item_type: 'image' or 'model'
            parent: Parent widget
            output_dir: Output directory for metadata lookup
            editable: Whether item can be edited/deleted
            is_new: Whether item is newly added (shows highlight)
            gallery_tab: Reference to gallery tab for selection callbacks
            has_metadata: Whether item has associated metadata (affects styling)
            job_prefix: Job prefix for stack color lookup
        """
        super().__init__(parent)
        self.path = path
        self.item_type = item_type
        self.output_dir = output_dir or os.path.dirname(path)
        self._editable = editable
        self._is_new = is_new
        self._is_selected = False
        self._job_prefix = job_prefix
        self._is_hovered = False
        self._has_metadata = has_metadata
        self._gallery_tab = gallery_tab
        self._double_click_in_progress = False
        self._cached_metadata = None
        self._thumbnail_loaded = False
        self._thumbnail_loading = False
        self._tooltip_loaded = False

        # Likes and groups state
        self._is_liked = False
        self._group_colors = []  # List of group colors this item belongs to
        self._favorites_manager = None  # Set by gallery tab after creation

        # Initialize drag support
        self._init_drag_state()

        # Initialize drop target support (accept images, videos, models)
        self._init_drop_target({'image', 'video', 'model'})

        # Styler uses is_model to determine border color
        self._styler = ThumbnailStyler(
            has_metadata=has_metadata,
            is_model=(item_type == 'model'),
            border_radius=4
        )
        self._setup_ui()
        self.setToolTip(os.path.basename(path))

    # Compatibility properties for code that uses image_path or model_path
    @property
    def image_path(self):
        return self.path

    @property
    def model_path(self):
        return self.path

    def _setup_ui(self):
        self.setFixedSize(self.THUMBNAIL_SIZE[0] + 10, self.THUMBNAIL_SIZE[1] + 30)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(*self.THUMBNAIL_SIZE)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.thumbnail_label.setContextMenuPolicy(Qt.NoContextMenu)
        self._apply_thumbnail_style()
        self.thumbnail_label.setPixmap(self._create_placeholder("..."))
        layout.addWidget(self.thumbnail_label)

        self.filename_label = QLabel(os.path.basename(self.path))
        self.filename_label.setAlignment(Qt.AlignCenter)
        self._apply_filename_style()
        self.filename_label.setWordWrap(True)
        self.filename_label.setMaximumWidth(self.THUMBNAIL_SIZE[0])
        self.filename_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.filename_label.setContextMenuPolicy(Qt.NoContextMenu)
        layout.addWidget(self.filename_label)

        # Selection checkmark indicator (top-left) - outline style
        self.selection_indicator = QLabel(self.thumbnail_label)
        self.selection_indicator.setText("✓")
        self.selection_indicator.setAlignment(Qt.AlignCenter)
        self.selection_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.4);
                color: rgba(59, 130, 246, 0.95);
                border: 2px solid rgba(59, 130, 246, 0.8);
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.selection_indicator.setFixedSize(24, 24)
        self.selection_indicator.move(4, 4)
        self.selection_indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.selection_indicator.setContextMenuPolicy(Qt.NoContextMenu)
        self.selection_indicator.hide()

        # Like indicator (heart icon, top-right corner) - always visible, toggleable
        self.like_indicator = QLabel(self.thumbnail_label)
        self.like_indicator.setText("♥")
        self.like_indicator.setAlignment(Qt.AlignCenter)
        self.like_indicator.setFixedSize(26, 26)
        self.like_indicator.move(self.THUMBNAIL_SIZE[0] - 30, 4)
        self.like_indicator.setCursor(Qt.PointingHandCursor)
        self.like_indicator.setContextMenuPolicy(Qt.NoContextMenu)
        self._update_like_indicator_style()
        # Always visible - no hide()

        # Group dots indicator (bottom-right, shows up to 3 colored dots)
        self.group_dots_container = QWidget(self.thumbnail_label)
        self.group_dots_container.setFixedSize(50, 14)
        self.group_dots_container.move(self.THUMBNAIL_SIZE[0] - 54, self.THUMBNAIL_SIZE[1] - 18)
        self.group_dots_container.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.group_dots_container.setContextMenuPolicy(Qt.NoContextMenu)
        self._group_dots_layout = QHBoxLayout(self.group_dots_container)
        self._group_dots_layout.setContentsMargins(0, 0, 0, 0)
        self._group_dots_layout.setSpacing(3)
        self._group_dots_layout.addStretch()
        self.group_dots_container.hide()

        # NEW indicator (top-right, pulsing red notification dot for new items)
        # Uses same visual style as TabGlowEffect and ButtonNotificationBadge
        from effects import ThumbnailNotificationDot
        self._new_indicator = ThumbnailNotificationDot(self.thumbnail_label)
        self._new_indicator.move(self.THUMBNAIL_SIZE[0] - 18, 4)

        # Start pulsing if new
        if self._is_new:
            self._new_indicator.show_dot()

    def _apply_thumbnail_style(self):
        """Apply the appropriate style based on current state."""
        drop_hover = getattr(self, '_drop_highlight_active', False)
        style = self._styler.get_style(
            selected=self._is_selected,
            hover=self._is_hovered,
            is_new=self._is_new,
            drop_hover=drop_hover
        )
        self.thumbnail_label.setStyleSheet(style)

    def _apply_filename_style(self):
        # New items no longer use green - they have a pulsing NEW badge instead
        self.filename_label.setStyleSheet("color: #aaaaaa; font-size: 10px;")

    # --- Likes and Groups ---
    def set_favorites_manager(self, manager):
        """Set the favorites manager and update visual state."""
        self._favorites_manager = manager

        # Connect to signals for live updates
        if manager:
            manager.item_groups_changed.connect(self._on_item_groups_changed)
            manager.like_changed.connect(self._on_like_changed)

        self.update_favorites_state()

    def _on_item_groups_changed(self, path):
        """Handle item group membership change."""
        if path == self.path:
            self.update_favorites_state()

    def _on_like_changed(self, path, is_liked):
        """Handle like state change."""
        if path == self.path:
            self.update_favorites_state()

    def update_favorites_state(self):
        """Update like and group visual state from favorites manager."""
        if not self._favorites_manager:
            return
        # Update like state (heart is always visible, style changes when liked)
        self._is_liked = self._favorites_manager.is_liked(self.path)
        self._update_like_indicator_style()

        # Update group colors
        self._group_colors = self._favorites_manager.get_item_group_colors(self.path)
        self._update_group_dots()
        self._update_group_border()

    def _update_like_indicator_style(self):
        """Update the like indicator appearance based on liked state - uses color from settings."""
        from core.settings_manager import get_setting

        # Get liked color from settings (default mint green if not set)
        liked_color = get_setting("gallery_liked_color") or "#55ff9c"
        hex_color = liked_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)

        if self._is_liked:
            self.like_indicator.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(0, 0, 0, 0.4);
                    color: rgba({r}, {g}, {b}, 0.95);
                    border: 2px solid rgba({r}, {g}, {b}, 0.8);
                    border-radius: 13px;
                    font-size: 15px;
                }}
            """)
        else:
            self.like_indicator.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(0, 0, 0, 0.3);
                    color: rgba(255, 255, 255, 0.5);
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    border-radius: 13px;
                    font-size: 15px;
                }}
                QLabel:hover {{
                    background-color: rgba(0, 0, 0, 0.4);
                    color: rgba({r}, {g}, {b}, 0.9);
                    border: 2px solid rgba({r}, {g}, {b}, 0.7);
                }}
            """)

    def _update_group_dots(self):
        """Update the group dots display based on group membership."""
        # Clear existing dots
        while self._group_dots_layout.count() > 1:  # Keep the stretch
            item = self._group_dots_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._group_colors:
            self.group_dots_container.hide()
            return

        # Add colored dots (max 3) - outline style
        for color in self._group_colors[:3]:
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(0, 0, 0, 0.4);
                    border-radius: 5px;
                    border: 2px solid {color};
                }}
            """)
            dot.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._group_dots_layout.insertWidget(self._group_dots_layout.count() - 1, dot)

        self.group_dots_container.show()

    def _update_group_border(self):
        """Update thumbnail border color based on group membership.

        Liked state is shown only via the heart icon, not the border.
        """
        from core.settings_manager import get_setting

        # Priority 1: Group color (from user-defined groups)
        if self._group_colors:
            self._styler.group_color = self._group_colors[0]
            self._apply_thumbnail_style()
            return

        # Priority 2: Stack color (if has job_prefix and custom stack color)
        if self._job_prefix:
            stack_colors = get_setting("gallery_stack_colors") or {}
            stack_color = stack_colors.get(self._job_prefix)
            if stack_color:
                self._styler.group_color = stack_color
                self._apply_thumbnail_style()
                return

        # No custom color - use default (liked state shown via heart icon only)
        self._styler.group_color = None
        self._apply_thumbnail_style()

    def _toggle_like(self):
        """Toggle like state for this item."""
        if not self._favorites_manager:
            return
        is_liked = self._favorites_manager.toggle_like(self.path)
        self._is_liked = is_liked
        self._update_like_indicator_style()
        self.like_toggled.emit(self.path, is_liked)

        # Animate the heart
        self._animate_like()

        # Show statusbar message
        if self._gallery_tab and hasattr(self._gallery_tab, 'show_status_message'):
            msg = "Added to Likes" if is_liked else "Removed from Likes"
            self._gallery_tab.show_status_message(msg)

    def _animate_like(self):
        """Animate the like indicator with a scale bounce."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect
        if not hasattr(self, '_like_anim') or self._like_anim is None:
            self._like_anim = QPropertyAnimation(self.like_indicator, b"geometry")
            self._like_anim.setDuration(150)
            self._like_anim.setEasingCurve(QEasingCurve.OutBack)

        original = self.like_indicator.geometry()
        enlarged = QRect(
            original.x() - 3,
            original.y() - 3,
            original.width() + 6,
            original.height() + 6
        )

        self._like_anim.setKeyValueAt(0.0, original)
        self._like_anim.setKeyValueAt(0.5, enlarged)
        self._like_anim.setKeyValueAt(1.0, original)
        self._like_anim.start()

    def _toggle_group_membership(self, group_id):
        """Toggle membership in a group."""
        if not self._favorites_manager:
            return
        is_in_group = self._favorites_manager.toggle_group_membership(self.path, group_id)
        self.update_favorites_state()

        # Show feedback
        group = self._favorites_manager.get_group(group_id)
        if group and self._gallery_tab and hasattr(self._gallery_tab, 'show_status_message'):
            msg = f"Added to {group.name}" if is_in_group else f"Removed from {group.name}"
            self._gallery_tab.show_status_message(msg)

        # Flash border in group color
        self._flash_border(group.color if group else None)

    def _create_new_group(self):
        """Open dialog to create a new group and add this item to it."""
        from dialogs import GroupEditorDialog
        dialog = GroupEditorDialog(parent=self)
        if dialog.exec_():
            name, color = dialog.get_result()
            if name and self._favorites_manager:
                group_id = self._favorites_manager.create_group(name, color)
                self._favorites_manager.add_to_group(self.path, group_id)
                self.update_favorites_state()
                if self._gallery_tab and hasattr(self._gallery_tab, 'show_status_message'):
                    self._gallery_tab.show_status_message(f"Created group '{name}' and added item")

    def _flash_border(self, color=None):
        """Flash the border briefly in a color for feedback."""
        if not color:
            return
        # Store original color
        original_color = self._styler.group_color
        # Set to flash color
        self._styler.group_color = color
        self._apply_thumbnail_style()
        # Restore after delay
        QTimer.singleShot(200, lambda: self._restore_border(original_color))

    def _restore_border(self, original_color):
        """Restore border after flash."""
        if not isValid(self):
            return
        self._styler.group_color = original_color
        self._apply_thumbnail_style()

    def mark_as_viewed(self):
        if self._is_new:
            self._is_new = False
            self._new_indicator.hide_dot()  # Stop pulsing animation
            self._apply_thumbnail_style()
            self.viewed.emit(self.path)

    def set_selected(self, selected):
        """Set the selection state of this thumbnail."""
        if self._is_selected != selected:
            self._is_selected = selected
            self._apply_thumbnail_style()
            self.selection_changed.emit(self.path, selected)

    def is_selected(self):
        """Return whether this thumbnail is selected."""
        return self._is_selected

    def load_thumbnail_if_needed(self):
        if not self._thumbnail_loaded:
            self._thumbnail_loaded = True
            if self.item_type == 'model':
                self._load_model_thumbnail()
            elif self.item_type == 'video':
                self._load_video_thumbnail()
            elif self.item_type == 'audio':
                self._load_audio_placeholder()
            else:
                self._load_image_thumbnail()
        if not self._tooltip_loaded:
            self._tooltip_loaded = True
            self._load_tooltip_async()

    def _load_tooltip_async(self):
        self._tooltip_worker = Worker(self._get_tooltip_data, self.output_dir, self.path)
        self._tooltip_worker.signals.result.connect(self._on_tooltip_loaded)
        self._tooltip_worker.signals.error.connect(lambda msg, tb: None)
        QThreadPool.globalInstance().start(self._tooltip_worker)

    @staticmethod
    def _get_tooltip_data(output_dir, path):
        from comfyui.service import get_model_note
        filename = os.path.basename(path)
        note = get_model_note(output_dir, filename)
        return (filename, note)

    def _on_tooltip_loaded(self, data):
        if not isValid(self):
            return
        filename, note = data
        tooltip_parts = [filename]
        if note:
            tooltip_parts.append(f"\nNote: {note}")
        self.setToolTip("\n".join(tooltip_parts))

    # --- Image thumbnail loading ---
    def _load_image_thumbnail(self):
        ext = os.path.splitext(self.path)[1].lower()
        if ext == '.exr':
            self.thumbnail_label.setPixmap(self._create_placeholder("EXR"))
            return

        # Check in-memory cache first (fast path for recycled widgets)
        cached_data = get_cached_image_thumbnail(self.path)
        if cached_data:
            pixmap = QPixmap()
            pixmap.loadFromData(cached_data)
            if not pixmap.isNull():
                self.thumbnail_label.setPixmap(pixmap)
                return

        # Load from disk in background
        self._load_worker = Worker(self._load_image_data, self.path)
        self._load_worker.signals.result.connect(self._on_image_thumbnail_loaded)
        self._load_worker.signals.error.connect(lambda msg, tb: self._on_thumbnail_error())
        QThreadPool.globalInstance().start(self._load_worker)

    @staticmethod
    def _load_image_data(image_path):
        from PySide6.QtGui import QImage
        from PySide6.QtCore import QBuffer, QIODevice
        image = QImage(image_path)
        if image.isNull():
            return None
        scaled = image.scaled(
            ThumbnailWidget.THUMBNAIL_SIZE[0],
            ThumbnailWidget.THUMBNAIL_SIZE[1],
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        scaled.save(buffer, "PNG")
        return buffer.data().data()

    def _on_image_thumbnail_loaded(self, image_data):
        if not isValid(self):
            return
        if image_data is None:
            self.thumbnail_label.setPixmap(self._create_placeholder("?"))
            return

        # Cache the thumbnail data for reuse
        cache_image_thumbnail(self.path, image_data)

        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        if not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap)
        else:
            self.thumbnail_label.setPixmap(self._create_placeholder("?"))

    # --- Model thumbnail loading ---
    def _load_model_thumbnail(self):
        try:
            from geo.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            cached = service.get_cached_thumbnail(self.path)
            if cached and not cached.isNull():
                self.thumbnail_label.setPixmap(cached.scaled(
                    *self.THUMBNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
                return
        except Exception as e:
            logger.error(f"Error loading cached model thumbnail: {e}")
        self.thumbnail_label.setPixmap(self._create_3d_placeholder("3D"))
        self._generate_model_thumbnail_async()

    def _generate_model_thumbnail_async(self):
        """Generate thumbnail on main thread (Three.js viewer requires it)."""
        if self._thumbnail_loading:
            return
        try:
            from geo.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            if service.is_pending(self.path):
                return
            service.set_pending(self.path, True)
        except Exception:
            pass
        self._thumbnail_loading = True
        QTimer.singleShot(100, self._generate_model_thumbnail_on_main_thread)

    def _generate_model_thumbnail_on_main_thread(self):
        """Generate thumbnail - must run on main thread for Three.js viewer."""
        if not isValid(self):
            return
        try:
            from geo.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            pixmap = service.generate_thumbnail_sync(self.path)
            self._on_model_thumbnail_generated(pixmap)
        except Exception as e:
            logger.error(f"Error generating model thumbnail: {e}")
            self._on_thumbnail_error()

    def _on_model_thumbnail_generated(self, pixmap):
        self._thumbnail_loading = False
        try:
            from geo.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            service.set_pending(self.path, False)
        except Exception:
            pass
        if not isValid(self):
            return
        if pixmap and not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap.scaled(
                *self.THUMBNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))

    # --- Video thumbnail loading ---
    def _load_video_thumbnail(self):
        """Load video thumbnail by extracting first frame."""
        self.thumbnail_label.setPixmap(self._create_video_placeholder())
        self._load_worker = Worker(self._extract_video_frame, self.path)
        self._load_worker.signals.result.connect(self._on_video_thumbnail_loaded)
        self._load_worker.signals.error.connect(lambda msg, tb: None)  # Keep placeholder on error
        QThreadPool.globalInstance().start(self._load_worker)

    @staticmethod
    def _extract_video_frame(video_path):
        """Extract first frame from video using FFmpeg."""
        import subprocess
        import tempfile
        from core.config import FFMPEG_PATH
        if not FFMPEG_PATH:
            return None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name
            cmd = [
                FFMPEG_PATH, '-i', video_path,
                '-vframes', '1', '-y', tmp_path
            ]
            subprocess.run(cmd, capture_output=True, timeout=10)
            from PySide6.QtGui import QImage
            from PySide6.QtCore import QBuffer, QIODevice
            image = QImage(tmp_path)
            os.remove(tmp_path)
            if image.isNull():
                return None
            scaled = image.scaled(
                ThumbnailWidget.THUMBNAIL_SIZE[0],
                ThumbnailWidget.THUMBNAIL_SIZE[1],
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            scaled.save(buffer, "PNG")
            return buffer.data().data()
        except Exception:
            return None

    def _on_video_thumbnail_loaded(self, image_data):
        if not isValid(self):
            return
        if image_data is None:
            return  # Keep the video placeholder
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        if not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap)

    def _create_video_placeholder(self):
        """Create a video placeholder with play icon."""
        cache_key = "video_placeholder"
        if cache_key in BaseThumbnailWidget._placeholder_cache:
            return BaseThumbnailWidget._placeholder_cache[cache_key]

        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#2a3040"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw play triangle
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#ef4444")))
        center_x, center_y = 75, 65
        size = 25
        from PySide6.QtGui import QPolygon
        from PySide6.QtCore import QPoint
        triangle = QPolygon([
            QPoint(center_x - size//2, center_y - size//2),
            QPoint(center_x - size//2, center_y + size//2),
            QPoint(center_x + size//2, center_y),
        ])
        painter.drawPolygon(triangle)

        # Draw "VIDEO" text
        painter.setPen(QColor("#ef4444"))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, 95, self.THUMBNAIL_SIZE[0], 20, Qt.AlignCenter, "VIDEO")
        painter.end()

        BaseThumbnailWidget._placeholder_cache[cache_key] = pixmap
        return pixmap

    # --- Audio placeholder ---
    def _load_audio_placeholder(self):
        """Show audio placeholder (no thumbnail extraction for audio)."""
        self.thumbnail_label.setPixmap(self._create_audio_placeholder())

    def _create_audio_placeholder(self):
        """Create an audio placeholder with music note icon."""
        cache_key = "audio_placeholder"
        if cache_key in BaseThumbnailWidget._placeholder_cache:
            return BaseThumbnailWidget._placeholder_cache[cache_key]

        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#2a3040"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw music note
        painter.setPen(QColor("#a855f7"))
        font = painter.font()
        font.setPointSize(40)
        painter.setFont(font)
        painter.drawText(0, 20, self.THUMBNAIL_SIZE[0], 80, Qt.AlignCenter, "♫")

        # Draw "AUDIO" text
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, 95, self.THUMBNAIL_SIZE[0], 20, Qt.AlignCenter, "AUDIO")
        painter.end()

        BaseThumbnailWidget._placeholder_cache[cache_key] = pixmap
        return pixmap

    def _on_thumbnail_error(self):
        if not isValid(self):
            return
        if self.item_type == 'model':
            self._thumbnail_loading = False
            try:
                from geo.thumbnail_service import get_model_thumbnail_service
                service = get_model_thumbnail_service()
                service.set_pending(self.path, False)
            except Exception:
                pass
        self.thumbnail_label.setPixmap(self._create_placeholder("!"))

    def _create_3d_placeholder(self, text):
        """Create a 3D cube icon placeholder for model thumbnails."""
        cache_key = f"model_3d_cube_{text}"
        if cache_key in BaseThumbnailWidget._placeholder_cache:
            return BaseThumbnailWidget._placeholder_cache[cache_key]

        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#2a3040"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#4a9eff"), 2))

        # Draw 3D cube
        center_x, center_y = 75, 65
        size = 30
        painter.drawRect(center_x - size//2, center_y - size//2, size, size)
        offset = 12
        painter.drawLine(center_x - size//2, center_y - size//2, center_x - size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x + size//2, center_y - size//2, center_x + size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x - size//2 + offset, center_y - size//2 - offset, center_x + size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x + size//2, center_y + size//2, center_x + size//2 + offset, center_y + size//2 - offset)
        painter.drawLine(center_x + size//2 + offset, center_y - size//2 - offset, center_x + size//2 + offset, center_y + size//2 - offset)

        painter.setPen(QColor("#888888"))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, 100, self.THUMBNAIL_SIZE[0], 30, Qt.AlignCenter, text)
        painter.end()

        BaseThumbnailWidget._placeholder_cache[cache_key] = pixmap
        return pixmap

    # --- Mouse events ---
    def mousePressEvent(self, event):
        from PySide6.QtWidgets import QApplication
        mods = QApplication.keyboardModifiers()
        if event.button() == Qt.LeftButton:
            # Check if click is on like indicator
            like_geom = self.like_indicator.geometry()
            # Map click position to thumbnail_label coordinates
            thumb_pos = self.thumbnail_label.mapFrom(self, event.pos())
            if self.like_indicator.isVisible() and like_geom.contains(thumb_pos):
                self._toggle_like()
                event.accept()
                return

            if self._double_click_in_progress:
                super().mousePressEvent(event)
                return

            # Store drag start position for potential drag operation
            self._handle_drag_press(event)

            if mods & Qt.ShiftModifier:
                if self._gallery_tab:
                    self._gallery_tab._on_shift_click_selection(self.path)
            elif mods & Qt.ControlModifier:
                self.set_selected(not self._is_selected)
            else:
                if self._gallery_tab:
                    self._gallery_tab._clear_selection()
                self.set_selected(True)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for drag initiation."""
        # Check if we should start a drag
        if self._handle_drag_move(event):
            return  # Drag was started
        super().mouseMoveEvent(event)

    def _get_drag_paths(self):
        """Return paths to drag - this item plus any other selected items."""
        if self._gallery_tab and hasattr(self._gallery_tab, '_selected_items'):
            selected = self._gallery_tab._selected_items
            if self.path in selected and len(selected) > 1:
                # Multiple items selected - drag all of them
                return list(selected)
        # Single item
        return [self.path]

    def _get_drag_pixmap(self, paths):
        """Create drag pixmap, using our thumbnail if available."""
        if len(paths) == 1:
            # Single item - use our thumbnail if loaded
            pixmap = self.thumbnail_label.pixmap()
            if pixmap and not pixmap.isNull():
                return pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # Multiple items or no thumbnail - use default stack visualization
        return create_drag_pixmap(paths)

    # --- Drop target methods ---
    def _on_files_dropped(self, paths):
        """Handle files dropped on this thumbnail - create a new group."""
        # Don't create group if dropped on self
        if len(paths) == 1 and paths[0] == self.path:
            return

        # Filter out self from dropped paths if present
        other_paths = [p for p in paths if p != self.path]
        if not other_paths:
            return

        # Emit signal with this item + dropped items to create a new group
        all_paths = [self.path] + other_paths
        logger.info(f"[ThumbnailWidget] Group requested for {len(all_paths)} items")
        self.group_items_requested.emit(all_paths)

    def _show_drop_highlight(self, show):
        """Show or hide drop highlight visual feedback."""
        logger.debug(f"[ThumbnailWidget] _show_drop_highlight({show}) for {self.path}")
        self._drop_highlight_active = show
        if show:
            # Just apply style with drop highlight
            self._apply_thumbnail_style()
        else:
            # When hiding highlight, use _update_group_border to restore proper colors
            self._update_group_border()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._double_click_in_progress = True
            self.mark_as_viewed()
            self.clicked.emit(self.path)
            QTimer.singleShot(300, lambda: setattr(self, '_double_click_in_progress', False))
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._is_hovered = True
        self._apply_thumbnail_style()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._is_hovered = False
        self._apply_thumbnail_style()

    def contextMenuEvent(self, event):
        if self._gallery_tab and self._is_selected and len(self._gallery_tab._selected_items) > 1:
            self._show_batch_context_menu(event.pos())
        else:
            self._show_context_menu(event.pos())
        event.accept()

    def _get_metadata(self):
        if self._cached_metadata is None:
            try:
                from comfyui.service import get_image_metadata
                filename = os.path.basename(self.path)
                self._cached_metadata = get_image_metadata(self.output_dir, filename) or {}
            except Exception as e:
                logger.error(f"Error loading metadata for {self.path}: {e}")
                self._cached_metadata = {}
        return self._cached_metadata

    def _show_context_menu(self, pos):
        try:
            menu = QMenu(self)

            # Like option (at the top for quick access)
            if self._favorites_manager:
                is_liked = self._is_liked
                like_action = menu.addAction("Unlike" if is_liked else "Like")
                like_action.triggered.connect(self._toggle_like)
                # Add heart icon visual
                if is_liked:
                    like_action.setText("♥ Unlike")
                else:
                    like_action.setText("♡ Like")

                # Groups submenu
                groups_menu = menu.addMenu("Add to Group")
                groups = self._favorites_manager.get_groups()
                item_group_ids = set(self._favorites_manager.get_item_groups(self.path))

                for group in groups:
                    action = groups_menu.addAction(f"● {group.name}")
                    action.setCheckable(True)
                    action.setChecked(group.group_id in item_group_ids)
                    # Use colored text to indicate group color
                    action.triggered.connect(
                        lambda checked, gid=group.group_id: self._toggle_group_membership(gid)
                    )

                if groups:
                    groups_menu.addSeparator()

                new_group_action = groups_menu.addAction("+ New Group...")
                new_group_action.triggered.connect(self._create_new_group)

                menu.addSeparator()

            # View options
            open_action = menu.addAction("Open in Viewer")
            open_action.triggered.connect(self._open_item)

            if self.item_type == 'image':
                fullscreen_action = menu.addAction("View Fullscreen")
                fullscreen_action.triggered.connect(lambda: self.fullscreen_requested.emit(self.path))

            edit_action = menu.addAction("Edit Item")
            edit_action.triggered.connect(self._edit_item)
            if not self._editable:
                edit_action.setEnabled(False)
                edit_action.setText("Edit Item (view only)")

            open_folder_action = menu.addAction("Open Containing Folder")
            open_folder_action.triggered.connect(self._open_folder)

            # View Input option (for outputs that have source images)
            if self.item_type == 'image':
                metadata = self._get_metadata()
                input_image = metadata.get('input_image')
                input_path = os.path.join(self.output_dir, input_image) if input_image else None
                has_input = bool(input_path and os.path.exists(input_path))
                view_input_action = menu.addAction("View Input")
                view_input_action.triggered.connect(lambda: self._view_input(input_path))
                view_input_action.setEnabled(has_input)
                if not has_input and input_image:
                    view_input_action.setText("View Input (not found)")

            menu.addSeparator()

            # Properties
            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(self._show_properties)

            menu.addSeparator()

            # Copy options
            if self.item_type == 'image':
                metadata = self._get_metadata()
                has_settings = bool(metadata.get('workflow_preset') or metadata.get('editable_values'))
                apply_settings_action = menu.addAction("Apply Settings")
                apply_settings_action.triggered.connect(self._copy_settings)
                apply_settings_action.setEnabled(has_settings)
                if not has_settings:
                    apply_settings_action.setText("Apply Settings (no metadata)")

                prompt = metadata.get('prompt', '')
                copy_prompt_action = menu.addAction("Copy Prompt")
                copy_prompt_action.triggered.connect(self._copy_prompt)
                copy_prompt_action.setEnabled(bool(prompt))

            copy_path_action = menu.addAction("Copy Path")
            copy_path_action.triggered.connect(lambda: self._copy_path(self.path))

            # Publish to AYON
            menu.addSeparator()
            publish_action = menu.addAction("Publish to AYON")
            publish_action.triggered.connect(self._publish_to_ayon)

            # Delete
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(self._delete_item)
            if not self._editable:
                delete_action.setEnabled(False)
                delete_action.setText("Delete (view only)")

            menu.exec_(self.mapToGlobal(pos))
        except Exception as e:
            logger.error(f"Exception in _show_context_menu: {e}", exc_info=True)

    def _show_batch_context_menu(self, pos):
        """Show context menu for batch operations on multiple selected items."""
        if not self._gallery_tab:
            return

        menu = QMenu(self)
        count = len(self._gallery_tab._selected_items)

        header_action = menu.addAction(f"{count} items selected")
        header_action.setEnabled(False)
        menu.addSeparator()

        # Batch like/unlike
        if self._favorites_manager:
            like_action = menu.addAction("♡ Like Selected")
            like_action.triggered.connect(lambda: self._batch_like(True))

            unlike_action = menu.addAction("♥ Unlike Selected")
            unlike_action.triggered.connect(lambda: self._batch_like(False))

            # Groups submenu for batch operations
            groups_menu = menu.addMenu("Add Selected to Group")
            groups = self._favorites_manager.get_groups()

            for group in groups:
                action = groups_menu.addAction(f"● {group.name}")
                action.triggered.connect(
                    lambda checked, gid=group.group_id: self._batch_add_to_group(gid)
                )

            if groups:
                groups_menu.addSeparator()

            new_group_action = groups_menu.addAction("+ New Group...")
            new_group_action.triggered.connect(self._create_new_group_for_batch)

            menu.addSeparator()

        view_action = menu.addAction("View Selected")
        view_action.triggered.connect(self._gallery_tab._on_view_selected)

        menu.addSeparator()
        publish_action = menu.addAction("Publish to AYON")
        publish_action.triggered.connect(self._gallery_tab._on_publish_selected)

        menu.addSeparator()
        delete_action = menu.addAction("Delete Selected")
        delete_action.triggered.connect(self._gallery_tab._on_delete_selected)
        if not self._editable:
            delete_action.setEnabled(False)
            delete_action.setText("Delete Selected (view only)")

        menu.addSeparator()
        clear_action = menu.addAction("Clear Selection")
        clear_action.triggered.connect(self._gallery_tab._clear_selection)

        menu.exec_(self.mapToGlobal(pos))

    def _batch_like(self, like=True):
        """Like or unlike all selected items."""
        if not self._favorites_manager or not self._gallery_tab:
            return
        paths = list(self._gallery_tab._selected_items)
        if like:
            self._favorites_manager.like_items(paths)
            msg = f"Liked {len(paths)} items"
        else:
            self._favorites_manager.unlike_items(paths)
            msg = f"Unliked {len(paths)} items"
        # Update visuals for all selected widgets
        self._gallery_tab._refresh_favorites_state()
        if hasattr(self._gallery_tab, 'show_status_message'):
            self._gallery_tab.show_status_message(msg)

    def _batch_add_to_group(self, group_id):
        """Add all selected items to a group."""
        if not self._favorites_manager or not self._gallery_tab:
            return
        paths = list(self._gallery_tab._selected_items)
        self._favorites_manager.add_items_to_group(paths, group_id)
        group = self._favorites_manager.get_group(group_id)
        self._gallery_tab._refresh_favorites_state()
        if group and hasattr(self._gallery_tab, 'show_status_message'):
            self._gallery_tab.show_status_message(f"Added {len(paths)} items to {group.name}")

    def _create_new_group_for_batch(self):
        """Create a new group and add all selected items to it."""
        from dialogs import GroupEditorDialog
        dialog = GroupEditorDialog(parent=self)
        if dialog.exec_():
            name, color = dialog.get_result()
            if name and self._favorites_manager and self._gallery_tab:
                group_id = self._favorites_manager.create_group(name, color)
                paths = list(self._gallery_tab._selected_items)
                self._favorites_manager.add_items_to_group(paths, group_id)
                self._gallery_tab._refresh_favorites_state()
                if hasattr(self._gallery_tab, 'show_status_message'):
                    self._gallery_tab.show_status_message(f"Created '{name}' with {len(paths)} items")

    def _publish_to_ayon(self):
        """Publish this item to AYON."""
        parent_window = get_active_window()
        try:
            from comfyui.ayon_publisher import publish_comfyui_asset_to_ayon
            publish_comfyui_asset_to_ayon(self.path, parent_window, self.output_dir)
        except Exception as e:
            logger.error(f"Error publishing to AYON: {e}")

    def _open_item(self):
        try:
            os.startfile(self.path)
        except Exception as e:
            logger.error(f"Error opening item: {e}")

    def _open_folder(self):
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{self.path}"')
        except Exception as e:
            logger.error(f"Error opening folder: {e}")

    def _view_input(self, input_path):
        """Open the input image that was used to generate this output."""
        if not input_path or not os.path.exists(input_path):
            logger.warning(f"Input image not found: {input_path}")
            return
        try:
            os.startfile(input_path)
        except Exception as e:
            logger.error(f"Error opening input image: {e}")

    def _delete_item(self):
        from PySide6.QtWidgets import QMessageBox
        filename = os.path.basename(self.path)
        parent_window = get_active_window()
        reply = QMessageBox.question(
            parent_window, "Delete Item",
            f"Are you sure you want to delete '{filename}'?\n\nThis will permanently delete the file from disk.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                os.remove(self.path)
                logger.info(f"Deleted file: {self.path}")
                self.deleted.emit(self.path)
                container = self.parentWidget()
                if container:
                    container.setUpdatesEnabled(False)
                    try:
                        layout = container.layout()
                        if layout:
                            for i in range(layout.count()):
                                item = layout.itemAt(i)
                                if item and item.widget() is self:
                                    layout.takeAt(i)
                                    break
                        self.setParent(None)
                        self.deleteLater()
                    finally:
                        container.setUpdatesEnabled(True)
                else:
                    self.setParent(None)
                    self.deleteLater()
            except Exception as e:
                logger.error(f"Error deleting file: {e}")
                QMessageBox.critical(parent_window, "Delete Error", f"Could not delete file:\n{e}")

    def _edit_item(self):
        try:
            parent_window = get_active_window()
            if self.item_type == 'model':
                dialog = EditModelDialog(self.path, self.output_dir, parent_window)
            else:
                dialog = EditItemDialog(self.path, self.output_dir, parent_window)
            if dialog.exec() == QDialog.Accepted:
                self._tooltip_loaded = False
                self._load_tooltip_async()
        except Exception as e:
            logger.error(f"Error opening edit item dialog: {e}")

    def _show_properties(self):
        """Show comprehensive properties dialog for this item."""
        try:
            parent_window = get_active_window()

            from properties_dialog import PropertiesDialog
            metadata = self._get_metadata()

            dialog = PropertiesDialog(
                self.path,
                self.output_dir,
                metadata=metadata,
                parent=parent_window
            )
            dialog.exec()
        except Exception as e:
            logger.error(f"Error showing properties: {e}")



# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def enhance_ui(parent_widget):
    """Initialize UI animations for the parent widget."""
    animator = UIAnimations(parent_widget)
    animator.setup_animations()
    return animator


# ============================================================================
# GALLERY SELECTION TOOLBAR
# ============================================================================

class GallerySelectionToolbar(QWidget):
    """Floating toolbar for gallery multi-select actions."""

    # Signals for multi-select actions
    delete_selected = Signal()
    publish_selected = Signal()
    view_selected = Signal()
    clear_selection = Signal()

    # Signals for ComfyUI cross-tab actions
    use_in_comfyui = Signal(list)  # List of selected paths
    copy_prompt = Signal(str)  # Path of item to copy prompt from
    compare_to_source = Signal(str)  # Path of item to compare
    recreate_settings = Signal(str)  # Path of item to recreate from

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_paths = []
        self._setup_ui()

    def _setup_ui(self):
        """Setup the toolbar UI."""
        # Enable styled background painting for QWidget with rgba colors
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        # Main horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Selection count label
        self.count_label = QLabel("0 items selected")
        self.count_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
                padding: 4px;
            }
        """)
        layout.addWidget(self.count_label)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet("color: rgba(255, 255, 255, 0.3);")
        layout.addWidget(sep1)

        # === ComfyUI Actions (show for single or multi-select) ===

        # Use in ComfyUI button
        self.use_comfyui_btn = QPushButton("Use in ComfyUI")
        self.use_comfyui_btn.setToolTip("Load selected images as ComfyUI inputs")
        self.use_comfyui_btn.clicked.connect(self._on_use_in_comfyui)
        self.use_comfyui_btn.setStyleSheet(self._get_button_style("#059669"))  # Green
        layout.addWidget(self.use_comfyui_btn)

        # Copy Prompt button (single selection only)
        self.copy_prompt_btn = QPushButton("Copy Prompt")
        self.copy_prompt_btn.setToolTip("Copy the prompt text from this image")
        self.copy_prompt_btn.clicked.connect(self._on_copy_prompt)
        self.copy_prompt_btn.setStyleSheet(self._get_button_style())
        layout.addWidget(self.copy_prompt_btn)

        # Compare to Source button (single selection only)
        self.compare_btn = QPushButton("Compare")
        self.compare_btn.setToolTip("Open side-by-side with the source image")
        self.compare_btn.clicked.connect(self._on_compare_to_source)
        self.compare_btn.setStyleSheet(self._get_button_style())
        layout.addWidget(self.compare_btn)

        # Recreate Settings button (single selection only)
        self.recreate_btn = QPushButton("Recreate")
        self.recreate_btn.setToolTip("Restore all ComfyUI settings from this image")
        self.recreate_btn.clicked.connect(self._on_recreate_settings)
        self.recreate_btn.setStyleSheet(self._get_button_style())
        layout.addWidget(self.recreate_btn)

        # Separator
        sep2 = QLabel("|")
        sep2.setStyleSheet("color: rgba(255, 255, 255, 0.3);")
        layout.addWidget(sep2)

        # === Standard Actions ===

        # View selected button
        self.view_btn = QPushButton("View")
        self.view_btn.setToolTip("Open selected images in viewer")
        self.view_btn.clicked.connect(self.view_selected.emit)
        self.view_btn.setStyleSheet(self._get_button_style())
        layout.addWidget(self.view_btn)

        # Publish to AYON button
        self.publish_btn = QPushButton("Publish")
        self.publish_btn.setToolTip("Publish selected images to AYON")
        self.publish_btn.clicked.connect(self.publish_selected.emit)
        self.publish_btn.setStyleSheet(self._get_button_style())
        layout.addWidget(self.publish_btn)

        # Delete button
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setToolTip("Delete selected images")
        self.delete_btn.clicked.connect(self.delete_selected.emit)
        self.delete_btn.setStyleSheet(self._get_button_style("#dc2626"))
        layout.addWidget(self.delete_btn)

        # Clear selection button
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setToolTip("Clear selection (Escape)")
        self.clear_btn.setFixedSize(28, 28)
        self.clear_btn.clicked.connect(self.clear_selection.emit)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9ca3af;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
        """)
        layout.addWidget(self.clear_btn)

        # Toolbar background style - 65% opacity with darker, less saturated blue
        self.setStyleSheet("""
            GallerySelectionToolbar {
                background-color: rgba(45, 65, 95, 0.65);
                border: 1px solid rgba(70, 90, 120, 0.6);
                border-radius: 8px;
            }
        """)

    def _get_button_style(self, hover_color="#2563eb"):
        """Get button stylesheet with optional custom hover color."""
        return f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.15);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
                border-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 0, 0, 0.2);
            }}
        """

    def _on_use_in_comfyui(self):
        """Handle 'Use in ComfyUI' action."""
        if self._selected_paths:
            self.use_in_comfyui.emit(self._selected_paths)

    def _on_copy_prompt(self):
        """Handle 'Copy Prompt' action."""
        if self._selected_paths:
            self.copy_prompt.emit(self._selected_paths[0])

    def _on_compare_to_source(self):
        """Handle 'Compare to Source' action."""
        if self._selected_paths:
            self.compare_to_source.emit(self._selected_paths[0])

    def _on_recreate_settings(self):
        """Handle 'Recreate Settings' action."""
        if self._selected_paths:
            self.recreate_settings.emit(self._selected_paths[0])

    def update_count(self, count, selected_paths=None):
        """Update the selection count display and button states.

        Args:
            count: Number of selected items
            selected_paths: List of selected file paths (optional, for ComfyUI actions)
        """
        # Store paths for ComfyUI actions
        self._selected_paths = list(selected_paths) if selected_paths else []

        # Update count label
        if count == 1:
            self.count_label.setText("1 selected")
        else:
            self.count_label.setText(f"{count} selected")

        # Update button states based on selection count
        has_single = count == 1
        has_any = count > 0

        # ComfyUI actions
        self.use_comfyui_btn.setEnabled(has_any)
        self.copy_prompt_btn.setEnabled(has_single)
        self.copy_prompt_btn.setVisible(has_single)
        self.compare_btn.setEnabled(has_single)
        self.compare_btn.setVisible(has_single)
        self.recreate_btn.setEnabled(has_single)
        self.recreate_btn.setVisible(has_single)

    def position_at_bottom(self, parent_widget):
        """Position toolbar at bottom center of parent widget."""
        # Calculate position
        parent_width = parent_widget.width()
        toolbar_width = self.sizeHint().width()
        x = (parent_width - toolbar_width) // 2
        y = parent_widget.height() - self.sizeHint().height() - 20

        # Position and ensure visible
        self.move(x, y)
        self.raise_()


def load_stylesheet():
    """Load combined QDarkStyle and custom stylesheet."""
    from config import QDARKSTYLE_PATH, CUSTOM_STYLE_PATH
    file = QFile(QDARKSTYLE_PATH)
    file.open(QFile.ReadOnly | QFile.Text)
    stream = QTextStream(file)
    base_style = stream.readAll()
    file.close()
    custom_file = QFile(CUSTOM_STYLE_PATH)
    custom_file.open(QFile.ReadOnly | QFile.Text)
    custom_stream = QTextStream(custom_file)
    custom_style = custom_stream.readAll()
    custom_file.close()
    return base_style + "\n" + custom_style


def apply_stylesheet(app):
    """Apply stylesheet to the application."""
    stylesheet = load_stylesheet()
    app.setStyleSheet(stylesheet)


