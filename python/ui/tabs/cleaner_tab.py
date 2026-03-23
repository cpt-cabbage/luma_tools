"""
Cleaner tab module for Luma Tools.

Handles cleanup of shot files (renders, USD, HIP backups)
and gallery footprint management.
"""

import logging
from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem

from .base_tab import BaseTab, TabConfig
from core.utils import ByteSize

logger = logging.getLogger(__name__)


class CleanerTab(BaseTab):
    """Tab for cleaning up shot files and gallery outputs."""

    TAB_CONFIG = TabConfig(ui_file="cleaner.ui", tab_name="Cleaner", tab_id="cleaner")

    def connect_signals(self):
        """Connect cleaner tab signals."""
        # Existing shot cleanup signals
        self.ui.RescanCleanFiles.clicked.connect(self._on_rescan_clicked)
        self.ui.CleanFiles.clicked.connect(self._on_clean_files_clicked)

        # Gallery cleanup signals
        self.ui.GalleryScanButton.clicked.connect(self._on_gallery_scan)
        self.ui.GalleryCleanupButton.clicked.connect(self._on_gallery_cleanup)

        # Filter controls
        self.ui.GalleryStatsTree.itemChanged.connect(self._on_filter_changed)
        self.ui.GalleryAgeSlider.valueChanged.connect(self._on_age_filter_changed)

    def initialize(self):
        """Initialize cleaner tab."""
        # Shot cleanup init
        self.ui.progressBar.setValue(0)

        if self.app_state.lookdev_dir:
            self._setup_scanner()

        # Gallery cleanup init
        self._gallery_footprint = None
        self._selected_files = []
        self._updating_tree = False  # Flag to prevent recursive updates
        self._setup_gallery_tree()
        self._update_gallery_path_label()

    # =========================================================================
    # Shot Cleanup Methods (existing functionality)
    # =========================================================================

    def _setup_scanner(self):
        """Setup the directory scanner."""
        from services.scan_service import DirectoryScanner

        try:
            self.scanner = DirectoryScanner(self.app_state, self.ui, None)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Cleaner scanner setup failed (pre-existing API mismatch): {e}"
            )

    def _on_add_render_item(self, text):
        """Add item to renders list."""
        self.ui.RendersClean.addItem(text)

    def _on_add_usd_item(self, text):
        """Add item to USD list."""
        self.ui.USDSClean.addItem(text)

    def _on_set_hip_backup_label(self, text):
        """Set HIP backup label text."""
        self.ui.HIPBackupsLabel.setText(text)

    def _on_set_latest_render_label(self, text):
        """Set latest render label text."""
        self.ui.LatestRender.setText(text)

    def _on_rescan_clicked(self):
        """Rescan for files to clean."""
        self.run_scanner()

    def run_scanner(self, on_complete=None):
        """
        Scan directories for renders, USD, HIP files, and comps - runs on background thread.

        Args:
            on_complete: Optional callback to call when scanning completes
        """
        from ui_components import StatusColors

        if not hasattr(self, "scanner"):
            self._setup_scanner()

        if not hasattr(self, "scanner"):
            self.show_status("Scanner not available", "warning")
            return

        # Store callback for use in handlers
        self._scan_on_complete = on_complete

        # Clear UI elements
        self.ui.CleanFiles.setEnabled(False)
        self.ui.USDSClean.clear()
        self.ui.RendersClean.clear()

        # Show status bar progress
        self.update_status_with_spinner("Shot Cleaner: Scanning directories...", StatusColors.INFO)

        # Use base class worker helper
        self.start_worker(
            self.scanner.scan_all,
            on_result=self._on_scan_result,
            on_error=self._on_scan_error,
        )

    def _on_scan_result(self, result):
        """Handle scan completion."""
        from ui_components import StatusColors

        # Enable clean button
        self.ui.CleanFiles.setEnabled(True)

        # Select all items by default
        self._deselect_renders_in_comp(result.get("renders_in_comp", []))

        # Stop spinner and update status
        self.update_status_with_spinner(
            "Shot Cleaner: Scan complete", StatusColors.SUCCESS, start=False
        )

        # Call completion callback if provided
        if hasattr(self, "_scan_on_complete") and self._scan_on_complete:
            self._scan_on_complete()

    def _on_scan_error(self, error_msg, traceback_str=""):
        """Handle scan error."""
        from ui_components import StatusColors

        self.update_status_with_spinner(
            f"Shot Cleaner: Scan error - {error_msg}", StatusColors.ERROR, start=False
        )
        logger.error(f"Scanner error: {error_msg}")
        if traceback_str:
            logger.error(traceback_str)

        # Call completion callback even on error
        if hasattr(self, "_scan_on_complete") and self._scan_on_complete:
            self._scan_on_complete()

    def _deselect_renders_in_comp(self, renders_in_comp):
        """Deselect renders that are in use by comp files."""
        self.ui.RendersClean.selectAll()
        self.ui.USDSClean.selectAll()

        if renders_in_comp:
            for render_name in renders_in_comp:
                matching_items = self.ui.RendersClean.findItems(
                    render_name, Qt.MatchContains
                )
                for item in matching_items:
                    item.setSelected(False)

    def _on_clean_files_clicked(self):
        """Handle cleanup button click."""
        from ui_components import StatusColors
        from services.cleanup_service import (
            cleanup_renders,
            cleanup_usd,
            cleanup_hip_backups,
        )

        self.animate_button_click(self.ui.CleanFiles)

        # Cleanup renders
        if self.ui.CleanRender.isChecked():
            render_dirs = [
                item.text() for item in self.ui.RendersClean.selectedItems()
            ]
            if render_dirs:
                count = 0
                for dir_name in render_dirs:
                    count += 1
                    status_msg = f"Removing Renders: {self.app_state.lookdev_dir}\\img\\renders\\{dir_name}"
                    self.show_status(status_msg, "warning")
                    logger.info(status_msg)
                    self.ui.progressBar.setValue(int(count / len(render_dirs) * 100))

                cleanup_renders(self.app_state.lookdev_dir, render_dirs)

        # Cleanup USD
        if self.ui.CleanUSD.isChecked():
            usd_dirs = [item.text() for item in self.ui.USDSClean.selectedItems()]
            if usd_dirs:
                count = 0
                for dir_name in usd_dirs:
                    count += 1
                    self.ui.progressBar.setValue(int(count / len(usd_dirs) * 100))
                    status_msg = f"Removing USDs: {self.app_state.lookdev_dir}\\usd_files\\{dir_name}"
                    self.show_status(status_msg, "warning")
                    logger.info(status_msg)

                cleanup_usd(self.app_state.lookdev_dir, usd_dirs)

        # Cleanup HIP backups
        if self.ui.HIPBackups.isChecked():
            self.ui.progressBar.setValue(0)
            status_msg = (
                f"Removing Hip Backups Folder: {self.app_state.lookdev_dir}\\backup\\"
            )
            self.show_status(status_msg, "warning")
            cleanup_hip_backups(self.app_state.lookdev_dir)
            self.ui.progressBar.setValue(100)

        # Final status
        self.show_status("Cleanup complete", "success")

        # Rescan after cleanup
        self.run_scanner()

    # =========================================================================
    # Gallery Cleanup Methods (new functionality)
    # =========================================================================

    def _setup_gallery_tree(self):
        """Setup the gallery statistics tree widget."""
        tree = self.ui.GalleryStatsTree
        tree.setColumnWidth(0, 250)
        tree.setColumnWidth(1, 80)
        tree.setColumnWidth(2, 100)

    def _update_gallery_path_label(self):
        """Update the gallery path label."""
        from services.gallery_cleanup_service import get_gallery_output_path

        path = get_gallery_output_path()
        if path:
            self.ui.GalleryPathLabel.setText(f"Gallery: {path}")
            self.ui.GalleryScanButton.setEnabled(True)
        else:
            self.ui.GalleryPathLabel.setText("Gallery: Not configured")
            self.ui.GalleryScanButton.setEnabled(False)

    def _on_gallery_scan(self):
        """Scan gallery for footprint analysis.

        Only scans the current user's files to prevent users from
        accidentally deleting other users' data.
        """
        from services.gallery_cleanup_service import (
            get_gallery_output_path,
            scan_gallery_footprint,
        )
        from ui_components import StatusColors

        output_path = get_gallery_output_path()
        if not output_path:
            self.show_status("Gallery path not configured", "warning")
            return

        self.animate_button_click(self.ui.GalleryScanButton)
        self.ui.GalleryScanButton.setEnabled(False)
        self.ui.galleryProgressBar.setValue(0)

        # Get current user to filter scan results
        current_user = self.app_state.user if self.app_state.user else None

        self.update_status_with_spinner(
            f"Scanning gallery for {current_user or 'all users'}...",
            StatusColors.INFO
        )

        self.start_worker(
            scan_gallery_footprint,
            output_path,
            worker_kwargs={"user_filter": current_user},
            on_result=self._on_gallery_scan_complete,
            on_error=self._on_gallery_scan_error,
        )

    def _on_gallery_scan_complete(self, footprint):
        """Handle gallery scan completion."""
        from ui_components import StatusColors

        self._gallery_footprint = footprint
        self.ui.GalleryScanButton.setEnabled(True)
        self.ui.galleryProgressBar.setValue(100)
        self._update_gallery_stats_tree()
        self._update_gallery_totals()
        self._update_preview_size()
        self.update_status_with_spinner(
            f"Gallery scan complete: {footprint.total_files} files, {ByteSize(footprint.total_size)}",
            StatusColors.SUCCESS,
            start=False,
        )

    def _on_gallery_scan_error(self, error_msg, traceback_str=""):
        """Handle gallery scan error."""
        from ui_components import StatusColors
        self.ui.GalleryScanButton.setEnabled(True)
        self.ui.galleryProgressBar.setValue(0)
        self.update_status_with_spinner(
            f"Gallery scan failed: {error_msg}",
            StatusColors.ERROR,
            start=False,
        )

    def _update_gallery_stats_tree(self):
        """Update the gallery statistics tree view."""
        if not self._gallery_footprint:
            return

        self._updating_tree = True  # Prevent itemChanged from firing during updates
        tree = self.ui.GalleryStatsTree
        tree.clear()
        fp = self._gallery_footprint

        # By Output Type
        type_root = QTreeWidgetItem(tree, ["By Output Type", "", ""])
        type_root.setFlags(type_root.flags() | Qt.ItemIsUserCheckable)
        type_root.setCheckState(0, Qt.Checked)

        type_display_names = {
            "image": "Images",
            "video": "Videos",
            "3d": "3D Models",
            "audio": "Audio",
            "other": "Other",
        }

        for output_type in ["image", "video", "3d", "audio", "other"]:
            if output_type not in fp.by_type:
                continue
            data = fp.by_type[output_type]
            display_name = type_display_names.get(output_type, output_type.title())
            item = QTreeWidgetItem(
                type_root,
                [display_name, str(data["count"]), str(ByteSize(data["size"]))],
            )
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setData(0, Qt.UserRole, ("type", output_type))

        type_root.setExpanded(True)

        # By Workflow Preset
        preset_root = QTreeWidgetItem(tree, ["By Workflow Preset", "", ""])
        preset_root.setFlags(preset_root.flags() | Qt.ItemIsUserCheckable)
        preset_root.setCheckState(0, Qt.Checked)

        for preset in sorted(fp.by_preset.keys()):
            data = fp.by_preset[preset]
            item = QTreeWidgetItem(
                preset_root,
                [preset, str(data["count"]), str(ByteSize(data["size"]))],
            )
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setData(0, Qt.UserRole, ("preset", preset))

        preset_root.setExpanded(True)

        # By Age (info only, not checkable)
        age_root = QTreeWidgetItem(tree, ["By Age", "", ""])
        age_order = ["Last 7 days", "8-30 days", "31-90 days", "Older than 90 days"]

        for bucket in age_order:
            if bucket not in fp.by_age:
                continue
            data = fp.by_age[bucket]
            item = QTreeWidgetItem(
                age_root,
                [bucket, str(data["count"]), str(ByteSize(data["size"]))],
            )
            item.setData(0, Qt.UserRole, ("age", bucket))

        age_root.setExpanded(True)

        self._updating_tree = False

    def _update_gallery_totals(self):
        """Update total size and file count labels."""
        if self._gallery_footprint:
            fp = self._gallery_footprint
            self.ui.GalleryTotalSize.setText(
                f"Total Size: {ByteSize(fp.total_size)}"
            )
            self.ui.GalleryTotalFiles.setText(f"Total Files: {fp.total_files}")

    def _on_filter_changed(self, item, column):
        """Handle filter checkbox changes."""
        if self._updating_tree:
            return
        if column != 0:
            return

        # Handle parent checkbox toggling all children
        data = item.data(0, Qt.UserRole)
        if data is None and item.childCount() > 0:
            # This is a parent item, toggle all children
            self._updating_tree = True
            check_state = item.checkState(0)
            for i in range(item.childCount()):
                child = item.child(i)
                if child.flags() & Qt.ItemIsUserCheckable:
                    child.setCheckState(0, check_state)
            self._updating_tree = False

        self._update_preview_size()

    def _on_age_filter_changed(self, value):
        """Handle age slider changes."""
        if value == 0:
            self.ui.GalleryAgeLabel.setText("All ages")
        else:
            self.ui.GalleryAgeLabel.setText(f"Older than {value} days")
        self._update_preview_size()

    def _get_selected_filters(self):
        """Get currently selected filter criteria."""
        selected_types = []
        selected_presets = []

        tree = self.ui.GalleryStatsTree
        root = tree.invisibleRootItem()

        for i in range(root.childCount()):
            category = root.child(i)
            for j in range(category.childCount()):
                item = category.child(j)
                if item.checkState(0) == Qt.Checked:
                    data = item.data(0, Qt.UserRole)
                    if data:
                        filter_type, filter_value = data
                        if filter_type == "type":
                            selected_types.append(filter_value)
                        elif filter_type == "preset":
                            selected_presets.append(filter_value)

        age_days = self.ui.GalleryAgeSlider.value()
        age_filter = age_days if age_days > 0 else None

        return selected_types, selected_presets, age_filter

    def _update_preview_size(self):
        """Update the preview of space to be freed."""
        if not self._gallery_footprint:
            self.ui.GalleryPreviewSize.setText("Selected: -- files (--)")
            self.ui.GalleryCleanupButton.setEnabled(False)
            return

        from services.gallery_cleanup_service import filter_files_for_cleanup

        types, presets, age = self._get_selected_filters()
        files, total_size = filter_files_for_cleanup(
            self._gallery_footprint,
            by_types=types if types else None,
            by_presets=presets if presets else None,
            older_than_days=age,
        )

        self._selected_files = files
        self.ui.GalleryPreviewSize.setText(
            f"Selected: {len(files)} files ({ByteSize(total_size)})"
        )
        self.ui.GalleryCleanupButton.setEnabled(len(files) > 0)

    def _on_gallery_cleanup(self):
        """Execute gallery cleanup."""
        from dialog_helpers import confirm_action
        from services.gallery_cleanup_service import cleanup_gallery_files
        from ui_components import StatusColors

        if not self._selected_files:
            self.show_status("No files selected for cleanup", "warning")
            return

        file_count = len(self._selected_files)
        total_size = sum(f.size for f in self._selected_files)

        if not confirm_action(
            "Confirm Gallery Cleanup",
            f"Are you sure you want to delete {file_count} files?\n\n"
            f"This will free {ByteSize(total_size)} of disk space.\n\n"
            "This action cannot be undone.",
            parent=self.main_window,
        ):
            return

        self.animate_button_click(self.ui.GalleryCleanupButton)
        self.ui.GalleryCleanupButton.setEnabled(False)
        self.ui.galleryProgressBar.setValue(0)

        self.update_status_with_spinner("Cleaning up gallery...", StatusColors.INFO)

        self.start_worker(
            cleanup_gallery_files,
            self._selected_files,
            on_result=self._on_gallery_cleanup_complete,
            on_error=self._on_gallery_cleanup_error,
        )

    def _on_gallery_cleanup_complete(self, result):
        """Handle gallery cleanup completion."""
        from ui_components import StatusColors

        deleted, freed, errors = result
        self.ui.GalleryCleanupButton.setEnabled(True)
        self.ui.galleryProgressBar.setValue(100)

        if errors:
            logger.warning(f"Cleanup completed with {len(errors)} errors")
            for err in errors[:5]:
                logger.warning(f"  - {err}")

        self.update_status_with_spinner(
            f"Cleanup complete: deleted {deleted} files, freed {ByteSize(freed)}",
            StatusColors.SUCCESS,
            start=False,
        )

        # Rescan to update stats
        self._on_gallery_scan()

    def _on_gallery_cleanup_error(self, error_msg, traceback_str=""):
        """Handle gallery cleanup error."""
        from ui_components import StatusColors
        self.ui.GalleryCleanupButton.setEnabled(True)
        self.ui.galleryProgressBar.setValue(0)
        self.update_status_with_spinner(
            f"Cleanup failed: {error_msg}",
            StatusColors.ERROR,
            start=False,
        )
