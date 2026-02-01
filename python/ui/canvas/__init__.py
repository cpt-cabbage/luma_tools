"""
Canvas module for collaborative infinite canvas workspace.

This module provides an infinite 2D canvas where generations live spatially,
synchronized across team members via the shared network drive.

Features:
- Infinite canvas with pixel density preservation
- Drawing tools with pen tablet support
- Non-destructive image transformations
- Grid and snapping
- Color sampler with history
"""

from .collaborative_canvas import CollaborativeCanvas
from .canvas_items import ImageNode, ConnectionLine, StickyNote, GroupRegion
from .canvas_drawing import (
    DrawingPath, DrawingRect, DrawingEllipse, DrawingLine,
    DrawingToolbar, DrawingItemBase
)
from .canvas_undo import (
    UndoStack, CanvasCommand, AddItemCommand, RemoveItemCommand,
    MoveItemCommand, TransformItemCommand, ResizeItemCommand, CompositeCommand
)
from .canvas_export import export_to_luma, import_from_luma, get_luma_info, LUMA_EXTENSION
from .sync_manager import CanvasSyncManager, CursorPresenceManager
from .minimap import CanvasMinimap
from .timeline import GenerationTimeline, TimelinePanel

__all__ = [
    'CollaborativeCanvas',
    'ImageNode',
    'ConnectionLine',
    'StickyNote',
    'GroupRegion',
    'DrawingPath',
    'DrawingRect',
    'DrawingEllipse',
    'DrawingLine',
    'DrawingToolbar',
    'DrawingItemBase',
    'UndoStack',
    'CanvasCommand',
    'AddItemCommand',
    'RemoveItemCommand',
    'MoveItemCommand',
    'TransformItemCommand',
    'ResizeItemCommand',
    'CompositeCommand',
    'CanvasSyncManager',
    'CursorPresenceManager',
    'CanvasMinimap',
    'GenerationTimeline',
    'TimelinePanel',
    'export_to_luma',
    'import_from_luma',
    'get_luma_info',
    'LUMA_EXTENSION',
]
