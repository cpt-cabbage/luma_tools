"""
Settings manager for Luma Tools.

Handles saving and loading user preferences and global settings.
"""

import os
import json
from typing import Optional, Dict, Any, Union
from config import (
    USER_SETTINGS_DIR,
    USER_SETTINGS_FILE,
    DEFAULT_PASSES,
    REQUIRED_PASSES,
    DEFAULT_GLOBAL_SETTINGS_PATH,
    GLOBAL_SETTINGS_FILENAME,
)

# ============================================================================
# SETTINGS CACHE
# Caches settings to avoid repeated disk/network I/O during startup
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


def load_user_settings():
    """
    Load user settings from file.

    Returns:
        dict: User settings dictionary with default values if file doesn't exist
    """
    global _user_settings_cache

    # Return cached settings if available
    if _user_settings_cache is not None:
        return _user_settings_cache.copy()

    default_settings = {
        "default_passes": DEFAULT_PASSES.copy()
    }

    if not os.path.exists(USER_SETTINGS_FILE):
        print("No user settings file found, using defaults")
        _user_settings_cache = default_settings
        return default_settings.copy()

    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            settings = json.load(f)

            # Ensure default_passes key exists
            if "default_passes" not in settings:
                settings["default_passes"] = DEFAULT_PASSES.copy()

            _user_settings_cache = settings
            return settings.copy()
    except Exception as e:
        print(f"Error loading user settings: {e}")
        _user_settings_cache = default_settings
        return default_settings.copy()


def save_user_settings(settings):
    """
    Save user settings to file.

    Args:
        settings: Dictionary containing user settings
    """
    global _user_settings_cache
    ensure_settings_dir()

    try:
        with open(USER_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        # Update cache with new settings
        _user_settings_cache = settings.copy()
    except Exception as e:
        print(f"Error saving user settings: {e}")


# ============================================================================
# GLOBAL SETTINGS
# ============================================================================

def get_global_settings_path():
    """
    Get the path to the global settings directory.

    Returns:
        str: Path to global settings directory (user override or default)
    """
    global _global_settings_path_cache

    # Return cached path if available (avoids slow os.path.isdir on network)
    if _global_settings_path_cache is not None:
        return _global_settings_path_cache

    settings = load_user_settings()
    path = settings.get("global_settings_path")
    if path and os.path.isdir(path):
        _global_settings_path_cache = path
        return path

    _global_settings_path_cache = DEFAULT_GLOBAL_SETTINGS_PATH
    return DEFAULT_GLOBAL_SETTINGS_PATH


def set_global_settings_path(path):
    """
    Set a custom global settings path.

    Args:
        path: Path to global settings directory
    """
    global _global_settings_path_cache, _global_settings_cache
    settings = load_user_settings()
    settings["global_settings_path"] = path
    save_user_settings(settings)
    # Clear caches since path changed
    _global_settings_path_cache = None
    _global_settings_cache = None
    print(f"Set global settings path to: {path}")


def _get_global_settings_file():
    """Get the full path to the global settings file."""
    return os.path.join(get_global_settings_path(), GLOBAL_SETTINGS_FILENAME)


def _ensure_global_settings_dir():
    """Ensure global settings directory exists."""
    path = get_global_settings_path()
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Created global settings directory: {path}")


def load_global_settings():
    """
    Load global settings from file.

    Returns:
        dict: Global settings dictionary
    """
    global _global_settings_cache

    # Return cached settings if available
    if _global_settings_cache is not None:
        return _global_settings_cache.copy()

    default_settings = {
        "comfyui_workflow_presets": {},
        "admin_users": ["christophe.leyder"]  # Default admin user
    }

    settings_file = _get_global_settings_file()
    if not os.path.exists(settings_file):
        print(f"No global settings file found at {settings_file}, using defaults")
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


def save_global_settings(settings):
    """
    Save global settings to file.

    Args:
        settings: Dictionary containing global settings
    """
    global _global_settings_cache
    _ensure_global_settings_dir()

    settings_file = _get_global_settings_file()
    try:
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)
            print(f"Saved global settings to: {settings_file}")
        # Update cache with new settings
        _global_settings_cache = settings.copy()
    except Exception as e:
        print(f"Error saving global settings: {e}")


# ============================================================================
# UNIFIED SETTINGS ACCESSOR
# Eliminates getter/setter boilerplate via a single accessor class
# ============================================================================

