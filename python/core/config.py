"""
Configuration settings for Luma Tools.

All tool paths, defaults, and constants in one place.
Supports standalone mode when AYON environment is not available.
"""

import os
import glob
import logging
import shutil
import threading

logger = logging.getLogger(__name__)

# ============================================================================
# BASE PATHS
# ============================================================================

# Get the directory where this config file is located (python/core/)
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the python directory (parent of core/)
_PYTHON_DIR = os.path.dirname(_CONFIG_DIR)
# Get the root directory of luma_tools (parent of python/)
_ROOT_DIR = os.path.dirname(_PYTHON_DIR)

# ============================================================================
# DEFAULT PATHS (used when environment variables are not set)
# ============================================================================

def _get_default_ayon_dir():
    """Get default AYON launcher directory based on OS."""
    # Windows: C:\Users\<username>\AppData\Local\Ynput\AYON
    # Linux: ~/.local/share/Ynput/AYON
    # macOS: ~/Library/Application Support/Ynput/AYON
    if os.name == 'nt':  # Windows
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
        return os.path.join(local_app_data, "Ynput", "AYON")
    elif os.name == 'posix':
        if os.path.exists("/Library"):  # macOS
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Ynput", "AYON")
        else:  # Linux
            return os.path.join(os.path.expanduser("~"), ".local", "share", "Ynput", "AYON")
    return None

def _get_default_deadline_dir():
    """Get default Deadline directory based on OS."""
    # Windows: C:\Program Files\Thinkbox\Deadline10\bin
    # Linux/macOS: /opt/Thinkbox/Deadline10/bin
    if os.name == 'nt':
        return r"C:\Program Files\Thinkbox\Deadline10\bin"
    else:
        return "/opt/Thinkbox/Deadline10/bin"

# GET ENV VARS with fallback to defaults
_AYON_DIR_ENV = os.environ.get("AYON_LAUNCHER_LOCAL_DIR")
_AYON_DIR_DEFAULT = _get_default_ayon_dir()
_AYON_DIR = _AYON_DIR_ENV if _AYON_DIR_ENV else (_AYON_DIR_DEFAULT if _AYON_DIR_DEFAULT and os.path.exists(_AYON_DIR_DEFAULT) else None)

_DEADLINE_DIR_ENV = os.environ.get("DEADLINE_PATH")
_DEADLINE_DIR_DEFAULT = _get_default_deadline_dir()
_DEADLINE_DIR = _DEADLINE_DIR_ENV if _DEADLINE_DIR_ENV else (_DEADLINE_DIR_DEFAULT if os.path.exists(_DEADLINE_DIR_DEFAULT) else None)

# Flag to indicate if AYON environment is available (from env var or default path)
AYON_ENV_AVAILABLE = _AYON_DIR is not None


def get_ocio_config():
    """Get OCIO config path from environment."""
    ocio_root = os.environ.get("BUILTIN_OCIO_ROOT")
    if not ocio_root:
        return None
    OCIO_SEARCHPATH = os.path.join(ocio_root, "aces_2.0", "*.ocio")
    matches = glob.glob(OCIO_SEARCHPATH)
    return matches[0] if matches else None


_cached_bundle_name = None
_bundle_lock = threading.RLock()


def get_ayon_bundle():
    """Get AYON bundle name from environment or API.

    Priority:
    1. AYON_BUNDLE_NAME env var (set by AYON launcher or our own publish env)
    2. Query AYON server API for the current production bundle
    3. Fall back to "production" (last resort)

    The result is cached after the first successful API resolution so we
    don't call /api/bundles on every publish or settings read.
    Thread-safe: concurrent callers won't race on the cache write.
    """
    global _cached_bundle_name

    # Env var set by AYON launcher or our own publish subprocess
    env_bundle = os.environ.get("AYON_BUNDLE_NAME")
    if env_bundle:
        logger.debug("AYON bundle from AYON_BUNDLE_NAME env var: %s", env_bundle)
        return env_bundle

    # Resolve from AYON server API (serialize concurrent callers)
    with _bundle_lock:
        # Check under lock for thread safety
        if _cached_bundle_name:
            return _cached_bundle_name

        try:
            import ayon_api
            if not ayon_api.is_connection_created():
                ayon_api.create_connection()
            bundles_info = ayon_api.get_bundles()
            production_bundle = bundles_info.get("productionBundle")
            if production_bundle:
                _cached_bundle_name = production_bundle
                logger.info("Resolved AYON bundle from API: %s", production_bundle)
                return production_bundle
            logger.warning("API returned no productionBundle")
        except Exception as e:
            logger.warning("Could not resolve AYON bundle from API: %s", e)

    return "production"


