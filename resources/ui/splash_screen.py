from PySide2.QtCore import Qt, QTimer, QThread, Signal, QPropertyAnimation, QEasingCurve
from PySide2.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar
from PySide2.QtGui import QPainter, QColor, QPen, QFont, QPixmap
import math
import os
from ui_components import LoadingStyles


class SpinnerWidget(QWidget):
    """
    Animated circular spinner for the splash screen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.setMinimumSize(*LoadingStyles.SPINNER_SIZE)
        self.setMaximumSize(*LoadingStyles.SPINNER_SIZE)

        # Make background transparent
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Spinner colors
        self.primary_color = LoadingStyles.PRIMARY_COLOR

        # Animation properties
        self.line_count = LoadingStyles.SPINNER_LINE_COUNT
        self.line_length = LoadingStyles.SPINNER_LINE_LENGTH
        self.line_width = LoadingStyles.SPINNER_LINE_WIDTH
        self.inner_radius = LoadingStyles.SPINNER_INNER_RADIUS

        # Event processing timer to keep UI responsive during blocking operations
        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self._process_events)

    def _process_events(self):
        """Process Qt events to keep the UI responsive."""
        from PySide2.QtWidgets import QApplication
        QApplication.processEvents()

    def start(self):
        """Start the spinner animation."""
        self.timer.start(LoadingStyles.SPINNER_ROTATION_INTERVAL)
        # Start event processing timer at higher frequency (every 16ms ~= 60 FPS)
        self.event_timer.start(16)

    def stop(self):
        """Stop the spinner animation."""
        self.timer.stop()
        self.event_timer.stop()

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
        from PySide2.QtWidgets import QApplication
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

        # Title - removed for cleaner logo-only design
        # self.title_label = QLabel("Luma Shot Tools")
        # self.title_label.setAlignment(Qt.AlignCenter)
        # self.title_label.setFont(LoadingStyles.TITLE_FONT)
        # self.title_label.setStyleSheet(f"color: {LoadingStyles.PRIMARY_COLOR_STR};")

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
        layout.addStretch()  # Move logo up away from spinner
        # Title label removed for cleaner design
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
        Show splash and run initialization callback using QTimer.
        This keeps the splash responsive while initialization happens.

        Args:
            init_callback: A function that will be called after the splash is shown.
                          Should return the main window.
        """
        from PySide2.QtCore import QTimer
        from PySide2.QtWidgets import QApplication

        def do_init():
            """Perform initialization."""
            try:
                # Update progress
                self.update_progress(30, "Initializing Luma Shot Tools", "Creating main window...")
                QApplication.processEvents()

                # Call the initialization callback
                window = init_callback()

                # Update progress
                self.update_progress(90, "Initializing Luma Shot Tools", "Almost ready...")
                QApplication.processEvents()

                # Close splash and show window
                QTimer.singleShot(500, lambda: self._finish_initialization(window))

            except Exception as e:
                print(f"Error during initialization: {e}")
                import traceback
                traceback.print_exc()
                self.close()

        # Start initialization after a short delay to ensure splash is visible
        QTimer.singleShot(100, do_init)

    def _finish_initialization(self, window):
        """Finish initialization and show the main window."""
        if window:
            self.stop_animation()
            self.fade_out_and_close()
            window.show()
        else:
            self.close()
