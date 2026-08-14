"""
ComfyUI Workflow Loading and Format Conversion.

Handles loading workflow JSON files and converting between UI/nodes format
and API format used by ComfyUI's API.
"""

import os
import copy
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
        # Use explicit None checks to handle falsy values like 0 correctly
        if 0 in link or '0' in link:
            link_id = link.get(0) if link.get(0) is not None else link.get('0')
            from_node = link.get(1) if link.get(1) is not None else link.get('1')
            from_slot = link.get(2) if link.get(2) is not None else (link.get('2') if link.get('2') is not None else 0)
            to_node = link.get(3) if link.get(3) is not None else link.get('3')
            to_slot = link.get(4) if link.get(4) is not None else (link.get('4') if link.get('4') is not None else 0)
            link_type = link.get(5) if link.get(5) is not None else (link.get('5') if link.get('5') is not None else '*')

            if link_id is not None and from_node is not None and to_node is not None:
                return [link_id, from_node, from_slot, to_node, to_slot, link_type]

        # Try string key naming conventions
        # Use explicit None checks to handle falsy values like 0 correctly
        link_id = link.get('id') if link.get('id') is not None else link.get('link_id')
        from_node = link.get('origin_id') if link.get('origin_id') is not None else link.get('from_node')
        from_slot = link.get('origin_slot') if link.get('origin_slot') is not None else (link.get('from_slot') if link.get('from_slot') is not None else 0)
        to_node = link.get('target_id') if link.get('target_id') is not None else link.get('to_node')
        to_slot = link.get('target_slot') if link.get('target_slot') is not None else (link.get('to_slot') if link.get('to_slot') is not None else 0)
        link_type = link.get('type') if link.get('type') is not None else '*'

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


class _ExpansionContext:
    """Mutable bookkeeping shared by every subgraph instance in one pass.

    ``expanded_links`` is the live link list of the workflow being built —
    external links are rewired *in place* inside it. ``new_nodes`` /
    ``new_links`` accumulate everything the expansion adds, and the two
    counters hand out collision-free IDs across all subgraph instances.
    """

    __slots__ = ('expanded_links', 'link_lookup', 'max_node_id', 'max_link_id',
                 'new_nodes', 'new_links', 'nodes_to_remove')

    def __init__(self, expanded_links, link_lookup, max_node_id, max_link_id):
        self.expanded_links = expanded_links
        self.link_lookup = link_lookup
        self.max_node_id = max_node_id
        self.max_link_id = max_link_id
        self.new_nodes = []
        self.new_links = []
        self.nodes_to_remove = set()


def _allocate_subgraph_ids(ctx, sg_internal_nodes, sg_internal_links):
    """Hand out fresh workflow-wide IDs for one subgraph instance.

    Args:
        ctx: Expansion context whose ID counters are advanced.
        sg_internal_nodes: Node dicts from the subgraph definition.
        sg_internal_links: Normalized link lists from the subgraph definition.

    Returns:
        Tuple of (node_id_map, link_id_map) mapping definition-local IDs to the
        newly allocated workflow-wide IDs.
    """
    node_id_map = {}
    logger.debug(f"    Remapping {len(sg_internal_nodes)} internal nodes "
                 f"(starting from ID {ctx.max_node_id + 1}):")
    for internal_node in sg_internal_nodes:
        old_id = internal_node.get('id')
        node_type = internal_node.get('type', 'unknown')
        ctx.max_node_id += 1
        node_id_map[old_id] = ctx.max_node_id
        logger.debug(f"      {node_type}: {old_id} -> {ctx.max_node_id}")

    link_id_map = {}
    for internal_link in sg_internal_links:
        ctx.max_link_id += 1
        link_id_map[internal_link[0]] = ctx.max_link_id

    return node_id_map, link_id_map


def _remap_subgraph_nodes(sg_internal_nodes, node_id_map, link_id_map):
    """Copy a subgraph's internal nodes with their IDs and link IDs remapped.

    Links that are not in ``link_id_map`` are boundary connections: input links
    are cleared (rewired later by :func:`_wire_external_inputs`) and output
    links are dropped from the node's ``links`` list.

    Args:
        sg_internal_nodes: Node dicts from the subgraph definition.
        node_id_map: definition-local node ID -> new node ID.
        link_id_map: definition-local link ID -> new link ID.

    Returns:
        List of deep-copied, remapped node dicts.
    """
    remapped = []
    for internal_node in sg_internal_nodes:
        new_node = copy.deepcopy(internal_node)
        new_node['id'] = node_id_map[internal_node.get('id')]

        if 'inputs' in new_node:
            for inp in new_node['inputs']:
                if inp.get('link') is not None:
                    # .get() yields None for unmapped (boundary) links
                    inp['link'] = link_id_map.get(inp['link'])

        if 'outputs' in new_node:
            for out in new_node['outputs']:
                if out.get('links'):
                    out['links'] = [link_id_map[l] for l in out['links']
                                    if l in link_id_map]

        remapped.append(new_node)
    return remapped


def _remap_subgraph_links(sg_internal_links, node_id_map, link_id_map):
    """Copy a subgraph's internal links with node and link IDs remapped.

    Boundary links — those whose source or target is a negative (or otherwise
    unmapped) node ID — are dropped; they are re-created from the external
    wiring instead.

    Returns:
        List of remapped link lists in the standard 6-element format.
    """
    logger.debug(f"    Processing {len(sg_internal_links)} internal links:")
    remapped = []
    for internal_link in sg_internal_links:
        # link format: [link_id, from_node, from_slot, to_node, to_slot, type]
        from_node_id = internal_link[1]
        to_node_id = internal_link[3]

        if from_node_id not in node_id_map or to_node_id not in node_id_map:
            logger.debug(f"      Link {internal_link[0]}: {from_node_id} -> "
                         f"{to_node_id} (SKIPPED - boundary)")
            continue

        new_link = list(internal_link)
        new_link[0] = link_id_map[internal_link[0]]
        new_link[1] = node_id_map[from_node_id]
        new_link[3] = node_id_map[to_node_id]
        remapped.append(new_link)
        logger.debug(
            f"      Link {internal_link[0]}->{new_link[0]}: "
            f"{from_node_id}->{new_link[1]} slot {internal_link[2]} -> "
            f"{to_node_id}->{new_link[3]} slot {internal_link[4]}"
        )
    return remapped


