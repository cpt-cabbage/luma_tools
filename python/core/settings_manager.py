"""
Settings manager for Luma Tools.

Handles saving and loading user preferences and global settings.
Uses a registry pattern to minimize boilerplate for simple settings.
"""

import copy
import os
import time
import logging
import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, Callable, List
from .config import (
    USER_SETTINGS_DIR,
    USER_SETTINGS_FILE,
    DEFAULT_PASSES,
    REQUIRED_PASSES,
    DEFAULT_GLOBAL_SETTINGS_PATH,
    GLOBAL_SETTINGS_FILENAME,
)

logger = logging.getLogger(__name__)

# ============================================================================
# SETTINGS REGISTRY
# Declarative definitions for all settings with defaults and validation
# ============================================================================

@dataclass
class SettingDef:
    """Definition for a single setting."""
    key: str
    default: Any = None
    scope: str = "global"  # "global" or "user"
    validator: Optional[Callable[[Any], Any]] = None

# Validators
def _validate_enum(value: Any, allowed: tuple, default: Any) -> Any:
    """Validate value is in allowed set, return default if not."""
    return value if value in allowed else default

def _validate_comfyui_mode(v):
    return _validate_enum(v, ("embedded", "portable", "standalone"), "embedded")

def _validate_timeout(v, min_val=60, max_val=86400):
    try:
        return max(min_val, min(max_val, int(v)))
    except (ValueError, TypeError):
        return min_val

def _validate_server_wait_timeout(v):
    try:
        return max(30, min(3600, int(v)))
    except (ValueError, TypeError):
        return 30

def _validate_server_behavior(v):
    return _validate_enum(v, ("fail", "wait", "fail_delete"), "fail")

def _validate_stacking_mode(v):
    return _validate_enum(v, ("job", "groups", "both", "grid"), "job")

def _validate_deadline_poll_interval(v):
    """Validate Deadline poll interval (1-60 seconds)."""
    try:
        return max(1, min(60, int(v)))
    except (ValueError, TypeError):
        return 5  # Default 5 seconds

def _validate_build_type(v):
    return _validate_enum(v, ("local", "farm"), "local")

def _validate_quality_index(v):
    try:
        return max(0, min(10, int(v)))
    except (ValueError, TypeError):
        return 0

def _validate_gallery_poll_interval(v):
    """Validate Gallery network poll interval (5-300 seconds)."""
    try:
        return max(5, min(300, int(v)))
    except (ValueError, TypeError):
        return 10

