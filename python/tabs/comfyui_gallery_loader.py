"""
ComfyUI Gallery Loader module.

Handles async loading operations for the gallery:
- Directory scanning
- Metadata extraction
- User discovery
- File system watching
"""

import os
import re

# Supported file extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.exr'}
MODEL_EXTENSIONS = {'.glb', '.gltf', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz', '.dae'}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | MODEL_EXTENSIONS


def extract_job_prefix(filename: str) -> tuple:
    """Extract the job prefix from a ComfyUI output filename.

    Filenames follow patterns like:
    - sh0030_luma_tools_Body_Color_ORANGE_gen01_00001.png (with _genXX)
    - sh0030_body_color_gen02_00003.png (with _genXX)
    - workflow_name_00001.png (sequence without _genXX)
    - ComfyUI_temp_xxxxx.png (temp file - these are outputs)

    Args:
        filename: The filename to extract prefix from

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
                result = (prefix, True)
                print(f"[Detection] {filename} -> OUTPUT (ComfyUI temp, prefix={result[0]})")
                return result
            except Exception as e:
                print(f"[Detection] Error processing ComfyUI file {filename}: {e}")
                return (base, True)  # Still mark as output

        # Look for _genXX pattern (marks it as an output)
        try:
            gen_match = re.search(r'_gen(\d+)', base, re.IGNORECASE)
            if gen_match:
                # Extract everything before _genXX as the prefix
                prefix = base[:gen_match.start()]
                # Clean up trailing underscores
                prefix = prefix.rstrip('_')
                result = (prefix if prefix else None, True)
                print(f"[Detection] {filename} -> OUTPUT (has _genXX, prefix={result[0]})")
                return result
        except Exception as e:
            print(f"[Detection] Error in _genXX pattern search for {filename}: {e}")

        # No _genXX pattern - check for other output indicators
        # Files with trailing sequence numbers (4+ digits) are likely outputs
        # Examples: workflow_00001.png, render_0001.png
        try:
            sequence_match = re.search(r'_(\d{4,})$', base)
            if sequence_match:
                # Extract prefix before sequence number
                prefix = base[:sequence_match.start()]
                result = (prefix if prefix else None, True)
                print(f"[Detection] {filename} -> OUTPUT (4+ digit sequence, prefix={result[0]})")
                return result
        except Exception as e:
            print(f"[Detection] Error in 4+ digit sequence search for {filename}: {e}")

        # Files with shorter trailing numbers might also be outputs (3 digits)
        # But be more conservative - only if there's an underscore before them
        try:
            short_sequence_match = re.search(r'_(\d{3})$', base)
            if short_sequence_match:
                prefix = base[:short_sequence_match.start()]
                # Only treat as output if prefix is substantial (not just a few chars)
                if len(prefix) > 3:
                    result = (prefix, True)
                    print(f"[Detection] {filename} -> OUTPUT (3 digit sequence, prefix={result[0]})")
                    return result
        except Exception as e:
            print(f"[Detection] Error in 3 digit sequence search for {filename}: {e}")

        # No clear output pattern - likely an input image
        # Try to extract a meaningful prefix by removing trailing numbers
        try:
            cleaned = re.sub(r'_?\d+$', '', base)
            result = (cleaned if cleaned else None, False)
            print(f"[Detection] {filename} -> INPUT (no pattern match, prefix={result[0]})")
            return result
        except Exception as e:
            print(f"[Detection] Error in cleanup for {filename}: {e}")
            return (base, False)  # Return base as fallback

    except Exception as e:
        print(f"[Detection] Unexpected error processing {filename}: {e}")
        return (None, False)


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

        # Check if directory exists (can be slow on network paths)
        if not os.path.isdir(output_dir):
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
                        full_path = os.path.join(root, filename)
                        try:
                            mtime = os.path.getmtime(full_path)
                        except OSError:
                            continue
                        file_type = 'model' if ext in model_extensions else 'image'

                        if root not in files_by_dir:
                            files_by_dir[root] = []
                        files_by_dir[root].append((filename, full_path, mtime, file_type))

            # Second pass: load metadata and create items
            # Import metadata functions once at the top
            try:
                from comfyui.metadata import load_gallery_metadata, _lookup_file_metadata
                from comfyui.service import get_workflow_preset_for_files
            except ImportError as e:
                print(f"[Loader] Failed to import metadata functions: {e}")
                load_gallery_metadata = None
                get_workflow_preset_for_files = None
                _lookup_file_metadata = None

            for dir_path, file_list in files_by_dir.items():
                # Load full metadata if enabled (for enhanced detection)
                full_metadata = {}
                workflow_map = {}

                if load_metadata and load_gallery_metadata and get_workflow_preset_for_files:
                    filenames = [f[0] for f in file_list]
                    try:
                        # Load full metadata for advanced detection
                        full_metadata = load_gallery_metadata(dir_path)
                        if not isinstance(full_metadata, dict):
                            print(f"[Loader] Invalid metadata format from {dir_path}, expected dict")
                            full_metadata = {}
                    except Exception as e:
                        print(f"[Loader] Error loading full metadata from {dir_path}: {e}")
                        full_metadata = {}

                    try:
                        # Also get workflow presets (for backward compat)
                        workflow_map = get_workflow_preset_for_files(dir_path, filenames)
                        if not isinstance(workflow_map, dict):
                            workflow_map = {}
                    except Exception as e:
                        print(f"[Loader] Error loading workflow presets from {dir_path}: {e}")
                        workflow_map = {}

                # Build items dict
                items_dict = {}
                for filename, full_path, mtime, file_type in file_list:
                    # Try to get metadata-based detection first (new method)
                    file_metadata = None
                    if full_metadata and _lookup_file_metadata:
                        try:
                            file_metadata = _lookup_file_metadata(full_metadata, filename)
                        except Exception as e:
                            print(f"[Loader] Error looking up metadata for {filename}: {e}")
                            file_metadata = None

                    # Determine if file is output and get job prefix
                    is_output = None
                    job_prefix = None
                    source_images = []
                    has_metadata = False  # Track if metadata was found for this file

                    if file_metadata and isinstance(file_metadata, dict) and 'is_output' in file_metadata:
                        # Use metadata-based detection (reliable)
                        has_metadata = True
                        try:
                            is_output = file_metadata.get('is_output', True)
                            job_prefix = file_metadata.get('job_prefix')
                            source_images = file_metadata.get('source_images', [])
                            if not isinstance(source_images, list):
                                source_images = []
                            print(f"[Detection] {filename} -> {'OUTPUT' if is_output else 'INPUT'} (from metadata, prefix={job_prefix})")
                        except Exception as e:
                            print(f"[Loader] Error reading metadata fields for {filename}: {e}")
                            is_output = None
                            job_prefix = None
                            has_metadata = False

                    # Fall back to filename pattern detection if metadata missing or invalid
                    if is_output is None or job_prefix is None:
                        try:
                            job_prefix, is_output = extract_job_prefix(filename)
                        except Exception as e:
                            print(f"[Loader] Error extracting prefix from {filename}: {e}")
                            job_prefix = None
                            is_output = False  # Default to input if all detection fails

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
                                'is_bundled': True
                            })
                        else:
                            if filename not in bundled_files:
                                items.append(items_dict[filename])
                else:
                    # No bundling - just add all items
                    items.extend(items_dict.values())

        except Exception as e:
            print(f"Error scanning gallery directory: {e}")

        return items

    @staticmethod
    def enrich_prewarm_items(items):
        """Enrich pre-warmed items with workflow metadata and job prefix (runs on worker thread).

        Uses metadata-based detection first, falls back to filename patterns for legacy files.

        Args:
            items: List of item dicts from pre-warm cache

        Returns:
            list: Items with workflow metadata, job prefix, and source info added
        """
        # Import metadata functions with error handling
        try:
            from comfyui.service import load_gallery_metadata, get_workflow_preset_for_files, _lookup_file_metadata
        except ImportError as e:
            print(f"[Prewarm] Failed to import metadata functions: {e}")
            # Fall back to filename pattern for all items
            for item in items:
                if 'workflow' not in item:
                    item['workflow'] = ''
                if 'job_prefix' not in item:
                    try:
                        filename = os.path.basename(item.get('path', ''))
                        job_prefix, is_output = extract_job_prefix(filename)
                        item['job_prefix'] = job_prefix
                        item['is_input'] = not is_output
                        item['source_images'] = []
                    except Exception as e:
                        print(f"[Prewarm] Error extracting prefix: {e}")
                        item['job_prefix'] = None
                        item['is_input'] = True
                        item['source_images'] = []
            return items

        # Group items by directory for batch metadata loading
        items_by_dir = {}  # dir_path -> [item, ...]
        for item in items:
            if not isinstance(item, dict) or 'path' not in item:
                continue
            try:
                output_dir = os.path.dirname(item['path'])
                if output_dir not in items_by_dir:
                    items_by_dir[output_dir] = []
                items_by_dir[output_dir].append(item)
            except Exception as e:
                print(f"[Prewarm] Error grouping item: {e}")

        # Batch load metadata per directory
        for output_dir, dir_items in items_by_dir.items():
            full_metadata = {}
            workflow_map = {}

            # Try to load metadata
            try:
                full_metadata = load_gallery_metadata(output_dir)
                if not isinstance(full_metadata, dict):
                    full_metadata = {}
            except Exception as e:
                print(f"[Prewarm] Error loading metadata from {output_dir}: {e}")
                full_metadata = {}

            # Try to load workflow presets
            try:
                filenames = [os.path.basename(item['path']) for item in dir_items]
                workflow_map = get_workflow_preset_for_files(output_dir, filenames)
                if not isinstance(workflow_map, dict):
                    workflow_map = {}
            except Exception as e:
                print(f"[Prewarm] Error loading workflow presets from {output_dir}: {e}")
                workflow_map = {}

            # Enrich each item
            for item in dir_items:
                try:
                    filename = os.path.basename(item.get('path', ''))
                    if not filename:
                        continue

                    # Update workflow if missing
                    if 'workflow' not in item or not item['workflow']:
                        item['workflow'] = workflow_map.get(filename, '')

                    # Update job_prefix and is_input if missing
                    if 'job_prefix' not in item:
                        file_metadata = None

                        # Try metadata-based detection
                        if full_metadata:
                            try:
                                file_metadata = _lookup_file_metadata(full_metadata, filename)
                            except Exception as e:
                                print(f"[Prewarm] Error looking up metadata for {filename}: {e}")

                        if file_metadata and isinstance(file_metadata, dict) and 'is_output' in file_metadata:
                            # Use metadata-based detection
                            try:
                                is_output = file_metadata.get('is_output', True)
                                job_prefix = file_metadata.get('job_prefix')
                                source_images = file_metadata.get('source_images', [])
                                if not isinstance(source_images, list):
                                    source_images = []
                                item['source_images'] = source_images
                                print(f"[Prewarm] {filename} -> {'OUTPUT' if is_output else 'INPUT'} (from metadata, prefix={job_prefix})")
                            except Exception as e:
                                print(f"[Prewarm] Error reading metadata fields for {filename}: {e}")
                                # Fall back to filename pattern
                                job_prefix, is_output = extract_job_prefix(filename)
                                item['source_images'] = []
                        else:
                            # Fall back to filename pattern
                            job_prefix, is_output = extract_job_prefix(filename)
                            item['source_images'] = []

                        item['job_prefix'] = job_prefix
                        item['is_input'] = not is_output

                except Exception as e:
                    print(f"[Prewarm] Error enriching item {item.get('path', 'unknown')}: {e}")
                    # Set safe defaults
                    if 'workflow' not in item:
                        item['workflow'] = ''
                    if 'job_prefix' not in item:
                        item['job_prefix'] = None
                        item['is_input'] = True
                        item['source_images'] = []

        return items

    @staticmethod
    def discover_users(network_path):
        """Discover available users by scanning the network output path (worker thread).

        Args:
            network_path: Path to network output directory

        Returns:
            list: Sorted list of usernames (folder names in network output path)
        """
        print(f"[Gallery] Discovering users in: {network_path}")

        if not network_path:
            print("[Gallery] No network output path configured")
            return []

        if not os.path.isdir(network_path):
            print(f"[Gallery] Network path does not exist or is not accessible: {network_path}")
            return []

        users = []
        try:
            for entry in os.scandir(network_path):
                # Only include directories, skip hidden folders
                if entry.is_dir() and not entry.name.startswith('.'):
                    users.append(entry.name)
            print(f"[Gallery] Found {len(users)} users: {users}")
        except Exception as e:
            print(f"[Gallery] Error scanning users: {e}")
            return []

        return sorted(users, key=str.lower)

    @staticmethod
    def collect_watch_directories(output_dir):
        """Collect all directories to watch (runs on worker thread).

        Args:
            output_dir: Root directory to collect subdirectories from

        Returns:
            tuple: (output_dir, list of all directories) or None if output_dir doesn't exist
        """
        # Check if directory exists (can be slow on network paths)
        if not os.path.isdir(output_dir):
            return None

        dirs_to_watch = [output_dir]
        for root, dirs, files in os.walk(output_dir):
            for dir_name in dirs:
                dirs_to_watch.append(os.path.join(root, dir_name))
        return (output_dir, dirs_to_watch)
