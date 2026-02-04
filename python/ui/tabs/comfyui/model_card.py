"""
Model Card Widget for ComfyUI Model Picker.

Visual card representation of a workflow model/preset with:
- Thumbnail image (auto-generated or manual)
- Model name and description
- Star rating display
- Usage count
- Hover animations (border, shadow, scale)
- Double-click to select
"""

import logging
import os
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal, QPoint, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QColor, QPainter, QPixmap, QFont, QCursor
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect,
    QSizePolicy, QPushButton, QWidget
)

from .star_rating import CompactStarRating

logger = logging.getLogger(__name__)

# Card dimensions
CARD_WIDTH = 200
CARD_HEIGHT = 180
THUMB_HEIGHT = 120

# Colors
CARD_BG = "#2a2a2a"
CARD_BG_HOVER = "#323232"
CARD_BORDER = "#3c414b"
CARD_BORDER_HOVER = "#4a9eff"
CARD_BORDER_SELECTED = "#10b981"
TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#888888"


class ThumbnailWidget(QLabel):
    """Thumbnail display with placeholder support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._placeholder_text = "No Preview"

        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(CARD_WIDTH - 10, THUMB_HEIGHT)
        self.setMaximumHeight(THUMB_HEIGHT)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: #1e1e1e;
                border-radius: 4px;
                color: #666;
                font-size: 11px;
            }}
        """)

    def set_thumbnail(self, path: Optional[str]) -> None:
        """Set thumbnail from file path."""
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                # Scale to fit while maintaining aspect ratio
                scaled = pixmap.scaled(
                    self.width(), THUMB_HEIGHT,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._pixmap = scaled
                self.setPixmap(scaled)
                return

        # Show placeholder
        self._pixmap = None
        self.setText(self._placeholder_text)

    def set_placeholder_text(self, text: str) -> None:
        """Set placeholder text for when no thumbnail is available."""
        self._placeholder_text = text
        if self._pixmap is None:
            self.setText(text)


class ModelCard(QFrame):
    """
    Visual card widget for a model in the picker grid.

    Displays:
    - Thumbnail image
    - Model name (bold, truncated)
    - Star rating with count
    - Usage count

    Signals:
        selected(str): Single-click highlight
        activated(str): Double-click to load model
        context_menu(str, QPoint): Right-click menu request
    """

    selected = Signal(str)
    activated = Signal(str)
    context_menu = Signal(str, QPoint)

    def __init__(
        self,
        model_name: str,
        preset_config: Dict[str, Any],
        rating_data: Dict[str, Any],
        parent=None
    ):
        """
        Initialize model card.

        Args:
            model_name: Full model/preset name (e.g., "folder/Flux Upscale")
            preset_config: Preset configuration dict
            rating_data: Rating data dict from ratings module
            parent: Parent widget
        """
        super().__init__(parent)
        self._model_name = model_name
        self._preset_config = preset_config
        self._rating_data = rating_data
        self._is_selected = False
        self._is_hovered = False
        self._border_color = QColor(CARD_BORDER)

        self.setObjectName("ModelCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)

        self._setup_ui()
        self._setup_effects()
        self._update_data()

    def _setup_ui(self):
        """Set up the card UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # Thumbnail
        self._thumbnail = ThumbnailWidget()
        layout.addWidget(self._thumbnail)

        # Model name (display name, not full path)
        display_name = self._get_display_name()
        self._name_label = QLabel(display_name)
        self._name_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._name_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        self._name_label.setWordWrap(False)
        self._name_label.setMaximumWidth(CARD_WIDTH - 10)
        # Elide long names
        metrics = self._name_label.fontMetrics()
        elided = metrics.elidedText(display_name, Qt.ElideRight, CARD_WIDTH - 20)
        self._name_label.setText(elided)
        self._name_label.setToolTip(self._model_name)
        layout.addWidget(self._name_label)

        # Rating and usage row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)

        self._rating_widget = CompactStarRating(rating=0.0, show_value=True, size=12)
        stats_row.addWidget(self._rating_widget)

        stats_row.addStretch()

        self._usage_label = QLabel("0 uses")
        self._usage_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
        stats_row.addWidget(self._usage_label)

        layout.addLayout(stats_row)

        # Prevent child QLabels from intercepting context menu events
        for child in self.findChildren(QLabel):
            child.setContextMenuPolicy(Qt.NoContextMenu)

        self._apply_style()

    def _setup_effects(self):
        """Set up visual effects (shadow)."""
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(self._shadow)

        # Animation for border color
        self._border_animation = QPropertyAnimation(self, b"border_color")
        self._border_animation.setDuration(150)
        self._border_animation.setEasingCurve(QEasingCurve.OutCubic)

        # Animation for shadow
        self._shadow_animation = QPropertyAnimation(self._shadow, b"blurRadius")
        self._shadow_animation.setDuration(150)
        self._shadow_animation.setEasingCurve(QEasingCurve.OutCubic)

    def _get_display_name(self) -> str:
        """Get display name (last part of full path)."""
        if '/' in self._model_name:
            return self._model_name.rsplit('/', 1)[-1]
        if '\\' in self._model_name:
            return self._model_name.rsplit('\\', 1)[-1]
        return self._model_name

    def _apply_style(self):
        """Apply the current style to the card."""
        border_color = self._border_color.name()
        bg_color = CARD_BG_HOVER if self._is_hovered else CARD_BG

        if self._is_selected:
            border_color = CARD_BORDER_SELECTED
            border_width = 2
        else:
            border_width = 1

        self.setStyleSheet(f"""
            QFrame#ModelCard {{
                background-color: {bg_color};
                border: {border_width}px solid {border_color};
                border-radius: 6px;
            }}
        """)

    def _update_data(self):
        """Update displayed data from rating_data."""
        # Thumbnail
        thumb_path = self._rating_data.get("thumbnail_path")
        self._thumbnail.set_thumbnail(thumb_path)

        # Rating
        average = self._rating_data.get("average", 0.0)
        self._rating_widget.set_rating(average)

        # Usage count
        total_uses = self._rating_data.get("total_uses", 0)
        self._usage_label.setText(f"{total_uses} uses")

    def update_rating_data(self, rating_data: Dict[str, Any]) -> None:
        """Update the card with new rating data."""
        self._rating_data = rating_data
        self._update_data()

    def set_selected(self, selected: bool) -> None:
        """Set the selection state."""
        self._is_selected = selected
        self._apply_style()

    def is_selected(self) -> bool:
        """Check if card is selected."""
        return self._is_selected

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self._model_name

    # Border color property for animation
    def get_border_color(self) -> QColor:
        return self._border_color

    def set_border_color(self, color: QColor) -> None:
        self._border_color = color
        self._apply_style()

    border_color = Property(QColor, get_border_color, set_border_color)

    # Event handlers
    def enterEvent(self, event):
        """Handle mouse enter - animate hover effects."""
        self._is_hovered = True

        # Animate border color
        self._border_animation.stop()
        self._border_animation.setStartValue(self._border_color)
        self._border_animation.setEndValue(QColor(CARD_BORDER_HOVER))
        self._border_animation.start()

        # Animate shadow
        self._shadow_animation.stop()
        self._shadow_animation.setStartValue(self._shadow.blurRadius())
        self._shadow_animation.setEndValue(15)
        self._shadow_animation.start()

        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leave - animate back to normal."""
        self._is_hovered = False

        # Animate border color back
        self._border_animation.stop()
        self._border_animation.setStartValue(self._border_color)
        self._border_animation.setEndValue(QColor(CARD_BORDER))
        self._border_animation.start()

        # Animate shadow back
        self._shadow_animation.stop()
        self._shadow_animation.setStartValue(self._shadow.blurRadius())
        self._shadow_animation.setEndValue(0)
        self._shadow_animation.start()

        self._apply_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press - emit selected signal."""
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._model_name)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click - emit activated signal."""
        if event.button() == Qt.LeftButton:
            self.activated.emit(self._model_name)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Handle right-click - emit context menu signal."""
        self.context_menu.emit(self._model_name, event.globalPos())


class MultiWorkflowCard(ModelCard):
    """
    Card for multi-workflow models.

    Shows expand indicator and can display nested workflow cards.
    """

    expanded = Signal(str, bool)  # model_name, is_expanded

    def __init__(
        self,
        model_name: str,
        preset_config: Dict[str, Any],
        rating_data: Dict[str, Any],
        parent=None
    ):
        super().__init__(model_name, preset_config, rating_data, parent)
        self._is_expanded = False

        # Add expand indicator
        self._add_expand_indicator()

    def _add_expand_indicator(self):
        """Add visual indicator that this card can expand."""
        # Add a small indicator to the thumbnail
        self._thumbnail.set_placeholder_text("Multi-Workflow\n▼")

    def toggle_expanded(self) -> None:
        """Toggle expanded state."""
        self._is_expanded = not self._is_expanded
        self.expanded.emit(self._model_name, self._is_expanded)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click - toggle expanded instead of activating."""
        if event.button() == Qt.LeftButton:
            # For multi-workflow, double-click expands/collapses
            # Single workflow selection happens in expanded view
            self.toggle_expanded()
        # Don't call super - we override the behavior