# Registry of all simple settings (get/set only, no complex logic)
SETTINGS_REGISTRY: Dict[str, SettingDef] = {
    # ComfyUI Global Settings (actual paths configured in global_settings.json)
    "comfyui_path": SettingDef("comfyui_path", "", "global"),
    "comfyui_mode": SettingDef("comfyui_mode", "embedded", "global", _validate_comfyui_mode),
    "comfyui_python_path": SettingDef("comfyui_python_path", "", "global"),
    "comfyui_fast_mode": SettingDef("comfyui_fast_mode", False, "global"),
    "comfyui_lowvram": SettingDef("comfyui_lowvram", False, "global"),
    "comfyui_highvram": SettingDef("comfyui_highvram", False, "global"),
    "comfyui_normalvram": SettingDef("comfyui_normalvram", False, "global"),
    "comfyui_disable_smart_memory": SettingDef("comfyui_disable_smart_memory", False, "global"),
    "network_output_path": SettingDef("network_output_path", "", "global"),
    "comfyui_workflows_directory": SettingDef(
        "comfyui_workflows_directory",
        "",  # Empty default — resolved from network_output_path at runtime
        "global"
    ),
    "comfyui_timeout": SettingDef("comfyui_timeout", 3600, "global", _validate_timeout),
    "comfyui_port": SettingDef("comfyui_port", 8188, "global"),
    "comfyui_server_not_found_behavior": SettingDef(
        "comfyui_server_not_found_behavior", "fail", "user", _validate_server_behavior
    ),
    "comfyui_server_wait_timeout": SettingDef(
        "comfyui_server_wait_timeout", 300, "user", _validate_server_wait_timeout
    ),
    "comfyui_preset_categories": SettingDef(
        "comfyui_preset_categories",
        [
            "Upscaling", "Generation", "Video", "Style Transfer",
            "Inpainting", "3D", "Animation", "Portrait",
            "Landscape", "Abstract", "Experimental"
        ],
        "global"
    ),
    # Deadline Settings
    "deadline_poll_interval": SettingDef(
        "deadline_poll_interval", 5, "global", _validate_deadline_poll_interval
    ),
    # User Settings
    "comfyui_tab_state": SettingDef("comfyui_tab_state", {}, "user"),
    "comfyui_per_workflow_inputs": SettingDef("comfyui_per_workflow_inputs", {}, "user"),
    "tab_order": SettingDef("tab_order", [], "user"),
    "show_tray_notifications": SettingDef("show_tray_notifications", True, "user"),
    "show_verbose_logs": SettingDef("show_verbose_logs", False, "user"),
    "viewer_3d_zoom_distance": SettingDef("viewer_3d_zoom_distance", 3.5, "user"),
    "viewer_3d_shading_mode": SettingDef("viewer_3d_shading_mode", "textured", "user"),
    "viewer_3d_lighting_mode": SettingDef("viewer_3d_lighting_mode", "studio", "user"),
    "viewer_3d_hdri_name": SettingDef("viewer_3d_hdri_name", "", "user"),
    "viewer_3d_light_strength": SettingDef("viewer_3d_light_strength", 1.0, "user"),
    # Window state
    "window_width": SettingDef("window_width", 1250, "user"),
    "window_height": SettingDef("window_height", 1000, "user"),
    "window_maximized": SettingDef("window_maximized", False, "user"),
    # Version tracking
    "last_opened_version": SettingDef("last_opened_version", "0.0.0", "user"),
    # Feature requests tracking
    "feature_requests_last_read": SettingDef("feature_requests_last_read", "", "user"),
    # Gallery likes and groups
    "gallery_liked_items": SettingDef("gallery_liked_items", [], "user"),
    "gallery_groups": SettingDef("gallery_groups", {}, "user"),
    "gallery_item_groups": SettingDef("gallery_item_groups", {}, "user"),
    "gallery_hash_index": SettingDef("gallery_hash_index", {}, "user"),
    "gallery_multi_group_enabled": SettingDef("gallery_multi_group_enabled", True, "user"),
    "gallery_stacking_mode": SettingDef("gallery_stacking_mode", "both", "user", _validate_stacking_mode),
    "gallery_sidebar_collapsed": SettingDef("gallery_sidebar_collapsed", False, "user"),
    "gallery_splitter_sizes": SettingDef("gallery_splitter_sizes", [200, 800], "user"),
    "gallery_stack_colors": SettingDef("gallery_stack_colors", {}, "user"),
    "gallery_liked_color": SettingDef("gallery_liked_color", None, "user"),
    "gallery_likes_stack": SettingDef("gallery_likes_stack", False, "user"),
    "gallery_stacks_data": SettingDef("gallery_stacks_data", {}, "user"),
    "gallery_stacks_collapsed": SettingDef("gallery_stacks_collapsed", False, "user"),
    # UI display settings
    "show_statusbar_log": SettingDef("show_statusbar_log", False, "user"),
    # Pass Builder settings
    "pass_builder_publish_to_ayon": SettingDef("pass_builder_publish_to_ayon", True, "user"),
    "pass_builder_build_type": SettingDef("pass_builder_build_type", "local", "user", _validate_build_type),
    # MP4 Maker settings
    "mp4_maker_add_to_gallery": SettingDef("mp4_maker_add_to_gallery", True, "user"),
    "mp4_maker_publish_to_ayon": SettingDef("mp4_maker_publish_to_ayon", False, "user"),
    "mp4_maker_publish_on_farm": SettingDef("mp4_maker_publish_on_farm", False, "user"),
    "mp4_maker_quality_index": SettingDef("mp4_maker_quality_index", 0, "user", _validate_quality_index),
    "mp4_maker_burn_in_timecode": SettingDef("mp4_maker_burn_in_timecode", False, "user"),
    # rePublish settings
    "republish_use_farm": SettingDef("republish_use_farm", False, "user"),
    # ComfyUI seed behavior
    "comfyui_auto_randomize_seed": SettingDef("comfyui_auto_randomize_seed", False, "user"),
    # Gallery network polling interval (seconds)
    "gallery_poll_interval": SettingDef("gallery_poll_interval", 10, "user", _validate_gallery_poll_interval),
    # ComfyUI-Gallery integration settings
    "comfyui_completion_sound": SettingDef("comfyui_completion_sound", "none", "user"),  # none, subtle, system
    # ComfyUI Model Picker settings
    "comfyui_model_sort": SettingDef("comfyui_model_sort", "recently_used", "user"),
    "comfyui_model_filter": SettingDef("comfyui_model_filter", "all", "user"),
    # Cached tool paths (fallback for standalone mode)
    "cached_oiio_path": SettingDef("cached_oiio_path", "", "user"),
    "cached_oiio_info_path": SettingDef("cached_oiio_info_path", "", "user"),
    "cached_ffmpeg_path": SettingDef("cached_ffmpeg_path", "", "user"),
    # Prompt Builder Settings
    "prompt_builder_presets": SettingDef("prompt_builder_presets", {}, "user"),
    "prompt_builder_last_template": SettingDef("prompt_builder_last_template", "Natural Language", "user"),
    # Image conversion settings
    "comfyui_convert_colorspace": SettingDef("comfyui_convert_colorspace", True, "user"),
    # Viewer settings
    "viewer_live_audio_scrub": SettingDef("viewer_live_audio_scrub", False, "user"),
}