def _build_boundary_input_map(sg_internal_links, sg_inputs):
    """Map each subgraph input slot to every internal node that consumes it.

    Boundary inputs are encoded as internal links with a negative ``from_node``
    (e.g. ``-10``); the ``from_slot`` is the subgraph input slot index. A single
    boundary input commonly fans out to several internal nodes (e.g. one
    ``ckpt_name`` feeding three loaders), so the value is a list.

    Returns:
        Dict of slot_index -> list of (internal_node, internal_slot, link).
    """
    boundary_input_map = {}
    for il in sg_internal_links:
        from_node = il[1]
        if not (isinstance(from_node, int) and from_node < 0):
            continue
        from_slot = il[2]   # The subgraph input slot
        to_node = il[3]     # The internal node receiving the input
        to_slot = il[4]     # The input slot on the internal node
        if from_slot < 0 or from_slot >= len(sg_inputs):
            logger.warning(f"    Boundary input slot {from_slot} out of range "
                           f"(subgraph has {len(sg_inputs)} inputs), skipping")
            continue
        boundary_input_map.setdefault(from_slot, []).append((to_node, to_slot, il))
        logger.debug(f"    Found boundary input: slot {from_slot} -> "
                     f"internal node {to_node} slot {to_slot}")
    return boundary_input_map


def _build_boundary_output_map(sg_internal_links):
    """Map each subgraph output slot to the internal node that produces it.

    Boundary outputs are encoded as internal links with a negative ``to_node``
    (e.g. ``-20``); the ``to_slot`` is the subgraph output slot index. Unlike
    inputs, an output slot has exactly one producer.

    Returns:
        Dict of slot_index -> (internal_node, internal_slot, link).
    """
    boundary_output_map = {}
    for il in sg_internal_links:
        to_node = il[3]
        if not (isinstance(to_node, int) and to_node < 0):
            continue
        from_node = il[1]   # The internal node providing the output
        from_slot = il[2]   # The output slot on the internal node
        to_slot = il[4]     # The subgraph output slot
        boundary_output_map[to_slot] = (from_node, from_slot, il)
        logger.debug(f"    Found boundary output: internal node {from_node} "
                     f"slot {from_slot} -> output slot {to_slot}")
    return boundary_output_map


def _resolve_input_targets(sg_input_def, sg_input_idx, sg_internal_links,
                           boundary_input_map):
    """Find the internal nodes fed by one subgraph input.

    Prefers the input definition's explicit ``link`` field (single target) and
    falls back to the boundary input map, which can name several targets.

    Returns:
        List of (internal_node, internal_slot, link) tuples (possibly empty).
    """
    internal_link_id = sg_input_def.get('link')
    if internal_link_id is not None:
        for il in sg_internal_links:
            if il[0] == internal_link_id:
                return [(il[3], il[4], il)]

    if sg_input_idx in boundary_input_map:
        targets = boundary_input_map[sg_input_idx]
        logger.debug(f"    Input {sg_input_idx}: using boundary map -> "
                     f"{len(targets)} target(s)")
        return targets

    return []


def _connect_input_target(ctx, target_idx, target_node_id, target_slot,
                          ext_link_id, ext_link_data):
    """Point one internal node's input at the subgraph's external source.

    The first target reuses (rewires) the original external link so link IDs
    stay stable; every additional target gets a freshly minted link from the
    same source node and slot.

    Returns:
        The link ID now feeding this target.
    """
    if target_idx == 0:
        if ext_link_data:
            old_target = ext_link_data[3]
            ext_link_data[3] = target_node_id
            ext_link_data[4] = target_slot
            logger.debug(f"    Rewired external link {ext_link_id}: "
                         f"target {old_target} -> {target_node_id}")
        return ext_link_id

    ctx.max_link_id += 1
    ctx.new_links.append([
        ctx.max_link_id,
        ext_link_data[1],  # Same source node
        ext_link_data[2],  # Same source slot
        target_node_id,
        target_slot,
        ext_link_data[5] if len(ext_link_data) > 5 else '*',
    ])
    logger.debug(f"    Created new link {ctx.max_link_id} for additional "
                 f"target: -> node {target_node_id} slot {target_slot}")
    return ctx.max_link_id


def _set_node_input_link(new_nodes, target_node_id, target_slot, link_id):
    """Record ``link_id`` on the matching input slot of an expanded node.

    Slots are matched by explicit ``slot_index`` first, then by position for
    nodes whose inputs omit it.

    Returns:
        True if a matching input slot was found.
    """
    for new_node in new_nodes:
        if new_node['id'] != target_node_id:
            continue
        for inp_idx, inp in enumerate(new_node.get('inputs', [])):
            slot_match = inp.get('slot_index') == target_slot
            index_match = 'slot_index' not in inp and inp_idx == target_slot
            if slot_match or index_match:
                inp['link'] = link_id
                logger.debug(f"    Updated internal node {target_node_id} input "
                             f"slot {target_slot}: link={link_id}")
                return True
        return False
    return False


