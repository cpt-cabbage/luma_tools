"""
rePublish tab module for Luma Tools.

Handles republishing renders to AYON.
"""

import os
import logging
import threading

from ui_components import StatusColors
from .base_tab import BaseTab, TabConfig
from .mixins.render_scan_mixin import RenderScanMixin

logger = logging.getLogger(__name__)


class RePublishTab(RenderScanMixin, BaseTab):
    """Tab for republishing renders to AYON."""

    TAB_CONFIG = TabConfig(ui_file="republish.ui", tab_name="rePublish", tab_id="republish")

    # RenderScanMixin widget configuration
    _render_list_widget = "RePublishRendersList"
    _render_path_widget = "RePublishRenderPath"
    _version_widget = "RePublishCurrentVer"
    _action_button = "RePublishPublish"
    _source_button = "RePublishSourceButton"
    _custom_path_label = "RePublishCustomPathLabel"
    _browse_custom_button = "RePublishBrowseCustomPath"

    # RenderScanMixin app_state attributes
    _renders_attr = "republish_renders"
    _searchpath_attr = "republish_searchpath"
    _custom_path_attr = "republish_custom_path"

    def connect_signals(self):
        """Connect rePublish tab signals."""
        # Explicit Rescan invalidates the shared task-dir scan cache first
        self.ui.RePublishScanRenders.clicked.connect(self._on_rescan_clicked)
        # Debounce rapid version spinbox changes (~350ms) before rescanning
        self._connect_debounced(
            self.ui.RePublishCurrentVer.valueChanged, self._on_scan_renders_clicked
        )
        # Source and task buttons are connected via OptionButtonManager in initialize()
        self.ui.RePublishBrowseCustomPath.clicked.connect(self._on_browse_custom_path)
        self.ui.RePublishRendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.RePublishPublish.clicked.connect(self._on_publish_clicked)
        # Publish-on-farm state persistence
        self.ui.RePublishUseFarm.stateChanged.connect(self._on_use_farm_changed)

    def _get_source_options(self):
        """Override: in standalone mode, only custom is available.
        Publish source not offered here — Republish is for publishing filesystem renders to AYON.
        """
        if self.app_state.standalone_mode:
            return [("Custom", "custom")]
        return [("For Comp", "for_comp"), ("Raw", "raw"), ("Custom", "custom")]

    def _get_initial_source(self):
        """Override: standalone mode defaults to custom."""
        return "custom" if self.app_state.standalone_mode else "for_comp"

    # Tasks always offered in the Task dropdown
    _DEFAULT_TASK_OPTIONS = ["lighting", "compositing", "fx"]

    def initialize(self):
        """Initialize rePublish tab."""
        from option_button import OptionButtonManager
        from core.settings_manager import safe_get_setting

        self.ui.RePublishPublish.setEnabled(False)
        self._products_loading = False

        # Restore the persisted "Publish on Farm" preference
        self.ui.RePublishUseFarm.setChecked(safe_get_setting("republish_use_farm", False))

        # AYON branding for publish button and checkbox
        from icons import get_ayon_icon
        from core.config import UIColors
        self.ui.RePublishPublish.setIcon(get_ayon_icon(18))
        self.ui.RePublishPublish.setStyleSheet(f"""
            QPushButton {{
                background-color: {UIColors.AYON_GREEN}; color: white;
                border: none; border-radius: 4px; font-weight: bold; font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {UIColors.AYON_GREEN_HOVER}; }}
            QPushButton:disabled {{ background-color: #3c414b; color: #6b6f78; }}
        """)
        self.apply_ayon_checkbox_style(self.ui.RePublishUseCurrentTask)

        # In standalone mode, show browse button immediately
        if self.app_state.standalone_mode:
            self.ui.RePublishBrowseCustomPath.setVisible(True)
            logger.info("Republish tab: Standalone mode - only custom directory selection allowed")

        # Source manager from mixin
        self._init_source_manager()

        # Make product combo dropdown wide enough to show full names
        from PySide6.QtWidgets import QComboBox
        self.ui.RePublishProductName.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.ui.RePublishProductName.setMinimumWidth(200)

        # Task button manager - republish-specific.
        # The launch context task is seeded into the options when it isn't one of
        # the three defaults, so the current task is always selectable.
        current_task = (self.app_state.task or "").strip()
        task_values = list(self._DEFAULT_TASK_OPTIONS)
        if current_task and current_task.lower() not in task_values:
            task_values.append(current_task.lower())

        self._task_manager = OptionButtonManager(
            button=self.ui.RePublishTaskButton,
            options=[(t, t) for t in task_values],
            initial_value=current_task.lower() if current_task else "lighting",
            on_changed=lambda v: None,  # No special action on task change
            label_prefix="Task: ",
            parent_window=self.main_window
        )

        # Run initial scan to find render directory (independent of Shot Cleaner tab)
        if self.app_state.has_shot_context() and not self.app_state.republish_searchpath:
            self._run_initial_scan()

        # Populate "Publish To:" dropdown with AYON products
        if self.app_state.has_shot_context():
            self._populate_product_combo("")

    def _run_initial_scan(self):
        """Find render directory and set republish_searchpath on startup (async)."""
        from services.file_operations import get_task_directory

        task = self.app_state.task
        task_dir = get_task_directory(self.app_state.shotpath, task)

        if not os.path.isdir(task_dir):
            logger.warning(f"Republish: Task directory not found: {task_dir}")
            return

        def _on_scan_result(result):
            if not result:
                return
            from core.utils import get_trailing_number

            searchpath = os.path.join(result['render_directory'], result['latest_render'])
            self.app_state.republish_searchpath = searchpath
            self.ui.RePublishRenderPath.setText(searchpath)

            # Block valueChanged while setting range/value to prevent premature scan
            self.ui.RePublishCurrentVer.blockSignals(True)
            ver_str = get_trailing_number(result['latest_render'])
            if ver_str is not None:
                latest_ver = int(ver_str)
                self.ui.RePublishCurrentVer.setRange(0, latest_ver)
                self.ui.RePublishCurrentVer.setValue(latest_ver)
            self.ui.RePublishCurrentVer.blockSignals(False)

            # Task is seeded from app_state.task in initialize(), so nothing to
            # do here — the scan result must not override a user's choice.

            logger.info(f"Republish: Found render path: {searchpath}")

            # Now trigger the scan with everything properly set up
            self._on_scan_renders_clicked()

        self.start_worker(
            self._scan_render_directory_worker, task_dir, task,
            on_result=_on_scan_result
        )

    @property
    def _task(self):
        # Defensive guard: _task_manager is created in initialize(), which
        # runs only on first tab activation. Mirror the _source/_source_manager
        # pattern so any signal handler that fires before initialize() gets a
        # safe default instead of AttributeError.
        if not hasattr(self, '_task_manager'):
            return "lighting"
        return self._task_manager.value

    def _on_source_changed(self, value=None):
        """Override: extra visibility logic for version spinbox and UseCurrentTask."""
        if not hasattr(self, '_source_manager'):
            return
        # Call base for browse/label visibility
        super()._on_source_changed(value)

        is_custom = self._source == "custom"

        # RePublish-specific: show/hide additional widgets
        self.ui.RePublishUseCurrentTask.setVisible(is_custom)
        self.ui.RePublishVersionLabel.setVisible(not is_custom)
        self.ui.RePublishCurrentVer.setVisible(not is_custom)

        # Enable "Use Current AYON Task" only when custom path is selected AND we have AYON context
        if is_custom:
            can_use_current_task = self.app_state.has_ayon_context()
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

    def _on_use_farm_changed(self, state):
        """Persist the Publish on Farm checkbox state."""
        from core.settings_manager import safe_set_setting
        from PySide6.QtCore import Qt
        safe_set_setting("republish_use_farm", state == Qt.Checked)

    def _on_scan_renders_clicked(self):
        """Override: republish has standalone mode check and custom display names."""
        if not hasattr(self, '_source_manager'):
            return  # Tab not yet initialized

        # Publish source is handled by PublishSourceMixin
        if self._source == "publish":
            # Invalidate any in-flight filesystem scan so stale results cannot
            # land on top of the publish-mode list.
            self._begin_scan_generation()
            self._on_publish_source_selected()
            return

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
            self._begin_scan_generation()
            self.app_state.republish_renders = []
            if self.app_state.standalone_mode:
                self.ui.RePublishStatusLabel.setText("Status: Please browse for a directory")
            else:
                self.ui.RePublishStatusLabel.setText("Status: Invalid path")
            return

        # Find EXR sequences off the GUI thread — network paths can stall.
        self.ui.RePublishStatusLabel.setText("Status: Scanning...")

        # Generation counter: rapid version changes can queue multiple scans;
        # only the newest one is allowed to populate the list.
        generation = self._begin_scan_generation()

        def _scan_worker(path=search_path):
            sequences = scan_exr_sequences(path)
            renders = []
            display_names = []
            for seq in sequences:
                seq_path = str(seq)
                rel_path = os.path.relpath(os.path.dirname(seq_path), path)
                subdir = rel_path if rel_path != "." else ""
                renders.append((subdir, seq))
                display_names.append(
                    f"{subdir}/{seq.basename()}" if subdir and subdir != "." else seq.basename()
                )
            return renders, display_names

        def _on_scan_result(result):
            if not self._is_current_scan(generation):
                return  # A newer scan superseded this one — drop stale results
            renders, display_names = result
            self.ui.RePublishRendersList.clear()
            for name in display_names:
                self.ui.RePublishRendersList.addItem(name)
            self.app_state.republish_renders = renders
            count = len(renders)
            self.ui.RePublishStatusLabel.setText(f"Status: Found {count} render sequence(s)")
            if count > 0:
                self.ui.RePublishRendersList.setCurrentRow(0)

        def _on_scan_error(error_msg, traceback_str=""):
            if not self._is_current_scan(generation):
                return
            logger.error(f"Error scanning renders for republish: {error_msg}")
            self.ui.RePublishRendersList.clear()
            self.app_state.republish_renders = []
            self.ui.RePublishStatusLabel.setText(f"Status: Scan error - {error_msg}")
            self.show_status(f"rePublish scan error: {error_msg}", "error")

        self.start_worker(_scan_worker, on_result=_on_scan_result, on_error=_on_scan_error)

    def _on_render_selection_changed(self):
        """Handle render selection in rePublish list."""
        selected = self._get_selected_render()
        if not selected:
            self.ui.RePublishPublish.setEnabled(False)
            self.app_state.republish_selected_render = None
            return

        # Get the fileseq object
        _, seq = selected
        self.app_state.republish_selected_render = seq

        # Extract frame range
        self.app_state.republish_startframe = seq.start()
        self.app_state.republish_endframe = seq.end()

        # Update status with frame range
        self.ui.RePublishStatusLabel.setText(
            f"Status: Selected {seq.basename()}\n"
            f"Frames: {self.app_state.republish_startframe}-{self.app_state.republish_endframe}"
        )

        # Populate AYON products and auto-select matching product name.
        # This disables the Publish button until the product list has landed —
        # publishing mid-fetch would use a stale/blank product name.
        from core.utils import extract_render_name
        render_name = extract_render_name(seq.basename(), strip_frame_padding=True)
        self._populate_product_combo(render_name)

        # Enable publish button (unless a product fetch is still in flight)
        if not getattr(self, '_products_loading', False):
            self.ui.RePublishPublish.setEnabled(True)
            self.pulse_button(self.ui.RePublishPublish)

    def _set_products_loading(self, loading: bool):
        """Disable/relabel the Publish button while AYON products are fetched."""
        self._products_loading = loading

        # Never touch the button while a publish is running — it is the Cancel
        # button at that point.
        if getattr(self, '_is_publishing', False):
            return

        if loading:
            self.ui.RePublishPublish.setEnabled(False)
            self.ui.RePublishPublish.setText("Loading products...")
        else:
            self.ui.RePublishPublish.setText("Publish to AYON")
            has_selection = self.app_state.republish_selected_render is not None
            self.ui.RePublishPublish.setEnabled(has_selection)
            if has_selection:
                self.pulse_button(self.ui.RePublishPublish)

    def _populate_product_combo(self, default_name):
        """Populate the publish product combo box with existing AYON products.

        Queries AYON for all products in the current shot folder, then
        auto-selects the product that matches the selected render. The Publish
        button is disabled for the duration of the query.
        """
        combo = self.ui.RePublishProductName

        if not self.app_state.has_shot_context():
            return

        self._set_products_loading(True)

        def _query_products():
            from ayon.service import (
                AYON_AVAILABLE, convert_to_ayon_folder_path,
                get_folder_product_names, find_product_for_render,
            )
            if not AYON_AVAILABLE:
                return [], default_name

            project_name = self.app_state.jobname
            folder_path = convert_to_ayon_folder_path(
                self.app_state.shotpath, project_name
            )
            product_names = get_folder_product_names(project_name, folder_path)
            matched = find_product_for_render(project_name, folder_path, default_name) if default_name else ""
            return product_names, matched

        def _on_products(result):
            product_names, matched_name = result
            combo.clear()
            for name in product_names:
                combo.addItem(name)
            if matched_name:
                # Select the matched product from the dropdown
                idx = combo.findText(matched_name)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setCurrentText(matched_name)
            self._set_products_loading(False)

        def _on_products_error(error_msg, traceback_str=""):
            logger.error(f"Republish: Failed to fetch AYON products: {error_msg}")
            self.ui.RePublishStatusLabel.setText(
                f"Status: Could not load AYON products - {error_msg}"
            )
            # Re-enable publishing — the user can still type a product name
            self._set_products_loading(False)

        self.start_worker(
            _query_products, on_result=_on_products, on_error=_on_products_error
        )

    def _on_publish_clicked(self):
        """Handle publish to AYON button click, or cancel if already publishing."""
        # If already publishing, cancel the operation
        if getattr(self, '_is_publishing', False):
            cancel_event = getattr(self, '_cancel_event', None)
            if cancel_event:
                cancel_event.set()
            self.ui.RePublishPublish.setEnabled(False)
            self.show_status("Cancelling publish...", "warning")
            return

        self.animate_button_click(self.ui.RePublishPublish)

        # Validate selection
        if not self.app_state.republish_selected_render:
            self.ui.RePublishStatusLabel.setText("Status: No render selected")
            return

        # Get options
        task = self._task
        use_farm = self.ui.RePublishUseFarm.isChecked()
        product_name = self.ui.RePublishProductName.currentText().strip()

        if not product_name:
            from core.utils import extract_render_name
            product_name = extract_render_name(
                self.app_state.republish_selected_render.basename(),
                strip_frame_padding=True
            )

        # Set up cancellation
        self._cancel_event = threading.Event()
        self._is_publishing = True
        cancel_event = self._cancel_event

        # Switch button to Cancel mode
        self.ui.RePublishPublish.setText("Cancel")

        # Show status bar progress
        self.update_status_with_spinner(
            "AYON: Preparing files for publish...",
            StatusColors.INFO
        )

        # Check if user wants to use current AYON task context
        use_current_task = (
            self._source == "custom" and
            self.ui.RePublishUseCurrentTask.isChecked() and
            self.app_state.has_ayon_context()
        )

        # Use BaseTab helper for worker management
        try:
            self.start_worker(
                self._publish_worker,
                task,
                use_farm,
                product_name,
                use_current_task,
                cancel_event,
                on_result=self._on_publish_complete,
                on_error=self._on_publish_error,
                on_progress=self._on_publish_progress
            )
        except Exception:
            self._reset_publish_button()
            raise

    def _publish_worker(self, task, use_farm, product_name, use_current_task, cancel_event, progress_callback):
        """Worker thread function for publishing to AYON."""
        from ayon.service import (
            convert_to_ayon_folder_path, create_ayon_metadata, write_metadata_file,
            publish_to_ayon_local, submit_ayon_publish_to_deadline
        )
        from core.error_handling import check_cancelled

        # Get render path information
        seq = self.app_state.republish_selected_render
        first_frame = seq.frame(self.app_state.republish_startframe)
        source_dir = os.path.dirname(first_frame)

        # Determine if source_dir is inside a render version directory (a subdirectory
        # like "combined", "for_comp", etc.) or IS the version directory itself.
        # Compare against the known render searchpath to avoid hardcoding subdir names.
        searchpath = self.app_state.republish_searchpath
        if searchpath and os.path.normcase(source_dir) != os.path.normcase(searchpath):
            # source_dir is deeper than the version dir — treat the extra part as output subdir
            rel = os.path.relpath(source_dir, searchpath)
            if rel and not rel.startswith(".."):
                base_render_path = searchpath
                output_subdirectory = rel
            else:
                base_render_path = source_dir
                output_subdirectory = ""
        else:
            base_render_path = source_dir
            output_subdirectory = ""

        logger.info(f"Source directory: {source_dir}")
        logger.info(f"Base render path: {base_render_path}")
        logger.info(f"Output subdirectory: {output_subdirectory}")

        check_cancelled(cancel_event)
        progress_callback(50, "Preparing metadata for AYON publish...")

        # Build render_file pattern from the actual sequence filename
        # seq.basename() returns e.g. "Main." — we need "Main.%04d.exr"
        import fileseq
        base_name = seq.basename()  # e.g. "Main."
        frame_padding = fileseq.FileSequence.getPaddingNum(seq.padding())
        render_file = f"{base_name}%0{frame_padding}d.exr"

        # render_name is the actual filename stem (for file listing in metadata)
        # product_name is the AYON product name (for product/version tracking)
        render_name = base_name.rstrip(".")  # "Main." → "Main"

        # Determine project name and folder path
        from core.utils import normalize_path
        if use_current_task:
            project_name = self.app_state.jobname
            shot_path_for_conversion = self.app_state.shotpath
            logger.info(f"[Use Current Task] Using current AYON context instead of parsing path")
        else:
            normalized_source = normalize_path(source_dir)
            path_parts = normalized_source.split("/")

            project_name = self.app_state.jobname  # Default to current project
            shot_path_for_conversion = None

            for i, part in enumerate(path_parts):
                if part in ["shots", "assets"] and i > 0:
                    project_name = path_parts[i - 1]
                    if "work" in path_parts:
                        work_idx = path_parts.index("work")
                        shot_path_for_conversion = "/".join(path_parts[:work_idx + 1])
                    break

            if not shot_path_for_conversion:
                shot_path_for_conversion = self.app_state.shotpath
                project_name = self.app_state.jobname

        folder_path = convert_to_ayon_folder_path(shot_path_for_conversion, project_name)

        logger.info(f"Detected project: {project_name}")
        logger.info(f"Detected folder path: {folder_path}")

        # working_dir must end with "work/" for the source path template
        if "/work" in normalize_path(shot_path_for_conversion):
            working_dir = normalize_path(shot_path_for_conversion).split("/work")[0] + "/work/"
        else:
            working_dir = normalize_path(shot_path_for_conversion) + "/"

        # Create metadata
        check_cancelled(cancel_event)
        progress_callback(75, "Creating AYON metadata...")
        metadata = create_ayon_metadata(
            project_name=project_name,
            render_name=render_name,
            start_frame=self.app_state.republish_startframe,
            end_frame=self.app_state.republish_endframe,
            renders_path=base_render_path,
            folder_path=folder_path,
            task=task,
            user=self.app_state.user,
            output_subdirectory=output_subdirectory,
            working_dir=working_dir,
            render_file=render_file,
            product_name=product_name,
            farm=use_farm
        )

        # Write metadata file to source directory
        from ayon.service import build_ayon_metadata_filename
        metadata_filename = build_ayon_metadata_filename(product_name)
        metadata_path = os.path.join(source_dir, metadata_filename)
        metadata_path = write_metadata_file(metadata, metadata_path)

        if not metadata_path:
            raise RuntimeError("Failed to write metadata file")

        # Check cancellation before publish step
        check_cancelled(cancel_event)

        # Publish
        progress_callback(85, f"{'Submitting to farm' if use_farm else 'Publishing locally'}...")

        if use_farm:
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
                raise RuntimeError("Failed to submit to Deadline")

            progress_callback(100, "Publish job submitted to farm")
            return {"success": True, "message": f"Published to farm! Job ID: {job_id}", "job_id": job_id}
        else:
            success = publish_to_ayon_local(
                metadata_path,
                project_name,
                folder_path,
                task,
                self.app_state.user
            )

            if not success:
                raise RuntimeError("Local publish failed")

            progress_callback(100, "Published successfully")
            return {"success": True, "message": f"Published: {product_name}"}

    def _on_publish_progress(self, progress, message):
        """Handle progress updates from worker."""
        if self.animator:
            self.animator.update_status_animated(
                f"AYON: {message}",
                StatusColors.INFO
            )

    def _reset_publish_button(self):
        """Reset publish button to its default state."""
        self._is_publishing = False
        self.ui.RePublishPublish.setText("Publish to AYON")
        from icons import get_ayon_icon
        self.ui.RePublishPublish.setIcon(get_ayon_icon(18))
        self.ui.RePublishPublish.setEnabled(True)

    def _on_publish_complete(self, result):
        """Handle successful publish completion."""
        self._reset_publish_button()
        self.ui.RePublishStatusLabel.setText(f"Status: {result['message']}")

        self.update_status_with_spinner(
            f"AYON: {result['message']}",
            StatusColors.SUCCESS,
            start=False
        )
        self.show_status(result['message'], "success")

    def _on_publish_error(self, error_msg, traceback_str):
        """Handle publish errors or cancellation."""
        self._reset_publish_button()

        if getattr(self, '_cancel_event', None) and self._cancel_event.is_set():
            self.ui.RePublishStatusLabel.setText("Status: Publish cancelled")
            self.update_status_with_spinner(
                "AYON: Publish cancelled",
                StatusColors.WARNING,
                start=False
            )
            self.show_status("Publish cancelled", "warning")
            return

        full_error_msg = f"Publish failed: {error_msg}"
        self.ui.RePublishStatusLabel.setText(f"Status: {full_error_msg}")

        self.update_status_with_spinner(
            f"AYON: {full_error_msg}",
            StatusColors.ERROR,
            start=False
        )

        logger.error(f"Publish error: {error_msg}")
        if traceback_str:
            logger.error(traceback_str)