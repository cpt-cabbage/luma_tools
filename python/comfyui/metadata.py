"""
Gallery Metadata and Output File Management Module.

Handles:
- Gallery metadata storage and retrieval
- Output file scanning and cleanup
- Job metadata tracking for generated images
- User notes and annotations
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

# Farm isolation: this module must import on workers where the `core` package
# is not available (it's copied to a flat _job_data dir as `comfyui_metadata.py`).
# Provide fallbacks for the two core symbols we use.
try:
    from core.config import COMFYUI_OUTPUT_EXTENSIONS
except ImportError:
    # Mirror of core.config.COMFYUI_OUTPUT_EXTENSIONS for farm-isolated execution
    COMFYUI_OUTPUT_EXTENSIONS = [
        ".png", ".jpg", ".jpeg", ".webp", ".exr", ".tiff", ".tif", ".bmp", ".gif",
        ".fbx", ".obj", ".gltf", ".glb", ".usd", ".usda", ".usdc", ".usdz",
        ".mp4", ".mov", ".avi", ".webm",
        ".wav", ".mp3", ".flac", ".ogg",
        ".npy", ".npz", ".safetensors", ".pt", ".pth", ".ckpt", ".bin",
    ]

try:
    from core.utils import ensure_directory
except ImportError:
    def ensure_directory(path):
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

# The metadata file abstraction is farm-copied alongside this module as
# `comfyui_metadata_file.py` (see deadline/submitter.py), so farm workers get
# the same locked, atomic implementation the workstation uses. Without this
# fallback, farm metadata writes fail with ImportError and are silently lost.
try:
    from core.metadata_file import get_metadata_file, clear_metadata_file_cache
except ImportError:
    from comfyui_metadata_file import get_metadata_file, clear_metadata_file_cache

logger = logging.getLogger(__name__)


# ============================================================================
# OUTPUT FILE MANAGEMENT
# ============================================================================

def get_job_output_files(
    output_dir: str,
    job_prefix: Optional[str] = None,
    min_mtime: Optional[float] = None
) -> List[str]:
    """Get the output files from a job's output directory.

    Args:
        output_dir: Directory to scan for output files
        job_prefix: Optional job prefix to filter files (e.g., 'sh0010_luma_tools_myimage')
                   If provided, only returns files whose names start with this prefix.
        min_mtime: Optional minimum modification time (Unix timestamp).
                   If provided, only returns files modified after this time.

    Returns:
        List of file paths, sorted by modification time (newest first)
    """
    if not output_dir or not os.path.isdir(output_dir):
        return []

    supported_extensions = set(COMFYUI_OUTPUT_EXTENSIONS)
    files = []

    # Use os.scandir() for better performance - stat info is cached
    try:
        with os.scandir(output_dir) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                ext = os.path.splitext(entry.name)[1].lower()
                if ext not in supported_extensions:
                    continue
                # Filter by job prefix if provided
                if job_prefix and not entry.name.startswith(job_prefix):
                    continue
                # Get mtime from cached stat (no extra syscall)
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue  # Skip files that can't be stat'd
                # Filter by minimum modification time if provided
                if min_mtime is not None and mtime < min_mtime:
                    continue
                files.append((entry.path, mtime))
    except OSError as e:
        logger.warning(f"Error scanning directory {output_dir}: {e}")
        return []

    files.sort(key=lambda x: x[1], reverse=True)
    return [f[0] for f in files]


def cleanup_job_temp_files(output_dir: str) -> int:
    """Clean up temporary job files from the output directory.

    Cleans up:
    - Old _job_data/<job_id>/ subdirectories (older than 1 hour, safe from
      concurrent submissions since each job gets its own unique subdirectory)
    - Legacy root-level temp files from old job format
    """
    import glob
    import shutil
    import time

    if not output_dir or not os.path.exists(output_dir):
        return 0

    deleted_count = 0
    max_age_seconds = 3600  # 1 hour

    # Clean up old _job_data/<job_id>/ subdirectories
    job_data_dir = os.path.join(output_dir, "_job_data")
    if os.path.isdir(job_data_dir):
        now = time.time()
        try:
            for entry in os.scandir(job_data_dir):
                if entry.is_dir():
                    try:
                        age = now - entry.stat().st_mtime
                        if age > max_age_seconds:
                            shutil.rmtree(entry.path)
                            deleted_count += 1
                            logger.debug(f"Cleaned up old job data: {entry.name}")
                    except Exception as e:
                        logger.debug(f"Could not clean up {entry.name}: {e}")
        except OSError as e:
            logger.debug(f"Could not scan for old job data: {e}")

        # Remove _job_data/ parent if empty
        try:
            if not any(os.scandir(job_data_dir)):
                os.rmdir(job_data_dir)
        except OSError:
            pass

    # Backward compat: clean up root-level files from old jobs
    # (comfyui_client.py is from a long-removed module; leave the pattern so
    # legacy jobs still get tidied)
    temp_patterns = [
        "comfyui_workflow*.json",
        "comfyui_seeds.json",
        "comfyui_runner.py",
        "comfyui_client.py",
        "comfyui_utils.py",
        "comfyui_analytics.py",
        "comfyui_job_info.txt",
        "comfyui_plugin_info.txt",
    ]

    for pattern in temp_patterns:
        for file_path in glob.glob(os.path.join(output_dir, pattern)):
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception as e:
                logger.debug(f"Could not remove temp file {file_path}: {e}")

    return deleted_count


# ============================================================================
# GALLERY METADATA
# ============================================================================

GALLERY_METADATA_FILE = "comfyui_gallery_metadata.json"


def _validate_output_dir(output_dir: str) -> bool:
    """Validate output_dir is a valid path string."""
    if not isinstance(output_dir, (str, os.PathLike)):
        logger.error(f"[Metadata] Invalid output_dir type: {type(output_dir).__name__} (expected str or PathLike)")
        return False
    return True


def _get_gallery_metadata_file(output_dir: str):
    """Get MetadataFile instance for gallery metadata (uses centralized caching)."""
    return get_metadata_file(output_dir, GALLERY_METADATA_FILE)


def clear_gallery_metadata_cache(output_dir: str = None) -> None:
    """Clear the gallery metadata cache. Thread-safe."""
    if output_dir:
        clear_metadata_file_cache(output_dir, GALLERY_METADATA_FILE)
    else:
        # Clear all gallery metadata caches
        clear_metadata_file_cache()


def load_gallery_metadata(output_dir: str, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
    """Load gallery metadata from the output directory.

    Thread-safe via MetadataFile. Uses mtime-based cache invalidation.

    Returns:
        Dict with metadata, or empty dict if file missing/corrupted
    """
    if not output_dir or not _validate_output_dir(output_dir):
        return {}

    try:
        metadata_file = _get_gallery_metadata_file(output_dir)
        return metadata_file.load(default={}, use_cache=use_cache)
    except Exception as e:
        logger.error(f"[Metadata] Error loading gallery metadata from {output_dir}: {e}")
        return {}


def save_gallery_metadata(output_dir: str, metadata: Dict[str, Dict[str, Any]]) -> bool:
    """Save gallery metadata to the output directory (atomic write)."""
    if not output_dir or not _validate_output_dir(output_dir):
        return False

    try:
        metadata_file = _get_gallery_metadata_file(output_dir)
        return metadata_file.save(metadata)
    except Exception as e:
        logger.error(f"[Metadata] Error saving gallery metadata: {e}")
        return False


def mutate_gallery_metadata(output_dir: str, mutator) -> bool:
    """Atomically load-modify-save gallery metadata.

    Safe against concurrent writers in other threads AND other processes
    (farm workers writing the same file over the network). Prefer this over
    load_gallery_metadata() + save_gallery_metadata() for any read-modify-write.

    Args:
        output_dir: Directory containing the metadata file
        mutator: Callable that mutates the metadata dict in place

    Returns:
        bool: True if saved successfully
    """
    if not output_dir or not _validate_output_dir(output_dir):
        return False

    try:
        metadata_file = _get_gallery_metadata_file(output_dir)
        return metadata_file.mutate(mutator)
    except Exception as e:
        logger.error(f"[Metadata] Error mutating gallery metadata: {e}")
        return False


def add_item_metadata(
    output_dir: str,
    output_prefix: str,
    prompt: Optional[str] = None,
    workflow_name: Optional[str] = None,
    input_image: Optional[str] = None,
    generation_count: int = 1,
    base_seed: Optional[int] = None,
    workflow_preset: Optional[str] = None,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None,
    output_type: Optional[str] = None,
    source_image_hashes: Optional[Dict[str, str]] = None,
    custom_name: Optional[str] = None,
) -> bool:
    """Add metadata for items that will be generated with a given prefix.

    Enhanced to store:
    - is_output: True (marks as generated output)
    - job_prefix: Grouping key for gallery stacking
    - source_images: All input images used in generation
    - source_models: All 3D models used as inputs
    - output_type: Type of output (image, video, 3d, audio, other)

    Args:
        output_dir: Directory where outputs are saved
        output_prefix: Prefix used for output filenames
        prompt: Text prompt used for generation
        workflow_name: Name of the workflow file
        input_image: Primary input image (deprecated, use editable_values)
        generation_count: Number of generations in this job
        base_seed: Base seed used for generation
        workflow_preset: Name of the workflow preset used
        editable_values: Dict of editable node values
        output_type: Type of output (image, video, 3d, audio, other)
        source_image_hashes: Dict of basename -> sha256 hash for source files

    Returns:
        bool: True if metadata saved successfully, False otherwise
    """
    # Extract all source images and models from editable values
    source_images = []
    source_models = []

    # Helper to safely extract basename
    def safe_basename(path):
        try:
            return os.path.basename(path) if path else None
        except (TypeError, AttributeError):
            return None

    if input_image:
        basename = safe_basename(input_image)
        if basename:
            source_images.append(basename)

    serialized_editable = {}
    if editable_values:
        for node_id, entries in editable_values.items():
            entry_list = entries if isinstance(entries, list) else [entries]
            for data in entry_list:
                if not isinstance(data, dict):
                    continue

                node_info = data.get('node')
                value = data.get('value')

                # Safely get widget_type
                widget_type = None
                if node_info and hasattr(node_info, 'widget_type'):
                    widget_type = node_info.widget_type

                widget_name = getattr(node_info, 'widget_name', '') if node_info else ''

                # Collect source files
                if widget_type == 'image':
                    # Don't serialize image widgets, but collect their paths
                    try:
                        if isinstance(value, list):
                            for v in value:
                                basename = safe_basename(v)
                                if basename:
                                    source_images.append(basename)
                        elif value:
                            basename = safe_basename(value)
                            if basename:
                                source_images.append(basename)
                    except Exception as e:
                        logger.error(f"[Metadata] Error extracting image paths: {e}")
                    continue
                elif widget_type == '3d_model':
                    # Collect 3D model paths
                    try:
                        if isinstance(value, list):
                            for v in value:
                                basename = safe_basename(v)
                                if basename:
                                    source_models.append(basename)
                        elif value:
                            basename = safe_basename(value)
                            if basename:
                                source_models.append(basename)
                    except Exception as e:
                        logger.error(f"[Metadata] Error extracting model paths: {e}")

                # Serialize editable value (use node_id:widget_name for uniqueness)
                serial_key = f"{node_id}:{widget_name}" if widget_name else str(node_id)
                try:
                    serialized_editable[serial_key] = {
                        "node_id": getattr(node_info, 'node_id', node_id) if node_info else node_id,
                        "display_name": getattr(node_info, 'display_name', "") if node_info else "",
                        "node_type": getattr(node_info, 'node_type', "") if node_info else "",
                        "widget_type": widget_type or "text",
                        "widget_name": widget_name,
                        "value": value,
                    }
                except Exception as e:
                    logger.error(f"[Metadata] Error serializing editable value for node {node_id}: {e}")

    # Deduplicate source lists while preserving order
    try:
        source_images = list(dict.fromkeys(source_images))  # Remove dupes, keep order
        source_models = list(dict.fromkeys(source_models))
    except Exception as e:
        logger.error(f"[Metadata] Error deduplicating sources: {e}")

    prefix_key = output_prefix.rstrip('_') if output_prefix else "unknown"

    try:
        entry = {
            "prompt": prompt,
            "workflow": workflow_name,
            "workflow_preset": workflow_preset or "",
            "input_image": safe_basename(input_image),  # Keep for backward compat
            "timestamp": datetime.now().isoformat(),
            "generation_count": generation_count,
            "base_seed": base_seed,
            "editable_values": serialized_editable if serialized_editable else None,
            # New fields for enhanced detection
            "is_output": True,  # Explicitly mark as generated output
            "job_prefix": prefix_key,  # Store grouping key
            "source_images": source_images if source_images else None,  # All input images
            "source_models": source_models if source_models else None,  # All 3D model inputs
            "output_type": output_type,  # Type of output (image, video, 3d, audio, other)
            "source_image_hashes": source_image_hashes if source_image_hashes else None,
            "custom_name": custom_name if custom_name else None,
        }

        def _apply(metadata):
            metadata[f"_prefix_{prefix_key}"] = entry

            # Also mark source images as inputs explicitly
            # This ensures input files are correctly identified even if they have
            # filenames that look like outputs (e.g., with _001 suffix)
            for source_image in source_images:
                input_key = f"_input_{source_image}"
                content_hash = source_image_hashes.get(source_image) if source_image_hashes else None
                if input_key not in metadata:
                    input_entry = {
                        "is_output": False,
                        "is_input": True,
                        "used_by_job": prefix_key,
                        "timestamp": datetime.now().isoformat(),
                    }
                    if content_hash:
                        input_entry["content_hash"] = content_hash
                    metadata[input_key] = input_entry

                # Create hash index entry for reverse lookup
                if content_hash:
                    hash_key = f"_hash_{content_hash}"
                    if hash_key not in metadata:
                        metadata[hash_key] = {
                            "filename": source_image,
                            "job_prefix": prefix_key,
                            "is_input": True,
                        }

            # Same for source models
            for source_model in source_models:
                input_key = f"_input_{source_model}"
                if input_key not in metadata:
                    metadata[input_key] = {
                        "is_output": False,
                        "is_input": True,
                        "used_by_job": prefix_key,
                        "timestamp": datetime.now().isoformat(),
                    }

        return mutate_gallery_metadata(output_dir, _apply)
    except Exception as e:
        logger.error(f"[Metadata] Error saving metadata: {e}")
        return False


def get_item_metadata(
    output_dir: str,
    filename: str,
    allow_reverse_match: bool = True,
    content_hash: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific gallery item (image, video, model, etc.).

    Args:
        output_dir: Directory containing the metadata file
        filename: Filename to look up
        allow_reverse_match: If True (default), also match when job prefix ends with
            the filename. This is useful for display/recreate purposes. Set to False
            when determining input/output status to avoid matching input files to
            output job metadata.
        content_hash: Optional SHA-256 hash for hash-based fallback lookup

    Returns:
        Metadata dict for the file, or None if not found
    """
    metadata = load_gallery_metadata(output_dir)
    return _lookup_file_metadata(
        metadata, filename,
        allow_reverse_match=allow_reverse_match,
        content_hash=content_hash,
    )


