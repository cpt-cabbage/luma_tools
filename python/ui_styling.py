"""
UI Styling - Stylesheet and UI setup utilities.

This module handles loading and applying stylesheets and UI configuration.
"""

from PySide2.QtCore import QFile, QTextStream
from config import QDARKSTYLE_PATH, CUSTOM_STYLE_PATH


def load_stylesheet():
    """
    Load and combine QDarkStyle base theme with custom stylesheet.

    Returns:
        str: Combined stylesheet string
    """
    # Load QDarkStyle as base theme
    file = QFile(QDARKSTYLE_PATH)
    file.open(QFile.ReadOnly | QFile.Text)
    stream = QTextStream(file)
    base_style = stream.readAll()
    file.close()

    # Load custom stylesheet enhancements
    custom_file = QFile(CUSTOM_STYLE_PATH)
    custom_file.open(QFile.ReadOnly | QFile.Text)
    custom_stream = QTextStream(custom_file)
    custom_style = custom_stream.readAll()
    custom_file.close()

    print(f"Loaded custom stylesheet from: {CUSTOM_STYLE_PATH}")

    # Return combined stylesheet (custom style overrides base)
    return base_style + "\n" + custom_style


def apply_stylesheet(app):
    """
    Apply stylesheet to the application.

    Args:
        app: QApplication instance
    """
    stylesheet = load_stylesheet()
    app.setStyleSheet(stylesheet)
