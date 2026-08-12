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

from core.design_tokens import set_role

logger = logging.getLogger(__name__)


# Common dark theme stylesheet for edit dialogs
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

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Item name
        name_label = QLabel(f"{self.item_type_label}: {filename}")
        name_label.setProperty("textRole", "title")
        name_label.setProperty("state", "info")
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
        self.save_btn.setProperty("role", "primary")
        self.save_btn.clicked.connect(self._save_note)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

    def _load_note(self):
        """Load existing note for this item."""
        try:
            from comfyui.metadata import get_model_note
            filename = os.path.basename(self.item_path)
            note = get_model_note(self.output_dir, filename)
            self.note_edit.setPlainText(note)
        except Exception as e:
            logger.error(f"Error loading {self.item_type_label.lower()} note: {e}")

    def _save_note(self):
        """Save the note and close the dialog."""
        try:
            from comfyui.metadata import set_model_note
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


from core.config import UIColors


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
        self._selected_color = group.color if group else UIColors.GROUP_COLORS[0]
        self._color_buttons = []
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Edit Group" if self.group else "New Group")
        self.setMinimumWidth(300)
        self.setModal(True)

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

        for i, color in enumerate(UIColors.GROUP_COLORS):
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
        self.save_btn.setProperty("role", "primary")
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
            set_role(self.name_input, state="error")
            return
        self.accept()

    def get_result(self):
        """Get the name and color from the dialog.

        Returns:
            Tuple of (name, color) or (None, None) if cancelled
        """
        return (self.name_input.text().strip(), self._selected_color)


class QuickGroupDialog(QDialog):
    """
    Quick dialog for creating a group via drag-and-drop.

    Shows a simple name input field and automatically assigns a random color.
    Used when dragging one thumbnail onto another to quickly create a group.
    """

    def __init__(self, item_count=2, parent=None):
        """
        Initialize the quick group dialog.

        Args:
            item_count: Number of items that will be in the group
            parent: Parent widget
        """
        import random
        super().__init__(parent)
        self._item_count = item_count
        self._selected_color = random.choice(UIColors.GROUP_COLORS)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Create Group")
        self.setMinimumWidth(280)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header message
        header = QLabel(f"Create a new group with {self._item_count} items")
        header.setProperty("textRole", "help")
        layout.addWidget(header)

        # Name input
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Group name...")
        self.name_input.returnPressed.connect(self._on_create)
        layout.addWidget(self.name_input)

        # Color preview
        color_layout = QHBoxLayout()
        color_label = QLabel("Color:")
        color_label.setProperty("textRole", "help")
        color_layout.addWidget(color_label)

        self._color_preview = QLabel()
        self._color_preview.setFixedSize(20, 20)
        self._color_preview.setStyleSheet(f"""
            QLabel {{
                background-color: {self._selected_color};
                border-radius: 4px;
            }}
        """)
        color_layout.addWidget(self._color_preview)
        color_layout.addStretch()

        # Change color button
        change_btn = QPushButton("Change")
        change_btn.setFixedWidth(60)
        change_btn.setProperty("role", "secondary")
        change_btn.setProperty("density", "sm")
        change_btn.clicked.connect(self._cycle_color)
        color_layout.addWidget(change_btn)

        layout.addLayout(color_layout)

        layout.addStretch()

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        create_btn = QPushButton("Create")
        create_btn.setProperty("role", "primary")
        create_btn.clicked.connect(self._on_create)
        button_layout.addWidget(create_btn)

        layout.addLayout(button_layout)

        # Focus on name input
        self.name_input.setFocus()

    def _cycle_color(self):
        """Cycle to next color in the palette."""
        import random
        # Pick a different random color
        available = [c for c in UIColors.GROUP_COLORS if c != self._selected_color]
        if available:
            self._selected_color = random.choice(available)
        else:
            self._selected_color = random.choice(UIColors.GROUP_COLORS)
        self._color_preview.setStyleSheet(f"""
            QLabel {{
                background-color: {self._selected_color};
                border-radius: 4px;
            }}
        """)

    def _on_create(self):
        """Validate and accept the dialog."""
        name = self.name_input.text().strip()
        if not name:
            self.name_input.setFocus()
            set_role(self.name_input, state="error")
            return
        self.accept()

    def get_result(self):
        """Get the name and color from the dialog (QuickGroupDialog).

        Returns:
            Tuple of (name, color) or (None, None) if cancelled
        """
        return (self.name_input.text().strip(), self._selected_color)