class SettingsAccessor:
    """Unified accessor for getting/setting individual settings values."""

    def __init__(self, settings_type: str):
        """
        Initialize settings accessor.

        Args:
            settings_type: Either 'global' or 'user'
        """
        self.settings_type = settings_type
        self._load_fn = load_global_settings if settings_type == 'global' else load_user_settings
        self._save_fn = save_global_settings if settings_type == 'global' else save_user_settings

    def get(self, key: str, default: Any = None) -> Any:
        """Get a settings value by key."""
        settings = self._load_fn()
        return settings.get(key, default)

    def set(self, key: str, value: Any, verbose: bool = True):
        """Set a settings value by key."""
        settings = self._load_fn()
        settings[key] = value
        self._save_fn(settings)
        if verbose:
            print(f"Set {key} to: {value}")

    def update(self, updates: Dict[str, Any], verbose: bool = False):
        """Update multiple settings values at once."""
        settings = self._load_fn()
        settings.update(updates)
        self._save_fn(settings)
        if verbose:
            print(f"Updated {len(updates)} settings")


# Create singleton accessors for easy access
_global_settings = SettingsAccessor('global')
_user_settings = SettingsAccessor('user')


# ============================================================================
# DEFAULT PASSES MANAGEMENT
# ============================================================================

def get_default_passes():
    """
    Get the user's configured default passes.

    Returns:
        list: List of default pass names (excludes REQUIRED_PASSES)
    """
    settings = load_user_settings()
    return settings.get("default_passes", DEFAULT_PASSES.copy())


def get_all_default_passes():
    """
    Get all passes that should be selected by default.

    Returns:
        list: List of all default passes including REQUIRED_PASSES
    """
    user_passes = get_default_passes()
    # Combine required passes and user's default passes (avoid duplicates)
    all_passes = REQUIRED_PASSES.copy()
    for pass_name in user_passes:
        if pass_name not in all_passes:
            all_passes.append(pass_name)
    return all_passes


def set_default_passes(passes_list):
    """
    Set the user's default passes.

    Args:
        passes_list: List of pass names to set as defaults
    """
    _user_settings.set("default_passes", passes_list, verbose=False)


# ============================================================================
# COMFYUI GLOBAL SETTINGS
# All ComfyUI configuration values using unified accessor
# ============================================================================

def get_comfyui_path():
    """Get ComfyUI installation path."""
    return _global_settings.get("comfyui_path") or r"L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\ComfyUI_windows_portable\ComfyUI"

def set_comfyui_path(path):
    """Set ComfyUI installation path."""
    _global_settings.set("comfyui_path", path)

def get_comfyui_mode():
    """Get ComfyUI installation mode ('embedded', 'portable', 'standalone')."""
    return _global_settings.get("comfyui_mode", "embedded")

def set_comfyui_mode(mode):
    """Set ComfyUI installation mode."""
    if mode not in ("embedded", "portable", "standalone"):
        raise ValueError(f"Invalid ComfyUI mode: {mode}. Must be 'embedded', 'portable', or 'standalone'")
    _global_settings.set("comfyui_mode", mode)

def get_comfyui_python_path():
    """Get Python executable path for ComfyUI."""
    return _global_settings.get("comfyui_python_path", "")

def set_comfyui_python_path(path):
    """Set Python executable path for ComfyUI."""
    _global_settings.set("comfyui_python_path", path)

def get_comfyui_fast_mode():
    """Get whether ComfyUI --fast flag is enabled."""
    return _global_settings.get("comfyui_fast_mode", False)

def set_comfyui_fast_mode(enabled):
    """Set whether ComfyUI --fast flag is enabled."""
    _global_settings.set("comfyui_fast_mode", enabled)

def get_comfyui_fp16_accumulation():
    """Get whether ComfyUI --fp16-accumulation flag is enabled."""
    return _global_settings.get("comfyui_fp16_accumulation", False)

def set_comfyui_fp16_accumulation(enabled):
    """Set whether ComfyUI --fp16-accumulation flag is enabled."""
    _global_settings.set("comfyui_fp16_accumulation", enabled)

def get_comfyui_network_output_path():
    """Get network output path for ComfyUI."""
    return _global_settings.get("comfyui_network_output_path", "")

def set_comfyui_network_output_path(path):
    """Set network output path for ComfyUI."""
    _global_settings.set("comfyui_network_output_path", path)

