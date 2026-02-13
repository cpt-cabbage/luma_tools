"""
Gallery Selection Manager.

Handles multi-select functionality including:
- Single click selection
- Ctrl+click toggle selection
- Shift+click range selection
- Box selection (rubber band)
- Selection toolbar management
- Keyboard shortcuts (Ctrl+A, Escape)
"""

from PySide6 import QtCore
from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QRubberBand

from .base_manager import BaseGalleryManager


class BoxSelectionEventFilter(QtCore.QObject):
    """Event filter for box selection (rubber band) on scroll area viewport."""

    def __init__(self, selection_manager):
        super().__init__()
        self.selection_manager = selection_manager
        self._mouse_moved = False

    def eventFilter(self, watched, event):
        """Handle mouse events for rubber band selection."""
        from PySide6.QtCore import QEvent

        tab = self.selection_manager.tab
        if watched == tab.ui.galleryScrollArea.viewport():
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    # Map from viewport coords to container coords
                    container_pos = tab.ui.galleryThumbnailContainer.mapFrom(
                        tab.ui.galleryScrollArea.viewport(),
                        event.pos()
                    )
                    # Check if clicking on empty space (not on a thumbnail)
                    child = tab.ui.galleryThumbnailContainer.childAt(container_pos)
                    if child is None or child == tab.ui.galleryThumbnailContainer:
                        # Track that we haven't moved yet
                        self._mouse_moved = False
                        # Clear selection unless Ctrl is held (for simple clicks)
                        if not (event.modifiers() & Qt.ControlModifier):
                            self.selection_manager.clear_selection()
                        # Prepare for potential rubber band selection
                        self.selection_manager._rubber_band_origin = event.pos()
                        self.selection_manager._rubber_band_active = True
                        return True

            elif event.type() == QEvent.MouseMove:
                if self.selection_manager._rubber_band_active:
                    # Mark that mouse has moved (not just a click)
                    if not self._mouse_moved:
                        self._mouse_moved = True
                        # Now create and show rubber band since we're dragging
                        if not self.selection_manager._rubber_band:
                            self.selection_manager._rubber_band = QRubberBand(
                                QRubberBand.Rectangle,
                                tab.ui.galleryScrollArea.viewport()
                            )
                        self.selection_manager._rubber_band.setGeometry(
                            QRect(self.selection_manager._rubber_band_origin, event.pos()).normalized()
                        )
                        self.selection_manager._rubber_band.show()
                    else:
                        # Update rubber band geometry
                        self.selection_manager._rubber_band.setGeometry(
                            QRect(self.selection_manager._rubber_band_origin, event.pos()).normalized()
                        )
                    return True

            elif event.type() == QEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton and self.selection_manager._rubber_band_active:
                    # Only process selection if mouse was moved (dragged)
                    if self._mouse_moved:
                        self.selection_manager.process_rubber_band_selection()
                    # Hide rubber band
                    if self.selection_manager._rubber_band:
                        self.selection_manager._rubber_band.hide()
                    self.selection_manager._rubber_band_active = False
                    self._mouse_moved = False
                    return True

        return super().eventFilter(watched, event)


