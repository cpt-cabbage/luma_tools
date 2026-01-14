"""
Thumbnail Service for Luma Tools.

Generates and caches thumbnails from EXR sequences using OIIO.
Designed for async loading with caching for performance.
"""

import os
import hashlib
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Callable, Dict, Tuple
from datetime import datetime

from PySide6.QtCore import QObject, Signal, QSize
from PySide6.QtGui import QPixmap, QImage

import core.config as config

# ============================================================================
# CONFIGURATION
# ============================================================================

# Cache settings
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".luma_tools", "thumbnails")
THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 90  # 16:9 aspect ratio
THUMBNAIL_QUALITY = 85

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================================
# THUMBNAIL SERVICE
# ============================================================================

class ThumbnailService:
    """
    Generates and caches thumbnails from EXR sequences.

    Uses OIIO to extract a frame from the sequence, apply OCIO color transform,
    and resize to thumbnail dimensions. Results are cached as PNG files.

    Usage:
        service = ThumbnailService()

        # Synchronous (cached only)
        pixmap = service.get_cached_thumbnail(render_path)

        # Async generation
        service.generate_thumbnail_async(render_path, callback)
    """

    def __init__(self):
        self._cache: Dict[str, QPixmap] = {}  # In-memory cache
        self._pending: Dict[str, bool] = {}  # Tracks pending generations

    def get_cache_path(self, render_path: str) -> str:
        """
        Get the cache file path for a render.

        Args:
            render_path: Path to the render directory or first frame

        Returns:
            Path to the cached thumbnail PNG
        """
        # Create hash of path for unique filename
        path_hash = hashlib.md5(render_path.encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"{path_hash}.png")

    def get_cached_thumbnail(self, render_path: str) -> Optional[QPixmap]:
        """
        Get a cached thumbnail if available.

        Args:
            render_path: Path to the render

        Returns:
            QPixmap if cached, None otherwise
        """
        # Check in-memory cache first
        if render_path in self._cache:
            return self._cache[render_path]

        # Check disk cache
        cache_path = self.get_cache_path(render_path)
        if os.path.exists(cache_path):
            pixmap = QPixmap(cache_path)
            if not pixmap.isNull():
                self._cache[render_path] = pixmap
                return pixmap

        return None

    def is_cached(self, render_path: str) -> bool:
        """Check if a thumbnail is cached (memory or disk)."""
        if render_path in self._cache:
            return True
        return os.path.exists(self.get_cache_path(render_path))

    def generate_thumbnail(
        self,
        render_path: str,
        frame_pattern: str = None,
        progress_callback: Callable[[int, str], None] = None
    ) -> Optional[QPixmap]:
        """
        Generate a thumbnail from an EXR sequence.

        Args:
            render_path: Path to the render directory
            frame_pattern: Optional specific frame pattern (e.g., "render.1001.exr")
            progress_callback: Optional callback for progress updates

        Returns:
            QPixmap of the thumbnail, or None if generation failed
        """
        if not config.OIIO_PATH:
            print("OIIO not available for thumbnail generation")
            return None

        # Find the source EXR file
        source_exr = self._find_source_frame(render_path, frame_pattern)
        if not source_exr:
            print(f"No EXR found for thumbnail: {render_path}")
            return None

        if progress_callback:
            progress_callback(10, "Found source frame...")

        # Generate thumbnail
        cache_path = self.get_cache_path(render_path)
        temp_png = None

        try:
            # Create temp file for output
            temp_fd, temp_png = tempfile.mkstemp(suffix=".png")
            os.close(temp_fd)

            if progress_callback:
                progress_callback(30, "Processing with OIIO...")

            # Build OIIO command
            cmd = self._build_oiio_command(source_exr, temp_png)

            # Run OIIO
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"OIIO thumbnail generation failed: {result.stderr}")
                return None

            if progress_callback:
                progress_callback(70, "Loading thumbnail...")

            # Load the generated thumbnail
            if os.path.exists(temp_png):
                pixmap = QPixmap(temp_png)
                if not pixmap.isNull():
                    # Save to cache
                    pixmap.save(cache_path, "PNG", THUMBNAIL_QUALITY)
                    self._cache[render_path] = pixmap

                    if progress_callback:
                        progress_callback(100, "Done")

                    return pixmap

        except subprocess.TimeoutExpired:
            print(f"Thumbnail generation timed out: {render_path}")
        except Exception as e:
            print(f"Thumbnail generation error: {e}")
        finally:
            # Clean up temp file
            if temp_png and os.path.exists(temp_png):
                try:
                    os.remove(temp_png)
                except:
                    pass

        return None

    def _find_source_frame(
        self,
        render_path: str,
        frame_pattern: str = None
    ) -> Optional[str]:
        """
        Find a suitable source frame for thumbnail generation.
        Prefers the middle frame of the sequence.

        Args:
            render_path: Path to render directory or frame
            frame_pattern: Optional specific frame pattern

        Returns:
            Path to the source EXR file
        """
        # If it's a file path, use it directly
        if os.path.isfile(render_path) and render_path.endswith(".exr"):
            return render_path

        # If frame_pattern provided, try to construct path
        if frame_pattern:
            potential_path = os.path.join(render_path, frame_pattern)
            if os.path.exists(potential_path):
                return potential_path

        # Find all EXR files in directory
        if os.path.isdir(render_path):
            exr_files = sorted([
                f for f in os.listdir(render_path)
                if f.endswith(".exr")
            ])

            if exr_files:
                # Use middle frame for most representative thumbnail
                middle_idx = len(exr_files) // 2
                return os.path.join(render_path, exr_files[middle_idx])

        return None

    def _build_oiio_command(
        self,
        source_exr: str,
        output_png: str
    ) -> list:
        """
        Build the OIIO command for thumbnail generation.

        Args:
            source_exr: Source EXR file path
            output_png: Output PNG file path

        Returns:
            Command list for subprocess
        """
        cmd = [config.OIIO_PATH]

        # Input file
        cmd.extend([source_exr])

        # Select only Beauty/RGB channels if available (avoid alpha issues)
        cmd.extend(["--ch", "R,G,B"])

        # Apply OCIO color transform if available
        ocio_config = config.get_ocio_config()
        if ocio_config:
            cmd.extend([
                "--colorconfig", ocio_config,
                "--colorconvert", config.AYON_COLORSPACE, "sRGB"
            ])

        # Resize to thumbnail dimensions
        cmd.extend(["--resize", f"{THUMBNAIL_WIDTH}x{THUMBNAIL_HEIGHT}"])

        # Clamp values to valid range
        cmd.extend(["--clamp:min=0", "--clamp:max=1"])

        # Output
        cmd.extend(["-o", output_png])

        return cmd

    def clear_cache(self, render_path: str = None):
        """
        Clear thumbnail cache.

        Args:
            render_path: If provided, only clear cache for this path.
                         If None, clear entire cache.
        """
        if render_path:
            # Clear specific entry
            if render_path in self._cache:
                del self._cache[render_path]
            cache_path = self.get_cache_path(render_path)
            if os.path.exists(cache_path):
                os.remove(cache_path)
        else:
            # Clear all
            self._cache.clear()
            for cache_file in os.listdir(CACHE_DIR):
                try:
                    os.remove(os.path.join(CACHE_DIR, cache_file))
                except:
                    pass

    def get_cache_size(self) -> Tuple[int, int]:
        """
        Get cache statistics.

        Returns:
            Tuple of (file_count, total_bytes)
        """
        file_count = 0
        total_bytes = 0

        for cache_file in os.listdir(CACHE_DIR):
            cache_path = os.path.join(CACHE_DIR, cache_file)
            if os.path.isfile(cache_path):
                file_count += 1
                total_bytes += os.path.getsize(cache_path)

        return file_count, total_bytes


