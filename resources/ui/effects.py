"""
UI animation and visual effect utilities.

Provides animations, tab glow effects, and visual feedback.
"""
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect,
    QSequentialAnimationGroup, QObject, QRectF, Signal
)
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtGui import QColor, QPixmap, QPainter, QIcon, QBrush


class TabGlowEffect(QObject):
    """
    Creates a pulsing glow effect on a tab bar to draw user attention.

    Usage:
        glow = TabGlowEffect(tab_widget, tab_index, color="#ec4899")
        glow.start()
        # Later, when user clicks the tab:
        glow.stop()
    """

    def __init__(self, tab_widget, tab_index, color="#ec4899", parent=None):
        """
        Initialize the tab glow effect.

        Args:
            tab_widget: The QTabWidget containing the tabs
            tab_index: The index of the tab to glow
            color: Hex color for the glow (default: pink for gallery)
            parent: Parent QObject
        """
        super().__init__(parent)
        self.tab_widget = tab_widget
        self.tab_index = tab_index
        self.color = QColor(color)
        self.base_color = QColor(color)

        # Animation state
        self._intensity = 0.0
        self._direction = 1  # 1 = brightening, -1 = dimming
        self._is_running = False

        # Timer for animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._animation_interval = 50  # 20 FPS
        self._intensity_step = 0.08  # How much to change per frame

        # Store original icon for restoration
        self._original_icon = None

    def start(self, pulse_count=0):
        """
        Start the pulsing glow animation.

        Args:
            pulse_count: Number of pulses (0 = infinite until stopped)
        """
        if self._is_running:
            return

        self._is_running = True
        self._intensity = 0.0
        self._direction = 1
        self._pulse_count = pulse_count
        self._current_pulses = 0

        # Store original icon if not already stored
        if self._original_icon is None:
            self._original_icon = self.tab_widget.tabIcon(self.tab_index)

        self._timer.start(self._animation_interval)

    def stop(self):
        """Stop the glow animation and restore original appearance."""
        self._is_running = False
        self._timer.stop()
        self._update_tab_style(0.0)

    def _animate(self):
        """Update the glow intensity for animation."""
        if not self._is_running:
            return

        # Update intensity
        self._intensity += self._intensity_step * self._direction

        # Clamp and reverse direction at bounds
        if self._intensity >= 1.0:
            self._intensity = 1.0
            self._direction = -1
        elif self._intensity <= 0.0:
            self._intensity = 0.0
            self._direction = 1
            self._current_pulses += 1

            # Check if we've completed the requested pulses
            if self._pulse_count > 0 and self._current_pulses >= self._pulse_count:
                self.stop()
                return

        self._update_tab_style(self._intensity)

    def _update_tab_style(self, intensity):
        """
        Update the tab appearance to show the glow effect.

        Args:
            intensity: Glow intensity from 0.0 to 1.0
        """
        if intensity <= 0.01:
            # Reset to original icon
            if self._original_icon is not None:
                self.tab_widget.setTabIcon(self.tab_index, self._original_icon)
            return

        # Store original icon if not already stored
        if self._original_icon is None:
            self._original_icon = self.tab_widget.tabIcon(self.tab_index)

        # Create icon with pulsing notification dot
        glow_icon = self._create_notification_icon(intensity)
        if glow_icon:
            self.tab_widget.setTabIcon(self.tab_index, glow_icon)

    def _create_notification_icon(self, intensity):
        """
        Create an icon with a pulsing notification dot overlay.

        Args:
            intensity: Glow intensity from 0.0 to 1.0

        Returns:
            QIcon with notification dot, or None if no original icon
        """
        icon_size = 16

        result_pixmap = QPixmap(icon_size, icon_size)
        result_pixmap.fill(Qt.transparent)

        painter = QPainter(result_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Draw the original icon if available
        if self._original_icon is not None and not self._original_icon.isNull():
            original_pixmap = self._original_icon.pixmap(icon_size, icon_size)
            if not original_pixmap.isNull():
                painter.drawPixmap(0, 0, original_pixmap)

        # Draw pulsing notification dot in top-right corner
        dot_size = 6 + int(2 * intensity)
        dot_x = icon_size - dot_size
        dot_y = 0

        notification_color = QColor(255, 80, 80)  # Bright red
        alpha = int(200 + 55 * intensity)

        # Draw outer glow
        glow_color = QColor(255, 100, 100, int(100 * intensity))
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.NoPen)
        glow_rect = QRectF(dot_x - 2, dot_y - 1, dot_size + 3, dot_size + 3)
        painter.drawEllipse(glow_rect)

        # Draw main dot
        dot_color = QColor(notification_color)
        dot_color.setAlpha(alpha)
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.NoPen)
        dot_rect = QRectF(dot_x, dot_y, dot_size, dot_size)
        painter.drawEllipse(dot_rect)

        # Draw bright center highlight
        highlight_color = QColor(255, 255, 255, int(180 * intensity))
        painter.setBrush(QBrush(highlight_color))
        highlight_size = dot_size * 0.35
        highlight_rect = QRectF(
            dot_x + dot_size * 0.2,
            dot_y + dot_size * 0.15,
            highlight_size,
            highlight_size
        )
        painter.drawEllipse(highlight_rect)

        painter.end()

        return QIcon(result_pixmap)


