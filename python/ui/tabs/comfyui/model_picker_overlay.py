"""
Full-Screen Model Picker Overlay for ComfyUI Tab.

An immersive overlay experience for browsing and selecting workflow models,
inspired by Netflix, Spotify, and modern game launchers.

Features:
- Full-screen dark backdrop with fade animation
- Left sidebar with categories (including Favorites) and sort options
- Responsive card grid with Netflix-style hover
- Search with instant filtering
- Keyboard navigation (Escape to close)
"""

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QScrollArea
)

from core.settings_manager import get_setting, set_setting
from core.state_manager import app_state
from comfyui.presets_manager import get_comfyui_workflow_presets
from comfyui.ratings import (
    get_sorted_models, get_predefined_tags, get_model_rating,
    increment_model_usage, get_user_favorites, get_user_recents,
    toggle_favorite, add_to_recents, refresh_all_thumbnails
)

logger = logging.getLogger(__name__)

# Styling constants
OVERLAY_BACKDROP = "rgba(0, 0, 0, 0.85)"
SIDEBAR_BG = "#1a1d21"
CONTENT_BG = "#0f1114"
CARD_BG = "#2c313a"
CARD_BORDER = "#3c414b"
CARD_BORDER_HOVER = "#4a9eff"
STAR_GOLD = "#fbbf24"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#888888"
ACCENT = "#4a9eff"

# Dimensions
SIDEBAR_WIDTH = 220
CONTENT_PADDING = 24

# Animation timings (ms)
FADE_DURATION = 150
SLIDE_DURATION = 200


