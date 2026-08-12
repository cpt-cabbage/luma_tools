"""
Gallery Stacks Dialog.

Floating popup dialog for gallery stacking options (Generations/Groups).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QCheckBox, QFrame
)


class StacksDialog(QWidget):
    """
    Floating popup dialog for gallery stacking options.

    Appears below the Stacks button and auto-closes when clicking outside.

    Signals:
        stacks_changed(): Emitted when any stacking setting changes
        closed(): Emitted when dialog is closed
    """

    stacks_changed = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=None)  # No parent - standalone popup
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Stacking state
        self._generations_on = True
        self._groups_on = False

        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # Main container with styling
        self.container = QFrame(self)
        self.container.setObjectName("StacksDialogContainer")
        self.container.setProperty("variant", "panel")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(8)

        # Header
        header = QLabel("Stacks")
        header.setProperty("textRole", "title")
        container_layout.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setProperty("variant", "divider")
        sep.setFixedHeight(1)
        container_layout.addWidget(sep)

        # Checkbox style

        # Generations checkbox
        self._generations_checkbox = QCheckBox("Generations")
        self._generations_checkbox.setToolTip("Group items by generation/job prefix")
        self._generations_checkbox.setChecked(self._generations_on)
        self._generations_checkbox.toggled.connect(self._on_generations_changed)
        container_layout.addWidget(self._generations_checkbox)

        # Groups checkbox
        self._groups_checkbox = QCheckBox("Groups")
        self._groups_checkbox.setToolTip("Group items by user-defined groups")
        self._groups_checkbox.setChecked(self._groups_on)
        self._groups_checkbox.toggled.connect(self._on_groups_changed)
        container_layout.addWidget(self._groups_checkbox)

        # Set minimum width
        self.setMinimumWidth(160)

    def _on_generations_changed(self, checked):
        """Handle generations checkbox change."""
        self._generations_on = checked
        self.stacks_changed.emit()

    def _on_groups_changed(self, checked):
        """Handle groups checkbox change."""
        self._groups_on = checked
        self.stacks_changed.emit()

    def get_generations(self):
        """Get generations setting."""
        return self._generations_on

    def set_generations(self, on):
        """Set generations setting."""
        self._generations_on = on
        self._generations_checkbox.blockSignals(True)
        self._generations_checkbox.setChecked(on)
        self._generations_checkbox.blockSignals(False)

    def get_groups(self):
        """Get groups setting."""
        return self._groups_on

    def set_groups(self, on):
        """Set groups setting."""
        self._groups_on = on
        self._groups_checkbox.blockSignals(True)
        self._groups_checkbox.setChecked(on)
        self._groups_checkbox.blockSignals(False)

    def get_active_count(self):
        """Get count of active stacking options.

        Returns:
            int: Number of active stacking modes
        """
        return int(self._generations_on) + int(self._groups_on)

    def show_below(self, widget):
        """Show the dialog below the specified widget.

        Args:
            widget: The widget to position below
        """
        pos = widget.mapToGlobal(widget.rect().bottomLeft())
        self.move(pos.x(), pos.y() + 4)
        self.show()

    def keyPressEvent(self, event):
        """Handle key press - close on Escape."""
        if event.key() == Qt.Key_Escape:
            # close() triggers closeEvent, which emits `closed` — emitting
            # here too double-fired the close handler
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Handle close event."""
        self.closed.emit()
        super().closeEvent(event)
