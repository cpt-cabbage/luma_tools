"""
ComfyUI Gallery Manager module.

Handles gallery UI management operations:
- Item sorting and filtering
- Widget creation and caching
- Layout management
- Display coordination (stacked and grid views)
"""

import os
import logging
from PySide6.QtCore import QTimer, Qt
from shiboken6 import isValid
from ui_components import ThumbnailWidget, StackedThumbnailWidget


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

    def group_items_by_prefix(self, items, separate_inputs=True):
        """Group items by their job prefix, preserving the input sort order.

        Args:
            items: List of item dicts with 'job_prefix' field (already sorted by user's preference)
            separate_inputs: If True, group all input images into a separate "Inputs" group

        Returns:
            dict: {prefix: [items]} ordered by first item's position in the input list
        """
        from collections import OrderedDict

        groups = {}  # prefix -> (first_seen_index, [items])
        input_group = []  # Separate list for input images
        input_first_index = None

        for idx, item in enumerate(items):
            # Separate input images into their own group
            if separate_inputs and item.get('is_input', False):
                input_group.append(item)
                if input_first_index is None:
                    input_first_index = idx
                continue

            prefix = item.get('job_prefix') or 'Other'
            if prefix not in groups:
                # Store the index of first item in this group (for ordering groups)
                groups[prefix] = (idx, [item])
            else:
                first_idx, group_items = groups[prefix]
                group_items.append(item)

        # Sort groups by first-seen index (preserves input sort order for groups)
        sorted_groups = sorted(groups.items(), key=lambda x: x[1][0])

        # Build ordered dict - items within groups already in correct order from input
        result = OrderedDict()
        for prefix, (_, group_items) in sorted_groups:
            result[prefix] = group_items  # Already sorted from input

        # Add inputs group at the end if there are any
        if input_group:
            result['📥 Inputs'] = input_group  # Already sorted from input

        return result

    def group_items_by_groups(self, items, fallback_to_job=True, separate_inputs=True):
        """Group items by their user-defined groups, preserving input sort order.

        Args:
            items: List of item dicts (already sorted by user's preference)
            fallback_to_job: If True, ungrouped items are stacked by job_prefix
            separate_inputs: If True, group all input images into a separate "Inputs" group

        Returns:
            OrderedDict: {group_name: [items]} plus group_colors dict
        """
        from collections import OrderedDict

        # Get favorites manager from tab
        favorites_manager = getattr(self.tab, '_favorites_manager', None)
        if not favorites_manager:
            # Fall back to job prefix grouping if no favorites manager
            return self.group_items_by_prefix(items, separate_inputs)

        groups = {}  # group_id -> (group_def, first_seen_index, [items])
        ungrouped = []  # Items not in any group
        input_group = []  # Separate list for input images

        for idx, item in enumerate(items):
            # Separate input images
            if separate_inputs and item.get('is_input', False):
                input_group.append(item)
                continue

            # Check if item is in any group
            item_groups = favorites_manager.get_item_groups(item['path'])
            if item_groups:
                # Use primary (first) group
                primary_group_id = item_groups[0]
                group_def = favorites_manager.get_group(primary_group_id)
                if group_def:
                    if primary_group_id not in groups:
                        groups[primary_group_id] = (group_def, idx, [item])
                    else:
                        group_def_stored, first_idx, group_items = groups[primary_group_id]
                        group_items.append(item)
                else:
                    ungrouped.append(item)
            else:
                ungrouped.append(item)

        # Sort groups by user-defined order, then by first-seen index
        sorted_groups = sorted(
            groups.items(),
            key=lambda x: (x[1][0].order, x[1][1])  # (group_def.order, first_seen_index)
        )

        # Build ordered dict - items already in correct order from input
        result = OrderedDict()
        group_colors = {}  # Store colors for stacked widget styling

        for group_id, (group_def, _, group_items) in sorted_groups:
            group_name = f"🏷 {group_def.name}"
            result[group_name] = group_items  # Already sorted from input
            group_colors[group_name] = group_def.color

        # Handle ungrouped items
        if ungrouped:
            if fallback_to_job:
                # Stack ungrouped items by job prefix (preserves sort order)
                job_groups = self.group_items_by_prefix(ungrouped, separate_inputs=False)
                for prefix, job_items in job_groups.items():
                    result[prefix] = job_items
            else:
                result['Ungrouped'] = ungrouped  # Already sorted from input

        # Add inputs group at the end
        if input_group:
            result['📥 Inputs'] = input_group  # Already sorted from input

        # Store group colors on the manager for use by display methods
        self._group_colors = group_colors

        return result

    def display_items(self, items, view_mode=None, incremental=False):
        """Display items in the gallery.

        Args:
            items: List of item dicts (already sorted)
            view_mode: View mode string - "stacked" or "grid" (default)
            incremental: If True, only add new items without clearing existing widgets
        """
        container = self.tab.ui.galleryThumbnailContainer

        # Stacked mode
        stacked = view_mode == "stacked"

        if stacked and items:
            if incremental and hasattr(self, '_stack_widgets') and self._stack_widgets:
                # Incremental update for stacked mode
                self._update_stacked_items_incrementally(items)
            else:
                # Full rebuild
                self._display_stacked_items(items)
            self.update_status_count(items)
            self._connect_scroll_events()
            self.tab._visible_items_ordered = [item['path'] for item in items]
            return

        # Grid mode - check for widget recycling opportunity
        if hasattr(self.tab, '_widget_cache') and self.tab._widget_cache:
            target_paths = set(item['path'] for item in items)
            existing_paths = set(self.tab._widget_cache.keys())

            # Check if this is a filter change (subset/superset of existing)
            # or incremental addition
            if incremental:
                new_items = [item for item in items if item['path'] not in existing_paths]
                stale_paths = existing_paths - target_paths

                # Remove stale widgets (items no longer in scan results)
                if stale_paths:
                    self._remove_stale_widgets(stale_paths)
                    logging.info(f"[Gallery] Incremental sync: removed {len(stale_paths)} stale items")

                # Add new items
                if new_items:
                    self._insert_new_items_incrementally(items, new_items)
                    logging.info(f"[Gallery] Incremental sync: added {len(new_items)} new items")

                if stale_paths or new_items:
                    self.update_status_count(items)
                    self.tab._visible_items_ordered = [item['path'] for item in items]
                return

            # Check if we can recycle widgets (filter change scenario)
            # All target items exist in cache, just need to show/hide and reorder
            if target_paths <= existing_paths:
                recycled = self._recycle_widgets_for_filter(items, target_paths, existing_paths)
                if recycled:
                    return

        # Full refresh - clear and rebuild everything
        # Ensure layout guard is released in case an animation was in progress
        if hasattr(self.tab, '_flow_layout') and self.tab._flow_layout._animation_active:
            self.tab._flow_layout.end_animation()

        container.setUpdatesEnabled(False)

        # Clear existing stacks
        self._clear_stack_widgets()

        while self.tab._flow_layout.count():
            item = self.tab._flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reset widget cache
        self.tab._widget_cache = {}
        self.tab._section_items = {}  # section_id -> [paths]

        # Store items for widget creation (grid mode)
        # Include has_metadata and job_prefix for proper styling
        self.tab._pending_items = [
            (item['path'], item['type'], item.get('has_metadata', False), item.get('job_prefix'))
            for item in items
        ]
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

    def _recycle_widgets_for_filter(self, items, target_paths, existing_paths):
        """Recycle existing widgets for a filter change instead of rebuilding.

        When filtering, we often just need to hide some widgets and reorder the visible ones.
        This is much faster than deleting and recreating widgets.

        Args:
            items: List of item dicts (sorted, filtered)
            target_paths: Set of paths that should be visible
            existing_paths: Set of paths that have cached widgets

        Returns:
            True if recycling was successful, False if full rebuild needed
        """


        container = self.tab.ui.galleryThumbnailContainer

        # Verify all target widgets exist and are valid
        for path in target_paths:
            widget = self.tab._widget_cache.get(path)
            if not widget or not isValid(widget):
                return False

        container.setUpdatesEnabled(False)

        try:
            # Remove all widgets from layout (but keep in cache)
            while self.tab._flow_layout.count():
                self.tab._flow_layout.takeAt(0)

            # Add only the target widgets in sorted order
            for item in items:
                path = item['path']
                widget = self.tab._widget_cache[path]
                if isValid(widget):
                    widget.setVisible(True)
                    self.tab._flow_layout.addWidget(widget)

            # Hide widgets that are filtered out (keep in cache for quick restoration)
            hidden_paths = existing_paths - target_paths
            for path in hidden_paths:
                widget = self.tab._widget_cache.get(path)
                if widget and isValid(widget):
                    widget.setVisible(False)

        finally:
            container.setUpdatesEnabled(True)

        # Force layout recalculation
        self.tab._flow_layout.invalidate()
        container.updateGeometry()

        # Update status and ordered list
        self.update_status_count(items)
        self.tab._visible_items_ordered = [item['path'] for item in items]

        # Note: We don't reload thumbnails - recycled widgets already have them loaded
        logging.info(f"[Gallery] Widget recycling: {len(target_paths)} shown, {len(hidden_paths)} hidden")
        return True

    def _clear_stack_widgets(self):
        """Remove all stack widgets."""
        if hasattr(self, '_stack_widgets'):
            for stack in self._stack_widgets.values():
                # Collapse without animation to avoid blocking the layout guard
                if stack.is_expanded():
                    stack.collapse(animated=False)
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


        container = self.tab.ui.galleryThumbnailContainer

        # Ensure layout guard is released in case an animation was in progress
        if hasattr(self.tab, '_flow_layout') and self.tab._flow_layout._animation_active:
            self.tab._flow_layout.end_animation()

        container.setUpdatesEnabled(False)

        # Clear existing widgets
        self._clear_stack_widgets()

        while self.tab._flow_layout.count():
            item = self.tab._flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reset caches
        self.tab._widget_cache = {}
        self.tab._section_items = {}
        self._stack_widgets = {}
        self._group_colors = {}

        # Get stacking mode from settings
        from core.settings_manager import get_setting
        stacking_mode = get_setting("gallery_stacking_mode")

        # Group items by job prefix (user groups are shown via sidebar filter, not stacking)
        groups = self.group_items_by_prefix(items)

        # Get favorites manager once for all stacks
        favorites_manager = getattr(self.tab, '_favorites_manager', None)

        # Create stack widgets for groups with multiple items
        # Single items are shown as regular thumbnails
        for prefix, group_items in groups.items():
            if len(group_items) > 1:
                # Get group color if available
                group_color = self._group_colors.get(prefix)

                # Create stacked thumbnail with gallery_tab reference for creating thumbnails
                stack = StackedThumbnailWidget(
                    stack_id=prefix,
                    items=group_items,
                    parent=container,
                    gallery_tab=self.tab,
                    group_color=group_color
                )
                # Set favorites manager for likes/groups functionality
                if favorites_manager:
                    stack.set_favorites_manager(favorites_manager)

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
                    # Track in section_items so incremental sync can find this prefix
                    self.tab._section_items[prefix] = [item['path']]

        container.setUpdatesEnabled(True)

        # Trigger thumbnail loading after layout settles
        from PySide6.QtCore import QTimer
        QTimer.singleShot(150, self._load_visible_stack_thumbnails)

    def _update_stacked_items_incrementally(self, items):
        """Update stacked view incrementally without full rebuild.

        Handles additions, removals, and updates of stacks/items.
        This prevents the visual "flash" when new images are added.

        Args:
            items: List of item dicts with job_prefix field
        """



        container = self.tab.ui.galleryThumbnailContainer

        # Group new items by prefix
        new_groups = self.group_items_by_prefix(items)

        # Get existing prefixes from stacks and single items
        existing_stack_prefixes = set(self._stack_widgets.keys())

        # For single items in widget_cache, extract their prefixes from section_items
        existing_single_prefixes = set()
        if hasattr(self.tab, '_section_items'):
            for prefix, paths in self.tab._section_items.items():
                if prefix not in existing_stack_prefixes and len(paths) == 1:
                    existing_single_prefixes.add(prefix)

        existing_prefixes = existing_stack_prefixes | existing_single_prefixes
        new_prefixes = set(new_groups.keys())

        # Find additions and removals
        added_prefixes = new_prefixes - existing_prefixes
        removed_prefixes = existing_prefixes - new_prefixes

        # Check for stacks that need updating (existing stacks with changed items)
        stacks_to_update = []
        for prefix in existing_prefixes & new_prefixes:
            old_paths = set(self.tab._section_items.get(prefix, []))
            new_paths = set(item['path'] for item in new_groups[prefix])
            if new_paths != old_paths:
                stacks_to_update.append(prefix)

        if not added_prefixes and not removed_prefixes and not stacks_to_update:
            # No changes - just update internal tracking
            self.tab._section_items = {}
            for prefix, group_items in new_groups.items():
                self.tab._section_items[prefix] = [item['path'] for item in group_items]
            return

        # Disable updates during modifications
        container.setUpdatesEnabled(False)

        try:
            # Remove stale stacks/items
            for prefix in removed_prefixes:
                if prefix in self._stack_widgets:
                    stack = self._stack_widgets.pop(prefix)
                    if isValid(stack):
                        if stack.is_expanded():
                            stack.collapse(animated=False)
                        self.tab._flow_layout.removeWidget(stack)
                        stack.deleteLater()
                else:
                    # Single item - remove from widget cache
                    paths = self.tab._section_items.get(prefix, [])
                    for path in paths:
                        widget = self.tab._widget_cache.pop(path, None)
                        if widget and isValid(widget):
                            self.tab._flow_layout.removeWidget(widget)
                            widget.deleteLater()
                # Clean up section tracking
                self.tab._section_items.pop(prefix, None)

            # Update existing stacks that have changed items
            for prefix in stacks_to_update:
                if prefix in self._stack_widgets:
                    stack = self._stack_widgets[prefix]
                    if isValid(stack):
                        stack.update_items(new_groups[prefix])
                        self.tab._section_items[prefix] = [item['path'] for item in new_groups[prefix]]

            # Add new stacks/thumbnails
            favorites_manager = getattr(self.tab, '_favorites_manager', None)
            new_widgets = []

            for prefix in added_prefixes:
                group_items = new_groups[prefix]

                if len(group_items) > 1:
                    # Create stacked thumbnail
                    stack = StackedThumbnailWidget(
                        stack_id=prefix,
                        items=group_items,
                        parent=container,
                        gallery_tab=self.tab
                    )
                    if favorites_manager:
                        stack.set_favorites_manager(favorites_manager)

                    stack.expanded.connect(self._on_stack_expanded)
                    stack.thumbnail_clicked.connect(self._on_expanded_thumbnail_clicked)
                    self._stack_widgets[prefix] = stack
                    self.tab._flow_layout.addWidget(stack)
                    new_widgets.append(stack)

                    self.tab._section_items[prefix] = [item['path'] for item in group_items]
                else:
                    # Single item - show as regular thumbnail
                    item = group_items[0]
                    thumbnail = self._create_thumbnail_widget(item, container)
                    if thumbnail:
                        self.tab._widget_cache[item['path']] = thumbnail
                        self.tab._flow_layout.addWidget(thumbnail)
                        new_widgets.append(thumbnail)
                        self.tab._section_items[prefix] = [item['path']]

            changes = []
            if added_prefixes:
                changes.append(f"{len(added_prefixes)} added")
            if removed_prefixes:
                changes.append(f"{len(removed_prefixes)} removed")
            if stacks_to_update:
                changes.append(f"{len(stacks_to_update)} updated")
            if changes:
                logging.info(f"[Gallery] Incremental stacked sync: {', '.join(changes)}")

            # Reorder all widgets to match the sorted item order
            if added_prefixes or removed_prefixes:
                self._reorder_stacks(items)

        finally:
            container.setUpdatesEnabled(True)

        # Animate newly added widgets
        if new_widgets:
            self._animate_new_items(new_widgets)

        # Load thumbnails for new items
        QTimer.singleShot(150, self._load_visible_stack_thumbnails)

    def _reorder_stacks(self, items):
        """Reorder all stack/single widgets to match the sorted item order.

        After incremental additions/removals, widgets may be out of order.
        This repositions them to match the expected sort order.

        Args:
            items: List of item dicts in sorted order
        """


        # Use the same grouping logic as display to get correct prefix order
        groups = self.group_items_by_prefix(items)
        seen_prefixes = list(groups.keys())

        # Reposition widgets in the layout according to sorted prefix order
        target_index = 0
        for prefix in seen_prefixes:
            if prefix in self._stack_widgets:
                stack = self._stack_widgets[prefix]
                if isValid(stack):
                    # Remove and re-insert at correct position
                    self.tab._flow_layout.removeWidget(stack)
                    self.tab._flow_layout.insertWidget(target_index, stack)
                    target_index += 1
            else:
                # Single item - find its widget in cache
                paths = self.tab._section_items.get(prefix, [])
                for path in paths:
                    widget = self.tab._widget_cache.get(path)
                    if widget and isValid(widget):
                        self.tab._flow_layout.removeWidget(widget)
                        self.tab._flow_layout.insertWidget(target_index, widget)
                        target_index += 1

    def _load_visible_stack_thumbnails(self):
        """Load thumbnails for visible stack widgets."""


        scroll_area = self.tab.ui.galleryScrollArea
        viewport = scroll_area.viewport()
        viewport_rect = viewport.rect()

        # Retry if viewport hasn't been laid out yet
        if viewport_rect.height() <= 0:
            QTimer.singleShot(150, self._load_visible_stack_thumbnails)
            return

        visible_top = scroll_area.verticalScrollBar().value()
        visible_bottom = visible_top + viewport_rect.height()
        buffer = 300

        visible_top = max(0, visible_top - buffer)
        visible_bottom += buffer

        # Load stack thumbnails
        for stack in self._stack_widgets.values():
            if not isValid(stack):
                continue
            widget_rect = stack.geometry()
            # Stacks not yet laid out (zero geometry) are assumed visible
            if widget_rect.width() == 0 and widget_rect.height() == 0:
                stack.load_thumbnail_if_needed()
                continue
            if (widget_rect.bottom() >= visible_top and
                widget_rect.top() <= visible_bottom):
                stack.load_thumbnail_if_needed()

        # Also load regular thumbnails
        self.load_visible_thumbnails()

    def _animate_new_items(self, widgets):
        """Fade in newly inserted gallery items with staggered animation.

        Args:
            widgets: List of newly created widgets to animate
        """
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        if not widgets:
            return

        # Store references to prevent GC
        if not hasattr(self, '_new_item_animations'):
            self._new_item_animations = []

        duration = 250
        stagger = 30
        max_animated = 20

        for idx, widget in enumerate(widgets[:max_animated]):
            opacity_effect = QGraphicsOpacityEffect(widget)
            opacity_effect.setOpacity(0.0)
            widget.setGraphicsEffect(opacity_effect)

            anim = QPropertyAnimation(opacity_effect, b"opacity")
            anim.setDuration(duration)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._new_item_animations.append(anim)

            delay = idx * stagger
            QTimer.singleShot(delay, anim.start)

        # Cleanup after animations complete
        total_time = min(len(widgets), max_animated) * stagger + duration + 50
        QTimer.singleShot(total_time, self._cleanup_new_item_animations)

    def _cleanup_new_item_animations(self):
        """Clean up new item animation references and remove opacity effects."""


        for anim in getattr(self, '_new_item_animations', []):
            target = anim.targetObject()
            if target:
                # Find the widget that has this opacity effect
                parent = target.parent()
                if parent and isValid(parent):
                    parent.setGraphicsEffect(None)
        self._new_item_animations = []

    def _on_stack_expanded(self, stack_id, is_expanded):
        """Handle stack expansion/collapse state change.

        Args:
            stack_id: The stack identifier (job_prefix)
            is_expanded: True if expanded, False if collapsed
        """
        if is_expanded:
            logging.info(f"[Gallery] Stack expanded: {stack_id}")
            # Track expanded stack
            self.tab._expanded_stack_id = stack_id
        else:
            logging.info(f"[Gallery] Stack collapsed: {stack_id}")
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


        if is_editable is None:
            is_editable = self.tab._is_own_gallery()

        path = item['path']
        file_type = item['type']
        is_new = path in self.tab._new_items
        item_output_dir = os.path.dirname(path)
        # Check if item has metadata
        has_metadata = item.get('has_metadata', False)
        job_prefix = item.get('job_prefix')

        try:
            # Use unified ThumbnailWidget with item_type parameter
            thumbnail = ThumbnailWidget(
                path,
                item_type=file_type,  # 'image' or 'model'
                parent=container,
                output_dir=item_output_dir,
                editable=is_editable,
                is_new=is_new,
                gallery_tab=self.tab,
                has_metadata=has_metadata,
                job_prefix=job_prefix
            )
            thumbnail.clicked.connect(self.tab._on_thumbnail_clicked)
            thumbnail.deleted.connect(self.tab._on_item_deleted)
            thumbnail.viewed.connect(self.tab._on_item_viewed)
            thumbnail.selection_changed.connect(self.tab._on_selection_changed)

            # Set favorites manager for likes/groups functionality
            favorites_manager = getattr(self.tab, '_favorites_manager', None)
            if favorites_manager:
                thumbnail.set_favorites_manager(favorites_manager)
                # Connect like toggle signal
                thumbnail.like_toggled.connect(self._on_thumbnail_like_toggled)

            # Connect image-specific signals
            if file_type == 'image':
                thumbnail.fullscreen_requested.connect(
                    lambda img_path=path: self.tab._open_viewer(img_path, fullscreen=True)
                )
                thumbnail.copy_settings_requested.connect(self.tab._on_copy_settings_requested)

            return thumbnail
        except Exception as e:
            logging.error(f"[Gallery] Error creating thumbnail for {path}: {e}")
            return None

    def _on_thumbnail_like_toggled(self, path, is_liked):
        """Handle like toggle from a thumbnail.

        Args:
            path: Path of the item
            is_liked: New like state
        """
        # Show status message
        if hasattr(self.tab, 'show_status_message'):
            if is_liked:
                self.tab.show_status_message("♥ Added to Likes")
            else:
                self.tab.show_status_message("Removed from Likes")

    def _remove_stale_widgets(self, stale_paths):
        """Remove widgets for items that are no longer in the current scan.

        Handles both grid widgets and stacked view items.

        Args:
            stale_paths: Set of paths to remove
        """


        for path in stale_paths:
            widget = self.tab._widget_cache.pop(path, None)
            if widget and isValid(widget):
                self.tab._flow_layout.removeWidget(widget)
                widget.deleteLater()

        # Also clean up section_items references
        if hasattr(self.tab, '_section_items'):
            for section_id in list(self.tab._section_items.keys()):
                paths = self.tab._section_items[section_id]
                self.tab._section_items[section_id] = [
                    p for p in paths if p not in stale_paths
                ]
                # Remove empty sections
                if not self.tab._section_items[section_id]:
                    del self.tab._section_items[section_id]

    def _insert_new_items_incrementally(self, sorted_items, new_items):
        """Insert new items at their correct positions without rebuilding the layout.

        This is much faster than recreating all widgets and avoids visual flash.

        Args:
            sorted_items: Full list of items in sorted order
            new_items: List of only the new items to add
        """
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

                thumbnail = self._create_thumbnail_widget(item, container, is_editable)
                if thumbnail is None:
                    continue

                # Add to cache and insert at correct layout position
                self.tab._widget_cache[path] = thumbnail
                self.tab._flow_layout.insertWidget(target_index, thumbnail)

            # Update status count
            self.update_status_count(sorted_items)

            # Update ordered list for shift-select range selection
            self.tab._visible_items_ordered = [item['path'] for item in sorted_items]

        finally:
            container.setUpdatesEnabled(True)

        # Animate newly added items with staggered fade-in
        new_widgets = [self.tab._widget_cache[item['path']] for item in new_items
                       if item['path'] in self.tab._widget_cache]
        if new_widgets:
            self._animate_new_items(new_widgets)

        # Trigger lazy loading for the new visible items
        QTimer.singleShot(150, self.tab._load_visible_thumbnails)

    def reorder_widgets(self, items):
        """Reorder existing widgets without recreating them.

        This is much faster than display_items when just changing sort order.
        Only works for grid (flat) view mode - stacked mode needs full rebuild.

        Args:
            items: List of item dicts (already sorted)
        """


        container = self.tab.ui.galleryThumbnailContainer
        container.setUpdatesEnabled(False)

        try:
            # Build the new order from cache
            ordered_widgets = []
            for item_dict in items:
                path = item_dict['path']
                if path in self.tab._widget_cache:
                    widget = self.tab._widget_cache[path]
                    if isValid(widget):
                        ordered_widgets.append(widget)

            # Only proceed if we have all widgets
            if len(ordered_widgets) != len(items):
                # Mismatch - fall back to full rebuild
                container.setUpdatesEnabled(True)
                logging.info(f"[Gallery] Reorder mismatch: {len(ordered_widgets)} widgets vs {len(items)} items, doing full rebuild")
                self.display_items(items, self.tab._view_mode)
                return

            # Remove all widgets from layout (but don't delete them)
            while self.tab._flow_layout.count():
                self.tab._flow_layout.takeAt(0)

            # Add widgets back in sorted order
            for widget in ordered_widgets:
                self.tab._flow_layout.addWidget(widget)

        finally:
            container.setUpdatesEnabled(True)

        # Force layout recalculation - need multiple calls to ensure Qt processes the change
        self.tab._flow_layout.invalidate()
        self.tab._flow_layout.activate()
        container.updateGeometry()
        container.update()

        # Update status count (items haven't changed, just order)
        self.update_status_count(items)

        # Update ordered list for shift-select range selection
        self.tab._visible_items_ordered = [item['path'] for item in items]

        # Note: We don't reload thumbnails here - they're already loaded in the widgets
        logging.info(f"[Gallery] Fast reorder: {len(items)} items repositioned")

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
        self.tab._widget_batch_size = 20  # Create 20 widgets per batch for faster loading
        self.tab._is_editable_cache = self.tab._is_own_gallery()
        self.create_widget_batch()

    def create_widget_batch(self):
        """Create a batch of widgets, then schedule the next batch."""
        container = self.tab.ui.galleryThumbnailContainer

        if not hasattr(self.tab, '_pending_items') or self.tab._widget_create_index >= len(self.tab._pending_items):
            # All widgets created - re-enable updates and trigger layout
            container.setUpdatesEnabled(True)

            # Trigger initial lazy load after layout settles
            QTimer.singleShot(150, self.tab._load_visible_thumbnails)
            return

        end_index = min(self.tab._widget_create_index + self.tab._widget_batch_size, len(self.tab._pending_items))

        for i in range(self.tab._widget_create_index, end_index):
            pending_item = self.tab._pending_items[i]
            # Support formats: (path, type), (path, type, has_metadata), (path, type, has_metadata, job_prefix)
            if len(pending_item) == 4:
                path, file_type, has_metadata, job_prefix = pending_item
            elif len(pending_item) == 3:
                path, file_type, has_metadata = pending_item
                job_prefix = None
            else:
                path, file_type = pending_item
                has_metadata = False
                job_prefix = None

            # Convert tuple to item dict for _create_thumbnail_widget
            item = {
                'path': path,
                'type': file_type,
                'has_metadata': has_metadata,
                'job_prefix': job_prefix
            }

            thumbnail = self._create_thumbnail_widget(item, container, self.tab._is_editable_cache)
            if thumbnail is None:
                continue

            self.tab._widget_cache[path] = thumbnail
            self.tab._flow_layout.addWidget(thumbnail)

        self.tab._widget_create_index = end_index

        # Schedule next batch with minimal delay
        QTimer.singleShot(1, self.create_widget_batch)

    def load_visible_thumbnails(self):
        """Load thumbnails for widgets that are currently visible in the viewport.

        Loads in batches to avoid overwhelming the thread pool.
        Uses a guard flag to prevent parallel loading loops from rapid
        scroll/resize events.
        """


        # Prevent parallel loading batches - if already loading, defer
        if getattr(self.tab, '_thumbnail_loading_in_progress', False):
            self.tab._thumbnail_load_pending = True
            return

        if not hasattr(self.tab, '_widget_cache') or not self.tab._widget_cache:
            return

        scroll_area = self.tab.ui.galleryScrollArea
        viewport = scroll_area.viewport()
        viewport_rect = viewport.rect()

        # Retry if viewport hasn't been laid out yet (height 0)
        if viewport_rect.height() <= 0:
            QTimer.singleShot(150, self.load_visible_thumbnails)
            return

        # Convert viewport rect to container coordinates
        visible_top = scroll_area.verticalScrollBar().value()
        visible_bottom = visible_top + viewport_rect.height()
        visible_left = scroll_area.horizontalScrollBar().value()
        visible_right = visible_left + viewport_rect.width()

        # Add buffer zone for smoother scrolling
        buffer = 300
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

            # Widgets that haven't been laid out yet (zero geometry) are
            # assumed visible so they load immediately rather than staying blank
            if widget_rect.width() == 0 and widget_rect.height() == 0:
                widgets_to_load.append(widget)
                continue

            if (widget_rect.bottom() >= visible_top and
                widget_rect.top() <= visible_bottom and
                widget_rect.right() >= visible_left and
                widget_rect.left() <= visible_right):
                widgets_to_load.append(widget)

        if not widgets_to_load:
            return

        # Set guard flag and store batch state
        self.tab._thumbnail_loading_in_progress = True
        self.tab._pending_thumbnail_loads = widgets_to_load
        self.tab._thumbnail_load_index = 0
        self.load_thumbnail_batch()

    def load_thumbnail_batch(self):
        """Load thumbnails in small batches for better performance."""


        if not hasattr(self.tab, '_pending_thumbnail_loads'):
            self._finish_thumbnail_loading()
            return

        pending = self.tab._pending_thumbnail_loads
        start_idx = self.tab._thumbnail_load_index

        if start_idx >= len(pending):
            self._finish_thumbnail_loading()
            return

        # Load 4 thumbnails per batch for faster loading while keeping UI responsive
        batch_size = 4
        end_idx = min(start_idx + batch_size, len(pending))

        for i in range(start_idx, end_idx):
            widget = pending[i]
            if isValid(widget):
                widget.load_thumbnail_if_needed()

        self.tab._thumbnail_load_index = end_idx

        # Schedule next batch with minimal delay
        if end_idx < len(pending):
            QTimer.singleShot(5, self.load_thumbnail_batch)
        else:
            self._finish_thumbnail_loading()

    def _finish_thumbnail_loading(self):
        """Clear loading guard and retry if a load was deferred during loading."""
        self.tab._thumbnail_loading_in_progress = False
        if getattr(self.tab, '_thumbnail_load_pending', False):
            self.tab._thumbnail_load_pending = False
            QTimer.singleShot(50, self.load_visible_thumbnails)

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
