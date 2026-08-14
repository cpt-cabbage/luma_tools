"""
ComfyUI Node Info Service.

Auto-discovers node widget configurations by querying ComfyUI's /object_info
endpoint and caching results locally. Replaces the need for manually maintaining
WIDGET_MAPPINGS for every custom node type.

Usage:
    from comfyui.node_info import get_widget_names, get_widget_info, refresh_node_info

    # Get ordered widget names for API format conversion
    names = get_widget_names("KSampler")  # ['seed', None, 'steps', 'cfg', ...]

    # Get full widget info (type, default, min/max, options)
    info = get_widget_info("KSampler", "steps")  # WidgetInfo(...)

    # Refresh cache from running server
    refresh_node_info("http://127.0.0.1:8188")
"""

import os
import json
import time
import logging
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict, fields
from typing import Any, Dict, List, Optional, Set

from core.config import USER_SETTINGS_DIR

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class WidgetInfo:
    """Information about a single widget input on a ComfyUI node."""
    name: str
    widget_type: str  # 'int', 'float', 'string', 'text', 'combo', 'toggle'
    default: Any = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: Optional[float] = None
    options: Optional[List[str]] = None  # For combo types
    multiline: bool = False  # For string type
    # True when ComfyUI attaches a 'control_after_generate' phantom widget to
    # this input. Read from the input spec's options dict; see
    # _widget_has_control_after_generate() for why this beats name-matching.
    control_after_generate: bool = False


@dataclass
class NodeTypeInfo:
    """Parsed information about a ComfyUI node type."""
    class_type: str
    display_name: str
    category: str
    widgets: List[WidgetInfo] = field(default_factory=list)
    # widget_names_for_values includes None placeholders for phantom widgets
    # (control_after_generate, upload buttons, etc.)
    widget_names_for_values: List[Optional[str]] = field(default_factory=list)
    # Names of all required inputs (both widget and connection inputs)
    required_input_names: List[str] = field(default_factory=list)
    # Names of all optional inputs (both widget and connection inputs).
    # Used to discover the ceiling for numbered slot inputs such as
    # media_1..media_15, which fan-out expansion allocates into.
    optional_input_names: List[str] = field(default_factory=list)


# =============================================================================
# Constants
# =============================================================================

# Fallback for input names that trigger a control_after_generate phantom
# widget. Only consulted when /object_info does NOT report the explicit
# `control_after_generate` flag (older ComfyUI builds) — see
# _widget_has_control_after_generate(). The phantom widget occupies a slot in
# widgets_values but is absent from /object_info's input definitions.
SEED_INPUT_NAMES = frozenset({'seed', 'noise_seed'})

# Nodes with additional phantom widgets (buttons, internal state) that appear
# in widgets_values but aren't in /object_info. Format: {node_type: [(position, count)]}
# where position is 'after:<widget_name>' or 'end', and count is number of phantoms.
PHANTOM_WIDGETS = {
    'LoadImage': {'after:image': 1},            # 'upload' button
    'Trellis2LoadImageWithTransparency': {'after:image': 1},  # 'upload' button
    'Load3D': {'after:model_file': 3},          # 3 buttons (upload3dmodel, uploadExtraResources, clear)
    'ImageBatchMulti': {'end': 1},              # internal state
    'GeomPackPreviewMeshVTK': {'end': 1},       # internal state
}

# Nodes with missing widgets that /object_info doesn't report correctly.
# These are real widgets that appear in widgets_values but ComfyUI doesn't
# include them in the input definitions (display widgets, dynamic combos, etc.).
# Format: {node_type: [(position, widget_name)]} where position is 'after:<widget_name>' or 'end'.
MISSING_WIDGETS = {
    'SaveAudioMP3': {'after:filename_prefix': ['quality']},  # quality combo not reported by /object_info
    'SaveAudioOpus': {'after:filename_prefix': ['quality']},  # same issue as MP3
}

DEFAULT_SERVER_URL = "http://127.0.0.1:8188"
CACHE_FILENAME = "comfyui_node_info.json"
CACHE_MAX_AGE_HOURS = 168  # 7 days
NETWORK_CACHE_SUBDIR = "_node_info"


