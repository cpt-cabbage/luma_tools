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

### Strategy Pattern for Publishing
The codebase uses the Strategy Pattern in `ayon_service.py` to handle farm vs local publishing:
- `PublishStrategy` (ABC) - Base strategy interface
- `FarmPublishStrategy` - Submits AYON publish jobs to Deadline farm
- `LocalPublishStrategy` - Publishes directly to AYON locally

This eliminates code duplication and makes it easy to extend with new publishing methods.

### Service-Oriented Design
Each major feature is encapsulated in a dedicated service module:
- Services are stateless where possible
- Shared state managed through `state_manager.app_state`
- Main window delegates to services rather than implementing business logic

### UI Event Flow
1. User interacts with Qt widget
2. Signal connected to handler in `LumaShotTools` class
3. Handler updates UI state and calls service functions
4. Services report progress via callbacks
5. Callbacks update loading overlay or status messages

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

### Modifying UI
- UI layout defined in `resources/ui/la_shottools_ui.ui` (Qt Designer file)
- Styles in `resources/ui/la_shot_tools_styles.qss`
- UI animations and enhancements in `ui_components.py`
- Connect new signals in `LumaShotTools._connect_signals()`

### Adding New Features
1. Create service module in `python/` if needed
2. Add configuration to `config.py`
3. Add UI elements to `.ui` file
4. Connect signals in `_connect_signals()`
5. Implement handler in `LumaShotTools` class
6. Use loading overlay for long operations: `animator.show_loading()`
7. Report progress via callbacks to update UI

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
