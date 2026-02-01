---
name: new-tab
description: Guided scaffolding for creating a new tab in luma_tools. Asks the right questions then generates complete tab structure.
disable-model-invocation: true
argument-hint: <tab-name>
---

# New Tab Scaffolding

When the user wants to create a new tab, I MUST ask these questions BEFORE generating any code:

## Required Questions

1. **Tab name**: What should the tab be called? (e.g., "Canvas", "Timeline")
   - Used for: display name, class name, file names

2. **Restrict key**: What access restriction key? (e.g., "canvas", "timeline")
   - Used for: TAB_CONFIG registration, global_settings.json restricted_tabs

3. **Settings needed**: What user preferences should this tab save?
   - Examples: last selected option, checkbox states, input values
   - Each setting needs: key name, default value, scope (user/global)

4. **Cross-tab communication**: Does this tab need to communicate with others?
   - If yes: What events to emit? What events to listen for?
   - Uses: core/event_bus.py pipeline_events

5. **Threading needs**: Will this tab do long operations?
   - If yes: What operations? Need progress callbacks?
   - Uses: BaseTab.start_worker() pattern

6. **Access control**: Should this tab be restricted to admins/supervisors?
   - If yes: Add to global_settings.json restricted_tabs list

## Files to Create

After gathering requirements, create these files:

### 1. Tab Class: `python/ui/tabs/{name}_tab.py`
```python
"""
{Name} Tab module.

{Brief description of what the tab does}
"""

import logging
from PySide6.QtCore import Qt

from .base_tab import BaseTab

logger = logging.getLogger(__name__)


class {Name}Tab(BaseTab):
    """{Description}"""

    @property
    def ui_file(self) -> str:
        return "{name}.ui"

    @property
    def tab_name(self) -> str:
        return "{Display Name}"

    def connect_signals(self):
        """Connect tab-specific signals."""
        # Connect UI signals
        # self.ui.myButton.clicked.connect(self._on_button_clicked)
        pass

    def initialize(self):
        """Initialize tab after UI is loaded."""
        # Load saved settings
        # Connect to event bus if needed
        # Setup initial state
        pass

    def on_tab_activated(self):
        """Called when tab becomes visible."""
        pass

    def on_tab_deactivated(self):
        """Called when switching away from tab."""
        pass

    # =========================================================================
    # Event Handlers
    # =========================================================================

    # =========================================================================
    # Worker Operations (if threading needed)
    # =========================================================================

    def _do_long_operation(self):
        """Example worker operation."""
        from ui_components import StatusColors

        self.update_status_with_spinner("Processing...", StatusColors.INFO)

        self.start_worker(
            self._long_operation_func,
            worker_kwargs={"param": "value"},
            on_result=self._on_operation_complete,
            on_error=self._on_operation_error
        )

    def _long_operation_func(self, param, progress_callback=None):
        """Runs in worker thread. Return result, don't touch UI."""
        # Do work here
        if progress_callback:
            progress_callback(50, "Halfway done")
        return result

    def _on_operation_complete(self, result):
        """Handle successful operation."""
        self.on_worker_success("Operation complete!")

    def _on_operation_error(self, error_msg, traceback_str):
        """Handle operation error."""
        self.on_worker_error(error_msg, traceback_str, status_prefix="{Name}")
```

### 2. UI File: `resources/ui/tabs/{name}.ui`
Create in Qt Designer with basic layout:
- Main vertical layout
- Placeholder widgets for tab content
- Standard button styling from UIStyles

### 3. Register in `python/ui/tabs/__init__.py`
```python
from .{name}_tab import {Name}Tab

__all__ = [
    # ... existing exports
    '{Name}Tab',
]

TAB_CONFIG = [
    # ... existing tabs
    {{'class': {Name}Tab, 'restrict_key': '{restrict_key}'}},
]
```

### 4. Add Settings (if needed) in `core/settings_manager.py`
```python
SETTINGS_REGISTRY = {{
    # ... existing settings
    "{name}_setting_1": SettingDef("{name}_setting_1", default=False, scope="user"),
    "{name}_setting_2": SettingDef("{name}_setting_2", default="option_a", scope="user"),
}}
```

