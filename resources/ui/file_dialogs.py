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


def _get_start_directory(context: str, fallback_path: Optional[str] = None,
                          check_parent: bool = False) -> str:
    """
    Get starting directory for file dialogs with memory.

    Args:
        context: Unique key for remembering this dialog's last location
        fallback_path: Default path if no last location exists
        check_parent: If True, check parent directory of fallback_path exists

    Returns:
        Valid directory path to start the dialog
    """
    from core.user_preferences import get_last_browse_directory

    last_dir = get_last_browse_directory(context)
    if last_dir and os.path.exists(last_dir):
        return last_dir

    if fallback_path:
        if check_parent:
            parent = os.path.dirname(fallback_path)
            if parent and os.path.exists(parent):
                return parent
        elif os.path.exists(fallback_path):
            return fallback_path

    return os.path.expanduser("~")


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
    from core.user_preferences import set_last_browse_directory

    selected = QFileDialog.getExistingDirectory(
        parent, title, _get_start_directory(context, fallback_path), options
    )

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
    from core.user_preferences import set_last_browse_directory

    selected, _ = QFileDialog.getOpenFileName(
        parent, title, _get_start_directory(context, fallback_path, check_parent=True), file_filter
    )

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
    from core.user_preferences import set_last_browse_directory

    selected, _ = QFileDialog.getOpenFileNames(
        parent,
        title,
        _get_start_directory(context, fallback_path),
        file_filter
    )

    # Save directory if successful
    if selected:
        set_last_browse_directory(context, os.path.dirname(selected[0]))

    return tuple(selected) if selected else ()


# =============================================================================
# Context-Specific Helpers
# =============================================================================
# These eliminate repeated context strings and provide sensible defaults

def browse_workflow_file(parent: QWidget) -> Optional[str]:
    """Browse for a ComfyUI workflow JSON file."""
    return browse_file_with_memory(
        parent,
        context="workflow",
        title="Select ComfyUI Workflow",
        file_filter="Workflow Files (*.json)"
    )


def browse_comfyui_output_dir(parent: QWidget) -> Optional[str]:
    """Browse for ComfyUI network output directory."""
    return browse_directory_with_memory(
        parent,
        context="comfyui_output",
        title="Select ComfyUI Output Directory"
    )


def browse_custom_renders_dir(parent: QWidget) -> Optional[str]:
    """Browse for a custom render directory (for MP4/republish)."""
    return browse_directory_with_memory(
        parent,
        context="renders_custom",
        title="Select Custom Render Directory",
        fallback_path=os.path.join(os.path.expanduser("~"), "Videos")
    )


def browse_images(parent: QWidget, multiple: bool = True) -> Tuple[str, ...]:
    """Browse for image files."""
    file_filter = "Images (*.png *.jpg *.jpeg *.exr *.tiff *.tif *.webp)"
    if multiple:
        return browse_multiple_files_with_memory(
            parent,
            context="images",
            title="Select Images",
            file_filter=file_filter
        )
    else:
        result = browse_file_with_memory(
            parent,
            context="images",
            title="Select Image",
            file_filter=file_filter
        )
        return (result,) if result else ()


def browse_global_settings_dir(parent: QWidget) -> Optional[str]:
    """Browse for global settings directory."""
    return browse_directory_with_memory(
        parent,
        context="global_settings",
        title="Select Global Settings Directory"
    )


def browse_hdri_file(parent: QWidget) -> Optional[str]:
    """Browse for an HDRI/EXR file."""
    return browse_file_with_memory(
        parent,
        context="hdri",
        title="Select HDRI File",
        file_filter="HDRI Files (*.exr *.hdr *.hdri)"
    )


def save_mp4_file(parent: QWidget, default_filename: str = "output.mp4") -> Optional[str]:
    """Save dialog for MP4 output."""
    return save_file_with_memory(
        parent,
        context="mp4_output",
        title="Save MP4 Video",
        default_filename=default_filename,
        file_filter="MP4 Video (*.mp4)"
    )
