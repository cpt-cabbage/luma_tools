"""
MP4 Maker Service Module.

Handles MP4 video generation from image sequences.
- For EXR files: Uses OIIO for color conversion, then FFmpeg for encoding
- For other formats (PNG, JPG, etc.): Uses FFmpeg directly
"""

import os
import subprocess
import tempfile
import shutil
from typing import Optional, Callable

import sys
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "ui"))

from config import FFMPEG_PATH, OIIO_PATH, get_ocio_config, FRAME_PADDING
from utils import normalize_path
from ui_components import report_progress


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


def build_ffmpeg_command(
    input_pattern: str,
    output_path: str,
    start_frame: int,
    end_frame: int,
    crf: int = 23,
    burn_in_timecode: bool = False,
    ocio_config: Optional[str] = None
) -> list:
    """
    Build FFmpeg command for image sequence to MP4 conversion.

    Args:
        input_pattern: Input file pattern (e.g., "render.%04d.exr", "frame.%04d.png")
        output_path: Output MP4 file path
        start_frame: Start frame number
        end_frame: End frame number
        crf: Constant Rate Factor (18-28, lower = higher quality)
        burn_in_timecode: Whether to burn in frame numbers
        ocio_config: Path to OCIO config file (uses environment if None)

    Returns:
        List of command arguments for subprocess
    """
    # Calculate frame count
    frame_count = end_frame - start_frame + 1

    # Build base command
    cmd = [
        FFMPEG_PATH,
        "-y",  # Overwrite output file
        "-start_number", str(start_frame),
        "-framerate", "25",  # Standard framerate
        "-i", input_pattern,
        "-frames:v", str(frame_count),
    ]

    # Add video filter chain
    filters = []

    # EXR to MP4 conversion using the eq filter for basic exposure/gamma correction
    # This is simpler and more universal than colorspace conversions
    # Apply: gamma correction to convert linear to display
    # filters.append("eq=gamma=2.2:gamma_r=2.2:gamma_g=2.2:gamma_b=2.2")  # Apply gamma 2.2 (converts linear to sRGB-like)
    filters.append("format=yuv420p")  # H.264 pixel format

    # Add timecode burn-in if requested
    if burn_in_timecode:
        # Create frame counter text overlay
        timecode_filter = (
            f"drawtext=fontfile=C\\\\:/Windows/Fonts/consola.ttf:"
            f"text='Frame\\: %{{expr\\:n+{start_frame}}}':"
            f"fontcolor=white:fontsize=32:box=1:boxcolor=black@0.5:"
            f"boxborderw=5:x=10:y=10"
        )
        filters.append(timecode_filter)

    # Combine filters
    if filters:
        cmd.extend(["-vf", ",".join(filters)])

    # Add encoding settings for H.264
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        output_path
    ])

    return cmd


