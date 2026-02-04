"""
Rating Breakdown Widget for ComfyUI Model Dialog.

Displays a horizontal bar chart showing the distribution of ratings
(how many 5-star, 4-star, etc. ratings a model has received).
"""

import logging
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QProgressBar
)

logger = logging.getLogger(__name__)

# Colors matching the star rating gold theme
BAR_FILLED_COLOR = "#fbbf24"  # Gold
BAR_EMPTY_COLOR = "#3c3c3c"   # Dark gray


class RatingBreakdownWidget(QWidget):
    """
    Widget displaying rating distribution as horizontal bars.

    Shows 5 rows (one for each star level), with bars indicating
    the count/percentage of ratings at that level.
    """

    def __init__(self, parent=None):
        """
        Initialize rating breakdown widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._ratings = {}  # username -> rating
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Create a row for each star level (5 down to 1)
        self._bars = {}
        self._count_labels = {}

        for stars in range(5, 0, -1):
            row = QHBoxLayout()
            row.setSpacing(8)

            # Star label (e.g., "5 ★")
            star_label = QLabel(f"{stars} ★")
            star_label.setFixedWidth(35)
            star_label.setStyleSheet("color: #fbbf24; font-size: 12px;")
            star_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(star_label)

            # Progress bar for this star level
            bar = QProgressBar()
            bar.setMinimum(0)
            bar.setMaximum(100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(14)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {BAR_EMPTY_COLOR};
                    border: none;
                    border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background-color: {BAR_FILLED_COLOR};
                    border-radius: 3px;
                }}
            """)
            row.addWidget(bar, 1)
            self._bars[stars] = bar

            # Count label
            count_label = QLabel("0")
            count_label.setFixedWidth(30)
            count_label.setStyleSheet("color: #888; font-size: 11px;")
            count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(count_label)
            self._count_labels[stars] = count_label

            layout.addLayout(row)

    def set_ratings(self, ratings: Dict[str, int]) -> None:
        """
        Set the ratings data and update the display.

        Args:
            ratings: Dict mapping username to rating value (1-5)
        """
        self._ratings = ratings or {}
        self._update_display()

    def _update_display(self):
        """Update the bar chart based on current ratings."""
        # Count ratings per star level
        counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rating in self._ratings.values():
            if 1 <= rating <= 5:
                counts[rating] = counts.get(rating, 0) + 1

        # Find max count for scaling
        total = sum(counts.values())
        max_count = max(counts.values()) if counts.values() else 1

        # Update bars
        for stars in range(1, 6):
            count = counts.get(stars, 0)

            # Calculate percentage relative to max (for visual scaling)
            # This makes the largest bar always fill 100%
            if max_count > 0:
                percentage = int((count / max_count) * 100)
            else:
                percentage = 0

            self._bars[stars].setValue(percentage)
            self._count_labels[stars].setText(str(count))

    def clear(self):
        """Clear all ratings data."""
        self._ratings = {}
        self._update_display()
