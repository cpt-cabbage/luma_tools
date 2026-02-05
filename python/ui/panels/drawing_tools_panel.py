"""
Floating Drawing Tools Panel for Canvas tab.

Provides drawing tools (pen, shapes) in a floating panel that appears
when drawing mode is activated.
"""

import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QSpinBox, QColorDialog
)
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


class DrawingToolsPanel(QWidget):
    """
    Floating panel containing drawing tools.

    Shows when drawing mode is enabled, hides when disabled.
    Can be dragged to reposition within the canvas area.
    """

    # Signals
    tool_changed = Signal(str)  # pen, rect, ellipse, line
    brush_size_changed = Signal(int)
    color_changed = Signal(QColor)
    panel_closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_tool = "pen"
        self._brush_size = 3
        self._current_color = QColor(255, 0, 0)  # Red to match canvas default
        self._tool_buttons = {}

        self._setup_ui()
        self._dragging = False
        self._drag_offset = None

        # Float above other widgets without stealing keyboard focus
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)

    def _setup_ui(self):
        """Setup the panel UI."""
        self.setFixedWidth(180)
        self.setStyleSheet("""
            DrawingToolsPanel {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (draggable)
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border-bottom: 1px solid #444;
            }
        """)
        header.setFixedHeight(28)
        header.setCursor(Qt.OpenHandCursor)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 4, 6, 4)

        title = QLabel("Drawing Tools")
        title.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.setFixedSize(18, 18)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { color: #fff; background: #555; border-radius: 3px; }
        """)
        close_btn.clicked.connect(self._on_close)
        header_layout.addWidget(close_btn)

        layout.addWidget(header)
        self._header = header

        # Tools section
        tools_frame = QFrame()
        tools_frame.setStyleSheet("background: transparent;")
        tools_layout = QVBoxLayout(tools_frame)
        tools_layout.setContentsMargins(8, 8, 8, 8)
        tools_layout.setSpacing(6)

        # Top row: Select drawings and Eraser
        row0 = QHBoxLayout()
        row0.setSpacing(4)

        self._add_tool_button(row0, "select_drawings", "Select", "")
        self._add_tool_button(row0, "eraser", "Eraser", "E")

        tools_layout.addLayout(row0)

        # Tool buttons row 1
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._add_tool_button(row1, "pen", "Pen", "P")
        self._add_tool_button(row1, "line", "Line", "L")

        tools_layout.addLayout(row1)

        # Tool buttons row 2
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self._add_tool_button(row2, "rect", "Rect", "U")
        self._add_tool_button(row2, "ellipse", "Ellipse", "O")

        tools_layout.addLayout(row2)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444;")
        tools_layout.addWidget(sep)

        # Brush size
        size_row = QHBoxLayout()
        size_row.setSpacing(6)

        size_label = QLabel("Size:")
        size_label.setStyleSheet("color: #888; font-size: 11px;")
        size_label.setFixedWidth(32)
        size_row.addWidget(size_label)

        self._size_slider = QSlider(Qt.Horizontal)
        self._size_slider.setFocusPolicy(Qt.NoFocus)
        self._size_slider.setMinimum(1)
        self._size_slider.setMaximum(50)
        self._size_slider.setValue(self._brush_size)
        self._size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #4a9eff;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
        """)
        self._size_slider.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self._size_slider)

        self._size_spin = QSpinBox()
        self._size_spin.setFocusPolicy(Qt.NoFocus)
        self._size_spin.setMinimum(1)
        self._size_spin.setMaximum(50)
        self._size_spin.setValue(self._brush_size)
        self._size_spin.setFixedWidth(45)
        self._size_spin.setStyleSheet("""
            QSpinBox {
                background: #383838;
                color: #ccc;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px;
            }
        """)
        self._size_spin.valueChanged.connect(self._on_size_spin_changed)
        size_row.addWidget(self._size_spin)

        tools_layout.addLayout(size_row)

        # Color button
        color_row = QHBoxLayout()
        color_row.setSpacing(6)

        color_label = QLabel("Color:")
        color_label.setStyleSheet("color: #888; font-size: 11px;")
        color_label.setFixedWidth(32)
        color_row.addWidget(color_label)

        self._color_btn = QPushButton()
        self._color_btn.setFocusPolicy(Qt.NoFocus)
        self._color_btn.setFixedSize(60, 24)
        self._update_color_button()
        self._color_btn.clicked.connect(self._on_color_click)
        color_row.addWidget(self._color_btn)

        color_row.addStretch()

        tools_layout.addLayout(color_row)

        layout.addWidget(tools_frame)

        # Set initial tool
        self._update_tool_buttons()

    def _add_tool_button(self, layout: QHBoxLayout, tool_id: str, label: str, shortcut: str):
        """Add a tool button to the layout."""
        btn_text = f"{label} [{shortcut}]" if shortcut else label
        btn = QPushButton(btn_text)
        btn.setCheckable(True)
        btn.setFixedHeight(28)
        btn.setStyleSheet("""
            QPushButton {
                background: #383838;
                color: #ccc;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #454545;
                border-color: #555;
            }
            QPushButton:checked {
                background: #4a9eff;
                color: white;
                border-color: #4a9eff;
            }
        """)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.clicked.connect(lambda checked, t=tool_id: self._on_tool_clicked(t))
        layout.addWidget(btn)
        self._tool_buttons[tool_id] = btn

    def _on_tool_clicked(self, tool_id: str):
        """Handle tool button click."""
        self._current_tool = tool_id
        self._update_tool_buttons()
        self.tool_changed.emit(tool_id)
        logger.debug(f"Drawing tool changed to: {tool_id}")

    def _update_tool_buttons(self):
        """Update tool button checked states."""
        for tool_id, btn in self._tool_buttons.items():
            btn.setChecked(tool_id == self._current_tool)

    def _on_size_changed(self, value: int):
        """Handle size slider change."""
        self._brush_size = value
        self._size_spin.blockSignals(True)
        self._size_spin.setValue(value)
        self._size_spin.blockSignals(False)
        self.brush_size_changed.emit(value)

    def _on_size_spin_changed(self, value: int):
        """Handle size spinbox change."""
        self._brush_size = value
        self._size_slider.blockSignals(True)
        self._size_slider.setValue(value)
        self._size_slider.blockSignals(False)
        self.brush_size_changed.emit(value)

    def _on_color_click(self):
        """Handle color button click."""
        color = QColorDialog.getColor(
            self._current_color,
            self,
            "Select Drawing Color"
        )
        if color.isValid():
            self._current_color = color
            self._update_color_button()
            self.color_changed.emit(color)

    def _update_color_button(self):
        """Update color button appearance."""
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._current_color.name()};
                border: 2px solid #555;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: #888;
            }}
        """)

    def _on_close(self):
        """Handle close button click."""
        self.hide()
        self.panel_closed.emit()

    def set_tool(self, tool_id: str):
        """Set the current tool programmatically."""
        if tool_id in self._tool_buttons:
            self._current_tool = tool_id
            self._update_tool_buttons()

    def get_tool(self) -> str:
        """Get the current tool."""
        return self._current_tool

    def set_brush_size(self, size: int):
        """Set brush size programmatically."""
        size = max(1, min(50, size))
        self._brush_size = size
        self._size_slider.setValue(size)
        self._size_spin.setValue(size)

    def get_brush_size(self) -> int:
        """Get the current brush size."""
        return self._brush_size

    def set_color(self, color: QColor):
        """Set drawing color programmatically."""
        self._current_color = color
        self._update_color_button()

    def get_color(self) -> QColor:
        """Get the current drawing color."""
        return self._current_color

    def show_at(self, x: int, y: int):
        """Show the panel at the specified position."""
        self.move(x, y)
        self.show()
        self.raise_()

    # Dragging support
    def mousePressEvent(self, event):
        """Handle mouse press for dragging."""
        if event.button() == Qt.LeftButton:
            # Check if clicking on header
            header_rect = self._header.geometry()
            if header_rect.contains(event.pos()):
                self._dragging = True
                # Store the offset from the window's top-left to the click position
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self._header.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging."""
        if self._dragging and self._drag_offset:
            # Calculate new position in global screen coordinates
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release for dragging."""
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._drag_offset = None
            self._header.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