def _wire_external_inputs(ctx, sg_node, sg_inputs, sg_internal_links,
                          boundary_input_map, node_id_map):
    """Rewire links that fed the subgraph node so they feed its internals.

    For every connected subgraph input, the external link is retargeted at the
    first internal consumer and duplicated for any further consumers.
    """
    sg_node_inputs = sg_node.get('inputs', [])
    logger.debug(f"    Processing {len(sg_inputs)} subgraph inputs, "
                 f"{len(sg_node_inputs)} connected inputs")

    for i, sg_input_def in enumerate(sg_inputs):
        input_name = sg_input_def.get('name', f'input_{i}')

        ext_link_id = None
        if i < len(sg_node_inputs):
            ext_link_id = sg_node_inputs[i].get('link')
        if ext_link_id is None:
            logger.debug(f"    Input {i} ({input_name}): no external link connected")
            continue

        internal_targets = _resolve_input_targets(
            sg_input_def, i, sg_internal_links, boundary_input_map)
        if not internal_targets:
            logger.debug(f"    Input {i} ({input_name}): no internal targets found")
            continue

        if not ctx.link_lookup.get(ext_link_id):
            logger.warning(f"    Input {i} ({input_name}): external link "
                           f"{ext_link_id} not found in link_lookup")
            continue

        ext_link_data = None
        for link in ctx.expanded_links:
            if link[0] == ext_link_id:
                ext_link_data = link
                break

        for target_idx, (internal_to_node, target_slot, _il) in enumerate(internal_targets):
            target_node_id = node_id_map.get(internal_to_node)
            if target_node_id is None:
                logger.warning(f"    Input {i} ({input_name}): target node "
                               f"{internal_to_node} not in node_id_map")
                continue

            current_link_id = _connect_input_target(
                ctx, target_idx, target_node_id, target_slot,
                ext_link_id, ext_link_data)

            if not _set_node_input_link(ctx.new_nodes, target_node_id,
                                        target_slot, current_link_id):
                logger.warning(f"    Could not find input slot {target_slot} "
                               f"on node {target_node_id}")


def _resolve_output_source(sg_output_def, sg_output_idx, sg_internal_links,
                           boundary_output_map):
    """Find the internal node and slot that produce one subgraph output.

    Returns:
        Tuple of (internal_node, internal_slot), or (None, None) if unknown.
    """
    internal_link_id = sg_output_def.get('link')
    if internal_link_id is not None:
        for il in sg_internal_links:
            if il[0] == internal_link_id:
                logger.debug(f"    Output {sg_output_idx}: found via link "
                             f"{internal_link_id}")
                return il[1], il[2]

    if sg_output_idx in boundary_output_map:
        source_node, source_slot, _ = boundary_output_map[sg_output_idx]
        logger.debug(f"    Output {sg_output_idx}: using boundary map -> node "
                     f"{source_node} slot {source_slot}")
        return source_node, source_slot

    return None, None


def _register_node_output_link(new_nodes, source_node_id, source_slot, ext_link_id):
    """Add ``ext_link_id`` to the matching output slot of an expanded node."""
    for new_node in new_nodes:
        if new_node['id'] != source_node_id:
            continue
        for out_idx, out in enumerate(new_node.get('outputs', [])):
            if out.get('slot_index') == source_slot or (
                'slot_index' not in out and out_idx == source_slot
            ):
                if 'links' not in out or out['links'] is None:
                    out['links'] = []
                if ext_link_id not in out['links']:
                    out['links'].append(ext_link_id)
                return
        return


def _wire_external_outputs(ctx, sg_node, sg_outputs, sg_internal_links,
                           boundary_output_map, node_id_map):
    """Rewire links that read from the subgraph node to read from its internals."""
    sg_node_outputs = sg_node.get('outputs', [])
    logger.debug(f"    Processing {len(sg_outputs)} subgraph outputs, "
                 f"{len(sg_node_outputs)} connected outputs")

    for i, sg_output_def in enumerate(sg_outputs):
        output_name = sg_output_def.get('name', f'output_{i}')

        source_internal_node, source_slot = _resolve_output_source(
            sg_output_def, i, sg_internal_links, boundary_output_map)
        if source_internal_node is None:
            logger.debug(f"    Output {i} ({output_name}): no internal source found")
            continue

        source_node_id = node_id_map.get(source_internal_node)
        if source_node_id is None:
            logger.warning(f"    Output {i} ({output_name}): internal node "
                           f"{source_internal_node} not in node_id_map")
            continue

        if i >= len(sg_node_outputs):
            continue
        output_links = sg_node_outputs[i].get('links', [])
        logger.debug(f"    Output {i} ({output_name}): "
                     f"{len(output_links) if output_links else 0} external links to rewire")
        if not output_links:
            continue

        for ext_link_id in output_links:
            if ext_link_id not in ctx.link_lookup:
                continue
            for link in ctx.expanded_links:
                if link[0] == ext_link_id:
                    old_from = link[1]
                    link[1] = source_node_id
                    link[2] = source_slot
                    logger.debug(f"    Rewired external output link {ext_link_id}: "
                                 f"source {old_from} -> {source_node_id}")
                    break
            _register_node_output_link(ctx.new_nodes, source_node_id,
                                       source_slot, ext_link_id)


def _find_sg_input_index(sg_inputs, widget_name):
    """Return the subgraph input slot index whose name is ``widget_name``."""
    for si_idx, sg_inp in enumerate(sg_inputs):
        if sg_inp.get('name') == widget_name:
            return si_idx
    return None


