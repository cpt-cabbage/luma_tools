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


class OperationsManager:
    """Manages operations on gallery items."""

    def __init__(self, tab):
        """
        Initialize the operations manager.

        Args:
            tab: Reference to the ComfyUIGalleryTab
        """
        self.tab = tab

    def delete_selected(self):
        """Delete all selected items with confirmation."""
        from PySide6.QtWidgets import QMessageBox, QApplication

        if not self.tab._selected_items:
            return

        count = len(self.tab._selected_items)

        # Get proper parent window for dialog
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and hasattr(widget, 'windowTitle'):
                parent_window = widget
                break

        reply = QMessageBox.question(
            parent_window,
            "Delete Selected Items",
            f"Are you sure you want to delete {count} selected item(s)?\n\nThis will permanently delete the files from disk.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
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

            for item_path in items_to_delete:
                try:
                    if os.path.exists(item_path):
                        os.remove(item_path)
                        success_count += 1

                        # Remove widget from layout
                        if item_path in self.tab._widget_cache:
                            widget = self.tab._widget_cache[item_path]
                            self.tab._flow_layout.removeWidget(widget)
                            widget.deleteLater()
                            del self.tab._widget_cache[item_path]

                        # Clean up caches via tab's method
                        self._on_item_deleted(item_path)
                    else:
                        self.tab.log(f"[Gallery] File not found: {item_path}")
                        failed_items.append(os.path.basename(item_path))
                except Exception as e:
                    self.tab.log(f"[Gallery] Error deleting {item_path}: {e}")
                    failed_items.append(f"{os.path.basename(item_path)}: {e}")

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
                self.tab.main_window.animator.show_success(f"Deleted {success_count} item(s)")
                self.tab.log(f"[Gallery] Deleted {success_count} item(s)")
            else:
                self.tab.update_status_with_spinner(
                    f"Gallery: Deleted {success_count}/{count} (partial)",
                    StatusColors.WARNING,
                    start=False
                )
                QMessageBox.warning(
                    parent_window,
                    "Partial Delete",
                    f"Deleted {success_count} of {count} items.\n\nFailed:\n" + "\n".join(failed_items[:5])
                )

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
        from PySide6.QtWidgets import QMessageBox
        from ui_components import Worker
        from PySide6.QtCore import QThreadPool

        if not self.tab._selected_items:
            return

        # Check if we're in own gallery (can only publish own items)
        if not self.tab._is_own_gallery():
            QMessageBox.warning(
                self.tab.main_window,
                "Cannot Publish",
                "You can only publish items from your own gallery.\n\n"
                "Switch to your own gallery to publish items."
            )
            return

        count = len(self.tab._selected_items)

        # Confirm publish
        reply = QMessageBox.question(
            self.tab.main_window,
            "Publish Selected Items",
            f"Publish {count} selected item(s) to AYON?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
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
            lambda msg, tb: QMessageBox.critical(self.tab.main_window, "Publish Error", msg)
        )
        QThreadPool.globalInstance().start(self._publish_worker)

        self.tab.log(f"[Gallery] Publishing {count} items...")

    def _on_publish_complete(self, results):
        """Handle publish batch completion."""
        from PySide6.QtWidgets import QMessageBox
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
            self.tab.main_window.animator.show_success(f"Published {success_count} item(s) to AYON")
            self.tab.log(f"[Gallery] Published {success_count} items to AYON")
        else:
            # Stop spinner and show warning
            self.tab.update_status_with_spinner(
                f"Gallery: Published {success_count}/{len(results)} (partial)",
                StatusColors.WARNING,
                start=False
            )
            QMessageBox.warning(
                self.tab.main_window,
                "Partial Publish",
                f"Published {success_count} of {len(results)} items.\n\nFailed:\n" + "\n".join(failed_items[:5])
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