DEFAULT_COMFYUI_TIMEOUT = 3600

def get_comfyui_timeout():
    """Get ComfyUI job timeout in seconds (default: 3600 = 1 hour)."""
    return _global_settings.get("comfyui_timeout", DEFAULT_COMFYUI_TIMEOUT)

def set_comfyui_timeout(timeout_seconds):
    """Set ComfyUI job timeout in seconds (min 60, max 86400)."""
    timeout_seconds = max(60, min(86400, int(timeout_seconds)))
    _global_settings.set("comfyui_timeout", timeout_seconds)

DEFAULT_SERVER_NOT_FOUND_WAIT = 300

def get_comfyui_server_not_found_behavior():
    """Get behavior when ComfyUI server is not found ('fail' or 'wait')."""
    return _global_settings.get("comfyui_server_not_found_behavior", "fail")

def set_comfyui_server_not_found_behavior(behavior):
    """Set behavior when ComfyUI server is not found."""
    if behavior not in ("fail", "wait"):
        raise ValueError(f"Invalid behavior: {behavior}. Must be 'fail' or 'wait'")
    _global_settings.set("comfyui_server_not_found_behavior", behavior)

def get_comfyui_server_wait_timeout():
    """Get timeout for waiting for ComfyUI server to start (default: 300 seconds)."""
    return _global_settings.get("comfyui_server_wait_timeout", DEFAULT_SERVER_NOT_FOUND_WAIT)

def set_comfyui_server_wait_timeout(timeout_seconds):
    """Set timeout for waiting for ComfyUI server to start (min 30, max 3600)."""
    timeout_seconds = max(30, min(3600, int(timeout_seconds)))
    _global_settings.set("comfyui_server_wait_timeout", timeout_seconds)


# ============================================================================
# COMFYUI TEXT PRESETS (User Settings)
# ============================================================================

def get_comfyui_text_presets():
    """Get saved ComfyUI text presets."""
    settings = load_user_settings()
    # Check both keys for backward compatibility
    presets = settings.get("comfyui_text_presets", {})
    legacy_presets = settings.get("prompt_presets", {})
    return {**presets, **legacy_presets}


def save_comfyui_text_preset(name, text):
    """Save a ComfyUI text preset."""
    settings = load_user_settings()
    if "comfyui_text_presets" not in settings:
        settings["comfyui_text_presets"] = {}
    settings["comfyui_text_presets"][name] = text
    save_user_settings(settings)
    print(f"Saved ComfyUI text preset: {name}")


def delete_comfyui_text_preset(name):
    """Delete a ComfyUI text preset."""
    settings = load_user_settings()
    deleted = False
    # Check both keys for backward compatibility
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
# COMFYUI PROMPT PRESETS (Per-Node-Type, User Settings)
# ============================================================================

def get_comfyui_prompt_presets_for_node_type(node_type):
    """Get prompt presets for a specific node type."""
    settings = load_user_settings()
    all_presets = settings.get("comfyui_prompt_presets_by_node_type", {})
    return all_presets.get(node_type, {})


def save_comfyui_prompt_preset_for_node_type(node_type, preset_name, text):
    """Save a prompt preset for a specific node type."""
    settings = load_user_settings()
    if "comfyui_prompt_presets_by_node_type" not in settings:
        settings["comfyui_prompt_presets_by_node_type"] = {}
    if node_type not in settings["comfyui_prompt_presets_by_node_type"]:
        settings["comfyui_prompt_presets_by_node_type"][node_type] = {}

    settings["comfyui_prompt_presets_by_node_type"][node_type][preset_name] = text
    save_user_settings(settings)
    print(f"Saved prompt preset '{preset_name}' for node type '{node_type}'")


def delete_comfyui_prompt_preset_for_node_type(node_type, preset_name):
    """Delete a prompt preset for a specific node type."""
    settings = load_user_settings()
    all_presets = settings.get("comfyui_prompt_presets_by_node_type", {})

    if node_type in all_presets and preset_name in all_presets[node_type]:
        del all_presets[node_type][preset_name]
        # Clean up empty node type entry
        if not all_presets[node_type]:
            del all_presets[node_type]
        settings["comfyui_prompt_presets_by_node_type"] = all_presets
        save_user_settings(settings)
        print(f"Deleted prompt preset '{preset_name}' from node type '{node_type}'")


