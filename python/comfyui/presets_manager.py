"""
ComfyUI presets management for Luma Tools.

Handles text presets, prompt presets by node type, and workflow presets.
Text presets are stored in user settings, while workflow presets are in global settings.
"""

import logging
import os
import shutil
from typing import Dict, Any, Optional
from core.settings_manager import (
    load_user_settings, save_user_settings,
    load_global_settings, save_global_settings,
    safe_get_setting
)
from core.utils import ensure_directory, normalize_path

logger = logging.getLogger(__name__)


# ============================================================================
# WORKFLOW FILE COPYING
# ============================================================================

DEFAULT_WORKFLOWS_DIRECTORY = "L:/tools/_studio_tools/luma_tools/comfyui/workflows"


def get_workflows_directory() -> str:
    """Get the centralized workflows directory path.

    Returns:
        Path to workflows directory from settings, or default.
    """
    return safe_get_setting("comfyui_workflows_directory", DEFAULT_WORKFLOWS_DIRECTORY)


def _is_path_under_directory(file_path: str, directory: str) -> bool:
    """Check if a file path is under a given directory.

    Args:
        file_path: Path to check
        directory: Directory to check against

    Returns:
        True if file_path is under directory
    """
    file_path = os.path.normpath(os.path.abspath(file_path)).lower()
    directory = os.path.normpath(os.path.abspath(directory)).lower()
    return file_path.startswith(directory)


def _generate_unique_filename(directory: str, filename: str) -> str:
    """Generate a unique filename by appending version suffix if needed.

    Args:
        directory: Target directory
        filename: Original filename

    Returns:
        Unique filename (may be modified with _v001, _v002, etc.)
    """
    target_path = os.path.join(directory, filename)
    if not os.path.exists(target_path):
        return filename

    base, ext = os.path.splitext(filename)
    version = 1
    while True:
        new_filename = f"{base}_v{version:03d}{ext}"
        new_path = os.path.join(directory, new_filename)
        if not os.path.exists(new_path):
            return new_filename
        version += 1
        if version > 999:  # Safety limit
            raise RuntimeError(f"Too many versions of {filename}")


def copy_workflow_to_central_directory(source_path: str) -> Optional[str]:
    """Copy a workflow file to the centralized workflows directory.

    Uses flat structure - all workflows in the root directory.

    Args:
        source_path: Path to the source workflow JSON file

    Returns:
        New path to the copied workflow, or None if copy was skipped/failed
    """
    if not source_path or not os.path.isfile(source_path):
        logger.warning(f"Cannot copy workflow: source does not exist: {source_path}")
        return None

    workflows_dir = get_workflows_directory()

    # Check if source is already in the workflows directory
    if _is_path_under_directory(source_path, workflows_dir):
        logger.debug(f"Workflow already in central directory, skipping copy: {source_path}")
        return source_path  # Return original path, no copy needed

    # Ensure target directory exists
    try:
        ensure_directory(workflows_dir)
    except Exception as e:
        logger.error(f"Failed to create workflow directory {workflows_dir}: {e}")
        return None

    # Get filename and handle conflicts
    original_filename = os.path.basename(source_path)
    target_filename = _generate_unique_filename(workflows_dir, original_filename)
    target_path = os.path.join(workflows_dir, target_filename)

    # Copy the file
    try:
        shutil.copy2(source_path, target_path)
        logger.info(f"Copied workflow to central directory: {source_path} -> {target_path}")
        return normalize_path(target_path)
    except Exception as e:
        logger.error(f"Failed to copy workflow {source_path} to {target_path}: {e}")
        return None


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
    logger.info(f"Saved ComfyUI text preset: {name}")


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
        logger.info(f"Deleted ComfyUI text preset: {name}")


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
    logger.info(f"Saved prompt preset '{preset_name}' for node type '{node_type}'")


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
        logger.info(f"Deleted prompt preset '{preset_name}' from node type '{node_type}'")


def get_all_comfyui_prompt_presets_by_node_type() -> Dict[str, Dict[str, str]]:
    """Get all prompt presets for all node types."""
    return load_user_settings().get("comfyui_prompt_presets_by_node_type", {})


