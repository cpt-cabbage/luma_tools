"""
ComfyUI Editable Node Extraction.

Handles parsing workflow nodes to find editable nodes (nodes with '_editable'
suffix in their title) and extracting their configuration for dynamic UI generation.
"""

import os
import re
import logging
import threading
from typing import Optional, List, Tuple, Any, Callable
from dataclasses import dataclass, field

from comfyui.workflow import load_workflow, _is_uuid, _get_subgraph_definitions
from comfyui.node_configs import EDITABLE_NODE_CONFIGS, SETTINGS_NODE_CONFIGS, WIDGET_MAPPINGS

logger = logging.getLogger(__name__)


# Cardinality of an editable slot, declared by a marker placed directly after
# '_editable' and before any '@if_'/'&if_' condition:
#   Name_editable    -> one value (historical behaviour)
#   Name_editable?   -> optional; the node is removed when left empty
#   Name_editable*   -> fan-out; one selector expands into N loader nodes
CARDINALITY_SINGLE = 'single'
CARDINALITY_OPTIONAL = 'optional'
CARDINALITY_MANY = 'many'

_CARDINALITY_MARKERS = {'*': CARDINALITY_MANY, '?': CARDINALITY_OPTIONAL}


@dataclass
class EditableNode:
    """Represents an editable node extracted from a workflow."""
    node_id: int
    node_type: str
    title: str
    display_name: str  # User-friendly name derived from title
    widget_type: str   # 'text', 'image', 'int', 'float', 'combo', 'toggle', '3d_model', 'directory', 'video'
    widget_name: str = ""  # Name of the specific widget parameter (e.g. 'steps', 'cfg', 'seed')
    current_value: Any = None
    options: List[str] = field(default_factory=list)  # For combo boxes
    condition_node: Optional[str] = None  # Node name that controls visibility (from @if_<name> syntax)
    cardinality: str = CARDINALITY_SINGLE  # 'single' | 'optional' | 'many'


def _parse_editable_marker(title: str) -> Tuple[bool, str, Optional[str], str]:
    """Parse an editable title into flag, base name, condition and cardinality.

    The cardinality marker sits between the '_editable' suffix and any
    condition, so it must be consumed before the '@if_'/'&if_' check — reading
    the condition first would fail to match on 'Name_editable*@if_Toggle' and
    silently drop the condition.

    Returns:
        (is_editable, base_title, condition_node_name, cardinality)
    """
    editable_markers = ['_editable', '_editble']
    is_editable = False
    condition_node = None
    cardinality = CARDINALITY_SINGLE
    base_title = title

    for marker in editable_markers:
        if marker not in title:
            continue
        is_editable = True
        parts = title.split(marker)
        base_title = parts[0]

        if len(parts) > 1:
            after_marker = parts[1]
            if after_marker[:1] in _CARDINALITY_MARKERS:
                cardinality = _CARDINALITY_MARKERS[after_marker[0]]
                after_marker = after_marker[1:]
            for sep in ('@if_', '&if_'):
                if after_marker.startswith(sep):
                    condition_node = after_marker[len(sep):]
                    break
        break

    return is_editable, base_title, condition_node, cardinality


def _parse_editable_title(title: str) -> Tuple[bool, str, Optional[str]]:
    """
    Parse a node title to check if it's editable and extract condition.

    Supports formats:
    - "Name_editable" - simple editable node
    - "Name_editable@if_ConditionNode" - editable node visible only when ConditionNode is true

    Note: Also supports older format with typo "editble" for backwards compatibility.

    Cardinality markers ('*', '?') are parsed but not returned here — see
    _parse_editable_marker(), which this delegates to.

    Args:
        title: Node title to parse

    Returns:
        Tuple of (is_editable, base_title, condition_node_name)
        - is_editable: True if node is editable
        - base_title: Title without _editable and @if_ parts
        - condition_node_name: Name of condition node, or None if unconditional
    """
    is_editable, base_title, condition_node, _ = _parse_editable_marker(title)
    return is_editable, base_title, condition_node


def _resolve_widget_index(node_type: str, widget_name: str) -> Optional[int]:
    """Resolve a widget index, preferring node_info cache and falling back
    to the manual WIDGET_MAPPINGS table.

    The node_info cache requires a live /object_info query from the ComfyUI
    server; for custom nodes that were never cached locally (e.g. Trellis2),
    this fallback lets us still resolve widget positions using the manual
    mappings in node_configs.py.
    """
    from comfyui.node_info import get_widget_index

    idx = get_widget_index(node_type, widget_name)
    if idx is not None:
        return idx

    mapping = WIDGET_MAPPINGS.get(node_type)
    if not mapping:
        return None
    try:
        return mapping.index(widget_name)
    except ValueError:
        return None


