"""
User preferences management for Luma Tools.

Handles user-specific settings like window state, tab order, default passes,
version tracking, and workflow execution time tracking.
"""

import threading
from typing import Dict, Any, List, Optional
from .settings_manager import (
    get_setting, set_setting,
    load_user_settings, save_user_settings,
    _settings_cache_lock
)
from .config import DEFAULT_PASSES


# ============================================================================
# WINDOW STATE MANAGEMENT
# ============================================================================

def get_window_state() -> Dict[str, Any]:
    """Get the saved window state (size and maximized status)."""
    return {
        "width": get_setting("window_width"),
        "height": get_setting("window_height"),
        "maximized": get_setting("window_maximized")
    }


def save_window_state(width: int, height: int, maximized: bool):
    """Save the window state."""
    set_setting("window_width", width, verbose=False)
    set_setting("window_height", height, verbose=False)
    set_setting("window_maximized", maximized, verbose=False)


# ============================================================================
# TAB ORDER MANAGEMENT
# ============================================================================

def get_tab_order() -> List[str]:
    """Get the saved tab order."""
    return get_setting("tab_order")


def save_tab_order(tab_order: List[str]):
    """Save the tab order."""
    set_setting("tab_order", tab_order, verbose=False)


# ============================================================================
# DEFAULT PASSES MANAGEMENT
# ============================================================================

def get_default_passes() -> List[str]:
    """Get the user's configured default passes."""
    return load_user_settings().get("default_passes", DEFAULT_PASSES.copy())


def get_all_default_passes() -> List[str]:
    """Get all passes that should be selected by default (including required)."""
    from .config import REQUIRED_PASSES

    user_passes = get_default_passes()
    all_passes = REQUIRED_PASSES.copy()
    for pass_name in user_passes:
        if pass_name not in all_passes:
            all_passes.append(pass_name)
    return all_passes


def set_default_passes(passes_list: List[str]):
    """Set the user's default passes."""
    with _settings_cache_lock:
        settings = load_user_settings()
        settings["default_passes"] = passes_list
        save_user_settings(settings)


# ============================================================================
# VERSION TRACKING
# ============================================================================

def get_last_opened_version() -> str:
    """Get the last version that the user opened."""
    return get_setting("last_opened_version")


def set_last_opened_version(version: str):
    """Save the current version as the last opened version."""
    set_setting("last_opened_version", version, verbose=False)


def is_new_version(current_version: str) -> bool:
    """Check if the current version is newer than the last opened version."""
    last_version = get_last_opened_version()

    # If never opened before, it's a new version
    if last_version == "0.0.0":
        return True

    # Compare versions (simple string comparison works for x.y.z.w format)
    try:
        # Split versions into parts and compare
        current_parts = [int(p) for p in current_version.split('.')]
        last_parts = [int(p) for p in last_version.split('.')]

        # Pad to same length
        max_len = max(len(current_parts), len(last_parts))
        current_parts += [0] * (max_len - len(current_parts))
        last_parts += [0] * (max_len - len(last_parts))

        # Compare part by part
        for curr, last in zip(current_parts, last_parts):
            if curr > last:
                return True
            elif curr < last:
                return False

        # Versions are equal
        return False
    except (ValueError, AttributeError):
        # If version parsing fails, assume it's new
        return True


# ============================================================================
# WORKFLOW EXECUTION TIME TRACKING
# ============================================================================

def record_workflow_execution_time(workflow_preset: str, per_frame_seconds: float):
    """Record per-frame execution time for a workflow.

    Stores the last 10 execution times to calculate median estimates.
    """
    with _settings_cache_lock:
        settings = load_user_settings()
        times = settings.get("comfyui_workflow_times", {})
        if workflow_preset not in times:
            times[workflow_preset] = []
        times[workflow_preset].append(per_frame_seconds)
        times[workflow_preset] = times[workflow_preset][-10:]  # Keep last 10
        settings["comfyui_workflow_times"] = times
        save_user_settings(settings)


def get_workflow_estimated_time_per_frame(workflow_preset: str) -> Optional[float]:
    """Get median per-frame time for a workflow based on history.

    Returns None if no history is available.
    """
    settings = load_user_settings()
    times = settings.get("comfyui_workflow_times", {}).get(workflow_preset, [])
    if not times:
        return None
    sorted_times = sorted(times)
    mid = len(sorted_times) // 2
    return sorted_times[mid]


# ============================================================================
# LAST BROWSED DIRECTORIES
# ============================================================================

