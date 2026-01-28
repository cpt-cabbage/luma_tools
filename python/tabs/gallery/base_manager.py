"""
Base Gallery Manager class.

Provides common functionality for all gallery manager components:
- Tab reference and state access
- Convenience properties for common tab attributes
- Logging and status message helpers
- Worker thread management (delegates to tab, stores reference locally)
"""

from typing import Callable, Optional, Set, Dict, Any


class BaseGalleryManager:
    """Base class for gallery manager components."""

    def __init__(self, tab):
        """
        Initialize the manager.

        Args:
            tab: Reference to the ComfyUIGalleryTab
        """
        self.tab = tab
        # Worker reference storage (prevents GC)
        # Each manager stores its own worker to allow concurrent operations
        self._worker = None

    # =========================================================================
    # Convenience Properties
    # =========================================================================

    @property
    def app_state(self):
        """Get the global application state."""
        return self.tab.app_state

    @property
    def main_window(self):
        """Get the main window reference."""
        return self.tab.main_window

    @property
    def ui(self):
        """Get the tab's UI."""
        return self.tab.ui

    @property
    def selected_items(self) -> Set[str]:
        """Get the set of selected item paths."""
        return self.tab._selected_items

    @property
    def widget_cache(self) -> Dict[str, Any]:
        """Get the widget cache dictionary."""
        return self.tab._widget_cache

    @property
    def cached_items(self):
        """Get the cached items list."""
        return self.tab._cached_items

    @property
    def flow_layout(self):
        """Get the flow layout."""
        return self.tab._flow_layout

    # =========================================================================
    # Logging and Status
    # =========================================================================

    def log(self, message: str):
        """Log a message via the tab."""
        self.tab.log(message)

    def show_status(self, message: str, level: str = "info"):
        """Show a status message. Delegates to tab's show_status."""
        self.tab.show_status(message, level)

    def update_status_with_spinner(self, message: str, color, start: bool = True):
        """
        Update status bar with spinner control.

        Args:
            message: Status message
            color: StatusColors enum value
            start: If True, start spinner; if False, stop it
        """
        self.tab.update_status_with_spinner(message, color, start=start)

    # =========================================================================
    # Worker Thread Management
    # =========================================================================

    def start_worker(
        self,
        func: Callable,
        *args,
        on_result: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        worker_kwargs: Optional[Dict[str, Any]] = None
    ):
        """
        Start a worker thread with standard signal connections.

        Worker is stored on self._worker to prevent garbage collection.
        Each manager stores its own worker to allow concurrent operations.

        Args:
            func: Function to run in worker thread
            *args: Arguments to pass to the function
            on_result: Optional callback for successful completion
            on_error: Optional callback for errors (receives msg, traceback)
            on_progress: Optional callback for progress updates
            worker_kwargs: Optional dict of keyword arguments for the function
        """
        from workers import start_worker_thread
        self._worker = start_worker_thread(
            func, *args,
            on_result=on_result,
            on_error=on_error,
            on_progress=on_progress,
            worker_kwargs=worker_kwargs
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def is_own_gallery(self) -> bool:
        """Check if we're viewing our own gallery."""
        if hasattr(self.tab, '_is_own_gallery'):
            return self.tab._is_own_gallery()
        return True

    def get_output_dir(self) -> str:
        """Get the current output directory."""
        if hasattr(self.tab, '_output_dir'):
            return self.tab._output_dir
        return ""
