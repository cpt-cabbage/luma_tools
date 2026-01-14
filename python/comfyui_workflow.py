"""
ComfyUI Workflow Loading and Format Conversion.

Handles loading workflow JSON files and converting between UI/nodes format
and API format used by ComfyUI's API.
"""

import os
import json
from typing import Dict, Any, List, Optional

from comfyui_node_configs import WIDGET_MAPPINGS, SKIP_NODE_TYPES


def load_workflow(workflow_path: str) -> Dict[str, Any]:
    """
    Load ComfyUI workflow JSON from file.

    Args:
        workflow_path: Path to workflow JSON file

    Returns:
        Workflow dictionary
    """
    with open(workflow_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_workflow(
    workflow: Dict[str, Any],
    output_dir: str,
    job_id: Optional[str] = None
) -> str:
    """
    Save modified workflow to a JSON file with unique name per job.

    Args:
        workflow: Modified workflow dictionary
        output_dir: Directory to save the workflow file
        job_id: Optional unique job identifier. If not provided, generates one
                using timestamp + random suffix to prevent workflow file conflicts
                between concurrent jobs.

    Returns:
        Path to saved workflow file
    """
    import uuid
    from datetime import datetime

    os.makedirs(output_dir, exist_ok=True)

    # Generate unique job ID if not provided
    if not job_id:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        job_id = f"{timestamp}_{unique_suffix}"

    workflow_filename = f"comfyui_workflow_{job_id}.json"
    workflow_path = os.path.join(output_dir, workflow_filename)

    with open(workflow_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2)

    print(f"Saved modified workflow to: {workflow_path}")
    return workflow_path


def is_api_format(workflow: Dict[str, Any]) -> bool:
    """
    Check if workflow is in API format vs UI/nodes format.

    API format has node IDs as keys with 'inputs' and 'class_type'.
    UI format has a 'nodes' array with 'widgets_values'.
    """
    # API format has no 'nodes' key and values have 'class_type'
    if 'nodes' in workflow:
        return False

    # Check if first value looks like API format
    for value in workflow.values():
        if isinstance(value, dict) and 'class_type' in value:
            return True

    return False


def _extract_widget_names_from_node(node: Dict[str, Any]) -> Optional[List[str]]:
    """
    Extract widget names from a node's inputs array.

    ComfyUI workflow nodes contain an 'inputs' array where each input with a
    'widget' property represents a widget. The order of these widget-inputs
    corresponds to the order of values in 'widgets_values'.

    IMPORTANT: ComfyUI has a special 'control_after_generate' widget that appears
    in widgets_values immediately after seed/noise_seed widgets, but is NOT listed
    in the inputs array. We try inserting placeholders for it, but validate the
    count matches before returning.

    Args:
        node: Node dictionary from workflow

    Returns:
        List of widget names in order, or None if extraction failed.
        Names may include None for widgets we should skip (like control_after_generate).
    """
    inputs_spec = node.get('inputs', [])
    widgets_values = node.get('widgets_values', [])

    if not inputs_spec or not widgets_values:
        return None

    # Seed widget names that have control_after_generate following them
    SEED_WIDGET_NAMES = {'seed', 'noise_seed'}

    # Collect inputs that have widget properties (these are the widgets)
    base_widget_names = []
    for inp in inputs_spec:
        widget_def = inp.get('widget')
        if widget_def and isinstance(widget_def, dict):
            widget_name = widget_def.get('name')
            if widget_name:
                base_widget_names.append(widget_name)

    if not base_widget_names:
        return None

    # Check if base names match (no control_after_generate needed)
    if len(base_widget_names) == len(widgets_values):
        return base_widget_names

    # Try adding control_after_generate placeholders after seed widgets
    widget_names_with_placeholders = []
    for name in base_widget_names:
        widget_names_with_placeholders.append(name)
        if name in SEED_WIDGET_NAMES:
            widget_names_with_placeholders.append(None)  # None = skip this value

    # Check if names with placeholders match
    if len(widget_names_with_placeholders) == len(widgets_values):
        return widget_names_with_placeholders

    # Neither approach worked - return None to fall back to manual mapping
    # This handles nodes with button widgets or other special cases
    return None


def _build_subgraph_widget_map(workflow: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Build a mapping of subgraph UUIDs to their widget names from workflow definitions.

    Args:
        workflow: Workflow dictionary containing 'definitions' section

    Returns:
        Dict mapping subgraph UUID -> list of input names that act as widgets
    """
    subgraph_map = {}
    definitions = workflow.get('definitions', {})
    subgraphs = definitions.get('subgraphs', [])

    for sg in subgraphs:
        sg_id = sg.get('id')
        if sg_id:
            # Get input names from subgraph definition - these become widgets
            inputs = sg.get('inputs', [])
            widget_names = [inp.get('name') for inp in inputs if inp.get('name')]
            if widget_names:
                subgraph_map[sg_id] = widget_names

    return subgraph_map


def convert_to_api_format(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert UI/nodes format workflow to API format.

    UI format has 'nodes' array with widgets_values.
    API format has node IDs as keys with 'inputs' dict.

    Args:
        workflow: Workflow in UI/nodes format

    Returns:
        Workflow in API format
    """
    if is_api_format(workflow):
        return workflow  # Already in API format

    nodes = workflow.get('nodes', [])
    links = workflow.get('links', [])

    # Build subgraph widget map for UUID node types
    subgraph_widgets = _build_subgraph_widget_map(workflow)

    # First pass: collect all node IDs that will be skipped (muted/bypassed)
    skipped_node_ids = set()
    for node in nodes:
        node_id = node.get('id')
        node_type = node.get('type')
        node_mode = node.get('mode', 0)
        # Skip muted or bypassed nodes (mode 2 = bypass, mode 4 = mute)
        if node_mode in (2, 4):
            skipped_node_ids.add(node_id)
            print(f"Will skip node {node_id} ({node_type}) - mode {node_mode} (muted/bypassed)")
        # Skip certain node types (defined in comfyui_node_configs.py)
        elif node_type in SKIP_NODE_TYPES or node_type is None:
            skipped_node_ids.add(node_id)

    print(f"Skipped node IDs: {skipped_node_ids}")

    # Build link lookup: link_id -> (from_node_id, from_slot)
    link_map = {}
    for link in links:
        # link format: [link_id, from_node, from_slot, to_node, to_slot, type]
        if len(link) >= 5:
            link_id = link[0]
            from_node = link[1]
            from_slot = link[2]
            link_map[link_id] = (from_node, from_slot)

    api_workflow = {}

    for node in nodes:
        node_id = str(node.get('id'))
        node_type = node.get('type')
        widgets_values = node.get('widgets_values', [])
        inputs_spec = node.get('inputs', [])  # Input slot definitions

        # Skip nodes already identified in first pass (muted/bypassed/skip types)
        if node.get('id') in skipped_node_ids:
            continue

        # Build inputs dict
        inputs = {}

        # First, handle connected inputs (from links)
        for input_spec in inputs_spec:
            input_name = input_spec.get('name')
            link_id = input_spec.get('link')

            if link_id is not None and link_id in link_map:
                from_node, from_slot = link_map[link_id]
                # Skip links that reference skipped/muted nodes
                if from_node in skipped_node_ids:
                    print(f"Removing input '{input_name}' from node {node_id} ({node_type}) - references skipped node {from_node}")
                    continue
                # Reference format: [node_id, slot_index]
                inputs[input_name] = [str(from_node), from_slot]

        # Then, handle widget values
        # Widget values are stored in order of the node's widget definitions
        # We use a multi-tier approach to discover widget names:
        # 1. Auto-extract from workflow's inputs array (most reliable)
        # 2. Fall back to manual WIDGET_MAPPINGS (for edge cases)
        # 3. Warn if both fail

        if widgets_values:
            # Tier 1: Try to extract widget names from the node's inputs array
            widget_names = _extract_widget_names_from_node(node)

            # Tier 2: Check if this is a subgraph node (UUID type) with definition
            if widget_names is None and node_type in subgraph_widgets:
                widget_names = subgraph_widgets[node_type]
                # Subgraph widgets might have extra None values for connected inputs
                # Pad with None if needed
                while len(widget_names) < len(widgets_values):
                    widget_names = [None] + widget_names  # Prepend None for linked inputs

            # Tier 3: Fall back to manual mappings if auto-extraction failed
            if widget_names is None:
                widget_names = WIDGET_MAPPINGS.get(node_type, None)
                if widget_names is not None:
                    print(f"Using manual mapping for '{node_type}' (no widget info in workflow)")

            # Apply widget values using discovered names
            if widget_names is not None:
                for i, widget_name in enumerate(widget_names):
                    # Skip None entries (placeholder for control_after_generate or button widgets)
                    if widget_name is None:
                        continue
                    if i < len(widgets_values) and widget_name not in inputs:
                        inputs[widget_name] = widgets_values[i]
            else:
                # Tier 3: No widget info available - warn but continue
                print(f"Warning: Unknown node type '{node_type}' with {len(widgets_values)} widget values - widget names could not be auto-discovered")

        api_workflow[node_id] = {
            'class_type': node_type,
            'inputs': inputs
        }

        # Add _meta if node has a title
        if node.get('title'):
            api_workflow[node_id]['_meta'] = {'title': node['title']}

    return api_workflow
