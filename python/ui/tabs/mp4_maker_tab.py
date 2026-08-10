"""
MP4 Maker tab module for Luma Tools.

Handles MP4 generation from EXR sequences.
"""

import os
import logging
import threading

from core.config import DEFAULT_VIDEOS_DIR, UIStyles
from ui_components import StatusColors
from .base_tab import BaseTab, TabConfig
from .mixins.render_scan_mixin import RenderScanMixin

logger = logging.getLogger(__name__)


class MP4MakerTab(RenderScanMixin, BaseTab):
    """Tab for generating MP4 files from render sequences."""

    TAB_CONFIG = TabConfig(ui_file="mp4_maker.ui", tab_name="MP4 Maker", tab_id="mp4maker")

    # RenderScanMixin widget configuration
    _render_list_widget = "MP4RendersList"
    _render_path_widget = "MP4RenderPath"
    _version_widget = "MP4CurrentVer"
    _version_label_widget = "mp4VersionLabel"
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
        # Publish to AYON checkbox signals
        self.ui.MP4PublishToAyon.stateChanged.connect(self._on_publish_to_ayon_changed)
        self.ui.MP4PublishOnFarm.stateChanged.connect(self._on_publish_on_farm_changed)

    def initialize(self):
        """Initialize MP4 maker tab."""
        from option_button import IndexedOptionButtonManager
        from core.settings_manager import safe_get_setting

        self.ui.MP4Generate.setEnabled(False)

        # Source manager from mixin
        self._init_source_manager()

        # Publish source widgets (product/version combos)
        self._init_publish_widgets(self.ui.MP4CurrentVer)

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
        # (registry default is True, fall through to it for first-run users)
        add_to_gallery = safe_get_setting("mp4_maker_add_to_gallery", True)
        self.ui.MP4AddToGallery.setChecked(add_to_gallery)

        # Load Publish to AYON checkbox states
        publish_to_ayon = safe_get_setting("mp4_maker_publish_to_ayon", False)
        publish_on_farm = safe_get_setting("mp4_maker_publish_on_farm", False)
        self.ui.MP4PublishToAyon.setChecked(publish_to_ayon)
        self.ui.MP4PublishOnFarm.setChecked(publish_on_farm)
        self.ui.MP4PublishOnFarm.setVisible(publish_to_ayon)
        self._update_publish_availability()

        # AYON branding for publish checkboxes
        self.apply_ayon_checkbox_style(self.ui.MP4PublishToAyon)
        self.apply_ayon_checkbox_style(self.ui.MP4PublishOnFarm)

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

        logger.info(f"MP4 Maker: Selected render from '{subdir}' - frames {self.app_state.mp4_startframe} to {self.app_state.mp4_endframe}")

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
        """Generate MP4 from selected render, or cancel if already generating."""

        # If already generating, cancel the operation
        if getattr(self, '_is_generating', False):
            cancel_event = getattr(self, '_cancel_event', None)
            if cancel_event:
                cancel_event.set()
            self.ui.MP4Generate.setEnabled(False)
            self.show_status("Cancelling MP4 generation...", "warning")
            return

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
        if self.animator:
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

        # Format: name.####.ext — derive padding and extension from actual filename
        ext = parts[-1] if len(parts) >= 3 else "exr"
        actual_padding = len(parts[1]) if len(parts) >= 3 else 4
        input_pattern = os.path.join(base_dir, f"{parts[0]}.%0{actual_padding}d.{ext}")

        # Get settings
        if self.animator:
            self.animator.update_status_animated(
                "MP4: Configuring conversion settings...",
                StatusColors.INFO
            )

        quality_index = self._quality_index
        burn_in_timecode = self.ui.MP4BurnInTimecode.isChecked()

        # Set up cancellation
        self._cancel_event = threading.Event()
        self._is_generating = True
        cancel_event = self._cancel_event

        # Switch button to Cancel mode
        self.ui.MP4Generate.setText("Cancel")

        def on_progress(progress, message):
            """Update UI with MP4 generation progress."""
            if self.animator:
                self.animator.update_status_animated(
                    f"MP4: {message} ({progress}%)",
                    StatusColors.INFO
                )

        want_gallery = self.ui.MP4AddToGallery.isChecked()
        want_publish = self.ui.MP4PublishToAyon.isChecked() and self.ui.MP4PublishToAyon.isEnabled()

        def _reset_button():
            """Reset button to Generate state."""
            self._is_generating = False
            self.ui.MP4Generate.setText("Generate MP4")
            self.ui.MP4Generate.setEnabled(True)

        def on_result(success):
            """Called when MP4 generation completes."""
            _reset_button()
            if success:
                if want_gallery:
                    self.update_status_with_spinner(
                        "MP4 generated. Copying to gallery...",
                        StatusColors.INFO,
                        start=True
                    )
                    self._copy_to_gallery(input_pattern, publish_after=want_publish)
                elif want_publish:
                    self.update_status_with_spinner(
                        "MP4 generated. Publishing to AYON...",
                        StatusColors.INFO,
                        start=True
                    )
                    self._publish_mp4_to_ayon()
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
            """Called when MP4 generation fails or is cancelled."""
            _reset_button()

            if cancel_event.is_set():
                self.update_status_with_spinner(
                    "MP4: Generation cancelled",
                    StatusColors.WARNING,
                    start=False
                )
                self.show_status("MP4 generation cancelled", "warning")
                return

            self.update_status_with_spinner(
                f"MP4 generation failed: {error_msg}",
                StatusColors.ERROR,
                start=False
            )
            logger.error(f"MP4 generation error: {error_msg}")
            logger.debug(traceback_str)

        # Use BaseTab helper for worker management
        try:
            self.start_worker(
                generate_mp4,
                input_pattern,
                self.app_state.mp4_output_path,
                self.app_state.mp4_startframe,
                self.app_state.mp4_endframe,
                worker_kwargs={
                    "quality_index": quality_index,
                    "burn_in_timecode": burn_in_timecode,
                    "cancel_event": cancel_event,
                },
                on_result=on_result,
                on_error=on_error,
                on_progress=on_progress,
            )
        except Exception:
            _reset_button()
            raise

    def _on_add_to_gallery_changed(self, state):
        """Save Add to Gallery checkbox state to user settings."""
        from core.settings_manager import safe_set_setting
        from PySide6.QtCore import Qt
        safe_set_setting("mp4_maker_add_to_gallery", state == Qt.Checked)

    def _update_publish_availability(self):
        """Enable/disable publish checkboxes based on AYON/Deadline availability and context."""
        from ayon.service import AYON_AVAILABLE, DEADLINE_AVAILABLE

        # Publish to AYON requires AYON and AYON context (shot or asset)
        ayon_enabled = AYON_AVAILABLE and self.app_state.has_ayon_context()
        self.ui.MP4PublishToAyon.setEnabled(ayon_enabled)
        if not AYON_AVAILABLE:
            self.ui.MP4PublishToAyon.setToolTip("AYON is not available in this environment")
        elif not self.app_state.has_ayon_context():
            self.ui.MP4PublishToAyon.setToolTip("Publish requires AYON context (launch from AYON)")
        else:
            self.ui.MP4PublishToAyon.setToolTip("Publish the generated MP4 as a review file to AYON")

        # Publish on Farm additionally requires Deadline
        farm_enabled = ayon_enabled and DEADLINE_AVAILABLE
        self.ui.MP4PublishOnFarm.setEnabled(farm_enabled)
        if not DEADLINE_AVAILABLE:
            self.ui.MP4PublishOnFarm.setToolTip("Deadline is not available in this environment")
        else:
            self.ui.MP4PublishOnFarm.setToolTip("Submit the AYON publish job to Deadline farm instead of publishing locally")

    def _on_publish_to_ayon_changed(self, state):
        """Save Publish to AYON checkbox state and toggle farm checkbox visibility."""
        from core.settings_manager import safe_set_setting
        from PySide6.QtCore import Qt
        checked = state == Qt.Checked
        safe_set_setting("mp4_maker_publish_to_ayon", checked)
        self.ui.MP4PublishOnFarm.setVisible(checked)

    def _on_publish_on_farm_changed(self, state):
        """Save Publish on Farm checkbox state."""
        from core.settings_manager import safe_set_setting
        from PySide6.QtCore import Qt
        safe_set_setting("mp4_maker_publish_on_farm", state == Qt.Checked)

    def _copy_to_gallery(self, source_path: str, publish_after: bool = False):
        """Copy the generated MP4 to the gallery folder with metadata.

        Args:
            source_path: EXR input pattern used for gallery metadata.
            publish_after: If True, chain AYON publish after gallery copy completes.
        """
        from services.mp4_maker import copy_mp4_to_gallery

        def on_gallery_result(result):
            """Handle gallery copy completion."""
            success, path_or_error = result
            if publish_after:
                if success:
                    self.update_status_with_spinner(
                        "Added to gallery. Publishing to AYON...",
                        StatusColors.INFO,
                        start=True
                    )
                else:
                    logger.warning(f"Gallery copy failed: {path_or_error}")
                    self.update_status_with_spinner(
                        "Gallery copy failed. Publishing to AYON...",
                        StatusColors.INFO,
                        start=True
                    )
                self._publish_mp4_to_ayon()
            elif success:
                self.update_status_with_spinner(
                    "MP4 generated and added to gallery",
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
            logger.error(f"Gallery copy error: {error_msg}")
            if publish_after:
                # Still attempt publish even if gallery copy errored
                self.update_status_with_spinner(
                    "Gallery error. Publishing to AYON...",
                    StatusColors.INFO,
                    start=True
                )
                self._publish_mp4_to_ayon()
            else:
                self.update_status_with_spinner(
                    f"MP4 generated (gallery error: {error_msg})",
                    StatusColors.WARNING,
                    start=False
                )

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

    def _publish_mp4_to_ayon(self):
        """Publish the generated MP4 to AYON as a review file."""

        use_farm = self.ui.MP4PublishOnFarm.isChecked() and self.ui.MP4PublishOnFarm.isEnabled()
        mp4_path = self.app_state.mp4_output_path

        def on_publish_result(result):
            """Handle AYON publish completion."""
            success, detail = result
            if success:
                if use_farm:
                    self.update_status_with_spinner(
                        f"MP4 published to AYON (Deadline job: {detail})",
                        StatusColors.SUCCESS,
                        start=False
                    )
                    self.show_status(f"MP4 published to AYON via Deadline farm", "success")
                else:
                    self.update_status_with_spinner(
                        "MP4 published to AYON",
                        StatusColors.SUCCESS,
                        start=False
                    )
                    self.show_status("MP4 published to AYON successfully!", "success")
            else:
                self.update_status_with_spinner(
                    f"AYON publish failed: {detail}",
                    StatusColors.ERROR,
                    start=False
                )
                self.show_status(f"AYON publish failed: {detail}", "error")

        def on_publish_error(error_msg, traceback_str):
            """Handle AYON publish error."""
            self.update_status_with_spinner(
                f"AYON publish error: {error_msg}",
                StatusColors.ERROR,
                start=False
            )
            logger.error(f"AYON publish error: {error_msg}")
            logger.debug(traceback_str)

        def on_publish_progress(progress, message):
            """Update UI with publish progress."""
            if not self.animator:
                return
            self.animator.update_status_animated(
                f"AYON: {message} ({progress}%)",
                StatusColors.INFO
            )

        self.start_worker(
            self._publish_mp4_worker,
            worker_kwargs={
                "mp4_path": mp4_path,
                "use_farm": use_farm,
            },
            on_result=on_publish_result,
            on_error=on_publish_error,
            on_progress=on_publish_progress,
        )

    @staticmethod
    def _publish_mp4_worker(mp4_path, use_farm, progress_callback=None):
        """Worker thread function for publishing MP4 to AYON.

        Args:
            mp4_path: Path to the MP4 file to publish.
            use_farm: If True, submit publish to Deadline; otherwise publish locally.
            progress_callback: Optional callback(percent, message).

        Returns:
            Tuple of (success: bool, detail: str).
        """
        from ayon.service import (
            create_ayon_metadata_single_file,
            write_metadata_file,
            publish_to_ayon_local,
            submit_ayon_publish_to_deadline,
            convert_to_ayon_folder_path,
        )
        from core.state_manager import app_state

        if progress_callback:
            progress_callback(10, "Preparing metadata...")

        # Build product name from MP4 filename
        mp4_basename = os.path.basename(mp4_path)
        render_name = os.path.splitext(mp4_basename)[0]
        product_name = f"review_{render_name}"

        # Build AYON folder path from shot context
        folder_path = convert_to_ayon_folder_path(app_state.shotpath, app_state.jobname)
        task = app_state.task or "compositing"

        logger.info(f"[MP4 AYON Publish] File: {mp4_path}")
        logger.info(f"[MP4 AYON Publish] Product: {product_name}, Task: {task}")
        logger.info(f"[MP4 AYON Publish] Folder: {folder_path}, Farm: {use_farm}")

        if progress_callback:
            progress_callback(20, "Creating AYON metadata...")

        # Create metadata for single MP4 file
        metadata = create_ayon_metadata_single_file(
            project_name=app_state.jobname,
            file_path=mp4_path,
            product_name=product_name,
            product_type="review",
            folder_path=folder_path,
            task=task,
            user=app_state.user,
        )

        if not metadata:
            return (False, "Failed to create AYON metadata")

        if progress_callback:
            progress_callback(40, "Writing metadata file...")

        # Write metadata file next to the MP4
        mp4_dir = os.path.dirname(mp4_path)
        from ayon.service import build_ayon_metadata_filename
        metadata_filename = build_ayon_metadata_filename(product_name, prefix="mp4")
        metadata_path = os.path.join(mp4_dir, metadata_filename)
        metadata_path = write_metadata_file(metadata, metadata_path)

        if not metadata_path:
            return (False, "Failed to write metadata file")

        if progress_callback:
            progress_callback(60, "Publishing to AYON..." if not use_farm else "Submitting to Deadline...")

        if use_farm:
            job_id = submit_ayon_publish_to_deadline(
                project_name=app_state.jobname,
                render_name=product_name,
                render_file=mp4_basename,
                metadata_path=metadata_path,
                folder_path=folder_path,
                task=task,
                user=app_state.user,
            )
            if job_id:
                if progress_callback:
                    progress_callback(100, "Submitted to Deadline")
                return (True, job_id)
            else:
                return (False, "Deadline submission failed")
        else:
            # For local publish, ensure farm flag is False
            if "instances" in metadata and metadata["instances"]:
                metadata["instances"][0]["farm"] = False
                # Re-write metadata with farm=False
                write_metadata_file(metadata, metadata_path)

            success = publish_to_ayon_local(
                metadata_path=metadata_path,
                project_name=app_state.jobname,
                folder_path=folder_path,
                task=task,
                user=app_state.user,
            )
            if progress_callback:
                progress_callback(100, "Publish complete" if success else "Publish failed")
            if success:
                return (True, "Published locally")
            else:
                return (False, "Local publish failed")
