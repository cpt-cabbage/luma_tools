"""
rePublish tab module for Luma Tools.

Handles republishing renders to AYON.
"""

import os

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QFileDialog

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
        self.ui.RePublishTaskButton.clicked.connect(self._on_task_button_clicked)

    def initialize(self):
        """Initialize rePublish tab."""
        self.ui.RePublishPublish.setEnabled(False)

        # Task options
        self._task = "lighting"  # Default
        self._task_options = [
            ("lighting", "lighting"),
            ("compositing", "compositing"),
            ("fx", "fx"),
        ]
        self._update_task_button_text()

    def _update_task_button_text(self):
        """Update the task button text to show current selection."""
        self.ui.RePublishTaskButton.setText(f"Task: {self._task}")

    def _on_task_button_clicked(self):
        """Show popup menu with task options."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self.main_window)

        for label, value in self._task_options:
            action = menu.addAction(label)
            action.setData(value)
            if value == self._task:
                action.setCheckable(True)
                action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.RePublishTaskButton.mapToGlobal(
            self.ui.RePublishTaskButton.rect().bottomLeft()
        ))

        if action and action.data():
            self._task = action.data()
            self._update_task_button_text()

    def _on_source_changed(self):
        """Handle rePublish source type radio button changes."""
        is_custom = self.ui.RePublishUseCustom.isChecked()
        self.ui.RePublishBrowseCustomPath.setEnabled(is_custom)
        self._on_scan_renders_clicked()

    def _on_browse_custom_path(self):
        """Handle custom path browse button click for rePublish."""
        from core.settings_manager import get_last_browse_directory, set_last_browse_directory

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

        # Update searchpath with current version
        current_ver = self.ui.RePublishCurrentVer.value()
        if self.app_state.republish_searchpath:
            self.app_state.republish_searchpath = update_path_version(
                self.app_state.republish_searchpath, current_ver
            )
            self.ui.RePublishRenderPath.setText(self.app_state.republish_searchpath)

        # Update "For Comp" label if output_subdirectory is set
        if self.app_state.output_subdirectory:
            self.ui.RePublishUseForComp.setText(f"Denoised ({self.app_state.output_subdirectory.title()})")

        # Clear previous list
        self.ui.RePublishRendersList.clear()
        self.app_state.republish_renders = []

        # Determine which source to scan
        search_path = ""
        if self.ui.RePublishUseForComp.isChecked():
            if self.app_state.output_subdirectory:
                search_path = os.path.join(self.app_state.republish_searchpath, self.app_state.output_subdirectory)
            else:
                search_path = self.app_state.republish_searchpath
        elif self.ui.RePublishUseRaw.isChecked():
            search_path = self.app_state.republish_searchpath
        elif self.ui.RePublishUseCustom.isChecked():
            search_path = self.app_state.republish_custom_path

        if not search_path or not os.path.exists(search_path):
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

        # Auto-populate product name if empty
        if not self.ui.RePublishProductName.text():
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
        from ui_components import StatusColors

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
        self.main_window.start_status_spinner()
        self.main_window.animator.update_status_animated(
            "📦 AYON: Preparing files for publish...",
            StatusColors.INFO
        )

        # Start worker thread
        from ui_components import Worker
        worker = Worker(
            self._publish_worker,
            task,
            use_farm,
            product_name
        )
        worker.signals.result.connect(self._on_publish_complete)
        worker.signals.error.connect(self._on_publish_error)
        worker.signals.progress.connect(self._on_publish_progress)
        QThreadPool.globalInstance().start(worker)

    def _publish_worker(self, task, use_farm, product_name, progress_callback):
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

        # Extract project and shot from searchpath
        folder_path = convert_to_ayon_folder_path(self.app_state.shotpath, self.app_state.jobname)

        # Create metadata
        progress_callback(75, "Creating AYON metadata...")
        metadata = create_ayon_metadata(
            project_name=self.app_state.jobname,
            render_name=product_name,
            start_frame=self.app_state.republish_startframe,
            end_frame=self.app_state.republish_endframe,
            renders_path=base_render_path,
            folder_path=folder_path,
            task=task,
            user=self.app_state.user,
            output_subdirectory=output_subdirectory,
            working_dir=self.app_state.working_dir,
            render_file=render_file
        )

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
                project_name=self.app_state.jobname,
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
                self.app_state.jobname,
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
        from ui_components import StatusColors
        self.main_window.animator.update_status_animated(
            f"📦 AYON: {message}",
            StatusColors.INFO
        )

    def _on_publish_complete(self, result):
        """Handle successful publish completion."""
        from ui_components import StatusColors

        self.ui.RePublishPublish.setEnabled(True)
        self.ui.RePublishStatusLabel.setText(f"Status: {result['message']}")

        # Stop spinner and show success
        self.main_window.stop_status_spinner()
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.update_status_animated(
                f"✅ AYON: {result['message']}",
                StatusColors.SUCCESS
            )
            self.main_window.animator.show_success(result['message'])

    def _on_publish_error(self, error_tuple):
        """Handle publish errors."""
        from ui_components import StatusColors

        exc_type, exc_value, exc_traceback = error_tuple
        error_msg = f"Publish failed: {str(exc_value)}"

        self.ui.RePublishPublish.setEnabled(True)
        self.ui.RePublishStatusLabel.setText(f"Status: {error_msg}")

        # Stop spinner and show error
        self.main_window.stop_status_spinner()
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.update_status_animated(
                f"❌ AYON: {error_msg}",
                StatusColors.ERROR
            )

        self.log(f"Publish error: {exc_value}")
        import traceback
        traceback.print_exception(exc_type, exc_value, exc_traceback)
