# Gallery Tab Architecture

The gallery tab uses a manager-based architecture for better maintainability and separation of concerns. Each manager handles a specific aspect of gallery functionality.

## Manager Overview

| Manager | File | Responsibility |
|---------|------|----------------|
| **GalleryManager** | `gallery_manager.py` | Main coordinator - item loading, display, delegation to sub-managers |
| **SelectionManager** | `selection_manager.py` | Multi-select, box selection, shift-click, selection state |
| **ViewerManager** | `viewer_manager.py` | Full-size viewer lifecycle, embedded vs fullscreen modes |
| **OperationsManager** | `operations_manager.py` | Batch operations - delete, copy, publish, move |
| **RefreshController** | `refresh_controller.py` | File watching, polling, incremental updates, scanning |
| **UIManager** | `ui_manager.py` | Sort controls, filter controls, view mode (grid/stacked) |
| **FavoritesManager** | `favorites_manager.py` | Likes, groups data, persistence to JSON |
| **GroupsFilterPanel** | `groups_panel.py` | Groups sidebar UI, color-coded group chips |

## Supporting Components

| Component | File | Responsibility |
|-----------|------|----------------|
| **BaseGalleryManager** | `base_manager.py` | Base class with shared functionality (workers, status, logging) |
| **JobStatusBar** | `job_status_bar.py` | Running job status display, progress tracking |
| **QuickActionsBar** | `quick_actions_bar.py` | Quick action buttons for common operations |
| **FiltersDialog** | `filters_dialog.py` | Advanced filter configuration dialog |
| **StacksDialog** | `stacks_dialog.py` | Stack management and configuration |

## Architecture Diagram

```
GalleryTab
    │
    ├── GalleryManager (coordinator)
    │       │
    │       ├── SelectionManager
    │       │       └── handles selection state, box select, multi-select
    │       │
    │       ├── ViewerManager
    │       │       └── full-size viewer, keyboard nav, 3D model preview
    │       │
    │       ├── OperationsManager
    │       │       └── delete, copy, publish, batch operations
    │       │
    │       ├── RefreshController
    │       │       └── file watching, incremental updates, prewarm
    │       │
    │       ├── UIManager
    │       │       └── sort, filter, view mode, user selection
    │       │
    │       └── FavoritesManager
    │               └── likes, groups, persistence
    │
    ├── JobStatusBar (independent widget)
    │
    └── GroupsFilterPanel (sidebar widget)
```

## Communication Patterns

### Internal (Manager to Manager)
Managers communicate through the parent `GalleryTab` reference:
```python
# From SelectionManager
self.tab.operations_manager.delete_selected()
```

### Cross-Tab (via Event Bus)
Gallery subscribes to job events from ComfyUI:
```python
from core.import_utils import get_event_bus
pipeline_events, _ = get_event_bus()
pipeline_events.job_completed.connect(self._on_job_completed)
```

### External Events Emitted
- `gallery_refresh_requested` - Request gallery refresh from other tabs
- `gallery_navigate_to` - Navigate to specific item
- `add_to_canvas` - Send items to canvas tab
- `favorites_changed` - Notify when likes/groups change

## BaseGalleryManager

All managers inherit from `BaseGalleryManager` which provides:

```python
class BaseGalleryManager:
    # Access to tab and app state
    @property
    def app_state(self): ...
    @property
    def main_window(self): ...

    # Shared helpers
    def start_worker(self, func, *args, on_result=..., on_error=...): ...
    def show_status(self, message, level="info"): ...
    def log(self, message): ...
    def update_status_with_spinner(self, message, color, start=True): ...
```

## Adding a New Manager

1. Create `new_manager.py` in this directory
2. Inherit from `BaseGalleryManager`
3. Implement `__init__(self, tab)` calling `super().__init__(tab)`
4. Add to `__init__.py` exports
5. Instantiate in `GalleryManager.__init__()` or `GalleryTab.initialize()`

Example:
```python
from .base_manager import BaseGalleryManager

class NewManager(BaseGalleryManager):
    def __init__(self, tab):
        super().__init__(tab)
        # Initialize manager-specific state

    def do_something(self):
        self.show_status("Doing something...", "info")
        # Use self.tab to access other managers or UI
```

## Key Design Decisions

1. **Composition over inheritance** - Tab composes managers rather than inheriting functionality
2. **Single responsibility** - Each manager handles one concern
3. **Shared base class** - Common functionality in BaseGalleryManager
4. **Tab as coordinator** - GalleryTab owns managers and mediates communication
5. **Event bus for cross-tab** - Loose coupling between tabs via signals

## File Data Flow

```
Network/Custom Path
        │
        ▼
RefreshController.scan()
        │
        ▼
GalleryManager.display_items()
        │
        ├─► UIManager (sort/filter)
        │
        ├─► SelectionManager (track selection)
        │
        └─► FavoritesManager (load likes/groups)
                │
                ▼
        Thumbnails displayed in FlowLayout
```

## Metadata Flow

```
ComfyUI Job Completes
        │
        ▼
comfyui/metadata.py writes _gallery_metadata.json
        │
        ▼
RefreshController detects new files
        │
        ▼
GalleryLoader reads metadata per-item
        │
        ▼
ThumbnailWidget styled based on metadata
```
