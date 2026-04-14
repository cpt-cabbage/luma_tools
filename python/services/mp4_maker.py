"""
MP4 Maker Service Module.

Handles MP4 video generation from image sequences.
- For EXR files: Uses OIIO for color conversion, then FFmpeg for encoding
- For other formats (PNG, JPG, etc.): Uses FFmpeg directly
"""

import logging
import os
import re
import subprocess
import tempfile
import shutil
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)

from core.config import FFMPEG_PATH, OIIO_PATH, AYON_COLORSPACE, get_ocio_config
from core.error_handling import CancellationError
from core.utils import normalize_path, ensure_directory
from core.subprocess_utils import run_command, start_process
from core.progress_utils import report_progress


def get_crf_value(quality_index: int) -> int:
    """
    Get CRF value from quality combo box index.

    Args:
        quality_index: Index from quality combo box (0=high, 1=medium, 2=low)

    Returns:
        CRF value (lower = higher quality)
    """
    quality_map = {
        0: 18,  # High quality
        1: 23,  # Medium quality
        2: 28   # Low quality
    }
    return quality_map.get(quality_index, 23)


def convert_exr_to_png_with_oiio(
    input_pattern: str,
    output_dir: str,
    start_frame: int,
    end_frame: int,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event=None,
) -> bool:
    """
    Convert EXR sequence to PNG using OIIO with proper ACES/OCIO color management.

    Args:
        input_pattern: Input EXR pattern (e.g., "render.%04d.exr")
        output_dir: Output directory for PNG files
        start_frame: Start frame number
        end_frame: End frame number
        progress_callback: Optional progress callback
        cancel_event: Optional threading.Event to signal cancellation

    Returns:
        True if successful, False otherwise
    """
    from core.error_handling import check_cancelled
    import re
    if not OIIO_PATH or not os.path.exists(OIIO_PATH):
        logger.error("OIIO not available for EXR conversion")
        return False

    # Detect frame padding from the input pattern (e.g. %04d, %05d, %06d).
    # Default to 4 if no token found — caller is expected to pass a printf
    # padding token like %04d, but be defensive about other widths.
    padding_match = re.search(r"%0(\d+)d", input_pattern)
    if not padding_match:
        logger.error(
            f"Input pattern has no %0Nd frame token; cannot substitute frame number: {input_pattern}"
        )
        return False
    padding_width = int(padding_match.group(1))
    padding_token = f"%0{padding_width}d"

    try:
        frame_count = end_frame - start_frame + 1

        # Get OCIO config — evaluate once before the loop
        ocio_config = get_ocio_config()
        use_ocio = bool(ocio_config and os.path.exists(ocio_config))

        # Convert per frame using OIIO
        for i, frame in enumerate(range(start_frame, end_frame + 1)):
            # Check for cancellation before each frame
            check_cancelled(cancel_event)

            # Build input/output paths (preserve original padding width on both sides)
            input_file = input_pattern.replace(padding_token, format(frame, f"0{padding_width}d"))
            output_file = os.path.join(
                output_dir, f"frame_{format(frame, f'0{padding_width}d')}.png"
            )

            # Build OIIO command with OCIO color conversion
            # Use colorconvert to transform from ACES/linear to sRGB for display
            oiio_cmd = [
                OIIO_PATH,
                input_file,
            ]

            # Add OCIO color conversion if config is available
            if use_ocio:
                # Use OCIO to convert from ACEScg (linear) to sRGB (display)
                # This properly handles ACES color management
                oiio_cmd.extend([
                    "--colorconvert", AYON_COLORSPACE, "sRGB",
                ])
                if i == 0:
                    logger.info(f"Using OCIO config: {ocio_config}")
            else:
                # Fallback: Use simple gamma curve if OCIO not available
                # This converts linear to sRGB approximation
                if i == 0:
                    logger.warning("OCIO config not found, using gamma 2.2 fallback")
                oiio_cmd.extend([
                    "--powc", "0.4545",  # Gamma 1/2.2 = 0.4545 (linear to sRGB)
                ])

            # Strip alpha channel to avoid including it in PNG
            oiio_cmd.extend(["--ch", "R,G,B"])

            # Add output file
            oiio_cmd.extend(["-o", output_file])

            # Log command for debugging (first frame only)
            if i == 0:
                logger.info("=" * 60)
                logger.info("OIIO Conversion Command:")
                logger.info(" ".join(oiio_cmd))
                logger.info("=" * 60)

            # Execute OIIO
            result = run_command(oiio_cmd)

            if result.returncode != 0:
                logger.error(f"OIIO conversion failed for frame {frame}")
                logger.error(f"Error: {result.stderr}")
                logger.error(f"Command: {' '.join(oiio_cmd)}")
                return False

            # Update progress (10-50% range for conversion)
            if progress_callback:
                progress = 10 + int(((i + 1) / frame_count) * 40)
                progress_callback(
                    min(progress, 50),
                    f"Converting frame {frame} to PNG ({i+1}/{frame_count})..."
                )

        return True

    except CancellationError:
        raise
    except Exception as e:
        logger.error(f"Error in OIIO conversion: {e}")
        return False


