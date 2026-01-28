# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Work Discipline

**NEVER skip, simplify, or reduce the scope of tasks because they seem complex or because you feel you are "running out of context".** Complete every task fully as specified. If a task genuinely cannot be finished in the current session, **defer it explicitly** by either:
- listing remaining steps clearly for the user to continue later OR
- Deferring to a new task on task list so compact threshold can be hit.
**Do not silently drop items, cut corners, or produce partial implementations. Every todo item created must be completed or explicitly handed off. "Good enough" is not acceptable when the full scope was requested.**

## Project Overview

Luma Tools is a PySide6 suite of tools for an animation studio, tools are separated by tabs. The goal is to aid Animation and VFX pipeline by providing a single interface to handle denoiser render pass combiner, AYON publishing, Deadline farm jobs, Tools for MP4 making, ComfyUI AI workflows, and shot cleanup.

## Running the Application

```bash
luma_tools.bat                  # With shot context (6 args: jobname, shot, task, shotpath, user, output_subdirectory)
luma_tools_standalone.bat       # Standalone mode
install.bat                     # Deploy to L:\tools\_studio_tools\luma_tools with version management

# Direct Python
python\venv\Scripts\activate.bat
set PYTHONPATH=%CD%\python;%CD%\resources\ui;%PYTHONPATH%
python python/core/luma_tools.py
```

**Single Instance:** Uses Windows mutex `Global\\LumaToolsSingleInstance` to prevent multiple instances.

## Deployment

`install.bat` auto-increments version, updates changelog, copies code/venv to production, updates global_settings.json paths (dev→prod). Current version in `version.json` (project root).

## Project Structure

```
python/
├── core/         # luma_tools.py (main), config.py, state_manager.py, settings_manager.py, user_preferences.py
│                 # error_handling.py, utils.py, import_utils.py
├── comfyui/      # service.py (re-exports), workflow.py, editable.py, modifier.py, node_configs.py
│                 # presets_manager.py, runner.py, server.py, client.py
│                 # deadline_submitter.py, deadline_poller.py, metadata.py, ayon_publisher.py, utils.py
├── models/       # viewer.py, animation_controller.py, animation_utils.py, thumbnail_service.py
│   └── loaders/  # base.py, factory.py, open3d_loader.py, trimesh_loader.py, assimp_loader.py, usd_loader.py, smpl_loader.py
├── ayon/         # service.py (Strategy Pattern), publisher_integration.py, validators/
├── services/     # pass_builder.py, render_service.py, mp4_maker.py, file_operations.py, deadline_utils.py
├── tabs/         # base_tab.py, *_tab.py, comfyui_*_manager.py, comfyui_polling.py (mixin)
│   ├── gallery/  # base_manager.py, selection_manager.py, viewer_manager.py, operations_manager.py
│   │             # refresh_controller.py, ui_manager.py, favorites_manager.py, groups_panel.py
│   ├── mixins/   # render_scan_mixin.py (shared render tab functionality)
│   └── dialogs/  # feature_request_dialog.py
├── ui/           # spell_checker.py, gallery_prewarm.py
resources/ui/     # workers.py, styles.py, image_viewers.py, small_widgets.py, dialogs.py
                  # file_dialogs.py, dialog_helpers.py, option_button.py
tests/            # test_loaders.py, test_animation_controller.py, test_config.py, test_file_dialogs.py
```

### Import Patterns

```python
from core.config import OIIO_PATH, FFMPEG_PATH, UIColors, UIStyles
from core.utils import ensure_directory, load_json, save_json, normalize_path
from core.state_manager import app_state  # app_state.has_shot_context(), .has_elevated_access, .refresh_admin_status()
from core.settings_manager import get_setting, set_setting
from core.error_handling import safe_operation, handle_errors, log_error
from comfyui.service import submit_comfyui_to_deadline
from comfyui.utils import resolve_comfyui_paths
from models.loaders.factory import load_model
from ayon.service import create_ayon_metadata
from services.pass_builder import PassBuilder

# File dialogs with memory (remembers last directory per context)
from file_dialogs import browse_file_with_memory, browse_directory_with_memory

# Dialog helpers - use instead of raw QMessageBox
from dialog_helpers import confirm_action, show_warning, show_error, show_info

# UI components - MUST lazy import (inside functions) to avoid worker thread issues
from ui_components import Worker  # resources/ui/ in PYTHONPATH
```

## Architecture Patterns

