# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Luma Tools is a VFX shot management PySide6 GUI application for the Luma Animation pipeline handling render passes, AYON publishing, Deadline farm jobs, MP4 previews, ComfyUI AI workflows, and lookdev cleanup.

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

**Single Instance:** Uses Windows mutex `Global\\LumaToolsSingleInstance` to prevent multiple instances. Console hidden via `ctypes.windll`.

## Deployment

`install.bat` auto-increments version, updates changelog, copies code/venv to production, updates global_settings.json paths (dev→prod), and removes 'pause' from launchers. Version stored in `version.json`.

## Key Features

- **Version Checking:** Every 2 minutes, compares local vs production `version.json`, notifies via status bar/system tray (`_check_deployed_version()`, `_setup_system_tray()` in `core/luma_tools.py`)
- **File Logging:** All output → `~/.luma_tools/logs/` (last 5 files kept, UTF-8, global exception handler via `TeeStream`)
- **Window State Persistence:** Size, position, maximized state, tab order saved in `~/.luma_tools/settings.json` (`core/user_preferences`)

## Project Structure (Domain-Based)

```
python/
├── core/         # luma_tools.py (main), config.py, state_manager.py, settings_manager.py, user_preferences.py, feature_requests.py
├── comfyui/      # service.py, workflow.py, node_configs.py, presets_manager.py, runner.py, server.py, ayon_publisher.py
├── models/       # loader.py (GLB/FBX/OBJ/USD), viewer.py, animation_utils.py, thumbnail_service.py
├── ayon/         # service.py (Strategy Pattern), publisher_integration.py, validators/ (base, file_exists, format, naming)
├── services/     # pass_builder.py, render_service.py, mp4_maker.py, file_operations.py, deadline_utils.py
├── tabs/         # base_tab.py, *_tab.py, comfyui_*_manager.py (helpers), comfyui_polling.py (mixin)
├── ui/           # spell_checker.py, gallery_prewarm.py
└── resources/ui/ # workers.py, styles.py, image_viewers.py, small_widgets.py, dialogs.py, etc.
```

### Import Patterns

```python
from core.config import OIIO_PATH, FFMPEG_PATH
from core.state_manager import app_state
from core.settings_manager import get_setting, set_setting  # Prefer generic get/set
from core.user_preferences import get_window_state, save_window_state
from comfyui.service import submit_comfyui_to_deadline
from models.loader import load_3d_model
from ayon.service import create_ayon_metadata
from services.pass_builder import PassBuilder

# UI components - MUST lazy import (inside functions) to avoid worker thread issues
from ui_components import Worker  # resources/ui/ in PYTHONPATH
```

## Architecture Patterns

### Tabs (BaseTab)
Inherit from `tabs/base_tab.py`, define `ui_file`, `tab_name`, implement `connect_signals()`, `initialize()`. Register in `TAB_CONFIG` with `restrict_key` for access control. BaseTab provides `TabSignals` (log_message, status_update), lifecycle hooks, and helpers (`log()`, `set_status()`).

**Helper Classes:** Complex tabs extract helpers (e.g., ComfyUIWidgetManager, ComfyUIStateManager, GalleryLoader, GalleryManager) to separate UI generation, state, and I/O concerns.

### Threading (CRITICAL)

**Worker Pattern:**
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
- Workers auto-inject `progress_callback(int, str)` if in function signature
- Use `self.set_status("msg")` for status bar, `self.log("msg")` for logs (never QProgressDialog)

### Settings

4 modules: `core/settings_manager` (registry, get/set), `core/user_preferences` (window state, tab order), `core/feature_requests`, `comfyui/presets_manager`. Use `get_setting(key)` / `set_setting(key, val)`.

- **User:** `~/.luma_tools/settings.json` (window, tabs, last dirs)
- **Global:** `L:/tools/_studio_tools/luma_tools/global_settings/global_settings.json` (presets, restricted_tabs via TAB_RESTRICTION_MAP)

### Strategy Pattern
`ayon/service.py`: `PublishStrategy` (ABC) → `FarmPublishStrategy`, `LocalPublishStrategy`

### Mixin Pattern
`PollingMixin` (`tabs/comfyui_polling.py`): Add to tabs via inheritance, call `_init_polling_state()` in `initialize()`, then `_start_iterate_polling()` or `_start_batch_polling(job_ids)`

## Naming Conventions

