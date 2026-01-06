"""
ComfyUI Gallery tab module for Luma Tools.

Handles browsing and displaying generated images.
"""

from PySide2 import QtWidgets, QtCore
from PySide2.QtCore import QThreadPool

from .base_tab import BaseTab


class ComfyUIGalleryTab(BaseTab):
    """Tab for browsing ComfyUI generated images."""

    @property
    def ui_file(self) -> str:
        return "comfyui_gallery.ui"

    @property
    def tab_name(self) -> str:
        return "ComfyUI Gallery"

    @property
    def tab_id(self) -> str:
        return "comfyui_gallery"

    def connect_signals(self):
        """Connect gallery tab signals."""
        self.ui.GalleryBrowse.clicked.connect(self._on_browse_clicked)
        self.ui.GalleryRefresh.clicked.connect(self._on_refresh_clicked)

    def initialize(self):
        """Initialize gallery tab."""
        pass

    def _on_browse_clicked(self):
        """Browse for gallery directory."""
        # TODO: Migrate from luma_tools.py _on_gallery_browse_clicked
        self.log("Gallery: Browse clicked")

    def _on_refresh_clicked(self):
        """Refresh the gallery view."""
        # TODO: Migrate from luma_tools.py _on_gallery_refresh_clicked
        self.log("Gallery: Refresh clicked")
