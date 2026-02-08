"""
Undo/Redo system for the collaborative canvas.

Uses the Command pattern to implement a full undo stack for all canvas operations.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, Signal, QObject

logger = logging.getLogger(__name__)


class CanvasCommand(ABC):
    """
    Abstract base class for undoable canvas commands.

    Each command must implement execute() and undo() methods.
    """

    def __init__(self, canvas: 'CollaborativeCanvas', description: str = ""):
        """
        Initialize the command.

        Args:
            canvas: The canvas to operate on
            description: Human-readable description for UI
        """
        self._canvas = canvas
        self._description = description

    @property
    def description(self) -> str:
        """Get the command description."""
        return self._description

    @abstractmethod
    def execute(self) -> bool:
        """
        Execute the command.

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def undo(self) -> bool:
        """
        Undo the command.

        Returns:
            True if successful, False otherwise
        """
        pass

    def redo(self) -> bool:
        """
        Redo the command (default: same as execute).

        Returns:
            True if successful, False otherwise
        """
        return self.execute()


class AddItemCommand(CanvasCommand):
    """Command to add an item to the canvas."""

    def __init__(self, canvas, item_type: str, item_data: dict):
        """
        Initialize add item command.

        Args:
            canvas: The canvas
            item_type: Type of item ('image', 'video', 'sticky', 'connection', 'group')
            item_data: Data needed to create the item
        """
        super().__init__(canvas, f"Add {item_type}")
        self._item_type = item_type
        self._item_data = item_data
        self._item_id: Optional[str] = None

    def execute(self) -> bool:
        try:
            if self._item_type == 'image':
                node = self._canvas.add_image(
                    self._item_data.get('path', ''),
                    x=self._item_data.get('x'),
                    y=self._item_data.get('y'),
                    width=self._item_data.get('width'),
                    height=self._item_data.get('height'),
                    liked=self._item_data.get('liked', False),
                    node_id=self._item_data.get('id')
                )
                self._item_id = self._item_data.get('id') or node.filename

            elif self._item_type == 'video':
                node = self._canvas.add_video(
                    self._item_data.get('path', ''),
                    x=self._item_data.get('x'),
                    y=self._item_data.get('y'),
                    width=self._item_data.get('width'),
                    height=self._item_data.get('height'),
                    node_id=self._item_data.get('id')
                )
                self._item_id = self._item_data.get('id') or node.filename

            elif self._item_type == 'sticky':
                note = self._canvas.add_sticky_note(
                    self._item_data.get('x', 0),
                    self._item_data.get('y', 0),
                    text=self._item_data.get('text', ''),
                    color=self._item_data.get('color', 'yellow'),
                    font_size=self._item_data.get('font_size', 10),
                    note_id=self._item_data.get('id')
                )
                self._item_id = self._item_data.get('id')

            elif self._item_type == 'connection':
                conn = self._canvas.add_connection(
                    self._item_data.get('source'),
                    self._item_data.get('target'),
                    connection_type=self._item_data.get('type', 'manual'),
                    label=self._item_data.get('label', ''),
                    connection_id=self._item_data.get('id')
                )
                self._item_id = self._item_data.get('id')

            elif self._item_type == 'group':
                group = self._canvas.add_group(
                    self._item_data.get('x', 0),
                    self._item_data.get('y', 0),
                    self._item_data.get('width', 200),
                    self._item_data.get('height', 150),
                    name=self._item_data.get('name', 'Group'),
                    color=self._item_data.get('color', '#ff6b6b'),
                    group_id=self._item_data.get('id')
                )
                self._item_id = self._item_data.get('id')

            return True
        except Exception as e:
            logger.error(f"Failed to execute add command: {e}")
            return False

    def undo(self) -> bool:
        try:
            if not self._item_id:
                return False

            if self._item_type == 'image':
                self._canvas.remove_image(self._item_id)
            elif self._item_type == 'video':
                self._canvas.remove_video(self._item_id)
            elif self._item_type == 'sticky':
                self._canvas.remove_sticky_note(self._item_id)
            elif self._item_type == 'connection':
                self._canvas.remove_connection(self._item_id)
            elif self._item_type == 'group':
                self._canvas.remove_group(self._item_id)

            return True
        except Exception as e:
            logger.error(f"Failed to undo add command: {e}")
            return False


