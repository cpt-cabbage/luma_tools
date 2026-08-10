"""
Luma Shot Tools - Main Application.

VFX shot management application for the Luma Animation pipeline.
Handles render pass management, AYON publishing, Deadline farm submission,
and lookdev file cleanup for shot-based workflows.

Uses modular tab-based architecture with BaseTab pattern.
"""

import sys
import os
import logging

from core.config import APP_ID, APP_TITLE, APP_VERSION, ICON_PATH, DEADLINE_PATH, OIIO_PATH, OIIO_INFO_PATH, FFMPEG_PATH, IS_DEV_MODE
from core.logging_utils import setup_file_logging, cleanup_old_logs, setup_exception_hook, setup_polling_logger, get_network_log_dir, get_local_log_dir


# ============================================================================
# File Logging Setup (must be early to catch all errors)
# ============================================================================
# Initialize file logging immediately using centralized module
LOG_FILE = setup_file_logging(
    log_prefix="luma_tools",
    subdirectory="users",
    include_hostname=True,
    include_username=True,
    redirect_stdout=True,
    tee_mode="stream"
)

# Cleanup old log files
import socket
import getpass
username = getpass.getuser()
hostname = socket.gethostname()
log_dir = get_network_log_dir("users") or get_local_log_dir()
cleanup_old_logs(log_dir, f"luma_tools_{username}_{hostname}_", keep_count=5)

logging.info(f"=== Luma Tools Starting ===")

# Route polling logs to separate file to reduce main log noise
POLLING_LOG_FILE = setup_polling_logger()

# Install global exception hook
setup_exception_hook()

# Set up Windows things
if sys.platform == 'win32':
    import ctypes
    user32 = ctypes.WinDLL('user32')
    SW_HIDE = 0
    hWnd = ctypes.WinDLL('kernel32').GetConsoleWindow()
    user32.ShowWindow(hWnd, SW_HIDE)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

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

# Chromium flags to prevent GPU process window flash during initialization
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--in-process-gpu"

# PySide6 imports
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt, QtMsgType
from PySide6.QtGui import QIcon, QPainter, QColor, QPen
from PySide6.QtWidgets import QApplication, QTabBar

# Drop known cosmetic Qt warnings; route everything else through Python logging.
# Installed at module import (before any Qt widgets are created) so all
# early-init warnings hit the same handler that main() relies on.
_QT_NOISE_PATTERNS = (
    "QFont::setPointSize: Point size <= 0",
    "QThreadStorage: entry",
    "QDxgiVSyncService not destroyed in time",
    "sandbox",  # QtWebEngineProcess sandbox warnings
)

_QT_LEVEL_MAP = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


def _filtered_qt_message_handler(mode, context, message):
    text = str(message) if message else ""
    for pat in _QT_NOISE_PATTERNS:
        if pat in text:
            return
    logging.getLogger("Qt").log(_QT_LEVEL_MAP.get(mode, logging.WARNING), text)


QtCore.qInstallMessageHandler(_filtered_qt_message_handler)

# Import UI components
from ui_components import enhance_ui, apply_stylesheet, LoadingStyles, TabGlowManager, InlineSpinner
from splash_screen import SplashScreen
from icons import IconManager, TAB_COLORS, DEFAULT_ICON_COLOR

# Import state manager
from core.state_manager import app_state

# Import tab registry (tab classes are imported lazily during _load_tabs)
from ui.tabs import TAB_REGISTRY

# Tabs that appear as fixed utility buttons instead of reorderable tabs
UTILITY_TAB_KEYS = {'settings', 'logs'}


# ============================================================================
# DEBUG CLI ARGUMENTS
# ============================================================================
# Parse --tab, --auto-close from sys.argv before other processing.
# These are stripped so positional args for app_state aren't affected.

_DEBUG_ARGS = {}
_TAB_ALIASES = {
    'gallery': 'gallery',
    'comfyui': 'comfyui',
    'settings': 'settings',
    'logs': 'logs',
    'pass': 'passbuilder',
    'passbuilder': 'passbuilder',
    'mp4': 'mp4maker',
    'mp4maker': 'mp4maker',
    'republish': 'republish',
    'shotcleaner': 'cleaner',
    'cleaner': 'cleaner',
}


def _parse_debug_args():
    """Extract debug arguments from sys.argv (--tab, --auto-close).

    Removes consumed args from sys.argv so positional parsing is unaffected.
    """
    cleaned = [sys.argv[0]]
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--tab' and i + 1 < len(sys.argv):
            tab_name = sys.argv[i + 1].lower()
            _DEBUG_ARGS['tab'] = _TAB_ALIASES.get(tab_name, tab_name)
            logging.info(f"[Debug] --tab {sys.argv[i + 1]} -> {_DEBUG_ARGS['tab']}")
            i += 2
            continue
        elif arg == '--auto-close' and i + 1 < len(sys.argv):
            try:
                _DEBUG_ARGS['auto_close'] = int(sys.argv[i + 1])
                logging.info(f"[Debug] --auto-close {_DEBUG_ARGS['auto_close']}s")
            except ValueError:
                logging.warning(f"[Debug] Invalid --auto-close value: {sys.argv[i + 1]}")
            i += 2
            continue
        cleaned.append(arg)
        i += 1
    sys.argv = cleaned


_parse_debug_args()

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
    logging.info("OpenGL surface format configured")
except Exception as e:
    logging.warning(f"Could not configure OpenGL surface format: {e}")

# Apply stylesheet
apply_stylesheet(app)

logging.info(f"DEADLINE {DEADLINE_PATH}")
logging.info(f"OIIO {OIIO_PATH}")
logging.info(f"OIIO INFO {OIIO_INFO_PATH}")
logging.info(f"FFMPEG {FFMPEG_PATH}")


# Global reference to main window for cross-widget access
_main_window = None


def get_main_window():
    """Get the main application window instance.

    Returns:
        LumaShotTools instance or None if not yet created.
    """
    return _main_window


class LogStream(QtCore.QObject):
    """Custom stream that redirects output to the log widget."""
    message_written = QtCore.Signal(str)

    def write(self, message):
        if message.strip():
            self.message_written.emit(message)

    def flush(self):
        pass


