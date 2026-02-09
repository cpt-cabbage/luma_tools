# Resources UI Module

Shared UI components and widgets used across all tabs. These are on `PYTHONPATH` and imported directly by name.

**CRITICAL:** Always lazy import these inside functions (not at module level) to avoid worker thread issues.

## Module Reference

### dialog_helpers.py — Message Dialogs
Use instead of raw QMessageBox:
- `confirm_action(title, message, parent, detail, default_yes)` → bool
- `show_warning(title, message, parent, detail)`
- `show_error(title, message, parent, detail)`
- `show_info(title, message, parent, detail)`

### file_dialogs.py — File Dialogs with Memory
Remembers last directory per context:
- `browse_file_with_memory()`, `browse_directory_with_memory()`, `save_file_with_memory()`, `browse_multiple_files_with_memory()`
- Context-specific: `browse_workflow_file()`, `browse_images()`, `save_mp4_file()`, `browse_comfyui_output_dir()`, `browse_hdri_file()`, `browse_custom_renders_dir()`

### option_button.py — Popup Menu Buttons
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

### ui_components.py — Core Components
`Worker` class for threading — the foundation of all async operations.

### media_viewers.py
Media viewing widgets (image, video, audio, 3D model) with zoom, pan, and comparison features.

### small_widgets.py
Small reusable widgets (labels, buttons, indicators).

### properties_dialog.py
Comprehensive properties dialog for gallery items (file info, metadata, workflow details, relationships).

### thumbnail_base.py
Base class for thumbnail widgets with disk/memory cache management.

### thumbnail_styles.py
`ThumbnailStyler` for consistent thumbnail appearance (borders, badges, colors).

### splash_screen.py
Application splash screen with async loading progress.

### spinners.py
Loading spinner widgets for async operations.

### effects.py
UI animation effects (pulse, glow, fade).

### styles.py
Global stylesheet and theme management.
