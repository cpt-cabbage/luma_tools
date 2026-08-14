"""Unit tests for comfyui.workflow module.

Tests cover all public and private functions in workflow.py:
- load_workflow / save_workflow (file I/O)
- is_api_format (format detection)
- _is_uuid (UUID validation)
- _normalize_link (link normalization)
- _extract_widget_names_from_node (widget name extraction)
- _build_subgraph_widget_map / _get_subgraph_definitions (subgraph helpers)
- _apply_boundary_overrides (boundary override propagation)
- expand_subgraphs (subgraph expansion)
- convert_to_api_format (UI -> API conversion)
"""
import sys
import os

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))

# Path to test workflow files
WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), 'workflows')

# All test workflow filenames
ALL_WORKFLOW_FILES = [
    'NormalCrafter_ImageSequence.json',
    'NormalCrafter_Video.json',
    'audio_stable_audio.json',
    'audio_ace_step_1_5.json',
    'mmaudio.json',
    'sharp_basic.json',
    'image_qwen_image_layered_control.json',
    'image_qwen_image_edit_2511.json',
    'image_qwen_image_2512_with_2steps_lora.json',
    'video_ltx2_i2v.json',
    'Trellis_2.json',
]


# ---------------------------------------------------------------------------
# Helpers: load real workflows
# ---------------------------------------------------------------------------

def _load_test_workflow(name):
    """Load a real workflow JSON from tests/workflows/ by filename."""
    import json
    path = os.path.join(WORKFLOWS_DIR, name)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Helpers: synthetic fixture factories
# ---------------------------------------------------------------------------

def _make_ui_node(node_id, node_type, widgets_values=None, inputs=None,
                  outputs=None, mode=0, title=None, properties=None):
    """Build a single UI-format node dict."""
    node = {
        'id': node_id,
        'type': node_type,
        'mode': mode,
        'inputs': inputs or [],
        'outputs': outputs or [],
        'widgets_values': widgets_values if widgets_values is not None else [],
        'properties': properties or {},
    }
    if title:
        node['title'] = title
    return node


def _make_link(link_id, from_node, from_slot, to_node, to_slot, link_type='*'):
    """Build a 6-element link list."""
    return [link_id, from_node, from_slot, to_node, to_slot, link_type]


def _make_simple_workflow():
    """3-node linear workflow: CheckpointLoader -> KSampler -> SaveImage.

    Links:
      link 1: node 1 slot 0 -> node 2 slot 0 (MODEL)
      link 2: node 2 slot 0 -> node 3 slot 0 (LATENT)
    """
    nodes = [
        _make_ui_node(
            1, 'CheckpointLoaderSimple',
            widgets_values=['model.safetensors'],
            inputs=[{'name': 'ckpt_name', 'widget': {'name': 'ckpt_name'}, 'link': None}],
            outputs=[{'name': 'MODEL', 'links': [1], 'slot_index': 0}],
        ),
        _make_ui_node(
            2, 'KSampler',
            widgets_values=[12345, 'randomize', 20, 7.0, 'euler', 'normal', 1.0],
            inputs=[
                {'name': 'model', 'link': 1, 'slot_index': 0},
                {'name': 'seed', 'widget': {'name': 'seed'}, 'link': None},
                {'name': 'steps', 'widget': {'name': 'steps'}, 'link': None},
                {'name': 'cfg', 'widget': {'name': 'cfg'}, 'link': None},
                {'name': 'sampler_name', 'widget': {'name': 'sampler_name'}, 'link': None},
                {'name': 'scheduler', 'widget': {'name': 'scheduler'}, 'link': None},
                {'name': 'denoise', 'widget': {'name': 'denoise'}, 'link': None},
            ],
            outputs=[{'name': 'LATENT', 'links': [2], 'slot_index': 0}],
        ),
        _make_ui_node(
            3, 'SaveImage',
            widgets_values=['output'],
            inputs=[
                {'name': 'images', 'link': 2, 'slot_index': 0},
                {'name': 'filename_prefix', 'widget': {'name': 'filename_prefix'}, 'link': None},
            ],
            outputs=[],
        ),
    ]
    links = [
        _make_link(1, 1, 0, 2, 0, 'MODEL'),
        _make_link(2, 2, 0, 3, 0, 'LATENT'),
    ]
    return {'nodes': nodes, 'links': links}


def _make_bypassed_node_workflow():
    """Workflow with a bypassed node (mode=4) between two active nodes.

    node 1 (active) -> node 2 (bypassed, mode=4) -> node 3 (active)

    litegraph modes: 2 = NEVER (mute), 4 = BYPASS. Only BYPASS passes data
    through, which is why this fixture uses mode 4 for the pass-through case.
    """
    nodes = [
        _make_ui_node(
            1, 'NodeA',
            widgets_values=['val_a'],
            inputs=[{'name': 'a_in', 'widget': {'name': 'a_in'}, 'link': None}],
            outputs=[{'name': 'OUT', 'links': [1], 'slot_index': 0}],
        ),
        _make_ui_node(
            2, 'NodeB',
            widgets_values=['val_b'],
            inputs=[{'name': 'b_in', 'link': 1, 'slot_index': 0}],
            outputs=[{'name': 'OUT', 'links': [2], 'slot_index': 0}],
            mode=4,  # muted
        ),
        _make_ui_node(
            3, 'NodeC',
            widgets_values=['val_c'],
            inputs=[
                {'name': 'c_in', 'link': 2, 'slot_index': 0},
                {'name': 'c_widget', 'widget': {'name': 'c_widget'}, 'link': None},
            ],
            outputs=[],
        ),
    ]
    links = [
        _make_link(1, 1, 0, 2, 0, 'DATA'),
        _make_link(2, 2, 0, 3, 0, 'DATA'),
    ]
    return {'nodes': nodes, 'links': links}


def _make_chained_bypassed_workflow():
    """Workflow with 2 consecutive bypassed nodes.

    node 1 (active) -> node 2 (bypassed) -> node 3 (bypassed) -> node 4 (active)
    """
    nodes = [
        _make_ui_node(
            1, 'NodeA',
            widgets_values=['val_a'],
            inputs=[{'name': 'a_in', 'widget': {'name': 'a_in'}, 'link': None}],
            outputs=[{'name': 'OUT', 'links': [1], 'slot_index': 0}],
        ),
        _make_ui_node(
            2, 'NodeB', mode=4,
            inputs=[{'name': 'in', 'link': 1, 'slot_index': 0}],
            outputs=[{'name': 'OUT', 'links': [2], 'slot_index': 0}],
        ),
        _make_ui_node(
            3, 'NodeC', mode=4,
            inputs=[{'name': 'in', 'link': 2, 'slot_index': 0}],
            outputs=[{'name': 'OUT', 'links': [3], 'slot_index': 0}],
        ),
        _make_ui_node(
            4, 'NodeD',
            widgets_values=['val_d'],
            inputs=[
                {'name': 'd_in', 'link': 3, 'slot_index': 0},
                {'name': 'd_widget', 'widget': {'name': 'd_widget'}, 'link': None},
            ],
            outputs=[],
        ),
    ]
    links = [
        _make_link(1, 1, 0, 2, 0, 'DATA'),
        _make_link(2, 2, 0, 3, 0, 'DATA'),
        _make_link(3, 3, 0, 4, 0, 'DATA'),
    ]
    return {'nodes': nodes, 'links': links}


# ===========================================================================
# Test Classes
# ===========================================================================