class SelectionManager(BaseGalleryManager):
    """Manages multi-select functionality for the gallery."""

    def __init__(self, tab):
        """
        Initialize the selection manager.

        Args:
            tab: Reference to the GalleryTab
        """
        super().__init__(tab)

        # Selection state (stored on tab for backwards compatibility)
        self.tab._selected_items = set()
        self.tab._selection_toolbar = None
        self.tab._last_selected_path = None
        self.tab._visible_items_ordered = []

        # Box selection state
        self._rubber_band = None
        self._rubber_band_origin = None
        self._rubber_band_active = False

        # Track which widgets currently have checkmarks visible (for targeted updates)
        self._widgets_with_checkmarks_shown = set()

        # Create and install event filter
        self._box_filter = BoxSelectionEventFilter(self)
        self.tab.ui.galleryScrollArea.viewport().installEventFilter(self._box_filter)

    def handle_key_press(self, event):
        """
        Handle keyboard shortcuts for selection.

        Returns True if event was handled, False otherwise.
        """
        # Ctrl+A: Select all items
        if event.key() == Qt.Key_A and event.modifiers() == Qt.ControlModifier:
            self.select_all()
            return True

        # Escape: Clear selection
        if event.key() == Qt.Key_Escape:
            if self.tab._selected_items:
                self.clear_selection()
                return True

        # L: Toggle like on selected items
        if event.key() == Qt.Key_L:
            self._toggle_like_selected()
            return True

        # G: Open group menu for selected items
        if event.key() == Qt.Key_G:
            if event.modifiers() == Qt.ControlModifier:
                # Ctrl+G: Create new group
                self._create_new_group()
            else:
                # G: Show group menu
                self._show_group_menu()
            return True

        # Number keys 1-9: Quick add to group by index
        if Qt.Key_1 <= event.key() <= Qt.Key_9:
            group_index = event.key() - Qt.Key_1
            if event.modifiers() == Qt.ShiftModifier:
                self._remove_from_group_by_index(group_index)
            else:
                self._add_to_group_by_index(group_index)
            return True

        # C: Compare two selected items
        if event.key() == Qt.Key_C and not event.modifiers():
            if len(self.tab._selected_items) == 2:
                self.tab._operations_manager.compare_selected()
                return True

        return False

    def _toggle_like_selected(self):
        """Toggle like status for all selected items."""
        favorites_manager = getattr(self.tab, '_favorites_manager', None)
        if not favorites_manager or not self.tab._selected_items:
            return

        paths = list(self.tab._selected_items)
        # Check if any are liked - if all liked, unlike all; otherwise like all
        all_liked = all(favorites_manager.is_liked(p) for p in paths)

        if all_liked:
            favorites_manager.unlike_items(paths)
            msg = f"Unliked {len(paths)} items"
        else:
            favorites_manager.like_items(paths)
            msg = f"Liked {len(paths)} items"

        # Only refresh the affected widgets, not all widgets
        self.tab._refresh_favorites_state_for_paths(paths)
        if hasattr(self.tab, 'show_status_message'):
            self.tab.show_status_message(msg)

    def _show_group_menu(self):
        """Show a popup menu to add selected items to a group."""
        favorites_manager = getattr(self.tab, '_favorites_manager', None)
        if not favorites_manager or not self.tab._selected_items:
            return

        from PySide6.QtWidgets import QMenu, QCursor

        menu = QMenu(self.tab)
        groups = favorites_manager.get_groups()

        for group in groups:
            action = menu.addAction(f"● {group.name}")
            action.triggered.connect(
                lambda checked, gid=group.group_id: self._add_selected_to_group(gid)
            )

        if groups:
            menu.addSeparator()

        new_action = menu.addAction("+ New Group...")
        new_action.triggered.connect(self._create_new_group)

        menu.exec_(QCursor.pos())

    def _create_new_group(self):
        """Create a new group and add selected items to it."""
        favorites_manager = getattr(self.tab, '_favorites_manager', None)
        if not favorites_manager:
            return

        from dialogs import GroupEditorDialog
        dialog = GroupEditorDialog(parent=self.tab)
        if dialog.exec_():
            name, color = dialog.get_result()
            if name:
                group_id = favorites_manager.create_group(name, color)
                if self.tab._selected_items:
                    paths = list(self.tab._selected_items)
                    favorites_manager.add_items_to_group(paths, group_id)
                    # Only refresh the affected widgets, not all widgets
                    self.tab._refresh_favorites_state_for_paths(paths)
                    if hasattr(self.tab, 'show_status_message'):
                        self.tab.show_status_message(f"Created '{name}' with {len(paths)} items")

    def _add_selected_to_group(self, group_id):
        """Add all selected items to a group."""
        favorites_manager = getattr(self.tab, '_favorites_manager', None)
        if not favorites_manager or not self.tab._selected_items:
            return

        paths = list(self.tab._selected_items)
        favorites_manager.add_items_to_group(paths, group_id)
        group = favorites_manager.get_group(group_id)
        # Only refresh the affected widgets, not all widgets
        self.tab._refresh_favorites_state_for_paths(paths)
        if group and hasattr(self.tab, 'show_status_message'):
            self.tab.show_status_message(f"Added {len(paths)} items to {group.name}")

    def _add_to_group_by_index(self, index):
        """Add selected items to group by its index (0-8 for keys 1-9)."""
        favorites_manager = getattr(self.tab, '_favorites_manager', None)
        if not favorites_manager or not self.tab._selected_items:
            return

        groups = favorites_manager.get_groups()
        if index < len(groups):
            self._add_selected_to_group(groups[index].group_id)

    def _remove_from_group_by_index(self, index):
        """Remove selected items from group by its index (0-8 for keys 1-9)."""
        favorites_manager = getattr(self.tab, '_favorites_manager', None)
        if not favorites_manager or not self.tab._selected_items:
            return

        groups = favorites_manager.get_groups()
        if index < len(groups):
            group = groups[index]
            paths = list(self.tab._selected_items)
            favorites_manager.remove_items_from_group(paths, group.group_id)
            # Only refresh the affected widgets, not all widgets
            self.tab._refresh_favorites_state_for_paths(paths)
            if hasattr(self.tab, 'show_status_message'):
                self.tab.show_status_message(f"Removed {len(paths)} items from {group.name}")

    def select_all(self):
        """Select all items in the gallery."""
        if not hasattr(self.tab, '_widget_cache'):
            return

        # Use thread-safe copy for iteration
        for path, widget in self.get_widget_cache_copy().items():
            if hasattr(widget, 'set_selected'):
                widget.set_selected(True)

        count = len(self.tab._selected_items)
        self.tab.log(f"[Gallery] Selected all {count} items")
        if hasattr(self.tab, 'show_status_message'):
            self.tab.show_status_message(f"Selected all {count} items")

    def select_single(self, widget):
        """
        Select a single widget, clearing any previous selection.

        Args:
            widget: The widget to select
        """
        # Clear existing selection first
        self.clear_selection(show_status=False)

        # Select the new widget
        if hasattr(widget, 'set_selected'):
            widget.set_selected(True)
            # The selection state is tracked via widget callbacks

    def clear_selection(self, show_status=True):
        """Clear all selected items.

        Args:
            show_status: Whether to show status message (default True)
        """
        had_selection = len(self.tab._selected_items) > 0

        # Snapshot and clear selection state first to prevent callbacks from
        # re-adding items during iteration (set_selected triggers _on_selection_changed)
        selected_paths = list(self.tab._selected_items)
        self.tab._selected_items.clear()

        # Update all previously selected widgets
        for path in selected_paths:
            widget = self.get_cached_widget(path)
            if widget:
                widget.set_selected(False)

        # Also clear stack selections and their expanded widgets
        if hasattr(self.tab, '_manager') and hasattr(self.tab._manager, '_stack_widgets'):
            for stack in self.tab._manager._stack_widgets.values():
                # Clear collapsed stack selection
                if hasattr(stack, 'set_selected') and stack.is_selected():
                    stack.set_selected(False)
                # Clear expanded widgets inside the stack
                if hasattr(stack, '_expanded_widgets') and stack._expanded_widgets:
                    for widget in stack._expanded_widgets:
                        if hasattr(widget, 'set_selected') and widget.is_selected():
                            widget.set_selected(False)

        self._update_toolbar()

    def _on_selection_changed(self, image_path, is_selected):
        """Handle thumbnail selection state change."""
        if is_selected:
            self.tab._selected_items.add(image_path)
            self.tab._last_selected_path = image_path
        else:
            self.tab._selected_items.discard(image_path)

        self._update_toolbar()
        self._update_checkmark_visibility()

    def _on_shift_click(self, clicked_path):
        """Handle shift+click for range selection.

        Builds visual order from the actual flow layout to properly handle:
        - Collapsed stacks (treated as single items)
        - Expanded stacks (individual items are selectable)
        - Mixed views with both stacked and non-stacked items
        """
        from small_widgets import StackedThumbnailWidget

        if not self.tab._last_selected_path:
            # No previous selection, just select this item
            self._select_item_by_path(clicked_path)
            return

        # Build visual order from flow layout
        visual_order = []  # List of (path_or_id, widget, is_stack) tuples

        if hasattr(self.tab, '_flow_layout'):
            # Snapshot layout widgets to avoid issues if layout changes during iteration
            layout = self.tab._flow_layout
            layout_count = layout.count()
            for i in range(layout_count):
                item = layout.itemAt(i)
                if not item:
                    continue
                widget = item.widget()
                if not widget or not widget.isVisible():
                    continue

                if isinstance(widget, StackedThumbnailWidget):
                    if widget._is_expanded:
                        # Skip the collapsed stack widget itself when expanded
                        # (expanded items are shown as separate widgets)
                        continue
                    else:
                        # Collapsed stack - use top item path as identifier
                        if widget._top_item:
                            visual_order.append((widget._top_item['path'], widget, True))
                elif hasattr(widget, 'image_path'):
                    # Regular image thumbnail
                    visual_order.append((widget.image_path, widget, False))
                elif hasattr(widget, 'model_path'):
                    # GLB/3D model thumbnail
                    visual_order.append((widget.model_path, widget, False))

        if not visual_order:
            # Fallback to old behavior if flow layout unavailable
            self._select_item_by_path(clicked_path)
            return

        # Find indices of last selected and clicked items
        last_index = -1
        current_index = -1

        for idx, (path, widget, is_stack) in enumerate(visual_order):
            if path == self.tab._last_selected_path:
                last_index = idx
            if path == clicked_path:
                current_index = idx

            # Also check if paths are inside a collapsed stack
            if is_stack:
                stack_widget = widget
                for stack_item in stack_widget._items:
                    if last_index == -1 and stack_item['path'] == self.tab._last_selected_path:
                        last_index = idx
                    if current_index == -1 and stack_item['path'] == clicked_path:
                        current_index = idx

        if last_index == -1 or current_index == -1:
            # Path not found, just select the clicked item
            self._select_item_by_path(clicked_path)
            return

        # Select all items in the range
        start = min(last_index, current_index)
        end = max(last_index, current_index)

        for i in range(start, end + 1):
            path, widget, is_stack = visual_order[i]
            if is_stack:
                # Select entire collapsed stack
                if hasattr(widget, 'set_selected'):
                    widget.set_selected(True)
            else:
                # Select individual item
                if hasattr(widget, 'set_selected') and not widget.is_selected():
                    widget.set_selected(True)

        # Update last selected path to the clicked item for subsequent shift-clicks
        self.tab._last_selected_path = clicked_path

    def _select_item_by_path(self, path):
        """Select a single item by its path, checking both widget cache and stacks."""
        from small_widgets import StackedThumbnailWidget

        # Check widget cache first
        if path in self.tab._widget_cache:
            self.tab._widget_cache[path].set_selected(True)
            return

        # Check if it's in a collapsed stack
        if hasattr(self.tab, '_manager') and hasattr(self.tab._manager, '_stack_widgets'):
            for stack in self.tab._manager._stack_widgets.values():
                if isinstance(stack, StackedThumbnailWidget) and not stack._is_expanded:
                    for item in stack._items:
                        if item['path'] == path:
                            stack.set_selected(True)
                            return

    def process_rubber_band_selection(self):
        """Select all items that intersect with the rubber band."""
        if not self._rubber_band or not self._rubber_band_origin:
            return

        # Get rubber band geometry in viewport coords
        rubber_band_rect = self._rubber_band.geometry()

        # Map to container coords
        container_rect = QRect(
            self.tab.ui.galleryThumbnailContainer.mapFrom(
                self.tab.ui.galleryScrollArea.viewport(),
                rubber_band_rect.topLeft()
            ),
            self.tab.ui.galleryThumbnailContainer.mapFrom(
                self.tab.ui.galleryScrollArea.viewport(),
                rubber_band_rect.bottomRight()
            )
        )

        # Check each widget for intersection (thread-safe copy)
        for path, widget in self.get_widget_cache_copy().items():
            if widget.geometry().intersects(container_rect):
                if hasattr(widget, 'set_selected'):
                    widget.set_selected(True)

        # Also check stack widgets (in stacked view)
        if hasattr(self.tab, '_manager') and hasattr(self.tab._manager, '_stack_widgets'):
            for stack in self.tab._manager._stack_widgets.values():
                if stack.geometry().intersects(container_rect):
                    if hasattr(stack, 'is_expanded') and stack.is_expanded():
                        # Stack is expanded - select its expanded widgets
                        for widget in stack.get_expanded_widgets():
                            if widget.geometry().intersects(container_rect):
                                if hasattr(widget, 'set_selected'):
                                    widget.set_selected(True)
                    else:
                        # Stack is collapsed - select all items in the stack
                        if hasattr(stack, 'set_selected'):
                            stack.set_selected(True)

    def create_toolbar(self):
        """Create the floating selection toolbar."""
        from ui_components import GallerySelectionToolbar

        # Parent to scroll area viewport so toolbar stays in visible area
        viewport = self.tab.ui.galleryScrollArea.viewport()
        self.tab._selection_toolbar = GallerySelectionToolbar(viewport)

        # Standard multi-select actions
        self.tab._selection_toolbar.delete_selected.connect(self.tab._on_delete_selected)
        self.tab._selection_toolbar.publish_selected.connect(self.tab._on_publish_selected)
        self.tab._selection_toolbar.view_selected.connect(self.tab._on_view_selected)
        self.tab._selection_toolbar.clear_selection.connect(self.clear_selection)

        # ComfyUI cross-tab actions
        self.tab._selection_toolbar.use_in_comfyui.connect(self.tab._on_use_in_comfyui)
        self.tab._selection_toolbar.copy_prompt.connect(self.tab._on_copy_prompt)
        self.tab._selection_toolbar.compare_to_source.connect(self.tab._on_compare_to_source)
        self.tab._selection_toolbar.recreate_settings.connect(self.tab._on_recreate_settings)

        self.tab._selection_toolbar.hide()

        # Setup resize event to reposition toolbar when viewport resizes
        original_resize_event = viewport.resizeEvent

        def on_viewport_resize(event):
            if self.tab._selection_toolbar and self.tab._selection_toolbar.isVisible():
                self._position_toolbar()
            return original_resize_event(event)

        viewport.resizeEvent = on_viewport_resize

    def _position_toolbar(self):
        """Position the selection toolbar at the bottom center of the scroll area viewport."""
        if not self.tab._selection_toolbar:
            return

        viewport = self.tab.ui.galleryScrollArea.viewport()
        viewport_width = viewport.width()
        viewport_height = viewport.height()
        toolbar_size = self.tab._selection_toolbar.sizeHint()

        # Center horizontally, position at bottom with padding
        x = (viewport_width - toolbar_size.width()) // 2
        y = viewport_height - toolbar_size.height() - 20

        self.tab._selection_toolbar.move(x, y)
        self.tab._selection_toolbar.raise_()

    def _update_toolbar(self):
        """Show/hide and update the selection toolbar based on selection state."""
        count = len(self.tab._selected_items)

        # Show toolbar for 1 or more selected items (ComfyUI actions work with single selection too)
        if count >= 1:
            if not self.tab._selection_toolbar:
                self.create_toolbar()
            # Pass both count and selected paths for ComfyUI actions
            self.tab._selection_toolbar.update_count(
                count,
                selected_paths=list(self.tab._selected_items)
            )
            self._position_toolbar()
            self.tab._selection_toolbar.show()
            self.tab._selection_toolbar.raise_()
        else:
            if self.tab._selection_toolbar:
                self.tab._selection_toolbar.hide()

    def _update_checkmark_visibility(self):
        """Update checkmark visibility only for affected widgets (not all widgets).

        Performance optimization: Instead of iterating ALL widgets on every selection
        change, we track which widgets have checkmarks visible and only update those
        that need to change.
        """
        show_checkmarks = len(self.tab._selected_items) > 1
        current_selected = self.tab._selected_items

        if not show_checkmarks:
            # Hide all currently visible checkmarks
            for path in list(self._widgets_with_checkmarks_shown):
                widget = self.get_cached_widget(path)
                if widget and hasattr(widget, 'selection_indicator'):
                    widget.selection_indicator.hide()
            self._widgets_with_checkmarks_shown.clear()
        else:
            # Only update widgets that changed state
            # Hide checkmarks on items that were showing but are no longer selected
            to_hide = self._widgets_with_checkmarks_shown - current_selected
            for path in to_hide:
                widget = self.get_cached_widget(path)
                if widget and hasattr(widget, 'selection_indicator'):
                    widget.selection_indicator.hide()

            # Show checkmarks on newly selected items
            to_show = current_selected - self._widgets_with_checkmarks_shown
            for path in to_show:
                widget = self.get_cached_widget(path)
                if widget and hasattr(widget, 'selection_indicator'):
                    widget.selection_indicator.show()

            # Update tracking set
            self._widgets_with_checkmarks_shown = current_selected.copy()

    def get_selected(self) -> set:
        """Get the set of currently selected item paths.

        Returns:
            Set of paths that are currently selected
        """
        return self.tab._selected_items

    def _on_item_deleted(self, item_path):
        """Handle item deletion from selection perspective."""
        if item_path in self.tab._selected_items:
            self.tab._selected_items.discard(item_path)
            self._update_toolbar()