def get_last_browse_directory(context: str) -> str:
    """Get the last browsed directory for a specific context."""
    return load_user_settings().get("last_browse_directories", {}).get(context, "")


def set_last_browse_directory(context: str, directory: str):
    """Save the last browsed directory for a specific context."""
    if not directory:
        return
    with _settings_cache_lock:
        settings = load_user_settings()
        if "last_browse_directories" not in settings:
            settings["last_browse_directories"] = {}
        settings["last_browse_directories"][context] = directory
        save_user_settings(settings)


# ============================================================================
# COMFYUI RUNNING JOBS PERSISTENCE
# ============================================================================

def save_comfyui_running_jobs(job_state: Optional[Dict[str, Any]]):
    """Save running ComfyUI job state for recovery on restart.

    Args:
        job_state: Dictionary containing job state info, or None to clear
            Expected keys for iterate mode:
                - mode: "iterate"
                - job_id: str
                - network_output_dir: str
                - total_tasks: int
                - generation_count: int
                - start_time: float
            Expected keys for batch mode:
                - mode: "batch"
                - job_ids: List[str]
                - network_output_dir: str
                - total_tasks: Dict[str, int]
                - generation_count: int
                - start_time: float
    """
    with _settings_cache_lock:
        settings = load_user_settings()
        if job_state is None:
            # Clear running jobs
            settings.pop("comfyui_running_jobs", None)
        else:
            settings["comfyui_running_jobs"] = job_state
        save_user_settings(settings)


def get_comfyui_running_jobs() -> Optional[Dict[str, Any]]:
    """Get persisted ComfyUI running job state.

    Returns:
        Job state dictionary if jobs were running when app closed, None otherwise
    """
    settings = load_user_settings()
    return settings.get("comfyui_running_jobs")


# ============================================================================
# GALLERY SETTINGS PERSISTENCE
# ============================================================================

def get_gallery_settings() -> Dict[str, Any]:
    """Get persisted gallery settings.

    Returns:
        Dictionary with gallery settings:
            - show_inputs: bool (default False)
            - view_mode: str (default "stacked") - "stacked" or "grid"
            - collapsed_sections: List[str] (section IDs that are collapsed)
            - sort_mode: str (default "date_desc")
    """
    settings = load_user_settings()
    gallery = settings.get("gallery_settings", {})

    # Ensure gallery is a dict (handle corrupted settings)
    if not isinstance(gallery, dict):
        gallery = {}

    # Get values with type validation to handle corrupted settings
    show_inputs = gallery.get("show_inputs", False)
    if not isinstance(show_inputs, bool):
        show_inputs = False

    view_mode = gallery.get("view_mode", "stacked")
    if not isinstance(view_mode, str):
        view_mode = "stacked"
    # Migrate "sections" to "stacked" if user had it saved
    if view_mode == "sections":
        view_mode = "stacked"

    collapsed_sections = gallery.get("collapsed_sections", [])
    if not isinstance(collapsed_sections, list):
        collapsed_sections = []

    sort_mode = gallery.get("sort_mode", "date_desc")
    if not isinstance(sort_mode, str):
        sort_mode = "date_desc"

    return {
        "show_inputs": show_inputs,
        "view_mode": view_mode,
        "collapsed_sections": collapsed_sections,
        "sort_mode": sort_mode
    }


def save_gallery_settings(
    show_inputs: Optional[bool] = None,
    view_mode: Optional[str] = None,
    collapsed_sections: Optional[List[str]] = None,
    sort_mode: Optional[str] = None,
    type_filters: Optional[dict] = None
):
    """Save gallery settings.

    Only saves values that are not None, preserving existing values for others.

    Args:
        show_inputs: Whether to show input images
        view_mode: View mode - "stacked" or "grid"
        collapsed_sections: List of section IDs that are collapsed
        sort_mode: Sort mode - "date_desc", "date_asc", "name_asc", "name_desc", "workflow"
        type_filters: Dict of file type -> bool for filtering by type
    """
    with _settings_cache_lock:
        settings = load_user_settings()
        if "gallery_settings" not in settings:
            settings["gallery_settings"] = {}

        if show_inputs is not None:
            settings["gallery_settings"]["show_inputs"] = show_inputs
        if view_mode is not None:
            settings["gallery_settings"]["view_mode"] = view_mode
        if collapsed_sections is not None:
            settings["gallery_settings"]["collapsed_sections"] = collapsed_sections
        if sort_mode is not None:
            settings["gallery_settings"]["sort_mode"] = sort_mode
        if type_filters is not None:
            settings["gallery_settings"]["type_filters"] = type_filters

        save_user_settings(settings)