def get_all_comfyui_prompt_presets_by_node_type():
    """Get all prompt presets for all node types."""
    settings = load_user_settings()
    return settings.get("comfyui_prompt_presets_by_node_type", {})


# ============================================================================
# COMFYUI WORKFLOW PRESETS (Global Settings)
# ============================================================================

def get_comfyui_workflow_presets():
    """Get saved ComfyUI workflow presets from global settings."""
    settings = load_global_settings()
    return settings.get("comfyui_workflow_presets", {})


def save_comfyui_workflow_preset(name, workflow_path, description="", iteratable=False, note="", full_restart=False, node_overrides=None, is_multi=False, workflows=None):
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
        print(f"Saved ComfyUI workflow preset: {name} -> {workflow_path} (iteratable={iteratable}, full_restart={full_restart})")


def update_comfyui_workflow_preset(name, workflow_path=None, description=None, iteratable=None, note=None, full_restart=None, node_overrides=None, is_multi=None, workflows=None):
    """Update an existing ComfyUI workflow preset."""
    settings = load_global_settings()
    presets = settings.get("comfyui_workflow_presets", {})

    if name not in presets:
        return False

    preset = presets[name]
    # Handle legacy format
    if isinstance(preset, str):
        preset = {"path": preset, "description": "", "iteratable": False, "note": "", "full_restart": False, "node_overrides": {}, "is_multi": False}

    if workflow_path is not None:
        preset["path"] = workflow_path
    if description is not None:
        preset["description"] = description
    if iteratable is not None:
        preset["iteratable"] = iteratable
    if note is not None:
        preset["note"] = note
    if full_restart is not None:
        preset["full_restart"] = full_restart
    if node_overrides is not None:
        preset["node_overrides"] = node_overrides
    if is_multi is not None:
        preset["is_multi"] = is_multi
    if workflows is not None:
        preset["workflows"] = workflows

    presets[name] = preset
    settings["comfyui_workflow_presets"] = presets
    save_global_settings(settings)
    print(f"Updated ComfyUI workflow preset: {name}")
    return True


def delete_comfyui_workflow_preset(name):
    """Delete a ComfyUI workflow preset from global settings."""
    settings = load_global_settings()
    if "comfyui_workflow_presets" in settings and name in settings["comfyui_workflow_presets"]:
        del settings["comfyui_workflow_presets"][name]
        save_global_settings(settings)
        print(f"Deleted ComfyUI workflow preset: {name}")


def get_comfyui_workflow_preset_path(name, selected_workflow=None):
    """Get the workflow path for a specific preset."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            # Check if it's a multi-workflow model and a specific workflow is selected
            if preset.get("is_multi") and selected_workflow:
                workflows = preset.get("workflows", {})
                if selected_workflow in workflows:
                    return workflows[selected_workflow].get("path")
            return preset.get("path")
        # Legacy format: just the path string
        return preset
    return None


def is_workflow_preset_iteratable(name):
    """Check if a workflow preset supports iterate mode."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("iteratable", False)
    return False


def is_workflow_preset_full_restart(name):
    """Check if a workflow preset requires full ComfyUI server restart."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("full_restart", False)
    return False


def is_workflow_preset_multi(name):
    """Check if a workflow preset is a multi-workflow model."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("is_multi", False)
    return False