### Tabs (BaseTab)
Inherit from `tabs/base_tab.py`, define `ui_file`, `tab_name`, implement `connect_signals()`, `initialize()`. Register in `TAB_CONFIG` (`tabs/__init__.py`) with `restrict_key` for access control (matches keys in `global_settings.json` → `restricted_tabs` to hide tabs from non-admin users).

### Threading (CRITICAL)

**Worker Pattern (preferred - use BaseTab helper):**
```python
# Simple args
self.start_worker(my_function, arg1, arg2, on_result=self._handle_result, on_error=self._handle_error)

# With keyword arguments (use worker_kwargs)
self.start_worker(
    submit_job,
    worker_kwargs={"name": "MyJob", "priority": 50, "path": "/path/to/file"},
    on_result=self._on_submit_complete,
    on_error=self._on_submit_error,
    on_progress=self._on_progress
)
```

**Manual Worker Pattern (when BaseTab helper unavailable):**
```python
from ui_components import Worker  # Lazy import
self._worker = Worker(func, arg1)  # MUST store reference to prevent GC
self._worker.signals.result.connect(handle_result)
QThreadPool.globalInstance().start(self._worker)
```

**Rules:**
- Store worker on `self` or long-lived object (GC will delete if not stored)
- Never update Qt widgets from worker threads (use signals)
- `app_state` is thread-safe (RLock)
- Workers auto-inject `progress_callback(percent: int, message: str)` if in function signature

### Settings

- **User:** `~/.luma_tools/settings.json` (window state, tab order, last dirs)
- **Global:** `L:/tools/_studio_tools/luma_tools/global_settings/global_settings.json` (presets, restricted_tabs)
- **Key global setting:** `comfyui_network_output_path` — network path for ComfyUI outputs AND centralized logs (currently `W:/LumaRND/tmp/ComfyUI_OUT`). Used by runner.py, server.py, luma_tools.py for log file destinations, and by gallery/submitter for output paths.

Use `get_setting(key)` / `set_setting(key, val)` from `core.settings_manager`.

**IMPORTANT:** `get_setting()` raises `KeyError` for unknown settings. Always wrap in try/except when reading settings that may not exist:
```python
try:
    value = get_setting("my_new_setting")
except KeyError:
    value = False  # default
```

**Adding New Settings:** Settings use a registry pattern in `core/settings_manager.py`. Add a `SettingDef` to `SETTINGS_REGISTRY`:
```python
SETTINGS_REGISTRY: Dict[str, SettingDef] = {
    # scope: "global" (shared JSON on network) or "user" (local ~/.luma_tools/)
    "my_new_setting": SettingDef("my_new_setting", default=False, scope="user"),
    # With validation:
    "my_validated_setting": SettingDef("my_validated_setting", "option_a", "global", _my_validator),
}
```
Once registered, `get_setting("my_new_setting")` and `set_setting("my_new_setting", value)` work automatically. Settings are cached; `clear_settings_cache()` after external modifications.

### State Manager (Thread-Safe Global State)
`core/state_manager.py`: Singleton `ApplicationState` accessed via `app_state`. Uses `ThreadSafeProperty` descriptors with RLock for thread-safe property access from both GUI and worker threads.

```python
from core.state_manager import app_state

# Read/write state (thread-safe automatically)
app_state.jobname = "MyJob"
current = app_state.jobname

# Role checks (cached, thread-safe)
if app_state.is_admin:       # Full access including Settings tab
if app_state.is_sup:         # Supervisor access (ComfyUI, Gallery)
if app_state.has_elevated_access:  # Admin or supervisor
app_state.refresh_admin_status()   # Force re-check after role changes

# Shot context
if app_state.has_shot_context():   # True when launched with AYON context
```

State groups: command line args (jobname, shot, task, shotpath, user), Pass Builder (renders, channels, searchpath, frames), MP4 (mp4_renders, mp4_searchpath), rePublish (republish_renders), ComfyUI (comfyui_workflow_path, comfyui_iterate_mode), standalone_mode.

### 3D Model Loaders (Strategy Pattern)
`models/loaders/factory.py`: `load_model()` tries loaders by format priority (USD→Trimesh→Assimp→Open3D→SMPL). Each loader in `models/loaders/` implements `BaseModelLoader` ABC.

### Gallery Managers
`tabs/gallery/` decomposes gallery functionality: `selection_manager.py` (multi-select), `viewer_manager.py` (viewer lifecycle), `operations_manager.py` (batch ops), `refresh_controller.py` (file watching), `ui_manager.py` (sort/filter/view mode), `favorites_manager.py` (likes/groups), `groups_panel.py` (sidebar UI).

