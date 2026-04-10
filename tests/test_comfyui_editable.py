"""Tests for comfyui.editable — editable node parsing and extraction."""

import pytest

from comfyui.editable import (
    EditableNode,
    _parse_editable_title,
    _COMFYUI_TYPE_MAP,
)


# ============================================================================
# EditableNode dataclass
# ============================================================================

class TestEditableNode:
    def test_defaults(self):
        node = EditableNode(
            node_id=1,
            node_type="KSampler",
            title="Sampler_editable",
            display_name="Sampler",
            widget_type="int",
        )
        assert node.node_id == 1
        assert node.widget_name == ""
        assert node.current_value is None
        assert node.options == []
        assert node.condition_node is None

    def test_full_init(self):
        node = EditableNode(
            node_id=5,
            node_type="CheckpointLoaderSimple",
            title="Model_editable",
            display_name="Model",
            widget_type="combo",
            widget_name="ckpt_name",
            current_value="sd_v1.5.safetensors",
            options=["sd_v1.5.safetensors", "sdxl.safetensors"],
            condition_node="UseUpscale",
        )
        assert node.condition_node == "UseUpscale"
        assert len(node.options) == 2

    def test_options_list_independent(self):
        n1 = EditableNode(node_id=1, node_type="A", title="A", display_name="A", widget_type="combo")
        n2 = EditableNode(node_id=2, node_type="B", title="B", display_name="B", widget_type="combo")
        n1.options.append("opt1")
        assert n2.options == []


# ============================================================================
# _parse_editable_title
# ============================================================================

class TestParseEditableTitle:
    def test_simple_editable(self):
        is_edit, base, cond = _parse_editable_title("Sampler_editable")
        assert is_edit is True
        assert base == "Sampler"
        assert cond is None

    def test_typo_editble(self):
        is_edit, base, cond = _parse_editable_title("Prompt_editble")
        assert is_edit is True
        assert base == "Prompt"

    def test_not_editable(self):
        is_edit, base, cond = _parse_editable_title("KSampler")
        assert is_edit is False
        assert base == "KSampler"
        assert cond is None

    def test_conditional_at_syntax(self):
        is_edit, base, cond = _parse_editable_title("Upscale_editable@if_UseUpscale")
        assert is_edit is True
        assert base == "Upscale"
        assert cond == "UseUpscale"

    def test_conditional_ampersand_syntax(self):
        is_edit, base, cond = _parse_editable_title("Steps_editable&if_AdvancedMode")
        assert is_edit is True
        assert base == "Steps"
        assert cond == "AdvancedMode"

    def test_spaces_in_name(self):
        is_edit, base, cond = _parse_editable_title("My Cool Node_editable")
        assert is_edit is True
        assert base == "My Cool Node"

    def test_empty_string(self):
        is_edit, base, cond = _parse_editable_title("")
        assert is_edit is False
        assert base == ""

    def test_editable_only(self):
        is_edit, base, cond = _parse_editable_title("_editable")
        assert is_edit is True
        assert base == ""

    def test_editable_with_no_condition_after_marker(self):
        is_edit, base, cond = _parse_editable_title("Node_editable_extra")
        assert is_edit is True
        assert base == "Node"
        # "extra" doesn't start with @if_ or &if_, so no condition
        assert cond is None


# ============================================================================
# Type map
# ============================================================================

class TestComfyuiTypeMap:
    def test_standard_mappings(self):
        assert _COMFYUI_TYPE_MAP["INT"] == "int"
        assert _COMFYUI_TYPE_MAP["FLOAT"] == "float"
        assert _COMFYUI_TYPE_MAP["BOOLEAN"] == "toggle"
        assert _COMFYUI_TYPE_MAP["STRING"] == "string"
        assert _COMFYUI_TYPE_MAP["COMBO"] == "combo"
