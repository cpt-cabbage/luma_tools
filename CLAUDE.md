# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Luma Tools is a VFX shot management application for the Luma Animation pipeline. It's a Windows-based PySide6 GUI application that handles:
- Render pass management and building
- AYON publishing (local and farm-based)
- Deadline farm job submission
- MP4 preview generation from EXR sequences
- ComfyUI AI image generation workflows
- Lookdev file cleanup

## Running the Application

```bash
# From repository root (Windows)
luma_tools.bat                  # With shot context args passed through
luma_tools_standalone.bat       # Without shot context (standalone mode)

# Direct Python (ensure venv is activated and PYTHONPATH is set)
python\venv\Scripts\activate.bat
set PYTHONPATH=%CD%\python;%CD%\resources\ui;%PYTHONPATH%
python python/core/luma_tools.py

# Deploy to production location
install.bat                     # Copies files to L:\tools\_studio_tools\luma_tools
```

The batch files activate the venv and launch with `start /B` to run in background. The console window is hidden by the Python code itself using Windows API (`ctypes.windll`).

**Single Instance Enforcement:**
The application uses a Windows named mutex (`Global\\LumaToolsSingleInstance`) to ensure only one instance runs at a time. If a second instance is launched, it finds and focuses the existing window instead of starting a new one.

**Command Line Arguments:**
The application accepts 6 positional arguments for shot context: `jobname`, `shot`, `task`, `shotpath`, `user`, `output_subdirectory` (parsed by `state_manager.py`).

## Deployment

The `install.bat` script handles deployment to production with automated version management:

```bash
install.bat  # Deploys to L:\tools\_studio_tools\luma_tools
```

**What it does:**
1. Prompts for version increment (big update: +0.1, small update: +0.01)
2. Auto-increments version in `version.json`
3. Optionally updates `changelog.md` from last git commit
4. Copies all files to production location
5. Updates paths in global_settings.json (dev → production)
6. Removes 'pause' from production launchers for silent execution

**Version tracking:** Version is stored in `version.json` and displayed in Settings tab. Changelog entries are auto-generated from git commit messages during deployment.

## Project Structure (Domain-Based Organization)

The codebase is organized into domain-specific packages for clarity and maintainability:

```
python/
├── core/                    # Core infrastructure
│   ├── luma_tools.py        # Main window, entry point
│   ├── config.py            # Configuration and path resolution
│   ├── state_manager.py     # Thread-safe global state
│   ├── settings_manager.py  # User/global settings with registry pattern
│   ├── utils.py             # General utilities
│   └── import_utils.py      # Safe import utilities
│
├── comfyui/                 # ComfyUI AI image generation
│   ├── service.py           # Main orchestration, Deadline submission
│   ├── workflow.py          # Load/save, format conversion
│   ├── editable.py          # Extract editable nodes
│   ├── modifier.py          # Modify workflow parameters
│   ├── node_configs.py      # Node type configurations
│   ├── utils.py             # Server communication utilities
│   ├── runner.py            # Farm worker script
│   ├── client.py            # Persistent server mode client
│   ├── server.py            # Server management
│   └── ayon_publisher.py    # AYON publishing integration
│
├── models/                  # 3D model handling
│   ├── loader.py            # Universal 3D loader (GLB, FBX, OBJ, USD)
│   ├── viewer.py            # 3D viewer with textures/skeletons/animation
│   ├── animation_utils.py   # Animation interpolation utilities
│   ├── thumbnail_service.py # Multi-format thumbnail generation
│   └── thumbnail_renderer.py # Subprocess thumbnail renderer
│
├── ayon/                    # AYON publishing integration
│   ├── service.py           # AYON/Deadline integration, Strategy Pattern
│   ├── publisher_integration.py # Standard AYON Publisher UI
│   └── validators/          # Validation plugins
│       ├── base.py
│       ├── validate_file_exists.py
│       ├── validate_file_format.py
│       └── validate_naming_convention.py
│
├── services/                # General service layer
│   ├── pass_builder.py      # Pass building orchestration (OIIO)
│   ├── render_service.py    # Pass detection from EXR
│   ├── mp4_maker.py         # FFmpeg-based MP4 generation
│   ├── scan_service.py      # Directory scanning
│   ├── cleanup_service.py   # File cleanup
│   ├── thumbnail_service.py # EXR thumbnail generation
│   ├── file_operations.py   # File utilities
│   └── deadline_utils.py    # Deadline job submission helper
│
├── tabs/                    # UI tabs (modular tab system)
│   ├── base_tab.py          # Abstract base class with TabSignals
│   ├── pass_builder_tab.py  # Render scanning and pass building
│   ├── mp4_maker_tab.py     # MP4 generation
│   ├── republish_tab.py     # Re-publishing renders
│   ├── shot_cleaner_tab.py  # Cleanup tool
│   ├── comfyui_tab.py       # ComfyUI workflow execution
│   ├── comfyui_gallery_tab.py # Gallery view for outputs
│   ├── comfyui_polling.py   # Polling mixin for ComfyUI
│   ├── settings_tab.py      # Settings UI
│   └── logs_tab.py          # Log output viewer
│
├── ui/                      # Shared UI components
│   ├── spell_checker.py     # PyEnchant spell checking widget
│   └── gallery_prewarm.py   # Pre-load gallery data
│
└── libs/                    # External binaries (Assimp DLL)
```

