"""
Configuration settings for Luma Tools.

All tool paths, defaults, and constants in one place.
Supports standalone mode when AYON environment is not available.
"""

import os
import glob
import shutil

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


def get_ayon_bundle():
    """Get AYON bundle name from environment or API.

    Priority:
    1. AYON_DEFAULT_SETTINGS_VARIANT env var (set by AYON launcher)
    2. AYON_BUNDLE_NAME env var (set by some AYON configurations)
    3. Query AYON server API for the current production bundle
    4. Fall back to "production"
    """
    env_bundle = (
        os.environ.get("AYON_DEFAULT_SETTINGS_VARIANT")
        or os.environ.get("AYON_BUNDLE_NAME")
    )
    if env_bundle:
        return env_bundle

    try:
        import ayon_api
        if not ayon_api.is_connection_created():
            ayon_api.create_connection()
        bundles_info = ayon_api.get_bundles()
        production_bundle = bundles_info.get("productionBundle")
        if production_bundle:
            return production_bundle
    except Exception:
        pass

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
    OIIO_ROOT = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "oiio_*", "bin", "oiiotool*")
    OIIO_PATH = _safe_glob(OIIO_ROOT)

    OIIO_INFO_ROOT = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "oiio_*", "bin", "iinfo*")
    OIIO_INFO_PATH = _safe_glob(OIIO_INFO_ROOT)

    FFMPEG_ROOT = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "ffmpeg_*", "bin", "ffmpeg*")
    FFMPEG_PATH = _safe_glob(FFMPEG_ROOT)

    AYON_CONSOLE_ROOT = os.path.join(_AYON_DIR, "app", "AYON*", "ayon_console*")
    AYON_CONSOLE = _safe_glob(AYON_CONSOLE_ROOT)
else:
    # Standalone mode - try to find tools via PATH, then fall back to cached paths
    OIIO_ROOT = None
    OIIO_PATH = shutil.which("oiiotool") or _get_cached_tool_path("cached_oiio_path")
    OIIO_INFO_ROOT = None
    OIIO_INFO_PATH = shutil.which("iinfo") or _get_cached_tool_path("cached_oiio_info_path")
    FFMPEG_ROOT = None
    FFMPEG_PATH = shutil.which("ffmpeg") or _get_cached_tool_path("cached_ffmpeg_path")
    AYON_CONSOLE_ROOT = None
    AYON_CONSOLE = None

# Deadline - try both AYON path and system PATH
DEADLINE_PATH = shutil.which("deadlinecommand", path=_DEADLINE_DIR) if _DEADLINE_DIR else shutil.which("deadlinecommand")


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
QDARKSTYLE_PATH = os.path.join(_PYTHON_DIR, "venv", "Lib", "site-packages", "qdarkstyle", "dark", "darkstyle.qss")
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

DEADLINE_GROUP_COMPFYUI = "temp_compute"
DEADLINE_PRIORITY_COMFYUI = 50

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

# ============================================================================
# FILE PATTERNS
# ============================================================================

# Directory structure expectations (relative to task directory)
RENDERS_SUBPATH = r"img\renders"
USD_SUBPATH = r"usd_files"
BACKUP_SUBPATH = r"backup"
DEFAULT_TASK = "lookdev"
COMPOSITING_SUBPATH = "Compositing"

# File extensions
COMP_EXTENSIONS = [".nk", ".comp"]
HIP_EXTENSION = ".hip"
EXR_EXTENSION = ".exr"
COMFYUI_SUPPORTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".exr", ".hdr", ".dpx", ".tga"]
# Output file extensions that ComfyUI workflows can generate (images, models, etc.)
COMFYUI_OUTPUT_EXTENSIONS = [
    # Images
    ".png", ".jpg", ".jpeg", ".webp", ".exr", ".tiff", ".tif", ".bmp", ".gif",
    # 3D/Motion files
    ".fbx", ".obj", ".gltf", ".glb", ".usd", ".usda", ".usdc", ".usdz",
    # Video/Animation
    ".mp4", ".mov", ".avi", ".webm",
    # Audio
    ".wav", ".mp3", ".flac", ".ogg",
    # Other data formats
    ".npy", ".npz", ".safetensors", ".pt", ".pth", ".ckpt", ".bin",
]

