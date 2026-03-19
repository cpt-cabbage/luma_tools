"""
Tab modules for Luma Tools.

Each tab is a separate module that handles its own UI and signal connections.
Tab classes are imported lazily during window creation, not at import time,
to speed up application startup.
"""

from .base_tab import BaseTab, TabSignals

__all__ = [
    'BaseTab',
    'TabSignals',
    'TAB_REGISTRY',
]

# Tab registry: (relative_module, class_name, restrict_key)
# Tab modules are NOT imported here — they're loaded on demand in _load_tabs()
# Order determines default tab order in the UI
TAB_REGISTRY = [
    ('.comfyui', 'ComfyUITab', 'comfyui'),
    ('.gallery_tab', 'GalleryTab', 'gallery'),
    ('.canvas_tab', 'CanvasTab', 'canvas'),
    ('.pass_builder_tab', 'PassBuilderTab', 'passbuilder'),
    ('.republish_tab', 'RePublishTab', 'republish'),
    ('.mp4_maker_tab', 'MP4MakerTab', 'mp4maker'),
    ('.cleaner_tab', 'CleanerTab', 'cleaner'),
    ('.settings_tab', 'SettingsTab', 'settings'),
    ('.logs_tab', 'LogsTab', 'logs'),
]
