"""
Configuration settings for Luma Tools.

All tool paths, defaults, and constants in one place.
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

# GET ENV VARS
_AYON_DIR = os.environ.get("AYON_LAUNCHER_LOCAL_DIR")
_DEADLINE_DIR = os.environ.get("DEADLINE_PATH") 

def get_ocio_config():
    """Get OCIO config path from environment."""
    OCIO_SEARCHPATH = os.path.join(os.environ.get("BUILTIN_OCIO_ROOT"), "aces_2.0","*.ocio")
    OIIO = glob.glob(OCIO_SEARCHPATH)[0]
    return OIIO

def get_ayon_bundle():
    """Get AYON bundle name from environment."""
    return os.environ.get("AYON_DEFAULT_SETTINGS_VARIANT", "production")

# ============================================================================
# TOOL PATHS
# ============================================================================

OIIO_ROOT = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "oiio_*", "bin", "oiiotool*")
OIIO_PATH = glob.glob(OIIO_ROOT)[0]

OIIO_INFO_ROOT = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "oiio_*", "bin", "iinfo*")
OIIO_INFO_PATH = glob.glob(OIIO_INFO_ROOT)[0]

FFMPEG_ROOT = os.path.join(_AYON_DIR, "addons_resources", "ayon_third_party", "ffmpeg_*", "bin", "ffmpeg*")
FFMPEG_PATH = glob.glob(FFMPEG_ROOT)[0]

DEADLINE_PATH = shutil.which("deadlinecommand", path=_DEADLINE_DIR)

AYON_CONSOLE_ROOT = os.path.join(_AYON_DIR, "app", "AYON*", "ayon_console*")
AYON_CONSOLE = glob.glob(AYON_CONSOLE_ROOT)[0]

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