# Gallery file extension sets (used by gallery loader and prewarm)
GALLERY_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.exr', '.tiff', '.tif', '.bmp', '.gif'}
GALLERY_MODEL_EXTENSIONS = {'.glb', '.gltf', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz', '.dae'}
GALLERY_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.webm'}
GALLERY_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg'}
GALLERY_SUPPORTED_EXTENSIONS = GALLERY_IMAGE_EXTENSIONS | GALLERY_MODEL_EXTENSIONS | GALLERY_VIDEO_EXTENSIONS | GALLERY_AUDIO_EXTENSIONS

# File naming patterns
DENOISED_SUBDIRECTORY = "denoised"

# ============================================================================
# CHANNEL FILTERING
# ============================================================================

# Channels to exclude from pass detection
EXCLUDED_CHANNELS = ["variance", "var", "Ci", "beauty", "a.Z"]

# Special channel mappings
NORMAL_CHANNELS = [" normal.x", " normal.y", " normal.z"]

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
# Use these constants instead of hardcoding hex colors.

class UIColors:
    """Common UI color constants for consistent styling."""

    # Backgrounds
    BG_DARK = "#1e1e1e"
    BG_DARK_ALT = "#1e1e22"  # Slight blue tint
    BG_MEDIUM = "#2a2a2a"
    BG_MEDIUM_ALT = "#2a2e36"  # Slight blue tint
    BG_LIGHT = "#3c3c3c"
    BG_LIGHT_ALT = "#3c414b"  # For buttons, borders
    BG_HOVER = "#4a5160"

    # Text colors
    TEXT_WHITE = "#ffffff"
    TEXT_LIGHT = "#e0e0e0"
    TEXT_SECONDARY = "#aaaaaa"
    TEXT_MUTED = "#888888"
    TEXT_DARK_MUTED = "#666666"

    # Accent colors
    ACCENT_BLUE = "#4a9eff"
    ACCENT_BLUE_HOVER = "#5aa9ff"
    ACCENT_BLUE_ALT = "#6ab0ff"

    # Status colors
    SUCCESS = "#10b981"
    SUCCESS_HOVER = "#14ce94"
    ERROR = "#ef4444"
    ERROR_ALT = "#ff6b6b"
    WARNING = "#f59e0b"
    WARNING_DARK = "#d97706"
    INFO = "#4a9eff"
    SCANNING = "#8b5cf6"

    # Border colors
    BORDER = "#3c3c3c"
    BORDER_FOCUS = "#4a9eff"

    # Group colors palette (for gallery groups)
    GROUP_COLORS = [
        "#ef4444",  # Red
        "#f97316",  # Orange
        "#eab308",  # Yellow
        "#22c55e",  # Green
        "#06b6d4",  # Cyan
        "#3b82f6",  # Blue
        "#8b5cf6",  # Purple
        "#ec4899",  # Pink
    ]


class UIStyles:
    """Common stylesheet snippets for consistent styling."""

    # Label styles
    LABEL_LIGHT = "color: #e0e0e0;"
    LABEL_MUTED = "color: #888888;"
    LABEL_SECONDARY = "color: #aaaaaa;"
    LABEL_ITALIC_MUTED = "color: #888888; font-style: italic;"
    LABEL_SMALL_MUTED = "color: #888888; font-size: 11px;"
    LABEL_PATH = "color: white; font-size: 9pt;"

    # Button base styles
    BUTTON_PRIMARY = """
        QPushButton {
            background-color: #4a9eff;
            color: white;
            border: none;
            border-radius: 3px;
            padding: 5px 15px;
        }
        QPushButton:hover { background-color: #5aa9ff; }
        QPushButton:pressed { background-color: #3a8eef; }
        QPushButton:disabled { background-color: #3c414b; color: #666; }
    """

    BUTTON_SUCCESS = """
        QPushButton {
            background-color: #10b981;
            color: white;
            border: none;
            border-radius: 3px;
            padding: 5px 15px;
        }
        QPushButton:hover { background-color: #14ce94; }
        QPushButton:disabled { background-color: #3c414b; color: #6b6f78; }
    """

    BUTTON_SECONDARY = """
        QPushButton {
            background-color: #3c414b;
            color: #e0e0e0;
            border: none;
            border-radius: 3px;
            padding: 5px 15px;
        }
        QPushButton:hover { background-color: #4a5160; }
        QPushButton:pressed { background-color: #2a2e36; }
        QPushButton:checked { background-color: #4a9eff; }
        QPushButton:disabled { background-color: #2a2e36; color: #666; }
    """

    BUTTON_DANGER = """
        QPushButton {
            background-color: #ef4444;
            color: white;
            border: none;
            border-radius: 3px;
            padding: 5px 15px;
        }
        QPushButton:hover { background-color: #f87171; }
    """

    # Scroll area style
    SCROLL_AREA = """
        QScrollArea {
            background-color: #1e1e1e;
            border: 1px solid #3c3c3c;
        }
    """

    # Input/ComboBox styles
    COMBOBOX = """
        QComboBox {
            background-color: #3c414b;
            color: #e0e0e0;
            border: 1px solid #3c3c3c;
            border-radius: 3px;
            padding: 5px;
        }
        QComboBox:hover { background-color: #4a5160; }
    """

    # Dialog base style
    DIALOG = """
        QDialog { background-color: #1e1e22; }
        QLabel { color: #e0e0e0; }
    """


# ============================================================================
# SETTINGS ACCESSOR FUNCTIONS
# ============================================================================
# Typed accessor functions for commonly-used settings.
# Use these instead of repeated get_setting() calls to reduce boilerplate.

def get_network_output_path() -> str:
    """Get the ComfyUI network output path.

    Returns:
        Network path string, or empty string if not configured.
    """
    from core.settings_manager import safe_get_setting
    return safe_get_setting("network_output_path", "")


def is_mp4_add_to_gallery_enabled() -> bool:
    """Check if MP4 Maker should add outputs to gallery.

    Returns:
        True if enabled, False otherwise.
    """
    from core.settings_manager import safe_get_setting
    return safe_get_setting("mp4_maker_add_to_gallery", False)


def get_completion_sound() -> str:
    """Get the ComfyUI completion sound setting.

    Returns:
        Sound setting: 'none', 'chime', 'success', etc.
    """
    from core.settings_manager import safe_get_setting
    return safe_get_setting("comfyui_completion_sound", "none")

