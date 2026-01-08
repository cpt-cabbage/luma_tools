"""
GLB Thumbnail Service for Luma Tools.

Generates and caches thumbnails from GLB/GLTF 3D models.
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
RENDERER_SCRIPT = os.path.join(os.path.dirname(__file__), "glb_thumbnail_renderer.py")

# Python executable - use the same venv as the main app
PYTHON_EXE = sys.executable

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================================
# GLB THUMBNAIL SERVICE
# ============================================================================

class GLBThumbnailService:
    """
    Generates and caches thumbnails from GLB/GLTF 3D models.

    Uses a subprocess to render thumbnails, avoiding OpenGL conflicts with Qt.
    Results are cached as PNG files using MD5 hash of file path.

    Usage:
        service = get_glb_thumbnail_service()

        # Synchronous (cached only)
        pixmap = service.get_cached_thumbnail(glb_path)

        # Generate new thumbnail (runs subprocess)
        pixmap = service.generate_thumbnail_sync(glb_path)
    """

    def __init__(self):
        self._cache: Dict[str, QPixmap] = {}  # In-memory cache
        self._pending: Dict[str, bool] = {}  # Tracks pending generations

    def get_cache_path(self, glb_path: str) -> str:
        """
        Get the cache file path for a GLB model.

        Args:
            glb_path: Path to the GLB/GLTF file

        Returns:
            Path to the cached thumbnail PNG
        """
        # Create hash of path for unique filename (prefix with 'glb_' to avoid collision)
        path_hash = hashlib.md5(glb_path.encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"glb_{path_hash}.png")

    def get_cached_thumbnail(self, glb_path: str) -> Optional[QPixmap]:
        """
        Get a cached thumbnail if available.

        Args:
            glb_path: Path to the GLB/GLTF file

        Returns:
            QPixmap if cached, None otherwise
        """
        # Check in-memory cache first
        if glb_path in self._cache:
            return self._cache[glb_path]

        # Check disk cache
        cache_path = self.get_cache_path(glb_path)
        if os.path.exists(cache_path):
            # Check if cache is still valid (GLB file hasn't been modified)
            if os.path.exists(glb_path):
                cache_mtime = os.path.getmtime(cache_path)
                glb_mtime = os.path.getmtime(glb_path)
                if cache_mtime < glb_mtime:
                    # Cache is stale, remove it
                    try:
                        os.remove(cache_path)
                    except:
                        pass
                    return None

            pixmap = QPixmap(cache_path)
            if not pixmap.isNull():
                self._cache[glb_path] = pixmap
                return pixmap

        return None

    def is_cached(self, glb_path: str) -> bool:
        """Check if a thumbnail is cached (memory or disk)."""
        if glb_path in self._cache:
            return True
        return os.path.exists(self.get_cache_path(glb_path))

    def is_pending(self, glb_path: str) -> bool:
        """Check if thumbnail generation is already pending for this path."""
        return self._pending.get(glb_path, False)

    def set_pending(self, glb_path: str, pending: bool = True):
        """Mark a path as pending generation."""
        self._pending[glb_path] = pending

    def generate_thumbnail_sync(self, glb_path: str) -> Optional[QPixmap]:
        """
        Generate a thumbnail from a GLB/GLTF file using subprocess.

        This method runs synchronously but the actual rendering happens
        in a separate process to avoid OpenGL conflicts.

        Args:
            glb_path: Path to the GLB/GLTF file

        Returns:
            QPixmap of the thumbnail, or None if generation failed
        """
        if not os.path.exists(glb_path):
            print(f"GLB file not found: {glb_path}")
            return None

        if not os.path.exists(RENDERER_SCRIPT):
            print(f"Renderer script not found: {RENDERER_SCRIPT}")
            return None

        cache_path = self.get_cache_path(glb_path)

        try:
            # Run the renderer in a subprocess
            result = subprocess.run(
                [PYTHON_EXE, RENDERER_SCRIPT, glb_path, cache_path, str(THUMBNAIL_SIZE)],
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            if result.returncode != 0:
                print(f"GLB thumbnail renderer failed: {result.stderr}")
                return None

            # Load the generated thumbnail
            if os.path.exists(cache_path):
                pixmap = QPixmap(cache_path)
                if not pixmap.isNull():
                    self._cache[glb_path] = pixmap
                    return pixmap

        except subprocess.TimeoutExpired:
            print(f"GLB thumbnail generation timed out for: {glb_path}")
        except Exception as e:
            print(f"GLB thumbnail generation error: {e}")

        return None

    def clear_cache(self, glb_path: str = None):
        """
        Clear thumbnail cache.

        Args:
            glb_path: If provided, only clear cache for this path.
                      If None, clear all GLB thumbnails.
        """
        if glb_path:
            # Clear specific entry
            if glb_path in self._cache:
                del self._cache[glb_path]
            if glb_path in self._pending:
                del self._pending[glb_path]
            cache_path = self.get_cache_path(glb_path)
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                except:
                    pass
        else:
            # Clear all GLB thumbnails (those starting with 'glb_')
            self._cache.clear()
            self._pending.clear()
            for cache_file in os.listdir(CACHE_DIR):
                if cache_file.startswith("glb_"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, cache_file))
                    except:
                        pass


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_glb_thumbnail_service_instance: Optional[GLBThumbnailService] = None


def get_glb_thumbnail_service() -> GLBThumbnailService:
    """Get the global GLB thumbnail service instance."""
    global _glb_thumbnail_service_instance
    if _glb_thumbnail_service_instance is None:
        _glb_thumbnail_service_instance = GLBThumbnailService()
    return _glb_thumbnail_service_instance
