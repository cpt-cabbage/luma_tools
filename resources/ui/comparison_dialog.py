"""
Parameter Comparison Dialog.

Shows side-by-side comparison of two gallery items with their metadata,
highlighting parameter differences.
"""

import os
import logging
from typing import Dict, Any, Optional, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QScrollArea,
    QFrame, QSizePolicy
)
from PySide6.QtGui import QPixmap, QColor

logger = logging.getLogger(__name__)


# Stylesheet for the comparison dialog


class ComparisonDialog(QDialog):
    """Dialog for comparing two gallery items side-by-side."""

    # Parameters to compare (key, display_name)
    COMPARISON_PARAMS = [
        ('workflow_preset', 'Workflow Preset'),
        ('seed', 'Base Seed'),
        ('actual_seed', 'Actual Seed'),
        ('generation_count', 'Generation Count'),
        ('frame_index', 'Frame Index'),
        ('execution_time_ms', 'Execution Time'),
        ('source_images', 'Source Images'),
        ('source_models', 'Source Models'),
        ('parent_id', 'Parent ID'),
        ('iteration_depth', 'Iteration Depth'),
        ('metadata_level', 'Metadata Level'),
    ]

    # Editable parameter keys to extract
    EDITABLE_PARAM_PATTERNS = [
        'cfg', 'steps', 'denoise', 'sampler', 'scheduler',
        'width', 'height', 'batch', 'model', 'lora',
        'prompt', 'negative', 'strength', 'scale', 'guidance'
    ]

    def __init__(
        self,
        item1_path: str,
        item2_path: str,
        metadata1: Optional[Dict[str, Any]] = None,
        metadata2: Optional[Dict[str, Any]] = None,
        parent=None
    ):
        """
        Initialize the comparison dialog.

        Args:
            item1_path: Path to first item
            item2_path: Path to second item
            metadata1: Metadata for first item (loaded if None)
            metadata2: Metadata for second item (loaded if None)
            parent: Parent widget
        """
        super().__init__(parent)
        self.item1_path = item1_path
        self.item2_path = item2_path
        self.metadata1 = metadata1 or {}
        self.metadata2 = metadata2 or {}

        # Load metadata if not provided
        if not self.metadata1:
            self.metadata1 = self._load_metadata(item1_path)
        if not self.metadata2:
            self.metadata2 = self._load_metadata(item2_path)

        self._setup_ui()
        self._populate_comparison()

    def _load_metadata(self, item_path: str) -> Dict[str, Any]:
        """Load metadata for an item."""
        try:
            from comfyui.metadata import get_item_metadata
            output_dir = os.path.dirname(item_path)
            filename = os.path.basename(item_path)
            metadata = get_item_metadata(output_dir, filename) or {}
            return metadata
        except Exception as e:
            logger.warning(f"Could not load metadata for {item_path}: {e}")
            return {}

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Compare Parameters")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("Parameter Comparison")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        # Thumbnails side by side
        thumbs_layout = QHBoxLayout()
        thumbs_layout.setSpacing(16)

        # Item 1 thumbnail
        thumb1_widget = self._create_thumbnail_widget(self.item1_path, "Item A")
        thumbs_layout.addWidget(thumb1_widget)

        # Item 2 thumbnail
        thumb2_widget = self._create_thumbnail_widget(self.item2_path, "Item B")
        thumbs_layout.addWidget(thumb2_widget)

        layout.addLayout(thumbs_layout)

        # Legend
        legend_layout = QHBoxLayout()
        legend_layout.addStretch()

        same_label = QLabel("  Same values")
        same_label.setProperty("state", "success")
        legend_layout.addWidget(same_label)

        diff_label = QLabel("  Different values")
        diff_label.setProperty("state", "error")
        legend_layout.addWidget(diff_label)

        legend_layout.addStretch()
        layout.addLayout(legend_layout)

        # Comparison table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Parameter", "Item A", "Item B"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _create_thumbnail_widget(self, item_path: str, label_text: str) -> QWidget:
        """Create a thumbnail widget with label."""
        container = QFrame()
        container.setObjectName("thumbnailFrame")
        container.setFixedSize(200, 180)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Label (A or B)
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignCenter)
        label.setProperty("textRole", "title")
        label.setProperty("state", "info")
        layout.addWidget(label)

        # Thumbnail
        thumb_label = QLabel()
        thumb_label.setFixedSize(180, 120)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setProperty("variant", "thumb")

        # Load thumbnail
        if os.path.exists(item_path):
            pixmap = QPixmap(item_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(180, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                thumb_label.setPixmap(scaled)
            else:
                thumb_label.setText("Preview\nUnavailable")
        else:
            thumb_label.setText("File\nNot Found")

        layout.addWidget(thumb_label)

        # Filename
        filename = os.path.basename(item_path)
        name_label = QLabel(filename)
        name_label.setObjectName("filenameLabel")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        return container

    def _populate_comparison(self):
        """Populate the comparison table with metadata differences."""
        rows: List[Tuple[str, str, str, bool]] = []

        # Standard parameters
        for key, display_name in self.COMPARISON_PARAMS:
            val1 = self._get_value(self.metadata1, key)
            val2 = self._get_value(self.metadata2, key)
            if val1 or val2:  # Only show if at least one has the value
                is_same = self._values_equal(val1, val2)
                rows.append((display_name, val1, val2, is_same))

        # Editable values (dynamic parameters from workflow)
        editable1 = self.metadata1.get('editable_values', {})
        editable2 = self.metadata2.get('editable_values', {})

        # Collect all editable keys
        all_editable_keys = set(editable1.keys()) | set(editable2.keys())

        for key in sorted(all_editable_keys):
            # Create a readable display name
            display_name = key.replace('_', ' ').title()
            if len(display_name) > 30:
                display_name = display_name[:27] + "..."

            val1 = self._format_value(editable1.get(key))
            val2 = self._format_value(editable2.get(key))
            is_same = self._values_equal(val1, val2)
            rows.append((f"[Param] {display_name}", val1, val2, is_same))

        # Node execution trace summary
        trace1 = self.metadata1.get('node_execution_trace', [])
        trace2 = self.metadata2.get('node_execution_trace', [])
        if trace1 or trace2:
            # Show number of nodes executed
            nodes1 = str(len(trace1)) if trace1 else "N/A"
            nodes2 = str(len(trace2)) if trace2 else "N/A"
            is_same = nodes1 == nodes2
            rows.append(("Nodes Executed", nodes1, nodes2, is_same))

            # Show total execution time from traces
            time1 = sum(n.get('duration_ms', 0) for n in trace1) if trace1 else 0
            time2 = sum(n.get('duration_ms', 0) for n in trace2) if trace2 else 0
            if time1 or time2:
                t1_str = f"{time1}ms" if time1 else "N/A"
                t2_str = f"{time2}ms" if time2 else "N/A"
                is_same = time1 == time2
                rows.append(("Total Node Time", t1_str, t2_str, is_same))

        # Set table row count
        self.table.setRowCount(len(rows))

        # Populate table
        for row_idx, (param, val1, val2, is_same) in enumerate(rows):
            # Parameter name
            param_item = QTableWidgetItem(param)
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 0, param_item)

            # Item A value
            val1_item = QTableWidgetItem(val1)
            val1_item.setFlags(val1_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 1, val1_item)

            # Item B value
            val2_item = QTableWidgetItem(val2)
            val2_item.setFlags(val2_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 2, val2_item)

            # Color code based on difference
            if is_same:
                color = QColor(74, 222, 128, 40)  # Green tint
            else:
                color = QColor(248, 113, 113, 40)  # Red tint

            val1_item.setBackground(color)
            val2_item.setBackground(color)

    def _get_value(self, metadata: Dict[str, Any], key: str) -> str:
        """Get a formatted value from metadata."""
        value = metadata.get(key)
        return self._format_value(value)

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if value is None:
            return "N/A"
        if isinstance(value, list):
            if not value:
                return "None"
            # Truncate long lists
            if len(value) > 3:
                return f"{', '.join(str(v) for v in value[:3])}... ({len(value)} items)"
            return ", ".join(str(v) for v in value)
        if isinstance(value, dict):
            if not value:
                return "None"
            return f"({len(value)} values)"
        if isinstance(value, float):
            return f"{value:.4f}".rstrip('0').rstrip('.')
        return str(value)

    def _values_equal(self, val1: str, val2: str) -> bool:
        """Check if two formatted values are equal."""
        # Treat N/A vs N/A as equal, but N/A vs value as different
        if val1 == val2:
            return True
        # Both being "None" or empty equivalents
        if val1 in ("N/A", "None", "") and val2 in ("N/A", "None", ""):
            return True
        return False
