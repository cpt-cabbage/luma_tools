# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Luma Tools is a VFX shot management application for the Luma Animation pipeline. It's a Windows-based PySide2 GUI application that handles:
- Render pass management and building
- AYON publishing (local and farm-based)
- Deadline farm job submission
- MP4 preview generation from EXR sequences
- ComfyUI AI image generation workflows
- Lookdev file cleanup

## Running the Application

```bash
# From repository root (Windows)
luma_tools.bat

# Direct Python (ensure venv is activated)
python\venv\Scripts\activate.bat
python python/luma_tools.py
```

The batch file activates the venv and launches with `start /B` to run in background. The console window is hidden by the Python code itself using Windows API (`ctypes.windll`).

**Command Line Arguments:**
The application accepts 6 positional arguments for shot context: `jobname`, `shot`, `task`, `shotpath`, `user`, `output_subdirectory` (parsed by `state_manager.py`).

## Project Structure

### Core Modules (python/)

| Module | Purpose |
|--------|---------|
| `luma_tools.py` | Main window class (`LumaShotTools`), UI event handlers, entry point |
| `state_manager.py` | Thread-safe global state (`app_state` singleton with RLock) |
| `config.py` | Configuration with dynamic path resolution from environment variables |
| `settings_manager.py` | User settings (~/.luma_tools/) and global settings persistence |
| `utils.py` | Utilities: `get_trailing_number`, `remove_after`, `update_path_version`, `scan_exr_sequences`, `normalize_path` |

### Modular Tab System (python/tabs/)

Each tab is a self-contained module inheriting from `BaseTab`:

| Module | Purpose |
|--------|---------|
| `base_tab.py` | Abstract base class with `TabSignals` for cross-tab communication |
| `pass_builder_tab.py` | Render scanning and pass building |
| `mp4_maker_tab.py` | MP4 generation from EXR sequences |
| `republish_tab.py` | Re-publishing renders to AYON |
| `shot_cleaner_tab.py` | Cleanup for renders/USD/HIP files |
| `comfyui_tab.py` | ComfyUI workflow execution |
| `comfyui_gallery_tab.py` | Gallery view for ComfyUI outputs |
| `settings_tab.py` | User and global settings |
| `logs_tab.py` | Log output viewer |

Tab registration in `python/tabs/__init__.py` via `TAB_CONFIG` list.

### Service Layer

| Module | Purpose |
|--------|---------|
| `ayon_service.py` | AYON/Deadline integration with Strategy Pattern (`FarmPublishStrategy`, `LocalPublishStrategy`) |
| `pass_builder.py` | Pass building orchestration using OIIO |
| `render_service.py` | Pass detection from EXR files using OpenImageIO |
| `mp4_maker.py` | FFmpeg-based MP4 generation from EXR sequences |
| `scan_service.py` | Directory scanning with `DirectoryScanner` class |
| `cleanup_service.py` | File cleanup for renders/USD/HIP files |
| `file_operations.py` | File utilities (find renders, normalize paths) |
| `thumbnail_service.py` | EXR thumbnail generation with OIIO and caching |

### ComfyUI Integration

| Module | Purpose |
|--------|---------|
| `comfyui_service.py` | Workflow manipulation, editable node extraction, Deadline submission |
| `comfyui_runner.py` | Farm worker script that launches ComfyUI and executes workflows |
| `comfyui_client.py` | Lightweight client for server mode (persistent ComfyUI) |
| `comfyui_server.py` | Server management for persistent ComfyUI instances |

### UI Components (resources/ui/)

| File | Purpose |
|------|---------|
| `ui_components.py` | Worker class, animations, inline spinners, status colors, loading overlay |
| `splash_screen.py` | Animated loading splash screen |
| `icons.py` | `IconManager` for SVG icons, `TAB_COLORS` theme constants |
| `main_window.ui` | Qt Designer main window UI file |
| `tabs/*.ui` | Individual tab UI files (e.g., `pass_builder.ui`) |
| `la_shottools_ui.ui` | Legacy monolithic UI file (backup) |
| `la_shot_tools_styles.qss` | Custom Qt stylesheet |

### Additional Python Modules (python/)

| Module | Purpose |
|--------|---------|
| `spell_checker.py` | PyEnchant-based `SpellCheckTextEdit` widget, `is_spell_check_available()` |

## Architecture Patterns

### Modular Tab Architecture

Tabs follow a base class pattern defined in `python/tabs/base_tab.py`:

```python
class MyTab(BaseTab):
    @property
    def ui_file(self) -> str:
        return "my_tab.ui"  # Located in resources/ui/tabs/

    @property
    def tab_name(self) -> str:
        return "My Tab"

    def connect_signals(self):
        """Wire up UI signals after load."""
        self.ui.myButton.clicked.connect(self._on_button_clicked)

    def initialize(self):
        """Post-load setup."""
        pass
```

**Key BaseTab features:**
- `TabSignals` for cross-tab communication (`log_message`, `status_update`, `show_loading`, `hide_loading`)
- `load_ui()` loads from `resources/ui/tabs/{ui_file}`
- Lifecycle hooks: `on_tab_activated()`, `on_tab_deactivated()`
- Helper methods: `log()`, `set_status()`, `show_loading()`, `hide_loading()`, `get_widget()`

**Adding a new tab:**
1. Create `python/tabs/my_tab.py` inheriting from `BaseTab`
2. Create `resources/ui/tabs/my_tab.ui` in Qt Designer
3. Register in `python/tabs/__init__.py` by adding to `TAB_CONFIG`

### Threading Model (Critical)

Uses Qt's QThreadPool + QRunnable pattern:

