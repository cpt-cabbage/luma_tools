"""
Animation controller and transport bar for 3D model viewer.

Provides animation playback control with:
- Play/pause/stop controls
- Timeline seeking
- Speed adjustment
- Loop toggle
- Frame stepping
"""

from typing import Optional, Dict, List

import numpy as np

from PySide6.QtCore import Qt, Signal, QTimer, QObject
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QSlider, QComboBox
)

from models.loader import Animation
from models.animation_utils import interpolate_bone_animation, compose_transform


class AnimationController(QObject):
    """
    Controls animation playback for 3D models.

    Signals:
        time_changed: Emitted when current time changes (time_seconds, time_normalized)
        animation_changed: Emitted when active animation changes
        playback_state_changed: Emitted when play/pause state changes
    """

    time_changed = Signal(float, float)  # (time_seconds, time_normalized 0-1)
    animation_changed = Signal(str)  # animation name
    playback_state_changed = Signal(bool)  # is_playing

    SPEED_OPTIONS = [0.25, 0.5, 1.0, 2.0, 4.0]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._animations: List[Animation] = []
        self._current_animation: Optional[Animation] = None
        self._current_time: float = 0.0
        self._is_playing: bool = False
        self._loop: bool = True
        self._speed: float = 1.0

        # Playback timer
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 FPS
        self._timer.timeout.connect(self._update_time)

    def set_animations(self, animations: List[Animation]):
        """Set available animations."""
        self._animations = animations
        if animations:
            self.set_animation(animations[0].name)
        else:
            self._current_animation = None
            self._current_time = 0.0

    def set_animation(self, name: str):
        """Set the active animation by name."""
        for anim in self._animations:
            if anim.name == name:
                self._current_animation = anim
                self._current_time = 0.0
                self.animation_changed.emit(name)
                self.time_changed.emit(0.0, 0.0)
                return

    @property
    def animation_names(self) -> List[str]:
        """Get list of animation names."""
        return [a.name for a in self._animations]

    @property
    def current_animation(self) -> Optional[Animation]:
        return self._current_animation

    @property
    def duration(self) -> float:
        """Duration of current animation in seconds."""
        if self._current_animation:
            return self._current_animation.duration
        return 0.0

    @property
    def current_time(self) -> float:
        return self._current_time

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def loop(self) -> bool:
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, value: float):
        self._speed = max(0.1, min(10.0, value))

    def play(self):
        """Start playback."""
        if not self._current_animation:
            return
        self._is_playing = True
        self._timer.start()
        self.playback_state_changed.emit(True)

    def pause(self):
        """Pause playback."""
        self._is_playing = False
        self._timer.stop()
        self.playback_state_changed.emit(False)

    def toggle_play(self):
        """Toggle play/pause."""
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def stop(self):
        """Stop playback and reset to start."""
        self.pause()
        self.seek(0.0)

    def seek(self, time_seconds: float):
        """Seek to a specific time."""
        if not self._current_animation:
            return

        duration = self._current_animation.duration
        self._current_time = max(0.0, min(duration, time_seconds))
        normalized = self._current_time / duration if duration > 0 else 0.0
        self.time_changed.emit(self._current_time, normalized)

    def seek_normalized(self, normalized: float):
        """Seek to a normalized position (0-1)."""
        if self._current_animation:
            self.seek(normalized * self._current_animation.duration)

    def step_forward(self):
        """Step forward one frame."""
        if self._current_animation:
            frame_time = 1.0 / self._current_animation.fps
            self.seek(self._current_time + frame_time)

    def step_backward(self):
        """Step backward one frame."""
        if self._current_animation:
            frame_time = 1.0 / self._current_animation.fps
            self.seek(self._current_time - frame_time)

    def go_to_start(self):
        """Go to the start of the animation."""
        self.seek(0.0)

    def go_to_end(self):
        """Go to the end of the animation."""
        if self._current_animation:
            self.seek(self._current_animation.duration)

    def _update_time(self):
        """Update time during playback."""
        if not self._current_animation or not self._is_playing:
            return

        # Advance time
        dt = 0.016 * self._speed  # ~60 FPS * speed
        new_time = self._current_time + dt
        duration = self._current_animation.duration

        if new_time >= duration:
            if self._loop:
                new_time = new_time % duration
            else:
                new_time = duration
                self.pause()

        self._current_time = new_time
        normalized = self._current_time / duration if duration > 0 else 0.0
        self.time_changed.emit(self._current_time, normalized)

    def get_bone_transforms(self) -> Dict[str, np.ndarray]:
        """
        Get bone transformation matrices for the current time.

        Returns:
            Dict mapping bone name to 4x4 transformation matrix
        """
        transforms = {}

        if not self._current_animation:
            return transforms

        for bone_name, bone_anim in self._current_animation.bone_animations.items():
            pos, rot, scale = interpolate_bone_animation(bone_anim, self._current_time)
            transforms[bone_name] = compose_transform(pos, rot, scale)

        return transforms