class MetadataDiffDialog(QDialog):
    """Dialog showing side-by-side metadata comparison between two images.

    Highlights differences in parameters like seed, prompt, and editable values.
    """

    def __init__(self, parent, path_a: str, path_b: str, metadata_a: dict, metadata_b: dict):
        """Initialize the diff dialog.

        Args:
            parent: Parent widget
            path_a: Path to first image (left)
            path_b: Path to second image (right)
            metadata_a: Metadata dict for first image
            metadata_b: Metadata dict for second image
        """
        super().__init__(parent)
        self.setWindowTitle("Parameter Comparison")
        self.setMinimumSize(600, 400)
        self.resize(700, 500)

        self._path_a = path_a
        self._path_b = path_b
        self._metadata_a = metadata_a or {}
        self._metadata_b = metadata_b or {}

        self._setup_ui()
        self._compute_diff()

    def _setup_ui(self):
        """Set up the dialog UI."""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header with filenames
        header = QHBoxLayout()
        name_a = os.path.basename(self._path_a)
        name_b = os.path.basename(self._path_b)

        label_a = QLabel(f"A: {name_a}")
        label_a.setProperty("textRole", "title")
        label_a.setProperty("state", "info")
        label_b = QLabel(f"B: {name_b}")
        label_b.setProperty("textRole", "title")
        label_b.setProperty("state", "success")

        header.addWidget(label_a)
        header.addStretch()
        header.addWidget(label_b)
        layout.addLayout(header)

        # Diff content area
        from PySide6.QtWidgets import QScrollArea, QWidget
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self._diff_container = QWidget()
        self._diff_layout = QGridLayout(self._diff_container)
        self._diff_layout.setColumnStretch(0, 1)  # Parameter name
        self._diff_layout.setColumnStretch(1, 2)  # Value A
        self._diff_layout.setColumnStretch(2, 2)  # Value B
        scroll.setWidget(self._diff_container)
        layout.addWidget(scroll, 1)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setProperty("role", "secondary")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _compute_diff(self):
        """Compute and display the diff between metadata."""
        row = 0

        # Add header row
        header_style = "font-weight: bold; color: #888; font-size: 10px; padding: 4px;"
        for col, text in enumerate(["Parameter", "Image A", "Image B"]):
            label = QLabel(text)
            label.setProperty("textRole", "micro")
            self._diff_layout.addWidget(label, row, col)
        row += 1

        # Parameters to compare
        params = [
            ("workflow_preset", "Workflow Preset"),
            ("base_seed", "Base Seed"),
            ("generation_count", "Generation Count"),
            ("prompt", "Prompt"),
            ("timestamp", "Timestamp"),
        ]

        for key, display_name in params:
            val_a = self._metadata_a.get(key)
            val_b = self._metadata_b.get(key)
            self._add_diff_row(row, display_name, val_a, val_b)
            row += 1

        # Compare editable values
        editable_a = self._metadata_a.get('editable_values', {})
        editable_b = self._metadata_b.get('editable_values', {})

        if editable_a or editable_b:
            # Section header
            section_label = QLabel("-- Editable Parameters --")
            section_label.setProperty("textRole", "micro")
            self._diff_layout.addWidget(section_label, row, 0, 1, 3)
            row += 1

            # Collect all keys
            all_keys = set(editable_a.keys()) | set(editable_b.keys())

            for node_key in sorted(all_keys):
                node_a = editable_a.get(node_key, {})
                node_b = editable_b.get(node_key, {})

                display_name = node_a.get('display_name') or node_b.get('display_name') or node_key
                val_a = node_a.get('value')
                val_b = node_b.get('value')

                # Truncate long values
                if isinstance(val_a, str) and len(val_a) > 50:
                    val_a = val_a[:47] + "..."
                if isinstance(val_b, str) and len(val_b) > 50:
                    val_b = val_b[:47] + "..."

                self._add_diff_row(row, f"  {display_name}", val_a, val_b)
                row += 1

        # Add stretch
        self._diff_layout.setRowStretch(row, 1)

    def _add_diff_row(self, row: int, name: str, val_a, val_b):
        """Add a row to the diff display."""
        # Format values
        str_a = str(val_a) if val_a is not None else "-"
        str_b = str(val_b) if val_b is not None else "-"

        # Determine if different
        is_different = val_a != val_b

        # Styles
        name_style = "color: #aaa; font-size: 11px; padding: 4px;"
        value_style_same = "color: #888; font-size: 11px; padding: 4px; background-color: #252528;"
        value_style_diff_a = "color: #4a9eff; font-size: 11px; padding: 4px; background-color: #1e2a3f; border-left: 2px solid #4a9eff;"
        value_style_diff_b = "color: #10b981; font-size: 11px; padding: 4px; background-color: #1e2f28; border-left: 2px solid #10b981;"

        # Name label
        name_label = QLabel(name)
        name_label.setProperty("textRole", "label")
        self._diff_layout.addWidget(name_label, row, 0)

        # Value labels
        val_label_a = QLabel(str_a)
        val_label_b = QLabel(str_b)

        if is_different:
            val_label_a.setProperty("variant", "cell")
            val_label_a.setProperty("state", "a")
            val_label_b.setProperty("variant", "cell")
            val_label_b.setProperty("state", "b")
        else:
            val_label_a.setProperty("variant", "cell")
            val_label_b.setProperty("variant", "cell")

        self._diff_layout.addWidget(val_label_a, row, 1)
        self._diff_layout.addWidget(val_label_b, row, 2)


def show_metadata_diff_dialog(parent, path_a: str, path_b: str, metadata_a: dict, metadata_b: dict):
    """Show a metadata comparison dialog.

    Args:
        parent: Parent widget
        path_a: Path to first image
        path_b: Path to second image
        metadata_a: Metadata dict for first image
        metadata_b: Metadata dict for second image
    """
    dialog = MetadataDiffDialog(parent, path_a, path_b, metadata_a, metadata_b)
    dialog.exec()