def _safe_glob(pattern):
    """Safely glob a pattern, returning None if no matches or pattern is invalid."""
    if pattern is None:
        return None
    try:
        matches = glob.glob(pattern)
        return matches[0] if matches else None
    except Exception:
        return None


def _get_cached_tool_path(setting_key: str) -> str:
    """Get a cached tool path from user settings (for standalone fallback).

    Uses lazy import to avoid circular dependency with settings_manager.

    Args:
        setting_key: The setting key (e.g., "cached_oiio_path")

    Returns:
        The cached path if it exists and is valid, otherwise None
    """
    try:
        from .settings_manager import safe_get_setting
        cached = safe_get_setting(setting_key, "")
        if cached and os.path.isfile(cached):
            return cached
    except Exception:
        pass
    return None


# ============================================================================
# TOOL PATHS (may be None in standalone mode)
# ============================================================================

if _AYON_DIR:
    _oiio_root = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "oiio_*", "bin", "oiiotool*")
    OIIO_PATH = _safe_glob(_oiio_root)

    _oiio_info_root = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "oiio_*", "bin", "iinfo*")
    OIIO_INFO_PATH = _safe_glob(_oiio_info_root)

    _ffmpeg_root = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "ffmpeg_*", "bin", "ffmpeg*")
    FFMPEG_PATH = _safe_glob(_ffmpeg_root)

    _ayon_console_root = os.path.join(_AYON_DIR, "app", "AYON*", "ayon_console*")
    AYON_CONSOLE = _safe_glob(_ayon_console_root)
else:
    # Standalone mode - try to find tools via PATH, then fall back to cached paths
    OIIO_PATH = shutil.which("oiiotool") or _get_cached_tool_path("cached_oiio_path")
    OIIO_INFO_PATH = shutil.which("iinfo") or _get_cached_tool_path("cached_oiio_info_path")
    FFMPEG_PATH = shutil.which("ffmpeg") or _get_cached_tool_path("cached_ffmpeg_path")
    AYON_CONSOLE = None

# Deadline - try both AYON path and system PATH
DEADLINE_PATH = shutil.which("deadlinecommand", path=_DEADLINE_DIR) if _DEADLINE_DIR else shutil.which("deadlinecommand")

# MP4 burn-in font. First existing path in the list wins; None means "no font".
# Override globally by editing the list below — the mp4_maker uses the first hit.
_MP4_BURN_IN_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/Library/Fonts/Arial.ttf",
)
MP4_BURN_IN_FONT = next((p for p in _MP4_BURN_IN_FONT_CANDIDATES if os.path.isfile(p)), None)


def cache_tool_paths():
    """Cache working tool paths to user settings for standalone mode fallback.

    Call this during app startup when paths are successfully discovered.
    Only caches paths that are valid and exist.
    """
    try:
        from .settings_manager import safe_get_setting, safe_set_setting

        paths_to_cache = [
            ("cached_oiio_path", OIIO_PATH),
            ("cached_oiio_info_path", OIIO_INFO_PATH),
            ("cached_ffmpeg_path", FFMPEG_PATH),
        ]

        for setting_key, current_path in paths_to_cache:
            if current_path and os.path.isfile(current_path):
                # Only update if path changed
                cached = safe_get_setting(setting_key, "")
                if cached != current_path:
                    safe_set_setting(setting_key, current_path)
    except Exception:
        pass  # Silently fail during early startup