def _set_internal_override(new_nodes, node_id_map, proxy_node_id_str,
                           widget_name, widget_value, log_tag):
    """Apply one widget value to the expanded copy of a specific internal node.

    ``proxy_node_id_str`` is the definition-local node ID as it appears in
    ``proxyWidgets``. Non-numeric IDs are ignored.
    """
    try:
        internal_id = int(proxy_node_id_str)
    except (ValueError, TypeError):
        return
    target_remapped = node_id_map.get(internal_id)
    if target_remapped is None:
        return
    for new_node in new_nodes:
        if new_node['id'] == target_remapped:
            new_node.setdefault('_input_overrides', {})[widget_name] = widget_value
            logger.debug(f"    Override ({log_tag}): node {target_remapped} widget "
                         f"'{widget_name}' = {repr(widget_value)[:60]}")
            return


def _propagate_via_proxy_list(sg_widgets_values, sg_proxy_widgets, sg_inputs,
                              boundary_input_map, node_id_map, new_nodes):
    """Widget path 1: ``proxyWidgets`` + list ``widgets_values``.

    Each ``proxyWidgets`` entry is ``[node_id_str, widget_name]`` positionally
    paired with ``widgets_values[idx]``. A node ID of ``"-1"`` means the value
    belongs to a subgraph boundary input and must fan out to every internal
    node that consumes it.
    """
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
            sg_input_idx = _find_sg_input_index(sg_inputs, widget_name)
            if sg_input_idx is None:
                logger.debug(f"    Boundary widget '{widget_name}': "
                             f"no matching sg_input found")
                continue
            _apply_boundary_overrides(widget_name, widget_value, sg_input_idx,
                                      boundary_input_map, node_id_map, new_nodes)
        else:
            _set_internal_override(new_nodes, node_id_map, proxy_node_id_str,
                                   widget_name, widget_value, 'internal')


def _propagate_via_input_index(sg_widgets_values, sg_inputs, boundary_input_map,
                               node_id_map, new_nodes):
    """Widget path 2: no ``proxyWidgets``, list ``widgets_values``.

    Values are paired with the subgraph's input definitions by position and
    propagated through the boundary input map. This holds whether or not the
    input definition carries an explicit ``link``.
    """
    for i, sg_input_def in enumerate(sg_inputs):
        if i >= len(sg_widgets_values):
            break
        input_name = sg_input_def.get('name', f'input_{i}')
        _apply_boundary_overrides(input_name, sg_widgets_values[i], i,
                                  boundary_input_map, node_id_map, new_nodes)


def _propagate_via_proxy_dict(sg_widgets_values, sg_proxy_widgets, sg_inputs,
                              boundary_input_map, node_id_map, new_nodes):
    """Widget path 3: ``proxyWidgets`` + dict ``widgets_values``.

    Values are looked up by widget name rather than by position; entries whose
    name is absent from the dict are skipped.
    """
    for proxy_entry in sg_proxy_widgets:
        if not isinstance(proxy_entry, (list, tuple)) or len(proxy_entry) < 2:
            continue
        proxy_node_id_str, widget_name = proxy_entry[0], proxy_entry[1]

        if widget_name not in sg_widgets_values:
            continue
        widget_value = sg_widgets_values[widget_name]

        # Skip phantom widgets
        if widget_name == 'control_after_generate':
            continue

        if proxy_node_id_str != "-1":
            _set_internal_override(new_nodes, node_id_map, proxy_node_id_str,
                                   widget_name, widget_value, 'dict')
        else:
            sg_input_idx = _find_sg_input_index(sg_inputs, widget_name)
            if sg_input_idx is not None:
                _apply_boundary_overrides(widget_name, widget_value, sg_input_idx,
                                          boundary_input_map, node_id_map, new_nodes)


def _broadcast_dict_widgets(sg_widgets_values, new_nodes):
    """Dict ``widgets_values`` with no ``proxyWidgets``: broadcast by name.

    Without proxy metadata there is no way to tell which internal node owns a
    widget, so every value is offered to every internal node. Existing
    overrides win, and UI-only preview state is skipped.
    """
    for new_node in new_nodes:
        for widget_name, widget_value in sg_widgets_values.items():
            if widget_name in ('videopreview', 'audiopreview'):
                continue
            overrides = new_node.setdefault('_input_overrides', {})
            if widget_name not in overrides:
                overrides[widget_name] = widget_value


def _normalize_subgraph_widgets_values(sg_node_id, sg_widgets_values):
    """Coerce a subgraph node's ``widgets_values`` into a supported shape.

    Returns:
        Tuple of (widgets_values, is_dict). Unexpected types become an empty
        list so downstream propagation is a no-op.
    """
    if isinstance(sg_widgets_values, dict):
        logger.info(f"Subgraph node {sg_node_id} uses dict widgets_values format")
        return sg_widgets_values, True
    if not isinstance(sg_widgets_values, list):
        logger.warning(f"Subgraph node {sg_node_id} has unexpected widgets_values "
                       f"type: {type(sg_widgets_values)} - resetting to empty list")
        return [], False
    return sg_widgets_values, False


def _propagate_subgraph_widgets(sg_node, sg_inputs, boundary_input_map,
                                node_id_map, new_nodes):
    """Push the subgraph node's widget values onto its expanded internal nodes.

    Values land in each internal node's ``_input_overrides`` dict, which
    :func:`convert_to_api_format` later applies on top of the (stale) defaults
    baked into the subgraph definition. Which of the three propagation paths
    applies depends on whether ``proxyWidgets`` metadata exists and whether
    ``widgets_values`` is a list or a dict.
    """
    sg_node_id = sg_node.get('id')
    sg_proxy_widgets = sg_node.get('properties', {}).get('proxyWidgets', [])
    sg_widgets_values, is_dict = _normalize_subgraph_widgets_values(
        sg_node_id, sg_node.get('widgets_values', []))

    if not is_dict and sg_widgets_values and sg_proxy_widgets:
        _propagate_via_proxy_list(sg_widgets_values, sg_proxy_widgets, sg_inputs,
                                  boundary_input_map, node_id_map, new_nodes)
    elif not is_dict and sg_widgets_values and sg_inputs:
        _propagate_via_input_index(sg_widgets_values, sg_inputs,
                                   boundary_input_map, node_id_map, new_nodes)
    elif is_dict:
        if sg_proxy_widgets:
            _propagate_via_proxy_dict(sg_widgets_values, sg_proxy_widgets, sg_inputs,
                                      boundary_input_map, node_id_map, new_nodes)
        else:
            _broadcast_dict_widgets(sg_widgets_values, new_nodes)


