"""
Settings manager for Luma Tools.

Handles saving and loading user preferences and global settings.
"""

import os
import json
from config import (
    USER_SETTINGS_DIR,
    USER_SETTINGS_FILE,
    DEFAULT_PASSES,
    REQUIRED_PASSES,
    DEFAULT_GLOBAL_SETTINGS_PATH,
    GLOBAL_SETTINGS_FILENAME,
)


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
    default_settings = {
        "default_passes": DEFAULT_PASSES.copy()
    }

    if not os.path.exists(USER_SETTINGS_FILE):
        print("No user settings file found, using defaults")
        return default_settings

    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            print(f"Loaded user settings from: {USER_SETTINGS_FILE}")

            # Ensure default_passes key exists
            if "default_passes" not in settings:
                settings["default_passes"] = DEFAULT_PASSES.copy()

            return settings
    except Exception as e:
        print(f"Error loading user settings: {e}")
        return default_settings


def save_user_settings(settings):
    """
    Save user settings to file.

    Args:
        settings: Dictionary containing user settings
    """
    ensure_settings_dir()

    try:
        with open(USER_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
            print(f"Saved user settings to: {USER_SETTINGS_FILE}")
    except Exception as e:
        print(f"Error saving user settings: {e}")


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
    settings = load_user_settings()
    settings["default_passes"] = passes_list
    save_user_settings(settings)


def get_comfyui_path():
    """
    Get the configured ComfyUI installation path from global settings.

    Returns:
        str: Absolute path to ComfyUI directory
    """
    settings = load_global_settings()
    path = settings.get("comfyui_path")

    # Return default path if not configured
    if not path:
        return r"L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\ComfyUI_windows_portable\ComfyUI"

    return path


def set_comfyui_path(path):
    """
    Set the ComfyUI installation path in global settings.

    Args:
        path: Path to ComfyUI installation directory
    """
    settings = load_global_settings()
    settings["comfyui_path"] = path
    save_global_settings(settings)
    print(f"Set ComfyUI path to: {path}")


def get_comfyui_mode():
    """
    Get the ComfyUI installation mode.

    Returns:
        str: 'embedded' for python_embeded install, 'portable' for venv-based install
             (e.g., comfy-cli), 'standalone' for system install
    """
    settings = load_global_settings()
    return settings.get("comfyui_mode", "embedded")


def set_comfyui_mode(mode):
    """
    Set the ComfyUI installation mode.

    Args:
        mode: 'embedded' for python_embeded install, 'portable' for venv-based install
              (e.g., comfy-cli), 'standalone' for system install
    """
    if mode not in ("embedded", "portable", "standalone"):
        raise ValueError(f"Invalid ComfyUI mode: {mode}. Must be 'embedded', 'portable', or 'standalone'")
    settings = load_global_settings()
    settings["comfyui_mode"] = mode
    save_global_settings(settings)
    print(f"Set ComfyUI mode to: {mode}")


def get_comfyui_python_path():
    """
    Get the Python executable path for ComfyUI based on mode.

    Returns:
        str: Path to Python executable, or None if using system Python
    """
    settings = load_global_settings()
    return settings.get("comfyui_python_path", "")


def set_comfyui_python_path(path):
    """
    Set the Python executable path for standalone ComfyUI.

    Args:
        path: Path to Python executable (venv or system)
    """
    settings = load_global_settings()
    settings["comfyui_python_path"] = path
    save_global_settings(settings)
    print(f"Set ComfyUI Python path to: {path}")


def get_comfyui_fast_mode():
    """
    Get whether ComfyUI --fast flag is enabled.

    Returns:
        bool: True if fast mode is enabled
    """
    settings = load_global_settings()
    return settings.get("comfyui_fast_mode", False)


def set_comfyui_fast_mode(enabled):
    """
    Set whether ComfyUI --fast flag is enabled.

    Args:
        enabled: True to enable --fast flag
    """
    settings = load_global_settings()
    settings["comfyui_fast_mode"] = enabled
    save_global_settings(settings)
    print(f"Set ComfyUI fast mode to: {enabled}")


def get_comfyui_fp16_accumulation():
    """
    Get whether ComfyUI --fp16-accumulation flag is enabled.

    Returns:
        bool: True if fp16 accumulation is enabled
    """
    settings = load_global_settings()
    return settings.get("comfyui_fp16_accumulation", False)


def set_comfyui_fp16_accumulation(enabled):
    """
    Set whether ComfyUI --fp16-accumulation flag is enabled.

    Args:
        enabled: True to enable --fp16-accumulation flag
    """
    settings = load_global_settings()
    settings["comfyui_fp16_accumulation"] = enabled
    save_global_settings(settings)
    print(f"Set ComfyUI fp16 accumulation to: {enabled}")


def get_comfyui_text_presets():
    """
    Get saved ComfyUI text presets.

    Returns:
        dict: Dictionary of preset_name -> preset_text
    """
    settings = load_user_settings()
    # Check both keys for backward compatibility (prompt_presets was the old key)
    presets = settings.get("comfyui_text_presets", {})
    legacy_presets = settings.get("prompt_presets", {})
    # Merge legacy presets (legacy takes precedence if both exist for migration)
    return {**presets, **legacy_presets}


def save_comfyui_text_preset(name, text):
    """
    Save a ComfyUI text preset.

    Args:
        name: Preset name
        text: Preset text content
    """
    settings = load_user_settings()
    if "comfyui_text_presets" not in settings:
        settings["comfyui_text_presets"] = {}
    settings["comfyui_text_presets"][name] = text
    save_user_settings(settings)
    print(f"Saved ComfyUI text preset: {name}")


def delete_comfyui_text_preset(name):
    """
    Delete a ComfyUI text preset.

    Args:
        name: Preset name to delete
    """
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
# GLOBAL SETTINGS
# ============================================================================

def get_global_settings_path():
    """
    Get the path to the global settings directory.

    Returns:
        str: Path to global settings directory (user override or default)
    """
    settings = load_user_settings()
    path = settings.get("global_settings_path")
    if path and os.path.isdir(path):
        return path
    return DEFAULT_GLOBAL_SETTINGS_PATH


def set_global_settings_path(path):
    """
    Set a custom global settings path.

    Args:
        path: Path to global settings directory
    """
    settings = load_user_settings()
    settings["global_settings_path"] = path
    save_user_settings(settings)
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
    default_settings = {
        "comfyui_workflow_presets": {},
        "admin_users": ["christophe.leyder"]  # Default admin user
    }

    settings_file = _get_global_settings_file()
    if not os.path.exists(settings_file):
        print(f"No global settings file found at {settings_file}, using defaults")
        return default_settings

    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
            print(f"Loaded global settings from: {settings_file}")
            return settings
    except Exception as e:
        print(f"Error loading global settings: {e}")
        return default_settings


def save_global_settings(settings):
    """
    Save global settings to file.

    Args:
        settings: Dictionary containing global settings
    """
    _ensure_global_settings_dir()

    settings_file = _get_global_settings_file()
    try:
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)
            print(f"Saved global settings to: {settings_file}")
    except Exception as e:
        print(f"Error saving global settings: {e}")


