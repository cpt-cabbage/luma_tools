"""
Settings manager for Luma Tools.

Handles saving and loading user preferences and global settings.
Uses a registry pattern to minimize boilerplate for simple settings.
"""

import os
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, Callable, List
from .config import (
    USER_SETTINGS_DIR,
    USER_SETTINGS_FILE,
    DEFAULT_PASSES,
    REQUIRED_PASSES,
    DEFAULT_GLOBAL_SETTINGS_PATH,
    GLOBAL_SETTINGS_FILENAME,
)

logger = logging.getLogger(__name__)

# ============================================================================
# SETTINGS REGISTRY
# Declarative definitions for all settings with defaults and validation
# ============================================================================

@dataclass
class SettingDef:
    """Definition for a single setting."""
    key: str
    default: Any = None
    scope: str = "global"  # "global" or "user"
    validator: Optional[Callable[[Any], Any]] = None

# Validators
def _validate_enum(value: Any, allowed: tuple, default: Any) -> Any:
    """Validate value is in allowed set, return default if not."""
    return value if value in allowed else default

def _validate_comfyui_mode(v):
    return _validate_enum(v, ("embedded", "portable", "standalone"), "embedded")

def _validate_timeout(v, min_val=60, max_val=86400):
    return max(min_val, min(max_val, int(v)))

def _validate_server_wait_timeout(v):
    return max(30, min(3600, int(v)))

def _validate_server_behavior(v):
    return _validate_enum(v, ("fail", "wait"), "fail")

def _validate_stacking_mode(v):
    return _validate_enum(v, ("job", "groups", "both", "grid"), "job")

# Registry of all simple settings (get/set only, no complex logic)
SETTINGS_REGISTRY: Dict[str, SettingDef] = {
    # ComfyUI Global Settings
    "comfyui_path": SettingDef(
        "comfyui_path",
        r"L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\ComfyUI_windows_portable\ComfyUI",
        "global"
    ),
    "comfyui_mode": SettingDef("comfyui_mode", "embedded", "global", _validate_comfyui_mode),
    "comfyui_python_path": SettingDef("comfyui_python_path", "", "global"),
    "comfyui_fast_mode": SettingDef("comfyui_fast_mode", False, "global"),
    "comfyui_fp16_accumulation": SettingDef("comfyui_fp16_accumulation", False, "global"),
    "comfyui_lowvram": SettingDef("comfyui_lowvram", False, "global"),
    "comfyui_highvram": SettingDef("comfyui_highvram", False, "global"),
    "comfyui_normalvram": SettingDef("comfyui_normalvram", False, "global"),
    "comfyui_disable_smart_memory": SettingDef("comfyui_disable_smart_memory", False, "global"),
    "comfyui_network_output_path": SettingDef("comfyui_network_output_path", "", "global"),
    "comfyui_timeout": SettingDef("comfyui_timeout", 3600, "global", _validate_timeout),
    "comfyui_server_not_found_behavior": SettingDef(
        "comfyui_server_not_found_behavior", "fail", "global", _validate_server_behavior
    ),
    "comfyui_server_wait_timeout": SettingDef(
        "comfyui_server_wait_timeout", 300, "global", _validate_server_wait_timeout
    ),
    # User Settings
    "comfyui_tab_state": SettingDef("comfyui_tab_state", {}, "user"),
    "tab_order": SettingDef("tab_order", [], "user"),
    "auto_extract_textures": SettingDef("auto_extract_textures", False, "user"),
    "generate_3d_thumbnails": SettingDef("generate_3d_thumbnails", True, "user"),
    "show_tray_notifications": SettingDef("show_tray_notifications", True, "user"),
    "show_verbose_logs": SettingDef("show_verbose_logs", False, "user"),
    "viewer_3d_zoom_distance": SettingDef("viewer_3d_zoom_distance", 3.5, "user"),
    "viewer_3d_shading_mode": SettingDef("viewer_3d_shading_mode", "textured", "user"),
    "viewer_3d_lighting_mode": SettingDef("viewer_3d_lighting_mode", "studio", "user"),
    "viewer_3d_hdri_name": SettingDef("viewer_3d_hdri_name", "", "user"),
    "viewer_3d_light_strength": SettingDef("viewer_3d_light_strength", 1.0, "user"),
    # Window state
    "window_width": SettingDef("window_width", 1250, "user"),
    "window_height": SettingDef("window_height", 1000, "user"),
    "window_maximized": SettingDef("window_maximized", False, "user"),
    # Version tracking
    "last_opened_version": SettingDef("last_opened_version", "0.0.0", "user"),
    # Feature requests tracking
    "feature_requests_last_read": SettingDef("feature_requests_last_read", "", "user"),
    # Gallery likes and groups
    "gallery_liked_items": SettingDef("gallery_liked_items", [], "user"),
    "gallery_groups": SettingDef("gallery_groups", {}, "user"),
    "gallery_item_groups": SettingDef("gallery_item_groups", {}, "user"),
    "gallery_multi_group_enabled": SettingDef("gallery_multi_group_enabled", True, "user"),
    "gallery_stacking_mode": SettingDef("gallery_stacking_mode", "both", "user", _validate_stacking_mode),
    "gallery_sidebar_collapsed": SettingDef("gallery_sidebar_collapsed", False, "user"),
    "gallery_splitter_sizes": SettingDef("gallery_splitter_sizes", [200, 800], "user"),
    "gallery_stack_colors": SettingDef("gallery_stack_colors", {}, "user"),
    "gallery_liked_color": SettingDef("gallery_liked_color", None, "user"),
    "gallery_likes_stack": SettingDef("gallery_likes_stack", False, "user"),
    "gallery_stacks_data": SettingDef("gallery_stacks_data", {}, "user"),
    "gallery_stacks_collapsed": SettingDef("gallery_stacks_collapsed", False, "user"),
    # UI display settings
    "show_statusbar_log": SettingDef("show_statusbar_log", False, "user"),
    # ComfyUI-Gallery integration settings
    "comfyui_completion_sound": SettingDef("comfyui_completion_sound", "none", "user"),  # none, subtle, system
    "comfyui_show_recent_outputs": SettingDef("comfyui_show_recent_outputs", True, "user"),
    "gallery_show_job_status": SettingDef("gallery_show_job_status", True, "user"),
    "gallery_show_quick_actions": SettingDef("gallery_show_quick_actions", True, "user"),
    # Global Settings (Settings tab is admin-only, not configurable via restricted_tabs)
    "restricted_tabs": SettingDef("restricted_tabs", ["comfyui", "gallery"], "global"),
}

