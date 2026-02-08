"""
ComfyUI Editable Node Extraction.

Handles parsing workflow nodes to find editable nodes (nodes with '_editable'
suffix in their title) and extracting their configuration for dynamic UI generation.
"""

import os
import re
import logging
from typing import Optional, List, Tuple, Any
from dataclasses import dataclass, field

from comfyui.workflow import load_workflow, _is_uuid, _get_subgraph_definitions
from comfyui.node_configs import EDITABLE_NODE_CONFIGS, SETTINGS_NODE_CONFIGS

logger = logging.getLogger(__name__)


@dataclass
class EditableNode:
    """Represents an editable node extracted from a workflow."""
    node_id: int
    node_type: str
    title: str
    display_name: str  # User-friendly name derived from title
    widget_type: str   # 'text', 'image', 'int', 'float', 'combo', 'toggle', '3d_model', 'directory', 'video'
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


def _resolve_config_entries(node_type: str, config: list) -> list:
    """Resolve config entries to (widget_idx, widget_name, widget_type) tuples.

    Supports formats:
    - Name only: 'seed' — index and type auto-resolved from node_info
    - Name + type override: ('image', 'image') — index auto-resolved, type forced
    - Legacy tuple: (0, 'seed', 'int') — used as-is (3-element tuple)

    Returns list of (widget_idx, widget_name, widget_type) tuples.
    """
    from comfyui.node_info import get_widget_index, get_widget_type

    resolved = []
    for entry in config:
        if entry is None:
            continue
        if isinstance(entry, str):
            # Name-only format
            widget_name = entry
            widget_idx = get_widget_index(node_type, widget_name)
            widget_type = get_widget_type(node_type, widget_name)
            if widget_idx is None or widget_type is None:
                logger.warning(
                    f"Could not resolve widget '{widget_name}' for {node_type} "
                    f"from node_info cache (idx={widget_idx}, type={widget_type})"
                )
                continue
            resolved.append((widget_idx, widget_name, widget_type))
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            # (widget_name, override_type) format — type override for special UI widgets
            widget_name, override_type = entry
            widget_idx = get_widget_index(node_type, widget_name)
            if widget_idx is None:
                logger.warning(
                    f"Could not resolve widget index for '{widget_name}' on {node_type}"
                )
                continue
            resolved.append((widget_idx, widget_name, override_type))
        elif isinstance(entry, (tuple, list)) and len(entry) == 3:
            # Legacy tuple format: (index, name, type)
            resolved.append(tuple(entry))
        else:
            logger.warning(f"Unknown config entry format for {node_type}: {entry}")
    return resolved


def _get_widget_options(node_type: str, widget_name: str) -> list:
    """Get combo options for a widget from node_info cache."""
    from comfyui.node_info import get_widget_info
    widget_info = get_widget_info(node_type, widget_name)
    if widget_info and widget_info.options:
        return widget_info.options
    return []


# Map ComfyUI type strings to widget_type identifiers
_COMFYUI_TYPE_MAP = {
    'INT': 'int',
    'FLOAT': 'float',
    'BOOLEAN': 'toggle',
    'STRING': 'string',  # May be overridden to 'text' if multiline
    'COMBO': 'combo',
}

# Phantom/internal widgets that should be skipped
_PHANTOM_WIDGET_NAMES = {'control_after_generate'}