**Incremental Updates:** Gallery uses incremental display to avoid flashing when new items arrive. `display_items(items, view_mode, incremental=True)` adds only new items without clearing existing widgets. Stacked view uses `_update_stacked_items_incrementally()`.

**Item Metadata:** Gallery items have `has_metadata` field indicating if ComfyUI metadata was found (for styling), `is_input` for source images, and `job_prefix` for grouping.

**Likes & Groups:** Users can like items and organize them into color-coded groups. Data stored in `_gallery_favorites.json` per output directory.

**Gallery Keyboard Shortcuts:** `L` (toggle like), `G` (quick add to group), `Ctrl+G` (group management dialog), `1-9` (quick assign to group by number).

**Thumbnail Styling:** `resources/ui/thumbnail_styles.py` centralizes thumbnail appearance via `ThumbnailStyler`. Border/background color priority: group color > liked color > stack color > metadata-based default. New items use a pulsing "NEW" badge (blue) rather than border color changes.

### Mixin Pattern
`PollingMixin` (`tabs/comfyui_polling.py`): Add via inheritance, call `_init_polling_state()` in `initialize()`, then `_start_iterate_polling()` or `_start_batch_polling(job_ids)`.

`RenderScanMixin` (`tabs/mixins/render_scan_mixin.py`): For tabs working with render sequences. Provides source selection (for_comp/raw/custom), version handling, render scanning.
```python
class MyRenderTab(RenderScanMixin, BaseTab):
    # Widget names to override
    _render_list_widget = "MyRendersList"
    _source_button = "MySourceButton"
    # app_state attributes
    _renders_attr = "my_renders"
    _searchpath_attr = "my_searchpath"
```

## Configuration

**Environment (auto-set by batch files):**
- `AYON_LAUNCHER_LOCAL_DIR`, `DEADLINE_PATH`, `BUILTIN_OCIO_ROOT`, `PYTHONPATH`
- `QTWEBENGINE_DISABLE_SANDBOX=1`, `QTWEBENGINE_CHROMIUM_FLAGS=--in-process-gpu`, `QT_IMAGEIO_MAXALLOC=2048`

**Key Settings:** ACES-ACEScg colorspace, sRGB view, 25 FPS, Deadline pool=luma, group=processing_group

**Standalone Mode:** Limited functionality when AYON unavailable (no OIIO/FFmpeg)

## Key Workflows

### ComfyUI
1. Select preset, scan for `_editable` suffix nodes (dynamic UI), select images, configure params
2. Submit to Deadline (each frame = different seed), `comfyui/runner.py` executes on farm
3. **Module decomposition:** `workflow.py` (load/format detection/API conversion), `editable.py` (node extraction), `modifier.py` (parameter modification), `service.py` (re-exports all public APIs)
4. **Editable Nodes:** See `EDITABLE_NODE_CONFIGS` in `comfyui/node_configs.py`
5. **Subgraph Expansion:** `expand_subgraphs()` expands UUID component nodes into concrete nodes
6. **Export Nodes:** Add to `EXPORT_NODE_TYPES` dict (maps node type → filename param), add to `WIDGET_MAPPINGS`
7. **Metadata:** `comfyui/metadata.py` stores/loads job metadata (job_prefix, is_output, source_images) in `_gallery_metadata.json` per directory

### Pass Building
`find_renders()` → `detect_passes()` → `PassBuilder.build_passes()` (OIIO/Deadline) → AYON publish

### MP4 Generation
Scan renders → configure quality/burn-in → `services/mp4_maker.py` (FFmpeg)

## Development

**Setup:** Python 3.10+, PySide6, pre-configured venv in `python/venv/`. No build process.
**Key deps:** PySide6 ≥6.6, open3d ≥0.18, trimesh ≥4.10, usd-core ≥25.11, PyOpenGL ≥3.1, pyenchant ≥3.3

**Testing:**
```bash
python -m pytest tests/              # Run all tests
python -m pytest tests/test_config.py -v  # Run single test file
python -m pytest tests/ -k "test_name"    # Run specific test by name
```
`tests/conftest.py` auto-configures PYTHONPATH and skips `test_animation_controller` and `test_loaders` if numpy is broken (common in some venv states). Manual testing also required (both launcher modes, with/without AYON env).

### Windows PowerShell (for Claude Code)
Always use PowerShell for Python scripts (Bash compatibility layer has path issues):
```powershell
# Syntax check a file
powershell -Command "Set-Location 'l:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'; python\venv\Scripts\python.exe -m py_compile python\tabs\file.py"

# Run all tests
powershell -Command "Set-Location 'l:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'; python\venv\Scripts\python.exe -m pytest tests/ -v"

# Run single test file
powershell -Command "Set-Location 'l:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'; python\venv\Scripts\python.exe -m pytest tests\test_loaders.py -v"

# Quick import check
powershell -Command "Set-Location 'l:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'; python\venv\Scripts\python.exe -c \"import sys; sys.path.insert(0, 'python'); sys.path.insert(0, 'resources/ui'); from tabs.my_tab import MyTab; print('OK')\""
```

