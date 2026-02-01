---
name: comfyui-complete
description: Complete ComfyUI workflow processing, node configuration, and metadata flows. Auto-loads when working on ComfyUI-related code including workflows, nodes, submission, polling, and output handling.
user-invocable: false
---

# ComfyUI System - Complete Reference

## Module Architecture

```
python/comfyui/
├── workflow.py      # Load/save workflows, format detection, API conversion
├── editable.py      # Extract _editable nodes for dynamic UI
├── modifier.py      # Modify workflow parameters before submission
├── node_configs.py  # EDITABLE_NODE_CONFIGS, WIDGET_MAPPINGS, EXPORT_NODE_TYPES
├── runner.py        # Executes workflow on Deadline farm
├── server.py        # Persistent ComfyUI server management
├── client.py        # HTTP client for ComfyUI API
├── metadata.py      # Job metadata storage, output file tracking
├── presets_manager.py # Workflow preset management
├── ayon_publisher.py  # AYON integration for outputs
└── utils.py         # Path resolution, server health checks
```

## Workflow Formats

### UI/Nodes Format (from ComfyUI export)
```json
{
    "nodes": [
        {
            "id": 1,
            "type": "LoadImage",
            "widgets_values": ["image.png", "upload"]
        }
    ],
    "links": [[1, 0, 2, 0, "IMAGE"]]
}
```

### API Format (for ComfyUI API)
```json
{
    "1": {
        "class_type": "LoadImage",
        "inputs": {
            "image": "image.png"
        }
    }
}
```

### Detection
```python
from comfyui.workflow import is_api_format

if is_api_format(workflow):
    # Already API format, use directly
else:
    # Need to convert via convert_to_api_format()
```

## Key Data Flows

### Workflow Load → Editable UI
```
User selects preset → presets_manager.load_preset()
→ workflow.load_workflow(path)
→ editable.extract_editable_nodes(workflow)
→ finds nodes with titles ending in "_editable"
→ looks up EDITABLE_NODE_CONFIGS for widget types
→ UI renders controls for each editable widget
```

### Submit → Deadline → Poll
```
User clicks Submit → comfyui_tab._on_submit()
→ modifier.modify_workflow() applies user settings
→ deadline.submitter.submit_comfyui_to_deadline()
→ creates Deadline job with runner.py as payload
→ PollingMixin._start_iterate_polling() or _start_batch_polling()
→ deadline.poller.poll_deadline_job_status()
→ status updates via signals → UI updated
```

### Output → Metadata → Gallery
```
runner.py executes on farm → files written to output_dir
→ metadata.store_job_metadata() saves to _gallery_metadata.json
→ gallery RefreshController detects new files
→ metadata.get_file_metadata() retrieves job info
→ item displayed with has_metadata=True (blue styling)
```

## Node Configuration

### EDITABLE_NODE_CONFIGS
Defines which widgets appear in the editable UI:
```python
EDITABLE_NODE_CONFIGS = {
    'LoadImage': [(0, 'image', 'image')],  # index, name, type
    'KSampler': [
        (0, 'seed', 'int'),
        (2, 'steps', 'int'),
        (3, 'cfg', 'float'),
    ],
    'CLIPTextEncode': [(0, 'text', 'text')],
    # ...
}
```

Widget types: `'text'`, `'image'`, `'int'`, `'float'`, `'combo'`, `'toggle'`, `'3d_model'`, `'string'`

### WIDGET_MAPPINGS
Maps widgets_values array indices to input names for API conversion:
```python
WIDGET_MAPPINGS = {
    'LoadImage': ['image', 'upload'],
    'KSampler': ['seed', 'control_after_generate', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise'],
    # ...
}
```

### EXPORT_NODE_TYPES
Nodes that output files (need filename_prefix handling):
```python
EXPORT_NODE_TYPES = {
    'SaveImage': 'filename_prefix',
    'Trellis2ExportGLB': 'filename_prefix',
    'SaveVideo': 'filename_prefix',
    # ...
}
```

## Adding a New Node Config

1. **Check if node has _editable suffix convention**
2. **Add to EDITABLE_NODE_CONFIGS** with (index, name, type) tuples
3. **Add to WIDGET_MAPPINGS** with ordered widget names
4. **If export node**: Add to EXPORT_NODE_TYPES with filename param
5. **Test with workflow containing the node**

