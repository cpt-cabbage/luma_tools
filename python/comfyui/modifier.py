"""
ComfyUI Workflow Modification.

Handles modifying workflow parameters like seeds, prompts, input images,
and output prefixes based on user inputs and editable node values.
"""

import os
import copy
import logging
import random
import re
from typing import Optional, Dict, Any, Tuple

from comfyui.workflow import is_api_format, convert_to_api_format
from comfyui.node_configs import WIDGET_MAPPINGS, EXPORT_NODE_TYPES, OUTPUT_SUFFIX
from core.config import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    AUDIO_EXTENSIONS,
    MODEL_EXTENSIONS,
    COMFYUI_DATA_EXTENSIONS,
)

logger = logging.getLogger(__name__)

# File extensions that indicate a file path input.
# Includes a few text/data formats not in the canonical sets.
FILE_EXTENSIONS = (
    IMAGE_EXTENSIONS
    | VIDEO_EXTENSIONS
    | AUDIO_EXTENSIONS
    | MODEL_EXTENSIONS
    | COMFYUI_DATA_EXTENSIONS
    | {'.m4a', '.aac', '.json', '.txt'}
)


def _is_file_path(value: Any) -> bool:
    """Check if a value looks like a file path."""
    if not isinstance(value, str):
        return False
    # Check if it has a file extension
    return any(value.lower().endswith(ext) for ext in FILE_EXTENSIONS)


def _is_link(value: Any) -> bool:
    """Check if an input value is a link reference to another node ([node_id, slot])."""
    return isinstance(value, list) and len(value) == 2 and isinstance(value[1], int)


def remove_nodes_from_api_workflow(
    workflow: Dict[str, Any],
    node_ids_to_remove: set,
) -> None:
    """Remove nodes from an API-format workflow with cascading removal.

    For each removed node, downstream references are rerouted through it
    (pass-through: output slot N maps to N-th link input). If no upstream
    source exists for a slot, the downstream input is removed. If that
    input was REQUIRED (per node_info cache), the downstream node is also
    removed (cascade). Optional lost inputs are simply dropped.

    Args:
        workflow: API format workflow dict (modified in place).
        node_ids_to_remove: Set of node ID strings to remove.
    """
    from comfyui.node_info import get_required_input_names

    if not node_ids_to_remove:
        return

    all_removed = set(node_ids_to_remove)
    pending = set(node_ids_to_remove)

    # Cascade: keep removing until no new nodes are affected
    max_iterations = 100
    iteration = 0
    while pending:
        iteration += 1
        if iteration > max_iterations:
            logger.warning(
                f"Node removal exceeded {max_iterations} iterations, "
                f"possible circular reference — force-removing {len(pending)} remaining node(s)"
            )
            # Force-remove remaining pending nodes to avoid inconsistent state
            for nid in pending:
                if nid in workflow:
                    class_type = workflow[nid].get('class_type', 'unknown')
                    del workflow[nid]
                    logger.info(f"  Force-removed node {nid} ({class_type})")
            break
        # Build pass-through maps for pending nodes:
        # {node_id: {output_slot: (upstream_node_id, upstream_slot)}}
        passthrough = {}
        for nid in pending:
            node_data = workflow.get(nid)
            if not node_data or not isinstance(node_data, dict):
                continue
            inputs = node_data.get('inputs', {})
            # Collect link inputs in dict order (insertion order = slot order)
            link_inputs = []
            for value in inputs.values():
                if _is_link(value):
                    link_inputs.append((str(value[0]), value[1]))
            passthrough[nid] = {slot: src for slot, src in enumerate(link_inputs)}

        # Reroute downstream references, track nodes that lose required inputs
        newly_broken = set()
        for node_id, node_data in list(workflow.items()):
            if node_id in all_removed or not isinstance(node_data, dict):
                continue
            inputs = node_data.get('inputs', {})
            class_type = node_data.get('class_type', '')
            required = get_required_input_names(class_type)
            # If cache miss, assume all inputs are required (safe default)
            required_set = set(required) if required is not None else None

            keys_to_remove = []
            for input_name, value in inputs.items():
                if not _is_link(value):
                    continue
                ref_node = str(value[0])
                ref_slot = value[1]
                if ref_node not in pending:
                    continue
                # Trace through chain of removed nodes
                visited = set()  # Track (node, slot) pairs to detect slot-based cycles
                cur_node, cur_slot = ref_node, ref_slot
                while cur_node in all_removed and (cur_node, cur_slot) not in visited:
                    visited.add((cur_node, cur_slot))
                    upstream = passthrough.get(cur_node, {}).get(cur_slot)
                    if upstream:
                        cur_node, cur_slot = upstream
                    else:
                        cur_node = None
                        break
                if cur_node and cur_node not in all_removed:
                    inputs[input_name] = [cur_node, cur_slot]
                    logger.info(f"  Rerouted node {node_id}.{input_name}: "
                                f"[{ref_node},{ref_slot}] -> [{cur_node},{cur_slot}]")
                else:
                    keys_to_remove.append(input_name)

            if keys_to_remove:
                lost_required = False
                for key in keys_to_remove:
                    del inputs[key]
                    is_req = required_set is None or key in required_set
                    req_label = "required" if is_req else "optional"
                    logger.info(f"  Removed {req_label} input {node_id}.{key}: "
                                f"no upstream through removed node(s)")
                    if is_req:
                        lost_required = True
                if lost_required:
                    # Lost a required input — node can't execute, cascade
                    newly_broken.add(node_id)

        # Delete pending nodes from workflow
        for nid in pending:
            if nid in workflow:
                class_type = workflow[nid].get('class_type', 'unknown')
                del workflow[nid]
                logger.info(f"  Removed node {nid} ({class_type}) from workflow")

        # Cascade: only nodes that lost required inputs
        pending = newly_broken - all_removed
        if pending:
            logger.info(f"  Cascading removal to {len(pending)} downstream node(s)")
        all_removed.update(pending)