# ============================================================================
# COMFYUI WORKFLOW PRESETS (Global)
# ============================================================================

def get_comfyui_workflow_presets():
    """
    Get saved ComfyUI workflow presets from global settings.

    Returns:
        dict: Dictionary of preset_name -> {
            "path": workflow_path,
            "description": optional_description,
            "iteratable": bool (whether iterate mode is available),
            "note": optional_note,
            "full_restart": bool,
            "node_overrides": dict,
            "is_multi": bool (whether this is a multi-workflow model),
            "workflows": dict of workflow_name -> {
                "path": workflow_path,
                "note": optional_note,
                "iteratable": bool,
                "full_restart": bool,
                "node_overrides": dict
            }
        }
    """
    settings = load_global_settings()
    return settings.get("comfyui_workflow_presets", {})


def save_comfyui_workflow_preset(name, workflow_path, description="", iteratable=False, note="", full_restart=False, node_overrides=None, is_multi=False, workflows=None):
    """
    Save a ComfyUI workflow preset to global settings.

    Args:
        name: Preset display name
        workflow_path: Path to the workflow JSON file (for single-workflow models)
        description: Optional description for the preset
        iteratable: Whether this workflow supports iterate mode
        note: Optional user note for this preset
        full_restart: Whether to completely restart ComfyUI server before processing
        node_overrides: Dict of node title -> {enabled: bool, default_value: str} overrides
        is_multi: Whether this is a multi-workflow model
        workflows: Dict of workflow_name -> workflow config (for multi-workflow models)
    """
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
    """
    Update an existing ComfyUI workflow preset.

    Args:
        name: Preset name to update
        workflow_path: New path (None to keep existing)
        description: New description (None to keep existing)
        iteratable: New iteratable flag (None to keep existing)
        note: New note (None to keep existing)
        full_restart: New full_restart flag (None to keep existing)
        node_overrides: New node overrides dict (None to keep existing)
        is_multi: New is_multi flag (None to keep existing)
        workflows: New workflows dict for multi-workflow models (None to keep existing)

    Returns:
        bool: True if updated, False if preset not found
    """
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


