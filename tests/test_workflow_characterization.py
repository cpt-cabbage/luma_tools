"""Golden-output characterization tests for the ComfyUI workflow pipeline.

These are NOT behaviour specifications — they are a safety net.  Every case
runs one of the three hot-path functions

    comfyui.workflow.expand_subgraphs
    comfyui.workflow.convert_to_api_format
    comfyui.modifier.modify_workflow_api_format

against a fixture workflow, serialises the result canonically (sorted keys),
and compares it byte-for-byte against a committed golden file under
``tests/fixtures/golden/``.

Every ComfyUI farm job goes through these functions, and a silent behavioural
change only surfaces after a full Deadline round-trip.  The goldens exist so
that refactoring them cannot change what gets submitted.

**Do NOT regenerate the goldens to make a failing test pass.**  A golden diff
means behaviour changed; investigate the diff instead.  Regeneration is only
legitimate when a behaviour change is *intended* and reviewed, via::

    powershell -ExecutionPolicy Bypass -File _regen_goldens.ps1
    # (equivalent to: PYTHONPATH=python python tests/test_workflow_characterization.py --regen)

Fixtures
--------
* ``tests/workflows/`` — real production workflows already committed to the
  repo (the same files that live in the studio's central workflow directory).
  They cover subgraphs with proxyWidgets, muted nodes, dict widgets_values and
  plain linear graphs.
* ``tests/fixtures/workflows/`` — small hand-authored workflows covering the
  documented invariants that no real workflow happens to exercise: boundary
  fan-out, all three widget-propagation paths, nested subgraphs, bypassed
  nodes, and unresolvable links through skipped nodes.

Neither directory touches the network share.

Determinism
-----------
``comfyui.node_info`` caches widget metadata scraped from a live ComfyUI
server, so its contents differ per machine.  Every case runs with
``get_widget_names``/``get_required_input_names`` patched to return ``None``,
forcing the deterministic in-repo fallbacks (WIDGET_MAPPINGS / "assume
required").
"""
import json
import os
import sys
from contextlib import contextmanager
from unittest.mock import patch

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(TESTS_DIR), 'python'))

REAL_WORKFLOWS_DIR = os.path.join(TESTS_DIR, 'workflows')
SYNTHETIC_WORKFLOWS_DIR = os.path.join(TESTS_DIR, 'fixtures', 'workflows')
GOLDEN_DIR = os.path.join(TESTS_DIR, 'fixtures', 'golden')

# Real production workflows (tests/workflows/).  Marked with the structural
# features each one contributes to the coverage of this suite.
REAL_WORKFLOWS = [
    'NormalCrafter_ImageSequence.json',      # dict widgets_values
    'NormalCrafter_Video.json',              # dict widgets_values
    'audio_stable_audio.json',               # plain linear graph
    'audio_ace_step_1_5.json',               # plain, seed node
    'mmaudio.json',                          # dict widgets_values
    'sharp_basic.json',                      # export node with output_prefix
    'image_qwen_image_layered_control.json',  # subgraph, proxyWidgets + list
    'image_qwen_image_edit_2511.json',       # 2 subgraphs + muted (mode=4) nodes
    'image_qwen_image_2512_with_2steps_lora.json',
    'video_ltx2_i2v.json',                   # 41-node subgraph, proxyWidgets
    'Trellis_2.json',                        # 24 nodes, export + output_dir
]

# Real workflows that actually contain subgraph instances
REAL_SUBGRAPH_WORKFLOWS = [
    'image_qwen_image_layered_control.json',
    'image_qwen_image_edit_2511.json',
    'video_ltx2_i2v.json',
]

# Hand-authored fixtures (tests/fixtures/workflows/)
SYNTHETIC_SUBGRAPH_WORKFLOWS = [
    'sg_boundary_fanout.json',   # one boundary input -> 3 internal nodes
    'sg_no_proxy_list.json',     # propagation path 2: no proxyWidgets + list
    'sg_proxy_dict.json',        # propagation path 3: proxyWidgets + dict
    'sg_no_proxy_dict.json',     # dict broadcast, no proxyWidgets
    'sg_nested.json',            # nested subgraph -> recursive expansion
    'sg_external_io.json',       # external in/out rewiring + link minting
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(directory, name):
    """Load a fixture workflow JSON by directory and filename."""
    with open(os.path.join(directory, name), 'r', encoding='utf-8') as f:
        return json.load(f)


def load_real(name):
    """Load a real production workflow from tests/workflows/."""
    return _load(REAL_WORKFLOWS_DIR, name)


def load_synthetic(name):
    """Load a hand-authored workflow from tests/fixtures/workflows/."""
    return _load(SYNTHETIC_WORKFLOWS_DIR, name)


def canonical(obj):
    """Serialise a workflow deterministically: sorted keys, stable indent."""
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False)


