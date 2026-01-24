"""
Dialog helper functions for Luma Tools.

Provides simplified wrappers around QMessageBox for common dialog patterns,
reducing boilerplate and ensuring consistent dialog behavior across the application.
"""

from typing import Optional
from PySide6.QtWidgets import QMessageBox, QWidget, QApplication


def get_active_window() -> Optional[QWidget]:
    """Get the currently active top-level window for dialogs."""
    for widget in QApplication.topLevelWidgets():
        if widget.isVisible() and hasattr(widget, 'windowTitle'):
            return widget
    return None


def confirm_action(
    title: str,
    message: str,
    parent: Optional[QWidget] = None,
    detail: Optional[str] = None,
    default_yes: bool = False
) -> bool:
    """
    Show a yes/no confirmation dialog.

    Args:
        title: Dialog title
        message: Main message to display
        parent: Parent widget (auto-detected if None)
        detail: Optional detailed text
        default_yes: If True, Yes button is default; otherwise No is default

    Returns:
        True if user clicked Yes, False otherwise
    """
    parent = parent or get_active_window()
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.Yes if default_yes else QMessageBox.No)
    if detail:
        box.setDetailedText(detail)
    return box.exec() == QMessageBox.Yes


def show_warning(
    title: str,
    message: str,
    parent: Optional[QWidget] = None,
    detail: Optional[str] = None
):
    """
    Show a warning dialog.

    Args:
        title: Dialog title
        message: Warning message to display
        parent: Parent widget (auto-detected if None)
        detail: Optional detailed text
    """
    parent = parent or get_active_window()
    box = QMessageBox(QMessageBox.Warning, title, message, QMessageBox.Ok, parent)
    if detail:
        box.setDetailedText(detail)
    box.exec()


def show_error(
    title: str,
    message: str,
    parent: Optional[QWidget] = None,
    detail: Optional[str] = None
):
    """
    Show an error dialog.

    Args:
        title: Dialog title
        message: Error message to display
        parent: Parent widget (auto-detected if None)
        detail: Optional detailed text (e.g., traceback)
    """
    parent = parent or get_active_window()
    box = QMessageBox(QMessageBox.Critical, title, message, QMessageBox.Ok, parent)
    if detail:
        box.setDetailedText(detail)
    box.exec()


def show_info(
    title: str,
    message: str,
    parent: Optional[QWidget] = None,
    detail: Optional[str] = None
):
    """
    Show an informational dialog.

    Args:
        title: Dialog title
        message: Information to display
        parent: Parent widget (auto-detected if None)
        detail: Optional detailed text
    """
    parent = parent or get_active_window()
    box = QMessageBox(QMessageBox.Information, title, message, QMessageBox.Ok, parent)
    if detail:
        box.setDetailedText(detail)
    box.exec()
