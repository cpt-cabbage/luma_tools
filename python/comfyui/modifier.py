"""
ComfyUI Workflow Modification.

Handles modifying workflow parameters like seeds, prompts, input images,
and output prefixes based on user inputs and editable node values.
"""

import os
import copy
import logging
import random
from typing import Optional, Dict, Any, Tuple

from comfyui.workflow import is_api_format, convert_to_api_format
from comfyui.node_configs import WIDGET_MAPPINGS, EXPORT_NODE_TYPES, OUTPUT_SUFFIX

logger = logging.getLogger(__name__)

# File extensions that indicate a file path input
FILE_EXTENSIONS = {
    # Images
    '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.webp', '.exr',
    # Videos
    '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v',
    # 3D Models
    '.obj', '.fbx', '.glb', '.gltf', '.usd', '.usda', '.usdc', '.usdz', '.ply', '.stl',
    # Audio
    '.wav', '.mp3', '.ogg', '.flac', '.m4a', '.aac',
    # Other
    '.json', '.txt', '.safetensors', '.pt', '.pth', '.ckpt', '.bin'
}


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
    from comfyui.image_convert import needs_conversion, get_png_basename

    modified = copy.deepcopy(workflow)
    if input_image:
        image_basename = os.path.basename(input_image)
        if needs_conversion(input_image):
            image_basename = get_png_basename(image_basename)
    else:
        image_basename = None
    found_editable_prompt = False

    # Convert PreviewImage nodes to SaveImage nodes so we can control the output filename
    # PreviewImage saves to temp folder with temp names, SaveImage allows filename_prefix
    preview_nodes_converted = []
    for node_id, node_data in modified.items():
        if isinstance(node_data, dict) and node_data.get('class_type') == 'PreviewImage':
            node_data['class_type'] = 'SaveImage'
            # SaveImage needs filename_prefix input (will be set later in EXPORT_NODE_TYPES handling)
            if 'inputs' not in node_data:
                node_data['inputs'] = {}
            preview_nodes_converted.append(node_id)

    if preview_nodes_converted:
        logger.info(f"Converted {len(preview_nodes_converted)} PreviewImage node(s) to SaveImage: {preview_nodes_converted}")

    # Build a lookup of node_id -> True from editable_values for "already handled" checks
    editable_by_node_id = {}
    if editable_values:
        for node_id, entries in editable_values.items():
            entry_list = entries if isinstance(entries, list) else [entries]
            editable_by_node_id[node_id] = True
            for data in entry_list:
                if data.get('node') and data['node'].widget_type == 'text':
                    found_editable_prompt = True

    # Log workflow summary for debugging
    node_types = {}
    for node_id, node_data in modified.items():
        if isinstance(node_data, dict) and 'class_type' in node_data:
            ct = node_data.get('class_type')
            meta = node_data.get('_meta', {})
            title = meta.get('title', '')
            if ct not in node_types:
                node_types[ct] = []
            node_types[ct].append(f"{node_id}:{title}" if title else node_id)
    logger.info(f"Workflow contains {len(modified)} nodes:")
    for ct, nodes in sorted(node_types.items()):
        logger.info(f"  {ct}: {nodes}")

    # Apply editable_values first (from dynamic UI)
    # Format: {node_id: [{'node': EditableNode, 'value': Any}, ...]} (list-per-node)
    # Also supports legacy format: {node_id: {'node': EditableNode, 'value': Any}}

    if editable_values:
        total_entries = sum(len(v) if isinstance(v, list) else 1 for v in editable_values.values())
        logger.info(f"=== Applying {total_entries} editable values across {len(editable_values)} nodes ===")
        for node_id, entries in editable_values.items():
            # Normalize to list format
            entry_list = entries if isinstance(entries, list) else [entries]

            for data in entry_list:
                node_id_str = str(node_id)
                node_info = data.get('node')
                value = data.get('value')

                if node_id_str not in modified:
                    # For subgraph nodes, the node_id won't be in the API format
                    # (subgraphs are expanded into internal nodes). Skip silently.
                    if node_info and hasattr(node_info, 'node_type'):
                        from comfyui.workflow import _is_uuid
                        if _is_uuid(node_info.node_type):
                            continue
                    logger.warning(f"  Node {node_id} not found in workflow")
                    continue

                node_data = modified[node_id_str]
                inputs = node_data.get('inputs', {})
                node_type = node_info.node_type if node_info else 'unknown'
                widget_type = node_info.widget_type if node_info else 'unknown'

                # Check if this is a settings node with explicit widget_name
                # (from SettingsNode with widget_name attribute)
                widget_name = getattr(node_info, 'widget_name', None)

                # Apply value based on widget type
                if widget_type == 'text':
                    if widget_name:
                        inputs[widget_name] = value
                    elif 'prompt' in inputs:
                        inputs['prompt'] = value
                    elif 'text' in inputs:
                        inputs['text'] = value
                    else:
                        inputs['text'] = value
                    logger.info(f"  Set text node {node_id} ({node_type}): {str(value)[:50]}...")
                elif widget_type == 'image':
                    if value:
                        # Handle both string paths and lists (from batch selector)
                        if isinstance(value, list):
                            image_path = value[0] if value else None
                        else:
                            image_path = value

                        if image_path:
                            basename = os.path.basename(image_path)
                            # Rewrite to .png if format needs conversion
                            if needs_conversion(image_path):
                                basename = get_png_basename(basename)
                                logger.info(f"  Image {os.path.basename(image_path)} will be converted to {basename}")
                            inputs['image'] = basename
                            logger.info(f"  Set image node {node_id} ({node_type}): {basename}")
                    else:
                        # No image provided — leave node as-is with its workflow default
                        logger.info(f"  Image node {node_id} ({node_type}): no file selected, keeping workflow default")
                elif widget_type == 'int':
                    # For settings nodes, use explicit widget_name if available
                    if widget_name:
                        try:
                            inputs[widget_name] = int(value)
                            logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {value}")
                        except (ValueError, TypeError):
                            logger.warning(f"  Failed to convert {value} to int for {widget_name}")
                    else:
                        # Default behavior for editable nodes (seed-related)
                        inputs['seed'] = value
                        inputs['noise_seed'] = value
                        logger.info(f"  Set int node {node_id} ({node_type}): {value}")
                elif widget_type == 'float':
                    # For settings nodes, use explicit widget_name if available
                    if widget_name:
                        try:
                            inputs[widget_name] = float(value)
                            logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {value}")
                        except (ValueError, TypeError):
                            logger.warning(f"  Failed to convert {value} to float for {widget_name}")
                    else:
                        # Default behavior for editable nodes
                        inputs['cfg'] = value
                        logger.info(f"  Set float node {node_id} ({node_type}): {value}")
                elif widget_type == 'string':
                    if widget_name:
                        inputs[widget_name] = value
                        logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {value}")
                    else:
                        inputs['filename_prefix'] = value
                        logger.info(f"  Set string node {node_id} ({node_type}): {value}")
                elif widget_type == 'combo':
                    # Combo box - use widget_name if available
                    if widget_name:
                        inputs[widget_name] = value
                        logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {value}")
                    else:
                        logger.info(f"  Combo node {node_id} ({node_type}): {value} (no widget_name)")
                elif widget_type == 'toggle':
                    # Toggle/switch value (0 or 1)
                    int_value = 1 if value else 0
                    if widget_name:
                        inputs[widget_name] = int_value
                        logger.info(f"  Set {widget_name} on node {node_id} ({node_type}): {int_value}")
                    else:
                        inputs['index'] = int_value
                        logger.info(f"  Set toggle node {node_id} ({node_type}): {int_value}")
                elif widget_type == '3d_model':
                    # 3D model file path
                    if value:
                        # Handle both string paths and lists
                        if isinstance(value, list):
                            model_path = value[0] if value else None
                        else:
                            model_path = value

                        if model_path:
                            inputs['model_file'] = os.path.basename(model_path)
                            logger.info(f"  Set 3D model node {node_id} ({node_type}): {os.path.basename(model_path)}")
                    else:
                        # No model provided — leave node as-is with its workflow default
                        logger.info(f"  3D model node {node_id} ({node_type}): no file selected, keeping workflow default")
                elif widget_type == 'video':
                    # Video file path
                    if value:
                        # Handle both string paths and lists (from batch selector)
                        if isinstance(value, list):
                            video_path = value[0] if value else None
                        else:
                            video_path = value

                        if video_path:
                            inputs['video'] = os.path.basename(video_path)
                            logger.info(f"  Set video node {node_id} ({node_type}): {os.path.basename(video_path)}")
                    else:
                        # No video provided — leave node as-is with its workflow default
                        logger.info(f"  Video node {node_id} ({node_type}): no file selected, keeping workflow default")
                elif widget_type == 'directory':
                    # Directory path
                    if value:
                        # Use the widget_name to set the correct input field
                        if widget_name:
                            inputs[widget_name] = str(value)
                            logger.info(f"  Set directory on node {node_id} ({node_type}): {widget_name} = {value}")
                        else:
                            # Fallback to 'directory' if no specific widget name
                            inputs['directory'] = str(value)
                            logger.info(f"  Set directory on node {node_id} ({node_type}): {value}")

    # Build a map of toggle node names to their values (True/False)
    # Toggle nodes have names like "Ultrashape_Only_editable" - extract base name
    toggle_values = {}
    for node_id, entries in (editable_values or {}).items():
        entry_list = entries if isinstance(entries, list) else [entries]
        for data in entry_list:
            node_info = data.get('node')
            if node_info and node_info.widget_type == 'toggle':
                title = node_info.title or ''
                # Extract base name (remove _editable suffix)
                base_name = title.replace('_editable', '').strip()
                value = bool(data.get('value'))
                base_key = base_name.lower()
                if base_key in toggle_values:
                    logger.warning(f"[Toggle] Duplicate toggle name '{base_name}' "
                                   f"(node {node_id}), overwriting with value: {value}")
                toggle_values[base_key] = value
                logger.info(f"[Toggle] Found toggle '{base_name}' = {value}")

    # Process nodes with @if_ conditional in their title
    # Format: "Node Name_editable&if_ToggleName" or "Node Name&if_ToggleName"
    # If the referenced toggle is False, remove the node from the workflow
    # with pass-through rerouting of downstream references
    nodes_to_remove = set()
    for node_id, node_data in modified.items():
        if not isinstance(node_data, dict):
            continue
        meta = node_data.get('_meta', {})
        title = meta.get('title', '')

        # Check for &if_ or @if_ pattern in title
        if_match = None
        for separator in ['&if_', '@if_']:
            if separator in title.lower():
                # Extract the toggle name after &if_ or @if_
                parts = title.lower().split(separator)
                if len(parts) > 1:
                    # Get toggle name (may have _editable or other suffixes)
                    toggle_ref = parts[1].split('_editable')[0].split('&')[0].strip()
                    if_match = toggle_ref
                    break

        if if_match:
            # Check if this toggle exists and its value
            toggle_value = toggle_values.get(if_match)
            if toggle_value is not None:
                if not toggle_value:
                    # Toggle is OFF - mark for removal
                    class_type = node_data.get('class_type', 'unknown')
                    nodes_to_remove.add(str(node_id))
                    logger.info(f"[Bypass] Will remove node {node_id} ({class_type}) - '{if_match}' is OFF")
            else:
                logger.warning(f"[Bypass] Node {node_id} references toggle '{if_match}' but toggle not found")

    if nodes_to_remove:
        logger.info(f"[Bypass] Removing {len(nodes_to_remove)} conditionally disabled node(s)")
        remove_nodes_from_api_workflow(modified, nodes_to_remove)

    # Check if any export node has _output suffix (primary output designation)
    # If so, only those nodes get the output prefix — others are skipped
    has_output_nodes = False
    for _nid, _nd in modified.items():
        if isinstance(_nd, dict) and _nd.get('class_type') in EXPORT_NODE_TYPES:
            _title = _nd.get('_meta', {}).get('title', '')
            if _title.lower().endswith(OUTPUT_SUFFIX):
                has_output_nodes = True
                break
    if has_output_nodes:
        logger.info(f"Detected {OUTPUT_SUFFIX} suffix node(s) - only setting prefix on designated output nodes")
        # Diagnostic: log all export nodes and their designation status
        for _nid, _nd in modified.items():
            if isinstance(_nd, dict) and _nd.get('class_type') in EXPORT_NODE_TYPES:
                _title = _nd.get('_meta', {}).get('title', '')
                _is_designated = _title.lower().endswith(OUTPUT_SUFFIX)
                logger.info(f"  Export node {_nid} ({_nd.get('class_type')}): "
                            f"title='{_title}', designated={_is_designated}")

    # Find and modify nodes by class_type
    # Apply special handling for certain node types (seeds, output prefixes, directories)
    # even if they were already handled by editable_values
    from comfyui.node_info import get_widget_names as _get_ni_widget_names
    for node_id, node_data in modified.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})
        meta = node_data.get('_meta', {})
        node_title = meta.get('title', '')

        # Check if this node was already modified by editable_values
        # Use str() for consistent key type comparison
        node_already_handled = str(node_id) in editable_by_node_id or int(node_id) in editable_by_node_id

        # LoadImage nodes - set input image filename (only if we have a legacy image and not already handled)
        if class_type == 'LoadImage' and image_basename and not node_already_handled:
            inputs['image'] = image_basename
            logger.info(f"Set LoadImage node {node_id} to: {image_basename}")

        # TextEncodeQwenImageEditPlus nodes - only modify if title ends with "_editable" and not already handled
        elif class_type == 'TextEncodeQwenImageEditPlus' and not node_already_handled:
            if node_title.endswith('_editable'):
                found_editable_prompt = True
                if prompt:
                    inputs['prompt'] = prompt
                    logger.info(f"Set editable prompt node {node_id} ({node_title}) to: {prompt[:50]}...")
                else:
                    existing = inputs.get('prompt', '')
                    if existing:
                        logger.info(f"Keeping existing prompt in editable node {node_id} ({node_title}): {str(existing)[:50]}...")
            else:
                # Non-editable prompt node - log but don't modify
                logger.info(f"Skipping non-editable prompt node {node_id} (title: '{node_title}' - missing '_editable' suffix)")

        # Generic handling based on node capabilities
        # This handles output_dir, filename_prefix, and seed for ANY node that supports them

        # Get widget names: try node_info cache first, fall back to manual WIDGET_MAPPINGS
        widget_list = _get_ni_widget_names(class_type)
        if widget_list is not None:
            widget_list = [w for w in widget_list if w is not None]
        else:
            widget_list = WIDGET_MAPPINGS.get(class_type, [])

        # Set output_dir for any node that supports it
        if 'output_dir' in widget_list and output_dir:
            # If _output nodes exist, skip output_dir on non-designated export nodes
            # so their files don't end up in the user's gallery directory
            if has_output_nodes and not node_title.lower().endswith(OUTPUT_SUFFIX):
                logger.info(f"Skipping output_dir for non-{OUTPUT_SUFFIX} export node {node_id} ({class_type}, title='{node_title}')")
            else:
                inputs['output_dir'] = output_dir
                logger.info(f"Set {class_type} node {node_id} output_dir to: {output_dir}")

        # Set filename_prefix for export nodes
        if class_type in EXPORT_NODE_TYPES:
            # If _output nodes exist, only set prefix on those
            if has_output_nodes and not node_title.lower().endswith(OUTPUT_SUFFIX):
                logger.info(f"Skipping non-{OUTPUT_SUFFIX} export node {node_id} ({class_type}, title='{node_title}')")
            else:
                prefix_key = EXPORT_NODE_TYPES[class_type]
                inputs[prefix_key] = output_prefix
                logger.info(f"Set {class_type} node {node_id} prefix to: {output_prefix}")

        # Set seed for sampler/generator nodes
        if 'seed' in widget_list:
            inputs['seed'] = seed
            logger.info(f"Set {class_type} node {node_id} seed to: {seed}")
        elif 'noise_seed' in widget_list:
            inputs['noise_seed'] = seed
            logger.info(f"Set {class_type} node {node_id} noise_seed to: {seed}")

    # Normalize all file paths in workflow to basenames
    logger.info("Scanning workflow for file paths to normalize...")
    files_to_copy = normalize_file_paths_in_workflow(modified)
    if files_to_copy:
        logger.info(f"Found {len(files_to_copy)} file path(s) to copy and normalize")

    # Summary
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
