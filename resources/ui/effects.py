"""
UI animation and visual effect utilities.

Provides animations, tab glow effects, and visual feedback.
"""
import logging

from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect,
    QSequentialAnimationGroup, QObject, QRectF, Signal, QEvent
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget
from PySide6.QtGui import QColor, QPixmap, QPainter, QIcon, QBrush, QPen

from core.design_tokens import Color

logger = logging.getLogger(__name__)


# ============================================================================
# ANIMATION HELPERS
# ============================================================================

def create_property_animation(
    target,
    property_name: bytes,
    start_value,
    end_value,
    duration: int = 300,
    easing: QEasingCurve.Type = QEasingCurve.OutCubic
) -> QPropertyAnimation:
    """
    Create a property animation with common settings.

    Reduces boilerplate for creating QPropertyAnimation instances.

    Args:
        target: The QObject to animate
        property_name: Property name as bytes (e.g., b"pos", b"opacity")
        start_value: Starting value for the animation
        end_value: Ending value for the animation
        duration: Animation duration in milliseconds (default: 300)
        easing: Easing curve type (default: OutCubic)

    Returns:
        QPropertyAnimation: Configured animation (call .start() to begin)

    Example:
        anim = create_property_animation(widget, b"pos", QPoint(0, 0), QPoint(100, 100))
        anim.start()
    """
    anim = QPropertyAnimation(target, property_name)
    anim.setDuration(duration)
    anim.setStartValue(start_value)
    anim.setEndValue(end_value)
    anim.setEasingCurve(easing)
    return anim


def create_fade_animation(
    widget: QWidget,
    fade_in: bool = True,
    duration: int = 200,
    easing: QEasingCurve.Type = QEasingCurve.OutCubic
) -> QPropertyAnimation:
    """
    Create a fade in/out animation for a widget.

    Creates or reuses a QGraphicsOpacityEffect on the widget.

    Args:
        widget: The widget to fade
        fade_in: True to fade in (0->1), False to fade out (1->0)
        duration: Animation duration in milliseconds
        easing: Easing curve type

    Returns:
        QPropertyAnimation: Configured fade animation
    """
    # Get or create opacity effect
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

    start_val = 0.0 if fade_in else 1.0
    end_val = 1.0 if fade_in else 0.0

    return create_property_animation(effect, b"opacity", start_val, end_val, duration, easing)


# ============================================================================
# TAB GLOW EFFECT
# ============================================================================

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

            # Check if we've completed the requested pulses. Stop animating
            # (no more 20 FPS icon repaints) but keep a static notification
            # dot so the attention indicator remains until the tab is visited.
            if self._pulse_count > 0 and self._current_pulses >= self._pulse_count:
                self._is_running = False
                self._timer.stop()
                self._update_tab_style(0.6)
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

        notification_color = QColor(59, 130, 246)  # Bright blue
        alpha = int(200 + 55 * intensity)

        # Draw outer glow
        glow_color = QColor(80, 140, 255, int(100 * intensity))
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

        # Reuse the existing effect for this tab — replacing it leaked the
        # old QObject (parented to this manager) with its timer
        glow = self._active_glows.get(tab_index)
        if glow is not None:
            glow.stop()
        else:
            glow = TabGlowEffect(self.tab_widget, tab_index, color, self)
            self._active_glows[tab_index] = glow

        # Finite pulse count: after ~30 pulses the animation stops and a
        # static dot remains, instead of repainting the icon 20x/s forever
        glow.start(pulse_count=30)

    def stop_glow(self, tab_index):
        """
        Stop the glow on the specified tab.

        Args:
            tab_index: Index of the tab to stop glowing
        """
        if tab_index in self._active_glows:
            glow = self._active_glows.pop(tab_index)
            glow.stop()
            glow.deleteLater()  # actually free the effect (it is our child)

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


