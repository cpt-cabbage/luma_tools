"""
Image viewer widgets for the gallery.

Contains embedded and fullscreen viewers with support for images, 3D models, and videos.
"""
import os
from PySide6.QtCore import Qt, QTimer, Signal, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QMenu, QComboBox, QApplication
)
from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap

from workers import Worker


class ZoomableImageWidget(QtWidgets.QGraphicsView):
    """A widget that displays an image with support for zooming and panning."""
    double_clicked = Signal()
    zoom_changed = Signal(str)
    ZOOM_LEVELS = ["Fit", "100%", "50%", "25%", "10%"]

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QPainter
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.viewport().setCursor(Qt.ArrowCursor)
        self.setStyleSheet("background: transparent;")

        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QtWidgets.QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        self._is_panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0
        self._current_zoom = "Fit"

    def setPixmap(self, pixmap):
        self._scene.removeItem(self._pixmap_item)
        self._pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._pixmap_item)
        self.setSceneRect(self._pixmap_item.boundingRect())
        self._current_zoom = "Fit"
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        self.zoom_changed.emit("Fit")

    def setZoomLevel(self, level):
        if not self._pixmap_item.pixmap() or self._pixmap_item.pixmap().isNull():
            return
        self._current_zoom = level
        if level == "Fit":
            self.resetTransform()
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        else:
            percentage = int(level.replace("%", ""))
            scale = percentage / 100.0
            self.resetTransform()
            self.scale(scale, scale)
            self.centerOn(self._pixmap_item)
        self.zoom_changed.emit(level)

    def currentZoom(self):
        return self._current_zoom

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        zoom_factor = zoom_in_factor if event.angleDelta().y() > 0 else zoom_out_factor
        self.scale(zoom_factor, zoom_factor)
        current_scale = self.transform().m11() * 100
        self._current_zoom = f"{int(current_scale)}%"
        self.zoom_changed.emit(self._current_zoom)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start_x = event.x()
            self._pan_start_y = event.y()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta_x = event.x() - self._pan_start_x
            delta_y = event.y() - self._pan_start_y
            self._pan_start_x = event.x()
            self._pan_start_y = event.y()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta_x)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta_y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class EmbeddedImageViewer(QWidget):
    """
    Embedded image viewer with keyboard navigation for use within the gallery tab.

    Controls:
    - Left/Right arrows or A/D: Navigate between images
    - Escape or Backspace: Close viewer and return to gallery
    - Home/End: Jump to first/last image
    - C: Copy prompt to clipboard (if available)
    - S: Copy settings to ComfyUI tab (if available)
    """
    closed = Signal()
    view_fullscreen = Signal(str, int)
    copy_settings_requested = Signal(dict)

    def __init__(self, image_paths, start_index=0, output_dir=None, parent=None):
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.current_index = start_index
        self.output_dir = output_dir

        self._setup_ui()
        self._load_current_image()
        self.setFocusPolicy(Qt.StrongFocus)

    def _setup_ui(self):
        """Set up the embedded viewer UI."""
        self.setStyleSheet("background-color: #1a1a1a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        self.top_bar = QWidget()
        self.top_bar.setStyleSheet("background-color: rgba(0, 0, 0, 0.5);")
        self.top_bar.setFixedHeight(40)

        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 5, 10, 5)

        self.back_btn = QPushButton("< Back to Gallery")
        self.back_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: #4a9eff; border: none; font-size: 12px; padding: 5px 10px; }
            QPushButton:hover { color: #7ab8ff; }
        """)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self._on_back)
        top_layout.addWidget(self.back_btn)

        top_layout.addStretch()

        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("color: #888888; font-size: 12px;")
        top_layout.addWidget(self.counter_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(ZoomableImageWidget.ZOOM_LEVELS)
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.setFixedWidth(80)
        self.zoom_combo.setStyleSheet("""
            QComboBox { background-color: #2a2a2a; color: #cccccc; border: 1px solid #555555; border-radius: 3px; padding: 3px 8px; font-size: 11px; }
            QComboBox:hover { border-color: #4a9eff; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #888888; margin-right: 5px; }
            QComboBox QAbstractItemView { background-color: #2a2a2a; color: #cccccc; selection-background-color: #4a9eff; border: 1px solid #555555; }
        """)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        top_layout.addWidget(self.zoom_combo)

        self.fullscreen_btn = QPushButton("Fullscreen")
        self.fullscreen_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888888; border: 1px solid #555555; border-radius: 3px; font-size: 11px; padding: 3px 10px; }
            QPushButton:hover { color: #ffffff; border-color: #4a9eff; }
        """)
        self.fullscreen_btn.setCursor(Qt.PointingHandCursor)
        self.fullscreen_btn.clicked.connect(self._on_fullscreen)
        top_layout.addWidget(self.fullscreen_btn)

        layout.addWidget(self.top_bar)

        # Image container with navigation
        image_container = QWidget()
        image_layout = QHBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)

        self.left_btn = QPushButton("<")
        self.left_btn.setFixedWidth(50)
        self.left_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 24px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
            QPushButton:disabled { color: #333333; }
        """)
        self.left_btn.setCursor(Qt.PointingHandCursor)
        self.left_btn.clicked.connect(self._prev_image)
        image_layout.addWidget(self.left_btn)

        self.image_stack = QtWidgets.QStackedWidget()
        image_layout.addWidget(self.image_stack, stretch=1)

        # 1. Zoomable Image View
        self.image_view = ZoomableImageWidget()
        self.image_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_view.customContextMenuRequested.connect(self._show_context_menu)
        self.image_view.double_clicked.connect(self.close)
        self.image_view.zoom_changed.connect(self._on_image_zoom_changed)
        self.image_stack.addWidget(self.image_view)

        # 2. 3D Model Viewer - Lazy initialization
        self._has_glb_viewer = None
        self.glb_viewer = None
        self._use_pyvista_viewer = False
        self._glb_viewer_initialized = False

        # 3. Video Player
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget

            self.video_widget = QVideoWidget()
            self.video_widget.setStyleSheet("background-color: #000000;")
            # Qt6: QMediaPlayer constructor changed, no flags needed
            self.media_player = QMediaPlayer(self)
            self.media_player.setVideoOutput(self.video_widget)
            self.image_stack.addWidget(self.video_widget)
            self._has_video_player = True
        except Exception as e:
            print(f"Video player not available: {e}")
            self._has_video_player = False
            self.video_widget = None
            self.media_player = None

        # 4. Message Label
        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("background-color: #1a1a1a; color: #888888; font-size: 16px;")
        self.image_stack.addWidget(self.message_label)

        self.right_btn = QPushButton(">")
        self.right_btn.setFixedWidth(50)
        self.right_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 24px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
            QPushButton:disabled { color: #333333; }
        """)
        self.right_btn.setCursor(Qt.PointingHandCursor)
        self.right_btn.clicked.connect(self._next_image)
        image_layout.addWidget(self.right_btn)

        layout.addWidget(image_container, stretch=1)

        # Bottom info bar
        self.info_bar = QWidget()
        self.info_bar.setStyleSheet("background-color: rgba(0, 0, 0, 0.5);")
        self.info_bar.setFixedHeight(35)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(15, 5, 15, 5)

        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        info_layout.addWidget(self.filename_label)

        # 3D Model controls (hidden by default)
        self.texture_toggle_btn = QPushButton("Wireframe")
        self.texture_toggle_btn.setFixedHeight(25)
        self.texture_toggle_btn.setStyleSheet("""
            QPushButton { background-color: #4a9eff; color: white; border: none; border-radius: 3px; padding: 0 10px; font-size: 11px; }
            QPushButton:hover { background-color: #5aa9ff; }
        """)
        self.texture_toggle_btn.clicked.connect(self._toggle_3d_render_mode)
        self.texture_toggle_btn.hide()
        info_layout.addWidget(self.texture_toggle_btn)

        self.keep_camera_checkbox = QCheckBox("Keep Camera")
        self.keep_camera_checkbox.setFixedHeight(25)
        self.keep_camera_checkbox.setStyleSheet("""
            QCheckBox { color: #888888; font-size: 11px; spacing: 5px; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #555555; border-radius: 3px; background-color: #2a2a2a; }
            QCheckBox::indicator:checked { background-color: #4a9eff; border-color: #4a9eff; }
            QCheckBox::indicator:hover { border-color: #4a9eff; }
        """)
        self.keep_camera_checkbox.setToolTip("Preserve camera position when navigating between 3D models")
        self.keep_camera_checkbox.hide()
        info_layout.addWidget(self.keep_camera_checkbox)

        # Publish to AYON button
        self.publish_to_ayon_btn = QPushButton("Publish to AYON")
        self.publish_to_ayon_btn.setFixedHeight(25)
        self.publish_to_ayon_btn.setStyleSheet("""
            QPushButton { background-color: #10b981; color: white; border: none; border-radius: 3px; padding: 0 12px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background-color: #14ce94; }
            QPushButton:disabled { background-color: #3c414b; color: #6b6f78; }
        """)
        self.publish_to_ayon_btn.clicked.connect(self._publish_to_ayon)

        try:
            from state_manager import get_app_state
            from ayon.service import AYON_AVAILABLE
            app_state = get_app_state()
            is_standalone = app_state.standalone_mode

            if is_standalone or not AYON_AVAILABLE:
                self.publish_to_ayon_btn.setEnabled(False)
                self.publish_to_ayon_btn.setToolTip("AYON publishing is not available" if not AYON_AVAILABLE else "Not available in standalone mode")
            else:
                self.publish_to_ayon_btn.setToolTip("Publish this asset to AYON")
        except Exception as e:
            print(f"Warning: Could not initialize AYON button: {e}")
            self.publish_to_ayon_btn.setEnabled(False)
            self.publish_to_ayon_btn.setToolTip("AYON is not available")

        info_layout.addWidget(self.publish_to_ayon_btn)

        self._3d_textured_mode = False
        self._current_3d_path = None
        self._saved_camera_state = None

        info_layout.addStretch()

        help_label = QLabel("Navigate | Esc Back | C Copy Prompt")
        help_label.setStyleSheet("color: #555555; font-size: 10px;")
        info_layout.addWidget(help_label)

        layout.addWidget(self.info_bar)

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def _init_glb_viewer_async(self, callback=None):
        """Initialize the GLB viewer widget asynchronously."""
        if self._glb_viewer_initialized:
            if callback:
                callback(self._has_glb_viewer)
            return

        self.message_label.setText("Initializing 3D viewer...")
        self.image_stack.setCurrentWidget(self.message_label)

        # Use QTimer to defer initialization so UI can update
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._do_init_glb_viewer(callback))

    def _do_init_glb_viewer(self, callback=None):
        """Actually initialize the GLB viewer widget (called after short delay)."""
        # Don't use worker thread - Qt widgets must be created on main thread
        # Just check availability and create widget directly

        # Add python directory to path if needed
        import sys
        import os
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python_dir = os.path.join(os.path.dirname(current_dir), 'python')
        if python_dir not in sys.path:
            sys.path.insert(0, python_dir)

        try:
            from models.viewer import ModelViewerWidget, is_viewer_available, OPENGL_AVAILABLE, PYOPENGL_AVAILABLE, MODEL_LOADER_AVAILABLE
            print(f"3D Viewer availability check:")
            print(f"  OPENGL_AVAILABLE: {OPENGL_AVAILABLE}")
            print(f"  PYOPENGL_AVAILABLE: {PYOPENGL_AVAILABLE}")
            print(f"  MODEL_LOADER_AVAILABLE: {MODEL_LOADER_AVAILABLE}")

            if is_viewer_available():
                # Configure OpenGL surface format before widget creation to prevent window flashing
                from PySide6.QtGui import QSurfaceFormat
                fmt = QSurfaceFormat()
                fmt.setDepthBufferSize(24)
                fmt.setStencilBufferSize(8)
                fmt.setVersion(2, 1)  # OpenGL 2.1
                fmt.setProfile(QSurfaceFormat.NoProfile)
                fmt.setSamples(4)  # 4x MSAA
                fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
                QSurfaceFormat.setDefaultFormat(fmt)

                # Block updates on parent window during OpenGL widget creation
                parent_window = self.window()
                if parent_window:
                    parent_window.setUpdatesEnabled(False)

                try:
                    # Create the OpenGL widget
                    self.glb_viewer = ModelViewerWidget()

                    # Add to stack (will be hidden until set as current)
                    self.image_stack.addWidget(self.glb_viewer)

                    self._has_glb_viewer = True
                    self._use_pyvista_viewer = False
                    print(f"✓ Using model_viewer GLB viewer")
                    self._glb_viewer_initialized = True

                    if callback:
                        callback(True)
                finally:
                    # Re-enable updates
                    if parent_window:
                        parent_window.setUpdatesEnabled(True)
                        # Process pending events to ensure smooth rendering
                        from PySide6.QtCore import QCoreApplication
                        QCoreApplication.processEvents()

                return
            else:
                print(f"✗ Model viewer not available - one or more requirements missing")
        except Exception as e:
            print(f"✗ Model viewer import failed: {e}")
            import traceback
            traceback.print_exc()

        try:
            from glb_viewer_pyvista import PyVistaGLBViewerWidget, is_pyvista_available
            if is_pyvista_available():
                self.glb_viewer = PyVistaGLBViewerWidget()
                self.image_stack.addWidget(self.glb_viewer)
                self._has_glb_viewer = True
                self._use_pyvista_viewer = True
                print(f"Using pyvista GLB viewer")
                self._glb_viewer_initialized = True
                if callback:
                    callback(True)
                return
        except Exception as e:
            print(f"PyVista GLB viewer not available: {e}")

        try:
            from glb_viewer import GLBViewerWidget
            self.glb_viewer = GLBViewerWidget()
            self.image_stack.addWidget(self.glb_viewer)
            self._has_glb_viewer = True
            self._use_pyvista_viewer = False
            print(f"Using opengl GLB viewer")
            self._glb_viewer_initialized = True
            if callback:
                callback(True)
            return
        except Exception as e:
            print(f"OpenGL GLB viewer not available: {e}")

        # No viewer available
        self._has_glb_viewer = False
        self._glb_viewer_initialized = True
        if callback:
            callback(False)

    def _load_current_image(self):
        """Load and display the current media (image, 3D model, or video)."""
        if not self.image_paths or self.current_index < 0 or self.current_index >= len(self.image_paths):
            return

        media_path = self.image_paths[self.current_index]

        try:
            ext = os.path.splitext(media_path)[1].lower()

            if hasattr(self, '_has_video_player') and self._has_video_player and self.media_player:
                self.media_player.stop()

            MODEL_EXTENSIONS = {'.glb', '.gltf', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz', '.dae', '.stl', '.ply'}
            if ext in MODEL_EXTENSIONS:
                self.texture_toggle_btn.show()
                self.keep_camera_checkbox.show()
                self._current_3d_path = media_path
                self._3d_textured_mode = False
                self.texture_toggle_btn.setText("Wireframe")

                if not self._glb_viewer_initialized:
                    self.message_label.setText("Initializing 3D viewer...")
                    self.image_stack.setCurrentWidget(self.message_label)
                    self._pending_3d_path = media_path

                    def on_viewer_ready(available):
                        if available and hasattr(self, '_pending_3d_path'):
                            self._load_3d_model(self._pending_3d_path)
                        elif not available:
                            self.message_label.setText("3D Model Viewer Not Available\n\nInstall pyvista and pyvistaqt")
                            self.image_stack.setCurrentWidget(self.message_label)

                    self._init_glb_viewer_async(callback=on_viewer_ready)
                elif self._has_glb_viewer and self.glb_viewer:
                    self._load_3d_model(media_path)
                else:
                    self.message_label.setText("3D Model Viewer Not Available")
                    self.image_stack.setCurrentWidget(self.message_label)

            elif ext in ('.mp4', '.mov', '.avi', '.webm'):
                self.texture_toggle_btn.hide()
                self.keep_camera_checkbox.hide()
                self._current_3d_path = None
                if hasattr(self, '_has_video_player') and self._has_video_player and self.media_player and self.video_widget:
                    from PySide6.QtMultimedia import QMediaContent
                    from PySide6.QtCore import QUrl

                    media_content = QMediaContent(QUrl.fromLocalFile(media_path))
                    self.media_player.setMedia(media_content)
                    self.image_stack.setCurrentWidget(self.video_widget)
                    self.media_player.play()
                else:
                    self.message_label.setText("Video Player Not Available")
                    self.image_stack.setCurrentWidget(self.message_label)

            elif ext == '.exr':
                self.texture_toggle_btn.hide()
                self.keep_camera_checkbox.hide()
                self._current_3d_path = None
                self.message_label.setText("EXR Preview Not Available")
                self.image_stack.setCurrentWidget(self.message_label)

            else:
                self.texture_toggle_btn.hide()
                self.keep_camera_checkbox.hide()
                self._current_3d_path = None
                pixmap = QPixmap(media_path)
                if not pixmap.isNull():
                    self.image_view.setPixmap(pixmap)
                    self.image_stack.setCurrentWidget(self.image_view)
                else:
                    self.message_label.setText("Failed to load image")
                    self.image_stack.setCurrentWidget(self.message_label)

        except Exception as e:
            self.message_label.setText(f"Error: {e}")
            self.image_stack.setCurrentWidget(self.message_label)

        self._update_info()

    def _load_3d_model(self, media_path):
        """Load a 3D model into the viewer."""
        if (self.keep_camera_checkbox.isChecked() and
            self.glb_viewer and hasattr(self.glb_viewer, 'get_camera_state')):
            self._saved_camera_state = self.glb_viewer.get_camera_state()
        else:
            self._saved_camera_state = None

        self.message_label.setText(f"Loading 3D model...\n{os.path.basename(media_path)}")
        self.image_stack.setCurrentWidget(self.message_label)

        try:
            from models.viewer import ModelLoaderWorker
            loader = ModelLoaderWorker(media_path)
            loader.signals.finished.connect(self._on_model_loaded)
            loader.signals.error.connect(self._on_model_error)
            QThreadPool.globalInstance().start(loader)
        except ImportError:
            if self._use_pyvista_viewer:
                from glb_viewer_pyvista import PyVistaModelLoaderWorker
                loader = PyVistaModelLoaderWorker(media_path)
            else:
                from glb_viewer import ModelLoaderWorker
                loader = ModelLoaderWorker(media_path)
            loader.signals.finished.connect(self._on_model_loaded)
            loader.signals.error.connect(self._on_model_error)
            QThreadPool.globalInstance().start(loader)

    def _on_model_loaded(self, model_data):
        """Handle successful 3D model loading."""
        if self.glb_viewer:
            try:
                self.glb_viewer.set_model_data(model_data)
                if self._saved_camera_state and hasattr(self.glb_viewer, 'set_camera_state'):
                    self.glb_viewer.set_camera_state(self._saved_camera_state)
                self.image_stack.setCurrentWidget(self.glb_viewer)
                self.glb_viewer.setFocus()
            except Exception as e:
                import traceback
                traceback.print_exc()
                error_msg = f"Failed to display 3D model:\n{str(e)}"
                self.message_label.setText(f"Error Loading 3D Model\n\n{error_msg}")
                self.image_stack.setCurrentWidget(self.message_label)

    def _on_model_error(self, error_msg):
        """Handle 3D model loading error."""
        self.message_label.setText(f"Error Loading 3D Model\n\n{error_msg}")
        self.image_stack.setCurrentWidget(self.message_label)

    def _update_info(self):
        """Update info labels and button states."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        self.filename_label.setText(filename)
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.image_paths)}")

        self.left_btn.setEnabled(self.current_index > 0)
        self.right_btn.setEnabled(self.current_index < len(self.image_paths) - 1)

    def _next_image(self):
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._load_current_image()

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()

    def _on_back(self):
        self.closed.emit()

    def _on_fullscreen(self):
        if self.image_paths:
            self.view_fullscreen.emit(self.image_paths[self.current_index], self.current_index)

    def _on_zoom_changed(self, level):
        self.image_view.setZoomLevel(level)

    def _on_image_zoom_changed(self, level):
        self.zoom_combo.blockSignals(True)
        if level in ZoomableImageWidget.ZOOM_LEVELS:
            self.zoom_combo.setCurrentText(level)
        self.zoom_combo.blockSignals(False)

    def _toggle_3d_render_mode(self):
        """Toggle between textured and wireframe mode for 3D models."""
        if not self._current_3d_path:
            return

        if self._has_glb_viewer and self.glb_viewer:
            self.glb_viewer.toggle_wireframe()
            self._3d_textured_mode = not self._3d_textured_mode
            self.texture_toggle_btn.setText("Textured" if self._3d_textured_mode else "Wireframe")

    def _copy_prompt(self):
        """Copy prompt for current image to clipboard."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.service import get_image_metadata
            metadata = get_image_metadata(output_dir, filename)
            if metadata and metadata.get('prompt'):
                clipboard = QApplication.clipboard()
                clipboard.setText(metadata['prompt'])
                self.filename_label.setText(f"{filename} - Prompt copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No prompt available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            print(f"Error copying prompt: {e}")

    def _copy_settings(self):
        """Copy all settings for current image to the ComfyUI tab."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.service import get_image_metadata
            metadata = get_image_metadata(output_dir, filename)
            if metadata:
                self.copy_settings_requested.emit(metadata)
                self.filename_label.setText(f"{filename} - Settings copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No settings available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            print(f"Error copying settings: {e}")

    def _publish_to_ayon(self):
        """Publish this image to AYON."""
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break

        try:
            from comfyui_ayon_publisher import publish_comfyui_asset_to_ayon
            image_path = self.image_paths[self.current_index]
            success = publish_comfyui_asset_to_ayon(
                file_path=image_path,
                parent_widget=parent_window,
                output_dir=self.output_dir
            )
            if success:
                print(f"Successfully published image to AYON: {image_path}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(parent_window, "Publish Error", f"Failed to publish image to AYON:\n\n{str(e)}")

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_D):
            self._next_image()
        elif key in (Qt.Key_Left, Qt.Key_A):
            self._prev_image()
        elif key in (Qt.Key_Escape, Qt.Key_Backspace):
            self._on_back()
        elif key == Qt.Key_Home:
            self.current_index = 0
            self._load_current_image()
        elif key == Qt.Key_End:
            self.current_index = len(self.image_paths) - 1
            self._load_current_image()
        elif key == Qt.Key_C:
            self._copy_prompt()
        elif key == Qt.Key_S:
            self._copy_settings()
        elif key == Qt.Key_F:
            self._on_fullscreen()
        else:
            super().keyPressEvent(event)

    def _show_context_menu(self, pos):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        menu = QMenu(self)

        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(lambda: self._open_folder(image_path))

        menu.addSeparator()

        copy_settings_action = menu.addAction("Copy Settings (S)")
        copy_settings_action.triggered.connect(self._copy_settings)

        copy_prompt_action = menu.addAction("Copy Prompt (C)")
        copy_prompt_action.triggered.connect(self._copy_prompt)

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path(image_path))

        menu.exec_(self.image_view.mapToGlobal(pos))

    def _open_folder(self, image_path):
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{image_path}"')
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _copy_path(self, image_path):
        clipboard = QApplication.clipboard()
        clipboard.setText(image_path)
        self.filename_label.setText(f"{os.path.basename(image_path)} - Path copied!")
        QTimer.singleShot(1500, self._update_info)


class FullscreenImageViewer(QWidget):
    """
    Fullscreen image viewer (separate window) with keyboard navigation.

    Controls:
    - Left/Right arrows or A/D: Navigate between images
    - Escape or Q: Close viewer
    - Home/End: Jump to first/last image
    - Space: Toggle filename display
    - C: Copy prompt to clipboard (if available)
    - S: Copy settings to ComfyUI tab (if available)
    """
    closed = Signal()
    copy_settings_requested = Signal(dict)

    def __init__(self, image_paths, start_index=0, output_dir=None, parent=None):
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.current_index = start_index
        self.output_dir = output_dir
        self._show_info = True

        self._setup_ui()
        self._load_current_image()

    def _setup_ui(self):
        """Set up the fullscreen UI."""
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet("background-color: #1a1a1a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.image_stack, stretch=1)

        self.image_view = ZoomableImageWidget()
        self.image_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_view.customContextMenuRequested.connect(self._show_context_menu)
        self.image_view.double_clicked.connect(self.close)
        self.image_view.zoom_changed.connect(self._on_image_zoom_changed)
        self.image_stack.addWidget(self.image_view)

        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("background-color: #1a1a1a; color: #888888; font-size: 16px;")
        self.image_stack.addWidget(self.message_label)

        # Info bar
        self.info_bar = QWidget()
        self.info_bar.setStyleSheet("QWidget { background-color: rgba(0, 0, 0, 0.7); padding: 10px; }")
        self.info_bar.setFixedHeight(60)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(20, 5, 20, 5)

        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("color: #ffffff; font-size: 14px;")
        info_layout.addWidget(self.filename_label)

        info_layout.addStretch()

        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("color: #888888; font-size: 12px;")
        info_layout.addWidget(self.counter_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(ZoomableImageWidget.ZOOM_LEVELS)
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.setFixedWidth(80)
        self.zoom_combo.setStyleSheet("""
            QComboBox { background-color: #2a2a2a; color: #cccccc; border: 1px solid #555555; border-radius: 3px; padding: 3px 8px; font-size: 11px; }
            QComboBox:hover { border-color: #4a9eff; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #888888; margin-right: 5px; }
            QComboBox QAbstractItemView { background-color: #2a2a2a; color: #cccccc; selection-background-color: #4a9eff; border: 1px solid #555555; }
        """)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        info_layout.addWidget(self.zoom_combo)

        self.help_label = QLabel("Navigate | Esc Close | Space Toggle Info | C Copy Prompt")
        self.help_label.setStyleSheet("color: #666666; font-size: 10px; margin-left: 20px;")
        info_layout.addWidget(self.help_label)

        layout.addWidget(self.info_bar)

        self._create_nav_buttons()

    def _create_nav_buttons(self):
        """Create navigation buttons on the sides."""
        self.left_btn = QPushButton("<", self)
        self.left_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 30px; padding: 20px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
        """)
        self.left_btn.setCursor(Qt.PointingHandCursor)
        self.left_btn.clicked.connect(self._prev_image)

        self.right_btn = QPushButton(">", self)
        self.right_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 30px; padding: 20px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
        """)
        self.right_btn.setCursor(Qt.PointingHandCursor)
        self.right_btn.clicked.connect(self._next_image)

    def showEvent(self, event):
        super().showEvent(event)
        self.showFullScreen()
        self._position_nav_buttons()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_nav_buttons()

    def _position_nav_buttons(self):
        btn_width = 60
        btn_height = 100
        margin = 20
        center_y = (self.height() - self.info_bar.height() - btn_height) // 2

        self.left_btn.setGeometry(margin, center_y, btn_width, btn_height)
        self.right_btn.setGeometry(self.width() - margin - btn_width, center_y, btn_width, btn_height)

        self.left_btn.setVisible(self.current_index > 0)
        self.right_btn.setVisible(self.current_index < len(self.image_paths) - 1)

    def _load_current_image(self):
        if not self.image_paths or self.current_index < 0 or self.current_index >= len(self.image_paths):
            return

        image_path = self.image_paths[self.current_index]

        try:
            ext = os.path.splitext(image_path)[1].lower()

            if ext == '.exr':
                self.message_label.setText("EXR Preview Not Available")
                self.image_stack.setCurrentWidget(self.message_label)
            else:
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    self.image_view.setPixmap(pixmap)
                    self.image_stack.setCurrentWidget(self.image_view)
                else:
                    self.message_label.setText("Failed to load image")
                    self.image_stack.setCurrentWidget(self.message_label)

        except Exception as e:
            self.message_label.setText(f"Error: {e}")
            self.image_stack.setCurrentWidget(self.message_label)

        self._update_info()
        self._position_nav_buttons()

    def _update_info(self):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        self.filename_label.setText(filename)
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.image_paths)}")
        self.info_bar.setVisible(self._show_info)

    def _next_image(self):
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._load_current_image()

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()

    def _on_zoom_changed(self, level):
        self.image_view.setZoomLevel(level)

    def _on_image_zoom_changed(self, level):
        self.zoom_combo.blockSignals(True)
        if level in ZoomableImageWidget.ZOOM_LEVELS:
            self.zoom_combo.setCurrentText(level)
        self.zoom_combo.blockSignals(False)

    def _copy_prompt(self):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.service import get_image_metadata
            metadata = get_image_metadata(output_dir, filename)
            if metadata and metadata.get('prompt'):
                clipboard = QApplication.clipboard()
                clipboard.setText(metadata['prompt'])
                self.filename_label.setText(f"{filename} - Prompt copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No prompt available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            print(f"Error copying prompt: {e}")

    def _copy_settings(self):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.service import get_image_metadata
            metadata = get_image_metadata(output_dir, filename)
            if metadata:
                self.copy_settings_requested.emit(metadata)
                self.filename_label.setText(f"{filename} - Settings copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No settings available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            print(f"Error copying settings: {e}")

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_D):
            self._next_image()
        elif key in (Qt.Key_Left, Qt.Key_A):
            self._prev_image()
        elif key in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
        elif key == Qt.Key_Home:
            self.current_index = 0
            self._load_current_image()
        elif key == Qt.Key_End:
            self.current_index = len(self.image_paths) - 1
            self._load_current_image()
        elif key == Qt.Key_Space:
            self._show_info = not self._show_info
            self._update_info()
        elif key == Qt.Key_C:
            self._copy_prompt()
        elif key == Qt.Key_S:
            self._copy_settings()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            click_x = event.pos().x()
            margin = 100
            if margin < click_x < self.width() - margin:
                pass
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.close()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def _show_context_menu(self, pos):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        menu = QMenu(self)

        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(lambda: self._open_folder(image_path))

        menu.addSeparator()

        copy_settings_action = menu.addAction("Copy Settings (S)")
        copy_settings_action.triggered.connect(self._copy_settings)

        copy_prompt_action = menu.addAction("Copy Prompt (C)")
        copy_prompt_action.triggered.connect(self._copy_prompt)

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path(image_path))

        menu.exec_(self.image_view.mapToGlobal(pos))

    def _open_folder(self, image_path):
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{image_path}"')
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _copy_path(self, image_path):
        clipboard = QApplication.clipboard()
        clipboard.setText(image_path)
        self.filename_label.setText(f"{os.path.basename(image_path)} - Path copied!")
        QTimer.singleShot(1500, self._update_info)
