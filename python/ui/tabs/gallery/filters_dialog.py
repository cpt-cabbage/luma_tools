"""
Gallery Filters Dialog.

Floating popup dialog for gallery filter settings.
"""

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QFrame
)


class FiltersDialog(QWidget):
    """
    Floating popup dialog for gallery filters.

    Appears below the Filters button and auto-closes when clicking outside.

    Signals:
        filters_changed(): Emitted when any filter setting changes
        closed(): Emitted when dialog is closed
    """

    filters_changed = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=None)  # No parent - standalone popup
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Filter state
        self._show_inputs = False
        self._type_filters = {
            "image": True,
            "video": True,
            "audio": True,
            "model": True
        }

        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # Main container with styling
        self.container = QFrame(self)
        self.container.setObjectName("FiltersDialogContainer")
        self.container.setProperty("variant", "panel")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(8)

        # Header
        header = QLabel("Filters")
        header.setProperty("textRole", "title")
        container_layout.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setProperty("variant", "divider")
        sep.setFixedHeight(1)
        container_layout.addWidget(sep)

        # File Type section
        type_header = QLabel("File Types")
        type_header.setProperty("textRole", "micro")
        container_layout.addWidget(type_header)

        # Type checkboxes
        self._type_checkboxes = {}
        type_labels = {
            "image": "Images",
            "video": "Videos",
            "audio": "Audio",
            "model": "3D Models"
        }

        for type_key, label in type_labels.items():
            checkbox = QCheckBox(label)
            checkbox.setChecked(self._type_filters.get(type_key, True))
            checkbox.toggled.connect(
                lambda checked, k=type_key: self._on_type_filter_changed(k, checked)
            )
            container_layout.addWidget(checkbox)
            self._type_checkboxes[type_key] = checkbox

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setProperty("variant", "divider")
        sep2.setFixedHeight(1)
        container_layout.addWidget(sep2)

        # Other filters section
        other_header = QLabel("Display")
        other_header.setProperty("textRole", "micro")
        container_layout.addWidget(other_header)

        # Show Inputs checkbox
        self._show_inputs_checkbox = QCheckBox("Show Inputs")
        self._show_inputs_checkbox.setToolTip("Show/hide input source images")
        self._show_inputs_checkbox.setChecked(self._show_inputs)
        self._show_inputs_checkbox.toggled.connect(self._on_show_inputs_changed)
        container_layout.addWidget(self._show_inputs_checkbox)

        # Set minimum width
        self.setMinimumWidth(180)

    def _on_type_filter_changed(self, type_key, checked):
        """Handle type filter checkbox change."""
        self._type_filters[type_key] = checked
        self.filters_changed.emit()

    def _on_show_inputs_changed(self, checked):
        """Handle show inputs checkbox change."""
        self._show_inputs = checked
        self.filters_changed.emit()

    def get_type_filters(self):
        """Get current type filter settings.

        Returns:
            dict: Type key -> bool mapping
        """
        return self._type_filters.copy()

    def set_type_filters(self, filters):
        """Set type filter settings.

        Args:
            filters: Dict of type key -> bool
        """
        self._type_filters = filters.copy()
        for type_key, checkbox in self._type_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(self._type_filters.get(type_key, True))
            checkbox.blockSignals(False)

    def get_show_inputs(self):
        """Get show inputs setting.

        Returns:
            bool: Whether to show input images
        """
        return self._show_inputs

    def set_show_inputs(self, show):
        """Set show inputs setting.

        Args:
            show: Whether to show input images
        """
        self._show_inputs = show
        self._show_inputs_checkbox.blockSignals(True)
        self._show_inputs_checkbox.setChecked(show)
        self._show_inputs_checkbox.blockSignals(False)

    def has_active_filters(self):
        """Check if any non-default filters are active.

        Returns:
            bool: True if any filters are restricting the view
        """
        # Check if any type is unchecked
        if not all(self._type_filters.values()):
            return True
        # Show inputs being True is also considered "active" for indicator
        if self._show_inputs:
            return True
        return False

    def get_active_filter_count(self):
        """Get count of active filters for badge display.

        Returns:
            int: Number of active filter modifications
        """
        count = 0
        # Count unchecked types
        count += sum(1 for v in self._type_filters.values() if not v)
        # Show inputs counts if enabled
        if self._show_inputs:
            count += 1
        return count

    def show_below(self, widget):
        """Show the dialog below the specified widget.

        Args:
            widget: The widget to position below
        """
        # Position below the widget
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
