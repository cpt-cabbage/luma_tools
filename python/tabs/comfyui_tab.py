"""
ComfyUI tab module for Luma Tools.

Handles ComfyUI workflow submission and AI image generation.
"""

import os
import random

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
        from icons import IconManager, TAB_COLORS

        # Workflow preset signals
        self.ui.ComfyUIChoosePreset.clicked.connect(self._on_choose_preset_clicked)
        self.ui.ComfyUIAddPreset.clicked.connect(self._on_add_preset_clicked)
        self.ui.ComfyUIEditPreset.clicked.connect(self._on_edit_preset_clicked)
        self.ui.ComfyUIDeletePreset.clicked.connect(self._on_delete_preset_clicked)
        self.ui.ComfyUIBrowseOutputDir.clicked.connect(self._on_browse_output_dir)
        self.ui.ComfyUIOutputDir.textChanged.connect(self._validate_inputs)
        self.ui.ComfyUISubmit.clicked.connect(self._on_submit_clicked)
        self.ui.ComfyUIGenerationCount.valueChanged.connect(self._on_generation_count_changed)
        self.ui.ComfyUISeed.valueChanged.connect(self._on_seed_changed)
        self.ui.ComfyUIRandomizeSeed.clicked.connect(self._on_randomize_seed)
        self.ui.ComfyUIRandomizeSeed.setIcon(IconManager.get_icon("dice", TAB_COLORS["comfyui"], 16))


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
        self._iterate_user_output_dir = ""
        self._iterate_poll_count = 0

        # Batch mode state
        self._batch_poll_timer = None
        self._batch_job_ids = []
        self._batch_pending_jobs = set()
        self._batch_network_output_dir = ""
        self._batch_user_output_dir = ""
        self._batch_poll_count = 0

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

    def _on_choose_preset_clicked(self):
        """Show popup menu with available workflow presets."""
        from settings_manager import get_comfyui_workflow_presets

        menu = QMenu(self.main_window)

        presets = get_comfyui_workflow_presets()
        if not presets:
            action = menu.addAction("No presets available")
            action.setEnabled(False)
        else:
            for name in sorted(presets.keys()):
                action = menu.addAction(name)
                action.setData(name)
                # Mark current preset with a checkmark
                if name == self._current_preset_name:
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
            self.ui.ComfyUICurrentPreset.setText(preset_name)
            self.ui.ComfyUIWorkflowPath.setText(workflow_path)
            self.app_state.comfyui_workflow_path = workflow_path
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._save_state()

            # Show/hide iterate mode based on workflow's iteratable flag
            is_iteratable = is_workflow_preset_iteratable(preset_name)
            self._update_iterate_mode_visibility(is_iteratable)
        else:
            self.main_window.animator.show_error(f"Workflow file not found: {workflow_path}")
            self.ui.ComfyUIWorkflowPath.setText("Workflow file not found")
            self.ui.ComfyUICurrentPreset.setText("No preset selected")
            self._current_preset_name = None
            self.app_state.comfyui_workflow_path = None
            self._validate_inputs()
            self._update_iterate_mode_visibility(False)

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
            preset = {"path": preset, "description": "", "iteratable": False}

        current_name = self._current_preset_name
        current_path = preset.get("path", "")
        current_iteratable = preset.get("iteratable", False)

        # Create edit dialog
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(f"Edit Preset: {current_name}")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)

        # Preset name
        name_layout = QHBoxLayout()
        name_label = QLabel("Preset Name:")
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

        browse_btn.clicked.connect(browse_workflow)

        # Iteratable checkbox
        iteratable_check = QtWidgets.QCheckBox("Enable Iterate Mode for this workflow")
        iteratable_check.setChecked(current_iteratable)
        iteratable_check.setToolTip(
            "Iterate mode allows submitting one image, reviewing the result,\n"
            "and refining the prompt before the next generation."
        )
        layout.addWidget(iteratable_check)

        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec_() == QDialog.Accepted:
            new_name = name_edit.text().strip()
            new_path = path_edit.text().strip()
            new_iteratable = iteratable_check.isChecked()

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
                save_comfyui_workflow_preset(new_name, new_path, iteratable=new_iteratable)
                self._current_preset_name = new_name
                self.ui.ComfyUICurrentPreset.setText(new_name)
                self.main_window.animator.show_success(f"Preset renamed to '{new_name}'")
            else:
                # Just update the existing preset
                update_comfyui_workflow_preset(
                    current_name,
                    workflow_path=new_path,
                    iteratable=new_iteratable
                )
                self.main_window.animator.show_success(f"Preset '{current_name}' updated")

            # Refresh the UI with the (possibly new) preset name
            self._select_preset(self._current_preset_name)

    def _on_delete_preset_clicked(self):
        """Delete the currently selected workflow preset."""
        from settings_manager import delete_comfyui_workflow_preset

        if not self._current_preset_name:
            self.main_window.animator.show_error("No preset selected")
            return

        reply = QMessageBox.question(
            self.main_window, "Delete Preset",
            f"Delete workflow preset '{self._current_preset_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            deleted_name = self._current_preset_name
            delete_comfyui_workflow_preset(self._current_preset_name)
            self._current_preset_name = None
            self.ui.ComfyUICurrentPreset.setText("No preset selected")
            self.ui.ComfyUIWorkflowPath.setText("No workflow selected")
            self.app_state.comfyui_workflow_path = None
            self._refresh_editable_nodes()
            self._validate_inputs()
            self.main_window.animator.show_info(f"Preset '{deleted_name}' deleted")

    # =========================================================================
    # EDITABLE NODES
    # =========================================================================

    def _refresh_editable_nodes(self):
        """Refresh dynamic UI widgets based on editable nodes in the workflow."""
        from comfyui_service import extract_editable_nodes

        # Clear layout
        layout = self.ui.comfyuiEditableNodesLayout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._comfyui_dynamic_widgets = {}

        if not self.app_state.comfyui_workflow_path:
            return

        editable_nodes = extract_editable_nodes(self.app_state.comfyui_workflow_path)
        for node in editable_nodes:
            widget = self._create_editable_node_widget(node)
            if widget:
                layout.addWidget(widget)
                self._comfyui_dynamic_widgets[node.node_id] = widget

        # Apply any pending editable values from restored state
        self._apply_pending_editable_values()

    def _create_editable_node_widget(self, node):
        """Create a widget for an editable node."""
        from ui_components import BatchImageSelector
        from spell_checker import SpellCheckTextEdit
        from settings_manager import get_last_browse_directory

        container = QWidget()
        layout = QVBoxLayout(container)
        label = QLabel(f"{node.display_name}:")
        layout.addWidget(label)

        if node.widget_type == 'text':
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

            # Connect preset button to show popup menu
            preset_btn.clicked.connect(
                lambda checked=False, w=input_widget, btn=preset_btn: self._on_prompt_preset_clicked(w, btn)
            )
            # Save state when text changes (with delay)
            input_widget.textChanged.connect(self._on_text_changed)

        elif node.widget_type == 'image':
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
            input_widget = QLineEdit()
            if node.current_value:
                input_widget.setText(str(node.current_value))
            input_widget.textChanged.connect(self._on_text_changed)
            layout.addWidget(input_widget)
            container.input_widget = input_widget

        return container

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

    def _on_prompt_preset_clicked(self, text_widget, button):
        """Show popup menu for prompt presets (per-workflow)."""
        from settings_manager import get_comfyui_prompt_presets_for_workflow

        menu = QMenu(self.main_window)

        # Get current workflow name
        workflow_name = self._current_preset_name or ""
        if not workflow_name:
            menu.addAction("No workflow selected").setEnabled(False)
            menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))
            return

        # Get presets for this workflow
        presets = get_comfyui_prompt_presets_for_workflow(workflow_name)

        # Add preset items
        if presets:
            for name in sorted(presets.keys()):
                action = menu.addAction(name)
                action.triggered.connect(
                    lambda checked=False, n=name, w=text_widget: self._apply_prompt_preset(n, w)
                )
            menu.addSeparator()
        else:
            no_presets = menu.addAction("No presets saved")
            no_presets.setEnabled(False)
            menu.addSeparator()

        # Add save/delete options
        save_action = menu.addAction("Save Current...")
        save_action.triggered.connect(
            lambda checked=False, w=text_widget: self._save_prompt_preset(w)
        )

        if presets:
            delete_menu = menu.addMenu("Delete...")
            for name in sorted(presets.keys()):
                delete_action = delete_menu.addAction(name)
                delete_action.triggered.connect(
                    lambda checked=False, n=name: self._delete_prompt_preset(n)
                )

        menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))

    def _apply_prompt_preset(self, preset_name, text_widget):
        """Apply a prompt preset to the text widget."""
        from settings_manager import get_comfyui_prompt_presets_for_workflow

        workflow_name = self._current_preset_name or ""
        presets = get_comfyui_prompt_presets_for_workflow(workflow_name)
        if preset_name in presets:
            text_widget.setPlainText(presets[preset_name])

    def _save_prompt_preset(self, text_widget):
        """Save current text as a new prompt preset for the current workflow."""
        from settings_manager import save_comfyui_prompt_preset_for_workflow

        workflow_name = self._current_preset_name or ""
        if not workflow_name:
            self.main_window.animator.show_error("No workflow selected")
            return

        current_text = text_widget.toPlainText().strip()
        if not current_text:
            self.main_window.animator.show_error("Cannot save empty preset")
            return

        dialog = QInputDialog(self.main_window)
        dialog.setWindowTitle("Save Prompt Preset")
        dialog.setLabelText(f"Preset name (for '{workflow_name}'):")
        dialog.setTextValue("")
        dialog.setWindowModality(Qt.WindowModal)

        if dialog.exec_() == QInputDialog.Accepted:
            name = dialog.textValue().strip()
            if not name:
                self.main_window.animator.show_error("Preset name cannot be empty")
                return
            save_comfyui_prompt_preset_for_workflow(workflow_name, name, current_text)
            self.main_window.animator.show_success(f"Preset '{name}' saved")

    def _delete_prompt_preset(self, preset_name):
        """Delete a prompt preset from the current workflow."""
        from settings_manager import delete_comfyui_prompt_preset_for_workflow

        workflow_name = self._current_preset_name or ""
        if not workflow_name:
            return

        reply = QMessageBox.question(
            self.main_window, "Delete Preset",
            f"Delete prompt preset '{preset_name}' from '{workflow_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            delete_comfyui_prompt_preset_for_workflow(workflow_name, preset_name)
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
    # OUTPUT DIRECTORY
    # =========================================================================

    def _on_browse_output_dir(self):
        """Browse for ComfyUI output directory."""
        from settings_manager import get_last_browse_directory, set_last_browse_directory

        current_path = self.ui.ComfyUIOutputDir.text()
        if not current_path:
            current_path = get_last_browse_directory("comfyui_output")
        if not current_path and self.app_state.shotpath:
            current_path = self.app_state.shotpath

        directory = QFileDialog.getExistingDirectory(
            self.main_window,
            "Select Output Directory",
            current_path or ""
        )
        if directory:
            self.ui.ComfyUIOutputDir.setText(directory)
            set_last_browse_directory("comfyui_output", directory)
            self._save_state()

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_inputs(self):
        """Validate inputs and enable/disable submit button."""
        workflow_ok = bool(self.app_state.comfyui_workflow_path)
        output_ok = bool(self.ui.ComfyUIOutputDir.text().strip())
        self.ui.ComfyUISubmit.setEnabled(workflow_ok and output_ok)

    # =========================================================================
    # SUBMISSION
    # =========================================================================

    def _on_submit_clicked(self):
        """Submit the workflow to ComfyUI/Deadline."""
        from ui_components import Worker, StatusColors
        from comfyui_service import extract_editable_nodes, submit_comfyui_job
        from settings_manager import (
            get_comfyui_network_output_path,
            get_comfyui_use_user_subfolder
        )

        # Validate workflow
        if not self.app_state.comfyui_workflow_path:
            self.main_window.animator.show_error("No workflow selected")
            return

        # Validate output directory
        output_dir = self.ui.ComfyUIOutputDir.text().strip()
        if not output_dir:
            self.main_window.animator.show_error("No output directory selected")
            return

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
        job_name = f"{self.app_state.shot}_comfyui" if self.app_state.shot else "comfyui_job"

        # Show loading overlay
        self.main_window.animator.show_loading(
            "Submitting to ComfyUI",
            f"Preparing {generation_count} generation(s)...",
            show_progress=True
        )
        self.main_window.animator.animate_button_click(self.ui.ComfyUISubmit)

        # Server mode is always enabled (persistent ComfyUI)
        use_server_mode = True

        # Get seed value
        base_seed = self.ui.ComfyUISeed.value()

        # Get network output path from global settings (optional)
        network_output_dir = get_comfyui_network_output_path()

        # Add user subfolder if enabled
        if network_output_dir and get_comfyui_use_user_subfolder():
            network_output_dir = os.path.join(network_output_dir, self.app_state.user)
            self.log(f"[ComfyUI] Using user subfolder: {network_output_dir}")

        self.log(f"[ComfyUI UI] Network output path: {network_output_dir!r}")
        self.log(f"[ComfyUI UI] User output path: {output_dir}")

        def on_result(result):
            """Called when submission completes."""
            self.main_window.animator.hide_loading()
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
                poll_output_dir = network_output_dir if network_output_dir else output_dir

                if self.app_state.comfyui_iterate_mode and len(job_ids) == 1:
                    self._start_iterate_polling(job_ids[0], poll_output_dir, output_dir)
                else:
                    self._start_batch_polling(job_ids, poll_output_dir, output_dir)
            else:
                self.main_window.animator.show_error(f"Submission failed: {error_msg}")
                self.main_window.animator.update_status_animated(
                    f"ComfyUI failed: {error_msg}",
                    StatusColors.ERROR
                )

        def on_error(error_msg, traceback_str):
            """Called when submission fails."""
            self.main_window.animator.hide_loading()
            self.main_window.animator.show_error(f"Submission error: {error_msg}")
            self.main_window.animator.update_status_animated(
                f"ComfyUI error: {error_msg}",
                StatusColors.ERROR
            )
            self.log(f"ComfyUI submission error: {error_msg}")
            self.log(traceback_str)

        def on_progress(progress, message):
            """Called for progress updates."""
            self.main_window.animator.update_loading_message(message)
            self.main_window.animator.update_loading_progress(progress)

        # Create worker and run submission on background thread
        worker = Worker(
            submit_comfyui_job,
            workflow_path=self.app_state.comfyui_workflow_path,
            input_image=None,
            prompt=None,
            output_dir=output_dir,
            generation_count=generation_count,
            job_name=job_name,
            editable_values=editable_values,
            use_server_mode=use_server_mode,
            base_seed=base_seed,
            network_output_dir=network_output_dir if network_output_dir else None,
        )
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(on_progress)
        QThreadPool.globalInstance().start(worker)

    # =========================================================================
    # ITERATE MODE POLLING
    # =========================================================================

    def _start_iterate_polling(self, job_id, network_output_dir, user_output_dir=None):
        """Start polling for iterate mode job completion."""
        from ui_components import StatusColors

        self.app_state.comfyui_current_job_id = job_id
        self._iterate_network_output_dir = network_output_dir
        self._iterate_user_output_dir = user_output_dir or network_output_dir
        self._iterate_poll_count = 0

        self.log(f"[Iterate] Starting polling for job {job_id}")
        self.log(f"[Iterate] Network output dir: {network_output_dir}")
        self.log(f"[Iterate] User output dir: {user_output_dir}")

        # Update UI
        self.ui.ComfyUIIterateStatus.setText("Job submitted, waiting for Deadline...")
        self.ui.ComfyUIIterateProgress.setValue(0)
        self.ui.ComfyUIUseAsInput.setEnabled(False)

        # Update main status bar
        self.main_window.animator.update_status_animated(
            "Deadline: Job submitted, waiting...",
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

        # Poll on worker thread
        worker = Worker(poll_deadline_job_status, job_id)
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

        self.log(f"[Iterate Poll] Status: {status}, Progress: {progress}%, Tasks: {completed_tasks}/{total_tasks}")

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
                f"Deadline: Job failed - {error_message}",
                StatusColors.ERROR
            )
        else:
            # Still running - show detailed status
            dots = "." * ((self._iterate_poll_count % 3) + 1)

            if status in ("Active", "Rendering"):
                status_text = f"Rendering {completed_tasks}/{total_tasks} tasks{dots}"
                main_status = f"Deadline: Rendering ({completed_tasks}/{total_tasks})"
            elif status in ("Pending", "Queued"):
                status_text = f"Queued, waiting for worker{dots}"
                main_status = f"Deadline: Queued, waiting for worker{dots}"
            else:
                status_text = f"{status}: {progress}%{dots}"
                main_status = f"Deadline: {status} ({progress}%)"

            self.ui.ComfyUIIterateStatus.setText(status_text)
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #4a9eff;")
            self.main_window.animator.update_status_animated(main_status, StatusColors.INFO)

    def _stop_iterate_polling(self):
        """Stop the iterate poll timer."""
        if self._iterate_poll_timer:
            self._iterate_poll_timer.stop()

    def _on_iterate_job_completed(self):
        """Handle iterate job completion - show the generated image."""
        from ui_components import StatusColors
        from comfyui_service import (
            get_job_output_files,
            transfer_outputs_to_user_folder,
            cleanup_job_temp_files
        )
        from settings_manager import (
            get_comfyui_transfer_to_user_folder,
            get_comfyui_transfer_mode
        )

        self.ui.ComfyUIIterateStatus.setText("Completed! Looking for output...")
        self.ui.ComfyUIIterateStatus.setStyleSheet("color: #10b981;")

        self.main_window.animator.update_status_animated(
            "Deadline: Job completed!",
            StatusColors.SUCCESS
        )

        # Find the most recent output file
        output_files = []
        network_dir = self._iterate_network_output_dir
        user_dir = self._iterate_user_output_dir

        self.log(f"[Iterate] Looking for output files...")
        self.log(f"[Iterate] Network dir: {network_dir}")
        self.log(f"[Iterate] User dir: {user_dir}")

        # Clean up temp files from network directory
        if network_dir:
            deleted = cleanup_job_temp_files(network_dir)
            if deleted:
                self.log(f"[Iterate] Cleaned up {deleted} temp files from network dir")

        # Check network directory first
        if network_dir:
            output_files = get_job_output_files(network_dir)
            if output_files:
                self.log(f"[Iterate] Found {len(output_files)} files in network dir")

                # Transfer files if different and enabled
                if user_dir and user_dir != network_dir and get_comfyui_transfer_to_user_folder():
                    transfer_mode = get_comfyui_transfer_mode()
                    self.log(f"[Iterate] Transferring files to user folder (mode: {transfer_mode})")
                    self.ui.ComfyUIIterateStatus.setText(
                        f"{'Copying' if transfer_mode == 'copy' else 'Moving'} files to user folder..."
                    )

                    transferred_files = transfer_outputs_to_user_folder(
                        network_dir, user_dir, transfer_mode
                    )
                    if transferred_files:
                        self.log(f"[Iterate] Transferred {len(transferred_files)} files to user folder")
                        output_files = transferred_files

        # If not found in network, check user directory
        if not output_files and user_dir and user_dir != network_dir:
            output_files = get_job_output_files(user_dir)
            if output_files:
                self.log(f"[Iterate] Found {len(output_files)} files in user dir")

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

    def _start_batch_polling(self, job_ids, network_output_dir, user_output_dir):
        """Start polling for batch job completion."""
        from ui_components import StatusColors

        self._batch_job_ids = list(job_ids)
        self._batch_pending_jobs = set(job_ids)
        self._batch_network_output_dir = network_output_dir
        self._batch_user_output_dir = user_output_dir
        self._batch_poll_count = 0

        self.log(f"[Batch] Starting polling for {len(job_ids)} job(s)")

        self.main_window.animator.update_status_animated(
            f"ComfyUI Batch: Monitoring {len(job_ids)} job(s)...",
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
        """Poll all pending batch jobs."""
        from ui_components import Worker
        from comfyui_service import poll_deadline_job_status

        if not self._batch_pending_jobs:
            self._stop_batch_polling()
            return

        # Poll each pending job
        for job_id in list(self._batch_pending_jobs):
            worker = Worker(poll_deadline_job_status, job_id)
            worker.signals.result.connect(lambda result, jid=job_id: self._on_batch_poll_result(jid, result))
            worker.signals.error.connect(lambda msg, tb, jid=job_id: self.log(f"[Batch] Poll error for {jid}: {msg}"))
            QThreadPool.globalInstance().start(worker)

    def _on_batch_poll_result(self, job_id, result):
        """Handle batch poll result for a single job."""
        from ui_components import StatusColors

        status = result.get("status", "Unknown")
        progress = result.get("progress", 0)
        completed_tasks = result.get("completed_tasks", 0)
        total_tasks = result.get("total_tasks", 1)

        self._batch_poll_count += 1
        total_jobs = len(self._batch_job_ids)
        completed_jobs = total_jobs - len(self._batch_pending_jobs)

        self.log(f"[Batch Poll] Job {job_id}: {status} ({progress}%), Tasks: {completed_tasks}/{total_tasks}")

        if status == "Completed":
            self._batch_pending_jobs.discard(job_id)
            completed_jobs = total_jobs - len(self._batch_pending_jobs)
            self.log(f"[Batch] Job {job_id} completed, {len(self._batch_pending_jobs)} remaining")

            self.main_window.animator.update_status_animated(
                f"ComfyUI Batch: {completed_jobs}/{total_jobs} jobs completed",
                StatusColors.SUCCESS if not self._batch_pending_jobs else StatusColors.INFO
            )

            if not self._batch_pending_jobs:
                self._on_batch_jobs_completed()
        elif status == "Failed":
            self._batch_pending_jobs.discard(job_id)
            completed_jobs = total_jobs - len(self._batch_pending_jobs)
            self.log(f"[Batch] Job {job_id} failed, {len(self._batch_pending_jobs)} remaining")

            self.main_window.animator.update_status_animated(
                f"ComfyUI Batch: Job failed ({completed_jobs}/{total_jobs} done)",
                StatusColors.WARNING
            )

            if not self._batch_pending_jobs:
                self._on_batch_jobs_completed()
        else:
            # Still running
            dots = "." * ((self._batch_poll_count % 3) + 1)
            pending_count = len(self._batch_pending_jobs)

            if status in ("Active", "Rendering"):
                main_status = f"ComfyUI Batch: Rendering {completed_jobs}/{total_jobs} jobs{dots}"
            elif status in ("Pending", "Queued"):
                main_status = f"ComfyUI Batch: {pending_count} jobs queued{dots}"
            else:
                main_status = f"ComfyUI Batch: {status} ({completed_jobs}/{total_jobs}){dots}"

            self.main_window.animator.update_status_animated(main_status, StatusColors.INFO)

    def _stop_batch_polling(self):
        """Stop the batch poll timer."""
        if self._batch_poll_timer:
            self._batch_poll_timer.stop()

    def _on_batch_jobs_completed(self):
        """Handle batch jobs completion - cleanup and refresh gallery."""
        from ui_components import StatusColors
        from comfyui_service import (
            transfer_outputs_to_user_folder,
            cleanup_job_temp_files
        )
        from settings_manager import (
            get_comfyui_transfer_to_user_folder,
            get_comfyui_transfer_mode
        )

        self._stop_batch_polling()

        network_dir = self._batch_network_output_dir
        user_dir = self._batch_user_output_dir

        self.log(f"[Batch] All jobs completed!")
        self.log(f"[Batch] Network dir: {network_dir}")
        self.log(f"[Batch] User dir: {user_dir}")

        # Clean up temp files from network directory
        if network_dir:
            deleted = cleanup_job_temp_files(network_dir)
            if deleted:
                self.log(f"[Batch] Cleaned up {deleted} temp files from network dir")

        # Transfer files if enabled
        if network_dir and user_dir and user_dir != network_dir and get_comfyui_transfer_to_user_folder():
            transfer_mode = get_comfyui_transfer_mode()
            self.log(f"[Batch] Transferring files to user folder (mode: {transfer_mode})")

            transferred_files = transfer_outputs_to_user_folder(
                network_dir, user_dir, transfer_mode
            )
            if transferred_files:
                self.log(f"[Batch] Transferred {len(transferred_files)} files to user folder")

        # Update status
        self.main_window.animator.show_success("All ComfyUI jobs completed!")
        self.main_window.animator.update_status_animated(
            "ComfyUI: All jobs completed",
            StatusColors.SUCCESS
        )

    # =========================================================================
    # STATE PERSISTENCE
    # =========================================================================

    def _save_state(self):
        """Save the current ComfyUI tab state to user settings."""
        from settings_manager import save_comfyui_tab_state

        state = {
            "workflow_preset": self._current_preset_name or "",
            "output_directory": self.ui.ComfyUIOutputDir.text(),
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
            # No saved state - use defaults
            if self.app_state.shotpath:
                default_output = os.path.join(self.app_state.shotpath, "comfyui_output")
                self.ui.ComfyUIOutputDir.setText(default_output)
            return

        # Restore workflow preset selection
        preset_name = state.get("workflow_preset", "")
        if preset_name:
            presets = get_comfyui_workflow_presets()
            if preset_name in presets:
                self._select_preset(preset_name)

        # Restore output directory
        output_dir = state.get("output_directory", "")
        if output_dir:
            self.ui.ComfyUIOutputDir.setText(output_dir)
        elif self.app_state.shotpath:
            default_output = os.path.join(self.app_state.shotpath, "comfyui_output")
            self.ui.ComfyUIOutputDir.setText(default_output)

        # Restore generation count
        gen_count = state.get("generation_count", 1)
        self.ui.ComfyUIGenerationCount.setValue(gen_count)

        # Restore seed
        seed = state.get("seed", random.randint(0, 2147483647))
        self.ui.ComfyUISeed.setValue(seed)


        # Store editable values to apply after widgets are created
        self._pending_editable_values = state.get("editable_values", {})
