"""
Configuration settings for Luma Tools.

All tool paths, defaults, and constants in one place.
"""

import os

# ============================================================================
# BASE PATHS
# ============================================================================

# Get the directory where this config file is located
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the root directory of luma_tools (parent of python/)
_ROOT_DIR = os.path.dirname(_CONFIG_DIR)

# ============================================================================
# TOOL PATHS
# ============================================================================

OIIO_PATH = r"L:\tools\_studio_tools\AYON\AYON-1.3.3-windows\addons_resources\ayon_third_party\oiio_windows_83e412e9\bin\oiiotool.exe"
OIIO_INFO_PATH = r"L:\tools\_studio_tools\_openpype\CURRENT\vendor\bin\oiio\windows\iinfo.exe"
FFMPEG_PATH = r"L:\tools\_studio_tools\_openpype\CURRENT\vendor\bin\ffmpeg\windows\bin\ffmpeg.exe"
DEADLINE_PATH = r"C:\Program Files\Thinkbox\Deadline10\bin\deadlinecommand.exe"

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
# ENVIRONMENT VARIABLES
# ============================================================================

def get_deadline_path():
    """Get Deadline path from environment or use default."""
    return os.getenv('DEADLINE_path', DEADLINE_PATH)

def get_ocio_config():
    """Get OCIO config path from environment."""
    return r"L:\tools\ocio\aces_1.2\config.ocio"

def get_ayon_bundle():
    """Get AYON bundle name from environment."""
    return os.environ.get("AYON_DEFAULT_SETTINGS_VARIANT", "production")
