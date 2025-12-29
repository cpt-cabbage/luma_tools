import os
import math
import traceback
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QSize,
    QRectF, Signal, QObject, QRect, QSequentialAnimationGroup,
    QParallelAnimationGroup, QFile, QTextStream, QThread, QRunnable,
    QThreadPool, Slot
)
from PySide2.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QProgressBar, QGraphicsOpacityEffect,
    QApplication, QFrame, QHBoxLayout, QGroupBox, QPushButton, 
    QListWidget, QListWidgetItem, QFileDialog, QSpinBox, QLineEdit, QTextEdit
)
from PySide2.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QPixmap


# ============================================================================
# THREADING UTILITIES - QThread Workers for Background Operations
# ============================================================================

class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Signals:
        started: Emitted when the worker starts
        finished: Emitted when the worker finishes successfully
        error: Emitted when an error occurs (str: error message, str: traceback)
        result: Emitted with the result of the operation (object: result)
        progress: Emitted with progress updates (int: percentage, str: message)
    """
    started = Signal()
    finished = Signal()
    error = Signal(str, str)  # error message, traceback
    result = Signal(object)   # result data
    progress = Signal(int, str)  # progress percentage, message


class Worker(QRunnable):
    """
    Generic worker thread for running functions in the background.

    This prevents blocking the GUI thread and keeps spinners smooth.

    Usage:
        worker = Worker(some_function, arg1, arg2, kwarg1=value1)
        worker.signals.result.connect(handle_result)
        worker.signals.error.connect(handle_error)
        worker.signals.progress.connect(update_progress)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, fn, *args, **kwargs):
        """
        Initialize the worker.

        Args:
            fn: The function to run in the background
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
                     Note: 'progress_callback' kwarg will be replaced with signal emitter
        """
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Only add progress_callback if the function accepts it
        import inspect
        sig = inspect.signature(fn)
        if 'progress_callback' in sig.parameters:
            # Replace progress_callback with signal emitter if present
            if 'progress_callback' in self.kwargs:
                del self.kwargs['progress_callback']
            self.kwargs['progress_callback'] = self.signals.progress.emit

    @Slot()
    def run(self):
        """
        Execute the worker function with error handling.
        """
        try:
            self.signals.started.emit()
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
            self.signals.finished.emit()
        except Exception as e:
            error_msg = str(e)
            tb = traceback.format_exc()
            self.signals.error.emit(error_msg, tb)
            print(f"Worker error: {error_msg}")
            print(tb)


