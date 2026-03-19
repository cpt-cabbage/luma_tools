# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Work Discipline

**NEVER skip, simplify, or reduce the scope of tasks because they seem complex or because you feel you are "running out of context".** Complete every task fully as specified. If a task genuinely cannot be finished in the current session, **defer it explicitly** by either:
- listing remaining steps clearly for the user to continue later OR
- Deferring to a new task on task list so compact threshold can be hit.
**Do not silently drop items, cut corners, or produce partial implementations. Every todo item created must be completed or explicitly handed off. "Good enough" is not acceptable when the full scope was requested.**
**When adding new features or doing any larger changes, always ask clarifying questions to the user to create absolute certainty in task planning**
Do not update changelog and version, user does that.

## Multi-File Implementation Discipline

When a feature touches more than 2-3 files, follow these rules to avoid introducing regressions:

**Implement in layers, not all at once:**
1. Data/config layer first (settings, state, models)
2. Service/logic layer next (business logic, utilities)
3. Signal wiring and integration
4. UI layer last
After each layer, pause and tell the user what existing flows could be affected and what to test before continuing.

**Before removing or renaming anything:**
- Grep the entire codebase for all references before deleting or renaming functions, methods, signals, or attributes
- Update all call sites in the same change — never leave orphaned references
- If tests reference removed code, update tests in the same pass

