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
- `client.py` - HTTP client for ComfyUI API
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
- `3d_model` - File browser for 3D models (GLB, OBJ, FBX, USD)
- `directory` - Folder browser for directory selection

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
`expand_subgraphs()` expands UUID component nodes into concrete nodes before submission.

### Export Nodes
Add to `EXPORT_NODE_TYPES` dict (maps node type → filename param) and `WIDGET_MAPPINGS`.

### Workflow Formats
Two formats exist: UI/nodes format and API format. Use `is_api_format()` to detect. Workflows are converted to API format before execution.

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