# ============================================================================
# COMFYUI WORKFLOW PRESETS (Global Settings)
# ============================================================================

def get_comfyui_workflow_presets() -> Dict[str, Any]:
    """Get saved ComfyUI workflow presets from global settings."""
    return load_global_settings().get("comfyui_workflow_presets", {})


# Valid output types for workflow presets
OUTPUT_TYPES = ("image", "video", "3d", "audio", "other")


def save_comfyui_workflow_preset(
    name: str,
    workflow_path: str,
    description: str = "",
    iteratable: bool = False,
    note: str = "",
    full_restart: bool = False,
    node_overrides: Optional[Dict] = None,
    is_multi: bool = False,
    workflows: Optional[Dict] = None,
    output_type: str = "image",
    copy_to_central: bool = True
):
    """Save a ComfyUI workflow preset to global settings.

    Args:
        name: Preset name
        workflow_path: Path to workflow JSON file
        description: Optional description
        iteratable: Whether preset supports iterate mode
        note: User note/description
        full_restart: Whether to restart ComfyUI server before running
        node_overrides: Dict of node overrides
        is_multi: Whether this is a multi-workflow preset
        workflows: Dict of workflows for multi-workflow presets
        output_type: Type of output (image, video, 3d, audio, other)
        copy_to_central: If True, copy workflow file(s) to central directory
    """
    # Copy main workflow to central directory if enabled
    final_workflow_path = workflow_path
    if copy_to_central and workflow_path:
        copied_path = copy_workflow_to_central_directory(workflow_path)
        if copied_path:
            final_workflow_path = copied_path

    # Handle multi-workflow presets - copy each sub-workflow
    final_workflows = workflows
    if copy_to_central and is_multi and workflows:
        final_workflows = {}
        for wf_name, wf_config in workflows.items():
            wf_path = wf_config.get("path", "")
            if wf_path:
                copied_wf_path = copy_workflow_to_central_directory(wf_path)
                if copied_wf_path:
                    wf_path = copied_wf_path
            final_workflows[wf_name] = {
                **wf_config,
                "path": wf_path
            }

    settings = load_global_settings()
    if "comfyui_workflow_presets" not in settings:
        settings["comfyui_workflow_presets"] = {}

    # Validate output_type
    if output_type not in OUTPUT_TYPES:
        output_type = "image"

    preset_data = {
        "path": final_workflow_path,
        "description": description,
        "iteratable": iteratable,
        "note": note,
        "full_restart": full_restart,
        "node_overrides": node_overrides or {},
        "is_multi": is_multi,
        "output_type": output_type,
    }
    if is_multi and final_workflows:
        preset_data["workflows"] = final_workflows

    settings["comfyui_workflow_presets"][name] = preset_data
    save_global_settings(settings)
    if is_multi:
        logger.info(f"Saved ComfyUI multi-workflow preset: {name} with {len(final_workflows or {})} workflow(s)")
    else:
        logger.info(f"Saved ComfyUI workflow preset: {name} -> {final_workflow_path}")