# ============================================================================
# SETTINGS CACHE
# ============================================================================

_user_settings_cache: Optional[Dict[str, Any]] = None
_global_settings_cache: Optional[Dict[str, Any]] = None
_global_settings_path_cache: Optional[str] = None
_settings_cache_lock = threading.RLock()

# Staleness tracking for the global settings cache. The global file is shared
# studio-wide and written by multiple workstations, so the cache must notice
# external changes: we re-stat the file's mtime at most every
# _GLOBAL_CACHE_TTL seconds and reload when it changed.
_GLOBAL_CACHE_TTL = 5.0
_global_settings_mtime: Optional[float] = None
_global_settings_last_check: float = 0.0

# When a custom global-settings path is configured but unreachable (network
# blip), fall back to the default path temporarily and retry the custom path
# after this many seconds instead of caching the fallback for the session.
_FALLBACK_PATH_RETRY_TTL = 30.0
_global_settings_path_fallback_until: float = 0.0

# Cross-process lockfile for global settings read-modify-write cycles.
_GLOBAL_LOCK_TIMEOUT = 5.0      # max seconds to wait for the lock
_GLOBAL_LOCK_STALE_AGE = 10.0   # break locks older than this (crashed writer)


def _acquire_global_lockfile(settings_file: str) -> Optional[str]:
    """Best-effort cross-process lock around global settings writes.

    Returns the lock path when acquired, None when the lock could not be
    obtained in time (callers proceed anyway — availability over strictness,
    the atomic tmp+rename write still prevents torn files).
    """
    lock_path = settings_file + ".lock"
    deadline = time.monotonic() + _GLOBAL_LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock_path
        except FileExistsError:
            # Break stale locks left by a crashed writer
            try:
                if time.time() - os.path.getmtime(lock_path) > _GLOBAL_LOCK_STALE_AGE:
                    os.remove(lock_path)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                logger.warning("Timed out waiting for global settings lock; proceeding without it")
                return None
            time.sleep(0.05)
        except OSError as e:
            logger.warning(f"Could not create global settings lock: {e}")
            return None


def _release_global_lockfile(lock_path: Optional[str]):
    if not lock_path:
        return
    try:
        os.remove(lock_path)
    except OSError:
        pass


def _record_global_mtime(settings_file: str):
    """Remember the on-disk mtime backing the current cache (lock held)."""
    global _global_settings_mtime, _global_settings_last_check
    try:
        _global_settings_mtime = os.path.getmtime(settings_file)
    except OSError:
        _global_settings_mtime = None
    _global_settings_last_check = time.monotonic()


