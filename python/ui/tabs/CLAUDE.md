# Tabs Module

Tab system architecture for Luma Tools.

## BaseTab Pattern

All tabs inherit from `ui/tabs/base_tab.py`. Define `TAB_CONFIG`, implement `connect_signals()` and `initialize()`. Register in `TAB_REGISTRY` in `ui/tabs/__init__.py` with `(module_path, class_name, restrict_key)` for lazy loading and access control.

**Note:** `initialize()` is deferred until the tab is first activated. Only `load_ui()` and `connect_signals()` run at startup. Do not assume initialized state in signal handlers unless the tab has been activated.

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

Tabs are registered in `ui/tabs/__init__.py` via `TAB_REGISTRY` — a list of `(module_path, class_name, restrict_key)` tuples. Tab modules are **not** imported at package level; they're loaded lazily via `importlib` during `_load_tabs()`.

```python
# ui/tabs/__init__.py
TAB_REGISTRY = [
    ('.comfyui', 'ComfyUITab', 'comfyui'),
    ('.gallery_tab', 'GalleryTab', 'gallery'),
    # ...
]
```

## Startup Optimization

### Precompiled UI Files
`.ui` files are precompiled to Python via `pyside6-uic` and stored in `resources/ui/tabs/_compiled/ui_<name>.py`. `BaseTab.load_ui()` loads these first, falling back to `QUiLoader` if missing. This eliminates a ~5s first-load penalty from Qt's UiTools module initialization.

**After editing a `.ui` file in Qt Designer**, regenerate the compiled version:
```bash
python/venv/Scripts/pyside6-uic.exe resources/ui/tabs/<name>.ui -o resources/ui/tabs/_compiled/ui_<name>.py -g python
```
Or recompile all:
```bash
for f in resources/ui/tabs/*.ui; do python/venv/Scripts/pyside6-uic.exe "$f" -o "resources/ui/tabs/_compiled/ui_$(basename "$f" .ui).py" -g python; done
```
The deploy script runs this automatically.

### Deferred Tab Initialization
`initialize()` is **not** called during `_load_tabs()`. Only UI loading and signal connections happen at startup. `initialize()` runs on first tab activation via `BaseTab._ensure_initialized()`, which shows a loading overlay. The initially visible tab is initialized eagerly after tab order is restored.
