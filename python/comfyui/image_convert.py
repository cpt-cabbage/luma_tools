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


def _source_has_alpha(source_path: str) -> bool:
    """Probe an image for an alpha channel via `oiiotool --info -v`.

    Returns False on any failure — a missing alpha is the safe assumption,
    since requesting a channel OIIO can't supply fails the whole conversion.
    """
    if not OIIO_PATH:
        return False
    try:
        result = run_command([OIIO_PATH, "--info", "-v", source_path], timeout=30)
    except Exception as e:
        logger.debug(f"[convert] Could not probe channels for {source_path}: {e}")
        return False
    if result.returncode != 0:
        return False

    for line in result.stdout.splitlines():
        if "channel list:" not in line.lower():
            continue
        channels = line.split(":", 1)[1]
        # Channel names may be layer-qualified (e.g. "rgba.A") — compare the leaf
        for chan in channels.split(","):
            leaf = chan.strip().split(".")[-1].split(" ")[0]
            if leaf.upper() == "A":
                return True
        return False
    return False


@safe_operation("convert_to_png", return_on_error=None)
def convert_to_png(
    source_path: str,
    output_dir: str,
    apply_colorspace: bool = True,
) -> Optional[str]:
    """Convert an image to PNG using OIIO.

    Alpha is preserved when the source has it. This matters for nodes that
    consume transparency (Trellis2LoadImageWithTransparency and friends) —
    silently flattening to RGB there produces a valid-looking but wrong result.

    Args:
        source_path: Full path to the source image.
        output_dir: Directory to write the converted PNG.
        apply_colorspace: If True, applies ACES→sRGB via OCIO (with gamma fallback).
            If False, does simple format conversion with channel selection only.

    Returns:
        Path to the converted PNG, or None on failure.
    """
    if not OIIO_PATH:
        logger.warning("OIIO not available — cannot convert image, copying as-is")
        return None

    basename = os.path.basename(source_path)
    png_basename = get_png_basename(basename)
    output_path = os.path.join(output_dir, png_basename)

    has_alpha = _source_has_alpha(source_path)

    oiio_cmd = [OIIO_PATH, source_path]

    if apply_colorspace:
        ocio_config = get_ocio_config()
        if ocio_config and os.path.exists(ocio_config):
            # unpremult so the transform runs on straight (un-associated) color;
            # OIIO re-premultiplies afterwards. Without this, ACES→sRGB on a
            # premultiplied source darkens the edges of anything semi-transparent.
            if has_alpha:
                oiio_cmd.extend(["--colorconvert:unpremult=1", "ACES - ACEScg", "sRGB"])
            else:
                oiio_cmd.extend(["--colorconvert", "ACES - ACEScg", "sRGB"])
            logger.info(f"Converting {basename} with OCIO ACES→sRGB")
        else:
            # --powc applies per channel; leave alpha linear (exponent 1.0)
            oiio_cmd.extend(["--powc", "0.4545,0.4545,0.4545,1.0" if has_alpha else "0.4545"])
            logger.info(f"Converting {basename} with gamma 2.2 fallback (OCIO not available)")
    else:
        logger.info(f"Converting {basename} (format only, no colorspace)")

    # Select output channels — keep alpha when the source carries it
    oiio_cmd.extend(["--ch", "R,G,B,A" if has_alpha else "R,G,B"])
    oiio_cmd.extend(["-o", output_path])

    result = run_command(oiio_cmd, timeout=60)

    if result.returncode != 0:
        logger.error(f"OIIO conversion failed for {basename}: {result.stderr}")
        return None

    logger.info(
        f"Converted {basename} → {png_basename}"
        f"{' (alpha preserved)' if has_alpha else ''}"
    )
    return output_path


def copy_or_convert(
    source_path: str,
    dest_dir: str,
    apply_colorspace: bool = True,
) -> Optional[str]:
    """Copy a file to dest_dir, converting to PNG if needed.

    High-level helper: if the file needs conversion, converts to dest_dir.
    Otherwise copies as-is.

    Returns None when a *required* conversion fails. Callers must treat that as
    fatal: by the time this runs, the workflow's input has already been
    rewritten to `<name>.png` by the modifier, so falling back to copying the
    original .exr would produce a job that dies on the farm minutes later with
    a missing-file error naming a PNG nobody ever tried to write.

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

    basename = os.path.basename(source_path)

    if needs_conversion(source_path):
        converted = convert_to_png(source_path, dest_dir, apply_colorspace=apply_colorspace)
        if converted:
            return converted
        logger.error(
            f"Conversion to PNG failed for {basename}. The workflow already "
            f"references {get_png_basename(basename)}, so this input cannot be "
            f"satisfied — fix the source file or OIIO setup and resubmit."
        )
        return None

    ext = os.path.splitext(source_path)[1].lower()
    if ext not in COMFYUI_NATIVE_FORMATS:
        # Neither natively loadable nor something OIIO is set up to convert.
        # Copy it anyway (a custom node may handle it) but say so up front,
        # because the usual outcome is a load failure on the farm.
        logger.warning(
            f"'{ext}' is not a ComfyUI-native format and has no conversion rule; "
            f"copying {basename} unchanged — the workflow may fail to load it."
        )

    # Native format — plain copy
    dest_path = os.path.join(dest_dir, basename)
    if not os.path.exists(dest_path) or os.path.getmtime(source_path) > os.path.getmtime(dest_path):
        shutil.copy2(source_path, dest_path)
    return dest_path
