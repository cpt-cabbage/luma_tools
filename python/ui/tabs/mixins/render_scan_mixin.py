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
import threading
from typing import List, Tuple, Callable, Optional, Any

logger = logging.getLogger(__name__)

from core.config import DEFAULT_VIDEOS_DIR, UIStyles
from .publish_source_mixin import PublishSourceMixin


# ---------------------------------------------------------------------------
# Shared task-directory scan cache (G1)
#
# The initial task-directory scan (_scan_render_directory_worker) is identical
# for Pass Builder, MP4 Maker and rePublish. The first tab to run it populates
# this cache (from its worker thread); later tabs reuse the result instantly.
# Invalidated when the user explicitly clicks a Rescan button.
# ---------------------------------------------------------------------------
_task_scan_cache: dict = {}
_task_scan_cache_lock = threading.RLock()


def invalidate_task_scan_cache():
    """Clear the shared task-directory scan cache (called on explicit Rescan)."""
    with _task_scan_cache_lock:
        _task_scan_cache.clear()


# ---------------------------------------------------------------------------
# Scan-generation helpers
#
# Guard against stale worker results populating a list after a newer scan has
# started (e.g. rapid version spinbox changes). Implemented as module-level
# functions so tabs that do not inherit RenderScanMixin (Pass Builder) can
# reuse them.
# ---------------------------------------------------------------------------
def begin_scan_generation(obj) -> int:
    """Increment and return obj's scan generation counter (main thread only)."""
    obj._scan_generation = getattr(obj, '_scan_generation', 0) + 1
    return obj._scan_generation


def is_current_scan(obj, generation: int) -> bool:
    """Return True if `generation` is still the newest scan for obj."""
    return getattr(obj, '_scan_generation', 0) == generation


