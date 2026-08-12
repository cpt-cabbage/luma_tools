"""
Prompt Builder overlay for ComfyUI text inputs.

Provides a full-screen overlay with categories, presets, and live preview
for building complex prompts with weighted tags.
"""

import logging
import random
from typing import List, Dict, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QScrollArea, QFrame, QCheckBox,
    QDoubleSpinBox, QTabWidget, QListWidget,
    QInputDialog, QComboBox, QSplitter
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPalette, QKeyEvent

# Data models and utilities
from prompt_builder_models import (
    PromptCategory, PromptOption, PromptBuilderState,
    get_default_categories, get_category_by_id, get_option_by_id
)
from prompt_builder_templates import (
    TemplateEngine, get_builtin_templates, get_template_help_text
)
from core.settings_manager import safe_get_setting, safe_set_setting
from dialog_helpers import confirm_action, show_error, show_info

logger = logging.getLogger(__name__)


# The overlay backdrop is painted through QPalette rather than QSS, so it
# is the one colour this module still needs as a QColor. Everything else now
# comes from the stylesheet via the component contract.
OVERLAY_BACKDROP = QColor(0, 0, 0, 180)


class OverlayBackdrop(QWidget):
    """Semi-transparent backdrop that catches clicks outside content"""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # Set background color
        palette = self.palette()
        palette.setColor(QPalette.Window, OVERLAY_BACKDROP)
        self.setAutoFillBackground(True)
        self.setPalette(palette)

    def mousePressEvent(self, event):
        """Emit clicked signal when backdrop is clicked"""
        self.clicked.emit()
        event.accept()


