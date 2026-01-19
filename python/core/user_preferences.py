"""
User preferences management for Luma Tools.

Handles user-specific settings like window state, tab order, default passes,
version tracking, and workflow execution time tracking.
"""

from typing import Dict, Any, List, Optional
from .settings_manager import (
    get_setting, set_setting,
    load_user_settings, save_user_settings
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
    settings = load_user_settings()
    if "last_browse_directories" not in settings:
        settings["last_browse_directories"] = {}
    settings["last_browse_directories"][context] = directory
    save_user_settings(settings)
