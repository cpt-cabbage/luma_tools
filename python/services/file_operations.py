"""
File system operations for Luma Tools.

Handles directory scanning, file discovery, and file system queries.
"""

import os
import fileseq
from pathlib import Path
from typing import List, Tuple

from core.config import (
    LOOKDEV_SUBPATH,
    RENDERS_SUBPATH,
    USD_SUBPATH,
    COMP_EXTENSIONS,
    HIP_EXTENSION,
    EXR_EXTENSION,
    DENOISED_SUBDIRECTORY
)
from core.utils import remove_after


def fast_scandir(dirname):
    """
    Recursively scan directory and return all subdirectories.

    Args:
        dirname: Root directory to scan

    Returns:
        list: List of all subdirectory paths
    """
    subfolders = [f.path for f in os.scandir(dirname) if f.is_dir()]
    for dirname in list(subfolders):
        subfolders.extend(fast_scandir(dirname))
    return subfolders


def find_renders(render_path):
    """
    Find render sequences in the specified path.

    Args:
        render_path: Path to search for render sequences

    Returns:
        list: List of fileseq.FrameSet objects for found sequences
    """
    # Use the original path pattern with backslashes (Windows-style)
    denoised_path = render_path + "\\denoised\\*.exr"
    sequences = fileseq.findSequencesOnDisk(denoised_path)
    return list(sequences) if sequences else []


def find_hip_files(dirname):
    """
    Find Houdini HIP files containing 'lookdev' in the name.

    Args:
        dirname: Directory to search

    Returns:
        list: List of HIP file names
    """
    hipfiles = []
    for root, dirs, files in os.walk(dirname):
        for file in files:
            if file.endswith(HIP_EXTENSION):
                if "lookdev" in file:
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
                        foundcomps = foundcomps.removeprefix(" file ")
                        foundcomps = foundcomps.strip()
                        foundcomps = os.path.dirname(foundcomps)
                        try:
                            foundcomps = foundcomps.removesuffix(r'/for_comp')
                        except AttributeError:
                            # removesuffix not available in Python <3.9
                            if foundcomps.endswith(r'/for_comp'):
                                foundcomps = foundcomps[:-len(r'/for_comp')]
                        foundcomps = foundcomps.split(r"/")[-1]
                        renders_in_comp.append(foundcomps)
    except Exception as e:
        print(f"Error reading comp file {compfile}: {e}")

    return renders_in_comp


def find_render_directory(shot_path):
    """
    Find the render directory for a given shot path.

    Args:
        shot_path: Path to shot

    Returns:
        tuple: (render_directory, all_render_folders) or (None, [])
    """
    try:
        lookdev_dir = remove_after(shot_path, "work")
        lookdev_dir = lookdev_dir + LOOKDEV_SUBPATH

        dirs = fast_scandir(lookdev_dir)
        render_folders = [d for d in dirs if RENDERS_SUBPATH in d]

        if render_folders:
            render_directory = remove_after(render_folders[0], RENDERS_SUBPATH)
            return render_directory, render_folders

    except Exception as e:
        print(f"Error finding render directory: {e}")

    return None, []


def find_usd_directory(shot_path):
    """
    Find the USD files directory for a given shot path.

    Args:
        shot_path: Path to shot

    Returns:
        tuple: (usd_directory, all_usd_folders) or (None, [])
    """
    try:
        lookdev_dir = remove_after(shot_path, "work")
        lookdev_dir = lookdev_dir + LOOKDEV_SUBPATH

        dirs = fast_scandir(lookdev_dir)
        usd_folders = [d for d in dirs if USD_SUBPATH in d]

        if usd_folders:
            usd_directory = remove_after(usd_folders[0], USD_SUBPATH)
            return usd_directory, usd_folders

    except Exception as e:
        print(f"Error finding USD directory: {e}")

    return None, []


def scan_render_versions(render_directory, hip_file_name):
    """
    Scan for render versions matching the HIP file name.

    Args:
        render_directory: Directory containing renders
        hip_file_name: HIP file name to match

    Returns:
        list: List of render version directory names
    """
    try:
        render_dirs = sorted(next(os.walk(render_directory))[1])
        matching_renders = [d for d in render_dirs if hip_file_name in d]
        return matching_renders
    except Exception as e:
        print(f"Error scanning render versions: {e}")
        return []


def scan_usd_versions(usd_directory):
    """
    Scan for USD versions.

    Args:
        usd_directory: Directory containing USD files

    Returns:
        list: List of USD version directory names
    """
    try:
        usd_dirs = sorted(next(os.walk(usd_directory))[1])
        return usd_dirs
    except Exception as e:
        print(f"Error scanning USD versions: {e}")
        return []


def get_lookdev_directory(shot_path):
    """
    Get the lookdev directory from shot path.

    Args:
        shot_path: Path to shot

    Returns:
        str: Path to lookdev directory
    """
    lookdev_dir = remove_after(shot_path, "work")
    lookdev_dir = lookdev_dir + "\\lookdev"
    return lookdev_dir


def get_working_directory(shot_path):
    """
    Get the working directory from shot path.

    Args:
        shot_path: Path to shot

    Returns:
        str: Path to working directory
    """
    working_dir = remove_after(shot_path, LOOKDEV_SUBPATH)
    return working_dir


def get_comp_directory(shot_path):
    """
    Get the compositing directory from shot path.

    Args:
        shot_path: Path to shot

    Returns:
        str: Path to compositing directory
    """
    comp_dir = remove_after(shot_path, "work")
    comp_dir = comp_dir + "\\Compositing"
    return comp_dir
