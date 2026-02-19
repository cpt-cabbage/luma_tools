"""
Model Dialog for ComfyUI Tab.

Modern edit dialog for workflow models/presets with sections for:
- Basic Info: Name, description, workflow path, iteratable, full_restart
- Workflows: Multi-workflow support with per-workflow settings
- Exposed Parameters: Per-parameter visibility and default value overrides
- Thumbnail: Preview, upload button, "Generate from Gallery" button
- Tags: Checkbox list of predefined tags
- Ratings: Display current rating + "Clear All Ratings" button (admin)
"""

import os
import logging
from typing import Any, Dict, List, Optional, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QCheckBox,
    QFrame, QScrollArea, QWidget, QTabWidget, QFileDialog,
    QDialogButtonBox, QGroupBox, QComboBox
)

from core.state_manager import app_state
from core.utils import ensure_directory
from comfyui.ratings import (
    get_model_rating, set_model_thumbnail, set_model_tags,
    clear_model_ratings, get_predefined_tags
)

from .star_rating import StarRatingWidget
from .rating_breakdown import RatingBreakdownWidget

logger = logging.getLogger(__name__)


class ModelDialog(QDialog):
    """
    Modern edit dialog for workflow models.

    Provides a tabbed interface for editing model configuration,
    managing thumbnails, setting tags, and viewing/clearing ratings.
    """

    def __init__(
        self,
        parent,
        model_name: str,
        preset_data: Dict[str, Any],
        main_window,
        extract_editable_nodes_func: Callable
    ):
        """
        Initialize model dialog.

        Args:
            parent: Parent widget
            model_name: Current model name
            preset_data: Preset configuration dictionary
            main_window: Reference to main window
            extract_editable_nodes_func: Function to extract editable nodes
        """
        super().__init__(parent)
        self.model_name = model_name
        self.preset_data = preset_data
        self.main_window = main_window
        self.extract_editable_nodes = extract_editable_nodes_func

        # Result storage
        self.result_accepted = False
        self.result_data = {}

        # Multi-workflow storage
        self._workflow_entry_widgets = {}

        # Exposed parameters state
        self._exposed_param_widgets: Dict[str, Dict] = {}  # key -> {checkbox, default_input, node}
        self._exposed_params_dirty = True  # Needs refresh on first show
        self._multi_overrides: Dict[str, Dict] = {}  # wf_name -> overrides dict (multi-workflow)
        self._current_exposed_wf: Optional[str] = None  # Currently selected workflow for exposed params

        self._setup_ui()
        self._load_data()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle(f"Edit Model: {self.model_name}")
        self.setMinimumSize(600, 500)
        self.resize(700, 600)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Tab widget for sections
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)

        # Basic Info tab
        self._setup_basic_tab()

        # Workflows tab (for multi-workflow support)
        self._setup_workflows_tab()

        # Exposed Parameters tab
        self._setup_exposed_params_tab()

        # Thumbnail tab
        self._setup_thumbnail_tab()

        # Tags tab
        self._setup_tags_tab()

        # Ratings tab (admin only)
        if app_state.is_admin:
            self._setup_ratings_tab()

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _setup_basic_tab(self):
        """Set up the Basic Info tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        form.setSpacing(12)

        # Model name
        self._name_edit = QLineEdit()
        self._name_edit.setText(self.model_name)
        form.addRow("Name:", self._name_edit)

        # Output type dropdown
        self._output_type_combo = QComboBox()
        self._output_type_combo.addItems(["Image", "Video", "3D", "Audio", "Other"])
        self._output_type_map = {"Image": "image", "Video": "video", "3D": "3d", "Audio": "audio", "Other": "other"}
        self._output_type_reverse = {v: k for k, v in self._output_type_map.items()}
        current_output_type = self.preset_data.get("output_type", "image")
        self._output_type_combo.setCurrentText(self._output_type_reverse.get(current_output_type, "Image"))
        self._output_type_combo.setToolTip(
            "Specify what type of content this model generates.\n\n"
            "• Image/Video: Auto-add to Canvas option will be available\n"
            "• 3D/Audio/Other: Canvas integration is disabled"
        )
        form.addRow("Output Type:", self._output_type_combo)

        # Workflow path
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setText(self.preset_data.get("path", ""))
        path_layout.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_workflow)
        path_layout.addWidget(browse_btn)
        form.addRow("Workflow File:", path_layout)

        # Description (single-line, shown in model browser)
        self._description_edit = QLineEdit()
        self._description_edit.setPlaceholderText("Brief description for model browser...")
        self._description_edit.setText(self.preset_data.get("description", ""))
        form.addRow("Description:", self._description_edit)

        # Notes (multi-line, shown in model group box for workflow instructions)
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setPlaceholderText("Workflow notes, settings, or restrictions...")
        self._notes_edit.setPlainText(self.preset_data.get("note", ""))
        self._notes_edit.setMaximumHeight(100)
        form.addRow("Notes:", self._notes_edit)

        layout.addLayout(form)

        # Options checkboxes
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self._iteratable_check = QCheckBox("Enable Iterate Mode")
        self._iteratable_check.setChecked(self.preset_data.get("iteratable", False))
        self._iteratable_check.setToolTip(
            "Iterate mode allows reviewing results and refining prompts\n"
            "between generations when only 1 image is selected."
        )
        options_layout.addWidget(self._iteratable_check)

        self._full_restart_check = QCheckBox("Full Restart (restart server before each job)")
        self._full_restart_check.setChecked(self.preset_data.get("full_restart", False))
        self._full_restart_check.setToolTip(
            "Completely restart the ComfyUI server before processing.\n"
            "Slower but ensures consistent results for certain models."
        )
        options_layout.addWidget(self._full_restart_check)

        self._restart_lowvram_check = QCheckBox("Low VRAM on Restart (--lowvram)")
        self._restart_lowvram_check.setChecked(self.preset_data.get("restart_lowvram", False))
        self._restart_lowvram_check.setToolTip(
            "Restart the ComfyUI server with --lowvram for this model.\n"
            "Only active when Full Restart is enabled.\n"
            "Reduces VRAM usage at the cost of performance."
        )
        self._restart_lowvram_check.setVisible(self._full_restart_check.isChecked())
        options_layout.addWidget(self._restart_lowvram_check)

        self._full_restart_check.toggled.connect(self._restart_lowvram_check.setVisible)

        layout.addWidget(options_group)
        layout.addStretch()

        self._tabs.addTab(tab, "Basic Info")

    def _setup_workflows_tab(self):
        """Set up the Workflows tab for multi-workflow support."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)

        # Multi-workflow checkbox
        self._is_multi_check = QCheckBox("Enable Multi-Workflow Mode")
        self._is_multi_check.setChecked(self.preset_data.get("is_multi", False))
        self._is_multi_check.setToolTip(
            "Enable this to add multiple workflows to a single model.\n"
            "Each workflow can have its own settings and note.\n"
            "A dropdown will appear in the ComfyUI tab to select which workflow to use."
        )
        self._is_multi_check.toggled.connect(self._on_multi_mode_toggled)
        layout.addWidget(self._is_multi_check)

        # Info label
        info_label = QLabel(
            "Multi-Workflow Mode allows you to bundle multiple workflows under one model.\n"
            "Each workflow can have different settings. Users select which workflow to use from a dropdown."
        )
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Workflows container (scroll area)
        self._workflows_scroll = QScrollArea()
        self._workflows_scroll.setWidgetResizable(True)
        self._workflows_scroll.setMinimumHeight(300)
        self._workflows_scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: 1px solid #3c3c3c; }")

        self._workflows_container = QWidget()
        self._workflows_layout = QVBoxLayout(self._workflows_container)
        self._workflows_layout.setContentsMargins(5, 5, 5, 5)
        self._workflows_layout.setSpacing(8)
        self._workflows_scroll.setWidget(self._workflows_container)
        layout.addWidget(self._workflows_scroll)

        # Add workflow button
        add_btn_layout = QHBoxLayout()
        self._add_workflow_btn = QPushButton("+ Add Workflow")
        self._add_workflow_btn.setFixedWidth(150)
        self._add_workflow_btn.setStyleSheet("QPushButton { color: #10b981; }")
        self._add_workflow_btn.clicked.connect(self._on_add_workflow)
        add_btn_layout.addWidget(self._add_workflow_btn)
        add_btn_layout.addStretch()
        layout.addLayout(add_btn_layout)

        self._tabs.addTab(tab, "Workflows")

        # Populate existing workflows
        self._populate_workflows()

        # Update visibility based on multi-workflow mode
        self._on_multi_mode_toggled(self._is_multi_check.isChecked())

    def _on_multi_mode_toggled(self, checked: bool):
        """Handle multi-workflow mode toggle."""
        self._workflows_scroll.setEnabled(checked)
        self._add_workflow_btn.setEnabled(checked)
        # Also disable the single workflow path in Basic Info when multi-mode is on
        self._path_edit.setEnabled(not checked)
        if checked:
            self._path_edit.setPlaceholderText("(Using multi-workflow mode - configure in Workflows tab)")
        else:
            self._path_edit.setPlaceholderText("")
        self._mark_exposed_params_dirty()

    def _populate_workflows(self):
        """Populate the workflows list from preset data."""
        # Clear existing
        while self._workflows_layout.count():
            item = self._workflows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._workflow_entry_widgets.clear()

        # Add existing workflows
        workflows = self.preset_data.get("workflows", {})
        for wf_name, wf_config in workflows.items():
            self._add_workflow_entry(wf_name, wf_config)

        # Add stretch at end
        self._workflows_layout.addStretch()

    def _on_add_workflow(self):
        """Add a new workflow entry."""
        # Generate unique name
        idx = len(self._workflow_entry_widgets) + 1
        wf_name = f"workflow_{idx}"
        while wf_name in self._workflow_entry_widgets:
            idx += 1
            wf_name = f"workflow_{idx}"

        self._add_workflow_entry(wf_name, None)

    def _add_workflow_entry(self, wf_name: str, wf_config):
        """Create a workflow entry widget."""
        if wf_config is None:
            wf_config = {
                "path": "",
                "note": "",
                "iteratable": False,
                "full_restart": False,
                "node_overrides": {}
            }

        entry_widget = QWidget()
        entry_widget.setStyleSheet("QWidget { background-color: #2a2a2a; border-radius: 4px; }")
        entry_layout = QVBoxLayout(entry_widget)
        entry_layout.setContentsMargins(10, 10, 10, 10)

        # Header row with name and delete button
        header_row = QHBoxLayout()
        wf_name_edit = QLineEdit(wf_name)
        wf_name_edit.setPlaceholderText("Workflow name...")
        wf_name_edit.setFixedWidth(200)
        header_row.addWidget(QLabel("Name:"))
        header_row.addWidget(wf_name_edit)
        header_row.addStretch()

        delete_btn = QPushButton("Remove")
        delete_btn.setStyleSheet("QPushButton { color: #ef4444; }")
        delete_btn.setFixedWidth(80)
        delete_btn.clicked.connect(lambda checked=False, w=entry_widget, n=wf_name: self._on_remove_workflow(w, n))
        header_row.addWidget(delete_btn)
        entry_layout.addLayout(header_row)

        # Path row
        path_row = QHBoxLayout()
        wf_path_edit = QLineEdit(wf_config.get("path", ""))
        wf_path_edit.setPlaceholderText("Workflow JSON file...")
        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(lambda checked=False, e=wf_path_edit: self._on_browse_wf_path(e))
        path_row.addWidget(QLabel("File:"))
        path_row.addWidget(wf_path_edit)
        path_row.addWidget(browse_btn)
        entry_layout.addLayout(path_row)

        # Options row
        options_row = QHBoxLayout()
        wf_iteratable = QCheckBox("Iterate Mode")
        wf_iteratable.setChecked(wf_config.get("iteratable", False))
        wf_full_restart = QCheckBox("Full Restart")
        wf_full_restart.setChecked(wf_config.get("full_restart", False))
        wf_restart_lowvram = QCheckBox("Low VRAM on Restart")
        wf_restart_lowvram.setChecked(wf_config.get("restart_lowvram", False))
        wf_restart_lowvram.setToolTip(
            "Restart server with --lowvram for this workflow.\n"
            "Only active when Full Restart is enabled."
        )
        wf_restart_lowvram.setVisible(wf_full_restart.isChecked())
        wf_full_restart.toggled.connect(wf_restart_lowvram.setVisible)
        options_row.addWidget(wf_iteratable)
        options_row.addWidget(wf_full_restart)
        options_row.addWidget(wf_restart_lowvram)
        options_row.addStretch()
        entry_layout.addLayout(options_row)

        # Note row
        note_row = QHBoxLayout()
        wf_note_edit = QLineEdit(wf_config.get("note", ""))
        wf_note_edit.setPlaceholderText("Note for this workflow...")
        note_row.addWidget(QLabel("Note:"))
        note_row.addWidget(wf_note_edit)
        entry_layout.addLayout(note_row)

        # Insert before stretch
        count = self._workflows_layout.count()
        if count > 0 and self._workflows_layout.itemAt(count - 1).spacerItem():
            self._workflows_layout.insertWidget(count - 1, entry_widget)
        else:
            self._workflows_layout.addWidget(entry_widget)

        # Store widgets
        self._workflow_entry_widgets[wf_name] = {
            "widget": entry_widget,
            "name_edit": wf_name_edit,
            "path_edit": wf_path_edit,
            "iteratable_check": wf_iteratable,
            "full_restart_check": wf_full_restart,
            "restart_lowvram_check": wf_restart_lowvram,
            "note_edit": wf_note_edit,
            "node_overrides": wf_config.get("node_overrides", {})
        }

    def _on_remove_workflow(self, widget: QWidget, original_name: str):
        """Remove a workflow entry."""
        if original_name in self._workflow_entry_widgets:
            del self._workflow_entry_widgets[original_name]
        widget.deleteLater()

    def _on_browse_wf_path(self, path_edit: QLineEdit):
        """Browse for workflow path (for multi-workflow entries)."""
        from file_dialogs import browse_file_with_memory

        file_path = browse_file_with_memory(
            self,
            context="comfyui_workflow",
            title="Select ComfyUI Workflow File",
            file_filter="JSON Files (*.json);;All Files (*)",
            fallback_path=os.path.expanduser("~")
        )
        if file_path:
            path_edit.setText(file_path)

    # =========================================================================
    # EXPOSED PARAMETERS TAB
    # =========================================================================

    def _setup_exposed_params_tab(self):
        """Set up the Exposed Parameters tab.

        Shows editable parameters from the workflow with toggles to control
        visibility and optional default values. Supports both single-workflow
        and multi-workflow modes.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)

        # Workflow selector (only visible in multi-workflow mode)
        self._exposed_wf_selector = QComboBox()
        self._exposed_wf_selector.currentTextChanged.connect(self._on_exposed_wf_changed)
        self._exposed_wf_selector_label = QLabel("Workflow:")
        selector_row = QHBoxLayout()
        selector_row.addWidget(self._exposed_wf_selector_label)
        selector_row.addWidget(self._exposed_wf_selector, 1)
        layout.addLayout(selector_row)
        # Hide selector by default; shown when multi-workflow mode is active
        self._exposed_wf_selector.setVisible(False)
        self._exposed_wf_selector_label.setVisible(False)

        # Info label
        info_label = QLabel("Toggle which parameters are visible to users. "
                            "Optionally set default values for text/string parameters.")
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Scroll area for parameter rows
        self._exposed_scroll = QScrollArea()
        self._exposed_scroll.setWidgetResizable(True)
        self._exposed_scroll.setStyleSheet(
            "QScrollArea { background-color: #1e1e1e; border: 1px solid #3c3c3c; }"
        )

        self._exposed_container = QWidget()
        self._exposed_layout = QVBoxLayout(self._exposed_container)
        self._exposed_layout.setContentsMargins(10, 10, 10, 10)
        self._exposed_layout.setSpacing(6)
        self._exposed_scroll.setWidget(self._exposed_container)
        layout.addWidget(self._exposed_scroll, 1)

        self._exposed_params_tab_index = self._tabs.count()
        self._tabs.addTab(tab, "Exposed Parameters")

    def _on_tab_changed(self, index: int):
        """Handle tab change — refresh exposed params lazily."""
        if index == self._exposed_params_tab_index and self._exposed_params_dirty:
            self._refresh_exposed_params()
            self._exposed_params_dirty = False

    def _mark_exposed_params_dirty(self):
        """Mark exposed params for refresh on next tab selection."""
        self._exposed_params_dirty = True

    def _on_exposed_wf_changed(self, wf_name: str):
        """Handle workflow selector change in exposed params tab."""
        if not wf_name:
            return
        # Save current overrides before switching
        self._save_current_exposed_overrides()
        self._current_exposed_wf = wf_name
        self._refresh_exposed_params()

    def _save_current_exposed_overrides(self):
        """Save the current exposed parameter overrides to the appropriate storage."""
        if not self._exposed_param_widgets:
            return

        overrides = self._collect_exposed_param_overrides()
        is_multi = self._is_multi_check.isChecked()

        if is_multi and self._current_exposed_wf:
            self._multi_overrides[self._current_exposed_wf] = overrides
        # For single-workflow, overrides are collected at save time

    def _refresh_exposed_params(self):
        """Refresh the exposed parameters list from the current workflow."""
        # Clear existing widgets
        while self._exposed_layout.count():
            item = self._exposed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._exposed_param_widgets.clear()

        is_multi = self._is_multi_check.isChecked()

        # Update selector visibility
        self._exposed_wf_selector.setVisible(is_multi)
        self._exposed_wf_selector_label.setVisible(is_multi)

        if is_multi:
            # Populate workflow selector from current workflow entries
            self._exposed_wf_selector.blockSignals(True)
            self._exposed_wf_selector.clear()
            for original_name, wf_widgets in self._workflow_entry_widgets.items():
                display_name = wf_widgets["name_edit"].text().strip() or original_name
                self._exposed_wf_selector.addItem(display_name)
            self._exposed_wf_selector.blockSignals(False)

            if self._exposed_wf_selector.count() == 0:
                self._add_no_params_label("No workflows configured. Add workflows in the Workflows tab.")
                return

            # Select current or first
            if self._current_exposed_wf and self._exposed_wf_selector.findText(self._current_exposed_wf) >= 0:
                self._exposed_wf_selector.setCurrentText(self._current_exposed_wf)
            else:
                self._current_exposed_wf = self._exposed_wf_selector.currentText()

            # Find the workflow path for the selected workflow
            workflow_path, node_overrides = self._get_exposed_wf_info(self._current_exposed_wf)
        else:
            workflow_path = self._path_edit.text().strip()
            node_overrides = self.preset_data.get("node_overrides", {})

        if not workflow_path or not os.path.exists(workflow_path):
            self._add_no_params_label("No workflow selected or file not found.")
            return

        editable_nodes = self.extract_editable_nodes(workflow_path)
        if not editable_nodes:
            self._add_no_params_label("No editable parameters found in this workflow.")
            return

        # Build parameter rows
        for node in editable_nodes:
            override_key = f"{node.node_id}:{node.widget_name}" if node.widget_name else str(node.node_id)
            # Look up existing override (try per-param key, then legacy node_id, then title)
            override = node_overrides.get(
                override_key,
                node_overrides.get(str(node.node_id), node_overrides.get(node.title, {}))
            )
            is_enabled = override.get("enabled", True)
            default_value = override.get("default_value", "")

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(8)

            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(is_enabled)
            checkbox.setToolTip("Show this parameter in the UI")
            checkbox.setFixedWidth(20)
            row_layout.addWidget(checkbox)

            # Display name
            name_label = QLabel(node.display_name)
            name_label.setMinimumWidth(180)
            name_label.setMaximumWidth(250)
            name_label.setStyleSheet("color: #e0e0e0;")
            name_label.setToolTip(
                f"Node: {node.title}\nID: {node.node_id}\n"
                f"Type: {node.node_type}\nWidget: {node.widget_name or 'value'}"
            )
            row_layout.addWidget(name_label)

            # Type badge
            type_badge = QLabel(node.widget_type)
            type_badge.setFixedWidth(60)
            type_badge.setAlignment(Qt.AlignCenter)
            type_badge.setStyleSheet(
                "color: #888; background-color: #333; border-radius: 3px; "
                "padding: 1px 4px; font-size: 10px;"
            )
            row_layout.addWidget(type_badge)

            # Default value input (text/string only)
            if node.widget_type in ('text', 'string'):
                default_input = QLineEdit()
                default_input.setPlaceholderText("Default value...")
                default_input.setText(default_value)
                default_input.setToolTip("Pre-fill this value (leave empty to use workflow default)")
                row_layout.addWidget(default_input, 1)
            else:
                default_input = None
                row_layout.addStretch(1)

            self._exposed_layout.addWidget(row)
            self._exposed_param_widgets[override_key] = {
                "checkbox": checkbox,
                "default_input": default_input,
                "node": node,
            }

        self._exposed_layout.addStretch()

    def _add_no_params_label(self, text: str):
        """Add an informational label to the exposed params area."""
        label = QLabel(text)
        label.setStyleSheet("color: #888; font-style: italic;")
        label.setWordWrap(True)
        self._exposed_layout.addWidget(label)
        self._exposed_layout.addStretch()

    def _get_exposed_wf_info(self, wf_display_name: str):
        """Get workflow path and node_overrides for a multi-workflow entry by display name.

        Returns:
            Tuple of (workflow_path, node_overrides)
        """
        for original_name, wf_widgets in self._workflow_entry_widgets.items():
            actual_name = wf_widgets["name_edit"].text().strip() or original_name
            if actual_name == wf_display_name:
                path = wf_widgets["path_edit"].text().strip()
                # Use multi_overrides if we have them, otherwise fall back to stored preset data
                overrides = self._multi_overrides.get(
                    wf_display_name,
                    wf_widgets.get("node_overrides", {})
                )
                return path, overrides
        return "", {}

    def _collect_exposed_param_overrides(self) -> Dict[str, Any]:
        """Collect overrides from the current exposed parameter widgets.

        Only stores overrides for parameters that are disabled or have a
        non-empty default value.

        Returns:
            Dict mapping override_key -> {"enabled": bool, "default_value": str}
        """
        overrides = {}
        for key, widgets in self._exposed_param_widgets.items():
            is_enabled = widgets["checkbox"].isChecked()
            default_input = widgets["default_input"]
            default_value = default_input.text().strip() if default_input else ""

            if not is_enabled or default_value:
                overrides[key] = {
                    "enabled": is_enabled,
                    "default_value": default_value,
                }
        return overrides

    def _setup_thumbnail_tab(self):
        """Set up the Thumbnail tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)

        # Preview
        preview_frame = QFrame()
        preview_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
        """)
        preview_layout = QVBoxLayout(preview_frame)

        self._thumb_preview = QLabel()
        self._thumb_preview.setAlignment(Qt.AlignCenter)
        self._thumb_preview.setMinimumSize(300, 200)
        self._thumb_preview.setStyleSheet("color: #666;")
        self._thumb_preview.setText("No thumbnail")
        preview_layout.addWidget(self._thumb_preview)

        layout.addWidget(preview_frame)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        upload_btn = QPushButton("Upload Image...")
        upload_btn.clicked.connect(self._on_upload_thumbnail)
        btn_layout.addWidget(upload_btn)

        generate_btn = QPushButton("Generate from Gallery")
        generate_btn.setToolTip("Use the highest-rated output as thumbnail")
        generate_btn.clicked.connect(self._on_generate_thumbnail)
        btn_layout.addWidget(generate_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._on_clear_thumbnail)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

        self._tabs.addTab(tab, "Thumbnail")

    def _setup_tags_tab(self):
        """Set up the Tags tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel("Select tags to categorize this model:")
        label.setStyleSheet("color: #888;")
        layout.addWidget(label)

        # Tags grid
        tags_frame = QFrame()
        tags_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
        """)
        tags_layout = QGridLayout(tags_frame)
        tags_layout.setContentsMargins(15, 15, 15, 15)
        tags_layout.setSpacing(10)

        # Get current tags for this model
        rating_data = get_model_rating(self.model_name)
        current_tags = rating_data.get("tags", [])

        self._tag_checks: Dict[str, QCheckBox] = {}
        predefined = get_predefined_tags()

        cols = 3
        for i, tag in enumerate(predefined):
            check = QCheckBox(tag)
            check.setChecked(tag in current_tags)
            check.setStyleSheet("color: #e0e0e0;")
            self._tag_checks[tag] = check
            tags_layout.addWidget(check, i // cols, i % cols)

        layout.addWidget(tags_frame)
        layout.addStretch()

        self._tabs.addTab(tab, "Tags")

    def _setup_ratings_tab(self):
        """Set up the Ratings tab (admin only)."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)

        # Get rating data
        rating_data = get_model_rating(self.model_name)
        ratings = rating_data.get("ratings", {})
        average = rating_data.get("average", 0.0)
        count = rating_data.get("rating_count", 0)

        # Summary
        summary_layout = QHBoxLayout()

        avg_label = QLabel(f"Average: {average:.1f}")
        avg_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #fbbf24;")
        summary_layout.addWidget(avg_label)

        count_label = QLabel(f"({count} ratings)")
        count_label.setStyleSheet("color: #888; font-size: 14px;")
        summary_layout.addWidget(count_label)

        summary_layout.addStretch()
        layout.addLayout(summary_layout)

        # Star rating display
        self._rating_display = StarRatingWidget(rating=average, interactive=False, size=24)
        layout.addWidget(self._rating_display)

        # Breakdown
        breakdown_label = QLabel("Rating Distribution:")
        breakdown_label.setStyleSheet("color: #888; margin-top: 20px;")
        layout.addWidget(breakdown_label)

        self._rating_breakdown = RatingBreakdownWidget()
        self._rating_breakdown.set_ratings(ratings)
        layout.addWidget(self._rating_breakdown)

        # Clear ratings button
        layout.addSpacing(20)

        clear_layout = QHBoxLayout()
        clear_layout.addStretch()

        clear_btn = QPushButton("Clear All Ratings")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ef4444;
                border: 1px solid #ef4444;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: white;
            }
        """)
        clear_btn.clicked.connect(self._on_clear_ratings)
        clear_layout.addWidget(clear_btn)

        layout.addLayout(clear_layout)
        layout.addStretch()

        self._tabs.addTab(tab, "Ratings")

    def _connect_signals(self):
        """Connect signals."""
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _load_data(self):
        """Load current data into UI."""
        # Load thumbnail
        rating_data = get_model_rating(self.model_name)
        thumb_path = rating_data.get("thumbnail_path")
        self._update_thumbnail_preview(thumb_path)

    def _update_thumbnail_preview(self, path: Optional[str]):
        """Update thumbnail preview."""
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    300, 200,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._thumb_preview.setPixmap(scaled)
                self._thumb_path = path
                return

        self._thumb_preview.setText("No thumbnail")
        self._thumb_path = None

    def _on_browse_workflow(self):
        """Browse for workflow file."""
        from file_dialogs import browse_file_with_memory

        file_path = browse_file_with_memory(
            self,
            context="comfyui_workflow",
            title="Select ComfyUI Workflow File",
            file_filter="JSON Files (*.json);;All Files (*)",
            fallback_path=os.path.expanduser("~")
        )
        if file_path:
            self._path_edit.setText(file_path)

    def _on_upload_thumbnail(self):
        """Upload a custom thumbnail."""
        from file_dialogs import browse_file_with_memory

        file_path = browse_file_with_memory(
            self,
            context="comfyui_thumbnails",
            title="Select Thumbnail Image",
            file_filter="Images (*.png *.jpg *.jpeg *.webp);;All Files (*)",
            fallback_path=os.path.expanduser("~")
        )
        if file_path:
            # Copy to thumbnails directory
            from core.settings_manager import get_setting
            from shutil import copy2

            network_path = get_setting("network_output_path")
            if network_path:
                thumb_dir = os.path.join(network_path, "_model_thumbnails")
                ensure_directory(thumb_dir)

                # Generate unique filename
                ext = os.path.splitext(file_path)[1]
                safe_name = self.model_name.replace("/", "_").replace("\\", "_")
                dest_path = os.path.join(thumb_dir, f"{safe_name}{ext}")

                try:
                    copy2(file_path, dest_path)
                    set_model_thumbnail(self.model_name, dest_path, "manual")
                    self._update_thumbnail_preview(dest_path)
                except Exception as e:
                    logger.error(f"Failed to copy thumbnail: {e}")

    def _on_generate_thumbnail(self):
        """Generate thumbnail from highest-rated gallery output."""
        # TODO: Implement auto-thumbnail generation
        # This would scan gallery metadata for outputs from this workflow
        # and use the highest-rated one as the thumbnail
        from dialog_helpers import show_info
        show_info(
            "Not Implemented",
            "Auto-thumbnail generation from gallery is not yet implemented.\n\n"
            "Please upload a thumbnail manually.",
            self
        )

    def _on_clear_thumbnail(self):
        """Clear the current thumbnail."""
        set_model_thumbnail(self.model_name, None, None)
        self._update_thumbnail_preview(None)

    def _on_clear_ratings(self):
        """Clear all ratings for this model."""
        from dialog_helpers import confirm_action

        if confirm_action(
            "Clear Ratings",
            f"Clear all ratings for '{self.model_name}'?\n\n"
            "This cannot be undone.",
            self
        ):
            clear_model_ratings(self.model_name)
            # Refresh display
            self._rating_display.set_rating(0.0)
            self._rating_breakdown.set_ratings({})

    def _on_save(self):
        """Save the model configuration."""
        from comfyui.presets_manager import delete_comfyui_workflow_preset, save_comfyui_workflow_preset
        from dialog_helpers import show_warning

        new_name = self._name_edit.text().strip()
        if not new_name:
            show_warning("Invalid Name", "Model name cannot be empty.", self)
            return

        is_multi = self._is_multi_check.isChecked()
        output_type = self._output_type_map.get(self._output_type_combo.currentText(), "image")

        # Collect fields - save to CORRECT semantic keys (migration happens on save)
        # Description field → "description" key (correct semantic name)
        new_description = self._description_edit.text().strip()
        # Notes field → "note" key (correct semantic name)
        new_note = self._notes_edit.toPlainText().strip()

        # Save any in-progress exposed param edits before collecting
        self._save_current_exposed_overrides()

        if is_multi:
            # Multi-workflow mode: collect all workflows
            new_workflows = {}
            for original_wf_name, wf_widgets in self._workflow_entry_widgets.items():
                actual_wf_name = wf_widgets["name_edit"].text().strip()
                if not actual_wf_name:
                    show_warning("Invalid Workflow", "All workflow names must be filled.", self)
                    return

                wf_path = wf_widgets["path_edit"].text().strip()
                if not wf_path:
                    show_warning("Invalid Workflow", f"Workflow '{actual_wf_name}' path cannot be empty.", self)
                    return

                # Use exposed param overrides if available, otherwise fall back to stored overrides
                wf_overrides = self._multi_overrides.get(
                    actual_wf_name,
                    wf_widgets.get("node_overrides", {})
                )

                new_workflows[actual_wf_name] = {
                    "path": wf_path,
                    "note": wf_widgets["note_edit"].text().strip(),
                    "iteratable": wf_widgets["iteratable_check"].isChecked(),
                    "full_restart": wf_widgets["full_restart_check"].isChecked(),
                    "restart_lowvram": wf_widgets["restart_lowvram_check"].isChecked(),
                    "node_overrides": wf_overrides
                }

            if not new_workflows:
                show_warning("No Workflows", "At least one workflow must be added in multi-workflow mode.", self)
                return

            # In multi-workflow mode, these are not used (each workflow has its own)
            new_path = None
            new_iteratable = False
            new_full_restart = False
            new_restart_lowvram = False
            new_node_overrides = {}
            # But description and note apply to the overall model
        else:
            # Single workflow mode
            new_path = self._path_edit.text().strip()
            if not new_path:
                show_warning("Invalid Path", "Workflow path cannot be empty.", self)
                return

            new_workflows = None
            new_iteratable = self._iteratable_check.isChecked()
            new_full_restart = self._full_restart_check.isChecked()
            new_restart_lowvram = self._restart_lowvram_check.isChecked() if new_full_restart else False
            # Use exposed param overrides if the tab was visited, otherwise keep existing
            if self._exposed_param_widgets:
                new_node_overrides = self._collect_exposed_param_overrides()
            else:
                new_node_overrides = self.preset_data.get("node_overrides", {})

        # Collect tags
        selected_tags = [
            tag for tag, check in self._tag_checks.items()
            if check.isChecked()
        ]

        # Save tags to ratings
        set_model_tags(self.model_name, selected_tags)

        # Delete old preset and save new one (handles both update and rename)
        if new_name != self.model_name:
            from comfyui.ratings import rename_model_data
            delete_comfyui_workflow_preset(self.model_name)
            rename_model_data(self.model_name, new_name)

        save_comfyui_workflow_preset(
            new_name,
            workflow_path=new_path or "",
            description=new_description,
            iteratable=new_iteratable,
            note=new_note,
            full_restart=new_full_restart,
            restart_lowvram=new_restart_lowvram,
            node_overrides=new_node_overrides,
            is_multi=is_multi,
            workflows=new_workflows,
            output_type=output_type
        )

        self.result_accepted = True
        self.accept()