def _resolve_config_entries(node_type: str, config: list) -> list:
    """Resolve config entries to (widget_idx, widget_name, widget_type) tuples.

    Supports formats:
    - Name only: 'seed' — index and type auto-resolved from node_info
    - Name + type override: ('image', 'image') — index auto-resolved, type forced
    - Legacy tuple: (0, 'seed', 'int') — used as-is (3-element tuple)

    Returns list of (widget_idx, widget_name, widget_type) tuples.
    """
    from comfyui.node_info import get_widget_index, get_widget_type

    resolved = []
    for entry in config:
        if entry is None:
            continue
        if isinstance(entry, str):
            # Name-only format
            widget_name = entry
            widget_idx = get_widget_index(node_type, widget_name)
            widget_type = get_widget_type(node_type, widget_name)
            if widget_idx is None or widget_type is None:
                logger.warning(
                    f"Could not resolve widget '{widget_name}' for {node_type} "
                    f"from node_info cache (idx={widget_idx}, type={widget_type})"
                )
                continue
            resolved.append((widget_idx, widget_name, widget_type))
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            # (widget_name, override_type) format — type override for special UI widgets
            # Since the type is explicit, we only need to resolve the index;
            # fall back to WIDGET_MAPPINGS when node_info doesn't know this node.
            widget_name, override_type = entry
            widget_idx = _resolve_widget_index(node_type, widget_name)
            if widget_idx is None:
                logger.warning(
                    f"Could not resolve widget index for '{widget_name}' on {node_type}"
                )
                continue
            resolved.append((widget_idx, widget_name, override_type))
        elif isinstance(entry, (tuple, list)) and len(entry) == 3:
            # Legacy tuple format: (index, name, type)
            resolved.append(tuple(entry))
        else:
            logger.warning(f"Unknown config entry format for {node_type}: {entry}")
    return resolved


def _get_widget_options(node_type: str, widget_name: str) -> list:
    """Get combo options for a widget from node_info cache."""
    from comfyui.node_info import get_widget_info
    widget_info = get_widget_info(node_type, widget_name)
    if widget_info and widget_info.options:
        return widget_info.options
    return []


# Map ComfyUI type strings to widget_type identifiers
_COMFYUI_TYPE_MAP = {
    'INT': 'int',
    'FLOAT': 'float',
    'BOOLEAN': 'toggle',
    'STRING': 'string',  # May be overridden to 'text' if multiline
    'COMBO': 'combo',
}

# Phantom/internal widgets that should be skipped
_PHANTOM_WIDGET_NAMES = {'control_after_generate'}

# Memoization for extract_editable_nodes / extract_settings_nodes:
# path -> (mtime, result). Bounded implicitly by the number of workflow presets
# in use. Both live on the network workflows share, and the UI re-extracts on
# every preset and variant switch, so re-parsing is a remote read each time.
_editable_cache = {}
_editable_cache_lock = threading.RLock()
_settings_cache = {}
_settings_cache_lock = threading.RLock()


def _cache_lookup(cache, lock, workflow_path):
    """Return (mtime, cached_result). ``mtime`` is None when unavailable."""
    try:
        mtime = os.path.getmtime(workflow_path)
    except OSError:
        return None, None
    with lock:
        entry = cache.get(workflow_path)
    if entry is not None and entry[0] == mtime:
        return mtime, entry[1]
    return mtime, None


def _cache_store(cache, lock, workflow_path, mtime, result):
    """Record a parse result keyed by the file's mtime."""
    if mtime is None:
        return
    with lock:
        cache[workflow_path] = (mtime, result)


def clear_workflow_parse_caches():
    """Drop memoized editable/settings extraction results (used by tests)."""
    with _editable_cache_lock:
        _editable_cache.clear()
    with _settings_cache_lock:
        _settings_cache.clear()