class AnimationTransportBar(QWidget):
    """
    Transport controls for animation playback.

    Provides play/pause, stop, step, loop, speed, and timeline controls.
    """

    def __init__(self, controller: AnimationController, parent=None):
        super().__init__(parent)

        self._controller = controller
        self._dragging_slider = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Button style
        btn_style = """
            QPushButton {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 14px;
                min-width: 28px;
            }
            QPushButton:hover { background-color: #4a5160; }
            QPushButton:pressed { background-color: #2a2e36; }
            QPushButton:checked { background-color: #4a9eff; }
            QPushButton:disabled { background-color: #2a2e36; color: #666; }
        """

        # Go to start
        self._start_btn = QPushButton("|◀")
        self._start_btn.setToolTip("Go to start")
        self._start_btn.setStyleSheet(btn_style)
        layout.addWidget(self._start_btn)

        # Step backward
        self._prev_btn = QPushButton("◀◀")
        self._prev_btn.setToolTip("Step backward")
        self._prev_btn.setStyleSheet(btn_style)
        layout.addWidget(self._prev_btn)

        # Play/Pause
        self._play_btn = QPushButton("▶")
        self._play_btn.setToolTip("Play/Pause")
        self._play_btn.setStyleSheet(btn_style)
        self._play_btn.setMinimumWidth(36)
        layout.addWidget(self._play_btn)

        # Step forward
        self._next_btn = QPushButton("▶▶")
        self._next_btn.setToolTip("Step forward")
        self._next_btn.setStyleSheet(btn_style)
        layout.addWidget(self._next_btn)

        # Go to end
        self._end_btn = QPushButton("▶|")
        self._end_btn.setToolTip("Go to end")
        self._end_btn.setStyleSheet(btn_style)
        layout.addWidget(self._end_btn)

        layout.addSpacing(8)

        # Loop toggle
        self._loop_btn = QPushButton("🔁")
        self._loop_btn.setToolTip("Toggle loop")
        self._loop_btn.setCheckable(True)
        self._loop_btn.setChecked(True)
        self._loop_btn.setStyleSheet(btn_style)
        layout.addWidget(self._loop_btn)

        # Speed selector
        self._speed_combo = QComboBox()
        self._speed_combo.addItems(["0.25x", "0.5x", "1x", "2x", "4x"])
        self._speed_combo.setCurrentText("1x")
        self._speed_combo.setStyleSheet("""
            QComboBox {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                padding: 4px 8px;
                border-radius: 3px;
                min-width: 50px;
            }
            QComboBox:hover { background-color: #4a5160; }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: none; border: none; }
        """)
        layout.addWidget(self._speed_combo)

        layout.addSpacing(8)

        # Timeline slider
        self._timeline = QSlider(Qt.Horizontal)
        self._timeline.setRange(0, 1000)
        self._timeline.setValue(0)
        self._timeline.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #3c414b;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #4a9eff;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #4a9eff;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self._timeline, stretch=1)

        # Time display
        self._time_label = QLabel("0:00.0 / 0:00.0")
        self._time_label.setStyleSheet("color: #a0a0a0; font-size: 11px; min-width: 90px;")
        layout.addWidget(self._time_label)

    def _connect_signals(self):
        """Connect signals."""
        self._start_btn.clicked.connect(self._controller.go_to_start)
        self._prev_btn.clicked.connect(self._controller.step_backward)
        self._play_btn.clicked.connect(self._controller.toggle_play)
        self._next_btn.clicked.connect(self._controller.step_forward)
        self._end_btn.clicked.connect(self._controller.go_to_end)

        self._loop_btn.toggled.connect(self._on_loop_toggled)
        self._speed_combo.currentTextChanged.connect(self._on_speed_changed)

        self._timeline.sliderPressed.connect(self._on_slider_pressed)
        self._timeline.sliderReleased.connect(self._on_slider_released)
        self._timeline.valueChanged.connect(self._on_slider_changed)

        self._controller.time_changed.connect(self._on_time_changed)
        self._controller.playback_state_changed.connect(self._on_playback_changed)

    def _on_loop_toggled(self, checked: bool):
        self._controller.loop = checked

    def _on_speed_changed(self, text: str):
        speed = float(text.replace('x', ''))
        self._controller.speed = speed

    def _on_slider_pressed(self):
        self._dragging_slider = True

    def _on_slider_released(self):
        self._dragging_slider = False
        normalized = self._timeline.value() / 1000.0
        self._controller.seek_normalized(normalized)

    def _on_slider_changed(self, value: int):
        if self._dragging_slider:
            normalized = value / 1000.0
            self._controller.seek_normalized(normalized)

    def _on_time_changed(self, time_sec: float, normalized: float):
        if not self._dragging_slider:
            self._timeline.setValue(int(normalized * 1000))

        duration = self._controller.duration
        self._time_label.setText(f"{self._format_time(time_sec)} / {self._format_time(duration)}")

    def _on_playback_changed(self, is_playing: bool):
        self._play_btn.setText("❚❚" if is_playing else "▶")

    def _format_time(self, seconds: float) -> str:
        """Format time as M:SS.s"""
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}:{secs:04.1f}"