def _expand_subgraph_instance(ctx, sg_node, sg_def):
    """Expand a single subgraph instance into concrete nodes and links.

    Everything produced is appended to the shared context; the subgraph node
    itself is recorded for removal by the caller.

    Args:
        ctx: Shared :class:`_ExpansionContext` for this expansion pass.
        sg_node: The UUID-typed node instance in the parent workflow.
        sg_def: The matching subgraph definition from ``definitions.subgraphs``.
    """
    sg_internal_nodes = sg_def.get('nodes', [])
    sg_inputs = sg_def.get('inputs', [])    # External inputs
    sg_outputs = sg_def.get('outputs', [])  # External outputs

    sg_internal_links = [_normalize_link(l) for l in sg_def.get('links', [])]
    sg_internal_links = [l for l in sg_internal_links if l is not None]

    node_id_map, link_id_map = _allocate_subgraph_ids(
        ctx, sg_internal_nodes, sg_internal_links)

    ctx.new_nodes.extend(
        _remap_subgraph_nodes(sg_internal_nodes, node_id_map, link_id_map))
    ctx.new_links.extend(
        _remap_subgraph_links(sg_internal_links, node_id_map, link_id_map))

    boundary_input_map = _build_boundary_input_map(sg_internal_links, sg_inputs)
    _wire_external_inputs(ctx, sg_node, sg_inputs, sg_internal_links,
                          boundary_input_map, node_id_map)

    boundary_output_map = _build_boundary_output_map(sg_internal_links)
    _wire_external_outputs(ctx, sg_node, sg_outputs, sg_internal_links,
                           boundary_output_map, node_id_map)

    _propagate_subgraph_widgets(sg_node, sg_inputs, boundary_input_map,
                                node_id_map, ctx.new_nodes)


def _is_expandable_subgraph_node(node: Dict[str, Any], subgraph_defs: dict) -> bool:
    """True when a node is a subgraph instance that should be expanded.

    A muted or bypassed subgraph node is deliberately NOT expanded. Expanding
    it would splice its internals into the graph carrying their own (active)
    modes, and the wrapper node — the only thing that recorded the artist's
    intent to switch the whole group off — would be gone before
    :func:`_collect_skipped_node_ids` ever ran. Leaving the wrapper in place
    lets the normal mute/bypass machinery handle it: a muted subgraph severs
    its outputs, a bypassed one passes its inputs through by type.
    """
    if not (_is_uuid(node.get('type')) and node.get('type') in subgraph_defs):
        return False
    return node.get('mode', MODE_ALWAYS) not in (MODE_MUTED, MODE_BYPASSED)


def expand_subgraphs(workflow: Dict[str, Any], _depth: int = 0) -> Dict[str, Any]:
    """
    Expand all subgraph/component nodes into their constituent nodes.

    ComfyUI components/subgraphs are groups of nodes packaged together with a UUID
    as their type. This function expands them so the workflow can be executed via API.

    Args:
        workflow: Workflow in UI/nodes format (with 'nodes' array)
        _depth: Internal recursion depth counter (do not pass manually)

    Returns:
        Workflow with all subgraphs expanded into individual nodes
    """
    # Only process UI format workflows
    if 'nodes' not in workflow:
        return workflow

    subgraph_defs = _get_subgraph_definitions(workflow)
    if not subgraph_defs:
        return workflow  # No subgraphs to expand

    # Check if any nodes use subgraph types
    nodes = workflow.get('nodes', [])
    subgraph_nodes = [n for n in nodes
                      if _is_expandable_subgraph_node(n, subgraph_defs)]

    # Report the ones held back so a "why didn't my subgraph run?" question has
    # an answer in the log rather than silence.
    for n in nodes:
        if (_is_uuid(n.get('type')) and n.get('type') in subgraph_defs
                and n.get('mode', MODE_ALWAYS) in (MODE_MUTED, MODE_BYPASSED)):
            state = 'bypassed' if n.get('mode') == MODE_BYPASSED else 'muted'
            logger.info(f"Subgraph node {n.get('id')} is {state} — "
                        f"not expanding; handled as a unit")

    if not subgraph_nodes:
        return workflow  # No subgraph instances to expand

    logger.info(f"Expanding {len(subgraph_nodes)} subgraph node(s)...")

    # Deep copy to avoid modifying original
    expanded = copy.deepcopy(workflow)
    expanded_nodes = expanded.get('nodes', [])

    # Normalize all links to list format
    expanded_links = [_normalize_link(l) for l in expanded.get('links', [])]
    expanded_links = [l for l in expanded_links if l is not None]
    expanded['links'] = expanded_links

    ctx = _ExpansionContext(
        expanded_links=expanded_links,
        # link_id -> link data, for the links already in the parent workflow
        link_lookup={link[0]: link for link in expanded_links if link},
        # Track ID offsets to avoid collisions
        max_node_id=max((n.get('id', 0) for n in expanded_nodes), default=0),
        max_link_id=max((l[0] for l in expanded_links if l), default=0),
    )

    for sg_node in subgraph_nodes:
        sg_node_id = sg_node.get('id')
        sg_type = sg_node.get('type')
        sg_def = subgraph_defs.get(sg_type)

        if not sg_def:
            logger.warning(f"  Subgraph definition not found for {sg_type}")
            continue

        logger.debug(f"  Expanding subgraph node {sg_node_id} (type: {sg_type[:8]}...)")
        ctx.nodes_to_remove.add(sg_node_id)
        _expand_subgraph_instance(ctx, sg_node, sg_def)

    # Remove subgraph nodes and add expanded nodes
    expanded['nodes'] = [n for n in expanded_nodes
                         if n.get('id') not in ctx.nodes_to_remove]
    expanded['nodes'].extend(ctx.new_nodes)
    expanded['links'] = expanded_links + ctx.new_links

    # Recursively expand in case of nested subgraphs (with depth limit)
    if _depth >= 10:
        logger.warning("  Subgraph expansion depth limit reached (10), stopping expansion")
    elif any(_is_expandable_subgraph_node(n, subgraph_defs)
             for n in expanded['nodes']):
        logger.debug("  Checking for nested subgraphs...")
        return expand_subgraphs(expanded, _depth=_depth + 1)

    logger.info(f"  Expansion complete: {len(expanded['nodes'])} nodes, "
                f"{len(expanded['links'])} links")
    return expanded


