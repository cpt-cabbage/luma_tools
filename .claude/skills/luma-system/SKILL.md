---
name: luma-system
description: Holistic understanding of luma_tools architecture, data flows, and system interactions. Auto-loads when working on any luma_tools code.
user-invocable: false
---

# Luma Tools System Architecture

## Core Principle
Understand the WHOLE system - how managers coordinate, data flows through pipelines, events propagate across tabs, and metadata connects everything.

## System Layers

### 1. Core Layer (python/core/)
- `config.py` - Constants, paths, UIColors, UIStyles
- `state_manager.py` - Thread-safe global state via `app_state` singleton
- `settings_manager.py` - User/global settings with registry pattern
- `error_handling.py` - `@safe_operation`, `handle_errors`, `log_error`
- `logging_utils.py` - Network logging, TeeStream, file setup
- `event_bus.py` - Cross-tab Qt signals for decoupled communication

### 2. Service Layer (python/services/, python/comfyui/, python/deadline/, python/geo/)
- Services do work, tabs orchestrate UI
- ComfyUI: workflow.py → editable.py → modifier.py → runner.py
- Deadline: submitter.py → poller.py → parser.py
- Pass Builder: services/pass_builder.py (OIIO operations)
- MP4 Maker: services/mp4_maker.py (FFmpeg operations)
- 3D Model: geo/loaders/ (Strategy Pattern)
- AYON: ayon/service.py (publishing)
- Gallery metadata: comfyui/metadata.py

### 3. UI Layer (python/ui/tabs/, resources/ui/)
- Tabs inherit BaseTab, use managers for decomposed functionality
- Gallery has 10+ managers in ui/tabs/gallery/
- Workers for threading, signals for cross-thread updates

## Data Flow Patterns

### Settings Flow
```
User action → set_setting(key, val) → SETTINGS_REGISTRY lookup →
scope determines file (user: ~/.luma_tools/, global: network path) →
cache invalidation → next get_setting() reads fresh
```

### Event Bus Flow
```
Tab A action → pipeline_events.signal.emit(data) →
Qt signal system → all connected handlers fire →
Tab B/C/D receive and react independently
```

### Gallery Refresh Flow
```
File system change → RefreshController detects →
scan_directory() → parse metadata →
GalleryManager.display_items(incremental=True) →
only new items added to UI (no flash)
```

### ComfyUI Job Flow
```
User configures → submit_comfyui_to_deadline() →
Deadline job created → PollingMixin polls status →
runner.py executes on farm → outputs written →
metadata stored → gallery refresh detects → displayed
```

## Critical Edge Cases

### Empty/Null Handling
- No selection: Check `if not selected_items` before operations
- No files in directory: Show empty state, don't error
- No metadata: Graceful fallback, items still display (grey vs blue)

### Network Path Failures
- `comfyui_network_output_path` unavailable: Fall back to `~/.luma_tools/`
- Settings network path down: Use cached values, warn user
- Gallery path inaccessible: Show error state, allow retry

### Concurrent Operations
- Multiple workers: Each stored on self with unique name (`self._worker_1`, `self._worker_2`)
- Rapid user clicks: Debounce or cancel previous operation
- File watching + polling: RefreshController handles both, deduplicates

## Manager Coordination Pattern

Managers in gallery follow this pattern:
1. Each manager owns ONE responsibility
2. Managers communicate via signals, NOT direct calls
3. GalleryManager orchestrates, doesn't implement details
4. base_manager.py provides common helpers (start_worker, show_status)

## Before ANY Code Change

1. Read the target file
2. Read its imports to understand dependencies
3. Read relevant CLAUDE.md section for patterns
4. For gallery: also read gallery_manager.py + affected managers
5. For ComfyUI: read files relevant to the specific change

## When Suggesting Features

Always consider:
1. Which managers need updating (gallery has 10+)
2. What event bus signals are needed for cross-tab communication
3. What settings should be added for user preferences
4. What metadata implications exist (storage, lineage, display)

## Changelog Entry Format

Match exactly:
- `- Add X` = wholly new feature
- `- Fix X` = bug resolution
- `- Update X` = enhancement to existing
- `- Refactor X` = code restructure, no behavior change
- `- Remove X` = deleted functionality

Commits should match what would go in changelog.md.

## Subsystem Reference

### 3D Model Loading (python/geo/)
Uses Strategy Pattern via loaders/factory.py:
- Tries loaders by format priority: USD → Trimesh → Assimp → Open3D → SMPL
- Each loader implements `BaseModelLoader` ABC
- Animation support via `animation_controller.py`, `animation_utils.py`

### Pass Builder Pipeline (python/services/pass_builder.py)
```
find_renders() → detect_passes() → PassBuilder.build_passes() →
OIIO combines channels → Deadline job → AYON publish
```

### MP4 Maker (python/services/mp4_maker.py)
```
scan renders → configure quality/burn-in → FFmpeg encoding →
optional: add to gallery via copy_mp4_to_gallery()
```

### AYON Publishing (python/ayon/service.py)
- Single files: `create_ayon_metadata_single_file()`
- EXR sequences: `create_ayon_metadata()`
- Check `AYON_AVAILABLE` flag before use

### Deadline Integration (python/deadline/)
- `submitter.py` - Job submission functions
- `poller.py` - Status polling and queue info
- `parser.py` - Output parsing utilities
- `utils.py` - Command execution helpers

### Logging System
Centralized logs at `comfyui_network_output_path/_logs/`:
- `users/` - Main app logs
- `server/` - ComfyUI server logs
- `runner/` - Farm runner logs
Falls back to `~/.luma_tools/logs/` if network unavailable.

### New Utilities Available
In `core/utils.py`:
- `validate_directory_for_operation(path, operation)` - Check with logging
- `validate_file_for_operation(path, operation)` - Check with logging
- `safe_list_dir(path, pattern)` - List with error handling
- `plural(count, singular, plural_form)` - Format "N items"
- `nested_get(d, keys, default)` - Safe nested dict access
- `nested_set(d, keys, value)` - Safe nested dict update

In `core/config.py`:
- `get_network_output_path()` - ComfyUI network path accessor
- `is_mp4_add_to_gallery_enabled()` - MP4 gallery setting
- `get_completion_sound()` - Completion sound setting