def is_workflow_preset_iteratable(name):
    """
    Check if a workflow preset supports iterate mode.

    Args:
        name: Preset name

    Returns:
        bool: True if iteratable, False otherwise
    """
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("iteratable", False)
    return False


def is_workflow_preset_full_restart(name):
    """
    Check if a workflow preset requires full ComfyUI server restart.

    Args:
        name: Preset name

    Returns:
        bool: True if full restart is required, False otherwise
    """
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("full_restart", False)
    return False


def delete_comfyui_workflow_preset(name):
    """
    Delete a ComfyUI workflow preset from global settings.

    Args:
        name: Preset name to delete
    """
    settings = load_global_settings()
    if "comfyui_workflow_presets" in settings and name in settings["comfyui_workflow_presets"]:
        del settings["comfyui_workflow_presets"][name]
        save_global_settings(settings)
        print(f"Deleted ComfyUI workflow preset: {name}")


def get_comfyui_workflow_preset_path(name, selected_workflow=None):
    """
    Get the workflow path for a specific preset.

    Args:
        name: Preset name
        selected_workflow: For multi-workflow models, the name of the selected workflow

    Returns:
        str: Path to workflow file, or None if not found
    """
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


def is_workflow_preset_multi(name):
    """
    Check if a workflow preset is a multi-workflow model.

    Args:
        name: Preset name

    Returns:
        bool: True if multi-workflow, False otherwise
    """
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get("is_multi", False)
    return False


def get_workflow_preset_workflows(name):
    """
    Get the workflows dictionary for a multi-workflow preset.

    Args:
        name: Preset name

    Returns:
        dict: Dictionary of workflow_name -> workflow config, or empty dict
    """
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict) and preset.get("is_multi"):
            return preset.get("workflows", {})
    return {}


def get_workflow_preset_note(name, selected_workflow=None):
    """
    Get the note for a workflow preset.

    Args:
        name: Preset name
        selected_workflow: For multi-workflow models, the name of the selected workflow

    Returns:
        str: Note text, or empty string if not found
    """
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            # For multi-workflow models with a selected workflow, return that workflow's note
            if preset.get("is_multi") and selected_workflow:
                workflows = preset.get("workflows", {})
                if selected_workflow in workflows:
                    return workflows[selected_workflow].get("note", "")
            # Otherwise return the model-level note
            return preset.get("note", "")
    return ""


def get_workflow_config(name, selected_workflow=None):
    """
    Get the complete workflow configuration for a preset.

    For single-workflow models, returns the preset config.
    For multi-workflow models, returns the selected workflow's config
    merged with the model-level config.

    Args:
        name: Preset name
        selected_workflow: For multi-workflow models, the name of the selected workflow

    Returns:
        dict: Workflow configuration with keys: path, iteratable, full_restart, note, node_overrides
    """
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
# COMFYUI NETWORK OUTPUT PATH (Global)
# ============================================================================

def get_comfyui_network_output_path():
    """
    Get the network output path for ComfyUI from global settings.

    This is the shared network path where ComfyUI writes outputs,
    accessible by farm workers and LoadImage nodes.

    Returns:
        str: Network output path, or empty string if not configured
    """
    settings = load_global_settings()
    return settings.get("comfyui_network_output_path", "")


def set_comfyui_network_output_path(path):
    """
    Set the network output path for ComfyUI in global settings.

    Args:
        path: Network path for ComfyUI output
    """
    settings = load_global_settings()
    settings["comfyui_network_output_path"] = path
    save_global_settings(settings)
    print(f"Set ComfyUI network output path to: {path}")


# Default timeout in seconds (1 hour)
DEFAULT_COMFYUI_TIMEOUT = 3600


def get_comfyui_timeout():
    """
    Get the ComfyUI job timeout in seconds from global settings.

    This is the maximum time a single ComfyUI generation can run before
    timing out. Useful for complex workflows like Trellis/UltraShape that
    can take a long time.

    Returns:
        int: Timeout in seconds (default: 3600 = 1 hour)
    """
    settings = load_global_settings()
    return settings.get("comfyui_timeout", DEFAULT_COMFYUI_TIMEOUT)


def set_comfyui_timeout(timeout_seconds):
    """
    Set the ComfyUI job timeout in seconds in global settings.

    Args:
        timeout_seconds: Timeout in seconds (minimum 60, maximum 86400)
    """
    # Clamp to valid range
    timeout_seconds = max(60, min(86400, int(timeout_seconds)))
    settings = load_global_settings()
    settings["comfyui_timeout"] = timeout_seconds
    save_global_settings(settings)
    print(f"Set ComfyUI timeout to: {timeout_seconds} seconds")


