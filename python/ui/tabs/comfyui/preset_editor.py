"""
ComfyUI Preset Editor Dialog.

Extracted from ComfyUITab to reduce complexity.
Handles the preset editing UI with single/multi-workflow modes and editable nodes.
"""

import os
from typing import Dict, Optional, Any

from PySide6 import QtWidgets
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QScrollArea
)


class PresetEditorDialog(QDialog):
    """Dialog for editing ComfyUI workflow presets."""

    def __init__(
        self,
        parent,
        preset_name: str,
        preset_data: Dict[str, Any],
        main_window,
        extract_editable_nodes_func
    ):
        """
        Initialize the preset editor dialog.

        Args:
            parent: Parent widget
            preset_name: Current preset name
            preset_data: Preset configuration dictionary
            main_window: Reference to main window for animator
            extract_editable_nodes_func: Function to extract editable nodes from workflow
        """
        super().__init__(parent)
        self.preset_name = preset_name
        self.preset_data = preset_data
        self.main_window = main_window
        self.extract_editable_nodes = extract_editable_nodes_func

        # Store original values
        self.current_path = preset_data.get("path", "")
        self.current_iteratable = preset_data.get("iteratable", False)
        self.current_note = preset_data.get("note", "")
        self.current_full_restart = preset_data.get("full_restart", False)
        self.current_node_overrides = preset_data.get("node_overrides", {})
        self.current_is_multi = preset_data.get("is_multi", False)
        self.current_workflows = preset_data.get("workflows", {})
        self.current_output_type = preset_data.get("output_type", "image")

        # Storage for widgets
        self.node_override_widgets = {}
        self.workflow_entry_widgets = {}

        # Result storage
        self.result_accepted = False
        self.result_data = {}

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle(f"Edit Model: {self.preset_name}")
        self.setMinimumWidth(800)
        self.setMinimumHeight(750)

        layout = QVBoxLayout(self)

        # Preset name
        name_layout = QHBoxLayout()
        name_label = QLabel("Model Name:")
        self.name_edit = QLineEdit(self.preset_name)
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # Output type dropdown
        output_type_layout = QHBoxLayout()
        output_type_label = QLabel("Output Type:")
        self.output_type_combo = QtWidgets.QComboBox()
        self.output_type_combo.addItems(["Image", "Video", "3D", "Audio", "Other"])
        # Map display names to internal values
        self._output_type_map = {"Image": "image", "Video": "video", "3D": "3d", "Audio": "audio", "Other": "other"}
        self._output_type_reverse = {v: k for k, v in self._output_type_map.items()}
        # Set current value
        current_display = self._output_type_reverse.get(self.current_output_type, "Image")
        self.output_type_combo.setCurrentText(current_display)
        self.output_type_combo.setToolTip(
            "Specify what type of content this model generates.\n\n"
            "• Image/Video: Auto-add to Canvas option will be available\n"
            "• 3D/Audio/Other: Canvas integration is disabled"
        )
        output_type_layout.addWidget(output_type_label)
        output_type_layout.addWidget(self.output_type_combo)
        output_type_layout.addStretch()
        layout.addLayout(output_type_layout)

        # Multi-workflow checkbox
        self.is_multi_check = QtWidgets.QCheckBox("Multi-Workflow Model (allows multiple workflows per model)")
        self.is_multi_check.setChecked(self.current_is_multi)
        self.is_multi_check.setToolTip(
            "Enable this to add multiple workflows to a single model.\n"
            "Each workflow can have its own settings and note.\n"
            "A dropdown will appear in the ComfyUI tab to select which workflow to use."
        )
        layout.addWidget(self.is_multi_check)

        # ======== Single Workflow Section ========
        self.single_workflow_widget = QWidget()
        single_workflow_layout = QVBoxLayout(self.single_workflow_widget)
        single_workflow_layout.setContentsMargins(0, 0, 0, 0)

        # Workflow path
        path_layout = QHBoxLayout()
        path_label = QLabel("Workflow File:")
        self.path_edit = QLineEdit(self.current_path)
        self.browse_btn = QPushButton("Browse...")
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_btn)
        single_workflow_layout.addLayout(path_layout)

        # Iteratable checkbox
        self.iteratable_check = QtWidgets.QCheckBox("Enable Iterate Mode for this workflow")
        self.iteratable_check.setChecked(self.current_iteratable)
        self.iteratable_check.setToolTip(
            "Iterate mode is automatically enabled when only 1 image is selected.\n"
            "It allows reviewing results and refining prompts between generations.\n"
            "This option must be enabled for the workflow to support iterate mode."
        )
        single_workflow_layout.addWidget(self.iteratable_check)

        # Full Restart checkbox
        self.full_restart_check = QtWidgets.QCheckBox("Full Restart - Completely restart ComfyUI server before each job")
        self.full_restart_check.setChecked(self.current_full_restart)
        self.full_restart_check.setToolTip(
            "Enable this if the model requires a clean server state.\n"
            "The ComfyUI server will be completely restarted before processing this workflow.\n"
            "This is slower but ensures consistent results for certain models."
        )
        single_workflow_layout.addWidget(self.full_restart_check)

        # Note field for single workflow
        note_label = QLabel("Note:")
        single_workflow_layout.addWidget(note_label)

        self.note_edit = QtWidgets.QPlainTextEdit()
        self.note_edit.setPlaceholderText("Add a note or description for this model...")
        self.note_edit.setPlainText(self.current_note)
        self.note_edit.setMaximumHeight(80)
        single_workflow_layout.addWidget(self.note_edit)

        # ======== Editable Nodes Section (Single Workflow) ========
        nodes_group = QtWidgets.QGroupBox("Node Overrides (Advanced)")
        nodes_group_layout = QVBoxLayout(nodes_group)

        nodes_info_label = QLabel(
            "Configure default values for editable nodes.\n"
            "Uncheck to hide a node from the UI. Leave value blank to use workflow default."
        )
        nodes_info_label.setStyleSheet("color: #888; font-size: 11px;")
        nodes_group_layout.addWidget(nodes_info_label)

        # Scroll area for editable nodes
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(120)
        self.scroll_area.setMaximumHeight(180)

        self.nodes_container = QWidget()
        self.nodes_scroll_layout = QVBoxLayout(self.nodes_container)
        self.nodes_scroll_layout.setContentsMargins(5, 5, 5, 5)
        self.nodes_scroll_layout.setSpacing(8)

        self.scroll_area.setWidget(self.nodes_container)
        nodes_group_layout.addWidget(self.scroll_area)
        single_workflow_layout.addWidget(nodes_group)

        layout.addWidget(self.single_workflow_widget)

        # ======== Multi-Workflow Section ========
        self.multi_workflow_widget = QWidget()
        multi_workflow_layout = QVBoxLayout(self.multi_workflow_widget)
        multi_workflow_layout.setContentsMargins(0, 0, 0, 0)

        multi_info = QLabel(
            "Multi-Workflow Mode: Add multiple workflows to this model.\n"
            "Each workflow can have its own settings. Use the dropdown in the ComfyUI tab to select which one to use."
        )
        multi_info.setStyleSheet("color: #888; font-size: 11px;")
        multi_info.setWordWrap(True)
        multi_workflow_layout.addWidget(multi_info)

        # Scroll area for workflow list
        self.workflows_scroll = QtWidgets.QScrollArea()
        self.workflows_scroll.setWidgetResizable(True)
        self.workflows_scroll.setMinimumHeight(200)
        self.workflows_scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: 1px solid #3c3c3c; }")

        self.workflows_container = QWidget()
        self.workflows_layout = QVBoxLayout(self.workflows_container)
        self.workflows_layout.setContentsMargins(5, 5, 5, 5)
        self.workflows_layout.setSpacing(8)
        self.workflows_scroll.setWidget(self.workflows_container)
        multi_workflow_layout.addWidget(self.workflows_scroll)

        # Add workflow button
        self.add_workflow_btn = QPushButton("+ Add Workflow")
        self.add_workflow_btn.setFixedWidth(150)
        self.add_workflow_btn.setStyleSheet("QPushButton { color: #10b981; }")
        multi_workflow_layout.addWidget(self.add_workflow_btn)

        layout.addWidget(self.multi_workflow_widget)

        # Update visibility based on multi-workflow mode
        self._update_mode_visibility()

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(100)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setFixedWidth(100)
        self.save_btn.setDefault(True)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

        # Initial population
        self._refresh_editable_nodes_list()
        self._populate_multi_workflows()

    def _connect_signals(self):
        """Connect widget signals."""
        self.browse_btn.clicked.connect(self._on_browse_workflow)
        self.path_edit.textChanged.connect(self._on_path_changed)
        self.is_multi_check.toggled.connect(self._update_mode_visibility)
        self.add_workflow_btn.clicked.connect(self._on_add_workflow)
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn.clicked.connect(self.reject)

    def _update_mode_visibility(self):
        """Update widget visibility based on multi-workflow mode."""
        is_multi = self.is_multi_check.isChecked()
        self.single_workflow_widget.setVisible(not is_multi)
        self.multi_workflow_widget.setVisible(is_multi)

    def _on_browse_workflow(self):
        """Browse for workflow JSON file."""
        from file_dialogs import browse_file_with_memory

        file_path = browse_file_with_memory(
            self,
            context="comfyui_workflow",
            title="Select ComfyUI Workflow File",
            file_filter="JSON Files (*.json);;All Files (*)",
            fallback_path=os.path.expanduser("~")
        )
        if file_path:
            self.path_edit.setText(file_path)

    def _on_path_changed(self):
        """Handle workflow path change."""
        # Refresh editable nodes when path changes
        self._refresh_editable_nodes_list()

    def _refresh_editable_nodes_list(self):
        """Refresh the list of editable nodes from the workflow."""
        # Clear existing widgets
        while self.nodes_scroll_layout.count():
            item = self.nodes_scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.node_override_widgets.clear()

        workflow_path = self.path_edit.text().strip()
        if not workflow_path or not os.path.exists(workflow_path):
            no_nodes_label = QLabel("No workflow selected or file not found")
            no_nodes_label.setStyleSheet("color: #888; font-style: italic;")
            self.nodes_scroll_layout.addWidget(no_nodes_label)
            return

        editable_nodes = self.extract_editable_nodes(workflow_path)
        if not editable_nodes:
            no_nodes_label = QLabel("No editable nodes found in this workflow")
            no_nodes_label.setStyleSheet("color: #888; font-style: italic;")
            self.nodes_scroll_layout.addWidget(no_nodes_label)
            return

        for node in editable_nodes:
            # Get existing override for this node
            # Support both node_id (new, unique) and title (legacy) for backwards compatibility
            override = self.current_node_overrides.get(
                str(node.node_id),
                self.current_node_overrides.get(node.title, {})
            )
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
            node_name_label.setToolTip(
                f"Node: {node.title}\nID: {node.node_id}\n"
                f"Type: {node.node_type}\nWidget: {node.widget_type}"
            )
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

            self.nodes_scroll_layout.addWidget(node_row)

            # Store reference for later retrieval
            # Use node_id as key instead of title to ensure uniqueness
            self.node_override_widgets[str(node.node_id)] = {
                "enable_check": enable_check,
                "default_input": default_input,
                "node": node
            }

        # Add stretch at end
        self.nodes_scroll_layout.addStretch()

    def _populate_multi_workflows(self):
        """Populate the multi-workflow list."""
        # Clear existing
        while self.workflows_layout.count():
            item = self.workflows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.workflow_entry_widgets.clear()

        # Add existing workflows
        for wf_name, wf_config in self.current_workflows.items():
            self._add_workflow_entry(wf_name, wf_config)

        # Add stretch at end
        self.workflows_layout.addStretch()

    def _on_add_workflow(self):
        """Add a new workflow entry."""
        # Generate unique name
        idx = len(self.workflow_entry_widgets) + 1
        wf_name = f"workflow_{idx}"
        while wf_name in self.workflow_entry_widgets:
            idx += 1
            wf_name = f"workflow_{idx}"

        self._add_workflow_entry(wf_name, None)

    def _add_workflow_entry(self, wf_name: str, wf_config: Optional[Dict]):
        """Create a workflow entry widget."""
        if wf_config is None:
            wf_config = {
                "path": "",
                "note": "",
                "iteratable": False,
                "full_restart": False,
                "node_overrides": {}
            }

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
        delete_wf_btn.clicked.connect(lambda: self._on_remove_workflow(wf_name, entry_widget))
        header_row.addWidget(delete_wf_btn)
        entry_layout.addLayout(header_row)

        # Path row
        path_row = QHBoxLayout()
        wf_path_edit = QLineEdit(wf_config.get("path", ""))
        wf_path_edit.setPlaceholderText("Workflow JSON file...")
        wf_browse_btn = QPushButton("Browse...")
        wf_browse_btn.setFixedWidth(90)
        wf_browse_btn.clicked.connect(lambda: self._on_browse_wf_path(wf_path_edit))
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

            editable_nodes = self.extract_editable_nodes(workflow_path)
            if not editable_nodes:
                no_nodes_label = QLabel("No editable nodes found")
                no_nodes_label.setStyleSheet("color: #888; font-style: italic;")
                nodes_scroll_layout.addWidget(no_nodes_label)
                return

            for node in editable_nodes:
                # Support both node_id (new, unique) and title (legacy) for backwards compatibility
                override = current_wf_node_overrides.get(
                    str(node.node_id),
                    current_wf_node_overrides.get(node.title, {})
                )
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

                wf_node_override_widgets[str(node.node_id)] = {
                    "enable_check": enable_check,
                    "default_input": default_input,
                    "node": node
                }

            nodes_scroll_layout.addStretch()

        # Insert before stretch
        count = self.workflows_layout.count()
        if count > 0 and self.workflows_layout.itemAt(count - 1).spacerItem():
            self.workflows_layout.insertWidget(count - 1, entry_widget)
        else:
            self.workflows_layout.addWidget(entry_widget)

        # Store widgets for this workflow entry
        self.workflow_entry_widgets[wf_name] = {
            "widget": entry_widget,
            "name_edit": wf_name_edit,
            "path_edit": wf_path_edit,
            "iteratable_check": wf_iteratable,
            "full_restart_check": wf_full_restart,
            "note_edit": wf_note_edit,
            "node_override_widgets": wf_node_override_widgets,
            "refresh_nodes_func": refresh_wf_editable_nodes
        }

    def _on_browse_wf_path(self, path_edit: QLineEdit):
        """Browse for workflow path (for multi-workflow entries)."""
        from file_dialogs import browse_file_with_memory

        file_path = browse_file_with_memory(
            self,
            context="comfyui_workflow",
            title="Select ComfyUI Workflow File",
            file_filter="JSON Files (*.json);;All Files (*)",
            fallback_path=os.path.expanduser("~")
        )
        if file_path:
            path_edit.setText(file_path)

    def _on_remove_workflow(self, wf_name: str, entry_widget: QWidget):
        """Remove a workflow entry."""
        if wf_name in self.workflow_entry_widgets:
            del self.workflow_entry_widgets[wf_name]
        entry_widget.deleteLater()

    def _on_save(self):
        """Save the preset data."""
        new_name = self.name_edit.text().strip()
        if not new_name:
            self.main_window.animator.show_error("Preset name cannot be empty")
            return

        new_is_multi = self.is_multi_check.isChecked()

        if new_is_multi:
            # Multi-workflow mode: collect all workflows
            new_workflows = {}
            for original_wf_name, wf_widgets in self.workflow_entry_widgets.items():
                actual_wf_name = wf_widgets["name_edit"].text().strip()
                if not actual_wf_name:
                    self.main_window.animator.show_error("All workflow names must be filled")
                    return

                wf_path = wf_widgets["path_edit"].text().strip()
                if not wf_path:
                    self.main_window.animator.show_error(f"Workflow '{actual_wf_name}' path cannot be empty")
                    return

                # Collect node overrides for this workflow
                wf_node_overrides = {}
                for node_key, widgets in wf_widgets["node_override_widgets"].items():
                    is_enabled = widgets["enable_check"].isChecked()
                    default_input = widgets["default_input"]
                    default_value = default_input.text().strip() if default_input else ""
                    if not is_enabled or default_value:
                        wf_node_overrides[node_key] = {
                            "enabled": is_enabled,
                            "default_value": default_value
                        }

                new_workflows[actual_wf_name] = {
                    "path": wf_path,
                    "note": wf_widgets["note_edit"].text().strip(),
                    "iteratable": wf_widgets["iteratable_check"].isChecked(),
                    "full_restart": wf_widgets["full_restart_check"].isChecked(),
                    "node_overrides": wf_node_overrides
                }

            if not new_workflows:
                self.main_window.animator.show_error("At least one workflow must be added in multi-workflow mode")
                return

            # Set result data
            new_path = None
            new_iteratable = False
            new_full_restart = False
            new_note = ""
            new_node_overrides = {}
        else:
            # Single workflow mode
            new_path = self.path_edit.text().strip()
            new_iteratable = self.iteratable_check.isChecked()
            new_note = self.note_edit.toPlainText().strip()
            new_full_restart = self.full_restart_check.isChecked()
            new_workflows = None

            # Collect node overrides from widgets
            new_node_overrides = {}
            for node_key, widgets in self.node_override_widgets.items():
                is_enabled = widgets["enable_check"].isChecked()
                default_input = widgets["default_input"]
                default_value = default_input.text().strip() if default_input else ""
                if not is_enabled or default_value:
                    # Use node_id as key to ensure uniqueness
                    new_node_overrides[node_key] = {
                        "enabled": is_enabled,
                        "default_value": default_value
                    }

            if not new_path:
                self.main_window.animator.show_error("Workflow path cannot be empty")
                return

        # Get output type from combo box
        output_type_display = self.output_type_combo.currentText()
        new_output_type = self._output_type_map.get(output_type_display, "image")

        # Store result
        self.result_accepted = True
        self.result_data = {
            "name": new_name,
            "path": new_path,
            "iteratable": new_iteratable,
            "note": new_note,
            "full_restart": new_full_restart,
            "node_overrides": new_node_overrides,
            "is_multi": new_is_multi,
            "workflows": new_workflows,
            "output_type": new_output_type
        }

        self.accept()

    def get_result(self):
        """Get the result data after dialog closes."""
        if self.result_accepted:
            return self.result_data
        return None