def connect_debounced(signal, slot, ms: int = 350):
    """Connect a signal to a slot through a single-shot restartable QTimer.

    Rapid signal emissions (e.g. version spinbox changes) restart the timer,
    so `slot` only fires `ms` after the last emission.

    Returns the QTimer — the caller MUST store it on a long-lived object to
    prevent garbage collection.
    """
    from PySide6.QtCore import QTimer

    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(ms)
    timer.timeout.connect(slot)
    signal.connect(lambda *_args: timer.start())
    return timer


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

    # ── Scan-generation / debounce / rescan helpers ─────────────────────

    def _begin_scan_generation(self) -> int:
        """Start a new scan generation, invalidating in-flight scan results."""
        return begin_scan_generation(self)

    def _is_current_scan(self, generation: int) -> bool:
        """Return True if `generation` is still the newest scan."""
        return is_current_scan(self, generation)

    def _connect_debounced(self, signal, slot, ms: int = 350):
        """Connect signal → slot through a ~ms single-shot debounce timer.

        The timer is stored on self to prevent garbage collection.
        """
        timer = connect_debounced(signal, slot, ms)
        if not hasattr(self, '_debounce_timers'):
            self._debounce_timers = []
        self._debounce_timers.append(timer)
        return timer

    def _on_rescan_clicked(self):
        """Explicit Rescan button handler: invalidate shared cache, then scan."""
        invalidate_task_scan_cache()
        self._on_scan_renders_clicked()

    def _on_scan_renders_clicked(self):
        """
        Default scan implementation using _scan_renders_base().
        Override if tab needs completely custom scanning logic.
        """
        if not hasattr(self, '_source_manager'):
            return  # Called before initialize() — ignore
        if self._source == "publish":
            # Invalidate any in-flight filesystem scan so its stale results
            # cannot land on top of the publish-mode list.
            self._begin_scan_generation()
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

        The path existence check and scan run on a worker thread (network
        paths can stall for seconds); list population happens on the main
        thread in the result handler. Stale results from superseded scans
        are dropped via the scan-generation counter.

        Args:
            scan_func: Function that takes a path and returns list of render sequences
            status_prefix: Prefix for status messages (e.g., "MP4 Maker")
        """
        from ui_components import StatusColors
        from core.utils import update_path_version

        # Get widgets
        render_list = self.get_widget(self._render_list_widget)
        render_path = self.get_widget(self._render_path_widget)
        version_widget = self.get_widget(self._version_widget)
        action_button = self.get_widget(self._action_button)

        if not render_list:
            return

        # Show scanning status with spinner
        self.update_status_with_spinner(
            f"{status_prefix}: Scanning..." if status_prefix else "Scanning...",
            StatusColors.INFO
        )

        render_list.clear()
        render_list.setEnabled(False)

        # Get and update search path (UI reads stay on the main thread)
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

        # Determine search path based on source (main thread)
        source = self._source
        if source == "for_comp":
            output_subdir = getattr(self.app_state, 'output_subdirectory', '')
            search_path = os.path.join(searchpath, output_subdir) if output_subdir else searchpath
            subdir_label = output_subdir or "root"
        elif source == "raw":
            search_path = searchpath
            subdir_label = "raw"
        elif source == "custom":
            search_path = getattr(self.app_state, self._custom_path_attr, "")
            subdir_label = "custom"
        else:
            search_path = ""
            subdir_label = ""

        logger.debug(f"{status_prefix}: Scanning {subdir_label}: {search_path}")

        # Disable action button until selection
        if action_button:
            action_button.setEnabled(False)

        generation = self._begin_scan_generation()

        def _scan_worker(path=search_path, label=subdir_label):
            """Path check + scan in background thread (network paths can stall)."""
            renders = []
            if path and os.path.exists(path):
                for render_seq in scan_func(path):
                    renders.append((label, render_seq))
            return renders

        def _on_scan_result(renders):
            if not self._is_current_scan(generation):
                return  # A newer scan superseded this one — drop stale results
            render_list.clear()
            setattr(self.app_state, self._renders_attr, renders)
            logger.info(f"{status_prefix}: Found {len(renders)} sequence(s)")
            if renders:
                for subdir, render_seq in renders:
                    render_list.addItem(os.path.basename(str(render_seq)))
                render_list.setEnabled(True)
                self.update_status_with_spinner(
                    f"Found {len(renders)} sequence(s)", StatusColors.INFO, start=False
                )
            else:
                render_list.addItem("No Renders Found")
                render_list.setEnabled(False)
                self.update_status_with_spinner(
                    "No sequences found", StatusColors.WARNING, start=False
                )

        def _on_scan_error(error_msg, traceback_str=""):
            if not self._is_current_scan(generation):
                return
            logger.error(f"{status_prefix}: Scan error: {error_msg}")
            setattr(self.app_state, self._renders_attr, [])
            render_list.clear()
            render_list.addItem("Scan error")
            render_list.setEnabled(False)
            self.update_status_with_spinner(
                f"Scan error: {error_msg}", StatusColors.ERROR, start=False
            )

        self.start_worker(_scan_worker, on_result=_on_scan_result, on_error=_on_scan_error)

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
    def _scan_render_directory_worker(task_dir, task, use_cache=True):
        """Scan a task directory for the latest render version (worker thread).

        Shared by Pass Builder, MP4 Maker and rePublish initial scans. Returns
        ``{'latest_render', 'render_directory'}`` or None if nothing found.

        Results are cached in a shared module-level cache keyed by
        ``(task_dir, task)`` — the first tab pays for the network scan, later
        tabs reuse the result instantly. Pass ``use_cache=False`` (or click
        Rescan, which clears the cache) to force a fresh scan.
        """
        from services.file_operations import fast_scandir, find_renders, find_hip_files
        from core.config import RENDERS_SUBPATH
        from core.utils import truncate_at_suffix, version_sort_key

        cache_key = (os.path.normcase(os.path.normpath(task_dir)), (task or "").lower())
        if use_cache:
            with _task_scan_cache_lock:
                if cache_key in _task_scan_cache:
                    logger.debug(f"Render scan: cache hit for {cache_key}")
                    return _task_scan_cache[cache_key]

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

        result = {
            "latest_render": latest_render,
            "render_directory": render_directory,
        }
        # Cache only successful scans — a None result (empty/new task dir)
        # should be retried by the next tab rather than pinned.
        with _task_scan_cache_lock:
            _task_scan_cache[cache_key] = result
        return result

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
