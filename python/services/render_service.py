"""
Render management service for Luma Tools.

Handles pass detection, channel parsing, and render configuration.
"""

import logging
import os
import re
import shlex

logger = logging.getLogger(__name__)

from core.config import OIIO_INFO_PATH, EXCLUDED_CHANNELS, NORMAL_CHANNELS
from core.utils import substring_after, truncate_at_suffix, ensure_directory, normalize_path, replace_frame_tokens, load_json, save_json
from core.subprocess_utils import run_command
from core.progress_utils import report_progress

# Hard cap on iinfo / oiiotool calls. Network EXR mounts can hang indefinitely
# and the calls run on worker threads, so we never want to block forever.
_OIIO_CMD_TIMEOUT = 60


def detect_passes(render_file):
    """
    Detect passes in a render file using OIIO.

    Args:
        render_file: Path to render EXR file

    Returns:
        dict: Dictionary mapping pass names to channel lists
    """
    if not OIIO_INFO_PATH:
        logger.error("OIIO not available (standalone mode)")
        return {}

    if not os.path.exists(render_file):
        logger.error(f"Render file not found: {render_file}")
        return {}

    # Look for passes in file using OIIO
    result = run_command([OIIO_INFO_PATH, '-v', '-m', 'channel', render_file], timeout=_OIIO_CMD_TIMEOUT)
    if result.returncode != 0:
        logger.error(f"OIIO command failed: {result.stderr}")
        return {}

    choutput = result.stdout

    # OIIO `-v` prints additional metadata lines after the channel list.
    # Take only the first line after the marker so subsequent attribute lines
    # don't get interpreted as channel names.
    channelsraw = substring_after(choutput, "channel list:").splitlines()[0] if "channel list:" in choutput else ""
    channelsraw = re.sub(r"\(.*?\)", "", channelsraw)
    channelscaptured = channelsraw.split(",")

    # Convert passes into dictionary
    channels = {}
    for ch in channelscaptured:
        # Filter out unwanted channels
        if not any(excluded in ch for excluded in EXCLUDED_CHANNELS):
            if "." in ch:
                try:
                    key = truncate_at_suffix(ch, ".")
                    key = key.replace(".", "")
                except (ValueError, AttributeError) as e:
                    logger.debug(f"Channel parse fallback for {ch!r}: {e}")
                    key = ch
            else:
                key = ch

            key = key.strip()
            channelgroup = channels.get(key, [])
            channelgroup.append(ch.strip())
            channels[key] = channelgroup

    # Manual Passes - Normals (only if the file actually has normal.* channels)
    if any(c.strip() in {"normal.x", "normal.y", "normal.z"} for c in channelscaptured):
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
        return load_json(pass_file, {})
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
    # Ensure directory exists (dirname is "" for a bare filename — guard it,
    # os.makedirs("") raises FileNotFoundError)
    pass_dir = os.path.dirname(pass_file)
    if pass_dir:
        ensure_directory(pass_dir)

    save_json(pass_file, passes_dict)

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


