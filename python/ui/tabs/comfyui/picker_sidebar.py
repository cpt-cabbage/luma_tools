"""
Picker Sidebar for Model Picker Overlay.

Left sidebar with:
- "All Models" reset button
- Category filter (radio buttons for tags)
- Sort options (radio buttons)
- Add Model button (admin only)
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QButtonGroup,
    QRadioButton, QFrame, QScrollArea
)

from comfyui.ratings import get_predefined_tags

logger = logging.getLogger(__name__)

# Styling
SIDEBAR_BG = "#1a1d21"
SECTION_HEADER_COLOR = "#888888"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#aaaaaa"
ACCENT = "#4a9eff"
DIVIDER_COLOR = "#2a2d32"

# Sort options
SORT_OPTIONS = [
    ("Recently Used", "recently_used"),
    ("Highest Rated", "highest_rated"),
    ("Most Used", "most_used"),
    ("Name (A-Z)", "name"),
]


class SidebarSection(QWidget):
    """A section in the sidebar with header and content."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(8)

        # Section header
        header = QLabel(title.upper())
        header.setStyleSheet(f"""
            color: {SECTION_HEADER_COLOR};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        layout.addWidget(header)

        # Content container
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        layout.addWidget(self._content)

    def add_widget(self, widget: QWidget):
        """Add a widget to the section content."""
        self._content_layout.addWidget(widget)


class SidebarRadioButton(QRadioButton):
    """Styled radio button for sidebar."""

    def __init__(self, text: str, value: str, parent=None):
        super().__init__(text, parent)
        self._value = value
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QRadioButton {{
                color: {TEXT_SECONDARY};
                font-size: 12px;
                padding: 6px 8px;
                border-radius: 4px;
            }}
            QRadioButton:hover {{
                color: {TEXT_PRIMARY};
                background-color: #2a2d32;
            }}
            QRadioButton:checked {{
                color: {ACCENT};
                background-color: rgba(74, 158, 255, 0.1);
            }}
            QRadioButton::indicator {{
                width: 0px;
                height: 0px;
            }}
        """)

    @property
    def value(self) -> str:
        return self._value


