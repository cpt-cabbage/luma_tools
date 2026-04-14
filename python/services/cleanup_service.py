"""
Cleanup service for Luma Tools.

Handles directory cleanup operations for renders, USD files, and backups.
"""

import logging
import os
import shutil
from typing import List

from core.error_handling import handle_errors
from core.config import RENDERS_SUBPATH, USD_SUBPATH

logger = logging.getLogger(__name__)


def _cleanup_directories(base_path, dirs_to_delete, label):
    """Delete specified subdirectories under base_path.

    Args:
        base_path: Parent directory containing the subdirectories
        dirs_to_delete: List of directory names to delete
        label: Human-readable label for logging (e.g. "render", "USD")

    Returns:
        list: List of deleted directory names
    """
    deleted = []
    for dir_name in dirs_to_delete:
        dir_path = os.path.join(base_path, dir_name)
        if not os.path.exists(dir_path):
            logger.warning(f"Directory not found: {dir_path}")
            continue
        with handle_errors(f"deleting {label} directory {dir_path}"):
            shutil.rmtree(dir_path)
            deleted.append(dir_name)
            logger.info(f"Removed {label} directory: {dir_path}")
    return deleted


def cleanup_renders(lookdev_dir, render_dirs_to_delete):
    """Delete specified render directories."""
    return _cleanup_directories(
        os.path.join(lookdev_dir, RENDERS_SUBPATH), render_dirs_to_delete, "render"
    )


def cleanup_usd(lookdev_dir, usd_dirs_to_delete):
    """Delete specified USD directories."""
    return _cleanup_directories(
        os.path.join(lookdev_dir, USD_SUBPATH), usd_dirs_to_delete, "USD"
    )


def cleanup_hip_backups(lookdev_dir):
    """
    Delete HIP backup directory.

    Args:
        lookdev_dir: Base lookdev directory

    Returns:
        bool: True if successful, False otherwise
    """
    backup_path = os.path.join(lookdev_dir, "backup")

    if not os.path.exists(backup_path):
        logger.warning(f"Backup directory not found: {backup_path}")
        return False

    try:
        shutil.rmtree(backup_path)
        logger.info(f"Removed backup directory: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Error deleting backup directory {backup_path}: {e}")
        return False


def calculate_cleanup_size(lookdev_dir, render_dirs, usd_dirs, include_backups):
    """
    Calculate total size of files to be cleaned up.

    Args:
        lookdev_dir: Base lookdev directory
        render_dirs: List of render directories to clean
        usd_dirs: List of USD directories to clean
        include_backups: Whether to include backup directory

    Returns:
        int: Total size in bytes
    """
    from core.utils import get_folder_size
    from pathlib import Path

    total_size = 0

    # Calculate render sizes
    renders_path = os.path.join(lookdev_dir, "img", "renders")
    for dir_name in render_dirs:
        dir_path = Path(os.path.join(renders_path, dir_name))
        if dir_path.exists():
            total_size += get_folder_size(dir_path)

    # Calculate USD sizes
    usd_path = os.path.join(lookdev_dir, "usd_files")
    for dir_name in usd_dirs:
        dir_path = Path(os.path.join(usd_path, dir_name))
        if dir_path.exists():
            total_size += get_folder_size(dir_path)

    # Calculate backup size
    if include_backups:
        backup_path = Path(os.path.join(lookdev_dir, "backup"))
        if backup_path.exists():
            total_size += get_folder_size(backup_path)

    return total_size


def get_cleanup_summary(lookdev_dir, render_dirs, usd_dirs, include_backups):
    """
    Get summary of cleanup operation.

    Args:
        lookdev_dir: Base lookdev directory
        render_dirs: List of render directories to clean
        usd_dirs: List of USD directories to clean
        include_backups: Whether to include backup directory

    Returns:
        dict: Summary with counts and size
    """
    total_size = calculate_cleanup_size(lookdev_dir, render_dirs, usd_dirs, include_backups)

    summary = {
        "render_count": len(render_dirs),
        "usd_count": len(usd_dirs),
        "backups": include_backups,
        "total_size": total_size,
        "render_dirs": render_dirs,
        "usd_dirs": usd_dirs
    }

    return summary


def filter_renders_in_use(all_renders, renders_in_comp):
    """
    Filter out renders that are in use by comp files.

    Args:
        all_renders: List of all render directories
        renders_in_comp: List of renders referenced in comp files

    Returns:
        list: Renders that are safe to delete (not in comp)
    """
    # Use set for O(n) lookup instead of O(n*m) nested loop
    renders_in_comp_set = set(renders_in_comp)
    return [render for render in all_renders if render not in renders_in_comp_set]


def keep_latest_n_versions(all_versions, n=1):
    """
    Keep only the latest N versions.

    Args:
        all_versions: List of version directory names (sorted)
        n: Number of latest versions to keep

    Returns:
        list: Versions to delete (excluding the latest N)
    """
    if len(all_versions) <= n:
        return []

    # Keep the last N versions, delete the rest
    return all_versions[:-n]
