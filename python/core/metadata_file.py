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
import time
from typing import Any, Callable, Dict, Optional

# Farm isolation: this module is copied to the flat _job_data dir as
# `comfyui_metadata_file.py`, where the `core` package is not available.
try:
    from core.utils import ensure_directory
except ImportError:
    def ensure_directory(path):
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

logger = logging.getLogger(__name__)

# Cross-process lockfile tuning. Writers on other machines (farm workers,
# other workstations) coordinate through a `<path>.lock` sentinel created
# with O_EXCL, which is atomic on SMB shares.
_LOCKFILE_TIMEOUT_SECONDS = 5.0
_LOCKFILE_STALE_SECONDS = 30.0


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
        # Cross-process lockfile state (guarded by self._lock; the depth
        # counter makes the file lock reentrant within a thread)
        self._flock_fd: Optional[int] = None
        self._flock_depth: int = 0

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

        Thread-safe: Uses RLock for cache check, file read, and cache update
        to prevent TOCTOU races between mtime check and file read.

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
            with self._lock:
                current_mtime = os.path.getmtime(metadata_path)

                # Check cache
                if use_cache:
                    if self._cache is not None and self._cache_mtime == current_mtime:
                        # Return a shallow copy so callers can mutate the result
                        # without corrupting the in-memory cache.
                        return dict(self._cache)

                # Load from file (under lock to prevent TOCTOU race between
                # mtime check and file read — another thread could modify the
                # file between the two operations)
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Validate data is a dict
                if not isinstance(data, dict):
                    logger.warning(
                        f"[MetadataFile] Invalid format in {metadata_path}, "
                        f"expected dict but got {type(data).__name__}"
                    )
                    return default

                # Update cache (store a copy so subsequent caller mutations
                # don't reach back through the cache reference)
                self._cache = dict(data)
                self._cache_mtime = current_mtime

                return data

        except json.JSONDecodeError as e:
            logger.error(f"[MetadataFile] Corrupted JSON in {metadata_path}: {e}")
            return default
        except Exception as e:
            logger.error(f"[MetadataFile] Error loading {metadata_path}: {e}")
            return default

    def _acquire_file_lock(self) -> None:
        """Acquire the cross-process lockfile. Call with self._lock held.

        Reentrant within a thread via a depth counter. On timeout or lockfile
        creation failure, proceeds without the lock (availability over strict
        consistency) after logging — a wedged lockfile must never stop saves.
        """
        if self._flock_depth > 0:
            self._flock_depth += 1
            return

        lock_path = self.path + ".lock"
        deadline = time.monotonic() + _LOCKFILE_TIMEOUT_SECONDS
        fd = None
        while True:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                # Break locks left behind by crashed processes
                try:
                    if time.time() - os.path.getmtime(lock_path) > _LOCKFILE_STALE_SECONDS:
                        os.remove(lock_path)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    logger.warning(
                        f"[MetadataFile] Timed out waiting for {lock_path}; "
                        f"proceeding without cross-process lock"
                    )
                    break
                time.sleep(0.05)
            except OSError as e:
                logger.debug(f"[MetadataFile] Could not create lockfile {lock_path}: {e}")
                break

        self._flock_fd = fd
        self._flock_depth = 1

    def _release_file_lock(self) -> None:
        """Release the cross-process lockfile. Call with self._lock held."""
        if self._flock_depth == 0:
            return
        self._flock_depth -= 1
        if self._flock_depth > 0:
            return
        fd = self._flock_fd
        self._flock_fd = None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.remove(self.path + ".lock")
            except OSError:
                pass

    def save(self, data: Dict[str, Any], indent: int = 2) -> bool:
        """
        Save metadata to file with atomic write.

        Thread-safe (RLock) and cross-process safe: writes go to a temp file
        unique per process/thread, then os.replace() under a lockfile so
        concurrent writers on other machines don't interleave.

        Args:
            data: Dict to save as JSON
            indent: JSON indentation (default: 2)

        Returns:
            True if saved successfully, False on error
        """
        metadata_path = self.path
        # Unique per process AND thread so concurrent savers never share a temp file
        temp_path = f"{metadata_path}.{os.getpid()}.{threading.get_ident()}.tmp"

        with self._lock:
            try:
                ensure_directory(self._directory)
                self._acquire_file_lock()
                try:
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=indent, default=str)
                    # Atomic rename (on same filesystem)
                    os.replace(temp_path, metadata_path)
                finally:
                    self._release_file_lock()

                # Clear cache to force re-read on next load
                self.clear_cache()
                return True

            except Exception as e:
                logger.error(f"[MetadataFile] Error saving {metadata_path}: {e}")
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                return False

    def mutate(self, mutator: Callable[[Dict[str, Any]], None]) -> bool:
        """
        Atomically load, modify, and save the metadata file.

        Holds both the in-process RLock and the cross-process lockfile across
        the whole read-modify-write, so concurrent writers (other threads,
        other processes, farm workers) can't lose each other's updates.

        Args:
            mutator: Callable that mutates the loaded dict in place

        Returns:
            True if saved successfully, False on error
        """
        with self._lock:
            try:
                ensure_directory(self._directory)
            except Exception as e:
                logger.error(f"[MetadataFile] Error creating {self._directory}: {e}")
                return False
            self._acquire_file_lock()
            try:
                data = self.load(use_cache=False)
                mutator(data)
                return self.save(data)
            except Exception as e:
                logger.error(f"[MetadataFile] Error mutating {self.path}: {e}")
                return False
            finally:
                self._release_file_lock()

    def update(self, key: str, value: Any) -> bool:
        """
        Update a single key in the metadata file.

        Convenience method that loads, updates, and saves atomically
        (cross-process safe via mutate()).

        Args:
            key: Key to update
            value: New value

        Returns:
            True if saved successfully, False on error
        """
        def _set(data: Dict[str, Any]) -> None:
            data[key] = value
        return self.mutate(_set)

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
    # Normalize path for consistent cache keys on Windows (C:/path vs C:\\path)
    key = os.path.normpath(os.path.join(directory, filename))

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
            key = os.path.normpath(os.path.join(directory, filename))
            _metadata_file_cache.pop(key, None)
        else:
            _metadata_file_cache.clear()
