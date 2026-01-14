"""
Luma Shot Tools - Main Application.

VFX shot management application for the Luma Animation pipeline.
Handles render pass management, AYON publishing, Deadline farm submission,
and lookdev file cleanup for shot-based workflows.

This is the refactored version using the modular tab system.
"""

import sys
import os

from core.config import APP_ID, APP_TITLE, ICON_PATH, DEADLINE_PATH, OIIO_PATH, OIIO_INFO_ROOT, FFMPEG_PATH

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

# Suppress NumPy compatibility warnings from PySide6/shiboken6
import warnings
warnings.filterwarnings("ignore", message=".*NumPy.*")

# Disable QtWebEngine sandbox when running from network paths
# (Chromium sandbox doesn't work with UNC/network paths)
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

# PySide6 imports
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QColor, QPen
from PySide6.QtWidgets import QApplication, QTabBar

# Import UI components
from ui_components import enhance_ui, apply_stylesheet, LoadingStyles, TabGlowManager, InlineSpinner
from splash_screen import SplashScreen
from icons import IconManager, TAB_COLORS, DEFAULT_ICON_COLOR

# Import state manager
from core.state_manager import app_state

# Import tab configuration
from tabs import TAB_CONFIG

# Initialize application state from command line arguments
app_state.initialize_from_args(sys.argv)

# Application instance
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

# Qt6: Increase image allocation limit for large render images
# Default is 256MB, increase to 2GB for VFX work with large EXR/PNG files
from PySide6.QtGui import QImageReader
QImageReader.setAllocationLimit(2048)  # 2GB in megabytes

# Configure OpenGL surface format globally before any OpenGL widgets are created
# This prevents window flashing when 3D viewer initializes
try:
    from PySide6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setVersion(2, 1)  # OpenGL 2.1
    fmt.setProfile(QSurfaceFormat.NoProfile)
    fmt.setSamples(4)  # 4x MSAA
    fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
    QSurfaceFormat.setDefaultFormat(fmt)
    print("OpenGL surface format configured")
except Exception as e:
    print(f"Warning: Could not configure OpenGL surface format: {e}")

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


