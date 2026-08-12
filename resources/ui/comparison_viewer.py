"""
Comparison viewer widget for comparing multiple images.

Provides three comparison modes:
- Slider: Vertical split with draggable divider
- Onion Skin: Overlay with opacity slider
- 2x2 Grid: Four images with synchronized zoom/pan
"""

import os
import logging
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush, QWheelEvent, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QStackedWidget, QSizePolicy, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QFrame
)

logger = logging.getLogger(__name__)


class SliderComparisonWidget(QWidget):
    """
    Slider comparison mode - vertical split with draggable divider.

    Left image on left, right image on right, drag to reveal more of each.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._left_pixmap: Optional[QPixmap] = None
        self._right_pixmap: Optional[QPixmap] = None
        self._slider_pos = 0.5  # 0.0 = all right, 1.0 = all left
        self._is_dragging = False
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        self.setCursor(Qt.SplitHCursor)

    def set_images(self, left_path: str, right_path: str):
        """Set the two images to compare."""
        if left_path and os.path.exists(left_path):
            self._left_pixmap = QPixmap(left_path)
        else:
            self._left_pixmap = None

        if right_path and os.path.exists(right_path):
            self._right_pixmap = QPixmap(right_path)
        else:
            self._right_pixmap = None

        self._slider_pos = 0.5
        self.update()

    def set_slider_position(self, pos: float):
        """Set slider position (0.0 to 1.0)."""
        self._slider_pos = max(0.0, min(1.0, pos))
        self.update()

    def paintEvent(self, event):
        """Paint the comparison view."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()
        split_x = int(rect.width() * self._slider_pos)

        # Draw left image (clipped to left of split)
        if self._left_pixmap and not self._left_pixmap.isNull():
            scaled_left = self._left_pixmap.scaled(
                rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            # Center the image
            x_offset = (rect.width() - scaled_left.width()) // 2
            y_offset = (rect.height() - scaled_left.height()) // 2

            painter.setClipRect(0, 0, split_x, rect.height())
            painter.drawPixmap(x_offset, y_offset, scaled_left)

        # Draw right image (clipped to right of split)
        if self._right_pixmap and not self._right_pixmap.isNull():
            scaled_right = self._right_pixmap.scaled(
                rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x_offset = (rect.width() - scaled_right.width()) // 2
            y_offset = (rect.height() - scaled_right.height()) // 2

            painter.setClipRect(split_x, 0, rect.width() - split_x, rect.height())
            painter.drawPixmap(x_offset, y_offset, scaled_right)

        # Draw divider line
        painter.setClipping(False)
        painter.setPen(QPen(QColor(100, 150, 255), 3))
        painter.drawLine(split_x, 0, split_x, rect.height())

        # Draw handle
        handle_y = rect.height() // 2
        painter.setBrush(QBrush(QColor(100, 150, 255)))
        painter.drawEllipse(split_x - 10, handle_y - 10, 20, 20)

    def mousePressEvent(self, event: QMouseEvent):
        """Start dragging the slider."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._update_slider_from_mouse(event.position())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Update slider position while dragging."""
        if self._is_dragging:
            self._update_slider_from_mouse(event.position())
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Stop dragging."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            event.accept()

    def _update_slider_from_mouse(self, pos: QPointF):
        """Update slider position from mouse position."""
        self._slider_pos = pos.x() / self.width()
        self._slider_pos = max(0.05, min(0.95, self._slider_pos))
        self.update()


class OnionSkinWidget(QWidget):
    """
    Onion skin comparison mode - overlay with opacity control.

    Base image shown at full opacity, overlay image with adjustable opacity.
    """

    opacity_changed = Signal(int)  # 0-100

    def __init__(self, parent=None):
        super().__init__(parent)

        self._base_pixmap: Optional[QPixmap] = None
        self._overlay_pixmap: Optional[QPixmap] = None
        self._opacity = 50  # 0-100

    def set_images(self, base_path: str, overlay_path: str):
        """Set base and overlay images."""
        if base_path and os.path.exists(base_path):
            self._base_pixmap = QPixmap(base_path)
        else:
            self._base_pixmap = None

        if overlay_path and os.path.exists(overlay_path):
            self._overlay_pixmap = QPixmap(overlay_path)
        else:
            self._overlay_pixmap = None

        self.update()

    def set_opacity(self, opacity: int):
        """Set overlay opacity (0-100)."""
        self._opacity = max(0, min(100, opacity))
        self.update()

    def paintEvent(self, event):
        """Paint the onion skin view."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()

        # Draw base image at full opacity
        if self._base_pixmap and not self._base_pixmap.isNull():
            scaled = self._base_pixmap.scaled(
                rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x_offset = (rect.width() - scaled.width()) // 2
            y_offset = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x_offset, y_offset, scaled)

        # Draw overlay image with opacity
        if self._overlay_pixmap and not self._overlay_pixmap.isNull():
            painter.setOpacity(self._opacity / 100.0)
            scaled = self._overlay_pixmap.scaled(
                rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x_offset = (rect.width() - scaled.width()) // 2
            y_offset = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x_offset, y_offset, scaled)


class GridComparisonWidget(QWidget):
    """
    2x2 grid comparison mode - four images with synchronized zoom/pan.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pixmaps: List[Optional[QPixmap]] = [None, None, None, None]
        self._labels: List[str] = ["A", "B", "C", "D"]

        self._setup_ui()

    def _setup_ui(self):
        """Setup the grid layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Top row
        top_row = QHBoxLayout()
        top_row.setSpacing(2)

        self._cells = []
        for i in range(4):
            cell = GridCell(self._labels[i])
            self._cells.append(cell)
            if i < 2:
                top_row.addWidget(cell)

        layout.addLayout(top_row)

        # Bottom row
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(2)
        bottom_row.addWidget(self._cells[2])
        bottom_row.addWidget(self._cells[3])
        layout.addLayout(bottom_row)

    def set_images(self, paths: List[str]):
        """Set up to 4 images for comparison."""
        for i in range(4):
            if i < len(paths) and paths[i] and os.path.exists(paths[i]):
                self._cells[i].set_image(paths[i])
            else:
                self._cells[i].clear_image()

    def set_image(self, index: int, path: str):
        """Set a single image at the given index (0-3)."""
        if 0 <= index < 4:
            if path and os.path.exists(path):
                self._cells[index].set_image(path)
            else:
                self._cells[index].clear_image()


class GridCell(QWidget):
    """Single cell in the grid comparison view."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)

        self._label = label
        self._pixmap: Optional[QPixmap] = None

        self.setProperty("variant", "canvas")
        self.setMinimumSize(100, 100)

    def set_image(self, path: str):
        """Set the image for this cell."""
        if path and os.path.exists(path):
            self._pixmap = QPixmap(path)
        else:
            self._pixmap = None
        self.update()

    def clear_image(self):
        """Clear the image from this cell."""
        self._pixmap = None
        self.update()

    def paintEvent(self, event):
        """Paint the cell."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()

        # Fill background
        painter.fillRect(rect, QColor(26, 26, 26))

        if self._pixmap and not self._pixmap.isNull():
            # Draw image
            scaled = self._pixmap.scaled(
                rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x_offset = (rect.width() - scaled.width()) // 2
            y_offset = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x_offset, y_offset, scaled)
        else:
            # Draw empty label
            painter.setPen(QColor(80, 80, 80))
            painter.drawText(rect, Qt.AlignCenter, f"Drop image {self._label}")

        # Draw label in corner
        painter.setPen(QColor(100, 150, 255))
        painter.drawText(10, 20, self._label)

        # Draw border
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))


class ComparisonViewer(QWidget):
    """
    Main comparison viewer widget with mode selection.

    Integrates slider, onion skin, and grid comparison modes.
    """

    closed = Signal()
    image_selected = Signal(int, str)  # slot index, path

    # Comparison modes
    MODE_SLIDER = "slider"
    MODE_ONION = "onion"
    MODE_GRID = "grid"

    def __init__(self, parent=None):
        super().__init__(parent)

        self._image_paths: List[str] = []
        self._current_mode = self.MODE_SLIDER

        self._setup_ui()

    def _setup_ui(self):
        """Setup the comparison viewer UI."""
        self.setProperty("variant", "canvas")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top control bar
        control_bar = QWidget()
        control_bar.setProperty("variant", "subtle")
        control_bar.setFixedHeight(40)

        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(10, 5, 10, 5)

        # Mode selector
        mode_label = QLabel("Mode:")
        mode_label.setProperty("textRole", "help")
        control_layout.addWidget(mode_label)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Slider", self.MODE_SLIDER)
        self._mode_combo.addItem("Onion Skin", self.MODE_ONION)
        self._mode_combo.addItem("2x2 Grid", self.MODE_GRID)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        control_layout.addWidget(self._mode_combo)

        control_layout.addSpacing(20)

        # Opacity slider (for onion skin mode)
        self._opacity_label = QLabel("Opacity:")
        self._opacity_label.setProperty("textRole", "help")
        control_layout.addWidget(self._opacity_label)

        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(50)
        self._opacity_slider.setFixedWidth(150)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        control_layout.addWidget(self._opacity_slider)

        self._opacity_value = QLabel("50%")
        self._opacity_value.setProperty("textRole", "help")
        self._opacity_value.setFixedWidth(40)
        control_layout.addWidget(self._opacity_value)

        control_layout.addStretch()

        # Swap button
        swap_btn = QPushButton("Swap A/B")
        swap_btn.setProperty("role", "secondary")
        swap_btn.setProperty("density", "sm")
        swap_btn.clicked.connect(self._swap_images)
        control_layout.addWidget(swap_btn)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("role", "secondary")
        clear_btn.setProperty("density", "sm")
        clear_btn.clicked.connect(self._clear_images)
        control_layout.addWidget(clear_btn)

        # Close button
        close_btn = QPushButton("X")
        close_btn.setFixedSize(30, 30)
        close_btn.setProperty("role", "ghost")
        close_btn.setProperty("iconOnly", "true")
        close_btn.clicked.connect(self.closed.emit)
        control_layout.addWidget(close_btn)

        layout.addWidget(control_bar)

        # Stacked widget for different modes
        self._stack = QStackedWidget()

        # Slider mode
        self._slider_widget = SliderComparisonWidget()
        self._stack.addWidget(self._slider_widget)

        # Onion skin mode
        self._onion_widget = OnionSkinWidget()
        self._stack.addWidget(self._onion_widget)

        # Grid mode
        self._grid_widget = GridComparisonWidget()
        self._stack.addWidget(self._grid_widget)

        layout.addWidget(self._stack)

        # Image selection bar (shows which images are loaded)
        self._selection_bar = QWidget()
        self._selection_bar.setProperty("variant", "subtle")
        self._selection_bar.setFixedHeight(35)

        selection_layout = QHBoxLayout(self._selection_bar)
        selection_layout.setContentsMargins(10, 5, 10, 5)

        self._slot_labels = []
        for i, label in enumerate(["A", "B", "C", "D"]):
            slot = QLabel(f"[{label}] Empty")
            slot.setProperty("textRole", "help")
            self._slot_labels.append(slot)
            selection_layout.addWidget(slot)

        selection_layout.addStretch()

        layout.addWidget(self._selection_bar)

        # Initial mode setup
        self._update_mode_ui()

    def _on_mode_changed(self, index: int):
        """Handle mode change."""
        self._current_mode = self._mode_combo.itemData(index)
        self._stack.setCurrentIndex(index)
        self._update_mode_ui()
        self._update_comparison()

    def _update_mode_ui(self):
        """Update UI based on current mode."""
        is_onion = self._current_mode == self.MODE_ONION
        self._opacity_label.setVisible(is_onion)
        self._opacity_slider.setVisible(is_onion)
        self._opacity_value.setVisible(is_onion)

        # Show/hide grid slots
        is_grid = self._current_mode == self.MODE_GRID
        for i, label in enumerate(self._slot_labels):
            label.setVisible(i < 2 or is_grid)

    def _on_opacity_changed(self, value: int):
        """Handle opacity slider change."""
        self._opacity_value.setText(f"{value}%")
        self._onion_widget.set_opacity(value)

    def _swap_images(self):
        """Swap A and B images."""
        if len(self._image_paths) >= 2:
            self._image_paths[0], self._image_paths[1] = self._image_paths[1], self._image_paths[0]
            self._update_comparison()
            self._update_slot_labels()

    def _clear_images(self):
        """Clear all images."""
        self._image_paths.clear()
        self._update_comparison()
        self._update_slot_labels()

    def set_images(self, paths: List[str]):
        """
        Set images for comparison.

        Args:
            paths: List of image paths (up to 4 for grid mode)
        """
        self._image_paths = list(paths)[:4]
        self._update_comparison()
        self._update_slot_labels()

    def add_image(self, path: str, slot: int = None):
        """
        Add an image to a specific slot.

        Args:
            path: Image path
            slot: Slot index (0-3), or None to use next available
        """
        if slot is None:
            slot = len(self._image_paths)

        while len(self._image_paths) <= slot:
            self._image_paths.append("")

        if slot < 4:
            self._image_paths[slot] = path
            self._update_comparison()
            self._update_slot_labels()

    def _update_comparison(self):
        """Update the comparison display based on current mode and images."""
        paths = self._image_paths

        if self._current_mode == self.MODE_SLIDER:
            left = paths[0] if len(paths) > 0 else ""
            right = paths[1] if len(paths) > 1 else ""
            self._slider_widget.set_images(left, right)

        elif self._current_mode == self.MODE_ONION:
            base = paths[0] if len(paths) > 0 else ""
            overlay = paths[1] if len(paths) > 1 else ""
            self._onion_widget.set_images(base, overlay)

        elif self._current_mode == self.MODE_GRID:
            self._grid_widget.set_images(paths)

    def _update_slot_labels(self):
        """Update slot labels with current image names."""
        labels = ["A", "B", "C", "D"]
        for i, label in enumerate(self._slot_labels):
            if i < len(self._image_paths) and self._image_paths[i]:
                name = os.path.basename(self._image_paths[i])
                if len(name) > 20:
                    name = name[:17] + "..."
                label.setText(f"[{labels[i]}] {name}")
                label.setProperty("textRole", "help")
                label.setProperty("state", "info")
            else:
                label.setText(f"[{labels[i]}] Empty")
                label.setProperty("textRole", "help")