def _extract_subgraph_widgets(
    node: dict,
    display_name: str,
    condition_node: Optional[str],
    subgraph_defs: dict,
    cardinality: str = CARDINALITY_SINGLE,
) -> List[EditableNode]:
    """Extract EditableNode entries from a subgraph/component node.

    Subgraph nodes (UUID type) store their parameters in proxyWidgets and
    widgets_values.  This function parses those structures to create one
    EditableNode per exposed widget parameter.

    Args:
        node: The raw node dict from the workflow
        display_name: Cleaned display name for the node
        condition_node: Optional condition node name for visibility
        subgraph_defs: Dict mapping subgraph UUID -> definition dict
        cardinality: Slot cardinality inherited from the node's title marker

    Returns:
        List of EditableNode objects, one per widget parameter
    """
    node_id = node.get('id')
    node_type = node.get('type')
    title = node.get('title', '')
    widgets_values = node.get('widgets_values', [])
    if isinstance(widgets_values, dict):
        widgets_values = list(widgets_values.values())
    properties = node.get('properties', {})
    proxy_widgets = properties.get('proxyWidgets', [])
    node_inputs = node.get('inputs', [])
    sg_def = subgraph_defs.get(node_type, {})
    sg_def_inputs = sg_def.get('inputs', [])

    results = []

    # Build input lookup from the node's inputs array: name -> {type, label, ...}
    input_lookup = {}
    for inp in node_inputs:
        name = inp.get('name')
        if name:
            input_lookup[name] = inp

    # Build subgraph definition input lookup: name -> {type, label, ...}
    sg_input_lookup = {}
    for sg_inp in sg_def_inputs:
        name = sg_inp.get('name')
        if name:
            sg_input_lookup[name] = sg_inp

    if proxy_widgets:
        # Primary approach: use proxyWidgets property
        # Each entry is [node_id_str, widget_name]
        for idx, proxy_entry in enumerate(proxy_widgets):
            if not isinstance(proxy_entry, (list, tuple)) or len(proxy_entry) < 2:
                continue

            proxy_node_id_str, widget_name = proxy_entry[0], proxy_entry[1]

            # Skip phantom widgets
            if widget_name in _PHANTOM_WIDGET_NAMES:
                continue

            # Skip widgets that have a connection (link) - they're not user-editable
            inp_info = input_lookup.get(widget_name)
            if inp_info and inp_info.get('link') is not None:
                continue

            # Get value from widgets_values
            value = widgets_values[idx] if idx < len(widgets_values) else None

            # Determine type and display label
            widget_type = 'string'  # default fallback
            display_label = widget_name
            options = []

            if proxy_node_id_str == "-1":
                # Boundary input - look up in node's inputs and subgraph def inputs
                inp_info = input_lookup.get(widget_name) or {}
                sg_inp_info = sg_input_lookup.get(widget_name) or {}

                # Use label from input if available
                label = inp_info.get('label') or sg_inp_info.get('label')
                if label:
                    display_label = label

                # Determine type from input type field
                inp_type = inp_info.get('type') or sg_inp_info.get('type', '')
                widget_type = _COMFYUI_TYPE_MAP.get(inp_type, 'string')

                # For STRING type, check if multiline (heuristic: long values or "text" in name)
                if inp_type == 'STRING':
                    if isinstance(value, str) and (len(value) > 80 or '\n' in value):
                        widget_type = 'text'
                    elif widget_name in ('text', 'prompt', 'negative_prompt'):
                        widget_type = 'text'

            else:
                # Internal node widget - try to look up via node_info cache
                # The proxy_node_id_str references a node inside the subgraph definition
                sg_internal_nodes = sg_def.get('nodes', [])
                internal_node_type = None
                for sg_node in sg_internal_nodes:
                    if str(sg_node.get('id')) == proxy_node_id_str:
                        internal_node_type = sg_node.get('type')
                        break

                if internal_node_type:
                    from comfyui.node_info import get_widget_type, get_widget_info
                    cached_type = get_widget_type(internal_node_type, widget_name)
                    if cached_type:
                        widget_type = cached_type
                    cached_info = get_widget_info(internal_node_type, widget_name)
                    if cached_info and cached_info.options:
                        options = cached_info.options

                # Use label from node input if available
                inp_info = input_lookup.get(widget_name) or {}
                label = inp_info.get('label')
                if label:
                    display_label = label

            # For COMBO type with null value, try to get options
            if widget_type == 'combo' and not options:
                # Check if the subgraph definition input has options
                sg_inp_info = sg_input_lookup.get(widget_name) or {}
                sg_opts = sg_inp_info.get('options')
                if isinstance(sg_opts, list):
                    options = sg_opts

            # Clean up display label
            display_label = display_label.replace('_', ' ')

            multi_widget = len(proxy_widgets) - sum(
                1 for pw in proxy_widgets
                if isinstance(pw, (list, tuple)) and len(pw) >= 2
                and pw[1] in _PHANTOM_WIDGET_NAMES
            ) > 1

            results.append(EditableNode(
                node_id=node_id,
                node_type=node_type,
                title=title,
                display_name=f"{display_name} - {display_label}" if multi_widget else display_name,
                widget_type=widget_type,
                widget_name=widget_name,
                current_value=value,
                options=options,
                condition_node=condition_node,
                cardinality=cardinality,
            ))

    else:
        # Fallback: no proxyWidgets - use node's inputs array
        # Extract inputs that have a 'widget' property (these are widget inputs).
        #
        # The index into widgets_values must advance across EVERY widget input,
        # including connected ones: a widget that has been wired to another node
        # still occupies its slot in widgets_values. Filtering first and then
        # walking a separate counter read every value after the first connected
        # widget one position early.
        all_widget_inputs = [inp for inp in node_inputs
                             if isinstance(inp.get('widget'), dict)]
        editable_count = sum(1 for inp in all_widget_inputs
                             if inp.get('link') is None)

        for widget_idx, inp in enumerate(all_widget_inputs):
            # Connected widgets are driven by the graph, not the user
            if inp.get('link') is not None:
                continue

            widget_def = inp.get('widget', {})
            widget_name = widget_def.get('name', inp.get('name', ''))
            inp_type = inp.get('type', '')
            label = inp.get('label') or widget_name

            widget_type = _COMFYUI_TYPE_MAP.get(inp_type, 'string')
            if inp_type == 'STRING' and widget_name in ('text', 'prompt', 'negative_prompt'):
                widget_type = 'text'

            value = widgets_values[widget_idx] if widget_idx < len(widgets_values) else None

            display_label = label.replace('_', ' ')

            results.append(EditableNode(
                node_id=node_id,
                node_type=node_type,
                title=title,
                display_name=f"{display_name} - {display_label}" if editable_count > 1 else display_name,
                widget_type=widget_type,
                widget_name=widget_name,
                current_value=value,
                condition_node=condition_node,
                cardinality=cardinality,
            ))

    return results