def normalize_file_paths_in_workflow(workflow: Dict[str, Any]) -> Dict[str, str]:
    """
    Scan API format workflow and convert all file paths to basenames.

    Returns dict mapping original full paths to basenames for file copying.
    """
    from comfyui.image_convert import needs_conversion, get_png_basename

    files_to_copy = {}  # full_path -> basename

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue

        inputs = node_data.get('inputs', {})
        if not isinstance(inputs, dict):
            continue

        for input_name, input_value in inputs.items():
            # Check if this input looks like a file path
            if _is_file_path(input_value):
                basename = os.path.basename(input_value)
                # Only convert if it looks like an absolute/relative path (has separators)
                if '/' in input_value or '\\' in input_value:
                    # Validate file exists and reject suspicious paths
                    abs_path = os.path.abspath(input_value)
                    if not os.path.isfile(abs_path):
                        logger.warning(f"  Skipping non-existent file path in node {node_id}.{input_name}: {input_value}")
                        continue
                    # Rewrite basename to .png if format needs conversion
                    if needs_conversion(input_value):
                        dest_basename = get_png_basename(basename)
                        logger.info(f"  Will convert {basename} → {dest_basename}")
                    else:
                        dest_basename = basename
                    files_to_copy[input_value] = dest_basename
                    inputs[input_name] = dest_basename
                    logger.info(f"  Normalized file path in node {node_id}.{input_name}: {dest_basename}")

    return files_to_copy


def _iter_editable_entries(editable_values):
    """Yield ``(node_id, entry)`` pairs from an editable_values mapping.

    Callers may pass either the current list-per-node format
    ``{node_id: [{'node': EditableNode, 'value': Any}, ...]}`` or the legacy
    single-dict-per-node format; both are normalized here.
    """
    for node_id, entries in (editable_values or {}).items():
        entry_list = entries if isinstance(entries, list) else [entries]
        for data in entry_list:
            yield node_id, data


def _index_editable_nodes(editable_values):
    """Summarize which nodes the dynamic UI touched.

    Returns:
        Tuple of (editable_by_node_id, found_editable_prompt) where the first is
        a ``{node_id: True}`` lookup used to suppress legacy per-class_type
        handling, and the second is True when any entry is a text widget.
    """
    editable_by_node_id = {}
    found_editable_prompt = False
    for node_id, entries in (editable_values or {}).items():
        entry_list = entries if isinstance(entries, list) else [entries]
        editable_by_node_id[node_id] = True
        for data in entry_list:
            node_info = data.get('node')
            if node_info and node_info.widget_type == 'text':
                found_editable_prompt = True
    return editable_by_node_id, found_editable_prompt


def _convert_preview_to_save_nodes(workflow: Dict[str, Any]) -> None:
    """Rewrite every PreviewImage node as a SaveImage node, in place.

    PreviewImage writes temp files with generated names; SaveImage accepts a
    ``filename_prefix``, which is what the gallery needs to find the output.
    """
    converted = []
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict) or node_data.get('class_type') != 'PreviewImage':
            continue
        node_data['class_type'] = 'SaveImage'
        # SaveImage needs filename_prefix input (set later by EXPORT_NODE_TYPES handling)
        if 'inputs' not in node_data:
            node_data['inputs'] = {}
        converted.append(node_id)

    if converted:
        logger.info(f"Converted {len(converted)} PreviewImage node(s) to "
                    f"SaveImage: {converted}")


def _log_workflow_summary(workflow: Dict[str, Any]) -> None:
    """Log the workflow's node types and titles, grouped by class_type."""
    node_types = {}
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue
        ct = node_data.get('class_type')
        title = node_data.get('_meta', {}).get('title', '')
        node_types.setdefault(ct, []).append(f"{node_id}:{title}" if title else node_id)

    logger.info(f"Workflow contains {len(workflow)} nodes:")
    for ct, nodes in sorted(node_types.items()):
        logger.info(f"  {ct}: {nodes}")