def update_comfyui_workflow_preset(name: str, copy_to_central: bool = True, **kwargs) -> bool:
    """Update an existing ComfyUI workflow preset.

    Args:
        name: Preset name
        copy_to_central: If True, copy new workflow paths to central directory
        **kwargs: Fields to update

    Returns:
        bool: True if update successful
    """
    settings = load_global_settings()
    presets = settings.get("comfyui_workflow_presets", {})
    if name not in presets:
        return False

    preset = presets[name]
    # Handle legacy format
    if isinstance(preset, str):
        preset = {"path": preset, "description": "", "iteratable": False, "note": "",
                  "full_restart": False, "node_overrides": {}, "is_multi": False,
                  "output_type": "image"}

    # Handle workflow_path with copy
    if "workflow_path" in kwargs and kwargs["workflow_path"] is not None:
        new_path = kwargs["workflow_path"]
        if copy_to_central and new_path:
            copied_path = copy_workflow_to_central_directory(new_path)
            if copied_path:
                new_path = copied_path
        preset["path"] = new_path
        del kwargs["workflow_path"]  # Remove so we don't process it again below

    # Handle multi-workflow updates with copy
    if "workflows" in kwargs and kwargs["workflows"] is not None and copy_to_central:
        final_workflows = {}
        for wf_name, wf_config in kwargs["workflows"].items():
            wf_path = wf_config.get("path", "")
            if wf_path:
                copied_wf_path = copy_workflow_to_central_directory(wf_path)
                if copied_wf_path:
                    wf_path = copied_wf_path
            final_workflows[wf_name] = {
                **wf_config,
                "path": wf_path
            }
        kwargs["workflows"] = final_workflows

    # Update remaining fields
    for key in ["description", "iteratable", "note", "full_restart",
                "node_overrides", "is_multi", "workflows", "output_type"]:
        if key in kwargs and kwargs[key] is not None:
            # Validate output_type
            if key == "output_type" and kwargs[key] not in OUTPUT_TYPES:
                continue
            preset[key] = kwargs[key]

    presets[name] = preset
    settings["comfyui_workflow_presets"] = presets
    save_global_settings(settings)
    logger.info(f"Updated ComfyUI workflow preset: {name}")
    return True


def delete_comfyui_workflow_preset(name: str):
    """Delete a ComfyUI workflow preset from global settings."""
    settings = load_global_settings()
    if "comfyui_workflow_presets" in settings and name in settings["comfyui_workflow_presets"]:
        del settings["comfyui_workflow_presets"][name]
        save_global_settings(settings)
        logger.info(f"Deleted ComfyUI workflow preset: {name}")


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


def _get_workflow_preset_field(name: str, field: str, default: Any = None) -> Any:
    """Get a field from a workflow preset.

    Args:
        name: Preset name
        field: Field name to retrieve
        default: Default value if field not found

    Returns:
        Field value or default
    """
    presets = get_comfyui_workflow_presets()
    if name in presets:
        preset = presets[name]
        if isinstance(preset, dict):
            return preset.get(field, default)
    return default


def is_workflow_preset_iteratable(name: str) -> bool:
    """Check if a workflow preset supports iterate mode."""
    return _get_workflow_preset_field(name, "iteratable", False)


def is_workflow_preset_full_restart(name: str) -> bool:
    """Check if a workflow preset requires full ComfyUI server restart."""
    return _get_workflow_preset_field(name, "full_restart", False)


def get_workflow_preset_output_type(name: str) -> str:
    """Get the output type for a workflow preset.

    Args:
        name: Preset name

    Returns:
        Output type string (image, video, 3d, audio, other). Defaults to "image".
    """
    output_type = _get_workflow_preset_field(name, "output_type", "image")
    if output_type not in OUTPUT_TYPES:
        return "image"
    return output_type


# ============================================================================
# COMFYUI STYLE PRESETS (User Settings)
# ============================================================================

def get_style_presets(workflow_preset: str = None) -> Dict[str, Dict[str, Any]]:
    """Get saved style presets.

    Style presets save all editable parameter values for quick recall.
    Optionally filtered by workflow preset.

    Args:
        workflow_preset: If provided, only return presets for this workflow

    Returns:
        Dict of preset_name -> {editable_values, workflow_preset, created}
    """
    settings = load_user_settings()
    all_presets = settings.get("comfyui_style_presets", {})

    if workflow_preset:
        return {
            name: preset for name, preset in all_presets.items()
            if preset.get('workflow_preset') == workflow_preset
        }
    return all_presets


