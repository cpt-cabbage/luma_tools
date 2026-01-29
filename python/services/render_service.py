"""
Render management service for Luma Tools.

Handles pass detection, channel parsing, and render configuration.
"""

import logging
import subprocess
import json
import os
import re
import sys
from typing import Dict, List

logger = logging.getLogger(__name__)

from core.config import OIIO_INFO_PATH, EXCLUDED_CHANNELS, NORMAL_CHANNELS
from core.utils import substring_after, remove_after, ensure_directory
from core.subprocess_utils import run_command

# Import UI utilities
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "ui"))
from ui_components import report_progress


def detect_passes(render_file):
    """
    Detect passes in a render file using OIIO.

    Args:
        render_file: Path to render EXR file

    Returns:
        dict: Dictionary mapping pass names to channel lists
    """
    # Look for passes in file using OIIO
    result = run_command([OIIO_INFO_PATH, '-v', '-m', 'channel', render_file])
    choutput = result.stdout

    channelsraw = substring_after(choutput, "channel list:")
    channelsraw = re.sub(r"\(.*?\)", "", channelsraw)
    channelscaptured = channelsraw.split(",")

    # Convert passes into dictionary
    channels = {}
    for ch in channelscaptured:
        # Filter out unwanted channels
        if not any(excluded in ch for excluded in EXCLUDED_CHANNELS):
            if "." in ch:
                try:
                    key = remove_after(ch, ".")
                    key = key.replace(".", "")
                except (ValueError, AttributeError, Exception):
                    key = ch
            else:
                key = ch

            key = key.strip()
            channelgroup = channels.get(key, [])
            channelgroup.append(ch.strip())
            channels[key] = channelgroup

    # Manual Passes - Normals
    channels["normal"] = NORMAL_CHANNELS

    return channels


def load_pass_config(pass_file):
    """
    Load pass configuration from JSON file.

    Args:
        pass_file: Path to pass configuration JSON

    Returns:
        dict: Pass configuration or empty dict if not found
    """
    logger.info(f"Reading passes from file: {pass_file}")
    if os.path.isfile(pass_file):
        logger.info("Passes file found")
        with open(pass_file) as json_file:
            passes = json.load(json_file)
        return passes
    else:
        logger.info("Passes file not found")
        return {}


def save_pass_config(pass_file, passes_dict):
    """
    Save pass configuration to JSON file.

    Args:
        pass_file: Path to save pass configuration
        passes_dict: Dictionary of passes to save
    """
    # Ensure directory exists
    ensure_directory(os.path.dirname(pass_file))

    with open(pass_file, 'w') as fp:
        json.dump(passes_dict, fp, indent=2)

    logger.info(f"Pass configuration saved to: {pass_file}")


def get_pass_file_path(working_dir, render_name):
    """
    Get the path for a pass configuration file.

    Args:
        working_dir: Working directory path
        render_name: Name of the render

    Returns:
        str: Path to pass file
    """
    shot_data_dir = os.path.join(working_dir, "shot_data")
    return os.path.join(shot_data_dir, f"{render_name}.json")


def build_oiio_command(passes_dict, denoised_path, renders_path, output_path):
    """
    Build OIIO command for combining passes.

    Args:
        passes_dict: Dictionary of passes to build
        denoised_path: Path to denoised renders
        renders_path: Path to raw renders
        output_path: Output path for combined passes

    Returns:
        str: OIIO command arguments
    """
    # Build Denoise Passes String
    denoised_passes = ""
    for key, val in passes_dict.items():
        for cur in val:
            if "normal" not in cur:
                denoised_passes += str(cur).strip()
                denoised_passes += ","

    # Remove last comma
    if denoised_passes:
        denoised_passes = denoised_passes[:-1]

    # Build Render Passes String
    render_passes = ""
    cryptomat = False
    cryptoprim = False

    if "CryptoMaterials" in passes_dict:
        cryptomat = True
        render_passes += 'CryptoMaterials00.R,CryptoMaterials00.G,CryptoMaterials00.B,CryptoMaterials00.A,'
        render_passes += 'CryptoMaterials01.R,CryptoMaterials01.G,CryptoMaterials01.B,CryptoMaterials01.A,'
        render_passes += 'CryptoMaterials02.R,CryptoMaterials02.G,CryptoMaterials02.B,CryptoMaterials02.A'

    if "CryptoPrimitives" in passes_dict:
        cryptoprim = True
        if cryptomat:
            render_passes += ","
        render_passes += 'CryptoPrimitives00.R,CryptoPrimitives00.G,CryptoPrimitives00.B,CryptoPrimitives00.A,'
        render_passes += 'CryptoPrimitives01.R,CryptoPrimitives01.G,CryptoPrimitives01.B,CryptoPrimitives01.A,'
        render_passes += 'CryptoPrimitives02.R,CryptoPrimitives02.G,CryptoPrimitives02.B,CryptoPrimitives02.A'

    if "normal" in passes_dict:
        if cryptoprim or cryptomat:
            render_passes += ","
        render_passes += "normal.x,normal.y,normal.z"

    # Build OIIO Command
    oiio_args = ""
    oiio_args += denoised_path
    oiio_args += " --ch "
    # Defaults - Beauty and Alpha
    oiio_args += "Beauty.R,Beauty.G,Beauty.B,a.Z,"
    oiio_args += denoised_passes

    # Add Passes from Raw Render
    if render_passes:
        oiio_args += f" {renders_path}"
        oiio_args += ' --ch '
        oiio_args += render_passes

    # Append final Pass names
    # Copy beauty and alpha to RGBA
    oiio_args += ' --chappend'
    oiio_args += ' --chnames R,G,B,A,'
    # Add Built Passes
    oiio_args += denoised_passes
    if render_passes != "":
        oiio_args += ","
    oiio_args += render_passes
    oiio_args += ' -o '
    oiio_args += output_path

    return oiio_args