@dataclass
class _NodeView:
    """One workflow node, normalised across the UI and API formats.

    ``get_value`` is the only thing that genuinely differs between the two:
    UI format resolves a positional index into ``widgets_values``, while API
    format reads the input name straight out of the ``inputs`` dict and needs
    no index arithmetic at all.
    """
    node_id: Any
    node_type: str
    title: str
    display_name: str
    condition_node: Optional[str]
    cardinality: str
    connected_inputs: set
    get_value: Callable[[str, Optional[int]], Any]
    fallback_value: Any = None       # last-resort generic text widget
    raw_node: Optional[dict] = None  # UI format only — subgraph extraction


def _build_editable_widgets(view: _NodeView, subgraph_defs: dict) -> List[EditableNode]:
    """Resolve one node into zero or more EditableNode descriptors.

    Ladder: explicit config -> node_info auto-discovery -> subgraph
    proxyWidgets -> last-resort generic text widget.
    """
    from comfyui.node_info import get_node_info, get_widget_index

    def _make(widget_type, widget_name, current_value, options, multi):
        return EditableNode(
            node_id=view.node_id,
            node_type=view.node_type,
            title=view.title,
            display_name=(f"{view.display_name} - {widget_name}" if multi
                          else view.display_name),
            widget_type=widget_type,
            widget_name=widget_name,
            current_value=current_value,
            options=options,
            condition_node=view.condition_node,
            cardinality=view.cardinality,
        )

    config = EDITABLE_NODE_CONFIGS.get(view.node_type)
    if config:
        out = []
        for widget_idx, widget_name, widget_type in _resolve_config_entries(view.node_type, config):
            if widget_name in view.connected_inputs:
                continue
            out.append(_make(widget_type, widget_name,
                             view.get_value(widget_name, widget_idx),
                             _get_widget_options(view.node_type, widget_name),
                             len(config) > 1))
        return out

    info = get_node_info(view.node_type)
    if info and info.widgets:
        out = []
        for widget in info.widgets:
            if widget.name in view.connected_inputs:
                continue
            out.append(_make(widget.widget_type, widget.name,
                             view.get_value(widget.name,
                                            get_widget_index(view.node_type, widget.name)),
                             widget.options or [],
                             len(info.widgets) > 1))
        return out

    if view.raw_node is not None and _is_uuid(view.node_type) and view.node_type in subgraph_defs:
        return _extract_subgraph_widgets(
            view.raw_node, view.display_name, view.condition_node, subgraph_defs,
            view.cardinality
        )

    if view.fallback_value is not None:
        logger.warning(f"Unknown editable node type: {view.node_type} (title: {view.title})")
        return [_make('text', 'value', view.fallback_value, [], False)]

    return []


