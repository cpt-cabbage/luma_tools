"""
Base class for all tab modules in Luma Tools.

Provides a common interface for tab initialization, UI loading, and signal connections.
"""

import os
import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from PySide6 import QtCore, QtWidgets, QtUiTools

# Import StatusColors at module level - it's just an enum with no side effects
# This avoids repeated lazy imports in tab methods
from ui_components import StatusColors as _StatusColors

logger = logging.getLogger(__name__)


@dataclass
class TabConfig:
    """
    Configuration dataclass for tab metadata.

    Use this to define tab properties instead of individual property overrides:

        class MyTab(BaseTab):
            TAB_CONFIG = TabConfig(
                ui_file="my_tab.ui",
                tab_name="My Tab",
                tab_id="mytab"
            )

    Args:
        ui_file: UI filename relative to resources/ui/tabs/
        tab_name: Display name for this tab
        tab_id: Unique identifier for settings/state (defaults to tab_name.lower().replace(' ', '_'))
        icon: Optional icon name for tab (default: "")
    """
    ui_file: str
    tab_name: str
    tab_id: str = ""
    icon: str = ""

    def __post_init__(self):
        # Auto-generate tab_id from tab_name if not provided
        if not self.tab_id:
            self.tab_id = self.tab_name.lower().replace(' ', '_')


class TabSignals(QtCore.QObject):
    """Signals for cross-tab communication."""
    log_message = QtCore.Signal(str)
    status_update = QtCore.Signal(str)
    settings_changed = QtCore.Signal()
    request_attention = QtCore.Signal()  # Request pulsing glow on tab


