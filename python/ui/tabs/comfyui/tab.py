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
import time
import logging

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import (
    QMenu, QInputDialog, QDialog, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget,
    QSizePolicy, QFrame, QToolButton
)
from PySide6.QtGui import QPixmap

from ..base_tab import BaseTab, TabConfig
from dialog_helpers import confirm_action
from ui_components import StatusColors
from .polling import PollingMixin
from .ui_manager import ComfyUIWidgetManager
from .state_manager import ComfyUIStateManager, read_seed, write_seed, random_seed
from .inline_model_grid import InlineModelGrid
from .variant_selector import VariantSelector

from core.design_tokens import Color, set_role

logger = logging.getLogger(__name__)

from core.import_utils import get_event_bus
pipeline_events, EVENT_BUS_AVAILABLE = get_event_bus()


# =============================================================================
# Worker functions for server control (no Qt access - they run off the GUI
# thread, because every one of them touches Deadline or the network share)
# =============================================================================

def _list_comfyui_workers():
    """The Deadline workers that run ComfyUI."""
    from deadline.server_job import list_group_workers
    from deadline.utils import resolve_comfyui_targeting

    _pool, group, _priority = resolve_comfyui_targeting()
    return list_group_workers(group)


def _read_server_state():
    """Per-worker heartbeat state."""
    from comfyui.server_status import read_server_heartbeats
    from core.settings_manager import safe_get_setting

    network_path = safe_get_setting("network_output_path", "")
    if not network_path:
        return {"servers": {}, "error": "Network output path not configured"}
    return {
        "servers": read_server_heartbeats(
            network_path, ComfyUITab._HEARTBEAT_STALE_SECONDS),
        "error": "",
    }


def _start_server_worker(worker):
    """Submit a server job."""
    from deadline.server_job import submit_server_job

    return submit_server_job(worker)


def _stop_server_worker(worker):
    """Stop the server job for a worker.

    Returns (ok, message). ok=False with message="no-job" means a server is
    running that Luma Tools did not start - typically one launched by hand.
    """
    from deadline.server_job import find_server_jobs, stop_server_job

    job_id = find_server_jobs().get(worker.lower())
    if not job_id:
        return (False, "no-job")
    return stop_server_job(job_id)


