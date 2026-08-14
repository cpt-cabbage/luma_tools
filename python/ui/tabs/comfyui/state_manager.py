"""
ComfyUI State Manager Module.

Handles state persistence and restoration for the ComfyUI tab.
Extracted from comfyui_tab.py to improve maintainability.
"""

import random
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ComfyUI seeds are 64-bit. The seed field is a QLineEdit (not a QSpinBox,
# which clamps at 2^31-1), so every read has to parse text defensively.
SEED_MAX = 2 ** 63 - 1


def read_seed(ui) -> int:
    """Read the seed widget as an int, falling back to 0 on anything unparsable."""
    widget = ui.ComfyUISeed
    # Tolerate an older compiled .ui where the seed was still a QSpinBox.
    if hasattr(widget, "value"):
        try:
            return int(widget.value())
        except (TypeError, ValueError):
            return 0
    try:
        value = int((widget.text() or "").strip())
    except (TypeError, ValueError):
        return 0
    return max(0, min(SEED_MAX, value))


def write_seed(ui, value) -> None:
    """Write an int seed into the seed widget, clamping to the valid range."""
    try:
        seed = int(value)
    except (TypeError, ValueError):
        seed = 0
    seed = max(0, min(SEED_MAX, seed))

    widget = ui.ComfyUISeed
    if hasattr(widget, "setValue"):
        widget.setValue(seed)
    else:
        widget.setText(str(seed))


def random_seed() -> int:
    """Generate a new random 64-bit seed."""
    return random.randint(0, SEED_MAX)


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
            "seed": read_seed(ui),
            "custom_name": ui.ComfyUIName.text().strip(),
            "custom_name_enabled": ui.ComfyUINameToggle.isChecked(),
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
        seed = state.get("seed", random_seed())
        write_seed(ui, seed)

        # Restore custom name toggle and text
        custom_name_enabled = state.get("custom_name_enabled", False)
        custom_name = state.get("custom_name", "")
        ui.ComfyUINameToggle.setChecked(custom_name_enabled)
        ui.ComfyUIName.setVisible(custom_name_enabled)
        if custom_name_enabled:
            ui.ComfyUIName.setText(custom_name)

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
            write_seed(ui, base_seed)

        # Restore generation count
        gen_count = metadata.get("generation_count")
        if gen_count is not None:
            ui.ComfyUIGenerationCount.setValue(gen_count)

        # Restore custom name from metadata
        custom_name = metadata.get("custom_name")
        if custom_name:
            ui.ComfyUINameToggle.setChecked(True)
            ui.ComfyUIName.setVisible(True)
            ui.ComfyUIName.setText(custom_name)

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
    # PER-WORKFLOW INPUT PERSISTENCE
    # =========================================================================

    def get_workflow_key(self) -> str:
        """Return a storage key for the current preset + sub-workflow.

        Returns:
            Key like "PresetName" or "PresetName/SubWorkflow"
        """
        if not self.current_preset_name:
            return ""
        if self.current_selected_workflow:
            return f"{self.current_preset_name}/{self.current_selected_workflow}"
        return self.current_preset_name

    def save_per_workflow_inputs(self, widget_manager) -> None:
        """Save current widget values to per-workflow store.

        Args:
            widget_manager: ComfyUIWidgetManager instance
        """
        from core.settings_manager import safe_get_setting, safe_set_setting

        workflow_key = self.get_workflow_key()
        if not workflow_key:
            return

        values = widget_manager.capture_editable_values_by_type()
        if not values:
            return

        store = safe_get_setting("comfyui_per_workflow_inputs", {})
        store[workflow_key] = values
        safe_set_setting("comfyui_per_workflow_inputs", store)
        logger.debug(f"[PerWorkflow] Saved {len(values)} values for '{workflow_key}'")

    def load_per_workflow_inputs(self, workflow_key: str = None) -> Dict[str, Any]:
        """Load saved values for a workflow key.

        Filters file paths to only include files that still exist.

        Args:
            workflow_key: Workflow key to load. Uses current if None.

        Returns:
            Semantic values dict (e.g. {'text/Prompt': 'value', ...})
        """
        import os
        from core.settings_manager import safe_get_setting

        if workflow_key is None:
            workflow_key = self.get_workflow_key()
        if not workflow_key:
            return {}

        store = safe_get_setting("comfyui_per_workflow_inputs", {})
        values = store.get(workflow_key, {})
        if not values:
            return {}

        # Filter file paths: only keep existing files
        filtered = {}
        for key, value in values.items():
            if isinstance(value, list):
                # BatchImageSelector paths — keep only existing files
                existing = [p for p in value if os.path.exists(p)]
                if existing:
                    filtered[key] = existing
            else:
                filtered[key] = value

        return filtered

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
            seed=read_seed(ui),
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
            write_seed(ui, seed)

        gen_count = session.get("generation_count")
        if gen_count is not None:
            ui.ComfyUIGenerationCount.setValue(gen_count)

        logger.info(f"[Session] Restored session: {session.get('description', 'unknown')}")

        # Editable values are stored flat ("node_id:widget_name" -> value), the
        # same shape _apply_pending_editable_values() consumes, so hand them
        # back untouched.
        return session.get("editable_values", {}) or None

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