# =============================================================================
# Type Classification
# =============================================================================

# These are ComfyUI's built-in connection types that are NOT widgets.
# Any input type NOT in this set and NOT a list is assumed to be a
# connection type too (custom node types like "TRELLIS_MODEL" etc.).
#
# Widget types are: INT, FLOAT, STRING, BOOLEAN, COMBO, or a bare list.
#
# 'COMBO' matters: nodes written against ComfyUI's V3 schema serialize combos
# as ("COMBO", {"options": [...]}) rather than the V1 ([opt1, opt2, ...],)
# form. Treating that as a connection slot drops the widget from
# widget_names_for_values, which silently shifts every widget after it by one
# index — so widget values land on the wrong inputs with no error raised.
WIDGET_TYPE_NAMES = frozenset({'INT', 'FLOAT', 'STRING', 'BOOLEAN', 'COMBO'})


def _is_combo_spec(type_info) -> bool:
    """True when an input's type field denotes a combo/dropdown widget.

    Handles both serializations:
    - V1: the type field IS the list of options
    - V3: the type field is the literal string "COMBO" (options live in opts)
    """
    if isinstance(type_info, list):
        return True
    return isinstance(type_info, str) and type_info == 'COMBO'


def _is_widget_input(input_spec) -> bool:
    """Check if an input specification represents a widget (not a connection slot).

    Widget inputs have types like INT, FLOAT, STRING, BOOLEAN, COMBO, or are
    bare combo lists. Connection inputs have typed names like MODEL,
    CONDITIONING, etc.
    """
    if not isinstance(input_spec, (list, tuple)) or len(input_spec) == 0:
        return False

    type_info = input_spec[0]

    # Combo type (V1 bare list or V3 "COMBO")
    if _is_combo_spec(type_info):
        return True

    # Known widget type names
    if isinstance(type_info, str) and type_info in WIDGET_TYPE_NAMES:
        # Check for forceInput flag which makes it a connection instead
        if len(input_spec) > 1 and isinstance(input_spec[1], dict):
            if input_spec[1].get('forceInput', False):
                return False
        return True

    return False


def _widget_has_control_after_generate(widget: WidgetInfo) -> bool:
    """True when this widget is followed by a control_after_generate phantom.

    Prefers the explicit flag ComfyUI reports in the input's options dict.
    Falls back to matching the input name against SEED_INPUT_NAMES only when
    the flag is absent, which is the case on older ComfyUI builds — the name
    heuristic misses any node whose seeded input isn't literally called
    'seed'/'noise_seed' (rand_seed, seed_num, and most custom-node variants).
    """
    if widget.control_after_generate:
        return True
    return widget.name in SEED_INPUT_NAMES


def _parse_widget_type(input_name: str, input_spec) -> WidgetInfo:
    """Parse an input specification into a WidgetInfo.

    Understands both the V1 serialization ([type_or_options, opts]) and the V3
    schema, where combos arrive as ("COMBO", {"options": [...]}) and the
    control_after_generate phantom is declared explicitly in the opts dict.
    """
    type_info = input_spec[0]
    opts = input_spec[1] if len(input_spec) > 1 and isinstance(input_spec[1], dict) else {}
    # ComfyUI reports this for INT and COMBO inputs that carry the phantom
    # 'control_after_generate' widget. Absent on older builds.
    cag = bool(opts.get('control_after_generate', False))

    # Combo type — options are the type field itself (V1) or in opts (V3)
    if _is_combo_spec(type_info):
        options = type_info if isinstance(type_info, list) else opts.get('options')
        if not isinstance(options, list):
            options = []
        return WidgetInfo(
            name=input_name,
            widget_type='combo',
            default=opts.get('default', options[0] if options else None),
            options=options,
            control_after_generate=cag,
        )

    # Scalar types
    if type_info == 'INT':
        return WidgetInfo(
            name=input_name,
            widget_type='int',
            default=opts.get('default'),
            min_val=opts.get('min'),
            max_val=opts.get('max'),
            step=opts.get('step'),
            control_after_generate=cag,
        )
    elif type_info == 'FLOAT':
        return WidgetInfo(
            name=input_name,
            widget_type='float',
            default=opts.get('default'),
            min_val=opts.get('min'),
            max_val=opts.get('max'),
            step=opts.get('step', opts.get('round')),
        )
    elif type_info == 'STRING':
        multiline = opts.get('multiline', False)
        return WidgetInfo(
            name=input_name,
            widget_type='text' if multiline else 'string',
            default=opts.get('default'),
            multiline=multiline,
        )
    elif type_info == 'BOOLEAN':
        return WidgetInfo(
            name=input_name,
            widget_type='toggle',
            default=opts.get('default'),
        )

    # Fallback
    return WidgetInfo(name=input_name, widget_type='string', default=opts.get('default'))


