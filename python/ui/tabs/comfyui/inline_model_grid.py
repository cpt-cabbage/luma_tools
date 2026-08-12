"""
Inline Model Grid for ComfyUI Tab.

Displays workflow models as visual cards directly in the tab,
replacing the full-screen overlay for a streamlined experience.

Features:
- Visual card grid with thumbnails
- Single-click to select
- Inline search bar
- Responsive flow layout (adapts to tab width)
- Selected model highlighted
"""

import logging
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QPixmap, QFont, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QScrollArea, QSizePolicy, QGridLayout,
    QPushButton, QMenu,
)

from core.state_manager import app_state
from core.settings_manager import safe_get_setting, safe_set_setting
from comfyui.presets_manager import get_comfyui_workflow_presets
from comfyui.ratings import get_sorted_models, get_model_rating, get_predefined_tags

from core.design_tokens import set_role

logger = logging.getLogger(__name__)

# Card dimensions
CARD_MIN_WIDTH = 190
CARD_MAX_WIDTH = 280
THUMB_HEIGHT = 120
CARD_SPACING = 10

# Colors
GRID_BG = "#1e2127"

# Output type display
OUTPUT_TYPE_CONFIG = {
    "image": ("IMAGE", "#4a9eff", "rgba(74, 158, 255, 0.15)"),
    "video": ("VIDEO", "#a855f7", "rgba(168, 85, 247, 0.15)"),
    "3d": ("3D MODEL", "#10b981", "rgba(16, 185, 129, 0.15)"),
    "audio": ("AUDIO", "#f59e0b", "rgba(245, 158, 11, 0.15)"),
    "other": ("OTHER", "#797e89", "rgba(121, 126, 137, 0.15)"),
}

# Sort options (label, key)
SORT_OPTIONS = [
    ("Recently Used", "recently_used"),
    ("Highest Rated", "highest_rated"),
    ("Most Used", "most_used"),
    ("Name (A-Z)", "name"),
]

# Filter button styling


