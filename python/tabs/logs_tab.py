"""
Logs tab module for Luma Tools.

Handles the terminal log output display and clear functionality.
"""

from .base_tab import BaseTab


class LogsTab(BaseTab):
    """Tab for displaying terminal log output."""

    def __init__(self, main_window=None, app_state=None):
        self._paused = False
        self._paused_messages = []
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

    def _on_clear_log_clicked(self):
        """Clear the log output."""
        self.ui.LogOutput.clear()
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

    def _append_to_log(self, message: str):
        """Internal method to append a message to the log widget."""
        self.ui.LogOutput.append(message.rstrip())
        scrollbar = self.ui.LogOutput.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def append_log(self, message: str):
        """
        Append a message to the log output.

        Args:
            message: The message to append
        """
        if self.ui is None:
            return
        try:
            if self._paused:
                self._paused_messages.append(message)
            else:
                self._append_to_log(message)
        except (RuntimeError, AttributeError):
            # Widget may not be fully initialized or may have been deleted
            pass