# Default constants (for external reference)
DEFAULT_COMFYUI_TIMEOUT = 3600
DEFAULT_SERVER_NOT_FOUND_WAIT = 300
DEFAULT_RESTRICTED_TABS = ["comfyui", "gallery"]  # Settings is admin-only, not in restricted list

TAB_RESTRICTION_MAP = {
    "comfyui": "RestrictComfyUI",
    "gallery": "RestrictGallery",
    # Settings tab is admin-only, not configurable
    "passbuilder": "RestrictPassBuilder",
    "mp4maker": "RestrictMP4Maker",
    "republish": "RestrictRePublish",
    "shotcleaner": "RestrictShotCleaner"
}

# ============================================================================
# SETTINGS CACHE
# ============================================================================

_user_settings_cache: Optional[Dict[str, Any]] = None
_global_settings_cache: Optional[Dict[str, Any]] = None
_global_settings_path_cache: Optional[str] = None


def clear_settings_cache():
    """Clear all settings caches. Call after saving settings."""
    global _user_settings_cache, _global_settings_cache, _global_settings_path_cache
    _user_settings_cache = None
    _global_settings_cache = None
    _global_settings_path_cache = None


def ensure_settings_dir():
    """Ensure settings directory exists."""
    from .utils import ensure_directory
    if not os.path.exists(USER_SETTINGS_DIR):
        ensure_directory(USER_SETTINGS_DIR)
        logger.info(f"Created settings directory: {USER_SETTINGS_DIR}")


# ============================================================================
# CORE LOAD/SAVE FUNCTIONS
# ============================================================================

def load_user_settings() -> Dict[str, Any]:
    """Load user settings from file."""
    global _user_settings_cache
    if _user_settings_cache is not None:
        return _user_settings_cache.copy()

    default_settings = {"default_passes": DEFAULT_PASSES.copy()}

    if not os.path.exists(USER_SETTINGS_FILE):
        _user_settings_cache = default_settings
        return default_settings.copy()

    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            if "default_passes" not in settings:
                settings["default_passes"] = DEFAULT_PASSES.copy()
            _user_settings_cache = settings
            return settings.copy()
    except Exception as e:
        logger.error(f"Error loading user settings: {e}")
        _user_settings_cache = default_settings
        return default_settings.copy()


def save_user_settings(settings: Dict[str, Any]):
    """Save user settings to file using atomic write to prevent corruption."""
    from .utils import save_json
    global _user_settings_cache
    ensure_settings_dir()
    if save_json(USER_SETTINGS_FILE, settings):
        _user_settings_cache = settings.copy()
    else:
        logger.error("Failed to save user settings")


