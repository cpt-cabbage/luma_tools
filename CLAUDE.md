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

**Single Instance:** Uses Windows mutex `Global\\LumaToolsSingleInstance` to prevent multiple instances.

## Deployment

`install.bat` auto-increments version, updates changelog, copies code/venv to production, updates global_settings.json paths (dev→prod). Version stored in `version.json`.

## Project Structure

```
python/
├── core/         # luma_tools.py (main), config.py, state_manager.py, settings_manager.py, user_preferences.py
├── comfyui/      # service.py, workflow.py, node_configs.py, presets_manager.py, runner.py, server.py
│                 # deadline_submitter.py, deadline_poller.py, metadata.py, ayon_publisher.py
├── models/       # viewer.py, animation_controller.py, animation_utils.py, thumbnail_service.py
│   └── loaders/  # base.py, factory.py, open3d_loader.py, trimesh_loader.py, assimp_loader.py, usd_loader.py, smpl_loader.py
├── ayon/         # service.py (Strategy Pattern), publisher_integration.py, validators/
├── services/     # pass_builder.py, render_service.py, mp4_maker.py, file_operations.py, deadline_utils.py
├── tabs/         # base_tab.py, *_tab.py, comfyui_*_manager.py, comfyui_polling.py (mixin)
│   ├── gallery/  # selection_manager.py, viewer_manager.py, operations_manager.py, refresh_controller.py, ui_manager.py
│   └── dialogs/  # feature_request_dialog.py
├── ui/           # spell_checker.py, gallery_prewarm.py
resources/ui/     # workers.py, styles.py, image_viewers.py, small_widgets.py, dialogs.py, file_dialogs.py
tests/            # test_loaders.py, test_animation_controller.py, test_config.py, test_file_dialogs.py
```

### Import Patterns

```python
from core.config import OIIO_PATH, FFMPEG_PATH, UIColors, UIStyles
from core.state_manager import app_state
from core.settings_manager import get_setting, set_setting
from comfyui.service import submit_comfyui_to_deadline
from models.loaders.factory import load_model
from ayon.service import create_ayon_metadata
from services.pass_builder import PassBuilder

# File dialogs with memory (remembers last directory per context)
from file_dialogs import browse_file_with_memory, browse_directory_with_memory

# UI components - MUST lazy import (inside functions) to avoid worker thread issues
from ui_components import Worker  # resources/ui/ in PYTHONPATH
```

## Architecture Patterns

### Tabs (BaseTab)
Inherit from `tabs/base_tab.py`, define `ui_file`, `tab_name`, implement `connect_signals()`, `initialize()`. Register in `TAB_CONFIG` (`tabs/__init__.py`) with `restrict_key` for access control.

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

### Settings

- **User:** `~/.luma_tools/settings.json` (window state, tab order, last dirs)
- **Global:** `L:/tools/_studio_tools/luma_tools/global_settings/global_settings.json` (presets, restricted_tabs)

Use `get_setting(key)` / `set_setting(key, val)` from `core.settings_manager`.

### 3D Model Loaders (Strategy Pattern)
`models/loaders/factory.py`: `load_model()` tries loaders by format priority (USD→Trimesh→Assimp→Open3D→SMPL). Each loader in `models/loaders/` implements `BaseModelLoader` ABC.

### Gallery Managers
`tabs/gallery/` decomposes gallery functionality: `selection_manager.py` (multi-select), `viewer_manager.py` (viewer lifecycle), `operations_manager.py` (batch ops), `refresh_controller.py` (file watching), `ui_manager.py` (sort/filter/view mode).

**Incremental Updates:** Gallery uses incremental display to avoid flashing when new items arrive. `display_items(items, view_mode, incremental=True)` adds only new items without clearing existing widgets. Stacked view uses `_update_stacked_items_incrementally()`.

**Item Metadata:** Gallery items have `has_metadata` field indicating if ComfyUI metadata was found (for styling), `is_input` for source images, and `job_prefix` for grouping.

### Mixin Pattern
`PollingMixin` (`tabs/comfyui_polling.py`): Add via inheritance, call `_init_polling_state()` in `initialize()`, then `_start_iterate_polling()` or `_start_batch_polling(job_ids)`.

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
6. **Metadata:** `comfyui/metadata.py` stores/loads job metadata (job_prefix, is_output, source_images) in `_gallery_metadata.json` per directory

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
python tests/test_loaders.py         # Run individual test
```
Manual testing required (both launcher modes, with/without AYON env)

### Windows PowerShell (for Claude Code)
Always use PowerShell for Python scripts (Bash compatibility layer has path issues):
```bash
# Syntax check
powershell -Command "Set-Location 'l:\path\to\luma_tools'; python\venv\Scripts\python.exe -m py_compile python\tabs\file.py"

# Run tests
powershell -Command "Set-Location 'l:\path\to\luma_tools'; python\venv\Scripts\python.exe -m pytest tests/"
```

### Debugging
**IMPORTANT: Always check the log files when debugging issues.** Logs are at `~/.luma_tools/logs/` (last 5 kept, UTF-8). On Windows: `C:\Users\<username>\.luma_tools\logs\`. Read the most recent log file using the Read tool - don't ask the user to copy/paste logs. Use Grep to search for errors: `Grep pattern="ERROR|Exception|Traceback" path="C:\Users\<username>\.luma_tools\logs\"`. Check worker GC if callbacks don't fire.

### UI Modifications
Edit `.ui` files in Qt Designer, update tab logic in `python/tabs/`, styles in `resources/ui/la_shot_tools_styles.qss`.

### Adding Features
1. Create service in domain package, add config to `core/config.py`
2. For tabs: inherit BaseTab, register in TAB_CONFIG
3. Long ops: wrap in Worker (store on self), use signals

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
- **Paths:** Use `normalize_path()` from `core.utils` (Windows backslash vs AYON forward slash)
- **ComfyUI Workflows:** 2 formats (UI/nodes vs API), use `is_api_format()` to detect
- **Imports:** Lazy import UI components inside functions (avoid module-level `from resources.ui...`)

## Utilities

**core/config.py:** `UIColors` (background, text, accent, status colors), `UIStyles` (reusable stylesheet snippets)

**core/import_utils.py:** `safe_import()`, `safe_import_multiple()` - graceful optional imports with `*_AVAILABLE` flags

**resources/ui/file_dialogs.py:** `browse_file_with_memory()`, `browse_directory_with_memory()`, `save_file_with_memory()` - remembers last dir per context

**models/animation_controller.py:** `AnimationController` (playback state, timing), `AnimationTransportBar` (play/pause/loop UI)
