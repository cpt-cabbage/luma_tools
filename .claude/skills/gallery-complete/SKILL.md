---
name: gallery-complete
description: Complete gallery manager architecture, interactions, and patterns. Auto-loads when working on gallery-related code including selection, viewing, operations, refresh, favorites, and UI management.
user-invocable: false
---

# Gallery System - Complete Reference

## Architecture Overview

The gallery decomposes into 10+ specialized managers in `python/ui/tabs/gallery/`:

| Manager | Responsibility |
|---------|----------------|
| `gallery_manager.py` | Sorting, grouping, widget creation, display coordination |
| `selection_manager.py` | Single/multi-select, Ctrl+click, Shift+click, box selection |
| `viewer_manager.py` | Embedded/fullscreen viewer lifecycle, navigation |
| `operations_manager.py` | Delete, publish, copy settings, batch operations |
| `refresh_controller.py` | File watching, polling, scan operations, prewarm cache |
| `ui_manager.py` | Sort controls, filter controls, view mode switching |
| `favorites_manager.py` | Likes, groups, persistence to `_gallery_favorites.json` |
| `groups_panel.py` | Sidebar UI for groups, drag-to-group |
| `filters_dialog.py` | File type filtering dialog |
| `stacks_dialog.py` | Stacking mode controls |
| `job_status_bar.py` | Real-time job progress display |
| `quick_actions_bar.py` | Action buttons bar |
| `base_manager.py` | Common helpers (start_worker, show_status, properties) |

## Manager Interaction Patterns

### Selection → Viewer
```
User clicks thumbnail → SelectionManager.on_thumbnail_clicked()
→ updates tab._selected_items set
→ if double-click: ViewerManager.open_viewer(start_image=path)
→ ViewerManager._show_embedded() hides gallery, shows viewer
→ viewer.image_viewed.connect(tab._on_item_viewed) for tracking
```

### Refresh → Display
```
File system change detected → RefreshController._watcher callback
→ RefreshController.on_refresh() with debouncing (500ms)
→ _do_refresh() starts worker → scan_directory()
→ on_scan_complete → GalleryManager.display_items(incremental=True)
→ only NEW items added (no flash/clear)
```

### Operations → Metadata
```
User selects items → SelectionManager updates tab._selected_items
→ User triggers delete → OperationsManager.delete_selected()
→ os.remove() each file
→ _on_item_deleted() cleans up:
   - widget_cache removal
   - cached_items list update
   - FavoritesManager.remove_item() for likes/groups
   - metadata cleanup (if stored)
```

### Groups → Styling
```
User assigns item to group → FavoritesManager.add_to_group(path, group_id)
→ persists to _gallery_favorites.json
→ ThumbnailStyler.apply_styles() checks:
   1. Group color (from favorites_manager.get_item_groups())
   2. Liked status (border highlight)
   3. Stack membership
   4. Metadata presence (blue vs grey)
→ Thumbnail border/background updated
```

## Incremental Display Pattern (CRITICAL)

To avoid UI flashing when new items arrive:

```python
# In GalleryManager or GalleryTab
self._manager.display_items(items, view_mode, incremental=True)
```

With `incremental=True`:
1. Existing widgets are NOT cleared
2. Only new items (not in widget_cache) get widgets created
3. Existing widgets retain their position
4. Stacked view uses `_update_stacked_items_incrementally()`

## Key Data Structures

### Item Dict
```python
item = {
    'path': '/full/path/to/image.png',
    'name': 'image.png',
    'mtime': 1234567890.0,  # For sorting
    'workflow': 'workflow_name',  # From metadata
    'job_prefix': 'job_001',  # For grouping
    'is_input': False,  # True for source images
    'has_metadata': True,  # Blue (True) vs grey (False) styling
    'file_id': 'uuid-123',  # For lineage tracking
    'parent_id': 'uuid-456',  # Previous iteration
}
```

### Widget Cache
```python
tab._widget_cache = {
    '/path/to/image.png': ThumbnailWidget,
    '/path/to/model.glb': ThumbnailWidget,
}
```

### Selected Items
```python
tab._selected_items = set()  # Set of file paths
```

## Keyboard Shortcuts

| Key | Action | Handler |
|-----|--------|---------|
| `L` | Toggle like | FavoritesManager.toggle_like() |
| `G` | Quick add to group | FavoritesManager.quick_add_to_group() |
| `Ctrl+G` | Group management dialog | FavoritesManager.show_group_dialog() |
| `1-9` | Quick assign to group by number | FavoritesManager.assign_to_group(n) |
| `Ctrl+A` | Select all | SelectionManager.select_all() |
| `Escape` | Clear selection / close viewer | SelectionManager.clear_selection() |
| `Delete` | Delete selected | OperationsManager.delete_selected() |

## Persistence Files

### _gallery_favorites.json (per output directory)
```json
{
    "liked": ["/path/to/image1.png", "/path/to/image2.png"],
    "groups": {
        "group_id_1": {
            "name": "Hero Shots",
            "color": "#FF5733",
            "items": ["/path/to/image3.png"]
        }
    }
}
```

### _gallery_metadata.json (per workflow subdirectory)
```json
{
    "image_001.png": {
        "job_prefix": "job_001",
        "is_output": true,
        "source_images": ["/path/to/input.png"],
        "workflow": "upscale_4x",
        "seed": 12345,
        "file_id": "uuid-123",
        "parent_id": null
    }
}
```

## Common Operations

### Adding a New Gallery Feature

1. Determine which manager(s) are affected
2. Check if new metadata fields needed
3. Consider thumbnail styling implications
4. Add keyboard shortcut if applicable
5. Update persistence if state needs saving
6. Test incremental display still works

### Modifying Selection Behavior

1. Read `selection_manager.py` fully
2. Understand box selection event filter
3. Check shift-click range selection logic
4. Verify toolbar updates on selection change
5. Test with stacked view (different widget structure)

### Adding New View Mode

1. Add mode to `ui_manager.py` mode list
2. Implement display logic in `gallery_manager.py`
3. Handle incremental updates for new mode
4. Consider sort interaction
5. Update widget cache strategy if needed

## Thread Safety in Gallery

- `_widget_cache` access: Main thread only (Qt widgets)
- `_cached_items` list: Protected by refresh debouncing
- Metadata cache: Uses `threading.Lock` in `comfyui/metadata.py`
- File operations: Run in workers, signals update UI
- FavoritesManager JSON writes: Atomic via temp file + rename

## Event Bus Integration

Gallery listens to cross-tab events:
```python
from core.event_bus import pipeline_events

# In GalleryTab.initialize()
pipeline_events.job_completed.connect(self._on_external_job_completed)
pipeline_events.gallery_item_added.connect(self._on_item_added_externally)
```

Gallery emits events:
```python
pipeline_events.gallery_selection_changed.emit(selected_paths)
pipeline_events.gallery_item_deleted.emit(deleted_path)
```

## Files to Read Before Gallery Changes

1. `gallery_tab.py` - Main tab orchestration
2. `gallery_manager.py` - If changing display/sorting
3. Specific manager for the feature area
4. `base_manager.py` - For helper patterns
5. `thumbnail_styles.py` - If changing appearance
6. `comfyui/metadata.py` - If changing metadata handling
