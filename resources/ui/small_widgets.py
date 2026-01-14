"""
Small reusable UI widgets.

Contains simple widgets used across the application.
"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QWidget, QGroupBox, QListWidget, QListWidgetItem
)


class CollapsibleSection(QGroupBox):
    """A group box that can collapse/expand its contents."""

    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        """Handle toggle to show/hide contents."""
        for child in self.findChildren(QWidget):
            child.setVisible(checked)


class StepGroupBox(QGroupBox):
    """A group box styled as a step in a wizard-like UI."""

    def __init__(self, title="", parent=None):
        super().__init__(title, parent)


class StepProgressIndicator(QWidget):
    """A widget showing progress through numbered steps."""

    def __init__(self, parent=None):
        super().__init__(parent)


class EmptyStateWidget(QWidget):
    """A placeholder widget shown when content is empty."""

    def __init__(self, message="No items", parent=None):
        super().__init__(parent)


class ThumbnailRenderList(QListWidget):
    """A list widget optimized for displaying render thumbnails."""

    def __init__(self, parent=None):
        super().__init__(parent)


class RenderListItem(QListWidgetItem):
    """A list item for render thumbnails."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