def extract_editable_nodes(workflow_path: str) -> List[EditableNode]:
    """
    Extract all nodes with '_editable' suffix in their title from a workflow.

    Supports conditional visibility with syntax: NodeName_editable@if_ConditionNodeName
    When a condition is specified, the widget should only be visible when the
    condition node's toggle/switch is true (value != 0).

    Args:
        workflow_path: Path to workflow JSON file

    Returns:
        List of EditableNode objects describing editable nodes
    """
    if not workflow_path or not os.path.exists(workflow_path):
        return []

    # Central mtime-based memoization: several UI paths (model pickers,
    # dialogs) call this directly per invocation, each re-reading and
    # re-parsing the workflow JSON from the network workflows directory
    mtime, cached = _cache_lookup(_editable_cache, _editable_cache_lock, workflow_path)
    if cached is not None:
        return cached

    try:
        workflow = load_workflow(workflow_path)
    except Exception as e:
        logger.error(f"Error loading workflow for editable nodes: {e}")
        return []

    from comfyui.workflow import is_api_format, _is_node_reference

    subgraph_defs = _get_subgraph_definitions(workflow)
    editable_nodes = []

    if is_api_format(workflow):
        # API format keeps the marker in _meta.title and every widget value in
        # the inputs dict, so no widget-index resolution is needed. Node packs
        # whose frontend injects inputs at serialization time (e.g. the
        # MiniMax H3 Easy media ports) only survive as an API export, which is
        # why this path exists at all.
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                continue
            title = (node_data.get('_meta') or {}).get('title', '')
            is_editable, base_title, condition_node_name, cardinality =                 _parse_editable_marker(title)
            if not is_editable:
                continue

            node_type = node_data.get('class_type', '')
            inputs = node_data.get('inputs', {}) or {}
            connected = {k for k, v in inputs.items() if _is_node_reference(v)}
            plain = [v for k, v in inputs.items() if k not in connected]

            display_name = base_title.replace('_', ' ').strip()
            if not display_name or display_name == node_type:
                display_name = node_type.replace('Plus', '+')

            editable_nodes.extend(_build_editable_widgets(_NodeView(
                node_id=node_id,
                node_type=node_type,
                title=title,
                display_name=display_name,
                condition_node=condition_node_name,
                cardinality=cardinality,
                connected_inputs=connected,
                get_value=lambda name, idx, _in=inputs: _in.get(name),
                fallback_value=plain[0] if plain else None,
            ), subgraph_defs))
    else:
        nodes = workflow.get('nodes', [])

        for node in nodes:
            title = node.get('title', '')
            is_editable, base_title, condition_node_name, cardinality =                 _parse_editable_marker(title)
            if not is_editable:
                continue

            # Skip muted/bypassed nodes
            if node.get('mode', 0) in (2, 4):
                continue

            node_type = node.get('type')
            widgets_values = node.get('widgets_values', [])
            # Normalize: some workflows store widgets_values as a dict
            if isinstance(widgets_values, dict):
                widgets_values = list(widgets_values.values())

            display_name = base_title.replace('_', ' ').strip()
            if not display_name or display_name == node_type:
                display_name = node_type.replace('Plus', '+')

            def _ui_get_value(name, idx, _wv=widgets_values):
                if idx is not None and idx < len(_wv):
                    return _wv[idx]
                return None

            editable_nodes.extend(_build_editable_widgets(_NodeView(
                node_id=node.get('id'),
                node_type=node_type,
                title=title,
                display_name=display_name,
                condition_node=condition_node_name,
                cardinality=cardinality,
                connected_inputs={inp.get('name') for inp in node.get('inputs', [])
                                  if inp.get('link') is not None},
                get_value=_ui_get_value,
                fallback_value=(str(widgets_values[0]) if widgets_values else None),
                raw_node=node,
            ), subgraph_defs))

    # Sort by display_name using natural sort so "Image 2" < "Image 10"
    def _natural_sort_key(node):
        return [int(c) if c.isdigit() else c.lower()
                for c in re.split(r'(\d+)', node.display_name)]

    editable_nodes.sort(key=_natural_sort_key)

    logger.info(f"Found {len(editable_nodes)} editable nodes in workflow")
    for node in editable_nodes:
        condition_info = f" (visible when {node.condition_node})" if node.condition_node else ""
        logger.info(f"  - {node.display_name} ({node.node_type}): {node.widget_type}{condition_info}")

    _cache_store(_editable_cache, _editable_cache_lock, workflow_path,
                 mtime, editable_nodes)

    return editable_nodes