def _lookup_file_metadata(
    metadata: Dict[str, Dict[str, Any]],
    filename: str,
    allow_reverse_match: bool = False,
    content_hash: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Internal helper to look up metadata for a filename.

    Looks up by exact filename first, then by prefix match,
    then by content hash if provided.

    Args:
        metadata: Gallery metadata dict
        filename: Filename to look up
        allow_reverse_match: If True, also match when prefix ends with basename.
            This is useful for recreate settings but should be False for
            input/output detection to avoid matching input files to output metadata.
        content_hash: Optional SHA-256 hash for hash-based fallback lookup

    Returns:
        Metadata dict for the file, or None if not found
    """
    # Validate inputs
    if not isinstance(metadata, dict):
        return None
    if not filename or not isinstance(filename, str):
        return None

    # Try exact filename match first
    if filename in metadata:
        result = metadata[filename]
        if isinstance(result, dict):
            return result

    # Check for explicit input file entry (highest priority for input detection)
    # These are created when source images are used in jobs
    input_key = f"_input_{filename}"
    if input_key in metadata:
        result = metadata[input_key]
        if isinstance(result, dict):
            return result

    # Try prefix matching
    try:
        basename = os.path.splitext(filename)[0]
    except Exception as e:
        logger.debug(f"Could not extract basename from {filename}: {e}")
        return None

    # Look for matching prefix entries (for output files)
    # Use longest-prefix-wins to avoid short prefixes (e.g. "LumaRND_luma_tools")
    # incorrectly matching files that belong to a more specific prefix
    # (e.g. "LumaRND_luma_tools_Screenshot 2025-06-06 083801")
    try:
        # Longest-prefix-wins, done as direct lookups instead of a sweep over
        # every metadata key. Scanning a directory calls this once (often twice)
        # per file, so the old sweep made a scan O(files x metadata entries) —
        # ~5 s for 2500 files whose names don't share a job prefix. Testing each
        # prefix of the basename is O(len(basename)) dict hits and yields the
        # same match: the longest key of the form "_prefix_<p>" where the
        # basename starts with p.
        for length in range(len(basename), -1, -1):
            candidate = metadata.get(f"_prefix_{basename[:length]}")
            if isinstance(candidate, dict):
                return candidate

        # Reverse match: prefix ends with basename (for recreate settings only)
        # e.g., prefix="luma_tools_job_filename" matches basename="filename"
        # IMPORTANT: Only use this when explicitly requested, otherwise input
        # files may incorrectly match output job metadata
        if allow_reverse_match:
            for key, value in metadata.items():
                if not isinstance(key, str) or not key.startswith("_prefix_"):
                    continue
                if not isinstance(value, dict):
                    continue

                prefix = key[8:]
                if prefix.endswith(basename) or prefix.endswith(f"_{basename}"):
                    return value
    except Exception as e:
        logger.error(f"[Metadata] Error during prefix lookup for {filename}: {e}")

    # Hash-based fallback: look up by content hash if provided
    if content_hash:
        hash_key = f"_hash_{content_hash}"
        hash_entry = metadata.get(hash_key)
        if isinstance(hash_entry, dict):
            # Follow the reference to get the job's _prefix_ entry
            job_prefix = hash_entry.get("job_prefix")
            if job_prefix:
                prefix_entry = metadata.get(f"_prefix_{job_prefix}")
                if isinstance(prefix_entry, dict):
                    logger.info(f"[Metadata] Found metadata via hash lookup for {filename}")
                    return prefix_entry
            # Return hash entry itself as minimal metadata
            return hash_entry

    return None


def get_workflow_preset_for_files(output_dir: str, filenames: List[str]) -> Dict[str, str]:
    """Get workflow preset names for multiple files efficiently."""
    metadata = load_gallery_metadata(output_dir)
    results = {}

    for filename in filenames:
        file_metadata = _lookup_file_metadata(metadata, filename)
        if file_metadata:
            results[filename] = file_metadata.get('workflow_preset', '') or ''
        else:
            results[filename] = ''

    return results


def collect_known_input_files(metadata: Dict[str, Any]) -> tuple:
    """Collect all known input file basenames from an already-loaded metadata dict.

    One pass over the metadata instead of a linear scan per candidate file.

    Args:
        metadata: Already-loaded gallery metadata dict

    Returns:
        tuple: (explicit_inputs, source_name_to_job) where:
            - explicit_inputs: set of filenames that have an _input_ entry
            - source_name_to_job: dict of filename -> job_prefix for files that
              appear in any job's source_images/source_models but have no
              explicit _input_ entry yet (candidates for lazy migration)
    """
    explicit_inputs = set()
    source_name_to_job = {}

    if not isinstance(metadata, dict):
        return explicit_inputs, source_name_to_job

    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        if key.startswith("_input_"):
            explicit_inputs.add(key[7:])  # Remove "_input_" prefix
        elif key.startswith("_prefix_") and isinstance(value, dict):
            job_prefix = value.get('job_prefix', key[8:])
            for name in (value.get('source_images') or []):
                if isinstance(name, str):
                    source_name_to_job.setdefault(name, job_prefix)
            for name in (value.get('source_models') or []):
                if isinstance(name, str):
                    source_name_to_job.setdefault(name, job_prefix)

    # Files already marked explicitly need no migration
    for name in explicit_inputs:
        source_name_to_job.pop(name, None)

    return explicit_inputs, source_name_to_job


def is_known_input_file(output_dir: str, filename: str) -> bool:
    """Check if a file is known to be an input file (used as source in any job).

    This is a reliable way to identify input files even if they have filenames
    that look like outputs (e.g., with sequence numbers).

    Args:
        output_dir: Directory containing the metadata file
        filename: Filename to check

    Returns:
        True if the file is listed as a source_image or source_model in any job
    """
    metadata = load_gallery_metadata(output_dir)

    explicit_inputs, source_name_to_job = collect_known_input_files(metadata)

    if filename in explicit_inputs:
        return True

    if filename in source_name_to_job:
        # Mark it for future lookups (lazy migration)
        mark_as_input_file(output_dir, filename, source_name_to_job[filename])
        return True

    return False


def mark_input_files_batch(output_dir: str, filename_to_job: Dict[str, Optional[str]]) -> bool:
    """Mark multiple files as input files in a single locked metadata write.

    Batch variant of mark_as_input_file() — use this when a directory scan
    discovers several unmarked input files, so the (network) metadata file is
    locked and written once instead of once per file.

    Args:
        output_dir: Directory containing the metadata file
        filename_to_job: Mapping of filename -> job prefix that used it (or None)

    Returns:
        True if successfully marked (or nothing to mark)
    """
    if not filename_to_job:
        return True

    try:
        def _apply(data):
            for filename, used_by_job in filename_to_job.items():
                input_key = f"_input_{filename}"
                if input_key not in data:
                    data[input_key] = {
                        "is_output": False,
                        "is_input": True,
                        "used_by_job": used_by_job,
                        "timestamp": datetime.now().isoformat(),
                    }

        return mutate_gallery_metadata(output_dir, _apply)
    except Exception as e:
        logger.error(f"[Metadata] Error batch-marking input files: {e}")
        return False


def mark_as_input_file(output_dir: str, filename: str, used_by_job: str = None) -> bool:
    """Explicitly mark a file as an input file.

    Args:
        output_dir: Directory containing the metadata file
        filename: Filename to mark as input
        used_by_job: Optional job prefix that used this file

    Returns:
        True if successfully marked
    """
    try:
        metadata = load_gallery_metadata(output_dir)
        input_key = f"_input_{filename}"

        if input_key in metadata:
            return True  # Already marked

        def _apply(data):
            if input_key not in data:
                data[input_key] = {
                    "is_output": False,
                    "is_input": True,
                    "used_by_job": used_by_job,
                    "timestamp": datetime.now().isoformat(),
                }

        return mutate_gallery_metadata(output_dir, _apply)
    except Exception as e:
        logger.error(f"[Metadata] Error marking {filename} as input: {e}")
        return False


def add_mp4_maker_metadata(
    output_dir: str,
    filename: str,
    shot: str,
    source_render: str,
    source_path: str,
    frame_range: tuple,
    quality_setting: str,
    burn_in_timecode: bool,
) -> bool:
    """Store metadata for an MP4 Maker output in the gallery.

    Creates a dedicated metadata entry for MP4 files generated by the MP4 Maker tab,
    distinct from ComfyUI-generated outputs.

    Args:
        output_dir: Directory containing the MP4 file (gallery output dir)
        filename: MP4 filename (e.g., 'sh0010_diffuse_combined.mp4')
        shot: Shot name or 'standalone' if no shot context
        source_render: Name of the source render sequence
        source_path: Full path to the source EXR sequence pattern
        frame_range: Tuple of (start_frame, end_frame)
        quality_setting: Quality description (e.g., 'High (CRF 18)')
        burn_in_timecode: Whether timecode was burned into the video

    Returns:
        bool: True if metadata saved successfully, False otherwise
    """
    # Use basename without extension as key
    basename = os.path.splitext(filename)[0]
    mp4_key = f"_mp4maker_{basename}"

    entry = {
        "is_output": True,
        "source_type": "mp4_maker",
        "source_render": source_render,
        "source_path": source_path,
        "frame_range": list(frame_range) if frame_range else None,
        "quality_setting": quality_setting,
        "burn_in_timecode": burn_in_timecode,
        "shot": shot or "standalone",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        def _apply(metadata):
            metadata[mp4_key] = entry

        return mutate_gallery_metadata(output_dir, _apply)
    except Exception as e:
        logger.error(f"[Metadata] Error saving MP4 Maker metadata: {e}")
        return False


def extract_prompts_from_editable_values(
    editable_values: Optional[Dict[int, list]]
) -> str:
    """Extract prompt text from editable values dictionary."""
    if not editable_values:
        return ""

    prompts = []
    for entries in editable_values.values():
        entry_list = entries if isinstance(entries, list) else [entries]
        for data in entry_list:
            node_info = data.get('node')
            value = data.get('value')
            if node_info and node_info.widget_type == 'text' and value:
                prompts.append(str(value).strip())

    return "\n---\n".join(prompts) if prompts else ""


def get_model_note(output_dir: str, filename: str) -> str:
    """Get the user note for a specific model file."""
    metadata = load_gallery_metadata(output_dir)
    basename = os.path.splitext(filename)[0]
    note_key = f"_note_{basename}"
    return metadata.get(note_key, "")


def set_model_note(output_dir: str, filename: str, note: str) -> bool:
    """Set a user note for a specific model file."""
    basename = os.path.splitext(filename)[0]
    note_key = f"_note_{basename}"

    def _apply(metadata):
        if note.strip():
            metadata[note_key] = note.strip()
        elif note_key in metadata:
            del metadata[note_key]

    return mutate_gallery_metadata(output_dir, _apply)


# ============================================================================
# PER-FILE METADATA (Phase 2 Enhancement)
# ============================================================================

def add_per_file_metadata(
    output_dir: str,
    filename: str,
    file_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    job_id: Optional[str] = None,
    frame_index: Optional[int] = None,
    actual_seed: Optional[int] = None,
    execution_time_ms: Optional[int] = None,
    node_execution_trace: Optional[list] = None,
    error: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> bool:
    """Store per-file metadata for enhanced traceability.

    This provides granular metadata per output file, complementing the
    job-level metadata stored via add_item_metadata().

    Args:
        output_dir: Directory containing the file
        filename: The output filename
        file_id: Unique identifier for this file (UUID, auto-generated if None)
        parent_id: UUID of parent/source file (for iteration lineage)
        job_id: Deadline job ID
        frame_index: Frame number within the job
        actual_seed: The exact seed used for this file (not base seed)
        execution_time_ms: Total execution time in milliseconds
        node_execution_trace: List of dicts with node_id, name, duration_ms
        error: Error message if generation failed
        content_hash: SHA-256 hash of the file content

    Returns:
        bool: True if saved successfully
    """
    import uuid

    # Generate file_id if not provided
    if file_id is None:
        file_id = str(uuid.uuid4())

    # Create per-file entry with _file_ prefix
    basename = os.path.splitext(filename)[0]
    file_key = f"_file_{basename}"

    entry = {
        "file_id": file_id,
        "parent_id": parent_id,
        "job_id": job_id,
        "frame_index": frame_index,
        "actual_seed": actual_seed,
        "execution_time_ms": execution_time_ms,
        "node_execution_trace": node_execution_trace,
        "error": error,
        "content_hash": content_hash,
        "timestamp": datetime.now().isoformat(),
    }

    # Remove None values to keep JSON clean
    entry = {k: v for k, v in entry.items() if v is not None}

    def _apply(metadata):
        metadata[file_key] = entry

        # Create hash index entry for reverse lookup
        if content_hash:
            hash_key = f"_hash_{content_hash}"
            if hash_key not in metadata:
                metadata[hash_key] = {
                    "filename": filename,
                    "job_prefix": None,  # Output file, not tied to a specific job prefix
                    "is_input": False,
                }

    try:
        return mutate_gallery_metadata(output_dir, _apply)
    except Exception as e:
        logger.error(f"[Metadata] Error saving per-file metadata: {e}")
        return False


def get_per_file_metadata_from_dict(
    metadata: Dict[str, Any], filename: str
) -> Optional[Dict[str, Any]]:
    """Get per-file metadata from an already-loaded metadata dict.

    Pure-dict variant of get_per_file_metadata() — no disk/network I/O. Use
    this inside loops that already hold the directory's metadata (e.g. the
    gallery scan) so the JSON isn't re-stat'ed once per file.

    Args:
        metadata: Already-loaded gallery metadata dict
        filename: The output filename

    Returns:
        Dict with per-file metadata, or None if not found
    """
    if not isinstance(metadata, dict) or not filename or not isinstance(filename, str):
        return None
    try:
        basename = os.path.splitext(filename)[0]
    except Exception:
        return None
    entry = metadata.get(f"_file_{basename}")
    return entry if isinstance(entry, dict) else None


def has_per_file_metadata_from_dict(metadata: Dict[str, Any], filename: str) -> bool:
    """Pure-dict variant of has_per_file_metadata()."""
    return get_per_file_metadata_from_dict(metadata, filename) is not None


def get_metadata_level_from_dict(metadata: Dict[str, Any], filename: str) -> str:
    """Determine metadata completeness from an already-loaded metadata dict.

    Pure-dict variant of get_metadata_level(). Same semantics, zero I/O.

    Returns:
        'full' / 'partial' / 'none'
    """
    if get_per_file_metadata_from_dict(metadata, filename) is not None:
        return "full"

    if _lookup_file_metadata(metadata, filename, allow_reverse_match=True) is not None:
        return "partial"

    return "none"


def get_per_file_metadata(output_dir: str, filename: str) -> Optional[Dict[str, Any]]:
    """Get per-file metadata for a specific output file.

    Args:
        output_dir: Directory containing the file
        filename: The output filename

    Returns:
        Dict with per-file metadata, or None if not found
    """
    try:
        metadata = load_gallery_metadata(output_dir)
        return get_per_file_metadata_from_dict(metadata, filename)
    except Exception as e:
        logger.error(f"[Metadata] Error getting per-file metadata: {e}")
        return None


def has_per_file_metadata(output_dir: str, filename: str) -> bool:
    """Check if a file has per-file metadata (full traceability).

    Args:
        output_dir: Directory containing the file
        filename: The output filename

    Returns:
        bool: True if per-file metadata exists
    """
    return get_per_file_metadata(output_dir, filename) is not None


def get_metadata_level(output_dir: str, filename: str) -> str:
    """Determine the metadata completeness level for a file.

    Args:
        output_dir: Directory containing the file
        filename: The output filename

    Returns:
        'full' - Per-file metadata exists
        'partial' - Only job-level metadata exists
        'none' - No metadata available

    Note:
        This loads the directory metadata. Callers that already hold the
        loaded dict (e.g. the gallery scan loop) must use
        get_metadata_level_from_dict() instead — otherwise every file costs
        another network stat of the same JSON.
    """
    return get_metadata_level_from_dict(load_gallery_metadata(output_dir), filename)


def establish_lineage(
    output_dir: str,
    child_filename: str,
    parent_filename: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Establish a parent-child lineage relationship between two files.

    This is used when we know a file was generated from another (iteration),
    and we want to record that relationship in the per-file metadata.

    Args:
        output_dir: Directory containing both files
        child_filename: The output file (child)
        parent_filename: The input file used (parent)
        metadata: Optional already-loaded metadata dict. When supplied, the
            read-side lookups use it instead of re-loading the JSON, and any
            entry this call creates is mirrored back into it so a caller
            looping over many files stays consistent. Writes always go
            through the locked mutate path regardless.

    Returns:
        bool: True if lineage was established
    """
    use_dict = isinstance(metadata, dict)

    try:
        # Get parent's file_id (create one if needed)
        if use_dict:
            parent_meta = get_per_file_metadata_from_dict(metadata, parent_filename)
        else:
            parent_meta = get_per_file_metadata(output_dir, parent_filename)
        if parent_meta:
            parent_id = parent_meta.get('file_id')
        else:
            # Parent doesn't have per-file metadata - create minimal entry
            import uuid
            parent_id = str(uuid.uuid4())
            add_per_file_metadata(output_dir, parent_filename, file_id=parent_id)
            if use_dict:
                parent_key = f"_file_{os.path.splitext(parent_filename)[0]}"
                metadata[parent_key] = {"file_id": parent_id}

        if not parent_id:
            logger.warning(f"[Metadata] Could not get/create parent_id for {parent_filename}")
            return False

        # Get or create child's per-file metadata with parent_id
        if use_dict:
            child_meta = get_per_file_metadata_from_dict(metadata, child_filename)
        else:
            child_meta = get_per_file_metadata(output_dir, child_filename)
        if child_meta:
            # Update existing entry with parent_id (create it if it vanished
            # between the lookup above and the locked mutation below)
            basename = os.path.splitext(child_filename)[0]
            file_key = f"_file_{basename}"

            def _apply(metadata):
                entry = metadata.get(file_key)
                if isinstance(entry, dict):
                    entry['parent_id'] = parent_id
                else:
                    metadata[file_key] = dict(child_meta, parent_id=parent_id)

            saved = mutate_gallery_metadata(output_dir, _apply)
            if saved and use_dict:
                metadata[file_key] = dict(child_meta, parent_id=parent_id)
            return saved
        else:
            # Create new entry with parent_id
            import uuid
            child_id = str(uuid.uuid4())
            saved = add_per_file_metadata(
                output_dir, child_filename, file_id=child_id, parent_id=parent_id
            )
            if saved and use_dict:
                child_key = f"_file_{os.path.splitext(child_filename)[0]}"
                metadata[child_key] = {"file_id": child_id, "parent_id": parent_id}
            return saved

    except Exception as e:
        logger.error(f"[Metadata] Error establishing lineage: {e}")
        return False


