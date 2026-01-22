"""
Base class for all tab modules in Luma Tools.

Provides a common interface for tab initialization, UI loading, and signal connections.
"""

import os
from abc import ABC, abstractmethod
from PySide6 import QtCore, QtWidgets, QtUiTools


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
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(os.path.dirname(script_dir))

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
        """Emit a log message signal."""
        self.signals.log_message.emit(message)

    def set_status(self, message: str):
        """Emit a status update signal."""
        self.signals.status_update.emit(message)

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

    def start_worker(self, func, *args, on_result=None, on_error=None, on_progress=None):
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

        Example:
            self.start_worker(
                my_long_operation, arg1, arg2,
                on_result=self._on_operation_complete,
                on_error=self._on_operation_error
            )
        """
        from PySide6.QtCore import QThreadPool
        from ui_components import Worker

        self._worker = Worker(func, *args)

        if on_result:
            self._worker.signals.result.connect(on_result)
        if on_error:
            self._worker.signals.error.connect(on_error)
        if on_progress:
            self._worker.signals.progress.connect(on_progress)

        QThreadPool.globalInstance().start(self._worker)

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

        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.update_status_animated(message, color)