class ThreadedOperation(QObject):
    """
    Helper class to manage threaded operations with proper cleanup.

    Usage:
        operation = ThreadedOperation(function, arg1, arg2)
        operation.signals.result.connect(handle_result)
        operation.signals.error.connect(handle_error)
        operation.start()
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.worker = Worker(fn, *args, **kwargs)
        self.signals = self.worker.signals

    def start(self):
        """Start the operation on a background thread."""
        QThreadPool.globalInstance().start(self.worker)


def report_progress(callback, progress, message):
    """
    Report progress and process Qt events to keep UI responsive.

    This is a utility function to consolidate the common pattern of:
    - Checking if callback exists
    - Calling the callback
    - Processing Qt events to keep the UI responsive

    Args:
        callback: Progress callback function(progress, message) or None
        progress: Progress value (0-100)
        message: Status message string

    Example:
        report_progress(progress_callback, 50, "Halfway done...")
    """
    if callback:
        callback(progress, message)
        QApplication.processEvents()


# ============================================================================
# LOADING STYLES - Constants and Stylesheets
# ============================================================================

class LoadingStyles:
    """Unified styling constants for loading screens."""

    # Colors - AYON Theme
    PRIMARY_COLOR = QColor(74, 158, 255)  # #4a9eff - Light blue accent (for spinner)
    BACKGROUND_COLOR = QColor(33, 37, 43)  # #21252b - Dark background
    SECONDARY_BG_COLOR = QColor(44, 49, 58)  # #2c313a - Lighter dark
    TEXT_PRIMARY_COLOR = QColor(255, 255, 255)  # #ffffff - White
    TEXT_SECONDARY_COLOR = QColor(197, 202, 211)  # #c5cad3 - Light gray
    TEXT_TERTIARY_COLOR = QColor(121, 126, 137)  # #797e89 - Darker gray

    # Color strings (for stylesheets)
    PRIMARY_COLOR_STR = "#4a9eff"
    BACKGROUND_COLOR_STR = "#21252b"
    SECONDARY_BG_COLOR_STR = "#2c313a"
    TEXT_PRIMARY_COLOR_STR = "#ffffff"
    TEXT_SECONDARY_COLOR_STR = "#c5cad3"
    TEXT_TERTIARY_COLOR_STR = "#797e89"

    # Fonts
    TITLE_FONT = QFont("Segoe UI", 24, QFont.Bold)
    MAIN_TEXT_FONT = QFont("Segoe UI", 12)
    SUB_TEXT_FONT = QFont("Segoe UI", 9)
    OVERLAY_TITLE_SIZE = "16pt"
    OVERLAY_SUB_SIZE = "10pt"

    # Logo
    LOGO_SIZE_SPLASH = (200, 200)  # Larger for splash screen - increased for more prominence
    LOGO_SIZE_OVERLAY = (100, 100)  # Smaller for overlay

    # Spinner
    SPINNER_SIZE = (40, 40)  # Reduced size for cleaner look
    SPINNER_LINE_COUNT = 12
    SPINNER_LINE_LENGTH = 10  # Shorter lines for smaller spinner
    SPINNER_LINE_WIDTH = 2  # Thinner lines
    SPINNER_INNER_RADIUS = 6  # Smaller inner radius
    SPINNER_ROTATION_INTERVAL = 50  # milliseconds (20 FPS)

    # Layout
    SPLASH_SIZE = (500, 450)  # Increased height to accommodate larger logo
    SPLASH_MARGIN = 40
    SPLASH_SPACING = 15  # Reduced spacing for better fit
    OVERLAY_SPACING = 20
    BORDER_RADIUS = 15
    OVERLAY_BORDER_RADIUS = 10

    # Progress bar
    PROGRESS_BAR_HEIGHT = 4
    PROGRESS_BAR_SPLASH_HEIGHT = 4
    PROGRESS_BAR_OVERLAY_HEIGHT = 6
    PROGRESS_BAR_OVERLAY_WIDTH = 300

    # Animation
    FADE_DURATION = 300  # milliseconds
    SPINNER_ROTATION_ANGLE = 30  # degrees per step

    @staticmethod
    def get_logo_path():
        """Get the path to the logo file."""
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Icon_white_small.png"
        )

    @staticmethod
    def get_progress_bar_stylesheet(height=4):
        """Get unified progress bar stylesheet."""
        return f"""
            QProgressBar {{
                background-color: {LoadingStyles.SECONDARY_BG_COLOR_STR};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {LoadingStyles.PRIMARY_COLOR_STR};
                border-radius: 2px;
            }}
        """

    @staticmethod
    def get_overlay_progress_stylesheet():
        """Get progress bar stylesheet for overlay (with gradient)."""
        return f"""
            QProgressBar {{
                background-color: rgba(44, 49, 58, 180);
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #5cadff, stop:1 {LoadingStyles.PRIMARY_COLOR_STR});
                border-radius: 3px;
            }}
        """

    @staticmethod
    def get_overlay_background_stylesheet():
        """Get overlay background stylesheet."""
        return """
            LoadingOverlay {
                background-color: rgba(33, 37, 43, 220);
                border-radius: 10px;
            }
        """

    @staticmethod
    def get_status_label_stylesheet():
        """Get status label stylesheet for overlay."""
        return f"""
            QLabel {{
                color: {LoadingStyles.PRIMARY_COLOR_STR};
                font-size: {LoadingStyles.OVERLAY_TITLE_SIZE};
                font-weight: bold;
                background: transparent;
            }}
        """

    @staticmethod
    def get_substatus_label_stylesheet():
        """Get sub-status label stylesheet for overlay."""
        return f"""
            QLabel {{
                color: {LoadingStyles.TEXT_SECONDARY_COLOR_STR};
                font-size: {LoadingStyles.OVERLAY_SUB_SIZE};
                background: transparent;
            }}
        """


# ============================================================================
# PREMIUM UI COMPONENTS
# ============================================================================

class StatusColors:
    """Standard color palette for UI status elements."""
    SUCCESS = "#2ecc71"
    WARNING = "#f39c12"
    ERROR = "#e74c3c"
    INFO = "#3498db"
    NEUTRAL = "#95a5a6"
    ACCENT = "#3b82f6"


class ToastNotification(QWidget):
    """
    Floating toast notification that appears at the top/bottom of the window.
    """
    def __init__(self, message, type="info", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.layout = QVBoxLayout(self)
        self.label = QLabel(message)
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)
        
        # Color based on type
        color_map = {
            "success": "#2ecc71",
            "error": "#e74c3c",
            "warning": "#f39c12",
            "info": "#3498db"
        }
        self.color = color_map.get(type, "#3498db")
        
        self.setObjectName("ToastNotification")
        self.setProperty("type", type)
        
        # Animations
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        
        # Auto-hide timer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_toast)

    def show_toast(self, duration=3000):
        if not self.parent(): return
        
        # Position at top center
        parent_rect = self.parent().geometry()
        self.adjustSize()
        x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
        y = parent_rect.y() + 40
        self.move(x, y)
        
        self.show()
        self.opacity_anim.setDuration(300)
        self.opacity_anim.setStartValue(0)
        self.opacity_anim.setEndValue(1)
        self.opacity_anim.start()
        
        self.timer.start(duration)

    def hide_toast(self):
        self.opacity_anim.setDuration(500)
        self.opacity_anim.setStartValue(1)
        self.opacity_anim.setEndValue(0)
        self.opacity_anim.finished.connect(self.deleteLater)
        self.opacity_anim.start()


class ComfyUIStatusBanner(QWidget):
    """
    Enhanced status banner with pulsing animations and clear indicators.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)
        
        self.label = QLabel("Ready to submit")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-weight: bold; color: white;")
        self.layout.addWidget(self.label)
        
        self.setFixedHeight(40)
        self.setStyleSheet("background-color: #2c3e50; border-radius: 4px;")

    def set_status(self, message, color="#34495e"):
        self.label.setText(message)
        self.setStyleSheet(f"background-color: {color}; border-radius: 4px;")


