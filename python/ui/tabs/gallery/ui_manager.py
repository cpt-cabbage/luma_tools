"""
Gallery UI Manager.

Handles UI controls for the gallery:
- Sort button and mode selection
- Filters button and floating filters dialog
- View mode toggle (grid/stacked by job)
- User selector for multi-user gallery viewing
"""

import os
from PySide6.QtWidgets import QPushButton, QMenu
from PySide6.QtCore import QThreadPool

from .base_manager import BaseGalleryManager
from .filters_dialog import FiltersDialog


class UIManager(BaseGalleryManager):
    """Manages UI controls for the gallery."""

    def __init__(self, tab):
        """
        Initialize the UI manager.

        Args:
            tab: Reference to the GalleryTab
        """
        super().__init__(tab)

        # Sort options (field only, direction handled separately)
        self._sort_options = [
            ("Date", "date"),
            ("Name", "name"),
            ("Workflow", "workflow"),
        ]
        # Track current sort field and direction separately
        self._sort_field = "date"  # date, name, workflow
        self._sort_ascending = False  # False = descending (newest first for date)

    def _setup_ui(self):
        """Set up additional UI elements."""
        # Sync internal sort state FIRST before creating any UI
        self._sync_sort_state_from_mode()

        self._create_sort_direction_toggle()
        self._create_filter_button()
        self._create_view_mode_button()
        self.update_sort_button_text()

    # =========================================================================
    # SORT CONTROLS
    # =========================================================================

    def _create_sort_direction_toggle(self):
        """Create the sort direction toggle button (arrow) next to sort button."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QPushButton, QWidget, QHBoxLayout

        # Create container to group sort button and direction toggle together
        self._sort_container = QWidget()
        self._sort_container.setObjectName("sortContainer")
        container_layout = QHBoxLayout(self._sort_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)  # Tight spacing between sort and arrow

        # Create direction toggle button with correct initial arrow
        initial_arrow = "▲" if self._sort_ascending else "▼"
        self._sort_direction_btn = QPushButton(initial_arrow)
        self._sort_direction_btn.setObjectName("sortDirectionButton")
        self._sort_direction_btn.setFixedWidth(24)  # Narrow but same height as other buttons
        self._sort_direction_btn.setCursor(Qt.ArrowCursor)
        self._sort_direction_btn.setToolTip("Toggle sort direction")
        self._sort_direction_btn.clicked.connect(self._on_sort_direction_clicked)
        self._sort_direction_btn.setStyleSheet("padding: 2px 0px;")

        # Move sort button into container, add direction toggle
        header_layout = self._find_header_layout()
        if header_layout:
            sort_index = header_layout.indexOf(self.tab.ui.GallerySortButton)
            # Remove sort button from header, add to container
            header_layout.removeWidget(self.tab.ui.GallerySortButton)
            container_layout.addWidget(self.tab.ui.GallerySortButton)
            container_layout.addWidget(self._sort_direction_btn)
            # Insert container at original sort button position
            header_layout.insertWidget(sort_index, self._sort_container)

    def _sync_sort_state_from_mode(self):
        """Sync internal sort state from tab's sort_mode (for backward compat)."""
        mode = self.tab._sort_mode
        if mode == "date_desc":
            self._sort_field = "date"
            self._sort_ascending = False
        elif mode == "date_asc":
            self._sort_field = "date"
            self._sort_ascending = True
        elif mode == "name_asc":
            self._sort_field = "name"
            self._sort_ascending = True
        elif mode == "name_desc":
            self._sort_field = "name"
            self._sort_ascending = False
        elif mode == "workflow":
            self._sort_field = "workflow"
            self._sort_ascending = True
        else:
            self._sort_field = "date"
            self._sort_ascending = False

    def _get_sort_mode(self):
        """Get the combined sort mode string from field and direction."""
        if self._sort_field == "workflow":
            return "workflow"
        direction = "asc" if self._sort_ascending else "desc"
        return f"{self._sort_field}_{direction}"

    def _on_sort_direction_clicked(self):
        """Toggle sort direction."""
        self._sort_ascending = not self._sort_ascending
        self._update_sort_direction_button()
        self._apply_current_sort()

    def _update_sort_direction_button(self):
        """Update the direction button arrow and tooltip."""
        if self._sort_ascending:
            self._sort_direction_btn.setText("▲")
            if self._sort_field == "date":
                self._sort_direction_btn.setToolTip("Oldest first (click for newest)")
            else:
                self._sort_direction_btn.setToolTip("A-Z (click for Z-A)")
        else:
            self._sort_direction_btn.setText("▼")
            if self._sort_field == "date":
                self._sort_direction_btn.setToolTip("Newest first (click for oldest)")
            else:
                self._sort_direction_btn.setToolTip("Z-A (click for A-Z)")

    def update_sort_button_text(self):
        """Update the sort button text to show current field."""
        field_map = {field: label for label, field in self._sort_options}
        current_label = field_map.get(self._sort_field, "Sort")
        self.tab.ui.GallerySortButton.setText(current_label)
        self._update_sort_direction_button()

    def on_sort_button_clicked(self):
        """Show sort field options menu."""
        menu = QMenu(self.tab.ui.GallerySortButton)

        for label, field in self._sort_options:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(field == self._sort_field)
            action.triggered.connect(lambda checked, f=field: self._select_sort_field(f))

        # Position menu below button
        pos = self.tab.ui.GallerySortButton.mapToGlobal(
            self.tab.ui.GallerySortButton.rect().bottomLeft()
        )
        menu.exec_(pos)

    def _select_sort_field(self, field):
        """Apply selected sort field."""
        if field == self._sort_field:
            return

        self._sort_field = field
        self.update_sort_button_text()
        self._apply_current_sort()

    def _apply_current_sort(self):
        """Apply current sort settings (field + direction)."""
        mode = self._get_sort_mode()

        if mode == self.tab._sort_mode:
            return

        self.tab._sort_mode = mode

        # Save to settings
        from core.user_preferences import save_gallery_settings
        save_gallery_settings(sort_mode=mode)

        # Show status feedback
        field_labels = {f: label for label, f in self._sort_options}
        field_label = field_labels.get(self._sort_field, self._sort_field)
        direction = "ascending" if self._sort_ascending else "descending"
        if hasattr(self.tab, 'show_status_message'):
            self.tab.show_status_message(f"Gallery sorted by {field_label} ({direction})")

        # Re-sort and redisplay (use cached items, no rescan needed)
        self.redisplay_items()

    # =========================================================================
    # FILTER CONTROLS
    # =========================================================================

    def _create_filter_button(self):
        """Create the Filters button that opens the floating filters dialog."""
        from PySide6.QtCore import Qt

        self._filters_btn = QPushButton("Filters")
        self._filters_btn.setObjectName("filtersButton")
        self._filters_btn.setCursor(Qt.ArrowCursor)
        self._filters_btn.setToolTip("Open filter settings")
        self._filters_btn.clicked.connect(self._on_filters_button_clicked)

        # Create the filters dialog (hidden initially)
        self._filters_dialog = FiltersDialog(self.tab)
        self._filters_dialog.filters_changed.connect(self._on_filters_changed)
        self._filters_dialog.closed.connect(self._on_filters_dialog_closed)

        # Load saved filter settings
        self._load_filter_settings()
        self._update_filters_button_text()

        # Insert after sort container in the header layout
        header_layout = self._find_header_layout()
        if header_layout:
            sort_index = header_layout.indexOf(self._sort_container)
            header_layout.insertWidget(sort_index + 1, self._filters_btn)

    def _find_header_layout(self):
        """Find the header layout (cached after first call)."""
        # Return cached layout if available
        if hasattr(self, '_header_layout') and self._header_layout:
            return self._header_layout

        # self.tab.ui is the root widget loaded from the .ui file
        # Get the main layout (galleryMainLayout) from the root widget
        main_layout = self.tab.ui.layout()

        if main_layout:
            # galleryHeaderLayout is the first item in the main vertical layout
            for i in range(main_layout.count()):
                item = main_layout.itemAt(i)
                if item.layout():
                    # Check if this layout contains the sort button (before we move it)
                    nested_layout = item.layout()
                    if nested_layout.indexOf(self.tab.ui.GallerySortButton) >= 0:
                        self._header_layout = nested_layout
                        return nested_layout
        return None

    def _load_filter_settings(self):
        """Load filter settings from user preferences."""
        from core.user_preferences import get_gallery_settings
        settings = get_gallery_settings()

        # Load show_inputs
        show_inputs = settings.get("show_inputs", False)
        self._filters_dialog.set_show_inputs(show_inputs)

        # Load type filters
        type_filters = settings.get("type_filters", {
            "image": True,
            "video": True,
            "audio": True,
            "model": True
        })
        self._filters_dialog.set_type_filters(type_filters)

        # Sync to tab state
        self.tab._show_inputs = show_inputs
        self.tab._type_filters = type_filters

    def _on_filters_button_clicked(self):
        """Toggle the filters dialog visibility."""
        if self._filters_dialog.isVisible():
            self._filters_dialog.close()
        else:
            self._filters_dialog.show_below(self._filters_btn)

    def _on_filters_dialog_closed(self):
        """Handle filters dialog close."""
        self._update_filters_button_text()

    def _on_filters_changed(self):
        """Handle filter settings change from dialog."""
        # Get current settings from dialog
        show_inputs = self._filters_dialog.get_show_inputs()
        type_filters = self._filters_dialog.get_type_filters()

        # Update tab state
        self.tab._show_inputs = show_inputs
        self.tab._type_filters = type_filters

        # Save to settings
        from core.user_preferences import save_gallery_settings
        save_gallery_settings(show_inputs=show_inputs, type_filters=type_filters)

        # Update button text
        self._update_filters_button_text()

        # Re-filter and redisplay from cached items (no rescan needed)
        self.redisplay_items()

    def _update_filters_button_text(self):
        """Update the Filters button text based on active filters."""
        count = self._filters_dialog.get_active_filter_count()
        if count > 0:
            self._filters_btn.setText(f"Filters ({count})")
        else:
            self._filters_btn.setText("Filters")

    # =========================================================================
    # VIEW MODE CONTROLS
    # =========================================================================

    def _create_view_mode_button(self):
        """Create the Stacks button with floating dialog (like Filters)."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QPushButton
        from .stacks_dialog import StacksDialog

        # Get current stacking mode from settings
        from core.settings_manager import safe_get_setting
        current_mode = safe_get_setting("gallery_stacking_mode", "job")

        # Decode mode to checkbox states
        generations_on = current_mode in ("job", "both")
        groups_on = current_mode in ("groups", "both")

        # Create button
        self._stacks_btn = QPushButton("Stacks")
        self._stacks_btn.setObjectName("stacksButton")
        self._stacks_btn.setCursor(Qt.ArrowCursor)
        self._stacks_btn.setToolTip("Group items by generations or user groups")
        self._stacks_btn.clicked.connect(self._on_stacks_button_clicked)

        # Create the stacks dialog (hidden initially)
        self._stacks_dialog = StacksDialog(self.tab)
        self._stacks_dialog.set_generations(generations_on)
        self._stacks_dialog.set_groups(groups_on)
        self._stacks_dialog.stacks_changed.connect(self._on_stacks_changed)
        self._stacks_dialog.closed.connect(self._on_stacks_dialog_closed)

        self._update_stacks_button_text()

        # Insert after filters button in the header layout
        header_layout = self._find_header_layout()
        if header_layout:
            filter_index = header_layout.indexOf(self._filters_btn)
            header_layout.insertWidget(filter_index + 1, self._stacks_btn)

    def _update_stacks_button_text(self):
        """Update the Stacks button text."""
        self._stacks_btn.setText("Stacks")

    def _on_stacks_button_clicked(self):
        """Toggle the stacks dialog visibility."""
        if self._stacks_dialog.isVisible():
            self._stacks_dialog.close()
        else:
            self._stacks_dialog.show_below(self._stacks_btn)

    def _on_stacks_dialog_closed(self):
        """Handle stacks dialog close."""
        self._update_stacks_button_text()

    def _on_stacks_changed(self):
        """Handle stacking settings change from dialog."""
        generations_on = self._stacks_dialog.get_generations()
        groups_on = self._stacks_dialog.get_groups()

        # Map to stacking mode
        if generations_on and groups_on:
            mode = "both"
        elif generations_on:
            mode = "job"
        elif groups_on:
            mode = "groups"
        else:
            mode = "grid"

        # Update button text
        self._update_stacks_button_text()

        # Apply the mode
        self._apply_stacking_mode(mode)

    def _apply_stacking_mode(self, mode):
        """Apply selected stacking mode."""
        from core.settings_manager import get_setting, set_setting
        current_mode = get_setting("gallery_stacking_mode")

        if mode == current_mode:
            return

        set_setting("gallery_stacking_mode", mode, verbose=False)

        # Show status feedback
        mode_labels = {
            "grid": "Grid",
            "job": "Generations",
            "groups": "Groups",
            "both": "Generations + Groups"
        }
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
        self.redisplay_items(force_rebuild=True)

    def redisplay_items(self, force_rebuild=False):
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
            # Full rebuild - add transition animation
            self._animate_gallery_transition(sorted_items)

        # Update tracking state
        self.tab._last_displayed_paths = current_paths
        self.tab._last_view_mode = self.tab._view_mode

        # Note: _visible_items_ordered is set by reorder_widgets or display_items internally,
        # so we don't need to set it here (avoids redundant O(n) list comprehension)

    def _animate_gallery_transition(self, sorted_items):
        """Rebuild gallery display with a smooth opacity transition.

        Performance optimization: Skips opacity animation for large galleries
        to avoid performance impact.

        Args:
            sorted_items: Sorted list of items to display
        """
        from PySide6.QtCore import QEasingCurve, QTimer
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from effects import create_property_animation

        container = self.tab.ui.galleryThumbnailContainer

        # Cancel any running transition
        if hasattr(self, '_transition_anim') and self._transition_anim:
            self._transition_anim.stop()

        # Skip opacity animation for large galleries (100+ items)
        cache_size = len(getattr(self.tab, '_widget_cache', {}))
        if cache_size > 100:
            # Just rebuild without animation
            self.tab._manager.display_items(sorted_items, self.tab._view_mode)
            return

        # Quick dip: set opacity down, rebuild, then fade back up
        effect = container.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(container)
            container.setGraphicsEffect(effect)

        effect.setOpacity(0.7)  # Less drastic dip

        # Rebuild the display
        self.tab._manager.display_items(sorted_items, self.tab._view_mode)

        # Fade back to full opacity with shorter duration
        self._transition_anim = create_property_animation(
            effect, b"opacity", 0.7, 1.0,
            duration=100, easing=QEasingCurve.OutCubic  # Reduced from 200ms
        )
        self._transition_anim.start()

        # Remove effect after animation to avoid rendering overhead
        QTimer.singleShot(150, self._cleanup_transition)  # Reduced from 250ms

    def _cleanup_transition(self):
        """Remove transition opacity effect from gallery container."""
        self._transition_anim = None
        container = self.tab.ui.galleryThumbnailContainer
        if container.graphicsEffect():
            container.setGraphicsEffect(None)

    # =========================================================================
    # USER SELECTION
    # =========================================================================

    def populate_user_selector(self):
        """Initialize user selector with async discovery."""
        self.start_worker(self._discover_users_sync, on_result=self._on_users_discovered)

    def _discover_users_sync(self):
        """Discover available users from the network gallery path.

        Lists all user directories found in the network gallery path.
        This allows users to browse each other's public galleries (read-only).
        """
        import logging
        from core.settings_manager import get_setting

        logger = logging.getLogger(__name__)

        users = []

        # Get base path directly from settings (not via _get_network_user_path which requires a username)
        base_path = get_setting("network_output_path")
        if base_path:
            base_path = base_path.strip()

        logger.info(f"[Gallery] User discovery - base path: {base_path}")

        if base_path and os.path.exists(base_path):
            try:
                # List all directories as potential users
                all_items = os.listdir(base_path)
                logger.info(f"[Gallery] User discovery - found {len(all_items)} items in base path")

                # No per-item logging here — this runs on every gallery load and
                # wrote three DEBUG lines per directory entry into the shared
                # network logs. The summary line below is the useful record.
                import re
                for name in all_items:
                    full_path = os.path.join(base_path, name)
                    if not os.path.isdir(full_path):
                        continue
                    # Skip hidden/system directories and validate username safety
                    if not name.startswith('.') and not name.startswith('_') and re.match(r'^[\w.\-]+$', name):
                        users.append(name)
            except Exception as e:
                logger.error(f"[Gallery] Error discovering users: {e}")
        else:
            if not base_path:
                logger.warning("[Gallery] User discovery - network_output_path not configured")
            else:
                logger.warning(f"[Gallery] User discovery - path does not exist: {base_path}")

        logger.info(f"[Gallery] User discovery complete - found {len(users)} users: {users}")
        return sorted(users, key=str.lower)

    def _on_users_discovered(self, users):
        """Handle user discovery completion."""
        import logging
        logger = logging.getLogger(__name__)

        self.tab._available_users = users
        logger.info(f"[Gallery] Users discovered: {users}")
        self._update_user_button_visibility()

    def update_user_button_text(self):
        """Update user selector button text (app-wide 'Label: value' pattern)."""
        if self.tab._is_own_gallery():
            self.tab.ui.GalleryUserButton.setText(f"User: {self.tab._selected_user} (You)")
        else:
            self.tab.ui.GalleryUserButton.setText(f"User: {self.tab._selected_user}")

    def _update_user_button_visibility(self):
        """Show/hide user button based on available users."""
        import logging
        logger = logging.getLogger(__name__)

        # Show if there are other users
        has_other_users = len(self.tab._available_users) > 1
        logger.info(f"[Gallery] User button visibility - {len(self.tab._available_users)} users, showing button: {has_other_users}")
        self.tab.ui.GalleryUserButton.setVisible(has_other_users)

    def on_user_button_clicked(self):
        """Show user selection menu."""
        menu = QMenu(self.tab.ui.GalleryUserButton)

        # Add current user at top
        current_user = self.tab.app_state.user
        current_user_lower = (current_user or "").strip().lower()
        action = menu.addAction(f"{current_user} (You)")
        action.setCheckable(True)
        action.setChecked(self.tab._is_own_gallery())
        action.triggered.connect(lambda: self._select_user(current_user))

        if self.tab._available_users:
            menu.addSeparator()

            # Add other users (skip current user's directory by case-insensitive match)
            for user in self.tab._available_users:
                if user.strip().lower() != current_user_lower:
                    action = menu.addAction(user)
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

        # Clear selection when switching users (previous items no longer valid)
        self.tab._selection_manager.clear_selection(show_status=False)

        # Show loading overlay for user feedback during switch
        if new_user == self.tab.app_state.user:
            self.tab.show_loading_overlay("Loading your gallery...")
        else:
            self.tab.show_loading_overlay(f"Loading {new_user}'s gallery...")

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
