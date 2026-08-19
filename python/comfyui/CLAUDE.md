# ComfyUI Module

ComfyUI AI workflow management — loading, modifying, submitting, and executing workflows.

## Workflow Pipeline

1. Select preset, scan for `_editable` suffix nodes (dynamic UI), select images, configure params
2. Submit to Deadline (each frame = different seed), `runner.py` executes on farm
3. Results appear in Gallery tab

## Module Decomposition

- `workflow.py` - Load workflows, format detection (`is_api_format()`), UI→API conversion
- `editable.py` - Extract `_editable` suffix nodes for dynamic UI generation
- `modifier.py` - Parameter modification before submission
- `node_configs.py` - `EDITABLE_NODE_CONFIGS` defining per-node-type editable parameters
- `metadata.py` - Store/load job metadata (job_prefix, is_output, source_images) in `_gallery_metadata.json` per directory
- `presets_manager.py` - Workflow preset management (load, save, import, validate)
- `runner.py` - Farm execution of workflows (called by Deadline)
- `server.py` - ComfyUI server management (start, stop, health checks)
- `ayon_publisher.py` - AYON publishing integration for ComfyUI outputs
- `ratings.py` - Rating/scoring system for generated outputs
- `service.py` - Re-exports all public APIs
- `utils.py` - `resolve_comfyui_paths(comfyui_path, mode)`, `check_server_health()`, `wait_for_server()`

## Key Concepts

### Editable Nodes
Nodes with `_editable` suffix in their title are extracted and presented as dynamic UI. Configuration in `EDITABLE_NODE_CONFIGS` (in `node_configs.py`) maps node types to their editable parameters and widget types.

**Widget Types:**
- `text` - Multiline text input with spell checking (for prompts)
- `string` - Single-line text input
- `int` / `float` - Numeric inputs
- `combo` - Dropdown selection
- `toggle` - Checkbox for boolean values
- `image` - Batch image selector with preview
- `video` - Batch video selector
- `audio` - Batch audio selector
- `3d_model` - File browser for 3D models (GLB, OBJ, FBX, USD)
- `directory` - Folder browser for directory selection

**Cardinality markers** — a marker directly after `_editable`, before any `@if_`:

| Title | Meaning |
|---|---|
| `Name_editable` | one value (default) |
| `Name_editable?` | optional — the node is removed from the workflow when left empty |
| `Name_editable*` | fan-out — one selector holding N files expands at submit time |
| `Name_editable*@if_Toggle` | both, combined |

Fan-out (`_expand_fanout_slots` in `modifier.py`) clones the template loader
once per extra file and wires each clone into the consumer's next free numbered
input. It splits the trailing integer off the consumer's input name and
duplicates the sibling inputs sharing that index **within the same slot
family** — prefixes related by containment (`media_` / `media_type_`) or
inputs fed by the template itself — which is how `media_type_N` follows
`media_N` without the code naming either, while an unrelated `lora_N` neither
travels, blocks a free slot, nor is deleted when the slot empties. Siblings
fed by the template keep their own output slot; siblings fed by other nodes
are duplicated as-is. The slot ceiling comes from
`node_info.get_optional_input_names()`; if the consumer class isn't cached,
extra files are refused with a warning rather than written to inputs ComfyUI
would silently drop.

`_expand_fanout_slots` never mutates `editable_values` — the submitter reads
the same dict afterwards for gallery metadata and content hashes, so
`_apply_editable_values` skips fan-out entries by cardinality instead. Empty
`?`/`*` slots are detached via `_detach_slot_node`, which also drops
un-indexed consumer inputs that link to the removed node.

Fan-out slots are excluded from `_collect_batch_images` — their files belong to
one generation, not one Deadline job each.

**Reference tags** (MiniMax H3): `<Picture N>`, `<Video N>`, `<Audio N>` are
literals the model consumes directly — N is the ordinal *within that media
type*. `<d>...</d>` marks dialogue. The "@ Reference" button beside a prompt's
Presets button inserts them; there is no submit-time rewriting.

### Workflow Formats — API format is fully supported

Both `extract_editable_nodes` and `extract_settings_nodes` read either format.
In API format the marker rides in `_meta.title` and values are keyed by input
name in `inputs`, so there is no widget-index resolution, no subgraph expansion
and no mute/bypass handling. The shared ladder lives in
`_build_editable_widgets` / `_build_settings_widgets`; `_NodeView.get_value` is
the only real difference between the two formats.

