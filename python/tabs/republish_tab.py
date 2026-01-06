"""
rePublish tab module for Luma Tools.

Handles republishing renders to AYON.
"""

from PySide2 import QtWidgets, QtCore
from PySide2.QtCore import QThreadPool

from .base_tab import BaseTab


class RePublishTab(BaseTab):
    """Tab for republishing renders to AYON."""

    @property
    def ui_file(self) -> str:
        return "republish.ui"

    @property
    def tab_name(self) -> str:
        return "rePublish"

    @property
    def tab_id(self) -> str:
        return "republish"

    def connect_signals(self):
        """Connect rePublish tab signals."""
        self.ui.RePublishScanRenders.clicked.connect(self._on_scan_renders_clicked)
        self.ui.RePublishCurrentVer.valueChanged.connect(self._on_scan_renders_clicked)
        self.ui.RePublishUseForComp.toggled.connect(self._on_source_changed)
        self.ui.RePublishUseRaw.toggled.connect(self._on_source_changed)
        self.ui.RePublishUseCustom.toggled.connect(self._on_source_changed)
        self.ui.RePublishBrowseCustomPath.clicked.connect(self._on_browse_custom_path)
        self.ui.RePublishRendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.RePublishPublish.clicked.connect(self._on_publish_clicked)

    def initialize(self):
        """Initialize rePublish tab."""
        self.ui.RePublishPublish.setEnabled(False)
        self.custom_path = None

    def _on_scan_renders_clicked(self):
        """Scan for renders."""
        # TODO: Migrate from luma_tools.py on_republish_scan_renders_clicked
        self.log("rePublish: Scan renders clicked")

    def _on_source_changed(self):
        """Handle source type change."""
        is_custom = self.ui.RePublishUseCustom.isChecked()
        self.ui.RePublishBrowseCustomPath.setEnabled(is_custom)

    def _on_browse_custom_path(self):
        """Browse for custom render path."""
        # TODO: Migrate from luma_tools.py on_republish_browse_custom_path_clicked
        pass

    def _on_render_selection_changed(self):
        """Handle render selection change."""
        # TODO: Migrate from luma_tools.py on_republish_render_selection_changed
        pass

    def _on_publish_clicked(self):
        """Publish selected render to AYON."""
        # TODO: Migrate from luma_tools.py on_republish_publish_clicked
        self.log("rePublish: Publish clicked")
