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


class ComfyUITab(BaseTab):
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
        self.ui.ComfyUIChooseMode.clicked.connect(self._on_choose_mode_clicked)
        self.ui.ComfyUIUseAsInput.clicked.connect(self._on_use_as_input_clicked)

    def initialize(self):
        """Initialize ComfyUI tab."""
        # Internal state
        self._comfyui_dynamic_widgets = {}
        self._current_preset_name = None
        self._pending_editable_values = {}

        # Iterate mode state
        self._iterate_poll_timer = None
        self._iterate_network_output_dir = ""
        self._iterate_poll_count = 0
        self._iterate_completed_tasks = 0  # Track completed tasks for incremental updates
        self._iterate_total_tasks = 1  # Total tasks expected
        self._iterate_start_time = None  # For ETA calculation

        # Batch mode state
        self._batch_poll_timer = None
        self._batch_job_ids = []
        self._batch_pending_jobs = set()
        self._batch_failed_jobs = set()  # Track which jobs failed
        self._batch_completed_tasks = {}  # Track completed tasks per job for incremental updates
        self._batch_total_tasks = {}  # Total tasks per job
        self._batch_job_statuses = {}  # Current status per job (Queued, Rendering, etc.)
        self._batch_network_output_dir = ""
        self._batch_poll_count = 0
        self._batch_start_time = None  # For ETA calculation
        self._batch_generation_count = 1  # Frames per job

        # Hide iterate mode controls by default
        self._update_iterate_mode_visibility(False)

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
    # MODE SELECTION (BATCH/ITERATE)
    # =========================================================================

    def _on_choose_mode_clicked(self):
        """Show popup menu with available modes (Batch/Iterate)."""
        menu = QMenu(self.main_window)

        modes = [
            ("Batch", "Submit all images at once"),
            ("Iterate", "Submit one, review result, refine prompt")
        ]

        current_mode = self.ui.ComfyUICurrentMode.text()

        for mode_name, description in modes:
            action = menu.addAction(f"{mode_name} - {description}")
            action.setData(mode_name)
            if mode_name == current_mode:
                action.setCheckable(True)
                action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.ComfyUIChooseMode.mapToGlobal(
            self.ui.ComfyUIChooseMode.rect().bottomLeft()
        ))

        if action and action.data():
            self._select_mode(action.data())

    def _select_mode(self, mode_name):
        """Select a mode by name."""
        self.ui.ComfyUICurrentMode.setText(mode_name)

        is_iterate = mode_name == "Iterate"
        self.app_state.comfyui_iterate_mode = is_iterate
        self.log(f"[ComfyUI] Mode changed to: {mode_name}")

        # Show/hide iterate frame
        self.ui.comfyuiIterateFrame.setVisible(is_iterate)

        # In iterate mode, force generation count to 1
        if is_iterate:
            self.ui.ComfyUIGenerationCount.setValue(1)
            self.ui.ComfyUIGenerationCount.setEnabled(False)
        else:
            self.ui.ComfyUIGenerationCount.setEnabled(True)

        self._save_state()

    def _update_iterate_mode_visibility(self, show):
        """Show or hide the iterate mode controls based on workflow capability."""
        self.ui.comfyuiModeLabel.setVisible(show)
        self.ui.ComfyUIChooseMode.setVisible(show)
        self.ui.ComfyUICurrentMode.setVisible(show)

        if not show:
            # Reset to batch mode when hiding
            self.ui.ComfyUICurrentMode.setText("Batch")
            self.ui.comfyuiIterateFrame.setVisible(False)
            self.ui.ComfyUIGenerationCount.setEnabled(True)
            self.app_state.comfyui_iterate_mode = False

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
            is_workflow_preset_iteratable
        )

        workflow_path = get_comfyui_workflow_preset_path(preset_name)
        if workflow_path and os.path.exists(workflow_path):
            self._current_preset_name = preset_name
            # Display short name (last part after slash) but store full name internally
            display_name = self._get_preset_display_name(preset_name)
            self.ui.ComfyUICurrentPreset.setText(display_name)
            self.ui.ComfyUIWorkflowPath.setText(workflow_path)
            self.app_state.comfyui_workflow_path = workflow_path
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._save_state()

            # Show/hide iterate mode based on workflow's iteratable flag
            is_iteratable = is_workflow_preset_iteratable(preset_name)
            self._update_iterate_mode_visibility(is_iteratable)
        else:
            # Workflow file not found - still keep preset name so user can edit/delete it
            self._current_preset_name = preset_name
            display_name = self._get_preset_display_name(preset_name)
            self.ui.ComfyUICurrentPreset.setText(f"{display_name} (missing)")
            self.ui.ComfyUIWorkflowPath.setText(f"Workflow file not found: {workflow_path}")
            self.app_state.comfyui_workflow_path = None
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._update_iterate_mode_visibility(False)
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
            "Iterate mode allows submitting one image, reviewing the result,\n"
            "and refining the prompt before the next generation.",
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
            preset = {"path": preset, "description": "", "iteratable": False, "note": "", "node_overrides": {}}

        current_name = self._current_preset_name
        current_path = preset.get("path", "")
        current_iteratable = preset.get("iteratable", False)
        current_note = preset.get("note", "")
        current_full_restart = preset.get("full_restart", False)
        current_node_overrides = preset.get("node_overrides", {})

        # Create edit dialog
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(f"Edit Model: {current_name}")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(500)

        layout = QVBoxLayout(dialog)

        # Preset name
        name_layout = QHBoxLayout()
        name_label = QLabel("Model Name:")
        name_edit = QLineEdit(current_name)
        name_layout.addWidget(name_label)
        name_layout.addWidget(name_edit)
        layout.addLayout(name_layout)

        # Workflow path
        path_layout = QHBoxLayout()
        path_label = QLabel("Workflow File:")
        path_edit = QLineEdit(current_path)
        browse_btn = QPushButton("Browse...")
        path_layout.addWidget(path_label)
        path_layout.addWidget(path_edit)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        def browse_workflow():
            last_dir = os.path.dirname(current_path) if current_path else ""
            file_path, _ = QFileDialog.getOpenFileName(
                dialog, "Select ComfyUI Workflow", last_dir, "ComfyUI JSON (*.json)"
            )
            if file_path:
                path_edit.setText(file_path)
                # Refresh editable nodes when workflow changes
                refresh_editable_nodes_list()

        browse_btn.clicked.connect(browse_workflow)

        # Iteratable checkbox
        iteratable_check = QtWidgets.QCheckBox("Enable Iterate Mode for this workflow")
        iteratable_check.setChecked(current_iteratable)
        iteratable_check.setToolTip(
            "Iterate mode allows submitting one image, reviewing the result,\n"
            "and refining the prompt before the next generation."
        )
        layout.addWidget(iteratable_check)

        # Full Restart checkbox
        full_restart_check = QtWidgets.QCheckBox("Full Restart - Completely restart ComfyUI server before each job")
        full_restart_check.setChecked(current_full_restart)
        full_restart_check.setToolTip(
            "Enable this if the model requires a clean server state.\n"
            "The ComfyUI server will be completely restarted before processing this workflow.\n"
            "This is slower but ensures consistent results for certain models."
        )
        layout.addWidget(full_restart_check)

        # Note field
        note_label = QLabel("Note:")
        layout.addWidget(note_label)

        note_edit = QtWidgets.QPlainTextEdit()
        note_edit.setPlaceholderText("Add a note or description for this model...")
        note_edit.setPlainText(current_note)
        note_edit.setMaximumHeight(80)
        layout.addWidget(note_edit)

        # Editable Nodes section
        nodes_group = QtWidgets.QGroupBox("Editable Nodes")
        nodes_group_layout = QVBoxLayout(nodes_group)

        nodes_info_label = QLabel("Configure which nodes appear in the UI and set default values:")
        nodes_info_label.setStyleSheet("color: #888; font-size: 11px;")
        nodes_group_layout.addWidget(nodes_info_label)

        # Scroll area for editable nodes
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(150)
        scroll_area.setMaximumHeight(250)

        nodes_container = QWidget()
        nodes_scroll_layout = QVBoxLayout(nodes_container)
        nodes_scroll_layout.setContentsMargins(5, 5, 5, 5)
        nodes_scroll_layout.setSpacing(8)

        scroll_area.setWidget(nodes_container)
        nodes_group_layout.addWidget(scroll_area)
        layout.addWidget(nodes_group)

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

            # Filter to only show text-type nodes (prompts) - skip toggles, images, 3d models
            text_nodes = [n for n in editable_nodes if n.widget_type == 'text']

            if not text_nodes:
                no_nodes_label = QLabel("No text/prompt nodes found in this workflow")
                no_nodes_label.setStyleSheet("color: #888; font-style: italic;")
                nodes_scroll_layout.addWidget(no_nodes_label)
                return

            for node in text_nodes:
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

                # Node name label
                name_label = QLabel(node.display_name)
                name_label.setFixedWidth(150)
                name_label.setToolTip(f"Node: {node.title}\nType: {node.node_type}")
                node_row_layout.addWidget(name_label)

                # Default value input
                default_input = QLineEdit()
                default_input.setPlaceholderText("Leave blank to keep unchanged")
                default_input.setText(default_value)
                default_input.setToolTip("Default value to pre-fill (leave empty to use workflow default)")
                node_row_layout.addWidget(default_input, 1)

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
            self.ui.ComfyUICurrentPreset.setText("No model selected")
            self.ui.ComfyUIWorkflowPath.setText("No workflow selected")
            self.app_state.comfyui_workflow_path = None
            self._refresh_editable_nodes()
            self._validate_inputs()
            self.main_window.animator.show_info(f"Model '{current_name}' deleted")
            return

        if result == QDialog.Accepted:
            new_name = name_edit.text().strip()
            new_path = path_edit.text().strip()
            new_iteratable = iteratable_check.isChecked()
            new_note = note_edit.toPlainText().strip()
            new_full_restart = full_restart_check.isChecked()

            # Collect node overrides from widgets - always store if there's any override
            new_node_overrides = {}
            for node_title, widgets in node_override_widgets.items():
                is_enabled = widgets["enable_check"].isChecked()
                default_value = widgets["default_input"].text().strip()
                # Store override if node is disabled or has a default value set
                if not is_enabled or default_value:
                    new_node_overrides[node_title] = {
                        "enabled": is_enabled,
                        "default_value": default_value
                    }

            if not new_name:
                self.main_window.animator.show_error("Preset name cannot be empty")
                return

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
                    node_overrides=new_node_overrides
                )
                self._current_preset_name = new_name
                self.ui.ComfyUICurrentPreset.setText(new_name)
                self.main_window.animator.show_success(f"Preset renamed to '{new_name}'")
            else:
                # Just update the existing preset
                update_comfyui_workflow_preset(
                    current_name,
                    workflow_path=new_path,
                    iteratable=new_iteratable,
                    note=new_note,
                    full_restart=new_full_restart,
                    node_overrides=new_node_overrides
                )
                self.main_window.animator.show_success(f"Preset '{current_name}' updated")

            # Refresh the UI with the (possibly new) preset name
            self._select_preset(self._current_preset_name)

    # =========================================================================
    # EDITABLE NODES
    # =========================================================================

    def _refresh_editable_nodes(self):
        """Refresh dynamic UI widgets based on editable nodes in the workflow."""
        from comfyui_service import extract_editable_nodes
        from settings_manager import get_comfyui_workflow_presets

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

        # Get node overrides from current preset
        node_overrides = {}
        if self._current_preset_name:
            presets = get_comfyui_workflow_presets()
            preset = presets.get(self._current_preset_name, {})
            if isinstance(preset, dict):
                node_overrides = preset.get("node_overrides", {})

        editable_nodes = extract_editable_nodes(self.app_state.comfyui_workflow_path)

        # First pass: create all widgets (skip disabled nodes)
        for node in editable_nodes:
            # Check if this node is disabled via overrides
            override = node_overrides.get(node.title, {})
            if not override.get("enabled", True):
                # Node is disabled, skip it
                continue

            # Apply default value override if present
            default_value = override.get("default_value", "")
            if default_value and node.widget_type == 'text':
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
        from settings_manager import get_comfyui_network_output_path, is_workflow_preset_full_restart

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
                    else:
                        value = input_widget.text().strip() if hasattr(input_widget, 'text') else str(node.current_value)

                    editable_values[node_id] = {'node': node, 'value': value}

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
            full_restart=is_workflow_preset_full_restart(self._current_preset_name) if self._current_preset_name else False,
        )
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(on_progress)
        QThreadPool.globalInstance().start(worker)

    # =========================================================================
    # PROGRESS FORMATTING HELPERS
    # =========================================================================

    def _format_elapsed_time(self, seconds):
        """Format elapsed time in a human-readable way."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins}m"

    def _estimate_remaining_time(self, completed, total, elapsed_seconds):
        """Estimate remaining time based on progress."""
        if completed <= 0 or elapsed_seconds <= 0:
            return None
        rate = completed / elapsed_seconds  # tasks per second
        remaining_tasks = total - completed
        if rate > 0:
            remaining_seconds = remaining_tasks / rate
            return self._format_elapsed_time(remaining_seconds)
        return None

    # =========================================================================
    # ITERATE MODE POLLING
    # =========================================================================

    def _start_iterate_polling(self, job_id, network_output_dir):
        """Start polling for iterate mode job completion."""
        from ui_components import StatusColors

        self.app_state.comfyui_current_job_id = job_id
        self._iterate_network_output_dir = network_output_dir
        self._iterate_poll_count = 0
        self._iterate_completed_tasks = 0  # Reset task tracking
        self._iterate_total_tasks = self.ui.ComfyUIGenerationCount.value()
        self._iterate_start_time = time.time()

        self.log(f"[Iterate] Starting polling for job {job_id}")
        self.log(f"[Iterate] Network output dir: {network_output_dir}")
        self.log(f"[Iterate] Expected frames: {self._iterate_total_tasks}")

        # Start status bar spinner
        self.main_window.start_status_spinner()

        # Update UI
        self.ui.ComfyUIIterateStatus.setText("Job submitted, waiting for Deadline...")
        self.ui.ComfyUIIterateProgress.setValue(0)
        self.ui.ComfyUIUseAsInput.setEnabled(False)

        # Update main status bar with more detail
        gen_count = self._iterate_total_tasks
        self.main_window.animator.update_status_animated(
            f"🎨 ComfyUI: Submitted {gen_count} frame(s) • Waiting for worker...",
            StatusColors.INFO
        )

        # Start poll timer
        if self._iterate_poll_timer is None:
            self._iterate_poll_timer = QTimer(self.main_window)
            self._iterate_poll_timer.timeout.connect(self._poll_iterate_job)

        self._iterate_poll_timer.start(5000)  # Poll every 5 seconds

        # Also do an immediate first poll
        self._poll_iterate_job()

    def _poll_iterate_job(self):
        """Poll the iterate job status."""
        from ui_components import Worker
        from comfyui_service import poll_deadline_job_status

        job_id = self.app_state.comfyui_current_job_id
        if not job_id:
            self._stop_iterate_polling()
            return

        # Poll on worker thread, passing output_dir to verify success via output files
        output_dir = self._iterate_network_output_dir
        worker = Worker(poll_deadline_job_status, job_id, output_dir)
        worker.signals.result.connect(self._on_iterate_poll_result)
        worker.signals.error.connect(lambda msg, tb: self.log(f"Poll error: {msg}"))
        QThreadPool.globalInstance().start(worker)

    def _on_iterate_poll_result(self, result):
        """Handle iterate poll result."""
        from ui_components import StatusColors

        status = result.get("status", "Unknown")
        progress = result.get("progress", 0)
        completed_tasks = result.get("completed_tasks", 0)
        total_tasks = result.get("total_tasks", 1)
        error_message = result.get("error_message", "")

        # Use our tracked total if Deadline reports 1 (single job with multiple frames)
        display_total = max(total_tasks, self._iterate_total_tasks)

        self.log(f"[Iterate Poll] Status: {status}, Progress: {progress}%, Tasks: {completed_tasks}/{display_total}")

        # Calculate elapsed time
        elapsed = time.time() - self._iterate_start_time if self._iterate_start_time else 0
        elapsed_str = self._format_elapsed_time(elapsed)

        # Check if new tasks completed since last poll (new frames rendered)
        if completed_tasks > self._iterate_completed_tasks:
            new_frames = completed_tasks - self._iterate_completed_tasks
            self.log(f"[Iterate] {new_frames} new frame(s) rendered! ({completed_tasks}/{display_total})")
            self._iterate_completed_tasks = completed_tasks

            # Refresh gallery and request attention directly
            gallery_tab = self.main_window.get_tab("comfyui_gallery")
            if gallery_tab:
                self.log(f"[Iterate] Triggering gallery refresh and attention for new frames")
                gallery_tab._on_refresh()
                # Emit attention signal directly since we know new images were generated
                gallery_tab.signals.request_attention.emit()

        self.ui.ComfyUIIterateProgress.setValue(progress)
        self._iterate_poll_count += 1

        if status == "Completed":
            self._stop_iterate_polling()
            self._on_iterate_job_completed()
        elif status == "Failed":
            self._stop_iterate_polling()
            self.ui.ComfyUIIterateStatus.setText(f"Job failed: {error_message}")
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #ef4444;")
            self.main_window.animator.update_status_animated(
                f"❌ ComfyUI Failed: {error_message}",
                StatusColors.ERROR
            )
        else:
            # Still running - build detailed status message
            eta_str = self._estimate_remaining_time(completed_tasks, display_total, elapsed)

            if status in ("Active", "Rendering"):
                # Show progress with frame count and timing
                status_text = f"Rendering frame {completed_tasks + 1}/{display_total}"
                if completed_tasks > 0:
                    main_status = f"🎨 ComfyUI: Frame {completed_tasks}/{display_total} • {elapsed_str} elapsed"
                    if eta_str:
                        main_status += f" • ~{eta_str} remaining"
                else:
                    main_status = f"🎨 ComfyUI: Starting render • {display_total} frame(s)"
            elif status in ("Pending", "Queued"):
                status_text = f"Queued, waiting for worker..."
                main_status = f"⏳ ComfyUI: Queued • Waiting for available worker..."
            else:
                status_text = f"{status}: {progress}%"
                main_status = f"🎨 ComfyUI: {status} ({progress}%)"

            self.ui.ComfyUIIterateStatus.setText(status_text)
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #4a9eff;")
            self.main_window.animator.update_status_animated(main_status, StatusColors.INFO)

    def _stop_iterate_polling(self):
        """Stop the iterate poll timer."""
        if self._iterate_poll_timer:
            self._iterate_poll_timer.stop()
        # Stop status bar spinner
        self.main_window.stop_status_spinner()

    def _on_iterate_job_completed(self):
        """Handle iterate job completion - show the generated image."""
        from ui_components import StatusColors
        from comfyui_service import get_job_output_files, cleanup_job_temp_files

        # Calculate total time
        elapsed = time.time() - self._iterate_start_time if self._iterate_start_time else 0
        elapsed_str = self._format_elapsed_time(elapsed)
        frames = self._iterate_total_tasks

        self.ui.ComfyUIIterateStatus.setText("Completed! Looking for output...")
        self.ui.ComfyUIIterateStatus.setStyleSheet("color: #10b981;")

        self.main_window.animator.update_status_animated(
            f"✅ ComfyUI Complete: {frames} frame(s) in {elapsed_str}",
            StatusColors.SUCCESS
        )

        # Find the most recent output file in network directory (user subfolder)
        output_files = []
        network_dir = self._iterate_network_output_dir

        self.log(f"[Iterate] Looking for output files...")
        self.log(f"[Iterate] Network dir: {network_dir}")

        # Clean up temp files from network directory
        if network_dir:
            deleted = cleanup_job_temp_files(network_dir)
            if deleted:
                self.log(f"[Iterate] Cleaned up {deleted} temp files from network dir")

        # Get files from network directory
        if network_dir:
            output_files = get_job_output_files(network_dir)
            if output_files:
                self.log(f"[Iterate] Found {len(output_files)} files in network dir")

        if output_files:
            latest_image = output_files[0]
            self.app_state.comfyui_last_generated_image = latest_image
            self.log(f"[Iterate] Latest output: {latest_image}")

            self.ui.ComfyUIIterateStatus.setText("Completed!")

            # Display thumbnail in preview
            pixmap = QPixmap(latest_image)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.ui.ComfyUIIteratePreview.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.ui.ComfyUIIteratePreview.setPixmap(scaled)

            # Enable "Use as Input" button
            self.ui.ComfyUIUseAsInput.setEnabled(True)

            self.main_window.animator.show_success("Image generated! Click 'Use as Input' to iterate.")

            # Trigger gallery refresh to show new images and flash the tab
            gallery_tab = self.main_window.get_tab("comfyui_gallery")
            if gallery_tab:
                self.log("[Iterate] Triggering gallery refresh...")
                gallery_tab._on_refresh()
        else:
            self.log(f"[Iterate] No output files found in either directory")
            self.ui.ComfyUIIterateStatus.setText("No output files found")
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #f59e0b;")
            self.main_window.animator.update_status_animated(
                "Deadline: Completed but no output files found",
                StatusColors.WARNING
            )

    def _on_use_as_input_clicked(self):
        """Copy the generated image path to the input image field."""
        last_image = self.app_state.comfyui_last_generated_image
        if not last_image or not os.path.exists(last_image):
            self.main_window.animator.show_error("No generated image available")
            return

        # Find the image input widget and set the path
        for node_id, container in self._comfyui_dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget and hasattr(input_widget, 'add_images'):
                # This is a BatchImageSelector
                input_widget.clear_images()
                input_widget.add_images([last_image])
                self.main_window.animator.show_success("Image set as input for next iteration")
                return

        self.main_window.animator.show_warning("No image input field found in current workflow")

    # =========================================================================
    # BATCH MODE POLLING
    # =========================================================================

    def _start_batch_polling(self, job_ids, network_output_dir):
        """Start polling for batch job completion."""
        from ui_components import StatusColors

        self._batch_job_ids = list(job_ids)
        self._batch_pending_jobs = set(job_ids)
        self._batch_failed_jobs = set()  # Reset failure tracking
        self._batch_completed_tasks = {job_id: 0 for job_id in job_ids}  # Track tasks per job
        self._batch_total_tasks = {job_id: self.ui.ComfyUIGenerationCount.value() for job_id in job_ids}
        self._batch_job_statuses = {job_id: "Pending" for job_id in job_ids}
        self._batch_network_output_dir = network_output_dir
        self._batch_poll_count = 0
        self._batch_start_time = time.time()
        self._batch_generation_count = self.ui.ComfyUIGenerationCount.value()
        self._batch_poll_pending_results = 0  # Track pending poll results per cycle
        self._batch_poll_results = {}  # Collected results for current poll cycle

        total_jobs = len(job_ids)
        total_frames = total_jobs * self._batch_generation_count

        self.log(f"[Batch] Starting polling for {total_jobs} job(s), {total_frames} total frame(s)")

        # Start status bar spinner
        self.main_window.start_status_spinner()

        self.main_window.animator.update_status_animated(
            f"🎨 ComfyUI Batch: {total_jobs} job(s), {total_frames} frame(s) • Waiting for workers...",
            StatusColors.INFO
        )

        # Create batch poll timer if needed
        if self._batch_poll_timer is None:
            self._batch_poll_timer = QTimer(self.main_window)
            self._batch_poll_timer.timeout.connect(self._poll_batch_jobs)

        self._batch_poll_timer.start(10000)  # Poll every 10 seconds

        # Do an immediate first poll
        self._poll_batch_jobs()

    def _poll_batch_jobs(self):
        """Poll all pending batch jobs and collect results before updating status."""
        from ui_components import Worker
        from comfyui_service import poll_deadline_job_status

        if not self._batch_pending_jobs:
            self._stop_batch_polling()
            return

        # Track how many results we're waiting for in this poll cycle
        self._batch_poll_pending_results = len(self._batch_pending_jobs)
        self._batch_poll_results = {}

        # Poll each pending job, passing output_dir to verify success via output files
        output_dir = self._batch_network_output_dir
        for job_id in list(self._batch_pending_jobs):
            worker = Worker(poll_deadline_job_status, job_id, output_dir)
            worker.signals.result.connect(lambda result, jid=job_id: self._on_batch_poll_result_collected(jid, result))
            worker.signals.error.connect(lambda msg, tb, jid=job_id: self._on_batch_poll_error(jid, msg))
            QThreadPool.globalInstance().start(worker)

    def _on_batch_poll_error(self, job_id, error_msg):
        """Handle poll error for a single job."""
        self.log(f"[Batch] Poll error for {job_id}: {error_msg}")
        # Store error as a failed result
        self._batch_poll_results[job_id] = {"status": "PollError", "error_message": error_msg}
        self._batch_poll_pending_results -= 1
        if self._batch_poll_pending_results <= 0:
            self._process_collected_poll_results()

    def _on_batch_poll_result_collected(self, job_id, result):
        """Collect a single job's poll result, then process all when complete."""
        self._batch_poll_results[job_id] = result
        self._batch_poll_pending_results -= 1

        # Once all results are collected, process them together
        if self._batch_poll_pending_results <= 0:
            self._process_collected_poll_results()

    def _process_collected_poll_results(self):
        """Process all collected poll results and update status bar once."""
        from ui_components import StatusColors

        had_new_frames = False
        total_jobs = len(self._batch_job_ids)

        # Process each result
        for job_id, result in self._batch_poll_results.items():
            status = result.get("status", "Unknown")
            completed_tasks = result.get("completed_tasks", 0)
            total_tasks = result.get("total_tasks", 1)

            # Update job status tracking
            self._batch_job_statuses[job_id] = status
            if total_tasks > 1:
                self._batch_total_tasks[job_id] = total_tasks

            # Check if new tasks completed since last poll (new frames rendered)
            prev_completed = self._batch_completed_tasks.get(job_id, 0)
            if completed_tasks > prev_completed:
                new_frames = completed_tasks - prev_completed
                self.log(f"[Batch] Job {job_id}: {new_frames} new frame(s) rendered! ({completed_tasks}/{total_tasks})")
                self._batch_completed_tasks[job_id] = completed_tasks
                had_new_frames = True

            self.log(f"[Batch Poll] Job {job_id}: {status}, Tasks: {completed_tasks}/{total_tasks}")

            if status == "Completed":
                self._batch_pending_jobs.discard(job_id)
                # Update completed tasks to total for this job
                self._batch_completed_tasks[job_id] = self._batch_total_tasks.get(job_id, 1)
                self.log(f"[Batch] Job {job_id} completed, {len(self._batch_pending_jobs)} remaining")

            elif status == "Failed":
                self._batch_pending_jobs.discard(job_id)
                self._batch_failed_jobs.add(job_id)
                error_msg = result.get("error_message", "Unknown error")
                self.log(f"[Batch] Job {job_id} FAILED: {error_msg}")

        # Refresh gallery if any new frames were rendered
        if had_new_frames:
            gallery_tab = self.main_window.get_tab("comfyui_gallery")
            if gallery_tab:
                self.log(f"[Batch] Triggering gallery refresh for new frames")
                gallery_tab._on_refresh()
                gallery_tab.signals.request_attention.emit()

        # Calculate totals for status update
        completed_jobs = total_jobs - len(self._batch_pending_jobs)
        total_frames_all = sum(self._batch_total_tasks.values())
        completed_frames_all = sum(self._batch_completed_tasks.values())
        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        elapsed_str = self._format_elapsed_time(elapsed)

        # Check if all jobs are done
        if not self._batch_pending_jobs:
            self._on_batch_jobs_completed(had_failures=len(self._batch_failed_jobs) > 0)
            return

        # Build consolidated status message
        active_jobs = sum(1 for s in self._batch_job_statuses.values() if s in ("Active", "Rendering"))
        queued_jobs = len(self._batch_pending_jobs) - active_jobs
        failed_count = len(self._batch_failed_jobs)

        # Determine overall status
        if failed_count > 0:
            main_status = f"⚠️ ComfyUI: {completed_frames_all}/{total_frames_all} frames • {failed_count} failed, {completed_jobs}/{total_jobs} done"
            status_color = StatusColors.WARNING
        elif active_jobs > 0:
            eta_str = self._estimate_remaining_time(completed_frames_all, total_frames_all, elapsed)
            if completed_frames_all > 0:
                main_status = f"🎨 ComfyUI: {completed_frames_all}/{total_frames_all} frames • {active_jobs} rendering"
                if queued_jobs > 0:
                    main_status += f", {queued_jobs} queued"
                main_status += f" • {elapsed_str}"
                if eta_str:
                    main_status += f" (~{eta_str} left)"
            else:
                main_status = f"🎨 ComfyUI: Starting {total_frames_all} frames • {active_jobs} active, {queued_jobs} queued"
            status_color = StatusColors.INFO
        elif queued_jobs > 0:
            main_status = f"⏳ ComfyUI: {queued_jobs} job(s) queued • Waiting for workers..."
            status_color = StatusColors.INFO
        else:
            main_status = f"🎨 ComfyUI: {completed_jobs}/{total_jobs} jobs • {elapsed_str}"
            status_color = StatusColors.INFO

        self.main_window.animator.update_status_animated(main_status, status_color)

    def _stop_batch_polling(self):
        """Stop the batch poll timer."""
        if self._batch_poll_timer:
            self._batch_poll_timer.stop()
        # Stop status bar spinner
        self.main_window.stop_status_spinner()

    def _on_batch_jobs_completed(self, had_failures=False):
        """Handle batch jobs completion - cleanup and refresh gallery.

        Args:
            had_failures: True if any jobs failed during the batch
        """
        from ui_components import StatusColors
        from comfyui_service import cleanup_job_temp_files

        self._stop_batch_polling()

        network_dir = self._batch_network_output_dir

        # Calculate total time and frame counts
        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        elapsed_str = self._format_elapsed_time(elapsed)
        total_frames = sum(self._batch_total_tasks.values())
        completed_frames = sum(self._batch_completed_tasks.values())

        if had_failures:
            self.log(f"[Batch] Jobs finished with failures!")
        else:
            self.log(f"[Batch] All jobs completed successfully!")
        self.log(f"[Batch] Network dir: {network_dir}")

        # Clean up temp files from network directory
        if network_dir:
            deleted = cleanup_job_temp_files(network_dir)
            if deleted:
                self.log(f"[Batch] Cleaned up {deleted} temp files from network dir")

        # Update status based on success/failure
        # Get counts before clearing
        failed_count = len(self._batch_failed_jobs)
        total_count = len(self._batch_job_ids)
        success_count = total_count - failed_count

        if had_failures:
            self.main_window.animator.show_error(f"ComfyUI: {failed_count}/{total_count} job(s) failed!")
            self.main_window.animator.update_status_animated(
                f"❌ ComfyUI: {failed_count} failed, {success_count} succeeded • {completed_frames} frames in {elapsed_str}",
                StatusColors.ERROR
            )
        else:
            self.main_window.animator.show_success(f"All {total_count} ComfyUI jobs completed!")
            self.main_window.animator.update_status_animated(
                f"✅ ComfyUI Complete: {total_frames} frames in {elapsed_str}",
                StatusColors.SUCCESS
            )

        # Reset failure tracking for next batch
        self._batch_failed_jobs.clear()

        # Trigger gallery refresh to show new images and flash the tab
        gallery_tab = self.main_window.get_tab("comfyui_gallery")
        if gallery_tab:
            self.log("[Batch] Triggering gallery refresh...")
            gallery_tab._on_refresh()

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
        if preset_name:
            presets = get_comfyui_workflow_presets()
            if preset_name in presets:
                self._select_preset(preset_name)

        # Restore generation count
        gen_count = state.get("generation_count", 1)
        self.ui.ComfyUIGenerationCount.setValue(gen_count)

        # Restore seed
        seed = state.get("seed", random.randint(0, 2147483647))
        self.ui.ComfyUISeed.setValue(seed)


        # Store editable values to apply after widgets are created
        self._pending_editable_values = state.get("editable_values", {})
