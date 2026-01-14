"""
Notification and banner widgets.

Provides toast notifications and status banners for user feedback.
"""
from PySide2.QtCore import Qt, QTimer, QPropertyAnimation
from PySide2.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect


class ToastNotification(QWidget):
    """
    Floating toast notification that appears at the top of the window.
    """

    def __init__(self, message, type="info", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.layout = QVBoxLayout(self)
        self.label = QLabel(message)
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)

        # Color based on type
        color_map = {
            "success": "#2ecc71",
            "error": "#e74c3c",
            "warning": "#f39c12",
            "info": "#3498db"
        }
        self.color = color_map.get(type, "#3498db")

        self.setObjectName("ToastNotification")
        self.setProperty("type", type)

        # Animations
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")

        # Auto-hide timer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_toast)

    def show_toast(self, duration=3000):
        """Show the toast notification."""
        if not self.parent():
            return

        # Position at top center
        parent_rect = self.parent().geometry()
        self.adjustSize()
        x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
        y = parent_rect.y() + 40
        self.move(x, y)

        self.show()
        self.opacity_anim.setDuration(300)
        self.opacity_anim.setStartValue(0)
        self.opacity_anim.setEndValue(1)
        self.opacity_anim.start()

        self.timer.start(duration)

    def hide_toast(self):
        """Hide the toast notification with fade out."""
        self.opacity_anim.setDuration(500)
        self.opacity_anim.setStartValue(1)
        self.opacity_anim.setEndValue(0)
        self.opacity_anim.finished.connect(self.deleteLater)
        self.opacity_anim.start()


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
