"""
Star Rating Widget for ComfyUI Model Picker.

Interactive 5-star rating widget with:
- Display mode: Shows average rating with filled/empty stars
- Interactive mode: Click to set rating with hover preview
- Half-star display for decimal averages
- Smooth hover animations
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPainterPath, QPolygonF
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

logger = logging.getLogger(__name__)

# Colors
STAR_FILLED_COLOR = QColor("#fbbf24")  # Gold
STAR_EMPTY_COLOR = QColor("#4a4a4a")   # Gray
STAR_HOVER_COLOR = QColor("#fcd34d")   # Lighter gold for hover


class StarWidget(QWidget):
    """Single star widget with partial fill support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fill_amount = 0.0  # 0.0 = empty, 1.0 = full, 0.5 = half
        self._hover = False
        self._hover_fill = 0.0

        self.setFixedSize(20, 20)
        self.setCursor(Qt.PointingHandCursor)

    def get_fill_amount(self) -> float:
        return self._fill_amount

    def set_fill_amount(self, value: float) -> None:
        self._fill_amount = max(0.0, min(1.0, value))
        self.update()

    fill_amount = Property(float, get_fill_amount, set_fill_amount)

    def set_hover(self, hover: bool, fill: float = 1.0) -> None:
        """Set hover state and fill amount for preview."""
        self._hover = hover
        self._hover_fill = fill if hover else 0.0
        self.update()

    def paintEvent(self, event):
        """Paint the star with current fill amount."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate effective fill (hover takes precedence)
        fill = self._hover_fill if self._hover else self._fill_amount

        # Draw star path
        path = self._create_star_path()

        # Draw empty star background
        painter.setPen(Qt.NoPen)
        painter.setBrush(STAR_EMPTY_COLOR)
        painter.drawPath(path)

        # Draw filled portion
        if fill > 0:
            painter.setClipRect(0, 0, int(self.width() * fill), self.height())
            color = STAR_HOVER_COLOR if self._hover else STAR_FILLED_COLOR
            painter.setBrush(color)
            painter.drawPath(path)

    def _create_star_path(self) -> QPainterPath:
        """Create a 5-pointed star path."""
        import math

        path = QPainterPath()
        cx, cy = self.width() / 2, self.height() / 2
        outer_r = min(self.width(), self.height()) / 2 - 1
        inner_r = outer_r * 0.4

        points = []
        for i in range(10):
            angle = math.radians(i * 36 - 90)  # Start at top
            r = outer_r if i % 2 == 0 else inner_r
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))

        path.moveTo(points[0][0], points[0][1])
        for x, y in points[1:]:
            path.lineTo(x, y)
        path.closeSubpath()

        return path


class StarRatingWidget(QWidget):
    """
    Interactive 5-star rating widget.

    Modes:
    - Display mode (interactive=False): Shows average rating
    - Interactive mode (interactive=True): User can click to rate

    Signals:
        rating_changed(int): Emitted when user clicks to rate (1-5)
    """

    rating_changed = Signal(int)

    def __init__(
        self,
        parent=None,
        rating: float = 0.0,
        interactive: bool = True,
        show_count: bool = False,
        size: int = 20
    ):
        """
        Initialize star rating widget.

        Args:
            parent: Parent widget
            rating: Initial rating (0.0-5.0)
            interactive: Allow user to click to rate
            show_count: Show rating count label after stars
            size: Size of each star in pixels
        """
        super().__init__(parent)
        self._rating = rating
        self._interactive = interactive
        self._hover_rating = 0
        self._rating_count = 0
        self._size = size

        self._setup_ui(show_count)
        self._update_stars()

    def _setup_ui(self, show_count: bool):
        """Set up the UI layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Create 5 star widgets
        self._stars = []
        for i in range(5):
            star = StarWidget()
            star.setFixedSize(self._size, self._size)
            if self._interactive:
                star.setCursor(Qt.PointingHandCursor)
            else:
                star.setCursor(Qt.ArrowCursor)
            layout.addWidget(star)
            self._stars.append(star)

        # Optional count label
        self._count_label = None
        if show_count:
            self._count_label = QLabel("(0)")
            self._count_label.setStyleSheet("color: #888; font-size: 11px; margin-left: 4px;")
            layout.addWidget(self._count_label)

        layout.addStretch()

    def _update_stars(self):
        """Update star fill amounts based on current rating."""
        for i, star in enumerate(self._stars):
            star_value = i + 1
            if self._rating >= star_value:
                star.set_fill_amount(1.0)
            elif self._rating > star_value - 1:
                # Partial fill for decimal ratings
                star.set_fill_amount(self._rating - (star_value - 1))
            else:
                star.set_fill_amount(0.0)

    def set_rating(self, rating: float) -> None:
        """Set the displayed rating (0.0-5.0)."""
        self._rating = max(0.0, min(5.0, rating))
        self._update_stars()

    def get_rating(self) -> float:
        """Get the current rating value."""
        return self._rating

    def set_rating_count(self, count: int) -> None:
        """Set the rating count display."""
        self._rating_count = count
        if self._count_label:
            self._count_label.setText(f"({count})")

    def set_interactive(self, interactive: bool) -> None:
        """Set whether the widget is interactive."""
        self._interactive = interactive
        cursor = Qt.PointingHandCursor if interactive else Qt.ArrowCursor
        for star in self._stars:
            star.setCursor(cursor)

    def enterEvent(self, event):
        """Handle mouse entering the widget."""
        if not self._interactive:
            return
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leaving the widget."""
        if not self._interactive:
            return
        self._hover_rating = 0
        for star in self._stars:
            star.set_hover(False)
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse movement for hover preview."""
        if not self._interactive:
            return

        # Determine which star is being hovered
        pos = event.position()
        hover_rating = 0

        for i, star in enumerate(self._stars):
            star_rect = star.geometry()
            if pos.x() >= star_rect.left() and pos.x() < star_rect.right():
                hover_rating = i + 1
                break
            elif pos.x() >= star_rect.right():
                hover_rating = i + 1

        if hover_rating != self._hover_rating:
            self._hover_rating = hover_rating
            for i, star in enumerate(self._stars):
                star.set_hover(i < hover_rating)

    def mousePressEvent(self, event):
        """Handle click to set rating."""
        if not self._interactive or event.button() != Qt.LeftButton:
            return

        # Determine which star was clicked
        pos = event.position()
        clicked_rating = 0

        for i, star in enumerate(self._stars):
            star_rect = star.geometry()
            if pos.x() >= star_rect.left() and pos.x() <= star_rect.right():
                clicked_rating = i + 1
                break

        if clicked_rating > 0:
            self._rating = float(clicked_rating)
            self._update_stars()
            self.rating_changed.emit(clicked_rating)

    def sizeHint(self):
        """Return preferred size."""
        from PySide6.QtCore import QSize
        width = self._size * 5 + 2 * 4  # 5 stars + spacing
        if self._count_label:
            width += 40  # Extra space for count
        return QSize(width, self._size)