class TestIsApiFormat:
    """Tests for is_api_format() — detect whether a workflow dict is API format."""

    def test_api_format_detected(self):
        """API format dict with class_type returns True."""
        from comfyui.workflow import is_api_format
        wf = {'1': {'class_type': 'KSampler', 'inputs': {}}}
        assert is_api_format(wf) is True

    def test_ui_format_detected(self):
        """UI format dict with 'nodes' key returns False."""
        from comfyui.workflow import is_api_format
        wf = {'nodes': [{'id': 1, 'type': 'KSampler'}]}
        assert is_api_format(wf) is False

    def test_empty_dict_returns_false(self):
        """Empty dict has no class_type values, returns False."""
        from comfyui.workflow import is_api_format
        assert is_api_format({}) is False

    def test_multiple_api_nodes(self):
        """Multiple API-format nodes detected."""
        from comfyui.workflow import is_api_format
        wf = {
            '1': {'class_type': 'KSampler', 'inputs': {}},
            '2': {'class_type': 'SaveImage', 'inputs': {}},
        }
        assert is_api_format(wf) is True

    def test_ui_with_nested_class_type_returns_false(self):
        """UI format with class_type inside nested structures still returns False
        because the top-level dict has 'nodes' key."""
        from comfyui.workflow import is_api_format
        wf = {'nodes': [{'class_type': 'X'}], 'extra': {}}
        assert is_api_format(wf) is False

    def test_non_dict_values_return_false(self):
        """Dict with non-dict values and no 'nodes' returns False."""
        from comfyui.workflow import is_api_format
        wf = {'key': 'not_a_dict', 'other': 42}
        assert is_api_format(wf) is False

    def test_dict_value_without_class_type(self):
        """Dict values that are dicts but lack class_type return False."""
        from comfyui.workflow import is_api_format
        wf = {'1': {'inputs': {}, 'outputs': {}}}
        assert is_api_format(wf) is False

    def test_mixed_values(self):
        """First dict value with class_type is enough to return True."""
        from comfyui.workflow import is_api_format
        wf = {
            'metadata': 'some_string',
            '1': {'class_type': 'KSampler', 'inputs': {}},
        }
        assert is_api_format(wf) is True