class RemoveItemCommand(CanvasCommand):
    """Command to remove an item from the canvas."""

    def __init__(self, canvas, item_type: str, item_id: str, item_data: dict):
        """
        Initialize remove item command.

        Args:
            canvas: The canvas
            item_type: Type of item
            item_id: ID of the item
            item_data: Data needed to restore the item
        """
        super().__init__(canvas, f"Remove {item_type}")
        self._item_type = item_type
        self._item_id = item_id
        self._item_data = item_data

    def execute(self) -> bool:
        try:
            if self._item_type == 'image':
                self._canvas.remove_image(self._item_id)
            elif self._item_type == 'video':
                self._canvas.remove_video(self._item_id)
            elif self._item_type == 'sticky':
                self._canvas.remove_sticky_note(self._item_id)
            elif self._item_type == 'connection':
                self._canvas.remove_connection(self._item_id)
            elif self._item_type == 'group':
                self._canvas.remove_group(self._item_id)
            return True
        except Exception as e:
            logger.error(f"Failed to execute remove command: {e}")
            return False

    def undo(self) -> bool:
        # Re-add the item with saved data
        add_cmd = AddItemCommand(self._canvas, self._item_type, self._item_data)
        return add_cmd.execute()


class MoveItemCommand(CanvasCommand):
    """Command to move an item."""

    def __init__(self, canvas, item_id: str, old_pos: QPointF, new_pos: QPointF):
        """
        Initialize move command.

        Args:
            canvas: The canvas
            item_id: ID of the item
            old_pos: Original position
            new_pos: New position
        """
        super().__init__(canvas, "Move item")
        self._item_id = item_id
        self._old_pos = old_pos
        self._new_pos = new_pos

    def _find_node(self):
        """Find node by ID across image and video nodes."""
        node = self._canvas.get_image_node(self._item_id)
        if not node:
            node = self._canvas.get_video_node(self._item_id)
        return node

    def execute(self) -> bool:
        try:
            node = self._find_node()
            if node:
                node.setPos(self._new_pos)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to execute move command: {e}")
            return False

    def undo(self) -> bool:
        try:
            node = self._find_node()
            if node:
                node.setPos(self._old_pos)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to undo move command: {e}")
            return False


class TransformItemCommand(CanvasCommand):
    """Command for transform operations (rotate, flip, scale, opacity, crop)."""

    def __init__(self, canvas, item_id: str, old_state: dict, new_state: dict,
                 transform_type: str = "transform"):
        """
        Initialize transform command.

        Args:
            canvas: The canvas
            item_id: ID of the item
            old_state: Previous transform state
            new_state: New transform state
            transform_type: Type of transform for description
        """
        super().__init__(canvas, f"{transform_type.capitalize()} image")
        self._item_id = item_id
        self._old_state = old_state
        self._new_state = new_state

    def execute(self) -> bool:
        try:
            node = self._canvas.get_image_node(self._item_id)
            if node:
                node.set_transform_state(self._new_state)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to execute transform command: {e}")
            return False

    def undo(self) -> bool:
        try:
            node = self._canvas.get_image_node(self._item_id)
            if node:
                node.set_transform_state(self._old_state)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to undo transform command: {e}")
            return False


class ResizeItemCommand(CanvasCommand):
    """Command to resize an item."""

    def __init__(self, canvas, item_id: str, old_size: tuple, new_size: tuple):
        """
        Initialize resize command.

        Args:
            canvas: The canvas
            item_id: ID of the item
            old_size: (width, height) before resize
            new_size: (width, height) after resize
        """
        super().__init__(canvas, "Resize item")
        self._item_id = item_id
        self._old_size = old_size
        self._new_size = new_size

    def _find_node(self):
        """Find node by ID across image and video nodes."""
        node = self._canvas.get_image_node(self._item_id)
        if not node:
            node = self._canvas.get_video_node(self._item_id)
        return node

    def execute(self) -> bool:
        try:
            node = self._find_node()
            if node:
                node.set_size(self._new_size[0], self._new_size[1])
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to execute resize command: {e}")
            return False

    def undo(self) -> bool:
        try:
            node = self._find_node()
            if node:
                node.set_size(self._old_size[0], self._old_size[1])
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to undo resize command: {e}")
            return False


class AddDrawingCommand(CanvasCommand):
    """Command to add a drawing item to the canvas."""

    def __init__(self, canvas, drawing_item, drawing_id: str):
        """
        Initialize add drawing command.

        Args:
            canvas: The canvas
            drawing_item: The drawing QGraphicsItem (DrawingPath, DrawingRect, etc.)
            drawing_id: Unique ID for the drawing
        """
        super().__init__(canvas, "Add drawing")
        self._drawing_item = drawing_item
        self._drawing_id = drawing_id

    def execute(self) -> bool:
        """Execute is a no-op since the drawing is already added."""
        # Drawing is already added to scene when this command is created
        return True

    def undo(self) -> bool:
        """Remove the drawing from the canvas."""
        try:
            self._canvas.remove_drawing(self._drawing_id)
            return True
        except Exception as e:
            logger.error(f"Failed to undo add drawing: {e}")
            return False

    def redo(self) -> bool:
        """Re-add the drawing to the canvas."""
        try:
            # Re-add to scene and tracking dict
            self._canvas._scene.addItem(self._drawing_item)
            self._canvas._drawings[self._drawing_id] = self._drawing_item
            self._canvas._emit_modified()
            return True
        except Exception as e:
            logger.error(f"Failed to redo add drawing: {e}")
            return False