class OverlayBackdrop(QWidget):
    """Semi-transparent backdrop that catches clicks outside content."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {OVERLAY_BACKDROP};")

    def mousePressEvent(self, event):
        """Emit clicked signal when backdrop is clicked."""
        self.clicked.emit()
        event.accept()


class ModelPickerOverlay(QWidget):
    """
    Full-screen overlay for immersive model selection.

    Signals:
        model_selected(str, str): Emitted when model is selected (model_name, workflow_name)
        closed(): Emitted when overlay is closed
        add_model_requested(): Emitted when Add Model button is clicked
    """

    model_selected = Signal(str, str)
    closed = Signal()
    add_model_requested = Signal()

    def __init__(self, is_admin: bool = False, parent=None):
        super().__init__(parent)
        self._is_admin = is_admin
        self._is_visible = False
        self._current_model: Optional[str] = None
        self._search_text = ""
        self._sort_key = get_setting("comfyui_model_sort")
        self._category_filter = get_setting("comfyui_model_filter")

        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)

        self._setup_ui()
        self._setup_animations()
        self._connect_signals()

        # Install event filter on parent to catch resize events
        if parent:
            parent.installEventFilter(self)

        # Start hidden
        self.hide()

    def _setup_ui(self):
        """Set up the overlay UI structure."""
        # Main layout fills entire parent
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Backdrop (catches clicks)
        self._backdrop = OverlayBackdrop(self)

        # Content container (centered card with padding)
        self._content = QFrame(self)
        self._content.setObjectName("OverlayContent")
        self._content.setStyleSheet(f"""
            QFrame#OverlayContent {{
                background-color: {CONTENT_BG};
                border-radius: 12px;
            }}
        """)

        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Header bar
        self._setup_header(content_layout)

        # Main area: sidebar + content
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Left sidebar
        self._setup_sidebar(body_layout)

        # Right content area (quick access + grid)
        self._setup_main_content(body_layout)

        content_layout.addLayout(body_layout, 1)

        # NOTE: QGraphicsOpacityEffect removed - causes QPainter conflicts
        # with child widgets, making cards invisible. Using simple show/hide instead.

        main_layout.addWidget(self._backdrop)

    def _setup_header(self, parent_layout: QVBoxLayout):
        """Set up the header bar with title, search, and close button."""
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {SIDEBAR_BG};
                border-bottom: 1px solid #2a2d32;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
        """)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)
        header_layout.setSpacing(16)

        # Title
        title = QLabel("Model Library")
        title.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: 18px;
            font-weight: bold;
        """)
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Search box
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search models...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedWidth(300)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #2a2d32;
                border: 1px solid #3c414b;
                border-radius: 6px;
                padding: 8px 12px;
                color: {TEXT_PRIMARY};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {ACCENT};
            }}
        """)
        header_layout.addWidget(self._search_input)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 18px;
                font-size: 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3c414b;
                color: {TEXT_PRIMARY};
            }}
        """)
        close_btn.clicked.connect(self.hide_overlay)
        header_layout.addWidget(close_btn)

        parent_layout.addWidget(header)

    def _setup_sidebar(self, parent_layout: QHBoxLayout):
        """Set up the left sidebar with categories and sort."""
        from .picker_sidebar import PickerSidebar

        self._sidebar = PickerSidebar(is_admin=self._is_admin)
        self._sidebar.setFixedWidth(SIDEBAR_WIDTH)

        parent_layout.addWidget(self._sidebar)

    def _setup_main_content(self, parent_layout: QHBoxLayout):
        """Set up the main content area with quick access and grid."""
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(CONTENT_PADDING, CONTENT_PADDING,
                                          CONTENT_PADDING, CONTENT_PADDING)
        content_layout.setSpacing(24)

        # Scroll area for all content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(32)

        # Model grid (using bars layout for horizontal list)
        from .model_grid import ModelGrid

        self._model_grid = ModelGrid(
            on_model_selected=self._on_model_activated,
            on_favorite_toggled=self._on_favorite_toggled,
            on_context_menu=self._on_context_menu,
            layout_mode="bars"
        )
        scroll_layout.addWidget(self._model_grid)

        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        content_layout.addWidget(scroll_area, 1)

        parent_layout.addWidget(content_widget, 1)

    def _setup_animations(self):
        """Set up animations."""
        # NOTE: Fade animation removed - QGraphicsOpacityEffect causes
        # QPainter conflicts with child widgets. Using simple show/hide.
        pass

    def _connect_signals(self):
        """Connect widget signals."""
        self._backdrop.clicked.connect(self.hide_overlay)
        self._search_input.textChanged.connect(self._on_search_changed)

        # Sidebar signals
        self._sidebar.category_changed.connect(self._on_category_changed)
        self._sidebar.sort_changed.connect(self._on_sort_changed)
        self._sidebar.add_model_clicked.connect(self._on_add_model_clicked)

    def show_overlay(self):
        """Show the overlay."""
        if self._is_visible:
            return

        self._is_visible = True

        # Resize to parent
        if self.parent():
            self.setGeometry(self.parent().rect())

        # Position content
        self._position_content()

        # Show immediately
        self.show()
        self.raise_()

        # Trigger background thumbnail refresh
        self._refresh_thumbnails_background()

        # Refresh data
        self._refresh_all()

        # Focus search
        QTimer.singleShot(50, lambda: self._search_input.setFocus())

    def hide_overlay(self):
        """Hide the overlay."""
        if not self._is_visible:
            return

        self._is_visible = False
        self.hide()
        self.closed.emit()

    def _position_content(self):
        """Position the content frame within the overlay."""
        if not self.parent():
            return

        parent_rect = self.parent().rect()
        margin = 40

        # Content takes most of the space with margins
        content_rect = parent_rect.adjusted(margin, margin, -margin, -margin)
        self._content.setGeometry(content_rect)

        # Backdrop fills everything
        self._backdrop.setGeometry(parent_rect)

        # Ensure content is above backdrop in Z-order
        self._content.raise_()

    def _refresh_thumbnails_background(self):
        """Refresh thumbnails in background thread on picker open."""
        from ui_components import Worker
        from PySide6.QtCore import QThreadPool

        def do_refresh():
            try:
                updated = refresh_all_thumbnails()
                return updated
            except Exception as e:
                logger.warning(f"[Overlay] Background thumbnail refresh failed: {e}")
                return 0

        def on_done(updated):
            logger.debug(f"[Overlay] Background thumbnail refresh done: updated={updated}, type={type(updated)}")
            if updated and updated > 0:
                logger.info(f"[Overlay] Refreshed {updated} model thumbnails, refreshing favorites")
                # Refresh favorites to show new thumbnails
                self._refresh_all()
            else:
                logger.debug(f"[Overlay] No thumbnails updated, NOT refreshing")

        self._thumbnail_worker = Worker(do_refresh)
        self._thumbnail_worker.signals.result.connect(on_done)
        QThreadPool.globalInstance().start(self._thumbnail_worker)

    def _refresh_all(self):
        """Refresh all sections with current data."""
        logger.debug("[Overlay] _refresh_all called")

        # Refresh sidebar categories (picks up any changes from Settings)
        if hasattr(self, '_sidebar'):
            self._sidebar.refresh_categories()

        # Refresh main grid
        self._refresh_grid()

    def _refresh_grid(self):
        """Refresh the main model grid."""
        presets = get_comfyui_workflow_presets()
        username = app_state.user

        logger.debug(f"[Overlay] _refresh_grid called: presets={len(presets)}, filter={self._category_filter}, sort={self._sort_key}, search='{self._search_text}'")

        # Get filtered/sorted models
        tag_filter = None if self._category_filter == "all" else self._category_filter
        models = get_sorted_models(
            presets,
            sort_key=self._sort_key,
            tag_filter=tag_filter,
            search_query=self._search_text if self._search_text else None,
            username=username
        )

        logger.debug(f"[Overlay] _refresh_grid: got {len(models)} models after filter/sort")
        self._model_grid.set_models(models, username)

    def _on_search_changed(self, text: str):
        """Handle search text change."""
        logger.debug(f"[Overlay] _on_search_changed: text='{text}'")
        self._search_text = text.strip()
        # Debounce the refresh
        if not hasattr(self, '_search_timer'):
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self._refresh_grid)
        self._search_timer.start(150)

    def _on_category_changed(self, category: str):
        """Handle category filter change."""
        logger.debug(f"[Overlay] _on_category_changed: category='{category}'")
        self._category_filter = category
        set_setting("comfyui_model_filter", category, verbose=False)
        self._refresh_grid()

    def _on_sort_changed(self, sort_key: str):
        """Handle sort option change."""
        logger.debug(f"[Overlay] _on_sort_changed: sort_key='{sort_key}'")
        self._sort_key = sort_key
        set_setting("comfyui_model_sort", sort_key, verbose=False)
        self._refresh_grid()

    def _on_model_activated(self, model_name: str):
        """Handle model selection (double-click)."""
        # Increment usage and add to recents
        increment_model_usage(model_name)
        try:
            add_to_recents(model_name, app_state.user)
        except Exception:
            pass

        # Emit selection signal
        self.model_selected.emit(model_name, "")

        # Hide overlay
        self.hide_overlay()

    def _on_favorite_toggled(self, model_name: str):
        """Handle favorite toggle."""
        try:
            toggle_favorite(model_name, app_state.user)
            self._refresh_all()
        except Exception as e:
            logger.warning(f"Could not toggle favorite: {e}")

    def _on_add_model_clicked(self):
        """Handle Add Model button click."""
        self.hide_overlay()
        self.add_model_requested.emit()

    def _on_context_menu(self, model_name: str, pos: QPoint):
        """Handle context menu request."""
        if not app_state.has_elevated_access:
            return

        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)

        edit_action = menu.addAction("Edit Model...")
        edit_action.triggered.connect(lambda: self._edit_model(model_name))

        rate_action = menu.addAction("Rate Model...")
        rate_action.triggered.connect(lambda: self._rate_model(model_name))

        menu.addSeparator()

        delete_action = menu.addAction("Delete Model")
        delete_action.triggered.connect(lambda: self._delete_model(model_name))

        menu.exec_(pos)

    def _edit_model(self, model_name: str):
        """Open edit model dialog."""
        from .model_dialog import ModelDialog
        from comfyui.editable import extract_editable_nodes

        presets = get_comfyui_workflow_presets()
        preset_data = presets.get(model_name, {})

        dialog = ModelDialog(
            self.window(),
            model_name,
            preset_data,
            self.window(),
            extract_editable_nodes
        )

        if dialog.exec_():
            self._refresh_all()

    def _rate_model(self, model_name: str):
        """Open rate model dialog."""
        from .star_rating import StarRatingWidget
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        from comfyui.ratings import rate_model

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Rate: {model_name}")
        layout = QVBoxLayout(dialog)

        rating_data = get_model_rating(model_name)
        current_rating = rating_data.get("ratings", {}).get(app_state.user, 0)

        label = QLabel("Your rating:")
        layout.addWidget(label)

        rating_widget = StarRatingWidget(
            rating=float(current_rating),
            interactive=True,
            size=30
        )
        layout.addWidget(rating_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_():
            new_rating = int(rating_widget.get_rating())
            if new_rating > 0:
                rate_model(model_name, app_state.user, new_rating)
                self._refresh_all()

    def _delete_model(self, model_name: str):
        """Delete a model."""
        from dialog_helpers import confirm_action
        from comfyui.presets_manager import delete_comfyui_workflow_preset
        from comfyui.ratings import delete_model_data

        if confirm_action(
            "Delete Model",
            f"Delete model '{model_name}'?\n\nThis will also delete all rating data.",
            self.window()
        ):
            delete_comfyui_workflow_preset(model_name)
            delete_model_data(model_name)
            self._refresh_all()

    def refresh(self):
        """Public refresh method - reload all preset data."""
        self._refresh_all()

    def set_current_model(self, model_name: Optional[str]):
        """Set the currently selected model (for highlighting)."""
        self._current_model = model_name
        self._model_grid.set_current_model(model_name)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press - Escape to close."""
        if event.key() == Qt.Key_Escape:
            self.hide_overlay()
            event.accept()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        """Handle resize - reposition content."""
        super().resizeEvent(event)
        if self._is_visible:
            self._position_content()

    def eventFilter(self, obj, event):
        """Filter events from parent to catch resize events."""
        # Cache parent reference to avoid multiple calls
        parent = self.parent()

        # If parent is resizing and overlay is visible, update overlay size
        if obj == parent and event.type() == QEvent.Resize and self._is_visible:
            # Update overlay geometry to match parent
            if parent:
                self.setGeometry(parent.rect())
            # Content will be repositioned by our own resizeEvent

        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        """Clean up event filter on close."""
        parent = self.parent()
        if parent:
            parent.removeEventFilter(self)
        super().closeEvent(event)