# litegraph node modes (LGraphEventMode). These values are NOT interchangeable
# and the two that matter here behave differently:
#
#   MODE_MUTED (2, "NEVER")  — the node does not run and produces nothing.
#                              Links out of it are severed; downstream inputs
#                              that depended on it are dropped.
#   MODE_BYPASSED (4)        — the node does not run but passes data straight
#                              through, matching each output to an input of the
#                              same type.
#
# Conflating them (the previous behaviour) makes muting a node silently act
# like bypassing it, so a branch the artist meant to cut stays wired.
MODE_ALWAYS = 0
MODE_MUTED = 2
MODE_BYPASSED = 4


def _collect_skipped_node_ids(nodes: List[Dict[str, Any]]) -> tuple:
    """Collect node IDs that must not appear in the API workflow.

    Three reasons to skip: the node is muted (``mode=2``), bypassed
    (``mode=4``), or its type is UI-only (``SKIP_NODE_TYPES``).

    Returns:
        Tuple of (skipped_ids, passthrough_ids). ``passthrough_ids`` is the
        subset whose links should be re-sourced upstream — bypassed nodes plus
        the UI-only wrappers (Reroute) that exist purely to relay a link. Muted
        nodes are deliberately excluded: their links must be dropped.
    """
    skipped = set()
    passthrough = set()
    for node in nodes:
        node_id = node.get('id')
        node_type = node.get('type')
        node_mode = node.get('mode', MODE_ALWAYS)

        if node_mode == MODE_BYPASSED:
            skipped.add(node_id)
            passthrough.add(node_id)
            logger.info(f"Will skip node {node_id} ({node_type}) - "
                        f"mode 4 (bypassed, links pass through)")
        elif node_mode == MODE_MUTED:
            skipped.add(node_id)
            logger.info(f"Will skip node {node_id} ({node_type}) - "
                        f"mode 2 (muted, links severed)")
        # Skip certain node types (defined in comfyui_node_configs.py).
        # These are UI-only relays, so they pass through like a bypass.
        elif node_type in SKIP_NODE_TYPES or node_type is None:
            skipped.add(node_id)
            passthrough.add(node_id)
    return skipped, passthrough


def _build_link_map(links: List[Any], valid_node_ids: set) -> Dict[Any, tuple]:
    """Index links by ID as ``link_id -> (from_node, from_slot)``.

    Links whose endpoints are not real nodes are dropped: they would otherwise
    become dangling input references in the API workflow.
    """
    link_map = {}
    for link in links:
        # link format: [link_id, from_node, from_slot, to_node, to_slot, type]
        if len(link) < 5:
            continue
        link_id, from_node, from_slot, to_node = link[0], link[1], link[2], link[3]
        if from_node not in valid_node_ids:
            logger.info(f"Skipping link {link_id}: from_node {from_node} "
                        f"not in valid nodes")
            continue
        if to_node not in valid_node_ids:
            logger.info(f"Skipping link {link_id}: to_node {to_node} "
                        f"not in valid nodes")
            continue
        link_map[link_id] = (from_node, from_slot)
    return link_map


def _slot_entries(node: Dict[str, Any], key: str):
    """Yield ``(slot_index, spec)`` for a node's ``inputs`` or ``outputs``.

    Honours an explicit ``slot_index`` and falls back to array position.
    """
    for idx, spec in enumerate(node.get(key) or []):
        if isinstance(spec, dict):
            yield spec.get('slot_index', idx), spec


def _types_match(out_type: Any, in_type: Any) -> bool:
    """True when a bypassed node's output slot can be fed by an input slot.

    ComfyUI matches bypass connections by data type, not slot position. ``*``
    is litegraph's wildcard and matches anything.
    """
    if out_type is None or in_type is None:
        return False
    out_s = str(out_type).upper()
    in_s = str(in_type).upper()
    if out_s == '*' or in_s == '*':
        return True
    return out_s == in_s