def clear_settings_cache():
    """Clear all settings caches. Call after saving settings."""
    global _user_settings_cache, _global_settings_cache, _global_settings_path_cache
    global _global_settings_mtime, _global_settings_last_check, _global_settings_path_fallback_until
    with _settings_cache_lock:
        _user_settings_cache = None
        _global_settings_cache = None
        _global_settings_path_cache = None
        _global_settings_mtime = None
        _global_settings_last_check = 0.0
        _global_settings_path_fallback_until = 0.0
    from .logging_utils import clear_path_cache
    clear_path_cache()


def reload_settings():
    """Clear and reload all settings caches.

    Clears caches first, then reloads outside the lock to avoid holding it
    during potentially slow network file I/O. The reload calls will re-acquire
    the lock internally for cache population.
    """
    global _user_settings_cache, _global_settings_cache, _global_settings_path_cache
    global _global_settings_mtime, _global_settings_last_check, _global_settings_path_fallback_until
    with _settings_cache_lock:
        _user_settings_cache = None
        _global_settings_cache = None
        _global_settings_path_cache = None
        _global_settings_mtime = None
        _global_settings_last_check = 0.0
        _global_settings_path_fallback_until = 0.0
    # Reload outside lock — load functions acquire the lock internally
    # and file I/O won't block other threads from reading cached values
    load_user_settings()
    load_global_settings()


def ensure_settings_dir():
    """Ensure settings directory exists."""
    from .utils import ensure_directory
    if not os.path.exists(USER_SETTINGS_DIR):
        ensure_directory(USER_SETTINGS_DIR)
        logger.info(f"Created settings directory: {USER_SETTINGS_DIR}")


# Keys that were migrated from global to user scope.  On first load we copy
# their value from global_settings.json so existing studio configuration is
# preserved for each user.
_MIGRATED_TO_USER = (
    "comfyui_server_not_found_behavior",
    "comfyui_server_wait_timeout",
)


# ============================================================================
# CORE LOAD/SAVE FUNCTIONS
# ============================================================================

def load_user_settings() -> Dict[str, Any]:
    """Load user settings from file. Thread-safe via _settings_cache_lock."""
    from .utils import load_json
    global _user_settings_cache
    with _settings_cache_lock:
        if _user_settings_cache is not None:
            return _user_settings_cache.copy()

        default_settings = {"default_passes": DEFAULT_PASSES.copy()}

        if not os.path.exists(USER_SETTINGS_FILE):
            _user_settings_cache = default_settings
            return default_settings.copy()

        settings = load_json(USER_SETTINGS_FILE, default_settings)
        if "default_passes" not in settings:
            settings["default_passes"] = DEFAULT_PASSES.copy()
        _user_settings_cache = settings
        return settings.copy()


def _migrate_global_to_user():
    """One-time migration: copy formerly-global settings into user settings.

    Called once during startup (after both caches are populated) so that users
    who relied on the global value don't silently fall back to registry defaults.
    """
    from .utils import save_json
    global _user_settings_cache
    with _settings_cache_lock:
        if _user_settings_cache is None or _global_settings_cache is None:
            return
        migrated = False
        for key in _MIGRATED_TO_USER:
            if key not in _user_settings_cache:
                global_val = _global_settings_cache.get(key)
                if global_val is not None:
                    _user_settings_cache[key] = global_val
                    migrated = True
                    logger.info(f"Migrated setting '{key}' from global to user: {global_val}")
        if migrated:
            ensure_settings_dir()
            save_json(USER_SETTINGS_FILE, _user_settings_cache)


def save_user_settings(settings: Dict[str, Any]):
    """Save user settings to file using atomic write. Thread-safe via _settings_cache_lock."""
    from .utils import save_json
    global _user_settings_cache
    ensure_settings_dir()
    with _settings_cache_lock:
        if save_json(USER_SETTINGS_FILE, settings):
            _user_settings_cache = settings.copy()
        else:
            logger.error("Failed to save user settings")