# =============================================================================
# Node Info Parsing
# =============================================================================

def _parse_node_info(class_type: str, raw_info: dict) -> NodeTypeInfo:
    """Parse raw /object_info response for a single node type into NodeTypeInfo."""
    input_data = raw_info.get('input', {})
    input_order = raw_info.get('input_order', {})

    # Collect all widget inputs in order
    widgets = []
    ordered_names = (
        input_order.get('required', []) +
        input_order.get('optional', [])
    )

    # Build input lookup from required + optional
    all_inputs = {}
    for section in ('required', 'optional'):
        section_data = input_data.get(section, {})
        if isinstance(section_data, dict):
            all_inputs.update(section_data)

    for input_name in ordered_names:
        if input_name not in all_inputs:
            continue
        input_spec = all_inputs[input_name]
        if _is_widget_input(input_spec):
            widget = _parse_widget_type(input_name, input_spec)
            widgets.append(widget)

    # Build widget_names_for_values with phantom widget placeholders and missing widgets
    widget_names = []
    phantom_config = PHANTOM_WIDGETS.get(class_type, {})
    missing_config = MISSING_WIDGETS.get(class_type, {})

    for widget in widgets:
        widget_names.append(widget.name)

        # Insert control_after_generate placeholder — flag-driven, with a
        # name-based fallback for ComfyUI builds that don't report the flag
        if _widget_has_control_after_generate(widget):
            widget_names.append(None)

        # Insert node-specific phantom widgets (buttons, internal state)
        key = f'after:{widget.name}'
        if key in phantom_config:
            for _ in range(phantom_config[key]):
                widget_names.append(None)

        # Insert missing widgets that /object_info doesn't report
        if key in missing_config:
            for missing_name in missing_config[key]:
                widget_names.append(missing_name)

    # Append end-of-list phantoms
    if 'end' in phantom_config:
        for _ in range(phantom_config['end']):
            widget_names.append(None)

    # Append end-of-list missing widgets
    if 'end' in missing_config:
        for missing_name in missing_config['end']:
            widget_names.append(missing_name)

    # Collect names of all required inputs (both widget and connection)
    required_section = input_data.get('required', {})
    required_input_names = list(required_section.keys()) if isinstance(required_section, dict) else []

    optional_section = input_data.get('optional', {})
    optional_input_names = list(optional_section.keys()) if isinstance(optional_section, dict) else []

    return NodeTypeInfo(
        class_type=class_type,
        display_name=raw_info.get('display_name', class_type),
        category=raw_info.get('category', ''),
        widgets=widgets,
        widget_names_for_values=widget_names,
        required_input_names=required_input_names,
        optional_input_names=optional_input_names,
    )


def _get_network_cache_path() -> Optional[str]:
    """Get the network cache file path from global settings."""
    try:
        from core.settings_manager import safe_get_setting
        network_path = safe_get_setting("network_output_path", "")
        if network_path and os.path.isdir(network_path):
            return os.path.join(network_path, NETWORK_CACHE_SUBDIR, CACHE_FILENAME)
    except Exception:
        pass
    return None


# =============================================================================
# Cache
# =============================================================================

