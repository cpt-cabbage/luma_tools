---
name: trace-flow
description: Trace feature flows through the luma_tools codebase. Use for understanding how features work or debugging issues. Provides file:line references.
argument-hint: <feature or question>
---

# Feature Flow Tracing

Trace how features flow through the codebase. Use when:
- Investigating bugs ("why doesn't X work?")
- Understanding features ("how does gallery refresh work?")
- Planning modifications ("what do I need to change for X?")

## Tracing Approach

### Direction depends on the question:

**"What triggers X?"** → Trace backwards (effect → cause)
- Start from the observed behavior
- Find what calls it, what signals trigger it
- Trace back to user action or external event

**"What does X do?"** → Trace forwards (cause → effect)
- Start from the action/function
- Follow calls, signals, data flow
- End at final effects (UI update, file write, etc.)

## Output Format

Adapt output to complexity:

### Simple flows (3-5 steps)
```
User clicks Refresh → RefreshController.on_refresh() → _do_refresh() starts worker → scan_directory() → display_items(incremental=True)
```

### Complex flows (provide file:line refs)
```
1. [gallery_tab.py] User double-clicks thumbnail
2. [selection_manager.py] _on_thumbnail_double_clicked() called
3. [viewer_manager.py:37] open_viewer(start_image=path)
4. [viewer_manager.py:82] _show_embedded() hides gallery
5. [ui_components.py] EmbeddedImageViewer created
6. [viewer_manager.py:79] image_viewed signal connected
```

## Common Flow Patterns

### UI Action → Result
```
Widget signal → Tab handler → Manager method → Worker (if async)
→ Service/utility → Result signal → UI update
```

### Event Bus Cross-Tab
```
Tab A action → pipeline_events.signal.emit(data)
→ Qt signal dispatch → Tab B._on_signal() → Tab B updates
```

### File System → UI Update
```
File change → QFileSystemWatcher/poll timer → RefreshController
→ scan_directory() → GalleryManager.display_items()
→ incremental widget creation → UI shows new items
```

### Settings Read/Write
```
User changes setting → set_setting(key, value)
→ SETTINGS_REGISTRY lookup → scope determines file
→ JSON write → cache update
→ get_setting() returns new value
```

## Key Entry Points

### Gallery
- **User action**: `gallery_tab.py` handlers
- **Selection**: `selection_manager.py`
- **Viewing**: `viewer_manager.py`
- **Operations**: `operations_manager.py`
- **Refresh**: `refresh_controller.py`
- **Display**: `gallery_manager.py`

### ComfyUI
- **Submit**: `comfyui_tab.py:_on_submit()`
- **Polling**: `comfyui_polling.py` mixin
- **Workflow**: `comfyui/workflow.py`
- **Nodes**: `comfyui/node_configs.py`
- **Metadata**: `comfyui/metadata.py`

### Cross-Tab
- **Events**: `core/event_bus.py`
- **State**: `core/state_manager.py`
- **Settings**: `core/settings_manager.py`

## Tracing Steps

1. **Identify starting point**
   - For UI actions: Find the widget/signal in tab code
   - For errors: Find the error message in logs
   - For behavior: Find the visible effect

2. **Follow the chain**
   - Use Grep to find function calls
   - Use Read to understand function bodies
   - Track signal connections
   - Note worker thread boundaries

3. **Document key points**
   - file:function or file:line format
   - Note async boundaries (worker start/end)
   - Note signal emissions and connections

4. **Identify dependencies**
   - What managers are involved?
   - What settings are read?
   - What events are emitted/consumed?

## Example Traces

### "How does gallery refresh work?"
```
1. [refresh_controller.py:50] on_refresh() called (user or watcher)
2. [refresh_controller.py:77] _refresh_timer debounces (500ms)
3. [refresh_controller.py:88] _do_refresh() starts worker
4. [Worker thread] scan_directory() scans output_dir
5. [refresh_controller.py] _on_scan_complete() receives items
6. [gallery_manager.py] display_items(incremental=True)
7. [gallery_manager.py] Only new items get widgets created
```

### "Why isn't my setting persisting?"
```
1. Check SETTINGS_REGISTRY - is key defined?
2. Check scope - user (local) vs global (network)?
3. Check safe_set_setting() return value
4. Check file permissions on settings JSON
5. Check if cache cleared when needed
```

### "How does ComfyUI job submission work?"
```
1. [comfyui_tab.py] _on_submit() clicked
2. [comfyui/modifier.py] modify_workflow() applies settings
3. [deadline/submitter.py] submit_comfyui_to_deadline()
4. [deadline/utils.py] Deadline job created
5. [comfyui_polling.py] _start_iterate_polling() begins
6. [deadline/poller.py] poll_deadline_job_status() periodically
7. [comfyui_polling.py] _on_poll_result() updates UI
8. [event_bus.py] job_completed emitted → gallery refreshes
```

## When Tracing for User

Provide:
- Clear step-by-step flow
- file:line references for key points
- Note any async/worker boundaries
- Identify which files they'd need to modify

When Tracing for My Understanding

Use this to:
- Find all places that need changes
- Understand existing patterns before modifying
- Identify potential side effects of changes
