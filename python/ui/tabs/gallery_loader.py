"""
Gallery Loader module.

Handles async loading operations for the gallery:
- Directory scanning
- Metadata extraction
- User discovery
- File system watching
"""

import os
import re
import logging

from core.config import (
    GALLERY_IMAGE_EXTENSIONS as IMAGE_EXTENSIONS,
    GALLERY_MODEL_EXTENSIONS as MODEL_EXTENSIONS,
    GALLERY_VIDEO_EXTENSIONS as VIDEO_EXTENSIONS,
    GALLERY_AUDIO_EXTENSIONS as AUDIO_EXTENSIONS,
    GALLERY_SUPPORTED_EXTENSIONS as SUPPORTED_EXTENSIONS,
)

logger = logging.getLogger(__name__)


def extract_job_prefix(filename: str, file_type: str = 'image') -> tuple:
    """Extract the job prefix from a ComfyUI output filename.

    Filenames follow patterns like:
    - sh0030_luma_tools_Body_Color_ORANGE_gen01_00001.png (with _genXX)
    - sh0030_body_color_gen02_00003.png (with _genXX)
    - workflow_name_00001.png (sequence without _genXX)
    - ComfyUI_temp_xxxxx.png (temp file - these are outputs)

    Args:
        filename: The filename to extract prefix from
        file_type: 'image', 'model', 'video', or 'audio' - models default to output

    Returns:
        tuple: (prefix, is_output) where:
            - prefix: The job prefix string (or None if no valid prefix)
            - is_output: True if this appears to be a generated output
    """
    # Validate input
    if not filename or not isinstance(filename, str):
        return (None, False)

    try:
        # Remove extension
        base = os.path.splitext(filename)[0]
        if not base:
            return (None, False)

        # Check for ComfyUI temp files (these are outputs)
        if base.startswith('ComfyUI_temp') or base.startswith('ComfyUI_'):
            # Try to extract a meaningful prefix by removing ComfyUI prefix and trailing numbers
            # Example: ComfyUI_temp_xxxxx_00001 -> ComfyUI_temp_xxxxx
            try:
                cleaned = re.sub(r'_\d+$', '', base)
                prefix = cleaned if cleaned != base else None
                return (prefix, True)
            except Exception:
                return (base, True)  # Still mark as output

        # Look for _genXX pattern (marks it as an output)
        try:
            gen_match = re.search(r'_gen(\d+)', base, re.IGNORECASE)
            if gen_match:
                # Extract everything before _genXX as the prefix
                prefix = base[:gen_match.start()]
                # Clean up trailing underscores
                prefix = prefix.rstrip('_')
                return (prefix if prefix else None, True)
        except Exception:
            pass  # Fall through to next pattern

        # No _genXX pattern - check for other output indicators
        # Files with trailing sequence numbers (4+ digits) are likely outputs
        # Examples: workflow_00001.png, render_0001.png
        try:
            sequence_match = re.search(r'_(\d{4,})$', base)
            if sequence_match:
                # Extract prefix before sequence number
                prefix = base[:sequence_match.start()]
                return (prefix if prefix else None, True)
        except Exception:
            pass  # Fall through to next pattern

        # Files with shorter trailing numbers might also be outputs (3 digits)
        # But be more conservative - only if there's an underscore before them
        try:
            short_sequence_match = re.search(r'_(\d{3})$', base)
            if short_sequence_match:
                prefix = base[:short_sequence_match.start()]
                # Only treat as output if prefix is substantial (not just a few chars)
                if len(prefix) > 3:
                    return (prefix, True)
        except Exception:
            pass  # Fall through to fallback

        # No clear output pattern
        # 3D models are typically generated outputs, so default them to output
        # Images without patterns are likely input images
        try:
            cleaned = re.sub(r'_?\d+$', '', base)
            # 3D models (and video/audio) default to output, images default to input
            is_output = file_type in ('model', 'video', 'audio')
            return (cleaned if cleaned else None, is_output)
        except Exception:
            is_output = file_type in ('model', 'video', 'audio')
            return (base, is_output)  # Return base as fallback

    except Exception:
        is_output = file_type in ('model', 'video', 'audio')
        return (None, is_output)


def _enrich_file_fallback(item):
    """Set safe default metadata fields on an item dict."""
    if 'workflow' not in item:
        item['workflow'] = ''
    if 'job_prefix' not in item:
        try:
            filename = os.path.basename(item.get('path', ''))
            file_type = item.get('type', 'image')
            job_prefix, is_output = extract_job_prefix(filename, file_type)
            item['job_prefix'] = job_prefix
            item['is_input'] = not is_output
        except Exception:
            item['job_prefix'] = None
            file_type = item.get('type', 'image')
            item['is_input'] = file_type not in ('model', 'video', 'audio')
    if 'source_images' not in item:
        item['source_images'] = []


