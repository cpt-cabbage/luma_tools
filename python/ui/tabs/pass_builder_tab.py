"""
Pass Builder tab module for Luma Tools.

Handles render scanning, pass detection, and pass building functionality.
"""

import os
import re
import logging
import threading
from PySide6 import QtWidgets

from .base_tab import BaseTab, TabConfig
from .mixins.publish_source_mixin import PublishSourceMixin

logger = logging.getLogger(__name__)



class PassBuilderTab(PublishSourceMixin, BaseTab):
    """Tab for building render passes."""

    TAB_CONFIG = TabConfig(ui_file="pass_builder.ui", tab_name="Pass Builder", tab_id="passbuilder")

    def connect_signals(self):
        """Connect pass builder tab signals."""
        self.ui.ScanRenders.clicked.connect(self._on_scan_renders_clicked)
        self.ui.RendersList.itemSelectionChanged.connect(self._on_render_selection_changed)
        self.ui.BuildPasses.pressed.connect(self._on_build_passes_clicked)
        self.ui.CurrentVer.valueChanged.connect(self._on_scan_renders_clicked)
        # Build type button connected in initialize() via manager

    # Widget names used by PublishSourceMixin for render list population
    _render_list_widget = "RendersList"
    _render_path_widget = "RenderPath"
    _action_button = "BuildPasses"
    _renders_attr = "renders"

    def initialize(self):
        """Initialize pass builder tab."""
        from ui_components import InlineSpinner
        from option_button import OptionButtonManager
        from core.import_utils import safe_import

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

        # "Publish to AYON" checkbox — on by default, controls whether build publishes
        from icons import get_ayon_icon
        from core.config import UIColors
        from core.settings_manager import safe_get_setting, safe_set_setting
        self._publish_to_ayon_cb = QtWidgets.QCheckBox("Publish to AYON")
        self._publish_to_ayon_cb.setIcon(get_ayon_icon(14))
        self._publish_to_ayon_cb.setStyleSheet(f"QCheckBox {{ color: {UIColors.AYON_GREEN}; }}")
        self._publish_to_ayon_cb.setToolTip("When enabled, built passes are published to AYON")
        self._publish_to_ayon_cb.setChecked(safe_get_setting("pass_builder_publish_to_ayon", True))
        self._publish_to_ayon_cb.stateChanged.connect(self._on_publish_to_ayon_changed)

        # Insert checkbox before the "Publish To:" label in the build options layout
        build_layout = self.ui.buildOptionsLayout
        label_index = build_layout.indexOf(self.ui.publishToLabel)
        if label_index >= 0:
            build_layout.insertWidget(label_index, self._publish_to_ayon_cb)
        else:
            build_layout.insertWidget(2, self._publish_to_ayon_cb)

        # Show/hide product widgets based on initial state
        self._update_publish_widgets_visibility()

        # Source selection (File vs Publish) - only show if AYON is available
        ayon_service, _ = safe_import("ayon.service")
        ayon_available = getattr(ayon_service, 'AYON_AVAILABLE', False) if ayon_service else False
        if ayon_available and self.app_state.has_ayon_context():
            self._pb_source_button = QtWidgets.QPushButton("Source: File")
            self._pb_source_button.setMinimumSize(140, 28)
            self._pb_source_button.setToolTip("Click to choose render source (filesystem or AYON publish)")

            # Insert source button into the version layout
            version_layout = self._find_layout_containing(self.ui.CurrentVer)
            if version_layout:
                version_layout.insertWidget(0, self._pb_source_button)

            self._pb_source_manager = OptionButtonManager(
                button=self._pb_source_button,
                options=[("File", "file"), ("Publish", "publish")],
                initial_value="publish",
                on_changed=self._on_pb_source_changed,
                label_prefix="Source: ",
                parent_window=self.main_window
            )

            # Publish source widgets (product/version combos)
            self._init_publish_widgets(self.ui.CurrentVer)

            # Make product combo dropdown wide enough to show full names
            from PySide6.QtWidgets import QComboBox
            self.ui.PublishProductCombo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToContents
            )
            self.ui.PublishProductCombo.setMinimumWidth(200)

            # Start in publish mode - hide file widgets, show publish widgets
            self._on_pb_source_changed("publish")

        # Run initial scan if we have shot context (only for file mode)
        if self.app_state.has_shot_context() and not hasattr(self, '_pb_source_manager'):
            self._run_initial_scan()

        # Populate "Publish To:" dropdown with AYON products
        if self.app_state.has_shot_context():
            self._populate_product_combo()

    def _on_publish_to_ayon_changed(self, state):
        """Save Publish to AYON checkbox state and toggle product widgets."""
        from core.settings_manager import safe_set_setting
        from PySide6.QtCore import Qt
        safe_set_setting("pass_builder_publish_to_ayon", state == Qt.Checked)
        self._update_publish_widgets_visibility()

    def _update_publish_widgets_visibility(self):
        """Show/hide the Publish To label and product combo based on checkbox."""
        visible = self._publish_to_ayon_cb.isChecked()
        self.ui.publishToLabel.setVisible(visible)
        self.ui.PublishProductCombo.setVisible(visible)

    def _run_initial_scan(self):
        """Find render directory and populate render path on startup (async)."""
        from services.file_operations import get_task_directory

        task = self.app_state.task
        task_dir = get_task_directory(self.app_state.shotpath, task)
        self.app_state.lookdev_dir = task_dir
        logger.info(f"Pass Builder: Task Dir: {task_dir}")

        if not os.path.isdir(task_dir):
            logger.warning(f"Pass Builder: Task directory not found: {task_dir}")
            return

        def _scan_worker(task_dir, task, shotpath):
            """Background worker for initial render scan."""
            from services.file_operations import fast_scandir, find_renders, find_hip_files
            from core.config import RENDERS_SUBPATH
            from core.utils import truncate_at_suffix, get_trailing_number

            try:
                dirs = fast_scandir(task_dir)
            except Exception as e:
                logger.warning(f"Pass Builder: Error scanning {task_dir}: {e}")
                return None

            render_folders = [d for d in dirs if RENDERS_SUBPATH in d]
            if not render_folders:
                logger.warning(f"Pass Builder: No render directory found in {task_dir}")
                return None

            render_directory = truncate_at_suffix(render_folders[0], RENDERS_SUBPATH)

            hip_files = find_hip_files(task_dir, task)
            hip_file = ""
            if hip_files:
                hip_files = sorted(hip_files)
                hip_file = hip_files[0].rsplit("_", 1)[0]

            try:
                render_dirs = sorted(next(os.walk(render_directory))[1])
            except StopIteration:
                return None

            if hip_file:
                matching = [d for d in render_dirs if hip_file in d]
                if matching:
                    render_dirs = matching

            if not render_dirs:
                return None

            latest_render = None
            for render_version in reversed(render_dirs):
                version_path = os.path.join(render_directory, render_version)
                test_renders = find_renders(version_path)
                if len(test_renders) > 0:
                    latest_render = render_version
                    break

            if not latest_render:
                latest_render = render_dirs[-1]

            return {
                'latest_render': latest_render,
                'render_directory': render_directory,
                'task': task,
            }

        def _on_scan_result(result):
            if not result:
                return
            from core.utils import truncate_at_suffix, get_trailing_number

            self.app_state.latestrender = result['latest_render']
            self.app_state.searchpath = os.path.join(result['render_directory'], result['latest_render'])
            self.app_state.working_dir = truncate_at_suffix(result['render_directory'], result['task'])

            self.ui.RenderPath.setText(self.app_state.searchpath)
            ver_str = get_trailing_number(result['latest_render'])
            if ver_str is not None:
                latest_ver = int(ver_str)
                self.ui.CurrentVer.blockSignals(True)
                self.ui.CurrentVer.setRange(0, latest_ver)
                self.ui.CurrentVer.setValue(latest_ver)
                self.ui.CurrentVer.blockSignals(False)

            logger.info(f"Pass Builder: Found render path: {self.app_state.searchpath}")
            self._initial_scan_done = True

        self.start_worker(
            _scan_worker, task_dir, task, self.app_state.shotpath,
            on_result=_on_scan_result
        )

    @property
    def _build_type(self):
        return self._build_type_manager.value

    def _on_pb_source_changed(self, value):
        """Handle source toggle between File and Publish modes."""
        is_publish = value == "publish"

        # Toggle filesystem widgets
        self.ui.CurrentVer.setVisible(not is_publish)
        self.ui.label_3.setVisible(not is_publish)  # "Version:" label
        self.ui.ScanRenders.setVisible(not is_publish)

        # Toggle publish widgets
        self._show_publish_widgets(is_publish)

        if is_publish:
            self._on_publish_source_selected()

    def _fetch_ayon_products(self):
        """Override: fetch render products and scan available denoised render variants.

        Returns both the AYON products and the set of available denoised render
        variant names, so the product list can be filtered to only show products
        that have matching denoised renders on disk.
        """
        from ayon.service import AYON_AVAILABLE, convert_to_ayon_folder_path, get_folder_render_products

        products = []
        if AYON_AVAILABLE:
            project_name = self.app_state.jobname
            folder_path = convert_to_ayon_folder_path(
                self.app_state.shotpath, project_name
            )
            products = get_folder_render_products(project_name, folder_path)

        available_variants = self._scan_available_render_variants()
        return products, available_variants

    def _scan_available_render_variants(self):
        """Scan work directory for available denoised render variant names.

        If a task is set, scans only that task directory. Otherwise scans all
        task directories under work/ to support task-less browsing.

        Returns:
            dict[str, set[str]]: Mapping of task_lowercase → set of variant
            names (lowercase). e.g., {'lighting': {'main', 'girrafe'}}.
        """
        from services.file_operations import get_task_directory, fast_scandir, find_renders
        from core.config import RENDERS_SUBPATH
        from core.utils import truncate_at_suffix, extract_render_name

        available = {}
        shot_path = self.app_state.shotpath

        # Determine which task directories to scan
        task = self.app_state.task
        if task:
            tasks_to_scan = [task]
        else:
            work_dir = truncate_at_suffix(shot_path, "work")
            if os.path.isdir(work_dir):
                tasks_to_scan = [
                    d for d in os.listdir(work_dir)
                    if os.path.isdir(os.path.join(work_dir, d))
                ]
            else:
                return available

        for t in tasks_to_scan:
            task_dir = get_task_directory(shot_path, t)
            if not os.path.isdir(task_dir):
                continue
            try:
                dirs = fast_scandir(task_dir)
                render_folders = [d for d in dirs if RENDERS_SUBPATH in d]
                if not render_folders:
                    continue

                render_directory = truncate_at_suffix(render_folders[0], RENDERS_SUBPATH)
                render_dirs = sorted(next(os.walk(render_directory))[1])

                for d in reversed(render_dirs):
                    version_path = os.path.join(render_directory, d)
                    renders = find_renders(version_path)
                    if renders:
                        variants = set()
                        for seq in renders:
                            name = extract_render_name(os.path.basename(str(seq)))
                            variants.add(name.lower())
                        available[t.lower()] = variants
                        break
            except (StopIteration, Exception) as e:
                logger.warning(f"Pass Builder: Error scanning render variants for task '{t}': {e}")

        logger.info(f"Pass Builder: Available denoised render variants: {available}")
        return available

    def _on_ayon_products_fetched(self, result):
        """Override: filter products to only those with available denoised renders."""
        products, available_variants = result

        if available_variants:
            filtered = []
            for p in products:
                task, variant = self._parse_render_product(p["name"])
                if task and variant and task in available_variants and variant.lower() in available_variants[task]:
                    filtered.append(p)

            if filtered:
                logger.info(
                    f"Pass Builder: Showing {len(filtered)} products with denoised renders "
                    f"(of {len(products)} total)"
                )
                products = filtered
            else:
                logger.info("Pass Builder: No products matched available renders, showing all")

        # Delegate to mixin for combo population
        super()._on_ayon_products_fetched(products)

    def _on_publish_product_changed(self, index):
        """Override: capture product name before worker starts (thread safety)."""
        if index >= 0:
            self._current_publish_product_name = self._publish_product_combo.currentText()
        super()._on_publish_product_changed(index)

    def _fetch_product_versions(self, product_id):
        """Override: filter out versions without resolvable denoised work renders."""
        from ayon.service import get_product_version_list

        versions = get_product_version_list(self.app_state.jobname, product_id)
        if not versions:
            return versions

        product_name = getattr(self, '_current_publish_product_name', '')
        derived_task, _ = self._parse_render_product(product_name)
        task = self.app_state.task or derived_task
        if not task:
            return versions

        filtered = []
        for v in versions:
            work_path = self._resolve_work_render_path(v["id"], task)
            if work_path:
                filtered.append(v)
            else:
                logger.info(
                    f"Pass Builder: Hiding version v{v['version']:03d} "
                    "(no denoised work renders found)"
                )

        if not filtered:
            logger.warning(
                "Pass Builder: No versions have denoised work renders, showing all"
            )
            return versions

        logger.info(
            f"Pass Builder: Showing {len(filtered)} of {len(versions)} "
            "versions with denoised renders"
        )
        return filtered

    def _resolve_work_render_path(self, version_id, task):
        """Resolve an AYON version to its work render directory with denoised renders.

        Returns the work render path if denoised renders exist, None otherwise.
        """
        from ayon.service import resolve_version_render_path
        from services.file_operations import get_task_directory, fast_scandir, find_renders
        from core.config import RENDERS_SUBPATH
        from core.utils import truncate_at_suffix

        result = resolve_version_render_path(self.app_state.jobname, version_id)
        if not result:
            return None

        renders_path = result.get("renders_path")
        source_info = result.get("source_dir")

        # Priority 1: renders_path from AYON metadata (set by luma_tools during publish)
        if renders_path and os.path.isdir(renders_path) and find_renders(renders_path):
            return renders_path

        # Priority 2: scene stem from version.attrib.source
        if source_info:
            scene_stem = source_info["stem"]
            task_dir = get_task_directory(self.app_state.shotpath, task)
            if os.path.isdir(task_dir):
                dirs = fast_scandir(task_dir)
                render_folders = [d for d in dirs if RENDERS_SUBPATH in d]
                if render_folders:
                    render_directory = truncate_at_suffix(render_folders[0], RENDERS_SUBPATH)
                    candidate = os.path.join(render_directory, scene_stem)
                    if os.path.isdir(candidate) and find_renders(candidate):
                        return candidate

        return None

    def _resolve_and_scan_publish(self, version_id):
        """Override: resolve AYON publish back to the WORK directory with denoised renders.

        Versions are pre-filtered by _fetch_product_versions to only include those
        with resolvable denoised work renders, so this should always succeed.

        The task is derived from the selected product name (render{Task}{Variant})
        so this works even when no task is selected in the AYON context.
        """
        from services.file_operations import find_renders
        from core.utils import truncate_at_suffix

        product_name = self._publish_product_combo.currentText()
        derived_task, _ = self._parse_render_product(product_name)
        task = self.app_state.task or derived_task
        if not task:
            raise ValueError(
                f"Cannot determine task from product '{product_name}'. "
                "Select a task or choose a render product."
            )

        work_render_path = self._resolve_work_render_path(version_id, task)
        if not work_render_path:
            raise FileNotFoundError(
                "Could not resolve work render directory with denoised renders "
                "for this version."
            )

        logger.info(f"Pass Builder: Resolved work render path: {work_render_path}")

        # Set working_dir for pass file cache
        render_directory = os.path.dirname(work_render_path)
        self.app_state.working_dir = truncate_at_suffix(render_directory, task)

        # Scan for denoised renders
        renders = find_renders(work_render_path)
        if not renders:
            raise FileNotFoundError(f"No denoised renders found in {work_render_path}")

        return work_render_path, renders

    def _on_publish_scan_complete(self, result):
        """Override: Pass Builder stores plain FileSequence objects, not tuples."""
        staging_dir, sequences = result

        self.ui.RenderPath.setText(staging_dir)
        self.app_state.searchpath = staging_dir

        # In publish mode, filter renders to match selected product variant
        if hasattr(self, '_publish_product_combo') and len(sequences) > 1:
            sequences = self._filter_renders_by_product(sequences)

        # Store as plain FileSequence list (Pass Builder convention)
        self.app_state.renders = sequences
        self.ui.BuildPasses.setEnabled(False)

        self.ui.RendersList.clear()
        if sequences:
            for render_seq in sequences:
                self.ui.RendersList.addItem(os.path.basename(str(render_seq)))
            self.ui.RendersList.setEnabled(True)
            self.show_status(f"Found {len(sequences)} render(s)", "info")
            # Auto-select first render after filtering
            self.ui.RendersList.setCurrentRow(0)
        else:
            self.ui.RendersList.addItem("No Renders Found")
            self.ui.RendersList.setEnabled(False)
            self.show_status("No renders at resolved path", "warning")

    @staticmethod
    def _parse_render_product(product_name):
        """Parse AYON render product name into (task, variant).

        Product names follow render{Task}{Variant} CamelCase convention.
        e.g., renderLightingMain → ('lighting', 'Main')
              renderLookdevBeauty → ('lookdev', 'Beauty')

        Returns:
            tuple: (task_lowercase, variant) or ('', '') if not parseable.
        """
        if not product_name or not product_name.startswith("render"):
            return "", ""
        remainder = product_name[6:]  # strip 'render'
        if not remainder:
            return "", ""
        # Split on uppercase boundaries: 'LightingMain' → ['Lighting', 'Main']
        parts = re.findall(r"[A-Z][a-z0-9]*", remainder)
        if len(parts) < 2:
            return "", ""
        return parts[0].lower(), "".join(parts[1:])

    def _filter_renders_by_product(self, sequences):
        """Filter render sequences to match the selected publish product variant.

        Falls back to all sequences if no match is found.
        """
        product_name = self._publish_product_combo.currentText()
        _, variant = self._parse_render_product(product_name)
        if not variant:
            return sequences

        from core.utils import extract_render_name
        filtered = [
            seq for seq in sequences
            if extract_render_name(os.path.basename(str(seq))).lower() == variant.lower()
        ]

        if filtered:
            logger.info(f"Pass Builder: Filtered renders to {len(filtered)} matching variant '{variant}'")
            return filtered

        logger.info(f"Pass Builder: No renders matched variant '{variant}', showing all")
        return sequences

    def _on_scan_renders_clicked(self):
        """Scan for renders when button clicked or version changed."""
        if not self._initialized:
            return

        # If in publish mode, don't do filesystem scan
        if hasattr(self, '_pb_source_manager') and self._pb_source_manager.value == "publish":
            return

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
        denoisedpath = framename

        # Find passes (shows inline spinner automatically)
        if self.app_state.working_dir:
            self.app_state.passesfile = get_pass_file_path(
                self.app_state.working_dir, self.app_state.currentrender
            )
        self._detect_passes(denoisedpath)

        # Populate AYON product selector
        self._populate_product_combo()

    def _detect_passes(self, render_file):
        """Detect passes in render file with spinner animation - runs on background thread."""
        if not hasattr(self, 'passes_spinner'):
            return  # Tab not yet initialized

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

        def on_error(error_msg, traceback_str=""):
            """Called when pass detection fails."""
            self.passes_spinner.stop()
            logger.error(f"Pass detection error: {error_msg}")
            self.ui.BuildPasses.setEnabled(False)
            self.show_status(f"Pass detection failed: {error_msg}", "error")

        # Use BaseTab helper for worker management
        self.start_worker(detect_passes, render_file, on_result=on_result, on_error=on_error)

    def _select_saved_passes(self, passes_file):
        """Select previously saved passes in the UI."""
        from services.render_service import load_pass_config
        from core.user_preferences import get_all_default_passes

        selectedpasses = load_pass_config(passes_file)
        logger.info(f"Loaded passes from file: {selectedpasses}")

        # Select items in UI
        for i in range(self.ui.Passes.count()):
            item = self.ui.Passes.item(i)
            if item.text() in selectedpasses:
                item.setSelected(True)

    def _build_product_name(self, render_name, task=None):
        """Construct AYON product name from render variant using render{Task}{Variant} convention.

        If task is not provided, derives it from app_state.task or the selected
        source product name.
        """
        if not render_name:
            return ""
        if not task:
            task = self.app_state.task
        if not task and hasattr(self, '_publish_product_combo'):
            task, _ = self._parse_render_product(self._publish_product_combo.currentText())
        if not task:
            return ""
        return f"render{task.capitalize()}{render_name.capitalize()}"

    def _populate_product_combo(self):
        """Populate the publish product combo box with existing AYON products.

        Queries AYON for render products in the current shot folder, then
        auto-selects the product that matches the selected render using
        the render{Task}{Variant} naming convention.
        """
        combo = self.ui.PublishProductCombo

        # Use selected render name for product matching
        render_name = self.app_state.currentrender

        # Fallback: in publish mode use source product name if no render selected yet
        if not render_name and hasattr(self, '_publish_product_combo') and hasattr(self, '_pb_source_manager') and self._pb_source_manager.value == "publish":
            render_name = self._publish_product_combo.currentText()

        # Build expected product name using AYON convention: render{Task}{Variant}
        expected_product = self._build_product_name(render_name) if render_name else ""
        combo.setCurrentText(expected_product or render_name)

        # Query AYON for existing products in background
        if not self.app_state.has_shot_context():
            return

        def _query_products():
            from ayon.service import (
                AYON_AVAILABLE, convert_to_ayon_folder_path,
                get_folder_render_products, find_product_for_render,
            )
            if not AYON_AVAILABLE:
                return [], expected_product

            project_name = self.app_state.jobname
            folder_path = convert_to_ayon_folder_path(
                self.app_state.shotpath, project_name
            )
            render_products = get_folder_render_products(project_name, folder_path)
            product_names = [p["name"] for p in render_products]
            matched = find_product_for_render(
                project_name, folder_path, render_name, products=render_products
            ) if render_name else ""
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
            elif expected_product:
                # No AYON match — use constructed name (will be created on publish)
                combo.setCurrentText(expected_product)

        self.start_worker(_query_products, on_result=_on_products)

    def _on_build_passes_clicked(self):
        """Build passes for the selected render, or cancel if already building."""
        from ui_components import StatusColors

        # If already building, cancel the operation
        if getattr(self, '_is_building', False):
            cancel_event = getattr(self, '_cancel_event', None)
            if cancel_event:
                cancel_event.set()
            self.ui.BuildPasses.setEnabled(False)
            self.show_status("Cancelling build...", "warning")
            return

        from services.pass_builder import create_pass_builder
        from services.render_service import save_pass_config
        from core.user_preferences import get_all_default_passes

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
        if self.app_state.passesfile:
            save_pass_config(self.app_state.passesfile, final_channels)
        logger.info(f"Building with passes: {list(final_channels.keys())}")

        # Get build location (Local or Farm)
        build_type = self._build_type
        use_farm = build_type == "farm"

        # Get selected product name (empty string means auto-derive from render name)
        do_publish = self._publish_to_ayon_cb.isChecked()
        selected_product = (self.ui.PublishProductCombo.currentText().strip() or None) if do_publish else None

        # Get display name for status
        build_type_display = "Local" if build_type == "local" else "Farm"

        # Set up cancellation
        self._cancel_event = threading.Event()
        self._is_building = True
        cancel_event = self._cancel_event

        # Show status bar progress (no overlay so user can still interact)
        self.update_status_with_spinner(
            f"Pass Builder: Building passes ({build_type_display})...",
            StatusColors.INFO
        )

        # Switch button to Cancel mode
        self.ui.BuildPasses.setText("Cancel")

        def do_build(progress_callback=None):
            """Run the pass building operation."""
            return create_pass_builder().build_passes(
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
                do_publish=do_publish,
                progress_callback=progress_callback,
                product_name=selected_product,
                cancel_event=cancel_event,
            )

        def on_progress(percent, message):
            """Update status bar with build progress."""
            self.update_status_with_spinner(
                f"Pass Builder: {message} ({percent}%)",
                StatusColors.INFO
            )

        def _reset_button():
            """Reset button to Build state."""
            self._is_building = False
            self.ui.BuildPasses.setText("Build")
            self.ui.BuildPasses.setEnabled(True)

        def on_result(result):
            """Called when build completes."""
            logger.info(f"Build completed: {result}")
            _reset_button()
            self.update_status_with_spinner(
                "Pass Builder: Build completed successfully",
                StatusColors.SUCCESS,
                start=False
            )
            self.show_status("Build completed successfully", "success")

        def on_error(error_msg, traceback_str=""):
            """Called when build fails or is cancelled."""
            _reset_button()

            if cancel_event.is_set():
                self.update_status_with_spinner(
                    "Pass Builder: Build cancelled",
                    StatusColors.WARNING,
                    start=False
                )
                self.show_status("Build cancelled", "warning")
                return

            logger.error(f"Build failed: {error_msg}")
            self.update_status_with_spinner(
                f"Pass Builder failed: {error_msg}",
                StatusColors.ERROR,
                start=False
            )
            self.show_status(f"Build failed: {error_msg}", "error")

        # Use BaseTab helper for worker management
        try:
            self.start_worker(do_build, on_result=on_result, on_error=on_error, on_progress=on_progress)
        except Exception:
            _reset_button()
            raise
