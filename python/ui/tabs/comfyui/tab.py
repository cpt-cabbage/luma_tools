"""
ComfyUI tab module for Luma Tools.

Handles ComfyUI workflow submission and AI image generation.
Refactored to delegate business logic to helper classes.

Cross-tab communication:
- Subscribes to gallery selection events via PipelineEventBus
- Emits job events for gallery awareness
"""

import os
import re
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

from ..base_tab import BaseTab, TabConfig
from dialog_helpers import confirm_action
from .polling import PollingMixin
from .ui_manager import ComfyUIWidgetManager
from .state_manager import ComfyUIStateManager
from .model_picker_overlay import ModelPickerOverlay
from .star_rating import CompactStarRating

logger = logging.getLogger(__name__)

from core.import_utils import get_event_bus
pipeline_events, EVENT_BUS_AVAILABLE = get_event_bus()


class ComfyUITab(PollingMixin, BaseTab):
    """Tab for ComfyUI AI image generation."""

    TAB_CONFIG = TabConfig(ui_file="comfyui.ui", tab_name="ComfyUI", tab_id="comfyui")

    def connect_signals(self):
        """Connect ComfyUI tab signals."""
        from icons import IconManager, DEFAULT_ICON_COLOR

        # Model picker toggle
        self.ui.ComfyUIChoosePreset.clicked.connect(self._on_choose_preset_clicked)

        # Generation settings
        self.ui.ComfyUISubmit.clicked.connect(self._on_submit_clicked)
        self.ui.ComfyUIGenerationCount.valueChanged.connect(self._on_generation_count_changed)
        self.ui.ComfyUISeed.valueChanged.connect(self._on_seed_changed)
        self.ui.ComfyUIRandomizeSeed.clicked.connect(self._on_randomize_seed)
        self.ui.ComfyUIRandomizeSeed.setIcon(IconManager.get_icon("dice", DEFAULT_ICON_COLOR, 16))

        # Name field (debounced save)
        self.ui.ComfyUIName.textChanged.connect(self._on_text_changed)

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

        # Setup model picker (inline expandable panel)
        self._setup_model_picker()

        # Setup workflow settings button (next to model button)
        self._setup_workflow_settings_button()

        # Setup rating widget below model button
        self._setup_rating_widget()

        # Create workflow selector dropdown (will be added to UI dynamically)
        self._setup_workflow_selector()
        self._setup_note_display()

        # Set up filename-safe validator on the Name field
        from PySide6.QtCore import QRegularExpression
        from PySide6.QtGui import QRegularExpressionValidator
        name_validator = QRegularExpressionValidator(
            QRegularExpression(r'[\w\- ]*'), self.ui.ComfyUIName
        )
        self.ui.ComfyUIName.setValidator(name_validator)

        # Initialize polling state from mixin
        self._init_polling_state()

        # Display network path from global settings
        self._update_network_path_display()

        # Setup contextual tooltips for guidance
        self._setup_tooltips()

        # Setup session resume banner (shows if previous session available)
        self._setup_session_resume_banner()

        # Restore saved state
        self._restore_state()

        # Attempt to recover and resume any jobs that were running when app closed
        self._attempt_job_recovery()

        # Initial validation
        self._validate_inputs()

        # Subscribe to event bus for cross-tab communication
        self._setup_event_bus_subscriptions()

        # Deferred node_info cache check (give server time to start)
        QTimer.singleShot(5000, self._check_node_info_cache)

    def on_tab_activated(self):
        """Called when tab becomes visible."""
        self._validate_inputs()

    # =========================================================================
    # NODE INFO CACHE
    # =========================================================================

    def _check_node_info_cache(self):
        """Check if node_info cache needs refresh from network."""
        from comfyui.node_info import is_cache_available, is_cache_stale, load_cache_from_network

        if not is_cache_available() or is_cache_stale():
            logger.info("Node info cache is stale or missing, checking network cache...")
            self.start_worker(
                load_cache_from_network,
                on_result=self._on_node_info_refreshed,
                on_error=self._on_node_info_error,
            )
        else:
            from comfyui.node_info import get_cache_node_count
            logger.info(f"Node info cache OK ({get_cache_node_count()} node types)")

    def _on_node_info_refreshed(self, count):
        """Handle successful node info cache load."""
        if count > 0:
            logger.info(f"Node info cache refreshed: {count} node types loaded from network")
        else:
            logger.warning("Node info not available (farm server may not have run yet)")

    def _on_node_info_error(self, error):
        """Handle node info refresh failure."""
        logger.warning(f"Failed to refresh node info cache: {error}")

    # =========================================================================
    # CONTEXTUAL TOOLTIPS & GUIDANCE
    # =========================================================================

    def _setup_tooltips(self):
        """Set up contextual tooltips for better user guidance."""
        # Preset selection
        self.ui.ComfyUIChoosePreset.setToolTip(
            "Select a workflow preset.\n\n"
            "Each preset defines what kind of AI generation you want to do:\n"
            "• Image generation from text prompts\n"
            "• Image upscaling and enhancement\n"
            "• Style transfer and variations\n"
            "• Video generation"
        )

        # Generation count
        self.ui.ComfyUIGenerationCount.setToolTip(
            "Number of images to generate.\n\n"
            "Each generation uses a different seed for variety.\n"
            "Higher counts take longer but give more options."
        )

        # Seed control
        self.ui.ComfyUISeed.setToolTip(
            "Random seed for reproducibility.\n\n"
            "Same seed + same parameters = same result.\n"
            "Use this to recreate or iterate on specific outputs."
        )

        self.ui.ComfyUIRandomizeSeed.setToolTip(
            "Generate a new random seed.\n\n"
            "Click to get fresh, unpredictable results."
        )

        # Submit button
        self.ui.ComfyUISubmit.setToolTip(
            "Submit workflow to render farm.\n\n"
            "Jobs are processed by the Deadline render farm.\n"
            "You can continue working while jobs render."
        )

        # Cancel button
        self.ui.ComfyUICancelJobs.setToolTip(
            "Cancel all running jobs.\n\n"
            "Stops pending and rendering jobs on the farm."
        )

        # Network path
        self.ui.ComfyUINetworkPathDisplay.setToolTip(
            "Network output directory.\n\n"
            "Generated images are saved here.\n"
            "Configure in Settings tab."
        )

    def _setup_model_picker(self):
        """Set up the full-screen model picker overlay."""
        # Create the model picker overlay (parented to main window for full-screen)
        self._model_picker = ModelPickerOverlay(
            is_admin=self.app_state.is_admin,
            parent=self.main_window
        )

        # Connect signals
        self._model_picker.model_selected.connect(self._on_model_selected)
        self._model_picker.add_model_requested.connect(self._on_add_preset_clicked)

    def _setup_workflow_settings_button(self):
        """Set up the workflow settings button next to the model button."""
        from icons import IconManager, DEFAULT_ICON_COLOR

        self._workflow_settings_btn = QPushButton()
        self._workflow_settings_btn.setFixedWidth(40)
        self._workflow_settings_btn.setFixedHeight(32)
        self._workflow_settings_btn.setToolTip(
            "Workflow settings\n\n"
            "Adjust workflow-specific parameters like\n"
            "steps, guidance, denoise, etc."
        )
        self._workflow_settings_btn.setVisible(False)

        try:
            self._workflow_settings_btn.setIcon(
                IconManager.get_icon("settings", DEFAULT_ICON_COLOR, 16)
            )
        except Exception:
            self._workflow_settings_btn.setText("\u2699")

        self._workflow_settings_btn.clicked.connect(self._on_workflow_settings_clicked)

        # Insert after the model button (index 1 in preset buttons layout)
        self.ui.comfyuiPresetButtonsLayout.insertWidget(1, self._workflow_settings_btn, 0)

    def _setup_rating_widget(self):
        """Set up the interactive rating widget below the model button."""
        from .star_rating import StarRatingWidget

        # Create container widget for rating
        self._rating_container = QWidget()
        rating_layout = QHBoxLayout(self._rating_container)
        rating_layout.setContentsMargins(0, 4, 0, 4)
        rating_layout.setSpacing(8)

        # Label
        rating_label = QLabel("Your rating:")
        rating_label.setStyleSheet("color: #888; font-size: 11px;")
        rating_layout.addWidget(rating_label)

        # Star rating widget
        self._rating_widget = StarRatingWidget(
            rating=0.0,
            interactive=True,
            show_count=True,
            size=18
        )
        self._rating_widget.rating_changed.connect(self._on_model_rated)
        rating_layout.addWidget(self._rating_widget)

        rating_layout.addStretch()

        # Hide initially until a model is selected
        self._rating_container.setVisible(False)

        # Insert into workflow layout after the buttons (index 1, after comfyuiPresetButtonsLayout)
        if hasattr(self.ui, 'comfyuiWorkflowLayout'):
            self.ui.comfyuiWorkflowLayout.insertWidget(1, self._rating_container)

    def _on_model_rated(self, rating: int):
        """Handle user rating a model."""
        from comfyui.ratings import rate_model, get_model_rating

        if not self.state_manager.current_preset_name:
            return

        model_name = self.state_manager.current_preset_name
        username = self.app_state.user

        # Save rating
        if rate_model(model_name, username, rating):
            # Update rating widget with new average
            updated_data = get_model_rating(model_name)
            new_average = updated_data.get("average", 0.0)
            new_count = updated_data.get("rating_count", 0)

            self._rating_widget.set_rating(new_average)
            self._rating_widget.set_rating_count(new_count)

            # Update preset button display
            self._update_model_button_with_rating()

            self.show_status(f"Rated '{model_name}' {rating}/5 stars", "success")
            logger.info(f"[ComfyUITab] User rated '{model_name}': {rating}/5 (new avg: {new_average:.1f})")

    def _update_rating_widget(self):
        """Update the rating widget for the currently selected model."""
        from comfyui.ratings import get_model_rating

        if not self.state_manager.current_preset_name:
            self._rating_container.setVisible(False)
            return

        model_name = self.state_manager.current_preset_name
        username = self.app_state.user

        # Get rating data
        rating_data = get_model_rating(model_name)
        average = rating_data.get("average", 0.0)
        rating_count = rating_data.get("rating_count", 0)
        user_rating = rating_data.get("ratings", {}).get(username)

        # Update widget
        self._rating_widget.set_rating(average)
        self._rating_widget.set_rating_count(rating_count)

        # If user has already rated, set that as the displayed rating
        if user_rating:
            # Set the widget to show the user's rating
            # (the widget will update to show user rating visually)
            from .star_rating import StarRatingWidget
            # Update the internal stars to reflect user rating
            for i, star in enumerate(self._rating_widget._stars):
                star.set_fill_amount(1.0 if i < user_rating else 0.0)

        self._rating_container.setVisible(True)

    def _on_workflow_settings_clicked(self):
        """Show the workflow settings dialog."""
        self.widget_manager.show_settings_dialog()

    def _update_workflow_settings_button_visibility(self):
        """Show/hide the settings button based on whether settings nodes exist."""
        if hasattr(self, '_workflow_settings_btn'):
            self._workflow_settings_btn.setVisible(self.widget_manager.has_settings_nodes)

    def _on_model_selected(self, model_name: str, workflow_name: str):
        """Handle model selection from the overlay.

        Args:
            model_name: The selected model/preset name
            workflow_name: The selected workflow name (for multi-workflow models)
        """
        # The overlay hides itself on selection, no need to close here

        # Store the workflow name if provided (for multi-workflow models)
        if workflow_name:
            self.state_manager.current_selected_workflow = workflow_name

        # Select the preset (this updates the UI and loads the workflow)
        self._select_preset(model_name)

        # Update the button text to show the rating
        self._update_model_button_with_rating()

    def _update_model_button_with_rating(self):
        """Update the model button text to show name + rating stars."""
        from comfyui.ratings import get_model_rating

        if not self.state_manager.current_preset_name:
            self.ui.ComfyUIChoosePreset.setText("Choose Model")
            return

        # Get display name
        display_name = self._get_preset_display_name(self.state_manager.current_preset_name)

        # Get rating data
        rating_data = get_model_rating(self.state_manager.current_preset_name)
        average = rating_data.get("average", 0.0)

        if average > 0:
            # Format: "Model Name ★★★★☆ (4.2)"
            filled = int(round(average))
            stars = "★" * filled + "☆" * (5 - filled)
            self.ui.ComfyUIChoosePreset.setText(f"{display_name}  {stars} ({average:.1f})")
        else:
            self.ui.ComfyUIChoosePreset.setText(display_name)

    def _setup_session_resume_banner(self):
        """Set up the session resume banner if a previous session is available."""
        from empty_states import SessionResumeBanner

        # Check for recent sessions
        sessions = self.state_manager.get_recent_sessions()
        if not sessions:
            return

        # Get the most recent session
        recent_session = sessions[0]
        display_text = recent_session.get('display_text', 'Previous session')

        # Create and show the banner
        self._session_banner = SessionResumeBanner(display_text, session_index=0)
        self._session_banner.resume_clicked.connect(self._on_resume_session)
        self._session_banner.dismiss_clicked.connect(self._on_dismiss_session_banner)

        # Insert at the top of the main layout
        if hasattr(self.ui, 'comfyuiLayout'):
            self.ui.comfyuiLayout.insertWidget(0, self._session_banner)

    def _on_resume_session(self, session_index: int):
        """Handle click on session resume button."""
        pending_values = self.state_manager.restore_session(
            session_index, self.ui, self._select_preset
        )

        if pending_values:
            self.widget_manager.pending_editable_values = pending_values
            self.widget_manager._apply_pending_editable_values()

        # Get input images from session
        input_images = self.state_manager.get_session_input_images(session_index)
        if input_images:
            # Find image input widget and add images
            for node_id, container in self.widget_manager.dynamic_widgets.items():
                input_widget = getattr(container, 'input_widget', None)
                if input_widget and hasattr(input_widget, 'add_images'):
                    # Filter to existing files only
                    existing_images = [img for img in input_images if os.path.exists(img)]
                    if existing_images:
                        input_widget.add_images(existing_images)
                    break

        self.show_status("Session restored", "success")
        self._on_dismiss_session_banner()

    def _on_dismiss_session_banner(self):
        """Handle click on session banner dismiss button."""
        if hasattr(self, '_session_banner') and self._session_banner:
            self._session_banner.hide()
            self._session_banner.deleteLater()
            self._session_banner = None

    # =========================================================================
    # NETWORK PATH DISPLAY
    # =========================================================================

    def _update_network_path_display(self):
        """Update the network path display label."""
        from core.settings_manager import get_setting

        network_path = get_setting("network_output_path")
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

    def _update_auto_add_canvas_visibility(self):
        """Show/hide auto-add to canvas based on preset output type.

        Only image/video outputs can be added to canvas.
        """
        from comfyui.presets_manager import get_workflow_preset_output_type

        if not hasattr(self.ui, 'ComfyUIAutoAddToCanvas'):
            return

        # Get output type for current preset
        output_type = "image"  # Default
        if self.state_manager.current_preset_name:
            output_type = get_workflow_preset_output_type(self.state_manager.current_preset_name)

        # Show checkbox only for image/video outputs
        show_checkbox = output_type in ("image", "video")
        self.ui.ComfyUIAutoAddToCanvas.setVisible(show_checkbox)

        # Also uncheck if hidden to avoid unexpected behavior
        if not show_checkbox:
            self.ui.ComfyUIAutoAddToCanvas.setChecked(False)

    def _on_workflow_selected(self, workflow_name):
        """Handle workflow selection change in multi-workflow model."""
        from comfyui.presets_manager import get_comfyui_workflow_preset_path, get_workflow_preset_config

        if not workflow_name:
            return

        # Save current per-workflow inputs before switching
        self.state_manager.save_per_workflow_inputs(self.widget_manager)

        # Capture current editable values as cross-workflow fallback
        cross_workflow_values = self.widget_manager.capture_editable_values_by_type()

        self.state_manager.current_selected_workflow = workflow_name

        # Load per-workflow saved inputs for the new sub-workflow,
        # falling back to cross-workflow semantic values if no saved data
        saved_inputs = self.state_manager.load_per_workflow_inputs()
        if saved_inputs:
            self.widget_manager.pending_semantic_values = saved_inputs
        else:
            self.widget_manager.pending_semantic_values = cross_workflow_values

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
        """Show the full-screen model picker overlay."""
        # Set current selection for highlighting
        self._model_picker.set_current_model(self.state_manager.current_preset_name)
        # Show the overlay
        self._model_picker.show_overlay()

    def _select_preset(self, preset_name):
        """Select a workflow preset by name."""
        from comfyui.presets_manager import (
            get_comfyui_workflow_preset_path,
            is_workflow_preset_multi,
            get_workflow_preset_subworkflows
        )

        # Save current per-workflow inputs before switching
        self.state_manager.save_per_workflow_inputs(self.widget_manager)

        self.state_manager.current_preset_name = preset_name

        # Update button text with rating
        self._update_model_button_with_rating()

        # Update rating widget
        self._update_rating_widget()

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

            # Load per-workflow saved inputs for the new preset
            saved_inputs = self.state_manager.load_per_workflow_inputs()
            if saved_inputs:
                self.widget_manager.pending_semantic_values = saved_inputs

            self._refresh_editable_nodes()
            self._validate_inputs()
            self._update_note_display()
            self._update_auto_add_canvas_visibility()
            self._save_state()
        else:
            display_name = self._get_preset_display_name(preset_name)
            self.ui.ComfyUIChoosePreset.setText(f"{display_name} (missing)")
            self.ui.ComfyUIWorkflowPath.setText(f"Workflow file not found: {workflow_path}")
            self.app_state.comfyui_workflow_path = None
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._update_note_display()
            self._update_auto_add_canvas_visibility()
            # Guard for animator not being initialized yet during tab initialization
            self.show_status(f"Workflow file not found: {workflow_path}", "error")

    def _on_add_preset_clicked(self):
        """Add a new workflow preset using the wizard."""
        from .add_model_wizard import AddModelWizard

        wizard = AddModelWizard(parent=self.main_window)
        if wizard.exec_() == QDialog.Accepted:
            # Get the model name that was just created
            model_name = wizard.field("model_name")
            if model_name:
                self._select_preset(model_name)
                self.show_status(f"Model '{model_name}' created", "success")
                # Refresh the picker if it's visible
                if hasattr(self, '_model_picker'):
                    self._model_picker.refresh()

    def _on_edit_preset_clicked(self):
        """Edit the currently selected workflow preset."""
        from comfyui.editable import extract_editable_nodes
        from comfyui.presets_manager import get_comfyui_workflow_presets
        from .model_dialog import ModelDialog

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

        # Create and show model dialog (handles save internally)
        dialog = ModelDialog(
            parent=self.main_window,
            model_name=current_name,
            preset_data=preset,
            main_window=self.main_window,
            extract_editable_nodes_func=extract_editable_nodes
        )

        if dialog.exec_() == QDialog.Accepted:
            self.show_status(f"Model '{current_name}' updated", "success")

            # Update auto-add to canvas visibility based on output type
            self._update_auto_add_canvas_visibility()

            # Refresh the UI with the (possibly new) preset name
            # Re-fetch presets in case name changed
            presets = get_comfyui_workflow_presets()

            # Find the current preset (may have been renamed)
            if current_name not in presets:
                # Name was changed, find the new name by looking for the preset
                # that was just modified (most recent save)
                # For simplicity, just refresh the combo
                self._refresh_presets_combo()
            else:
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

        # Also refresh settings nodes (dialog)
        self.widget_manager.refresh_settings_nodes(
            self.app_state.comfyui_workflow_path,
            node_overrides
        )

        # Clear pending semantic values now that both widget types have been processed
        self.widget_manager.pending_semantic_values = {}

        # Update settings button visibility
        self._update_workflow_settings_button_visibility()

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

            elif node.widget_type == 'video':
                input_widget.images_changed.connect(self._on_images_changed)

            else:
                # Default widgets
                if hasattr(input_widget, 'textChanged'):
                    input_widget.textChanged.connect(self._on_text_changed)

        # Connect settings widget signals for auto-save
        for (node_id, widget_name), container in self.widget_manager.settings_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if not input_widget:
                continue
            if hasattr(input_widget, 'valueChanged'):
                input_widget.valueChanged.connect(self._on_text_changed)
            elif hasattr(input_widget, 'currentTextChanged'):
                input_widget.currentTextChanged.connect(self._on_text_changed)
            elif hasattr(input_widget, 'stateChanged'):
                input_widget.stateChanged.connect(lambda: self._on_text_changed())

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

        # Add prompt builder option
        builder_action = menu.addAction("Use Prompt Builder...")
        builder_action.triggered.connect(
            lambda checked=False, w=text_widget, nt=node_type: self._on_prompt_builder_clicked(w, nt)
        )
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

    def _on_prompt_builder_clicked(self, text_widget, node_type):
        """Show the prompt builder overlay."""
        # Lazy-create overlay if not exists
        if not hasattr(self, '_prompt_builder_overlay') or self._prompt_builder_overlay is None:
            from .prompt_builder_overlay import PromptBuilderOverlay
            self._prompt_builder_overlay = PromptBuilderOverlay(self.main_window)
            self._prompt_builder_overlay.prompt_generated.connect(self._on_prompt_generated)

        # Store current text widget for later
        self._current_prompt_widget = text_widget

        # Pre-populate with current text
        current_text = text_widget.toPlainText()

        # Pass model and workflow names for context (filename generation)
        model_name = self.state_manager.current_preset_name
        workflow_name = getattr(self.state_manager, 'current_selected_workflow', None)

        self._prompt_builder_overlay.show_overlay(
            initial_text=current_text,
            model_name=model_name,
            workflow_name=workflow_name
        )

    def _on_prompt_generated(self, positive_prompt, negative_prompt, json_output):
        """Handle prompt generated from builder."""
        # Use the stored text widget
        if not hasattr(self, '_current_prompt_widget') or self._current_prompt_widget is None:
            logger.warning("No text widget stored for prompt insertion")
            return

        # Set positive prompt
        self._current_prompt_widget.setPlainText(positive_prompt)

        # Store JSON output for potential later use
        self._last_prompt_json = json_output
        logger.info(f"Prompt generated with JSON settings: {json_output.get('settings', {})}")

        # TODO: Handle negative prompt if negative text widget exists
        # For now, we only update the positive prompt that was clicked

        self.show_status("Prompt inserted from builder", "success")
        logger.info(f"Inserted prompt from builder: {len(positive_prompt)} chars")

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
        """Handle image selection changes - save the last browse directory and trigger state save."""
        from core.user_preferences import set_last_browse_directory

        if images:
            last_dir = os.path.dirname(images[0])
            set_last_browse_directory("comfyui_images", last_dir)

        # Trigger debounced save so image selections are persisted per-workflow
        self._on_text_changed()

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_inputs(self):
        """Validate inputs and enable/disable submit button."""
        from core.settings_manager import get_setting

        workflow_ok = bool(self.app_state.comfyui_workflow_path)
        network_path_ok = bool(get_setting("network_output_path"))
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
        from .polling import format_elapsed_time

        # Immediately save state before submission (crash recovery)
        self._save_state()

        # Validate workflow
        if not self.app_state.comfyui_workflow_path:
            self.show_status("No workflow selected", "error")
            return

        # Get network output path - always use user subfolder
        network_output_dir = get_setting("network_output_path")
        if not network_output_dir:
            self.show_status("Network output path not configured in Settings", "error")
            return

        network_output_dir = os.path.join(network_output_dir, self.app_state.user)
        logger.info(f"[ComfyUI] Using user subfolder: {network_output_dir}")

        # Get generation count from UI
        generation_count = self.ui.ComfyUIGenerationCount.value()

        # Show time estimate if available
        if self.state_manager.current_preset_name:
            from core.user_preferences import get_workflow_estimated_time_per_frame
            per_frame = get_workflow_estimated_time_per_frame(self.state_manager.current_preset_name)
            if per_frame:
                total_estimate = per_frame * generation_count
                logger.info(f"[ComfyUI] Estimated time: ~{format_elapsed_time(total_estimate)} ({generation_count} frame(s))")

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
            logger.debug("[ComfyUI] Iterate mode enabled (1 image selected, workflow supports iteration)")
        else:
            logger.debug(f"[ComfyUI] Batch mode ({selected_image_count} images selected)")

        # Build job name from shot/project
        if self.app_state.shot and self.app_state.jobname:
            job_name = f"{self.app_state.jobname}_{self.app_state.shot}_luma_tools"
        elif self.app_state.shot:
            job_name = f"{self.app_state.shot}_luma_tools"
        elif self.app_state.jobname:
            job_name = f"{self.app_state.jobname}_luma_tools"
        else:
            job_name = "luma_tools_job"

        # Read optional custom name and prepend to job_name
        custom_name = self.ui.ComfyUIName.text().strip()
        if custom_name:
            # Sanitize: replace spaces with underscores, strip non-filename-safe chars
            sanitized_name = re.sub(r'[^\w\-]', '_', custom_name).strip('_')
            if sanitized_name:
                job_name = f"{sanitized_name}_{job_name}"

        # Show status bar progress (no overlay so user can still interact)
        self.main_window.start_status_spinner()
        self.animator.update_status_animated(
            f"ComfyUI: Preparing {generation_count} generation(s)...",
            StatusColors.INFO
        )
        self.animator.animate_button_click(self.ui.ComfyUISubmit)

        # Server mode is always enabled (persistent ComfyUI)
        use_server_mode = True

        # Get seed value
        base_seed = self.ui.ComfyUISeed.value()

        logger.info(f"[ComfyUI] Network output path: {network_output_dir}")

        # Get full_restart and restart_lowvram from workflow config
        full_restart = workflow_config.get("full_restart", False) if workflow_config else False
        restart_lowvram = workflow_config.get("restart_lowvram", False) if workflow_config else False

        # Get output_type from workflow config (for metadata)
        output_type = workflow_config.get("output_type", "image") if workflow_config else "image"

        # Store submission context for callbacks
        self._submit_context = {
            "network_output_dir": network_output_dir,
            "generation_count": generation_count,
            "output_type": output_type,
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
                "restart_lowvram": restart_lowvram,
                "output_type": output_type,
                "custom_name": custom_name if custom_name else None,
            },
            on_result=self._on_submit_result,
            on_error=self._on_submit_error,
            on_progress=self._on_submit_progress
        )

    def _on_submit_result(self, result):
        """Handle ComfyUI job submission result."""
        from ui_components import StatusColors

        try:
            logger.debug(f"[ComfyUI] on_result called with: {result}")
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
                logger.info(f"ComfyUI submission complete: {job_ids}")

                # Increment model usage count for rating system
                if self.state_manager.current_preset_name:
                    from comfyui.ratings import increment_model_usage
                    increment_model_usage(self.state_manager.current_preset_name)

                # Capture preset name for analytics recording in polling handlers
                self._current_preset_name = self.state_manager.current_preset_name

                # Start polling for job completion
                logger.info(f"[ComfyUI] Starting polling - iterate_mode={self.app_state.comfyui_iterate_mode}, job_count={len(job_ids)}")
                if self.app_state.comfyui_iterate_mode and len(job_ids) == 1:
                    self._start_iterate_polling(job_ids[0], ctx["network_output_dir"], ctx["output_type"])
                else:
                    self._start_batch_polling(job_ids, ctx["network_output_dir"], ctx["output_type"])
            else:
                self.main_window.stop_status_spinner()
                self.show_status(f"Submission failed: {error_msg}", "error")
                self.animator.update_status_animated(
                    f"ComfyUI failed: {error_msg}",
                    StatusColors.ERROR
                )
        except Exception as e:
            import traceback
            logger.error(f"[ComfyUI] ERROR in on_result: {e}")
            logger.error(traceback.format_exc())

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
        logger.error(f"ComfyUI submission error: {error_msg}")
        if traceback_str:
            logger.error(traceback_str)

    def _on_submit_progress(self, progress, message):
        """Handle ComfyUI job submission progress."""
        from ui_components import StatusColors

        self.animator.update_status_animated(
            f"ComfyUI: {message}",
            StatusColors.INFO
        )

    # =========================================================================
    # POLLING METHODS - See polling.py (PollingMixin)
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
                - source_images: List of input image basenames
                - source_models: List of input 3D model basenames
                - _output_dir: Directory where the output was saved (for finding source files)
        """
        if not metadata:
            self.show_status("No settings metadata found for this image", "warning")
            return

        # Debug: show what metadata keys we received
        logger.debug(f"[ComfyUI] Applying settings from metadata. Keys: {list(metadata.keys())}")
        if 'source_images' in metadata:
            logger.debug(f"[ComfyUI]   source_images: {metadata.get('source_images')}")
        if 'input_image' in metadata:
            logger.debug(f"[ComfyUI]   input_image: {metadata.get('input_image')}")
        if '_output_dir' in metadata:
            logger.debug(f"[ComfyUI]   _output_dir: {metadata.get('_output_dir')}")

        # Use state manager to apply metadata
        pending_values = self.state_manager.apply_settings_from_metadata(
            metadata, self.ui, self._select_preset
        )

        if pending_values:
            # Store pending values and try to apply them
            self.widget_manager.pending_editable_values = pending_values
            self.widget_manager._apply_pending_editable_values()
            logger.debug(f"[ComfyUI] Applied {len(pending_values)} editable value(s)")

        # Restore source images/models to input widgets
        self._restore_source_files_from_metadata(metadata)

        self.show_status("Settings applied from image", "success")

        # Switch to this tab
        self.main_window.select_tab_by_name("comfyui")

    def _restore_source_files_from_metadata(self, metadata):
        """Restore source images and models from metadata to input widgets.

        Args:
            metadata: Metadata dict with source_images, source_models, and _output_dir
        """
        output_dir = metadata.get('_output_dir', '')

        # Handle both new format (source_images list) and old format (input_image string)
        # Note: metadata may have None values, so we need to handle that
        source_images = metadata.get('source_images') or []
        if not source_images:
            # Fallback to input_image for backward compatibility
            input_image = metadata.get('input_image', '')
            if input_image:
                source_images = [input_image]

        source_models = metadata.get('source_models') or []

        if not output_dir:
            logger.warning("[ComfyUI] Cannot restore source files - no output directory in metadata")
            return

        if not source_images and not source_models:
            logger.debug("[ComfyUI] No source files found in metadata")
            return

        # Get source image hashes for hash-based fallback
        source_image_hashes = metadata.get('source_image_hashes') or {}

        # Build full paths for source files
        image_paths = []
        for basename in source_images:
            if not basename:
                continue
            full_path = os.path.join(output_dir, basename)
            if os.path.exists(full_path):
                image_paths.append(full_path)
            else:
                # Try hash-based fallback: scan directory for file with matching hash
                found_by_hash = self._find_file_by_hash(
                    output_dir, source_image_hashes.get(basename)
                )
                if found_by_hash:
                    image_paths.append(found_by_hash)
                    logger.info(f"[ComfyUI] Found source image by hash: {basename} -> {os.path.basename(found_by_hash)}")
                else:
                    logger.warning(f"[ComfyUI] Source image not found: {full_path}")

        model_paths = []
        for basename in source_models:
            if not basename:
                continue
            full_path = os.path.join(output_dir, basename)
            if os.path.exists(full_path):
                model_paths.append(full_path)
            else:
                # Try hash-based fallback for models too
                found_by_hash = self._find_file_by_hash(
                    output_dir, source_image_hashes.get(basename)
                )
                if found_by_hash:
                    model_paths.append(found_by_hash)
                    logger.info(f"[ComfyUI] Found source model by hash: {basename} -> {os.path.basename(found_by_hash)}")
                else:
                    logger.warning(f"[ComfyUI] Source model not found: {full_path}")

        # Find and populate input widgets
        for node_id, container in self.widget_manager.dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if not input_widget:
                continue

            node = getattr(container, 'editable_node', None)
            if not node:
                continue

            # Add images to image input widgets
            if node.widget_type == 'image' and image_paths:
                if hasattr(input_widget, 'set_images'):
                    input_widget.set_images(image_paths)
                    logger.info(f"[ComfyUI] Restored {len(image_paths)} source image(s) to node {node_id}")
                elif hasattr(input_widget, 'add_images'):
                    if hasattr(input_widget, 'clear_images'):
                        input_widget.clear_images()
                    input_widget.add_images(image_paths)
                    logger.info(f"[ComfyUI] Restored {len(image_paths)} source image(s) to node {node_id}")

            # Add models to 3D model input widgets
            elif node.widget_type == '3d_model' and model_paths:
                if hasattr(input_widget, 'setText'):
                    # For single model input (text field)
                    input_widget.setText(model_paths[0])
                    logger.info(f"[ComfyUI] Restored source model: {model_paths[0]}")

    @staticmethod
    def _find_file_by_hash(directory: str, expected_hash: str) -> str:
        """Scan directory for a file matching the expected content hash.

        Args:
            directory: Directory to scan
            expected_hash: SHA-256 hash to match

        Returns:
            Full path to matching file, or empty string if not found
        """
        if not expected_hash or not directory or not os.path.isdir(directory):
            return ""

        try:
            from comfyui.utils import compute_file_hash
        except ImportError:
            return ""

        # Scan all supported file types (images, videos, 3D models, audio)
        from core.config import COMFYUI_OUTPUT_EXTENSIONS
        scannable_exts = set(COMFYUI_OUTPUT_EXTENSIONS) | {
            '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.webp', '.exr',
        }
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not entry.is_file():
                        continue
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext not in scannable_exts:
                        continue
                    file_hash = compute_file_hash(entry.path)
                    if file_hash == expected_hash:
                        return entry.path
        except OSError:
            pass

        return ""

    # =========================================================================
    # STATE PERSISTENCE
    # =========================================================================

    def _save_state(self):
        """Save the current ComfyUI tab state to user settings."""
        from core.settings_manager import set_setting

        state = self.state_manager.save_state(self.ui, self.widget_manager)
        set_setting("comfyui_tab_state", state, verbose=False)

        # Also save per-workflow inputs
        self.state_manager.save_per_workflow_inputs(self.widget_manager)

    def _restore_state(self):
        """Restore the ComfyUI tab state from user settings."""
        from core.settings_manager import get_setting

        state = get_setting("comfyui_tab_state")
        if not state:
            return

        # Pre-load editable and settings values BEFORE restore_state() calls
        # _select_preset() which creates widgets and applies pending values.
        # This fixes the pre-existing bug where pending values were set after
        # widgets were already created and _apply_pending_editable_values() had run.
        editable_values = state.get("editable_values", {})
        if editable_values:
            # Split into editable vs settings values
            settings_vals = {k: v for k, v in editable_values.items() if k.startswith("settings_")}
            editable_vals = {k: v for k, v in editable_values.items() if not k.startswith("settings_")}
            if editable_vals:
                self.widget_manager.pending_editable_values = editable_vals
            if settings_vals:
                self.widget_manager.pending_settings_values = settings_vals

        # restore_state() calls _select_preset() which creates widgets;
        # pending values are now already set so they get applied during widget creation
        self.state_manager.restore_state(state, self.ui, self._select_preset)

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

        # Subscribe to our own job completion events
        pipeline_events.job_completed.connect(self._on_own_job_completed)
        pipeline_events.all_jobs_completed.connect(self._on_all_own_jobs_completed)

        logger.debug("ComfyUI tab subscribed to event bus")

    def _on_gallery_selection_changed(self, paths: list, count: int):
        """Handle gallery selection change event.

        This allows the ComfyUI tab to be aware of what's selected in the gallery.

        Args:
            paths: List of selected file paths
            count: Number of selected items
        """
        # Currently just for awareness - could enable features like
        # "Use Selected as Input" button when items are selected
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
        """Handle our own job completion."""
        pass

    def _on_all_own_jobs_completed(self, total_outputs: int, elapsed_seconds: float):
        """Handle all jobs completed."""
        pass