class ExpandingTabBar(QTabBar):
    """Custom tab bar that expands tabs to fill the available width.

    Supports hover-to-switch during drag operations: when dragging files
    over a tab header for 500ms, that tab becomes active.
    """

    # Padding on each side of the tab bar
    HORIZONTAL_PADDING = 10
    # Delay before switching tabs during drag hover (milliseconds)
    DRAG_HOVER_DELAY = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        # Don't use Qt's expanding - we'll handle it ourselves
        self.setExpanding(False)
        # Disable scroll buttons so all tabs are always visible
        self.setUsesScrollButtons(False)
        # Enable document mode for cleaner look
        self.setDocumentMode(True)

        # Enable drag-and-drop for hover-to-switch functionality
        self.setAcceptDrops(True)

        # Track drag hover state
        self._drag_hover_tab = -1
        self._drag_hover_timer = QtCore.QTimer(self)
        self._drag_hover_timer.setSingleShot(True)
        self._drag_hover_timer.timeout.connect(self._on_drag_hover_timeout)

    def dragEnterEvent(self, event):
        """Accept drag to enable hover-to-switch."""
        try:
            # Accept any drag that contains files (URLs or text with paths)
            if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-luma-files"):
                event.acceptProposedAction()
                self._update_drag_hover(event.position().toPoint())
            else:
                event.ignore()
        except Exception as e:
            logging.debug(f"ExpandingTabBar.dragEnterEvent error: {e}")
            event.ignore()

    def dragMoveEvent(self, event):
        """Track which tab is being hovered during drag."""
        try:
            if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-luma-files"):
                event.acceptProposedAction()
                self._update_drag_hover(event.position().toPoint())
            else:
                event.ignore()
        except Exception as e:
            logging.debug(f"ExpandingTabBar.dragMoveEvent error: {e}")
            event.ignore()

    def dragLeaveEvent(self, event):
        """Cancel hover timer when drag leaves."""
        self._cancel_drag_hover()
        event.accept()

    def dropEvent(self, event):
        """Don't handle the drop - let the actual target widget handle it."""
        # Cancel hover timer
        self._cancel_drag_hover()
        # Ignore the drop so it propagates to the actual drop target
        event.ignore()

    def _update_drag_hover(self, pos):
        """Update drag hover state based on cursor position."""
        try:
            tab_index = self.tabAt(pos)

            if tab_index != self._drag_hover_tab:
                # Hovering over a different tab, reset timer
                self._drag_hover_tab = tab_index
                self._drag_hover_timer.stop()

                if tab_index >= 0 and tab_index != self.currentIndex():
                    # Start timer to switch to this tab
                    self._drag_hover_timer.start(self.DRAG_HOVER_DELAY)
        except Exception as e:
            logging.debug(f"ExpandingTabBar._update_drag_hover error: {e}")

    def _cancel_drag_hover(self):
        """Cancel any pending tab switch."""
        try:
            self._drag_hover_timer.stop()
            self._drag_hover_tab = -1
        except Exception:
            pass

    def _on_drag_hover_timeout(self):
        """Handle hover timeout during drag - switch to the hovered tab."""
        try:
            logging.debug(f"[ExpandingTabBar] _on_drag_hover_timeout START hover_tab={self._drag_hover_tab} current={self.currentIndex()}")
            if self._drag_hover_tab >= 0 and self._drag_hover_tab != self.currentIndex():
                logging.debug(f"[ExpandingTabBar] _on_drag_hover_timeout switching to tab {self._drag_hover_tab}")
                self.setCurrentIndex(self._drag_hover_tab)
                logging.debug(f"[ExpandingTabBar] _on_drag_hover_timeout tab switch COMPLETE")
        except Exception as e:
            logging.error(f"ExpandingTabBar._on_drag_hover_timeout error: {e}", exc_info=True)

    def tabSizeHint(self, index):
        """Calculate tab size to fill the tab bar width evenly.

        Hidden tabs get zero width.  Visible tabs share the remaining space
        after subtracting the corner widget.
        """
        default_size = super().tabSizeHint(index)
        tab_widget = self.parentWidget()

        # Hidden tabs get zero width (but keep height to avoid layout issues)
        if tab_widget and hasattr(tab_widget, 'isTabVisible') and not tab_widget.isTabVisible(index):
            return QtCore.QSize(0, default_size.height())

        # Count only visible tabs
        visible_count = 0
        for i in range(self.count()):
            if not tab_widget or not hasattr(tab_widget, 'isTabVisible') or tab_widget.isTabVisible(i):
                visible_count += 1
        if visible_count <= 0:
            return default_size

        # Use the parent (QTabWidget) width, subtract corner widget
        if tab_widget:
            corner = tab_widget.cornerWidget(Qt.TopRightCorner)
            corner_width = 0
            if corner and corner.isVisible():
                corner_width = corner.width() or corner.sizeHint().width()
            available_width = tab_widget.width() - corner_width
        else:
            available_width = self.width()

        if available_width < 200:
            return default_size

        tab_width = available_width // visible_count
        tab_width = max(80, tab_width)

        return QtCore.QSize(tab_width, default_size.height())

    def paintEvent(self, event):
        """Paint normally, then paint over hidden tabs to erase ghost indicators."""
        # Let Qt handle all normal rendering (including drag animations)
        super().paintEvent(event)

        # Paint over hidden tab areas with the tab bar background
        tab_widget = self.parentWidget()
        if not tab_widget:
            return
        painter = QPainter(self)
        bg = QColor("#1a1d23")
        for i in range(self.count()):
            if hasattr(tab_widget, 'isTabVisible') and not tab_widget.isTabVisible(i):
                rect = self.tabRect(i)
                if not rect.isEmpty():
                    painter.fillRect(rect, bg)
        painter.end()

    def showEvent(self, event):
        """Force size recalculation when tab bar is shown."""
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self.updateGeometry)


