"""
Settings manager for Luma Tools.

Handles saving and loading user preferences and global settings.
Uses a registry pattern to minimize boilerplate for simple settings.
"""

import os
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union, Callable, List
from .config import (
    USER_SETTINGS_DIR,
    USER_SETTINGS_FILE,
    DEFAULT_PASSES,
    REQUIRED_PASSES,
    DEFAULT_GLOBAL_SETTINGS_PATH,
    GLOBAL_SETTINGS_FILENAME,
)

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
def _validate_comfyui_mode(v):
    return v if v in ("embedded", "portable", "standalone") else "embedded"

def _validate_timeout(v, min_val=60, max_val=86400):
    return max(min_val, min(max_val, int(v)))

def _validate_server_wait_timeout(v):
    return max(30, min(3600, int(v)))

def _validate_server_behavior(v):
    return v if v in ("fail", "wait") else "fail"

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
    "viewer_3d_zoom_distance": SettingDef("viewer_3d_zoom_distance", 3.5, "user"),
    # Window state
    "window_width": SettingDef("window_width", 1250, "user"),
    "window_height": SettingDef("window_height", 1000, "user"),
    "window_maximized": SettingDef("window_maximized", False, "user"),
    # Version tracking
    "last_opened_version": SettingDef("last_opened_version", "0.0.0", "user"),
    # Feature requests tracking
    "feature_requests_last_read": SettingDef("feature_requests_last_read", "", "user"),
    # Global Settings (Settings tab is admin-only, not configurable via restricted_tabs)
    "restricted_tabs": SettingDef("restricted_tabs", ["comfyui", "comfyui_gallery"], "global"),
}

# Default constants (for external reference)
DEFAULT_COMFYUI_TIMEOUT = 3600
DEFAULT_SERVER_NOT_FOUND_WAIT = 300
DEFAULT_RESTRICTED_TABS = ["comfyui", "comfyui_gallery"]  # Settings is admin-only, not in restricted list