# UI paths (relative to luma_tools root directory)
UI_FILE_PATH = os.path.join(_ROOT_DIR, "resources", "ui", "main_window.ui")
UI_TABS_DIR = os.path.join(_ROOT_DIR, "resources", "ui", "tabs")
# qdarkstyle is no longer used. The application owns its entire stylesheet;
# layering on top of qdarkstyle is what forced 84 !important declarations.
CUSTOM_STYLE_PATH = os.path.join(_ROOT_DIR, "resources", "ui", "la_shot_tools_styles.qss")
ICON_PATH = os.path.join(_ROOT_DIR, "resources", "logo_White_small_filled.png")

# ============================================================================
# DEADLINE DEFAULTS
# ============================================================================

DEADLINE_POOL = "luma"
DEADLINE_GROUP = "processing_group"
DEADLINE_PRIORITY_BUILD = 25
DEADLINE_PRIORITY_PUBLISH = 50
DEADLINE_DEPARTMENT = "compositing"
DEADLINE_CHUNK_SIZE = 1

DEADLINE_GROUP_COMFYUI = "temp_compute"
DEADLINE_PRIORITY_COMFYUI = 50
DEADLINE_JOB_NAME_PREFIX = "LUMA TOOLS - "
# Diagnostic jobs (e.g. the ComfyUI farm path check) are identifiable on the
# farm but must NOT be mistaken for generation jobs: crash recovery scans by
# job name, and adopting a probe makes the ComfyUI tab track a job that never
# produces renders. See deadline.poller.is_recoverable_luma_job.
DEADLINE_JOB_NAME_PREFIX_DIAGNOSTIC = "LUMA TOOLS DIAG - "
# The persistent ComfyUI server runs as a long-lived Deadline job. Like the
# diagnostic prefix above it must stay out of crash recovery - a server is not
# a generation job and never produces renders.
DEADLINE_JOB_NAME_PREFIX_SERVER = "LUMA TOOLS SERVER - "

# ============================================================================
# AYON SETTINGS
# ============================================================================

AYON_PRODUCT_TYPE = "render"
AYON_FAMILY = "render"
AYON_COLORSPACE = "ACES - ACEScg"
AYON_DISPLAY = "ACES"
AYON_VIEW = "sRGB"
AYON_DEFAULT_FPS = 25.0

# Default resolution (can be overridden)
AYON_DEFAULT_WIDTH = 1920
AYON_DEFAULT_HEIGHT = 1080

# ============================================================================
# APPLICATION SETTINGS
# ============================================================================

APP_ID = u'luma.tools.shotbuilder.001'
APP_TITLE = "Luma Tools"

# Dev mode detection - check if running from _dev directory
IS_DEV_MODE = "_dev" in _ROOT_DIR.lower()

# Load version from resources/version.json
def _load_version():
    """Load version from resources/version.json."""
    from .utils import load_json
    version_file = os.path.join(_ROOT_DIR, "resources", "version.json")
    data = load_json(version_file, {"version": "unknown"})
    return data.get("version", "unknown")

APP_VERSION = _load_version()


