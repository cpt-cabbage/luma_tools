"""
File system operations for Luma Tools.

Handles directory scanning, file discovery, and file system queries.
"""

import logging
import os

logger = logging.getLogger(__name__)

from core.config import (
    DEFAULT_TASK,
    COMP_EXTENSIONS,
    HIP_EXTENSION,
    DENOISED_SUBDIRECTORY,
)
from core.utils import truncate_at_suffix


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


def find_renders(render_path):
    """
    Find render sequences in the render directory.

    Scans the root render directory for EXR sequences (raw renders).
    Falls back to the denoised/ subdirectory if no raw renders exist
    (e.g., when raw renders have been cleaned up after denoising).

    Args:
        render_path: Base render path to scan for EXR sequences

    Returns:
        list: List of fileseq.FileSequence objects for found sequences
    """
    sequences, _ = find_renders_with_source(render_path)
    return sequences


def find_renders_with_source(render_path):
    """
    Find render sequences and report which directory they came from.

    Returns the same fallback behavior as `find_renders`, but also returns
    the actual source directory the sequences were found in. Callers that
    need to point downstream tools (e.g., OIIO pass building) at the right
    folder must use this to detect the denoised-only case.

    Returns:
        tuple: (sequences, source_dir) where source_dir is render_path or
        the denoised subdirectory, depending on which scan succeeded.
    """
    from core.utils import scan_exr_sequences

    sequences = scan_exr_sequences(render_path)
    if sequences:
        return sequences, render_path

    denoised_path = os.path.join(render_path, DENOISED_SUBDIRECTORY)
    sequences = scan_exr_sequences(denoised_path)
    if sequences:
        return sequences, denoised_path

    return [], render_path


def get_denoised_status(render_path, render_names):
    """Check which renders have denoised versions available.

    Looks in the denoised/ subdirectory for matching EXR files.

    Args:
        render_path: Base render directory (parent of denoised/)
        render_names: List of render names to check

    Returns:
        dict: {render_name: bool} indicating denoised status
    """
    denoised_path = os.path.join(render_path, DENOISED_SUBDIRECTORY)
    if not os.path.isdir(denoised_path):
        return {name: False for name in render_names}

    try:
        denoised_files = os.listdir(denoised_path)
    except OSError:
        return {name: False for name in render_names}

    # Pre-build set of EXR prefixes for O(1) lookup per render name.
    # Use extract_render_name so versioned names like "scene_v1.2" survive.
    from core.utils import extract_render_name
    denoised_prefixes = set()
    for f in denoised_files:
        if f.endswith(".exr"):
            prefix = extract_render_name(f, strip_frame_padding=True)
            if prefix:
                denoised_prefixes.add(prefix)

    return {name: name in denoised_prefixes for name in render_names}


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
    Find compositing files (Nuke/Fusion) with 'compositing' in the name.
    Ignores files with 'baking' in the name.

    The name match is case-insensitive: shots name their comps
    ``<show>_<shot>_compositing_v021.nk`` in lowercase, while this used to
    require a capital "Compositing". That mismatch made every comp scan return
    nothing, which surfaced as "Comp Directory Not Found!" in the shot summary
    and left Shot Cleaner unable to see which renders a comp still uses.

    Args:
        compdirname: Directory to search

    Returns:
        list: List of comp file names
    """
    compfiles = []
    for root, dirs, files in os.walk(compdirname):
        for file in files:
            if any(file.endswith(ext) for ext in COMP_EXTENSIONS):
                lowered = file.lower()
                if "compositing" in lowered and "baking" not in lowered:
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
        # Comp files (Nuke .nk) are ASCII but may contain non-ASCII paths;
        # explicit utf-8 + replace avoids cp1252 decode crashes on Windows.
        with open(compfile, "r", encoding="utf-8", errors="replace") as f:
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
                        foundcomps = os.path.basename(foundcomps)
                        renders_in_comp.append(foundcomps)
    except Exception as e:
        logger.error(f"Error reading comp file {compfile}: {e}")

    return renders_in_comp


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
