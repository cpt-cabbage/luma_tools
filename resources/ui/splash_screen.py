"""
Splash Screen for Luma Shot Tools
Displays immediately on startup with initialization running in a separate thread.
"""

from PySide2.QtCore import Qt, QTimer, QThread, Signal, QPropertyAnimation, QEasingCurve
from PySide2.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar
from PySide2.QtGui import QPainter, QColor, QPen, QFont, QPixmap
import math


class SpinnerWidget(QWidget):
    """
    Animated circular spinner for the splash screen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.setMinimumSize(80, 80)
        self.setMaximumSize(80, 80)

        # Spinner colors
        self.primary_color = QColor(74, 158, 255)  # #4a9eff

        # Animation properties
        self.line_count = 12
        self.line_length = 20
        self.line_width = 3
        self.inner_radius = 15

    def start(self):
        """Start the spinner animation."""
        self.timer.start(50)  # 20 FPS for smooth animation

    def stop(self):
        """Stop the spinner animation."""
        self.timer.stop()

    def rotate(self):
        """Rotate the spinner."""
        self.angle = (self.angle + 30) % 360
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
        self.setFixedSize(500, 300)

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
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # Title
        self.title_label = QLabel("Luma Shot Tools")
        self.title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont("Segoe UI", 24, QFont.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #4a9eff;")

        # Spinner
        self.spinner = SpinnerWidget()
        spinner_container = QWidget()
        spinner_layout = QVBoxLayout(spinner_container)
        spinner_layout.addWidget(self.spinner, alignment=Qt.AlignCenter)
        spinner_layout.setContentsMargins(0, 0, 0, 0)

        # Main status label
        self.main_label = QLabel("Initializing...")
        self.main_label.setAlignment(Qt.AlignCenter)
        main_font = QFont("Segoe UI", 12)
        self.main_label.setFont(main_font)
        self.main_label.setStyleSheet("color: #ffffff;")

        # Sub status label
        self.sub_label = QLabel("Starting application...")
        self.sub_label.setAlignment(Qt.AlignCenter)
        sub_font = QFont("Segoe UI", 9)
        self.sub_label.setFont(sub_font)
        self.sub_label.setStyleSheet("color: #888888;")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2a2a2a;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #4a9eff;
                border-radius: 2px;
            }
        """)

        # Add widgets to layout
        layout.addStretch()
        layout.addWidget(self.title_label)
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
        painter.setBrush(QColor(30, 30, 30, 240))
        painter.setPen(QPen(QColor(74, 158, 255, 100), 2))
        painter.drawRoundedRect(self.rect(), 15, 15)

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
