"""
Luma Shot Tools - Main Application (Refactored).

VFX shot management application for the Luma Animation pipeline.
Handles render pass management, AYON publishing, Deadline farm submission,
and lookdev file cleanup for shot-based workflows.
"""

import sys
import os
import ctypes

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # Parent directory of 'python'

# Add paths - support both Windows network paths and local development
sys.path.append(r"L:\tools\_studio_tools\luma_tools\python")
sys.path.append(r"L:\tools\_studio_tools\luma_tools\resources\ui")

# Also add local paths for development/testing
sys.path.append(os.path.join(PROJECT_ROOT, "python"))
sys.path.append(os.path.join(PROJECT_ROOT, "resources", "ui"))

# PySide2 imports
from PySide2 import QtCore, QtUiTools, QtWidgets
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

# Import our modular services
from config import UI_FILE_PATH, QDARKSTYLE_PATH, CUSTOM_STYLE_PATH, ICON_PATH, APP_ID, APP_TITLE
from utils import get_trailing_number, remove_after, get_folder_size
from file_operations import (
    find_renders,
    find_hip_files,
    find_comp_files,
    read_comp_file,
    get_lookdev_directory,
    get_comp_directory,
    fast_scandir
)
from render_service import (
    detect_passes,
    load_pass_config,
    save_pass_config,
    get_pass_file_path
)
from cleanup_service import cleanup_renders, cleanup_usd, cleanup_hip_backups
from pass_builder import pass_builder
from mp4_maker import generate_mp4, get_output_filename

# Import animation and loading modules
try:
    from ui_animations import enhance_ui, StatusColors
    from loading_overlay import InlineSpinner
    from splash_screen import SplashScreen
    ANIMATIONS_ENABLED = True
except ImportError:
    ANIMATIONS_ENABLED = False
    print("ui_animations/loading_overlay modules not found - animations disabled")


# ============================================================================
# GLOBAL STATE (to be refactored later)
# ============================================================================
jobname = sys.argv[1]
shot = sys.argv[2]
task = sys.argv[3]
shotpath = sys.argv[4]
user = sys.argv[5]
output_subdirectory = sys.argv[6]

print("Full command: " + str(sys.argv))
print(f"jobname = {jobname}")
print(f"shot = {shot}")
print(f"task = {task}")
print(f"shotpath = {shotpath}")
print(f"user = {user}")
print(f"output_subdirectory = {output_subdirectory}")

# Application state
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

# Global variables (kept for backward compatibility)
renders = []
channels = {}
WorkingDir = ""
currentrender = ""
passesfile = ""
lookdevDir = ""
latestrender = ""
searchpath = ""
startframe = 0
endframe = 0

# MP4 Maker global variables
mp4_renders = []
mp4_searchpath = ""
mp4_custom_path = ""
mp4_startframe = 0
mp4_endframe = 0
mp4_output_path = ""

# Set up Windows things
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


# ============================================================================
# MAIN WINDOW CLASS
# ============================================================================

class LogStream(QtCore.QObject):
    """Custom stream that redirects output to the log widget."""
    message_written = QtCore.Signal(str)

    def __init__(self):
        super(LogStream, self).__init__()

    def write(self, message):
        if message.strip():  # Only emit non-empty messages
            self.message_written.emit(message)

    def flush(self):
        pass


