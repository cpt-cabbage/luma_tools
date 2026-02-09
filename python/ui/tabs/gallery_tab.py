"""
Gallery tab module for Luma Tools.

Displays generated images and 3D models in a gallery view.

This tab uses a manager-based architecture for better maintainability:
- SelectionManager: Multi-select, box selection, shift-click
- ViewerManager: Embedded/fullscreen viewer lifecycle
- OperationsManager: Delete, publish, copy settings
- RefreshController: File watching, polling, scanning
- UIManager: Sort, filter, view mode, user selection

Cross-tab communication:
- Subscribes to job events from ComfyUI via PipelineEventBus
- Emits context events when selection/visibility changes
"""

import os
import logging
import threading
import re

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QTimer, QThreadPool

from .base_tab import BaseTab, TabConfig
from .gallery_loader import GalleryLoader
from .gallery import SelectionManager, ViewerManager, OperationsManager, RefreshController, UIManager, GalleryManager
from .gallery.favorites_manager import FavoritesManager
from .gallery.groups_panel import GroupsFilterPanel

logger = logging.getLogger(__name__)


def _validate_username(username: str) -> bool:
    """
    Validate username contains only safe characters.

    Args:
        username: Username to validate

    Returns:
        True if username is valid, False otherwise
    """
    if not username or not isinstance(username, str):
        return False

    # Strip whitespace and check if empty
    username = username.strip()
    if not username:
        return False

    # Only allow alphanumeric, underscore, hyphen, and period
    # This prevents path traversal attacks like "../other_user"
    if not re.match(r'^[a-zA-Z0-9._-]+$', username):
        logger.error(f"[Gallery] Invalid username characters: {username}")
        return False

    return True

from core.import_utils import get_event_bus
pipeline_events, EVENT_BUS_AVAILABLE = get_event_bus()