```python
worker = Worker(some_function, arg1, arg2)
worker.signals.result.connect(handle_result)
worker.signals.error.connect(handle_error)
worker.signals.progress.connect(update_progress)
QThreadPool.globalInstance().start(worker)
```

**Thread Safety:**
- `ApplicationState` uses `threading.RLock()` for all property access
- Qt Signals automatically queue cross-thread communication
- **Never update Qt widgets directly from worker threads** - always use signals

**Worker Progress Callbacks:**
- Workers auto-inject `progress_callback` if function signature includes it
- Progress callback receives: `(int: percentage, str: message)`
- Use `report_progress(callback, progress, message)` utility for consistent progress reporting

**Additional Threading Utilities:**
- `ThreadedOperation` - Wrapper class for cleaner worker management
- `LogStream` - Custom QObject in `luma_tools.py` that redirects stdout/stderr to the Log tab via signals (all `print()` output appears in Log tab)

### Strategy Pattern for Publishing

`ayon_service.py` implements farm vs local publishing:
- `PublishStrategy` (ABC) - Base strategy interface
- `FarmPublishStrategy` - Submits to Deadline farm
- `LocalPublishStrategy` - Publishes directly

### Settings System

Two-tier settings managed by `settings_manager.py`:

**User Settings** (`~/.luma_tools/settings.json`):
- Default passes, ComfyUI text presets, tab order, last browse directories

**Global Settings** (shared network path):
- ComfyUI workflow presets, ComfyUI installation path/mode

## Configuration

### Dynamic Path Resolution (config.py)

Tool paths are resolved dynamically from environment variables:
- `AYON_LAUNCHER_LOCAL_DIR` - Base path for OIIO, FFmpeg
- `DEADLINE_PATH` - Deadline executable location
- `BUILTIN_OCIO_ROOT` - OCIO config path

```python
# Example: OIIO resolved from AYON directory
OIIO_ROOT = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "oiio_*", "bin", "oiiotool*")
OIIO_PATH = glob.glob(OIIO_ROOT)[0]
```

### Key Settings

| Setting | Value |
|---------|-------|
| Colorspace | ACES - ACEScg |
| Display/View | ACES/sRGB |
| Default FPS | 25.0 |
| Deadline Pool | luma |
| Deadline Group | processing_group |

## Key Workflows

### ComfyUI Workflow (New)

1. Select workflow preset from global settings
2. Workflow scanned for `_editable` suffix nodes (dynamic UI generated)
3. Select input images (batch processing supported)
4. Configure editable parameters (prompts, seeds, etc.)
5. Submit to Deadline - each frame is a different seed
6. `comfyui_runner.py` executes on farm workers

**Editable Nodes:** Nodes with titles ending in `_editable` become UI controls. Supported types: `LoadImage`, `TextEncodeQwenImageEditPlus`, `CLIPTextEncode`, `HYMotionEncodeText`, `KSampler`, `SaveImage`, `HYMotionExportFBX`. See `EDITABLE_NODE_CONFIGS` in `comfyui_service.py` for widget mappings.

### Pass Building

1. Scan renders via `find_renders()` from `file_operations.py`
2. Detect passes using `detect_passes()` from `render_service.py`
3. Build using `PassBuilder.build_passes()` (OIIO local or Deadline)
4. Publish to AYON using appropriate strategy

### MP4 Generation

1. Scan renders from denoised/raw/custom paths
2. Configure quality and burn-in options
3. Generate via `mp4_maker.py` using FFmpeg

## Development

No build process - runs directly from source. Venv location: `python/venv/`

### Debugging

- Console hidden by Windows API (`ctypes.windll`)
- All `print()` statements redirect to Log tab in UI
- Worker errors emit `error` signal with traceback
- Check for `"Worker error:"` messages in log

### Modifying UI

**For modular tabs (preferred):**
1. Edit `resources/ui/tabs/{tab_name}.ui` in Qt Designer
2. Update tab logic in `python/tabs/{tab_name}_tab.py`
3. Styles in `resources/ui/la_shot_tools_styles.qss`

**For main window:**
1. Edit `resources/ui/main_window.ui`
2. Connect signals in `LumaShotTools._connect_signals()`

### Adding New Features

1. Create service module in `python/` if needed
2. Add configuration to `config.py`
3. For new tab: Follow "Adding a new tab" steps in Architecture section
4. For long operations: Wrap in Worker, submit to QThreadPool
5. Use `show_loading()` for loading overlay

**Thread Safety Checklist:**
- Access `app_state` properties (thread-safe via RLock)
- Update GUI via signals from worker threads
- Never call Qt widget methods directly from workers
- Never access Qt widgets from service functions

### Working with AYON

```python
# Check availability before using features
if AYON_AVAILABLE:
    # Use AYON features
if DEADLINE_AVAILABLE:
    # Use Deadline features
```

Use `convert_to_ayon_folder_path()` for path conversion.

## Common Pitfalls

**Threading Errors:**
- Symptom: Crashes or "QObject: Cannot create children for a parent that is in a different thread"
- Solution: Use signals for all cross-thread GUI updates

**State Management:**
- `app_state` is thread-safe - access properties normally
- Services should be stateless

**AYON/Deadline Availability:**
- These flags are False when imports fail (outside production environment)
- Features gracefully degrade when unavailable

**Path Handling:**
- Windows uses backslashes, AYON uses forward slashes
- Use `normalize_path()` from utils to standardize

**ComfyUI Workflow Formats:**
- UI/nodes format has `nodes` array with `widgets_values`
- API format has node IDs as keys with `inputs` dict
- Use `is_api_format(workflow)` to detect format type
- `comfyui_service.py` converts between formats automatically
