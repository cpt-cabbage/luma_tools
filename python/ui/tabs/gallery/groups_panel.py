"""
Gallery Groups Panel.

Collapsible sidebar for filtering gallery by likes and groups.
"""

import logging
from PySide6.QtCore import Qt, Signal

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QMenu, QCheckBox
)


class GroupFilterItem(QWidget):
    """A clickable filter item (All, Liked, or a group)."""

    clicked = Signal(str)  # Emits filter_id

    def __init__(self, filter_id, name, color=None, count=0, icon=None, parent=None):
        super().__init__(parent)
        self.filter_id = filter_id
        self._color = color
        self._is_active = False
        self._setup_ui(name, icon, count)

    def _setup_ui(self, name, icon, count):
        self.setFixedHeight(32)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Color dot or icon
        if self._color:
            self.color_dot = QLabel()
            self.color_dot.setFixedSize(12, 12)
            self.color_dot.setStyleSheet(f"""
                QLabel {{
                    background-color: {self._color};
                    border-radius: 6px;
                    border: 1px solid rgba(0, 0, 0, 0.2);
                }}
            """)
            self.color_dot.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(self.color_dot)
        elif icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 14px;")
            icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(icon_label)

        # Name
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.name_label, 1)

        # Count badge
        self.count_label = QLabel(str(count))
        self.count_label.setStyleSheet("""
            color: #888888;
            font-size: 11px;
            background-color: #3c414b;
            border-radius: 8px;
            padding: 2px 6px;
        """)
        self.count_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.count_label)

        self._update_style()

    def set_active(self, active):
        """Set whether this filter is currently active."""
        self._is_active = active
        self._update_style()

    def set_count(self, count):
        """Update the count badge."""
        self.count_label.setText(str(count))

    def _hex_to_rgba(self, hex_color, alpha):
        """Convert hex color to rgba string."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

    def _update_style(self):
        # Determine background color based on custom color
        if self._color:
            bg_color = self._hex_to_rgba(self._color, 0.15)
            bg_hover = self._hex_to_rgba(self._color, 0.25)
            bg_active = self._hex_to_rgba(self._color, 0.35)
        else:
            bg_color = "transparent"
            bg_hover = "rgba(255, 255, 255, 0.05)"
            bg_active = "rgba(74, 158, 255, 0.2)"

        if self._is_active:
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {bg_active};
                    border-radius: 4px;
                }}
            """)
            self.name_label.setStyleSheet("color: #4a9eff; font-size: 12px; font-weight: bold;")
        else:
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {bg_color};
                    border-radius: 4px;
                }}
                QWidget:hover {{
                    background-color: {bg_hover};
                }}
            """)
            self.name_label.setStyleSheet("color: #e0e0e0; font-size: 12px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.filter_id)
        super().mousePressEvent(event)


class GroupsFilterPanel(QWidget):
    """
    Collapsible sidebar for filtering gallery by likes, groups, and stacks.

    Signals:
        filter_changed(filter_type, filter_id): Emitted when filter selection changes
            filter_type: "all", "liked", "group", "ungrouped", "stack"
            filter_id: group_id for groups, stack_id for stacks, None for others
        collapsed_changed(is_collapsed): Emitted when panel is collapsed/expanded
    """

    filter_changed = Signal(str, str)  # filter_type, filter_id
    collapsed_changed = Signal(bool)  # is_collapsed
    status_message = Signal(str)  # message to display in status bar

    def __init__(self, favorites_manager, parent=None):
        super().__init__(parent)
        self._favorites_manager = favorites_manager
        self._is_collapsed = False
        self._current_filter = ("all", None)
        self._filter_items = {}  # filter_id -> GroupFilterItem
        self._stack_items = {}  # stack_id -> GroupFilterItem
        self._stacks_data = self._load_stacks_data()  # stack_id -> count (cached)
        self._stacks_separator = None  # QFrame separator before stacks section
        self._stacks_header = None  # QWidget header container for stacks section
        self._stacks_toggle = None  # QLabel toggle arrow for stacks section
        self._stacks_collapsed = self._load_stacks_collapsed()  # Whether stacks section is collapsed
        self._stack_colors = self._load_stack_colors()  # stack_id -> color
        self._liked_color = self._load_liked_color()  # Custom color for liked filter
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # Allow resizing via splitter
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Set initial min width (will be changed during collapse/expand)
        self.setMinimumWidth(120)
        # Set object name for specific styling - only this widget gets dark background
        # NOT children (which have their own tinted backgrounds)
        self.setObjectName("GroupsFilterPanel")
        self.setStyleSheet("""
            #GroupsFilterPanel {
                background-color: #1e1e22;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header with collapse toggle
        header = QWidget()
        header.setFixedHeight(40)
        header.setStyleSheet("background-color: #2a2e36;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 8, 0)

        title = QLabel("Filters")
        title.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 13px;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.collapse_btn = QPushButton("Hide")
        self.collapse_btn.setFixedHeight(24)
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.setToolTip("Collapse sidebar")
        self.collapse_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #4a5160;
            }
        """)
        self.collapse_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self.collapse_btn)

        main_layout.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #3c414b;")
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)

        # Content area (scrollable)
        self.content = QWidget()
        self.content.setObjectName("GroupsFilterContent")
        self.content.setStyleSheet("#GroupsFilterContent { background-color: #1e1e22; }")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidget(self.content)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #2a2e36;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a5160;
                border-radius: 4px;
                min-height: 20px;
            }
        """)
        main_layout.addWidget(scroll, 1)

        # Add filter items
        self._build_filter_list()

        # Add group button at bottom
        self.add_group_btn = QPushButton("+ New Group")
        self.add_group_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4a5160;
            }
        """)
        self.add_group_btn.clicked.connect(self._on_add_group)
        main_layout.addWidget(self.add_group_btn)

    def _build_filter_list(self):
        """Build the list of filter items."""
        # Clear existing items
        for item in self._filter_items.values():
            item.deleteLater()
        self._filter_items.clear()

        # "All Items" option
        all_item = GroupFilterItem("all", "All Items", icon="📁", count=0)
        all_item.clicked.connect(lambda fid: self._on_filter_clicked("all", None))
        self.content_layout.addWidget(all_item)
        self._filter_items["all"] = all_item

        # "Liked" filter
        liked_count = self._favorites_manager.get_liked_count() if self._favorites_manager else 0
        liked_item = GroupFilterItem(
            "liked", "Liked",
            icon="♥" if not self._liked_color else None,
            color=self._liked_color,
            count=liked_count
        )
        liked_item.clicked.connect(lambda fid: self._on_filter_clicked("liked", None))
        # Right-click for color change
        liked_item.setContextMenuPolicy(Qt.CustomContextMenu)
        liked_item.customContextMenuRequested.connect(self._show_liked_context_menu)
        self.content_layout.addWidget(liked_item)
        self._filter_items["liked"] = liked_item

        # "Inputs" filter (source images)
        inputs_item = GroupFilterItem("inputs", "Inputs", icon="📥", count=0)
        inputs_item.clicked.connect(lambda fid: self._on_filter_clicked("inputs", None))
        self.content_layout.addWidget(inputs_item)
        self._filter_items["inputs"] = inputs_item

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #3c414b;")
        sep.setFixedHeight(1)
        self.content_layout.addWidget(sep)

        # Groups
        if self._favorites_manager:
            groups = self._favorites_manager.get_groups()
            for group in groups:
                count = self._favorites_manager.get_group_item_count(group.group_id)
                item = GroupFilterItem(
                    group.group_id,
                    group.name,
                    color=group.color,
                    count=count
                )
                item.clicked.connect(lambda fid, gid=group.group_id: self._on_filter_clicked("group", gid))
                # Right-click for edit/delete
                item.setContextMenuPolicy(Qt.CustomContextMenu)
                item.customContextMenuRequested.connect(
                    lambda pos, gid=group.group_id: self._show_group_context_menu(pos, gid)
                )
                self.content_layout.addWidget(item)
                self._filter_items[group.group_id] = item

        # "Ungrouped" filter
        ungrouped_item = GroupFilterItem("ungrouped", "Ungrouped", icon="○", count=0)
        ungrouped_item.clicked.connect(lambda fid: self._on_filter_clicked("ungrouped", None))
        self.content_layout.addWidget(ungrouped_item)
        self._filter_items["ungrouped"] = ungrouped_item

        # Stacks section
        self._build_stacks_section()

        # Add stretch at bottom
        self.content_layout.addStretch()

        # Set initial active state
        self._update_active_state()

    def _build_stacks_section(self):
        """Build the stacks section of the filter list.

        Delegates to _rebuild_stacks() which handles the full collapsible header.
        """
        # Just use _rebuild_stacks which handles all the cleanup and creation properly
        self._rebuild_stacks()

    def set_stacks_data(self, stacks_data):
        """Update the stacks section with new data.

        Args:
            stacks_data: Dict of stack_id -> item_count
        """
        new_data = stacks_data or {}

        # Check if only counts changed (same stacks, different counts) - optimize this case
        widgets_exist = bool(self._stack_items)
        old_keys = set(self._stacks_data.keys())
        new_keys = set(new_data.keys())

        if widgets_exist and old_keys == new_keys and new_data:
            # Same stacks exist, just update counts without full rebuild
            self._stacks_data = new_data
            for stack_id, count in new_data.items():
                if stack_id in self._stack_items:
                    self._stack_items[stack_id].set_count(count)
            self._save_stacks_data()
            return

        # Stacks changed or widgets don't exist, do full rebuild
        self._stacks_data = new_data
        self._save_stacks_data()
        self._rebuild_stacks()

    def _rebuild_stacks(self):
        """Rebuild just the stacks section."""
        try:
            # Remove old stack widgets
            for item in list(self._stack_items.values()):
                try:
                    item.setParent(None)
                    item.deleteLater()
                except RuntimeError:
                    logger.debug("Stack item widget already deleted during cleanup")
            self._stack_items.clear()

            # Remove old separator and header if they exist
            if self._stacks_separator:
                try:
                    self._stacks_separator.setParent(None)
                    self._stacks_separator.deleteLater()
                except RuntimeError:
                    pass
                self._stacks_separator = None
            if self._stacks_header:
                try:
                    self._stacks_header.setParent(None)
                    self._stacks_header.deleteLater()
                except RuntimeError:
                    pass
                self._stacks_header = None
            self._stacks_toggle = None  # Cleaned up with header

            # Rebuild if we have data
            if not self._stacks_data:
                self._update_active_state()
                return

            if not hasattr(self, 'content_layout') or not self.content_layout:
                return

            # Find the index of ungrouped item to insert after it
            ungrouped_idx = -1
            for i in range(self.content_layout.count()):
                item = self.content_layout.itemAt(i)
                if item and item.widget() == self._filter_items.get("ungrouped"):
                    ungrouped_idx = i
                    break

            # If ungrouped not found, find the stretch and insert before it
            # Or just append if nothing found
            if ungrouped_idx >= 0:
                insert_idx = ungrouped_idx + 1
            else:
                # Fallback: find stretch or use end of layout
                insert_idx = self.content_layout.count()
                for i in range(self.content_layout.count()):
                    item = self.content_layout.itemAt(i)
                    if item and item.spacerItem():
                        insert_idx = i
                        break

            # Stacks separator
            stacks_sep = QFrame()
            stacks_sep.setFrameShape(QFrame.HLine)
            stacks_sep.setStyleSheet("background-color: #3c414b;")
            stacks_sep.setFixedHeight(1)
            self.content_layout.insertWidget(insert_idx, stacks_sep)
            self._stacks_separator = stacks_sep
            insert_idx += 1

            # Stacks header (clickable to collapse/expand)
            stacks_header = QWidget()
            stacks_header.setFixedHeight(28)
            stacks_header.setCursor(Qt.PointingHandCursor)
            header_layout = QHBoxLayout(stacks_header)
            header_layout.setContentsMargins(8, 4, 8, 4)
            header_layout.setSpacing(4)

            # Collapse toggle arrow
            self._stacks_toggle = QLabel("▼" if not self._stacks_collapsed else "▶")
            self._stacks_toggle.setStyleSheet("color: #888888; font-size: 8px;")
            self._stacks_toggle.setFixedWidth(12)
            header_layout.addWidget(self._stacks_toggle)

            # Header text with count
            header_text = QLabel(f"Stacks ({len(self._stacks_data)})")
            header_text.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
            header_layout.addWidget(header_text)
            header_layout.addStretch()

            # Make header clickable
            stacks_header.mousePressEvent = lambda e: self._toggle_stacks_collapsed()

            self.content_layout.insertWidget(insert_idx, stacks_header)
            self._stacks_header = stacks_header
            insert_idx += 1

            # Add stack items sorted by name (hidden if collapsed)
            for stack_id in sorted(self._stacks_data.keys()):
                count = self._stacks_data[stack_id]
                display_name = stack_id if len(stack_id) <= 20 else stack_id[:17] + "..."
                stack_color = self._stack_colors.get(stack_id)
                item = GroupFilterItem(
                    f"stack_{stack_id}",
                    display_name,
                    icon="▣" if not stack_color else None,
                    color=stack_color,
                    count=count
                )
                item.setToolTip(f"{stack_id}\n{count} items")
                item.clicked.connect(lambda fid, sid=stack_id: self._on_filter_clicked("stack", sid))
                # Add context menu for color change
                item.setContextMenuPolicy(Qt.CustomContextMenu)
                item.customContextMenuRequested.connect(
                    lambda pos, sid=stack_id: self._show_stack_context_menu(pos, sid)
                )
                self.content_layout.insertWidget(insert_idx, item)
                self._stack_items[stack_id] = item
                insert_idx += 1

                # Hide if collapsed
                if self._stacks_collapsed:
                    item.hide()

            self._update_active_state()

            # Force layout update to ensure widgets are visible immediately
            self.content.updateGeometry()
            self.content_layout.update()
        except Exception as e:
            import logging
            logging.error(f"Error rebuilding stacks section: {e}")

    def _toggle_stacks_collapsed(self):
        """Toggle the collapsed state of the stacks section."""
        self._stacks_collapsed = not self._stacks_collapsed
        self._save_stacks_collapsed()

        # Update toggle arrow
        if hasattr(self, '_stacks_toggle') and self._stacks_toggle:
            self._stacks_toggle.setText("▶" if self._stacks_collapsed else "▼")

        # Show/hide stack items
        for item in self._stack_items.values():
            if self._stacks_collapsed:
                item.hide()
            else:
                item.show()

    def _load_setting(self, key, default=None):
        """Load a setting with optional default."""
        from core.settings_manager import get_setting
        value = get_setting(key, default)
        return value if value is not None else default

    def _save_setting(self, key, value, verbose=False):
        """Save a setting."""
        from core.settings_manager import set_setting
        set_setting(key, value, verbose=verbose)

    def _load_stack_colors(self):
        return self._load_setting("gallery_stack_colors", {})

    def _save_stack_colors(self):
        self._save_setting("gallery_stack_colors", self._stack_colors)

    def _load_stacks_data(self):
        return self._load_setting("gallery_stacks_data", {})

    def _save_stacks_data(self):
        self._save_setting("gallery_stacks_data", self._stacks_data)

    def _load_stacks_collapsed(self):
        return self._load_setting("gallery_stacks_collapsed", False)

    def _save_stacks_collapsed(self):
        self._save_setting("gallery_stacks_collapsed", self._stacks_collapsed)

    def _show_stack_context_menu(self, pos, stack_id):
        """Show context menu for a stack item."""
        menu = QMenu(self)

        change_color_action = menu.addAction("Change Color")
        change_color_action.triggered.connect(lambda: self._change_stack_color(stack_id))

        if stack_id in self._stack_colors:
            clear_color_action = menu.addAction("Clear Color")
            clear_color_action.triggered.connect(lambda: self._clear_stack_color(stack_id))

        item = self._stack_items.get(stack_id)
        if item:
            menu.exec_(item.mapToGlobal(pos))

    def _change_stack_color(self, stack_id):
        """Open color picker to change stack color."""
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor

        current_color = self._stack_colors.get(stack_id, "#4a9eff")
        color = QColorDialog.getColor(QColor(current_color), self, f"Choose Color for {stack_id}")
        if color.isValid():
            self._stack_colors[stack_id] = color.name()
            self._save_stack_colors()
            self._rebuild_stacks()

    def _clear_stack_color(self, stack_id):
        """Remove custom color from a stack."""
        if stack_id in self._stack_colors:
            del self._stack_colors[stack_id]
            self._save_stack_colors()
            self._rebuild_stacks()

    def _load_liked_color(self):
        return self._load_setting("gallery_liked_color")

    def _save_liked_color(self):
        self._save_setting("gallery_liked_color", self._liked_color)

    def _show_liked_context_menu(self, pos):
        """Show context menu for the liked filter item."""
        menu = QMenu(self)

        change_color_action = menu.addAction("Change Color")
        change_color_action.triggered.connect(self._change_liked_color)

        if self._liked_color:
            clear_color_action = menu.addAction("Clear Color")
            clear_color_action.triggered.connect(self._clear_liked_color)

        item = self._filter_items.get("liked")
        if item:
            menu.exec_(item.mapToGlobal(pos))

    def _change_liked_color(self):
        """Open color picker to change liked filter color."""
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor

        current_color = self._liked_color or "#ff6b6b"  # Default red-ish for liked
        color = QColorDialog.getColor(QColor(current_color), self, "Choose Color for Liked")
        if color.isValid():
            self._liked_color = color.name()
            self._save_liked_color()
            self._build_filter_list()

    def _clear_liked_color(self):
        """Remove custom color from liked filter."""
        self._liked_color = None
        self._save_liked_color()
        self._build_filter_list()

    def _connect_signals(self):
        """Connect to favorites manager signals."""
        if self._favorites_manager:
            self._favorites_manager.group_created.connect(self._on_groups_changed)
            self._favorites_manager.group_deleted.connect(self._on_groups_changed)
            self._favorites_manager.group_updated.connect(self._on_groups_changed)
            self._favorites_manager.like_changed.connect(self._on_like_changed)
            self._favorites_manager.item_groups_changed.connect(self._on_item_groups_changed)

    def _on_groups_changed(self, group_id=None):
        """Rebuild the filter list when groups change."""
        self._build_filter_list()

    def _on_like_changed(self, path, is_liked):
        """Update liked count when like status changes."""
        if "liked" in self._filter_items:
            count = self._favorites_manager.get_liked_count()
            self._filter_items["liked"].set_count(count)

    def _on_item_groups_changed(self, path):
        """Update group counts when item group membership changes."""
        if self._favorites_manager:
            for group in self._favorites_manager.get_groups():
                if group.group_id in self._filter_items:
                    count = self._favorites_manager.get_group_item_count(group.group_id)
                    self._filter_items[group.group_id].set_count(count)

    def _on_filter_clicked(self, filter_type, filter_id):
        """Handle filter item click."""
        self._current_filter = (filter_type, filter_id)
        self._update_active_state()
        self.filter_changed.emit(filter_type, filter_id or "")

        # Emit status message for filter change
        if filter_type == "all":
            self.status_message.emit("Showing all items")
        elif filter_type == "liked":
            self.status_message.emit("Showing liked items")
        elif filter_type == "inputs":
            self.status_message.emit("Showing input images")
        elif filter_type == "ungrouped":
            self.status_message.emit("Showing ungrouped items")
        elif filter_type == "group" and filter_id:
            group = self._favorites_manager.get_group(filter_id) if self._favorites_manager else None
            if group:
                self.status_message.emit(f"Showing group: {group.name}")
        elif filter_type == "stack" and filter_id:
            self.status_message.emit(f"Showing stack: {filter_id}")

    def _update_active_state(self):
        """Update which filter item appears active."""
        filter_type, filter_id = self._current_filter

        # Update main filter items
        for fid, item in self._filter_items.items():
            if filter_type == "group":
                item.set_active(fid == filter_id)
            elif filter_type == "stack":
                item.set_active(False)  # No main filter active when stack selected
            else:
                item.set_active(fid == filter_type)

        # Update stack items
        for stack_id, item in self._stack_items.items():
            if filter_type == "stack":
                item.set_active(stack_id == filter_id)
            else:
                item.set_active(False)

    def _show_group_context_menu(self, pos, group_id):
        """Show context menu for a group."""
        menu = QMenu(self)

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_group(group_id))

        change_color_action = menu.addAction("Change Color")
        change_color_action.triggered.connect(lambda: self._change_group_color(group_id))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_group(group_id))

        # Show at cursor position
        item = self._filter_items.get(group_id)
        if item:
            menu.exec_(item.mapToGlobal(pos))

    def _rename_group(self, group_id):
        """Open dialog to rename a group."""
        if not self._favorites_manager:
            return
        group = self._favorites_manager.get_group(group_id)
        if not group:
            return

        from dialogs import GroupEditorDialog
        dialog = GroupEditorDialog(group=group, parent=self)
        if dialog.exec_():
            name, color = dialog.get_result()
            if name:
                self._favorites_manager.rename_group(group_id, name)
                self.status_message.emit(f"Renamed group to '{name}'")
                self._favorites_manager.change_group_color(group_id, color)

    def _change_group_color(self, group_id):
        """Open color picker to change group color."""
        if not self._favorites_manager:
            return
        group = self._favorites_manager.get_group(group_id)
        if not group:
            return

        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(group.color), self, "Choose Group Color")
        if color.isValid():
            self._favorites_manager.change_group_color(group_id, color.name())

    def _delete_group(self, group_id):
        """Delete a group after confirmation."""
        if not self._favorites_manager:
            return
        group = self._favorites_manager.get_group(group_id)
        if not group:
            return

        from dialog_helpers import confirm_action
        if confirm_action(
            "Delete Group",
            f"Delete group '{group.name}'?\n\nItems in this group will not be deleted.",
            self
        ):
            group_name = group.name
            self._favorites_manager.delete_group(group_id)
            self.status_message.emit(f"Deleted group '{group_name}'")
            # Reset filter if we were viewing this group
            if self._current_filter == ("group", group_id):
                self._on_filter_clicked("all", None)

    def _on_add_group(self):
        """Open dialog to create a new group."""
        from dialogs import GroupEditorDialog
        dialog = GroupEditorDialog(parent=self)
        if dialog.exec_():
            name, color = dialog.get_result()
            if name and self._favorites_manager:
                self._favorites_manager.create_group(name, color)
                self.status_message.emit(f"Created group '{name}'")

    def _animate_width(self, target_max, target_min, duration=200):
        """Animate panel width to target max/min values."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        # Cancel any running animation
        for anim in getattr(self, '_collapse_anims', []):
            anim.stop()

        max_anim = QPropertyAnimation(self, b"maximumWidth")
        max_anim.setDuration(duration)
        max_anim.setStartValue(self.maximumWidth())
        max_anim.setEndValue(target_max)
        max_anim.setEasingCurve(QEasingCurve.InOutCubic)

        min_anim = QPropertyAnimation(self, b"minimumWidth")
        min_anim.setDuration(duration)
        min_anim.setStartValue(self.minimumWidth())
        min_anim.setEndValue(target_min)
        min_anim.setEasingCurve(QEasingCurve.InOutCubic)

        max_anim.start()
        min_anim.start()
        self._collapse_anims = [max_anim, min_anim]

    def _toggle_collapse(self):
        """Toggle collapsed state with smooth width animation."""
        from PySide6.QtCore import QTimer

        self._is_collapsed = not self._is_collapsed
        duration = 200

        if self._is_collapsed:
            self._expanded_width = self.width()
            self.content.hide()
            self.add_group_btn.hide()
            self.collapse_btn.setText("Show")
            self.collapse_btn.setToolTip("Expand sidebar")
            self._animate_width(40, 40, duration)
        else:
            self.collapse_btn.setText("Hide")
            self.collapse_btn.setToolTip("Collapse sidebar")
            self._animate_width(400, 120, duration)
            QTimer.singleShot(duration // 2, self._show_content_if_expanded)

        self.collapsed_changed.emit(self._is_collapsed)

    def _show_content_if_expanded(self):
        """Show content widgets if panel is currently expanded."""
        if not self._is_collapsed:
            self.content.show()
            self.add_group_btn.show()

    def is_collapsed(self):
        """Return whether the panel is currently collapsed."""
        return self._is_collapsed

    def set_item_counts(self, all_count, liked_count, group_counts, ungrouped_count, inputs_count=0):
        """Update all item counts.

        Args:
            all_count: Total number of items
            liked_count: Number of liked items
            group_counts: Dict of group_id -> count
            ungrouped_count: Number of ungrouped items
            inputs_count: Number of input images
        """
        if "all" in self._filter_items:
            self._filter_items["all"].set_count(all_count)
        if "liked" in self._filter_items:
            self._filter_items["liked"].set_count(liked_count)
        if "inputs" in self._filter_items:
            self._filter_items["inputs"].set_count(inputs_count)
        if "ungrouped" in self._filter_items:
            self._filter_items["ungrouped"].set_count(ungrouped_count)
        for group_id, count in group_counts.items():
            if group_id in self._filter_items:
                self._filter_items[group_id].set_count(count)

    def get_current_filter(self):
        """Get the current filter selection.

        Returns:
            Tuple of (filter_type, filter_id)
        """
        return self._current_filter

    def refresh(self):
        """Rebuild the filter list from the favorites manager."""
        self._build_filter_list()
