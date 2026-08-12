"""
Logs tab module for Luma Tools.

Handles the terminal log output display and clear functionality.
"""
import logging

import os

from PySide6.QtGui import QColor, QTextCursor, QTextCharFormat, QClipboard
from PySide6.QtWidgets import QMenu, QApplication
from PySide6.QtCore import Qt, QTimer

from .base_tab import BaseTab, TabConfig
from core.settings_manager import safe_get_setting, safe_set_setting

logger = logging.getLogger(__name__)

# Prefixes that indicate debug messages
# These are filtered from the UI log view when "Show debug" is unchecked
# All messages still pass to the file logger regardless of this filter
DEBUG_LOG_PREFIXES = (
    "[Poll Debug]",
    "[Detection]",
    "[find_user_running_jobs]",
    "[Batch Poll]",
    "[Batch]",
    "[TabAttention]",
)

# Color mapping for log level prefixes (all levels included so every message
# goes through QTextCursor with an explicit foreground, bypassing QSS overrides)
_LOG_LEVEL_COLORS = {
    "[ERROR]": "#ef4444",
    "[WARNING]": "#f59e0b",
    "[DEBUG]": "#888888",
    "[INFO]": "#b0b5bd",
}
_DEFAULT_LOG_COLOR = "#b0b5bd"