class ComfyUITab(PollingMixin, BaseTab):
    """Tab for ComfyUI AI image generation."""

    TAB_CONFIG = TabConfig(ui_file="comfyui.ui", tab_name="ComfyUI", tab_id="comfyui")

    def connect_signals(self):
        """Connect ComfyUI tab signals."""
        # Submit / generation
        self.ui.ComfyUISubmit.clicked.connect(self._on_submit_clicked)
        self.ui.ComfyUIGenerationCount.valueChanged.connect(self._on_generation_count_changed)
        self.ui.ComfyUIGenerationCountSpin.valueChanged.connect(self._on_generation_count_spin_changed)
        # Seed is a QLineEdit (64-bit seeds overflow a QSpinBox) — see state_manager.read_seed
        self.ui.ComfyUISeed.textChanged.connect(self._on_seed_changed)
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

        # Seed field is digits-only (19 digits covers the full 64-bit range)
        seed_validator = QRegularExpressionValidator(
            QRegularExpression(r'\d{0,19}'), self.ui.ComfyUISeed
        )
        self.ui.ComfyUISeed.setValidator(seed_validator)

        # Initialize polling state from mixin
        self._init_polling_state()

        # Guards the submit button. Using the button's own enabled state as the
        # lock didn't work: _validate_inputs() re-enables it, and it runs from
        # several signals including on_tab_activated — so tabbing away and back
        # mid-submit re-armed the button.
        self._submit_in_flight = False

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
        # Server control state must exist before the banner is built: that
        # method starts a worker whose callback reads these attributes.
        self._server_states = {}
        self._server_workers = []
        self._selected_worker = ""
        self._server_action = None
        self._server_action_started = 0.0
        self._server_restart_pending = False

        self._setup_server_status_banner()

        # Persistent submit failure banner (stays until the next submit)
        self._setup_submit_failure_banner()

        # Dice + auto-randomize toggle on the submit bar
        self._setup_submit_bar_seed_controls()

        # Keep the generation-count spinbox and slider in sync
        self._sync_generation_count_widgets()
        self._update_eta_display()

        # Auto-refresh server status every 30 seconds. initialize() is deferred
        # until the tab is first activated, so starting here is correct; the
        # timer is then paused/resumed by on_tab_deactivated/on_tab_activated.
        self._server_check_timer = QTimer(self.main_window)
        self._server_check_timer.timeout.connect(self._check_server_status)
        self._heartbeat_pending = False
        self._server_check_timer.start(30000)

        # Initial server status check (slight delay for startup)
        QTimer.singleShot(2000, self._check_server_status)

        # Start in grid state if no model selected
        if not self.state_manager.current_preset_name:
            self._show_model_grid()

    def on_tab_activated(self):
        """Called when tab becomes visible."""
        self._validate_inputs()
        # Resume the heartbeat poll and refresh immediately
        timer = getattr(self, '_server_check_timer', None)
        if timer and not timer.isActive():
            timer.start(30000)
        if hasattr(self, '_server_status_label'):
            self._check_server_status()

    def on_tab_deactivated(self):
        """Called when the tab is hidden — pause the 30s heartbeat poll.

        The heartbeat read hits the network share; there's no reason to keep
        paying for it while nobody is looking at the status banner.
        """
        timer = getattr(self, '_server_check_timer', None)
        if timer and timer.isActive():
            timer.stop()
            logger.debug("[ComfyUI] Tab hidden — paused server heartbeat polling")

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
        self._server_status_label.setProperty("textRole", "help")
        self.ui.serverStatusLayout.addWidget(self._server_status_label)
        self.ui.serverStatusLayout.addStretch()

        # Buttons live here rather than in comfyui.ui because this banner's
        # layout is populated programmatically (the status label above is too).
        self._server_start_button = QPushButton("Start Server")
        self._server_start_button.clicked.connect(self._on_start_server)
        self._server_stop_button = QPushButton("Stop")
        self._server_stop_button.clicked.connect(self._on_stop_server)
        self._server_restart_button = QPushButton("Restart")
        self._server_restart_button.clicked.connect(self._on_restart_server)

        for button in (self._server_start_button, self._server_stop_button,
                       self._server_restart_button):
            button.setProperty("density", "sm")
            button.setProperty("role", "secondary")
            button.setEnabled(False)
            self.ui.serverStatusLayout.addWidget(button)

        # Always show the banner
        banner.setVisible(True)
        banner.setProperty("variant", "subtle")

        # Which workers exist is a Deadline query - keep it off the GUI thread.
        self.start_worker(
            _list_comfyui_workers,
            on_result=self._on_workers_listed,
            on_error=lambda msg, tb="": logger.debug(f"Worker list unavailable: {msg}"),
        )

    # =========================================================================
    # SERVER CONTROL (start / stop / restart the farm server)
    # =========================================================================

    _SERVER_FAST_POLL_MS = 5000
    _SERVER_NORMAL_POLL_MS = 30000
    _SERVER_ACTION_TIMEOUT_S = 300

    def _on_workers_listed(self, workers):
        """Remember the ComfyUI group's workers (GUI thread)."""
        self._server_workers = workers or []
        if not self._selected_worker and self._server_workers:
            self._selected_worker = self._server_workers[0]
        self._update_server_controls()

    def _target_worker(self):
        """The worker the buttons act on.

        With one worker in the group there is nothing to choose. With several,
        prefer the one already running a server so Stop and Restart act on
        what the banner is reporting.
        """
        if self._selected_worker:
            return self._selected_worker
        for info in self._server_states.values():
            if info["status"] == "online" and not info["stale"]:
                return info["hostname"]
        return ""

    def _update_server_controls(self):
        """Drive button enablement from the heartbeat state."""
        if not hasattr(self, '_server_start_button'):
            return

        from core.config import DEADLINE_PATH

        if not DEADLINE_PATH:
            for button in (self._server_start_button, self._server_stop_button,
                           self._server_restart_button):
                button.setEnabled(False)
                button.setToolTip("Deadline is not available on this machine")
            return

        worker = self._target_worker()
        info = self._server_states.get(worker.lower(), {}) if worker else {}
        is_online = bool(info) and info.get("status") == "online" and not info.get("stale")
        busy = self._server_action is not None

        self._server_start_button.setEnabled(bool(worker) and not is_online and not busy)
        self._server_stop_button.setEnabled(is_online and not busy)
        self._server_restart_button.setEnabled(is_online and not busy)

        tip = f"Target worker: {worker}" if worker else "No ComfyUI workers found"
        for button in (self._server_start_button, self._server_stop_button,
                       self._server_restart_button):
            button.setToolTip(tip)

    def _set_server_poll(self, fast):
        """Poll the heartbeat faster while waiting for a state change."""
        timer = getattr(self, '_server_check_timer', None)
        if timer:
            timer.start(self._SERVER_FAST_POLL_MS if fast else self._SERVER_NORMAL_POLL_MS)

    def _on_start_server(self):
        worker = self._target_worker()
        if not worker:
            self.show_status("No ComfyUI workers found on Deadline", "warning")
            return
        self._server_action = "start"
        self._update_server_controls()
        self.show_status(f"Submitting ComfyUI server job for {worker}...", "info")
        self.start_worker(
            _start_server_worker, worker,
            on_result=self._on_server_started,
            on_error=self._on_server_action_error,
        )

    def _on_server_started(self, job_id):
        if not job_id:
            self._server_action = None
            self._update_server_controls()
            self.show_status("Deadline did not accept the server job", "error")
            return
        logger.info(f"ComfyUI server job submitted: {job_id}")
        self.show_status("Server job queued - waiting for it to come online...", "info")
        self._server_action_started = time.monotonic()
        self._set_server_poll(True)
        self._check_server_status()

    def _on_stop_server(self):
        worker = self._target_worker()
        if not worker:
            return
        if not confirm_action(
            "Stop ComfyUI Server",
            f"Stop the ComfyUI server on {worker}?\n\n"
            "Models loaded into VRAM will be discarded, and any ComfyUI job "
            "currently rendering on that worker will fail.",
            self.main_window,
        ):
            self._server_restart_pending = False
            return
        self._server_action = "stop"
        self._update_server_controls()
        self.show_status(f"Stopping the server on {worker}...", "info")
        self.start_worker(
            _stop_server_worker, worker,
            on_result=self._on_server_stopped,
            on_error=self._on_server_action_error,
        )

    def _on_server_stopped(self, result):
        ok, message = result
        if not ok and message == "no-job":
            # The heartbeat is real but Luma Tools did not start it - almost
            # always a server launched by hand on the worker itself.
            self._server_action = None
            self._server_restart_pending = False
            self._update_server_controls()
            self.show_status(
                "That server was not started from Luma Tools, so it must be "
                "stopped on the worker itself", "warning")
            return
        if not ok:
            self._server_action = None
            self._server_restart_pending = False
            self._update_server_controls()
            self.show_status(f"Could not stop the server: {message}", "error")
            return
        self.show_status("Server job completed - waiting for it to go offline...", "info")
        self._server_action_started = time.monotonic()
        self._set_server_poll(True)
        self._check_server_status()

    def _on_restart_server(self):
        """Stop, then start again once the heartbeat has gone."""
        self._server_restart_pending = True
        self._on_stop_server()
        if self._server_action is None:
            self._server_restart_pending = False

    def _on_server_action_error(self, error_msg, traceback_str=""):
        logger.error(f"Server control failed: {error_msg}")
        self._server_action = None
        self._server_restart_pending = False
        self._set_server_poll(False)
        self._update_server_controls()
        self.show_status(f"Server control failed: {error_msg}", "error")

    def _settle_server_action(self):
        """Resolve an in-flight start/stop against the latest heartbeat."""
        if self._server_action is None:
            return

        worker = self._target_worker()
        info = self._server_states.get(worker.lower(), {}) if worker else {}
        is_online = bool(info) and info.get("status") == "online" and not info.get("stale")
        elapsed = time.monotonic() - self._server_action_started

        if self._server_action == "start" and is_online:
            self._server_action = None
            self._set_server_poll(False)
            self.show_status(f"ComfyUI server online on {worker}", "success")
        elif self._server_action == "stop" and not is_online:
            self._server_action = None
            self._set_server_poll(False)
            if self._server_restart_pending:
                self._server_restart_pending = False
                self._on_start_server()
            else:
                self.show_status("ComfyUI server stopped", "success")
        elif elapsed > self._SERVER_ACTION_TIMEOUT_S:
            action = self._server_action
            self._server_action = None
            self._server_restart_pending = False
            self._set_server_poll(False)
            self.show_status(
                f"Server {action} did not settle within 5 minutes - check Deadline",
                "warning")
        self._update_server_controls()

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
            _read_server_state,
            on_result=self._on_heartbeat_result,
            on_error=self._on_heartbeat_error,
        )

    def _on_heartbeat_result(self, result):
        """Handle heartbeat check result on the main thread."""
        self._heartbeat_pending = False
        if not hasattr(self, '_server_status_label') or not self._server_status_label:
            return

        self._server_states = result.get("servers", {})
        status, info = self._summarise_servers(
            self._server_states, result.get("error", ""))
        self._update_server_indicator(status, info)
        self._update_server_controls()
        self._settle_server_action()

    def _summarise_servers(self, servers, error):
        """Turn per-worker heartbeats into (status, detail) for the banner.

        The old code collapsed every worker into one "best" status, so any
        server anywhere read as online even when the worker a job lands on had
        none. The count is now explicit.
        """
        if error:
            return ("unknown", error)

        total = len(self._server_workers) or len(servers)
        online = [i for i in servers.values()
                  if i["status"] == "online" and not i["stale"]]
        starting = [i for i in servers.values()
                    if i["status"] == "starting" and not i["stale"]]

        lines = []
        for info in sorted(servers.values(), key=lambda i: i["hostname"]):
            age = int(info["age_seconds"])
            uptime_min = int(info["uptime_seconds"]) // 60
            state = info["status"] if not info["stale"] else f"stale ({age}s)"
            lines.append(
                f"{info['hostname']}: {state} | up {uptime_min}m | "
                f"jobs {info['jobs_completed']}"
            )
        if not lines:
            lines.append("No server heartbeats found")
        detail = "\n".join(lines)

        if online:
            names = ", ".join(sorted(i["hostname"] for i in online))
            return ("online",
                    f"{len(online)} of {total} workers online - {names}\n\n{detail}")
        if starting:
            return ("starting", detail)
        return ("offline", detail)

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
            set_role(self._server_status_label, state="success")
            set_role(banner, variant="note", state="success")
            self._server_status_label.setToolTip(info)
        elif status == "starting":
            self._server_status_label.setText("\u25cf  Server Starting...")
            set_role(self._server_status_label, state="warning")
            set_role(banner, variant="note", state="warning")
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
            set_role(self._server_status_label, state="error")
            set_role(banner, variant="note", state="error")
            tip = info or "ComfyUI server is not responding"
            self._server_status_label.setToolTip(tip)

    # =========================================================================
    # PERSISTENT SUBMIT FAILURE BANNER
    # =========================================================================

    def _setup_submit_failure_banner(self):
        """Create the persistent banner used to surface submission failures.

        The transient status bar message scrolls away within seconds, so a
        failed submit could go completely unnoticed. This banner sits in the
        submit card and stays until the next submit attempt.
        """
        banner = QFrame(self.ui.comfyuiSubmitFrame)
        banner.setObjectName("comfyuiSubmitFailureBanner")
        banner.setVisible(False)
        banner.setProperty("variant", "note")
        banner.setProperty("state", "error")

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        label = QLabel("")
        label.setWordWrap(True)
        label.setProperty("textRole", "help")
        label.setProperty("state", "error")
        layout.addWidget(label, 1)

        dismiss = QPushButton("Dismiss")
        dismiss.setCursor(Qt.PointingHandCursor)
        dismiss.setProperty("role", "ghost")
        dismiss.setProperty("density", "sm")
        dismiss.clicked.connect(self._clear_submit_failure)
        layout.addWidget(dismiss, 0)

        self._submit_failure_banner = banner
        self._submit_failure_label = label

        # Insert directly under the server status banner (index 2 = after the
        # step header and the server banner), falling back to append.
        submit_layout = self.ui.comfyuiSubmitLayout
        try:
            submit_layout.insertWidget(2, banner)
        except (AttributeError, RuntimeError):
            submit_layout.addWidget(banner)

    def _show_submit_failure(self, message: str):
        """Show a submission failure in the persistent banner."""
        banner = getattr(self, '_submit_failure_banner', None)
        label = getattr(self, '_submit_failure_label', None)
        if not banner or not label:
            return
        label.setText(f"Submission failed: {message}")
        label.setToolTip(message)
        banner.setVisible(True)

    def _clear_submit_failure(self):
        """Hide the persistent submission failure banner."""
        banner = getattr(self, '_submit_failure_banner', None)
        if banner:
            banner.setVisible(False)

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

        # Refresh the estimated-time readout for the newly shown model
        self._update_eta_display()

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
            "image": (Color.ACCENT, Color.ACCENT_SUBTLE),
            "video": ("#a855f7", "rgba(168, 85, 247, 0.15)"),
            "3d": (Color.SUCCESS, "rgba(16, 185, 129, 0.15)"),
            "audio": (Color.WARNING, "rgba(245, 158, 11, 0.15)"),
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
            # Same split as _restore_state: settings widgets live in a separate
            # dict and are keyed with a "settings_" prefix.
            settings_vals = {k: v for k, v in pending_values.items()
                             if str(k).startswith("settings_")}
            editable_vals = {k: v for k, v in pending_values.items()
                             if not str(k).startswith("settings_")}
            if editable_vals:
                self.widget_manager.pending_editable_values = editable_vals
                self.widget_manager._apply_pending_editable_values()
            if settings_vals:
                self.widget_manager.pending_settings_values = settings_vals
                self.widget_manager._apply_pending_settings_values()

        # Get input images from session
        input_images = self.state_manager.get_session_input_images(session_index)
        if input_images:
            # Find image input widget and add images
            for widget_key, container in self.widget_manager.dynamic_widgets.items():
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
            set_role(self.ui.ComfyUINetworkPathDisplay, state=None)
        else:
            self.ui.ComfyUINetworkPathDisplay.setText("(Not configured - set in Settings tab)")
            set_role(self.ui.ComfyUINetworkPathDisplay, state="warning")

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
        sep.setProperty("variant", "divider")
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
        self._update_eta_display()
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

    def _sync_generation_count_widgets(self):
        """Push the slider's value into the spinbox without re-entering signals."""
        value = self.ui.ComfyUIGenerationCount.value()
        spin = self.ui.ComfyUIGenerationCountSpin
        if spin.value() != value:
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _on_generation_count_changed(self, value):
        """Handle generation count change from the slider."""
        self.ui.label_count_value.setText(str(value))
        self._sync_generation_count_widgets()
        self._update_eta_display()
        self._validate_inputs()
        self._save_state()

    def _on_generation_count_spin_changed(self, value):
        """Handle generation count change from the spinbox (drives the slider)."""
        slider = self.ui.ComfyUIGenerationCount
        if slider.value() != value:
            # The slider's valueChanged handler does the rest of the work.
            slider.setValue(value)

    def _get_time_estimate(self, count=None):
        """Return (per_frame_seconds, total_seconds) for the current preset, or None.

        Uses the recorded per-frame execution time for the selected workflow.
        """
        # May be called from a slider signal before initialize() has run.
        state_manager = getattr(self, 'state_manager', None)
        preset = state_manager.current_preset_name if state_manager else None
        if not preset:
            return None

        from core.user_preferences import get_workflow_estimated_time_per_frame
        per_frame = get_workflow_estimated_time_per_frame(preset)
        if not per_frame:
            return None

        if count is None:
            count = self.ui.ComfyUIGenerationCount.value()
        return per_frame, per_frame * count

    def _update_eta_display(self):
        """Show the estimated time as visible text next to the count slider.

        Previously this only lived in a tooltip, so the user had no way to see
        that 100 generations means hours of farm time before submitting.
        """
        from .polling import format_elapsed_time

        estimate = self._get_time_estimate()
        label = self.ui.ComfyUIEtaLabel
        if not estimate:
            label.setText("")
            label.setVisible(False)
            self.ui.label_count.setToolTip(
                "Number of images to generate. Each gets a different seed for variety."
            )
            return

        per_frame, total = estimate
        tooltip = (
            f"Estimated time: ~{format_elapsed_time(total)}\n"
            f"({format_elapsed_time(per_frame)} per output)"
        )
        label.setText(
            f"Estimated time: ~{format_elapsed_time(total)} "
            f"({format_elapsed_time(per_frame)} per output)"
        )
        label.setToolTip(tooltip)
        label.setVisible(True)
        self.ui.label_count.setToolTip(tooltip)

    def _on_seed_changed(self, _value=None):
        """Handle seed value change."""
        self._save_state()

    def _on_randomize_seed(self):
        """Generate a new random seed."""
        write_seed(self.ui, random_seed())

    # -------------------------------------------------------------------------
    # Submit-bar seed controls (dice + auto-randomize toggle)
    # -------------------------------------------------------------------------

    def _setup_submit_bar_seed_controls(self):
        """Add a dice button and auto-randomize toggle next to the submit button.

        Randomizing the seed used to require opening the advanced-settings gear
        dialog, which is the single most common per-submit tweak.
        """
        from core.settings_manager import safe_get_setting

        try:
            from icons import IconManager, DEFAULT_ICON_COLOR
        except Exception:  # pragma: no cover - icons are optional
            IconManager = None
            DEFAULT_ICON_COLOR = None

        dice = QToolButton(self.ui.comfyuiSubmitFrame)
        dice.setObjectName("ComfyUISubmitBarDice")
        dice.setFixedSize(42, 42)
        dice.setCursor(Qt.PointingHandCursor)
        dice.setToolTip("Randomize seed now")
        if IconManager:
            dice.setIcon(IconManager.get_icon("dice", DEFAULT_ICON_COLOR, 18))
            dice.setIconSize(QSize(18, 18))
        else:
            # QToolButton is icon-only by default — show the glyph instead.
            dice.setText("\U0001F3B2")
            dice.setToolButtonStyle(Qt.ToolButtonTextOnly)
        dice.clicked.connect(self._on_randomize_seed)
        self._submit_bar_dice = dice

        auto = QToolButton(self.ui.comfyuiSubmitFrame)
        auto.setObjectName("ComfyUIAutoRandomizeSeed")
        auto.setCheckable(True)
        auto.setFixedSize(42, 42)
        auto.setCursor(Qt.PointingHandCursor)
        auto.setText("AUTO")
        auto.setToolButtonStyle(Qt.ToolButtonTextOnly)
        auto.setToolTip(
            "Auto-randomize the seed on every submit.\n"
            "When off, the seed stays fixed until you randomize it manually."
        )
        auto.setChecked(bool(safe_get_setting("comfyui_auto_randomize_seed", False)))
        auto.toggled.connect(self._on_auto_randomize_toggled)
        self._auto_randomize_btn = auto

        layout = self.ui.submitButtonsLayout
        layout.addWidget(dice)
        layout.addWidget(auto)

    def _on_auto_randomize_toggled(self, checked):
        """Persist the auto-randomize-seed preference."""
        from core.settings_manager import safe_set_setting

        safe_set_setting("comfyui_auto_randomize_seed", bool(checked))
        logger.info(f"[ComfyUI] Auto-randomize seed {'enabled' if checked else 'disabled'}")

    def _is_auto_randomize_enabled(self) -> bool:
        """True when a new seed should be rolled before each submit."""
        btn = getattr(self, '_auto_randomize_btn', None)
        if btn is not None:
            return btn.isChecked()
        from core.settings_manager import safe_get_setting
        return bool(safe_get_setting("comfyui_auto_randomize_seed", False))


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
        for widget_key, container in self.widget_manager.dynamic_widgets.items():
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

            elif node.widget_type == 'audio':
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

    # Widget types that carry a file selection (BatchImageSelector-style)
    _FILE_INPUT_WIDGET_TYPES = ('image', 'video', 'audio')

    def _validate_inputs(self):
        """Validate inputs and enable/disable submit button.

        Returns:
            None when everything needed for a submit is present, otherwise a
            user-facing string explaining what is missing. The submit button is
            only hard-disabled for the two global blockers (no workflow, no
            network path); per-widget problems are reported at submit time so a
            late file selection can't leave the button stuck disabled.
        """
        from core.settings_manager import safe_get_setting

        workflow_ok = bool(self.app_state.comfyui_workflow_path)
        network_path_ok = bool(safe_get_setting("network_output_path", ""))
        # Never re-enable while a submit is in flight — this method runs from
        # several signals and would otherwise undo the double-submit guard.
        in_flight = getattr(self, '_submit_in_flight', False)
        self.ui.ComfyUISubmit.setEnabled(
            workflow_ok and network_path_ok and not in_flight
        )

        if not workflow_ok:
            return "No workflow selected"
        if not network_path_ok:
            return "Network output path not configured in Settings"

        return self._validate_dynamic_inputs()

    def _validate_dynamic_inputs(self):
        """Check the workflow's editable widgets for empty required inputs.

        Deliberately conservative — a false block is worse than a wasted farm
        job, so only two cases are flagged:

        * A file selector (image/video) with zero files. The workflow's baked-in
          default filename points at whatever was in the *authoring* machine's
          ComfyUI input folder, so relying on it is how jobs end up failing on
          the farm minutes after submit.
        * A text/prompt field that is empty with no workflow default, and only
          when it is the workflow's *sole* prompt input. Workflows routinely
          ship optional secondary prompts (negative prompts, MMAudio-style
          descriptions) that are legitimately left blank, so anything with more
          than one prompt field is left alone.

        Hidden (conditionally disabled) widgets are skipped entirely.

        Returns:
            A user-facing message, or None if nothing is blocking.
        """
        widget_manager = getattr(self, 'widget_manager', None)
        if not widget_manager:
            return None

        checked = 0
        problems = []
        empty_text_inputs = []
        text_input_count = 0

        for key, container in widget_manager.dynamic_widgets.items():
            node = getattr(container, 'editable_node', None)
            input_widget = getattr(container, 'input_widget', None)
            if not node or not input_widget:
                continue

            # Skip widgets hidden by an @if_ condition toggle
            try:
                if container.isHidden():
                    continue
            except RuntimeError:
                continue

            label = node.display_name or node.title or f"node {node.node_id}"

            if node.widget_type in self._FILE_INPUT_WIDGET_TYPES:
                checked += 1
                selected = getattr(input_widget, 'selected_files', None)
                if selected is not None and len(selected) == 0:
                    kind = node.widget_type
                    problems.append(f"'{label}' has no {kind} selected")

            elif node.widget_type == 'text':
                if not hasattr(input_widget, 'toPlainText'):
                    continue
                checked += 1
                text_input_count += 1
                if input_widget.toPlainText().strip():
                    continue
                # Empty is fine when the workflow itself supplies a default.
                if not str(node.current_value or "").strip():
                    empty_text_inputs.append(label)

        # Only treat an empty prompt as blocking when it's the workflow's only one.
        if text_input_count == 1 and empty_text_inputs:
            problems.append(
                f"'{empty_text_inputs[0]}' is empty and the workflow has no default prompt"
            )

        if not problems:
            # Routine path runs on every slider tick — keep it at debug.
            logger.debug(f"[ComfyUI] Validated {checked} input widget(s): all OK")
            return None

        logger.info(
            f"[ComfyUI] Validated {checked} input widget(s); "
            f"blocking problem(s): {problems}"
        )

        if len(problems) == 1:
            return f"Cannot submit — {problems[0]}."
        joined = "; ".join(problems)
        return f"Cannot submit — {joined}."

    # =========================================================================
    # SUBMISSION
    # =========================================================================

    def _collect_selected_input_files(self):
        """Every file currently chosen in the image/video selectors."""
        files = []
        for _key, container in self.widget_manager.dynamic_widgets.items():
            node = getattr(container, 'editable_node', None)
            input_widget = getattr(container, 'input_widget', None)
            if not node or not input_widget:
                continue
            if node.widget_type not in ('image', 'video'):
                continue
            files.extend(getattr(input_widget, 'selected_files', None) or [])
        return files

    def _save_resumable_session(self):
        """Persist the current setup as a resumable session (never fatal)."""
        try:
            saved = self.state_manager.save_current_session(
                self.ui,
                self.widget_manager,
                input_images=self._collect_selected_input_files(),
            )
            if saved:
                logger.debug("[ComfyUI] Saved resumable session")
        except Exception:
            # A session is a convenience; losing one must never block a submit.
            logger.warning("[ComfyUI] Could not save resumable session", exc_info=True)

    def _end_submit(self):
        """Release the submit guard and re-enable the button.

        Single exit point so every early return and both worker callbacks
        clear the in-flight flag — a missed one would wedge the button.
        """
        self._submit_in_flight = False
        self.ui.ComfyUISubmit.setEnabled(True)

    def _on_submit_clicked(self):
        """Submit the workflow to ComfyUI/Deadline."""
        from deadline.submitter import submit_comfyui_job
        from core.settings_manager import safe_get_setting
        from comfyui.presets_manager import get_workflow_preset_config
        from .polling import format_elapsed_time

        # Guard against double-submit (cleared in _on_submit_result/_on_submit_error)
        if getattr(self, '_submit_in_flight', False):
            logger.debug("[ComfyUI] Submit ignored — a submission is already in flight")
            return
        if not self.ui.ComfyUISubmit.isEnabled():
            return
        self._submit_in_flight = True
        self.ui.ComfyUISubmit.setEnabled(False)

        # Clear any failure left over from the previous attempt
        self._clear_submit_failure()

        # Roll a new seed before values are collected, so the submitted job and
        # the saved state agree on which seed was used.
        if self._is_auto_randomize_enabled():
            self._on_randomize_seed()
            logger.info(f"[ComfyUI] Auto-randomized seed to {read_seed(self.ui)}")

        # Immediately save state before submission (crash recovery)
        self._save_state()

        # Validate workflow
        if not self.app_state.comfyui_workflow_path:
            self._end_submit()
            self.show_status("No workflow selected", "error")
            return

        # Get network output path - always use user subfolder
        network_output_dir = safe_get_setting("network_output_path", "")
        if not network_output_dir:
            self._end_submit()
            self.show_status("Network output path not configured in Settings", "error")
            return

        # Validate the workflow's own inputs before we pay for a farm round-trip.
        # (Kept separate from _validate_inputs() so the double-submit guard above
        # isn't undone by that method re-enabling the button.)
        input_error = self._validate_dynamic_inputs()
        if input_error:
            self._end_submit()
            self.show_status(input_error, "error")
            self._show_submit_failure(input_error)
            logger.warning(f"[ComfyUI] Submit blocked by input validation: {input_error}")
            return

        network_output_dir = os.path.join(network_output_dir, self.app_state.user)
        logger.info(f"[ComfyUI] Using user subfolder: {network_output_dir}")

        # Get generation count from UI
        generation_count = self.ui.ComfyUIGenerationCount.value()

        # Show time estimate if available
        estimate = self._get_time_estimate(generation_count)
        total_estimate = estimate[1] if estimate else None
        if total_estimate:
            logger.info(
                f"[ComfyUI] Estimated time: ~{format_elapsed_time(total_estimate)} "
                f"({generation_count} frame(s))"
            )

        # Collect editable values using widget manager
        editable_values, selected_image_count = self.widget_manager.collect_editable_values()

        # Snapshot this configuration as a resumable session. Submitting is the
        # natural "I care about this setup" moment, and it's what makes the
        # resume banner appear next launch.
        self._save_resumable_session()

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

        # Non-modal submit summary: no confirmation dialog, but the user still
        # gets told how many generations were queued and roughly how long the
        # farm will be busy.
        summary = f"Submitting {generation_count} generation(s)"
        if total_estimate:
            summary += f" \u2014 est. ~{format_elapsed_time(total_estimate)}"

        # Inform user about server status when submitting
        if hasattr(self, '_server_is_online') and self._server_is_online is False:
            behavior = self.ui.ServerBehaviorCombo.currentData()
            behavior_msgs = {
                "wait": "Server offline \u2014 job will wait for server to come online",
                "fail_delete": "Server offline \u2014 job will fail and be deleted",
            }
            msg = behavior_msgs.get(behavior, "Server offline \u2014 job will fail immediately")
            self.update_status_with_spinner(
                f"ComfyUI: {summary} \u2014 {msg}", StatusColors.WARNING, start=False
            )
        else:
            self.update_status_with_spinner(f"ComfyUI: {summary}...", StatusColors.INFO, start=False)
        self.animate_button_click(self.ui.ComfyUISubmit)

        # Get seed value (QLineEdit \u2014 parsed safely, 64-bit capable)
        base_seed = read_seed(self.ui)

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

        self._end_submit()
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
                # Transient status scrolls away — keep the failure on screen.
                self._show_submit_failure(error_msg or "Unknown error")
        except Exception as e:
            import traceback
            logger.error(f"[ComfyUI] ERROR in on_result: {e}")
            logger.error(traceback.format_exc())

    def _on_submit_error(self, error_msg, traceback_str=""):
        """Handle ComfyUI job submission error."""

        self._end_submit()
        self.main_window.stop_status_spinner()
        self.show_status(f"Submission error: {error_msg}", "error")
        self.update_status_with_spinner(
            f"ComfyUI error: {error_msg}",
            StatusColors.ERROR, start=False
        )
        # Transient status scrolls away — keep the failure on screen.
        self._show_submit_failure(error_msg or "Unknown error")
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

        # Resolve by name first — that's just a stat per file and covers the
        # common case. Anything still missing needs a content-hash search, which
        # reads whole files off the share and must not run on the GUI thread.
        image_paths, missing_images = self._resolve_by_name(output_dir, source_images)
        model_paths, missing_models = self._resolve_by_name(output_dir, source_models)

        if missing_images or missing_models:
            logger.info(
                f"[ComfyUI] {len(missing_images) + len(missing_models)} source "
                f"file(s) not found by name — searching by content hash in background"
            )
            self.start_worker(
                self._resolve_sources_by_hash,
                worker_kwargs={
                    "directory": output_dir,
                    "missing_images": missing_images,
                    "missing_models": missing_models,
                    "hashes": source_image_hashes,
                },
                on_result=lambda found, imgs=image_paths, mdls=model_paths:
                    self._on_sources_resolved(found, imgs, mdls),
                on_error=lambda msg, tb="", imgs=image_paths, mdls=model_paths: (
                    logger.warning(f"[ComfyUI] Hash search failed: {msg}"),
                    self._populate_source_widgets(imgs, mdls),
                ),
            )
            return

        self._populate_source_widgets(image_paths, model_paths)

    @staticmethod
    def _resolve_by_name(output_dir, basenames):
        """Split source basenames into (found_paths, still_missing)."""
        found, missing = [], []
        for basename in basenames or []:
            if not basename:
                continue
            full_path = os.path.join(output_dir, basename)
            if os.path.exists(full_path):
                found.append(full_path)
            else:
                missing.append(basename)
        return found, missing

    @staticmethod
    def _resolve_sources_by_hash(directory, missing_images, missing_models, hashes):
        """Locate renamed source files by content hash (worker thread)."""
        result = {"images": [], "models": []}
        for key, names in (("images", missing_images), ("models", missing_models)):
            for basename in names:
                match = ComfyUITab._find_file_by_hash(directory, hashes.get(basename))
                if match:
                    result[key].append(match)
                    logger.info(
                        f"[ComfyUI] Found source {key[:-1]} by hash: "
                        f"{basename} -> {os.path.basename(match)}"
                    )
                else:
                    logger.warning(f"[ComfyUI] Source not found: {basename}")
        return result

    def _on_sources_resolved(self, found, image_paths, model_paths):
        """Merge hash-resolved paths and populate the widgets (GUI thread)."""
        self._populate_source_widgets(
            image_paths + (found or {}).get("images", []),
            model_paths + (found or {}).get("models", []),
        )

    def _populate_source_widgets(self, image_paths, model_paths):
        """Push resolved source files into the matching input widgets."""
        # Find and populate input widgets
        for widget_key, container in self.widget_manager.dynamic_widgets.items():
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
                    logger.info(f"[ComfyUI] Restored {len(image_paths)} source image(s) to node {node.node_id}")
                elif hasattr(input_widget, 'add_images'):
                    if hasattr(input_widget, 'clear_images'):
                        input_widget.clear_images()
                    input_widget.add_images(image_paths)
                    logger.info(f"[ComfyUI] Restored {len(image_paths)} source image(s) to node {node.node_id}")

            # Add models to 3D model input widgets
            elif node.widget_type == '3d_model' and model_paths:
                if hasattr(input_widget, 'setText'):
                    # For single model input (text field)
                    input_widget.setText(model_paths[0])
                    logger.info(f"[ComfyUI] Restored source model: {model_paths[0]}")

    @staticmethod
    def _find_file_by_hash(directory: str, expected_hash: str,
                           size_hint: int = None) -> str:
        """Scan directory for a file matching the expected content hash.

        Hashing reads whole files, and this runs against a gallery directory on
        a network share, so candidates are narrowed by size first where possible
        and the caller is expected to run this off the GUI thread.

        Args:
            directory: Directory to scan
            expected_hash: SHA-256 hash to match
            size_hint: Expected file size in bytes; when given, files of any
                other size are skipped without being read.

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
                    if size_hint is not None:
                        try:
                            if entry.stat().st_size != size_hint:
                                continue
                        except OSError:
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

        # React to Settings tab changes (network_output_path drives the path
        # display and the submit gating, both of which were previously only
        # refreshed once in initialize()).
        pipeline_events.settings_changed.connect(self._on_settings_changed)

        logger.debug("ComfyUI tab subscribed to event bus")

    def _on_settings_changed(self, changed_keys):
        """Refresh path-dependent UI when relevant global settings change."""
        keys = set(changed_keys or [])
        if keys and "network_output_path" not in keys:
            return

        logger.info("[ComfyUI] network_output_path changed — refreshing path display")
        self._update_network_path_display()
        self._validate_inputs()

    def _on_use_images_from_gallery(self, paths: list):
        """Handle request to use gallery images as inputs."""
        if not paths:
            return

        # Find an image input widget and add the images
        for widget_key, container in self.widget_manager.dynamic_widgets.items():
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