TAB_RESTRICTION_MAP = {
    "comfyui": "RestrictComfyUI",
    "comfyui_gallery": "RestrictComfyUIGallery",
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
    if not os.path.exists(USER_SETTINGS_DIR):
        os.makedirs(USER_SETTINGS_DIR)
        print(f"Created settings directory: {USER_SETTINGS_DIR}")


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
        print(f"Error loading user settings: {e}")
        _user_settings_cache = default_settings
        return default_settings.copy()


def save_user_settings(settings: Dict[str, Any]):
    """Save user settings to file."""
    global _user_settings_cache
    ensure_settings_dir()
    try:
        with open(USER_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        _user_settings_cache = settings.copy()
    except Exception as e:
        print(f"Error saving user settings: {e}")


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
    print(f"Set global settings path to: {path}")


def _get_global_settings_file() -> str:
    """Get the full path to the global settings file."""
    return os.path.join(get_global_settings_path(), GLOBAL_SETTINGS_FILENAME)


def _ensure_global_settings_dir():
    """Ensure global settings directory exists."""
    path = get_global_settings_path()
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Created global settings directory: {path}")


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
        print(f"Error loading global settings: {e}")
        _global_settings_cache = default_settings
        return default_settings.copy()


def save_global_settings(settings: Dict[str, Any]):
    """Save global settings to file."""
    global _global_settings_cache
    _ensure_global_settings_dir()
    settings_file = _get_global_settings_file()
    try:
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)
        _global_settings_cache = settings.copy()
    except Exception as e:
        print(f"Error saving global settings: {e}")


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
            print(f"Set {key} to: {value}")


_global_settings = SettingsAccessor('global')
_user_settings = SettingsAccessor('user')


def get_setting(name: str) -> Any:
    """Get any registered setting by name."""
    defn = SETTINGS_REGISTRY.get(name)
    if not defn:
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


# ============================================================================
# BACKWARDS-COMPATIBLE FUNCTION ALIASES
# These wrap the registry for existing code that uses get_*/set_* functions
# ============================================================================

# ComfyUI settings
get_comfyui_path = lambda: get_setting("comfyui_path")
set_comfyui_path = lambda v: set_setting("comfyui_path", v)
get_comfyui_mode = lambda: get_setting("comfyui_mode")
set_comfyui_mode = lambda v: set_setting("comfyui_mode", v)
get_comfyui_python_path = lambda: get_setting("comfyui_python_path")
set_comfyui_python_path = lambda v: set_setting("comfyui_python_path", v)
get_comfyui_fast_mode = lambda: get_setting("comfyui_fast_mode")
set_comfyui_fast_mode = lambda v: set_setting("comfyui_fast_mode", v)
get_comfyui_fp16_accumulation = lambda: get_setting("comfyui_fp16_accumulation")
set_comfyui_fp16_accumulation = lambda v: set_setting("comfyui_fp16_accumulation", v)
get_comfyui_network_output_path = lambda: get_setting("comfyui_network_output_path")
set_comfyui_network_output_path = lambda v: set_setting("comfyui_network_output_path", v)
get_comfyui_timeout = lambda: get_setting("comfyui_timeout")
set_comfyui_timeout = lambda v: set_setting("comfyui_timeout", v)
get_comfyui_server_not_found_behavior = lambda: get_setting("comfyui_server_not_found_behavior")
set_comfyui_server_not_found_behavior = lambda v: set_setting("comfyui_server_not_found_behavior", v)
get_comfyui_server_wait_timeout = lambda: get_setting("comfyui_server_wait_timeout")
set_comfyui_server_wait_timeout = lambda v: set_setting("comfyui_server_wait_timeout", v)

# Tab and UI state
get_comfyui_tab_state = lambda: get_setting("comfyui_tab_state")
save_comfyui_tab_state = lambda v: set_setting("comfyui_tab_state", v, verbose=False)
get_tab_order = lambda: get_setting("tab_order")
save_tab_order = lambda v: set_setting("tab_order", v, verbose=False)
get_restricted_tabs = lambda: get_setting("restricted_tabs")
set_restricted_tabs = lambda v: (set_setting("restricted_tabs", v, verbose=False), print(f"Updated restricted tabs: {v}"))[0]

# Model export settings
get_auto_extract_textures = lambda: get_setting("auto_extract_textures")
set_auto_extract_textures = lambda v: set_setting("auto_extract_textures", v)
get_generate_3d_thumbnails = lambda: get_setting("generate_3d_thumbnails")
set_generate_3d_thumbnails = lambda v: set_setting("generate_3d_thumbnails", v)


def is_tab_restricted(tab_name: str) -> bool:
    """Check if a specific tab is restricted to admin users."""
    return tab_name in get_restricted_tabs()


# ============================================================================
# DEFAULT PASSES MANAGEMENT
# ============================================================================

def get_default_passes() -> List[str]:
    """Get the user's configured default passes."""
    return load_user_settings().get("default_passes", DEFAULT_PASSES.copy())


def get_all_default_passes() -> List[str]:
    """Get all passes that should be selected by default (including required)."""
    user_passes = get_default_passes()
    all_passes = REQUIRED_PASSES.copy()
    for pass_name in user_passes:
        if pass_name not in all_passes:
            all_passes.append(pass_name)
    return all_passes


def set_default_passes(passes_list: List[str]):
    """Set the user's default passes."""
    _user_settings.set("default_passes", passes_list, verbose=False)


# ============================================================================
# COMFYUI TEXT PRESETS (User Settings)
# ============================================================================

def get_comfyui_text_presets() -> Dict[str, str]:
    """Get saved ComfyUI text presets."""
    settings = load_user_settings()
    presets = settings.get("comfyui_text_presets", {})
    legacy_presets = settings.get("prompt_presets", {})
    return {**presets, **legacy_presets}


def save_comfyui_text_preset(name: str, text: str):
    """Save a ComfyUI text preset."""
    settings = load_user_settings()
    if "comfyui_text_presets" not in settings:
        settings["comfyui_text_presets"] = {}
    settings["comfyui_text_presets"][name] = text
    save_user_settings(settings)
    print(f"Saved ComfyUI text preset: {name}")


def delete_comfyui_text_preset(name: str):
    """Delete a ComfyUI text preset."""
    settings = load_user_settings()
    deleted = False
    if "comfyui_text_presets" in settings and name in settings["comfyui_text_presets"]:
        del settings["comfyui_text_presets"][name]
        deleted = True
    if "prompt_presets" in settings and name in settings["prompt_presets"]:
        del settings["prompt_presets"][name]
        deleted = True
    if deleted:
        save_user_settings(settings)
        print(f"Deleted ComfyUI text preset: {name}")


# ============================================================================
# COMFYUI PROMPT PRESETS BY NODE TYPE (User Settings)
# ============================================================================

def get_comfyui_prompt_presets_for_node_type(node_type: str) -> Dict[str, str]:
    """Get prompt presets for a specific node type."""
    settings = load_user_settings()
    return settings.get("comfyui_prompt_presets_by_node_type", {}).get(node_type, {})


def save_comfyui_prompt_preset_for_node_type(node_type: str, preset_name: str, text: str):
    """Save a prompt preset for a specific node type."""
    settings = load_user_settings()
    if "comfyui_prompt_presets_by_node_type" not in settings:
        settings["comfyui_prompt_presets_by_node_type"] = {}
    if node_type not in settings["comfyui_prompt_presets_by_node_type"]:
        settings["comfyui_prompt_presets_by_node_type"][node_type] = {}
    settings["comfyui_prompt_presets_by_node_type"][node_type][preset_name] = text
    save_user_settings(settings)
    print(f"Saved prompt preset '{preset_name}' for node type '{node_type}'")


def delete_comfyui_prompt_preset_for_node_type(node_type: str, preset_name: str):
    """Delete a prompt preset for a specific node type."""
    settings = load_user_settings()
    all_presets = settings.get("comfyui_prompt_presets_by_node_type", {})
    if node_type in all_presets and preset_name in all_presets[node_type]:
        del all_presets[node_type][preset_name]
        if not all_presets[node_type]:
            del all_presets[node_type]
        settings["comfyui_prompt_presets_by_node_type"] = all_presets
        save_user_settings(settings)
        print(f"Deleted prompt preset '{preset_name}' from node type '{node_type}'")


def get_all_comfyui_prompt_presets_by_node_type() -> Dict[str, Dict[str, str]]:
    """Get all prompt presets for all node types."""
    return load_user_settings().get("comfyui_prompt_presets_by_node_type", {})


# ============================================================================
# COMFYUI WORKFLOW PRESETS (Global Settings)
# ============================================================================

def get_comfyui_workflow_presets() -> Dict[str, Any]:
    """Get saved ComfyUI workflow presets from global settings."""
    return load_global_settings().get("comfyui_workflow_presets", {})


def save_comfyui_workflow_preset(
    name: str,
    workflow_path: str,
    description: str = "",
    iteratable: bool = False,
    note: str = "",
    full_restart: bool = False,
    node_overrides: Optional[Dict] = None,
    is_multi: bool = False,
    workflows: Optional[Dict] = None
):
    """Save a ComfyUI workflow preset to global settings."""
    settings = load_global_settings()
    if "comfyui_workflow_presets" not in settings:
        settings["comfyui_workflow_presets"] = {}

    preset_data = {
        "path": workflow_path,
        "description": description,
        "iteratable": iteratable,
        "note": note,
        "full_restart": full_restart,
        "node_overrides": node_overrides or {},
        "is_multi": is_multi,
    }
    if is_multi and workflows:
        preset_data["workflows"] = workflows

    settings["comfyui_workflow_presets"][name] = preset_data
    save_global_settings(settings)
    if is_multi:
        print(f"Saved ComfyUI multi-workflow preset: {name} with {len(workflows or {})} workflow(s)")
    else:
        print(f"Saved ComfyUI workflow preset: {name} -> {workflow_path}")


def update_comfyui_workflow_preset(name: str, **kwargs) -> bool:
    """Update an existing ComfyUI workflow preset."""
    settings = load_global_settings()
    presets = settings.get("comfyui_workflow_presets", {})
    if name not in presets:
        return False

    preset = presets[name]
    # Handle legacy format
    if isinstance(preset, str):
        preset = {"path": preset, "description": "", "iteratable": False, "note": "",
                  "full_restart": False, "node_overrides": {}, "is_multi": False}

    # Update only provided fields
    for key in ["workflow_path", "description", "iteratable", "note", "full_restart",
                "node_overrides", "is_multi", "workflows"]:
        if key in kwargs and kwargs[key] is not None:
            preset_key = "path" if key == "workflow_path" else key
            preset[preset_key] = kwargs[key]

    presets[name] = preset
    settings["comfyui_workflow_presets"] = presets
    save_global_settings(settings)
    print(f"Updated ComfyUI workflow preset: {name}")
    return True


def delete_comfyui_workflow_preset(name: str):
    """Delete a ComfyUI workflow preset from global settings."""
    settings = load_global_settings()
    if "comfyui_workflow_presets" in settings and name in settings["comfyui_workflow_presets"]:
        del settings["comfyui_workflow_presets"][name]
        save_global_settings(settings)
        print(f"Deleted ComfyUI workflow preset: {name}")


def get_comfyui_workflow_preset_path(name: str, selected_workflow: Optional[str] = None) -> Optional[str]:
    """Get the workflow path for a specific preset."""
    presets = get_comfyui_workflow_presets()
    if name not in presets:
        return None

    preset = presets[name]
    if isinstance(preset, dict):
        if preset.get("is_multi") and selected_workflow:
            workflows = preset.get("workflows", {})
            if selected_workflow in workflows:
                return workflows[selected_workflow].get("path")
        return preset.get("path")
    return preset  # Legacy format


def is_workflow_preset_iteratable(name: str) -> bool:
    """Check if a workflow preset supports iterate mode."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("iteratable", False)
    return False


def is_workflow_preset_full_restart(name: str) -> bool:
    """Check if a workflow preset requires full ComfyUI server restart."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("full_restart", False)
    return False


def is_workflow_preset_multi(name: str) -> bool:
    """Check if a workflow preset is a multi-workflow model."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("is_multi", False)
    return False


def get_workflow_preset_workflows(name: str) -> Dict[str, Any]:
    """Get the workflows dictionary for a multi-workflow preset."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict) and preset.get("is_multi"):
            return preset.get("workflows", {})
    return {}


def get_workflow_preset_note(name: str, selected_workflow: Optional[str] = None) -> str:
    """Get the note for a workflow preset."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("note", "")
    return ""


def get_workflow_config(name: str, selected_workflow: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get the complete workflow configuration for a preset."""
    presets = get_comfyui_workflow_presets()
    if name not in presets:
        return None

    preset = presets[name]
    if isinstance(preset, str):
        return {"path": preset, "iteratable": False, "full_restart": False, "note": "", "node_overrides": {}}

    if preset.get("is_multi") and selected_workflow:
        workflows = preset.get("workflows", {})
        if selected_workflow in workflows:
            wf = workflows[selected_workflow]
            return {
                "path": wf.get("path", ""),
                "iteratable": wf.get("iteratable", False),
                "full_restart": wf.get("full_restart", False),
                "note": wf.get("note", ""),
                "node_overrides": wf.get("node_overrides", {}),
            }

    return {
        "path": preset.get("path", ""),
        "iteratable": preset.get("iteratable", False),
        "full_restart": preset.get("full_restart", False),
        "note": preset.get("note", ""),
        "node_overrides": preset.get("node_overrides", {}),
    }


# ============================================================================
# USER ROLE MANAGEMENT (Global)
# Admins: Full access (all tabs including Settings)
# Supervisors (Sups): Can see ComfyUI and Gallery tabs (not Settings)
# ============================================================================

def get_admin_users() -> List[str]:
    """Get the list of admin users from global settings."""
    return _global_settings.get("admin_users", [])


def get_sup_users() -> List[str]:
    """Get the list of supervisor users from global settings."""
    return _global_settings.get("sup_users", [])


def is_admin_user(username: str) -> bool:
    """Check if a username is in the admin list (case-insensitive)."""
    if not username:
        return False
    return username.lower() in [u.lower() for u in get_admin_users()]


def is_sup_user(username: str) -> bool:
    """Check if a username is in the supervisor list (case-insensitive)."""
    if not username:
        return False
    return username.lower() in [u.lower() for u in get_sup_users()]


def has_elevated_access(username: str) -> bool:
    """Check if a username has any elevated access (admin or sup)."""
    return is_admin_user(username) or is_sup_user(username)


def add_admin_user(username: str):
    """Add a user to the admin list."""
    if not username:
        return
    settings = load_global_settings()
    if "admin_users" not in settings:
        settings["admin_users"] = []
    existing_lower = [u.lower() for u in settings["admin_users"]]
    if username.lower() not in existing_lower:
        settings["admin_users"].append(username)
        save_global_settings(settings)
        print(f"Added admin user: {username}")


def remove_admin_user(username: str):
    """Remove a user from the admin list."""
    settings = load_global_settings()
    if "admin_users" not in settings:
        return
    original_list = settings["admin_users"]
    settings["admin_users"] = [u for u in original_list if u.lower() != username.lower()]
    if len(settings["admin_users"]) < len(original_list):
        save_global_settings(settings)
        print(f"Removed admin user: {username}")


def add_sup_user(username: str):
    """Add a user to the supervisor list."""
    if not username:
        return
    settings = load_global_settings()
    if "sup_users" not in settings:
        settings["sup_users"] = []
    existing_lower = [u.lower() for u in settings["sup_users"]]
    if username.lower() not in existing_lower:
        settings["sup_users"].append(username)
        save_global_settings(settings)
        print(f"Added supervisor user: {username}")


def remove_sup_user(username: str):
    """Remove a user from the supervisor list."""
    settings = load_global_settings()
    if "sup_users" not in settings:
        return
    original_list = settings["sup_users"]
    settings["sup_users"] = [u for u in original_list if u.lower() != username.lower()]
    if len(settings["sup_users"]) < len(original_list):
        save_global_settings(settings)
        print(f"Removed supervisor user: {username}")


# ============================================================================
# LAST BROWSED DIRECTORIES (User Settings)
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


# ============================================================================
# WINDOW STATE MANAGEMENT (User Settings)
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
# VERSION TRACKING (User Settings)
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
# FEATURE REQUESTS (Global Settings)
# ============================================================================

def get_feature_requests_base_dir() -> str:
    """Get base path for feature requests (ComfyUI network output path)."""
    network_path = get_setting("comfyui_network_output_path")
    if not network_path:
        # Fallback to global settings if network path not configured
        return os.path.join(get_global_settings_path(), "feature_requests")
    return os.path.join(network_path, ".feature_requests")


def get_user_feature_requests_file(username: str) -> str:
    """Get path to user's feature requests file.

    Each user has their own requests file in the ComfyUI network output folder.
    Files are stored in a hidden .feature_requests directory to avoid showing in gallery.

    Args:
        username: Username

    Returns:
        Full path to user's requests file
    """
    base_dir = get_feature_requests_base_dir()
    return os.path.join(base_dir, f"{username}_requests.json")


def append_feature_request(category: str, description: str, username: str) -> bool:
    """Add a feature request to the user's requests file.

    Each user has their own JSON file containing an array of requests.

    Args:
        category: Feature, Bug, Enhancement, or Question
        description: Detailed description of the request
        username: Username of the requester

    Returns:
        True on success, False on failure
    """
    from datetime import datetime

    try:
        file_path = get_user_feature_requests_file(username)

        # Ensure the directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Format timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Create new request
        new_request = {
            'timestamp': timestamp,
            'username': username,
            'category': category,
            'description': description
        }

        # Read existing requests
        requests = []
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    requests = json.load(f)
            except Exception as e:
                print(f"Error reading existing requests: {e}")
                requests = []

        # Append new request
        requests.append(new_request)

        # Write back to file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(requests, f, indent=2, ensure_ascii=False)

        print(f"Feature request created: {category} by {username}")
        return True

    except Exception as e:
        print(f"Error creating feature request: {e}")
        return False


def get_feature_requests() -> List[Dict[str, str]]:
    """Read and parse all feature requests from all user files.

    Returns:
        List of dicts with keys: timestamp, username, category, description
        Sorted by timestamp (oldest first)
    """
    try:
        base_dir = get_feature_requests_base_dir()

        # Check if directory exists
        if not os.path.exists(base_dir):
            return []

        # Read all user request files
        all_requests = []
        for filename in os.listdir(base_dir):
            if not filename.endswith('_requests.json'):
                continue

            file_path = os.path.join(base_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    user_requests = json.load(f)
                    if isinstance(user_requests, list):
                        all_requests.extend(user_requests)
            except Exception as e:
                print(f"Error reading feature request file {filename}: {e}")
                continue

        # Sort by timestamp
        all_requests.sort(key=lambda x: x.get('timestamp', ''))

        return all_requests

    except Exception as e:
        print(f"Error reading feature requests: {e}")
        return []


def get_unread_feature_request_count(username: str) -> int:
    """Get count of unread feature requests for admin users.

    Uses user settings to track last read timestamp.

    Args:
        username: Admin username

    Returns:
        Count of unread requests
    """
    from datetime import datetime

    try:
        # Get user's last read timestamp
        settings = load_user_settings()
        last_read_str = settings.get("feature_requests_last_read", "")

        # Parse timestamp
        if last_read_str:
            try:
                last_read = datetime.strptime(last_read_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                last_read = None
        else:
            last_read = None

        # Get all requests
        requests = get_feature_requests()

        # Count requests newer than last read
        if last_read is None:
            # Never read before, all are unread
            return len(requests)

        unread_count = 0
        for req in requests:
            try:
                req_time = datetime.strptime(req['timestamp'], "%Y-%m-%d %H:%M:%S")
                if req_time > last_read:
                    unread_count += 1
            except ValueError:
                # If can't parse, assume unread
                unread_count += 1

        return unread_count

    except Exception as e:
        print(f"Error counting unread feature requests: {e}")
        return 0


def mark_feature_requests_as_read(username: str):
    """Mark all current feature requests as read for this admin user.

    Saves current timestamp to user settings.

    Args:
        username: Admin username
    """
    from datetime import datetime

    try:
        # Save current timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        set_setting("feature_requests_last_read", timestamp, verbose=False)
        print(f"Marked feature requests as read for {username} at {timestamp}")

    except Exception as e:
        print(f"Error marking feature requests as read: {e}")