def execute_oiio_local(oiio_path, oiio_args, start_frame=None, end_frame=None, progress_callback=None):
    """
    Execute OIIO command locally, frame by frame (like the farm does).

    Args:
        oiio_path: Path to oiiotool executable
        oiio_args: Arguments for oiiotool (with frame token placeholders)
        start_frame: Starting frame number (if None, executes command once)
        end_frame: Ending frame number (if None, executes command once)
        progress_callback: Optional callback function(progress, message) for progress updates

    Returns:
        bool: True if successful, False otherwise
    """
    # If no frame range specified, execute once
    if start_frame is None or end_frame is None:
        local_command = f'"{oiio_path}" {oiio_args}'
        logger.info(f"Local Command: {local_command}")

        try:
            result = run_command(local_command, shell=True)
            logger.info(f"STDOUT: {result.stdout}")
            if result.stderr:
                logger.info(f"STDERR: {result.stderr}")

            if result.returncode == 0:
                logger.info('OIIO Local Process Successful')
                return True
            else:
                logger.error(f'OIIO Local Process Failed with code {result.returncode}')
                return False

        except Exception as e:
            logger.error(f'OIIO Local Process Failed: {e}')
            return False

    # Execute frame by frame (like farm does)
    total_frames = end_frame - start_frame + 1
    failed_frames = []

    logger.info(f"Executing OIIO locally for frames {start_frame}-{end_frame} ({total_frames} frames)")
    logger.info(f"OIIO args template: {oiio_args}")

    # Import Qt for event processing
    from PySide6.QtWidgets import QApplication


    for frame_num in range(start_frame, end_frame + 1):
        # Calculate progress (50-90% range for OIIO execution)
        frame_index = frame_num - start_frame
        progress = 50 + int((frame_index / total_frames) * 40)

        # Replace frame token with actual frame number
        # Deadline uses <STARTFRAME%{padding}> format - need to replace with actual frame
        # Example: <STARTFRAME%4> becomes 1001 (4-digit padding)
        import re
        frame_args = re.sub(r'<STARTFRAME%(\d+)>', lambda m: f"{frame_num:0{m.group(1)}d}", oiio_args)

        local_command = f'"{oiio_path}" -v {frame_args}'

        # Print first command for debugging
        if frame_num == start_frame:
            logger.info(f"First frame command: {local_command}")

        # Update progress and process Qt events to keep UI responsive
        report_progress(progress_callback, progress, f"Processing frame {frame_num}/{end_frame}...")

        try:
            result = run_command(local_command, shell=True)

            if result.returncode != 0:
                error_msg = f"Frame {frame_num} failed with code {result.returncode}"
                logger.error(error_msg)
                if result.stderr:
                    logger.error(f"STDERR: {result.stderr}")
                failed_frames.append(frame_num)
            else:
                logger.info(f"Frame {frame_num} completed successfully")

        except Exception as e:
            logger.error(f'Frame {frame_num} failed: {e}')
            failed_frames.append(frame_num)

    # Report results
    if failed_frames:
        logger.error(f'OIIO Local Process completed with {len(failed_frames)} failed frames: {failed_frames}')
        return False
    else:
        logger.info(f'OIIO Local Process Successful - all {total_frames} frames completed')
        return True


def get_render_basename(render_path):
    """
    Extract base name from render path.

    Args:
        render_path: Full path to render

    Returns:
        str: Base name without extension
    """
    filename = os.path.basename(render_path)
    return filename.split(".")[0]
