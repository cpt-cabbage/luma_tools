---
name: event-bus
description: Cross-tab communication via Qt signals. All signal types, connection patterns, and common event flows. Auto-loads when working on event-based communication between tabs.
user-invocable: false
---

# Event Bus - Cross-Tab Communication

## Overview

The event bus (`python/core/event_bus.py`) provides decoupled communication between tabs via Qt signals. Tabs can emit events without knowing who listens, and listeners can react without knowing who emits.

## Import Pattern

```python
from core.event_bus import pipeline_events

# In initialize() - connect to events
pipeline_events.job_completed.connect(self._on_job_completed)

# Anywhere - emit events
pipeline_events.job_submitted.emit(job_id, expected_count, job_prefix)
```

## Available Signals

### ComfyUI → Gallery Events

| Signal | Signature | Description |
|--------|-----------|-------------|
| `job_submitted` | `(str, int, str)` | Job ID, expected output count, job prefix |
| `job_progress` | `(str, int, str)` | Job ID, progress %, status message |
| `job_output_ready` | `(str, str)` | Job ID, output file path |
| `job_completed` | `(str, list)` | Job ID, list of output paths |
| `job_failed` | `(str, str)` | Job ID, error message |
| `all_jobs_completed` | `(int, float)` | Total outputs, elapsed seconds |

### Gallery → ComfyUI Events

| Signal | Signature | Description |
|--------|-----------|-------------|
| `use_as_input` | `(list)` | List of paths to use as ComfyUI inputs |
| `copy_settings` | `(dict)` | Metadata dict to copy workflow settings |
| `selection_changed` | `(list, int)` | Selected paths, count |

### Gallery Events

| Signal | Signature | Description |
|--------|-----------|-------------|
| `gallery_refresh_requested` | `(bool)` | Force refresh flag (True clears cache) |

### Canvas Events

| Signal | Signature | Description |
|--------|-----------|-------------|
| `add_to_canvas` | `(str)` | Path of image to add to canvas |
| `canvas_image_added` | `(str)` | Path of image successfully added |
| `gallery_navigate_to` | `(str)` | Navigate to and select image in gallery |
| `favorites_changed` | `()` | Favorites (likes/groups) changed, listeners should re-query |

## Connection Patterns

### Connect Once in initialize()

```python
# CORRECT - connect once
def initialize(self):
    pipeline_events.job_completed.connect(self._on_job_completed)

# WRONG - multiple connections
def refresh(self):
    pipeline_events.job_completed.connect(self._on_job_completed)  # Called multiple times!
```

### Disconnect When Needed

```python
def cleanup(self):
    try:
        pipeline_events.job_completed.disconnect(self._on_job_completed)
    except RuntimeError:
        pass  # Already disconnected
```

### Check Connection Before Disconnecting

```python
# Safe disconnect pattern
try:
    pipeline_events.job_completed.disconnect(self._on_job_completed)
except (TypeError, RuntimeError):
    pass  # Not connected or already disconnected
```

## Job Tracking Methods

The event bus also provides job tracking utilities:

```python
# Register a new job
job_info = pipeline_events.register_job(
    job_id="12345",
    expected_outputs=5,
    job_prefix="job_20240115_abc",
    workflow_name="upscale_4x"
)

# Update progress
pipeline_events.update_job_progress(
    job_id="12345",
    progress=50,
    status="rendering",
    current_node=3,
    total_nodes=10,
    eta_seconds=120
)

# Record output
pipeline_events.record_job_output(job_id="12345", output_path="/path/to/output.png")

# Complete job
pipeline_events.complete_job(job_id="12345", success=True)
# Or: pipeline_events.complete_job(job_id="12345", success=False, error_message="...")

# Query jobs
active_jobs = pipeline_events.get_active_jobs()  # Dict[str, JobInfo]
job = pipeline_events.get_job_info("12345")      # Optional[JobInfo]
has_active = pipeline_events.has_active_jobs()    # bool
progress = pipeline_events.get_aggregate_progress()  # Dict with totals
```

## Common Event Flows

### Submit → Poll → Complete

```
ComfyUI Tab                    Event Bus                    Gallery Tab
     |                             |                             |
     |-- job_submitted.emit() ---->|                             |
     |                             |---- job_submitted --------->|
     |                             |     (register for updates)  |
     |                             |                             |
     |-- job_progress.emit() ----->|                             |
     |                             |---- job_progress ---------->|
     |                             |     (update status bar)     |
     |                             |                             |
     |-- job_completed.emit() ---->|                             |
     |                             |---- job_completed --------->|
     |                             |     (refresh gallery)       |
```

### Gallery Selection → ComfyUI Input

```
Gallery Tab                    Event Bus                    ComfyUI Tab
     |                             |                             |
     | (user selects, clicks       |                             |
     |  "Use as Input")            |                             |
     |-- use_as_input.emit() ----->|                             |
     |                             |---- use_as_input ---------->|
     |                             |     (load images to UI)     |
```

## Thread Safety

The event bus uses `threading.RLock` internally:
- Job tracking methods are thread-safe
- Signal emissions cross thread boundaries via Qt's signal mechanism
- Worker threads can safely emit signals
- Always update UI in the slot handler (main thread), not in workers

```python
# Safe: Worker emits signal, handler runs on main thread
def _worker_func(self):
    # ... do work ...
    return result

def _on_worker_result(self, result):
    # This runs on main thread
    pipeline_events.job_completed.emit(job_id, result.paths)
```

## Dataclasses

### JobInfo

```python
@dataclass
class JobInfo:
    job_id: str
    status: str = "pending"  # pending, queued, rendering, completed, failed
    progress: int = 0        # 0-100
    current_node: int = 0
    total_nodes: int = 0
    eta_seconds: Optional[int] = None
    expected_outputs: int = 0
    completed_outputs: int = 0
    output_paths: List[str] = field(default_factory=list)
    job_prefix: str = ""
    workflow_name: str = ""
    start_time: Optional[float] = None
```

### GalleryContext

```python
@dataclass
class GalleryContext:
    selected_paths: List[str] = field(default_factory=list)
    selected_count: int = 0
    active_filter: str = "all"
    current_user: str = ""
    visible: bool = False
```

## Adding New Signals

1. Add signal to `PipelineEventBus` class:
```python
class PipelineEventBus(QObject):
    # Add with clear signature documentation
    my_new_event = Signal(str, dict)  # (item_id, metadata)
```

2. Document in this skill file

3. Emit from source:
```python
pipeline_events.my_new_event.emit(item_id, metadata)
```

4. Connect in listeners' `initialize()`:
```python
pipeline_events.my_new_event.connect(self._on_my_event)
```

## Debugging Tips

- **Signal not received**: Check connection happens in `initialize()` before any emits
- **Multiple calls**: Signal connected multiple times (connect in `initialize()` only)
- **Wrong data**: Check signal signature matches emit/slot signatures
- **Thread crash**: Ensure UI updates happen in slot handler, not worker
