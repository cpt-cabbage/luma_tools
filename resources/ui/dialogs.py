"""
Dialog widgets for editing gallery items.

Provides dialogs for editing notes on images and 3D models,
and group management dialogs.
"""
import os
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QLineEdit, QGridLayout, QButtonGroup, QColorDialog
)
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


# Common dark theme stylesheet for edit dialogs
EDIT_DIALOG_STYLESHEET = """
    QDialog {
        background-color: #1e1e22;
    }
    QLabel {
        color: #e0e0e0;
        font-size: 12px;
    }
    QPlainTextEdit {
        background-color: #2c313a;
        color: #e0e0e0;
        border: 1px solid #3c414b;
        border-radius: 4px;
        padding: 8px;
        font-size: 12px;
    }
    QPlainTextEdit:focus {
        border-color: #4a9eff;
    }
    QPushButton {
        background-color: #3c414b;
        color: #e0e0e0;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 12px;
    }
    QPushButton:hover {
        background-color: #4a5160;
    }
    QPushButton:pressed {
        background-color: #2a2e36;
    }
    QPushButton[primary="true"] {
        background-color: #4a9eff;
        color: white;
    }
    QPushButton[primary="true"]:hover {
        background-color: #6ab0ff;
    }
"""


class BaseEditDialog(QDialog):
    """
    Base dialog for editing gallery item notes.

    Subclasses override:
    - item_type_label: Display label for item type (e.g., "Item", "Model")
    - placeholder_text: Placeholder for the note text edit
    """
    item_type_label = "Item"
    placeholder_text = "Add a note or description..."

    def __init__(self, item_path: str, output_dir: str, parent=None):
        super().__init__(parent)
        self.item_path = item_path
        self.output_dir = output_dir
        self._setup_ui()
        self._load_note()

    def _setup_ui(self):
        """Set up the dialog UI."""
        filename = os.path.basename(self.item_path)
        self.setWindowTitle(f"Edit {self.item_type_label} - {filename}")
        self.setMinimumSize(400, 300)
        self.resize(450, 350)
        self.setModal(True)
        self.setStyleSheet(EDIT_DIALOG_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Item name
        name_label = QLabel(f"{self.item_type_label}: {filename}")
        name_label.setStyleSheet("font-weight: bold; color: #4a9eff;")
        layout.addWidget(name_label)

        # Note label
        note_label = QLabel("Note:")
        layout.addWidget(note_label)

        # Note text edit
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText(self.placeholder_text)
        layout.addWidget(self.note_edit)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(self._save_note)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

    def _load_note(self):
        """Load existing note for this item."""
        try:
            from comfyui.service import get_model_note
            filename = os.path.basename(self.item_path)
            note = get_model_note(self.output_dir, filename)
            self.note_edit.setPlainText(note)
        except Exception as e:
            logger.error(f"Error loading {self.item_type_label.lower()} note: {e}")

    def _save_note(self):
        """Save the note and close the dialog."""
        try:
            from comfyui.service import set_model_note
            filename = os.path.basename(self.item_path)
            note = self.note_edit.toPlainText()
            if set_model_note(self.output_dir, filename, note):
                logger.info(f"Saved note for {filename}")
                self.accept()
            else:
                logger.error(f"Failed to save note for {filename}")
                self.reject()
        except Exception as e:
            logger.error(f"Error saving {self.item_type_label.lower()} note: {e}")
            self.reject()

    def get_note(self) -> str:
        """Get the current note text."""
        return self.note_edit.toPlainText()


class EditItemDialog(BaseEditDialog):
    """Dialog for editing gallery item notes (images)."""
    item_type_label = "Item"
    placeholder_text = "Add a note or description for this item..."


class EditModelDialog(BaseEditDialog):
    """Dialog for editing 3D model notes."""
    item_type_label = "Model"
    placeholder_text = "Add a note or description for this model..."


# Import GROUP_COLORS from config for backwards compatibility
from core.config import UIColors
GROUP_COLORS = UIColors.GROUP_COLORS


class ColorButton(QPushButton):
    """A colored button for the color picker."""

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(36, 36)
        self.setCheckable(True)
        self._update_style()

    def _update_style(self):
        checked_border = "3px solid white" if self.isChecked() else f"2px solid {self.color}"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color};
                border: {checked_border};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border: 2px solid white;
            }}
        """)

    def setChecked(self, checked):
        super().setChecked(checked)
        self._update_style()


class GroupEditorDialog(QDialog):
    """
    Dialog for creating or editing a gallery group.

    Provides:
    - Name input field
    - Color picker grid (8 preset colors in 4x2)
    - Create/Save and Cancel buttons
    """

    def __init__(self, group=None, parent=None):
        """
        Initialize the group editor dialog.

        Args:
            group: Optional GroupDef to edit (None for creating new)
            parent: Parent widget
        """
        super().__init__(parent)
        self.group = group
        self._selected_color = group.color if group else GROUP_COLORS[0]
        self._color_buttons = []
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Edit Group" if self.group else "New Group")
        self.setMinimumWidth(300)
        self.setModal(True)
        self.setStyleSheet(EDIT_DIALOG_STYLESHEET + """
            QLineEdit {
                background-color: #2c313a;
                color: #e0e0e0;
                border: 1px solid #3c414b;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #4a9eff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Name input
        name_label = QLabel("Group Name:")
        layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter group name...")
        if self.group:
            self.name_input.setText(self.group.name)
        layout.addWidget(self.name_input)

        # Color picker
        color_label = QLabel("Color:")
        layout.addWidget(color_label)

        color_layout = QHBoxLayout()
        color_layout.setSpacing(8)

        # Create 4x2 grid of color buttons
        color_grid = QGridLayout()
        color_grid.setSpacing(8)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        for i, color in enumerate(GROUP_COLORS):
            btn = ColorButton(color)
            btn.setChecked(color == self._selected_color)
            btn.clicked.connect(lambda checked, c=color: self._on_color_selected(c))
            self._button_group.addButton(btn)
            self._color_buttons.append(btn)
            row = i // 4
            col = i % 4
            color_grid.addWidget(btn, row, col)

        layout.addLayout(color_grid)

        # Custom color button (optional)
        custom_btn = QPushButton("Custom Color...")
        custom_btn.clicked.connect(self._pick_custom_color)
        layout.addWidget(custom_btn)

        layout.addStretch()

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save" if self.group else "Create")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

        # Focus on name input
        self.name_input.setFocus()

    def _on_color_selected(self, color):
        """Handle color button selection."""
        self._selected_color = color
        for btn in self._color_buttons:
            btn.setChecked(btn.color == color)

    def _pick_custom_color(self):
        """Open system color picker for custom color."""
        color = QColorDialog.getColor(
            QColor(self._selected_color),
            self,
            "Choose Group Color"
        )
        if color.isValid():
            self._selected_color = color.name()
            # Uncheck all preset buttons
            for btn in self._color_buttons:
                btn.setChecked(False)

    def _on_save(self):
        """Validate and accept the dialog."""
        name = self.name_input.text().strip()
        if not name:
            self.name_input.setFocus()
            self.name_input.setStyleSheet("""
                QLineEdit {
                    background-color: #2c313a;
                    color: #e0e0e0;
                    border: 2px solid #ef4444;
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 12px;
                }
            """)
            return
        self.accept()

    def get_result(self):
        """Get the name and color from the dialog.

        Returns:
            Tuple of (name, color) or (None, None) if cancelled
        """
        return (self.name_input.text().strip(), self._selected_color)
