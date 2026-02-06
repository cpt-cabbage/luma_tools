"""
ComfyUI Workflow Loading and Format Conversion.

Handles loading workflow JSON files and converting between UI/nodes format
and API format used by ComfyUI's API.
"""

import os
import logging
from typing import Dict, Any, List, Optional

from comfyui.node_configs import WIDGET_MAPPINGS, SKIP_NODE_TYPES
from core.utils import ensure_directory, load_json, save_json

logger = logging.getLogger(__name__)


def load_workflow(workflow_path: str) -> Dict[str, Any]:
    """
    Load ComfyUI workflow JSON from file.

    Args:
        workflow_path: Path to workflow JSON file

    Returns:
        Workflow dictionary
    """
    return load_json(workflow_path, {})


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

    ensure_directory(output_dir)

    # Generate unique job ID if not provided
    if not job_id:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        job_id = f"{timestamp}_{unique_suffix}"

    workflow_filename = f"comfyui_workflow_{job_id}.json"
    workflow_path = os.path.join(output_dir, workflow_filename)

    save_json(workflow_path, workflow)

    logger.info(f"Saved modified workflow to: {workflow_path}")
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


def _is_uuid(value: Any) -> bool:
    """Check if a value looks like a UUID (subgraph type identifier)."""
    if not isinstance(value, str):
        return False
    # UUID format: 8-4-4-4-12 hex characters
    import re
    return bool(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', value.lower()))


def _get_subgraph_definitions(workflow: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Get subgraph definitions from workflow, indexed by UUID.

    Args:
        workflow: Workflow dictionary

    Returns:
        Dict mapping subgraph UUID -> subgraph definition
    """
    definitions = workflow.get('definitions', {})
    subgraphs = definitions.get('subgraphs', [])
    return {sg['id']: sg for sg in subgraphs if sg.get('id')}


def _normalize_link(link: Any) -> Optional[List]:
    """
    Normalize a link to list format [link_id, from_node, from_slot, to_node, to_slot, type].

    Links can be stored as:
    - List/tuple: [link_id, from_node, from_slot, to_node, to_slot, type]
    - Dict with string keys: {"id": ..., "origin_id": ..., ...}
    - Dict with int keys: {0: link_id, 1: from_node, ...}

    Returns:
        Normalized link as list, or None if invalid
    """
    if link is None:
        return None

    # Already a list/tuple
    if isinstance(link, (list, tuple)):
        return list(link)

    # Dictionary format
    if isinstance(link, dict):
        # Try integer keys first (common in some JSON serializations)
        if 0 in link or '0' in link:
            link_id = link.get(0) or link.get('0')
            from_node = link.get(1) or link.get('1')
            from_slot = link.get(2) or link.get('2') or 0
            to_node = link.get(3) or link.get('3')
            to_slot = link.get(4) or link.get('4') or 0
            link_type = link.get(5) or link.get('5') or '*'

            if link_id is not None and from_node is not None and to_node is not None:
                return [link_id, from_node, from_slot, to_node, to_slot, link_type]

        # Try string key naming conventions
        link_id = link.get('id') or link.get('link_id')
        from_node = link.get('origin_id') or link.get('from_node')
        from_slot = link.get('origin_slot') or link.get('from_slot') or 0
        to_node = link.get('target_id') or link.get('to_node')
        to_slot = link.get('target_slot') or link.get('to_slot') or 0
        link_type = link.get('type') or '*'

        if link_id is not None and from_node is not None and to_node is not None:
            return [link_id, from_node, from_slot, to_node, to_slot, link_type]

    return None


def _apply_boundary_overrides(
    widget_name: str,
    widget_value: Any,
    sg_input_idx: int,
    boundary_input_map: Dict[int, List],
    node_id_map: Dict[int, int],
    new_nodes: List[Dict[str, Any]],
) -> int:
    """
    Apply _input_overrides to all internal target nodes for a boundary input.

    When a subgraph boundary input has a widget value (from the parent node's
    widgets_values), this propagates it to every internal node that receives
    that boundary input — not just one.

    Args:
        widget_name: Fallback name for the override key
        widget_value: The value to set
        sg_input_idx: The subgraph input slot index (key into boundary_input_map)
        boundary_input_map: slot -> list of (internal_node, internal_slot, link)
        node_id_map: old internal node ID -> remapped node ID
        new_nodes: The list of remapped internal nodes being built

    Returns:
        Number of overrides applied
    """
    targets = boundary_input_map.get(sg_input_idx, [])
    applied = 0
    for int_to_node, int_to_slot, _il in targets:
        target_remapped = node_id_map.get(int_to_node)
        if target_remapped is None:
            continue
        for new_node in new_nodes:
            if new_node['id'] == target_remapped:
                target_inputs = new_node.get('inputs', [])
                input_name = None
                for ti_idx, ti in enumerate(target_inputs):
                    slot_idx = ti.get('slot_index', ti_idx)
                    if slot_idx == int_to_slot:
                        input_name = ti.get('name', widget_name)
                        break
                if input_name is None:
                    input_name = widget_name
                overrides = new_node.setdefault('_input_overrides', {})
                overrides[input_name] = widget_value
                applied += 1
                logger.debug(
                    f"    Override (boundary): node {target_remapped} "
                    f"input '{input_name}' = {repr(widget_value)[:60]}"
                )
                break
    return applied


def expand_subgraphs(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expand all subgraph/component nodes into their constituent nodes.

    ComfyUI components/subgraphs are groups of nodes packaged together with a UUID
    as their type. This function expands them so the workflow can be executed via API.

    Args:
        workflow: Workflow in UI/nodes format (with 'nodes' array)

    Returns:
        Workflow with all subgraphs expanded into individual nodes
    """
    import copy

    # Only process UI format workflows
    if 'nodes' not in workflow:
        return workflow

    subgraph_defs = _get_subgraph_definitions(workflow)
    if not subgraph_defs:
        return workflow  # No subgraphs to expand

    # Check if any nodes use subgraph types
    nodes = workflow.get('nodes', [])
    subgraph_nodes = [n for n in nodes if _is_uuid(n.get('type')) and n.get('type') in subgraph_defs]

    if not subgraph_nodes:
        return workflow  # No subgraph instances to expand

    logger.info(f"Expanding {len(subgraph_nodes)} subgraph node(s)...")

    # Deep copy to avoid modifying original
    expanded = copy.deepcopy(workflow)
    expanded_nodes = expanded.get('nodes', [])
    expanded_links = expanded.get('links', [])

    # Normalize all links to list format
    expanded_links = [_normalize_link(l) for l in expanded_links]
    expanded_links = [l for l in expanded_links if l is not None]
    expanded['links'] = expanded_links

    # Track ID offsets to avoid collisions
    max_node_id = max((n.get('id', 0) for n in expanded_nodes), default=0)
    max_link_id = max((l[0] for l in expanded_links if l), default=0)

    # Build lookup for existing links: link_id -> link data
    # link format: [link_id, from_node, from_slot, to_node, to_slot, type]
    link_lookup = {link[0]: link for link in expanded_links if link}

    # Process each subgraph node
    nodes_to_remove = set()
    new_nodes = []
    new_links = []

    for sg_node in subgraph_nodes:
        sg_node_id = sg_node.get('id')
        sg_type = sg_node.get('type')
        sg_def = subgraph_defs.get(sg_type)

        if not sg_def:
            logger.warning(f"  Subgraph definition not found for {sg_type}")
            continue

        logger.debug(f"  Expanding subgraph node {sg_node_id} (type: {sg_type[:8]}...)")
        nodes_to_remove.add(sg_node_id)

        # Get subgraph internal structure
        sg_internal_nodes = sg_def.get('nodes', [])
        sg_internal_links_raw = sg_def.get('links', [])
        sg_inputs = sg_def.get('inputs', [])  # External inputs
        sg_outputs = sg_def.get('outputs', [])  # External outputs

        # Normalize internal links to list format
        sg_internal_links = [_normalize_link(l) for l in sg_internal_links_raw]
        sg_internal_links = [l for l in sg_internal_links if l is not None]

        # Create ID mappings for this subgraph instance
        node_id_map = {}  # old_internal_id -> new_id
        link_id_map = {}  # old_internal_link_id -> new_link_id

        # Assign new IDs to internal nodes
        logger.debug(f"    Remapping {len(sg_internal_nodes)} internal nodes (starting from ID {max_node_id + 1}):")
        for internal_node in sg_internal_nodes:
            old_id = internal_node.get('id')
            node_type = internal_node.get('type', 'unknown')
            max_node_id += 1
            node_id_map[old_id] = max_node_id
            logger.debug(f"      {node_type}: {old_id} -> {max_node_id}")

        # Assign new IDs to internal links
        for internal_link in sg_internal_links:
            old_link_id = internal_link[0]
            max_link_id += 1
            link_id_map[old_link_id] = max_link_id

        # Create remapped internal nodes
        for internal_node in sg_internal_nodes:
            new_node = copy.deepcopy(internal_node)
            old_id = internal_node.get('id')
            new_node['id'] = node_id_map[old_id]

            # Update input links to use new link IDs
            # Clear unmapped links (boundary connections will be rewired later)
            if 'inputs' in new_node:
                for inp in new_node['inputs']:
                    if inp.get('link') is not None:
                        old_link = inp['link']
                        if old_link in link_id_map:
                            inp['link'] = link_id_map[old_link]
                        else:
                            # Clear unmapped link - will be rewired via external connections
                            inp['link'] = None

            # Update output links to use new link IDs
            # Only include links that are mapped (skip boundary links)
            if 'outputs' in new_node:
                for out in new_node['outputs']:
                    if out.get('links'):
                        out['links'] = [
                            link_id_map[l] for l in out['links']
                            if l in link_id_map
                        ]

            new_nodes.append(new_node)

        # Create remapped internal links
        # Skip links that reference boundary nodes (negative IDs or unmapped IDs)
        logger.debug(f"    Processing {len(sg_internal_links)} internal links:")
        for internal_link in sg_internal_links:
            # link format: [link_id, from_node, from_slot, to_node, to_slot, type]
            from_node_id = internal_link[1]
            to_node_id = internal_link[3]

            # Skip boundary links (negative IDs are subgraph input/output references)
            if from_node_id not in node_id_map or to_node_id not in node_id_map:
                logger.debug(f"      Link {internal_link[0]}: {from_node_id} -> {to_node_id} (SKIPPED - boundary)")
                continue

            new_link = list(internal_link)
            new_link[0] = link_id_map[internal_link[0]]
            new_link[1] = node_id_map[from_node_id]
            new_link[3] = node_id_map[to_node_id]
            new_links.append(new_link)
            logger.debug(f"      Link {internal_link[0]}->{new_link[0]}: {from_node_id}->{new_link[1]} slot {internal_link[2]} -> {to_node_id}->{new_link[3]} slot {internal_link[4]}")

        # Handle external connections TO the subgraph (inputs)
        # The subgraph node's inputs connect to internal nodes
        # Find boundary links: links where from_node is negative (boundary input marker)
        # These indicate connections from external inputs to internal nodes
        sg_node_inputs = sg_node.get('inputs', [])
        logger.debug(f"    Processing {len(sg_inputs)} subgraph inputs, {len(sg_node_inputs)} connected inputs")

        # Build map of boundary input slot -> LIST of (internal_node, internal_slot, link)
        # Boundary inputs use negative from_node IDs (e.g., -1, -2, etc.)
        # The from_slot indicates which subgraph input slot
        # IMPORTANT: Multiple internal nodes can need the same external input!
        boundary_input_map = {}
        for il in sg_internal_links:
            from_node = il[1]
            if isinstance(from_node, int) and from_node < 0:
                # This is a boundary input link
                from_slot = il[2]  # The subgraph input slot
                to_node = il[3]    # The internal node receiving the input
                to_slot = il[4]    # The input slot on the internal node
                if from_slot not in boundary_input_map:
                    boundary_input_map[from_slot] = []
                boundary_input_map[from_slot].append((to_node, to_slot, il))
                logger.debug(f"    Found boundary input: slot {from_slot} -> internal node {to_node} slot {to_slot}")

        for i, sg_input_def in enumerate(sg_inputs):
            input_name = sg_input_def.get('name', f'input_{i}')
            # Find the external link connecting to this subgraph input
            ext_link_id = None
            if i < len(sg_node_inputs):
                ext_link_id = sg_node_inputs[i].get('link')

            if ext_link_id is None:
                logger.debug(f"    Input {i} ({input_name}): no external link connected")
                continue

            # Get all internal targets for this input
            # First try: use the link field from the input definition
            internal_targets = []
            internal_link_id = sg_input_def.get('link')
            if internal_link_id is not None:
                for il in sg_internal_links:
                    if il[0] == internal_link_id:
                        internal_targets.append((il[3], il[4], il))
                        break

            # Second try: use boundary input map by slot index (may have multiple targets)
            if not internal_targets and i in boundary_input_map:
                internal_targets = boundary_input_map[i]
                logger.debug(f"    Input {i} ({input_name}): using boundary map -> {len(internal_targets)} target(s)")

            if not internal_targets:
                logger.debug(f"    Input {i} ({input_name}): no internal targets found")
                continue

            # Get the external link info for creating additional links
            ext_link_info = link_lookup.get(ext_link_id)
            if not ext_link_info:
                logger.warning(f"    Input {i} ({input_name}): external link {ext_link_id} not found in link_lookup")
                continue

            # Find the external link to get source info
            ext_link_data = None
            for link in expanded_links:
                if link[0] == ext_link_id:
                    ext_link_data = link
                    break

            # Process each internal target
            for target_idx, (internal_to_node, internal_to_slot, internal_link) in enumerate(internal_targets):
                target_node_id = node_id_map.get(internal_to_node)
                target_slot = internal_to_slot

                if target_node_id is None:
                    logger.warning(f"    Input {i} ({input_name}): target node {internal_to_node} not in node_id_map")
                    continue

                if target_idx == 0:
                    # First target: rewire the existing external link
                    if ext_link_data:
                        old_target = ext_link_data[3]
                        ext_link_data[3] = target_node_id
                        ext_link_data[4] = target_slot
                        logger.debug(f"    Rewired external link {ext_link_id}: target {old_target} -> {target_node_id}")
                    current_link_id = ext_link_id
                else:
                    # Additional targets: create new links from the same source
                    max_link_id += 1
                    new_link = [
                        max_link_id,
                        ext_link_data[1],  # Same source node
                        ext_link_data[2],  # Same source slot
                        target_node_id,
                        target_slot,
                        ext_link_data[5] if len(ext_link_data) > 5 else '*'
                    ]
                    new_links.append(new_link)
                    current_link_id = max_link_id
                    logger.debug(f"    Created new link {max_link_id} for additional target: -> node {target_node_id} slot {target_slot}")

                # Update the target internal node's input
                found_input = False
                for new_node in new_nodes:
                    if new_node['id'] == target_node_id:
                        for inp in new_node.get('inputs', []):
                            # Find input by slot index or by matching name
                            slot_match = inp.get('slot_index') == target_slot
                            index_match = 'slot_index' not in inp and new_node.get('inputs', []).index(inp) == target_slot
                            if slot_match or index_match:
                                inp['link'] = current_link_id
                                found_input = True
                                logger.debug(f"    Updated internal node {target_node_id} input slot {target_slot}: link={current_link_id}")
                                break
                        break
                if not found_input:
                    logger.warning(f"    Could not find input slot {target_slot} on node {target_node_id}")

        # Handle external connections FROM the subgraph (outputs)
        # Other nodes that were connected to the subgraph's outputs need rewiring
        # Build map of boundary output slot -> (internal_source_node, internal_source_slot)
        # Boundary outputs use negative to_node IDs (e.g., -20, -21, etc.)
        # The to_slot indicates which subgraph output slot
        boundary_output_map = {}
        for il in sg_internal_links:
            to_node = il[3]
            if isinstance(to_node, int) and to_node < 0:
                # This is a boundary output link
                from_node = il[1]    # The internal node providing the output
                from_slot = il[2]    # The output slot on the internal node
                to_slot = il[4]      # The subgraph output slot
                boundary_output_map[to_slot] = (from_node, from_slot, il)
                logger.debug(f"    Found boundary output: internal node {from_node} slot {from_slot} -> output slot {to_slot}")

        sg_node_outputs = sg_node.get('outputs', [])
        logger.debug(f"    Processing {len(sg_outputs)} subgraph outputs, {len(sg_node_outputs)} connected outputs")

        for i, sg_output_def in enumerate(sg_outputs):
            output_name = sg_output_def.get('name', f'output_{i}')

            # Get the source internal node and slot
            source_internal_node = None
            source_slot = None

            # First try: use the link field from the output definition
            internal_link_id = sg_output_def.get('link')
            if internal_link_id is not None:
                for il in sg_internal_links:
                    if il[0] == internal_link_id:
                        source_internal_node = il[1]
                        source_slot = il[2]
                        logger.debug(f"    Output {i} ({output_name}): found via link {internal_link_id}")
                        break

            # Second try: use boundary output map by slot index
            if source_internal_node is None and i in boundary_output_map:
                source_internal_node, source_slot, _ = boundary_output_map[i]
                logger.debug(f"    Output {i} ({output_name}): using boundary map -> node {source_internal_node} slot {source_slot}")

            if source_internal_node is None:
                logger.debug(f"    Output {i} ({output_name}): no internal source found")
                continue

            # Map to remapped node ID
            source_node_id = node_id_map.get(source_internal_node)
            if source_node_id is None:
                logger.warning(f"    Output {i} ({output_name}): internal node {source_internal_node} not in node_id_map")
                continue

            # Find all external links that were connected to this subgraph output
            if i < len(sg_node_outputs):
                output_links = sg_node_outputs[i].get('links', [])
                logger.debug(f"    Output {i} ({output_name}): {len(output_links) if output_links else 0} external links to rewire")

                if output_links:
                    for ext_link_id in output_links:
                        if ext_link_id in link_lookup:
                            # Update the link's source to the internal node
                            for link in expanded_links:
                                if link[0] == ext_link_id:
                                    old_from = link[1]
                                    link[1] = source_node_id
                                    link[2] = source_slot
                                    logger.debug(f"    Rewired external output link {ext_link_id}: source {old_from} -> {source_node_id}")
                                    break

                            # Update the source internal node's output
                            for new_node in new_nodes:
                                if new_node['id'] == source_node_id:
                                    for out in new_node.get('outputs', []):
                                        if out.get('slot_index') == source_slot or (
                                            'slot_index' not in out and new_node.get('outputs', []).index(out) == source_slot
                                        ):
                                            if 'links' not in out or out['links'] is None:
                                                out['links'] = []
                                            if ext_link_id not in out['links']:
                                                out['links'].append(ext_link_id)
                                            break
                                    break

        # Handle widgets_values from the subgraph node
        # These need to be applied to the appropriate internal nodes via _input_overrides
        sg_widgets_values = sg_node.get('widgets_values', [])
        sg_properties = sg_node.get('properties', {})
        sg_proxy_widgets = sg_properties.get('proxyWidgets', [])

        # Check if widgets_values is dict format (for subgraphs, list format is standard)
        sg_widgets_values_is_dict = isinstance(sg_widgets_values, dict)
        if sg_widgets_values_is_dict:
            logger.info(f"Subgraph node {sg_node_id} uses dict widgets_values format")
            # For dict format, we'll handle it differently below
        elif not isinstance(sg_widgets_values, list):
            logger.warning(f"Subgraph node {sg_node_id} has unexpected widgets_values type: {type(sg_widgets_values)} - resetting to empty list")
            sg_widgets_values = []

        if sg_widgets_values and sg_proxy_widgets and not sg_widgets_values_is_dict:
            # Use proxyWidgets for precise mapping:
            # Each entry is [node_id_str, widget_name] mapping to widgets_values[idx]
            for idx, proxy_entry in enumerate(sg_proxy_widgets):
                if not isinstance(proxy_entry, (list, tuple)) or len(proxy_entry) < 2:
                    continue
                if idx >= len(sg_widgets_values):
                    break

                proxy_node_id_str, widget_name = proxy_entry[0], proxy_entry[1]
                widget_value = sg_widgets_values[idx]

                # Skip phantom widgets
                if widget_name == 'control_after_generate':
                    continue

                if proxy_node_id_str == "-1":
                    # Boundary input — find the sg_input index by name, then
                    # use boundary_input_map to propagate to ALL target nodes
                    sg_input_idx = None
                    for si_idx, sg_inp in enumerate(sg_inputs):
                        if sg_inp.get('name') == widget_name:
                            sg_input_idx = si_idx
                            break

                    if sg_input_idx is not None:
                        _apply_boundary_overrides(
                            widget_name, widget_value, sg_input_idx,
                            boundary_input_map, node_id_map, new_nodes,
                        )
                    else:
                        logger.debug(f"    Boundary widget '{widget_name}': no matching sg_input found")
                else:
                    # Internal node widget — find the expanded node by original ID
                    try:
                        internal_id = int(proxy_node_id_str)
                    except (ValueError, TypeError):
                        continue
                    target_remapped = node_id_map.get(internal_id)
                    if target_remapped is not None:
                        for new_node in new_nodes:
                            if new_node['id'] == target_remapped:
                                overrides = new_node.setdefault('_input_overrides', {})
                                overrides[widget_name] = widget_value
                                logger.debug(f"    Override (internal): node {target_remapped} widget '{widget_name}' = {repr(widget_value)[:60]}")
                                break

        elif sg_widgets_values and sg_inputs and not sg_widgets_values_is_dict:
            # Fallback: no proxyWidgets — map via subgraph input definitions
            for i, sg_input_def in enumerate(sg_inputs):
                if i >= len(sg_widgets_values):
                    break

                widget_value = sg_widgets_values[i]
                internal_link_id = sg_input_def.get('link')
                input_name = sg_input_def.get('name', f'input_{i}')

                if internal_link_id is None:
                    # link field is null — use boundary_input_map to find targets
                    _apply_boundary_overrides(
                        input_name, widget_value, i,
                        boundary_input_map, node_id_map, new_nodes,
                    )
                    continue

                _apply_boundary_overrides(
                    input_name, widget_value, i,
                    boundary_input_map, node_id_map, new_nodes,
                )

        elif sg_widgets_values_is_dict:
            # Dict format: use proxyWidgets to map widget names to internal nodes
            if sg_proxy_widgets:
                for proxy_entry in sg_proxy_widgets:
                    if not isinstance(proxy_entry, (list, tuple)) or len(proxy_entry) < 2:
                        continue
                    proxy_node_id_str, widget_name = proxy_entry[0], proxy_entry[1]

                    # Look up value by widget name in dict
                    if widget_name not in sg_widgets_values:
                        continue
                    widget_value = sg_widgets_values[widget_name]

                    # Skip phantom widgets
                    if widget_name == 'control_after_generate':
                        continue

                    # Apply to internal node
                    if proxy_node_id_str != "-1":
                        try:
                            internal_id = int(proxy_node_id_str)
                        except (ValueError, TypeError):
                            continue
                        target_remapped = node_id_map.get(internal_id)
                        if target_remapped is not None:
                            for new_node in new_nodes:
                                if new_node['id'] == target_remapped:
                                    overrides = new_node.setdefault('_input_overrides', {})
                                    overrides[widget_name] = widget_value
                                    logger.debug(f"    Override (dict): node {target_remapped} widget '{widget_name}' = {repr(widget_value)[:60]}")
                                    break
                    else:
                        # Boundary input (dict format) — find sg_input index by name
                        sg_input_idx = None
                        for si_idx, sg_inp in enumerate(sg_inputs):
                            if sg_inp.get('name') == widget_name:
                                sg_input_idx = si_idx
                                break
                        if sg_input_idx is not None:
                            _apply_boundary_overrides(
                                widget_name, widget_value, sg_input_idx,
                                boundary_input_map, node_id_map, new_nodes,
                            )
            else:
                # No proxyWidgets - apply dict values directly to matching widget names in internal nodes
                for new_node in new_nodes:
                    for widget_name, widget_value in sg_widgets_values.items():
                        if widget_name in ('videopreview', 'audiopreview'):
                            continue
                        overrides = new_node.setdefault('_input_overrides', {})
                        if widget_name not in overrides:
                            overrides[widget_name] = widget_value

    # Remove subgraph nodes and add expanded nodes
    expanded['nodes'] = [n for n in expanded_nodes if n.get('id') not in nodes_to_remove]
    expanded['nodes'].extend(new_nodes)
    expanded['links'] = expanded_links + new_links

    # Recursively expand in case of nested subgraphs
    if any(_is_uuid(n.get('type')) and n.get('type') in subgraph_defs
           for n in expanded['nodes']):
        logger.debug("  Checking for nested subgraphs...")
        return expand_subgraphs(expanded)

    logger.info(f"  Expansion complete: {len(expanded['nodes'])} nodes, {len(expanded['links'])} links")
    return expanded


def convert_to_api_format(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert UI/nodes format workflow to API format.

    UI format has 'nodes' array with widgets_values.
    API format has node IDs as keys with 'inputs' dict.

    Automatically expands subgraph/component nodes before conversion.

    Args:
        workflow: Workflow in UI/nodes format

    Returns:
        Workflow in API format
    """
    if is_api_format(workflow):
        return workflow  # Already in API format

    # Expand subgraphs before conversion
    workflow = expand_subgraphs(workflow)

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
            logger.info(f"Will skip node {node_id} ({node_type}) - mode {node_mode} (muted/bypassed)")
        # Skip certain node types (defined in comfyui_node_configs.py)
        elif node_type in SKIP_NODE_TYPES or node_type is None:
            skipped_node_ids.add(node_id)

    logger.info(f"Skipped node IDs: {skipped_node_ids}")

    # Build set of valid node IDs for validation
    valid_node_ids = set(node.get('id') for node in nodes if node.get('id') is not None)

    # Build link lookup: link_id -> (from_node_id, from_slot)
    # Only include links that reference valid nodes
    link_map = {}
    for link in links:
        # link format: [link_id, from_node, from_slot, to_node, to_slot, type]
        if len(link) >= 5:
            link_id = link[0]
            from_node = link[1]
            from_slot = link[2]
            to_node = link[3]
            # Skip links that reference non-existent nodes
            if from_node not in valid_node_ids:
                logger.info(f"Skipping link {link_id}: from_node {from_node} not in valid nodes")
                continue
            if to_node not in valid_node_ids:
                logger.info(f"Skipping link {link_id}: to_node {to_node} not in valid nodes")
                continue
            link_map[link_id] = (from_node, from_slot)

    # Resolve links through skipped (muted/bypassed) nodes.
    # Muted nodes act as pass-through: output slot N comes from input slot N.
    # Build input-slot-to-link mapping for skipped nodes so we can trace upstream.
    if skipped_node_ids:
        _skipped_input_links = {}  # node_id -> {input_slot: link_id}
        for node in nodes:
            nid = node.get('id')
            if nid not in skipped_node_ids:
                continue
            slot_map = {}
            for inp_spec in node.get('inputs', []):
                slot_idx = inp_spec.get('slot_index',
                                        node.get('inputs', []).index(inp_spec))
                lid = inp_spec.get('link')
                if lid is not None:
                    slot_map[slot_idx] = lid
            _skipped_input_links[nid] = slot_map

        def _resolve_source(from_node, from_slot, visited=None):
            """Trace through skipped nodes to find the real upstream source."""
            if visited is None:
                visited = set()
            if from_node not in skipped_node_ids or from_node in visited:
                return from_node, from_slot
            visited.add(from_node)
            upstream_link = _skipped_input_links.get(from_node, {}).get(from_slot)
            if upstream_link is not None and upstream_link in link_map:
                up_node, up_slot = link_map[upstream_link]
                return _resolve_source(up_node, up_slot, visited)
            return None, None  # No pass-through found

        for link_id in list(link_map.keys()):
            from_node, from_slot = link_map[link_id]
            if from_node in skipped_node_ids:
                resolved_node, resolved_slot = _resolve_source(from_node, from_slot)
                if resolved_node is not None:
                    link_map[link_id] = (resolved_node, resolved_slot)
                    logger.debug(f"Resolved link {link_id} through muted node(s): "
                                 f"{from_node}:{from_slot} -> {resolved_node}:{resolved_slot}")
                else:
                    del link_map[link_id]
                    logger.debug(f"Removed link {link_id}: can't resolve through "
                                 f"muted node {from_node}")

    api_workflow = {}
    from comfyui.node_info import get_widget_names as _get_ni_widget_names

    for node in nodes:
        node_id = str(node.get('id'))
        node_type = node.get('type')
        widgets_values = node.get('widgets_values', [])
        inputs_spec = node.get('inputs', [])  # Input slot definitions

        # Detect widgets_values format: dict (named) or list (indexed)
        widgets_values_is_dict = isinstance(widgets_values, dict)
        if not widgets_values_is_dict and not isinstance(widgets_values, list):
            logger.warning(f"Node {node_id} ({node_type}) has unexpected widgets_values type: {type(widgets_values)} - resetting to empty list")
            widgets_values = []
            widgets_values_is_dict = False

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
                    logger.info(f"Removing input '{input_name}' from node {node_id} ({node_type}) - references skipped node {from_node}")
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
            if widgets_values_is_dict:
                # Dict format: keys are widget names, values are widget values
                # Apply directly to inputs (skip keys that are internal/hidden)
                for widget_name, widget_value in widgets_values.items():
                    # Skip internal keys like videopreview/audiopreview (UI state, not actual inputs)
                    if widget_name in ('videopreview', 'audiopreview'):
                        continue
                    # Only add if not already connected via link
                    if widget_name not in inputs:
                        inputs[widget_name] = widget_value
            else:
                # List format: need to map indices to widget names
                # Tier 1: Try to extract widget names from the node's inputs array
                widget_names = _extract_widget_names_from_node(node)

                # Tier 2: Check if this is a subgraph node (UUID type) with definition
                if widget_names is None and node_type in subgraph_widgets:
                    widget_names = subgraph_widgets[node_type]
                    # Subgraph widgets might have extra None values for connected inputs
                    # Pad with None if needed
                    while len(widget_names) < len(widgets_values):
                        widget_names = [None] + widget_names  # Prepend None for linked inputs

                # Tier 3: Try node_info cache (auto-discovered from /object_info)
                if widget_names is None:
                    widget_names = _get_ni_widget_names(node_type)
                    if widget_names is not None:
                        logger.info(f"Using node_info cache for '{node_type}'")

                # Tier 4: Fall back to manual mappings if auto-extraction failed
                if widget_names is None:
                    widget_names = WIDGET_MAPPINGS.get(node_type, None)
                    if widget_names is not None:
                        logger.info(f"Using manual mapping for '{node_type}' (no widget info in workflow)")

                # Apply widget values using discovered names
                if widget_names is not None:
                    for i, widget_name in enumerate(widget_names):
                        # Skip None entries (placeholder for control_after_generate or button widgets)
                        if widget_name is None:
                            continue
                        if i < len(widgets_values) and widget_name not in inputs:
                            inputs[widget_name] = widgets_values[i]
                else:
                    # No widget info from any source - warn but continue
                    logger.warning(f"Unknown node type '{node_type}' with {len(widgets_values)} widget values - widget names could not be auto-discovered")

        # Apply _input_overrides from subgraph expansion (widget values propagated
        # from the parent subgraph node to its expanded internal nodes).
        # Overrides take precedence over widget values (which are stale defaults
        # from the subgraph definition) but must NOT replace link connections.
        overrides = node.get('_input_overrides', {})
        for key, val in overrides.items():
            existing = inputs.get(key)
            # Skip if the existing value is a link reference [node_id_str, slot_index]
            if isinstance(existing, list):
                continue
            inputs[key] = val

        api_workflow[node_id] = {
            'class_type': node_type,
            'inputs': inputs
        }

        # Add _meta if node has a title
        if node.get('title'):
            api_workflow[node_id]['_meta'] = {'title': node['title']}

    # Final validation: remove any input references to non-existent nodes
    valid_api_ids = set(api_workflow.keys())
    for node_id, node_data in api_workflow.items():
        inputs = node_data.get('inputs', {})
        invalid_inputs = []
        for input_name, input_value in inputs.items():
            # Check if it's a node reference [node_id, slot]
            if isinstance(input_value, list) and len(input_value) == 2:
                ref_node_id = str(input_value[0])
                if ref_node_id not in valid_api_ids:
                    logger.warning(f"Removing invalid input '{input_name}' from node {node_id}: references non-existent node {ref_node_id}")
                    invalid_inputs.append(input_name)
        for input_name in invalid_inputs:
            del inputs[input_name]

    return api_workflow
