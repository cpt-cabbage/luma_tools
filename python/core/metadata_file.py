"""
Thread-safe JSON metadata file handling with caching.

Provides a reusable abstraction for JSON files that are:
- Frequently read but less frequently written
- Accessed from multiple threads
- Need mtime-based cache invalidation

Usage:
    metadata = MetadataFile(output_dir, "my_metadata.json")
    data = metadata.load()  # Returns cached data if file unchanged
    data["key"] = "value"
    metadata.save(data)  # Atomic write, clears cache
"""

import json
import logging
import os
import threading
from typing import Any, Dict, Optional

from core.utils import ensure_directory

logger = logging.getLogger(__name__)


class MetadataFile:
    """
    Thread-safe JSON metadata file with mtime-based caching.

    Features:
    - Thread-safe read/write via RLock
    - Automatic cache invalidation on file modification
    - Atomic writes (write to temp, then rename)
    - Graceful handling of missing/corrupted files

    Example:
        metadata = MetadataFile("/path/to/dir", "settings.json")

        # Read (uses cache if file unchanged)
        data = metadata.load(default={})

        # Modify and save
        data["setting"] = "value"
        if metadata.save(data):
            print("Saved!")

        # Force cache refresh
        metadata.clear_cache()
    """

    def __init__(self, directory: str, filename: str):
        """
        Initialize a metadata file handler.

        Args:
            directory: Directory containing the metadata file
            filename: Name of the metadata file (e.g., "metadata.json")
        """
        self._directory = directory
        self._filename = filename
        self._lock = threading.RLock()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_mtime: float = 0.0

    @property
    def path(self) -> str:
        """Full path to the metadata file."""
        return os.path.join(self._directory, self._filename)

    @property
    def exists(self) -> bool:
        """Check if the metadata file exists."""
        return os.path.exists(self.path)

    def clear_cache(self) -> None:
        """Clear the in-memory cache, forcing next load to read from disk."""
        with self._lock:
            self._cache = None
            self._cache_mtime = 0.0

    def load(self, default: Optional[Dict[str, Any]] = None, use_cache: bool = True) -> Dict[str, Any]:
        """
        Load metadata from file, using cache if available and file unchanged.

        Thread-safe: Uses RLock for cache access.

        Args:
            default: Value to return if file is missing/corrupted (default: empty dict)
            use_cache: Whether to use cached data if available (default: True)

        Returns:
            Dict with metadata, or default if file missing/corrupted
        """
        if default is None:
            default = {}

        if not self._directory:
            return default

        metadata_path = self.path

        if not os.path.exists(metadata_path):
            return default

        try:
            current_mtime = os.path.getmtime(metadata_path)

            # Check cache (thread-safe)
            if use_cache:
                with self._lock:
                    if self._cache is not None and self._cache_mtime == current_mtime:
                        return self._cache

            # Load from file (outside lock - file I/O can be slow)
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate data is a dict
            if not isinstance(data, dict):
                logger.warning(
                    f"[MetadataFile] Invalid format in {metadata_path}, "
                    f"expected dict but got {type(data).__name__}"
                )
                return default

            # Update cache (thread-safe)
            with self._lock:
                self._cache = data
                self._cache_mtime = current_mtime

            return data

        except json.JSONDecodeError as e:
            logger.error(f"[MetadataFile] Corrupted JSON in {metadata_path}: {e}")
            return default
        except Exception as e:
            logger.error(f"[MetadataFile] Error loading {metadata_path}: {e}")
            return default

    def save(self, data: Dict[str, Any], indent: int = 2) -> bool:
        """
        Save metadata to file with atomic write.

        Thread-safe: Uses RLock and atomic file operations.

        Args:
            data: Dict to save as JSON
            indent: JSON indentation (default: 2)

        Returns:
            True if saved successfully, False on error
        """
        metadata_path = self.path

        try:
            ensure_directory(self._directory)

            # Atomic write: write to temp file, then rename
            temp_path = metadata_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, default=str)

            # Atomic rename (on same filesystem)
            os.replace(temp_path, metadata_path)

            # Clear cache to force re-read on next load
            self.clear_cache()

            return True

        except Exception as e:
            logger.error(f"[MetadataFile] Error saving {metadata_path}: {e}")
            # Clean up temp file if it exists
            temp_path = metadata_path + ".tmp"
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return False

    def update(self, key: str, value: Any) -> bool:
        """
        Update a single key in the metadata file.

        Convenience method that loads, updates, and saves atomically.

        Args:
            key: Key to update
            value: New value

        Returns:
            True if saved successfully, False on error
        """
        data = self.load()
        data[key] = value
        return self.save(data)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a single value from the metadata file.

        Convenience method for single key access.

        Args:
            key: Key to retrieve
            default: Default value if key not found

        Returns:
            Value for key, or default
        """
        data = self.load()
        return data.get(key, default)

    def delete(self) -> bool:
        """
        Delete the metadata file and clear cache.

        Returns:
            True if deleted or didn't exist, False on error
        """
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
            self.clear_cache()
            return True
        except Exception as e:
            logger.error(f"[MetadataFile] Error deleting {self.path}: {e}")
            return False


# Module-level cache for MetadataFile instances
# Allows reusing the same MetadataFile object for repeated access to the same file
_metadata_file_cache: Dict[str, MetadataFile] = {}
_metadata_file_cache_lock = threading.RLock()


def get_metadata_file(directory: str, filename: str) -> MetadataFile:
    """
    Get or create a MetadataFile instance for the given path.

    Uses a module-level cache to reuse MetadataFile objects, which preserves
    their internal caching across calls.

    Args:
        directory: Directory containing the metadata file
        filename: Name of the metadata file

    Returns:
        MetadataFile instance
    """
    key = os.path.join(directory, filename)

    with _metadata_file_cache_lock:
        if key not in _metadata_file_cache:
            _metadata_file_cache[key] = MetadataFile(directory, filename)
        return _metadata_file_cache[key]


def clear_metadata_file_cache(directory: str = None, filename: str = None) -> None:
    """
    Clear the module-level MetadataFile cache.

    Args:
        directory: If provided with filename, clear only that specific entry
        filename: If provided with directory, clear only that specific entry
                  If neither provided, clear entire cache
    """
    with _metadata_file_cache_lock:
        if directory and filename:
            key = os.path.join(directory, filename)
            _metadata_file_cache.pop(key, None)
        else:
            _metadata_file_cache.clear()