### Import Conventions

With the domain-based structure, imports follow these patterns:

```python
# Core modules
from core.config import OIIO_PATH, FFMPEG_PATH
from core.settings_manager import get_comfyui_path, save_user_settings
from core.state_manager import app_state
from core.utils import normalize_path
from core.import_utils import safe_import

# ComfyUI modules
from comfyui.service import submit_comfyui_to_deadline
from comfyui.workflow import load_workflow
from comfyui.node_configs import EDITABLE_NODE_CONFIGS

# Model modules
from models.loader import load_3d_model
from models.animation_utils import lerp, slerp, interpolate_bone_animation

# AYON modules
from ayon.service import create_ayon_metadata
from ayon.validators.base import BaseValidator

# Service modules
from services.pass_builder import PassBuilder
from services.render_service import detect_passes
from services.mp4_maker import generate_mp4
```

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
- `TabSignals` for cross-tab communication (`log_message`, `status_update`, `request_attention`)
- `load_ui()` loads from `resources/ui/tabs/{ui_file}`
- Lifecycle hooks: `on_tab_activated()`, `on_tab_deactivated()`
- Helper methods: `log()`, `set_status()`, `get_widget()`

**Adding a new tab:**
1. Create `python/tabs/my_tab.py` inheriting from `BaseTab`
2. Create `resources/ui/tabs/my_tab.ui` in Qt Designer
3. Import the tab class in `python/tabs/__init__.py`
4. Register in `TAB_CONFIG` with format: `{'class': MyTab, 'restrict_key': 'mytab'}`
   - The `restrict_key` is used for tab access control via global settings
   - Restricted tabs won't appear unless user has permission

### Threading Model (Critical)

Uses Qt's QThreadPool + QRunnable pattern. The `Worker` class is defined in `resources/ui/workers.py`:

```python
from resources.ui.workers import Worker
from PySide6.QtCore import QThreadPool

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

### Progress and Status Reporting (Critical)

**IMPORTANT:** All progress feedback must use the main window status bar ONLY. Never create separate QProgressDialog, loading overlays, or custom progress widgets.

**For Tabs (inheriting from BaseTab):**
```python
# Show status message on status bar
self.set_status("Processing files...")

# Log to console (appears in Log tab)
self.log("Operation completed")
```

### Settings System with Registry Pattern

Two-tier settings managed by `core/settings_manager.py` using a registry pattern:

**Settings Registry:**
```python
SETTINGS_REGISTRY = {
    "comfyui_path": SettingDef("comfyui_path", default=r"L:\...", scope="global"),
    "comfyui_mode": SettingDef("comfyui_mode", "embedded", "global", validator=...),
    # ... all settings defined once
}

# Generic getters/setters
value = get_setting("comfyui_path")
set_setting("comfyui_mode", "standalone")

