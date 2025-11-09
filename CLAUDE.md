# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Luma Tools is a VFX shot management application for the Luma Animation pipeline. It's a Windows-based PySide2 GUI application that handles:
- Render pass management and building
- AYON publishing (local and farm-based)
- Deadline farm job submission
- MP4 preview generation from EXR sequences
- Lookdev file cleanup

## Running the Application

**Launch Application:**
```bash
# From repository root (Windows)
luma_tools.bat

# The batch file activates the venv and launches the Python application
# It also hides the console window automatically
```

**Python Entry Point:**
```bash
# If running directly (ensure venv is activated)
python python/luma_tools.py
```

**Command Line Arguments:**
The application accepts command-line arguments for shot context, parsed by `state_manager.py`.

## Project Structure

### Core Modules (python/)

**Main Application:**
- `luma_tools.py` - Main window class (`LumaShotTools`), UI event handlers, and application entry point

**Service Layer (Strategy Pattern):**
- `ayon_service.py` - AYON/Deadline integration with publish strategies (`FarmPublishStrategy`, `LocalPublishStrategy`)
- `pass_builder.py` - Orchestrates pass building using OIIO and publishes to AYON
- `render_service.py` - Pass detection from EXR files using OpenImageIO
- `mp4_maker.py` - FFmpeg-based MP4 generation from EXR sequences
- `scan_service.py` - Directory scanning service with `DirectoryScanner` class
- `cleanup_service.py` - File cleanup operations for renders/USD/HIP files
- `file_operations.py` - File utilities (find renders, normalize paths, etc.)

**State & Configuration:**
- `state_manager.py` - Global application state (`app_state` singleton)
- `config.py` - All configuration constants, tool paths, and defaults
- `utils.py` - General utility functions (trailing numbers, string operations)

**UI Components (resources/ui/):**
- `ui_components.py` - UI enhancements, animations, inline spinners, status colors
- `splash_screen.py` - Animated loading splash screen
- `la_shottools_ui.ui` - Qt Designer UI file
- `la_shot_tools_styles.qss` - Custom Qt stylesheet

## Architecture Patterns

### Threading Model (Critical)
The application uses Qt's QThreadPool + QRunnable pattern for background operations:

**Worker Pattern (`ui_components.py`):**
- `Worker(QRunnable)` - Generic worker class that wraps functions for background execution
- `WorkerSignals` - Defines signals for thread communication: `started`, `finished`, `error`, `result`, `progress`
- All long-running operations execute via `QThreadPool.globalInstance().start(worker)`

**Thread Safety:**
- `ApplicationState` (state_manager.py) uses `threading.RLock()` for all property access
- All state reads/writes are protected by the reentrant lock
- Qt Signals automatically queue cross-thread communication to main GUI thread

**Usage Pattern:**
```python
worker = Worker(some_function, arg1, arg2)
worker.signals.result.connect(handle_result)
worker.signals.error.connect(handle_error)
worker.signals.progress.connect(update_progress)
QThreadPool.globalInstance().start(worker)
```

**IMPORTANT:** Never update Qt widgets directly from worker threads. Always use signals or `DirectoryScannerSignals` for cross-thread GUI updates.

### Strategy Pattern for Publishing
The codebase uses the Strategy Pattern in `ayon_service.py` to handle farm vs local publishing:
- `PublishStrategy` (ABC) - Base strategy interface
- `FarmPublishStrategy` - Submits AYON publish jobs to Deadline farm
- `LocalPublishStrategy` - Publishes directly to AYON locally

This eliminates code duplication and makes it easy to extend with new publishing methods.

### Service-Oriented Design
Each major feature is encapsulated in a dedicated service module:
- Services are stateless where possible
- Shared state managed through `state_manager.app_state` (thread-safe singleton)
- Main window delegates to services rather than implementing business logic

### UI Event Flow
1. User interacts with Qt widget
2. Signal connected to handler in `LumaShotTools` class
3. Handler creates Worker and submits to QThreadPool
4. Worker executes service function in background thread
5. Worker emits progress signals (safe cross-thread communication)
6. Main thread receives signals and updates UI (loading overlay, status messages)

## Key Workflows

### Pass Building (Pass Builder Tab)
1. Scan renders → `find_renders()` from `file_operations.py`
2. Select render → Detect passes using `detect_passes()` from `render_service.py`
3. Select passes → Build using `PassBuilder.build_passes()` from `pass_builder.py`
4. Building invokes OIIO (local) or submits to Deadline (farm)
5. Publish to AYON using appropriate strategy

### MP4 Generation (MP4 Maker Tab)
1. Scan renders from denoised/raw/custom paths
2. Select render sequence
3. Configure quality and burn-in options
4. Generate MP4 using `generate_mp4()` from `mp4_maker.py`
5. FFmpeg converts EXR sequence to MP4 with progress tracking

### Re-Publishing (rePublish Tab)
1. Scan existing renders (denoised/raw/custom)
2. Select render to republish
3. Configure task and product name
4. Publish to AYON (farm or local) using `ayon_service.py`

### Shot Cleanup (Shot Cleaner Tab)
1. Scanner finds renders, USD files, HIP backups in lookdev structure
2. Scan comp files (.nk) to identify renders in use
3. Select items to clean (auto-deselects renders in use)
4. Execute cleanup operations

## Important Configuration

### Tool Paths (config.py)
All external tool paths are centralized in `config.py`:
- `OIIO_PATH` - OpenImageIO oiiotool executable
- `FFMPEG_PATH` - FFmpeg executable
- `DEADLINE_PATH` - Deadline command executable
- `OIIO_INFO_PATH` - iinfo executable for metadata