def save_style_preset(
    name: str,
    editable_values: Dict[str, Any],
    workflow_preset: str = None,
    description: str = None
) -> bool:
    """Save a style preset with current editable parameter values.

    Args:
        name: Preset name
        editable_values: Dict of node_id -> {display_name, value, node_type, widget_type}
        workflow_preset: Associated workflow preset name
        description: Optional description

    Returns:
        bool: True if saved successfully
    """
    from datetime import datetime

    settings = load_user_settings()
    if "comfyui_style_presets" not in settings:
        settings["comfyui_style_presets"] = {}

    # Serialize editable values (exclude non-serializable data)
    serialized = {}
    for node_id, entries in editable_values.items():
        entry_list = entries if isinstance(entries, list) else [entries]
        for data in entry_list:
            if not isinstance(data, dict):
                continue
            widget_name = getattr(data.get('node'), 'widget_name', '') if data.get('node') else ''
            serial_key = f"{node_id}:{widget_name}" if widget_name else str(node_id)
            serialized[serial_key] = {
                "display_name": data.get('display_name', ''),
                "node_type": data.get('node_type', ''),
                "widget_type": data.get('widget_type', ''),
                "value": data.get('value'),
            }

    settings["comfyui_style_presets"][name] = {
        "editable_values": serialized,
        "workflow_preset": workflow_preset,
        "description": description,
        "created": datetime.now().isoformat(),
    }

    try:
        save_user_settings(settings)
        logger.info(f"Saved style preset: {name}")
        return True
    except Exception as e:
        logger.error(f"Failed to save style preset: {e}")
        return False


def load_style_preset(name: str) -> Optional[Dict[str, Any]]:
    """Load a style preset by name.

    Args:
        name: Preset name

    Returns:
        Preset dict with editable_values, workflow_preset, etc. or None
    """
    settings = load_user_settings()
    return settings.get("comfyui_style_presets", {}).get(name)


def delete_style_preset(name: str) -> bool:
    """Delete a style preset.

    Args:
        name: Preset name

    Returns:
        bool: True if deleted
    """
    settings = load_user_settings()
    if "comfyui_style_presets" in settings and name in settings["comfyui_style_presets"]:
        del settings["comfyui_style_presets"][name]
        save_user_settings(settings)
        logger.info(f"Deleted style preset: {name}")
        return True
    return False


def get_style_preset_names(workflow_preset: str = None) -> list:
    """Get list of style preset names.

    Args:
        workflow_preset: If provided, only return presets for this workflow

    Returns:
        List of preset names
    """
    presets = get_style_presets(workflow_preset)
    return sorted(presets.keys())


def is_workflow_preset_multi(name: str) -> bool:
    """Check if a workflow preset is a multi-workflow model."""
    return _get_workflow_preset_field(name, "is_multi", False)


def get_workflow_preset_subworkflows(name: str) -> Dict[str, Any]:
    """Get the workflows dictionary for a multi-workflow preset."""
    if is_workflow_preset_multi(name):
        return _get_workflow_preset_field(name, "workflows", {})
    return {}


def get_workflow_preset_note(name: str, selected_workflow: Optional[str] = None) -> str:
    """Get the note for a workflow preset."""
    return _get_workflow_preset_field(name, "note", "")


