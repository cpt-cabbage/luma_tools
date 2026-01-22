"""
Gallery UI Manager.

Handles UI controls for the gallery:
- Sort button and mode selection
- Filter button (show/hide inputs)
- View mode toggle (stacked/grid/sections)
- User selector for multi-user gallery viewing
"""

import os
from PySide6.QtWidgets import QPushButton, QMenu
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
        from core.user_preferences import save_gallery_settings, get_gallery_settings
        settings = get_gallery_settings()
        settings['sort_mode'] = mode
        save_gallery_settings(settings)

        # Re-sort and redisplay (use cached items, no rescan needed)
        self._redisplay_items()

    # =========================================================================
    # FILTER CONTROLS
    # =========================================================================

    def _create_filter_button(self):
        """Create the filter toggle button."""
        self._filter_button = QPushButton()
        self._filter_button.setObjectName("filterToggleButton")
        self._update_filter_button_text()
        self._filter_button.clicked.connect(self._on_filter_toggle)

        # Insert after sort button in the header layout
        header_layout = self._find_header_layout()
        if header_layout:
            sort_index = header_layout.indexOf(self.tab.ui.GallerySortButton)
            header_layout.insertWidget(sort_index + 1, self._filter_button)

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

    def _update_filter_button_text(self):
        """Update filter button text based on current state."""
        if self.tab._show_inputs:
            self._filter_button.setText("Inputs: Shown")
        else:
            self._filter_button.setText("Inputs: Hidden")

    def _on_filter_toggle(self):
        """Toggle input file visibility."""
        self.tab._show_inputs = not self.tab._show_inputs
        self._update_filter_button_text()

        # Save to settings
        from core.user_preferences import save_gallery_settings, get_gallery_settings
        settings = get_gallery_settings()
        settings['show_inputs'] = self.tab._show_inputs
        save_gallery_settings(settings)

        # Re-filter and redisplay from cached items (no rescan needed)
        self._redisplay_items()

    # =========================================================================
    # VIEW MODE CONTROLS
    # =========================================================================

    def _create_view_mode_button(self):
        """Create the stacked/grid view toggle button."""
        self._view_button = QPushButton()
        self._view_button.setObjectName("viewModeButton")
        self._update_view_button_text()
        self._view_button.clicked.connect(self._on_view_mode_toggle)

        # Insert after filter button in the header layout
        header_layout = self._find_header_layout()
        if header_layout:
            filter_index = header_layout.indexOf(self._filter_button)
            header_layout.insertWidget(filter_index + 1, self._view_button)

    def _update_view_button_text(self):
        """Update view mode button text."""
        mode_labels = {
            "stacked": "Stacked",
            "grid": "Grid",
        }
        label = mode_labels.get(self.tab._view_mode, "View")
        self._view_button.setText(label)

    def _on_view_mode_toggle(self):
        """Show view mode menu."""
        menu = QMenu(self._view_button)

        modes = [
            ("Stacked (Grouped)", "stacked"),
            ("Grid (All Items)", "grid"),
        ]

        for label, mode in modes:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == self.tab._view_mode)
            action.triggered.connect(lambda checked, m=mode: self._select_view_mode(m))

        pos = self._view_button.mapToGlobal(self._view_button.rect().bottomLeft())
        menu.exec_(pos)

    def _select_view_mode(self, mode):
        """Apply selected view mode."""
        if mode == self.tab._view_mode:
            return

        self.tab._view_mode = mode
        self._update_view_button_text()

        # Save to settings
        from core.user_preferences import save_gallery_settings, get_gallery_settings
        settings = get_gallery_settings()
        settings['view_mode'] = mode
        save_gallery_settings(settings)

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
        """Discover available users from the network gallery path."""
        users = []
        base_path = self.tab._get_network_user_path(username="")

        if base_path and os.path.exists(base_path):
            try:
                # List directories in the ComfyUI output folder
                for name in os.listdir(base_path):
                    full_path = os.path.join(base_path, name)
                    if os.path.isdir(full_path):
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