**These paths are hardcoded to network locations (L:\ drive).** When working on a different environment, update these paths.

### AYON Settings
AYON integration settings in `config.py`:
- Colorspace: ACES - ACEScg
- Display/View: ACES/sRGB
- Default FPS: 25.0
- Product type: "render"

### Deadline Settings
Deadline job defaults in `config.py`:
- Pool: "luma"
- Group: "processing_group"
- Department: "compositing"
- Priorities: 25 (build), 50 (publish)

## External Dependencies

**Python Packages (in venv):**
- PySide2 - Qt GUI framework
- fileseq - Image sequence handling
- ayon-python-api - AYON API client
- ayon_core - AYON pipeline integration
- ayon_deadline - Deadline integration for AYON

**External Tools (not in repo):**
- OpenImageIO (oiiotool) - EXR manipulation and pass building
- FFmpeg - Video encoding
- Deadline - Farm rendering system
- AYON - Asset management and pipeline

## Development Practices

### Environment Setup
**Virtual Environment:**
- Python venv located at `python/venv/`
- Activated automatically by `luma_tools.bat`
- To activate manually (Windows): `python\venv\Scripts\activate.bat`

**No Build Process:**
- Application runs directly from source (no compilation needed)
- No linting/testing infrastructure currently in place

### Debugging
**Console Output:**
- Application hides console window by default (via Windows API)
- All `print()` statements redirect to Log tab in UI
- Check Log tab for debug output and error messages

**Debugging Workers:**
- Worker errors emit `error` signal with traceback
- Check console/log for `"Worker error:"` messages
- Use `print()` statements - they're redirected to UI log widget

**Qt Signal Debugging:**
- Signal connections are printed during startup
- Failed signal connections usually silent - check connection syntax

### Modifying UI
- UI layout defined in `resources/ui/la_shottools_ui.ui` (Qt Designer file)
- Styles in `resources/ui/la_shot_tools_styles.qss`
- UI animations and enhancements in `ui_components.py`
- Connect new signals in `LumaShotTools._connect_signals()`

### Adding New Features
1. Create service module in `python/` if needed
2. Add configuration to `config.py`
3. Add UI elements to `.ui` file (use Qt Designer)
4. Connect signals in `_connect_signals()`
5. Implement handler in `LumaShotTools` class
6. **For long operations:** Wrap in Worker and submit to QThreadPool
7. Use loading overlay: `animator.show_loading()`
8. Report progress via callbacks to update UI

**Thread Safety Checklist for New Features:**
- ✓ Access `app_state` properties (automatically thread-safe via RLock)
- ✓ Update GUI via signals from worker threads
- ✗ Never call Qt widget methods directly from worker threads
- ✗ Never access Qt widgets from service functions (pass callbacks instead)

### Working with AYON
- Import checks: `AYON_AVAILABLE` and `DEADLINE_AVAILABLE` flags
- Use `convert_to_ayon_folder_path()` to convert filesystem paths
- Metadata creation: `create_ayon_metadata()`
- Publishing strategies: Choose farm or local based on user selection

### Progress Reporting
Long operations should use progress callbacks:
```python
def operation_with_progress(progress_callback):
    if progress_callback:
        progress_callback(50, "Halfway done...")
```

Loading overlay supports:
- Main title and subtitle messages
- Progress bar (0-100)
- Shown via `animator.show_loading()`, updated via `animator.update_loading_message()` and `animator.update_loading_progress()`

## Windows-Specific Notes

- Application uses Windows API calls (`ctypes.windll`) to hide console window
- App ID set for Windows taskbar: `luma.tools.shotbuilder.001`
- Path separators: Code uses both forward slashes and backslashes (normalize with `normalize_path()`)
- Batch file launcher: `luma_tools.bat` activates venv before running

## Code Style Notes

- Recent refactor consolidated UI components into single module
- Module docstrings removed in recent refactor
- Services follow single-responsibility principle
- Strategy pattern used to eliminate code duplication
- Qt signals/slots for event handling
- Global `app_state` singleton manages shared state
- Print statements used for logging (redirected to UI log widget)

## Common Pitfalls and Important Notes

**Threading Errors:**
- Most common error: Calling Qt widget methods from worker threads
- Symptom: Crashes or "QObject: Cannot create children for a parent that is in a different thread"
- Solution: Use signals for all cross-thread GUI updates

**State Management:**
- `app_state` is thread-safe - access properties normally
- Never store state in service modules (they should be stateless)
- For UI-specific state, store in `LumaShotTools` instance variables

**Worker Progress Callbacks:**
- Workers auto-inject `progress_callback` if function signature includes it
- Don't manually pass `progress_callback` to Worker - it's handled automatically
- Progress callback receives: `(int: percentage, str: message)`

**AYON/Deadline Availability:**
- Check `AYON_AVAILABLE` and `DEADLINE_AVAILABLE` before using features
- These are False when imports fail (e.g., outside production environment)
- Gracefully degrade functionality when unavailable

**Path Handling:**
- Windows uses backslashes, but code uses both `/` and `\`
- Use `normalize_path()` from utils to standardize paths
- AYON paths use forward slashes - convert with `convert_to_ayon_folder_path()`

**DirectoryScanner Signals:**
- `DirectoryScannerSignals` provides thread-safe GUI updates during scans
- These signals are connected in `_connect_scanner_signals()`
- Add new signal types to `DirectoryScannerSignals` class if needed
