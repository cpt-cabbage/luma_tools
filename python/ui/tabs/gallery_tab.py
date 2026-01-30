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
- Shows job status bar when jobs are running
- Emits context events when selection/visibility changes
"""

import os
import logging

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QTimer, QThreadPool

from .base_tab import BaseTab
from .gallery_loader import GalleryLoader
from .gallery import SelectionManager, ViewerManager, OperationsManager, RefreshController, UIManager, GalleryManager
from .gallery.favorites_manager import FavoritesManager
from .gallery.groups_panel import GroupsFilterPanel
from .gallery.job_status_bar import JobStatusBar

logger = logging.getLogger(__name__)

from core.import_utils import get_event_bus
pipeline_events, EVENT_BUS_AVAILABLE = get_event_bus()


class GalleryTab(BaseTab):
    """Tab for viewing generated images."""

    @property
    def ui_file(self) -> str:
        return "gallery.ui"

    @property
    def tab_name(self) -> str:
        return "Gallery"

    @property
    def tab_id(self) -> str:
        return "gallery"

    def connect_signals(self):
        """Connect gallery tab signals."""
        self.ui.GallerySourceToggle.clicked.connect(self._on_source_toggle)
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

        # Source mode: "network" or "custom"
        self._source_mode = "network"
        self._custom_path = ""
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

        # User selection for multi-user gallery viewing
        self._selected_user = self.app_state.user
        self._available_users = []
        self._user_cache = {}
        self._precache_in_progress = set()

        # Initialize managers
        self._selection_manager = SelectionManager(self)
        self._viewer_manager = ViewerManager(self)
        self._operations_manager = OperationsManager(self)
        self._refresh_controller = RefreshController(self)
        self._ui_manager = UIManager(self)

        # Initialize favorites manager for likes and groups
        self._favorites_manager = FavoritesManager(self)

        # Current filter state: ("all", None), ("liked", None), ("group", group_id), ("ungrouped", None)
        self._current_filter = ("all", None)

        # Setup groups filter panel (collapsible sidebar)
        self._setup_groups_panel()

        # Setup job status bar (shows when ComfyUI jobs are running)
        self._setup_job_status_bar()

        # Setup UI elements
        self._ui_manager.setup_ui()

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
        self._selection_manager.on_selection_changed(image_path, is_selected)
        # Emit selection to event bus
        self._emit_selection_changed()

    def _on_view_selected(self):
        """Open viewer showing only selected images."""
        self._viewer_manager.view_selected()

    # -- Viewer (signal handlers from thumbnails) --

    def _on_thumbnail_clicked(self, image_path):
        """Handle thumbnail click - open embedded viewer."""
        self._clear_selection()
        self._viewer_manager.open_viewer(image_path)

    def _open_viewer(self, start_image=None, fullscreen=False, image_paths=None):
        """Open the image viewer."""
        self._viewer_manager.open_viewer(start_image, fullscreen, image_paths)

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
        self._selection_manager.on_item_deleted(item_path)

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
        self._ui_manager._redisplay_items()

    # =========================================================================
    # CORE METHODS (kept in main tab)
    # =========================================================================

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
        self.log("[Gallery] on_tab_deactivated START")
        self._refresh_controller.stop_watcher()
        self._refresh_controller.stop_network_polling()

        # Disable drop targets on all thumbnail widgets to prevent crash during drag
        self._set_gallery_drop_enabled(False)

        # Update visibility state
        if EVENT_BUS_AVAILABLE:
            from core.state_manager import app_state
            app_state.gallery_visible = False
            pipeline_events.update_gallery_context(visible=False)
        self.log("[Gallery] on_tab_deactivated COMPLETE")

    def _set_gallery_drop_enabled(self, enabled):
        """Enable or disable drop targets on gallery widgets."""
        try:
            # Disable drops on the scroll area content
            if hasattr(self, '_gallery_manager') and self._gallery_manager:
                content = self._gallery_manager._scroll_content
                if content:
                    # Find all widgets that accept drops
                    from PySide6.QtWidgets import QWidget
                    for child in content.findChildren(QWidget):
                        if child.acceptDrops():
                            child.setAcceptDrops(enabled)
            self.log(f"[Gallery] Drop targets {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            self.log(f"[Gallery] Error setting drop enabled: {e}")

    def _on_scan_complete_impl(self, items):
        """Implementation of scan complete handling."""
        # Store in cache
        self._cached_items = items

        # Detect new items (paths are already normalized at scan source)
        current_paths = set(item['path'] for item in items)
        if self._initial_scan_done:
            new_paths = current_paths - self._known_items
            self._new_items.update(new_paths)
            if new_paths:
                self.log(f"[Gallery] {len(new_paths)} new item(s) detected")
        self._known_items = current_paths

        # Apply filter and sort
        filtered_items = self._filter_items(items)
        sorted_items = self._manager.sort_items(filtered_items, self._sort_mode)

        # Display items (use incremental update after initial scan to avoid flashing)
        # Incremental mode compares existing items vs new and only adds/removes differences
        if self._first_scan_after_prewarm:
            self._first_scan_after_prewarm = False
            self.log("[Gallery] First scan after prewarm, using incremental sync")
        incremental = self._initial_scan_done
        self._manager.display_items(sorted_items, self._view_mode, incremental=incremental)

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

        base_path = get_setting("comfyui_network_output_path")
        if not base_path:
            return None

        if username is None:
            username = self._selected_user

        if username:
            return os.path.join(base_path, username)
        return base_path

    def _update_gallery_path(self, reset_tracking=True):
        """Update the gallery path based on source mode and selected user."""
        if self._source_mode == "network":
            self._current_path = self._get_network_user_path()
        else:
            self._current_path = self._custom_path

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
            self.log("[Gallery] No valid path to open")
            return

        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(self._current_path)
            elif system == "Darwin":
                subprocess.run(["open", self._current_path])
            else:
                subprocess.run(["xdg-open", self._current_path])
            # Show success status
            self.show_status("Opened gallery folder", "info")
        except Exception as e:
            self.log(f"[Gallery] Error opening explorer: {e}")
            self.show_status(f"Could not open folder: {e}", "error")

    def _on_source_toggle(self):
        """Toggle between network and custom source modes."""
        if self._source_mode == "network":
            self._browse_custom_folder()
        else:
            # Switch back to network
            self._source_mode = "network"
            self.ui.GallerySourceToggle.setText("📁 Network")
            self._update_gallery_path()
            self._on_refresh(force=True)
            self.show_status("Switched to network gallery", "info")

    def _browse_custom_folder(self):
        """Browse for a custom gallery folder."""
        from file_dialogs import browse_directory_with_memory

        folder = browse_directory_with_memory(
            self.main_window,
            context="gallery_custom_folder",
            title="Select Gallery Folder",
            fallback_path=self._current_path or ""
        )

        if folder:
            self._source_mode = "custom"
            self._custom_path = folder
            self.ui.GallerySourceToggle.setText("📁 Custom")
            self._update_gallery_path()
            self._on_refresh(force=True)
            self.show_status(f"Custom: {os.path.basename(folder)}", "info")

    # =========================================================================
    # GROUPS & LIKES FILTERING
    # =========================================================================

    def _setup_job_status_bar(self):
        """Set up the job status bar at the top of the gallery."""
        self._job_status_bar = JobStatusBar()
        self._job_status_bar.view_in_comfyui_clicked.connect(self._on_view_in_comfyui)

        # Insert at the top of the main layout (before toolbar)
        if hasattr(self.ui, 'galleryMainLayout'):
            self.ui.galleryMainLayout.insertWidget(0, self._job_status_bar)

    def _on_view_in_comfyui(self):
        """Handle click on 'View in ComfyUI' button."""
        self.main_window.select_tab_by_name("comfyui")

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

        Loads metadata from the _gallery_metadata.json file in the item's directory.

        Args:
            path: Full path to the item

        Returns:
            dict: Item metadata or empty dict if not found
        """
        try:
            from comfyui.metadata import load_gallery_metadata

            # Get the directory and filename
            dir_path = os.path.dirname(path)
            filename = os.path.basename(path)

            # Load all metadata for this directory
            all_metadata = load_gallery_metadata(dir_path)
            if not all_metadata:
                return {}

            # Look for metadata by filename (without extension for flexibility)
            name_without_ext = os.path.splitext(filename)[0]

            # Try exact filename match first
            if filename in all_metadata:
                return all_metadata[filename]

            # Try without extension
            if name_without_ext in all_metadata:
                return all_metadata[name_without_ext]

            # Try prefix match (for job_prefix based metadata)
            for key, meta in all_metadata.items():
                if filename.startswith(key) or name_without_ext.startswith(key):
                    return meta

            return {}
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
                start_image=path,
                image_paths=[source_path, path]
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
            return self._favorites_manager.filter_liked(items)
        elif filter_type == "group" and filter_id:
            return self._favorites_manager.filter_by_group(items, filter_id)
        elif filter_type == "ungrouped":
            return self._favorites_manager.filter_ungrouped(items)
        elif filter_type == "stack" and filter_id:
            # Filter by job_prefix (stack)
            return [item for item in items if item.get('job_prefix') == filter_id]

        return items

    def _update_filter_counts(self, items):
        """Update the counts shown in the groups panel.

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

        # Count liked items
        liked_count = len(self._favorites_manager.filter_liked(items))

        # Count items per group
        group_counts = {}
        for group in self._favorites_manager.get_groups():
            group_counts[group.group_id] = len(
                self._favorites_manager.filter_by_group(items, group.group_id)
            )

        # Count ungrouped items
        ungrouped_count = len(self._favorites_manager.filter_ungrouped(items))

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

    def _refresh_favorites_state(self):
        """Refresh the favorites state on all visible thumbnails."""
        from shiboken6 import isValid

        if not hasattr(self, '_widget_cache'):
            return

        for path, widget in self._widget_cache.items():
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

        # Subscribe to job events from ComfyUI
        pipeline_events.job_submitted.connect(self._on_job_submitted)
        pipeline_events.job_progress.connect(self._on_job_progress)
        pipeline_events.job_output_ready.connect(self._on_job_output_ready)
        pipeline_events.job_completed.connect(self._on_job_completed)
        pipeline_events.job_failed.connect(self._on_job_failed)
        pipeline_events.all_jobs_completed.connect(self._on_all_jobs_completed)

        # Subscribe to "use as input" from ourselves (for consistency)
        pipeline_events.use_as_input.connect(self._on_use_as_input_requested)

        logger.debug("Gallery tab subscribed to event bus")

    def _on_job_submitted(self, job_id: str, expected_count: int, job_prefix: str):
        """Handle job submitted event from ComfyUI."""
        logger.debug(f"[Gallery] Job submitted: {job_id}, expecting {expected_count} outputs")
        # Update job status bar (if we have one)
        self._update_job_status_bar()

    def _on_job_progress(self, job_id: str, progress: int, status_message: str):
        """Handle job progress event from ComfyUI."""
        # Update job status bar with progress
        self._update_job_status_bar()

    def _on_job_output_ready(self, job_id: str, output_path: str):
        """Handle single output ready event - animate new item arrival."""
        logger.debug(f"[Gallery] Output ready: {output_path}")
        # The refresh is already triggered by polling, but we could add
        # special handling here for immediate item highlighting

    def _on_job_completed(self, job_id: str, output_paths: list):
        """Handle job completion event."""
        logger.debug(f"[Gallery] Job completed: {job_id}, {len(output_paths)} outputs")
        self._update_job_status_bar()

    def _on_job_failed(self, job_id: str, error_message: str):
        """Handle job failure event."""
        logger.warning(f"[Gallery] Job failed: {job_id}: {error_message}")
        self._update_job_status_bar()

    def _on_all_jobs_completed(self, total_outputs: int, elapsed_seconds: float):
        """Handle all jobs completed event - hide job status bar."""
        logger.info(f"[Gallery] All jobs completed: {total_outputs} outputs in {elapsed_seconds:.1f}s")
        self._update_job_status_bar()

    def _on_use_as_input_requested(self, paths: list):
        """Handle request to use gallery images as ComfyUI inputs."""
        # This is handled by operations_manager, but we could add logic here
        # to switch tabs or show confirmation
        pass

    def _update_job_status_bar(self):
        """Update the job status bar based on current active jobs."""
        if not EVENT_BUS_AVAILABLE:
            return

        if not hasattr(self, '_job_status_bar'):
            return

        # Get aggregate progress from event bus
        progress = pipeline_events.get_aggregate_progress()
        self._job_status_bar.update_from_progress(progress)

    def _emit_selection_changed(self):
        """Emit selection changed event to event bus."""
        if not EVENT_BUS_AVAILABLE:
            return

        selected = self._selection_manager.get_selected()
        from core.state_manager import app_state
        app_state.gallery_selected_paths = list(selected)
        pipeline_events.selection_changed.emit(list(selected), len(selected))

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
        self._ui_manager._redisplay_items(force_rebuild=True)

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
            self._ui_manager._redisplay_items(force_rebuild=True)
        else:
            self.show_status_message("Items already in group")
