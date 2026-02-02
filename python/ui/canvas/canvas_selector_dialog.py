"""
Canvas selector dialog for managing multiple canvases.

Provides:
- List of available canvases (job-wide and shot-specific)
- Create, rename, duplicate, delete operations
- Dark-themed UI matching the application style
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMenu,
    QWidget, QComboBox, QMessageBox
)

from .canvas_metadata import CanvasMetadataManager, CanvasDef, CanvasScope

logger = logging.getLogger(__name__)


CANVAS_DIALOG_STYLESHEET = """
    QDialog {
        background-color: #1e1e22;
    }
    QLabel {
        color: #e0e0e0;
        font-size: 12px;
    }
    QLineEdit {
        background-color: #2c313a;
        color: #e0e0e0;
        border: 1px solid #3c414b;
        border-radius: 4px;
        padding: 8px;
        font-size: 12px;
    }
    QLineEdit:focus {
        border-color: #4a9eff;
    }
    QComboBox {
        background-color: #2c313a;
        color: #e0e0e0;
        border: 1px solid #3c414b;
        border-radius: 4px;
        padding: 6px 10px;
        font-size: 12px;
        min-width: 100px;
    }
    QComboBox:hover {
        border-color: #4a5160;
    }
    QComboBox::drop-down {
        border: none;
        padding-right: 8px;
    }
    QComboBox::down-arrow {
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid #888;
        margin-right: 5px;
    }
    QComboBox QAbstractItemView {
        background-color: #2c313a;
        color: #e0e0e0;
        selection-background-color: #4a9eff;
        border: 1px solid #3c414b;
    }
    QListWidget {
        background-color: #2c313a;
        color: #e0e0e0;
        border: 1px solid #3c414b;
        border-radius: 4px;
        font-size: 12px;
        outline: none;
    }
    QListWidget::item {
        padding: 8px 12px;
        border-bottom: 1px solid #3c414b;
    }
    QListWidget::item:selected {
        background-color: #4a9eff;
        color: white;
    }
    QListWidget::item:hover:!selected {
        background-color: #3c414b;
    }
    QPushButton {
        background-color: #3c414b;
        color: #e0e0e0;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 12px;
    }
    QPushButton:hover {
        background-color: #4a5160;
    }
    QPushButton:pressed {
        background-color: #5a6170;
    }
    QPushButton[primary="true"] {
        background-color: #4a9eff;
        color: white;
    }
    QPushButton[primary="true"]:hover {
        background-color: #5aa8ff;
    }
    QPushButton[primary="true"]:pressed {
        background-color: #3a8eef;
    }
    QPushButton:disabled {
        background-color: #2c313a;
        color: #666;
    }