@contextmanager
def deterministic_node_info():
    """Force the in-repo fallbacks by emptying the machine-local node_info cache."""
    with patch('comfyui.node_info.get_widget_names', return_value=None), \
            patch('comfyui.node_info.get_required_input_names', return_value=None):
        yield


class StubEditableNode:
    """Minimal stand-in for ``comfyui.editable.EditableNode``.

    ``modify_workflow_api_format`` only ever reads ``node_type``,
    ``widget_type``, ``title`` and (optionally) ``widget_name`` off these
    objects, so a plain attribute holder is a faithful substitute.
    """

    def __init__(self, node_type, widget_type, title=None, widget_name=None):
        self.node_type = node_type
        self.widget_type = widget_type
        self.title = title
        if widget_name is not None:
            self.widget_name = widget_name

    def __repr__(self):
        return f"StubEditableNode({self.node_type!r}, {self.widget_type!r})"


# ---------------------------------------------------------------------------
# Case producers — each returns the JSON-serialisable output to snapshot
# ---------------------------------------------------------------------------

def _case_expand(directory, name):
    """expand_subgraphs() on one fixture."""
    def run():
        from comfyui.workflow import expand_subgraphs
        return expand_subgraphs(_load(directory, name))
    return run


def _case_convert(directory, name):
    """convert_to_api_format() on one fixture."""
    def run():
        from comfyui.workflow import convert_to_api_format
        return convert_to_api_format(_load(directory, name))
    return run


def _editable_values_full():
    """Editable values covering every widget_type branch of the modifier.

    Node ids intentionally mix ``int`` and ``str`` keys, and node 3 carries a
    toggle whose title drives the ``&if_UseUpscale`` conditional removal of
    node 8.
    """
    return {
        2: [{'node': StubEditableNode('TextEncodeQwenImageEditPlus', 'text',
                                      title='Prompt_editable'),
             'value': 'edited prompt text'}],
        '3': [{'node': StubEditableNode('TextEncodeQwenImageEditPlus', 'toggle',
                                        title='UseUpscale_editable'),
               'value': False}],
        4: [
            {'node': StubEditableNode('KSampler', 'int', title='Sampler_editable'),
             'value': 999},
            {'node': StubEditableNode('KSampler', 'float', title='Cfg_editable',
                                      widget_name='cfg'),
             'value': 3.25},
        ],
        7: [{'node': StubEditableNode('SaveImage', 'string', title='Secondary'),
             'value': 'string_widget_prefix'}],
        11: [{'node': StubEditableNode('HYMotionExportFBX', '3d_model',
                                       title='Fbx'),
              'value': ['C:/assets/character.glb']}],
        12: [{'node': StubEditableNode('SamplerCustomAdvanced', 'combo',
                                       title='Advanced', widget_name='sampler_name'),
              'value': 'euler'}],
        13: [{'node': StubEditableNode('LoadImage', 'image',
                                       title='Editable Loader'),
              'value': ['C:/renders/frame.exr']}],
        1: [{'node': StubEditableNode('LoadImage', 'directory',
                                      title='Loader', widget_name='directory'),
             'value': 'C:/renders/seq'}],
        5: [{'node': StubEditableNode('PreviewImage', 'video', title='Preview'),
             'value': ['C:/renders/clip.mov']}],
        # Node id that is absent from the workflow — exercises the
        # "not found" warning branch without changing the output.
        4242: [{'node': StubEditableNode('MissingNode', 'text', title='Ghost'),
                'value': 'never applied'}],
    }


def _case_modify(variant):
    """modify_workflow_api_format() on the API-format modifier fixture.

    variant:
        'full'        — every widget type + toggle-driven node removal
        'legacy'      — no editable values, legacy input_image/prompt path
        'no_output'   — the ``_output`` title suffix stripped, so *all* export
                        nodes receive the prefix and output_dir
    """
    def run():
        from comfyui.modifier import modify_workflow_api_format
        wf = load_synthetic('api_modifier.json')
        if variant == 'no_output':
            for node in wf.values():
                if isinstance(node, dict) and '_meta' in node:
                    node['_meta']['title'] = node['_meta']['title'].replace('_output', '')
        editable = _editable_values_full() if variant == 'full' else None
        modified, found_prompt, files = modify_workflow_api_format(
            workflow=wf,
            input_image='C:/renders/legacy_input.exr' if variant != 'full' else None,
            prompt='legacy prompt' if variant != 'full' else None,
            output_prefix='JOB_prefix',
            seed=4242,
            editable_values=editable,
            output_dir='C:/out/dir',
        )
        return {
            'workflow': modified,
            'found_editable_prompt': found_prompt,
            'files_to_copy': files,
        }
    return run


