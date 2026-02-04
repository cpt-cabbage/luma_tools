# Gallery Module

Decomposed gallery functionality for browsing and managing ComfyUI outputs.

## Manager Architecture

The gallery is decomposed into focused managers:

- `gallery_manager.py` - Main orchestrator, coordinates all managers
- `selection_manager.py` - Multi-select with Shift/Ctrl support
- `viewer_manager.py` - Image/video viewer lifecycle and navigation
- `operations_manager.py` - Batch operations (delete, move, publish)
- `refresh_controller.py` - File watching and incremental refresh
- `ui_manager.py` - Sort/filter/view mode controls
- `favorites_manager.py` - Likes and group management
- `groups_panel.py` - Sidebar UI for group browsing and filtering
- `base_manager.py` - Base class with same helpers as BaseTab (start_worker, show_status, etc.)

## Key Patterns

### Incremental Updates
Gallery uses incremental display to avoid flashing when new items arrive. `display_items(items, view_mode, incremental=True)` adds only new items without clearing existing widgets. Stacked view uses `_update_stacked_items_incrementally()`.

### Item Metadata
Gallery items have:
- `has_metadata` - Whether ComfyUI metadata was found (affects styling)
- `is_input` - Whether this is a source/input image
- `job_prefix` - For grouping items by generation job

### Likes & Groups
Users can like items and organize them into color-coded groups. Data stored in `_gallery_favorites.json` per output directory.

### Keyboard Shortcuts
- `L` - Toggle like on selected item(s)
- `G` - Quick add to group
- `Ctrl+G` - Group management dialog
- `1-9` - Quick assign to group by number

### Thumbnail Styling
`resources/ui/thumbnail_styles.py` centralizes thumbnail appearance via `ThumbnailStyler`. Border/background color priority: group color > liked color > stack color > metadata-based default. New items use a pulsing "NEW" badge (blue) rather than border color changes.
