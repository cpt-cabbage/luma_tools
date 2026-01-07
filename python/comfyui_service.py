"""
ComfyUI Service Module.

Handles ComfyUI workflow manipulation and Deadline submission.
"""

import os
import json
import copy
import random
import subprocess
from typing import Optional, Callable, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from config import (
    DEADLINE_PATH,
    DEADLINE_POOL,
    DEADLINE_GROUP_COMPFYUI,
    DEADLINE_PRIORITY_COMFYUI,
    DEADLINE_DEPARTMENT,
    COMFYUI_SUPPORTED_EXTENSIONS,
    COMFYUI_OUTPUT_EXTENSIONS,
)
from settings_manager import (
    get_comfyui_path, get_comfyui_mode, get_comfyui_python_path,
    get_comfyui_fast_mode, get_comfyui_fp16_accumulation
)


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


@dataclass
class EditableNode:
    """Represents an editable node extracted from a workflow."""
    node_id: int
    node_type: str
    title: str
    display_name: str  # User-friendly name derived from title
    widget_type: str   # 'text', 'image', 'int', 'float', 'combo'
    current_value: Any = None
    options: List[str] = field(default_factory=list)  # For combo boxes


# Mapping of node types to their editable widget configurations
# Format: {node_type: [(widget_index, widget_name, widget_type), ...]}
EDITABLE_NODE_CONFIGS = {
    'LoadImage': [(0, 'image', 'image')],
    'TextEncodeQwenImageEditPlus': [(0, 'prompt', 'text')],
    'CLIPTextEncode': [(0, 'text', 'text')],
    'HYMotionEncodeText': [(0, 'text', 'text')],  # HY-Motion text prompt
    'KSampler': [
        (0, 'seed', 'int'),
        (2, 'steps', 'int'),
        (3, 'cfg', 'float'),
    ],
    'SaveImage': [(0, 'filename_prefix', 'string')],
    'HYMotionExportFBX': [(1, 'filename_prefix', 'string')],  # output_dir auto-set to use main output
}


