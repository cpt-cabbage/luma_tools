"""
ComfyUI UI Manager Module.

Handles dynamic UI widget creation and management for editable nodes.
Extracted from comfyui_tab.py to improve maintainability.
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple

from PySide6 import QtWidgets

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy
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
        self.dynamic_widgets = {}  # (node_id, widget_name) -> widget container
        self.condition_map = {}  # Maps condition_node_name -> list of dependent widget node_ids
        self.settings_widgets = {}  # node_id -> widget container for settings nodes
        self._settings_dialog = None  # Settings dialog (opened from button)

        # Pending values (for restoration after widget recreation)
        self.pending_editable_values = {}
        self.pending_semantic_values = {}
        self.pending_settings_values = {}  # For settings node restoration

    def _get_node_override(self, node, node_overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Get override dict for a node, supporting per-parameter keys.

        Key format: "{node_id}:{widget_name}" for per-parameter granularity,
        falling back to "{node_id}" then title for legacy compatibility.
        """
        if node.widget_name:
            key = f"{node.node_id}:{node.widget_name}"
            if key in node_overrides:
                return node_overrides[key]
        # Fall back to node_id then title (legacy)
        return node_overrides.get(str(node.node_id), node_overrides.get(node.title, {}))

    def clear_widgets(self):
        """Clear all dynamic widgets from the layout."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        # Clear the layout's cached size constraints so new widgets
        # get a fresh calculation instead of inheriting stale values.
        self.layout.invalidate()

        self.dynamic_widgets = {}
        self.condition_map = {}
        self.settings_widgets = {}
        if self._settings_dialog:
            self._settings_dialog.close()
            self._settings_dialog.deleteLater()
            self._settings_dialog = None

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
        from comfyui.editable import extract_editable_nodes

        self.clear_widgets()

        # Flush pending deleteLater() calls before adding new widgets.
        # Without this, Qt's layout engine can retain stale size hints from
        # widgets that are detached but not yet destroyed, causing overflow
        # when switching from fewer to more widgets.
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        if not workflow_path:
            return

        editable_nodes = extract_editable_nodes(workflow_path)

        # Count total image/video nodes for pairing calculation
        total_image_nodes = sum(1 for node in editable_nodes
                               if node.widget_type == 'image'
                               and self._get_node_override(node, node_overrides).get("enabled", True))
        total_video_nodes = sum(1 for node in editable_nodes
                               if node.widget_type == 'video'
                               and self._get_node_override(node, node_overrides).get("enabled", True))
        logger.info(f"[ComfyUI] Total enabled image nodes: {total_image_nodes}, video nodes: {total_video_nodes}")

        # Collect widgets separately for horizontal layout
        non_image_widgets = []  # List of (widget, node) tuples for text, toggles, etc.
        image_widgets = []  # List of (widget, node) tuples for images and videos (file selectors)

        # First pass: create all widgets (skip disabled nodes)
        for node in editable_nodes:
            # Check if this node is disabled via overrides
            override = self._get_node_override(node, node_overrides)
            if not override.get("enabled", True):
                continue

            # Apply default value override if present (for text and string nodes)
            default_value = override.get("default_value", "")
            if default_value and node.widget_type in ('text', 'string'):
                # Override the current_value with the default
                node.current_value = default_value

            widget = self._create_editable_node_widget(node, total_image_nodes, total_video_nodes)
            if widget:
                # Store the node info on the widget for condition handling
                widget.editable_node = node
                self.dynamic_widgets[(node.node_id, node.widget_name)] = widget

                # Separate file selector widgets (image/video) from non-file widgets
                if node.widget_type in ('image', 'video'):
                    image_widgets.append((widget, node))
                else:
                    non_image_widgets.append((widget, node))

        # Layout strategy: non-image widgets on top, image widgets below in a
        # horizontal row.  This prevents text inputs from competing for width
        # with image selectors and gives images the full available width.
        if non_image_widgets:
            for widget, node in non_image_widgets:
                # Only text widgets (multiline) should expand vertically
                stretch = 1 if node.widget_type == 'text' else 0
                self.layout.addWidget(widget, stretch)

        if image_widgets:
            if len(image_widgets) > 1:
                image_row_container = QWidget()
                image_row_container.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                image_row_layout = QHBoxLayout(image_row_container)
                image_row_layout.setContentsMargins(0, 5, 0, 5)
                image_row_layout.setSpacing(10)

                for widget, node in image_widgets:
                    image_row_layout.addWidget(widget, 1)  # Add stretch factor to expand

                self.layout.addWidget(image_row_container, 1)  # Add stretch to container
                image_row_container.is_image_row = True
            else:
                widget = image_widgets[0][0]
                widget.setVisible(True)
                self.layout.addWidget(widget, 1)  # Add stretch factor

        if not image_widgets and non_image_widgets:
            # Add final stretch to push non-expanding widgets to the top
            self.layout.addStretch()

        # Second pass: set up conditional visibility connections
        for node in editable_nodes:
            # Skip disabled nodes
            override = self._get_node_override(node, node_overrides)
            if not override.get("enabled", True):
                continue

            if node.condition_node:
                # Find the toggle widget that controls this node's visibility
                toggle_widget = self._find_toggle_widget_by_name(node.condition_node)
                if toggle_widget:
                    # Register this widget as dependent on the toggle
                    if node.condition_node not in self.condition_map:
                        self.condition_map[node.condition_node] = []
                    self.condition_map[node.condition_node].append((node.node_id, node.widget_name))

                    # Set initial visibility based on toggle state
                    dependent_widget = self.dynamic_widgets.get((node.node_id, node.widget_name))
                    if dependent_widget and hasattr(toggle_widget, 'input_widget'):
                        checkbox = toggle_widget.input_widget
                        if hasattr(checkbox, 'isChecked'):
                            dependent_widget.setVisible(checkbox.isChecked())

        # Apply any pending editable values from restored state
        self._apply_pending_editable_values()

        # Apply semantic values (for workflow switching within multi-workflow presets)
        self._apply_semantic_editable_values()

        # Defer layout recalculation to next event loop tick.
        # New widgets need one event loop pass to compute their sizeHints
        # before we can force the parent tree to recalculate geometry.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._force_layout_update)

    def _force_layout_update(self):
        """Force full layout recalculation up the widget tree.

        Called on a deferred timer so that newly-added widgets have already
        computed their sizeHints before we invalidate cached geometry.
        """
        self.layout.activate()
        parent = self.layout.parentWidget()
        while parent:
            parent.updateGeometry()
            if parent.layout():
                parent.layout().invalidate()
                parent.layout().activate()
            parent = parent.parentWidget()

    def _create_label_with_tooltip(self, text: str, min_width: int = 160) -> QLabel:
        """Create a label that expands to show full text.

        Args:
            text: Label text
            min_width: Minimum width in pixels

        Returns:
            QLabel configured to expand and show full text
        """
        from PySide6.QtCore import Qt
        label = QLabel(text)
        label.setMinimumWidth(min_width)
        # Allow label to expand horizontally to show full text
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        label.setWordWrap(False)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

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
        dependent_keys = self.condition_map.get(toggle_node_name, [])
        for key in dependent_keys:
            widget = self.dynamic_widgets.get(key)
            if widget:
                widget.setVisible(checked)

    def _create_editable_node_widget(self, node, total_image_nodes=1, total_video_nodes=1):
        """Create a widget for an editable node.

        Args:
            node: EditableNode object
            total_image_nodes: Total number of image nodes in the workflow (for pairing)
            total_video_nodes: Total number of video nodes in the workflow (for pairing)
        """
        from ui_components import BatchImageSelector
        from ui.spell_checker import SpellCheckTextEdit
        from core.user_preferences import get_last_browse_directory

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)

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
            file_row = QHBoxLayout()

            label = self._create_label_with_tooltip(f"{node.display_name}:")
            file_row.addWidget(label)

            file_path_edit = QLineEdit()
            file_path_edit.setPlaceholderText("Select a 3D model file (GLB, OBJ, FBX)...")
            file_path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if node.current_value:
                file_path_edit.setText(str(node.current_value))
            file_row.addWidget(file_path_edit, 1)

            browse_btn = QPushButton("Browse...")
            browse_btn.setFixedWidth(100)
            browse_btn.clicked.connect(
                lambda checked=False, edit=file_path_edit: self._browse_3d_model(edit)
            )
            file_row.addWidget(browse_btn)
            layout.addLayout(file_row)

            container.input_widget = file_path_edit

        elif node.widget_type == 'directory':
            # Directory selector - folder browser
            dir_row = QHBoxLayout()

            label = self._create_label_with_tooltip(f"{node.display_name}:")
            dir_row.addWidget(label)

            dir_path_edit = QLineEdit()
            dir_path_edit.setPlaceholderText("Select a directory...")
            dir_path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if node.current_value:
                dir_path_edit.setText(str(node.current_value))
            dir_row.addWidget(dir_path_edit, 1)

            browse_btn = QPushButton("Browse...")
            browse_btn.setFixedWidth(100)
            browse_btn.clicked.connect(
                lambda checked=False, edit=dir_path_edit: self._browse_directory(edit)
            )
            dir_row.addWidget(browse_btn)
            layout.addLayout(dir_row)

            container.input_widget = dir_path_edit

        elif node.widget_type == 'text':
            # Top row: Label and Presets button
            top_row = QHBoxLayout()
            label = self._create_label_with_tooltip(f"{node.display_name}:")
            top_row.addWidget(label)
            top_row.addStretch()

            preset_btn = QPushButton("Presets")
            preset_btn.setFixedWidth(100)
            top_row.addWidget(preset_btn)
            layout.addLayout(top_row)

            # Text input with spell checking - expands to fill available space
            input_widget = SpellCheckTextEdit()
            input_widget.setMinimumHeight(100)
            input_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            if node.current_value:
                input_widget.setPlainText(str(node.current_value))
            layout.addWidget(input_widget, 1)  # Stretch factor of 1 to expand
            container.input_widget = input_widget
            container.node_type = node.node_type  # Store node type for preset lookup
            container.preset_btn = preset_btn  # Store button for signal connection

        elif node.widget_type == 'image':
            # Create BatchImageSelector first so we can access its toolbar
            input_widget = BatchImageSelector(total_image_nodes=total_image_nodes)
            input_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # Set last browse directory for image selector
            last_dir = get_last_browse_directory("comfyui_images")
            if last_dir:
                input_widget.set_last_browse_dir(last_dir)

            # Insert label at the beginning of the BatchImageSelector's toolbar
            # Use smaller min-width when many image nodes to prevent toolbar truncation
            label_min_w = 0 if total_image_nodes >= 3 else 160
            label = self._create_label_with_tooltip(f"{node.display_name}:", min_width=label_min_w)
            input_widget.toolbar_layout.insertWidget(0, label)

            layout.addWidget(input_widget, 1)  # Stretch factor of 1 to expand
            container.input_widget = input_widget

        elif node.widget_type == 'video':
            # Create BatchImageSelector configured for video files
            input_widget = BatchImageSelector(
                supported_extensions=['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.wmv'],
                total_image_nodes=total_video_nodes,
                file_type_label="videos",
            )
            input_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # Set last browse directory for video selector
            last_dir = get_last_browse_directory("comfyui_videos")
            if last_dir:
                input_widget.set_last_browse_dir(last_dir)

            # Insert label at the beginning of the BatchImageSelector's toolbar
            label_min_w = 0 if total_video_nodes >= 3 else 160
            label = self._create_label_with_tooltip(f"{node.display_name}:", min_width=label_min_w)
            input_widget.toolbar_layout.insertWidget(0, label)

            layout.addWidget(input_widget, 1)  # Stretch factor of 1 to expand
            container.input_widget = input_widget

        else:
            # Default: generic line edit for strings, ints, floats
            row = QHBoxLayout()

            label = self._create_label_with_tooltip(f"{node.display_name}:")
            row.addWidget(label)

            input_widget = QLineEdit()
            input_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if node.current_value:
                input_widget.setText(str(node.current_value))
            row.addWidget(input_widget, 1)
            layout.addLayout(row)
            container.input_widget = input_widget

        return container

    def _browse_3d_model(self, line_edit):
        """Open file browser for 3D model selection."""
        from file_dialogs import browse_file_with_memory

        file_path = browse_file_with_memory(
            self.main_window,
            context="comfyui_3d_models",
            title="Select 3D Model",
            file_filter="3D Models (*.glb *.gltf *.obj *.fbx *.usd *.usda *.usdc *.usdz);;All Files (*)",
            fallback_path=""
        )
        if file_path:
            line_edit.setText(file_path)

    def _browse_directory(self, line_edit):
        """Open directory browser for folder selection."""
        from file_dialogs import browse_directory_with_memory

        dir_path = browse_directory_with_memory(
            self.main_window,
            context="comfyui_directories",
            title="Select Directory",
            fallback_path=""
        )
        if dir_path:
            line_edit.setText(dir_path)

    def _apply_pending_editable_values(self):
        """Apply pending editable values that were saved from a previous session."""
        if not self.pending_editable_values:
            return

        for key_str, value in self.pending_editable_values.items():
            try:
                # Support both new format "node_id:widget_name" and legacy "node_id"
                container = None
                if ':' in key_str:
                    node_id_str, widget_name = key_str.split(':', 1)
                    node_id = int(node_id_str)
                    container = self.dynamic_widgets.get((node_id, widget_name))
                else:
                    node_id = int(key_str)
                    # Legacy: find first widget for this node_id
                    for (nid, wname), cont in self.dynamic_widgets.items():
                        if nid == node_id:
                            container = cont
                            break

                if container:
                    input_widget = getattr(container, 'input_widget', None)
                    if input_widget:
                        if hasattr(input_widget, 'setPlainText'):
                            input_widget.setPlainText(value)
                        elif hasattr(input_widget, 'setText'):
                            input_widget.setText(value)
                        elif hasattr(input_widget, 'set_images') and isinstance(value, list):
                            # BatchImageSelector - restore image paths
                            input_widget.set_images(value)
            except (ValueError, AttributeError) as e:
                logger.debug(f"Skipped restoration of editable value for {key_str}: {e}")

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

    def collect_editable_values(self) -> Tuple[Dict[int, Any], int]:
        """
        Collect editable values from dynamic widgets, including settings nodes.

        Returns:
            Tuple of (editable_values dict, selected_image_count)
            The editable_values dict maps node_id -> list of {'node': EditableNode, 'value': Any}.
            For nodes with a single widget, the list has one entry.
            The dict also includes settings nodes (single-entry lists).
        """
        from comfyui.editable import extract_editable_nodes

        editable_values = {}
        selected_image_count = 0

        if not self.app_state.comfyui_workflow_path:
            return editable_values, selected_image_count

        editable_nodes = extract_editable_nodes(self.app_state.comfyui_workflow_path)

        for node in editable_nodes:
            node_id = node.node_id
            key = (node_id, node.widget_name)
            if key in self.dynamic_widgets:
                container = self.dynamic_widgets[key]
                input_widget = getattr(container, 'input_widget', None)
                if input_widget:
                    if node.widget_type == 'text':
                        value = input_widget.toPlainText().strip()
                    elif node.widget_type in ('image', 'video'):
                        value = getattr(input_widget, 'selected_files', [])
                        selected_image_count = max(selected_image_count, len(value) if value else 0)
                    elif hasattr(input_widget, 'isChecked'):
                        value = input_widget.isChecked()
                    else:
                        value = input_widget.text().strip() if hasattr(input_widget, 'text') else str(node.current_value)

                    if node_id not in editable_values:
                        editable_values[node_id] = []
                    editable_values[node_id].append({'node': node, 'value': value})

        # Also collect settings values - they use list-per-node format too
        settings_values = self.collect_settings_values()
        for nid, entries in settings_values.items():
            if nid not in editable_values:
                editable_values[nid] = []
            if isinstance(entries, list):
                editable_values[nid].extend(entries)
            else:
                # Legacy single-entry format from settings
                editable_values[nid].append(entries)

        return editable_values, selected_image_count

    def get_editable_values_for_state(self) -> Dict[str, Any]:
        """Get editable values in a format suitable for state persistence.

        Keys use "node_id:widget_name" format for multi-widget node support.
        """
        editable_values = {}
        for (node_id, widget_name), container in self.dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget:
                state_key = f"{node_id}:{widget_name}"
                if hasattr(input_widget, 'toPlainText'):
                    editable_values[state_key] = input_widget.toPlainText()
                elif hasattr(input_widget, 'isChecked'):
                    editable_values[state_key] = input_widget.isChecked()
                elif hasattr(input_widget, 'text'):
                    editable_values[state_key] = input_widget.text()
                elif hasattr(input_widget, 'selected_files'):
                    # BatchImageSelector - save image paths
                    editable_values[state_key] = input_widget.selected_files.copy()

        # Also include settings values with a prefix to distinguish them
        for node_id, container in self.settings_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget:
                key = f"settings_{node_id}"
                if hasattr(input_widget, 'isChecked'):
                    editable_values[key] = input_widget.isChecked()
                elif hasattr(input_widget, 'text'):
                    editable_values[key] = input_widget.text()
        return editable_values

    # =========================================================================
    # SETTINGS NODES
    # =========================================================================

    def refresh_settings_nodes(self, workflow_path: Optional[str], node_overrides: Dict[str, Any]):
        """
        Refresh the settings dialog based on settings nodes in the workflow.

        Settings nodes have '_settings' suffix and are displayed in a separate
        dialog grouped by their base title.

        Args:
            workflow_path: Path to the workflow JSON file
            node_overrides: Dict of node overrides (enabled/default_value)
        """
        from comfyui.editable import extract_settings_nodes

        # Track if dialog was visible so we can re-show the new one
        was_visible = self._settings_dialog and self._settings_dialog.isVisible()

        # Clear existing settings widgets and dialog
        self.settings_widgets = {}
        if self._settings_dialog:
            self._settings_dialog.close()
            self._settings_dialog.deleteLater()
            self._settings_dialog = None

        if not workflow_path:
            return

        settings_nodes = extract_settings_nodes(workflow_path)
        if not settings_nodes:
            return

        # Filter out disabled nodes
        enabled_nodes = []
        for node in settings_nodes:
            override = self._get_node_override(node, node_overrides)
            if override.get("enabled", True):
                enabled_nodes.append(node)

        if not enabled_nodes:
            return

        # Group nodes by group_name
        groups: Dict[str, list] = {}
        for node in enabled_nodes:
            if node.group_name not in groups:
                groups[node.group_name] = []
            groups[node.group_name].append(node)

        # Create settings dialog
        self._settings_dialog = self._create_settings_dialog(groups)

        # Apply pending settings values
        self._apply_pending_settings_values()

        # Re-show dialog if it was previously visible
        if was_visible:
            self._settings_dialog.show()

    @property
    def has_settings_nodes(self) -> bool:
        """Whether the current workflow has settings nodes."""
        return bool(self.settings_widgets)

    def show_settings_dialog(self):
        """Show the workflow settings dialog."""
        if self._settings_dialog:
            self._settings_dialog.show()
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()

    def _create_settings_dialog(self, groups: Dict[str, list]):
        """
        Create a dialog containing grouped workflow settings.

        Args:
            groups: Dict mapping group_name -> list of SettingsNode

        Returns:
            QDialog containing all settings
        """
        from PySide6.QtWidgets import QDialog, QFrame, QScrollArea
        from PySide6.QtCore import Qt

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Workflow Settings")
        dialog.setMinimumWidth(450)
        dialog.setMinimumHeight(200)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Scroll area for many settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)

        for group_name, nodes in groups.items():
            group_widget = self._create_settings_group(group_name, nodes)
            content_layout.addWidget(group_widget)

        content_layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        return dialog

    def _create_settings_group(self, group_name: str, nodes: list) -> QWidget:
        """
        Create a group widget containing settings for related nodes.

        Args:
            group_name: Display name for the group
            nodes: List of SettingsNode objects in this group

        Returns:
            Widget containing the grouped settings
        """
        from PySide6.QtWidgets import QFrame, QGridLayout
        from PySide6.QtCore import Qt

        group = QFrame()
        group.setFrameShape(QFrame.StyledPanel)
        group.setObjectName("settingsGroup")
        group.setStyleSheet("""
            QFrame#settingsGroup {
                background-color: #2d2d2d;
                border: 1px solid #444444;
                border-radius: 4px;
            }
            QSpinBox, QDoubleSpinBox, QComboBox {
                color: #cccccc;
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 2px;
                padding: 2px 4px;
            }
        """)

        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(10, 8, 10, 8)
        group_layout.setSpacing(8)

        # Group title
        title = QLabel(group_name)
        title.setStyleSheet("font-weight: bold; color: #aaaaaa; border: none;")
        group_layout.addWidget(title)

        # Grid layout for settings (2 columns for compact display)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)

        row = 0
        col = 0
        for node in nodes:
            widget = self._create_settings_widget(node)
            if widget:
                grid.addWidget(widget, row, col)
                self.settings_widgets[node.node_id] = widget
                col += 1
                if col >= 2:
                    col = 0
                    row += 1

        group_layout.addLayout(grid)
        return group

    def _create_settings_widget(self, node) -> Optional[QWidget]:
        """
        Create a compact widget for a settings node.

        Uses node_info cache for real min/max/step constraints when available,
        falling back to sensible defaults.

        Args:
            node: SettingsNode object

        Returns:
            Widget or None if creation failed
        """
        from PySide6.QtWidgets import QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox
        from PySide6.QtCore import Qt
        from comfyui.node_info import get_widget_info

        # Try to get real constraints from node_info cache
        widget_info = get_widget_info(node.node_type, node.widget_name)

        container = QWidget()
        container.setStyleSheet("border: none;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Label
        label = QLabel(f"{node.widget_name}:")
        label.setStyleSheet("color: #888888; border: none;")
        label.setMinimumWidth(80)
        layout.addWidget(label)

        # Create appropriate input widget based on type
        if node.widget_type == 'toggle':
            input_widget = QCheckBox()
            input_widget.setChecked(bool(node.current_value) if node.current_value else False)
            layout.addWidget(input_widget)

        elif node.widget_type == 'int':
            input_widget = QSpinBox()
            # Use real constraints from node_info, fall back to defaults
            min_val = int(widget_info.min_val) if widget_info and widget_info.min_val is not None else 0
            max_val = int(widget_info.max_val) if widget_info and widget_info.max_val is not None else 999999
            input_widget.setRange(min_val, max_val)
            if widget_info and widget_info.step is not None:
                input_widget.setSingleStep(int(widget_info.step))
            input_widget.setFixedWidth(80)
            if node.current_value is not None:
                try:
                    input_widget.setValue(int(node.current_value))
                except (ValueError, TypeError):
                    pass
            layout.addWidget(input_widget)

        elif node.widget_type == 'float':
            input_widget = QDoubleSpinBox()
            # Use real constraints from node_info, fall back to defaults
            min_val = float(widget_info.min_val) if widget_info and widget_info.min_val is not None else 0.0
            max_val = float(widget_info.max_val) if widget_info and widget_info.max_val is not None else 999999.0
            step = float(widget_info.step) if widget_info and widget_info.step is not None else 0.1
            input_widget.setRange(min_val, max_val)
            input_widget.setSingleStep(step)
            # Auto-detect decimal places from step size
            if step >= 1.0:
                input_widget.setDecimals(0)
            elif step >= 0.1:
                input_widget.setDecimals(2)
            else:
                input_widget.setDecimals(4)
            input_widget.setFixedWidth(80)
            if node.current_value is not None:
                try:
                    input_widget.setValue(float(node.current_value))
                except (ValueError, TypeError):
                    pass
            layout.addWidget(input_widget)

        elif node.widget_type == 'combo':
            input_widget = QComboBox()
            input_widget.setFixedWidth(120)
            # Combo options from node_info or from node extraction
            if node.options:
                input_widget.addItems([str(o) for o in node.options])
            if node.current_value is not None:
                idx = input_widget.findText(str(node.current_value))
                if idx >= 0:
                    input_widget.setCurrentIndex(idx)
                else:
                    input_widget.addItem(str(node.current_value))
                    input_widget.setCurrentText(str(node.current_value))
            layout.addWidget(input_widget)

        else:
            # Default: line edit
            input_widget = QLineEdit()
            input_widget.setFixedWidth(80)
            if node.current_value is not None:
                input_widget.setText(str(node.current_value))
            layout.addWidget(input_widget)

        layout.addStretch()

        # Store references
        container.input_widget = input_widget
        container.settings_node = node

        return container

    def _apply_pending_settings_values(self):
        """Apply pending settings values from a previous session."""
        if not self.pending_settings_values:
            return

        for key, value in self.pending_settings_values.items():
            # Key format: "settings_<node_id>"
            if key.startswith("settings_"):
                try:
                    node_id = int(key.replace("settings_", ""))
                    if node_id in self.settings_widgets:
                        container = self.settings_widgets[node_id]
                        input_widget = getattr(container, 'input_widget', None)
                        if input_widget:
                            if hasattr(input_widget, 'setChecked'):
                                input_widget.setChecked(bool(value))
                            elif hasattr(input_widget, 'setValue'):
                                try:
                                    input_widget.setValue(float(value) if isinstance(input_widget, QtWidgets.QDoubleSpinBox) else int(value))
                                except (ValueError, TypeError):
                                    pass
                            elif hasattr(input_widget, 'setCurrentText'):
                                input_widget.setCurrentText(str(value))
                            elif hasattr(input_widget, 'setText'):
                                input_widget.setText(str(value))
                except (ValueError, AttributeError) as e:
                    logger.debug(f"Skipped restoration of settings value for {key}: {e}")

        self.pending_settings_values = {}

    def collect_settings_values(self) -> Dict[int, list]:
        """
        Collect settings values from settings widgets.

        Returns:
            Dict mapping node_id -> list of {'node': SettingsNode, 'value': Any}
        """
        settings_values = {}

        for node_id, container in self.settings_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            node = getattr(container, 'settings_node', None)
            if input_widget and node:
                if hasattr(input_widget, 'isChecked'):
                    value = input_widget.isChecked()
                elif hasattr(input_widget, 'value'):
                    value = input_widget.value()
                elif hasattr(input_widget, 'currentText'):
                    value = input_widget.currentText()
                elif hasattr(input_widget, 'text'):
                    value = input_widget.text()
                else:
                    value = node.current_value

                if node_id not in settings_values:
                    settings_values[node_id] = []
                settings_values[node_id].append({'node': node, 'value': value})

        return settings_values