def get_global_settings_path() -> str:
    """Get the path to the global settings directory. Thread-safe via _settings_cache_lock.

    When a custom path is configured but momentarily unreachable (network
    blip), the default path is used temporarily WITHOUT being cached for the
    session — the custom path is retried after _FALLBACK_PATH_RETRY_TTL so a
    recovered share doesn't leave writes going to the wrong file.
    """
    global _global_settings_path_cache, _global_settings_path_fallback_until
    with _settings_cache_lock:
        if _global_settings_path_cache is not None:
            return _global_settings_path_cache

        # Load inside lock to prevent TOCTOU race between cache check and load
        settings = load_user_settings()
        path = settings.get("global_settings_path")
        if not path:
            _global_settings_path_cache = DEFAULT_GLOBAL_SETTINGS_PATH
            return DEFAULT_GLOBAL_SETTINGS_PATH

        now = time.monotonic()
        if now < _global_settings_path_fallback_until:
            # Custom path recently failed — serve fallback without re-probing
            return DEFAULT_GLOBAL_SETTINGS_PATH

        if os.path.isdir(path):
            _global_settings_path_cache = path
            return path

        # Custom path configured but unreachable: temporary fallback, retry later
        _global_settings_path_fallback_until = now + _FALLBACK_PATH_RETRY_TTL
        logger.warning(
            f"Configured global settings path unreachable ({path}); "
            f"using default temporarily, will retry in {int(_FALLBACK_PATH_RETRY_TTL)}s"
        )
        return DEFAULT_GLOBAL_SETTINGS_PATH


def set_global_settings_path(path: str):
    """Set a custom global settings path. Atomic load-modify-save under lock."""
    global _global_settings_path_cache, _global_settings_cache
    with _settings_cache_lock:
        settings = load_user_settings()
        settings["global_settings_path"] = path
        save_user_settings(settings)
        _global_settings_path_cache = None
        _global_settings_cache = None
    logger.info(f"Set global settings path to: {path}")


def _get_global_settings_file() -> str:
    """Get the full path to the global settings file."""
    return os.path.join(get_global_settings_path(), GLOBAL_SETTINGS_FILENAME)


def _ensure_global_settings_dir():
    """Ensure global settings directory exists."""
    from .utils import ensure_directory
    path = get_global_settings_path()
    if not os.path.exists(path):
        ensure_directory(path)
        logger.info(f"Created global settings directory: {path}")


def _global_default_settings() -> Dict[str, Any]:
    return {
        "comfyui_workflow_presets": {},
        "admin_users": [],  # Admins: full access (all tabs including Settings) - set in global_settings.json
    }


def load_global_settings() -> Dict[str, Any]:
    """Load global settings from file. Thread-safe via _settings_cache_lock.

    The cache is invalidated automatically when the on-disk file's mtime
    changes (checked at most every _GLOBAL_CACHE_TTL seconds), so changes
    made by other workstations — presets, admin roles, HDRIs — are picked up
    without an app restart.
    """
    from .utils import load_json
    global _global_settings_cache, _global_settings_last_check
    with _settings_cache_lock:
        if _global_settings_cache is not None:
            now = time.monotonic()
            if now - _global_settings_last_check < _GLOBAL_CACHE_TTL:
                return _global_settings_cache.copy()
            # TTL expired — cheap freshness probe against the network file
            settings_file = _get_global_settings_file()
            try:
                disk_mtime = os.path.getmtime(settings_file)
            except OSError:
                disk_mtime = None  # unreachable/missing: keep serving the cache
            _global_settings_last_check = now
            if disk_mtime is None or disk_mtime == _global_settings_mtime:
                return _global_settings_cache.copy()
            logger.info("Global settings changed on disk — reloading")
            _global_settings_cache = None

        default_settings = _global_default_settings()
        settings_file = _get_global_settings_file()

        if not os.path.exists(settings_file):
            _global_settings_cache = default_settings
            _record_global_mtime(settings_file)
            return default_settings.copy()

        settings = load_json(settings_file, default_settings)
        _global_settings_cache = settings
        _record_global_mtime(settings_file)
        return settings.copy()


def save_global_settings(settings: Dict[str, Any]):
    """Save global settings to file using atomic write. Thread-safe via _settings_cache_lock.

    WARNING: this replaces the ENTIRE file with the caller's dict. For
    read-modify-write updates (adding a preset, toggling one key) use
    update_global_settings() instead — it re-reads the file from disk under a
    cross-process lock so concurrent changes from other workstations are not
    silently overwritten.
    """
    from .utils import save_json
    global _global_settings_cache
    with _settings_cache_lock:
        _ensure_global_settings_dir()
        settings_file = _get_global_settings_file()
        lock_path = _acquire_global_lockfile(settings_file)
        try:
            if save_json(settings_file, settings):
                _global_settings_cache = settings.copy()
                _record_global_mtime(settings_file)
            else:
                logger.error("Failed to save global settings")
        finally:
            _release_global_lockfile(lock_path)


