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
    QApplication, QFrame, QHBoxLayout, QGroupBox, QPushButton, QCheckBox,
    QListWidget, QListWidgetItem, QFileDialog, QSpinBox, QLineEdit, QTextEdit,
    QMenu, QSizePolicy, QDialog, QDialogButtonBox, QPlainTextEdit, QComboBox
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
    Supports drag and drop of image files.
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

        # Drop zone frame with visual feedback
        self.drop_frame = QFrame()
        self.drop_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.drop_frame.setStyleSheet("""
            QFrame {
                border: 2px dashed #555555;
                border-radius: 5px;
                background-color: #2a2d32;
            }
            QFrame[drag_active="true"] {
                border: 2px dashed #4a9eff;
                background-color: #2a3a4a;
            }
        """)
        self.drop_frame_layout = QVBoxLayout(self.drop_frame)
        self.drop_frame_layout.setContentsMargins(0, 0, 0, 0)

        # List area with icon view mode for thumbnails
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setMinimumHeight(120)
        self.list_widget.setIconSize(QSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE))
        self.list_widget.setSpacing(2)
        self.list_widget.setStyleSheet("QListWidget { background-color: transparent; border: none; }")
        self.drop_frame_layout.addWidget(self.list_widget)

        # Drop hint label (shown when empty)
        self.drop_hint = QLabel("Drop images here or click 'Add Images...'")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setStyleSheet("color: #888888; font-style: italic; padding: 20px;")
        self.drop_frame_layout.addWidget(self.drop_hint)

        self.main_layout.addWidget(self.drop_frame)

        # Enable drag and drop on the widget itself
        self.setAcceptDrops(True)

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
        # Show/hide drop hint based on whether images are selected
        self.drop_hint.setVisible(count == 0)
        self.list_widget.setVisible(count > 0)

    def dragEnterEvent(self, event):
        """Handle drag enter - accept if contains files."""
        if event.mimeData().hasUrls():
            # Check if any URL is a supported image file
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in self.supported_extensions:
                        event.acceptProposedAction()
                        # Visual feedback
                        self.drop_frame.setProperty("drag_active", True)
                        self.drop_frame.style().unpolish(self.drop_frame)
                        self.drop_frame.style().polish(self.drop_frame)
                        return
        event.ignore()

    def dragLeaveEvent(self, event):
        """Handle drag leave - reset visual feedback."""
        self.drop_frame.setProperty("drag_active", False)
        self.drop_frame.style().unpolish(self.drop_frame)
        self.drop_frame.style().polish(self.drop_frame)

    def dropEvent(self, event):
        """Handle drop - add dropped image files."""
        self.drop_frame.setProperty("drag_active", False)
        self.drop_frame.style().unpolish(self.drop_frame)
        self.drop_frame.style().polish(self.drop_frame)

        if event.mimeData().hasUrls():
            valid_files = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext in self.supported_extensions and os.path.exists(file_path):
                        valid_files.append(file_path)

            if valid_files:
                self.add_images(valid_files)
                event.acceptProposedAction()
                return

        event.ignore()


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
        # Track last status to avoid animating unchanged messages
        self._last_status_message = None
        self._last_status_color = None

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
        Update status label with fade animation (only if message or color changed).

        Args:
            message: Status message to display
            color: Color for the status text (hex string)
        """
        # Skip animation if message and color haven't changed
        if message == self._last_status_message and color == self._last_status_color:
            return

        # Update tracking
        self._last_status_message = message
        self._last_status_color = color

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

    # Toast notification methods
    def show_success(self, message):
        """Show a success toast notification."""
        print(f"SUCCESS: {message}")
        toast = ToastNotification(message, "success", self.parent)
        toast.show_toast()

    def show_error(self, message):
        """Show an error toast notification."""
        print(f"ERROR: {message}")
        toast = ToastNotification(message, "error", self.parent)
        toast.show_toast()

    def show_warning(self, message):
        """Show a warning toast notification."""
        print(f"WARNING: {message}")
        toast = ToastNotification(message, "warning", self.parent)
        toast.show_toast()

    def show_info(self, message):
        """Show an info toast notification."""
        print(f"INFO: {message}")
        toast = ToastNotification(message, "info", self.parent)
        toast.show_toast()


class StatusColors:
    """Predefined colors for status messages - AYON Theme Palette."""
    SUCCESS = "#10b981"  # Modern green
    ERROR = "#ef4444"    # Modern red
    WARNING = "#f59e0b"  # Modern orange
    INFO = "#4a9eff"     # AYON blue
    SCANNING = "#8b5cf6" # Modern purple


# ============================================================================
# TAB GLOW EFFECT
# ============================================================================

class TabGlowEffect(QObject):
    """
    Creates a pulsing glow effect on a tab bar to draw user attention.

    Usage:
        glow = TabGlowEffect(tab_widget, tab_index, color="#ec4899")
        glow.start()
        # Later, when user clicks the tab:
        glow.stop()
    """

    def __init__(self, tab_widget, tab_index, color="#ec4899", parent=None):
        """
        Initialize the tab glow effect.

        Args:
            tab_widget: The QTabWidget containing the tabs
            tab_index: The index of the tab to glow
            color: Hex color for the glow (default: pink for gallery)
            parent: Parent QObject
        """
        super().__init__(parent)
        self.tab_widget = tab_widget
        self.tab_index = tab_index
        self.color = QColor(color)
        self.base_color = QColor(color)

        # Animation state
        self._intensity = 0.0
        self._direction = 1  # 1 = brightening, -1 = dimming
        self._is_running = False

        # Timer for animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._animation_interval = 50  # 20 FPS
        self._intensity_step = 0.08  # How much to change per frame

        # Store original icon for restoration
        self._original_icon = None

    def start(self, pulse_count=0):
        """
        Start the pulsing glow animation.

        Args:
            pulse_count: Number of pulses (0 = infinite until stopped)
        """
        if self._is_running:
            return

        self._is_running = True
        self._intensity = 0.0
        self._direction = 1
        self._pulse_count = pulse_count
        self._current_pulses = 0

        # Store original icon if not already stored
        if self._original_icon is None:
            self._original_icon = self.tab_widget.tabIcon(self.tab_index)

        self._timer.start(self._animation_interval)

    def stop(self):
        """Stop the glow animation and restore original appearance."""
        self._is_running = False
        self._timer.stop()

        # Restore original icon
        self._update_tab_style(0.0)

    def _animate(self):
        """Update the glow intensity for animation."""
        if not self._is_running:
            return

        # Update intensity
        self._intensity += self._intensity_step * self._direction

        # Clamp and reverse direction at bounds
        if self._intensity >= 1.0:
            self._intensity = 1.0
            self._direction = -1
        elif self._intensity <= 0.0:
            self._intensity = 0.0
            self._direction = 1
            self._current_pulses += 1

            # Check if we've completed the requested pulses
            if self._pulse_count > 0 and self._current_pulses >= self._pulse_count:
                self.stop()
                return

        # Apply the glow effect
        self._update_tab_style(self._intensity)

    def _update_tab_style(self, intensity):
        """
        Update the tab appearance to show the glow effect.

        Uses a pulsing notification dot indicator next to the tab icon,
        since setTabTextColor is overridden by stylesheets.

        Args:
            intensity: Glow intensity from 0.0 to 1.0
        """
        if intensity <= 0.01:
            # Reset to original icon (remove notification dot)
            if self._original_icon is not None:
                self.tab_widget.setTabIcon(self.tab_index, self._original_icon)
            return

        # Store original icon if not already stored
        if self._original_icon is None:
            self._original_icon = self.tab_widget.tabIcon(self.tab_index)

        # Create icon with pulsing notification dot
        glow_icon = self._create_notification_icon(intensity)
        if glow_icon:
            self.tab_widget.setTabIcon(self.tab_index, glow_icon)

    def _create_notification_icon(self, intensity):
        """
        Create an icon with a pulsing notification dot overlay.

        Args:
            intensity: Glow intensity from 0.0 to 1.0

        Returns:
            QIcon with notification dot, or None if no original icon
        """
        from PySide2.QtGui import QPixmap, QPainter, QIcon, QBrush, QPen
        from PySide2.QtCore import Qt, QRectF

        # Icon size - match the tab icon size (16px)
        icon_size = 16

        # Create a new pixmap for the icon with notification
        result_pixmap = QPixmap(icon_size, icon_size)
        result_pixmap.fill(Qt.transparent)

        painter = QPainter(result_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Draw the original icon if available
        if self._original_icon is not None and not self._original_icon.isNull():
            original_pixmap = self._original_icon.pixmap(icon_size, icon_size)
            if not original_pixmap.isNull():
                painter.drawPixmap(0, 0, original_pixmap)

        # Draw pulsing notification dot in top-right corner
        # Use a bright, attention-grabbing color (red/orange) instead of the subtle tab color
        dot_size = 6 + int(2 * intensity)  # Pulse between 6-8px
        dot_x = icon_size - dot_size
        dot_y = 0

        # Use a bright notification color - red for high visibility
        notification_color = QColor(255, 80, 80)  # Bright red

        # Calculate pulsing alpha (full visibility during pulse)
        alpha = int(200 + 55 * intensity)  # 200-255

        # Draw outer glow for visibility
        glow_color = QColor(255, 100, 100, int(100 * intensity))
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.NoPen)
        glow_rect = QRectF(dot_x - 2, dot_y - 1, dot_size + 3, dot_size + 3)
        painter.drawEllipse(glow_rect)

        # Draw main dot
        dot_color = QColor(notification_color)
        dot_color.setAlpha(alpha)
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.NoPen)
        dot_rect = QRectF(dot_x, dot_y, dot_size, dot_size)
        painter.drawEllipse(dot_rect)

        # Draw bright center highlight
        highlight_color = QColor(255, 255, 255, int(180 * intensity))
        painter.setBrush(QBrush(highlight_color))
        highlight_size = dot_size * 0.35
        highlight_rect = QRectF(
            dot_x + dot_size * 0.2,
            dot_y + dot_size * 0.15,
            highlight_size,
            highlight_size
        )
        painter.drawEllipse(highlight_rect)

        painter.end()

        return QIcon(result_pixmap)


class TabGlowManager(QObject):
    """
    Manages pulsing glow effects for multiple tabs.
    Handles starting/stopping glows and auto-stopping when tab is activated.
    """

    def __init__(self, tab_widget, parent=None):
        """
        Initialize the glow manager.

        Args:
            tab_widget: The QTabWidget to manage glows for
            parent: Parent QObject
        """
        super().__init__(parent)
        self.tab_widget = tab_widget
        self._active_glows = {}  # tab_index -> TabGlowEffect

        # Connect to tab change signal to auto-stop glow
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def start_glow(self, tab_index, color="#ec4899"):
        """
        Start a pulsing glow on the specified tab.

        Args:
            tab_index: Index of the tab to glow
            color: Hex color for the glow
        """
        print(f"[TabGlowManager] start_glow called for tab_index={tab_index}, color={color}")
        print(f"[TabGlowManager] Current tab index: {self.tab_widget.currentIndex()}")

        # Don't glow if this tab is currently active
        if self.tab_widget.currentIndex() == tab_index:
            print(f"[TabGlowManager] Skipping glow - tab is currently active")
            return

        # Stop existing glow on this tab if any
        if tab_index in self._active_glows:
            print(f"[TabGlowManager] Stopping existing glow on tab {tab_index}")
            self._active_glows[tab_index].stop()

        # Create and start new glow
        print(f"[TabGlowManager] Creating and starting new glow effect")
        glow = TabGlowEffect(self.tab_widget, tab_index, color, self)
        self._active_glows[tab_index] = glow
        glow.start()
        print(f"[TabGlowManager] Glow started successfully")

    def stop_glow(self, tab_index):
        """
        Stop the glow on the specified tab.

        Args:
            tab_index: Index of the tab to stop glowing
        """
        if tab_index in self._active_glows:
            self._active_glows[tab_index].stop()
            del self._active_glows[tab_index]

            # Reset tab text color to default
            tab_bar = self.tab_widget.tabBar()
            tab_bar.setTabTextColor(tab_index, QColor())  # Reset to default

    def stop_all_glows(self):
        """Stop all active glows."""
        for tab_index in list(self._active_glows.keys()):
            self.stop_glow(tab_index)

    def _on_tab_changed(self, index):
        """Auto-stop glow when user navigates to the glowing tab."""
        if index in self._active_glows:
            self.stop_glow(index)


# ============================================================================
# GALLERY WIDGETS
# ============================================================================

class FlowLayout(QtWidgets.QLayout):
    """
    A flow layout that arranges widgets in a row, wrapping to the next row when space runs out.
    Similar to CSS flexbox with flex-wrap: wrap.
    """

    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._item_list = []
        self._h_spacing = spacing
        self._v_spacing = spacing

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def horizontalSpacing(self):
        if self._h_spacing >= 0:
            return self._h_spacing
        return self._smart_spacing(QtWidgets.QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self._v_spacing >= 0:
            return self._v_spacing
        return self._smart_spacing(QtWidgets.QStyle.PM_LayoutVerticalSpacing)

    def _smart_spacing(self, pm):
        parent = self.parent()
        if parent is None:
            return -1
        elif parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        else:
            return parent.spacing()

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(+left, +top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._item_list:
            wid = item.widget()
            space_x = self.horizontalSpacing()
            if space_x == -1:
                space_x = wid.style().layoutSpacing(
                    QtWidgets.QSizePolicy.PushButton, QtWidgets.QSizePolicy.PushButton, Qt.Horizontal
                )
            space_y = self.verticalSpacing()
            if space_y == -1:
                space_y = wid.style().layoutSpacing(
                    QtWidgets.QSizePolicy.PushButton, QtWidgets.QSizePolicy.PushButton, Qt.Vertical
                )

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom



class ZoomableImageWidget(QtWidgets.QGraphicsView):
    """
    A widget that displays an image with support for zooming and panning.
    """
    double_clicked = Signal()
    zoom_changed = Signal(str)  # Emits zoom level as string (e.g., "100%", "Fit")

    # Predefined zoom levels
    ZOOM_LEVELS = ["Fit", "100%", "50%", "25%", "10%"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.viewport().setCursor(Qt.ArrowCursor)
        self.setStyleSheet("background: transparent;")

        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QtWidgets.QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        # Pan state
        self._is_panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0

        # Current zoom mode
        self._current_zoom = "Fit"
        
    def setPixmap(self, pixmap):
        self._scene.removeItem(self._pixmap_item)
        self._pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._pixmap_item)
        self.setSceneRect(self._pixmap_item.boundingRect())
        self._current_zoom = "Fit"
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        self.zoom_changed.emit("Fit")

    def setZoomLevel(self, level):
        """Set zoom to a predefined level.

        Args:
            level: One of "Fit", "100%", "50%", "25%", "10%"
        """
        if not self._pixmap_item.pixmap() or self._pixmap_item.pixmap().isNull():
            return

        self._current_zoom = level

        if level == "Fit":
            self.resetTransform()
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        else:
            # Parse percentage
            percentage = int(level.replace("%", ""))
            scale = percentage / 100.0

            # Reset transform and apply new scale
            self.resetTransform()
            self.scale(scale, scale)

            # Center the image
            self.centerOn(self._pixmap_item)

        self.zoom_changed.emit(level)

    def currentZoom(self):
        """Return the current zoom level string."""
        return self._current_zoom
        
    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        # Zoom
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        self.scale(zoom_factor, zoom_factor)

        # Update zoom tracking - calculate actual percentage
        current_scale = self.transform().m11() * 100
        self._current_zoom = f"{int(current_scale)}%"
        self.zoom_changed.emit(self._current_zoom)

        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start_x = event.x()
            self._pan_start_y = event.y()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta_x = event.x() - self._pan_start_x
            delta_y = event.y() - self._pan_start_y
            
            self._pan_start_x = event.x()
            self._pan_start_y = event.y()
            
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta_x)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta_y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class EmbeddedImageViewer(QWidget):
    """
    Embedded image viewer with keyboard navigation for use within the gallery tab.

    Controls:
    - Left/Right arrows or A/D: Navigate between images
    - Escape or Backspace: Close viewer and return to gallery
    - Home/End: Jump to first/last image
    - C: Copy prompt to clipboard (if available)
    - S: Copy settings to ComfyUI tab (if available)
    """
    closed = Signal()  # Emitted when user wants to close the viewer
    view_fullscreen = Signal(str, int)  # Emitted when user wants fullscreen (image_path, index)
    copy_settings_requested = Signal(dict)  # Emits metadata for copying settings to ComfyUI tab

    def __init__(self, image_paths, start_index=0, output_dir=None, parent=None):
        """
        Initialize the embedded viewer.

        Args:
            image_paths: List of image file paths
            start_index: Index of image to show first
            output_dir: Directory for metadata lookup
            parent: Parent widget
        """
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.current_index = start_index
        self.output_dir = output_dir

        self._setup_ui()
        self._load_current_image()

        # Ensure we can receive keyboard events
        self.setFocusPolicy(Qt.StrongFocus)

    def _setup_ui(self):
        """Set up the embedded viewer UI."""
        self.setStyleSheet("background-color: #1a1a1a;")

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar with back button and info
        self.top_bar = QWidget()
        self.top_bar.setStyleSheet("background-color: rgba(0, 0, 0, 0.5);")
        self.top_bar.setFixedHeight(40)

        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 5, 10, 5)

        # Back button
        self.back_btn = QPushButton("< Back to Gallery")
        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #4a9eff;
                border: none;
                font-size: 12px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                color: #7ab8ff;
            }
        """)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self._on_back)
        top_layout.addWidget(self.back_btn)

        top_layout.addStretch()

        # Counter label
        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("color: #888888; font-size: 12px;")
        top_layout.addWidget(self.counter_label)

        # Zoom dropdown
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(ZoomableImageWidget.ZOOM_LEVELS)
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.setFixedWidth(80)
        self.zoom_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: #cccccc;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QComboBox:hover {
                border-color: #4a9eff;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #888888;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #cccccc;
                selection-background-color: #4a9eff;
                border: 1px solid #555555;
            }
        """)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        top_layout.addWidget(self.zoom_combo)

        # Fullscreen button
        self.fullscreen_btn = QPushButton("Fullscreen")
        self.fullscreen_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: 1px solid #555555;
                border-radius: 3px;
                font-size: 11px;
                padding: 3px 10px;
            }
            QPushButton:hover {
                color: #ffffff;
                border-color: #4a9eff;
            }
        """)
        self.fullscreen_btn.setCursor(Qt.PointingHandCursor)
        self.fullscreen_btn.clicked.connect(self._on_fullscreen)
        top_layout.addWidget(self.fullscreen_btn)

        layout.addWidget(self.top_bar)

        # Image container with navigation
        image_container = QWidget()
        image_layout = QHBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)

        # Left nav button
        self.left_btn = QPushButton("<")
        self.left_btn.setFixedWidth(50)
        self.left_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.3);
                color: white;
                border: none;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: rgba(74, 158, 255, 0.5);
            }
            QPushButton:disabled {
                color: #333333;
            }
        """)
        self.left_btn.setCursor(Qt.PointingHandCursor)
        self.left_btn.clicked.connect(self._prev_image)
        image_layout.addWidget(self.left_btn)

        # Media display (images, 3D models, videos)
        self.image_stack = QtWidgets.QStackedWidget()
        image_layout.addWidget(self.image_stack, stretch=1)

        # 1. Zoomable Image View
        self.image_view = ZoomableImageWidget()
        self.image_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_view.customContextMenuRequested.connect(self._show_context_menu)
        self.image_view.double_clicked.connect(self.close)
        self.image_view.zoom_changed.connect(self._on_image_zoom_changed)
        self.image_stack.addWidget(self.image_view)

        # 2. 3D Model Viewer (GLB/GLTF) - Lazy initialization to avoid startup lag
        # The actual viewer widget will be created on first use
        self._has_glb_viewer = None  # None = not yet checked, True/False after check
        self.glb_viewer = None
        self._use_pyvista_viewer = False
        self._glb_viewer_initialized = False

        # 3. Video Player
        try:
            from PySide2.QtMultimedia import QMediaPlayer, QMediaContent
            from PySide2.QtMultimediaWidgets import QVideoWidget
            from PySide2.QtCore import QUrl
            
            self.video_widget = QVideoWidget()
            self.video_widget.setStyleSheet("background-color: #000000;")
            self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
            self.media_player.setVideoOutput(self.video_widget)
            self.image_stack.addWidget(self.video_widget)
            self._has_video_player = True
        except Exception as e:
            print(f"Video player not available: {e}")
            self._has_video_player = False
            self.video_widget = None
            self.media_player = None

        # 4. Message Label (for errors/unsupported formats)
        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("background-color: #1a1a1a; color: #888888; font-size: 16px;")
        self.image_stack.addWidget(self.message_label)

        # Right nav button
        self.right_btn = QPushButton(">")
        self.right_btn.setFixedWidth(50)
        self.right_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.3);
                color: white;
                border: none;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: rgba(74, 158, 255, 0.5);
            }
            QPushButton:disabled {
                color: #333333;
            }
        """)
        self.right_btn.setCursor(Qt.PointingHandCursor)
        self.right_btn.clicked.connect(self._next_image)
        image_layout.addWidget(self.right_btn)

        layout.addWidget(image_container, stretch=1)

        # Bottom info bar
        self.info_bar = QWidget()
        self.info_bar.setStyleSheet("background-color: rgba(0, 0, 0, 0.5);")
        self.info_bar.setFixedHeight(35)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(15, 5, 15, 5)

        # Filename
        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        info_layout.addWidget(self.filename_label)

        # 3D Model texture toggle (hidden by default)
        self.texture_toggle_btn = QPushButton("📷 Textured")
        self.texture_toggle_btn.setFixedHeight(25)
        self.texture_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 0 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5aa9ff;
            }
        """)
        self.texture_toggle_btn.clicked.connect(self._toggle_3d_render_mode)
        self.texture_toggle_btn.hide()  # Hidden by default, shown for 3D models
        info_layout.addWidget(self.texture_toggle_btn)

        # Keep camera checkbox for 3D models (hidden by default)
        self.keep_camera_checkbox = QCheckBox("Keep Camera")
        self.keep_camera_checkbox.setFixedHeight(25)
        self.keep_camera_checkbox.setStyleSheet("""
            QCheckBox {
                color: #888888;
                font-size: 11px;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background-color: #4a9eff;
                border-color: #4a9eff;
            }
            QCheckBox::indicator:hover {
                border-color: #4a9eff;
            }
        """)
        self.keep_camera_checkbox.setToolTip("Preserve camera position when navigating between 3D models")
        self.keep_camera_checkbox.hide()  # Hidden by default, shown for 3D models
        info_layout.addWidget(self.keep_camera_checkbox)

        self._3d_textured_mode = False  # Track current mode
        self._current_3d_path = None  # Track current 3D model path
        self._saved_camera_state = None  # Store camera state for preservation

        info_layout.addStretch()

        # Help hint
        help_label = QLabel("← → Navigate  |  Esc Back  |  C Copy Prompt")
        help_label.setStyleSheet("color: #555555; font-size: 10px;")
        info_layout.addWidget(help_label)

        layout.addWidget(self.info_bar)

    def showEvent(self, event):
        """Grab focus when shown."""
        super().showEvent(event)
        self.setFocus()

    def resizeEvent(self, event):
        """Handle resize."""
        super().resizeEvent(event)

    def _init_glb_viewer_async(self, callback=None):
        """
        Initialize the GLB viewer widget asynchronously.

        This defers the heavy import of PyVista/PyOpenGL to avoid lag on first click.
        The callback is called with True if viewer is ready, False if not available.
        """
        if self._glb_viewer_initialized:
            # Already initialized
            if callback:
                callback(self._has_glb_viewer)
            return

        # Show loading state with spinner
        self.message_label.setText("Initializing 3D viewer...")
        self.image_stack.setCurrentWidget(self.message_label)

        # Add inline spinner if not already present
        if not hasattr(self, '_init_spinner_shown'):
            self._init_spinner_shown = True
            # The message label will show the text, spinner would require more UI changes
            # For now just ensure the message is visible

        # Use a worker to do the heavy import in background
        from ui_components import Worker
        from PySide2.QtCore import QThreadPool

        def init_viewer():
            """Initialize viewer in background thread (import heavy modules)."""
            # Try PyVista first (better PBR support)
            try:
                from glb_viewer_pyvista import PyVistaGLBViewerWidget, is_pyvista_available
                if is_pyvista_available():
                    return ('pyvista', PyVistaGLBViewerWidget)
            except Exception as e:
                print(f"PyVista GLB viewer not available: {e}")

            # Fallback to OpenGL viewer
            try:
                from glb_viewer import GLBViewerWidget
                return ('opengl', GLBViewerWidget)
            except Exception as e:
                print(f"OpenGL GLB viewer not available: {e}")

            return (None, None)

        def on_init_complete(result):
            """Handle viewer initialization completion on main thread."""
            viewer_type, widget_class = result
            self._glb_viewer_initialized = True

            if widget_class:
                # Create the widget on the main thread
                self.glb_viewer = widget_class()
                self.image_stack.addWidget(self.glb_viewer)
                self._has_glb_viewer = True
                self._use_pyvista_viewer = (viewer_type == 'pyvista')
                print(f"Using {viewer_type} GLB viewer")
            else:
                self._has_glb_viewer = False

            if callback:
                callback(self._has_glb_viewer)

        def on_init_error(error, traceback):
            """Handle initialization error."""
            print(f"GLB viewer init error: {error}")
            self._glb_viewer_initialized = True
            self._has_glb_viewer = False
            if callback:
                callback(False)

        worker = Worker(init_viewer)
        worker.signals.result.connect(on_init_complete)
        worker.signals.error.connect(on_init_error)
        QThreadPool.globalInstance().start(worker)

    def _load_current_image(self):
        """Load and display the current media (image, 3D model, or video)."""
        if not self.image_paths or self.current_index < 0 or self.current_index >= len(self.image_paths):
            return

        media_path = self.image_paths[self.current_index]

        try:
            ext = os.path.splitext(media_path)[1].lower()

            # Stop any playing video from previous item
            if hasattr(self, '_has_video_player') and self._has_video_player and self.media_player:
                self.media_player.stop()

            # Handle 3D models (.glb, .gltf)
            if ext in ('.glb', '.gltf'):
                # Show texture toggle button and keep camera checkbox
                self.texture_toggle_btn.show()
                if hasattr(self, 'keep_camera_checkbox'):
                    self.keep_camera_checkbox.show()
                self._current_3d_path = media_path
                self._3d_textured_mode = False  # Start in textured/surface mode
                self.texture_toggle_btn.setText("🔲 Wireframe")  # Shows what clicking will do

                # Check if viewer needs lazy initialization
                if not self._glb_viewer_initialized:
                    # First time loading a 3D model - initialize viewer async
                    self.message_label.setText(f"Initializing 3D viewer...")
                    self.image_stack.setCurrentWidget(self.message_label)

                    # Store the path to load after initialization
                    self._pending_3d_path = media_path

                    def on_viewer_ready(available):
                        if available and hasattr(self, '_pending_3d_path'):
                            self._load_3d_model(self._pending_3d_path)
                        elif not available:
                            self.message_label.setText("3D Model Viewer Not Available\n\nInstall pyvista and pyvistaqt:\npip install pyvista pyvistaqt")
                            self.image_stack.setCurrentWidget(self.message_label)

                    self._init_glb_viewer_async(callback=on_viewer_ready)
                elif self._has_glb_viewer and self.glb_viewer:
                    # Viewer already initialized - load model directly
                    self._load_3d_model(media_path)
                else:
                    self.message_label.setText("3D Model Viewer Not Available\n\nInstall pyvista and pyvistaqt:\npip install pyvista pyvistaqt")
                    self.image_stack.setCurrentWidget(self.message_label)

            # Handle videos (.mp4, .mov, .avi, .webm)
            elif ext in ('.mp4', '.mov', '.avi', '.webm'):
                # Hide 3D controls for videos
                self.texture_toggle_btn.hide()
                if hasattr(self, 'keep_camera_checkbox'):
                    self.keep_camera_checkbox.hide()
                self._current_3d_path = None
                if hasattr(self, '_has_video_player') and self._has_video_player and self.media_player and self.video_widget:
                    from PySide2.QtMultimedia import QMediaContent
                    from PySide2.QtCore import QUrl
                    
                    # Load and play video
                    media_content = QMediaContent(QUrl.fromLocalFile(media_path))
                    self.media_player.setMedia(media_content)
                    self.image_stack.setCurrentWidget(self.video_widget)
                    self.media_player.play()
                else:
                    self.message_label.setText("Video Player Not Available\n\nPySide2 multimedia support required")
                    self.image_stack.setCurrentWidget(self.message_label)

            # Handle EXR (not supported)
            elif ext == '.exr':
                self.texture_toggle_btn.hide()
                if hasattr(self, 'keep_camera_checkbox'):
                    self.keep_camera_checkbox.hide()
                self._current_3d_path = None
                self.message_label.setText("EXR Preview Not Available")
                self.image_stack.setCurrentWidget(self.message_label)

            # Handle regular images (.png, .jpg, .jpeg, .webp, etc.)
            else:
                self.texture_toggle_btn.hide()
                if hasattr(self, 'keep_camera_checkbox'):
                    self.keep_camera_checkbox.hide()
                self._current_3d_path = None
                pixmap = QPixmap(media_path)
                if not pixmap.isNull():
                    self.image_view.setPixmap(pixmap)
                    self.image_stack.setCurrentWidget(self.image_view)
                else:
                    self.message_label.setText("Failed to load image")
                    self.image_stack.setCurrentWidget(self.message_label)

        except Exception as e:
            self.message_label.setText(f"Error: {e}")
            self.image_stack.setCurrentWidget(self.message_label)

        self._update_info()

    def _load_3d_model(self, media_path):
        """Load a 3D model into the viewer (assumes viewer is initialized)."""
        from PySide2.QtCore import QThreadPool

        # Save camera state if "Keep Camera" is checked and viewer exists
        if (hasattr(self, 'keep_camera_checkbox') and
            self.keep_camera_checkbox.isChecked() and
            self.glb_viewer and
            hasattr(self.glb_viewer, 'get_camera_state')):
            self._saved_camera_state = self.glb_viewer.get_camera_state()
        else:
            self._saved_camera_state = None

        # Show loading message
        self.message_label.setText(f"Loading 3D model...\n{os.path.basename(media_path)}")
        self.image_stack.setCurrentWidget(self.message_label)

        # Use PyVista's direct import for best PBR support
        if self._use_pyvista_viewer:
            from glb_viewer_pyvista import PyVistaModelLoaderWorker
            loader = PyVistaModelLoaderWorker(media_path)
            loader.signals.finished.connect(self._on_model_loaded)
            loader.signals.error.connect(self._on_model_error)
            QThreadPool.globalInstance().start(loader)
        else:
            # Fallback to OpenGL loader
            from glb_viewer import ModelLoaderWorker
            loader = ModelLoaderWorker(media_path)
            loader.signals.finished.connect(self._on_model_loaded)
            loader.signals.error.connect(self._on_model_error)
            QThreadPool.globalInstance().start(loader)

    def _on_model_loaded(self, model_data):
        """Handle successful 3D model loading."""
        if self.glb_viewer:
            self.glb_viewer.set_model_data(model_data)

            # Restore camera state if saved
            if self._saved_camera_state and hasattr(self.glb_viewer, 'set_camera_state'):
                self.glb_viewer.set_camera_state(self._saved_camera_state)

            self.image_stack.setCurrentWidget(self.glb_viewer)
            self.glb_viewer.setFocus()  # Allow keyboard controls

    def _on_model_error(self, error_msg):
        """Handle 3D model loading error."""
        self.message_label.setText(f"Error Loading 3D Model\n\n{error_msg}")
        self.image_stack.setCurrentWidget(self.message_label)

    def _update_info(self):
        """Update info labels and button states."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        self.filename_label.setText(filename)
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.image_paths)}")

        # Update nav button states
        self.left_btn.setEnabled(self.current_index > 0)
        self.right_btn.setEnabled(self.current_index < len(self.image_paths) - 1)

    def _next_image(self):
        """Go to next image."""
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._load_current_image()

    def _prev_image(self):
        """Go to previous image."""
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()

    def _on_back(self):
        """Handle back button - close viewer."""
        self.closed.emit()

    def _on_fullscreen(self):
        """Handle fullscreen button."""
        if self.image_paths:
            self.view_fullscreen.emit(self.image_paths[self.current_index], self.current_index)

    def _on_zoom_changed(self, level):
        """Handle zoom dropdown selection."""
        self.image_view.setZoomLevel(level)

    def _on_image_zoom_changed(self, level):
        """Handle zoom change from image widget (e.g., mouse wheel)."""
        # Block signals to prevent feedback loop
        self.zoom_combo.blockSignals(True)
        # Check if level matches a preset, otherwise just show the percentage
        if level in ZoomableImageWidget.ZOOM_LEVELS:
            self.zoom_combo.setCurrentText(level)
        else:
            # For custom zoom levels, update the combo box text without changing selection
            # Find the index and temporarily add/update the displayed text
            self.zoom_combo.setEditText(level) if self.zoom_combo.isEditable() else None
        self.zoom_combo.blockSignals(False)

    def _toggle_3d_render_mode(self):
        """Toggle between textured and wireframe mode for 3D models."""
        if not self._current_3d_path:
            return

        # Toggle wireframe mode on the viewer directly
        if hasattr(self, '_has_glb_viewer') and self._has_glb_viewer and self.glb_viewer:
            self.glb_viewer.toggle_wireframe()
            self._3d_textured_mode = not self._3d_textured_mode

            # Button label shows what clicking will switch TO (opposite of current state)
            if self._3d_textured_mode:
                # Currently in textured mode, button will switch to wireframe
                self.texture_toggle_btn.setText("🔲 Wireframe")
            else:
                # Currently in wireframe mode, button will switch to textured
                self.texture_toggle_btn.setText("📷 Textured")
    
    def _show_textured_render(self, model_path):
        """Show a static textured render of the 3D model."""
        try:
            # Use the thumbnail service to generate a high-res textured render
            from glb_thumbnail_service import get_glb_thumbnail_service
            import trimesh
            from PIL import Image
            import numpy as np
            from PySide2.QtGui import QPixmap, QImage
            
            # Load the model with trimesh
            scene = trimesh.load(model_path)
            
            # Try to render with textures using trimesh's scene export
            # This creates a larger, higher quality render than thumbnails
            size = min(800, self.width() - 100, self.height() - 100)
            
            # Create a simple textured render
            # For now, show a message that textured mode uses the thumbnail
            service = get_glb_thumbnail_service()
            pixmap = service.get_cached_thumbnail(model_path)
            
            if pixmap and not pixmap.isNull():
                # Scale up the thumbnail for display
                scaled = pixmap.scaled(
                    size, size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.image_view.setPixmap(scaled)
                self.image_stack.setCurrentWidget(self.image_view)
            else:
                self.message_label.setText("Textured render not available\nGenerating thumbnail...")
                self.image_stack.setCurrentWidget(self.message_label)
        except Exception as e:
            print(f"Error showing textured render: {e}")
            self.message_label.setText(f"Error loading textured view:\n{e}")
            self.image_stack.setCurrentWidget(self.message_label)
    
    def _show_wireframe_view(self, model_path):
        """Show the interactive wireframe OpenGL view."""
        # Reload the model in the GLB viewer
        if hasattr(self, '_has_glb_viewer') and self._has_glb_viewer and self.glb_viewer:
            from glb_viewer import ModelLoaderWorker
            from PySide2.QtCore import QThreadPool
            
            self.message_label.setText(f"Loading 3D model...\n{os.path.basename(model_path)}")
            self.image_stack.setCurrentWidget(self.message_label)
            
            loader = ModelLoaderWorker(model_path)
            loader.signals.finished.connect(self._on_model_loaded)
            loader.signals.error.connect(self._on_model_error)
            QThreadPool.globalInstance().start(loader)

    def _copy_prompt(self):
        """Copy prompt for current image to clipboard."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui_service import get_image_metadata
            metadata = get_image_metadata(output_dir, filename)
            if metadata and metadata.get('prompt'):
                clipboard = QApplication.clipboard()
                clipboard.setText(metadata['prompt'])
                self.filename_label.setText(f"{filename} - Prompt copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No prompt available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            print(f"Error copying prompt: {e}")

    def keyPressEvent(self, event):
        """Handle keyboard navigation."""
        key = event.key()

        if key in (Qt.Key_Right, Qt.Key_D):
            self._next_image()
        elif key in (Qt.Key_Left, Qt.Key_A):
            self._prev_image()
        elif key in (Qt.Key_Escape, Qt.Key_Backspace):
            self._on_back()
        elif key == Qt.Key_Home:
            self.current_index = 0
            self._load_current_image()
        elif key == Qt.Key_End:
            self.current_index = len(self.image_paths) - 1
            self._load_current_image()
        elif key == Qt.Key_C:
            self._copy_prompt()
        elif key == Qt.Key_S:
            self._copy_settings()
        elif key == Qt.Key_F:
            self._on_fullscreen()
        else:
            super().keyPressEvent(event)

    def _show_context_menu(self, pos):
        """Show context menu for the current image."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        menu = QMenu(self)

        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(lambda: self._open_folder(image_path))

        menu.addSeparator()

        # Copy Settings action
        copy_settings_action = menu.addAction("Copy Settings (S)")
        copy_settings_action.triggered.connect(self._copy_settings)

        # Copy Prompt action
        copy_prompt_action = menu.addAction("Copy Prompt (C)")
        copy_prompt_action.triggered.connect(self._copy_prompt)

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path(image_path))

        menu.exec_(self.image_view.mapToGlobal(pos))

    def _copy_settings(self):
        """Copy all settings for current image to the ComfyUI tab."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui_service import get_image_metadata
            metadata = get_image_metadata(output_dir, filename)
            if metadata:
                self.copy_settings_requested.emit(metadata)
                self.filename_label.setText(f"{filename} - Settings copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No settings available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            print(f"Error copying settings: {e}")

    def _open_folder(self, image_path):
        """Open the containing folder in file explorer."""
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{image_path}"')
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _copy_path(self, image_path):
        """Copy the image path to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(image_path)
        self.filename_label.setText(f"{os.path.basename(image_path)} - Path copied!")
        QTimer.singleShot(1500, self._update_info)