def get_changelog():
    """Get the changelog content from resources/changelog.md."""
    changelog_file = os.path.join(_ROOT_DIR, "resources", "changelog.md")
    try:
        with open(changelog_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return "No changelog available."


def get_latest_changelog():
    """Get only the latest version entry from the changelog.

    Returns the title and first version section (up to but not including the next ## Version).
    """
    full_changelog = get_changelog()
    if full_changelog == "No changelog available.":
        return full_changelog

    lines = full_changelog.split('\n')
    result_lines = []
    found_first_version = False

    for line in lines:
        # Check if this is a version header (## Version X.X.X)
        if line.startswith('## Version '):
            if found_first_version:
                # We've hit the second version, stop here
                break
            found_first_version = True
        result_lines.append(line)

    return '\n'.join(result_lines).strip()


# Frame padding
FRAME_PADDING = 4
FRAME_PADDING_FORMAT = f"%0{FRAME_PADDING}d"

# ============================================================================
# FILE PATTERNS
# ============================================================================

# Directory structure expectations (relative to task directory)
RENDERS_SUBPATH = os.path.join("img", "renders")
# Where USD caches live under a task directory, in priority order. Shots write
# them to render/usd (<task>/render/usd/<version>/...); "usd_files" is the
# older convention and is kept so shots using it still scan and clean.
# Resolve with services.file_operations.resolve_usd_directory() rather than
# joining one of these directly — the scan and the cleanup MUST agree on the
# same directory, or Shot Cleaner would delete from a path it never listed.
USD_SUBPATHS = (os.path.join("render", "usd"), r"usd_files")
USD_SUBPATH = USD_SUBPATHS[0]
DEFAULT_TASK = "lookdev"

# File extensions
COMP_EXTENSIONS = [".nk", ".comp"]
HIP_EXTENSION = ".hip"
EXR_EXTENSION = ".exr"
# =====================================================================
# Single source of truth for media file extensions.
# All other modules MUST import from here rather than redeclare locally —
# we lost data ('.webm' missing from one publisher) the last time these
# drifted. Add a new format here and it's available everywhere.
# =====================================================================

# Image formats Luma Tools understands across the gallery, viewers,
# drag-drop, ComfyUI inputs/outputs, and AYON publishing.
IMAGE_EXTENSIONS = frozenset({
    '.png', '.jpg', '.jpeg', '.webp',
    '.exr', '.hdr', '.dpx',
    '.tiff', '.tif', '.bmp', '.gif', '.tga',
})

# Video formats accepted by viewers, drag-drop, and ComfyUI outputs.
VIDEO_EXTENSIONS = frozenset({
    '.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.wmv', '.m4v',
})

# Audio formats accepted by viewers and ComfyUI outputs.
AUDIO_EXTENSIONS = frozenset({
    '.wav', '.mp3', '.flac', '.ogg',
})

# 3D model formats (gallery thumbnails, viewer, ComfyUI 3D widgets, AYON).
MODEL_EXTENSIONS = frozenset({
    '.glb', '.gltf', '.fbx', '.obj',
    '.usd', '.usda', '.usdc', '.usdz',
    '.dae', '.stl', '.ply',
})

# Other data formats ComfyUI workflows may emit.
COMFYUI_DATA_EXTENSIONS = frozenset({
    '.npy', '.npz', '.safetensors', '.pt', '.pth', '.ckpt', '.bin',
})

# Backwards-compatible aliases — names used throughout the codebase.
GALLERY_IMAGE_EXTENSIONS = IMAGE_EXTENSIONS
GALLERY_VIDEO_EXTENSIONS = VIDEO_EXTENSIONS
GALLERY_AUDIO_EXTENSIONS = AUDIO_EXTENSIONS
GALLERY_MODEL_EXTENSIONS = MODEL_EXTENSIONS
GALLERY_SUPPORTED_EXTENSIONS = (
    IMAGE_EXTENSIONS | MODEL_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
)

# ComfyUI input formats (what the user can feed into a workflow).
COMFYUI_SUPPORTED_EXTENSIONS = sorted(IMAGE_EXTENSIONS)

# ComfyUI output formats (what a workflow can produce).
COMFYUI_OUTPUT_EXTENSIONS = sorted(
    IMAGE_EXTENSIONS | MODEL_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | COMFYUI_DATA_EXTENSIONS
)

# File naming patterns
DENOISED_SUBDIRECTORY = "denoised"

# ============================================================================
# CHANNEL FILTERING
# ============================================================================

# Channels to exclude from pass detection
EXCLUDED_CHANNELS = ["variance", "var", "Ci", "beauty", "a.Z"]

# Special channel mappings
NORMAL_CHANNELS = ["normal.x", "normal.y", "normal.z"]

# ============================================================================
# DEFAULT PASSES
# ============================================================================

# Always-included passes (user cannot deselect these)
REQUIRED_PASSES = ["Beauty", "a"]

# Default additional passes (user can customize this list in settings)
DEFAULT_PASSES = ["CryptoMaterials", "P", "depth", "uv", "normal"]

# ============================================================================
# USER SETTINGS
# ============================================================================

# User settings file location (in user's home directory)
USER_SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".luma_tools")
USER_SETTINGS_FILE = os.path.join(USER_SETTINGS_DIR, "settings.json")

