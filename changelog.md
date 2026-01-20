# Luma Tools Changelog

## Version 0.4.5.1
- Added job persistence/recovery
- Luma tools should pick up running jobs if you close and open now.
- Fix ComfyUI Gallery flashing when new images appear
- UI Tweaks

## Version 0.4.5
- Improve batch image selector with visual pairing for multiple LoadImage nodes
- Add square grid layout for batch image thumbnails
- Color-coded borders to show which images will pair with which nodes
- Add drag-and-drop reordering of images in batch selector
- Display order numbers in corner of each thumbnail
- Show pairing statistics in count label (images per node)
- Support double-click to remove images from batch selection
- Remove toast notifications
- Fix ComfyUI Gallery flashing when new images appear - now uses incremental updates

## Version 0.4.4.1
- Better user feedback
- Fix preview nodes being bypassed and not saving images

## Version 0.4.4
- Add model loading detection in ComfyUI polling with improved status messages
- Implement horizontal layout for multiple image widgets in UI manager
- Add image_viewed signals to gallery viewers
- Update server defaults from global settings and improve encoding handling to handle all the emojis

## Version 0.4.3.7
- Add Low VRAM mode setting for ComfyUI (--lowvram flag)
- ComfyUI server now reads global settings automatically (lowvram, fast mode)

## Version 0.4.3.6
- Fix job-level progress percentage display in batch mode status bar
- Fix queue counting to only include luma_tools ComfyUI jobs (was showing all Deadline jobs)

## Version 0.4.3.5
- Fix mapping for some nodes

## Version 0.4.3.4
- Add real-time ComfyUI task progress tracking via Deadline logs
- Improve queue messaging to distinguish between own queued jobs vs other users' jobs
- Show job-level progress percentage in status bar during rendering

## Version 0.4.3.3
- Improve ComfyUI server crash detection and automatic restart

## Version 0.4.3.2
- Refactor backend for easier maintainability

## Version 0.4.3.1
- Hdri rendering improvements
- Viewer UI polish

## Version 0.4.3
- Add lighting modes (headlight, studio, HDRI)
- Add shading modes (shaded, textured, wireframe)
- Add light strength slider for intensity control
- Implement queue position display for Deadline jobs in ComfyUI polling
- Add admin level HDRI management
- Fix 3D viewer race condition when rapidly clicking next/prev
- Enhance viewer UI

## Version 0.4.2.2
- Fix double clicking an image making it close

## Version 0.4.2.1
- Remove pop up when new version just use settings notification badge
- Fix issue where rapid clicks would trigger multiple async viewer creations before the first one completed

## Version 0.4.2
- Add time estimates
- Improve settings persistence with atomic writes
- Remove unused camera controls in 3D viewer
- Update notification text fix
- Close viewer when switching users
- Dont send user message feature request  task is complete
- Better server crash detection

## Version 0.4.1.23
- Always append input filename to ComfyUI output files

## Version 0.4.1.22
- Feature request improvements

## Version 0.4.1.21
- Fix 3D viewer

## Version 0.4.1.20
- Move user requests to user folders

## Version 0.4.1.19
- Support input images from custom nodes

## Version 0.4.1.18
- Fix input file handling edge cases, always look in their hardcoded default input directory

## Version 0.4.1.17
- Implement feature request submission dialog with categories (Feature, Bug, Enhancement, Question)
- Fix worker import patterns to use lazy imports for thread safety
- Fix install script not considering venv

## Version 0.4.1.15
- Implement periodic version checking with timer (every 2 minutes)
- Add notifications for new deployed versions via status bar, system tray, and popup

## Version 0.4.1.14
- New window size and maximized state persistence
- New version notifications
- Use slider for generation count
- Update requirements.txt and remove unused libs

## Version 0.4.1.13
- New "Apply Settings" option in gallery
- Implement expand_subgraphs function to handle ComfyUI component/subgraph nodes
- Add file logging setup with rotation and global exception handling
- Enhance UI components with validity checks and new menu options (View Input, Publish to AYON)
- Update node configurations and workflow processing

## Version 0.4.1.10
- Refactor polling terminology from frames to jobs for clarity
- Hide add/edit model buttons from non-admin users
- Rename thumbnail renderer script and update references

## Version 0.4.1.9
- Introduce system tray icon with notifications for cross-platform alerts
- Fix worker garbage collection issues in polling, gallery, and other tabs
- Add network path polling fallback for reliable file watching
- Preserve editable node values when switching workflows in multi-workflow presets
- Update install script to support skipping version changes

## Version 0.4.1.8
- Add automatic crash recovery for ComfyUI persistent server
- Server now auto-restarts ComfyUI when it crashes (configurable via --max-crash-restarts, --crash-cooldown)
- Enhanced health monitor triggers restart when ComfyUI becomes unresponsive
- Crash counter resets after 5 minutes of stable uptime
- Status endpoint now reports crash count and recovery info