class _InlineModelCard(QFrame):
    """
    Simplified visual card for inline model selection.

    Shows: thumbnail, name, output type badge, one-line description.
    Single-click to select.
    """

    clicked = Signal(str)
    context_menu_requested = Signal(str, object)  # model_name, QPoint

    def __init__(self, model_name: str, preset_config: Dict[str, Any],
                 thumbnail_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._model_name = model_name
        self._preset_config = preset_config
        self._thumbnail_path = thumbnail_path
        self._is_selected = False
        self._is_hovered = False

        self.setObjectName("InlineModelCard")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(CARD_MIN_WIDTH)

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Thumbnail
        self._thumbnail = QLabel()
        self._thumbnail.setFixedHeight(THUMB_HEIGHT)
        self._thumbnail.setAlignment(Qt.AlignCenter)
        self._thumbnail.setProperty("variant", "thumb")
        self._load_thumbnail()
        layout.addWidget(self._thumbnail)

        # Info area
        info = QWidget()
        info.setProperty("variant", "transparent")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(10, 8, 10, 10)
        info_layout.setSpacing(4)

        # Name + badge row
        top = QHBoxLayout()
        top.setSpacing(6)

        display_name = self._get_display_name()
        self._name_label = QLabel(display_name)
        self._name_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._name_label.setToolTip(self._model_name)
        top.addWidget(self._name_label, 1)

        output_type = self._preset_config.get("output_type", "image")
        label_text, fg, bg = OUTPUT_TYPE_CONFIG.get(output_type, OUTPUT_TYPE_CONFIG["image"])
        badge = QLabel(label_text)
        badge.setStyleSheet(
            f"background-color: {bg}; color: {fg};"
            "border-radius: 3px; padding: 1px 6px;"
            "font-size: 9px; font-weight: bold;"
        )
        badge.setFixedHeight(16)
        top.addWidget(badge)
        info_layout.addLayout(top)

        # Description
        desc = self._preset_config.get("description", "").strip()
        self._desc_label = QLabel(desc or "")
        self._desc_label.setFont(QFont("Segoe UI", 9))
        self._desc_label.setProperty("textRole", "help")
        self._desc_label.setWordWrap(True)
        self._desc_label.setMaximumHeight(32)
        if desc:
            info_layout.addWidget(self._desc_label)

        layout.addWidget(info)

    def _load_thumbnail(self):
        if self._thumbnail_path and os.path.exists(self._thumbnail_path):
            pixmap = QPixmap(self._thumbnail_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    CARD_MAX_WIDTH, THUMB_HEIGHT,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                if scaled.width() > CARD_MAX_WIDTH:
                    x = (scaled.width() - CARD_MAX_WIDTH) // 2
                    scaled = scaled.copy(x, 0, CARD_MAX_WIDTH, min(scaled.height(), THUMB_HEIGHT))
                self._thumbnail.setPixmap(scaled)
                return
        self._thumbnail.setText("No Preview")

    def _get_display_name(self) -> str:
        name = self._model_name
        for sep in ('/', '\\'):
            if sep in name:
                name = name.rsplit(sep, 1)[-1]
        return name

    def _apply_style(self):
        # Hover is handled by QFrame[variant="card"]:hover in the stylesheet,
        # so only selection needs to be pushed through as state.
        set_role(self, variant="card",
                 state="selected" if self._is_selected else None)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._apply_style()

    @property
    def model_name(self) -> str:
        return self._model_name

    def enterEvent(self, event):
        # No restyle here: hover is a QSS pseudo-state now, and unpolishing
        # every card on every mouse-over was pure churn.
        self._is_hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._model_name)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(self._model_name, event.globalPos())
        event.accept()


class InlineModelGrid(QWidget):
    """
    Grid of model cards displayed directly in the ComfyUI tab.

    Replaces the full-screen overlay picker with an inline experience.
    Shows all models as visual cards with search filtering.

    Signals:
        model_selected(str): Emitted when a model card is clicked
    """

    model_selected = Signal(str)
    add_model_requested = Signal()
    edit_model_requested = Signal(str)
    delete_model_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: Dict[str, _InlineModelCard] = {}
        self._current_model: Optional[str] = None
        self._search_text = ""
        self._all_models: List[Dict[str, Any]] = []

        # Persisted sort/filter preferences
        self._sort_key = safe_get_setting("comfyui_model_sort", "recently_used")
        self._category_filter = safe_get_setting("comfyui_model_filter", "all")

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # Row 1: Title + search + add button
        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("Choose a Model")
        title.setProperty("textRole", "display")
        header.addWidget(title)
        header.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search models...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedWidth(220)
        self._search_input.textChanged.connect(self._on_search_changed)
        header.addWidget(self._search_input)

        # Add Model button (admin only)
        self._add_model_btn = QPushButton("+ Add Model")
        self._add_model_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._add_model_btn.setProperty("role", "ghost")
        self._add_model_btn.setProperty("state", "success")
        self._add_model_btn.clicked.connect(self.add_model_requested.emit)
        self._add_model_btn.setVisible(app_state.is_admin)
        header.addWidget(self._add_model_btn)

        outer.addLayout(header)

        # Row 2: Filter/sort bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        # Favorites toggle
        self._fav_btn = QPushButton("★ Favorites")
        self._fav_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._fav_btn.setCheckable(True)
        self._fav_btn.setChecked(self._category_filter == "favorites")
        self._fav_btn.clicked.connect(self._on_favorites_toggled)
        self._update_fav_btn_style()
        filter_bar.addWidget(self._fav_btn)

        # Category dropdown
        self._category_btn = QPushButton("Category: All")
        self._category_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._category_btn.setProperty("role", "secondary")
        self._category_menu = QMenu(self._category_btn)
        self._rebuild_category_menu()
        self._category_btn.setMenu(self._category_menu)
        self._category_btn.setProperty("hasMenu", "true")
        filter_bar.addWidget(self._category_btn)

        # Sort dropdown
        sort_label = dict(SORT_OPTIONS).get(self._sort_key, "Recently Used")
        # Reverse lookup: key → label
        for label, key in SORT_OPTIONS:
            if key == self._sort_key:
                sort_label = label
                break
        self._sort_btn = QPushButton(f"Sort: {sort_label}")
        self._sort_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._sort_btn.setProperty("role", "secondary")
        sort_menu = QMenu(self._sort_btn)
        for label, key in SORT_OPTIONS:
            action = sort_menu.addAction(label)
            action.triggered.connect(lambda checked=False, k=key, l=label: self._on_sort_selected(k, l))
        self._sort_btn.setMenu(sort_menu)
        self._sort_btn.setProperty("hasMenu", "true")
        filter_bar.addWidget(self._sort_btn)

        filter_bar.addStretch()

        # Result count
        self._count_label = QLabel("")
        self._count_label.setProperty("textRole", "help")
        filter_bar.addWidget(self._count_label)

        outer.addLayout(filter_bar)

        # Scrollable card grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(CARD_SPACING)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)

        self._scroll.setWidget(self._grid_widget)
        outer.addWidget(self._scroll, 1)

        # Empty state
        self._empty_label = QLabel("No models available")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setProperty("textRole", "help")
        self._empty_label.setVisible(False)
        outer.addWidget(self._empty_label)

        # Debounce timer for search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_filter)

        # Sync initial filter UI state
        self._update_category_btn_label()

    def refresh(self):
        """Reload models from presets and rebuild the grid."""
        presets = get_comfyui_workflow_presets()
        username = app_state.user

        # Apply category filter
        tag_filter = None if self._category_filter == "all" else self._category_filter

        # get_sorted_models returns List[Tuple[name, preset_config, rating_data]]
        raw = get_sorted_models(
            presets,
            sort_key=self._sort_key,
            tag_filter=tag_filter,
            search_query=self._search_text if self._search_text else None,
            username=username,
        )
        # Normalize to list of dicts for easier handling
        self._all_models = [
            {"name": name, "preset_config": cfg, "rating_data": rd}
            for name, cfg, rd in raw
        ]
        self._rebuild_grid()

    def set_current_model(self, model_name: Optional[str]):
        """Highlight the currently selected model."""
        old = self._current_model
        self._current_model = model_name

        if old and old in self._cards:
            self._cards[old].set_selected(False)
        if model_name and model_name in self._cards:
            self._cards[model_name].set_selected(True)

    def _rebuild_grid(self):
        """Rebuild the card grid from current model list."""
        # Clear existing cards
        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        # Remove all items from grid layout
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        models = self._all_models

        # Update count label
        self._count_label.setText(f"{len(models)} model{'s' if len(models) != 1 else ''}")

        if not models:
            self._empty_label.setVisible(True)
            self._scroll.setVisible(False)
            if self._search_text:
                self._empty_label.setText(f'No models matching "{self._search_text}"')
            elif self._category_filter == "favorites":
                self._empty_label.setText("No favorite models yet")
            elif self._category_filter != "all":
                self._empty_label.setText(f'No models in category "{self._category_filter}"')
            else:
                self._empty_label.setText("No models available")
            return

        self._empty_label.setVisible(False)
        self._scroll.setVisible(True)

        # Calculate columns based on available width
        available_width = max(self.width() - 20, 600)
        cols = max(1, available_width // (CARD_MIN_WIDTH + CARD_SPACING))
        cols = min(cols, 5)  # Cap at 5 columns

        for i, model_data in enumerate(models):
            name = model_data["name"]
            preset_config = model_data.get("preset_config", {})
            rating_data = model_data.get("rating_data", {})
            thumbnail = rating_data.get("thumbnail_path")

            card = _InlineModelCard(name, preset_config, thumbnail, parent=self._grid_widget)
            card.clicked.connect(self._on_card_clicked)
            card.context_menu_requested.connect(self._on_card_context_menu)

            if name == self._current_model:
                card.set_selected(True)

            row, col = divmod(i, cols)
            self._grid_layout.addWidget(card, row, col)
            self._cards[name] = card

        # Fill remaining cells in last row with spacers
        remainder = len(models) % cols
        if remainder > 0:
            last_row = len(models) // cols
            for c in range(remainder, cols):
                spacer = QWidget()
                spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                self._grid_layout.addWidget(spacer, last_row, c)

    def _on_card_clicked(self, model_name: str):
        """Handle card click — select and emit."""
        self.set_current_model(model_name)
        self.model_selected.emit(model_name)

    def _on_card_context_menu(self, model_name: str, pos):
        """Handle right-click on a card — show edit/delete menu for admins."""
        if not app_state.is_admin:
            return

        menu = QMenu(self)
        edit_action = menu.addAction("Edit Model...")
        edit_action.triggered.connect(lambda: self.edit_model_requested.emit(model_name))

        menu.addSeparator()

        delete_action = menu.addAction("Delete Model")
        delete_action.triggered.connect(lambda: self.delete_model_requested.emit(model_name))

        menu.exec_(pos)

    # ------------------------------------------------------------------
    # Filter / Sort handlers
    # ------------------------------------------------------------------

    def _on_favorites_toggled(self):
        """Toggle favorites filter."""
        if self._fav_btn.isChecked():
            self._category_filter = "favorites"
        else:
            self._category_filter = "all"
        self._update_fav_btn_style()
        self._update_category_btn_label()
        safe_set_setting("comfyui_model_filter", self._category_filter)
        self.refresh()

    def _on_category_selected(self, category: str):
        """Handle category selection from dropdown."""
        self._category_filter = category
        self._fav_btn.setChecked(False)
        self._update_fav_btn_style()
        self._update_category_btn_label()
        safe_set_setting("comfyui_model_filter", self._category_filter)
        self.refresh()

    def _on_sort_selected(self, sort_key: str, label: str):
        """Handle sort selection from dropdown."""
        self._sort_key = sort_key
        self._sort_btn.setText(f"Sort: {label}")
        safe_set_setting("comfyui_model_sort", sort_key)
        self.refresh()

    def _update_fav_btn_style(self):
        """Update favorites button style based on checked state."""
        if self._fav_btn.isChecked():
            set_role(self._fav_btn, state="active")
        else:
            set_role(self._fav_btn, state=None)

    def _update_category_btn_label(self):
        """Update category button text based on current filter."""
        if self._category_filter in ("all", "favorites"):
            self._category_btn.setText("Category: All")
            set_role(self._category_btn, state=None)
        else:
            self._category_btn.setText(f"Category: {self._category_filter}")
            set_role(self._category_btn, state="active")

    def _rebuild_category_menu(self):
        """Rebuild category dropdown menu from current tags."""
        self._category_menu.clear()

        # "All" option
        all_action = self._category_menu.addAction("All")
        all_action.triggered.connect(lambda: self._on_category_selected("all"))

        self._category_menu.addSeparator()

        # Tag-based categories
        for tag in get_predefined_tags():
            action = self._category_menu.addAction(tag)
            action.triggered.connect(
                lambda checked=False, t=tag: self._on_category_selected(t)
            )

    def _on_search_changed(self, text: str):
        self._search_text = text.strip()
        self._search_timer.start(150)

    def _apply_filter(self):
        self.refresh()

    def resizeEvent(self, event):
        """Rebuild grid on resize to adapt column count."""
        super().resizeEvent(event)
        if self._all_models:
            self._rebuild_grid()
