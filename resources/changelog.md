# Luma Tools Changelog

## Version 0.6.5.12
- Fix some casses where OIIO would fail

## Version 0.6.5.11
- Improve version filtering

## Version 0.6.5.10
● Pass Builder: Fix publish mode resolving same render dir for all versions

## Version 0.6.5.9
- Improve task and product finding

## Version 0.6.5.8
● Pass Builder: Fix product-render correspondence in publish mode

  - Filter denoised renders to match selected product variant
    (renderLightingMain → only shows Main, not girrafe)
  - Fix Publish To autofill to construct proper product name from
    selected render using render{Task}{Variant} convention
  - Filter Publish To dropdown to only show render-type products
  - Hide products from source dropdown when no matching denoised
    renders exist on disk (scans work dir for available variants)
  - Extract shared _extract_variant_from_product() helper

## Version 0.6.5.7
rePublish:                                                                                                                                                                               - Add independent _run_initial_scan() so tab no longer depends on
    Shot Cleaner tab for render path discovery at startup
  - Fix ThreadSafeProperty mutation bug: build list locally then
    assign (append on read copy was silently discarded)
  - Fix output_subdirectory detection using searchpath comparison
    instead of hardcoded subdirectory names
  - Fix shot_path_for_conversion to include "work" segment in path
  - Fix render_file pattern construction using fileseq padding API
  - Pass render_name and product_name separately to create_ayon_metadata
  - Auto-select first render after scan for immediate publish readiness
  - Populate AYON product dropdown on tab initialization
  - Guard find_product_for_render against empty render names

  Pass Builder:
  - Add "Publish to AYON" checkbox (on by default, persisted per user)
  - Show/hide product name widgets based on checkbox state
  - Populate product combo on tab initialization
  - Respect do_publish flag in build_passes call

  AYON Branding:
  - Add AYON SVG icon and get_ayon_icon()/get_ayon_pixmap() helpers
  - Add AYON_GREEN color constants to UIColors
  - Apply AYON green branding to all "Publish to AYON" buttons,
    checkboxes, and context menu actions across Gallery, Viewer,
    MP4 Maker, rePublish, Pass Builder, and Settings tabs

  Fixes:
  - Filter out empty/deleted AYON products (no versions) from
    get_folder_render_products results
  - Settings tab: AYON bundle label styled with brand color

## Version 0.6.5.6
- Add cancel buttons to all tabs
- Various bug fixes and ui improvements

## Version 0.6.5.5
- Fix Publish path resolving to publishes instead of source renders

## Version 0.6.5.4
- Fix product name detection

## Version 0.6.5.3
- Add Ability to find renders based on Ayon Publish

## Version 0.6.5.2
- Improve Ayon product selection for publishing
- Add product selection dropdown for publishing

## Version 0.6.5
Optimize startup with lazy tab loading and precompiled UI

Startup Performance:
- Defer tab initialize() to first activation instead of
  startup (BaseTab._ensure_initialized with loading overlay)
- Lazy-import tab modules via TAB_REGISTRY instead of
  importing all at package level
- Load precompiled .ui Python files (pyside6-uic) in
  BaseTab.load_ui(), falling back to QUiLoader if missing
- Add startup timing instrumentation to _load_tabs and
  main window creation
- Deploy script now precompiles .ui files and cleans stale
  _compiled/ dir before regenerating

Canvas Tab:
- Stop sync timers when tab deactivated, restart on
  activation to avoid background file I/O on hidden tab

Gallery:
- Disconnect favorites signals before widget deletion to
  prevent callbacks on zombie widgets
- Block signals and processEvents() during bulk widget
  cleanup to avoid stale references
- Defer favorites_manager setup to after all stacks are
  created (avoids redundant _apply_stack_colors during init)

AYON Publishing:
- Add farm parameter to create_ayon_metadata() (default True)
- LocalPublishStrategy now passes farm=False for immediate
  file integration instead of deferring to farm job

Pass Builder:
- Show per-frame progress in spinner with percentage
- Consolidate dual status updates into single spinner call

Bug Fixes:
- Fix check_server_health(port) missing keyword argument
- Add close confirmation dialog when tasks are still running
- Add has_active_workers() to BaseTab for task tracking

## Version 0.6.4.5
- Fix pass builder local publishing

## Version 0.6.4.2
- Improve startup times
- Fix Pass Builder button calling wrong function