**CRITICAL: PowerShell `$` variable escaping.** The bash compatibility layer mangles PowerShell `$` variables (e.g., `$LASTEXITCODE` becomes `extglob`, `$env:PYTHONPATH` becomes `:PYTHONPATH`). For any commands that use PowerShell variables or `$env:`, write a temporary `.ps1` script file and run it instead:
```powershell
# Write the script
Write tool → _temp_script.ps1

# Execute it
powershell -ExecutionPolicy Bypass -File "l:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools\_temp_script.ps1"
```

### Debugging

**Logging:** All output uses Python `logging` module (not `print()`). Every module should have:
```python
import logging
logger = logging.getLogger(__name__)
```
Use `logger.info()`, `logger.warning()`, `logger.error()`. Never use `print()` for new code.

**Log Files:** All logs are centralized on the network path from `comfyui_network_output_path` global setting:
```
<network_path>/_logs/
├── users/    # Main app logs: luma_tools_<user>_<hostname>_<timestamp>.log
├── server/   # Persistent server logs: comfyui_server_<hostname>_<timestamp>.log
├── runner/   # Farm runner logs: comfyui_runner_<jobname>_<timestamp>.log
```
Currently: `W:/LumaRND/tmp/ComfyUI_OUT/_logs/`. Falls back to `~/.luma_tools/logs/` if network unavailable.

**Reading logs (NO SCRIPT NEEDED):**
```bash
# Get latest log file path (use for Read tool)
powershell -Command "(Get-ChildItem 'W:\LumaRND\tmp\ComfyUI_OUT\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName"

# Read last 100 lines directly
powershell -Command "Get-Content (Get-ChildItem 'W:\LumaRND\tmp\ComfyUI_OUT\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 100"

# Search for errors across all logs
Grep pattern="ERROR|Exception|Traceback" path="W:\LumaRND\tmp\ComfyUI_OUT\_logs\users\" output_mode="content"

# Read specific log with Read tool (use offset=-100 for last 100 lines)
Read tool on log path with offset=-100
```
**IMPORTANT:** PowerShell one-liners work fine for file operations. Only use `.ps1` script files when you need `$env:` variables (which get mangled by bash compatibility layer).

**Debug CLI Arguments:** The app supports debug flags that can be appended after the normal positional arguments:
```
--tab <name>       Select a tab on startup (gallery, comfyui, settings, logs, passbuilder, mp4, republish, cleaner)
--auto-close <sec> Auto-close the app after N seconds (for automated testing)
```

**Running the app from Claude Code for debugging:**
Because PYTHONPATH must be set (uses `$env:` which bash mangles), write a `.ps1` script:
```powershell
# _run_test.ps1 - write this file, then execute with: powershell -ExecutionPolicy Bypass -File _run_test.ps1
Set-Location 'l:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe python\core\luma_tools.py --tab gallery --auto-close 30

# With shot context:
# python\venv\Scripts\python.exe python\core\luma_tools.py LumaRND '' '' 'W:\LumaRNDwork' 'christophe.leyder' 'combined' --tab gallery --auto-close 30
```

```powershell
# After app closes, read the latest log from network path
powershell -Command "Get-ChildItem 'W:\LumaRND\tmp\ComfyUI_OUT\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Get-Content $_.FullName }"
```

**Debugging workflow:**
1. Run the app with `--tab <target> --auto-close <seconds>` in background
2. Wait for it to close (or read logs while running)
3. Read the log file with `Read` tool or search with `Grep`
4. All gallery, prewarm, thumbnail, and incremental sync events are logged to the file

### UI Modifications
Edit `.ui` files in Qt Designer, update tab logic in `python/tabs/`, styles in `resources/ui/la_shot_tools_styles.qss`.

### Adding Features
1. Create service in domain package, add config to `core/config.py`
2. For tabs: inherit BaseTab, register in `TAB_CONFIG` (`tabs/__init__.py`)
3. For new settings: add `SettingDef` to `SETTINGS_REGISTRY` in `core/settings_manager.py`
4. For new app state: add `ThreadSafeProperty` to `ApplicationState` in `core/state_manager.py`
5. Long ops: wrap in Worker (store on self), use signals

