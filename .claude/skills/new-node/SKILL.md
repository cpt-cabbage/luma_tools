---
name: new-node
description: Guided creation of ComfyUI node configurations. Asks the right questions then adds proper entries to node_configs.py.
disable-model-invocation: true
argument-hint: <node-type>
---

# New ComfyUI Node Configuration

When adding support for a new ComfyUI node, I MUST ask these questions BEFORE modifying code:

## Required Questions

1. **Node type**: What is the exact ComfyUI node class_type? (e.g., "SaveImage", "KSampler")
   - Must match exactly as it appears in workflow JSON

2. **Widget mappings**: What widgets does this node have?
   - List ALL widgets in order as they appear in widgets_values array
   - Include UI-only widgets (buttons) as None/placeholder
   - Example: ['seed', 'control_after_generate', 'steps', 'cfg']

3. **Editable widgets**: Which widgets should appear in the _editable UI?
   - For each: (index, name, type)
   - Types: 'text', 'image', 'int', 'float', 'combo', 'toggle', '3d_model', 'string'
   - Only widgets users should adjust, not internal controls

4. **Is this an export node?**: Does this node save files to disk?
   - If yes: What parameter contains the filename prefix?
   - Examples: SaveImage uses 'filename_prefix', Trellis2ExportGLB uses 'filename_prefix'

5. **Bypass conditions**: Can this node be conditionally bypassed?
   - If yes: What toggle controls it?
   - Toggle nodes (easy anythingIndexSwitch) use 'toggle' type

6. **Sample workflow**: Do you have a workflow JSON with this node?
   - Helps verify widget order and parameter names

## How to Find Widget Information

### From ComfyUI UI
1. Add node to workflow in ComfyUI
2. Export workflow as JSON
3. Find node in "nodes" array
4. Check "widgets_values" array for order
5. Check "inputs" array for names

### Example Node in Workflow JSON
```json
{
    "id": 5,
    "type": "KSampler",
    "widgets_values": [
        123456,      // index 0: seed
        "randomize", // index 1: control_after_generate
        20,          // index 2: steps
        7.5,         // index 3: cfg
        "euler",     // index 4: sampler_name
        "normal",    // index 5: scheduler
        1.0          // index 6: denoise
    ]
}
```

## Entries to Add

### 1. WIDGET_MAPPINGS (always required)
```python
# In python/comfyui/node_configs.py
WIDGET_MAPPINGS = {
    # ... existing entries
    'NewNodeType': ['widget1', 'widget2', 'widget3'],  # In widgets_values order
}
```

Use `None` for button/UI-only widgets that don't map to API inputs.

### 2. EDITABLE_NODE_CONFIGS (if node should be editable)
```python
EDITABLE_NODE_CONFIGS = {
    # ... existing entries
    'NewNodeType': [
        (0, 'widget_name', 'widget_type'),  # (index, name, type)
        (2, 'another_widget', 'int'),
    ],
}
```

Widget types:
- `'text'` - Multi-line text input (prompts)
- `'string'` - Single-line text input (filenames)
- `'image'` - Image file selector
- `'int'` - Integer spinner
- `'float'` - Float spinner
- `'combo'` - Dropdown selector
- `'toggle'` - Boolean switch (index 0=off, 1=on)
- `'3d_model'` - 3D model file selector

### 3. EXPORT_NODE_TYPES (if node saves files)
```python
EXPORT_NODE_TYPES = {
    # ... existing entries
    'NewNodeType': 'filename_prefix',  # Parameter that sets output filename
}
```

### 4. SKIP_NODE_TYPES (if node should be skipped when no inputs)
```python
SKIP_NODE_TYPES = [
    # ... existing entries
    'NewNodeType',  # Add if node should be bypassed when inputs missing
]
```

## Verification Checklist

After adding entries, verify:

- [ ] Widget indices match actual widgets_values order in workflow JSON
- [ ] Widget names match exactly (case-sensitive)
- [ ] Widget types are appropriate for the data
- [ ] WIDGET_MAPPINGS covers ALL widgets (use None for UI-only)
- [ ] EDITABLE_NODE_CONFIGS only includes user-facing widgets
- [ ] EXPORT_NODE_TYPES entry if node saves files
- [ ] Test with actual workflow containing the node

## Common Patterns

### Sampler Nodes
```python
'KSampler': ['seed', 'control_after_generate', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise'],
```
Note: `control_after_generate` is always after seed widgets.

### Image Loader Nodes
```python
'LoadImage': ['image', 'upload'],  # upload is UI button, but include it
```

### Text/Prompt Nodes
```python
'CLIPTextEncode': ['text'],
```
Use `'text'` type for multi-line, `'string'` for single-line.

### Export/Save Nodes
```python
WIDGET_MAPPINGS['SaveImage'] = ['filename_prefix']
EXPORT_NODE_TYPES['SaveImage'] = 'filename_prefix'
```

### Toggle Nodes (2-input switches)
```python
'easy anythingIndexSwitch': [(0, 'index', 'toggle')],
```
Toggle type renders as on/off switch in UI.

## File to Modify

All entries go in: `python/comfyui/node_configs.py`

After modification, the node will:
1. Convert correctly between UI and API formats
2. Appear in editable UI when title ends with `_editable`
3. Have filename_prefix properly set for output files