**When adding new attribute usage to a class:**
- Check that the attribute is initialized in `__init__` (or the class's setup method like `initialize()`)
- This is the #1 source of runtime `AttributeError` bugs in this codebase

**When modifying event handlers, signals, or mouse/keyboard interactions:**
- Trace what other features share that event path (e.g., mouse events used by both pen tool and pan, keyboard events shared between gallery and canvas)
- Test the adjacent features, not just the one being changed

**Run the test suite at natural checkpoints** — after completing a logical layer of changes, not after every single edit.

## Skills

This project has skills in `.claude/skills/`.

| Skill | When to Apply | Invocation |
|-------|---------------|------------|
| **check-code** | **After writing larger code changes that affects:** threading, imports, settings patterns before presenting. | Auto (runs automatically, do not invoke manually) |
| **commit-message** | Generate well-formatted commit messages from staged/unstaged changes | `/commit-message` |
| **feature-dev** | Guided feature development with codebase understanding and architecture focus | `/feature-dev` |
| **paper-watcher** | Track research papers, check for code releases and ComfyUI custom node support | `/paper-watcher` |

## Per-Module Documentation

Detailed architecture and API reference for each module lives in CLAUDE.md files within the module directories. These are loaded automatically when working on files in those directories.

| Module CLAUDE.md | Contents |
|------------------|----------|
| `python/core/CLAUDE.md` | utils, error_handling, validators, caching, metadata_file, config, logging_utils, subprocess_utils, event_bus |
| `python/comfyui/CLAUDE.md` | Workflow pipeline, editable nodes, export nodes, subgraphs, metadata, Deadline integration |
| `python/ui/canvas/CLAUDE.md` | Canvas architecture, multi-canvas system, network sync, items, drawing, undo, export |
| `python/ui/tabs/CLAUDE.md` | BaseTab pattern, helpers, PollingMixin, RenderScanMixin, tab registration |
| `python/ui/tabs/gallery/CLAUDE.md` | Gallery managers, incremental updates, favorites, groups, keyboard shortcuts, thumbnail styling |
| `resources/ui/CLAUDE.md` | dialog_helpers, file_dialogs, option_button, thumbnails, spinners, viewers, effects |

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

## Deployment

`deploy_production.bat` runs `scripts/deploy.py` which auto-increments version, updates changelog, copies code/venv to production, updates global_settings.json paths (dev→prod). Version in `resources/version.json`, changelog in `resources/changelog.md`.

**Version increment strategies** (deploy script prompts for type):
- **`b` (big):** `0.4` → `0.5` (major feature)
- **`s` (small):** `0.4` → `0.4.1`, or `0.4.1` → `0.4.2` (bug fix, minor enhancement)
- **`m` (minor):** `0.4` → `0.4.0.1`, `0.4.1` → `0.4.1.1` (hotfix)

**Details:** Venv is never deleted/overwritten in target. `.pyc`/`__pycache__` are not copied. All network paths in `global_settings.json` are rewritten from dev to prod. Changelog entry uses latest git commit message (full body). `.ui` files are precompiled to Python via `pyside6-uic` after resource copy.

## Project Structure

```
python/
├── core/         # App entry (luma_tools.py), config, state_manager, settings_manager, utils, error_handling
├── deadline/     # Deadline farm job submission, polling, parsing
├── comfyui/      # Workflow load/modify/submit pipeline, presets, server/client
├── geo/          # 3D model loading (Strategy pattern), Three.js viewer, animation
│   └── loaders/  # Format-specific loaders (USD, Trimesh, Assimp, Open3D, SMPL)
├── ayon/         # AYON publishing service (Strategy pattern), validators
├── services/     # pass_builder, render_service, mp4_maker, file_operations
├── ui/
│   ├── canvas/   # Collaborative infinite canvas with network sync
│   └── tabs/     # BaseTab subclasses, one per tool tab
│       ├── gallery/  # Decomposed manager architecture (see gallery/CLAUDE.md)
│       └── mixins/   # Shared tab functionality (RenderScanMixin)
resources/
├── ui/           # Shared widgets, dialogs, styles, workers, thumbnails
│   └── tabs/     # .ui files for each tab (Qt Designer)
│       └── _compiled/  # Precompiled .ui → .py (pyside6-uic, auto-generated)
├── version.json
└── changelog.md
scripts/          # deploy.py, install_venv.py
tests/
```

### Import Patterns

```python
from core.config import OIIO_PATH, FFMPEG_PATH, UIColors, UIStyles
from core.utils import ensure_directory, load_json, save_json, normalize_path
from core.state_manager import app_state  # app_state.has_shot_context(), .has_elevated_access, .refresh_admin_status()
from core.settings_manager import get_setting, set_setting
from core.error_handling import safe_operation, handle_errors, log_error
from core.event_bus import pipeline_events  # Cross-tab communication singleton
from core.user_preferences import get_window_state, save_gallery_settings  # High-level settings API
from deadline.submitter import submit_comfyui_to_deadline
from comfyui.utils import resolve_comfyui_paths
from geo.loaders.factory import load_model
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
Inherit from `ui/tabs/base_tab.py`, define `TAB_CONFIG` (with `ui_file`, `tab_name`), implement `connect_signals()`, `initialize()`. Register in `TAB_REGISTRY` (`ui/tabs/__init__.py`) with `(module_path, class_name, restrict_key)`. See `python/ui/tabs/CLAUDE.md` for BaseTab helpers, mixin patterns, and startup optimization details.

**Important:** `initialize()` is deferred until first tab activation (not called during startup). Only `load_ui()` and `connect_signals()` run eagerly. Do not access state created in `initialize()` from `connect_signals()` handlers unless guarded.

**Key BaseTab helpers beyond `start_worker`:**
- `spinner_context(message, success_msg, error_msg)` — context manager for automatic spinner lifecycle
- `on_worker_success(message, status_message, log_message)` — standard success handler
- `on_worker_error(error_tuple, status_prefix, show_dialog)` — standard error handler
- `unpack_worker_error(error_tuple)` — extract message from worker error signal

**OptionButtonManager** — widely used for dropdown-style toggle buttons:
```python
from option_button import OptionButtonManager
self._source_manager = OptionButtonManager(
    button=self.ui.SourceButton,
    options=[("For Comp", "for_comp"), ("Raw", "raw")],
    initial_value="for_comp",
    on_changed=self._on_source_changed,
    label_prefix="Source: ",
)
# self._source_manager.value / .set_value("raw")
```

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

**Thread-Safe Caching:** When caching data accessed from multiple threads, use locks:
```python
import threading
self._cache_lock = threading.RLock()

with self._cache_lock:
    self._cache[key] = value  # Thread-safe access
```

### Settings

- **User:** `~/.luma_tools/settings.json` (window state, tab order, last dirs)
- **Global:** `L:/tools/_studio_tools/luma_tools/global_settings/global_settings.json` (presets, restricted_tabs)
- **Key global setting:** `network_output_path` — network path for outputs AND centralized logs (currently `W:/LumaRND/luma_tools`). Used by runner.py, server.py, luma_tools.py for log file destinations, and by gallery/submitter for output paths.

Use `get_setting(key)` / `set_setting(key, val)` from `core.settings_manager`.

**Safe accessors (preferred):** Use `safe_get_setting()` and `safe_set_setting()` to avoid try/except boilerplate:
```python
from core.settings_manager import safe_get_setting, safe_set_setting

# These never raise KeyError
value = safe_get_setting("my_new_setting", False)  # returns False if not found
safe_set_setting("my_setting", new_value)  # returns True/False, verbose=False by default
```

**Raw accessors:** `get_setting()` raises `KeyError` for unknown settings:
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

### Event Bus (Cross-Tab Communication)
`core/event_bus.py`: Central signal hub (`pipeline_events` singleton) for decoupled cross-tab communication. Used by ComfyUI, Gallery, Canvas, and Settings tabs.

```python
from core.event_bus import pipeline_events

# Emit events
pipeline_events.job_submitted.emit(job_id, expected_count, prefix)
pipeline_events.job_completed.emit(job_id, output_paths)

# Listen to events (connect in initialize(), not in methods called repeatedly)
pipeline_events.job_completed.connect(self._on_job_completed)
```

**Key signal groups:**
- **ComfyUI → Gallery:** `job_submitted`, `job_progress`, `job_output_ready`, `job_completed`, `job_failed`, `all_jobs_completed`
- **Gallery → ComfyUI:** `use_as_input`, `copy_settings`, `selection_changed`
- **Canvas:** `add_to_canvas`, `canvas_image_added`, `gallery_navigate_to`
- **Viewer:** `toggle_item_like`, `add_item_to_group`, `show_item_properties`

Includes thread-safe job tracking via `JobInfo` dataclass and `GalleryContext` for state sharing.

### User Preferences (High-Level Settings API)
`core/user_preferences.py` provides typed wrappers over raw settings for common preferences. **Prefer these over direct `get_setting`/`set_setting` for standard preferences:**

```python
from core.user_preferences import (
    get_window_state, save_window_state,
    get_tab_order, save_tab_order,
    get_gallery_settings, save_gallery_settings,
    is_new_version, set_last_opened_version,
    record_workflow_execution_time, get_workflow_estimated_time_per_frame,
    save_comfyui_running_jobs, get_comfyui_running_jobs,  # Crash recovery
)
```

### Main Window API
`core/luma_tools.py` exposes `get_main_window()` for tabs that need main window interaction:

```python
from core.luma_tools import get_main_window
main = get_main_window()
if main:
    main.show_system_notification(title, message, icon_type)
    main.select_tab_by_name(restrict_key)
    main.get_tab(tab_id)
```

### Domain-Specific Architecture
- **ComfyUI:** Workflow load/modify/submit pipeline. See `python/comfyui/CLAUDE.md`
- **Canvas:** Collaborative infinite canvas with network sync. See `python/ui/canvas/CLAUDE.md`
- **Gallery:** Decomposed manager architecture. See `python/ui/tabs/gallery/CLAUDE.md`
- **3D Loaders:** Strategy pattern in `geo/loaders/factory.py` — `load_model()` tries loaders by format priority (USD→Trimesh→Assimp→Open3D→SMPL)
- **Pass Building:** `find_renders()` → `detect_passes()` → `PassBuilder.build_passes()` (OIIO/Deadline) → AYON publish
- **MP4 Generation:** Scan renders → configure quality/burn-in → `services/mp4_maker.py` (FFmpeg)
- **File Scanners:** Strategy pattern in `services/scanners.py` — `RenderScanner`, `get_scanner(type)`, `scan_files(dir, type)`

## Configuration

**Environment (auto-set by batch files):**
- `AYON_LAUNCHER_LOCAL_DIR`, `DEADLINE_PATH`, `BUILTIN_OCIO_ROOT`, `PYTHONPATH`
- `QTWEBENGINE_DISABLE_SANDBOX=1`, `QTWEBENGINE_CHROMIUM_FLAGS=--in-process-gpu`, `QT_IMAGEIO_MAXALLOC=2048`

**Key Settings:** ACES-ACEScg colorspace, sRGB view, 25 FPS, Deadline pool=luma, group=processing_group

**Standalone Mode:** Limited functionality when AYON unavailable (no OIIO/FFmpeg)

## Development

**Setup:** Python 3.10+, PySide6, pre-configured venv in `python/venv/`. Build step: precompile `.ui` files (see below).
**Key deps:** PySide6 ≥6.6, open3d ≥0.18, trimesh ≥4.10, usd-core ≥25.11, PyOpenGL ≥3.1, pyenchant ≥3.3

**Testing:**
Tests must be run with PYTHONPATH set. From Claude Code, use a `.ps1` script:
```powershell
# _run_tests.ps1
Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe -m pytest tests\ -v                    # All tests
# python\venv\Scripts\python.exe -m pytest tests\test_config.py -v   # Single file
# python\venv\Scripts\python.exe -m pytest tests\ -k "test_name"     # By name
```
```bash
powershell -ExecutionPolicy Bypass -File _run_tests.ps1
```
Note: `pytest-timeout` is NOT installed — do not use `--timeout` flag.

**Test infrastructure (`tests/conftest.py`):**
- Auto-adds `python/` and `resources/ui/` to `sys.path`
- `NUMPY_WORKS` flag — skips `test_animation_controller.py` and `test_loaders.py` if numpy import fails (broken venv)
- Use `@pytest.mark.skipif()` or `pytest.skip()` for environment-dependent tests

**Farm isolation tests (`tests/test_farm_isolation.py`):**
The Deadline runner copies scripts from `python/comfyui/` to a flat `_job_data/` dir with `comfyui_` prefix (e.g., `utils.py` → `comfyui_utils.py`). These must import **without** the `comfyui` package on `sys.path`. The farm isolation test validates this by purging all `comfyui.*` from `sys.modules` and importing from a temp dir. If this test fails, a farm script has introduced a dependency on other comfyui modules that won't be available on the farm.

**Helper scripts** (root directory):
- `_run_tests.ps1` — Run full pytest suite with proper PYTHONPATH
- `_check_logs.ps1` — Stability test: 10 back-to-back app launches (10s each)
- `_find_logs.ps1` — Find latest log file path
- `_find_workflow.ps1` — Search for workflow files
- `_check_analytics.ps1` — Check analytics data

### Debugging

**Logging:** All output uses Python `logging` module (not `print()`). Every module should have:
```python
import logging
logger = logging.getLogger(__name__)
```
Use `logger.info()`, `logger.warning()`, `logger.error()`. Never use `print()` for new code.

**Log Files:** All logs are centralized on the network path from `network_output_path` global setting:
```
<network_path>/_logs/
├── users/    # Main app logs: luma_tools_<user>_<hostname>_<timestamp>.log
├── server/   # Persistent server logs: comfyui_server_<hostname>_<timestamp>.log
├── runner/   # Farm runner logs: comfyui_runner_<jobname>_<timestamp>.log
```
Currently: `W:/LumaRND/luma_tools/_logs/`. Falls back to `~/.luma_tools/logs/` if network unavailable.

**Reading logs (NO SCRIPT NEEDED):**
```bash
# Get latest log file path (use for Read tool)
powershell -Command "(Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName"

# Read last 100 lines directly
powershell -Command "Get-Content (Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 100"

# Search for errors across all logs
Grep pattern="ERROR|Exception|Traceback" path="W:\LumaRND\luma_tools\_logs\users\" output_mode="content"

# Read specific log with Read tool (use offset=-100 for last 100 lines)
Read tool on log path with offset=-100
```
**IMPORTANT:** PowerShell one-liners work fine for file operations. Only use `.ps1` script files when you need `$env:` variables (which get mangled by bash compatibility layer).

**Debug CLI Arguments:** The app supports debug flags that can be appended after the normal positional arguments:
```
--tab <name>       Select a tab on startup (passbuilder, mp4maker, republish, shotcleaner/cleaner, logs, comfyui, gallery, settings)
--auto-close <sec> Auto-close the app after N seconds (for automated testing)
```
Tab names come from `_TAB_ALIASES` dict in `core/luma_tools.py` (not all `restrict_key` values work — e.g., `canvas` has no alias).

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
powershell -Command "Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Get-Content $_.FullName }"
```

**Bug triage — pre-existing vs. introduced:**
When a bug appears during testing, **always determine if it's pre-existing before debugging:**
1. Check if the error's code path was touched by current changes (git diff)
2. If untouched, it's pre-existing — flag it to the user and move on rather than spending rounds fixing unrelated bugs
3. Only invest debugging time in bugs caused by the current changes

**Debugging workflow:**
1. Run the app with `--tab <target> --auto-close <seconds>` in background
2. Wait for it to close (or read logs while running)
3. Read the log file with `Read` tool or search with `Grep`

### UI Modifications
Edit `.ui` files in Qt Designer, update tab logic in `python/ui/tabs/`, styles in `resources/ui/la_shot_tools_styles.qss`.

**After editing any `.ui` file**, recompile its Python equivalent:
```bash
python/venv/Scripts/pyside6-uic.exe resources/ui/tabs/<name>.ui -o resources/ui/tabs/_compiled/ui_<name>.py -g python
```
If compiled files are missing, `BaseTab.load_ui()` falls back to `QUiLoader` (slower first startup due to ~5s initialization penalty). The deploy script recompiles automatically.

### Adding Features
1. Create service in domain package, add config to `core/config.py`
2. For tabs: inherit BaseTab, add entry to `TAB_REGISTRY` (`ui/tabs/__init__.py`), create `.ui` file and compile it
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

### Lambda Closure Bug
When creating lambdas in loops, capture variables by value:
```python
# ❌ Wrong: all lambdas share same 'i' reference
for i in range(5):
    button.clicked.connect(lambda: print(i))  # Always prints 4

# ✅ Correct: capture 'i' by value using default argument
for i in range(5):
    button.clicked.connect(lambda x=i: print(x))  # Prints 0, 1, 2, 3, 4
```

### Other Issues
- **Threading:** Use signals for cross-thread GUI updates (never direct Qt widget calls from workers)
- **Optional Deps:** Check `*_AVAILABLE` flags (AYON_AVAILABLE, DEADLINE_AVAILABLE, etc.) before using features
- **Paths:** Use `normalize_path()` from `core.utils` for AYON/Deadline compatibility; use `ensure_directory()` instead of `os.makedirs()`
- **ComfyUI Workflows:** 2 formats (UI/nodes vs API), use `is_api_format()` to detect
- **Imports:** Lazy import UI components inside functions (avoid module-level `from resources.ui...`)

## Pattern Guidelines

### Signal Naming Convention
When creating Qt signals, follow these conventions:
- **Completion events:** Use past tense - `job_completed`, `file_saved`, `scan_finished`
- **Request events:** Use "requested" suffix - `refresh_requested`, `navigate_requested`
- **State changes:** Use "changed" suffix - `settings_changed`, `selection_changed`
- **Format:** `{entity}_{action}` - e.g., `gallery_refresh_requested`, `job_progress`

### Error Handling Guide
Three patterns are available, use the appropriate one:
- **`@safe_operation(name, default)`** - Decorator for entire functions that may fail
- **`with handle_errors(name)`** - Context manager for specific code blocks
- **`log_error(op, error, var)`** - Manual logging after catch

```python
# Decorator for whole function
@safe_operation("load_settings", return_on_error={})
def load_settings():
    ...

# Context manager for blocks
def process():
    with handle_errors("parse_data"):
        data = parse(raw_data)
    with handle_errors("transform"):
        result = transform(data)
```

### Caching Guide
Use the caching utilities from `core/caching.py`:
- **`@cached_with_ttl(seconds)`** - Decorator for time-based cache invalidation
- **`ThreadSafeCache`** - Thread-safe dictionary cache for mutable shared state
- **`functools.lru_cache`** - For pure functions with immutable results

```python
from core.caching import cached_with_ttl, ThreadSafeCache

@cached_with_ttl(seconds=300)
def get_user_data(user_id):
    return db.fetch(user_id)

cache = ThreadSafeCache(max_size=100)
cache.set("key", value, ttl=60)
```

### Thread Safety
Always use `threading.RLock()` (not `Lock()`) for thread-safe access. RLock allows the same thread to acquire the lock multiple times without deadlock.
