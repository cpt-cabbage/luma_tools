"""
Error handling utilities for consistent error logging and handling.

Provides decorators and context managers for cleaner error handling.
"""

import functools
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Default log function uses the module logger instead of print
_default_log = logger.error


def safe_operation(operation_name, return_on_error=None, log_func=None):
    """
    Decorator for consistent error handling with logging.

    Args:
        operation_name: Description of the operation (e.g., "finding render directory")
        return_on_error: Value to return on exception (default: None)
        log_func: Function to log errors (default: logger.error)

    Example:
        @safe_operation("reading config file", return_on_error={})
        def read_config(path):
            with open(path) as f:
                return json.load(f)
    """
    if log_func is None:
        log_func = _default_log

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log_func(f"Error {operation_name}: {e}")
                return return_on_error
        return wrapper
    return decorator


@contextmanager
def handle_errors(operation_name, log_func=None, reraise=False):
    """
    Context manager for consistent error handling.

    Args:
        operation_name: Description of the operation
        log_func: Function to log errors (default: logger.error)
        reraise: Whether to re-raise the exception after logging

    Example:
        with handle_errors("deleting file"):
            os.remove(path)

        # With re-raise
        with handle_errors("parsing JSON", reraise=True):
            data = json.loads(content)
    """
    if log_func is None:
        log_func = _default_log

    try:
        yield
    except Exception as e:
        log_func(f"Error {operation_name}: {e}")
        if reraise:
            raise


def log_error(operation_name, error, variable=None, log_func=None):
    """
    Consistent error logging helper.

    Args:
        operation_name: Description of what was being done
        error: The exception or error message
        variable: Optional variable/path that was being processed
        log_func: Function to log errors (default: logger.error)

    Example:
        except Exception as e:
            log_error("reading file", e, file_path)
    """
    if log_func is None:
        log_func = _default_log

    if variable is not None:
        log_func(f"Error {operation_name} {variable}: {error}")
    else:
        log_func(f"Error {operation_name}: {error}")