### AYON Publishing
- Single files: `create_ayon_metadata_single_file()` in `ayon/service.py`
- EXR sequences: `create_ayon_metadata()`
- Check `AYON_AVAILABLE`, `DEADLINE_AVAILABLE` before using features

## Common Pitfalls

### Worker GC (CRITICAL)
**Must store worker on `self`** or GC deletes before completion:
```python
# ❌ worker = Worker(func); QThreadPool.start(worker)  # Gets GC'd
# ✅ self._worker = Worker(func); QThreadPool.start(self._worker)
```

### Other Issues
- **Threading:** Use signals for cross-thread GUI updates (never direct Qt widget calls from workers)
- **Optional Deps:** Check `*_AVAILABLE` flags (AYON_AVAILABLE, DEADLINE_AVAILABLE, etc.) before using features
- **Paths:** Use `normalize_path()` from `core.utils` for AYON/Deadline compatibility; use `ensure_directory()` instead of `os.makedirs()`
- **ComfyUI Workflows:** 2 formats (UI/nodes vs API), use `is_api_format()` to detect
- **Imports:** Lazy import UI components inside functions (avoid module-level `from resources.ui...`)

## Utilities

**core/utils.py:** Common helpers:
- `ensure_directory(path)` - create directory if needed (prefer over `os.makedirs`)
- `load_json(path, default)` / `save_json(path, data)` - with error handling and atomic writes
- `remove_prefix(s, prefix)` / `remove_suffix(s, suffix)` - Python <3.9 compatible
- `normalize_path(path)` - Windows backslash → forward slash for AYON/Deadline
- `extract_render_name(filename, strip_frame_padding=False)` - extract render name from sequence filename

**core/error_handling.py:** Consistent error handling utilities:
- `@safe_operation(name, return_on_error)` - decorator for functions that may fail
- `with handle_errors(name, reraise=False)` - context manager for error blocks
- `log_error(operation, error, variable)` - consistent error logging format
- `format_error(operation, error, variable, include_traceback)` - format error message string

**core/config.py:** `UIColors` (background, text, accent, status colors, `GROUP_COLORS` for gallery groups), `UIStyles` (reusable stylesheet snippets)

**core/import_utils.py:** `safe_import()`, `safe_import_multiple()` - graceful optional imports with `*_AVAILABLE` flags

**resources/ui/dialog_helpers.py:** Wrapper functions for QMessageBox (use instead of raw QMessageBox):
- `confirm_action(title, message, parent, detail, default_yes)` → bool - Yes/No confirmation
- `show_warning(title, message, parent, detail)` - warning dialog
- `show_error(title, message, parent, detail)` - error dialog
- `show_info(title, message, parent, detail)` - info dialog

**resources/ui/file_dialogs.py:** File dialogs with last-directory memory per context:
- `browse_file_with_memory()`, `browse_directory_with_memory()`, `save_file_with_memory()`, `browse_multiple_files_with_memory()`
- Context-specific helpers: `browse_workflow_file()`, `browse_images()`, `save_mp4_file()`, `browse_comfyui_output_dir()`, `browse_hdri_file()`, `browse_custom_renders_dir()`

**resources/ui/option_button.py:** Reusable popup menu button pattern:
```python
from option_button import OptionButtonManager, IndexedOptionButtonManager

self._source_manager = OptionButtonManager(
    button=self.ui.SourceButton,
    options=[("For Comp", "for_comp"), ("Raw", "raw")],
    initial_value="for_comp",
    on_changed=self._on_source_changed,
    label_prefix="Source: "
)
# Access: self._source_manager.value, self._source_manager.set_value("raw")
```

**comfyui/utils.py:** ComfyUI utilities:
- `resolve_comfyui_paths(comfyui_path, mode)` - get python exe and main.py for embedded/portable/standalone modes
- `check_server_health()`, `wait_for_server()` - server management

**models/animation_controller.py:** `AnimationController` (playback state, timing), `AnimationTransportBar` (play/pause/loop UI)

**tabs/base_tab.py Helpers:**
- `self.start_worker(func, *args, on_result=..., on_error=..., on_progress=..., worker_kwargs={})` - simplified worker thread management (use `worker_kwargs` for keyword arguments to function)
- `self.show_status(message, level)` - status bar updates (info/success/warning/error)
- `self.update_status_with_spinner(message, color, start=True)` - status bar with spinner control
- `self.pulse_button(widget)` - safe button animation
- `self.on_worker_success()` / `self.on_worker_error()` - standard completion handlers

**tabs/gallery/base_manager.py:** Base class for gallery manager components with same helpers as BaseTab
