"""
MP4 Maker Service Module.

Handles MP4 video generation from image sequences.
- For EXR files: Uses OIIO for color conversion, then FFmpeg for encoding
- For other formats (PNG, JPG, etc.): Uses FFmpeg directly
"""

import concurrent.futures
import logging
import os
import re
import subprocess
import tempfile
import shutil
import threading
import time
from collections import deque
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

from core.config import FFMPEG_PATH, OIIO_PATH, AYON_COLORSPACE, get_ocio_config
from core.error_handling import CancellationError
from core.utils import normalize_path, ensure_directory
from core.subprocess_utils import run_command, start_process
from core.progress_utils import report_progress

# Tuning constants
OIIO_MAX_WORKERS = 4  # Parallel oiiotool processes (safe for a network share)
OIIO_FRAME_TIMEOUT = 120  # Seconds allowed per single-frame OIIO conversion
FFMPEG_MIN_TIMEOUT = 300  # Overall FFmpeg timeout floor (seconds)
FFMPEG_PER_FRAME_TIMEOUT = 10  # Seconds budgeted per frame for the FFmpeg encode
STDERR_TAIL_LINES = 15  # Lines of tool stderr included in error details


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


def _stderr_tail(stderr, max_lines: int = STDERR_TAIL_LINES) -> str:
    """Return the last `max_lines` lines of a tool's stderr output.

    Accepts either a string or an iterable of lines (e.g. a deque of
    raw lines captured from a streaming pipe).
    """
    if not stderr:
        return ""
    if isinstance(stderr, str):
        lines = stderr.splitlines()
    else:
        # Snapshot first: the source may be a deque still being appended to by
        # the stderr reader thread (list() over a deque is atomic in CPython).
        lines = [str(line) for line in list(stderr)]
    return "\n".join(line.rstrip() for line in lines[-max_lines:]).strip()


def clamp_frame_range(
    start_frame: Optional[int],
    end_frame: Optional[int],
    seq_start: int,
    seq_end: int,
) -> Tuple[int, int]:
    """
    Clamp a requested frame sub-range to the sequence's actual range.

    Args:
        start_frame: Requested start frame, or None for the sequence start
        end_frame: Requested end frame, or None for the sequence end
        seq_start: First frame that actually exists in the sequence
        seq_end: Last frame that actually exists in the sequence

    Returns:
        (start, end) guaranteed to satisfy seq_start <= start <= end <= seq_end.
        Inverted or out-of-range requests are silently clamped (and logged).
    """
    start = seq_start if start_frame is None else int(start_frame)
    end = seq_end if end_frame is None else int(end_frame)

    if start > end:
        logger.warning(
            f"Requested frame range is inverted ({start}-{end}); swapping"
        )
        start, end = end, start

    clamped_start = min(max(start, seq_start), seq_end)
    clamped_end = max(min(end, seq_end), seq_start)

    if (clamped_start, clamped_end) != (start, end):
        logger.warning(
            f"Requested frame range {start}-{end} clamped to sequence range "
            f"{seq_start}-{seq_end}: using {clamped_start}-{clamped_end}"
        )
    return clamped_start, clamped_end


def _scan_sequence_frames(input_pattern: str) -> Optional[List[int]]:
    """
    List the frame numbers that actually exist on disk for a sequence.

    Scans the directory of `input_pattern` (a printf-style pattern such as
    "X:/renders/shot.%04d.exr") once and returns the matching frame numbers in
    ascending order, or None if the pattern is unusable / the scan failed.
    A single scandir is far cheaper than one stat per frame on a network share.
    """
    match = re.search(r"%0(\d+)d", input_pattern)
    if not match:
        return None
    token = f"%0{match.group(1)}d"

    directory = os.path.dirname(input_pattern) or "."
    basename = os.path.basename(input_pattern)
    if token not in basename:
        # Frame token sits in the directory part — can't scan for that
        return None

    prefix, _, suffix = basename.partition(token)
    frame_re = re.compile(
        re.escape(prefix) + r"(\d+)" + re.escape(suffix) + r"$",
        re.IGNORECASE,
    )

    frames: List[int] = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                name_match = frame_re.match(entry.name)
                if name_match:
                    frames.append(int(name_match.group(1)))
    except OSError as e:
        logger.warning(f"Could not scan sequence directory {directory}: {e}")
        return None

    if not frames:
        return None
    return sorted(frames)


