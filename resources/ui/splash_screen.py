from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPropertyAnimation, QEasingCurve, QThreadPool
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPixmap
import math
import os
from ui_components import LoadingStyles, Worker, SpinnerWidget


class SplashScreen(QWidget):
    """
    Standalone splash screen that appears immediately on startup.
    Uses QTimer to coordinate initialization steps while keeping the UI responsive.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Set fixed size
        self.setFixedSize(*LoadingStyles.SPLASH_SIZE)

        # Center on screen
        self.center_on_screen()

        # Create UI
        self.setup_ui()

    def center_on_screen(self):
        """Center the splash screen on the screen."""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        self.move(
            (screen.width() - size.width()) // 2,
            (screen.height() - size.height()) // 2
        )

    def setup_ui(self):
        """Set up the splash screen UI."""
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(LoadingStyles.SPLASH_MARGIN, LoadingStyles.SPLASH_MARGIN,
                                  LoadingStyles.SPLASH_MARGIN, LoadingStyles.SPLASH_MARGIN)
        layout.setSpacing(LoadingStyles.SPLASH_SPACING)

        # Logo container for proper centering
        logo_path = LoadingStyles.get_logo_path()
        logo_container = QWidget()
        logo_container.setStyleSheet("background: transparent;")
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setAlignment(Qt.AlignCenter)

        self.logo_label = QLabel()
        self.logo_label.setStyleSheet("background: transparent;")
        # Set size to ensure logo is not cut off
        self.logo_label.setFixedSize(*LoadingStyles.LOGO_SIZE_SPLASH)
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Scale to a reasonable size while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                *LoadingStyles.LOGO_SIZE_SPLASH,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.logo_label.setPixmap(scaled_pixmap)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setScaledContents(False)  # Don't scale contents, use actual pixmap size

        logo_layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)

        # Spinner
        self.spinner = SpinnerWidget()
        spinner_container = QWidget()
        spinner_container.setStyleSheet("background: transparent;")
        spinner_layout = QVBoxLayout(spinner_container)
        spinner_layout.addWidget(self.spinner, alignment=Qt.AlignCenter)
        spinner_layout.setContentsMargins(0, 0, 0, 0)

        # Main status label
        self.main_label = QLabel("Initializing...")
        self.main_label.setAlignment(Qt.AlignCenter)
        self.main_label.setFont(LoadingStyles.MAIN_TEXT_FONT)
        self.main_label.setStyleSheet(f"color: {LoadingStyles.TEXT_PRIMARY_COLOR_STR}; background: transparent;")

        # Sub status label
        self.sub_label = QLabel("Starting application...")
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setFont(LoadingStyles.SUB_TEXT_FONT)
        self.sub_label.setStyleSheet(f"color: {LoadingStyles.TEXT_TERTIARY_COLOR_STR}; background: transparent;")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(LoadingStyles.PROGRESS_BAR_SPLASH_HEIGHT)
        self.progress_bar.setStyleSheet(LoadingStyles.get_progress_bar_stylesheet(
            LoadingStyles.PROGRESS_BAR_SPLASH_HEIGHT
        ))

        # Add widgets to layout
        layout.addStretch()
        layout.addWidget(logo_container)
        layout.addStretch()
        layout.addWidget(spinner_container)
        layout.addWidget(self.main_label)
        layout.addWidget(self.sub_label)
        layout.addWidget(self.progress_bar)
        layout.addStretch()

        self.setLayout(layout)

    def paintEvent(self, event):
        """Paint the background."""
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

    def update_progress(self, progress, main_text, sub_text):
        """Update the splash screen progress."""
        self.progress_bar.setValue(progress)
        self.main_label.setText(main_text)
        self.sub_label.setText(sub_text)

    def start_animation(self):
        """Start the spinner animation."""
        self.spinner.start()

    def stop_animation(self):
        """Stop the spinner animation."""
        self.spinner.stop()

    def fade_out_and_close(self):
        """Fade out and close the splash screen."""
        # Simple immediate close for now
        # Could add fade animation here if desired
        self.close()

    def run_with_initialization(self, init_callback):
        """
        Show splash and run initialization callback on a background thread.
        This keeps the splash spinner smooth while initialization happens.

        Args:
            init_callback: A function that will be called on a background thread.
                          Should return the main window.
        """
        from PySide6.QtCore import QTimer

        def progress_update(progress, message):
            """Update progress from worker thread."""
            if progress <= 30:
                self.update_progress(progress, "Initializing Luma Shot Tools", message)
            elif progress <= 90:
                self.update_progress(progress, "Initializing Luma Shot Tools", message)
            else:
                self.update_progress(progress, "Initializing Luma Shot Tools", "Almost ready...")

        def on_result(window):
            """Called when initialization completes successfully."""
            self.update_progress(100, "Initializing Luma Shot Tools", "Ready!")
            # Small delay before closing splash
            QTimer.singleShot(300, lambda: self._finish_initialization(window))

        def on_error(error_msg, traceback_str):
            """Called when initialization fails."""
            print(f"Error during initialization: {error_msg}")
            print(traceback_str)
            self.close()

        # Create worker for initialization
        worker = Worker(init_callback)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(progress_update)

        # Start worker after a short delay to ensure splash is visible
        QTimer.singleShot(100, lambda: QThreadPool.globalInstance().start(worker))

    def _finish_initialization(self, window):
        """Finish initialization and show the main window."""
        if window:
            self.stop_animation()
            self.fade_out_and_close()
            window.show()
        else:
            self.close()
