"""
UI Components for Luma Tools.

This module re-exports components from submodules for convenient importing.
The actual implementations are in:
- workers.py: Threading utilities (Worker, WorkerSignals, ThreadedOperation)
- styles.py: Style constants (LoadingStyles, StatusColors)
- spinners.py: Loading animations (SpinnerWidget, InlineSpinner, PulsingDotsWidget)
- effects.py: Visual effects (TabGlowEffect, TabGlowManager, UIAnimations)
- notifications.py: Notification widgets (ComfyUIStatusBanner)
- layouts.py: Custom layouts (FlowLayout)
- dialogs.py: Edit dialogs (EditItemDialog, EditModelDialog)
- batch_selector.py: Image selection (BatchImageSelector)
- thumbnail_base.py: Base thumbnail widget (BaseThumbnailWidget)
- image_viewers.py: Image and model viewing widgets
"""
import os
from PySide6.QtCore import Qt, QTimer, Signal, QThreadPool, QFile, QTextStream
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QMenu, QDialog, QComboBox, QApplication
)
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap
from shiboken6 import isValid

# Re-export from submodules (absolute imports since resources/ui is in path)
from workers import Worker, WorkerSignals, ThreadedOperation, report_progress
from styles import LoadingStyles, StatusColors, load_stylesheet as _load_simple_stylesheet, apply_stylesheet as _apply_simple_stylesheet
from spinners import SpinnerWidget, InlineSpinner, PulsingDotsWidget, BaseSpinner
from effects import TabGlowEffect, TabGlowManager, UIAnimations
from thumbnail_styles import ThumbnailStyler
from notifications import ComfyUIStatusBanner
from layouts import FlowLayout
from dialogs import EditItemDialog, EditModelDialog, BaseEditDialog
from batch_selector import BatchImageSelector
from thumbnail_base import BaseThumbnailWidget
from image_viewers import ZoomableImageWidget, EmbeddedImageViewer, FullscreenImageViewer
from small_widgets import GallerySectionHeader, StackedThumbnailWidget, show_popup_menu, browse_directory, browse_file


# ============================================================================
# METADATA COPY MIXIN
# ============================================================================

class MetadataCopyMixin:
    """
    Mixin providing unified copy functionality for image/model viewers.
    """

    def _get_current_metadata(self):
        """Get metadata for current item."""
        if hasattr(self, '_get_metadata'):
            return self._get_metadata()
        return getattr(self, '_metadata', None)

    def _show_feedback(self, message, duration=1500):
        """Show UI feedback. Override in subclass for custom feedback."""
        print(message)

    def _copy_prompt(self):
        """Copy prompt to clipboard with feedback."""
        metadata = self._get_current_metadata()
        if not metadata:
            self._show_feedback("No metadata available")
            return

        prompt = metadata.get('prompt', '')
        if not prompt:
            self._show_feedback("No prompt available")
            return

        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(prompt, mode=clipboard.Mode.Clipboard)
            self._show_feedback(f"Prompt copied: {prompt[:50]}...")
        except Exception as e:
            print(f"Error copying prompt: {e}")
            self._show_feedback("Error copying prompt")

    def _copy_settings(self):
        """Apply settings to ComfyUI tab (workflow, seed, editable values)."""
        metadata = self._get_current_metadata()
        if not metadata:
            self._show_feedback("No settings available")
            return

        if not hasattr(self, 'copy_settings_requested'):
            print("Error: copy_settings_requested signal not defined")
            return

        try:
            self.copy_settings_requested.emit(metadata)
            path = getattr(self, 'image_path', getattr(self, 'model_path', 'unknown'))
            self._show_feedback(f"Settings applied from {os.path.basename(path)}")
        except Exception as e:
            print(f"Error applying settings: {e}")
            self._show_feedback("Error applying settings")

    def _copy_path(self, path=None):
        """Copy path to clipboard with feedback."""
        if path is None:
            path = getattr(self, 'image_path', getattr(self, 'model_path', None))

        if not path:
            self._show_feedback("No path available")
            return

        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(path)
            self._show_feedback(f"Path copied: {os.path.basename(path)}")
        except Exception as e:
            print(f"Error copying path: {e}")
            self._show_feedback("Error copying path")


# ============================================================================
# GALLERY THUMBNAIL WIDGET
# ============================================================================

