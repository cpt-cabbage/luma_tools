"""
File scanner strategy pattern for luma_tools.

Provides abstract base class and concrete implementations for different
file type scanning operations. Following the strategy pattern allows
for consistent interfaces while handling type-specific logic.

Usage:
    from services.scanners import RenderScanner, HIPScanner, CompScanner

    # Use specific scanner
    scanner = RenderScanner()
    files = scanner.scan("/path/to/renders")

    # Chain with post-processing
    scanner = RenderScanner(recursive=True)
    filtered = scanner.scan_and_filter("/path", name_contains="beauty")
"""

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, List, Optional, Set

logger = logging.getLogger(__name__)


class FileScanner(ABC):
    """
    Abstract base class for file scanning strategies.

    Subclasses implement specific file type matching logic while
    inheriting common scanning functionality.

    Attributes:
        recursive: Whether to scan subdirectories (default: True)
        follow_symlinks: Whether to follow symbolic links (default: False)
    """

    def __init__(self, recursive: bool = True, follow_symlinks: bool = False):
        """
        Initialize scanner.

        Args:
            recursive: Whether to scan subdirectories
            follow_symlinks: Whether to follow symbolic links
        """
        self.recursive = recursive
        self.follow_symlinks = follow_symlinks

    @property
    @abstractmethod
    def extensions(self) -> Set[str]:
        """Set of file extensions this scanner matches (lowercase, with dot)."""
        pass

    @property
    def name(self) -> str:
        """Human-readable name for this scanner."""
        return self.__class__.__name__

    def matches(self, path: Path) -> bool:
        """
        Check if a file matches this scanner's criteria.

        Default implementation checks file extension. Override for
        more complex matching logic.

        Args:
            path: Path to check

        Returns:
            True if file matches, False otherwise
        """
        return path.suffix.lower() in self.extensions

    def scan(self, directory: str) -> List[Path]:
        """
        Scan directory and return matching files.

        Args:
            directory: Directory to scan

        Returns:
            List of matching file paths
        """
        if not directory or not os.path.isdir(directory):
            return []

        try:
            root = Path(directory)
            if self.recursive:
                files = root.rglob("*")
            else:
                files = root.glob("*")

            return [f for f in files if f.is_file() and self.matches(f)]

        except OSError as e:
            logger.error(f"[{self.name}] Error scanning {directory}: {e}")
            return []

    def scan_and_filter(
        self,
        directory: str,
        name_contains: Optional[str] = None,
        name_excludes: Optional[str] = None,
        predicate: Optional[Callable[[Path], bool]] = None
    ) -> List[Path]:
        """
        Scan with additional filtering.

        Args:
            directory: Directory to scan
            name_contains: Only include files with this substring in name
            name_excludes: Exclude files with this substring in name
            predicate: Custom filter function (receives Path, returns bool)

        Returns:
            List of filtered matching file paths
        """
        files = self.scan(directory)

        if name_contains:
            files = [f for f in files if name_contains.lower() in f.name.lower()]

        if name_excludes:
            files = [f for f in files if name_excludes.lower() not in f.name.lower()]

        if predicate:
            files = [f for f in files if predicate(f)]

        return files

    def count(self, directory: str) -> int:
        """
        Count matching files without loading full list.

        Args:
            directory: Directory to scan

        Returns:
            Number of matching files
        """
        return len(self.scan(directory))


class RenderScanner(FileScanner):
    """
    Scanner for render image files (EXR, PNG, JPG, TIFF).

    Used for finding render outputs, ComfyUI generations, etc.
    """

    @property
    def extensions(self) -> Set[str]:
        return {'.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff'}


class HIPScanner(FileScanner):
    """
    Scanner for Houdini project files.

    Default behavior matches only files containing 'lookdev' in the name.
    """

    def __init__(
        self,
        recursive: bool = True,
        require_lookdev: bool = True,
        follow_symlinks: bool = False
    ):
        """
        Initialize HIP scanner.

        Args:
            recursive: Whether to scan subdirectories
            require_lookdev: Only match files containing 'lookdev' (default: True)
            follow_symlinks: Whether to follow symbolic links
        """
        super().__init__(recursive=recursive, follow_symlinks=follow_symlinks)
        self.require_lookdev = require_lookdev

    @property
    def extensions(self) -> Set[str]:
        return {'.hip', '.hipnc', '.hiplc'}

    def matches(self, path: Path) -> bool:
        """Match HIP files, optionally requiring 'lookdev' in name."""
        if not super().matches(path):
            return False
        if self.require_lookdev and 'lookdev' not in path.name.lower():
            return False
        return True