class TestIsUuid:
    """Tests for _is_uuid() — check if a value looks like a UUID string."""

    def test_valid_lowercase(self):
        """Standard lowercase UUID is valid."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid('f754a936-daaf-4b6e-9658-41fdc54d301d') is True

    def test_valid_uppercase(self):
        """Uppercase UUID is valid (function lowercases before matching)."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid('F754A936-DAAF-4B6E-9658-41FDC54D301D') is True

    def test_valid_mixed_case(self):
        """Mixed-case UUID is valid."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid('f754A936-Daaf-4b6E-9658-41FDc54d301D') is True

    def test_invalid_too_short(self):
        """Truncated string is not a UUID."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid('f754a936-daaf-4b6e') is False

    def test_invalid_no_dashes(self):
        """32 hex chars without dashes is not detected as UUID."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid('f754a936daaf4b6e965841fdc54d301d') is False

    def test_invalid_wrong_segments(self):
        """Wrong segment lengths are rejected."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid('f754a93-6daaf-4b6e-9658-41fdc54d301d') is False

    def test_invalid_non_hex(self):
        """Non-hex characters are rejected."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid('g754a936-daaf-4b6e-9658-41fdc54d301d') is False

    def test_integer_returns_false(self):
        """Integer input returns False."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid(12345) is False

    def test_none_returns_false(self):
        """None returns False."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid(None) is False

    def test_empty_string_returns_false(self):
        """Empty string returns False."""
        from comfyui.workflow import _is_uuid
        assert _is_uuid('') is False


class TestNormalizeLink:
    """Tests for _normalize_link() — normalize various link formats to list."""

    def test_list_passthrough(self):
        """List input passes through unchanged."""
        from comfyui.workflow import _normalize_link
        link = [1, 10, 0, 20, 1, 'MODEL']
        result = _normalize_link(link)
        assert result == [1, 10, 0, 20, 1, 'MODEL']

    def test_tuple_to_list(self):
        """Tuple input converted to list."""
        from comfyui.workflow import _normalize_link
        link = (1, 10, 0, 20, 1, 'MODEL')
        result = _normalize_link(link)
        assert result == [1, 10, 0, 20, 1, 'MODEL']
        assert isinstance(result, list)

    def test_none_returns_none(self):
        """None input returns None."""
        from comfyui.workflow import _normalize_link
        assert _normalize_link(None) is None

    def test_dict_integer_keys(self):
        """Dict with integer keys (0,1,2,3,4,5) normalizes correctly."""
        from comfyui.workflow import _normalize_link
        link = {0: 1, 1: 10, 2: 0, 3: 20, 4: 1, 5: 'MODEL'}
        result = _normalize_link(link)
        assert result == [1, 10, 0, 20, 1, 'MODEL']

    def test_dict_string_integer_keys(self):
        """Dict with string-integer keys ('0','1',...) normalizes correctly."""
        from comfyui.workflow import _normalize_link
        link = {'0': 1, '1': 10, '2': 0, '3': 20, '4': 1, '5': 'MODEL'}
        result = _normalize_link(link)
        assert result == [1, 10, 0, 20, 1, 'MODEL']

    def test_dict_named_keys_origin(self):
        """Dict with origin_id/target_id naming convention."""
        from comfyui.workflow import _normalize_link
        link = {
            'id': 5,
            'origin_id': 10,
            'origin_slot': 0,
            'target_id': 20,
            'target_slot': 1,
            'type': 'IMAGE',
        }
        result = _normalize_link(link)
        assert result == [5, 10, 0, 20, 1, 'IMAGE']

    def test_dict_named_keys_from_node(self):
        """Dict with from_node/to_node naming convention."""
        from comfyui.workflow import _normalize_link
        link = {
            'link_id': 7,
            'from_node': 100,
            'from_slot': 2,
            'to_node': 200,
            'to_slot': 3,
            'type': 'LATENT',
        }
        result = _normalize_link(link)
        assert result == [7, 100, 2, 200, 3, 'LATENT']

    def test_dict_default_slot_and_type(self):
        """Missing slot/type fields get defaults (0 and '*')."""
        from comfyui.workflow import _normalize_link
        link = {'id': 1, 'origin_id': 10, 'target_id': 20}
        result = _normalize_link(link)
        assert result == [1, 10, 0, 20, 0, '*']

    def test_invalid_dict_returns_none(self):
        """Dict missing required fields returns None."""
        from comfyui.workflow import _normalize_link
        link = {'id': 1}  # missing from_node and to_node
        assert _normalize_link(link) is None

    def test_invalid_type_returns_none(self):
        """Non-dict, non-list, non-tuple, non-None type returns None."""
        from comfyui.workflow import _normalize_link
        assert _normalize_link(42) is None
        assert _normalize_link('not_a_link') is None

    def test_empty_list_passthrough(self):
        """Empty list passes through (caller should handle length)."""
        from comfyui.workflow import _normalize_link
        assert _normalize_link([]) == []

    def test_integer_key_priority_over_named(self):
        """When a dict has both integer keys and named keys, integer keys are tried first."""
        from comfyui.workflow import _normalize_link
        link = {
            0: 1, 1: 10, 2: 0, 3: 20, 4: 1, 5: 'MODEL',
            'id': 99, 'origin_id': 999, 'target_id': 888,
        }
        result = _normalize_link(link)
        # Integer keys should be used since they're checked first
        assert result[0] == 1
        assert result[1] == 10


class TestExtractWidgetNamesFromNode:
    """Tests for _extract_widget_names_from_node() — extract widget names from node inputs."""

    def test_basic_extraction(self):
        """Node with matching widget count extracts names correctly."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {
            'inputs': [
                {'name': 'model', 'link': 1},
                {'name': 'seed', 'widget': {'name': 'seed'}},
                {'name': 'steps', 'widget': {'name': 'steps'}},
            ],
            'widgets_values': [42, 20],
        }
        result = _extract_widget_names_from_node(node)
        assert result == ['seed', 'steps']

    def test_no_inputs_returns_none(self):
        """Node with no inputs returns None."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {'inputs': [], 'widgets_values': [1, 2]}
        assert _extract_widget_names_from_node(node) is None

    def test_no_widgets_values_returns_none(self):
        """Node with no widgets_values returns None."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {
            'inputs': [{'name': 'seed', 'widget': {'name': 'seed'}}],
            'widgets_values': [],
        }
        assert _extract_widget_names_from_node(node) is None

    def test_count_match(self):
        """When base widget count matches widgets_values length, returns base names."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {
            'inputs': [
                {'name': 'steps', 'widget': {'name': 'steps'}},
                {'name': 'cfg', 'widget': {'name': 'cfg'}},
            ],
            'widgets_values': [20, 7.0],
        }
        result = _extract_widget_names_from_node(node)
        assert result == ['steps', 'cfg']
        assert len(result) == len(node['widgets_values'])

    def test_seed_placeholder(self):
        """Seed widget gets control_after_generate placeholder inserted."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {
            'inputs': [
                {'name': 'seed', 'widget': {'name': 'seed'}},
                {'name': 'steps', 'widget': {'name': 'steps'}},
            ],
            'widgets_values': [42, 'randomize', 20],  # 3 values: seed, control_after_generate, steps
        }
        result = _extract_widget_names_from_node(node)
        assert result == ['seed', None, 'steps']

    def test_noise_seed_placeholder(self):
        """noise_seed widget also gets control_after_generate placeholder."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {
            'inputs': [
                {'name': 'noise_seed', 'widget': {'name': 'noise_seed'}},
                {'name': 'steps', 'widget': {'name': 'steps'}},
            ],
            'widgets_values': [42, 'fixed', 20],
        }
        result = _extract_widget_names_from_node(node)
        assert result == ['noise_seed', None, 'steps']

    def test_count_mismatch_returns_none(self):
        """When neither base nor placeholder count matches, returns None."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {
            'inputs': [
                {'name': 'a', 'widget': {'name': 'a'}},
                {'name': 'b', 'widget': {'name': 'b'}},
            ],
            'widgets_values': [1, 2, 3, 4, 5],  # way more values than widgets
        }
        assert _extract_widget_names_from_node(node) is None

    def test_no_widget_property_returns_none(self):
        """Inputs without widget property have no widget names to extract."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {
            'inputs': [
                {'name': 'model', 'link': 1},  # no widget property
                {'name': 'latent', 'link': 2},
            ],
            'widgets_values': [1, 2],
        }
        assert _extract_widget_names_from_node(node) is None

    def test_widget_without_name(self):
        """Widget dict without 'name' key is skipped."""
        from comfyui.workflow import _extract_widget_names_from_node
        node = {
            'inputs': [
                {'name': 'x', 'widget': {}},  # widget dict but no 'name'
                {'name': 'y', 'widget': {'name': 'y_widget'}},
            ],
            'widgets_values': ['val_y'],
        }
        result = _extract_widget_names_from_node(node)
        assert result == ['y_widget']


class TestBuildSubgraphWidgetMap:
    """Tests for _build_subgraph_widget_map() — build UUID-to-widget-names mapping."""

    def test_basic_mapping(self):
        """Subgraph with inputs produces correct widget name list."""
        from comfyui.workflow import _build_subgraph_widget_map
        wf = {
            'definitions': {
                'subgraphs': [{
                    'id': 'aaaa-bbbb-cccc-dddd',
                    'inputs': [
                        {'name': 'text'},
                        {'name': 'steps'},
                    ],
                }],
            },
        }
        result = _build_subgraph_widget_map(wf)
        assert result == {'aaaa-bbbb-cccc-dddd': ['text', 'steps']}

    def test_no_definitions_returns_empty(self):
        """Workflow without definitions returns empty dict."""
        from comfyui.workflow import _build_subgraph_widget_map
        assert _build_subgraph_widget_map({}) == {}

    def test_no_subgraphs_returns_empty(self):
        """Definitions with empty subgraphs list returns empty dict."""
        from comfyui.workflow import _build_subgraph_widget_map
        wf = {'definitions': {'subgraphs': []}}
        assert _build_subgraph_widget_map(wf) == {}

    def test_multiple_subgraphs(self):
        """Multiple subgraphs each get their own entry."""
        from comfyui.workflow import _build_subgraph_widget_map
        wf = {
            'definitions': {
                'subgraphs': [
                    {'id': 'sg-1', 'inputs': [{'name': 'a'}]},
                    {'id': 'sg-2', 'inputs': [{'name': 'x'}, {'name': 'y'}]},
                ],
            },
        }
        result = _build_subgraph_widget_map(wf)
        assert result == {'sg-1': ['a'], 'sg-2': ['x', 'y']}

    def test_without_id_skipped(self):
        """Subgraph without 'id' is skipped."""
        from comfyui.workflow import _build_subgraph_widget_map
        wf = {
            'definitions': {
                'subgraphs': [
                    {'inputs': [{'name': 'a'}]},  # no id
                ],
            },
        }
        assert _build_subgraph_widget_map(wf) == {}

    def test_without_inputs_skipped(self):
        """Subgraph with id but no inputs produces no entry (empty widget list)."""
        from comfyui.workflow import _build_subgraph_widget_map
        wf = {
            'definitions': {
                'subgraphs': [
                    {'id': 'sg-1', 'inputs': []},
                ],
            },
        }
        # Empty inputs -> no widget_names -> not added
        assert _build_subgraph_widget_map(wf) == {}


class TestGetSubgraphDefinitions:
    """Tests for _get_subgraph_definitions() — get subgraph defs indexed by UUID."""

    def test_uuid_keyed_dict(self):
        """Returns dict with UUID keys mapping to subgraph definitions."""
        from comfyui.workflow import _get_subgraph_definitions
        sg = {'id': 'abc-123', 'name': 'TestSG', 'nodes': []}
        wf = {'definitions': {'subgraphs': [sg]}}
        result = _get_subgraph_definitions(wf)
        assert 'abc-123' in result
        assert result['abc-123'] == sg

    def test_no_definitions_returns_empty(self):
        """Workflow without definitions returns empty dict."""
        from comfyui.workflow import _get_subgraph_definitions
        assert _get_subgraph_definitions({}) == {}

    def test_empty_list_returns_empty(self):
        """Empty subgraphs list returns empty dict."""
        from comfyui.workflow import _get_subgraph_definitions
        wf = {'definitions': {'subgraphs': []}}
        assert _get_subgraph_definitions(wf) == {}

    def test_without_id_skipped(self):
        """Subgraph entry without 'id' is excluded."""
        from comfyui.workflow import _get_subgraph_definitions
        wf = {'definitions': {'subgraphs': [{'name': 'NoID', 'nodes': []}]}}
        assert _get_subgraph_definitions(wf) == {}

    def test_multiple_included(self):
        """Multiple valid subgraphs all included."""
        from comfyui.workflow import _get_subgraph_definitions
        sg1 = {'id': 'id-1', 'name': 'SG1'}
        sg2 = {'id': 'id-2', 'name': 'SG2'}
        wf = {'definitions': {'subgraphs': [sg1, sg2]}}
        result = _get_subgraph_definitions(wf)
        assert len(result) == 2
        assert result['id-1']['name'] == 'SG1'
        assert result['id-2']['name'] == 'SG2'


class TestApplyBoundaryOverrides:
    """Tests for _apply_boundary_overrides() — propagate widget values to internal nodes."""

    def _make_test_data(self, num_targets=1):
        """Create test data for boundary override tests.

        Returns (boundary_input_map, node_id_map, new_nodes).
        Each target node has inputs with slot_index matching the boundary slot.
        """
        boundary_input_map = {}
        node_id_map = {}
        new_nodes = []

        for i in range(num_targets):
            old_id = 100 + i
            new_id = 200 + i
            node_id_map[old_id] = new_id
            new_nodes.append({
                'id': new_id,
                'type': f'InternalNode{i}',
                'inputs': [{'name': f'widget_{i}', 'slot_index': 0}],
            })
            if 0 not in boundary_input_map:
                boundary_input_map[0] = []
            boundary_input_map[0].append((old_id, 0, None))

        return boundary_input_map, node_id_map, new_nodes

    def test_single_target(self):
        """Single target node gets override applied."""
        from comfyui.workflow import _apply_boundary_overrides
        bmap, nmap, nodes = self._make_test_data(1)
        applied = _apply_boundary_overrides('my_widget', 'my_value', 0, bmap, nmap, nodes)
        assert applied == 1
        assert nodes[0]['_input_overrides']['widget_0'] == 'my_value'

    def test_multi_target_regression(self):
        """REGRESSION: Multiple target nodes all get override applied (not just first)."""
        from comfyui.workflow import _apply_boundary_overrides
        bmap, nmap, nodes = self._make_test_data(3)
        applied = _apply_boundary_overrides('my_widget', 'ckpt.safetensors', 0, bmap, nmap, nodes)
        assert applied == 3
        for node in nodes:
            assert '_input_overrides' in node

    def test_no_targets(self):
        """Non-existent slot index returns 0 applied."""
        from comfyui.workflow import _apply_boundary_overrides
        bmap, nmap, nodes = self._make_test_data(1)
        applied = _apply_boundary_overrides('my_widget', 'val', 99, bmap, nmap, nodes)
        assert applied == 0

    def test_unmapped_node_skipped(self):
        """Target node not in node_id_map is skipped."""
        from comfyui.workflow import _apply_boundary_overrides
        boundary_input_map = {0: [(999, 0, None)]}  # node 999 not in map
        node_id_map = {100: 200}
        new_nodes = [{'id': 200, 'inputs': [{'name': 'w', 'slot_index': 0}]}]
        applied = _apply_boundary_overrides('w', 'v', 0, boundary_input_map, node_id_map, new_nodes)
        assert applied == 0

    def test_uses_slot_index_name(self):
        """Override key uses the input's name matching slot_index, not the fallback."""
        from comfyui.workflow import _apply_boundary_overrides
        boundary_input_map = {0: [(100, 0, None)]}
        node_id_map = {100: 200}
        new_nodes = [{'id': 200, 'inputs': [{'name': 'specific_name', 'slot_index': 0}]}]
        _apply_boundary_overrides('fallback_name', 'val', 0, boundary_input_map, node_id_map, new_nodes)
        assert 'specific_name' in new_nodes[0]['_input_overrides']

    def test_uses_fallback_name(self):
        """When no input matches slot_index, uses the fallback widget_name."""
        from comfyui.workflow import _apply_boundary_overrides
        boundary_input_map = {0: [(100, 5, None)]}  # slot 5 doesn't exist
        node_id_map = {100: 200}
        new_nodes = [{'id': 200, 'inputs': [{'name': 'wrong_slot', 'slot_index': 0}]}]
        _apply_boundary_overrides('fallback_name', 'val', 0, boundary_input_map, node_id_map, new_nodes)
        assert 'fallback_name' in new_nodes[0]['_input_overrides']

    def test_creates_dict(self):
        """_input_overrides dict is created if it doesn't exist."""
        from comfyui.workflow import _apply_boundary_overrides
        bmap, nmap, nodes = self._make_test_data(1)
        assert '_input_overrides' not in nodes[0]
        _apply_boundary_overrides('w', 'v', 0, bmap, nmap, nodes)
        assert '_input_overrides' in nodes[0]

    def test_preserves_existing_overrides(self):
        """New overrides don't clobber existing ones."""
        from comfyui.workflow import _apply_boundary_overrides
        bmap, nmap, nodes = self._make_test_data(1)
        nodes[0]['_input_overrides'] = {'existing_key': 'existing_val'}
        _apply_boundary_overrides('w', 'v', 0, bmap, nmap, nodes)
        assert nodes[0]['_input_overrides']['existing_key'] == 'existing_val'


