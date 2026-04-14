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
            tab: Reference to the GalleryTab
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
        """Get the widget cache dictionary.

        WARNING: For iteration, use get_widget_cache_copy() to avoid race conditions.
        For single-item access, prefer get_cached_widget() / set_cached_widget().
        """
        return self.tab._widget_cache

    # =========================================================================
    # Thread-Safe Cache Access (delegates to tab)
    # =========================================================================

    def get_cached_widget(self, path: str):
        """Thread-safe access to get a widget from cache."""
        return self.tab.get_cached_widget(path)

    def set_cached_widget(self, path: str, widget):
        """Thread-safe access to set a widget in cache."""
        self.tab.set_cached_widget(path, widget)

    def remove_cached_widget(self, path: str):
        """Thread-safe access to remove a widget from cache."""
        return self.tab.remove_cached_widget(path)

    def clear_widget_cache(self):
        """Thread-safe access to clear all widgets from cache."""
        self.tab.clear_widget_cache()

    def get_widget_cache_copy(self) -> Dict[str, Any]:
        """Thread-safe access to get a copy of the widget cache for iteration."""
        return self.tab.get_widget_cache_copy()

    def get_section_items_copy(self) -> Dict[str, Any]:
        """Thread-safe access to get a copy of section items for iteration."""
        return self.tab.get_section_items_copy()

    def set_section_items(self, section_id: str, items: list):
        """Thread-safe access to set section items."""
        self.tab.set_section_items(section_id, items)

    def clear_section_items(self):
        """Thread-safe access to clear section items."""
        self.tab.clear_section_items()

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

        Workers are stored in self._active_workers list to prevent garbage
        collection, even when multiple operations run concurrently. Completed
        workers are pruned on each new start.

        Args:
            func: Function to run in worker thread
            *args: Arguments to pass to the function
            on_result: Optional callback for successful completion
            on_error: Optional callback for errors (receives msg, traceback)
            on_progress: Optional callback for progress updates
            worker_kwargs: Optional dict of keyword arguments for the function
        """
        from workers import start_worker_thread
        if not hasattr(self, '_active_workers'):
            self._active_workers = []
        # Prune completed workers (those whose QRunnable has finished)
        self._active_workers = [w for w in self._active_workers if w is not None]
        worker = start_worker_thread(
            func, *args,
            on_result=on_result,
            on_error=on_error,
            on_progress=on_progress,
            worker_kwargs=worker_kwargs
        )
        self._active_workers.append(worker)

    # =========================================================================
    # Settings Helpers
    # =========================================================================

    def get_setting(self, key: str, default=None):
        """
        Get a setting value.

        Args:
            key: Setting key
            default: Default value if setting not found

        Returns:
            Setting value or default
        """
        from core.settings_manager import safe_get_setting
        return safe_get_setting(key, default)

    def set_setting(self, key: str, value, verbose: bool = False):
        """
        Set a setting value.

        Args:
            key: Setting key
            value: Value to set
            verbose: If True, log the setting change

        Returns:
            bool: True if successful
        """
        from core.settings_manager import set_setting
        return set_setting(key, value, verbose=verbose)

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
