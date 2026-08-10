"""
Three.js-based 3D Model Viewer for Luma Tools.

Uses QWebEngineView to embed a Three.js scene for 3D model viewing.
This provides better FBX support and eliminates OpenGL context issues.

Supports:
- GLB/glTF (via GLTFLoader)
- FBX (via FBXLoader)
- OBJ (via OBJLoader)
"""

import os
import json
import logging
from typing import Optional, Dict
from enum import Enum

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt, Signal, Slot, QObject, QUrl, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebChannel import QWebChannel
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False


class ViewMode(Enum):
    """Viewer display modes."""
    TEXTURED = "textured"
    SKELETON = "skeleton"
    WIREFRAME = "wireframe"


class LightingMode(Enum):
    """Viewer lighting modes."""
    HEADLIGHT = "headlight"
    STUDIO = "studio"
    HDRI = "hdri"


class ShadingMode(Enum):
    """Viewer shading modes."""
    SHADED = "shaded"
    TEXTURED = "textured"
    WIREFRAME = "wireframe"


# Global pre-warmed viewer instance (initialized during splash)


class ThreeJSBridge(QObject):
    """
    Bridge for Python <-> JavaScript communication via QWebChannel.

    Signals:
        viewerReady: Emitted when Three.js viewer is fully initialized
        modelLoaded: Emitted when model loads successfully (path)
        loadError: Emitted when model fails to load (error message)
        animationInfo: Emitted with animation list after model loads
        screenshotCaptured: Emitted with base64 screenshot data
    """

    viewerReady = Signal()
    modelLoaded = Signal(str)
    loadError = Signal(str)
    animationInfo = Signal(list)
    screenshotCaptured = Signal(str)  # base64 data URL

    def __init__(self, parent=None):
        super().__init__(parent)
        self._web_view = None
        self._viewer_ready = False

    def set_web_view(self, web_view):
        """Set the web view for executing JavaScript."""
        self._web_view = web_view

    def is_viewer_ready(self) -> bool:
        """Check if the JavaScript viewer is fully initialized."""
        return self._viewer_ready

    @Slot()
    def onViewerReady(self):
        """Called from JavaScript when Three.js viewer is fully initialized."""
        logger.info("Three.js viewer JavaScript ready")
        self._viewer_ready = True
        self.viewerReady.emit()

    @Slot(str)
    def onModelLoaded(self, path: str):
        """Called from JavaScript when model loads successfully."""
        self.modelLoaded.emit(path)

    @Slot(str)
    def onLoadError(self, error: str):
        """Called from JavaScript when model fails to load."""
        self.loadError.emit(error)

    @Slot(str)
    def onAnimationsFound(self, animations_json: str):
        """Called from JavaScript with list of animations."""
        try:
            animations = json.loads(animations_json)
            self.animationInfo.emit(animations)
        except json.JSONDecodeError:
            pass

    def load_model(self, file_path: str):
        """Send load model command to JavaScript."""
        if self._web_view:
            # Convert to file:// URL with forward slashes
            file_url = file_path.replace('\\', '/')
            if not file_url.startswith('file://'):
                file_url = f'file:///{file_url}'
            # json.dumps escapes quotes/backslashes — paths with apostrophes
            # (e.g. "O'Brien") would otherwise produce broken JS that
            # runJavaScript silently rejects.
            js_code = f"loadModel({json.dumps(file_url)});"
            self._web_view.page().runJavaScript(js_code)

    def set_view_mode(self, mode: str):
        """Send view mode command to JavaScript."""
        if self._web_view:
            js_code = f"setViewMode({json.dumps(mode)});"
            self._web_view.page().runJavaScript(js_code)

    def play_animation(self, name: str = None):
        """Send play animation command to JavaScript."""
        if self._web_view:
            if name:
                js_code = f"playAnimation({json.dumps(name)});"
            else:
                js_code = "playAnimation();"
            self._web_view.page().runJavaScript(js_code)

    def stop_animation(self):
        """Send stop animation command to JavaScript."""
        if self._web_view:
            self._web_view.page().runJavaScript("stopAnimation();")

    def set_animation_time(self, time_normalized: float):
        """Set animation time (0-1 normalized)."""
        if self._web_view:
            js_code = f"setAnimationTime({time_normalized});"
            self._web_view.page().runJavaScript(js_code)

    def set_camera_distance(self, distance: float):
        """Set the default camera distance for model loading."""
        if self._web_view:
            js_code = f"setCameraDistance({distance});"
            self._web_view.page().runJavaScript(js_code)

    def set_lighting_mode(self, mode: str):
        """Send lighting mode command to JavaScript."""
        if self._web_view:
            js_code = f"setLightingMode({json.dumps(mode)});"
            self._web_view.page().runJavaScript(js_code)

    def set_shading_mode(self, mode: str):
        """Send shading mode command to JavaScript."""
        if self._web_view:
            js_code = f"setShadingMode({json.dumps(mode)});"
            self._web_view.page().runJavaScript(js_code)

    def load_hdri(self, path: str):
        """Send load HDRI command to JavaScript."""
        if self._web_view:
            file_url = path.replace('\\', '/')
            if not file_url.startswith('file://'):
                file_url = f'file:///{file_url}'
            js_code = f"loadHdri({json.dumps(file_url)});"
            self._web_view.page().runJavaScript(js_code)

    def set_light_strength(self, strength: float):
        """Send light strength command to JavaScript."""
        if self._web_view:
            js_code = f"setLightStrength({strength});"
            self._web_view.page().runJavaScript(js_code)

    def capture_screenshot(self, size: int = 150, callback=None):
        """Capture a screenshot of the current view.

        Args:
            size: Size of the square thumbnail (default 150)
            callback: Optional callback function to receive the base64 data
        """
        if self._web_view:
            js_code = f"captureScreenshot({size});"

            def handle_result(result):
                if result:
                    self.screenshotCaptured.emit(result)
                    if callback:
                        callback(result)

            self._web_view.page().runJavaScript(js_code, handle_result)


