"""
Gallery Operations Manager.

Handles batch operations on gallery items:
- Delete selected items
- Publish selected items to AYON
- Copy settings from images
- Item cleanup after operations
"""

import os
from typing import Dict, Any

from .base_manager import BaseGalleryManager


class OperationsManager(BaseGalleryManager):
    """Manages operations on gallery items."""

    def __init__(self, tab):
        """
        Initialize the operations manager.

        Args:
            tab: Reference to the GalleryTab
        """
        super().__init__(tab)

    def delete_selected(self):
        """Delete all selected items with confirmation."""
        from dialog_helpers import confirm_action, show_warning

        if not self.tab._selected_items:
            return

        count = len(self.tab._selected_items)

        if confirm_action(
            "Delete Selected Items",
            f"Are you sure you want to delete {count} selected item(s)?\n\nThis will permanently delete the files from disk.",
            parent=self.tab.main_window
        ):
            success_count = 0
            failed_items = []

            # Show status with spinner
            from ui_components import StatusColors
            self.tab.update_status_with_spinner(
                f"Gallery: Deleting {count} item(s)...",
                StatusColors.INFO
            )

            # Make a copy of the set since we'll be modifying it
            items_to_delete = list(self.tab._selected_items)

            # Track which stacks need updating after deletion
            stacks_to_update = set()

            for item_path in items_to_delete:
                try:
                    os.remove(item_path)
                    success_count += 1

                    # Remove widget from layout (for non-stacked items)
                    if item_path in self.tab._widget_cache:
                        widget = self.tab._widget_cache[item_path]
                        self.tab._flow_layout.removeWidget(widget)
                        widget.deleteLater()
                        del self.tab._widget_cache[item_path]
                    else:
                        # Item might be in a stacked view - find which stack contains it
                        stack_id = self._find_stack_containing_item(item_path)
                        if stack_id:
                            stacks_to_update.add(stack_id)

                    # Clean up caches via tab's method
                    self._on_item_deleted(item_path)
                except FileNotFoundError:
                    self.tab.log(f"[Gallery] File not found: {item_path}")
                    failed_items.append(os.path.basename(item_path))
                except Exception as e:
                    self.tab.log(f"[Gallery] Error deleting {item_path}: {e}")
                    failed_items.append(f"{os.path.basename(item_path)}: {e}")

            # Update or remove stacks that had items deleted
            self._update_stacks_after_deletion(stacks_to_update)

            # Clear selection (items already removed from widget cache)
            self.tab._selected_items.clear()
            self.tab._selection_manager._update_toolbar()

            # Show result with status feedback
            if success_count == count:
                self.tab.update_status_with_spinner(
                    f"Gallery: Deleted {success_count} item(s)",
                    StatusColors.SUCCESS,
                    start=False
                )
                self.show_status(f"Deleted {success_count} item(s)", "success")
                self.tab.log(f"[Gallery] Deleted {success_count} item(s)")
            else:
                self.tab.update_status_with_spinner(
                    f"Gallery: Deleted {success_count}/{count} (partial)",
                    StatusColors.WARNING,
                    start=False
                )
                show_warning(
                    "Partial Delete",
                    f"Deleted {success_count} of {count} items.\n\nFailed:\n" + "\n".join(failed_items[:5]),
                    parent=self.tab.main_window
                )

    def _find_stack_containing_item(self, item_path):
        """Find the stack_id that contains the given item path.

        Args:
            item_path: Path to the item

        Returns:
            stack_id if found, None otherwise
        """
        if not hasattr(self.tab, '_manager') or not hasattr(self.tab._manager, '_stack_widgets'):
            return None

        for stack_id, stack_widget in self.tab._manager._stack_widgets.items():
            if hasattr(stack_widget, '_items'):
                for item in stack_widget._items:
                    if item.get('path') == item_path:
                        return stack_id
        return None

    def _update_stacks_after_deletion(self, stack_ids):
        """Update or remove stacks after items have been deleted.

        Args:
            stack_ids: Set of stack_ids that need updating
        """
        from shiboken6 import isValid

        if not stack_ids:
            return

        if not hasattr(self.tab, '_manager') or not hasattr(self.tab._manager, '_stack_widgets'):
            return

        stacks_to_remove = []

        for stack_id in stack_ids:
            if stack_id not in self.tab._manager._stack_widgets:
                continue

            stack_widget = self.tab._manager._stack_widgets[stack_id]
            if not isValid(stack_widget):
                stacks_to_remove.append(stack_id)
                continue

            # Filter out deleted items from the stack
            if hasattr(stack_widget, '_items'):
                # Keep only items that still exist on disk
                remaining_items = [item for item in stack_widget._items if os.path.exists(item.get('path', ''))]

                if len(remaining_items) == 0:
                    # Stack is now empty - remove it
                    stacks_to_remove.append(stack_id)
                elif len(remaining_items) == 1:
                    # Only one item left - convert to regular thumbnail
                    stacks_to_remove.append(stack_id)
                    # The single item will be shown on next refresh
                else:
                    # Update the stack with remaining items
                    stack_widget.update_items(remaining_items)
                    # Clear selection state since items were deleted
                    if hasattr(stack_widget, 'set_selected'):
                        stack_widget.set_selected(False)

        # Remove empty/single-item stacks
        for stack_id in stacks_to_remove:
            if stack_id in self.tab._manager._stack_widgets:
                stack_widget = self.tab._manager._stack_widgets[stack_id]
                if isValid(stack_widget):
                    # Collapse if expanded
                    if hasattr(stack_widget, 'is_expanded') and stack_widget.is_expanded():
                        stack_widget.collapse(animated=False)
                    self.tab._flow_layout.removeWidget(stack_widget)
                    stack_widget.deleteLater()
                del self.tab._manager._stack_widgets[stack_id]

            # Also clean up section_items tracking
            if hasattr(self.tab, '_section_items') and stack_id in self.tab._section_items:
                del self.tab._section_items[stack_id]

    def _on_item_deleted(self, item_path):
        """Handle item deletion - clean up all caches."""
        # Remove from cached items
        if self.tab._cached_items:
            self.tab._cached_items = [item for item in self.tab._cached_items if item['path'] != item_path]

        # Remove from known images
        if item_path in self.tab._known_items:
            self.tab._known_items.discard(item_path)

        # Remove from new items
        self.tab._new_items.discard(item_path)

        # Update status count
        if self.tab._cached_items:
            self.tab._manager.update_status_count(self.tab._cached_items)

        self.tab.log(f"[Gallery] Item deleted: {os.path.basename(item_path)}")

    def publish_selected(self):
        """Publish selected items to AYON."""
        from dialog_helpers import confirm_action, show_warning, show_error
        from ui_components import Worker
        from PySide6.QtCore import QThreadPool

        if not self.tab._selected_items:
            return

        # Check if we're in own gallery (can only publish own items)
        if not self.tab._is_own_gallery():
            show_warning(
                "Cannot Publish",
                "You can only publish items from your own gallery.\n\n"
                "Switch to your own gallery to publish items.",
                parent=self.tab.main_window
            )
            return

        count = len(self.tab._selected_items)

        # Confirm publish
        if not confirm_action(
            "Publish Selected Items",
            f"Publish {count} selected item(s) to AYON?",
            parent=self.tab.main_window
        ):
            return

        # Show status with spinner
        from ui_components import StatusColors
        self.tab.update_status_with_spinner(
            f"Gallery: Publishing {count} item(s)...",
            StatusColors.INFO
        )

        # Get list of paths to publish
        selected_paths = list(self.tab._selected_items)

        # Start publish worker
        def publish_batch(paths):
            """Publish multiple items in a batch."""
            from comfyui.ayon_publisher import ComfyUIAYONPublisher

            results = []
            publisher = ComfyUIAYONPublisher(self.tab.app_state)

            for path in paths:
                try:
                    success = publisher.publish_single_file(path)
                    results.append({'path': path, 'success': success, 'error': None})
                except Exception as e:
                    results.append({'path': path, 'success': False, 'error': str(e)})

            return results

        self._publish_worker = Worker(publish_batch, selected_paths)
        self._publish_worker.signals.result.connect(self._on_publish_complete)
        self._publish_worker.signals.error.connect(
            lambda msg, tb: show_error("Publish Error", msg, parent=self.tab.main_window)
        )
        QThreadPool.globalInstance().start(self._publish_worker)

        self.tab.log(f"[Gallery] Publishing {count} items...")

    def _on_publish_complete(self, results):
        """Handle publish batch completion."""
        from dialog_helpers import show_warning
        from ui_components import StatusColors

        success_count = sum(1 for r in results if r['success'])
        failed_items = [os.path.basename(r['path']) for r in results if not r['success']]

        if success_count == len(results):
            # Stop spinner and show success
            self.tab.update_status_with_spinner(
                f"Gallery: Published {success_count} item(s) to AYON",
                StatusColors.SUCCESS,
                start=False
            )
            self.show_status(f"Published {success_count} item(s) to AYON", "success")
            self.tab.log(f"[Gallery] Published {success_count} items to AYON")
        else:
            # Stop spinner and show warning
            self.tab.update_status_with_spinner(
                f"Gallery: Published {success_count}/{len(results)} (partial)",
                StatusColors.WARNING,
                start=False
            )
            show_warning(
                "Partial Publish",
                f"Published {success_count} of {len(results)} items.\n\nFailed:\n" + "\n".join(failed_items[:5]),
                parent=self.tab.main_window
            )

    def copy_settings_to_comfyui(self, metadata: Dict[str, Any]):
        """
        Copy settings from an image's metadata to the ComfyUI tab.

        Args:
            metadata: Image metadata dictionary
        """
        comfyui_tab = self.tab.main_window.get_tab("comfyui")
        if comfyui_tab:
            comfyui_tab.apply_settings_from_metadata(metadata)
        else:
            self.tab.log("Could not find ComfyUI tab to apply settings")

    def on_item_viewed(self, item_path):
        """Handle item viewed - remove from new items set."""
        self.tab._new_items.discard(item_path)

    def compare_selected(self):
        """Compare two selected items side-by-side.

        Shows a dialog comparing metadata and parameters between two items.
        Requires exactly 2 items to be selected.
        """
        from dialog_helpers import show_warning

        if len(self.tab._selected_items) != 2:
            show_warning(
                "Compare Items",
                "Please select exactly 2 items to compare.\n\n"
                f"Currently selected: {len(self.tab._selected_items)} item(s)",
                parent=self.tab.main_window
            )
            return

        # Get the two selected items
        selected_list = sorted(list(self.tab._selected_items))
        item1_path = selected_list[0]
        item2_path = selected_list[1]

        # Show comparison dialog
        try:
            from comparison_dialog import ComparisonDialog
            dialog = ComparisonDialog(
                item1_path=item1_path,
                item2_path=item2_path,
                parent=self.tab.main_window
            )
            dialog.exec()
        except Exception as e:
            self.tab.log(f"[Gallery] Error opening comparison dialog: {e}")
            show_warning(
                "Compare Error",
                f"Could not open comparison dialog:\n{e}",
                parent=self.tab.main_window
            )
