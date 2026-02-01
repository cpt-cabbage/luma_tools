---
name: debug-symptoms
description: Maps common symptoms to their root causes for rapid debugging. Auto-loads when investigating bugs, errors, or unexpected behavior in luma_tools.
user-invocable: false
---

# Debug Symptoms → Causes Reference

## Threading Issues

### Symptom: Nothing happens (silent failure)
**Cause**: Worker garbage collected before completion
**Check**: Is worker stored on `self._worker`?
```python
# WRONG - gets GC'd
worker = Worker(func)
QThreadPool.globalInstance().start(worker)

# CORRECT
self._worker = Worker(func)
QThreadPool.globalInstance().start(self._worker)
```
**Files**: Any file using Worker directly (check for bare `worker =`)

### Symptom: All loop iterations use same value
**Cause**: Lambda closure capturing by reference
**Check**: Lambdas in loops missing default argument capture
```python
# WRONG - all use final i value
for i in range(5):
    button.clicked.connect(lambda: handle(i))

# CORRECT - capture by value
for i in range(5):
    button.clicked.connect(lambda x=i: handle(x))
```
**Files**: comfyui_polling.py, any loop with lambda/connect

### Symptom: Intermittent crashes, data corruption
**Cause**: Missing thread lock on shared cache
**Check**: Cache dictionary without `threading.Lock()`
```python
# WRONG
self._cache[key] = value  # Race condition

# CORRECT
with self._cache_lock:
    self._cache[key] = value
```
**Files**: ui_components.py, thumbnail_base.py, metadata.py, event_bus.py

### Symptom: UI freeze during operation
**Cause**: Heavy work on main thread instead of worker
**Check**: Long operation not wrapped in `start_worker()`
**Fix**: Move to worker, update UI via signals

### Symptom: "Cannot access widget from thread" crash
**Cause**: Qt widget access from worker thread
**Check**: Widget method calls inside worker function
**Fix**: Return data from worker, update widget in result handler

## Settings Issues

### Symptom: KeyError when accessing setting
**Cause**: Setting not in SETTINGS_REGISTRY
**Check**: `core/settings_manager.py` SETTINGS_REGISTRY dict
**Fix**: Add `SettingDef` to registry:
```python
SETTINGS_REGISTRY = {
    "my_setting": SettingDef("my_setting", default=False, scope="user"),
}
```

### Symptom: Setting doesn't persist after restart
**Cause 1**: Wrong scope (user vs global)
**Cause 2**: Cache not cleared after external modification
**Check**: Scope in SettingDef, call `clear_settings_cache()` if needed

### Symptom: Setting returns old value
**Cause**: Settings cache stale
**Fix**: `clear_settings_cache()` after external file changes

### Symptom: Safe accessor returns default despite setting existing
**Cause**: Using `safe_get_setting()` with wrong default type
**Check**: Default type matches expected value type

## Event Bus Issues

### Symptom: Signal emitted but handler not called
**Cause 1**: Not connected - missing `.connect()` call
**Cause 2**: Connected after emit (timing issue)
**Cause 3**: Connected to wrong signal
**Check**:
```python
# In initialize()
pipeline_events.job_completed.connect(self._on_job_done)  # Must be before any emit
```

### Symptom: Handler called multiple times
**Cause**: Signal connected multiple times (e.g., in method called repeatedly)
**Fix**: Connect in `__init__` or `initialize()`, not in repeated methods

### Symptom: Handler receives wrong data
**Cause**: Connected to wrong signal or signal signature mismatch
**Check**: Signal parameters match handler signature

## Gallery Issues

### Symptom: Gallery flashes/clears when updating
**Cause**: Not using incremental display
**Fix**: `display_items(items, view_mode, incremental=True)`

### Symptom: Thumbnail shows wrong styling
**Cause**: ThumbnailStyler priority order
**Check**: Group color > liked > stack > metadata order in thumbnail_styles.py

### Symptom: Selection not updating toolbar
**Cause**: SelectionManager signal not connected
**Check**: `_on_selection_changed` connected to selection updates

### Symptom: Viewer doesn't open on double-click
**Cause**: ViewerManager not initialized or click handler not connected
**Check**: `_viewer_manager` exists, double-click signal connected