class ExpandingTabBar(QTabBar):
    """Custom tab bar that expands tabs to fill the available width."""

    # Padding on each side of the tab bar
    HORIZONTAL_PADDING = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        # Don't use Qt's expanding - we'll handle it ourselves
        self.setExpanding(False)
        # Disable scroll buttons so all tabs are always visible
        self.setUsesScrollButtons(False)
        # Enable document mode for cleaner look
        self.setDocumentMode(True)

    def tabSizeHint(self, index):
        """Calculate tab size to fill the tab bar width evenly."""
        # Get the default size for height
        default_size = super().tabSizeHint(index)

        # Get number of tabs
        tab_count = self.count()
        if tab_count <= 0:
            return default_size

        # Get parent tab widget width
        parent = self.parentWidget()
        if parent:
            available_width = parent.width() - (self.HORIZONTAL_PADDING * 2)
        else:
            available_width = self.width() - (self.HORIZONTAL_PADDING * 2)

        # If width is too small (during init), use a reasonable default
        if available_width < 200:
            return default_size

        # Calculate width per tab - equal distribution
        tab_width = available_width // tab_count

        # Ensure minimum width
        tab_width = max(80, tab_width)

        return QtCore.QSize(tab_width, default_size.height())

    def showEvent(self, event):
        """Force size recalculation when tab bar is shown."""
        super().showEvent(event)
        # Defer the update to after the widget is fully shown
        QtCore.QTimer.singleShot(0, self.updateGeometry)


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
        self.tab_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )

        # Use custom expanding tab bar
        expanding_tab_bar = ExpandingTabBar(self.tab_widget)
        self.tab_widget.setTabBar(expanding_tab_bar)

        # Enable tab reordering (must be after setTabBar, as it replaces the tab bar)
        self.tab_widget.setMovable(True)

        layout.addWidget(self.tab_widget, 1)  # stretch factor 1 to expand

        # Create status bar with left status and right log message
        status_layout = QtWidgets.QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(10)

        # Status spinner (hidden by default, shown during long operations)
        self.status_spinner = InlineSpinner(size=16)
        status_layout.addWidget(self.status_spinner, 0)

        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setObjectName("StatusLabel")
        status_layout.addWidget(self.status_label, 0)

        status_layout.addStretch(1)

        self.last_log_label = QtWidgets.QLabel("")
        self.last_log_label.setObjectName("LastLogLabel")
        self.last_log_label.setStyleSheet("color: #888888; font-size: 11px;")
        status_layout.addWidget(self.last_log_label, 0)

        status_widget = QtWidgets.QWidget()
        status_widget.setLayout(status_layout)
        layout.addWidget(status_widget, 0)  # stretch factor 0

        # Instantiate and load each tab
        for tab_config in TAB_CONFIG:
            tab_class = tab_config['class']
            restrict_key = tab_config['restrict_key']

            # Skip ComfyUI and Gallery tabs for non-admin users (don't even initialize them)
            if not app_state.is_admin and restrict_key in ['comfyui', 'comfyui_gallery']:
                print(f"Skipping initialization of '{restrict_key}' tab for non-admin user")
                continue

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

        # Update last log label in status bar (truncate if too long)
        if hasattr(self, 'last_log_label'):
            clean_msg = message.strip()
            if len(clean_msg) > 80:
                clean_msg = clean_msg[:77] + "..."
            self.last_log_label.setText(clean_msg)

    def start_status_spinner(self):
        """Start the status bar spinner to indicate a background operation."""
        if hasattr(self, 'status_spinner'):
            self.status_spinner.start()

    def stop_status_spinner(self):
        """Stop the status bar spinner."""
        if hasattr(self, 'status_spinner'):
            self.status_spinner.stop()

    def _on_tab_request_attention(self, tab_instance):
        """Handle tab requesting attention with pulsing glow."""
        print(f"[TabAttention] _on_tab_request_attention called for tab '{tab_instance.tab_name}'")

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
        from core.settings_manager import save_tab_order

        tab_names = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            tab_names.append(widget.objectName())

        save_tab_order(tab_names)

    def _restore_tab_order(self):
        """Restore saved tab order on startup."""
        from core.settings_manager import get_tab_order

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
        from core.settings_manager import get_restricted_tabs

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

        # Republish tab is allowed in standalone mode (uses custom directory selection)
        standalone_incompatible = ['passbuilder', 'shotcleaner']

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
        from PySide6.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox

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
        painter.drawRoundedRect(self.rect(), 0, 0)

    def resizeEvent(self, event):
        """Handle window resize to update tab widths."""
        super().resizeEvent(event)
        # Force tab bar to recalculate sizes
        if hasattr(self, 'tab_widget'):
            self.tab_widget.tabBar().updateGeometry()

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
    import time

    try:
        # Show splash screen
        splash = SplashScreen()
        splash.show()
        splash.start_animation()
        app.processEvents()

        # Pre-load settings to populate cache before tabs initialize
        splash.update_progress(20, "Loading", "Loading settings...")
        app.processEvents()
        try:
            from core.settings_manager import load_user_settings, load_global_settings
            load_user_settings()  # Populate user settings cache
            load_global_settings()  # Populate global settings cache (may hit network)
        except Exception as e:
            print(f"Warning: Could not pre-load settings: {e}")

        # Pre-scan gallery directory on worker thread while splash shows
        splash.update_progress(30, "Loading", "Scanning gallery...")
        app.processEvents()

        # Shared state for progress updates from worker thread
        gallery_data = {
            'items': [],
            'done': False,
            'error': None,
            'progress': 0,
            'message': 'Starting scan...'
        }

        def progress_callback(pct, message):
            """Callback for progress updates from prewarm (runs on worker thread)."""
            # Map prewarm progress (0-100) to splash progress (30-75)
            gallery_data['progress'] = 30 + int(pct * 0.45)
            gallery_data['message'] = message

        def scan_gallery_worker():
            """Scan gallery directory (runs on worker thread)."""
            try:
                from ui.gallery_prewarm import prewarm_gallery
                result = prewarm_gallery(progress_callback=progress_callback)
                gallery_data['items'] = result.get('items', [])
                gallery_data['thumbnails_generated'] = result.get('thumbnails_generated', 0)
            except Exception as e:
                gallery_data['error'] = str(e)
                print(f"Warning: Gallery pre-scan failed: {e}")
            finally:
                gallery_data['done'] = True

        # Start worker thread for gallery scanning
        from PySide6.QtCore import QThreadPool, QRunnable

        class ScanWorker(QRunnable):
            def run(self):
                scan_gallery_worker()

        worker = ScanWorker()
        QThreadPool.globalInstance().start(worker)

        # Wait for gallery scan while keeping splash responsive
        last_message = ""
        while not gallery_data['done']:
            app.processEvents()
            time.sleep(0.016)  # ~60fps polling for smooth updates

            # Update splash with progress from worker thread
            current_progress = gallery_data['progress']
            current_message = gallery_data['message']
            if current_message != last_message:
                splash.update_progress(current_progress, "Loading", current_message)
                last_message = current_message

        # Show final count
        if gallery_data['items']:
            item_count = len(gallery_data['items'])
            thumb_count = gallery_data.get('thumbnails_generated', 0)
            if thumb_count > 0:
                splash.update_progress(75, "Loading", f"Found {item_count} items, generated {thumb_count} thumbnails")
            else:
                splash.update_progress(75, "Loading", f"Found {item_count} items")
            app.processEvents()

        # Store gallery data for the gallery tab to use
        try:
            from ui.gallery_prewarm import set_prewarm_cache
            set_prewarm_cache({'items': gallery_data['items']})
        except Exception as e:
            print(f"Warning: Could not set prewarm cache: {e}")

        # Pre-initialize Three.js viewer during splash to avoid window flicker
        # WebEngine initialization can cause visual glitches if done later
        splash.update_progress(78, "Loading", "Initializing 3D viewer...")
        app.processEvents()

        _threejs_prewarm_viewer = None
        try:
            from models.threejs_viewer import ThreeJSViewerWidget, is_threejs_viewer_available
            if is_threejs_viewer_available():
                # Create prewarm viewer with DontShowOnScreen attribute to prevent flashing
                _threejs_prewarm_viewer = ThreeJSViewerWidget(prewarm=True)
                # Give WebEngine time to fully initialize
                import time
                for _ in range(10):
                    app.processEvents()
                    time.sleep(0.05)
                print("Three.js viewer pre-initialized successfully")
        except Exception as e:
            print(f"Warning: Could not pre-initialize Three.js viewer: {e}")

        # Create main window
        splash.update_progress(88, "Loading", "Creating main window...")
        app.processEvents()

        window = LumaShotTools()

        # Store pre-warmed viewer on window to keep WebEngine alive
        if _threejs_prewarm_viewer is not None:
            window._threejs_prewarm_viewer = _threejs_prewarm_viewer

        splash.update_progress(95, "Loading", "Finalizing...")
        app.processEvents()

        # Close splash and show main window
        splash.stop_animation()
        splash.close()
        window.show()

        # Enable log redirection after window is shown
        window.enable_log_redirect()

        # Run the application
        sys.exit(app.exec())
    except Exception as e:
        print(f"ERROR in main: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
