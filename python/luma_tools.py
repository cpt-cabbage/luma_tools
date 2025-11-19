"""
Luma Shot Tools - Main Application (Refactored).

VFX shot management application for the Luma Animation pipeline.
Handles render pass management, AYON publishing, Deadline farm submission,
and lookdev file cleanup for shot-based workflows.
"""

import sys
import os
from config import *

# Set up Windows things
if sys.platform == 'win32':
    import ctypes

    kernel32 = ctypes.WinDLL('kernel32')
    user32 = ctypes.WinDLL('user32')
    SW_HIDE = 0
    hWnd = kernel32.GetConsoleWindow()
    user32.ShowWindow(hWnd, SW_HIDE)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # Parent directory of 'python'



# Also add local paths for development/testing
sys.path.append(os.path.join(PROJECT_ROOT, "python"))
sys.path.append(os.path.join(PROJECT_ROOT, "resources", "ui"))

# PySide2 imports
from PySide2 import QtCore, QtUiTools, QtWidgets
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtCore import QThreadPool



from utils import get_trailing_number, remove_after, update_path_version, scan_exr_sequences
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
from ui_components import enhance_ui, StatusColors, InlineSpinner, apply_stylesheet, LoadingStyles, Worker
from splash_screen import SplashScreen

# Import new modular services
from state_manager import app_state
from scan_service import DirectoryScanner




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