def _extract_subgraph_widgets(
    node: dict,
    display_name: str,
    condition_node: Optional[str],
    subgraph_defs: dict,
) -> List[EditableNode]:
    """Extract EditableNode entries from a subgraph/component node.

    Subgraph nodes (UUID type) store their parameters in proxyWidgets and
    widgets_values.  This function parses those structures to create one
    EditableNode per exposed widget parameter.

    Args:
        node: The raw node dict from the workflow
        display_name: Cleaned display name for the node
        condition_node: Optional condition node name for visibility
        subgraph_defs: Dict mapping subgraph UUID -> definition dict

    Returns:
        List of EditableNode objects, one per widget parameter
    """
    node_id = node.get('id')
    node_type = node.get('type')
    title = node.get('title', '')
    widgets_values = node.get('widgets_values', [])
    if isinstance(widgets_values, dict):
        widgets_values = list(widgets_values.values())
    properties = node.get('properties', {})
    proxy_widgets = properties.get('proxyWidgets', [])
    node_inputs = node.get('inputs', [])
    sg_def = subgraph_defs.get(node_type, {})
    sg_def_inputs = sg_def.get('inputs', [])

    results = []

    # Build input lookup from the node's inputs array: name -> {type, label, ...}
    input_lookup = {}
    for inp in node_inputs:
        name = inp.get('name')
        if name:
            input_lookup[name] = inp

    # Build subgraph definition input lookup: name -> {type, label, ...}
    sg_input_lookup = {}
    for sg_inp in sg_def_inputs:
        name = sg_inp.get('name')
        if name:
            sg_input_lookup[name] = sg_inp

    if proxy_widgets:
        # Primary approach: use proxyWidgets property
        # Each entry is [node_id_str, widget_name]
        for idx, proxy_entry in enumerate(proxy_widgets):
            if not isinstance(proxy_entry, (list, tuple)) or len(proxy_entry) < 2:
                continue

            proxy_node_id_str, widget_name = proxy_entry[0], proxy_entry[1]

            # Skip phantom widgets
            if widget_name in _PHANTOM_WIDGET_NAMES:
                continue

            # Skip widgets that have a connection (link) - they're not user-editable
            inp_info = input_lookup.get(widget_name)
            if inp_info and inp_info.get('link') is not None:
                continue

            # Get value from widgets_values
            value = widgets_values[idx] if idx < len(widgets_values) else None

            # Determine type and display label
            widget_type = 'string'  # default fallback
            display_label = widget_name
            options = []

            if proxy_node_id_str == "-1":
                # Boundary input - look up in node's inputs and subgraph def inputs
                inp_info = input_lookup.get(widget_name) or {}
                sg_inp_info = sg_input_lookup.get(widget_name) or {}

                # Use label from input if available
                label = inp_info.get('label') or sg_inp_info.get('label')
                if label:
                    display_label = label

                # Determine type from input type field
                inp_type = inp_info.get('type') or sg_inp_info.get('type', '')
                widget_type = _COMFYUI_TYPE_MAP.get(inp_type, 'string')

                # For STRING type, check if multiline (heuristic: long values or "text" in name)
                if inp_type == 'STRING':
                    if isinstance(value, str) and (len(value) > 80 or '\n' in value):
                        widget_type = 'text'
                    elif widget_name in ('text', 'prompt', 'negative_prompt'):
                        widget_type = 'text'

            else:
                # Internal node widget - try to look up via node_info cache
                # The proxy_node_id_str references a node inside the subgraph definition
                sg_internal_nodes = sg_def.get('nodes', [])
                internal_node_type = None
                for sg_node in sg_internal_nodes:
                    if str(sg_node.get('id')) == proxy_node_id_str:
                        internal_node_type = sg_node.get('type')
                        break

                if internal_node_type:
                    from comfyui.node_info import get_widget_type, get_widget_info
                    cached_type = get_widget_type(internal_node_type, widget_name)
                    if cached_type:
                        widget_type = cached_type
                    cached_info = get_widget_info(internal_node_type, widget_name)
                    if cached_info and cached_info.options:
                        options = cached_info.options

                # Use label from node input if available
                inp_info = input_lookup.get(widget_name) or {}
                label = inp_info.get('label')
                if label:
                    display_label = label

            # For COMBO type with null value, try to get options
            if widget_type == 'combo' and not options:
                # Check if the subgraph definition input has options
                sg_inp_info = sg_input_lookup.get(widget_name) or {}
                sg_opts = sg_inp_info.get('options')
                if isinstance(sg_opts, list):
                    options = sg_opts

            # Clean up display label
            display_label = display_label.replace('_', ' ')

            multi_widget = len(proxy_widgets) - sum(
                1 for pw in proxy_widgets
                if isinstance(pw, (list, tuple)) and len(pw) >= 2
                and pw[1] in _PHANTOM_WIDGET_NAMES
            ) > 1

            results.append(EditableNode(
                node_id=node_id,
                node_type=node_type,
                title=title,
                display_name=f"{display_name} - {display_label}" if multi_widget else display_name,
                widget_type=widget_type,
                widget_name=widget_name,
                current_value=value,
                options=options,
                condition_node=condition_node,
            ))

    else:
        # Fallback: no proxyWidgets - use node's inputs array
        # Extract inputs that have a 'widget' property (these are widget inputs)
        widget_idx = 0
        widget_entries = []
        for inp in node_inputs:
            widget_def = inp.get('widget')
            if widget_def and isinstance(widget_def, dict) and inp.get('link') is None:
                widget_entries.append(inp)

        for inp in widget_entries:
            widget_def = inp.get('widget', {})
            widget_name = widget_def.get('name', inp.get('name', ''))
            inp_type = inp.get('type', '')
            label = inp.get('label') or widget_name

            widget_type = _COMFYUI_TYPE_MAP.get(inp_type, 'string')
            if inp_type == 'STRING' and widget_name in ('text', 'prompt', 'negative_prompt'):
                widget_type = 'text'

            value = widgets_values[widget_idx] if widget_idx < len(widgets_values) else None
            widget_idx += 1

            display_label = label.replace('_', ' ')

            results.append(EditableNode(
                node_id=node_id,
                node_type=node_type,
                title=title,
                display_name=f"{display_name} - {display_label}" if len(widget_entries) > 1 else display_name,
                widget_type=widget_type,
                widget_name=widget_name,
                current_value=value,
                condition_node=condition_node,
            ))

    return results


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

    # Build subgraph definitions map for UUID-type nodes
    subgraph_defs = _get_subgraph_definitions(workflow)

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
        # Normalize: some workflows store widgets_values as a dict instead of list
        if isinstance(widgets_values, dict):
            widgets_values = list(widgets_values.values())

        # Create display name from base title (clean up underscores)
        display_name = base_title.replace('_', ' ').strip()
        # If display name is just the node type, make it more readable
        if not display_name or display_name == node_type:
            display_name = node_type.replace('Plus', '+')

        # Get widget configuration for this node type
        config = EDITABLE_NODE_CONFIGS.get(node_type)
        if config:
            # Build lookup of connected inputs (those with links)
            node_inputs = node.get('inputs', [])
            connected_inputs = {inp.get('name') for inp in node_inputs if inp.get('link') is not None}

            resolved = _resolve_config_entries(node_type, config)
            for widget_idx, widget_name, widget_type in resolved:
                # Skip widgets that are connected to other nodes (not user-editable)
                if widget_name in connected_inputs:
                    continue

                current_value = None
                if widget_idx is not None and widget_idx < len(widgets_values):
                    current_value = widgets_values[widget_idx]

                # Try to get combo options from node_info
                options = _get_widget_options(node_type, widget_name)

                editable_nodes.append(EditableNode(
                    node_id=node_id,
                    node_type=node_type,
                    title=title,
                    display_name=f"{display_name} - {widget_name}" if len(config) > 1 else display_name,
                    widget_type=widget_type,
                    widget_name=widget_name,
                    current_value=current_value,
                    options=options,
                    condition_node=condition_node_name,
                ))
        else:
            # Try auto-discovery from node_info cache
            from comfyui.node_info import get_node_info, get_widget_index
            info = get_node_info(node_type)
            if info and info.widgets:
                # Build lookup of connected inputs (those with links)
                node_inputs = node.get('inputs', [])
                connected_inputs = {inp.get('name') for inp in node_inputs if inp.get('link') is not None}
                logger.info(f"Node {node_id} ({node_type}): total widgets={len(info.widgets)}, connected_inputs={connected_inputs}")

                for widget in info.widgets:
                    # Skip widgets that are connected to other nodes (not user-editable)
                    if widget.name in connected_inputs:
                        logger.info(f"  Skipping connected widget: {widget.name}")
                        continue
                    logger.info(f"  Adding editable widget: {widget.name}")

                    widget_idx = get_widget_index(node_type, widget.name)
                    current_value = None
                    if widget_idx is not None and widget_idx < len(widgets_values):
                        current_value = widgets_values[widget_idx]
                    options = widget.options or []
                    editable_nodes.append(EditableNode(
                        node_id=node_id,
                        node_type=node_type,
                        title=title,
                        display_name=f"{display_name} - {widget.name}" if len(info.widgets) > 1 else display_name,
                        widget_type=widget.widget_type,
                        widget_name=widget.name,
                        current_value=current_value,
                        options=options,
                        condition_node=condition_node_name,
                    ))
            elif _is_uuid(node_type) and node_type in subgraph_defs:
                # Subgraph/component node - extract widgets from proxyWidgets
                sg_widgets = _extract_subgraph_widgets(
                    node, display_name, condition_node_name, subgraph_defs
                )
                editable_nodes.extend(sg_widgets)
                if sg_widgets:
                    logger.info(f"  Extracted {len(sg_widgets)} widgets from subgraph node {node_id}")
            elif widgets_values:
                # Last resort: generic text widget
                logger.warning(f"Unknown editable node type: {node_type} (title: {title})")
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

    # Sort by display_name using natural sort so "Image 2" < "Image 10"
    def _natural_sort_key(node):
        return [int(c) if c.isdigit() else c.lower()
                for c in re.split(r'(\d+)', node.display_name)]

    editable_nodes.sort(key=_natural_sort_key)

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
        if isinstance(widgets_values, dict):
            widgets_values = list(widgets_values.values())

        # Get widget configuration for this node type
        config = SETTINGS_NODE_CONFIGS.get(node_type)
        if config:
            resolved = _resolve_config_entries(node_type, config)
            for widget_idx, widget_name, widget_type in resolved:
                current_value = None
                if widget_idx is not None and widget_idx < len(widgets_values):
                    current_value = widgets_values[widget_idx]

                options = _get_widget_options(node_type, widget_name)

                settings_nodes.append(SettingsNode(
                    node_id=node_id,
                    node_type=node_type,
                    title=title,
                    group_name=group_name,
                    widget_name=widget_name,
                    widget_type=widget_type,
                    current_value=current_value,
                    options=options,
                ))
        else:
            # Unknown node type - try EDITABLE_NODE_CONFIGS as fallback
            fallback_config = EDITABLE_NODE_CONFIGS.get(node_type)
            if fallback_config:
                resolved = _resolve_config_entries(node_type, fallback_config)
                for widget_idx, widget_name, widget_type in resolved:
                    current_value = None
                    if widget_idx is not None and widget_idx < len(widgets_values):
                        current_value = widgets_values[widget_idx]

                    options = _get_widget_options(node_type, widget_name)

                    settings_nodes.append(SettingsNode(
                        node_id=node_id,
                        node_type=node_type,
                        title=title,
                        group_name=group_name,
                        widget_name=widget_name,
                        widget_type=widget_type,
                        current_value=current_value,
                        options=options,
                    ))
            else:
                # Try auto-discovery from node_info cache
                from comfyui.node_info import get_node_info, get_widget_index
                info = get_node_info(node_type)
                if info and info.widgets:
                    for widget in info.widgets:
                        widget_idx = get_widget_index(node_type, widget.name)
                        current_value = None
                        if widget_idx is not None and widget_idx < len(widgets_values):
                            current_value = widgets_values[widget_idx]
                        options = widget.options or []
                        settings_nodes.append(SettingsNode(
                            node_id=node_id,
                            node_type=node_type,
                            title=title,
                            group_name=group_name,
                            widget_name=widget.name,
                            widget_type=widget.widget_type,
                            current_value=current_value,
                            options=options,
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
