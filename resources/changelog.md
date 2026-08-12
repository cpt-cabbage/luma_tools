# Luma Tools Changelog

## Version 0.8
refactor

## Version 0.7.1.2
More bug fixes

## Version 0.7.1.1
Bug fixes

## Version 0.7.1
- ComfyUI: live server status indicator next to the Submit button — shows whether the farm server is online, starting, or offline
- ComfyUI: new "Fail & Delete Job" option in Settings — automatically removes the Deadline job when the server is unavailable instead of leaving it in a failed state
- ComfyUI: submit button now warns you about server status before sending jobs
- Gallery: faster loading — file hashes are only computed when actually needed instead of for every file
- Fixed network path detection not retrying after a temporary network outage
- Removed hardcoded studio paths from farm scripts — farm jobs now get their config from the submitter

## Version 0.7
- Removed the Canvas tab (and all the "Add to Canvas" right-click options that came with it)
- MP4 Maker: now works with render sequences using any frame number padding, not just 4 digits
- MP4 Maker: "Add to Gallery" is now turned on by default for new users
- 3D Viewer: model files with apostrophes in the path (e.g. "O'Brien") now load correctly
- 3D Viewer: skeleton preview thumbnails now show properly for SMPL and USD characters
- ComfyUI: seed, render time, and other per-file info is now saved for farm jobs (was silently disabled)
- ComfyUI: cleaner farm logs - no more "Uploading 0 images" spam
- AYON publish: fixed source path getting mangled on Windows backslash paths
- Clearer error messages when FFmpeg or Deadline aren't installed
- Lots of internal cleanup and reliability improvements under the hood

## Version 0.6.5.12
- Fixed some cases where OIIO conversion would fail

## Version 0.6.5.11
- Improved version filtering when picking publishes

## Version 0.6.5.10
- Pass Builder: fixed publish mode using the same render folder for all versions

## Version 0.6.5.9
- Improved task and product detection

## Version 0.6.5.8
- Pass Builder: fixed product/render mismatches in publish mode
- Denoised renders now correctly match the selected variant
- "Publish To" autofill builds the right product name from the selected render
- Hides products that have no matching renders on disk

## Version 0.6.5.7
- rePublish: now finds renders on its own at startup (no longer needs the Shot Cleaner tab open first)
- rePublish: fixed several path and version-detection bugs
- Pass Builder: added "Publish to AYON" checkbox (on by default)
- All "Publish to AYON" buttons across the app now use AYON green branding

## Version 0.6.5.6
- Added Cancel buttons to all tabs
- Various bug fixes and UI improvements

## Version 0.6.5.5
- Fixed Publish path going to publishes instead of source renders

## Version 0.6.5.4
- Fixed product name detection

## Version 0.6.5.3
- Added the ability to find renders based on AYON publishes

## Version 0.6.5.2
- Improved AYON product selection for publishing
- Added a product selection dropdown for publishing

## Version 0.6.5
**Faster startup**
- Tabs now load on first click instead of all at once during startup, so the app opens noticeably faster
- Various Gallery and Pass Builder stability fixes
- Confirmation dialog when closing the app while jobs are still running

## Version 0.6.4.5
- Fixed Pass Builder local publishing

## Version 0.6.4.2
- Faster startup
- Fixed Pass Builder button calling the wrong action

## Version 0.6.4.1
- Fixed Pass Builder using the old render path lookup

## Version 0.6.4
- Fixed an issue where the app sometimes wouldn't launch
- Gallery: usernames are now matched case-insensitively
- Renamed "Publish" buttons to "Publish to AYON" everywhere for clarity
- Settings tab now opens reliably (fixed a crash)
- rePublish now works in more contexts (no longer requires strict shot context)
- **MP4 Maker: new "Publish to AYON" checkbox** — publish your MP4 as a review file in one click
- **MP4 Maker: "Publish on Farm" option** — submit AYON publish jobs to Deadline instead of locally
- Canvas: drag images directly from a web browser onto the canvas (downloads automatically)
- Canvas: paste images from clipboard with Ctrl+V (screenshots, browser images, URLs)
- 3D Viewer: fixed crashes on some GPUs by initializing on first use instead of startup