def _first_path(value: Any) -> Optional[str]:
    """Return a single path from a widget value that may be a list or a string."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


# --- Per-widget-type appliers -------------------------------------------------
# All of these take the same arguments so they can be dispatched from a table:
#   inputs      the node's API-format inputs dict, mutated in place
#   value       the value chosen in the UI
#   widget_name explicit target input name (settings nodes), or None
#   node_id/node_type  for logging only

def _apply_text_widget(inputs, value, widget_name, node_id, node_type):
    """Text/prompt widget — writes the named input, else 'prompt', else 'text'."""
    if widget_name:
        inputs[widget_name] = value
    elif 'prompt' in inputs:
        inputs['prompt'] = value
    else:
        inputs['text'] = value
    logger.info(f"  Set text node {node_id} ({node_type}): {str(value)[:50]}...")


def _apply_image_widget(inputs, value, widget_name, node_id, node_type):
    """Image widget — stores the basename, rewritten to .png when converted."""
    from comfyui.image_convert import needs_conversion, get_png_basename

    if not value:
        # No image provided — leave node as-is with its workflow default
        logger.info(f"  Image node {node_id} ({node_type}): no file selected, "
                    f"keeping workflow default")
        return
    image_path = _first_path(value)
    if not image_path:
        return
    basename = os.path.basename(image_path)
    if needs_conversion(image_path):
        basename = get_png_basename(basename)
        logger.info(f"  Image {os.path.basename(image_path)} will be converted "
                    f"to {basename}")
    inputs['image'] = basename
    logger.info(f"  Set image node {node_id} ({node_type}): {basename}")


def _apply_int_widget(inputs, value, widget_name, node_id, node_type):
    """Int widget — named input for settings nodes, else the seed pair."""
    if widget_name:
        try:
            inputs[widget_name] = int(value)
            logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {value}")
        except (ValueError, TypeError):
            logger.warning(f"  Failed to convert {value} to int for {widget_name}")
        return
    # Default behavior for editable nodes (seed-related)
    inputs['seed'] = value
    inputs['noise_seed'] = value
    logger.info(f"  Set int node {node_id} ({node_type}): {value}")


def _apply_float_widget(inputs, value, widget_name, node_id, node_type):
    """Float widget — named input for settings nodes, else 'cfg'."""
    if widget_name:
        try:
            inputs[widget_name] = float(value)
            logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {value}")
        except (ValueError, TypeError):
            logger.warning(f"  Failed to convert {value} to float for {widget_name}")
        return
    # Default behavior for editable nodes
    inputs['cfg'] = value
    logger.info(f"  Set float node {node_id} ({node_type}): {value}")


def _apply_string_widget(inputs, value, widget_name, node_id, node_type):
    """Single-line string widget — named input, else 'filename_prefix'."""
    if widget_name:
        inputs[widget_name] = value
        logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {value}")
    else:
        inputs['filename_prefix'] = value
        logger.info(f"  Set string node {node_id} ({node_type}): {value}")


def _apply_combo_widget(inputs, value, widget_name, node_id, node_type):
    """Dropdown widget — only actionable when the target input is named."""
    if widget_name:
        inputs[widget_name] = value
        logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {value}")
    else:
        logger.info(f"  Combo node {node_id} ({node_type}): {value} (no widget_name)")


def _apply_toggle_widget(inputs, value, widget_name, node_id, node_type):
    """Toggle widget — written as 0/1 to the named input, else 'index'."""
    int_value = 1 if value else 0
    if widget_name:
        inputs[widget_name] = int_value
        logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {int_value}")
    else:
        inputs['index'] = int_value
        logger.info(f"  Set toggle node {node_id} ({node_type}): {int_value}")


def _apply_model_widget(inputs, value, widget_name, node_id, node_type):
    """3D model widget — stores the basename in the named input, else 'model_file'."""
    if not value:
        # No model provided — leave node as-is with its workflow default
        logger.info(f"  3D model node {node_id} ({node_type}): no file selected, "
                    f"keeping workflow default")
        return
    model_path = _first_path(value)
    if model_path:
        inputs[widget_name or 'model_file'] = os.path.basename(model_path)
        logger.info(f"  Set 3D model node {node_id} ({node_type}): "
                    f"{os.path.basename(model_path)}")


def _apply_video_widget(inputs, value, widget_name, node_id, node_type):
    """Video widget — stores the basename in the named input, else 'video'."""
    if not value:
        # No video provided — leave node as-is with its workflow default
        logger.info(f"  Video node {node_id} ({node_type}): no file selected, "
                    f"keeping workflow default")
        return
    video_path = _first_path(value)
    if video_path:
        inputs[widget_name or 'video'] = os.path.basename(video_path)
        logger.info(f"  Set video node {node_id} ({node_type}): "
                    f"{os.path.basename(video_path)}")


def _apply_audio_widget(inputs, value, widget_name, node_id, node_type):
    """Audio widget — stores the basename in the named input, else 'audio'."""
    if not value:
        # No audio provided — leave node as-is with its workflow default
        logger.info(f"  Audio node {node_id} ({node_type}): no file selected, "
                    f"keeping workflow default")
        return
    audio_path = _first_path(value)
    if audio_path:
        inputs[widget_name or 'audio'] = os.path.basename(audio_path)
        logger.info(f"  Set audio node {node_id} ({node_type}): "
                    f"{os.path.basename(audio_path)}")


def _apply_directory_widget(inputs, value, widget_name, node_id, node_type):
    """Directory widget — writes the full path to the named input, else 'directory'."""
    if not value:
        return
    if widget_name:
        inputs[widget_name] = str(value)
        logger.info(f"  Set directory on node {node_id} ({node_type}): "
                    f"{widget_name} = {value}")
    else:
        # Fallback to 'directory' if no specific widget name
        inputs['directory'] = str(value)
        logger.info(f"  Set directory on node {node_id} ({node_type}): {value}")


# widget_type -> applier. Unlisted widget types are silently ignored.
_WIDGET_APPLIERS = {
    'text': _apply_text_widget,
    'image': _apply_image_widget,
    'int': _apply_int_widget,
    'float': _apply_float_widget,
    'string': _apply_string_widget,
    'combo': _apply_combo_widget,
    'toggle': _apply_toggle_widget,
    '3d_model': _apply_model_widget,
    'video': _apply_video_widget,
    'audio': _apply_audio_widget,
    'directory': _apply_directory_widget,
}


def _is_expanded_subgraph_node(node_info) -> bool:
    """True when an editable node belongs to a subgraph that has been expanded.

    Subgraph node IDs never survive into API format — their internals were
    already given the value during expansion — so a missing node is expected
    and must not be warned about.
    """
    if not (node_info and hasattr(node_info, 'node_type')):
        return False
    from comfyui.workflow import _is_uuid
    return _is_uuid(node_info.node_type)


_INDEXED_NAME_RE = re.compile(r'^(?P<prefix>.*?)(?P<idx>\d+)$')


def _split_indexed_name(name: str) -> Optional[Tuple[str, int]]:
    """Split 'media_1' into ('media_', 1). None when there is no trailing int."""
    match = _INDEXED_NAME_RE.match(name or '')
    if not match:
        return None
    return match.group('prefix'), int(match.group('idx'))


def _find_consumers(workflow: Dict[str, Any], template_id: str):
    """Every (consumer_id, input_name, output_slot) fed by ``template_id``."""
    found = []
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        for input_name, value in (node_data.get('inputs') or {}).items():
            if _is_link(value) and str(value[0]) == str(template_id):
                found.append((node_id, input_name, value[1]))
    return found


def _allocate_node_id(workflow: Dict[str, Any]) -> str:
    """Next unused integer-like key."""
    max_id = 0
    for key in workflow:
        try:
            max_id = max(max_id, int(key))
        except (TypeError, ValueError):
            continue
    return str(max_id + 1)


def _detach_slot_node(workflow: Dict[str, Any], template_id: str) -> None:
    """Remove a slot's node and every consumer input it feeds.

    Used for empty '?' and '*' slots, which are optional by construction, so
    dropping the inputs can never break the consumer. Goes input-by-input
    rather than through remove_nodes_from_api_workflow: that treats a
    node_info cache miss as "all inputs required" and would cascade into
    deleting the consumer itself.

    The linking input is always dropped — a link to a removed node fails the
    whole prompt on the farm. Indexed siblings (media_type_N alongside
    media_N) travel with the linked input.
    """
    for consumer_id, input_name, _slot in _find_consumers(workflow, template_id):
        consumer_inputs = workflow[consumer_id]['inputs']
        consumer_inputs.pop(input_name, None)
        logger.info(f"[Slot] Dropped optional input {consumer_id}.{input_name}")
        split = _split_indexed_name(input_name)
        if not split:
            continue
        for name in [n for n in consumer_inputs
                     if (_split_indexed_name(n) or (None, None))[1] == split[1]]:
            del consumer_inputs[name]
            logger.info(f"[Slot] Dropped optional input {consumer_id}.{name}")
    workflow.pop(template_id, None)


# Widget types where "left empty" is unambiguous — a False toggle or blank
# combo is a legitimate value, not an empty slot.
_FILE_SLOT_WIDGET_TYPES = ('image', 'video', 'audio', '3d_model', 'directory')


def _remove_empty_optional_slots(workflow: Dict[str, Any], editable_values) -> None:
    """'Name_editable?' semantics: remove the node when the slot is left empty.

    A filled optional slot is applied by the normal appliers like any single
    slot; only the empty case differs from CARDINALITY_SINGLE, which keeps
    the workflow's baked-in default instead.
    """
    from comfyui.editable import CARDINALITY_OPTIONAL

    if not editable_values:
        return
    for node_id, data in _iter_editable_entries(editable_values):
        node_info = data.get('node')
        if getattr(node_info, 'cardinality', None) != CARDINALITY_OPTIONAL:
            continue
        if getattr(node_info, 'widget_type', None) not in _FILE_SLOT_WIDGET_TYPES:
            continue
        value = data.get('value')
        files = [f for f in (value if isinstance(value, list) else [value]) if f]
        if files:
            continue
        template_id = str(node_id)
        if template_id in workflow:
            _detach_slot_node(workflow, template_id)
            logger.info(f"[Optional] Slot {template_id} empty — node removed")


def _expand_fanout_slots(workflow: Dict[str, Any], editable_values) -> None:
    """Expand every fan-out slot into one loader node per selected file.

    A slot titled ``Name_editable*`` holds a list of files. The first stays on
    the template node; each extra file gets a cloned node wired into the next
    free numbered input on the same consumer. Every consumer input sharing the
    template's trailing index is duplicated too, so ``media_type_N`` follows
    ``media_N`` without this code knowing either name.

    Full paths are written deliberately — normalize_file_paths_in_workflow()
    later basenames them, handles .exr -> .png renaming, and collects them for
    staging, so there is no separate copy step for the generated nodes.
    """
    from comfyui.editable import CARDINALITY_MANY
    from comfyui.node_info import get_optional_input_names

    if not editable_values:
        return

    handled = []
    for node_id, entries in list(editable_values.items()):
        entry_list = entries if isinstance(entries, list) else [entries]
        for data in entry_list:
            node_info = data.get('node')
            if getattr(node_info, 'cardinality', None) != CARDINALITY_MANY:
                continue

            template_id = str(node_id)
            template = workflow.get(template_id)
            if template is None:
                logger.warning(f"[Fanout] Template node {template_id} not in workflow")
                continue

            value = data.get('value')
            files = [f for f in (value if isinstance(value, list) else [value]) if f]
            file_input = getattr(node_info, 'widget_name', None) or 'image'

            handled.append((node_id, data))
            consumers = _find_consumers(workflow, template_id)

            if not files:
                _detach_slot_node(workflow, template_id)
                logger.info(f"[Fanout] Slot {template_id} empty — template node removed")
                continue

            template['inputs'][file_input] = files[0]
            if len(files) == 1:
                continue

            if not consumers:
                logger.warning(f"[Fanout] Node {template_id} feeds nothing — "
                               f"{len(files) - 1} extra file(s) ignored")
                continue
            consumer_id, input_name, out_slot = consumers[0]
            split = _split_indexed_name(input_name)
            if not split:
                logger.warning(f"[Fanout] Consumer input '{input_name}' has no trailing "
                               f"index — {len(files) - 1} extra file(s) ignored")
                continue
            prefix, base_idx = split

            consumer_inputs = workflow[consumer_id]['inputs']
            # Every input sharing the template's index travels with it, which
            # is what carries media_type_N alongside media_N generically.
            siblings = {}
            for name, val in list(consumer_inputs.items()):
                parsed = _split_indexed_name(name)
                if parsed and parsed[1] == base_idx:
                    siblings[parsed[0]] = val

            consumer_type = workflow[consumer_id].get('class_type', '')
            declared = get_optional_input_names(consumer_type) or []
            ceiling = 0
            for name in declared:
                parsed = _split_indexed_name(name)
                if parsed and parsed[0] == prefix:
                    ceiling = max(ceiling, parsed[1])
            if ceiling == 0:
                # Writing an undeclared input would be dropped by ComfyUI without
                # complaint, so refuse rather than fan out into nowhere.
                logger.warning(
                    f"[Fanout] node_info has no '{prefix}N' inputs for "
                    f"'{consumer_type}' — cannot allocate slots, so "
                    f"{len(files) - 1} extra file(s) are ignored. Refresh the "
                    f"node info cache (restart the ComfyUI server) if this node "
                    f"pack was installed recently."
                )
                continue
            used = {p[1] for p in (_split_indexed_name(n) for n in consumer_inputs) if p}

            for extra in files[1:]:
                free = next((i for i in range(1, ceiling + 1) if i not in used), None)
                if free is None:
                    logger.warning(
                        f"[Fanout] No free '{prefix}N' slot below {ceiling} on "
                        f"{consumer_id} — dropping {os.path.basename(str(extra))}")
                    continue
                used.add(free)

                clone_id = _allocate_node_id(workflow)
                clone = copy.deepcopy(template)
                clone['inputs'][file_input] = extra
                workflow[clone_id] = clone

                for sib_prefix, sib_value in siblings.items():
                    if _is_link(sib_value):
                        consumer_inputs[f"{sib_prefix}{free}"] = [clone_id, out_slot]
                    else:
                        consumer_inputs[f"{sib_prefix}{free}"] = sib_value
                logger.info(f"[Fanout] {os.path.basename(str(extra))} -> node {clone_id} "
                            f"-> {consumer_id}.{prefix}{free}")

    # Handled entries must not reach the normal appliers, which would overwrite
    # the template's path with a basename and undo the expansion.
    for node_id, data in handled:
        entries = editable_values.get(node_id)
        if isinstance(entries, list):
            if data in entries:
                entries.remove(data)
            if not entries:
                del editable_values[node_id]
        else:
            editable_values.pop(node_id, None)


def _apply_editable_values(workflow: Dict[str, Any], editable_values) -> None:
    """Write every value collected from the dynamic UI into the workflow.

    Each entry names a node and a widget type; the widget type selects how the
    value is written (see ``_WIDGET_APPLIERS``).
    """
    if not editable_values:
        return

    total_entries = sum(len(v) if isinstance(v, list) else 1
                        for v in editable_values.values())
    logger.info(f"=== Applying {total_entries} editable values across "
                f"{len(editable_values)} nodes ===")

    for node_id, data in _iter_editable_entries(editable_values):
        node_id_str = str(node_id)
        node_info = data.get('node')
        value = data.get('value')

        if node_id_str not in workflow:
            if _is_expanded_subgraph_node(node_info):
                continue
            from comfyui.editable import CARDINALITY_OPTIONAL
            if getattr(node_info, 'cardinality', None) == CARDINALITY_OPTIONAL:
                # Removed by _remove_empty_optional_slots — expected, not an error
                continue
            logger.warning(f"  Node {node_id} not found in workflow")
            continue

        node_data = workflow[node_id_str]
        inputs = node_data.get('inputs', {})
        node_type = node_info.node_type if node_info else 'unknown'
        widget_type = node_info.widget_type if node_info else 'unknown'
        # Settings nodes carry an explicit target input name
        widget_name = getattr(node_info, 'widget_name', None)

        applier = _WIDGET_APPLIERS.get(widget_type)
        if applier is not None:
            applier(inputs, value, widget_name, node_id, node_type)


def _collect_toggle_values(editable_values) -> Dict[str, bool]:
    """Map toggle names to their on/off state.

    A toggle's name comes from its node title with the ``_editable`` suffix
    stripped, lowercased — that is the key ``&if_``/``@if_`` conditionals refer to.
    """
    toggle_values = {}
    for node_id, data in _iter_editable_entries(editable_values):
        node_info = data.get('node')
        if not (node_info and node_info.widget_type == 'toggle'):
            continue
        title = node_info.title or ''
        base_name = title.replace('_editable', '').strip()
        value = bool(data.get('value'))
        base_key = base_name.lower()
        if base_key in toggle_values:
            logger.warning(f"[Toggle] Duplicate toggle name '{base_name}' "
                           f"(node {node_id}), overwriting with value: {value}")
        toggle_values[base_key] = value
        logger.info(f"[Toggle] Found toggle '{base_name}' = {value}")
    return toggle_values


def _extract_conditional_toggle(title: str) -> Optional[str]:
    """Parse the toggle name out of a ``Name&if_Toggle`` / ``Name@if_Toggle`` title.

    Returns:
        The lowercased toggle name, or None when the title has no conditional.
    """
    for separator in ['&if_', '@if_']:
        if separator not in title.lower():
            continue
        parts = title.lower().split(separator)
        if len(parts) > 1:
            # Toggle name may carry _editable or further &-suffixes
            return parts[1].split('_editable')[0].split('&')[0].strip()
    return None


def _collect_conditionally_disabled_nodes(workflow: Dict[str, Any],
                                          toggle_values: Dict[str, bool]) -> set:
    """Find nodes whose ``&if_`` toggle is switched off.

    Nodes referencing an unknown toggle are kept (and warned about).
    """
    nodes_to_remove = set()
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        title = node_data.get('_meta', {}).get('title', '')
        if_match = _extract_conditional_toggle(title)
        if not if_match:
            continue

        toggle_value = toggle_values.get(if_match)
        if toggle_value is None:
            logger.warning(f"[Bypass] Node {node_id} references toggle "
                           f"'{if_match}' but toggle not found")
        elif not toggle_value:
            class_type = node_data.get('class_type', 'unknown')
            nodes_to_remove.add(str(node_id))
            logger.info(f"[Bypass] Will remove node {node_id} ({class_type}) - "
                        f"'{if_match}' is OFF")
    return nodes_to_remove


def _iter_export_nodes(workflow: Dict[str, Any]):
    """Yield ``(node_id, node_data, title)`` for every export node."""
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict) and node_data.get('class_type') in EXPORT_NODE_TYPES:
            yield node_id, node_data, node_data.get('_meta', {}).get('title', '')


def _has_designated_output_nodes(workflow: Dict[str, Any]) -> bool:
    """True when at least one export node is marked with the ``_output`` suffix.

    When that happens only the designated nodes receive the output prefix and
    output_dir, so the other exports' files stay out of the user's gallery.
    """
    has_output_nodes = any(
        title.lower().endswith(OUTPUT_SUFFIX)
        for _nid, _nd, title in _iter_export_nodes(workflow)
    )
    if not has_output_nodes:
        return False

    logger.info(f"Detected {OUTPUT_SUFFIX} suffix node(s) - only setting prefix "
                f"on designated output nodes")
    # Diagnostic: log all export nodes and their designation status
    for nid, nd, title in _iter_export_nodes(workflow):
        logger.info(f"  Export node {nid} ({nd.get('class_type')}): "
                    f"title='{title}', designated={title.lower().endswith(OUTPUT_SUFFIX)}")
    return True


def _widget_names_for(class_type: str) -> list:
    """Widget names for a node type: node_info cache first, manual table second."""
    from comfyui.node_info import get_widget_names as _get_ni_widget_names

    widget_list = _get_ni_widget_names(class_type)
    if widget_list is not None:
        return [w for w in widget_list if w is not None]
    return WIDGET_MAPPINGS.get(class_type, [])


def _is_node_already_handled(node_id, editable_by_node_id) -> bool:
    """True when the dynamic UI already wrote a value to this node.

    editable_values may be keyed by ``int`` or ``str`` node ids, so both forms
    are checked.
    """
    return str(node_id) in editable_by_node_id or int(node_id) in editable_by_node_id


def _apply_editable_prompt_node(node_id, node_title, inputs, prompt) -> bool:
    """Handle a ``TextEncodeQwenImageEditPlus`` node in the legacy prompt path.

    Only nodes titled ``..._editable`` are modified.

    Returns:
        True if this node is an editable prompt node.
    """
    if not node_title.endswith('_editable'):
        # Non-editable prompt node - log but don't modify
        logger.info(f"Skipping non-editable prompt node {node_id} "
                    f"(title: '{node_title}' - missing '_editable' suffix)")
        return False

    if prompt:
        inputs['prompt'] = prompt
        logger.info(f"Set editable prompt node {node_id} ({node_title}) to: "
                    f"{prompt[:50]}...")
    else:
        existing = inputs.get('prompt', '')
        if existing:
            logger.info(f"Keeping existing prompt in editable node {node_id} "
                        f"({node_title}): {str(existing)[:50]}...")
    return True


def _apply_output_dir(inputs, widget_list, class_type, node_id, node_title,
                      output_dir, has_output_nodes) -> None:
    """Set ``output_dir`` on any node that declares the widget."""
    if 'output_dir' not in widget_list or not output_dir:
        return
    # If _output nodes exist, skip output_dir on non-designated export nodes
    # so their files don't end up in the user's gallery directory
    if has_output_nodes and not node_title.lower().endswith(OUTPUT_SUFFIX):
        logger.info(f"Skipping output_dir for non-{OUTPUT_SUFFIX} export node "
                    f"{node_id} ({class_type}, title='{node_title}')")
        return
    inputs['output_dir'] = output_dir
    logger.info(f"Set {class_type} node {node_id} output_dir to: {output_dir}")


def _apply_export_prefix(inputs, class_type, node_id, node_title,
                         output_prefix, has_output_nodes) -> None:
    """Set the output filename prefix on an export node."""
    if class_type not in EXPORT_NODE_TYPES:
        return
    # If _output nodes exist, only set prefix on those
    if has_output_nodes and not node_title.lower().endswith(OUTPUT_SUFFIX):
        logger.info(f"Skipping non-{OUTPUT_SUFFIX} export node {node_id} "
                    f"({class_type}, title='{node_title}')")
        return
    prefix_key = EXPORT_NODE_TYPES[class_type]
    inputs[prefix_key] = output_prefix
    logger.info(f"Set {class_type} node {node_id} prefix to: {output_prefix}")


def _apply_seed(inputs, widget_list, class_type, node_id, seed) -> None:
    """Set the per-job seed on any sampler/generator node."""
    if 'seed' in widget_list:
        inputs['seed'] = seed
        logger.info(f"Set {class_type} node {node_id} seed to: {seed}")
    elif 'noise_seed' in widget_list:
        inputs['noise_seed'] = seed
        logger.info(f"Set {class_type} node {node_id} noise_seed to: {seed}")


def _apply_class_type_rules(workflow, editable_by_node_id, image_basename, prompt,
                            output_prefix, seed, output_dir, has_output_nodes) -> bool:
    """Apply the class_type-driven modifications to every node.

    This covers the legacy image/prompt injection (skipped for nodes the dynamic
    UI already handled) plus the capability-driven settings — output_dir,
    filename prefix and seed — which are applied regardless.

    Returns:
        True if an editable prompt node was found.
    """
    found_editable_prompt = False

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})
        node_title = node_data.get('_meta', {}).get('title', '')
        already_handled = _is_node_already_handled(node_id, editable_by_node_id)

        # LoadImage nodes - set input image filename (only if we have a legacy
        # image and the node was not already handled)
        if class_type == 'LoadImage' and image_basename and not already_handled:
            inputs['image'] = image_basename
            logger.info(f"Set LoadImage node {node_id} to: {image_basename}")
        elif class_type == 'TextEncodeQwenImageEditPlus' and not already_handled:
            if _apply_editable_prompt_node(node_id, node_title, inputs, prompt):
                found_editable_prompt = True

        # Generic handling based on node capabilities: this handles output_dir,
        # filename_prefix and seed for ANY node that supports them.
        widget_list = _widget_names_for(class_type)
        _apply_output_dir(inputs, widget_list, class_type, node_id, node_title,
                          output_dir, has_output_nodes)
        _apply_export_prefix(inputs, class_type, node_id, node_title,
                             output_prefix, has_output_nodes)
        _apply_seed(inputs, widget_list, class_type, node_id, seed)

    return found_editable_prompt


def _resolve_legacy_image_basename(input_image: Optional[str]) -> Optional[str]:
    """Basename for the legacy single-input image, rewritten to .png if converted."""
    from comfyui.image_convert import needs_conversion, get_png_basename

    if not input_image:
        return None
    image_basename = os.path.basename(input_image)
    if needs_conversion(input_image):
        image_basename = get_png_basename(image_basename)
    return image_basename


def modify_workflow_api_format(
    workflow: Dict[str, Any],
    input_image: Optional[str],
    prompt: Optional[str],
    output_prefix: str,
    seed: int,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None,
    output_dir: Optional[str] = None
) -> Tuple[Dict[str, Any], bool, Dict[str, str]]:
    """
    Modify workflow in API format (node IDs as keys with 'inputs' dict).

    Searches for nodes by class_type to be flexible with different workflows.
    Applies editable_values from dynamic UI widgets, then falls back to legacy behavior.

    Args:
        workflow: Workflow in API format
        input_image: Legacy input image path (can be None)
        prompt: Legacy prompt text (can be None)
        output_prefix: Output filename prefix
        seed: Random seed for samplers
        editable_values: Dict of node_id -> list of {'node': EditableNode, 'value': Any}
            Also supports legacy single-dict format per node_id.
        output_dir: Output directory for export nodes (FBX, GLB, etc.)

    Returns:
        Tuple of (modified_workflow, found_editable_prompt_node, files_to_copy)
        - files_to_copy: Dict mapping full paths to basenames for file copying
    """
    modified = copy.deepcopy(workflow)
    image_basename = _resolve_legacy_image_basename(input_image)

    _convert_preview_to_save_nodes(modified)

    editable_by_node_id, found_editable_prompt = _index_editable_nodes(editable_values)

    _log_workflow_summary(modified)

    # Apply values from the dynamic UI first, then the class_type rules below
    # fill in / override the pipeline-controlled settings.
    # Fan-out slots become concrete loader nodes before any value is applied,
    # so the normal appliers never see the multi-file entry. Empty optional
    # ('?') slots are removed outright rather than keeping a stale default.
    _expand_fanout_slots(modified, editable_values)
    _remove_empty_optional_slots(modified, editable_values)

    _apply_editable_values(modified, editable_values)

    # Nodes whose title carries an &if_/@if_ conditional are removed when the
    # referenced toggle is OFF, with pass-through rerouting of downstream refs.
    toggle_values = _collect_toggle_values(editable_values)
    nodes_to_remove = _collect_conditionally_disabled_nodes(modified, toggle_values)
    if nodes_to_remove:
        logger.info(f"[Bypass] Removing {len(nodes_to_remove)} conditionally "
                    f"disabled node(s)")
        remove_nodes_from_api_workflow(modified, nodes_to_remove)

    has_output_nodes = _has_designated_output_nodes(modified)

    if _apply_class_type_rules(modified, editable_by_node_id, image_basename, prompt,
                               output_prefix, seed, output_dir, has_output_nodes):
        found_editable_prompt = True

    # Normalize all file paths in workflow to basenames
    logger.info("Scanning workflow for file paths to normalize...")
    files_to_copy = normalize_file_paths_in_workflow(modified)
    if files_to_copy:
        logger.info(f"Found {len(files_to_copy)} file path(s) to copy and normalize")

    logger.info(f"=== Workflow Modification Summary ===")
    logger.info(f"Input image: {image_basename or '(from editable values)'}")
    logger.info(f"Prompt provided: {'Yes' if prompt else 'No (using workflow default or editable values)'}")
    logger.info(f"Editable values provided: {len(editable_values) if editable_values else 0}")
    logger.info(f"Found editable prompt node: {found_editable_prompt}")
    logger.info(f"Output prefix: {output_prefix}")
    logger.info(f"Files to copy: {len(files_to_copy)}")
    logger.info(f"=====================================")

    return modified, found_editable_prompt, files_to_copy


def modify_workflow(
    workflow: Dict[str, Any],
    input_image: Optional[str],
    prompt: Optional[str],
    output_prefix: str,
    seed: Optional[int] = None,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None,
    output_dir: Optional[str] = None
) -> Tuple[Dict[str, Any], bool, Dict[str, str]]:
    """
    Modify Qwen image edit workflow with user inputs.

    Converts UI/nodes format to API format if needed, then modifies.

    Args:
        workflow: Loaded workflow dict (API or nodes format)
        input_image: Path to input image (can be None if using editable_values)
        prompt: Edit prompt text (can be None if using editable_values)
        output_prefix: Output filename prefix
        seed: Random seed for KSampler (None = generate random)
        editable_values: Dict of node_id -> list of {'node': EditableNode, 'value': Any}
            Also supports legacy single-dict format per node_id.
        output_dir: Output directory for export nodes (FBX, GLB, etc.)

    Returns:
        Tuple of (modified_workflow, found_editable_prompt_node, files_to_copy)
        - modified_workflow: Modified workflow dictionary in API format
        - found_editable_prompt_node: True if a prompt node with "_editable" suffix was found
        - files_to_copy: Dict mapping full paths to basenames for file copying
    """
    # Generate random seed if not provided
    if seed is None:
        seed = random.randint(0, 2**63 - 1)

    # Convert to API format if needed
    if is_api_format(workflow):
        logger.info("Detected API format workflow")
        api_workflow = workflow
    else:
        # Pre-expansion: inject user-edited values into subgraph nodes' widgets_values
        # before subgraph expansion happens (inside convert_to_api_format).
        # This ensures the expanded internal nodes get the correct values.
        if editable_values and 'nodes' in workflow:
            from comfyui.workflow import _is_uuid
            workflow = copy.deepcopy(workflow)
            nodes_by_id = {n.get('id'): n for n in workflow.get('nodes', [])}

            for node_id, entries in editable_values.items():
                entry_list = entries if isinstance(entries, list) else [entries]
                raw_node = nodes_by_id.get(node_id)
                if not raw_node:
                    continue
                node_type = raw_node.get('type', '')
                if not _is_uuid(node_type):
                    continue

                # This is a subgraph node — update its widgets_values
                proxy_widgets = raw_node.get('properties', {}).get('proxyWidgets', [])
                widgets_values = raw_node.get('widgets_values', [])

                # Check if widgets_values is dict or list format
                widgets_values_is_dict = isinstance(widgets_values, dict)
                if not widgets_values_is_dict and not isinstance(widgets_values, list):
                    logger.warning(f"Subgraph node {node_id} has unexpected widgets_values type: {type(widgets_values)} - skipping")
                    continue

                if not proxy_widgets or not widgets_values:
                    continue

                for data in entry_list:
                    node_info = data.get('node')
                    value = data.get('value')
                    widget_name = getattr(node_info, 'widget_name', None)
                    if not widget_name:
                        continue

                    if widgets_values_is_dict:
                        # Dict format: set value by widget name directly
                        if widget_name in widgets_values:
                            widgets_values[widget_name] = value
                            logger.info(f"  Pre-expansion: set subgraph node {node_id} "
                                        f"widget '{widget_name}' = {repr(value)[:60]}")
                    else:
                        # List format: find the proxyWidgets index for this widget_name
                        for pw_idx, pw_entry in enumerate(proxy_widgets):
                            if (isinstance(pw_entry, (list, tuple)) and len(pw_entry) >= 2
                                    and pw_entry[1] == widget_name and pw_idx < len(widgets_values)):
                                widgets_values[pw_idx] = value
                                logger.info(f"  Pre-expansion: set subgraph node {node_id} "
                                            f"widget '{widget_name}' [idx {pw_idx}] = {repr(value)[:60]}")
                                break

        logger.info("Detected UI/nodes format workflow - converting to API format...")
        api_workflow = convert_to_api_format(workflow)
        logger.info(f"Converted workflow with {len(api_workflow)} nodes")

    # Modify the API format workflow
    return modify_workflow_api_format(api_workflow, input_image, prompt, output_prefix, seed, editable_values, output_dir)
