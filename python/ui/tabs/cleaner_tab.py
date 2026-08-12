"""
Cleaner tab module for Luma Tools.

Handles cleanup of shot files (renders, USD, HIP backups)
and gallery footprint management.
"""

import os
import logging
from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem

from .base_tab import BaseTab, TabConfig
from core.utils import ByteSize
from ui_components import StatusColors

logger = logging.getLogger(__name__)


def _run_shot_cleanup(lookdev_dir, render_dirs, usd_dirs, do_hip, progress_callback=None):
    """Delete the requested shot directories, reporting progress per directory.

    Worker function — no Qt access. Each directory is deleted individually so
    the progress bar advances as work actually completes (deleting the whole
    list in one call left the bar frozen for the entire operation).

    Returns:
        dict: {"deleted_renders", "failed_renders", "deleted_usds",
               "failed_usds", "hip_requested", "hip_deleted"}
    """
    from services.cleanup_service import (
        cleanup_renders,
        cleanup_usd,
        cleanup_hip_backups,
    )

    total_steps = len(render_dirs) + len(usd_dirs) + (1 if do_hip else 0)
    step = 0

    def _tick(message):
        nonlocal step
        step += 1
        if progress_callback:
            progress_callback(int(step / max(total_steps, 1) * 100), message)

    deleted_renders, failed_renders = [], []
    for dir_name in render_dirs:
        if cleanup_renders(lookdev_dir, [dir_name]):
            deleted_renders.append(dir_name)
        else:
            failed_renders.append(dir_name)
        _tick(f"Removed render: {dir_name}")

    deleted_usds, failed_usds = [], []
    for dir_name in usd_dirs:
        if cleanup_usd(lookdev_dir, [dir_name]):
            deleted_usds.append(dir_name)
        else:
            failed_usds.append(dir_name)
        _tick(f"Removed USD: {dir_name}")

    hip_deleted = False
    if do_hip:
        hip_deleted = cleanup_hip_backups(lookdev_dir)
        _tick("Removed HIP backups")

    return {
        "deleted_renders": deleted_renders,
        "failed_renders": failed_renders,
        "deleted_usds": deleted_usds,
        "failed_usds": failed_usds,
        "hip_requested": do_hip,
        "hip_deleted": hip_deleted,
    }


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

        # Always run scanner setup so the GalleryStatsTree.itemChanged handler
        # (connected eagerly in connect_signals) doesn't see uninitialized
        # state if it fires before the first rescan, and so a later rescan
        # can't double-bind signals onto a fresh DirectoryScanner instance.
        self._setup_scanner()

        # Gallery cleanup init
        self._gallery_footprint = None
        self._selected_files = []
        self._updating_tree = False  # Flag to prevent recursive updates
        self._setup_gallery_tree()
        self._update_gallery_path_label()

        # Note: the 'HipNumber' widget name is historical — the scanner
        # (services/scan_service.py) emits label updates by widget name
        # ('HipNumber' → "Amount of Hipfiles: N"), so renaming the widget in
        # cleaner.ui would break that emit. The name stays until the scan
        # service can be updated in the same change.

        # Auto-run the shot scan on first activation so the tab shows real
        # data instead of placeholder labels. Without a shot context there is
        # nothing to scan — tell the user what the labels are waiting for.
        if self.app_state.has_shot_context():
            self.run_scanner()
        else:
            self.ui.FolderSize.setText("Press Rescan to analyze shot files")
            self.ui.HipNumber.setText("Amount of Hipfiles: —")

    # =========================================================================
    # Shot Cleanup Methods (existing functionality)
    # =========================================================================

    def _setup_scanner(self):
        """Setup the directory scanner and wire its signals to UI slots."""
        from services.scan_service import DirectoryScanner

        self.scanner = DirectoryScanner(self.app_state, self.ui, None)
        s = self.scanner.signals
        s.set_label_text.connect(self._scanner_set_label_text)
        s.add_list_item.connect(self._scanner_add_list_item)
        s.clear_list.connect(self._scanner_clear_list)
        s.scroll_list_to_bottom.connect(self._scanner_scroll_list_to_bottom)
        s.set_widget_enabled.connect(self._scanner_set_widget_enabled)
        s.set_widget_checked.connect(self._scanner_set_widget_checked)
        s.set_spinbox_range.connect(self._scanner_set_spinbox_range)
        s.set_spinbox_value.connect(self._scanner_set_spinbox_value)
        s.set_combobox_text.connect(self._scanner_set_combobox_text)

    def _scanner_widget(self, widget_name):
        """Resolve a widget the scanner addresses by name.

        The scanner reports into widgets that do not all live on this tab —
        the shot-summary labels (Complabel, Renderlabel, USDlabel, HIPlabel,
        HipNumber) are defined in settings.ui. Looking them up only on
        ``self.ui`` silently found nothing, so those labels sat on their
        placeholder text ("Not Found") no matter what the scan actually found.
        The main window's unified namespace holds every tab's named widgets,
        so fall back to it.
        """
        widget = getattr(self.ui, widget_name, None)
        if widget is not None:
            return widget
        main_ui = getattr(self.main_window, 'ui', None)
        return getattr(main_ui, widget_name, None) if main_ui is not None else None

    def _scanner_set_label_text(self, widget_name, text):
        widget = self._scanner_widget(widget_name)
        if widget is not None:
            widget.setText(text)

    def _scanner_add_list_item(self, list_name, item_text):
        widget = self._scanner_widget(list_name)
        if widget is not None:
            widget.addItem(item_text)

    def _scanner_clear_list(self, list_name):
        widget = self._scanner_widget(list_name)
        if widget is not None:
            widget.clear()

    def _scanner_scroll_list_to_bottom(self, list_name):
        widget = self._scanner_widget(list_name)
        if widget is not None and widget.count() > 0:
            widget.scrollToBottom()

    def _scanner_set_widget_enabled(self, widget_name, enabled):
        widget = self._scanner_widget(widget_name)
        if widget is not None:
            widget.setEnabled(enabled)

    def _scanner_set_widget_checked(self, widget_name, checked):
        widget = self._scanner_widget(widget_name)
        if widget is not None and hasattr(widget, "setChecked"):
            widget.setChecked(checked)

    def _scanner_set_spinbox_range(self, widget_name, lo, hi):
        widget = self._scanner_widget(widget_name)
        if widget is not None:
            widget.setRange(lo, hi)

    def _scanner_set_spinbox_value(self, widget_name, value):
        widget = self._scanner_widget(widget_name)
        if widget is not None:
            widget.setValue(value)

    def _scanner_set_combobox_text(self, widget_name, text):
        widget = self._scanner_widget(widget_name)
        if widget is None:
            return
        idx = widget.findText(text)
        if idx >= 0:
            widget.setCurrentIndex(idx)
        else:
            widget.setCurrentText(text)

    def _on_rescan_clicked(self):
        """Rescan for files to clean."""
        self.run_scanner()

    def run_scanner(self, on_complete=None):
        """
        Scan directories for renders, USD, HIP files, and comps - runs on background thread.

        Args:
            on_complete: Optional callback to call when scanning completes
        """

        if not hasattr(self, "scanner") or self.scanner is None:
            self.show_status("Scanner not available", "warning")
            return

        # Store callback for use in handlers
        self._scan_on_complete = on_complete

        # Clear UI elements
        self.ui.CleanFiles.setEnabled(False)
        self.ui.USDSClean.clear()
        self.ui.RendersClean.clear()

        # Prevent concurrent scans (double-clicking Rescan used to spawn two
        # scanner workers racing on the same UI lists). A true "Cancel"
        # affordance is not possible here: DirectoryScanner.scan_all
        # (services/scan_service.py) runs monolithic filesystem walks with no
        # cancellation hooks, so the honest state is a disabled button for
        # the duration of the scan.
        self.ui.RescanCleanFiles.setEnabled(False)
        self.ui.RescanCleanFiles.setText("Scanning…")

        # Show status bar progress
        self.update_status_with_spinner("Shot Cleaner: Scanning directories...", StatusColors.INFO)

        # Use base class worker helper. scan_all accepts a progress_callback
        # (auto-injected by Worker), so on_progress surfaces real progress —
        # previously the progress bar sat at 0 for the whole multi-minute scan.
        self.start_worker(
            self.scanner.scan_all,
            on_result=self._on_scan_result,
            on_error=self._on_scan_error,
            on_progress=self._on_scan_progress,
        )

    def _on_scan_progress(self, percent, message):
        """Update the progress bar and status during the scan."""
        self.ui.progressBar.setValue(int(percent))
        if message:
            self.set_status(message)

    def _set_rescan_idle(self):
        """Restore the Rescan button to its idle state after a scan."""
        self.ui.RescanCleanFiles.setEnabled(True)
        self.ui.RescanCleanFiles.setText("Rescan")

    def _on_scan_result(self, result):
        """Handle scan completion."""

        self._set_rescan_idle()

        # Enable the clean button only when the scan actually found something
        # to clean (render/USD versions in the lists, or a HIP backup folder).
        backup_exists = False
        try:
            lookdev = self.app_state.lookdev_dir
            if lookdev:
                backup_exists = os.path.isdir(os.path.join(lookdev, "backup"))
        except Exception:
            pass
        has_items = (
            self.ui.RendersClean.count() > 0
            or self.ui.USDSClean.count() > 0
            or backup_exists
        )
        self.ui.CleanFiles.setEnabled(has_items)

        # Select all items by default
        self._deselect_renders_in_comp(result.get("renders_in_comp", []))

        # Stop spinner and update status
        self.update_status_with_spinner(
            "Shot Cleaner: Scan complete", StatusColors.SUCCESS, start=False
        )

        # Call completion callback if provided (clear before calling to avoid re-entrancy)
        cb = getattr(self, "_scan_on_complete", None)
        self._scan_on_complete = None
        if cb:
            cb()

    def _on_scan_error(self, error_msg, traceback_str=""):
        """Handle scan error."""

        self._set_rescan_idle()
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
        """Size the pending deletion in a worker, then ask for confirmation."""
        from services.cleanup_service import get_cleanup_summary

        self.animate_button_click(self.ui.CleanFiles)

        # Collect what to clean (on main thread, reading UI state)
        render_dirs = []
        usd_dirs = []

        if self.ui.CleanRender.isChecked():
            render_dirs = [
                item.text() for item in self.ui.RendersClean.selectedItems()
            ]

        if self.ui.CleanUSD.isChecked():
            usd_dirs = [item.text() for item in self.ui.USDSClean.selectedItems()]

        do_hip = self.ui.HIPBackups.isChecked()

        if not render_dirs and not usd_dirs and not do_hip:
            # Used to return silently, leaving the user to wonder why the
            # button did nothing.
            self.show_status(
                "Nothing to clean - tick a category and select versions in the lists",
                "warning",
            )
            return

        lookdev_dir = self.app_state.lookdev_dir
        if not lookdev_dir:
            self.show_status("No task directory resolved - press Rescan first", "warning")
            return

        # Sizing walks the whole version tree on a network share, so it runs in
        # a worker; the confirmation dialog is shown once the real byte count
        # is known (previously the dialog only quoted directory counts).
        self._pending_cleanup_lookdev = lookdev_dir
        self.ui.CleanFiles.setEnabled(False)
        self.update_status_with_spinner(
            "Shot Cleaner: Calculating deletion size...", StatusColors.INFO
        )
        self.start_worker(
            get_cleanup_summary,
            lookdev_dir,
            render_dirs,
            usd_dirs,
            do_hip,
            on_result=self._on_cleanup_size_ready,
            on_error=self._on_cleanup_size_error,
        )

    def _on_cleanup_size_ready(self, summary):
        """Confirm the deletion with real sizes, then run it (GUI thread)."""
        from dialog_helpers import confirm_action

        self.update_status_with_spinner(
            "Shot Cleaner: Ready to clean", StatusColors.INFO, start=False
        )
        self.ui.CleanFiles.setEnabled(True)

        render_dirs = summary["render_dirs"]
        usd_dirs = summary["usd_dirs"]
        do_hip = summary["backups"]
        lookdev_dir = getattr(self, "_pending_cleanup_lookdev", "")

        summary_parts = []
        detail_lines = []
        if render_dirs:
            summary_parts.append(
                f"{len(render_dirs)} render director{'y' if len(render_dirs) == 1 else 'ies'}"
            )
            detail_lines.append("Render directories:")
            detail_lines.extend(f"  {name}" for name in render_dirs)
        if usd_dirs:
            summary_parts.append(
                f"{len(usd_dirs)} USD director{'y' if len(usd_dirs) == 1 else 'ies'}"
            )
            detail_lines.append("USD directories:")
            detail_lines.extend(f"  {name}" for name in usd_dirs)
        if do_hip:
            summary_parts.append("HIP backups folder")
            detail_lines.append(f"HIP backups folder: {os.path.join(lookdev_dir, 'backup')}")

        if not confirm_action(
            "Confirm Shot Cleanup",
            f"Are you sure you want to delete {', '.join(summary_parts)}?\n\n"
            f"This will free {ByteSize(summary['total_size'])} of disk space.\n\n"
            "This action cannot be undone.",
            parent=self.main_window,
            detail="\n".join(detail_lines),
        ):
            return

        self.ui.CleanFiles.setEnabled(False)
        self.ui.progressBar.setValue(0)
        self.update_status_with_spinner("Shot Cleaner: Cleaning up files...", StatusColors.INFO)

        self.start_worker(
            _run_shot_cleanup,
            lookdev_dir,
            render_dirs,
            usd_dirs,
            do_hip,
            on_result=self._on_cleanup_complete,
            on_error=self._on_cleanup_error,
            on_progress=self._on_cleanup_progress,
        )

    def _on_cleanup_size_error(self, error_msg, traceback_str=""):
        """Handle failure while sizing the pending cleanup."""
        self.ui.CleanFiles.setEnabled(True)
        self.update_status_with_spinner(
            f"Shot Cleaner: Could not calculate size - {error_msg}",
            StatusColors.ERROR,
            start=False,
        )
        logger.error(f"Cleanup size calculation failed: {error_msg}")
        if traceback_str:
            logger.error(traceback_str)

    def _on_cleanup_progress(self, percent, message):
        """Update the progress bar as each directory finishes deleting."""
        self.ui.progressBar.setValue(int(percent))
        if message:
            self.set_status(message)

    def _on_cleanup_complete(self, result):
        """Handle cleanup completion, reporting per-directory failures."""
        from dialog_helpers import show_warning

        failures = list(result["failed_renders"]) + list(result["failed_usds"])
        if result["hip_requested"] and not result["hip_deleted"]:
            failures.append("HIP backups folder")

        deleted_count = len(result["deleted_renders"]) + len(result["deleted_usds"])
        if result["hip_deleted"]:
            deleted_count += 1

        if failures:
            logger.warning(f"Shot cleanup finished with {len(failures)} failures")
            show_warning(
                "Partial Cleanup",
                f"Deleted {deleted_count} item(s), but {len(failures)} could not be removed.\n"
                "They may be in use or you may lack permission.",
                self.main_window,
                detail="\n".join(failures),
            )
            self.update_status_with_spinner(
                f"Shot Cleaner: Cleanup finished with {len(failures)} failures",
                StatusColors.WARNING,
                start=False,
            )
        else:
            self.update_status_with_spinner(
                f"Shot Cleaner: Cleanup complete ({deleted_count} item(s) removed)",
                StatusColors.SUCCESS,
                start=False,
            )
        self.run_scanner()

    def _on_cleanup_error(self, error_msg, traceback_str=""):
        """Handle an unexpected cleanup failure."""
        self.update_status_with_spinner(
            f"Shot Cleaner: Cleanup error - {error_msg}", StatusColors.ERROR, start=False
        )
        logger.error(f"Cleanup error: {error_msg}")
        if traceback_str:
            logger.error(traceback_str)
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
        from services.gallery_cleanup_service import get_gallery_root_path

        path = get_gallery_root_path()
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
            get_gallery_root_path,
            scan_gallery_footprint,
        )

        output_path = get_gallery_root_path()
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
        # connect_signals() runs eagerly at startup but _updating_tree is set
        # in initialize() which is deferred until first activation, so this
        # may fire before initialize. Bail out cleanly in that case.
        if not hasattr(self, "_updating_tree") or self._updating_tree:
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
        # May fire before deferred initialize() creates _gallery_footprint /
        # _selected_files (same guard as _on_filter_changed)
        if hasattr(self, "_gallery_footprint"):
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

        # Guard against firing before deferred initialize() creates state
        if not getattr(self, '_selected_files', None):
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
        from dialog_helpers import show_warning

        deleted, freed, errors = result
        self.ui.GalleryCleanupButton.setEnabled(True)
        self.ui.galleryProgressBar.setValue(100)

        if errors:
            # Reporting a flat "Cleanup complete" while files failed to delete
            # hid real failures (locked files, permission errors) — surface them.
            logger.warning(f"Cleanup completed with {len(errors)} errors")
            for err in errors[:5]:
                logger.warning(f"  - {err}")
            summary = (
                f"Deleted {deleted} files ({ByteSize(freed)} freed), "
                f"but {len(errors)} file(s) could not be deleted.\n"
                "They may be open in another application or read-only."
            )
            show_warning(
                "Partial Cleanup",
                summary,
                self.main_window,
                detail="\n".join(str(e) for e in errors),
            )
            self.update_status_with_spinner(
                f"Gallery cleanup finished with {len(errors)} errors "
                f"(deleted {deleted} files, freed {ByteSize(freed)})",
                StatusColors.WARNING,
                start=False,
            )
        else:
            self.update_status_with_spinner(
                f"Cleanup complete: deleted {deleted} files, freed {ByteSize(freed)}",
                StatusColors.SUCCESS,
                start=False,
            )

        # Rescan to update stats
        self._on_gallery_scan()

    def _on_gallery_cleanup_error(self, error_msg, traceback_str=""):
        """Handle gallery cleanup error."""
        self.ui.GalleryCleanupButton.setEnabled(True)
        self.ui.galleryProgressBar.setValue(0)
        self.update_status_with_spinner(
            f"Cleanup failed: {error_msg}",
            StatusColors.ERROR,
            start=False,
        )