class TestExpandSubgraphs:
    """Tests for expand_subgraphs() — expand subgraph component nodes."""

    def test_no_nodes_unchanged(self):
        """Workflow without 'nodes' key passes through unchanged."""
        from comfyui.workflow import expand_subgraphs
        wf = {'some_key': 'value'}
        result = expand_subgraphs(wf)
        assert result == wf

    def test_no_definitions_unchanged(self):
        """Workflow with nodes but no definitions passes through."""
        from comfyui.workflow import expand_subgraphs
        wf = _make_simple_workflow()
        result = expand_subgraphs(wf)
        assert len(result['nodes']) == len(wf['nodes'])

    def test_no_uuid_instances_unchanged(self):
        """Workflow with definitions but no UUID-typed nodes passes through."""
        from comfyui.workflow import expand_subgraphs
        wf = _make_simple_workflow()
        wf['definitions'] = {'subgraphs': [{'id': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'nodes': []}]}
        result = expand_subgraphs(wf)
        assert len(result['nodes']) == 3

    def test_basic_expansion_adds_internal_nodes(self):
        """Subgraph expansion adds internal nodes from the definition."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(1, sg_uuid, widgets_values=['val1'],
                              inputs=[{'name': 'in1', 'link': None}],
                              outputs=[]),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'in1'}],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'InternalA', 'inputs': [], 'outputs': []},
                        {'id': 11, 'type': 'InternalB', 'inputs': [], 'outputs': []},
                    ],
                    'links': [],
                }],
            },
        }
        result = expand_subgraphs(wf)
        types = [n['type'] for n in result['nodes']]
        assert 'InternalA' in types
        assert 'InternalB' in types

    def test_subgraph_node_removed(self):
        """The original subgraph node is removed after expansion."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(1, sg_uuid,
                              inputs=[{'name': 'in1', 'link': None}],
                              outputs=[]),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'in1'}],
                    'outputs': [],
                    'nodes': [{'id': 10, 'type': 'InternalA', 'inputs': [], 'outputs': []}],
                    'links': [],
                }],
            },
        }
        result = expand_subgraphs(wf)
        node_ids = [n['id'] for n in result['nodes']]
        assert 1 not in node_ids

    def test_internal_node_ids_remapped(self):
        """Internal nodes get new unique IDs (not their original internal IDs)."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(1, sg_uuid,
                              inputs=[{'name': 'in1', 'link': None}],
                              outputs=[]),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'in1'}],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'IntA', 'inputs': [], 'outputs': []},
                    ],
                    'links': [],
                }],
            },
        }
        result = expand_subgraphs(wf)
        # Internal node 10 should be remapped to something > 1 (the max existing)
        assert result['nodes'][0]['id'] != 10
        assert result['nodes'][0]['id'] > 1

    def test_internal_link_ids_remapped(self):
        """Internal links get new unique IDs."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(1, sg_uuid,
                              inputs=[{'name': 'in1', 'link': None}],
                              outputs=[]),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'in1'}],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'IntA', 'inputs': [], 'outputs': [{'links': [100], 'slot_index': 0}]},
                        {'id': 11, 'type': 'IntB', 'inputs': [{'link': 100, 'slot_index': 0}], 'outputs': []},
                    ],
                    'links': [[100, 10, 0, 11, 0, 'DATA']],
                }],
            },
        }
        result = expand_subgraphs(wf)
        # The link should have a remapped ID, not the original 100
        assert len(result['links']) > 0
        link_ids = [l[0] for l in result['links']]
        assert 100 not in link_ids

    def test_boundary_input_links_excluded(self):
        """Internal links from negative (boundary) from_node IDs are excluded from output links."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(1, sg_uuid,
                              inputs=[{'name': 'in1', 'link': None}],
                              outputs=[]),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'in1'}],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'IntA', 'inputs': [{'link': 200, 'slot_index': 0}], 'outputs': []},
                    ],
                    # Boundary link from negative node
                    'links': [[200, -10, 0, 10, 0, 'DATA']],
                }],
            },
        }
        result = expand_subgraphs(wf)
        # The boundary link should NOT appear in the output (it's from a negative node)
        for link in result['links']:
            assert link[1] >= 0  # no negative from_node

    def test_external_input_rewired(self):
        """External link to subgraph input is rewired to the internal target node."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(5, 'SourceNode',
                              outputs=[{'name': 'OUT', 'links': [10], 'slot_index': 0}]),
                _make_ui_node(1, sg_uuid,
                              inputs=[{'name': 'image', 'link': 10}],
                              outputs=[]),
            ],
            'links': [_make_link(10, 5, 0, 1, 0, 'IMAGE')],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'image', 'link': None}],
                    'outputs': [],
                    'nodes': [
                        {'id': 20, 'type': 'InternalTarget', 'inputs': [{'name': 'in', 'slot_index': 0, 'link': None}], 'outputs': []},
                    ],
                    'links': [[300, -10, 0, 20, 0, 'IMAGE']],
                }],
            },
        }
        result = expand_subgraphs(wf)
        # The external link 10 should now point to the remapped internal node
        ext_link = None
        for l in result['links']:
            if l[0] == 10:
                ext_link = l
                break
        assert ext_link is not None
        # Target should be the remapped internal node, not the subgraph node (1)
        assert ext_link[3] != 1

    def test_external_output_rewired(self):
        """External links from subgraph output are rewired to internal source node."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(1, sg_uuid,
                              inputs=[],
                              outputs=[{'name': 'OUT', 'links': [10], 'slot_index': 0}]),
                _make_ui_node(5, 'TargetNode',
                              inputs=[{'name': 'IN', 'link': 10, 'slot_index': 0}]),
            ],
            'links': [_make_link(10, 1, 0, 5, 0, 'IMAGE')],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [],
                    'outputs': [{'name': 'OUT', 'link': 400}],
                    'nodes': [
                        {'id': 30, 'type': 'InternalSource',
                         'inputs': [],
                         'outputs': [{'name': 'OUT', 'links': [], 'slot_index': 0}]},
                    ],
                    'links': [[400, 30, 0, -20, 0, 'IMAGE']],
                }],
            },
        }
        result = expand_subgraphs(wf)
        ext_link = None
        for l in result['links']:
            if l[0] == 10:
                ext_link = l
                break
        assert ext_link is not None
        # Source should now be the remapped internal node, not the subgraph node (1)
        assert ext_link[1] != 1

    def test_widget_propagation_proxy_widgets_list(self):
        """proxyWidgets + list widgets_values correctly set _input_overrides on internal nodes."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(
                    1, sg_uuid,
                    widgets_values=['my_prompt', 20],
                    inputs=[{'name': 'text', 'link': None}, {'name': 'steps', 'link': None}],
                    outputs=[],
                    properties={
                        'proxyWidgets': [['-1', 'text'], ['-1', 'steps']],
                    },
                ),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [
                        {'name': 'text', 'link': None},
                        {'name': 'steps', 'link': None},
                    ],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'CLIPEncode',
                         'inputs': [{'name': 'text', 'slot_index': 0, 'link': None}],
                         'outputs': []},
                        {'id': 11, 'type': 'KSampler',
                         'inputs': [{'name': 'steps', 'slot_index': 0, 'link': None}],
                         'outputs': []},
                    ],
                    'links': [
                        [500, -10, 0, 10, 0, 'STRING'],
                        [501, -10, 1, 11, 0, 'INT'],
                    ],
                }],
            },
        }
        result = expand_subgraphs(wf)
        # Find the expanded internal nodes
        clip_node = None
        ksampler_node = None
        for n in result['nodes']:
            if n['type'] == 'CLIPEncode':
                clip_node = n
            elif n['type'] == 'KSampler':
                ksampler_node = n
        assert clip_node is not None
        assert clip_node.get('_input_overrides', {}).get('text') == 'my_prompt'
        assert ksampler_node is not None
        assert ksampler_node.get('_input_overrides', {}).get('steps') == 20

    def test_widget_propagation_no_proxy_widgets_list(self):
        """Without proxyWidgets, list widgets_values are mapped via subgraph input definitions."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(
                    1, sg_uuid,
                    widgets_values=['prompt_val'],
                    inputs=[{'name': 'text', 'link': None}],
                    outputs=[],
                ),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'text', 'link': None}],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'CLIPEncode',
                         'inputs': [{'name': 'text', 'slot_index': 0, 'link': None}],
                         'outputs': []},
                    ],
                    'links': [[500, -10, 0, 10, 0, 'STRING']],
                }],
            },
        }
        result = expand_subgraphs(wf)
        clip_node = [n for n in result['nodes'] if n['type'] == 'CLIPEncode'][0]
        assert clip_node.get('_input_overrides', {}).get('text') == 'prompt_val'

    def test_widget_propagation_proxy_widgets_dict(self):
        """proxyWidgets + dict widgets_values correctly propagate to internal nodes."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(
                    1, sg_uuid,
                    widgets_values={'text': 'dict_prompt', 'steps': 30},
                    inputs=[{'name': 'text', 'link': None}, {'name': 'steps', 'link': None}],
                    outputs=[],
                    properties={
                        'proxyWidgets': [['10', 'text'], ['11', 'steps']],
                    },
                ),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [
                        {'name': 'text', 'link': None},
                        {'name': 'steps', 'link': None},
                    ],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'CLIPEncode', 'inputs': [], 'outputs': []},
                        {'id': 11, 'type': 'KSampler', 'inputs': [], 'outputs': []},
                    ],
                    'links': [],
                }],
            },
        }
        result = expand_subgraphs(wf)
        clip = [n for n in result['nodes'] if n['type'] == 'CLIPEncode'][0]
        ksampler = [n for n in result['nodes'] if n['type'] == 'KSampler'][0]
        assert clip.get('_input_overrides', {}).get('text') == 'dict_prompt'
        assert ksampler.get('_input_overrides', {}).get('steps') == 30

    def test_widget_propagation_no_proxy_widgets_dict(self):
        """Dict widgets_values without proxyWidgets are broadcast to all internal nodes."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(
                    1, sg_uuid,
                    widgets_values={'text': 'broadcast_val'},
                    inputs=[{'name': 'text', 'link': None}],
                    outputs=[],
                ),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'text', 'link': None}],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'InternalA', 'inputs': [], 'outputs': []},
                        {'id': 11, 'type': 'InternalB', 'inputs': [], 'outputs': []},
                    ],
                    'links': [],
                }],
            },
        }
        result = expand_subgraphs(wf)
        for n in result['nodes']:
            overrides = n.get('_input_overrides', {})
            assert overrides.get('text') == 'broadcast_val'

    def test_multi_target_boundary_propagation(self):
        """REGRESSION: Boundary input fanning out to multiple internal nodes overrides all targets."""
        from comfyui.workflow import expand_subgraphs
        sg_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        wf = {
            'nodes': [
                _make_ui_node(
                    1, sg_uuid,
                    widgets_values=['model.safetensors'],
                    inputs=[{'name': 'ckpt_name', 'link': None}],
                    outputs=[],
                ),
            ],
            'links': [],
            'definitions': {
                'subgraphs': [{
                    'id': sg_uuid,
                    'inputs': [{'name': 'ckpt_name', 'link': None}],
                    'outputs': [],
                    'nodes': [
                        {'id': 10, 'type': 'LoaderA', 'inputs': [{'name': 'ckpt_name', 'slot_index': 0, 'link': None}], 'outputs': []},
                        {'id': 11, 'type': 'LoaderB', 'inputs': [{'name': 'ckpt_name', 'slot_index': 0, 'link': None}], 'outputs': []},
                        {'id': 12, 'type': 'LoaderC', 'inputs': [{'name': 'ckpt_name', 'slot_index': 0, 'link': None}], 'outputs': []},
                    ],
                    'links': [
                        [600, -10, 0, 10, 0, 'COMBO'],
                        [601, -10, 0, 11, 0, 'COMBO'],
                        [602, -10, 0, 12, 0, 'COMBO'],
                    ],
                }],
            },
        }
        result = expand_subgraphs(wf)
        overridden_count = 0
        for n in result['nodes']:
            overrides = n.get('_input_overrides', {})
            if overrides.get('ckpt_name') == 'model.safetensors':
                overridden_count += 1
        assert overridden_count == 3


class TestExpandSubgraphsRealWorkflows:
    """Integration tests for expand_subgraphs() using real workflow files."""

    def test_layered_control_expands(self):
        """image_qwen_image_layered_control.json expands without error."""
        from comfyui.workflow import expand_subgraphs
        wf = _load_test_workflow('image_qwen_image_layered_control.json')
        result = expand_subgraphs(wf)
        # Subgraph node should be removed
        node_types = [n.get('type') for n in result['nodes']]
        assert 'f754a936-daaf-4b6e-9658-41fdc54d301d' not in node_types
        # Internal nodes should be present
        assert 'KSampler' in node_types
        assert 'UNETLoader' in node_types

    def test_ltx2_video_expands(self):
        """video_ltx2_i2v.json expands, adding 67+ internal nodes."""
        from comfyui.workflow import expand_subgraphs
        wf = _load_test_workflow('video_ltx2_i2v.json')
        original_count = len(wf.get('nodes', []))
        result = expand_subgraphs(wf)
        expanded_count = len(result['nodes'])
        # Should have significantly more nodes after expansion
        assert expanded_count > original_count

    def test_qwen_edit_active_subgraph_expands(self):
        """image_qwen_image_edit_2511.json: the active subgraph (89) expands."""
        from comfyui.workflow import expand_subgraphs, _is_uuid, MODE_ALWAYS
        wf = _load_test_workflow('image_qwen_image_edit_2511.json')
        result = expand_subgraphs(wf)
        # Every UUID node that survives expansion must be one that was
        # deliberately held back (muted/bypassed), never an active one.
        for n in result['nodes']:
            if _is_uuid(n.get('type', '')):
                assert n.get('mode', MODE_ALWAYS) != MODE_ALWAYS, (
                    f"Active subgraph node {n.get('id')} was not expanded"
                )

    def test_qwen_edit_bypassed_subgraph_not_expanded(self):
        """A bypassed subgraph node is left intact, not spliced into the graph.

        Fixture node 91 has mode=4. Expanding it would inject its internals
        carrying their own active modes, so the whole group would execute
        despite the artist having switched it off.
        """
        from comfyui.workflow import expand_subgraphs, MODE_BYPASSED
        wf = _load_test_workflow('image_qwen_image_edit_2511.json')
        bypassed_type = next(
            n['type'] for n in wf['nodes'] if n.get('id') == 91
        )
        result = expand_subgraphs(wf)

        survivor = [n for n in result['nodes'] if n.get('id') == 91]
        assert len(survivor) == 1, "Bypassed subgraph wrapper should survive expansion"
        assert survivor[0]['type'] == bypassed_type
        assert survivor[0].get('mode') == MODE_BYPASSED

    def test_qwen_edit_bypassed_subgraph_absent_from_api(self):
        """The bypassed subgraph and its internals never reach the API workflow."""
        from comfyui.workflow import convert_to_api_format
        wf = _load_test_workflow('image_qwen_image_edit_2511.json')
        api = convert_to_api_format(wf)
        # The wrapper itself is skipped like any other bypassed node...
        assert '91' not in api
        # ...and no node in the output is a raw UUID class_type
        for node_id, data in api.items():
            ct = data.get('class_type') or ''
            assert len(ct) != 36 or '-' not in ct, (
                f"Subgraph UUID leaked into API workflow as node {node_id}: {ct}"
            )

    def test_no_subgraph_workflow_unchanged(self):
        """audio_stable_audio.json has no subgraphs — passes through unchanged."""
        from comfyui.workflow import expand_subgraphs
        wf = _load_test_workflow('audio_stable_audio.json')
        original_count = len(wf.get('nodes', []))
        result = expand_subgraphs(wf)
        assert len(result['nodes']) == original_count

    def test_expanded_node_count(self):
        """Node count increases after expansion of a subgraph workflow."""
        from comfyui.workflow import expand_subgraphs
        wf = _load_test_workflow('image_qwen_image_layered_control.json')
        original_count = len(wf.get('nodes', []))
        result = expand_subgraphs(wf)
        expanded_count = len(result['nodes'])
        # Should have more nodes after expansion (original had 6, subgraph has ~15 internal)
        assert expanded_count > original_count


class TestConvertToApiFormat:
    """Tests for convert_to_api_format() — UI->API format conversion.

    Most tests mock comfyui.node_info.get_widget_names to return None (forces fallback).
    """

    def _mock_get_widget_names(self, return_value=None):
        """Return a mock patcher for node_info.get_widget_names."""
        from unittest.mock import patch
        return patch('comfyui.node_info.get_widget_names', return_value=return_value)

    def test_already_api_unchanged(self):
        """API-format workflow passes through unchanged."""
        from comfyui.workflow import convert_to_api_format
        wf = {'1': {'class_type': 'KSampler', 'inputs': {'seed': 42}}}
        result = convert_to_api_format(wf)
        assert result == wf

    def test_basic_conversion(self):
        """Simple workflow converts to API format with correct structure."""
        from comfyui.workflow import convert_to_api_format
        wf = _make_simple_workflow()
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert '1' in result
        assert '2' in result
        assert '3' in result
        assert result['1']['class_type'] == 'CheckpointLoaderSimple'

    def test_string_keys(self):
        """All node IDs in API format are strings."""
        from comfyui.workflow import convert_to_api_format
        wf = _make_simple_workflow()
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        for key in result:
            assert isinstance(key, str)

    def test_class_type_preserved(self):
        """Node class_type is preserved in conversion."""
        from comfyui.workflow import convert_to_api_format
        wf = _make_simple_workflow()
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert result['2']['class_type'] == 'KSampler'

    def test_link_becomes_reference(self):
        """Connected input becomes [str(node_id), slot_index] reference."""
        from comfyui.workflow import convert_to_api_format
        wf = _make_simple_workflow()
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        # KSampler's 'model' input is linked from node 1 slot 0
        model_input = result['2']['inputs']['model']
        assert isinstance(model_input, list)
        assert model_input == ['1', 0]

    def test_widget_values_mapped_by_name(self):
        """Widget values are mapped to inputs by widget name."""
        from comfyui.workflow import convert_to_api_format
        # SaveImage has manual mapping: ['filename_prefix']
        wf = {
            'nodes': [
                _make_ui_node(1, 'SaveImage',
                              widgets_values=['my_output'],
                              inputs=[
                                  {'name': 'images', 'link': None},
                                  {'name': 'filename_prefix', 'widget': {'name': 'filename_prefix'}, 'link': None},
                              ]),
            ],
            'links': [],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert result['1']['inputs']['filename_prefix'] == 'my_output'

    def test_dict_format_widgets(self):
        """Dict-format widgets_values are applied as key-value inputs."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, 'CustomNode',
                              widgets_values={'param_a': 10, 'param_b': 'hello'},
                              inputs=[]),
            ],
            'links': [],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert result['1']['inputs']['param_a'] == 10
        assert result['1']['inputs']['param_b'] == 'hello'

    def test_dict_skips_videopreview_audiopreview(self):
        """Dict widgets skip 'videopreview' and 'audiopreview' keys."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, 'CustomNode',
                              widgets_values={
                                  'param_a': 10,
                                  'videopreview': {'hidden': False},
                                  'audiopreview': {'some': 'data'},
                              },
                              inputs=[]),
            ],
            'links': [],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert 'videopreview' not in result['1']['inputs']
        assert 'audiopreview' not in result['1']['inputs']
        assert result['1']['inputs']['param_a'] == 10

    def test_linked_inputs_not_overwritten_by_widgets(self):
        """Widget values don't overwrite inputs that are already connected via links."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(5, 'SourceNode', outputs=[{'name': 'OUT', 'links': [1], 'slot_index': 0}]),
                _make_ui_node(1, 'KSampler',
                              widgets_values=[42, 'randomize', 20, 7.0, 'euler', 'normal', 1.0],
                              inputs=[
                                  {'name': 'model', 'link': 1, 'slot_index': 0},
                                  {'name': 'seed', 'widget': {'name': 'seed'}, 'link': None},
                                  {'name': 'steps', 'widget': {'name': 'steps'}, 'link': None},
                                  {'name': 'cfg', 'widget': {'name': 'cfg'}, 'link': None},
                                  {'name': 'sampler_name', 'widget': {'name': 'sampler_name'}, 'link': None},
                                  {'name': 'scheduler', 'widget': {'name': 'scheduler'}, 'link': None},
                                  {'name': 'denoise', 'widget': {'name': 'denoise'}, 'link': None},
                              ],
                              outputs=[]),
            ],
            'links': [_make_link(1, 5, 0, 1, 0, 'MODEL')],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        # 'model' should be a link reference, not a widget value
        model_input = result['1']['inputs']['model']
        assert isinstance(model_input, list)
        assert model_input == ['5', 0]

    def test_bypassed_node_skipped(self):
        """Node with mode=4 (bypass) is excluded from API output."""
        from comfyui.workflow import convert_to_api_format
        wf = _make_bypassed_node_workflow()
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert '2' not in result  # Bypassed node excluded

    def test_muted_node_skipped(self):
        """Node with mode=2 (mute) is excluded from API output."""
        from comfyui.workflow import convert_to_api_format
        wf = _make_simple_workflow()
        wf['nodes'][1]['mode'] = 2  # Mute KSampler
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert '2' not in result

    def test_bypassed_node_link_resolved_upstream(self):
        """Link through a bypassed node resolves to the upstream active node."""
        from comfyui.workflow import convert_to_api_format
        wf = _make_bypassed_node_workflow()
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        # Node 3's input should resolve through bypassed node 2 to node 1
        c_in = result['3']['inputs'].get('c_in')
        assert c_in is not None
        assert c_in == ['1', 0]

    def test_chained_bypassed_nodes_resolved(self):
        """Links through consecutive bypassed nodes resolve to the upstream node."""
        from comfyui.workflow import convert_to_api_format
        wf = _make_chained_bypassed_workflow()
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        # Node 4's input should resolve through bypassed nodes 3 and 2 to node 1
        d_in = result['4']['inputs'].get('d_in')
        assert d_in is not None
        assert d_in == ['1', 0]

    def test_muted_node_severs_the_link(self):
        """A MUTED node does NOT pass data through — the downstream input is dropped.

        This is the behaviour that distinguishes mute from bypass. Treating the
        two the same means muting a node to cut a branch silently leaves the
        branch wired, which is the opposite of what the artist asked for.
        """
        from comfyui.workflow import convert_to_api_format
        wf = _make_bypassed_node_workflow()
        wf['nodes'][1]['mode'] = 2  # mute node 2 instead of bypassing it
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert '2' not in result
        assert 'c_in' not in result['3']['inputs'], (
            "muted node must sever the link, not pass it through"
        )

    def test_bypass_matches_input_to_output_by_type(self):
        """Bypass picks the type-compatible input, not the same-numbered slot."""
        from comfyui.workflow import convert_to_api_format
        nodes = [
            _make_ui_node(1, 'LatentSource', widgets_values=[],
                          outputs=[{'name': 'LATENT', 'type': 'LATENT',
                                    'links': [1], 'slot_index': 0}]),
            _make_ui_node(2, 'ImageSource', widgets_values=[],
                          outputs=[{'name': 'IMAGE', 'type': 'IMAGE',
                                    'links': [2], 'slot_index': 0}]),
            # Bypassed: inputs are [LATENT, IMAGE] but the single output is IMAGE.
            # Positional matching would wrongly wire output 0 to the LATENT input.
            _make_ui_node(3, 'Mixer', mode=4, widgets_values=[],
                          inputs=[{'name': 'samples', 'type': 'LATENT',
                                   'link': 1, 'slot_index': 0},
                                  {'name': 'image', 'type': 'IMAGE',
                                   'link': 2, 'slot_index': 1}],
                          outputs=[{'name': 'IMAGE', 'type': 'IMAGE',
                                    'links': [3], 'slot_index': 0}]),
            _make_ui_node(4, 'Sink', widgets_values=[],
                          inputs=[{'name': 'image', 'type': 'IMAGE',
                                   'link': 3, 'slot_index': 0}]),
        ]
        links = [
            [1, 1, 0, 3, 0, 'LATENT'],
            [2, 2, 0, 3, 1, 'IMAGE'],
            [3, 3, 0, 4, 0, 'IMAGE'],
        ]
        with self._mock_get_widget_names():
            result = convert_to_api_format({'nodes': nodes, 'links': links})
        assert '3' not in result
        # Must resolve to the IMAGE producer (node 2), not the LATENT one (node 1)
        assert result['4']['inputs']['image'] == ['2', 0]

    def test_bypass_drops_link_with_no_compatible_input(self):
        """An output with no type-compatible input yields no connection."""
        from comfyui.workflow import convert_to_api_format
        nodes = [
            _make_ui_node(1, 'LatentSource', widgets_values=[],
                          outputs=[{'name': 'LATENT', 'type': 'LATENT',
                                    'links': [1], 'slot_index': 0}]),
            # VAEDecode-shaped: LATENT in, IMAGE out. Bypassing it can produce
            # nothing sensible, so ComfyUI drops the connection entirely.
            _make_ui_node(2, 'VAEDecode', mode=4, widgets_values=[],
                          inputs=[{'name': 'samples', 'type': 'LATENT',
                                   'link': 1, 'slot_index': 0}],
                          outputs=[{'name': 'IMAGE', 'type': 'IMAGE',
                                    'links': [2], 'slot_index': 0}]),
            _make_ui_node(3, 'SaveImage', widgets_values=['out'],
                          inputs=[{'name': 'images', 'type': 'IMAGE',
                                   'link': 2, 'slot_index': 0}]),
        ]
        links = [
            [1, 1, 0, 2, 0, 'LATENT'],
            [2, 2, 0, 3, 0, 'IMAGE'],
        ]
        with self._mock_get_widget_names():
            result = convert_to_api_format({'nodes': nodes, 'links': links})
        assert '2' not in result
        assert 'images' not in result['3']['inputs'], (
            "a LATENT source must not be wired into an IMAGE input"
        )

    def test_skip_node_types_excluded(self):
        """Nodes in SKIP_NODE_TYPES are excluded from API output."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, 'Reroute', inputs=[], outputs=[]),
                _make_ui_node(2, 'Note', inputs=[], outputs=[]),
                _make_ui_node(3, 'SaveImage', widgets_values=['out'],
                              inputs=[{'name': 'filename_prefix', 'widget': {'name': 'filename_prefix'}, 'link': None}]),
            ],
            'links': [],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert '1' not in result  # Reroute skipped
        assert '2' not in result  # Note skipped
        assert '3' in result      # SaveImage kept

    def test_none_type_excluded(self):
        """Nodes with type=None are excluded from API output."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, None, inputs=[], outputs=[]),
                _make_ui_node(2, 'SaveImage', widgets_values=['out'],
                              inputs=[{'name': 'filename_prefix', 'widget': {'name': 'filename_prefix'}, 'link': None}]),
            ],
            'links': [],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert '1' not in result
        assert '2' in result

    def test_title_in_meta(self):
        """Node with title gets _meta.title in API output."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, 'SaveImage', title='My Custom Title',
                              widgets_values=['out'],
                              inputs=[{'name': 'filename_prefix', 'widget': {'name': 'filename_prefix'}, 'link': None}]),
            ],
            'links': [],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert result['1']['_meta']['title'] == 'My Custom Title'

    def test_no_title_no_meta(self):
        """Node without title has no _meta key."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, 'SaveImage', widgets_values=['out'],
                              inputs=[{'name': 'filename_prefix', 'widget': {'name': 'filename_prefix'}, 'link': None}]),
            ],
            'links': [],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert '_meta' not in result['1']

    def test_invalid_link_references_removed(self):
        """Input references to non-existent nodes are removed in final validation."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, 'NodeA',
                              inputs=[{'name': 'in1', 'link': 1, 'slot_index': 0}],
                              outputs=[]),
                # Node 99 doesn't exist but link points to it
            ],
            'links': [_make_link(1, 99, 0, 1, 0, 'DATA')],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        # The invalid link should be skipped during build (from_node 99 not valid)
        assert 'in1' not in result.get('1', {}).get('inputs', {})

    def test_node_info_fallback(self):
        """When node_info returns widget names, they are used for mapping."""
        from comfyui.workflow import convert_to_api_format
        from unittest.mock import patch
        wf = {
            'nodes': [
                _make_ui_node(1, 'CustomNodeX',
                              widgets_values=['val_a', 'val_b'],
                              inputs=[
                                  {'name': 'param_a', 'widget': {'name': 'param_a'}, 'link': None},
                                  {'name': 'param_b', 'widget': {'name': 'param_b'}, 'link': None},
                              ]),
            ],
            'links': [],
        }
        # Node info returns the names — so auto-extract from inputs should work first
        # but if inputs didn't have widget info, node_info would be the fallback
        with patch('comfyui.node_info.get_widget_names', return_value=['param_a', 'param_b']):
            result = convert_to_api_format(wf)
        assert result['1']['inputs']['param_a'] == 'val_a'
        assert result['1']['inputs']['param_b'] == 'val_b'

    def test_widget_mappings_fallback(self):
        """WIDGET_MAPPINGS is used when both auto-extract and node_info fail."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, 'SaveImage',
                              widgets_values=['my_prefix'],
                              # No widget property in inputs, so auto-extract fails
                              inputs=[{'name': 'images', 'link': None}]),
            ],
            'links': [],
        }
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        # Should fall through to WIDGET_MAPPINGS which has SaveImage: ['filename_prefix']
        assert result['1']['inputs'].get('filename_prefix') == 'my_prefix'

    def test_override_replaces_stale_widget_default(self):
        """REGRESSION: _input_overrides replace stale widget defaults from subgraph definition."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(1, 'CustomNode',
                              widgets_values={'param': 'stale_default'},
                              inputs=[]),
            ],
            'links': [],
        }
        wf['nodes'][0]['_input_overrides'] = {'param': 'fresh_override'}
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert result['1']['inputs']['param'] == 'fresh_override'

    def test_override_does_not_replace_link_reference(self):
        """REGRESSION: _input_overrides must NOT replace link connection references."""
        from comfyui.workflow import convert_to_api_format
        wf = {
            'nodes': [
                _make_ui_node(5, 'SourceNode', outputs=[{'name': 'OUT', 'links': [1], 'slot_index': 0}]),
                _make_ui_node(1, 'TargetNode',
                              widgets_values={'model': 'stale_model.safetensors'},
                              inputs=[{'name': 'model', 'link': 1, 'slot_index': 0}]),
            ],
            'links': [_make_link(1, 5, 0, 1, 0, 'MODEL')],
        }
        wf['nodes'][1]['_input_overrides'] = {'model': 'override_model.safetensors'}
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        # 'model' should remain as link reference, not be overridden
        model_input = result['1']['inputs']['model']
        assert isinstance(model_input, list)
        assert model_input == ['5', 0]


class TestConvertRealWorkflows:
    """End-to-end conversion tests using real workflow files."""

    def _mock_get_widget_names(self, return_value=None):
        """Return a mock patcher for node_info.get_widget_names."""
        from unittest.mock import patch
        return patch('comfyui.node_info.get_widget_names', return_value=return_value)

    def test_simple_audio_converts(self):
        """audio_stable_audio.json converts and all nodes have class_type."""
        from comfyui.workflow import convert_to_api_format
        wf = _load_test_workflow('audio_stable_audio.json')
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert len(result) > 0
        for node_id, node_data in result.items():
            assert 'class_type' in node_data
            assert 'inputs' in node_data

    def test_dict_format_converts(self):
        """mmaudio.json converts correctly with dict widgets."""
        from comfyui.workflow import convert_to_api_format
        wf = _load_test_workflow('mmaudio.json')
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert len(result) > 0
        for node_data in result.values():
            assert 'class_type' in node_data

    def test_subgraph_workflow_converts(self):
        """image_qwen_image_layered_control.json expands and converts."""
        from comfyui.workflow import convert_to_api_format
        wf = _load_test_workflow('image_qwen_image_layered_control.json')
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        assert len(result) > 0
        # Should have KSampler from expanded subgraph
        class_types = [n['class_type'] for n in result.values()]
        assert 'KSampler' in class_types

    def test_large_subgraph_converts(self):
        """video_ltx2_i2v.json full pipeline — no subgraph UUIDs in output class_types."""
        from comfyui.workflow import convert_to_api_format, _is_uuid
        wf = _load_test_workflow('video_ltx2_i2v.json')
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        for node_data in result.values():
            ct = node_data.get('class_type', '')
            assert not _is_uuid(ct), f"UUID class_type still present: {ct}"

    def test_dual_subgraph_converts(self):
        """image_qwen_image_edit_2511.json — both subgraphs expanded and converted."""
        from comfyui.workflow import convert_to_api_format, _is_uuid
        wf = _load_test_workflow('image_qwen_image_edit_2511.json')
        with self._mock_get_widget_names():
            result = convert_to_api_format(wf)
        for node_data in result.values():
            ct = node_data.get('class_type', '')
            assert not _is_uuid(ct), f"UUID class_type still present: {ct}"

    def test_all_workflows_convert_without_error(self):
        """All test workflow files convert without raising exceptions."""
        from comfyui.workflow import convert_to_api_format
        for name in ALL_WORKFLOW_FILES:
            wf = _load_test_workflow(name)
            with self._mock_get_widget_names():
                result = convert_to_api_format(wf)
            assert isinstance(result, dict), f"Failed on {name}"
            assert len(result) > 0, f"Empty result for {name}"


class TestLoadAndSaveWorkflow:
    """Tests for load_workflow() and save_workflow() file I/O."""

    def test_load_valid_workflow(self):
        """load_workflow reads and parses a JSON file."""
        import tempfile
        import json
        from comfyui.workflow import load_workflow

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'test.json')
            data = {'nodes': [{'id': 1}], 'links': []}
            with open(path, 'w') as f:
                json.dump(data, f)
            result = load_workflow(path)
            assert result == data

    def test_load_nonexistent_returns_empty(self):
        """load_workflow on non-existent file returns empty dict."""
        from comfyui.workflow import load_workflow
        result = load_workflow('/nonexistent/path/workflow.json')
        assert result == {}

    def test_load_invalid_json_returns_empty(self):
        """load_workflow on invalid JSON returns empty dict."""
        import tempfile
        from comfyui.workflow import load_workflow

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'bad.json')
            with open(path, 'w') as f:
                f.write('{not valid json!!!}')
            result = load_workflow(path)
            assert result == {}

    def test_save_creates_file(self):
        """save_workflow creates a file in the output directory."""
        import tempfile
        from comfyui.workflow import save_workflow

        with tempfile.TemporaryDirectory() as tmpdir:
            wf = {'nodes': [], 'links': []}
            path = save_workflow(wf, tmpdir, job_id='test_job')
            assert os.path.isfile(path)
            assert 'test_job' in os.path.basename(path)

    def test_roundtrip_identity(self):
        """Saving and loading a workflow produces the same data."""
        import tempfile
        import json
        from comfyui.workflow import load_workflow, save_workflow

        with tempfile.TemporaryDirectory() as tmpdir:
            original = {'nodes': [{'id': 1, 'type': 'Test'}], 'links': [[1, 1, 0, 2, 0, '*']]}
            path = save_workflow(original, tmpdir, job_id='roundtrip')
            loaded = load_workflow(path)
            assert loaded == original

    def test_save_creates_directory(self):
        """save_workflow creates the output directory if it doesn't exist."""
        import tempfile
        from comfyui.workflow import save_workflow

        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, 'nested', 'deep')
            wf = {'nodes': []}
            path = save_workflow(wf, subdir, job_id='dir_test')
            assert os.path.isfile(path)

    def test_save_with_custom_job_id(self):
        """save_workflow uses the provided job_id in the filename."""
        import tempfile
        from comfyui.workflow import save_workflow

        with tempfile.TemporaryDirectory() as tmpdir:
            wf = {'nodes': []}
            path = save_workflow(wf, tmpdir, job_id='custom_id_123')
            assert 'custom_id_123' in os.path.basename(path)

    def test_save_generates_unique_job_id(self):
        """save_workflow generates a unique job_id when none provided."""
        import tempfile
        from comfyui.workflow import save_workflow

        with tempfile.TemporaryDirectory() as tmpdir:
            wf = {'nodes': []}
            path1 = save_workflow(wf, tmpdir)
            path2 = save_workflow(wf, tmpdir)
            # Two saves should produce different filenames
            assert path1 != path2


class TestLoadRealWorkflow:
    """Tests for loading real workflow files with load_workflow()."""

    def test_load_real_workflow(self):
        """load_workflow() on a real test file returns non-empty dict with 'nodes' key."""
        from comfyui.workflow import load_workflow
        path = os.path.join(WORKFLOWS_DIR, 'audio_stable_audio.json')
        result = load_workflow(path)
        assert isinstance(result, dict)
        assert len(result) > 0
        assert 'nodes' in result

    def test_load_all_test_workflows(self):
        """All test workflow files load successfully."""
        from comfyui.workflow import load_workflow
        for name in ALL_WORKFLOW_FILES:
            path = os.path.join(WORKFLOWS_DIR, name)
            result = load_workflow(path)
            assert isinstance(result, dict), f"Failed to load {name}"
            assert len(result) > 0, f"Empty result for {name}"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
