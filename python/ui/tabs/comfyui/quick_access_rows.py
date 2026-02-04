"""
Quick Access Rows for Model Picker Overlay.

Horizontal scrollable rows for:
- Favorites: User's favorite models (starred)
- Recently Used: Models sorted by last use time
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame
)

logger = logging.getLogger(__name__)

# Styling
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#888888"
SECTION_HEADER = "#aaaaaa"

# Card dimensions (smaller for quick access)
QUICK_CARD_WIDTH = 160
QUICK_CARD_HEIGHT = 200


class QuickAccessCard(QFrame):
    """
    Smaller card for quick access rows.

    Similar to OverlayModelCard but more compact.
    """

    clicked = Signal(str)  # model_name
    favorite_toggled = Signal(str)  # model_name
    context_menu_requested = Signal(str, object)  # model_name, global_pos

    def __init__(
        self,
        model_name: str,
        preset_config: Dict[str, Any],
        rating_data: Dict[str, Any],
        username: str,
        show_favorite_button: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self._model_name = model_name
        self._preset_config = preset_config
        self._rating_data = rating_data
        self._username = username
        self._show_favorite = show_favorite_button

        self.setObjectName("QuickAccessCard")
        self.setFixedSize(QUICK_CARD_WIDTH, QUICK_CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        """Set up the card UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Thumbnail placeholder
        thumb_frame = QFrame()
        thumb_frame.setFixedHeight(100)
        thumb_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border-radius: 4px;
            }
        """)

        thumb_layout = QVBoxLayout(thumb_frame)
        thumb_layout.setContentsMargins(0, 0, 0, 0)

        # Check for thumbnail
        thumb_path = self._rating_data.get("thumbnail_path")
        if thumb_path:
            from PySide6.QtGui import QPixmap
            import os
            if os.path.exists(thumb_path):
                thumb_label = QLabel()
                pixmap = QPixmap(thumb_path).scaled(
                    QUICK_CARD_WIDTH - 12, 100,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                thumb_label.setPixmap(pixmap)
                thumb_label.setAlignment(Qt.AlignCenter)
                thumb_layout.addWidget(thumb_label)
            else:
                no_thumb = QLabel("No Preview")
                no_thumb.setStyleSheet("color: #666; font-size: 10px;")
                no_thumb.setAlignment(Qt.AlignCenter)
                thumb_layout.addWidget(no_thumb)
        else:
            no_thumb = QLabel("No Preview")
            no_thumb.setStyleSheet("color: #666; font-size: 10px;")
            no_thumb.setAlignment(Qt.AlignCenter)
            thumb_layout.addWidget(no_thumb)

        layout.addWidget(thumb_frame)

        # Model name
        display_name = self._get_display_name()
        name_label = QLabel(display_name)
        name_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: 11px;
            font-weight: bold;
        """)
        name_label.setWordWrap(False)
        # Elide long names
        metrics = name_label.fontMetrics()
        elided = metrics.elidedText(display_name, Qt.ElideRight, QUICK_CARD_WIDTH - 16)
        name_label.setText(elided)
        name_label.setToolTip(self._model_name)
        layout.addWidget(name_label)

        # Rating stars
        from .star_rating import CompactStarRating
        average = self._rating_data.get("average", 0.0)
        rating = CompactStarRating(rating=average, show_value=True, size=10)
        layout.addWidget(rating)

        # Favorite button row
        if self._show_favorite:
            btn_row = QHBoxLayout()
            btn_row.setContentsMargins(0, 4, 0, 0)
            btn_row.setSpacing(4)

            is_favorite = self._rating_data.get("is_favorite", {}).get(self._username, False)
            fav_btn = QPushButton("★" if is_favorite else "☆")
            fav_btn.setFixedSize(24, 24)
            fav_btn.setCursor(Qt.PointingHandCursor)
            fav_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {"#fbbf24" if is_favorite else "#666"};
                    border: none;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    color: #fbbf24;
                }}
            """)
            fav_btn.clicked.connect(self._on_favorite_clicked)
            btn_row.addWidget(fav_btn)
            btn_row.addStretch()

            layout.addLayout(btn_row)

        # Prevent child QLabels from intercepting context menu events
        for child in self.findChildren(QLabel):
            child.setContextMenuPolicy(Qt.NoContextMenu)

    def _get_display_name(self) -> str:
        """Get display name (last part of full path)."""
        if '/' in self._model_name:
            return self._model_name.rsplit('/', 1)[-1]
        if '\\' in self._model_name:
            return self._model_name.rsplit('\\', 1)[-1]
        return self._model_name

    def _apply_style(self):
        """Apply card style."""
        self.setStyleSheet("""
            QFrame#QuickAccessCard {
                background-color: #2a2a2a;
                border: 1px solid #3c414b;
                border-radius: 6px;
            }
            QFrame#QuickAccessCard:hover {
                border-color: #4a9eff;
                background-color: #323232;
            }
        """)

    def _on_favorite_clicked(self):
        """Handle favorite button click."""
        self.favorite_toggled.emit(self._model_name)

    def contextMenuEvent(self, event):
        """Handle right-click for context menu."""
        self.context_menu_requested.emit(self._model_name, event.globalPos())

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to select."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._model_name)


class QuickAccessRow(QWidget):
    """
    Horizontal scrollable row of quick access cards.

    Shows section title, scroll buttons, and cards in a horizontal layout.
    """

    def __init__(
        self,
        title: str,
        icon: str = "",
        on_card_selected: Optional[Callable[[str], None]] = None,
        on_favorite_toggled: Optional[Callable[[str], None]] = None,
        on_context_menu: Optional[Callable] = None,
        parent=None
    ):
        """
        Initialize quick access row.

        Args:
            title: Section title (e.g., "Favorites", "Recently Used")
            icon: Icon to show before title (e.g., "★", "⏱")
            on_card_selected: Callback when card is double-clicked
            on_favorite_toggled: Callback when favorite is toggled
            on_context_menu: Callback for right-click context menu
            parent: Parent widget
        """
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._on_card_selected = on_card_selected
        self._on_favorite_toggled = on_favorite_toggled
        self._on_context_menu = on_context_menu

        self._cards: List[QuickAccessCard] = []
        self._models: List[Tuple[str, Dict, Dict]] = []
        self._username = ""

        self._setup_ui()

    def _setup_ui(self):
        """Set up the row UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # Title with icon
        title_text = f"{self._icon} {self._title}" if self._icon else self._title
        self._title_label = QLabel(title_text)
        self._title_label.setStyleSheet(f"""
            color: {SECTION_HEADER};
            font-size: 13px;
            font-weight: bold;
        """)
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        # Scroll buttons
        self._scroll_left_btn = QPushButton("<")
        self._scroll_left_btn.setFixedSize(28, 28)
        self._scroll_left_btn.setCursor(Qt.PointingHandCursor)
        self._scroll_left_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2d32;
                color: #888;
                border: none;
                border-radius: 14px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3c414b;
                color: #fff;
            }
        """)
        self._scroll_left_btn.clicked.connect(self._scroll_left)
        header_layout.addWidget(self._scroll_left_btn)

        self._scroll_right_btn = QPushButton(">")
        self._scroll_right_btn.setFixedSize(28, 28)
        self._scroll_right_btn.setCursor(Qt.PointingHandCursor)
        self._scroll_right_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2d32;
                color: #888;
                border: none;
                border-radius: 14px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3c414b;
                color: #fff;
            }
        """)
        self._scroll_right_btn.clicked.connect(self._scroll_right)
        header_layout.addWidget(self._scroll_right_btn)

        layout.addLayout(header_layout)

        # Scroll area for cards
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFixedHeight(QUICK_CARD_HEIGHT + 16)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)

        self._cards_container = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(12)
        self._cards_layout.addStretch()

        self._scroll_area.setWidget(self._cards_container)
        layout.addWidget(self._scroll_area)

        # Empty state widget
        self._empty_widget = QFrame()
        self._empty_widget.setStyleSheet("""
            QFrame {
                background-color: #1a1d21;
                border: 1px dashed #3c414b;
                border-radius: 8px;
            }
        """)
        self._empty_widget.setFixedHeight(100)

        empty_layout = QVBoxLayout(self._empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(8)

        # Icon
        if self._icon == "★":
            empty_icon = QLabel("☆")
            hint_text = "Click the ★ on a model card to add favorites"
        else:
            empty_icon = QLabel("⏱")
            hint_text = "Models you use will appear here"

        empty_icon.setStyleSheet("color: #4a4a4a; font-size: 24px;")
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)

        self._empty_label = QLabel(f"No {self._title.lower()} yet")
        self._empty_label.setStyleSheet("color: #666; font-size: 12px;")
        self._empty_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self._empty_label)

        hint_label = QLabel(hint_text)
        hint_label.setStyleSheet("color: #4a4a4a; font-size: 10px;")
        hint_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(hint_label)

        self._empty_widget.hide()
        layout.addWidget(self._empty_widget)

        # Scroll animation
        self._scroll_anim = QPropertyAnimation(
            self._scroll_area.horizontalScrollBar(), b"value"
        )
        self._scroll_anim.setDuration(200)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)

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
        self._models = models
        self._username = username
        self._rebuild_cards()

    def _rebuild_cards(self):
        """Rebuild the cards from current models."""
        # Clear existing cards
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        # Clear layout
        while self._cards_layout.count() > 1:  # Keep the stretch
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Check for empty state
        if not self._models:
            self._scroll_area.hide()
            self._empty_widget.show()
            self._scroll_left_btn.setEnabled(False)
            self._scroll_right_btn.setEnabled(False)
            return

        self._empty_widget.hide()
        self._scroll_area.show()
        self._scroll_left_btn.setEnabled(True)
        self._scroll_right_btn.setEnabled(True)

        # Create cards (insert before the stretch)
        for model_name, preset_config, rating_data in self._models[:10]:  # Max 10
            card = QuickAccessCard(
                model_name=model_name,
                preset_config=preset_config,
                rating_data=rating_data,
                username=self._username,
                show_favorite_button=True
            )

            card.clicked.connect(self._on_card_clicked)
            card.favorite_toggled.connect(self._on_card_favorite_toggled)
            card.context_menu_requested.connect(self._on_card_context_menu)

            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
            self._cards.append(card)

    def _on_card_clicked(self, model_name: str):
        """Handle card click."""
        if self._on_card_selected:
            self._on_card_selected(model_name)

    def _on_card_favorite_toggled(self, model_name: str):
        """Handle favorite toggle."""
        if self._on_favorite_toggled:
            self._on_favorite_toggled(model_name)

    def _on_card_context_menu(self, model_name: str, pos):
        """Handle card context menu request."""
        if self._on_context_menu:
            self._on_context_menu(model_name, pos)

    def _scroll_left(self):
        """Scroll the row left."""
        scroll_bar = self._scroll_area.horizontalScrollBar()
        target = max(0, scroll_bar.value() - QUICK_CARD_WIDTH * 2)

        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(scroll_bar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()

    def _scroll_right(self):
        """Scroll the row right."""
        scroll_bar = self._scroll_area.horizontalScrollBar()
        target = min(scroll_bar.maximum(), scroll_bar.value() + QUICK_CARD_WIDTH * 2)

        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(scroll_bar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()