class GalleryLoader:
    """Handles async loading operations for the gallery.

    This class is stateless and all methods are designed to run on worker threads.
    """

    @staticmethod
    def scan_directory(output_dir, load_metadata=True, bundle_pairs=True):
        """Scan directory recursively for image and 3D model files (runs on worker thread).

        Args:
            output_dir: Directory to scan
            load_metadata: If True, load workflow metadata from JSON files (slower but complete)
            bundle_pairs: If True, detect and bundle _view/_export file pairs

        Returns:
            list: List of item dicts with keys: path, mtime, type, name, workflow
        """
        items = []

        # Check if directory exists (can be slow on network paths — up to 30s on Windows)
        if not os.path.isdir(output_dir):
            logger.warning(f"[Loader] Gallery directory not accessible: {output_dir}")
            return items

        # Use module-level constants for supported extensions
        model_extensions = MODEL_EXTENSIONS
        supported_extensions = SUPPORTED_EXTENSIONS

        try:
            # First pass: collect all files grouped by directory
            files_by_dir = {}  # dir_path -> [(filename, full_path, mtime, file_type), ...]

            for root, dirs, files in os.walk(output_dir):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in supported_extensions:
                        full_path = os.path.normpath(os.path.join(root, filename))
                        try:
                            mtime = os.path.getmtime(full_path)
                        except OSError as e:
                            logger.debug(f"Could not get mtime for {full_path}: {e}")
                            continue
                        # Determine file type based on extension
                        if ext in model_extensions:
                            file_type = 'model'
                        elif ext in VIDEO_EXTENSIONS:
                            file_type = 'video'
                        elif ext in AUDIO_EXTENSIONS:
                            file_type = 'audio'
                        else:
                            file_type = 'image'

                        if root not in files_by_dir:
                            files_by_dir[root] = []
                        files_by_dir[root].append((filename, full_path, mtime, file_type))

            # Second pass: load metadata and create items
            # Import metadata functions once at the top
            try:
                from comfyui.metadata import (
                    load_gallery_metadata, _lookup_file_metadata,
                    get_workflow_preset_for_files, is_known_input_file,
                    get_metadata_level,
                )
                from comfyui.utils import compute_file_hash
            except ImportError as e:
                logger.error(f"[Loader] Failed to import metadata functions: {e}")
                load_gallery_metadata = None
                get_workflow_preset_for_files = None
                _lookup_file_metadata = None
                is_known_input_file = None
                get_metadata_level = None
                compute_file_hash = None

            for dir_path, file_list in files_by_dir.items():
                # Load full metadata if enabled (for enhanced detection)
                full_metadata = {}
                workflow_map = {}

                if load_metadata and load_gallery_metadata and get_workflow_preset_for_files:
                    filenames = [f[0] for f in file_list]
                    try:
                        full_metadata = load_gallery_metadata(dir_path)
                        if not isinstance(full_metadata, dict):
                            full_metadata = {}
                    except Exception as e:
                        logger.debug(f"[GalleryLoader] Failed to load metadata for {dir_path}: {e}")
                        full_metadata = {}

                    try:
                        workflow_map = get_workflow_preset_for_files(dir_path, filenames)
                        if not isinstance(workflow_map, dict):
                            workflow_map = {}
                    except Exception as e:
                        logger.debug(f"[GalleryLoader] Failed to load workflow presets for {dir_path}: {e}")
                        workflow_map = {}

                # Build items dict
                items_dict = {}
                for filename, full_path, mtime, file_type in file_list:
                    # Try filename-based metadata lookup first (no hash needed)
                    file_metadata = None
                    if full_metadata and _lookup_file_metadata:
                        try:
                            file_metadata = _lookup_file_metadata(
                                full_metadata, filename,
                                allow_reverse_match=False,
                                content_hash=None)
                        except Exception as e:
                            logger.debug(f"[GalleryLoader] Metadata lookup failed for {filename}: {e}")
                            file_metadata = None

                    # Only compute hash if filename lookup missed and hash lookup is available
                    content_hash = None
                    if file_metadata is None and full_metadata and _lookup_file_metadata and compute_file_hash:
                        try:
                            content_hash = compute_file_hash(full_path)
                            file_metadata = _lookup_file_metadata(
                                full_metadata, filename,
                                allow_reverse_match=False,
                                content_hash=content_hash)
                        except Exception:
                            pass

                    # Determine if file is output and get job prefix
                    is_output = None
                    job_prefix = None
                    source_images = []
                    has_metadata = False

                    if file_metadata and isinstance(file_metadata, dict) and 'is_output' in file_metadata:
                        has_metadata = True
                        try:
                            is_output = file_metadata.get('is_output', True)
                            job_prefix = file_metadata.get('job_prefix')
                            source_images = file_metadata.get('source_images', [])
                            if not isinstance(source_images, list):
                                source_images = []
                        except Exception:
                            is_output = None
                            job_prefix = None
                            has_metadata = False

                    # Fall back to filename pattern detection if metadata missing or invalid
                    if is_output is None or (is_output and job_prefix is None):
                        try:
                            job_prefix, is_output = extract_job_prefix(filename, file_type)
                        except Exception:
                            job_prefix = None
                            is_output = file_type in ('model', 'video', 'audio')

                        if is_output and file_type == 'image' and is_known_input_file:
                            try:
                                if is_known_input_file(output_dir, filename):
                                    is_output = False
                            except Exception:
                                pass

                    # Determine metadata completeness level
                    if get_metadata_level:
                        try:
                            metadata_level = get_metadata_level(dir_path, filename)
                        except Exception:
                            metadata_level = 'partial' if has_metadata else 'none'
                    else:
                        metadata_level = 'partial' if has_metadata else 'none'

                    items_dict[filename] = {
                        'path': full_path,
                        'mtime': mtime,
                        'type': file_type,
                        'name': filename.lower(),
                        'workflow': workflow_map.get(filename, '') if workflow_map else '',
                        'job_prefix': job_prefix,
                        'is_input': not is_output,  # If not a generated output, treat as input
                        'source_images': source_images,  # Input images used
                        'has_metadata': has_metadata,  # Whether metadata was found for this file
                        'metadata_level': metadata_level,  # 'full', 'partial', or 'none'
                        'content_hash': content_hash,  # SHA-256 hash for file identification
                    }

                # Detect and bundle _view/_export pairs if enabled
                if bundle_pairs:
                    bundled_files = set()
                    for filename in list(items_dict.keys()):
                        if filename in bundled_files:
                            continue

                        base_name = None
                        view_file = None
                        export_file = None

                        # Check if this is a _view or _export file
                        if '_view' in filename:
                            parts = filename.rsplit('_view', 1)
                            if len(parts) == 2:
                                base_name = parts[0]
                                ext_part = parts[1]
                                view_file = filename
                                export_candidate = f"{base_name}_export{ext_part}"
                                if export_candidate in items_dict:
                                    export_file = export_candidate
                        elif '_export' in filename:
                            parts = filename.rsplit('_export', 1)
                            if len(parts) == 2:
                                base_name = parts[0]
                                ext_part = parts[1]
                                export_file = filename
                                view_candidate = f"{base_name}_view{ext_part}"
                                if view_candidate in items_dict:
                                    view_file = view_candidate

                        # If we found a pair, create a bundled item
                        if base_name and view_file and export_file:
                            bundled_files.add(view_file)
                            bundled_files.add(export_file)

                            view_item = items_dict[view_file]
                            export_item = items_dict[export_file]

                            items.append({
                                'path': view_item['path'],
                                'export_path': export_item['path'],
                                'mtime': max(view_item['mtime'], export_item['mtime']),
                                'type': view_item['type'],
                                'name': view_item['name'],
                                'workflow': view_item['workflow'],
                                'job_prefix': view_item.get('job_prefix'),
                                'is_input': view_item.get('is_input', False),
                                'source_images': view_item.get('source_images', []),
                                'has_metadata': view_item.get('has_metadata', False),
                                'metadata_level': view_item.get('metadata_level', 'none'),
                                'content_hash': view_item.get('content_hash'),
                                'is_bundled': True
                            })
                        else:
                            if filename not in bundled_files:
                                items.append(items_dict[filename])
                else:
                    # No bundling - just add all items
                    items.extend(items_dict.values())

        except Exception as e:
            logger.error(f"Error scanning gallery directory: {e}")

        # Log summary instead of per-file
        if items:
            outputs = sum(1 for i in items if not i.get('is_input', False))
            inputs = len(items) - outputs
            with_meta = sum(1 for i in items if i.get('has_metadata', False))
            logger.debug(f"[Loader] Scanned {len(items)} files: {outputs} outputs, {inputs} inputs, {with_meta} with metadata")

        return items
