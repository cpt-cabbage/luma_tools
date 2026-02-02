"""
Add Model Wizard for ComfyUI Tab.

Quick-add wizard for creating new workflow models with steps:
1. Browse for workflow .json file
2. Enter model name, optional description
3. Select tags from predefined list
4. Done - model added

Designed for fast model creation with minimal friction.
"""

import os
import logging
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QCheckBox,
    QGridLayout, QFrame, QFileDialog
)

from comfyui.presets_manager import save_comfyui_workflow_preset, get_comfyui_workflow_presets
from comfyui.ratings import set_model_tags, get_predefined_tags

logger = logging.getLogger(__name__)


class WorkflowPage(QWizardPage):
    """Page 1: Select workflow file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Select Workflow")
        self.setSubTitle("Choose the ComfyUI workflow JSON file for this model.")

        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # File selection
        file_layout = QHBoxLayout()

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select workflow file...")
        self._path_edit.textChanged.connect(self.completeChanged)
        file_layout.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        file_layout.addWidget(browse_btn)

        layout.addLayout(file_layout)

        # Info label
        info = QLabel(
            "Select a ComfyUI workflow JSON file. The workflow should have\n"
            "editable nodes marked with '_editable' suffix in their titles."
        )
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)

        layout.addStretch()

        # Register field
        self.registerField("workflow_path*", self._path_edit)

    def _on_browse(self):
        """Browse for workflow file."""
        from file_dialogs import browse_file_with_memory

        file_path = browse_file_with_memory(
            self.wizard(),
            context="comfyui_workflow",
            title="Select ComfyUI Workflow File",
            file_filter="JSON Files (*.json);;All Files (*)",
            fallback_path=os.path.expanduser("~")
        )
        if file_path:
            self._path_edit.setText(file_path)

    def isComplete(self) -> bool:
        """Check if page is complete."""
        path = self._path_edit.text().strip()
        return bool(path) and os.path.exists(path)


class DetailsPage(QWizardPage):
    """Page 2: Enter model details."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Model Details")
        self.setSubTitle("Enter a name and optional description for the model.")

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        form = QFormLayout()
        form.setSpacing(12)

        # Model name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g., Flux Upscale or Generation/SD3.5")
        self._name_edit.textChanged.connect(self.completeChanged)
        form.addRow("Name:", self._name_edit)

        # Description
        self._desc_edit = QPlainTextEdit()
        self._desc_edit.setPlaceholderText("Optional description or usage notes...")
        self._desc_edit.setMaximumHeight(80)
        form.addRow("Description:", self._desc_edit)

        layout.addLayout(form)

        # Options
        self._iteratable_check = QCheckBox("Enable Iterate Mode")
        self._iteratable_check.setToolTip(
            "Iterate mode allows reviewing results and refining prompts\n"
            "between generations when only 1 image is selected."
        )
        layout.addWidget(self._iteratable_check)

        # Info
        info = QLabel(
            "Use forward slashes (/) in the name to organize models into folders.\n"
            "Example: 'Upscaling/Flux 4x' creates a folder called 'Upscaling'."
        )
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)

        layout.addStretch()

        # Register fields
        self.registerField("model_name*", self._name_edit)
        self.registerField("model_description", self._desc_edit, "plainText")
        self.registerField("iteratable", self._iteratable_check)

    def initializePage(self):
        """Initialize page with workflow file name as default."""
        workflow_path = self.field("workflow_path")
        if workflow_path:
            # Use workflow filename (without extension) as default name
            basename = os.path.basename(workflow_path)
            name = os.path.splitext(basename)[0]
            # Clean up common prefixes/suffixes
            name = name.replace("_", " ").replace("-", " ")
            if not self._name_edit.text():
                self._name_edit.setText(name)

    def isComplete(self) -> bool:
        """Check if page is complete."""
        name = self._name_edit.text().strip()
        if not name:
            return False

        # Check if name already exists
        presets = get_comfyui_workflow_presets()
        if name in presets:
            return False

        return True

    def validatePage(self) -> bool:
        """Validate before proceeding."""
        name = self._name_edit.text().strip()
        presets = get_comfyui_workflow_presets()

        if name in presets:
            from dialog_helpers import show_warning
            show_warning(
                "Name Exists",
                f"A model named '{name}' already exists.\n"
                "Please choose a different name.",
                self.wizard()
            )
            return False

        return True


class TagsPage(QWizardPage):
    """Page 3: Select tags."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Categorize Model")
        self.setSubTitle("Select tags to help organize and find this model.")

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Tags grid
        tags_frame = QFrame()
        tags_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
        """)
        tags_layout = QGridLayout(tags_frame)
        tags_layout.setContentsMargins(15, 15, 15, 15)
        tags_layout.setSpacing(10)

        self._tag_checks: Dict[str, QCheckBox] = {}
        predefined = get_predefined_tags()

        cols = 3
        for i, tag in enumerate(predefined):
            check = QCheckBox(tag)
            check.setStyleSheet("color: #e0e0e0;")
            self._tag_checks[tag] = check
            tags_layout.addWidget(check, i // cols, i % cols)

        layout.addWidget(tags_frame)

        # Info
        info = QLabel(
            "Tags help users find models by category.\n"
            "Select any that apply to this model."
        )
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)

        layout.addStretch()

    def get_selected_tags(self) -> List[str]:
        """Get list of selected tags."""
        return [
            tag for tag, check in self._tag_checks.items()
            if check.isChecked()
        ]


class AddModelWizard(QWizard):
    """
    Wizard for quickly adding new workflow models.

    Steps:
    1. Select workflow file
    2. Enter name and description
    3. Select tags
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Model")
        self.setMinimumSize(500, 400)

        # Set modern style
        self.setWizardStyle(QWizard.ModernStyle)

        # Add pages
        self._workflow_page = WorkflowPage()
        self._details_page = DetailsPage()
        self._tags_page = TagsPage()

        self.addPage(self._workflow_page)
        self.addPage(self._details_page)
        self.addPage(self._tags_page)

        # Customize buttons
        self.setButtonText(QWizard.FinishButton, "Create Model")

    def accept(self):
        """Create the model when wizard completes."""
        try:
            workflow_path = self.field("workflow_path")
            model_name = self.field("model_name")
            description = self.field("model_description")
            iteratable = self.field("iteratable")
            tags = self._tags_page.get_selected_tags()

            # Save the preset
            save_comfyui_workflow_preset(
                model_name,
                workflow_path,
                iteratable=iteratable,
                note=description
            )

            # Save tags
            if tags:
                set_model_tags(model_name, tags)

            logger.info(f"Created new model: {model_name}")
            super().accept()

        except Exception as e:
            logger.error(f"Failed to create model: {e}")
            from dialog_helpers import show_error
            show_error("Error", f"Failed to create model:\n{e}", self)
