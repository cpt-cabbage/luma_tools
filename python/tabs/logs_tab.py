"""
Logs tab module for Luma Tools.

Handles the terminal log output display and clear functionality.
"""

from .base_tab import BaseTab


class LogsTab(BaseTab):
    """Tab for displaying terminal log output."""

    @property
    def ui_file(self) -> str:
        return "logs.ui"

    @property
    def tab_name(self) -> str:
        return "Logs"

    def connect_signals(self):
        """Connect log tab signals."""
        self.ui.ClearLogButton.clicked.connect(self._on_clear_log_clicked)

    def _on_clear_log_clicked(self):
        """Clear the log output."""
        self.ui.LogOutput.clear()
        self.log("Log cleared")

    def append_log(self, message: str):
        """
        Append a message to the log output.

        Args:
            message: The message to append
        """
        self.ui.LogOutput.append(message.rstrip())
        # Auto-scroll to bottom
        scrollbar = self.ui.LogOutput.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