class BaseTab(ABC):
    """
    Base class for all tab modules.

    Each tab module should either:
    1. Define TAB_CONFIG class attribute with a TabConfig instance (preferred), OR
    2. Override ui_file and tab_name properties (legacy)

    Plus:
    3. Connect its signals via connect_signals()
    4. Implement its event handlers

    Class attributes:
        StatusColors: Enum for status message colors (INFO, SUCCESS, WARNING, ERROR)
                     Use as self.StatusColors.INFO in subclasses
        TAB_CONFIG: Optional TabConfig instance for tab metadata

    Example with TAB_CONFIG (preferred):
        class MyTab(BaseTab):
            TAB_CONFIG = TabConfig(ui_file="my_tab.ui", tab_name="My Tab")

    Example with properties (legacy):
        class MyTab(BaseTab):
            @property
            def ui_file(self) -> str:
                return "my_tab.ui"
            @property
            def tab_name(self) -> str:
                return "My Tab"
    """

    # Make StatusColors available to all subclasses without repeated imports
    StatusColors = _StatusColors

    # Optional: Define TAB_CONFIG in subclass to avoid property boilerplate
    TAB_CONFIG: Optional[TabConfig] = None

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
        self._initialized = False  # Deferred initialization flag

        # Get project root for resolving UI file paths
        # base_tab.py is at python/ui/tabs/, so go up 3 levels to get project root
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))

    @property
    def ui_file(self) -> str:
        """Return the UI filename (relative to resources/ui/tabs/).

        Can be provided via TAB_CONFIG or by overriding this property.
        """
        if self.TAB_CONFIG:
            return self.TAB_CONFIG.ui_file
        raise NotImplementedError(
            f"{self.__class__.__name__} must either define TAB_CONFIG or override ui_file property"
        )

    @property
    def tab_name(self) -> str:
        """Return the display name for this tab.

        Can be provided via TAB_CONFIG or by overriding this property.
        """
        if self.TAB_CONFIG:
            return self.TAB_CONFIG.tab_name
        raise NotImplementedError(
            f"{self.__class__.__name__} must either define TAB_CONFIG or override tab_name property"
        )

    @property
    def tab_id(self) -> str:
        """Return a unique identifier for this tab (used for settings, etc.).

        Can be provided via TAB_CONFIG or by overriding this property.
        """
        if self.TAB_CONFIG:
            return self.TAB_CONFIG.tab_id
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
        Load the tab's UI, preferring precompiled Python over QUiLoader.

        Precompiled files are generated by pyside6-uic and live in
        resources/ui/tabs/_compiled/ui_<name>.py.  Using them avoids a ~5 s
        first-load penalty from Qt's UiTools module initialization.

        Args:
            parent: Optional parent widget

        Returns:
            The loaded UI widget
        """
        ui_path = self.get_ui_file_path()

        # Try precompiled .py first (avoids QUiLoader first-load penalty)
        compiled_dir = os.path.join(os.path.dirname(ui_path), "_compiled")
        base_name = os.path.splitext(os.path.basename(ui_path))[0]
        compiled_path = os.path.join(compiled_dir, f"ui_{base_name}.py")

        if os.path.exists(compiled_path):
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    f"ui_{base_name}", compiled_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find the Ui_ class in the compiled module
                ui_class = None
                for attr_name in dir(module):
                    if attr_name.startswith('Ui_'):
                        ui_class = getattr(module, attr_name)
                        break

                if ui_class:
                    widget = QtWidgets.QWidget(parent)
                    ui_obj = ui_class()
                    ui_obj.setupUi(widget)
                    # Copy widget references for backward compatibility
                    # (tabs access child widgets via self.ui.WidgetName)
                    for attr_name, value in vars(ui_obj).items():
                        if not attr_name.startswith('_'):
                            setattr(widget, attr_name, value)
                    self.ui = widget
                    return self.ui
            except Exception as e:
                logger.warning(f"Compiled UI load failed for {base_name}, falling back to QUiLoader: {e}")

        # Fallback to QUiLoader
        if not os.path.exists(ui_path):
            raise FileNotFoundError(f"UI file not found: {ui_path}")

        loader = QtUiTools.QUiLoader()
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

    def _ensure_initialized(self):
        """Run deferred initialization on first tab activation.

        Tab UI is loaded and signals connected during startup, but the heavier
        initialize() is deferred until the tab is first shown to speed up
        application startup. Shows a loading overlay while initializing.
        """
        if not self._initialized:
            import time
            overlay = self._show_deferred_loading_overlay()
            start = time.perf_counter()
            self._initialized = True
            self.initialize()
            elapsed = time.perf_counter() - start
            if overlay:
                overlay.deleteLater()
            logger.info(f"[Startup] {self.tab_name} deferred init: {elapsed*1000:.0f}ms")

    def _show_deferred_loading_overlay(self):
        """Show a loading overlay on the tab during deferred initialization."""
        if not self.ui:
            return None
        try:
            from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
            from PySide6.QtCore import Qt

            overlay = QWidget(self.ui)
            overlay.setObjectName("_deferred_loading_overlay")
            overlay.setStyleSheet(
                "background-color: rgba(24, 24, 24, 220); border-radius: 4px;"
            )
            overlay.setGeometry(self.ui.rect())

            layout = QVBoxLayout(overlay)
            layout.setAlignment(Qt.AlignCenter)

            label = QLabel(f"Loading {self.tab_name}...")
            label.setStyleSheet(
                "color: #cccccc; font-size: 14px; background: transparent;"
            )
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)

            overlay.raise_()
            overlay.show()
            QApplication.processEvents()
            return overlay
        except Exception:
            return None

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
        func: Callable[..., Any],
        *args: Any,
        on_result: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[tuple], None]] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
        worker_kwargs: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Start a worker thread with standard signal connections.

        This helper eliminates boilerplate for async operations. The worker is
        stored on self._worker to prevent garbage collection.

        Args:
            func: The function to run in the worker thread
            *args: Arguments to pass to the function
            on_result: Optional callback for successful completion (receives result)
            on_error: Optional callback for errors (receives (exc_type, exc_value, traceback) tuple)
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
        worker = start_worker_thread(
            func, *args,
            on_result=on_result,
            on_error=on_error,
            on_progress=on_progress,
            worker_kwargs=worker_kwargs
        )
        # Store on self to prevent GC. Use a list so concurrent workers
        # don't overwrite each other (previous code used self._worker which
        # could GC the first worker if a second was started before it finished).
        self._worker = worker  # Keep for backwards compatibility
        if not hasattr(self, '_active_workers'):
            self._active_workers = []
        self._active_workers.append(worker)
        # Clean up finished workers to prevent unbounded memory growth
        worker.signals.finished.connect(lambda w=worker: self._cleanup_finished_worker(w))

    def _cleanup_finished_worker(self, worker):
        """Remove a finished worker from the active list to prevent memory leaks."""
        try:
            if hasattr(self, '_active_workers'):
                self._active_workers = [w for w in self._active_workers if w is not worker]
        except (ValueError, RuntimeError):
            pass

    def has_active_workers(self) -> bool:
        """Return True if this tab has any active worker threads."""
        return bool(getattr(self, '_active_workers', None))

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

    @contextmanager
    def spinner_context(self, message: str, success_msg: str = None, error_msg: str = None):
        """
        Context manager for spinner lifecycle.

        Automatically starts spinner on enter and stops on exit. Shows appropriate
        status message based on success or exception.

        Args:
            message: Message to display while operation is running
            success_msg: Optional message to show on successful completion
            error_msg: Optional message prefix to show on error (default: "Error")

        Example:
            with self.spinner_context("Processing...", success_msg="Done!"):
                do_something()
                do_something_else()
                # Spinner stops automatically, shows "Done!" on success
                # Shows "Error: ..." if exception occurs

            # Without success message (just stops spinner):
            with self.spinner_context("Saving..."):
                save_data()
        """
        from ui_components import StatusColors

        self.update_status_with_spinner(message, StatusColors.INFO)
        try:
            yield
            # Success path
            if success_msg:
                self.update_status_with_spinner(success_msg, StatusColors.SUCCESS, start=False)
            else:
                self.main_window.stop_status_spinner()
        except Exception as e:
            # Error path
            prefix = error_msg or "Error"
            self.update_status_with_spinner(f"{prefix}: {e}", StatusColors.ERROR, start=False)
            raise

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
    def unpack_worker_error(error_msg, traceback_str="") -> tuple:
        """Unpack worker error signal args into (error_msg, traceback_str).

        Worker error signal is Signal(str, str) — emits (error_msg, traceback_str).
        Error handlers should use signature: def on_error(self, error_msg, traceback_str="")

        This method is kept for backward compatibility but simply passes through
        the arguments. New code should use the two-parameter signature directly.
        """
        return str(error_msg), traceback_str

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
