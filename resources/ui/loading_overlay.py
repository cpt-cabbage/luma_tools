"""
Modern Loading Overlay for Luma Shot Tools
Provides a beautiful, animated loading screen during long operations.
"""

from PySide2.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QSize,
    QRectF, Signal, QObject
)
from PySide2.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QProgressBar, QGraphicsOpacityEffect
)
from PySide2.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QPixmap
import math
import os
from loading_styles import LoadingStyles


class SpinnerWidget(QWidget):
    """
    Modern circular spinner widget with smooth animation.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.setMinimumSize(*LoadingStyles.SPINNER_SIZE)

        # Make background transparent
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Spinner colors
        self.primary_color = LoadingStyles.PRIMARY_COLOR
        self.secondary_color = LoadingStyles.SECONDARY_BG_COLOR

        # Animation properties
        self.line_count = LoadingStyles.SPINNER_LINE_COUNT
        self.line_length = LoadingStyles.SPINNER_LINE_LENGTH
        self.line_width = LoadingStyles.SPINNER_LINE_WIDTH
        self.inner_radius = LoadingStyles.SPINNER_INNER_RADIUS

        # Event processing timer to keep UI responsive during blocking operations
        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self._process_events)

    def _process_events(self):
        """Process Qt events to keep the UI responsive."""
        from PySide2.QtWidgets import QApplication
        QApplication.processEvents()

    def start(self):
        """Start the spinner animation."""
        self.timer.start(LoadingStyles.SPINNER_ROTATION_INTERVAL)
        # Start event processing timer at higher frequency (every 16ms ~= 60 FPS)
        self.event_timer.start(16)

    def stop(self):
        """Stop the spinner animation."""
        self.timer.stop()
        self.event_timer.stop()

    def rotate(self):
        """Rotate the spinner."""
        self.angle = (self.angle + LoadingStyles.SPINNER_ROTATION_ANGLE) % 360
        self.update()

    def paintEvent(self, event):
        """Paint the spinner."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Clear background to transparent
        painter.fillRect(self.rect(), Qt.transparent)

        # Center the spinner
        width = self.width()
        height = self.height()
        painter.translate(width / 2, height / 2)
        painter.rotate(self.angle)

        # Draw spinning lines
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


