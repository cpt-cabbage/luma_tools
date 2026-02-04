"""
MP4 Maker tab module for Luma Tools.

Handles MP4 generation from EXR sequences.
"""

import os

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QTimer

from core.config import DEFAULT_VIDEOS_DIR, UIStyles
from .base_tab import BaseTab, TabConfig
from .mixins.render_scan_mixin import RenderScanMixin
import logging


class MP4MakerTab(RenderScanMixin, BaseTab):
    """Tab for generating MP4 files from render sequences."""

    TAB_CONFIG = TabConfig(ui_file="mp4_maker.ui", tab_name="MP4 Maker", tab_id="mp4maker")

    # RenderScanMixin widget configuration
    _render_list_widget = "MP4RendersList"
    _render_path_widget = "MP4RenderPath"
    _version_widget = "MP4CurrentVer"
    _action_button = "MP4Generate"
    _source_button = "MP4SourceButton"
    _custom_path_label = "MP4CustomPathLabel"
    _browse_custom_button = "MP4BrowseCustomPath"

    # RenderScanMixin app_state attributes
    _renders_attr = "mp4_renders"
    _searchpath_attr = "mp4_searchpath"
    _custom_path_attr = "mp4_custom_path"

    def connect_signals(self):
        """Connect MP4 maker tab signals."""
        self.ui.MP4ScanRenders.clicked.connect(self._on_scan_renders_clicked)
        self.ui.MP4CurrentVer.valueChanged.connect(self._on_scan_renders_clicked)
        # Source and quality buttons connected in initialize() via managers
        self.ui.MP4BrowseCustomPath.clicked.connect(self._on_browse_custom_path)
        self.ui.MP4RendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.MP4BrowseOutput.clicked.connect(self._on_browse_output)
        self.ui.MP4Generate.clicked.connect(self._on_generate_clicked)
        # Add to Gallery checkbox state persistence
        self.ui.MP4AddToGallery.stateChanged.connect(self._on_add_to_gallery_changed)

    def initialize(self):
        """Initialize MP4 maker tab."""
        from option_button import IndexedOptionButtonManager
        from core.settings_manager import get_setting

        self.ui.MP4Generate.setEnabled(False)

        # Source manager from mixin
        self._init_source_manager()

        # Quality option manager (indexed options) - MP4-specific
        self._quality_manager = IndexedOptionButtonManager(
            button=self.ui.MP4QualityButton,
            options=[
                (0, "High Quality (CRF 18)", "Quality: High (CRF 18)"),
                (1, "Medium Quality (CRF 23)", "Quality: Medium (CRF 23)"),
                (2, "Low Quality (CRF 28)", "Quality: Low (CRF 28)"),
            ],
            initial_index=0,
            on_changed=lambda idx: None,  # No additional action needed
            parent_window=self.main_window
        )

        # Load "Add to Gallery" checkbox state from user settings
        add_to_gallery = get_setting("mp4_maker_add_to_gallery")
        self.ui.MP4AddToGallery.setChecked(add_to_gallery)

    @property
    def _quality_index(self):
        return self._quality_manager.index

    def _on_render_selection_changed(self):
        """Update MP4 state when selected render changes."""
        from services.mp4_maker import get_output_filename

        selected = self._get_selected_render()
        if not selected:
            self.ui.MP4Generate.setEnabled(False)
            return

        subdir, render_seq = selected
        self.app_state.mp4_startframe = render_seq.start()
        self.app_state.mp4_endframe = render_seq.end()

        logging.info(f"MP4 Maker: Selected render from '{subdir}' - frames {self.app_state.mp4_startframe} to {self.app_state.mp4_endframe}")

        # Automatically set output path to user's Videos folder
        framename = render_seq.frame(render_seq.start())
        filename = os.path.basename(framename)
        from core.utils import extract_render_name
        render_name = extract_render_name(filename)
        default_filename = get_output_filename(render_name, self.app_state.shot)
        videos_folder = DEFAULT_VIDEOS_DIR
        self.app_state.mp4_output_path = os.path.join(videos_folder, default_filename)

        # Update UI
        self.ui.MP4OutputPath.setText(self.app_state.mp4_output_path)
        self.ui.MP4OutputPath.setStyleSheet(UIStyles.LABEL_PATH)

        # Enable generate button
        self.ui.MP4Generate.setEnabled(True)
        self.pulse_button(self.ui.MP4Generate)

    def _on_browse_output(self):
        """Browse for MP4 output location."""
        from file_dialogs import save_file_with_memory
        from services.mp4_maker import get_output_filename

        # Get current render name for default filename
        default_filename = f"{self.app_state.shot}_preview.mp4"

        selected = self._get_selected_render()
        if selected:
            subdir, render_seq = selected
            framename = render_seq.frame(render_seq.start())
            filename = os.path.basename(framename)
            from core.utils import extract_render_name
            render_name = extract_render_name(filename)
            default_filename = get_output_filename(render_name, self.app_state.shot)

        # Use save_file_with_memory helper
        output_file = save_file_with_memory(
            self.main_window,
            context="mp4_output",
            title="Save MP4 As",
            default_filename=default_filename,
            file_filter="MP4 Video (*.mp4)",
            fallback_path=DEFAULT_VIDEOS_DIR
        )

        if output_file:
            self.app_state.mp4_output_path = output_file
            self.ui.MP4OutputPath.setText(output_file)
            self.ui.MP4OutputPath.setStyleSheet(UIStyles.LABEL_PATH)

            # Enable generate button if render is selected
            if self._get_selected_render():
                self.ui.MP4Generate.setEnabled(True)
                self.pulse_button(self.ui.MP4Generate)

    def _on_generate_clicked(self):
        """Generate MP4 from selected render - runs on background thread."""
        from ui_components import Worker, StatusColors
        from services.mp4_maker import generate_mp4

        # Show status bar progress (no overlay so user can still interact)
        self.update_status_with_spinner(
            "MP4: Preparing to convert...",
            StatusColors.INFO
        )
        self.animate_button_click(self.ui.MP4Generate)

        # Get selected render
        selected = self._get_selected_render()
        if not selected:
            self.update_status_with_spinner(
                "No render selected",
                StatusColors.ERROR,
                start=False
            )
            return

        # Get render info
        self.animator.update_status_animated(
            "MP4: Analyzing render sequence...",
            StatusColors.INFO
        )

        subdir, render_seq = selected
        framename = render_seq.frame(self.app_state.mp4_startframe)

        # Build input pattern for ffmpeg
        base_dir = os.path.dirname(framename)
        base_filename = os.path.basename(framename)
        parts = base_filename.split(".")
        if len(parts) < 3:
            self.update_status_with_spinner(
                f"Unexpected filename format: {base_filename}",
                StatusColors.ERROR,
                start=False
            )
            return

        # Format: name.####.exr
        input_pattern = os.path.join(base_dir, f"{parts[0]}.%04d.exr")

        # Get settings
        self.animator.update_status_animated(
            "MP4: Configuring conversion settings...",
            StatusColors.INFO
        )

        quality_index = self._quality_index
        burn_in_timecode = self.ui.MP4BurnInTimecode.isChecked()

        def on_progress(progress, message):
            """Update UI with MP4 generation progress."""
            self.animator.update_status_animated(
                f"MP4: {message} ({progress}%)",
                StatusColors.INFO
            )

        def on_result(success):
            """Called when MP4 generation completes."""
            if success:
                # Check if we should copy to gallery
                if self.ui.MP4AddToGallery.isChecked():
                    self.update_status_with_spinner(
                        f"MP4 generated. Copying to gallery...",
                        StatusColors.INFO,
                        start=True
                    )
                    self._copy_to_gallery(input_pattern)
                else:
                    self.update_status_with_spinner(
                        f"MP4 generated: {os.path.basename(self.app_state.mp4_output_path)}",
                        StatusColors.SUCCESS,
                        start=False
                    )
                    self.show_status("MP4 generation complete!", "success")
            else:
                self.update_status_with_spinner(
                    "MP4 generation failed",
                    StatusColors.ERROR,
                    start=False
                )

        def on_error(error_msg, traceback_str):
            """Called when MP4 generation fails."""
            self.update_status_with_spinner(
                f"MP4 generation failed: {error_msg}",
                StatusColors.ERROR,
                start=False
            )
            logging.error(f"MP4 generation error: {error_msg}")
            logging.debug(traceback_str)

        # Use BaseTab helper for worker management
        self.start_worker(
            generate_mp4,
            input_pattern,
            self.app_state.mp4_output_path,
            self.app_state.mp4_startframe,
            self.app_state.mp4_endframe,
            worker_kwargs={
                "quality_index": quality_index,
                "burn_in_timecode": burn_in_timecode,
            },
            on_result=on_result,
            on_error=on_error,
            on_progress=on_progress,
        )

    def _on_add_to_gallery_changed(self, state):
        """Save Add to Gallery checkbox state to user settings."""
        from core.settings_manager import set_setting
        from PySide6.QtCore import Qt
        set_setting("mp4_maker_add_to_gallery", state == Qt.Checked, verbose=False)

    def _copy_to_gallery(self, source_path: str):
        """Copy the generated MP4 to the gallery folder with metadata."""
        from ui_components import StatusColors
        from services.mp4_maker import copy_mp4_to_gallery

        def on_gallery_result(result):
            """Handle gallery copy completion."""
            success, path_or_error = result
            if success:
                self.update_status_with_spinner(
                    f"MP4 generated and added to gallery",
                    StatusColors.SUCCESS,
                    start=False
                )
                self.show_status("MP4 generation complete! Added to gallery.", "success")
            else:
                self.update_status_with_spinner(
                    f"MP4 generated (gallery copy failed: {path_or_error})",
                    StatusColors.WARNING,
                    start=False
                )
                self.show_status(f"MP4 generated but gallery copy failed: {path_or_error}", "warning")

        def on_gallery_error(error_msg, traceback_str):
            """Handle gallery copy error."""
            self.update_status_with_spinner(
                f"MP4 generated (gallery error: {error_msg})",
                StatusColors.WARNING,
                start=False
            )
            logging.error(f"Gallery copy error: {error_msg}")

        # Run gallery copy on worker thread
        self.start_worker(
            copy_mp4_to_gallery,
            worker_kwargs={
                "mp4_path": self.app_state.mp4_output_path,
                "user": self.app_state.user,
                "shot": self.app_state.shot,
                "source_path": source_path,
                "frame_range": (self.app_state.mp4_startframe, self.app_state.mp4_endframe),
                "quality_index": self._quality_index,
                "burn_in_timecode": self.ui.MP4BurnInTimecode.isChecked(),
            },
            on_result=on_gallery_result,
            on_error=on_gallery_error
        )