def update_global_settings(mutator: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Cross-process-safe read-modify-write of the global settings file.

    The mutator receives a freshly-loaded copy of the on-disk settings (NOT
    the in-process cache, which may be stale relative to other workstations)
    and must return the modified dict, or None to abort without writing.

    The whole cycle runs under a cross-process lockfile so two workstations
    saving presets/roles/HDRIs at the same time cannot silently drop each
    other's changes.

    Returns the saved dict, or None if the mutator aborted or the save failed.
    """
    from .utils import load_json, save_json
    global _global_settings_cache
    with _settings_cache_lock:
        _ensure_global_settings_dir()
        settings_file = _get_global_settings_file()
        lock_path = _acquire_global_lockfile(settings_file)
        try:
            if os.path.exists(settings_file):
                fresh = load_json(settings_file, _global_default_settings())
            else:
                fresh = _global_default_settings()

            result = mutator(fresh)
            if result is None:
                # No change requested — still refresh the cache from disk
                _global_settings_cache = fresh
                _record_global_mtime(settings_file)
                return None

            if save_json(settings_file, result):
                _global_settings_cache = result.copy()
                _record_global_mtime(settings_file)
                return result
            logger.error("Failed to save global settings (update)")
            return None
        finally:
            _release_global_lockfile(lock_path)


# ============================================================================
# INTERNAL SAVE (lock already held)
# ============================================================================

def _save_settings_unlocked(settings_type: str, settings: Dict[str, Any]):
    """Save settings while the caller already holds _settings_cache_lock.

    Avoids nested RLock acquisition that causes lost-update races.
    """
    from .utils import save_json
    global _user_settings_cache, _global_settings_cache
    if settings_type == 'global':
        _ensure_global_settings_dir()
        settings_file = _get_global_settings_file()
        if save_json(settings_file, settings):
            _global_settings_cache = settings.copy()
            _record_global_mtime(settings_file)
        else:
            logger.error("Failed to save global settings")
    else:
        ensure_settings_dir()
        if save_json(USER_SETTINGS_FILE, settings):
            _user_settings_cache = settings.copy()
        else:
            logger.error("Failed to save user settings")


# ============================================================================
# UNIFIED SETTINGS ACCESSOR
# Generic get/set for registry-defined settings
# ============================================================================

class SettingsAccessor:
    """Unified accessor for getting/setting individual settings values."""

    def __init__(self, settings_type: str):
        self.settings_type = settings_type
        self._load_fn = load_global_settings if settings_type == 'global' else load_user_settings
        self._save_fn = save_global_settings if settings_type == 'global' else save_user_settings

    def get(self, key: str, default: Any = None) -> Any:
        """Get a settings value by key.

        The load functions return only a SHALLOW copy of the cache, so a
        container value (dict/list settings such as gallery_groups,
        comfyui_tab_state, prompt_builder_presets) would still be the very
        object held in the cache — a caller mutating it in place would
        silently poison the cache and could have that unintended change
        flushed to the shared network file by an unrelated save. Hand out a
        deep copy for containers; scalars need no copy, so the common path
        stays free.
        """
        value = self._load_fn().get(key, default)
        if isinstance(value, (dict, list, set)):
            return copy.deepcopy(value)
        return value

    def set(self, key: str, value: Any, verbose: bool = True):
        """Set a settings value by key. Atomic load-modify-save under lock.

        Global scope goes through update_global_settings() so the value is
        merged into a fresh read of the shared network file under a
        cross-process lock — never written from a possibly-stale cache.
        """
        if self.settings_type == 'global':
            def _apply(settings: Dict[str, Any]) -> Dict[str, Any]:
                settings[key] = value
                return settings
            update_global_settings(_apply)
        else:
            with _settings_cache_lock:
                # Read from live cache directly (not a copy) to avoid lost-update race
                cache = _user_settings_cache
                # If cache is empty, load it first (load_fn acquires lock, OK with RLock)
                if cache is None:
                    cache = self._load_fn()
                settings = dict(cache)  # shallow copy for save
                settings[key] = value
                # Save without re-acquiring the lock
                _save_settings_unlocked(self.settings_type, settings)
        if verbose:
            logger.info(f"Set {key} to: {value}")
        # network_output_path has a sibling cache in core.logging_utils for
        # early-startup access; flush it whenever the value changes.
        if key == "network_output_path":
            try:
                from core.logging_utils import clear_path_cache
                clear_path_cache()
            except Exception:
                pass


_global_settings = SettingsAccessor('global')
_user_settings = SettingsAccessor('user')


_SENTINEL = object()


def get_setting(name: str, default: Any = _SENTINEL) -> Any:
    """Get any registered setting by name.

    Args:
        name: Setting key (must be in SETTINGS_REGISTRY unless default is provided)
        default: Fallback value for unregistered keys (suppresses KeyError)

    Raises:
        KeyError: If name is not in SETTINGS_REGISTRY and no default provided
    """
    defn = SETTINGS_REGISTRY.get(name)
    if not defn:
        if default is not _SENTINEL:
            return default
        raise KeyError(f"Unknown setting: {name}")
    accessor = _global_settings if defn.scope == "global" else _user_settings
    return accessor.get(defn.key, defn.default)


def set_setting(name: str, value: Any, verbose: bool = True):
    """Set any registered setting by name."""
    defn = SETTINGS_REGISTRY.get(name)
    if not defn:
        raise KeyError(f"Unknown setting: {name}")
    if defn.validator:
        value = defn.validator(value)
    accessor = _global_settings if defn.scope == "global" else _user_settings
    accessor.set(defn.key, value, verbose=verbose)


def set_settings(updates: Dict[str, Any], verbose: bool = False):
    """Set multiple registered settings with ONE file write per scope.

    Prefer this over calling set_setting() in a loop — each set_setting()
    does a full load-modify-save of the backing JSON (a network file for
    global scope), so N calls means N sequential network writes.

    Args:
        updates: {setting_name: value} — all names must be in SETTINGS_REGISTRY
        verbose: log the changed keys

    Raises:
        KeyError: If any name is not in SETTINGS_REGISTRY (nothing is written)
    """
    by_scope: Dict[str, Dict[str, Any]] = {"global": {}, "user": {}}
    for name, value in updates.items():
        defn = SETTINGS_REGISTRY.get(name)
        if not defn:
            raise KeyError(f"Unknown setting: {name}")
        if defn.validator:
            value = defn.validator(value)
        by_scope[defn.scope][defn.key] = value

    if by_scope["user"]:
        with _settings_cache_lock:
            cache = _user_settings_cache
            if cache is None:
                cache = load_user_settings()
            settings = dict(cache)
            settings.update(by_scope["user"])
            _save_settings_unlocked('user', settings)

    if by_scope["global"]:
        def _apply(settings: Dict[str, Any]) -> Dict[str, Any]:
            settings.update(by_scope["global"])
            return settings
        update_global_settings(_apply)

    if verbose:
        logger.info(f"Set {len(updates)} settings: {sorted(updates.keys())}")

    if "network_output_path" in by_scope["global"]:
        try:
            from core.logging_utils import clear_path_cache
            clear_path_cache()
        except Exception:
            pass


def safe_get_setting(name: str, default: Any = _SENTINEL) -> Any:
    """
    Get a setting with a guaranteed default if not found.

    Unlike get_setting(), this never raises KeyError. Use when reading
    settings that may not exist in older configurations or are optional.

    Args:
        name: Setting key (may or may not be in SETTINGS_REGISTRY)
        default: Fallback value if setting not found (default: registry default or None)

    Returns:
        Setting value or default

    Example:
        # These are equivalent:
        try:
            value = get_setting("my_setting")
        except KeyError:
            value = False

        value = safe_get_setting("my_setting", False)
    """
    defn = SETTINGS_REGISTRY.get(name)
    if not defn:
        return default if default is not _SENTINEL else None
    accessor = _global_settings if defn.scope == "global" else _user_settings
    return accessor.get(defn.key, defn.default if default is _SENTINEL else default)


def safe_set_setting(name: str, value: Any, verbose: bool = False) -> bool:
    """
    Set a setting without raising errors.

    Unlike set_setting(), this catches exceptions and returns success status.
    The verbose parameter defaults to False for cleaner logs.

    Args:
        name: Setting key
        value: Value to set
        verbose: Whether to log the change (default: False)

    Returns:
        True if setting was saved successfully, False otherwise
    """
    try:
        set_setting(name, value, verbose=verbose)
        return True
    except Exception as e:
        logger.warning(f"Could not save setting {name}: {e}")
        return False


# ============================================================================
# HDRI LIST MANAGEMENT
# ============================================================================

def get_hdri_list() -> List[Dict[str, str]]:
    """Get list of available HDRIs from global settings.

    Returns:
        List of dicts with keys: name, path
    """
    return load_global_settings().get("hdri_list", [])


def add_hdri_to_list(name: str, path: str):
    """Add an HDRI to the global list. Cross-process-safe read-modify-write."""
    def _apply(settings):
        hdri_list = settings.get("hdri_list", [])
        for hdri in hdri_list:
            if hdri.get("name") == name:
                return None  # Already exists — no write
        settings["hdri_list"] = hdri_list + [{"name": name, "path": path}]
        return settings
    if update_global_settings(_apply) is not None:
        logger.info(f"Added HDRI to global settings: {name}")


def remove_hdri_from_list(name: str):
    """Remove an HDRI from the global list. Cross-process-safe read-modify-write."""
    def _apply(settings):
        hdri_list = settings.get("hdri_list", [])
        filtered = [h for h in hdri_list if h.get("name") != name]
        if len(filtered) == len(hdri_list):
            return None  # Nothing to remove — no write
        settings["hdri_list"] = filtered
        return settings
    if update_global_settings(_apply) is not None:
        logger.info(f"Removed HDRI from global settings: {name}")


# ============================================================================
# USER ROLE MANAGEMENT (Global)
# Admins: Full access (all tabs including Settings)
# ============================================================================

# Role-based settings keys mapping
_ROLE_SETTINGS_KEYS = {
    "admin": "admin_users",
}


def _get_role_settings_key(role: str) -> str:
    """Get the settings key for a role."""
    if role not in _ROLE_SETTINGS_KEYS:
        raise ValueError(f"Unknown role: {role}. Valid roles: {list(_ROLE_SETTINGS_KEYS.keys())}")
    return _ROLE_SETTINGS_KEYS[role]


def get_users_with_role(role: str) -> List[str]:
    """Get the list of users with a specific role.

    Args:
        role: Role name ("admin")

    Returns:
        List of usernames with the role
    """
    return _global_settings.get(_get_role_settings_key(role), [])


def is_user_in_role(username: str, role: str) -> bool:
    """Check if a username has a specific role (case-insensitive).

    Args:
        username: Username to check
        role: Role name ("admin")

    Returns:
        True if user has the role
    """
    if not username:
        return False
    return any(u.lower() == username.lower() for u in get_users_with_role(role))


def _refresh_role_cache():
    """Best-effort: clear the cached admin status on app_state so the next
    is_admin / has_elevated_access read picks up the new role list."""
    try:
        from core.state_manager import app_state
        app_state.refresh_admin_status()
    except Exception:
        pass


def add_user_to_role(username: str, role: str):
    """Add a user to a role. Atomic load-modify-save.

    Stores the username in lowercase form so future reads/removes are
    consistent regardless of the input casing.
    """
    if not username:
        return
    username = username.lower()
    settings_key = _get_role_settings_key(role)

    def _apply(settings):
        users = settings.get(settings_key, [])
        if username in [u.lower() for u in users]:
            return None  # Already present — no write
        settings[settings_key] = users + [username]
        return settings

    update_global_settings(_apply)
    logger.info(f"Added {role} user: {username}")
    _refresh_role_cache()


def remove_user_from_role(username: str, role: str):
    """Remove a user from a role. Cross-process-safe read-modify-write."""
    settings_key = _get_role_settings_key(role)

    def _apply(settings):
        users = settings.get(settings_key, [])
        filtered = [u for u in users if u.lower() != username.lower()]
        if len(filtered) == len(users):
            return None  # Not present — no write
        settings[settings_key] = filtered
        return settings

    update_global_settings(_apply)
    logger.info(f"Removed {role} user: {username}")
    _refresh_role_cache()
