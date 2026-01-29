"""
Gallery management components for Gallery Tab.

This package decomposes the GalleryTab into focused manager classes:
- SelectionManager: Multi-select, box selection, shift-click range selection
- ViewerManager: Embedded viewer lifecycle, fullscreen viewing
- OperationsManager: Delete, publish, copy settings operations
- RefreshController: File watching, polling, scan management
- UIManager: Sort, filter, view mode, user selection UI

Each manager holds a reference to the parent tab and handles specific responsibilities.
"""

from .selection_manager import SelectionManager, BoxSelectionEventFilter
from .viewer_manager import ViewerManager
from .operations_manager import OperationsManager
from .refresh_controller import RefreshController
from .ui_manager import UIManager

__all__ = [
    'SelectionManager',
    'BoxSelectionEventFilter',
    'ViewerManager',
    'OperationsManager',
    'RefreshController',
    'UIManager',
]
