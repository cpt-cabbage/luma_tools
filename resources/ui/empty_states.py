"""
Empty state guidance widgets for Luma Tools.

Provides contextual help and guidance when gallery or workflow areas are empty.
Follows industry best practices for AI image generation UX.

Usage:
    from empty_states import GalleryEmptyState, ComfyUIEmptyState

    # In gallery when no items:
    empty_widget = GalleryEmptyState()
    empty_widget.get_started_clicked.connect(self._on_get_started)
    layout.addWidget(empty_widget)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class EmptyStateWidget(QWidget):
    """Base class for empty state guidance widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyStateWidget")
        self._setup_ui()

    def _setup_ui(self):
        """Set up the empty state UI. Override in subclasses."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        # Icon/emoji label
        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setFont(QFont("Segoe UI Emoji", 48))
        layout.addWidget(self._icon_label)

        # Title
        self._title_label = QLabel()
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self._title_label.setStyleSheet("color: #ffffff;")
        layout.addWidget(self._title_label)

        # Description
        self._desc_label = QLabel()
        self._desc_label.setAlignment(Qt.AlignCenter)
        self._desc_label.setWordWrap(True)
        self._desc_label.setMaximumWidth(400)
        self._desc_label.setStyleSheet("color: #aaaaaa; line-height: 1.4;")
        layout.addWidget(self._desc_label)

        # Steps container
        self._steps_frame = QFrame()
        self._steps_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(74, 158, 255, 0.1);
                border: 1px solid rgba(74, 158, 255, 0.3);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        self._steps_layout = QVBoxLayout(self._steps_frame)
        self._steps_layout.setSpacing(8)
        layout.addWidget(self._steps_frame)

        # Action button container
        self._button_layout = QHBoxLayout()
        self._button_layout.setAlignment(Qt.AlignCenter)
        layout.addLayout(self._button_layout)

        # Spacer
        layout.addStretch()

        # Apply default styling
        self.setStyleSheet("""
            EmptyStateWidget, #EmptyStateWidget {
                background-color: transparent;
            }
        """)

    def set_icon(self, icon_text: str):
        """Set the icon/emoji."""
        self._icon_label.setText(icon_text)

    def set_title(self, title: str):
        """Set the title text."""
        self._title_label.setText(title)

    def set_description(self, desc: str):
        """Set the description text."""
        self._desc_label.setText(desc)

    def add_step(self, number: int, text: str):
        """Add a numbered step."""
        step_layout = QHBoxLayout()
        step_layout.setSpacing(8)

        # Number badge
        number_label = QLabel(str(number))
        number_label.setFixedSize(24, 24)
        number_label.setAlignment(Qt.AlignCenter)
        number_label.setStyleSheet("""
            QLabel {
                background-color: #4a9eff;
                color: white;
                border-radius: 12px;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        step_layout.addWidget(number_label)

        # Step text
        text_label = QLabel(text)
        text_label.setStyleSheet("color: #cccccc;")
        step_layout.addWidget(text_label, 1)

        self._steps_layout.addLayout(step_layout)

    def add_action_button(self, text: str, callback, primary=True):
        """Add an action button."""
        btn = QPushButton(text)
        if primary:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a9eff;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 24px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #5ba3ff;
                }
                QPushButton:pressed {
                    background-color: #3d8ae6;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #4a9eff;
                    border: 1px solid #4a9eff;
                    border-radius: 4px;
                    padding: 8px 24px;
                }
                QPushButton:hover {
                    background-color: rgba(74, 158, 255, 0.1);
                }
            """)
        btn.clicked.connect(callback)
        self._button_layout.addWidget(btn)
        return btn


class GalleryEmptyState(EmptyStateWidget):
    """Empty state guidance for the gallery tab."""

    get_started_clicked = Signal()
    browse_folder_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._configure()

    def _configure(self):
        """Configure the gallery empty state."""
        self.set_icon("🖼️")
        self.set_title("No generations yet")
        self.set_description(
            "Your AI-generated images, videos, and 3D models will appear here. "
            "Start creating to build your gallery!"
        )

        self.add_step(1, "Go to the ComfyUI tab")
        self.add_step(2, "Select a workflow preset")
        self.add_step(3, "Add input images (if needed)")
        self.add_step(4, "Click Generate")

        self.add_action_button("Go to ComfyUI", self._on_get_started)
        self.add_action_button("Browse Folder", self._on_browse, primary=False)

    def _on_get_started(self):
        """Handle get started button click."""
        self.get_started_clicked.emit()

    def _on_browse(self):
        """Handle browse folder button click."""
        self.browse_folder_clicked.emit()


class ComfyUIEmptyState(EmptyStateWidget):
    """Empty state guidance for the ComfyUI tab (no preset selected)."""

    select_preset_clicked = Signal()
    add_preset_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._configure()

    def _configure(self):
        """Configure the ComfyUI empty state."""
        self.set_icon("🎨")
        self.set_title("Select a Workflow")
        self.set_description(
            "Choose a workflow preset to start generating. "
            "Each workflow has different capabilities and input requirements."
        )

        self.add_step(1, "Click 'Choose Preset' to see available workflows")
        self.add_step(2, "Select a workflow that matches your needs")
        self.add_step(3, "Configure the editable parameters")
        self.add_step(4, "Add input images and click Generate")

        self.add_action_button("Choose Preset", self._on_select)

    def _on_select(self):
        """Handle select preset button click."""
        self.select_preset_clicked.emit()

    def _on_add(self):
        """Handle add preset button click."""
        self.add_preset_clicked.emit()


class NoResultsState(EmptyStateWidget):
    """Empty state when filter returns no results."""

    clear_filter_clicked = Signal()

    def __init__(self, filter_name: str = "filter", parent=None):
        self._filter_name = filter_name
        super().__init__(parent)
        self._configure()

    def _configure(self):
        """Configure the no results state."""
        self.set_icon("🔍")
        self.set_title("No matching items")
        self.set_description(
            f"No items match your current {self._filter_name}. "
            "Try adjusting your filter or viewing all items."
        )

        # Hide steps frame for simpler message
        self._steps_frame.hide()

        self.add_action_button("Show All", self._on_clear)

    def _on_clear(self):
        """Handle clear filter button click."""
        self.clear_filter_clicked.emit()

    def set_filter_name(self, name: str):
        """Update the filter name in the description."""
        self._filter_name = name
        self.set_description(
            f"No items match your current {self._filter_name}. "
            "Try adjusting your filter or viewing all items."
        )


class SessionResumeBanner(QWidget):
    """Banner widget for resuming previous sessions."""

    resume_clicked = Signal(int)  # Emits session index
    dismiss_clicked = Signal()

    def __init__(self, session_description: str, session_index: int = 0, parent=None):
        super().__init__(parent)
        self._session_index = session_index
        self._setup_ui(session_description)

    def _setup_ui(self, description: str):
        """Set up the banner UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Icon
        icon_label = QLabel("📂")
        icon_label.setFont(QFont("Segoe UI Emoji", 14))
        layout.addWidget(icon_label)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_label = QLabel("Resume Previous Session")
        title_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        text_layout.addWidget(title_label)

        desc_label = QLabel(description)
        desc_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        text_layout.addWidget(desc_label)

        layout.addLayout(text_layout, 1)

        # Resume button
        resume_btn = QPushButton("Resume")
        resume_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5ba3ff;
            }
        """)
        resume_btn.clicked.connect(lambda: self.resume_clicked.emit(self._session_index))
        layout.addWidget(resume_btn)

        # Dismiss button
        dismiss_btn = QPushButton("✕")
        dismiss_btn.setFixedSize(24, 24)
        dismiss_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        dismiss_btn.clicked.connect(self.dismiss_clicked.emit)
        layout.addWidget(dismiss_btn)

        # Frame styling
        self.setStyleSheet("""
            SessionResumeBanner {
                background-color: rgba(74, 158, 255, 0.1);
                border: 1px solid rgba(74, 158, 255, 0.3);
                border-radius: 6px;
            }
        """)
        self.setObjectName("SessionResumeBanner")
