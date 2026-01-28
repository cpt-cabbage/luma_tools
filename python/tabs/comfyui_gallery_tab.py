"""
ComfyUI Gallery tab module for Luma Tools.

Displays generated images and 3D models from ComfyUI in a gallery view.

This tab uses a manager-based architecture for better maintainability:
- SelectionManager: Multi-select, box selection, shift-click
- ViewerManager: Embedded/fullscreen viewer lifecycle
- OperationsManager: Delete, publish, copy settings
- RefreshController: File watching, polling, scanning
- UIManager: Sort, filter, view mode, user selection
"""

import os

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QTimer, QThreadPool

from .base_tab import BaseTab
from .comfyui_gallery_loader import GalleryLoader
from .comfyui_gallery_manager import GalleryManager
from .gallery import SelectionManager, ViewerManager, OperationsManager, RefreshController, UIManager
from .gallery.favorites_manager import FavoritesManager
from .gallery.groups_panel import GroupsFilterPanel


class ComfyUIGalleryTab(BaseTab):
    """Tab for viewing ComfyUI generated images."""

    @property
    def ui_file(self) -> str:
        return "comfyui_gallery.ui"

    @property
    def tab_name(self) -> str:
        return "ComfyUI Gallery"

    @property
    def tab_id(self) -> str:
        return "comfyui_gallery"

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
        # Start file watcher if not already running
        if self._current_path:
            self._start_watcher(self._current_path)

        # If no initial scan done yet, do one now
        if not self._initial_scan_done:
            self._on_refresh()
            self._initial_scan_done = True

    def on_tab_deactivated(self):
        """Called when user switches away from this tab. Stop watchers and timers."""
        self._refresh_controller.stop_watcher()
        self._refresh_controller.stop_network_polling()

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
        # But NOT for the first scan after prewarm - that should replace to avoid duplicates
        if self._first_scan_after_prewarm:
            incremental = False
            self._first_scan_after_prewarm = False
            self.log("[Gallery] First scan after prewarm, using full replacement display")
        else:
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

    def _setup_groups_panel(self):
        """Set up the groups filter panel as a resizable sidebar."""
        from PySide6.QtWidgets import QSplitter
        from PySide6.QtCore import Qt

        # Create groups panel
        self._groups_panel = GroupsFilterPanel(self._favorites_manager, parent=self.ui)
        self._groups_panel.filter_changed.connect(self._on_filter_changed)
        self._groups_panel.status_message.connect(self.show_status_message)

        # Make panel resizable (remove fixed width, set min/max)
        self._groups_panel.setMinimumWidth(120)
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