### Symptom: File changes not detected
**Cause 1**: QFileSystemWatcher not setup for path
**Cause 2**: Network path (needs polling instead)
**Check**: RefreshController._watcher setup, _poll_timer for network

### Symptom: Gallery items disappear unexpectedly
**Cause 1**: Not using incremental mode
**Cause 2**: Widget cache cleared improperly
**Check**: `display_items()` using `incremental=True`, `_widget_cache` management

### Symptom: Group/like colors not showing on thumbnails
**Cause**: ThumbnailStyler not updated after favorite change
**Check**: `like_changed` or `item_groups_changed` signal triggers `_update_thumbnail_style()`
**Files**: thumbnail_styles.py, favorites_manager.py

### Symptom: NEW badge not appearing on new items
**Cause 1**: Item not marked as new in metadata
**Cause 2**: ThumbnailNotificationDot not created/shown
**Check**: `is_new` flag, `_notification_dot.show_dot()` called

### Symptom: Stacking groups items incorrectly
**Cause**: Job prefix extraction wrong
**Check**: `job_prefix` in metadata, `_get_stack_key()` logic
**Files**: ui_manager.py, metadata.py

### Symptom: Metadata shows for wrong file
**Cause**: Metadata cache key mismatch (path normalization)
**Fix**: Always use `os.path.normpath()` for cache keys
**Files**: metadata.py `_gallery_metadata_cache`

## ComfyUI Issues

### Symptom: Node not appearing in editable UI
**Cause 1**: Node title missing `_editable` suffix
**Cause 2**: Node type not in EDITABLE_NODE_CONFIGS
**Check**: Workflow JSON node titles, node_configs.py

### Symptom: Workflow conversion fails
**Cause**: Node type missing from WIDGET_MAPPINGS
**Fix**: Add mapping to node_configs.py WIDGET_MAPPINGS

### Symptom: Output files not appearing in gallery
**Cause 1**: Export node not in EXPORT_NODE_TYPES
**Cause 2**: Metadata not stored
**Check**: node_configs.py EXPORT_NODE_TYPES, metadata.py store calls

### Symptom: Job stuck in "Queued" status
**Cause**: Deadline connection issue or job configuration error
**Check**: Deadline logs, `deadline.poller.poll_deadline_job_status()` output

### Symptom: Polling shows wrong progress
**Cause**: Lambda closure bug in polling callbacks
**Check**: Capture job_id by value in lambdas

## Import Issues

### Symptom: ImportError on app start
**Cause**: Circular import or wrong path
**Check**: Import order, PYTHONPATH includes python/ and resources/ui/

### Symptom: Worker import fails
**Cause**: UI component imported at module level (should be lazy)
**Fix**: Move import inside function:
```python
def my_method(self):
    from ui_components import Worker  # Lazy import
    self._worker = Worker(...)
```

## Log File Locations

| Type | Path |
|------|------|
| User logs | `W:/LumaRND/tmp/ComfyUI_OUT/_logs/users/` |
| Server logs | `W:/LumaRND/tmp/ComfyUI_OUT/_logs/server/` |
| Runner logs | `W:/LumaRND/tmp/ComfyUI_OUT/_logs/runner/` |
| Fallback | `~/.luma_tools/logs/` |

### Reading Latest Log
```powershell
# Get latest log file path
powershell -Command "(Get-ChildItem 'W:\LumaRND\tmp\ComfyUI_OUT\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName"

# Search for errors
Grep pattern="ERROR|Exception|Traceback" path="W:\LumaRND\tmp\ComfyUI_OUT\_logs\users\"
```

## Debugging Workflow

1. **Reproduce** - Run app with `--tab <name> --auto-close 30`
2. **Check logs** - Read latest log file for errors
3. **Match symptom** - Find symptom in this guide
4. **Verify cause** - Check the specific code pattern
5. **Fix** - Apply the documented solution
6. **Test** - Run again to verify fix

## Quick Checks

| Issue | First Check |
|-------|-------------|
| Silent failure | Worker stored on self? |
| KeyError | Setting in registry? |
| Signal not received | Connected in initialize()? |
| Gallery flash | Using incremental=True? |
| Wrong loop value | Lambda captures by value? |
| Race condition | Lock on shared cache? |
| Import error | Lazy import for UI components? |