class GalleryTab(BaseTab):
    """Tab for viewing generated images."""

    TAB_CONFIG = TabConfig(ui_file="gallery.ui", tab_name="Gallery", tab_id="gallery")

    def connect_signals(self):
        """Connect gallery tab signals."""
        self.ui.GalleryOpenExplorer.clicked.connect(self._on_open_explorer)
        self.ui.GalleryRefresh.clicked.connect(self._on_refresh_button_clicked)
        self.ui.GallerySortButton.clicked.connect(self._on_sort_button_clicked)
        self.ui.GalleryUserButton.clicked.connect(self._on_user_button_clicked)

    def _on_refresh_button_clicked(self):
        """Handle manual refresh button click - force immediate refresh."""
        self._refresh_controller.on_refresh(force=True)

    def initialize(self):
        """Initialize the gallery tab."""
        from ui_components import FlowLayout

        # Initialize helper classes (existing)
        self._loader = GalleryLoader()
        self._manager = GalleryManager(self)

        # Setup flow layout for thumbnails
        self._flow_layout = FlowLayout(margin=10, spacing=10)
        self.ui.galleryThumbnailContainer.setLayout(self._flow_layout)

        self._current_path = ""

        # Load gallery settings
        from core.user_preferences import get_gallery_settings
        gallery_settings = get_gallery_settings()
        self._sort_mode = gallery_settings.get("sort_mode", "date_desc")
        self._show_inputs = gallery_settings.get("show_inputs", False)
        self._view_mode = gallery_settings.get("view_mode", "stacked")
        self._collapsed_sections = set(gallery_settings.get("collapsed_sections", []))
        self._type_filters = gallery_settings.get("type_filters", {
            "image": True,
            "video": True,
            "audio": True,
            "model": True
        })
        self._section_items = {}
        self._expanded_stack_id = None
        self._pre_expansion_stacked = False

        # Track known images to detect new additions
        self._known_items = set()
        self._initial_scan_done = False
        self._new_items = set()
        self._first_scan_after_prewarm = False

        # Cache for scanned items
        self._cached_items = None
        self._widget_cache = {}
        self._hash_to_path = {}  # content_hash -> path (secondary index for widget lookups)

        # User selection for multi-user gallery viewing
        # Normalize username: strip whitespace, treat empty as None
        raw_user = self.app_state.user
        self._selected_user = raw_user.strip() if raw_user else None
        self._available_users = []
        self._user_cache = {}
        self._precache_in_progress = set()

        # Thread-safe lock for cache access (protects _widget_cache, _section_items, _user_cache)
        self._cache_lock = threading.RLock()

        # Initialize managers
        self._selection_manager = SelectionManager(self)
        self._viewer_manager = ViewerManager(self)
        self._operations_manager = OperationsManager(self)
        self._refresh_controller = RefreshController(self)
        self._ui_manager = UIManager(self)

        # Initialize favorites manager for likes and groups
        self._favorites_manager = FavoritesManager(self)

        # Forward favorites changes to event bus for cross-tab sync (e.g., canvas)
        # Single-item signals (for toggle_like, add_to_group, remove_from_group single operations)
        self._favorites_manager.like_changed.connect(self._on_favorites_changed)
        self._favorites_manager.item_groups_changed.connect(self._on_favorites_changed)
        # Batch signals (for like_items, unlike_items, add_items_to_group, remove_items_from_group)
        self._favorites_manager.items_liked_batch.connect(self._on_favorites_batch_changed)
        self._favorites_manager.items_unliked_batch.connect(self._on_favorites_batch_changed)
        self._favorites_manager.items_groups_changed_batch.connect(self._on_favorites_batch_changed)

        # Current filter state: ("all", None), ("liked", None), ("group", group_id), ("ungrouped", None)
        self._current_filter = ("all", None)

        # Setup groups filter panel (collapsible sidebar)
        self._setup_groups_panel()

        # Setup loading overlay for gallery switching
        self._setup_loading_overlay()

        # Setup UI elements
        self._ui_manager._setup_ui()

        # Initialize user selector
        self._ui_manager.populate_user_selector()

        # Hide "View Only" label initially
        self.ui.GalleryViewOnlyLabel.hide()

        # Set initial output directory
        self._update_gallery_path()

        # Use pre-warmed cache from splash screen
        self._refresh_controller.use_prewarm_cache_sync()

        # Subscribe to event bus for cross-tab communication
        self._setup_event_bus_subscriptions()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for gallery actions."""
        # Delegate to selection manager first
        if self._selection_manager.handle_key_press(event):
            event.accept()
            return

        # Pass unhandled events to parent
        super().keyPressEvent(event)

    # =========================================================================
    # MANAGER DELEGATION - Signal handlers and cross-manager coordination
    # These methods are connected as Qt signal handlers from manager classes
    # or called from external modules (comfyui_polling.py, settings_tab.py).
    # =========================================================================

    # -- Selection (signal handlers from thumbnails/toolbar) --

    def _clear_selection(self):
        """Clear all selected items."""
        self._selection_manager.clear_selection()

    def _on_selection_changed(self, image_path, is_selected):
        """Handle thumbnail selection state change."""
        self._selection_manager._on_selection_changed(image_path, is_selected)
        # Emit selection to event bus
        self._emit_selection_changed()

    def _on_shift_click_selection(self, clicked_path):
        """Handle shift+click for range selection."""
        self._selection_manager._on_shift_click(clicked_path)
        self._emit_selection_changed()

    def _on_view_selected(self):
        """Open viewer showing only selected images."""
        self._viewer_manager.view_selected()

    # -- Viewer (signal handlers from thumbnails) --

    def _on_thumbnail_clicked(self, image_path):
        """Handle thumbnail click - open embedded viewer."""
        self._clear_selection()
        self._viewer_manager.open_viewer(image_path)

    def _open_viewer(self, start_media=None, fullscreen=False, media_paths=None):
        """Open the media viewer."""
        self._viewer_manager.open_viewer(start_media, fullscreen, media_paths)

    # -- Operations (signal handlers from thumbnails/toolbar) --

    def _on_delete_selected(self):
        """Delete all selected items with confirmation."""
        self._operations_manager.delete_selected()

    def _on_publish_selected(self):
        """Publish selected items to AYON."""
        self._operations_manager.publish_selected()

    def _on_item_deleted(self, item_path):
        """Handle item deletion (coordinates selection + operations managers)."""
        self._operations_manager._on_item_deleted(item_path)
        self._selection_manager._on_item_deleted(item_path)

    def _on_item_viewed(self, item_path):
        """Handle item viewed."""
        self._operations_manager.on_item_viewed(item_path)

    def _on_copy_settings_requested(self, metadata):
        """Handle request to copy settings from an image."""
        self._operations_manager.copy_settings_to_comfyui(metadata)

    # -- Refresh (called from comfyui_polling.py, settings_tab.py, and internally) --

    def _on_refresh(self, force=False, show_status=True):
        """Handle refresh request."""
        self._refresh_controller.on_refresh(force, show_status=show_status)

    def _start_watcher(self, output_dir):
        """Start file system watcher."""
        self._refresh_controller.start_watcher(output_dir)

    # -- UI (signal handlers from connect_signals + internal use) --

    def _on_sort_button_clicked(self):
        """Handle sort button click."""
        self._ui_manager.on_sort_button_clicked()

    def _on_user_button_clicked(self):
        """Handle user button click."""
        self._ui_manager.on_user_button_clicked()

    def _redisplay_items(self):
        """Redisplay items with current settings."""
        self._ui_manager.redisplay_items()

    # =========================================================================
    # CORE METHODS (kept in main tab)
    # =========================================================================

    # -- Thread-safe cache access helpers --

    def get_cached_widget(self, path: str):
        """Thread-safe access to get a widget from cache."""
        with self._cache_lock:
            return self._widget_cache.get(path)

    def set_cached_widget(self, path: str, widget):
        """Thread-safe access to set a widget in cache."""
        with self._cache_lock:
            self._widget_cache[path] = widget

    def remove_cached_widget(self, path: str):
        """Thread-safe access to remove a widget from cache."""
        with self._cache_lock:
            return self._widget_cache.pop(path, None)

    def clear_widget_cache(self):
        """Thread-safe access to clear all widgets from cache."""
        with self._cache_lock:
            self._widget_cache.clear()
            self._hash_to_path.clear()

    def get_widget_cache_copy(self) -> dict:
        """Thread-safe access to get a copy of the widget cache for iteration."""
        with self._cache_lock:
            return dict(self._widget_cache)

    def get_section_items_copy(self) -> dict:
        """Thread-safe access to get a copy of section items for iteration."""
        with self._cache_lock:
            return dict(self._section_items)

    def set_section_items(self, section_id: str, items: list):
        """Thread-safe access to set section items."""
        with self._cache_lock:
            self._section_items[section_id] = items

    def clear_section_items(self):
        """Thread-safe access to clear section items."""
        with self._cache_lock:
            self._section_items.clear()

    def on_tab_activated(self):
        """Called when tab becomes visible."""
        # Re-enable drop targets on gallery widgets
        self._set_gallery_drop_enabled(True)

        # Start file watcher if not already running
        if self._current_path:
            self._start_watcher(self._current_path)

        # If no initial scan done yet, do one now
        if not self._initial_scan_done:
            self._on_refresh()
            self._initial_scan_done = True

        # Reset new items counter (user is now viewing gallery)
        if EVENT_BUS_AVAILABLE:
            from core.state_manager import app_state
            app_state.reset_gallery_new_count()
            app_state.gallery_visible = True
            # Emit context update
            pipeline_events.update_gallery_context(visible=True)

    def on_tab_deactivated(self):
        """Called when user switches away from this tab. Stop watchers and timers."""
        logging.debug("[Gallery] on_tab_deactivated START")
        self._refresh_controller.stop_watcher()
        self._refresh_controller.stop_network_polling()

        # Disable drop targets on all thumbnail widgets to prevent crash during drag
        self._set_gallery_drop_enabled(False)

        # Update visibility state
        if EVENT_BUS_AVAILABLE:
            from core.state_manager import app_state
            app_state.gallery_visible = False
            pipeline_events.update_gallery_context(visible=False)
        logging.debug("[Gallery] on_tab_deactivated COMPLETE")

    def _set_gallery_drop_enabled(self, enabled):
        """Enable or disable drop targets on gallery widgets."""
        try:
            if hasattr(self, '_gallery_manager') and self._gallery_manager:
                content = self._gallery_manager._scroll_content
                if content:
                    from PySide6.QtWidgets import QWidget
                    if not enabled:
                        # Remember which widgets had drops enabled, then disable
                        self._drop_enabled_widgets = set()
                        for child in content.findChildren(QWidget):
                            if child.acceptDrops():
                                self._drop_enabled_widgets.add(id(child))
                                child.setAcceptDrops(False)
                    else:
                        # Re-enable drops on the widgets that previously had them
                        saved = getattr(self, '_drop_enabled_widgets', None)
                        if saved:
                            for child in content.findChildren(QWidget):
                                if id(child) in saved:
                                    child.setAcceptDrops(True)
                            self._drop_enabled_widgets = None
            logging.debug(f"[Gallery] Drop targets {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logging.debug(f"[Gallery] Error setting drop enabled: {e}")

    def _handle_scan_complete(self, items):
        """Handle scan complete event with item processing."""
        # Store in cache
        self._cached_items = items

        # Detect new items (paths are already normalized at scan source)
        current_paths = set(item['path'] for item in items)
        if self._initial_scan_done:
            new_paths = current_paths - self._known_items
            self._new_items.update(new_paths)
            if new_paths:
                logging.debug(f"[Gallery] {len(new_paths)} new item(s) detected")
        self._known_items = current_paths

        # Apply filter and sort
        filtered_items = self._filter_items(items)
        sorted_items = self._manager.sort_items(filtered_items, self._sort_mode)

        # Display items (use incremental update after initial scan to avoid flashing)
        # Incremental mode compares existing items vs new and only adds/removes differences
        if self._first_scan_after_prewarm:
            self._first_scan_after_prewarm = False
            logging.debug("[Gallery] First scan after prewarm, using incremental sync")
        incremental = self._initial_scan_done
        self._manager.display_items(sorted_items, self._view_mode, incremental=incremental)

        # Hide loading overlay after display completes
        self.hide_loading_overlay()

        # Update tracking state for smart redisplay
        self._last_displayed_paths = set(item['path'] for item in sorted_items)
        self._last_view_mode = self._view_mode

        # Update ordered list for shift-select
        self._visible_items_ordered = [item['path'] for item in sorted_items]

        # Note: display_items already updates status count with filtered items

        # Update filter counts in groups panel
        self._update_filter_counts(items)

        # Mark initial scan done
        self._initial_scan_done = True

    def _on_scroll(self, value=None):
        """Handle scroll event - load visible thumbnails."""
        self._load_visible_thumbnails()

    def _load_visible_thumbnails(self):
        """Load thumbnails for widgets that are currently visible."""
        self._manager.load_visible_thumbnails()

    def _is_own_gallery(self):
        """Check if currently viewing own gallery."""
        return self._selected_user == self.app_state.user

    def _get_network_user_path(self, username=None):
        """Get the network gallery path for a user."""
        from core.settings_manager import get_setting

        # Validate network_output_path setting
        base_path = get_setting("network_output_path")
        if not base_path or not isinstance(base_path, str):
            logger.error("[Gallery] network_output_path not configured or invalid")
            return None

        # Strip whitespace
        base_path = base_path.strip()
        if not base_path:
            logger.error("[Gallery] network_output_path is empty")
            return None

        # Verify it's an absolute path
        if not os.path.isabs(base_path):
            logger.error(f"[Gallery] network_output_path must be absolute: {base_path}")
            return None

        if username is None:
            username = self._selected_user

        # Normalize username: strip whitespace, treat empty as None
        username = username.strip() if username else None

        # SECURITY: Reject empty username - don't fall back to base path
        # This prevents showing all users' files when username is missing
        if not username:
            logger.error("[Gallery] Cannot show gallery without username")
            return None

        # SECURITY: Validate username to prevent path traversal attacks
        if not _validate_username(username):
            logger.error(f"[Gallery] Username validation failed: {username}")
            return None

        return os.path.join(base_path, username)

    def _update_gallery_path(self, reset_tracking=True):
        """Update the gallery path to the network path for selected user."""
        self._current_path = self._get_network_user_path()

        if reset_tracking:
            self._known_items.clear()
            self._new_items.clear()
            self._initial_scan_done = False
            self._first_scan_after_prewarm = False
            self._cached_items = None
        # Update watcher
        if self._current_path:
            self._start_watcher(self._current_path)

    def _on_open_explorer(self):
        """Open the current gallery folder in file explorer."""
        import subprocess
        import platform

        if not self._current_path or not os.path.exists(self._current_path):
            logging.debug("[Gallery] No valid path to open")
            return

        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(self._current_path)
            elif system == "Darwin":
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                subprocess.run(["open", self._current_path], creationflags=creationflags)
            else:
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                subprocess.run(["xdg-open", self._current_path], creationflags=creationflags)
            # Show success status
            self.show_status("Opened gallery folder", "info")
        except Exception as e:
            logging.warning(f"[Gallery] Error opening explorer: {e}")
            self.show_status(f"Could not open folder: {e}", "error")

    # =========================================================================
    # GROUPS & LIKES FILTERING
    # =========================================================================

    def _on_use_in_comfyui(self, paths: list):
        """Handle 'Use in ComfyUI' action from quick actions bar."""
        if not paths:
            return

        # Emit event through event bus if available
        if EVENT_BUS_AVAILABLE:
            pipeline_events.use_as_input.emit(paths)
        else:
            # Fallback: direct call to comfyui tab
            comfyui_tab = self.main_window.get_tab("comfyui")
            if comfyui_tab and hasattr(comfyui_tab, '_on_use_images_from_gallery'):
                comfyui_tab._on_use_images_from_gallery(paths)

        self.main_window.select_tab_by_name("comfyui")
        self.show_status(f"Added {len(paths)} image(s) to ComfyUI input", "success")

    def _get_item_metadata(self, path: str) -> dict:
        """Get metadata for an item by its file path.

        Loads metadata from the comfyui_gallery_metadata.json file in the item's directory.

        Args:
            path: Full path to the item

        Returns:
            dict: Item metadata or empty dict if not found
        """
        try:
            from comfyui.metadata import get_item_metadata

            # Get the directory and filename
            dir_path = os.path.dirname(path)
            filename = os.path.basename(path)

            # Use centralized metadata lookup
            result = get_item_metadata(dir_path, filename)
            return result if result else {}
        except Exception as e:
            logger.error(f"Error getting metadata for {path}: {e}")
            return {}

    def _on_copy_prompt(self, path: str):
        """Handle 'Copy Prompt' action - copy prompt text to clipboard."""
        from PySide6.QtWidgets import QApplication

        # Get metadata for the image
        metadata = self._get_item_metadata(path)
        if not metadata:
            self.show_status("No metadata found for this image", "warning")
            return

        # Look for prompt in editable_values
        editable_values = metadata.get('editable_values', {})
        prompt_text = None

        for node_id, node_data in editable_values.items():
            if isinstance(node_data, dict):
                display_name = node_data.get('display_name', '').lower()
                if 'prompt' in display_name or 'text' in display_name:
                    prompt_text = node_data.get('value', '')
                    break

        if prompt_text:
            QApplication.clipboard().setText(prompt_text)
            self.show_status("Prompt copied to clipboard", "success")
        else:
            self.show_status("No prompt found in image metadata", "warning")

    def _on_compare_to_source(self, path: str):
        """Handle 'Compare to Source' action - open side-by-side viewer."""
        # Get metadata to find source image
        metadata = self._get_item_metadata(path)
        if not metadata:
            self.show_status("No metadata found for this image", "warning")
            return

        source_images = metadata.get('source_images', [])
        if not source_images:
            self.show_status("No source image recorded for this output", "warning")
            return

        # Find the source image path
        source_name = source_images[0]
        source_path = None

        # Look for the source in current items
        if self._cached_items:
            for item in self._cached_items:
                if item.get('name', '').lower() == source_name.lower():
                    source_path = item['path']
                    break

        if source_path:
            # Open comparison viewer
            self._viewer_manager.open_viewer(
                start_media=path,
                media_paths=[source_path, path]
            )
            self.show_status("Showing comparison with source image", "info")
        else:
            self.show_status(f"Source image '{source_name}' not found in gallery", "warning")

    def _on_recreate_settings(self, path: str):
        """Handle 'Recreate Settings' action - restore ComfyUI settings and switch tab."""
        metadata = self._get_item_metadata(path)
        if not metadata:
            self.show_status("No metadata found for this image", "warning")
            return

        # Add the output directory to metadata so source images can be found
        metadata['_output_dir'] = os.path.dirname(path)

        # Emit through event bus or direct call
        if EVENT_BUS_AVAILABLE:
            pipeline_events.copy_settings.emit(metadata)
        else:
            comfyui_tab = self.main_window.get_tab("comfyui")
            if comfyui_tab and hasattr(comfyui_tab, 'apply_settings_from_metadata'):
                comfyui_tab.apply_settings_from_metadata(metadata)

        # Switch to ComfyUI tab
        self.main_window.select_tab_by_name("comfyui")
        self.show_status("Settings restored in ComfyUI tab", "success")

    def _setup_groups_panel(self):
        """Set up the groups filter panel as a resizable sidebar."""
        from PySide6.QtWidgets import QSplitter
        from PySide6.QtCore import Qt

        # Create groups panel
        self._groups_panel = GroupsFilterPanel(self._favorites_manager, parent=self.ui)
        self._groups_panel.filter_changed.connect(self._on_filter_changed)
        self._groups_panel.status_message.connect(self.show_status_message)

        # Make panel resizable (min/max managed by panel's collapse logic)
        # Don't set minWidth here - the panel manages it during collapse/expand
        self._groups_panel.setMaximumWidth(400)

        # Get the main gallery area (scroll area)
        scroll_area = self.ui.galleryScrollArea

        # Create a splitter to hold panel + scroll area
        from PySide6.QtWidgets import QSizePolicy
        self._gallery_splitter = QSplitter(Qt.Horizontal)
        self._gallery_splitter.setChildrenCollapsible(False)
        self._gallery_splitter.setHandleWidth(4)
        # Ensure splitter expands to fill available space like the scroll area did
        self._gallery_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._gallery_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #3c414b;
            }
            QSplitter::handle:hover {
                background-color: #4a9eff;
            }
        """)

        # Add groups panel on the left
        self._gallery_splitter.addWidget(self._groups_panel)

        # Take scroll area out of its current parent and add to splitter
        main_layout = self.ui.galleryMainLayout

        # Find scroll area index in main layout
        scroll_index = -1
        for i in range(main_layout.count()):
            if main_layout.itemAt(i).widget() == scroll_area:
                scroll_index = i
                break

        if scroll_index >= 0:
            # Remove scroll area from main layout
            main_layout.takeAt(scroll_index)

            # Add scroll area to splitter
            self._gallery_splitter.addWidget(scroll_area)

            # Insert splitter at the same position with stretch factor
            main_layout.insertWidget(scroll_index, self._gallery_splitter)
            # Set stretch factor so splitter takes available space (like scroll area did)
            main_layout.setStretchFactor(self._gallery_splitter, 1)

            # Load saved splitter sizes from settings
            from core.settings_manager import get_setting
            saved_sizes = get_setting("gallery_splitter_sizes")
            if saved_sizes:
                self._gallery_splitter.setSizes(saved_sizes)
            else:
                # Default: panel 200px, rest for gallery
                self._gallery_splitter.setSizes([200, 800])

            # Save splitter sizes when changed
            self._gallery_splitter.splitterMoved.connect(self._save_splitter_sizes)

        # Connect collapsed state signal
        self._groups_panel.collapsed_changed.connect(self._on_sidebar_collapsed)

        # Load collapsed state from settings
        from core.settings_manager import get_setting
        collapsed = get_setting("gallery_sidebar_collapsed")
        if collapsed:
            self._groups_panel._toggle_collapse()

    def _setup_loading_overlay(self):
        """Set up a loading overlay for gallery switching feedback."""
        from loading_widgets import LoadingOverlay

        # Create overlay as child of scroll area's viewport to float above content
        viewport = self.ui.galleryScrollArea.viewport()
        self._loading_overlay = LoadingOverlay(viewport)
        self._loading_overlay.hide()

    def show_loading_overlay(self, message="Loading..."):
        """Show the loading overlay with a message."""
        if hasattr(self, '_loading_overlay'):
            # Size overlay to cover the entire viewport
            viewport = self.ui.galleryScrollArea.viewport()
            self._loading_overlay.setGeometry(viewport.rect())
            self._loading_overlay.show_loading(message)

            # Note: Do NOT call QApplication.processEvents() here.
            # Re-entering the event loop can cause batch poll timers, gallery
            # refresh timers, or other deferred callbacks to fire mid-operation,
            # leading to widget access on deleted objects (segfault).
            self._loading_overlay.repaint()

    def hide_loading_overlay(self):
        """Hide the loading overlay."""
        if hasattr(self, '_loading_overlay'):
            self._loading_overlay.hide_loading()

    def _on_sidebar_collapsed(self, is_collapsed):
        """Save sidebar collapsed state to settings."""
        from core.settings_manager import set_setting
        set_setting("gallery_sidebar_collapsed", is_collapsed)

    def _save_splitter_sizes(self):
        """Save splitter sizes to settings."""
        from core.settings_manager import set_setting
        if hasattr(self, '_gallery_splitter'):
            set_setting("gallery_splitter_sizes", self._gallery_splitter.sizes())

    def _on_filter_changed(self, filter_type, filter_id):
        """Handle filter selection change from groups panel.

        Args:
            filter_type: "all", "liked", "group", "ungrouped"
            filter_id: group_id for groups, empty string for others
        """
        self._current_filter = (filter_type, filter_id if filter_id else None)

        # Save collapsed state when filter changes (if collapsed state changed)
        from core.settings_manager import set_setting
        set_setting("gallery_sidebar_collapsed", self._groups_panel._is_collapsed, verbose=False)

        # Redisplay with filter applied
        self._redisplay_items()

    def _filter_items(self, items):
        """Filter items based on current filter settings.

        Applies type filter, show_inputs filter, and likes/groups/stacks filter.
        """
        filter_type, filter_id = self._current_filter

        # Apply type filter first (unless viewing inputs specifically)
        if filter_type != "inputs" and hasattr(self, '_type_filters'):
            items = [
                item for item in items
                if self._type_filters.get(item.get('type', 'image'), True)
            ]

        # Special case: "inputs" filter shows only input images (bypass show_inputs setting)
        if filter_type == "inputs":
            return [item for item in items if item.get('is_input', False)]

        # Apply show_inputs filter for other filter types
        if not self._show_inputs:
            items = [item for item in items if not item.get('is_input', False)]

        # Apply likes/groups/stacks filter
        if filter_type == "all":
            return items
        elif filter_type == "liked":
            # Get liked items from current directory
            local_liked = self._favorites_manager.filter_liked(items)
            # Also include liked items from other directories
            external_liked = self._favorites_manager.get_liked_items_as_dicts(
                exclude_dir=self._current_path
            )
            return local_liked + external_liked
        elif filter_type == "group" and filter_id:
            # Get grouped items from current directory
            local_grouped = self._favorites_manager.filter_by_group(items, filter_id)
            # Also include grouped items from other directories
            external_grouped = self._favorites_manager.get_group_items_as_dicts(
                filter_id, exclude_dir=self._current_path
            )
            return local_grouped + external_grouped
        elif filter_type == "ungrouped":
            return self._favorites_manager.filter_ungrouped(items)
        elif filter_type == "stack" and filter_id:
            # Filter by job_prefix (stack)
            return [item for item in items if item.get('job_prefix') == filter_id]

        return items

    def _update_filter_counts(self, items):
        """Update the counts shown in the groups panel.

        Performance optimization: Uses set intersections with reverse index
        for O(1) group counts instead of O(n) filtering per group.

        Args:
            items: List of all items (before likes/groups filtering)
        """
        if not hasattr(self, '_groups_panel'):
            return

        # Count inputs from all items (before filtering)
        inputs_count = sum(1 for item in items if item.get('is_input', False))

        # Apply show_inputs filter to get the base item set for other counts
        if not self._show_inputs:
            items = [item for item in items if not item.get('is_input', False)]

        all_count = len(items)

        # Build path set once for efficient lookups
        item_paths = {item['path'] for item in items}

        # Count liked items using set intersection (O(min(n,m)) instead of O(n*m))
        self._favorites_manager._ensure_loaded()
        liked_count = len(item_paths & self._favorites_manager._liked_items)

        # Count items per group using reverse index (O(1) per group instead of O(n))
        group_counts = {}
        for group in self._favorites_manager.get_groups():
            group_items = self._favorites_manager._group_items.get(group.group_id, set())
            group_counts[group.group_id] = len(item_paths & group_items)

        # Count ungrouped items - items not in any group
        all_grouped_paths = set()
        for paths in self._favorites_manager._group_items.values():
            all_grouped_paths.update(paths)
        ungrouped_count = len(item_paths - all_grouped_paths)

        # Count items per stack (job_prefix)
        stack_counts = {}
        for item in items:
            job_prefix = item.get('job_prefix')
            if job_prefix:
                stack_counts[job_prefix] = stack_counts.get(job_prefix, 0) + 1

        # Update panel
        self._groups_panel.set_item_counts(all_count, liked_count, group_counts, ungrouped_count, inputs_count)
        if hasattr(self._groups_panel, 'set_stacks_data'):
            self._groups_panel.set_stacks_data(stack_counts)

    def _refresh_favorites_state_for_path(self, path: str):
        """Refresh favorites state for a single widget.

        Performance optimization: Only updates the specific widget instead of all.

        Args:
            path: Path of the item to update
        """
        from shiboken6 import isValid

        if not hasattr(self, '_widget_cache'):
            return

        widget = self.get_cached_widget(path)
        if widget and isValid(widget) and hasattr(widget, 'update_favorites_state'):
            widget.update_favorites_state()

    def _refresh_favorites_state_for_paths(self, paths):
        """Refresh favorites state for specific widgets.

        Performance optimization: Only updates the specified widgets instead of all.

        Args:
            paths: List or set of paths to update
        """
        from shiboken6 import isValid

        if not hasattr(self, '_widget_cache'):
            return

        for path in paths:
            widget = self.get_cached_widget(path)
            if widget and isValid(widget) and hasattr(widget, 'update_favorites_state'):
                widget.update_favorites_state()

    def _refresh_favorites_state(self):
        """Refresh the favorites state on all visible thumbnails.

        Note: Prefer using _refresh_favorites_state_for_paths() when you know
        which items changed, as this method iterates ALL widgets.
        """
        from shiboken6 import isValid

        if not hasattr(self, '_widget_cache'):
            return

        # Get a thread-safe copy to iterate over
        for path, widget in self.get_widget_cache_copy().items():
            if isValid(widget) and hasattr(widget, 'update_favorites_state'):
                widget.update_favorites_state()

    def show_status_message(self, message, duration=2000):
        """Show a status message in the statusbar.

        Args:
            message: Message to display
            duration: Duration in milliseconds (default 2000)
        """
        self.show_status(message, "info")

    # =========================================================================
    # EVENT BUS INTEGRATION (Cross-tab communication)
    # =========================================================================

    def _setup_event_bus_subscriptions(self):
        """Subscribe to event bus signals for cross-tab awareness."""
        if not EVENT_BUS_AVAILABLE:
            return

        # Subscribe to job output ready for refresh triggers
        pipeline_events.job_output_ready.connect(self._on_job_output_ready)

        # Subscribe to "use as input" from ourselves (for consistency)
        pipeline_events.use_as_input.connect(self._on_use_as_input_requested)

        # Subscribe to refresh requests from other tabs (e.g., settings)
        pipeline_events.gallery_refresh_requested.connect(self._on_refresh_requested)

        # Subscribe to navigation requests from other tabs (e.g., canvas)
        pipeline_events.gallery_navigate_to.connect(self._on_navigate_to_requested)

        # Subscribe to viewer action requests (from image viewers)
        pipeline_events.toggle_item_like.connect(self._on_toggle_item_like)
        pipeline_events.add_item_to_group.connect(self._on_add_item_to_group)
        pipeline_events.create_item_group.connect(self._on_create_item_group)
        pipeline_events.show_item_properties.connect(self._on_show_item_properties)
        pipeline_events.publish_item.connect(self._on_publish_item)
        pipeline_events.view_input_image.connect(self._on_view_input_image)
        pipeline_events.request_groups_list.connect(self._on_request_groups_list)
        pipeline_events.request_item_like_status.connect(self._on_request_item_like_status)

        logger.debug("Gallery tab subscribed to event bus")

    def _on_job_output_ready(self, job_id: str, output_path: str):
        """Handle single output ready event - animate new item arrival."""
        logger.debug(f"[Gallery] Output ready: {output_path}")
        # The refresh is already triggered by polling, but we could add
        # special handling here for immediate item highlighting

    def _on_use_as_input_requested(self, paths: list):
        """Handle request to use gallery images as ComfyUI inputs."""
        # This is handled by operations_manager, but we could add logic here
        # to switch tabs or show confirmation
        pass

    def _emit_selection_changed(self):
        """Emit selection changed event to event bus."""
        if not EVENT_BUS_AVAILABLE:
            return

        selected = self._selection_manager.get_selected()
        from core.state_manager import app_state
        app_state.gallery_selected_paths = list(selected)
        pipeline_events.selection_changed.emit(list(selected), len(selected))

    def _on_refresh_requested(self, force: bool = False):
        """Handle refresh request from event bus.

        Called when another tab (e.g., settings) requests a gallery refresh.

        Args:
            force: If True, clears widget cache before refresh
        """
        if force:
            # Clear widget cache to force thumbnail reload (thread-safe)
            if hasattr(self, '_widget_cache'):
                self.clear_widget_cache()
        self._on_refresh(force=force)

    def _on_navigate_to_requested(self, image_path: str):
        """Handle navigation request from event bus.

        Called when another tab (e.g., canvas) wants to show an image in the gallery.

        Args:
            image_path: Path of the image to navigate to
        """
        # Switch to this tab
        if hasattr(self.main_window, 'select_tab_by_name'):
            self.main_window.select_tab_by_name('gallery')
        elif hasattr(self.main_window, 'tab_widget'):
            tab_widget = self.main_window.tab_widget
            for i in range(tab_widget.count()):
                if tab_widget.widget(i) == self:
                    tab_widget.setCurrentIndex(i)
                    break

        # Navigate to the image
        if hasattr(self, 'select_and_scroll_to_item'):
            self.select_and_scroll_to_item(image_path)
        elif hasattr(self, '_selection_manager'):
            self._selection_manager.select_item_by_path(image_path)

    # =========================================================================
    # EVENT BUS HANDLERS (image viewer actions)
    # =========================================================================

    def _on_toggle_item_like(self, path: str, source: str):
        """Handle toggle like request from event bus (e.g., image viewer)."""
        if not path:
            return
        self._favorites_manager.toggle_like(path)

    def _on_add_item_to_group(self, path: str, group_id: str, source: str):
        """Handle add to group request from event bus."""
        if not path or not group_id:
            return
        self._favorites_manager.add_to_group(path, group_id)

    def _on_create_item_group(self, path: str, group_name: str, color: str, source: str):
        """Handle create group request from event bus."""
        if not path or not group_name:
            return
        group = self._favorites_manager.create_group(group_name, color)
        if group:
            self._favorites_manager.add_to_group(path, group.group_id)

    def _on_show_item_properties(self, path: str, source: str):
        """Handle show properties request from event bus."""
        if not path:
            return
        self._operations_manager.show_properties_for_path(path)

    def _on_publish_item(self, path: str, source: str):
        """Handle publish request from event bus."""
        if not path:
            return
        self._operations_manager.publish_items([path])

    def _on_view_input_image(self, path: str, source: str):
        """Handle view input image request from event bus."""
        if not path:
            return
        self._viewer_manager.open_viewer(path)

    def _on_request_groups_list(self, source: str):
        """Handle request for groups list from event bus."""
        if EVENT_BUS_AVAILABLE:
            groups = self._favorites_manager.get_groups()
            groups_data = [{"id": g.group_id, "name": g.name, "color": g.color} for g in groups]
            pipeline_events.groups_list_response.emit(groups_data, source)

    def _on_request_item_like_status(self, path: str, source: str):
        """Handle request for item like status from event bus."""
        if EVENT_BUS_AVAILABLE and path:
            is_liked = self._favorites_manager.is_liked(path)
            pipeline_events.item_like_status_response.emit(path, is_liked, source)

    def _on_favorites_changed(self, *args):
        """Forward favorites changes to event bus for cross-tab sync.

        Called when likes or group assignments change. Emits favorites_changed
        signal on the event bus so other tabs (e.g., canvas) can sync.
        """
        if EVENT_BUS_AVAILABLE:
            pipeline_events.favorites_changed.emit()

    def _on_favorites_batch_changed(self, paths: list):
        """Handle batch favorites changes with targeted widget updates.

        Called when batch operations (like_items, unlike_items, add_items_to_group,
        remove_items_from_group) complete. Updates only affected widgets instead of
        refreshing all widgets for better performance.

        Args:
            paths: List of paths that were affected by the batch operation
        """
        # Update only affected widgets
        self._refresh_favorites_state_for_paths(paths)

        # Forward to event bus for cross-tab sync
        if EVENT_BUS_AVAILABLE:
            pipeline_events.favorites_changed.emit()

    # =========================================================================
    # DRAG-TO-GROUP HANDLERS
    # =========================================================================

    def _on_group_items_requested(self, paths):
        """Handle request to create a new group from dropped items.

        Called when items are dragged onto a thumbnail to create a group.

        Args:
            paths: List of paths to add to the new group
        """
        from dialogs import QuickGroupDialog

        if not paths or len(paths) < 2:
            return

        # Show quick group dialog
        dialog = QuickGroupDialog(item_count=len(paths), parent=self)
        if dialog.exec() != dialog.Accepted:
            return

        name, color = dialog.get_result()
        if not name:
            return

        # Create the group
        group = self._favorites_manager.create_group(name, color)
        if not group:
            self.show_status_message("Failed to create group", duration=2000)
            return

        # Add all items to the group
        for path in paths:
            self._favorites_manager.add_to_group(path, group.group_id)

        logger.info(f"[Gallery] Created group '{name}' with {len(paths)} items")
        self.show_status_message(f"Created group '{name}' with {len(paths)} items")

        # Refresh the display to show the new grouping
        self._ui_manager.redisplay_items(force_rebuild=True)

    def _on_add_to_existing_group(self, stack_id, paths):
        """Handle request to add items to an existing group.

        Called when items are dragged onto a group stack widget.

        Args:
            stack_id: The stack_id of the group (format: "🏷 GroupName")
            paths: List of paths to add to the group
        """
        if not paths:
            return

        # Extract group name from stack_id (format: "🏷 GroupName")
        if not stack_id.startswith('🏷 '):
            logger.warning(f"[Gallery] Invalid group stack_id: {stack_id}")
            return

        group_name = stack_id[2:].strip()  # Remove "🏷 " prefix

        # Find the group by name
        group = None
        for g in self._favorites_manager.get_groups():
            if g.name == group_name:
                group = g
                break

        if not group:
            logger.warning(f"[Gallery] Group not found: {group_name}")
            self.show_status_message(f"Group '{group_name}' not found", duration=2000)
            return

        # Add all items to the group
        added_count = 0
        for path in paths:
            if self._favorites_manager.add_to_group(path, group.group_id):
                added_count += 1

        if added_count > 0:
            logger.info(f"[Gallery] Added {added_count} items to group '{group_name}'")
            self.show_status_message(f"Added {added_count} item(s) to '{group_name}'")

            # Refresh the display to show the updated grouping
            self._ui_manager.redisplay_items(force_rebuild=True)
        else:
            self.show_status_message("Items already in group")

    # =========================================================================
    # EXTERNAL NAVIGATION
    # =========================================================================

    def select_and_scroll_to_item(self, image_path: str):
        """
        Select an item and scroll it into view.

        Called from external sources like Canvas tab's "Show in Gallery" action.

        Args:
            image_path: Path to the image to select and show
        """
        import os

        # Normalize path for consistent lookup
        image_path = os.path.normpath(image_path)

        # Find the widget for this path
        widget = self._gallery_manager.find_widget_by_path(image_path)

        if not widget:
            # Item not visible in current view - may need to change filters or load
            logger.info(f"[Gallery] Item not in current view: {image_path}")

            # Try to clear filters and reload
            self._clear_all_filters()
            self._gallery_manager.refresh(force=True)

            # Try again after refresh (use a timer to let refresh complete)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, lambda: self._select_and_scroll_deferred(image_path))
            return

        # Clear current selection and select this item
        self._selection_manager.clear_selection()
        self._selection_manager.select_single(widget)

        # Scroll the widget into view
        self._scroll_widget_into_view(widget)

        logger.info(f"[Gallery] Selected and scrolled to: {image_path}")

    def _select_and_scroll_deferred(self, image_path: str):
        """Deferred select and scroll after refresh."""
        import os
        image_path = os.path.normpath(image_path)

        widget = self._gallery_manager.find_widget_by_path(image_path)
        if widget:
            self._selection_manager.clear_selection()
            self._selection_manager.select_single(widget)
            self._scroll_widget_into_view(widget)
            logger.info(f"[Gallery] Deferred select completed: {image_path}")
        else:
            self.show_status_message(f"Item not found in gallery")

    def _scroll_widget_into_view(self, widget):
        """Scroll the scroll area to bring a widget into view."""
        scroll_area = self.ui.galleryScrollArea

        # Get widget position relative to scroll content
        widget_pos = widget.mapTo(self.ui.galleryThumbnailContainer, widget.rect().topLeft())
        widget_center_y = widget_pos.y() + widget.height() // 2

        # Get viewport dimensions
        viewport_height = scroll_area.viewport().height()

        # Calculate scroll position to center the widget
        target_scroll = widget_center_y - viewport_height // 2

        # Clamp to valid range
        max_scroll = scroll_area.verticalScrollBar().maximum()
        target_scroll = max(0, min(target_scroll, max_scroll))

        # Animate the scroll
        scroll_area.verticalScrollBar().setValue(target_scroll)

    def _clear_all_filters(self):
        """Clear all active filters to show all items."""
        if hasattr(self, '_ui_manager'):
            # Reset filter buttons
            self.ui.GalleryShowAllButton.setChecked(True)
            self._ui_manager._current_filter = 'all'

    def cleanup(self):
        """Clean up resources when tab is being destroyed.

        Disconnects signals and releases resources to prevent memory leaks.
        Should be called by the main window when the app is closing.
        """
        # Clean up groups panel signals
        if hasattr(self, '_groups_panel') and self._groups_panel:
            self._groups_panel.cleanup()

        # Disconnect event bus subscriptions
        if EVENT_BUS_AVAILABLE:
            try:
                pipeline_events.job_output_ready.disconnect(self._on_job_output_ready)
                pipeline_events.use_as_input.disconnect(self._on_use_as_input_requested)
                pipeline_events.gallery_refresh_requested.disconnect(self._on_refresh_requested)
                pipeline_events.gallery_navigate_to.disconnect(self._on_navigate_to_requested)
            except (RuntimeError, TypeError):
                # Already disconnected or invalid connection
                pass

        # Stop refresh controller timers
        if hasattr(self, '_refresh_controller') and self._refresh_controller:
            self._refresh_controller.stop_all()

        logger.debug("Gallery tab cleanup completed")