"""


class CanvasSelectorDialog(QDialog):
    """
    Dialog for selecting and managing canvases.

    Shows list of job-wide and shot-specific canvases with options to:
    - Open a canvas
    - Create new canvas
    - Rename, duplicate, delete existing canvases
    """

    canvas_selected = Signal(str)  # Emits canvas_id when user selects a canvas
    canvas_created = Signal(str)   # Emits canvas_id when user creates a new canvas

    def __init__(
        self,
        metadata_manager: CanvasMetadataManager,
        has_shot_context: bool = False,
        parent: Optional[QWidget] = None
    ):
        """
        Initialize the canvas selector dialog.

        Args:
            metadata_manager: CanvasMetadataManager instance
            has_shot_context: Whether shot-specific canvases are available
            parent: Parent widget
        """
        super().__init__(parent)
        self._metadata_manager = metadata_manager
        self._has_shot_context = has_shot_context
        self._selected_canvas_id: Optional[str] = None

        self._setup_ui()
        self._populate_canvas_list()

    def _setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("Select Canvas")
        self.setMinimumSize(400, 350)
        self.resize(450, 400)
        self.setStyleSheet(CANVAS_DIALOG_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel("Choose a canvas to open:")
        header.setStyleSheet("font-weight: bold; color: #4a9eff;")
        layout.addWidget(header)

        # Canvas list
        self._canvas_list = QListWidget()
        self._canvas_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._canvas_list.customContextMenuRequested.connect(self._show_context_menu)
        self._canvas_list.itemDoubleClicked.connect(self._on_open_canvas)
        self._canvas_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._canvas_list, 1)

        # Button row
        button_layout = QHBoxLayout()

        self._new_btn = QPushButton("New Canvas...")
        self._new_btn.clicked.connect(self._on_new_canvas)
        button_layout.addWidget(self._new_btn)

        button_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_btn)

        self._open_btn = QPushButton("Open")
        self._open_btn.setProperty("primary", True)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open_canvas)
        button_layout.addWidget(self._open_btn)

        layout.addLayout(button_layout)

    def _populate_canvas_list(self):
        """Populate the list with available canvases."""
        self._canvas_list.clear()

        # Get all canvases
        job_canvases = self._metadata_manager.list_canvases(CanvasScope.JOB)
        shot_canvases = (
            self._metadata_manager.list_canvases(CanvasScope.SHOT)
            if self._has_shot_context else []
        )

        # Add job canvases section
        if job_canvases:
            header_item = QListWidgetItem("── Job Canvases ──")
            header_item.setFlags(Qt.NoItemFlags)
            header_item.setData(Qt.UserRole, None)
            header_item.setForeground(Qt.gray)
            self._canvas_list.addItem(header_item)

            for canvas in job_canvases:
                self._add_canvas_item(canvas)

        # Add shot canvases section
        if shot_canvases:
            header_item = QListWidgetItem("── Shot Canvases ──")
            header_item.setFlags(Qt.NoItemFlags)
            header_item.setData(Qt.UserRole, None)
            header_item.setForeground(Qt.gray)
            self._canvas_list.addItem(header_item)

            for canvas in shot_canvases:
                self._add_canvas_item(canvas)

        # Show message if no canvases
        if not job_canvases and not shot_canvases:
            empty_item = QListWidgetItem("No canvases found. Create one to get started.")
            empty_item.setFlags(Qt.NoItemFlags)
            empty_item.setData(Qt.UserRole, None)
            empty_item.setForeground(Qt.gray)
            self._canvas_list.addItem(empty_item)

    def _add_canvas_item(self, canvas: CanvasDef):
        """Add a canvas item to the list."""
        # Format: "Name (by creator, modified date)"
        modified_date = canvas.modified[:10] if canvas.modified else "unknown"
        text = f"  {canvas.name}"
        subtitle = f"by {canvas.created_by} • {modified_date} • {canvas.item_count} items"

        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, canvas.id)
        item.setToolTip(f"{canvas.name}\n{subtitle}")

        # Add subtitle as separate line style using rich text would be complex,
        # so we'll just use tooltip for details
        self._canvas_list.addItem(item)

    def _on_selection_changed(self):
        """Handle selection change in the list."""
        current = self._canvas_list.currentItem()
        if current and current.data(Qt.UserRole):
            self._selected_canvas_id = current.data(Qt.UserRole)
            self._open_btn.setEnabled(True)
        else:
            self._selected_canvas_id = None
            self._open_btn.setEnabled(False)

    def _on_open_canvas(self):
        """Open the selected canvas."""
        if self._selected_canvas_id:
            self.canvas_selected.emit(self._selected_canvas_id)
            self.accept()

    def _on_new_canvas(self):
        """Show dialog to create a new canvas."""
        dialog = NewCanvasDialog(
            has_shot_context=self._has_shot_context,
            parent=self
        )
        if dialog.exec() == QDialog.Accepted:
            name = dialog.canvas_name
            scope = dialog.canvas_scope

            canvas = self._metadata_manager.create_canvas(name, scope)
            if canvas:
                self.canvas_created.emit(canvas.id)
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Error",
                    "Failed to create canvas. Please try again."
                )

    def _show_context_menu(self, pos):
        """Show context menu for canvas item."""
        item = self._canvas_list.itemAt(pos)
        if not item or not item.data(Qt.UserRole):
            return

        canvas_id = item.data(Qt.UserRole)
        canvas = self._metadata_manager.get_canvas(canvas_id)
        if not canvas:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2c313a;
                color: #e0e0e0;
                border: 1px solid #3c414b;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
            }
            QMenu::item:selected {
                background-color: #4a9eff;
            }
        """)

        open_action = menu.addAction("Open")
        open_action.triggered.connect(lambda: self._open_specific_canvas(canvas_id))

        menu.addSeparator()

        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(lambda: self._rename_canvas(canvas_id))

        duplicate_action = menu.addAction("Duplicate...")
        duplicate_action.triggered.connect(lambda: self._duplicate_canvas(canvas_id))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_canvas(canvas_id))

        menu.exec_(self._canvas_list.mapToGlobal(pos))

    def _open_specific_canvas(self, canvas_id: str):
        """Open a specific canvas."""
        self._selected_canvas_id = canvas_id
        self.canvas_selected.emit(canvas_id)
        self.accept()

    def _rename_canvas(self, canvas_id: str):
        """Rename a canvas."""
        canvas = self._metadata_manager.get_canvas(canvas_id)
        if not canvas:
            return

        dialog = RenameCanvasDialog(canvas.name, parent=self)
        if dialog.exec() == QDialog.Accepted:
            new_name = dialog.new_name
            if self._metadata_manager.rename_canvas(canvas_id, new_name):
                self._populate_canvas_list()
            else:
                QMessageBox.warning(
                    self, "Error",
                    "Failed to rename canvas."
                )

    def _duplicate_canvas(self, canvas_id: str):
        """Duplicate a canvas."""
        canvas = self._metadata_manager.get_canvas(canvas_id)
        if not canvas:
            return

        dialog = NewCanvasDialog(
            has_shot_context=self._has_shot_context,
            default_name=f"{canvas.name} (copy)",
            default_scope=canvas.scope_enum,
            title="Duplicate Canvas",
            parent=self
        )
        if dialog.exec() == QDialog.Accepted:
            new_name = dialog.canvas_name
            new_scope = dialog.canvas_scope

            new_canvas = self._metadata_manager.duplicate_canvas(
                canvas_id, new_name, new_scope
            )
            if new_canvas:
                self._populate_canvas_list()
            else:
                QMessageBox.warning(
                    self, "Error",
                    "Failed to duplicate canvas."
                )

    def _delete_canvas(self, canvas_id: str):
        """Delete a canvas with confirmation."""
        canvas = self._metadata_manager.get_canvas(canvas_id)
        if not canvas:
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Canvas",
            f"Are you sure you want to delete '{canvas.name}'?\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self._metadata_manager.delete_canvas(canvas_id):
                self._populate_canvas_list()
            else:
                QMessageBox.warning(
                    self, "Cannot Delete",
                    "Cannot delete the last canvas in this scope.\n"
                    "Create another canvas first."
                )