def convert_exr_to_png_with_oiio(
    input_pattern: str,
    output_dir: str,
    start_frame: int,
    end_frame: int,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> bool:
    """
    Convert EXR sequence to PNG using OIIO with proper ACES/OCIO color management.

    Args:
        input_pattern: Input EXR pattern (e.g., "render.%04d.exr")
        output_dir: Output directory for PNG files
        start_frame: Start frame number
        end_frame: End frame number
        progress_callback: Optional progress callback

    Returns:
        True if successful, False otherwise
    """
    try:
        frame_count = end_frame - start_frame + 1

        # Get OCIO config
        ocio_config = get_ocio_config()

        # Convert per frame using OIIO
        for i, frame in enumerate(range(start_frame, end_frame + 1)):
            # Build input/output paths
            input_file = input_pattern.replace("%04d", f"{frame:04d}")
            output_file = os.path.join(output_dir, f"frame_{frame:04d}.png")

            # Build OIIO command with OCIO color conversion
            # Use colorconvert to transform from ACES/linear to sRGB for display
            oiio_cmd = [
                OIIO_PATH,
                input_file,
            ]

            # Add OCIO color conversion if config is available
            if ocio_config and os.path.exists(ocio_config):
                # Use OCIO to convert from ACEScg (linear) to sRGB (display)
                # This properly handles ACES color management
                oiio_cmd.extend([
                    "--colorconvert", "ACES - ACEScg", "sRGB",
                ])
                print(f"Using OCIO config: {ocio_config}")
            else:
                # Fallback: Use simple gamma curve if OCIO not available
                # This converts linear to sRGB approximation
                print("OCIO config not found, using gamma 2.2 fallback")
                oiio_cmd.extend([
                    "--powc", "0.4545",  # Gamma 1/2.2 = 0.4545 (linear to sRGB)
                ])

            # Strip alpha channel to avoid including it in PNG
            oiio_cmd.extend(["--ch", "R,G,B"])

            # Add output file
            oiio_cmd.extend(["-o", output_file])

            # Print command for debugging (first frame only)
            if i == 0:
                print("=" * 60)
                print("OIIO Conversion Command:")
                print(" ".join(oiio_cmd))
                print("=" * 60)

            # Execute OIIO
            result = subprocess.run(
                oiio_cmd,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                print(f"OIIO conversion failed for frame {frame}")
                print(f"Error: {result.stderr}")
                print(f"Command: {' '.join(oiio_cmd)}")
                return False

            # Update progress (10-50% range for conversion)
            if progress_callback:
                progress = 10 + int((i / frame_count) * 40)
                progress_callback(
                    min(progress, 50),
                    f"Converting frame {frame} to PNG ({i+1}/{frame_count})..."
                )
                if QT_AVAILABLE:
                    QApplication.processEvents()

        return True

    except Exception as e:
        print(f"Error in OIIO conversion: {e}")
        return False


def generate_mp4(
    input_sequence_path: str,
    output_mp4_path: str,
    start_frame: int,
    end_frame: int,
    quality_index: int = 1,
    burn_in_timecode: bool = False,
    progress_callback: Optional[Callable[[int, str], None]] = None
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

    Returns:
        True if successful, False otherwise
    """
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
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Detect file extension to determine if we need OIIO conversion
        # Extract extension from the pattern (e.g., "render.%04d.exr" -> ".exr")
        file_ext = os.path.splitext(input_sequence_path)[1].lower()
        is_exr = file_ext == ".exr"

        # Determine input pattern for FFmpeg
        if is_exr:
            # EXR files need OIIO conversion for proper color management
            print(f"Detected EXR format - will convert to PNG using OIIO")

            # Create temporary directory for PNG files
            temp_dir = tempfile.mkdtemp(prefix="mp4_maker_")
            print(f"Created temporary directory: {temp_dir}")

            report_progress(progress_callback, 8, "Converting EXR to PNG with OIIO...")

            # Step 1: Convert EXR to PNG using OIIO
            success = convert_exr_to_png_with_oiio(
                input_sequence_path,
                temp_dir,
                start_frame,
                end_frame,
                progress_callback
            )

            if not success:
                raise RuntimeError("OIIO conversion failed")

            # Use PNG files as input for FFmpeg
            ffmpeg_input_pattern = os.path.join(temp_dir, f"frame_%04d.png")
        else:
            # Non-EXR files can be used directly by FFmpeg
            print(f"Detected {file_ext} format - will use directly with FFmpeg")
            ffmpeg_input_pattern = input_sequence_path

        # Step 2: Encode sequence to MP4 using FFmpeg
        report_progress(progress_callback, 55, "Encoding MP4 with FFmpeg...")

        # Build FFmpeg command
        frame_count = end_frame - start_frame + 1

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
            timecode_filter = (
                f"drawtext=fontfile=C\\\\:/Windows/Fonts/consola.ttf:"
                f"text='Frame\\: %{{expr\\:n+{start_frame}}}':"
                f"fontcolor=white:fontsize=32:box=1:boxcolor=black@0.5:"
                f"boxborderw=5:x=10:y=10"
            )
            filters.append(timecode_filter)

        filters.append("format=yuv420p")

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

        # Print command for debugging
        print("=" * 60)
        print("FFmpeg Command:")
        print(" ".join(cmd))
        print("=" * 60)

        # Execute FFmpeg
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        # Monitor progress
        for line in process.stderr:
            print(line.strip())

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
                        if QT_AVAILABLE:
                            QApplication.processEvents()
                except (ValueError, IndexError):
                    pass

        # Wait for completion
        return_code = process.wait()

        if return_code != 0:
            stderr_output = process.stderr.read() if process.stderr else ""
            print(f"FFmpeg failed with return code {return_code}")
            print(f"Error output: {stderr_output}")
            if progress_callback:
                progress_callback(0, f"FFmpeg failed with error code {return_code}")
            return False

        # Verify output file exists
        if not os.path.exists(output_mp4_path):
            print(f"Output file not created: {output_mp4_path}")
            if progress_callback:
                progress_callback(0, "Output file not created")
            return False

        # Success
        report_progress(progress_callback, 98, "MP4 generation complete!")

        print(f"MP4 successfully generated: {output_mp4_path}")
        return True

    except Exception as e:
        print(f"Error generating MP4: {e}")
        if progress_callback:
            progress_callback(0, f"Error: {str(e)}")
        return False

    finally:
        # Clean up temporary directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                print(f"Warning: Could not delete temp directory {temp_dir}: {e}")


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


print("=" * 60)
print("LOADING: mp4_maker.py")
print("=" * 60)

if __name__ == "__main__":
    print("MP4 Maker module loaded successfully")
    print(f"FFmpeg path: {FFMPEG_PATH}")
    print(f"OCIO config: {get_ocio_config() or 'Not set'}")