def get_global_settings_path() -> str:
    """Get the path to the global settings directory."""
    global _global_settings_path_cache
    if _global_settings_path_cache is not None:
        return _global_settings_path_cache

    settings = load_user_settings()
    path = settings.get("global_settings_path")
    if path and os.path.isdir(path):
        _global_settings_path_cache = path
        return path

    _global_settings_path_cache = DEFAULT_GLOBAL_SETTINGS_PATH
    return DEFAULT_GLOBAL_SETTINGS_PATH


def set_global_settings_path(path: str):
    """Set a custom global settings path."""
    global _global_settings_path_cache, _global_settings_cache
    settings = load_user_settings()
    settings["global_settings_path"] = path
    save_user_settings(settings)
    _global_settings_path_cache = None
    _global_settings_cache = None
    logger.info(f"Set global settings path to: {path}")


def _get_global_settings_file() -> str:
    """Get the full path to the global settings file."""
    return os.path.join(get_global_settings_path(), GLOBAL_SETTINGS_FILENAME)


def _ensure_global_settings_dir():
    """Ensure global settings directory exists."""
    from .utils import ensure_directory
    path = get_global_settings_path()
    if not os.path.exists(path):
        ensure_directory(path)
        logger.info(f"Created global settings directory: {path}")


def load_global_settings() -> Dict[str, Any]:
    """Load global settings from file."""
    global _global_settings_cache
    if _global_settings_cache is not None:
        return _global_settings_cache.copy()

    default_settings = {
        "comfyui_workflow_presets": {},
        "admin_users": ["christophe.leyder"],  # Admins: full access (all tabs including Settings)
        "sup_users": [],  # Supervisors: can see ComfyUI and Gallery tabs (not Settings)
    }
    settings_file = _get_global_settings_file()

    if not os.path.exists(settings_file):
        _global_settings_cache = default_settings
        return default_settings.copy()

    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
            _global_settings_cache = settings
            return settings.copy()
    except Exception as e:
        logger.error(f"Error loading global settings: {e}")
        _global_settings_cache = default_settings
        return default_settings.copy()


def save_global_settings(settings: Dict[str, Any]):
    """Save global settings to file using atomic write to prevent corruption."""
    from .utils import save_json
    global _global_settings_cache
    _ensure_global_settings_dir()
    settings_file = _get_global_settings_file()
    if save_json(settings_file, settings):
        _global_settings_cache = settings.copy()
    else:
        logger.error("Failed to save global settings")


# ============================================================================
# UNIFIED SETTINGS ACCESSOR
# Generic get/set for registry-defined settings
# ============================================================================

class SettingsAccessor:
    """Unified accessor for getting/setting individual settings values."""

    def __init__(self, settings_type: str):
        self.settings_type = settings_type
        self._load_fn = load_global_settings if settings_type == 'global' else load_user_settings
        self._save_fn = save_global_settings if settings_type == 'global' else save_user_settings

    def get(self, key: str, default: Any = None) -> Any:
        """Get a settings value by key."""
        return self._load_fn().get(key, default)

    def set(self, key: str, value: Any, verbose: bool = True):
        """Set a settings value by key."""
        settings = self._load_fn()
        settings[key] = value
        self._save_fn(settings)
        if verbose:
            logger.info(f"Set {key} to: {value}")


_global_settings = SettingsAccessor('global')
_user_settings = SettingsAccessor('user')


_SENTINEL = object()


def get_setting(name: str, default: Any = _SENTINEL) -> Any:
    """Get any registered setting by name.

    Args:
        name: Setting key (must be in SETTINGS_REGISTRY unless default is provided)
        default: Fallback value for unregistered keys (suppresses KeyError)

    Raises:
        KeyError: If name is not in SETTINGS_REGISTRY and no default provided
    """
    defn = SETTINGS_REGISTRY.get(name)
    if not defn:
        if default is not _SENTINEL:
            return default
        raise KeyError(f"Unknown setting: {name}")
    accessor = _global_settings if defn.scope == "global" else _user_settings
    return accessor.get(defn.key, defn.default)


def set_setting(name: str, value: Any, verbose: bool = True):
    """Set any registered setting by name."""
    defn = SETTINGS_REGISTRY.get(name)
    if not defn:
        raise KeyError(f"Unknown setting: {name}")
    if defn.validator:
        value = defn.validator(value)
    accessor = _global_settings if defn.scope == "global" else _user_settings
    accessor.set(defn.key, value, verbose=verbose)


def safe_get_setting(name: str, default: Any = None) -> Any:
    """
    Get a setting with a guaranteed default if not found.

    Unlike get_setting(), this never raises KeyError. Use when reading
    settings that may not exist in older configurations or are optional.

    Args:
        name: Setting key (may or may not be in SETTINGS_REGISTRY)
        default: Fallback value if setting not found (default: None)

    Returns:
        Setting value or default

    Example:
        # These are equivalent:
        try:
            value = get_setting("my_setting")
        except KeyError:
            value = False

        value = safe_get_setting("my_setting", False)
    """
    defn = SETTINGS_REGISTRY.get(name)
    if not defn:
        return default
    accessor = _global_settings if defn.scope == "global" else _user_settings
    return accessor.get(defn.key, defn.default if default is None else default)


