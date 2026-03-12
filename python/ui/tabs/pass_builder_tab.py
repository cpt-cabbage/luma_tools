"""
Pass Builder tab module for Luma Tools.

Handles render scanning, pass detection, and pass building functionality.
"""

import os
import logging
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QThreadPool

from .base_tab import BaseTab, TabConfig



class PassBuilderTab(BaseTab):
    """Tab for building render passes."""

    TAB_CONFIG = TabConfig(ui_file="pass_builder.ui", tab_name="Pass Builder", tab_id="passbuilder")

    def connect_signals(self):
        """Connect pass builder tab signals."""
        self.ui.ScanRenders.clicked.connect(self._on_scan_renders_clicked)
        self.ui.RendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.BuildPasses.pressed.connect(self._on_build_passes_clicked)
        self.ui.CurrentVer.valueChanged.connect(self._on_scan_renders_clicked)
        # Build type button connected in initialize() via manager

    def initialize(self):
        """Initialize pass builder tab."""
        from ui_components import InlineSpinner
        from option_button import OptionButtonManager

        self.ui.BuildPasses.setEnabled(False)
        self._initial_scan_done = False

        # Create inline spinner for pass detection (will be positioned in showEvent)
        self.passes_spinner = InlineSpinner(self.ui.passesGroupBox, size=20)

        # Build type option manager
        self._build_type_manager = OptionButtonManager(
            button=self.ui.BuildTypeButton,
            options=[("Local", "local"), ("Farm", "farm")],
            initial_value="local",
            on_changed=lambda val: None,  # No additional action needed
            label_prefix="Location: ",
            parent_window=self.main_window
        )

        # Run initial scan if we have shot context
        if self.app_state.has_shot_context():
            self._run_initial_scan()

    def _run_initial_scan(self):
        """Find render directory and populate render path on startup."""
        from services.file_operations import get_task_directory, fast_scandir, find_renders, find_hip_files
        from core.config import RENDERS_SUBPATH
        from core.utils import truncate_at_suffix, get_trailing_number

        task = self.app_state.task
        task_dir = get_task_directory(self.app_state.shotpath, task)
        self.app_state.lookdev_dir = task_dir
        logging.info(f"Pass Builder: Task Dir: {task_dir}")

        if not os.path.isdir(task_dir):
            logging.warning(f"Pass Builder: Task directory not found: {task_dir}")
            return

        # Find render directory
        try:
            dirs = fast_scandir(task_dir)
        except Exception as e:
            logging.warning(f"Pass Builder: Error scanning {task_dir}: {e}")
            return

        render_folders = [d for d in dirs if RENDERS_SUBPATH in d]
        if not render_folders:
            logging.warning(f"Pass Builder: No render directory found in {task_dir}")
            return

        render_directory = truncate_at_suffix(render_folders[0], RENDERS_SUBPATH)
        logging.info(f"Pass Builder: Render directory: {render_directory}")

        # Find HIP files to match render versions
        hip_files = find_hip_files(task_dir, task)
        hip_file = ""
        if hip_files:
            hip_files = sorted(hip_files)
            hip_file = hip_files[0].rsplit("_", 1)[0]

        # Find render versions
        try:
            render_dirs = sorted(next(os.walk(render_directory))[1])
        except StopIteration:
            return

        # Filter by HIP file name if available
        if hip_file:
            matching = [d for d in render_dirs if hip_file in d]
            if matching:
                render_dirs = matching

        if not render_dirs:
            return

        # Find latest version with actual renders (denoised EXRs)
        latest_render = None
        for render_version in reversed(render_dirs):
            version_path = os.path.join(render_directory, render_version)
            test_renders = find_renders(version_path)
            if len(test_renders) > 0:
                latest_render = render_version
                break

        if not latest_render:
            # Fall back to latest directory even if empty
            latest_render = render_dirs[-1]

        # Populate state and UI
        self.app_state.latestrender = latest_render
        self.app_state.searchpath = os.path.join(render_directory, latest_render)
        self.app_state.working_dir = truncate_at_suffix(render_directory, task)

        self.ui.RenderPath.setText(self.app_state.searchpath)
        latest_ver = int(get_trailing_number(latest_render))
        self.ui.CurrentVer.setRange(0, latest_ver)
        self.ui.CurrentVer.setValue(latest_ver)

        logging.info(f"Pass Builder: Found render path: {self.app_state.searchpath}")
        self._initial_scan_done = True

    @property
    def _build_type(self):
        return self._build_type_manager.value

    def _on_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        from core.utils import update_path_version
        from services.file_operations import find_renders

        # Show scanning status
        self.show_status("Pass Builder: Scanning...", "info")

        self.ui.RendersList.clear()
        self.ui.Passes.clear()

        # Build search path
        self.app_state.searchpath = self.ui.RenderPath.text()
        newver = self.ui.CurrentVer.value()
        self.app_state.searchpath = update_path_version(self.app_state.searchpath, newver)
        self.ui.RenderPath.setText(self.app_state.searchpath)

        # Find renders
        self.app_state.renders = find_renders(self.app_state.searchpath)
        self.ui.BuildPasses.setEnabled(False)

        if len(self.app_state.renders) > 0:
            for render_seq in self.app_state.renders:
                self.ui.RendersList.addItem(os.path.basename(str(render_seq)))
            self.ui.RendersList.setEnabled(True)
            # Show result
            self.show_status(f"Found {len(self.app_state.renders)} render(s)", "info")
        else:
            self.ui.RendersList.addItem("No Renders Found")
            self.ui.RendersList.setEnabled(False)
            self.show_status("No renders found", "warning")

    def _on_render_selection_changed(self):
        """Update passes when selected render changes."""
        import os
        from services.render_service import get_pass_file_path

        sel0 = self.ui.RendersList.currentRow()
        if sel0 < 0 or sel0 >= len(self.app_state.renders):
            return

        index = sel0
        self.app_state.startframe = self.app_state.renders[index].start()
        self.app_state.endframe = self.app_state.renders[index].end()
        framename = self.app_state.renders[index].frame(self.app_state.startframe)
        filename = os.path.basename(framename)
        from core.utils import extract_render_name
        self.app_state.currentrender = extract_render_name(filename)
        denoisedpath = os.path.dirname(framename) + f"\\{filename}"

        # Find passes (shows inline spinner automatically)
        self.app_state.passesfile = get_pass_file_path(
            self.app_state.working_dir, self.app_state.currentrender
        )
        self._detect_passes(denoisedpath)

    def _detect_passes(self, render_file):
        """Detect passes in render file with spinner animation - runs on background thread."""
        from services.render_service import detect_passes

        self.ui.Passes.clear()

        # Show inline spinner and status
        self.passes_spinner.start()
        self.show_status("Detecting passes...", "info")

        def on_result(channels):
            """Called when pass detection completes."""
            from core.user_preferences import get_all_default_passes

            # Hide spinner
            self.passes_spinner.stop()

            # Store channels
            self.app_state.channels = channels

            # Get default passes that should be hidden from the list
            default_passes = get_all_default_passes()

            # Add passes to list (exclude default passes - they're auto-included)
            for key in channels.keys():
                if key not in default_passes:
                    self.ui.Passes.addItem(key)

            # Select previously saved passes (now that list is populated)
            self._select_saved_passes(self.app_state.passesfile)

            # Enable build button and show result
            if len(channels) >= 1:
                self.ui.BuildPasses.setEnabled(True)
                self.show_status(f"Found {len(channels)} passes", "info")
                self.pulse_button(self.ui.BuildPasses)
            else:
                self.ui.BuildPasses.setEnabled(False)

        def on_error(error_tuple):
            """Called when pass detection fails."""
            error_msg, _ = self.unpack_worker_error(error_tuple)
            self.passes_spinner.stop()
            logging.error(f"Pass detection error: {error_msg}")
            self.ui.BuildPasses.setEnabled(False)
            self.show_status(f"Pass detection failed: {error_msg}", "error")

        # Use BaseTab helper for worker management
        self.start_worker(detect_passes, render_file, on_result=on_result, on_error=on_error)

    def _select_saved_passes(self, passes_file):
        """Select previously saved passes in the UI."""
        from services.render_service import load_pass_config
        from core.user_preferences import get_all_default_passes

        selectedpasses = load_pass_config(passes_file)
        logging.info(f"Loaded passes from file: {selectedpasses}")

        # Select items in UI
        for i in range(self.ui.Passes.count()):
            item = self.ui.Passes.item(i)
            if item.text() in selectedpasses:
                item.setSelected(True)

    def _on_build_passes_clicked(self):
        """Build passes for the selected render."""
        from services.pass_builder import pass_builder
        from services.render_service import save_pass_config
        from core.user_preferences import get_all_default_passes
        from ui_components import Worker, StatusColors

        # Get selected passes from the list
        selected_items = self.ui.Passes.selectedItems()
        selected_pass_names = [item.text() for item in selected_items]

        # Add default passes (they're always included)
        default_passes = get_all_default_passes()
        all_pass_names = list(set(selected_pass_names + default_passes))

        # Build the full channel dict for selected passes (needed by OIIO)
        channels = self.app_state.channels
        final_channels = {k: channels[k] for k in all_pass_names if k in channels}

        # Save pass config as channel dict (consumed by AYON plugin's build_oiio_command)
        save_pass_config(self.app_state.passesfile, final_channels)
        logging.info(f"Building with passes: {list(final_channels.keys())}")

        # Get build location (Local or Farm)
        build_type = self._build_type
        use_farm = build_type == "farm"

        # Get display name for status
        build_type_display = "Local" if build_type == "local" else "Farm"

        # Show status bar progress (no overlay so user can still interact)
        self.update_status_with_spinner(
            f"Pass Builder: Building passes ({build_type_display})...",
            StatusColors.INFO
        )

        # Disable button to prevent double-clicks
        self.ui.BuildPasses.setEnabled(False)

        def do_build(progress_callback=None):
            """Run the pass building operation."""
            return pass_builder.build_passes(
                passes_file=self.app_state.passesfile,
                renders_path=self.app_state.searchpath,
                start_frame=self.app_state.startframe,
                end_frame=self.app_state.endframe,
                use_farm=use_farm,
                project_name=self.app_state.jobname,
                shot=self.app_state.shot,
                parent_job_id="NONE",
                task=self.app_state.task,
                user=self.app_state.user,
                output_subdirectory=self.app_state.output_subdirectory,
                do_publish=True,
                progress_callback=progress_callback
            )

        def on_progress(percent, message):
            """Update status bar with build progress."""
            self.update_status_with_spinner(
                f"Pass Builder: {message}",
                StatusColors.INFO
            )
            self.show_status(f"{message} ({percent}%)", "info")

        def on_result(result):
            """Called when build completes."""
            logging.info(f"Build completed: {result}")
            self.ui.BuildPasses.setEnabled(True)
            self.update_status_with_spinner(
                "Pass Builder: Build completed successfully",
                StatusColors.SUCCESS,
                start=False
            )
            self.show_status("Build completed successfully", "success")

        def on_error(error_tuple):
            """Called when build fails."""
            error_msg, _ = self.unpack_worker_error(error_tuple)
            logging.error(f"Build failed: {error_msg}")
            self.ui.BuildPasses.setEnabled(True)
            self.update_status_with_spinner(
                f"Pass Builder failed: {error_msg}",
                StatusColors.ERROR,
                start=False
            )
            self.show_status(f"Build failed: {error_msg}", "error")

        # Use BaseTab helper for worker management
        self.start_worker(do_build, on_result=on_result, on_error=on_error, on_progress=on_progress)
