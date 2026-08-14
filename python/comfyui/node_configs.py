"""
ComfyUI Node Configuration Module.

Contains configuration dictionaries for:
- EDITABLE_NODE_CONFIGS: Defines which widgets are exposed as editable in the UI
- SETTINGS_NODE_CONFIGS: Defines which widgets appear in the settings section
- WIDGET_MAPPINGS: Legacy fallback for API format conversion (prefer node_info auto-discovery)

Widget types and indices are auto-resolved from the node_info cache (/object_info).
Configs only need to specify widget names. Some entries use special types that
can't be auto-discovered (e.g., 'image', '3d_model', 'toggle' for switch nodes).
"""

# Mapping of node types to their editable widget names
# Simple format: {node_type: ['widget_name', ...]}
# Override format: {node_type: [(widget_name, override_type), ...]}
#   Use override_type when the auto-discovered type isn't what the UI needs
#   (e.g., 'image' for LoadImage, '3d_model' for Load3D, 'toggle' for switches)
EDITABLE_NODE_CONFIGS = {
    # Core ComfyUI nodes
    'LoadImage': [('image', 'image')],
    'SaveImage': ['filename_prefix'],
    'KSampler': ['seed', 'steps', 'cfg'],

    # Text/prompt nodes
    'TextEncodeQwenImageEditPlus': ['prompt'],
    'CLIPTextEncode': ['text'],
    'HYMotionEncodeText': ['text'],

    # SHARP 3D reconstruction nodes
    'SharpPredict': ['output_prefix'],

    # HY-Motion export
    'HYMotionExportFBX': ['filename_prefix'],

    # Hunyuan Video nodes
    'SaveVideo': ['filename_prefix'],

    # TRELLIS2 nodes
    'Trellis2ExportGLB': ['filename_prefix'],
    'Trellis2ExportMesh': ['filename_prefix'],
    'Trellis2LoadImageWithTransparency': [('image', 'image')],

    # UltraShape nodes
    'UltraShapeSaveGLB': ['filename_prefix'],

    # Switch nodes - 'toggle' type can't be auto-discovered (it's just INT)
    'easy anythingIndexSwitch': [('index', 'toggle')],

    # 3D model loading - '3d_model' type can't be auto-discovered
    'Load3D': [('model_file', '3d_model')],

    # Video loading nodes - 'video' type can't be auto-discovered
    'VHS_LoadVideo': [('video', 'video')],
    'VHS_LoadVideoPath': [('video', 'video')],
    # /object_info reports the native LoadVideo's input as 'file', not 'video'.
    # Prefer this node over VHS for reference video: it returns a VIDEO object
    # exposing get_components(), which is what H3 media-type inference keys on,
    # whereas VHS returns plain IMAGE frames.
    'LoadVideo': [('file', 'video')],

    # Audio loading - 'audio' type can't be auto-discovered (reported as COMBO)
    'LoadAudio': [('audio', 'audio')],
    'VHS_LoadAudioUpload': [('audio', 'audio')],

    # Image path loading nodes - 'directory' type can't be auto-discovered
    'VHS_LoadImagesPath': [('directory', 'directory')],
}


# Settings node configurations - for nodes with '_settings' suffix
# These appear in the collapsible "Workflow Settings" section, grouped by node title
# Format: {node_type: ['widget_name', ...]}
SETTINGS_NODE_CONFIGS = {
    # Core ComfyUI utility nodes
    'PrimitiveNode': ['value', None],  # Value + control mode (None = skip control mode)

    # Sampler settings
    'KSampler': ['steps', 'cfg', 'denoise'],
    'KSamplerAdvanced': ['steps', 'cfg'],

    # TRELLIS2 mesh settings
    'Trellis2MeshWithVoxelAdvancedGenerator': [
        'pipeline_type', 'sparse_structure_steps', 'sparse_structure_guidance_strength',
        'shape_steps', 'shape_guidance_strength',
        'texture_steps', 'texture_guidance_strength',
    ],
    'Trellis2PostProcessMesh': [
        'fill_holes', 'remove_small_connected_components', 'remove_floaters',
    ],
    'Trellis2SimplifyMesh': ['target_face_num', 'method'],
    'Trellis2PostProcessAndUnWrapAndRasterizer': [
        'texture_size', 'remesh', 'target_face_num', 'remove_floaters',
    ],

    # UltraShape settings
    'UltraShapeRefine': ['steps', 'guidance_scale', 'octree_resolution'],

    # HYMotion settings
    'HYMotionGenerate': ['duration', 'cfg_scale', 'num_samples'],

    # Image scaling settings
    'ImageScale': ['upscale_method', 'width', 'height'],
    'ImageScaleBy': ['upscale_method', 'scale_by'],

    # Latent settings
    'EmptyLatentImage': ['width', 'height', 'batch_size'],
}


