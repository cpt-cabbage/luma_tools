"""
UI Components for Luma Tools.

This module re-exports components from submodules for convenient importing.
The actual implementations are in:
- workers.py: Threading utilities (Worker, WorkerSignals, ThreadedOperation)
- styles.py: Style constants (LoadingStyles, StatusColors)
- spinners.py: Loading animations (SpinnerWidget, InlineSpinner, PulsingDotsWidget)
- effects.py: Visual effects (TabGlowEffect, TabGlowManager, UIAnimations)
- notifications.py: Notification widgets (ToastNotification, ComfyUIStatusBanner)
- layouts.py: Custom layouts (FlowLayout)
- dialogs.py: Edit dialogs (EditItemDialog, EditModelDialog)
- batch_selector.py: Image selection (BatchImageSelector)
- small_widgets.py: Simple widgets (CollapsibleSection, etc.)
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
from notifications import ToastNotification, ComfyUIStatusBanner
from layouts import FlowLayout
from dialogs import EditItemDialog, EditModelDialog, BaseEditDialog
from batch_selector import BatchImageSelector
from small_widgets import (
    CollapsibleSection, StepGroupBox, StepProgressIndicator,
    EmptyStateWidget, ThumbnailRenderList, RenderListItem
)
from image_viewers import ZoomableImageWidget, EmbeddedImageViewer, FullscreenImageViewer


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
            clipboard.setText(prompt)
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

class GalleryThumbnailWidget(MetadataCopyMixin, QWidget):
    """Thumbnail widget for gallery images with async loading."""
    clicked = Signal(str)
    fullscreen_requested = Signal(str)
    copy_settings_requested = Signal(dict)
    deleted = Signal(str)
    viewed = Signal(str)
    THUMBNAIL_SIZE = (150, 150)
    _placeholder_cache = {}

    def __init__(self, image_path, parent=None, output_dir=None, editable=True, is_new=False):
        super().__init__(parent)
        self.image_path = image_path
        self.output_dir = output_dir or os.path.dirname(image_path)
        self._editable = editable
        self._is_new = is_new
        self._cached_metadata = None
        self._thumbnail_loaded = False
        self._tooltip_loaded = False
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
        self._apply_thumbnail_style()
        self.thumbnail_label.setPixmap(self._create_placeholder("..."))
        layout.addWidget(self.thumbnail_label)

        self.filename_label = QLabel(os.path.basename(self.image_path))
        self.filename_label.setAlignment(Qt.AlignCenter)
        self.filename_label.setStyleSheet("color: #aaaaaa; font-size: 10px;")
        self.filename_label.setWordWrap(True)
        self.filename_label.setMaximumWidth(self.THUMBNAIL_SIZE[0])
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
        self.note_indicator.hide()

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_thumbnail_style(self):
        if self._is_new:
            self.thumbnail_label.setStyleSheet("""
                QLabel {
                    background-color: #2c313a;
                    border: 2px solid #10b981;
                    border-radius: 4px;
                }
            """)
        else:
            self.thumbnail_label.setStyleSheet("""
                QLabel {
                    background-color: #2c313a;
                    border: 1px solid #3c414b;
                    border-radius: 4px;
                }
            """)

    def mark_as_viewed(self):
        if self._is_new:
            self._is_new = False
            self._apply_thumbnail_style()
            self.viewed.emit(self.image_path)

    def load_thumbnail_if_needed(self):
        if not self._thumbnail_loaded:
            self._thumbnail_loaded = True
            self._load_thumbnail_async()
        if not self._tooltip_loaded:
            self._tooltip_loaded = True
            self._load_tooltip_async()

    def _load_tooltip_async(self):
        worker = Worker(self._get_tooltip_data, self.output_dir, self.image_path)
        worker.signals.result.connect(self._on_tooltip_loaded)
        worker.signals.error.connect(lambda msg, tb: None)
        QThreadPool.globalInstance().start(worker)

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
        worker = Worker(self._load_image_data, self.image_path)
        worker.signals.result.connect(self._on_thumbnail_loaded)
        worker.signals.error.connect(lambda msg, tb: self._on_thumbnail_error())
        QThreadPool.globalInstance().start(worker)

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

    def _create_placeholder(self, text):
        if text in GalleryThumbnailWidget._placeholder_cache:
            return GalleryThumbnailWidget._placeholder_cache[text]
        pixmap = QPixmap(*self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#3c414b"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#888888"))
        font = painter.font()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()
        GalleryThumbnailWidget._placeholder_cache[text] = pixmap
        return pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.mark_as_viewed()
            self.clicked.emit(self.image_path)
        super().mousePressEvent(event)

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
        has_input = input_path and os.path.exists(input_path)
        view_input_action = menu.addAction("View Input")
        view_input_action.triggered.connect(lambda: self._view_input(input_path))
        view_input_action.setEnabled(has_input)
        if not has_input and input_image:
            view_input_action.setText("View Input (not found)")

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


# ============================================================================
# GLB THUMBNAIL WIDGET (Stub - full implementation in separate file for large models)
# ============================================================================

class GLBThumbnailWidget(QWidget):
    """Thumbnail widget for 3D models. Full implementation kept for compatibility."""
    clicked = Signal(str)
    deleted = Signal(str)
    viewed = Signal(str)
    THUMBNAIL_SIZE = (150, 150)
    _placeholder_cache = {}

    def __init__(self, model_path, parent=None, output_dir=None, editable=True, is_new=False):
        super().__init__(parent)
        self.model_path = model_path
        self.output_dir = output_dir or os.path.dirname(model_path)
        self._editable = editable
        self._is_new = is_new
        self._thumbnail_loading = False
        self._thumbnail_loaded = False
        self._tooltip_loaded = False
        self._cached_metadata = None
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
        self._apply_thumbnail_style()
        layout.addWidget(self.thumbnail_label)

        self.filename_label = QLabel(os.path.basename(self.model_path))
        self.filename_label.setAlignment(Qt.AlignCenter)
        self._apply_filename_style()
        self.filename_label.setWordWrap(True)
        self.filename_label.setMaximumWidth(self.THUMBNAIL_SIZE[0])
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
        self.note_indicator.hide()

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_thumbnail_style(self):
        if self._is_new:
            self.thumbnail_label.setStyleSheet("""
                QLabel { background-color: #2c313a; border: 2px solid #10b981; border-radius: 4px; }
            """)
        else:
            self.thumbnail_label.setStyleSheet("""
                QLabel { background-color: #2c313a; border: 2px solid #4a9eff; border-radius: 4px; }
            """)

    def _apply_filename_style(self):
        if self._is_new:
            self.filename_label.setStyleSheet("color: #10b981; font-size: 10px; font-weight: bold;")
        else:
            self.filename_label.setStyleSheet("color: #4a9eff; font-size: 10px;")

    def mark_as_viewed(self):
        if self._is_new:
            self._is_new = False
            self._apply_thumbnail_style()
            self._apply_filename_style()
            self.viewed.emit(self.model_path)

    def load_thumbnail_if_needed(self):
        if not self._thumbnail_loaded:
            self._thumbnail_loaded = True
            self._load_thumbnail()
        if not self._tooltip_loaded:
            self._tooltip_loaded = True
            self._load_tooltip_async()

    def _load_tooltip_async(self):
        worker = Worker(self._get_tooltip_data, self.output_dir, self.model_path)
        worker.signals.result.connect(self._on_tooltip_loaded)
        worker.signals.error.connect(lambda msg, tb: None)
        QThreadPool.globalInstance().start(worker)

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
        try:
            worker = Worker(self._generate_thumbnail_sync)
            worker.signals.result.connect(self._on_thumbnail_generated)
            worker.signals.error.connect(self._on_thumbnail_error)
            QThreadPool.globalInstance().start(worker)
        except Exception as e:
            print(f"Error starting thumbnail worker: {e}")
            self._thumbnail_loading = False

    def _generate_thumbnail_sync(self):
        from models.thumbnail_service import get_model_thumbnail_service
        service = get_model_thumbnail_service()
        return service.generate_thumbnail_sync(self.model_path)

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
        if text in GLBThumbnailWidget._placeholder_cache:
            return GLBThumbnailWidget._placeholder_cache[text]
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
        GLBThumbnailWidget._placeholder_cache[text] = pixmap
        return pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.mark_as_viewed()
            self.clicked.emit(self.model_path)
        super().mousePressEvent(event)

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


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def enhance_ui(parent_widget):
    """Initialize UI animations for the parent widget."""
    animator = UIAnimations(parent_widget)
    animator.setup_animations()
    return animator


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