## Version 0.6.4.1
Fix Pass Builder using old openpype path finding for renders

## Version 0.6.4

- Remove single-instance mutex check that could prevent the app from launching
- Gallery: Fix case-insensitive username matching when comparing selected user to current user
- UI: Rename "Publish" buttons and labels to "Publish to AYON" across the app for clarity
- Fix version history null check in Settings tab preventing it from sometimes opening
- rePublish tab now uses broader AYON context check instead of strict shot context
- MP4 Maker AYON Publishing:
  - Add "Publish to AYON" checkbox to publish generated MP4s as review files directly from the MP4 Maker tab
  - Add "Publish on Farm" option to submit AYON publish jobs to Deadline instead of publishing locally
  - Supports chaining: generate MP4 → copy to gallery → publish to AYON in one click
  - Settings are persisted per user
- Canvas Browser Drag-Drop & Clipboard Paste:
  - Drag images from a web browser directly onto the canvas (downloads and saves automatically)
  - Paste images from clipboard with Ctrl+V (screenshots, browser "Copy image", URLs)
  - Images paste at cursor position when hovering over canvas, or at view center otherwise
  - Downloads run in background worker threads with size limits and content-type validation
  - Saved images are stored in the user's gallery folder and trigger gallery refresh
- 3D Viewer Stability:
  - Remove pre-warm initialization at startup to fix intermittent access violation crashes on some GPU drivers
  - 3D viewer now initializes lazily on first use instead of during splash screen
  - Add explicit QWebEngineView cleanup before exit to prevent Chromium subprocess crashes
  - Use os._exit() to bypass Qt/Chromium destructor chain that caused exit crashes


## Version 0.6.3.6
- Lots of bug fixes

## Version 0.6.3.5
- Bug fixes

## Version 0.6.3.4
- Fix seed Qspinbox overflow

## Version 0.6.3.3
- Fix Multiworkflow models not showing notes

## Version 0.6.3.2
- Add Trellis MultiView

## Version 0.6.3.1
UI Fix

## Version 0.6.3

- Canvas: Add VideoNode with inline playback, thumbnail extraction, drag-drop, and gallery integration
- Content Hashing: SHA-256 file identity for gallery metadata, canvas file recovery, and favorites auto-migration on rename
- Per-Workflow Input Persistence: Save/restore editable widget values per preset and sub-workflow across sessions
- Custom Job Names: Add ComfyUI job name field with filename-safe validation
- Utility Tab Buttons: Move Settings and Logs to fixed icon buttons in tab bar corner with notification badges
- Video Player: Click-to-play/pause, Space key toggle, seek throttling, fade animations on control bar
- Thread Safety: Wrap server state, settings cache, metadata, and thumbnail writes in proper locks; remove processEvents() calls that caused re-entrancy crashes
- Gallery Stability: Display generation guards against stale widget references, single-to-stack transition handling, batch poll overlap protection
- Polling: Dedicated polling log, grace period for new Deadline jobs, UserName filter, smarter Unknown status handling
- WebSocket: Track activity timestamps to prevent false-positive completion detection during normal execution
- Job Data Isolation: Per-submission _job_data directories to fix race conditions between concurrent submissions
- Feature Requests: Add reject with reason and user notification support
- ComfyUI: WebSocket image download, deduplication between WS and HTTP paths, configurable Deadline poll interval

## Version 0.6.2.10

- Add ComfyUI dynamic workflow execution analytics, user feedback from farm will get more and more accurate as we use the models.

## Version 0.6.2.9

- Changed metadata matching to use longest-prefix-wins to fix some gallery items not finding links correctly

## Version 0.6.2.8

- Fix muted nodes breaking model chain in subgraph expansion

  ComfyUI Workflow:
  - Fix muted/bypassed nodes (mode 2/4) inside subgraphs severing link chains during API conversion — downstream nodes lost required inputs
  - Add pass-through resolution: trace links upstream through muted nodes (output slot N → input slot N) to find the real source node
  - Handle chains of multiple consecutive muted nodes via recursive resolution

## Version 0.6.2.7

- Fix values not being set by user not falling back to values in comfyui workflow files

## Version 0.6.2.6

- UI Improvements:
  - Vertical separation: Non-image widgets (text, toggles, combos) are now stacked on top, image widgets are arranged horizontally below instead of the old left/right horizontal split
  - Compact labels: Image/video node labels use min_width=0 instead of 160 when there are 3+ nodes
  - Simplified the 3-branch layout logic (mixed / image-only / non-image-only) into a cleaner 2-step approach (add non-image widgets, then add image widgets)
