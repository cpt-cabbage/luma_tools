"""
Universal 3D Model Thumbnail Service for Luma Tools.

Generates and caches thumbnails from 3D models (GLB, FBX, OBJ, USD, etc.).
Uses a subprocess to avoid OpenGL context conflicts with Qt.
Designed for async loading with caching for performance.
"""

import os
import hashlib
import subprocess
import sys
from typing import Optional, Dict

from PySide2.QtGui import QPixmap

# ============================================================================
# CONFIGURATION
# ============================================================================

# Cache settings
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".luma_tools", "thumbnails")
THUMBNAIL_SIZE = 150  # Square thumbnails for gallery

# Path to the renderer script
RENDERER_SCRIPT = os.path.join(os.path.dirname(__file__), "model_thumbnail_renderer.py")

# Python executable - use the venv's Python explicitly (sys.executable may point to AYON's Python)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_VENV_PYTHON = os.path.join(_SCRIPT_DIR, "venv", "Scripts", "python.exe") if sys.platform == 'win32' else os.path.join(_SCRIPT_DIR, "venv", "bin", "python")
PYTHON_EXE = _VENV_PYTHON if os.path.exists(_VENV_PYTHON) else sys.executable

# Supported extensions
SUPPORTED_EXTENSIONS = {
    '.glb', '.gltf',  # glTF
    '.fbx',           # Autodesk FBX
    '.obj',           # Wavefront OBJ
    '.usd', '.usda', '.usdc', '.usdz',  # USD
    '.dae',           # Collada
    '.3ds',           # 3D Studio Max
    '.stl',           # STL
    '.ply',           # PLY
}

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================================
# MODEL THUMBNAIL SERVICE
# ============================================================================

class ModelThumbnailService:
    """
    Generates and caches thumbnails from 3D models.

    Uses a subprocess to render thumbnails, avoiding OpenGL conflicts with Qt.
    Results are cached as PNG files using MD5 hash of file path.

    Usage:
        service = get_model_thumbnail_service()

        # Synchronous (cached only)
        pixmap = service.get_cached_thumbnail(model_path)

        # Generate new thumbnail (runs subprocess)
        pixmap = service.generate_thumbnail_sync(model_path)
    """

    def __init__(self):
        self._cache: Dict[str, QPixmap] = {}  # In-memory cache
        self._pending: Dict[str, bool] = {}   # Tracks pending generations

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

    def generate_thumbnail_sync(self, model_path: str) -> Optional[QPixmap]:
        """
        Generate a thumbnail from a 3D model file using subprocess.

        This method runs synchronously but the actual rendering happens
        in a separate process to avoid OpenGL conflicts.

        Args:
            model_path: Path to the 3D model file

        Returns:
            QPixmap of the thumbnail, or None if generation failed
        """
        if not os.path.exists(model_path):
            print(f"Model file not found: {model_path}")
            return None

        # Check renderer script exists
        if not os.path.exists(RENDERER_SCRIPT):
            print(f"Renderer script not found: {RENDERER_SCRIPT}")
            return None

        cache_path = self.get_cache_path(model_path)

        try:
            # Determine creation flags based on platform
            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            # Create clean environment for subprocess to avoid conflicts with parent's PYTHONPATH
            # (e.g., AYON sets PYTHONPATH which can cause typing_extensions conflicts)
            clean_env = os.environ.copy()
            clean_env.pop('PYTHONPATH', None)
            clean_env.pop('PYTHONHOME', None)

            # Run the renderer in a subprocess
            result = subprocess.run(
                [PYTHON_EXE, RENDERER_SCRIPT, model_path, cache_path, str(THUMBNAIL_SIZE)],
                capture_output=True,
                text=True,
                timeout=60,  # 60 second timeout for complex models
                creationflags=creation_flags,
                env=clean_env
            )

            if result.returncode != 0:
                print(f"Model thumbnail renderer failed: {result.stderr}")
                return None

            # Load the generated thumbnail
            if os.path.exists(cache_path):
                pixmap = QPixmap(cache_path)
                if not pixmap.isNull():
                    self._cache[model_path] = pixmap
                    return pixmap

        except subprocess.TimeoutExpired:
            print(f"Model thumbnail generation timed out for: {model_path}")
        except Exception as e:
            print(f"Model thumbnail generation error: {e}")

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


