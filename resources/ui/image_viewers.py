"""
Image viewer widgets for the gallery.

Contains embedded and fullscreen viewers with support for images, 3D models, and videos.
"""
import os
import logging
from PySide6.QtCore import Qt, QTimer, Signal, QThreadPool, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QMenu, QComboBox, QApplication, QSlider, QGraphicsOpacityEffect
)
from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap

from dialog_helpers import get_active_window, show_error, show_warning, confirm_action

# Import event bus for cross-tab communication
try:
    from core.event_bus import pipeline_events
    EVENT_BUS_AVAILABLE = True
except ImportError:
    EVENT_BUS_AVAILABLE = False
    pipeline_events = None

logger = logging.getLogger(__name__)


class ZoomableImageWidget(QtWidgets.QGraphicsView):
    """A widget that displays an image with support for zooming and panning."""
    double_clicked = Signal()
    zoom_changed = Signal(str)
    ZOOM_LEVELS = ["Fit", "100%", "50%", "25%", "10%"]
    MIN_ZOOM = 0.10  # Minimum zoom level (10%)
    MAX_ZOOM = 10.0  # Maximum zoom level (1000%)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QPainter
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
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

        self._is_panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0
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
        if not self._pixmap_item.pixmap() or self._pixmap_item.pixmap().isNull():
            return
        self._current_zoom = level
        if level == "Fit":
            self.resetTransform()
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        else:
            percentage = int(level.replace("%", ""))
            scale = percentage / 100.0
            self.resetTransform()
            self.scale(scale, scale)
            self.centerOn(self._pixmap_item)
        self.zoom_changed.emit(level)

    def currentZoom(self):
        return self._current_zoom

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        zoom_factor = zoom_in_factor if event.angleDelta().y() > 0 else zoom_out_factor

        # Check zoom limits before applying
        current_scale = self.transform().m11()
        new_scale = current_scale * zoom_factor

        if new_scale < self.MIN_ZOOM:
            zoom_factor = self.MIN_ZOOM / current_scale
        elif new_scale > self.MAX_ZOOM:
            zoom_factor = self.MAX_ZOOM / current_scale

        self.scale(zoom_factor, zoom_factor)
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

    def resizeEvent(self, event):
        """Re-fit image when resized if in Fit mode."""
        super().resizeEvent(event)
        if self._current_zoom == "Fit" and self._pixmap_item.pixmap() and not self._pixmap_item.pixmap().isNull():
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)


class VideoSinkWidget(QWidget):
    """Video display using QVideoSink for software rendering.

    Replaces QVideoWidget to avoid its native rendering surface painting
    over Qt overlay widgets (controls, info bars) on Windows.
    """
    clicked = Signal()  # Emitted on left mouse click (for click-to-play/pause)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtMultimedia import QVideoSink
        self.setStyleSheet("background-color: #000000;")
        self._video_sink = QVideoSink(self)
        self._video_sink.videoFrameChanged.connect(self._on_frame_changed)
        self._current_image = None

    @property
    def videoSink(self):
        return self._video_sink

    def _on_frame_changed(self, frame):
        if frame.isValid():
            self._current_image = frame.toImage()
        else:
            self._current_image = None
        self.update()

    def paintEvent(self, event):
        if self._current_image and not self._current_image.isNull():
            from PySide6.QtGui import QPainter
            from PySide6.QtCore import QRect
            painter = QPainter(self)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            # Scale to fit while keeping aspect ratio, centered
            img_size = self._current_image.size()
            scaled = img_size.scaled(self.size(), Qt.KeepAspectRatio)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawImage(QRect(x, y, scaled.width(), scaled.height()), self._current_image)
            painter.end()
        else:
            super().paintEvent(event)

    def mousePressEvent(self, event):
        """Emit clicked signal on left mouse button press."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class VideoControlBar(QWidget):
    """
    Video/audio playback control bar with play/pause, seek, volume, and time display.

    Features:
    - Play/pause button
    - Timeline scrubber (seek bar)
    - Volume control (button + slider)
    - Time display (current / total)
    - Loop toggle
    - Auto-hide after inactivity
    """

    def __init__(self, media_player, parent=None):
        super().__init__(parent)
        self.media_player = media_player
        self._is_playing = False
        self._duration = 0
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._fade_out)
        self._hide_delay = 3000  # 3 seconds

        # Seek throttle — Windows Media Foundation drops rapid setPosition() calls,
        # so we buffer to ~20fps to let each seek actually decode a frame.
        self._pending_seek_pos = None
        self._was_playing_before_seek = False
        self._seek_throttle = QTimer(self)
        self._seek_throttle.setSingleShot(True)
        self._seek_throttle.setInterval(50)
        self._seek_throttle.timeout.connect(self._apply_pending_seek)

        # Enable mouse tracking and ensure widget accepts events
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # Opacity effect for fade animations
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

        self._setup_ui()
        self._connect_signals()
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 180);
                border-radius: 5px;
            }
        """)

    def _setup_ui(self):
        """Set up the control bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        # Ensure layout doesn't constrain child widgets
        layout.setAlignment(Qt.AlignVCenter)

        # Play/Pause button
        self.play_button = QPushButton()
        self.play_button.setText("\u25B6")  # Play symbol ▶
        self.play_button.setFixedSize(44, 44)
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.setFocusPolicy(Qt.ClickFocus)
        # Ensure button gets all mouse events
        self.play_button.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.play_button.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: white;
                border: none;
                border-radius: 22px;
                font-size: 22px;
                font-weight: bold;
                font-family: "Segoe UI Symbol", "Segoe UI Emoji", "Arial Unicode MS", Arial, sans-serif;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #5aa9ff;
            }
            QPushButton:pressed {
                background-color: #3a8eef;
            }
        """)
        self.play_button.clicked.connect(self._toggle_play)
        layout.addWidget(self.play_button)

        # Current time label
        self.time_label = QLabel("0:00")
        self.time_label.setStyleSheet("color: white; font-size: 12px;")
        self.time_label.setFixedWidth(45)
        layout.addWidget(self.time_label)

        # Timeline scrubber (seek bar)
        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setRange(0, 1000)
        self.timeline_slider.setValue(0)
        self.timeline_slider.setCursor(Qt.PointingHandCursor)
        self.timeline_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444444;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #4a9eff;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #e0e0e0;
            }
        """)
        self.timeline_slider.sliderPressed.connect(self._on_seek_start)
        self.timeline_slider.sliderMoved.connect(self._on_seek_move)
        self.timeline_slider.sliderReleased.connect(self._on_seek_end)
        layout.addWidget(self.timeline_slider, stretch=1)

        # Duration label
        self.duration_label = QLabel("0:00")
        self.duration_label.setStyleSheet("color: white; font-size: 12px;")
        self.duration_label.setFixedWidth(45)
        layout.addWidget(self.duration_label)

        # Volume button
        self.volume_button = QPushButton("\U0001f50a")
        self.volume_button.setFixedSize(34, 34)
        self.volume_button.setCursor(Qt.PointingHandCursor)
        self.volume_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 17px;
            }
        """)
        self.volume_button.clicked.connect(self._toggle_mute)
        layout.addWidget(self.volume_button)

        # Volume slider (initially hidden)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setCursor(Qt.PointingHandCursor)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444444;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #4a9eff;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self.volume_slider)

        # Loop toggle button
        self.loop_button = QPushButton("\U0001f501")
        self.loop_button.setCheckable(True)
        self.loop_button.setChecked(False)
        self.loop_button.setFixedSize(34, 34)
        self.loop_button.setCursor(Qt.PointingHandCursor)
        self.loop_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 17px;
            }
            QPushButton:checked {
                color: #4a9eff;
            }
        """)
        layout.addWidget(self.loop_button)

    def _connect_signals(self):
        """Connect media player signals."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            self.media_player.positionChanged.connect(self._on_position_changed)
            self.media_player.durationChanged.connect(self._on_duration_changed)
            self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)

            # Loop support
            self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
        except Exception as e:
            logger.warning(f"Failed to connect media player signals: {e}")

    def _toggle_play(self):
        """Toggle play/pause."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            # Provide immediate visual feedback
            self.play_button.setDown(True)
            QTimer.singleShot(100, lambda: self.play_button.setDown(False))

            if self.media_player.playbackState() == QMediaPlayer.PlayingState:
                self.media_player.pause()
            else:
                self.media_player.play()
        except Exception as e:
            logger.error(f"Error toggling playback: {e}")

    def _on_playback_state_changed(self, state):
        """Handle playback state changes."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            self._is_playing = (state == QMediaPlayer.PlayingState)
            # Update button icon based on state
            if self._is_playing:
                self.play_button.setText("\u23F8")  # Pause symbol ⏸
            else:
                self.play_button.setText("\u25B6")  # Play symbol ▶
        except Exception:
            pass

    def _on_position_changed(self, position):
        """Update timeline and time label when position changes."""
        if not self.timeline_slider.isSliderDown():
            if self._duration > 0:
                self.timeline_slider.setValue(int((position / self._duration) * 1000))

            # Format and update time label
            from core.utils import format_duration
            self.time_label.setText(format_duration(position / 1000))

    def _on_duration_changed(self, duration):
        """Update duration label when media duration is known."""
        self._duration = duration
        from core.utils import format_duration
        self.duration_label.setText(format_duration(duration / 1000))

    def _on_seek_start(self):
        """Pause playback while seeking so the backend renders each seeked frame."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            self._was_playing_before_seek = (
                self.media_player.playbackState() == QMediaPlayer.PlayingState
            )
            if self._was_playing_before_seek:
                self.media_player.pause()
        except Exception:
            self._was_playing_before_seek = False

    def _on_seek_move(self, value):
        """Buffer seek position and throttle actual seeks for live scrubbing."""
        if self._duration > 0:
            position = int((value / 1000) * self._duration)
            from core.utils import format_duration
            self.time_label.setText(format_duration(position / 1000))
            self._pending_seek_pos = position
            # Fire immediately if throttle isn't running, otherwise let timer batch it
            if not self._seek_throttle.isActive():
                self._apply_pending_seek()
                self._seek_throttle.start()

    def _apply_pending_seek(self):
        """Apply the most recent buffered seek position."""
        if self._pending_seek_pos is not None:
            self.media_player.setPosition(self._pending_seek_pos)
            self._pending_seek_pos = None

    def _on_seek_end(self):
        """Apply final position and resume playback if it was playing."""
        self._seek_throttle.stop()
        if self._duration > 0:
            position = int((self.timeline_slider.value() / 1000) * self._duration)
            self.media_player.setPosition(position)
        self._pending_seek_pos = None
        if self._was_playing_before_seek:
            self.media_player.play()
            self._was_playing_before_seek = False

    def _on_volume_changed(self, value):
        """Update volume."""
        try:
            from PySide6.QtMultimedia import QAudioOutput
            # Qt6 uses QAudioOutput for volume control
            audio_output = self.media_player.audioOutput()
            if audio_output:
                audio_output.setVolume(value / 100.0)

                # Update volume icon
                if value == 0:
                    self.volume_button.setText("🔇")
                elif value < 50:
                    self.volume_button.setText("🔉")
                else:
                    self.volume_button.setText("🔊")
        except Exception as e:
            logger.debug(f"Error setting volume: {e}")

    def _toggle_mute(self):
        """Toggle mute."""
        if self.volume_slider.value() > 0:
            self._saved_volume = self.volume_slider.value()
            self.volume_slider.setValue(0)
        else:
            self.volume_slider.setValue(self._saved_volume if hasattr(self, '_saved_volume') else 100)

    def _on_media_status_changed(self, status):
        """Handle media status changes for looping."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.EndOfMedia and self.loop_button.isChecked():
                self.media_player.setPosition(0)
                self.media_player.play()
        except Exception:
            pass

    def show_controls(self):
        """Show controls with fade-in and restart auto-hide timer."""
        # Stop any running fade animation
        self._fade_anim.stop()

        self.show()
        self.raise_()  # Ensure controls are on top
        self.setFocus()  # Give focus to controls for interaction

        # Fade in from current opacity to fully visible
        current_opacity = self._opacity_effect.opacity()
        if current_opacity < 1.0:
            self._fade_anim.setDuration(200)
            self._fade_anim.setStartValue(current_opacity)
            self._fade_anim.setEndValue(1.0)
            # Disconnect any previous finished connections
            try:
                self._fade_anim.finished.disconnect()
            except RuntimeError:
                pass
            self._fade_anim.start()
        self._auto_hide_timer.start(self._hide_delay)

    def _fade_out(self):
        """Fade out controls after inactivity."""
        if self._is_playing:
            self._fade_anim.stop()
            self._fade_anim.setDuration(400)
            self._fade_anim.setStartValue(self._opacity_effect.opacity())
            self._fade_anim.setEndValue(0.0)
            # Disconnect any previous finished connections
            try:
                self._fade_anim.finished.disconnect()
            except RuntimeError:
                pass
            self._fade_anim.finished.connect(self._on_fade_out_finished)
            self._fade_anim.start()

    def _on_fade_out_finished(self):
        """Hide widget after fade-out completes."""
        if self._opacity_effect.opacity() <= 0.01:
            self.hide()

    def enterEvent(self, event):
        """Show controls on mouse enter."""
        super().enterEvent(event)
        self.show_controls()
        # Stop auto-hide while hovering over controls
        self._auto_hide_timer.stop()

    def leaveEvent(self, event):
        """Start hide timer on mouse leave."""
        super().leaveEvent(event)
        self._auto_hide_timer.start(self._hide_delay)


