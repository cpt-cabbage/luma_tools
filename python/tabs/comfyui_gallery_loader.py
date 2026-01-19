"""
ComfyUI Gallery Loader module.

Handles async loading operations for the gallery:
- Directory scanning
- Metadata extraction
- User discovery
- File system watching
"""

import os

# Supported file extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.exr'}
MODEL_EXTENSIONS = {'.glb', '.gltf', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz', '.dae'}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | MODEL_EXTENSIONS


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
            for dir_path, file_list in files_by_dir.items():
                # Get workflow presets if metadata loading is enabled
                workflow_map = {}
                if load_metadata:
                    from comfyui.service import get_workflow_preset_for_files
                    filenames = [f[0] for f in file_list]
                    try:
                        workflow_map = get_workflow_preset_for_files(dir_path, filenames)
                    except Exception:
                        pass

                # Build items dict
                items_dict = {}
                for filename, full_path, mtime, file_type in file_list:
                    items_dict[filename] = {
                        'path': full_path,
                        'mtime': mtime,
                        'type': file_type,
                        'name': filename.lower(),
                        'workflow': workflow_map.get(filename, '')
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
        """Enrich pre-warmed items with workflow metadata (runs on worker thread).

        Args:
            items: List of item dicts from pre-warm cache

        Returns:
            list: Items with workflow metadata added
        """
        from comfyui.service import get_workflow_preset_for_files

        # Group items by directory for batch metadata loading
        items_by_dir = {}  # dir_path -> [item, ...]
        for item in items:
            if 'workflow' not in item or not item['workflow']:
                output_dir = os.path.dirname(item['path'])
                if output_dir not in items_by_dir:
                    items_by_dir[output_dir] = []
                items_by_dir[output_dir].append(item)

        # Batch load metadata per directory
        for output_dir, dir_items in items_by_dir.items():
            try:
                filenames = [os.path.basename(item['path']) for item in dir_items]
                workflow_map = get_workflow_preset_for_files(output_dir, filenames)
                for item in dir_items:
                    filename = os.path.basename(item['path'])
                    item['workflow'] = workflow_map.get(filename, '')
            except Exception:
                for item in dir_items:
                    item['workflow'] = ''

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
