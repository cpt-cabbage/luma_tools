"""
ComfyUI State Manager Module.

Handles state persistence and restoration for the ComfyUI tab.
Extracted from comfyui_tab.py to improve maintainability.
"""

import random
from typing import Dict, Any, Optional


class ComfyUIStateManager:
    """Manages state persistence and restoration for ComfyUI tab."""

    def __init__(self):
        """Initialize the state manager."""
        self.current_preset_name = None
        self.current_selected_workflow = None  # For multi-workflow models

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
