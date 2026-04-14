"""
Visual Variant Selector for ComfyUI multi-workflow models.

Replaces radio buttons with visual toggle cards that show:
- Variant name
- Brief description (from preset config or auto-generated)
- Clear selected/unselected state
"""

import logging
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy,
)

logger = logging.getLogger(__name__)

# Colors
VARIANT_BG = "#22252b"
VARIANT_BG_HOVER = "#2a2e36"
VARIANT_BG_SELECTED = "#1a2636"
VARIANT_BORDER = "#3c414b"
VARIANT_BORDER_HOVER = "#4a9eff"
VARIANT_BORDER_SELECTED = "#4a9eff"
TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#999999"
ACCENT = "#4a9eff"


class _VariantCard(QFrame):
    """Single variant toggle card."""

    clicked = Signal(str)

    def __init__(self, name: str, description: str = "", parent=None):
        super().__init__(parent)
        self._name = name
        self._is_selected = False
        self._is_hovered = False

        self.setObjectName("VariantCard")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(100)
        self.setMaximumWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        # Name
        self._name_label = QLabel(name)
        self._name_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._name_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        layout.addWidget(self._name_label)

        # Description (optional)
        if description:
            desc = QLabel(description)
            desc.setFont(QFont("Segoe UI", 9))
            desc.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            desc.setWordWrap(True)
            desc.setMaximumHeight(32)
            layout.addWidget(desc)

        self._apply_style()

    def _apply_style(self):
        if self._is_selected:
            bg, border, bw = VARIANT_BG_SELECTED, VARIANT_BORDER_SELECTED, 2
        elif self._is_hovered:
            bg, border, bw = VARIANT_BG_HOVER, VARIANT_BORDER_HOVER, 1
        else:
            bg, border, bw = VARIANT_BG, VARIANT_BORDER, 1

        # Selection indicator
        indicator = f"border-left: 3px solid {ACCENT};" if self._is_selected else ""

        self.setStyleSheet(
            f"QFrame#VariantCard {{"
            f"  background-color: {bg}; border: {bw}px solid {border};"
            f"  border-radius: 6px; {indicator}"
            f"}}"
        )

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._apply_style()

    @property
    def name(self) -> str:
        return self._name

    def enterEvent(self, event):
        self._is_hovered = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self._apply_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._name)
        super().mousePressEvent(event)


class VariantSelector(QWidget):
    """
    Visual variant selector for multi-workflow models.

    Displays workflow variants as horizontal toggle cards.
    Only one can be selected at a time.

    Signals:
        variant_selected(str): Emitted when a variant is clicked
    """

    variant_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: Dict[str, _VariantCard] = {}
        self._current: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Label
        self._label = QLabel("Variant:")
        self._label.setStyleSheet("color: #797e89; font-size: 12px; font-weight: bold;")
        layout.addWidget(self._label)

        # Cards row
        self._cards_layout = QHBoxLayout()
        self._cards_layout.setSpacing(8)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._cards_layout)

        self.setVisible(False)

    def set_variants(self, variants: Dict[str, Dict], selected: Optional[str] = None):
        """
        Set available variants and optionally select one.

        Args:
            variants: Dict of {variant_name: config_dict}
                      config_dict may have 'description' key
            selected: Name of initially selected variant (or None for first)
        """
        # Clear existing
        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        # Remove spacer items
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        if not variants or len(variants) < 2:
            self.setVisible(False)
            return

        # Create cards
        for name in sorted(variants.keys()):
            config = variants[name]
            desc = config.get("description", "")
            card = _VariantCard(name, desc)
            card.clicked.connect(self._on_card_clicked)
            self._cards_layout.addWidget(card)
            self._cards[name] = card

        self._cards_layout.addStretch()

        # Select
        if selected and selected in self._cards:
            self._select(selected)
        elif self._cards:
            self._select(sorted(variants.keys())[0])

        self.setVisible(True)

    def _on_card_clicked(self, name: str):
        if name == self._current:
            return
        self._select(name)
        self.variant_selected.emit(name)

    def _select(self, name: str):
        if self._current and self._current in self._cards:
            self._cards[self._current].set_selected(False)
        self._current = name
        if name in self._cards:
            self._cards[name].set_selected(True)

    @property
    def current_variant(self) -> Optional[str]:
        return self._current

    def clear(self):
        """Clear all variants and hide."""
        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._current = None
        self.setVisible(False)