class GalleryThumbnailWidget(MetadataCopyMixin, BaseThumbnailWidget):
    """Thumbnail widget for gallery images with async loading."""
    clicked = Signal(str)
    fullscreen_requested = Signal(str)
    copy_settings_requested = Signal(dict)
    deleted = Signal(str)
    viewed = Signal(str)
    selection_changed = Signal(str, bool)  # path, is_selected

    def __init__(self, image_path, parent=None, output_dir=None, editable=True, is_new=False, gallery_tab=None, has_metadata=False):
        super().__init__(parent)
        self.image_path = image_path
        self.output_dir = output_dir or os.path.dirname(image_path)
        self._editable = editable
        self._is_new = is_new
        self._is_selected = False
        self._is_hovered = False
        self._has_metadata = has_metadata
        self._gallery_tab = gallery_tab
        self._double_click_in_progress = False
        self._cached_metadata = None
        self._thumbnail_loaded = False
        self._tooltip_loaded = False
        self._styler = ThumbnailStyler(has_metadata=has_metadata, is_model=False, border_radius=4)
        self._setup_ui()
        self.setToolTip(os.path.basename(image_path))

    def _setup_ui(self):
        self.setFixedSize(self.THUMBNAIL_SIZE[0] + 10, self.THUMBNAIL_SIZE[1] + 30)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(*self.THUMBNAIL_SIZE)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # Pass all mouse events to parent
        self.thumbnail_label.setContextMenuPolicy(Qt.NoContextMenu)  # No context menu on child
        self._apply_thumbnail_style()
        self.thumbnail_label.setPixmap(self._create_placeholder("..."))
        layout.addWidget(self.thumbnail_label)

        self.filename_label = QLabel(os.path.basename(self.image_path))
        self.filename_label.setAlignment(Qt.AlignCenter)
        self.filename_label.setStyleSheet("color: #aaaaaa; font-size: 10px;")
        self.filename_label.setWordWrap(True)
        self.filename_label.setMaximumWidth(self.THUMBNAIL_SIZE[0])
        self.filename_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # Pass all mouse events to parent
        self.filename_label.setContextMenuPolicy(Qt.NoContextMenu)  # No context menu on child
        layout.addWidget(self.filename_label)

        self.note_indicator = QLabel(self.thumbnail_label)
        self.note_indicator.setText("N")
        self.note_indicator.setAlignment(Qt.AlignCenter)
        self.note_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(74, 158, 255, 0.9);
                color: white;
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        self.note_indicator.setFixedSize(18, 18)
        self.note_indicator.move(self.THUMBNAIL_SIZE[0] - 22, 4)
        self.note_indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.note_indicator.setContextMenuPolicy(Qt.NoContextMenu)
        self.note_indicator.hide()

        # Selection checkmark indicator
        self.selection_indicator = QLabel(self.thumbnail_label)
        self.selection_indicator.setText("✓")
        self.selection_indicator.setAlignment(Qt.AlignCenter)
        self.selection_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(59, 130, 246, 0.95);
                color: white;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.selection_indicator.setFixedSize(24, 24)
        self.selection_indicator.move(4, 4)
        self.selection_indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.selection_indicator.setContextMenuPolicy(Qt.NoContextMenu)
        self.selection_indicator.hide()

    def _apply_thumbnail_style(self):
        """Apply the appropriate style based on current state."""
        style = self._styler.get_style(
            selected=self._is_selected,
            hover=self._is_hovered,
            is_new=self._is_new
        )
        self.thumbnail_label.setStyleSheet(style)

    def mark_as_viewed(self):
        if self._is_new:
            self._is_new = False
            self._apply_thumbnail_style()
            self.viewed.emit(self.image_path)

    def set_selected(self, selected):
        """Set the selection state of this thumbnail."""
        if self._is_selected != selected:
            self._is_selected = selected
            self._apply_thumbnail_style()
            # Note: Checkmark visibility will be updated by gallery tab after signal processing
            self.selection_changed.emit(self.image_path, selected)

    def is_selected(self):
        """Return whether this thumbnail is selected."""
        return self._is_selected

    def load_thumbnail_if_needed(self):
        if not self._thumbnail_loaded:
            self._thumbnail_loaded = True
            self._load_thumbnail_async()
        if not self._tooltip_loaded:
            self._tooltip_loaded = True
            self._load_tooltip_async()

    def _load_tooltip_async(self):
        self._tooltip_worker = Worker(self._get_tooltip_data, self.output_dir, self.image_path)
        self._tooltip_worker.signals.result.connect(self._on_tooltip_loaded)
        self._tooltip_worker.signals.error.connect(lambda msg, tb: None)
        QThreadPool.globalInstance().start(self._tooltip_worker)

    @staticmethod
    def _get_tooltip_data(output_dir, image_path):
        from comfyui.service import get_model_note
        filename = os.path.basename(image_path)
        note = get_model_note(output_dir, filename)
        return (filename, note)

    def _on_tooltip_loaded(self, data):
        # Check if widget is still valid (may have been deleted during async load)
        if not isValid(self):
            return
        filename, note = data
        tooltip_parts = [filename]
        if note:
            tooltip_parts.append(f"\nNote: {note}")
            self.note_indicator.show()
        else:
            self.note_indicator.hide()
        self.setToolTip("\n".join(tooltip_parts))

    def _load_thumbnail_async(self):
        ext = os.path.splitext(self.image_path)[1].lower()
        if ext == '.exr':
            self.thumbnail_label.setPixmap(self._create_placeholder("EXR"))
            return
        self._load_worker = Worker(self._load_image_data, self.image_path)
        self._load_worker.signals.result.connect(self._on_thumbnail_loaded)
        self._load_worker.signals.error.connect(lambda msg, tb: self._on_thumbnail_error())
        QThreadPool.globalInstance().start(self._load_worker)

    @staticmethod
    def _load_image_data(image_path):
        from PySide6.QtGui import QImage
        from PySide6.QtCore import QBuffer, QIODevice
        image = QImage(image_path)
        if image.isNull():
            return None
        scaled = image.scaled(
            GalleryThumbnailWidget.THUMBNAIL_SIZE[0],
            GalleryThumbnailWidget.THUMBNAIL_SIZE[1],
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        scaled.save(buffer, "PNG")
        return buffer.data().data()

    def _on_thumbnail_loaded(self, image_data):
        # Check if widget is still valid (may have been deleted during async load)
        if not isValid(self):
            return
        if image_data is None:
            self.thumbnail_label.setPixmap(self._create_placeholder("?"))
            return
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        if not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap)
        else:
            self.thumbnail_label.setPixmap(self._create_placeholder("?"))

    def _on_thumbnail_error(self):
        # Check if widget is still valid (may have been deleted during async load)
        if not isValid(self):
            return
        self.thumbnail_label.setPixmap(self._create_placeholder("!"))

    def mousePressEvent(self, event):
        print(f"[DEBUG GalleryThumbnailWidget] mousePressEvent button={event.button()} modifiers={event.modifiers()}")
        if event.button() == Qt.LeftButton:
            # Skip if double-click is in progress
            if self._double_click_in_progress:
                super().mousePressEvent(event)
                return

            # Check for shift-click (range selection)
            if event.modifiers() & Qt.ShiftModifier:
                print("[DEBUG] Shift-click detected")
                if self._gallery_tab:
                    self._gallery_tab._on_shift_click_selection(self.image_path)
            # Check for ctrl-click (toggle selection for multi-select)
            elif event.modifiers() & Qt.ControlModifier:
                print("[DEBUG] Ctrl-click detected - toggle selection")
                self.set_selected(not self._is_selected)
            else:
                # Plain left-click: select only this item (clear others first)
                print("[DEBUG] Plain click - clear and select one")
                if self._gallery_tab:
                    self._gallery_tab._clear_selection()
                self.set_selected(True)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Set flag to prevent mousePressEvent from toggling selection
            self._double_click_in_progress = True
            # Mark as viewed and open in embedded viewer
            self.mark_as_viewed()
            self.clicked.emit(self.image_path)
            # Clear flag after short delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, lambda: setattr(self, '_double_click_in_progress', False))
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event):
        """Handle mouse enter - show hover state."""
        super().enterEvent(event)
        self._is_hovered = True
        self._apply_thumbnail_style()

    def leaveEvent(self, event):
        """Handle mouse leave - restore normal state."""
        super().leaveEvent(event)
        self._is_hovered = False
        self._apply_thumbnail_style()

    def contextMenuEvent(self, event):
        """Override to directly handle context menu (fixes child widget event capture)."""
        print(f"[DEBUG GalleryThumbnailWidget] contextMenuEvent triggered for {os.path.basename(self.image_path)}")
        # Check if this item is selected AND there are other selections
        if self._gallery_tab and self._is_selected and len(self._gallery_tab._selected_items) > 1:
            print(f"[DEBUG] Showing batch context menu, {len(self._gallery_tab._selected_items)} items selected")
            self._show_batch_context_menu(event.pos())
        else:
            print(f"[DEBUG] Showing single item context menu")
            self._show_context_menu(event.pos())
        event.accept()

    def _get_metadata(self):
        if self._cached_metadata is None:
            try:
                from comfyui.service import get_image_metadata
                filename = os.path.basename(self.image_path)
                self._cached_metadata = get_image_metadata(self.output_dir, filename) or {}
            except Exception as e:
                print(f"Error loading metadata for {self.image_path}: {e}")
                self._cached_metadata = {}
        return self._cached_metadata

    def _show_context_menu(self, pos):
        try:
            print(f"[DEBUG] _show_context_menu called with pos={pos}")
            menu = QMenu(self)
            open_action = menu.addAction("Open in Viewer")
            open_action.triggered.connect(self._open_image)
            fullscreen_action = menu.addAction("View Fullscreen")
            fullscreen_action.triggered.connect(lambda: self.fullscreen_requested.emit(self.image_path))
            edit_action = menu.addAction("Edit Item")
            edit_action.triggered.connect(self._edit_item)
            if not self._editable:
                edit_action.setEnabled(False)
                edit_action.setText("Edit Item (view only)")
            open_folder_action = menu.addAction("Open Containing Folder")
            open_folder_action.triggered.connect(self._open_folder)

            # View Input option - show the source image used to generate this output
            metadata = self._get_metadata()
            input_image = metadata.get('input_image')
            input_path = os.path.join(self.output_dir, input_image) if input_image else None
            has_input = bool(input_path and os.path.exists(input_path))
            view_input_action = menu.addAction("View Input")
            view_input_action.triggered.connect(lambda: self._view_input(input_path))
            view_input_action.setEnabled(has_input)
            if not has_input and input_image:
                view_input_action.setText("View Input (not found)")

            menu.addSeparator()
            # Properties dialog - comprehensive information
            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(self._show_properties)

            menu.addSeparator()
            has_settings = bool(metadata.get('workflow_preset') or metadata.get('editable_values'))
            apply_settings_action = menu.addAction("Apply Settings")
            apply_settings_action.triggered.connect(self._copy_settings)
            apply_settings_action.setEnabled(has_settings)
            if not has_settings:
                apply_settings_action.setText("Apply Settings (no metadata)")
            prompt = metadata.get('prompt', '')
            copy_prompt_action = menu.addAction("Copy Prompt")
            copy_prompt_action.triggered.connect(self._copy_prompt)
            copy_prompt_action.setEnabled(bool(prompt))
            copy_path_action = menu.addAction("Copy Path")
            copy_path_action.triggered.connect(self._copy_path)

            # Publish to AYON
            menu.addSeparator()
            publish_action = menu.addAction("Publish to AYON")
            publish_action.triggered.connect(self._publish_to_ayon)

            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(self._delete_item)
            if not self._editable:
                delete_action.setEnabled(False)
                delete_action.setText("Delete (view only)")
            global_pos = self.mapToGlobal(pos)
            print(f"[DEBUG] Showing context menu at global position: {global_pos}")
            menu.exec_(global_pos)
            print(f"[DEBUG] Context menu closed")
        except Exception as e:
            import traceback
            print(f"[ERROR] Exception in _show_context_menu: {e}")
            traceback.print_exc()

    def _show_batch_context_menu(self, pos):
        """Show context menu for batch operations on multiple selected items."""
        if not self._gallery_tab:
            return

        menu = QMenu(self)
        count = len(self._gallery_tab._selected_items)

        # Header showing selection count
        header_action = menu.addAction(f"{count} items selected")
        header_action.setEnabled(False)
        menu.addSeparator()

        # View selected
        view_action = menu.addAction("View Selected")
        view_action.triggered.connect(self._gallery_tab._on_view_selected)

        # Publish to AYON
        menu.addSeparator()
        publish_action = menu.addAction("Publish to AYON")
        publish_action.triggered.connect(self._gallery_tab._on_publish_selected)

        # Delete
        menu.addSeparator()
        delete_action = menu.addAction("Delete Selected")
        delete_action.triggered.connect(self._gallery_tab._on_delete_selected)
        if not self._editable:
            delete_action.setEnabled(False)
            delete_action.setText("Delete Selected (view only)")

        # Clear selection
        menu.addSeparator()
        clear_action = menu.addAction("Clear Selection")
        clear_action.triggered.connect(self._gallery_tab._clear_selection)

        menu.exec_(self.mapToGlobal(pos))

    def _publish_to_ayon(self):
        """Publish this image to AYON."""
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break
        try:
            from comfyui.ayon_publisher import publish_comfyui_asset_to_ayon
            publish_comfyui_asset_to_ayon(self.image_path, parent_window, self.output_dir)
        except Exception as e:
            print(f"Error publishing to AYON: {e}")

    def _open_image(self):
        try:
            os.startfile(self.image_path)
        except Exception as e:
            print(f"Error opening image: {e}")

    def _open_folder(self):
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{self.image_path}"')
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _view_input(self, input_path):
        """Open the input image that was used to generate this output."""
        if not input_path or not os.path.exists(input_path):
            print(f"Input image not found: {input_path}")
            return
        try:
            os.startfile(input_path)
        except Exception as e:
            print(f"Error opening input image: {e}")

    def _delete_item(self):
        print(f"[DEBUG] _delete_item called for {self.image_path}")
        from PySide6.QtWidgets import QMessageBox
        filename = os.path.basename(self.image_path)
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break
        reply = QMessageBox.question(
            parent_window, "Delete Item",
            f"Are you sure you want to delete '{filename}'?\n\nThis will permanently delete the file from disk.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                os.remove(self.image_path)
                print(f"Deleted file: {self.image_path}")
                self.deleted.emit(self.image_path)
                container = self.parentWidget()
                if container:
                    container.setUpdatesEnabled(False)
                    try:
                        layout = container.layout()
                        if layout:
                            for i in range(layout.count()):
                                item = layout.itemAt(i)
                                if item and item.widget() is self:
                                    layout.takeAt(i)
                                    break
                        self.setParent(None)
                        self.deleteLater()
                    finally:
                        container.setUpdatesEnabled(True)
                else:
                    self.setParent(None)
                    self.deleteLater()
            except Exception as e:
                print(f"Error deleting file: {e}")
                QMessageBox.critical(parent_window, "Delete Error", f"Could not delete file:\n{e}")

    def _edit_item(self):
        try:
            parent_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'windowTitle'):
                    parent_window = widget
                    break
            dialog = EditItemDialog(self.image_path, self.output_dir, parent_window)
            if dialog.exec() == QDialog.Accepted:
                self._tooltip_loaded = False
                self._load_tooltip_async()
        except Exception as e:
            print(f"Error opening edit item dialog: {e}")

    def _show_properties(self):
        """Show comprehensive properties dialog for this item."""
        try:
            parent_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'windowTitle'):
                    parent_window = widget
                    break
            
            # Import here to avoid circular imports
            from properties_dialog import PropertiesDialog
            
            # Pre-load metadata to avoid loading it twice
            metadata = self._get_metadata()
            
            dialog = PropertiesDialog(
                self.image_path, 
                self.output_dir, 
                metadata=metadata,
                parent=parent_window
            )
            
            # Connect the copy settings signal
            dialog.copy_settings_requested.connect(self.copy_settings_requested)
            
            dialog.exec()
        except Exception as e:
            import traceback
            print(f"Error opening properties dialog: {e}")
            traceback.print_exc()