# ============================================================================
# THUMBNAIL WORKER SIGNALS
# ============================================================================

class ThumbnailWorkerSignals(QObject):
    """Signals for async thumbnail generation."""
    finished = Signal(str, object)  # render_path, pixmap (or None)
    error = Signal(str, str)  # render_path, error_message
    progress = Signal(str, int, str)  # render_path, progress, message


# ============================================================================
# RENDER METADATA
# ============================================================================

class RenderMetadata:
    """
    Stores metadata about a render for display in UI.
    """

    def __init__(self, render_path: str):
        self.path = render_path
        self.name = os.path.basename(render_path)
        self.frame_count = 0
        self.frame_range = ""
        self.resolution = ""
        self.file_size = 0
        self.last_modified = None

        self._analyze()

    def _analyze(self):
        """Analyze the render directory to gather metadata."""
        if not os.path.exists(self.path):
            return

        # Find EXR files
        if os.path.isdir(self.path):
            exr_files = sorted([
                f for f in os.listdir(self.path)
                if f.endswith(".exr")
            ])

            if exr_files:
                self.frame_count = len(exr_files)

                # Extract frame numbers
                frames = []
                for f in exr_files:
                    # Try to extract frame number from filename
                    parts = os.path.splitext(f)[0].split(".")
                    for part in reversed(parts):
                        if part.isdigit():
                            frames.append(int(part))
                            break

                if frames:
                    self.frame_range = f"{min(frames)}-{max(frames)}"

                # Get total file size
                for f in exr_files:
                    file_path = os.path.join(self.path, f)
                    self.file_size += os.path.getsize(file_path)

                # Get last modified time
                last_exr = os.path.join(self.path, exr_files[-1])
                mtime = os.path.getmtime(last_exr)
                self.last_modified = datetime.fromtimestamp(mtime)

                # Try to get resolution using OIIO
                first_exr = os.path.join(self.path, exr_files[0])
                self._get_resolution(first_exr)

    def _get_resolution(self, exr_path: str):
        """Get resolution from EXR using OIIO."""
        if not config.OIIO_INFO_PATH:
            return

        try:
            result = subprocess.run(
                [config.OIIO_INFO_PATH, "-v", exr_path],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                # Parse output for resolution
                for line in result.stdout.split("\n"):
                    if "x" in line and "pixels" in line.lower():
                        # Format: "1920 x 1080 pixels"
                        parts = line.split()
                        for i, p in enumerate(parts):
                            if p == "x" and i > 0 and i < len(parts) - 1:
                                try:
                                    w = int(parts[i-1])
                                    h = int(parts[i+1])
                                    self.resolution = f"{w}x{h}"
                                    return
                                except ValueError:
                                    pass
        except:
            pass

    def format_file_size(self) -> str:
        """Format file size for display."""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        elif self.file_size < 1024 * 1024 * 1024:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.file_size / (1024 * 1024 * 1024):.2f} GB"

    def format_last_modified(self) -> str:
        """Format last modified time for display."""
        if not self.last_modified:
            return ""

        now = datetime.now()
        diff = now - self.last_modified

        if diff.days == 0:
            if diff.seconds < 3600:
                minutes = diff.seconds // 60
                return f"{minutes}m ago" if minutes > 0 else "Just now"
            else:
                hours = diff.seconds // 3600
                return f"{hours}h ago"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        else:
            return self.last_modified.strftime("%b %d")


