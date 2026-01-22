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

import os
from PySide6 import QtCore
from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QRubberBand


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
                            QRect(self.selection_manager._rubber_band_origin, event.pos())
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


class SelectionManager:
    """Manages multi-select functionality for the gallery."""

    def __init__(self, tab):
        """
        Initialize the selection manager.

        Args:
            tab: Reference to the ComfyUIGalleryTab
        """
        self.tab = tab

        # Selection state (stored on tab for backwards compatibility)
        self.tab._selected_items = set()
        self.tab._selection_toolbar = None
        self.tab._last_selected_path = None
        self.tab._visible_items_ordered = []

        # Box selection state
        self._rubber_band = None
        self._rubber_band_origin = None
        self._rubber_band_active = False

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

        return False

    def select_all(self):
        """Select all items in the gallery."""
        if not hasattr(self.tab, '_widget_cache'):
            return

        for path, widget in self.tab._widget_cache.items():
            if hasattr(widget, 'set_selected'):
                widget.set_selected(True)

        self.tab.log(f"[Gallery] Selected all {len(self.tab._selected_items)} items")

    def clear_selection(self):
        """Clear all selected items."""
        # Update all selected widgets
        for path in list(self.tab._selected_items):
            if path in self.tab._widget_cache:
                widget = self.tab._widget_cache[path]
                widget.set_selected(False)
        self.tab._selected_items.clear()
        self._update_toolbar()

    def on_selection_changed(self, image_path, is_selected):
        """Handle thumbnail selection state change."""
        if is_selected:
            self.tab._selected_items.add(image_path)
            self.tab._last_selected_path = image_path
        else:
            self.tab._selected_items.discard(image_path)

        self._update_toolbar()
        self._update_checkmark_visibility()

    def on_shift_click(self, clicked_path):
        """Handle shift+click for range selection."""
        if not self.tab._last_selected_path or not self.tab._visible_items_ordered:
            # No previous selection, just select this item
            if clicked_path in self.tab._widget_cache:
                self.tab._widget_cache[clicked_path].set_selected(True)
            return

        try:
            # Find indices of last selected and current clicked items
            last_index = self.tab._visible_items_ordered.index(self.tab._last_selected_path)
            current_index = self.tab._visible_items_ordered.index(clicked_path)

            # Select all items in the range
            start = min(last_index, current_index)
            end = max(last_index, current_index)

            for i in range(start, end + 1):
                item_path = self.tab._visible_items_ordered[i]
                if item_path in self.tab._widget_cache:
                    widget = self.tab._widget_cache[item_path]
                    if not widget.is_selected():
                        widget.set_selected(True)

        except ValueError:
            # Path not found in ordered list, just select the clicked item
            if clicked_path in self.tab._widget_cache:
                self.tab._widget_cache[clicked_path].set_selected(True)

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

        # Check each widget for intersection
        for path, widget in self.tab._widget_cache.items():
            if widget.geometry().intersects(container_rect):
                if hasattr(widget, 'set_selected'):
                    widget.set_selected(True)

    def create_toolbar(self):
        """Create the floating selection toolbar."""
        from ui_components import GallerySelectionToolbar

        # Parent to scroll area viewport so toolbar stays in visible area
        viewport = self.tab.ui.galleryScrollArea.viewport()
        self.tab._selection_toolbar = GallerySelectionToolbar(viewport)
        self.tab._selection_toolbar.delete_selected.connect(self.tab._on_delete_selected)
        self.tab._selection_toolbar.publish_selected.connect(self.tab._on_publish_selected)
        self.tab._selection_toolbar.view_selected.connect(self.tab._on_view_selected)
        self.tab._selection_toolbar.clear_selection.connect(self.clear_selection)
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
        # Only show toolbar for multi-select (2 or more items)
        if len(self.tab._selected_items) > 1:
            if not self.tab._selection_toolbar:
                self.create_toolbar()
            self.tab._selection_toolbar.update_count(len(self.tab._selected_items))
            self._position_toolbar()
            self.tab._selection_toolbar.show()
            self.tab._selection_toolbar.raise_()
        else:
            if self.tab._selection_toolbar:
                self.tab._selection_toolbar.hide()

    def _update_checkmark_visibility(self):
        """Update checkmark visibility for all selected items (show only if multiple selections)."""
        show_checkmarks = len(self.tab._selected_items) > 1
        for path in self.tab._selected_items:
            if path in self.tab._widget_cache:
                widget = self.tab._widget_cache[path]
                if hasattr(widget, 'selection_indicator'):
                    if show_checkmarks:
                        widget.selection_indicator.show()
                    else:
                        widget.selection_indicator.hide()

    def on_item_deleted(self, item_path):
        """Handle item deletion from selection perspective."""
        if item_path in self.tab._selected_items:
            self.tab._selected_items.discard(item_path)
            self._update_toolbar()
