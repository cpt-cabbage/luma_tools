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

# Get the directory where this config file is located
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the root directory of luma_tools (parent of python/)
_ROOT_DIR = os.path.dirname(_CONFIG_DIR)

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
    """Get AYON bundle name from environment."""
    return os.environ.get("AYON_DEFAULT_SETTINGS_VARIANT", "production")


def _safe_glob(pattern):
    """Safely glob a pattern, returning None if no matches or pattern is invalid."""
    if pattern is None:
        return None
    try:
        matches = glob.glob(pattern)
        return matches[0] if matches else None
    except Exception:
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
    # Standalone mode - try to find tools via PATH or common locations
    OIIO_ROOT = None
    OIIO_PATH = shutil.which("oiiotool")
    OIIO_INFO_ROOT = None
    OIIO_INFO_PATH = shutil.which("iinfo")
    FFMPEG_ROOT = None
    FFMPEG_PATH = shutil.which("ffmpeg")
    AYON_CONSOLE_ROOT = None
    AYON_CONSOLE = None

# Deadline - try both AYON path and system PATH
DEADLINE_PATH = shutil.which("deadlinecommand", path=_DEADLINE_DIR) if _DEADLINE_DIR else shutil.which("deadlinecommand")

# UI paths (relative to luma_tools root directory)
UI_FILE_PATH = os.path.join(_ROOT_DIR, "resources", "ui", "la_shottools_ui.ui")
QDARKSTYLE_PATH = os.path.join(_CONFIG_DIR, "venv", "Lib", "site-packages", "qdarkstyle", "dark", "darkstyle.qss")
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

# Frame padding
FRAME_PADDING = 4

# ============================================================================
# FILE PATTERNS
# ============================================================================

# Directory structure expectations
LOOKDEV_SUBPATH = "lookdev"
RENDERS_SUBPATH = r"lookdev\img\renders"
USD_SUBPATH = r"lookdev\usd_files"
BACKUP_SUBPATH = r"lookdev\backup"
COMPOSITING_SUBPATH = "Compositing"

# File extensions
COMP_EXTENSIONS = [".nk", ".comp"]
HIP_EXTENSION = ".hip"
EXR_EXTENSION = ".exr"
COMFYUI_SUPPORTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".exr"]
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

# Global settings (shared across all users)
# Default global settings path - can be overridden by user settings
DEFAULT_GLOBAL_SETTINGS_PATH = r"L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools\global_settings"
GLOBAL_SETTINGS_FILENAME = "global_settings.json"