## Version 0.4.1.7
- Replace hardcoded node type checks with generic handling based on WIDGET_MAPPINGS and EXPORT_NODE_TYPES for better maintainability
- Add output_dir support for export nodes
- Improve polling and submission error handling to prevent garbage collection issues

## Version 0.4.1.6
- Added explicit sys.path manipulation to ensure the script directory is in Python's search path

## Version 0.4.1.5
- Rename upload_image_from_server to upload_image_to_server in runner.py
- Always copy scripts to output directory in service.py for reliability

## Version 0.4.1.4
- Comfy fixes

## Version 0.4.1.3
- added PYTHONIOENCODING=utf-8 to comfy launch
- Fix AYON publishing always creating version 1 - now auto-increments to next version

## Version 0.4.1.2
- Make Daddy Mark Happy
- Improve UI and flow in republish tab
- Convert source selector to dropdown button
- Make product name field read-only

## Version 0.4.1.1
- Add Publish to Current AYON Task toggle checkbox to rePublish tab that allows users to publish custom selected renders to their current AYON task instead of the path string

## Version 0.4.1
- Fix publishing from viewer
- Fix changelog generation

## Version 0.4
- New custom tree.js 3d viewport
- Improve 3D viewer prewarming to prevent window flashing and add configurable camera distance.
- Enhance image viewers with delete functionality.
- fix models not being offloaded when leaving model

## Version 0.39
- More import fixes

## Version 0.38
- Fix style imports

## Version 0.37
- Prevent initialization of restricted tabs entirely
- Enable republish tab in standalone mode with custom directory selection

## Version 0.36
- Switch AYON publish to real-time output streaming with progress detection
- Configure OpenGL surface format globally to prevent window flashing
- Pre-initialize 3D viewer in background for faster loading
- Update broken import paths

## Version 0.35
- Refactor republish tab to publish directly from work folder without copying files
- Add status spinner and animated updates during AYON publish process
- Update global settings with new user and node overrides
- Fix batch selector import and add last browse directory method

## Version 0.34
- Bugfixes

## Version 0.33
- More publishing fixes

## Version 0.32
- Fixing bundle name

## Version 0.31
- Ayon Fixes

## Version 0.3
- Migrate UI components from PySide2 to PySide6

## Version 0.28
- Add unified model loader supporting FBX, OBJ, USD, GLB, GLTF formats
- Implement lazy loading for gallery thumbnails with batched loading
- Add multi-workflow models with individual settings and editable nodes
- Improve metadata caching and batch loading for better performance
- Update UI components with tooltip lazy loading and placeholder caching
- Add server restart functionality for persistent ComfyUI mode
- Refactor GLB-specific modules to unified model handling
- Update dependencies and clean up cache files

## Version 0.26
- Introduce multi-workflow models allowing multiple workflows per preset with individual settings
- Add UI components for workflow selection and notes display in ComfyUI tab
- Implement metadata caching and batch loading for improved gallery performance
- Update workflow presets structure

## Version 0.25
- Implement lazy loading for gallery thumbnails to improve performance
- Updates to thumbnail rendering
- Add auto-extract textures option for 3D model exports
- Add server not found behavior settings for persistent mode
- Add regenerate thumbnails button in settings

## Version 0.24
- Add conditional node bypassing based on toggle values in workflows
- Refactor USD export to use subprocess for avoiding DLL conflicts

## Version 0.23
- Add support for exporting 3D models to ABC, OBJ, USD, and FBX formats from the gallery context menu. Include texture extraction functionality for 3D models
- Update metadata handling to use per-workflow subfolders
- Fix runner to avoid double prefixing filenames and adjust tab reordering logic

## Version 0.22
- Fix Changelog generation

## Version 0.21
- Fix installer

## Version 0.20
- Implement user selector for viewing other users' galleries in network mode with view-only restrictions
- Add job cancellation functionality for running ComfyUI submissions
- Pause/resume controls for log output
- Update installer
- Enhance thumbnail widgets with new item highlighting and editable permissions
- Auto-enable iterate mode when single image selected
- Background caching updates

## Version 0.14
- UI Updates

## Version 0.13
- Replace loading overlay with status bar progress
- Better batch job polling
- Add editable node overrides in Edit Model dialog

## Version 0.12
- Fix tab notifications not showing

## Version 0.11
- Installer Updates
- Fix texture toggle mode

## Version 0.1
- Change 3D viewer to PyVista
- Add full restart option to ComfyUI workflow presets
- Improve embedded viewer with async loading and support for videos
- Update settings tab UI to display version history and info
- Add Trellis 2 and Ultrashape Support
- Added version tracking and changelog system
