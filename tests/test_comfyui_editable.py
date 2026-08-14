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


# ============================================================================
# _parse_editable_marker — cardinality
# ============================================================================

class TestParseEditableMarker:
    def test_plain_is_single(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_SINGLE
        assert _parse_editable_marker("Ref Image_editable") == (
            True, "Ref Image", None, CARDINALITY_SINGLE)

    def test_star_is_many(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_MANY
        assert _parse_editable_marker("Ref Images_editable*") == (
            True, "Ref Images", None, CARDINALITY_MANY)

    def test_question_is_optional(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_OPTIONAL
        assert _parse_editable_marker("Last Frame_editable?") == (
            True, "Last Frame", None, CARDINALITY_OPTIONAL)

    def test_star_with_condition(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_MANY
        assert _parse_editable_marker("Refs_editable*@if_UseRefs") == (
            True, "Refs", "UseRefs", CARDINALITY_MANY)

    def test_question_with_ampersand_condition(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_OPTIONAL
        assert _parse_editable_marker("Tail_editable?&if_Advanced") == (
            True, "Tail", "Advanced", CARDINALITY_OPTIONAL)

    def test_typo_marker_supports_cardinality(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_MANY
        assert _parse_editable_marker("Refs_editble*") == (
            True, "Refs", None, CARDINALITY_MANY)

    def test_not_editable(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_SINGLE
        assert _parse_editable_marker("KSampler") == (
            False, "KSampler", None, CARDINALITY_SINGLE)

    def test_condition_without_cardinality_still_parses(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_SINGLE
        assert _parse_editable_marker("Upscale_editable@if_UseUpscale") == (
            True, "Upscale", "UseUpscale", CARDINALITY_SINGLE)


class TestParseEditableTitleBackCompat:
    def test_still_returns_three_tuple(self):
        from comfyui.editable import _parse_editable_title
        result = _parse_editable_title("Refs_editable*@if_UseRefs")
        assert len(result) == 3
        assert result == (True, "Refs", "UseRefs")


class TestEditableNodeCardinality:
    def test_default_is_single(self):
        from comfyui.editable import EditableNode, CARDINALITY_SINGLE
        node = EditableNode(node_id=1, node_type="LoadImage", title="A_editable",
                            display_name="A", widget_type="image")
        assert node.cardinality == CARDINALITY_SINGLE


# ============================================================================
# API-format editable extraction
# ============================================================================

import json


def _write_api_workflow(tmp_path, workflow, name="api_workflow.json"):
    path = tmp_path / name
    path.write_text(json.dumps(workflow), encoding="utf-8")
    return str(path)


def _h3_style_workflow():
    return {
        "41": {
            "class_type": "LoadImage",
            "inputs": {"image": "ref_a.png"},
            "_meta": {"title": "Ref Images_editable*"},
        },
        "42": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "a cat", "clip": ["9", 0]},
            "_meta": {"title": "Prompt_editable"},
        },
        "43": {
            "class_type": "LoadImage",
            "inputs": {"image": "tail.png"},
            "_meta": {"title": "Last Frame_editable?"},
        },
        "9": {"class_type": "CLIPLoader", "inputs": {"clip_name": "x.safetensors"}},
    }


class TestExtractEditableApiFormat:
    def test_finds_marked_nodes_only(self, tmp_path):
        from comfyui.editable import extract_editable_nodes
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, _h3_style_workflow()))
        assert {n.node_id for n in nodes} == {"41", "42", "43"}

    def test_reads_current_value_from_inputs(self, tmp_path):
        from comfyui.editable import extract_editable_nodes
        by_id = {n.node_id: n for n in
                 extract_editable_nodes(_write_api_workflow(tmp_path, _h3_style_workflow()))}
        assert by_id["41"].current_value == "ref_a.png"
        assert by_id["42"].current_value == "a cat"

    def test_image_widget_type_from_configs(self, tmp_path):
        from comfyui.editable import extract_editable_nodes
        by_id = {n.node_id: n for n in
                 extract_editable_nodes(_write_api_workflow(tmp_path, _h3_style_workflow()))}
        assert by_id["41"].widget_type == "image"
        assert by_id["41"].widget_name == "image"

    def test_cardinality_preserved(self, tmp_path):
        from comfyui.editable import (extract_editable_nodes, CARDINALITY_MANY,
                                      CARDINALITY_OPTIONAL, CARDINALITY_SINGLE)
        by_id = {n.node_id: n for n in
                 extract_editable_nodes(_write_api_workflow(tmp_path, _h3_style_workflow()))}
        assert by_id["41"].cardinality == CARDINALITY_MANY
        assert by_id["43"].cardinality == CARDINALITY_OPTIONAL
        assert by_id["42"].cardinality == CARDINALITY_SINGLE

    def test_linked_inputs_are_not_editable(self, tmp_path):
        """'clip' is a link ["9", 0] and must never become a widget."""
        from comfyui.editable import extract_editable_nodes
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, _h3_style_workflow()))
        assert not any(n.widget_name == "clip" for n in nodes)

    def test_display_name_strips_marker_and_underscores(self, tmp_path):
        from comfyui.editable import extract_editable_nodes
        by_id = {n.node_id: n for n in
                 extract_editable_nodes(_write_api_workflow(tmp_path, _h3_style_workflow()))}
        assert by_id["41"].display_name == "Ref Images"
        assert by_id["43"].display_name == "Last Frame"

    def test_list_valued_widget_is_not_mistaken_for_link(self, tmp_path):
        """[512, 512] is a value, not a node reference."""
        from comfyui.editable import extract_editable_nodes
        wf = {"7": {"class_type": "SomeUnknownCustomNode",
                    "inputs": {"size": [512, 512]},
                    "_meta": {"title": "Size_editable"}}}
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, wf, "size.json"))
        assert len(nodes) == 1
        assert nodes[0].current_value == [512, 512]

    def test_unmarked_nodes_ignored(self, tmp_path):
        from comfyui.editable import extract_editable_nodes
        wf = {"1": {"class_type": "LoadImage", "inputs": {"image": "a.png"}}}
        assert extract_editable_nodes(_write_api_workflow(tmp_path, wf, "none.json")) == []

    def test_ui_format_still_works(self):
        """Regression guard: the UI path must be untouched."""
        import os as _os
        from comfyui.editable import extract_editable_nodes
        path = _os.path.join(_os.path.dirname(__file__), "workflows",
                             "image_qwen_image_edit_2511.json")
        nodes = extract_editable_nodes(path)
        assert len(nodes) > 0
        assert all(n.widget_type for n in nodes)