class FullscreenImageViewer(QWidget):
    """
    Fullscreen image viewer (separate window) with keyboard navigation.

    Controls:
    - Left/Right arrows or A/D: Navigate between images
    - Escape or Q: Close viewer
    - Home/End: Jump to first/last image
    - Space: Toggle filename display
    - C: Copy prompt to clipboard (if available)
    - S: Copy settings to ComfyUI tab (if available)
    """
    closed = Signal()
    copy_settings_requested = Signal(dict)  # Emits metadata for copying settings to ComfyUI tab

    def __init__(self, image_paths, start_index=0, output_dir=None, parent=None):
        """
        Initialize the fullscreen viewer.

        Args:
            image_paths: List of image file paths
            start_index: Index of image to show first
            output_dir: Directory for metadata lookup
            parent: Parent widget
        """
        super().__init__(parent)
        self.image_paths = list(image_paths)  # Make a copy
        self.current_index = start_index
        self.output_dir = output_dir
        self._show_info = True

        self._setup_ui()
        self._load_current_image()

    def _setup_ui(self):
        """Set up the fullscreen UI."""
        # Set window flags for fullscreen
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet("background-color: #1a1a1a;")

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Image display
        self.image_stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.image_stack, stretch=1)

        # 1. Zoomable Image View
        self.image_view = ZoomableImageWidget()
        self.image_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_view.customContextMenuRequested.connect(self._show_context_menu)
        # Fullscreen double click handling - maybe close or just ignore?
        # Viewer says "Double-click to close" in mouse events later.
        # But image_view swallows double clicks unless we connect signal.
        self.image_view.double_clicked.connect(self.close)
        self.image_view.zoom_changed.connect(self._on_image_zoom_changed)
        self.image_stack.addWidget(self.image_view)

        # 2. Message Label
        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("background-color: #1a1a1a; color: #888888; font-size: 16px;")
        self.image_stack.addWidget(self.message_label)

        # Info bar at bottom
        self.info_bar = QWidget()
        self.info_bar.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 0.7);
                padding: 10px;
            }
        """)
        self.info_bar.setFixedHeight(60)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(20, 5, 20, 5)

        # Filename label
        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("color: #ffffff; font-size: 14px;")
        info_layout.addWidget(self.filename_label)

        info_layout.addStretch()

        # Counter label
        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("color: #888888; font-size: 12px;")
        info_layout.addWidget(self.counter_label)

        # Zoom dropdown
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(ZoomableImageWidget.ZOOM_LEVELS)
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.setFixedWidth(80)
        self.zoom_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: #cccccc;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QComboBox:hover {
                border-color: #4a9eff;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #888888;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #cccccc;
                selection-background-color: #4a9eff;
                border: 1px solid #555555;
            }
        """)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        info_layout.addWidget(self.zoom_combo)

        # Help hint
        self.help_label = QLabel("← → Navigate  |  Esc Close  |  Space Toggle Info  |  C Copy Prompt")
        self.help_label.setStyleSheet("color: #666666; font-size: 10px; margin-left: 20px;")
        info_layout.addWidget(self.help_label)

        layout.addWidget(self.info_bar)

        # Navigation buttons (semi-transparent, on sides)
        self._create_nav_buttons()

    def _create_nav_buttons(self):
        """Create navigation buttons on the sides."""
        # Left button
        self.left_btn = QPushButton("<", self)
        self.left_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.3);
                color: white;
                border: none;
                font-size: 30px;
                padding: 20px;
            }
            QPushButton:hover {
                background-color: rgba(74, 158, 255, 0.5);
            }
        """)
        self.left_btn.setCursor(Qt.PointingHandCursor)
        self.left_btn.clicked.connect(self._prev_image)

        # Right button
        self.right_btn = QPushButton(">", self)
        self.right_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.3);
                color: white;
                border: none;
                font-size: 30px;
                padding: 20px;
            }
            QPushButton:hover {
                background-color: rgba(74, 158, 255, 0.5);
            }
        """)
        self.right_btn.setCursor(Qt.PointingHandCursor)
        self.right_btn.clicked.connect(self._next_image)

    def showEvent(self, event):
        """Handle show event - go fullscreen."""
        super().showEvent(event)
        self.showFullScreen()
        self._position_nav_buttons()

    def resizeEvent(self, event):
        """Handle resize to reposition nav buttons."""
        super().resizeEvent(event)
        self._position_nav_buttons()

    def _position_nav_buttons(self):
        """Position navigation buttons on sides."""
        btn_width = 60
        btn_height = 100
        margin = 20
        center_y = (self.height() - self.info_bar.height() - btn_height) // 2

        self.left_btn.setGeometry(margin, center_y, btn_width, btn_height)
        self.right_btn.setGeometry(self.width() - margin - btn_width, center_y, btn_width, btn_height)

        # Update button visibility based on index
        self.left_btn.setVisible(self.current_index > 0)
        self.right_btn.setVisible(self.current_index < len(self.image_paths) - 1)

    def _load_current_image(self):
        """Load and display the current image."""
        if not self.image_paths or self.current_index < 0 or self.current_index >= len(self.image_paths):
            return

        image_path = self.image_paths[self.current_index]

        try:
            ext = os.path.splitext(image_path)[1].lower()

            if ext == '.exr':
                self.message_label.setText("EXR Preview Not Available")
                self.image_stack.setCurrentWidget(self.message_label)
            else:
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    self.image_view.setPixmap(pixmap)
                    self.image_stack.setCurrentWidget(self.image_view)
                else:
                    self.message_label.setText("Failed to load image")
                    self.image_stack.setCurrentWidget(self.message_label)

        except Exception as e:
            self.message_label.setText(f"Error: {e}")
            self.image_stack.setCurrentWidget(self.message_label)

        # Update info
        self._update_info()
        self._position_nav_buttons()

    def _update_info(self):
        """Update the info bar."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        self.filename_label.setText(filename)
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.image_paths)}")

        # Show/hide info bar
        self.info_bar.setVisible(self._show_info)

    def _next_image(self):
        """Go to next image."""
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._load_current_image()

    def _prev_image(self):
        """Go to previous image."""
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()

    def _on_zoom_changed(self, level):
        """Handle zoom dropdown selection."""
        self.image_view.setZoomLevel(level)

    def _on_image_zoom_changed(self, level):
        """Handle zoom change from image widget (e.g., mouse wheel)."""
        # Block signals to prevent feedback loop
        self.zoom_combo.blockSignals(True)
        # Check if level matches a preset, otherwise just show the percentage
        if level in ZoomableImageWidget.ZOOM_LEVELS:
            self.zoom_combo.setCurrentText(level)
        self.zoom_combo.blockSignals(False)

    def _copy_prompt(self):
        """Copy prompt for current image to clipboard."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui_service import get_image_metadata
            metadata = get_image_metadata(output_dir, filename)
            if metadata and metadata.get('prompt'):
                clipboard = QApplication.clipboard()
                clipboard.setText(metadata['prompt'])
                # Brief visual feedback
                self.filename_label.setText(f"{filename} - Prompt copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No prompt available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            print(f"Error copying prompt: {e}")

    def keyPressEvent(self, event):
        """Handle keyboard navigation."""
        key = event.key()

        if key in (Qt.Key_Right, Qt.Key_D):
            self._next_image()
        elif key in (Qt.Key_Left, Qt.Key_A):
            self._prev_image()
        elif key in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
        elif key == Qt.Key_Home:
            self.current_index = 0
            self._load_current_image()
        elif key == Qt.Key_End:
            self.current_index = len(self.image_paths) - 1
            self._load_current_image()
        elif key == Qt.Key_Space:
            self._show_info = not self._show_info
            self._update_info()
        elif key == Qt.Key_C:
            self._copy_prompt()
        elif key == Qt.Key_S:
            self._copy_settings()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse clicks - click on image area to close."""
        # Only close if clicking on the dark background, not on buttons
        if event.button() == Qt.LeftButton:
            # Check if click is in the middle area (not on nav buttons)
            click_x = event.pos().x()
            margin = 100
            if margin < click_x < self.width() - margin:
                # Double-click to close
                pass
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click to close."""
        if event.button() == Qt.LeftButton:
            self.close()

    def closeEvent(self, event):
        """Handle close event."""
        self.closed.emit()
        super().closeEvent(event)

    def _show_context_menu(self, pos):
        """Show context menu for the current image."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        menu = QMenu(self)

        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(lambda: self._open_folder(image_path))

        menu.addSeparator()

        # Copy Settings action
        copy_settings_action = menu.addAction("Copy Settings (S)")
        copy_settings_action.triggered.connect(self._copy_settings)

        # Copy Prompt action
        copy_prompt_action = menu.addAction("Copy Prompt (C)")
        copy_prompt_action.triggered.connect(self._copy_prompt)

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path(image_path))

        menu.exec_(self.image_view.mapToGlobal(pos))

    def _copy_settings(self):
        """Copy all settings for current image to the ComfyUI tab."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui_service import get_image_metadata
            metadata = get_image_metadata(output_dir, filename)
            if metadata:
                self.copy_settings_requested.emit(metadata)
                self.filename_label.setText(f"{filename} - Settings copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No settings available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            print(f"Error copying settings: {e}")

    def _open_folder(self, image_path):
        """Open the containing folder in file explorer."""
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{image_path}"')
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _copy_path(self, image_path):
        """Copy the image path to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(image_path)
        self.filename_label.setText(f"{os.path.basename(image_path)} - Path copied!")
        QTimer.singleShot(1500, self._update_info)


class GalleryThumbnailWidget(QWidget):
    """
    A thumbnail widget for the gallery that displays an image preview with filename.
    Supports click to open, right-click context menu with "Copy Prompt" and "Copy Settings" options.
    Loads thumbnails asynchronously to avoid blocking the UI.
    """
    clicked = Signal(str)  # Emits the image path when clicked
    fullscreen_requested = Signal(str)  # Emits the image path for fullscreen view
    copy_settings_requested = Signal(dict)  # Emits metadata for copying settings to ComfyUI tab
    deleted = Signal(str)  # Emits the image path when deleted
    viewed = Signal(str)  # Emits when item has been viewed (no longer new)
    THUMBNAIL_SIZE = (150, 150)

    def __init__(self, image_path, parent=None, output_dir=None, editable=True, is_new=False):
        super().__init__(parent)
        self.image_path = image_path
        self.output_dir = output_dir or os.path.dirname(image_path)
        self._editable = editable  # Can this item be edited/deleted
        self._is_new = is_new  # New item that hasn't been viewed yet
        self._cached_metadata = None
        self._setup_ui()
        self._load_thumbnail_async()
        self._update_tooltip()

    def _setup_ui(self):
        """Set up the widget UI."""
        self.setFixedSize(self.THUMBNAIL_SIZE[0] + 10, self.THUMBNAIL_SIZE[1] + 30)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # Thumbnail label - start with loading placeholder
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(*self.THUMBNAIL_SIZE)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self._apply_thumbnail_style()
        self.thumbnail_label.setPixmap(self._create_placeholder("..."))
        layout.addWidget(self.thumbnail_label)

        # Filename label
        self.filename_label = QLabel(os.path.basename(self.image_path))
        self.filename_label.setAlignment(Qt.AlignCenter)
        self.filename_label.setStyleSheet("color: #aaaaaa; font-size: 10px;")
        self.filename_label.setWordWrap(True)
        self.filename_label.setMaximumWidth(self.THUMBNAIL_SIZE[0])
        layout.addWidget(self.filename_label)

        # Note indicator (small icon overlay on thumbnail)
        self.note_indicator = QLabel(self.thumbnail_label)
        self.note_indicator.setText("N")
        self.note_indicator.setAlignment(Qt.AlignCenter)
        self.note_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(74, 158, 255, 0.9);
                color: white;
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        self.note_indicator.setFixedSize(18, 18)
        self.note_indicator.move(self.THUMBNAIL_SIZE[0] - 22, 4)
        self.note_indicator.hide()

        # Context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_thumbnail_style(self):
        """Apply the appropriate style to the thumbnail based on new status."""
        if self._is_new:
            # Green glow effect for new items
            self.thumbnail_label.setStyleSheet("""
                QLabel {
                    background-color: #2c313a;
                    border: 2px solid #10b981;
                    border-radius: 4px;
                }
            """)
        else:
            # Normal style
            self.thumbnail_label.setStyleSheet("""
                QLabel {
                    background-color: #2c313a;
                    border: 1px solid #3c414b;
                    border-radius: 4px;
                }
            """)

    def mark_as_viewed(self):
        """Mark this item as viewed, removing the new highlight."""
        if self._is_new:
            self._is_new = False
            self._apply_thumbnail_style()
            self.viewed.emit(self.image_path)

    def _load_thumbnail_async(self):
        """Load the thumbnail image asynchronously."""
        ext = os.path.splitext(self.image_path)[1].lower()

        if ext == '.exr':
            # For EXR, show a placeholder immediately (no async needed)
            self.thumbnail_label.setPixmap(self._create_placeholder("EXR"))
            return

        # Load image on worker thread
        worker = Worker(self._load_image_data, self.image_path)
        worker.signals.result.connect(self._on_thumbnail_loaded)
        worker.signals.error.connect(lambda msg, tb: self._on_thumbnail_error())
        QThreadPool.globalInstance().start(worker)

    @staticmethod
    def _load_image_data(image_path):
        """Load and scale image data on worker thread. Returns bytes for QPixmap."""
        from PySide2.QtGui import QImage
        from PySide2.QtCore import QBuffer, QIODevice

        image = QImage(image_path)
        if image.isNull():
            return None

        # Scale the image
        scaled = image.scaled(
            GalleryThumbnailWidget.THUMBNAIL_SIZE[0],
            GalleryThumbnailWidget.THUMBNAIL_SIZE[1],
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # Convert to bytes for thread-safe transfer
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        scaled.save(buffer, "PNG")
        return buffer.data().data()

    def _on_thumbnail_loaded(self, image_data):
        """Handle thumbnail loaded from worker thread."""
        if image_data is None:
            self.thumbnail_label.setPixmap(self._create_placeholder("?"))
            return

        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        if not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap)
        else:
            self.thumbnail_label.setPixmap(self._create_placeholder("?"))

    def _on_thumbnail_error(self):
        """Handle thumbnail loading error."""
        self.thumbnail_label.setPixmap(self._create_placeholder("!"))

    def _create_placeholder(self, text):
        """Create a placeholder pixmap with text."""
        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#3c414b"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#888888"))
        font = painter.font()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()

        return pixmap

    def mousePressEvent(self, event):
        """Handle mouse press to emit clicked signal."""
        if event.button() == Qt.LeftButton:
            self.mark_as_viewed()
            self.clicked.emit(self.image_path)
        super().mousePressEvent(event)

    def _get_metadata(self):
        """Get metadata for this image (cached)."""
        if self._cached_metadata is None:
            try:
                from comfyui_service import get_image_metadata
                filename = os.path.basename(self.image_path)
                self._cached_metadata = get_image_metadata(self.output_dir, filename) or {}
            except Exception as e:
                print(f"Error loading metadata for {self.image_path}: {e}")
                self._cached_metadata = {}
        return self._cached_metadata

    def _show_context_menu(self, pos):
        """Show context menu for the thumbnail."""
        menu = QMenu(self)

        open_action = menu.addAction("Open in Viewer")
        open_action.triggered.connect(lambda: self._open_image())

        fullscreen_action = menu.addAction("View Fullscreen")
        fullscreen_action.triggered.connect(lambda: self.fullscreen_requested.emit(self.image_path))

        edit_action = menu.addAction("Edit Item")
        edit_action.triggered.connect(self._edit_item)
        # Disable edit when not editable (viewing another user's gallery)
        if not self._editable:
            edit_action.setEnabled(False)
            edit_action.setText("Edit Item (view only)")

        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(lambda: self._open_folder())

        menu.addSeparator()

        # Copy Settings action (copy all ComfyUI settings from this image)
        metadata = self._get_metadata()
        has_settings = bool(metadata.get('workflow_preset') or metadata.get('editable_values'))
        copy_settings_action = menu.addAction("Copy Settings")
        copy_settings_action.triggered.connect(lambda: self._copy_settings())
        copy_settings_action.setEnabled(has_settings)
        if not has_settings:
            copy_settings_action.setText("Copy Settings (none)")

        # Copy Prompt action (only enabled if metadata has prompt)
        prompt = metadata.get('prompt', '')
        copy_prompt_action = menu.addAction("Copy Prompt")
        copy_prompt_action.triggered.connect(lambda: self._copy_prompt())
        copy_prompt_action.setEnabled(bool(prompt))
        if not prompt:
            copy_prompt_action.setText("Copy Prompt (none)")

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path())

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(self._delete_item)
        # Disable delete when not editable (viewing another user's gallery)
        if not self._editable:
            delete_action.setEnabled(False)
            delete_action.setText("Delete (view only)")

        menu.exec_(self.mapToGlobal(pos))

    def _copy_settings(self):
        """Copy all ComfyUI settings from this image to the ComfyUI tab."""
        metadata = self._get_metadata()
        if metadata:
            self.copy_settings_requested.emit(metadata)
            print(f"Copying settings from image: {os.path.basename(self.image_path)}")

    def _copy_prompt(self):
        """Copy the prompt used to generate this image to clipboard."""
        metadata = self._get_metadata()
        prompt = metadata.get('prompt', '')
        if prompt:
            clipboard = QApplication.clipboard()
            clipboard.setText(prompt)
            print(f"Copied prompt to clipboard: {prompt[:50]}...")

    def _open_image(self):
        """Open the image with the default viewer."""
        import subprocess
        try:
            os.startfile(self.image_path)
        except Exception as e:
            print(f"Error opening image: {e}")

    def _open_folder(self):
        """Open the containing folder in file explorer."""
        import subprocess
        folder = os.path.dirname(self.image_path)
        try:
            subprocess.Popen(f'explorer /select,"{self.image_path}"')
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _copy_path(self):
        """Copy the image path to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.image_path)

    def _delete_item(self):
        """Delete this item from disk after confirmation."""
        from PySide2.QtWidgets import QMessageBox

        filename = os.path.basename(self.image_path)

        # Find the main window safely for dialog parent
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break

        reply = QMessageBox.question(
            parent_window,
            "Delete Item",
            f"Are you sure you want to delete '{filename}'?\n\nThis will permanently delete the file from disk.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                os.remove(self.image_path)
                print(f"Deleted file: {self.image_path}")
                # Emit signal so gallery can refresh
                self.deleted.emit(self.image_path)
                # Remove this widget from its parent layout
                self.setParent(None)
                self.deleteLater()
            except Exception as e:
                print(f"Error deleting file: {e}")
                QMessageBox.critical(
                    parent_window,
                    "Delete Error",
                    f"Could not delete file:\n{e}"
                )

    def _edit_item(self):
        """Open the edit item dialog to add/edit notes."""
        try:
            # Find the main window safely
            parent_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'windowTitle'):
                    parent_window = widget
                    break

            dialog = EditItemDialog(self.image_path, self.output_dir, parent_window)
            if dialog.exec_() == QDialog.Accepted:
                # Update tooltip to show note
                self._update_tooltip()
        except Exception as e:
            print(f"Error opening edit item dialog: {e}")
            import traceback
            traceback.print_exc()

    def _update_tooltip(self):
        """Update the widget tooltip with item info including note."""
        try:
            from comfyui_service import get_model_note
            filename = os.path.basename(self.image_path)
            note = get_model_note(self.output_dir, filename)

            # Build tooltip
            tooltip_parts = [filename]
            if note:
                tooltip_parts.append(f"\nNote: {note}")
                self.note_indicator.show()
            else:
                self.note_indicator.hide()

            self.setToolTip("\n".join(tooltip_parts))
        except Exception as e:
            print(f"Error updating tooltip: {e}")
            self.note_indicator.hide()


class EditItemDialog(QDialog):
    """
    Dialog for editing gallery item notes (images).

    Allows users to add or edit notes/descriptions for images.
    """

    def __init__(self, item_path: str, output_dir: str, parent=None):
        super().__init__(parent)
        self.item_path = item_path
        self.output_dir = output_dir
        self._setup_ui()
        self._load_note()

    def _setup_ui(self):
        """Set up the dialog UI."""
        filename = os.path.basename(self.item_path)
        self.setWindowTitle(f"Edit Item - {filename}")
        self.setMinimumSize(400, 300)
        self.resize(450, 350)
        self.setModal(True)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e22;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            QPlainTextEdit {
                background-color: #2c313a;
                color: #e0e0e0;
                border: 1px solid #3c414b;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
            QPlainTextEdit:focus {
                border-color: #4a9eff;
            }
            QPushButton {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4a5160;
            }
            QPushButton:pressed {
                background-color: #2a2e36;
            }
            QPushButton[primary="true"] {
                background-color: #4a9eff;
                color: white;
            }
            QPushButton[primary="true"]:hover {
                background-color: #6ab0ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Item name
        name_label = QLabel(f"Item: {os.path.basename(self.item_path)}")
        name_label.setStyleSheet("font-weight: bold; color: #4a9eff;")
        layout.addWidget(name_label)

        # Note label
        note_label = QLabel("Note:")
        layout.addWidget(note_label)

        # Note text edit
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("Add a note or description for this item...")
        layout.addWidget(self.note_edit)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(self._save_note)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

    def _load_note(self):
        """Load existing note for this item."""
        try:
            from comfyui_service import get_model_note
            filename = os.path.basename(self.item_path)
            note = get_model_note(self.output_dir, filename)
            self.note_edit.setPlainText(note)
        except Exception as e:
            print(f"Error loading item note: {e}")

    def _save_note(self):
        """Save the note and close the dialog."""
        try:
            from comfyui_service import set_model_note
            filename = os.path.basename(self.item_path)
            note = self.note_edit.toPlainText()
            if set_model_note(self.output_dir, filename, note):
                print(f"Saved note for {filename}")
                self.accept()
            else:
                print(f"Failed to save note for {filename}")
                self.reject()
        except Exception as e:
            print(f"Error saving item note: {e}")
            self.reject()

    def get_note(self) -> str:
        """Get the current note text."""
        return self.note_edit.toPlainText()


class EditModelDialog(QDialog):
    """
    Dialog for editing model notes.

    Allows users to add or edit notes/descriptions for 3D models.
    """

    def __init__(self, model_path: str, output_dir: str, parent=None):
        super().__init__(parent)
        self.model_path = model_path
        self.output_dir = output_dir
        self._setup_ui()
        self._load_note()

    def _setup_ui(self):
        """Set up the dialog UI."""
        filename = os.path.basename(self.model_path)
        self.setWindowTitle(f"Edit Model - {filename}")
        self.setMinimumSize(400, 300)
        self.resize(450, 350)
        self.setModal(True)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e22;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            QPlainTextEdit {
                background-color: #2c313a;
                color: #e0e0e0;
                border: 1px solid #3c414b;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
            QPlainTextEdit:focus {
                border-color: #4a9eff;
            }
            QPushButton {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4a5160;
            }
            QPushButton:pressed {
                background-color: #2a2e36;
            }
            QPushButton[primary="true"] {
                background-color: #4a9eff;
                color: white;
            }
            QPushButton[primary="true"]:hover {
                background-color: #6ab0ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Model name
        name_label = QLabel(f"Model: {os.path.basename(self.model_path)}")
        name_label.setStyleSheet("font-weight: bold; color: #4a9eff;")
        layout.addWidget(name_label)

        # Note label
        note_label = QLabel("Note:")
        layout.addWidget(note_label)

        # Note text edit
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("Add a note or description for this model...")
        layout.addWidget(self.note_edit)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(self._save_note)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

    def _load_note(self):
        """Load existing note for this model."""
        try:
            from comfyui_service import get_model_note
            filename = os.path.basename(self.model_path)
            note = get_model_note(self.output_dir, filename)
            self.note_edit.setPlainText(note)
        except Exception as e:
            print(f"Error loading model note: {e}")

    def _save_note(self):
        """Save the note and close the dialog."""
        try:
            from comfyui_service import set_model_note
            filename = os.path.basename(self.model_path)
            note = self.note_edit.toPlainText()
            if set_model_note(self.output_dir, filename, note):
                print(f"Saved note for {filename}")
                self.accept()
            else:
                print(f"Failed to save note for {filename}")
                self.reject()
        except Exception as e:
            print(f"Error saving model note: {e}")
            self.reject()

    def get_note(self) -> str:
        """Get the current note text."""
        return self.note_edit.toPlainText()


class GLBThumbnailWidget(QWidget):
    """
    A thumbnail widget for GLB/GLTF 3D models in the gallery.
    Displays a rendered preview with filename. Click to open 3D viewer.
    """
    clicked = Signal(str)  # Emits the model path when clicked
    deleted = Signal(str)  # Emits the model path when deleted
    viewed = Signal(str)  # Emits when item has been viewed (no longer new)
    THUMBNAIL_SIZE = (150, 150)

    def __init__(self, model_path, parent=None, output_dir=None, editable=True, is_new=False):
        super().__init__(parent)
        self.model_path = model_path
        self.output_dir = output_dir or os.path.dirname(model_path)
        self._editable = editable  # Can this item be edited/deleted
        self._is_new = is_new  # New item that hasn't been viewed yet
        self._thumbnail_loading = False
        self._cached_metadata = None
        self._setup_ui()
        self._load_thumbnail()
        self._update_tooltip()

    def _setup_ui(self):
        """Set up the widget UI."""
        self.setFixedSize(self.THUMBNAIL_SIZE[0] + 10, self.THUMBNAIL_SIZE[1] + 30)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # Thumbnail label
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(*self.THUMBNAIL_SIZE)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self._apply_thumbnail_style()
        layout.addWidget(self.thumbnail_label)

        # Filename label
        self.filename_label = QLabel(os.path.basename(self.model_path))
        self.filename_label.setAlignment(Qt.AlignCenter)
        self._apply_filename_style()
        self.filename_label.setWordWrap(True)
        self.filename_label.setMaximumWidth(self.THUMBNAIL_SIZE[0])
        layout.addWidget(self.filename_label)

        # Note indicator (small icon overlay on thumbnail)
        self.note_indicator = QLabel(self.thumbnail_label)
        self.note_indicator.setText("N")
        self.note_indicator.setAlignment(Qt.AlignCenter)
        self.note_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(74, 158, 255, 0.9);
                color: white;
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        self.note_indicator.setFixedSize(18, 18)
        self.note_indicator.move(self.THUMBNAIL_SIZE[0] - 22, 4)
        self.note_indicator.hide()

        # Context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_thumbnail_style(self):
        """Apply the appropriate style to the thumbnail based on new status."""
        if self._is_new:
            # Green glow effect for new items (distinct from normal blue)
            self.thumbnail_label.setStyleSheet("""
                QLabel {
                    background-color: #2c313a;
                    border: 2px solid #10b981;
                    border-radius: 4px;
                }
            """)
        else:
            # Normal blue border for 3D models
            self.thumbnail_label.setStyleSheet("""
                QLabel {
                    background-color: #2c313a;
                    border: 2px solid #4a9eff;
                    border-radius: 4px;
                }
            """)

    def _apply_filename_style(self):
        """Apply the appropriate style to the filename based on new status."""
        if self._is_new:
            self.filename_label.setStyleSheet("color: #10b981; font-size: 10px; font-weight: bold;")
        else:
            self.filename_label.setStyleSheet("color: #4a9eff; font-size: 10px;")

    def mark_as_viewed(self):
        """Mark this item as viewed, removing the new highlight."""
        if self._is_new:
            self._is_new = False
            self._apply_thumbnail_style()
            self._apply_filename_style()
            self.viewed.emit(self.model_path)

    def _load_thumbnail(self):
        """Load or generate the thumbnail asynchronously."""
        # First, try to load from cache (instant)
        try:
            from glb_thumbnail_service import get_glb_thumbnail_service
            service = get_glb_thumbnail_service()
            cached = service.get_cached_thumbnail(self.model_path)
            if cached and not cached.isNull():
                self.thumbnail_label.setPixmap(cached.scaled(
                    *self.THUMBNAIL_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                ))
                return
        except Exception as e:
            print(f"Error loading cached GLB thumbnail: {e}")

        # Show placeholder and start async generation
        self.thumbnail_label.setPixmap(self._create_placeholder("3D"))
        self._generate_thumbnail_async()

    def _generate_thumbnail_async(self):
        """Generate thumbnail on a worker thread using subprocess."""
        if self._thumbnail_loading:
            return

        # Check if already pending in service
        try:
            from glb_thumbnail_service import get_glb_thumbnail_service
            service = get_glb_thumbnail_service()
            if service.is_pending(self.model_path):
                return
            service.set_pending(self.model_path, True)
        except Exception:
            pass

        self._thumbnail_loading = True

        from PySide2.QtCore import QThreadPool

        try:
            worker = Worker(self._generate_thumbnail_sync)
            worker.signals.result.connect(self._on_thumbnail_generated)
            worker.signals.error.connect(self._on_thumbnail_error)
            QThreadPool.globalInstance().start(worker)
        except Exception as e:
            print(f"Error starting thumbnail worker: {e}")
            self._thumbnail_loading = False
            try:
                service.set_pending(self.model_path, False)
            except Exception:
                pass

    def _generate_thumbnail_sync(self):
        """Generate thumbnail synchronously (runs on worker thread via subprocess)."""
        from glb_thumbnail_service import get_glb_thumbnail_service
        service = get_glb_thumbnail_service()
        # This uses subprocess to render, avoiding OpenGL conflicts with Qt
        return service.generate_thumbnail_sync(self.model_path)

    def _on_thumbnail_generated(self, pixmap):
        """Handle generated thumbnail."""
        self._thumbnail_loading = False
        # Clear pending state
        try:
            from glb_thumbnail_service import get_glb_thumbnail_service
            service = get_glb_thumbnail_service()
            service.set_pending(self.model_path, False)
        except Exception:
            pass

        if pixmap and not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap.scaled(
                *self.THUMBNAIL_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))

    def _on_thumbnail_error(self, error_msg, traceback_str):
        """Handle thumbnail generation error."""
        self._thumbnail_loading = False
        # Clear pending state
        try:
            from glb_thumbnail_service import get_glb_thumbnail_service
            service = get_glb_thumbnail_service()
            service.set_pending(self.model_path, False)
        except Exception:
            pass
        print(f"GLB thumbnail error: {error_msg}")

    def _create_placeholder(self, text):
        """Create a placeholder pixmap with text and 3D icon."""
        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#2a3040"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw a simple 3D cube icon
        painter.setPen(QPen(QColor("#4a9eff"), 2))
        center_x, center_y = 75, 65
        size = 30

        # Front face
        painter.drawRect(center_x - size//2, center_y - size//2, size, size)

        # Top face (parallelogram)
        offset = 12
        painter.drawLine(center_x - size//2, center_y - size//2,
                        center_x - size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x + size//2, center_y - size//2,
                        center_x + size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x - size//2 + offset, center_y - size//2 - offset,
                        center_x + size//2 + offset, center_y - size//2 - offset)

        # Right face (parallelogram)
        painter.drawLine(center_x + size//2, center_y + size//2,
                        center_x + size//2 + offset, center_y + size//2 - offset)
        painter.drawLine(center_x + size//2 + offset, center_y - size//2 - offset,
                        center_x + size//2 + offset, center_y + size//2 - offset)

        # Draw text
        painter.setPen(QColor("#888888"))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, 100, self.THUMBNAIL_SIZE[0], 30, Qt.AlignCenter, text)
        painter.end()

        return pixmap

    def mousePressEvent(self, event):
        """Handle mouse press to open 3D viewer."""
        if event.button() == Qt.LeftButton:
            self.mark_as_viewed()
            self.clicked.emit(self.model_path)
        super().mousePressEvent(event)

    def _get_metadata(self):
        """Get metadata for this model (cached)."""
        if self._cached_metadata is None:
            try:
                from comfyui_service import get_image_metadata
                filename = os.path.basename(self.model_path)
                self._cached_metadata = get_image_metadata(self.output_dir, filename) or {}
            except Exception as e:
                print(f"Error loading metadata for {self.model_path}: {e}")
                self._cached_metadata = {}
        return self._cached_metadata

    def _show_context_menu(self, pos):
        """Show context menu for the thumbnail."""
        menu = QMenu(self)

        open_action = menu.addAction("Open 3D Viewer")
        open_action.triggered.connect(self._open_viewer)

        edit_action = menu.addAction("Edit Model")
        edit_action.triggered.connect(self._edit_model)
        # Disable edit when not editable (viewing another user's gallery)
        if not self._editable:
            edit_action.setEnabled(False)
            edit_action.setText("Edit Model (view only)")

        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(self._open_folder)

        menu.addSeparator()

        # Copy Prompt action (only enabled if metadata has prompt)
        metadata = self._get_metadata()
        prompt = metadata.get('prompt', '')
        copy_prompt_action = menu.addAction("Copy Prompt")
        copy_prompt_action.triggered.connect(self._copy_prompt)
        copy_prompt_action.setEnabled(bool(prompt))
        if not prompt:
            copy_prompt_action.setText("Copy Prompt (none)")

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(self._copy_path)

        regen_action = menu.addAction("Regenerate Thumbnail")
        regen_action.triggered.connect(self._regenerate_thumbnail)

        menu.addSeparator()

        # Export submenu
        export_menu = menu.addMenu("Export As...")
        export_abc_action = export_menu.addAction("Alembic (.abc)")
        export_abc_action.triggered.connect(lambda: self._export_model("abc"))
        export_obj_action = export_menu.addAction("Wavefront OBJ (.obj)")
        export_obj_action.triggered.connect(lambda: self._export_model("obj"))
        export_usd_action = export_menu.addAction("USD (.usd)")
        export_usd_action.triggered.connect(lambda: self._export_model("usd"))
        export_fbx_action = export_menu.addAction("FBX (.fbx)")
        export_fbx_action.triggered.connect(lambda: self._export_model("fbx"))

        # Extract textures action
        extract_textures_action = menu.addAction("Extract Textures...")
        extract_textures_action.triggered.connect(self._extract_textures)

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(self._delete_model)
        # Disable delete when not editable (viewing another user's gallery)
        if not self._editable:
            delete_action.setEnabled(False)
            delete_action.setText("Delete (view only)")

        menu.exec_(self.mapToGlobal(pos))

    def _copy_prompt(self):
        """Copy the prompt used to generate this model to clipboard."""
        metadata = self._get_metadata()
        prompt = metadata.get('prompt', '')
        if prompt:
            clipboard = QApplication.clipboard()
            clipboard.setText(prompt)
            print(f"Copied prompt to clipboard: {prompt[:50]}...")

    def _delete_model(self):
        """Delete this model from disk after confirmation."""
        from PySide2.QtWidgets import QMessageBox

        filename = os.path.basename(self.model_path)

        # Find the main window safely for dialog parent
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break

        reply = QMessageBox.question(
            parent_window,
            "Delete Model",
            f"Are you sure you want to delete '{filename}'?\n\nThis will permanently delete the file from disk.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                os.remove(self.model_path)
                print(f"Deleted file: {self.model_path}")
                # Emit signal so gallery can refresh
                self.deleted.emit(self.model_path)
                # Remove this widget from its parent layout
                self.setParent(None)
                self.deleteLater()
            except Exception as e:
                print(f"Error deleting file: {e}")
                QMessageBox.critical(
                    parent_window,
                    "Delete Error",
                    f"Could not delete file:\n{e}"
                )

    def _edit_model(self):
        """Open the edit model dialog to add/edit notes."""
        try:
            # Find the main window safely
            parent_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'windowTitle'):
                    parent_window = widget
                    break

            dialog = EditModelDialog(self.model_path, self.output_dir, parent_window)
            if dialog.exec_() == QDialog.Accepted:
                # Update tooltip to show note
                self._update_tooltip()
        except Exception as e:
            print(f"Error opening edit model dialog: {e}")
            import traceback
            traceback.print_exc()

    def _update_tooltip(self):
        """Update the widget tooltip with model info including note."""
        try:
            from comfyui_service import get_model_note
            filename = os.path.basename(self.model_path)
            note = get_model_note(self.output_dir, filename)

            # Build tooltip
            tooltip_parts = [filename]
            if note:
                tooltip_parts.append(f"\nNote: {note}")
                self.note_indicator.show()
            else:
                self.note_indicator.hide()

            self.setToolTip("\n".join(tooltip_parts))
        except Exception as e:
            print(f"Error updating tooltip: {e}")
            self.note_indicator.hide()

    def _open_viewer(self):
        """Open the 3D model viewer dialog."""
        from PySide2.QtWidgets import QApplication

        # Find the main window safely
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break

        # Try PyVista viewer first (better PBR support)
        try:
            from glb_viewer_pyvista import PyVistaGLBViewerDialog, is_pyvista_available
            if is_pyvista_available():
                dialog = PyVistaGLBViewerDialog(self.model_path, parent_window)
                dialog.show()
                return
        except ImportError as e:
            print(f"PyVista GLB viewer not available: {e}")

        # Fallback to OpenGL viewer
        try:
            from glb_viewer import GLBViewerDialog
            dialog = GLBViewerDialog(self.model_path, parent_window)
            dialog.exec_()
        except ImportError as e:
            print(f"GLB viewer not available: {e}")
        except Exception as e:
            print(f"Error opening 3D viewer: {e}")
            import traceback
            traceback.print_exc()

    def _open_folder(self):
        """Open the containing folder in file explorer."""
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{self.model_path}"')
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _copy_path(self):
        """Copy the model path to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.model_path)

    def _regenerate_thumbnail(self):
        """Clear cache and regenerate thumbnail."""
        try:
            from glb_thumbnail_service import get_glb_thumbnail_service
            service = get_glb_thumbnail_service()
            service.clear_cache(self.model_path)
            self.thumbnail_label.setPixmap(self._create_placeholder("3D"))
            self._generate_thumbnail_async()
        except Exception as e:
            print(f"Error regenerating thumbnail: {e}")

    def _export_model(self, format_type):
        """Export the model to a different format.

        Args:
            format_type: Target format - 'abc', 'obj', 'usd', or 'fbx'
        """
        from PySide2.QtWidgets import QFileDialog, QMessageBox

        # Format configuration
        format_config = {
            'abc': {'ext': '.abc', 'name': 'Alembic', 'filter': 'Alembic Files (*.abc)'},
            'obj': {'ext': '.obj', 'name': 'Wavefront OBJ', 'filter': 'OBJ Files (*.obj)'},
            'usd': {'ext': '.usd', 'name': 'USD', 'filter': 'USD Files (*.usd *.usda *.usdc)'},
            'fbx': {'ext': '.fbx', 'name': 'FBX', 'filter': 'FBX Files (*.fbx)'},
        }

        if format_type not in format_config:
            print(f"Unsupported export format: {format_type}")
            return

        config = format_config[format_type]

        # Find the main window for dialogs
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break

        # Generate default output filename
        base_name = os.path.splitext(os.path.basename(self.model_path))[0]
        default_dir = os.path.dirname(self.model_path)
        default_path = os.path.join(default_dir, base_name + config['ext'])

        # Ask user for save location
        output_path, _ = QFileDialog.getSaveFileName(
            parent_window,
            f"Export as {config['name']}",
            default_path,
            config['filter']
        )

        if not output_path:
            return  # User cancelled

        # Ensure correct extension
        if not output_path.lower().endswith(config['ext']):
            output_path += config['ext']

        try:
            import trimesh

            # Load the model
            scene_or_mesh = trimesh.load(self.model_path)

            # Export based on format
            if format_type == 'obj':
                # OBJ export - trimesh handles this directly
                if isinstance(scene_or_mesh, trimesh.Scene):
                    # Combine all meshes for OBJ export
                    combined = scene_or_mesh.dump(concatenate=True)
                    if combined:
                        combined.export(output_path, file_type='obj')
                    else:
                        scene_or_mesh.export(output_path, file_type='obj')
                else:
                    scene_or_mesh.export(output_path, file_type='obj')

            elif format_type == 'abc':
                # Alembic export
                self._export_to_alembic(scene_or_mesh, output_path)

            elif format_type == 'usd':
                # USD export using pxr (OpenUSD)
                self._export_to_usd_format(scene_or_mesh, output_path, 'usd')

            elif format_type == 'fbx':
                # FBX export - try trimesh first, fall back to error message
                try:
                    scene_or_mesh.export(output_path, file_type='fbx')
                except Exception as e:
                    raise RuntimeError(
                        f"FBX export is not supported by trimesh.\n\n"
                        f"Alternatives:\n"
                        f"- Export as OBJ and convert in Blender/Maya\n"
                        f"- Use Blender's Python API for direct FBX export\n\n"
                        f"Error: {e}"
                    )

            print(f"Exported model to: {output_path}")
            QMessageBox.information(
                parent_window,
                "Export Complete",
                f"Model exported successfully to:\n{output_path}"
            )

        except Exception as e:
            print(f"Error exporting model: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                parent_window,
                "Export Error",
                f"Failed to export model:\n\n{str(e)}"
            )

    def _export_to_usd_format(self, scene_or_mesh, output_path, format_type):
        """Export mesh data to USD or Alembic format using pxr library.

        Args:
            scene_or_mesh: Trimesh Scene or Trimesh mesh object
            output_path: Path to save the file
            format_type: 'usd' or 'abc'
        """
        import trimesh
        import sys
        import builtins

        # Work around PySide2/shiboken2 import hook conflicts with pxr
        # Save the original __import__ and use it directly
        _original_import = builtins.__import__

        def _safe_import(name, *args, **kwargs):
            """Import bypassing shiboken's import hook for pxr modules."""
            # For pxr modules, try to import without going through hooks
            if name.startswith('pxr'):
                try:
                    # Try direct import first
                    return _original_import(name, *args, **kwargs)
                except Exception:
                    pass
            return _original_import(name, *args, **kwargs)

        try:
            # Temporarily replace __import__ to bypass shiboken hook
            builtins.__import__ = _safe_import

            # Import pxr modules
            Usd = __import__('pxr.Usd', fromlist=['Usd'])
            UsdGeom = __import__('pxr.UsdGeom', fromlist=['UsdGeom'])
            Gf = __import__('pxr.Gf', fromlist=['Gf'])
            Vt = __import__('pxr.Vt', fromlist=['Vt'])
        except (ImportError, ModuleNotFoundError) as e:
            raise RuntimeError(
                f"USD/Alembic export requires the 'pxr' library.\n\n"
                f"Install with: pip install usd-core\n\n"
                f"Note: This provides OpenUSD (Pixar's Universal Scene Description)\n\n"
                f"Error: {e}"
            )
        finally:
            # Restore original __import__
            builtins.__import__ = _original_import

        # Create the USD stage
        stage = Usd.Stage.CreateNew(output_path)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)

        # Helper to add a mesh to the stage
        def add_mesh_to_stage(mesh, name, parent_path="/World"):
            # Sanitize name for USD (no special characters)
            safe_name = "".join(c if c.isalnum() or c == '_' else '_' for c in name)
            if not safe_name or safe_name[0].isdigit():
                safe_name = "mesh_" + safe_name

            mesh_path = f"{parent_path}/{safe_name}"
            usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)

            # Set vertices
            vertices = mesh.vertices
            points = [Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])) for v in vertices]
            usd_mesh.GetPointsAttr().Set(Vt.Vec3fArray(points))

            # Set faces
            faces = mesh.faces
            face_vertex_counts = [3] * len(faces)  # All triangles
            face_vertex_indices = faces.flatten().tolist()

            usd_mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray(face_vertex_counts))
            usd_mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray(face_vertex_indices))

            # Set normals if available
            if mesh.vertex_normals is not None and len(mesh.vertex_normals) > 0:
                normals = [Gf.Vec3f(float(n[0]), float(n[1]), float(n[2])) for n in mesh.vertex_normals]
                usd_mesh.GetNormalsAttr().Set(Vt.Vec3fArray(normals))
                usd_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)

            return usd_mesh

        # Create root xform
        root = UsdGeom.Xform.Define(stage, "/World")

        # Process meshes
        if isinstance(scene_or_mesh, trimesh.Scene):
            for name, geometry in scene_or_mesh.geometry.items():
                if isinstance(geometry, trimesh.Trimesh):
                    add_mesh_to_stage(geometry, name)
        elif isinstance(scene_or_mesh, trimesh.Trimesh):
            add_mesh_to_stage(scene_or_mesh, "mesh")

        # Save the stage
        stage.GetRootLayer().Save()

    def _export_to_alembic(self, scene_or_mesh, output_path):
        """Export mesh data to Alembic format.

        Args:
            scene_or_mesh: Trimesh Scene or Trimesh mesh object
            output_path: Path to save the .abc file
        """
        import trimesh

        try:
            import alembic
            from alembic import Abc, AbcGeom
            import imath
        except ImportError:
            raise RuntimeError(
                "Alembic export requires the 'alembic' and 'imath' packages.\n\n"
                "Install with: pip install alembic\n\n"
                "Note: On Windows, you may need to install from conda:\n"
                "  conda install -c conda-forge alembic"
            )

        # Create the Alembic archive
        archive = Abc.OArchive(output_path)
        top = archive.getTop()

        # Helper to add a mesh
        def add_mesh(mesh, name, parent):
            # Create the mesh object
            mesh_obj = AbcGeom.OPolyMesh(parent, name)
            mesh_schema = mesh_obj.getSchema()

            # Get mesh data
            vertices = mesh.vertices.flatten().tolist()
            faces = mesh.faces

            # Build face counts and indices
            face_counts = [3] * len(faces)  # All triangles
            face_indices = faces.flatten().tolist()

            # Create the sample
            sample = AbcGeom.OPolyMeshSchemaSample(
                imath.V3fArray(len(mesh.vertices)),  # positions
                imath.IntArray(face_indices),        # face indices
                imath.IntArray(face_counts)          # face counts
            )

            # Set positions manually
            positions = sample.getPositions()
            for i, v in enumerate(mesh.vertices):
                positions[i] = imath.V3f(float(v[0]), float(v[1]), float(v[2]))

            mesh_schema.set(sample)

        # Process meshes
        if isinstance(scene_or_mesh, trimesh.Scene):
            for name, geometry in scene_or_mesh.geometry.items():
                if isinstance(geometry, trimesh.Trimesh):
                    # Sanitize name
                    safe_name = "".join(c if c.isalnum() or c == '_' else '_' for c in name)
                    if not safe_name or safe_name[0].isdigit():
                        safe_name = "mesh_" + safe_name
                    add_mesh(geometry, safe_name, top)
        elif isinstance(scene_or_mesh, trimesh.Trimesh):
            add_mesh(scene_or_mesh, "mesh", top)

    def _extract_textures(self):
        """Extract textures from the model to a folder."""
        from PySide2.QtWidgets import QFileDialog, QMessageBox

        # Find the main window for dialogs
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break

        # Default to a 'textures' subfolder next to the model
        default_dir = os.path.join(os.path.dirname(self.model_path), "textures")

        # Ask user for output folder
        output_dir = QFileDialog.getExistingDirectory(
            parent_window,
            "Select Folder for Extracted Textures",
            os.path.dirname(self.model_path)
        )

        if not output_dir:
            return  # User cancelled

        try:
            import trimesh
            from PIL import Image
            import io

            # Load the model with resolver to access textures
            scene_or_mesh = trimesh.load(self.model_path)

            extracted_count = 0
            base_name = os.path.splitext(os.path.basename(self.model_path))[0]

            # Helper to extract textures from a mesh
            def extract_from_mesh(mesh, mesh_name=""):
                nonlocal extracted_count

                if not hasattr(mesh, 'visual') or mesh.visual is None:
                    return

                visual = mesh.visual

                # Check for PBR material with textures
                if hasattr(visual, 'material') and visual.material is not None:
                    material = visual.material

                    # Common texture attributes in PBR materials
                    texture_attrs = [
                        ('baseColorTexture', 'basecolor'),
                        ('image', 'diffuse'),
                        ('normalTexture', 'normal'),
                        ('metallicRoughnessTexture', 'metallic_roughness'),
                        ('occlusionTexture', 'occlusion'),
                        ('emissiveTexture', 'emissive'),
                    ]

                    for attr, suffix in texture_attrs:
                        texture = getattr(material, attr, None)
                        if texture is not None:
                            try:
                                # Handle PIL Image
                                if hasattr(texture, 'save'):
                                    prefix = f"{base_name}_{mesh_name}_" if mesh_name else f"{base_name}_"
                                    filename = f"{prefix}{suffix}.png"
                                    filepath = os.path.join(output_dir, filename)
                                    texture.save(filepath)
                                    extracted_count += 1
                                    print(f"Extracted texture: {filename}")
                            except Exception as e:
                                print(f"Could not extract {attr}: {e}")

                # Check for TextureVisuals (contains UV-mapped textures)
                if hasattr(visual, 'material') and hasattr(visual.material, 'image'):
                    img = visual.material.image
                    if img is not None:
                        try:
                            prefix = f"{base_name}_{mesh_name}_" if mesh_name else f"{base_name}_"
                            filename = f"{prefix}texture.png"
                            filepath = os.path.join(output_dir, filename)
                            if hasattr(img, 'save'):
                                img.save(filepath)
                                extracted_count += 1
                                print(f"Extracted texture: {filename}")
                        except Exception as e:
                            print(f"Could not extract texture image: {e}")

            # Process scene or single mesh
            if isinstance(scene_or_mesh, trimesh.Scene):
                for name, geometry in scene_or_mesh.geometry.items():
                    if isinstance(geometry, trimesh.Trimesh):
                        extract_from_mesh(geometry, name)
            elif isinstance(scene_or_mesh, trimesh.Trimesh):
                extract_from_mesh(scene_or_mesh)

            # Also try to extract embedded textures from GLB
            if self.model_path.lower().endswith(('.glb', '.gltf')):
                try:
                    import json

                    # For GLTF, try to load the JSON directly to find embedded images
                    if self.model_path.lower().endswith('.gltf'):
                        with open(self.model_path, 'r') as f:
                            gltf_data = json.load(f)
                            if 'images' in gltf_data:
                                gltf_dir = os.path.dirname(self.model_path)
                                for i, img_info in enumerate(gltf_data['images']):
                                    if 'uri' in img_info and not img_info['uri'].startswith('data:'):
                                        # External image file
                                        src_path = os.path.join(gltf_dir, img_info['uri'])
                                        if os.path.exists(src_path):
                                            import shutil
                                            dst_name = f"{base_name}_texture_{i}{os.path.splitext(img_info['uri'])[1]}"
                                            dst_path = os.path.join(output_dir, dst_name)
                                            shutil.copy2(src_path, dst_path)
                                            extracted_count += 1
                                            print(f"Copied texture: {dst_name}")
                except Exception as e:
                    print(f"Could not extract GLTF textures: {e}")

            if extracted_count > 0:
                print(f"Extracted {extracted_count} texture(s) to: {output_dir}")
                QMessageBox.information(
                    parent_window,
                    "Texture Extraction Complete",
                    f"Extracted {extracted_count} texture(s) to:\n{output_dir}"
                )
            else:
                print("No textures found in model")
                QMessageBox.information(
                    parent_window,
                    "No Textures Found",
                    "No embedded textures were found in this model.\n\n"
                    "The model may use vertex colors or procedural materials instead."
                )

        except ImportError as e:
            print(f"Missing dependency for texture extraction: {e}")
            QMessageBox.warning(
                parent_window,
                "Missing Dependency",
                f"Texture extraction requires PIL/Pillow.\n\n"
                f"Install with: pip install Pillow\n\nError: {e}"
            )
        except Exception as e:
            print(f"Error extracting textures: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                parent_window,
                "Extraction Error",
                f"Failed to extract textures:\n\n{str(e)}"
            )


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