# Backward-compatible aliases
get_comfyui_path = lambda: get_setting("comfyui_path")
```

**User Settings** (`~/.luma_tools/settings.json`):
- Default passes, ComfyUI text presets, tab order, last browse directories

**Global Settings** (shared network path):
- ComfyUI workflow presets, ComfyUI installation path/mode
- Tab restrictions (`restricted_tabs`) - controls which tabs are hidden from users
  - Maps restrict_key to permission flags via `TAB_RESTRICTION_MAP` in settings_manager.py
  - Restricted tabs are prevented from initializing entirely (including UI pre-loading) to avoid performance impact
  - When a tab is restricted, it's hidden unless the user has the corresponding permission

**Global Settings Location:**
- Development: `L:/tools/_studio_tools/AYON/_dev/christophe/la_shot_tools/luma_tools/global_settings/global_settings.json`
- Production: `L:/tools/_studio_tools/luma_tools/global_settings/global_settings.json`
- Paths are automatically updated during deployment by `install.bat`

### Strategy Pattern for Publishing

`ayon/service.py` implements farm vs local publishing:
- `PublishStrategy` (ABC) - Base strategy interface
- `FarmPublishStrategy` - Submits to Deadline farm
- `LocalPublishStrategy` - Publishes directly

## Configuration

### Dynamic Path Resolution (core/config.py)

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

### Environment Variables

The application uses these environment variables (set automatically by batch launchers):

| Variable | Purpose | Default |
|----------|---------|---------|
| AYON_LAUNCHER_LOCAL_DIR | AYON installation path for OIIO/FFmpeg | OS-specific (see config.py) |
| DEADLINE_PATH | Deadline installation path | `C:\Program Files\Thinkbox\Deadline10\bin` (Windows) |
| BUILTIN_OCIO_ROOT | OCIO config location | From AYON environment |
| AYON_DEFAULT_SETTINGS_VARIANT | AYON bundle name | `LUMA-PRODUCTION-Bundle-2025-12-08-02` |
| PYTHONPATH | Python module search path | Set by batch files to include `python/` and `resources/ui/` |

**Standalone Mode:** When AYON environment is unavailable, the app runs in standalone mode with limited functionality (no OIIO/FFmpeg-dependent features).

## Key Workflows

### ComfyUI Workflow

1. Select workflow preset from global settings
2. Workflow scanned for `_editable` suffix nodes (dynamic UI generated)
3. Select input images (batch processing supported)
4. Configure editable parameters (prompts, seeds, etc.)
5. Submit to Deadline - each frame is a different seed
6. `comfyui/runner.py` executes on farm workers

**Editable Nodes:** Nodes with titles ending in `_editable` become UI controls. Supported types: `LoadImage`, `TextEncodeQwenImageEditPlus`, `CLIPTextEncode`, `HYMotionEncodeText`, `KSampler`, `SaveImage`, `HYMotionExportFBX`, `Trellis2ExportMesh`, `UltraShapeSaveGLB`, `Load3D`. See `EDITABLE_NODE_CONFIGS` in `comfyui/node_configs.py` for widget mappings.

**Output Files:** ComfyUI can output images, 3D models (GLB/FBX/USD), video, audio, and other formats. See `COMFYUI_OUTPUT_EXTENSIONS` in `core/config.py` for the full list.

### Pass Building

1. Scan renders via `find_renders()` from `services/file_operations.py`
2. Detect passes using `detect_passes()` from `services/render_service.py`
3. Build using `PassBuilder.build_passes()` (OIIO local or Deadline)
4. Publish to AYON using appropriate strategy

### MP4 Generation

1. Scan renders from denoised/raw/custom paths
2. Configure quality and burn-in options
3. Generate via `services/mp4_maker.py` using FFmpeg

## Development

No build process - runs directly from source. Venv location: `python/venv/`

### Requirements

- Python 3.10+
- PySide6 (Qt6) - upgraded from PySide2 for NumPy 2.x compatibility and macOS support
- **Virtual environment is pre-configured** in `python/venv/`
- To reinstall dependencies: `python\venv\Scripts\activate.bat && pip install -r requirements.txt`

**Key dependencies:**
- PySide6 >= 6.6.0 (Qt6 GUI framework)
- open3d >= 0.18.0 (3D model loading with bundled Assimp)
- trimesh >= 4.10.1 (Fallback 3D loader)
- usd-core >= 25.11 (USD format support)
- PyOpenGL >= 3.1.0 (3D viewer rendering)
- numpy >= 1.26.4, scipy >= 1.15.3 (NumPy 2.x compatible)
- pyenchant >= 3.3.0 (Spell checking for text prompts)

### Testing

**Important:** This project currently has no test suite. When making changes:
- Test manually using both launcher modes (context and standalone)
- Verify tab functionality after modifying core components
- Test with and without AYON environment variables set
- Verify UI changes in Qt Designer preview and running application

### Running Python Scripts on Windows (Claude Code)

**IMPORTANT:** On Windows, the Bash tool runs in a compatibility layer that doesn't handle Windows paths well. Always use PowerShell to run Python scripts:

```bash
# CORRECT - Use PowerShell with full paths
powershell -Command "& 'l:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools\python\venv\Scripts\python.exe' 'l:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools\python\script.py'"