# ============================================================================
# GLB THUMBNAIL WIDGET (Stub - full implementation in separate file for large models)
# ============================================================================

class GLBThumbnailWidget(BaseThumbnailWidget):
    """Thumbnail widget for 3D models. Full implementation kept for compatibility."""
    clicked = Signal(str)
    deleted = Signal(str)
    viewed = Signal(str)
    selection_changed = Signal(str, bool)  # path, is_selected

    def __init__(self, model_path, parent=None, output_dir=None, editable=True, is_new=False, gallery_tab=None, has_metadata=False):
        super().__init__(parent)
        self.model_path = model_path
        self.output_dir = output_dir or os.path.dirname(model_path)
        self._editable = editable
        self._is_new = is_new
        self._is_selected = False
        self._is_hovered = False
        self._has_metadata = has_metadata
        self._gallery_tab = gallery_tab
        self._double_click_in_progress = False
        self._thumbnail_loading = False
        self._thumbnail_loaded = False
        self._tooltip_loaded = False
        self._cached_metadata = None
        self._styler = ThumbnailStyler(has_metadata=has_metadata, is_model=True, border_radius=4)
        self._setup_ui()
        self.setToolTip(os.path.basename(model_path))

    def _setup_ui(self):
        self.setFixedSize(self.THUMBNAIL_SIZE[0] + 10, self.THUMBNAIL_SIZE[1] + 30)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(*self.THUMBNAIL_SIZE)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # Pass all mouse events to parent
        self.thumbnail_label.setContextMenuPolicy(Qt.NoContextMenu)  # No context menu on child
        self._apply_thumbnail_style()
        layout.addWidget(self.thumbnail_label)

        self.filename_label = QLabel(os.path.basename(self.model_path))
        self.filename_label.setAlignment(Qt.AlignCenter)
        self._apply_filename_style()
        self.filename_label.setWordWrap(True)
        self.filename_label.setMaximumWidth(self.THUMBNAIL_SIZE[0])
        self.filename_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # Pass all mouse events to parent
        self.filename_label.setContextMenuPolicy(Qt.NoContextMenu)  # No context menu on child
        layout.addWidget(self.filename_label)

        self.note_indicator = QLabel(self.thumbnail_label)
        self.note_indicator.setText("N")
        self.note_indicator.setAlignment(Qt.AlignCenter)
        self.note_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(74, 158, 255, 0.9);
                color: white;
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        self.note_indicator.setFixedSize(18, 18)
        self.note_indicator.move(self.THUMBNAIL_SIZE[0] - 22, 4)
        self.note_indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.note_indicator.setContextMenuPolicy(Qt.NoContextMenu)
        self.note_indicator.hide()

        # Selection checkmark indicator
        self.selection_indicator = QLabel(self.thumbnail_label)
        self.selection_indicator.setText("✓")
        self.selection_indicator.setAlignment(Qt.AlignCenter)
        self.selection_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(59, 130, 246, 0.95);
                color: white;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.selection_indicator.setFixedSize(24, 24)
        self.selection_indicator.move(4, 4)
        self.selection_indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.selection_indicator.setContextMenuPolicy(Qt.NoContextMenu)
        self.selection_indicator.hide()

        # 3D model cube indicator (bottom-left corner)
        self.cube_indicator = QLabel(self.thumbnail_label)
        self.cube_indicator.setText("⬣")  # Hexagon as cube symbol
        self.cube_indicator.setAlignment(Qt.AlignCenter)
        self.cube_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(74, 158, 255, 0.85);
                color: white;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }
        """)
        self.cube_indicator.setFixedSize(20, 20)
        self.cube_indicator.move(4, self.THUMBNAIL_SIZE[1] - 24)
        self.cube_indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.cube_indicator.setContextMenuPolicy(Qt.NoContextMenu)
        self.cube_indicator.show()  # Always show for 3D models

    def _apply_thumbnail_style(self):
        """Apply the appropriate style based on current state."""
        style = self._styler.get_style(
            selected=self._is_selected,
            hover=self._is_hovered,
            is_new=self._is_new
        )
        self.thumbnail_label.setStyleSheet(style)

    def _apply_filename_style(self):
        if self._is_new:
            self.filename_label.setStyleSheet("color: #10b981; font-size: 10px; font-weight: bold;")
        else:
            self.filename_label.setStyleSheet("color: #aaaaaa; font-size: 10px;")

    def mark_as_viewed(self):
        if self._is_new:
            self._is_new = False
            self._apply_thumbnail_style()
            self._apply_filename_style()
            self.viewed.emit(self.model_path)

    def set_selected(self, selected):
        """Set selection state and update UI."""
        if self._is_selected != selected:
            self._is_selected = selected
            self._apply_thumbnail_style()
            # Note: Checkmark visibility will be updated by gallery tab after signal processing
            self.selection_changed.emit(self.model_path, selected)

    def is_selected(self):
        """Check if this item is selected."""
        return self._is_selected

    def load_thumbnail_if_needed(self):
        if not self._thumbnail_loaded:
            self._thumbnail_loaded = True
            self._load_thumbnail()
        if not self._tooltip_loaded:
            self._tooltip_loaded = True
            self._load_tooltip_async()

    def _load_tooltip_async(self):
        self._tooltip_worker = Worker(self._get_tooltip_data, self.output_dir, self.model_path)
        self._tooltip_worker.signals.result.connect(self._on_tooltip_loaded)
        self._tooltip_worker.signals.error.connect(lambda msg, tb: None)
        QThreadPool.globalInstance().start(self._tooltip_worker)

    @staticmethod
    def _get_tooltip_data(output_dir, model_path):
        from comfyui.service import get_model_note
        filename = os.path.basename(model_path)
        note = get_model_note(output_dir, filename)
        return (filename, note)

    def _on_tooltip_loaded(self, data):
        # Check if widget is still valid (may have been deleted during async load)
        if not isValid(self):
            return
        filename, note = data
        tooltip_parts = [filename]
        if note:
            tooltip_parts.append(f"\nNote: {note}")
            self.note_indicator.show()
        else:
            self.note_indicator.hide()
        self.setToolTip("\n".join(tooltip_parts))

    def _load_thumbnail(self):
        try:
            from models.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            cached = service.get_cached_thumbnail(self.model_path)
            if cached and not cached.isNull():
                self.thumbnail_label.setPixmap(cached.scaled(
                    *self.THUMBNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
                return
        except Exception as e:
            print(f"Error loading cached GLB thumbnail: {e}")
        self.thumbnail_label.setPixmap(self._create_placeholder("3D"))
        self._generate_thumbnail_async()

    def _generate_thumbnail_async(self):
        """Generate thumbnail on main thread (Three.js viewer requires it)."""
        if self._thumbnail_loading:
            return
        try:
            from models.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            if service.is_pending(self.model_path):
                return
            service.set_pending(self.model_path, True)
        except Exception:
            pass
        self._thumbnail_loading = True

        # Use QTimer to run on main thread (Three.js viewer requires Qt event loop)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._generate_thumbnail_on_main_thread)

    def _generate_thumbnail_on_main_thread(self):
        """Generate thumbnail - must run on main thread for Three.js viewer."""
        if not isValid(self):
            return
        try:
            from models.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            pixmap = service.generate_thumbnail_sync(self.model_path)
            self._on_thumbnail_generated(pixmap)
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
            self._on_thumbnail_error(str(e), "")

    def _on_thumbnail_generated(self, pixmap):
        self._thumbnail_loading = False
        try:
            from models.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            service.set_pending(self.model_path, False)
        except Exception:
            pass
        # Check if widget is still valid (may have been deleted during async load)
        if not isValid(self):
            return
        if pixmap and not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap.scaled(
                *self.THUMBNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))

    def _on_thumbnail_error(self, error_msg, traceback_str):
        self._thumbnail_loading = False
        try:
            from models.thumbnail_service import get_model_thumbnail_service
            service = get_model_thumbnail_service()
            service.set_pending(self.model_path, False)
        except Exception:
            pass
        # Widget may have been deleted during async load - just log the error
        print(f"GLB thumbnail error: {error_msg}")

    def _create_placeholder(self, text):
        """Create a 3D cube icon placeholder for GLB thumbnails."""
        # Create a cache key including the cube indicator
        cache_key = f"glb_3d_cube_{text}"

        # Return cached version if available
        if cache_key in BaseThumbnailWidget._placeholder_cache:
            return BaseThumbnailWidget._placeholder_cache[cache_key]

        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#2a3040"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#4a9eff"), 2))
        center_x, center_y = 75, 65
        size = 30
        painter.drawRect(center_x - size//2, center_y - size//2, size, size)
        offset = 12
        painter.drawLine(center_x - size//2, center_y - size//2, center_x - size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x + size//2, center_y - size//2, center_x + size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x - size//2 + offset, center_y - size//2 - offset, center_x + size//2 + offset, center_y - size//2 - offset)
        painter.drawLine(center_x + size//2, center_y + size//2, center_x + size//2 + offset, center_y + size//2 - offset)
        painter.drawLine(center_x + size//2 + offset, center_y - size//2 - offset, center_x + size//2 + offset, center_y + size//2 - offset)
        painter.setPen(QColor("#888888"))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, 100, self.THUMBNAIL_SIZE[0], 30, Qt.AlignCenter, text)
        painter.end()

        # Cache and return
        BaseThumbnailWidget._placeholder_cache[cache_key] = pixmap
        return pixmap

    def mousePressEvent(self, event):
        print(f"[DEBUG GLBThumbnailWidget] mousePressEvent button={event.button()} modifiers={event.modifiers()}")
        if event.button() == Qt.LeftButton:
            # Skip if double-click is in progress
            if self._double_click_in_progress:
                super().mousePressEvent(event)
                return

            # Check for shift-click (range selection)
            if event.modifiers() & Qt.ShiftModifier:
                print("[DEBUG] Shift-click detected")
                if self._gallery_tab:
                    self._gallery_tab._on_shift_click_selection(self.model_path)
            # Check for ctrl-click (toggle selection for multi-select)
            elif event.modifiers() & Qt.ControlModifier:
                print("[DEBUG] Ctrl-click detected - toggle selection")
                self.set_selected(not self._is_selected)
            else:
                # Plain left-click: select only this item (clear others first)
                print("[DEBUG] Plain click - clear and select one")
                if self._gallery_tab:
                    self._gallery_tab._clear_selection()
                self.set_selected(True)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Set flag to prevent mousePressEvent from toggling selection
            self._double_click_in_progress = True
            # Mark as viewed and open in embedded viewer
            self.mark_as_viewed()
            self.clicked.emit(self.model_path)
            # Clear flag after short delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, lambda: setattr(self, '_double_click_in_progress', False))
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event):
        """Handle mouse enter - show hover state."""
        super().enterEvent(event)
        self._is_hovered = True
        self._apply_thumbnail_style()

    def leaveEvent(self, event):
        """Handle mouse leave - restore normal state."""
        super().leaveEvent(event)
        self._is_hovered = False
        self._apply_thumbnail_style()

    def contextMenuEvent(self, event):
        """Override to directly handle context menu (fixes child widget event capture)."""
        print(f"[DEBUG GLBThumbnailWidget] contextMenuEvent triggered for {os.path.basename(self.model_path)}")
        # Check if this item is selected AND there are other selections
        if self._gallery_tab and self._is_selected and len(self._gallery_tab._selected_items) > 1:
            print(f"[DEBUG] Showing batch context menu, {len(self._gallery_tab._selected_items)} items selected")
            self._show_batch_context_menu(event.pos())
        else:
            print(f"[DEBUG] Showing single item context menu")
            self._show_context_menu(event.pos())
        event.accept()

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        open_action = menu.addAction("Open 3D Viewer")
        open_action.triggered.connect(self._open_viewer)
        edit_action = menu.addAction("Edit Model")
        edit_action.triggered.connect(self._edit_model)
        if not self._editable:
            edit_action.setEnabled(False)
        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(self._open_folder)
        menu.addSeparator()
        # Properties dialog
        properties_action = menu.addAction("Properties")
        properties_action.triggered.connect(self._show_properties)
        menu.addSeparator()
        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(self._copy_path)

        # Publish to AYON
        menu.addSeparator()
        publish_action = menu.addAction("Publish to AYON")
        publish_action.triggered.connect(self._publish_to_ayon)

        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(self._delete_model)
        if not self._editable:
            delete_action.setEnabled(False)
        menu.exec_(self.mapToGlobal(pos))

    def _show_batch_context_menu(self, pos):
        """Show context menu for batch operations on multiple selected items."""
        if not self._gallery_tab:
            return

        menu = QMenu(self)
        count = len(self._gallery_tab._selected_items)

        # Header showing selection count
        header_action = menu.addAction(f"{count} items selected")
        header_action.setEnabled(False)
        menu.addSeparator()

        # View selected
        view_action = menu.addAction("View Selected")
        view_action.triggered.connect(self._gallery_tab._on_view_selected)

        # Publish to AYON
        menu.addSeparator()
        publish_action = menu.addAction("Publish to AYON")
        publish_action.triggered.connect(self._gallery_tab._on_publish_selected)

        # Delete
        menu.addSeparator()
        delete_action = menu.addAction("Delete Selected")
        delete_action.triggered.connect(self._gallery_tab._on_delete_selected)
        if not self._editable:
            delete_action.setEnabled(False)
            delete_action.setText("Delete Selected (view only)")

        # Clear selection
        menu.addSeparator()
        clear_action = menu.addAction("Clear Selection")
        clear_action.triggered.connect(self._gallery_tab._clear_selection)

        menu.exec_(self.mapToGlobal(pos))

    def _publish_to_ayon(self):
        """Publish this 3D model to AYON."""
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break
        try:
            from comfyui.ayon_publisher import publish_comfyui_asset_to_ayon
            publish_comfyui_asset_to_ayon(self.model_path, parent_window, self.output_dir)
        except Exception as e:
            print(f"Error publishing to AYON: {e}")

    def _open_viewer(self):
        """Open the 3D model in a Three.js viewer dialog."""
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break
        try:
            from models.threejs_viewer import ThreeJSViewerDialog, is_threejs_viewer_available
            if is_threejs_viewer_available():
                dialog = ThreeJSViewerDialog(self.model_path, parent_window)
                dialog.show()
                return
        except Exception as e:
            print(f"Error opening 3D viewer: {e}")

    def _open_folder(self):
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{self.model_path}"')
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _copy_path(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.model_path)

    def _delete_model(self):
        from PySide6.QtWidgets import QMessageBox
        filename = os.path.basename(self.model_path)
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break
        reply = QMessageBox.question(
            parent_window, "Delete Model",
            f"Are you sure you want to delete '{filename}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                os.remove(self.model_path)
                self.deleted.emit(self.model_path)
                self.setParent(None)
                self.deleteLater()
            except Exception as e:
                print(f"Error deleting file: {e}")
                QMessageBox.critical(parent_window, "Delete Error", f"Could not delete file:\n{e}")

    def _edit_model(self):
        try:
            parent_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'windowTitle'):
                    parent_window = widget
                    break
            dialog = EditModelDialog(self.model_path, self.output_dir, parent_window)
            dialog.exec()
        except Exception as e:
            print(f"Error opening edit model dialog: {e}")

    def _show_properties(self):
        """Show comprehensive properties dialog for this model."""
        try:
            parent_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'windowTitle'):
                    parent_window = widget
                    break
            
            # Import here to avoid circular imports
            from properties_dialog import PropertiesDialog
            
            # Pre-load metadata (models might not have metadata, but dialog handles this gracefully)
            metadata = getattr(self, '_cached_metadata', None)
            if metadata is None:
                try:
                    from comfyui.service import get_image_metadata
                    filename = os.path.basename(self.model_path)
                    metadata = get_image_metadata(self.output_dir, filename) or {}
                except Exception:
                    metadata = {}
            
            dialog = PropertiesDialog(
                self.model_path, 
                self.output_dir, 
                metadata=metadata,
                parent=parent_window
            )
            
            dialog.exec()
        except Exception as e:
            import traceback
            print(f"Error opening properties dialog: {e}")
            traceback.print_exc()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def enhance_ui(parent_widget):
    """Initialize UI animations for the parent widget."""
    animator = UIAnimations(parent_widget)
    animator.setup_animations()
    return animator


# ============================================================================
# GALLERY SELECTION TOOLBAR
# ============================================================================

class GallerySelectionToolbar(QWidget):
    """Floating toolbar for gallery multi-select actions."""

    # Signals for multi-select actions
    delete_selected = Signal()
    publish_selected = Signal()
    view_selected = Signal()
    clear_selection = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup the toolbar UI."""
        # Set as floating toolbar (will be positioned by parent)
        self.setAutoFillBackground(True)

        # Main horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Selection count label
        self.count_label = QLabel("0 items selected")
        self.count_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 4px;
            }
        """)
        layout.addWidget(self.count_label)

        # Spacer
        layout.addStretch()

        # View selected button
        self.view_btn = QPushButton("View")
        self.view_btn.setToolTip("Open selected images in viewer")
        self.view_btn.clicked.connect(self.view_selected.emit)
        self.view_btn.setStyleSheet(self._get_button_style())
        layout.addWidget(self.view_btn)

        # Publish to AYON button
        self.publish_btn = QPushButton("Publish to AYON")
        self.publish_btn.setToolTip("Publish selected images to AYON")
        self.publish_btn.clicked.connect(self.publish_selected.emit)
        self.publish_btn.setStyleSheet(self._get_button_style())
        layout.addWidget(self.publish_btn)

        # Delete button
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setToolTip("Delete selected images")
        self.delete_btn.clicked.connect(self.delete_selected.emit)
        self.delete_btn.setStyleSheet(self._get_button_style("#dc2626"))
        layout.addWidget(self.delete_btn)

        # Clear selection button
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setToolTip("Clear selection (Escape)")
        self.clear_btn.setFixedSize(32, 32)
        self.clear_btn.clicked.connect(self.clear_selection.emit)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9ca3af;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
        """)
        layout.addWidget(self.clear_btn)

        # Toolbar background style
        self.setStyleSheet("""
            GallerySelectionToolbar {
                background-color: rgba(59, 130, 246, 0.95);
                border: 1px solid rgba(96, 165, 250, 0.5);
                border-radius: 8px;
            }
        """)

    def _get_button_style(self, hover_color="#2563eb"):
        """Get button stylesheet with optional custom hover color."""
        return f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.15);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
                border-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 0, 0, 0.2);
            }}
        """

    def update_count(self, count):
        """Update the selection count display."""
        if count == 1:
            self.count_label.setText("1 item selected")
        else:
            self.count_label.setText(f"{count} items selected")

    def position_at_bottom(self, parent_widget):
        """Position toolbar at bottom center of parent widget."""
        # Calculate position
        parent_width = parent_widget.width()
        toolbar_width = self.sizeHint().width()
        x = (parent_width - toolbar_width) // 2
        y = parent_widget.height() - self.sizeHint().height() - 20

        # Position and ensure visible
        self.move(x, y)
        self.raise_()


def load_stylesheet():
    """Load combined QDarkStyle and custom stylesheet."""
    from config import QDARKSTYLE_PATH, CUSTOM_STYLE_PATH
    file = QFile(QDARKSTYLE_PATH)
    file.open(QFile.ReadOnly | QFile.Text)
    stream = QTextStream(file)
    base_style = stream.readAll()
    file.close()
    custom_file = QFile(CUSTOM_STYLE_PATH)
    custom_file.open(QFile.ReadOnly | QFile.Text)
    custom_stream = QTextStream(custom_file)
    custom_style = custom_stream.readAll()
    custom_file.close()
    return base_style + "\n" + custom_style


def apply_stylesheet(app):
    """Apply stylesheet to the application."""
    stylesheet = load_stylesheet()
    app.setStyleSheet(stylesheet)


