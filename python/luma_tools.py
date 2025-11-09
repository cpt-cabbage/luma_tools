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
from config import UI_FILE_PATH, ICON_PATH, APP_ID, APP_TITLE
from utils import get_trailing_number, remove_after
from file_operations import find_renders
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
from ui_animations import enhance_ui, StatusColors
from loading_overlay import InlineSpinner
from splash_screen import SplashScreen

# Import new modular services
from state_manager import app_state
from scan_service import DirectoryScanner
from ui_styling import apply_stylesheet



import ctypes



kernel32 = ctypes.WinDLL('kernel32')

user32 = ctypes.WinDLL('user32')

SW_HIDE = 0

hWnd = kernel32.GetConsoleWindow()
user32.ShowWindow(hWnd, SW_HIDE)

# ============================================================================
# GLOBAL STATE - Managed by state_manager
# ============================================================================

# Initialize application state from command line arguments
app_state.initialize_from_args(sys.argv)

# Application instance
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

# Apply stylesheet
apply_stylesheet(app)

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

        # Set window flags for frameless, rounded style (same as splash screen)
        # self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Load UI
        self.ui = QtUiTools.QUiLoader().load(UI_FILE_PATH, parentWidget=self)
        self.parent = parent
        self.change_val[int].connect(self.set_progress_val)
        self.setWindowTitle(f"{APP_TITLE} - {app_state.jobname} - {app_state.shot}")
        self.setWindowIcon(QIcon(ICON_PATH))

        # Setup log redirection
        self.log_stream = LogStream()
        self.log_stream.message_written.connect(self.append_log)
        sys.stdout = self.log_stream
        sys.stderr = self.log_stream

        # Set window size from UI file and make it non-resizable
        self.setFixedSize(self.ui.size())

        # Setup animations
        self.animator = enhance_ui(self)
        print("UI animations enabled")

        # Create inline spinner for pass detection
        self.passes_spinner = InlineSpinner(self.ui.passesGroupBox, size=20)
        # Position will be set in showEvent when widget is fully laid out
        print("Inline spinner created for pass detection")

        # Initialize scanner
        self.scanner = DirectoryScanner(app_state, self.ui, self.animator)

        # Connect signals
        self._connect_signals()

        # Initialize UI state
        self.ui.OverrideHou.setChecked(True)
        self.ui.BuildPasses.setEnabled(False)

    def showEvent(self, event):
        """Override showEvent to position spinner after window is laid out."""
        super().showEvent(event)
        # Position the spinner after the UI is fully laid out
        self._position_spinner()

    def _position_spinner(self):
        """Position the inline spinner in the top-right of the passes group box."""
        if hasattr(self, 'passes_spinner') and hasattr(self.ui, 'passesGroupBox'):
            # Position in top-right corner with some padding
            x = self.ui.passesGroupBox.width() - 30
            y = 5
            self.passes_spinner.move(x, y)

    def paintEvent(self, event):
        """Paint the rounded background and border (same style as splash screen)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw rounded rectangle background
        bg_color = QColor(LoadingStyles.BACKGROUND_COLOR)
        bg_color.setAlpha(240)
        border_color = QColor(LoadingStyles.PRIMARY_COLOR)
        border_color.setAlpha(100)
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(self.rect(), LoadingStyles.BORDER_RADIUS, LoadingStyles.BORDER_RADIUS)

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
        self.ui.MP4UseForComp.toggled.connect(self.on_mp4_source_changed)
        self.ui.MP4UseRaw.toggled.connect(self.on_mp4_source_changed)
        self.ui.MP4UseCustom.toggled.connect(self.on_mp4_source_changed)
        self.ui.MP4BrowseCustomPath.clicked.connect(self.on_mp4_browse_custom_path_clicked)
        self.ui.MP4RendersList.itemSelectionChanged.connect(self.on_mp4_render_selection_changed)
        self.ui.MP4BrowseOutput.clicked.connect(self.on_mp4_browse_output_clicked)
        self.ui.MP4Generate.clicked.connect(self.on_mp4_generate_clicked)

        # rePublish tab
        self.ui.RePublishScanRenders.clicked.connect(self.on_republish_scan_renders_clicked)
        self.ui.RePublishCurrentVer.valueChanged.connect(self.on_republish_scan_renders_clicked)
        self.ui.RePublishUseForComp.toggled.connect(self.on_republish_source_changed)
        self.ui.RePublishUseRaw.toggled.connect(self.on_republish_source_changed)
        self.ui.RePublishUseCustom.toggled.connect(self.on_republish_source_changed)
        self.ui.RePublishBrowseCustomPath.clicked.connect(self.on_republish_browse_custom_path_clicked)
        self.ui.RePublishRendersList.itemSelectionChanged.connect(self.on_republish_render_selection_changed)
        self.ui.RePublishPublish.clicked.connect(self.on_republish_publish_clicked)

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
        self.ui.RendersList.clear()
        self.ui.Passes.clear()

        # Build search path
        app_state.searchpath = self.ui.RenderPath.text()
        currentver = get_trailing_number(app_state.searchpath)
        paddedcurrentver = '{:03d}'.format(int(currentver))
        split_path = app_state.searchpath.rsplit("_", 1)
        app_state.searchpath = split_path[0] + r"_" + split_path[1].replace(paddedcurrentver, "")[-1]
        newver = self.ui.CurrentVer.value()
        paddednewver = '{:03d}'.format(newver)
        app_state.searchpath += paddednewver
        self.ui.RenderPath.setText(app_state.searchpath)

        # Find renders
        app_state.renders = find_renders(app_state.searchpath)
        self.ui.BuildPasses.setEnabled(False)

        if len(app_state.renders) > 0:
            for render_seq in app_state.renders:
                self.ui.RendersList.addItem(str(render_seq).split("\\")[-1])
            self.ui.RendersList.setEnabled(True)
        else:
            self.ui.RendersList.addItem("No Renders Found")
            self.ui.RendersList.setEnabled(False)

    def on_render_selection_changed(self):
        """Update passes when selected render changes."""
        sel0 = self.ui.RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(app_state.renders):
            return

        index = sel0
        app_state.startframe = app_state.renders[index].start()
        app_state.endframe = app_state.renders[index].end()
        framename = app_state.renders[index].frame(app_state.startframe)
        filename = os.path.basename(framename)
        app_state.currentrender = filename.split(".")[0]
        denoisedpath = os.path.dirname(framename) + f"\{filename}"

        # Find passes (shows inline spinner automatically)
        self._detect_passes(denoisedpath)

        # Select previously saved passes
        app_state.passesfile = get_pass_file_path(app_state.working_dir, app_state.currentrender)
        self._select_saved_passes(app_state.passesfile)

    def _detect_passes(self, render_file):
        """Detect passes in render file with spinner animation."""
        self.ui.Passes.clear()

        # Show inline spinner
        self.passes_spinner.start()

        QApplication.processEvents()

        # Detect passes using service
        app_state.channels = detect_passes(render_file)

        # Hide spinner
        self.passes_spinner.stop()

        # Add passes to list
        for key in app_state.channels.keys():
            self.ui.Passes.addItem(key)

        # Enable build button
        if len(app_state.channels) >= 1:
            self.ui.BuildPasses.setEnabled(True)
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
        # Determine build type for UI messages
        use_farm = (self.ui.BuildType.currentIndex() == 1)
        main_title = "Submitting Render Passes" if use_farm else "Building Render Passes"

        # Show loading overlay IMMEDIATELY
        QApplication.processEvents()
        window.repaint()
        window.animator.show_loading(
            main_title,
            "Preparing to build...",
            show_progress=True
        )
        # Force immediate UI update
        QApplication.processEvents()
        window.repaint()

        # Add click animation after overlay is shown
        self.animator.animate_button_click(self.ui.BuildPasses)
        QApplication.processEvents()
        window.repaint()

        try:
            # Phase 1: Collect selected passes
            self.animator.update_loading_message(
                main_title,
                "Collecting selected passes..."
            )
            self.animator.update_loading_progress(5)
            QApplication.processEvents()
            window.repaint()

            channellist = []
            for item in self.ui.Passes.selectedItems():
                channellist.append(item.text())

            final_channels = dict((k, app_state.channels[k]) for k in channellist if k in app_state.channels)

            # Phase 2: Write pass configuration
            self.animator.update_loading_message(
                main_title,
                "Writing pass configuration file..."
            )
            self.animator.update_loading_progress(15)
            QApplication.processEvents()
            window.repaint()

            self._write_pass_config(final_channels)

            # Phase 3: Submit to farm or build locally
            build_location = "farm" if use_farm else "local"
            action_text = "Submitting to" if use_farm else "Building on"

            self.animator.update_loading_message(
                main_title,
                f"{action_text} {build_location}..."
            )
            self.animator.update_loading_progress(25)
            QApplication.processEvents()
            window.repaint()

            # Execute build with progress callback

            pass_builder.build_passes(
                passes_file=app_state.passesfile,
                renders_path=app_state.searchpath,
                start_frame=app_state.startframe,
                end_frame=app_state.endframe,
                use_farm=use_farm,
                project_name=app_state.jobname,
                shot=app_state.shot,
                parent_job_id="NONE",
                task=app_state.task,
                user=app_state.user,
                output_subdirectory=app_state.output_subdirectory,
                do_publish=True,
                progress_callback=self._build_progress_callback
            )

            # Phase 4: Complete
            self.animator.update_loading_message(
                main_title,
                "Build complete!"
            )
            self.animator.update_loading_progress(100)
            QApplication.processEvents()

            # Small delay to show completion
            QTimer.singleShot(500, lambda: self._finish_build_success(use_farm))

        except Exception as e:
            # Handle errors
            self.animator.hide_loading()
            self.animator.update_status_animated(
                f"Build failed: {str(e)}",
                StatusColors.ERROR
            )
            print(f"Build error: {e}")

    def _build_progress_callback(self, progress, message):
        """Callback for build progress updates from pass_builder."""
        use_farm = (self.ui.BuildType.currentIndex() == 1)
        main_title = "Submitting To Deadline" if use_farm else "Building EXRs"
        self.animator.update_loading_message(main_title, message)
        self.animator.update_loading_progress(progress)

    def _write_pass_config(self, passes_dictionary):
        """Write pass configuration to file."""
        save_pass_config(app_state.passesfile, passes_dictionary)
        self._write_settings_file()

    def _write_settings_file(self):
        """Write shot settings file."""
        import json
        settings = {}
        settings['overridehou'] = self.ui.OverrideHou.isChecked()

        shot_data_dir = os.path.join(app_state.working_dir, "shot_data")
        os.makedirs(shot_data_dir, exist_ok=True)

        settings_file = os.path.join(shot_data_dir, 'shot_settings.json')
        with open(settings_file, 'w') as fp:
            json.dump(settings, fp)

    def _finish_build_success(self, use_farm):
        """Called after successful build to show completion message."""
        completion_msg = "Farm submission complete!" if use_farm else "Local build and publish complete!"
        self.animator.hide_loading()
        self.animator.update_status_animated(
            completion_msg,
            StatusColors.SUCCESS
        )

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
            app_state.mp4_custom_path = custom_dir
            self.ui.MP4CustomPathLabel.setText(f"Custom path: {app_state.mp4_custom_path}")
            self.ui.MP4CustomPathLabel.setStyleSheet("color: white; font-size: 9pt;")
            print(f"MP4 Maker: Custom path set to: {app_state.mp4_custom_path}")

            # Trigger scan
            self.on_mp4_scan_renders_clicked()

    def on_mp4_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        self.ui.MP4RendersList.clear()

        # Build search path (same logic as Pass Builder)
        app_state.mp4_searchpath = self.ui.MP4RenderPath.text()

        # Handle version change
        if app_state.mp4_searchpath:
            currentver = get_trailing_number(app_state.mp4_searchpath)
            paddedcurrentver = '{:03d}'.format(int(currentver))
            split_path = app_state.mp4_searchpath.rsplit("_", 1)
            app_state.mp4_searchpath = split_path[0] + r"_" + split_path[1].replace(paddedcurrentver, "")[-1]
            newver = self.ui.MP4CurrentVer.value()
            paddednewver = '{:03d}'.format(newver)
            app_state.mp4_searchpath += paddednewver
            self.ui.MP4RenderPath.setText(app_state.mp4_searchpath)

        # Update "For Comp" radio button label with actual subdirectory name
        self.ui.MP4UseForComp.setText(f"Denoised ({app_state.output_subdirectory.title()})")

        # Determine which source to scan based on radio buttons
        app_state.mp4_renders = []
        self.ui.MP4Generate.setEnabled(False)

        print(f"MP4 Maker: Scanning path: {app_state.mp4_searchpath}")

        if self.ui.MP4UseForComp.isChecked():
            # Check for renders in for_comp subdirectory
            for_comp_path = os.path.join(app_state.mp4_searchpath, app_state.output_subdirectory)
            print(f"MP4 Maker: Scanning {app_state.output_subdirectory} path: {for_comp_path}")
            if os.path.exists(for_comp_path):
                # Use fileseq directly instead of find_renders which hardcodes denoised subdirectory
                import fileseq
                search_pattern = os.path.join(for_comp_path, "*.exr")
                print(f"MP4 Maker: Search pattern: {search_pattern}")
                for_comp_renders = list(fileseq.findSequencesOnDisk(search_pattern))
                print(f"MP4 Maker: Found {len(for_comp_renders)} renders in {app_state.output_subdirectory}")
                for render_seq in for_comp_renders:
                    app_state.mp4_renders.append((app_state.output_subdirectory, render_seq))
            else:
                print(f"MP4 Maker: {app_state.output_subdirectory} path does not exist")

        elif self.ui.MP4UseRaw.isChecked():
            # Check root path (for raw/non-denoised renders)
            print(f"MP4 Maker: Scanning raw render path: {app_state.mp4_searchpath}")
            if os.path.exists(app_state.mp4_searchpath):
                # Use fileseq directly instead of find_renders which hardcodes denoised subdirectory
                import fileseq
                search_pattern = os.path.join(app_state.mp4_searchpath, "*.exr")
                print(f"MP4 Maker: Search pattern: {search_pattern}")
                root_renders = list(fileseq.findSequencesOnDisk(search_pattern))
                print(f"MP4 Maker: Found {len(root_renders)} renders in root")
                for render_seq in root_renders:
                    app_state.mp4_renders.append(("raw", render_seq))
            else:
                print(f"MP4 Maker: Raw render path does not exist")

        elif self.ui.MP4UseCustom.isChecked():
            # Check custom path
            print(f"MP4 Maker: Scanning custom path: {app_state.mp4_custom_path}")
            if app_state.mp4_custom_path and os.path.exists(app_state.mp4_custom_path):
                # Use fileseq directly to find all EXR sequences
                import fileseq
                search_pattern = os.path.join(app_state.mp4_custom_path, "*.exr")
                print(f"MP4 Maker: Search pattern: {search_pattern}")
                custom_renders = list(fileseq.findSequencesOnDisk(search_pattern))
                print(f"MP4 Maker: Found {len(custom_renders)} renders in custom path")
                for render_seq in custom_renders:
                    app_state.mp4_renders.append(("custom", render_seq))
            elif not app_state.mp4_custom_path:
                print(f"MP4 Maker: No custom path selected - please browse to a directory")
            else:
                print(f"MP4 Maker: Custom path does not exist: {app_state.mp4_custom_path}")

        # Populate list
        print(f"MP4 Maker: Total renders found: {len(app_state.mp4_renders)}")
        if len(app_state.mp4_renders) > 0:
            for subdir, render_seq in app_state.mp4_renders:
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
        sel0 = self.ui.MP4RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(app_state.mp4_renders):
            self.ui.MP4Generate.setEnabled(False)
            return

        index = sel0
        # mp4_renders is now a list of tuples: (subdir, render_seq)
        subdir, render_seq = app_state.mp4_renders[index]
        app_state.mp4_startframe = render_seq.start()
        app_state.mp4_endframe = render_seq.end()

        print(f"MP4 Maker: Selected render from '{subdir}' - frames {app_state.mp4_startframe} to {app_state.mp4_endframe}")

        # Automatically set output path to user's Videos folder
        framename = render_seq.frame(render_seq.start())
        filename = os.path.basename(framename)
        render_name = filename.split(".")[0]
        default_filename = get_output_filename(render_name, app_state.shot)
        videos_folder = os.path.join(os.path.expanduser("~"), "Videos")
        app_state.mp4_output_path = os.path.join(videos_folder, default_filename)

        # Update UI
        self.ui.MP4OutputPath.setText(app_state.mp4_output_path)
        self.ui.MP4OutputPath.setStyleSheet("color: white; font-size: 9pt;")

        # Enable generate button
        self.ui.MP4Generate.setEnabled(True)
        self.animator.pulse_button(self.ui.MP4Generate)

    def on_mp4_browse_output_clicked(self):
        """Browse for MP4 output location."""
        # Get current render name for default filename
        sel0 = self.ui.MP4RendersList.currentRow()
        default_filename = f"{app_state.shot}_preview.mp4"

        if sel0 >= 0 and sel0 < len(app_state.mp4_renders):
            # mp4_renders is now a list of tuples: (subdir, render_seq)
            subdir, render_seq = app_state.mp4_renders[sel0]
            framename = render_seq.frame(render_seq.start())
            filename = os.path.basename(framename)
            render_name = filename.split(".")[0]
            default_filename = get_output_filename(render_name, app_state.shot)

        # Open file dialog with default location in user's Videos folder
        output_file, _ = QFileDialog.getSaveFileName(
            None,
            "Save MP4 As",
            os.path.join(os.path.expanduser("~"), "Videos", default_filename),
            "MP4 Video (*.mp4)"
        )

        if output_file:
            app_state.mp4_output_path = output_file
            self.ui.MP4OutputPath.setText(app_state.mp4_output_path)
            self.ui.MP4OutputPath.setStyleSheet("color: white; font-size: 9pt;")

            # Enable generate button if render is selected
            if self.ui.MP4RendersList.currentRow() >= 0:
                self.ui.MP4Generate.setEnabled(True)
                self.animator.pulse_button(self.ui.MP4Generate)

    def on_mp4_generate_clicked(self):
        """Generate MP4 from selected render."""
        # Show loading overlay
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
            if sel0 < 0 or sel0 >= len(app_state.mp4_renders):
                raise ValueError("No render selected")

            # Phase 1: Get render info
            self.animator.update_loading_message(
                "Generating MP4",
                "Analyzing render sequence..."
            )
            self.animator.update_loading_progress(5)
            QApplication.processEvents()

            # mp4_renders is now a list of tuples: (subdir, render_seq)
            subdir, render_seq = app_state.mp4_renders[sel0]
            framename = render_seq.frame(app_state.mp4_startframe)

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
                app_state.mp4_output_path,
                app_state.mp4_startframe,
                app_state.mp4_endframe,
                quality_index=quality_index,
                burn_in_timecode=burn_in_timecode,
                progress_callback=self._mp4_progress_callback
            )

            # Phase 4: Complete
            if success:
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
            self.animator.hide_loading()
            self.animator.update_status_animated(
                f"MP4 generation failed: {str(e)}",
                StatusColors.ERROR
            )
            print(f"MP4 generation error: {e}")

    def _mp4_progress_callback(self, progress, message):
        """Callback for MP4 generation progress updates."""
        self.animator.update_loading_message("Generating MP4", message)
        self.animator.update_loading_progress(progress)

    def _finish_mp4_success(self):
        """Called after successful MP4 generation to show completion message."""
        self.animator.hide_loading()
        self.animator.update_status_animated(
            f"MP4 generated: {os.path.basename(app_state.mp4_output_path)}",
            StatusColors.SUCCESS
        )
    # ========================================================================
    # REPUBLISH TAB HANDLERS
    # ========================================================================

    def on_republish_source_changed(self):
        """Handle rePublish source type radio button changes."""
        # Enable/disable custom path browse button
        is_custom = self.ui.RePublishUseCustom.isChecked()
        self.ui.RePublishBrowseCustomPath.setEnabled(is_custom)

        # Trigger scan when source changes
        self.on_republish_scan_renders_clicked()

    def on_republish_browse_custom_path_clicked(self):
        """Handle custom path browse button click for rePublish."""
        # Default to user's Videos folder
        default_path = os.path.join(os.path.expanduser("~"), "Videos")
        if not os.path.exists(default_path):
            default_path = os.path.expanduser("~")

        # Open directory dialog
        custom_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Custom Render Directory",
            default_path,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if custom_dir:
            app_state.republish_custom_path = custom_dir
            # Update label to show selected path
            self.ui.RePublishCustomPathLabel.setText(f"Custom path: {custom_dir}")
            self.ui.RePublishCustomPathLabel.setStyleSheet("color: white; font-size: 9pt;")

            # Trigger scan
            self.on_republish_scan_renders_clicked()

    def on_republish_scan_renders_clicked(self):
        """Scan for renders to republish based on selected source type."""
        import fileseq

        # Update searchpath with current version
        current_ver = self.ui.RePublishCurrentVer.value()
        if app_state.republish_searchpath:
            # Extract base path and replace version number
            import re
            # Match patterns like _v001, _v002, etc.
            app_state.republish_searchpath = re.sub(r'_v\d{3}', f'_v{current_ver:03d}', app_state.republish_searchpath)
            self.ui.RePublishRenderPath.setText(app_state.republish_searchpath)

        # Update "For Comp" label if output_subdirectory is set
        if app_state.output_subdirectory:
            self.ui.RePublishUseForComp.setText(f"Denoised ({app_state.output_subdirectory.title()})")

        # Clear previous list
        self.ui.RePublishRendersList.clear()
        app_state.republish_renders = []

        # Determine which source to scan
        search_path = ""
        if self.ui.RePublishUseForComp.isChecked():
            if app_state.output_subdirectory:
                search_path = os.path.join(app_state.republish_searchpath, app_state.output_subdirectory)
            else:
                search_path = app_state.republish_searchpath
        elif self.ui.RePublishUseRaw.isChecked():
            search_path = app_state.republish_searchpath
        elif self.ui.RePublishUseCustom.isChecked():
            search_path = app_state.republish_custom_path

        if not search_path or not os.path.exists(search_path):
            self.ui.RePublishStatusLabel.setText("Status: Invalid path")
            return

        # Find EXR sequences using fileseq
        try:
            search_pattern = os.path.join(search_path, "*.exr")
            sequences = list(fileseq.findSequencesOnDisk(search_pattern))

            for seq in sequences:
                # Extract subdirectory name if applicable
                seq_path = str(seq)
                rel_path = os.path.relpath(os.path.dirname(seq_path), search_path)
                subdir = rel_path if rel_path != "." else ""

                # Store tuple of (subdir, sequence_object)
                app_state.republish_renders.append((subdir, seq))

                # Display name
                if subdir and subdir != ".":
                    display_name = f"{subdir}/{seq.basename()}"
                else:
                    display_name = seq.basename()

                self.ui.RePublishRendersList.addItem(display_name)

            # Update status
            count = len(app_state.republish_renders)
            self.ui.RePublishStatusLabel.setText(f"Status: Found {count} render sequence(s)")

        except Exception as e:
            print(f"Error scanning renders for republish: {e}")
            self.ui.RePublishStatusLabel.setText(f"Status: Scan error - {str(e)}")

    def on_republish_render_selection_changed(self):
        """Handle render selection in rePublish list."""
        selected_items = self.ui.RePublishRendersList.selectedItems()
        if not selected_items:
            self.ui.RePublishPublish.setEnabled(False)
            app_state.republish_selected_render = None
            return

        # Get selected index
        selected_idx = self.ui.RePublishRendersList.currentRow()
        if selected_idx < 0 or selected_idx >= len(app_state.republish_renders):
            return

        # Get the fileseq object
        _, seq = app_state.republish_renders[selected_idx]  # subdir not needed here
        app_state.republish_selected_render = seq

        # Extract frame range
        app_state.republish_startframe = seq.start()
        app_state.republish_endframe = seq.end()

        # Update status with frame range
        self.ui.RePublishStatusLabel.setText(
            f"Status: Selected {seq.basename()}\n"
            f"Frames: {app_state.republish_startframe}-{app_state.republish_endframe}"
        )

        # Auto-populate product name if empty
        if not self.ui.RePublishProductName.text():
            # Extract render name from sequence
            # basename() returns something like "render.####.exr"
            # We need to extract just "render" part
            base = seq.basename()
            # Split by dots and filter out empty strings and hash patterns
            parts = [p for p in base.split('.') if p and not all(c == '#' for c in p)]
            # Take the first part (the actual render name) and remove extension
            render_name = parts[0] if parts else base.replace("#", "").strip(".")
            self.ui.RePublishProductName.setText(render_name)

        # Enable publish button
        self.ui.RePublishPublish.setEnabled(True)

        # Pulse animation if enabled
        self.animator.pulse_button(self.ui.RePublishPublish)

    def on_republish_publish_clicked(self):
        """Handle publish to AYON button click."""
        self.animator.animate_button_click(self.ui.RePublishPublish)

        # Validate selection
        if not app_state.republish_selected_render:
            self.ui.RePublishStatusLabel.setText("Status: No render selected")
            return

        # Get options
        task = self.ui.RePublishTask.currentText()
        use_farm = self.ui.RePublishUseFarm.isChecked()
        product_name = self.ui.RePublishProductName.text().strip()

        if not product_name:
            # Extract clean render name from sequence basename
            base = app_state.republish_selected_render.basename()
            parts = [p for p in base.split('.') if p and not all(c == '#' for c in p)]
            product_name = parts[0] if parts else base.replace("#", "").strip(".")

        # Show loading overlay
        self.animator.show_loading("Publishing to AYON", "Preparing metadata...")

        try:
            # Get render path information
            seq = app_state.republish_selected_render
            first_frame = seq.frame(app_state.republish_startframe)
            render_dir = os.path.dirname(first_frame)

            # Get the base filename pattern for the sequence
            # fileseq format: basename.####.ext, we need basename.%04d.ext for metadata
            base_name = seq.basename()
            frame_padding = len(seq.frameSet().frameRange().split("-")[0])
            render_file = f"{base_name.replace('#' * frame_padding, f'%0{frame_padding}d')}"

            # Determine folder path from searchpath
            from ayon_service import convert_to_ayon_folder_path, create_ayon_metadata, write_metadata_file
            from ayon_service import publish_to_ayon_local, submit_ayon_publish_to_deadline

            # Extract project and shot from searchpath
            folder_path = convert_to_ayon_folder_path(app_state.shotpath, app_state.jobname)

            # Create metadata
            metadata = create_ayon_metadata(
                project_name=app_state.jobname,
                render_name=product_name,
                start_frame=app_state.republish_startframe,
                end_frame=app_state.republish_endframe,
                renders_path=render_dir,
                folder_path=folder_path,
                task=task,
                user=app_state.user,
                output_subdirectory="",
                working_dir=app_state.working_dir,
                render_file=render_file
            )

            # Write metadata file to working directory, not render directory
            metadata_filename = f"ayon_{render_file}_{product_name}.json"
            metadata_path = os.path.join(app_state.working_dir, metadata_filename)
            metadata_path = write_metadata_file(metadata, metadata_path)

            if not metadata_path:
                raise Exception("Failed to write metadata file")

            self.animator.update_loading_message("Publishing to AYON",
                "Submitting to farm..." if use_farm else "Publishing locally...")

            # Publish
            if use_farm:
                # Submit to Deadline
                job_id = submit_ayon_publish_to_deadline(
                    metadata_path=metadata_path,
                    job_name=f"Publish_{product_name}",
                    priority=50,
                    pool="",
                    group="",
                    dependency_job_id=None
                )

                if job_id:
                    success_msg = f"Published to farm!\nJob ID: {job_id}"
                    self.ui.RePublishStatusLabel.setText(f"Status: {success_msg}")

                    self.animator.hide_loading()
                    self.animator.update_status_animated(success_msg, StatusColors.SUCCESS)
                else:
                    raise Exception("Failed to submit to Deadline")
            else:
                # Publish locally with correct arguments
                success = publish_to_ayon_local(
                    metadata_path,
                    app_state.jobname,  # project_name
                    folder_path,
                    task,
                    app_state.user
                )

                if success:
                    success_msg = f"Published: {product_name}"
                    self.ui.RePublishStatusLabel.setText(f"Status: {success_msg}")

                    self.animator.hide_loading()
                    self.animator.update_status_animated(success_msg, StatusColors.SUCCESS)
                else:
                    raise Exception("Local publish failed")

        except Exception as e:
            error_msg = f"Publish failed: {str(e)}"
            self.ui.RePublishStatusLabel.setText(f"Status: {error_msg}")

            self.animator.hide_loading()
            self.animator.update_status_animated(error_msg, StatusColors.ERROR)
            print(f"Publish error: {e}")
            import traceback
            traceback.print_exc()

    # ========================================================================
    # CLEANUP TAB HANDLERS
    # ========================================================================

    def on_clean_files_clicked(self):
        """Handle cleanup button click."""
        self.animator.animate_button_click(self.ui.CleanFiles)

        # Cleanup renders
        if self.ui.CleanRender.isChecked():
            render_dirs = [item.text() for item in self.ui.RendersClean.selectedItems()]
            if render_dirs:
                count = 0
                for dir_name in render_dirs:
                    count += 1
                    status_msg = f"Removing Renders: {app_state.lookdev_dir}\\img\\renders\\{dir_name}"
                    self.animator.update_status_animated(status_msg, StatusColors.WARNING)
                    print(status_msg)
                    self.change_val.emit(int(count / len(render_dirs) * 100))
                    QApplication.processEvents()

                cleanup_renders(app_state.lookdev_dir, render_dirs)

        # Cleanup USD
        if self.ui.CleanUSD.isChecked():
            usd_dirs = [item.text() for item in self.ui.USDSClean.selectedItems()]
            if usd_dirs:
                count = 0
                for dir_name in usd_dirs:
                    count += 1
                    self.change_val.emit(int(count / len(usd_dirs) * 100))
                    status_msg = f"Removing USDs: {app_state.lookdev_dir}\\usd_files\\{dir_name}"
                    self.animator.update_status_animated(status_msg, StatusColors.WARNING)
                    QApplication.processEvents()
                    print(status_msg)

                cleanup_usd(app_state.lookdev_dir, usd_dirs)

        # Cleanup HIP backups
        if self.ui.HIPBackups.isChecked():
            self.change_val.emit(0)
            status_msg = f"Removing Hip Backups Folder: {app_state.lookdev_dir}\\backup\\"
            self.animator.update_status_animated(status_msg, StatusColors.WARNING)
            cleanup_hip_backups(app_state.lookdev_dir)
            self.change_val.emit(100)
            QApplication.processEvents()

        # Final status
        self.animator.update_status_animated("Cleanup Done", StatusColors.SUCCESS)
        self.run_scanner()

    # ========================================================================
    # DIRECTORY SCANNER (Now uses scan_service module)
    # ========================================================================

    def run_scanner(self):
        """Scan directories for renders, USD, HIP files, and comps using scan_service."""
        # Clear UI elements
        self.ui.CleanFiles.setEnabled(False)
        self.ui.USDSClean.clear()
        self.ui.RendersClean.clear()

        # Delegate to scanner service
        self.scanner.scan_all()

        # Scan for renders in the current path
        try:
            self.on_scan_renders_clicked()
        except:
            self.ui.LatestRender.setText("Latest Render: None")
            self.ui.StatusLabel.setText('Cant find any renders')

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
splash = None


def create_window_and_scan():
    """Create the main window (hidden) and run the initial scan."""
    global window, splash

    # Update splash progress
    if splash:
        splash.update_progress(30, "Initializing Luma Shot Tools", "Creating main window...")
        QApplication.processEvents()

    # Create window but don't show it yet
    window = LumaShotTools()

    # Update splash progress
    if splash:
        splash.update_progress(50, "Initializing Luma Shot Tools", "Starting initial scan...")
        QApplication.processEvents()

    # Schedule the scanner to run
    QTimer.singleShot(100, run_initial_scan_with_splash)


def run_initial_scan_with_splash():
    """Run the initial scan while updating splash screen progress."""
    global window, splash

    if window is None:
        return

    # Temporarily disable the window's loading overlay during initial scan
    original_show_loading = None
    original_update_message = None
    original_update_progress = None
    original_hide_loading = None

    if hasattr(window, 'animator'):
        # Save original methods
        original_show_loading = window.animator.show_loading
        original_update_message = window.animator.update_loading_message
        original_update_progress = window.animator.update_loading_progress
        original_hide_loading = window.animator.hide_loading

        # Replace with splash update methods
        def splash_show_loading(main_text, sub_text="", show_progress=True):
            if splash:
                progress = 60  # Start at 60% for scanning
                splash.update_progress(progress, main_text, sub_text)
                QApplication.processEvents()

        def splash_update_message(main_text, sub_text=""):
            if splash:
                # Keep progress advancing during scan
                current_progress = splash.progress_bar.value()
                new_progress = min(current_progress + 5, 90)
                splash.update_progress(new_progress, main_text, sub_text)
                QApplication.processEvents()

        def splash_update_progress(value):
            if splash:
                # Map the progress to 60-90 range
                mapped_progress = 60 + int(value * 0.3)
                current_text = splash.main_label.text()
                current_sub = splash.sub_label.text()
                splash.update_progress(mapped_progress, current_text, current_sub)
                QApplication.processEvents()

        def splash_hide_loading():
            pass  # Don't hide, we'll handle it after scan

        # Monkey-patch the animator methods
        window.animator.show_loading = splash_show_loading
        window.animator.update_loading_message = splash_update_message
        window.animator.update_loading_progress = splash_update_progress
        window.animator.hide_loading = splash_hide_loading

    # Run the scanner
    window.run_scanner()

    # Restore original methods
    if hasattr(window, 'animator'):
        window.animator.show_loading = original_show_loading
        window.animator.update_loading_message = original_update_message
        window.animator.update_loading_progress = original_update_progress
        window.animator.hide_loading = original_hide_loading

    # Scan complete - show window and close splash
    finish_initialization()


def finish_initialization():
    """Finish initialization by showing the window and closing splash."""
    global window, splash

    if splash:
        splash.update_progress(100, "Initialization Complete", "Opening application...")
        QApplication.processEvents()

    # Small delay to show completion
    QTimer.singleShot(300, show_window_and_close_splash)


def show_window_and_close_splash():
    """Show the main window and close the splash screen."""
    global window, splash

    if window:
        window.show()

    if splash:
        splash.stop_animation()
        splash.close()
        splash = None


# Show splash screen and initialize
# Create and show splash screen
splash = SplashScreen()
splash.start_animation()
splash.update_progress(10, "Initializing Luma Shot Tools", "Loading application...")
splash.show()

# Process events to ensure splash is visible
QApplication.processEvents()

# Start initialization after splash is visible
QTimer.singleShot(200, create_window_and_scan)

# Start event loop
sys.exit(app.exec_())