# Default wait time for server not found (5 minutes)
DEFAULT_SERVER_NOT_FOUND_WAIT = 300


def get_comfyui_server_not_found_behavior():
    """
    Get the behavior when ComfyUI server is not found in persistent mode.

    Returns:
        str: 'fail' to fail immediately, 'wait' to wait for server to start
    """
    settings = load_global_settings()
    return settings.get("comfyui_server_not_found_behavior", "fail")


def set_comfyui_server_not_found_behavior(behavior):
    """
    Set the behavior when ComfyUI server is not found in persistent mode.

    Args:
        behavior: 'fail' to fail immediately, 'wait' to wait for server to start
    """
    if behavior not in ("fail", "wait"):
        raise ValueError(f"Invalid behavior: {behavior}. Must be 'fail' or 'wait'")
    settings = load_global_settings()
    settings["comfyui_server_not_found_behavior"] = behavior
    save_global_settings(settings)
    print(f"Set ComfyUI server not found behavior to: {behavior}")


def get_comfyui_server_wait_timeout():
    """
    Get the timeout for waiting for ComfyUI server to start (in seconds).

    Returns:
        int: Timeout in seconds (default: 300 = 5 minutes)
    """
    settings = load_global_settings()
    return settings.get("comfyui_server_wait_timeout", DEFAULT_SERVER_NOT_FOUND_WAIT)


def set_comfyui_server_wait_timeout(timeout_seconds):
    """
    Set the timeout for waiting for ComfyUI server to start.

    Args:
        timeout_seconds: Timeout in seconds (minimum 30, maximum 3600)
    """
    # Clamp to valid range
    timeout_seconds = max(30, min(3600, int(timeout_seconds)))
    settings = load_global_settings()
    settings["comfyui_server_wait_timeout"] = timeout_seconds
    save_global_settings(settings)
    print(f"Set ComfyUI server wait timeout to: {timeout_seconds} seconds")




# ============================================================================
# COMFYUI PROMPT PRESETS (Per-Node-Type, User Settings)
# ============================================================================

def get_comfyui_prompt_presets_for_node_type(node_type):
    """
    Get prompt presets for a specific node type.

    Args:
        node_type: The ComfyUI node type (e.g., 'CLIPTextEncode', 'TextEncodeQwenImageEditPlus')

    Returns:
        dict: Dictionary of preset_name -> preset_text
    """
    settings = load_user_settings()
    all_presets = settings.get("comfyui_prompt_presets_by_node_type", {})
    return all_presets.get(node_type, {})


def save_comfyui_prompt_preset_for_node_type(node_type, preset_name, text):
    """
    Save a prompt preset for a specific node type.

    Args:
        node_type: The ComfyUI node type (e.g., 'CLIPTextEncode', 'TextEncodeQwenImageEditPlus')
        preset_name: Name for the prompt preset
        text: The prompt text to save
    """
    settings = load_user_settings()
    if "comfyui_prompt_presets_by_node_type" not in settings:
        settings["comfyui_prompt_presets_by_node_type"] = {}
    if node_type not in settings["comfyui_prompt_presets_by_node_type"]:
        settings["comfyui_prompt_presets_by_node_type"][node_type] = {}

    settings["comfyui_prompt_presets_by_node_type"][node_type][preset_name] = text
    save_user_settings(settings)
    print(f"Saved prompt preset '{preset_name}' for node type '{node_type}'")


def delete_comfyui_prompt_preset_for_node_type(node_type, preset_name):
    """
    Delete a prompt preset for a specific node type.

    Args:
        node_type: The ComfyUI node type
        preset_name: Name of the prompt preset to delete
    """
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
    """
    Get all prompt presets for all node types.

    Returns:
        dict: Dictionary of node_type -> {preset_name -> preset_text}
    """
    settings = load_user_settings()
    return settings.get("comfyui_prompt_presets_by_node_type", {})


# ============================================================================
# RESTRICTED TABS CONFIGURATION (Global)
# ============================================================================

# Default restricted tabs (legacy behavior)
DEFAULT_RESTRICTED_TABS = ["comfyui", "comfyui_gallery", "settings"]

# Tab name to checkbox mapping
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
    """
    Get the list of tabs that are restricted to admin users.

    Returns:
        list: List of tab object names that should be hidden for non-admin users
    """
    settings = load_global_settings()
    return settings.get("restricted_tabs", DEFAULT_RESTRICTED_TABS)


