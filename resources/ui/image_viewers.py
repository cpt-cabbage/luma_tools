"""
Image viewer widgets for the gallery.

Contains embedded and fullscreen viewers with support for images, 3D models, and videos.
"""
import os
import logging
from PySide6.QtCore import Qt, QTimer, Signal, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QMenu, QComboBox, QApplication, QSlider
)
from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap

from workers import Worker
from dialog_helpers import get_active_window

logger = logging.getLogger(__name__)


class ZoomableImageWidget(QtWidgets.QGraphicsView):
    """A widget that displays an image with support for zooming and panning."""
    double_clicked = Signal()
    zoom_changed = Signal(str)
    ZOOM_LEVELS = ["Fit", "100%", "50%", "25%", "10%"]
    MIN_ZOOM = 0.10  # Minimum zoom level (10%)
    MAX_ZOOM = 10.0  # Maximum zoom level (1000%)

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

        # Check zoom limits before applying
        current_scale = self.transform().m11()
        new_scale = current_scale * zoom_factor

        if new_scale < self.MIN_ZOOM:
            zoom_factor = self.MIN_ZOOM / current_scale
        elif new_scale > self.MAX_ZOOM:
            zoom_factor = self.MAX_ZOOM / current_scale

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

    def resizeEvent(self, event):
        """Re-fit image when resized if in Fit mode."""
        super().resizeEvent(event)
        if self._current_zoom == "Fit" and self._pixmap_item.pixmap() and not self._pixmap_item.pixmap().isNull():
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)


