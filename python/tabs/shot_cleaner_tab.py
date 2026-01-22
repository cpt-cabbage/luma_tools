"""
Shot Cleaner tab module for Luma Tools.

Handles cleanup of renders, USD files, and HIP backups.
"""

import os

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QThreadPool

from .base_tab import BaseTab


class ShotCleanerTab(BaseTab):
    """Tab for cleaning up shot files."""

    @property
    def ui_file(self) -> str:
        return "shot_cleaner.ui"

    @property
    def tab_name(self) -> str:
        return "Shot Cleaner"

    @property
    def tab_id(self) -> str:
        return "shotcleaner"

    def connect_signals(self):
        """Connect shot cleaner tab signals."""
        self.ui.RescanCleanFiles.clicked.connect(self._on_rescan_clicked)
        self.ui.CleanFiles.clicked.connect(self._on_clean_files_clicked)

    def initialize(self):
        """Initialize shot cleaner tab."""
        self.ui.progressBar.setValue(0)

        # Set up scanner if app_state has lookdev_dir
        if self.app_state.lookdev_dir:
            self._setup_scanner()

    def _setup_scanner(self):
        """Setup the directory scanner."""
        from services.scan_service import DirectoryScanner

        self.scanner = DirectoryScanner(self.app_state.lookdev_dir)

        # Connect scanner signals to UI
        self.scanner.signals.add_render_item.connect(self._on_add_render_item)
        self.scanner.signals.add_usd_item.connect(self._on_add_usd_item)
        self.scanner.signals.set_hip_backup_label.connect(self._on_set_hip_backup_label)
        self.scanner.signals.set_latest_render_label.connect(self._on_set_latest_render_label)

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
        from ui_components import Worker, StatusColors

        if not hasattr(self, 'scanner'):
            self._setup_scanner()

        # Clear UI elements
        self.ui.CleanFiles.setEnabled(False)
        self.ui.USDSClean.clear()
        self.ui.RendersClean.clear()

        def on_result(result):
            """Called when scanning completes."""
            # Enable clean button
            self.ui.CleanFiles.setEnabled(True)

            # Select all items by default
            self._deselect_renders_in_comp(result.get('renders_in_comp', []))

            # Stop spinner and update status
            self.update_status_with_spinner(

                "✅ Shot Cleaner: Scan complete",

                StatusColors.SUCCESS,

                start=False

            )

            # Call completion callback if provided
            if on_complete:
                on_complete()

        def on_error(error_msg, traceback_str):
            """Called when scanning fails."""
            self.update_status_with_spinner(

                f"Shot Cleaner: Scan error - {error_msg}",

                StatusColors.ERROR,

                start=False

            )
            self.log(f"Scanner error: {error_msg}")
            self.log(traceback_str)

            # Call completion callback even on error
            if on_complete:
                on_complete()

        # Show status bar progress (no overlay so user can still interact)
        self.update_status_with_spinner(

            "🔍 Shot Cleaner: Scanning directories...",

            StatusColors.INFO

        )

        # Create worker and run scan on background thread
        # Store as instance attribute to prevent garbage collection
        self._scan_worker = Worker(self.scanner.scan_all)
        self._scan_worker.signals.result.connect(on_result)
        self._scan_worker.signals.error.connect(on_error)
        QThreadPool.globalInstance().start(self._scan_worker)

    def _deselect_renders_in_comp(self, renders_in_comp):
        """Deselect renders that are in use by comp files."""
        self.ui.RendersClean.selectAll()
        self.ui.USDSClean.selectAll()

        if renders_in_comp:
            for render_name in renders_in_comp:
                matching_items = self.ui.RendersClean.findItems(render_name, Qt.MatchContains)
                for item in matching_items:
                    item.setSelected(False)

    def _on_clean_files_clicked(self):
        """Handle cleanup button click."""
        from ui_components import StatusColors
        from services.cleanup_service import cleanup_renders, cleanup_usd, cleanup_hip_backups

        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.animate_button_click(self.ui.CleanFiles)

        # Cleanup renders
        if self.ui.CleanRender.isChecked():
            render_dirs = [item.text() for item in self.ui.RendersClean.selectedItems()]
            if render_dirs:
                count = 0
                for dir_name in render_dirs:
                    count += 1
                    status_msg = f"Removing Renders: {self.app_state.lookdev_dir}\\img\\renders\\{dir_name}"
                    if hasattr(self.main_window, 'animator'):
                        self.main_window.animator.update_status_animated(status_msg, StatusColors.WARNING)
                    self.log(status_msg)
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
                    if hasattr(self.main_window, 'animator'):
                        self.main_window.animator.update_status_animated(status_msg, StatusColors.WARNING)
                    self.log(status_msg)

                cleanup_usd(self.app_state.lookdev_dir, usd_dirs)

        # Cleanup HIP backups
        if self.ui.HIPBackups.isChecked():
            self.ui.progressBar.setValue(0)
            status_msg = f"Removing Hip Backups Folder: {self.app_state.lookdev_dir}\\backup\\"
            if hasattr(self.main_window, 'animator'):
                self.main_window.animator.update_status_animated(status_msg, StatusColors.WARNING)
            cleanup_hip_backups(self.app_state.lookdev_dir)
            self.ui.progressBar.setValue(100)

        # Final status - use show_success for proper priority queue handling
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.show_success("Cleanup complete")

        # Rescan after cleanup
        self.run_scanner()
