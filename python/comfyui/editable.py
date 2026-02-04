"""
ComfyUI Editable Node Extraction.

Handles parsing workflow nodes to find editable nodes (nodes with '_editable'
suffix in their title) and extracting their configuration for dynamic UI generation.
"""

import os
import logging
from typing import Optional, List, Tuple, Any
from dataclasses import dataclass, field

from comfyui.workflow import load_workflow
from comfyui.node_configs import EDITABLE_NODE_CONFIGS, SETTINGS_NODE_CONFIGS

logger = logging.getLogger(__name__)


@dataclass
class EditableNode:
    """Represents an editable node extracted from a workflow."""
    node_id: int
    node_type: str
    title: str
    display_name: str  # User-friendly name derived from title
    widget_type: str   # 'text', 'image', 'int', 'float', 'combo', 'toggle', '3d_model'
    widget_name: str = ""  # Name of the specific widget parameter (e.g. 'steps', 'cfg', 'seed')
    current_value: Any = None
    options: List[str] = field(default_factory=list)  # For combo boxes
    condition_node: Optional[str] = None  # Node name that controls visibility (from @if_<name> syntax)


def _parse_editable_title(title: str) -> Tuple[bool, str, Optional[str]]:
    """
    Parse a node title to check if it's editable and extract condition.

    Supports formats:
    - "Name_editable" - simple editable node
    - "Name_editable@if_ConditionNode" - editable node visible only when ConditionNode is true

    Note: Also supports older format with typo "editble" for backwards compatibility.

    Args:
        title: Node title to parse

    Returns:
        Tuple of (is_editable, base_title, condition_node_name)
        - is_editable: True if node is editable
        - base_title: Title without _editable and @if_ parts
        - condition_node_name: Name of condition node, or None if unconditional
    """
    # Handle both correct spelling and common typo
    editable_markers = ['_editable', '_editble']
    is_editable = False
    condition_node = None
    base_title = title

    for marker in editable_markers:
        if marker in title:
            is_editable = True
            # Check for conditional syntax: _editable@if_NodeName or _editable&if_NodeName
            # Split on the marker first
            parts = title.split(marker)
            base_title = parts[0]

            # Check for condition after the marker
            if len(parts) > 1:
                after_marker = parts[1]
                # Support both @ and & as separators
                for sep in ['@if_', '&if_']:
                    if after_marker.startswith(sep):
                        condition_node = after_marker[len(sep):]
                        break
            break

    return is_editable, base_title, condition_node


def extract_editable_nodes(workflow_path: str) -> List[EditableNode]:
    """
    Extract all nodes with '_editable' suffix in their title from a workflow.

    Supports conditional visibility with syntax: NodeName_editable@if_ConditionNodeName
    When a condition is specified, the widget should only be visible when the
    condition node's toggle/switch is true (value != 0).

    Args:
        workflow_path: Path to workflow JSON file

    Returns:
        List of EditableNode objects describing editable nodes
    """
    if not workflow_path or not os.path.exists(workflow_path):
        return []

    try:
        workflow = load_workflow(workflow_path)
    except Exception as e:
        logger.error(f"Error loading workflow for editable nodes: {e}")
        return []

    nodes = workflow.get('nodes', [])
    editable_nodes = []

    # First pass: build a map of node titles to node IDs (for condition resolution)
    title_to_node_id = {}
    for node in nodes:
        title = node.get('title', '')
        if title:
            # Store the base name (without _editable suffix) for condition matching
            is_edit, base, _ = _parse_editable_title(title)
            if is_edit:
                # Store both the full title and base name
                title_to_node_id[title] = node.get('id')
                title_to_node_id[base] = node.get('id')
            else:
                title_to_node_id[title] = node.get('id')

    for node in nodes:
        title = node.get('title', '')

        # Parse the title for editable marker and condition
        is_editable, base_title, condition_node_name = _parse_editable_title(title)
        if not is_editable:
            continue

        # Skip muted/bypassed nodes
        mode = node.get('mode', 0)
        if mode in (2, 4):
            continue

        node_id = node.get('id')
        node_type = node.get('type')
        widgets_values = node.get('widgets_values', [])

        # Create display name from base title (clean up underscores)
        display_name = base_title.replace('_', ' ').strip()
        # If display name is just the node type, make it more readable
        if not display_name or display_name == node_type:
            display_name = node_type.replace('Plus', '+')

        # Get widget configuration for this node type
        config = EDITABLE_NODE_CONFIGS.get(node_type)
        if config:
            for widget_idx, widget_name, widget_type in config:
                current_value = None
                if widget_idx < len(widgets_values):
                    current_value = widgets_values[widget_idx]

                editable_nodes.append(EditableNode(
                    node_id=node_id,
                    node_type=node_type,
                    title=title,
                    display_name=f"{display_name} - {widget_name}" if len(config) > 1 else display_name,
                    widget_type=widget_type,
                    widget_name=widget_name,
                    current_value=current_value,
                    condition_node=condition_node_name,
                ))
        else:
            # Unknown node type - try to create a generic text widget
            logger.warning(f"Unknown editable node type: {node_type} (title: {title})")
            if widgets_values:
                editable_nodes.append(EditableNode(
                    node_id=node_id,
                    node_type=node_type,
                    title=title,
                    display_name=display_name,
                    widget_type='text',
                    widget_name='value',
                    current_value=str(widgets_values[0]) if widgets_values else '',
                    condition_node=condition_node_name,
                ))

    logger.info(f"Found {len(editable_nodes)} editable nodes in workflow")
    for node in editable_nodes:
        condition_info = f" (visible when {node.condition_node})" if node.condition_node else ""
        logger.info(f"  - {node.display_name} ({node.node_type}): {node.widget_type}{condition_info}")

    return editable_nodes