API format is **required** for node packs whose frontend injects inputs at
`graphToPrompt` time — e.g. `ComfyUI-MiniMaxH3-Easy`, whose media ports exist
only in an API export. Those presets must be exported with **Export (API)**;
a UI-format save loses the wiring silently.

**Adding New Widget Types:**
1. Add widget type to `EditableNode.widget_type` docstring in `editable.py`
2. Add UI rendering case in `ui_manager.py` → `_create_editable_node_widget()`
3. Add workflow modification handling in `modifier.py` → `modify_workflow_api_format()`
4. Configure node in `node_configs.py` → `EDITABLE_NODE_CONFIGS` with format: `'NodeType': [('widget_name', 'widget_type')]`

Example configuration for directory widget:
```python
EDITABLE_NODE_CONFIGS = {
    'VHS_LoadImagesPath': [('directory', 'directory')],  # (widget_name, widget_type_override)
}
```

### Subgraph Expansion
`expand_subgraphs()` in `workflow.py` expands UUID component nodes into concrete nodes before API conversion. Key architecture:

**Boundary inputs** use negative `from_node` IDs (e.g., `-10`) in internal links. `boundary_input_map` maps `slot_index → [(internal_node, internal_slot, link)]` — note one boundary input can fan out to multiple internal nodes (e.g., `ckpt_name` → 3 different loader nodes).

**Widget value propagation** to internal nodes uses `_input_overrides` dict on expanded nodes. Three code paths handle this based on format:
1. `proxyWidgets` + list `widgets_values` — each entry is `[node_id_str, widget_name]`, boundary inputs use `"-1"` as node_id
2. No `proxyWidgets` + list `widgets_values` — maps by subgraph input index
3. `proxyWidgets` + dict `widgets_values` — looks up by widget name

All three paths use `_apply_boundary_overrides()` helper to propagate values through `boundary_input_map` when the subgraph input definition's `link` field is `null`.

**Muted/bypassed node handling** in `convert_to_api_format()`: Nodes with `mode=4` (muted) or `mode=2` (bypassed) are skipped, and links through them are resolved upstream. A muted node acts as pass-through: output slot N comes from input slot N. The resolution handles chains of multiple muted nodes.

### Export Nodes
Add to `EXPORT_NODE_TYPES` dict (maps node type → filename param) and `WIDGET_MAPPINGS`.

### Workflow Formats
Two formats exist: UI/nodes format and API format. Use `is_api_format()` to detect. Workflows are converted to API format before execution. Editable/settings extraction handles both — see "Workflow Formats — API format is fully supported" above.

### Submit-time validation
`collect_missing_node_types()` (`workflow.py`) diffs a workflow's class types against `node_info.get_known_class_types()` and blocks Submit rather than failing on the farm minutes later. Two contracts matter: an **empty** known-set means the cache is unavailable, not that nothing is installed, so it reports nothing; and `SKIP_NODE_TYPES` is excluded because canvas-only nodes (`MarkdownNote`, `PrimitiveNode`, `Reroute`) have no backend class and never appear in `/object_info`.

### Metadata
`metadata.py` stores/loads job metadata in `_gallery_metadata.json` per output directory. Fields include `job_prefix`, `is_output`, `source_images`, `output_type`.

## Deadline Integration

The `deadline/` package handles farm job submission and monitoring:

- `deadline.submitter` - Job submission: `submit_comfyui_to_deadline()`, `submit_comfyui_to_deadline_server_mode()`, `submit_comfyui_job()`
- `deadline.poller` - Status polling: `poll_deadline_job_status()`, `get_queue_info()`, `find_user_running_jobs()`, `cancel_deadline_jobs()`
- `deadline.parser` - Output parsing: `parse_deadline_output()`, `parse_job_info()`, `extract_job_id()`, `is_job_not_found()`
- `deadline.utils` - Utilities: `run_deadline_command()`, `submit_deadline_job()`

```python
from deadline import submit_comfyui_job, poll_deadline_job_status
from deadline.utils import submit_deadline_job
from deadline.parser import parse_deadline_output, extract_job_id
```