class EmbeddedImageViewer(QWidget):
    """
    Embedded image viewer with keyboard navigation for use within the gallery tab.

    Controls:
    - Left/Right arrows or A/D: Navigate between images
    - Escape or Backspace: Close viewer and return to gallery
    - Home/End: Jump to first/last image
    - C: Copy prompt to clipboard (if available)
    - S: Apply settings to ComfyUI tab (if available)
    - Delete: Delete current image
    """
    closed = Signal()
    view_fullscreen = Signal(str, int)
    copy_settings_requested = Signal(dict)
    image_deleted = Signal(str)  # Emitted when an image is deleted (path)
    image_viewed = Signal(str)  # Emitted when navigating to an image (path)
    like_toggled = Signal(str, bool)  # Emitted when like status is toggled (path, is_liked)

    def __init__(self, image_paths, start_index=0, output_dir=None, parent=None):
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.current_index = start_index
        self.output_dir = output_dir
        self._favorites_manager = None

        self._setup_ui()
        self._load_current_image()
        self.setFocusPolicy(Qt.StrongFocus)

    def set_favorites_manager(self, manager):
        """Set the favorites manager for like functionality."""
        self._favorites_manager = manager
        self._update_like_button()

    def _setup_ui(self):
        """Set up the embedded viewer UI."""
        self.setStyleSheet("background-color: #1a1a1a;")

        # Set size policy to expand and fill available space
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Main layout - single container fills everything
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main container for content and overlays
        self.image_container = QWidget()
        self.image_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.image_container, stretch=1)

        # Content layout inside container
        content_layout = QHBoxLayout(self.image_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.left_btn = QPushButton("<")
        self.left_btn.setFixedWidth(50)
        self.left_btn.setStyleSheet("""
            QPushButton { background-color: rgba(0, 0, 0, 0.3); color: white; border: none; font-size: 24px; }
            QPushButton:hover { background-color: rgba(74, 158, 255, 0.5); }
            QPushButton:disabled { color: #333333; }
        """)
        self.left_btn.setCursor(Qt.PointingHandCursor)
        self.left_btn.clicked.connect(self._prev_image)
        content_layout.addWidget(self.left_btn)

        self.image_stack = QtWidgets.QStackedWidget()
        content_layout.addWidget(self.image_stack, stretch=1)

        # 1. Zoomable Image View
        self.image_view = ZoomableImageWidget()
        self.image_view.setFocusPolicy(Qt.NoFocus)  # Prevent stealing focus from parent
        self.image_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_view.customContextMenuRequested.connect(self._show_context_menu)
        self.image_view.zoom_changed.connect(self._on_image_zoom_changed)
        self.image_stack.addWidget(self.image_view)

        # 2. 3D Model Viewer (Three.js) - Lazy initialization
        self._has_glb_viewer = None
        self.glb_viewer = None
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
            logger.warning(f"Video player not available: {e}")
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
        content_layout.addWidget(self.right_btn)

        # Top bar - overlay widget (child of image_container, not in layout)
        self.top_bar = QWidget(self.image_container)
        self.top_bar.setStyleSheet("background-color: transparent;")
        self.top_bar.setFixedHeight(75)

        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 10, 10, 10)

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

        # Bottom info bar - overlay widget (child of image_container, not in layout)
        self.info_bar = QWidget(self.image_container)
        self.info_bar.setStyleSheet("background-color: transparent;")
        self.info_bar.setFixedHeight(120)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(1, 10, 10, 75)

        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        info_layout.addWidget(self.filename_label)

        # Like button
        self.like_btn = QPushButton("♡")
        self.like_btn.setFixedSize(32, 32)
        self.like_btn.setToolTip("Like (L)")
        self.like_btn.setCursor(Qt.PointingHandCursor)
        self.like_btn.clicked.connect(self._toggle_like)
        self._update_like_button_style(False)
        info_layout.addWidget(self.like_btn)

        # 3D Model controls (hidden by default)
        # Shading Mode dropdown
        self.shading_btn = QPushButton("Textured")
        self.shading_btn.setFixedHeight(10)
        self.shading_btn.setStyleSheet("""
            QPushButton { background-color: #4a9eff; color: white; border: none; border-radius: 3px; padding: 0 10px; font-size: 11px; }
            QPushButton:hover { background-color: #5aa9ff; }
        """)
        self.shading_btn.clicked.connect(self._show_shading_menu)
        self.shading_btn.hide()
        info_layout.addWidget(self.shading_btn)

        # Lighting Mode dropdown
        self.lighting_btn = QPushButton("Studio")
        self.lighting_btn.setFixedHeight(10)
        self.lighting_btn.setStyleSheet("""
            QPushButton { background-color: #6b7280; color: white; border: none; border-radius: 3px; padding: 0 10px; font-size: 11px; }
            QPushButton:hover { background-color: #7c8596; }
        """)
        self.lighting_btn.clicked.connect(self._show_lighting_menu)
        self.lighting_btn.hide()
        info_layout.addWidget(self.lighting_btn)

        # Light strength label
        self.light_label = QLabel("Light:")
        self.light_label.setStyleSheet("color: #888888; font-size: 11px;")
        self.light_label.hide()
        info_layout.addWidget(self.light_label)

        # Light strength slider
        self.light_slider = QSlider(Qt.Horizontal)
        self.light_slider.setMinimum(10)  # 0.1x
        self.light_slider.setMaximum(300)  # 3.0x
        self.light_slider.setValue(100)  # 1.0x default
        self.light_slider.setFixedWidth(100)
        self.light_slider.setFixedHeight(20)
        self.light_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333333;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #4a9eff;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #5aa9ff;
            }
        """)
        self.light_slider.valueChanged.connect(self._on_light_strength_changed)
        self.light_slider.hide()
        info_layout.addWidget(self.light_slider)

        # Light strength value label
        self.light_value_label = QLabel("1.0x")
        self.light_value_label.setFixedWidth(35)
        self.light_value_label.setStyleSheet("color: #888888; font-size: 11px;")
        self.light_value_label.hide()
        info_layout.addWidget(self.light_value_label)

        # Publish to AYON button
        self.publish_to_ayon_btn = QPushButton("Publish to AYON")
        self.publish_to_ayon_btn.setFixedHeight(10)
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
            logger.warning(f"Could not initialize AYON button: {e}")
            self.publish_to_ayon_btn.setEnabled(False)
            self.publish_to_ayon_btn.setToolTip("AYON is not available")

        info_layout.addWidget(self.publish_to_ayon_btn)

        # Delete button
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setFixedHeight(10)
        self.delete_btn.setStyleSheet("""
            QPushButton { background-color: #dc2626; color: white; border: none; border-radius: 3px; padding: 0 12px; font-size: 11px; }
            QPushButton:hover { background-color: #ef4444; }
        """)
        self.delete_btn.setToolTip("Delete current file (Del)")
        self.delete_btn.clicked.connect(self._delete_current_image)
        info_layout.addWidget(self.delete_btn)

        self._current_3d_path = None
        self._saved_camera_state = None
        self._current_shading_mode = "textured"
        self._current_lighting_mode = "studio"
        self._current_hdri_path = None
        self._current_light_strength = 1.0

        info_layout.addStretch()

        help_label = QLabel("Navigate | Esc Back | C Prompt | Del Delete")
        help_label.setStyleSheet("color: #888888; font-size: 10px;")
        info_layout.addWidget(help_label)

        # Position and raise overlay bars immediately
        # They'll be repositioned in resizeEvent when actual size is known
        self.top_bar.move(0, 0)
        self.info_bar.move(0, 0)
        self.top_bar.raise_()
        self.info_bar.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()
        # Delay positioning to ensure layout is complete
        QTimer.singleShot(0, self._position_overlays)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlays()

    def _position_overlays(self):
        """Position top_bar and info_bar as overlays on image_container."""
        if not hasattr(self, 'image_container'):
            return

        w = self.image_container.width()
        h = self.image_container.height()

        if w == 0 or h == 0:
            return  # Widget not yet sized

        # Lower the content stack first (helps with QWebEngineView z-order)
        if hasattr(self, 'image_stack'):
            self.image_stack.lower()

        # Top bar at top of image_container
        if hasattr(self, 'top_bar'):
            top_height = 40
            self.top_bar.setGeometry(0, 0, w, top_height)
            self.top_bar.raise_()
            self.top_bar.show()

        # Info bar at bottom of image_container
        if hasattr(self, 'info_bar'):
            bar_height = 75
            self.info_bar.setGeometry(0, h - bar_height, w, bar_height)
            self.info_bar.raise_()
            self.info_bar.show()

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
        """Initialize the Three.js 3D viewer widget."""
        # Add python directory to path if needed
        import sys
        import os
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python_dir = os.path.join(os.path.dirname(current_dir), 'python')
        if python_dir not in sys.path:
            sys.path.insert(0, python_dir)

        try:
            from geo.threejs_viewer import ThreeJSViewerWidget, is_threejs_viewer_available, get_prewarm_viewer
            if is_threejs_viewer_available():
                # The prewarm viewer was initialized in main window layout before window.show()
                # to warm up the Chromium GPU thread. We do NOT reparent it (causes rendering issues).
                # Instead, create a fresh viewer - it won't flash because the GPU is already warm.
                # Just consume the prewarm reference to mark it as used.
                _ = get_prewarm_viewer()  # Consume prewarm (stays in main window, keeps GPU warm)

                # Create fresh viewer - GPU thread is already initialized, no flash expected
                self.glb_viewer = ThreeJSViewerWidget()
                logger.info("Created Three.js 3D viewer (GPU pre-warmed)")
                self.glb_viewer.loadError.connect(self._on_3d_load_error)
                self.glb_viewer.modelLoaded.connect(self._on_3d_model_loaded)
                self.image_stack.addWidget(self.glb_viewer)
                self._has_glb_viewer = True
                self._glb_viewer_initialized = True
                if callback:
                    callback(True)
                return
            else:
                logger.warning("Three.js viewer not available - PySide6 WebEngine may be missing")
        except Exception as e:
            logger.error(f"Three.js viewer failed: {e}", exc_info=True)

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
                self.shading_btn.show()
                self.lighting_btn.show()
                self.light_label.show()
                self.light_slider.show()
                self.light_value_label.show()
                self._current_3d_path = media_path

                # Restore saved preferences from settings
                try:
                    from core.settings_manager import get_setting
                    self._current_shading_mode = get_setting("viewer_3d_shading_mode")
                    self._current_lighting_mode = get_setting("viewer_3d_lighting_mode")
                    self._current_hdri_path = get_setting("viewer_3d_hdri_name")
                    self._current_light_strength = get_setting("viewer_3d_light_strength") or 1.0
                    self.light_slider.setValue(int(self._current_light_strength * 100))
                    self.light_value_label.setText(f"{self._current_light_strength:.1f}x")
                except Exception:
                    pass  # Use defaults if settings unavailable

                # Update button labels
                self.shading_btn.setText(self._current_shading_mode.title())
                label_map = {"headlight": "Headlight", "studio": "Studio", "hdri": "HDRI"}
                self.lighting_btn.setText(label_map.get(self._current_lighting_mode, "Studio"))

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
                self.shading_btn.hide()
                self.lighting_btn.hide()
                self.light_label.hide()
                self.light_slider.hide()
                self.light_value_label.hide()
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
                self.shading_btn.hide()
                self.lighting_btn.hide()
                self.light_label.hide()
                self.light_slider.hide()
                self.light_value_label.hide()
                self._current_3d_path = None
                self.message_label.setText("EXR Preview Not Available")
                self.image_stack.setCurrentWidget(self.message_label)

            else:
                self.shading_btn.hide()
                self.lighting_btn.hide()
                self.light_label.hide()
                self.light_slider.hide()
                self.light_value_label.hide()
                self._current_3d_path = None
                pixmap = QPixmap(media_path)
                if not pixmap.isNull():
                    self.image_view.setPixmap(pixmap)
                    self.image_stack.setCurrentWidget(self.image_view)
                    self.setFocus()  # Ensure keyboard navigation works
                else:
                    self.message_label.setText("Failed to load image")
                    self.image_stack.setCurrentWidget(self.message_label)

        except Exception as e:
            self.message_label.setText(f"Error: {e}")
            self.image_stack.setCurrentWidget(self.message_label)

        self._update_info()
        self._update_like_button()

    def _load_3d_model(self, media_path):
        """Load a 3D model into the Three.js viewer."""
        if not self.glb_viewer:
            self.message_label.setText("3D viewer not available")
            self.image_stack.setCurrentWidget(self.message_label)
            return

        # Show loading message while model loads
        self.message_label.setText("Loading 3D model...")
        self.image_stack.setCurrentWidget(self.message_label)

        # Set camera distance from user settings before loading
        try:
            from core.settings_manager import get_setting
            zoom_distance = get_setting("viewer_3d_zoom_distance")
            self.glb_viewer.set_camera_distance(zoom_distance)
        except Exception:
            pass  # Use default if settings unavailable

        # Three.js viewer loads files directly via WebGL
        # Switch to viewer only after model is loaded (via modelLoaded signal)
        self.glb_viewer.load_file(media_path)

    def _on_3d_model_loaded(self, path):
        """Handle successful 3D model load - switch to the viewer."""
        self.image_stack.setCurrentWidget(self.glb_viewer)
        self.glb_viewer.setFocus()

        # Apply saved lighting/shading preferences
        if self.glb_viewer:
            try:
                from geo.threejs_viewer import ShadingMode, LightingMode

                # Apply shading mode
                if self._current_shading_mode:
                    mode_enum = ShadingMode(self._current_shading_mode)
                    self.glb_viewer.set_shading_mode(mode_enum)

                # Apply lighting mode
                if self._current_lighting_mode:
                    mode_enum = LightingMode(self._current_lighting_mode)
                    self.glb_viewer.set_lighting_mode(mode_enum)

                    # If HDRI mode and we have a saved HDRI, load it
                    if self._current_lighting_mode == "hdri" and self._current_hdri_path:
                        # Find the full path from settings
                        from core.settings_manager import get_hdri_list
                        hdri_list = get_hdri_list()
                        for hdri in hdri_list:
                            if hdri["name"] == self._current_hdri_path or hdri["path"].endswith(self._current_hdri_path):
                                self.glb_viewer.load_hdri(hdri["path"])
                                break

                # Apply light strength
                if self._current_light_strength != 1.0:
                    self.glb_viewer.set_light_strength(self._current_light_strength)

            except Exception as e:
                logger.error(f"Error applying viewer preferences: {e}")

    def _on_3d_load_error(self, error_msg):
        """Handle 3D model loading error from Three.js viewer."""
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
            self.image_viewed.emit(self.image_paths[self.current_index])

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()
            self.image_viewed.emit(self.image_paths[self.current_index])

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

    def _show_shading_menu(self):
        """Show shading mode selection menu."""
        menu = QMenu(self)
        modes = [("Shaded", "shaded"), ("Textured", "textured"), ("Wireframe", "wireframe")]

        for label, mode in modes:
            action = menu.addAction(label)
            action.setData(mode)
            if mode == self._current_shading_mode:
                action.setCheckable(True)
                action.setChecked(True)

        action = menu.exec_(self.shading_btn.mapToGlobal(
            self.shading_btn.rect().bottomLeft()))

        if action and action.data():
            self._set_shading_mode(action.data())

    def _show_lighting_menu(self):
        """Show lighting mode selection menu."""
        menu = QMenu(self)

        # Basic lighting modes
        modes = [("Headlight", "headlight"), ("Studio (3-Point)", "studio")]
        for label, mode in modes:
            action = menu.addAction(label)
            action.setData(("mode", mode))
            if mode == self._current_lighting_mode:
                action.setCheckable(True)
                action.setChecked(True)

        # HDRI submenu (only if HDRIs are configured)
        try:
            from core.settings_manager import get_hdri_list
            hdri_list = get_hdri_list()
            if hdri_list:
                hdri_menu = menu.addMenu("HDRI")
                for hdri in hdri_list:
                    action = hdri_menu.addAction(hdri["name"])
                    action.setData(("hdri", hdri["path"]))
                    if (self._current_lighting_mode == "hdri" and
                        self._current_hdri_path == hdri["path"]):
                        action.setCheckable(True)
                        action.setChecked(True)
        except Exception as e:
            logger.error(f"Error loading HDRI list: {e}")

        action = menu.exec_(self.lighting_btn.mapToGlobal(
            self.lighting_btn.rect().bottomLeft()))

        if action and action.data():
            data_type, value = action.data()
            if data_type == "mode":
                self._set_lighting_mode(value)
            elif data_type == "hdri":
                self._set_lighting_mode("hdri")
                self._load_hdri(value)

    def _set_shading_mode(self, mode):
        """Set shading mode on the viewer."""
        self._current_shading_mode = mode
        self.shading_btn.setText(mode.title())

        if self.glb_viewer:
            try:
                from geo.threejs_viewer import ShadingMode
                mode_enum = ShadingMode(mode)
                self.glb_viewer.set_shading_mode(mode_enum)
            except Exception as e:
                logger.error(f"Error setting shading mode: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            set_setting("viewer_3d_shading_mode", mode, verbose=False)
        except Exception:
            pass

    def _set_lighting_mode(self, mode):
        """Set lighting mode on the viewer."""
        self._current_lighting_mode = mode
        label_map = {"headlight": "Headlight", "studio": "Studio", "hdri": "HDRI"}
        self.lighting_btn.setText(label_map.get(mode, mode.title()))

        if self.glb_viewer:
            try:
                from geo.threejs_viewer import LightingMode
                mode_enum = LightingMode(mode)
                self.glb_viewer.set_lighting_mode(mode_enum)
            except Exception as e:
                logger.error(f"Error setting lighting mode: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            set_setting("viewer_3d_lighting_mode", mode, verbose=False)
        except Exception:
            pass

    def _load_hdri(self, hdri_path):
        """Load an HDRI environment map."""
        self._current_hdri_path = hdri_path

        if self.glb_viewer:
            try:
                self.glb_viewer.load_hdri(hdri_path)
            except Exception as e:
                logger.error(f"Error loading HDRI: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            import os
            set_setting("viewer_3d_hdri_name", os.path.basename(hdri_path), verbose=False)
        except Exception:
            pass

    def _on_light_strength_changed(self, value):
        """Handle light strength slider changes."""
        strength = value / 100.0
        self._current_light_strength = strength
        self.light_value_label.setText(f"{strength:.1f}x")

        if self.glb_viewer:
            try:
                self.glb_viewer.set_light_strength(strength)
            except Exception as e:
                logger.error(f"Error setting light strength: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            set_setting("viewer_3d_light_strength", strength, verbose=False)
        except Exception:
            pass

    def _copy_prompt(self):
        """Copy prompt for current image to clipboard."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.metadata import get_item_metadata
            metadata = get_item_metadata(output_dir, filename)
            if metadata and metadata.get('prompt'):
                clipboard = QApplication.clipboard()
                clipboard.setText(metadata['prompt'], mode=clipboard.Mode.Clipboard)
                self.filename_label.setText(f"{filename} - Prompt copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No prompt available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Error copying prompt: {e}")

    def _copy_settings(self):
        """Apply all settings for current image to the ComfyUI tab."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.metadata import get_item_metadata
            metadata = get_item_metadata(output_dir, filename)
            if metadata:
                self.copy_settings_requested.emit(metadata)
                self.filename_label.setText(f"{filename} - Settings copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No settings available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Error applying settings: {e}")

    def _publish_to_ayon(self):
        """Publish this image to AYON."""
        parent_window = get_active_window()

        try:
            from comfyui.ayon_publisher import publish_comfyui_asset_to_ayon
            image_path = self.image_paths[self.current_index]
            success = publish_comfyui_asset_to_ayon(
                file_path=image_path,
                parent_widget=parent_window,
                output_dir=self.output_dir
            )
            if success:
                logger.info(f"Successfully published image to AYON: {image_path}")
        except Exception as e:
            logger.error(f"Failed to publish image to AYON: {e}", exc_info=True)
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
        elif key == Qt.Key_Delete:
            self._delete_current_image()
        elif key == Qt.Key_L:
            self._toggle_like()
        else:
            super().keyPressEvent(event)

    def _toggle_like(self):
        """Toggle like status for current image."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        is_liked = self._favorites_manager.toggle_like(path)
        self._update_like_button_style(is_liked)
        self.like_toggled.emit(path, is_liked)

    def _update_like_button(self):
        """Update like button based on current image's like status."""
        if not self.image_paths or not self._favorites_manager:
            return
        path = self.image_paths[self.current_index]
        is_liked = self._favorites_manager.is_liked(path)
        self._update_like_button_style(is_liked)

    def _update_like_button_style(self, is_liked):
        """Update like button appearance based on liked state."""
        if is_liked:
            self.like_btn.setText("♥")
            self.like_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(239, 68, 68, 0.9);
                    color: white;
                    border: none;
                    border-radius: 16px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: rgba(239, 68, 68, 1.0);
                }
            """)
        else:
            self.like_btn.setText("♡")
            self.like_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(60, 60, 60, 0.8);
                    color: rgba(255, 255, 255, 0.7);
                    border: none;
                    border-radius: 16px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: rgba(239, 68, 68, 0.7);
                    color: white;
                }
            """)

    def _delete_current_image(self):
        """Delete the current image file after confirmation."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Delete File",
            f"Are you sure you want to delete:\n{filename}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                os.remove(image_path)
                deleted_path = image_path
                self.image_paths.pop(self.current_index)

                if not self.image_paths:
                    self.image_deleted.emit(deleted_path)
                    self._on_back()
                    return

                if self.current_index >= len(self.image_paths):
                    self.current_index = len(self.image_paths) - 1

                self._load_current_image()
                self.image_deleted.emit(deleted_path)
                self.filename_label.setText(f"Deleted: {filename}")
                QTimer.singleShot(1500, self._update_info)

            except Exception as e:
                QMessageBox.warning(self, "Delete Error", f"Failed to delete file:\n{str(e)}")

    def _show_context_menu(self, pos):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        menu = QMenu(self)

        open_folder_action = menu.addAction("Open Containing Folder")
        open_folder_action.triggered.connect(lambda: self._open_folder(image_path))

        menu.addSeparator()

        apply_settings_action = menu.addAction("Apply Settings (S)")
        apply_settings_action.triggered.connect(self._copy_settings)

        copy_prompt_action = menu.addAction("Copy Prompt (C)")
        copy_prompt_action.triggered.connect(self._copy_prompt)

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path(image_path))

        menu.addSeparator()

        delete_action = menu.addAction("Delete (Del)")
        delete_action.triggered.connect(self._delete_current_image)

        menu.exec_(self.image_view.mapToGlobal(pos))

    def _open_folder(self, image_path):
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{image_path}"')
        except Exception as e:
            logger.error(f"Error opening folder: {e}")

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
    - S: Apply settings to ComfyUI tab (if available)
    - Delete: Delete current file
    """
    closed = Signal()
    copy_settings_requested = Signal(dict)
    image_deleted = Signal(str)  # Emitted when a file is deleted (path)
    image_viewed = Signal(str)  # Emitted when navigating to an image (path)

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
        self.image_view.zoom_changed.connect(self._on_image_zoom_changed)
        self.image_stack.addWidget(self.image_view)

        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("background-color: #1a1a1a; color: #888888; font-size: 16px;")
        self.image_stack.addWidget(self.message_label)

        # Info bar - overlays on content
        self.info_bar = QWidget(self)  # Child of self for overlay
        self.info_bar.setStyleSheet("QWidget { background-color: transparent; }")
        self.info_bar.setFixedHeight(60)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(20, 15, 20, 15)

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

        self.help_label = QLabel("Navigate | Esc Close | Space Info | C Prompt | Del Delete")
        self.help_label.setStyleSheet("color: #888888; font-size: 10px; margin-left: 20px;")
        info_layout.addWidget(self.help_label)

        self.info_bar.raise_()

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
        self._position_overlays()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlays()

    def _position_overlays(self):
        """Position info bar and nav buttons as overlays."""
        # Lower the content first
        if hasattr(self, 'image_stack'):
            self.image_stack.lower()

        # Position info_bar at bottom
        bar_height = self.info_bar.height()
        self.info_bar.setGeometry(0, self.height() - bar_height, self.width(), bar_height)
        self.info_bar.raise_()
        self.info_bar.show()

        # Position nav buttons centered vertically (accounting for info bar)
        btn_width = 60
        btn_height = 100
        margin = 20
        center_y = (self.height() - bar_height - btn_height) // 2

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
            self.image_viewed.emit(self.image_paths[self.current_index])

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()
            self.image_viewed.emit(self.image_paths[self.current_index])

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
            from comfyui.metadata import get_item_metadata
            metadata = get_item_metadata(output_dir, filename)
            if metadata and metadata.get('prompt'):
                clipboard = QApplication.clipboard()
                clipboard.setText(metadata['prompt'], mode=clipboard.Mode.Clipboard)
                self.filename_label.setText(f"{filename} - Prompt copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No prompt available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Error copying prompt: {e}")

    def _copy_settings(self):
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)
        output_dir = self.output_dir or os.path.dirname(image_path)

        try:
            from comfyui.metadata import get_item_metadata
            metadata = get_item_metadata(output_dir, filename)
            if metadata:
                self.copy_settings_requested.emit(metadata)
                self.filename_label.setText(f"{filename} - Settings copied!")
                QTimer.singleShot(1500, self._update_info)
            else:
                self.filename_label.setText(f"{filename} - No settings available")
                QTimer.singleShot(1500, self._update_info)
        except Exception as e:
            logger.error(f"Error applying settings: {e}")

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
        elif key == Qt.Key_Delete:
            self._delete_current_image()
        else:
            super().keyPressEvent(event)

    def _delete_current_image(self):
        """Delete the current file after confirmation."""
        if not self.image_paths:
            return

        image_path = self.image_paths[self.current_index]
        filename = os.path.basename(image_path)

        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Delete File",
            f"Are you sure you want to delete:\n{filename}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                os.remove(image_path)
                deleted_path = image_path
                self.image_paths.pop(self.current_index)

                if not self.image_paths:
                    self.image_deleted.emit(deleted_path)
                    self.close()
                    return

                if self.current_index >= len(self.image_paths):
                    self.current_index = len(self.image_paths) - 1

                self._load_current_image()
                self.image_deleted.emit(deleted_path)
                self.filename_label.setText(f"Deleted: {filename}")
                QTimer.singleShot(1500, self._update_info)

            except Exception as e:
                QMessageBox.warning(self, "Delete Error", f"Failed to delete file:\n{str(e)}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            click_x = event.pos().x()
            margin = 100
            if margin < click_x < self.width() - margin:
                pass
        super().mousePressEvent(event)

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

        apply_settings_action = menu.addAction("Apply Settings (S)")
        apply_settings_action.triggered.connect(self._copy_settings)

        copy_prompt_action = menu.addAction("Copy Prompt (C)")
        copy_prompt_action.triggered.connect(self._copy_prompt)

        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_path(image_path))

        menu.addSeparator()

        delete_action = menu.addAction("Delete (Del)")
        delete_action.triggered.connect(self._delete_current_image)

        menu.exec_(self.image_view.mapToGlobal(pos))

    def _open_folder(self, image_path):
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{image_path}"')
        except Exception as e:
            logger.error(f"Error opening folder: {e}")

    def _copy_path(self, image_path):
        clipboard = QApplication.clipboard()
        clipboard.setText(image_path)
        self.filename_label.setText(f"{os.path.basename(image_path)} - Path copied!")
        QTimer.singleShot(1500, self._update_info)
