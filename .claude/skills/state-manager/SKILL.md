---
name: state-manager
description: Thread-safe global state management via app_state singleton. ThreadSafeProperty descriptor, role checking, state groups. Auto-loads when working with global application state.
user-invocable: false
---

# State Manager - Thread-Safe Global State

## Overview

The state manager (`python/core/state_manager.py`) provides a thread-safe singleton `app_state` for sharing state across the application. All property access is protected by `threading.RLock`.

## Import Pattern

```python
from core.state_manager import app_state

# Read state (thread-safe automatically)
current_job = app_state.jobname
is_standalone = app_state.standalone_mode

# Write state (thread-safe automatically)
app_state.jobname = "MyJob"
app_state.comfyui_workflow_path = "/path/to/workflow.json"
```

## ThreadSafeProperty Descriptor

The `ThreadSafeProperty` descriptor wraps get/set with automatic locking:

```python
class ApplicationState:
    _lock = threading.RLock()

    # One line per property - automatic thread safety
    jobname = ThreadSafeProperty('jobname', '')
    renders = ThreadSafeProperty('renders', [])

# Usage - no explicit locking needed
app_state.jobname = "NewJob"  # Automatically acquires lock
current = app_state.jobname   # Automatically acquires lock
```

### Adding New State Properties

Add to `ApplicationState` class:

```python
class ApplicationState:
    # ... existing properties ...

    # Add new property with name and default
    my_feature_enabled = ThreadSafeProperty('my_feature_enabled', False)
    my_feature_items = ThreadSafeProperty('my_feature_items', [])
```

CRITICAL: Default value for mutable types (list, dict) is shared! For mutable defaults, copy on first access:

```python
# In code that uses the list
items = list(app_state.my_feature_items or [])  # Copy to avoid mutation
items.append(new_item)
app_state.my_feature_items = items  # Replace entire list
```

## State Groups

### Command Line Arguments

```python
app_state.jobname           # str: AYON job name
app_state.shot              # str: Shot identifier
app_state.task              # str: Task type
app_state.shotpath          # str: Path to shot directory
app_state.user              # str: Current username
app_state.output_subdirectory  # str: Output subdirectory
```

### Pass Builder State

```python
app_state.renders           # list: Render paths
app_state.channels          # dict: Channel configuration
app_state.searchpath        # str: Current search path
app_state.startframe        # int: Start frame
app_state.endframe          # int: End frame
```

### MP4 Maker State

```python
app_state.mp4_renders       # list: Render paths for MP4
app_state.mp4_searchpath    # str: Search path
app_state.mp4_startframe    # int: Start frame
app_state.mp4_endframe      # int: End frame
app_state.mp4_output_path   # str: Output path
```

### ComfyUI State

```python
app_state.comfyui_workflow_path      # str: Current workflow path
app_state.comfyui_iterate_mode       # bool: Iterate mode enabled
app_state.comfyui_current_job_id     # str: Active job ID
app_state.comfyui_active_job_ids     # list: All active job IDs
app_state.comfyui_recent_outputs     # list: Recent output paths
app_state.comfyui_session_stats      # dict: Session statistics
```

### Gallery State

```python
app_state.gallery_new_since_view     # int: New items since last view
app_state.gallery_selected_paths     # list: Selected item paths
app_state.gallery_visible            # bool: Gallery tab visible
```

### Workflow Context

```python
app_state.workflow_last_used_inputs    # list: Recent input images
app_state.workflow_generation_history  # list: Generation history entries
```

## Role Checking

Role checking is cached and thread-safe:

```python
# Check if user is admin (full access including Settings tab)
if app_state.is_admin:
    show_settings_tab()

# Check if user is supervisor (ComfyUI and Gallery access)
if app_state.is_sup:
    show_supervisor_features()

# Check for any elevated access
if app_state.has_elevated_access:  # admin OR sup
    show_elevated_features()

# Force refresh after role list changes
app_state.refresh_admin_status()
```

## Context Checking

```python
# Check if running with AYON shot context
if app_state.has_shot_context():
    # Full functionality available
    use_ayon_publishing()
else:
    # Standalone mode - limited features
    show_standalone_warning()

# Check standalone mode directly
if app_state.standalone_mode:
    disable_ayon_features()
```

## Helper Methods

### Recent Outputs

```python
# Add to recent outputs (auto-deduplicates, keeps max 20)
app_state.add_recent_output("/path/to/new_output.png")

# Access recent outputs
for path in app_state.comfyui_recent_outputs:
    display_thumbnail(path)
```

### Session Statistics

```python
# Update stats after generation
app_state.update_session_stats(
    outputs_added=3,
    time_seconds=45.5,
    job_completed=True
)

# Get current stats
stats = app_state.get_session_stats()
print(f"Generated {stats['total_generated']} images in {stats['total_time_seconds']:.1f}s")
```

### Gallery New Items Counter

```python
# Increment when new items arrive (from ComfyUI completion)
app_state.increment_gallery_new_count(5)

# Reset when gallery becomes visible
def on_tab_activated(self):
    app_state.reset_gallery_new_count()
```

### Workflow Defaults

```python
# Record generation for smart defaults
app_state.add_to_generation_history({
    'workflow_name': 'upscale_4x',
    'generation_count': 10,
    'seed': 12345
})

# Get suggested defaults
defaults = app_state.get_workflow_defaults('upscale_4x')
suggested_count = defaults.get('generation_count', 5)
```

## Initialization

The app state is initialized from command line arguments:

```python
# In main entry point
app_state.initialize_from_args(sys.argv)

# If 6+ args provided: sets jobname, shot, task, shotpath, user, output_subdirectory
# Otherwise: enters standalone mode with USERNAME from environment
```

## Thread Safety Notes

1. **All property access is thread-safe** - no explicit locking needed
2. **RLock allows reentrant access** - same thread can acquire lock multiple times
3. **Role checks are cached** - first access checks file, subsequent reads use cache
4. **Use `refresh_admin_status()`** after modifying admin/sup lists

## Common Patterns

### Read-Modify-Write for Collections

```python
# CORRECT - copy, modify, replace
outputs = list(app_state.comfyui_recent_outputs or [])
outputs.append(new_path)
app_state.comfyui_recent_outputs = outputs

# WRONG - mutates shared default
app_state.comfyui_recent_outputs.append(new_path)  # Race condition!
```

### Conditional State Update

```python
# Check before update
if app_state.has_shot_context():
    app_state.renders = found_renders
else:
    logger.warning("No shot context - skipping render update")
```

### State Debugging

```python
# Log current state
logger.debug(f"ComfyUI state: mode={app_state.comfyui_iterate_mode}, "
             f"job={app_state.comfyui_current_job_id}")
```

## Files to Read Before State Changes

| Change | File |
|--------|------|
| Add new property | `python/core/state_manager.py` |
| Role checking | `python/core/settings_manager.py` (is_user_in_role) |
| State initialization | Entry point where `initialize_from_args()` called |