def auto_establish_lineage_from_job_metadata(output_dir: str) -> int:
    """Automatically establish lineage for all files based on source_images in job metadata.

    Scans job-level metadata and creates per-file entries with parent_id
    for files that have a single source_image.

    Args:
        output_dir: Directory to process

    Returns:
        int: Number of lineage relationships established
    """
    if not os.path.isdir(output_dir):
        return 0

    metadata = load_gallery_metadata(output_dir)
    established = 0

    try:
        dir_listing = os.listdir(output_dir)
    except OSError as e:
        logger.warning(f"Cannot list {output_dir} for lineage scan: {e}")
        return 0

    # First pass: collect all files and their source_images from job metadata
    for key, value in metadata.items():
        if not key.startswith("_prefix_"):
            continue
        if not isinstance(value, dict):
            continue

        source_images = value.get('source_images') or []
        job_prefix = value.get('job_prefix', key[8:])  # Remove "_prefix_"

        # Only establish lineage if there's exactly one source image
        if len(source_images) != 1:
            continue

        parent_filename = source_images[0]

        # Find files that match this job prefix (snapshot listing taken above)
        for filename in dir_listing:
            if not filename.startswith(job_prefix):
                continue

            # Skip non-output files
            ext = os.path.splitext(filename)[1].lower()
            if ext not in COMFYUI_OUTPUT_EXTENSIONS:
                continue

            # Check if lineage already established (pure-dict lookup — the
            # directory metadata was loaded once above, re-loading it per
            # candidate file cost a network stat each time)
            file_meta = get_per_file_metadata_from_dict(metadata, filename)
            if file_meta and file_meta.get('parent_id'):
                continue  # Already has lineage

            # Establish lineage (metadata dict is kept in sync by the callee)
            if establish_lineage(output_dir, filename, parent_filename, metadata=metadata):
                established += 1

    return established
