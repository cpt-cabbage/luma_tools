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
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from core.config import COMFYUI_OUTPUT_EXTENSIONS


# ============================================================================
# OUTPUT FILE MANAGEMENT
# ============================================================================

def get_job_output_files(output_dir: str) -> List[str]:
    """Get the output files from a job's output directory."""
    if not output_dir or not os.path.isdir(output_dir):
        return []

    supported_extensions = set(COMFYUI_OUTPUT_EXTENSIONS)
    files = []

    for filename in os.listdir(output_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext in supported_extensions:
            full_path = os.path.join(output_dir, filename)
            mtime = os.path.getmtime(full_path)
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
                pass

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
                pass

    output_files.sort(key=lambda x: x['created'], reverse=True)
    return output_files


# ============================================================================
# GALLERY METADATA
# ============================================================================

GALLERY_METADATA_FILE = "comfyui_gallery_metadata.json"
_gallery_metadata_cache: Dict[str, Tuple[float, Dict[str, Dict[str, Any]]]] = {}


def _get_metadata_path(output_dir: str) -> str:
    """Get the path to the metadata file for a directory."""
    return os.path.join(output_dir, GALLERY_METADATA_FILE)


def clear_gallery_metadata_cache(output_dir: str = None) -> None:
    """Clear the gallery metadata cache."""
    global _gallery_metadata_cache
    if output_dir:
        _gallery_metadata_cache.pop(output_dir, None)
    else:
        _gallery_metadata_cache.clear()


def load_gallery_metadata(output_dir: str, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
    """Load gallery metadata from the output directory.

    Returns:
        Dict with metadata, or empty dict if file missing/corrupted
    """
    global _gallery_metadata_cache

    if not output_dir:
        return {}

    try:
        metadata_path = _get_metadata_path(output_dir)
    except Exception as e:
        print(f"[Metadata] Error getting metadata path for {output_dir}: {e}")
        return {}

    if not os.path.exists(metadata_path):
        return {}

    try:
        current_mtime = os.path.getmtime(metadata_path)

        # Check cache
        if use_cache and output_dir in _gallery_metadata_cache:
            try:
                cached_mtime, cached_data = _gallery_metadata_cache[output_dir]
                if cached_mtime == current_mtime and isinstance(cached_data, dict):
                    return cached_data
            except Exception as e:
                print(f"[Metadata] Error reading cache: {e}")

        # Load from file
        with open(metadata_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

            # Validate data is a dict
            if not isinstance(data, dict):
                print(f"[Metadata] Invalid metadata format in {metadata_path}, expected dict but got {type(data)}")
                return {}

            _gallery_metadata_cache[output_dir] = (current_mtime, data)
            return data

    except json.JSONDecodeError as e:
        print(f"[Metadata] Corrupted JSON in {metadata_path}: {e}")
        return {}
    except Exception as e:
        print(f"[Metadata] Error loading gallery metadata from {output_dir}: {e}")
        return {}


def save_gallery_metadata(output_dir: str, metadata: Dict[str, Dict[str, Any]]) -> bool:
    """Save gallery metadata to the output directory."""
    metadata_path = _get_metadata_path(output_dir)

    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)
        clear_gallery_metadata_cache(output_dir)
        return True
    except Exception as e:
        print(f"Error saving gallery metadata: {e}")
        return False


def add_image_metadata(
    output_dir: str,
    output_prefix: str,
    prompt: Optional[str] = None,
    workflow_name: Optional[str] = None,
    input_image: Optional[str] = None,
    generation_count: int = 1,
    base_seed: Optional[int] = None,
    workflow_preset: Optional[str] = None,
    editable_values: Optional[Dict[int, Dict[str, Any]]] = None,
) -> bool:
    """Add metadata for images that will be generated with a given prefix.

    Enhanced to store:
    - is_output: True (marks as generated output)
    - job_prefix: Grouping key for gallery stacking
    - source_images: All input images used in generation
    - source_models: All 3D models used as inputs

    Returns:
        bool: True if metadata saved successfully, False otherwise
    """
    try:
        metadata = load_gallery_metadata(output_dir)
    except Exception as e:
        print(f"[Metadata] Error loading metadata, starting fresh: {e}")
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
                    print(f"[Metadata] Error extracting image paths: {e}")
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
                    print(f"[Metadata] Error extracting model paths: {e}")

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
                print(f"[Metadata] Error serializing editable value for node {node_id}: {e}")

    # Deduplicate source lists while preserving order
    try:
        source_images = list(dict.fromkeys(source_images))  # Remove dupes, keep order
        source_models = list(dict.fromkeys(source_models))
    except Exception as e:
        print(f"[Metadata] Error deduplicating sources: {e}")

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
        }

        metadata[f"_prefix_{prefix_key}"] = entry
        return save_gallery_metadata(output_dir, metadata)
    except Exception as e:
        print(f"[Metadata] Error saving metadata: {e}")
        return False


def get_image_metadata(output_dir: str, filename: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific image file."""
    metadata = load_gallery_metadata(output_dir)
    return _lookup_file_metadata(metadata, filename)


def _lookup_file_metadata(metadata: Dict[str, Dict[str, Any]], filename: str) -> Optional[Dict[str, Any]]:
    """Internal helper to look up metadata for a filename.

    Looks up by exact filename first, then by prefix match.

    Args:
        metadata: Gallery metadata dict
        filename: Filename to look up

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

    # Try prefix matching
    try:
        basename = os.path.splitext(filename)[0]
    except Exception:
        return None

    # Look for matching prefix entries
    try:
        for key, value in metadata.items():
            if not isinstance(key, str) or not key.startswith("_prefix_"):
                continue

            prefix = key[8:]  # Remove "_prefix_" prefix
            if basename.startswith(prefix):
                if isinstance(value, dict):
                    return value
    except Exception as e:
        print(f"[Metadata] Error during prefix lookup for {filename}: {e}")

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