class NodeInfoCache:
    """Thread-safe file-backed cache for ComfyUI node definitions."""

    def __init__(self, cache_dir: Optional[str] = None):
        self._cache_dir = cache_dir or USER_SETTINGS_DIR
        self._cache_path = os.path.join(self._cache_dir, CACHE_FILENAME)
        self._lock = threading.RLock()
        self._node_types: Dict[str, NodeTypeInfo] = {}
        self._raw_data: Optional[Dict] = None
        self._loaded = False
        self._last_fetch_time: Optional[float] = None

    def _ensure_loaded(self):
        """Load from disk if not already loaded, with network fallback."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_from_disk()
            # If local cache is empty or stale, try network cache
            if not self._node_types or self._is_data_stale():
                self._try_load_from_network()
            self._loaded = True

    def _is_data_stale(self) -> bool:
        """Check if current in-memory data is stale (no _ensure_loaded call)."""
        if not self._last_fetch_time:
            return True
        age_hours = (time.time() - self._last_fetch_time) / 3600
        return age_hours > CACHE_MAX_AGE_HOURS

    def _load_from_disk(self):
        """Load cached data from local disk."""
        if not os.path.exists(self._cache_path):
            return

        try:
            with open(self._cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._load_from_data(data)
            logger.info(f"Loaded {len(self._node_types)} node types from local cache")
        except Exception as e:
            logger.warning(f"Failed to load node info cache: {e}")

    def _load_from_data(self, data: dict):
        """Load node types from a parsed JSON data dict."""
        self._last_fetch_time = data.get('_meta', {}).get('fetch_time')
        raw_nodes = data.get('nodes', {})
        self._node_types.clear()

        # The network cache is shared by workstations that may be running
        # different luma_tools versions, so a cache written by a NEWER build
        # can carry WidgetInfo fields this build doesn't know about. Filter to
        # known fields instead of letting WidgetInfo(**w) raise TypeError and
        # drop the whole node definition.
        _widget_fields = {f.name for f in fields(WidgetInfo)}

        for class_type, node_data in raw_nodes.items():
            try:
                widgets = [
                    WidgetInfo(**{k: v for k, v in w.items() if k in _widget_fields})
                    for w in node_data.get('widgets', [])
                ]
                widget_names = node_data.get('widget_names_for_values', [])

                # Apply MISSING_WIDGETS patches to fix incomplete cached data
                missing_config = MISSING_WIDGETS.get(class_type, {})
                if missing_config:
                    # Rebuild widget_names with missing widgets inserted
                    patched_names = []
                    for name in widget_names:
                        patched_names.append(name)
                        # Check if we need to insert missing widgets after this one
                        key = f'after:{name}'
                        if key in missing_config:
                            patched_names.extend(missing_config[key])
                    # Append end-of-list missing widgets
                    if 'end' in missing_config:
                        patched_names.extend(missing_config['end'])
                    widget_names = patched_names

                self._node_types[class_type] = NodeTypeInfo(
                    class_type=class_type,
                    display_name=node_data.get('display_name', class_type),
                    category=node_data.get('category', ''),
                    widgets=widgets,
                    widget_names_for_values=widget_names,
                    required_input_names=node_data.get('required_input_names', []),
                )
            except Exception as e:
                logger.debug(f"Skipping cached node '{class_type}': {e}")

    def _try_load_from_network(self):
        """Try to load fresher data from network cache path."""
        network_path = _get_network_cache_path()
        if not network_path or not os.path.exists(network_path):
            return

        try:
            with open(network_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            network_time = data.get('_meta', {}).get('fetch_time', 0)
            if network_time > (self._last_fetch_time or 0):
                self._load_from_data(data)
                self._save_to_disk()  # Cache locally for faster future loads
                logger.info(f"Loaded {len(self._node_types)} node types from network cache")
        except Exception as e:
            logger.debug(f"Could not load from network cache: {e}")

    def _save_to_disk(self):
        """Save current data to local disk cache."""
        self.save_to_path(self._cache_path)

    def save_to_path(self, path: str):
        """Save current cache data to a specific file path.

        Used internally for local cache, and by server.py to save
        to the network path for other machines.
        """
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)

            data = {
                '_meta': {
                    'fetch_time': self._last_fetch_time or time.time(),
                    'node_count': len(self._node_types),
                },
                'nodes': {},
            }

            for class_type, node_info in self._node_types.items():
                node_entry = {
                    'display_name': node_info.display_name,
                    'category': node_info.category,
                    'widgets': [asdict(w) for w in node_info.widgets],
                    'widget_names_for_values': node_info.widget_names_for_values,
                }
                if node_info.required_input_names:
                    node_entry['required_input_names'] = node_info.required_input_names
                data['nodes'][class_type] = node_entry

            # Atomic write (unique tmp + rename): this multi-MB file is read
            # by every workstation while the server writes it — a plain
            # open('w') exposed a truncation window that silently degraded
            # widget/type resolution on readers.
            tmp_path = f"{path}.{os.getpid()}.tmp"
            try:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, path)
                logger.info(f"Saved {len(self._node_types)} node types to: {path}")
            except Exception as e:
                logger.error(f"Failed to save cache to {path}: {e}")
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass

    def update_from_server(self, raw_object_info: Dict) -> int:
        """Parse raw /object_info response and update cache.

        Returns number of node types parsed.
        """
        with self._lock:
            self._node_types.clear()
            count = 0

            for class_type, raw_info in raw_object_info.items():
                if not isinstance(raw_info, dict):
                    continue
                try:
                    node_info = _parse_node_info(class_type, raw_info)
                    self._node_types[class_type] = node_info
                    count += 1
                except Exception as e:
                    logger.debug(f"Failed to parse node '{class_type}': {e}")

            self._last_fetch_time = time.time()
            self._loaded = True
            self._save_to_disk()
            logger.info(f"Parsed {count} node types from /object_info")
            return count

    def get(self, class_type: str) -> Optional[NodeTypeInfo]:
        """Get parsed node info for a class type."""
        self._ensure_loaded()
        with self._lock:
            return self._node_types.get(class_type)

    def is_stale(self, max_age_hours: int = CACHE_MAX_AGE_HOURS) -> bool:
        """Check if cache is older than max_age_hours."""
        self._ensure_loaded()
        if not self._last_fetch_time:
            return True
        age_hours = (time.time() - self._last_fetch_time) / 3600
        return age_hours > max_age_hours

    def is_available(self) -> bool:
        """Check if any cached data exists."""
        self._ensure_loaded()
        return len(self._node_types) > 0

    @property
    def node_count(self) -> int:
        """Number of cached node types."""
        self._ensure_loaded()
        return len(self._node_types)


# =============================================================================
# Module-Level Singleton
# =============================================================================

_cache = NodeInfoCache()


# =============================================================================
# Public API
# =============================================================================

def fetch_object_info(server_url: str = DEFAULT_SERVER_URL, timeout: int = 30) -> Optional[Dict]:
    """Fetch complete node definitions from ComfyUI server's /object_info endpoint.

    Args:
        server_url: ComfyUI server URL
        timeout: Request timeout in seconds

    Returns:
        Raw object_info dict, or None on failure
    """
    url = f"{server_url.rstrip('/')}/object_info"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))
            logger.info(f"Fetched /object_info: {len(data)} node types")
            return data
    except urllib.error.URLError as e:
        logger.warning(f"Failed to fetch /object_info from {server_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching /object_info: {e}")
        return None


def refresh_node_info(server_url: str = DEFAULT_SERVER_URL, timeout: int = 30) -> int:
    """Fetch fresh node definitions from server and update cache.

    Args:
        server_url: ComfyUI server URL
        timeout: Request timeout in seconds

    Returns:
        Number of node types discovered, or 0 on failure
    """
    raw_data = fetch_object_info(server_url, timeout)
    if raw_data is None:
        return 0
    return _cache.update_from_server(raw_data)


def get_node_info(class_type: str) -> Optional[NodeTypeInfo]:
    """Get full parsed info for a node type.

    Returns None if the node type is not in cache.
    """
    return _cache.get(class_type)


def get_widget_names(class_type: str) -> Optional[List[Optional[str]]]:
    """Get ordered widget names for widgets_values mapping.

    Returns a list where each element is either a widget name (str) or None
    for phantom widgets (control_after_generate, buttons, etc.).
    Returns None if the node type is not in cache.
    """
    info = _cache.get(class_type)
    if info is None:
        return None
    return info.widget_names_for_values


def get_required_input_names(class_type: str) -> Optional[List[str]]:
    """Get names of all required inputs for a node type.

    Returns a list of input names that are required (both widget and connection).
    Returns None if the node type is not in cache.
    """
    info = _cache.get(class_type)
    if info is None:
        return None
    return info.required_input_names


def get_optional_input_names(class_type: str) -> Optional[List[str]]:
    """Names of a node type's optional inputs, or None if not cached."""
    info = get_node_info(class_type)
    return info.optional_input_names if info else None


