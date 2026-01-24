"""
Render Scan Mixin for tabs that work with render sequences.

Provides common functionality for:
- Source selection (for_comp, raw, custom)
- Version handling
- Render scanning and list population
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

import os
from typing import List, Tuple, Callable, Optional, Any


class RenderScanMixin:
    """Mixin providing render scanning functionality for tabs."""

    # Widget names - subclasses should override these
    _render_list_widget: str = "RendersList"
    _render_path_widget: str = "RenderPath"
    _version_widget: str = "CurrentVer"
    _action_button: str = "ActionButton"
    _source_button: str = "SourceButton"
    _custom_path_label: str = "CustomPathLabel"
    _browse_custom_button: str = "BrowseCustomPath"

    # app_state attribute names - subclasses should override these
    _renders_attr: str = "renders"
    _searchpath_attr: str = "searchpath"
    _custom_path_attr: str = "custom_path"

    # Internal state
    _source: str = "for_comp"

    def _get_source_options(self) -> List[Tuple[str, str]]:
        """
        Return source options as list of (label, value) tuples.
        Override in subclass to customize.
        """
        return [
            ("For Comp", "for_comp"),
            ("Raw", "raw"),
            ("Custom", "custom"),
        ]

    def _init_render_scan_state(self):
        """Initialize render scan state. Call from initialize()."""
        self._source = "for_comp"
        self._update_source_button_text()

    def _get_source_button_label(self, source: str) -> str:
        """
        Get display label for a source value.
        Override in subclass for custom label logic.
        """
        options = self._get_source_options()
        label = next((l for l, v in options if v == source), source)

        # Special handling for for_comp
        if source == "for_comp" and hasattr(self.app_state, 'output_subdirectory'):
            if self.app_state.output_subdirectory:
                label = self.app_state.output_subdirectory.title()

        return label

    def _update_source_button_text(self):
        """Update source button text to show current selection."""
        source_button = self.get_widget(self._source_button)
        if source_button:
            label = self._get_source_button_label(self._source)
            source_button.setText(f"Source: {label}")

    def _on_source_button_clicked(self):
        """Show popup menu with source options."""
        from small_widgets import show_popup_menu

        source_button = self.get_widget(self._source_button)
        if not source_button:
            return

        # Build display options with dynamic labels
        display_options = []
        for label, value in self._get_source_options():
            display_label = self._get_source_button_label(value) if value == "for_comp" else label
            display_options.append((display_label, value))

        result = show_popup_menu(
            self.main_window,
            source_button,
            display_options,
            current=self._source
        )

        if result is not None:
            self._source = result
            self._update_source_button_text()
            self._on_source_changed()

    def _on_source_changed(self):
        """
        Handle source type change.
        Override in subclass for custom behavior.
        Default: toggle custom path visibility and trigger scan.
        """
        is_custom = self._source == "custom"

        # Show/hide custom path controls
        browse_button = self.get_widget(self._browse_custom_button)
        custom_label = self.get_widget(self._custom_path_label)

        if browse_button:
            browse_button.setVisible(is_custom)
        if custom_label:
            custom_label.setVisible(is_custom)

        # Trigger scan
        self._on_scan_renders_clicked()

    def _on_browse_custom_path(self):
        """Browse for custom directory."""
        from file_dialogs import browse_directory_with_memory

        context = f"{self.tab_id}_custom"
        custom_dir = browse_directory_with_memory(
            self.main_window,
            context=context,
            title="Select Directory with Render Sequences",
            fallback_path=os.path.join(os.path.expanduser("~"), "Videos")
        )

        if custom_dir:
            # Store in app_state
            setattr(self.app_state, self._custom_path_attr, custom_dir)

            # Update label
            custom_label = self.get_widget(self._custom_path_label)
            if custom_label:
                custom_label.setText(f"Custom path: {custom_dir}")
                custom_label.setStyleSheet("color: white; font-size: 9pt;")

            self.log(f"{self.tab_name}: Custom path set to: {custom_dir}")

            self.show_status(f"Custom: {os.path.basename(custom_dir)}", "info")

            self._on_scan_renders_clicked()

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
            self.log(f"{status_prefix}: Scanning {output_subdir or 'root'}: {search_path}")
            if os.path.exists(search_path):
                found = scan_func(search_path)
                for render_seq in found:
                    renders.append((output_subdir or "root", render_seq))

        elif self._source == "raw":
            self.log(f"{status_prefix}: Scanning raw path: {searchpath}")
            if os.path.exists(searchpath):
                found = scan_func(searchpath)
                for render_seq in found:
                    renders.append(("raw", render_seq))

        elif self._source == "custom":
            custom_path = getattr(self.app_state, self._custom_path_attr, "")
            self.log(f"{status_prefix}: Scanning custom path: {custom_path}")
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
        self.log(f"{status_prefix}: Found {len(renders)} sequence(s)")
        if renders:
            for subdir, render_seq in renders:
                display_name = str(render_seq).split("\\")[-1]
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
