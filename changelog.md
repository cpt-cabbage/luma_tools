# Luma Tools Changelog

## Version 0.4.1.5
- Rename upload_image_from_server to upload_image_to_server in runner.py
- Always copy scripts to output directory in service.py for reliability

## Version 0.4.1.4
- Comfy fixes

## Version 0.4.1.3
- added PYTHONIOENCODING=utf-8 to comfy launch
- Fix AYON publishing always creating version 1 - now auto-increments to next version

## Version 0.4.1.2
- Make Daddy Mark Happy.
- Improve UI and flow in republish tab
- Convert source selector to dropdown button
- Make product name field read-only

## Version 0.4.1.1
- Add Publish to Current AYON Task toggle checkbox to rePublish tab that allows users to publish custom selected renders to their current AYON task instead of the path string.

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
- Updates to thumbnaill rendering 
- Add auto-extract textures option for 3D model exports 
- Add server not found behavior settings for persistent mode 
- Add regenerate thumbnails button in settings

## Version 0.24
- Add conditional node bypassing based on toggle values in workflows 
- Refactor USD export to use subprocess for avoiding DLL conflicts

## Version 0.23
- -Add support for exporting 3D models to ABC, OBJ, USD, and FBX formats from the gallery context menu. Include texture extraction functionality for 3D models. 
- Update metadata handling to use per-workflow subfolders. 
- Fix runner to avoid double prefixing filenames and adjust tab reordering logic.

## Version 0.22
- Fix Changelog generation

## Version 0.21
- fix installer
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
