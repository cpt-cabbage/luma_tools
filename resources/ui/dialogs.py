"""
Dialog widgets for editing gallery items.

Provides dialogs for editing notes on images and 3D models.
"""
import os
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit
)


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
            print(f"Error loading {self.item_type_label.lower()} note: {e}")

    def _save_note(self):
        """Save the note and close the dialog."""
        try:
            from comfyui.service import set_model_note
            filename = os.path.basename(self.item_path)
            note = self.note_edit.toPlainText()
            if set_model_note(self.output_dir, filename, note):
                print(f"Saved note for {filename}")
                self.accept()
            else:
                print(f"Failed to save note for {filename}")
                self.reject()
        except Exception as e:
            print(f"Error saving {self.item_type_label.lower()} note: {e}")
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
