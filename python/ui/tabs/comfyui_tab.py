"""
ComfyUI tab module for Luma Tools.

Handles ComfyUI workflow submission and AI image generation.
Refactored to delegate business logic to helper classes.

Cross-tab communication:
- Subscribes to gallery selection events via PipelineEventBus
- Emits job events for gallery awareness
- Shows recent outputs panel for quick access to generated images
"""

import os
import random
import time
import logging

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMenu, QInputDialog, QDialog, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget,
    QSizePolicy
)
from PySide6.QtGui import QPixmap

from .base_tab import BaseTab
from dialog_helpers import confirm_action
from .comfyui_polling import PollingMixin
from .comfyui_ui_manager import ComfyUIWidgetManager
from .comfyui_state_manager import ComfyUIStateManager

logger = logging.getLogger(__name__)

from core.import_utils import get_event_bus
pipeline_events, EVENT_BUS_AVAILABLE = get_event_bus()


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
        # Create helper managers
        self.widget_manager = ComfyUIWidgetManager(
            self.main_window,
            self.app_state,
            self.ui.comfyuiEditableNodesLayout
        )
        self.state_manager = ComfyUIStateManager()

        # Create workflow selector dropdown (will be added to UI dynamically)
        self._setup_workflow_selector()
        self._setup_note_display()

        # Initialize polling state from mixin
        self._init_polling_state()

        # Display network path from global settings
        self._update_network_path_display()

        # Restore saved state
        self._restore_state()

        # Attempt to recover and resume any jobs that were running when app closed
        self._attempt_job_recovery()

        # Initial validation
        self._validate_inputs()

        # Hide add/edit model buttons from non-admin users
        if not self.app_state.is_admin:
            self.ui.ComfyUIAddPreset.setVisible(False)
            self.ui.ComfyUIEditPreset.setVisible(False)

        # Setup recent outputs panel (below submit buttons)
        self._setup_recent_outputs_panel()

        # Subscribe to event bus for cross-tab communication
        self._setup_event_bus_subscriptions()

    def on_tab_activated(self):
        """Called when tab becomes visible."""
        self._validate_inputs()

    # =========================================================================
    # NETWORK PATH DISPLAY
    # =========================================================================

    def _update_network_path_display(self):
        """Update the network path display label."""
        from core.settings_manager import get_setting

        network_path = get_setting("comfyui_network_output_path")
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
        # Add workflow selector to the existing button row instead of creating a new row
        if not hasattr(self.ui, 'comfyuiPresetButtonsLayout'):
            return

        # Add workflow label and combo to button row with proper stretch for symmetry
        self._workflow_label = QLabel("Workflow:")
        self._workflow_label.setVisible(False)
        self.ui.comfyuiPresetButtonsLayout.addWidget(self._workflow_label, 0)

        self._workflow_selector_combo = QtWidgets.QComboBox()
        self._workflow_selector_combo.setMinimumWidth(150)
        self._workflow_selector_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._workflow_selector_combo.currentTextChanged.connect(self._on_workflow_selected)
        self._workflow_selector_combo.setVisible(False)
        # Use stretch factor of 1 to maintain symmetry with the 3 buttons (each also having stretch 1)
        self.ui.comfyuiPresetButtonsLayout.addWidget(self._workflow_selector_combo, 1)

    def _setup_note_display(self):
        """Set up the note display area for showing model/workflow notes."""
        # Create note display widget (hidden by default)
        self._note_display_widget = QWidget()
        note_layout = QHBoxLayout(self._note_display_widget)
        note_layout.setContentsMargins(0, 0, 0, 2)
        note_layout.setSpacing(6)

        note_icon_label = QLabel("Note:")
        note_icon_label.setFixedWidth(70)
        note_icon_label.setStyleSheet("color: #4a9eff; font-weight: bold;")
        note_layout.addWidget(note_icon_label)

        self._note_display_label = QLabel("")
        self._note_display_label.setWordWrap(True)
        self._note_display_label.setStyleSheet("color: #aaaaaa; font-style: italic;")
        note_layout.addWidget(self._note_display_label, 1)

        self._note_display_widget.setVisible(False)

        # Insert into comfyuiWorkflowLayout after buttons and path label
        if hasattr(self.ui, 'comfyuiWorkflowLayout'):
            self.ui.comfyuiWorkflowLayout.addWidget(self._note_display_widget)

    def _update_workflow_selector_visibility(self):
        """Update workflow selector visibility based on current preset."""
        from comfyui.presets_manager import is_workflow_preset_multi, get_workflow_preset_subworkflows

        if not self.state_manager.current_preset_name:
            self._workflow_label.setVisible(False)
            self._workflow_selector_combo.setVisible(False)
            return

        is_multi = is_workflow_preset_multi(self.state_manager.current_preset_name)
        self._workflow_label.setVisible(is_multi)
        self._workflow_selector_combo.setVisible(is_multi)

        if is_multi:
            # Populate workflow options
            workflows = get_workflow_preset_subworkflows(self.state_manager.current_preset_name)
            self._workflow_selector_combo.blockSignals(True)
            try:
                self._workflow_selector_combo.clear()

                for wf_name in sorted(workflows.keys()):
                    self._workflow_selector_combo.addItem(wf_name)

                # Select first workflow by default or restore previously selected
                if self.state_manager.current_selected_workflow and self.state_manager.current_selected_workflow in workflows:
                    self._workflow_selector_combo.setCurrentText(self.state_manager.current_selected_workflow)
                elif workflows:
                    first_workflow = sorted(workflows.keys())[0]
                    self.state_manager.current_selected_workflow = first_workflow
                    self._workflow_selector_combo.setCurrentText(first_workflow)
            finally:
                self._workflow_selector_combo.blockSignals(False)

    def _on_workflow_selected(self, workflow_name):
        """Handle workflow selection change in multi-workflow model."""
        from comfyui.presets_manager import get_comfyui_workflow_preset_path, get_workflow_preset_config

        if not workflow_name:
            return

        # Capture current editable values BEFORE clearing widgets
        # This preserves prompts etc. when switching between workflows
        self.widget_manager.pending_semantic_values = self.widget_manager.capture_editable_values_by_type()

        self.state_manager.current_selected_workflow = workflow_name

        # Get the workflow path for this selection
        workflow_path = get_comfyui_workflow_preset_path(
            self.state_manager.current_preset_name,
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
        from comfyui.presets_manager import get_workflow_preset_note

        if not self.state_manager.current_preset_name:
            self._note_display_widget.setVisible(False)
            return

        note = get_workflow_preset_note(
            self.state_manager.current_preset_name,
            selected_workflow=self.state_manager.current_selected_workflow
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
        # Update the value label next to the slider
        self.ui.label_count_value.setText(str(value))
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
        from comfyui.presets_manager import get_comfyui_workflow_presets

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
                if full_name == self.state_manager.current_preset_name:
                    action.setCheckable(True)
                    action.setChecked(True)

            # Add folders as submenus
            for folder in sorted(folders.keys()):
                submenu = menu.addMenu(folder)
                for full_name, display_name in folders[folder]:
                    action = submenu.addAction(display_name)
                    action.setData(full_name)
                    if full_name == self.state_manager.current_preset_name:
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
        from comfyui.presets_manager import (
            get_comfyui_workflow_preset_path,
            is_workflow_preset_multi,
            get_workflow_preset_subworkflows
        )

        self.state_manager.current_preset_name = preset_name
        display_name = self._get_preset_display_name(preset_name)
        self.ui.ComfyUIChoosePreset.setText(display_name)

        # Check if this is a multi-workflow model
        is_multi = is_workflow_preset_multi(preset_name)

        if is_multi:
            # For multi-workflow models, update selector and select first workflow
            workflows = get_workflow_preset_subworkflows(preset_name)
            if workflows:
                # Reset selected workflow if switching presets
                if not self.state_manager.current_selected_workflow or self.state_manager.current_selected_workflow not in workflows:
                    self.state_manager.current_selected_workflow = sorted(workflows.keys())[0]

                workflow_path = get_comfyui_workflow_preset_path(
                    preset_name,
                    selected_workflow=self.state_manager.current_selected_workflow
                )
            else:
                workflow_path = None
                self.state_manager.current_selected_workflow = None
        else:
            # Single workflow model
            self.state_manager.current_selected_workflow = None
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
            self.ui.ComfyUIChoosePreset.setText(f"{display_name} (missing)")
            self.ui.ComfyUIWorkflowPath.setText(f"Workflow file not found: {workflow_path}")
            self.app_state.comfyui_workflow_path = None
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._update_note_display()
            # Guard for animator not being initialized yet during tab initialization
            self.show_status(f"Workflow file not found: {workflow_path}", "error")

    def _on_add_preset_clicked(self):
        """Add a new workflow preset."""
        from comfyui.presets_manager import (
            get_comfyui_workflow_presets,
            save_comfyui_workflow_preset
        )
        from file_dialogs import browse_file_with_memory

        # Use last browsed directory for workflows
        file_path = browse_file_with_memory(
            self.main_window,
            context="comfyui_workflow",
            title="Select ComfyUI Workflow",
            file_filter="ComfyUI JSON (*.json)",
            fallback_path=""
        )
        if not file_path:
            return

        # Ask for a preset name
        name, ok = QInputDialog.getText(
            self.main_window, "Add Workflow Preset",
            "Enter a name for this workflow preset:"
        )
        if not ok or not name:
            return

        name = name.strip()
        if not name:
            self.show_status("Preset name cannot be empty", "error")
            return

        # Check if preset already exists
        presets = get_comfyui_workflow_presets()
        if name in presets:
            if not confirm_action(
                "Overwrite Preset",
                f"Preset '{name}' already exists. Overwrite?",
                self.main_window
            ):
                return

        # Ask if workflow supports iterate mode
        iteratable = confirm_action(
            "Iterate Mode",
            "Does this workflow support Iterate mode?\n\n"
            "Iterate mode is automatically enabled when only 1 image is selected.\n"
            "It allows reviewing results and refining prompts between generations.",
            self.main_window
        )

        # Save the preset and select it
        save_comfyui_workflow_preset(name, file_path, iteratable=iteratable)
        self._select_preset(name)
        self.show_status(f"Workflow preset '{name}' saved", "success")

    def _on_edit_preset_clicked(self):
        """Edit the currently selected workflow preset."""
        from comfyui.editable import extract_editable_nodes
        from comfyui.presets_manager import (
            get_comfyui_workflow_presets,
            save_comfyui_workflow_preset,
            update_comfyui_workflow_preset,
            delete_comfyui_workflow_preset
        )
        from .comfyui_preset_editor import PresetEditorDialog

        if not self.state_manager.current_preset_name:
            self.show_status("No preset selected", "error")
            return

        presets = get_comfyui_workflow_presets()
        preset = presets.get(self.state_manager.current_preset_name, {})
        if isinstance(preset, str):
            preset = {
                "path": preset,
                "description": "",
                "iteratable": False,
                "note": "",
                "node_overrides": {},
                "is_multi": False
            }

        current_name = self.state_manager.current_preset_name

        # Create and show preset editor dialog
        dialog = PresetEditorDialog(
            parent=self.main_window,
            preset_name=current_name,
            preset_data=preset,
            main_window=self.main_window,
            extract_editable_nodes_func=extract_editable_nodes
        )

        if dialog.exec_() == QDialog.Accepted:
            result = dialog.get_result()
            if not result:
                return

            new_name = result["name"]
            new_path = result["path"]
            new_iteratable = result["iteratable"]
            new_note = result["note"]
            new_full_restart = result["full_restart"]
            new_node_overrides = result["node_overrides"]
            new_is_multi = result["is_multi"]
            new_workflows = result["workflows"]

            # Check if name changed and new name already exists
            if new_name != current_name:
                if new_name in presets:
                    self.show_status(f"A preset named '{new_name}' already exists", "error")
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
                self.state_manager.current_preset_name = new_name
                self.state_manager.current_selected_workflow = None
                self.ui.ComfyUIChoosePreset.setText(self._get_preset_display_name(new_name))
                self.show_status(f"Preset renamed to '{new_name}'", "success")
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
                self.show_status(f"Preset '{current_name}' updated", "success")

            # Refresh the UI with the (possibly new) preset name
            self.state_manager.current_selected_workflow = None
            self._select_preset(self.state_manager.current_preset_name)

    # =========================================================================
    # EDITABLE NODES
    # =========================================================================

    def _refresh_editable_nodes(self):
        """Refresh dynamic UI widgets based on editable nodes in the workflow."""
        from comfyui.presets_manager import get_workflow_preset_config

        # Get node overrides from current preset (supports both single and multi-workflow)
        node_overrides = {}
        if self.state_manager.current_preset_name:
            config = get_workflow_preset_config(
                self.state_manager.current_preset_name,
                selected_workflow=self.state_manager.current_selected_workflow
            )
            if config:
                node_overrides = config.get("node_overrides", {})

        # Use widget manager to refresh widgets
        self.widget_manager.refresh_editable_nodes(
            self.app_state.comfyui_workflow_path,
            node_overrides
        )

        # Connect signals for newly created widgets
        self._connect_widget_signals()

    def _connect_widget_signals(self):
        """Connect signals for dynamically created widgets."""
        for node_id, container in self.widget_manager.dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if not input_widget:
                continue

            node = getattr(container, 'editable_node', None)
            if not node:
                continue

            # Connect toggle change handler
            if node.widget_type == 'toggle':
                toggle_name = getattr(container, 'toggle_name', None)
                if toggle_name:
                    input_widget.stateChanged.connect(
                        lambda state, name=toggle_name: self.widget_manager.on_toggle_changed(state != 0, name)
                    )
                    input_widget.stateChanged.connect(lambda: self._save_state())

            # Connect text/image change handlers
            elif node.widget_type == 'text':
                # Connect preset button
                preset_btn = getattr(container, 'preset_btn', None)
                if preset_btn:
                    preset_btn.clicked.connect(
                        lambda checked=False, w=input_widget, btn=preset_btn, nt=getattr(container, 'node_type', ''):
                        self._on_prompt_preset_clicked(w, btn, nt)
                    )
                input_widget.textChanged.connect(self._on_text_changed)

            elif node.widget_type == 'image':
                input_widget.images_changed.connect(self._on_images_changed)

            elif node.widget_type == '3d_model':
                input_widget.textChanged.connect(self._on_text_changed)

            else:
                # Default widgets
                if hasattr(input_widget, 'textChanged'):
                    input_widget.textChanged.connect(self._on_text_changed)

    # =========================================================================
    # PROMPT PRESETS
    # =========================================================================

    def _on_prompt_preset_clicked(self, text_widget, button, node_type):
        """Show popup menu for prompt presets (per-node-type)."""
        from comfyui.presets_manager import get_comfyui_prompt_presets_for_node_type

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
        from comfyui.presets_manager import get_comfyui_prompt_presets_for_node_type

        presets = get_comfyui_prompt_presets_for_node_type(node_type)
        if preset_name in presets:
            text_widget.setPlainText(presets[preset_name])

    def _save_prompt_preset(self, text_widget, node_type):
        """Save current text as a new prompt preset for the node type."""
        from comfyui.presets_manager import save_comfyui_prompt_preset_for_node_type

        current_text = text_widget.toPlainText().strip()
        if not current_text:
            self.show_status("Cannot save empty preset", "error")
            return

        # Make node type more readable for display
        display_type = node_type.replace('Plus', '+')

        dialog = QInputDialog(self.main_window)
        dialog.setWindowTitle("Save Prompt Preset")
        dialog.setLabelText(f"Preset name (for {display_type} nodes):")
        dialog.setTextValue("")
        dialog.setWindowModality(Qt.WindowModal)

        if dialog.exec() == QInputDialog.Accepted:
            name = dialog.textValue().strip()
            if not name:
                self.show_status("Preset name cannot be empty", "error")
                return
            save_comfyui_prompt_preset_for_node_type(node_type, name, current_text)
            self.show_status(f"Preset '{name}' saved", "success")

    def _delete_prompt_preset(self, preset_name, node_type):
        """Delete a prompt preset for a node type."""
        from comfyui.presets_manager import delete_comfyui_prompt_preset_for_node_type

        # Make node type more readable for display
        display_type = node_type.replace('Plus', '+')

        if confirm_action(
            "Delete Preset",
            f"Delete prompt preset '{preset_name}' from {display_type} nodes?",
            self.main_window
        ):
            delete_comfyui_prompt_preset_for_node_type(node_type, preset_name)
            self.show_status(f"Preset '{preset_name}' deleted", "info")

    # =========================================================================
    # TEXT/IMAGE CHANGE HANDLERS
    # =========================================================================

    def _on_text_changed(self):
        """Handle text change in editable nodes - save state with debounce."""
        if not hasattr(self, '_save_timer'):
            self._save_timer = QTimer(self.main_window)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._save_state)
        # Restart timer on each change (200ms debounce for faster crash recovery)
        self._save_timer.start(200)

    def _on_images_changed(self, images):
        """Handle image selection changes - save the last browse directory."""
        from core.user_preferences import set_last_browse_directory

        if images:
            last_dir = os.path.dirname(images[0])
            set_last_browse_directory("comfyui_images", last_dir)

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_inputs(self):
        """Validate inputs and enable/disable submit button."""
        from core.settings_manager import get_setting

        workflow_ok = bool(self.app_state.comfyui_workflow_path)
        network_path_ok = bool(get_setting("comfyui_network_output_path"))
        self.ui.ComfyUISubmit.setEnabled(workflow_ok and network_path_ok)

    # =========================================================================
    # SUBMISSION
    # =========================================================================

    def _on_submit_clicked(self):
        """Submit the workflow to ComfyUI/Deadline."""
        from ui_components import StatusColors
        from deadline.submitter import submit_comfyui_job
        from core.settings_manager import get_setting
        from comfyui.presets_manager import get_workflow_preset_config

        # Immediately save state before submission (crash recovery)
        self._save_state()

        # Validate workflow
        if not self.app_state.comfyui_workflow_path:
            self.show_status("No workflow selected", "error")
            return

        # Get network output path - always use user subfolder
        network_output_dir = get_setting("comfyui_network_output_path")
        if not network_output_dir:
            self.show_status("Network output path not configured in Settings", "error")
            return

        network_output_dir = os.path.join(network_output_dir, self.app_state.user)
        self.log(f"[ComfyUI] Using user subfolder: {network_output_dir}")

        # Get generation count from UI
        generation_count = self.ui.ComfyUIGenerationCount.value()

        # Show time estimate if available
        if self.state_manager.current_preset_name:
            from core.user_preferences import get_workflow_estimated_time_per_frame
            from ui.tabs.comfyui_polling import format_elapsed_time
            per_frame = get_workflow_estimated_time_per_frame(self.state_manager.current_preset_name)
            if per_frame:
                total_estimate = per_frame * generation_count
                self.log(f"[ComfyUI] Estimated time: ~{format_elapsed_time(total_estimate)} ({generation_count} frame(s))")

        # Collect editable values using widget manager
        editable_values, selected_image_count = self.widget_manager.collect_editable_values()

        # Get workflow config (supports both single and multi-workflow models)
        workflow_config = get_workflow_preset_config(
            self.state_manager.current_preset_name,
            selected_workflow=self.state_manager.current_selected_workflow
        ) if self.state_manager.current_preset_name else None

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
        self.animator.update_status_animated(
            f"🎨 ComfyUI: Preparing {generation_count} generation(s)...",
            StatusColors.INFO
        )
        self.animator.animate_button_click(self.ui.ComfyUISubmit)

        # Server mode is always enabled (persistent ComfyUI)
        use_server_mode = True

        # Get seed value
        base_seed = self.ui.ComfyUISeed.value()

        self.log(f"[ComfyUI] Network output path: {network_output_dir}")

        # Get full_restart from workflow config
        full_restart = workflow_config.get("full_restart", False) if workflow_config else False

        # Store submission context for callbacks
        self._submit_context = {
            "network_output_dir": network_output_dir,
            "generation_count": generation_count,
        }

        # Use start_worker helper for cleaner code
        self.start_worker(
            submit_comfyui_job,
            worker_kwargs={
                "workflow_path": self.app_state.comfyui_workflow_path,
                "input_image": None,
                "prompt": None,
                "output_dir": network_output_dir,
                "generation_count": generation_count,
                "job_name": job_name,
                "editable_values": editable_values,
                "use_server_mode": use_server_mode,
                "base_seed": base_seed,
                "network_output_dir": network_output_dir,
                "workflow_preset": self.state_manager.current_preset_name,
                "full_restart": full_restart,
            },
            on_result=self._on_submit_result,
            on_error=self._on_submit_error,
            on_progress=self._on_submit_progress
        )

    def _on_submit_result(self, result):
        """Handle ComfyUI job submission result."""
        from ui_components import StatusColors

        try:
            self.log(f"[ComfyUI] on_result called with: {result}")
            job_ids, error_msg = result
            ctx = self._submit_context

            if job_ids:
                job_count = len(job_ids)
                total_gens = job_count * ctx["generation_count"]
                self.show_status(f"Submitted {job_count} job(s), {total_gens} generations", "success")
                self.animator.update_status_animated(
                    f"ComfyUI: {job_count} job(s) submitted",
                    StatusColors.SUCCESS
                )
                self.log(f"ComfyUI submission complete: {job_ids}")

                # Start polling for job completion
                self.log(f"[ComfyUI] Starting polling - iterate_mode={self.app_state.comfyui_iterate_mode}, job_count={len(job_ids)}")
                if self.app_state.comfyui_iterate_mode and len(job_ids) == 1:
                    self._start_iterate_polling(job_ids[0], ctx["network_output_dir"])
                else:
                    self._start_batch_polling(job_ids, ctx["network_output_dir"])
            else:
                self.main_window.stop_status_spinner()
                self.show_status(f"Submission failed: {error_msg}", "error")
                self.animator.update_status_animated(
                    f"ComfyUI failed: {error_msg}",
                    StatusColors.ERROR
                )
        except Exception as e:
            import traceback
            self.log(f"[ComfyUI] ERROR in on_result: {e}")
            self.log(traceback.format_exc())

    def _on_submit_error(self, error_tuple):
        """Handle ComfyUI job submission error."""
        from ui_components import StatusColors

        error_msg, traceback_str = self.unpack_worker_error(error_tuple)

        self.main_window.stop_status_spinner()
        self.show_status(f"Submission error: {error_msg}", "error")
        self.animator.update_status_animated(
            f"ComfyUI error: {error_msg}",
            StatusColors.ERROR
        )
        self.log(f"ComfyUI submission error: {error_msg}")
        if traceback_str:
            self.log(traceback_str)

    def _on_submit_progress(self, progress, message):
        """Handle ComfyUI job submission progress."""
        from ui_components import StatusColors

        self.animator.update_status_animated(
            f"🎨 ComfyUI: {message}",
            StatusColors.INFO
        )

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
        if not metadata:
            self.show_status("No settings metadata found for this image", "warning")
            return

        self.log(f"[ComfyUI] Applying settings from image metadata...")

        # Use state manager to apply metadata
        pending_values = self.state_manager.apply_settings_from_metadata(
            metadata, self.ui, self._select_preset
        )

        if pending_values:
            # Store pending values and try to apply them
            self.widget_manager.pending_editable_values = pending_values
            self.widget_manager._apply_pending_editable_values()
            self.log(f"[ComfyUI] Applied {len(pending_values)} editable value(s)")

        self.show_status("Settings applied from image", "success")

        # Switch to this tab
        self.main_window.switch_to_tab("comfyui")

    # =========================================================================
    # STATE PERSISTENCE
    # =========================================================================

    def _save_state(self):
        """Save the current ComfyUI tab state to user settings."""
        from core.settings_manager import set_setting

        state = self.state_manager.save_state(self.ui, self.widget_manager)
        set_setting("comfyui_tab_state", state, verbose=False)

    def _restore_state(self):
        """Restore the ComfyUI tab state from user settings."""
        from core.settings_manager import get_setting

        state = get_setting("comfyui_tab_state")
        pending_values = self.state_manager.restore_state(state, self.ui, self._select_preset)

        if pending_values:
            # Store pending values to apply after widgets are created
            self.widget_manager.pending_editable_values = pending_values

    # =========================================================================
    # RECENT OUTPUTS PANEL (Cross-tab awareness)
    # =========================================================================

    def _setup_recent_outputs_panel(self):
        """Set up the recent outputs preview panel below submit buttons."""
        from .comfyui_recent_outputs import RecentOutputsPanel

        self._recent_outputs_panel = RecentOutputsPanel()
        self._recent_outputs_panel.thumbnail_clicked.connect(self._on_recent_output_clicked)
        self._recent_outputs_panel.use_as_input.connect(self._on_recent_output_use_as_input)

        # Insert after the settingsAndSubmitLayout (before iterate frame)
        # The layout order is: Workflow, Input, SettingsAndSubmit, [INSERT HERE], IterateFrame, Spacer
        if hasattr(self.ui, 'comfyuiLayout'):
            # Find the iterate frame's index and insert before it
            layout = self.ui.comfyuiLayout
            iterate_index = -1
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget() == self.ui.comfyuiIterateFrame:
                    iterate_index = i
                    break

            if iterate_index >= 0:
                layout.insertWidget(iterate_index, self._recent_outputs_panel)
            else:
                # Fallback: add before spacer
                layout.insertWidget(layout.count() - 1, self._recent_outputs_panel)

        # Initialize with any existing recent outputs from app state
        self._refresh_recent_outputs_panel()

    def _refresh_recent_outputs_panel(self):
        """Refresh the recent outputs panel with current data."""
        if not hasattr(self, '_recent_outputs_panel'):
            return

        from core.state_manager import app_state

        # Get recent outputs from app state
        recent_outputs = app_state.comfyui_recent_outputs or []
        self._recent_outputs_panel.update_outputs(recent_outputs)

        # Get session stats
        stats = app_state.get_session_stats()
        total = stats.get('total_generated', 0)
        total_time = stats.get('total_time_seconds', 0.0)
        avg_time = total_time / total if total > 0 else 0.0
        self._recent_outputs_panel.update_stats(total, avg_time)

    def _on_recent_output_clicked(self, path: str):
        """Handle click on recent output thumbnail - open in gallery viewer."""
        gallery_tab = self.main_window.get_tab("gallery")
        if gallery_tab:
            self.main_window.switch_to_tab("gallery")
            gallery_tab._open_viewer(start_image=path)

    def _on_recent_output_use_as_input(self, path: str):
        """Handle drag/use as input request from recent output."""
        if not path or not os.path.exists(path):
            self.show_status("File not found", "error")
            return

        # Find an image input widget and add the image
        for node_id, container in self.widget_manager.dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget and hasattr(input_widget, 'add_images'):
                input_widget.add_images([path])
                self.show_status("Image added to input", "success")
                return

        self.show_status("No image input field in current workflow", "warning")

    # =========================================================================
    # EVENT BUS INTEGRATION (Cross-tab communication)
    # =========================================================================

    def _setup_event_bus_subscriptions(self):
        """Subscribe to event bus signals for cross-tab awareness."""
        if not EVENT_BUS_AVAILABLE:
            return

        # Subscribe to gallery events
        pipeline_events.selection_changed.connect(self._on_gallery_selection_changed)
        pipeline_events.use_as_input.connect(self._on_use_images_from_gallery)
        pipeline_events.copy_settings.connect(self.apply_settings_from_metadata)

        # Subscribe to our own job completion events to update recent outputs
        pipeline_events.job_completed.connect(self._on_own_job_completed)
        pipeline_events.all_jobs_completed.connect(self._on_all_own_jobs_completed)

        logger.debug("ComfyUI tab subscribed to event bus")

    def _on_gallery_selection_changed(self, selected_paths: list, selected_count: int):
        """Handle gallery selection change signal (currently unused)."""
        pass

    def _on_use_images_from_gallery(self, paths: list):
        """Handle request to use gallery images as inputs."""
        if not paths:
            return

        # Find an image input widget and add the images
        for node_id, container in self.widget_manager.dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget and hasattr(input_widget, 'add_images'):
                input_widget.add_images(paths)
                self.show_status(f"Added {len(paths)} image(s) to input", "success")
                return

        self.show_status("No image input field in current workflow", "warning")

    def _on_own_job_completed(self, job_id: str, output_paths: list):
        """Handle our own job completion - update recent outputs panel."""
        self._refresh_recent_outputs_panel()

    def _on_all_own_jobs_completed(self, total_outputs: int, elapsed_seconds: float):
        """Handle all jobs completed - final update to recent outputs panel."""
        self._refresh_recent_outputs_panel()
