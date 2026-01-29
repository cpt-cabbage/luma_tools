"""
Base class for all tab modules in Luma Tools.

Provides a common interface for tab initialization, UI loading, and signal connections.
"""

import os
import logging
from abc import ABC, abstractmethod
from PySide6 import QtCore, QtWidgets, QtUiTools

logger = logging.getLogger(__name__)


class TabSignals(QtCore.QObject):
    """Signals for cross-tab communication."""
    log_message = QtCore.Signal(str)
    status_update = QtCore.Signal(str)
    settings_changed = QtCore.Signal()
    request_attention = QtCore.Signal()  # Request pulsing glow on tab


class BaseTab(ABC):
    """
    Base class for all tab modules.

    Each tab module should:
    1. Define its UI file path
    2. Define its tab name
    3. Connect its signals
    4. Implement its event handlers
    """

    def __init__(self, main_window, app_state):
        """
        Initialize the tab.

        Args:
            main_window: Reference to the main LumaShotTools window
            app_state: The global application state
        """
        self.main_window = main_window
        self.app_state = app_state
        self.ui = None
        self.signals = TabSignals()

        # Get project root for resolving UI file paths
        # base_tab.py is at python/ui/tabs/, so go up 3 levels to get project root
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))

    @property
    @abstractmethod
    def ui_file(self) -> str:
        """Return the UI filename (relative to resources/ui/tabs/)."""
        pass

    @property
    @abstractmethod
    def tab_name(self) -> str:
        """Return the display name for this tab."""
        pass

    @property
    def tab_id(self) -> str:
        """Return a unique identifier for this tab (used for settings, etc.)."""
        return self.tab_name.lower().replace(' ', '_')

    @property
    def animator(self):
        """Get the main window's UI animator, or None if unavailable.

        Use this instead of ``hasattr(self.main_window, 'animator')`` checks.
        """
        return getattr(self.main_window, 'animator', None)

    def get_ui_file_path(self) -> str:
        """Return the full path to the tab's UI file."""
        return os.path.join(self.project_root, "resources", "ui", "tabs", self.ui_file)

    def load_ui(self, parent=None) -> QtWidgets.QWidget:
        """
        Load the tab's UI from its .ui file.

        Args:
            parent: Optional parent widget

        Returns:
            The loaded UI widget
        """
        loader = QtUiTools.QUiLoader()
        ui_path = self.get_ui_file_path()

        if not os.path.exists(ui_path):
            raise FileNotFoundError(f"UI file not found: {ui_path}")

        self.ui = loader.load(ui_path, parent)
        return self.ui

    @abstractmethod
    def connect_signals(self):
        """
        Connect tab-specific signals to handlers.

        This method is called after the UI is loaded.
        Subclasses must implement this to wire up their signal/slot connections.
        """
        pass

    def initialize(self):
        """
        Perform any initialization after UI is loaded and signals are connected.

        Override this method for tab-specific setup that needs to happen
        after the UI is fully ready.
        """
        pass

    def on_tab_activated(self):
        """
        Called when this tab becomes visible/active.

        Override this method to perform actions when the user switches to this tab.
        """
        pass

    def on_tab_deactivated(self):
        """
        Called when the user switches away from this tab.

        Override this method to perform cleanup or save state.
        """
        pass

    def log(self, message: str):
        """Emit a log message signal and write to file logger."""
        logger.info(message)
        self.signals.log_message.emit(message)

    def set_status(self, message: str):
        """Emit a status update signal."""
        self.signals.status_update.emit(message)

    def show_status(self, message: str, level: str = "info"):
        """
        Show a status message via the animator.

        This helper eliminates the repeated `hasattr(self.main_window, 'animator')`
        checks throughout tab code.

        Args:
            message: Message to display
            level: One of "info", "success", "warning", "error"

        Example:
            self.show_status("File saved successfully", "success")
            self.show_status("Invalid input", "warning")
        """
        if self.animator:
            if level == "info":
                self.animator.show_info(message)
            elif level == "success":
                self.animator.show_success(message)
            elif level == "warning":
                self.animator.show_warning(message)
            elif level == "error":
                self.animator.show_error(message)

    def get_widget(self, name: str):
        """
        Get a widget from the UI by name.

        Args:
            name: The widget's object name

        Returns:
            The widget, or None if not found
        """
        if self.ui is None:
            return None
        return getattr(self.ui, name, None)

    def start_worker(
        self,
        func,
        *args,
        on_result=None,
        on_error=None,
        on_progress=None,
        worker_kwargs=None
    ):
        """
        Start a worker thread with standard signal connections.

        This helper eliminates boilerplate for async operations. The worker is
        stored on self._worker to prevent garbage collection.

        Args:
            func: The function to run in the worker thread
            *args: Arguments to pass to the function
            on_result: Optional callback for successful completion (receives result)
            on_error: Optional callback for errors (receives (msg, traceback) tuple)
            on_progress: Optional callback for progress updates (receives int, str)
            worker_kwargs: Optional dict of keyword arguments to pass to the function

        Example:
            self.start_worker(
                my_long_operation, arg1, arg2,
                on_result=self._on_operation_complete,
                on_error=self._on_operation_error
            )

            # With keyword arguments:
            self.start_worker(
                submit_job,
                worker_kwargs={"name": "MyJob", "priority": 50},
                on_result=self._on_submit_complete
            )
        """
        from workers import start_worker_thread
        self._worker = start_worker_thread(
            func, *args,
            on_result=on_result,
            on_error=on_error,
            on_progress=on_progress,
            worker_kwargs=worker_kwargs
        )

    def update_status_with_spinner(self, message: str, color, start: bool = True):
        """
        Update status bar with animated message and control spinner.

        This helper consolidates the common pattern of starting/stopping the status spinner
        and updating the animated status message. It eliminates duplication across tabs.

        Args:
            message: Status message to display
            color: StatusColors enum value (INFO, SUCCESS, WARNING, ERROR)
            start: If True, starts the spinner; if False, stops it (default: True)

        Example:
            # Start operation
            self.update_status_with_spinner("Processing data...", StatusColors.INFO)

            # Complete operation
            self.update_status_with_spinner("Processing complete!", StatusColors.SUCCESS, start=False)
        """
        if start:
            self.main_window.start_status_spinner()
        else:
            self.main_window.stop_status_spinner()

        if self.animator:
            self.animator.update_status_animated(message, color)

    def on_worker_success(self, message: str, status_message: str = None, log_message: str = None):
        """
        Standard handler for worker success.

        Stops spinner, shows success status, and optionally shows animator popup.

        Args:
            message: Short message for animator popup
            status_message: Optional status bar message (defaults to message)
            log_message: Optional log message (defaults to message)

        Example:
            self.start_worker(
                my_operation,
                on_result=lambda result: self.on_worker_success("Operation complete!")
            )
        """
        from ui_components import StatusColors

        self.update_status_with_spinner(
            status_message or message,
            StatusColors.SUCCESS,
            start=False
        )
        if self.animator:
            self.animator.show_success(message)
        if log_message:
            self.log(log_message)

    def on_worker_error(
        self,
        error_msg: str,
        traceback_str: str = None,
        status_prefix: str = "",
        show_dialog: bool = False
    ):
        """
        Standard handler for worker errors.

        Stops spinner, shows error status, logs the error, and optionally shows dialog.

        Args:
            error_msg: Error message
            traceback_str: Optional traceback for logging
            status_prefix: Prefix for status message (e.g., "MP4 Maker")
            show_dialog: Whether to show an error dialog

        Example:
            self.start_worker(
                my_operation,
                on_error=lambda msg, tb: self.on_worker_error(msg, tb, "Build")
            )
        """
        from ui_components import StatusColors

        full_msg = f"{status_prefix}: {error_msg}" if status_prefix else error_msg

        self.update_status_with_spinner(
            full_msg,
            StatusColors.ERROR,
            start=False
        )
        self.log(f"Error: {error_msg}")
        if traceback_str:
            self.log(traceback_str)

        if show_dialog:
            from dialog_helpers import show_error
            show_error("Error", error_msg, parent=self.main_window)

    @staticmethod
    def unpack_worker_error(error_tuple) -> tuple:
        """Unpack a worker error tuple into (error_msg, traceback_str).

        Worker error signals emit a tuple of (exc_type, exc_value, traceback_str).
        This helper safely extracts the message and traceback.
        """
        if isinstance(error_tuple, tuple) and len(error_tuple) >= 2:
            error_msg = str(error_tuple[1])
            traceback_str = error_tuple[2] if len(error_tuple) > 2 else ""
        else:
            error_msg = str(error_tuple)
            traceback_str = ""
        return error_msg, traceback_str

    def pulse_button(self, widget):
        """
        Safely pulse a button using the animator.

        This helper eliminates the repeated `hasattr(self.main_window, 'animator')`
        checks throughout tab code.

        Args:
            widget: The button widget to pulse
        """
        if self.animator:
            self.animator.pulse_button(widget)

    def animate_button_click(self, widget):
        """Safely animate a button click using the animator."""
        if self.animator:
            self.animator.animate_button_click(widget)

    def enable_button(self, widget, enabled: bool = True):
        """
        Enable or disable a button widget.

        Simple helper for consistent button state management.

        Args:
            widget: The button widget
            enabled: Whether to enable (True) or disable (False)
        """
        if widget:
            widget.setEnabled(enabled)