class SidebarButton(QPushButton):
    """Styled button for sidebar (All Models, etc.)."""

    def __init__(self, text: str, is_active: bool = False, parent=None):
        super().__init__(text, parent)
        self._is_active = is_active
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def set_active(self, active: bool):
        """Set the active state."""
        self._is_active = active
        self._apply_style()

    def _apply_style(self):
        """Apply style based on active state."""
        if self._is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(74, 158, 255, 0.15);
                    color: {ACCENT};
                    border: none;
                    border-radius: 6px;
                    padding: 10px 12px;
                    font-size: 13px;
                    font-weight: bold;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: rgba(74, 158, 255, 0.2);
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {TEXT_PRIMARY};
                    border: none;
                    border-radius: 6px;
                    padding: 10px 12px;
                    font-size: 13px;
                    font-weight: bold;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: #2a2d32;
                }}
            """)


class PickerSidebar(QWidget):
    """
    Left sidebar for the model picker overlay.

    Signals:
        category_changed(str): Emitted when category filter changes
        sort_changed(str): Emitted when sort option changes
        add_model_clicked(): Emitted when Add Model button is clicked
    """

    category_changed = Signal(str)
    sort_changed = Signal(str)
    add_model_clicked = Signal()

    def __init__(self, is_admin: bool = False, parent=None):
        super().__init__(parent)
        self._is_admin = is_admin
        self._current_category = "all"
        self._current_sort = "recently_used"

        self._setup_ui()

    def _setup_ui(self):
        """Set up the sidebar UI."""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {SIDEBAR_BG};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(0)

        # Scroll area for content
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
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        # All Models button
        self._all_models_btn = SidebarButton("All Models", is_active=True)
        self._all_models_btn.clicked.connect(lambda: self._on_category_clicked("all"))
        content_layout.addWidget(self._all_models_btn)

        # Divider
        divider1 = QFrame()
        divider1.setFrameShape(QFrame.HLine)
        divider1.setStyleSheet(f"background-color: {DIVIDER_COLOR}; max-height: 1px;")
        content_layout.addWidget(divider1)

        # Categories section
        self._categories_section = SidebarSection("Categories")
        self._category_buttons: dict = {}
        self._category_group = QButtonGroup(self)
        self._category_group.setExclusive(True)

        for tag in get_predefined_tags():
            radio = SidebarRadioButton(tag, tag)
            self._category_group.addButton(radio)
            self._category_buttons[tag] = radio
            self._categories_section.add_widget(radio)

        self._category_group.buttonClicked.connect(self._on_category_radio_clicked)
        content_layout.addWidget(self._categories_section)

        # Divider
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setStyleSheet(f"background-color: {DIVIDER_COLOR}; max-height: 1px;")
        content_layout.addWidget(divider2)

        # Sort section
        self._sort_section = SidebarSection("Sort By")
        self._sort_buttons: dict = {}
        self._sort_group = QButtonGroup(self)
        self._sort_group.setExclusive(True)

        for label, key in SORT_OPTIONS:
            radio = SidebarRadioButton(label, key)
            if key == self._current_sort:
                radio.setChecked(True)
            self._sort_group.addButton(radio)
            self._sort_buttons[key] = radio
            self._sort_section.add_widget(radio)

        self._sort_group.buttonClicked.connect(self._on_sort_clicked)
        content_layout.addWidget(self._sort_section)

        content_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        # Add Model button (admin only)
        if self._is_admin:
            self._add_model_btn = QPushButton("+ Add Model")
            self._add_model_btn.setCursor(Qt.PointingHandCursor)
            self._add_model_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: #10b981;
                    border: 1px solid #10b981;
                    border-radius: 6px;
                    padding: 10px 16px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #10b981;
                    color: white;
                }}
            """)
            self._add_model_btn.clicked.connect(self._on_add_model_clicked)
            main_layout.addWidget(self._add_model_btn)

    def _on_category_clicked(self, category: str):
        """Handle All Models button click."""
        self._current_category = category
        self._all_models_btn.set_active(True)

        # Uncheck category radios
        checked = self._category_group.checkedButton()
        if checked:
            self._category_group.setExclusive(False)
            checked.setChecked(False)
            self._category_group.setExclusive(True)

        self.category_changed.emit(category)

    def _on_category_radio_clicked(self, button):
        """Handle category radio selection."""
        if isinstance(button, SidebarRadioButton):
            self._current_category = button.value
            self._all_models_btn.set_active(False)
            self.category_changed.emit(button.value)

    def _on_sort_clicked(self, button):
        """Handle sort radio selection."""
        if isinstance(button, SidebarRadioButton):
            self._current_sort = button.value
            self.sort_changed.emit(button.value)

    def _on_add_model_clicked(self):
        """Handle Add Model button click."""
        self.add_model_clicked.emit()

    def refresh_categories(self):
        """Rebuild category radio buttons from current settings."""
        # Remove old buttons from group and section
        for button in list(self._category_buttons.values()):
            self._category_group.removeButton(button)
            button.deleteLater()
        self._category_buttons.clear()

        # Clear the section content layout
        content_layout = self._categories_section._content_layout
        while content_layout.count():
            item = content_layout.takeAt(0)
            # Widgets already deleted above via deleteLater

        # Add fresh buttons
        for tag in get_predefined_tags():
            radio = SidebarRadioButton(tag, tag)
            self._category_group.addButton(radio)
            self._category_buttons[tag] = radio
            self._categories_section.add_widget(radio)

        # Reset to "All" since categories changed
        self._current_category = "all"
        self._all_models_btn.set_active(True)

    def set_category(self, category: str):
        """Set the current category."""
        self._current_category = category

        if category == "all":
            self._all_models_btn.set_active(True)
            checked = self._category_group.checkedButton()
            if checked:
                self._category_group.setExclusive(False)
                checked.setChecked(False)
                self._category_group.setExclusive(True)
        else:
            self._all_models_btn.set_active(False)
            if category in self._category_buttons:
                self._category_buttons[category].setChecked(True)

    def set_sort(self, sort_key: str):
        """Set the current sort option."""
        self._current_sort = sort_key
        if sort_key in self._sort_buttons:
            self._sort_buttons[sort_key].setChecked(True)
