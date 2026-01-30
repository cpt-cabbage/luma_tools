"""
Progress reporting utilities for background operations.

Provides a single source of truth for progress reporting with optional Qt event processing.
"""

import logging

logger = logging.getLogger(__name__)


def report_progress(callback, progress, message):
    """
    Report progress and process Qt events to keep UI responsive.

    This utility consolidates the common pattern of:
    - Checking if callback exists
    - Calling the callback
    - Processing Qt events to keep the UI responsive (if Qt available)

    Args:
        callback: Progress callback function(progress, message) or None
        progress: Progress value (0-100)
        message: Status message string

    Example:
        report_progress(progress_callback, 50, "Halfway done...")
    """
    if callback:
        callback(progress, message)
        # Process events if Qt is available (non-blocking)
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.processEvents()
        except ImportError:
            pass  # Qt not available, skip processEvents