def _find_missing_frames(
    input_pattern: str,
    start_frame: int,
    end_frame: int,
    existing_frames: Optional[set] = None,
) -> List[int]:
    """
    Return frame numbers in [start_frame, end_frame] whose files are missing.

    If `existing_frames` is supplied (from `_scan_sequence_frames`) the check is
    done in memory; otherwise each frame is stat'ed individually.
    """
    if existing_frames is not None:
        return [f for f in range(start_frame, end_frame + 1) if f not in existing_frames]

    match = re.search(r"%0(\d+)d", input_pattern)
    if not match:
        return []
    width = int(match.group(1))
    token = f"%0{width}d"

    missing: List[int] = []
    for frame in range(start_frame, end_frame + 1):
        frame_file = input_pattern.replace(token, format(frame, f"0{width}d"))
        if not os.path.exists(frame_file):
            missing.append(frame)
    return missing


def _stop_process(process) -> None:
    """Terminate a subprocess, escalating to kill if it doesn't exit."""
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.error("Process failed to terminate after kill")
    except OSError:
        pass


def convert_exr_to_png_with_oiio(
    input_pattern: str,
    output_dir: str,
    start_frame: int,
    end_frame: int,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event=None,
    max_workers: int = OIIO_MAX_WORKERS,
) -> Tuple[bool, str]:
    """
    Convert EXR sequence to PNG using OIIO with proper ACES/OCIO color management.

    Frames are converted in parallel (one ``oiiotool`` process per worker) so a
    long sequence is not serialized behind ~200 sequential network reads.

    Args:
        input_pattern: Input EXR pattern (e.g., "render.%04d.exr")
        output_dir: Output directory for PNG files
        start_frame: Start frame number
        end_frame: End frame number
        progress_callback: Optional progress callback
        cancel_event: Optional threading.Event to signal cancellation
        max_workers: Number of concurrent oiiotool processes

    Returns:
        Tuple of (success, error_detail). error_detail is "" on success,
        otherwise a user-meaningful message naming the failed frame(s) and
        including the tail of oiiotool's stderr.

    Raises:
        CancellationError: If cancel_event is set during conversion.
    """
    if not OIIO_PATH or not os.path.exists(OIIO_PATH):
        logger.error("OIIO not available for EXR conversion")
        return False, "OIIO (oiiotool) is not available for EXR conversion."

    # Detect frame padding from the input pattern (e.g. %04d, %05d, %06d).
    # Caller is expected to pass a printf padding token like %04d, but be
    # defensive about other widths.
    padding_match = re.search(r"%0(\d+)d", input_pattern)
    if not padding_match:
        logger.error(
            f"Input pattern has no %0Nd frame token; cannot substitute frame number: {input_pattern}"
        )
        return False, (
            f"Input sequence pattern has no %0Nd frame token: {input_pattern}"
        )
    padding_width = int(padding_match.group(1))
    padding_token = f"%0{padding_width}d"

    frames = list(range(start_frame, end_frame + 1))
    frame_count = len(frames)
    if frame_count <= 0:
        return False, f"Empty frame range requested: {start_frame}-{end_frame}"

    # Get OCIO config — evaluate once, shared by every worker
    ocio_config = get_ocio_config()
    use_ocio = bool(ocio_config and os.path.exists(ocio_config))
    if use_ocio:
        logger.info(f"Using OCIO config: {ocio_config}")
    else:
        logger.warning("OCIO config not found, using gamma 2.2 fallback")

    def _build_cmd(frame: int) -> Tuple[List[str], str]:
        """Build the oiiotool command for a single frame."""
        frame_str = format(frame, f"0{padding_width}d")
        input_file = input_pattern.replace(padding_token, frame_str)
        output_file = os.path.join(output_dir, f"frame_{frame_str}.png")

        cmd = [OIIO_PATH, input_file]
        if use_ocio:
            # Convert from ACEScg (linear) to sRGB (display) via OCIO
            cmd.extend(["--colorconvert", AYON_COLORSPACE, "sRGB"])
        else:
            # Fallback: simple gamma curve (1/2.2 = 0.4545) linear -> sRGB
            cmd.extend(["--powc", "0.4545"])
        # Strip alpha channel to avoid including it in PNG
        cmd.extend(["--ch", "R,G,B"])
        cmd.extend(["-o", output_file])
        return cmd, input_file

    logger.info("=" * 60)
    logger.info(f"OIIO Conversion Command ({max_workers} parallel workers):")
    logger.info(" ".join(_build_cmd(frames[0])[0]))
    logger.info("=" * 60)

    # Thread-safe completion counter shared by the worker threads
    counter_lock = threading.Lock()
    completed = 0

    def _convert_frame(frame: int) -> Tuple[int, Optional[str]]:
        """Convert one frame. Returns (frame, error_message_or_None)."""
        nonlocal completed
        oiio_cmd, input_file = _build_cmd(frame)
        error: Optional[str] = None
        try:
            result = run_command(oiio_cmd, timeout=OIIO_FRAME_TIMEOUT)
            if result.returncode != 0:
                tail = _stderr_tail(result.stderr)
                error = (
                    f"frame {frame} ({os.path.basename(input_file)}): "
                    f"oiiotool exited with code {result.returncode}"
                )
                if tail:
                    error = f"{error}\n{tail}"
                logger.error(f"OIIO conversion failed for {error}")
                logger.error(f"Command: {' '.join(oiio_cmd)}")
        except subprocess.TimeoutExpired:
            error = (
                f"frame {frame} ({os.path.basename(input_file)}): "
                f"oiiotool timed out after {OIIO_FRAME_TIMEOUT}s"
            )
            logger.error(f"OIIO conversion timed out for {error}")
        except OSError as e:
            error = (
                f"frame {frame} ({os.path.basename(input_file)}): "
                f"could not run oiiotool: {e}"
            )
            logger.error(error)

        # Report progress (10-50% range for conversion) using a monotonically
        # increasing shared counter so percentages never go backwards even
        # though frames finish out of order.
        with counter_lock:
            completed += 1
            done_count = completed
        if progress_callback:
            progress = 10 + int((done_count / frame_count) * 40)
            progress_callback(
                min(progress, 50),
                f"Converting frame {frame} to PNG ({done_count}/{frame_count})...",
            )
        return frame, error

    errors: List[Tuple[int, str]] = []
    cancelled = False
    workers = max(1, min(int(max_workers), frame_count))
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="oiio"
    )
    pending: set = set()
    try:
        frame_iter = iter(frames)
        exhausted = False
        while True:
            # Top up the in-flight window, honouring cancellation before each
            # submission so a cancel never queues more network reads.
            while not exhausted and not errors and len(pending) < workers * 2:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break
                try:
                    pending.add(executor.submit(_convert_frame, next(frame_iter)))
                except StopIteration:
                    exhausted = True

            if cancelled or not pending:
                break

            done, pending = concurrent.futures.wait(
                pending,
                timeout=0.5,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                frame, error = future.result()
                if error:
                    errors.append((frame, error))

            # Honour cancellation between completions too
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
    except Exception as e:
        logger.error(f"Error in OIIO conversion: {e}")
        errors.append((-1, f"Unexpected OIIO conversion error: {e}"))
    finally:
        for future in pending:
            future.cancel()
        # Don't block on in-flight oiiotool processes when aborting
        executor.shutdown(wait=not (cancelled or bool(errors)), cancel_futures=True)

    if cancelled:
        raise CancellationError("EXR to PNG conversion cancelled by user")

    if errors:
        errors.sort(key=lambda item: item[0])
        failed_frames = [str(frame) for frame, _ in errors if frame >= 0]
        summary = (
            f"OIIO conversion failed for {len(errors)} frame(s)"
            + (f" ({', '.join(failed_frames[:10])}" if failed_frames else "")
            + (", ..." if len(failed_frames) > 10 else "")
            + (")" if failed_frames else "")
        )
        detail = "\n".join(message for _, message in errors[:3])
        return False, f"{summary}\n{detail}".strip()

    return True, ""


def generate_mp4(
    input_sequence_path: str,
    output_mp4_path: str,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
    quality_index: int = 1,
    burn_in_timecode: bool = False,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event=None,
) -> Tuple[bool, str]:
    """
    Generate MP4 from image sequence.
    - For EXR files: Uses two-step process (EXR -> PNG via OIIO -> MP4 via FFmpeg)
    - For other formats: Uses FFmpeg directly on the original files

    Args:
        input_sequence_path: Path to input sequence (with frame number pattern)
        output_mp4_path: Path to output MP4 file
        start_frame: Optional first frame to encode. None means "the sequence's
            first frame". Values outside the sequence are clamped.
        end_frame: Optional last frame to encode. None means "the sequence's
            last frame". Values outside the sequence are clamped.
        quality_index: Quality setting (0=high, 1=medium, 2=low)
        burn_in_timecode: Whether to burn in frame numbers
        progress_callback: Optional callback function(progress, message) for progress updates
        cancel_event: Optional threading.Event to signal cancellation

    Returns:
        Tuple of (success, error_detail). error_detail is "" on success,
        otherwise a user-meaningful message (missing frames, the tail of
        ffmpeg/oiiotool stderr, the failing frame/file, etc.).

    Raises:
        CancellationError: If cancel_event is set during generation.
    """
    from core.error_handling import check_cancelled

    if not FFMPEG_PATH:
        logger.error("FFmpeg not available for MP4 generation")
        return False, "FFmpeg is not available on this machine."

    temp_dir = None

    try:
        # Report progress
        report_progress(progress_callback, 5, "Preparing conversion...")

        # Normalize paths
        input_sequence_path = normalize_path(input_sequence_path)
        output_mp4_path = normalize_path(output_mp4_path)

        # Resolve the frame sub-range against what actually exists on disk
        existing_frames = _scan_sequence_frames(input_sequence_path)
        if existing_frames:
            start_frame, end_frame = clamp_frame_range(
                start_frame, end_frame, existing_frames[0], existing_frames[-1]
            )
        elif start_frame is None or end_frame is None:
            logger.error(
                f"Could not determine frame range for sequence: {input_sequence_path}"
            )
            return False, (
                "Could not determine the frame range of the sequence "
                f"{input_sequence_path} and no explicit start/end frame was given."
            )
        else:
            start_frame, end_frame = int(start_frame), int(end_frame)
            if start_frame > end_frame:
                start_frame, end_frame = end_frame, start_frame
        logger.info(f"Encoding frame range {start_frame}-{end_frame}")

        # Fail early (with a useful message) on gaps in the sequence — FFmpeg
        # silently stops at the first missing frame.
        missing = _find_missing_frames(
            input_sequence_path,
            start_frame,
            end_frame,
            set(existing_frames) if existing_frames else None,
        )
        if missing:
            shown = ", ".join(str(f) for f in missing[:10])
            suffix = ", ..." if len(missing) > 10 else ""
            logger.error(f"Missing {len(missing)} frame(s) in sequence: {shown}{suffix}")
            return False, (
                f"{len(missing)} frame(s) missing from {input_sequence_path} "
                f"between {start_frame} and {end_frame}: {shown}{suffix}"
            )

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

            # Step 1: Convert only the requested sub-range to PNG using OIIO
            success, oiio_error = convert_exr_to_png_with_oiio(
                input_sequence_path,
                temp_dir,
                start_frame,
                end_frame,
                progress_callback,
                cancel_event=cancel_event,
            )

            if not success:
                report_progress(progress_callback, 0, "OIIO conversion failed")
                return False, oiio_error or "OIIO conversion failed."

            # Use PNG files as input for FFmpeg — match the padding width detected
            # from the input EXR sequence (convert_exr_to_png_with_oiio writes
            # frame_%0Nd.png where N is the input pattern's padding width).
            _pad_match = re.search(r"%0(\d+)d", input_sequence_path)
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

        # Build FFmpeg command. -start_number / -frames:v restrict the encode
        # to the requested sub-range in both the OIIO and direct-FFmpeg paths.
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
            from core.config import MP4_BURN_IN_FONT
            if not MP4_BURN_IN_FONT:
                logger.warning(
                    "Burn-in requested but no font found on this machine; "
                    "skipping timecode overlay."
                )
            else:
                safe_start_frame = int(start_frame)  # Ensure integer for FFmpeg filter
                # Escape backslashes and the drive-letter colon for FFmpeg filter syntax
                font_escaped = MP4_BURN_IN_FONT.replace("\\", "/").replace(":", "\\\\:")
                timecode_filter = (
                    f"drawtext=fontfile={font_escaped}:"
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

        # Drain stderr on a helper thread. Reading the pipe inline can block
        # forever (FFmpeg stuck on a bad frame never closes stderr), which used
        # to make the process.wait() timeout below unreachable.
        stderr_tail_buf = deque(maxlen=200)

        def _drain_stderr():
            try:
                for line in process.stderr:
                    stderr_tail_buf.append(line)
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
                                    f"Encoding MP4: frame {current_frame}/{frame_count}...",
                                )
                        except (ValueError, IndexError):
                            pass
            except (OSError, ValueError) as e:
                # Pipe closed underneath us (process killed) — nothing to do
                logger.debug(f"FFmpeg stderr reader stopped: {e}")

        stderr_thread = threading.Thread(
            target=_drain_stderr, name="ffmpeg-stderr", daemon=True
        )
        stderr_thread.start()

        # Poll for completion in short slices so cancellation stays responsive
        # and an overall deadline is always enforced.
        overall_timeout = max(FFMPEG_MIN_TIMEOUT, FFMPEG_PER_FRAME_TIMEOUT * frame_count)
        deadline = time.monotonic() + overall_timeout
        return_code = None
        while True:
            try:
                return_code = process.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                pass

            if cancel_event is not None and cancel_event.is_set():
                logger.info("Cancellation requested, stopping FFmpeg process")
                _stop_process(process)
                stderr_thread.join(timeout=5)
                raise CancellationError("MP4 generation cancelled by user")

            if time.monotonic() > deadline:
                logger.error(
                    f"FFmpeg process timed out after {overall_timeout} seconds, killing process"
                )
                process.kill()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.error("FFmpeg process failed to terminate after kill")
                stderr_thread.join(timeout=5)
                report_progress(progress_callback, 0, "FFmpeg timed out")
                tail = _stderr_tail(stderr_tail_buf)
                detail = f"FFmpeg timed out after {overall_timeout}s"
                return False, f"{detail}\n{tail}".strip()

        stderr_thread.join(timeout=10)

        if return_code != 0:
            tail = _stderr_tail(stderr_tail_buf)
            logger.error(f"FFmpeg failed with return code {return_code}")
            logger.error(f"Error output: {tail}")
            report_progress(
                progress_callback, 0, f"FFmpeg failed with error code {return_code}"
            )
            detail = f"FFmpeg failed with exit code {return_code}"
            return False, f"{detail}\n{tail}".strip()

        # Verify output file exists and is not empty
        if not os.path.exists(output_mp4_path):
            logger.error(f"Output file not created: {output_mp4_path}")
            report_progress(progress_callback, 0, "Output file not created")
            tail = _stderr_tail(stderr_tail_buf)
            detail = f"FFmpeg reported success but no output file was created at {output_mp4_path}"
            return False, f"{detail}\n{tail}".strip()

        if os.path.getsize(output_mp4_path) == 0:
            logger.error(f"Output file is empty: {output_mp4_path}")
            report_progress(progress_callback, 0, "Output file is empty")
            tail = _stderr_tail(stderr_tail_buf)
            detail = f"FFmpeg produced a zero-byte output file at {output_mp4_path}"
            return False, f"{detail}\n{tail}".strip()

        # Success
        report_progress(progress_callback, 98, "MP4 generation complete!")

        logger.info(f"MP4 successfully generated: {output_mp4_path}")
        return True, ""

    except CancellationError:
        raise
    except Exception as e:
        logger.error(f"Error generating MP4: {e}")
        report_progress(progress_callback, 0, f"Error: {str(e)}")
        return False, f"Unexpected error during MP4 generation: {e}"

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

        # Use the SAME username rule as the gallery's path builder
        # (core.utils.is_valid_username allows dots). The old sanitizer
        # replaced dots with underscores, so "christophe.leyder" MP4s landed
        # in "christophe_leyder" — a folder the gallery never displays —
        # while the log still reported "successfully added".
        from core.utils import is_valid_username
        safe_user = (user or "").strip() or "standalone"
        if not is_valid_username(safe_user):
            # Fallback sanitize for genuinely unsafe names — keep dots
            safe_user = re.sub(r'[^\w.\-]', '_', safe_user)

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
