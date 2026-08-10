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
    QSizePolicy, QFrame
)
from PySide6.QtGui import QPixmap

from ..base_tab import BaseTab, TabConfig
from dialog_helpers import confirm_action
from ui_components import StatusColors
from .polling import PollingMixin
from .ui_manager import ComfyUIWidgetManager
from .state_manager import ComfyUIStateManager
from .inline_model_grid import InlineModelGrid
from .variant_selector import VariantSelector

logger = logging.getLogger(__name__)

from core.import_utils import get_event_bus
pipeline_events, EVENT_BUS_AVAILABLE = get_event_bus()


class ComfyUITab(PollingMixin, BaseTab):
    """Tab for ComfyUI AI image generation."""

    TAB_CONFIG = TabConfig(ui_file="comfyui.ui", tab_name="ComfyUI", tab_id="comfyui")

    def connect_signals(self):
        """Connect ComfyUI tab signals."""
        # Submit / generation
        self.ui.ComfyUISubmit.clicked.connect(self._on_submit_clicked)
        self.ui.ComfyUIGenerationCount.valueChanged.connect(self._on_generation_count_changed)
        self.ui.ComfyUISeed.valueChanged.connect(self._on_seed_changed)
        self.ui.ComfyUIRandomizeSeed.clicked.connect(self._on_randomize_seed)

        # Name field toggle and input
        self.ui.ComfyUINameToggle.toggled.connect(self._on_name_toggle_changed)
        self.ui.ComfyUIName.textChanged.connect(self._on_text_changed)

        # Iterate mode signals
        self.ui.ComfyUIUseAsInput.clicked.connect(self._on_use_as_input_clicked)

        # Cancel jobs button
        self.ui.ComfyUICancelJobs.clicked.connect(self._on_cancel_jobs_clicked)

        # Change model button (header bar)
        self.ui.changeModelBtn.clicked.connect(self._on_change_model_clicked)

        # Advanced settings gear
        self.ui.advancedGearBtn.clicked.connect(self._on_advanced_gear_clicked)

        # Workflow settings gear (in header)
        self.ui.workflowSettingsBtn.clicked.connect(self._on_workflow_settings_clicked)

        # Edit model button (in header, admin only)
        self.ui.editModelBtn.clicked.connect(self._on_edit_preset_clicked)

    def initialize(self):
        """Initialize ComfyUI tab."""
        # Create helper managers
        self.widget_manager = ComfyUIWidgetManager(
            self.main_window,
            self.app_state,
            self.ui.comfyuiEditableNodesLayout
        )
        self.state_manager = ComfyUIStateManager()

        # Setup inline model grid (replaces overlay picker)
        self._setup_inline_grid()

        # Setup variant selector (replaces radio buttons)
        self._setup_variant_selector()

        # Set up filename-safe validator on the Name field
        from PySide6.QtCore import QRegularExpression
        from PySide6.QtGui import QRegularExpressionValidator
        name_validator = QRegularExpressionValidator(
            QRegularExpression(r'[\w\- ]*'), self.ui.ComfyUIName
        )
        self.ui.ComfyUIName.setValidator(name_validator)

        # Initialize polling state from mixin
        self._init_polling_state()

        # Debounce timer for state saves (created once, not lazily)
        self._save_timer = QTimer(self.main_window)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_state)

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

        # Server behavior controls (per-job, persisted to user settings)
        self._setup_server_behavior_controls()

        # Server status banner (prominent, in submit section)
        self._setup_server_status_banner()

        # Auto-refresh server status every 30 seconds
        self._server_check_timer = QTimer(self.main_window)
        self._server_check_timer.timeout.connect(self._check_server_status)
        self._server_check_timer.start(30000)
        self._heartbeat_pending = False

        # Initial server status check (slight delay for startup)
        QTimer.singleShot(2000, self._check_server_status)

        # Start in grid state if no model selected
        if not self.state_manager.current_preset_name:
            self._show_model_grid()

    def on_tab_activated(self):
        """Called when tab becomes visible."""
        self._validate_inputs()
        # Refresh server status when tab becomes visible
        if hasattr(self, '_server_status_label'):
            self._check_server_status()

    # =========================================================================
    # SERVER STATUS (reads heartbeat file from network, written by server.py)
    # =========================================================================

    _HEARTBEAT_STALE_SECONDS = 60  # Heartbeat older than this = offline

    def _setup_server_behavior_controls(self):
        """Initialize server-offline behavior combo and wait timeout spinbox."""
        from core.settings_manager import safe_get_setting, safe_set_setting

        combo = self.ui.ServerBehaviorCombo
        combo.clear()
        combo.addItem("Fail Immediately", "fail")
        combo.addItem("Wait for Server", "wait")
        combo.addItem("Fail & Delete Job", "fail_delete")

        # Load persisted value
        saved = safe_get_setting("comfyui_server_not_found_behavior", "fail")
        idx = combo.findData(saved)
        if idx >= 0:
            combo.setCurrentIndex(idx)

        # Load wait timeout (stored in seconds, displayed in minutes)
        timeout_sec = safe_get_setting("comfyui_server_wait_timeout", 300)
        self.ui.ServerWaitTimeoutSpinBox.setValue(timeout_sec // 60)

        # Initial visibility
        self._update_server_wait_visibility()

        # Connect signals to persist on change
        combo.currentIndexChanged.connect(self._on_server_behavior_changed)
        self.ui.ServerWaitTimeoutSpinBox.valueChanged.connect(self._on_server_wait_timeout_changed)

    def _on_server_behavior_changed(self):
        """Save server behavior selection and update timeout visibility."""
        from core.settings_manager import safe_set_setting
        value = self.ui.ServerBehaviorCombo.currentData()
        safe_set_setting("comfyui_server_not_found_behavior", value)
        self._update_server_wait_visibility()

    def _on_server_wait_timeout_changed(self, minutes):
        """Save wait timeout (convert minutes to seconds for storage)."""
        from core.settings_manager import safe_set_setting
        safe_set_setting("comfyui_server_wait_timeout", minutes * 60)

    def _update_server_wait_visibility(self):
        """Show/hide wait timeout based on selected behavior."""
        is_wait = self.ui.ServerBehaviorCombo.currentData() == "wait"
        self.ui.ServerWaitTimeoutSpinBox.setVisible(is_wait)
        self.ui.serverWaitTimeoutLabel.setVisible(is_wait)

    def _setup_server_status_banner(self):
        """Create prominent server status banner in the submit section."""
        self._server_is_online = None  # Unknown initially

        # Use the serverStatusBanner frame from the .ui file
        banner = self.ui.serverStatusBanner

        # Status icon + text label
        self._server_status_label = QLabel("Checking server...")
        self._server_status_label.setStyleSheet(
            "color: #797e89; font-size: 12px; border: none;"
        )
        self.ui.serverStatusLayout.addWidget(self._server_status_label)
        self.ui.serverStatusLayout.addStretch()

        # Always show the banner
        banner.setVisible(True)
        banner.setStyleSheet(
            "QFrame#serverStatusBanner {"
            "  background-color: #2c313a;"
            "  border: 1px solid #3c414b;"
            "  border-radius: 6px;"
            "}"
        )

    def _check_server_status(self):
        """Read heartbeat file(s) from the network path to determine server status.

        Runs the file I/O on a worker thread to avoid blocking the Qt event loop
        when the network path is slow or unreachable. Skips if a previous check
        is still in flight.
        """
        if getattr(self, '_heartbeat_pending', False):
            return
        self._heartbeat_pending = True
        self.start_worker(
            self._read_heartbeat_status,
            on_result=self._on_heartbeat_result,
            on_error=self._on_heartbeat_error,
        )

    @staticmethod
    def _read_heartbeat_status():
        """Read heartbeat files from network path (runs on worker thread)."""
        from core.settings_manager import safe_get_setting
        from core.utils import load_json
        from datetime import datetime, timezone
        import glob

        stale_seconds = ComfyUITab._HEARTBEAT_STALE_SECONDS

        network_path = safe_get_setting("network_output_path", "")
        if not network_path:
            return ("unknown", "Network output path not configured")

        heartbeat_dir = os.path.join(network_path, '_server_status')
        if not os.path.isdir(heartbeat_dir):
            return ("offline", "No server heartbeat found")

        heartbeat_files = glob.glob(os.path.join(heartbeat_dir, 'heartbeat_*.json'))
        if not heartbeat_files:
            return ("offline", "No server heartbeat found")

        best_status = "offline"
        best_info = ""
        # UTC for safe cross-timezone comparison with the farm server.
        now = datetime.now(timezone.utc)

        for hb_file in heartbeat_files:
            data = load_json(hb_file, {})
            if not data or 'timestamp' not in data:
                continue

            try:
                ts = datetime.fromisoformat(data['timestamp'])
                # Older heartbeats wrote naive local time; assume UTC if naive
                # so we don't crash mixing aware/naive on subtraction.
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_seconds = (now - ts).total_seconds()
            except (ValueError, TypeError):
                continue

            status = data.get('status', 'offline')
            hostname = data.get('hostname', 'unknown')

            if age_seconds > stale_seconds:
                continue

            if status == "online":
                uptime = data.get('uptime_seconds', 0)
                jobs = data.get('jobs_completed', 0)
                best_status = "online"
                hours = uptime // 3600
                minutes = (uptime % 3600) // 60
                uptime_str = f"{hours}h {minutes}m" if hours else f"{uptime // 60}m" if uptime >= 60 else f"{uptime}s"
                best_info = (
                    f"Server: {hostname} | "
                    f"Uptime: {uptime_str} | "
                    f"Jobs completed: {jobs}"
                )
                break
            elif status == "starting":
                best_status = "starting"
                best_info = f"Server on {hostname} is loading models..."

        return (best_status, best_info)

    def _on_heartbeat_result(self, result):
        """Handle heartbeat check result on the main thread."""
        self._heartbeat_pending = False
        if not hasattr(self, '_server_status_label') or not self._server_status_label:
            return
        status, info = result
        self._update_server_indicator(status, info)

    def _on_heartbeat_error(self, error_msg, traceback_str=""):
        """Handle heartbeat check error."""
        self._heartbeat_pending = False
        if not hasattr(self, '_server_status_label') or not self._server_status_label:
            return
        self._update_server_indicator("unknown", f"Error checking server: {error_msg}")

    def _update_server_indicator(self, status: str, info: str):
        """Update the server status banner based on resolved status."""
        self._server_is_online = (status == "online")
        banner = self.ui.serverStatusBanner

        if status == "online":
            self._server_status_label.setText("\u25cf  Server Online")
            self._server_status_label.setStyleSheet(
                "color: #10b981; font-size: 12px; font-weight: bold; border: none;"
            )
            banner.setStyleSheet(
                "QFrame#serverStatusBanner {"
                "  background-color: rgba(16, 185, 129, 0.08);"
                "  border: 1px solid rgba(16, 185, 129, 0.25);"
                "  border-radius: 6px;"
                "}"
            )
            self._server_status_label.setToolTip(info)
        elif status == "starting":
            self._server_status_label.setText("\u25cf  Server Starting...")
            self._server_status_label.setStyleSheet(
                "color: #f59e0b; font-size: 12px; font-weight: bold; border: none;"
            )
            banner.setStyleSheet(
                "QFrame#serverStatusBanner {"
                "  background-color: rgba(245, 158, 11, 0.08);"
                "  border: 1px solid rgba(245, 158, 11, 0.25);"
                "  border-radius: 6px;"
                "}"
            )
            self._server_status_label.setToolTip(info)
        else:
            # Build helpful offline message
            behavior = self.ui.ServerBehaviorCombo.currentData()
            behavior_labels = {
                "wait": "Jobs will wait for server",
                "fail": "Jobs will fail immediately",
                "fail_delete": "Jobs will fail and be deleted",
            }
            behavior_text = behavior_labels.get(behavior, "")
            offline_text = f"\u25cf  Server Offline \u2014 {behavior_text}" if behavior_text else "\u25cf  Server Offline"
            self._server_status_label.setText(offline_text)
            self._server_status_label.setStyleSheet(
                "color: #ef4444; font-size: 12px; font-weight: bold; border: none;"
            )
            banner.setStyleSheet(
                "QFrame#serverStatusBanner {"
                "  background-color: rgba(239, 68, 68, 0.08);"
                "  border: 1px solid rgba(239, 68, 68, 0.25);"
                "  border-radius: 6px;"
                "}"
            )
            tip = info or "ComfyUI server is not responding"
            self._server_status_label.setToolTip(tip)

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

    def _on_node_info_error(self, error_msg, traceback_str=""):
        """Handle node info refresh failure."""
        logger.warning(f"Failed to refresh node info cache: {error_msg}")

    # =========================================================================
    # CONTEXTUAL TOOLTIPS & GUIDANCE
    # =========================================================================

    def _setup_tooltips(self):
        """Set up contextual tooltips for better user guidance."""
        self.ui.ComfyUIGenerationCount.setToolTip(
            "How many outputs to generate.\n"
            "Each one uses a different seed for variety."
        )
        self.ui.ComfyUISubmit.setToolTip(
            "Send to the render farm for processing.\n"
            "You can continue working while it renders."
        )
        self.ui.ComfyUICancelJobs.setToolTip(
            "Cancel all running jobs on the farm"
        )

    # =========================================================================
    # INLINE MODEL GRID (replaces full-screen overlay)
    # =========================================================================

    def _setup_inline_grid(self):
        """Set up the inline model grid directly in the tab."""
        self._model_grid = InlineModelGrid(parent=self.ui.modelGridContainer)
        self.ui.modelGridContainerLayout.addWidget(self._model_grid)
        self._model_grid.model_selected.connect(self._on_model_selected)
        self._model_grid.add_model_requested.connect(self._on_add_preset_clicked)
        self._model_grid.edit_model_requested.connect(self._on_edit_model_from_grid)
        self._model_grid.delete_model_requested.connect(self._on_delete_model_from_grid)

        # Initial load
        self._model_grid.refresh()

    def _setup_variant_selector(self):
        """Set up the variant selector for multi-workflow models."""
        self._variant_selector = VariantSelector(parent=self.ui.variantSelectorContainer)
        self.ui.variantSelectorLayout.addWidget(self._variant_selector)
        self._variant_selector.variant_selected.connect(self._on_workflow_selected)

    # =========================================================================
    # STATE MACHINE: Grid (A) ↔ Selected (B/C)
    # =========================================================================

    def _show_model_grid(self):
        """State A: Show the model grid, hide everything else."""
        self.ui.modelGridContainer.setVisible(True)
        self.ui.selectedModelHeader.setVisible(False)
        self.ui.variantSelectorContainer.setVisible(False)
        self.ui.noteBanner.setVisible(False)
        self.ui.comfyuiInputFrame.setVisible(False)
        self.ui.submitBar.setVisible(False)
        # The bottom verticalSpacer_comfy is Expanding and would eat all the
        # extra vertical space. Neutralize it so the model frame fills the tab.
        if hasattr(self.ui, 'verticalSpacer_comfy'):
            self.ui.verticalSpacer_comfy.changeSize(
                0, 0, QSizePolicy.Minimum, QSizePolicy.Minimum
            )
            self.ui.comfyuiLayout.invalidate()
        # Refresh grid to pick up any changes
        self._model_grid.refresh()

    def _show_selected_state(self):
        """State B/C: Show selected model header + inputs + submit bar."""
        self.ui.modelGridContainer.setVisible(False)
        self.ui.selectedModelHeader.setVisible(True)
        self.ui.submitBar.setVisible(True)
        # Restore the bottom spacer so content stays anchored to the top
        # in selected state (input frame's own verstretch=3 still dominates).
        if hasattr(self.ui, 'verticalSpacer_comfy'):
            self.ui.verticalSpacer_comfy.changeSize(
                0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding
            )
            self.ui.comfyuiLayout.invalidate()

        # Show edit button for admins
        self.ui.editModelBtn.setVisible(self.app_state.is_admin)

        # Update header with current model info
        self._update_selected_header()

        # Show variant selector if multi-workflow
        self._update_variant_selector()

        # Show note if present
        self._update_note_display()

        # Input frame visibility depends on whether there are editable widgets
        has_widgets = len(self.widget_manager.dynamic_widgets) > 0
        self.ui.comfyuiInputFrame.setVisible(has_widgets)

    def _update_selected_header(self):
        """Update the selected model header bar with current model info."""
        from comfyui.presets_manager import get_comfyui_workflow_presets, get_workflow_preset_config

        name = self.state_manager.current_preset_name
        if not name:
            return

        display_name = self._get_preset_display_name(name)
        self.ui.selectedModelName.setText(display_name)

        # Get preset config for badge and description
        presets = get_comfyui_workflow_presets()
        preset_data = presets.get(name, {})
        if isinstance(preset_data, str):
            preset_data = {"path": preset_data}

        config = get_workflow_preset_config(
            name, selected_workflow=self.state_manager.current_selected_workflow
        ) or {}

        # Output type badge
        output_type = config.get("output_type", preset_data.get("output_type", "image"))
        type_labels = {
            "image": "IMAGE", "video": "VIDEO", "3d": "3D MODEL",
            "audio": "AUDIO", "other": "OTHER",
        }
        type_colors = {
            "image": ("#4a9eff", "rgba(74, 158, 255, 0.15)"),
            "video": ("#a855f7", "rgba(168, 85, 247, 0.15)"),
            "3d": ("#10b981", "rgba(16, 185, 129, 0.15)"),
            "audio": ("#f59e0b", "rgba(245, 158, 11, 0.15)"),
            "other": ("#797e89", "rgba(121, 126, 137, 0.15)"),
        }
        fg, bg = type_colors.get(output_type, type_colors["image"])
        self.ui.selectedModelBadge.setText(type_labels.get(output_type, "IMAGE"))
        self.ui.selectedModelBadge.setStyleSheet(
            f"background-color: {bg}; color: {fg};"
            "border-radius: 3px; padding: 2px 8px;"
            "font-size: 10px; font-weight: bold;"
        )

        # Description (truncated)
        desc = preset_data.get("description", "")
        if len(desc) > 80:
            desc = desc[:77] + "..."
        self.ui.selectedModelDesc.setText(desc)

    def _on_change_model_clicked(self):
        """Handle [Change] button — go back to model grid."""
        self._show_model_grid()

    # Keep old method name as stub for backward compatibility
    def _setup_model_info_card(self):
        """Legacy stub — info is now in the header bar."""
        pass

    def _setup_workflow_settings_button(self):
        """Legacy stub — gear is now in the header bar."""
        pass

    def _setup_input_empty_state(self):
        """Legacy stub — empty state is handled by hiding the input frame."""
        pass

    # Legacy stubs for methods that no longer exist in the new UI
    def _update_rating_widget(self):
        """Legacy stub — ratings removed from main flow."""
        pass

    def _update_model_info_card(self):
        """Legacy stub — info is in the header bar now."""
        self._update_selected_header()

    def _on_workflow_settings_clicked(self):
        """Show the workflow settings dialog."""
        self.widget_manager.show_settings_dialog()

    def _update_workflow_settings_button_visibility(self):
        """Show/hide the workflow settings gear in the header bar."""
        self.ui.workflowSettingsBtn.setVisible(self.widget_manager.has_settings_nodes)

    def _on_model_selected(self, model_name: str, workflow_name: str = ""):
        """Handle model selection from the inline grid.

        Args:
            model_name: The selected model/preset name
            workflow_name: The selected workflow name (for multi-workflow models)
        """
        # Store the workflow name if provided (for multi-workflow models)
        if workflow_name:
            self.state_manager.current_selected_workflow = workflow_name

        # Select the preset (this updates the UI and loads the workflow)
        self._select_preset(model_name)

    def _update_model_button_with_rating(self):
        """Legacy stub — now updates the header bar instead."""
        self._update_selected_header()

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
        from core.settings_manager import safe_get_setting

        network_path = safe_get_setting("network_output_path", "")
        if network_path:
            self.ui.ComfyUINetworkPathDisplay.setText(network_path)
            self.ui.ComfyUINetworkPathDisplay.setStyleSheet("color: #aaaaaa;")
        else:
            self.ui.ComfyUINetworkPathDisplay.setText("(Not configured - set in Settings tab)")
            self.ui.ComfyUINetworkPathDisplay.setStyleSheet("color: #888888; font-style: italic;")

    # =========================================================================
    # WORKFLOW SELECTOR (for multi-workflow models)
    # =========================================================================

    # =========================================================================
    # ADVANCED SETTINGS DIALOG (gear icon)
    # =========================================================================

    def _on_advanced_gear_clicked(self):
        """Show advanced settings as a popup dialog.

        The dialog reparents UI widgets from `comfyuiInputFrame` (seed, name,
        server-behavior combo, network path) into its own layout. When the
        dialog closes we put them back into their original layouts/positions
        so the main tab layout doesn't end up with empty slots.
        """
        if hasattr(self, '_advanced_dialog') and self._advanced_dialog and self._advanced_dialog.isVisible():
            self._advanced_dialog.raise_()
            return

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Advanced Settings")
        dialog.setMinimumWidth(380)
        dialog.setStyleSheet(
            "QDialog { background-color: #282c34; }"
            "QLabel { color: #c5cad3; font-size: 12px; }"
        )

        # Snapshot original (layout, index) for every widget we're about to
        # reparent, so closing the dialog can restore them in place.
        moved_widgets = []

        def _snapshot(widget):
            """Return (layout, index) for widget so we can re-insert later."""
            parent = widget.parentWidget()
            if parent is None:
                return None
            parent_layout = parent.layout()
            if parent_layout is None:
                return None
            for i in range(parent_layout.count()):
                item = parent_layout.itemAt(i)
                if item is not None and item.widget() is widget:
                    return (parent_layout, i)
            return None

        for w in (
            self.ui.ComfyUISeed,
            self.ui.ComfyUIRandomizeSeed,
            self.ui.ComfyUINameToggle,
            self.ui.ComfyUIName,
            self.ui.ServerBehaviorCombo,
            self.ui.serverWaitTimeoutLabel,
            self.ui.ServerWaitTimeoutSpinBox,
            self.ui.ComfyUINetworkPathDisplay,
        ):
            snap = _snapshot(w)
            if snap is not None:
                moved_widgets.append((w, snap))

        def _restore_widgets():
            for widget, (orig_layout, orig_idx) in moved_widgets:
                try:
                    orig_layout.insertWidget(orig_idx, widget)
                except RuntimeError:
                    pass

        dialog.finished.connect(lambda *_: _restore_widgets())

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Seed
        seed_row = QHBoxLayout()
        seed_row.setSpacing(8)
        seed_label = QLabel("Seed:")
        seed_label.setMinimumWidth(80)
        seed_row.addWidget(seed_label)
        seed_row.addWidget(self.ui.ComfyUISeed)
        self.ui.ComfyUISeed.setVisible(True)
        seed_row.addWidget(self.ui.ComfyUIRandomizeSeed)
        self.ui.ComfyUIRandomizeSeed.setVisible(True)
        try:
            from icons import IconManager, DEFAULT_ICON_COLOR
            self.ui.ComfyUIRandomizeSeed.setIcon(IconManager.get_icon("dice", DEFAULT_ICON_COLOR, 16))
        except Exception:
            pass
        layout.addLayout(seed_row)

        # Custom name
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.ui.ComfyUINameToggle.setVisible(True)
        name_row.addWidget(self.ui.ComfyUINameToggle)
        self.ui.ComfyUIName.setVisible(self.ui.ComfyUINameToggle.isChecked())
        name_row.addWidget(self.ui.ComfyUIName)
        layout.addLayout(name_row)

        # Server behavior
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #3c414b;")
        layout.addWidget(sep)

        server_row = QHBoxLayout()
        server_row.setSpacing(6)
        server_label = QLabel("If server offline:")
        server_row.addWidget(server_label)
        self.ui.ServerBehaviorCombo.setVisible(True)
        server_row.addWidget(self.ui.ServerBehaviorCombo)
        self.ui.serverWaitTimeoutLabel.setVisible(
            self.ui.ServerBehaviorCombo.currentData() == "wait"
        )
        server_row.addWidget(self.ui.serverWaitTimeoutLabel)
        self.ui.ServerWaitTimeoutSpinBox.setVisible(
            self.ui.ServerBehaviorCombo.currentData() == "wait"
        )
        server_row.addWidget(self.ui.ServerWaitTimeoutSpinBox)
        server_row.addStretch()
        layout.addLayout(server_row)

        # Network output path
        net_row = QHBoxLayout()
        net_label = QLabel("Output path:")
        net_label.setMinimumWidth(80)
        net_row.addWidget(net_label)
        self.ui.ComfyUINetworkPathDisplay.setVisible(True)
        net_row.addWidget(self.ui.ComfyUINetworkPathDisplay)
        layout.addLayout(net_row)

        layout.addStretch()

        # Close button
        from PySide6.QtWidgets import QDialogButtonBox
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)

        self._advanced_dialog = dialog
        dialog.show()

    def _update_variant_selector(self):
        """Update variant selector visibility based on current preset."""
        from comfyui.presets_manager import is_workflow_preset_multi, get_workflow_preset_subworkflows

        if not self.state_manager.current_preset_name:
            self._variant_selector.clear()
            self.ui.variantSelectorContainer.setVisible(False)
            return

        is_multi = is_workflow_preset_multi(self.state_manager.current_preset_name)

        if is_multi:
            workflows = get_workflow_preset_subworkflows(self.state_manager.current_preset_name)

            # Select the current or first workflow
            selected = self.state_manager.current_selected_workflow
            if not selected or selected not in workflows:
                selected = sorted(workflows.keys())[0]
                self.state_manager.current_selected_workflow = selected

            self._variant_selector.set_variants(workflows, selected)
            self.ui.variantSelectorContainer.setVisible(True)
        else:
            self._variant_selector.clear()
            self.ui.variantSelectorContainer.setVisible(False)

    # Keep old name as alias for backward compat
    def _update_workflow_selector_visibility(self):
        self._update_variant_selector()

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
        """Update the note/tip banner based on current preset/workflow."""
        from comfyui.presets_manager import get_workflow_preset_note

        if not self.state_manager.current_preset_name:
            self.ui.noteBanner.setVisible(False)
            return

        note = get_workflow_preset_note(
            self.state_manager.current_preset_name,
            selected_workflow=self.state_manager.current_selected_workflow
        )

        if note:
            self.ui.noteText.setText(note)
            self.ui.noteBanner.setVisible(True)
        else:
            self.ui.noteBanner.setVisible(False)

    # =========================================================================
    # GENERATION SETTINGS
    # =========================================================================

    def _on_generation_count_changed(self, value):
        """Handle generation count change."""
        self.ui.label_count_value.setText(str(value))
        self._validate_inputs()
        self._save_state()

        # Show time estimate if available
        if self.state_manager.current_preset_name:
            from core.user_preferences import get_workflow_estimated_time_per_frame
            from .polling import format_elapsed_time
            per_frame = get_workflow_estimated_time_per_frame(self.state_manager.current_preset_name)
            if per_frame:
                total = per_frame * value
                self.ui.label_count.setToolTip(
                    f"Estimated time: ~{format_elapsed_time(total)}\n"
                    f"({format_elapsed_time(per_frame)} per output)"
                )

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
        """Legacy stub — redirects to showing the model grid."""
        self._show_model_grid()

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

        # Check if this is a multi-workflow model
        is_multi = is_workflow_preset_multi(preset_name)

        if is_multi:
            workflows = get_workflow_preset_subworkflows(preset_name)
            if workflows:
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
            self.state_manager.current_selected_workflow = None
            workflow_path = get_comfyui_workflow_preset_path(preset_name)

        if workflow_path and os.path.exists(workflow_path):
            self.ui.ComfyUIWorkflowPath.setText(workflow_path)
            self.app_state.comfyui_workflow_path = workflow_path

            # Load per-workflow saved inputs
            saved_inputs = self.state_manager.load_per_workflow_inputs()
            if saved_inputs:
                self.widget_manager.pending_semantic_values = saved_inputs

            self._refresh_editable_nodes()
            self._validate_inputs()
            self._save_state()

            # Switch to selected state (header + inputs + submit)
            self._show_selected_state()
        else:
            self.ui.ComfyUIWorkflowPath.setText(f"Workflow file not found: {workflow_path}")
            self.app_state.comfyui_workflow_path = None
            self._refresh_editable_nodes()
            self._validate_inputs()
            self._show_selected_state()
            self.show_status(f"Workflow file not found: {workflow_path}", "error")

    def _on_add_preset_clicked(self):
        """Add a new workflow preset using the wizard."""
        from .add_model_wizard import AddModelWizard

        wizard = AddModelWizard(parent=self.main_window)
        if wizard.exec_() == QDialog.Accepted:
            model_name = wizard.field("model_name")
            if model_name:
                self._select_preset(model_name)
                self.show_status(f"Model '{model_name}' created", "success")
                # Refresh the inline grid
                if hasattr(self, '_model_grid'):
                    self._model_grid.refresh()

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

            # Refresh the UI with the (possibly new) preset name
            # Re-fetch presets in case name changed
            presets = get_comfyui_workflow_presets()

            # Find the current preset (may have been renamed)
            if current_name not in presets:
                # Name was changed — refresh the inline grid
                if hasattr(self, '_model_grid'):
                    self._model_grid.refresh()
            else:
                self.state_manager.current_selected_workflow = None
                self._select_preset(self.state_manager.current_preset_name)

    def _on_edit_model_from_grid(self, model_name):
        """Edit a model from the inline grid context menu."""
        from comfyui.editable import extract_editable_nodes
        from comfyui.presets_manager import get_comfyui_workflow_presets
        from .model_dialog import ModelDialog

        presets = get_comfyui_workflow_presets()
        preset = presets.get(model_name, {})
        if isinstance(preset, str):
            preset = {
                "path": preset, "description": "", "iteratable": False,
                "note": "", "node_overrides": {}, "is_multi": False,
            }

        dialog = ModelDialog(
            parent=self.main_window,
            model_name=model_name,
            preset_data=preset,
            main_window=self.main_window,
            extract_editable_nodes_func=extract_editable_nodes,
        )

        if dialog.exec_() == QDialog.Accepted:
            self.show_status(f"Model '{model_name}' updated", "success")
            if hasattr(self, '_model_grid'):
                self._model_grid.refresh()

    def _on_delete_model_from_grid(self, model_name):
        """Delete a model from the inline grid context menu."""
        from comfyui.presets_manager import delete_comfyui_workflow_preset
        from comfyui.ratings import delete_model_data

        if not confirm_action(
            "Delete Model",
            f"Delete model '{model_name}'?\n\nThis will also delete all rating data.",
            self.main_window,
        ):
            return

        delete_comfyui_workflow_preset(model_name)
        delete_model_data(model_name)
        self.show_status(f"Model '{model_name}' deleted", "success")

        # If the deleted model was currently selected, go back to grid
        if self.state_manager.current_preset_name == model_name:
            self.state_manager.current_preset_name = None
            self._show_model_grid()
        elif hasattr(self, '_model_grid'):
            self._model_grid.refresh()

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

        # Clear dangling prompt widget reference before widgets are recreated
        self._current_prompt_widget = None

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

        # Show/hide input frame based on whether editable widgets exist
        has_widgets = len(self.widget_manager.dynamic_widgets) > 0
        self.ui.comfyuiInputFrame.setVisible(has_widgets)

    def _connect_widget_signals(self):
        """Connect signals for dynamically created widgets.

        Each container is tagged with `_signals_connected` after its first
        wire-up so a subsequent `_refresh_editable_nodes` call (e.g. settings
        nodes refreshing without a full clear) doesn't accumulate duplicate
        connections that fire `_save_state` and `_on_text_changed` multiple
        times per change.
        """
        for node_id, container in self.widget_manager.dynamic_widgets.items():
            if getattr(container, '_signals_connected', False):
                continue
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
                    input_widget.stateChanged.connect(lambda state: self._save_state())

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

            container._signals_connected = True

        # Connect settings widget signals for auto-save
        for (node_id, widget_name), container in self.widget_manager.settings_widgets.items():
            if getattr(container, '_signals_connected', False):
                continue
            input_widget = getattr(container, 'input_widget', None)
            if not input_widget:
                continue
            if hasattr(input_widget, 'valueChanged'):
                input_widget.valueChanged.connect(self._on_text_changed)
            elif hasattr(input_widget, 'currentTextChanged'):
                input_widget.currentTextChanged.connect(self._on_text_changed)
            elif hasattr(input_widget, 'stateChanged'):
                input_widget.stateChanged.connect(lambda state: self._on_text_changed())
            container._signals_connected = True

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

    def _on_name_toggle_changed(self, checked):
        """Show/hide the custom name field based on toggle state.

        Preserves typed text when hidden so re-enabling restores it.
        """
        self.ui.ComfyUIName.setVisible(checked)
        self._on_text_changed()

    def _on_text_changed(self):
        """Handle text change in editable nodes - save state with debounce."""
        if not hasattr(self, '_save_timer'):
            return  # Called before initialize() — ignore
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
        from core.settings_manager import safe_get_setting

        workflow_ok = bool(self.app_state.comfyui_workflow_path)
        network_path_ok = bool(safe_get_setting("network_output_path", ""))
        self.ui.ComfyUISubmit.setEnabled(workflow_ok and network_path_ok)

    # =========================================================================
    # SUBMISSION
    # =========================================================================

    def _on_submit_clicked(self):
        """Submit the workflow to ComfyUI/Deadline."""
        from deadline.submitter import submit_comfyui_job
        from core.settings_manager import safe_get_setting
        from comfyui.presets_manager import get_workflow_preset_config
        from .polling import format_elapsed_time

        # Guard against double-submit (re-enabled in _on_submit_result/_on_submit_error)
        if not self.ui.ComfyUISubmit.isEnabled():
            return
        self.ui.ComfyUISubmit.setEnabled(False)

        # Immediately save state before submission (crash recovery)
        self._save_state()

        # Validate workflow
        if not self.app_state.comfyui_workflow_path:
            self.ui.ComfyUISubmit.setEnabled(True)
            self.show_status("No workflow selected", "error")
            return

        # Get network output path - always use user subfolder
        network_output_dir = safe_get_setting("network_output_path", "")
        if not network_output_dir:
            self.ui.ComfyUISubmit.setEnabled(True)
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

        # Inform user about server status when submitting
        if hasattr(self, '_server_is_online') and self._server_is_online is False:
            behavior = self.ui.ServerBehaviorCombo.currentData()
            behavior_msgs = {
                "wait": "ComfyUI: Server offline \u2014 job will wait for server to come online",
                "fail_delete": "ComfyUI: Server offline \u2014 job will fail and be deleted",
            }
            msg = behavior_msgs.get(behavior, "ComfyUI: Server offline \u2014 job will fail immediately")
            self.update_status_with_spinner(msg, StatusColors.WARNING, start=False)
        else:
            self.update_status_with_spinner(
                f"ComfyUI: Preparing {generation_count} generation(s)...",
                StatusColors.INFO, start=False
            )
        self.animate_button_click(self.ui.ComfyUISubmit)

        # Get seed value
        base_seed = self.ui.ComfyUISeed.value()

        logger.info(f"[ComfyUI] Network output path: {network_output_dir}")

        # Get full_restart and restart_lowvram from workflow config
        full_restart = workflow_config.get("full_restart", False) if workflow_config else False
        restart_lowvram = workflow_config.get("restart_lowvram", False) if workflow_config else False

        # Get output_type from workflow config (for metadata)
        output_type = workflow_config.get("output_type", "image") if workflow_config else "image"

        # Capture submission context before starting worker (bound via closure
        # so rapid double-submits don't overwrite the first callback's context)
        submit_context = {
            "network_output_dir": network_output_dir,
            "generation_count": generation_count,
            "output_type": output_type,
        }
        self._submit_context = submit_context

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
                "base_seed": base_seed,
                "network_output_dir": network_output_dir,
                "workflow_preset": self.state_manager.current_preset_name,
                "full_restart": full_restart,
                "restart_lowvram": restart_lowvram,
                "output_type": output_type,
                "custom_name": custom_name if custom_name else None,
            },
            on_result=lambda result, ctx=submit_context: self._on_submit_result(result, ctx),
            on_error=self._on_submit_error,
            on_progress=self._on_submit_progress
        )

    def _on_submit_result(self, result, ctx=None):
        """Handle ComfyUI job submission result."""

        self.ui.ComfyUISubmit.setEnabled(True)
        try:
            logger.debug(f"[ComfyUI] on_result called with: {result}")
            job_ids, error_msg = result
            if ctx is None:
                ctx = self._submit_context

            if job_ids:
                job_count = len(job_ids)
                total_gens = job_count * ctx["generation_count"]
                self.show_status(f"Submitted {job_count} job(s), {total_gens} generations", "success")
                self.update_status_with_spinner(
                    f"ComfyUI: {job_count} job(s) submitted",
                    StatusColors.SUCCESS, start=False
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
                self.update_status_with_spinner(
                    f"ComfyUI failed: {error_msg}",
                    StatusColors.ERROR, start=False
                )
        except Exception as e:
            import traceback
            logger.error(f"[ComfyUI] ERROR in on_result: {e}")
            logger.error(traceback.format_exc())

    def _on_submit_error(self, error_msg, traceback_str=""):
        """Handle ComfyUI job submission error."""

        self.ui.ComfyUISubmit.setEnabled(True)
        self.main_window.stop_status_spinner()
        self.show_status(f"Submission error: {error_msg}", "error")
        self.update_status_with_spinner(
            f"ComfyUI error: {error_msg}",
            StatusColors.ERROR, start=False
        )
        logger.error(f"ComfyUI submission error: {error_msg}")
        if traceback_str:
            logger.error(traceback_str)

    def _on_submit_progress(self, progress, message):
        """Handle ComfyUI job submission progress."""

        self.update_status_with_spinner(
            f"ComfyUI: {message}",
            StatusColors.INFO, start=False
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
        scannable_exts = set(COMFYUI_OUTPUT_EXTENSIONS)
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
        pipeline_events.use_as_input.connect(self._on_use_images_from_gallery)
        pipeline_events.copy_settings.connect(self.apply_settings_from_metadata)

        # Subscribe to our own job completion events
        pipeline_events.job_completed.connect(self._on_own_job_completed)
        pipeline_events.all_jobs_completed.connect(self._on_all_own_jobs_completed)

        logger.debug("ComfyUI tab subscribed to event bus")

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
