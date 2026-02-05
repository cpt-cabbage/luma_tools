"""
Responsive Model Grid for Model Picker Overlay.

A responsive grid layout that displays model cards with:
- Auto-adjusting columns based on available width
- Netflix-style hover effects with neighbor awareness
- Selection highlighting

Can also display as a vertical list of horizontal bars.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QPoint, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QFrame,
    QSizePolicy
)

logger = logging.getLogger(__name__)

# Grid settings
MIN_COLUMNS = 2
MAX_COLUMNS = 6
CARD_SPACING = 16

# Import card dimensions from model_card
CARD_WIDTH = 200
CARD_HEIGHT = 260

# Bar settings
BAR_SPACING = 8


class ModelGrid(QWidget):
    """
    Responsive grid of model cards with Netflix-style hover.

    The grid automatically adjusts the number of columns based on
    available width, and coordinates hover effects across neighboring cards.

    Can also display as a vertical list of horizontal bars (layout_mode="bars").
    """

    def __init__(
        self,
        on_model_selected: Optional[Callable[[str], None]] = None,
        on_favorite_toggled: Optional[Callable[[str], None]] = None,
        on_context_menu: Optional[Callable[[str, QPoint], None]] = None,
        layout_mode: str = "grid",
        parent=None
    ):
        """
        Initialize the model grid.

        Args:
            on_model_selected: Callback when model is double-clicked
            on_favorite_toggled: Callback when favorite is toggled
            on_context_menu: Callback for right-click context menu
            layout_mode: "grid" for card grid, "bars" for horizontal bars
            parent: Parent widget
        """
        super().__init__(parent)
        self._on_model_selected = on_model_selected
        self._on_favorite_toggled = on_favorite_toggled
        self._on_context_menu = on_context_menu
        self._layout_mode = layout_mode

        self._models: List[Tuple[str, Dict, Dict]] = []
        self._cards: Dict[str, 'OverlayModelCard'] = {}
        self._current_model: Optional[str] = None
        self._username: str = ""
        self._columns = 4
        self._focused_index: int = -1  # Track keyboard focus
        self._skip_resize_rebuild = False  # Flag to skip resize rebuild after set_models

        self.setFocusPolicy(Qt.StrongFocus)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the grid UI."""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Create container based on layout mode
        self._grid_container = QWidget()

        if self._layout_mode == "bars":
            # Vertical list of bars
            self._grid_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._grid_layout = QVBoxLayout(self._grid_container)
            self._grid_layout.setSpacing(BAR_SPACING)
            self._grid_layout.setContentsMargins(0, 0, 0, 0)
            self._layout.addWidget(self._grid_container, 0, Qt.AlignTop)
        else:
            # Grid of cards - use fixed sizing to prevent over-expansion
            self._grid_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self._grid_layout = QGridLayout(self._grid_container)
            self._grid_layout.setSpacing(CARD_SPACING)
            self._grid_layout.setContentsMargins(0, 0, 0, 0)
            # Add with alignment so container stays top-left even in wide parent
            self._layout.addWidget(self._grid_container, 0, Qt.AlignTop | Qt.AlignLeft)

        # Empty state widget
        self._empty_widget = QFrame()
        self._empty_widget.setStyleSheet("""
            QFrame {
                background-color: #1a1d21;
                border: 1px dashed #3c414b;
                border-radius: 12px;
                min-height: 200px;
            }
        """)

        empty_layout = QVBoxLayout(self._empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(12)

        # Icon
        empty_icon = QLabel("🔍")
        empty_icon.setStyleSheet("font-size: 32px;")
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)

        self._empty_title = QLabel("No models found")
        self._empty_title.setStyleSheet("color: #888; font-size: 16px; font-weight: bold;")
        self._empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self._empty_title)

        self._empty_hint = QLabel("Try adjusting your search or category filter")
        self._empty_hint.setStyleSheet("color: #555; font-size: 12px;")
        self._empty_hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self._empty_hint)

        self._empty_widget.hide()
        self._layout.addWidget(self._empty_widget)

    def set_models(
        self,
        models: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
        username: str
    ):
        """
        Set the models to display.

        Args:
            models: List of (model_name, preset_config, rating_data) tuples
            username: Current username for favorites
        """
        # Cancel any pending resize timeout to prevent double rebuild
        if hasattr(self, '_resize_timer') and self._resize_timer.isActive():
            self._resize_timer.stop()

        # Skip the next resize rebuild since we're about to rebuild anyway
        self._skip_resize_rebuild = True

        self._models = models
        self._username = username
        self._rebuild_grid()

        # Re-enable resize rebuilds after a short delay to let layout settle
        QTimer.singleShot(200, self._enable_resize_rebuild)

    def set_current_model(self, model_name: Optional[str]):
        """Set the currently selected model for highlighting."""
        # Deselect previous
        if self._current_model and self._current_model in self._cards:
            self._cards[self._current_model].set_selected(False)

        self._current_model = model_name

        # Select new
        if model_name and model_name in self._cards:
            self._cards[model_name].set_selected(True)

    def _rebuild_grid(self):
        """Rebuild the grid with current models."""

        # Clear existing cards - remove from layout first, then delete
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        # Clear our reference dict
        self._cards.clear()

        # Check for empty state
        if not self._models:
            self._empty_widget.show()
            self._grid_container.hide()
            return

        self._empty_widget.hide()
        self._grid_container.show()

        if self._layout_mode == "bars":
            # Build vertical list of bars
            from .model_bar import ModelBar

            for model_name, preset_config, rating_data in self._models:
                bar = ModelBar(
                    model_name=model_name,
                    preset_config=preset_config,
                    rating_data=rating_data,
                    username=self._username
                )

                # Connect signals
                bar.activated.connect(self._on_card_activated)
                bar.favorite_toggled.connect(self._on_card_favorite_toggled)
                bar.context_menu_requested.connect(self._on_card_context_menu)

                self._grid_layout.addWidget(bar)
                self._cards[model_name] = bar

                # Mark current model as selected
                if model_name == self._current_model:
                    bar.set_selected(True)

            # Add stretch at the end to push bars to the top
            self._grid_layout.addStretch()

            logger.debug(f"[ModelGrid] _rebuild_grid COMPLETE (bars): {len(self._cards)} bars")

        else:
            # Build grid of cards
            self._update_columns()

            from .model_card import OverlayModelCard

            row, col = 0, 0
            for model_name, preset_config, rating_data in self._models:
                card = OverlayModelCard(
                    model_name=model_name,
                    preset_config=preset_config,
                    rating_data=rating_data,
                    username=self._username,
                    grid_parent=self
                )

                # Connect signals
                card.activated.connect(self._on_card_activated)
                card.favorite_toggled.connect(self._on_card_favorite_toggled)
                card.context_menu_requested.connect(self._on_card_context_menu)
                card.hover_started.connect(self._on_card_hover_started)
                card.hover_ended.connect(self._on_card_hover_ended)

                self._grid_layout.addWidget(card, row, col)
                self._cards[model_name] = card

                # Mark current model as selected
                if model_name == self._current_model:
                    card.set_selected(True)

                col += 1
                if col >= self._columns:
                    col = 0
                    row += 1

            # Calculate exact size needed for the grid
            num_rows = (len(self._models) + self._columns - 1) // self._columns
            grid_width = self._columns * CARD_WIDTH + (self._columns - 1) * CARD_SPACING
            grid_height = num_rows * CARD_HEIGHT + (num_rows - 1) * CARD_SPACING

            # Set fixed size on container to prevent layout from spreading cards
            self._grid_container.setFixedSize(grid_width, grid_height)

            # Force layout update
            self._grid_layout.activate()
            for card in self._cards.values():
                card.show()

            logger.debug(f"[ModelGrid] _rebuild_grid COMPLETE: {len(self._cards)} cards, {self._columns} cols, size={grid_width}x{grid_height}")

            # Log card details for debugging
            for name, card in self._cards.items():
                logger.debug(f"[ModelGrid] Card '{name}': visible={card.isVisible()}, geometry={card.geometry()}, parent={card.parent()}")

    def _update_columns(self):
        """Calculate and update the number of columns based on width."""
        available_width = self.width() - 20  # Account for scrollbar
        if available_width <= 0:
            available_width = 800  # Default

        card_with_spacing = CARD_WIDTH + CARD_SPACING
        columns = max(MIN_COLUMNS, min(MAX_COLUMNS, available_width // card_with_spacing))
        self._columns = columns
        logger.debug(f"[ModelGrid] _update_columns: available_width={available_width}, columns={columns}")

    def _on_card_activated(self, model_name: str):
        """Handle card double-click."""
        if self._on_model_selected:
            self._on_model_selected(model_name)

    def _on_card_favorite_toggled(self, model_name: str):
        """Handle favorite toggle."""
        if self._on_favorite_toggled:
            self._on_favorite_toggled(model_name)

    def _on_card_context_menu(self, model_name: str, pos: QPoint):
        """Handle context menu request."""
        if self._on_context_menu:
            self._on_context_menu(model_name, pos)

    def _on_card_hover_started(self, model_name: str):
        """Handle card hover start - shift neighbors (grid mode only)."""
        if self._layout_mode == "bars":
            return  # No neighbor shifting for bars

        if model_name not in self._cards:
            return

        card = self._cards[model_name]
        card_index = self._get_card_index(model_name)
        if card_index < 0:
            return

        row = card_index // self._columns
        col = card_index % self._columns

        # Get neighbors in same row
        left_neighbor = None
        right_neighbor = None

        left_index = card_index - 1
        right_index = card_index + 1

        if col > 0 and left_index >= 0:
            left_name = self._models[left_index][0]
            if left_name in self._cards:
                left_neighbor = self._cards[left_name]

        if col < self._columns - 1 and right_index < len(self._models):
            right_name = self._models[right_index][0]
            if right_name in self._cards:
                right_neighbor = self._cards[right_name]

        # Shift neighbors
        shift_amount = 20  # pixels
        if left_neighbor:
            left_neighbor.animate_shift(-shift_amount)
        if right_neighbor:
            right_neighbor.animate_shift(shift_amount)

    def _on_card_hover_ended(self, model_name: str):
        """Handle card hover end - reset neighbors (grid mode only)."""
        if self._layout_mode == "bars":
            return  # No neighbor shifting for bars

        card_index = self._get_card_index(model_name)
        if card_index < 0:
            return

        col = card_index % self._columns

        # Get neighbors in same row
        left_index = card_index - 1
        right_index = card_index + 1

        if col > 0 and left_index >= 0:
            left_name = self._models[left_index][0]
            if left_name in self._cards:
                self._cards[left_name].animate_shift(0)

        if col < self._columns - 1 and right_index < len(self._models):
            right_name = self._models[right_index][0]
            if right_name in self._cards:
                self._cards[right_name].animate_shift(0)

    def _get_card_index(self, model_name: str) -> int:
        """Get the index of a model in the models list."""
        for i, (name, _, _) in enumerate(self._models):
            if name == model_name:
                return i
        return -1

    def resizeEvent(self, event):
        """Handle resize - recalculate columns."""
        super().resizeEvent(event)

        # Debounce rebuild
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._on_resize_timeout)

        self._resize_timer.start(100)

    def _on_resize_timeout(self):
        """Handle resize debounce timeout."""
        # Skip if we just did a set_models rebuild
        if self._skip_resize_rebuild:
            logger.debug("[ModelGrid] _on_resize_timeout: skipping (skip flag set)")
            return

        old_columns = self._columns
        self._update_columns()
        logger.debug(f"[ModelGrid] _on_resize_timeout: old_columns={old_columns}, new_columns={self._columns}, models={len(self._models)}")
        if self._columns != old_columns:
            logger.debug(f"[ModelGrid] Columns changed, rebuilding grid")
            self._rebuild_grid()

    def _enable_resize_rebuild(self):
        """Re-enable resize rebuilds after set_models delay."""
        logger.debug(f"[ModelGrid] _enable_resize_rebuild: re-enabling resize rebuilds, cards={len(self._cards)}, grid_container.isVisible={self._grid_container.isVisible()}")
        self._skip_resize_rebuild = False

        # Log card state after a delay to see if visibility changes
        QTimer.singleShot(1000, self._debug_card_state)

    def _debug_card_state(self):
        """Debug: log card state after delay."""
        logger.debug(f"[ModelGrid] _debug_card_state (1s later): cards={len(self._cards)}, grid_container.isVisible={self._grid_container.isVisible()}")
        for name, card in self._cards.items():
            logger.debug(f"[ModelGrid] Card '{name}' (1s later): visible={card.isVisible()}, geometry={card.geometry()}")

    # =========================================================================
    # KEYBOARD NAVIGATION
    # =========================================================================

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation."""
        if not self._models:
            super().keyPressEvent(event)
            return

        key = event.key()

        # Initialize focus if not set
        if self._focused_index < 0:
            self._focused_index = 0
            self._update_focus()

        new_index = self._focused_index
        handled = True

        if self._layout_mode == "bars":
            # Simple up/down navigation for bars
            if key == Qt.Key_Down:
                if self._focused_index + 1 < len(self._models):
                    new_index = self._focused_index + 1
            elif key == Qt.Key_Up:
                if self._focused_index > 0:
                    new_index = self._focused_index - 1
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                self._activate_focused_card()
            elif key == Qt.Key_Space:
                self._toggle_favorite_focused_card()
            elif key == Qt.Key_Home:
                new_index = 0
            elif key == Qt.Key_End:
                new_index = len(self._models) - 1
            else:
                handled = False
        else:
            # Grid navigation
            if key == Qt.Key_Right:
                # Move right
                col = self._focused_index % self._columns
                if col < self._columns - 1 and self._focused_index + 1 < len(self._models):
                    new_index = self._focused_index + 1
            elif key == Qt.Key_Left:
                # Move left
                col = self._focused_index % self._columns
                if col > 0:
                    new_index = self._focused_index - 1
            elif key == Qt.Key_Down:
                # Move down
                next_row_index = self._focused_index + self._columns
                if next_row_index < len(self._models):
                    new_index = next_row_index
            elif key == Qt.Key_Up:
                # Move up
                prev_row_index = self._focused_index - self._columns
                if prev_row_index >= 0:
                    new_index = prev_row_index
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                # Select focused card
                self._activate_focused_card()
            elif key == Qt.Key_Space:
                # Toggle favorite on focused card
                self._toggle_favorite_focused_card()
            elif key == Qt.Key_Home:
                # Go to first card
                new_index = 0
            elif key == Qt.Key_End:
                # Go to last card
                new_index = len(self._models) - 1
            else:
                handled = False

        if new_index != self._focused_index:
            self._focused_index = new_index
            self._update_focus()

        if handled:
            event.accept()
        else:
            super().keyPressEvent(event)

    def _update_focus(self):
        """Update visual focus on cards/bars."""
        for i, (model_name, _, _) in enumerate(self._models):
            if model_name in self._cards:
                item = self._cards[model_name]
                # Only call set_focused if the item has this method (cards do, bars don't)
                if hasattr(item, 'set_focused'):
                    item.set_focused(i == self._focused_index)

        # Ensure focused card is visible in scroll area
        self._ensure_focused_visible()

    def _ensure_focused_visible(self):
        """Scroll to make the focused card visible."""
        if self._focused_index < 0 or self._focused_index >= len(self._models):
            return

        model_name = self._models[self._focused_index][0]
        if model_name not in self._cards:
            return

        card = self._cards[model_name]
        card.ensureVisible = True  # Hint for parent scroll area

    def _activate_focused_card(self):
        """Activate (select) the currently focused card."""
        if self._focused_index < 0 or self._focused_index >= len(self._models):
            return

        model_name = self._models[self._focused_index][0]
        if self._on_model_selected:
            self._on_model_selected(model_name)

    def _toggle_favorite_focused_card(self):
        """Toggle favorite on the currently focused card."""
        if self._focused_index < 0 or self._focused_index >= len(self._models):
            return

        model_name = self._models[self._focused_index][0]
        if self._on_favorite_toggled:
            self._on_favorite_toggled(model_name)

    def focus_first_card(self):
        """Focus the first card (called when grid receives focus)."""
        if self._models:
            self._focused_index = 0
            self._update_focus()

    def focusInEvent(self, event):
        """Handle focus received."""
        super().focusInEvent(event)
        if self._focused_index < 0 and self._models:
            self._focused_index = 0
            self._update_focus()

    def focusOutEvent(self, event):
        """Handle focus lost."""
        super().focusOutEvent(event)
        # Clear focus styling
        for model_name in self._cards:
            self._cards[model_name].set_focused(False)