class PulsingDotsWidget(QWidget):
    """
    Alternative loading animation with pulsing dots.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dot_count = 3
        self.current_dot = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.pulse)
        self.setMinimumSize(80, 30)

        self.dot_color = LoadingStyles.PRIMARY_COLOR
        self.dot_radius = 8
        self.dot_spacing = 20

        # Event processing timer to keep UI responsive during blocking operations
        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self._process_events)

    def _process_events(self):
        """Process Qt events to keep the UI responsive."""
        from PySide2.QtWidgets import QApplication
        QApplication.processEvents()

    def start(self):
        """Start the pulsing animation."""
        self.timer.start(400)  # Pulse every 400ms
        # Start event processing timer at higher frequency (every 16ms ~= 60 FPS)
        self.event_timer.start(16)

    def stop(self):
        """Stop the pulsing animation."""
        self.timer.stop()
        self.event_timer.stop()

    def pulse(self):
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


class LoadingOverlay(QWidget):
    """
    Modern loading overlay with animated spinner and status text.
    Covers the entire parent widget with a semi-transparent background.
    """

    def __init__(self, parent=None, style='spinner'):
        super().__init__(parent)

        # Setup overlay appearance
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(LoadingStyles.get_overlay_background_stylesheet())

        # Create layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(LoadingStyles.OVERLAY_SPACING)

        # Create logo
        logo_path = LoadingStyles.get_logo_path()
        self.logo_label = QLabel(self)
        self.logo_label.setStyleSheet("background: transparent;")
        # Set minimum size to ensure logo is not cut off
        self.logo_label.setMinimumSize(*LoadingStyles.LOGO_SIZE_OVERLAY)
        self.logo_label.setMaximumSize(*LoadingStyles.LOGO_SIZE_OVERLAY)
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Scale to a reasonable size while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                *LoadingStyles.LOGO_SIZE_OVERLAY,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.logo_label.setPixmap(scaled_pixmap)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setScaledContents(False)  # Don't scale contents, use actual pixmap size

        # Create loading animation
        if style == 'spinner':
            self.animation_widget = SpinnerWidget(self)
        else:
            self.animation_widget = PulsingDotsWidget(self)

        # Create status label
        self.status_label = QLabel("Loading...", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(LoadingStyles.get_status_label_stylesheet())

        # Create sub-status label
        self.substatus_label = QLabel("", self)
        self.substatus_label.setAlignment(Qt.AlignCenter)
        self.substatus_label.setStyleSheet(LoadingStyles.get_substatus_label_stylesheet())

        # Create progress bar (optional, hidden by default)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(LoadingStyles.PROGRESS_BAR_OVERLAY_WIDTH)
        self.progress_bar.setFixedHeight(LoadingStyles.PROGRESS_BAR_OVERLAY_HEIGHT)
        self.progress_bar.setStyleSheet(LoadingStyles.get_overlay_progress_stylesheet())
        self.progress_bar.hide()

        # Add widgets to layout
        layout.addStretch()
        layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.animation_widget, alignment=Qt.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addWidget(self.substatus_label)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)
        layout.addStretch()

        # Setup fade animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        # Hide initially
        self.hide()

    def show_loading(self, message="Loading...", submessage="", show_progress=False):
        """
        Show the loading overlay with a message.

        Args:
            message: Main loading message
            submessage: Optional secondary message
            show_progress: Whether to show the progress bar
        """
        # Update text
        self.status_label.setText(message)
        self.substatus_label.setText(submessage)

        # Show/hide progress bar
        if show_progress:
            self.progress_bar.show()
            self.progress_bar.setValue(0)
        else:
            self.progress_bar.hide()

        # Resize to cover parent
        if self.parent():
            self.resize(self.parent().size())

        # Show and start animation
        self.show()
        self.raise_()  # Bring to front
        self.animation_widget.start()

        # Fade in
        self.fade_in()

    def hide_loading(self):
        """Hide the loading overlay with fade out animation."""
        # Stop animation
        self.animation_widget.stop()

        # Fade out
        self.fade_out()

        # Hide after fade
        QTimer.singleShot(LoadingStyles.FADE_DURATION, self.hide)

    def update_message(self, message, submessage=""):
        """
        Update the loading message.

        Args:
            message: New main message
            submessage: New secondary message
        """
        self.status_label.setText(message)
        self.substatus_label.setText(submessage)

    def update_progress(self, value):
        """
        Update the progress bar value.

        Args:
            value: Progress value (0-100)
        """
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
        self.progress_bar.setValue(value)

    def fade_in(self, duration=None):
        """Fade in the overlay."""
        if duration is None:
            duration = LoadingStyles.FADE_DURATION
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(duration)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.fade_animation.start()

    def fade_out(self, duration=None):
        """Fade out the overlay."""
        if duration is None:
            duration = LoadingStyles.FADE_DURATION
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(duration)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.fade_animation.start()

    def resizeEvent(self, event):
        """Handle parent resize to keep overlay covering entire area."""
        if self.parent():
            self.resize(self.parent().size())
        super().resizeEvent(event)


class LoadingManager(QObject):
    """
    Manager class to handle loading overlays for the application.
    """

    def __init__(self, parent_widget):
        super().__init__()
        self.parent_widget = parent_widget
        self.overlay = None
        self._create_overlay()

    def _create_overlay(self):
        """Create the loading overlay."""
        self.overlay = LoadingOverlay(self.parent_widget, style='spinner')

    def show(self, message="Loading...", submessage="", show_progress=False):
        """
        Show loading overlay.

        Args:
            message: Main loading message
            submessage: Optional secondary message
            show_progress: Whether to show progress bar
        """
        self.overlay.show_loading(message, submessage, show_progress)

    def hide(self):
        """Hide loading overlay."""
        self.overlay.hide_loading()

    def update_message(self, message, submessage=""):
        """
        Update loading message.

        Args:
            message: New main message
            submessage: New secondary message
        """
        self.overlay.update_message(message, submessage)

    def update_progress(self, value):
        """
        Update progress value.

        Args:
            value: Progress value (0-100)
        """
        self.overlay.update_progress(value)


class InlineSpinner(QWidget):
    """
    Compact inline spinner for showing loading state next to widgets.
    Perfect for showing "loading passes..." next to a list.
    """

    def __init__(self, parent=None, size=24):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.spinner_size = size
        self.setFixedSize(size, size)

        # Spinner colors
        self.primary_color = LoadingStyles.PRIMARY_COLOR

        # Animation properties
        self.line_count = 8
        self.line_length = int(size * 0.3)
        self.line_width = max(2, int(size * 0.08))
        self.inner_radius = int(size * 0.15)

        # Event processing timer to keep UI responsive during blocking operations
        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self._process_events)

        # Start hidden
        self.hide()

    def _process_events(self):
        """Process Qt events to keep the UI responsive."""
        from PySide2.QtWidgets import QApplication
        QApplication.processEvents()

    def start(self):
        """Start the spinner animation and show."""
        self.show()
        self.timer.start(80)  # Faster rotation for smaller spinner
        # Start event processing timer at higher frequency (every 16ms ~= 60 FPS)
        self.event_timer.start(16)

    def stop(self):
        """Stop the spinner animation and hide."""
        self.timer.stop()
        self.event_timer.stop()
        self.hide()

    def rotate(self):
        """Rotate the spinner."""
        self.angle = (self.angle + 45) % 360
        self.update()

    def paintEvent(self, event):
        """Paint the spinner."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Center the spinner
        width = self.width()
        height = self.height()
        painter.translate(width / 2, height / 2)
        painter.rotate(self.angle)

        # Draw spinning lines
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