class ThreeJSViewerWidget(QWidget):
    """
    Three.js-based 3D model viewer widget.

    Drop-in replacement for ModelViewerWidget using WebGL via QWebEngineView.

    Signals:
        modelLoaded: Emitted when model loads successfully
        loadError: Emitted when model fails to load
    """

    modelLoaded = Signal(str)
    loadError = Signal(str)

    def __init__(self, parent=None, prewarm=False):
        super().__init__(parent)

        if not WEBENGINE_AVAILABLE:
            raise ImportError("PySide6-WebEngine is required for ThreeJSViewerWidget")

        self._is_prewarm = prewarm

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create web view - always start hidden
        self._web_view = QWebEngineView()
        self._web_view.setStyleSheet("background: #1e1e1e;")
        self._web_view.hide()
        layout.addWidget(self._web_view)

        # Enable WebGL and local file access. We deliberately do NOT enable
        # LocalContentCanAccessRemoteUrls — Three.js loads from bundled local
        # files only, and turning this on would let user-supplied glTF files
        # fetch arbitrary remote textures.
        settings = self._web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)

        # Create bridge and channel
        self._bridge = ThreeJSBridge(self)
        self._bridge.set_web_view(self._web_view)
        self._bridge.modelLoaded.connect(self.modelLoaded)
        self._bridge.loadError.connect(self.loadError)
        self._bridge.viewerReady.connect(self._on_viewer_ready)

        # Setup web channel
        self._channel = QWebChannel()
        self._channel.registerObject('bridge', self._bridge)
        self._web_view.page().setWebChannel(self._channel)

        # Track viewer state - wait for JS callback, not just page load
        self._viewer_ready = False
        self._pending_model_path: Optional[str] = None
        self._web_view.loadFinished.connect(self._on_page_loaded)

        # Current state
        self._current_model_path: Optional[str] = None
        self._view_mode = ViewMode.TEXTURED

        # Load the viewer HTML
        self._load_viewer()

        # Set minimum size
        self.setMinimumSize(400, 300)

        self._cleaned_up = False

        # For prewarm: force native window creation now (during splash)
        # This ensures all GPU/rendering initialization happens while splash covers screen
        if prewarm:
            self._web_view.winId()  # Forces native window handle creation

    def cleanup(self):
        """Explicitly clean up QWebEngineView before application exit.

        Must be called before sys.exit() to prevent Chromium subprocess crash
        (access violation 0xC0000005) during Qt's C++ destructor chain.
        """
        if self._cleaned_up:
            return
        self._cleaned_up = True
        try:
            if hasattr(self, '_web_view') and self._web_view is not None:
                self._web_view.setUrl(QUrl("about:blank"))
                page = self._web_view.page()
                if page:
                    page.deleteLater()
                self._web_view.deleteLater()
                self._web_view = None
        except RuntimeError:
            pass  # Widget already deleted by Qt

    def _load_viewer(self):
        """Load the Three.js viewer HTML."""
        # Find the viewer.html file relative to this module
        module_dir = os.path.dirname(os.path.abspath(__file__))
        resources_dir = os.path.join(os.path.dirname(os.path.dirname(module_dir)), 'resources', 'threejs')
        viewer_path = os.path.join(resources_dir, 'viewer.html')

        if os.path.exists(viewer_path):
            url = QUrl.fromLocalFile(viewer_path)
            self._web_view.setUrl(url)
        else:
            logger.warning(f"Three.js viewer not found at {viewer_path}")
            self._viewer_ready = True  # Mark as ready to prevent hanging
            self._bridge._viewer_ready = True  # Keep bridge in sync (H35)
            # Show error message in widget
            self._web_view.setHtml(f"""
                <html>
                <body style="background: #1e1e1e; color: #fff; font-family: sans-serif;
                             display: flex; align-items: center; justify-content: center; height: 100vh;">
                    <div style="text-align: center;">
                        <h2>Three.js Viewer Not Found</h2>
                        <p>Expected at: {viewer_path}</p>
                    </div>
                </body>
                </html>
            """)

    def _on_page_loaded(self, ok: bool):
        """Called when the HTML page finishes loading."""
        if ok:
            logger.info("Three.js viewer HTML loaded, waiting for JS initialization...")
            return
        # Page-load failure is terminal — flip both ready flags so subsequent
        # load_file() calls don't sit forever in _pending_model_path, and emit
        # exactly one error for any path the caller already queued up.
        logger.error("Three.js viewer page failed to load")
        self._viewer_ready = True
        self._bridge._viewer_ready = True
        pending = self._pending_model_path
        self._pending_model_path = None
        if pending:
            self.loadError.emit(f"Viewer page failed to load (pending: {pending})")
        else:
            self.loadError.emit("Failed to load viewer page")

    def _on_viewer_ready(self):
        """Called when JavaScript viewer is fully initialized (via QWebChannel callback)."""
        logger.info("Three.js viewer fully ready")
        self._viewer_ready = True

        # Show the web view now that it's ready (if not a prewarm widget)
        if not self._is_prewarm:
            self._web_view.show()

        # Load any pending model now that viewer is ready
        if self._pending_model_path:
            logger.info(f"Loading pending model: {self._pending_model_path}")
            self._do_load_model(self._pending_model_path)
            self._pending_model_path = None

    def _do_load_model(self, file_path: str):
        """Actually load the model (called after page is ready)."""
        self._current_model_path = file_path
        self._bridge.load_model(file_path)

    def set_model_data(self, model_data):
        """
        Load model from ModelData object.

        This matches the interface of ModelViewerWidget for drop-in replacement.

        Args:
            model_data: ModelData object with 'path' attribute, or None to clear
        """
        if model_data is None:
            self._current_model_path = None
            return

        # Extract path from model_data
        if hasattr(model_data, 'path'):
            file_path = model_data.path
        elif isinstance(model_data, str):
            file_path = model_data
        else:
            self.loadError.emit("Invalid model data")
            return

        self.load_file(file_path)

    def load_file(self, file_path: str):
        """
        Load a 3D model file directly by path.

        Args:
            file_path: Path to the 3D model file
        """
        # Don't show web view here - wait until viewer is fully ready
        # to prevent window flashing during WebEngine initialization.
        # The web view will be shown in _on_viewer_ready().

        if self._viewer_ready:
            self._do_load_model(file_path)
        else:
            # Queue for loading after viewer is ready. If a previous request
            # is still pending, surface its failure so any UI spinner gets
            # cleared before we replace the slot.
            if self._pending_model_path:
                logger.warning(
                    f"Discarding queued model load for {self._pending_model_path}"
                    f" — replaced by {file_path}"
                )
                self.loadError.emit(
                    f"Replaced before viewer was ready: {self._pending_model_path}"
                )
            logger.info(f"Queuing model load (viewer not ready): {file_path}")
            self._pending_model_path = file_path

    def set_view_mode(self, mode: ViewMode):
        """
        Set the view mode (textured, skeleton, wireframe).

        Args:
            mode: ViewMode enum value
        """
        self._view_mode = mode
        if self._viewer_ready:
            self._bridge.set_view_mode(mode.value)

    def set_bone_transforms(self, transforms: Dict[str, any]):
        """
        Set bone transforms for animation.

        Note: Three.js handles animation internally via AnimationMixer,
        so this is mainly for compatibility with the old interface.
        """
        # Three.js handles animation internally
        pass

    def play_animation(self, name: str = None):
        """Play an animation by name, or the first animation if no name given."""
        if self._viewer_ready:
            self._bridge.play_animation(name)

    def stop_animation(self):
        """Stop the current animation."""
        if self._viewer_ready:
            self._bridge.stop_animation()

    def set_camera_distance(self, distance: float):
        """
        Set the default camera distance for model loading.

        Args:
            distance: Camera distance (lower = closer zoom)
        """
        if self._viewer_ready:
            self._bridge.set_camera_distance(distance)

    def set_animation_time(self, time_normalized: float):
        """
        Set the animation time.

        Args:
            time_normalized: Time value from 0.0 to 1.0
        """
        if self._viewer_ready:
            self._bridge.set_animation_time(time_normalized)

    def get_current_path(self) -> Optional[str]:
        """Get the currently loaded model path."""
        return self._current_model_path

    def capture_screenshot(self, size: int = 150, callback=None):
        """Capture a screenshot of the current model.

        Args:
            size: Size of the square thumbnail (default 150)
            callback: Optional callback function to receive the base64 data URL
        """
        if self._viewer_ready:
            self._bridge.capture_screenshot(size, callback)

    def set_lighting_mode(self, mode: LightingMode):
        """
        Set the lighting mode (headlight, studio, hdri).

        Args:
            mode: LightingMode enum value
        """
        if self._viewer_ready:
            self._bridge.set_lighting_mode(mode.value)

    def set_shading_mode(self, mode: ShadingMode):
        """
        Set the shading mode (shaded, textured, wireframe).

        Args:
            mode: ShadingMode enum value
        """
        if self._viewer_ready:
            self._bridge.set_shading_mode(mode.value)

    def load_hdri(self, path: str):
        """
        Load an HDRI environment map.

        Args:
            path: Path to HDRI file (.hdr or .exr)
        """
        if self._viewer_ready:
            self._bridge.load_hdri(path)

    def set_light_strength(self, strength: float):
        """
        Set the light intensity strength multiplier.

        Args:
            strength: Light strength from 0.1 to 3.0 (1.0 = default)
        """
        if self._viewer_ready:
            self._bridge.set_light_strength(strength)