## Version 0.6.3.6
- Lots of bug fixes

## Version 0.6.3.5
- Bug fixes

## Version 0.6.3.4
- Fixed seed input overflow

## Version 0.6.3.3
- Fixed multi-workflow models not showing notes

## Version 0.6.3.2
- Added Trellis MultiView preset

## Version 0.6.3.1
- UI fix

## Version 0.6.3
- **Canvas: video support** — drag videos onto the canvas with thumbnails and inline playback
- File identity tracking: files are now matched by content hash, so renames don't break favorites or canvas links
- Workflow inputs are now remembered per-preset across sessions
- Custom job names: name your ComfyUI submissions for easier tracking
- Settings and Logs are now icon buttons in the tab bar corner with notification badges
- Better video player: click to play/pause, Space to toggle, smoother seek
- Many stability fixes for Gallery, polling, and concurrent submissions

## Version 0.6.2.10
- Added ComfyUI workflow timing analytics — the more you use models, the more accurate time estimates become

## Version 0.6.2.9
- Fixed some gallery items not finding their input/output links correctly

## Version 0.6.2.8
- Fixed muted/bypassed nodes inside subgraphs breaking the model chain

## Version 0.6.2.7
- Fixed values from workflow files not being used as defaults when the user hadn't set anything

## Version 0.6.2.6
- ComfyUI tab UI improvements:
- Cleaner layout with text/toggle widgets on top, image widgets below
- More compact labels and buttons when there are 3+ image inputs

## Version 0.6.2.5
- Faster tab re-ordering
- Changed default tab order

## Version 0.6.2.4
- ComfyUI submissions: all temporary files are now organized in a per-job folder for easier cleanup

## Version 0.6.2.3
- ComfyUI farm runner logs are now stored in a /logs folder instead of the user folder root

## Version 0.6.2.2
- Improved node sorting

## Version 0.6.2.1
- Removed the old job status bar (replaced by status bar messages)
- Added a setting to convert ACES → sRGB images automatically for ComfyUI

## Version 0.6.2
- **Auto-convert images for ComfyUI**: EXR, HDR, DPX, and TGA files are now automatically converted to PNG when sending to ComfyUI, with proper colour management

## Version 0.6.1.4
- Fixed the job name not being added to output filenames

## Version 0.6.1.3
- UI fixes

## Version 0.6.1.2
- ComfyUI: added a "directory" widget type for nodes that need a folder (like VHS_LoadImagesPath)
- ComfyUI server: refreshes node info after a self-restart
- New "Normal Crafter" preset

## Version 0.6.1.1
- Gallery: now shows all users in the network gallery folder, not just admins/sups
- Gallery: fixed a bug where switching to a user with no items still showed the previous thumbnails
- Other users with no items now show a simple "{name}'s gallery is empty" message

## Version 0.6.1
- ComfyUI tab: fixed excessive vertical spacing between widgets
- ComfyUI: any file path you select is now automatically copied to the ComfyUI input folder
- Added support for ACE Step 1.5 audio nodes
- Simplified ComfyUI runner — always uses the persistent server now
- Image viewers: click multi-image thumbnails to cycle through them
- Image viewers: viewer state now persists across sessions

## Version 0.6
**Major release**

### New Canvas tab *(removed in 0.7)*
A collaborative workspace for image comparison and annotation:
- Drag images onto an infinite canvas for side-by-side comparison
- Drawing tools: pen, eraser, arrows, rectangles, ellipses, text
- Multiple canvases per project, with job-wide and shot-specific options
- Pan/zoom navigation, minimap, brush size indicator, full undo/redo
- Right-click Gallery items to "Add to Canvas", or auto-add new ComfyUI outputs
- Multi-user real-time sync