def get_workflow_preset_config(name: str, selected_workflow: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get the complete workflow configuration for a preset."""
    presets = get_comfyui_workflow_presets()
    if name not in presets:
        return None

    preset = presets[name]
    if isinstance(preset, str):
        return {"path": preset, "iteratable": False, "full_restart": False, "note": "",
                "node_overrides": {}, "output_type": "image"}

    # Get output_type from preset (model-level setting, not per-workflow)
    output_type = preset.get("output_type", "image")
    if output_type not in OUTPUT_TYPES:
        output_type = "image"

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
                "output_type": output_type,
            }

    return {
        "path": preset.get("path", ""),
        "iteratable": preset.get("iteratable", False),
        "full_restart": preset.get("full_restart", False),
        "note": preset.get("note", ""),
        "node_overrides": preset.get("node_overrides", {}),
        "output_type": output_type,
    }


# ============================================================================
# SESSION CONTINUITY (User Settings)
# ============================================================================

MAX_RECENT_SESSIONS = 5


def save_session(
    workflow_preset: str,
    editable_values: Dict[str, Any],
    seed: int,
    generation_count: int,
    input_images: list = None,
    description: str = None
) -> bool:
    """Save current session for later resumption.

    Sessions capture the complete state of a ComfyUI workflow configuration
    so users can easily return to previous work.

    Args:
        workflow_preset: Name of the workflow preset
        editable_values: Dict of node_id -> {display_name, value, node_type, widget_type}
        seed: Current seed value
        generation_count: Number of generations
        input_images: List of input image paths (optional)
        description: Optional description (auto-generated if not provided)

    Returns:
        bool: True if saved successfully
    """
    from datetime import datetime

    settings = load_user_settings()
    if "comfyui_recent_sessions" not in settings:
        settings["comfyui_recent_sessions"] = []

    # Serialize editable values
    serialized_values = {}
    for node_id, entries in editable_values.items():
        entry_list = entries if isinstance(entries, list) else [entries]
        for data in entry_list:
            if not isinstance(data, dict):
                continue
            widget_name = getattr(data.get('node'), 'widget_name', '') if data.get('node') else ''
            serial_key = f"{node_id}:{widget_name}" if widget_name else str(node_id)
            serialized_values[serial_key] = {
                "display_name": data.get('display_name', ''),
                "node_type": data.get('node_type', ''),
                "widget_type": data.get('widget_type', ''),
                "value": data.get('value'),
            }

    # Auto-generate description if not provided
    if not description:
        timestamp = datetime.now().strftime("%a %H:%M")
        description = f"{workflow_preset} - {timestamp}"

    session = {
        "workflow_preset": workflow_preset,
        "editable_values": serialized_values,
        "seed": seed,
        "generation_count": generation_count,
        "input_images": input_images or [],
        "description": description,
        "timestamp": datetime.now().isoformat(),
    }

    # Add to front of list (most recent first)
    sessions = settings["comfyui_recent_sessions"]
    sessions.insert(0, session)

    # Keep only last N sessions
    settings["comfyui_recent_sessions"] = sessions[:MAX_RECENT_SESSIONS]

    try:
        save_user_settings(settings)
        logger.info(f"Saved session: {description}")
        return True
    except Exception as e:
        logger.error(f"Failed to save session: {e}")
        return False


def get_recent_sessions() -> list:
    """Get list of recent sessions.

    Returns:
        List of session dicts, most recent first
    """
    settings = load_user_settings()
    return settings.get("comfyui_recent_sessions", [])


def get_session_by_index(index: int) -> Optional[Dict[str, Any]]:
    """Get a specific session by index.

    Args:
        index: 0-based index (0 = most recent)

    Returns:
        Session dict or None if index out of range
    """
    sessions = get_recent_sessions()
    if 0 <= index < len(sessions):
        return sessions[index]
    return None


def delete_session(index: int) -> bool:
    """Delete a session by index.

    Args:
        index: 0-based index

    Returns:
        bool: True if deleted
    """
    settings = load_user_settings()
    sessions = settings.get("comfyui_recent_sessions", [])
    if 0 <= index < len(sessions):
        deleted = sessions.pop(index)
        settings["comfyui_recent_sessions"] = sessions
        save_user_settings(settings)
        logger.info(f"Deleted session: {deleted.get('description', 'unknown')}")
        return True
    return False


def clear_recent_sessions() -> bool:
    """Clear all recent sessions.

    Returns:
        bool: True if cleared successfully
    """
    settings = load_user_settings()
    settings["comfyui_recent_sessions"] = []
    try:
        save_user_settings(settings)
        logger.info("Cleared all recent sessions")
        return True
    except Exception as e:
        logger.error(f"Failed to clear sessions: {e}")
        return False


def format_session_display(session: Dict[str, Any]) -> str:
    """Format a session for display in UI.

    Args:
        session: Session dict

    Returns:
        Formatted display string
    """
    from datetime import datetime

    description = session.get("description", "Unknown session")
    timestamp_str = session.get("timestamp", "")

    # Parse timestamp for relative time
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        delta = now - timestamp

        if delta.days == 0:
            if delta.seconds < 3600:
                minutes = delta.seconds // 60
                relative = f"{minutes}m ago" if minutes > 0 else "just now"
            else:
                hours = delta.seconds // 3600
                relative = f"{hours}h ago"
        elif delta.days == 1:
            relative = "yesterday"
        elif delta.days < 7:
            relative = f"{delta.days} days ago"
        else:
            relative = timestamp.strftime("%b %d")

        return f"{description} ({relative})"
    except (ValueError, TypeError):
        return description
