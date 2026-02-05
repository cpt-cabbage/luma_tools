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
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

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


# =============================================================================
# Constants
# =============================================================================

# Input names that trigger a control_after_generate phantom widget
# in ComfyUI's frontend. This widget appears in widgets_values but NOT
# in /object_info's input definitions.
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
# Widget types are: INT, FLOAT, STRING, BOOLEAN, or a list (combo).
WIDGET_TYPE_NAMES = frozenset({'INT', 'FLOAT', 'STRING', 'BOOLEAN'})


def _is_widget_input(input_spec) -> bool:
    """Check if an input specification represents a widget (not a connection slot).

    Widget inputs have types like INT, FLOAT, STRING, BOOLEAN, or are combo
    lists. Connection inputs have typed names like MODEL, CONDITIONING, etc.
    """
    if not isinstance(input_spec, (list, tuple)) or len(input_spec) == 0:
        return False

    type_info = input_spec[0]

    # Combo type: first element is a list of options
    if isinstance(type_info, list):
        return True

    # Known widget type names
    if isinstance(type_info, str) and type_info in WIDGET_TYPE_NAMES:
        # Check for forceInput flag which makes it a connection instead
        if len(input_spec) > 1 and isinstance(input_spec[1], dict):
            if input_spec[1].get('forceInput', False):
                return False
        return True

    return False


def _parse_widget_type(input_name: str, input_spec) -> WidgetInfo:
    """Parse an input specification into a WidgetInfo."""
    type_info = input_spec[0]
    opts = input_spec[1] if len(input_spec) > 1 and isinstance(input_spec[1], dict) else {}

    # Combo type
    if isinstance(type_info, list):
        return WidgetInfo(
            name=input_name,
            widget_type='combo',
            default=opts.get('default', type_info[0] if type_info else None),
            options=type_info,
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

    # Build widget_names_for_values with phantom widget placeholders
    widget_names = []
    phantom_config = PHANTOM_WIDGETS.get(class_type, {})

    for widget in widgets:
        widget_names.append(widget.name)

        # Insert control_after_generate placeholder after seed inputs
        if widget.name in SEED_INPUT_NAMES:
            widget_names.append(None)

        # Insert node-specific phantom widgets
        key = f'after:{widget.name}'
        if key in phantom_config:
            for _ in range(phantom_config[key]):
                widget_names.append(None)

    # Append end-of-list phantoms
    if 'end' in phantom_config:
        for _ in range(phantom_config['end']):
            widget_names.append(None)

    return NodeTypeInfo(
        class_type=class_type,
        display_name=raw_info.get('display_name', class_type),
        category=raw_info.get('category', ''),
        widgets=widgets,
        widget_names_for_values=widget_names,
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

        for class_type, node_data in raw_nodes.items():
            try:
                widgets = [
                    WidgetInfo(**w) for w in node_data.get('widgets', [])
                ]
                self._node_types[class_type] = NodeTypeInfo(
                    class_type=class_type,
                    display_name=node_data.get('display_name', class_type),
                    category=node_data.get('category', ''),
                    widgets=widgets,
                    widget_names_for_values=node_data.get('widget_names_for_values', []),
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
                data['nodes'][class_type] = {
                    'display_name': node_info.display_name,
                    'category': node_info.category,
                    'widgets': [asdict(w) for w in node_info.widgets],
                    'widget_names_for_values': node_info.widget_names_for_values,
                }

            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved {len(self._node_types)} node types to: {path}")
            except Exception as e:
                logger.error(f"Failed to save cache to {path}: {e}")

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
