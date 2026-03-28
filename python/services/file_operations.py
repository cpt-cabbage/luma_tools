"""
File system operations for Luma Tools.

Handles directory scanning, file discovery, and file system queries.
"""

import logging
import os
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

from core.config import (
    RENDERS_SUBPATH,
    USD_SUBPATH,
    DEFAULT_TASK,
    COMP_EXTENSIONS,
    HIP_EXTENSION,
    EXR_EXTENSION,
    DENOISED_SUBDIRECTORY
)
from core.utils import truncate_at_suffix
from core.error_handling import safe_operation


def fast_scandir(dirname, max_depth=100, _current_depth=0):
    """
    Recursively scan directory and return all subdirectories.

    Args:
        dirname: Root directory to scan
        max_depth: Maximum recursion depth (default 100, prevents stack overflow)
        _current_depth: Internal counter for current depth (do not set manually)

    Returns:
        list: List of all subdirectory paths (strings)
    """
    if _current_depth >= max_depth:
        logger.warning(f"Max scan depth ({max_depth}) reached at: {dirname}")
        return []

    try:
        subfolders = [f.path for f in os.scandir(dirname) if f.is_dir()]
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot scan directory {dirname}: {e}")
        return []

    for folder in list(subfolders):
        subfolders.extend(fast_scandir(folder, max_depth, _current_depth + 1))
    return subfolders


def scan_directories(root: str, recursive: bool = True) -> List[Path]:
    """
    Scan directory and return subdirectories using pathlib.

    Args:
        root: Root directory to scan
        recursive: If True, scan recursively; if False, only immediate children

    Returns:
        List of Path objects for all subdirectories
    """
    if not root or not os.path.isdir(root):
        return []

    root_path = Path(root)
    if recursive:
        return [p for p in root_path.rglob("*") if p.is_dir()]
    else:
        return [p for p in root_path.iterdir() if p.is_dir()]


def scan_files_by_extension(
    root: str,
    extensions: set,
    recursive: bool = True
) -> List[Path]:
    """
    Scan directory for files with specific extensions.

    Args:
        root: Root directory to scan
        extensions: Set of extensions to match (lowercase, with dot, e.g., {'.png', '.jpg'})
        recursive: If True, scan recursively

    Returns:
        List of Path objects for matching files
    """
    if not root or not os.path.isdir(root):
        return []

    root_path = Path(root)
    pattern = "**/*" if recursive else "*"

    return [
        p for p in root_path.glob(pattern)
        if p.is_file() and p.suffix.lower() in extensions
    ]


def find_renders(render_path):
    """
    Find render sequences in the denoised subdirectory.

    Delegates to core.utils.scan_exr_sequences for the actual scanning.

    Args:
        render_path: Base render path (denoised/ subdirectory is appended)

    Returns:
        list: List of fileseq.FileSequence objects for found sequences
    """
    from core.utils import scan_exr_sequences
    denoised_path = os.path.join(render_path, DENOISED_SUBDIRECTORY)
    return scan_exr_sequences(denoised_path)


def find_hip_files(dirname, task=None):
    """
    Find Houdini HIP files containing the task name in the filename.

    Args:
        dirname: Directory to search
        task: Task name to match in filename (e.g., 'lighting', 'lookdev').
              Falls back to DEFAULT_TASK if not provided.

    Returns:
        list: List of HIP file names
    """
    search_term = (task or DEFAULT_TASK).lower()
    hipfiles = []
    for root, dirs, files in os.walk(dirname):
        for file in files:
            if file.endswith(HIP_EXTENSION):
                if search_term in file.lower():
                    hipfiles.append(file)
    return hipfiles


def find_comp_files(compdirname):
    """
    Find compositing files (Nuke/Fusion) containing 'Compositing' in the name.
    Ignores files with 'baking' in the name.

    Args:
        compdirname: Directory to search

    Returns:
        list: List of comp file names
    """
    compfiles = []
    for root, dirs, files in os.walk(compdirname):
        for file in files:
            if any(file.endswith(ext) for ext in COMP_EXTENSIONS):
                if "Compositing" in file and "baking" not in file.lower():
                    compfiles.append(file)
    return compfiles