class CategorySection(QFrame):
    """Widget for a single category with options and weight controls.

    Single-select categories use a QComboBox dropdown.
    Multi-select categories use QCheckBox widgets with optional weight spinboxes.
    """
    selection_changed = Signal()

    """

    """

    def __init__(self, category: PromptCategory, parent=None):
        super().__init__(parent)
        self.category = category
        self._combo = None                # QComboBox for single-select
        self._option_ids = []             # ordered option IDs matching combo indices
        self.option_widgets = {}          # option_id -> QCheckBox (multi-select only)
        self.weight_widgets = {}          # option_id -> QDoubleSpinBox

        self._setup_ui()

    def _setup_ui(self):
        """Build the category section UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        header = QLabel(self.category.label)
        header.setProperty("textRole", "title")
        layout.addWidget(header)

        if self.category.multi_select:
            self._setup_multi_select(layout)
        else:
            self._setup_single_select(layout)

        # Frame styling
        self.setFrameShape(QFrame.StyledPanel)
        self.setProperty("variant", "subtle")

    def _setup_single_select(self, layout):
        """Build a dropdown for single-select categories"""
        self._combo = QComboBox()

        # First item is "None" (no selection)
        self._combo.addItem("— None —")
        self._option_ids = [None]

        for option in self.category.options:
            self._combo.addItem(option.label)
            self._combo.setItemData(self._combo.count() - 1, option.description, Qt.ToolTipRole)
            self._option_ids.append(option.id)

        self._combo.currentIndexChanged.connect(lambda _: self.selection_changed.emit())
        layout.addWidget(self._combo)

    def _setup_multi_select(self, layout):
        """Build checkboxes with optional weights for multi-select categories"""
        for option in self.category.options:
            option_layout = QHBoxLayout()
            option_layout.setSpacing(8)

            widget = QCheckBox(option.label)
            widget.setToolTip(option.description)
            widget.toggled.connect(lambda _: self.selection_changed.emit())

            self.option_widgets[option.id] = widget
            option_layout.addWidget(widget, stretch=1)

            if self.category.allow_weights:
                weight_spin = QDoubleSpinBox()
                weight_spin.setRange(0.1, 3.0)
                weight_spin.setSingleStep(0.1)
                weight_spin.setValue(option.weight)
                weight_spin.setDecimals(1)
                weight_spin.setFixedWidth(60)
                weight_spin.setPrefix("×")
                weight_spin.valueChanged.connect(lambda _: self.selection_changed.emit())

                self.weight_widgets[option.id] = weight_spin
                option_layout.addWidget(weight_spin)

            layout.addLayout(option_layout)

    def get_selected_options(self) -> List[str]:
        """Get list of selected option IDs"""
        if self._combo:
            idx = self._combo.currentIndex()
            opt_id = self._option_ids[idx] if idx < len(self._option_ids) else None
            return [opt_id] if opt_id else []
        return [oid for oid, w in self.option_widgets.items() if w.isChecked()]

    def get_weights(self) -> Dict[str, float]:
        """Get weights for all options"""
        return {oid: w.value() for oid, w in self.weight_widgets.items()}

    def set_selected_options(self, option_ids: List[str]):
        """Set which options are selected"""
        if self._combo:
            target = option_ids[0] if option_ids else None
            try:
                idx = self._option_ids.index(target)
            except ValueError:
                idx = 0  # "None" item
            self._combo.setCurrentIndex(idx)
        else:
            for opt_id, widget in self.option_widgets.items():
                widget.setChecked(opt_id in option_ids)

    def set_weights(self, weights: Dict[str, float]):
        """Set weights for options"""
        for opt_id, weight in weights.items():
            if opt_id in self.weight_widgets:
                self.weight_widgets[opt_id].setValue(weight)

    def clear_selection(self):
        """Clear all selections"""
        if self._combo:
            self._combo.setCurrentIndex(0)
        else:
            for widget in self.option_widgets.values():
                widget.setChecked(False)

    def randomize(self):
        """Randomly select options and weights"""
        if self.category.multi_select:
            count = random.randint(0, min(3, len(self.category.options)))
            selected = random.sample(self.category.options, count)
            self.set_selected_options([opt.id for opt in selected])
        else:
            if self.category.options:
                selected = random.choice(self.category.options)
                self.set_selected_options([selected.id])

        if self.category.allow_weights:
            for opt_id in self.weight_widgets:
                self.weight_widgets[opt_id].setValue(random.uniform(0.8, 1.5))


class PromptBuilderOverlay(QWidget):
    """Full-screen overlay for building prompts with categories and presets"""

    prompt_generated = Signal(str, str, dict)  # (positive_prompt, negative_prompt, json_output)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.categories = get_default_categories()
        self.template_engine = TemplateEngine(self.categories)
        self.builtin_templates = get_builtin_templates()

        # UI components
        self.backdrop = None
        self.content_frame = None
        self.description_edit = None
        self.category_sections = {}  # category_id -> CategorySection
        self.negative_category_sections = {}  # category_id -> CategorySection
        self.preview_edit = None
        self.negative_preview_edit = None
        self.json_preview_edit = None
        self.template_combo = None
        self.preset_list = None

        # State
        self.current_state = PromptBuilderState()
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(100)
        self.update_timer.timeout.connect(self._do_update_preview)

        # Context for filename generation
        self.model_name = None
        self.workflow_name = None

        self._setup_ui()
        self._load_last_template()

        # Hide initially
        self.hide()

    def _setup_ui(self):
        """Build the overlay UI"""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Backdrop
        self.backdrop = OverlayBackdrop(self)
        self.backdrop.clicked.connect(self.hide_overlay)

        # Content frame (centered card)
        self.content_frame = QFrame(self)
        self.content_frame.setFrameShape(QFrame.StyledPanel)
        self.content_frame.setProperty("variant", "panel")

        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        title = QLabel("Prompt Builder")
        title.setProperty("textRole", "display")
        header_layout.addWidget(title)

        # Template dropdown
        template_label = QLabel("Template:")
        template_label.setProperty("textRole", "help")
        header_layout.addWidget(template_label)

        self.template_combo = QComboBox()
        for name in self.builtin_templates.keys():
            self.template_combo.addItem(name)
        self.template_combo.currentTextChanged.connect(self._on_template_changed)
        self.template_combo.setFixedWidth(200)
        header_layout.addWidget(self.template_combo)

        header_layout.addStretch()

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setProperty("role", "ghost")
        close_btn.setProperty("iconOnly", "true")
        close_btn.clicked.connect(self.hide_overlay)
        header_layout.addWidget(close_btn)

        content_layout.addLayout(header_layout)

        # Body: splitter with left (categories) and right (preview/presets)
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: categories
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # Right panel: tabs
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        # Set initial sizes (60/40 split)
        splitter.setSizes([600, 400])

        content_layout.addWidget(splitter, stretch=1)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        randomize_btn = QPushButton("🎲 Randomize")
        randomize_btn.clicked.connect(self._on_randomize)
        randomize_btn.setProperty("role", "secondary")
        button_layout.addWidget(randomize_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._on_clear_all)
        clear_btn.setProperty("role", "secondary")
        button_layout.addWidget(clear_btn)

        button_layout.addStretch()

        insert_btn = QPushButton("Insert Prompt")
        insert_btn.setProperty("role", "primary")
        insert_btn.clicked.connect(self._on_insert_prompt)
        button_layout.addWidget(insert_btn)

        content_layout.addLayout(button_layout)

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with categories"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Scroll area for categories
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        scroll_layout.setContentsMargins(10, 10, 10, 10)

        # Description text area
        desc_label = QLabel("Video Description")
        desc_label.setProperty("textRole", "title")
        scroll_layout.addWidget(desc_label)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Describe your scene in natural language...")
        self.description_edit.setMaximumHeight(100)
        self.description_edit.textChanged.connect(self._schedule_update_preview)
        scroll_layout.addWidget(self.description_edit)

        # Category sections
        for category in self.categories:
            section = CategorySection(category)
            section.selection_changed.connect(self._schedule_update_preview)
            self.category_sections[category.id] = section
            scroll_layout.addWidget(section)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return panel

    def _create_right_panel(self) -> QWidget:
        """Create the right panel with tabs"""
        tabs = QTabWidget()

        # Tab 1: Positive Preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(10, 10, 10, 10)

        preview_label = QLabel("Positive Prompt Preview")
        preview_label.setProperty("textRole", "title")
        preview_layout.addWidget(preview_label)

        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        preview_layout.addWidget(self.preview_edit)

        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.clicked.connect(self._on_copy_positive)
        copy_btn.setProperty("role", "secondary")
        preview_layout.addWidget(copy_btn)

        tabs.addTab(preview_widget, "Positive")

        # Tab 2: Negative Builder
        negative_widget = self._create_negative_tab()
        tabs.addTab(negative_widget, "Negative")

        # Tab 3: JSON Output
        json_widget = self._create_json_tab()
        tabs.addTab(json_widget, "JSON")

        # Tab 4: Presets
        preset_widget = self._create_preset_tab()
        tabs.addTab(preset_widget, "Presets")

        return tabs

    def _create_negative_tab(self) -> QWidget:
        """Create the negative prompt builder tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Split: categories on left, preview on right
        splitter = QSplitter(Qt.Vertical)

        # Categories scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        scroll_layout.setContentsMargins(10, 10, 10, 10)

        # Create category sections for negative
        for category in self.categories:
            section = CategorySection(category)
            section.selection_changed.connect(self._schedule_update_preview)
            self.negative_category_sections[category.id] = section
            scroll_layout.addWidget(section)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        splitter.addWidget(scroll)

        # Preview area
        preview_frame = QFrame()
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 10, 10, 10)

        preview_label = QLabel("Negative Prompt Preview")
        preview_label.setProperty("textRole", "title")
        preview_layout.addWidget(preview_label)

        self.negative_preview_edit = QTextEdit()
        self.negative_preview_edit.setReadOnly(True)
        self.negative_preview_edit.setMaximumHeight(120)
        preview_layout.addWidget(self.negative_preview_edit)

        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.clicked.connect(self._on_copy_negative)
        copy_btn.setProperty("role", "secondary")
        preview_layout.addWidget(copy_btn)

        splitter.addWidget(preview_frame)
        splitter.setSizes([300, 150])

        layout.addWidget(splitter)
        return widget

    def _create_json_tab(self) -> QWidget:
        """Create the JSON output tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        label = QLabel("JSON Output")
        label.setProperty("textRole", "title")
        layout.addWidget(label)

        self.json_preview_edit = QTextEdit()
        self.json_preview_edit.setReadOnly(True)
        self.json_preview_edit.setProperty("textRole", "mono")
        layout.addWidget(self.json_preview_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        copy_btn = QPushButton("📋 Copy JSON")
        copy_btn.clicked.connect(self._on_copy_json)
        copy_btn.setProperty("role", "primary")
        btn_layout.addWidget(copy_btn)

        save_btn = QPushButton("💾 Save to File")
        save_btn.clicked.connect(self._on_save_json)
        save_btn.setProperty("role", "secondary")
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        return widget

    def _create_preset_tab(self) -> QWidget:
        """Create the presets management tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        label = QLabel("Saved Presets")
        label.setProperty("textRole", "title")
        layout.addWidget(label)

        self.preset_list = QListWidget()
        self.preset_list.itemDoubleClicked.connect(self._on_preset_load)
        layout.addWidget(self.preset_list)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        save_btn = QPushButton("Save Current")
        save_btn.clicked.connect(self._on_preset_save)
        save_btn.setProperty("role", "secondary")
        btn_layout.addWidget(save_btn)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(lambda: self._on_preset_load(self.preset_list.currentItem()))
        load_btn.setProperty("role", "secondary")
        btn_layout.addWidget(load_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._on_preset_delete)
        delete_btn.setProperty("role", "secondary")
        btn_layout.addWidget(delete_btn)

        layout.addLayout(btn_layout)

        # Load presets
        self._refresh_preset_list()

        return widget

    def show_overlay(self, initial_text: str = "", model_name: str = None, workflow_name: str = None):
        """Show the overlay

        Args:
            initial_text: Initial description text
            model_name: Name of the model/preset (for filename generation)
            workflow_name: Name of the workflow (for filename generation)
        """
        if initial_text:
            self.description_edit.setPlainText(initial_text)

        # Store context for filename generation
        self.model_name = model_name
        self.workflow_name = workflow_name

        # Show and position
        self.show()
        self.raise_()
        self._position_content()
        self._update_preview()

        # Install event filter on parent for resize
        if self.parent():
            self.parent().installEventFilter(self)

    def hide_overlay(self):
        """Hide the overlay"""
        self.hide()
        self.closed.emit()

        # Remove event filter
        if self.parent():
            self.parent().removeEventFilter(self)

    def _position_content(self):
        """Position the content frame in the center"""
        if not self.parent():
            return

        # Make backdrop fill parent
        self.setGeometry(self.parent().rect())
        self.backdrop.setGeometry(self.rect())

        # Center content frame with margins
        margin = 50
        content_width = self.width() - (margin * 2)
        content_height = self.height() - (margin * 2)

        self.content_frame.setGeometry(
            margin,
            margin,
            content_width,
            content_height
        )

    def eventFilter(self, obj, event):
        """Handle parent resize events"""
        if obj == self.parent() and event.type() == event.Type.Resize:
            self._position_content()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key_Escape:
            self.hide_overlay()
        elif event.key() == Qt.Key_R and event.modifiers() & Qt.ControlModifier:
            self._on_randomize()
        elif event.key() == Qt.Key_Return and event.modifiers() & Qt.ControlModifier:
            self._on_insert_prompt()
        else:
            super().keyPressEvent(event)

    def _schedule_update_preview(self):
        """Schedule a preview update (debounced)"""
        self.update_timer.start()

    def _do_update_preview(self):
        """Actually update the preview"""
        self._update_preview()

    def _update_preview(self):
        """Update preview text with current selections"""
        # Collect positive state
        self.current_state.description = self.description_edit.toPlainText()
        self.current_state.positive_selections = {}
        self.current_state.positive_weights = {}

        for cat_id, section in self.category_sections.items():
            selected = section.get_selected_options()
            if selected:
                self.current_state.positive_selections[cat_id] = selected
            self.current_state.positive_weights.update(section.get_weights())

        # Collect negative state
        self.current_state.negative_selections = {}
        self.current_state.negative_weights = {}

        for cat_id, section in self.negative_category_sections.items():
            selected = section.get_selected_options()
            if selected:
                self.current_state.negative_selections[cat_id] = selected
            self.current_state.negative_weights.update(section.get_weights())

        # Get current template
        template_name = self.template_combo.currentText()
        template = self.builtin_templates.get(template_name, "")

        # Render previews
        positive = self.template_engine.render(template, self.current_state, is_negative=False)
        negative = self.template_engine.render(template, self.current_state, is_negative=True)

        self.preview_edit.setPlainText(positive)
        self.negative_preview_edit.setPlainText(negative)

        # Generate JSON output
        import json
        json_output = self.current_state.to_json_output(self.categories, negative)
        formatted_json = json.dumps(json_output, indent=2, ensure_ascii=False)
        self.json_preview_edit.setPlainText(formatted_json)

    def _on_template_changed(self, template_name: str):
        """Handle template selection change"""
        self._update_preview()
        safe_set_setting("prompt_builder_last_template", template_name)

    def _load_last_template(self):
        """Load the last used template"""
        last = safe_get_setting("prompt_builder_last_template", "Natural Language")
        index = self.template_combo.findText(last)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)

    def _on_randomize(self):
        """Randomize all selections"""
        # Randomize positive
        for section in self.category_sections.values():
            section.randomize()

        # Randomize negative (fewer selections)
        for section in self.negative_category_sections.values():
            if random.random() < 0.3:  # 30% chance to add negative
                section.randomize()

        self._update_preview()

    def _on_clear_all(self):
        """Clear all selections"""
        if not confirm_action(
            "Clear All",
            "Clear all selections and weights?",
            parent=self,
            detail="This will reset the entire builder."
        ):
            return

        # Clear positive
        self.description_edit.clear()
        for section in self.category_sections.values():
            section.clear_selection()

        # Clear negative
        for section in self.negative_category_sections.values():
            section.clear_selection()

        self._update_preview()

    def _on_insert_prompt(self):
        """Emit the generated prompt and hide"""
        import json
        positive = self.preview_edit.toPlainText()
        negative = self.negative_preview_edit.toPlainText()

        # Generate JSON output
        json_output = self.current_state.to_json_output(self.categories, negative)

        self.prompt_generated.emit(positive, negative, json_output)
        self.hide_overlay()

    def _on_copy_positive(self):
        """Copy positive prompt to clipboard"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.preview_edit.toPlainText())
        show_info("Copied", "Positive prompt copied to clipboard", parent=self)

    def _on_copy_negative(self):
        """Copy negative prompt to clipboard"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.negative_preview_edit.toPlainText())
        show_info("Copied", "Negative prompt copied to clipboard", parent=self)

    def _on_copy_json(self):
        """Copy JSON to clipboard"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.json_preview_edit.toPlainText())
        show_info("Copied", "JSON output copied to clipboard", parent=self)

    def _on_save_json(self):
        """Save JSON to file"""
        from PySide6.QtWidgets import QFileDialog
        import json
        from datetime import datetime
        import re

        # Generate default filename with context
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Build filename from available context
        if self.model_name:
            # Sanitize model name for filename
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', self.model_name)
            if self.workflow_name:
                # Include workflow name if available
                safe_workflow = re.sub(r'[<>:"/\\|?*]', '_', self.workflow_name)
                default_name = f"{safe_name}_{safe_workflow}_{timestamp}.json"
            else:
                default_name = f"{safe_name}_{timestamp}.json"
        else:
            # Try to use description text (first few words)
            description = self.description_edit.toPlainText().strip()
            if description:
                # Take first 3-5 words, sanitize, limit length
                words = description.split()[:5]
                desc_part = '_'.join(words)
                desc_part = re.sub(r'[<>:"/\\|?*]', '_', desc_part)
                desc_part = desc_part[:40]  # Limit length
                default_name = f"{desc_part}_{timestamp}.json"
            else:
                # Last resort: generic but descriptive name
                default_name = f"prompt_{timestamp}.json"

        # Get save path
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save JSON Output",
            default_name,
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        # Write JSON to file
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.json_preview_edit.toPlainText())
            show_info("Saved", f"JSON saved to {file_path}", parent=self)
        except Exception as e:
            show_error("Error", f"Failed to save JSON: {str(e)}", parent=self)

    def _refresh_preset_list(self):
        """Refresh the preset list from settings"""
        self.preset_list.clear()

        presets = safe_get_setting("prompt_builder_presets", {})
        for name in sorted(presets.keys()):
            self.preset_list.addItem(name)

    def _on_preset_save(self):
        """Save current state as preset"""
        name, ok = QInputDialog.getText(
            self,
            "Save Preset",
            "Preset name:",
            text=f"Preset {datetime.now().strftime('%Y%m%d_%H%M')}"
        )

        if not ok or not name:
            return

        # Get current presets
        presets = safe_get_setting("prompt_builder_presets", {})

        # Save state
        presets[name] = {
            'state': self.current_state.to_dict(),
            'created': datetime.now().isoformat(),
            'template': self.template_combo.currentText()
        }

        safe_set_setting("prompt_builder_presets", presets)
        self._refresh_preset_list()
        show_info("Saved", f"Preset '{name}' saved successfully", parent=self)

    def _on_preset_load(self, item):
        """Load a preset"""
        if not item:
            return

        name = item.text()
        presets = safe_get_setting("prompt_builder_presets", {})

        if name not in presets:
            show_error("Error", f"Preset '{name}' not found", parent=self)
            return

        preset = presets[name]
        state_dict = preset['state']
        state = PromptBuilderState.from_dict(state_dict)

        # Apply state
        self.description_edit.setPlainText(state.description)

        # Apply positive selections
        for cat_id, section in self.category_sections.items():
            selected = state.positive_selections.get(cat_id, [])
            section.set_selected_options(selected)
            section.set_weights(state.positive_weights)

        # Apply negative selections
        for cat_id, section in self.negative_category_sections.items():
            selected = state.negative_selections.get(cat_id, [])
            section.set_selected_options(selected)
            section.set_weights(state.negative_weights)

        # Apply template
        template = preset.get('template', 'Natural Language')
        index = self.template_combo.findText(template)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)

        self._update_preview()
        logger.info(f"Loaded preset: {name}")

    def _on_preset_delete(self):
        """Delete selected preset"""
        item = self.preset_list.currentItem()
        if not item:
            return

        name = item.text()

        if not confirm_action(
            "Delete Preset",
            f"Delete preset '{name}'?",
            parent=self,
            detail="This cannot be undone."
        ):
            return

        presets = safe_get_setting("prompt_builder_presets", {})
        if name in presets:
            del presets[name]
            safe_set_setting("prompt_builder_presets", presets)
            self._refresh_preset_list()
            logger.info(f"Deleted preset: {name}")
