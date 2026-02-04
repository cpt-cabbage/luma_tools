"""
Model Picker Panel for ComfyUI Tab.

Inline expandable panel for browsing and selecting workflow models with:
- Search filter (instant as-you-type)
- Sort options (name, rating, usage, recently used)
- Tag filter chips
- Responsive card grid
- Context menu for admin actions
- Double-click to select and collapse

Layout when expanded:
+----------------------------------------------------------+
| [Search: ____________] [Sort: Recently Used ▼]           |
+----------------------------------------------------------+
| [All] [Upscaling] [Generation] [Video] [3D] [Animation]  |
+----------------------------------------------------------+
| +--------+ +--------+ +--------+ +--------+              |
| | Card 1 | | Card 2 | | Card 3 | | Card 4 |              |
| +--------+ +--------+ +--------+ +--------+              |
+----------------------------------------------------------+
| [+ Add Model] (admin only, bottom-right)                 |
+----------------------------------------------------------+
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QScrollArea, QLabel, QMenu, QGridLayout, QFrame,
    QSizePolicy
)

from core.settings_manager import get_setting, set_setting
from core.state_manager import app_state
from comfyui.presets_manager import get_comfyui_workflow_presets, is_workflow_preset_multi
from comfyui.ratings import (
    get_sorted_models, get_predefined_tags, get_all_tags_in_use,
    get_model_rating, increment_model_usage
)

from .model_card import ModelCard, MultiWorkflowCard, CARD_WIDTH, CARD_HEIGHT

logger = logging.getLogger(__name__)

# Sort options
SORT_OPTIONS = [
    ("Recently Used", "recently_used"),
    ("Name", "name"),
    ("Highest Rated", "highest_rated"),
    ("Most Used", "most_used"),
]


class TagFilterChip(QPushButton):
    """Clickable tag filter chip."""

    def __init__(self, tag: str, is_all: bool = False, parent=None):
        super().__init__(tag, parent)
        self._tag = tag
        self._is_all = is_all
        self._is_active = is_all  # "All" is active by default

        self.setCheckable(True)
        self.setChecked(self._is_active)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def _apply_style(self):
        """Apply style based on active state."""
        if self.isChecked():
            self.setStyleSheet("""
                QPushButton {
                    background-color: #4a9eff;
                    color: white;
                    border: none;
                    border-radius: 12px;
                    padding: 4px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #3b8fe8;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #3c3c3c;
                    color: #aaa;
                    border: none;
                    border-radius: 12px;
                    padding: 4px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    color: #fff;
                }
            """)

    @property
    def tag(self) -> str:
        return self._tag

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._is_active = checked
        self._apply_style()


class ModelPickerPanel(QWidget):
    """
    Inline expandable panel for browsing and selecting workflow models.

    Signals:
        model_selected(str, str): Emitted when a model is selected (model_name, workflow_name)
        expand_changed(bool): Emitted when panel expands/collapses
    """

    model_selected = Signal(str, str)  # (model_name, workflow_name or "")
    expand_changed = Signal(bool)
    add_model_requested = Signal()  # Emitted when add button clicked
    edit_model_requested = Signal(str)  # Emitted when edit requested (model_name)

    def __init__(self, is_admin: bool = False, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._is_admin = is_admin
        self._current_model: Optional[str] = None
        self._cards: Dict[str, ModelCard] = {}
        self._search_text = ""
        self._sort_key = get_setting("comfyui_model_sort")
        self._tag_filter = get_setting("comfyui_model_filter")

        self._setup_ui()
        self._connect_signals()

        # Start collapsed
        self._content_widget.setVisible(False)
        self._content_widget.setMaximumHeight(0)

    def _setup_ui(self):
        """Set up the picker UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Content widget (expands/collapses)
        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(0, 8, 0, 8)
        content_layout.setSpacing(8)

        # Top row: Search and Sort
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search models...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 6px 10px;
                color: #e0e0e0;
            }
            QLineEdit:focus {
                border-color: #4a9eff;
            }
        """)
        top_row.addWidget(self._search_input, 1)

        # Sort dropdown
        self._sort_combo = QComboBox()
        for label, key in SORT_OPTIONS:
            self._sort_combo.addItem(label, key)
        # Set current from settings
        for i in range(self._sort_combo.count()):
            if self._sort_combo.itemData(i) == self._sort_key:
                self._sort_combo.setCurrentIndex(i)
                break
        self._sort_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 6px 10px;
                color: #e0e0e0;
                min-width: 140px;
            }
            QComboBox:hover {
                border-color: #4a9eff;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
        """)
        top_row.addWidget(self._sort_combo)

        content_layout.addLayout(top_row)

        # Tag filter row
        self._tag_row = QHBoxLayout()
        self._tag_row.setSpacing(6)
        self._tag_chips: List[TagFilterChip] = []
        self._setup_tag_filters()
        content_layout.addLayout(self._tag_row)

        # Card grid (in scroll area)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_area.setWidget(self._grid_container)

        content_layout.addWidget(self._scroll_area, 1)

        # Bottom row: Add Model button (admin only)
        if self._is_admin:
            bottom_row = QHBoxLayout()
            bottom_row.addStretch()

            self._add_model_btn = QPushButton("+ Add Model")
            self._add_model_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #10b981;
                    border: 1px solid #10b981;
                    border-radius: 4px;
                    padding: 6px 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #10b981;
                    color: white;
                }
            """)
            bottom_row.addWidget(self._add_model_btn)

            content_layout.addLayout(bottom_row)

        main_layout.addWidget(self._content_widget)

        # Animation for expand/collapse
        self._expand_animation = QPropertyAnimation(self._content_widget, b"maximumHeight")
        self._expand_animation.setDuration(200)
        self._expand_animation.setEasingCurve(QEasingCurve.OutCubic)

    def _setup_tag_filters(self):
        """Set up tag filter chips."""
        # Clear existing
        for chip in self._tag_chips:
            chip.deleteLater()
        self._tag_chips.clear()

        # "All" chip first
        all_chip = TagFilterChip("All", is_all=True)
        all_chip.clicked.connect(lambda: self._on_tag_selected("all"))
        self._tag_row.addWidget(all_chip)
        self._tag_chips.append(all_chip)

        # Add predefined tags
        for tag in get_predefined_tags():
            chip = TagFilterChip(tag)
            chip.clicked.connect(lambda checked, t=tag: self._on_tag_selected(t))
            self._tag_row.addWidget(chip)
            self._tag_chips.append(chip)

        self._tag_row.addStretch()

        # Update active state
        self._update_tag_selection()

    def _connect_signals(self):
        """Connect widget signals."""
        self._search_input.textChanged.connect(self._on_search_changed)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        if hasattr(self, '_add_model_btn'):
            self._add_model_btn.clicked.connect(self._on_add_model_clicked)

    def _on_search_changed(self, text: str):
        """Handle search text change - filter cards."""
        self._search_text = text.strip()
        self._refresh_cards()

    def _on_sort_changed(self, index: int):
        """Handle sort selection change."""
        self._sort_key = self._sort_combo.itemData(index)
        set_setting("comfyui_model_sort", self._sort_key, verbose=False)
        self._refresh_cards()

    def _on_tag_selected(self, tag: str):
        """Handle tag filter selection."""
        self._tag_filter = tag
        set_setting("comfyui_model_filter", tag, verbose=False)
        self._update_tag_selection()
        self._refresh_cards()

    def _update_tag_selection(self):
        """Update tag chip selection states."""
        for chip in self._tag_chips:
            if chip.tag.lower() == "all":
                chip.setChecked(self._tag_filter == "all")
            else:
                chip.setChecked(chip.tag == self._tag_filter)

    def _on_add_model_clicked(self):
        """Handle Add Model button click - emit signal for tab to handle."""
        self.add_model_requested.emit()

    def expand(self):
        """Expand the picker panel with animation."""
        if self._expanded:
            return

        self._expanded = True
        self._content_widget.setVisible(True)

        # Refresh cards when expanding
        self._refresh_cards()

        # Animate height
        self._expand_animation.stop()
        self._expand_animation.setStartValue(0)
        self._expand_animation.setEndValue(400)  # Target height
        self._expand_animation.start()

        self.expand_changed.emit(True)

    def collapse(self):
        """Collapse the picker panel with animation."""
        if not self._expanded:
            return

        self._expanded = False

        # Animate height to 0
        self._expand_animation.stop()
        self._expand_animation.setStartValue(self._content_widget.height())
        self._expand_animation.setEndValue(0)
        self._expand_animation.finished.connect(self._on_collapse_finished)
        self._expand_animation.start()

        self.expand_changed.emit(False)

    def _on_collapse_finished(self):
        """Handle collapse animation finished."""
        self._content_widget.setVisible(False)
        self._expand_animation.finished.disconnect(self._on_collapse_finished)

    def toggle(self):
        """Toggle expand/collapse state."""
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def is_expanded(self) -> bool:
        """Check if panel is expanded."""
        return self._expanded

    def refresh(self):
        """Public method to refresh the picker content."""
        self._setup_tag_filters()
        self._refresh_cards()

    def _refresh_cards(self):
        """Refresh the card grid with current filters/sort."""
        # Clear existing cards
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()

        # Clear grid layout
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get presets
        presets = get_comfyui_workflow_presets()

        # Get sorted/filtered models
        tag_filter = None if self._tag_filter == "all" else self._tag_filter
        models = get_sorted_models(
            presets,
            sort_key=self._sort_key,
            tag_filter=tag_filter,
            search_query=self._search_text if self._search_text else None
        )

        if not models:
            # Show empty state
            empty_label = QLabel("No models found")
            empty_label.setStyleSheet("color: #888; font-size: 12px; padding: 20px;")
            empty_label.setAlignment(Qt.AlignCenter)
            self._grid_layout.addWidget(empty_label, 0, 0)
            return

        # Calculate columns based on available width
        available_width = self._scroll_area.viewport().width() - 20
        columns = max(1, available_width // (CARD_WIDTH + 12))

        # Create cards
        row, col = 0, 0
        for model_name, preset_config, rating_data in models:
            # Check if multi-workflow
            is_multi = preset_config.get("is_multi", False)

            if is_multi:
                card = MultiWorkflowCard(model_name, preset_config, rating_data)
            else:
                card = ModelCard(model_name, preset_config, rating_data)

            # Connect signals
            card.selected.connect(self._on_card_selected)
            card.activated.connect(self._on_card_activated)
            card.context_menu.connect(self._on_card_context_menu)

            self._grid_layout.addWidget(card, row, col)
            self._cards[model_name] = card

            # Mark current model as selected
            if model_name == self._current_model:
                card.set_selected(True)

            col += 1
            if col >= columns:
                col = 0
                row += 1

    def _on_card_selected(self, model_name: str):
        """Handle card single-click selection."""
        # Deselect previous
        if self._current_model and self._current_model in self._cards:
            self._cards[self._current_model].set_selected(False)

        # Select new
        self._current_model = model_name
        if model_name in self._cards:
            self._cards[model_name].set_selected(True)

    def _on_card_activated(self, model_name: str):
        """Handle card double-click activation."""
        # Increment usage
        increment_model_usage(model_name)

        # Emit selection
        self.model_selected.emit(model_name, "")

        # Collapse picker
        self.collapse()

    def _on_card_context_menu(self, model_name: str, pos):
        """Handle card right-click context menu."""
        if not app_state.is_admin:
            return

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
        from comfyui.presets_manager import get_comfyui_workflow_presets
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
            self._refresh_cards()

    def _rate_model(self, model_name: str):
        """Open rate model dialog."""
        from .star_rating import StarRatingWidget
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        from comfyui.ratings import rate_model, get_model_rating

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Rate: {model_name}")
        layout = QVBoxLayout(dialog)

        # Get current user rating
        rating_data = get_model_rating(model_name)
        current_user_rating = rating_data.get("ratings", {}).get(app_state.user, 0)

        label = QLabel("Your rating:")
        layout.addWidget(label)

        rating_widget = StarRatingWidget(rating=float(current_user_rating), interactive=True, size=30)
        layout.addWidget(rating_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_():
            new_rating = int(rating_widget.get_rating())
            if new_rating > 0:
                rate_model(model_name, app_state.user, new_rating)
                self._refresh_cards()

    def _delete_model(self, model_name: str):
        """Delete a model (admin only)."""
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
            self._refresh_cards()

    def set_current_model(self, model_name: Optional[str]) -> None:
        """Set the currently selected model."""
        # Deselect previous
        if self._current_model and self._current_model in self._cards:
            self._cards[self._current_model].set_selected(False)

        self._current_model = model_name

        # Select new
        if model_name and model_name in self._cards:
            self._cards[model_name].set_selected(True)

    def resizeEvent(self, event):
        """Handle resize - recalculate grid columns."""
        super().resizeEvent(event)
        if self._expanded:
            # Debounce refresh
            if not hasattr(self, '_resize_timer'):
                self._resize_timer = QTimer(self)
                self._resize_timer.setSingleShot(True)
                self._resize_timer.timeout.connect(self._refresh_cards)
            self._resize_timer.start(100)