class LogsTab(BaseTab):
    """Tab for displaying terminal log output."""

    TAB_CONFIG = TabConfig(ui_file="logs.ui", tab_name="Logs", tab_id="logs")

    def __init__(self, main_window=None, app_state=None):
        super().__init__(main_window, app_state)
        from collections import deque
        self._paused = False
        self._paused_messages = []
        self._show_debug = False
        self._all_messages = deque(maxlen=5000)
        self._filter_text = ""
        # Debounce timer for the filter field — re-rendering 5000 buffered
        # messages on every keystroke is visibly janky.
        self._filter_timer = None

    def connect_signals(self):
        """Connect log tab signals."""
        self.ui.ClearLogButton.clicked.connect(self._on_clear_log_clicked)
        self.ui.PauseLogButton.clicked.connect(self._on_pause_log_clicked)
        # Use stateChanged instead of toggled - stateChanged is more reliable
        # toggled only fires on checkState changes from user interaction,
        # stateChanged fires for any checkbox state change
        self.ui.VerboseLogsCheckbox.stateChanged.connect(self._on_verbose_checkbox_state_changed)

        if hasattr(self.ui, 'LogFilterEdit'):
            self.ui.LogFilterEdit.textChanged.connect(self._on_filter_text_changed)

    def initialize(self):
        """Initialize the logs tab with saved settings."""
        self._show_debug = safe_get_setting("show_verbose_logs", False)
        self.ui.VerboseLogsCheckbox.blockSignals(True)
        self.ui.VerboseLogsCheckbox.setChecked(self._show_debug)
        self.ui.VerboseLogsCheckbox.blockSignals(False)
        # Label/tooltip live in logs.ui ("Show debug logs") — no runtime rename,
        # which used to make the .ui text and the visible text disagree.

        # Debounce timer must be parented to a live QObject so it isn't GC'd
        self._filter_timer = QTimer(self.ui)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self._apply_filter)

        # Use custom context menu to avoid Qt parenting bug in tab widgets
        # "QWidgetWindow must be a top level window" error
        self.ui.LogOutput.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.LogOutput.customContextMenuRequested.connect(self._show_log_context_menu)

    def _on_filter_text_changed(self, text: str):
        """Queue a filtered re-render (debounced ~250ms)."""
        self._filter_text = text.strip().lower()
        if self._filter_timer is not None:
            self._filter_timer.start()
        else:
            # connect_signals() runs eagerly at startup; initialize() (which
            # creates the timer) is deferred until first activation.
            self._apply_filter()

    def _apply_filter(self):
        """Re-render the buffer with the current text filter applied."""
        self._rerender_log()

    def _passes_filter(self, message: str) -> bool:
        """Return True if the message should be visible in the log view."""
        if not self._show_debug and self._is_debug_message(message):
            return False
        if self._filter_text and self._filter_text not in message.lower():
            return False
        return True

    def _on_verbose_checkbox_state_changed(self, state: int):
        """Handle debug logs checkbox state change (view filter only).

        Args:
            state: Qt.CheckState value (0=Unchecked, 2=Checked)
        """
        checked = state == 2  # Qt.Checked
        self._show_debug = checked
        safe_set_setting("show_verbose_logs", checked)
        self._rerender_log()

    def _show_log_context_menu(self, position):
        """Show custom context menu for log output.

        Uses a custom menu instead of the default QTextEdit context menu
        to avoid Qt parenting bug ("QWidgetWindow must be a top level window")
        that occurs with context menus inside tab widgets.
        """
        # Capture selection BEFORE showing menu (right-click can clear selection)
        cursor = self.ui.LogOutput.textCursor()
        selected_text = cursor.selectedText()
        has_selection = bool(selected_text)

        # Parent menu to main window to avoid tab widget parenting issues
        menu = QMenu(self.main_window)

        # Copy action - use captured selection
        copy_action = menu.addAction("Copy")
        copy_action.setEnabled(has_selection)
        if has_selection:
            # Capture by value to preserve selection
            copy_action.triggered.connect(lambda checked=False, text=selected_text: self._copy_to_clipboard(text))

        # Select all action
        select_all_action = menu.addAction("Select All")
        select_all_action.triggered.connect(self.ui.LogOutput.selectAll)

        menu.addSeparator()

        # Clear action
        clear_action = menu.addAction("Clear Log")
        clear_action.triggered.connect(self._on_clear_log_clicked)

        menu.addSeparator()

        # Log file actions — the on-disk log holds everything, including the
        # debug lines this view filters out.
        log_path = self._get_current_log_path()

        open_action = menu.addAction("Open log file")
        open_action.setEnabled(bool(log_path))
        if log_path:
            open_action.setToolTip(log_path)
            open_action.triggered.connect(
                lambda checked=False, p=log_path: self._open_log_file(p)
            )

        copy_path_action = menu.addAction("Copy log path")
        copy_path_action.setEnabled(bool(log_path))
        if log_path:
            copy_path_action.setToolTip(log_path)
            copy_path_action.triggered.connect(
                lambda checked=False, p=log_path: self._copy_log_path(p)
            )

        # Use popup() instead of exec_() to avoid blocking issues
        menu.popup(self.ui.LogOutput.mapToGlobal(position))

    def _get_current_log_path(self):
        """Resolve the path of this session's log file.

        Prefers the LOG_FILE the entry module recorded at startup; falls back
        to the newest luma_tools_*.log under the network users log dir (or the
        local dir if the network share is unavailable).

        The entry module is read out of sys.modules rather than imported:
        core/luma_tools.py is the __main__ script, so `import core.luma_tools`
        would execute it a second time and set up a second log file.
        """
        import sys

        log_file = getattr(sys.modules.get("__main__"), "LOG_FILE", None)
        if not log_file:
            log_file = getattr(sys.modules.get("core.luma_tools"), "LOG_FILE", None)
        if log_file and os.path.isfile(log_file):
            return log_file

        from core.logging_utils import get_network_log_dir, get_local_log_dir
        for log_dir in (get_network_log_dir("users"), get_local_log_dir()):
            if not log_dir or not os.path.isdir(log_dir):
                continue
            try:
                candidates = [
                    os.path.join(log_dir, f)
                    for f in os.listdir(log_dir)
                    if f.startswith("luma_tools_") and f.endswith(".log")
                ]
            except OSError as e:
                logger.warning(f"Could not list log directory {log_dir}: {e}")
                continue
            if candidates:
                return max(candidates, key=os.path.getmtime)
        return None

    def _open_log_file(self, path: str):
        """Open the log file in the OS default handler."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            logger.warning(f"Could not open log file: {path}")
            self.show_status("Could not open log file", "warning")

    def _copy_log_path(self, path: str):
        """Copy the log file path to the clipboard."""
        QApplication.clipboard().setText(path)
        self.show_status("Log path copied to clipboard", "success")

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        # QTextEdit selection uses paragraph separator (U+2029), convert to newlines
        text = text.replace('\u2029', '\n')
        QApplication.clipboard().setText(text)

    def _on_clear_log_clicked(self):
        """Clear the log output."""
        self.ui.LogOutput.clear()
        self._all_messages.clear()
        self._paused_messages.clear()
        logger.info("Log cleared")

    def _on_pause_log_clicked(self, checked: bool):
        """Toggle pause state for log output."""
        self._paused = checked
        if checked:
            self.ui.PauseLogButton.setText("Resume")
        else:
            self.ui.PauseLogButton.setText("Pause")
            # Flush any messages that were queued while paused
            if self._paused_messages:
                for msg in self._paused_messages:
                    self._append_to_log(msg)
                self._paused_messages.clear()

    @staticmethod
    def _get_message_color(message: str) -> str:
        """Return a hex color for the message based on its log level prefix."""
        stripped = message.lstrip()
        for prefix, color in _LOG_LEVEL_COLORS.items():
            if stripped.startswith(prefix):
                return color
        return _DEFAULT_LOG_COLOR

    def _append_colored_text(self, message: str):
        """Append a message using QTextCursor with explicit color.

        Always uses QTextCursor + QTextCharFormat so the foreground color is
        embedded in the document and cannot be overridden by QSS.
        Uses a separate cursor for editing to preserve user's text selection.
        """
        text = message.rstrip()
        # Create a NEW cursor from the document to avoid clearing user's selection
        # (Using textCursor() and setTextCursor() would replace the user's selection)
        cursor = QTextCursor(self.ui.LogOutput.document())
        cursor.movePosition(QTextCursor.End)
        if not self.ui.LogOutput.document().isEmpty():
            cursor.insertBlock()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._get_message_color(message)))
        cursor.insertText(text, fmt)
        # Don't call setTextCursor() - that would clear any user selection

    def _append_to_log(self, message: str):
        """Internal method to append a message to the log widget."""
        self._append_colored_text(message)
        # Scroll vertically to bottom to show latest message
        v_scrollbar = self.ui.LogOutput.verticalScrollBar()
        v_scrollbar.setValue(v_scrollbar.maximum())
        # Keep horizontal scroll at left so long lines don't shift view
        h_scrollbar = self.ui.LogOutput.horizontalScrollBar()
        h_scrollbar.setValue(0)

    def _is_debug_message(self, message: str) -> bool:
        """Check if a message is a debug-level message (filtered from view by default).

        A message is considered debug if:
        1. It starts with [DEBUG] log level prefix, OR
        2. It starts with one of DEBUG_LOG_PREFIXES directly, OR
        3. It has a log level prefix followed by one of DEBUG_LOG_PREFIXES
        """
        stripped = message.lstrip()

        # Filter ALL messages at DEBUG log level
        if stripped.startswith("[DEBUG] "):
            return True

        # Check direct prefix match (e.g. "[Detection] ..." from tab.log() calls)
        if stripped.startswith(DEBUG_LOG_PREFIXES):
            return True

        # Check after logging level prefix (e.g. "[INFO] [Detection]...")
        for prefix in ("[INFO] ", "[WARNING] "):
            if stripped.startswith(prefix):
                remainder = stripped[len(prefix):]
                if remainder.startswith(DEBUG_LOG_PREFIXES):
                    return True

        return False

    def append_log(self, message: str):
        """
        Append a message to the log output.

        All messages are stored in the internal buffer so the log can be
        re-rendered when the debug filter is toggled. This is a view filter
        only - all messages are always written to the file logger regardless
        of the debug toggle.

        Args:
            message: The message to append
        """
        if self.ui is None:
            return
        try:
            # Always store in buffer for re-render on filter toggle
            self._all_messages.append(message)

            # Apply the view filters (debug toggle + text filter)
            if not self._passes_filter(message):
                return

            if self._paused:
                self._paused_messages.append(message)
            else:
                self._append_to_log(message)
        except RuntimeError as e:
            if "wrapped C/C++ object" not in str(e) and "deleted" not in str(e):
                raise
        except AttributeError:
            pass  # Widget may not be fully initialized

    def _rerender_log(self):
        """Re-render the entire log applying the current view filters.

        Called when the 'Show debug logs' checkbox is toggled or the text
        filter changes, so previously hidden messages appear (or visible
        messages disappear). With
        5000 buffered messages, calling _append_colored_text in a tight loop
        triggers a layout reflow per message and visibly freezes the UI;
        wrapping the loop in setUpdatesEnabled(False) batches the redraws
        into a single repaint at the end.
        """
        log = self.ui.LogOutput
        log.setUpdatesEnabled(False)
        try:
            log.clear()
            for msg in self._all_messages:
                if not self._passes_filter(msg):
                    continue
                self._append_colored_text(msg)
        finally:
            log.setUpdatesEnabled(True)
        # Scroll to bottom after re-render
        v_scrollbar = log.verticalScrollBar()
        v_scrollbar.setValue(v_scrollbar.maximum())