# Default fallback directories
DEFAULT_VIDEOS_DIR = os.path.join(os.path.expanduser("~"), "Videos")

# Global settings (shared across all users)
# Default global settings path - relative to luma_tools root, can be overridden by user settings
DEFAULT_GLOBAL_SETTINGS_PATH = os.path.join(_ROOT_DIR, "global_settings")
GLOBAL_SETTINGS_FILENAME = "global_settings.json"


# ============================================================================
# UI STYLING CONSTANTS
# ============================================================================
# Common colors used throughout the application UI.
# Use core.design_tokens directly in new code; UIColors is an alias layer.

from core.design_tokens import (
    Color as _Color,
    Font as _Font,
    Radius as _Radius,
    Size as _Size,
    Space as _Space,
)


class UIColors:
    """Common UI color constants — an alias layer over core.design_tokens.

    DEPRECATED. design_tokens.Color is the single source of truth; these names
    are kept so existing ``from core.config import UIColors`` imports keep
    working while call sites migrate. Do not add new names here.

    Several of these are now synonyms that used to be distinct values (the old
    palette drew no consistent line between, say, BG_LIGHT and BG_LIGHT_ALT).
    Collapsing them is the point — the drift they encoded is the bug.
    """

    # Backgrounds
    BG_DARK = _Color.PAGE
    BG_DARK_ALT = _Color.PAGE
    BG_MEDIUM = _Color.PANEL
    BG_MEDIUM_ALT = _Color.PANEL
    BG_LIGHT = _Color.PANEL_ALT
    BG_LIGHT_ALT = _Color.BORDER_STRONG
    BG_HOVER = _Color.HOVER

    # Text colors
    TEXT_WHITE = "#ffffff"
    TEXT_LIGHT = _Color.TEXT
    TEXT_SECONDARY = _Color.TEXT_SECONDARY
    TEXT_MUTED = _Color.TEXT_MUTED
    TEXT_DARK_MUTED = _Color.DISABLED_TEXT

    # Accent colors
    ACCENT_BLUE = _Color.ACCENT
    ACCENT_BLUE_HOVER = _Color.ACCENT_HOVER
    ACCENT_BLUE_ALT = _Color.ACCENT_HOVER

    # AYON brand colors
    AYON_GREEN = _Color.AYON
    AYON_GREEN_HOVER = _Color.AYON_HOVER
    AYON_GREEN_DARK = _Color.AYON_PRESSED

    # Status colors
    SUCCESS = _Color.SUCCESS
    SUCCESS_HOVER = _Color.SUCCESS
    ERROR = _Color.DANGER
    ERROR_ALT = _Color.DANGER_HOVER
    WARNING = _Color.WARNING
    WARNING_DARK = _Color.WARNING
    INFO = _Color.INFO
    SCANNING = _Color.SCANNING

    # Border colors
    BORDER = _Color.BORDER
    BORDER_FOCUS = _Color.BORDER_FOCUS

    # Group colors palette (for gallery groups) — data, not chrome
    GROUP_COLORS = _Color.GROUP_COLORS


