"""
Style constants and stylesheet utilities for the UI.

Provides unified styling for loading screens, status indicators, and themes.
"""
import os
from PySide2.QtCore import QFile, QTextStream
from PySide2.QtGui import QColor, QFont


class LoadingStyles:
    """Unified styling constants for loading screens."""

    # Colors - AYON Theme
    PRIMARY_COLOR = QColor(74, 158, 255)  # #4a9eff - Light blue accent (for spinner)
    BACKGROUND_COLOR = QColor(33, 37, 43)  # #21252b - Dark background
    SECONDARY_BG_COLOR = QColor(44, 49, 58)  # #2c313a - Lighter dark
    TEXT_PRIMARY_COLOR = QColor(255, 255, 255)  # #ffffff - White
    TEXT_SECONDARY_COLOR = QColor(197, 202, 211)  # #c5cad3 - Light gray
    TEXT_TERTIARY_COLOR = QColor(121, 126, 137)  # #797e89 - Darker gray

    # Color strings (for stylesheets)
    PRIMARY_COLOR_STR = "#4a9eff"
    BACKGROUND_COLOR_STR = "#21252b"
    SECONDARY_BG_COLOR_STR = "#2c313a"
    TEXT_PRIMARY_COLOR_STR = "#ffffff"
    TEXT_SECONDARY_COLOR_STR = "#c5cad3"
    TEXT_TERTIARY_COLOR_STR = "#797e89"

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
                background-color: rgba(44, 49, 58, 180);
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #5cadff, stop:1 {LoadingStyles.PRIMARY_COLOR_STR});
                border-radius: 3px;
            }}
        """

    @staticmethod
    def get_overlay_background_stylesheet():
        """Get overlay background stylesheet."""
        return """
            LoadingOverlay {
                background-color: rgba(33, 37, 43, 220);
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


class StatusColors:
    """Predefined colors for status messages - AYON Theme Palette."""
    SUCCESS = "#10b981"  # Modern green
    ERROR = "#ef4444"    # Modern red
    WARNING = "#f59e0b"  # Modern orange
    INFO = "#4a9eff"     # AYON blue
    SCANNING = "#8b5cf6" # Modern purple


def load_stylesheet(path):
    """
    Load a Qt stylesheet from a file.

    Args:
        path: Path to the .qss stylesheet file

    Returns:
        str: The stylesheet content, or empty string if file not found
    """
    if not os.path.exists(path):
        print(f"Stylesheet not found: {path}")
        return ""

    file = QFile(path)
    if file.open(QFile.ReadOnly | QFile.Text):
        stream = QTextStream(file)
        stylesheet = stream.readAll()
        file.close()
        return stylesheet
    return ""


def apply_stylesheet(widget, path):
    """
    Apply a stylesheet to a widget.

    Args:
        widget: The QWidget to style
        path: Path to the .qss stylesheet file
    """
    stylesheet = load_stylesheet(path)
    if stylesheet:
        widget.setStyleSheet(stylesheet)