# CORRECT - PowerShell for simple commands
powershell -Command "Remove-Item -Force 'path\to\file'"
powershell -Command "Test-Path 'path\to\file'"
```

**File Operations:**
```bash
# Check if file exists
powershell -Command "Test-Path 'path\to\file'"

# Delete file
powershell -Command "Remove-Item -Force 'path\to\file'"

# List directory contents
powershell -Command "Get-ChildItem 'path\to\directory'"
```

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

1. Create service module in appropriate domain package (`services/`, `comfyui/`, `models/`, etc.)
2. Add configuration to `core/config.py`
3. For new tab: Follow "Adding a new tab" steps in Architecture section
4. For long operations: Wrap in Worker, submit to QThreadPool
5. Use `set_status()` to update status bar, `print()` for logging

**Thread Safety Checklist:**
- Access `app_state` properties (thread-safe via RLock)
- Update GUI via signals from worker threads
- Never call Qt widget methods directly from workers
- Never access Qt widgets from service functions

### AYON Publishing

**For single files (FBX, GLB, images):**
Use `create_ayon_metadata_single_file()` in `ayon/service.py` - handles single files without frame sequences.

**For EXR sequences:**
Use `create_ayon_metadata()` in `ayon/service.py` - handles frame sequences with proper file lists.

**Validators:**
Located in `python/ayon/validators/`:
- `ValidateFileExists` - Checks file presence
- `ValidateFileFormat` - Validates extension against product type
- `ValidateNamingConvention` - Validates product/variant names

Call `run_validators()` before publishing to catch errors early.

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

**Optional Dependencies Pattern:**
- Many modules use try/except around imports with `*_AVAILABLE` flags
- Examples: `AYON_AVAILABLE`, `DEADLINE_AVAILABLE`, `OPENGL_AVAILABLE`, `PYOPENGL_AVAILABLE`
- Always check these flags before using optional features
- Features gracefully degrade when dependencies are unavailable

**Path Handling:**
- Windows uses backslashes, AYON uses forward slashes
- Use `normalize_path()` from `core.utils` to standardize

**ComfyUI Workflow Formats:**
- UI/nodes format has `nodes` array with `widgets_values`
- API format has node IDs as keys with `inputs` dict
- Use `is_api_format(workflow)` to detect format type
- `comfyui/service.py` converts between formats automatically

## UI Components Organization

The `resources/ui/` directory contains modularized UI components (recently refactored from monolithic `ui_components.py`):

- **workers.py** - Threading utilities (`Worker`, `WorkerSignals`)
- **styles.py** - Styling constants and themes
- **spinners.py** - Loading animations and progress indicators
- **effects.py** - Visual effects and animations
- **notifications.py** - Toast notifications and status banners
- **layouts.py** - Custom layout implementations
- **dialogs.py** - Edit dialogs and forms
- **batch_selector.py** - Image selection widgets
- **small_widgets.py** - Miscellaneous UI components (`show_popup_menu()`, `browse_directory()`, `browse_file()`)
- **image_viewers.py** - Image and model viewing widgets

## Utility Functions

**Shared UI Utilities (`resources/ui/small_widgets.py`):**
- `show_popup_menu()` - Display popup menu below button with optional submenus
- `browse_directory()` - Directory browser with last-used memory
- `browse_file()` - File browser with last-used memory

**Safe Imports (`core/import_utils.py`):**
```python
from core.import_utils import safe_import, safe_import_multiple

# Single import
Usd, USD_AVAILABLE = safe_import("pxr", "Usd")

# Multiple imports
(Usd, Sdf, UsdGeom), USD_AVAILABLE = safe_import_multiple("pxr", "Usd", "Sdf", "UsdGeom")
```

**Animation Utilities (`models/animation_utils.py`):**
- `lerp()` - Linear interpolation
- `slerp()` - Spherical linear interpolation (quaternions)
- `quaternion_to_matrix()` - Convert quaternion to 4x4 matrix
- `compose_transform()` - Build transform from position/rotation/scale
- `interpolate_bone_animation()` - Sample bone animation at time