class ThreeJSViewerDialog(QWidget):
    """
    Standalone dialog window for viewing 3D models with Three.js.

    Used when opening a 3D model from context menu or thumbnail click.
    Includes lighting and shading controls matching the embedded viewer.
    """

    def __init__(self, model_path: str, parent=None):
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QLabel, QMenu, QSlider

        super().__init__(parent)

        if not WEBENGINE_AVAILABLE:
            raise ImportError("PySide6-WebEngine is required for ThreeJSViewerDialog")

        self.setWindowTitle(f"3D Viewer - {os.path.basename(model_path)}")
        self.setWindowFlags(Qt.Window)
        self.resize(800, 600)

        # State for controls
        self._current_shading_mode = "textured"
        self._current_lighting_mode = "studio"
        self._current_hdri_path = None
        self._current_light_strength = 1.0

        # Load saved preferences (individual calls so one failure doesn't skip the rest)
        try:
            from core.settings_manager import safe_get_setting, get_hdri_list
            self._current_shading_mode = safe_get_setting("viewer_3d_shading_mode", "textured") or "textured"
            self._current_lighting_mode = safe_get_setting("viewer_3d_lighting_mode", "studio") or "studio"
            self._current_light_strength = safe_get_setting("viewer_3d_light_strength", 1.0) or 1.0
            hdri_name = safe_get_setting("viewer_3d_hdri_name", "")
            if hdri_name:
                hdri_list = get_hdri_list()
                for hdri in hdri_list:
                    if os.path.basename(hdri["path"]) == hdri_name:
                        self._current_hdri_path = hdri["path"]
                        break
        except Exception:
            pass

        # Create layout - viewer takes full space
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create viewer widget first (will be the main content)
        self._viewer = ThreeJSViewerWidget(self)
        layout.addWidget(self._viewer)

        # Info bar with controls - overlays on content
        self._info_bar = QWidget(self)  # Child of self for overlay
        self._info_bar.setStyleSheet("background-color: rgba(30, 30, 30, 200); border-top: 1px solid #444444;")
        self._info_bar.setFixedHeight(35)
        info_layout = QHBoxLayout(self._info_bar)
        info_layout.setContentsMargins(10, 5, 10, 5)
        info_layout.setSpacing(10)

        # Filename label
        filename_label = QLabel(os.path.basename(model_path))
        filename_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        info_layout.addWidget(filename_label)

        # Shading Mode dropdown
        self._shading_btn = QPushButton(self._current_shading_mode.title())
        self._shading_btn.setFixedHeight(25)
        self._shading_btn.setStyleSheet("""
            QPushButton { background-color: #4a9eff; color: white; border: none; border-radius: 3px; padding: 0 10px; font-size: 11px; }
            QPushButton:hover { background-color: #5aa9ff; }
        """)
        self._shading_btn.clicked.connect(self._show_shading_menu)
        info_layout.addWidget(self._shading_btn)

        # Lighting Mode dropdown
        label_map = {"headlight": "Headlight", "studio": "Studio", "hdri": "HDRI"}
        self._lighting_btn = QPushButton(label_map.get(self._current_lighting_mode, "Studio"))
        self._lighting_btn.setFixedHeight(25)
        self._lighting_btn.setStyleSheet("""
            QPushButton { background-color: #6b7280; color: white; border: none; border-radius: 3px; padding: 0 10px; font-size: 11px; }
            QPushButton:hover { background-color: #7c8596; }
        """)
        self._lighting_btn.clicked.connect(self._show_lighting_menu)
        info_layout.addWidget(self._lighting_btn)

        # Light strength label
        light_label = QLabel("Light:")
        light_label.setStyleSheet("color: #888888; font-size: 11px;")
        info_layout.addWidget(light_label)

        # Light strength slider
        self._light_slider = QSlider(Qt.Horizontal)
        self._light_slider.setMinimum(10)  # 0.1x
        self._light_slider.setMaximum(300)  # 3.0x
        self._light_slider.setValue(int(self._current_light_strength * 100))
        self._light_slider.setFixedWidth(100)
        self._light_slider.setFixedHeight(20)
        self._light_slider.setStyleSheet("""
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
        self._light_slider.valueChanged.connect(self._on_light_strength_changed)
        info_layout.addWidget(self._light_slider)

        # Light strength value label
        self._light_value_label = QLabel(f"{self._current_light_strength:.1f}x")
        self._light_value_label.setFixedWidth(35)
        self._light_value_label.setStyleSheet("color: #888888; font-size: 11px;")
        info_layout.addWidget(self._light_value_label)

        info_layout.addStretch()

        # Help text
        help_label = QLabel("Scroll: Zoom | Drag: Rotate | Shift+Drag: Pan")
        help_label.setStyleSheet("color: #888888; font-size: 10px;")
        info_layout.addWidget(help_label)

        self._info_bar.raise_()

        # Connect to viewer ready signal to apply saved preferences
        self._viewer._bridge.viewerReady.connect(self._on_viewer_ready)

        # Load the model
        self._viewer.load_file(model_path)

    def _on_viewer_ready(self):
        """Apply saved preferences once viewer is ready."""
        # Apply saved shading mode
        if self._current_shading_mode != "textured":
            self._viewer.set_shading_mode(ShadingMode(self._current_shading_mode))

        # Apply saved lighting mode
        if self._current_lighting_mode != "studio":
            self._viewer.set_lighting_mode(LightingMode(self._current_lighting_mode))
            if self._current_lighting_mode == "hdri" and self._current_hdri_path:
                self._viewer.load_hdri(self._current_hdri_path)

        # Apply saved light strength
        if self._current_light_strength != 1.0:
            self._viewer.set_light_strength(self._current_light_strength)

    def _show_shading_menu(self):
        """Show shading mode selection menu."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        modes = [("Shaded", "shaded"), ("Textured", "textured"), ("Wireframe", "wireframe")]

        for label, mode in modes:
            action = menu.addAction(label)
            action.setData(mode)
            if mode == self._current_shading_mode:
                action.setCheckable(True)
                action.setChecked(True)

        action = menu.exec_(self._shading_btn.mapToGlobal(
            self._shading_btn.rect().bottomLeft()))

        if action and action.data():
            self._set_shading_mode(action.data())

    def _show_lighting_menu(self):
        """Show lighting mode selection menu."""
        from PySide6.QtWidgets import QMenu

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

        action = menu.exec_(self._lighting_btn.mapToGlobal(
            self._lighting_btn.rect().bottomLeft()))

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
        self._shading_btn.setText(mode.title())

        try:
            mode_enum = ShadingMode(mode)
            self._viewer.set_shading_mode(mode_enum)
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
        self._lighting_btn.setText(label_map.get(mode, mode.title()))

        try:
            mode_enum = LightingMode(mode)
            self._viewer.set_lighting_mode(mode_enum)
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

        try:
            self._viewer.load_hdri(hdri_path)
        except Exception as e:
            logger.error(f"Error loading HDRI: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            set_setting("viewer_3d_hdri_name", os.path.basename(hdri_path), verbose=False)
        except Exception:
            pass

    def _on_light_strength_changed(self, value):
        """Handle light strength slider changes."""
        strength = value / 100.0
        self._current_light_strength = strength
        self._light_value_label.setText(f"{strength:.1f}x")

        try:
            self._viewer.set_light_strength(strength)
        except Exception as e:
            logger.error(f"Error setting light strength: {e}")

        # Persist preference
        try:
            from core.settings_manager import set_setting
            set_setting("viewer_3d_light_strength", strength, verbose=False)
        except Exception:
            pass

    def showEvent(self, event):
        """Handle show event - position info bar."""
        super().showEvent(event)
        self._position_info_bar()

    def resizeEvent(self, event):
        """Handle resize event - reposition info bar."""
        super().resizeEvent(event)
        self._position_info_bar()

    def _position_info_bar(self):
        """Position info_bar at bottom of window as overlay."""
        # Lower the viewer first (helps with QWebEngineView z-order)
        if hasattr(self, '_viewer'):
            self._viewer.lower()

        if hasattr(self, '_info_bar'):
            bar_height = self._info_bar.height()
            self._info_bar.setGeometry(
                0,
                self.height() - bar_height,
                self.width(),
                bar_height
            )
            self._info_bar.raise_()
            self._info_bar.show()

    def exec(self):
        """Show the viewer window (non-modal).

        ThreeJSViewerDialog is a QWidget, not a QDialog — it cannot run a
        local event loop without breaking the QtWebEngine's own one. Use
        ``show_window()`` for clarity in new code; ``exec()`` is kept for
        backwards compat with call sites that mistook it for QDialog.exec.
        """
        self.show_window()

    def show_window(self):
        """Show the viewer as a non-modal top-level window."""
        self.show()
        self.raise_()
        self.activateWindow()


def is_threejs_viewer_available() -> bool:
    """Check if Three.js viewer is available."""
    return WEBENGINE_AVAILABLE
