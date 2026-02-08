"""
Progress reporting utilities for background operations.

Provides a single source of truth for progress reporting with optional Qt event processing.
"""

import logging

logger = logging.getLogger(__name__)


def report_progress(callback, progress, message):
    """
    Report progress via callback.

    This utility consolidates the common pattern of:
    - Checking if callback exists
    - Calling the callback

    The callback (typically Worker's progress_callback) emits a cross-thread
    signal that safely updates the UI from the main thread.

    Args:
        callback: Progress callback function(progress, message) or None
        progress: Progress value (0-100)
        message: Status message string

    Example:
        report_progress(progress_callback, 50, "Halfway done...")
    """
    if callback:
        callback(progress, message)
        # Note: Do NOT call processEvents() here. This function is typically called
        # from worker threads where processEvents() is unsafe and can cause
        # re-entrancy crashes. The Worker's progress signal already delivers
        # updates to the main thread safely.