def read_comp_file(compfile, hip_file_name):
    """
    Read comp file and extract render references matching the HIP file name.

    Args:
        compfile: Path to comp file
        hip_file_name: HIP file name to search for

    Returns:
        list: List of render names found in comp file
    """
    renders_in_comp = []

    try:
        with open(compfile, "r") as f:
            for line in f:
                if hip_file_name in line:
                    if any(compfile.endswith(ext) for ext in COMP_EXTENSIONS):
                        # Parse file path from comp
                        foundcomps = line
                        foundcomps = foundcomps.lstrip()
                        if foundcomps.startswith("file "):
                            foundcomps = foundcomps[5:]  # Remove "file " prefix
                        foundcomps = foundcomps.strip()
                        foundcomps = os.path.dirname(foundcomps)
                        foundcomps = foundcomps.removesuffix('/for_comp').removesuffix('\\for_comp')
                        foundcomps = foundcomps.split(r"/")[-1]
                        renders_in_comp.append(foundcomps)
    except Exception as e:
        logger.error(f"Error reading comp file {compfile}: {e}")

    return renders_in_comp


def find_render_directory(shot_path, task=None):
    """
    Find the render directory for a given shot path.

    Args:
        shot_path: Path to shot
        task: Task name (e.g., 'lighting', 'lookdev'). Falls back to DEFAULT_TASK.

    Returns:
        tuple: (render_directory, all_render_folders) or (None, [])
    """
    try:
        task_dir = get_task_directory(shot_path, task)

        dirs = fast_scandir(task_dir)
        render_folders = [d for d in dirs if RENDERS_SUBPATH in d]

        if render_folders:
            render_directory = truncate_at_suffix(render_folders[0], RENDERS_SUBPATH)
            return render_directory, render_folders

    except Exception as e:
        logger.error(f"Error finding render directory: {e}")

    return None, []


def find_usd_directory(shot_path, task=None):
    """
    Find the USD files directory for a given shot path.

    Args:
        shot_path: Path to shot
        task: Task name (e.g., 'lighting', 'lookdev'). Falls back to DEFAULT_TASK.

    Returns:
        tuple: (usd_directory, all_usd_folders) or (None, [])
    """
    try:
        task_dir = get_task_directory(shot_path, task)

        dirs = fast_scandir(task_dir)
        usd_folders = [d for d in dirs if USD_SUBPATH in d]

        if usd_folders:
            usd_directory = truncate_at_suffix(usd_folders[0], USD_SUBPATH)
            return usd_directory, usd_folders

    except Exception as e:
        logger.error(f"Error finding USD directory: {e}")

    return None, []


@safe_operation("scanning render versions", return_on_error=[])
def scan_render_versions(render_directory, hip_file_name):
    """
    Scan for render versions matching the HIP file name.

    Args:
        render_directory: Directory containing renders
        hip_file_name: HIP file name to match

    Returns:
        list: List of render version directory names
    """
    render_dirs = sorted(next(os.walk(render_directory))[1])
    matching_renders = [d for d in render_dirs if hip_file_name in d]
    return matching_renders


@safe_operation("scanning USD versions", return_on_error=[])
def scan_usd_versions(usd_directory):
    """
    Scan for USD versions.

    Args:
        usd_directory: Directory containing USD files

    Returns:
        list: List of USD version directory names
    """
    usd_dirs = sorted(next(os.walk(usd_directory))[1])
    return usd_dirs


def get_task_directory(shot_path, task=None):
    """
    Get the task directory from shot path.

    Builds the path: <work_root>/<task_name>
    e.g., W:/Solensia/shots/sh0030/work/lighting

    Args:
        shot_path: Path to shot (may include task subdirectory)
        task: Task name (e.g., 'lighting', 'lookdev'). Falls back to DEFAULT_TASK.

    Returns:
        str: Path to task directory
    """
    task_name = task or DEFAULT_TASK
    task_dir = truncate_at_suffix(shot_path, "work")
    task_dir = os.path.join(task_dir, task_name)
    return task_dir


# Keep backward-compatible alias
def get_lookdev_directory(shot_path, task=None):
    """Get the task directory from shot path. Alias for get_task_directory."""
    return get_task_directory(shot_path, task)


def get_working_directory(shot_path, task=None):
    """
    Get the working directory from shot path.

    Args:
        shot_path: Path to shot
        task: Task name to truncate at. Falls back to DEFAULT_TASK.

    Returns:
        str: Path to working directory (up to and including task dir)
    """
    task_name = task or DEFAULT_TASK
    working_dir = truncate_at_suffix(shot_path, task_name)
    return working_dir


def get_comp_directory(shot_path):
    """
    Get the compositing directory from shot path.

    Args:
        shot_path: Path to shot

    Returns:
        str: Path to compositing directory
    """
    comp_dir = truncate_at_suffix(shot_path, "work")
    comp_dir = os.path.join(comp_dir, "Compositing")
    return comp_dir