def _build_passthrough_map(nodes: List[Dict[str, Any]],
                           passthrough_ids: set) -> Dict[Any, Dict[int, Any]]:
    """Map each pass-through node's output slots to the link feeding them.

    Type-matched, mirroring ComfyUI: for output slot N, find the first *unused*
    connected input carrying the same type. An output with no type-compatible
    input is left unmapped, so the downstream link is dropped — which is what
    ComfyUI does, rather than inventing a mismatched connection.

    Falls back to positional matching only when the node carries no type
    metadata at all (legacy workflows, bare Reroute nodes).

    Returns:
        Dict of node_id -> {output_slot: link_id}.
    """
    passthrough_map = {}
    for node in nodes:
        nid = node.get('id')
        if nid not in passthrough_ids:
            continue

        inputs = list(_slot_entries(node, 'inputs'))
        outputs = list(_slot_entries(node, 'outputs'))
        linked = {slot: spec.get('link') for slot, spec in inputs
                  if spec.get('link') is not None}

        has_types = (any(spec.get('type') for _s, spec in inputs)
                     and any(spec.get('type') for _s, spec in outputs))

        slot_map = {}
        if has_types:
            used_inputs = set()
            for out_slot, out_spec in outputs:
                out_type = out_spec.get('type')
                for in_slot, in_spec in inputs:
                    if in_slot in used_inputs or in_slot not in linked:
                        continue
                    if _types_match(out_type, in_spec.get('type')):
                        slot_map[out_slot] = linked[in_slot]
                        used_inputs.add(in_slot)
                        break
                else:
                    logger.debug(
                        f"Bypass node {nid}: output slot {out_slot} "
                        f"({out_type}) has no type-compatible input — "
                        f"downstream link will be dropped"
                    )
        elif outputs:
            # No type info — preserve the historical positional behaviour
            for out_slot, _spec in outputs:
                if out_slot in linked:
                    slot_map[out_slot] = linked[out_slot]
        else:
            # Node declares no outputs array at all (bare relay)
            slot_map = dict(linked)

        passthrough_map[nid] = slot_map
    return passthrough_map


def _trace_through_skipped(from_node, from_slot, skipped_node_ids,
                           passthrough_map, link_map, visited=None):
    """Walk upstream through bypassed/relay nodes to the first live source.

    Follows chains of pass-through nodes; ``visited`` guards against cycles.
    A *muted* node has no entry in ``passthrough_map``, so the walk terminates
    with ``(None, None)`` and the caller drops the link.

    Returns:
        Tuple of (node_id, slot), or ``(None, None)`` when the chain has no
        pass-through source.
    """
    if visited is None:
        visited = set()
    if from_node not in skipped_node_ids or from_node in visited:
        return from_node, from_slot
    visited.add(from_node)
    upstream_link = passthrough_map.get(from_node, {}).get(from_slot)
    if upstream_link is not None and upstream_link in link_map:
        up_node, up_slot = link_map[upstream_link]
        return _trace_through_skipped(up_node, up_slot, skipped_node_ids,
                                      passthrough_map, link_map, visited)
    return None, None  # No pass-through found


def _resolve_links_through_skipped(link_map: Dict[Any, tuple],
                                   nodes: List[Dict[str, Any]],
                                   skipped_node_ids: set,
                                   passthrough_ids: set) -> None:
    """Repoint links that originate at a skipped node, in place.

    Links out of a bypassed/relay node are re-sourced at the first live node
    upstream. Links out of a muted node — and any link with no resolvable
    source — are deleted from ``link_map`` so the consuming input is dropped
    rather than left dangling.
    """
    if not skipped_node_ids:
        return

    passthrough_map = _build_passthrough_map(nodes, passthrough_ids)

    for link_id in list(link_map.keys()):
        from_node, from_slot = link_map[link_id]
        if from_node not in skipped_node_ids:
            continue
        resolved_node, resolved_slot = _trace_through_skipped(
            from_node, from_slot, skipped_node_ids, passthrough_map, link_map)
        if resolved_node is not None:
            link_map[link_id] = (resolved_node, resolved_slot)
            logger.debug(f"Resolved link {link_id} through bypassed node(s): "
                         f"{from_node}:{from_slot} -> {resolved_node}:{resolved_slot}")
        else:
            del link_map[link_id]
            logger.debug(f"Removed link {link_id}: no pass-through source "
                         f"through skipped node {from_node}")


def _normalize_widgets_values(node_id: str, node_type: Any, widgets_values: Any):
    """Coerce a node's ``widgets_values`` into a dict or list.

    Returns:
        Tuple of (widgets_values, is_dict); unexpected types become an empty list.
    """
    if isinstance(widgets_values, dict):
        return widgets_values, True
    if not isinstance(widgets_values, list):
        logger.warning(f"Node {node_id} ({node_type}) has unexpected "
                       f"widgets_values type: {type(widgets_values)} - "
                       f"resetting to empty list")
        return [], False
    return widgets_values, False


def _build_connected_inputs(inputs_spec, link_map, skipped_node_ids,
                            node_id, node_type) -> tuple:
    """Turn a node's linked input slots into API-format node references.

    Each connected input becomes ``[from_node_id_str, from_slot]``. Inputs still
    pointing at a skipped node after link resolution are dropped entirely.

    Returns:
        Tuple of (inputs, linked_keys). ``linked_keys`` names exactly the
        inputs backed by a link, so later passes can refuse to overwrite them
        without having to guess from the value's shape — a widget whose value
        is genuinely a two-element list (a resolution pair, a range) is
        otherwise indistinguishable from a node reference.
    """
    inputs = {}
    linked_keys = set()
    for input_spec in inputs_spec:
        input_name = input_spec.get('name')
        link_id = input_spec.get('link')
        if link_id is None or link_id not in link_map:
            continue
        from_node, from_slot = link_map[link_id]
        if from_node in skipped_node_ids:
            logger.info(f"Removing input '{input_name}' from node {node_id} "
                        f"({node_type}) - references skipped node {from_node}")
            continue
        # Reference format: [node_id, slot_index]
        inputs[input_name] = [str(from_node), from_slot]
        linked_keys.add(input_name)
    return inputs, linked_keys


