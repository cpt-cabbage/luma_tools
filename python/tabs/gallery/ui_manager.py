"""
Gallery UI Manager.

Handles UI controls for the gallery:
- Sort button and mode selection
- Filter button (show/hide inputs)
- View mode toggle (stacked/grid/sections)
- User selector for multi-user gallery viewing
"""

import os
from PySide6.QtWidgets import QPushButton, QMenu, QCheckBox
from PySide6.QtCore import QThreadPool


class UIManager:
    """Manages UI controls for the gallery."""

    def __init__(self, tab):
        """
        Initialize the UI manager.

        Args:
            tab: Reference to the ComfyUIGalleryTab
        """
        self.tab = tab

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

        # Re-filter and redisplay from cached items (no rescan needed)
        self._redisplay_items()

    # =========================================================================
    # VIEW MODE CONTROLS
    # =========================================================================

    def _create_view_mode_button(self):
        """Create the stacked view checkbox toggle."""
        from PySide6.QtCore import Qt
        self._stacked_checkbox = QCheckBox("Stacked")
        self._stacked_checkbox.setObjectName("stackedViewCheckbox")
        self._stacked_checkbox.setCursor(Qt.ArrowCursor)
        self._stacked_checkbox.setChecked(self.tab._view_mode == "stacked")
        self._stacked_checkbox.setToolTip("Group items by job (stacked) or show all items (grid)")
        self._stacked_checkbox.toggled.connect(self._on_view_mode_toggle)

        # Insert after filter checkbox in the header layout
        header_layout = self._find_header_layout()
        if header_layout:
            filter_index = header_layout.indexOf(self._filter_checkbox)
            header_layout.insertWidget(filter_index + 1, self._stacked_checkbox)

    def _on_view_mode_toggle(self, checked):
        """Toggle between stacked and grid view modes."""
        new_mode = "stacked" if checked else "grid"
        if new_mode == self.tab._view_mode:
            return

        self.tab._view_mode = new_mode

        # Save to settings
        from core.user_preferences import save_gallery_settings
        save_gallery_settings(view_mode=new_mode)

        # Redisplay with new view mode
        self._redisplay_items()

    def _redisplay_items(self):
        """Redisplay items with current sort/filter/view settings."""
        if not self.tab._cached_items:
            return

        # Apply filter and sort
        filtered_items = self.tab._filter_items(self.tab._cached_items)
        sorted_items = self.tab._manager.sort_items(filtered_items, self.tab._sort_mode)

        # Clear and rebuild display
        self.tab._manager.display_items(sorted_items, self.tab._view_mode)

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

        # Pre-cache other users' galleries in background
        # (commented out for now to avoid excessive network traffic)
        # for user in users:
        #     if user != self.tab.app_state.user:
        #         self._precache_user_gallery(user)

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

        # Refresh gallery
        self.tab._refresh_controller.on_refresh(force=True)

    def _update_view_only_indicator(self):
        """Show/hide the 'View Only' indicator based on whose gallery is shown."""
        is_own = self.tab._is_own_gallery()
        self.tab.ui.GalleryViewOnlyLabel.setVisible(not is_own)