### 5. Add Event Bus Signals (if needed) in `core/event_bus.py`
```python
class PipelineEvents(QObject):
    # ... existing signals
    {name}_event = Signal(str)  # Add with appropriate signature
```

## Checklist Before Completion

- [ ] Tab class inherits from BaseTab
- [ ] ui_file and tab_name properties defined
- [ ] connect_signals() implemented (even if empty)
- [ ] initialize() implemented (even if empty)
- [ ] Registered in TAB_CONFIG with restrict_key
- [ ] Imported and exported in __init__.py
- [ ] Settings added to SETTINGS_REGISTRY if needed
- [ ] Event bus signals added if needed
- [ ] .ui file created with matching name
- [ ] Logger initialized at module level
- [ ] Worker operations store worker on self._worker
- [ ] UI component imports are lazy (inside methods)

## Mixin Integration

### RenderScanMixin (for tabs working with render sequences)

```python
from .mixins.render_scan_mixin import RenderScanMixin

class MyRenderTab(RenderScanMixin, BaseTab):
    # Widget names to override (must match .ui file)
    _render_list_widget = "MyRendersList"  # QListWidget for renders
    _source_button = "MySourceButton"       # OptionButton for source selection

    # app_state attribute names for storing state
    _renders_attr = "my_renders"            # List of render paths
    _searchpath_attr = "my_searchpath"      # Current search path

    def initialize(self):
        self._init_render_scan()  # Initialize mixin
        # ... rest of initialization
```

RenderScanMixin provides:
- Source selection (for_comp/raw/custom)
- Render scanning and version detection
- Frame range detection
- Automatic state persistence to app_state

### PollingMixin (for tabs that submit Deadline jobs)

```python
from .comfyui_polling import PollingMixin

class MyJobTab(PollingMixin, BaseTab):
    def initialize(self):
        self._init_polling_state()  # MUST call first
        # ... rest of initialization

    def _on_submit_success(self, job_id, total_frames):
        # Single job polling
        self._start_iterate_polling(job_id, total_frames)

    def _on_batch_submit(self, job_ids):
        # Multiple jobs polling
        self._start_batch_polling(job_ids)
```

PollingMixin provides:
- Deadline job status polling
- Progress tracking and UI updates
- Completion detection and event emission
- Lambda closure safety (captures by value)

## Keyboard Shortcuts

For tabs with keyboard shortcuts, implement in `initialize()`:

```python
def initialize(self):
    # ... other initialization
    self._setup_keyboard_shortcuts()

def _setup_keyboard_shortcuts(self):
    """Setup keyboard shortcuts for this tab."""
    from PySide6.QtWidgets import QShortcut
    from PySide6.QtGui import QKeySequence

    # Simple shortcut
    self._shortcut_refresh = QShortcut(QKeySequence("F5"), self)
    self._shortcut_refresh.activated.connect(self._on_refresh)

    # With modifier
    self._shortcut_select_all = QShortcut(QKeySequence("Ctrl+A"), self)
    self._shortcut_select_all.activated.connect(self._select_all)
```

CRITICAL: Store shortcuts on `self._shortcut_*` to prevent garbage collection.

## Tab Lifecycle Methods

```python
def on_tab_activated(self):
    """
    Called when tab becomes visible (user switches to this tab).

    Use for:
    - Refreshing data that may have changed
    - Starting auto-refresh timers
    - Updating UI based on external state changes
    - Resetting "new items" counters
    """
    # Example: refresh gallery when tab becomes visible
    self._refresh_if_needed()

def on_tab_deactivated(self):
    """
    Called when switching away from this tab.

    Use for:
    - Stopping auto-refresh timers to save resources
    - Saving unsaved state
    - Pausing expensive operations
    """
    # Example: stop polling when not visible
    if hasattr(self, '_refresh_timer') and self._refresh_timer.isActive():
        self._refresh_timer.stop()
```

## Reference: gallery_tab.py Structure

For complex tabs, reference gallery_tab.py which demonstrates:
- Manager decomposition pattern
- Worker thread usage
- Event bus integration
- Settings persistence
- Keyboard shortcuts
- Context menus
