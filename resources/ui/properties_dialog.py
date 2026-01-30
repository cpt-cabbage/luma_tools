"""
Properties Dialog for Gallery Items.

Shows comprehensive information about images and models including:
- File properties (name, path, size, date)
- Metadata (workflow, settings, prompt)
- Relationships (input images, source models, generated outputs)
- User notes
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QPushButton, QScrollArea, QWidget, QFrame, QApplication, QGroupBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QFont

logger = logging.getLogger(__name__)


class PropertiesDialog(QDialog):
    """Dialog showing comprehensive properties and metadata for a gallery item."""
    
    copy_settings_requested = Signal(dict)  # Emit metadata to apply settings
    
    def __init__(self, item_path: str, output_dir: str = None, metadata: Dict[str, Any] = None, parent=None):
        """Initialize the properties dialog.
        
        Args:
            item_path: Full path to the image or model file
            output_dir: Output directory containing metadata (defaults to item's directory)
            metadata: Pre-loaded metadata dict (optional, will load if not provided)
            parent: Parent widget
        """
        super().__init__(parent)
        self.item_path = item_path
        self.output_dir = output_dir or os.path.dirname(item_path)
        self._metadata = metadata
        self._is_model = self._check_if_model(item_path)
        
        self.setWindowTitle(f"Properties - {os.path.basename(item_path)}")
        self.setMinimumSize(700, 600)
        self.resize(800, 700)
        
        self._setup_ui()
        self._populate_data()
    
    def _check_if_model(self, path: str) -> bool:
        """Check if the item is a 3D model."""
        ext = os.path.splitext(path)[1].lower()
        return ext in ['.glb', '.gltf', '.obj', '.fbx']
    
    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header with icon and filename
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        
        # Icon/thumbnail placeholder
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(64, 64)
        self.icon_label.setStyleSheet("""
            QLabel {
                background-color: #2a3040;
                border: 1px solid #3a4050;
                border-radius: 6px;
            }
        """)
        self.icon_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.icon_label)
        
        # Filename and type
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(4)
        
        self.filename_label = QLabel()
        filename_font = QFont()
        filename_font.setPointSize(11)
        filename_font.setBold(True)
        self.filename_label.setFont(filename_font)
        self.filename_label.setWordWrap(True)
        header_text_layout.addWidget(self.filename_label)
        
        self.type_label = QLabel()
        self.type_label.setStyleSheet("color: #888888;")
        header_text_layout.addWidget(self.type_label)
        
        header_text_layout.addStretch()
        header_layout.addLayout(header_text_layout, 1)
        
        layout.addLayout(header_layout)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #3a4050;")
        layout.addWidget(separator)
        
        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)
        
        scroll_widget = QWidget()
        self.content_layout = QVBoxLayout(scroll_widget)
        self.content_layout.setSpacing(16)
        self.content_layout.setContentsMargins(0, 0, 8, 0)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)
        
        # Button bar
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        self.apply_settings_btn = QPushButton("Apply Settings to ComfyUI")
        self.apply_settings_btn.setMinimumHeight(32)
        self.apply_settings_btn.clicked.connect(self._apply_settings)
        button_layout.addWidget(self.apply_settings_btn)
        
        button_layout.addStretch()
        
        self.copy_path_btn = QPushButton("Copy Path")
        self.copy_path_btn.setMinimumHeight(32)
        self.copy_path_btn.clicked.connect(self._copy_path)
        button_layout.addWidget(self.copy_path_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.setMinimumHeight(32)
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
        
        # Apply stylesheet
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #cccccc;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #3a4050;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 12px;
                background-color: #252530;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #4a9eff;
            }
            QLabel {
                color: #cccccc;
            }
            QPushButton {
                background-color: #3a4050;
                border: 1px solid #4a5060;
                border-radius: 4px;
                padding: 6px 16px;
                color: #cccccc;
            }
            QPushButton:hover {
                background-color: #4a5060;
                border-color: #5a6070;
            }
            QPushButton:pressed {
                background-color: #2a3040;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666666;
            }
        """)
    
    def _populate_data(self):
        """Populate the dialog with item data."""
        # Set header info
        filename = os.path.basename(self.item_path)
        self.filename_label.setText(filename)
        
        if self._is_model:
            self.type_label.setText("3D Model")
            self.icon_label.setText("🎲")
            self.icon_label.setStyleSheet(self.icon_label.styleSheet() + "font-size: 32px;")
        else:
            ext = os.path.splitext(filename)[1].upper()
            self.type_label.setText(f"Image {ext}")
            self._load_thumbnail()
        
        # Load metadata if not provided
        if self._metadata is None:
            self._metadata = self._load_metadata()
        
        # Add sections
        self._add_file_properties_section()
        self._add_metadata_section()
        self._add_relationships_section()
        self._add_workflow_section()
        self._add_notes_section()
        
        # Enable/disable apply settings button
        has_settings = bool(self._metadata and (
            self._metadata.get('workflow_preset') or 
            self._metadata.get('editable_values')
        ))
        self.apply_settings_btn.setEnabled(has_settings)
        if not has_settings:
            self.apply_settings_btn.setText("Apply Settings (no metadata)")
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load metadata for the item."""
        try:
            from comfyui.metadata import get_item_metadata
            filename = os.path.basename(self.item_path)
            metadata = get_item_metadata(self.output_dir, filename)
            return metadata or {}
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
            return {}
    
    def _load_thumbnail(self):
        """Load a small thumbnail for the icon."""
        try:
            pixmap = QPixmap(self.item_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(scaled)
        except Exception as e:
            logger.error(f"Error loading thumbnail: {e}")
            self.icon_label.setText("🖼️")
            self.icon_label.setStyleSheet(self.icon_label.styleSheet() + "font-size: 32px;")
    
    def _add_file_properties_section(self):
        """Add file properties section."""
        group = self._create_group("File Properties")
        
        try:
            stat = os.stat(self.item_path)
            
            # Path (truncated if too long)
            self._add_property(group, "Location:", self.item_path, selectable=True)
            
            # File size
            size_mb = stat.st_size / (1024 * 1024)
            if size_mb >= 1:
                size_str = f"{size_mb:.2f} MB"
            else:
                size_kb = stat.st_size / 1024
                size_str = f"{size_kb:.2f} KB"
            self._add_property(group, "Size:", size_str)
            
            # Dates
            created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            self._add_property(group, "Created:", created)
            self._add_property(group, "Modified:", modified)
            
            # Dimensions for images
            if not self._is_model:
                try:
                    pixmap = QPixmap(self.item_path)
                    if not pixmap.isNull():
                        dimensions = f"{pixmap.width()} × {pixmap.height()} pixels"
                        self._add_property(group, "Dimensions:", dimensions)
                except Exception:
                    pass
        
        except Exception as e:
            self._add_property(group, "Error:", f"Could not read file properties: {e}")
        
        self.content_layout.addWidget(group)
    
    def _add_metadata_section(self):
        """Add metadata section."""
        if not self._metadata:
            return
        
        group = self._create_group("Generation Metadata")
        has_content = False
        
        # Workflow
        workflow = self._metadata.get('workflow') or self._metadata.get('workflow_preset')
        if workflow:
            self._add_property(group, "Workflow:", workflow)
            has_content = True
        
        # Prompt
        prompt = self._metadata.get('prompt')
        if prompt:
            self._add_text_property(group, "Prompt:", prompt)
            has_content = True
        
        # Timestamp
        timestamp = self._metadata.get('timestamp')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
                self._add_property(group, "Generated:", formatted)
                has_content = True
            except Exception:
                pass
        
        # Generation count
        gen_count = self._metadata.get('generation_count')
        if gen_count:
            self._add_property(group, "Generation Count:", str(gen_count))
            has_content = True
        
        # Base seed
        seed = self._metadata.get('base_seed')
        if seed is not None:
            self._add_property(group, "Base Seed:", str(seed))
            has_content = True
        
        # Editable values
        editable = self._metadata.get('editable_values')
        if editable and isinstance(editable, dict):
            self._add_separator(group)
            label = QLabel("Editable Parameters:")
            label.setStyleSheet("font-weight: bold; color: #4a9eff; margin-top: 8px;")
            group.layout().addWidget(label)
            
            for node_id, data in editable.items():
                if isinstance(data, dict):
                    name = data.get('display_name') or data.get('node_id', node_id)
                    value = data.get('value', '')
                    widget_type = data.get('widget_type', 'text')
                    
                    # Format value based on type
                    if widget_type == 'image' or widget_type == '3d_model':
                        continue  # Skip file paths here, show in relationships
                    elif isinstance(value, (list, tuple)):
                        value_str = ', '.join(str(v) for v in value)
                    else:
                        value_str = str(value)
                    
                    if len(value_str) > 100:
                        self._add_text_property(group, f"  {name}:", value_str)
                    else:
                        self._add_property(group, f"  {name}:", value_str)
                    has_content = True
        
        if has_content:
            self.content_layout.addWidget(group)
    
    def _add_relationships_section(self):
        """Add relationships section (inputs/outputs)."""
        if not self._metadata:
            return
        
        group = self._create_group("Relationships")
        has_content = False
        
        # Input image
        input_image = self._metadata.get('input_image')
        if input_image:
            self._add_property(group, "Primary Input:", input_image)
            has_content = True
        
        # All source images
        source_images = self._metadata.get('source_images')
        if source_images and isinstance(source_images, list) and len(source_images) > 0:
            if len(source_images) == 1 and source_images[0] == input_image:
                pass  # Already shown as primary input
            else:
                self._add_separator(group)
                label = QLabel("Source Images:")
                label.setStyleSheet("font-weight: bold; color: #4a9eff; margin-top: 8px;")
                group.layout().addWidget(label)
                
                for img in source_images:
                    self._add_property(group, "  •", img)
                has_content = True
        
        # Source 3D models
        source_models = self._metadata.get('source_models')
        if source_models and isinstance(source_models, list) and len(source_models) > 0:
            self._add_separator(group)
            label = QLabel("Source 3D Models:")
            label.setStyleSheet("font-weight: bold; color: #4a9eff; margin-top: 8px;")
            group.layout().addWidget(label)
            
            for model in source_models:
                self._add_property(group, "  •", model)
            has_content = True
        
        # Job grouping
        job_prefix = self._metadata.get('job_prefix')
        if job_prefix:
            self._add_separator(group)
            self._add_property(group, "Job Prefix:", job_prefix)
            self._add_property(group, "Group:", f"Part of batch with prefix '{job_prefix}_*'")
            has_content = True
        
        if has_content:
            self.content_layout.addWidget(group)
    
    def _add_workflow_section(self):
        """Add workflow/preset section."""
        if not self._metadata:
            return
        
        workflow_preset = self._metadata.get('workflow_preset')
        workflow_name = self._metadata.get('workflow')
        
        if not workflow_preset and not workflow_name:
            return
        
        group = self._create_group("Workflow Information")
        
        if workflow_preset:
            self._add_property(group, "Preset:", workflow_preset)
        
        if workflow_name and workflow_name != workflow_preset:
            self._add_property(group, "Workflow Name:", workflow_name)
        
        # Check if this is marked as output
        is_output = self._metadata.get('is_output')
        if is_output:
            self._add_property(group, "Type:", "Generated Output")
        
        self.content_layout.addWidget(group)
    
    def _add_notes_section(self):
        """Add user notes section."""
        try:
            from comfyui.metadata import get_model_note
            filename = os.path.basename(self.item_path)
            note = get_model_note(self.output_dir, filename)
            
            if note:
                group = self._create_group("User Notes")
                self._add_text_property(group, "", note)
                self.content_layout.addWidget(group)
        
        except Exception as e:
            logger.error(f"Error loading note: {e}")
    
    def _create_group(self, title: str) -> QGroupBox:
        """Create a styled group box."""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 18, 12, 12)
        return group
    
    def _add_property(self, group: QGroupBox, label: str, value: str, selectable: bool = False):
        """Add a simple property row."""
        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        
        label_widget = QLabel(label)
        label_widget.setStyleSheet("color: #888888; min-width: 120px;")
        label_widget.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        row_layout.addWidget(label_widget)
        
        value_widget = QLabel(value)
        value_widget.setWordWrap(True)
        if selectable:
            value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row_layout.addWidget(value_widget, 1)
        
        group.layout().addLayout(row_layout)
    
    def _add_text_property(self, group: QGroupBox, label: str, value: str):
        """Add a multi-line text property."""
        if label:
            label_widget = QLabel(label)
            label_widget.setStyleSheet("color: #888888; margin-bottom: 4px;")
            group.layout().addWidget(label_widget)
        
        text_widget = QTextEdit()
        text_widget.setPlainText(value)
        text_widget.setReadOnly(True)
        text_widget.setMaximumHeight(100)
        text_widget.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                border: 1px solid #3a4050;
                border-radius: 4px;
                padding: 6px;
                color: #cccccc;
            }
        """)
        group.layout().addWidget(text_widget)
    
    def _add_separator(self, group: QGroupBox):
        """Add a separator line."""
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #3a4050; margin: 6px 0;")
        group.layout().addWidget(sep)
    
    def _copy_path(self):
        """Copy the file path to clipboard."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.item_path)
            # Could show a temporary "Copied!" message here
            logger.info(f"Copied to clipboard: {self.item_path}")
        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
    
    def _apply_settings(self):
        """Apply settings to ComfyUI tab."""
        if self._metadata:
            self.copy_settings_requested.emit(self._metadata)
            # Could show a temporary "Applied!" message here
            logger.info("Settings applied to ComfyUI")