class BatchImageSelector(QWidget):
    """
    Custom widget for selecting multiple images with preview thumbnails.
    """
    images_changed = Signal(list)

    # Thumbnail size for list items
    THUMBNAIL_SIZE = 48

    def __init__(self, supported_extensions=None, parent=None):
        super().__init__(parent)
        self.supported_extensions = supported_extensions or ['.png', '.jpg', '.jpeg', '.exr']
        self.selected_files = []
        self._last_browse_dir = ""
        self._thumbnail_cache = {}

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        self.toolbar = QWidget()
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)

        self.add_btn = QtWidgets.QPushButton("Add Images...")
        self.add_btn.clicked.connect(self.browse_images)
        self.toolbar_layout.addWidget(self.add_btn)

        self.clear_btn = QtWidgets.QPushButton("Clear All")
        self.clear_btn.clicked.connect(self.clear_images)
        self.toolbar_layout.addWidget(self.clear_btn)

        self.count_label = QLabel("No images selected")
        self.toolbar_layout.addWidget(self.count_label)
        self.toolbar_layout.addStretch()

        self.main_layout.addWidget(self.toolbar)

        # List area with icon view mode for thumbnails
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setMinimumHeight(150)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setIconSize(QSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE))
        self.list_widget.setSpacing(2)
        self.main_layout.addWidget(self.list_widget)

    def set_last_browse_dir(self, directory):
        """Set the last browse directory (called from main app)."""
        self._last_browse_dir = directory

    def get_last_browse_dir(self):
        """Get the last browse directory."""
        return self._last_browse_dir

    def browse_images(self):
        start_dir = self._last_browse_dir or ""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Images", start_dir, "Images (*.png *.jpg *.jpeg *.exr)"
        )
        if files:
            # Remember the directory
            self._last_browse_dir = os.path.dirname(files[0])
            self.add_images(files)

    def add_images(self, paths):
        for path in paths:
            if path not in self.selected_files:
                self.selected_files.append(path)
                self._add_list_item_with_thumbnail(path)

        self._update_ui()
        self.images_changed.emit(self.selected_files)

    def _add_list_item_with_thumbnail(self, path):
        """Add a list item with a thumbnail preview."""
        item = QtWidgets.QListWidgetItem(os.path.basename(path))
        item.setToolTip(path)

        # Generate thumbnail
        thumbnail = self._get_thumbnail(path)
        if thumbnail:
            item.setIcon(QtGui.QIcon(thumbnail))

        self.list_widget.addItem(item)

    def _get_thumbnail(self, path):
        """Get or generate thumbnail for an image file."""
        if path in self._thumbnail_cache:
            return self._thumbnail_cache[path]

        try:
            ext = os.path.splitext(path)[1].lower()

            if ext == '.exr':
                # For EXR files, create a placeholder thumbnail
                pixmap = self._create_placeholder_thumbnail("EXR")
            else:
                # For standard image formats, load and scale
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(
                        self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE,
                        Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                else:
                    pixmap = self._create_placeholder_thumbnail("?")

            self._thumbnail_cache[path] = pixmap
            return pixmap

        except Exception as e:
            print(f"Error generating thumbnail for {path}: {e}")
            return self._create_placeholder_thumbnail("!")

    def _create_placeholder_thumbnail(self, text):
        """Create a placeholder thumbnail with text."""
        pixmap = QPixmap(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#3c414b"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw text
        painter.setPen(QColor("#888888"))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)

        painter.end()
        return pixmap

    def clear_images(self):
        self.selected_files = []
        self.list_widget.clear()
        self._thumbnail_cache.clear()
        self._update_ui()
        self.images_changed.emit([])

    def _update_ui(self):
        count = len(self.selected_files)
        self.count_label.setText(f"{count} image(s) selected" if count > 0 else "No images selected")


class CollapsibleSection(QWidget):
    """
    A collapsible UI section for organizing complex forms.
    """
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self.toggle_btn = QtWidgets.QPushButton(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(True)
        self.toggle_btn.toggled.connect(self.on_toggled)
        self.main_layout.addWidget(self.toggle_btn)
        
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.main_layout.addWidget(self.content)

    def on_toggled(self, is_checked):
        self.content.setVisible(is_checked)


class StepGroupBox(QtWidgets.QGroupBox):
    """GroupBox with step number badge for wizard-style layouts."""
    def __init__(self, step_number, title, parent=None):
        super().__init__(f"Step {step_number}: {title}", parent)
        self.setObjectName(f"Step{step_number}GroupBox")


class StepProgressIndicator(QWidget):
    """Horizontal progress indicator with step circles."""
    def __init__(self, steps, parent=None):
        super().__init__(parent)
        self.steps = steps
        self.current_step = 0
        self.setFixedHeight(50)


class EmptyStateWidget(QWidget):
    """Visual placeholder when lists are empty."""
    def __init__(self, text, icon=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)


class ThumbnailRenderList(QtWidgets.QListWidget):
    """List widget specifically for renders with thumbnails."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(5)


class RenderListItem(QtWidgets.QListWidgetItem):
    """Item for ThumbnailRenderList."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)


# ============================================================================
# MODERN UI ENHANCEMENTS & ANIMATIONS
# ============================================================================

def enhance_ui(window):
    """
    Initialize modern UI enhancements and animations.
    """
    class Animator(QObject):
        def __init__(self, target):
            super().__init__()
            self.target = target
            self.redirect_to_splash = False
            self.splash_screen = None
            
        def show_success(self, message):
            print(f"SUCCESS: {message}")
            toast = ToastNotification(message, "success", self.target)
            toast.show_toast()
            
        def show_error(self, message):
            print(f"ERROR: {message}")
            toast = ToastNotification(message, "error", self.target)
            toast.show_toast()
            
        def show_warning(self, message):
            print(f"WARNING: {message}")
            toast = ToastNotification(message, "warning", self.target)
            toast.show_toast()

        def show_info(self, message):
            print(f"INFO: {message}")
            toast = ToastNotification(message, "info", self.target)
            toast.show_toast()

    return Animator(window)


# ============================================================================
# SPINNER WIDGETS
# ============================================================================

class SpinnerWidget(QWidget):
    """
    Modern circular spinner widget with smooth animation.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.setMinimumSize(*LoadingStyles.SPINNER_SIZE)

        # Make background transparent
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Spinner colors
        self.primary_color = LoadingStyles.PRIMARY_COLOR
        self.secondary_color = LoadingStyles.SECONDARY_BG_COLOR

        # Animation properties
        self.line_count = LoadingStyles.SPINNER_LINE_COUNT
        self.line_length = LoadingStyles.SPINNER_LINE_LENGTH
        self.line_width = LoadingStyles.SPINNER_LINE_WIDTH
        self.inner_radius = LoadingStyles.SPINNER_INNER_RADIUS

    def start(self):
        """Start the spinner animation."""
        self.timer.start(LoadingStyles.SPINNER_ROTATION_INTERVAL)

    def stop(self):
        """Stop the spinner animation."""
        self.timer.stop()

    def rotate(self):
        """Rotate the spinner."""
        self.angle = (self.angle + LoadingStyles.SPINNER_ROTATION_ANGLE) % 360
        self.update()

    def paintEvent(self, event):
        """Paint the spinner."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Clear background to transparent
        painter.fillRect(self.rect(), Qt.transparent)

        # Center the spinner
        width = self.width()
        height = self.height()
        painter.translate(width / 2, height / 2)
        painter.rotate(self.angle)

        # Draw spinning lines
        for i in range(self.line_count):
            # Calculate opacity for trail effect
            opacity = 1.0 - (i / self.line_count)

            # Set pen with opacity
            color = QColor(self.primary_color)
            color.setAlphaF(opacity)
            pen = QPen(color)
            pen.setWidth(self.line_width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)

            # Draw line
            painter.drawLine(
                self.inner_radius, 0,
                self.inner_radius + self.line_length, 0
            )

            # Rotate for next line
            painter.rotate(360.0 / self.line_count)


class PulsingDotsWidget(QWidget):
    """
    Alternative loading animation with pulsing dots.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dot_count = 3
        self.current_dot = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.pulse)
        self.setMinimumSize(80, 30)

        self.dot_color = LoadingStyles.PRIMARY_COLOR
        self.dot_radius = 8
        self.dot_spacing = 20

    def start(self):
        """Start the pulsing animation."""
        self.timer.start(400)  # Pulse every 400ms

    def stop(self):
        """Stop the pulsing animation."""
        self.timer.stop()

    def pulse(self):
        """Move to next dot."""
        self.current_dot = (self.current_dot + 1) % self.dot_count
        self.update()

    def paintEvent(self, event):
        """Paint the pulsing dots."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # Calculate starting position to center dots
        total_width = (self.dot_count - 1) * self.dot_spacing
        start_x = (width - total_width) / 2
        center_y = height / 2

        # Draw dots
        for i in range(self.dot_count):
            x = start_x + (i * self.dot_spacing)

            # Scale the active dot
            if i == self.current_dot:
                radius = self.dot_radius * 1.5
                color = self.dot_color
            else:
                radius = self.dot_radius
                color = QColor(self.dot_color)
                color.setAlphaF(0.5)

            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                QRectF(x - radius, center_y - radius, radius * 2, radius * 2)
            )


class InlineSpinner(QWidget):
    """
    Compact inline spinner for showing loading state next to widgets.
    Perfect for showing "loading passes..." next to a list.
    """

    def __init__(self, parent=None, size=24):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.spinner_size = size
        self.setFixedSize(size, size)

        # Spinner colors
        self.primary_color = LoadingStyles.PRIMARY_COLOR

        # Animation properties
        self.line_count = 8
        self.line_length = int(size * 0.3)
        self.line_width = max(2, int(size * 0.08))
        self.inner_radius = int(size * 0.15)

        # Start hidden
        self.hide()

    def start(self):
        """Start the spinner animation and show."""
        self.show()
        self.timer.start(80)  # Faster rotation for smaller spinner

    def stop(self):
        """Stop the spinner animation and hide."""
        self.timer.stop()
        self.hide()

    def rotate(self):
        """Rotate the spinner."""
        self.angle = (self.angle + 45) % 360
        self.update()

    def paintEvent(self, event):
        """Paint the spinner."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Center the spinner
        width = self.width()
        height = self.height()
        painter.translate(width / 2, height / 2)
        painter.rotate(self.angle)

        # Draw spinning lines
        for i in range(self.line_count):
            # Calculate opacity for trail effect
            opacity = 1.0 - (i / self.line_count)

            # Set pen with opacity
            color = QColor(self.primary_color)
            color.setAlphaF(opacity)
            pen = QPen(color)
            pen.setWidth(self.line_width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)

            # Draw line
            painter.drawLine(
                self.inner_radius, 0,
                self.inner_radius + self.line_length, 0
            )

            # Rotate for next line
            painter.rotate(360.0 / self.line_count)


# ============================================================================
# LOADING OVERLAY
# ============================================================================

class LoadingOverlay(QWidget):
    """
    Modern loading overlay with animated spinner and status text.
    Covers the entire parent widget with a semi-transparent background.
    """

    def __init__(self, parent=None, style='spinner'):
        super().__init__(parent)

        # Setup overlay appearance
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(LoadingStyles.get_overlay_background_stylesheet())

        # Create layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(LoadingStyles.OVERLAY_SPACING)

        # Create logo
        logo_path = LoadingStyles.get_logo_path()
        self.logo_label = QLabel(self)
        self.logo_label.setStyleSheet("background: transparent;")
        # Set minimum size to ensure logo is not cut off
        self.logo_label.setMinimumSize(*LoadingStyles.LOGO_SIZE_OVERLAY)
        self.logo_label.setMaximumSize(*LoadingStyles.LOGO_SIZE_OVERLAY)
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Scale to a reasonable size while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                *LoadingStyles.LOGO_SIZE_OVERLAY,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.logo_label.setPixmap(scaled_pixmap)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setScaledContents(False)  # Don't scale contents, use actual pixmap size

        # Create loading animation
        if style == 'spinner':
            self.animation_widget = SpinnerWidget(self)
        else:
            self.animation_widget = PulsingDotsWidget(self)

        # Create status label
        self.status_label = QLabel("Loading...", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(LoadingStyles.get_status_label_stylesheet())

        # Create sub-status label
        self.substatus_label = QLabel("", self)
        self.substatus_label.setAlignment(Qt.AlignCenter)
        self.substatus_label.setStyleSheet(LoadingStyles.get_substatus_label_stylesheet())

        # Create progress bar (optional, hidden by default)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(LoadingStyles.PROGRESS_BAR_OVERLAY_WIDTH)
        self.progress_bar.setFixedHeight(LoadingStyles.PROGRESS_BAR_OVERLAY_HEIGHT)
        self.progress_bar.setStyleSheet(LoadingStyles.get_overlay_progress_stylesheet())
        self.progress_bar.hide()

        # Add widgets to layout
        layout.addStretch()
        layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.animation_widget, alignment=Qt.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addWidget(self.substatus_label)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)
        layout.addStretch()

        # Setup fade animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        # Hide initially
        self.hide()

    def show_loading(self, message="Loading...", submessage="", show_progress=False):
        """
        Show the loading overlay with a message.

        Args:
            message: Main loading message
            submessage: Optional secondary message
            show_progress: Whether to show the progress bar
        """
        # Update text
        self.status_label.setText(message)
        self.substatus_label.setText(submessage)

        # Show/hide progress bar
        if show_progress:
            self.progress_bar.show()
            self.progress_bar.setValue(0)
        else:
            self.progress_bar.hide()

        # Resize to cover parent
        if self.parent():
            self.resize(self.parent().size())

        # Show and start animation
        self.show()
        self.raise_()  # Bring to front
        self.animation_widget.start()

        # Fade in
        self.fade_in()

    def hide_loading(self):
        """Hide the loading overlay with fade out animation."""
        # Stop animation
        self.animation_widget.stop()

        # Fade out
        self.fade_out()

        # Hide after fade
        QTimer.singleShot(LoadingStyles.FADE_DURATION, self.hide)

    def update_message(self, message, submessage=""):
        """
        Update the loading message.

        Args:
            message: New main message
            submessage: New secondary message
        """
        self.status_label.setText(message)
        self.substatus_label.setText(submessage)

    def update_progress(self, value):
        """
        Update the progress bar value.

        Args:
            value: Progress value (0-100)
        """
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
        self.progress_bar.setValue(value)

    def fade_in(self, duration=None):
        """Fade in the overlay."""
        if duration is None:
            duration = LoadingStyles.FADE_DURATION
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(duration)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.fade_animation.start()

    def fade_out(self, duration=None):
        """Fade out the overlay."""
        if duration is None:
            duration = LoadingStyles.FADE_DURATION
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(duration)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.fade_animation.start()

    def resizeEvent(self, event):
        """Handle parent resize to keep overlay covering entire area."""
        if self.parent():
            self.resize(self.parent().size())
        super().resizeEvent(event)


class LoadingManager(QObject):
    """
    Manager class to handle loading overlays for the application.
    """

    def __init__(self, parent_widget):
        super().__init__()
        self.parent_widget = parent_widget
        self.overlay = None
        self._create_overlay()

    def _create_overlay(self):
        """Create the loading overlay."""
        self.overlay = LoadingOverlay(self.parent_widget, style='spinner')

    def show(self, message="Loading...", submessage="", show_progress=False):
        """
        Show loading overlay.

        Args:
            message: Main loading message
            submessage: Optional secondary message
            show_progress: Whether to show progress bar
        """
        self.overlay.show_loading(message, submessage, show_progress)

    def hide(self):
        """Hide loading overlay."""
        self.overlay.hide_loading()

    def update_message(self, message, submessage=""):
        """
        Update loading message.

        Args:
            message: New main message
            submessage: New secondary message
        """
        self.overlay.update_message(message, submessage)

    def update_progress(self, value):
        """
        Update progress value.

        Args:
            value: Progress value (0-100)
        """
        self.overlay.update_progress(value)


# ============================================================================
# UI ANIMATIONS
# ============================================================================

class UIAnimations:
    """
    Animation manager for the shot tools UI.
    Adds professional animations without modifying existing functionality.
    """

    def __init__(self, parent_widget):
        """
        Initialize the animation manager.

        Args:
            parent_widget: The main application widget
        """
        self.parent = parent_widget
        self.ui = parent_widget.ui
        self._animations = []  # Keep references to prevent garbage collection
        self.loading = None  # Loading manager

        # Splash screen redirection (avoids monkey-patching)
        self.redirect_to_splash = False
        self.splash_screen = None

    def setup_animations(self):
        """Setup all animations for the UI."""
        # Setup button animations
        self._setup_button_hover_effects()

        # Setup progress bar animation
        self._setup_progress_animation()

        # Add smooth transitions for status updates
        self._setup_status_animations()

        # Setup loading overlay
        self.loading = LoadingManager(self.parent)
        print("Loading overlay enabled")

    def _setup_button_hover_effects(self):
        """Add subtle hover effects to buttons."""
        buttons = [
            self.ui.BuildPasses,
            self.ui.ScanRenders,
            self.ui.CleanFiles,
            self.ui.RescanCleanFiles,
            self.ui.MP4ScanRenders,
            self.ui.MP4BrowseOutput,
            self.ui.MP4BrowseCustomPath,
            self.ui.MP4Generate
        ]

        for button in buttons:
            if hasattr(button, 'installEventFilter'):
                button.installEventFilter(self.parent)

    def _setup_progress_animation(self):
        """Setup smooth progress bar animation."""
        self.progress_animation = QPropertyAnimation(self.ui.progressBar, b"value")
        self.progress_animation.setDuration(500)
        self.progress_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._animations.append(self.progress_animation)

    def _setup_status_animations(self):
        """Setup animations for status label updates."""
        # Create opacity effect for status label
        self.status_opacity = QGraphicsOpacityEffect(self.ui.StatusLabel)
        self.ui.StatusLabel.setGraphicsEffect(self.status_opacity)
        self.status_opacity.setOpacity(1.0)

    def animate_button_click(self, button):
        """
        Animate button click with scale effect.

        Args:
            button: The button widget to animate
        """
        if not button.isEnabled():
            return

        original_geometry = button.geometry()

        # Shrink animation
        shrink = QPropertyAnimation(button, b"geometry")
        shrink.setDuration(80)
        shrink.setStartValue(original_geometry)
        shrink.setEndValue(QRect(
            original_geometry.x() + 2,
            original_geometry.y() + 2,
            original_geometry.width() - 4,
            original_geometry.height() - 4
        ))
        shrink.setEasingCurve(QEasingCurve.InOutQuad)

        # Expand back animation
        expand = QPropertyAnimation(button, b"geometry")
        expand.setDuration(80)
        expand.setStartValue(shrink.endValue())
        expand.setEndValue(original_geometry)
        expand.setEasingCurve(QEasingCurve.InOutQuad)

        # Create sequence
        sequence = QSequentialAnimationGroup()
        sequence.addAnimation(shrink)
        sequence.addAnimation(expand)
        sequence.start()

        # Store reference
        self._animations.append(sequence)
        # Clean up after animation
        QTimer.singleShot(200, lambda: self._cleanup_animation(sequence))

    def animate_progress(self, start, end, duration=500):
        """
        Animate progress bar smoothly.

        Args:
            start: Starting value (0-100)
            end: Ending value (0-100)
            duration: Animation duration in milliseconds
        """
        self.progress_animation.stop()
        self.progress_animation.setStartValue(start)
        self.progress_animation.setEndValue(end)
        self.progress_animation.setDuration(duration)
        self.progress_animation.start()

    def update_status_animated(self, message, color="#4a9eff"):
        """
        Update status label with fade animation.

        Args:
            message: Status message to display
            color: Color for the status text (hex string)
        """
        # Set the message
        self.ui.StatusLabel.setText(message)

        # Apply color
        self.ui.StatusLabel.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 10pt;")

        # Fade animation
        fade_anim = QPropertyAnimation(self.status_opacity, b"opacity")
        fade_anim.setDuration(300)
        fade_anim.setStartValue(0.3)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        fade_anim.start()

        # Store reference
        self._animations.append(fade_anim)
        QTimer.singleShot(350, lambda: self._cleanup_animation(fade_anim))

    def pulse_button(self, button):
        """
        Create a pulsing effect to draw attention to a button.

        Args:
            button: The button widget to pulse
        """
        original_style = button.styleSheet()

        def pulse_on():
            button.setStyleSheet(
                original_style +
                "background-color: #5cadff; border: 2px solid #4a9eff;"
            )
            QTimer.singleShot(300, pulse_off)

        def pulse_off():
            button.setStyleSheet(original_style)

        pulse_on()

    def fade_in_widget(self, widget, duration=300):
        """
        Fade in a widget.

        Args:
            widget: The widget to fade in
            duration: Animation duration in milliseconds
        """
        opacity_effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(opacity_effect)

        fade_anim = QPropertyAnimation(opacity_effect, b"opacity")
        fade_anim.setDuration(duration)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        fade_anim.start()

        self._animations.append(fade_anim)
        QTimer.singleShot(duration + 50, lambda: self._cleanup_animation(fade_anim))

    def fade_out_widget(self, widget, duration=300):
        """
        Fade out a widget.

        Args:
            widget: The widget to fade out
            duration: Animation duration in milliseconds
        """
        opacity_effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(opacity_effect)

        fade_anim = QPropertyAnimation(opacity_effect, b"opacity")
        fade_anim.setDuration(duration)
        fade_anim.setStartValue(1.0)
        fade_anim.setEndValue(0.0)
        fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        fade_anim.start()

        self._animations.append(fade_anim)
        QTimer.singleShot(duration + 50, lambda: self._cleanup_animation(fade_anim))

    def _cleanup_animation(self, animation):
        """
        Clean up animation reference.

        Args:
            animation: The animation to clean up
        """
        if animation in self._animations:
            self._animations.remove(animation)

    # Loading overlay methods
    def show_loading(self, message="Loading...", submessage="", show_progress=False):
        """
        Show loading overlay with message.

        Args:
            message: Main loading message
            submessage: Optional secondary message
            show_progress: Whether to show progress bar
        """
        # Redirect to splash screen if flag is set
        if self.redirect_to_splash and self.splash_screen:
            progress = 50  # Start at 50% for scanning
            self.splash_screen.update_progress(progress, message, submessage)
        elif self.loading:
            self.loading.show(message, submessage, show_progress)

    def hide_loading(self):
        """Hide loading overlay."""
        # Don't hide if redirecting to splash (splash handles its own lifecycle)
        if self.redirect_to_splash and self.splash_screen:
            pass  # Splash screen will close itself
        elif self.loading:
            self.loading.hide()

    def update_loading_message(self, message, submessage=""):
        """
        Update loading message.

        Args:
            message: New main message
            submessage: New secondary message
        """
        # Redirect to splash screen if flag is set
        if self.redirect_to_splash and self.splash_screen:
            # Keep progress advancing during scan
            current_progress = self.splash_screen.progress_bar.value()
            new_progress = min(current_progress + 2, 90)
            self.splash_screen.update_progress(new_progress, message, submessage)
        elif self.loading:
            self.loading.update_message(message, submessage)

    def update_loading_progress(self, value):
        """
        Update loading progress.

        Args:
            value: Progress value (0-100)
        """
        # Redirect to splash screen if flag is set
        if self.redirect_to_splash and self.splash_screen:
            # Map the progress to 50-90 range
            mapped_progress = 50 + int(value * 0.4)
            current_text = self.splash_screen.main_label.text()
            current_sub = self.splash_screen.sub_label.text()
            self.splash_screen.update_progress(mapped_progress, current_text, current_sub)
        elif self.loading:
            self.loading.update_progress(value)


class StatusColors:
    """Predefined colors for status messages - AYON Theme Palette."""
    SUCCESS = "#10b981"  # Modern green
    ERROR = "#ef4444"    # Modern red
    WARNING = "#f59e0b"  # Modern orange
    INFO = "#4a9eff"     # AYON blue
    SCANNING = "#8b5cf6" # Modern purple


def enhance_ui(parent_widget):
    """
    Convenience function to enhance UI with animations.

    Args:
        parent_widget: The main application widget

    Returns:
        UIAnimations: The animation manager instance
    """
    animator = UIAnimations(parent_widget)
    animator.setup_animations()
    return animator


# ============================================================================
# STYLESHEET LOADING
# ============================================================================

def load_stylesheet():
    """
    Load and combine QDarkStyle base theme with custom stylesheet.

    Returns:
        str: Combined stylesheet string
    """
    from config import QDARKSTYLE_PATH, CUSTOM_STYLE_PATH

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

    print(f"Loaded custom stylesheet from: {CUSTOM_STYLE_PATH}")

    # Return combined stylesheet (custom style overrides base)
    return base_style + "\n" + custom_style


def apply_stylesheet(app):
    """
    Apply stylesheet to the application.

    Args:
        app: QApplication instance
    """
    stylesheet = load_stylesheet()
    app.setStyleSheet(stylesheet)