class CompactStarRating(QWidget):
    """
    Compact star rating display for use in buttons and small spaces.

    Shows: ★★★★☆ (4.2) format
    """

    def __init__(
        self,
        parent=None,
        rating: float = 0.0,
        show_value: bool = True,
        size: int = 14
    ):
        """
        Initialize compact star rating.

        Args:
            parent: Parent widget
            rating: Rating value (0.0-5.0)
            show_value: Show numeric value in parentheses
            size: Font size for stars
        """
        super().__init__(parent)
        self._rating = rating
        self._show_value = show_value
        self._size = size

        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._stars_label = QLabel()
        self._stars_label.setStyleSheet(f"color: #fbbf24; font-size: {self._size}px;")
        layout.addWidget(self._stars_label)

        if self._show_value:
            self._value_label = QLabel()
            self._value_label.setStyleSheet(f"color: #888; font-size: {self._size - 2}px;")
            layout.addWidget(self._value_label)
        else:
            self._value_label = None

        self._update_display()

    def _update_display(self):
        """Update the star display."""
        filled = int(self._rating)
        half = (self._rating - filled) >= 0.5
        empty = 5 - filled - (1 if half else 0)

        # Use Unicode stars: ★ (filled), ☆ (empty)
        stars = "★" * filled
        if half:
            stars += "★"  # Use full star for half (simpler)
            empty = 5 - filled - 1
        stars += "☆" * empty

        self._stars_label.setText(stars)

        if self._value_label and self._rating > 0:
            self._value_label.setText(f"({self._rating:.1f})")
        elif self._value_label:
            self._value_label.setText("")

    def set_rating(self, rating: float) -> None:
        """Set the displayed rating."""
        self._rating = max(0.0, min(5.0, rating))
        self._update_display()

    def get_rating(self) -> float:
        """Get the current rating."""
        return self._rating
