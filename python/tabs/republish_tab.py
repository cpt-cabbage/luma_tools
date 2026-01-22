"""
rePublish tab module for Luma Tools.

Handles republishing renders to AYON.
"""

import os

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QFileDialog

from .base_tab import BaseTab
from ui_components import StatusColors


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
        self.ui.RePublishSourceButton.clicked.connect(self._on_source_button_clicked)
        self.ui.RePublishBrowseCustomPath.clicked.connect(self._on_browse_custom_path)
        self.ui.RePublishRendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.RePublishPublish.clicked.connect(self._on_publish_clicked)
        self.ui.RePublishTaskButton.clicked.connect(self._on_task_button_clicked)

    def initialize(self):
        """Initialize rePublish tab."""
        self.ui.RePublishPublish.setEnabled(False)

        # Source options (label, value)
        self._source = "for_comp"  # Default
        self._source_options = [
            ("For Comp", "for_comp"),
            ("Raw", "raw"),
            ("Custom", "custom"),
        ]
        self._update_source_button_text()

        # Task options
        self._task = "lighting"  # Default
        self._task_options = [
            ("lighting", "lighting"),
            ("compositing", "compositing"),
            ("fx", "fx"),
        ]
        self._update_task_button_text()

        # In standalone mode, only allow custom directory selection
        if self.app_state.standalone_mode:
            self._source = "custom"
            self._update_source_button_text()
            self.ui.RePublishBrowseCustomPath.setVisible(True)
            print("Republish tab: Standalone mode - only custom directory selection allowed")

    def _update_task_button_text(self):
        """Update the task button text to show current selection."""
        self.ui.RePublishTaskButton.setText(f"Task: {self._task}")

    def _update_source_button_text(self):
        """Update the source button text to show current selection."""
        # Find label for current source value
        label = next((l for l, v in self._source_options if v == self._source), self._source)
        # Update with output_subdirectory if available and using for_comp
        if self._source == "for_comp" and self.app_state.output_subdirectory:
            label = self.app_state.output_subdirectory.title()
        self.ui.RePublishSourceButton.setText(f"Source: {label}")

    def _on_source_button_clicked(self):
        """Show popup menu with source options."""
        from small_widgets import show_popup_menu

        # Build display options with filtering and dynamic labels
        display_options = []
        for label, value in self._source_options:
            # In standalone mode, only show Custom option
            if self.app_state.standalone_mode and value != "custom":
                continue

            # Update label for for_comp if output_subdirectory is set
            display_label = label
            if value == "for_comp" and self.app_state.output_subdirectory:
                display_label = self.app_state.output_subdirectory.title()
            display_options.append((display_label, value))

        result = show_popup_menu(
            self.main_window,
            self.ui.RePublishSourceButton,
            display_options,
            current=self._source
        )

        if result is not None:
            self._source = result
            self._update_source_button_text()
            self._on_source_changed()

    def _on_task_button_clicked(self):
        """Show popup menu with task options."""
        from small_widgets import show_popup_menu

        result = show_popup_menu(
            self.main_window,
            self.ui.RePublishTaskButton,
            self._task_options,
            current=self._task
        )

        if result is not None:
            self._task = result
            self._update_task_button_text()

    def _on_source_changed(self):
        """Handle rePublish source type changes."""
        is_custom = self._source == "custom"

        # Show/hide browse button and custom path controls based on source type
        self.ui.RePublishBrowseCustomPath.setVisible(is_custom)
        self.ui.RePublishCustomPathLabel.setVisible(is_custom)
        self.ui.RePublishUseCurrentTask.setVisible(is_custom)

        # Hide version spinbox when using custom path (not relevant for custom directories)
        self.ui.RePublishVersionLabel.setVisible(not is_custom)
        self.ui.RePublishCurrentVer.setVisible(not is_custom)

        # Enable "Use Current AYON Task" only when custom path is selected AND we have shot context
        if is_custom:
            can_use_current_task = self.app_state.has_shot_context()
            self.ui.RePublishUseCurrentTask.setEnabled(can_use_current_task)
            if not can_use_current_task:
                self.ui.RePublishUseCurrentTask.setChecked(False)
                self.ui.RePublishUseCurrentTask.setToolTip(
                    "Not available - no AYON task context (running in standalone mode)"
                )
            else:
                self.ui.RePublishUseCurrentTask.setToolTip(
                    "When enabled, publishes to the current AYON task context instead of inferring from the custom path"
                )

        self._on_scan_renders_clicked()

    def _on_browse_custom_path(self):
        """Handle custom path browse button click for rePublish."""
        from core.user_preferences import get_last_browse_directory, set_last_browse_directory

        default_path = get_last_browse_directory("republish_custom")
        if not default_path:
            default_path = os.path.join(os.path.expanduser("~"), "Videos")
            if not os.path.exists(default_path):
                default_path = os.path.expanduser("~")

        custom_dir = QFileDialog.getExistingDirectory(
            self.main_window,
            "Select Custom Render Directory",
            default_path,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if custom_dir:
            self.app_state.republish_custom_path = custom_dir
            self.ui.RePublishCustomPathLabel.setText(f"Custom path: {custom_dir}")
            self.ui.RePublishCustomPathLabel.setStyleSheet("color: white; font-size: 9pt;")
            set_last_browse_directory("republish_custom", custom_dir)
            self._on_scan_renders_clicked()

    def _on_scan_renders_clicked(self):
        """Scan for renders to republish based on selected source type."""
        from core.utils import update_path_version, scan_exr_sequences

        # In standalone mode, only custom path is allowed
        if self.app_state.standalone_mode and self._source != "custom":
            self.ui.RePublishStatusLabel.setText("Status: Use custom directory in standalone mode")
            return

        # Update searchpath with current version (skip in standalone mode if using custom)
        current_ver = self.ui.RePublishCurrentVer.value()
        if not self.app_state.standalone_mode and self.app_state.republish_searchpath:
            self.app_state.republish_searchpath = update_path_version(
                self.app_state.republish_searchpath, current_ver
            )
            self.ui.RePublishRenderPath.setText(self.app_state.republish_searchpath)

        # Clear previous list
        self.ui.RePublishRendersList.clear()
        self.app_state.republish_renders = []

        # Determine which source to scan
        search_path = ""
        if self._source == "for_comp":
            if self.app_state.output_subdirectory:
                search_path = os.path.join(self.app_state.republish_searchpath, self.app_state.output_subdirectory)
            else:
                search_path = self.app_state.republish_searchpath
        elif self._source == "raw":
            search_path = self.app_state.republish_searchpath
        elif self._source == "custom":
            search_path = self.app_state.republish_custom_path

        if not search_path or not os.path.exists(search_path):
            if self.app_state.standalone_mode:
                self.ui.RePublishStatusLabel.setText("Status: Please browse for a directory")
            else:
                self.ui.RePublishStatusLabel.setText("Status: Invalid path")
            return

        # Find EXR sequences using scan_exr_sequences
        try:
            sequences = scan_exr_sequences(search_path)

            for seq in sequences:
                # Extract subdirectory name if applicable
                seq_path = str(seq)
                rel_path = os.path.relpath(os.path.dirname(seq_path), search_path)
                subdir = rel_path if rel_path != "." else ""

                # Store tuple of (subdir, sequence_object)
                self.app_state.republish_renders.append((subdir, seq))

                # Display name
                if subdir and subdir != ".":
                    display_name = f"{subdir}/{seq.basename()}"
                else:
                    display_name = seq.basename()

                self.ui.RePublishRendersList.addItem(display_name)

            # Update status
            count = len(self.app_state.republish_renders)
            self.ui.RePublishStatusLabel.setText(f"Status: Found {count} render sequence(s)")

        except Exception as e:
            self.log(f"Error scanning renders for republish: {e}")
            self.ui.RePublishStatusLabel.setText(f"Status: Scan error - {str(e)}")

    def _on_render_selection_changed(self):
        """Handle render selection in rePublish list."""
        selected_items = self.ui.RePublishRendersList.selectedItems()
        if not selected_items:
            self.ui.RePublishPublish.setEnabled(False)
            self.app_state.republish_selected_render = None
            return

        # Get selected index
        selected_idx = self.ui.RePublishRendersList.currentRow()
        if selected_idx < 0 or selected_idx >= len(self.app_state.republish_renders):
            return

        # Get the fileseq object
        _, seq = self.app_state.republish_renders[selected_idx]
        self.app_state.republish_selected_render = seq

        # Extract frame range
        self.app_state.republish_startframe = seq.start()
        self.app_state.republish_endframe = seq.end()

        # Update status with frame range
        self.ui.RePublishStatusLabel.setText(
            f"Status: Selected {seq.basename()}\n"
            f"Frames: {self.app_state.republish_startframe}-{self.app_state.republish_endframe}"
        )

        # Set product name from render
        base = seq.basename()
        parts = [p for p in base.split('.') if p and not all(c == '#' for c in p)]
        render_name = parts[0] if parts else base.replace("#", "").strip(".")
        self.ui.RePublishProductName.setText(render_name)

        # Enable publish button
        self.ui.RePublishPublish.setEnabled(True)
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.pulse_button(self.ui.RePublishPublish)

    def _on_publish_clicked(self):
        """Handle publish to AYON button click."""
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.animate_button_click(self.ui.RePublishPublish)

        # Validate selection
        if not self.app_state.republish_selected_render:
            self.ui.RePublishStatusLabel.setText("Status: No render selected")
            return

        # Get options
        task = self._task
        use_farm = self.ui.RePublishUseFarm.isChecked()
        product_name = self.ui.RePublishProductName.text().strip()

        if not product_name:
            base = self.app_state.republish_selected_render.basename()
            parts = [p for p in base.split('.') if p and not all(c == '#' for c in p)]
            product_name = parts[0] if parts else base.replace("#", "").strip(".")

        # Disable button during processing
        self.ui.RePublishPublish.setEnabled(False)

        # Show status bar progress
        self.update_status_with_spinner(

            "AYON: Preparing files for publish...",

            StatusColors.INFO

        )

        # Check if user wants to use current AYON task context
        use_current_task = (
            self._source == "custom" and
            self.ui.RePublishUseCurrentTask.isChecked() and
            self.app_state.has_shot_context()
        )

        # Start worker thread - store reference to prevent garbage collection
        from ui_components import Worker
        self._publish_worker_ref = Worker(
            self._publish_worker,
            task,
            use_farm,
            product_name,
            use_current_task
        )
        self._publish_worker_ref.signals.result.connect(self._on_publish_complete)
        self._publish_worker_ref.signals.error.connect(self._on_publish_error)
        self._publish_worker_ref.signals.progress.connect(self._on_publish_progress)
        self._publish_worker_ref.signals.finished.connect(self._on_publish_finished)
        QThreadPool.globalInstance().start(self._publish_worker_ref)

    def _publish_worker(self, task, use_farm, product_name, use_current_task, progress_callback):
        """Worker thread function for publishing to AYON."""
        from ayon.service import (
            convert_to_ayon_folder_path, create_ayon_metadata, write_metadata_file,
            publish_to_ayon_local, submit_ayon_publish_to_deadline
        )

        # Get render path information
        seq = self.app_state.republish_selected_render
        first_frame = seq.frame(self.app_state.republish_startframe)
        source_dir = os.path.dirname(first_frame)

        # AYON publishes from work folder to publish folder automatically
        # We just need to point metadata to the correct staging directory (source_dir)

        # Determine base render path and output subdirectory
        # Example source_dir: "V:/project/shots/.../work/lighting/img/renders/v001/for_comp"
        # We need:
        #   renders_path = "V:/project/shots/.../work/lighting/img/renders/v001"
        #   output_subdirectory = "for_comp"

        source_basename = os.path.basename(source_dir)

        # Check if we're in a subdirectory (for_comp, denoised, raw, etc.)
        if source_basename in ['for_comp', 'denoised', 'raw']:
            # We're in a subdirectory
            base_render_path = os.path.dirname(source_dir)
            output_subdirectory = source_basename
        else:
            # We're directly in the version folder
            base_render_path = source_dir
            output_subdirectory = ""

        # Debug logging
        print(f"Source directory: {source_dir}")
        print(f"Base render path: {base_render_path}")
        print(f"Output subdirectory: {output_subdirectory}")

        progress_callback(50, "Preparing metadata for AYON publish...")

        # Get the base filename pattern for the sequence
        base_name = seq.basename()
        frame_padding = len(seq.frameSet().frameRange().split("-")[0])
        render_file = f"{base_name.replace('#' * frame_padding, f'%0{frame_padding}d')}"

        # Determine project name and folder path
        # Either use current AYON task context or extract from the custom path

        if use_current_task:
            # Use current AYON task context directly (user explicitly requested this)
            project_name = self.app_state.jobname
            shot_path_for_conversion = self.app_state.shotpath
            print(f"[Use Current Task] Using current AYON context instead of parsing path")
        else:
            # Extract project name and folder path from the actual source directory
            # This handles both standard workflow and custom directory selection
            # Example: V:/LieweHeksie/shots/.../work/... -> project=LieweHeksie, folder=/shots/.../shotname

            # Normalize path for parsing
            normalized_source = source_dir.replace("\\", "/")

            # Try to extract project name from path
            path_parts = normalized_source.split("/")

            # Find project name - it's typically after the drive letter and before "shots" or "assets"
            project_name = self.app_state.jobname  # Default to current project
            shot_path_for_conversion = None

            for i, part in enumerate(path_parts):
                if part in ["shots", "assets"] and i > 0:
                    # Project name is the part before shots/assets
                    project_name = path_parts[i - 1]
                    # Build the shot path up to /work
                    if "work" in path_parts:
                        work_idx = path_parts.index("work")
                        shot_path_for_conversion = "/".join(path_parts[:work_idx])
                    break

            # If we couldn't extract from path, fall back to app_state
            if not shot_path_for_conversion:
                shot_path_for_conversion = self.app_state.shotpath
                project_name = self.app_state.jobname

        folder_path = convert_to_ayon_folder_path(shot_path_for_conversion, project_name)

        print(f"Detected project: {project_name}")
        print(f"Detected folder path: {folder_path}")

        # Determine working_dir from the shot path
        if "work" in shot_path_for_conversion:
            working_dir = shot_path_for_conversion.split("work")[0] + "work"
        else:
            working_dir = self.app_state.working_dir or shot_path_for_conversion

        # Create metadata
        progress_callback(75, "Creating AYON metadata...")
        metadata = create_ayon_metadata(
            project_name=project_name,
            render_name=product_name,
            start_frame=self.app_state.republish_startframe,
            end_frame=self.app_state.republish_endframe,
            renders_path=base_render_path,
            folder_path=folder_path,
            task=task,
            user=self.app_state.user,
            output_subdirectory=output_subdirectory,
            working_dir=working_dir,
            render_file=render_file
        )

        # Fix farm flag based on publish mode
        # create_ayon_metadata() sets "farm": True by default, but for local publish we need False
        if not use_farm and "instances" in metadata and len(metadata["instances"]) > 0:
            metadata["instances"][0]["farm"] = False
            print(f"Set farm flag to False for local publish")

        # Write metadata file to source directory
        metadata_filename = f"ayon_{product_name}.json"
        metadata_path = os.path.join(source_dir, metadata_filename)
        metadata_path = write_metadata_file(metadata, metadata_path)

        if not metadata_path:
            raise Exception("Failed to write metadata file")

        # Publish
        progress_callback(85, f"{'Submitting to farm' if use_farm else 'Publishing locally'}...")

        if use_farm:
            # Submit to Deadline with correct signature
            job_id = submit_ayon_publish_to_deadline(
                project_name=project_name,
                render_name=product_name,
                render_file=render_file,
                metadata_path=metadata_path,
                folder_path=folder_path,
                task=task,
                user=self.app_state.user,
                build_job_id=None
            )

            if not job_id:
                raise Exception("Failed to submit to Deadline")

            progress_callback(100, "Publish job submitted to farm")
            return {"success": True, "message": f"Published to farm! Job ID: {job_id}", "job_id": job_id}
        else:
            # Publish locally with correct arguments
            success = publish_to_ayon_local(
                metadata_path,
                project_name,
                folder_path,
                task,
                self.app_state.user
            )

            if not success:
                raise Exception("Local publish failed")

            progress_callback(100, "Published successfully")
            return {"success": True, "message": f"Published: {product_name}"}

    def _on_publish_progress(self, progress, message):
        """Handle progress updates from worker."""
        self.main_window.animator.update_status_animated(
            f"AYON: {message}",
            StatusColors.INFO
        )

    def _on_publish_complete(self, result):
        """Handle successful publish completion."""
        self.ui.RePublishPublish.setEnabled(True)
        self.ui.RePublishStatusLabel.setText(f"Status: {result['message']}")

        # Stop spinner and show success
        self.main_window.stop_status_spinner()
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.update_status_animated(
                f"AYON: {result['message']}",
                StatusColors.SUCCESS
            )
            self.main_window.animator.show_success(result['message'])

    def _on_publish_error(self, error_msg, traceback_str):
        """Handle publish errors."""
        full_error_msg = f"Publish failed: {error_msg}"

        self.ui.RePublishPublish.setEnabled(True)
        self.ui.RePublishStatusLabel.setText(f"Status: {full_error_msg}")

        # Stop spinner and show error
        self.main_window.stop_status_spinner()
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.update_status_animated(
                f"AYON: {full_error_msg}",
                StatusColors.ERROR
            )

        self.log(f"Publish error: {error_msg}")
        if traceback_str:
            print(traceback_str)

    def _on_publish_finished(self):
        """Handle worker finished - ensures cleanup happens."""
        # Re-enable button and stop spinner as fallback
        self.ui.RePublishPublish.setEnabled(True)
        self.main_window.stop_status_spinner()
        # Clear worker reference
        self._publish_worker_ref = None
