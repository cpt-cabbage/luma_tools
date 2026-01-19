"""
MP4 Maker tab module for Luma Tools.

Handles MP4 generation from EXR sequences.
"""

import os

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QFileDialog

from .base_tab import BaseTab


class MP4MakerTab(BaseTab):
    """Tab for generating MP4 files from render sequences."""

    @property
    def ui_file(self) -> str:
        return "mp4_maker.ui"

    @property
    def tab_name(self) -> str:
        return "MP4 Maker"

    @property
    def tab_id(self) -> str:
        return "mp4maker"

    def connect_signals(self):
        """Connect MP4 maker tab signals."""
        self.ui.MP4ScanRenders.clicked.connect(self._on_scan_renders_clicked)
        self.ui.MP4CurrentVer.valueChanged.connect(self._on_scan_renders_clicked)
        self.ui.MP4SourceButton.clicked.connect(self._on_source_button_clicked)
        self.ui.MP4BrowseCustomPath.clicked.connect(self._on_browse_custom_path)
        self.ui.MP4RendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.MP4BrowseOutput.clicked.connect(self._on_browse_output)
        self.ui.MP4Generate.clicked.connect(self._on_generate_clicked)
        self.ui.MP4QualityButton.clicked.connect(self._on_quality_button_clicked)

    def initialize(self):
        """Initialize MP4 maker tab."""
        self.ui.MP4Generate.setEnabled(False)

        # Source options (label, value)
        self._source = "for_comp"  # Default
        self._source_options = [
            ("For Comp", "for_comp"),
            ("Raw", "raw"),
            ("Custom", "custom"),
        ]
        self._update_source_button_text()

        # Quality options (index, label, button_label)
        self._quality_index = 0  # Default: high quality
        self._quality_options = [
            (0, "High Quality (CRF 18)", "Quality: High (CRF 18)"),
            (1, "Medium Quality (CRF 23)", "Quality: Medium (CRF 23)"),
            (2, "Low Quality (CRF 28)", "Quality: Low (CRF 28)"),
        ]
        self._update_quality_button_text()

    def _update_source_button_text(self):
        """Update the source button text to show current selection."""
        # Find label for current source value
        label = next((l for l, v in self._source_options if v == self._source), self._source)
        # Update with output_subdirectory if available and using for_comp
        if self._source == "for_comp" and self.app_state.output_subdirectory:
            label = self.app_state.output_subdirectory.title()
        self.ui.MP4SourceButton.setText(f"Source: {label}")

    def _update_quality_button_text(self):
        """Update the quality button text to show current selection."""
        for index, label, button_label in self._quality_options:
            if index == self._quality_index:
                self.ui.MP4QualityButton.setText(button_label)
                break

    def _on_source_button_clicked(self):
        """Show popup menu with source options."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self.main_window)

        for label, value in self._source_options:
            # Update label for for_comp if output_subdirectory is set
            display_label = label
            if value == "for_comp" and self.app_state.output_subdirectory:
                display_label = self.app_state.output_subdirectory.title()

            action = menu.addAction(display_label)
            action.setData(value)
            if value == self._source:
                action.setCheckable(True)
                action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.MP4SourceButton.mapToGlobal(
            self.ui.MP4SourceButton.rect().bottomLeft()
        ))

        if action and action.data():
            self._source = action.data()
            self._update_source_button_text()
            self._on_source_changed()

    def _on_quality_button_clicked(self):
        """Show popup menu with quality options."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self.main_window)

        for index, label, button_label in self._quality_options:
            action = menu.addAction(label)
            action.setData(index)
            if index == self._quality_index:
                action.setCheckable(True)
                action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.MP4QualityButton.mapToGlobal(
            self.ui.MP4QualityButton.rect().bottomLeft()
        ))

        if action and action.data() is not None:
            self._quality_index = action.data()
            self._update_quality_button_text()

    def _on_source_changed(self):
        """Handle source type change - show/hide custom path controls and trigger scan."""
        is_custom = self._source == "custom"

        # Show/hide browse button and custom path label based on source type
        self.ui.MP4BrowseCustomPath.setVisible(is_custom)
        self.ui.MP4CustomPathLabel.setVisible(is_custom)

        # Trigger scan
        self._on_scan_renders_clicked()

    def _on_browse_custom_path(self):
        """Browse for custom directory containing image sequences."""
        from core.user_preferences import get_last_browse_directory, set_last_browse_directory

        default_dir = get_last_browse_directory("mp4_custom")
        if not default_dir:
            default_dir = os.path.join(os.path.expanduser("~"), "Videos")

        custom_dir = QFileDialog.getExistingDirectory(
            self.main_window,
            "Select Directory with Image Sequence",
            default_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if custom_dir:
            self.app_state.mp4_custom_path = custom_dir
            self.ui.MP4CustomPathLabel.setText(f"Custom path: {custom_dir}")
            self.ui.MP4CustomPathLabel.setStyleSheet("color: white; font-size: 9pt;")
            self.log(f"MP4 Maker: Custom path set to: {custom_dir}")
            set_last_browse_directory("mp4_custom", custom_dir)
            self._on_scan_renders_clicked()

    def _on_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        from core.utils import update_path_version, scan_exr_sequences

        self.ui.MP4RendersList.clear()

        # Build search path
        self.app_state.mp4_searchpath = self.ui.MP4RenderPath.text()

        # Handle version change
        if self.app_state.mp4_searchpath:
            newver = self.ui.MP4CurrentVer.value()
            self.app_state.mp4_searchpath = update_path_version(self.app_state.mp4_searchpath, newver)
            self.ui.MP4RenderPath.setText(self.app_state.mp4_searchpath)

        # Update source button text with actual subdirectory name if using for_comp
        self._update_source_button_text()

        # Determine which source to scan based on source selection
        self.app_state.mp4_renders = []
        self.ui.MP4Generate.setEnabled(False)

        self.log(f"MP4 Maker: Scanning path: {self.app_state.mp4_searchpath}")

        if self._source == "for_comp":
            for_comp_path = os.path.join(self.app_state.mp4_searchpath, self.app_state.output_subdirectory)
            self.log(f"MP4 Maker: Scanning {self.app_state.output_subdirectory} path: {for_comp_path}")
            if os.path.exists(for_comp_path):
                for_comp_renders = scan_exr_sequences(for_comp_path)
                self.log(f"MP4 Maker: Found {len(for_comp_renders)} renders in {self.app_state.output_subdirectory}")
                for render_seq in for_comp_renders:
                    self.app_state.mp4_renders.append((self.app_state.output_subdirectory, render_seq))

        elif self._source == "raw":
            self.log(f"MP4 Maker: Scanning raw render path: {self.app_state.mp4_searchpath}")
            if os.path.exists(self.app_state.mp4_searchpath):
                root_renders = scan_exr_sequences(self.app_state.mp4_searchpath)
                self.log(f"MP4 Maker: Found {len(root_renders)} renders in root")
                for render_seq in root_renders:
                    self.app_state.mp4_renders.append(("raw", render_seq))

        elif self._source == "custom":
            self.log(f"MP4 Maker: Scanning custom path: {self.app_state.mp4_custom_path}")
            if self.app_state.mp4_custom_path and os.path.exists(self.app_state.mp4_custom_path):
                custom_renders = scan_exr_sequences(self.app_state.mp4_custom_path)
                self.log(f"MP4 Maker: Found {len(custom_renders)} renders in custom path")
                for render_seq in custom_renders:
                    self.app_state.mp4_renders.append(("custom", render_seq))

        # Populate list
        self.log(f"MP4 Maker: Total renders found: {len(self.app_state.mp4_renders)}")
        if len(self.app_state.mp4_renders) > 0:
            for subdir, render_seq in self.app_state.mp4_renders:
                full_path = str(render_seq).split("\\")
                display_name = full_path[-1]
                self.ui.MP4RendersList.addItem(display_name)
            self.ui.MP4RendersList.setEnabled(True)
        else:
            self.ui.MP4RendersList.addItem("No Renders Found")
            self.ui.MP4RendersList.setEnabled(False)

    def _on_render_selection_changed(self):
        """Update MP4 state when selected render changes."""
        from services.mp4_maker import get_output_filename

        sel0 = self.ui.MP4RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(self.app_state.mp4_renders):
            self.ui.MP4Generate.setEnabled(False)
            return

        # mp4_renders is a list of tuples: (subdir, render_seq)
        subdir, render_seq = self.app_state.mp4_renders[sel0]
        self.app_state.mp4_startframe = render_seq.start()
        self.app_state.mp4_endframe = render_seq.end()

        self.log(f"MP4 Maker: Selected render from '{subdir}' - frames {self.app_state.mp4_startframe} to {self.app_state.mp4_endframe}")

        # Automatically set output path to user's Videos folder
        framename = render_seq.frame(render_seq.start())
        filename = os.path.basename(framename)
        render_name = filename.split(".")[0]
        default_filename = get_output_filename(render_name, self.app_state.shot)
        videos_folder = os.path.join(os.path.expanduser("~"), "Videos")
        self.app_state.mp4_output_path = os.path.join(videos_folder, default_filename)

        # Update UI
        self.ui.MP4OutputPath.setText(self.app_state.mp4_output_path)
        self.ui.MP4OutputPath.setStyleSheet("color: white; font-size: 9pt;")

        # Enable generate button
        self.ui.MP4Generate.setEnabled(True)
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.pulse_button(self.ui.MP4Generate)

    def _on_browse_output(self):
        """Browse for MP4 output location."""
        from core.user_preferences import get_last_browse_directory, set_last_browse_directory
        from services.mp4_maker import get_output_filename

        # Get current render name for default filename
        sel0 = self.ui.MP4RendersList.currentRow()
        default_filename = f"{self.app_state.shot}_preview.mp4"

        if sel0 >= 0 and sel0 < len(self.app_state.mp4_renders):
            subdir, render_seq = self.app_state.mp4_renders[sel0]
            framename = render_seq.frame(render_seq.start())
            filename = os.path.basename(framename)
            render_name = filename.split(".")[0]
            default_filename = get_output_filename(render_name, self.app_state.shot)

        # Use last browsed directory or default to user's Videos folder
        last_dir = get_last_browse_directory("mp4_output")
        if not last_dir:
            last_dir = os.path.join(os.path.expanduser("~"), "Videos")

        # Open file dialog with default location
        output_file, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Save MP4 As",
            os.path.join(last_dir, default_filename),
            "MP4 Video (*.mp4)"
        )

        if output_file:
            self.app_state.mp4_output_path = output_file
            self.ui.MP4OutputPath.setText(output_file)
            self.ui.MP4OutputPath.setStyleSheet("color: white; font-size: 9pt;")
            set_last_browse_directory("mp4_output", os.path.dirname(output_file))

            # Enable generate button if render is selected
            if self.ui.MP4RendersList.currentRow() >= 0:
                self.ui.MP4Generate.setEnabled(True)
                if hasattr(self.main_window, 'animator'):
                    self.main_window.animator.pulse_button(self.ui.MP4Generate)

    def _on_generate_clicked(self):
        """Generate MP4 from selected render - runs on background thread."""
        from ui_components import Worker, StatusColors
        from services.mp4_maker import generate_mp4

        # Show status bar progress (no overlay so user can still interact)
        self.main_window.start_status_spinner()
        self.main_window.animator.update_status_animated(
            "🎬 MP4: Preparing to convert...",
            StatusColors.INFO
        )
        self.main_window.animator.animate_button_click(self.ui.MP4Generate)

        # Get selected render
        sel0 = self.ui.MP4RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(self.app_state.mp4_renders):
            self.main_window.stop_status_spinner()
            self.main_window.animator.update_status_animated(
                "No render selected",
                StatusColors.ERROR
            )
            return

        # Get render info
        self.main_window.animator.update_status_animated(
            "🎬 MP4: Analyzing render sequence...",
            StatusColors.INFO
        )

        subdir, render_seq = self.app_state.mp4_renders[sel0]
        framename = render_seq.frame(self.app_state.mp4_startframe)

        # Build input pattern for ffmpeg
        base_dir = os.path.dirname(framename)
        base_filename = os.path.basename(framename)
        parts = base_filename.split(".")
        if len(parts) < 3:
            self.main_window.stop_status_spinner()
            self.main_window.animator.update_status_animated(
                f"Unexpected filename format: {base_filename}",
                StatusColors.ERROR
            )
            return

        # Format: name.####.exr
        input_pattern = os.path.join(base_dir, f"{parts[0]}.%04d.exr")

        # Get settings
        self.main_window.animator.update_status_animated(
            "🎬 MP4: Configuring conversion settings...",
            StatusColors.INFO
        )

        quality_index = self._quality_index
        burn_in_timecode = self.ui.MP4BurnInTimecode.isChecked()

        def on_progress(progress, message):
            """Update UI with MP4 generation progress."""
            self.main_window.animator.update_status_animated(
                f"🎬 MP4: {message} ({progress}%)",
                StatusColors.INFO
            )

        def on_result(success):
            """Called when MP4 generation completes."""
            self.main_window.stop_status_spinner()
            if success:
                self.main_window.animator.update_status_animated(
                    f"✅ MP4 generated: {os.path.basename(self.app_state.mp4_output_path)}",
                    StatusColors.SUCCESS
                )
                self.main_window.animator.show_success("MP4 generation complete!")
            else:
                self.main_window.animator.update_status_animated(
                    "MP4 generation failed",
                    StatusColors.ERROR
                )

        def on_error(error_msg, traceback_str):
            """Called when MP4 generation fails."""
            self.main_window.stop_status_spinner()
            self.main_window.animator.update_status_animated(
                f"MP4 generation failed: {error_msg}",
                StatusColors.ERROR
            )
            self.log(f"MP4 generation error: {error_msg}")
            self.log(traceback_str)

        # Create worker and run MP4 generation on background thread
        # Store as instance attribute to prevent garbage collection
        self._mp4_worker = Worker(
            generate_mp4,
            input_pattern,
            self.app_state.mp4_output_path,
            self.app_state.mp4_startframe,
            self.app_state.mp4_endframe,
            quality_index=quality_index,
            burn_in_timecode=burn_in_timecode
        )
        self._mp4_worker.signals.result.connect(on_result)
        self._mp4_worker.signals.error.connect(on_error)
        self._mp4_worker.signals.progress.connect(on_progress)
        QThreadPool.globalInstance().start(self._mp4_worker)