# Widget mappings for convert_to_api_format
# Maps node type to list of widget names in order of widgets_values array
# Use None for button/UI-only widgets that don't map to inputs
WIDGET_MAPPINGS = {
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
    'FluxKontextImageScale': [],
    'ResizeImagesByLongerEdge': ['longer_edge'],
    'ImageScale': ['upscale_method', 'width', 'height', 'crop'],
    'ImageScaleBy': ['upscale_method', 'scale_by'],
    'ImageInvert': [],
    'ImageBatch': [],
    'RepeatLatentBatch': ['amount'],
    'ResizeAndPadImage': ['target_width', 'target_height', 'padding_color', 'interpolation'],

    # Background removal nodes
    'RMBG': [
        'model', 'sensitivity', 'process_res', 'mask_blur', 'mask_offset',
        'invert_output', 'refine_foreground', 'background', 'background_color'
    ],

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

    # TRELLIS2 nodes (original)
    'LoadTrellis2Models': ['resolution', 'keep_model_loaded', 'attn_backend'],
    'Trellis2GetConditioning': ['include_1024', 'background_color'],
    'Trellis2ImageToShape': ['seed', 'control_after_generate', 'ss_guidance_strength', 'ss_sampling_steps', 'shape_guidance_strength', 'shape_sampling_steps'],
    'Trellis2ShapeToTexturedMesh': ['seed', 'control_after_generate', 'tex_guidance_strength', 'tex_sampling_steps'],
    'Trellis2ExportGLB': ['decimation_target', 'texture_size', 'remesh', 'filename_prefix'],
    'Trellis2RemoveBackground': ['low_vram'],

    # TRELLIS2 v2 nodes (from ComfyUI-Trellis2 visualbruno)
    # NOTE: These are fallback mappings only - auto-discovery from node inputs is preferred.
    # Widget counts may vary between node versions, so auto-discovery is more reliable.
    'Trellis2LoadModel': ['modelname', 'backend', 'device', 'low_vram', 'keep_models_loaded'],
    'Trellis2LoadImageWithTransparency': ['image', 'upload'],
    'Trellis2MeshWithVoxelAdvancedGenerator': [
        'seed', 'control_after_generate', 'pipeline_type',
        'sparse_structure_steps', 'sparse_structure_guidance_strength',
        'sparse_structure_guidance_rescale', 'sparse_structure_rescale_t',
        'shape_steps', 'shape_guidance_strength', 'shape_guidance_rescale', 'shape_rescale_t',
        'texture_steps', 'texture_guidance_strength', 'texture_guidance_rescale', 'texture_rescale_t',
        'max_num_tokens', 'max_views', 'sparse_structure_resolution', 'generate_texture_slat',
        'sparse_structure_guidance_interval_start', 'sparse_structure_guidance_interval_end',
        'shape_guidance_interval_start', 'shape_guidance_interval_end',
        'texture_guidance_interval_start', 'texture_guidance_interval_end',
        'use_tiled_decoder'
    ],
    # NOTE: Trellis2PostProcessMesh has different widget counts between versions
    # v1 (LQ): 9 widgets, v2 (HQ): 13 widgets - auto-discovery handles this
    'Trellis2PostProcessMesh': [
        'fill_holes', 'fill_holes_max_perimeter', 'remove_duplicate_faces',
        'repair_non_manifold_edges', 'remove_non_manifold_faces',
        'remove_small_connected_components', 'remove_small_connected_components_size',
        'unify_faces_orientation', 'remove_floaters',
        # v2 additions:
        'remove_infinite_vertices', 'merge_vertices', 'merge_distance', 'remove_nan_vertices'
    ],
    'Trellis2SimplifyMesh': ['target_face_num', 'method'],
    # NOTE: Trellis2PostProcessAndUnWrapAndRasterizer has different widget counts between versions
    # v1 (LQ): 16 widgets, v2 (HQ): 18 widgets - auto-discovery handles this
    'Trellis2PostProcessAndUnWrapAndRasterizer': [
        'mesh_cluster_threshold_cone_half_angle_rad', 'mesh_cluster_refine_iterations',
        'mesh_cluster_global_iterations', 'mesh_cluster_smooth_strength',
        'texture_size', 'remesh', 'remesh_band', 'remesh_project',
        'target_face_num', 'simplify_method', 'fill_holes', 'fill_holes_max_perimeter',
        'texture_alpha_mode', 'dual_contouring_resolution', 'double_side_material', 'remove_floaters',
        # v2 additions:
        'bake_on_vertices', 'use_custom_normals'
    ],
    'Trellis2ExportMesh': ['filename_prefix', 'file_format', 'save_file'],

    # Mask nodes
    'InvertMask': [],
    'MaskPreview': [],

    # UltraShape nodes
    'UltraShapeLoadModel': ['checkpoint', 'config', 'dtype', 'low_vram'],
    'UltraShapeLoadCoarseMesh': ['mesh_path', 'normalize_scale', 'num_sharp_points', 'num_uniform_points', 'num_latents'],
    'UltraShapeRefine': ['steps', 'guidance_scale', 'octree_resolution', 'num_chunks', 'mc_level', 'box_v', 'seed', 'control_after_generate', 'remove_bg'],
    'UltraShapeSaveGLB': ['output_dir', 'filename_prefix', 'file_format'],

    # Switch nodes
    'easy anythingIndexSwitch': ['index'],
    'Any Switch (rgthree)': [],  # Auto-selects first non-null input

    # SHARP 3D reconstruction nodes (Image → PLY gaussian splat)
    'LoadSharpModel': ['device', 'checkpoint_path'],
    'SharpPredict': ['focal_length_mm', 'output_prefix'],
    'LoadDepthPro': ['precision'],
    'DepthPro': [],  # No widgets, just processes
    'FocalPXtoMM': ['focal_px', 'sensor_mm', 'image_width', 'image_height'],
    'GetImageSize': [],  # Display-only output
    'GeomPackPreviewGaussian': [],  # Preview node

    # Hunyuan Video 1.5 nodes (Image → Video)
    'CLIPVisionLoader': ['clip_name'],
    'CLIPVisionEncode': ['crop'],
    'HunyuanVideo15ImageToVideo': ['width', 'height', 'length', 'batch_size'],
    'HunyuanVideo15SuperResolution': ['noise_augmentation'],
    'HunyuanVideo15LatentUpscaleWithModel': ['upscale_method', 'width', 'height', 'crop'],
    'LatentUpscaleModelLoader': ['model_name'],
    'CFGGuider': ['cfg'],
    'ModelSamplingSD3': ['shift'],
    'CreateVideo': ['fps'],
    'SaveVideo': ['filename_prefix', 'format', 'codec'],
    'EasyCache': ['reuse_threshold', 'start_percent', 'end_percent', 'verbose'],
    'DisableNoise': [],
    'VAEDecodeTiled': ['tile_size', 'overlap', 'temporal_size', 'temporal_overlap'],

    # ACE Step 1.5 Audio nodes
    # NOTE: 'quality' is also patched in via node_info.MISSING_WIDGETS, because
    # /object_info doesn't report it. These manual entries are the fallback for
    # when the node_info cache is unavailable.
    'SaveAudioMP3': ['filename_prefix', 'quality'],
    'SaveAudioOpus': ['filename_prefix', 'quality'],
    'VAEDecodeAudio': [],
    'TextEncodeAceStepAudio1.5': ['tags', 'lyrics', 'seed', None, 'bpm', 'duration', 'timesignature', 'language', 'keyscale'],
    'EmptyAceStep1.5LatentAudio': ['seconds', 'batch_size'],

    # Qwen Image Edit nodes
    'TorchCompileModelQwenImage': [],  # No widgets, just compiles model
    'ReferenceLatent': [],  # No widgets, passes through
    'ConditioningZeroOut': [],  # No widgets

    # Load3D node - widgets_values has 7 items in this order:
    # [0]: model_file, [1-3]: button text (upload3dmodel, uploadExtraResources, clear),
    # [4]: extra, [5]: width, [6]: height
    # We need to map all positions even for button widgets to get correct offsets
    'Load3D': ['model_file', None, None, None, None, 'width', 'height'],

    # Core ComfyUI utility nodes
    'PrimitiveNode': ['value', None],  # Value + control mode (None = skip control mode)

    # Nodes that need manual mapping (auto-discovery doesn't work)
    'ImageBatchMulti': ['inputcount', None],  # count widget + internal state
    'GeomPackPreviewMeshVTK': ['mode', None],  # mode widget + internal state
}


