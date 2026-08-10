"""
Render Scan Mixin for tabs that work with render sequences.

Provides common functionality for:
- Source selection via OptionButtonManager (for_comp, raw, custom, publish)
- Version handling
- Render scanning and list population
- Custom path browsing
- AYON publish-based render selection
- Selection handling with frame range extraction

Usage:
    class MyRenderTab(RenderScanMixin, BaseTab):
        # Define widget names
        _render_list_widget = "MyRendersList"
        _render_path_widget = "MyRenderPath"
        _version_widget = "MyCurrentVer"
        _action_button = "MyActionButton"
        _source_button = "MySourceButton"
        _custom_path_label = "MyCustomPathLabel"
        _browse_custom_button = "MyBrowseCustomPath"

        # Define app_state attributes
        _renders_attr = "my_renders"
        _searchpath_attr = "my_searchpath"
        _custom_path_attr = "my_custom_path"

        def _get_source_options(self):
            return [("For Comp", "for_comp"), ("Raw", "raw"), ("Custom", "custom")]
"""
import logging
import os
from typing import List, Tuple, Callable, Optional, Any

logger = logging.getLogger(__name__)

from core.config import DEFAULT_VIDEOS_DIR, UIStyles
from .publish_source_mixin import PublishSourceMixin


class RenderScanMixin(PublishSourceMixin):
    """Mixin providing render scanning functionality for tabs."""

    # Widget names - subclasses should override these
    _render_list_widget: str = "RendersList"
    _render_path_widget: str = "RenderPath"
    _version_widget: str = "CurrentVer"
    _version_label_widget: str = ""  # Version label to hide in publish mode
    _action_button: str = "ActionButton"
    _source_button: str = "SourceButton"
    _custom_path_label: str = "CustomPathLabel"
    _browse_custom_button: str = "BrowseCustomPath"

    # app_state attribute names - subclasses should override these
    _renders_attr: str = "renders"
    _searchpath_attr: str = "searchpath"
    _custom_path_attr: str = "custom_path"

    def _get_source_options(self) -> List[Tuple[str, str]]:
        """
        Return source options as list of (label, value) tuples.
        Override in subclass to customize.
        """
        from core.import_utils import safe_import
        ayon_service, _ = safe_import("ayon.service")

        options = [
            ("For Comp", "for_comp"),
            ("Raw", "raw"),
            ("Custom", "custom"),
        ]
        ayon_available = getattr(ayon_service, 'AYON_AVAILABLE', False) if ayon_service else False
        if ayon_available and self.app_state.has_ayon_context():
            options.append(("Publish", "publish"))
        return options

    def _get_initial_source(self) -> str:
        """Return the initial source value. Defaults to Publish when AYON available."""
        from core.import_utils import safe_import
        ayon_service, _ = safe_import("ayon.service")
        ayon_available = getattr(ayon_service, 'AYON_AVAILABLE', False) if ayon_service else False
        if ayon_available and self.app_state.has_ayon_context():
            return "publish"
        return "for_comp"

    def _init_source_manager(self):
        """Initialize the source OptionButtonManager. Call from initialize()."""
        from option_button import OptionButtonManager

        self._source_manager = OptionButtonManager(
            button=self.get_widget(self._source_button),
            options=self._get_source_options(),
            initial_value=self._get_initial_source(),
            on_changed=self._on_source_changed,
            label_prefix="Source: ",
            parent_window=self.main_window,
            label_func=self._get_source_label
        )

    def _get_source_label(self, value: str) -> str:
        """
        Get dynamic display label for a source value.
        Override in subclass for custom label logic.
        """
        if value == "for_comp" and getattr(self.app_state, 'output_subdirectory', ''):
            return self.app_state.output_subdirectory.title()
        label_map = {v: l for l, v in self._get_source_options()}
        return label_map.get(value, value)

    @property
    def _source(self) -> str:
        """Current source selection value."""
        return self._source_manager.value

    def _update_source_button_text(self):
        """Refresh the source button text via the manager."""
        if hasattr(self, '_source_manager'):
            self._source_manager.refresh_text()

    def _on_source_changed(self, value=None):
        """
        Handle source type change.
        Override in subclass for custom visibility logic (call super first).
        Default: toggle custom path visibility and trigger scan.
        """
        is_custom = self._source == "custom"
        is_publish = self._source == "publish"

        # Show/hide custom path controls
        browse_button = self.get_widget(self._browse_custom_button)
        custom_label = self.get_widget(self._custom_path_label)

        if browse_button:
            browse_button.setVisible(is_custom)
        if custom_label:
            custom_label.setVisible(is_custom)

        # Toggle version spinbox vs publish combos
        version_widget = self.get_widget(self._version_widget)
        if version_widget:
            version_widget.setVisible(not is_publish)

        # Hide version label in publish mode
        if self._version_label_widget:
            version_label = self.get_widget(self._version_label_widget)
            if version_label:
                version_label.setVisible(not is_publish)

        # Toggle publish product/version combos
        self._show_publish_widgets(is_publish)

        # Trigger appropriate scan
        if is_publish:
            self._on_publish_source_selected()
        else:
            self._on_scan_renders_clicked()

    def _on_browse_custom_path(self):
        """Browse for custom directory containing render sequences."""
        from file_dialogs import browse_directory_with_memory

        context = f"{self.tab_id}_custom"
        custom_dir = browse_directory_with_memory(
            self.main_window,
            context=context,
            title="Select Directory with Render Sequences",
            fallback_path=DEFAULT_VIDEOS_DIR
        )

        if custom_dir:
            # Store in app_state
            setattr(self.app_state, self._custom_path_attr, custom_dir)

            # Update label
            custom_label = self.get_widget(self._custom_path_label)
            if custom_label:
                custom_label.setText(f"Custom path: {custom_dir}")
                custom_label.setStyleSheet(UIStyles.LABEL_PATH)

            logger.info(f"{self.tab_name}: Custom path set to: {custom_dir}")
            self.show_status(f"Custom: {os.path.basename(custom_dir)}", "info")
            self._on_scan_renders_clicked()

    def _on_scan_renders_clicked(self):
        """
        Default scan implementation using _scan_renders_base().
        Override if tab needs completely custom scanning logic.
        """
        if not hasattr(self, '_source_manager'):
            return  # Called before initialize() — ignore
        if self._source == "publish":
            self._on_publish_source_selected()
            return
        from core.utils import scan_exr_sequences
        self._scan_renders_base(scan_exr_sequences, self.tab_name)

    def _scan_renders_base(
        self,
        scan_func: Callable[[str], List[Any]],
        status_prefix: str = ""
    ):
        """
        Base render scanning implementation.

        Args:
            scan_func: Function that takes a path and returns list of render sequences
            status_prefix: Prefix for status messages (e.g., "MP4 Maker")
        """
        from core.utils import update_path_version

        # Show scanning status
        self.show_status(f"{status_prefix}: Scanning...", "info")

        # Get widgets
        render_list = self.get_widget(self._render_list_widget)
        render_path = self.get_widget(self._render_path_widget)
        version_widget = self.get_widget(self._version_widget)
        action_button = self.get_widget(self._action_button)

        if not render_list:
            return

        render_list.clear()

        # Get and update search path
        searchpath = getattr(self.app_state, self._searchpath_attr, "")
        if render_path:
            searchpath = render_path.text() or searchpath

        # Handle version change
        if searchpath and version_widget:
            new_ver = version_widget.value()
            searchpath = update_path_version(searchpath, new_ver)
            if render_path:
                render_path.setText(searchpath)
            setattr(self.app_state, self._searchpath_attr, searchpath)

        # Update source button text
        self._update_source_button_text()

        # Determine search path based on source
        renders = []

        if self._source == "for_comp":
            output_subdir = getattr(self.app_state, 'output_subdirectory', '')
            search_path = os.path.join(searchpath, output_subdir) if output_subdir else searchpath
            logger.debug(f"{status_prefix}: Scanning {output_subdir or 'root'}: {search_path}")
            if os.path.exists(search_path):
                found = scan_func(search_path)
                for render_seq in found:
                    renders.append((output_subdir or "root", render_seq))

        elif self._source == "raw":
            logger.debug(f"{status_prefix}: Scanning raw path: {searchpath}")
            if os.path.exists(searchpath):
                found = scan_func(searchpath)
                for render_seq in found:
                    renders.append(("raw", render_seq))

        elif self._source == "custom":
            custom_path = getattr(self.app_state, self._custom_path_attr, "")
            logger.debug(f"{status_prefix}: Scanning custom path: {custom_path}")
            if custom_path and os.path.exists(custom_path):
                found = scan_func(custom_path)
                for render_seq in found:
                    renders.append(("custom", render_seq))

        # Store renders
        setattr(self.app_state, self._renders_attr, renders)

        # Disable action button until selection
        if action_button:
            action_button.setEnabled(False)

        # Populate list
        logger.info(f"{status_prefix}: Found {len(renders)} sequence(s)")
        if renders:
            for subdir, render_seq in renders:
                display_name = os.path.basename(str(render_seq))
                render_list.addItem(display_name)
            render_list.setEnabled(True)
            self.show_status(f"Found {len(renders)} sequence(s)", "info")
        else:
            render_list.addItem("No Renders Found")
            render_list.setEnabled(False)
            self.show_status("No sequences found", "warning")

    def _get_selected_render(self) -> Optional[Tuple[str, Any]]:
        """
        Get the currently selected render.

        Returns:
            Tuple of (subdir, render_sequence) or None if nothing selected
        """
        render_list = self.get_widget(self._render_list_widget)
        renders = getattr(self.app_state, self._renders_attr, [])

        if not render_list:
            return None

        sel_idx = render_list.currentRow()
        if sel_idx < 0 or sel_idx >= len(renders):
            return None

        return renders[sel_idx]

    def _scan_publish_directory(self, staging_dir):
        """Scan resolved AYON staging directory for EXR sequences."""
        from core.utils import scan_exr_sequences
        return scan_exr_sequences(staging_dir)

    @staticmethod
    def _scan_render_directory_worker(task_dir, task):
        """Scan a task directory for the latest render version (worker thread).

        Shared by Pass Builder and rePublish initial scans. Returns
        ``{'latest_render', 'render_directory'}`` or None if nothing found.
        """
        from services.file_operations import fast_scandir, find_renders, find_hip_files
        from core.config import RENDERS_SUBPATH
        from core.utils import truncate_at_suffix, version_sort_key

        try:
            dirs = fast_scandir(task_dir)
        except Exception as e:
            logger.warning(f"Render scan: error in {task_dir}: {e}")
            return None

        render_folders = [d for d in dirs if RENDERS_SUBPATH in d]
        if not render_folders:
            return None

        render_directory = truncate_at_suffix(render_folders[0], RENDERS_SUBPATH)

        hip_files = find_hip_files(task_dir, task)
        hip_file = ""
        if hip_files:
            hip_file = sorted(hip_files)[0].rsplit("_", 1)[0]

        try:
            # Numeric-aware sort so "latest" is v10, not v9, for unpadded names
            render_dirs = sorted(next(os.walk(render_directory))[1], key=version_sort_key)
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
            if find_renders(version_path):
                latest_render = render_version
                break
        if not latest_render:
            latest_render = render_dirs[-1]

        return {
            "latest_render": latest_render,
            "render_directory": render_directory,
        }

    def _get_selected_frame_range(self) -> Optional[Tuple[int, int]]:
        """
        Get frame range of the currently selected render.

        Returns:
            Tuple of (start_frame, end_frame) or None
        """
        selected = self._get_selected_render()
        if not selected:
            return None

        subdir, render_seq = selected
        return (render_seq.start(), render_seq.end())