class TabGlowManager(QObject):
    """
    Manages pulsing glow effects for multiple tabs.
    Handles starting/stopping glows and auto-stopping when tab is activated.
    """

    def __init__(self, tab_widget, parent=None):
        """
        Initialize the glow manager.

        Args:
            tab_widget: The QTabWidget to manage glows for
            parent: Parent QObject
        """
        super().__init__(parent)
        self.tab_widget = tab_widget
        self._active_glows = {}  # tab_index -> TabGlowEffect

        # Connect to tab change signal to auto-stop glow
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def start_glow(self, tab_index, color="#ec4899"):
        """
        Start a pulsing glow on the specified tab.

        Args:
            tab_index: Index of the tab to glow
            color: Hex color for the glow
        """
        # Don't glow if this tab is currently active
        if self.tab_widget.currentIndex() == tab_index:
            return

        # Stop existing glow on this tab if any
        if tab_index in self._active_glows:
            self._active_glows[tab_index].stop()

        # Create and start new glow
        glow = TabGlowEffect(self.tab_widget, tab_index, color, self)
        self._active_glows[tab_index] = glow
        glow.start()

    def stop_glow(self, tab_index):
        """
        Stop the glow on the specified tab.

        Args:
            tab_index: Index of the tab to stop glowing
        """
        if tab_index in self._active_glows:
            self._active_glows[tab_index].stop()
            del self._active_glows[tab_index]

            # Reset tab text color to default
            tab_bar = self.tab_widget.tabBar()
            tab_bar.setTabTextColor(tab_index, QColor())

    def stop_all_glows(self):
        """Stop all active glows."""
        for tab_index in list(self._active_glows.keys()):
            self.stop_glow(tab_index)

    def _on_tab_changed(self, index):
        """Auto-stop glow when user navigates to the glowing tab."""
        if index in self._active_glows:
            self.stop_glow(index)


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
        self._animations = []

        # Splash screen redirection
        self.redirect_to_splash = False
        self.splash_screen = None

        # Track buttons with "ready" styling applied
        self._ready_buttons = {}  # button -> original_style

    def setup_animations(self):
        """Setup all animations for the UI."""
        self._setup_button_hover_effects()
        self._setup_progress_animation()
        self._setup_status_animations()

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
        self.status_opacity = QGraphicsOpacityEffect(self.ui.StatusLabel)
        self.ui.StatusLabel.setGraphicsEffect(self.status_opacity)
        self.status_opacity.setOpacity(1.0)
        self._last_status_message = None
        self._last_status_color = None

    def animate_button_click(self, button):
        """Animate button click with scale effect."""
        if not button.isEnabled():
            return

        original_geometry = button.geometry()

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

        expand = QPropertyAnimation(button, b"geometry")
        expand.setDuration(80)
        expand.setStartValue(shrink.endValue())
        expand.setEndValue(original_geometry)
        expand.setEasingCurve(QEasingCurve.InOutQuad)

        sequence = QSequentialAnimationGroup()
        sequence.addAnimation(shrink)
        sequence.addAnimation(expand)
        sequence.start()

        self._animations.append(sequence)
        QTimer.singleShot(200, lambda: self._cleanup_animation(sequence))

    def animate_progress(self, start, end, duration=500):
        """Animate progress bar smoothly."""
        self.progress_animation.stop()
        self.progress_animation.setStartValue(start)
        self.progress_animation.setEndValue(end)
        self.progress_animation.setDuration(duration)
        self.progress_animation.start()

    def update_status_animated(self, message, color="#4a9eff"):
        """Update status label with fade animation (only if changed)."""
        if message == self._last_status_message and color == self._last_status_color:
            return

        self._last_status_message = message
        self._last_status_color = color

        self.ui.StatusLabel.setText(message)
        self.ui.StatusLabel.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 10pt;")

        fade_anim = QPropertyAnimation(self.status_opacity, b"opacity")
        fade_anim.setDuration(300)
        fade_anim.setStartValue(0.3)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        fade_anim.start()

        self._animations.append(fade_anim)
        QTimer.singleShot(350, lambda: self._cleanup_animation(fade_anim))

    def pulse_button(self, button):
        """
        Highlight a button as 'ready' with blue styling.
        The styling persists until the button is clicked.
        """
        # Skip if already styled as ready
        if button in self._ready_buttons:
            return

        # Store original style
        original_style = button.styleSheet()
        self._ready_buttons[button] = original_style

        # Apply ready styling
        button.setStyleSheet(
            original_style +
            "background-color: #5cadff; border: 2px solid #4a9eff;"
        )

        # Connect to clicked signal to reset styling
        def on_clicked():
            self._reset_button_style(button)

        button._ready_connection = button.clicked.connect(on_clicked)

    def _reset_button_style(self, button):
        """Reset a button's style back to its original state."""
        if button not in self._ready_buttons:
            return

        # Restore original style
        original_style = self._ready_buttons.pop(button)
        button.setStyleSheet(original_style)

        # Disconnect the click handler
        if hasattr(button, '_ready_connection'):
            try:
                button.clicked.disconnect(button._ready_connection)
            except (RuntimeError, TypeError):
                pass  # Connection already disconnected
            delattr(button, '_ready_connection')

    def clear_button_ready(self, button):
        """
        Manually clear the 'ready' styling from a button.
        Use this when conditions change and the button should no longer be highlighted.
        """
        self._reset_button_style(button)

    def fade_in_widget(self, widget, duration=300):
        """Fade in a widget."""
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
        """Fade out a widget."""
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
        """Clean up animation reference."""
        if animation in self._animations:
            self._animations.remove(animation)

    # Logging methods (toast notifications removed)
    def show_success(self, message):
        """Log a success message."""
        print(f"SUCCESS: {message}")

    def show_error(self, message):
        """Log an error message."""
        print(f"ERROR: {message}")

    def show_warning(self, message):
        """Log a warning message."""
        print(f"WARNING: {message}")

    def show_info(self, message):
        """Log an info message."""
        print(f"INFO: {message}")
