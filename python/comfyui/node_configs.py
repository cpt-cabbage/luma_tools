"""
ComfyUI Node Configuration Module.

Contains configuration dictionaries for:
- EDITABLE_NODE_CONFIGS: Defines which widgets are exposed as editable in the UI
- WIDGET_MAPPINGS: Maps widget_values indices to input names for API format conversion
"""

# Mapping of node types to their editable widget configurations
# Format: {node_type: [(widget_index, widget_name, widget_type), ...]}
# widget_type can be: 'text', 'image', 'int', 'float', 'combo', 'toggle', '3d_model', 'string'
EDITABLE_NODE_CONFIGS = {
    # Core ComfyUI nodes
    'LoadImage': [(0, 'image', 'image')],
    'SaveImage': [(0, 'filename_prefix', 'string')],
    'KSampler': [
        (0, 'seed', 'int'),
        (2, 'steps', 'int'),
        (3, 'cfg', 'float'),
    ],

    # Text/prompt nodes
    'TextEncodeQwenImageEditPlus': [(0, 'prompt', 'text')],
    'CLIPTextEncode': [(0, 'text', 'text')],
    'HYMotionEncodeText': [(0, 'text', 'text')],

    # SHARP 3D reconstruction nodes
    'SharpPredict': [(1, 'output_prefix', 'string')],

    # HY-Motion export
    'HYMotionExportFBX': [(1, 'filename_prefix', 'string')],

    # Hunyuan Video nodes
    'SaveVideo': [(0, 'filename_prefix', 'string')],

    # TRELLIS2 nodes
    'Trellis2ExportGLB': [(5, 'filename_prefix', 'string')],  # Old node
    'Trellis2ExportMesh': [(0, 'filename_prefix', 'string')],  # New mesh export (glb/obj/etc) - no output_dir
    'Trellis2LoadImageWithTransparency': [(0, 'image', 'image')],  # Load image with alpha

    # UltraShape nodes
    'UltraShapeSaveGLB': [(2, 'filename_prefix', 'string')],

    # Switch nodes - used as toggle/boolean when they have exactly 2 inputs
    'easy anythingIndexSwitch': [(0, 'index', 'toggle')],

    # 3D model loading
    'Load3D': [(0, 'model_file', '3d_model')],
}


# Settings node configurations - for nodes with '_settings' suffix
# These appear in the collapsible "Workflow Settings" section, grouped by node title
# Format: {node_type: [(widget_index, widget_name, widget_type), ...]}
SETTINGS_NODE_CONFIGS = {
    # Sampler settings
    'KSampler': [
        (2, 'steps', 'int'),
        (3, 'cfg', 'float'),
        (6, 'denoise', 'float'),
    ],
    'KSamplerAdvanced': [
        (3, 'steps', 'int'),
        (4, 'cfg', 'float'),
    ],

    # TRELLIS2 mesh settings
    'Trellis2MeshWithVoxelAdvancedGenerator': [
        (2, 'pipeline_type', 'combo'),
        (3, 'sparse_structure_steps', 'int'),
        (4, 'sparse_structure_guidance_strength', 'float'),
        (7, 'shape_steps', 'int'),
        (8, 'shape_guidance_strength', 'float'),
        (11, 'texture_steps', 'int'),
        (12, 'texture_guidance_strength', 'float'),
    ],
    'Trellis2PostProcessMesh': [
        (0, 'fill_holes', 'toggle'),
        (5, 'remove_small_connected_components', 'toggle'),
        (8, 'remove_floaters', 'toggle'),
    ],
    'Trellis2SimplifyMesh': [
        (0, 'target_face_num', 'int'),
        (1, 'method', 'combo'),
    ],
    'Trellis2PostProcessAndUnWrapAndRasterizer': [
        (4, 'texture_size', 'int'),
        (5, 'remesh', 'toggle'),
        (8, 'target_face_num', 'int'),
        (15, 'remove_floaters', 'toggle'),
    ],

    # UltraShape settings
    'UltraShapeRefine': [
        (0, 'steps', 'int'),
        (1, 'guidance_scale', 'float'),
        (2, 'octree_resolution', 'int'),
    ],

    # HYMotion settings
    'HYMotionGenerate': [
        (0, 'duration', 'float'),
        (2, 'cfg_scale', 'float'),
        (3, 'num_samples', 'int'),
    ],

    # Image scaling settings
    'ImageScale': [
        (0, 'upscale_method', 'combo'),
        (1, 'width', 'int'),
        (2, 'height', 'int'),
    ],
    'ImageScaleBy': [
        (0, 'upscale_method', 'combo'),
        (1, 'scale_by', 'float'),
    ],

    # Latent settings
    'EmptyLatentImage': [
        (0, 'width', 'int'),
        (1, 'height', 'int'),
        (2, 'batch_size', 'int'),
    ],
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

    # Qwen Image Edit nodes
    'TorchCompileModelQwenImage': [],  # No widgets, just compiles model
    'ReferenceLatent': [],  # No widgets, passes through
    'ConditioningZeroOut': [],  # No widgets

    # Load3D node - widgets_values has 7 items in this order:
    # [0]: model_file, [1-3]: button text (upload3dmodel, uploadExtraResources, clear),
    # [4]: extra, [5]: width, [6]: height
    # We need to map all positions even for button widgets to get correct offsets
    'Load3D': ['model_file', None, None, None, None, 'width', 'height'],

    # Nodes that need manual mapping (auto-discovery doesn't work)
    'ImageBatchMulti': ['inputcount', None],  # count widget + internal state
    'GeomPackPreviewMeshVTK': ['mode', None],  # mode widget + internal state
}


# Node types that should be skipped during API conversion
# These are UI-only nodes that don't affect workflow execution
SKIP_NODE_TYPES = [
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
]


# Node types that have seeds which should be set during workflow modification
SEED_NODE_TYPES = [
    'KSampler',
    'RandomNoise',
    'HYMotionGenerate',
    'Trellis2ImageToShape',
    'Trellis2ShapeToTexturedMesh',
    'Trellis2MeshWithVoxelAdvancedGenerator',
    'UltraShapeRefine',
]


# Node types that export files and need output prefix set
# Nodes with 'output_dir' in WIDGET_MAPPINGS will also have output_dir set automatically
EXPORT_NODE_TYPES = {
    'SaveImage': 'filename_prefix',
    'HYMotionExportFBX': 'filename_prefix',
    'Trellis2ExportGLB': 'filename_prefix',
    'Trellis2ExportMesh': 'filename_prefix',
    'UltraShapeSaveGLB': 'filename_prefix',
    # SHARP 3D reconstruction
    'SharpPredict': 'output_prefix',
    # Hunyuan Video
    'SaveVideo': 'filename_prefix',
}