# ============================================================================
# SETTINGS NODES
# ============================================================================

@dataclass
class SettingsNode:
    """Represents a settings node extracted from a workflow.

    Settings nodes are similar to editable nodes but displayed in a separate
    collapsible section, grouped by their base title.
    """
    node_id: int
    node_type: str
    title: str
    group_name: str    # Base title used for grouping (e.g., "Sampler" from "Sampler_settings")
    widget_name: str   # Name of this specific widget
    widget_type: str   # 'int', 'float', 'combo', 'toggle', 'string'
    current_value: Any = None
    options: List[str] = field(default_factory=list)  # For combo boxes


def _parse_settings_title(title: str) -> Tuple[bool, str]:
    """
    Parse a node title to check if it's a settings node.

    Args:
        title: Node title to parse

    Returns:
        Tuple of (is_settings, group_name)
        - is_settings: True if node is a settings node
        - group_name: Title without _settings suffix
    """
    # Match `<group>_settings` either at the end of the title or as an infix
    # (`Upscale_settings_v2`), so versioned settings nodes are still detected.
    # The group name is everything before the first `_settings`.
    if title.endswith('_settings') or '_settings_' in title:
        group_name = title.split('_settings', 1)[0].replace('_', ' ').strip()
        return True, group_name
    return False, title


def _build_settings_widgets(view: _NodeView, group_name: str) -> List[SettingsNode]:
    """Resolve one node into zero or more SettingsNode descriptors.

    Ladder: SETTINGS_NODE_CONFIGS -> EDITABLE_NODE_CONFIGS -> node_info
    auto-discovery -> nothing (warn only).
    """
    from comfyui.node_info import get_node_info, get_widget_index

    def _make(widget_type, widget_name, current_value, options):
        return SettingsNode(
            node_id=view.node_id,
            node_type=view.node_type,
            title=view.title,
            group_name=group_name,
            widget_name=widget_name,
            widget_type=widget_type,
            current_value=current_value,
            options=options,
        )

    config = (SETTINGS_NODE_CONFIGS.get(view.node_type)
              or EDITABLE_NODE_CONFIGS.get(view.node_type))
    if config:
        out = []
        for widget_idx, widget_name, widget_type in _resolve_config_entries(view.node_type, config):
            if widget_name in view.connected_inputs:
                continue
            out.append(_make(widget_type, widget_name,
                             view.get_value(widget_name, widget_idx),
                             _get_widget_options(view.node_type, widget_name)))
        return out

    info = get_node_info(view.node_type)
    if info and info.widgets:
        out = []
        for widget in info.widgets:
            if widget.name in view.connected_inputs:
                continue
            out.append(_make(widget.widget_type, widget.name,
                             view.get_value(widget.name,
                                            get_widget_index(view.node_type, widget.name)),
                             widget.options or []))
        return out

    logger.warning(f"Unknown settings node type: {view.node_type} (title: {view.title})")
    return []


