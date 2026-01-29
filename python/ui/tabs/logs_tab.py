"""
Logs tab module for Luma Tools.

Handles the terminal log output display and clear functionality.
"""

from PySide6.QtGui import QColor, QTextCursor, QTextCharFormat

from .base_tab import BaseTab
from core.settings_manager import get_setting, set_setting

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

    def __init__(self, main_window=None, app_state=None):
        self._paused = False
        self._paused_messages = []
        self._show_debug = False
        self._all_messages = []
        super().__init__(main_window, app_state)

    @property
    def ui_file(self) -> str:
        return "logs.ui"

    @property
    def tab_name(self) -> str:
        return "Logs"

    @property
    def tab_id(self) -> str:
        return "logs"

    def connect_signals(self):
        """Connect log tab signals."""
        self.ui.ClearLogButton.clicked.connect(self._on_clear_log_clicked)
        self.ui.PauseLogButton.clicked.connect(self._on_pause_log_clicked)
        self.ui.VerboseLogsCheckbox.toggled.connect(self._on_verbose_logs_toggled)

    def initialize(self):
        """Initialize the logs tab with saved settings."""
        self._show_debug = get_setting("show_verbose_logs")
        self.ui.VerboseLogsCheckbox.setChecked(self._show_debug)
        self.ui.VerboseLogsCheckbox.setText("Show debug")

    def _on_verbose_logs_toggled(self, checked: bool):
        """Handle debug logs checkbox toggle (view filter only)."""
        self._show_debug = checked
        set_setting("show_verbose_logs", checked, verbose=False)
        self._rerender_log()

    def _on_clear_log_clicked(self):
        """Clear the log output."""
        self.ui.LogOutput.clear()
        self._all_messages.clear()
        self._paused_messages.clear()
        self.log("Log cleared")

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
        """
        text = message.rstrip()
        cursor = self.ui.LogOutput.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.ui.LogOutput.document().isEmpty():
            cursor.insertBlock()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._get_message_color(message)))
        cursor.insertText(text, fmt)
        self.ui.LogOutput.setTextCursor(cursor)

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

        Handles both direct messages like '[Detection] ...' and logging-formatted
        messages like '[INFO] [Detection] ...' where a log level prefix is prepended.
        """
        stripped = message.lstrip()
        # Check direct prefix match
        if stripped.startswith(DEBUG_LOG_PREFIXES):
            return True
        # Check after logging level prefix (e.g. "[INFO] [Detection]...")
        for prefix in ("[INFO] ", "[DEBUG] ", "[WARNING] "):
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

            # Filter debug messages from view if toggle is off
            if not self._show_debug and self._is_debug_message(message):
                return

            if self._paused:
                self._paused_messages.append(message)
            else:
                self._append_to_log(message)
        except (RuntimeError, AttributeError):
            # Widget may not be fully initialized or may have been deleted
            pass

    def _rerender_log(self):
        """Re-render the entire log applying the current debug filter.

        Called when the 'Show debug' checkbox is toggled so that previously
        hidden messages appear (or visible debug messages disappear).
        """
        self.ui.LogOutput.clear()
        for msg in self._all_messages:
            if not self._show_debug and self._is_debug_message(msg):
                continue
            self._append_colored_text(msg)
        # Scroll to bottom after re-render
        v_scrollbar = self.ui.LogOutput.verticalScrollBar()
        v_scrollbar.setValue(v_scrollbar.maximum())
