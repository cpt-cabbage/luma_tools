"""
ComfyUI presets management for Luma Tools.

Handles text presets, prompt presets by node type, and workflow presets.
Text presets are stored in user settings, while workflow presets are in global settings.
"""

import logging
from typing import Dict, Any, Optional
from core.settings_manager import (
    load_user_settings, save_user_settings,
    load_global_settings, save_global_settings
)

logger = logging.getLogger(__name__)


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
        logger.info(f"Saved ComfyUI multi-workflow preset: {name} with {len(workflows or {})} workflow(s)")
    else:
        logger.info(f"Saved ComfyUI workflow preset: {name} -> {workflow_path}")


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
