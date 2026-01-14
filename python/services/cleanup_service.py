"""
Cleanup service for Luma Tools.

Handles directory cleanup operations for renders, USD files, and backups.
"""

import os
import shutil
from typing import List


def cleanup_renders(lookdev_dir, render_dirs_to_delete):
    """
    Delete specified render directories.

    Args:
        lookdev_dir: Base lookdev directory
        render_dirs_to_delete: List of render directory names to delete

    Returns:
        list: List of deleted directories
    """
    deleted = []
    renders_path = os.path.join(lookdev_dir, "img", "renders")

    for dir_name in render_dirs_to_delete:
        dir_path = os.path.join(renders_path, dir_name)
        try:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
                deleted.append(dir_name)
                print(f"Removed render directory: {dir_path}")
            else:
                print(f"Directory not found: {dir_path}")
        except Exception as e:
            print(f"Error deleting render directory {dir_path}: {e}")

    return deleted


def cleanup_usd(lookdev_dir, usd_dirs_to_delete):
    """
    Delete specified USD directories.

    Args:
        lookdev_dir: Base lookdev directory
        usd_dirs_to_delete: List of USD directory names to delete

    Returns:
        list: List of deleted directories
    """
    deleted = []
    usd_path = os.path.join(lookdev_dir, "usd_files")

    for dir_name in usd_dirs_to_delete:
        dir_path = os.path.join(usd_path, dir_name)
        try:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
                deleted.append(dir_name)
                print(f"Removed USD directory: {dir_path}")
            else:
                print(f"Directory not found: {dir_path}")
        except Exception as e:
            print(f"Error deleting USD directory {dir_path}: {e}")

    return deleted


def cleanup_hip_backups(lookdev_dir):
    """
    Delete HIP backup directory.

    Args:
        lookdev_dir: Base lookdev directory

    Returns:
        bool: True if successful, False otherwise
    """
    backup_path = os.path.join(lookdev_dir, "backup")

    try:
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path)
            print(f"Removed backup directory: {backup_path}")
            return True
        else:
            print(f"Backup directory not found: {backup_path}")
            return False
    except Exception as e:
        print(f"Error deleting backup directory {backup_path}: {e}")
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
    safe_to_delete = []
    for render in all_renders:
        if not any(comp_render in render for comp_render in renders_in_comp):
            safe_to_delete.append(render)

    return safe_to_delete


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