class CompositeCommand(CanvasCommand):
    """Command that groups multiple commands together."""

    def __init__(self, canvas, commands: List[CanvasCommand], description: str = ""):
        """
        Initialize composite command.

        Args:
            canvas: The canvas
            commands: List of commands to execute together
            description: Description for the group
        """
        super().__init__(canvas, description or f"Multiple operations ({len(commands)})")
        self._commands = commands

    def execute(self) -> bool:
        success = True
        for cmd in self._commands:
            if not cmd.execute():
                success = False
        return success

    def undo(self) -> bool:
        # Undo in reverse order
        success = True
        for cmd in reversed(self._commands):
            if not cmd.undo():
                success = False
        return success


class UndoStack(QObject):
    """
    Manages the undo/redo stack.

    Emits signals when undo/redo availability changes.
    """

    # Signals
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    stack_changed = Signal()

    # Maximum stack size
    MAX_STACK_SIZE = 100

    def __init__(self, parent=None):
        super().__init__(parent)

        self._undo_stack: List[CanvasCommand] = []
        self._redo_stack: List[CanvasCommand] = []
        self._is_executing = False  # Prevent nested commands

    def push(self, command: CanvasCommand):
        """
        Push a command onto the stack and execute it.

        Args:
            command: The command to execute and push
        """
        if self._is_executing:
            logger.warning("Cannot push command while executing")
            return

        self._is_executing = True
        try:
            if command.execute():
                self._undo_stack.append(command)
                self._redo_stack.clear()  # Clear redo stack on new command

                # Limit stack size
                if len(self._undo_stack) > self.MAX_STACK_SIZE:
                    self._undo_stack.pop(0)

                self._emit_changes()
                logger.debug(f"Pushed command: {command.description}")
        finally:
            self._is_executing = False

    def undo(self) -> bool:
        """
        Undo the last command.

        Returns:
            True if undo was successful
        """
        if not self.can_undo():
            return False

        if self._is_executing:
            logger.warning("Cannot undo while executing")
            return False

        self._is_executing = True
        try:
            command = self._undo_stack.pop()
            if command.undo():
                self._redo_stack.append(command)
                self._emit_changes()
                logger.debug(f"Undid: {command.description}")
                return True
            else:
                # Undo failed, put command back
                self._undo_stack.append(command)
                return False
        finally:
            self._is_executing = False

    def redo(self) -> bool:
        """
        Redo the last undone command.

        Returns:
            True if redo was successful
        """
        if not self.can_redo():
            return False

        if self._is_executing:
            logger.warning("Cannot redo while executing")
            return False

        self._is_executing = True
        try:
            command = self._redo_stack.pop()
            if command.redo():
                self._undo_stack.append(command)
                self._emit_changes()
                logger.debug(f"Redid: {command.description}")
                return True
            else:
                # Redo failed, put command back
                self._redo_stack.append(command)
                return False
        finally:
            self._is_executing = False

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return len(self._redo_stack) > 0

    def clear(self):
        """Clear both undo and redo stacks."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._emit_changes()

    def get_undo_text(self) -> str:
        """Get description of next undo action."""
        if self._undo_stack:
            return f"Undo {self._undo_stack[-1].description}"
        return "Undo"

    def get_redo_text(self) -> str:
        """Get description of next redo action."""
        if self._redo_stack:
            return f"Redo {self._redo_stack[-1].description}"
        return "Redo"

    def get_undo_count(self) -> int:
        """Get number of commands in undo stack."""
        return len(self._undo_stack)

    def get_redo_count(self) -> int:
        """Get number of commands in redo stack."""
        return len(self._redo_stack)

    def _emit_changes(self):
        """Emit signals for state changes."""
        self.can_undo_changed.emit(self.can_undo())
        self.can_redo_changed.emit(self.can_redo())
        self.stack_changed.emit()


# Convenience function to create undo stack for a canvas
def create_undo_stack(canvas) -> UndoStack:
    """
    Create an undo stack for a canvas.

    Args:
        canvas: The CollaborativeCanvas instance

    Returns:
        Configured UndoStack
    """
    stack = UndoStack()
    return stack
