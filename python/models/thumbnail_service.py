"""
Universal 3D Model Thumbnail Service for Luma Tools.

Generates and caches thumbnails from 3D models (GLB, FBX, OBJ, etc.).
Uses the Three.js viewer for rendering, avoiding OpenGL context conflicts.
Designed for async loading with caching for performance.
"""

import os
import hashlib
import base64
from typing import Optional, Dict

from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QEventLoop, QTimer

# ============================================================================
# CONFIGURATION
# ============================================================================

# Cache settings
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".luma_tools", "thumbnails")
THUMBNAIL_SIZE = 150  # Square thumbnails for gallery

# Supported extensions (Three.js viewer supports these)
SUPPORTED_EXTENSIONS = {
    '.glb', '.gltf',  # glTF
    '.fbx',           # Autodesk FBX
    '.obj',           # Wavefront OBJ
}

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================================
# MODEL THUMBNAIL SERVICE
# ============================================================================

class ModelThumbnailService:
    """
    Generates and caches thumbnails from 3D models.

    Uses the Three.js viewer for rendering via QWebEngineView.
    Results are cached as PNG files using MD5 hash of file path.

    Usage:
        service = get_model_thumbnail_service()

        # Synchronous (cached only)
        pixmap = service.get_cached_thumbnail(model_path)

        # Generate new thumbnail (uses Three.js viewer)
        pixmap = service.generate_thumbnail_sync(model_path)
    """

    def __init__(self):
        self._cache: Dict[str, QPixmap] = {}  # In-memory cache
        self._pending: Dict[str, bool] = {}   # Tracks pending generations
        self._thumbnail_viewer = None         # Reusable hidden viewer

    def get_cache_path(self, model_path: str) -> str:
        """
        Get the cache file path for a 3D model.

        Args:
            model_path: Path to the 3D model file

        Returns:
            Path to the cached thumbnail PNG
        """
        # Create hash of path for unique filename (prefix with 'model_' to avoid collision)
        path_hash = hashlib.md5(model_path.encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"model_{path_hash}.png")

    def get_cached_thumbnail(self, model_path: str) -> Optional[QPixmap]:
        """
        Get a cached thumbnail if available.

        Args:
            model_path: Path to the 3D model file

        Returns:
            QPixmap if cached, None otherwise
        """
        # Check in-memory cache first
        if model_path in self._cache:
            return self._cache[model_path]

        # Check disk cache
        cache_path = self.get_cache_path(model_path)
        if os.path.exists(cache_path):
            # Check if cache is still valid (model file hasn't been modified)
            if os.path.exists(model_path):
                cache_mtime = os.path.getmtime(cache_path)
                model_mtime = os.path.getmtime(model_path)
                if cache_mtime < model_mtime:
                    # Cache is stale, remove it
                    try:
                        os.remove(cache_path)
                    except:
                        pass
                    return None

            pixmap = QPixmap(cache_path)
            if not pixmap.isNull():
                self._cache[model_path] = pixmap
                return pixmap

        return None

    def is_cached(self, model_path: str) -> bool:
        """Check if a thumbnail is cached (memory or disk)."""
        if model_path in self._cache:
            return True
        return os.path.exists(self.get_cache_path(model_path))

    def is_pending(self, model_path: str) -> bool:
        """Check if thumbnail generation is already pending for this path."""
        return self._pending.get(model_path, False)

    def set_pending(self, model_path: str, pending: bool = True):
        """Mark a path as pending generation."""
        self._pending[model_path] = pending

    def is_supported(self, model_path: str) -> bool:
        """Check if the file format is supported."""
        ext = os.path.splitext(model_path)[1].lower()
        return ext in SUPPORTED_EXTENSIONS

    def _get_or_create_viewer(self):
        """Get or create a hidden Three.js viewer for thumbnail generation."""
        if self._thumbnail_viewer is not None:
            return self._thumbnail_viewer

        try:
            from models.threejs_viewer import ThreeJSViewerWidget, WEBENGINE_AVAILABLE
            if not WEBENGINE_AVAILABLE:
                print("[ThumbnailService] WebEngine not available")
                return None

            # Create hidden viewer
            self._thumbnail_viewer = ThreeJSViewerWidget(prewarm=True)
            self._thumbnail_viewer.setFixedSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
            self._thumbnail_viewer.hide()

            return self._thumbnail_viewer
        except Exception as e:
            print(f"[ThumbnailService] Error creating viewer: {e}")
            return None

    def generate_thumbnail_sync(self, model_path: str) -> Optional[QPixmap]:
        """
        Generate a thumbnail from a 3D model file using Three.js viewer.

        This method blocks until the thumbnail is generated or timeout occurs.

        Args:
            model_path: Path to the 3D model file

        Returns:
            QPixmap of the thumbnail, or None if generation failed
        """
        if not os.path.exists(model_path):
            print(f"[ThumbnailService] Model file not found: {model_path}")
            return None

        if not self.is_supported(model_path):
            print(f"[ThumbnailService] Unsupported format: {model_path}")
            return None

        cache_path = self.get_cache_path(model_path)

        try:
            viewer = self._get_or_create_viewer()
            if viewer is None:
                print("[ThumbnailService] Could not create viewer")
                return None

            # Track state
            result = {'pixmap': None, 'loaded': False, 'captured': False}
            loop = QEventLoop()

            # Timeout after 30 seconds
            timeout_timer = QTimer()
            timeout_timer.setSingleShot(True)
            timeout_timer.timeout.connect(loop.quit)

            def on_model_loaded(path):
                result['loaded'] = True
                # Wait a bit for rendering to complete, then capture
                QTimer.singleShot(500, capture_screenshot)

            def on_load_error(error):
                print(f"[ThumbnailService] Load error: {error}")
                loop.quit()

            def capture_screenshot():
                viewer.capture_screenshot(THUMBNAIL_SIZE, on_screenshot_captured)

            def on_screenshot_captured(data_url):
                if data_url and data_url.startswith('data:image/png;base64,'):
                    # Extract base64 data and convert to pixmap
                    base64_data = data_url.split(',', 1)[1]
                    image_data = base64.b64decode(base64_data)

                    # Save to cache file
                    try:
                        with open(cache_path, 'wb') as f:
                            f.write(image_data)

                        # Load as pixmap
                        pixmap = QPixmap(cache_path)
                        if not pixmap.isNull():
                            result['pixmap'] = pixmap
                            self._cache[model_path] = pixmap
                            result['captured'] = True
                    except Exception as e:
                        print(f"[ThumbnailService] Error saving thumbnail: {e}")

                loop.quit()

            # Connect signals
            viewer.modelLoaded.connect(on_model_loaded)
            viewer.loadError.connect(on_load_error)

            # Wait for viewer to be ready
            if not viewer._viewer_ready:
                ready_loop = QEventLoop()
                ready_timer = QTimer()
                ready_timer.setSingleShot(True)
                ready_timer.timeout.connect(ready_loop.quit)

                def on_viewer_ready():
                    ready_loop.quit()

                viewer._bridge.viewerReady.connect(on_viewer_ready)
                ready_timer.start(10000)  # 10s timeout for viewer ready
                ready_loop.exec()
                viewer._bridge.viewerReady.disconnect(on_viewer_ready)

            if not viewer._viewer_ready:
                print("[ThumbnailService] Viewer failed to initialize")
                return None

            # Load the model
            viewer.load_file(model_path)

            # Start timeout and wait
            timeout_timer.start(30000)  # 30s timeout
            loop.exec()
            timeout_timer.stop()

            # Disconnect signals
            try:
                viewer.modelLoaded.disconnect(on_model_loaded)
                viewer.loadError.disconnect(on_load_error)
            except:
                pass

            return result['pixmap']

        except Exception as e:
            print(f"[ThumbnailService] Thumbnail generation error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def clear_cache(self, model_path: str = None):
        """
        Clear thumbnail cache.

        Args:
            model_path: If provided, only clear cache for this path.
                       If None, clear all model thumbnails.
        """
        if model_path:
            # Clear specific entry
            if model_path in self._cache:
                del self._cache[model_path]
            if model_path in self._pending:
                del self._pending[model_path]
            cache_path = self.get_cache_path(model_path)
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                except:
                    pass
        else:
            # Clear all model thumbnails (those starting with 'model_')
            self._cache.clear()
            self._pending.clear()
            for cache_file in os.listdir(CACHE_DIR):
                if cache_file.startswith("model_"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, cache_file))
                    except:
                        pass


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_model_thumbnail_service_instance: Optional[ModelThumbnailService] = None


def get_model_thumbnail_service() -> ModelThumbnailService:
    """Get the global model thumbnail service instance."""
    global _model_thumbnail_service_instance
    if _model_thumbnail_service_instance is None:
        _model_thumbnail_service_instance = ModelThumbnailService()
    return _model_thumbnail_service_instance