# ============================================================================
# SETTINGS NODES
# ============================================================================

@dataclass
class SettingsNode:
    """Represents a settings node extracted from a workflow.

    Settings nodes are similar to editable nodes but displayed in a separate
    collapsible section, grouped by their base title.
    """
    node_id: int
    node_type: str
    title: str
    group_name: str    # Base title used for grouping (e.g., "Sampler" from "Sampler_settings")
    widget_name: str   # Name of this specific widget
    widget_type: str   # 'int', 'float', 'combo', 'toggle', 'string'
    current_value: Any = None
    options: List[str] = field(default_factory=list)  # For combo boxes


def _parse_settings_title(title: str) -> Tuple[bool, str]:
    """
    Parse a node title to check if it's a settings node.

    Args:
        title: Node title to parse

    Returns:
        Tuple of (is_settings, group_name)
        - is_settings: True if node is a settings node
        - group_name: Title without _settings suffix
    """
    if '_settings' in title:
        # Extract the base name before _settings
        parts = title.split('_settings')
        group_name = parts[0].replace('_', ' ').strip()
        return True, group_name
    return False, title


def extract_settings_nodes(workflow_path: str) -> List[SettingsNode]:
    """
    Extract all nodes with '_settings' suffix in their title from a workflow.

    Settings nodes are displayed in a collapsible "Workflow Settings" section,
    grouped by their base title.

    Args:
        workflow_path: Path to workflow JSON file

    Returns:
        List of SettingsNode objects describing settings nodes
    """
    if not workflow_path or not os.path.exists(workflow_path):
        return []

    try:
        workflow = load_workflow(workflow_path)
    except Exception as e:
        logger.error(f"Error loading workflow for settings nodes: {e}")
        return []

    nodes = workflow.get('nodes', [])
    settings_nodes = []

    for node in nodes:
        title = node.get('title', '')

        # Parse the title for settings marker
        is_settings, group_name = _parse_settings_title(title)
        if not is_settings:
            continue

        # Skip muted/bypassed nodes
        mode = node.get('mode', 0)
        if mode in (2, 4):
            continue

        node_id = node.get('id')
        node_type = node.get('type')
        widgets_values = node.get('widgets_values', [])

        # Get widget configuration for this node type
        config = SETTINGS_NODE_CONFIGS.get(node_type)
        if config:
            for widget_idx, widget_name, widget_type in config:
                current_value = None
                if widget_idx < len(widgets_values):
                    current_value = widgets_values[widget_idx]

                settings_nodes.append(SettingsNode(
                    node_id=node_id,
                    node_type=node_type,
                    title=title,
                    group_name=group_name,
                    widget_name=widget_name,
                    widget_type=widget_type,
                    current_value=current_value,
                ))
        else:
            # Unknown node type - try EDITABLE_NODE_CONFIGS as fallback
            fallback_config = EDITABLE_NODE_CONFIGS.get(node_type)
            if fallback_config:
                for widget_idx, widget_name, widget_type in fallback_config:
                    current_value = None
                    if widget_idx < len(widgets_values):
                        current_value = widgets_values[widget_idx]

                    settings_nodes.append(SettingsNode(
                        node_id=node_id,
                        node_type=node_type,
                        title=title,
                        group_name=group_name,
                        widget_name=widget_name,
                        widget_type=widget_type,
                        current_value=current_value,
                    ))
            else:
                logger.warning(f"Unknown settings node type: {node_type} (title: {title})")

    if settings_nodes:
        logger.info(f"Found {len(settings_nodes)} settings nodes in workflow")
        # Group by group_name for logging
        groups = {}
        for node in settings_nodes:
            if node.group_name not in groups:
                groups[node.group_name] = []
            groups[node.group_name].append(node)
        for group, nodes_list in groups.items():
            logger.info(f"  {group}: {[n.widget_name for n in nodes_list]}")

    return settings_nodes