def safe_set_setting(name: str, value: Any, verbose: bool = False) -> bool:
    """
    Set a setting without raising errors.

    Unlike set_setting(), this catches exceptions and returns success status.
    The verbose parameter defaults to False for cleaner logs.

    Args:
        name: Setting key
        value: Value to set
        verbose: Whether to log the change (default: False)

    Returns:
        True if setting was saved successfully, False otherwise
    """
    try:
        set_setting(name, value, verbose=verbose)
        return True
    except (KeyError, Exception) as e:
        logger.warning(f"Could not save setting {name}: {e}")
        return False


# ============================================================================
# HDRI LIST MANAGEMENT
# ============================================================================

def get_hdri_list() -> List[Dict[str, str]]:
    """Get list of available HDRIs from global settings.

    Returns:
        List of dicts with keys: name, path
    """
    return load_global_settings().get("hdri_list", [])


def add_hdri_to_list(name: str, path: str):
    """Add an HDRI to the global list."""
    settings = load_global_settings()
    hdri_list = settings.get("hdri_list", [])
    # Check for duplicates
    for hdri in hdri_list:
        if hdri.get("name") == name:
            return  # Already exists
    hdri_list.append({"name": name, "path": path})
    settings["hdri_list"] = hdri_list
    save_global_settings(settings)
    logger.info(f"Added HDRI to global settings: {name}")


def remove_hdri_from_list(name: str):
    """Remove an HDRI from the global list."""
    settings = load_global_settings()
    hdri_list = settings.get("hdri_list", [])
    settings["hdri_list"] = [h for h in hdri_list if h.get("name") != name]
    save_global_settings(settings)
    logger.info(f"Removed HDRI from global settings: {name}")


# ============================================================================
# TAB RESTRICTIONS
# ============================================================================

def is_tab_restricted(tab_name: str) -> bool:
    """Check if a specific tab is restricted to admin users."""
    return tab_name in get_setting("restricted_tabs")


# ============================================================================
# USER ROLE MANAGEMENT (Global)
# Admins: Full access (all tabs including Settings)
# Supervisors (Sups): Can see ComfyUI and Gallery tabs (not Settings)
# ============================================================================

# Role-based settings keys mapping
_ROLE_SETTINGS_KEYS = {
    "admin": "admin_users",
    "sup": "sup_users",
}


def _get_role_settings_key(role: str) -> str:
    """Get the settings key for a role."""
    if role not in _ROLE_SETTINGS_KEYS:
        raise ValueError(f"Unknown role: {role}. Valid roles: {list(_ROLE_SETTINGS_KEYS.keys())}")
    return _ROLE_SETTINGS_KEYS[role]


def get_users_with_role(role: str) -> List[str]:
    """Get the list of users with a specific role.

    Args:
        role: Role name ("admin" or "sup")

    Returns:
        List of usernames with the role
    """
    return _global_settings.get(_get_role_settings_key(role), [])


def is_user_in_role(username: str, role: str) -> bool:
    """Check if a username has a specific role (case-insensitive).

    Args:
        username: Username to check
        role: Role name ("admin" or "sup")

    Returns:
        True if user has the role
    """
    if not username:
        return False
    return username.lower() in [u.lower() for u in get_users_with_role(role)]


def add_user_to_role(username: str, role: str):
    """Add a user to a role.

    Args:
        username: Username to add
        role: Role name ("admin" or "sup")
    """
    if not username:
        return
    settings_key = _get_role_settings_key(role)
    settings = load_global_settings()
    if settings_key not in settings:
        settings[settings_key] = []
    existing_lower = [u.lower() for u in settings[settings_key]]
    if username.lower() not in existing_lower:
        settings[settings_key].append(username)
        save_global_settings(settings)
        logger.info(f"Added {role} user: {username}")


def remove_user_from_role(username: str, role: str):
    """Remove a user from a role.

    Args:
        username: Username to remove
        role: Role name ("admin" or "sup")
    """
    settings_key = _get_role_settings_key(role)
    settings = load_global_settings()
    if settings_key not in settings:
        return
    original_list = settings[settings_key]
    settings[settings_key] = [u for u in original_list if u.lower() != username.lower()]
    if len(settings[settings_key]) < len(original_list):
        save_global_settings(settings)
        logger.info(f"Removed {role} user: {username}")


def has_elevated_access(username: str) -> bool:
    """Check if a username has any elevated access (admin or sup)."""
    return is_user_in_role(username, "admin") or is_user_in_role(username, "sup")