def generate_mp4(
    input_sequence_path: str,
    output_mp4_path: str,
    start_frame: int,
    end_frame: int,
    quality_index: int = 1,
    burn_in_timecode: bool = False,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event=None,
) -> bool:
    """
    Generate MP4 from image sequence.
    - For EXR files: Uses two-step process (EXR -> PNG via OIIO -> MP4 via FFmpeg)
    - For other formats: Uses FFmpeg directly on the original files

    Args:
        input_sequence_path: Path to input sequence (with frame number pattern)
        output_mp4_path: Path to output MP4 file
        start_frame: Start frame number
        end_frame: End frame number
        quality_index: Quality setting (0=high, 1=medium, 2=low)
        burn_in_timecode: Whether to burn in frame numbers
        progress_callback: Optional callback function(progress, message) for progress updates
        cancel_event: Optional threading.Event to signal cancellation

    Returns:
        True if successful, False otherwise
    """
    from core.error_handling import check_cancelled

    if not FFMPEG_PATH:
        logger.error("FFmpeg not available for MP4 generation")
        return False

    temp_dir = None

    try:
        # Report progress
        report_progress(progress_callback, 5, "Preparing conversion...")

        # Normalize paths
        input_sequence_path = normalize_path(input_sequence_path)
        output_mp4_path = normalize_path(output_mp4_path)

        # Get CRF value from quality index
        crf = get_crf_value(quality_index)

        # Ensure output directory exists
        output_dir = os.path.dirname(output_mp4_path)
        if output_dir:
            ensure_directory(output_dir)

        # Detect file extension to determine if we need OIIO conversion
        # Extract extension from the pattern (e.g., "render.%04d.exr" -> ".exr")
        file_ext = os.path.splitext(input_sequence_path)[1].lower()
        is_exr = file_ext == ".exr"

        # Determine input pattern for FFmpeg
        if is_exr:
            # EXR files need OIIO conversion for proper color management
            logger.info(f"Detected EXR format - will convert to PNG using OIIO")

            # Create temporary directory for PNG files
            temp_dir = tempfile.mkdtemp(prefix="mp4_maker_")
            logger.info(f"Created temporary directory: {temp_dir}")

            report_progress(progress_callback, 8, "Converting EXR to PNG with OIIO...")

            # Step 1: Convert EXR to PNG using OIIO
            success = convert_exr_to_png_with_oiio(
                input_sequence_path,
                temp_dir,
                start_frame,
                end_frame,
                progress_callback,
                cancel_event=cancel_event,
            )

            if not success:
                raise RuntimeError("OIIO conversion failed")

            # Use PNG files as input for FFmpeg — match the padding width detected
            # from the input EXR sequence (convert_exr_to_png_with_oiio writes
            # frame_%0Nd.png where N is the input pattern's padding width).
            import re as _re
            _pad_match = _re.search(r"%0(\d+)d", input_sequence_path)
            _pad_width = int(_pad_match.group(1)) if _pad_match else 4
            ffmpeg_input_pattern = os.path.join(temp_dir, f"frame_%0{_pad_width}d.png")
        else:
            # Non-EXR files can be used directly by FFmpeg
            logger.info(f"Detected {file_ext} format - will use directly with FFmpeg")
            ffmpeg_input_pattern = input_sequence_path

        # Check cancellation before FFmpeg step
        check_cancelled(cancel_event)

        # Step 2: Encode sequence to MP4 using FFmpeg
        report_progress(progress_callback, 55, "Encoding MP4 with FFmpeg...")

        # Build FFmpeg command
        frame_count = max(end_frame - start_frame + 1, 1)

        cmd = [
            FFMPEG_PATH,
            "-y",  # Overwrite output
            "-start_number", str(start_frame),
            "-framerate", "25",
            "-i", ffmpeg_input_pattern,
            "-frames:v", str(frame_count),
        ]

        # Add filters
        filters = []

        if burn_in_timecode:
            safe_start_frame = int(start_frame)  # Ensure integer for FFmpeg filter
            timecode_filter = (
                f"drawtext=fontfile=C\\\\:/Windows/Fonts/consola.ttf:"
                f"text='Frame\\: %{{expr\\:n+{safe_start_frame}}}':"
                f"fontcolor=white:fontsize=32:box=1:boxcolor=black@0.5:"
                f"boxborderw=5:x=10:y=10"
            )
            filters.append(timecode_filter)

        if filters:
            cmd.extend(["-vf", ",".join(filters)])

        # Add encoding settings
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            output_mp4_path
        ])

        # Log command for debugging
        logger.info("=" * 60)
        logger.info("FFmpeg Command:")
        logger.info(" ".join(cmd))
        logger.info("=" * 60)

        # Execute FFmpeg
        process = start_process(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Monitor progress and capture stderr
        stderr_lines = []
        for line in process.stderr:
            # Check for cancellation - kill FFmpeg if cancelled
            if cancel_event is not None and cancel_event.is_set():
                logger.info("Cancellation requested, killing FFmpeg process")
                process.kill()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                raise CancellationError("MP4 generation cancelled by user")

            stderr_lines.append(line)
            logger.info(line.strip())

            # Parse frame progress from FFmpeg output
            if "frame=" in line:
                try:
                    frame_str = line.split("frame=")[1].split()[0]
                    current_frame = int(frame_str)

                    # Calculate progress (55-95% range for encoding)
                    progress = 55 + int((current_frame / frame_count) * 40)

                    if progress_callback:
                        progress_callback(
                            min(progress, 95),
                            f"Encoding MP4: frame {current_frame}/{frame_count}..."
                        )
                except (ValueError, IndexError):
                    pass

        # Wait for completion with timeout to prevent hanging
        try:
            return_code = process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg process timed out after 300 seconds, killing process")
            process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.error("FFmpeg process failed to terminate after kill")
            if progress_callback:
                progress_callback(0, "FFmpeg timed out after 5 minutes")
            return False

        if return_code != 0:
            stderr_output = "".join(stderr_lines)
            logger.error(f"FFmpeg failed with return code {return_code}")
            logger.error(f"Error output: {stderr_output}")
            if progress_callback:
                progress_callback(0, f"FFmpeg failed with error code {return_code}")
            return False

        # Verify output file exists
        if not os.path.exists(output_mp4_path):
            logger.error(f"Output file not created: {output_mp4_path}")
            if progress_callback:
                progress_callback(0, "Output file not created")
            return False

        # Success
        report_progress(progress_callback, 98, "MP4 generation complete!")

        logger.info(f"MP4 successfully generated: {output_mp4_path}")
        return True

    except CancellationError:
        raise
    except Exception as e:
        logger.error(f"Error generating MP4: {e}")
        if progress_callback:
            progress_callback(0, f"Error: {str(e)}")
        return False

    finally:
        # Clean up temporary directory with retry for file handle release
        if temp_dir and os.path.exists(temp_dir):
            for attempt in range(3):
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(0.5)  # Wait for file handles to release
                    else:
                        logger.warning(f"Could not delete temp directory after 3 attempts: {temp_dir}: {e}")


def get_output_filename(render_name: str, shot: str) -> str:
    """
    Generate default output filename for MP4.

    Args:
        render_name: Name of the render
        shot: Shot name

    Returns:
        Suggested MP4 filename
    """
    return f"{shot}_{render_name}.mp4"


def get_quality_description(quality_index: int) -> str:
    """Get human-readable quality description from index."""
    descriptions = {
        0: "High (CRF 18)",
        1: "Medium (CRF 23)",
        2: "Low (CRF 28)",
    }
    return descriptions.get(quality_index, "Medium (CRF 23)")


def copy_mp4_to_gallery(
    mp4_path: str,
    user: str,
    shot: str,
    source_path: str,
    frame_range: tuple,
    quality_index: int,
    burn_in_timecode: bool,
) -> tuple:
    """
    Copy generated MP4 to the gallery folder and add metadata.

    Args:
        mp4_path: Full path to the generated MP4 file
        user: Username for gallery subfolder
        shot: Shot name or empty string for standalone mode
        source_path: Full path to source EXR sequence pattern
        frame_range: Tuple of (start_frame, end_frame)
        quality_index: Quality setting index (0=high, 1=medium, 2=low)
        burn_in_timecode: Whether timecode was burned in

    Returns:
        Tuple of (success: bool, path_or_error: str)
        - On success: (True, gallery_path)
        - On failure: (False, error_message)
    """
    from core.settings_manager import get_setting
    from comfyui.metadata import add_mp4_maker_metadata

    try:
        # Get gallery output path from settings
        try:
            gallery_base = get_setting("network_output_path")
        except KeyError:
            gallery_base = None

        if not gallery_base:
            return (False, "Gallery path not configured in settings")

        # Sanitize username to prevent path traversal
        safe_user = re.sub(r'[^\w\-]', '_', user or "standalone")

        # Construct user subfolder
        gallery_user_dir = os.path.join(gallery_base, safe_user)

        # Ensure directory exists
        ensure_directory(gallery_user_dir)

        # Get MP4 filename
        mp4_filename = os.path.basename(mp4_path)

        # Destination path
        gallery_mp4_path = os.path.join(gallery_user_dir, mp4_filename)

        # Check if source file exists
        if not os.path.exists(mp4_path):
            return (False, f"Source MP4 not found: {mp4_path}")

        # Copy file (preserves metadata like timestamps)
        logger.info(f"Copying MP4 to gallery: {gallery_mp4_path}")
        shutil.copy2(mp4_path, gallery_mp4_path)

        # Verify copy succeeded
        if not os.path.exists(gallery_mp4_path):
            return (False, "Failed to copy MP4 to gallery")

        # Extract render name from source path for metadata.
        # Strip the trailing `.<frame>.<ext>` segments only — names with dots
        # like "scene_v1.2.0001.exr" must keep the version suffix.
        from core.utils import extract_render_name
        source_render = extract_render_name(os.path.basename(source_path)) or "unknown"

        # Add metadata
        quality_desc = get_quality_description(quality_index)
        metadata_success = add_mp4_maker_metadata(
            output_dir=gallery_user_dir,
            filename=mp4_filename,
            shot=shot or "standalone",
            source_render=source_render,
            source_path=source_path,
            frame_range=frame_range,
            quality_setting=quality_desc,
            burn_in_timecode=burn_in_timecode,
        )

        if not metadata_success:
            logger.warning("MP4 copied but metadata save failed")

        logger.info(f"MP4 successfully added to gallery: {gallery_mp4_path}")
        return (True, gallery_mp4_path)

    except PermissionError as e:
        logger.error(f"Permission denied copying to gallery: {e}")
        return (False, f"Permission denied: {e}")
    except OSError as e:
        logger.error(f"OS error copying to gallery: {e}")
        return (False, f"File system error: {e}")
    except Exception as e:
        logger.error(f"Error copying MP4 to gallery: {e}")
        return (False, str(e))


if __name__ == "__main__":
    logger.info("MP4 Maker module loaded successfully")
    logger.info(f"FFmpeg path: {FFMPEG_PATH}")
    logger.info(f"OCIO config: {get_ocio_config() or 'Not set'}")
