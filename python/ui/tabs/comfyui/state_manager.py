"""
ComfyUI State Manager Module.

Handles state persistence and restoration for the ComfyUI tab.
Extracted from comfyui_tab.py to improve maintainability.
"""

import random
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Maximum number of history entries to keep
MAX_HISTORY_SIZE = 50


class ComfyUIStateManager:
    """Manages state persistence and restoration for ComfyUI tab."""

    def __init__(self):
        """Initialize the state manager."""
        self.current_preset_name = None
        self.current_selected_workflow = None  # For multi-workflow models
        self._history: List[Dict[str, Any]] = []  # Parameter history for undo
        self._history_index = -1  # Current position in history (-1 = at latest)

    def save_state(self, ui, widget_manager) -> Dict[str, Any]:
        """
        Capture current ComfyUI tab state for persistence.

        Args:
            ui: Tab UI object with generation count and seed widgets
            widget_manager: ComfyUIWidgetManager instance

        Returns:
            State dictionary
        """
        state = {
            "workflow_preset": self.current_preset_name or "",
            "selected_workflow": self.current_selected_workflow or "",  # For multi-workflow models
            "generation_count": ui.ComfyUIGenerationCount.value(),
            "seed": ui.ComfyUISeed.value(),
        }

        # Save editable node values
        state["editable_values"] = widget_manager.get_editable_values_for_state()

        return state

    def restore_state(self, state: Dict[str, Any], ui, select_preset_callback) -> Optional[Dict[str, Any]]:
        """
        Restore ComfyUI tab state from persisted data.

        Args:
            state: State dictionary from settings
            ui: Tab UI object with generation count and seed widgets
            select_preset_callback: Callback to select a preset (function that takes preset_name)

        Returns:
            Pending editable values dict to be applied after widgets are created
        """
        from comfyui.presets_manager import get_comfyui_workflow_presets

        if not state:
            return None

        # Restore workflow preset selection
        preset_name = state.get("workflow_preset", "")
        selected_workflow = state.get("selected_workflow", "")

        if preset_name:
            presets = get_comfyui_workflow_presets()
            if preset_name in presets:
                # Set the selected workflow before selecting preset (for multi-workflow models)
                if selected_workflow:
                    self.current_selected_workflow = selected_workflow
                select_preset_callback(preset_name)

        # Restore generation count
        gen_count = state.get("generation_count", 1)
        ui.ComfyUIGenerationCount.setValue(gen_count)

        # Restore seed
        seed = state.get("seed", random.randint(0, 2147483647))
        ui.ComfyUISeed.setValue(seed)

        # Return editable values to apply after widgets are created
        return state.get("editable_values", {})

    def apply_settings_from_metadata(self, metadata: Dict[str, Any], ui, select_preset_callback) -> Optional[Dict[str, Any]]:
        """
        Apply settings from image metadata to restore the ComfyUI tab state.

        This allows users to recreate the exact configuration used to generate
        a specific image by copying settings from the gallery context menu.

        Args:
            metadata: Dictionary containing image generation metadata with keys:
                - workflow_preset: Full preset name (e.g. "folder/preset_name")
                - base_seed: The seed value used
                - generation_count: Number of generations
                - editable_values: Dict of node_id -> {display_name, value, ...}
            ui: Tab UI object with generation count and seed widgets
            select_preset_callback: Callback to select a preset (function that takes preset_name)

        Returns:
            Pending editable values dict to be applied after widgets are created,
            or None if metadata is invalid
        """
        from comfyui.presets_manager import get_comfyui_workflow_presets

        if not metadata:
            return None

        # Restore workflow preset
        workflow_preset = metadata.get("workflow_preset")
        if workflow_preset:
            presets = get_comfyui_workflow_presets()
            if workflow_preset in presets:
                select_preset_callback(workflow_preset)

        # Restore seed
        base_seed = metadata.get("base_seed")
        if base_seed is not None:
            ui.ComfyUISeed.setValue(base_seed)

        # Restore generation count
        gen_count = metadata.get("generation_count")
        if gen_count is not None:
            ui.ComfyUIGenerationCount.setValue(gen_count)

        # Prepare editable values for restoration
        editable_values = metadata.get("editable_values")
        if editable_values:
            pending_values = {
                node_id: data.get("value", "")
                for node_id, data in editable_values.items()
            }
            return pending_values

        return None

    # =========================================================================
    # PARAMETER HISTORY (for undo functionality)
    # =========================================================================

    def push_history(self, ui, widget_manager, description: str = None):
        """
        Save current state to history for undo capability.

        Call this before making changes that should be undoable.

        Args:
            ui: Tab UI object
            widget_manager: ComfyUIWidgetManager instance
            description: Optional description of what changed
        """
        state = self.save_state(ui, widget_manager)
        state["_history_description"] = description or "Parameter change"
        state["_history_timestamp"] = datetime.now().isoformat()

        # If we're not at the end of history, truncate forward history
        if self._history_index >= 0 and self._history_index < len(self._history) - 1:
            self._history = self._history[:self._history_index + 1]

        self._history.append(state)
        self._history_index = len(self._history) - 1

        # Trim history if too large
        if len(self._history) > MAX_HISTORY_SIZE:
            excess = len(self._history) - MAX_HISTORY_SIZE
            self._history = self._history[excess:]
            self._history_index -= excess

        logger.debug(f"[History] Pushed state: {description} (index={self._history_index})")

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self._history_index > 0

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self._history_index < len(self._history) - 1

    def undo(self, ui, select_preset_callback) -> Optional[Dict[str, Any]]:
        """
        Undo to previous state.

        Args:
            ui: Tab UI object
            select_preset_callback: Callback to select a preset

        Returns:
            Pending editable values to apply, or None if cannot undo
        """
        if not self.can_undo():
            logger.debug("[History] Cannot undo - at beginning of history")
            return None

        self._history_index -= 1
        state = self._history[self._history_index]

        logger.debug(f"[History] Undo to index {self._history_index}: {state.get('_history_description')}")

        return self.restore_state(state, ui, select_preset_callback)

    def redo(self, ui, select_preset_callback) -> Optional[Dict[str, Any]]:
        """
        Redo to next state.

        Args:
            ui: Tab UI object
            select_preset_callback: Callback to select a preset

        Returns:
            Pending editable values to apply, or None if cannot redo
        """
        if not self.can_redo():
            logger.debug("[History] Cannot redo - at end of history")
            return None

        self._history_index += 1
        state = self._history[self._history_index]

        logger.debug(f"[History] Redo to index {self._history_index}: {state.get('_history_description')}")

        return self.restore_state(state, ui, select_preset_callback)

    def get_history_info(self) -> Dict[str, Any]:
        """
        Get information about current history state.

        Returns:
            Dict with can_undo, can_redo, history_size, current_index
        """
        return {
            "can_undo": self.can_undo(),
            "can_redo": self.can_redo(),
            "history_size": len(self._history),
            "current_index": self._history_index,
        }

    def clear_history(self):
        """Clear all history."""
        self._history.clear()
        self._history_index = -1
        logger.debug("[History] Cleared")

    # =========================================================================
    # SESSION CONTINUITY (resume previous work)
    # =========================================================================

    def save_current_session(self, ui, widget_manager, input_images: list = None, description: str = None) -> bool:
        """Save current state as a resumable session.

        Call this when user wants to save their work for later,
        or auto-save before significant operations.

        Args:
            ui: Tab UI object
            widget_manager: ComfyUIWidgetManager instance
            input_images: List of input image paths
            description: Optional description (auto-generated if not provided)

        Returns:
            bool: True if saved successfully
        """
        from comfyui.presets_manager import save_session

        if not self.current_preset_name:
            logger.warning("[Session] Cannot save session - no workflow preset selected")
            return False

        editable_values = widget_manager.get_editable_values_for_state()

        return save_session(
            workflow_preset=self.current_preset_name,
            editable_values=editable_values,
            seed=ui.ComfyUISeed.value(),
            generation_count=ui.ComfyUIGenerationCount.value(),
            input_images=input_images,
            description=description
        )

    def get_recent_sessions(self) -> list:
        """Get list of recent sessions for display.

        Returns:
            List of session dicts with formatted display strings
        """
        from comfyui.presets_manager import get_recent_sessions, format_session_display

        sessions = get_recent_sessions()
        # Add formatted display text to each session
        for session in sessions:
            session['display_text'] = format_session_display(session)
        return sessions

    def restore_session(self, session_index: int, ui, select_preset_callback) -> Optional[Dict[str, Any]]:
        """Restore a previous session by index.

        Args:
            session_index: 0-based index (0 = most recent)
            ui: Tab UI object
            select_preset_callback: Callback to select a preset

        Returns:
            Pending editable values to apply, or None if failed
        """
        from comfyui.presets_manager import get_session_by_index, get_comfyui_workflow_presets

        session = get_session_by_index(session_index)
        if not session:
            logger.warning(f"[Session] Session index {session_index} not found")
            return None

        workflow_preset = session.get("workflow_preset")
        if not workflow_preset:
            logger.warning("[Session] Session has no workflow preset")
            return None

        # Verify preset still exists
        presets = get_comfyui_workflow_presets()
        if workflow_preset not in presets:
            logger.warning(f"[Session] Workflow preset '{workflow_preset}' no longer exists")
            return None

        # Select the workflow preset
        select_preset_callback(workflow_preset)

        # Restore seed and generation count
        seed = session.get("seed")
        if seed is not None:
            ui.ComfyUISeed.setValue(seed)

        gen_count = session.get("generation_count")
        if gen_count is not None:
            ui.ComfyUIGenerationCount.setValue(gen_count)

        logger.info(f"[Session] Restored session: {session.get('description', 'unknown')}")

        # Return editable values to apply after widgets are created
        editable_values = session.get("editable_values", {})
        if editable_values:
            # Convert to simple node_id -> value format for pending application
            return {
                node_id: data.get("value", "")
                for node_id, data in editable_values.items()
            }

        return None

    def get_session_input_images(self, session_index: int) -> list:
        """Get input images from a session.

        Args:
            session_index: 0-based index

        Returns:
            List of input image paths, or empty list
        """
        from comfyui.presets_manager import get_session_by_index

        session = get_session_by_index(session_index)
        if session:
            return session.get("input_images", [])
        return []

    def delete_session(self, session_index: int) -> bool:
        """Delete a session by index.

        Args:
            session_index: 0-based index

        Returns:
            bool: True if deleted
        """
        from comfyui.presets_manager import delete_session
        return delete_session(session_index)

    def clear_all_sessions(self) -> bool:
        """Clear all saved sessions.

        Returns:
            bool: True if cleared
        """
        from comfyui.presets_manager import clear_recent_sessions
        return clear_recent_sessions()