class LumaShotTools(QtWidgets.QWidget):
    """Main application window."""

    change_val = QtCore.Signal(int)

    def __init__(self, parent=None):
        super(LumaShotTools, self).__init__()

        # Load UI
        self.ui = QtUiTools.QUiLoader().load(UI_FILE_PATH, parentWidget=self)
        self.parent = parent
        self.change_val[int].connect(self.set_progress_val)
        self.setWindowTitle(f"{APP_TITLE} - {shot}")
        self.setWindowIcon(QIcon(ICON_PATH))

        # Setup log redirection
        self.log_stream = LogStream()
        self.log_stream.message_written.connect(self.append_log)
        sys.stdout = self.log_stream
        sys.stderr = self.log_stream

        # Set window size from UI file and make it resizable
        self.resize(self.ui.size())
        self.setMinimumSize(self.ui.minimumSize())

        # Load QDarkStyle as base theme
        file = QFile(QDARKSTYLE_PATH)
        file.open(QFile.ReadOnly | QFile.Text)
        stream = QTextStream(file)
        base_style = stream.readAll()
        file.close()

        # Load custom stylesheet enhancements
        custom_file = QFile(CUSTOM_STYLE_PATH)
        custom_file.open(QFile.ReadOnly | QFile.Text)
        custom_stream = QTextStream(custom_file)
        custom_style = custom_stream.readAll()
        custom_file.close()

        # Apply combined stylesheet (custom style overrides base)
        app.setStyleSheet(base_style + "\n" + custom_style)
        print(f"Loaded custom stylesheet from: {CUSTOM_STYLE_PATH}")

        # Setup animations
        if ANIMATIONS_ENABLED:
            self.animator = enhance_ui(self)
            print("UI animations enabled")

            # Create inline spinner for pass detection
            self.passes_spinner = InlineSpinner(self.ui.passesGroupBox, size=20)
            # Position will be set in showEvent when widget is fully laid out
            print("Inline spinner created for pass detection")
        else:
            print("UI animations disabled")

        # Connect signals
        self._connect_signals()

        # Initialize UI state
        self.ui.OverrideHou.setChecked(True)
        self.ui.BuildPasses.setEnabled(False)

    def showEvent(self, event):
        """Override showEvent to position spinner after window is laid out."""
        super().showEvent(event)
        # Position the spinner after the UI is fully laid out
        if ANIMATIONS_ENABLED and hasattr(self, 'passes_spinner'):
            self._position_spinner()

    def _position_spinner(self):
        """Position the inline spinner in the top-right of the passes group box."""
        if hasattr(self, 'passes_spinner') and hasattr(self.ui, 'passesGroupBox'):
            # Position in top-right corner with some padding
            x = self.ui.passesGroupBox.width() - 30
            y = 5
            self.passes_spinner.move(x, y)

    def _connect_signals(self):
        """Connect all UI signals to handlers."""
        # Pass Builder tab
        self.ui.ScanRenders.clicked.connect(self.on_scan_renders_clicked)
        self.ui.RendersList.itemSelectionChanged.connect(self.on_render_selection_changed)
        self.ui.BuildPasses.pressed.connect(self.on_build_passes_clicked)
        self.ui.CurrentVer.valueChanged.connect(self.on_scan_renders_clicked)

        # MP4 Maker tab
        self.ui.MP4ScanRenders.clicked.connect(self.on_mp4_scan_renders_clicked)
        self.ui.MP4CurrentVer.valueChanged.connect(self.on_mp4_scan_renders_clicked)
        self.ui.MP4UseDenoised.toggled.connect(self.on_mp4_source_changed)
        self.ui.MP4UseForComp.toggled.connect(self.on_mp4_source_changed)
        self.ui.MP4UseRaw.toggled.connect(self.on_mp4_source_changed)
        self.ui.MP4UseCustom.toggled.connect(self.on_mp4_source_changed)
        self.ui.MP4BrowseCustomPath.clicked.connect(self.on_mp4_browse_custom_path_clicked)
        self.ui.MP4RendersList.itemSelectionChanged.connect(self.on_mp4_render_selection_changed)
        self.ui.MP4BrowseOutput.clicked.connect(self.on_mp4_browse_output_clicked)
        self.ui.MP4Generate.clicked.connect(self.on_mp4_generate_clicked)

        # Shot Cleaner tab
        self.ui.RescanCleanFiles.clicked.connect(self.run_scanner)
        self.ui.CleanFiles.clicked.connect(self.on_clean_files_clicked)

        # Settings tab
        self.ui.ClearLogButton.clicked.connect(self.on_clear_log_clicked)

    @QtCore.Slot(int)
    def set_progress_val(self, val):
        """Update progress bar value."""
        self.ui.progressBar.setValue(val)
        QApplication.processEvents()

    @QtCore.Slot(str)
    def append_log(self, message):
        """Append a message to the log output widget."""
        self.ui.LogOutput.append(message.rstrip())
        # Auto-scroll to bottom
        self.ui.LogOutput.verticalScrollBar().setValue(
            self.ui.LogOutput.verticalScrollBar().maximum()
        )

    def on_clear_log_clicked(self):
        """Clear the log output."""
        self.ui.LogOutput.clear()

    # ========================================================================
    # RENDER TAB HANDLERS
    # ========================================================================

    def on_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        global renders, searchpath

        self.ui.RendersList.clear()
        self.ui.Passes.clear()

        # Build search path
        searchpath = self.ui.RenderPath.text()
        currentver = get_trailing_number(searchpath)
        paddedcurrentver = '{:03d}'.format(int(currentver))
        split_path = searchpath.rsplit("_", 1)
        searchpath = split_path[0] + r"_" + split_path[1].replace(paddedcurrentver, "")[-1]
        newver = self.ui.CurrentVer.value()
        paddednewver = '{:03d}'.format(newver)
        searchpath += paddednewver
        self.ui.RenderPath.setText(searchpath)

        # Find renders
        renders = find_renders(searchpath)
        self.ui.BuildPasses.setEnabled(False)

        if len(renders) > 0:
            for render_seq in renders:
                self.ui.RendersList.addItem(str(render_seq).split("\\")[-1])
            self.ui.RendersList.setEnabled(True)
        else:
            self.ui.RendersList.addItem("No Renders Found")
            self.ui.RendersList.setEnabled(False)

    def on_render_selection_changed(self):
        """Update passes when selected render changes."""
        global startframe, endframe, currentrender, passesfile

        sel0 = self.ui.RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(renders):
            return

        index = sel0
        startframe = renders[index].start()
        endframe = renders[index].end()
        framename = renders[index].frame(startframe)
        filename = os.path.basename(framename)
        currentrender = filename.split(".")[0]
        denoisedpath = os.path.dirname(framename) + f"\{filename}"

        # Find passes (shows inline spinner automatically)
        self._detect_passes(denoisedpath)

        # Select previously saved passes
        passesfile = get_pass_file_path(WorkingDir, currentrender)
        self._select_saved_passes(passesfile)

    def _detect_passes(self, render_file):
        """Detect passes in render file with spinner animation."""
        global channels

        self.ui.Passes.clear()

        # Show inline spinner
        if ANIMATIONS_ENABLED and hasattr(self, 'passes_spinner'):
            self.passes_spinner.start()

        QApplication.processEvents()

        # Detect passes using service
        channels = detect_passes(render_file)

        # Hide spinner
        if ANIMATIONS_ENABLED and hasattr(self, 'passes_spinner'):
            self.passes_spinner.stop()

        # Add passes to list
        for key in channels.keys():
            self.ui.Passes.addItem(key)

        # Enable build button
        if len(channels) >= 1:
            self.ui.BuildPasses.setEnabled(True)
            if ANIMATIONS_ENABLED:
                self.animator.pulse_button(self.ui.BuildPasses)
        else:
            self.ui.BuildPasses.setEnabled(False)

    def _select_saved_passes(self, passes_file):
        """Select previously saved passes in the UI."""
        selectedpasses = load_pass_config(passes_file)
        if selectedpasses:
            for pass_name in list(selectedpasses):
                matching_items = self.ui.Passes.findItems(pass_name, Qt.MatchEndsWith)
                for item in matching_items:
                    item.setSelected(True)

    # ========================================================================
    # PASS BUILDING HANDLERS
    # ========================================================================

    def on_build_passes_clicked(self):
        """Build render files with selected passes."""
        # Show loading overlay IMMEDIATELY
        QApplication.processEvents()
        window.repaint()
        if ANIMATIONS_ENABLED:
            window.animator.show_loading(
                "Submitting Render Passes",
                "Preparing to build...",
                show_progress=True
            )
            # Force immediate UI update
            QApplication.processEvents()
            window.repaint()

            # Add click animation after overlay is shown
            self.animator.animate_button_click(self.ui.BuildPasses)
            QApplication.processEvents()

        try:
            # Phase 1: Collect selected passes
            if ANIMATIONS_ENABLED:
                self.animator.update_loading_message(
                    "Submitting Render Passes",
                    "Collecting selected passes..."
                )
                self.animator.update_loading_progress(5)
            QApplication.processEvents()

            channellist = []
            for item in self.ui.Passes.selectedItems():
                channellist.append(item.text())

            final_channels = dict((k, channels[k]) for k in channellist if k in channels)

            # Phase 2: Write pass configuration
            if ANIMATIONS_ENABLED:
                self.animator.update_loading_message(
                    "Submitting Render Passes",
                    "Writing pass configuration file..."
                )
                self.animator.update_loading_progress(15)
            QApplication.processEvents()

            self._write_pass_config(final_channels)

            # Phase 3: Submit to farm or build locally
            build_location = "farm" if self.ui.BuildType.currentIndex() == 0 else "local"

            if ANIMATIONS_ENABLED:
                self.animator.update_loading_message(
                    "Submitting Render Passes",
                    f"Submitting to {build_location}..."
                )
                self.animator.update_loading_progress(25)
            QApplication.processEvents()

            # Execute build with progress callback
            use_farm = (self.ui.BuildType.currentIndex() == 0)

            pass_builder.build_passes(
                passes_file=passesfile,
                renders_path=searchpath,
                start_frame=startframe,
                end_frame=endframe,
                use_farm=use_farm,
                project_name=jobname,
                shot=shot,
                parent_job_id="NONE",
                task=task,
                user=user,
                output_subdirectory=output_subdirectory,
                do_publish=True,
                progress_callback=self._build_progress_callback
            )

            # Phase 4: Complete
            if ANIMATIONS_ENABLED:
                self.animator.update_loading_message(
                    "Submitting Render Passes",
                    "Build complete!"
                )
                self.animator.update_loading_progress(100)
            QApplication.processEvents()

            # Small delay to show completion
            QTimer.singleShot(500, lambda: self._finish_build_success())

        except Exception as e:
            # Handle errors
            if ANIMATIONS_ENABLED:
                self.animator.hide_loading()
                self.animator.update_status_animated(
                    f"Build failed: {str(e)}",
                    StatusColors.ERROR
                )
            else:
                self.ui.StatusLabel.setText(f"Build failed: {str(e)}")
            print(f"Build error: {e}")

    def _build_progress_callback(self, progress, message):
        """Callback for build progress updates from pass_builder."""
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message("Submitting Render Passes", message)
            self.animator.update_loading_progress(progress)

    def _write_pass_config(self, passes_dictionary):
        """Write pass configuration to file."""
        save_pass_config(passesfile, passes_dictionary)
        self._write_settings_file()

    def _write_settings_file(self):
        """Write shot settings file."""
        import json
        settings = {}
        settings['overridehou'] = self.ui.OverrideHou.isChecked()

        shot_data_dir = os.path.join(WorkingDir, "shot_data")
        os.makedirs(shot_data_dir, exist_ok=True)

        settings_file = os.path.join(shot_data_dir, 'shot_settings.json')
        with open(settings_file, 'w') as fp:
            json.dump(settings, fp)

    def _finish_build_success(self):
        """Called after successful build to show completion message."""
        if ANIMATIONS_ENABLED:
            self.animator.hide_loading()
            self.animator.update_status_animated(
                "Render build complete!",
                StatusColors.SUCCESS
            )
        else:
            self.ui.StatusLabel.setText("Farm Submission complete!")

    # ========================================================================
    # MP4 MAKER TAB HANDLERS
    # ========================================================================

    def on_mp4_source_changed(self):
        """Handle source type change - enable/disable custom path button and trigger scan."""
        # Enable/disable custom path browse button
        is_custom = self.ui.MP4UseCustom.isChecked()
        self.ui.MP4BrowseCustomPath.setEnabled(is_custom)

        # Trigger scan
        self.on_mp4_scan_renders_clicked()

    def on_mp4_browse_custom_path_clicked(self):
        """Browse for custom directory containing image sequences."""
        global mp4_custom_path

        # Default to user's Videos folder
        default_dir = os.path.join(os.path.expanduser("~"), "Videos")

        # Open directory dialog
        custom_dir = QFileDialog.getExistingDirectory(
            None,
            "Select Directory with Image Sequence",
            default_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if custom_dir:
            mp4_custom_path = custom_dir
            self.ui.MP4CustomPathLabel.setText(mp4_custom_path)
            self.ui.MP4CustomPathLabel.setStyleSheet("color: white; font-size: 9pt;")
            print(f"MP4 Maker: Custom path set to: {mp4_custom_path}")

            # Trigger scan
            self.on_mp4_scan_renders_clicked()

    def on_mp4_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        global mp4_renders, mp4_searchpath

        self.ui.MP4RendersList.clear()

        # Build search path (same logic as Pass Builder)
        mp4_searchpath = self.ui.MP4RenderPath.text()

        # Handle version change
        if mp4_searchpath:
            currentver = get_trailing_number(mp4_searchpath)
            paddedcurrentver = '{:03d}'.format(int(currentver))
            split_path = mp4_searchpath.rsplit("_", 1)
            mp4_searchpath = split_path[0] + r"_" + split_path[1].replace(paddedcurrentver, "")[-1]
            newver = self.ui.MP4CurrentVer.value()
            paddednewver = '{:03d}'.format(newver)
            mp4_searchpath += paddednewver
            self.ui.MP4RenderPath.setText(mp4_searchpath)

        # Update "For Comp" radio button label with actual subdirectory name
        self.ui.MP4UseForComp.setText(output_subdirectory.title())

        # Determine which source to scan based on radio buttons
        mp4_renders = []
        self.ui.MP4Generate.setEnabled(False)

        print(f"MP4 Maker: Scanning path: {mp4_searchpath}")

        if self.ui.MP4UseDenoised.isChecked():
            # Check for renders in denoised subdirectory
            denoised_path = os.path.join(mp4_searchpath, "denoised")
            print(f"MP4 Maker: Scanning denoised path: {denoised_path}")
            if os.path.exists(denoised_path):
                # Use fileseq directly instead of find_renders which hardcodes denoised subdirectory
                import fileseq
                search_pattern = os.path.join(denoised_path, "*.exr")
                print(f"MP4 Maker: Search pattern: {search_pattern}")
                denoised_renders = list(fileseq.findSequencesOnDisk(search_pattern))
                print(f"MP4 Maker: Found {len(denoised_renders)} renders in denoised")
                for render_seq in denoised_renders:
                    mp4_renders.append(("denoised", render_seq))
            else:
                print(f"MP4 Maker: Denoised path does not exist")

        elif self.ui.MP4UseForComp.isChecked():
            # Check for renders in for_comp subdirectory
            for_comp_path = os.path.join(mp4_searchpath, output_subdirectory)
            print(f"MP4 Maker: Scanning {output_subdirectory} path: {for_comp_path}")
            if os.path.exists(for_comp_path):
                # Use fileseq directly instead of find_renders which hardcodes denoised subdirectory
                import fileseq
                search_pattern = os.path.join(for_comp_path, "*.exr")
                print(f"MP4 Maker: Search pattern: {search_pattern}")
                for_comp_renders = list(fileseq.findSequencesOnDisk(search_pattern))
                print(f"MP4 Maker: Found {len(for_comp_renders)} renders in {output_subdirectory}")
                for render_seq in for_comp_renders:
                    mp4_renders.append((output_subdirectory, render_seq))
            else:
                print(f"MP4 Maker: {output_subdirectory} path does not exist")

        elif self.ui.MP4UseRaw.isChecked():
            # Check root path (for raw/non-denoised renders)
            print(f"MP4 Maker: Scanning raw render path: {mp4_searchpath}")
            if os.path.exists(mp4_searchpath):
                # Use fileseq directly instead of find_renders which hardcodes denoised subdirectory
                import fileseq
                search_pattern = os.path.join(mp4_searchpath, "*.exr")
                print(f"MP4 Maker: Search pattern: {search_pattern}")
                root_renders = list(fileseq.findSequencesOnDisk(search_pattern))
                print(f"MP4 Maker: Found {len(root_renders)} renders in root")
                for render_seq in root_renders:
                    mp4_renders.append(("raw", render_seq))
            else:
                print(f"MP4 Maker: Raw render path does not exist")

        elif self.ui.MP4UseCustom.isChecked():
            # Check custom path
            print(f"MP4 Maker: Scanning custom path: {mp4_custom_path}")
            if mp4_custom_path and os.path.exists(mp4_custom_path):
                # Use fileseq directly to find all EXR sequences
                import fileseq
                search_pattern = os.path.join(mp4_custom_path, "*.exr")
                print(f"MP4 Maker: Search pattern: {search_pattern}")
                custom_renders = list(fileseq.findSequencesOnDisk(search_pattern))
                print(f"MP4 Maker: Found {len(custom_renders)} renders in custom path")
                for render_seq in custom_renders:
                    mp4_renders.append(("custom", render_seq))
            elif not mp4_custom_path:
                print(f"MP4 Maker: No custom path selected - please browse to a directory")
            else:
                print(f"MP4 Maker: Custom path does not exist: {mp4_custom_path}")

        # Populate list
        print(f"MP4 Maker: Total renders found: {len(mp4_renders)}")
        if len(mp4_renders) > 0:
            for subdir, render_seq in mp4_renders:
                # Get just the filename
                full_path = str(render_seq).split("\\")
                display_name = full_path[-1]
                self.ui.MP4RendersList.addItem(display_name)
            self.ui.MP4RendersList.setEnabled(True)
        else:
            self.ui.MP4RendersList.addItem("No Renders Found")
            self.ui.MP4RendersList.setEnabled(False)

    def on_mp4_render_selection_changed(self):
        """Update MP4 state when selected render changes."""
        global mp4_startframe, mp4_endframe, mp4_output_path

        sel0 = self.ui.MP4RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(mp4_renders):
            self.ui.MP4Generate.setEnabled(False)
            return

        index = sel0
        # mp4_renders is now a list of tuples: (subdir, render_seq)
        subdir, render_seq = mp4_renders[index]
        mp4_startframe = render_seq.start()
        mp4_endframe = render_seq.end()

        print(f"MP4 Maker: Selected render from '{subdir}' - frames {mp4_startframe} to {mp4_endframe}")

        # Automatically set output path to user's Videos folder
        framename = render_seq.frame(render_seq.start())
        filename = os.path.basename(framename)
        render_name = filename.split(".")[0]
        default_filename = get_output_filename(render_name, shot)
        videos_folder = os.path.join(os.path.expanduser("~"), "Videos")
        mp4_output_path = os.path.join(videos_folder, default_filename)

        # Update UI
        self.ui.MP4OutputPath.setText(mp4_output_path)
        self.ui.MP4OutputPath.setStyleSheet("color: white; font-size: 9pt;")

        # Enable generate button
        self.ui.MP4Generate.setEnabled(True)
        if ANIMATIONS_ENABLED:
            self.animator.pulse_button(self.ui.MP4Generate)

    def on_mp4_browse_output_clicked(self):
        """Browse for MP4 output location."""
        global mp4_output_path

        # Get current render name for default filename
        sel0 = self.ui.MP4RendersList.currentRow()
        default_filename = f"{shot}_preview.mp4"

        if sel0 >= 0 and sel0 < len(mp4_renders):
            # mp4_renders is now a list of tuples: (subdir, render_seq)
            subdir, render_seq = mp4_renders[sel0]
            framename = render_seq.frame(render_seq.start())
            filename = os.path.basename(framename)
            render_name = filename.split(".")[0]
            default_filename = get_output_filename(render_name, shot)

        # Open file dialog with default location in user's Videos folder
        output_file, _ = QFileDialog.getSaveFileName(
            None,
            "Save MP4 As",
            os.path.join(os.path.expanduser("~"), "Videos", default_filename),
            "MP4 Video (*.mp4)"
        )

        if output_file:
            mp4_output_path = output_file
            self.ui.MP4OutputPath.setText(mp4_output_path)
            self.ui.MP4OutputPath.setStyleSheet("color: white; font-size: 9pt;")

            # Enable generate button if render is selected
            if self.ui.MP4RendersList.currentRow() >= 0:
                self.ui.MP4Generate.setEnabled(True)
                if ANIMATIONS_ENABLED:
                    self.animator.pulse_button(self.ui.MP4Generate)

    def on_mp4_generate_clicked(self):
        """Generate MP4 from selected render."""
        # Show loading overlay
        if ANIMATIONS_ENABLED:
            window.animator.show_loading(
                "Generating MP4",
                "Preparing to convert...",
                show_progress=True
            )
            QApplication.processEvents()
            window.repaint()
            self.animator.animate_button_click(self.ui.MP4Generate)
            QApplication.processEvents()

        try:
            # Get selected render
            sel0 = self.ui.MP4RendersList.currentRow()
            if sel0 < 0 or sel0 >= len(mp4_renders):
                raise ValueError("No render selected")

            # Phase 1: Get render info
            if ANIMATIONS_ENABLED:
                self.animator.update_loading_message(
                    "Generating MP4",
                    "Analyzing render sequence..."
                )
                self.animator.update_loading_progress(5)
            QApplication.processEvents()

            # mp4_renders is now a list of tuples: (subdir, render_seq)
            subdir, render_seq = mp4_renders[sel0]
            framename = render_seq.frame(mp4_startframe)

            # Build input pattern for ffmpeg
            # Convert from fileseq format to ffmpeg format
            base_dir = os.path.dirname(framename)
            base_filename = os.path.basename(framename)
            # Replace frame number with ffmpeg pattern
            parts = base_filename.split(".")
            if len(parts) >= 3:
                # Format: name.####.exr
                input_pattern = os.path.join(base_dir, f"{parts[0]}.%04d.exr")
            else:
                raise ValueError(f"Unexpected filename format: {base_filename}")

            # Phase 2: Get settings
            if ANIMATIONS_ENABLED:
                self.animator.update_loading_message(
                    "Generating MP4",
                    "Configuring conversion settings..."
                )
                self.animator.update_loading_progress(8)
            QApplication.processEvents()

            quality_index = self.ui.MP4Quality.currentIndex()
            burn_in_timecode = self.ui.MP4BurnInTimecode.isChecked()

            # Phase 3: Generate MP4
            success = generate_mp4(
                input_pattern,
                mp4_output_path,
                mp4_startframe,
                mp4_endframe,
                quality_index=quality_index,
                burn_in_timecode=burn_in_timecode,
                progress_callback=self._mp4_progress_callback
            )

            # Phase 4: Complete
            if success:
                if ANIMATIONS_ENABLED:
                    self.animator.update_loading_message(
                        "Generating MP4",
                        "MP4 generation complete!"
                    )
                    self.animator.update_loading_progress(100)
                QApplication.processEvents()

                # Small delay to show completion
                QTimer.singleShot(500, lambda: self._finish_mp4_success())
            else:
                raise RuntimeError("MP4 generation failed")

        except Exception as e:
            # Handle errors
            if ANIMATIONS_ENABLED:
                self.animator.hide_loading()
                self.animator.update_status_animated(
                    f"MP4 generation failed: {str(e)}",
                    StatusColors.ERROR
                )
            else:
                self.ui.StatusLabel.setText(f"MP4 generation failed: {str(e)}")
            print(f"MP4 generation error: {e}")

    def _mp4_progress_callback(self, progress, message):
        """Callback for MP4 generation progress updates."""
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message("Generating MP4", message)
            self.animator.update_loading_progress(progress)

    def _finish_mp4_success(self):
        """Called after successful MP4 generation to show completion message."""
        if ANIMATIONS_ENABLED:
            self.animator.hide_loading()
            self.animator.update_status_animated(
                f"MP4 generated: {os.path.basename(mp4_output_path)}",
                StatusColors.SUCCESS
            )
        else:
            self.ui.StatusLabel.setText(f"MP4 generated: {os.path.basename(mp4_output_path)}")

    # ========================================================================
    # CLEANUP TAB HANDLERS
    # ========================================================================

    def on_clean_files_clicked(self):
        """Handle cleanup button click."""
        if ANIMATIONS_ENABLED:
            self.animator.animate_button_click(self.ui.CleanFiles)

        # Cleanup renders
        if self.ui.CleanRender.isChecked():
            render_dirs = [item.text() for item in self.ui.RendersClean.selectedItems()]
            if render_dirs:
                count = 0
                for dir_name in render_dirs:
                    count += 1
                    status_msg = f"Removing Renders: {lookdevDir}\\img\\renders\\{dir_name}"
                    if ANIMATIONS_ENABLED:
                        self.animator.update_status_animated(status_msg, StatusColors.WARNING)
                    else:
                        self.ui.StatusLabel.setText(status_msg)
                    print(status_msg)
                    self.change_val.emit(int(count / len(render_dirs) * 100))
                    QApplication.processEvents()

                cleanup_renders(lookdevDir, render_dirs)

        # Cleanup USD
        if self.ui.CleanUSD.isChecked():
            usd_dirs = [item.text() for item in self.ui.USDSClean.selectedItems()]
            if usd_dirs:
                count = 0
                for dir_name in usd_dirs:
                    count += 1
                    self.change_val.emit(int(count / len(usd_dirs) * 100))
                    status_msg = f"Removing USDs: {lookdevDir}\\usd_files\\{dir_name}"
                    if ANIMATIONS_ENABLED:
                        self.animator.update_status_animated(status_msg, StatusColors.WARNING)
                    else:
                        self.ui.StatusLabel.setText(status_msg)
                    QApplication.processEvents()
                    print(status_msg)

                cleanup_usd(lookdevDir, usd_dirs)

        # Cleanup HIP backups
        if self.ui.HIPBackups.isChecked():
            self.change_val.emit(0)
            status_msg = f"Removing Hip Backups Folder: {lookdevDir}\\backup\\"
            if ANIMATIONS_ENABLED:
                self.animator.update_status_animated(status_msg, StatusColors.WARNING)
            else:
                self.ui.StatusLabel.setText(status_msg)

            cleanup_hip_backups(lookdevDir)
            self.change_val.emit(100)
            QApplication.processEvents()

        # Final status
        if ANIMATIONS_ENABLED:
            self.animator.update_status_animated("Cleanup Done", StatusColors.SUCCESS)
        else:
            self.ui.StatusLabel.setText("Cleanup Done")

        self.run_scanner()

    # ========================================================================
    # DIRECTORY SCANNER
    # ========================================================================

    def run_scanner(self):
        """Scan directories for renders, USD, HIP files, and comps."""
        global lookdevDir, WorkingDir, latestrender

        # Show loading overlay
        if ANIMATIONS_ENABLED:
            self.animator.show_loading(
                "Scanning Directories",
                "Initializing scan...",
                show_progress=True
            )
        QApplication.processEvents()

        self.ui.CleanFiles.setEnabled(False)
        self.ui.USDSClean.clear()
        self.ui.RendersClean.clear()

        # Get lookdev directory
        lookdevDir = get_lookdev_directory(shotpath)
        print(f"lookdev Dir: {lookdevDir}")

        # ====================================================================
        # FIND RENDER DIRECTORY
        # ====================================================================
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message(
                "Scanning Render Files",
                "Searching for render directories..."
            )

        try:
            dirs = fast_scandir(lookdevDir)
        except:
            dirs = ()
            print("No Renders Found")

        render_folders = []
        RenderDirectory = ""

        if len(dirs) > 0:
            for i in dirs:
                if r"lookdev\img\renders" in i:
                    render_folders.append(i)

            try:
                RenderDirectory = render_folders[0]
                RenderDirectory = remove_after(RenderDirectory, r"lookdev\img\renders")
                self.ui.Renderlabel.setText(f'Render Directory Found: {RenderDirectory}')
                QApplication.processEvents()
            except:
                self.ui.RendersList.setEnabled(False)
                print("No Renders Found!")
        else:
            self.ui.Renderlabel.setText('Render Directory Not Found!')
            QApplication.processEvents()
            self.ui.CleanRender.setEnabled(False)
            self.ui.CleanRender.setChecked(False)

        # ====================================================================
        # FIND USD DIRECTORY
        # ====================================================================
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message(
                "Scanning USD Files",
                "Searching for USD directories..."
            )

        try:
            dirs = fast_scandir(lookdevDir)
        except:
            dirs = ()

        usd_folders = []
        USDDirectory = ""

        if len(dirs) > 0:
            for i in dirs:
                if r"lookdev\usd_files" in i:
                    usd_folders.append(i)

            try:
                USDDirectory = usd_folders[0]
                USDDirectory = remove_after(USDDirectory, r"lookdev\usd_files")
                self.ui.USDlabel.setText(f'USD Directory Found: {USDDirectory}')
                QApplication.processEvents()
            except:
                USDDirectory = ""
                print("No USDs Found!")
        else:
            USDDirectory = ""
            self.ui.USDlabel.setText('USD Directory Not Found!')
            self.ui.CleanUSD.setEnabled(False)
            self.ui.CleanUSD.setChecked(False)
            QApplication.processEvents()

        # ====================================================================
        # FIND HIPS
        # ====================================================================
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message(
                "Scanning HIP Files",
                "Searching for Houdini project files..."
            )
            self.animator.update_loading_progress(34)

        hipfiles = find_hip_files(lookdevDir)
        hipcount = len(hipfiles)
        self.ui.HipNumber.setText(f'Amount of Hipfiles: {hipcount}')

        HipFile = ""
        if hipcount > 0:
            sorted(hipfiles)
            HipFile = hipfiles[0]
            temp = HipFile.rsplit("_", 1)
            HipFile = temp[0]
            self.ui.HIPlabel.setText(f'HIP Found: {HipFile}')
            QApplication.processEvents()
        else:
            self.ui.HIPlabel.setText('HIPS Not Found!')
            QApplication.processEvents()

        # ====================================================================
        # RENDER FILES
        # ====================================================================
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message(
                "Processing Render Files",
                "Organizing render versions..."
            )
            self.animator.update_loading_progress(50)

        FoundRenderFiles = []
        WorkingDir = ""

        if RenderDirectory != "":
            WorkingDir = remove_after(RenderDirectory, "lookdev")
            Renderdir = sorted(next(os.walk(RenderDirectory))[1])
            QApplication.processEvents()

            if len(Renderdir) < 2:
                self.ui.LatestRender.setText("Latest Render: None")

            for dir_name in Renderdir:
                if HipFile in dir_name:
                    FoundRenderFiles.append(dir_name)
                    self.ui.RendersClean.addItem(str(dir_name))
                    self.ui.RendersClean.scrollToBottom()
                    QApplication.processEvents()

            if FoundRenderFiles:
                # Find the latest version that has renders (not empty)
                latestrender = None
                for render_version in reversed(FoundRenderFiles):
                    # Check if this version has renders in the denoised folder
                    version_path = os.path.join(RenderDirectory, render_version)
                    test_renders = find_renders(version_path)
                    if len(test_renders) > 0:
                        latestrender = render_version
                        break

                # If we found a version with renders, use it
                if latestrender:
                    FoundRenderFiles.remove(latestrender)
                    self.ui.LatestRender.setText(f"Latest Render: {latestrender}")
                    latestver = get_trailing_number(latestrender)
                    self.ui.CurrentVer.setRange(0, int(latestver))
                else:
                    # No versions have renders - fall back to latest version
                    latestrender = FoundRenderFiles[-1]
                    FoundRenderFiles.pop(-1)
                    self.ui.LatestRender.setText(f"Latest Render: {latestrender} (empty)")
                    latestver = get_trailing_number(latestrender)
                    self.ui.CurrentVer.setRange(0, int(latestver))
                QApplication.processEvents()

        # ====================================================================
        # USD FILES
        # ====================================================================
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message(
                "Processing USD Files",
                "Organizing USD versions..."
            )
            self.animator.update_loading_progress(66)

        FoundUSDFiles = []
        if USDDirectory:
            USDdir = sorted(next(os.walk(USDDirectory))[1])
            QApplication.processEvents()

            for dir_name in USDdir:
                FoundUSDFiles.append(dir_name)
                self.ui.USDSClean.addItem(str(dir_name))
                self.ui.USDSClean.scrollToBottom()
                QApplication.processEvents()

            if len(FoundUSDFiles) > 0:
                latestUSD = FoundUSDFiles[-1]
                FoundUSDFiles.pop(-1)
                self.ui.LatestUSD.setText(f"Latest USD: {latestUSD}")
                self.ui.USDSClean.scrollToBottom()
                QApplication.processEvents()
                self.ui.CleanFiles.setEnabled(True)
            else:
                self.ui.LatestUSD.setText("Latest USD: None")
                QApplication.processEvents()

        # Set render path
        if RenderDirectory != "":
            searchpath = RenderDirectory + "\\" + latestrender
            self.ui.RenderPath.setText(searchpath)
            currentver = get_trailing_number(latestrender)
            self.ui.CurrentVer.setValue(int(currentver))

        # Find renders
        try:
            self.on_scan_renders_clicked()
        except:
            self.ui.LatestRender.setText("Latest Render: None")
            self.ui.StatusLabel.setText('Cant find any renders')

        # Calculate folder size
        try:
            if ANIMATIONS_ENABLED:
                self.animator.update_loading_message(
                    "Calculating Size",
                    "Computing total directory size..."
                )
                self.animator.update_loading_progress(75)

            QApplication.processEvents()
            TotalSize = get_folder_size(lookdevDir)
            self.ui.FolderSize.setText(f"Total Size: {str(TotalSize)}")
            QApplication.processEvents()
        except:
            self.ui.FolderSize.setText('Error calculating Size')
            self.ui.StatusLabel.setText('Error calculating Size')

        # ====================================================================
        # FIND COMPS
        # ====================================================================
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message(
                "Scanning Comp Files",
                "Searching for composition files..."
            )
            self.animator.update_loading_progress(85)

        CompDir = get_comp_directory(shotpath)

        try:
            dirs = fast_scandir(CompDir)
        except:
            dirs = ()

        comp_folders = []

        if len(dirs) > 0:
            for i in dirs:
                if r"Compositing" in i:
                    comp_folders.append(i)

            try:
                CompDirectory = comp_folders[0]
                CompDirectory = remove_after(CompDirectory, r"\Compositing" + "\\")
                comps = sorted(find_comp_files(CompDirectory))
                latestcomp = comps[-1]
                self.ui.Complabel.setText(f'Latest Comp Found: {CompDirectory + latestcomp}')

                # Read comp file and deselect renders in use
                renders_in_comp = read_comp_file(CompDirectory + latestcomp, HipFile)
                self._deselect_renders_in_comp(renders_in_comp)
                QApplication.processEvents()
            except:
                print("No Comp Dir Found!")
        else:
            self.ui.Complabel.setText('Comp Directory Not Found!')
            QApplication.processEvents()

        # ====================================================================
        # INITIALIZE MP4 MAKER TAB
        # ====================================================================
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_message(
                "Initializing MP4 Maker",
                "Setting up MP4 Maker tab..."
            )
            self.animator.update_loading_progress(95)

        # Set MP4 render path to same as pass builder
        if RenderDirectory != "":
            self.ui.MP4RenderPath.setText(searchpath)
            currentver = get_trailing_number(latestrender)
            self.ui.MP4CurrentVer.setValue(int(currentver))
            self.ui.MP4CurrentVer.setRange(0, int(currentver))

        # Final progress
        if ANIMATIONS_ENABLED:
            self.animator.update_loading_progress(100)
            self.animator.hide_loading()
            self.animator.update_status_animated('Scanning Complete!', StatusColors.SUCCESS)
        else:
            self.ui.StatusLabel.setText('Scanning Done')

        self.ui.CleanFiles.setEnabled(True)

    def _deselect_renders_in_comp(self, renders_in_comp):
        """Deselect renders that are in use by comp files."""
        self.ui.RendersClean.selectAll()
        self.ui.USDSClean.selectAll()

        if renders_in_comp:
            for render_name in renders_in_comp:
                matching_items = self.ui.RendersClean.findItems(render_name, Qt.MatchContains)
                for item in matching_items:
                    item.setSelected(False)


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

# Global window reference
window = None

def create_and_show_window():
    """Create the main window and show it."""
    global window
    window = LumaShotTools()
    window.show()

    # Close splash if it exists
    if ANIMATIONS_ENABLED and 'splash' in globals():
        splash.stop_animation()
        splash.close()

    # Run scanner after window is visible
    QTimer.singleShot(100, run_initial_scan)


def run_initial_scan():
    """Run the initial directory scan after the window is shown."""
    global window
    if window is None:
        return

    # Show loading overlay for initial scan
    if ANIMATIONS_ENABLED:
        window.animator.show_loading(
            "Scanning Directories",
            "Starting initial scan...",
            show_progress=True
        )
        window.animator.update_loading_progress(50)

    QApplication.processEvents()

    # Run initial scanner
    window.run_scanner()

    # Hide loading overlay
    if ANIMATIONS_ENABLED:
        window.animator.hide_loading()


# Show splash screen and initialize
if ANIMATIONS_ENABLED:
    # Create and show splash screen
    splash = SplashScreen()
    splash.start_animation()
    splash.update_progress(10, "Initializing Luma Shot Tools", "Loading application...")
    splash.show()

    # Process events to ensure splash is visible
    QApplication.processEvents()

    # Create window after short delay to ensure splash is visible
    QTimer.singleShot(200, create_and_show_window)

else:
    # No animations - create window directly
    window = LumaShotTools()
    window.show()
    QTimer.singleShot(100, run_initial_scan)

# Start event loop
sys.exit(app.exec_())