# ============================================================================
# PLACEHOLDER THUMBNAIL
# ============================================================================

def create_placeholder_thumbnail(
    width: int = THUMBNAIL_WIDTH,
    height: int = THUMBNAIL_HEIGHT,
    color: str = "#3c414b"
) -> QPixmap:
    """
    Create a placeholder thumbnail pixmap.

    Args:
        width: Thumbnail width
        height: Thumbnail height
        color: Background color

    Returns:
        QPixmap placeholder
    """
    from PySide6.QtGui import QColor, QPainter, QBrush
    from PySide6.QtCore import Qt

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(color))

    # Draw a subtle film icon or pattern
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Draw grid pattern
    painter.setPen(QColor("#4a5160"))
    grid_size = 20
    for x in range(0, width, grid_size):
        painter.drawLine(x, 0, x, height)
    for y in range(0, height, grid_size):
        painter.drawLine(0, y, width, y)

    painter.end()

    return pixmap


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_thumbnail_service_instance: Optional[ThumbnailService] = None

def get_thumbnail_service() -> ThumbnailService:
    """Get the global thumbnail service instance."""
    global _thumbnail_service_instance
    if _thumbnail_service_instance is None:
        _thumbnail_service_instance = ThumbnailService()
    return _thumbnail_service_instance


# Backward compatibility alias
ThumbnailManager = ThumbnailService