### New ComfyUI Prompt Builder
- Build prompts by picking from Camera, Style, Filters, Effects, Movement categories
- Adjust the weight of each element with sliders
- Live preview as you build
- Save and load your favourite prompt setups
- Multiple output formats (Automatic1111, NovelAI, plain list, etc.)
- Negative prompt builder included

### ComfyUI workflow improvements
- Full support for component/subgraph nodes (sub-workflows)
- Settings nodes (KSampler, motion controls, etc.) are organized into collapsible groups
- Workflows are categorized by output type (Image/Video/3D/Audio/Other)
- Filter workflow presets by category
- New "Exposed Parameters" tab for quick access to all editable values
- Compare two gallery items side-by-side (settings, prompts)
- Rating breakdown chart for each preset

### Gallery improvements (formerly ComfyUI Gallery)
- Full media player for video and audio playback
- Drag thumbnails onto each other to create groups
- Sort direction toggle
- Filter by image, video, 3D model, or audio
- "Show in Gallery" navigation from Canvas
- Better thumbnail design and faster loading

### MP4 Maker
- Generated MP4s can now be automatically added to your Gallery
- MP4s store source file info and quality settings as metadata

### Metadata & iteration tracking
- Better detection of input vs. output files
- Track parent/child relationships when iterating on previous generations
- Each output stores node timing, seed, and full workflow info
- Visual indicators for full vs. partial vs. legacy metadata

### Renamed
- "Shot Cleaner" tab is now called "Cleaner"

### Other
- Cross-tab drag and drop: drag Gallery items into ComfyUI inputs
- Loading overlays, progress indicators, and clearer status messages throughout
- Many crash and stability fixes

## Version 0.5.4.1
- Morning coffee bug fixes

## Version 0.5.4
- Cached all thumbnails for faster loading
- Fixed stacked view ignoring sort mode
- Faster reordering and general gallery performance

## Version 0.5.3.2
- UI fix

## Version 0.5.3.1
- Bug fixes and UI updates

## Version 0.5.3
- Like items with the L key
- Create custom groups for organizing gallery items
- New stacking modes: grid, by job, by groups, or both
- Group management dialog with colour picker
- Video and audio file support in gallery
- Quick group keyboard shortcuts (G, Ctrl+G, 1-9)
- Better gallery caching

## Version 0.5.2.3
- More selection/deletion fixes

## Version 0.5.2.2
- Selection/deletion fixes

## Version 0.5.2.1
- Added "Show verbose logs" checkbox to the Logs tab
- More user feedback fixes

## Version 0.5.2
- New status bar message system — messages no longer get lost or skipped
- Deadline job recovery no longer blocks the splash screen on startup

## Version 0.5.1.5
- More job recovery improvements

## Version 0.5.1.4
- Job recovery now always checks Deadline for your running jobs, even if state was lost

## Version 0.5.1.3
- Fixed potential crash while a job is running

## Version 0.5.1.2
- Selection fixes

## Version 0.5.1.1
- Fixed 3D objects not showing when pressing Next in the viewer
- Fixed background frame not updating

## Version 0.5.1
- New "Properties" right-click option for all gallery items — shows file info, metadata, workflow details, relationships, and notes
- Works for single items and stacks
- Various selection and hover fixes
- Splash screen no longer waits for thumbnails to finish generating
- 3D viewer now starts in the background

## Version 0.5.0.2
- Thumbnails regenerate when a new app version is detected
- Drag selection now handles grouped stack items
- Gallery bug fixes

## Version 0.5.0.1
- Gallery bug fixes

## Version 0.5
**New stacked view by job**
- New hide/show inputs button
- New features only apply to new generations going forward (require new metadata)
- Files with full metadata show in blue, older files in grey
- A few Gallery UI improvements
- Major refactor under the hood

