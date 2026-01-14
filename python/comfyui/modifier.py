"""
ComfyUI Workflow Modification.

Handles modifying workflow parameters like seeds, prompts, input images,
and output prefixes based on user inputs and editable node values.
"""

import os
import copy
import random
from typing import Optional, Dict, Any, Tuple

from comfyui.workflow import is_api_format, convert_to_api_format


def modify_workflow_api_format(
    workflow: Dict[str, Any],
    input_image: Optional[str],
    prompt: Optional[str],
    output_prefix: str,
    seed: int,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None
) -> Tuple[Dict[str, Any], bool]:
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
        editable_values: Dict of node_id -> {'node': EditableNode, 'value': Any}

    Returns:
        Tuple of (modified_workflow, found_editable_prompt_node)
    """
    modified = copy.deepcopy(workflow)
    image_basename = os.path.basename(input_image) if input_image else None
    found_editable_prompt = False

    # Build a lookup of node_id -> value from editable_values
    editable_by_node_id = {}
    if editable_values:
        for node_id, data in editable_values.items():
            editable_by_node_id[node_id] = data
            # Mark that we found editable nodes
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
    print(f"Workflow contains {len(modified)} nodes:")
    for ct, nodes in sorted(node_types.items()):
        print(f"  {ct}: {nodes}")

    # Apply editable_values first (from dynamic UI)
    if editable_values:
        print(f"\n=== Applying {len(editable_values)} editable values ===")
        for node_id, data in editable_values.items():
            node_id_str = str(node_id)
            node_info = data.get('node')
            value = data.get('value')

            if node_id_str not in modified:
                print(f"  Warning: Node {node_id} not found in workflow")
                continue

            node_data = modified[node_id_str]
            inputs = node_data.get('inputs', {})
            node_type = node_info.node_type if node_info else 'unknown'
            widget_type = node_info.widget_type if node_info else 'unknown'

            # Apply value based on widget type
            if widget_type == 'text':
                inputs['prompt'] = value
                inputs['text'] = value  # Some nodes use 'text' instead of 'prompt'
                print(f"  Set text node {node_id} ({node_type}): {str(value)[:50]}...")
            elif widget_type == 'image':
                if value:
                    inputs['image'] = os.path.basename(value)
                    print(f"  Set image node {node_id} ({node_type}): {os.path.basename(value)}")
            elif widget_type == 'int':
                inputs['seed'] = value
                inputs['noise_seed'] = value
                print(f"  Set int node {node_id} ({node_type}): {value}")
            elif widget_type == 'float':
                inputs['cfg'] = value
                print(f"  Set float node {node_id} ({node_type}): {value}")
            elif widget_type == 'string':
                inputs['filename_prefix'] = value
                print(f"  Set string node {node_id} ({node_type}): {value}")
            elif widget_type == 'toggle':
                # Toggle/switch value (0 or 1)
                int_value = 1 if value else 0
                inputs['index'] = int_value
                print(f"  Set toggle node {node_id} ({node_type}): {int_value}")
            elif widget_type == '3d_model':
                # 3D model file path
                if value:
                    inputs['model_file'] = os.path.basename(value)
                    print(f"  Set 3D model node {node_id} ({node_type}): {os.path.basename(value)}")

    # Build a map of toggle node names to their values (True/False)
    # Toggle nodes have names like "Ultrashape_Only_editable" - extract base name
    toggle_values = {}
    for node_id, data in (editable_values or {}).items():
        node_info = data.get('node')
        if node_info and node_info.widget_type == 'toggle':
            title = node_info.title or ''
            # Extract base name (remove _editable suffix)
            base_name = title.replace('_editable', '').strip()
            value = bool(data.get('value'))
            toggle_values[base_name.lower()] = value
            print(f"[Toggle] Found toggle '{base_name}' = {value}")

    # Process nodes with @if_ conditional in their title
    # Format: "Node Name_editable&if_ToggleName" or "Node Name&if_ToggleName"
    # If the referenced toggle is False, bypass this node
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
                    # Toggle is OFF - bypass this node
                    node_data['mode'] = 4  # 4 = bypassed
                    class_type = node_data.get('class_type', 'unknown')
                    print(f"[Bypass] Bypassed node {node_id} ({class_type}) - '{if_match}' is OFF")
            else:
                print(f"[Bypass] Warning: Node {node_id} references toggle '{if_match}' but toggle not found")

    # Find and modify nodes by class_type
    # Apply special handling for certain node types (seeds, output prefixes, directories)
    # even if they were already handled by editable_values
    for node_id, node_data in modified.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})
        meta = node_data.get('_meta', {})
        node_title = meta.get('title', '')

        # Check if this node was already modified by editable_values
        node_already_handled = int(node_id) in editable_by_node_id

        # LoadImage nodes - set input image filename (only if we have a legacy image and not already handled)
        if class_type == 'LoadImage' and image_basename and not node_already_handled:
            inputs['image'] = image_basename
            print(f"Set LoadImage node {node_id} to: {image_basename}")

        # TextEncodeQwenImageEditPlus nodes - only modify if title ends with "_editable" and not already handled
        elif class_type == 'TextEncodeQwenImageEditPlus' and not node_already_handled:
            if node_title.endswith('_editable'):
                found_editable_prompt = True
                if prompt:
                    inputs['prompt'] = prompt
                    print(f"Set editable prompt node {node_id} ({node_title}) to: {prompt[:50]}...")
                else:
                    existing = inputs.get('prompt', '')
                    if existing:
                        print(f"Keeping existing prompt in editable node {node_id} ({node_title}): {str(existing)[:50]}...")
            else:
                # Non-editable prompt node - log but don't modify
                print(f"Skipping non-editable prompt node {node_id} (title: '{node_title}' - missing '_editable' suffix)")

        # SaveImage nodes - set output prefix (always apply, even if editable)
        elif class_type == 'SaveImage':
            inputs['filename_prefix'] = output_prefix
            print(f"Set SaveImage node {node_id} prefix to: {output_prefix}")

        # HYMotionExportFBX nodes - clear output_dir so files go to main output, set prefix (always apply)
        elif class_type == 'HYMotionExportFBX':
            inputs['output_dir'] = ''  # Empty = use ComfyUI's output directory directly
            inputs['filename_prefix'] = output_prefix
            print(f"Set HYMotionExportFBX node {node_id}: output_dir='', prefix={output_prefix}")

        # Trellis2ExportGLB nodes - set output prefix (always apply)
        elif class_type == 'Trellis2ExportGLB':
            inputs['filename_prefix'] = output_prefix
            print(f"Set Trellis2ExportGLB node {node_id} prefix to: {output_prefix}")

        # Trellis2ExportMesh nodes - set output prefix (always apply)
        elif class_type == 'Trellis2ExportMesh':
            inputs['filename_prefix'] = output_prefix
            print(f"Set Trellis2ExportMesh node {node_id} prefix to: {output_prefix}")

        # UltraShapeSaveGLB nodes - set output prefix (always apply)
        # NOTE: output_dir cannot be reliably cleared - node writes to subdirectory regardless
        # The move_output_files function searches recursively to handle this
        elif class_type == 'UltraShapeSaveGLB':
            inputs['filename_prefix'] = output_prefix
            print(f"Set UltraShapeSaveGLB node {node_id}: prefix={output_prefix}")

        # Trellis2ImageToShape nodes - set seed (always apply)
        elif class_type == 'Trellis2ImageToShape':
            inputs['seed'] = seed
            print(f"Set Trellis2ImageToShape node {node_id} seed to: {seed}")

        # Trellis2ShapeToTexturedMesh nodes - set seed (always apply)
        elif class_type == 'Trellis2ShapeToTexturedMesh':
            inputs['seed'] = seed
            print(f"Set Trellis2ShapeToTexturedMesh node {node_id} seed to: {seed}")

        # Trellis2MeshWithVoxelAdvancedGenerator nodes - set seed (always apply)
        elif class_type == 'Trellis2MeshWithVoxelAdvancedGenerator':
            inputs['seed'] = seed
            print(f"Set Trellis2MeshWithVoxelAdvancedGenerator node {node_id} seed to: {seed}")

        # KSampler nodes - set seed (always apply)
        elif class_type == 'KSampler':
            inputs['seed'] = seed
            print(f"Set KSampler node {node_id} seed to: {seed}")

        # SamplerCustomAdvanced / RandomNoise nodes - set seed (always apply)
        elif class_type == 'RandomNoise':
            inputs['noise_seed'] = seed
            print(f"Set RandomNoise node {node_id} seed to: {seed}")

        # HYMotionGenerate nodes - set seed (always apply)
        elif class_type == 'HYMotionGenerate':
            inputs['seed'] = seed
            print(f"Set HYMotionGenerate node {node_id} seed to: {seed}")

    # Summary
    print(f"\n=== Workflow Modification Summary ===")
    print(f"Input image: {image_basename or '(from editable values)'}")
    print(f"Prompt provided: {'Yes' if prompt else 'No (using workflow default or editable values)'}")
    print(f"Editable values provided: {len(editable_values) if editable_values else 0}")
    print(f"Found editable prompt node: {found_editable_prompt}")
    print(f"Output prefix: {output_prefix}")
    print(f"=====================================\n")

    return modified, found_editable_prompt


def modify_workflow(
    workflow: Dict[str, Any],
    input_image: Optional[str],
    prompt: Optional[str],
    output_prefix: str,
    seed: Optional[int] = None,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None
) -> Tuple[Dict[str, Any], bool]:
    """
    Modify Qwen image edit workflow with user inputs.

    Converts UI/nodes format to API format if needed, then modifies.

    Args:
        workflow: Loaded workflow dict (API or nodes format)
        input_image: Path to input image (can be None if using editable_values)
        prompt: Edit prompt text (can be None if using editable_values)
        output_prefix: Output filename prefix
        seed: Random seed for KSampler (None = generate random)
        editable_values: Dict of node_id -> {'node': EditableNode, 'value': Any}

    Returns:
        Tuple of (modified_workflow, found_editable_prompt_node)
        - modified_workflow: Modified workflow dictionary in API format
        - found_editable_prompt_node: True if a prompt node with "_editable" suffix was found
    """
    # Generate random seed if not provided
    if seed is None:
        seed = random.randint(0, 2**63 - 1)

    # Convert to API format if needed
    if is_api_format(workflow):
        print("Detected API format workflow")
        api_workflow = workflow
    else:
        print("Detected UI/nodes format workflow - converting to API format...")
        api_workflow = convert_to_api_format(workflow)
        print(f"Converted workflow with {len(api_workflow)} nodes")

    # Modify the API format workflow
    return modify_workflow_api_format(api_workflow, input_image, prompt, output_prefix, seed, editable_values)
