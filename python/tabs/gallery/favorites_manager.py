"""
Gallery Favorites Manager.

Handles likes and groups functionality for the gallery:
- Like/unlike items
- Create, edit, delete groups
- Add/remove items from groups
- Batch operations for multi-select
- Persistence via settings manager
"""

import os
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field, asdict
from PySide6.QtCore import QObject, Signal

from core.config import UIColors

logger = logging.getLogger(__name__)

# Import GROUP_COLORS from config for backwards compatibility
GROUP_COLORS = UIColors.GROUP_COLORS


@dataclass
class GroupDef:
    """Definition for a gallery group."""
    group_id: str
    name: str
    color: str
    created: str
    order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupDef":
        """Create from dictionary."""
        return cls(
            group_id=data.get("group_id", str(uuid.uuid4())),
            name=data.get("name", "Untitled"),
            color=data.get("color", GROUP_COLORS[0]),
            created=data.get("created", datetime.now().isoformat()),
            order=data.get("order", 0)
        )


class FavoritesManager(QObject):
    """
    Manages likes and groups for gallery items.

    Signals:
        like_changed(path, is_liked): Emitted when an item's like status changes
        group_created(group_id): Emitted when a new group is created
        group_deleted(group_id): Emitted when a group is deleted
        group_updated(group_id): Emitted when a group's properties change
        item_groups_changed(path): Emitted when an item's group membership changes
    """

    like_changed = Signal(str, bool)  # path, is_liked
    group_created = Signal(str)  # group_id
    group_deleted = Signal(str)  # group_id
    group_updated = Signal(str)  # group_id
    item_groups_changed = Signal(str)  # path

    def __init__(self, tab):
        """
        Initialize the favorites manager.

        Args:
            tab: Reference to the ComfyUIGalleryTab
        """
        super().__init__()
        self.tab = tab
        self._liked_items: Set[str] = set()
        self._groups: Dict[str, GroupDef] = {}
        self._item_groups: Dict[str, Set[str]] = {}  # path -> set of group_ids
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy load settings on first access."""
        if not self._loaded:
            self._load_from_settings()
            self._loaded = True

    def _load_from_settings(self):
        """Load likes and groups from user settings."""
        from core.settings_manager import get_setting

        # Load liked items (normalize paths for consistent lookup)
        liked_list = get_setting("gallery_liked_items")
        self._liked_items = set(os.path.normpath(p) for p in liked_list) if liked_list else set()

        # Load groups
        groups_dict = get_setting("gallery_groups")
        self._groups = {}
        if groups_dict:
            for group_id, group_data in groups_dict.items():
                try:
                    self._groups[group_id] = GroupDef.from_dict(group_data)
                except Exception as e:
                    logger.error(f"Error loading group {group_id}: {e}")

        # Load item-to-groups mapping (normalize paths for consistent lookup)
        item_groups_dict = get_setting("gallery_item_groups")
        self._item_groups = {}
        if item_groups_dict:
            for path, group_ids in item_groups_dict.items():
                norm_path = os.path.normpath(path)
                self._item_groups[norm_path] = set(group_ids) if group_ids else set()

    def _save_liked_items(self):
        """Save liked items to settings."""
        from core.settings_manager import set_setting
        set_setting("gallery_liked_items", list(self._liked_items), verbose=False)

    def _save_groups(self):
        """Save groups to settings."""
        from core.settings_manager import set_setting
        groups_dict = {gid: g.to_dict() for gid, g in self._groups.items()}
        set_setting("gallery_groups", groups_dict, verbose=False)

    def _save_item_groups(self):
        """Save item-to-groups mapping to settings."""
        from core.settings_manager import set_setting
        item_groups_dict = {path: list(gids) for path, gids in self._item_groups.items()}
        set_setting("gallery_item_groups", item_groups_dict, verbose=False)

    # =========================================================================
    # LIKES
    # =========================================================================

    def toggle_like(self, path: str) -> bool:
        """
        Toggle like status for an item.

        Args:
            path: Path to the item

        Returns:
            True if item is now liked, False if unliked
        """
        self._ensure_loaded()
        path = os.path.normpath(path)
        if path in self._liked_items:
            self._liked_items.discard(path)
            is_liked = False
        else:
            self._liked_items.add(path)
            is_liked = True
        self._save_liked_items()
        self.like_changed.emit(path, is_liked)
        return is_liked

    def is_liked(self, path: str) -> bool:
        """Check if an item is liked."""
        self._ensure_loaded()
        return os.path.normpath(path) in self._liked_items

    def get_liked_items(self) -> List[str]:
        """Get list of all liked item paths."""
        self._ensure_loaded()
        return list(self._liked_items)

    def like_items(self, paths: List[str]):
        """Like multiple items (batch operation)."""
        self._ensure_loaded()
        for path in paths:
            path = os.path.normpath(path)
            if path not in self._liked_items:
                self._liked_items.add(path)
                self.like_changed.emit(path, True)
        self._save_liked_items()

    def unlike_items(self, paths: List[str]):
        """Unlike multiple items (batch operation)."""
        self._ensure_loaded()
        for path in paths:
            path = os.path.normpath(path)
            if path in self._liked_items:
                self._liked_items.discard(path)
                self.like_changed.emit(path, False)
        self._save_liked_items()

    def get_liked_count(self) -> int:
        """Get number of liked items."""
        self._ensure_loaded()
        return len(self._liked_items)

    # =========================================================================
    # GROUPS
    # =========================================================================

    def create_group(self, name: str, color: str = None) -> str:
        """
        Create a new group.

        Args:
            name: Name of the group
            color: Hex color for the group (defaults to first available color)

        Returns:
            The group_id of the new group
        """
        self._ensure_loaded()

        if color is None:
            # Pick next available color
            used_colors = {g.color for g in self._groups.values()}
            for c in GROUP_COLORS:
                if c not in used_colors:
                    color = c
                    break
            if color is None:
                color = GROUP_COLORS[len(self._groups) % len(GROUP_COLORS)]

        group_id = str(uuid.uuid4())
        order = max((g.order for g in self._groups.values()), default=-1) + 1
        group = GroupDef(
            group_id=group_id,
            name=name,
            color=color,
            created=datetime.now().isoformat(),
            order=order
        )
        self._groups[group_id] = group
        self._save_groups()
        self.group_created.emit(group_id)
        return group_id

    def delete_group(self, group_id: str):
        """
        Delete a group and remove all items from it.

        Args:
            group_id: ID of the group to delete
        """
        self._ensure_loaded()
        if group_id not in self._groups:
            return

        # Remove group from all items
        affected_paths = []
        for path, group_ids in self._item_groups.items():
            if group_id in group_ids:
                group_ids.discard(group_id)
                affected_paths.append(path)

        # Clean up empty sets
        self._item_groups = {p: gids for p, gids in self._item_groups.items() if gids}

        del self._groups[group_id]
        self._save_groups()
        self._save_item_groups()
        self.group_deleted.emit(group_id)

        # Notify about affected items
        for path in affected_paths:
            self.item_groups_changed.emit(path)

    def rename_group(self, group_id: str, new_name: str):
        """Rename a group."""
        self._ensure_loaded()
        if group_id in self._groups:
            self._groups[group_id].name = new_name
            self._save_groups()
            self.group_updated.emit(group_id)

    def change_group_color(self, group_id: str, new_color: str):
        """Change a group's color."""
        self._ensure_loaded()
        if group_id in self._groups:
            self._groups[group_id].color = new_color
            self._save_groups()
            self.group_updated.emit(group_id)

    def reorder_group(self, group_id: str, new_order: int):
        """Change a group's order position."""
        self._ensure_loaded()
        if group_id in self._groups:
            self._groups[group_id].order = new_order
            self._save_groups()
            self.group_updated.emit(group_id)

    def get_groups(self) -> List[GroupDef]:
        """Get list of all groups sorted by order."""
        self._ensure_loaded()
        return sorted(self._groups.values(), key=lambda g: g.order)

    def get_group(self, group_id: str) -> Optional[GroupDef]:
        """Get a group by ID."""
        self._ensure_loaded()
        return self._groups.get(group_id)

    def get_group_count(self) -> int:
        """Get number of groups."""
        self._ensure_loaded()
        return len(self._groups)

    # =========================================================================
    # ITEM-GROUP ASSIGNMENT
    # =========================================================================

    def add_to_group(self, path: str, group_id: str) -> bool:
        """
        Add an item to a group.

        Args:
            path: Path to the item
            group_id: ID of the group

        Returns:
            True if item was added, False if already in group or group doesn't exist
        """
        self._ensure_loaded()
        path = os.path.normpath(path)
        if group_id not in self._groups:
            return False

        # Check multi-group setting
        from core.settings_manager import get_setting
        multi_group_enabled = get_setting("gallery_multi_group_enabled")

        if path not in self._item_groups:
            self._item_groups[path] = set()

        if not multi_group_enabled:
            # Clear existing groups first
            self._item_groups[path].clear()

        if group_id in self._item_groups[path]:
            return False

        self._item_groups[path].add(group_id)
        self._save_item_groups()
        self.item_groups_changed.emit(path)
        return True

    def remove_from_group(self, path: str, group_id: str) -> bool:
        """
        Remove an item from a group.

        Args:
            path: Path to the item
            group_id: ID of the group

        Returns:
            True if item was removed, False if not in group
        """
        self._ensure_loaded()
        path = os.path.normpath(path)
        if path not in self._item_groups:
            return False

        if group_id not in self._item_groups[path]:
            return False

        self._item_groups[path].discard(group_id)
        if not self._item_groups[path]:
            del self._item_groups[path]
        self._save_item_groups()
        self.item_groups_changed.emit(path)
        return True

    def toggle_group_membership(self, path: str, group_id: str) -> bool:
        """
        Toggle an item's membership in a group.

        Args:
            path: Path to the item
            group_id: ID of the group

        Returns:
            True if item is now in group, False if removed
        """
        self._ensure_loaded()
        path = os.path.normpath(path)
        if path in self._item_groups and group_id in self._item_groups[path]:
            self.remove_from_group(path, group_id)
            return False
        else:
            self.add_to_group(path, group_id)
            return True

    def get_item_groups(self, path: str) -> List[str]:
        """Get list of group IDs an item belongs to."""
        self._ensure_loaded()
        path = os.path.normpath(path)
        if path not in self._item_groups:
            return []
        return list(self._item_groups[path])

    def get_item_group_colors(self, path: str) -> List[str]:
        """Get list of colors for groups an item belongs to (for visual display)."""
        self._ensure_loaded()
        group_ids = self.get_item_groups(path)  # Already normalizes
        colors = []
        for gid in group_ids:
            group = self._groups.get(gid)
            if group:
                colors.append(group.color)
        return colors[:3]  # Max 3 colors shown

    def get_primary_group_color(self, path: str) -> Optional[str]:
        """Get the primary (first) group color for an item."""
        colors = self.get_item_group_colors(path)
        return colors[0] if colors else None

    def get_items_in_group(self, group_id: str) -> List[str]:
        """Get list of all item paths in a group."""
        self._ensure_loaded()
        items = []
        for path, group_ids in self._item_groups.items():
            if group_id in group_ids:
                items.append(path)
        return items

    def get_group_item_count(self, group_id: str) -> int:
        """Get number of items in a group."""
        return len(self.get_items_in_group(group_id))

    def get_ungrouped_items(self, all_paths: List[str]) -> List[str]:
        """Get items that are not in any group."""
        self._ensure_loaded()
        return [p for p in all_paths if p not in self._item_groups or not self._item_groups[p]]

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    def add_items_to_group(self, paths: List[str], group_id: str):
        """Add multiple items to a group (batch operation)."""
        self._ensure_loaded()
        if group_id not in self._groups:
            return

        from core.settings_manager import get_setting
        multi_group_enabled = get_setting("gallery_multi_group_enabled")

        for path in paths:
            path = os.path.normpath(path)
            if path not in self._item_groups:
                self._item_groups[path] = set()
            if not multi_group_enabled:
                self._item_groups[path].clear()
            self._item_groups[path].add(group_id)
            self.item_groups_changed.emit(path)

        self._save_item_groups()

    def remove_items_from_group(self, paths: List[str], group_id: str):
        """Remove multiple items from a group (batch operation)."""
        self._ensure_loaded()
        for path in paths:
            path = os.path.normpath(path)
            if path in self._item_groups and group_id in self._item_groups[path]:
                self._item_groups[path].discard(group_id)
                if not self._item_groups[path]:
                    del self._item_groups[path]
                self.item_groups_changed.emit(path)
        self._save_item_groups()

    # =========================================================================
    # FILTERING
    # =========================================================================

    def filter_liked(self, items: List[Dict]) -> List[Dict]:
        """Filter items to only liked ones."""
        self._ensure_loaded()
        return [item for item in items if item.get('path') in self._liked_items]

    def filter_by_group(self, items: List[Dict], group_id: str) -> List[Dict]:
        """Filter items to only those in a specific group."""
        self._ensure_loaded()
        group_paths = set(self.get_items_in_group(group_id))
        return [item for item in items if item.get('path') in group_paths]

    def filter_ungrouped(self, items: List[Dict]) -> List[Dict]:
        """Filter items to only ungrouped ones."""
        self._ensure_loaded()
        return [item for item in items if item.get('path') not in self._item_groups or not self._item_groups.get(item.get('path'))]

    # =========================================================================
    # CLEANUP
    # =========================================================================

    def cleanup_missing_paths(self, existing_paths: Set[str]):
        """
        Remove likes and group memberships for paths that no longer exist.
        Call this after gallery scan to clean up stale data.
        """
        self._ensure_loaded()

        # Clean liked items
        missing_likes = self._liked_items - existing_paths
        if missing_likes:
            self._liked_items -= missing_likes
            self._save_liked_items()

        # Clean item groups
        missing_groups = [p for p in self._item_groups if p not in existing_paths]
        if missing_groups:
            for path in missing_groups:
                del self._item_groups[path]
            self._save_item_groups()