def build_oiio_command(passes_dict, denoised_path, renders_path, output_path, is_denoised=True):
    """
    Build OIIO command for combining passes.

    When is_denoised=True (default), beauty channels are read from the denoised
    file and AOVs from the raw render. When is_denoised=False, everything is read
    from the raw render file.

    Args:
        passes_dict: Dictionary of passes to build
        denoised_path: Path to denoised renders (ignored when is_denoised=False)
        renders_path: Path to raw renders
        output_path: Output path for combined passes
        is_denoised: Whether denoised renders are available

    Returns:
        str: OIIO command arguments
    """
    # When not denoised, read beauty from raw render instead.
    # Always normalize Windows paths to forward slashes so the eventual
    # shlex.split call doesn't mangle backslashes inside quoted tokens.
    if not is_denoised:
        denoised_path = renders_path
    denoised_path = normalize_path(denoised_path)
    renders_path = normalize_path(renders_path)
    output_path = normalize_path(output_path)

    # Build Denoise Passes String — exclude actual normal channels
    # (normal.x/y/z) and the Crypto* keys, which are emitted separately into
    # render_passes below. Without the Crypto skip the same channel names
    # appear in both --chnames lists, producing duplicate channel mappings.
    denoised_passes = ""
    _NORMAL_CHANNEL_NAMES = {"normal.x", "normal.y", "normal.z"}
    _CRYPTO_KEYS = {"CryptoMaterials", "CryptoPrimitives"}
    for key, val in passes_dict.items():
        if key == "normal" or key in _CRYPTO_KEYS:
            continue
        for cur in val:
            if str(cur).strip() in _NORMAL_CHANNEL_NAMES:
                continue
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

    # Build OIIO Command (quote paths to handle spaces in directory names)
    oiio_args = ""
    oiio_args += f'"{denoised_path}"'
    oiio_args += " --ch "
    # Defaults - Beauty and Alpha
    base_channels = "Beauty.R,Beauty.G,Beauty.B,a.Z"
    if denoised_passes:
        base_channels += "," + denoised_passes
    oiio_args += base_channels

    # Add Passes from Raw Render
    if render_passes:
        oiio_args += f' "{renders_path}"'
        oiio_args += ' --ch '
        oiio_args += render_passes

    # Append final Pass names
    # Copy beauty and alpha to RGBA
    oiio_args += ' --chappend'
    # Build --chnames: R,G,B,A + denoised + render passes (no trailing/double commas)
    chnames_parts = ["R,G,B,A"]
    if denoised_passes:
        chnames_parts.append(denoised_passes)
    if render_passes:
        chnames_parts.append(render_passes)
    oiio_args += ' --chnames ' + ",".join(chnames_parts)
    oiio_args += ' -o '
    oiio_args += f'"{output_path}"'

    return oiio_args


def execute_oiio_local(oiio_path, oiio_args, start_frame=None, end_frame=None, progress_callback=None, cancel_event=None):
    """
    Execute OIIO command locally, frame by frame (like the farm does).

    Args:
        oiio_path: Path to oiiotool executable
        oiio_args: Arguments for oiiotool (with frame token placeholders)
        start_frame: Starting frame number (if None, executes command once)
        end_frame: Ending frame number (if None, executes command once)
        progress_callback: Optional callback function(progress, message) for progress updates
        cancel_event: Optional threading.Event to signal cancellation

    Returns:
        bool: True if successful, False otherwise
    """
    from core.error_handling import check_cancelled
    # If no frame range specified, execute once
    if start_frame is None or end_frame is None:
        local_command = [oiio_path] + [arg.strip('"') for arg in shlex.split(oiio_args, posix=False)]
        logger.info(f"Local Command: {local_command}")

        try:
            result = run_command(local_command, shell=False, timeout=_OIIO_CMD_TIMEOUT)
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

    # Validate frame range
    if start_frame > end_frame:
        logger.error(f"Invalid frame range: {start_frame} > {end_frame}")
        return False

    # Execute frame by frame (like farm does)
    total_frames = end_frame - start_frame + 1
    failed_frames = []

    logger.info(f"Executing OIIO locally for frames {start_frame}-{end_frame} ({total_frames} frames)")
    logger.info(f"OIIO args template: {oiio_args}")

    for frame_num in range(start_frame, end_frame + 1):
        # Check for cancellation before each frame
        check_cancelled(cancel_event)

        # Calculate progress (50-90% range for OIIO execution)
        frame_index = frame_num - start_frame
        progress = 50 + int((frame_index / total_frames) * 40)

        # Replace frame token with actual frame number
        # Deadline uses <STARTFRAME%{padding}> format - need to replace with actual frame
        # Example: <STARTFRAME%4> becomes 1001 (4-digit padding)
        frame_args = replace_frame_tokens(oiio_args, frame_num)

        local_command = [oiio_path, '-v'] + [arg.strip('"') for arg in shlex.split(frame_args, posix=False)]

        # Print first command for debugging
        if frame_num == start_frame:
            logger.info(f"First frame command: {local_command}")

        # Report per-frame progress (50-90% range)
        report_progress(
            progress_callback, progress,
            f"Processing frame {frame_num} ({frame_index + 1}/{total_frames})"
        )

        try:
            result = run_command(local_command, shell=False, timeout=_OIIO_CMD_TIMEOUT)

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


