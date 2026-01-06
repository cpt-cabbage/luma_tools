"""
Shot Cleaner tab module for Luma Tools.

Handles cleanup of renders, USD files, and HIP backups.
"""

from PySide2 import QtWidgets, QtCore
from PySide2.QtCore import QThreadPool

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

    def _on_rescan_clicked(self):
        """Rescan for files to clean."""
        # TODO: Migrate from luma_tools.py run_scanner
        self.log("Shot Cleaner: Rescan clicked")

    def _on_clean_files_clicked(self):
        """Clean selected files."""
        # TODO: Migrate from luma_tools.py on_clean_files_clicked
        self.log("Shot Cleaner: Clean files clicked")
