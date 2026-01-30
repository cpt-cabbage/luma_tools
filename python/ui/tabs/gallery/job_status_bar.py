"""
Job Status Bar for Gallery tab.

Shows a subtle top bar displaying active ComfyUI job progress when jobs are running.
Auto-hides when no jobs are active.

Features:
- Shows aggregate progress across all active jobs
- Displays job counts (rendering, queued, completed)
- "View in ComfyUI" button to switch tabs
- Auto-fades out when all jobs complete
"""

import logging
from typing import Dict, Any

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QEasingCurve
from effects import create_property_animation
from PySide6.QtGui import QCursor

logger = logging.getLogger(__name__)


class JobStatusBar(QFrame):
    """
    Subtle status bar showing active ComfyUI job progress.

    Displays at the top of the gallery when jobs are running.
    """

    # Signals
    view_in_comfyui_clicked = Signal()  # User wants to switch to ComfyUI tab

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_visible = False
        self._fade_animation = None

        # Create opacity effect for fade animations (required for non-top-level widgets)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._setup_ui()
        self.hide()  # Start hidden

    def _setup_ui(self):
        """Set up the status bar UI."""
        self.setObjectName("JobStatusBar")
        self.setFixedHeight(32)
        self.setStyleSheet("""
            #JobStatusBar {
                background-color: #1e2127;
                border-bottom: 1px solid #3c414b;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)

        # Spinner indicator (using unicode for simplicity)
        self._spinner_label = QLabel("◉")
        self._spinner_label.setStyleSheet("color: #4a9eff; font-size: 12px;")
        self._spinner_label.setFixedWidth(16)
        layout.addWidget(self._spinner_label)

        # Status text
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self._status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._status_label)

        # Expected outputs indicator
        self._expected_label = QLabel("")
        self._expected_label.setStyleSheet("color: #666666; font-size: 10px;")
        layout.addWidget(self._expected_label)

        # View in ComfyUI button
        self._view_button = QPushButton("View in ComfyUI")
        self._view_button.setFixedHeight(22)
        self._view_button.setCursor(QCursor(Qt.PointingHandCursor))
        self._view_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #4a9eff;
                border-radius: 4px;
                color: #4a9eff;
                font-size: 10px;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background-color: #4a9eff;
                color: #ffffff;
            }
        """)
        self._view_button.clicked.connect(self.view_in_comfyui_clicked.emit)
        layout.addWidget(self._view_button)

    def update_from_progress(self, progress: Dict[str, Any]):
        """
        Update the status bar from aggregate progress data.

        Args:
            progress: Dict from pipeline_events.get_aggregate_progress() with keys:
                - total_jobs, completed_jobs, rendering_jobs, queued_jobs, failed_jobs
                - total_expected, total_completed, avg_progress
        """
        total = progress.get("total_jobs", 0)
        completed = progress.get("completed_jobs", 0)
        rendering = progress.get("rendering_jobs", 0)
        queued = progress.get("queued_jobs", 0)
        failed = progress.get("failed_jobs", 0)
        total_expected = progress.get("total_expected", 0)
        total_completed = progress.get("total_completed", 0)
        avg_progress = progress.get("avg_progress", 0)

        # Determine if we should show the bar
        active_jobs = total - completed - failed
        if active_jobs <= 0:
            self._hide_with_fade()
            return

        # Build status text
        parts = []

        if rendering > 0:
            if avg_progress > 0:
                parts.append(f"{rendering} rendering ({avg_progress}%)")
            else:
                parts.append(f"{rendering} rendering")

        if queued > 0:
            parts.append(f"{queued} queued")

        if completed > 0:
            parts.append(f"{completed} complete")

        if failed > 0:
            parts.append(f"{failed} failed")

        status_text = " • ".join(parts) if parts else "Jobs in progress..."
        self._status_label.setText(status_text)

        # Update expected outputs
        if total_expected > 0:
            self._expected_label.setText(f"{total_completed}/{total_expected} outputs")
        else:
            self._expected_label.setText("")

        # Update spinner color based on state
        if failed > 0:
            self._spinner_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        elif rendering > 0:
            self._spinner_label.setStyleSheet("color: #4a9eff; font-size: 12px;")
        else:
            self._spinner_label.setStyleSheet("color: #f59e0b; font-size: 12px;")

        # Show the bar
        self._show_with_fade()

    def _show_with_fade(self):
        """Show the bar with a fade-in animation."""
        if self._is_visible:
            return

        self._is_visible = True
        self._opacity_effect.setOpacity(0.0)
        self.show()

        self._fade_animation = create_property_animation(
            self._opacity_effect, b"opacity", 0.0, 1.0,
            duration=200, easing=QEasingCurve.OutCubic
        )
        self._fade_animation.start()

    def _hide_with_fade(self):
        """Hide the bar with a fade-out animation."""
        if not self._is_visible:
            return

        self._is_visible = False

        self._fade_animation = create_property_animation(
            self._opacity_effect, b"opacity", 1.0, 0.0,
            duration=300, easing=QEasingCurve.InCubic
        )
        self._fade_animation.finished.connect(self.hide)
        self._fade_animation.start()

    def force_hide(self):
        """Immediately hide without animation."""
        self._is_visible = False
        self.hide()

    def force_show(self):
        """Immediately show without animation."""
        self._is_visible = True
        self.show()
        self._opacity_effect.setOpacity(1.0)
