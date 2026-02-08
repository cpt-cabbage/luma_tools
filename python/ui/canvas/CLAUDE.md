# Canvas Module

Collaborative infinite canvas for spatial organization of AI generations.

## Architecture

### Multi-Canvas System
`CanvasMetadataManager` (in `canvas_metadata.py`) tracks canvases per project in `_canvases.json`. Supports creating, deleting, and switching between named canvases.

### Dual Scope
- `CanvasScope.JOB` - Shared across all shots in a project (job-wide canvases)
- `CanvasScope.SHOT` - Shot-specific canvases, only visible within that shot context

### Network Sync
`CanvasSyncManager` syncs canvas state via JSON files on a shared network drive. `CursorPresenceManager` shows collaborator cursors in real-time with user identification.

### Canvas Items
All items in `canvas_items.py`:
- `ImageNode` - Image display with metadata, thumbnails, and interaction
- `VideoNode` - Video display with thumbnail, inline playback (QMediaPlayer), duration badge
- `ConnectionLine` - Visual connections between items
- `StickyNote` - Text annotations on the canvas
- `GroupRegion` - Visual grouping regions for organizing items

### Video Support
`VideoNode` shows a static thumbnail (FFmpeg first-frame extraction) with play icon overlay and duration badge. Double-click activates inline playback via `QGraphicsProxyWidget` embedding `VideoSinkWidget` + `VideoControlBar`. Single-active-player policy: `deactivate_all_videos()` ensures only one video plays at a time. Videos are tracked in `_video_nodes` dict, serialized in `'videos'` key of state, and exported to a `videos` table in `.luma` files. Supports drag-drop, gallery context menu, ComfyUI auto-add, and event bus entry points.

### Drawing System
`canvas_drawing.py` provides pen tablet support with pressure sensitivity. Tools include pen, eraser, and selection modes for drawings.

### Undo/Redo
`canvas_undo.py` implements command pattern via `UndoStack`. Supports composite commands for grouping multiple operations into a single undo step.

### Export
`canvas_export.py` handles `.luma` file format — `export_to_luma()` and `import_from_luma()`.

### Canvas Selector
`canvas_selector_dialog.py` provides UI for browsing, creating, and managing canvases with scope filtering.

## Module Files

- `collaborative_canvas.py` - Main widget (pan, zoom, item management, tool handling)
- `sync_manager.py` - Network sync + cursor presence
- `canvas_items.py` - All canvas item types
- `canvas_drawing.py` - Pen/eraser tools, brush rendering
- `canvas_undo.py` - Undo stack with command pattern
- `canvas_export.py` - .luma file import/export
- `canvas_metadata.py` - Multi-canvas registry, CanvasScope enum
- `canvas_selector_dialog.py` - Canvas browser/creator dialog