class LumaShotTools(QtWidgets.QWidget):
    """Main application window."""

    def __init__(self, parent=None, progress_callback=None):
        super(LumaShotTools, self).__init__()

        self._progress_callback = progress_callback or (lambda p, m: None)

        self.setAttribute(Qt.WA_TranslucentBackground)

        # Store tab instances
        self.tabs = {}
        self.logs_tab = None

        # Utility buttons (Settings, Logs) in top-right corner
        self._utility_buttons = {}   # restrict_key -> QPushButton
        self._utility_badges = {}    # restrict_key -> ButtonNotificationBadge

        # Check for new version
        self._check_version_update()
        self._deployed_version_available = False  # Flag for new deployed version

        # Load UI using modular tab system
        self._progress_callback(25, "Building tab layout...")
        self._load_tabs()

        # Set window title based on mode
        dev_suffix = " - DEV" if IS_DEV_MODE else ""
        if app_state.standalone_mode:
            self.setWindowTitle(f"{APP_TITLE} - Standalone Mode - v{APP_VERSION}{dev_suffix}")
        else:
            self.setWindowTitle(f"{APP_TITLE} - {app_state.jobname} - {app_state.shot} - v{APP_VERSION}{dev_suffix}")
        self.setWindowIcon(QIcon(ICON_PATH))

        # Setup log redirection (deferred until after window is shown)
        self.log_stream = LogStream()
        self.log_stream.message_written.connect(self._append_log)
        self._log_redirect_pending = True

        # Check admin status
        self._check_admin_status()

        # Set minimum size
        self.setMinimumSize(800, 600)

        # Restore window state from previous session
        self._restore_window_state()

        # Setup animations
        self._progress_callback(82, "Setting up animations...")
        self.animator = enhance_ui(self)
        self.animator.redirect_to_splash = False
        self.animator.splash_screen = None
        logging.info("UI animations enabled")

        # Setup tab glow manager for attention notifications
        self.tab_glow_manager = TabGlowManager(self.tab_widget, self)

        # Setup colorful tab icons
        self._progress_callback(84, "Loading tab icons...")
        self._setup_tab_icons()

        # Restore saved tab order
        self._restore_tab_order()

        # Eagerly initialize the tab that's visible after order is restored
        # (other tabs will be initialized on first activation)
        self._progress_callback(86, "Initializing active tab...")
        self._initialize_active_tab()

        # Hide tabs that require shot context in standalone mode
        self._hide_standalone_incompatible_tabs()

        # Show notification on Settings tab if new version
        if self._is_new_version and 'settings' in self.tabs:
            # Show badge on the utility button (or fall back to glow for regular tabs)
            if 'settings' in self._utility_badges:
                self._utility_badges['settings'].show_badge()
            else:
                self.tabs['settings'].signals.request_attention.emit()

        # Disable scroll wheel on combo boxes and spin boxes
        self._disable_scroll_wheel_on_inputs()

        # Setup system tray for notifications
        self._setup_system_tray()

        # Connect tab change signal
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabBar().tabMoved.connect(self._on_tab_moved)

        # Debounce timer for tab order saving (avoids disk I/O on every
        # intermediate position while dragging a tab)
        self._tab_reorder_timer = QtCore.QTimer(self)
        self._tab_reorder_timer.setSingleShot(True)
        self._tab_reorder_timer.setInterval(500)
        self._tab_reorder_timer.timeout.connect(self._save_tab_order)
        self._is_reordering_tabs = False

        # Setup periodic version check (every 2 minutes)
        self._version_check_timer = QtCore.QTimer(self)
        self._version_check_timer.timeout.connect(self._check_deployed_version)
        self._version_check_timer.start(120000)  # 120000ms = 2 minutes

        # Subscribe to event bus for window title progress updates
        self._setup_event_bus_subscriptions()

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

        # Hide log label by default, show only if user setting is enabled
        from core.settings_manager import get_setting
        self._show_statusbar_log = get_setting("show_statusbar_log")
        self.last_log_label.setVisible(self._show_statusbar_log)

        status_widget = QtWidgets.QWidget()
        status_widget.setLayout(status_layout)
        layout.addWidget(status_widget, 0)  # stretch factor 0

        # Lazily import and instantiate each tab
        # Tab modules are imported on demand, and initialize() is deferred
        # until first activation to speed up startup
        import time as _time
        import importlib as _importlib
        _total_start = _time.perf_counter()

        # Calculate progress range for tab loading (28-80%)
        _tab_progress_start = 28
        _tab_progress_end = 80
        _loadable_tabs = list(TAB_REGISTRY)
        _tab_count = len(_loadable_tabs) or 1

        for _loaded_idx, (module_path, class_name, restrict_key) in enumerate(_loadable_tabs):
            _tab_start = _time.perf_counter()

            # Report per-tab progress to splash screen
            _tab_progress = _tab_progress_start + int(
                (_tab_progress_end - _tab_progress_start) * _loaded_idx / _tab_count
            )
            # Derive a friendly display name from class_name (e.g. "ComfyUITab" -> "ComfyUI")
            _display_name = class_name.replace("Tab", "")
            self._progress_callback(_tab_progress, f"Loading {_display_name}...")

            # Import tab class lazily (module loaded here, not at app import time)
            _module = _importlib.import_module(module_path, 'ui.tabs')
            tab_class = getattr(_module, class_name)

            # Create tab instance and load UI (uses precompiled .py when available)
            tab_instance = tab_class(self, app_state)
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

            # initialize() is deferred until first tab activation
            # (see _ensure_initialized in BaseTab and _on_tab_changed)

            # Store special reference to logs tab
            if restrict_key == 'logs':
                self.logs_tab = tab_instance

            _tab_elapsed = _time.perf_counter() - _tab_start
            logging.info(f"[Startup] {tab_instance.tab_name}: {_tab_elapsed*1000:.0f}ms")

        _total_elapsed = _time.perf_counter() - _total_start
        logging.info(f"[Startup] Tab loading total: {_total_elapsed*1000:.0f}ms ({len(self.tabs)} tabs, init deferred)")

        # Setup utility buttons (Settings, Logs) in the corner of the tab bar
        self._setup_utility_buttons()

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

    def _setup_utility_buttons(self):
        """Create fixed utility buttons (Settings, Logs) in the tab bar corner.

        Hides these tabs from the movable tab bar and shows them as fixed
        QPushButtons via setCornerWidget so they can't be reordered.
        """
        from PySide6.QtWidgets import QPushButton, QVBoxLayout
        from effects import ButtonNotificationBadge

        # Ordered list of utility tabs to show as buttons
        utility_tab_defs = [
            ('settings', 'settings', 'Settings'),
            ('logs', 'terminal', 'Logs'),
        ]

        container = QtWidgets.QWidget()
        container.setObjectName("UtilityButtonContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(0)

        for restrict_key, icon_name, label in utility_tab_defs:
            if restrict_key not in self.tabs:
                continue

            tab_instance = self.tabs[restrict_key]
            tab_index = self.tab_widget.indexOf(tab_instance.ui)
            if tab_index == -1:
                continue

            # Hide the tab bar entry but keep the page in the stack
            self.tab_widget.setTabVisible(tab_index, False)

            # Create icon-only button
            btn = QPushButton()
            btn.setObjectName(f"UtilityButton_{restrict_key}")
            icon = IconManager.get_icon(icon_name, DEFAULT_ICON_COLOR, 16)
            btn.setIcon(icon)
            btn.setToolTip(label)
            btn.setCheckable(True)
            btn.setProperty("utility", True)
            btn.clicked.connect(lambda checked, rk=restrict_key: self._on_utility_button_clicked(rk))

            layout.addWidget(btn)
            self._utility_buttons[restrict_key] = btn

            # Create notification badge on the button
            badge = ButtonNotificationBadge(btn)
            self._utility_badges[restrict_key] = badge

        if self._utility_buttons:
            # Size container height to actual button count (each button is 33px)
            button_count = len(self._utility_buttons)
            container_height = button_count * 33
            container.setFixedHeight(container_height)
            self.tab_widget.setCornerWidget(container, Qt.TopRightCorner)

    def _on_utility_button_clicked(self, restrict_key):
        """Handle click on a utility button — switch to the hidden tab."""
        if restrict_key not in self.tabs:
            return
        tab_instance = self.tabs[restrict_key]
        tab_index = self.tab_widget.indexOf(tab_instance.ui)
        if tab_index >= 0:
            self.tab_widget.setCurrentIndex(tab_index)

    def _update_utility_button_states(self, active_index):
        """Update checked state of utility buttons to reflect current tab."""
        for restrict_key, btn in self._utility_buttons.items():
            if restrict_key not in self.tabs:
                continue
            tab_index = self.tab_widget.indexOf(self.tabs[restrict_key].ui)
            is_active = (tab_index == active_index)
            btn.setChecked(is_active)
            # Hide badge when user navigates to that tab
            if is_active and restrict_key in self._utility_badges:
                self._utility_badges[restrict_key].hide_badge()

    @QtCore.Slot(str)
    def _append_log(self, message):
        """Append a message to the log output widget."""
        if self.logs_tab:
            self.logs_tab.append_log(message)

        # Update last log label in status bar (truncate if too long)
        # Only update if setting is enabled
        if hasattr(self, 'last_log_label') and getattr(self, '_show_statusbar_log', False):
            clean_msg = message.strip()
            if len(clean_msg) > 80:
                clean_msg = clean_msg[:77] + "..."
            self.last_log_label.setText(clean_msg)

    def update_statusbar_log_visibility(self, visible: bool):
        """Update the status bar log label visibility based on user setting."""
        self._show_statusbar_log = visible
        if hasattr(self, 'last_log_label'):
            self.last_log_label.setVisible(visible)
            if not visible:
                self.last_log_label.setText("")

    def start_status_spinner(self):
        """Start the status bar spinner to indicate a background operation."""
        if hasattr(self, 'status_spinner'):
            self.status_spinner.start()

    def stop_status_spinner(self):
        """Stop the status bar spinner."""
        if hasattr(self, 'status_spinner'):
            self.status_spinner.stop()

    def _on_tab_request_attention(self, tab_instance):
        """Handle tab requesting attention with pulsing glow or badge."""
        logging.info(f"[TabAttention] _on_tab_request_attention called for tab '{tab_instance.tab_name}'")

        # Determine the restrict_key for this tab
        restrict_key = None
        for key, inst in self.tabs.items():
            if inst is tab_instance:
                restrict_key = key
                break

        # For utility tabs, show a badge on the button instead of tab glow
        if restrict_key and restrict_key in self._utility_badges:
            badge = self._utility_badges[restrict_key]
            # Don't show badge if user is already viewing this tab
            tab_index = self.tab_widget.indexOf(tab_instance.ui)
            if tab_index != self.tab_widget.currentIndex():
                badge.show_badge()
                logging.info(f"[TabAttention] Showing badge on utility button '{restrict_key}'")
            return

        if not hasattr(self, 'tab_glow_manager'):
            logging.debug(f"[TabAttention] tab_glow_manager not yet initialized, skipping")
            return

        # Find the tab index for this tab instance
        tab_index = self.tab_widget.indexOf(tab_instance.ui)
        logging.info(f"[TabAttention] Tab index: {tab_index}, current index: {self.tab_widget.currentIndex()}")
        if tab_index == -1:
            logging.error(f"[TabAttention] Tab not found in tab_widget!")
            return

        # Use tab-specific color for glow
        tab_id = tab_instance.tab_id
        color = TAB_COLORS.get(tab_id, DEFAULT_ICON_COLOR)
        logging.info(f"[TabAttention] Starting glow for tab_id={tab_id}, color={color}")

        # Start the glow effect
        self.tab_glow_manager.start_glow(tab_index, color)
        logging.info(f"Tab '{tab_instance.tab_name}' is requesting attention")

    def _initialize_active_tab(self):
        """Eagerly initialize the currently visible tab after tab order is restored."""
        current_index = self.tab_widget.currentIndex()
        for restrict_key, tab_instance in self.tabs.items():
            if self.tab_widget.indexOf(tab_instance.ui) == current_index:
                tab_instance._ensure_initialized()
                break

    def _on_tab_changed(self, index):
        """Handle tab change - notify tabs and sync utility button states."""
        # Skip activation/deactivation while user is dragging tabs around
        if self._is_reordering_tabs:
            return
        logging.debug(f"[MainWindow] _on_tab_changed START index={index}")
        try:
            # Get previous and current tab
            for tab_name, tab_instance in self.tabs.items():
                tab_index = self.tab_widget.indexOf(tab_instance.ui)
                if tab_index == index:
                    logging.debug(f"[MainWindow] activating tab: {tab_name}")
                    tab_instance._ensure_initialized()
                    tab_instance.on_tab_activated()
                    logging.debug(f"[MainWindow] tab activated: {tab_name}")
                else:
                    # Only deactivate tabs that have been initialized
                    if tab_instance._initialized:
                        logging.debug(f"[MainWindow] deactivating tab: {tab_name}")
                        tab_instance.on_tab_deactivated()
                        logging.debug(f"[MainWindow] tab deactivated: {tab_name}")

            # Sync utility button checked states
            self._update_utility_button_states(index)

            logging.debug(f"[MainWindow] _on_tab_changed COMPLETE")
        except Exception as e:
            logging.error(f"[MainWindow] _on_tab_changed error: {e}", exc_info=True)

    def _on_tab_moved(self, _from_index, _to_index):
        """Debounce tab order save when user drags tabs."""
        self._is_reordering_tabs = True
        self._tab_reorder_timer.start()  # restart the 500ms timer

    def _save_tab_order(self):
        """Actually save tab order after drag settles."""
        self._is_reordering_tabs = False
        from core.user_preferences import save_tab_order

        tab_names = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            name = widget.objectName()
            # Don't persist utility tab positions — they're fixed buttons
            if name not in UTILITY_TAB_KEYS:
                tab_names.append(name)

        save_tab_order(tab_names)

        # Replay the tab activation that was suppressed during reorder
        self._on_tab_changed(self.tab_widget.currentIndex())

    def select_tab_by_name(self, restrict_key):
        """Select a tab by its restrict_key name (e.g. 'gallery').

        Args:
            restrict_key: Tab identifier from TAB_REGISTRY (e.g. 'gallery',
                         'comfyui', 'settings', 'logs', 'passbuilder', etc.)

        Returns:
            True if tab was found and selected, False otherwise.
        """
        if restrict_key in self.tabs:
            tab_instance = self.tabs[restrict_key]
            tab_index = self.tab_widget.indexOf(tab_instance.ui)
            if tab_index >= 0:
                self.tab_widget.setCurrentIndex(tab_index)
                logging.info(f"[Debug] Selected tab: {restrict_key} (index {tab_index})")
                return True
        logging.warning(f"[Debug] Tab not found: {restrict_key}")
        return False

    def _restore_tab_order(self):
        """Restore saved tab order on startup.

        Only reorders regular (non-utility) tabs.  Utility tabs are hidden
        from the tab bar and shown as fixed corner-widget buttons.
        """
        from core.user_preferences import get_tab_order

        saved_order = get_tab_order()
        if not saved_order:
            self.tab_widget.setCurrentIndex(0)
            return

        # Filter out utility tab keys — they are not in the movable bar
        saved_order = [n for n in saved_order if n not in UTILITY_TAB_KEYS]

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
        # Refresh and check role status (property auto-computes from settings)
        app_state.refresh_admin_status()

        if app_state.is_admin:
            logging.info(f"User '{app_state.user}' is an admin (full access)")
        else:
            logging.info(f"User '{app_state.user}' is a regular user")

    def _check_version_update(self):
        """Check if this is a new version and store flag for notification."""
        from core.user_preferences import is_new_version, set_last_opened_version

        # Check if current version is newer than last opened
        self._is_new_version = is_new_version(APP_VERSION)

        if self._is_new_version:
            logging.info(f"New version detected: v{APP_VERSION}")
            # Clear thumbnail cache to regenerate with new version
            self._clear_thumbnail_cache_for_new_version()
        else:
            logging.info(f"Current version: v{APP_VERSION}")

        # Update the last opened version to current (will be saved on close)
        # We don't save immediately to avoid file I/O on every startup

    def _clear_thumbnail_cache_for_new_version(self):
        """Clear 3D model thumbnail cache when a new version is detected.

        This ensures thumbnails are regenerated with any rendering improvements
        in the new version. The prewarm system will automatically regenerate
        thumbnails during startup.
        """
        try:
            from geo.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            service.clear_cache()  # Clear all model thumbnails
            logging.info("Cleared thumbnail cache for new version")
        except Exception as e:
            # Non-critical - don't block startup
            logging.warning(f"Could not clear thumbnail cache: {e}")

    def _check_deployed_version(self):
        """Periodically check if a new version has been deployed.

        The version file lives on the network install root, so the read runs
        in a worker — an SMB stall inside this QTimer slot froze the whole UI.
        """
        # Don't check if we already know there's a new version
        if self._deployed_version_available:
            return
        if getattr(self, '_version_check_in_flight', False):
            return

        from core.config import _load_version
        from ui_components import Worker

        self._version_check_in_flight = True
        worker = Worker(_load_version)
        worker.signals.result.connect(self._on_deployed_version_result)
        worker.signals.error.connect(self._on_deployed_version_error)
        self._version_check_worker = worker  # keep reference to prevent GC
        QtCore.QThreadPool.globalInstance().start(worker)

    def _on_deployed_version_result(self, deployed_version):
        """Handle deployed-version read (GUI thread via worker signal)."""
        self._version_check_in_flight = False
        if deployed_version != APP_VERSION and deployed_version != "unknown":
            logging.info(f"New deployed version detected: v{deployed_version} (current: v{APP_VERSION})")
            self._deployed_version_available = True
            self._show_new_version_notification(deployed_version)

    def _on_deployed_version_error(self, error_msg, traceback_str=""):
        """Handle deployed-version read failure (non-critical)."""
        self._version_check_in_flight = False
        logging.error(f"Version check failed: {error_msg}")

    def _show_new_version_notification(self, new_version: str):
        """Show notification that a new version is available via the Settings tab."""
        # Get the settings tab and show the notification there
        settings_tab = self.get_tab("settings")
        if settings_tab and hasattr(settings_tab, 'show_new_version_available'):
            settings_tab.show_new_version_available(new_version)

        # Show badge on the Settings utility button
        if 'settings' in self._utility_badges:
            self._utility_badges['settings'].show_badge()

        # Stop the periodic check — we found a new version, no need to keep polling
        timer = getattr(self, '_version_check_timer', None)
        if timer is not None:
            timer.stop()


    def _restore_window_state(self):
        """Restore window size and maximized state from previous session."""
        from core.settings_manager import load_user_settings

        # Check if we have saved window state
        settings = load_user_settings()
        has_saved_state = "window_width" in settings or "window_height" in settings or "window_maximized" in settings

        if has_saved_state:
            # Restore from saved state
            from core.user_preferences import get_window_state
            state = get_window_state()
            width = state.get("width", 1250)
            height = state.get("height", 1000)
            maximized = state.get("maximized", False)

            # Set the size (this will be the size when not maximized)
            self.resize(width, height)

            # Apply maximized state if it was saved
            if maximized:
                self.showMaximized()
        else:
            # First launch - use previous default (1250x1000, not maximized)
            self.resize(1250, 1000)

    def _save_window_state(self):
        """Save current window size and maximized state."""
        from core.user_preferences import save_window_state

        # Get the current state
        maximized = self.isMaximized()

        # If maximized, save the normal geometry (the size before maximization)
        # If not maximized, save the current size
        if maximized:
            # Use the normal geometry to get the size before maximization
            geom = self.normalGeometry()
            width = geom.width()
            height = geom.height()
        else:
            width = self.width()
            height = self.height()

        save_window_state(width, height, maximized)


    def _hide_standalone_incompatible_tabs(self):
        """Hide tabs that require shot context in standalone mode."""
        if not app_state.standalone_mode:
            return

        # Republish tab is allowed in standalone mode (uses custom directory selection)
        standalone_incompatible = ['passbuilder']

        for i in range(self.tab_widget.count() - 1, -1, -1):
            widget = self.tab_widget.widget(i)
            if widget.objectName() in standalone_incompatible:
                self.tab_widget.removeTab(i)
                logging.info(f"Hidden standalone-incompatible tab: {widget.objectName()}")

    def _setup_tab_icons(self):
        """Setup monochromatic icons for each tab.

        Skips utility tabs — their icons are set on the corner-widget buttons.
        """
        tab_icons = {
            'passbuilder': 'layers',
            'mp4maker': 'video',
            'republish': 'upload',
            'cleaner': 'trash',
            'comfyui': 'sparkles',
            'gallery': 'image',
        }

        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            tab_id = widget.objectName()
            if tab_id in tab_icons:
                icon_name = tab_icons[tab_id]
                icon = IconManager.get_icon(icon_name, DEFAULT_ICON_COLOR, 16)
                self.tab_widget.setTabIcon(i, icon)

    def _disable_scroll_wheel_on_inputs(self):
        """Disable scroll wheel on combo boxes and spin boxes to prevent accidental changes.

        Installs an application-wide event filter so dynamically created widgets
        (e.g. those in deferred tab initialize()) are also covered.
        """
        from PySide6.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox

        class _ScrollWheelFilter(QtCore.QObject):
            """Block wheel events on combo/spin boxes app-wide."""
            _FILTERED_TYPES = (QComboBox, QSpinBox, QDoubleSpinBox)

            def eventFilter(self, obj, event):
                if (event.type() == QtCore.QEvent.Wheel
                        and isinstance(obj, self._FILTERED_TYPES)):
                    event.ignore()
                    return True
                return False

        self._scroll_filter = _ScrollWheelFilter(self)
        QApplication.instance().installEventFilter(self._scroll_filter)

    def _setup_system_tray(self):
        """Setup system tray icon for OS-level notifications."""
        from PySide6.QtWidgets import QSystemTrayIcon, QMenu

        # Check if system tray is available
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logging.info("[Tray] System tray not available on this system")
            self._tray_icon = None
            return

        # Use None as parent to avoid "must be a top level window" warnings on Windows
        # Qt will handle the parent relationship automatically
        self._tray_icon = QSystemTrayIcon(None)

        # Use window icon for tray
        self._tray_icon.setIcon(self.windowIcon())
        self._tray_icon.setToolTip(APP_TITLE)

        # Create context menu
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show Window")
        show_action.triggered.connect(self._show_and_activate)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self.close)
        self._tray_icon.setContextMenu(tray_menu)

        # Handle tray icon activation (double-click)
        self._tray_icon.activated.connect(self._on_tray_activated)

        # Show tray icon
        self._tray_icon.show()
        logging.info("[Tray] System tray icon initialized")

    def _on_tray_activated(self, reason):
        """Handle tray icon activation."""
        from PySide6.QtWidgets import QSystemTrayIcon

        if reason == QSystemTrayIcon.DoubleClick:
            self._show_and_activate()

    def _show_and_activate(self):
        """Show and bring window to front."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def show_system_notification(self, title, message, icon_type="info"):
        """Show a system notification via the tray icon.

        Args:
            title: Notification title
            message: Notification message
            icon_type: 'info', 'warning', 'critical', or 'success'
        """
        from PySide6.QtWidgets import QSystemTrayIcon

        if not hasattr(self, '_tray_icon') or not self._tray_icon:
            return

        icon_map = {
            'info': QSystemTrayIcon.Information,
            'warning': QSystemTrayIcon.Warning,
            'critical': QSystemTrayIcon.Critical,
            'success': QSystemTrayIcon.Information,
        }
        icon = icon_map.get(icon_type, QSystemTrayIcon.Information)

        # Show message for 5 seconds
        self._tray_icon.showMessage(title, message, icon, 5000)

    def _setup_event_bus_subscriptions(self):
        """Subscribe to event bus signals for window title updates."""
        try:
            from core.event_bus import pipeline_events

            # Update window title when jobs progress
            pipeline_events.job_progress.connect(self._on_job_progress_for_title)
            pipeline_events.job_completed.connect(self._on_job_completed_for_title)
            pipeline_events.all_jobs_completed.connect(self._on_all_jobs_completed_for_title)

            logging.debug("Main window subscribed to event bus for title updates")
        except ImportError:
            logging.warning("Event bus not available - window title progress disabled")

    def _on_job_progress_for_title(self, job_id, progress, message):
        """Update window title with current progress."""
        try:
            from core.event_bus import pipeline_events
            progress_info = pipeline_events.get_aggregate_progress()
            self.update_window_title_progress(progress_info)
        except Exception as e:
            logging.debug(f"Error updating window title: {e}")

    def _on_job_completed_for_title(self, job_id, output_paths):
        """Update window title after job completion."""
        try:
            from core.event_bus import pipeline_events
            progress_info = pipeline_events.get_aggregate_progress()
            self.update_window_title_progress(progress_info)
        except Exception as e:
            logging.debug(f"Error updating window title: {e}")

    def _on_all_jobs_completed_for_title(self, total_outputs, elapsed_seconds):
        """Reset window title when all jobs complete."""
        # Delay reset slightly to show completion state
        QtCore.QTimer.singleShot(3000, lambda: self.update_window_title_progress(None))

    def update_window_title_progress(self, progress_info=None):
        """Update window title to show job progress.

        Args:
            progress_info: Dict with keys 'total_jobs', 'avg_progress', etc.
                           If None, resets to normal title.
        """
        if progress_info is None or progress_info.get('total_jobs', 0) == 0:
            # Reset to normal title
            dev_suffix = " - DEV" if IS_DEV_MODE else ""
            if app_state.standalone_mode:
                self.setWindowTitle(f"{APP_TITLE} - Standalone Mode - v{APP_VERSION}{dev_suffix}")
            else:
                self.setWindowTitle(f"{APP_TITLE} - {app_state.jobname} - {app_state.shot} - v{APP_VERSION}{dev_suffix}")
            return

        # Build progress string
        total = progress_info.get('total_jobs', 0)
        completed = progress_info.get('completed_jobs', 0)
        avg_progress = progress_info.get('avg_progress', 0)
        active = total - completed - progress_info.get('failed_jobs', 0)

        if active > 0:
            if completed > 0:
                progress_str = f"{completed}/{total} jobs"
            else:
                progress_str = f"{active} jobs"
            if avg_progress > 0:
                progress_str += f" • {avg_progress}%"
        else:
            progress_str = f"{completed} jobs done"

        # Update title with progress
        dev_suffix = " - DEV" if IS_DEV_MODE else ""
        if app_state.standalone_mode:
            self.setWindowTitle(f"{APP_TITLE} ({progress_str}) - v{APP_VERSION}{dev_suffix}")
        else:
            self.setWindowTitle(f"{APP_TITLE} - {app_state.jobname} ({progress_str}) - v{APP_VERSION}{dev_suffix}")

    def showEvent(self, event):
        """Override show event to force cursor update when window is first shown."""
        super().showEvent(event)

        # Force cursor update by overriding and restoring
        app = QApplication.instance()
        app.setOverrideCursor(Qt.ArrowCursor)
        QtCore.QTimer.singleShot(100, lambda: app.restoreOverrideCursor())

        # Force widget under cursor to update cursor shape
        def update_cursor():
            from PySide6.QtGui import QCursor
            pos = QCursor.pos()
            widget = app.widgetAt(pos)
            if widget:
                widget.unsetCursor()
                widget.update()

        QtCore.QTimer.singleShot(150, update_cursor)

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
            # Save the *real* originals (sys.__stdout__/__stderr__), not the
            # current sys.stdout. Earlier setup_file_logging may have already
            # wrapped sys.stdout in a TeeStream whose file handle is closed by
            # atexit; restoring to that wrapper after close would leave
            # sys.stdout pointing at a closed fd.
            self._orig_stdout = sys.__stdout__
            self._orig_stderr = sys.__stderr__

            # Redirect stdout/stderr for any remaining print() calls
            sys.stdout = self.log_stream
            sys.stderr = self.log_stream

            # Bridge logging module → UI logs tab
            # Without this, logger.info() etc. only write to the file handler
            # and never reach the logs tab (LogStream only captures stdout/stderr)
            self._ui_log_handler = logging.StreamHandler(self.log_stream)
            self._ui_log_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
            self._ui_log_handler.setLevel(logging.DEBUG)
            logging.getLogger().addHandler(self._ui_log_handler)

            self._log_redirect_pending = False
            logging.info("Log redirection enabled")

    def _get_running_tasks(self):
        """Check all tabs for running tasks and return a list of descriptions."""
        running = []
        for key, tab in self.tabs.items():
            # Check BaseTab active workers
            if hasattr(tab, 'has_active_workers') and tab.has_active_workers():
                tab_name = getattr(tab, 'tab_name', key)
                running.append(f"{tab_name}: background task running")

            # Check ComfyUI polling timers (farm jobs being monitored)
            if key == 'comfyui':
                iterate_timer = getattr(tab, '_iterate_poll_timer', None)
                batch_timer = getattr(tab, '_batch_poll_timer', None)
                if (iterate_timer and iterate_timer.isActive()) or \
                   (batch_timer and batch_timer.isActive()):
                    if f"{getattr(tab, 'tab_name', key)}: background task running" not in running:
                        running.append("ComfyUI: farm job in progress")
        return running

    def closeEvent(self, event):
        """Handle window close event - save window state and version."""
        from core.user_preferences import set_last_opened_version

        # Check for running tasks before closing
        running = self._get_running_tasks()
        if running:
            from dialog_helpers import confirm_action
            if not confirm_action(
                "Tasks Still Running",
                "There are tasks still running. Are you sure you want to exit?",
                parent=self,
                detail="\n".join(f"  - {task}" for task in running),
            ):
                event.ignore()
                return

        self._save_window_state()

        # Save current version as last opened
        set_last_opened_version(APP_VERSION)

        # Clean up system tray icon
        if hasattr(self, '_tray_icon') and self._tray_icon:
            self._tray_icon.hide()
            self._tray_icon = None

        # Restore stdout/stderr and remove UI log handler
        if hasattr(self, '_orig_stdout'):
            sys.stdout = self._orig_stdout
            sys.stderr = self._orig_stderr
        if hasattr(self, '_ui_log_handler'):
            logging.getLogger().removeHandler(self._ui_log_handler)

        super().closeEvent(event)


def main():
    """Main entry point."""
    import traceback
    import time
    # Qt message handler is installed at module import (see top of file).
    try:
        # Show splash screen
        splash = SplashScreen()
        splash.show()
        splash.start_animation()
        app.processEvents()

        # Pre-load settings to populate cache before tabs initialize
        splash.update_progress(5, "Loading", "Loading user settings...")
        app.processEvents()
        try:
            from core.settings_manager import load_user_settings, load_global_settings, _migrate_global_to_user
            load_user_settings()  # Populate user settings cache
            splash.update_progress(8, "Loading", "Loading global settings...")
            app.processEvents()
            load_global_settings()  # Populate global settings cache (may hit network)
            _migrate_global_to_user()  # Copy formerly-global settings to user scope
        except Exception as e:
            logging.warning(f"Could not pre-load settings: {e}")

        # Cache working tool paths for standalone mode fallback
        splash.update_progress(12, "Loading", "Detecting tool paths...")
        app.processEvents()
        try:
            from core.config import cache_tool_paths
            cache_tool_paths()
        except Exception as e:
            logging.debug(f"Could not cache tool paths: {e}")

        # Check for running jobs to recover (splash feedback only — the
        # actual recovery is done independently by the ComfyUI tab's polling
        # via find_user_running_jobs)
        splash.update_progress(15, "Loading", "Checking for jobs to recover...")
        app.processEvents()
        try:
            from core.user_preferences import get_comfyui_running_jobs
            job_state = get_comfyui_running_jobs()
            if job_state:
                mode = job_state.get("mode", "unknown")
                if mode == "iterate":
                    job_id = job_state.get("job_id", "")
                    splash.update_progress(17, "Loading", f"Found job to recover: {job_id[:8]}...")
                elif mode == "batch":
                    count = len(job_state.get("job_ids", []))
                    splash.update_progress(17, "Loading", f"Found {count} job(s) to recover...")
                app.processEvents()
                logging.info(f"[Startup] Found {mode} mode jobs to recover")
        except Exception as e:
            logging.warning(f"Could not check for job recovery: {e}")

        # Gallery loading is deferred until user opens the Gallery tab
        # (scans network directory on-demand with a loading overlay)

        # Create main window (job recovery is deferred until after splash closes)
        splash.update_progress(20, "Loading", "Creating application window...")
        app.processEvents()

        def _splash_progress(percent, message):
            """Callback for LumaShotTools to report init progress to splash."""
            splash.update_progress(percent, "Loading", message)
            app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)

        global _main_window
        t_start = time.perf_counter()
        window = LumaShotTools(progress_callback=_splash_progress)
        t_elapsed = time.perf_counter() - t_start
        logging.info(f"[Startup] Window creation total: {t_elapsed*1000:.0f}ms")
        _main_window = window  # Store reference for cross-widget access

        splash.update_progress(92, "Loading", "Finalizing...")
        app.processEvents()

        # Show main window first, then close splash
        window.show()
        app.processEvents()  # Ensure window is painted
        splash.stop_animation()
        splash.close()
        
        # Fix cursor being stuck in I-beam mode when mouse is over text field on startup
        # Method 1: Force cursor update by briefly overriding and restoring
        app.setOverrideCursor(Qt.ArrowCursor)
        QtCore.QTimer.singleShot(50, lambda: app.restoreOverrideCursor())
        
        # Method 2: Also force a mouse move event to update cursor
        def force_cursor_update():
            from PySide6.QtGui import QMouseEvent
            from PySide6.QtCore import QPoint
            from PySide6.QtGui import QCursor
            # Create and post a synthetic mouse move event to force cursor update
            pos = QCursor.pos()
            local_pos = window.mapFromGlobal(pos)
            event = QMouseEvent(QtCore.QEvent.Type.MouseMove, local_pos, pos, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
            QtCore.QCoreApplication.postEvent(window, event)
        
        QtCore.QTimer.singleShot(100, force_cursor_update)

        # Enable log redirection after window is shown
        window.enable_log_redirect()

        # 3D viewer (QWebEngineView/Chromium) is initialized lazily on first
        # use rather than pre-warmed at startup. Chromium's GPU initialization
        # causes intermittent access violations (0xC0000005) on some GPU
        # drivers. Lazy init means startup never crashes; the viewer is only
        # created when the user actually opens a 3D model in the gallery.

        # Apply debug CLI arguments
        if _DEBUG_ARGS.get('tab'):
            # Delay tab selection slightly to ensure all tabs are fully initialized
            def _select_debug_tab():
                window.select_tab_by_name(_DEBUG_ARGS['tab'])
            QtCore.QTimer.singleShot(200, _select_debug_tab)

        if _DEBUG_ARGS.get('auto_close'):
            seconds = _DEBUG_ARGS['auto_close']
            logging.info(f"[Debug] Auto-close scheduled in {seconds}s")
            QtCore.QTimer.singleShot(seconds * 1000, lambda: (
                logging.info("[Debug] Auto-close triggered, shutting down"),
                app.quit()
            ))

        # Clean up QWebEngineView instances before exit to prevent Chromium
        # subprocess crash (access violation 0xC0000005) during Qt destructor chain
        def _cleanup_web_engines():
            try:
                from geo.threejs_viewer import ThreeJSViewerWidget
                for widget in app.allWidgets():
                    if isinstance(widget, ThreeJSViewerWidget):
                        widget.cleanup()
                app.processEvents()
            except Exception as e:
                logging.debug(f"WebEngine cleanup: {e}")

            # Clean up TeeWriters here since os._exit() skips atexit handlers
            try:
                from core.logging_utils import cleanup_tee_writers
                cleanup_tee_writers()
            except Exception as e:
                logging.debug(f"TeeWriter cleanup: {e}")

        app.aboutToQuit.connect(_cleanup_web_engines)

        # Run the application
        logging.info("Application window shown, entering event loop")
        exit_code = app.exec()
        logging.info(f"Application exiting with code {exit_code}")

        # Try a normal Python exit. Historically this caused a 0xC0000005
        # crash deep in the Chromium/QWebEngine destructor chain, which is
        # why os._exit() was used. The aboutToQuit handler above now does an
        # orderly QWebEngineView cleanup, so a clean exit should work and
        # avoids the QThreadStorage warnings caused by os._exit() bypassing
        # Qt's TLS cleanup.
        sys.exit(exit_code)
    except Exception as e:
        logging.error(f"FATAL ERROR in main: {e}")
        traceback.print_exc()
        logging.error("Application terminating due to fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