def set_restricted_tabs(tabs):
    """
    Set the list of tabs that are restricted to admin users.

    Args:
        tabs: List of tab object names to restrict
    """
    settings = load_global_settings()
    settings["restricted_tabs"] = tabs
    save_global_settings(settings)
    print(f"Updated restricted tabs: {tabs}")


def is_tab_restricted(tab_name):
    """
    Check if a specific tab is restricted to admin users.

    Args:
        tab_name: The object name of the tab

    Returns:
        bool: True if tab is restricted, False otherwise
    """
    restricted = get_restricted_tabs()
    return tab_name in restricted


# ============================================================================
# LAST BROWSED DIRECTORIES
# ============================================================================

def get_last_browse_directory(context):
    """
    Get the last browsed directory for a specific context.

    Args:
        context: String identifier for the browse context (e.g., "comfyui_workflow",
                 "comfyui_output", "mp4_custom", "republish_custom", "comfyui_images")

    Returns:
        str: Last browsed directory path, or empty string if not set
    """
    settings = load_user_settings()
    directories = settings.get("last_browse_directories", {})
    return directories.get(context, "")


def set_last_browse_directory(context, directory):
    """
    Save the last browsed directory for a specific context.

    Args:
        context: String identifier for the browse context
        directory: Directory path to save
    """
    if not directory:
        return

    settings = load_user_settings()
    if "last_browse_directories" not in settings:
        settings["last_browse_directories"] = {}
    settings["last_browse_directories"][context] = directory
    save_user_settings(settings)


# ============================================================================
# COMFYUI TAB STATE PERSISTENCE
# ============================================================================

def get_comfyui_tab_state():
    """
    Get the saved ComfyUI tab state.

    Returns:
        dict: Dictionary with keys:
            - workflow_preset: Last selected workflow preset name
            - output_directory: Last used output directory
            - generation_count: Last used generation count
            - editable_values: Dict of node_id -> value for editable nodes
    """
    settings = load_user_settings()
    return settings.get("comfyui_tab_state", {})


def save_comfyui_tab_state(state):
    """
    Save the ComfyUI tab state.

    Args:
        state: Dictionary containing tab state to save
    """
    settings = load_user_settings()
    settings["comfyui_tab_state"] = state
    save_user_settings(settings)


# ============================================================================
# TAB ORDER PERSISTENCE
# ============================================================================

def get_tab_order():
    """
    Get the saved tab order.

    Returns:
        list: List of tab object names in order, or empty list if not saved
    """
    settings = load_user_settings()
    return settings.get("tab_order", [])


def save_tab_order(tab_names):
    """
    Save the tab order.

    Args:
        tab_names: List of tab object names in their current order
    """
    settings = load_user_settings()
    settings["tab_order"] = tab_names
    save_user_settings(settings)


# ============================================================================
# ADMIN USER MANAGEMENT
# ============================================================================

def get_admin_users():
    """
    Get the list of admin users from global settings.

    Returns:
        list: List of admin usernames
    """
    settings = load_global_settings()
    return settings.get("admin_users", [])


def is_admin_user(username):
    """
    Check if a username is in the admin list.

    Args:
        username: Username to check

    Returns:
        bool: True if user is an admin (case-insensitive)
    """
    if not username:
        return False
    admin_users = get_admin_users()
    return username.lower() in [u.lower() for u in admin_users]


def add_admin_user(username):
    """
    Add a user to the admin list.

    Args:
        username: Username to add
    """
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
    """
    Remove a user from the admin list.

    Args:
        username: Username to remove
    """
    settings = load_global_settings()
    if "admin_users" not in settings:
        return

    original_list = settings["admin_users"]
    settings["admin_users"] = [u for u in original_list if u.lower() != username.lower()]

    if len(settings["admin_users"]) < len(original_list):
        save_global_settings(settings)
        print(f"Removed admin user: {username}")


# ============================================================================
# MODEL EXPORT SETTINGS (User Settings)
# ============================================================================

def get_auto_extract_textures():
    """
    Get whether to automatically extract textures when exporting 3D models.

    Returns:
        bool: True if auto texture extraction is enabled
    """
    settings = load_user_settings()
    return settings.get("auto_extract_textures", False)


def set_auto_extract_textures(enabled):
    """
    Set whether to automatically extract textures when exporting 3D models.

    Args:
        enabled: True to enable auto texture extraction
    """
    settings = load_user_settings()
    settings["auto_extract_textures"] = enabled
    save_user_settings(settings)
    print(f"Set auto extract textures to: {enabled}")