- Added _compact flag when total_image_nodes >= 3
- Compact mode uses shorter button text: "Add..." / "Clear" instead of "Add Images..." / "Clear All"
- Compact count labels: "None (3 nodes)" instead of "No images selected (3 load nodes detected)", and "2/node" instead of "2 per node"
- Set count_label.setMinimumWidth(0) so it can shrink

## Version 0.6.2.5

- Improve tab re-ordering performance
- Change default tab order

## Version 0.6.2.4

- Deadline Submitter:
  - Create _job_data/ subdirectory under output dir for all submission artifacts
  - Move runner/utils scripts, job_info, plugin_info, workflow JSON, and seeds JSON into _job_data/
  - Update StartupDirectory to _job_data/ so runner can still import comfyui_utils
  - Gallery metadata (add_item_metadata) stays in output root as before
- ComfyUI Metadata:
  - Update cleanup_job_temp_files() to remove _job_data/ directory via shutil.rmtree
  - Keep backward-compat cleanup of root-level files for old jobs

## Version 0.6.2.3

- Change runner logs to be stored in /logs dir instead of directly in user folder

## Version 0.6.2.2

- Improve node sorting

## Version 0.6.2.1

- Gallery:
  - Remove JobStatusBar widget and all job event subscriptions (submitted, progress, completed, failed, all_completed)
  - Keep only job_output_ready subscription for refresh triggers
  - Delete job_status_bar.py module entirely
- Settings:
  - Remove unused settings: auto_extract_textures, comfyui_show_recent_outputs, gallery_show_job_status, gallery_show_quick_actions
  - Remove OverrideHou and AutoExtractTextures checkboxes from settings.ui
  - Add comfyui_convert_colorspace setting and checkbox for ACES→sRGB image conversion
  - Replace removed gallery checkboxes with new ComfyUIConvertColorspace checkbox

## Version 0.6.2

- Auto-convert unsupported image formats to PNG for ComfyUI
- ComfyUI Image Conversion:
  - Add image_convert.py module with OIIO-based format conversion (EXR, HDR, DPX, TGA → PNG)
  - Support ACES→sRGB colorspace conversion via OCIO with gamma 2.2 fallback
  - Add comfyui_convert_colorspace user setting (default: True)
  - Extend COMFYUI_SUPPORTED_EXTENSIONS to allow browsing EXR, HDR, DPX, TGA files
- Workflow Integration:
  - Rewrite image basenames to .png in modifier.py (both editable and legacy handlers)
  - Replace shutil.copy2 with copy_or_convert in submitter.py (all 3 file copy loops)
  - Add conversion support to copy_inputs_to_server in utils.py
  - Add conversion safety net in runner.py for farm execution (graceful fallback)

## Version 0.6.1.4

- Fix Jobname not appending to filenames

## Version 0.6.1.3

- UI Fixes

## Version 0.6.1.2

- ComfyUI Editable Nodes:
  - Add new 'directory' widget type for folder selection
  - Configure VHS_LoadImagesPath to use directory browser instead of plain text input
  - Add directory widget UI with Browse button and placeholder text
  - Add _browse_directory() method using browse_directory_with_memory for persistence
- ComfyUI Workflow Modifier:
  - Add directory widget type handling in modify_workflow_api_format()
  - Set directory path in workflow inputs using widget_name or 'directory' fallback
  - Add logging for directory value assignments
- ComfyUI Server:
  - Refresh node definitions on network after ComfyUI self-restart
  - Ensure node info cache stays in sync after server restarts
- Presets:
  - Add "Normal Crafter" multi-workflow preset with Video and Image Sequence inputs
  - Configure as image output type with non-iteratable workflows

## Version 0.6.1.1

- Gallery User Discovery:
  - Remove restrictive filtering that only showed admin/sup users
  - Discover all user directories in network gallery path for public browsing
  - Get base path directly from settings instead of via _get_network_user_path
  - Skip hidden/system directories (starting with . or _)
  - Add comprehensive logging for discovery process (base path, items found, users added)
- Gallery Empty State:
  - Fix bug where switching to user with no items left previous thumbnails visible
  - Add _clear_gallery_widgets() method to properly clear all widget types
  - Clear flow layout, widget cache, stacked widgets, section tracking, and group colors
  - Reset empty state widget reference after clearing to prevent "already deleted" errors
  - Show simple "{username}'s gallery is empty" message for other users
  - Show full guidance widget (ComfyUI buttons) only for own empty gallery
