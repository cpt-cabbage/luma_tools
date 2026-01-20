"""
ComfyUI Gallery Manager module.

Handles gallery UI management operations:
- Item sorting and filtering
- Widget creation and caching
- Layout management
- Display coordination
"""

import os
from PySide6.QtCore import QTimer


class GalleryManager:
    """Handles gallery UI management operations.

    This class manages the gallery state and widget lifecycle.
    It depends on tab instance for UI access and state.
    """

    def __init__(self, tab):
        """Initialize the gallery manager.

        Args:
            tab: The ComfyUIGalleryTab instance
        """
        self.tab = tab

    def sort_items(self, items, sort_mode):
        """Sort items based on sort mode.

        Args:
            items: List of item dicts
            sort_mode: Sort mode string

        Returns:
            Sorted list of items
        """
        if sort_mode == "date_desc":
            return sorted(items, key=lambda x: x['mtime'], reverse=True)
        elif sort_mode == "date_asc":
            return sorted(items, key=lambda x: x['mtime'])
        elif sort_mode == "name_asc":
            return sorted(items, key=lambda x: x['name'])
        elif sort_mode == "name_desc":
            return sorted(items, key=lambda x: x['name'], reverse=True)
        elif sort_mode == "workflow":
            # Sort by workflow name, then by date within each workflow
            return sorted(items, key=lambda x: (x['workflow'] or 'zzz_unknown', -x['mtime']))
        else:
            return items

    def display_items(self, items, incremental=False):
        """Display items in the gallery.

        Args:
            items: List of item dicts (already sorted)
            incremental: If True, only add new items without clearing existing widgets
        """
        container = self.tab.ui.galleryThumbnailContainer

        if incremental and hasattr(self.tab, '_widget_cache') and self.tab._widget_cache:
            # Incremental update - only add new items in correct sorted positions
            existing_paths = set(self.tab._widget_cache.keys())
            new_items = [item for item in items if item['path'] not in existing_paths]

            if new_items:
                # Disable updates during insertion
                container.setUpdatesEnabled(False)

                # Store only new items for widget creation (to be inserted later)
                self.tab._pending_items = [(item['path'], item['type']) for item in new_items]
                # Also store full sorted items list for proper insertion
                self.tab._sorted_items_for_insertion = items

                # Update status with new count
                self.update_status_count(items)

                # Create widgets for new items only
                self.create_all_widgets_incremental()

                print(f"[Gallery] Incremental update: added {len(new_items)} new items")
            return

        # Full refresh - clear and rebuild everything
        container.setUpdatesEnabled(False)

        while self.tab._flow_layout.count():
            item = self.tab._flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reset widget cache
        self.tab._widget_cache = {}

        # Store items for widget creation
        self.tab._pending_items = [(item['path'], item['type']) for item in items]
        self.tab._load_index = 0

        # Update status
        self.update_status_count(items)

        # Connect scroll events for lazy loading (if not already connected)
        if not hasattr(self.tab, '_scroll_connected') or not self.tab._scroll_connected:
            scroll_area = self.tab.ui.galleryScrollArea
            scroll_area.verticalScrollBar().valueChanged.connect(self.tab._on_scroll)
            scroll_area.horizontalScrollBar().valueChanged.connect(self.tab._on_scroll)
            self.tab._scroll_connected = True

        # Create widgets in batches to avoid blocking UI (lazy load triggered after completion)
        self.create_all_widgets()

    def reorder_widgets(self, items):
        """Reorder existing widgets without recreating them.

        This is much faster than display_items when just changing sort order.

        Args:
            items: List of item dicts (already sorted)
        """
        container = self.tab.ui.galleryThumbnailContainer
        container.setUpdatesEnabled(False)

        try:
            # Remove all widgets from layout (but don't delete them)
            while self.tab._flow_layout.count():
                self.tab._flow_layout.takeAt(0)

            # Add widgets back in sorted order using cache
            for item_dict in items:
                path = item_dict['path']
                if path in self.tab._widget_cache:
                    widget = self.tab._widget_cache[path]
                    self.tab._flow_layout.addWidget(widget)

        finally:
            container.setUpdatesEnabled(True)

        # Force layout update
        self.tab._flow_layout.invalidate()
        container.updateGeometry()

        # Trigger lazy loading for visible items after reorder
        QTimer.singleShot(50, self.tab._load_visible_thumbnails)

    def create_all_widgets(self):
        """Create thumbnail widgets in batches to avoid blocking the UI."""
        if not hasattr(self.tab, '_pending_items') or not self.tab._pending_items:
            # Re-enable updates since we're not creating anything
            self.tab.ui.galleryThumbnailContainer.setUpdatesEnabled(True)
            return

        # Ensure widget cache exists
        if not hasattr(self.tab, '_widget_cache'):
            self.tab._widget_cache = {}

        # Updates already disabled by display_items, don't toggle
        # Start batched creation
        self.tab._widget_create_index = 0
        self.tab._widget_batch_size = 12  # Create 12 widgets per batch for smoother UI
        self.tab._is_editable_cache = self.tab._is_own_gallery()
        self.create_widget_batch()

    def create_all_widgets_incremental(self):
        """Create thumbnail widgets for incremental update (inserts in sorted positions)."""
        if not hasattr(self.tab, '_pending_items') or not self.tab._pending_items:
            # Re-enable updates since we're not creating anything
            self.tab.ui.galleryThumbnailContainer.setUpdatesEnabled(True)
            return

        # Ensure widget cache exists
        if not hasattr(self.tab, '_widget_cache'):
            self.tab._widget_cache = {}

        # Start batched creation
        self.tab._widget_create_index = 0
        self.tab._widget_batch_size = 12
        self.tab._is_editable_cache = self.tab._is_own_gallery()
        self.create_widget_batch_incremental()

    def create_widget_batch(self):
        """Create a batch of widgets, then schedule the next batch."""
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget

        container = self.tab.ui.galleryThumbnailContainer

        if not hasattr(self.tab, '_pending_items') or self.tab._widget_create_index >= len(self.tab._pending_items):
            # All widgets created - re-enable updates and trigger layout
            container.setUpdatesEnabled(True)

            # Trigger initial lazy load after layout settles
            QTimer.singleShot(50, self.tab._load_visible_thumbnails)
            return

        end_index = min(self.tab._widget_create_index + self.tab._widget_batch_size, len(self.tab._pending_items))

        for i in range(self.tab._widget_create_index, end_index):
            path, file_type = self.tab._pending_items[i]
            is_new = path in self.tab._new_items
            item_output_dir = os.path.dirname(path)

            if file_type == 'model':
                thumbnail = GLBThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=self.tab._is_editable_cache,
                    is_new=is_new
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
            else:
                thumbnail = GalleryThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=self.tab._is_editable_cache,
                    is_new=is_new
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.fullscreen_requested.connect(
                    lambda img_path=path: self.tab._open_viewer(img_path, fullscreen=True)
                )
                thumbnail.copy_settings_requested.connect(self.tab._on_copy_settings_requested)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
                thumbnail.selection_changed.connect(self.tab._on_selection_changed)

            self.tab._widget_cache[path] = thumbnail
            self.tab._flow_layout.addWidget(thumbnail)

        self.tab._widget_create_index = end_index

        # Schedule next batch with small delay to keep UI responsive
        QTimer.singleShot(10, self.create_widget_batch)

    def create_widget_batch_incremental(self):
        """Create a batch of widgets for incremental update and insert in correct positions."""
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget

        container = self.tab.ui.galleryThumbnailContainer

        if not hasattr(self.tab, '_pending_items') or self.tab._widget_create_index >= len(self.tab._pending_items):
            # All widgets created - reorder to match sorted list
            if hasattr(self.tab, '_sorted_items_for_insertion'):
                sorted_items = self.tab._sorted_items_for_insertion
                # Remove all widgets from layout (but don't delete them)
                while self.tab._flow_layout.count():
                    self.tab._flow_layout.takeAt(0)

                # Add widgets back in sorted order using cache
                for item_dict in sorted_items:
                    path = item_dict['path']
                    if path in self.tab._widget_cache:
                        widget = self.tab._widget_cache[path]
                        self.tab._flow_layout.addWidget(widget)

                # Clean up temporary storage
                delattr(self.tab, '_sorted_items_for_insertion')

            # Re-enable updates and trigger layout
            container.setUpdatesEnabled(True)
            self.tab._flow_layout.invalidate()
            container.updateGeometry()

            # Trigger lazy load for visible items
            QTimer.singleShot(50, self.tab._load_visible_thumbnails)
            return

        end_index = min(self.tab._widget_create_index + self.tab._widget_batch_size, len(self.tab._pending_items))

        for i in range(self.tab._widget_create_index, end_index):
            path, file_type = self.tab._pending_items[i]
            is_new = path in self.tab._new_items
            item_output_dir = os.path.dirname(path)

            if file_type == 'model':
                thumbnail = GLBThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=self.tab._is_editable_cache,
                    is_new=is_new
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
            else:
                thumbnail = GalleryThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=self.tab._is_editable_cache,
                    is_new=is_new
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.fullscreen_requested.connect(
                    lambda img_path=path: self.tab._open_viewer(img_path, fullscreen=True)
                )
                thumbnail.copy_settings_requested.connect(self.tab._on_copy_settings_requested)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
                thumbnail.selection_changed.connect(self.tab._on_selection_changed)

            self.tab._widget_cache[path] = thumbnail
            # Don't add to layout yet - will be reordered after all widgets are created

        self.tab._widget_create_index = end_index

        # Schedule next batch
        QTimer.singleShot(10, self.create_widget_batch_incremental)

    def load_visible_thumbnails(self):
        """Load thumbnails for widgets that are currently visible in the viewport.

        Loads in batches to avoid overwhelming the thread pool.
        """
        from shiboken6 import isValid

        if not hasattr(self.tab, '_widget_cache') or not self.tab._widget_cache:
            return

        scroll_area = self.tab.ui.galleryScrollArea
        viewport = scroll_area.viewport()
        viewport_rect = viewport.rect()

        # Convert viewport rect to container coordinates
        visible_top = scroll_area.verticalScrollBar().value()
        visible_bottom = visible_top + viewport_rect.height()
        visible_left = scroll_area.horizontalScrollBar().value()
        visible_right = visible_left + viewport_rect.width()

        # Add buffer zone for smoother scrolling
        buffer = 200
        visible_top = max(0, visible_top - buffer)
        visible_bottom += buffer
        visible_left = max(0, visible_left - buffer)
        visible_right += buffer

        # Collect widgets that need loading (not already loaded)
        widgets_to_load = []
        for widget in self.tab._widget_cache.values():
            # Check widget validity (may have been deleted during refresh)
            if not widget or not isValid(widget) or not hasattr(widget, 'load_thumbnail_if_needed'):
                continue
            if getattr(widget, '_thumbnail_loaded', False):
                continue

            widget_rect = widget.geometry()
            if (widget_rect.bottom() >= visible_top and
                widget_rect.top() <= visible_bottom and
                widget_rect.right() >= visible_left and
                widget_rect.left() <= visible_right):
                widgets_to_load.append(widget)

        if not widgets_to_load:
            return

        # Store and start batched loading
        self.tab._pending_thumbnail_loads = widgets_to_load
        self.tab._thumbnail_load_index = 0
        self.load_thumbnail_batch()

    def load_thumbnail_batch(self):
        """Load thumbnails one at a time with delays to prevent UI lag."""
        from shiboken6 import isValid

        if not hasattr(self.tab, '_pending_thumbnail_loads'):
            return
        if self.tab._thumbnail_load_index >= len(self.tab._pending_thumbnail_loads):
            return

        # Load one widget at a time to stagger worker completions
        # Check if widget is still valid before accessing it
        widget = self.tab._pending_thumbnail_loads[self.tab._thumbnail_load_index]
        if isValid(widget):
            widget.load_thumbnail_if_needed()
        self.tab._thumbnail_load_index += 1

        # Schedule next with delay so workers don't all finish at once
        if self.tab._thumbnail_load_index < len(self.tab._pending_thumbnail_loads):
            QTimer.singleShot(20, self.load_thumbnail_batch)

    def update_status_count(self, items):
        """Update the status bar with item counts.

        Args:
            items: List of item dicts
        """
        image_count = sum(1 for item in items if item['type'] == 'image')
        model_count = sum(1 for item in items if item['type'] == 'model')
        total_count = len(items)

        if total_count == 0:
            self.tab.ui.GalleryStatus.setText("No files found")
        else:
            parts = []
            if image_count > 0:
                parts.append(f"{image_count} image{'s' if image_count != 1 else ''}")
            if model_count > 0:
                parts.append(f"{model_count} 3D model{'s' if model_count != 1 else ''}")
            self.tab.ui.GalleryStatus.setText(" • ".join(parts) if parts else f"{total_count} files")
