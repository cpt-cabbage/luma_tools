"""
Gallery cleanup service for Luma Tools.

Provides gallery footprint scanning, analysis, and cleanup operations.
Designed for thread-safe background execution.
"""

import os
import logging
import time
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field

from core.config import (
    GALLERY_IMAGE_EXTENSIONS,
    GALLERY_MODEL_EXTENSIONS,
    GALLERY_VIDEO_EXTENSIONS,
    GALLERY_AUDIO_EXTENSIONS,
    GALLERY_SUPPORTED_EXTENSIONS,
)
from core.utils import ByteSize
from core.settings_manager import safe_get_setting

logger = logging.getLogger(__name__)


@dataclass
class GalleryFile:
    """Represents a single gallery file with its metadata."""

    path: str
    filename: str
    size: int
    mtime: float
    extension: str
    output_type: str  # image, video, 3d, audio, other
    workflow_preset: Optional[str] = None
    job_prefix: Optional[str] = None
    created_by: Optional[str] = None  # Username who created the file

    @property
    def age_days(self) -> int:
        """Return file age in days."""
        return int((time.time() - self.mtime) / 86400)


@dataclass
class GalleryFootprint:
    """Aggregated gallery footprint statistics."""

    total_size: int = 0
    total_files: int = 0

    # By output type: {"image": {"size": int, "count": int}, ...}
    by_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # By workflow preset: {"FLUX Dev": {"size": int, "count": int}, ...}
    by_preset: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # By age bucket: {"Last 7 days": {"size": int, "count": int}, ...}
    by_age: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # By user: {"username": {"size": int, "count": int}, ...}
    by_user: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Raw file list for cleanup operations
    files: List[GalleryFile] = field(default_factory=list)

    def add_file(self, gf: GalleryFile):
        """Add a file to the footprint statistics."""
        self.total_size += gf.size
        self.total_files += 1
        self.files.append(gf)

        # By type
        if gf.output_type not in self.by_type:
            self.by_type[gf.output_type] = {"size": 0, "count": 0}
        self.by_type[gf.output_type]["size"] += gf.size
        self.by_type[gf.output_type]["count"] += 1

        # By preset
        preset_key = gf.workflow_preset or "Unknown"
        if preset_key not in self.by_preset:
            self.by_preset[preset_key] = {"size": 0, "count": 0}
        self.by_preset[preset_key]["size"] += gf.size
        self.by_preset[preset_key]["count"] += 1

        # By age bucket
        age_bucket = self._get_age_bucket(gf.age_days)
        if age_bucket not in self.by_age:
            self.by_age[age_bucket] = {"size": 0, "count": 0}
        self.by_age[age_bucket]["size"] += gf.size
        self.by_age[age_bucket]["count"] += 1

        # By user
        if gf.created_by:
            if gf.created_by not in self.by_user:
                self.by_user[gf.created_by] = {"size": 0, "count": 0}
            self.by_user[gf.created_by]["size"] += gf.size
            self.by_user[gf.created_by]["count"] += 1

    def _get_age_bucket(self, age_days: int) -> str:
        """Categorize age into buckets."""
        if age_days <= 7:
            return "Last 7 days"
        elif age_days <= 30:
            return "8-30 days"
        elif age_days <= 90:
            return "31-90 days"
        else:
            return "Older than 90 days"


def get_gallery_output_path() -> Optional[str]:
    """Get the gallery output directory from settings."""
    path = safe_get_setting("network_output_path", "")
    if path and os.path.isdir(path):
        return path
    return None


def classify_file_type(extension: str) -> str:
    """Classify a file extension into output type category."""
    ext = extension.lower()
    if ext in GALLERY_IMAGE_EXTENSIONS:
        return "image"
    elif ext in GALLERY_VIDEO_EXTENSIONS:
        return "video"
    elif ext in GALLERY_MODEL_EXTENSIONS:
        return "3d"
    elif ext in GALLERY_AUDIO_EXTENSIONS:
        return "audio"
    else:
        return "other"


