"""
MP4 Maker tab module for Luma Tools.

Handles MP4 generation from EXR sequences.
"""

import os

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QTimer

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
        # Source and quality buttons connected in initialize() via managers
        self.ui.MP4BrowseCustomPath.clicked.connect(self._on_browse_custom_path)
        self.ui.MP4RendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.MP4BrowseOutput.clicked.connect(self._on_browse_output)
        self.ui.MP4Generate.clicked.connect(self._on_generate_clicked)

    def initialize(self):
        """Initialize MP4 maker tab."""
        from option_button import OptionButtonManager, IndexedOptionButtonManager

        self.ui.MP4Generate.setEnabled(False)

        # Source option manager with dynamic label function
        def get_source_label(value):
            labels = {"for_comp": "For Comp", "raw": "Raw", "custom": "Custom"}
            if value == "for_comp" and self.app_state.output_subdirectory:
                return self.app_state.output_subdirectory.title()
            return labels.get(value, value)

        self._source_manager = OptionButtonManager(
            button=self.ui.MP4SourceButton,
            options=[("For Comp", "for_comp"), ("Raw", "raw"), ("Custom", "custom")],
            initial_value="for_comp",
            on_changed=self._on_source_changed,
            label_prefix="Source: ",
            parent_window=self.main_window,
            label_func=get_source_label
        )

        # Quality option manager (indexed options)
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

    # Properties for backward compatibility with existing code
    @property
    def _source(self):
        return self._source_manager.value if hasattr(self, '_source_manager') else "for_comp"

    @property
    def _quality_index(self):
        return self._quality_manager.index if hasattr(self, '_quality_manager') else 0

    def _update_source_button_text(self):
        """Refresh source button text (delegates to manager)."""
        if hasattr(self, '_source_manager'):
            self._source_manager.refresh_text()

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
        from file_dialogs import browse_directory_with_memory

        custom_dir = browse_directory_with_memory(
            self.main_window,
            context="mp4_custom",
            title="Select Directory with Image Sequence",
            fallback_path=os.path.join(os.path.expanduser("~"), "Videos")
        )

        if custom_dir:
            self.app_state.mp4_custom_path = custom_dir
            self.ui.MP4CustomPathLabel.setText(f"Custom path: {custom_dir}")
            self.ui.MP4CustomPathLabel.setStyleSheet("color: white; font-size: 9pt;")
            self.log(f"MP4 Maker: Custom path set to: {custom_dir}")
            self.show_status(f"Custom: {os.path.basename(custom_dir)}", "info")
            self._on_scan_renders_clicked()

    def _on_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        from core.utils import update_path_version, scan_exr_sequences

        # Show scanning status
        self.show_status("MP4: Scanning sequences...", "info")

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
            # Show result
            self.show_status(f"Found {len(self.app_state.mp4_renders)} sequence(s)", "info")
        else:
            self.ui.MP4RendersList.addItem("No Renders Found")
            self.ui.MP4RendersList.setEnabled(False)
            self.show_status("No sequences found", "warning")

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
        from core.utils import extract_render_name
        render_name = extract_render_name(filename)
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
        from file_dialogs import save_file_with_memory
        from services.mp4_maker import get_output_filename

        # Get current render name for default filename
        sel0 = self.ui.MP4RendersList.currentRow()
        default_filename = f"{self.app_state.shot}_preview.mp4"

        if sel0 >= 0 and sel0 < len(self.app_state.mp4_renders):
            subdir, render_seq = self.app_state.mp4_renders[sel0]
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
            fallback_path=os.path.join(os.path.expanduser("~"), "Videos")
        )

        if output_file:
            self.app_state.mp4_output_path = output_file
            self.ui.MP4OutputPath.setText(output_file)
            self.ui.MP4OutputPath.setStyleSheet("color: white; font-size: 9pt;")

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
        self.update_status_with_spinner(
            "🎬 MP4: Preparing to convert...",
            StatusColors.INFO
        )
        self.main_window.animator.animate_button_click(self.ui.MP4Generate)

        # Get selected render
        sel0 = self.ui.MP4RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(self.app_state.mp4_renders):
            self.update_status_with_spinner(
                "No render selected",
                StatusColors.ERROR,
                start=False
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
            self.update_status_with_spinner(
                f"Unexpected filename format: {base_filename}",
                StatusColors.ERROR,
                start=False
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
            if success:
                self.update_status_with_spinner(
                    f"✅ MP4 generated: {os.path.basename(self.app_state.mp4_output_path)}",
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
            self.log(f"MP4 generation error: {error_msg}")
            self.log(traceback_str)

        # Use BaseTab helper for worker management
        self.start_worker(
            generate_mp4,
            input_pattern,
            self.app_state.mp4_output_path,
            self.app_state.mp4_startframe,
            self.app_state.mp4_endframe,
            quality_index=quality_index,
            burn_in_timecode=burn_in_timecode,
            on_result=on_result,
            on_error=on_error,
            on_progress=on_progress
        )