class UIStyles:
    """Common stylesheet snippets — an alias layer over core.design_tokens.

    DEPRECATED. Prefer the component contract: set a dynamic property and let
    the stylesheet do the work::

        set_role(button, role="primary")     rather than the BUTTON_PRIMARY snippet
        set_role(label, textRole="help")     rather than the LABEL_MUTED snippet

    These are retained only so existing call sites keep rendering correctly
    until they are migrated. Do not add new snippets here.
    """

    # Label styles — prefer QLabel[text="..."]
    LABEL_LIGHT = f"color: {_Color.TEXT};"
    LABEL_MUTED = f"color: {_Color.TEXT_MUTED};"
    LABEL_SECONDARY = f"color: {_Color.TEXT_SECONDARY};"
    LABEL_ITALIC_MUTED = f"color: {_Color.TEXT_MUTED}; font-style: italic;"
    LABEL_SMALL_MUTED = f"color: {_Color.TEXT_MUTED}; font-size: {_Font.HELP}px;"
    LABEL_PATH = (f"color: {_Color.TEXT_SECONDARY}; "
                  f"font-family: {_Font.MONO_FAMILY}; font-size: {_Font.HELP}px;")

    # Button styles — prefer QPushButton[role="..."]
    BUTTON_PRIMARY = f"""
        QPushButton {{
            background-color: {_Color.ACCENT};
            color: {_Color.TEXT_ON_ACCENT};
            border: none;
            border-radius: {_Radius.SM}px;
            padding: 0px {_Space.LG}px;
            min-height: {_Size.CONTROL}px;
            font-weight: {_Font.WEIGHT_SEMIBOLD};
        }}
        QPushButton:hover {{ background-color: {_Color.ACCENT_HOVER}; }}
        QPushButton:pressed {{ background-color: {_Color.ACCENT_PRESSED}; }}
        QPushButton:disabled {{
            background-color: {_Color.DISABLED_BG};
            color: {_Color.DISABLED_TEXT};
        }}
    """

    BUTTON_SUCCESS = f"""
        QPushButton {{
            background-color: {_Color.AYON};
            color: {_Color.TEXT_ON_ACCENT};
            border: none;
            border-radius: {_Radius.SM}px;
            padding: 0px {_Space.LG}px;
            min-height: {_Size.CONTROL}px;
            font-weight: {_Font.WEIGHT_SEMIBOLD};
        }}
        QPushButton:hover {{ background-color: {_Color.AYON_HOVER}; }}
        QPushButton:disabled {{
            background-color: {_Color.DISABLED_BG};
            color: {_Color.DISABLED_TEXT};
        }}
    """

    BUTTON_SECONDARY = f"""
        QPushButton {{
            background-color: {_Color.PANEL_ALT};
            color: {_Color.TEXT};
            border: none;
            border-radius: {_Radius.SM}px;
            padding: 0px {_Space.LG}px;
            min-height: {_Size.CONTROL}px;
        }}
        QPushButton:hover {{ background-color: {_Color.HOVER}; }}
        QPushButton:pressed {{ background-color: {_Color.SELECTED}; }}
        QPushButton:checked {{
            background-color: {_Color.ACCENT_SUBTLE};
            color: {_Color.ACCENT};
        }}
        QPushButton:disabled {{
            background-color: {_Color.DISABLED_BG};
            color: {_Color.DISABLED_TEXT};
        }}
    """

    BUTTON_DANGER = f"""
        QPushButton {{
            background-color: {_Color.DANGER};
            color: {_Color.TEXT_ON_DANGER};
            border: none;
            border-radius: {_Radius.SM}px;
            padding: 0px {_Space.LG}px;
            min-height: {_Size.CONTROL}px;
            font-weight: {_Font.WEIGHT_SEMIBOLD};
        }}
        QPushButton:hover {{ background-color: {_Color.DANGER_HOVER}; }}
    """

    SCROLL_AREA = """
        QScrollArea {
            background-color: transparent;
            border: none;
        }
    """

    COMBOBOX = f"""
        QComboBox {{
            background-color: {_Color.SUNKEN};
            color: {_Color.TEXT};
            border: 1px solid {_Color.BORDER};
            border-radius: {_Radius.SM}px;
            padding: 0px {_Space.SM}px;
            min-height: {_Size.CONTROL}px;
        }}
        QComboBox:hover {{ border-color: {_Color.BORDER_STRONG}; }}
    """

    DIALOG = f"""
        QDialog {{ background-color: {_Color.PAGE}; }}
        QLabel {{ color: {_Color.TEXT}; }}
    """


# ============================================================================
# SETTINGS ACCESSOR FUNCTIONS
# ============================================================================
# Typed accessor functions for commonly-used settings.
# Use these instead of repeated get_setting() calls to reduce boilerplate.


