"""
ComfyUI tab module for Luma Tools.

Handles ComfyUI workflow submission and AI image generation.
"""

from PySide2 import QtWidgets, QtCore
from PySide2.QtCore import QThreadPool

from .base_tab import BaseTab


class ComfyUITab(BaseTab):
    """Tab for ComfyUI AI image generation."""

    @property
    def ui_file(self) -> str:
        return "comfyui.ui"

    @property
    def tab_name(self) -> str:
        return "ComfyUI"

    @property
    def tab_id(self) -> str:
        return "comfyui"

    def connect_signals(self):
        """Connect ComfyUI tab signals."""
        self.ui.ComfyUIChoosePreset.clicked.connect(self._on_choose_preset_clicked)
        self.ui.ComfyUIAddPreset.clicked.connect(self._on_add_preset_clicked)
        self.ui.ComfyUIEditPreset.clicked.connect(self._on_edit_preset_clicked)
        self.ui.ComfyUIDeletePreset.clicked.connect(self._on_delete_preset_clicked)
        self.ui.ComfyUIBrowseOutputDir.clicked.connect(self._on_browse_output_dir)
        self.ui.ComfyUIRandomizeSeed.clicked.connect(self._on_randomize_seed)
        self.ui.ComfyUIChooseMode.clicked.connect(self._on_choose_mode_clicked)
        self.ui.ComfyUISubmit.clicked.connect(self._on_submit_clicked)
        self.ui.ComfyUIUseAsInput.clicked.connect(self._on_use_as_input_clicked)

    def initialize(self):
        """Initialize ComfyUI tab."""
        import random
        # Set random initial seed
        self.ui.ComfyUISeed.setValue(random.randint(0, 2147483647))
        # Hide iterate frame initially
        self.ui.comfyuiIterateFrame.setVisible(False)

    def _on_choose_preset_clicked(self):
        """Choose a workflow preset."""
        # TODO: Migrate from luma_tools.py _on_choose_preset_clicked
        self.log("ComfyUI: Choose preset clicked")

    def _on_add_preset_clicked(self):
        """Add a new workflow preset."""
        # TODO: Migrate from luma_tools.py _on_add_preset_clicked
        self.log("ComfyUI: Add preset clicked")

    def _on_edit_preset_clicked(self):
        """Edit the selected workflow preset."""
        # TODO: Migrate from luma_tools.py _on_edit_preset_clicked
        self.log("ComfyUI: Edit preset clicked")

    def _on_delete_preset_clicked(self):
        """Delete the selected workflow preset."""
        # TODO: Migrate from luma_tools.py _on_delete_preset_clicked
        self.log("ComfyUI: Delete preset clicked")

    def _on_browse_output_dir(self):
        """Browse for output directory."""
        # TODO: Migrate from luma_tools.py
        pass

    def _on_randomize_seed(self):
        """Generate a new random seed."""
        import random
        self.ui.ComfyUISeed.setValue(random.randint(0, 2147483647))

    def _on_choose_mode_clicked(self):
        """Choose submission mode (Batch/Iterate)."""
        # TODO: Migrate from luma_tools.py
        self.log("ComfyUI: Choose mode clicked")

    def _on_submit_clicked(self):
        """Submit workflow to farm."""
        # TODO: Migrate from luma_tools.py _on_comfyui_submit_clicked
        self.log("ComfyUI: Submit clicked")

    def _on_use_as_input_clicked(self):
        """Use generated image as input for next iteration."""
        # TODO: Migrate from luma_tools.py
        self.log("ComfyUI: Use as input clicked")
