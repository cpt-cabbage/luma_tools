# Luma Tools Changelog

## Version 0.42
- Fixing bundle name

## Version 0.41
- Ayon Fixes

## Version 0.4
- Migrate UI components from PySide2 to PySide6

## Version 0.28
- Add unified model loader supporting FBX, OBJ, USD, GLB, GLTF formats - Implement lazy loading for gallery thumbnails with batched loading - Add multi-workflow models with individual settings and editable nodes - Improve metadata caching and batch loading for better performance - Update UI components with tooltip lazy loading and placeholder caching - Add server restart functionality for persistent ComfyUI mode - Refactor GLB-specific modules to unified model handling - Update dependencies and clean up cache files

## Version 0.26
- Introduce multi-workflow models allowing multiple workflows per preset with individual settings - Add UI components for workflow selection and notes display in ComfyUI tab - Implement metadata caching and batch loading for improved gallery performance - Update workflow presets structure

## Version 0.25
- Implement lazy loading for gallery thumbnails to improve performance - Updates to thumbnaill rendering - Add auto-extract textures option for 3D model exports - Add server not found behavior settings for persistent mode - Add regenerate thumbnails button in settings

## Version 0.24
- Add conditional node bypassing based on toggle values in workflows - Refactor USD export to use subprocess for avoiding DLL conflicts

## Version 0.23
- -Add support for exporting 3D models to ABC, OBJ, USD, and FBX formats from the gallery context menu. Include texture extraction functionality for 3D models. - Update metadata handling to use per-workflow subfolders. - Fix runner to avoid double prefixing filenames and adjust tab reordering logic.

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