def get_workflow_preset_workflows(name):
    """Get the workflows dictionary for a multi-workflow preset."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict) and preset.get("is_multi"):
            return preset.get("workflows", {})
    return {}


def get_workflow_preset_note(name, selected_workflow=None):
    """Get the note for a workflow preset (model-level note only)."""
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("note", "")
    return ""


def get_workflow_config(name, selected_workflow=None):
    """Get the complete workflow configuration for a preset."""
    presets = get_comfyui_workflow_presets()
    if name not in presets:
        return None

    preset = presets[name]
    if isinstance(preset, str):
        return {"path": preset, "iteratable": False, "full_restart": False, "note": "", "node_overrides": {}}

    # For multi-workflow models with a selected workflow
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

    # Single-workflow or default
    return {
        "path": preset.get("path", ""),
        "iteratable": preset.get("iteratable", False),
        "full_restart": preset.get("full_restart", False),
        "note": preset.get("note", ""),
        "node_overrides": preset.get("node_overrides", {}),
    }


# ============================================================================
# RESTRICTED TABS CONFIGURATION (Global)
# ============================================================================

DEFAULT_RESTRICTED_TABS = ["comfyui", "comfyui_gallery", "settings"]

TAB_RESTRICTION_MAP = {
    "comfyui": "RestrictComfyUI",
    "comfyui_gallery": "RestrictComfyUIGallery",
    "settings": "RestrictSettings",
    "passbuilder": "RestrictPassBuilder",
    "mp4maker": "RestrictMP4Maker",
    "republish": "RestrictRePublish",
    "shotcleaner": "RestrictShotCleaner"
}


def get_restricted_tabs():
    """Get the list of tabs that are restricted to admin users."""
    return _global_settings.get("restricted_tabs", DEFAULT_RESTRICTED_TABS)


def set_restricted_tabs(tabs):
    """Set the list of tabs that are restricted to admin users."""
    _global_settings.set("restricted_tabs", tabs, verbose=False)
    print(f"Updated restricted tabs: {tabs}")


def is_tab_restricted(tab_name):
    """Check if a specific tab is restricted to admin users."""
    restricted = get_restricted_tabs()
    return tab_name in restricted


# ============================================================================
# ADMIN USER MANAGEMENT (Global)
# ============================================================================

def get_admin_users():
    """Get the list of admin users from global settings."""
    return _global_settings.get("admin_users", [])


def is_admin_user(username):
    """Check if a username is in the admin list (case-insensitive)."""
    if not username:
        return False
    admin_users = get_admin_users()
    return username.lower() in [u.lower() for u in admin_users]


def add_admin_user(username):
    """Add a user to the admin list."""
    if not username:
        return

    settings = load_global_settings()
    if "admin_users" not in settings:
        settings["admin_users"] = []

    # Avoid duplicates (case-insensitive)
    existing_lower = [u.lower() for u in settings["admin_users"]]
    if username.lower() not in existing_lower:
        settings["admin_users"].append(username)
        save_global_settings(settings)
        print(f"Added admin user: {username}")


def remove_admin_user(username):
    """Remove a user from the admin list."""
    settings = load_global_settings()
    if "admin_users" not in settings:
        return

    original_list = settings["admin_users"]
    settings["admin_users"] = [u for u in original_list if u.lower() != username.lower()]

    if len(settings["admin_users"]) < len(original_list):
        save_global_settings(settings)
        print(f"Removed admin user: {username}")


# ============================================================================
# LAST BROWSED DIRECTORIES (User Settings)
# ============================================================================

def get_last_browse_directory(context):
    """Get the last browsed directory for a specific context."""
    settings = load_user_settings()
    directories = settings.get("last_browse_directories", {})
    return directories.get(context, "")


def set_last_browse_directory(context, directory):
    """Save the last browsed directory for a specific context."""
    if not directory:
        return

    settings = load_user_settings()
    if "last_browse_directories" not in settings:
        settings["last_browse_directories"] = {}
    settings["last_browse_directories"][context] = directory
    save_user_settings(settings)


# ============================================================================
# COMFYUI TAB STATE PERSISTENCE (User Settings)
# ============================================================================

def get_comfyui_tab_state():
    """Get the saved ComfyUI tab state."""
    return _user_settings.get("comfyui_tab_state", {})


def save_comfyui_tab_state(state):
    """Save the ComfyUI tab state."""
    _user_settings.set("comfyui_tab_state", state, verbose=False)


# ============================================================================
# TAB ORDER PERSISTENCE (User Settings)
# ============================================================================

def get_tab_order():
    """Get the saved tab order."""
    return _user_settings.get("tab_order", [])


def save_tab_order(tab_names):
    """Save the tab order."""
    _user_settings.set("tab_order", tab_names, verbose=False)


# ============================================================================
# MODEL EXPORT SETTINGS (User Settings)
# ============================================================================

def get_auto_extract_textures():
    """Get whether to automatically extract textures when exporting 3D models."""
    return _user_settings.get("auto_extract_textures", False)


def set_auto_extract_textures(enabled):
    """Set whether to automatically extract textures when exporting 3D models."""
    _user_settings.set("auto_extract_textures", enabled)


def get_generate_3d_thumbnails():
    """Get whether to generate thumbnails for 3D objects in the gallery."""
    return _user_settings.get("generate_3d_thumbnails", True)


def set_generate_3d_thumbnails(enabled):
    """Set whether to generate thumbnails for 3D objects in the gallery."""
    _user_settings.set("generate_3d_thumbnails", enabled)