def get_known_class_types() -> Set[str]:
    """Every class_type present in the cache.

    Empty when the cache is unavailable — callers must treat an empty result
    as "unknown", never as "nothing is installed".
    """
    _cache._ensure_loaded()
    with _cache._lock:
        return set(_cache._node_types.keys())


def get_widget_info(class_type: str, widget_name: str) -> Optional[WidgetInfo]:
    """Get full widget info for a specific widget on a node type.

    Returns WidgetInfo with type, default, min/max/step, options.
    Returns None if not found.
    """
    info = _cache.get(class_type)
    if info is None:
        return None
    for widget in info.widgets:
        if widget.name == widget_name:
            return widget
    return None


def get_widget_index(class_type: str, widget_name: str) -> Optional[int]:
    """Get the index in widgets_values for a named widget.

    Accounts for phantom widgets (control_after_generate, buttons).
    Returns None if not found.
    """
    info = _cache.get(class_type)
    if info is None:
        return None
    for i, name in enumerate(info.widget_names_for_values):
        if name == widget_name:
            return i
    return None


def get_widget_type(class_type: str, widget_name: str) -> Optional[str]:
    """Get the widget type for a named widget.

    Returns one of: 'int', 'float', 'string', 'text', 'combo', 'toggle'.
    Returns None if not found.
    """
    widget = get_widget_info(class_type, widget_name)
    if widget is None:
        return None
    return widget.widget_type