- Logging:
  - Add detailed logging to user discovery and visibility update methods
  - Log discovered users list and button visibility decisions for debugging

## Version 0.6.1

- ComfyUITab:
  - Fix excessive vertical spacing between editable node widgets in UI manager
  - Only text widgets (multiline) now expand vertically with stretch factor
  - Line edits, spinboxes, and checkboxes use default stretch (0) for compact layout
  - Add final stretch to push non-expanding widgets to top
- ComfyUI Workflow Pipeline:
  - Add automatic file path normalization: convert full paths to basenames in workflows
  - Add file copying system for all file types (images, videos, 3D models, audio)
  - Skip connected inputs when extracting editable nodes
  - Add support for dict-format widgets_values in subgraph nodes
  - Fix toggle node logging (indentation issue)
- Node Configs:
  - Add PrimitiveNode widget mappings for value and control mode
  - Add ACE Step 1.5 Audio node support (SaveAudioMP3, SaveAudioOpus, TextEncodeAceStepAudio1.5, EmptyAceStep1.5LatentAudio)
  - Add MISSING_WIDGETS system for widgets /object_info doesn't report correctly
  - Add quality widget mapping for audio save nodes
  - Add audio export nodes to EXPORT_NODE_TYPES
- Runner & Server:
  - Simplify runner.py: remove local ComfyUI management, always use persistent server
  - Remove start_comfyui_server(), stream_output() functions (now in server.py)
  - Deprecate --persistent, --mode, --python-path, --lowvram args (kept for backward compat)
  - Update server behavior documentation for persistent mode
- Image Viewers:
  - Major refactoring of image viewer widgets
  - Add click-to-cycle behavior for multi-image thumbnails
  - Add viewer state persistence across sessions
- Settings:
  - Swap workflow preset description/note fields for better UX
  - Update MMAudio preset
  - Add Stable Audio preset with new workflow path
  - Reorder presets for better organization
- Core Utils:
  - Add centralized path resolution utilities
  - Improve subprocess management for Windows compatibility
  - Add logging utilities with network path support

## Version 0.6

### New Canvas Tab

A new collaborative workspace for image comparison and annotation:
- **Visual Comparison**: Drag and drop images onto an infinite canvas for side-by-side comparison
- **Drawing Tools**: Add annotations with pen, eraser, arrows, rectangles, ellipses, and text
- **Multiple Canvases**: Create separate canvases for different projects or shots
- **Scope Options**: Choose between job-wide canvases (shared across all shots) or shot-specific canvases
- **Navigation**: Pan and zoom with mouse/touchpad, or use Space+drag for Photoshop-style temporary panning
- **Minimap**: Quick navigation overview of your entire canvas
- **Brush Size Indicator**: Visual cursor feedback shows pen/eraser size as you work
- **Undo/Redo**: Full history system for all canvas operations
- **Export**: Save your annotated canvas as an image
- **Gallery Integration**: Right-click images in Gallery to "Add to Canvas" or enable auto-add for new ComfyUI outputs, Canvas and Gallery are fully linked.
- **Multi-User Sync**: Real-time collaboration with network sync and timeline scrubbing

### New ComfyUI Prompt Builder

New interactive prompt building tool for creating complex AI prompts:
- **Category-Based Selection**: Choose from Camera, Style, Filters, Effects, and Movement options inspired by video generation tools
- **Weighted Tags**: Adjust importance of each element with weight sliders (0.1-3.0x)
- **Live Preview**: Real-time preview of formatted prompt as you make selections
- **Template System**: Multiple built-in templates (Natural Language, Keyword List, Weighted Tags, ComfyUI Format, Simple List)
- **Negative Prompts**: Separate builder for negative prompt generation
- **Preset Management**: Save and load your favorite prompt configurations
- **Randomization**: Generate random prompt combinations for creative exploration
- **Multiple Formats**: Support for Automatic1111 `(text:1.2)` and NovelAI `{text}` weight formats
- **Keyboard Shortcuts**: Escape to close, Ctrl+R to randomize, Ctrl+Enter to insert
- **Seamless Integration**: Access via "Use Prompt Builder..." in preset dropdown on any ComfyUI text input

### ComfyUI Workflow Enhancements

