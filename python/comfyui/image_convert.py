"""
Image format conversion for ComfyUI workflows.

Converts unsupported image formats (EXR, HDR, DPX, TGA) to PNG using OIIO
before submission, with optional ACES→sRGB color management.
"""

import os
import shutil
import logging
from typing import Optional

from core.config import OIIO_PATH, get_ocio_config
from core.error_handling import safe_operation
from core.subprocess_utils import run_command

logger = logging.getLogger(__name__)

# Formats that ComfyUI/PIL can load natively — no conversion needed
COMFYUI_NATIVE_FORMATS = {'.png', '.jpg', '.jpeg', '.gif', '.tiff', '.tif', '.bmp', '.webp'}

# Formats that OIIO can convert to PNG for ComfyUI consumption
OIIO_CONVERTIBLE_FORMATS = {'.exr', '.hdr', '.dpx', '.tga'}


def needs_conversion(file_path: str) -> bool:
    """Check if a file needs conversion to PNG for ComfyUI.

    Args:
        file_path: Path to the image file.

    Returns:
        True if the file's extension is in OIIO_CONVERTIBLE_FORMATS.
    """
    ext = os.path.splitext(file_path)[1].lower()
    return ext in OIIO_CONVERTIBLE_FORMATS


def get_png_basename(basename: str) -> str:
    """Return basename with .png extension.

    Args:
        basename: Original filename (e.g. "render.exr").

    Returns:
        Filename with .png extension (e.g. "render.png").
    """
    name, _ = os.path.splitext(basename)
    return f"{name}.png"


@safe_operation("convert_to_png", return_on_error=None)
def convert_to_png(
    source_path: str,
    output_dir: str,
    apply_colorspace: bool = True,
) -> Optional[str]:
    """Convert an image to PNG using OIIO.

    Args:
        source_path: Full path to the source image.
        output_dir: Directory to write the converted PNG.
        apply_colorspace: If True, applies ACES→sRGB via OCIO (with gamma fallback).
            If False, does simple format conversion with channel stripping only.

    Returns:
        Path to the converted PNG, or None on failure.
    """
    if not OIIO_PATH:
        logger.warning("OIIO not available — cannot convert image, copying as-is")
        return None

    basename = os.path.basename(source_path)
    png_basename = get_png_basename(basename)
    output_path = os.path.join(output_dir, png_basename)

    oiio_cmd = [OIIO_PATH, source_path]

    if apply_colorspace:
        ocio_config = get_ocio_config()
        if ocio_config and os.path.exists(ocio_config):
            oiio_cmd.extend(["--colorconvert", "ACES - ACEScg", "sRGB"])
            logger.info(f"Converting {basename} with OCIO ACES→sRGB")
        else:
            oiio_cmd.extend(["--powc", "0.4545"])
            logger.info(f"Converting {basename} with gamma 2.2 fallback (OCIO not available)")
    else:
        logger.info(f"Converting {basename} (format only, no colorspace)")

    # Strip alpha channel for clean PNG output
    oiio_cmd.extend(["--ch", "R,G,B"])
    oiio_cmd.extend(["-o", output_path])

    result = run_command(oiio_cmd, timeout=60)

    if result.returncode != 0:
        logger.error(f"OIIO conversion failed for {basename}: {result.stderr}")
        return None

    logger.info(f"Converted {basename} → {png_basename}")
    return output_path


def copy_or_convert(
    source_path: str,
    dest_dir: str,
    apply_colorspace: bool = True,
) -> Optional[str]:
    """Copy a file to dest_dir, converting to PNG if needed.

    High-level helper: if the file needs conversion, converts to dest_dir.
    Otherwise copies as-is.

    Args:
        source_path: Full path to the source file.
        dest_dir: Destination directory.
        apply_colorspace: Passed to convert_to_png() when conversion is needed.

    Returns:
        Path to the destination file, or None on failure.
    """
    if not os.path.exists(source_path):
        logger.warning(f"Source file not found: {source_path}")
        return None

    if needs_conversion(source_path):
        converted = convert_to_png(source_path, dest_dir, apply_colorspace=apply_colorspace)
        if converted:
            return converted
        # Fallback: copy original if conversion failed
        logger.warning(f"Conversion failed, copying original: {os.path.basename(source_path)}")

    # Native format or conversion fallback — plain copy
    basename = os.path.basename(source_path)
    dest_path = os.path.join(dest_dir, basename)
    if not os.path.exists(dest_path) or os.path.getmtime(source_path) > os.path.getmtime(dest_path):
        shutil.copy2(source_path, dest_path)
    return dest_path
