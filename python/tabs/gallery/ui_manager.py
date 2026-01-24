"""
Gallery UI Manager.

Handles UI controls for the gallery:
- Sort button and mode selection
- Filter button (show/hide inputs)
- View mode toggle (grid/stacked by job)
- User selector for multi-user gallery viewing
"""

import os
from PySide6.QtWidgets import QPushButton, QMenu, QCheckBox
from PySide6.QtCore import QThreadPool

from .base_manager import BaseGalleryManager


class UIManager(BaseGalleryManager):
    """Manages UI controls for the gallery."""

    def __init__(self, tab):
        """
        Initialize the UI manager.

        Args:
            tab: Reference to the ComfyUIGalleryTab
        """
        super().__init__(tab)

        # Sort options
        self._sort_options = [
            ("Date (Newest)", "date_desc"),
            ("Date (Oldest)", "date_asc"),
            ("Name (A-Z)", "name_asc"),
            ("Name (Z-A)", "name_desc"),
            ("Workflow", "workflow"),
        ]

    def setup_ui(self):
        """Set up additional UI elements."""
        self._create_filter_button()
        self._create_view_mode_button()
        self.update_sort_button_text()

    # =========================================================================
    # SORT CONTROLS
    # =========================================================================

    def update_sort_button_text(self):
        """Update the sort button text to show current mode."""
        mode_map = {mode: label for label, mode in self._sort_options}
        current_label = mode_map.get(self.tab._sort_mode, "Sort")
        self.tab.ui.GallerySortButton.setText(f"Sort: {current_label}")

    def on_sort_button_clicked(self):
        """Show sort options menu."""
        menu = QMenu(self.tab.ui.GallerySortButton)

        for label, mode in self._sort_options:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == self.tab._sort_mode)
            action.triggered.connect(lambda checked, m=mode: self._select_sort_mode(m))

        # Position menu below button
        pos = self.tab.ui.GallerySortButton.mapToGlobal(
            self.tab.ui.GallerySortButton.rect().bottomLeft()
        )
        menu.exec_(pos)

    def _select_sort_mode(self, mode):
        """Apply selected sort mode."""
        if mode == self.tab._sort_mode:
            return

        self.tab._sort_mode = mode
        self.update_sort_button_text()

        # Save to settings
        from core.user_preferences import save_gallery_settings
        save_gallery_settings(sort_mode=mode)

        # Show status feedback
        mode_labels = {m: label for label, m in self._sort_options}
        label = mode_labels.get(mode, mode)
        if hasattr(self.tab, 'show_status_message'):
            self.tab.show_status_message(f"Gallery sorted by {label}")

        # Re-sort and redisplay (use cached items, no rescan needed)
        self._redisplay_items()

    # =========================================================================
    # FILTER CONTROLS
    # =========================================================================

    def _create_filter_button(self):
        """Create the show inputs checkbox toggle."""
        from PySide6.QtCore import Qt
        self._filter_checkbox = QCheckBox("Show Inputs")
        self._filter_checkbox.setObjectName("filterToggleCheckbox")
        self._filter_checkbox.setCursor(Qt.ArrowCursor)
        self._filter_checkbox.setChecked(self.tab._show_inputs)
        self._filter_checkbox.setToolTip("Show/hide input source images")
        self._filter_checkbox.toggled.connect(self._on_filter_toggle)

        # Insert after sort button in the header layout
        header_layout = self._find_header_layout()
        if header_layout:
            sort_index = header_layout.indexOf(self.tab.ui.GallerySortButton)
            header_layout.insertWidget(sort_index + 1, self._filter_checkbox)

    def _find_header_layout(self):
        """Find the header layout that contains the sort button."""
        # self.tab.ui is the root widget loaded from the .ui file
        # Get the main layout (galleryMainLayout) from the root widget
        main_layout = self.tab.ui.layout()

        if main_layout:
            # galleryHeaderLayout is the first item in the main vertical layout
            for i in range(main_layout.count()):
                item = main_layout.itemAt(i)
                if item.layout():
                    # Check if this layout contains the sort button
                    nested_layout = item.layout()
                    if nested_layout.indexOf(self.tab.ui.GallerySortButton) >= 0:
                        return nested_layout
        return None

    def _on_filter_toggle(self, checked):
        """Toggle input file visibility."""
        self.tab._show_inputs = checked

        # Save to settings
        from core.user_preferences import save_gallery_settings
        save_gallery_settings(show_inputs=checked)

        # Show status feedback
        if hasattr(self.tab, 'show_status_message'):
            status = "shown" if checked else "hidden"
            self.tab.show_status_message(f"Input images {status}")

        # Re-filter and redisplay from cached items (no rescan needed)
        self._redisplay_items()

    # =========================================================================
    # VIEW MODE CONTROLS
    # =========================================================================

    # Stacking mode options (groups shown via sidebar filter, not stacking)
    STACKING_MODES = [
        ("Grid", "grid"),
        ("Stacked", "job"),
    ]

    def _create_view_mode_button(self):
        """Create the stacking mode dropdown button."""
        from PySide6.QtCore import Qt

        # Get current stacking mode from settings
        from core.settings_manager import get_setting
        current_mode = get_setting("gallery_stacking_mode")

        self._stacking_btn = QPushButton()
        self._stacking_btn.setObjectName("stackingModeButton")
        self._stacking_btn.setCursor(Qt.ArrowCursor)
        self._stacking_btn.setToolTip("Change how items are grouped in the gallery")
        self._stacking_btn.clicked.connect(self._on_stacking_button_clicked)
        self._update_stacking_button_text(current_mode)

        # Insert after filter checkbox in the header layout
        header_layout = self._find_header_layout()
        if header_layout:
            filter_index = header_layout.indexOf(self._filter_checkbox)
            header_layout.insertWidget(filter_index + 1, self._stacking_btn)

    def _update_stacking_button_text(self, mode):
        """Update the stacking button text based on current mode."""
        mode_labels = {m: label for label, m in self.STACKING_MODES}
        label = mode_labels.get(mode, "Grid")
        self._stacking_btn.setText(f"View: {label}")

    def _on_stacking_button_clicked(self):
        """Show stacking mode menu."""
        from core.settings_manager import get_setting
        current_mode = get_setting("gallery_stacking_mode")

        menu = QMenu(self._stacking_btn)
        for label, mode in self.STACKING_MODES:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == current_mode)
            action.triggered.connect(lambda checked, m=mode: self._select_stacking_mode(m))

        pos = self._stacking_btn.mapToGlobal(self._stacking_btn.rect().bottomLeft())
        menu.exec_(pos)

    def _select_stacking_mode(self, mode):
        """Apply selected stacking mode."""
        from core.settings_manager import get_setting, set_setting
        current_mode = get_setting("gallery_stacking_mode")

        if mode == current_mode:
            return

        set_setting("gallery_stacking_mode", mode, verbose=False)
        self._update_stacking_button_text(mode)

        # Show status feedback
        mode_labels = {m: label for label, m in self.STACKING_MODES}
        label = mode_labels.get(mode, mode)
        if hasattr(self.tab, 'show_status_message'):
            self.tab.show_status_message(f"View mode: {label}")

        # Update view mode for backward compatibility
        # grid mode = "grid", all others = "stacked"
        new_view_mode = "grid" if mode == "grid" else "stacked"
        if self.tab._view_mode != new_view_mode:
            self.tab._view_mode = new_view_mode
            from core.user_preferences import save_gallery_settings
            save_gallery_settings(view_mode=new_view_mode)

        # Redisplay with new stacking mode (force rebuild since view mode changed)
        self._redisplay_items(force_rebuild=True)

    def _redisplay_items(self, force_rebuild=False):
        """Redisplay items with current sort/filter/view settings.

        Uses smart detection to avoid full rebuilds when only sort order changed.

        Args:
            force_rebuild: If True, always do a full widget rebuild
        """
        if not self.tab._cached_items:
            return

        # Apply filter and sort
        filtered_items = self.tab._filter_items(self.tab._cached_items)
        sorted_items = self.tab._manager.sort_items(filtered_items, self.tab._sort_mode)

        # Get current state for comparison
        current_paths = set(item['path'] for item in sorted_items)
        cached_paths = getattr(self.tab, '_last_displayed_paths', set())
        last_view_mode = getattr(self.tab, '_last_view_mode', None)

        # Determine if we can use fast reordering (grid mode only, same visible items, same view mode)
        # Note: widget_cache may contain hidden widgets from previous filters, so we check
        # against cached_paths (visible paths) not cache size
        can_reorder = (
            not force_rebuild
            and self.tab._view_mode == "grid"
            and last_view_mode == "grid"
            and current_paths == cached_paths
            and hasattr(self.tab, '_widget_cache')
            and current_paths <= set(self.tab._widget_cache.keys())
        )

        if can_reorder:
            # Fast path: just reorder existing widgets without recreation
            self.tab._manager.reorder_widgets(sorted_items)
        else:
            # display_items handles widget recycling for filter changes automatically
            self.tab._manager.display_items(sorted_items, self.tab._view_mode)

        # Update tracking state
        self.tab._last_displayed_paths = current_paths
        self.tab._last_view_mode = self.tab._view_mode

        # Update ordered list for shift-select
        self.tab._visible_items_ordered = [item['path'] for item in sorted_items]

    # =========================================================================
    # USER SELECTION
    # =========================================================================

    def populate_user_selector(self):
        """Initialize user selector with async discovery."""
        from ui_components import Worker

        def discover_users():
            return self._discover_users_sync()

        self._user_discovery_worker = Worker(discover_users)
        self._user_discovery_worker.signals.result.connect(self._on_users_discovered)
        QThreadPool.globalInstance().start(self._user_discovery_worker)

    def _discover_users_sync(self):
        """Discover available users from the network gallery path.

        Uses inclusive approach: only shows directories that match known users
        from the admin_users and sup_users lists in global settings.
        """
        users = []
        base_path = self.tab._get_network_user_path(username="")

        # Get known users from global settings (admins and supervisors)
        from core.settings_manager import get_admin_users, get_sup_users
        known_users = set()
        for user in get_admin_users():
            known_users.add(user.lower())
        for user in get_sup_users():
            known_users.add(user.lower())

        # Always include current user
        current_user = self.tab.app_state.user
        if current_user:
            known_users.add(current_user.lower())

        if base_path and os.path.exists(base_path):
            try:
                # List directories that match known users
                for name in os.listdir(base_path):
                    full_path = os.path.join(base_path, name)
                    if os.path.isdir(full_path) and name.lower() in known_users:
                        users.append(name)
            except Exception as e:
                self.tab.log(f"[Gallery] Error discovering users: {e}")

        return sorted(users, key=str.lower)

    def _on_users_discovered(self, users):
        """Handle user discovery completion."""
        self.tab._available_users = users
        self._update_user_button_visibility()

    def update_user_button_text(self):
        """Update user selector button text."""
        if self.tab._selected_user == self.tab.app_state.user:
            self.tab.ui.GalleryUserButton.setText(f"👤 {self.tab._selected_user} (You)")
        else:
            self.tab.ui.GalleryUserButton.setText(f"👤 {self.tab._selected_user}")

    def _update_user_button_visibility(self):
        """Show/hide user button based on available users."""
        # Show if there are other users
        has_other_users = len(self.tab._available_users) > 1
        self.tab.ui.GalleryUserButton.setVisible(has_other_users)

    def on_user_button_clicked(self):
        """Show user selection menu."""
        menu = QMenu(self.tab.ui.GalleryUserButton)

        # Add current user at top
        current_user = self.tab.app_state.user
        action = menu.addAction(f"👤 {current_user} (You)")
        action.setCheckable(True)
        action.setChecked(self.tab._selected_user == current_user)
        action.triggered.connect(lambda: self._select_user(current_user))

        if self.tab._available_users:
            menu.addSeparator()

            # Add other users
            for user in self.tab._available_users:
                if user != current_user:
                    action = menu.addAction(f"👤 {user}")
                    action.setCheckable(True)
                    action.setChecked(self.tab._selected_user == user)
                    action.triggered.connect(lambda checked, u=user: self._select_user(u))

        pos = self.tab.ui.GalleryUserButton.mapToGlobal(
            self.tab.ui.GalleryUserButton.rect().bottomLeft()
        )
        menu.exec_(pos)

    def _select_user(self, new_user):
        """Switch to viewing another user's gallery."""
        if new_user == self.tab._selected_user:
            return

        self.tab._selected_user = new_user
        self.update_user_button_text()

        # Update gallery path
        self.tab._update_gallery_path(reset_tracking=True)

        # Show/hide "View Only" indicator
        self._update_view_only_indicator()

        # Show status feedback
        if hasattr(self.tab, 'show_status_message'):
            if new_user == self.tab.app_state.user:
                self.tab.show_status_message("Viewing your gallery")
            else:
                self.tab.show_status_message(f"Viewing {new_user}'s gallery")

        # Refresh gallery
        self.tab._refresh_controller.on_refresh(force=True)

    def _update_view_only_indicator(self):
        """Show/hide the 'View Only' indicator based on whose gallery is shown."""
        is_own = self.tab._is_own_gallery()
        self.tab.ui.GalleryViewOnlyLabel.setVisible(not is_own)