class NewCanvasDialog(QDialog):
    """Dialog for creating a new canvas."""

    def __init__(
        self,
        has_shot_context: bool = False,
        default_name: str = "",
        default_scope: Optional[CanvasScope] = None,
        title: str = "New Canvas",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._has_shot_context = has_shot_context
        self._default_name = default_name
        self._default_scope = default_scope or CanvasScope.JOB

        self.canvas_name = ""
        self.canvas_scope = CanvasScope.JOB

        self.setWindowTitle(title)
        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI."""
        self.setMinimumWidth(350)
        self.setStyleSheet(CANVAS_DIALOG_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Name input
        name_label = QLabel("Canvas Name:")
        layout.addWidget(name_label)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Enter canvas name...")
        self._name_input.setText(self._default_name)
        self._name_input.textChanged.connect(self._validate_input)
        layout.addWidget(self._name_input)

        # Scope selection
        scope_label = QLabel("Scope:")
        layout.addWidget(scope_label)

        self._scope_combo = QComboBox()
        self._scope_combo.addItem("Job-wide (visible in all shots)", CanvasScope.JOB.value)
        if self._has_shot_context:
            self._scope_combo.addItem("This shot only", CanvasScope.SHOT.value)

        # Set default scope
        if self._default_scope == CanvasScope.SHOT and self._has_shot_context:
            self._scope_combo.setCurrentIndex(1)

        layout.addWidget(self._scope_combo)

        layout.addStretch()

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_btn)

        self._create_btn = QPushButton("Create")
        self._create_btn.setProperty("primary", True)
        self._create_btn.setEnabled(bool(self._default_name))
        self._create_btn.clicked.connect(self._on_create)
        button_layout.addWidget(self._create_btn)

        layout.addLayout(button_layout)

        # Focus on name input
        self._name_input.setFocus()
        self._name_input.selectAll()

    def _validate_input(self):
        """Validate input and update create button state."""
        name = self._name_input.text().strip()
        self._create_btn.setEnabled(bool(name))

    def _on_create(self):
        """Handle create button click."""
        self.canvas_name = self._name_input.text().strip()
        scope_value = self._scope_combo.currentData()
        self.canvas_scope = CanvasScope(scope_value)
        self.accept()


class RenameCanvasDialog(QDialog):
    """Dialog for renaming a canvas."""

    def __init__(self, current_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_name = current_name
        self.new_name = ""

        self.setWindowTitle("Rename Canvas")
        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI."""
        self.setMinimumWidth(300)
        self.setStyleSheet(CANVAS_DIALOG_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Name input
        name_label = QLabel("New Name:")
        layout.addWidget(name_label)

        self._name_input = QLineEdit()
        self._name_input.setText(self._current_name)
        self._name_input.textChanged.connect(self._validate_input)
        layout.addWidget(self._name_input)

        layout.addStretch()

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_btn)

        self._rename_btn = QPushButton("Rename")
        self._rename_btn.setProperty("primary", True)
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(self._on_rename)
        button_layout.addWidget(self._rename_btn)

        layout.addLayout(button_layout)

        # Focus and select
        self._name_input.setFocus()
        self._name_input.selectAll()

    def _validate_input(self):
        """Validate input and update rename button state."""
        name = self._name_input.text().strip()
        # Enable if name is non-empty and different from current
        self._rename_btn.setEnabled(bool(name) and name != self._current_name)

    def _on_rename(self):
        """Handle rename button click."""
        self.new_name = self._name_input.text().strip()
        self.accept()
