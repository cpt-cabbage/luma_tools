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
from ui_components import (
    enhance_ui, StatusColors, InlineSpinner, apply_stylesheet, LoadingStyles, Worker,
    BatchImageSelector, ComfyUIStatusBanner, CollapsibleSection, StepGroupBox,
    ToastNotification, StepProgressIndicator, EmptyStateWidget, ThumbnailRenderList,
    RenderListItem
)
from splash_screen import SplashScreen
from icons import IconManager, TAB_COLORS

# Import new modular services
from state_manager import app_state
from scan_service import DirectoryScanner
from thumbnail_service import ThumbnailService
from comfyui_service import extract_editable_nodes, EditableNode, submit_comfyui_job
from spell_checker import SpellCheckTextEdit, is_spell_check_available
from settings_manager import (
    get_comfyui_text_presets,
    save_comfyui_text_preset,
    delete_comfyui_text_preset,
    get_comfyui_workflow_presets,
    save_comfyui_workflow_preset,
    delete_comfyui_workflow_preset,
    get_comfyui_workflow_preset_path,
    get_global_settings_path,
    set_global_settings_path,
    get_comfyui_path,
    set_comfyui_path,
    get_comfyui_mode,
    set_comfyui_mode,
    get_comfyui_python_path,
    set_comfyui_python_path,
    get_last_browse_directory,
    set_last_browse_directory,
    get_comfyui_tab_state,
    save_comfyui_tab_state,
    get_admin_users,
    add_admin_user,
    remove_admin_user,
)




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

        # Debug logging to file (writes before stdout redirect)
        import tempfile
        debug_log = os.path.join(tempfile.gettempdir(), "luma_tools_debug.log")
        def _debug(msg):
            with open(debug_log, "a") as f:
                f.write(f"{msg}\n")
                f.flush()
        _debug("=== LumaShotTools.__init__ started ===")

        # Set window flags for frameless, rounded style (same as splash screen)
        # self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        _debug("1. setAttribute done")

        # Load UI
        _debug("2. Loading UI file...")
        self.ui = QtUiTools.QUiLoader().load(UI_FILE_PATH, parentWidget=self)
        _debug("3. UI loaded successfully")
        self.parent = parent
        self.change_val[int].connect(self.set_progress_val)
        self.setWindowTitle(f"{APP_TITLE} - {app_state.jobname} - {app_state.shot}")
        self.setWindowIcon(QIcon(ICON_PATH))
        _debug("4. Window title and icon set")

        # Setup log redirection
        self.log_stream = LogStream()
        self.log_stream.message_written.connect(self.append_log)
        sys.stdout = self.log_stream
        sys.stderr = self.log_stream
        _debug("5. Log stream redirected")

        # Check admin status
        _debug("5a. Checking admin status...")
        self._check_admin_status()
        _debug("5b. Admin status checked")

        # Set window size from UI file and make it non-resizable
        self.setFixedSize(self.ui.size())
        _debug("6. Window size set")

        # Setup animations
        _debug("7. Setting up animations...")
        self.animator = enhance_ui(self)
        self.animator.redirect_to_splash = False  # Flag for splash screen redirection
        self.animator.splash_screen = None
        _debug("8. Animations done")
        print("UI animations enabled")

        # Create inline spinner for pass detection
        _debug("9. Creating InlineSpinner...")
        self.passes_spinner = InlineSpinner(self.ui.passesGroupBox, size=20)
        _debug("10. InlineSpinner created")
        # Position will be set in showEvent when widget is fully laid out
        print("Inline spinner created for pass detection")

        # Initialize scanner
        _debug("11. Creating DirectoryScanner...")
        self.scanner = DirectoryScanner(app_state, self.ui, self.animator)
        _debug("12. DirectoryScanner created")

        # Connect scanner signals for thread-safe GUI updates
        _debug("13. Connecting scanner signals...")
        self._connect_scanner_signals()
        _debug("14. Scanner signals connected")

        # Connect UI signals
        _debug("15. Connecting UI signals...")
        self._connect_signals()
        _debug("16. UI signals connected")

        # Initialize UI state
        _debug("17. Setting initial UI state...")
        self.ui.OverrideHou.setChecked(True)
        self.ui.BuildPasses.setEnabled(False)
        _debug("18. Initial UI state set")

        # Initialize default passes UI
        _debug("19. Loading default passes UI...")
        self._load_default_passes_ui()
        _debug("20. Default passes UI loaded")

        # Setup colorful tab icons
        _debug("21. Setting up tab icons...")
        self._setup_tab_icons()
        _debug("22. Tab icons done")

        # Restore saved tab order
        _debug("22a. Restoring tab order...")
        self._restore_tab_order()
        _debug("22b. Tab order restored")

        # Hide restricted tabs for non-admin users
        _debug("22c. Hiding restricted tabs...")
        self._hide_restricted_tabs()
        _debug("22d. Restricted tabs hidden")

        # Setup button icons
        _debug("23. Setting up button icons...")
        self._setup_button_icons()
        _debug("24. Button icons done")

        # Disable scroll wheel on combo boxes and spin boxes
        _debug("24a. Disabling scroll wheel on dropdowns...")
        self._disable_scroll_wheel_on_inputs()
        _debug("24b. Scroll wheel disabled")

        # Initialize ComfyUI tab
        _debug("25. Initializing ComfyUI tab...")
        self._init_comfyui_tab()
        _debug("26. ComfyUI tab done - __init__ complete!")

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

        # Global settings
        self.ui.BrowseGlobalSettingsPath.clicked.connect(self.on_browse_global_settings_path)
        self.ui.BrowseComfyUIPath.clicked.connect(self.on_browse_comfyui_path)
        self.ui.BrowseComfyUIPython.clicked.connect(self.on_browse_comfyui_python)
        self.ui.ComfyUIModeCombo.currentIndexChanged.connect(self.on_comfyui_mode_changed)
        self.ui.SaveGlobalSettings.clicked.connect(self.on_save_global_settings)
        self._load_global_settings_ui()

        # Admin user management (only available if admin and widgets exist)
        if hasattr(self.ui, 'AddAdminUserButton'):
            self.ui.AddAdminUserButton.clicked.connect(self.on_add_admin_user)
        if hasattr(self.ui, 'RemoveAdminUserButton'):
            self.ui.RemoveAdminUserButton.clicked.connect(self.on_remove_admin_user)
        self._load_admin_users_ui()

        # Tab reordering persistence
        self.ui.tabWidget.tabBar().tabMoved.connect(self.on_tab_moved)

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

    def on_tab_moved(self, from_index, to_index):
        """Save tab order when user reorders tabs."""
        from settings_manager import save_tab_order

        tab_names = []
        for i in range(self.ui.tabWidget.count()):
            widget = self.ui.tabWidget.widget(i)
            tab_names.append(widget.objectName())

        save_tab_order(tab_names)
        print(f"Tab order saved: {tab_names}")

    def _restore_tab_order(self):
        """Restore saved tab order on startup."""
        from settings_manager import get_tab_order

        saved_order = get_tab_order()
        if not saved_order:
            return

        # Build a map of tab name to widget
        tab_widgets = {}
        for i in range(self.ui.tabWidget.count()):
            widget = self.ui.tabWidget.widget(i)
            tab_widgets[widget.objectName()] = widget

        # Reorder tabs based on saved order
        for target_index, tab_name in enumerate(saved_order):
            if tab_name not in tab_widgets:
                continue

            # Find current index of this tab
            widget = tab_widgets[tab_name]
            current_index = self.ui.tabWidget.indexOf(widget)

            if current_index != -1 and current_index != target_index:
                # Move tab to target position
                self.ui.tabWidget.tabBar().moveTab(current_index, target_index)

        print(f"Restored tab order: {saved_order}")

    def _load_global_settings_ui(self):
        """Load global settings into the settings UI."""
        # Global settings path
        global_path = get_global_settings_path()
        self.ui.GlobalSettingsPathEdit.setText(global_path)
        self.ui.globalSettingsCurrentPath.setText(f"Current: {global_path}")

        # ComfyUI mode (0=embedded, 1=portable, 2=standalone)
        mode = get_comfyui_mode()
        mode_index = {"embedded": 0, "portable": 1, "standalone": 2}.get(mode, 0)
        self.ui.ComfyUIModeCombo.setCurrentIndex(mode_index)

        # ComfyUI path
        comfyui_path = get_comfyui_path()
        self.ui.ComfyUIPathEdit.setText(comfyui_path)

        # ComfyUI Python path
        python_path = get_comfyui_python_path()
        self.ui.ComfyUIPythonEdit.setText(python_path)

        # Update Python path field visibility based on mode
        self._update_comfyui_python_visibility()

        # Update current path display
        self._update_comfyui_current_path_display()

    def _update_comfyui_python_visibility(self):
        """Show/hide Python path field based on selected mode."""
        # 0=embedded, 1=portable, 2=standalone - only standalone needs custom Python path
        is_standalone = self.ui.ComfyUIModeCombo.currentIndex() == 2
        self.ui.ComfyUIPythonEdit.setEnabled(is_standalone)
        self.ui.BrowseComfyUIPython.setEnabled(is_standalone)
        mode_index = self.ui.ComfyUIModeCombo.currentIndex()
        if mode_index == 0:
            self.ui.ComfyUIPythonEdit.setPlaceholderText("(Uses python_embeded/python.exe)")
        elif mode_index == 1:
            self.ui.ComfyUIPythonEdit.setPlaceholderText("(Uses venv/Scripts/python.exe)")
        else:
            self.ui.ComfyUIPythonEdit.setPlaceholderText("Path to Python executable...")

    def _update_comfyui_current_path_display(self):
        """Update the current path display label."""
        mode_index = self.ui.ComfyUIModeCombo.currentIndex()
        mode_names = {0: "Embedded", 1: "Portable", 2: "Standalone"}
        mode = mode_names.get(mode_index, "Embedded")
        comfyui_path = self.ui.ComfyUIPathEdit.text() or get_comfyui_path()
        python_path = self.ui.ComfyUIPythonEdit.text() or get_comfyui_python_path()

        if mode_index == 2:  # Standalone needs custom Python path
            self.ui.comfyuiCurrentPath.setText(f"Mode: {mode} | Path: {comfyui_path} | Python: {python_path}")
        else:
            self.ui.comfyuiCurrentPath.setText(f"Mode: {mode} | Path: {comfyui_path}")

    def on_comfyui_mode_changed(self, index):
        """Handle ComfyUI mode combo change."""
        self._update_comfyui_python_visibility()
        self._update_comfyui_current_path_display()

    def on_browse_global_settings_path(self):
        """Browse for global settings directory."""
        current_path = self.ui.GlobalSettingsPathEdit.text() or get_global_settings_path()
        if not current_path:
            current_path = get_last_browse_directory("global_settings")
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Global Settings Directory",
            current_path
        )
        if directory:
            self.ui.GlobalSettingsPathEdit.setText(directory)
            set_last_browse_directory("global_settings", directory)

    def on_browse_comfyui_path(self):
        """Browse for ComfyUI installation directory."""
        current_path = self.ui.ComfyUIPathEdit.text() or get_comfyui_path()
        if not current_path:
            current_path = get_last_browse_directory("comfyui_path")
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select ComfyUI Installation Directory",
            current_path
        )
        if directory:
            self.ui.ComfyUIPathEdit.setText(directory)
            self._update_comfyui_current_path_display()
            set_last_browse_directory("comfyui_path", directory)

    def on_browse_comfyui_python(self):
        """Browse for Python executable."""
        current_path = self.ui.ComfyUIPythonEdit.text() or ""
        if not current_path:
            current_path = get_last_browse_directory("comfyui_python")
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Python Executable",
            current_path,
            "Executable (*.exe);;All Files (*)"
        )
        if file_path:
            self.ui.ComfyUIPythonEdit.setText(file_path)
            self._update_comfyui_current_path_display()
            set_last_browse_directory("comfyui_python", os.path.dirname(file_path))

    def on_save_global_settings(self):
        """Save all global settings."""
        # Save global settings path
        new_global_path = self.ui.GlobalSettingsPathEdit.text().strip()
        if new_global_path:
            # Validate that the path exists or can be created
            if not os.path.exists(new_global_path):
                reply = QMessageBox.question(
                    self,
                    "Create Directory",
                    f"The directory '{new_global_path}' does not exist. Create it?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    try:
                        os.makedirs(new_global_path)
                        print(f"Created directory: {new_global_path}")
                    except Exception as e:
                        self.animator.show_error(f"Failed to create directory: {e}")
                        return
                else:
                    return

            set_global_settings_path(new_global_path)
            self.ui.globalSettingsCurrentPath.setText(f"Current: {new_global_path}")

        # Save ComfyUI mode (0=embedded, 1=portable, 2=standalone)
        mode_map = {0: "embedded", 1: "portable", 2: "standalone"}
        mode = mode_map.get(self.ui.ComfyUIModeCombo.currentIndex(), "embedded")
        set_comfyui_mode(mode)

        # Save ComfyUI path
        new_comfyui_path = self.ui.ComfyUIPathEdit.text().strip()
        if new_comfyui_path:
            set_comfyui_path(new_comfyui_path)

        # Save ComfyUI Python path (for standalone mode)
        new_python_path = self.ui.ComfyUIPythonEdit.text().strip()
        set_comfyui_python_path(new_python_path)

        self._update_comfyui_current_path_display()
        self.animator.show_success("Global settings saved")

        # Refresh workflow presets since they may come from a new location
        self._refresh_workflow_preset_combo()

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
        # Use last browsed directory or default to user's Videos folder
        default_dir = get_last_browse_directory("mp4_custom")
        if not default_dir:
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
            set_last_browse_directory("mp4_custom", custom_dir)

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

        # Use last browsed directory or default to user's Videos folder
        last_dir = get_last_browse_directory("mp4_output")
        if not last_dir:
            last_dir = os.path.join(os.path.expanduser("~"), "Videos")

        # Open file dialog with default location
        output_file, _ = QFileDialog.getSaveFileName(
            None,
            "Save MP4 As",
            os.path.join(last_dir, default_filename),
            "MP4 Video (*.mp4)"
        )

        if output_file:
            app_state.mp4_output_path = output_file
            self.ui.MP4OutputPath.setText(app_state.mp4_output_path)
            self.ui.MP4OutputPath.setStyleSheet("color: white; font-size: 9pt;")
            set_last_browse_directory("mp4_output", os.path.dirname(output_file))

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
        # Use last browsed directory or default to user's Videos folder
        default_path = get_last_browse_directory("republish_custom")
        if not default_path:
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
            set_last_browse_directory("republish_custom", custom_dir)

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

    def _init_comfyui_tab(self):
        """Initialize ComfyUI tab state."""
        self._comfyui_dynamic_widgets = {}
        self._current_preset_name = None

        # Connect workflow preset signals
        self.ui.ComfyUIChoosePreset.clicked.connect(self._on_choose_preset_clicked)
        self.ui.ComfyUIAddPreset.clicked.connect(self.on_comfyui_add_preset)
        self.ui.ComfyUIDeletePreset.clicked.connect(self.on_comfyui_delete_preset)
        self.ui.ComfyUIBrowseOutputDir.clicked.connect(self.on_comfyui_browse_output_dir)
        self.ui.ComfyUIOutputDir.textChanged.connect(self.on_comfyui_validate_inputs)
        self.ui.ComfyUISubmit.clicked.connect(self.on_comfyui_submit)
        self.ui.ComfyUIGenerationCount.valueChanged.connect(self._on_comfyui_generation_count_changed)
        self.ui.ComfyUISeed.valueChanged.connect(self._on_comfyui_seed_changed)
        self.ui.ComfyUIRandomizeSeed.clicked.connect(self._on_comfyui_randomize_seed)
        self.ui.ComfyUIRandomizeSeed.setIcon(IconManager.get_icon("dice", TAB_COLORS["comfyui"], 16))
        self.ui.ComfyUIServerMode.stateChanged.connect(self._on_comfyui_server_mode_changed)

        # Restore saved state
        self._restore_comfyui_state()

        # Initial validation
        self.on_comfyui_validate_inputs()

    def _on_comfyui_generation_count_changed(self, value):
        """Handle generation count change."""
        self.on_comfyui_validate_inputs()
        self._save_comfyui_state()

    def _on_comfyui_seed_changed(self, value):
        """Handle seed value change."""
        self._save_comfyui_state()

    def _on_comfyui_randomize_seed(self):
        """Generate a new random seed."""
        import random
        new_seed = random.randint(0, 2147483647)
        self.ui.ComfyUISeed.setValue(new_seed)

    def _on_comfyui_server_mode_changed(self, state):
        """Handle server mode checkbox change."""
        self._save_comfyui_state()

    def _save_comfyui_state(self):
        """Save the current ComfyUI tab state to user settings."""
        state = {
            "workflow_preset": self._current_preset_name or "",
            "output_directory": self.ui.ComfyUIOutputDir.text(),
            "generation_count": self.ui.ComfyUIGenerationCount.value(),
            "seed": self.ui.ComfyUISeed.value(),
            "server_mode": self.ui.ComfyUIServerMode.isChecked(),
        }

        # Save editable node values
        editable_values = {}
        for node_id, container in self._comfyui_dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget:
                if hasattr(input_widget, 'toPlainText'):
                    # Text widget
                    editable_values[str(node_id)] = input_widget.toPlainText()
                elif hasattr(input_widget, 'text'):
                    # Line edit
                    editable_values[str(node_id)] = input_widget.text()
                # Note: Don't save image selections as they're typically session-specific

        state["editable_values"] = editable_values

        save_comfyui_tab_state(state)

    def _restore_comfyui_state(self):
        """Restore the ComfyUI tab state from user settings."""
        state = get_comfyui_tab_state()
        if not state:
            # No saved state - use defaults
            if app_state.shotpath:
                default_output = os.path.join(app_state.shotpath, "comfyui_output")
                self.ui.ComfyUIOutputDir.setText(default_output)
            return

        # Restore workflow preset selection
        preset_name = state.get("workflow_preset", "")
        if preset_name:
            # Check if preset still exists
            presets = get_comfyui_workflow_presets()
            if preset_name in presets:
                self._select_preset(preset_name)

        # Restore output directory
        output_dir = state.get("output_directory", "")
        if output_dir:
            self.ui.ComfyUIOutputDir.setText(output_dir)
        elif app_state.shotpath:
            default_output = os.path.join(app_state.shotpath, "comfyui_output")
            self.ui.ComfyUIOutputDir.setText(default_output)

        # Restore generation count
        gen_count = state.get("generation_count", 1)
        self.ui.ComfyUIGenerationCount.setValue(gen_count)

        # Restore seed (generate random if not saved)
        import random
        seed = state.get("seed", random.randint(0, 2147483647))
        self.ui.ComfyUISeed.setValue(seed)

        # Restore server mode
        server_mode = state.get("server_mode", False)
        self.ui.ComfyUIServerMode.setChecked(server_mode)

        # Store editable values to apply after widgets are created
        self._pending_editable_values = state.get("editable_values", {})

    def _setup_tab_icons(self):
        """Setup colorful icons for each tab."""
        # Tab icons disabled
        pass

    def _setup_button_icons(self):
        """Setup icons for icon-only buttons."""
        # Icons removed from text buttons (BuildPasses, MP4Generate, RePublishPublish, ComfyUISubmit)
        # Only icon-only buttons retain their icons (e.g., ComfyUIRandomizeSeed)
        pass

    def _disable_scroll_wheel_on_inputs(self):
        """Disable scroll wheel on combo boxes and spin boxes to prevent accidental changes."""
        # Find all combo boxes and spin boxes in the UI
        for combo in self.ui.findChildren(QtWidgets.QComboBox):
            combo.setFocusPolicy(Qt.StrongFocus)
            combo.wheelEvent = lambda event: event.ignore()

        for spinbox in self.ui.findChildren(QtWidgets.QSpinBox):
            spinbox.setFocusPolicy(Qt.StrongFocus)
            spinbox.wheelEvent = lambda event: event.ignore()

        for spinbox in self.ui.findChildren(QtWidgets.QDoubleSpinBox):
            spinbox.setFocusPolicy(Qt.StrongFocus)
            spinbox.wheelEvent = lambda event: event.ignore()

    def _restore_tab_order(self):
        """Restore the saved order of tabs."""
        pass # To be implemented with settings_manager

    def _check_admin_status(self):
        """Check if current user is an admin and cache the result."""
        self._is_admin = app_state.is_admin
        if self._is_admin:
            print(f"User '{app_state.user}' has admin privileges")
        else:
            print(f"User '{app_state.user}' is a regular user (restricted tabs hidden)")

    def _hide_restricted_tabs(self):
        """Hide admin-only tabs for non-admin users."""
        if self._is_admin:
            return  # Admin sees all tabs

        tabs_to_hide = ["comfyui", "settings"]
        indices_to_remove = []

        for i in range(self.ui.tabWidget.count()):
            widget = self.ui.tabWidget.widget(i)
            if widget and widget.objectName() in tabs_to_hide:
                indices_to_remove.append(i)

        # Remove tabs from highest index to lowest to preserve indices
        for i in sorted(indices_to_remove, reverse=True):
            tab_name = self.ui.tabWidget.widget(i).objectName()
            self.ui.tabWidget.removeTab(i)
            print(f"Hid restricted tab: {tab_name}")

    def _load_admin_users_ui(self):
        """Load admin users into the settings list widget."""
        if not hasattr(self.ui, 'AdminUsersList'):
            return

        self.ui.AdminUsersList.clear()
        admin_users = get_admin_users()

        for username in sorted(admin_users):
            item = QtWidgets.QListWidgetItem(username)
            # Highlight current user
            if username.lower() == app_state.user.lower():
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setToolTip("(You)")
            self.ui.AdminUsersList.addItem(item)

        print(f"Loaded {len(admin_users)} admin users")

    def on_add_admin_user(self):
        """Add a user to the admin list via input dialog."""
        username, ok = QInputDialog.getText(
            self,
            "Add Admin User",
            "Enter username to add as admin:"
        )

        if ok and username:
            username = username.strip()
            if not username:
                self.animator.show_error("Username cannot be empty")
                return

            add_admin_user(username)
            self._load_admin_users_ui()
            self.animator.show_success(f"Added admin user: {username}")

    def on_remove_admin_user(self):
        """Remove selected user from the admin list."""
        selected_items = self.ui.AdminUsersList.selectedItems()

        if not selected_items:
            self.animator.show_error("Select a user to remove")
            return

        username = selected_items[0].text()

        # Warn if removing self
        if username.lower() == app_state.user.lower():
            reply = QMessageBox.warning(
                self,
                "Remove Yourself?",
                "You are about to remove yourself from the admin list.\n"
                "You will lose access to admin features after restarting.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        remove_admin_user(username)
        self._load_admin_users_ui()
        self.animator.show_success(f"Removed admin user: {username}")

    def _on_choose_preset_clicked(self):
        """Show popup menu with available workflow presets."""
        menu = QMenu(self)

        presets = get_comfyui_workflow_presets()
        if not presets:
            action = menu.addAction("No presets available")
            action.setEnabled(False)
        else:
            for name in sorted(presets.keys()):
                action = menu.addAction(name)
                action.setData(name)
                # Mark current preset with a checkmark
                if name == self._current_preset_name:
                    action.setCheckable(True)
                    action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.ComfyUIChoosePreset.mapToGlobal(
            self.ui.ComfyUIChoosePreset.rect().bottomLeft()
        ))

        if action and action.data():
            self._select_preset(action.data())

    def _select_preset(self, preset_name):
        """Select a workflow preset by name."""
        workflow_path = get_comfyui_workflow_preset_path(preset_name)
        if workflow_path and os.path.exists(workflow_path):
            self._current_preset_name = preset_name
            self.ui.ComfyUICurrentPreset.setText(preset_name)
            self.ui.ComfyUIWorkflowPath.setText(workflow_path)
            app_state.comfyui_workflow_path = workflow_path
            self._refresh_comfyui_editable_nodes()
            self.on_comfyui_validate_inputs()
            self._save_comfyui_state()
        else:
            self.animator.show_error(f"Workflow file not found: {workflow_path}")
            self.ui.ComfyUIWorkflowPath.setText("Workflow file not found")
            self.ui.ComfyUICurrentPreset.setText("No preset selected")
            self._current_preset_name = None
            app_state.comfyui_workflow_path = None
            self.on_comfyui_validate_inputs()

    def on_comfyui_add_preset(self):
        """Add a new workflow preset."""
        # Use last browsed directory for workflows
        last_dir = get_last_browse_directory("comfyui_workflow")
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select ComfyUI Workflow", last_dir, "ComfyUI JSON (*.json)"
        )
        if not file_path:
            return
        set_last_browse_directory("comfyui_workflow", os.path.dirname(file_path))

        # Then ask for a preset name
        name, ok = QInputDialog.getText(
            self, "Add Workflow Preset",
            "Enter a name for this workflow preset:"
        )
        if not ok or not name:
            return

        name = name.strip()
        if not name:
            self.animator.show_error("Preset name cannot be empty")
            return

        # Check if preset already exists
        presets = get_comfyui_workflow_presets()
        if name in presets:
            reply = QMessageBox.question(
                self, "Overwrite Preset",
                f"Preset '{name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Save the preset and select it
        save_comfyui_workflow_preset(name, file_path)
        self._select_preset(name)
        self.animator.show_success(f"Workflow preset '{name}' saved")

    def on_comfyui_delete_preset(self):
        """Delete the currently selected workflow preset."""
        if not self._current_preset_name:
            self.animator.show_error("No preset selected")
            return

        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Delete workflow preset '{self._current_preset_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            deleted_name = self._current_preset_name
            delete_comfyui_workflow_preset(self._current_preset_name)
            self._current_preset_name = None
            self.ui.ComfyUICurrentPreset.setText("No preset selected")
            self.ui.ComfyUIWorkflowPath.setText("No workflow selected")
            app_state.comfyui_workflow_path = None
            self._refresh_comfyui_editable_nodes()
            self.on_comfyui_validate_inputs()
            self.animator.show_info(f"Preset '{deleted_name}' deleted")

    def _refresh_comfyui_editable_nodes(self):
        """Refresh dynamic UI widgets based on editable nodes in the workflow."""
        # Clear layout
        layout = self.ui.comfyuiEditableNodesLayout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._comfyui_dynamic_widgets = {}

        if not app_state.comfyui_workflow_path:
            return

        editable_nodes = extract_editable_nodes(app_state.comfyui_workflow_path)
        for node in editable_nodes:
            widget = self._create_editable_node_widget(node)
            if widget:
                layout.addWidget(widget)
                self._comfyui_dynamic_widgets[node.node_id] = widget

        # Apply any pending editable values from restored state
        self._apply_pending_editable_values()

    def _apply_pending_editable_values(self):
        """Apply pending editable values that were saved from a previous session."""
        if not hasattr(self, '_pending_editable_values') or not self._pending_editable_values:
            return

        for node_id_str, value in self._pending_editable_values.items():
            try:
                node_id = int(node_id_str)
                if node_id in self._comfyui_dynamic_widgets:
                    container = self._comfyui_dynamic_widgets[node_id]
                    input_widget = getattr(container, 'input_widget', None)
                    if input_widget:
                        if hasattr(input_widget, 'setPlainText'):
                            input_widget.setPlainText(value)
                        elif hasattr(input_widget, 'setText'):
                            input_widget.setText(value)
            except (ValueError, AttributeError) as e:
                print(f"Could not restore value for node {node_id_str}: {e}")

        # Clear pending values after applying
        self._pending_editable_values = {}

    def _create_editable_node_widget(self, node):
        """Create a widget for an editable node."""
        container = QWidget()
        layout = QVBoxLayout(container)
        label = QLabel(f"{node.display_name}:")
        layout.addWidget(label)

        if node.widget_type == 'text':
            # Add preset row
            preset_row = QHBoxLayout()
            preset_combo = QComboBox()
            preset_combo.setMinimumWidth(150)
            self._refresh_preset_combo(preset_combo)
            preset_row.addWidget(QLabel("Preset:"))
            preset_row.addWidget(preset_combo, 1)

            save_btn = QPushButton("Save")
            save_btn.setFixedWidth(100)
            delete_btn = QPushButton("Delete")
            delete_btn.setFixedWidth(100)
            preset_row.addWidget(save_btn)
            preset_row.addWidget(delete_btn)
            layout.addLayout(preset_row)

            # Text input with spell checking
            input_widget = SpellCheckTextEdit()
            input_widget.setMinimumHeight(60)
            if node.current_value:
                input_widget.setPlainText(str(node.current_value))
            layout.addWidget(input_widget)
            container.input_widget = input_widget
            container.preset_combo = preset_combo

            # Connect preset signals
            preset_combo.currentTextChanged.connect(
                lambda text, w=input_widget, c=preset_combo: self._on_preset_selected(text, w, c)
            )
            save_btn.clicked.connect(
                lambda checked=False, w=input_widget, c=preset_combo: self._on_save_preset(w, c)
            )
            delete_btn.clicked.connect(
                lambda checked=False, c=preset_combo: self._on_delete_preset(c)
            )
            # Save state when text changes (with delay to avoid too many saves)
            input_widget.textChanged.connect(self._on_comfyui_text_changed)

        elif node.widget_type == 'image':
            input_widget = BatchImageSelector()
            # Set last browse directory for image selector
            last_dir = get_last_browse_directory("comfyui_images")
            if last_dir:
                input_widget.set_last_browse_dir(last_dir)
            # Save directory when images are added
            input_widget.images_changed.connect(self._on_comfyui_images_changed)
            layout.addWidget(input_widget)
            container.input_widget = input_widget
        else:
            input_widget = QLineEdit()
            if node.current_value:
                input_widget.setText(str(node.current_value))
            input_widget.textChanged.connect(self._on_comfyui_text_changed)
            layout.addWidget(input_widget)
            container.input_widget = input_widget

        return container

    def _refresh_preset_combo(self, combo):
        """Refresh preset combo box with saved presets."""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("-- Select Preset --")
        presets = get_comfyui_text_presets()
        for name in sorted(presets.keys()):
            combo.addItem(name)
        combo.blockSignals(False)

    def _on_preset_selected(self, text, text_widget, combo):
        """Handle preset selection from combo box."""
        if text == "-- Select Preset --":
            return
        presets = get_comfyui_text_presets()
        if text in presets:
            text_widget.setPlainText(presets[text])

    def _on_save_preset(self, text_widget, combo):
        """Save current text as a new preset."""
        print(f"_on_save_preset called with text_widget={text_widget}, combo={combo}")
        current_text = text_widget.toPlainText().strip()
        if not current_text:
            self.animator.show_error("Cannot save empty preset")
            return

        # Create and show dialog explicitly to ensure it appears
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Save Preset")
        dialog.setLabelText("Preset name:")
        dialog.setTextValue("")
        dialog.setWindowModality(Qt.WindowModal)

        if dialog.exec_() == QInputDialog.Accepted:
            name = dialog.textValue().strip()
            if not name:
                self.animator.show_error("Preset name cannot be empty")
                return
            save_comfyui_text_preset(name, current_text)
            self._refresh_preset_combo(combo)
            combo.setCurrentText(name)
            self.animator.show_success(f"Preset '{name}' saved")

    def _on_delete_preset(self, combo):
        """Delete the currently selected preset."""
        print(f"_on_delete_preset called with combo={combo}")
        current = combo.currentText()
        if current == "-- Select Preset --":
            self.animator.show_error("No preset selected")
            return

        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Delete preset '{current}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            delete_comfyui_text_preset(current)
            self._refresh_preset_combo(combo)
            self.animator.show_info(f"Preset '{current}' deleted")

    def _on_comfyui_text_changed(self):
        """Handle text change in editable nodes - save state with debounce."""
        # Use a timer to debounce saves (avoid saving on every keystroke)
        if not hasattr(self, '_comfyui_save_timer'):
            self._comfyui_save_timer = QTimer(self)
            self._comfyui_save_timer.setSingleShot(True)
            self._comfyui_save_timer.timeout.connect(self._save_comfyui_state)
        # Restart timer on each change (500ms debounce)
        self._comfyui_save_timer.start(500)

    def _on_comfyui_images_changed(self, images):
        """Handle image selection changes - save the last browse directory."""
        if images:
            # Save the directory from the first image
            last_dir = os.path.dirname(images[0])
            set_last_browse_directory("comfyui_images", last_dir)

    def on_comfyui_browse_output_dir(self):
        """Browse for ComfyUI output directory."""
        current_path = self.ui.ComfyUIOutputDir.text()
        if not current_path:
            current_path = get_last_browse_directory("comfyui_output")
        if not current_path and app_state.shotpath:
            current_path = app_state.shotpath

        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            current_path or ""
        )
        if directory:
            self.ui.ComfyUIOutputDir.setText(directory)
            set_last_browse_directory("comfyui_output", directory)
            self._save_comfyui_state()

    def on_comfyui_validate_inputs(self):
        """Validate inputs and enable/disable submit button."""
        workflow_ok = bool(app_state.comfyui_workflow_path)
        output_ok = bool(self.ui.ComfyUIOutputDir.text().strip())
        self.ui.ComfyUISubmit.setEnabled(workflow_ok and output_ok)

    def on_comfyui_submit(self):
        """Submit the workflow to ComfyUI/Deadline."""
        # Validate workflow
        if not app_state.comfyui_workflow_path:
            self.animator.show_error("No workflow selected")
            return

        # Validate output directory
        output_dir = self.ui.ComfyUIOutputDir.text().strip()
        if not output_dir:
            self.animator.show_error("No output directory selected")
            return

        # Get generation count from UI
        generation_count = self.ui.ComfyUIGenerationCount.value()

        # Collect editable values from dynamic widgets
        editable_values = {}
        editable_nodes = extract_editable_nodes(app_state.comfyui_workflow_path)

        for node in editable_nodes:
            node_id = node.node_id
            if node_id in self._comfyui_dynamic_widgets:
                container = self._comfyui_dynamic_widgets[node_id]
                input_widget = getattr(container, 'input_widget', None)
                if input_widget:
                    if node.widget_type == 'text':
                        value = input_widget.toPlainText().strip()
                    elif node.widget_type == 'image':
                        # BatchImageSelector stores files in selected_files
                        value = getattr(input_widget, 'selected_files', [])
                    else:
                        value = input_widget.text().strip() if hasattr(input_widget, 'text') else str(node.current_value)

                    editable_values[node_id] = {'node': node, 'value': value}

        # Build job name from shot/project
        job_name = f"{app_state.shot}_comfyui" if app_state.shot else "comfyui_job"

        # Show loading overlay
        self.animator.show_loading(
            "Submitting to ComfyUI",
            f"Preparing {generation_count} generation(s)...",
            show_progress=True
        )
        self.animator.animate_button_click(self.ui.ComfyUISubmit)

        def on_result(result):
            """Called when submission completes."""
            self.animator.hide_loading()
            job_ids, error_msg = result

            if job_ids:
                job_count = len(job_ids)
                total_gens = job_count * generation_count
                self.animator.show_success(f"Submitted {job_count} job(s), {total_gens} generations")
                self.animator.update_status_animated(
                    f"ComfyUI: {job_count} job(s) submitted",
                    StatusColors.SUCCESS
                )
                print(f"ComfyUI submission complete: {job_ids}")
            else:
                self.animator.show_error(f"Submission failed: {error_msg}")
                self.animator.update_status_animated(
                    f"ComfyUI failed: {error_msg}",
                    StatusColors.ERROR
                )

        def on_error(error_msg, traceback_str):
            """Called when submission fails."""
            self.animator.hide_loading()
            self.animator.show_error(f"Submission error: {error_msg}")
            self.animator.update_status_animated(
                f"ComfyUI error: {error_msg}",
                StatusColors.ERROR
            )
            print(f"ComfyUI submission error: {error_msg}")
            print(traceback_str)

        def on_progress(progress, message):
            """Called for progress updates."""
            self.animator.update_loading_message(message)
            self.animator.update_loading_progress(progress)

        # Get server mode setting
        use_server_mode = self.ui.ComfyUIServerMode.isChecked()

        # Get seed value
        base_seed = self.ui.ComfyUISeed.value()

        # Create worker and run submission on background thread
        worker = Worker(
            submit_comfyui_job,
            workflow_path=app_state.comfyui_workflow_path,
            input_image=None,  # Using editable_values instead
            prompt=None,  # Using editable_values instead
            output_dir=output_dir,
            generation_count=generation_count,
            job_name=job_name,
            editable_values=editable_values,
            use_server_mode=use_server_mode,
            base_seed=base_seed,
        )
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(on_progress)
        QThreadPool.globalInstance().start(worker)

    def on_clear_log(self):
        """Clear the terminal log output."""
        self.ui.LogOutput.clear()
        self.animator.show_info("Log cleared")


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
