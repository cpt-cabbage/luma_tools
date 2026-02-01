"""
Path and data validation utilities for luma_tools.

Provides consistent validation patterns:
- Boolean checks: is_valid_file(), is_valid_directory(), is_writable()
- Validate-or-raise: validate_file(), validate_directory()
- Safe operations: safe_list_dir()
- Custom ValidationError exception

Naming convention:
- is_*() functions return bool, never raise
- validate_*() functions raise ValidationError on failure

Usage:
    from core.validators import is_valid_file, validate_directory, ValidationError

    # Boolean check (returns True/False)
    if is_valid_file(path):
        process(path)

    # Validate or raise
    try:
        validate_directory(output_path)
    except ValidationError as e:
        logger.error(f"Invalid path: {e}")
"""

import fnmatch
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """
    Raised when validation fails.

    Provides consistent error handling for validation operations.
    """
    pass


# ============================================================================
# BOOLEAN VALIDATORS (return True/False, never raise)
# ============================================================================

def is_valid_path(path: str) -> bool:
    """
    Check if path is a non-empty string.

    Args:
        path: Path to check

    Returns:
        True if path is non-empty string, False otherwise
    """
    return bool(path and isinstance(path, str))


def is_valid_file(path: str) -> bool:
    """
    Check if path exists and is a file.

    Args:
        path: Path to check

    Returns:
        True if path is an existing file, False otherwise
    """
    return bool(path and os.path.isfile(path))


def is_valid_directory(path: str) -> bool:
    """
    Check if path exists and is a directory.

    Args:
        path: Path to check

    Returns:
        True if path is an existing directory, False otherwise
    """
    return bool(path and os.path.isdir(path))


def is_writable(path: str) -> bool:
    """
    Check if path is writable.

    For existing paths, checks write permission.
    For non-existing paths, checks if parent directory is writable.

    Args:
        path: Path to check

    Returns:
        True if path is writable, False otherwise
    """
    if not path:
        return False

    if os.path.exists(path):
        return os.access(path, os.W_OK)

    # Check parent directory
    parent = os.path.dirname(path)
    if parent and os.path.isdir(parent):
        return os.access(parent, os.W_OK)

    return False


def is_readable(path: str) -> bool:
    """
    Check if path exists and is readable.

    Args:
        path: Path to check

    Returns:
        True if path is readable, False otherwise
    """
    return bool(path and os.path.exists(path) and os.access(path, os.R_OK))


# ============================================================================
# VALIDATE-OR-RAISE FUNCTIONS (raise ValidationError on failure)
# ============================================================================

def validate_file(path: str, must_exist: bool = True, must_be_readable: bool = False) -> str:
    """
    Validate that path is a valid file.

    Args:
        path: Path to validate
        must_exist: If True, file must exist (default: True)
        must_be_readable: If True, file must be readable (default: False)

    Returns:
        The validated path (for chaining)

    Raises:
        ValidationError: If validation fails
    """
    if not is_valid_path(path):
        raise ValidationError("File path is empty or None")

    if must_exist:
        if not os.path.exists(path):
            raise ValidationError(f"File not found: {path}")
        if not os.path.isfile(path):
            raise ValidationError(f"Path is not a file: {path}")

    if must_be_readable and not is_readable(path):
        raise ValidationError(f"File is not readable: {path}")

    return path


def validate_directory(path: str, must_exist: bool = True, create: bool = False) -> str:
    """
    Validate that path is a valid directory.

    Args:
        path: Path to validate
        must_exist: If True, directory must exist (default: True)
        create: If True and directory doesn't exist, create it (default: False)

    Returns:
        The validated path (for chaining)

    Raises:
        ValidationError: If validation fails
    """
    if not is_valid_path(path):
        raise ValidationError("Directory path is empty or None")

    if os.path.exists(path):
        if not os.path.isdir(path):
            raise ValidationError(f"Path is not a directory: {path}")
    elif must_exist:
        if create:
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as e:
                raise ValidationError(f"Failed to create directory {path}: {e}")
        else:
            raise ValidationError(f"Directory not found: {path}")

    return path


