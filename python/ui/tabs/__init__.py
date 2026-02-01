"""
Tab modules for Luma Tools.

Each tab is a separate module that handles its own UI and signal connections.
"""

from .base_tab import BaseTab, TabSignals
from .logs_tab import LogsTab
from .pass_builder_tab import PassBuilderTab
from .mp4_maker_tab import MP4MakerTab
from .republish_tab import RePublishTab
from .shot_cleaner_tab import ShotCleanerTab
from .comfyui_tab import ComfyUITab
from .gallery_tab import GalleryTab
from .canvas_tab import CanvasTab
from .settings_tab import SettingsTab

__all__ = [
    'BaseTab',
    'TabSignals',
    'LogsTab',
    'PassBuilderTab',
    'MP4MakerTab',
    'RePublishTab',
    'ShotCleanerTab',
    'ComfyUITab',
    'GalleryTab',
    'CanvasTab',
    'SettingsTab',
]

# Tab configuration for dynamic loading
# Order determines default tab order in the UI
TAB_CONFIG = [
    {'class': PassBuilderTab, 'restrict_key': 'passbuilder'},
    {'class': MP4MakerTab, 'restrict_key': 'mp4maker'},
    {'class': RePublishTab, 'restrict_key': 'republish'},
    {'class': ShotCleanerTab, 'restrict_key': 'shotcleaner'},
    {'class': LogsTab, 'restrict_key': 'logs'},
    {'class': ComfyUITab, 'restrict_key': 'comfyui'},
    {'class': GalleryTab, 'restrict_key': 'gallery'},
    {'class': CanvasTab, 'restrict_key': 'canvas'},
    {'class': SettingsTab, 'restrict_key': 'settings'},
]