class ButtonNotificationBadge(QWidget):
    """
    A notification badge that can be overlaid on a button.
    Shows a small pulsing blue dot in the top-right corner, similar to tab notification badges.

    Usage:
        badge = ButtonNotificationBadge(button)
        badge.show_badge()
        # Later:
        badge.hide_badge()
    """

    def __init__(self, parent_button, size=10, color=QColor(59, 130, 246), offset=(4, 4)):
        """
        Initialize the notification badge.

        Args:
            parent_button: The QPushButton to attach the badge to
            size: Diameter of the badge in pixels (default: 10)
            color: QColor for the badge (default: bright blue)
            offset: Tuple (x, y) offset from top-right corner (default: (4, 4))
        """
        super().__init__(parent_button)
        self._parent_button = parent_button
        self._size = size
        self._color = color
        self._offset = offset
        self._visible = False

        # Animation state
        self._intensity = 0.0
        self._direction = 1  # 1 = brightening, -1 = dimming
        self._is_animating = False

        # Timer for pulsing animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._animation_interval = 50  # 20 FPS
        self._intensity_step = 0.08  # How much to change per frame

        # Set fixed size for the badge (extra space for animated glow)
        self.setFixedSize(size + 6, size + 6)  # Extra space for glow

        # Make transparent background
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Initially hidden
        self.hide()

        # Connect to parent resize to reposition badge
        parent_button.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Reposition badge when parent button resizes."""
        if obj == self._parent_button and event.type() in (
            QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show
        ):
            self._update_position()
        return super().eventFilter(obj, event)

    def _update_position(self):
        """Position the badge in the top-right corner of the parent button."""
        if not self._parent_button:
            return
        parent_width = self._parent_button.width()
        x = parent_width - self._size - self._offset[0]
        y = self._offset[1]
        self.move(x, y)

    def _animate(self):
        """Update the pulse intensity for animation."""
        if not self._is_animating:
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

        self.update()

    def paintEvent(self, event):
        """Paint the notification badge with pulsing animation."""
        if not self._visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate animated values based on intensity
        size_boost = int(2 * self._intensity)  # Size varies by 0-2 pixels
        base_alpha = 200 + int(55 * self._intensity)  # Alpha varies 200-255
        glow_alpha = 60 + int(60 * self._intensity)  # Glow alpha varies 60-120

        # Draw outer glow (pulsing)
        glow_color = QColor(self._color)
        glow_color.setAlpha(glow_alpha)
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.NoPen)
        glow_size = self._size + 4 + size_boost
        painter.drawEllipse(0, 0, glow_size, glow_size)

        # Draw main badge (pulsing)
        badge_color = QColor(self._color)
        badge_color.setAlpha(base_alpha)
        painter.setBrush(QBrush(badge_color))
        painter.setPen(Qt.NoPen)
        badge_offset = 2
        badge_size = self._size + size_boost
        painter.drawEllipse(badge_offset, badge_offset, badge_size, badge_size)

        # Draw highlight (pulsing)
        highlight_alpha = 120 + int(60 * self._intensity)
        highlight_color = QColor(255, 255, 255, highlight_alpha)
        painter.setBrush(QBrush(highlight_color))
        highlight_size = badge_size * 0.35
        painter.drawEllipse(
            int(badge_offset + badge_size * 0.2),
            int(badge_offset + badge_size * 0.15),
            int(highlight_size),
            int(highlight_size)
        )

        painter.end()

    def show_badge(self):
        """Show the notification badge with pulsing animation."""
        self._visible = True
        self._is_animating = True
        self._intensity = 0.0
        self._direction = 1
        self._update_position()
        self.show()
        self.raise_()
        self._timer.start(self._animation_interval)
        self.update()

    def hide_badge(self):
        """Hide the notification badge and stop animation."""
        self._visible = False
        self._is_animating = False
        self._timer.stop()
        self.hide()

    def is_badge_visible(self):
        """Check if badge is currently visible."""
        return self._visible


class ThumbnailNotificationDot(QWidget):
    """
    A pulsing notification dot for thumbnail widgets to indicate new items.
    Uses the same visual style as TabGlowEffect and ButtonNotificationBadge.

    Usage:
        dot = ThumbnailNotificationDot(thumbnail_label)
        dot.move(x, y)  # Position in top-right
        dot.show_dot()
        # Later:
        dot.hide_dot()
    """

    def __init__(self, parent, size=10, color=QColor(59, 130, 246)):
        """
        Initialize the notification dot.

        Args:
            parent: The parent widget (typically thumbnail_label)
            size: Diameter of the dot in pixels (default: 10)
            color: QColor for the dot (default: bright blue)
        """
        super().__init__(parent)
        self._size = size
        self._color = color
        self._visible = False

        # Animation state
        self._intensity = 0.0
        self._direction = 1  # 1 = brightening, -1 = dimming
        self._is_animating = False

        # Timer for pulsing animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._animation_interval = 50  # 20 FPS
        self._intensity_step = 0.08  # How much to change per frame

        # Set fixed size for the dot (extra space for animated glow)
        self.setFixedSize(size + 6, size + 6)

        # Make transparent background
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Initially hidden
        self.hide()

    def _animate(self):
        """Update the pulse intensity for animation."""
        if not self._is_animating:
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

        self.update()

    def paintEvent(self, event):
        """Paint the notification glow with pulsing animation."""
        if not self._visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate animated values based on intensity
        size_boost = int(3 * self._intensity)  # Size varies more for glow effect
        center_x = (self._size + 6) / 2
        center_y = (self._size + 6) / 2

        # Draw multiple layered glows for a soft, diffuse effect
        # Outer glow (very soft, large)
        outer_alpha = int(20 + 30 * self._intensity)  # 20-50 alpha
        outer_color = QColor(self._color)
        outer_color.setAlpha(outer_alpha)
        painter.setBrush(QBrush(outer_color))
        painter.setPen(Qt.NoPen)
        outer_size = self._size + 6 + size_boost
        painter.drawEllipse(
            int(center_x - outer_size / 2),
            int(center_y - outer_size / 2),
            int(outer_size),
            int(outer_size)
        )

        # Middle glow
        mid_alpha = int(40 + 50 * self._intensity)  # 40-90 alpha
        mid_color = QColor(self._color)
        mid_color.setAlpha(mid_alpha)
        painter.setBrush(QBrush(mid_color))
        mid_size = self._size + 2 + size_boost * 0.6
        painter.drawEllipse(
            int(center_x - mid_size / 2),
            int(center_y - mid_size / 2),
            int(mid_size),
            int(mid_size)
        )

        # Inner core (brighter but still semi-transparent)
        core_alpha = int(80 + 80 * self._intensity)  # 80-160 alpha
        core_color = QColor(self._color)
        core_color.setAlpha(core_alpha)
        painter.setBrush(QBrush(core_color))
        core_size = self._size * 0.6 + size_boost * 0.3
        painter.drawEllipse(
            int(center_x - core_size / 2),
            int(center_y - core_size / 2),
            int(core_size),
            int(core_size)
        )

        painter.end()

    def show_dot(self):
        """Show the notification dot with pulsing animation."""
        self._visible = True
        self._is_animating = True
        self._intensity = 0.0
        self._direction = 1
        self.show()
        self.raise_()
        self._timer.start(self._animation_interval)
        self.update()

    def hide_dot(self):
        """Hide the notification dot and stop animation."""
        self._visible = False
        self._is_animating = False
        self._timer.stop()
        self.hide()

    def is_visible(self):
        """Check if dot is currently visible."""
        return self._visible


class StatusMessageQueue(QObject):
    """
    Smart status message queue that handles rapid messages intelligently.

    Features:
    - Priority levels (URGENT > HIGH > NORMAL > LOW)
    - Activity tracking with elapsed time display
    - Smart message coalescing for similar rapid messages
    - Minimum display time so users can read messages
    - Progress message handling (X of Y)
    """

    # Priority levels
    URGENT = 4   # Errors - always show immediately
    HIGH = 3     # Warnings, completions
    NORMAL = 2   # Info messages
    LOW = 1      # Progress updates, can be coalesced

    # Signals
    message_ready = Signal(str, str)  # message, color

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = []  # List of (priority, message, color, timestamp)
        self._current_message = None
        self._current_priority = 0
        self._current_start_time = 0
        self._min_display_ms = 800  # Minimum time to show a message
        self._process_timer = QTimer(self)
        self._process_timer.timeout.connect(self._process_queue)
        self._process_timer.setInterval(100)  # Check every 100ms

        # Activity tracking
        self._current_activity = None  # (activity_id, message_template, start_time)
        self._activity_timer = QTimer(self)
        self._activity_timer.timeout.connect(self._update_activity_display)
        self._activity_timer.setInterval(1000)  # Update every second

        # Message coalescing
        self._pending_similar = {}  # category -> (count, last_message, color)
        self._coalesce_timer = QTimer(self)
        self._coalesce_timer.timeout.connect(self._flush_coalesced)
        self._coalesce_timer.setSingleShot(True)

        import time
        self._time = time

    def start(self):
        """Start the queue processor."""
        self._process_timer.start()

    def stop(self):
        """Stop the queue processor."""
        self._process_timer.stop()
        self._activity_timer.stop()
        self._coalesce_timer.stop()

    def post(self, message: str, color: str, priority: int = None, category: str = None):
        """
        Post a message to the queue.

        Args:
            message: The status message
            color: Hex color for the message
            priority: Message priority (URGENT, HIGH, NORMAL, LOW)
            category: Optional category for coalescing similar messages
        """
        if priority is None:
            priority = self.NORMAL

        current_time = self._time.time() * 1000  # ms

        # Handle coalescing for LOW priority messages with categories
        if priority == self.LOW and category:
            if category in self._pending_similar:
                count, _, _ = self._pending_similar[category]
                self._pending_similar[category] = (count + 1, message, color)
            else:
                self._pending_similar[category] = (1, message, color)
            # Start coalesce timer if not running
            if not self._coalesce_timer.isActive():
                self._coalesce_timer.start(200)  # Coalesce within 200ms
            return

        # For higher priority messages, check if we should interrupt
        if priority >= self.HIGH or priority > self._current_priority:
            # Clear lower priority messages from queue
            self._queue = [(p, m, c, t) for p, m, c, t in self._queue if p >= priority]

        self._queue.append((priority, message, color, current_time))
        self._queue.sort(key=lambda x: (-x[0], x[3]))  # Sort by priority desc, then time

        # If urgent or nothing showing, process immediately
        if priority >= self.URGENT or self._current_message is None:
            self._process_queue()

    def _flush_coalesced(self):
        """Flush any coalesced messages."""
        for category, (count, message, color) in self._pending_similar.items():
            if count > 1:
                # Modify message to show count
                coalesced_msg = f"{message} (+{count-1} more)"
            else:
                coalesced_msg = message
            self._queue.append((self.LOW, coalesced_msg, color, self._time.time() * 1000))

        self._pending_similar.clear()
        self._queue.sort(key=lambda x: (-x[0], x[3]))
        self._process_queue()

    def _process_queue(self):
        """Process the message queue."""
        current_time = self._time.time() * 1000

        # Check if current message has been displayed long enough
        if self._current_message:
            elapsed = current_time - self._current_start_time
            # Allow higher priority to interrupt, but respect min display for same/lower
            if self._queue:
                next_priority = self._queue[0][0]
                if next_priority <= self._current_priority and elapsed < self._min_display_ms:
                    return  # Keep current message

        # Get next message
        if self._queue:
            priority, message, color, _ = self._queue.pop(0)
            self._current_message = message
            self._current_priority = priority
            self._current_start_time = current_time
            self.message_ready.emit(message, color)

    def start_activity(self, activity_id: str, message_template: str, color: str):
        """
        Start tracking an ongoing activity with elapsed time.

        Args:
            activity_id: Unique ID for this activity
            message_template: Message with {elapsed} placeholder, e.g. "Processing... ({elapsed})"
            color: Status color
        """
        self._current_activity = (activity_id, message_template, color, self._time.time())
        self._update_activity_display()
        self._activity_timer.start()

    def update_activity(self, activity_id: str, message_template: str = None, extra: str = None):
        """Update an ongoing activity's message."""
        if self._current_activity and self._current_activity[0] == activity_id:
            _, old_template, color, start_time = self._current_activity
            template = message_template or old_template
            self._current_activity = (activity_id, template, color, start_time)
            if extra:
                self._current_activity = (activity_id, template, color, start_time, extra)
            self._update_activity_display()

    def end_activity(self, activity_id: str):
        """End an ongoing activity."""
        if self._current_activity and self._current_activity[0] == activity_id:
            self._current_activity = None
            self._activity_timer.stop()

    def _update_activity_display(self):
        """Update the display for the current activity."""
        if not self._current_activity:
            return

        activity_data = self._current_activity
        activity_id, template, color = activity_data[0], activity_data[1], activity_data[2]
        start_time = activity_data[3]
        extra = activity_data[4] if len(activity_data) > 4 else ""

        elapsed_secs = int(self._time.time() - start_time)
        if elapsed_secs < 60:
            elapsed_str = f"{elapsed_secs}s"
        elif elapsed_secs < 3600:
            mins, secs = divmod(elapsed_secs, 60)
            elapsed_str = f"{mins}m {secs}s"
        else:
            hours, remainder = divmod(elapsed_secs, 3600)
            mins = remainder // 60
            elapsed_str = f"{hours}h {mins}m"

        message = template.format(elapsed=elapsed_str)
        if extra:
            message = f"{message} - {extra}"

        self.message_ready.emit(message, color)

    def post_progress(self, current: int, total: int, message: str, color: str):
        """
        Post a progress message that updates in place.

        Args:
            current: Current item number
            total: Total items
            message: Base message (will append progress)
            color: Status color
        """
        pct = int((current / max(total, 1)) * 100)
        full_message = f"{message} ({current}/{total} - {pct}%)"

        # Progress messages are low priority and coalesce
        self.post(full_message, color, priority=self.LOW, category="progress")


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

        # Status message queue for smart message handling
        self._status_queue = StatusMessageQueue(parent_widget)
        self._status_queue.message_ready.connect(self._on_queued_message)
        self._status_queue.start()

    def setup_animations(self):
        """Setup all animations for the UI."""
        self._setup_button_hover_effects()
        self._setup_progress_animation()
        self._setup_status_animations()

    def _on_queued_message(self, message: str, color: str):
        """Handle messages from the status queue."""
        self._apply_status_update(message, color)

    def _setup_button_hover_effects(self):
        """Add subtle hover effects to buttons.

        Widget names come from individual tab .ui files (flattened onto the
        synthetic main-window ui by luma_tools.py) — resolve with getattr so
        a renamed/removed widget degrades gracefully instead of crashing
        startup with AttributeError.
        """
        button_names = [
            'BuildPasses', 'ScanRenders', 'CleanFiles', 'RescanCleanFiles',
            'MP4ScanRenders', 'MP4BrowseOutput', 'MP4BrowseCustomPath', 'MP4Generate',
        ]

        for name in button_names:
            button = getattr(self.ui, name, None)
            if button is not None and hasattr(button, 'installEventFilter'):
                button.installEventFilter(self.parent)

    def _setup_progress_animation(self):
        """Setup smooth progress bar animation."""
        progress_bar = getattr(self.ui, 'progressBar', None)
        if progress_bar is None:
            self.progress_animation = None
            return
        self.progress_animation = QPropertyAnimation(progress_bar, b"value")
        self.progress_animation.setDuration(500)
        self.progress_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._animations.append(self.progress_animation)

    def _setup_status_animations(self):
        """Setup animations for status label updates."""
        status_label = getattr(self.ui, 'StatusLabel', None)
        if status_label is None:
            self.status_opacity = None
            self._last_status_message = None
            self._last_status_color = None
            self._last_status_context = None
            return
        self.status_opacity = QGraphicsOpacityEffect(status_label)
        status_label.setGraphicsEffect(self.status_opacity)
        self.status_opacity.setOpacity(1.0)
        self._last_status_message = None
        self._last_status_color = None
        self._last_status_context = None  # Track context for smart animation

    def animate_button_click(self, button):
        """Animate button click with scale effect."""
        if not button.isEnabled():
            return

        original_geometry = button.geometry()
        shrunk_geometry = QRect(
            original_geometry.x() + 2,
            original_geometry.y() + 2,
            original_geometry.width() - 4,
            original_geometry.height() - 4
        )

        shrink = create_property_animation(
            button, b"geometry", original_geometry, shrunk_geometry,
            duration=80, easing=QEasingCurve.InOutQuad
        )
        expand = create_property_animation(
            button, b"geometry", shrunk_geometry, original_geometry,
            duration=80, easing=QEasingCurve.InOutQuad
        )

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

    def update_status_animated(self, message, color=Color.ACCENT, priority=None, use_queue=True):
        """
        Update status label with fade animation.

        Args:
            message: Status message to display
            color: Hex color for the message
            priority: Optional priority (URGENT, HIGH, NORMAL, LOW from StatusMessageQueue)
            use_queue: If True, use the smart queue; if False, update immediately
        """
        if use_queue and hasattr(self, '_status_queue'):
            # Route through the smart queue
            self._status_queue.post(message, color, priority=priority)
        else:
            # Direct update (for backwards compatibility or urgent messages)
            self._apply_status_update(message, color)

    def _extract_context(self, message):
        """Extract context/source from message for smart animation decisions.

        Context is determined by:
        - Message prefix before ':' (e.g., "ComfyUI:", "Gallery:", "Ready")
        - Or the first word if no colon
        """
        if not message:
            return None
        # Check for prefix pattern like "ComfyUI:", "Gallery:", etc.
        if ':' in message:
            return message.split(':', 1)[0].strip()
        # Use first word as context
        return message.split()[0] if message.split() else None

    def _apply_status_update(self, message, color):
        """Apply status update directly to the UI.

        Only animates (fades) when context/task changes.
        Updates instantly when just the content changes within same context.
        """
        if message == self._last_status_message and color == self._last_status_color:
            return

        # Extract context to decide if we should animate
        current_context = self._extract_context(message)
        context_changed = current_context != self._last_status_context

        self._last_status_message = message
        self._last_status_color = color
        self._last_status_context = current_context

        # Update the label
        self.ui.StatusLabel.setText(message)
        self.ui.StatusLabel.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 10pt;")

        # Only animate if context changed (different task/source)
        if context_changed:
            fade_anim = create_property_animation(
                self.status_opacity, b"opacity", 0.3, 1.0,
                duration=300, easing=QEasingCurve.InOutCubic
            )
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

        # Connect to clicked signal to reset styling. Keep the slot callable
        # itself for the disconnect — disconnect(<connection handle>) raised
        # TypeError in PySide6 and was silently swallowed, so every
        # pulse/reset cycle stacked another closure on the button.
        def on_clicked():
            self._reset_button_style(button)

        button._ready_slot = on_clicked
        button.clicked.connect(on_clicked)

    def _reset_button_style(self, button):
        """Reset a button's style back to its original state."""
        if button not in self._ready_buttons:
            return

        # Restore original style
        original_style = self._ready_buttons.pop(button)
        button.setStyleSheet(original_style)

        # Disconnect the click handler (by slot, which PySide6 supports)
        slot = getattr(button, '_ready_slot', None)
        if slot is not None:
            try:
                button.clicked.disconnect(slot)
            except (RuntimeError, TypeError):
                pass  # Signal already gone (widget being destroyed)
            try:
                delattr(button, '_ready_slot')
            except AttributeError:
                pass

    def clear_button_ready(self, button):
        """
        Manually clear the 'ready' styling from a button.
        Use this when conditions change and the button should no longer be highlighted.
        """
        self._reset_button_style(button)

    def fade_in_widget(self, widget, duration=300):
        """Fade in a widget."""
        fade_anim = create_fade_animation(widget, fade_in=True, duration=duration, easing=QEasingCurve.InOutCubic)
        fade_anim.start()

        self._animations.append(fade_anim)
        QTimer.singleShot(duration + 50, lambda: self._cleanup_animation(fade_anim))

    def fade_out_widget(self, widget, duration=300):
        """Fade out a widget."""
        fade_anim = create_fade_animation(widget, fade_in=False, duration=duration, easing=QEasingCurve.InOutCubic)
        fade_anim.start()

        self._animations.append(fade_anim)
        QTimer.singleShot(duration + 50, lambda: self._cleanup_animation(fade_anim))

    def _cleanup_animation(self, animation):
        """Clean up animation reference."""
        if animation in self._animations:
            self._animations.remove(animation)

    # =========================================================================
    # STATUS MESSAGE METHODS
    # =========================================================================

    def show_success(self, message, show_in_status=True):
        """
        Show a success message in log and optionally status bar.

        Args:
            message: Success message
            show_in_status: If True, also show in status bar
        """
        logger.info(f"SUCCESS: {message}")
        if show_in_status and hasattr(self, '_status_queue'):
            from styles import StatusColors
            self._status_queue.post(message, StatusColors.SUCCESS,
                                   priority=StatusMessageQueue.HIGH)

    def show_error(self, message, show_in_status=True):
        """
        Show an error message in log and optionally status bar.

        Args:
            message: Error message
            show_in_status: If True, also show in status bar
        """
        logger.error(f"ERROR: {message}")
        if show_in_status and hasattr(self, '_status_queue'):
            from styles import StatusColors
            self._status_queue.post(message, StatusColors.ERROR,
                                   priority=StatusMessageQueue.URGENT)

    def show_warning(self, message, show_in_status=True):
        """
        Show a warning message in log and optionally status bar.

        Args:
            message: Warning message
            show_in_status: If True, also show in status bar
        """
        logger.warning(f"WARNING: {message}")
        if show_in_status and hasattr(self, '_status_queue'):
            from styles import StatusColors
            self._status_queue.post(message, StatusColors.WARNING,
                                   priority=StatusMessageQueue.HIGH)

    def show_info(self, message, show_in_status=True):
        """
        Show an info message in log and optionally status bar.

        Args:
            message: Info message
            show_in_status: If True, also show in status bar
        """
        logger.info(f"INFO: {message}")
        if show_in_status and hasattr(self, '_status_queue'):
            from styles import StatusColors
            self._status_queue.post(message, StatusColors.INFO,
                                   priority=StatusMessageQueue.NORMAL)

    # =========================================================================
    # ACTIVITY TRACKING METHODS
    # =========================================================================

    def start_activity(self, activity_id: str, message: str, color: str = None):
        """
        Start tracking an ongoing activity with elapsed time display.

        The status bar will show the message with elapsed time, e.g.:
        "Loading files... (5s)" -> "Loading files... (1m 30s)"

        Args:
            activity_id: Unique identifier for this activity
            message: Base message (elapsed time will be appended)
            color: Status color (defaults to INFO blue)
        """
        if hasattr(self, '_status_queue'):
            from styles import StatusColors
            color = color or StatusColors.INFO
            template = f"{message} ({{elapsed}})"
            self._status_queue.start_activity(activity_id, template, color)

    def update_activity(self, activity_id: str, message: str = None, detail: str = None):
        """
        Update an ongoing activity's message or add detail.

        Args:
            activity_id: The activity to update
            message: New base message (optional)
            detail: Additional detail to append (optional)
        """
        if hasattr(self, '_status_queue'):
            template = f"{message} ({{elapsed}})" if message else None
            self._status_queue.update_activity(activity_id, template, detail)

    def end_activity(self, activity_id: str, final_message: str = None, color: str = None):
        """
        End an ongoing activity and optionally show a final message.

        Args:
            activity_id: The activity to end
            final_message: Message to show after activity ends (optional)
            color: Color for final message (optional)
        """
        if hasattr(self, '_status_queue'):
            self._status_queue.end_activity(activity_id)
            if final_message:
                from styles import StatusColors
                color = color or StatusColors.SUCCESS
                self._status_queue.post(final_message, color, priority=StatusMessageQueue.HIGH)

    def show_progress(self, current: int, total: int, message: str, color: str = None):
        """
        Show progress in the status bar.

        Args:
            current: Current item number (1-based)
            total: Total number of items
            message: Base message
            color: Status color (defaults to INFO)
        """
        if hasattr(self, '_status_queue'):
            from styles import StatusColors
            color = color or StatusColors.INFO
            self._status_queue.post_progress(current, total, message, color)

    def post_status(self, message: str, color: str, priority: str = "normal"):
        """
        Post a status message with explicit priority.

        Args:
            message: Status message
            color: Hex color
            priority: "urgent", "high", "normal", or "low"
        """
        if hasattr(self, '_status_queue'):
            priority_map = {
                "urgent": StatusMessageQueue.URGENT,
                "high": StatusMessageQueue.HIGH,
                "normal": StatusMessageQueue.NORMAL,
                "low": StatusMessageQueue.LOW,
            }
            p = priority_map.get(priority.lower(), StatusMessageQueue.NORMAL)
            self._status_queue.post(message, color, priority=p)
