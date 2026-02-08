"""
Properties Dialog for Gallery Items.

Shows comprehensive information about images, videos, audio, and models including:
- At-a-glance header with thumbnail, file info, and tag chips
- Generation details (workflow, prompt, seed, parameters)
- Execution details (timing, node trace, errors)
- Lineage & identity (file ID, parent, content hash)
- Relationships (inputs, source images/models, job grouping)
- MP4 Maker details (for MP4 Maker outputs)
- File properties (path, size, dates, dimensions)
- User notes
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QScrollArea, QWidget, QFrame, QApplication, QGroupBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QFont

logger = logging.getLogger(__name__)


# File type extension sets (imported lazily to avoid circular imports)
_FILE_TYPE_EXTENSIONS = None


def _get_file_type_extensions():
    """Lazy-load file type extension sets from config."""
    global _FILE_TYPE_EXTENSIONS
    if _FILE_TYPE_EXTENSIONS is None:
        from core.config import (
            GALLERY_IMAGE_EXTENSIONS, GALLERY_VIDEO_EXTENSIONS,
            GALLERY_AUDIO_EXTENSIONS, GALLERY_MODEL_EXTENSIONS,
        )
        _FILE_TYPE_EXTENSIONS = {
            'image': GALLERY_IMAGE_EXTENSIONS,
            'video': GALLERY_VIDEO_EXTENSIONS,
            'audio': GALLERY_AUDIO_EXTENSIONS,
            'model': GALLERY_MODEL_EXTENSIONS,
        }
    return _FILE_TYPE_EXTENSIONS


# Tag chip color definitions
TAG_COLORS = {
    'comfyui': ('#1e3a5f', '#4a9eff', '#4a9eff'),      # Blue - bg, text, border
    'input': ('#1e3f2e', '#10b981', '#10b981'),          # Green
    'mp4maker': ('#2e1e3f', '#a855f7', '#a855f7'),       # Purple
    'unknown': ('#2a2a2a', '#888888', '#555555'),         # Grey
    'neutral': ('#2a3040', '#cccccc', '#3a4050'),         # Neutral
    'full': ('#1e3f2e', '#10b981', '#10b981'),            # Green
    'partial': ('#3f3a1e', '#fbbf24', '#fbbf24'),         # Yellow
    'none': ('#2a2a2a', '#888888', '#555555'),            # Grey
}

# Type emoji icons for non-image files
TYPE_ICONS = {
    'video': '\u25b6',   # Play triangle
    'audio': '\u266b',   # Music note
    'model': '\u2b23',   # Hexagon
    'other': '\u2753',   # Question mark
}

# Type icon colors matching thumbnail_styles.py TYPE_INDICATOR_CONFIG
TYPE_ICON_COLORS = {
    'video': 'rgba(239, 68, 68, 0.8)',
    'audio': 'rgba(168, 85, 247, 0.8)',
    'model': 'rgba(74, 158, 255, 0.8)',
    'other': 'rgba(128, 128, 128, 0.8)',
}


class PropertiesDialog(QDialog):
    """Dialog showing comprehensive properties and metadata for a gallery item."""

    copy_settings_requested = Signal(dict)  # Emit metadata to apply settings

    def __init__(
        self,
        item_path: str,
        output_dir: str = None,
        metadata: Dict[str, Any] = None,
        parent=None,
        show_comfyui_features: bool = True
    ):
        """Initialize the properties dialog.

        Args:
            item_path: Full path to the image or model file
            output_dir: Output directory containing metadata (defaults to item's directory)
            metadata: Pre-loaded metadata dict (optional, will load if not provided)
            parent: Parent widget
            show_comfyui_features: If False, hide ComfyUI-specific features like
                "Apply Settings to ComfyUI" button
        """
        super().__init__(parent)
        self.item_path = item_path
        self.output_dir = output_dir or os.path.dirname(item_path)
        self._pre_loaded_metadata = metadata
        self._metadata = None
        self._file_type = self._detect_file_type(item_path)
        self._show_comfyui_features = show_comfyui_features

        self.setWindowTitle(f"Properties - {os.path.basename(item_path)}")
        self.setMinimumSize(700, 600)
        self.resize(800, 700)

        self._setup_ui()
        self._populate_data()

    # ------------------------------------------------------------------
    # File type detection
    # ------------------------------------------------------------------

    def _detect_file_type(self, path: str) -> str:
        """Detect the file type based on extension.

        Returns:
            One of 'image', 'video', 'audio', 'model', 'other'
        """
        ext = os.path.splitext(path)[1].lower()
        extensions = _get_file_type_extensions()
        for file_type, ext_set in extensions.items():
            if ext in ext_set:
                return file_type
        return 'other'

    # ------------------------------------------------------------------
    # Metadata loading — 3-source merge
    # ------------------------------------------------------------------

    def _merge_all_metadata(self) -> Dict[str, Any]:
        """Load and merge metadata from all three sources.

        Sources (in priority order for overlapping keys):
        1. Job-level metadata (get_item_metadata) — prompt, workflow, seed, sources
        2. Per-file metadata (get_per_file_metadata) — execution time, actual seed, traces
        3. MP4 Maker metadata (direct lookup) — source render, quality, frame range

        Per-file data takes precedence for overlapping keys (e.g., timestamp).
        """
        merged = {}
        filename = os.path.basename(self.item_path)

        try:
            from comfyui.metadata import (
                get_item_metadata, get_per_file_metadata, load_gallery_metadata
            )

            # 1. Job-level metadata
            job_meta = get_item_metadata(self.output_dir, filename)
            if job_meta and isinstance(job_meta, dict):
                merged.update(job_meta)

            # 2. Per-file metadata (overwrites overlapping keys)
            per_file = get_per_file_metadata(self.output_dir, filename)
            if per_file and isinstance(per_file, dict):
                merged.update(per_file)

            # 3. MP4 Maker metadata (stored under _mp4maker sub-key)
            basename = os.path.splitext(filename)[0]
            mp4_key = f"_mp4maker_{basename}"
            all_metadata = load_gallery_metadata(self.output_dir)
            mp4_meta = all_metadata.get(mp4_key)
            if mp4_meta and isinstance(mp4_meta, dict):
                merged['_mp4maker'] = mp4_meta

            # Also check for input file metadata
            input_key = f"_input_{filename}"
            input_meta = all_metadata.get(input_key)
            if input_meta and isinstance(input_meta, dict):
                # Don't overwrite existing keys, just fill gaps
                for k, v in input_meta.items():
                    if k not in merged:
                        merged[k] = v

        except Exception as e:
            logger.error(f"Error loading metadata: {e}")

        return merged

    def _load_and_merge_metadata(self) -> Dict[str, Any]:
        """Build the final metadata dict, supplementing pre-loaded data if provided."""
        # Always merge from all sources
        merged = self._merge_all_metadata()

        # If caller provided pre-loaded metadata, use it as base and supplement
        if self._pre_loaded_metadata:
            # Pre-loaded data is the base
            result = dict(self._pre_loaded_metadata)
            # Supplement with merged data (only fill keys not in pre-loaded)
            for key, value in merged.items():
                if key not in result:
                    result[key] = value
                elif key == '_mp4maker' and key not in self._pre_loaded_metadata:
                    result[key] = value
            # But per-file keys should always override (they're more specific)
            per_file_keys = [
                'file_id', 'parent_id', 'job_id', 'actual_seed',
                'execution_time_ms', 'node_execution_trace', 'error',
                'content_hash', 'frame_index',
            ]
            for key in per_file_keys:
                if key in merged and merged[key] is not None:
                    result[key] = merged[key]
            return result

        return merged

    # ------------------------------------------------------------------
    # Tag chip helper
    # ------------------------------------------------------------------

    def _create_tag_chip(self, text: str, color_key: str = 'neutral') -> QLabel:
        """Create a colored pill-label tag chip.

        Args:
            text: Tag text to display
            color_key: Key into TAG_COLORS dict
        """
        chip = QLabel(text)
        bg, fg, border = TAG_COLORS.get(color_key, TAG_COLORS['neutral'])
        chip.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
            }}
        """)
        return chip

    # ------------------------------------------------------------------
    # Metadata completeness calculation
    # ------------------------------------------------------------------

    def _calculate_metadata_level(self) -> str:
        """Calculate metadata completeness level.

        Returns:
            'full', 'partial', or 'none'
        """
        if not self._metadata:
            return 'none'

        has_workflow = bool(
            self._metadata.get('workflow_preset') or
            self._metadata.get('workflow')
        )
        has_seed = (
            self._metadata.get('base_seed') is not None or
            self._metadata.get('actual_seed') is not None
        )
        has_prompt = bool(self._metadata.get('prompt'))
        has_lineage = bool(
            self._metadata.get('parent_id') or
            self._metadata.get('file_id')
        )
        has_execution = bool(
            self._metadata.get('node_execution_trace') or
            self._metadata.get('execution_time_ms')
        )

        checks = [has_workflow, has_seed, has_prompt]
        if all(checks) and (has_lineage or has_execution):
            return 'full'
        elif any(checks):
            return 'partial'
        return 'none'

    # ------------------------------------------------------------------
    # Origin detection
    # ------------------------------------------------------------------

    def _detect_origin(self) -> str:
        """Detect the origin of the file.

        Returns:
            'comfyui', 'input', 'mp4maker', or 'unknown'
        """
        if not self._metadata:
            return 'unknown'

        # MP4 Maker output
        if self._metadata.get('_mp4maker'):
            return 'mp4maker'

        # Explicit input file
        if self._metadata.get('is_input'):
            return 'input'

        # ComfyUI output
        if self._metadata.get('is_output'):
            return 'comfyui'

        # Has workflow/preset → ComfyUI
        if self._metadata.get('workflow_preset') or self._metadata.get('workflow'):
            return 'comfyui'

        return 'unknown'

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Set up the dialog UI with redesigned header."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ---- Header (above scroll, always visible) ----
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        # Thumbnail / type icon (96x96)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(96, 96)
        self.icon_label.setStyleSheet("""
            QLabel {
                background-color: #2a3040;
                border: 1px solid #3a4050;
                border-radius: 6px;
            }
        """)
        self.icon_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.icon_label)

        # Header text area
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(3)

        # Row 1: Filename (bold, 12pt)
        self.filename_label = QLabel()
        filename_font = QFont()
        filename_font.setPointSize(12)
        filename_font.setBold(True)
        self.filename_label.setFont(filename_font)
        self.filename_label.setWordWrap(True)
        header_text_layout.addWidget(self.filename_label)

        # Row 2: Type + format + dimensions + size
        self.info_line_label = QLabel()
        self.info_line_label.setStyleSheet("color: #aaaaaa;")
        header_text_layout.addWidget(self.info_line_label)

        # Row 3: Modification date
        self.date_label = QLabel()
        self.date_label.setStyleSheet("color: #888888;")
        header_text_layout.addWidget(self.date_label)

        # Row 4: Tag chips
        self.tags_layout = QHBoxLayout()
        self.tags_layout.setSpacing(4)
        self.tags_layout.setContentsMargins(0, 2, 0, 0)
        self.tags_layout.addStretch()
        header_text_layout.addLayout(self.tags_layout)

        header_text_layout.addStretch()
        header_layout.addLayout(header_text_layout, 1)

        layout.addLayout(header_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #3a4050;")
        layout.addWidget(separator)

        # ---- Scrollable content area ----
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

        # ---- Button bar ----
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        if self._show_comfyui_features:
            self.apply_settings_btn = QPushButton("Apply Settings to ComfyUI")
            self.apply_settings_btn.setMinimumHeight(32)
            self.apply_settings_btn.clicked.connect(self._apply_settings)
            button_layout.addWidget(self.apply_settings_btn)
        else:
            self.apply_settings_btn = None

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

    # ------------------------------------------------------------------
    # Populate data
    # ------------------------------------------------------------------

    def _populate_data(self):
        """Populate the dialog with item data."""
        filename = os.path.basename(self.item_path)
        ext = os.path.splitext(filename)[1].upper().lstrip('.')

        # ---- Row 1: Filename ----
        self.filename_label.setText(filename)

        # ---- Thumbnail / type icon ----
        if self._file_type == 'image':
            self._load_thumbnail()
        else:
            icon = TYPE_ICONS.get(self._file_type, '?')
            color = TYPE_ICON_COLORS.get(self._file_type, 'rgba(128, 128, 128, 0.8)')
            self.icon_label.setText(icon)
            self.icon_label.setStyleSheet(
                self.icon_label.styleSheet()
                + f"font-size: 40px; color: {color};"
            )

        # ---- Row 2: Type + format + dimensions + size ----
        info_parts = []
        type_labels = {
            'image': 'Image', 'video': 'Video', 'audio': 'Audio',
            'model': '3D Model', 'other': 'File',
        }
        info_parts.append(f"{type_labels.get(self._file_type, 'File')} ({ext})")

        # Dimensions (for images)
        dimensions_str = None
        if self._file_type == 'image':
            try:
                pixmap = QPixmap(self.item_path)
                if not pixmap.isNull():
                    dimensions_str = f"{pixmap.width()} x {pixmap.height()}"
                    info_parts.append(dimensions_str)
            except Exception:
                pass

        # File size
        size_str = None
        try:
            stat = os.stat(self.item_path)
            size_mb = stat.st_size / (1024 * 1024)
            if size_mb >= 1:
                size_str = f"{size_mb:.1f} MB"
            else:
                size_kb = stat.st_size / 1024
                size_str = f"{size_kb:.1f} KB"
            info_parts.append(size_str)
        except Exception:
            pass

        self.info_line_label.setText(" \u00b7 ".join(info_parts))

        # ---- Row 3: Modification date ----
        try:
            stat = os.stat(self.item_path)
            modified = datetime.fromtimestamp(stat.st_mtime).strftime(
                "Modified %Y-%m-%d %H:%M"
            )
            self.date_label.setText(modified)
        except Exception:
            self.date_label.setText("")

        # ---- Load metadata (3-source merge) ----
        self._metadata = self._load_and_merge_metadata()

        # ---- Row 4: Tag chips ----
        self._populate_tag_chips()

        # ---- Content sections ----
        self._add_generation_details_section()
        self._add_execution_section()
        self._add_lineage_section()
        self._add_relationships_section()
        self._add_mp4_maker_section()
        self._add_file_properties_section()
        self._add_notes_section()

        # Spacer at bottom of scroll content
        self.content_layout.addStretch()

        # ---- Apply settings button state (with null guard) ----
        has_settings = bool(self._metadata and (
            self._metadata.get('workflow_preset') or
            self._metadata.get('editable_values')
        ))
        if self.apply_settings_btn is not None:
            self.apply_settings_btn.setEnabled(has_settings)
            if not has_settings:
                self.apply_settings_btn.setText("Apply Settings (no metadata)")

    def _populate_tag_chips(self):
        """Build the tag chips row in the header."""
        # Remove stretch that was added during setup
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Origin tag (always shown)
        origin = self._detect_origin()
        origin_labels = {
            'comfyui': ('ComfyUI Output', 'comfyui'),
            'input': ('Input File', 'input'),
            'mp4maker': ('MP4 Maker', 'mp4maker'),
            'unknown': ('Unknown', 'unknown'),
        }
        label, color_key = origin_labels.get(origin, ('Unknown', 'unknown'))
        self.tags_layout.addWidget(self._create_tag_chip(label, color_key))

        if self._metadata:
            # Workflow preset tag
            preset = self._metadata.get('workflow_preset')
            if preset:
                display = preset[:25] + '...' if len(preset) > 25 else preset
                self.tags_layout.addWidget(self._create_tag_chip(display, 'neutral'))

            # Seed tag
            seed = self._metadata.get('actual_seed')
            if seed is None:
                seed = self._metadata.get('base_seed')
            if seed is not None:
                self.tags_layout.addWidget(
                    self._create_tag_chip(f"Seed: {seed}", 'neutral')
                )

            # Execution time tag
            exec_time = self._metadata.get('execution_time_ms')
            if exec_time is not None:
                if exec_time >= 60000:
                    time_str = f"{exec_time / 60000:.1f}min"
                elif exec_time >= 1000:
                    time_str = f"{exec_time / 1000:.1f}s"
                else:
                    time_str = f"{exec_time}ms"
                self.tags_layout.addWidget(
                    self._create_tag_chip(time_str, 'neutral')
                )

        # Metadata level tag
        level = self._calculate_metadata_level()
        level_labels = {
            'full': ('Full \u2713', 'full'),
            'partial': ('Partial \u25d0', 'partial'),
            'none': ('No Metadata', 'none'),
        }
        level_text, level_color = level_labels.get(level, ('No Metadata', 'none'))
        self.tags_layout.addWidget(self._create_tag_chip(level_text, level_color))

        self.tags_layout.addStretch()

    # ------------------------------------------------------------------
    # Thumbnail
    # ------------------------------------------------------------------

    def _load_thumbnail(self):
        """Load a thumbnail for the icon area."""
        try:
            pixmap = QPixmap(self.item_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.icon_label.setPixmap(scaled)
        except Exception as e:
            logger.error(f"Error loading thumbnail: {e}")
            self.icon_label.setText("\U0001f5bc\ufe0f")
            self.icon_label.setStyleSheet(
                self.icon_label.styleSheet() + "font-size: 40px;"
            )

    # ------------------------------------------------------------------
    # Section 1: Generation Details
    # ------------------------------------------------------------------

    def _add_generation_details_section(self):
        """Add generation details section (merged workflow + metadata)."""
        if not self._metadata:
            return

        group = self._create_group("Generation Details")
        has_content = False

        # Workflow preset
        workflow_preset = self._metadata.get('workflow_preset')
        if workflow_preset:
            self._add_property(group, "Preset:", workflow_preset)
            has_content = True

        # Custom name
        custom_name = self._metadata.get('custom_name')
        if custom_name:
            self._add_property(group, "Custom Name:", custom_name)
            has_content = True

        # Workflow name (if different from preset)
        workflow = self._metadata.get('workflow')
        if workflow and workflow != workflow_preset:
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

        # Output type
        output_type = self._metadata.get('output_type')
        if output_type:
            self._add_property(group, "Output Type:", output_type)
            has_content = True

        # Is output badge
        is_output = self._metadata.get('is_output')
        if is_output:
            self._add_property(group, "Type:", "Generated Output")
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

                    if widget_type in ('image', '3d_model'):
                        continue  # Shown in relationships
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

    # ------------------------------------------------------------------
    # Section 2: Execution
    # ------------------------------------------------------------------

    def _add_execution_section(self):
        """Add execution details section (timing, node trace)."""
        if not self._metadata:
            return

        group = self._create_group("Execution")
        has_content = False

        # Actual seed
        actual_seed = self._metadata.get('actual_seed')
        if actual_seed is not None:
            self._add_property(group, "Actual Seed:", str(actual_seed))
            has_content = True

        # Frame index
        frame_index = self._metadata.get('frame_index')
        if frame_index is not None:
            self._add_property(group, "Frame Index:", str(frame_index))
            has_content = True

        # Execution time
        exec_time_ms = self._metadata.get('execution_time_ms')
        if exec_time_ms is not None:
            if exec_time_ms >= 60000:
                time_str = f"{exec_time_ms / 60000:.1f} min"
            elif exec_time_ms >= 1000:
                time_str = f"{exec_time_ms / 1000:.1f} sec"
            else:
                time_str = f"{exec_time_ms} ms"
            self._add_property(group, "Execution Time:", time_str)
            has_content = True

        # Error status
        error = self._metadata.get('error')
        if error:
            self._add_separator(group)
            error_label = QLabel("Error:")
            error_label.setStyleSheet(
                "font-weight: bold; color: #f44336; margin-top: 8px;"
            )
            group.layout().addWidget(error_label)
            self._add_text_property(group, "", error)
            has_content = True

        # Node execution trace
        node_trace = self._metadata.get('node_execution_trace')
        if node_trace and isinstance(node_trace, list):
            self._add_separator(group)
            trace_label = QLabel("Node Execution Trace:")
            trace_label.setStyleSheet(
                "font-weight: bold; color: #4a9eff; margin-top: 8px;"
            )
            group.layout().addWidget(trace_label)

            for node in node_trace:
                if isinstance(node, dict):
                    node_name = node.get('name', node.get('node_id', 'Unknown'))
                    duration_ms = node.get('duration_ms', 0)
                    if duration_ms >= 1000:
                        duration_str = f"{duration_ms / 1000:.1f}s"
                    else:
                        duration_str = f"{duration_ms}ms"
                    self._add_property(group, f"  {node_name}:", duration_str)
            has_content = True

        if has_content:
            self.content_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Section 3: Lineage & Identity
    # ------------------------------------------------------------------

    def _add_lineage_section(self):
        """Add lineage & identity section."""
        if not self._metadata:
            return

        group = self._create_group("Lineage && Identity")
        has_content = False

        # File ID
        file_id = self._metadata.get('file_id')
        if file_id:
            display_id = (
                f"{file_id[:8]}...{file_id[-4:]}"
                if len(file_id) > 16 else file_id
            )
            self._add_property(group, "File ID:", display_id, selectable=True)
            has_content = True

        # Parent ID
        parent_id = self._metadata.get('parent_id')
        if parent_id:
            display_parent = (
                f"{parent_id[:8]}...{parent_id[-4:]}"
                if len(parent_id) > 16 else parent_id
            )
            self._add_property(
                group, "Parent ID:", display_parent, selectable=True
            )
            self._add_property(
                group, "Iteration:", "This image was iterated from another"
            )
            has_content = True

        # Parent filename
        parent_filename = self._metadata.get('parent_filename')
        if parent_filename:
            self._add_property(group, "Parent File:", parent_filename)
            has_content = True

        # Iteration depth
        iteration_depth = self._metadata.get('iteration_depth')
        if iteration_depth is not None and iteration_depth > 0:
            self._add_property(
                group, "Iteration Depth:", f"Generation {iteration_depth}"
            )
            has_content = True

        # Content hash (new)
        content_hash = self._metadata.get('content_hash')
        if content_hash:
            display_hash = (
                f"{content_hash[:12]}...{content_hash[-6:]}"
                if len(content_hash) > 20 else content_hash
            )
            self._add_property(
                group, "Content Hash:", display_hash, selectable=True
            )
            has_content = True

        # Job ID (new)
        job_id = self._metadata.get('job_id')
        if job_id:
            self._add_property(group, "Job ID:", job_id, selectable=True)
            has_content = True

        if has_content:
            self.content_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Section 4: Relationships
    # ------------------------------------------------------------------

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
            if not (len(source_images) == 1 and source_images[0] == input_image):
                self._add_separator(group)
                label = QLabel("Source Images:")
                label.setStyleSheet(
                    "font-weight: bold; color: #4a9eff; margin-top: 8px;"
                )
                group.layout().addWidget(label)

                for img in source_images:
                    self._add_property(group, "  \u2022", img)
                has_content = True

        # Source 3D models
        source_models = self._metadata.get('source_models')
        if source_models and isinstance(source_models, list) and len(source_models) > 0:
            self._add_separator(group)
            label = QLabel("Source 3D Models:")
            label.setStyleSheet(
                "font-weight: bold; color: #4a9eff; margin-top: 8px;"
            )
            group.layout().addWidget(label)

            for model in source_models:
                self._add_property(group, "  \u2022", model)
            has_content = True

        # Job grouping
        job_prefix = self._metadata.get('job_prefix')
        if job_prefix:
            self._add_separator(group)
            self._add_property(group, "Job Prefix:", job_prefix)
            self._add_property(
                group, "Group:", f"Part of batch with prefix '{job_prefix}_*'"
            )
            has_content = True

        # Used by job (for input files)
        used_by_job = self._metadata.get('used_by_job')
        if used_by_job:
            self._add_separator(group)
            self._add_property(group, "Used by Job:", used_by_job)
            has_content = True

        if has_content:
            self.content_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Section 5: MP4 Maker Details (conditional)
    # ------------------------------------------------------------------

    def _add_mp4_maker_section(self):
        """Add MP4 Maker details section (only for MP4 Maker outputs)."""
        if not self._metadata:
            return

        mp4_data = self._metadata.get('_mp4maker')
        if not mp4_data or not isinstance(mp4_data, dict):
            return

        group = self._create_group("MP4 Maker Details")

        # Source render
        source_render = mp4_data.get('source_render')
        if source_render:
            self._add_property(group, "Source Render:", source_render)

        # Source path
        source_path = mp4_data.get('source_path')
        if source_path:
            self._add_property(
                group, "Source Path:", source_path, selectable=True
            )

        # Frame range
        frame_range = mp4_data.get('frame_range')
        if frame_range and isinstance(frame_range, (list, tuple)) and len(frame_range) >= 2:
            self._add_property(
                group, "Frame Range:", f"{frame_range[0]} - {frame_range[1]}"
            )

        # Quality
        quality = mp4_data.get('quality_setting')
        if quality:
            self._add_property(group, "Quality:", quality)

        # Burn-in timecode
        burn_in = mp4_data.get('burn_in_timecode')
        if burn_in is not None:
            self._add_property(
                group, "Burn-in Timecode:", "Yes" if burn_in else "No"
            )

        # Shot
        shot = mp4_data.get('shot')
        if shot:
            self._add_property(group, "Shot:", shot)

        self.content_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Section 6: File Properties
    # ------------------------------------------------------------------

    def _add_file_properties_section(self):
        """Add file properties section."""
        group = self._create_group("File Properties")

        try:
            stat = os.stat(self.item_path)

            # Path
            self._add_property(
                group, "Location:", self.item_path, selectable=True
            )

            # File size
            size_mb = stat.st_size / (1024 * 1024)
            if size_mb >= 1:
                size_str = f"{size_mb:.2f} MB"
            else:
                size_kb = stat.st_size / 1024
                size_str = f"{size_kb:.2f} KB"
            self._add_property(group, "Size:", size_str)

            # Dates
            created = datetime.fromtimestamp(stat.st_ctime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            modified = datetime.fromtimestamp(stat.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            self._add_property(group, "Created:", created)
            self._add_property(group, "Modified:", modified)

            # Dimensions for images
            if self._file_type == 'image':
                try:
                    pixmap = QPixmap(self.item_path)
                    if not pixmap.isNull():
                        dimensions = f"{pixmap.width()} \u00d7 {pixmap.height()} pixels"
                        self._add_property(group, "Dimensions:", dimensions)
                except Exception:
                    pass

        except Exception as e:
            self._add_property(
                group, "Error:", f"Could not read file properties: {e}"
            )

        self.content_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Section 7: User Notes
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _create_group(self, title: str) -> QGroupBox:
        """Create a styled group box."""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 18, 12, 12)
        return group

    def _add_property(
        self, group: QGroupBox, label: str, value: str, selectable: bool = False
    ):
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

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _copy_path(self):
        """Copy the file path to clipboard."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.item_path)
            logger.info(f"Copied to clipboard: {self.item_path}")
        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")

    def _apply_settings(self):
        """Apply settings to ComfyUI tab."""
        if self._metadata:
            self.copy_settings_requested.emit(self._metadata)
            logger.info("Settings applied to ComfyUI")
