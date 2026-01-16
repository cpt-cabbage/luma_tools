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
from typing import Optional, Dict
from enum import Enum

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


# Global pre-warmed viewer instance (initialized during splash)
_prewarm_viewer = None


def set_prewarm_viewer(viewer):
    """Store a pre-warmed viewer instance for later reuse."""
    global _prewarm_viewer
    _prewarm_viewer = viewer


def get_prewarm_viewer():
    """Get and consume the pre-warmed viewer instance (one-time use)."""
    global _prewarm_viewer
    viewer = _prewarm_viewer
    _prewarm_viewer = None
    return viewer


class ThreeJSBridge(QObject):
    """
    Bridge for Python <-> JavaScript communication via QWebChannel.

    Signals:
        viewerReady: Emitted when Three.js viewer is fully initialized
        modelLoaded: Emitted when model loads successfully (path)
        loadError: Emitted when model fails to load (error message)
        animationInfo: Emitted with animation list after model loads
    """

    viewerReady = Signal()
    modelLoaded = Signal(str)
    loadError = Signal(str)
    animationInfo = Signal(list)

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
        print("Three.js viewer JavaScript ready")
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
            js_code = f"loadModel('{file_url}');"
            self._web_view.page().runJavaScript(js_code)

    def set_view_mode(self, mode: str):
        """Send view mode command to JavaScript."""
        if self._web_view:
            js_code = f"setViewMode('{mode}');"
            self._web_view.page().runJavaScript(js_code)

    def play_animation(self, name: str = None):
        """Send play animation command to JavaScript."""
        if self._web_view:
            if name:
                js_code = f"playAnimation('{name}');"
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

        # Enable WebGL and local file access
        settings = self._web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
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

        # For prewarm: force native window creation now (during splash)
        # This ensures all GPU/rendering initialization happens while splash covers screen
        if prewarm:
            self._web_view.winId()  # Forces native window handle creation

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
            print(f"Warning: Three.js viewer not found at {viewer_path}")
            self._viewer_ready = True  # Mark as ready to prevent hanging
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
            print("Three.js viewer HTML loaded, waiting for JS initialization...")
        else:
            print("Three.js viewer page failed to load")
            self.loadError.emit("Failed to load viewer page")

    def _on_viewer_ready(self):
        """Called when JavaScript viewer is fully initialized (via QWebChannel callback)."""
        print("Three.js viewer fully ready")
        self._viewer_ready = True

        # Show the web view now that it's ready (if not a prewarm widget)
        if not self._is_prewarm:
            self._web_view.show()

        # Load any pending model now that viewer is ready
        if self._pending_model_path:
            print(f"Loading pending model: {self._pending_model_path}")
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
            # Queue for loading after viewer is ready
            print(f"Queuing model load (viewer not ready): {file_path}")
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


class ThreeJSViewerDialog(QWidget):
    """
    Standalone dialog window for viewing 3D models with Three.js.

    Used when opening a 3D model from context menu or thumbnail click.
    """

    def __init__(self, model_path: str, parent=None):
        super().__init__(parent)

        if not WEBENGINE_AVAILABLE:
            raise ImportError("PySide6-WebEngine is required for ThreeJSViewerDialog")

        self.setWindowTitle(f"3D Viewer - {os.path.basename(model_path)}")
        self.setWindowFlags(Qt.Window)
        self.resize(800, 600)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create viewer widget
        self._viewer = ThreeJSViewerWidget(self)
        layout.addWidget(self._viewer)

        # Load the model
        self._viewer.load_file(model_path)

    def exec(self):
        """Show dialog modally (compatibility with QDialog interface)."""
        self.show()
        self.raise_()
        self.activateWindow()


def is_threejs_viewer_available() -> bool:
    """Check if Three.js viewer is available."""
    return WEBENGINE_AVAILABLE


# For backwards compatibility
def is_viewer_available() -> bool:
    """Check if any viewer is available."""
    return WEBENGINE_AVAILABLE