def validate_file_for_operation(path: str, operation: str = "access") -> bool:
    """
    Check if file exists and log error if not.

    This is a convenience function that returns bool and logs errors,
    useful for operations that should continue on failure.

    Args:
        path: File path to validate
        operation: Description for error message (e.g., "read", "process")

    Returns:
        True if file exists, False otherwise (with error logged)
    """
    if not path:
        logger.error(f"Cannot {operation}: path is empty or None")
        return False
    if not os.path.isfile(path):
        logger.error(f"Cannot {operation}: file does not exist: {path}")
        return False
    return True


def validate_directory_for_operation(path: str, operation: str = "access") -> bool:
    """
    Check if directory exists and log error if not.

    This is a convenience function that returns bool and logs errors,
    useful for operations that should continue on failure.

    Args:
        path: Directory path to validate
        operation: Description for error message (e.g., "scan", "write")

    Returns:
        True if directory exists, False otherwise (with error logged)
    """
    if not path:
        logger.error(f"Cannot {operation}: path is empty or None")
        return False
    if not os.path.isdir(path):
        logger.error(f"Cannot {operation}: directory does not exist: {path}")
        return False
    return True


# ============================================================================
# SAFE OPERATIONS (handle errors gracefully)
# ============================================================================

def safe_list_dir(path: str, pattern: Optional[str] = None) -> List[str]:
    """
    Safely list directory contents with error handling.

    Args:
        path: Directory to list
        pattern: Optional glob pattern to filter (e.g., "*.png")

    Returns:
        List of filenames, empty list on error or invalid path
    """
    if not is_valid_directory(path):
        return []

    try:
        entries = os.listdir(path)
        if pattern:
            return [f for f in entries if fnmatch.fnmatch(f, pattern)]
        return entries
    except OSError as e:
        logger.warning(f"Error listing directory {path}: {e}")
        return []


def safe_file_stat(path: str) -> Optional[os.stat_result]:
    """
    Safely get file stats without raising exceptions.

    Args:
        path: Path to stat

    Returns:
        os.stat_result or None if path invalid/inaccessible
    """
    if not path:
        return None
    try:
        return os.stat(path)
    except OSError:
        return None


def safe_path_join(*parts: str) -> str:
    """
    Safely join path parts, filtering empty/None values.

    Args:
        *parts: Path components to join

    Returns:
        Joined path, or empty string if no valid parts
    """
    valid_parts = [p for p in parts if p]
    if not valid_parts:
        return ""
    return os.path.join(*valid_parts)


# ============================================================================
# COMPATIBILITY FUNCTIONS
# ============================================================================

def validate_file_exists(path: str, raise_error: bool = True) -> bool:
    """
    Validate that a file exists.

    Args:
        path: Path to validate
        raise_error: If True, raise FileNotFoundError; otherwise return False

    Returns:
        True if file exists

    Raises:
        FileNotFoundError: If file doesn't exist and raise_error is True
    """
    if not os.path.exists(path):
        if raise_error:
            raise FileNotFoundError(f"File not found: {path}")
        return False
    return True


def validate_is_file(path: str, raise_error: bool = True) -> bool:
    """
    Validate that path is a file (not a directory).

    Args:
        path: Path to validate
        raise_error: If True, raise ValueError; otherwise return False

    Returns:
        True if path is a file

    Raises:
        ValueError: If path is not a file and raise_error is True
    """
    if not os.path.isfile(path):
        if raise_error:
            raise ValueError(f"Path is not a file: {path}")
        return False
    return True


def validate_is_directory(path: str, raise_error: bool = True) -> bool:
    """
    Validate that path is a directory.

    Args:
        path: Path to validate
        raise_error: If True, raise ValueError; otherwise return False

    Returns:
        True if path is a directory

    Raises:
        ValueError: If path is not a directory and raise_error is True
    """
    if not os.path.isdir(path):
        if raise_error:
            raise ValueError(f"Path is not a directory: {path}")
        return False
    return True
