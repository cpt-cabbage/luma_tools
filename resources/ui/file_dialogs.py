"""
Shared file dialog helpers for Luma Tools.

Consolidates duplicated file dialog patterns across tabs with:
- Automatic "last browsed directory" memory per context
- Consistent dialog options
- Simple one-line API for common operations
"""

import os
from typing import Optional, Tuple

from PySide6.QtWidgets import QWidget, QFileDialog


def browse_directory_with_memory(
    parent: QWidget,
    context: str,
    title: str,
    fallback_path: Optional[str] = None,
    options: QFileDialog.Options = QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
) -> Optional[str]:
    """
    Browse for a directory with last-location memory.

    Args:
        parent: Parent widget for the dialog
        context: Unique key for remembering this dialog's last location
        title: Dialog title
        fallback_path: Default path if no last location exists
        options: QFileDialog options

    Returns:
        Selected directory path, or None if cancelled
    """
    from core.user_preferences import get_last_browse_directory, set_last_browse_directory

    # Get starting directory
    last_dir = get_last_browse_directory(context)
    if not last_dir or not os.path.exists(last_dir):
        if fallback_path and os.path.exists(fallback_path):
            last_dir = fallback_path
        else:
            last_dir = os.path.expanduser("~")

    # Show dialog
    selected = QFileDialog.getExistingDirectory(
        parent,
        title,
        last_dir,
        options
    )

    # Save selection if successful
    if selected:
        set_last_browse_directory(context, selected)

    return selected if selected else None


def browse_file_with_memory(
    parent: QWidget,
    context: str,
    title: str,
    file_filter: str = "All Files (*.*)",
    fallback_path: Optional[str] = None
) -> Optional[str]:
    """
    Browse for a file with last-location memory.

    Args:
        parent: Parent widget for the dialog
        context: Unique key for remembering this dialog's last location
        title: Dialog title
        file_filter: File type filter (e.g., "Images (*.png *.jpg)")
        fallback_path: Default path if no last location exists

    Returns:
        Selected file path, or None if cancelled
    """
    from core.user_preferences import get_last_browse_directory, set_last_browse_directory

    # Get starting directory
    last_dir = get_last_browse_directory(context)
    if not last_dir or not os.path.exists(last_dir):
        if fallback_path and os.path.exists(os.path.dirname(fallback_path)):
            last_dir = os.path.dirname(fallback_path)
        else:
            last_dir = os.path.expanduser("~")

    # Show dialog
    selected, _ = QFileDialog.getOpenFileName(
        parent,
        title,
        last_dir,
        file_filter
    )

    # Save directory if successful
    if selected:
        set_last_browse_directory(context, os.path.dirname(selected))

    return selected if selected else None


def save_file_with_memory(
    parent: QWidget,
    context: str,
    title: str,
    default_filename: str = "",
    file_filter: str = "All Files (*.*)",
    fallback_path: Optional[str] = None
) -> Optional[str]:
    """
    Save file dialog with last-location memory.

    Args:
        parent: Parent widget for the dialog
        context: Unique key for remembering this dialog's last location
        title: Dialog title
        default_filename: Suggested filename
        file_filter: File type filter (e.g., "MP4 Video (*.mp4)")
        fallback_path: Default directory if no last location exists

    Returns:
        Selected file path, or None if cancelled
    """
    from core.user_preferences import get_last_browse_directory, set_last_browse_directory

    # Get starting directory
    last_dir = get_last_browse_directory(context)
    if not last_dir or not os.path.exists(last_dir):
        if fallback_path and os.path.exists(fallback_path):
            last_dir = fallback_path
        else:
            last_dir = os.path.join(os.path.expanduser("~"), "Videos")
            if not os.path.exists(last_dir):
                last_dir = os.path.expanduser("~")

    # Build full path with filename
    full_path = os.path.join(last_dir, default_filename) if default_filename else last_dir

    # Show dialog
    selected, _ = QFileDialog.getSaveFileName(
        parent,
        title,
        full_path,
        file_filter
    )

    # Save directory if successful
    if selected:
        set_last_browse_directory(context, os.path.dirname(selected))

    return selected if selected else None


def browse_multiple_files_with_memory(
    parent: QWidget,
    context: str,
    title: str,
    file_filter: str = "All Files (*.*)",
    fallback_path: Optional[str] = None
) -> Tuple[str, ...]:
    """
    Browse for multiple files with last-location memory.

    Args:
        parent: Parent widget for the dialog
        context: Unique key for remembering this dialog's last location
        title: Dialog title
        file_filter: File type filter
        fallback_path: Default path if no last location exists

    Returns:
        Tuple of selected file paths, or empty tuple if cancelled
    """
    from core.user_preferences import get_last_browse_directory, set_last_browse_directory

    # Get starting directory
    last_dir = get_last_browse_directory(context)
    if not last_dir or not os.path.exists(last_dir):
        if fallback_path and os.path.exists(fallback_path):
            last_dir = fallback_path
        else:
            last_dir = os.path.expanduser("~")

    # Show dialog
    selected, _ = QFileDialog.getOpenFileNames(
        parent,
        title,
        last_dir,
        file_filter
    )

    # Save directory if successful
    if selected:
        set_last_browse_directory(context, os.path.dirname(selected[0]))

    return tuple(selected) if selected else ()
