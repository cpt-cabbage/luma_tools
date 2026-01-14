"""
ComfyUI tab module for Luma Tools.

Handles ComfyUI workflow submission and AI image generation.
"""

import os
import random
import time

from PySide2 import QtWidgets, QtCore
from PySide2.QtCore import Qt, QTimer, QThreadPool
from PySide2.QtWidgets import (
    QMenu, QMessageBox, QInputDialog, QDialog, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget, QFileDialog
)
from PySide2.QtGui import QPixmap

from .base_tab import BaseTab
from .comfyui_polling import PollingMixin


class ComfyUITab(PollingMixin, BaseTab):
    """Tab for ComfyUI AI image generation."""

    @property
    def ui_file(self) -> str:
        return "comfyui.ui"

    @property
    def tab_name(self) -> str:
        return "ComfyUI"

    @property
    def tab_id(self) -> str:
        return "comfyui"

    def connect_signals(self):
        """Connect ComfyUI tab signals."""
        from icons import IconManager, DEFAULT_ICON_COLOR

        # Workflow preset signals
        self.ui.ComfyUIChoosePreset.clicked.connect(self._on_choose_preset_clicked)
        self.ui.ComfyUIAddPreset.clicked.connect(self._on_add_preset_clicked)
        self.ui.ComfyUIEditPreset.clicked.connect(self._on_edit_preset_clicked)
        self.ui.ComfyUISubmit.clicked.connect(self._on_submit_clicked)
        self.ui.ComfyUIGenerationCount.valueChanged.connect(self._on_generation_count_changed)
        self.ui.ComfyUISeed.valueChanged.connect(self._on_seed_changed)
        self.ui.ComfyUIRandomizeSeed.clicked.connect(self._on_randomize_seed)
        self.ui.ComfyUIRandomizeSeed.setIcon(IconManager.get_icon("dice", DEFAULT_ICON_COLOR, 16))


        # Iterate mode signals
        self.ui.ComfyUIUseAsInput.clicked.connect(self._on_use_as_input_clicked)

        # Cancel jobs button
        self.ui.ComfyUICancelJobs.clicked.connect(self._on_cancel_jobs_clicked)

    def initialize(self):
        """Initialize ComfyUI tab."""
        # Internal state
        self._comfyui_dynamic_widgets = {}
        self._current_preset_name = None
        self._current_selected_workflow = None  # For multi-workflow models
        self._pending_editable_values = {}

        # Create workflow selector dropdown (will be added to UI dynamically)
        self._setup_workflow_selector()
        self._setup_note_display()

        # Initialize polling state from mixin
        self._init_polling_state()

        # Display network path from global settings
        self._update_network_path_display()

        # Restore saved state
        self._restore_state()

        # Initial validation
        self._validate_inputs()

    def on_tab_activated(self):
        """Called when tab becomes visible."""
        self._validate_inputs()

    # =========================================================================
    # NETWORK PATH DISPLAY
    # =========================================================================

    def _update_network_path_display(self):
        """Update the network path display label."""
        from settings_manager import get_comfyui_network_output_path

        network_path = get_comfyui_network_output_path()
        if network_path:
            self.ui.ComfyUINetworkPathDisplay.setText(network_path)
            self.ui.ComfyUINetworkPathDisplay.setStyleSheet("color: #aaaaaa;")
        else:
            self.ui.ComfyUINetworkPathDisplay.setText("(Not configured - set in Settings tab)")
            self.ui.ComfyUINetworkPathDisplay.setStyleSheet("color: #888888; font-style: italic;")

    # =========================================================================
    # WORKFLOW SELECTOR (for multi-workflow models)
    # =========================================================================

    def _setup_workflow_selector(self):
        """Set up the workflow selector dropdown for multi-workflow models."""
        # Create workflow selector row (hidden by default)
        self._workflow_selector_widget = QWidget()
        workflow_selector_layout = QHBoxLayout(self._workflow_selector_widget)
        workflow_selector_layout.setContentsMargins(0, 5, 0, 5)

        label = QLabel("Workflow:")
        label.setFixedWidth(100)
        workflow_selector_layout.addWidget(label)

        self._workflow_selector_combo = QtWidgets.QComboBox()
        self._workflow_selector_combo.setMinimumWidth(200)
        self._workflow_selector_combo.currentTextChanged.connect(self._on_workflow_selected)
        workflow_selector_layout.addWidget(self._workflow_selector_combo)

        workflow_selector_layout.addStretch()

        self._workflow_selector_widget.setVisible(False)

        # Insert into comfyuiWorkflowLayout after comfyuiPresetLayout
        if hasattr(self.ui, 'comfyuiWorkflowLayout'):
            # Insert after the preset info row (index 2, after buttons and preset label)
            self.ui.comfyuiWorkflowLayout.insertWidget(2, self._workflow_selector_widget)

    def _setup_note_display(self):
        """Set up the note display area for showing model/workflow notes."""
        # Create note display widget (hidden by default)
        self._note_display_widget = QWidget()
        note_layout = QHBoxLayout(self._note_display_widget)
        note_layout.setContentsMargins(0, 0, 0, 5)

        note_icon_label = QLabel("Note:")
        note_icon_label.setFixedWidth(100)
        note_icon_label.setStyleSheet("color: #4a9eff; font-weight: bold;")
        note_layout.addWidget(note_icon_label)

        self._note_display_label = QLabel("")
        self._note_display_label.setWordWrap(True)
        self._note_display_label.setStyleSheet("color: #aaaaaa; font-style: italic;")
        note_layout.addWidget(self._note_display_label, 1)

        self._note_display_widget.setVisible(False)

        # Insert into comfyuiWorkflowLayout after workflow selector (index 3)
        if hasattr(self.ui, 'comfyuiWorkflowLayout'):
            self.ui.comfyuiWorkflowLayout.insertWidget(3, self._note_display_widget)

    def _update_workflow_selector_visibility(self):
        """Update workflow selector visibility based on current preset."""
        from settings_manager import is_workflow_preset_multi, get_workflow_preset_workflows

        if not self._current_preset_name:
            self._workflow_selector_widget.setVisible(False)
            return

        is_multi = is_workflow_preset_multi(self._current_preset_name)
        self._workflow_selector_widget.setVisible(is_multi)

        if is_multi:
            # Populate workflow options
            workflows = get_workflow_preset_workflows(self._current_preset_name)
            self._workflow_selector_combo.blockSignals(True)
            self._workflow_selector_combo.clear()

            for wf_name in sorted(workflows.keys()):
                self._workflow_selector_combo.addItem(wf_name)

            # Select first workflow by default or restore previously selected
            if self._current_selected_workflow and self._current_selected_workflow in workflows:
                self._workflow_selector_combo.setCurrentText(self._current_selected_workflow)
            elif workflows:
                first_workflow = sorted(workflows.keys())[0]
                self._current_selected_workflow = first_workflow
                self._workflow_selector_combo.setCurrentText(first_workflow)

            self._workflow_selector_combo.blockSignals(False)

    def _on_workflow_selected(self, workflow_name):
        """Handle workflow selection change in multi-workflow model."""
        from settings_manager import get_comfyui_workflow_preset_path, get_workflow_config

        if not workflow_name:
            return

        self._current_selected_workflow = workflow_name

        # Get the workflow path for this selection
        workflow_path = get_comfyui_workflow_preset_path(
            self._current_preset_name,
            selected_workflow=workflow_name
        )

        if workflow_path and os.path.exists(workflow_path):
            self.ui.ComfyUIWorkflowPath.setText(workflow_path)
            self.app_state.comfyui_workflow_path = workflow_path
            self._refresh_editable_nodes()
        else:
            self.ui.ComfyUIWorkflowPath.setText(f"Workflow file not found: {workflow_path}")
            self.app_state.comfyui_workflow_path = None

        self._update_note_display()
        self._validate_inputs()
        self._save_state()

    def _update_note_display(self):
        """Update the note display based on current preset/workflow."""
        from settings_manager import get_workflow_preset_note

        if not self._current_preset_name:
            self._note_display_widget.setVisible(False)
            return

        note = get_workflow_preset_note(
            self._current_preset_name,
            selected_workflow=self._current_selected_workflow
        )

        if note:
            self._note_display_label.setText(note)
            self._note_display_widget.setVisible(True)
        else:
            self._note_display_widget.setVisible(False)

    # =========================================================================
    # GENERATION SETTINGS
    # =========================================================================

    def _on_generation_count_changed(self, value):
        """Handle generation count change."""
        self._validate_inputs()
        self._save_state()

    def _on_seed_changed(self, value):
        """Handle seed value change."""
        self._save_state()

    def _on_randomize_seed(self):
        """Generate a new random seed."""
        new_seed = random.randint(0, 2147483647)
        self.ui.ComfyUISeed.setValue(new_seed)


    # =========================================================================
    # PRESET MANAGEMENT
    # =========================================================================

    def _get_preset_display_name(self, full_name):
        """Get display name from preset name (last part after slash if present)."""
        # Support both forward and back slashes
        if '/' in full_name:
            return full_name.rsplit('/', 1)[-1]
        if '\\' in full_name:
            return full_name.rsplit('\\', 1)[-1]
        return full_name

    def _on_choose_preset_clicked(self):
        """Show popup menu with available workflow presets, grouped by folder."""
        from settings_manager import get_comfyui_workflow_presets

        menu = QMenu(self.main_window)

        presets = get_comfyui_workflow_presets()
        if not presets:
            action = menu.addAction("No presets available")
            action.setEnabled(False)
        else:
            # Group presets by folder prefix
            folders = {}  # folder_name -> [(full_name, display_name), ...]
            root_items = []  # Items without folder prefix

            for name in sorted(presets.keys()):
                # Check for folder separator (support both / and \)
                if '/' in name:
                    folder, display = name.rsplit('/', 1)
                    if folder not in folders:
                        folders[folder] = []
                    folders[folder].append((name, display))
                elif '\\' in name:
                    folder, display = name.rsplit('\\', 1)
                    if folder not in folders:
                        folders[folder] = []
                    folders[folder].append((name, display))
                else:
                    root_items.append((name, name))

            # Add root items first
            for full_name, display_name in root_items:
                action = menu.addAction(display_name)
                action.setData(full_name)
                if full_name == self._current_preset_name:
                    action.setCheckable(True)
                    action.setChecked(True)

            # Add folders as submenus
            for folder in sorted(folders.keys()):
                submenu = menu.addMenu(folder)
                for full_name, display_name in folders[folder]:
                    action = submenu.addAction(display_name)
                    action.setData(full_name)
                    if full_name == self._current_preset_name:
                        action.setCheckable(True)
                        action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.ComfyUIChoosePreset.mapToGlobal(
            self.ui.ComfyUIChoosePreset.rect().bottomLeft()
        ))

        if action and action.data():
            self._select_preset(action.data())

    def _select_preset(self, preset_name):
        """Select a workflow preset by name."""
        from settings_manager import (
            get_comfyui_workflow_preset_path,
            is_workflow_preset_multi,
            get_workflow_preset_workflows
        )

        self._current_preset_name = preset_name
        display_name = self._get_preset_display_name(preset_name)
        self.ui.ComfyUICurrentPreset.setText(display_name)

        # Check if this is a multi-workflow model
        is_multi = is_workflow_preset_multi(preset_name)

        if is_multi:
            # For multi-workflow models, update selector and select first workflow
            workflows = get_workflow_preset_workflows(preset_name)
            if workflows:
                # Reset selected workflow if switching presets
                if not self._current_selected_workflow or self._current_selected_workflow not in workflows:
                    self._current_selected_workflow = sorted(workflows.keys())[0]

                workflow_path = get_comfyui_workflow_preset_path(
                    preset_name,
                    selected_workflow=self._current_selected_workflow
                )
            else:
                workflow_path = None
                self._current_selected_workflow = None
        else:
            # Single workflow model
            self._current_selected_workflow = None
            workflow_path = get_comfyui_workflow_preset_path(preset_name)

        # Update workflow selector visibility
        self._update_workflow_selector_visibility()

        if workflow_path and os.path.exists(workflow_path):
            self.ui.ComfyUIWorkflowPath.setText(workflow_path)
            self.app_state.comfyui_workflow_path = workflow_path
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._update_note_display()
            self._save_state()
        else:
            self.ui.ComfyUICurrentPreset.setText(f"{display_name} (missing)")
            self.ui.ComfyUIWorkflowPath.setText(f"Workflow file not found: {workflow_path}")
            self.app_state.comfyui_workflow_path = None
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._update_note_display()
            # Guard for animator not being initialized yet during tab initialization
            if hasattr(self.main_window, 'animator') and self.main_window.animator:
                self.main_window.animator.show_error(f"Workflow file not found: {workflow_path}")

    def _on_add_preset_clicked(self):
        """Add a new workflow preset."""
        from settings_manager import (
            get_comfyui_workflow_presets,
            save_comfyui_workflow_preset,
            get_last_browse_directory,
            set_last_browse_directory
        )

        # Use last browsed directory for workflows
        last_dir = get_last_browse_directory("comfyui_workflow")
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window, "Select ComfyUI Workflow", last_dir or "", "ComfyUI JSON (*.json)"
        )
        if not file_path:
            return
        set_last_browse_directory("comfyui_workflow", os.path.dirname(file_path))

        # Ask for a preset name
        name, ok = QInputDialog.getText(
            self.main_window, "Add Workflow Preset",
            "Enter a name for this workflow preset:"
        )
        if not ok or not name:
            return

        name = name.strip()
        if not name:
            self.main_window.animator.show_error("Preset name cannot be empty")
            return

        # Check if preset already exists
        presets = get_comfyui_workflow_presets()
        if name in presets:
            reply = QMessageBox.question(
                self.main_window, "Overwrite Preset",
                f"Preset '{name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Ask if workflow supports iterate mode
        iteratable = QMessageBox.question(
            self.main_window, "Iterate Mode",
            "Does this workflow support Iterate mode?\n\n"
            "Iterate mode is automatically enabled when only 1 image is selected.\n"
            "It allows reviewing results and refining prompts between generations.",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes

        # Save the preset and select it
        save_comfyui_workflow_preset(name, file_path, iteratable=iteratable)
        self._select_preset(name)
        self.main_window.animator.show_success(f"Workflow preset '{name}' saved")

    def _on_edit_preset_clicked(self):
        """Edit the currently selected workflow preset."""
        from comfyui_service import extract_editable_nodes
        from settings_manager import (
            get_comfyui_workflow_presets,
            save_comfyui_workflow_preset,
            update_comfyui_workflow_preset,
            delete_comfyui_workflow_preset
        )

        if not self._current_preset_name:
            self.main_window.animator.show_error("No preset selected")
            return

        presets = get_comfyui_workflow_presets()
        preset = presets.get(self._current_preset_name, {})
        if isinstance(preset, str):
            preset = {"path": preset, "description": "", "iteratable": False, "note": "", "node_overrides": {}, "is_multi": False}

        current_name = self._current_preset_name
        current_path = preset.get("path", "")
        current_iteratable = preset.get("iteratable", False)
        current_note = preset.get("note", "")
        current_full_restart = preset.get("full_restart", False)
        current_node_overrides = preset.get("node_overrides", {})
        current_is_multi = preset.get("is_multi", False)
        current_workflows = preset.get("workflows", {})

        # Create edit dialog
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(f"Edit Model: {current_name}")
        dialog.setMinimumWidth(800)
        dialog.setMinimumHeight(750)

        layout = QVBoxLayout(dialog)

        # Preset name
        name_layout = QHBoxLayout()
        name_label = QLabel("Model Name:")
        name_edit = QLineEdit(current_name)
        name_layout.addWidget(name_label)
        name_layout.addWidget(name_edit)
        layout.addLayout(name_layout)

        # Multi-workflow checkbox
        is_multi_check = QtWidgets.QCheckBox("Multi-Workflow Model (allows multiple workflows per model)")
        is_multi_check.setChecked(current_is_multi)
        is_multi_check.setToolTip(
            "Enable this to add multiple workflows to a single model.\n"
            "Each workflow can have its own settings and note.\n"
            "A dropdown will appear in the ComfyUI tab to select which workflow to use."
        )
        layout.addWidget(is_multi_check)

        # ======== Single Workflow Section ========
        single_workflow_widget = QWidget()
        single_workflow_layout = QVBoxLayout(single_workflow_widget)
        single_workflow_layout.setContentsMargins(0, 0, 0, 0)

        # Workflow path
        path_layout = QHBoxLayout()
        path_label = QLabel("Workflow File:")
        path_edit = QLineEdit(current_path)
        browse_btn = QPushButton("Browse...")
        path_layout.addWidget(path_label)
        path_layout.addWidget(path_edit)
        path_layout.addWidget(browse_btn)
        single_workflow_layout.addLayout(path_layout)

        # Iteratable checkbox
        iteratable_check = QtWidgets.QCheckBox("Enable Iterate Mode for this workflow")
        iteratable_check.setChecked(current_iteratable)
        iteratable_check.setToolTip(
            "Iterate mode is automatically enabled when only 1 image is selected.\n"
            "It allows reviewing results and refining prompts between generations.\n"
            "This option must be enabled for the workflow to support iterate mode."
        )
        single_workflow_layout.addWidget(iteratable_check)

        # Full Restart checkbox
        full_restart_check = QtWidgets.QCheckBox("Full Restart - Completely restart ComfyUI server before each job")
        full_restart_check.setChecked(current_full_restart)
        full_restart_check.setToolTip(
            "Enable this if the model requires a clean server state.\n"
            "The ComfyUI server will be completely restarted before processing this workflow.\n"
            "This is slower but ensures consistent results for certain models."
        )
        single_workflow_layout.addWidget(full_restart_check)

        # Note field for single workflow
        note_label = QLabel("Note:")
        single_workflow_layout.addWidget(note_label)

        note_edit = QtWidgets.QPlainTextEdit()
        note_edit.setPlaceholderText("Add a note or description for this model...")
        note_edit.setPlainText(current_note)
        note_edit.setMaximumHeight(80)
        single_workflow_layout.addWidget(note_edit)

        layout.addWidget(single_workflow_widget)

        # ======== Multi-Workflow Section ========
        multi_workflow_widget = QWidget()
        multi_workflow_layout = QVBoxLayout(multi_workflow_widget)
        multi_workflow_layout.setContentsMargins(0, 0, 0, 0)

        # Model-level note for multi-workflow models
        multi_note_label = QLabel("Model Note:")
        multi_workflow_layout.addWidget(multi_note_label)

        multi_note_edit = QtWidgets.QPlainTextEdit()
        multi_note_edit.setPlaceholderText("Add a note or description for this model...")
        multi_note_edit.setPlainText(current_note)  # Use the model-level note
        multi_note_edit.setMaximumHeight(60)
        multi_workflow_layout.addWidget(multi_note_edit)

        workflows_group = QtWidgets.QGroupBox("Workflows")
        workflows_group_layout = QVBoxLayout(workflows_group)

        # Workflows list with scroll area
        workflows_scroll = QtWidgets.QScrollArea()
        workflows_scroll.setWidgetResizable(True)
        workflows_scroll.setMinimumHeight(250)
        workflows_scroll.setMaximumHeight(350)

        workflows_container = QWidget()
        workflows_list_layout = QVBoxLayout(workflows_container)
        workflows_list_layout.setContentsMargins(5, 5, 5, 5)
        workflows_list_layout.setSpacing(10)
        workflows_scroll.setWidget(workflows_container)
        workflows_group_layout.addWidget(workflows_scroll)

        # Add workflow button
        add_workflow_btn = QPushButton("+ Add Workflow")
        add_workflow_btn.setMinimumWidth(130)
        workflows_group_layout.addWidget(add_workflow_btn)

        multi_workflow_layout.addWidget(workflows_group)
        layout.addWidget(multi_workflow_widget)

        # Store workflow data for multi-workflow mode
        workflow_entries = {}  # workflow_name -> {widgets...}

        def create_workflow_entry(wf_name="", wf_config=None):
            """Create a workflow entry widget."""
            if wf_config is None:
                wf_config = {"path": "", "note": "", "iteratable": False, "full_restart": False, "node_overrides": {}}

            entry_widget = QWidget()
            entry_widget.setStyleSheet("QWidget { background-color: #2a2a2a; border-radius: 4px; }")
            entry_layout = QVBoxLayout(entry_widget)
            entry_layout.setContentsMargins(10, 10, 10, 10)

            # Header row with name and delete button
            header_row = QHBoxLayout()
            wf_name_edit = QLineEdit(wf_name)
            wf_name_edit.setPlaceholderText("Workflow name...")
            wf_name_edit.setFixedWidth(200)
            header_row.addWidget(QLabel("Name:"))
            header_row.addWidget(wf_name_edit)
            header_row.addStretch()

            delete_wf_btn = QPushButton("Remove")
            delete_wf_btn.setStyleSheet("QPushButton { color: #ef4444; }")
            delete_wf_btn.setFixedWidth(80)
            header_row.addWidget(delete_wf_btn)
            entry_layout.addLayout(header_row)

            # Path row
            path_row = QHBoxLayout()
            wf_path_edit = QLineEdit(wf_config.get("path", ""))
            wf_path_edit.setPlaceholderText("Workflow JSON file...")
            wf_browse_btn = QPushButton("Browse...")
            wf_browse_btn.setFixedWidth(90)
            path_row.addWidget(QLabel("File:"))
            path_row.addWidget(wf_path_edit)
            path_row.addWidget(wf_browse_btn)
            entry_layout.addLayout(path_row)

            # Options row
            options_row = QHBoxLayout()
            wf_iteratable = QtWidgets.QCheckBox("Iterate Mode")
            wf_iteratable.setChecked(wf_config.get("iteratable", False))
            wf_full_restart = QtWidgets.QCheckBox("Full Restart")
            wf_full_restart.setChecked(wf_config.get("full_restart", False))
            options_row.addWidget(wf_iteratable)
            options_row.addWidget(wf_full_restart)
            options_row.addStretch()
            entry_layout.addLayout(options_row)

            # Note row
            note_row = QHBoxLayout()
            wf_note_edit = QLineEdit(wf_config.get("note", ""))
            wf_note_edit.setPlaceholderText("Note for this workflow...")
            note_row.addWidget(QLabel("Note:"))
            note_row.addWidget(wf_note_edit)
            entry_layout.addLayout(note_row)

            # Editable Nodes section (collapsible)
            nodes_header_row = QHBoxLayout()
            nodes_toggle_btn = QPushButton("Show Editable Nodes")
            nodes_toggle_btn.setMinimumWidth(160)
            nodes_toggle_btn.setCheckable(True)
            nodes_toggle_btn.setChecked(False)
            nodes_header_row.addWidget(nodes_toggle_btn)
            nodes_header_row.addStretch()
            entry_layout.addLayout(nodes_header_row)

            # Nodes container (hidden by default)
            nodes_container = QWidget()
            nodes_container.setVisible(False)
            nodes_container_layout = QVBoxLayout(nodes_container)
            nodes_container_layout.setContentsMargins(0, 5, 0, 0)
            nodes_container_layout.setSpacing(4)

            # Scroll area for nodes
            nodes_scroll = QtWidgets.QScrollArea()
            nodes_scroll.setWidgetResizable(True)
            nodes_scroll.setMaximumHeight(150)
            nodes_scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: 1px solid #3c3c3c; }")

            nodes_scroll_widget = QWidget()
            nodes_scroll_layout = QVBoxLayout(nodes_scroll_widget)
            nodes_scroll_layout.setContentsMargins(5, 5, 5, 5)
            nodes_scroll_layout.setSpacing(4)
            nodes_scroll.setWidget(nodes_scroll_widget)
            nodes_container_layout.addWidget(nodes_scroll)

            entry_layout.addWidget(nodes_container)

            # Store node override widgets for this workflow
            wf_node_override_widgets = {}
            current_wf_node_overrides = wf_config.get("node_overrides", {})

            def toggle_nodes_visibility(checked):
                nodes_container.setVisible(checked)
                nodes_toggle_btn.setText("Hide Editable Nodes" if checked else "Show Editable Nodes")
                if checked and nodes_scroll_layout.count() == 0:
                    # Refresh nodes when first shown
                    refresh_wf_editable_nodes()

            nodes_toggle_btn.toggled.connect(toggle_nodes_visibility)

            def refresh_wf_editable_nodes():
                """Refresh the editable nodes list for this workflow."""
                # Clear existing widgets
                while nodes_scroll_layout.count():
                    item = nodes_scroll_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                wf_node_override_widgets.clear()

                workflow_path = wf_path_edit.text().strip()
                if not workflow_path or not os.path.exists(workflow_path):
                    no_nodes_label = QLabel("No workflow selected or file not found")
                    no_nodes_label.setStyleSheet("color: #888; font-style: italic;")
                    nodes_scroll_layout.addWidget(no_nodes_label)
                    return

                editable_nodes = extract_editable_nodes(workflow_path)
                if not editable_nodes:
                    no_nodes_label = QLabel("No editable nodes found")
                    no_nodes_label.setStyleSheet("color: #888; font-style: italic;")
                    nodes_scroll_layout.addWidget(no_nodes_label)
                    return

                for node in editable_nodes:
                    override = current_wf_node_overrides.get(node.title, {})
                    is_enabled = override.get("enabled", True)
                    default_value = override.get("default_value", "")

                    node_row = QWidget()
                    node_row_layout = QHBoxLayout(node_row)
                    node_row_layout.setContentsMargins(0, 0, 0, 0)
                    node_row_layout.setSpacing(6)

                    enable_check = QtWidgets.QCheckBox()
                    enable_check.setChecked(is_enabled)
                    enable_check.setToolTip("Show this node in the UI")
                    enable_check.setFixedWidth(20)
                    node_row_layout.addWidget(enable_check)

                    type_indicator = f" ({node.widget_type})" if node.widget_type != 'text' else ""
                    node_name_label = QLabel(f"{node.display_name}{type_indicator}")
                    node_name_label.setFixedWidth(150)
                    node_name_label.setStyleSheet("color: #ccc;")
                    node_row_layout.addWidget(node_name_label)

                    if node.widget_type in ('text', 'string'):
                        default_input = QLineEdit()
                        default_input.setPlaceholderText("Default value...")
                        default_input.setText(default_value)
                        default_input.setStyleSheet("background-color: #2a2a2a;")
                        node_row_layout.addWidget(default_input, 1)
                    else:
                        default_input = None
                        spacer = QLabel("")
                        node_row_layout.addWidget(spacer, 1)

                    nodes_scroll_layout.addWidget(node_row)
                    wf_node_override_widgets[node.title] = {
                        "enable_check": enable_check,
                        "default_input": default_input,
                        "node": node
                    }

                nodes_scroll_layout.addStretch()

            # Generate unique key for this entry
            import uuid
            entry_key = str(uuid.uuid4())[:8]

            # Store widgets
            workflow_entries[entry_key] = {
                "widget": entry_widget,
                "name_edit": wf_name_edit,
                "path_edit": wf_path_edit,
                "iteratable": wf_iteratable,
                "full_restart": wf_full_restart,
                "note_edit": wf_note_edit,
                "node_overrides": current_wf_node_overrides,
                "node_override_widgets": wf_node_override_widgets,
                "refresh_nodes": refresh_wf_editable_nodes,
            }

            # Connect browse button
            def browse_wf():
                last_dir = os.path.dirname(wf_path_edit.text()) if wf_path_edit.text() else ""
                file_path, _ = QFileDialog.getOpenFileName(
                    dialog, "Select ComfyUI Workflow", last_dir, "ComfyUI JSON (*.json)"
                )
                if file_path:
                    wf_path_edit.setText(file_path)
                    # Refresh nodes if visible
                    if nodes_container.isVisible():
                        refresh_wf_editable_nodes()

            wf_browse_btn.clicked.connect(browse_wf)

            # Connect delete button
            def delete_entry():
                entry_widget.deleteLater()
                if entry_key in workflow_entries:
                    del workflow_entries[entry_key]

            delete_wf_btn.clicked.connect(delete_entry)

            return entry_widget

        def add_workflow_entry():
            """Add a new empty workflow entry."""
            entry = create_workflow_entry()
            workflows_list_layout.insertWidget(workflows_list_layout.count(), entry)

        add_workflow_btn.clicked.connect(add_workflow_entry)

        # Populate existing workflows
        for wf_name, wf_config in current_workflows.items():
            entry = create_workflow_entry(wf_name, wf_config)
            workflows_list_layout.addWidget(entry)

        # Add at least one empty entry if no workflows exist
        if not current_workflows:
            add_workflow_entry()

        workflows_list_layout.addStretch()

        def browse_workflow():
            last_dir = os.path.dirname(path_edit.text()) if path_edit.text() else ""
            file_path, _ = QFileDialog.getOpenFileName(
                dialog, "Select ComfyUI Workflow", last_dir, "ComfyUI JSON (*.json)"
            )
            if file_path:
                path_edit.setText(file_path)
                refresh_editable_nodes_list()

        browse_btn.clicked.connect(browse_workflow)

        # Toggle visibility based on multi-workflow mode
        def update_mode_visibility():
            is_multi = is_multi_check.isChecked()
            single_workflow_widget.setVisible(not is_multi)
            multi_workflow_widget.setVisible(is_multi)

        is_multi_check.stateChanged.connect(lambda: update_mode_visibility())
        update_mode_visibility()

        # Editable Nodes section (only for single workflow mode)
        nodes_group = QtWidgets.QGroupBox("Editable Nodes")
        nodes_group_layout = QVBoxLayout(nodes_group)

        nodes_info_label = QLabel("Configure which nodes appear in the UI and set default values:")
        nodes_info_label.setStyleSheet("color: #888; font-size: 11px;")
        nodes_group_layout.addWidget(nodes_info_label)

        # Scroll area for editable nodes
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(120)
        scroll_area.setMaximumHeight(180)

        nodes_container = QWidget()
        nodes_scroll_layout = QVBoxLayout(nodes_container)
        nodes_scroll_layout.setContentsMargins(5, 5, 5, 5)
        nodes_scroll_layout.setSpacing(8)

        scroll_area.setWidget(nodes_container)
        nodes_group_layout.addWidget(scroll_area)
        single_workflow_layout.addWidget(nodes_group)

        # Store node override widgets for retrieval
        node_override_widgets = {}

        def refresh_editable_nodes_list():
            """Refresh the list of editable nodes from the workflow."""
            # Clear existing widgets
            while nodes_scroll_layout.count():
                item = nodes_scroll_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            node_override_widgets.clear()

            workflow_path = path_edit.text().strip()
            if not workflow_path or not os.path.exists(workflow_path):
                no_nodes_label = QLabel("No workflow selected or file not found")
                no_nodes_label.setStyleSheet("color: #888; font-style: italic;")
                nodes_scroll_layout.addWidget(no_nodes_label)
                return

            editable_nodes = extract_editable_nodes(workflow_path)
            if not editable_nodes:
                no_nodes_label = QLabel("No editable nodes found in this workflow")
                no_nodes_label.setStyleSheet("color: #888; font-style: italic;")
                nodes_scroll_layout.addWidget(no_nodes_label)
                return

            for node in editable_nodes:
                # Get existing override for this node
                override = current_node_overrides.get(node.title, {})
                is_enabled = override.get("enabled", True)
                default_value = override.get("default_value", "")

                # Create row for this node
                node_row = QWidget()
                node_row_layout = QHBoxLayout(node_row)
                node_row_layout.setContentsMargins(0, 0, 0, 0)
                node_row_layout.setSpacing(8)

                # Checkbox to enable/disable
                enable_check = QtWidgets.QCheckBox()
                enable_check.setChecked(is_enabled)
                enable_check.setToolTip("Show this node in the UI")
                enable_check.setFixedWidth(20)
                node_row_layout.addWidget(enable_check)

                # Node name label with type indicator
                type_indicator = f" ({node.widget_type})" if node.widget_type != 'text' else ""
                node_name_label = QLabel(f"{node.display_name}{type_indicator}")
                node_name_label.setFixedWidth(180)
                node_name_label.setToolTip(f"Node: {node.title}\nType: {node.node_type}\nWidget: {node.widget_type}")
                node_row_layout.addWidget(node_name_label)

                # Default value input - show for text and string nodes
                if node.widget_type in ('text', 'string'):
                    default_input = QLineEdit()
                    default_input.setPlaceholderText("Leave blank to keep unchanged")
                    default_input.setText(default_value)
                    default_input.setToolTip("Default value to pre-fill (leave empty to use workflow default)")
                    node_row_layout.addWidget(default_input, 1)
                else:
                    # For non-text nodes, add a spacer/placeholder
                    default_input = None
                    spacer = QLabel("")
                    node_row_layout.addWidget(spacer, 1)

                nodes_scroll_layout.addWidget(node_row)

                # Store reference for later retrieval
                node_override_widgets[node.title] = {
                    "enable_check": enable_check,
                    "default_input": default_input,
                    "node": node
                }

            # Add stretch at end
            nodes_scroll_layout.addStretch()

        # Initial population of editable nodes
        refresh_editable_nodes_list()

        # Buttons layout with Delete on the left, OK/Cancel on the right
        buttons_layout = QHBoxLayout()

        # Delete button (left side, styled red)
        delete_btn = QPushButton("Delete Model")
        delete_btn.setStyleSheet("QPushButton { color: #ef4444; }")
        delete_btn.setToolTip("Permanently delete this workflow preset")

        def on_delete():
            reply = QMessageBox.question(
                dialog, "Delete Model",
                f"Are you sure you want to delete '{current_name}'?\n\nThis cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                dialog.done(2)  # Custom return code for delete

        delete_btn.clicked.connect(on_delete)
        buttons_layout.addWidget(delete_btn)

        buttons_layout.addStretch()

        # OK/Cancel buttons (right side)
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        buttons_layout.addWidget(button_box)

        layout.addLayout(buttons_layout)

        result = dialog.exec_()

        # Handle delete (custom return code 2)
        if result == 2:
            delete_comfyui_workflow_preset(current_name)
            self._current_preset_name = None
            self._current_selected_workflow = None
            self.ui.ComfyUICurrentPreset.setText("No model selected")
            self.ui.ComfyUIWorkflowPath.setText("No workflow selected")
            self.app_state.comfyui_workflow_path = None
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._update_workflow_selector_visibility()
            self._update_note_display()
            self.main_window.animator.show_info(f"Model '{current_name}' deleted")
            return

        if result == QDialog.Accepted:
            new_name = name_edit.text().strip()
            new_is_multi = is_multi_check.isChecked()

            if not new_name:
                self.main_window.animator.show_error("Preset name cannot be empty")
                return

            if new_is_multi:
                # Collect workflows from entries
                new_workflows = {}
                for entry_key, entry_data in workflow_entries.items():
                    wf_name = entry_data["name_edit"].text().strip()
                    wf_path = entry_data["path_edit"].text().strip()
                    if wf_name and wf_path:  # Only include if both name and path are set
                        # Collect node overrides from widgets if they were populated
                        wf_node_overrides = {}
                        node_override_widgets = entry_data.get("node_override_widgets", {})
                        if node_override_widgets:
                            for node_title, widgets in node_override_widgets.items():
                                is_enabled = widgets["enable_check"].isChecked()
                                default_input = widgets["default_input"]
                                default_value = default_input.text().strip() if default_input else ""
                                if not is_enabled or default_value:
                                    wf_node_overrides[node_title] = {
                                        "enabled": is_enabled,
                                        "default_value": default_value
                                    }
                        else:
                            # Use existing node_overrides if widgets weren't shown
                            wf_node_overrides = entry_data.get("node_overrides", {})

                        new_workflows[wf_name] = {
                            "path": wf_path,
                            "note": entry_data["note_edit"].text().strip(),
                            "iteratable": entry_data["iteratable"].isChecked(),
                            "full_restart": entry_data["full_restart"].isChecked(),
                            "node_overrides": wf_node_overrides,
                        }

                if not new_workflows:
                    self.main_window.animator.show_error("Please add at least one workflow with name and path")
                    return

                # Get the first workflow path as default for compatibility
                first_wf = list(new_workflows.values())[0]
                new_path = first_wf["path"]
                new_note = multi_note_edit.toPlainText().strip()  # Model-level note
                new_iteratable = False
                new_full_restart = False
                new_node_overrides = {}
            else:
                # Single workflow mode
                new_path = path_edit.text().strip()
                new_iteratable = iteratable_check.isChecked()
                new_note = note_edit.toPlainText().strip()
                new_full_restart = full_restart_check.isChecked()
                new_workflows = None

                # Collect node overrides from widgets
                new_node_overrides = {}
                for node_title, widgets in node_override_widgets.items():
                    is_enabled = widgets["enable_check"].isChecked()
                    default_input = widgets["default_input"]
                    default_value = default_input.text().strip() if default_input else ""
                    if not is_enabled or default_value:
                        new_node_overrides[node_title] = {
                            "enabled": is_enabled,
                            "default_value": default_value
                        }

                if not new_path:
                    self.main_window.animator.show_error("Workflow path cannot be empty")
                    return

            # Check if name changed and new name already exists
            if new_name != current_name:
                if new_name in presets:
                    self.main_window.animator.show_error(f"A preset named '{new_name}' already exists")
                    return

                # Delete old preset and create new one with new name
                delete_comfyui_workflow_preset(current_name)
                save_comfyui_workflow_preset(
                    new_name, new_path,
                    iteratable=new_iteratable,
                    note=new_note,
                    full_restart=new_full_restart,
                    node_overrides=new_node_overrides,
                    is_multi=new_is_multi,
                    workflows=new_workflows
                )
                self._current_preset_name = new_name
                self._current_selected_workflow = None
                self.ui.ComfyUICurrentPreset.setText(self._get_preset_display_name(new_name))
                self.main_window.animator.show_success(f"Preset renamed to '{new_name}'")
            else:
                # Just update the existing preset
                update_comfyui_workflow_preset(
                    current_name,
                    workflow_path=new_path,
                    iteratable=new_iteratable,
                    note=new_note,
                    full_restart=new_full_restart,
                    node_overrides=new_node_overrides,
                    is_multi=new_is_multi,
                    workflows=new_workflows
                )
                self.main_window.animator.show_success(f"Preset '{current_name}' updated")

            # Refresh the UI with the (possibly new) preset name
            self._current_selected_workflow = None
            self._select_preset(self._current_preset_name)

    # =========================================================================
    # EDITABLE NODES
    # =========================================================================

    def _refresh_editable_nodes(self):
        """Refresh dynamic UI widgets based on editable nodes in the workflow."""
        from comfyui_service import extract_editable_nodes
        from settings_manager import get_comfyui_workflow_presets, get_workflow_config

        # Clear layout
        layout = self.ui.comfyuiEditableNodesLayout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._comfyui_dynamic_widgets = {}
        self._comfyui_condition_map = {}  # Maps condition_node_name -> list of dependent widgets

        if not self.app_state.comfyui_workflow_path:
            return

        # Get node overrides from current preset (supports both single and multi-workflow)
        node_overrides = {}
        if self._current_preset_name:
            config = get_workflow_config(
                self._current_preset_name,
                selected_workflow=self._current_selected_workflow
            )
            if config:
                node_overrides = config.get("node_overrides", {})

        editable_nodes = extract_editable_nodes(self.app_state.comfyui_workflow_path)

        # First pass: create all widgets (skip disabled nodes)
        for node in editable_nodes:
            # Check if this node is disabled via overrides
            override = node_overrides.get(node.title, {})
            if not override.get("enabled", True):
                # Node is disabled, skip it
                continue

            # Apply default value override if present (for text and string nodes)
            default_value = override.get("default_value", "")
            if default_value and node.widget_type in ('text', 'string'):
                # Override the current_value with the default
                node.current_value = default_value

            widget = self._create_editable_node_widget(node)
            if widget:
                layout.addWidget(widget)
                self._comfyui_dynamic_widgets[node.node_id] = widget
                # Store the node info on the widget for condition handling
                widget.editable_node = node

        # Second pass: set up conditional visibility connections
        for node in editable_nodes:
            # Skip disabled nodes
            override = node_overrides.get(node.title, {})
            if not override.get("enabled", True):
                continue

            if node.condition_node:
                # Find the toggle widget that controls this node's visibility
                toggle_widget = self._find_toggle_widget_by_name(node.condition_node)
                if toggle_widget:
                    # Register this widget as dependent on the toggle
                    if node.condition_node not in self._comfyui_condition_map:
                        self._comfyui_condition_map[node.condition_node] = []
                    self._comfyui_condition_map[node.condition_node].append(node.node_id)

                    # Set initial visibility based on toggle state
                    dependent_widget = self._comfyui_dynamic_widgets.get(node.node_id)
                    if dependent_widget and hasattr(toggle_widget, 'input_widget'):
                        checkbox = toggle_widget.input_widget
                        if hasattr(checkbox, 'isChecked'):
                            dependent_widget.setVisible(checkbox.isChecked())

        # Apply any pending editable values from restored state
        self._apply_pending_editable_values()

    def _find_toggle_widget_by_name(self, condition_name):
        """Find a toggle widget by the condition node name."""
        for node_id, widget in self._comfyui_dynamic_widgets.items():
            node = getattr(widget, 'editable_node', None)
            if node:
                # Match by display name (base title without _editable)
                # The condition_name is the base title of the controlling node
                is_edit, base_title, _ = self._parse_node_title(node.title)
                if base_title == condition_name:
                    return widget
        return None

    def _parse_node_title(self, title):
        """Parse node title for editable marker and condition (mirrors comfyui_service logic)."""
        editable_markers = ['_editable', '_editble']
        is_editable = False
        condition_node = None
        base_title = title

        for marker in editable_markers:
            if marker in title:
                is_editable = True
                parts = title.split(marker)
                base_title = parts[0]
                if len(parts) > 1:
                    after_marker = parts[1]
                    for sep in ['@if_', '&if_']:
                        if after_marker.startswith(sep):
                            condition_node = after_marker[len(sep):]
                            break
                break

        return is_editable, base_title, condition_node

    def _on_toggle_changed(self, checked, toggle_node_name):
        """Handle toggle widget state change - update visibility of dependent widgets."""
        dependent_node_ids = self._comfyui_condition_map.get(toggle_node_name, [])
        for node_id in dependent_node_ids:
            widget = self._comfyui_dynamic_widgets.get(node_id)
            if widget:
                widget.setVisible(checked)
        self._save_state()

    def _create_editable_node_widget(self, node):
        """Create a widget for an editable node."""
        from ui_components import BatchImageSelector
        from spell_checker import SpellCheckTextEdit
        from settings_manager import get_last_browse_directory

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 5, 0, 5)

        if node.widget_type == 'toggle':
            # Toggle/switch widget - displayed as checkbox
            # Parse the base name for the toggle label
            _, base_title, _ = self._parse_node_title(node.title)
            toggle_name = base_title.replace('_', ' ')

            input_widget = QtWidgets.QCheckBox(toggle_name)
            # Index 0 = unchecked (first input), Index 1 = checked (second input)
            # For switch nodes, value != 0 means use second input
            is_checked = bool(node.current_value) if node.current_value else False
            input_widget.setChecked(is_checked)

            # Connect to toggle change handler
            input_widget.stateChanged.connect(
                lambda state, name=base_title: self._on_toggle_changed(state != 0, name)
            )
            layout.addWidget(input_widget)
            container.input_widget = input_widget
            container.toggle_name = base_title  # Store for condition matching

        elif node.widget_type == '3d_model':
            # 3D model selector - file browser for GLB/OBJ/FBX files
            label = QLabel(f"{node.display_name}:")
            layout.addWidget(label)

            file_row = QHBoxLayout()
            file_path_edit = QLineEdit()
            file_path_edit.setPlaceholderText("Select a 3D model file (GLB, OBJ, FBX)...")
            if node.current_value:
                file_path_edit.setText(str(node.current_value))
            file_row.addWidget(file_path_edit)

            browse_btn = QPushButton("Browse...")
            browse_btn.setFixedWidth(80)
            browse_btn.clicked.connect(
                lambda checked=False, edit=file_path_edit: self._browse_3d_model(edit)
            )
            file_row.addWidget(browse_btn)
            layout.addLayout(file_row)

            file_path_edit.textChanged.connect(self._on_text_changed)
            container.input_widget = file_path_edit

        elif node.widget_type == 'text':
            label = QLabel(f"{node.display_name}:")
            layout.addWidget(label)

            # Add preset row with button
            preset_row = QHBoxLayout()
            preset_btn = QPushButton("Presets")
            preset_btn.setFixedWidth(100)
            preset_row.addWidget(preset_btn)
            preset_row.addStretch()
            layout.addLayout(preset_row)

            # Text input with spell checking
            input_widget = SpellCheckTextEdit()
            input_widget.setMinimumHeight(60)
            if node.current_value:
                input_widget.setPlainText(str(node.current_value))
            layout.addWidget(input_widget)
            container.input_widget = input_widget
            container.node_type = node.node_type  # Store node type for preset lookup

            # Connect preset button to show popup menu
            preset_btn.clicked.connect(
                lambda checked=False, w=input_widget, btn=preset_btn, nt=node.node_type: self._on_prompt_preset_clicked(w, btn, nt)
            )
            # Save state when text changes (with delay)
            input_widget.textChanged.connect(self._on_text_changed)

        elif node.widget_type == 'image':
            label = QLabel(f"{node.display_name}:")
            layout.addWidget(label)

            input_widget = BatchImageSelector()
            # Set last browse directory for image selector
            last_dir = get_last_browse_directory("comfyui_images")
            if last_dir:
                input_widget.set_last_browse_dir(last_dir)
            # Save directory when images are added
            input_widget.images_changed.connect(self._on_images_changed)
            layout.addWidget(input_widget)
            container.input_widget = input_widget

        else:
            # Default: generic line edit for strings, ints, floats
            label = QLabel(f"{node.display_name}:")
            layout.addWidget(label)

            input_widget = QLineEdit()
            if node.current_value:
                input_widget.setText(str(node.current_value))
            input_widget.textChanged.connect(self._on_text_changed)
            layout.addWidget(input_widget)
            container.input_widget = input_widget

        return container

    def _browse_3d_model(self, line_edit):
        """Open file browser for 3D model selection."""
        from settings_manager import get_last_browse_directory, set_last_browse_directory

        last_dir = get_last_browse_directory("comfyui_3d_models") or ""
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Select 3D Model",
            last_dir,
            "3D Models (*.glb *.gltf *.obj *.fbx *.usd *.usda *.usdc *.usdz);;All Files (*)"
        )
        if file_path:
            line_edit.setText(file_path)
            set_last_browse_directory("comfyui_3d_models", os.path.dirname(file_path))

    def _apply_pending_editable_values(self):
        """Apply pending editable values that were saved from a previous session."""
        if not self._pending_editable_values:
            return

        for node_id_str, value in self._pending_editable_values.items():
            try:
                node_id = int(node_id_str)
                if node_id in self._comfyui_dynamic_widgets:
                    container = self._comfyui_dynamic_widgets[node_id]
                    input_widget = getattr(container, 'input_widget', None)
                    if input_widget:
                        if hasattr(input_widget, 'setPlainText'):
                            input_widget.setPlainText(value)
                        elif hasattr(input_widget, 'setText'):
                            input_widget.setText(value)
            except (ValueError, AttributeError) as e:
                self.log(f"Could not restore value for node {node_id_str}: {e}")

        # Clear pending values after applying
        self._pending_editable_values = {}

    # =========================================================================
    # PROMPT PRESETS
    # =========================================================================

    def _on_prompt_preset_clicked(self, text_widget, button, node_type):
        """Show popup menu for prompt presets (per-node-type)."""
        from settings_manager import get_comfyui_prompt_presets_for_node_type

        menu = QMenu(self.main_window)

        # Get presets for this node type
        presets = get_comfyui_prompt_presets_for_node_type(node_type)

        # Add preset items
        if presets:
            for name in sorted(presets.keys()):
                action = menu.addAction(name)
                action.triggered.connect(
                    lambda checked=False, n=name, w=text_widget, nt=node_type: self._apply_prompt_preset(n, w, nt)
                )
            menu.addSeparator()
        else:
            no_presets = menu.addAction("No presets saved")
            no_presets.setEnabled(False)
            menu.addSeparator()

        # Add save/delete options
        save_action = menu.addAction("Save Current...")
        save_action.triggered.connect(
            lambda checked=False, w=text_widget, nt=node_type: self._save_prompt_preset(w, nt)
        )

        if presets:
            delete_menu = menu.addMenu("Delete...")
            for name in sorted(presets.keys()):
                delete_action = delete_menu.addAction(name)
                delete_action.triggered.connect(
                    lambda checked=False, n=name, nt=node_type: self._delete_prompt_preset(n, nt)
                )

        menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))

    def _apply_prompt_preset(self, preset_name, text_widget, node_type):
        """Apply a prompt preset to the text widget."""
        from settings_manager import get_comfyui_prompt_presets_for_node_type

        presets = get_comfyui_prompt_presets_for_node_type(node_type)
        if preset_name in presets:
            text_widget.setPlainText(presets[preset_name])

    def _save_prompt_preset(self, text_widget, node_type):
        """Save current text as a new prompt preset for the node type."""
        from settings_manager import save_comfyui_prompt_preset_for_node_type

        current_text = text_widget.toPlainText().strip()
        if not current_text:
            self.main_window.animator.show_error("Cannot save empty preset")
            return

        # Make node type more readable for display
        display_type = node_type.replace('Plus', '+')

        dialog = QInputDialog(self.main_window)
        dialog.setWindowTitle("Save Prompt Preset")
        dialog.setLabelText(f"Preset name (for {display_type} nodes):")
        dialog.setTextValue("")
        dialog.setWindowModality(Qt.WindowModal)

        if dialog.exec_() == QInputDialog.Accepted:
            name = dialog.textValue().strip()
            if not name:
                self.main_window.animator.show_error("Preset name cannot be empty")
                return
            save_comfyui_prompt_preset_for_node_type(node_type, name, current_text)
            self.main_window.animator.show_success(f"Preset '{name}' saved")

    def _delete_prompt_preset(self, preset_name, node_type):
        """Delete a prompt preset for a node type."""
        from settings_manager import delete_comfyui_prompt_preset_for_node_type

        # Make node type more readable for display
        display_type = node_type.replace('Plus', '+')

        reply = QMessageBox.question(
            self.main_window, "Delete Preset",
            f"Delete prompt preset '{preset_name}' from {display_type} nodes?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            delete_comfyui_prompt_preset_for_node_type(node_type, preset_name)
            self.main_window.animator.show_info(f"Preset '{preset_name}' deleted")

    # =========================================================================
    # TEXT/IMAGE CHANGE HANDLERS
    # =========================================================================

    def _on_text_changed(self):
        """Handle text change in editable nodes - save state with debounce."""
        if not hasattr(self, '_save_timer'):
            self._save_timer = QTimer(self.main_window)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._save_state)
        # Restart timer on each change (500ms debounce)
        self._save_timer.start(500)

    def _on_images_changed(self, images):
        """Handle image selection changes - save the last browse directory."""
        from settings_manager import set_last_browse_directory

        if images:
            last_dir = os.path.dirname(images[0])
            set_last_browse_directory("comfyui_images", last_dir)

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_inputs(self):
        """Validate inputs and enable/disable submit button."""
        from settings_manager import get_comfyui_network_output_path

        workflow_ok = bool(self.app_state.comfyui_workflow_path)
        network_path_ok = bool(get_comfyui_network_output_path())
        self.ui.ComfyUISubmit.setEnabled(workflow_ok and network_path_ok)

    # =========================================================================
    # SUBMISSION
    # =========================================================================

    def _on_submit_clicked(self):
        """Submit the workflow to ComfyUI/Deadline."""
        from ui_components import Worker, StatusColors
        from comfyui_service import extract_editable_nodes, submit_comfyui_job
        from settings_manager import get_comfyui_network_output_path, get_workflow_config

        # Validate workflow
        if not self.app_state.comfyui_workflow_path:
            self.main_window.animator.show_error("No workflow selected")
            return

        # Get network output path - always use user subfolder
        network_output_dir = get_comfyui_network_output_path()
        if not network_output_dir:
            self.main_window.animator.show_error("Network output path not configured in Settings")
            return

        network_output_dir = os.path.join(network_output_dir, self.app_state.user)
        self.log(f"[ComfyUI] Using user subfolder: {network_output_dir}")

        # Get generation count from UI
        generation_count = self.ui.ComfyUIGenerationCount.value()

        # Collect editable values from dynamic widgets
        editable_values = {}
        editable_nodes = extract_editable_nodes(self.app_state.comfyui_workflow_path)
        selected_image_count = 0  # Track number of selected images for auto iterate mode

        for node in editable_nodes:
            node_id = node.node_id
            if node_id in self._comfyui_dynamic_widgets:
                container = self._comfyui_dynamic_widgets[node_id]
                input_widget = getattr(container, 'input_widget', None)
                if input_widget:
                    if node.widget_type == 'text':
                        value = input_widget.toPlainText().strip()
                    elif node.widget_type == 'image':
                        value = getattr(input_widget, 'selected_files', [])
                        selected_image_count = max(selected_image_count, len(value) if value else 0)
                    else:
                        value = input_widget.text().strip() if hasattr(input_widget, 'text') else str(node.current_value)

                    editable_values[node_id] = {'node': node, 'value': value}

        # Get workflow config (supports both single and multi-workflow models)
        workflow_config = get_workflow_config(
            self._current_preset_name,
            selected_workflow=self._current_selected_workflow
        ) if self._current_preset_name else None

        # Auto-determine iterate mode: enabled when only 1 image selected AND workflow supports it
        workflow_is_iteratable = workflow_config.get("iteratable", False) if workflow_config else False
        use_iterate_mode = workflow_is_iteratable and selected_image_count == 1
        self.app_state.comfyui_iterate_mode = use_iterate_mode

        if use_iterate_mode:
            self.log(f"[ComfyUI] Iterate mode enabled (1 image selected, workflow supports iteration)")
        else:
            self.log(f"[ComfyUI] Batch mode ({selected_image_count} images selected)")

        # Build job name from shot/project
        job_name = f"{self.app_state.shot}_luma_tools" if self.app_state.shot else "luma_tools_job"

        # Show status bar progress (no overlay so user can still interact)
        self.main_window.start_status_spinner()
        self.main_window.animator.update_status_animated(
            f"🎨 ComfyUI: Preparing {generation_count} generation(s)...",
            StatusColors.INFO
        )
        self.main_window.animator.animate_button_click(self.ui.ComfyUISubmit)

        # Server mode is always enabled (persistent ComfyUI)
        use_server_mode = True

        # Get seed value
        base_seed = self.ui.ComfyUISeed.value()

        self.log(f"[ComfyUI] Network output path: {network_output_dir}")

        def on_result(result):
            """Called when submission completes."""
            # Stop spinner only if no jobs were submitted (polling will handle spinner otherwise)
            job_ids, error_msg = result

            if job_ids:
                job_count = len(job_ids)
                total_gens = job_count * generation_count
                self.main_window.animator.show_success(f"Submitted {job_count} job(s), {total_gens} generations")
                self.main_window.animator.update_status_animated(
                    f"ComfyUI: {job_count} job(s) submitted",
                    StatusColors.SUCCESS
                )
                self.log(f"ComfyUI submission complete: {job_ids}")

                # Start polling for job completion
                if self.app_state.comfyui_iterate_mode and len(job_ids) == 1:
                    self._start_iterate_polling(job_ids[0], network_output_dir)
                else:
                    self._start_batch_polling(job_ids, network_output_dir)
            else:
                self.main_window.stop_status_spinner()
                self.main_window.animator.show_error(f"Submission failed: {error_msg}")
                self.main_window.animator.update_status_animated(
                    f"ComfyUI failed: {error_msg}",
                    StatusColors.ERROR
                )

        def on_error(error_msg, traceback_str):
            """Called when submission fails."""
            self.main_window.stop_status_spinner()
            self.main_window.animator.show_error(f"Submission error: {error_msg}")
            self.main_window.animator.update_status_animated(
                f"ComfyUI error: {error_msg}",
                StatusColors.ERROR
            )
            self.log(f"ComfyUI submission error: {error_msg}")
            self.log(traceback_str)

        def on_progress(progress, message):
            """Called for progress updates - show in status bar."""
            self.main_window.animator.update_status_animated(
                f"🎨 ComfyUI: {message}",
                StatusColors.INFO
            )

        # Get full_restart from workflow config
        full_restart = workflow_config.get("full_restart", False) if workflow_config else False

        # Create worker and run submission on background thread
        worker = Worker(
            submit_comfyui_job,
            workflow_path=self.app_state.comfyui_workflow_path,
            input_image=None,
            prompt=None,
            output_dir=network_output_dir,
            generation_count=generation_count,
            job_name=job_name,
            editable_values=editable_values,
            use_server_mode=use_server_mode,
            base_seed=base_seed,
            network_output_dir=network_output_dir,
            workflow_preset=self._current_preset_name,
            full_restart=full_restart,
        )
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(on_progress)
        QThreadPool.globalInstance().start(worker)

    # =========================================================================
    # POLLING METHODS - See comfyui_polling.py (PollingMixin)
    # =========================================================================
    # The following methods are provided by PollingMixin:
    # - _start_iterate_polling, _poll_iterate_job, _on_iterate_poll_result
    # - _stop_iterate_polling, _on_iterate_job_completed, _on_use_as_input_clicked
    # - _start_batch_polling, _poll_batch_jobs, _on_batch_poll_result_collected
    # - _process_collected_poll_results, _stop_batch_polling, _on_batch_jobs_completed
    # - _on_cancel_jobs_clicked, _on_cancel_complete, _on_cancel_error
    # - _update_cancel_button_visibility

    # =========================================================================
    # APPLY SETTINGS FROM IMAGE METADATA
    # =========================================================================

    def apply_settings_from_metadata(self, metadata):
        """
        Apply settings from image metadata to restore the ComfyUI tab state.

        This allows users to recreate the exact configuration used to generate
        a specific image by copying settings from the gallery context menu.

        Args:
            metadata: Dictionary containing image generation metadata with keys:
                - workflow_preset: Full preset name (e.g. "folder/preset_name")
                - base_seed: The seed value used
                - generation_count: Number of generations
                - editable_values: Dict of node_id -> {display_name, value, ...}
        """
        from settings_manager import get_comfyui_workflow_presets

        if not metadata:
            self.main_window.animator.show_warning("No settings metadata found for this image")
            return

        self.log(f"[ComfyUI] Applying settings from image metadata...")

        # Restore workflow preset
        workflow_preset = metadata.get("workflow_preset")
        if workflow_preset:
            presets = get_comfyui_workflow_presets()
            if workflow_preset in presets:
                self._select_preset(workflow_preset)
                self.log(f"[ComfyUI] Applied workflow preset: {workflow_preset}")
            else:
                self.log(f"[ComfyUI] Warning: Workflow preset '{workflow_preset}' not found")
                self.main_window.animator.show_warning(
                    f"Workflow preset '{workflow_preset}' not found in settings"
                )

        # Restore seed
        base_seed = metadata.get("base_seed")
        if base_seed is not None:
            self.ui.ComfyUISeed.setValue(base_seed)
            self.log(f"[ComfyUI] Applied seed: {base_seed}")

        # Restore generation count
        gen_count = metadata.get("generation_count")
        if gen_count is not None:
            self.ui.ComfyUIGenerationCount.setValue(gen_count)
            self.log(f"[ComfyUI] Applied generation count: {gen_count}")

        # Restore editable values
        editable_values = metadata.get("editable_values")
        if editable_values:
            # Store as pending values - they'll be applied after widgets are created
            # This handles the case where preset selection triggers widget recreation
            self._pending_editable_values = {
                node_id: data.get("value", "")
                for node_id, data in editable_values.items()
            }
            # Try to apply immediately if widgets exist
            self._apply_pending_editable_values()
            self.log(f"[ComfyUI] Applied {len(editable_values)} editable value(s)")

        self.main_window.animator.show_success("Settings applied from image")

        # Switch to this tab
        self.main_window.switch_to_tab("comfyui")

    # =========================================================================
    # STATE PERSISTENCE
    # =========================================================================

    def _save_state(self):
        """Save the current ComfyUI tab state to user settings."""
        from settings_manager import save_comfyui_tab_state

        state = {
            "workflow_preset": self._current_preset_name or "",
            "selected_workflow": self._current_selected_workflow or "",  # For multi-workflow models
            "generation_count": self.ui.ComfyUIGenerationCount.value(),
            "seed": self.ui.ComfyUISeed.value(),
        }

        # Save editable node values
        editable_values = {}
        for node_id, container in self._comfyui_dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget:
                if hasattr(input_widget, 'toPlainText'):
                    editable_values[str(node_id)] = input_widget.toPlainText()
                elif hasattr(input_widget, 'text'):
                    editable_values[str(node_id)] = input_widget.text()

        state["editable_values"] = editable_values

        save_comfyui_tab_state(state)

    def _restore_state(self):
        """Restore the ComfyUI tab state from user settings."""
        from settings_manager import get_comfyui_tab_state, get_comfyui_workflow_presets

        state = get_comfyui_tab_state()
        if not state:
            return

        # Restore workflow preset selection
        preset_name = state.get("workflow_preset", "")
        selected_workflow = state.get("selected_workflow", "")

        if preset_name:
            presets = get_comfyui_workflow_presets()
            if preset_name in presets:
                # Set the selected workflow before selecting preset (for multi-workflow models)
                if selected_workflow:
                    self._current_selected_workflow = selected_workflow
                self._select_preset(preset_name)

        # Restore generation count
        gen_count = state.get("generation_count", 1)
        self.ui.ComfyUIGenerationCount.setValue(gen_count)

        # Restore seed
        seed = state.get("seed", random.randint(0, 2147483647))
        self.ui.ComfyUISeed.setValue(seed)

        # Store editable values to apply after widgets are created
        self._pending_editable_values = state.get("editable_values", {})