def _case_convert_then_modify(name):
    """Full UI -> API -> modify pipeline on a real production workflow."""
    def run():
        from comfyui.workflow import convert_to_api_format
        from comfyui.modifier import modify_workflow_api_format
        api = convert_to_api_format(load_real(name))
        modified, found_prompt, files = modify_workflow_api_format(
            workflow=api,
            input_image='input_frame.png',
            prompt='characterization prompt',
            output_prefix='CHAR_prefix',
            seed=13579,
            editable_values=None,
            output_dir='C:/out/dir',
        )
        return {
            'workflow': modified,
            'found_editable_prompt': found_prompt,
            'files_to_copy': files,
        }
    return run


def build_cases():
    """Return an ordered {case_name: producer} mapping for the whole suite."""
    cases = {}

    for name in REAL_SUBGRAPH_WORKFLOWS:
        stem = os.path.splitext(name)[0]
        cases[f'expand__real__{stem}'] = _case_expand(REAL_WORKFLOWS_DIR, name)

    for name in SYNTHETIC_SUBGRAPH_WORKFLOWS:
        stem = os.path.splitext(name)[0]
        cases[f'expand__synth__{stem}'] = _case_expand(SYNTHETIC_WORKFLOWS_DIR, name)

    for name in REAL_WORKFLOWS:
        stem = os.path.splitext(name)[0]
        cases[f'convert__real__{stem}'] = _case_convert(REAL_WORKFLOWS_DIR, name)

    for name in SYNTHETIC_SUBGRAPH_WORKFLOWS + ['muted_bypassed.json']:
        stem = os.path.splitext(name)[0]
        cases[f'convert__synth__{stem}'] = _case_convert(SYNTHETIC_WORKFLOWS_DIR, name)

    for variant in ('full', 'legacy', 'no_output'):
        cases[f'modify__{variant}'] = _case_modify(variant)

    for name in ('image_qwen_image_layered_control.json', 'Trellis_2.json',
                 'sharp_basic.json', 'image_qwen_image_edit_2511.json'):
        stem = os.path.splitext(name)[0]
        cases[f'pipeline__{stem}'] = _case_convert_then_modify(name)

    return cases


CASES = build_cases()


def _golden_path(case_name):
    return os.path.join(GOLDEN_DIR, f'{case_name}.json')


def run_case(case_name):
    """Execute one case under deterministic conditions and canonicalise it."""
    with deterministic_node_info():
        return canonical(CASES[case_name]())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('case_name', sorted(CASES))
def test_matches_golden(case_name):
    """Output is byte-identical to the committed golden snapshot."""
    golden_file = _golden_path(case_name)
    assert os.path.isfile(golden_file), (
        f"Missing golden for '{case_name}'. Goldens are committed data — "
        f"generate with `python tests/test_workflow_characterization.py --regen` "
        f"only when adding a NEW case."
    )
    with open(golden_file, 'r', encoding='utf-8') as f:
        expected = f.read()
    actual = run_case(case_name)
    assert actual == expected, (
        f"Golden mismatch for '{case_name}'. Behaviour changed — investigate "
        f"the diff; do not regenerate the golden to silence this."
    )


@pytest.mark.parametrize('case_name', sorted(CASES))
def test_is_deterministic(case_name):
    """Running the same case twice produces identical output."""
    assert run_case(case_name) == run_case(case_name)


