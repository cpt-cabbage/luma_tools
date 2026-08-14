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


# ============================================================================
# node_info: optional inputs and known class types
# ============================================================================

class TestNodeInfoOptionalInputs:
    def _raw(self):
        return {
            'input': {
                'required': {'clip': ['CLIP'], 'prompt': ['STRING', {'multiline': True}]},
                'optional': {'media_1': ['*'], 'media_type_1': ['STRING', {'default': ''}]},
            },
            'input_order': {
                'required': ['clip', 'prompt'],
                'optional': ['media_1', 'media_type_1'],
            },
            'display_name': 'Fake H3',
            'category': 'test',
        }

    def test_optional_input_names_parsed(self):
        from comfyui.node_info import _parse_node_info
        info = _parse_node_info('FakeH3', self._raw())
        assert info.optional_input_names == ['media_1', 'media_type_1']

    def test_required_names_still_parsed(self):
        from comfyui.node_info import _parse_node_info
        info = _parse_node_info('FakeH3', self._raw())
        assert info.required_input_names == ['clip', 'prompt']

    def test_optional_defaults_empty(self):
        from comfyui.node_info import NodeTypeInfo
        info = NodeTypeInfo(class_type='X', display_name='X', category='')
        assert info.optional_input_names == []

    def test_known_class_types_returns_set(self):
        from comfyui.node_info import get_known_class_types
        result = get_known_class_types()
        assert isinstance(result, set)

    def test_known_class_types_empty_on_cache_miss(self, tmp_path, monkeypatch):
        """A cold/unavailable cache must yield an empty set, never None or a
        falsy-but-wrong value. A later task uses this to gate Submit — a
        non-empty result on a cache miss would incorrectly block valid
        submissions, so the miss case must be pinned exactly.
        """
        from comfyui import node_info

        # Point the module singleton at an empty tmp dir with no cache file
        # and no network fallback, guaranteeing a genuine cache miss
        # regardless of what other tests may have loaded into it.
        fresh_cache = node_info.NodeInfoCache(cache_dir=str(tmp_path))
        monkeypatch.setattr(node_info, "_cache", fresh_cache)
        monkeypatch.setattr(node_info, "_get_network_cache_path", lambda: None)

        result = node_info.get_known_class_types()
        assert result == set()


# ============================================================================
# NodeInfoCache: save/load round-trip
# ============================================================================

class TestNodeInfoCacheRoundTrip:
    def test_optional_input_names_survive_save_and_load(self, tmp_path):
        """optional_input_names must be wired through both save_to_path and
        _load_from_data, mirroring required_input_names. A prior gap parsed
        the field correctly in-memory but dropped it on the persisted-cache
        round trip, so every cold-started process reading the local or
        network cache saw an empty list regardless of source data.
        """
        import time
        from comfyui.node_info import NodeInfoCache, NodeTypeInfo

        writer = NodeInfoCache(cache_dir=str(tmp_path))
        writer._node_types['FakeH3'] = NodeTypeInfo(
            class_type='FakeH3',
            display_name='Fake H3',
            category='test',
            required_input_names=['clip', 'prompt'],
            optional_input_names=['media_1', 'media_type_1'],
        )
        writer._last_fetch_time = time.time()
        writer.save_to_path(writer._cache_path)

        # Load through a fresh instance and the real disk-load path
        # (_load_from_disk -> _load_from_data), not a direct call into
        # _load_from_data, so the test exercises the actual cold-start
        # code path a workstation process takes.
        reader = NodeInfoCache(cache_dir=str(tmp_path))
        reader._load_from_disk()

        info = reader._node_types['FakeH3']
        assert info.optional_input_names == ['media_1', 'media_type_1']
        assert info.required_input_names == ['clip', 'prompt']

    def test_optional_input_names_omitted_when_empty(self, tmp_path):
        """Mirrors required_input_names: an empty list is not written to
        disk at all (matches the conditional `if node_info.required_input_names`
        pattern), and loading it back still yields an empty list via the
        dataclass default / .get(..., []) fallback.
        """
        from comfyui.node_info import NodeInfoCache, NodeTypeInfo

        writer = NodeInfoCache(cache_dir=str(tmp_path))
        writer._node_types['NoOptionals'] = NodeTypeInfo(
            class_type='NoOptionals',
            display_name='No Optionals',
            category='test',
        )
        writer.save_to_path(writer._cache_path)

        with open(writer._cache_path, 'r', encoding='utf-8') as f:
            raw = f.read()
        assert 'optional_input_names' not in raw

        reader = NodeInfoCache(cache_dir=str(tmp_path))
        reader._load_from_disk()
        assert reader._node_types['NoOptionals'].optional_input_names == []