def extract_settings_nodes(workflow_path: str) -> List[SettingsNode]:
    """
    Extract all nodes with '_settings' suffix in their title from a workflow.

    Settings nodes are displayed in a collapsible "Workflow Settings" section,
    grouped by their base title.

    Args:
        workflow_path: Path to workflow JSON file

    Returns:
        List of SettingsNode objects describing settings nodes
    """
    if not workflow_path or not os.path.exists(workflow_path):
        return []

    # Same memoization as extract_editable_nodes — this is called on every
    # preset/variant switch and re-parses the workflow off the network share.
    mtime, cached = _cache_lookup(_settings_cache, _settings_cache_lock, workflow_path)
    if cached is not None:
        return cached

    try:
        workflow = load_workflow(workflow_path)
    except Exception as e:
        logger.error(f"Error loading workflow for settings nodes: {e}")
        return []

    from comfyui.workflow import is_api_format, _is_node_reference

    settings_nodes = []

    if is_api_format(workflow):
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                continue
            title = (node_data.get('_meta') or {}).get('title', '')
            is_settings, group_name = _parse_settings_title(title)
            if not is_settings:
                continue

            node_type = node_data.get('class_type', '')
            inputs = node_data.get('inputs', {}) or {}
            connected = {k for k, v in inputs.items() if _is_node_reference(v)}

            settings_nodes.extend(_build_settings_widgets(_NodeView(
                node_id=node_id,
                node_type=node_type,
                title=title,
                display_name=group_name,
                condition_node=None,
                cardinality=CARDINALITY_SINGLE,
                connected_inputs=connected,
                get_value=lambda name, idx, _in=inputs: _in.get(name),
            ), group_name))

        _cache_store(_settings_cache, _settings_cache_lock, workflow_path,
                     mtime, settings_nodes)
        return settings_nodes

    nodes = workflow.get('nodes', [])

    for node in nodes:
        title = node.get('title', '')

        # Parse the title for settings marker
        is_settings, group_name = _parse_settings_title(title)
        if not is_settings:
            continue

        # Skip muted/bypassed nodes
        mode = node.get('mode', 0)
        if mode in (2, 4):
            continue

        node_id = node.get('id')
        node_type = node.get('type')
        widgets_values = node.get('widgets_values', [])
        if isinstance(widgets_values, dict):
            widgets_values = list(widgets_values.values())

        # Get widget configuration for this node type
        config = SETTINGS_NODE_CONFIGS.get(node_type)
        if config:
            resolved = _resolve_config_entries(node_type, config)
            for widget_idx, widget_name, widget_type in resolved:
                current_value = None
                if widget_idx is not None and widget_idx < len(widgets_values):
                    current_value = widgets_values[widget_idx]

                options = _get_widget_options(node_type, widget_name)

                settings_nodes.append(SettingsNode(
                    node_id=node_id,
                    node_type=node_type,
                    title=title,
                    group_name=group_name,
                    widget_name=widget_name,
                    widget_type=widget_type,
                    current_value=current_value,
                    options=options,
                ))
        else:
            # Unknown node type - try EDITABLE_NODE_CONFIGS as fallback
            fallback_config = EDITABLE_NODE_CONFIGS.get(node_type)
            if fallback_config:
                resolved = _resolve_config_entries(node_type, fallback_config)
                for widget_idx, widget_name, widget_type in resolved:
                    current_value = None
                    if widget_idx is not None and widget_idx < len(widgets_values):
                        current_value = widgets_values[widget_idx]

                    options = _get_widget_options(node_type, widget_name)

                    settings_nodes.append(SettingsNode(
                        node_id=node_id,
                        node_type=node_type,
                        title=title,
                        group_name=group_name,
                        widget_name=widget_name,
                        widget_type=widget_type,
                        current_value=current_value,
                        options=options,
                    ))
            else:
                # Try auto-discovery from node_info cache
                from comfyui.node_info import get_node_info, get_widget_index
                info = get_node_info(node_type)
                if info and info.widgets:
                    for widget in info.widgets:
                        widget_idx = get_widget_index(node_type, widget.name)
                        current_value = None
                        if widget_idx is not None and widget_idx < len(widgets_values):
                            current_value = widgets_values[widget_idx]
                        options = widget.options or []
                        settings_nodes.append(SettingsNode(
                            node_id=node_id,
                            node_type=node_type,
                            title=title,
                            group_name=group_name,
                            widget_name=widget.name,
                            widget_type=widget.widget_type,
                            current_value=current_value,
                            options=options,
                        ))
                else:
                    logger.warning(f"Unknown settings node type: {node_type} (title: {title})")

    if settings_nodes:
        logger.info(f"Found {len(settings_nodes)} settings nodes in workflow")
        # Group by group_name for logging
        groups = {}
        for node in settings_nodes:
            if node.group_name not in groups:
                groups[node.group_name] = []
            groups[node.group_name].append(node)
        for group, nodes_list in groups.items():
            logger.info(f"  {group}: {[n.widget_name for n in nodes_list]}")

    _cache_store(_settings_cache, _settings_cache_lock, workflow_path,
                 mtime, settings_nodes)

    return settings_nodes