## Version 0.4.6.6
- Fixed multi-input workflows where loader nodes without inputs would fail

## Version 0.4.6.5
- Job persistence fixes
- Fixed copying multi-loader workflows

## Version 0.4.6.4
- Fixed file path lists for multi-image workflows

## Version 0.4.6.3
- Added memory management flags for the persistent ComfyUI server

## Version 0.4.6.2
- UI fix

## Version 0.4.6.1
- Fixed user feedback messages
- Fixed prompt copy

## Version 0.4.6
- Multi-select support in ComfyUI Gallery
- UI updates and logging fixes

## Version 0.4.5.1
- Job persistence/recovery added — the app picks up running jobs after a restart
- Gallery no longer flashes when new images appear
- UI tweaks

## Version 0.4.5
- Better batch image selector with visual pairing for multiple Load Image nodes
- Square grid layout with colour-coded borders showing which images go with which nodes
- Drag-and-drop reordering
- Order numbers in each thumbnail corner
- Pairing stats in the count label
- Double-click to remove images from selection
- Removed pop-up toast notifications

## Version 0.4.4.1
- Better user feedback
- Fixed preview nodes being skipped and not saving images

## Version 0.4.4
- Better ComfyUI status messages including "loading model" detection
- Horizontal layout for multiple image inputs
- Better encoding handling for emojis

## Version 0.4.3.7
- Added Low VRAM mode setting for ComfyUI

## Version 0.4.3.6
- Fixed batch mode progress percentage in the status bar
- Queue counter now only counts luma_tools jobs (not all Deadline jobs)

## Version 0.4.3.5
- Fixed mapping for some nodes

## Version 0.4.3.4
- Real-time ComfyUI task progress via Deadline logs
- Better queue messages distinguishing your jobs from other users'
- Job-level progress percentage in status bar during rendering

## Version 0.4.3.3
- Better ComfyUI server crash detection and auto-restart

## Version 0.4.3.2
- Backend refactor for easier maintenance

## Version 0.4.3.1
- HDRI rendering improvements
- 3D viewer UI polish

## Version 0.4.3
- 3D viewer: lighting modes (headlight, studio, HDRI)
- 3D viewer: shading modes (shaded, textured, wireframe)
- 3D viewer: light strength slider
- ComfyUI: queue position display for Deadline jobs
- Admin-level HDRI management
- Fixed 3D viewer freezing on rapid next/prev clicks

## Version 0.4.2.2
- Fixed double-clicking an image causing it to close

## Version 0.4.2.1
- Removed the new-version popup — now just uses the settings notification badge
- Fixed rapid clicks creating multiple async viewers at once

## Version 0.4.2
- Time estimates for jobs
- More reliable settings saves
- Removed unused 3D viewer camera controls
- Fixed close-viewer-on-user-switch
- Better server crash detection

## Version 0.4.1.23
- Always append input filename to ComfyUI output files

## Version 0.4.1.22
- Feature request improvements

## Version 0.4.1.21
- Fixed 3D viewer

## Version 0.4.1.20
- Moved user feature requests to user folders

## Version 0.4.1.19
- Support for input images from custom nodes

## Version 0.4.1.18
- Fixed input file handling edge cases

## Version 0.4.1.17
- Feature request submission dialog with categories (Feature, Bug, Enhancement, Question)
- Fixed install script issues

## Version 0.4.1.15
- Periodic version checking every 2 minutes
- New version notifications via status bar, system tray, and pop-up

## Version 0.4.1.14
- Window size and maximized state are now remembered
- New version notifications
- Slider for generation count
- Cleaned up unused dependencies

## Version 0.4.1.13
- New "Apply Settings" right-click option in gallery
- Component/subgraph node support
- File logging with rotation
- New menu options: View Input, Publish to AYON

## Version 0.4.1.10
- Renamed polling terminology from "frames" to "jobs" for clarity
- Hide add/edit model buttons from non-admin users

