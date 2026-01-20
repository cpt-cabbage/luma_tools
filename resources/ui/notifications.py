"""
Notification and banner widgets.

Provides status banners for user feedback.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout


class ComfyUIStatusBanner(QWidget):
    """
    Enhanced status banner with clear indicators.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)

        self.label = QLabel("Ready to submit")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-weight: bold; color: white;")
        self.layout.addWidget(self.label)

        self.setFixedHeight(40)
        self.setStyleSheet("background-color: #2c3e50; border-radius: 4px;")

    def set_status(self, message, color="#34495e"):
        """Set the status message and background color."""
        self.label.setText(message)
        self.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