Major improvements to AI workflow management:
- **Component/Subgraph Support**: Full support for advanced ComfyUI nodes that contain sub-workflows
- **Settings Nodes**: Adjustable parameters like KSampler settings, motion controls, and more are now organized in collapsible groups
- **Output Type System**: Workflows are now categorized (Image/Video/3D/Audio/Other) for better organization
- **Category Filtering**: Filter workflow presets by custom categories for easier browsing
- **Exposed Parameters Tab**: Quick access to all editable workflow parameters in one place
- **Comparison Dialog**: Select two gallery items to compare their settings and prompts side-by-side
- **Rating Breakdown**: Visual chart showing rating distribution for presets
- **Multi-Workflow Management**: Add, edit, and remove workflows within presets via improved dialog
- **Centralized Storage**: Workflows are now auto-copied to a shared directory for team access
- **Video Node Support**: Better handling of video loader and export nodes

### Gallery Improvements (Previously ComfyUI Gallery)

Enhanced browsing and organization:
- **Media Player**: Full media player for Video and Audio playback
- **Groups**: Create groups by dragging thumbnails onto each other
- **Sort Direction Toggle**: Quickly reverse sort order with a single click
- **Loading Overlay**: Clear visual feedback when switching galleries or loading content
- **File Type Filters**: Filter by image, video, 3D model, or audio files with persistent settings
- **Better Support**: Storing and playback fully added for audio and video
- **"Show in Gallery"**: Navigate from Canvas directly to an item's location in the Gallery
- **Better Thumbnails**: Optimized loading and cleaner visual design

### MP4 Maker Integration

- **Add to Gallery**: Generated MP4s can now be automatically added to your Gallery
- **Metadata Tracking**: MP4s store source file info and quality settings for reference
- **User Setting**: Toggle the "Add to Gallery" feature on/off per your preference

### Metadata & Iteration Tracking

- **Input File Tracking**: System now reliably identifies source images vs. generated outputs
- **Lineage System**: Track parent-child relationships when iterating on previous generations
- **Per-File Details**: Each output stores node execution timing, seed values, and full workflow info
- **Metadata Levels**: Visual indicators show full metadata (blue), partial metadata, or legacy files (gray)
- **Comparison Tools**: Side-by-side parameter comparison to see exactly what changed between iterations

### Shot Cleanup Tab (formerly Shot Cleaner)

- **Renamed**: "Shot Cleaner" is now "Cleaner" with expanded gallery cleanup functionality
- **Same Features**: All existing cleanup capabilities remain unchanged

### Settings & Configuration

- **Improved Settings Access**: New safe accessors prevent errors when reading/writing settings
- **Canvas Sync Interval**: Adjustable network sync timing (500-5000ms) for Canvas collaboration
- **Category Management**: Create and organize custom categories for ComfyUI presets
- **Better Logging**: All system messages now use standardized logging for easier troubleshooting
- **Network Path Updates**: Unified network output path setting across all tools

### User Experience Improvements

- **Cross-Tab Drag-and-Drop**: Drag Gallery items to ComfyUI inputs, auto-switch tabs by hovering
- **Better Feedback**: Loading overlays, progress indicators, and status messages throughout the app
- **Cleaner UI**: Streamlined layouts, improved button alignment, and consistent widget spacing
- **Keyboard Shortcuts**: Enhanced shortcut handling in Gallery and Canvas tabs
- **Empty States**: Helpful messages when no content is available

### Performance & Stability

- **Thread Safety**: Critical fixes to prevent crashes during multi-threaded operations
- **Memory Management**: Improved caching for thumbnails, metadata, and other resources
- **Worker Lifecycle**: Fixed garbage collection issues that could cause background tasks to fail
- **Drag-and-Drop Stability**: Robust widget validity checks prevent crashes during drag operations
- **Optimized Loading**: Faster thumbnail generation and gallery switching

### Code Architecture (Internal)

For developers and technically-inclined users:
- **Reorganized Structure**: Cleaner separation of UI code (python/ui/tabs/), 3D geometry (python/geo/), and Deadline integration (python/deadline/)
- **New Utilities**: Caching framework, validators, file scanners, metadata file handling, subprocess utilities
- **Event Bus**: Signal-based communication between tabs for better modularity
- **Consolidated Logging**: Centralized network logging with proper rotation and exception handling
- **Removed Dead Code**: Cleanup of unused imports, functions, and legacy code paths
- **Better Type Safety**: Type hints added throughout worker code and settings management
- **Testing Support**: CLI flags (--tab, --auto-close) for automated testing and debugging

