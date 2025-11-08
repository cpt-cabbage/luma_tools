"""
UI Animation Enhancement Module for Luma Shot Tools
Provides smooth animations and visual feedback without changing core functionality.

Compatible with PySide2 and the existing application architecture.
"""

from PySide2.QtCore import (
    QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup,
    QParallelAnimationGroup, QTimer, Qt, QRect
)
from PySide2.QtWidgets import QGraphicsOpacityEffect

# Import loading overlay if available
try:
    from loading_overlay import LoadingManager
    LOADING_AVAILABLE = True
except ImportError:
    LOADING_AVAILABLE = False
    print("loading_overlay module not found - loading screens disabled")


class UIAnimations:
    """
    Animation manager for the shot tools UI.
    Adds professional animations without modifying existing functionality.
    """

    def __init__(self, parent_widget):
        """
        Initialize the animation manager.

        Args:
            parent_widget: The main application widget
        """
        self.parent = parent_widget
        self.ui = parent_widget.ui
        self._animations = []  # Keep references to prevent garbage collection
        self.loading = None  # Loading manager

    def setup_animations(self):
        """Setup all animations for the UI."""
        # Setup button animations
        self._setup_button_hover_effects()

        # Setup progress bar animation
        self._setup_progress_animation()

        # Add smooth transitions for status updates
        self._setup_status_animations()

        # Setup loading overlay
        if LOADING_AVAILABLE:
            self.loading = LoadingManager(self.parent)
            print("Loading overlay enabled")

    def _setup_button_hover_effects(self):
        """Add subtle hover effects to buttons."""
        buttons = [
            self.ui.BuildPasses,
            self.ui.ScanRenders,
            self.ui.CleanFiles,
            self.ui.RescanCleanFiles,
            self.ui.MP4ScanRenders,
            self.ui.MP4BrowseOutput,
            self.ui.MP4BrowseCustomPath,
            self.ui.MP4Generate
        ]

        for button in buttons:
            if hasattr(button, 'installEventFilter'):
                button.installEventFilter(self.parent)

    def _setup_progress_animation(self):
        """Setup smooth progress bar animation."""
        self.progress_animation = QPropertyAnimation(self.ui.progressBar, b"value")
        self.progress_animation.setDuration(500)
        self.progress_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._animations.append(self.progress_animation)

    def _setup_status_animations(self):
        """Setup animations for status label updates."""
        # Create opacity effect for status label
        self.status_opacity = QGraphicsOpacityEffect(self.ui.StatusLabel)
        self.ui.StatusLabel.setGraphicsEffect(self.status_opacity)
        self.status_opacity.setOpacity(1.0)

    def animate_button_click(self, button):
        """
        Animate button click with scale effect.

        Args:
            button: The button widget to animate
        """
        if not button.isEnabled():
            return

        original_geometry = button.geometry()

        # Shrink animation
        shrink = QPropertyAnimation(button, b"geometry")
        shrink.setDuration(80)
        shrink.setStartValue(original_geometry)
        shrink.setEndValue(QRect(
            original_geometry.x() + 2,
            original_geometry.y() + 2,
            original_geometry.width() - 4,
            original_geometry.height() - 4
        ))
        shrink.setEasingCurve(QEasingCurve.InOutQuad)

        # Expand back animation
        expand = QPropertyAnimation(button, b"geometry")
        expand.setDuration(80)
        expand.setStartValue(shrink.endValue())
        expand.setEndValue(original_geometry)
        expand.setEasingCurve(QEasingCurve.InOutQuad)

        # Create sequence
        sequence = QSequentialAnimationGroup()
        sequence.addAnimation(shrink)
        sequence.addAnimation(expand)
        sequence.start()

        # Store reference
        self._animations.append(sequence)
        # Clean up after animation
        QTimer.singleShot(200, lambda: self._cleanup_animation(sequence))

    def animate_progress(self, start, end, duration=500):
        """
        Animate progress bar smoothly.

        Args:
            start: Starting value (0-100)
            end: Ending value (0-100)
            duration: Animation duration in milliseconds
        """
        self.progress_animation.stop()
        self.progress_animation.setStartValue(start)
        self.progress_animation.setEndValue(end)
        self.progress_animation.setDuration(duration)
        self.progress_animation.start()

    def update_status_animated(self, message, color="#4a9eff"):
        """
        Update status label with fade animation.

        Args:
            message: Status message to display
            color: Color for the status text (hex string)
        """
        # Set the message
        self.ui.StatusLabel.setText(message)

        # Apply color
        self.ui.StatusLabel.setStyleSheet(f"color: {color}; font-weight: 500;")

        # Fade animation
        fade_anim = QPropertyAnimation(self.status_opacity, b"opacity")
        fade_anim.setDuration(300)
        fade_anim.setStartValue(0.3)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        fade_anim.start()

        # Store reference
        self._animations.append(fade_anim)
        QTimer.singleShot(350, lambda: self._cleanup_animation(fade_anim))

    def pulse_button(self, button):
        """
        Create a pulsing effect to draw attention to a button.

        Args:
            button: The button widget to pulse
        """
        original_style = button.styleSheet()

        def pulse_on():
            button.setStyleSheet(
                original_style +
                "background-color: #1a5fb4; border: 2px solid #4a9eff;"
            )
            QTimer.singleShot(300, pulse_off)

        def pulse_off():
            button.setStyleSheet(original_style)

        pulse_on()

    def fade_in_widget(self, widget, duration=300):
        """
        Fade in a widget.

        Args:
            widget: The widget to fade in
            duration: Animation duration in milliseconds
        """
        opacity_effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(opacity_effect)

        fade_anim = QPropertyAnimation(opacity_effect, b"opacity")
        fade_anim.setDuration(duration)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        fade_anim.start()

        self._animations.append(fade_anim)
        QTimer.singleShot(duration + 50, lambda: self._cleanup_animation(fade_anim))

    def fade_out_widget(self, widget, duration=300):
        """
        Fade out a widget.

        Args:
            widget: The widget to fade out
            duration: Animation duration in milliseconds
        """
        opacity_effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(opacity_effect)

        fade_anim = QPropertyAnimation(opacity_effect, b"opacity")
        fade_anim.setDuration(duration)
        fade_anim.setStartValue(1.0)
        fade_anim.setEndValue(0.0)
        fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        fade_anim.start()

        self._animations.append(fade_anim)
        QTimer.singleShot(duration + 50, lambda: self._cleanup_animation(fade_anim))

    def _cleanup_animation(self, animation):
        """
        Clean up animation reference.

        Args:
            animation: The animation to clean up
        """
        if animation in self._animations:
            self._animations.remove(animation)

    # Loading overlay methods
    def show_loading(self, message="Loading...", submessage="", show_progress=False):
        """
        Show loading overlay with message.

        Args:
            message: Main loading message
            submessage: Optional secondary message
            show_progress: Whether to show progress bar
        """
        if self.loading:
            self.loading.show(message, submessage, show_progress)

    def hide_loading(self):
        """Hide loading overlay."""
        if self.loading:
            self.loading.hide()

    def update_loading_message(self, message, submessage=""):
        """
        Update loading message.

        Args:
            message: New main message
            submessage: New secondary message
        """
        if self.loading:
            self.loading.update_message(message, submessage)

    def update_loading_progress(self, value):
        """
        Update loading progress.

        Args:
            value: Progress value (0-100)
        """
        if self.loading:
            self.loading.update_progress(value)


class StatusColors:
    """Predefined colors for status messages."""
    SUCCESS = "#4ecca3"
    ERROR = "#ee6055"
    WARNING = "#ffa726"
    INFO = "#4a9eff"
    SCANNING = "#a78bfa"


def enhance_ui(parent_widget):
    """
    Convenience function to enhance UI with animations.

    Args:
        parent_widget: The main application widget

    Returns:
        UIAnimations: The animation manager instance
    """
    animator = UIAnimations(parent_widget)
    animator.setup_animations()
    return animator