def _is_node_reference(value: Any) -> bool:
    """True when an API-format input value is a ``[node_id, slot]`` reference.

    References are always built as ``[str(node_id), int(slot)]``. Requiring the
    string first element keeps genuine list-valued widgets (``[512, 512]``)
    from being mistaken for connections. ``bool`` is excluded explicitly since
    it is a subclass of ``int``.
    """
    if not (isinstance(value, list) and len(value) == 2):
        return False
    ref, slot = value
    return (isinstance(ref, str)
            and isinstance(slot, int)
            and not isinstance(slot, bool))


def _resolve_widget_names(node, node_type, widgets_values, subgraph_widgets):
    """Discover the ordered widget names behind a list ``widgets_values``.

    Four tiers, most reliable first:

    1. The node's own ``inputs`` array (widget metadata saved by the UI).
    2. The subgraph definition, for UUID-typed nodes — padded with leading
       ``None`` entries for values that belong to linked inputs.
    3. The ``node_info`` cache auto-discovered from ComfyUI's ``/object_info``.
    4. The hand-maintained ``WIDGET_MAPPINGS`` table.

    Returns:
        List of names (``None`` marks a value to skip), or ``None`` if no
        source could name the widgets.
    """
    from comfyui.node_info import get_widget_names as _get_ni_widget_names

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
            logger.info(f"Using manual mapping for '{node_type}' "
                        f"(no widget info in workflow)")

    return widget_names


def _apply_widget_values(inputs, node, node_type, widgets_values,
                         widgets_values_is_dict, subgraph_widgets) -> None:
    """Merge a node's widget values into its API inputs dict, in place.

    Link connections always win: a widget never overwrites an input that is
    already wired to another node.
    """
    if not widgets_values:
        return

    if widgets_values_is_dict:
        # Dict format: keys are widget names, values are widget values
        for widget_name, widget_value in widgets_values.items():
            # Skip internal keys like videopreview/audiopreview (UI state)
            if widget_name in ('videopreview', 'audiopreview'):
                continue
            # Only add if not already connected via link
            if widget_name not in inputs:
                inputs[widget_name] = widget_value
        return

    # List format: need to map indices to widget names
    widget_names = _resolve_widget_names(node, node_type, widgets_values,
                                         subgraph_widgets)
    if widget_names is None:
        # No widget info from any source - warn but continue
        logger.warning(f"Unknown node type '{node_type}' with "
                       f"{len(widgets_values)} widget values - widget names "
                       f"could not be auto-discovered")
        return

    for i, widget_name in enumerate(widget_names):
        # Skip None entries (placeholder for control_after_generate or buttons)
        if widget_name is None:
            continue
        if i < len(widgets_values) and widget_name not in inputs:
            inputs[widget_name] = widgets_values[i]


def _apply_input_overrides(inputs, node, linked_keys) -> None:
    """Apply ``_input_overrides`` left behind by subgraph expansion, in place.

    These carry the parent subgraph node's live widget values, so they beat the
    stale defaults baked into the subgraph definition — but they must never
    clobber a link reference. ``linked_keys`` names those exactly, so a widget
    whose value happens to be a list is still overridable.
    """
    for key, val in node.get('_input_overrides', {}).items():
        if key in linked_keys:
            continue
        inputs[key] = val


def _strip_invalid_references(api_workflow: Dict[str, Any]) -> None:
    """Delete inputs that reference nodes absent from the API workflow."""
    valid_api_ids = set(api_workflow.keys())
    for node_id, node_data in api_workflow.items():
        inputs = node_data.get('inputs', {})
        invalid_inputs = []
        for input_name, input_value in inputs.items():
            if not _is_node_reference(input_value):
                continue
            ref_node_id = str(input_value[0])
            if ref_node_id not in valid_api_ids:
                logger.warning(f"Removing invalid input '{input_name}' from "
                               f"node {node_id}: references non-existent "
                               f"node {ref_node_id}")
                invalid_inputs.append(input_name)
        for input_name in invalid_inputs:
            del inputs[input_name]


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
    skipped_node_ids, passthrough_node_ids = _collect_skipped_node_ids(nodes)
    logger.info(f"Skipped node IDs: {skipped_node_ids}")

    valid_node_ids = set(node.get('id') for node in nodes
                         if node.get('id') is not None)
    link_map = _build_link_map(links, valid_node_ids)
    _resolve_links_through_skipped(link_map, nodes, skipped_node_ids,
                                   passthrough_node_ids)

    api_workflow = {}
    for node in nodes:
        node_id = str(node.get('id'))
        node_type = node.get('type')
        inputs_spec = node.get('inputs', [])  # Input slot definitions

        # Detect widgets_values format: dict (named) or list (indexed)
        widgets_values, widgets_values_is_dict = _normalize_widgets_values(
            node_id, node_type, node.get('widgets_values', []))

        # Skip nodes already identified in first pass (muted/bypassed/skip types)
        if node.get('id') in skipped_node_ids:
            continue

        inputs, linked_keys = _build_connected_inputs(
            inputs_spec, link_map, skipped_node_ids, node_id, node_type)
        _apply_widget_values(inputs, node, node_type, widgets_values,
                             widgets_values_is_dict, subgraph_widgets)
        _apply_input_overrides(inputs, node, linked_keys)

        api_workflow[node_id] = {
            'class_type': node_type,
            'inputs': inputs,
        }

        # Add _meta if node has a title
        if node.get('title'):
            api_workflow[node_id]['_meta'] = {'title': node['title']}

    # Final validation: remove any input references to non-existent nodes
    _strip_invalid_references(api_workflow)

    return api_workflow