def scan_gallery_footprint(
    output_dir: str,
    user_filter: Optional[str] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> GalleryFootprint:
    """
    Scan gallery directory and compute footprint statistics.

    Thread-safe: Can be run in a worker thread.

    Gallery structure is expected to be: {output_dir}/{username}/...
    Files in user subdirectories are attributed to that user.

    Args:
        output_dir: Gallery output directory to scan
        user_filter: If provided, only scan files belonging to this user
        progress_callback: Optional callback(percent, message)

    Returns:
        GalleryFootprint with statistics and file list
    """
    footprint = GalleryFootprint()

    if not output_dir or not os.path.isdir(output_dir):
        logger.warning(f"Gallery path not valid: {output_dir}")
        return footprint

    # Lazy import to avoid circular
    from comfyui.metadata import load_gallery_metadata

    if progress_callback:
        progress_callback(5, "Scanning gallery files...")

    # Collect all files from user subdirectories
    supported_extensions = {ext.lower() for ext in GALLERY_SUPPORTED_EXTENSIONS}
    files_to_process = []
    metadata_cache = {}  # Cache metadata per directory

    try:
        # First level: user directories
        with os.scandir(output_dir) as user_entries:
            for user_entry in user_entries:
                if not user_entry.is_dir():
                    continue

                username = user_entry.name

                # Apply user filter if specified
                if user_filter and username != user_filter:
                    continue

                user_dir = user_entry.path

                # Load metadata for this user's directory
                metadata_cache[user_dir] = load_gallery_metadata(user_dir)

                # Scan files in user directory (non-recursive for simplicity)
                try:
                    with os.scandir(user_dir) as file_entries:
                        for file_entry in file_entries:
                            if not file_entry.is_file():
                                continue
                            ext = os.path.splitext(file_entry.name)[1].lower()
                            if ext not in supported_extensions:
                                continue
                            try:
                                stat = file_entry.stat()
                                files_to_process.append(
                                    (file_entry.path, file_entry.name, stat.st_size,
                                     stat.st_mtime, ext, username, user_dir)
                                )
                            except OSError:
                                continue
                except OSError:
                    continue

    except OSError as e:
        logger.warning(f"Error scanning gallery: {e}")
        return footprint

    total_files = len(files_to_process)
    logger.info(f"Found {total_files} gallery files to process")

    if progress_callback:
        progress_callback(20, f"Processing {total_files} files...")

    # Process files and extract metadata
    for idx, (path, name, size, mtime, ext, username, user_dir) in enumerate(files_to_process):
        # Look up workflow preset from cached metadata
        workflow_preset = None
        job_prefix = None
        metadata = metadata_cache.get(user_dir, {})

        # Try to find metadata for this file
        basename = os.path.splitext(name)[0]
        for key, value in metadata.items():
            if key.startswith("_prefix_"):
                prefix = key[8:]
                if basename.startswith(prefix):
                    workflow_preset = value.get("workflow_preset")
                    job_prefix = value.get("job_prefix", prefix)
                    break

        # Determine output type from extension
        output_type = classify_file_type(ext)

        gf = GalleryFile(
            path=path,
            filename=name,
            size=size,
            mtime=mtime,
            extension=ext,
            output_type=output_type,
            workflow_preset=workflow_preset,
            job_prefix=job_prefix,
            created_by=username,
        )
        footprint.add_file(gf)

        if progress_callback and idx % 100 == 0:
            pct = 20 + int((idx / total_files) * 70)
            progress_callback(pct, f"Processing {idx}/{total_files} files...")

    if progress_callback:
        progress_callback(100, "Scan complete")

    logger.info(
        f"Gallery scan complete: {footprint.total_files} files, {ByteSize(footprint.total_size)}"
    )

    return footprint


def filter_files_for_cleanup(
    footprint: GalleryFootprint,
    by_types: Optional[List[str]] = None,
    by_presets: Optional[List[str]] = None,
    older_than_days: Optional[int] = None,
) -> Tuple[List[GalleryFile], int]:
    """
    Filter files based on cleanup criteria.

    Args:
        footprint: Scanned gallery footprint
        by_types: List of output types to include (None = all)
        by_presets: List of workflow presets to include (None = all)
        older_than_days: Only include files older than this (None = all ages)

    Returns:
        Tuple of (filtered files list, total size in bytes)
    """
    filtered = []
    total_size = 0

    for gf in footprint.files:
        # Type filter
        if by_types and gf.output_type not in by_types:
            continue

        # Preset filter
        if by_presets:
            preset = gf.workflow_preset or "Unknown"
            if preset not in by_presets:
                continue

        # Age filter
        if older_than_days is not None and gf.age_days < older_than_days:
            continue

        filtered.append(gf)
        total_size += gf.size

    return filtered, total_size


def cleanup_gallery_files(
    files: List[GalleryFile],
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Tuple[int, int, List[str]]:
    """
    Delete the specified gallery files.

    Args:
        files: List of GalleryFile objects to delete
        progress_callback: Optional callback(percent, message)

    Returns:
        Tuple of (deleted_count, freed_bytes, error_messages)
    """
    deleted_count = 0
    freed_bytes = 0
    errors = []

    total = len(files)
    for idx, gf in enumerate(files):
        try:
            if os.path.exists(gf.path):
                os.remove(gf.path)
                deleted_count += 1
                freed_bytes += gf.size
                logger.debug(f"Deleted: {gf.filename}")
        except Exception as e:
            error_msg = f"Failed to delete {gf.filename}: {e}"
            errors.append(error_msg)
            logger.warning(error_msg)

        if progress_callback and idx % 10 == 0:
            pct = int((idx / total) * 100) if total > 0 else 100
            progress_callback(pct, f"Deleting {idx}/{total} files...")

    if progress_callback:
        progress_callback(100, "Cleanup complete")

    logger.info(
        f"Gallery cleanup: deleted {deleted_count} files, freed {ByteSize(freed_bytes)}"
    )

    return deleted_count, freed_bytes, errors
