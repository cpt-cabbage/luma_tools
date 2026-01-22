"""
Pass Builder tab module for Luma Tools.

Handles render scanning, pass detection, and pass building functionality.
"""

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QThreadPool

from .base_tab import BaseTab


class PassBuilderTab(BaseTab):
    """Tab for building render passes."""

    @property
    def ui_file(self) -> str:
        return "pass_builder.ui"

    @property
    def tab_name(self) -> str:
        return "Pass Builder"

    @property
    def tab_id(self) -> str:
        return "passbuilder"

    def connect_signals(self):
        """Connect pass builder tab signals."""
        self.ui.ScanRenders.clicked.connect(self._on_scan_renders_clicked)
        self.ui.RendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.BuildPasses.pressed.connect(self._on_build_passes_clicked)
        self.ui.CurrentVer.valueChanged.connect(self._on_scan_renders_clicked)
        self.ui.BuildTypeButton.clicked.connect(self._on_build_type_button_clicked)

    def initialize(self):
        """Initialize pass builder tab."""
        self.ui.BuildPasses.setEnabled(False)
        # Create inline spinner for pass detection (will be positioned in showEvent)
        from ui_components import InlineSpinner
        self.passes_spinner = InlineSpinner(self.ui.passesGroupBox, size=20)

        # Build type options
        self._build_type = "local"  # Default: local
        self._build_type_options = [
            ("Local", "local"),
            ("Farm", "farm"),
        ]
        self._update_build_type_button_text()

    def _update_build_type_button_text(self):
        """Update the build type button text to show current selection."""
        for label, mode in self._build_type_options:
            if mode == self._build_type:
                self.ui.BuildTypeButton.setText(f"Location: {label}")
                break

    def _on_build_type_button_clicked(self):
        """Show popup menu with build type options."""
        from small_widgets import show_popup_menu

        result = show_popup_menu(
            self.main_window,
            self.ui.BuildTypeButton,
            self._build_type_options,
            current=self._build_type
        )

        if result is not None:
            self._build_type = result
            self._update_build_type_button_text()

    def _on_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        from core.utils import update_path_version
        from services.file_operations import find_renders

        # Show scanning status
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.show_info("Pass Builder: Scanning...")

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
                self.ui.RendersList.addItem(str(render_seq).split("\\")[-1])
            self.ui.RendersList.setEnabled(True)
            # Show result
            if hasattr(self.main_window, 'animator'):
                self.main_window.animator.show_info(f"Found {len(self.app_state.renders)} render(s)")
        else:
            self.ui.RendersList.addItem("No Renders Found")
            self.ui.RendersList.setEnabled(False)
            if hasattr(self.main_window, 'animator'):
                self.main_window.animator.show_warning("No renders found")

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
        self.app_state.currentrender = filename.split(".")[0]
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
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.show_info("Detecting passes...")

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
                if hasattr(self.main_window, 'animator'):
                    self.main_window.animator.show_info(f"Found {len(channels)} passes")
                    self.main_window.animator.pulse_button(self.ui.BuildPasses)
            else:
                self.ui.BuildPasses.setEnabled(False)

        def on_error(error_msg, traceback_str):
            """Called when pass detection fails."""
            self.passes_spinner.stop()
            self.log(f"Pass detection error: {error_msg}")
            self.ui.BuildPasses.setEnabled(False)

        # Use BaseTab helper for worker management
        self.start_worker(detect_passes, render_file, on_result=on_result, on_error=on_error)

    def _select_saved_passes(self, passes_file):
        """Select previously saved passes in the UI."""
        from services.render_service import load_pass_config
        from core.user_preferences import get_all_default_passes

        selectedpasses = load_pass_config(passes_file)
        self.log(f"Loaded passes from file: {selectedpasses}")

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
        selected_passes = [item.text() for item in selected_items]

        # Add default passes (they're always included)
        default_passes = get_all_default_passes()
        all_passes = list(set(selected_passes + default_passes))

        # Save pass selection for this render
        save_pass_config(self.app_state.passesfile, selected_passes)
        self.log(f"Building with passes: {all_passes}")

        # Get build location (Local or Farm)
        build_type = self._build_type

        # Get display name for status
        build_type_display = "Local" if build_type == "local" else "Farm"

        # Show status bar progress (no overlay so user can still interact)
        self.update_status_with_spinner(
            f"🔧 Pass Builder: Building passes ({build_type_display})...",
            StatusColors.INFO
        )

        def do_build():
            """Run the pass building operation."""
            return pass_builder(
                self.app_state.renders[self.ui.RendersList.currentRow()],
                self.app_state.channels,
                all_passes,
                self.app_state.startframe,
                self.app_state.endframe,
                build_type
            )

        def on_result(result):
            """Called when build completes."""
            self.log(f"Build completed: {result}")
            self.update_status_with_spinner(
                "✅ Pass Builder: Build completed successfully",
                StatusColors.SUCCESS,
                start=False
            )
            self.main_window.animator.show_success("Build completed successfully")

        def on_error(error_msg, traceback_str):
            """Called when build fails."""
            self.log(f"Build failed: {error_msg}")
            self.update_status_with_spinner(
                f"Pass Builder failed: {error_msg}",
                StatusColors.ERROR,
                start=False
            )
            self.main_window.animator.show_error(f"Build failed: {error_msg}")

        # Use BaseTab helper for worker management
        self.start_worker(do_build, on_result=on_result, on_error=on_error)