# ============================================================================
# API-format settings extraction
# ============================================================================

class TestExtractSettingsApiFormat:
    def _workflow(self):
        return {
            "12": {
                "class_type": "KSampler",
                "inputs": {"steps": 20, "cfg": 7.5, "denoise": 1.0, "model": ["3", 0]},
                "_meta": {"title": "Sampler_settings"},
            },
            "3": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": "a.safetensors"}},
        }

    def test_finds_settings_widgets(self, tmp_path):
        from comfyui.editable import extract_settings_nodes
        nodes = extract_settings_nodes(_write_api_workflow(tmp_path, self._workflow(), "s1.json"))
        assert {n.widget_name for n in nodes} == {"steps", "cfg", "denoise"}

    def test_group_name_from_title(self, tmp_path):
        from comfyui.editable import extract_settings_nodes
        nodes = extract_settings_nodes(_write_api_workflow(tmp_path, self._workflow(), "s2.json"))
        assert all(n.group_name == "Sampler" for n in nodes)

    def test_values_read_from_inputs(self, tmp_path):
        from comfyui.editable import extract_settings_nodes
        by_name = {n.widget_name: n for n in
                   extract_settings_nodes(_write_api_workflow(tmp_path, self._workflow(), "s3.json"))}
        assert by_name["steps"].current_value == 20
        assert by_name["cfg"].current_value == 7.5

    def test_linked_input_not_offered(self, tmp_path):
        """'model' is a link and is driven by the graph, not the user."""
        from comfyui.editable import extract_settings_nodes
        nodes = extract_settings_nodes(_write_api_workflow(tmp_path, self._workflow(), "s4.json"))
        assert not any(n.widget_name == "model" for n in nodes)

    def test_unmarked_nodes_ignored(self, tmp_path):
        from comfyui.editable import extract_settings_nodes
        wf = {"1": {"class_type": "KSampler", "inputs": {"steps": 20}}}
        assert extract_settings_nodes(_write_api_workflow(tmp_path, wf, "s5.json")) == []

    def test_ui_format_still_works(self):
        """Regression guard: the UI settings path must be untouched."""
        import os as _os
        from comfyui.editable import extract_settings_nodes
        path = _os.path.join(_os.path.dirname(__file__), "workflows", "video_ltx2_i2v.json")
        nodes = extract_settings_nodes(path)
        assert isinstance(nodes, list)
