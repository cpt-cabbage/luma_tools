"""
ComfyUI Gallery Manager module.

Handles gallery UI management operations:
- Item sorting and filtering
- Widget creation and caching
- Layout management
- Display coordination
- Section grouping and collapse state
"""

import os
from PySide6.QtCore import QTimer, Qt


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
        # Section collapse state: section_id -> is_expanded
        self._section_states = {}
        # Header widgets: section_id -> GallerySectionHeader
        self._section_headers = {}

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

    def group_items_by_prefix(self, items, separate_inputs=True):
        """Group items by their job prefix.

        Args:
            items: List of item dicts with 'job_prefix' field
            separate_inputs: If True, group all input images into a separate "Inputs" group

        Returns:
            dict: {prefix: [items]} ordered by most recent item in each group
        """
        from collections import OrderedDict

        groups = {}  # prefix -> (most_recent_mtime, [items])
        input_group = []  # Separate list for input images
        input_max_mtime = 0

        for item in items:
            # Separate input images into their own group
            if separate_inputs and item.get('is_input', False):
                input_group.append(item)
                if item['mtime'] > input_max_mtime:
                    input_max_mtime = item['mtime']
                continue

            prefix = item.get('job_prefix') or 'Other'
            if prefix not in groups:
                groups[prefix] = (item['mtime'], [item])
            else:
                current_max_mtime, group_items = groups[prefix]
                group_items.append(item)
                # Track the most recent mtime for sorting groups
                if item['mtime'] > current_max_mtime:
                    groups[prefix] = (item['mtime'], group_items)

        # Sort groups by most recent item, then sort items within each group
        sorted_groups = sorted(groups.items(), key=lambda x: x[1][0], reverse=True)

        # Build ordered dict with items sorted within groups
        result = OrderedDict()
        for prefix, (_, group_items) in sorted_groups:
            # Sort items within group by date descending
            result[prefix] = sorted(group_items, key=lambda x: x['mtime'], reverse=True)

        # Add inputs group at the end if there are any
        if input_group:
            result['📥 Inputs'] = sorted(input_group, key=lambda x: x['mtime'], reverse=True)

        return result

    def is_section_expanded(self, section_id):
        """Check if a section is expanded (default: True for new sections).

        Uses tab's _collapsed_sections set which is loaded from user preferences.
        """
        # Check if section is in collapsed set (collapsed = not expanded)
        if hasattr(self.tab, '_collapsed_sections'):
            return section_id not in self.tab._collapsed_sections
        return self._section_states.get(section_id, True)

    def set_section_expanded(self, section_id, expanded):
        """Set section expanded state and update visibility."""
        self._section_states[section_id] = expanded

        # Update tab's collapsed sections set for persistence
        if hasattr(self.tab, '_collapsed_sections'):
            if expanded:
                self.tab._collapsed_sections.discard(section_id)
            else:
                self.tab._collapsed_sections.add(section_id)

    def on_section_toggled(self, section_id, is_expanded):
        """Handle section header toggle.

        Args:
            section_id: The section being toggled
            is_expanded: New expanded state
        """
        self.set_section_expanded(section_id, is_expanded)

        # Save to user preferences
        from core.user_preferences import save_gallery_settings
        if hasattr(self.tab, '_collapsed_sections'):
            save_gallery_settings(collapsed_sections=list(self.tab._collapsed_sections))

        # Update visibility of items in this section
        if hasattr(self.tab, '_section_items') and section_id in self.tab._section_items:
            for path in self.tab._section_items[section_id]:
                if path in self.tab._widget_cache:
                    widget = self.tab._widget_cache[path]
                    widget.setVisible(is_expanded)

        # Trigger layout update
        container = self.tab.ui.galleryThumbnailContainer
        self.tab._flow_layout.invalidate()
        container.updateGeometry()

    def clear_section_headers(self):
        """Remove all section header widgets."""
        for header in self._section_headers.values():
            header.setParent(None)
            header.deleteLater()
        self._section_headers.clear()

    def display_items(self, items, incremental=False, grouped=False, stacked=False):
        """Display items in the gallery.

        Args:
            items: List of item dicts (already sorted)
            incremental: If True, only add new items without clearing existing widgets
            grouped: If True, display with section headers (uses job_prefix)
            stacked: If True, display as stacked thumbnails (photo pile style)
        """
        container = self.tab.ui.galleryThumbnailContainer

        # Stacked mode takes precedence
        if stacked and items:
            self._display_stacked_items(items)
            self.update_status_count(items)
            self._connect_scroll_events()
            self.tab._visible_items_ordered = [item['path'] for item in items]
            return

        if incremental and hasattr(self.tab, '_widget_cache') and self.tab._widget_cache:
            # Incremental update - only add new items at correct positions
            existing_paths = set(self.tab._widget_cache.keys())
            new_items = [item for item in items if item['path'] not in existing_paths]

            if new_items:
                # Use fast incremental insert that doesn't rebuild the entire layout
                self._insert_new_items_incrementally(items, new_items)
                print(f"[Gallery] Incremental update: added {len(new_items)} new items")
            return

        # Full refresh - clear and rebuild everything
        container.setUpdatesEnabled(False)

        # Clear existing section headers and stacks
        self.clear_section_headers()
        self._clear_stack_widgets()

        while self.tab._flow_layout.count():
            item = self.tab._flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reset widget cache
        self.tab._widget_cache = {}
        self.tab._section_items = {}  # section_id -> [paths]

        if grouped and items:
            # Group items and display with headers
            self._display_grouped_items(items)
        else:
            # Store items for widget creation (non-grouped mode)
            self.tab._pending_items = [(item['path'], item['type']) for item in items]
            self.tab._load_index = 0

            # Create widgets in batches to avoid blocking UI (lazy load triggered after completion)
            self.create_all_widgets()

        # Update status
        self.update_status_count(items)

        # Connect scroll events for lazy loading (if not already connected)
        self._connect_scroll_events()

        # Update ordered list for shift-select range selection
        self.tab._visible_items_ordered = [item['path'] for item in items]

    def _connect_scroll_events(self):
        """Connect scroll events for lazy loading if not already connected."""
        if not hasattr(self.tab, '_scroll_connected') or not self.tab._scroll_connected:
            scroll_area = self.tab.ui.galleryScrollArea
            scroll_area.verticalScrollBar().valueChanged.connect(self.tab._on_scroll)
            scroll_area.horizontalScrollBar().valueChanged.connect(self.tab._on_scroll)
            self.tab._scroll_connected = True

    def _clear_stack_widgets(self):
        """Remove all stack widgets."""
        if hasattr(self, '_stack_widgets'):
            for stack in self._stack_widgets.values():
                stack.setParent(None)
                stack.deleteLater()
        self._stack_widgets = {}

    def _display_stacked_items(self, items):
        """Display items as stacked thumbnails (photo pile style).

        Groups items by job_prefix and shows each group as a single stack widget.
        Clicking a stack expands it in-place with card-deck animation.

        Args:
            items: List of item dicts with job_prefix field
        """
        from ui_components import StackedThumbnailWidget

        container = self.tab.ui.galleryThumbnailContainer
        container.setUpdatesEnabled(False)

        # Clear existing widgets
        self.clear_section_headers()
        self._clear_stack_widgets()

        while self.tab._flow_layout.count():
            item = self.tab._flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reset caches
        self.tab._widget_cache = {}
        self.tab._section_items = {}
        self._stack_widgets = {}

        # Group items by prefix
        groups = self.group_items_by_prefix(items)

        # Create stack widgets for groups with multiple items
        # Single items are shown as regular thumbnails
        for prefix, group_items in groups.items():
            if len(group_items) > 1:
                # Create stacked thumbnail with gallery_tab reference for creating thumbnails
                stack = StackedThumbnailWidget(
                    stack_id=prefix,
                    items=group_items,
                    parent=container,
                    gallery_tab=self.tab
                )
                # Connect signals for tracking expanded state
                stack.expanded.connect(self._on_stack_expanded)
                stack.thumbnail_clicked.connect(self._on_expanded_thumbnail_clicked)
                self._stack_widgets[prefix] = stack
                self.tab._flow_layout.addWidget(stack)

                # Track items for this stack
                self.tab._section_items[prefix] = [item['path'] for item in group_items]
            else:
                # Single item - show as regular thumbnail
                item = group_items[0]
                thumbnail = self._create_thumbnail_widget(item, container)
                if thumbnail:
                    self.tab._widget_cache[item['path']] = thumbnail
                    self.tab._flow_layout.addWidget(thumbnail)

        container.setUpdatesEnabled(True)

        # Trigger thumbnail loading after layout settles
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._load_visible_stack_thumbnails)

    def _load_visible_stack_thumbnails(self):
        """Load thumbnails for visible stack widgets."""
        from shiboken6 import isValid

        scroll_area = self.tab.ui.galleryScrollArea
        viewport = scroll_area.viewport()
        viewport_rect = viewport.rect()

        visible_top = scroll_area.verticalScrollBar().value()
        visible_bottom = visible_top + viewport_rect.height()
        buffer = 200

        visible_top = max(0, visible_top - buffer)
        visible_bottom += buffer

        # Load stack thumbnails
        for stack in self._stack_widgets.values():
            if not isValid(stack):
                continue
            widget_rect = stack.geometry()
            if (widget_rect.bottom() >= visible_top and
                widget_rect.top() <= visible_bottom):
                stack.load_thumbnail_if_needed()

        # Also load regular thumbnails
        self.load_visible_thumbnails()

    def _on_stack_expanded(self, stack_id, is_expanded):
        """Handle stack expansion/collapse state change.

        Args:
            stack_id: The stack identifier (job_prefix)
            is_expanded: True if expanded, False if collapsed
        """
        if is_expanded:
            print(f"[Gallery] Stack expanded: {stack_id}")
            # Track expanded stack
            self.tab._expanded_stack_id = stack_id
        else:
            print(f"[Gallery] Stack collapsed: {stack_id}")
            # Clear expanded state if this was the expanded stack
            if getattr(self.tab, '_expanded_stack_id', None) == stack_id:
                self.tab._expanded_stack_id = None

    def _on_expanded_thumbnail_clicked(self, path, item):
        """Handle click on an expanded thumbnail within a stack.

        Args:
            path: Path to the clicked file
            item: Item dict for the clicked item
        """
        # Forward to the tab's thumbnail click handler
        if hasattr(self.tab, '_on_thumbnail_clicked'):
            self.tab._on_thumbnail_clicked(path)

    def _create_thumbnail_widget(self, item, container, is_editable=None):
        """Create a thumbnail widget for an item.

        Args:
            item: Item dict with path, type, etc.
            container: Parent container widget
            is_editable: Whether the item is editable (None = auto-detect)

        Returns:
            The created thumbnail widget, or None on error
        """
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget

        if is_editable is None:
            is_editable = self.tab._is_own_gallery()

        path = item['path']
        file_type = item['type']
        is_new = path in self.tab._new_items
        item_output_dir = os.path.dirname(path)

        try:
            if file_type == 'model':
                thumbnail = GLBThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=is_editable,
                    is_new=is_new,
                    gallery_tab=self.tab
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
                thumbnail.selection_changed.connect(self.tab._on_selection_changed)
            else:
                thumbnail = GalleryThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=is_editable,
                    is_new=is_new,
                    gallery_tab=self.tab
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.fullscreen_requested.connect(
                    lambda img_path=path: self.tab._open_viewer(img_path, fullscreen=True)
                )
                thumbnail.copy_settings_requested.connect(self.tab._on_copy_settings_requested)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
                thumbnail.selection_changed.connect(self.tab._on_selection_changed)

            return thumbnail
        except Exception as e:
            print(f"[Gallery] Error creating thumbnail for {path}: {e}")
            return None

    def _display_grouped_items(self, items):
        """Display items organized in collapsible sections.

        Args:
            items: List of item dicts with job_prefix field
        """
        from ui_components import GallerySectionHeader, GalleryThumbnailWidget, GLBThumbnailWidget

        container = self.tab.ui.galleryThumbnailContainer
        is_editable = self.tab._is_own_gallery()

        # Group items by prefix
        groups = self.group_items_by_prefix(items)
        print(f"[Gallery] Grouped {len(items)} items into {len(groups)} sections")
        for section_id, group_items in list(groups.items())[:5]:  # Print first 5 groups
            print(f"  - {section_id}: {len(group_items)} items")

        # Create widgets for each group - headers and thumbnails together
        for section_id, group_items in groups.items():
            is_expanded = self.is_section_expanded(section_id)

            # Create section header
            header = GallerySectionHeader(
                section_id=section_id,
                title=section_id,
                count=len(group_items),
                expanded=is_expanded,
                parent=container
            )
            header.toggled.connect(self.on_section_toggled)
            self._section_headers[section_id] = header
            self.tab._flow_layout.addWidget(header)

            # Track items in this section
            self.tab._section_items[section_id] = []

            # Create thumbnails immediately after the header
            for item in group_items:
                path = item['path']
                file_type = item['type']
                self.tab._section_items[section_id].append(path)

                is_new = path in self.tab._new_items
                item_output_dir = os.path.dirname(path)

                if file_type == 'model':
                    thumbnail = GLBThumbnailWidget(
                        path,
                        container,
                        output_dir=item_output_dir,
                        editable=is_editable,
                        is_new=is_new,
                        gallery_tab=self.tab
                    )
                    thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                    thumbnail.deleted.connect(self.tab._on_item_deleted)
                    thumbnail.viewed.connect(self.tab._on_item_viewed)
                    thumbnail.selection_changed.connect(self.tab._on_selection_changed)
                else:
                    thumbnail = GalleryThumbnailWidget(
                        path,
                        container,
                        output_dir=item_output_dir,
                        editable=is_editable,
                        is_new=is_new,
                        gallery_tab=self.tab
                    )
                    thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                    thumbnail.fullscreen_requested.connect(
                        lambda img_path=path: self.tab._open_viewer(img_path, fullscreen=True)
                    )
                    thumbnail.copy_settings_requested.connect(self.tab._on_copy_settings_requested)
                    thumbnail.deleted.connect(self.tab._on_item_deleted)
                    thumbnail.viewed.connect(self.tab._on_item_viewed)
                    thumbnail.selection_changed.connect(self.tab._on_selection_changed)

                # Set visibility based on section state
                thumbnail.setVisible(is_expanded)

                self.tab._widget_cache[path] = thumbnail
                self.tab._flow_layout.addWidget(thumbnail)

        # Re-enable updates and trigger lazy loading
        container.setUpdatesEnabled(True)
        QTimer.singleShot(50, self.tab._load_visible_thumbnails)

    def _create_grouped_widget_batch(self):
        """Create widgets for grouped items in batches."""
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget

        container = self.tab.ui.galleryThumbnailContainer

        if not hasattr(self.tab, '_pending_grouped_items'):
            container.setUpdatesEnabled(True)
            QTimer.singleShot(50, self.tab._load_visible_thumbnails)
            return

        if self.tab._grouped_widget_index >= len(self.tab._pending_grouped_items):
            # Done creating widgets
            container.setUpdatesEnabled(True)
            QTimer.singleShot(50, self.tab._load_visible_thumbnails)
            return

        batch_size = 12
        end_index = min(self.tab._grouped_widget_index + batch_size, len(self.tab._pending_grouped_items))

        for i in range(self.tab._grouped_widget_index, end_index):
            path, file_type, is_visible, section_id = self.tab._pending_grouped_items[i]
            is_new = path in self.tab._new_items
            item_output_dir = os.path.dirname(path)

            if file_type == 'model':
                thumbnail = GLBThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=self.tab._is_editable_cache,
                    is_new=is_new,
                    gallery_tab=self.tab
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
                thumbnail.selection_changed.connect(self.tab._on_selection_changed)
            else:
                thumbnail = GalleryThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=self.tab._is_editable_cache,
                    is_new=is_new,
                    gallery_tab=self.tab
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.fullscreen_requested.connect(
                    lambda img_path=path: self.tab._open_viewer(img_path, fullscreen=True)
                )
                thumbnail.copy_settings_requested.connect(self.tab._on_copy_settings_requested)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
                thumbnail.selection_changed.connect(self.tab._on_selection_changed)

            # Set visibility based on section state
            thumbnail.setVisible(is_visible)

            self.tab._widget_cache[path] = thumbnail
            self.tab._flow_layout.addWidget(thumbnail)

        self.tab._grouped_widget_index = end_index

        # Schedule next batch
        QTimer.singleShot(10, self._create_grouped_widget_batch)

    def _insert_new_items_incrementally(self, sorted_items, new_items):
        """Insert new items at their correct positions without rebuilding the layout.

        This is much faster than recreating all widgets and avoids visual flash.

        Args:
            sorted_items: Full list of items in sorted order
            new_items: List of only the new items to add
        """
        from ui_components import GalleryThumbnailWidget, GLBThumbnailWidget

        container = self.tab.ui.galleryThumbnailContainer
        is_editable = self.tab._is_own_gallery()

        # Build a set of new paths for quick lookup
        new_paths = set(item['path'] for item in new_items)

        # Disable updates during insertion
        container.setUpdatesEnabled(False)

        try:
            # Create widgets for new items and insert at correct positions
            for target_index, item in enumerate(sorted_items):
                path = item['path']

                # Skip if this item already exists (not new)
                if path not in new_paths:
                    continue

                file_type = item['type']
                is_new = path in self.tab._new_items
                item_output_dir = os.path.dirname(path)

                # Create the widget
                if file_type == 'model':
                    thumbnail = GLBThumbnailWidget(
                        path,
                        container,
                        output_dir=item_output_dir,
                        editable=is_editable,
                        is_new=is_new,
                        gallery_tab=self.tab
                    )
                    thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                    thumbnail.deleted.connect(self.tab._on_item_deleted)
                    thumbnail.viewed.connect(self.tab._on_item_viewed)
                    thumbnail.selection_changed.connect(self.tab._on_selection_changed)
                else:
                    thumbnail = GalleryThumbnailWidget(
                        path,
                        container,
                        output_dir=item_output_dir,
                        editable=is_editable,
                        is_new=is_new,
                        gallery_tab=self.tab
                    )
                    thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                    thumbnail.fullscreen_requested.connect(
                        lambda img_path=path: self.tab._open_viewer(img_path, fullscreen=True)
                    )
                    thumbnail.copy_settings_requested.connect(self.tab._on_copy_settings_requested)
                    thumbnail.deleted.connect(self.tab._on_item_deleted)
                    thumbnail.viewed.connect(self.tab._on_item_viewed)
                    thumbnail.selection_changed.connect(self.tab._on_selection_changed)

                # Add to cache
                self.tab._widget_cache[path] = thumbnail

                # Insert at the correct position in the layout
                self.tab._flow_layout.insertWidget(target_index, thumbnail)

            # Update status count
            self.update_status_count(sorted_items)

            # Update ordered list for shift-select range selection
            self.tab._visible_items_ordered = [item['path'] for item in sorted_items]

        finally:
            container.setUpdatesEnabled(True)

        # Trigger lazy loading for the new visible items
        QTimer.singleShot(50, self.tab._load_visible_thumbnails)

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

        # Update ordered list for shift-select range selection
        self.tab._visible_items_ordered = [item['path'] for item in items]

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
                    is_new=is_new,
                    gallery_tab=self.tab
                )
                thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
                thumbnail.deleted.connect(self.tab._on_item_deleted)
                thumbnail.viewed.connect(self.tab._on_item_viewed)
                thumbnail.selection_changed.connect(self.tab._on_selection_changed)
            else:
                thumbnail = GalleryThumbnailWidget(
                    path,
                    container,
                    output_dir=item_output_dir,
                    editable=self.tab._is_editable_cache,
                    is_new=is_new,
                    gallery_tab=self.tab
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