# =============================================================================
# Netflix-Style Model Card for Overlay
# =============================================================================

# Larger dimensions for overlay
OVERLAY_CARD_WIDTH = 200
OVERLAY_CARD_HEIGHT = 260
OVERLAY_THUMB_HEIGHT = 150

# Animation constants
HOVER_SCALE = 1.10  # 10% larger on hover (less aggressive than 15%)
HOVER_DURATION = 150  # ms
NEIGHBOR_SHIFT = 20  # px neighbors shift


class OverlayModelCard(QFrame):
    """
    Netflix-style model card with scale animation and neighbor awareness.

    Used in the full-screen overlay picker.

    Signals:
        activated(str): Double-click to load model
        favorite_toggled(str): Favorite button clicked
        context_menu_requested(str, QPoint): Right-click
        hover_started(str): Mouse entered card
        hover_ended(str): Mouse left card
    """

    activated = Signal(str)
    favorite_toggled = Signal(str)
    context_menu_requested = Signal(str, QPoint)
    hover_started = Signal(str)
    hover_ended = Signal(str)

    def __init__(
        self,
        model_name: str,
        preset_config: Dict[str, Any],
        rating_data: Dict[str, Any],
        username: str,
        grid_parent=None,
        parent=None
    ):
        super().__init__(parent)
        self._model_name = model_name
        self._preset_config = preset_config
        self._rating_data = rating_data
        self._username = username
        self._grid_parent = grid_parent
        self._is_selected = False
        self._is_hovered = False
        self._is_focused = False  # Keyboard focus
        self._shift_offset = 0
        self._base_geometry = None

        self.setObjectName("OverlayModelCard")
        self.setFixedSize(OVERLAY_CARD_WIDTH, OVERLAY_CARD_HEIGHT)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)

        # Track destruction for debugging
        self.destroyed.connect(lambda: logger.debug(f"[ModelCard] Card DESTROYED: {model_name}"))

        self._setup_ui()
        self._setup_animations()

    def _setup_ui(self):
        """Set up the card UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Thumbnail - account for border (2px total)
        thumb_width = OVERLAY_CARD_WIDTH - 2
        thumb_height = OVERLAY_THUMB_HEIGHT
        self._thumbnail = QLabel()
        self._thumbnail.setFixedHeight(thumb_height)
        self._thumbnail.setAlignment(Qt.AlignCenter)
        self._thumbnail.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                color: #555;
                font-size: 11px;
            }
        """)
        thumb_path = self._rating_data.get("thumbnail_path")
        if thumb_path and os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    thumb_width, thumb_height,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation
                )
                # Center crop if needed
                if scaled.width() > thumb_width or scaled.height() > thumb_height:
                    x = (scaled.width() - thumb_width) // 2
                    y = (scaled.height() - thumb_height) // 2
                    scaled = scaled.copy(x, y, thumb_width, thumb_height)
                self._thumbnail.setPixmap(scaled)
            else:
                self._thumbnail.setText("No Preview")
        else:
            self._thumbnail.setText("No Preview")
        layout.addWidget(self._thumbnail)

        # Content area with padding
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 6, 8, 8)
        content_layout.setSpacing(2)

        # Model name
        display_name = self._get_display_name()
        self._name_label = QLabel(display_name)
        self._name_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._name_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        metrics = self._name_label.fontMetrics()
        elided = metrics.elidedText(display_name, Qt.ElideRight, OVERLAY_CARD_WIDTH - 20)
        self._name_label.setText(elided)
        self._name_label.setToolTip(self._model_name)
        content_layout.addWidget(self._name_label)

        # Rating row with favorite button
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(4)

        from .star_rating import CompactStarRating
        average = self._rating_data.get("average", 0.0)
        self._rating_widget = CompactStarRating(rating=average, show_value=False, size=12)
        stats_row.addWidget(self._rating_widget)

        stats_row.addStretch()

        # Favorite button
        is_favorite = self._rating_data.get("is_favorite", {}).get(self._username, False)
        self._fav_btn = QPushButton("★" if is_favorite else "☆")
        self._fav_btn.setFixedSize(20, 20)
        self._fav_btn.setCursor(Qt.PointingHandCursor)
        self._fav_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {"#fbbf24" if is_favorite else "#555"};
                border: none;
                font-size: 14px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: #fbbf24;
            }}
        """)
        self._fav_btn.clicked.connect(self._on_favorite_clicked)
        stats_row.addWidget(self._fav_btn)

        content_layout.addLayout(stats_row)

        # Usage count
        total_uses = self._rating_data.get("total_uses", 0)
        self._usage_label = QLabel(f"{total_uses} uses")
        self._usage_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px;")
        content_layout.addWidget(self._usage_label)

        layout.addWidget(content)

        # Prevent child QLabels from intercepting context menu events
        # so right-click propagates to the card's contextMenuEvent
        for child in self.findChildren(QLabel):
            child.setContextMenuPolicy(Qt.NoContextMenu)

        self._apply_style()

    def _setup_animations(self):
        """Set up hover animations."""
        # NOTE: QGraphicsDropShadowEffect removed - causes QPainter conflicts
        # when multiple cards are painted simultaneously, making cards invisible.
        # Using CSS border styling for hover feedback instead.

        # Shift animation (for neighbor shifting)
        self._shift_anim = QPropertyAnimation(self, b"geometry")
        self._shift_anim.setDuration(HOVER_DURATION)
        self._shift_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_display_name(self) -> str:
        """Get display name (last part of full path)."""
        if '/' in self._model_name:
            return self._model_name.rsplit('/', 1)[-1]
        if '\\' in self._model_name:
            return self._model_name.rsplit('\\', 1)[-1]
        return self._model_name

    def _apply_style(self):
        """Apply current style based on state."""
        if self._is_selected:
            border_color = CARD_BORDER_SELECTED
            border_width = 2
            bg = CARD_BG_HOVER
        elif self._is_focused:
            border_color = CARD_BORDER_HOVER
            border_width = 2
            bg = CARD_BG_HOVER
        elif self._is_hovered:
            border_color = CARD_BORDER_HOVER
            border_width = 1
            bg = CARD_BG_HOVER
        else:
            border_color = CARD_BORDER
            border_width = 1
            bg = CARD_BG

        self.setStyleSheet(f"""
            QFrame#OverlayModelCard {{
                background-color: {bg};
                border: {border_width}px solid {border_color};
                border-radius: 8px;
            }}
        """)

    def set_selected(self, selected: bool):
        """Set selection state."""
        self._is_selected = selected
        self._apply_style()

    def set_focused(self, focused: bool):
        """Set keyboard focus state."""
        self._is_focused = focused
        self._apply_style()

    def animate_shift(self, offset: int):
        """Animate horizontal shift (called by grid for neighbor awareness)."""
        if not self._base_geometry:
            self._base_geometry = self.geometry()

        target = self._base_geometry.translated(offset, 0)

        self._shift_anim.stop()
        self._shift_anim.setStartValue(self.geometry())
        self._shift_anim.setEndValue(target)
        self._shift_anim.start()

        self._shift_offset = offset

    def _on_favorite_clicked(self):
        """Handle favorite button click."""
        self.favorite_toggled.emit(self._model_name)

    # Event handlers
    def enterEvent(self, event):
        """Handle mouse enter - start hover animations."""
        self._is_hovered = True
        self._base_geometry = self.geometry()

        # Apply hover style
        self._apply_style()

        # Raise above siblings
        self.raise_()

        # Notify grid for neighbor shifting
        self.hover_started.emit(self._model_name)

        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leave - end hover animations."""
        self._is_hovered = False

        # Apply normal style
        self._apply_style()

        # Notify grid
        self.hover_ended.emit(self._model_name)

        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to select model."""
        if event.button() == Qt.LeftButton:
            # Show selection feedback animation then emit signal
            self._animate_selection()
        super().mouseDoubleClickEvent(event)

    def _animate_selection(self):
        """Animate selection feedback (brief pulse)."""
        from PySide6.QtCore import QTimer

        # Flash the border to indicate selection
        self._is_selected = True
        self._apply_style()

        # Emit signal after brief delay for visual feedback
        def emit_after_pulse():
            self.activated.emit(self._model_name)

        QTimer.singleShot(100, emit_after_pulse)

    def contextMenuEvent(self, event):
        """Handle right-click for context menu."""
        self.context_menu_requested.emit(self._model_name, event.globalPos())

    @property
    def model_name(self) -> str:
        return self._model_name
