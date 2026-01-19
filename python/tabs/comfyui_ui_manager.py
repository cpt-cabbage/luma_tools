"""
ComfyUI UI Manager Module.

Handles dynamic UI widget creation and management for editable nodes.
Extracted from comfyui_tab.py to improve maintainability.
"""

import os
from typing import Dict, Any, Optional, List, Tuple

from PySide6 import QtWidgets
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog
)


class ComfyUIWidgetManager:
    """Manages dynamic widget creation and state for ComfyUI editable nodes."""

    def __init__(self, main_window, app_state, layout):
        """
        Initialize the widget manager.

        Args:
            main_window: Main application window (for dialogs and animator)
            app_state: Application state object
            layout: Qt layout to add widgets to
        """
        self.main_window = main_window
        self.app_state = app_state
        self.layout = layout

        # Widget tracking
        self.dynamic_widgets = {}  # node_id -> widget container
        self.condition_map = {}  # Maps condition_node_name -> list of dependent widget node_ids

        # Pending values (for restoration after widget recreation)
        self.pending_editable_values = {}
        self.pending_semantic_values = {}

    def clear_widgets(self):
        """Clear all dynamic widgets from the layout."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.dynamic_widgets = {}
        self.condition_map = {}

    def capture_editable_values_by_type(self) -> Dict[str, Any]:
        """
        Capture current editable values keyed by widget type and display name.

        Used to preserve values when switching workflows in multi-workflow presets.
        Returns dict like: {'text/Prompt': 'value', 'text/Negative': 'value2', ...}
        """
        values = {}
        for node_id, container in self.dynamic_widgets.items():
            node = getattr(container, 'editable_node', None)
            input_widget = getattr(container, 'input_widget', None)
            if node and input_widget:
                # Create semantic key: widget_type/display_name
                semantic_key = f"{node.widget_type}/{node.display_name}"
                if hasattr(input_widget, 'toPlainText'):
                    values[semantic_key] = input_widget.toPlainText()
                elif hasattr(input_widget, 'text'):
                    values[semantic_key] = input_widget.text()
                elif hasattr(input_widget, 'isChecked'):
                    values[semantic_key] = input_widget.isChecked()
                elif hasattr(input_widget, 'selected_files'):
                    # BatchImageSelector - capture image paths
                    values[semantic_key] = input_widget.selected_files.copy()
        return values

    def refresh_editable_nodes(self, workflow_path: Optional[str], node_overrides: Dict[str, Any]):
        """
        Refresh dynamic UI widgets based on editable nodes in the workflow.

        Args:
            workflow_path: Path to the workflow JSON file
            node_overrides: Dict of node overrides (enabled/default_value)
        """
        from comfyui.service import extract_editable_nodes

        self.clear_widgets()

        if not workflow_path:
            return

        editable_nodes = extract_editable_nodes(workflow_path)

        # First pass: create all widgets (skip disabled nodes)
        for node in editable_nodes:
            # Check if this node is disabled via overrides
            override = node_overrides.get(node.title, {})
            if not override.get("enabled", True):
                # Node is disabled, skip it
                continue

            # Apply default value override if present (for text and string nodes)
            default_value = override.get("default_value", "")
            if default_value and node.widget_type in ('text', 'string'):
                # Override the current_value with the default
                node.current_value = default_value

            widget = self._create_editable_node_widget(node)
            if widget:
                self.layout.addWidget(widget)
                self.dynamic_widgets[node.node_id] = widget
                # Store the node info on the widget for condition handling
                widget.editable_node = node

        # Second pass: set up conditional visibility connections
        for node in editable_nodes:
            # Skip disabled nodes
            override = node_overrides.get(node.title, {})
            if not override.get("enabled", True):
                continue

            if node.condition_node:
                # Find the toggle widget that controls this node's visibility
                toggle_widget = self._find_toggle_widget_by_name(node.condition_node)
                if toggle_widget:
                    # Register this widget as dependent on the toggle
                    if node.condition_node not in self.condition_map:
                        self.condition_map[node.condition_node] = []
                    self.condition_map[node.condition_node].append(node.node_id)

                    # Set initial visibility based on toggle state
                    dependent_widget = self.dynamic_widgets.get(node.node_id)
                    if dependent_widget and hasattr(toggle_widget, 'input_widget'):
                        checkbox = toggle_widget.input_widget
                        if hasattr(checkbox, 'isChecked'):
                            dependent_widget.setVisible(checkbox.isChecked())

        # Apply any pending editable values from restored state
        self._apply_pending_editable_values()

        # Apply semantic values (for workflow switching within multi-workflow presets)
        self._apply_semantic_editable_values()

    def _find_toggle_widget_by_name(self, condition_name):
        """Find a toggle widget by the condition node name."""
        for node_id, widget in self.dynamic_widgets.items():
            node = getattr(widget, 'editable_node', None)
            if node:
                # Match by display name (base title without _editable)
                # The condition_name is the base title of the controlling node
                is_edit, base_title, _ = self._parse_node_title(node.title)
                if base_title == condition_name:
                    return widget
        return None

    def _parse_node_title(self, title: str) -> Tuple[bool, str, Optional[str]]:
        """Parse node title for editable marker and condition (mirrors comfyui_service logic)."""
        editable_markers = ['_editable', '_editble']
        is_editable = False
        condition_node = None
        base_title = title

        for marker in editable_markers:
            if marker in title:
                is_editable = True
                parts = title.split(marker)
                base_title = parts[0]
                if len(parts) > 1:
                    after_marker = parts[1]
                    for sep in ['@if_', '&if_']:
                        if after_marker.startswith(sep):
                            condition_node = after_marker[len(sep):]
                            break
                break

        return is_editable, base_title, condition_node

    def on_toggle_changed(self, checked: bool, toggle_node_name: str):
        """Handle toggle widget state change - update visibility of dependent widgets."""
        dependent_node_ids = self.condition_map.get(toggle_node_name, [])
        for node_id in dependent_node_ids:
            widget = self.dynamic_widgets.get(node_id)
            if widget:
                widget.setVisible(checked)

    def _create_editable_node_widget(self, node):
        """Create a widget for an editable node."""
        from ui_components import BatchImageSelector
        from ui.spell_checker import SpellCheckTextEdit
        from core.user_preferences import get_last_browse_directory

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 5, 0, 5)

        if node.widget_type == 'toggle':
            # Toggle/switch widget - displayed as checkbox
            # Parse the base name for the toggle label
            _, base_title, _ = self._parse_node_title(node.title)
            toggle_name = base_title.replace('_', ' ')

            input_widget = QtWidgets.QCheckBox(toggle_name)
            # Index 0 = unchecked (first input), Index 1 = checked (second input)
            # For switch nodes, value != 0 means use second input
            is_checked = bool(node.current_value) if node.current_value else False
            input_widget.setChecked(is_checked)

            layout.addWidget(input_widget)
            container.input_widget = input_widget
            container.toggle_name = base_title  # Store for condition matching

        elif node.widget_type == '3d_model':
            # 3D model selector - file browser for GLB/OBJ/FBX files
            label = QLabel(f"{node.display_name}:")
            layout.addWidget(label)

            file_row = QHBoxLayout()
            file_path_edit = QLineEdit()
            file_path_edit.setPlaceholderText("Select a 3D model file (GLB, OBJ, FBX)...")
            if node.current_value:
                file_path_edit.setText(str(node.current_value))
            file_row.addWidget(file_path_edit)

            browse_btn = QPushButton("Browse...")
            browse_btn.setFixedWidth(80)
            browse_btn.clicked.connect(
                lambda checked=False, edit=file_path_edit: self._browse_3d_model(edit)
            )
            file_row.addWidget(browse_btn)
            layout.addLayout(file_row)

            container.input_widget = file_path_edit

        elif node.widget_type == 'text':
            label = QLabel(f"{node.display_name}:")
            layout.addWidget(label)

            # Add preset row with button (will be connected by tab)
            preset_row = QHBoxLayout()
            preset_btn = QPushButton("Presets")
            preset_btn.setFixedWidth(100)
            preset_row.addWidget(preset_btn)
            preset_row.addStretch()
            layout.addLayout(preset_row)

            # Text input with spell checking
            input_widget = SpellCheckTextEdit()
            input_widget.setMinimumHeight(60)
            if node.current_value:
                input_widget.setPlainText(str(node.current_value))
            layout.addWidget(input_widget)
            container.input_widget = input_widget
            container.node_type = node.node_type  # Store node type for preset lookup
            container.preset_btn = preset_btn  # Store button for signal connection

        elif node.widget_type == 'image':
            label = QLabel(f"{node.display_name}:")
            layout.addWidget(label)

            input_widget = BatchImageSelector()
            # Set last browse directory for image selector
            last_dir = get_last_browse_directory("comfyui_images")
            if last_dir:
                input_widget.set_last_browse_dir(last_dir)
            layout.addWidget(input_widget)
            container.input_widget = input_widget

        else:
            # Default: generic line edit for strings, ints, floats
            label = QLabel(f"{node.display_name}:")
            layout.addWidget(label)

            input_widget = QLineEdit()
            if node.current_value:
                input_widget.setText(str(node.current_value))
            layout.addWidget(input_widget)
            container.input_widget = input_widget

        return container

    def _browse_3d_model(self, line_edit):
        """Open file browser for 3D model selection."""
        from core.user_preferences import get_last_browse_directory, set_last_browse_directory

        last_dir = get_last_browse_directory("comfyui_3d_models") or ""
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Select 3D Model",
            last_dir,
            "3D Models (*.glb *.gltf *.obj *.fbx *.usd *.usda *.usdc *.usdz);;All Files (*)"
        )
        if file_path:
            line_edit.setText(file_path)
            set_last_browse_directory("comfyui_3d_models", os.path.dirname(file_path))

    def _apply_pending_editable_values(self):
        """Apply pending editable values that were saved from a previous session."""
        if not self.pending_editable_values:
            return

        for node_id_str, value in self.pending_editable_values.items():
            try:
                node_id = int(node_id_str)
                if node_id in self.dynamic_widgets:
                    container = self.dynamic_widgets[node_id]
                    input_widget = getattr(container, 'input_widget', None)
                    if input_widget:
                        if hasattr(input_widget, 'setPlainText'):
                            input_widget.setPlainText(value)
                        elif hasattr(input_widget, 'setText'):
                            input_widget.setText(value)
                        elif hasattr(input_widget, 'set_images') and isinstance(value, list):
                            # BatchImageSelector - restore image paths
                            input_widget.set_images(value)
            except (ValueError, AttributeError):
                pass  # Silently skip if restoration fails

        # Clear pending values after applying
        self.pending_editable_values = {}

    def _apply_semantic_editable_values(self):
        """
        Apply pending semantic values to newly created widgets.

        Used when switching workflows within a multi-workflow preset to preserve
        prompt values etc. that match by widget type and display name.
        """
        if not self.pending_semantic_values:
            return

        for node_id, container in self.dynamic_widgets.items():
            node = getattr(container, 'editable_node', None)
            input_widget = getattr(container, 'input_widget', None)
            if node and input_widget:
                semantic_key = f"{node.widget_type}/{node.display_name}"
                if semantic_key in self.pending_semantic_values:
                    value = self.pending_semantic_values[semantic_key]
                    if hasattr(input_widget, 'setPlainText'):
                        input_widget.setPlainText(str(value))
                    elif hasattr(input_widget, 'setText'):
                        input_widget.setText(str(value))
                    elif hasattr(input_widget, 'setChecked'):
                        input_widget.setChecked(bool(value))
                    elif hasattr(input_widget, 'set_images') and isinstance(value, list):
                        # BatchImageSelector - restore image paths
                        input_widget.set_images(value)

        # Clear pending semantic values after applying
        self.pending_semantic_values = {}

    def collect_editable_values(self) -> Tuple[Dict[int, Dict[str, Any]], int]:
        """
        Collect editable values from dynamic widgets.

        Returns:
            Tuple of (editable_values dict, selected_image_count)
        """
        from comfyui.service import extract_editable_nodes

        editable_values = {}
        selected_image_count = 0

        if not self.app_state.comfyui_workflow_path:
            return editable_values, selected_image_count

        editable_nodes = extract_editable_nodes(self.app_state.comfyui_workflow_path)

        for node in editable_nodes:
            node_id = node.node_id
            if node_id in self.dynamic_widgets:
                container = self.dynamic_widgets[node_id]
                input_widget = getattr(container, 'input_widget', None)
                if input_widget:
                    if node.widget_type == 'text':
                        value = input_widget.toPlainText().strip()
                    elif node.widget_type == 'image':
                        value = getattr(input_widget, 'selected_files', [])
                        selected_image_count = max(selected_image_count, len(value) if value else 0)
                    else:
                        value = input_widget.text().strip() if hasattr(input_widget, 'text') else str(node.current_value)

                    editable_values[node_id] = {'node': node, 'value': value}

        return editable_values, selected_image_count

    def get_editable_values_for_state(self) -> Dict[str, Any]:
        """Get editable values in a format suitable for state persistence."""
        editable_values = {}
        for node_id, container in self.dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget:
                if hasattr(input_widget, 'toPlainText'):
                    editable_values[str(node_id)] = input_widget.toPlainText()
                elif hasattr(input_widget, 'text'):
                    editable_values[str(node_id)] = input_widget.text()
                elif hasattr(input_widget, 'selected_files'):
                    # BatchImageSelector - save image paths
                    editable_values[str(node_id)] = input_widget.selected_files.copy()
        return editable_values
