"""
Small reusable UI widgets and utilities.

Contains simple widgets and helper functions used across the application.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
from PySide6.QtWidgets import (
    QWidget, QMenu, QPushButton, QFileDialog
)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def show_popup_menu(
    parent: QWidget,
    button: QPushButton,
    items: List[Tuple[str, Any]],
    current: Any = None,
    submenus: Optional[Dict[str, List[Tuple[str, Any]]]] = None
) -> Optional[Any]:
    """
    Show a popup menu below a button and return the selected data.

    Args:
        parent: Parent widget for the menu
        button: Button to position the menu below
        items: List of (display_name, data) tuples for menu items
        current: Currently selected data value (will show checkmark)
        submenus: Optional dict of folder_name -> items for nested submenus

    Returns:
        Selected item's data, or None if cancelled
    """
    menu = QMenu(parent)

    for display, data in items:
        action = menu.addAction(display)
        action.setData(data)
        if data == current:
            action.setCheckable(True)
            action.setChecked(True)

    if submenus:
        for folder, folder_items in submenus.items():
            submenu = menu.addMenu(folder)
            for display, data in folder_items:
                action = submenu.addAction(display)
                action.setData(data)
                if data == current:
                    action.setCheckable(True)
                    action.setChecked(True)

    result = menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))
    return result.data() if result else None


def browse_directory(
    parent: QWidget,
    title: str,
    context: str,
    callback: Callable[[str], None]
) -> bool:
    """
    Show a directory browser dialog with last-directory memory.

    Args:
        parent: Parent widget for the dialog
        title: Dialog title
        context: Settings key for remembering the last directory
        callback: Function to call with the selected path

    Returns:
        True if a directory was selected, False if cancelled
    """
    # Import here to avoid circular imports
    import sys
    sys.path.insert(0, str(parent.window().python_path) if hasattr(parent.window(), 'python_path') else '')
    try:
        from settings_manager import get_last_browse_directory, set_last_browse_directory
    except ImportError:
        # Fallback if settings_manager not available
        def get_last_browse_directory(ctx):
            return ""
        def set_last_browse_directory(ctx, path):
            pass

    last_dir = get_last_browse_directory(context)
    path = QFileDialog.getExistingDirectory(parent, title, last_dir or "")

    if path:
        set_last_browse_directory(context, path)
        callback(path)
        return True
    return False


def browse_file(
    parent: QWidget,
    title: str,
    context: str,
    file_filter: str,
    callback: Callable[[str], None]
) -> bool:
    """
    Show a file browser dialog with last-directory memory.

    Args:
        parent: Parent widget for the dialog
        title: Dialog title
        context: Settings key for remembering the last directory
        file_filter: File filter string (e.g., "JSON Files (*.json)")
        callback: Function to call with the selected path

    Returns:
        True if a file was selected, False if cancelled
    """
    import sys
    import os
    sys.path.insert(0, str(parent.window().python_path) if hasattr(parent.window(), 'python_path') else '')
    try:
        from settings_manager import get_last_browse_directory, set_last_browse_directory
    except ImportError:
        def get_last_browse_directory(ctx):
            return ""
        def set_last_browse_directory(ctx, path):
            pass

    last_dir = get_last_browse_directory(context)
    path, _ = QFileDialog.getOpenFileName(parent, title, last_dir or "", file_filter)

    if path:
        set_last_browse_directory(context, os.path.dirname(path))
        callback(path)
        return True
    return False
