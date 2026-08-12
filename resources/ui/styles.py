"""
Style constants and stylesheet utilities for the UI.

Provides unified styling for loading screens, status indicators, and themes.
"""
import os
import logging
from PySide6.QtGui import QColor, QFont
from core.config import UIColors
from core.design_tokens import Color, Radius

logger = logging.getLogger(__name__)


class LoadingStyles:
    """Unified styling constants for loading screens."""

    # Colors — all derived from core.design_tokens. This class used to carry
    # its own hardcoded palette, which was a third source of truth alongside
    # UIColors and the stylesheet, and none of the three agreed.
    PRIMARY_COLOR_STR = Color.ACCENT
    BACKGROUND_COLOR_STR = Color.PAGE
    SECONDARY_BG_COLOR_STR = Color.PANEL
    TEXT_PRIMARY_COLOR_STR = Color.TEXT
    TEXT_SECONDARY_COLOR_STR = Color.TEXT_SECONDARY
    TEXT_TERTIARY_COLOR_STR = Color.TEXT_MUTED

    PRIMARY_COLOR = QColor(PRIMARY_COLOR_STR)
    BACKGROUND_COLOR = QColor(BACKGROUND_COLOR_STR)
    SECONDARY_BG_COLOR = QColor(SECONDARY_BG_COLOR_STR)
    TEXT_PRIMARY_COLOR = QColor(TEXT_PRIMARY_COLOR_STR)
    TEXT_SECONDARY_COLOR = QColor(TEXT_SECONDARY_COLOR_STR)
    TEXT_TERTIARY_COLOR = QColor(TEXT_TERTIARY_COLOR_STR)

    # Fonts
    TITLE_FONT = QFont("Segoe UI", 24, QFont.Bold)
    MAIN_TEXT_FONT = QFont("Segoe UI", 12)
    SUB_TEXT_FONT = QFont("Segoe UI", 9)
    OVERLAY_TITLE_SIZE = "16pt"
    OVERLAY_SUB_SIZE = "10pt"

    # Logo
    LOGO_SIZE_SPLASH = (200, 200)  # Larger for splash screen
    LOGO_SIZE_OVERLAY = (100, 100)  # Smaller for overlay

    # Spinner
    SPINNER_SIZE = (40, 40)  # Reduced size for cleaner look
    SPINNER_LINE_COUNT = 12
    SPINNER_LINE_LENGTH = 10  # Shorter lines for smaller spinner
    SPINNER_LINE_WIDTH = 2  # Thinner lines
    SPINNER_INNER_RADIUS = 6  # Smaller inner radius
    SPINNER_ROTATION_INTERVAL = 50  # milliseconds (20 FPS)

    # Layout
    SPLASH_SIZE = (500, 450)  # Increased height to accommodate larger logo
    SPLASH_MARGIN = 40
    SPLASH_SPACING = 15  # Reduced spacing for better fit
    OVERLAY_SPACING = 20
    BORDER_RADIUS = 15
    OVERLAY_BORDER_RADIUS = 10

    # Progress bar
    PROGRESS_BAR_HEIGHT = 4
    PROGRESS_BAR_SPLASH_HEIGHT = 4
    PROGRESS_BAR_OVERLAY_HEIGHT = 6
    PROGRESS_BAR_OVERLAY_WIDTH = 300

    # Animation
    FADE_DURATION = 300  # milliseconds
    SPINNER_ROTATION_ANGLE = 30  # degrees per step

    @staticmethod
    def get_logo_path():
        """Get the path to the logo file."""
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Icon_white_small.png"
        )

    @staticmethod
    def get_progress_bar_stylesheet(height=4):
        """Get unified progress bar stylesheet."""
        return f"""
            QProgressBar {{
                background-color: {LoadingStyles.SECONDARY_BG_COLOR_STR};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {LoadingStyles.PRIMARY_COLOR_STR};
                border-radius: 2px;
            }}
        """

    @staticmethod
    def get_overlay_progress_stylesheet():
        """Get progress bar stylesheet for overlay (with gradient)."""
        return f"""
            QProgressBar {{
                background-color: {Color.SUNKEN};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 {Color.ACCENT_HOVER},
                                                  stop:1 {Color.ACCENT});
                border-radius: 3px;
            }}
        """

    @staticmethod
    def get_overlay_background_stylesheet():
        """Get overlay background stylesheet."""
        return f"""
            LoadingOverlay {{
                background-color: {Color.OVERLAY_SCRIM};
                border-radius: {Radius.MD}px;
            }}
        """

    @staticmethod
    def get_status_label_stylesheet():
        """Get status label stylesheet for overlay."""
        return f"""
            QLabel {{
                color: {LoadingStyles.PRIMARY_COLOR_STR};
                font-size: {LoadingStyles.OVERLAY_TITLE_SIZE};
                font-weight: bold;
                background: transparent;
            }}
        """

    @staticmethod
    def get_substatus_label_stylesheet():
        """Get sub-status label stylesheet for overlay."""
        return f"""
            QLabel {{
                color: {LoadingStyles.TEXT_SECONDARY_COLOR_STR};
                font-size: {LoadingStyles.OVERLAY_SUB_SIZE};
                background: transparent;
            }}
        """


class StatusColors:
    """Predefined colors for status messages - references UIColors as single source of truth."""
    SUCCESS = UIColors.SUCCESS
    ERROR = UIColors.ERROR
    WARNING = UIColors.WARNING
    INFO = UIColors.INFO
    SCANNING = UIColors.SCANNING


