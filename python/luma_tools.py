"""
Luma Shot Tools - Main Application.

VFX shot management application for the Luma Animation pipeline.
Handles render pass management, AYON publishing, Deadline farm submission,
and lookdev file cleanup for shot-based workflows.

This is the refactored version using the modular tab system.
"""

import sys
import os

from config import APP_ID, APP_TITLE, ICON_PATH, DEADLINE_PATH, OIIO_PATH, OIIO_INFO_ROOT, FFMPEG_PATH

# Set up Windows things
if sys.platform == 'win32':
    import ctypes
    kernel32 = ctypes.WinDLL('kernel32')
    user32 = ctypes.WinDLL('user32')
    SW_HIDE = 0
    hWnd = kernel32.GetConsoleWindow()
    user32.ShowWindow(hWnd, SW_HIDE)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    # Single instance check using Windows named mutex
    MUTEX_NAME = "Global\\LumaToolsSingleInstance"
    ERROR_ALREADY_EXISTS = 183

    mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = ctypes.get_last_error()

    if last_error == ERROR_ALREADY_EXISTS:
        # Another instance is already running - find and focus it
        WINDOW_TITLE_PREFIX = APP_TITLE
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
        GetWindowText = user32.GetWindowTextW
        GetWindowTextLength = user32.GetWindowTextLengthW
        IsWindowVisible = user32.IsWindowVisible
        SetForegroundWindow = user32.SetForegroundWindow
        ShowWindow = user32.ShowWindow
        SW_RESTORE = 9

        def foreach_window(hwnd, _lParam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLength(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowText(hwnd, buff, length + 1)
                    if buff.value.startswith(WINDOW_TITLE_PREFIX):
                        ShowWindow(hwnd, SW_RESTORE)
                        SetForegroundWindow(hwnd)
                        return False  # Stop enumeration
            return True

        EnumWindows(EnumWindowsProc(foreach_window), 0)
        sys.exit(0)

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Add paths
sys.path.append(os.path.join(PROJECT_ROOT, "python"))
sys.path.append(os.path.join(PROJECT_ROOT, "resources", "ui"))

# PySide2 imports
from PySide2 import QtCore, QtWidgets
from PySide2.QtCore import Qt
from PySide2.QtGui import QIcon, QPainter, QColor, QPen
from PySide2.QtWidgets import QApplication

# Import UI components
from ui_components import enhance_ui, apply_stylesheet, LoadingStyles, TabGlowManager
from splash_screen import SplashScreen
from icons import IconManager, TAB_COLORS, DEFAULT_ICON_COLOR

# Import state manager
from state_manager import app_state

# Import tab configuration
from tabs import TAB_CONFIG

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


class LogStream(QtCore.QObject):
    """Custom stream that redirects output to the log widget."""
    message_written = QtCore.Signal(str)

    def write(self, message):
        if message.strip():
            self.message_written.emit(message)

    def flush(self):
        pass


class LumaShotTools(QtWidgets.QWidget):
    """Main application window."""

    def __init__(self, parent=None):
        super(LumaShotTools, self).__init__()

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.parent = parent

        # Store tab instances
        self.tabs = {}
        self.logs_tab = None

        # Load UI using modular tab system
        self._load_tabs()

        # Set window title based on mode
        if app_state.standalone_mode:
            self.setWindowTitle(f"{APP_TITLE} - Standalone Mode")
        else:
            self.setWindowTitle(f"{APP_TITLE} - {app_state.jobname} - {app_state.shot}")
        self.setWindowIcon(QIcon(ICON_PATH))

        # Setup log redirection (deferred until after window is shown)
        self.log_stream = LogStream()
        self.log_stream.message_written.connect(self._append_log)
        self._log_redirect_pending = True

        # Check admin status
        self._check_admin_status()

        # Set initial window size and minimum size (user can resize/maximize)
        self.resize(1250, 1000)
        self.setMinimumSize(800, 600)

        # Setup animations
        self.animator = enhance_ui(self)
        self.animator.redirect_to_splash = False
        self.animator.splash_screen = None
        print("UI animations enabled")

        # Setup tab glow manager for attention notifications
        self.tab_glow_manager = TabGlowManager(self.tab_widget, self)

        # Setup colorful tab icons
        self._setup_tab_icons()

        # Restore saved tab order
        self._restore_tab_order()

        # Hide restricted tabs for non-admin users
        self._hide_restricted_tabs()

        # Hide tabs that require shot context in standalone mode
        self._hide_standalone_incompatible_tabs()

        # Disable scroll wheel on combo boxes and spin boxes
        self._disable_scroll_wheel_on_inputs()

        # Connect tab change signal
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabBar().tabMoved.connect(self._on_tab_moved)

    def _load_tabs(self):
        """Load all tabs using the modular tab system."""
        # Create main layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Create tab widget with expanding size policy
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setMovable(True)
        self.tab_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        layout.addWidget(self.tab_widget, 1)  # stretch factor 1 to expand

        # Create status bar (fixed height, doesn't expand)
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setObjectName("StatusLabel")
        layout.addWidget(self.status_label, 0)  # stretch factor 0

        # Instantiate and load each tab
        for tab_config in TAB_CONFIG:
            tab_class = tab_config['class']
            restrict_key = tab_config['restrict_key']

            # Create tab instance
            tab_instance = tab_class(self, app_state)

            # Load the tab's UI
            tab_widget = tab_instance.load_ui(self.tab_widget)
            tab_widget.setObjectName(restrict_key)

            # Add to tab widget
            self.tab_widget.addTab(tab_widget, tab_instance.tab_name)

            # Store reference
            self.tabs[restrict_key] = tab_instance

            # Connect tab signals
            tab_instance.connect_signals()

            # Connect cross-tab signals
            tab_instance.signals.log_message.connect(self._append_log)
            tab_instance.signals.show_loading.connect(self._on_tab_show_loading)
            tab_instance.signals.hide_loading.connect(self._on_tab_hide_loading)
            tab_instance.signals.request_attention.connect(
                lambda ti=tab_instance: self._on_tab_request_attention(ti)
            )

            # Initialize tab
            tab_instance.initialize()

            # Store special reference to logs tab
            if restrict_key == 'logs':
                self.logs_tab = tab_instance

        # Create a unified ui object for backward compatibility
        self._create_unified_ui()

    def _create_unified_ui(self):
        """Create a unified UI object that provides access to all widgets."""
        class UnifiedUI:
            pass

        self.ui = UnifiedUI()
        self.ui.tabWidget = self.tab_widget
        self.ui.StatusLabel = self.status_label

        # Copy all widget references from each tab to the unified UI
        for _, tab_instance in self.tabs.items():
            if tab_instance.ui:
                for child in tab_instance.ui.findChildren(QtWidgets.QWidget):
                    name = child.objectName()
                    if name and not name.startswith("qt_"):
                        setattr(self.ui, name, child)
                for child in tab_instance.ui.findChildren(QtWidgets.QLayout):
                    name = child.objectName()
                    if name and not name.startswith("qt_"):
                        setattr(self.ui, name, child)

    @QtCore.Slot(str)
    def _append_log(self, message):
        """Append a message to the log output widget."""
        if self.logs_tab:
            self.logs_tab.append_log(message)

    @QtCore.Slot(str)
    def _on_tab_show_loading(self, message):
        """Show loading overlay when requested by a tab."""
        if hasattr(self, 'animator'):
            self.animator.show_loading("Loading", message)

    @QtCore.Slot()
    def _on_tab_hide_loading(self):
        """Hide loading overlay when requested by a tab."""
        if hasattr(self, 'animator'):
            self.animator.hide_loading()

    def _on_tab_request_attention(self, tab_instance):
        """Handle tab requesting attention with pulsing glow."""
        from settings_manager import get_tab_flashing_enabled

        print(f"[TabAttention] _on_tab_request_attention called for tab '{tab_instance.tab_name}'")

        # Check if tab flashing is enabled in settings
        flashing_enabled = get_tab_flashing_enabled()
        print(f"[TabAttention] Tab flashing enabled: {flashing_enabled}")
        if not flashing_enabled:
            print(f"Tab '{tab_instance.tab_name}' requested attention (flashing disabled)")
            return

        if not hasattr(self, 'tab_glow_manager'):
            print(f"[TabAttention] ERROR: No tab_glow_manager!")
            return

        # Find the tab index for this tab instance
        tab_index = self.tab_widget.indexOf(tab_instance.ui)
        print(f"[TabAttention] Tab index: {tab_index}, current index: {self.tab_widget.currentIndex()}")
        if tab_index == -1:
            print(f"[TabAttention] ERROR: Tab not found in tab_widget!")
            return

        # Use tab-specific color for glow
        tab_id = tab_instance.tab_id
        color = TAB_COLORS.get(tab_id, DEFAULT_ICON_COLOR)
        print(f"[TabAttention] Starting glow for tab_id={tab_id}, color={color}")

        # Start the glow effect
        self.tab_glow_manager.start_glow(tab_index, color)
        print(f"Tab '{tab_instance.tab_name}' is requesting attention")

    def _on_tab_changed(self, index):
        """Handle tab change - notify tabs."""
        # Get previous and current tab
        for _, tab_instance in self.tabs.items():
            tab_index = self.tab_widget.indexOf(tab_instance.ui)
            if tab_index == index:
                tab_instance.on_tab_activated()
            else:
                tab_instance.on_tab_deactivated()

    def _on_tab_moved(self, _from_index, _to_index):
        """Save tab order when user reorders tabs."""
        from settings_manager import save_tab_order

        tab_names = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            tab_names.append(widget.objectName())

        save_tab_order(tab_names)
        print(f"Tab order saved: {tab_names}")

    def _restore_tab_order(self):
        """Restore saved tab order on startup."""
        from settings_manager import get_tab_order

        saved_order = get_tab_order()
        if not saved_order:
            self.tab_widget.setCurrentIndex(0)
            return

        # Build a map of tab name to widget
        tab_widgets = {}
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            tab_widgets[widget.objectName()] = widget

        # Reorder tabs based on saved order
        for target_index, tab_name in enumerate(saved_order):
            if tab_name not in tab_widgets:
                continue

            widget = tab_widgets[tab_name]
            current_index = self.tab_widget.indexOf(widget)

            if current_index != -1 and current_index != target_index:
                self.tab_widget.tabBar().moveTab(current_index, target_index)

        self.tab_widget.setCurrentIndex(0)
        print(f"Restored tab order: {saved_order}")

    def _check_admin_status(self):
        """Check if current user is an admin."""
        # Refresh and check admin status (property auto-computes from settings)
        app_state.refresh_admin_status()

        if app_state.is_admin:
            print(f"User '{app_state.user}' is an admin")
        else:
            print(f"User '{app_state.user}' is not an admin")

    def _hide_restricted_tabs(self):
        """Hide tabs that are restricted for non-admin users."""
        from settings_manager import get_restricted_tabs

        if app_state.is_admin:
            return

        restricted = get_restricted_tabs()
        if not restricted:
            return

        for i in range(self.tab_widget.count() - 1, -1, -1):
            widget = self.tab_widget.widget(i)
            if widget.objectName() in restricted:
                self.tab_widget.removeTab(i)
                print(f"Hidden restricted tab: {widget.objectName()}")

    def _hide_standalone_incompatible_tabs(self):
        """Hide tabs that require shot context in standalone mode."""
        if not app_state.standalone_mode:
            return

        standalone_incompatible = ['passbuilder', 'republish', 'shotcleaner']

        for i in range(self.tab_widget.count() - 1, -1, -1):
            widget = self.tab_widget.widget(i)
            if widget.objectName() in standalone_incompatible:
                self.tab_widget.removeTab(i)
                print(f"Hidden standalone-incompatible tab: {widget.objectName()}")

    def _setup_tab_icons(self):
        """Setup monochromatic icons for each tab."""
        tab_icons = {
            'passbuilder': 'layers',
            'mp4maker': 'video',
            'republish': 'upload',
            'shotcleaner': 'trash',
            'logs': 'terminal',
            'comfyui': 'sparkles',
            'comfyui_gallery': 'image',
            'settings': 'settings',
        }

        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            tab_id = widget.objectName()
            if tab_id in tab_icons:
                icon_name = tab_icons[tab_id]
                icon = IconManager.get_icon(icon_name, DEFAULT_ICON_COLOR, 16)
                self.tab_widget.setTabIcon(i, icon)

    def _disable_scroll_wheel_on_inputs(self):
        """Disable scroll wheel on combo boxes and spin boxes to prevent accidental changes."""
        from PySide2.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox

        for combo in self.findChildren(QComboBox):
            combo.wheelEvent = lambda e: e.ignore()

        for spin in self.findChildren(QSpinBox):
            spin.wheelEvent = lambda e: e.ignore()

        for spin in self.findChildren(QDoubleSpinBox):
            spin.wheelEvent = lambda e: e.ignore()

    def paintEvent(self, event):
        """Paint the rounded background and border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor(LoadingStyles.BACKGROUND_COLOR)
        bg_color.setAlpha(240)
        border_color = QColor(LoadingStyles.PRIMARY_COLOR)
        border_color.setAlpha(100)
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(self.rect(), LoadingStyles.BORDER_RADIUS, LoadingStyles.BORDER_RADIUS)

    def get_tab(self, tab_id):
        """Get a tab instance by ID."""
        return self.tabs.get(tab_id)

    def enable_log_redirect(self):
        """Enable stdout/stderr redirection to the log widget."""
        if getattr(self, '_log_redirect_pending', False):
            sys.stdout = self.log_stream
            sys.stderr = self.log_stream
            self._log_redirect_pending = False
            print("Log redirection enabled")


def main():
    """Main entry point."""
    import traceback

    try:
        # Show splash screen
        splash = SplashScreen()
        splash.show()
        app.processEvents()

        # Create main window
        window = LumaShotTools()

        # Close splash and show main window
        splash.close()
        window.show()

        # Enable log redirection after window is shown
        window.enable_log_redirect()

        # Run the application
        sys.exit(app.exec_())
    except Exception as e:
        print(f"ERROR in main: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
