"""
Quick Actions Bar for Gallery selection.

Floating action bar that appears when images are selected in the gallery,
providing quick access to cross-tab operations.

Features:
- "Use in ComfyUI" - Load selected images as ComfyUI inputs
- "Copy Prompt" - Copy prompt text from selected image's metadata
- "Compare to Source" - Open side-by-side with source image
- "Recreate Settings" - Full settings restore + tab switch
"""

import logging
from typing import List, Callable, Optional

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor

logger = logging.getLogger(__name__)


class QuickActionsBar(QFrame):
    """
    Floating action bar for selected gallery items.

    Appears at the bottom of the gallery when items are selected.
    """

    # Signals
    use_in_comfyui = Signal(list)  # List of selected paths
    copy_prompt = Signal(str)  # Path of item to copy prompt from
    compare_to_source = Signal(str)  # Path of item to compare
    recreate_settings = Signal(str)  # Path of item to recreate from

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_paths: List[str] = []
        self._is_visible = False
        self._fade_animation = None
        self._get_metadata_func: Optional[Callable] = None

        # Create opacity effect for fade animations (required for non-top-level widgets)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._setup_ui()
        self.hide()  # Start hidden

    def _setup_ui(self):
        """Set up the action bar UI."""
        self.setObjectName("QuickActionsBar")
        self.setFixedHeight(44)
        self.setStyleSheet("""
            #QuickActionsBar {
                background-color: #282c34;
                border: 1px solid #4a9eff;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # Selection count label
        self._count_label = QLabel("0 selected")
        self._count_label.setStyleSheet("color: #4a9eff; font-weight: bold; font-size: 11px;")
        layout.addWidget(self._count_label)

        layout.addSpacing(8)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet("color: #3c414b;")
        layout.addWidget(sep)

        layout.addSpacing(8)

        # Action buttons
        self._use_in_comfyui_btn = self._create_action_button(
            "Use in ComfyUI",
            "Load selected images as ComfyUI inputs",
            self._on_use_in_comfyui
        )
        layout.addWidget(self._use_in_comfyui_btn)

        self._copy_prompt_btn = self._create_action_button(
            "Copy Prompt",
            "Copy the prompt text from this image",
            self._on_copy_prompt
        )
        layout.addWidget(self._copy_prompt_btn)

        self._compare_btn = self._create_action_button(
            "Compare to Source",
            "Open side-by-side with the source image",
            self._on_compare_to_source
        )
        layout.addWidget(self._compare_btn)

        self._recreate_btn = self._create_action_button(
            "Recreate Settings",
            "Restore all ComfyUI settings from this image",
            self._on_recreate_settings
        )
        layout.addWidget(self._recreate_btn)

        layout.addStretch()

    def _create_action_button(self, text: str, tooltip: str, callback: Callable) -> QPushButton:
        """Create a styled action button."""
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #3c414b;
                border-radius: 4px;
                color: #aaaaaa;
                font-size: 11px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #3c414b;
                color: #ffffff;
                border-color: #4a9eff;
            }
            QPushButton:disabled {
                color: #555555;
                border-color: #2c313a;
            }
        """)
        btn.clicked.connect(callback)
        return btn

    def set_metadata_callback(self, callback: Callable):
        """
        Set the callback function to get metadata for a path.

        Args:
            callback: Function that takes a path and returns metadata dict
        """
        self._get_metadata_func = callback

    def update_selection(self, selected_paths: List[str]):
        """
        Update the bar based on current selection.

        Args:
            selected_paths: List of selected file paths
        """
        self._selected_paths = list(selected_paths)
        count = len(selected_paths)

        if count == 0:
            self._hide_with_fade()
            return

        # Update count label
        self._count_label.setText(f"{count} selected")

        # Update button states based on selection
        has_single = count == 1
        has_any = count > 0

        self._use_in_comfyui_btn.setEnabled(has_any)
        self._copy_prompt_btn.setEnabled(has_single)  # Only for single selection
        self._compare_btn.setEnabled(has_single)  # Only for single selection
        self._recreate_btn.setEnabled(has_single)  # Only for single selection

        # Show the bar
        self._show_with_fade()

    def _on_use_in_comfyui(self):
        """Handle 'Use in ComfyUI' action."""
        if self._selected_paths:
            self.use_in_comfyui.emit(self._selected_paths)

    def _on_copy_prompt(self):
        """Handle 'Copy Prompt' action."""
        if self._selected_paths:
            self.copy_prompt.emit(self._selected_paths[0])

    def _on_compare_to_source(self):
        """Handle 'Compare to Source' action."""
        if self._selected_paths:
            self.compare_to_source.emit(self._selected_paths[0])

    def _on_recreate_settings(self):
        """Handle 'Recreate Settings' action."""
        if self._selected_paths:
            self.recreate_settings.emit(self._selected_paths[0])

    def _show_with_fade(self):
        """Show the bar with a fade-in animation."""
        if self._is_visible:
            return

        self._is_visible = True
        self._opacity_effect.setOpacity(0.0)
        self.show()

        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(150)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_animation.start()

    def _hide_with_fade(self):
        """Hide the bar with a fade-out animation."""
        if not self._is_visible:
            return

        self._is_visible = False

        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(200)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.InCubic)
        self._fade_animation.finished.connect(self.hide)
        self._fade_animation.start()

    def force_hide(self):
        """Immediately hide without animation."""
        self._is_visible = False
        self._selected_paths.clear()
        self.hide()

    def force_show(self):
        """Immediately show without animation."""
        self._is_visible = True
        self.show()
        self._opacity_effect.setOpacity(1.0)
