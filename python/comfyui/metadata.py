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
import threading
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from core.config import COMFYUI_OUTPUT_EXTENSIONS
from core.utils import ensure_directory

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

    for filename in os.listdir(output_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext in supported_extensions:
            # Filter by job prefix if provided
            if job_prefix and not filename.startswith(job_prefix):
                continue
            full_path = os.path.join(output_dir, filename)
            mtime = os.path.getmtime(full_path)
            # Filter by minimum modification time if provided
            if min_mtime is not None and mtime < min_mtime:
                continue
            files.append((full_path, mtime))

    files.sort(key=lambda x: x[1], reverse=True)
    return [f[0] for f in files]


def cleanup_job_temp_files(output_dir: str) -> int:
    """Clean up temporary job files from the output directory."""
    import glob

    if not output_dir or not os.path.exists(output_dir):
        return 0

    temp_patterns = [
        "comfyui_workflow*.json",
        "comfyui_seeds.json",
        "comfyui_runner.py",
        "comfyui_client.py",
        "comfyui_utils.py",
        "comfyui_job_info.txt",
        "comfyui_plugin_info.txt",
    ]

    deleted_count = 0

    for pattern in temp_patterns:
        for file_path in glob.glob(os.path.join(output_dir, pattern)):
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception:
                pass  # Silently skip files that can't be deleted

    return deleted_count


def scan_output_directory(output_dir: str) -> List[Dict[str, Any]]:
    """Scan directory for generated ComfyUI output files."""
    import glob

    if not output_dir or not os.path.exists(output_dir):
        return []

    output_files = []

    for ext in COMFYUI_OUTPUT_EXTENSIONS:
        pattern = os.path.join(output_dir, '**', f'*{ext}')
        for path in glob.glob(pattern, recursive=True):
            try:
                stat = os.stat(path)
                output_files.append({
                    'path': path,
                    'filename': os.path.basename(path),
                    'created': datetime.fromtimestamp(stat.st_ctime),
                    'size': stat.st_size,
                    'extension': ext,
                })
            except Exception:
                pass  # Skip files that can't be accessed

    output_files.sort(key=lambda x: x['created'], reverse=True)
    return output_files


# ============================================================================
# GALLERY METADATA
# ============================================================================

GALLERY_METADATA_FILE = "comfyui_gallery_metadata.json"
_gallery_metadata_cache: Dict[str, Tuple[float, Dict[str, Dict[str, Any]]]] = {}
# Use RLock for reentrant safety (same thread can acquire multiple times)
_gallery_metadata_cache_lock = threading.RLock()


def _get_metadata_path(output_dir: str) -> str:
    """Get the path to the metadata file for a directory."""
    # Validate input type - catch common error of passing widget instead of path
    if not isinstance(output_dir, (str, os.PathLike)):
        logger.error(f"[Metadata] Invalid output_dir type: {type(output_dir).__name__} (expected str or PathLike)")
        raise TypeError(f"output_dir must be a string or path-like object, not {type(output_dir).__name__}")
    return os.path.join(output_dir, GALLERY_METADATA_FILE)


def clear_gallery_metadata_cache(output_dir: str = None) -> None:
    """Clear the gallery metadata cache. Thread-safe."""
    global _gallery_metadata_cache
    with _gallery_metadata_cache_lock:
        if output_dir:
            _gallery_metadata_cache.pop(output_dir, None)
        else:
            _gallery_metadata_cache.clear()


def load_gallery_metadata(output_dir: str, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
    """Load gallery metadata from the output directory.

    Thread-safe: Uses lock for cache access. Handles TOCTOU race by
    re-checking mtime after file read before caching.

    Returns:
        Dict with metadata, or empty dict if file missing/corrupted
    """
    global _gallery_metadata_cache

    if not output_dir:
        return {}

    try:
        metadata_path = _get_metadata_path(output_dir)
    except Exception as e:
        logger.error(f"[Metadata] Error getting metadata path for {output_dir}: {e}")
        return {}

    if not os.path.exists(metadata_path):
        return {}

    try:
        # Get initial mtime for cache check
        initial_mtime = os.path.getmtime(metadata_path)

        # Check cache (thread-safe)
        if use_cache:
            with _gallery_metadata_cache_lock:
                if output_dir in _gallery_metadata_cache:
                    try:
                        cached_mtime, cached_data = _gallery_metadata_cache[output_dir]
                        if cached_mtime == initial_mtime and isinstance(cached_data, dict):
                            return cached_data
                    except Exception as e:
                        logger.error(f"[Metadata] Error reading cache: {e}")

        # Load from file (outside lock - file I/O can be slow)
        with open(metadata_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate data is a dict
        if not isinstance(data, dict):
            logger.warning(f"[Metadata] Invalid metadata format in {metadata_path}, expected dict but got {type(data)}")
            return {}

        # TOCTOU fix: Re-check mtime after reading to detect file changes during read
        # Only cache if file hasn't changed since we started reading
        final_mtime = os.path.getmtime(metadata_path)

        # Update cache (thread-safe) only if mtime is stable
        if final_mtime == initial_mtime:
            with _gallery_metadata_cache_lock:
                _gallery_metadata_cache[output_dir] = (final_mtime, data)
        else:
            logger.debug(f"[Metadata] File changed during read, not caching: {metadata_path}")

        return data

    except json.JSONDecodeError as e:
        logger.error(f"[Metadata] Corrupted JSON in {metadata_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"[Metadata] Error loading gallery metadata from {output_dir}: {e}")
        return {}


def save_gallery_metadata(output_dir: str, metadata: Dict[str, Dict[str, Any]]) -> bool:
    """Save gallery metadata to the output directory."""
    metadata_path = _get_metadata_path(output_dir)

    try:
        ensure_directory(output_dir)
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)
        clear_gallery_metadata_cache(output_dir)
        return True
    except Exception as e:
        logger.error(f"Error saving gallery metadata: {e}")
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

    Returns:
        bool: True if metadata saved successfully, False otherwise
    """
    try:
        metadata = load_gallery_metadata(output_dir)
    except Exception as e:
        logger.error(f"[Metadata] Error loading metadata, starting fresh: {e}")
        metadata = {}

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
        for node_id, data in editable_values.items():
            if not isinstance(data, dict):
                continue

            node_info = data.get('node')
            value = data.get('value')

            # Safely get widget_type
            widget_type = None
            if node_info and hasattr(node_info, 'widget_type'):
                widget_type = node_info.widget_type

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

            # Serialize editable value
            try:
                serialized_editable[str(node_id)] = {
                    "node_id": getattr(node_info, 'node_id', node_id) if node_info else node_id,
                    "display_name": getattr(node_info, 'display_name', "") if node_info else "",
                    "node_type": getattr(node_info, 'node_type', "") if node_info else "",
                    "widget_type": widget_type or "text",
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
            "workflow_preset": workflow_preset,
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
        }

        metadata[f"_prefix_{prefix_key}"] = entry

        # Also mark source images as inputs explicitly
        # This ensures input files are correctly identified even if they have
        # filenames that look like outputs (e.g., with _001 suffix)
        if source_images:
            for source_image in source_images:
                input_key = f"_input_{source_image}"
                if input_key not in metadata:
                    metadata[input_key] = {
                        "is_output": False,
                        "is_input": True,
                        "used_by_job": prefix_key,
                        "timestamp": datetime.now().isoformat(),
                    }

        # Same for source models
        if source_models:
            for source_model in source_models:
                input_key = f"_input_{source_model}"
                if input_key not in metadata:
                    metadata[input_key] = {
                        "is_output": False,
                        "is_input": True,
                        "used_by_job": prefix_key,
                        "timestamp": datetime.now().isoformat(),
                    }

        return save_gallery_metadata(output_dir, metadata)
    except Exception as e:
        logger.error(f"[Metadata] Error saving metadata: {e}")
        return False


def get_item_metadata(output_dir: str, filename: str, allow_reverse_match: bool = True) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific gallery item (image, video, model, etc.).

    Args:
        output_dir: Directory containing the metadata file
        filename: Filename to look up
        allow_reverse_match: If True (default), also match when job prefix ends with
            the filename. This is useful for display/recreate purposes. Set to False
            when determining input/output status to avoid matching input files to
            output job metadata.

    Returns:
        Metadata dict for the file, or None if not found
    """
    metadata = load_gallery_metadata(output_dir)
    return _lookup_file_metadata(metadata, filename, allow_reverse_match=allow_reverse_match)


def _lookup_file_metadata(
    metadata: Dict[str, Dict[str, Any]],
    filename: str,
    allow_reverse_match: bool = False
) -> Optional[Dict[str, Any]]:
    """Internal helper to look up metadata for a filename.

    Looks up by exact filename first, then by prefix match.

    Args:
        metadata: Gallery metadata dict
        filename: Filename to look up
        allow_reverse_match: If True, also match when prefix ends with basename.
            This is useful for recreate settings but should be False for
            input/output detection to avoid matching input files to output metadata.

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
    try:
        for key, value in metadata.items():
            if not isinstance(key, str) or not key.startswith("_prefix_"):
                continue

            prefix = key[8:]  # Remove "_prefix_" prefix
            # Check if basename starts with prefix (normal case for outputs)
            if basename.startswith(prefix):
                if isinstance(value, dict):
                    return value

            # Reverse match: prefix ends with basename (for recreate settings only)
            # e.g., prefix="luma_tools_job_filename" matches basename="filename"
            # IMPORTANT: Only use this when explicitly requested, otherwise input
            # files may incorrectly match output job metadata
            if allow_reverse_match:
                if prefix.endswith(basename) or prefix.endswith(f"_{basename}"):
                    if isinstance(value, dict):
                        return value
    except Exception as e:
        logger.error(f"[Metadata] Error during prefix lookup for {filename}: {e}")

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

    # Check for explicit input entry first
    input_key = f"_input_{filename}"
    if input_key in metadata:
        return True

    # Check if file appears in any job's source lists
    for key, value in metadata.items():
        if not key.startswith("_prefix_"):
            continue
        if not isinstance(value, dict):
            continue

        source_images = value.get('source_images') or []
        source_models = value.get('source_models') or []

        if filename in source_images or filename in source_models:
            # Mark it for future lookups (lazy migration)
            mark_as_input_file(output_dir, filename, value.get('job_prefix', key[8:]))
            return True

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

        if input_key not in metadata:
            metadata[input_key] = {
                "is_output": False,
                "is_input": True,
                "used_by_job": used_by_job,
                "timestamp": datetime.now().isoformat(),
            }
            return save_gallery_metadata(output_dir, metadata)
        return True  # Already marked
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
    try:
        metadata = load_gallery_metadata(output_dir)
    except Exception as e:
        logger.error(f"[Metadata] Error loading metadata for MP4 Maker: {e}")
        metadata = {}

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

    metadata[mp4_key] = entry

    try:
        return save_gallery_metadata(output_dir, metadata)
    except Exception as e:
        logger.error(f"[Metadata] Error saving MP4 Maker metadata: {e}")
        return False


def extract_prompts_from_editable_values(
    editable_values: Optional[Dict[int, Dict[str, Any]]]
) -> str:
    """Extract prompt text from editable values dictionary."""
    if not editable_values:
        return ""

    prompts = []
    for data in editable_values.values():
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
    metadata = load_gallery_metadata(output_dir)
    basename = os.path.splitext(filename)[0]
    note_key = f"_note_{basename}"

    if note.strip():
        metadata[note_key] = note.strip()
    elif note_key in metadata:
        del metadata[note_key]

    return save_gallery_metadata(output_dir, metadata)


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

    Returns:
        bool: True if saved successfully
    """
    import uuid

    try:
        metadata = load_gallery_metadata(output_dir)
    except Exception as e:
        logger.error(f"[Metadata] Error loading metadata for per-file: {e}")
        metadata = {}

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
        "timestamp": datetime.now().isoformat(),
    }

    # Remove None values to keep JSON clean
    entry = {k: v for k, v in entry.items() if v is not None}

    metadata[file_key] = entry

    try:
        return save_gallery_metadata(output_dir, metadata)
    except Exception as e:
        logger.error(f"[Metadata] Error saving per-file metadata: {e}")
        return False


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
        basename = os.path.splitext(filename)[0]
        file_key = f"_file_{basename}"
        return metadata.get(file_key)
    except Exception as e:
        logger.error(f"[Metadata] Error getting per-file metadata: {e}")
        return None


def get_file_lineage(output_dir: str, filename: str) -> list:
    """Get the lineage chain for a file (iteration history).

    Traces back through parent_id references to build the full lineage.

    Args:
        output_dir: Directory containing the file
        filename: Starting filename

    Returns:
        List of dicts with file_id, filename, timestamp (oldest first)
    """
    metadata = load_gallery_metadata(output_dir)
    lineage = []

    # Build a lookup by file_id
    file_id_to_entry = {}
    file_id_to_filename = {}

    for key, value in metadata.items():
        if key.startswith("_file_") and isinstance(value, dict):
            file_id = value.get("file_id")
            if file_id:
                file_id_to_entry[file_id] = value
                file_id_to_filename[file_id] = key[6:]  # Remove "_file_" prefix

    # Get starting file's metadata
    basename = os.path.splitext(filename)[0]
    file_key = f"_file_{basename}"
    current = metadata.get(file_key)

    if not current:
        return []

    # Trace back through parents
    visited = set()
    while current:
        file_id = current.get("file_id")
        if file_id in visited:
            break  # Avoid infinite loops
        visited.add(file_id)

        lineage.append({
            "file_id": file_id,
            "filename": file_id_to_filename.get(file_id, "unknown"),
            "timestamp": current.get("timestamp"),
            "actual_seed": current.get("actual_seed"),
        })

        # Move to parent
        parent_id = current.get("parent_id")
        if parent_id and parent_id in file_id_to_entry:
            current = file_id_to_entry[parent_id]
        else:
            break

    # Return oldest first
    lineage.reverse()
    return lineage


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
    """
    # Check for per-file metadata first
    if has_per_file_metadata(output_dir, filename):
        return "full"

    # Check for job-level metadata
    if get_item_metadata(output_dir, filename) is not None:
        return "partial"

    return "none"


def establish_lineage(output_dir: str, child_filename: str, parent_filename: str) -> bool:
    """Establish a parent-child lineage relationship between two files.

    This is used when we know a file was generated from another (iteration),
    and we want to record that relationship in the per-file metadata.

    Args:
        output_dir: Directory containing both files
        child_filename: The output file (child)
        parent_filename: The input file used (parent)

    Returns:
        bool: True if lineage was established
    """
    try:
        # Get parent's file_id (create one if needed)
        parent_meta = get_per_file_metadata(output_dir, parent_filename)
        if parent_meta:
            parent_id = parent_meta.get('file_id')
        else:
            # Parent doesn't have per-file metadata - create minimal entry
            import uuid
            parent_id = str(uuid.uuid4())
            add_per_file_metadata(output_dir, parent_filename, file_id=parent_id)

        if not parent_id:
            logger.warning(f"[Metadata] Could not get/create parent_id for {parent_filename}")
            return False

        # Get or create child's per-file metadata with parent_id
        child_meta = get_per_file_metadata(output_dir, child_filename)
        if child_meta:
            # Update existing entry with parent_id
            metadata = load_gallery_metadata(output_dir)
            basename = os.path.splitext(child_filename)[0]
            file_key = f"_file_{basename}"
            if file_key in metadata:
                metadata[file_key]['parent_id'] = parent_id
                return save_gallery_metadata(output_dir, metadata)
        else:
            # Create new entry with parent_id
            return add_per_file_metadata(output_dir, child_filename, parent_id=parent_id)

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
    metadata = load_gallery_metadata(output_dir)
    established = 0

    # First pass: collect all files and their source_images from job metadata
    for key, value in metadata.items():
        if not key.startswith("_prefix_"):
            continue
        if not isinstance(value, dict):
            continue

        source_images = value.get('source_images', [])
        job_prefix = value.get('job_prefix', key[8:])  # Remove "_prefix_"

        # Only establish lineage if there's exactly one source image
        if len(source_images) != 1:
            continue

        parent_filename = source_images[0]

        # Find files that match this job prefix
        for filename in os.listdir(output_dir):
            if not filename.startswith(job_prefix):
                continue

            # Skip non-output files
            ext = os.path.splitext(filename)[1].lower()
            if ext not in COMFYUI_OUTPUT_EXTENSIONS:
                continue

            # Check if lineage already established
            file_meta = get_per_file_metadata(output_dir, filename)
            if file_meta and file_meta.get('parent_id'):
                continue  # Already has lineage

            # Establish lineage
            if establish_lineage(output_dir, filename, parent_filename):
                established += 1

    return established