class CompScanner(FileScanner):
    """
    Scanner for compositing files (Nuke, Fusion).

    Default behavior matches only files containing 'Compositing' in the name
    and excludes files with 'baking' in the name.
    """

    def __init__(
        self,
        recursive: bool = True,
        require_compositing: bool = True,
        exclude_baking: bool = True,
        follow_symlinks: bool = False
    ):
        """
        Initialize comp scanner.

        Args:
            recursive: Whether to scan subdirectories
            require_compositing: Only match files containing 'Compositing' (default: True)
            exclude_baking: Exclude files containing 'baking' (default: True)
            follow_symlinks: Whether to follow symbolic links
        """
        super().__init__(recursive=recursive, follow_symlinks=follow_symlinks)
        self.require_compositing = require_compositing
        self.exclude_baking = exclude_baking

    @property
    def extensions(self) -> Set[str]:
        return {'.nk', '.nknc', '.comp'}

    def matches(self, path: Path) -> bool:
        """Match comp files with filtering."""
        if not super().matches(path):
            return False
        name = path.name
        if self.require_compositing and 'Compositing' not in name:
            return False
        if self.exclude_baking and 'baking' in name.lower():
            return False
        return True


class ImageScanner(FileScanner):
    """
    Scanner for common image files (for gallery, previews, etc.).

    Matches common web/preview image formats.
    """

    @property
    def extensions(self) -> Set[str]:
        return {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}


class VideoScanner(FileScanner):
    """
    Scanner for video files.
    """

    @property
    def extensions(self) -> Set[str]:
        return {'.mp4', '.mov', '.avi', '.mkv', '.webm'}


class ModelScanner(FileScanner):
    """
    Scanner for 3D model files.

    Matches formats supported by the geo loaders.
    """

    @property
    def extensions(self) -> Set[str]:
        return {
            '.usd', '.usda', '.usdc', '.usdz',  # USD
            '.obj', '.fbx', '.gltf', '.glb',     # Common mesh formats
            '.ply', '.stl', '.off',               # Point cloud / mesh
            '.abc',                                # Alembic
        }


class USDScanner(FileScanner):
    """
    Scanner specifically for USD files.
    """

    @property
    def extensions(self) -> Set[str]:
        return {'.usd', '.usda', '.usdc', '.usdz'}


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

_SCANNER_REGISTRY = {
    'render': RenderScanner,
    'hip': HIPScanner,
    'comp': CompScanner,
    'image': ImageScanner,
    'video': VideoScanner,
    'model': ModelScanner,
    'usd': USDScanner,
}


def get_scanner(scanner_type: str, **kwargs) -> FileScanner:
    """
    Factory function to get a scanner by type.

    Args:
        scanner_type: Type of scanner ('render', 'hip', 'comp', 'image', 'video', 'model', 'usd')
        **kwargs: Arguments to pass to scanner constructor

    Returns:
        FileScanner instance

    Raises:
        ValueError: If scanner_type is unknown
    """
    if scanner_type not in _SCANNER_REGISTRY:
        raise ValueError(
            f"Unknown scanner type: {scanner_type}. "
            f"Available: {list(_SCANNER_REGISTRY.keys())}"
        )
    return _SCANNER_REGISTRY[scanner_type](**kwargs)


def scan_files(
    directory: str,
    scanner_type: str,
    **scanner_kwargs
) -> List[Path]:
    """
    Convenience function to scan files in one call.

    Args:
        directory: Directory to scan
        scanner_type: Type of scanner to use
        **scanner_kwargs: Arguments to pass to scanner

    Returns:
        List of matching file paths
    """
    scanner = get_scanner(scanner_type, **scanner_kwargs)
    return scanner.scan(directory)