## Version 0.5.4.1

- Morning coffee bugfixes and UI updates

## Version 0.5.4

- Add caching for all thumbnails
- Fix stacked view not repecting sort mode
- Implement thumbnail in-memory caching for faster load times
- Improve reordering logic
- Improve general gallery performance

## Version 0.5.3.2

- UI fix

## Version 0.5.3.1

- Bug fixes
- UI updates

## Version 0.5.3

- Add favorites manager for handling liked items and user-defined groups
- Implement groups filter panel as a collapsible sidebar
- Add new stacking modes: grid, stack by job, stack by groups, stack by groups + job
- Add like button to embedded viewer with keyboard shortcut (L)
- Add group management dialog for creating/editing groups with color selection
- Add support for video and audio file types in gallery
- Update thumbnail widgets with like indicator and group color borders
- Add keyboard shortcuts for quick group actions (G, Ctrl+G, 1-9)
- Add to group/likes context menu
- Improved caching in gallery

## Version 0.5.2.3

- More pesky selection/deletion fixes

## Version 0.5.2.2

- Selection/deletion fixes

## Version 0.5.2.1

- Add "Show verbose logs" checkbox to logs tab with filtering for debug messages
- More user feedback improvemnts/fixes

## Version 0.5.2

- New statusbar message queue system with priority levels and activity tracking, this fixes many messages not showing up
- Make Deadline job query async to prevent blocking splash screen during recovery

## Version 0.5.1.5

- More job recovery improvements

## Version 0.5.1.4

- Job recovery now always checks Deadline for running jobs from the current user
- Recovers jobs even if persisted state was lost or jobs were submitted from another session

## Version 0.5.1.3

- Fix potential crash while job is running

## Version 0.5.1.2

- Selection Fixes

## Version 0.5.1.1

- Fix viewer not showing 3d objects when pressing next
- Fix background frame not updating correctly

## Version 0.5.1

- Add comprehensive "Properties" dialog to context menus for all gallery items (images, models, stacks)
- Properties shows: file info, metadata, workflow details, relationships (inputs/outputs), user notes
- Supports both single items and stacked items (shows top item properties)
- Fix checkmarks not disappearing
- Fix mouse hover deselecting items in some cases
- Fix user directory filtering
- Fix Splashscreen not disappearing until thumbnails are generated even though that is a background task
- Make 3D viewer initialization async to prevent splash screen blocking
- Unify thumbnail styling functions
- Gallery UI tweaks

## Version 0.5.0.2

- Thumbnails will now regenerate when new version detected to have latest renderer version rendered
- Extend drag selection to handle grouped stack items
- Gallery bug fixes

## Version 0.5.0.1

- Gallery bug fixes

## Version 0.5

- New stacked view based on job
- New hide/show inputs button
- New features only apply to new generations going forward due to required metadata
- New files fully supported will show in blue, old non supported are grey
- A few UI improvements to Gallery
- Major refactor (hopefully last)

## Version 0.4.6.6

- Fix multi-input workflows - loader nodes without inputs are now bypassed instead of failing

## Version 0.4.6.5

- Job Persistence fixes
- Fix copying of multiloader workflows

## Version 0.4.6.4

- Fix path lists for multi image workflows

## Version 0.4.6.3

- Add memory management flags for ComfyUI persistent server mode

## Version 0.4.6.2

- UI fix

## Version 0.4.6.1

- Fix User feedback
- Fix Prompt copy

## Version 0.4.6

- Add multi-select support to ComfyUI Gallery
- UI updates
- Logging fixes

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

- HDRI rendering improvements
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

- Remove pop up when new version, just use settings notification badge
- Fix issue where rapid clicks would trigger multiple async viewer creations before the first one completed

## Version 0.4.2

- Add time estimates
- Improve settings persistence with atomic writes
- Remove unused camera controls in 3D viewer
- Update notification text fix
- Close viewer when switching users
- Don't send user message feature request task is complete
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

- Added PYTHONIOENCODING=utf-8 to comfy launch
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

- New custom three.js 3D viewport
- Improve 3D viewer prewarming to prevent window flashing and add configurable camera distance
- Enhance image viewers with delete functionality
- Fix models not being offloaded when leaving model

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

- AYON Fixes

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
