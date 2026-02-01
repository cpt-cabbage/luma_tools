"""
Spinner and loading animation widgets.

Provides various loading indicators for background operations.
"""
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtGui import QPainter, QColor, QPen

from styles import LoadingStyles


class BaseSpinner(QWidget):
    """
    Base class for circular spinner widgets.

    Provides common painting logic for spinners with trailing opacity effect.
    Subclasses can customize size, speed, and line properties.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)

        # Spinner colors (can be overridden)
        self.primary_color = LoadingStyles.PRIMARY_COLOR

        # Animation properties (set by subclass)
        self.line_count = 12
        self.line_length = 10
        self.line_width = 2
        self.inner_radius = 6
        self.rotation_interval = 50  # milliseconds
        self.rotation_step = 30  # degrees per step

    def start(self):
        """Start the spinner animation."""
        self.timer.start(self.rotation_interval)

    def stop(self):
        """Stop the spinner animation."""
        self.timer.stop()

    def _rotate(self):
        """Rotate the spinner by one step."""
        self.angle = (self.angle + self.rotation_step) % 360
        self.update()

    def paintEvent(self, event):
        """Paint the spinner with trailing opacity effect."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Clear background to transparent
        painter.fillRect(self.rect(), Qt.transparent)

        # Center the spinner
        width = self.width()
        height = self.height()
        painter.translate(width / 2, height / 2)
        painter.rotate(self.angle)

        # Draw spinning lines with trail effect
        for i in range(self.line_count):
            # Calculate opacity for trail effect
            opacity = 1.0 - (i / self.line_count)

            # Set pen with opacity
            color = QColor(self.primary_color)
            color.setAlphaF(opacity)
            pen = QPen(color)
            pen.setWidth(self.line_width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)

            # Draw line
            painter.drawLine(
                self.inner_radius, 0,
                self.inner_radius + self.line_length, 0
            )

            # Rotate for next line
            painter.rotate(360.0 / self.line_count)


class SpinnerWidget(BaseSpinner):
    """
    Modern circular spinner widget with smooth animation.

    Standard size spinner for general loading indicators.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(*LoadingStyles.SPINNER_SIZE)

        # Make background transparent
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Use LoadingStyles defaults
        self.secondary_color = LoadingStyles.SECONDARY_BG_COLOR
        self.line_count = LoadingStyles.SPINNER_LINE_COUNT
        self.line_length = LoadingStyles.SPINNER_LINE_LENGTH
        self.line_width = LoadingStyles.SPINNER_LINE_WIDTH
        self.inner_radius = LoadingStyles.SPINNER_INNER_RADIUS
        self.rotation_interval = LoadingStyles.SPINNER_ROTATION_INTERVAL
        self.rotation_step = LoadingStyles.SPINNER_ROTATION_ANGLE


class InlineSpinner(BaseSpinner):
    """
    Compact inline spinner for showing loading state next to widgets.

    Perfect for showing "loading passes..." next to a list.
    Smaller and faster than SpinnerWidget.
    """

    def __init__(self, parent=None, size=24):
        super().__init__(parent)
        self.spinner_size = size
        self.setFixedSize(size, size)

        # Scaled animation properties
        self.line_count = 8
        self.line_length = int(size * 0.3)
        self.line_width = max(2, int(size * 0.08))
        self.inner_radius = int(size * 0.15)
        self.rotation_interval = 80  # Faster rotation for smaller spinner
        self.rotation_step = 45

        # Start hidden
        self.hide()

    def start(self):
        """Start the spinner animation and show."""
        self.show()
        super().start()

    def stop(self):
        """Stop the spinner animation and hide."""
        super().stop()
        self.hide()


class PulsingDotsWidget(QWidget):
    """
    Alternative loading animation with pulsing dots.

    Shows three dots that pulse sequentially.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dot_count = 3
        self.current_dot = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._pulse)
        self.setMinimumSize(80, 30)

        self.dot_color = LoadingStyles.PRIMARY_COLOR
        self.dot_radius = 8
        self.dot_spacing = 20

    def start(self):
        """Start the pulsing animation."""
        self.timer.start(400)  # Pulse every 400ms

    def stop(self):
        """Stop the pulsing animation."""
        self.timer.stop()

    def _pulse(self):
        """Move to next dot."""
        self.current_dot = (self.current_dot + 1) % self.dot_count
        self.update()

    def paintEvent(self, event):
        """Paint the pulsing dots."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # Calculate starting position to center dots
        total_width = (self.dot_count - 1) * self.dot_spacing
        start_x = (width - total_width) / 2
        center_y = height / 2

        # Draw dots
        for i in range(self.dot_count):
            x = start_x + (i * self.dot_spacing)

            # Scale the active dot
            if i == self.current_dot:
                radius = self.dot_radius * 1.5
                color = self.dot_color
            else:
                radius = self.dot_radius
                color = QColor(self.dot_color)
                color.setAlphaF(0.5)

            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                QRectF(x - radius, center_y - radius, radius * 2, radius * 2)
            )


class LoadingOverlay(QFrame):
    """
    Semi-transparent overlay with centered spinner and message.

    Use to indicate loading state over a content area.
    Shows a spinner with optional status message.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Use QFrame styling for reliable background
        self.setObjectName("LoadingOverlay")
        self.setFrameStyle(QFrame.NoFrame)
        self.setStyleSheet("""
            QFrame#LoadingOverlay {
                background-color: rgba(30, 30, 30, 220);
            }
        """)

        # Layout for spinner and message
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        # Spinner
        self._spinner = SpinnerWidget(self)
        self._spinner.setFixedSize(48, 48)
        # Configure larger spinner
        self._spinner.line_count = 12
        self._spinner.line_length = 14
        self._spinner.line_width = 3
        self._spinner.inner_radius = 8
        layout.addWidget(self._spinner, alignment=Qt.AlignCenter)

        # Message label
        self._message = QLabel("Loading...")
        self._message.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 500;
                background: transparent;
            }
        """)
        self._message.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._message, alignment=Qt.AlignCenter)

        # Start hidden
        self.hide()

    def show_loading(self, message="Loading..."):
        """Show the overlay with a message."""
        self._message.setText(message)
        self._spinner.start()
        self.show()
        self.raise_()
        self.update()  # Force repaint

    def hide_loading(self):
        """Hide the overlay."""
        self._spinner.stop()
        self.hide()

    def update_message(self, message):
        """Update the loading message."""
        self._message.setText(message)