class WaveformWidget(QWidget):
    """Custom widget for drawing audio waveform."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.waveform_data = None
        self.play_position = 0.0
        self.setStyleSheet("background-color: #1a1a1a;")
        self.setMinimumHeight(200)

    def paintEvent(self, event):
        """Draw the waveform."""
        super().paintEvent(event)

        if not self.waveform_data:
            return

        from PySide6.QtGui import QPainter, QPen, QColor
        from PySide6.QtCore import QPointF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        center_y = height / 2

        # Draw center line
        painter.setPen(QPen(QColor("#333333")))
        painter.drawLine(QPointF(0, center_y), QPointF(width, center_y))

        # Draw waveform
        pen = QPen(QColor("#4a9eff"))
        pen.setWidth(1)
        painter.setPen(pen)

        points = len(self.waveform_data)
        x_step = width / points

        for i in range(points):
            x = i * x_step
            sample = self.waveform_data[i]
            y = center_y - (sample * center_y * 0.9)
            painter.drawLine(QPointF(x, center_y), QPointF(x, y))

        # Draw playback cursor
        cursor_x = self.play_position * width
        cursor_pen = QPen(QColor("#ef4444"))
        cursor_pen.setWidth(2)
        painter.setPen(cursor_pen)
        painter.drawLine(QPointF(cursor_x, 0), QPointF(cursor_x, height))

        painter.end()


class AudioPlayerWidget(QWidget):
    """
    Audio player with waveform visualization.

    Features:
    - Audio playback using QMediaPlayer
    - Animated waveform display
    - Same playback controls as video
    - Waveform data extraction and caching
    """

    def __init__(self, audio_path, parent=None):
        super().__init__(parent)
        self.audio_path = audio_path

        self._setup_ui()
        self._setup_media_player()
        self._load_waveform_async()

    def _setup_ui(self):
        """Set up the audio player UI."""
        self.setStyleSheet("background-color: #1a1a1a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Waveform widget
        self.waveform_widget = WaveformWidget(self)
        layout.addWidget(self.waveform_widget, stretch=1)

        # Status label (shown while loading)
        self.status_label = QLabel("Loading audio...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #888888; font-size: 14px;")
        self.status_label.setAttribute(Qt.WA_TranslucentBackground)
        self.status_label.setParent(self.waveform_widget)

    def _setup_media_player(self):
        """Set up the media player for audio playback."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl

            self.media_player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.media_player.setAudioOutput(self.audio_output)

            # Connect signals
            self.media_player.positionChanged.connect(self._on_position_changed)
            self.media_player.durationChanged.connect(self._on_duration_changed)

            # Load audio file
            self.media_player.setSource(QUrl.fromLocalFile(self.audio_path))

            # Create control bar as overlay
            self.controls = VideoControlBar(self.media_player, parent=self)
            self.controls.show()
        except Exception as e:
            logger.error(f"Failed to set up audio player: {e}")
            self.status_label.setText(f"Audio Player Not Available\n\n{str(e)}")

    def _load_waveform_async(self):
        """Load waveform data in background thread."""
        from workers import Worker
        self._waveform_loading = True
        self._waveform_worker = Worker(self._extract_waveform_data, self.audio_path)
        self._waveform_worker.signals.result.connect(self._on_waveform_loaded)
        self._waveform_worker.signals.error.connect(self._on_waveform_error)
        QThreadPool.globalInstance().start(self._waveform_worker)

    @staticmethod
    def _extract_waveform_data(audio_path):
        """
        Extract waveform data from audio file using FFmpeg.

        Returns:
            list: Normalized waveform samples (values between -1.0 and 1.0)
        """
        import subprocess
        import tempfile
        import struct
        from core.config import FFMPEG_PATH

        if not FFMPEG_PATH:
            return None

        try:
            # Extract audio to raw PCM format
            with tempfile.NamedTemporaryFile(suffix='.raw', delete=False) as tmp:
                tmp_path = tmp.name

            # Extract mono 16-bit PCM at 8kHz (good for visualization, fast to process)
            cmd = [
                FFMPEG_PATH,
                '-i', audio_path,
                '-f', 's16le',  # 16-bit signed little-endian PCM
                '-ac', '1',     # Mono
                '-ar', '8000',  # 8kHz sample rate
                '-y', tmp_path
            ]

            import os
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=creationflags)
            if result.returncode != 0:
                logger.warning(f"FFmpeg waveform extraction failed: {result.stderr.decode()}")
                return None

            # Read PCM data
            with open(tmp_path, 'rb') as f:
                pcm_data = f.read()

            os.remove(tmp_path)

            if not pcm_data:
                return None

            # Convert to list of normalized samples
            sample_count = len(pcm_data) // 2
            samples = struct.unpack(f'<{sample_count}h', pcm_data)

            # Normalize to -1.0 to 1.0 range
            max_value = 32768.0
            normalized = [s / max_value for s in samples]

            # Downsample to max 2000 points for rendering performance
            target_points = min(2000, len(normalized))
            if len(normalized) > target_points:
                step = len(normalized) / target_points
                downsampled = []
                for i in range(target_points):
                    idx = int(i * step)
                    # Use RMS of nearby samples for better visual representation
                    window_start = max(0, idx - 5)
                    window_end = min(len(normalized), idx + 5)
                    window = normalized[window_start:window_end]
                    rms = (sum(s * s for s in window) / len(window)) ** 0.5
                    # Preserve sign
                    downsampled.append(rms if sum(window) >= 0 else -rms)
                normalized = downsampled

            return normalized

        except Exception as e:
            logger.error(f"Error extracting waveform: {e}")
            return None

    def _on_waveform_loaded(self, waveform_data):
        """Handle waveform data loaded."""
        self.waveform_widget.waveform_data = waveform_data
        self.status_label.hide()
        self.waveform_widget.update()

    def _on_waveform_error(self, error_msg, traceback):
        """Handle waveform loading error."""
        self.status_label.setText("Waveform visualization unavailable")
        logger.warning(f"Waveform loading error: {error_msg}")

    def _on_position_changed(self, position):
        """Update playback cursor position."""
        try:
            duration = self.media_player.duration()
            if duration > 0:
                self.waveform_widget.play_position = position / duration
                self.waveform_widget.update()
        except Exception:
            pass

    def _on_duration_changed(self, duration):
        """Handle duration change."""
        pass

    def resizeEvent(self, event):
        """Handle resize to reposition controls."""
        super().resizeEvent(event)

        # Position control bar at bottom
        if hasattr(self, 'controls'):
            controls_height = 56
            controls_margin = 10
            self.controls.setGeometry(
                controls_margin,
                self.height() - controls_height - controls_margin,
                self.width() - 2 * controls_margin,
                controls_height
            )
            self.controls.raise_()

        # Center status label
        if hasattr(self, 'status_label'):
            self.status_label.setGeometry(0, 0, self.waveform_widget.width(), self.waveform_widget.height())

    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'media_player') and self.media_player:
            self.media_player.stop()