def extract_editable_nodes(workflow_path: str) -> List[EditableNode]:
    """
    Extract all nodes with '_editable' suffix in their title from a workflow.

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
        print(f"Error loading workflow for editable nodes: {e}")
        return []

    nodes = workflow.get('nodes', [])
    editable_nodes = []

    for node in nodes:
        title = node.get('title', '')
        if not title.endswith('_editable'):
            continue

        # Skip muted/bypassed nodes
        mode = node.get('mode', 0)
        if mode in (2, 4):
            continue

        node_id = node.get('id')
        node_type = node.get('type')
        widgets_values = node.get('widgets_values', [])

        # Create display name from title (remove _editable suffix and clean up)
        display_name = title.replace('_editable', '').replace('_', ' ').strip()
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
                    current_value=current_value,
                ))
        else:
            # Unknown node type - try to create a generic text widget
            print(f"Unknown editable node type: {node_type} (title: {title})")
            if widgets_values:
                editable_nodes.append(EditableNode(
                    node_id=node_id,
                    node_type=node_type,
                    title=title,
                    display_name=display_name,
                    widget_type='text',
                    current_value=str(widgets_values[0]) if widgets_values else '',
                ))

    print(f"Found {len(editable_nodes)} editable nodes in workflow")
    for node in editable_nodes:
        print(f"  - {node.display_name} ({node.node_type}): {node.widget_type}")

    return editable_nodes


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

    # First pass: collect all node IDs that will be skipped (muted/bypassed)
    skipped_node_ids = set()
    skip_types = [
        'Reroute', 'Note', 'PrimitiveNode',
        # Note/comment nodes from various extensions
        'MarkdownNote', 'CR Text', 'ShowText', 'ShowTextForGPT',
        'Note+', 'NoteNode', 'CommentNode',
        # Preview/display nodes that don't affect output
        'PreviewImage', 'PreviewBridge', 'Preview3D',
    ]
    for node in nodes:
        node_id = node.get('id')
        node_type = node.get('type')
        node_mode = node.get('mode', 0)
        # Skip muted or bypassed nodes (mode 2 = bypass, mode 4 = mute)
        if node_mode in (2, 4):
            skipped_node_ids.add(node_id)
            print(f"Will skip node {node_id} ({node_type}) - mode {node_mode} (muted/bypassed)")
        # Skip certain node types
        elif node_type in skip_types or node_type is None:
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
        node_mode = node.get('mode', 0)  # 0=normal, 2=bypassed, 4=muted
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
        # We need to map them to input names based on the node type
        # This is a simplified mapping - real conversion requires node definitions

        # Common widget input names by node type
        # Order matters - widgets_values are positional
        widget_mappings = {
            # Core ComfyUI nodes
            'LoadImage': ['image', 'upload'],
            'SaveImage': ['filename_prefix'],
            'KSampler': ['seed', 'control_after_generate', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise'],
            'KSamplerAdvanced': ['add_noise', 'noise_seed', 'control_after_generate', 'steps', 'cfg', 'sampler_name', 'scheduler', 'start_at_step', 'end_at_step', 'return_with_leftover_noise'],
            'SamplerCustomAdvanced': ['noise_seed', 'control_after_generate'],
            'CLIPTextEncode': ['text'],
            'EmptyLatentImage': ['width', 'height', 'batch_size'],
            'VAEDecode': [],
            'VAEEncode': [],
            'CheckpointLoaderSimple': ['ckpt_name'],
            'LoraLoader': ['lora_name', 'strength_model', 'strength_clip'],
            # Loader nodes
            'VAELoader': ['vae_name'],
            'CLIPLoader': ['clip_name', 'type', 'device'],
            'UNETLoader': ['unet_name', 'weight_dtype'],
            'LoraLoaderModelOnly': ['lora_name', 'strength_model'],
            'DualCLIPLoader': ['clip_name1', 'clip_name2', 'type'],
            # Sampler/scheduler nodes
            'KSamplerSelect': ['sampler_name'],
            'BasicScheduler': ['scheduler', 'steps', 'denoise'],
            'BasicGuider': [],
            'RandomNoise': ['noise_seed', 'control_after_generate'],
            'SplitSigmas': ['step'],
            'FlipSigmas': [],
            # Model modification nodes
            'ModelSamplingAuraFlow': ['shift'],
            'ModelSamplingFlux': ['max_shift', 'base_shift', 'width', 'height'],
            'CFGNorm': ['strength'],
            'PatchModelAddDownscale': ['block_number', 'downscale_factor', 'start_percent', 'end_percent', 'downscale_after_skip', 'downscale_method', 'upscale_method'],
            # Text/prompt nodes
            'TextEncodeQwenImageEditPlus': ['prompt'],
            'CLIPTextEncodeFlux': ['clip_l', 'guidance'],
            'FluxGuidance': ['guidance'],
            # Image processing nodes
            'FluxKontextImageScale': [],  # No widgets, just connections
            'ResizeImagesByLongerEdge': ['longer_edge'],
            'ImageScale': ['upscale_method', 'width', 'height', 'crop'],
            'ImageScaleBy': ['upscale_method', 'scale_by'],
            'ImageInvert': [],
            'ImageBatch': [],
            'RepeatLatentBatch': ['amount'],
            # Latent nodes
            'LatentFromBatch': ['batch_index', 'length'],
            'SetLatentNoiseMask': [],
            'EmptySD3LatentImage': ['width', 'height', 'batch_size'],
            # Conditioning nodes
            'ConditioningCombine': [],
            'ConditioningSetTimestepRange': ['start', 'end'],
            'InstructPixToPixConditioning': [],
            # Utility nodes
            'GetImageSizeAndCount': [],
            'CropImage': ['width', 'height', 'x', 'y'],
            # Note/display nodes (no widgets needed in API)
            'MarkdownNote': [],
            # Image scaling nodes
            'ImageScaleToTotalPixels': ['upscale_method', 'megapixels', 'resolution_steps'],
            # Flux Kontext nodes
            'FluxKontextMultiReferenceLatentMethod': ['reference_latents_method'],
            # HYMotion nodes
            'HYMotionLoadNetwork': ['model_name'],
            'HYMotionLoadLLMGGUF': ['gguf_file'],
            'HYMotionGenerate': ['duration', 'seed', 'control_after_generate', 'cfg_scale', 'num_samples'],
            'HYMotionPreview': ['sample_index', 'frame_step', 'image_size'],
            'HYMotionEncodeText': ['text'],
            'HYMotionExportFBX': ['output_dir', 'filename_prefix'],
        }

        # Get widget names for this node type
        widget_names = widget_mappings.get(node_type, None)

        # For nodes in our mapping, use the defined widget order
        if widgets_values and widget_names is not None:
            for i, widget_name in enumerate(widget_names):
                if i < len(widgets_values) and widget_name not in inputs:
                    value = widgets_values[i]
                    # Skip control_after_generate - it's not an actual input
                    if widget_name != 'control_after_generate':
                        inputs[widget_name] = value
        elif widgets_values and widget_names is None:
            # For unknown nodes, try to extract widgets from node definition
            # Look for 'widgets' in the node which may contain widget specs
            node_widgets = node.get('widgets', [])
            if node_widgets:
                for i, widget in enumerate(node_widgets):
                    if i < len(widgets_values):
                        widget_name = widget.get('name')
                        if widget_name and widget_name not in inputs:
                            inputs[widget_name] = widgets_values[i]
            else:
                # Unknown node type without widget definitions
                print(f"Warning: Unknown node type '{node_type}' with {len(widgets_values)} widget values - may have missing inputs")

        api_workflow[node_id] = {
            'class_type': node_type,
            'inputs': inputs
        }

        # Add _meta if node has a title
        if node.get('title'):
            api_workflow[node_id]['_meta'] = {'title': node['title']}

    return api_workflow


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

    # Find and modify nodes by class_type (legacy behavior for non-editable nodes)
    for node_id, node_data in modified.items():
        if not isinstance(node_data, dict) or 'class_type' not in node_data:
            continue

        # Skip nodes that were already modified by editable_values
        if int(node_id) in editable_by_node_id:
            continue

        class_type = node_data.get('class_type')
        inputs = node_data.get('inputs', {})
        meta = node_data.get('_meta', {})
        node_title = meta.get('title', '')

        # LoadImage nodes - set input image filename (only if we have a legacy image)
        if class_type == 'LoadImage' and image_basename:
            inputs['image'] = image_basename
            print(f"Set LoadImage node {node_id} to: {image_basename}")

        # TextEncodeQwenImageEditPlus nodes - only modify if title ends with "_editable"
        elif class_type == 'TextEncodeQwenImageEditPlus':
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

        # SaveImage nodes - set output prefix
        elif class_type == 'SaveImage':
            inputs['filename_prefix'] = output_prefix
            print(f"Set SaveImage node {node_id} prefix to: {output_prefix}")

        # HYMotionExportFBX nodes - clear output_dir so files go to main output, set prefix
        elif class_type == 'HYMotionExportFBX':
            inputs['output_dir'] = ''  # Empty = use ComfyUI's output directory directly
            inputs['filename_prefix'] = output_prefix
            print(f"Set HYMotionExportFBX node {node_id}: output_dir='', prefix={output_prefix}")

        # KSampler nodes - set seed
        elif class_type == 'KSampler':
            inputs['seed'] = seed
            print(f"Set KSampler node {node_id} seed to: {seed}")

        # SamplerCustomAdvanced / RandomNoise nodes - set seed
        elif class_type == 'RandomNoise':
            inputs['noise_seed'] = seed
            print(f"Set RandomNoise node {node_id} seed to: {seed}")

        # HYMotionGenerate nodes - set seed
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


def save_workflow(
    workflow: Dict[str, Any],
    output_dir: str,
    suffix: str = ""
) -> str:
    """
    Save modified workflow to a JSON file.

    Args:
        workflow: Modified workflow dictionary
        output_dir: Directory to save the workflow file
        suffix: Optional suffix for the filename

    Returns:
        Path to saved workflow file
    """
    os.makedirs(output_dir, exist_ok=True)

    workflow_filename = f"comfyui_workflow{suffix}.json"
    workflow_path = os.path.join(output_dir, workflow_filename)

    with open(workflow_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2)

    print(f"Saved modified workflow to: {workflow_path}")
    return workflow_path


def submit_comfyui_to_deadline_server_mode(
    workflow_path: str,
    seeds_file: str,
    output_dir: str,
    batch_name: str,
    render_name: str,
    generation_count: int,
    server_url: str = "http://127.0.0.1:8188",
    priority: Optional[int] = None,
    pool: Optional[str] = None,
    group: Optional[str] = None,
) -> Optional[str]:
    """
    Submit ComfyUI job to Deadline using server mode (persistent ComfyUI).

    Uses a lightweight client script that connects to an already-running
    ComfyUI server. Much faster as models are already loaded in memory.

    Requires comfyui_server.py to be running on the farm node.

    Args:
        workflow_path: Path to workflow JSON file
        seeds_file: Path to JSON file containing seeds for each frame
        output_dir: Output directory for generated outputs
        batch_name: BatchName for Deadline job grouping
        render_name: Name for the job display
        generation_count: Number of generations (frames)
        server_url: URL of the ComfyUI server (default: http://127.0.0.1:8188)
        priority: Job priority (default from config)
        pool: Deadline pool (default from config)
        group: Deadline group (default from config)

    Returns:
        Deadline job ID or None if failed
    """
    if priority is None:
        priority = DEADLINE_PRIORITY_COMFYUI
    if pool is None:
        pool = DEADLINE_POOL
    if group is None:
        group = DEADLINE_GROUP_COMPFYUI

    import shutil

    # Get ComfyUI paths and mode from settings
    comfyui_path = get_comfyui_path()
    comfyui_mode = get_comfyui_mode()
    comfyui_python = get_comfyui_python_path()

    # Determine Python executable based on mode
    if comfyui_mode == "embedded":
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
    elif comfyui_mode == "portable":
        # Portable mode (comfy-cli install): venv folder with ComfyUI subfolder
        python_exe = os.path.join(comfyui_path, "venv", "Scripts", "python.exe")
    else:
        # Standalone mode - use configured Python path
        python_exe = comfyui_python if comfyui_python else "python"

    # Get the client script path
    client_script_source = os.path.join(os.path.dirname(__file__), "comfyui_client.py")
    client_script = os.path.join(output_dir, "comfyui_client.py")

    # Copy client script to output directory
    if not os.path.exists(client_script) or os.path.getmtime(client_script_source) > os.path.getmtime(client_script):
        shutil.copy2(client_script_source, client_script)
        print(f"Copied client script to: {client_script}")

    # Build arguments for the client script
    # Use --frame <STARTFRAME> for multiframe job - Deadline substitutes frame number
    client_args = (
        f'"{client_script}" '
        f'--workflow "{workflow_path}" '
        f'--seeds-file "{seeds_file}" '
        f'--server-url "{server_url}" '
        f'--server-input-dir "{output_dir}" '
        f'--output-prefix "{render_name}" '
        f'--frame <STARTFRAME> '
        f'--timeout 600 '
        f'--wait-for-server 30'
    )

    # Submit as multiframe job - each frame is a different seed
    # Matches OIIO COMBINE naming pattern: "LUMA TOOLS - {render_name}"
    deadline_command = [
        DEADLINE_PATH,
        '-SubmitCommandLineJob',
        '-executable', python_exe,
        '-arguments', client_args,
        '-frames', f'1-{generation_count}',
        '-chunksize', '1',
        '-pool', pool,
        '-group', group,
        '-priority', str(priority),
        '-prop', f'Department={DEADLINE_DEPARTMENT}',
        '-prop', f'BatchName={batch_name}',
        '-prop', f'OutputDirectory0={output_dir}',
        '-name', f'LUMA TOOLS - {render_name}',
    ]

    print(f"Submitting Luma Tools job (server mode): {render_name}")
    print(f"Frames: 1-{generation_count} (each frame = different seed)")
    print(f"Server URL: {server_url}")
    print(f"Deadline command: {' '.join(deadline_command)}")

    try:
        result = subprocess.run(
            deadline_command,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        result_output = result.stdout.strip()
        print(f"Deadline submission result: {result_output}")

        if result.returncode != 0:
            print(f"Deadline submission error: {result.stderr}")
            return None

        # Extract job ID
        job_id = None
        for line in result_output.split('\n'):
            if 'JobID=' in line:
                job_id = line.split('=')[-1].strip()
                break

        if job_id:
            print(f"ComfyUI Deadline Job ID (server mode): {job_id}")

        return job_id

    except Exception as e:
        print(f"Error submitting to Deadline: {e}")
        return None


def submit_comfyui_to_deadline(
    workflow_path: str,
    seeds_file: str,
    output_dir: str,
    batch_name: str,
    render_name: str,
    generation_count: int,
    priority: Optional[int] = None,
    pool: Optional[str] = None,
    group: Optional[str] = None,
    use_server_mode: bool = False,
) -> Optional[str]:
    """
    Submit ComfyUI job to Deadline using CommandLine plugin.

    Uses a runner script that starts ComfyUI, submits the workflow via API,
    waits for completion, then exits. Submits as a multiframe job where each
    frame represents a different seed/generation.

    Args:
        workflow_path: Path to workflow JSON file
        seeds_file: Path to JSON file containing seeds for each frame
        output_dir: Output directory for generated outputs (also used as ComfyUI input directory)
        batch_name: BatchName for Deadline job grouping
        render_name: Name for the job display
        generation_count: Number of generations (frames)
        priority: Job priority (default from config)
        pool: Deadline pool (default from config)
        group: Deadline group (default from config)
        use_server_mode: If True, keep ComfyUI server running between jobs.
                         Models stay loaded in GPU memory, server restarts only if workflow changes.

    Returns:
        Deadline job ID or None if failed
    """
    if priority is None:
        priority = DEADLINE_PRIORITY_COMFYUI
    if pool is None:
        pool = DEADLINE_POOL
    if group is None:
        group = DEADLINE_GROUP_COMPFYUI

    import shutil

    # Get ComfyUI paths and mode from settings
    comfyui_path = get_comfyui_path()
    comfyui_mode = get_comfyui_mode()
    comfyui_python = get_comfyui_python_path()

    # Determine Python executable based on mode
    if comfyui_mode == "embedded":
        python_exe = os.path.join(comfyui_path, "python_embeded", "python.exe")
    elif comfyui_mode == "portable":
        # Portable mode (comfy-cli install): venv folder with ComfyUI subfolder
        python_exe = os.path.join(comfyui_path, "venv", "Scripts", "python.exe")
    else:
        # Standalone mode - use configured Python path
        python_exe = comfyui_python if comfyui_python else "python"

    # Get the runner script path (same directory as this file)
    # Copy it to output directory so it's accessible on farm workers
    script_dir = os.path.dirname(__file__)
    runner_script_source = os.path.join(script_dir, "comfyui_runner.py")
    runner_script = os.path.join(output_dir, "comfyui_runner.py")

    # Copy runner script to output directory if not already there
    if not os.path.exists(runner_script) or os.path.getmtime(runner_script_source) > os.path.getmtime(runner_script):
        shutil.copy2(runner_script_source, runner_script)
        print(f"Copied runner script to: {runner_script}")

    # Use output directory as input directory (image already copied there)
    input_dir = output_dir

    # Use fixed port for persistent mode, random for non-persistent
    if use_server_mode:
        port = 8188  # Fixed port for persistent server
    else:
        port = random.randint(8200, 8299)

    # Build arguments for the runner script
    # Use --frame <F> to process specific frame/seed from the seeds file
    # Deadline will substitute <F> with frame number (1-based)
    # Strip trailing slashes to avoid escaping issues with quotes on Windows
    comfyui_path_clean = comfyui_path.rstrip('/\\')
    runner_args = (
        f'"{runner_script}" '
        f'--comfyui-path "{comfyui_path_clean}" '
        f'--workflow "{workflow_path}" '
        f'--seeds-file "{seeds_file}" '
        f'--input-directory "{input_dir}" '
        f'--output-directory "{output_dir}" '
        f'--output-prefix "{render_name}" '
        f'--frame <STARTFRAME> '
        f'--port {port} '
        f'--timeout 600 '
        f'--mode {comfyui_mode}'
    )

    # Add Python path for standalone mode
    if comfyui_mode == "standalone" and comfyui_python:
        runner_args += f' --python-path "{comfyui_python}"'

    # Add persistent flag if server mode is enabled
    if use_server_mode:
        runner_args += ' --persistent'

    # Add performance flags from settings
    if get_comfyui_fast_mode():
        runner_args += ' --fast'
    if get_comfyui_fp16_accumulation():
        runner_args += ' --fp16-accumulation'

    # Build Deadline submission using job info and plugin info files
    # This allows us to set plugin-specific properties like ExitCodeTreatedAsFailure
    # Submit as multiframe job - each frame is a different seed
    # Matches OIIO COMBINE naming pattern: "LUMA TOOLS - {render_name}"

    # Create job info file
    job_info_path = os.path.join(output_dir, "comfyui_job_info.txt")
    job_info_content = f"""Plugin=CommandLine
Name=LUMA TOOLS - {render_name}
Department={DEADLINE_DEPARTMENT}
BatchName={batch_name}
Pool={pool}
Group={group}
Priority={priority}
Frames=1-{generation_count}
ChunkSize=1
OutputDirectory0={output_dir}
OnJobComplete=Delete
OverrideTaskFailureDetection=True
FailureDetectionTaskErrors=1
"""

    # Create plugin info file
    plugin_info_path = os.path.join(output_dir, "comfyui_plugin_info.txt")
    plugin_info_content = f"""Executable={python_exe}
Arguments={runner_args}
StartupDirectory={output_dir}
ExitCodeTreatedAsFailure=1-255
"""

    # Write the info files
    with open(job_info_path, 'w') as f:
        f.write(job_info_content)
    with open(plugin_info_path, 'w') as f:
        f.write(plugin_info_content)

    print(f"Submitting Luma Tools job: {render_name}")
    print(f"Frames: 1-{generation_count} (each frame = different seed)")
    print(f"Job info: {job_info_path}")
    print(f"Plugin info: {plugin_info_path}")

    deadline_command = [DEADLINE_PATH, job_info_path, plugin_info_path]

    try:
        result = subprocess.run(
            deadline_command,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        result_output = result.stdout.strip()
        print(f"Deadline submission result: {result_output}")

        if result.returncode != 0:
            print(f"Deadline submission error: {result.stderr}")
            return None

        # Extract job ID from output
        job_id = None
        for line in result_output.split('\n'):
            if 'JobID=' in line:
                job_id = line.split('=')[-1].strip()
                break

        if job_id:
            print(f"ComfyUI Deadline Job ID: {job_id}")
        else:
            print("Failed to extract job ID from Deadline response")

        return job_id

    except Exception as e:
        print(f"Error submitting to Deadline: {e}")
        return None


def _collect_batch_images(editable_values: Optional[Dict[int, Dict[str, Any]]]) -> Tuple[List[str], int]:
    """
    Collect all batch images from editable values.

    Returns:
        Tuple of (list of image paths, node_id of the image node)
    """
    if not editable_values:
        return [], -1

    for node_id, data in editable_values.items():
        node_info = data.get('node')
        value = data.get('value')
        if node_info and node_info.widget_type == 'image':
            if isinstance(value, list):
                # Batch images
                return [p for p in value if os.path.exists(p)], node_id
            elif value and os.path.exists(value):
                # Single image
                return [value], node_id

    return [], -1


def submit_comfyui_job(
    workflow_path: str,
    input_image: Optional[str],
    prompt: Optional[str],
    output_dir: str,
    generation_count: int,
    job_name: str,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None,
    base_seed: Optional[int] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    network_output_dir: Optional[str] = None,
    use_server_mode: bool = True,  # Deprecated, always True - kept for compatibility
) -> Tuple[List[str], str]:
    """
    Submit ComfyUI job to Deadline. Supports batch image processing.

    If multiple images are selected, submits a separate job for each image.
    Each job runs generation_count generations with different seeds.

    Server mode (persistent ComfyUI) is always enabled for faster execution.

    Args:
        workflow_path: Path to original workflow JSON file
        input_image: Path to input image (legacy, can be None if using editable_values)
        prompt: Edit prompt text (legacy, can be None if using editable_values)
        output_dir: User's output directory (where files will be moved after completion)
        generation_count: Number of generations (frames) per image
        job_name: Base name for the job
        editable_values: Dict of node_id -> {'node': EditableNode, 'value': Any}
                         Image values can be a list of paths for batch processing
        base_seed: Optional starting seed. If provided, seeds will be sequential
                   (base_seed, base_seed+1, ...). If None, random seeds are used.
        progress_callback: Optional callback for progress updates
        network_output_dir: Network path where ComfyUI writes outputs (optional).
                           If provided, ComfyUI outputs here and files are moved
                           to output_dir after completion. If None, outputs directly
                           to output_dir.
        use_server_mode: Deprecated - server mode is always enabled.

    Returns:
        Tuple of (job_ids, error_message)
        - job_ids: List of job IDs (one per image in batch)
        - error_message: Error message if failed, empty string if successful
    """
    import shutil

    if progress_callback:
        progress_callback(5, "Loading workflow...")

    # Load workflow
    workflow = load_workflow(workflow_path)

    # Collect batch images from editable values
    batch_images, image_node_id = _collect_batch_images(editable_values)

    # Also check legacy input_image
    if not batch_images and input_image and os.path.exists(input_image):
        batch_images = [input_image]

    # If no images found, this might be a workflow without image input
    if not batch_images:
        print("No input images found - submitting workflow as-is")
        batch_images = [None]  # Submit once without image

    total_images = len(batch_images)
    print(f"Batch submission: {total_images} image(s) × {generation_count} generations each")

    if progress_callback:
        progress_callback(10, f"Processing {total_images} image(s)...")

    # Determine working output directory (network if provided, else user's dir)
    # ComfyUI writes to working_output_dir, files later moved to output_dir
    working_base_dir = network_output_dir if network_output_dir else output_dir

    # Debug: Log which output path is being used
    print(f"[ComfyUI Submit] network_output_dir param: {network_output_dir!r}")
    print(f"[ComfyUI Submit] user output_dir: {output_dir}")
    print(f"[ComfyUI Submit] working_base_dir (for runner): {working_base_dir}")

    # Ensure output directories exist
    os.makedirs(output_dir, exist_ok=True)
    if network_output_dir:
        os.makedirs(network_output_dir, exist_ok=True)
        print(f"Using network output: {network_output_dir}")
        print(f"Files will be moved to: {output_dir}")
    else:
        print(f"No network path configured - using user output directly: {output_dir}")

    all_job_ids = []
    errors = []

    for img_idx, current_image in enumerate(batch_images):
        # Calculate progress for this image
        base_progress = 10 + int((img_idx / total_images) * 80)

        if current_image:
            image_basename = os.path.basename(current_image)
            image_name = os.path.splitext(image_basename)[0]
            current_job_name = f"{job_name}_{image_name}" if total_images > 1 else job_name
            # Create subfolder for this image's generations
            current_working_dir = os.path.join(working_base_dir, image_name) if total_images > 1 else working_base_dir
        else:
            image_basename = None
            current_job_name = job_name
            current_working_dir = working_base_dir

        # Ensure the working output subfolder exists
        os.makedirs(current_working_dir, exist_ok=True)

        if progress_callback:
            msg = f"Submitting {img_idx + 1}/{total_images}"
            if current_image:
                msg += f": {image_basename}"
            progress_callback(base_progress, msg)

        # Create a copy of editable_values with current single image
        current_editable_values = None
        if editable_values:
            current_editable_values = copy.deepcopy(editable_values)
            # Replace the batch list with single image for this iteration
            if image_node_id >= 0 and image_node_id in current_editable_values:
                current_editable_values[image_node_id]['value'] = current_image

        # Modify workflow with current image
        modified, found_editable = modify_workflow(
            workflow,
            current_image,
            prompt,
            current_job_name,  # Base output prefix, runner adds _genXX
            seed=12345,  # Placeholder seed, will be overridden per-frame
            editable_values=current_editable_values,
        )

        # Check if we found an editable prompt node (only warn if prompt provided but no editable node)
        if prompt and not found_editable and not current_editable_values:
            error_msg = (
                "No editable prompt node found in workflow. "
                "The workflow must have a TextEncodeQwenImageEditPlus node "
                "with a title ending in '_editable' to accept custom prompts."
            )
            print(f"ERROR: {error_msg}")
            return [], error_msg

        # Save modified workflow to the working directory
        workflow_file = save_workflow(modified, current_working_dir, suffix="")

        # Generate seeds for each generation
        # If base_seed is provided, use sequential seeds; otherwise random
        if base_seed is not None:
            seeds = [base_seed + i for i in range(generation_count)]
            print(f"Using sequential seeds starting from {base_seed}")
        else:
            seeds = [random.randint(0, 2**63 - 1) for _ in range(generation_count)]
            print("Using random seeds")
        seeds_data = {"seeds": seeds, "count": generation_count}

        # Save seeds file to the working directory
        seeds_file = os.path.join(current_working_dir, "comfyui_seeds.json")
        with open(seeds_file, 'w', encoding='utf-8') as f:
            json.dump(seeds_data, f, indent=2)
        print(f"Saved seeds file with {generation_count} seeds to: {seeds_file}")

        # Copy current input image to the working directory
        if current_image:
            image_dest = os.path.join(current_working_dir, image_basename)
            if not os.path.exists(image_dest) or os.path.getmtime(current_image) > os.path.getmtime(image_dest):
                shutil.copy2(current_image, image_dest)
                print(f"Copied input image to: {image_dest}")

        # Submit job for this image with working directory as output
        # Server mode is always enabled (persistent ComfyUI)
        job_id = submit_comfyui_to_deadline(
            workflow_path=workflow_file,
            seeds_file=seeds_file,
            output_dir=current_working_dir,
            batch_name=job_name,  # Keep same batch name for grouping
            render_name=current_job_name,
            generation_count=generation_count,
            use_server_mode=True,
        )

        if job_id:
            all_job_ids.append(job_id)
            print(f"Submitted job {img_idx + 1}/{total_images}: {job_id}")
        else:
            error_msg = f"Failed to submit job for image: {image_basename or 'workflow'}"
            errors.append(error_msg)
            print(f"ERROR: {error_msg}")

    if progress_callback:
        progress_callback(95, "Submission complete")

    if all_job_ids:
        total_gens = len(all_job_ids) * generation_count
        print(f"ComfyUI batch submitted: {len(all_job_ids)} job(s), {total_gens} total generations")
        return all_job_ids, ""
    else:
        error_msg = "; ".join(errors) if errors else "Failed to submit any jobs to Deadline"
        return [], error_msg


def validate_inputs(
    workflow_path: str,
    input_image: str,
    prompt: str,
    output_path: str
) -> Tuple[bool, str]:
    """
    Validate all ComfyUI submission inputs.

    Args:
        workflow_path: Path to workflow JSON file
        input_image: Path to input image
        prompt: Edit prompt text
        output_path: Output directory path

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not workflow_path:
        return False, "No workflow file selected"

    if not os.path.exists(workflow_path):
        return False, f"Workflow file not found: {workflow_path}"

    if not input_image:
        return False, "No input image selected"

    if not os.path.exists(input_image):
        return False, f"Input image not found: {input_image}"

    # Check file extension
    ext = os.path.splitext(input_image)[1].lower()
    if ext not in COMFYUI_SUPPORTED_EXTENSIONS:
        return False, f"Unsupported image format: {ext}"

    # Prompt is optional - if empty, workflow's default prompt will be used

    if not output_path:
        return False, "No output path selected"

    return True, ""


def validate_comfyui_path(path: str) -> Tuple[bool, str]:
    """
    Validate that a ComfyUI path is configured.

    Note: We don't check if the path exists locally because
    ComfyUI runs on Deadline farm workers, not the local machine.

    Args:
        path: Path to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path:
        return False, "ComfyUI path is not configured"

    return True, ""


def poll_deadline_job_status(job_id: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Query Deadline for a job's current status.

    Args:
        job_id: The Deadline job ID to query
        output_dir: Optional output directory to check for actual output files.
                   When job is deleted (OnJobComplete=Delete), we verify success
                   by checking if output files exist.

    Returns:
        Dict with keys:
        - status: str - "Active", "Completed", "Failed", "Suspended", "Pending", "Unknown"
        - progress: int - Percentage complete (0-100)
        - completed_tasks: int - Number of completed tasks
        - total_tasks: int - Total number of tasks
        - error_message: str - Error message if failed
    """
    try:
        # DEADLINE_PATH is the full path to the executable (from shutil.which)
        if not DEADLINE_PATH:
            return {"status": "Unknown", "progress": 0, "error_message": "Deadline not available"}

        result = subprocess.run(
            [DEADLINE_PATH, "GetJob", job_id],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        # Check if job was deleted (OnJobComplete=Delete)
        # This can happen with returncode != 0 OR returncode == 0 but empty/minimal output
        output = result.stdout.strip()
        job_deleted = False

        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "not found" in stderr or "does not exist" in stderr or not result.stderr.strip():
                job_deleted = True
        elif not output or "Status=" not in output:
            # Job returned but no valid status - likely deleted
            print(f"[poll_deadline_job_status] Job {job_id} returned empty/invalid output - likely deleted")
            job_deleted = True

        if job_deleted:
            # Job was deleted - check if it actually succeeded by looking for outputs
            print(f"[poll_deadline_job_status] Job {job_id} appears deleted, checking for output files...")
            if output_dir:
                output_files = get_job_output_files(output_dir)
                if output_files:
                    # Found output files - job completed successfully
                    print(f"[poll_deadline_job_status] Found {len(output_files)} output files - marking as Completed")
                    return {
                        "status": "Completed",
                        "progress": 100,
                        "completed_tasks": 1,
                        "total_tasks": 1,
                        "error_message": ""
                    }
                else:
                    # No output files found - job likely failed
                    print(f"[poll_deadline_job_status] No output files found - marking as Failed")
                    return {
                        "status": "Failed",
                        "progress": 100,
                        "completed_tasks": 0,
                        "total_tasks": 1,
                        "error_message": "Job deleted but no output files found - likely failed"
                    }
            else:
                # No output_dir provided - can't verify, assume completed
                # (backwards compatibility)
                print(f"[poll_deadline_job_status] No output_dir to verify - assuming Completed")
                return {
                    "status": "Completed",
                    "progress": 100,
                    "completed_tasks": 1,
                    "total_tasks": 1,
                    "error_message": ""
                }

        if result.returncode != 0:
            return {"status": "Unknown", "progress": 0, "error_message": result.stderr}

        # Parse the output (output was already assigned above as result.stdout.strip())
        status = "Unknown"
        completed_tasks = 0
        failed_tasks = 0
        total_tasks = 1
        error_reports = 0
        error_message = ""

        # Debug: print raw Deadline output
        print(f"[poll_deadline_job_status] Raw Deadline output for {job_id}:")
        for line in output.split('\n')[:20]:  # First 20 lines
            print(f"  {line}")

        for line in output.split('\n'):
            line = line.strip()
            if line.startswith("Status="):
                status = line.split('=', 1)[1]
                print(f"[poll_deadline_job_status] Parsed Status: '{status}'")
            elif line.startswith("CompletedTasks=") or line.startswith("CompletedChunks="):
                # Deadline uses CompletedChunks, not CompletedTasks
                completed_tasks = int(line.split('=', 1)[1])
                print(f"[poll_deadline_job_status] Parsed CompletedTasks/Chunks: {completed_tasks}")
            elif line.startswith("FailedTasks=") or line.startswith("FailedChunks="):
                failed_tasks = int(line.split('=', 1)[1])
                print(f"[poll_deadline_job_status] Parsed FailedTasks/Chunks: {failed_tasks}")
            elif line.startswith("TaskCount=") or line.startswith("ChunkCount="):
                total_tasks = int(line.split('=', 1)[1])
                print(f"[poll_deadline_job_status] Parsed TaskCount/ChunkCount: {total_tasks}")
            elif line.startswith("ErrorReports="):
                error_reports = int(line.split('=', 1)[1])
                print(f"[poll_deadline_job_status] Parsed ErrorReports: {error_reports}")

        # Build error message from failure info
        if failed_tasks > 0:
            error_message = f"{failed_tasks}/{total_tasks} task(s) failed"
            if error_reports > 0:
                error_message += f" ({error_reports} error report(s))"
        elif error_reports > 0:
            error_message = f"Job has {error_reports} error report(s)"

        progress = int((completed_tasks / max(total_tasks, 1)) * 100)

        # If job shows as Complete/Completed but has failed tasks, treat as Failed
        # Deadline may report "Complete" even when some tasks failed
        if status in ("Complete", "Completed") and failed_tasks > 0:
            print(f"[poll_deadline_job_status] Job marked Complete but has {failed_tasks} failed tasks - treating as Failed")
            status = "Failed"

        return {
            "status": status,
            "progress": progress,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "error_message": error_message
        }

    except Exception as e:
        return {"status": "Unknown", "progress": 0, "error_message": str(e)}


def get_job_output_files(output_dir: str) -> List[str]:
    """
    Get the output files from a job's output directory.

    Scans for all supported ComfyUI output types including images, 3D models,
    video, audio, and data files.

    Args:
        output_dir: The output directory to scan

    Returns:
        List of output file paths, sorted by modification time (newest first)
    """
    if not output_dir or not os.path.isdir(output_dir):
        return []

    # Use centralized output extensions from config
    supported_extensions = set(COMFYUI_OUTPUT_EXTENSIONS)
    files = []

    for filename in os.listdir(output_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext in supported_extensions:
            full_path = os.path.join(output_dir, filename)
            mtime = os.path.getmtime(full_path)
            files.append((full_path, mtime))

    # Sort by modification time, newest first
    files.sort(key=lambda x: x[1], reverse=True)
    return [f[0] for f in files]


def cleanup_job_temp_files(output_dir: str) -> int:
    """
    Clean up temporary job files from the output directory.

    Removes workflow JSON, seeds JSON, and runner script files that were
    copied to the output directory for the job.

    Args:
        output_dir: The output directory to clean

    Returns:
        Number of files deleted
    """
    import glob

    if not output_dir or not os.path.exists(output_dir):
        return 0

    temp_patterns = [
        "comfyui_workflow*.json",
        "comfyui_seeds.json",
        "comfyui_runner.py",
        "comfyui_client.py",
        "comfyui_job_info.txt",
        "comfyui_plugin_info.txt",
    ]

    deleted_count = 0

    for pattern in temp_patterns:
        for file_path in glob.glob(os.path.join(output_dir, pattern)):
            try:
                os.remove(file_path)
                print(f"Cleaned up temp file: {file_path}")
                deleted_count += 1
            except Exception as e:
                print(f"Failed to delete temp file {file_path}: {e}")

    return deleted_count


def scan_output_directory(output_dir: str) -> List[Dict[str, Any]]:
    """
    Scan directory for generated ComfyUI output files.

    Scans for all supported ComfyUI output types including images, 3D models,
    video, audio, and data files.

    Args:
        output_dir: Directory to scan

    Returns:
        List of file info dicts with keys: path, filename, created, size, extension
    """
    import glob
    from datetime import datetime

    if not output_dir or not os.path.exists(output_dir):
        return []

    # Use centralized output extensions from config
    output_files = []

    for ext in COMFYUI_OUTPUT_EXTENSIONS:
        # Convert extension to glob pattern (e.g., ".png" -> "*.png")
        pattern = os.path.join(output_dir, '**', f'*{ext}')
        for path in glob.glob(pattern, recursive=True):
            try:
                stat = os.stat(path)
                output_files.append({
                    'path': path,
                    'filename': os.path.basename(path),
                    'created': datetime.fromtimestamp(stat.st_ctime),
                    'size': stat.st_size,
                    'extension': ext,
                })
            except Exception as e:
                print(f"Error scanning {path}: {e}")

    # Sort by creation time, newest first
    output_files.sort(key=lambda x: x['created'], reverse=True)
    return output_files
