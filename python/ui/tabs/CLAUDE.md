# Tabs Module

Tab system architecture for Luma Tools.

## BaseTab Pattern

All tabs inherit from `ui/tabs/base_tab.py`. Define `TAB_CONFIG`, implement `connect_signals()` and `initialize()`. Register in the tab config list in `ui/tabs/__init__.py` with `restrict_key` for access control (matches keys in `global_settings.json` → `restricted_tabs`).

```python
from ui.tabs.base_tab import BaseTab, TabConfig

class MyTab(BaseTab):
    TAB_CONFIG = TabConfig(ui_file="my_tab.ui", tab_name="My Tab")

    def connect_signals(self):
        self.ui.MyButton.clicked.connect(self._on_click)

    def initialize(self):
        self._load_data()
```

### BaseTab Helpers
- `self.start_worker(func, *args, on_result=..., on_error=..., on_progress=..., worker_kwargs={})` - simplified worker thread management (use `worker_kwargs` for keyword arguments)
- `self.spinner_context(message, success_msg)` - context manager for spinner lifecycle
- `self.show_status(message, level)` - status bar updates (info/success/warning/error)
- `self.update_status_with_spinner(message, color, start=True)` - status bar with spinner control
- `self.pulse_button(widget)` - safe button animation
- `self.on_worker_success()` / `self.on_worker_error()` - standard completion handlers

```python
def do_work(self):
    with self.spinner_context("Processing...", success_msg="Done!"):
        heavy_computation()
```

## Mixin Patterns

### PollingMixin
`ui/tabs/comfyui_polling.py`: For tabs that poll Deadline job status.
- Add via inheritance, call `_init_polling_state()` in `initialize()`
- Then `_start_iterate_polling()` or `_start_batch_polling(job_ids)`

### RenderScanMixin
`ui/tabs/mixins/render_scan_mixin.py`: For tabs working with render sequences. Provides source selection (for_comp/raw/custom), version handling, render scanning.

```python
class MyRenderTab(RenderScanMixin, BaseTab):
    # Widget names to override
    _render_list_widget = "MyRendersList"
    _source_button = "MySourceButton"
    # app_state attributes
    _renders_attr = "my_renders"
    _searchpath_attr = "my_searchpath"
```

## Tab Registration

Tabs are registered in `ui/tabs/__init__.py` via the config list. Each entry specifies:
- Tab class (lazy imported)
- `restrict_key` for access control (matches `global_settings.json` → `restricted_tabs`)
- Tab order and visibility