# Node types that should be skipped during API conversion
# These are UI-only nodes that don't affect workflow execution.
# frozenset (not list) — this is membership-tested once per node during
# conversion, so a linear scan is pure waste on large workflows.
SKIP_NODE_TYPES = frozenset({
    'Reroute', 'Note', 'PrimitiveNode',
    # Note/comment nodes from various extensions
    'MarkdownNote', 'CR Text', 'ShowText', 'ShowTextForGPT',
    'Note+', 'NoteNode', 'CommentNode',
    # Preview/display nodes that don't affect output
    # NOTE: PreviewImage and Preview3D are NOT skipped - they trigger image saving
    'PreviewBridge',
    # rgthree UI-only control nodes
    'Fast Groups Muter (rgthree)', 'Image Comparer (rgthree)',
    # Utility/cleanup nodes
    'easy cleanGpuUsed', 'easy imageSizeByLongerSide',
})


# NOTE: the former SEED_NODE_TYPES list lived here and duplicated
# comfyui.utils._SEED_NODES. Both are gone — seed application is now driven by
# the node's actual widget names (see comfyui.utils.iter_seed_inputs), so any
# sampler exposing a `seed`/`noise_seed` widget is handled without a hardcoded
# allow-list. Adding a new sampler node type no longer requires a code change.