- **Modules/Packages:** `snake_case` (settings_manager.py, core/)
- **Classes:** `PascalCase`, prefix `Base*`, suffix `*Mixin`/`*Manager`/`*Service`
- **Functions/Methods:** `snake_case()`, private `_method()`, handlers `_on_event()`, booleans `is_*/has_*/can_*()`
- **Variables:** `snake_case`, constants `UPPER_SNAKE`, private `_attr`, booleans `is_/has_/can_`
- **UI Files:** `camelCase` in .ui (submitButton), `snake_case` signals (log_message)

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
3. **Editable Nodes:** See `EDITABLE_NODE_CONFIGS` in `comfyui/node_configs.py`
4. **Subgraph Expansion:** `expand_subgraphs()` expands UUID component nodes into concrete nodes
5. **Export Nodes:** Add to `EXPORT_NODE_TYPES` dict (maps node type → filename param), add to `WIDGET_MAPPINGS`

### Pass Building
`find_renders()` → `detect_passes()` → `PassBuilder.build_passes()` (OIIO/Deadline) → AYON publish

### MP4 Generation
Scan renders → configure quality/burn-in → `services/mp4_maker.py` (FFmpeg)

## Development

**Setup:** Python 3.10+, PySide6, pre-configured venv in `python/venv/`. No build process.
**Key deps:** PySide6 ≥6.6, open3d ≥0.18, trimesh ≥4.10, usd-core ≥25.11, PyOpenGL ≥3.1, pyenchant ≥3.3
**Testing:** No test suite - manual testing required (both launcher modes, with/without AYON env)

### Windows PowerShell (for Claude Code)
Always use PowerShell for Python scripts and file operations (Bash compatibility layer has path issues):
```bash
powershell -Command "& 'python\venv\Scripts\python.exe' 'script.py'"
powershell -Command "Test-Path 'path'"
powershell -Command "Remove-Item -Force 'path'"
```

### Debugging
Logs: `~/.luma_tools/logs/` (last 5 kept, UTF-8, global exception handler). Check worker GC if callbacks don't fire.

### UI Modifications
Edit `.ui` files in Qt Designer, update tab logic in `python/tabs/`, styles in `resources/ui/la_shot_tools_styles.qss`.

### Adding Features
1. Create service in domain package, add config to `core/config.py`
2. For tabs: inherit BaseTab, register in TAB_CONFIG
3. Long ops: wrap in Worker (store on self), use signals
4. Use `set_status()` for status bar, `print()` for logs

### AYON Publishing
- Single files: `create_ayon_metadata_single_file()` in `ayon/service.py`
- EXR sequences: `create_ayon_metadata()`
- Validators: `ValidateFileExists`, `ValidateFileFormat`, `ValidateNamingConvention` (call `run_validators()` first)
- Check `AYON_AVAILABLE`, `DEADLINE_AVAILABLE` before using features
- Use `convert_to_ayon_folder_path()` for paths

## Performance

- **Prewarm 3D Viewer:** Pre-initialize Three.js viewer during splash screen (`set_prewarm_viewer()`, `get_prewarm_viewer()`) to eliminate ~1-2s delay
- **Qt Config:** 2GB image limit (`QT_IMAGEIO_MAXALLOC=2048`), global OpenGL surface format, in-process GPU for WebEngine
- **Restricted Tabs:** Don't initialize (no UI load, no resources) when user lacks permission (`restricted_tabs` in global settings)

## Common Pitfalls

### Worker GC (CRITICAL)
**Must store worker on `self`** or GC deletes before completion:
```python
# ❌ worker = Worker(func); QThreadPool.start(worker)  # Gets GC'd
# ✅ self._worker = Worker(func); QThreadPool.start(self._worker)
```

### Other Issues
- **Threading:** Use signals for cross-thread GUI updates (never direct Qt widget calls from workers)
- **State:** `app_state` is thread-safe, services are stateless
- **Optional Deps:** Check `*_AVAILABLE` flags (AYON_AVAILABLE, DEADLINE_AVAILABLE, etc.) before using features
- **Paths:** Use `normalize_path()` from `core.utils` (Windows backslash vs AYON forward slash)
- **ComfyUI Workflows:** 2 formats (UI/nodes vs API), use `is_api_format()` to detect, `comfyui/service.py` converts
- **Imports:** Lazy import UI components inside functions (avoid module-level `from resources.ui...`)
- **Subgraph Widgets:** If editable widgets missing, add explicit mappings to `WIDGET_MAPPINGS` in `EDITABLE_NODE_CONFIGS`

## Utilities

**resources/ui/:** workers.py, styles.py, spinners.py, dialogs.py, batch_selector.py, small_widgets.py (show_popup_menu, browse_directory, browse_file), image_viewers.py

**core/import_utils.py:** `safe_import()`, `safe_import_multiple()` - graceful optional imports with `*_AVAILABLE` flags

**models/animation_utils.py:** lerp, slerp, quaternion_to_matrix, compose_transform, interpolate_bone_animation