print("DEADLINE " + DEADLINE_PATH)
print("OIIO " + OIIO_PATH)
print("OIIO INFO " + OIIO_INFO_ROOT)
print("FFMPEG " + FFMPEG_PATH)
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
        self.animator.redirect_to_splash = False  # Flag for splash screen redirection
        self.animator.splash_screen = None
        print("UI animations enabled")

        # Create inline spinner for pass detection
        self.passes_spinner = InlineSpinner(self.ui.passesGroupBox, size=20)
        # Position will be set in showEvent when widget is fully laid out
        print("Inline spinner created for pass detection")

        # Initialize scanner
        self.scanner = DirectoryScanner(app_state, self.ui, self.animator)

        # Connect scanner signals for thread-safe GUI updates
        self._connect_scanner_signals()

        # Connect UI signals
        self._connect_signals()

        # Initialize UI state
        self.ui.OverrideHou.setChecked(True)
        self.ui.BuildPasses.setEnabled(False)

        # Initialize default passes settings
        self._load_default_passes_ui()

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

    def _connect_scanner_signals(self):
        """Connect DirectoryScanner signals to GUI update slots (thread-safe)."""
        # Text updates
        self.scanner.signals.set_label_text.connect(self._on_set_label_text)

        # List operations
        self.scanner.signals.add_list_item.connect(self._on_add_list_item)
        self.scanner.signals.clear_list.connect(self._on_clear_list)
        self.scanner.signals.scroll_list_to_bottom.connect(self._on_scroll_list_to_bottom)
        self.scanner.signals.select_all_items.connect(self._on_select_all_items)
        self.scanner.signals.deselect_items_matching.connect(self._on_deselect_items_matching)

        # Widget state
        self.scanner.signals.set_widget_enabled.connect(self._on_set_widget_enabled)
        self.scanner.signals.set_widget_checked.connect(self._on_set_widget_checked)

        # Spinbox operations
        self.scanner.signals.set_spinbox_range.connect(self._on_set_spinbox_range)
        self.scanner.signals.set_spinbox_value.connect(self._on_set_spinbox_value)

        # Combobox operations
        self.scanner.signals.set_combobox_text.connect(self._on_set_combobox_text)

    @QtCore.Slot(str, str)
    def _on_set_label_text(self, widget_name, text):
        """Set text on a label or line edit widget."""
        widget = getattr(self.ui, widget_name, None)
        if widget:
            widget.setText(text)

    @QtCore.Slot(str, str)
    def _on_add_list_item(self, list_name, item_text):
        """Add an item to a list widget."""
        list_widget = getattr(self.ui, list_name, None)
        if list_widget:
            list_widget.addItem(item_text)

    @QtCore.Slot(str)
    def _on_clear_list(self, list_name):
        """Clear a list widget."""
        list_widget = getattr(self.ui, list_name, None)
        if list_widget:
            list_widget.clear()

    @QtCore.Slot(str)
    def _on_scroll_list_to_bottom(self, list_name):
        """Scroll a list widget to the bottom."""
        list_widget = getattr(self.ui, list_name, None)
        if list_widget:
            list_widget.scrollToBottom()

    @QtCore.Slot(str)
    def _on_select_all_items(self, list_name):
        """Select all items in a list widget."""
        list_widget = getattr(self.ui, list_name, None)
        if list_widget:
            list_widget.selectAll()

    @QtCore.Slot(str, str)
    def _on_deselect_items_matching(self, list_name, text_to_match):
        """Deselect items matching text in a list widget."""
        from PySide2.QtCore import Qt
        list_widget = getattr(self.ui, list_name, None)
        if list_widget:
            matching_items = list_widget.findItems(text_to_match, Qt.MatchContains)
            for item in matching_items:
                item.setSelected(False)

    @QtCore.Slot(str, bool)
    def _on_set_widget_enabled(self, widget_name, enabled):
        """Enable/disable a widget."""
        widget = getattr(self.ui, widget_name, None)
        if widget:
            widget.setEnabled(enabled)

    @QtCore.Slot(str, bool)
    def _on_set_widget_checked(self, widget_name, checked):
        """Set checked state of a widget."""
        widget = getattr(self.ui, widget_name, None)
        if widget:
            widget.setChecked(checked)

    @QtCore.Slot(str, int, int)
    def _on_set_spinbox_range(self, widget_name, min_val, max_val):
        """Set range of a spinbox widget."""
        widget = getattr(self.ui, widget_name, None)
        if widget:
            widget.setRange(min_val, max_val)

    @QtCore.Slot(str, int)
    def _on_set_spinbox_value(self, widget_name, value):
        """Set value of a spinbox widget."""
        widget = getattr(self.ui, widget_name, None)
        if widget:
            widget.setValue(value)

    @QtCore.Slot(str, str)
    def _on_set_combobox_text(self, widget_name, text):
        """Set text/selection of a combobox widget."""
        from PySide2.QtCore import Qt
        widget = getattr(self.ui, widget_name, None)
        if widget:
            # Try to find and select the item
            index = widget.findText(text, Qt.MatchFixedString)
            if index >= 0:
                widget.setCurrentIndex(index)
            else:
                # If not found, add it and select it
                widget.addItem(text)
                widget.setCurrentText(text)

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
        self.ui.AddPassButton.clicked.connect(self.on_add_pass_clicked)
        self.ui.RemovePassButton.clicked.connect(self.on_remove_pass_clicked)
        self.ui.ResetPassesButton.clicked.connect(self.on_reset_passes_clicked)
        self.ui.SaveSettingsButton.clicked.connect(self.on_save_settings_clicked)

    @QtCore.Slot(int)
    def set_progress_val(self, val):
        """Update progress bar value."""
        self.ui.progressBar.setValue(val)

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

    def _load_default_passes_ui(self):
        """Load default passes into the settings UI."""
        from settings_manager import get_default_passes
        from config import REQUIRED_PASSES, DEFAULT_PASSES

        self.ui.DefaultPassesList.clear()

        # Get user's current default passes (or system defaults)
        default_passes = get_default_passes()

        # Populate the list with all available passes
        all_available_passes = list(set(REQUIRED_PASSES + DEFAULT_PASSES + default_passes))

        for pass_name in sorted(all_available_passes):
            item = QtWidgets.QListWidgetItem(pass_name)

            # Mark required passes as disabled (can't be removed)
            if pass_name in REQUIRED_PASSES:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setToolTip("This pass is always included and cannot be removed")
                # Make required passes visually distinct
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            else:
                item.setToolTip("Select to include this pass by default")

            self.ui.DefaultPassesList.addItem(item)

            # Select the item if it's in the user's default passes or is required
            if pass_name in default_passes or pass_name in REQUIRED_PASSES:
                item.setSelected(True)

        print(f"Loaded default passes UI with {len(all_available_passes)} passes")

    def on_add_pass_clicked(self):
        """Add a custom pass to the default passes list."""
        from PySide2.QtWidgets import QInputDialog

        pass_name, ok = QInputDialog.getText(
            self,
            "Add Pass",
            "Enter pass name:",
            QtWidgets.QLineEdit.Normal
        )

        if ok and pass_name:
            pass_name = pass_name.strip()

            # Check if pass already exists
            existing_items = self.ui.DefaultPassesList.findItems(pass_name, Qt.MatchExactly)
            if existing_items:
                print(f"Pass '{pass_name}' already exists in the list")
                return

            # Add the new pass
            item = QtWidgets.QListWidgetItem(pass_name)
            item.setToolTip("Select to include this pass by default")
            item.setSelected(True)  # Auto-select newly added passes
            self.ui.DefaultPassesList.addItem(item)
            print(f"Added custom pass: {pass_name}")

    def on_remove_pass_clicked(self):
        """Remove selected pass from the default passes list."""
        from config import REQUIRED_PASSES

        selected_items = self.ui.DefaultPassesList.selectedItems()

        if not selected_items:
            print("No passes selected for removal")
            return

        for item in selected_items:
            pass_name = item.text()

            # Don't allow removing required passes
            if pass_name in REQUIRED_PASSES:
                print(f"Cannot remove required pass: {pass_name}")
                continue

            # Remove the item
            row = self.ui.DefaultPassesList.row(item)
            self.ui.DefaultPassesList.takeItem(row)
            print(f"Removed pass: {pass_name}")

    def on_reset_passes_clicked(self):
        """Reset default passes to system defaults."""
        from PySide2.QtWidgets import QMessageBox

        # Confirm reset
        reply = QMessageBox.question(
            self,
            "Reset Default Passes",
            "Reset to default pass list (CryptoMaterials, P, depth, uv, normal)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            from config import DEFAULT_PASSES
            from settings_manager import set_default_passes

            # Reset to system defaults
            set_default_passes(DEFAULT_PASSES.copy())
            print("Reset to default passes")

            # Reload UI
            self._load_default_passes_ui()

    def on_save_settings_clicked(self):
        """Save the current default passes settings."""
        from config import REQUIRED_PASSES
        from settings_manager import set_default_passes

        # Collect selected passes (excluding required passes as they're always included)
        selected_passes = []
        for i in range(self.ui.DefaultPassesList.count()):
            item = self.ui.DefaultPassesList.item(i)
            pass_name = item.text()

            # Skip required passes (they're always included automatically)
            if pass_name in REQUIRED_PASSES:
                continue

            # Add selected passes
            if item.isSelected():
                selected_passes.append(pass_name)

        # Save settings
        set_default_passes(selected_passes)
        print(f"Saved default passes: {selected_passes}")

        # Show confirmation
        self.animator.pulse_button(self.ui.SaveSettingsButton)

    # ========================================================================
    # RENDER TAB HANDLERS
    # ========================================================================

    def on_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        self.ui.RendersList.clear()
        self.ui.Passes.clear()

        # Build search path
        app_state.searchpath = self.ui.RenderPath.text()
        newver = self.ui.CurrentVer.value()
        app_state.searchpath = update_path_version(app_state.searchpath, newver)
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
        # Note: Pass selection happens in _detect_passes callback after passes are loaded
        app_state.passesfile = get_pass_file_path(app_state.working_dir, app_state.currentrender)
        self._detect_passes(denoisedpath)

    def _detect_passes(self, render_file):
        """Detect passes in render file with spinner animation - runs on background thread."""
        self.ui.Passes.clear()

        # Show inline spinner
        self.passes_spinner.start()

        def on_result(channels):
            """Called when pass detection completes."""
            from settings_manager import get_all_default_passes

            # Hide spinner
            self.passes_spinner.stop()

            # Store channels
            app_state.channels = channels

            # Get default passes that should be hidden from the list
            default_passes = get_all_default_passes()

            # Add passes to list (exclude default passes - they're auto-included)
            for key in channels.keys():
                # Skip passes that are in the default list
                if key not in default_passes:
                    self.ui.Passes.addItem(key)

            # Select previously saved passes (now that list is populated)
            self._select_saved_passes(app_state.passesfile)

            # Enable build button
            if len(channels) >= 1:
                self.ui.BuildPasses.setEnabled(True)
                self.animator.pulse_button(self.ui.BuildPasses)
            else:
                self.ui.BuildPasses.setEnabled(False)

        def on_error(error_msg, traceback_str):
            """Called when pass detection fails."""
            self.passes_spinner.stop()
            print(f"Pass detection error: {error_msg}")
            self.ui.BuildPasses.setEnabled(False)

        # Create worker and run on background thread
        worker = Worker(detect_passes, render_file)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        QThreadPool.globalInstance().start(worker)

    def _select_saved_passes(self, passes_file):
        """
        Select previously saved passes in the UI.
        Note: Default passes are auto-included and hidden from the list.
        """
        from settings_manager import get_all_default_passes

        selectedpasses = load_pass_config(passes_file)
        print(f"DEBUG: Loaded passes from file: {selectedpasses}")

        # Debug: print all items currently in the list
        all_items = [self.ui.Passes.item(i).text() for i in range(self.ui.Passes.count())]
        print(f"DEBUG: Available passes in UI: {all_items}")

        # Get default passes (these are auto-included and not shown in the list)
        default_passes = get_all_default_passes()

        if selectedpasses:
            # Filter out default passes from the saved selection (they're auto-included)
            passes_to_select = [p for p in selectedpasses.keys() if p not in default_passes]
            print(f"Using saved passes from file (excluding auto-included): {passes_to_select}")
        else:
            # No saved passes and no manual selection needed (defaults are auto-included)
            passes_to_select = []
            print(f"No saved passes found, only default passes will be included: {default_passes}")

        # Select the passes that are visible in the UI
        for pass_name in passes_to_select:
            print(f"DEBUG: Looking for pass: '{pass_name}'")
            matching_items = self.ui.Passes.findItems(pass_name, Qt.MatchExactly)
            print(f"DEBUG: Found {len(matching_items)} matching items for '{pass_name}'")
            for item in matching_items:
                item.setSelected(True)
                print(f"DEBUG: Selected item: '{item.text()}'")

    # ========================================================================
    # PASS BUILDING HANDLERS
    # ========================================================================

    def on_build_passes_clicked(self):
        """Build render files with selected passes - runs on background thread."""
        # Determine build type for UI messages
        use_farm = (self.ui.BuildType.currentIndex() == 1)
        main_title = "Submitting Render Passes" if use_farm else "Building Render Passes"

        # Show loading overlay
        self.animator.show_loading(
            main_title,
            "Preparing to build...",
            show_progress=True
        )

        # Add click animation
        self.animator.animate_button_click(self.ui.BuildPasses)

        # Collect selected passes on main thread (UI access)
        from settings_manager import get_all_default_passes

        channellist = []
        # Add manually selected passes from the UI
        for item in self.ui.Passes.selectedItems():
            channellist.append(item.text())

        # Add default passes (auto-included, hidden from UI)
        default_passes = get_all_default_passes()
        for pass_name in default_passes:
            if pass_name not in channellist:
                channellist.append(pass_name)

        print(f"Building with passes: {channellist}")
        print(f"  - User selected: {[item.text() for item in self.ui.Passes.selectedItems()]}")
        print(f"  - Auto-included defaults: {default_passes}")

        final_channels = dict((k, app_state.channels[k]) for k in channellist if k in app_state.channels)

        # Write pass configuration (quick operation, can stay on main thread)
        self.animator.update_loading_message(
            main_title,
            "Writing pass configuration file..."
        )
        self.animator.update_loading_progress(15)
        self._write_pass_config(final_channels)

        # Prepare build parameters
        build_location = "farm" if use_farm else "local"
        action_text = "Submitting to" if use_farm else "Building on"

        self.animator.update_loading_message(
            main_title,
            f"{action_text} {build_location}..."
        )
        self.animator.update_loading_progress(25)

        def on_progress(progress, message):
            """Update UI with build progress."""
            progress_title = "Submitting To Deadline" if use_farm else "Building EXRs"
            self.animator.update_loading_message(progress_title, message)
            self.animator.update_loading_progress(progress)

        def on_result(result):
            """Called when build completes successfully."""
            self.animator.update_loading_message("Build Submitted", "Build complete!")
            self.animator.update_loading_progress(100)
            # Small delay to show completion
            QTimer.singleShot(500, lambda: self._finish_build_success(use_farm))

        def on_error(error_msg, traceback_str):
            """Called when build fails."""
            self.animator.hide_loading()
            self.animator.update_status_animated(
                f"Build failed: {error_msg}",
                StatusColors.ERROR
            )
            print(f"Build error: {error_msg}")
            print(traceback_str)

        # Create worker and run build on background thread
        worker = Worker(
            pass_builder.build_passes,
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
            do_publish=True
        )
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(on_progress)
        QThreadPool.globalInstance().start(worker)

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
            newver = self.ui.MP4CurrentVer.value()
            app_state.mp4_searchpath = update_path_version(app_state.mp4_searchpath, newver)
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
                # Use scan_exr_sequences to find renders
                print(f"MP4 Maker: Scanning path: {for_comp_path}")
                for_comp_renders = scan_exr_sequences(for_comp_path)
                print(f"MP4 Maker: Found {len(for_comp_renders)} renders in {app_state.output_subdirectory}")
                for render_seq in for_comp_renders:
                    app_state.mp4_renders.append((app_state.output_subdirectory, render_seq))
            else:
                print(f"MP4 Maker: {app_state.output_subdirectory} path does not exist")

        elif self.ui.MP4UseRaw.isChecked():
            # Check root path (for raw/non-denoised renders)
            print(f"MP4 Maker: Scanning raw render path: {app_state.mp4_searchpath}")
            if os.path.exists(app_state.mp4_searchpath):
                # Use scan_exr_sequences to find renders
                root_renders = scan_exr_sequences(app_state.mp4_searchpath)
                print(f"MP4 Maker: Found {len(root_renders)} renders in root")
                for render_seq in root_renders:
                    app_state.mp4_renders.append(("raw", render_seq))
            else:
                print(f"MP4 Maker: Raw render path does not exist")

        elif self.ui.MP4UseCustom.isChecked():
            # Check custom path
            print(f"MP4 Maker: Scanning custom path: {app_state.mp4_custom_path}")
            if app_state.mp4_custom_path and os.path.exists(app_state.mp4_custom_path):
                # Use scan_exr_sequences to find all EXR sequences
                custom_renders = scan_exr_sequences(app_state.mp4_custom_path)
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
        """Generate MP4 from selected render - runs on background thread."""
        # Show loading overlay
        self.animator.show_loading(
            "Generating MP4",
            "Preparing to convert...",
            show_progress=True
        )
        self.animator.animate_button_click(self.ui.MP4Generate)

        # Get selected render (UI access on main thread)
        sel0 = self.ui.MP4RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(app_state.mp4_renders):
            self.animator.hide_loading()
            self.animator.update_status_animated(
                "No render selected",
                StatusColors.ERROR
            )
            return

        # Get render info
        self.animator.update_loading_message(
            "Generating MP4",
            "Analyzing render sequence..."
        )
        self.animator.update_loading_progress(5)

        # mp4_renders is now a list of tuples: (subdir, render_seq)
        subdir, render_seq = app_state.mp4_renders[sel0]
        framename = render_seq.frame(app_state.mp4_startframe)

        # Build input pattern for ffmpeg
        base_dir = os.path.dirname(framename)
        base_filename = os.path.basename(framename)
        parts = base_filename.split(".")
        if len(parts) < 3:
            self.animator.hide_loading()
            self.animator.update_status_animated(
                f"Unexpected filename format: {base_filename}",
                StatusColors.ERROR
            )
            return

        # Format: name.####.exr
        input_pattern = os.path.join(base_dir, f"{parts[0]}.%04d.exr")

        # Get settings
        self.animator.update_loading_message(
            "Generating MP4",
            "Configuring conversion settings..."
        )
        self.animator.update_loading_progress(8)

        quality_index = self.ui.MP4Quality.currentIndex()
        burn_in_timecode = self.ui.MP4BurnInTimecode.isChecked()

        def on_progress(progress, message):
            """Update UI with MP4 generation progress."""
            self.animator.update_loading_message("Generating MP4", message)
            self.animator.update_loading_progress(progress)

        def on_result(success):
            """Called when MP4 generation completes."""
            if success:
                self.animator.update_loading_message(
                    "Generating MP4",
                    "MP4 generation complete!"
                )
                self.animator.update_loading_progress(100)
                # Small delay to show completion
                QTimer.singleShot(500, lambda: self._finish_mp4_success())
            else:
                self.animator.hide_loading()
                self.animator.update_status_animated(
                    "MP4 generation failed",
                    StatusColors.ERROR
                )

        def on_error(error_msg, traceback_str):
            """Called when MP4 generation fails."""
            self.animator.hide_loading()
            self.animator.update_status_animated(
                f"MP4 generation failed: {error_msg}",
                StatusColors.ERROR
            )
            print(f"MP4 generation error: {error_msg}")
            print(traceback_str)

        # Create worker and run MP4 generation on background thread
        worker = Worker(
            generate_mp4,
            input_pattern,
            app_state.mp4_output_path,
            app_state.mp4_startframe,
            app_state.mp4_endframe,
            quality_index=quality_index,
            burn_in_timecode=burn_in_timecode
        )
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(on_progress)
        QThreadPool.globalInstance().start(worker)

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
            app_state.republish_searchpath = update_path_version(app_state.republish_searchpath, current_ver)
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

        # Find EXR sequences using scan_exr_sequences
        try:
            sequences = scan_exr_sequences(search_path)

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
                    print(status_msg)

                cleanup_usd(app_state.lookdev_dir, usd_dirs)

        # Cleanup HIP backups
        if self.ui.HIPBackups.isChecked():
            self.change_val.emit(0)
            status_msg = f"Removing Hip Backups Folder: {app_state.lookdev_dir}\\backup\\"
            self.animator.update_status_animated(status_msg, StatusColors.WARNING)
            cleanup_hip_backups(app_state.lookdev_dir)
            self.change_val.emit(100)

        # Final status
        self.animator.update_status_animated("Cleanup Done", StatusColors.SUCCESS)
        self.run_scanner()

    # ========================================================================
    # DIRECTORY SCANNER (Now uses scan_service module)
    # ========================================================================

    def run_scanner(self, on_complete=None):
        """
        Scan directories for renders, USD, HIP files, and comps - runs on background thread.

        Args:
            on_complete: Optional callback to call when scanning completes
        """
        # Clear UI elements
        self.ui.CleanFiles.setEnabled(False)
        self.ui.USDSClean.clear()
        self.ui.RendersClean.clear()

        def on_result(result):
            """Called when scanning completes."""
            # Scan for renders in the current path
            try:
                self.on_scan_renders_clicked()
            except:
                self.ui.LatestRender.setText("Latest Render: None")
                self.ui.StatusLabel.setText('Cant find any renders')

            # Hide loading overlay
            self.animator.hide_loading()

            # Call completion callback if provided
            if on_complete:
                on_complete()

        def on_error(error_msg, traceback_str):
            """Called when scanning fails."""
            self.animator.hide_loading()
            print(f"Scanner error: {error_msg}")
            print(traceback_str)

            # Call completion callback even on error
            if on_complete:
                on_complete()

        # Create worker and run scan on background thread
        worker = Worker(self.scanner.scan_all)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        QThreadPool.globalInstance().start(worker)

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

    # Create window but don't show it yet
    window = LumaShotTools()

    # Update splash progress
    if splash:
        splash.update_progress(50, "Initializing Luma Shot Tools", "Starting initial scan...")

    # Schedule the scanner to run
    QTimer.singleShot(100, run_initial_scan_with_splash)


def run_initial_scan_with_splash():
    """Run the initial scan while updating splash screen progress."""
    global window, splash

    if window is None:
        return

    # Enable splash screen redirection using flag-based approach
    if hasattr(window, 'animator'):
        window.animator.redirect_to_splash = True
        window.animator.splash_screen = splash

    def on_scan_complete():
        """Called when the scanner completes."""
        # Disable splash screen redirection
        if hasattr(window, 'animator'):
            window.animator.redirect_to_splash = False
            window.animator.splash_screen = None

        # Scan complete - show window and close splash
        finish_initialization()

    # Run the scanner with completion callback
    window.run_scanner(on_complete=on_scan_complete)


def finish_initialization():
    """Finish initialization by showing the window and closing splash."""
    global window, splash

    if splash:
        splash.update_progress(100, "Initialization Complete", "Opening application...")

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
