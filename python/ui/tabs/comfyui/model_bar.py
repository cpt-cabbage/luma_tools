"""
Horizontal Model Bar Widget for ComfyUI Model Picker Overlay.

A Netflix/Spotify-style horizontal bar displaying model information:
- Small thumbnail on the left
- Model name (bold) and description
- Tags as chips
- Rating and usage stats on the right
- Favorite button
"""

import logging
import os
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QPixmap, QFont, QCursor
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
)

from core.design_tokens import set_role

logger = logging.getLogger(__name__)

# Bar dimensions
BAR_HEIGHT = 90
BAR_MIN_WIDTH = 600
THUMB_WIDTH = 100
THUMB_HEIGHT = 75

# Colors


class ModelBar(QFrame):
    """
    Horizontal bar widget for a model in the picker overlay.

    Displays:
    - Thumbnail image (small, left side)
    - Model name (bold)
    - Description text
    - Tags as chips
    - Star rating and usage count (right side)
    - Favorite button (right side)

    Signals:
        activated(str): Double-click to load model
        favorite_toggled(str): Favorite button clicked
        context_menu_requested(str, QPoint): Right-click
    """

    activated = Signal(str)
    favorite_toggled = Signal(str)
    context_menu_requested = Signal(str, QPoint)

    def __init__(
        self,
        model_name: str,
        preset_config: Dict[str, Any],
        rating_data: Dict[str, Any],
        username: str,
        parent=None
    ):
        super().__init__(parent)
        self._model_name = model_name
        self._preset_config = preset_config
        self._rating_data = rating_data
        self._username = username
        self._is_selected = False
        self._is_hovered = False
        self._is_focused = False

        self.setObjectName("ModelBar")
        self.setMinimumHeight(BAR_HEIGHT)
        self.setMinimumWidth(BAR_MIN_WIDTH)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the bar UI."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 12, 8)
        main_layout.setSpacing(12)

        # Thumbnail on the left
        self._thumbnail = QLabel()
        self._thumbnail.setFixedSize(THUMB_WIDTH, THUMB_HEIGHT)
        self._thumbnail.setAlignment(Qt.AlignCenter)
        self._thumbnail.setProperty("variant", "thumb")
        thumb_path = self._rating_data.get("thumbnail_path")
        if thumb_path and os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    THUMB_WIDTH, THUMB_HEIGHT,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._thumbnail.setPixmap(scaled)
            else:
                self._thumbnail.setText("No\nPreview")
        else:
            self._thumbnail.setText("No\nPreview")
        main_layout.addWidget(self._thumbnail)

        # Content area (name, description, tags)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)

        # Model name
        display_name = self._get_display_name()
        self._name_label = QLabel(display_name)
        self._name_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self._name_label.setWordWrap(False)
        self._name_label.setToolTip(self._model_name)
        content_layout.addWidget(self._name_label)

        # Description text
        description = self._get_description()
        self._desc_label = QLabel(description if description else "No description available")
        self._desc_label.setFont(QFont("Segoe UI", 9))
        self._desc_label.setProperty("textRole", "help")
        self._desc_label.setWordWrap(True)
        self._desc_label.setMaximumHeight(28)  # 2 lines max
        content_layout.addWidget(self._desc_label)

        # Tags row
        tags_row = QHBoxLayout()
        tags_row.setSpacing(4)
        tags_row.setContentsMargins(0, 2, 0, 0)

        tags = self._rating_data.get("tags", [])
        if tags:
            for tag in tags[:4]:  # Show max 4 tags
                tag_chip = QLabel(tag)
                tag_chip.setProperty("variant", "count")
                tags_row.addWidget(tag_chip)

            if len(tags) > 4:
                more_label = QLabel(f"+{len(tags) - 4} more")
                more_label.setProperty("textRole", "help")
                tags_row.addWidget(more_label)

        tags_row.addStretch()
        content_layout.addLayout(tags_row)

        main_layout.addWidget(content_widget, 1)

        # Stats area on the right (rating, usage, favorite)
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(6)
        stats_layout.setAlignment(Qt.AlignTop | Qt.AlignRight)

        # Rating row
        rating_row = QHBoxLayout()
        rating_row.setSpacing(8)
        rating_row.setAlignment(Qt.AlignRight)

        from .star_rating import CompactStarRating
        average = self._rating_data.get("average", 0.0)
        user_rating = self._rating_data.get("ratings", {}).get(self._username)
        self._rating_widget = CompactStarRating(
            rating=average,
            show_value=True,
            size=14,
            interactive=True,
            user_rating=user_rating
        )
        self._rating_widget.rating_changed.connect(self._on_rating_changed)
        rating_row.addWidget(self._rating_widget)

        # Favorite button
        is_favorite = self._rating_data.get("is_favorite", {}).get(self._username, False)
        self._fav_btn = QPushButton("★" if is_favorite else "☆")
        self._fav_btn.setFixedSize(24, 24)
        self._fav_btn.setCursor(Qt.PointingHandCursor)
        set_role(self._fav_btn, role="link",
                 state="warning" if is_favorite else None)
        self._fav_btn.clicked.connect(self._on_favorite_clicked)
        rating_row.addWidget(self._fav_btn)

        stats_layout.addLayout(rating_row)

        # Usage count
        total_uses = self._rating_data.get("total_uses", 0)
        self._usage_label = QLabel(f"{total_uses} uses")
        self._usage_label.setProperty("textRole", "help")
        self._usage_label.setAlignment(Qt.AlignRight)
        stats_layout.addWidget(self._usage_label)

        main_layout.addWidget(stats_widget)

        # Prevent child QLabels from intercepting context menu events
        for child in self.findChildren(QLabel):
            child.setContextMenuPolicy(Qt.NoContextMenu)

        self._apply_style()

    def _get_display_name(self) -> str:
        """Get display name (last part of full path)."""
        if '/' in self._model_name:
            return self._model_name.rsplit('/', 1)[-1]
        if '\\' in self._model_name:
            return self._model_name.rsplit('\\', 1)[-1]
        return self._model_name

    def _get_description(self) -> str:
        """Get description from preset config (shown in model browser)."""
        return self._preset_config.get("description", "").strip()

    def _apply_style(self):
        """Apply current style based on state.

        Hover is a QSS pseudo-state now, so only selection and keyboard focus
        have to be pushed through as properties.
        """
        if self._is_selected:
            state = "selected"
        elif self._is_focused:
            state = "focused"
        else:
            state = None
        set_role(self, variant="card", state=state)

    def set_selected(self, selected: bool):
        """Set selection state."""
        self._is_selected = selected
        self._apply_style()

    def set_focused(self, focused: bool):
        """Set keyboard focus state."""
        self._is_focused = focused
        self._apply_style()

    def _on_favorite_clicked(self):
        """Handle favorite button click."""
        self.favorite_toggled.emit(self._model_name)

    def _on_rating_changed(self, rating: int):
        """Handle rating change."""
        from comfyui.ratings import rate_model, get_model_rating

        # Save rating
        if rate_model(self._model_name, self._username, rating):
            # Update display with new average
            updated_data = get_model_rating(self._model_name)
            new_average = updated_data.get("average", 0.0)
            self._rating_widget.set_rating(new_average)
            logger.info(f"[ModelBar] Rated '{self._model_name}': {rating}/5 (new avg: {new_average:.1f})")

    # Event handlers
    def enterEvent(self, event):
        """Handle mouse enter - show hover state."""
        self._is_hovered = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leave - remove hover state."""
        self._is_hovered = False
        self._apply_style()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to select model."""
        if event.button() == Qt.LeftButton:
            # Flash the border for visual feedback
            self._is_selected = True
            self._apply_style()

            # Emit signal after brief delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, lambda: self.activated.emit(self._model_name))

        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Handle right-click for context menu."""
        self.context_menu_requested.emit(self._model_name, event.globalPos())

    @property
    def model_name(self) -> str:
        return self._model_name
