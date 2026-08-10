"""
Gallery sorting and grouping utilities.

Pure business logic for sorting and grouping gallery items.
Extracted from UI layer for testability and reuse.
"""

from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional


def sort_items(items: List[Dict], sort_mode: str) -> List[Dict]:
    """Sort items based on sort mode.

    All sort modes use a secondary key (filename) for stability when
    primary key is identical. This prevents items with the same
    mtime/name from "jumping" between refreshes.

    Args:
        items: List of item dicts with 'name', 'mtime', 'workflow' fields
        sort_mode: One of 'date_desc', 'date_asc', 'name_asc', 'name_desc', 'workflow'

    Returns:
        Sorted list of items (new list, original unchanged)
    """
    if sort_mode == "date_desc":
        return sorted(items, key=lambda x: (-x.get('mtime', 0), x.get('name', '')))
    elif sort_mode == "date_asc":
        return sorted(items, key=lambda x: (x.get('mtime', 0), x.get('name', '')))
    elif sort_mode == "name_asc":
        return sorted(items, key=lambda x: (x.get('name', ''), -x.get('mtime', 0)))
    elif sort_mode == "name_desc":
        return sorted(items, key=lambda x: (x.get('name', ''), x.get('mtime', 0)), reverse=True)
    elif sort_mode == "workflow":
        # Sort by workflow name, then by date (newest first), then by filename
        return sorted(
            items,
            key=lambda x: (x.get('workflow') or 'zzz_unknown', -x.get('mtime', 0), x.get('name', ''))
        )
    else:
        return list(items)  # Return copy to avoid mutation


def group_items_by_prefix(
    items: List[Dict],
    separate_inputs: bool = True,
    input_group_name: str = '📥 Inputs'
) -> OrderedDict:
    """Group items by their job prefix, preserving the input sort order.

    Args:
        items: List of item dicts with 'job_prefix' field (already sorted)
        separate_inputs: If True, group all input images into a separate group
        input_group_name: Name for the input images group

    Returns:
        OrderedDict: {prefix: [items]} ordered by first item's position
    """
    groups = {}  # prefix -> (first_seen_index, [items])
    input_group = []

    for idx, item in enumerate(items):
        # Separate input images into their own group (always appended last,
        # so no first-seen index is needed for it)
        if separate_inputs and item.get('is_input', False):
            input_group.append(item)
            continue

        prefix = item.get('job_prefix') or 'Other'
        if prefix not in groups:
            groups[prefix] = (idx, [item])
        else:
            _, group_items = groups[prefix]
            group_items.append(item)

    # Sort groups by first-seen index (preserves input sort order)
    sorted_groups = sorted(groups.items(), key=lambda x: x[1][0])

    # Build ordered dict
    result = OrderedDict()
    for prefix, (_, group_items) in sorted_groups:
        result[prefix] = group_items

    # Add inputs group at the end if there are any
    if input_group:
        result[input_group_name] = input_group

    return result


def group_items_by_user_groups(
    items: List[Dict],
    get_item_groups: Callable[[str], List[str]],
    get_group_def: Callable[[str], Optional[Any]],
    fallback_to_job: bool = True,
    separate_inputs: bool = True,
    input_group_name: str = '📥 Inputs'
) -> tuple:
    """Group items by user-defined groups, preserving input sort order.

    Args:
        items: List of item dicts (already sorted)
        get_item_groups: Function(path) -> list of group_ids for an item
        get_group_def: Function(group_id) -> group definition with .name, .color, .order
        fallback_to_job: If True, ungrouped items are stacked by job_prefix
        separate_inputs: If True, group input images separately
        input_group_name: Name for the input images group

    Returns:
        Tuple of (OrderedDict of groups, dict of group_colors)
    """
    groups = {}  # group_id -> (group_def, first_seen_index, [items])
    ungrouped = []
    input_group = []

    for idx, item in enumerate(items):
        # Separate input images
        if separate_inputs and item.get('is_input', False):
            input_group.append(item)
            continue

        # Check if item is in any group
        item_path = item.get('path', '')
        item_groups = get_item_groups(item_path) if item_path else []

        if item_groups:
            # Use primary (first) group
            primary_group_id = item_groups[0]
            group_def = get_group_def(primary_group_id)
            if group_def:
                if primary_group_id not in groups:
                    groups[primary_group_id] = (group_def, idx, [item])
                else:
                    _, _, group_items = groups[primary_group_id]
                    group_items.append(item)
            else:
                ungrouped.append(item)
        else:
            ungrouped.append(item)

    # Sort groups by user-defined order, then by first-seen index
    sorted_groups = sorted(
        groups.items(),
        key=lambda x: (getattr(x[1][0], 'order', 0), x[1][1])
    )

    # Build ordered dict
    result = OrderedDict()
    group_colors = {}

    for group_id, (group_def, _, group_items) in sorted_groups:
        group_name = f"🏷 {getattr(group_def, 'name', group_id)}"
        result[group_name] = group_items
        group_colors[group_name] = getattr(group_def, 'color', None)

    # Handle ungrouped items
    if ungrouped:
        if fallback_to_job:
            # Stack ungrouped items by job prefix
            job_groups = group_items_by_prefix(ungrouped, separate_inputs=False)
            for prefix, job_items in job_groups.items():
                result[prefix] = job_items
        else:
            # Show each ungrouped item individually
            for item in ungrouped:
                result[item.get('path', str(id(item)))] = [item]

    # Add inputs group at the end
    if input_group:
        result[input_group_name] = input_group

    return result, group_colors
