"""
Unified styling constants for all loading screens in Luma Shot Tools.
Ensures consistent look and feel across splash screen, loading overlay, and other UI elements.
"""

import os
from PySide2.QtGui import QColor, QFont


class LoadingStyles:
    """Unified styling constants for loading screens."""

    # Colors
    PRIMARY_COLOR = QColor(74, 158, 255)  # #4a9eff - Blue accent
    BACKGROUND_COLOR = QColor(30, 30, 30)  # #1e1e1e - Dark background
    SECONDARY_BG_COLOR = QColor(42, 42, 42)  # #2a2a2a - Lighter dark
    TEXT_PRIMARY_COLOR = QColor(255, 255, 255)  # #ffffff - White
    TEXT_SECONDARY_COLOR = QColor(160, 160, 160)  # #a0a0a0 - Gray
    TEXT_TERTIARY_COLOR = QColor(136, 136, 136)  # #888888 - Darker gray

    # Color strings (for stylesheets)
    PRIMARY_COLOR_STR = "#4a9eff"
    BACKGROUND_COLOR_STR = "#1e1e1e"
    SECONDARY_BG_COLOR_STR = "#2a2a2a"
    TEXT_PRIMARY_COLOR_STR = "#ffffff"
    TEXT_SECONDARY_COLOR_STR = "#a0a0a0"
    TEXT_TERTIARY_COLOR_STR = "#888888"

    # Fonts
    TITLE_FONT = QFont("Segoe UI", 24, QFont.Bold)
    MAIN_TEXT_FONT = QFont("Segoe UI", 12)
    SUB_TEXT_FONT = QFont("Segoe UI", 9)
    OVERLAY_TITLE_SIZE = "16pt"
    OVERLAY_SUB_SIZE = "10pt"

    # Logo
    LOGO_SIZE_SPLASH = (120, 120)  # Larger for splash screen
    LOGO_SIZE_OVERLAY = (100, 100)  # Smaller for overlay

    # Spinner
    SPINNER_SIZE = (80, 80)
    SPINNER_LINE_COUNT = 12
    SPINNER_LINE_LENGTH = 20
    SPINNER_LINE_WIDTH = 3
    SPINNER_INNER_RADIUS = 15
    SPINNER_ROTATION_INTERVAL = 50  # milliseconds (20 FPS)

    # Layout
    SPLASH_SIZE = (500, 300)
    SPLASH_MARGIN = 40
    SPLASH_SPACING = 20
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
                background-color: rgba(42, 42, 42, 180);
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #0e4d92, stop:1 {LoadingStyles.PRIMARY_COLOR_STR});
                border-radius: 3px;
            }}
        """

    @staticmethod
    def get_overlay_background_stylesheet():
        """Get overlay background stylesheet."""
        return """
            LoadingOverlay {
                background-color: rgba(30, 30, 30, 220);
                border-radius: 10px;
            }
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