class TestInvariantsAreCovered:
    """Explicit assertions on the invariants documented in comfyui/CLAUDE.md.

    These read the golden output rather than re-deriving it, so they double as
    documentation of *what* each fixture is protecting.
    """

    def _expanded(self, directory, name):
        from comfyui.workflow import expand_subgraphs
        with deterministic_node_info():
            return expand_subgraphs(_load(directory, name))

    def _converted(self, directory, name):
        from comfyui.workflow import convert_to_api_format
        with deterministic_node_info():
            return convert_to_api_format(_load(directory, name))

    def test_boundary_input_fans_out_to_every_internal_node(self):
        """One boundary input -> three internal loaders, all overridden."""
        result = self._expanded(SYNTHETIC_WORKFLOWS_DIR, 'sg_boundary_fanout.json')
        overridden = [n for n in result['nodes']
                      if n.get('_input_overrides', {}).get('ckpt_name') == 'model.safetensors']
        assert len(overridden) == 3
        sampler = [n for n in result['nodes'] if n['type'] == 'SamplerX'][0]
        assert sampler['_input_overrides']['steps'] == 42

    def test_widget_path_proxy_widgets_list(self):
        """Path 1: proxyWidgets + list widgets_values (real workflow)."""
        result = self._expanded(REAL_WORKFLOWS_DIR,
                                'image_qwen_image_layered_control.json')
        assert any('_input_overrides' in n for n in result['nodes'])

    def test_widget_path_no_proxy_widgets_list(self):
        """Path 2: no proxyWidgets, values mapped by subgraph input index."""
        result = self._expanded(SYNTHETIC_WORKFLOWS_DIR, 'sg_no_proxy_list.json')
        by_type = {n['type']: n for n in result['nodes']}
        assert by_type['CLIPTextEncode']['_input_overrides']['text'] == 'prompt text'
        assert by_type['KSampler']['_input_overrides']['cfg'] == 7.5

    def test_widget_path_proxy_widgets_dict(self):
        """Path 3: proxyWidgets + dict widgets_values, phantom widget skipped."""
        result = self._expanded(SYNTHETIC_WORKFLOWS_DIR, 'sg_proxy_dict.json')
        by_type = {n['type']: n for n in result['nodes']}
        assert by_type['KSampler']['_input_overrides']['seed'] == 123
        assert 'control_after_generate' not in by_type['KSampler']['_input_overrides']
        assert (by_type['CheckpointLoaderSimple']['_input_overrides']['ckpt_name']
                == 'dict_model.safetensors')

    def test_dict_without_proxy_widgets_broadcasts(self):
        """Dict values with no proxyWidgets land on every internal node."""
        result = self._expanded(SYNTHETIC_WORKFLOWS_DIR, 'sg_no_proxy_dict.json')
        for node in result['nodes']:
            assert node['_input_overrides']['text'] == 'broadcast'
            assert 'videopreview' not in node['_input_overrides']
            assert 'audiopreview' not in node['_input_overrides']

    def test_nested_subgraphs_fully_expanded(self):
        """Recursion leaves no UUID-typed nodes behind."""
        from comfyui.workflow import _is_uuid
        result = self._expanded(SYNTHETIC_WORKFLOWS_DIR, 'sg_nested.json')
        types = [n.get('type') for n in result['nodes']]
        assert not any(_is_uuid(t) for t in types)
        assert 'LeafNode' in types and 'PlainNode' in types

    def test_external_input_fanout_mints_extra_link(self):
        """Second internal target of an external input gets a brand-new link."""
        result = self._expanded(SYNTHETIC_WORKFLOWS_DIR, 'sg_external_io.json')
        by_type = {n['type']: n for n in result['nodes']}
        consumers = {by_type['ConsumerA']['id'], by_type['ConsumerB']['id']}
        targets = {l[3] for l in result['links'] if l[1] == 5}
        assert consumers == targets, "both consumers must be fed from node 5"

    def test_external_output_rewired_to_internal_producer(self):
        """Both downstream sinks now read from the internal Producer node."""
        result = self._expanded(SYNTHETIC_WORKFLOWS_DIR, 'sg_external_io.json')
        producer_id = [n for n in result['nodes'] if n['type'] == 'Producer'][0]['id']
        for link in result['links']:
            if link[0] in (11, 12):
                assert link[1] == producer_id

    def test_muted_chain_resolves_to_first_active_upstream(self):
        """1 -> [muted 2] -> [muted 3] -> 4 collapses to 1."""
        api = self._converted(SYNTHETIC_WORKFLOWS_DIR, 'muted_bypassed.json')
        assert '2' not in api and '3' not in api
        assert api['4']['inputs']['d_in'] == ['1', 0]

    def test_bypassed_node_without_upstream_drops_the_input(self):
        """A bypassed source with no pass-through removes the downstream input."""
        api = self._converted(SYNTHETIC_WORKFLOWS_DIR, 'muted_bypassed.json')
        assert '5' not in api
        assert 'f_in' not in api['6']['inputs']

    def test_skip_node_types_and_dangling_links(self):
        """Reroute nodes are dropped and links to missing nodes are removed."""
        api = self._converted(SYNTHETIC_WORKFLOWS_DIR, 'muted_bypassed.json')
        assert '7' not in api
        assert 'g_in' not in api['8']['inputs']

    def test_muted_nodes_in_real_workflow_are_dropped(self):
        """image_qwen_image_edit_2511.json ships two mode=4 nodes."""
        source = load_real('image_qwen_image_edit_2511.json')
        muted_ids = {str(n['id']) for n in source['nodes'] if n.get('mode') == 4}
        assert muted_ids, "fixture must contain muted nodes"
        api = self._converted(REAL_WORKFLOWS_DIR, 'image_qwen_image_edit_2511.json')
        assert not (muted_ids & set(api))


# ---------------------------------------------------------------------------
# Golden regeneration (manual, deliberate)
# ---------------------------------------------------------------------------

def _regen():
    """Rewrite every golden file from the current code. Use with care."""
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    for case_name in sorted(CASES):
        content = run_case(case_name)
        with open(_golden_path(case_name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        print(f"wrote {case_name}.json ({len(content)} bytes)")


if __name__ == '__main__':
    if '--regen' in sys.argv:
        _regen()
    else:
        pytest.main([__file__, '-q'])