### Verification Checklist
- [ ] Widget indices match ComfyUI node definition
- [ ] Widget names match exactly (case-sensitive)
- [ ] Export nodes have correct filename parameter
- [ ] Bypass conditions work if using toggle type

## Metadata System

### Per-File Metadata (_gallery_metadata.json)
```json
{
    "output_001.png": {
        "job_prefix": "job_20240115_abc123",
        "is_output": true,
        "is_input": false,
        "source_images": ["/path/to/input.png"],
        "workflow": "upscale_4x",
        "seed": 12345,
        "file_id": "uuid-123",
        "parent_id": "uuid-456",
        "node_timing": {"3": 1.5, "5": 2.3}
    }
}
```

### Input File Tracking
Input files are marked with `_input_` prefix in metadata:
```python
from comfyui.metadata import mark_as_input_file, is_known_input_file

mark_as_input_file(output_dir, input_path)  # Stores _input_filename entry
if is_known_input_file(output_dir, path):
    # Don't treat as output
```

### Lineage Tracking
```python
from comfyui.metadata import establish_lineage

establish_lineage(output_dir, parent_path, child_path)
# Sets child's parent_id to parent's file_id
```

## PollingMixin Integration

Located in `python/ui/tabs/comfyui_polling.py`:

```python
class MyTab(PollingMixin, BaseTab):
    def initialize(self):
        self._init_polling_state()  # MUST call first

    def _on_submit_success(self, job_id):
        # Single job (iterate mode)
        self._start_iterate_polling(job_id, total_frames)

        # Batch jobs
        self._start_batch_polling(job_ids_list)
```

**Critical**: Lambda closures in polling callbacks must capture by value:
```python
# WRONG
for job_id in job_ids:
    worker.signals.result.connect(lambda r: self._on_poll(r, job_id))

# CORRECT - capture job_id by value
for job_id in job_ids:
    worker.signals.result.connect(lambda r, jid=job_id: self._on_poll(r, jid))
```

## Server Management

### Persistent Server Mode
```python
from comfyui.server import start_persistent_server, stop_persistent_server
from comfyui.utils import check_server_health, wait_for_server

# Start server
start_persistent_server(port=8188, lowvram=True)

# Check health
if check_server_health(port=8188):
    # Server is ready

# Wait for startup
wait_for_server(port=8188, timeout=30)
```

### Server crashes are auto-detected and recovered:
- Health monitor checks every 30 seconds
- Auto-restart on crash (configurable max restarts)
- Crash counter resets after stable uptime

## Common Patterns

### Modifying Workflow Before Submit
```python
from comfyui.modifier import modify_workflow

modified = modify_workflow(
    workflow,
    image_paths=selected_images,
    seed=user_seed,
    output_prefix=job_prefix,
    output_dir=output_path
)
```

### Expanding Subgraphs
```python
from comfyui.workflow import expand_subgraphs

# Converts UUID component nodes to concrete nodes
expanded = expand_subgraphs(workflow)
```

### Getting Output Files
```python
from comfyui.metadata import get_job_output_files

# All files
files = get_job_output_files(output_dir)

# Filtered by job prefix and time
files = get_job_output_files(
    output_dir,
    job_prefix="job_001",
    min_mtime=start_time
)
```

## Files to Read Before ComfyUI Changes

| Change Type | Files to Read |
|-------------|---------------|
| Node config | node_configs.py |
| Workflow processing | workflow.py, modifier.py |
| Editable UI | editable.py, comfyui_ui_manager.py |
| Submission | deadline/submitter.py, runner.py |
| Polling | comfyui_polling.py |
| Metadata | metadata.py |
| Server | server.py, utils.py |

## Edge Cases

### Multi-Input Workflows
Nodes without inputs are bypassed, not failed. Check `SKIP_NODE_TYPES`.

### Workflow Format Mismatch
Always use `is_api_format()` before assuming format.

### Missing Widget Mappings
If node not in WIDGET_MAPPINGS, conversion may fail. Add mapping before testing new nodes.

### Metadata Not Found
Files without metadata display as grey (has_metadata=False). This is expected for old files or manual additions.