class EmbeddedImageViewer(QWidget):
    """
    Embedded image viewer with keyboard navigation for use within the gallery tab.

    Controls:
    - Left/Right arrows or A/D: Navigate between images
    - Escape or Backspace: Close viewer and return to gallery
    - Home/End: Jump to first/last image
    - C: Copy prompt to clipboard (if available)
    - S: Apply settings to ComfyUI tab (if available)
    - Delete: Delete current image
    """
    closed = Signal()
    view_fullscreen = Signal(str, int)
    copy_settings_requested = Signal(dict)
    image_deleted = Signal(str)  # Emitted when an image is deleted (path)
    image_viewed = Signal(str)  # Emitted when navigating to an image (path)
    like_toggled = Signal(str, bool)  # Emitted when like status is toggled (path, is_liked)

    def __init__(self, image_paths, start_index=0, output_dir=None, parent=None):
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.current_index = start_index
        self.output_dir = output_dir
        self._favorites_manager = None

        self._setup_ui()
        self._load_current_image()
        self.setFocusPolicy(Qt.StrongFocus)

    def set_favorites_manager(self, manager):
        """Set the favorites manager for like functionality."""
        self._favorites_manager = manager
        self._update_like_button()

    def _setup_ui(self):
        """Set up the embedded viewer UI."""
        self.setStyleSheet("background-color: #1a1a1a;")

        # Enable mouse tracking to show video controls on mouse movement
        self.setMouseTracking(True)

        # Set size policy to expand and fill available space
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Main layout - single container fills everything
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main container for content and overlays
        self.image_container = QWidget()
        self.image_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.image_container, stretch=1)

        # Content layout inside container
        content_layout = QHBoxLayout(self.image_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.left_btn = QPushButton("<")
        self.left_btn.setFixedWidth(50)
        self.left_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 24px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
            QPushButton:disabled { color: #333333; }
        """)
        self.left_btn.setCursor(Qt.PointingHandCursor)
        self.left_btn.clicked.connect(self._prev_image)
        content_layout.addWidget(self.left_btn)

        self.image_stack = QtWidgets.QStackedWidget()
        content_layout.addWidget(self.image_stack, stretch=1)

        # 1. Zoomable Image View
        self.image_view = ZoomableImageWidget()
        self.image_view.setFocusPolicy(Qt.NoFocus)  # Prevent stealing focus from parent
        self.image_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_view.customContextMenuRequested.connect(self._show_context_menu)
        self.image_view.zoom_changed.connect(self._on_image_zoom_changed)
        self.image_stack.addWidget(self.image_view)

        # 2. 3D Model Viewer (Three.js) - Lazy initialization
        self._has_glb_viewer = None
        self.glb_viewer = None
        self._glb_viewer_initialized = False

        # 3. Video Player (uses VideoSinkWidget for software rendering
        #    so overlay controls can draw on top of the video)
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

            self.video_widget = VideoSinkWidget()
            self.media_player = QMediaPlayer(self)

            self.audio_output = QAudioOutput(self)
            self.media_player.setAudioOutput(self.audio_output)
            self.media_player.setVideoSink(self.video_widget.videoSink)

            # Enable mouse tracking on video widget to show controls
            self.video_widget.setMouseTracking(True)
            self.video_widget.installEventFilter(self)

            self.image_stack.addWidget(self.video_widget)
            self._has_video_player = True

            # Create video control bar (overlay widget)
            self.video_controls = VideoControlBar(self.media_player, parent=self.image_container)
            self.video_controls.hide()  # Hidden by default, shown for video playback
        except Exception as e:
            logger.warning(f"Video player not available: {e}")
            self._has_video_player = False
            self.video_widget = None
            self.media_player = None
            self.video_controls = None

        # 4. Message Label
        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("background-color: #1a1a1a; color: #888888; font-size: 16px;")
        self.image_stack.addWidget(self.message_label)

        self.right_btn = QPushButton(">")
        self.right_btn.setFixedWidth(50)
        self.right_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 24px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
            QPushButton:disabled { color: #333333; }
        """)
        self.right_btn.setCursor(Qt.PointingHandCursor)
        self.right_btn.clicked.connect(self._next_image)
        content_layout.addWidget(self.right_btn)

        # Top bar - overlay widget (child of image_container, not in layout)
        self.top_bar = QWidget(self.image_container)
        self.top_bar.setStyleSheet("background-color: transparent;")
        self.top_bar.setFixedHeight(50)

        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 10, 10, 10)

        self.back_btn = QPushButton("< Back to Gallery")
        self.back_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: #4a9eff; border: none; font-size: 12px; padding: 5px 10px; }
            QPushButton:hover { color: #7ab8ff; }
        """)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self._on_back)
        top_layout.addWidget(self.back_btn)

        top_layout.addStretch()

        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("color: #888888; font-size: 12px;")
        top_layout.addWidget(self.counter_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(ZoomableImageWidget.ZOOM_LEVELS)
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.setFixedWidth(80)
        self.zoom_combo.setStyleSheet("""
            QComboBox { background-color: #2a2a2a; color: #cccccc; border: 1px solid #555555; border-radius: 3px; padding: 3px 8px; font-size: 11px; }
            QComboBox:hover { border-color: #4a9eff; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #888888; margin-right: 5px; }
            QComboBox QAbstractItemView { background-color: #2a2a2a; color: #cccccc; selection-background-color: #4a9eff; border: 1px solid #555555; }
        """)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        top_layout.addWidget(self.zoom_combo)

        self.fullscreen_btn = QPushButton("Fullscreen")
        self.fullscreen_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888888; border: 1px solid #555555; border-radius: 3px; font-size: 11px; padding: 3px 10px; }
            QPushButton:hover { color: #ffffff; border-color: #4a9eff; }
        """)
        self.fullscreen_btn.setCursor(Qt.PointingHandCursor)
        self.fullscreen_btn.clicked.connect(self._on_fullscreen)
        top_layout.addWidget(self.fullscreen_btn)

        # Add separator
        top_layout.addSpacing(10)

        # Like button (moved from bottom)
        self.like_btn = QPushButton("♡")
        self.like_btn.setFixedSize(28, 28)
        self.like_btn.setToolTip("Like (L)")
        self.like_btn.setCursor(Qt.PointingHandCursor)
        self.like_btn.clicked.connect(self._toggle_like)
        self._update_like_button_style(False)
        top_layout.addWidget(self.like_btn)

        # 3D Model controls (hidden by default, moved from bottom)
        # Shading Mode dropdown
        self.shading_btn = QPushButton("Textured")
        self.shading_btn.setFixedHeight(28)
        self.shading_btn.setStyleSheet("""
            QPushButton { background-color: #4a9eff; color: white; border: none; border-radius: 3px; padding: 0 10px; font-size: 11px; }
            QPushButton:hover { background-color: #5aa9ff; }
        """)
        self.shading_btn.clicked.connect(self._show_shading_menu)
        self.shading_btn.hide()
        top_layout.addWidget(self.shading_btn)

        # Lighting Mode dropdown
        self.lighting_btn = QPushButton("Studio")
        self.lighting_btn.setFixedHeight(28)
        self.lighting_btn.setStyleSheet("""
            QPushButton { background-color: #6b7280; color: white; border: none; border-radius: 3px; padding: 0 10px; font-size: 11px; }
            QPushButton:hover { background-color: #7c8596; }
        """)
        self.lighting_btn.clicked.connect(self._show_lighting_menu)
        self.lighting_btn.hide()
        top_layout.addWidget(self.lighting_btn)

        # Light strength label
        self.light_label = QLabel("Light:")
        self.light_label.setStyleSheet("color: #888888; font-size: 11px;")
        self.light_label.hide()
        top_layout.addWidget(self.light_label)

        # Light strength slider
        self.light_slider = QSlider(Qt.Horizontal)
        self.light_slider.setMinimum(10)  # 0.1x
        self.light_slider.setMaximum(300)  # 3.0x
        self.light_slider.setValue(100)  # 1.0x default
        self.light_slider.setFixedWidth(80)
        self.light_slider.setFixedHeight(20)
        self.light_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333333;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #4a9eff;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #5aa9ff;
            }
        """)
        self.light_slider.valueChanged.connect(self._on_light_strength_changed)
        self.light_slider.hide()
        top_layout.addWidget(self.light_slider)

        # Light strength value label
        self.light_value_label = QLabel("1.0x")
        self.light_value_label.setFixedWidth(35)
        self.light_value_label.setStyleSheet("color: #888888; font-size: 11px;")
        self.light_value_label.hide()
        top_layout.addWidget(self.light_value_label)

        # Publish to AYON button
        self.publish_to_ayon_btn = QPushButton("Publish to AYON")
        self.publish_to_ayon_btn.setFixedHeight(28)
        self.publish_to_ayon_btn.setStyleSheet("""
            QPushButton { background-color: #10b981; color: white; border: none; border-radius: 3px; padding: 0 12px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background-color: #14ce94; }
            QPushButton:disabled { background-color: #3c414b; color: #6b6f78; }
        """)
        self.publish_to_ayon_btn.clicked.connect(self._publish_to_ayon)

        try:
            from state_manager import get_app_state
            from ayon.service import AYON_AVAILABLE
            app_state = get_app_state()
            is_standalone = app_state.standalone_mode

            if is_standalone or not AYON_AVAILABLE:
                self.publish_to_ayon_btn.setEnabled(False)
                self.publish_to_ayon_btn.setToolTip("AYON publishing is not available" if not AYON_AVAILABLE else "Not available in standalone mode")
            else:
                self.publish_to_ayon_btn.setToolTip("Publish this asset to AYON")
        except Exception as e:
            logger.warning(f"Could not initialize AYON button: {e}")
            self.publish_to_ayon_btn.setEnabled(False)
            self.publish_to_ayon_btn.setToolTip("AYON is not available")

        top_layout.addWidget(self.publish_to_ayon_btn)

        # Delete button
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setFixedHeight(28)
        self.delete_btn.setStyleSheet("""
            QPushButton { background-color: #dc2626; color: white; border: none; border-radius: 3px; padding: 0 12px; font-size: 11px; }
            QPushButton:hover { background-color: #ef4444; }
        """)
        self.delete_btn.setToolTip("Delete current file (Del)")
        self.delete_btn.clicked.connect(self._delete_current_image)
        top_layout.addWidget(self.delete_btn)

        # Bottom info bar - overlay widget (simplified, just shows filename)
        self.info_bar = QWidget(self.image_container)
        self.info_bar.setStyleSheet("background-color: transparent;")
        self.info_bar.setFixedHeight(40)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(10, 10, 10, 10)

        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        info_layout.addWidget(self.filename_label)

        self._current_3d_path = None
        self._saved_camera_state = None
        self._current_shading_mode = "textured"
        self._current_lighting_mode = "studio"
        self._current_hdri_path = None
        self._current_light_strength = 1.0

        info_layout.addStretch()

        help_label = QLabel("Navigate | Esc Back | Space Play/Pause | C Prompt | Del Delete")
        help_label.setStyleSheet("color: #888888; font-size: 10px;")
        info_layout.addWidget(help_label)

        # Position and raise overlay bars immediately
        # They'll be repositioned in resizeEvent when actual size is known
        self.top_bar.move(0, 0)
        self.info_bar.move(0, 0)
        self.top_bar.raise_()
        self.info_bar.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()
        # Delay positioning to ensure layout is complete
        QTimer.singleShot(0, self._position_overlays)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlays()

    def _position_overlays(self):
        """Position top_bar and info_bar as overlays on image_container."""
        if not hasattr(self, 'image_container'):
            return

        w = self.image_container.width()
        h = self.image_container.height()

        if w == 0 or h == 0:
            return  # Widget not yet sized

        # Lower the content stack first (helps with QWebEngineView z-order)
        if hasattr(self, 'image_stack'):
            self.image_stack.lower()

        # Top bar at top of image_container
        if hasattr(self, 'top_bar'):
            top_height = 50
            self.top_bar.setGeometry(0, 0, w, top_height)
            self.top_bar.raise_()
            self.top_bar.show()

        # Info bar at bottom of image_container (now smaller - just filename)
        if hasattr(self, 'info_bar'):
            bar_height = 40
            self.info_bar.setGeometry(0, h - bar_height, w, bar_height)
            self.info_bar.raise_()
            self.info_bar.show()

        # Video controls bar (above info bar when playing video)
        if hasattr(self, 'video_controls') and self.video_controls:
            controls_height = 56
            controls_margin = 10
            # Position just above info bar (40px from bottom)
            self.video_controls.setGeometry(
                controls_margin,
                h - bar_height - controls_height - controls_margin,
                w - 2 * controls_margin,
                controls_height
            )
            self.video_controls.raise_()
            # Visibility is managed by video playback state

    def eventFilter(self, obj, event):
        """Event filter to show video controls on mouse movement and handle click-to-play."""
        from PySide6.QtCore import QEvent
        if hasattr(self, 'video_widget') and obj == self.video_widget:
            if event.type() == QEvent.MouseMove:
                if hasattr(self, 'video_controls') and self.video_controls:
                    self.video_controls.show_controls()
            elif event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                if hasattr(self, 'video_controls') and self.video_controls:
                    self.video_controls._toggle_play()
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        """Show video controls on any mouse movement in viewer."""
        super().mouseMoveEvent(event)
        # Show controls if video is currently playing
        if hasattr(self, 'video_controls') and self.video_controls:
            if hasattr(self, 'video_widget') and self.video_widget:
                if self.image_stack.currentWidget() == self.video_widget:
                    self.video_controls.show_controls()

    def _init_glb_viewer_async(self, callback=None):
        """Initialize the GLB viewer widget asynchronously."""
        if self._glb_viewer_initialized:
            if callback:
                callback(self._has_glb_viewer)
            return

        self.message_label.setText("Initializing 3D viewer...")
        self.image_stack.setCurrentWidget(self.message_label)

        # Use QTimer to defer initialization so UI can update
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._do_init_glb_viewer(callback))

    def _do_init_glb_viewer(self, callback=None):
        """Initialize the Three.js 3D viewer widget."""
        # Add python directory to path if needed
        import sys
        import os
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python_dir = os.path.join(os.path.dirname(current_dir), 'python')
        if python_dir not in sys.path:
            sys.path.insert(0, python_dir)

        try:
            from geo.threejs_viewer import ThreeJSViewerWidget, is_threejs_viewer_available, get_prewarm_viewer
            if is_threejs_viewer_available():
                # The prewarm viewer was initialized in main window layout before window.show()
                # to warm up the Chromium GPU thread. We do NOT reparent it (causes rendering issues).
                # Instead, create a fresh viewer - it won't flash because the GPU is already warm.
                # Just consume the prewarm reference to mark it as used.
                _ = get_prewarm_viewer()  # Consume prewarm (stays in main window, keeps GPU warm)

                # Create fresh viewer - GPU thread is already initialized, no flash expected
                self.glb_viewer = ThreeJSViewerWidget()
                logger.info("Created Three.js 3D viewer (GPU pre-warmed)")
                self.glb_viewer.loadError.connect(self._on_3d_load_error)
                self.glb_viewer.modelLoaded.connect(self._on_3d_model_loaded)
                self.image_stack.addWidget(self.glb_viewer)
                self._has_glb_viewer = True
                self._glb_viewer_initialized = True
                if callback:
                    callback(True)
                return
            else:
                logger.warning("Three.js viewer not available - PySide6 WebEngine may be missing")
        except Exception as e:
            logger.error(f"Three.js viewer failed: {e}", exc_info=True)

        # No viewer available
        self._has_glb_viewer = False
        self._glb_viewer_initialized = True
        if callback:
            callback(False)

    def _load_current_image(self):
        """Load and display the current media (image, 3D model, or video)."""
        if not self.image_paths or self.current_index < 0 or self.current_index >= len(self.image_paths):
            return

        media_path = self.image_paths[self.current_index]

        try:
            ext = os.path.splitext(media_path)[1].lower()

            # Stop any playing media
            if hasattr(self, '_has_video_player') and self._has_video_player and self.media_player:
                self.media_player.stop()

            # Hide video controls by default (will be shown for video files)
            if hasattr(self, 'video_controls') and self.video_controls:
                self.video_controls.hide()

            MODEL_EXTENSIONS = {'.glb', '.gltf', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz', '.dae', '.stl', '.ply'}
            if ext in MODEL_EXTENSIONS:
                self.shading_btn.show()
                self.lighting_btn.show()
                self.light_label.show()
                self.light_slider.show()
                self.light_value_label.show()
                self._current_3d_path = media_path

                # Restore saved preferences from settings
                try:
                    from core.settings_manager import get_setting
                    self._current_shading_mode = get_setting("viewer_3d_shading_mode")
                    self._current_lighting_mode = get_setting("viewer_3d_lighting_mode")
                    self._current_hdri_path = get_setting("viewer_3d_hdri_name")
                    self._current_light_strength = get_setting("viewer_3d_light_strength") or 1.0
                    self.light_slider.setValue(int(self._current_light_strength * 100))
                    self.light_value_label.setText(f"{self._current_light_strength:.1f}x")
                except Exception:
                    pass  # Use defaults if settings unavailable

                # Update button labels
                self.shading_btn.setText(self._current_shading_mode.title())
                label_map = {"headlight": "Headlight", "studio": "Studio", "hdri": "HDRI"}
                self.lighting_btn.setText(label_map.get(self._current_lighting_mode, "Studio"))

                if not self._glb_viewer_initialized:
                    self.message_label.setText("Initializing 3D viewer...")
                    self.image_stack.setCurrentWidget(self.message_label)
                    self._pending_3d_path = media_path

                    def on_viewer_ready(available):
                        if available and hasattr(self, '_pending_3d_path'):
                            self._load_3d_model(self._pending_3d_path)
                        elif not available:
                            self.message_label.setText("3D Model Viewer Not Available\n\nInstall pyvista and pyvistaqt")
                            self.image_stack.setCurrentWidget(self.message_label)

                    self._init_glb_viewer_async(callback=on_viewer_ready)
                elif self._has_glb_viewer and self.glb_viewer:
                    self._load_3d_model(media_path)
                else:
                    self.message_label.setText("3D Model Viewer Not Available")
                    self.image_stack.setCurrentWidget(self.message_label)

            elif ext in ('.mp4', '.mov', '.avi', '.webm'):
                self.shading_btn.hide()
                self.lighting_btn.hide()
                self.light_label.hide()
                self.light_slider.hide()
                self.light_value_label.hide()
                self._current_3d_path = None
                if hasattr(self, '_has_video_player') and self._has_video_player and self.media_player and self.video_widget:
                    from PySide6.QtCore import QUrl

                    # Qt6 API: use setSource instead of setMedia
                    self.media_player.setSource(QUrl.fromLocalFile(media_path))
                    self.image_stack.setCurrentWidget(self.video_widget)
                    self.media_player.play()

                    # Show video controls
                    if hasattr(self, 'video_controls') and self.video_controls:
                        self.video_controls.show_controls()
                else:
                    self.message_label.setText("Video Player Not Available")
                    self.image_stack.setCurrentWidget(self.message_label)

            elif ext in ('.wav', '.mp3', '.flac', '.ogg'):
                # Audio file
                self.shading_btn.hide()
                self.lighting_btn.hide()
                self.light_label.hide()
                self.light_slider.hide()
                self.light_value_label.hide()
                self._current_3d_path = None

                try:
                    # Check if we already have an audio player for this file
                    if (not hasattr(self, '_current_audio_player') or
                        not self._current_audio_player or
                        getattr(self._current_audio_player, 'audio_path', None) != media_path):

                        # Stop and clean up old audio player
                        if hasattr(self, '_current_audio_player') and self._current_audio_player:
                            old_player = self._current_audio_player
                            if hasattr(old_player, 'cleanup'):
                                old_player.cleanup()
                            # Remove from stack if present
                            stack_index = self.image_stack.indexOf(old_player)
                            if stack_index >= 0:
                                self.image_stack.removeWidget(old_player)
                            old_player.deleteLater()

                        # Create new audio player
                        self._current_audio_player = AudioPlayerWidget(media_path, parent=self)
                        self.image_stack.addWidget(self._current_audio_player)

                    # Show the audio player
                    self.image_stack.setCurrentWidget(self._current_audio_player)

                except Exception as e:
                    logger.error(f"Error loading audio player: {e}")
                    self.message_label.setText(f"Audio Player Error\n\n{str(e)}")
                    self.image_stack.setCurrentWidget(self.message_label)

            elif ext == '.exr':
                self.shading_btn.hide()
                self.lighting_btn.hide()
                self.light_label.hide()
                self.light_slider.hide()
                self.light_value_label.hide()
                self._current_3d_path = None
                self.message_label.setText("EXR Preview Not Available")
                self.image_stack.setCurrentWidget(self.message_label)

            else:
                self.shading_btn.hide()
                self.lighting_btn.hide()
                self.light_label.hide()
                self.light_slider.hide()
                self.light_value_label.hide()
                self._current_3d_path = None
                pixmap = QPixmap(media_path)
                if not pixmap.isNull():
                    self.image_view.setPixmap(pixmap)
                    self.image_stack.setCurrentWidget(self.image_view)
                    self.setFocus()  # Ensure keyboard navigation works
                else:
                    self.message_label.setText("Failed to load image")
                    self.image_stack.setCurrentWidget(self.message_label)

        except Exception as e:
            self.message_label.setText(f"Error: {e}")
            self.image_stack.setCurrentWidget(self.message_label)

        self._update_info()
        self._update_like_button()

    def _load_3d_model(self, media_path):
        """Load a 3D model into the Three.js viewer."""
        if not self.glb_viewer:
            self.message_label.setText("3D viewer not available")
            self.image_stack.setCurrentWidget(self.message_label)
            return

        # Show loading message while model loads
        self.message_label.setText("Loading 3D model...")
        self.image_stack.setCurrentWidget(self.message_label)

        # Set camera distance from user settings before loading
        try:
            from core.settings_manager import get_setting
            zoom_distance = get_setting("viewer_3d_zoom_distance")
            self.glb_viewer.set_camera_distance(zoom_distance)
        except Exception:
            pass  # Use default if settings unavailable

        # Three.js viewer loads files directly via WebGL
        # Switch to viewer only after model is loaded (via modelLoaded signal)
        self.glb_viewer.load_file(media_path)

    def _on_3d_model_loaded(self, path):
        """Handle successful 3D model load - switch to the viewer."""
        self.image_stack.setCurrentWidget(self.glb_viewer)
        self.glb_viewer.setFocus()

        # Apply saved lighting/shading preferences
        if self.glb_viewer:
            try:
                from geo.threejs_viewer import ShadingMode, LightingMode

                # Apply shading mode
                if self._current_shading_mode:
                    mode_enum = ShadingMode(self._current_shading_mode)
                    self.glb_viewer.set_shading_mode(mode_enum)

                # Apply lighting mode
                if self._current_lighting_mode:
                    mode_enum = LightingMode(self._current_lighting_mode)
                    self.glb_viewer.set_lighting_mode(mode_enum)

                    # If HDRI mode and we have a saved HDRI, load it
                    if self._current_lighting_mode == "hdri" and self._current_hdri_path:
                        # Find the full path from settings
                        from core.settings_manager import get_hdri_list
                        hdri_list = get_hdri_list()
                        for hdri in hdri_list:
                            if hdri["name"] == self._current_hdri_path or hdri["path"].endswith(self._current_hdri_path):
                                self.glb_viewer.load_hdri(hdri["path"])
                                break

                # Apply light strength
                if self._current_light_strength != 1.0:
                    self.glb_viewer.set_light_strength(self._current_light_strength)

            except Exception as e:
                logger.error(f"Error applying viewer preferences: {e}")

    def _on_3d_load_error(self, error_msg):
        """Handle 3D model loading error from Three.js viewer."""
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

        self.left_btn.setEnabled(self.current_index > 0)
        self.right_btn.setEnabled(self.current_index < len(self.image_paths) - 1)

    def _next_image(self):
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._load_current_image()
            self.image_viewed.emit(self.image_paths[self.current_index])

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()
            self.image_viewed.emit(self.image_paths[self.current_index])

    def _on_back(self):
        self.closed.emit()

    def _on_fullscreen(self):
        if self.image_paths:
            self.view_fullscreen.emit(self.image_paths[self.current_index], self.current_index)

    def _on_zoom_changed(self, level):
        self.image_view.setZoomLevel(level)

    def _on_image_zoom_changed(self, level):
        self.zoom_combo.blockSignals(True)
        if level in ZoomableImageWidget.ZOOM_LEVELS:
            self.zoom_combo.setCurrentText(level)
        self.zoom_combo.blockSignals(False)

    def _show_shading_menu(self):
        """Show shading mode selection menu."""
        menu = QMenu(self)
        modes = [("Shaded", "shaded"), ("Textured", "textured"), ("Wireframe", "wireframe")]

        for label, mode in modes:
            action = menu.addAction(label)
            action.setData(mode)
            if mode == self._current_shading_mode:
                action.setCheckable(True)
                action.setChecked(True)

        action = menu.exec_(self.shading_btn.mapToGlobal(
            self.shading_btn.rect().bottomLeft()))

        if action and action.data():
            self._set_shading_mode(action.data())

    def _show_lighting_menu(self):
        """Show lighting mode selection menu."""
        menu = QMenu(self)

        # Basic lighting modes
        modes = [("Headlight", "headlight"), ("Studio (3-Point)", "studio")]
        for label, mode in modes:
            action = menu.addAction(label)
            action.setData(("mode", mode))
            if mode == self._current_lighting_mode:
                action.setCheckable(True)
                action.setChecked(True)

        # HDRI submenu (only if HDRIs are configured)
        try:
            from core.settings_manager import get_hdri_list
            hdri_list = get_hdri_list()
            if hdri_list:
                hdri_menu = menu.addMenu("HDRI")
                for hdri in hdri_list:
                    action = hdri_menu.addAction(hdri["name"])
                    action.setData(("hdri", hdri["path"]))
                    if (self._current_lighting_mode == "hdri" and
                        self._current_hdri_path == hdri["path"]):
                        action.setCheckable(True)
                        action.setChecked(True)
        except Exception as e:
            logger.error(f"Error loading HDRI list: {e}")

        action = menu.exec_(self.lighting_btn.mapToGlobal(
            self.lighting_btn.rect().bottomLeft()))

        if action and action.data():
            data_type, value = action.data()
            if data_type == "mode":
                self._set_lighting_mode(value)
            elif data_type == "hdri":
                self._set_lighting_mode("hdri")
                self._load_hdri(value)

    def _set_shading_mode(self, mode):
        """Set shading mode on the viewer."""
        self._current_shading_mode = mode
        self.shading_btn.setText(mode.title())

        if self.glb_viewer:
            try:
                from geo.threejs_viewer import ShadingMode
                mode_enum = ShadingMode(mode)
                self.glb_viewer.set_shading_mode(mode_enum)
            except Exception as e:
                logger.error(f"Error setting shading mode: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            set_setting("viewer_3d_shading_mode", mode, verbose=False)
        except Exception:
            pass

    def _set_lighting_mode(self, mode):
        """Set lighting mode on the viewer."""
        self._current_lighting_mode = mode
        label_map = {"headlight": "Headlight", "studio": "Studio", "hdri": "HDRI"}
        self.lighting_btn.setText(label_map.get(mode, mode.title()))

        if self.glb_viewer:
            try:
                from geo.threejs_viewer import LightingMode
                mode_enum = LightingMode(mode)
                self.glb_viewer.set_lighting_mode(mode_enum)
            except Exception as e:
                logger.error(f"Error setting lighting mode: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            set_setting("viewer_3d_lighting_mode", mode, verbose=False)
        except Exception:
            pass

    def _load_hdri(self, hdri_path):
        """Load an HDRI environment map."""
        self._current_hdri_path = hdri_path

        if self.glb_viewer:
            try:
                self.glb_viewer.load_hdri(hdri_path)
            except Exception as e:
                logger.error(f"Error loading HDRI: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            import os
            set_setting("viewer_3d_hdri_name", os.path.basename(hdri_path), verbose=False)
        except Exception:
            pass

    def _on_light_strength_changed(self, value):
        """Handle light strength slider changes."""
        strength = value / 100.0
        self._current_light_strength = strength
        self.light_value_label.setText(f"{strength:.1f}x")

        if self.glb_viewer:
            try:
                self.glb_viewer.set_light_strength(strength)
            except Exception as e:
                logger.error(f"Error setting light strength: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            set_setting("viewer_3d_light_strength", strength, verbose=False)
        except Exception:
            pass

    def _copy_prompt(self):
        """Copy prompt for current image to clipboard."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.metadata import get_item_metadata
            metadata = get_item_metadata(output_dir, filename)
            if metadata and metadata.get('prompt'):
                clipboard = QApplication.clipboard()
                clipboard.setText(metadata['prompt'], mode=clipboard.Mode.Clipboard)
                self.filename_label.setText(f"{filename} - Prompt copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No prompt available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Error copying prompt: {e}")

    def _copy_settings(self):
        """Apply all settings for current image to the ComfyUI tab."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.metadata import get_item_metadata
            metadata = get_item_metadata(output_dir, filename)
            if metadata:
                self.copy_settings_requested.emit(metadata)
                self.filename_label.setText(f"{filename} - Settings copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No settings available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Error applying settings: {e}")

    def _publish_to_ayon(self):
        """Publish this image to AYON."""
        parent_window = get_active_window()

        try:
            from comfyui.ayon_publisher import publish_comfyui_asset_to_ayon
            image_path = self.image_paths[self.current_index]
            success = publish_comfyui_asset_to_ayon(
                file_path=image_path,
                parent_widget=parent_window,
                output_dir=self.output_dir
            )
            if success:
                logger.info(f"Successfully published image to AYON: {image_path}")
        except Exception as e:
            logger.error(f"Failed to publish image to AYON: {e}", exc_info=True)
            show_error("Publish Error", f"Failed to publish image to AYON:\n\n{str(e)}", parent_window)

    def keyPressEvent(self, event):
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
        elif key == Qt.Key_Space:
            # Toggle play/pause if video is showing
            if (hasattr(self, 'video_controls') and self.video_controls
                    and hasattr(self, 'video_widget') and self.video_widget
                    and self.image_stack.currentWidget() == self.video_widget):
                self.video_controls._toggle_play()
            else:
                super().keyPressEvent(event)
        elif key == Qt.Key_C:
            self._copy_prompt()
        elif key == Qt.Key_S:
            self._copy_settings()
        elif key == Qt.Key_F:
            self._on_fullscreen()
        elif key == Qt.Key_Delete:
            self._delete_current_image()
        elif key == Qt.Key_L:
            self._toggle_like()
        else:
            super().keyPressEvent(event)

    def _toggle_like(self):
        """Toggle like status for current image."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        is_liked = self._favorites_manager.toggle_like(path)
        self._update_like_button_style(is_liked)
        self.like_toggled.emit(path, is_liked)

    def _update_like_button(self):
        """Update like button based on current image's like status."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        is_liked = self._favorites_manager.is_liked(path)
        self._update_like_button_style(is_liked)

    def _update_like_button_style(self, is_liked):
        """Update like button appearance based on liked state."""
        if is_liked:
            self.like_btn.setText("♥")
            self.like_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(239, 68, 68, 0.9);
                    color: white;
                    border: none;
                    border-radius: 16px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: rgba(239, 68, 68, 1.0);
                }
            """)
        else:
            self.like_btn.setText("♡")
            self.like_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(60, 60, 60, 0.8);
                    color: rgba(255, 255, 255, 0.7);
                    border: none;
                    border-radius: 16px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: rgba(239, 68, 68, 0.7);
                    color: white;
                }
            """)

    def _delete_current_image(self):
        """Delete the current image file after confirmation."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        if confirm_action("Delete File", f"Are you sure you want to delete:\n{filename}?", self):
            try:
                os.remove(image_path)
                deleted_path = image_path
                self.image_paths.pop(self.current_index)

                if not self.image_paths:
                    self.image_deleted.emit(deleted_path)
                    self._on_back()
                    return

                if self.current_index >= len(self.image_paths):
                    self.current_index = len(self.image_paths) - 1

                self._load_current_image()
                self.image_deleted.emit(deleted_path)
                self.filename_label.setText(f"Deleted: {filename}")
                QTimer.singleShot(1500, self._update_info)

            except Exception as e:
                show_warning("Delete Error", f"Failed to delete file:\n{str(e)}", self)

    def _show_context_menu(self, pos):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)
        menu = QMenu(self)

        # Like option (at the top for quick access)
        if self._favorites_manager:
            is_liked = self._favorites_manager.is_liked(image_path)
            like_action = menu.addAction("♥ Unlike (L)" if is_liked else "♡ Like (L)")
            like_action.triggered.connect(self._toggle_like)

            # Groups submenu
            groups_menu = menu.addMenu("Add to Group")
            groups = self._favorites_manager.get_groups()
            item_group_ids = set(self._favorites_manager.get_item_groups(image_path))

            for group in groups:
                action = groups_menu.addAction(f"● {group.name}")
                action.setCheckable(True)
                action.setChecked(group.group_id in item_group_ids)
                action.triggered.connect(
                    lambda checked, gid=group.group_id: self._toggle_group_membership(gid)
                )

            if groups:
                groups_menu.addSeparator()

            new_group_action = groups_menu.addAction("+ New Group...")
            new_group_action.triggered.connect(self._create_new_group)

            menu.addSeparator()

        # View options
        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(lambda: self._open_folder(image_path))

        # Add to Canvas
        add_to_canvas_action = menu.addAction("Add to Canvas")
        add_to_canvas_action.triggered.connect(lambda: self._add_to_canvas(image_path))

        # View Input option (for outputs that have source images)
        metadata = self._get_metadata()
        input_image = metadata.get('input_image')
        input_path = os.path.join(output_dir, input_image) if input_image else None
        has_input = bool(input_path and os.path.exists(input_path))
        view_input_action = menu.addAction("View Input")
        view_input_action.triggered.connect(lambda: self._view_input(input_path))
        view_input_action.setEnabled(has_input)
        if not has_input and input_image:
            view_input_action.setText("View Input (not found)")

        menu.addSeparator()

        # Properties
        properties_action = menu.addAction("Properties")
        properties_action.triggered.connect(self._show_properties)

        menu.addSeparator()

        # Copy/Apply options
        has_settings = bool(metadata.get('workflow_preset') or metadata.get('editable_values'))
        apply_settings_action = menu.addAction("Apply Settings (S)")
        apply_settings_action.triggered.connect(self._copy_settings)
        apply_settings_action.setEnabled(has_settings)
        if not has_settings:
            apply_settings_action.setText("Apply Settings (no metadata)")

        prompt = metadata.get('prompt', '')
        copy_prompt_action = menu.addAction("Copy Prompt (C)")
        copy_prompt_action.triggered.connect(self._copy_prompt)
        copy_prompt_action.setEnabled(bool(prompt))

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path(image_path))

        # Publish to AYON
        menu.addSeparator()
        publish_action = menu.addAction("Publish to AYON")
        publish_action.triggered.connect(self._publish_to_ayon)

        # Delete
        menu.addSeparator()
        delete_action = menu.addAction("Delete (Del)")
        delete_action.triggered.connect(self._delete_current_image)

        menu.exec_(self.image_view.mapToGlobal(pos))

    def _get_metadata(self):
        """Get metadata for current image."""
        if not self.image_paths:
            return {}
        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)
        try:
            from comfyui.metadata import get_item_metadata
            return get_item_metadata(output_dir, filename) or {}
        except Exception as e:
            logger.debug(f"Could not load metadata: {e}")
            return {}

    def _toggle_group_membership(self, group_id):
        """Toggle group membership for current image."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        item_groups = set(self._favorites_manager.get_item_groups(path))
        if group_id in item_groups:
            self._favorites_manager.remove_from_group(path, group_id)
        else:
            self._favorites_manager.add_to_group(path, group_id)

    def _create_new_group(self):
        """Create a new group and add current image to it."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        try:
            from dialogs import QuickGroupDialog
            dialog = QuickGroupDialog(item_count=1, parent=self)
            if dialog.exec() == dialog.Accepted:
                name, color = dialog.get_result()
                group = self._favorites_manager.create_group(name, color)
                if group:
                    self._favorites_manager.add_to_group(path, group.group_id)
        except Exception as e:
            logger.error(f"Error creating group: {e}")

    def _add_to_canvas(self, image_path):
        """Add image to canvas via event bus."""
        if EVENT_BUS_AVAILABLE and pipeline_events:
            pipeline_events.add_to_canvas.emit(image_path)
            self.filename_label.setText(f"{os.path.basename(image_path)} - Added to canvas!")
            QTimer.singleShot(1500, self._update_info)

    def _view_input(self, input_path):
        """View the input/source image."""
        if not input_path or not os.path.exists(input_path):
            return
        # Navigate to the input image in the current viewer
        if input_path in self.image_paths:
            self.current_index = self.image_paths.index(input_path)
            self._load_current_image()
        else:
            # Open in a new viewer if not in current list
            if EVENT_BUS_AVAILABLE and pipeline_events:
                pipeline_events.view_input_image.emit(input_path)

    def _show_properties(self):
        """Show properties dialog for current image."""
        if not self.image_paths:
            return
        image_path = self.image_paths[self.current_index]
        output_dir = self.output_dir or os.path.dirname(image_path)
        try:
            from properties_dialog import PropertiesDialog
            from core.state_manager import app_state

            metadata = self._get_metadata()
            dialog = PropertiesDialog(
                image_path,
                output_dir,
                metadata=metadata,
                parent=self,
                show_comfyui_features=app_state.has_elevated_access
            )
            dialog.exec()
        except Exception as e:
            logger.error(f"Error showing properties: {e}")

    def _open_folder(self, image_path):
        import subprocess
        import os
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.Popen(f'explorer /select,"{image_path}"', creationflags=creationflags)
        except Exception as e:
            logger.error(f"Error opening folder: {e}")

    def _copy_path(self, image_path):
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
    - S: Apply settings to ComfyUI tab (if available)
    - Delete: Delete current file
    - L: Toggle like status
    """
    closed = Signal()
    copy_settings_requested = Signal(dict)
    image_deleted = Signal(str)  # Emitted when a file is deleted (path)
    image_viewed = Signal(str)  # Emitted when navigating to an image (path)
    like_toggled = Signal(str, bool)  # Emitted when like status is toggled (path, is_liked)

    def __init__(self, image_paths, start_index=0, output_dir=None, parent=None):
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.current_index = start_index
        self.output_dir = output_dir
        self._show_info = True
        self._favorites_manager = None

        self._setup_ui()
        self._load_current_image()

    def set_favorites_manager(self, manager):
        """Set the favorites manager for like functionality."""
        self._favorites_manager = manager

    def _setup_ui(self):
        """Set up the fullscreen UI."""
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet("background-color: #1a1a1a;")

        # Enable mouse tracking to show video controls on mouse movement
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.image_stack, stretch=1)

        self.image_view = ZoomableImageWidget()
        self.image_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_view.customContextMenuRequested.connect(self._show_context_menu)
        self.image_view.zoom_changed.connect(self._on_image_zoom_changed)
        self.image_stack.addWidget(self.image_view)

        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("background-color: #1a1a1a; color: #888888; font-size: 16px;")
        self.image_stack.addWidget(self.message_label)

        # Video Player (uses VideoSinkWidget for software rendering
        #    so overlay controls can draw on top of the video)
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

            self.video_widget = VideoSinkWidget()
            self.media_player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.media_player.setAudioOutput(self.audio_output)
            self.media_player.setVideoSink(self.video_widget.videoSink)

            # Enable mouse tracking
            self.video_widget.setMouseTracking(True)
            self.video_widget.installEventFilter(self)

            self.image_stack.addWidget(self.video_widget)
            self._has_video_player = True

            # Create video control bar (overlay widget)
            self.video_controls = VideoControlBar(self.media_player, parent=self)
            self.video_controls.hide()
        except Exception as e:
            logger.warning(f"Video player not available: {e}")
            self._has_video_player = False
            self.video_widget = None
            self.media_player = None
            self.video_controls = None

        # Info bar - overlays on content
        self.info_bar = QWidget(self)  # Child of self for overlay
        self.info_bar.setStyleSheet("QWidget { background-color: transparent; }")
        self.info_bar.setFixedHeight(60)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(20, 15, 20, 15)

        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("color: #ffffff; font-size: 14px;")
        info_layout.addWidget(self.filename_label)

        info_layout.addStretch()

        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("color: #888888; font-size: 12px;")
        info_layout.addWidget(self.counter_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(ZoomableImageWidget.ZOOM_LEVELS)
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.setFixedWidth(80)
        self.zoom_combo.setStyleSheet("""
            QComboBox { background-color: #2a2a2a; color: #cccccc; border: 1px solid #555555; border-radius: 3px; padding: 3px 8px; font-size: 11px; }
            QComboBox:hover { border-color: #4a9eff; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #888888; margin-right: 5px; }
            QComboBox QAbstractItemView { background-color: #2a2a2a; color: #cccccc; selection-background-color: #4a9eff; border: 1px solid #555555; }
        """)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        info_layout.addWidget(self.zoom_combo)

        self.help_label = QLabel("Navigate | Esc Close | Space Play/Info | C Prompt | Del Delete")
        self.help_label.setStyleSheet("color: #888888; font-size: 10px; margin-left: 20px;")
        info_layout.addWidget(self.help_label)

        self.info_bar.raise_()

        self._create_nav_buttons()

    def _create_nav_buttons(self):
        """Create navigation buttons on the sides."""
        self.left_btn = QPushButton("<", self)
        self.left_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 30px; padding: 20px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
        """)
        self.left_btn.setCursor(Qt.PointingHandCursor)
        self.left_btn.clicked.connect(self._prev_image)

        self.right_btn = QPushButton(">", self)
        self.right_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 30px; padding: 20px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
        """)
        self.right_btn.setCursor(Qt.PointingHandCursor)
        self.right_btn.clicked.connect(self._next_image)

    def showEvent(self, event):
        super().showEvent(event)
        self.showFullScreen()
        self._position_overlays()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlays()

    def eventFilter(self, obj, event):
        """Event filter to show video controls on mouse movement and handle click-to-play."""
        from PySide6.QtCore import QEvent
        if hasattr(self, 'video_widget') and obj == self.video_widget:
            if event.type() == QEvent.MouseMove:
                if hasattr(self, 'video_controls') and self.video_controls:
                    self.video_controls.show_controls()
            elif event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                if hasattr(self, 'video_controls') and self.video_controls:
                    self.video_controls._toggle_play()
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        """Show video controls on any mouse movement in viewer."""
        super().mouseMoveEvent(event)
        # Show controls if video is currently playing
        if hasattr(self, 'video_controls') and self.video_controls:
            if hasattr(self, 'video_widget') and self.video_widget:
                if self.image_stack.currentWidget() == self.video_widget:
                    self.video_controls.show_controls()

    def _position_overlays(self):
        """Position info bar and nav buttons as overlays."""
        # Lower the content first
        if hasattr(self, 'image_stack'):
            self.image_stack.lower()

        # Video controls bar (above info bar when playing video)
        bar_height = self.info_bar.height()
        if hasattr(self, 'video_controls') and self.video_controls:
            controls_height = 56
            controls_margin = 20
            # Position just above info bar
            self.video_controls.setGeometry(
                controls_margin,
                self.height() - bar_height - controls_height - controls_margin,
                self.width() - 2 * controls_margin,
                controls_height
            )
            self.video_controls.raise_()

        # Position info_bar at bottom
        self.info_bar.setGeometry(0, self.height() - bar_height, self.width(), bar_height)
        self.info_bar.raise_()
        self.info_bar.show()

        # Position nav buttons centered vertically (accounting for info bar)
        btn_width = 60
        btn_height = 100
        margin = 20
        center_y = (self.height() - bar_height - btn_height) // 2

        self.left_btn.setGeometry(margin, center_y, btn_width, btn_height)
        self.right_btn.setGeometry(self.width() - margin - btn_width, center_y, btn_width, btn_height)

        self.left_btn.setVisible(self.current_index > 0)
        self.right_btn.setVisible(self.current_index < len(self.image_paths) - 1)

    def _load_current_image(self):
        if not self.image_paths or self.current_index < 0 or self.current_index >= len(self.image_paths):
            return

        media_path = self.image_paths[self.current_index]

        try:
            ext = os.path.splitext(media_path)[1].lower()

            # Stop any playing media
            if hasattr(self, '_has_video_player') and self._has_video_player and self.media_player:
                self.media_player.stop()

            # Hide video controls by default
            if hasattr(self, 'video_controls') and self.video_controls:
                self.video_controls.hide()

            if ext in ('.mp4', '.mov', '.avi', '.webm'):
                # Video file
                if hasattr(self, '_has_video_player') and self._has_video_player and self.media_player and self.video_widget:
                    from PySide6.QtCore import QUrl
                    self.media_player.setSource(QUrl.fromLocalFile(media_path))
                    self.image_stack.setCurrentWidget(self.video_widget)
                    self.media_player.play()

                    # Show video controls
                    if hasattr(self, 'video_controls') and self.video_controls:
                        self.video_controls.show_controls()
                else:
                    self.message_label.setText("Video Player Not Available")
                    self.image_stack.setCurrentWidget(self.message_label)

            elif ext in ('.wav', '.mp3', '.flac', '.ogg'):
                # Audio file
                try:
                    # Check if we already have an audio player for this file
                    if (not hasattr(self, '_current_audio_player') or
                        not self._current_audio_player or
                        getattr(self._current_audio_player, 'audio_path', None) != media_path):

                        # Stop and clean up old audio player
                        if hasattr(self, '_current_audio_player') and self._current_audio_player:
                            old_player = self._current_audio_player
                            if hasattr(old_player, 'cleanup'):
                                old_player.cleanup()
                            stack_index = self.image_stack.indexOf(old_player)
                            if stack_index >= 0:
                                self.image_stack.removeWidget(old_player)
                            old_player.deleteLater()

                        # Create new audio player
                        self._current_audio_player = AudioPlayerWidget(media_path, parent=self)
                        self.image_stack.addWidget(self._current_audio_player)

                    # Show the audio player
                    self.image_stack.setCurrentWidget(self._current_audio_player)

                except Exception as e:
                    logger.error(f"Error loading audio player: {e}")
                    self.message_label.setText(f"Audio Player Error\n\n{str(e)}")
                    self.image_stack.setCurrentWidget(self.message_label)

            elif ext == '.exr':
                self.message_label.setText("EXR Preview Not Available")
                self.image_stack.setCurrentWidget(self.message_label)

            else:
                # Regular image
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
        self._position_nav_buttons()

    def _update_info(self):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        self.filename_label.setText(filename)
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.image_paths)}")
        self.info_bar.setVisible(self._show_info)

    def _next_image(self):
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._load_current_image()
            self.image_viewed.emit(self.image_paths[self.current_index])

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()
            self.image_viewed.emit(self.image_paths[self.current_index])

    def _on_zoom_changed(self, level):
        self.image_view.setZoomLevel(level)

    def _on_image_zoom_changed(self, level):
        self.zoom_combo.blockSignals(True)
        if level in ZoomableImageWidget.ZOOM_LEVELS:
            self.zoom_combo.setCurrentText(level)
        self.zoom_combo.blockSignals(False)

    def _copy_prompt(self):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.metadata import get_item_metadata
            metadata = get_item_metadata(output_dir, filename)
            if metadata and metadata.get('prompt'):
                clipboard = QApplication.clipboard()
                clipboard.setText(metadata['prompt'], mode=clipboard.Mode.Clipboard)
                self.filename_label.setText(f"{filename} - Prompt copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No prompt available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Error copying prompt: {e}")

    def _copy_settings(self):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.metadata import get_item_metadata
            metadata = get_item_metadata(output_dir, filename)
            if metadata:
                self.copy_settings_requested.emit(metadata)
                self.filename_label.setText(f"{filename} - Settings copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No settings available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Error applying settings: {e}")

    def keyPressEvent(self, event):
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
            # Toggle play/pause if video is showing, otherwise toggle info display
            if (hasattr(self, 'video_controls') and self.video_controls
                    and hasattr(self, 'video_widget') and self.video_widget
                    and self.image_stack.currentWidget() == self.video_widget):
                self.video_controls._toggle_play()
            else:
                self._show_info = not self._show_info
                self._update_info()
        elif key == Qt.Key_C:
            self._copy_prompt()
        elif key == Qt.Key_S:
            self._copy_settings()
        elif key == Qt.Key_Delete:
            self._delete_current_image()
        elif key == Qt.Key_L:
            self._toggle_like()
        else:
            super().keyPressEvent(event)

    def _toggle_like(self):
        """Toggle like status for current image."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        is_liked = self._favorites_manager.toggle_like(path)
        self.like_toggled.emit(path, is_liked)
        # Show feedback in info label
        status = "Liked" if is_liked else "Unliked"
        self.filename_label.setText(f"{os.path.basename(path)} - {status}")
        QTimer.singleShot(1500, self._update_info)

    def _delete_current_image(self):
        """Delete the current file after confirmation."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        if confirm_action("Delete File", f"Are you sure you want to delete:\n{filename}?", self):
            try:
                os.remove(image_path)
                deleted_path = image_path
                self.image_paths.pop(self.current_index)

                if not self.image_paths:
                    self.image_deleted.emit(deleted_path)
                    self.close()
                    return

                if self.current_index >= len(self.image_paths):
                    self.current_index = len(self.image_paths) - 1

                self._load_current_image()
                self.image_deleted.emit(deleted_path)
                self.filename_label.setText(f"Deleted: {filename}")
                QTimer.singleShot(1500, self._update_info)

            except Exception as e:
                show_warning("Delete Error", f"Failed to delete file:\n{str(e)}", self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            click_x = event.pos().x()
            margin = 100
            if margin < click_x < self.width() - margin:
                pass
        super().mousePressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def _show_context_menu(self, pos):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)
        menu = QMenu(self)

        # Like option (at the top for quick access)
        if self._favorites_manager:
            is_liked = self._favorites_manager.is_liked(image_path)
            like_action = menu.addAction("♥ Unlike (L)" if is_liked else "♡ Like (L)")
            like_action.triggered.connect(self._toggle_like)

            # Groups submenu
            groups_menu = menu.addMenu("Add to Group")
            groups = self._favorites_manager.get_groups()
            item_group_ids = set(self._favorites_manager.get_item_groups(image_path))

            for group in groups:
                action = groups_menu.addAction(f"● {group.name}")
                action.setCheckable(True)
                action.setChecked(group.group_id in item_group_ids)
                action.triggered.connect(
                    lambda checked, gid=group.group_id: self._toggle_group_membership(gid)
                )

            if groups:
                groups_menu.addSeparator()

            new_group_action = groups_menu.addAction("+ New Group...")
            new_group_action.triggered.connect(self._create_new_group)

            menu.addSeparator()

        # View options
        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(lambda: self._open_folder(image_path))

        # Add to Canvas
        add_to_canvas_action = menu.addAction("Add to Canvas")
        add_to_canvas_action.triggered.connect(lambda: self._add_to_canvas(image_path))

        # View Input option (for outputs that have source images)
        metadata = self._get_metadata()
        input_image = metadata.get('input_image')
        input_path = os.path.join(output_dir, input_image) if input_image else None
        has_input = bool(input_path and os.path.exists(input_path))
        view_input_action = menu.addAction("View Input")
        view_input_action.triggered.connect(lambda: self._view_input(input_path))
        view_input_action.setEnabled(has_input)
        if not has_input and input_image:
            view_input_action.setText("View Input (not found)")

        menu.addSeparator()

        # Properties
        properties_action = menu.addAction("Properties")
        properties_action.triggered.connect(self._show_properties)

        menu.addSeparator()

        # Copy/Apply options
        has_settings = bool(metadata.get('workflow_preset') or metadata.get('editable_values'))
        apply_settings_action = menu.addAction("Apply Settings (S)")
        apply_settings_action.triggered.connect(self._copy_settings)
        apply_settings_action.setEnabled(has_settings)
        if not has_settings:
            apply_settings_action.setText("Apply Settings (no metadata)")

        prompt = metadata.get('prompt', '')
        copy_prompt_action = menu.addAction("Copy Prompt (C)")
        copy_prompt_action.triggered.connect(self._copy_prompt)
        copy_prompt_action.setEnabled(bool(prompt))

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path(image_path))

        # Publish to AYON
        menu.addSeparator()
        publish_action = menu.addAction("Publish to AYON")
        publish_action.triggered.connect(self._publish_to_ayon)

        # Delete
        menu.addSeparator()
        delete_action = menu.addAction("Delete (Del)")
        delete_action.triggered.connect(self._delete_current_image)

        menu.exec_(self.image_view.mapToGlobal(pos))

    def _get_metadata(self):
        """Get metadata for current image."""
        if not self.image_paths:
            return {}
        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)
        try:
            from comfyui.metadata import get_item_metadata
            return get_item_metadata(output_dir, filename) or {}
        except Exception as e:
            logger.debug(f"Could not load metadata: {e}")
            return {}

    def _toggle_group_membership(self, group_id):
        """Toggle group membership for current image."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        item_groups = set(self._favorites_manager.get_item_groups(path))
        if group_id in item_groups:
            self._favorites_manager.remove_from_group(path, group_id)
        else:
            self._favorites_manager.add_to_group(path, group_id)

    def _create_new_group(self):
        """Create a new group and add current image to it."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        try:
            from dialogs import QuickGroupDialog
            dialog = QuickGroupDialog(item_count=1, parent=self)
            if dialog.exec() == dialog.Accepted:
                name, color = dialog.get_result()
                group = self._favorites_manager.create_group(name, color)
                if group:
                    self._favorites_manager.add_to_group(path, group.group_id)
        except Exception as e:
            logger.error(f"Error creating group: {e}")

    def _add_to_canvas(self, image_path):
        """Add image to canvas via event bus."""
        if EVENT_BUS_AVAILABLE and pipeline_events:
            pipeline_events.add_to_canvas.emit(image_path)
            self.filename_label.setText(f"{os.path.basename(image_path)} - Added to canvas!")
            QTimer.singleShot(1500, self._update_info)

    def _view_input(self, input_path):
        """View the input/source image."""
        if not input_path or not os.path.exists(input_path):
            return
        # Navigate to the input image in the current viewer
        if input_path in self.image_paths:
            self.current_index = self.image_paths.index(input_path)
            self._load_current_image()
        else:
            # Open in a new viewer if not in current list
            if EVENT_BUS_AVAILABLE and pipeline_events:
                pipeline_events.view_input_image.emit(input_path)

    def _show_properties(self):
        """Show properties dialog for current image."""
        if not self.image_paths:
            return
        image_path = self.image_paths[self.current_index]
        output_dir = self.output_dir or os.path.dirname(image_path)
        try:
            from properties_dialog import PropertiesDialog
            from core.state_manager import app_state

            metadata = self._get_metadata()
            dialog = PropertiesDialog(
                image_path,
                output_dir,
                metadata=metadata,
                parent=self,
                show_comfyui_features=app_state.has_elevated_access
            )
            dialog.exec()
        except Exception as e:
            logger.error(f"Error showing properties: {e}")

    def _publish_to_ayon(self):
        """Publish this image to AYON."""
        parent_window = get_active_window()

        try:
            from comfyui.ayon_publisher import publish_comfyui_asset_to_ayon
            image_path = self.image_paths[self.current_index]
            success = publish_comfyui_asset_to_ayon(
                file_path=image_path,
                parent_widget=parent_window,
                output_dir=self.output_dir
            )
            if success:
                logger.info(f"Successfully published image to AYON: {image_path}")
                self.filename_label.setText(f"{os.path.basename(image_path)} - Published!")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Failed to publish image to AYON: {e}", exc_info=True)
            show_error("Publish Error", f"Failed to publish image to AYON:\n\n{str(e)}", parent_window)

    def _open_folder(self, image_path):
        import subprocess
        import os
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.Popen(f'explorer /select,"{image_path}"', creationflags=creationflags)
        except Exception as e:
            logger.error(f"Error opening folder: {e}")

    def _copy_path(self, image_path):
        clipboard = QApplication.clipboard()
        clipboard.setText(image_path)
        self.filename_label.setText(f"{os.path.basename(image_path)} - Path copied!")
        QTimer.singleShot(1500, self._update_info)