## Version 0.4.1.9
- System tray icon with notifications
- Fixed background tasks getting cancelled too early in polling and gallery
- Network path polling fallback for reliable file watching
- Editable node values are now preserved when switching workflows

## Version 0.4.1.8
- Auto crash recovery for the persistent ComfyUI server
- Server auto-restarts when ComfyUI crashes
- Crash counter resets after 5 minutes of stable uptime

## Version 0.4.1.7
- Better generic handling for export nodes
- Improved polling and submission error handling

## Version 0.4.1.6
- Fixed Python search path issue

## Version 0.4.1.5
- Internal cleanup

## Version 0.4.1.4
- ComfyUI fixes

## Version 0.4.1.3
- Use UTF-8 encoding when launching ComfyUI
- Fixed AYON publishing always creating version 1 (now auto-increments)

## Version 0.4.1.2
- rePublish tab UI improvements
- Source selector is now a dropdown button
- Product name field is now read-only

## Version 0.4.1.1
- rePublish: added "Publish to Current AYON Task" toggle for publishing custom renders to your current task

## Version 0.4.1
- Fixed publishing from the viewer
- Fixed changelog generation

## Version 0.4
- New three.js-based 3D viewport (custom)
- Better 3D viewer pre-warming to prevent window flashing
- Configurable camera distance
- Delete option in image viewers
- Fixed models not being released when leaving the model

## Version 0.39
- More import fixes

## Version 0.38
- Fixed stylesheet imports

## Version 0.37
- Restricted tabs are now fully prevented from initializing
- rePublish tab now works in standalone mode with custom directory selection

## Version 0.36
- AYON publish now streams output in real-time with progress detection
- Configured OpenGL globally to prevent window flashing
- Pre-initialize 3D viewer in the background for faster loading

## Version 0.35
- rePublish now publishes directly from the work folder without copying files
- Status spinner and animated updates during AYON publish

## Version 0.34
- Bug fixes

## Version 0.33
- More publishing fixes

## Version 0.32
- Fixed bundle name

## Version 0.31
- AYON fixes

## Version 0.3
- Migrated UI from PySide2 to PySide6

## Version 0.28
- New unified 3D model loader supporting FBX, OBJ, USD, GLB, and GLTF
- Lazy loading for gallery thumbnails
- Multi-workflow models with individual settings
- Better metadata caching for performance
- Server restart for persistent ComfyUI mode

## Version 0.26
- Multi-workflow models: multiple workflows per preset, each with its own settings
- Workflow selection UI in ComfyUI tab
- Workflow notes display

## Version 0.25
- Lazy loading for gallery thumbnails
- Auto-extract textures option for 3D model exports
- "Server not found" behaviour settings
- "Regenerate thumbnails" button in settings

## Version 0.24
- Toggle nodes can now bypass other nodes in workflows
- USD export uses a subprocess to avoid DLL conflicts

## Version 0.23
- Export 3D models from gallery to ABC, OBJ, USD, and FBX
- Texture extraction included
- Per-workflow metadata folders

## Version 0.22
- Fixed changelog generation

## Version 0.21
- Fixed installer

## Version 0.20
- User selector for viewing other users' galleries (read-only)
- Cancel button for running ComfyUI submissions
- Pause/resume controls for log output
- Auto-enable iterate mode when one image is selected
- Background caching updates

## Version 0.14
- UI updates

## Version 0.13
- Replaced loading overlay with status bar progress
- Better batch job polling
- Editable node overrides in Edit Model dialog

## Version 0.12
- Fixed tab notifications not showing

## Version 0.11
- Installer updates
- Fixed texture toggle mode

## Version 0.1
- Switched 3D viewer to PyVista
- Full restart option for ComfyUI workflow presets
- Embedded viewer with async loading and video support
- Settings tab now shows version history and info
- Trellis 2 and Ultrashape support
- Version tracking and changelog system added