# Suffix convention for marking the primary output node in multi-output workflows.
# When any export node has this suffix in its title, ONLY that node gets the
# output prefix set — other export nodes are skipped and their files are not
# moved to the output directory. Backwards-compatible: if no node has the suffix,
# all export nodes are handled as before.
OUTPUT_SUFFIX = '_output'

# Node types that export files and need output prefix set
# Nodes with 'output_dir' in WIDGET_MAPPINGS will also have output_dir set automatically
EXPORT_NODE_TYPES = {
    # --- Core ComfyUI image saves ---
    'SaveImage': 'filename_prefix',
    'SaveAnimatedWEBP': 'filename_prefix',
    'SaveAnimatedPNG': 'filename_prefix',
    # --- Core ComfyUI video saves ---
    'SaveVideo': 'filename_prefix',
    'SaveWEBM': 'filename_prefix',
    # --- Core ComfyUI audio saves ---
    'SaveAudio': 'filename_prefix',        # FLAC
    'SaveAudioMP3': 'filename_prefix',
    'SaveAudioOpus': 'filename_prefix',
    # --- Core ComfyUI 3D saves ---
    'SaveGLB': 'filename_prefix',
    # --- Custom node packs ---
    'HYMotionExportFBX': 'filename_prefix',
    'Trellis2ExportGLB': 'filename_prefix',
    'Trellis2ExportMesh': 'filename_prefix',
    'UltraShapeSaveGLB': 'filename_prefix',
    # SHARP 3D reconstruction
    'SharpPredict': 'output_prefix',
}