def is_cache_available() -> bool:
    """Check if cached node info exists (even if stale)."""
    return _cache.is_available()


def is_cache_stale(max_age_hours: int = CACHE_MAX_AGE_HOURS) -> bool:
    """Check if the cache is older than max_age_hours."""
    return _cache.is_stale(max_age_hours)


def get_cache_node_count() -> int:
    """Get number of node types in cache."""
    return _cache.node_count


def save_cache_to_network(network_base_path: str) -> bool:
    """Save current cache to network path for other machines to use.

    Called by server.py after ComfyUI starts to share node definitions
    with all luma_tools instances on the network.

    Args:
        network_base_path: Network output directory (e.g. W:/LumaRND/tmp/ComfyUI_OUT)

    Returns:
        True if saved successfully
    """
    if not _cache.is_available():
        logger.warning("No node info to save to network (cache empty)")
        return False

    cache_dir = os.path.join(network_base_path, NETWORK_CACHE_SUBDIR)
    cache_path = os.path.join(cache_dir, CACHE_FILENAME)

    try:
        _cache.save_to_path(cache_path)
        return True
    except Exception as e:
        logger.error(f"Failed to save cache to network: {e}")
        return False


def load_cache_from_network() -> int:
    """Try to load node info from network cache.

    Used by luma_tools clients that can't directly reach the ComfyUI server.
    The network cache is populated by server.py running on the farm.

    Returns:
        Number of node types loaded, or 0 if network cache unavailable
    """
    network_path = _get_network_cache_path()
    if not network_path or not os.path.exists(network_path):
        return 0

    try:
        with open(network_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        network_time = data.get('_meta', {}).get('fetch_time', 0)

        # Ensure local cache is loaded for comparison
        _cache._ensure_loaded()
        current_time = _cache._last_fetch_time or 0

        if network_time > current_time:
            with _cache._lock:
                _cache._load_from_data(data)
                _cache._loaded = True
                _cache._save_to_disk()
            count = len(_cache._node_types)
            logger.info(f"Loaded {count} node types from network cache")
            return count
        else:
            logger.info("Local cache is up-to-date with network cache")
            return _cache.node_count
    except Exception as e:
        logger.warning(f"Failed to load from network cache: {e}")
        return 0
