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
from .base_manager import BaseGalleryManager

logger = logging.getLogger(__name__)


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
            color=data.get("color", UIColors.GROUP_COLORS[0]),
            created=data.get("created", datetime.now().isoformat()),
            order=data.get("order", 0)
        )


class FavoritesManager(BaseGalleryManager, QObject):
    """
    Manages likes and groups for gallery items.

    Inherits from BaseGalleryManager for convenience properties and from
    QObject for signal support.

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

    # Batch signals for performance - emit once with all affected paths instead of per-item
    items_liked_batch = Signal(list)  # list of paths that were liked
    items_unliked_batch = Signal(list)  # list of paths that were unliked
    items_groups_changed_batch = Signal(list)  # list of paths whose groups changed

    def __init__(self, tab):
        """
        Initialize the favorites manager.

        Args:
            tab: Reference to the GalleryTab
        """
        BaseGalleryManager.__init__(self, tab)
        QObject.__init__(self)
        self._liked_items: Set[str] = set()
        self._groups: Dict[str, GroupDef] = {}
        self._item_groups: Dict[str, Set[str]] = {}  # path -> set of group_ids
        self._group_items: Dict[str, Set[str]] = {}  # group_id -> set of paths (reverse index)
        self._hash_index: Dict[str, str] = {}  # content_hash -> path (for liked/grouped items)
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
        self._group_items = {}  # Build reverse index
        if item_groups_dict:
            for path, group_ids in item_groups_dict.items():
                norm_path = os.path.normpath(path)
                group_ids_set = set(group_ids) if group_ids else set()
                self._item_groups[norm_path] = group_ids_set
                # Build reverse index: group_id -> set of paths
                for gid in group_ids_set:
                    if gid not in self._group_items:
                        self._group_items[gid] = set()
                    self._group_items[gid].add(norm_path)

        # Load hash index (content_hash -> path for liked/grouped items)
        hash_index_dict = get_setting("gallery_hash_index")
        self._hash_index = {}
        if hash_index_dict and isinstance(hash_index_dict, dict):
            self._hash_index = dict(hash_index_dict)

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

    def _save_hash_index(self):
        """Save hash index to settings."""
        from core.settings_manager import set_setting
        set_setting("gallery_hash_index", dict(self._hash_index), verbose=False)

    def register_hash(self, path: str, content_hash: str):
        """Register a content hash for a file path.

        Called during gallery scan to associate current file hash with path.
        Does not save immediately (batched during scan) — saved on next mutation.

        Args:
            path: File path
            content_hash: SHA-256 content hash
        """
        if content_hash:
            self._ensure_loaded()
            self._hash_index[content_hash] = os.path.normpath(path)

    def _resolve_and_migrate(self, path: str, content_hash: str = None) -> str:
        """Resolve a path using hash index, auto-migrating if file was renamed.

        Args:
            path: Current file path
            content_hash: Optional content hash for the file

        Returns:
            The resolved path (may be the same or migrated)
        """
        path = os.path.normpath(path)

        # Fast path: already known by current path
        if path in self._liked_items or path in self._item_groups:
            return path

        if not content_hash:
            return path

        # Hash lookup: find old path that was liked/grouped with this hash
        old_path = self._hash_index.get(content_hash)
        if not old_path or old_path == path:
            return path

        # Check if the old path has favorites data that should be migrated
        if old_path in self._liked_items or old_path in self._item_groups:
            self._migrate_path(old_path, path, content_hash)

        return path

    def _migrate_path(self, old_path: str, new_path: str, content_hash: str):
        """Migrate all favorites data from old_path to new_path.

        Args:
            old_path: Previous file path (has favorites data)
            new_path: New file path (same content, different name/location)
            content_hash: Content hash linking the two
        """
        migrated = False

        # Migrate likes
        if old_path in self._liked_items:
            self._liked_items.discard(old_path)
            self._liked_items.add(new_path)
            migrated = True

        # Migrate group memberships
        if old_path in self._item_groups:
            group_ids = self._item_groups.pop(old_path)
            self._item_groups[new_path] = group_ids
            # Update reverse index
            for gid in group_ids:
                if gid in self._group_items:
                    self._group_items[gid].discard(old_path)
                    self._group_items[gid].add(new_path)
            migrated = True

        # Update hash index
        self._hash_index[content_hash] = new_path

        if migrated:
            self._save_liked_items()
            self._save_item_groups()
            self._save_hash_index()
            logger.info(f"Favorites: migrated '{os.path.basename(old_path)}' -> "
                        f"'{os.path.basename(new_path)}' (hash match)")

    # =========================================================================
    # LIKES
    # =========================================================================

    def toggle_like(self, path: str, content_hash: str = None) -> bool:
        """
        Toggle like status for an item.

        Args:
            path: Path to the item
            content_hash: Optional content hash for hash-based migration

        Returns:
            True if item is now liked, False if unliked
        """
        self._ensure_loaded()
        if content_hash:
            self.register_hash(path, content_hash)
        path = os.path.normpath(path)
        path = self._resolve_and_migrate(path, content_hash)
        if path in self._liked_items:
            self._liked_items.discard(path)
            is_liked = False
        else:
            self._liked_items.add(path)
            is_liked = True
        self._save_liked_items()
        self.like_changed.emit(path, is_liked)
        return is_liked

    def is_liked(self, path: str, content_hash: str = None) -> bool:
        """Check if an item is liked.

        Args:
            path: Path to the item
            content_hash: Optional content hash for hash-based migration
        """
        self._ensure_loaded()
        path = os.path.normpath(path)
        if content_hash:
            path = self._resolve_and_migrate(path, content_hash)
        return path in self._liked_items

    def get_liked_items(self) -> List[str]:
        """Get list of all liked item paths."""
        self._ensure_loaded()
        return list(self._liked_items)

    def like_items(self, paths: List[str]):
        """Like multiple items (batch operation).

        Emits items_liked_batch signal once with all affected paths instead of
        per-item signals for performance.
        """
        self._ensure_loaded()
        affected_paths = []
        for path in paths:
            path = os.path.normpath(path)
            if path not in self._liked_items:
                self._liked_items.add(path)
                affected_paths.append(path)
        if affected_paths:
            self._save_liked_items()
            self.items_liked_batch.emit(affected_paths)

    def unlike_items(self, paths: List[str]):
        """Unlike multiple items (batch operation).

        Emits items_unliked_batch signal once with all affected paths instead of
        per-item signals for performance.
        """
        self._ensure_loaded()
        affected_paths = []
        for path in paths:
            path = os.path.normpath(path)
            if path in self._liked_items:
                self._liked_items.discard(path)
                affected_paths.append(path)
        if affected_paths:
            self._save_liked_items()
            self.items_unliked_batch.emit(affected_paths)

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
            for c in UIColors.GROUP_COLORS:
                if c not in used_colors:
                    color = c
                    break
            if color is None:
                color = UIColors.GROUP_COLORS[len(self._groups) % len(UIColors.GROUP_COLORS)]

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

        # Use reverse index to get affected paths (O(1) instead of O(n))
        affected_paths = list(self._group_items.get(group_id, set()))

        # Remove group from all affected items
        for path in affected_paths:
            if path in self._item_groups:
                self._item_groups[path].discard(group_id)

        # Clean up empty sets
        self._item_groups = {p: gids for p, gids in self._item_groups.items() if gids}

        # Clean up reverse index
        if group_id in self._group_items:
            del self._group_items[group_id]

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

    def add_to_group(self, path: str, group_id: str, content_hash: str = None) -> bool:
        """
        Add an item to a group.

        Args:
            path: Path to the item
            group_id: ID of the group
            content_hash: Optional content hash for hash-based migration

        Returns:
            True if item was added, False if already in group or group doesn't exist
        """
        self._ensure_loaded()
        if content_hash:
            self.register_hash(path, content_hash)
        path = os.path.normpath(path)
        path = self._resolve_and_migrate(path, content_hash)
        if group_id not in self._groups:
            return False

        # Check multi-group setting
        from core.settings_manager import get_setting
        multi_group_enabled = get_setting("gallery_multi_group_enabled")

        if path not in self._item_groups:
            self._item_groups[path] = set()

        if not multi_group_enabled:
            # Clear existing groups first - also update reverse index
            for old_gid in list(self._item_groups[path]):
                if old_gid in self._group_items:
                    self._group_items[old_gid].discard(path)
            self._item_groups[path].clear()

        if group_id in self._item_groups[path]:
            return False

        self._item_groups[path].add(group_id)
        # Update reverse index
        if group_id not in self._group_items:
            self._group_items[group_id] = set()
        self._group_items[group_id].add(path)
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
        # Update reverse index
        if group_id in self._group_items:
            self._group_items[group_id].discard(path)
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

    def get_item_groups(self, path: str, content_hash: str = None) -> List[str]:
        """Get list of group IDs an item belongs to.

        Args:
            path: Path to the item
            content_hash: Optional content hash for hash-based migration
        """
        self._ensure_loaded()
        path = os.path.normpath(path)
        if content_hash:
            path = self._resolve_and_migrate(path, content_hash)
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
        """Get list of all item paths in a group.

        Performance optimization: Uses reverse index for O(1) lookup instead of O(n) scan.
        """
        self._ensure_loaded()
        return list(self._group_items.get(group_id, set()))

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
        """Add multiple items to a group (batch operation).

        Emits items_groups_changed_batch signal once with all affected paths instead of
        per-item signals for performance.
        """
        self._ensure_loaded()
        if group_id not in self._groups:
            return

        from core.settings_manager import get_setting
        multi_group_enabled = get_setting("gallery_multi_group_enabled")

        # Ensure reverse index entry exists
        if group_id not in self._group_items:
            self._group_items[group_id] = set()

        affected_paths = []
        for path in paths:
            path = os.path.normpath(path)
            if path not in self._item_groups:
                self._item_groups[path] = set()
            if not multi_group_enabled:
                # Clear existing groups - update reverse index
                for old_gid in list(self._item_groups[path]):
                    if old_gid in self._group_items:
                        self._group_items[old_gid].discard(path)
                self._item_groups[path].clear()
            self._item_groups[path].add(group_id)
            # Update reverse index
            self._group_items[group_id].add(path)
            affected_paths.append(path)

        if affected_paths:
            self._save_item_groups()
            self.items_groups_changed_batch.emit(affected_paths)

    def remove_items_from_group(self, paths: List[str], group_id: str):
        """Remove multiple items from a group (batch operation).

        Emits items_groups_changed_batch signal once with all affected paths instead of
        per-item signals for performance.
        """
        self._ensure_loaded()
        affected_paths = []
        for path in paths:
            path = os.path.normpath(path)
            if path in self._item_groups and group_id in self._item_groups[path]:
                self._item_groups[path].discard(group_id)
                # Update reverse index
                if group_id in self._group_items:
                    self._group_items[group_id].discard(path)
                if not self._item_groups[path]:
                    del self._item_groups[path]
                affected_paths.append(path)
        if affected_paths:
            self._save_item_groups()
            self.items_groups_changed_batch.emit(affected_paths)

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

    def _get_file_type(self, path: str) -> str:
        """Determine file type from extension."""
        from core.config import (
            GALLERY_IMAGE_EXTENSIONS,
            GALLERY_MODEL_EXTENSIONS,
            GALLERY_VIDEO_EXTENSIONS,
            GALLERY_AUDIO_EXTENSIONS,
        )
        ext = os.path.splitext(path)[1].lower()
        if ext in GALLERY_MODEL_EXTENSIONS:
            return 'model'
        elif ext in GALLERY_VIDEO_EXTENSIONS:
            return 'video'
        elif ext in GALLERY_AUDIO_EXTENSIONS:
            return 'audio'
        elif ext in GALLERY_IMAGE_EXTENSIONS:
            return 'image'
        return 'image'  # Default

    def get_liked_items_as_dicts(self, exclude_dir: Optional[str] = None) -> List[Dict]:
        """Get all liked items as gallery item dicts.

        Creates minimal item dicts for liked paths that exist.
        Used when showing "Liked" filter to include items from any directory.

        Args:
            exclude_dir: Optional directory path to exclude items from

        Returns:
            List of gallery item dicts for liked items
        """
        self._ensure_loaded()
        items = []
        exclude_dir_norm = os.path.normpath(exclude_dir) if exclude_dir else None

        for path in self._liked_items:
            # Skip items in the excluded directory
            if exclude_dir_norm and os.path.normpath(path).startswith(exclude_dir_norm):
                continue

            if os.path.exists(path):
                filename = os.path.basename(path)
                items.append({
                    'path': path,
                    'filename': filename,
                    'name': filename.lower(),
                    'type': self._get_file_type(path),
                    'mtime': os.path.getmtime(path),
                    'is_external': True,
                    'has_metadata': False,
                    'metadata_level': 'none',
                    'is_input': False,
                    'job_prefix': None,
                })
        return items

    def get_group_items_as_dicts(self, group_id: str, exclude_dir: Optional[str] = None) -> List[Dict]:
        """Get all items in a group as gallery item dicts.

        Creates minimal item dicts for grouped paths that exist.
        Used when showing group filter to include items from any directory.

        Args:
            group_id: The group ID to get items for
            exclude_dir: Optional directory path to exclude items from

        Returns:
            List of gallery item dicts for items in the group
        """
        self._ensure_loaded()
        items = []
        exclude_dir_norm = os.path.normpath(exclude_dir) if exclude_dir else None
        group_paths = self.get_items_in_group(group_id)

        for path in group_paths:
            # Skip items in the excluded directory
            if exclude_dir_norm and os.path.normpath(path).startswith(exclude_dir_norm):
                continue

            if os.path.exists(path):
                filename = os.path.basename(path)
                items.append({
                    'path': path,
                    'filename': filename,
                    'name': filename.lower(),
                    'type': self._get_file_type(path),
                    'mtime': os.path.getmtime(path),
                    'is_external': True,
                    'has_metadata': False,
                    'metadata_level': 'none',
                    'is_input': False,
                    'job_prefix': None,
                })
        return items

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
