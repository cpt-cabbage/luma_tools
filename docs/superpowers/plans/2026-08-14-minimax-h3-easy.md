# MiniMax H3 (ComfyUI-MiniMaxH3-Easy) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let artists run MiniMax H3 video generation (T2V / I2V / R2V with multiple image, video and audio references) from the ComfyUI tab, driven by an API-format workflow exported from the ComfyUI browser.

**Architecture:** Three independent capabilities, none of them H3-specific. (1) `editable.py` learns to read API-format workflows, using `_meta.title` for the `_editable` marker and the `inputs` dict for values — no widget-index arithmetic. (2) A new `*` title marker makes a file selector *fan out*: one selector holding N files expands at submit time into N cloned loader nodes wired to N numbered consumer inputs, by splitting the trailing integer off the consumer's input name and duplicating every sibling input that shares it. (3) An `audio` widget type, matching the existing `video` one. Referencing needs no runtime code at all — `<Picture 1>` / `<Video 1>` / `<Audio 1>` / `<d>…</d>` are literal strings the model consumes directly, so the UI only gains a button that types them for you.

**Tech Stack:** Python 3.10, PySide6, pytest. No new dependencies.

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-08-14-minimax-h3-easy-design.md`.
- Run tests with `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`. `pytest-timeout` is NOT installed — never pass `--timeout`.
- For a single test file: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_editable.py -v` with `PYTHONPATH` set to `<repo>\python;<repo>\resources\ui`.
- `python/comfyui/node_configs.py`, `metadata.py`, `utils.py`, `runner.py`, `analytics.py` are copied to the farm under flat `comfyui_*` names. They must import without the `comfyui` package on `sys.path` — `tests/test_farm_isolation.py` enforces this. Do not add package-relative imports to those files.
- Never use `print()`; every module uses `logger = logging.getLogger(__name__)`.
- Never edit `resources/ui/tabs/_compiled/ui_*.py` — regenerated on deploy.
- Do not update `resources/version.json` or `resources/changelog.md`; the user handles those.
- Existing behaviour must not change for UI-format presets. `_parse_editable_title` keeps its 3-tuple signature (a new function carries the 4th value) so its 10 existing tests and `ui_manager._parse_node_title` are untouched.
- Reference tag literals, exactly: `<Picture N>`, `<Video N>`, `<Audio N>`, `<d>…</d>`. N is the 1-based ordinal **within that media type**.
- Media slot ceiling on `MiniMaxH3Easy`: 15 (`media_1`..`media_15`). Reference-mode limits enforced by the node: 9 images, 3 videos, 3 audio.

---

## Task 0: Farm prerequisites (external — no code)

Not a coding task. Tasks 7 and 9 cannot be verified end-to-end until this is done, but every task's unit tests pass without it.

- [ ] **Step 1: Install the node pack on every worker in the ComfyUI group**

Clone `https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy` into `D:\ComfyUI\ComfyUI\custom_nodes\`.

- [ ] **Step 2: Place the model weights**

| File | Folder |
|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `D:\ComfyUI\ComfyUI\models\diffusion_models\` |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `D:\ComfyUI\ComfyUI\models\diffusion_models\` |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `D:\ComfyUI\ComfyUI\models\text_encoders\` |
| `minimax_h3_video_vae_fp16.safetensors` | `D:\ComfyUI\ComfyUI\models\vae\` |
| `minimax_h3_audio_vae_fp32.safetensors` | `D:\ComfyUI\ComfyUI\models\vae\` |

- [ ] **Step 3: Restart the ComfyUI server job and confirm the node info cache updated**

Use the tab's Stop then Start buttons. Then:

```bash
python -c "
import json, io
d = json.load(io.open(r'W:/LumaRND/luma_tools/_node_info/comfyui_node_info.json', encoding='utf-8'))
print([k for k in d['nodes'] if 'MiniMaxH3Easy' in k])
"
```

Expected: `['MiniMaxH3EasyLoader', 'MiniMaxH3EasyModelAdapter', 'MiniMaxH3Easy', 'MiniMaxH3EasyOutput']`

---

## Task 1: node_info — optional input names and known class types

**Files:**
- Modify: `python/comfyui/node_info.py:57-68` (dataclass), `:248-320` (`_parse_node_info`), `:602-689` (public accessors)
- Test: `tests/test_comfyui_editable.py` (append a new class at the end)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `NodeTypeInfo.optional_input_names: List[str]`
  - `get_optional_input_names(class_type: str) -> Optional[List[str]]` — `None` on cache miss
  - `get_known_class_types() -> Set[str]` — empty set on cache miss

- [ ] **Step 1: Write the failing test**

Append to `tests/test_comfyui_editable.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_editable.py::TestNodeInfoOptionalInputs -v`
Expected: FAIL — `AttributeError: 'NodeTypeInfo' object has no attribute 'optional_input_names'` and `ImportError` for `get_known_class_types`.

- [ ] **Step 3: Add the dataclass field**

In `python/comfyui/node_info.py`, after `required_input_names` (line 68):

```python
    # Names of all optional inputs (both widget and connection inputs).
    # Used to discover the ceiling for numbered slot inputs such as
    # media_1..media_15, which fan-out expansion allocates into.
    optional_input_names: List[str] = field(default_factory=list)
```

- [ ] **Step 4: Populate it in `_parse_node_info`**

Replace lines 309-311:

```python
    # Collect names of all required inputs (both widget and connection)
    required_section = input_data.get('required', {})
    required_input_names = list(required_section.keys()) if isinstance(required_section, dict) else []
```

with:

```python
    # Collect names of all required inputs (both widget and connection)
    required_section = input_data.get('required', {})
    required_input_names = list(required_section.keys()) if isinstance(required_section, dict) else []

    optional_section = input_data.get('optional', {})
    optional_input_names = list(optional_section.keys()) if isinstance(optional_section, dict) else []
```

Then add `optional_input_names=optional_input_names,` to the `NodeTypeInfo(...)` constructor call that follows.

- [ ] **Step 5: Add the public accessors**

Next to `get_required_input_names` in the public API block (around line 620):

```python
def get_optional_input_names(class_type: str) -> Optional[List[str]]:
    """Names of a node type's optional inputs, or None if not cached."""
    info = get_node_info(class_type)
    return info.optional_input_names if info else None


def get_known_class_types() -> Set[str]:
    """Every class_type present in the cache.

    Empty when the cache is unavailable — callers must treat an empty result
    as "unknown", never as "nothing is installed".
    """
    _cache._ensure_loaded()
    with _cache._lock:
        return set(_cache._nodes.keys())
```

Add `Set` to the `typing` import at the top of the file. If the cache's internal dict is not named `_nodes`, use the actual attribute name — check `NodeInfoCache.__init__` around line 342.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_editable.py -v`
Expected: PASS, including all pre-existing tests in the file.

- [ ] **Step 7: Commit**

```bash
git add python/comfyui/node_info.py tests/test_comfyui_editable.py
git commit -m "feat(comfyui): expose optional input names and known class types from node_info"
```

---

## Task 2: Cardinality markers in editable titles

**Files:**
- Modify: `python/comfyui/editable.py:21-33` (dataclass), `:35-78` (`_parse_editable_title`)
- Test: `tests/test_comfyui_editable.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CARDINALITY_SINGLE = 'single'`, `CARDINALITY_OPTIONAL = 'optional'`, `CARDINALITY_MANY = 'many'`
  - `_parse_editable_marker(title: str) -> Tuple[bool, str, Optional[str], str]` — `(is_editable, base_title, condition_node, cardinality)`
  - `_parse_editable_title(title: str) -> Tuple[bool, str, Optional[str]]` — unchanged 3-tuple, now a wrapper
  - `EditableNode.cardinality: str` — defaults to `CARDINALITY_SINGLE`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_comfyui_editable.py`:

```python
# ============================================================================
# _parse_editable_marker — cardinality
# ============================================================================

class TestParseEditableMarker:
    def test_plain_is_single(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_SINGLE
        is_edit, base, cond, card = _parse_editable_marker("Ref Image_editable")
        assert (is_edit, base, cond, card) == (True, "Ref Image", None, CARDINALITY_SINGLE)

    def test_star_is_many(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_MANY
        is_edit, base, cond, card = _parse_editable_marker("Ref Images_editable*")
        assert (is_edit, base, cond, card) == (True, "Ref Images", None, CARDINALITY_MANY)

    def test_question_is_optional(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_OPTIONAL
        is_edit, base, cond, card = _parse_editable_marker("Last Frame_editable?")
        assert (is_edit, base, cond, card) == (True, "Last Frame", None, CARDINALITY_OPTIONAL)

    def test_star_with_condition(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_MANY
        is_edit, base, cond, card = _parse_editable_marker("Refs_editable*@if_UseRefs")
        assert (is_edit, base, cond, card) == (True, "Refs", "UseRefs", CARDINALITY_MANY)

    def test_question_with_ampersand_condition(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_OPTIONAL
        is_edit, base, cond, card = _parse_editable_marker("Tail_editable?&if_Advanced")
        assert (is_edit, base, cond, card) == (True, "Tail", "Advanced", CARDINALITY_OPTIONAL)

    def test_typo_marker_supports_cardinality(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_MANY
        is_edit, base, cond, card = _parse_editable_marker("Refs_editble*")
        assert (is_edit, base, cond, card) == (True, "Refs", None, CARDINALITY_MANY)

    def test_not_editable(self):
        from comfyui.editable import _parse_editable_marker, CARDINALITY_SINGLE
        is_edit, base, cond, card = _parse_editable_marker("KSampler")
        assert (is_edit, base, cond, card) == (False, "KSampler", None, CARDINALITY_SINGLE)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_editable.py::TestParseEditableMarker -v`
Expected: FAIL — `ImportError: cannot import name '_parse_editable_marker'`.

- [ ] **Step 3: Implement the marker parser**

In `python/comfyui/editable.py`, add above `_parse_editable_title` (line 35):

```python
# Cardinality of an editable slot, declared by a marker directly after
# '_editable' and before any '@if_'/'&if_' condition.
#   Name_editable    -> one value (historical behaviour)
#   Name_editable?   -> optional; the node is removed when left empty
#   Name_editable*   -> fan-out; one selector expands into N loader nodes
CARDINALITY_SINGLE = 'single'
CARDINALITY_OPTIONAL = 'optional'
CARDINALITY_MANY = 'many'

_CARDINALITY_MARKERS = {'*': CARDINALITY_MANY, '?': CARDINALITY_OPTIONAL}


def _parse_editable_marker(title: str) -> Tuple[bool, str, Optional[str], str]:
    """Parse an editable title into its flag, base name, condition and cardinality.

    Returns:
        (is_editable, base_title, condition_node_name, cardinality)
    """
    editable_markers = ['_editable', '_editble']
    is_editable = False
    condition_node = None
    cardinality = CARDINALITY_SINGLE
    base_title = title

    for marker in editable_markers:
        if marker not in title:
            continue
        is_editable = True
        parts = title.split(marker)
        base_title = parts[0]

        if len(parts) > 1:
            after_marker = parts[1]
            # Cardinality marker comes first, then the optional condition
            if after_marker[:1] in _CARDINALITY_MARKERS:
                cardinality = _CARDINALITY_MARKERS[after_marker[0]]
                after_marker = after_marker[1:]
            for sep in ('@if_', '&if_'):
                if after_marker.startswith(sep):
                    condition_node = after_marker[len(sep):]
                    break
        break

    return is_editable, base_title, condition_node, cardinality
```

- [ ] **Step 4: Make `_parse_editable_title` a wrapper**

Replace the entire body of `_parse_editable_title` (lines 54-78) with:

```python
    is_editable, base_title, condition_node, _ = _parse_editable_marker(title)
    return is_editable, base_title, condition_node
```

Leave the docstring in place and add a line to it: `Cardinality markers are ignored here — see _parse_editable_marker().`

- [ ] **Step 5: Add the dataclass field**

In `EditableNode` (after `condition_node`, line 32):

```python
    cardinality: str = CARDINALITY_SINGLE  # 'single' | 'optional' | 'many'
```

Because `CARDINALITY_SINGLE` is referenced as a default, it must be defined **above** the `EditableNode` dataclass. Move the three constants and `_CARDINALITY_MARKERS` above the `@dataclass` at line 21, keeping `_parse_editable_marker` where it is.

- [ ] **Step 6: Thread cardinality through extraction**

In `extract_editable_nodes`, change line 475 from:

```python
        is_editable, base_title, condition_node_name = _parse_editable_title(title)
```

to:

```python
        is_editable, base_title, condition_node_name, cardinality = _parse_editable_marker(title)
```

Then add `cardinality=cardinality,` to **all four** `EditableNode(...)` constructor calls in that function (lines 517, 550, 572, and inside `_extract_subgraph_widgets` at line 213 pass it through as a parameter defaulting to `CARDINALITY_SINGLE`). Leave line 463 (`is_edit, base, _ = _parse_editable_title(title)`) alone — the title map only needs the base name.

- [ ] **Step 7: Run tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: PASS. The 10 pre-existing `_parse_editable_title` tests must still pass unchanged.

- [ ] **Step 8: Commit**

```bash
git add python/comfyui/editable.py tests/test_comfyui_editable.py
git commit -m "feat(comfyui): add cardinality markers (_editable* and _editable?) to node titles"
```

---

## Task 3: API-format editable node extraction

**Files:**
- Modify: `python/comfyui/editable.py:409-598` (`extract_editable_nodes`)
- Test: `tests/test_comfyui_editable.py`

**Interfaces:**
- Consumes: `CARDINALITY_*` and `_parse_editable_marker` (Task 2); `node_info` accessors (Task 1).
- Produces:
  - `_NodeView` dataclass — the format-neutral input to widget building
  - `_build_editable_widgets(view, subgraph_defs) -> List[EditableNode]`
  - `extract_editable_nodes(path)` now returns populated results for API-format workflows

- [ ] **Step 1: Write the failing test**

Append to `tests/test_comfyui_editable.py`:

```python
# ============================================================================
# API-format editable extraction
# ============================================================================

import json


def _write_api_workflow(tmp_path, workflow):
    path = tmp_path / "api_workflow.json"
    path.write_text(json.dumps(workflow), encoding="utf-8")
    return str(path)


class TestExtractEditableApiFormat:
    def _workflow(self):
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

    def test_finds_marked_nodes_only(self, tmp_path):
        from comfyui.editable import extract_editable_nodes
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, self._workflow()))
        assert {n.node_id for n in nodes} == {"41", "42", "43"}

    def test_reads_current_value_from_inputs(self, tmp_path):
        from comfyui.editable import extract_editable_nodes
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, self._workflow()))
        by_id = {n.node_id: n for n in nodes}
        assert by_id["41"].current_value == "ref_a.png"
        assert by_id["42"].current_value == "a cat"

    def test_image_widget_type_from_configs(self, tmp_path):
        from comfyui.editable import extract_editable_nodes
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, self._workflow()))
        by_id = {n.node_id: n for n in nodes}
        assert by_id["41"].widget_type == "image"
        assert by_id["41"].widget_name == "image"

    def test_cardinality_preserved(self, tmp_path):
        from comfyui.editable import extract_editable_nodes, CARDINALITY_MANY, CARDINALITY_OPTIONAL
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, self._workflow()))
        by_id = {n.node_id: n for n in nodes}
        assert by_id["41"].cardinality == CARDINALITY_MANY
        assert by_id["43"].cardinality == CARDINALITY_OPTIONAL

    def test_linked_inputs_are_not_editable(self, tmp_path):
        """'clip' is a link ["9", 0] and must never become a widget."""
        from comfyui.editable import extract_editable_nodes
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, self._workflow()))
        assert not any(n.widget_name == "clip" for n in nodes)

    def test_list_valued_widget_is_not_mistaken_for_link(self, tmp_path):
        """[512, 512] is a value, not a node reference."""
        from comfyui.editable import extract_editable_nodes
        wf = {
            "7": {
                "class_type": "SomeUnknownCustomNode",
                "inputs": {"size": [512, 512]},
                "_meta": {"title": "Size_editable"},
            }
        }
        nodes = extract_editable_nodes(_write_api_workflow(tmp_path, wf))
        assert len(nodes) == 1
        assert nodes[0].current_value == [512, 512]

    def test_ui_format_still_works(self):
        """Regression guard: the UI path must be untouched."""
        import os
        from comfyui.editable import extract_editable_nodes
        path = os.path.join(os.path.dirname(__file__), "workflows",
                            "image_qwen_image_edit_2511.json")
        nodes = extract_editable_nodes(path)
        assert len(nodes) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_editable.py::TestExtractEditableApiFormat -v`
Expected: FAIL — all API tests return `[]` because of the bail at `editable.py:443`.

- [ ] **Step 3: Add the format-neutral view**

In `python/comfyui/editable.py`, add after the `EditableNode` dataclass:

```python
@dataclass
class _NodeView:
    """One workflow node, normalised across UI and API formats.

    ``get_value`` is the only thing that genuinely differs between the two:
    UI format resolves a positional index into ``widgets_values``, API format
    reads the input name straight out of the ``inputs`` dict.
    """
    node_id: Any
    node_type: str
    title: str
    display_name: str
    condition_node: Optional[str]
    cardinality: str
    connected_inputs: set
    get_value: Any                      # Callable[[str, Optional[int]], Any]
    fallback_value: Any = None          # last-resort generic text widget
    raw_node: Optional[dict] = None     # UI format only — subgraph extraction
```

- [ ] **Step 4: Extract the shared ladder**

Add this function, lifting the body of the `if config: ... else: ...` block currently at lines 498-581:

```python
def _build_editable_widgets(view: '_NodeView', subgraph_defs: dict) -> List[EditableNode]:
    """Resolve one node into zero or more EditableNode descriptors.

    Ladder: explicit config -> node_info auto-discovery -> subgraph
    proxyWidgets -> last-resort generic text widget.
    """
    from comfyui.node_info import get_node_info, get_widget_index

    def _make(widget_type, widget_name, current_value, options, multi):
        return EditableNode(
            node_id=view.node_id,
            node_type=view.node_type,
            title=view.title,
            display_name=(f"{view.display_name} - {widget_name}" if multi
                          else view.display_name),
            widget_type=widget_type,
            widget_name=widget_name,
            current_value=current_value,
            options=options,
            condition_node=view.condition_node,
            cardinality=view.cardinality,
        )

    config = EDITABLE_NODE_CONFIGS.get(view.node_type)
    if config:
        out = []
        for widget_idx, widget_name, widget_type in _resolve_config_entries(view.node_type, config):
            if widget_name in view.connected_inputs:
                continue
            out.append(_make(widget_type, widget_name,
                             view.get_value(widget_name, widget_idx),
                             _get_widget_options(view.node_type, widget_name),
                             len(config) > 1))
        return out

    info = get_node_info(view.node_type)
    if info and info.widgets:
        out = []
        for widget in info.widgets:
            if widget.name in view.connected_inputs:
                continue
            out.append(_make(widget.widget_type, widget.name,
                             view.get_value(widget.name,
                                            get_widget_index(view.node_type, widget.name)),
                             widget.options or [],
                             len(info.widgets) > 1))
        return out

    if view.raw_node is not None and _is_uuid(view.node_type) and view.node_type in subgraph_defs:
        # Signature gained its `cardinality` parameter in Task 2 Step 6.
        return _extract_subgraph_widgets(
            view.raw_node, view.display_name, view.condition_node, subgraph_defs,
            view.cardinality
        )

    if view.fallback_value is not None:
        logger.warning(f"Unknown editable node type: {view.node_type} (title: {view.title})")
        return [_make('text', 'value', str(view.fallback_value), [], False)]

    return []
```

- [ ] **Step 5: Rewrite `extract_editable_nodes` to dispatch on format**

Replace lines 439-581 (from the `is_api_format` bail through the end of the node loop) with:

```python
    from comfyui.workflow import is_api_format, _is_node_reference

    subgraph_defs = _get_subgraph_definitions(workflow)
    editable_nodes = []

    if is_api_format(workflow):
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                continue
            title = (node_data.get('_meta') or {}).get('title', '')
            is_editable, base_title, condition_node_name, cardinality = \
                _parse_editable_marker(title)
            if not is_editable:
                continue

            node_type = node_data.get('class_type', '')
            inputs = node_data.get('inputs', {}) or {}
            connected = {k for k, v in inputs.items() if _is_node_reference(v)}
            plain = [v for k, v in inputs.items() if k not in connected]

            display_name = base_title.replace('_', ' ').strip()
            if not display_name or display_name == node_type:
                display_name = node_type.replace('Plus', '+')

            editable_nodes.extend(_build_editable_widgets(_NodeView(
                node_id=node_id,
                node_type=node_type,
                title=title,
                display_name=display_name,
                condition_node=condition_node_name,
                cardinality=cardinality,
                connected_inputs=connected,
                get_value=lambda name, idx, _in=inputs: _in.get(name),
                fallback_value=plain[0] if plain else None,
            ), subgraph_defs))
    else:
        nodes = workflow.get('nodes', [])

        title_to_node_id = {}
        for node in nodes:
            title = node.get('title', '')
            if not title:
                continue
            is_edit, base, _ = _parse_editable_title(title)
            if is_edit:
                title_to_node_id[title] = node.get('id')
                title_to_node_id[base] = node.get('id')
            else:
                title_to_node_id[title] = node.get('id')

        for node in nodes:
            title = node.get('title', '')
            is_editable, base_title, condition_node_name, cardinality = \
                _parse_editable_marker(title)
            if not is_editable:
                continue
            if node.get('mode', 0) in (2, 4):
                continue

            node_type = node.get('type')
            widgets_values = node.get('widgets_values', [])
            if isinstance(widgets_values, dict):
                widgets_values = list(widgets_values.values())

            display_name = base_title.replace('_', ' ').strip()
            if not display_name or display_name == node_type:
                display_name = node_type.replace('Plus', '+')

            def _ui_get_value(name, idx, _wv=widgets_values):
                if idx is not None and idx < len(_wv):
                    return _wv[idx]
                return None

            editable_nodes.extend(_build_editable_widgets(_NodeView(
                node_id=node.get('id'),
                node_type=node_type,
                title=title,
                display_name=display_name,
                condition_node=condition_node_name,
                cardinality=cardinality,
                connected_inputs={inp.get('name') for inp in node.get('inputs', [])
                                  if inp.get('link') is not None},
                get_value=_ui_get_value,
                fallback_value=widgets_values[0] if widgets_values else None,
                raw_node=node,
            ), subgraph_defs))
```

The natural sort, logging and `_cache_store` block (lines 583-598) stay exactly as they are.

- [ ] **Step 6: Run tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: PASS. `test_ui_format_still_works` and every existing test in `test_comfyui_editable.py` and `test_workflow.py` must pass.

- [ ] **Step 7: Commit**

```bash
git add python/comfyui/editable.py tests/test_comfyui_editable.py
git commit -m "feat(comfyui): extract editable nodes from API-format workflows"
```

---

## Task 4: API-format settings node extraction

**Files:**
- Modify: `python/comfyui/editable.py:643-782` (`extract_settings_nodes`)
- Test: `tests/test_comfyui_editable.py`

**Interfaces:**
- Consumes: `_NodeView` (Task 3).
- Produces: `_build_settings_widgets(view, group_name) -> List[SettingsNode]`; `extract_settings_nodes(path)` works on API format.

- [ ] **Step 1: Write the failing test**

```python
class TestExtractSettingsApiFormat:
    def test_finds_settings_nodes(self, tmp_path):
        from comfyui.editable import extract_settings_nodes
        wf = {
            "12": {
                "class_type": "KSampler",
                "inputs": {"steps": 20, "cfg": 7.5, "denoise": 1.0, "model": ["3", 0]},
                "_meta": {"title": "Sampler_settings"},
            },
            "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "a.safetensors"}},
        }
        path = tmp_path / "s.json"
        path.write_text(json.dumps(wf), encoding="utf-8")
        nodes = extract_settings_nodes(str(path))
        assert {n.widget_name for n in nodes} == {"steps", "cfg", "denoise"}
        assert all(n.group_name == "Sampler" for n in nodes)
        by_name = {n.widget_name: n for n in nodes}
        assert by_name["steps"].current_value == 20
        assert by_name["cfg"].current_value == 7.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_editable.py::TestExtractSettingsApiFormat -v`
Expected: FAIL — returns `[]` because of the bail at `editable.py:673`.

- [ ] **Step 3: Extract the settings ladder**

```python
def _build_settings_widgets(view: '_NodeView', group_name: str) -> List[SettingsNode]:
    """Resolve one node into zero or more SettingsNode descriptors.

    Ladder: SETTINGS_NODE_CONFIGS -> EDITABLE_NODE_CONFIGS -> node_info
    auto-discovery -> nothing (warn only).
    """
    from comfyui.node_info import get_node_info, get_widget_index

    def _make(widget_type, widget_name, current_value, options):
        return SettingsNode(
            node_id=view.node_id,
            node_type=view.node_type,
            title=view.title,
            group_name=group_name,
            widget_name=widget_name,
            widget_type=widget_type,
            current_value=current_value,
            options=options,
        )

    config = (SETTINGS_NODE_CONFIGS.get(view.node_type)
              or EDITABLE_NODE_CONFIGS.get(view.node_type))
    if config:
        out = []
        for widget_idx, widget_name, widget_type in _resolve_config_entries(view.node_type, config):
            if widget_name in view.connected_inputs:
                continue
            out.append(_make(widget_type, widget_name,
                             view.get_value(widget_name, widget_idx),
                             _get_widget_options(view.node_type, widget_name)))
        return out

    info = get_node_info(view.node_type)
    if info and info.widgets:
        out = []
        for widget in info.widgets:
            if widget.name in view.connected_inputs:
                continue
            out.append(_make(widget.widget_type, widget.name,
                             view.get_value(widget.name,
                                            get_widget_index(view.node_type, widget.name)),
                             widget.options or []))
        return out

    logger.warning(f"Unknown settings node type: {view.node_type} (title: {view.title})")
    return []
```

Note this adds `connected_inputs` filtering to the settings path, which the UI-format version did not do. That is a deliberate fix — a linked input is not user-editable in either format.

- [ ] **Step 4: Rewrite `extract_settings_nodes` to dispatch on format**

Replace lines 671-767 with a format branch mirroring Task 3 Step 5, using `_parse_settings_title(title)` for the marker (it returns `(is_settings, group_name)`), `CARDINALITY_SINGLE` for the view's cardinality, `raw_node=None`, and `fallback_value=None`. Call `_build_settings_widgets(view, group_name)` in both branches. Keep the UI branch's `mode in (2, 4)` skip and the trailing logging block (lines 769-782) untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python/comfyui/editable.py tests/test_comfyui_editable.py
git commit -m "feat(comfyui): extract settings nodes from API-format workflows"
```

---

## Task 5: Audio widget type — backend

**Files:**
- Modify: `python/comfyui/modifier.py:402-442`, `python/comfyui/node_configs.py:53-60`, `python/comfyui/image_convert.py:20,185-200`, `python/comfyui/editable.py:28` (docstring)
- Test: `tests/test_comfyui_modifier.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_apply_audio_widget(inputs, value, widget_name, node_id, node_type)`, registered as `'audio'` in `_WIDGET_APPLIERS`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_comfyui_modifier.py`:

```python
class TestApplyAudioWidget:
    def test_writes_basename_to_audio(self):
        from comfyui.modifier import _apply_audio_widget
        inputs = {"audio": "old.wav"}
        _apply_audio_widget(inputs, r"C:\refs\voice.wav", None, "5", "LoadAudio")
        assert inputs["audio"] == "voice.wav"

    def test_named_widget_wins(self):
        from comfyui.modifier import _apply_audio_widget
        inputs = {}
        _apply_audio_widget(inputs, r"C:\refs\voice.wav", "audio_file", "5", "VHS_LoadAudio")
        assert inputs["audio_file"] == "voice.wav"

    def test_empty_value_keeps_default(self):
        from comfyui.modifier import _apply_audio_widget
        inputs = {"audio": "keep.wav"}
        _apply_audio_widget(inputs, "", None, "5", "LoadAudio")
        assert inputs["audio"] == "keep.wav"

    def test_list_value_takes_first(self):
        from comfyui.modifier import _apply_audio_widget
        inputs = {}
        _apply_audio_widget(inputs, [r"C:\a\one.wav", r"C:\a\two.wav"], None, "5", "LoadAudio")
        assert inputs["audio"] == "one.wav"

    def test_registered_in_dispatch_table(self):
        from comfyui.modifier import _WIDGET_APPLIERS
        assert "audio" in _WIDGET_APPLIERS


class TestAudioNodeConfigs:
    def test_loadaudio_registered(self):
        from comfyui.node_configs import EDITABLE_NODE_CONFIGS
        assert EDITABLE_NODE_CONFIGS["LoadAudio"] == [("audio", "audio")]

    def test_loadvideo_uses_correct_input_name(self):
        """/object_info reports LoadVideo's input as 'file', not 'video'."""
        from comfyui.node_configs import EDITABLE_NODE_CONFIGS
        assert EDITABLE_NODE_CONFIGS["LoadVideo"] == [("file", "video")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_modifier.py::TestApplyAudioWidget tests\test_comfyui_modifier.py::TestAudioNodeConfigs -v`
Expected: FAIL — `ImportError: cannot import name '_apply_audio_widget'`.

- [ ] **Step 3: Add the applier**

In `python/comfyui/modifier.py`, after `_apply_video_widget` (line 414):

```python
def _apply_audio_widget(inputs, value, widget_name, node_id, node_type):
    """Audio widget — stores the basename in the named input, else 'audio'."""
    if not value:
        # No audio provided — leave node as-is with its workflow default
        logger.info(f"  Audio node {node_id} ({node_type}): no file selected, "
                    f"keeping workflow default")
        return
    audio_path = _first_path(value)
    if audio_path:
        inputs[widget_name or 'audio'] = os.path.basename(audio_path)
        logger.info(f"  Set audio node {node_id} ({node_type}): "
                    f"{os.path.basename(audio_path)}")
```

Register it in `_WIDGET_APPLIERS` (line 431): `'audio': _apply_audio_widget,`

- [ ] **Step 4: Update node_configs**

In `python/comfyui/node_configs.py`, replace line 56 and add the audio entries:

```python
    'VHS_LoadVideo': [('video', 'video')],
    'VHS_LoadVideoPath': [('video', 'video')],
    # /object_info reports the native LoadVideo's input as 'file'. Use the
    # native node (not VHS) for reference video: it returns a VIDEO object
    # exposing get_components(), which is what H3 media-type inference keys on.
    'LoadVideo': [('file', 'video')],

    # Audio loading nodes - 'audio' type can't be auto-discovered (it's a COMBO)
    'LoadAudio': [('audio', 'audio')],
    'VHS_LoadAudioUpload': [('audio', 'audio')],
```

- [ ] **Step 5: Stop the misleading conversion warning for audio and video**

In `python/comfyui/image_convert.py`, after line 20:

```python
# Formats ComfyUI loads directly but that this module never converts. Without
# this, every audio and video input trips the "may fail to load it" warning.
COMFYUI_PASSTHROUGH_FORMATS = {
    '.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac',
    '.mp4', '.mov', '.mkv', '.avi', '.webm',
}
```

Then change the guard at line 191 from `if ext not in COMFYUI_NATIVE_FORMATS:` to:

```python
    if ext not in COMFYUI_NATIVE_FORMATS and ext not in COMFYUI_PASSTHROUGH_FORMATS:
```

- [ ] **Step 6: Update the widget_type docstring**

In `python/comfyui/editable.py` line 28, add `'audio'` to the comment listing widget types.

- [ ] **Step 7: Run tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: PASS, including `tests/test_farm_isolation.py` (node_configs.py is farm-copied).

- [ ] **Step 8: Commit**

```bash
git add python/comfyui/modifier.py python/comfyui/node_configs.py python/comfyui/image_convert.py python/comfyui/editable.py tests/test_comfyui_modifier.py
git commit -m "feat(comfyui): add audio input widget type and fix LoadVideo input name"
```

---

## Task 6: Audio widget type — UI

**Files:**
- Modify: `python/ui/tabs/comfyui/ui_manager.py:212-241` (layout), `:463-484` (widget branch); `python/ui/tabs/comfyui/tab.py:1628-1630` (signal wiring), `:1830` (`_FILE_INPUT_WIDGET_TYPES`)

**Interfaces:**
- Consumes: `'audio'` widget type from Task 5.
- Produces: an `audio` branch producing a `BatchImageSelector` on `container.input_widget`.

- [ ] **Step 1: Add the widget branch**

In `ui_manager._create_editable_node_widget`, after the `video` branch (ends ~line 484):

```python
        elif node.widget_type == 'audio':
            from core.config import AUDIO_EXTENSIONS as _AUDIO_EXT
            input_widget = BatchImageSelector(
                supported_extensions=sorted(_AUDIO_EXT),
                total_image_nodes=total_audio_nodes,
                file_type_label="audio",
            )
            input_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            last_dir = get_last_browse_directory("comfyui_audio")
            if last_dir:
                input_widget.set_last_browse_dir(last_dir)

            label_min_w = 0 if total_audio_nodes >= 3 else 160
            label = self._create_label_with_tooltip(f"{node.display_name}:", min_width=label_min_w)
            input_widget.toolbar_layout.insertWidget(0, label)

            layout.addWidget(input_widget, 1)
            container.input_widget = input_widget
```

Add `total_audio_nodes=1` to the `_create_editable_node_widget` signature (line 341) and pass it from `refresh_editable_nodes` alongside the existing `total_image_nodes` / `total_video_nodes` counts (lines 212-241) — count nodes whose `widget_type == 'audio'` and include them in the horizontal file-selector row.

- [ ] **Step 2: Wire the change signal**

In `tab.py`, after the `video` branch at line 1628:

```python
            elif node.widget_type == 'audio':
                input_widget.images_changed.connect(self._on_images_changed)
```

- [ ] **Step 3: Include audio in empty-input validation**

In `tab.py` line 1830, change `_FILE_INPUT_WIDGET_TYPES = ('image', 'video')` to `('image', 'video', 'audio')`.

Then in `_validate_dynamic_inputs` (line 1909), replace:

```python
                    kind = "image" if node.widget_type == 'image' else "video"
```

with:

```python
                    kind = {'image': 'image', 'video': 'video', 'audio': 'audio'}[node.widget_type]
```

- [ ] **Step 4: Verify in the running app**

Write `_run_test.ps1`:

```powershell
Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe python\core\luma_tools.py --tab comfyui --auto-close 30
```

Run: `powershell -ExecutionPolicy Bypass -File _run_test.ps1`
Then read the newest log under `W:\LumaRND\luma_tools\_logs\users\`.
Expected: the tab loads, no traceback, no `Unknown editable widget_type 'audio'` warning.

- [ ] **Step 5: Run the suite and commit**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`

```bash
git add python/ui/tabs/comfyui/ui_manager.py python/ui/tabs/comfyui/tab.py
git commit -m "feat(comfyui): render audio input selectors in the dynamic UI"
```

---

## Task 7: Fan-out expansion

**Files:**
- Modify: `python/comfyui/modifier.py` (new helpers + call site at `:770`)
- Test: `tests/test_comfyui_modifier.py`

**Interfaces:**
- Consumes: `CARDINALITY_MANY` (Task 2), `get_optional_input_names` (Task 1), `remove_nodes_from_api_workflow` (`modifier.py:51`).
- Produces: `_expand_fanout_slots(workflow: Dict[str, Any], editable_values) -> None` — mutates both; removes handled entries from `editable_values`.
- Helpers: `_split_indexed_name(name) -> Optional[Tuple[str, int]]`, `_find_consumers(workflow, template_id) -> List[Tuple[str, str, int]]`, `_allocate_node_id(workflow) -> str`.

- [ ] **Step 1: Write the failing test**

```python
class TestFanoutSlots:
    def _wf(self):
        return {
            "41": {"class_type": "LoadImage", "inputs": {"image": "a.png"},
                   "_meta": {"title": "Ref Images_editable*"}},
            "50": {"class_type": "MiniMaxH3Easy",
                   "inputs": {"prompt": "hi", "media_1": ["41", 0], "media_type_1": "image"},
                   "_meta": {"title": "Video_editable"}},
        }

    def _values(self, files):
        from comfyui.editable import EditableNode, CARDINALITY_MANY
        node = EditableNode(node_id="41", node_type="LoadImage", title="Ref Images_editable*",
                            display_name="Ref Images", widget_type="image",
                            widget_name="image", cardinality=CARDINALITY_MANY)
        return {"41": [{"node": node, "value": files}]}

    def test_single_file_writes_template_only(self):
        from comfyui.modifier import _expand_fanout_slots
        wf, vals = self._wf(), self._values([r"C:\r\one.png"])
        _expand_fanout_slots(wf, vals)
        assert wf["41"]["inputs"]["image"] == r"C:\r\one.png"
        assert len(wf) == 2
        assert vals == {}

    def test_three_files_create_two_clones(self):
        from comfyui.modifier import _expand_fanout_slots
        wf = self._wf()
        _expand_fanout_slots(wf, self._values([r"C:\r\1.png", r"C:\r\2.png", r"C:\r\3.png"]))
        loaders = [n for n in wf.values() if n["class_type"] == "LoadImage"]
        assert len(loaders) == 3
        assert {n["inputs"]["image"] for n in loaders} == {r"C:\r\1.png", r"C:\r\2.png", r"C:\r\3.png"}

    def test_clones_wired_to_free_media_slots(self):
        from comfyui.modifier import _expand_fanout_slots
        wf = self._wf()
        _expand_fanout_slots(wf, self._values([r"C:\r\1.png", r"C:\r\2.png", r"C:\r\3.png"]))
        consumer = wf["50"]["inputs"]
        assert consumer["media_1"] == ["41", 0]
        assert "media_2" in consumer and "media_3" in consumer
        wired = {consumer[k][0] for k in ("media_1", "media_2", "media_3")}
        assert len(wired) == 3

    def test_sibling_media_type_duplicated(self):
        """media_type_N must follow media_N automatically."""
        from comfyui.modifier import _expand_fanout_slots
        wf = self._wf()
        _expand_fanout_slots(wf, self._values([r"C:\r\1.png", r"C:\r\2.png"]))
        assert wf["50"]["inputs"]["media_type_2"] == "image"

    def test_zero_files_removes_template_and_input(self):
        from comfyui.modifier import _expand_fanout_slots
        wf = self._wf()
        _expand_fanout_slots(wf, self._values([]))
        assert "41" not in wf
        assert "media_1" not in wf["50"]["inputs"]
        assert "50" in wf  # optional input lost -> no cascade

    def test_single_cardinality_untouched(self):
        from comfyui.modifier import _expand_fanout_slots
        from comfyui.editable import EditableNode
        wf = self._wf()
        node = EditableNode(node_id="41", node_type="LoadImage", title="Ref_editable",
                            display_name="Ref", widget_type="image", widget_name="image")
        vals = {"41": [{"node": node, "value": [r"C:\r\1.png", r"C:\r\2.png"]}]}
        _expand_fanout_slots(wf, vals)
        assert len(wf) == 2
        assert vals != {}  # left for the normal appliers


class TestSplitIndexedName:
    def test_splits_trailing_int(self):
        from comfyui.modifier import _split_indexed_name
        assert _split_indexed_name("media_1") == ("media_", 1)
        assert _split_indexed_name("media_type_12") == ("media_type_", 12)

    def test_none_without_trailing_int(self):
        from comfyui.modifier import _split_indexed_name
        assert _split_indexed_name("image") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_modifier.py::TestFanoutSlots -v`
Expected: FAIL — `ImportError: cannot import name '_expand_fanout_slots'`.

- [ ] **Step 3: Implement the helpers**

In `python/comfyui/modifier.py`, above `_apply_editable_values`:

```python
_INDEXED_NAME_RE = re.compile(r'^(?P<prefix>.*?)(?P<idx>\d+)$')


def _split_indexed_name(name: str) -> Optional[Tuple[str, int]]:
    """Split 'media_1' into ('media_', 1). None when there is no trailing int."""
    match = _INDEXED_NAME_RE.match(name or '')
    if not match:
        return None
    return match.group('prefix'), int(match.group('idx'))


def _find_consumers(workflow: Dict[str, Any], template_id: str):
    """Every (consumer_id, input_name, output_slot) fed by ``template_id``."""
    found = []
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        for input_name, value in (node_data.get('inputs') or {}).items():
            if _is_link(value) and str(value[0]) == str(template_id):
                found.append((node_id, input_name, value[1]))
    return found


def _allocate_node_id(workflow: Dict[str, Any]) -> str:
    """Next unused integer-like key."""
    max_id = 0
    for key in workflow:
        try:
            max_id = max(max_id, int(key))
        except (TypeError, ValueError):
            continue
    return str(max_id + 1)
```

Add `import re` and `Tuple` to the imports if absent.

- [ ] **Step 4: Implement `_expand_fanout_slots`**

```python
def _expand_fanout_slots(workflow: Dict[str, Any], editable_values) -> None:
    """Expand every fan-out slot into one loader node per selected file.

    A slot titled ``Name_editable*`` holds a list of files. The first stays on
    the template node; each extra file gets a cloned node wired into the next
    free numbered input on the same consumer. Every consumer input sharing the
    template's trailing index is duplicated too, so ``media_type_N`` follows
    ``media_N`` without this code knowing either name.

    Full paths are written deliberately — normalize_file_paths_in_workflow()
    later basenames them, handles .exr -> .png renaming, and collects them for
    staging.
    """
    from comfyui.editable import CARDINALITY_MANY
    from comfyui.node_info import get_optional_input_names

    if not editable_values:
        return

    handled = []
    for node_id, entries in list(editable_values.items()):
        entry_list = entries if isinstance(entries, list) else [entries]
        for data in entry_list:
            node_info = data.get('node')
            if getattr(node_info, 'cardinality', None) != CARDINALITY_MANY:
                continue

            template_id = str(node_id)
            template = workflow.get(template_id)
            if template is None:
                logger.warning(f"[Fanout] Template node {template_id} not in workflow")
                continue

            value = data.get('value')
            files = [f for f in (value if isinstance(value, list) else [value]) if f]
            file_input = getattr(node_info, 'widget_name', None) or 'image'

            if not files:
                logger.info(f"[Fanout] Slot {template_id} empty — removing template node")
                remove_nodes_from_api_workflow(workflow, {template_id})
                handled.append((node_id, data))
                continue

            template['inputs'][file_input] = files[0]
            handled.append((node_id, data))
            if len(files) == 1:
                continue

            consumers = _find_consumers(workflow, template_id)
            if not consumers:
                logger.warning(f"[Fanout] Node {template_id} feeds nothing — "
                               f"{len(files) - 1} extra file(s) ignored")
                continue
            consumer_id, input_name, out_slot = consumers[0]
            split = _split_indexed_name(input_name)
            if not split:
                logger.warning(f"[Fanout] Consumer input '{input_name}' has no trailing "
                               f"index — {len(files) - 1} extra file(s) ignored")
                continue
            prefix, base_idx = split

            consumer_inputs = workflow[consumer_id]['inputs']
            siblings = {}
            for name, val in list(consumer_inputs.items()):
                parsed = _split_indexed_name(name)
                if parsed and parsed[1] == base_idx:
                    siblings[parsed[0]] = val

            declared = get_optional_input_names(workflow[consumer_id].get('class_type', '')) or []
            ceiling = 0
            for name in declared:
                parsed = _split_indexed_name(name)
                if parsed and parsed[0] == prefix:
                    ceiling = max(ceiling, parsed[1])
            used = {p[1] for p in (_split_indexed_name(n) for n in consumer_inputs) if p}

            for extra in files[1:]:
                free = next((i for i in range(1, ceiling + 1) if i not in used), None)
                if free is None:
                    logger.warning(f"[Fanout] No free '{prefix}N' slot below {ceiling} — "
                                   f"dropping {os.path.basename(str(extra))}")
                    continue
                used.add(free)

                clone_id = _allocate_node_id(workflow)
                clone = copy.deepcopy(template)
                clone['inputs'][file_input] = extra
                workflow[clone_id] = clone

                for sib_prefix, sib_value in siblings.items():
                    if _is_link(sib_value):
                        consumer_inputs[f"{sib_prefix}{free}"] = [clone_id, out_slot]
                    else:
                        consumer_inputs[f"{sib_prefix}{free}"] = sib_value
                logger.info(f"[Fanout] {os.path.basename(str(extra))} -> node {clone_id} "
                            f"-> {consumer_id}.{prefix}{free}")

    for node_id, data in handled:
        entries = editable_values.get(node_id)
        if isinstance(entries, list):
            if data in entries:
                entries.remove(data)
            if not entries:
                del editable_values[node_id]
        else:
            editable_values.pop(node_id, None)
```

- [ ] **Step 5: Call it before values are applied**

In `modify_workflow_api_format`, insert immediately before line 770 (`_apply_editable_values(modified, editable_values)`):

```python
    # Fan-out slots become concrete loader nodes before any value is applied,
    # so the normal appliers never see the multi-file entry.
    _expand_fanout_slots(modified, editable_values)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add python/comfyui/modifier.py tests/test_comfyui_modifier.py
git commit -m "feat(comfyui): expand fan-out slots into per-file loader nodes at submit time"
```

---

## Task 8: Keep fan-out slots out of Deadline batching

**Files:**
- Modify: `python/deadline/submitter.py:242-267`
- Test: `tests/test_comfyui_modifier.py`

**Interfaces:**
- Consumes: `CARDINALITY_MANY` (Task 2).
- Produces: `_collect_batch_images` skips fan-out entries.

- [ ] **Step 1: Write the failing test**

```python
class TestCollectBatchImagesSkipsFanout:
    def test_fanout_slot_is_not_batched(self, tmp_path):
        """5 references must be ONE job, not five."""
        from deadline.submitter import _collect_batch_images
        from comfyui.editable import EditableNode, CARDINALITY_MANY

        files = []
        for name in ("a.png", "b.png"):
            p = tmp_path / name
            p.write_bytes(b"x")
            files.append(str(p))

        node = EditableNode(node_id="41", node_type="LoadImage", title="Refs_editable*",
                            display_name="Refs", widget_type="image",
                            widget_name="image", cardinality=CARDINALITY_MANY)
        paths, node_id = _collect_batch_images({"41": [{"node": node, "value": files}]})
        assert paths == []
        assert node_id == -1

    def test_normal_slot_still_batches(self, tmp_path):
        from deadline.submitter import _collect_batch_images
        from comfyui.editable import EditableNode

        p = tmp_path / "a.png"
        p.write_bytes(b"x")
        node = EditableNode(node_id="41", node_type="LoadImage", title="Img_editable",
                            display_name="Img", widget_type="image", widget_name="image")
        paths, node_id = _collect_batch_images({"41": [{"node": node, "value": [str(p)]}]})
        assert paths == [str(p)]
        assert node_id == "41"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_modifier.py::TestCollectBatchImagesSkipsFanout -v`
Expected: FAIL on `test_fanout_slot_is_not_batched` — it returns both paths and `"41"`.

- [ ] **Step 3: Implement the skip**

In `python/deadline/submitter.py`, inside the innermost loop of `_collect_batch_images` (after line 260, `value = data.get('value')`):

```python
                # Fan-out slots hold every reference for ONE generation. Batching
                # them would turn 5 references into 5 single-reference jobs.
                if getattr(node_info, 'cardinality', None) == CARDINALITY_MANY:
                    continue
```

Add the import at the top of `submitter.py`: `from comfyui.editable import CARDINALITY_MANY`.

Extend the docstring: `Fan-out slots (_editable*) are skipped — their files all belong to a single generation.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python/deadline/submitter.py tests/test_comfyui_modifier.py
git commit -m "fix(comfyui): keep fan-out reference slots out of per-file Deadline batching"
```

---

## Task 9: Submit-time validation — missing nodes and reference tags

**Files:**
- Modify: `python/ui/tabs/comfyui/tab.py:1860-1950` (`_validate_dynamic_inputs`)
- Test: `tests/test_comfyui_modifier.py`

**Interfaces:**
- Consumes: `get_known_class_types` (Task 1), `CARDINALITY_MANY` (Task 2).
- Produces:
  - `collect_missing_node_types(workflow: dict, known: Set[str]) -> List[str]` in `python/comfyui/workflow.py`
  - `find_out_of_range_reference_tags(prompt: str, counts: Dict[str, int]) -> List[str]` in `python/comfyui/editable.py`

- [ ] **Step 1: Write the failing test**

```python
class TestMissingNodeTypes:
    def test_reports_missing(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"1": {"class_type": "LoadImage", "inputs": {}},
              "2": {"class_type": "MiniMaxH3Easy", "inputs": {}}}
        assert collect_missing_node_types(wf, {"LoadImage"}) == ["MiniMaxH3Easy"]

    def test_empty_cache_reports_nothing(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"1": {"class_type": "Whatever", "inputs": {}}}
        assert collect_missing_node_types(wf, set()) == []

    def test_ui_format_supported(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"nodes": [{"id": 1, "type": "LoadImage"}, {"id": 2, "type": "Nope"}]}
        assert collect_missing_node_types(wf, {"LoadImage"}) == ["Nope"]

    def test_uuid_subgraph_nodes_ignored(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"nodes": [{"id": 1, "type": "0f8c1e2a-3b4d-5e6f-7a8b-9c0d1e2f3a4b"}]}
        assert collect_missing_node_types(wf, {"LoadImage"}) == []


class TestReferenceTagValidation:
    def test_out_of_range_picture(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "a <Picture 3> b", {"image": 2, "video": 0, "audio": 0}) == ["<Picture 3>"]

    def test_in_range_is_clean(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "<Picture 1> and <Picture 2>", {"image": 2, "video": 0, "audio": 0}) == []

    def test_video_and_audio_counted_separately(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "<Video 1> <Audio 2>", {"image": 9, "video": 1, "audio": 1}) == ["<Audio 2>"]

    def test_dialogue_tags_ignored(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "<d>hello there</d>", {"image": 0, "video": 0, "audio": 0}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python\venv\Scripts\python.exe -m pytest tests\test_comfyui_modifier.py::TestMissingNodeTypes tests\test_comfyui_modifier.py::TestReferenceTagValidation -v`
Expected: FAIL — both functions are undefined.

- [ ] **Step 3: Implement the node-type check**

In `python/comfyui/workflow.py`:

```python
def collect_missing_node_types(workflow: Dict[str, Any], known: set) -> List[str]:
    """Class types used by the workflow that the node_info cache doesn't know.

    An empty ``known`` set means "cache unavailable" and yields no findings —
    a cold workstation must never block a valid submission.
    """
    if not known:
        return []

    if is_api_format(workflow):
        used = {n.get('class_type') for n in workflow.values()
                if isinstance(n, dict) and n.get('class_type')}
    else:
        used = {n.get('type') for n in workflow.get('nodes', [])
                if n.get('type') and not _is_uuid(n.get('type'))}

    return sorted(used - known)
```

- [ ] **Step 4: Implement the reference tag check**

In `python/comfyui/editable.py`:

```python
# H3 resolves every reference mention to one of these literals before the text
# encoder sees it, so artists can simply type them. N is the 1-based ordinal
# within that media type.
_REFERENCE_TAG_RE = re.compile(r'<(Picture|Video|Audio)\s+(\d+)>')
_REFERENCE_TAG_TYPES = {'Picture': 'image', 'Video': 'video', 'Audio': 'audio'}


def find_out_of_range_reference_tags(prompt: str, counts: dict) -> List[str]:
    """Reference tags whose ordinal exceeds the files selected for that type.

    H3 substitutes an empty string for an unmatched reference, so this fails
    silently at render time rather than erroring.
    """
    if not prompt:
        return []
    bad = []
    for kind, number in _REFERENCE_TAG_RE.findall(prompt):
        ordinal = int(number)
        available = counts.get(_REFERENCE_TAG_TYPES[kind], 0)
        if ordinal < 1 or ordinal > available:
            bad.append(f"<{kind} {ordinal}>")
    return bad
```

- [ ] **Step 5: Wire both into `_validate_dynamic_inputs`**

At the top of the method (after the `widget_manager` guard at line 1883):

```python
        # Blocking: the workflow needs a node pack the farm doesn't have
        try:
            from comfyui.node_info import get_known_class_types
            from comfyui.workflow import collect_missing_node_types, load_workflow
            workflow_path = self.app_state.comfyui_workflow_path
            if workflow_path:
                missing = collect_missing_node_types(
                    load_workflow(workflow_path), get_known_class_types())
                if missing:
                    return ("The ComfyUI server does not have these node types "
                            "installed: " + ", ".join(missing))
        except Exception as e:
            logger.warning(f"Node availability check skipped: {e}")
```

`self.app_state.comfyui_workflow_path` is the selected workflow; `_can_submit` already
truth-checks it at `tab.py:1844`, one line before this method is called, so no new
accessor is needed.

Then, after the existing widget loop finishes collecting `problems`, add the non-blocking warning:

```python
        # Non-blocking: reference tags pointing past the selected files
        from comfyui.editable import find_out_of_range_reference_tags, CARDINALITY_MANY
        counts = {'image': 0, 'video': 0, 'audio': 0}
        prompts = []
        for _key, container in widget_manager.dynamic_widgets.items():
            node = getattr(container, 'editable_node', None)
            input_widget = getattr(container, 'input_widget', None)
            if not node or not input_widget:
                continue
            if (node.cardinality == CARDINALITY_MANY
                    and node.widget_type in counts):
                counts[node.widget_type] += len(getattr(input_widget, 'selected_files', []) or [])
            elif node.widget_type == 'text' and hasattr(input_widget, 'toPlainText'):
                prompts.append(input_widget.toPlainText())

        for text in prompts:
            bad = find_out_of_range_reference_tags(text, counts)
            if bad:
                self.show_status(
                    f"Prompt references {', '.join(bad)} but fewer files are selected — "
                    f"H3 will substitute nothing for them.", "warning")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: PASS.

- [ ] **Step 7: Verify in the running app**

Run `_run_test.ps1` from Task 6 Step 4, select an existing preset, and confirm the log shows no `Node availability check skipped` warning and Submit is not blocked for a valid preset.

- [ ] **Step 8: Commit**

```bash
git add python/comfyui/workflow.py python/comfyui/editable.py python/ui/tabs/comfyui/tab.py tests/test_comfyui_modifier.py
git commit -m "feat(comfyui): block submit on missing node types, warn on stale reference tags"
```

---

## Task 10: Reference insert menu

**Files:**
- Modify: `python/ui/tabs/comfyui/ui_manager.py:422-443` (text branch, add button), plus a new method on `ComfyUIWidgetManager`; `python/ui/tabs/comfyui/tab.py:1612-1620` (wiring)

**Interfaces:**
- Consumes: `CARDINALITY_MANY` (Task 2), the `audio` widget type (Task 6).
- Produces: `ComfyUIWidgetManager.build_reference_entries() -> List[Tuple[str, str]]` — `(tag, filename)` pairs in insertion order.

- [ ] **Step 1: Add the entry builder**

On `ComfyUIWidgetManager`:

```python
    def build_reference_entries(self):
        """(tag, filename) pairs for every file in a fan-out slot.

        H3 resolves references to <Picture N> / <Video N> / <Audio N> where N
        is the 1-based ordinal within that media type, so the tags are built
        from the live selector contents rather than stored anywhere.
        """
        from comfyui.editable import CARDINALITY_MANY

        tag_names = {'image': 'Picture', 'video': 'Video', 'audio': 'Audio'}
        buckets = {'image': [], 'video': [], 'audio': []}

        for _key, container in self.dynamic_widgets.items():
            node = getattr(container, 'editable_node', None)
            input_widget = getattr(container, 'input_widget', None)
            if not node or not input_widget:
                continue
            if node.cardinality != CARDINALITY_MANY or node.widget_type not in buckets:
                continue
            buckets[node.widget_type].extend(getattr(input_widget, 'selected_files', []) or [])

        entries = []
        for widget_type, files in buckets.items():
            for ordinal, path in enumerate(files, start=1):
                entries.append((f"<{tag_names[widget_type]} {ordinal}>",
                                os.path.basename(str(path))))
        return entries
```

Ensure `import os` is present at the top of `ui_manager.py`.

- [ ] **Step 2: Add the button to the text widget**

In `_create_editable_node_widget`, in the `text` branch, after `top_row.addWidget(preset_btn)` (line 431):

```python
            reference_btn = QPushButton("@ Reference")
            reference_btn.setFixedWidth(110)
            reference_btn.setToolTip(
                "Insert a reference tag for one of the selected reference files")
            top_row.addWidget(reference_btn)
```

And after line 443:

```python
            container.reference_btn = reference_btn
```

- [ ] **Step 3: Wire it**

In `tab.py`, in the `text` branch after the preset button block (line 1619):

```python
                reference_btn = getattr(container, 'reference_btn', None)
                if reference_btn:
                    reference_btn.clicked.connect(
                        lambda checked=False, w=input_widget, btn=reference_btn:
                        self._on_reference_insert_clicked(w, btn)
                    )
```

Add the handler to `ComfyUITab`:

```python
    def _on_reference_insert_clicked(self, text_widget, button):
        """Insert a <Picture N>/<Video N>/<Audio N> tag at the cursor.

        The menu is built on every click so it always reflects the files
        currently selected in the fan-out selectors.
        """
        from PySide6.QtWidgets import QMenu

        entries = self.widget_manager.build_reference_entries()
        menu = QMenu(button)
        if not entries:
            action = menu.addAction("No reference files selected")
            action.setEnabled(False)
        else:
            for tag, filename in entries:
                action = menu.addAction(f"{tag}   {filename}")
                action.triggered.connect(
                    lambda checked=False, t=tag: text_widget.insertPlainText(t)
                )
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
```

Note the lambda uses a default argument to capture `tag` by value — capturing by reference makes every entry insert the last tag.

- [ ] **Step 4: Verify in the running app**

Run `_run_test.ps1`. Select an H3 preset, add two reference images, click **@ Reference**, and confirm the menu lists `<Picture 1>` and `<Picture 2>` with the right filenames and that clicking one inserts it at the cursor.

- [ ] **Step 5: Run the suite and commit**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`

```bash
git add python/ui/tabs/comfyui/ui_manager.py python/ui/tabs/comfyui/tab.py
git commit -m "feat(comfyui): add reference tag insert menu to prompt widgets"
```

---

## Task 11: Author the presets and document the conventions

**Files:**
- Create: `L:/tools/_studio_tools/luma_tools/comfyui/workflows/minimax_h3_t2v.json`, `..._i2v.json`, `..._r2v.json` (API format, exported from the browser)
- Modify: `python/comfyui/CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a registered `MiniMax H3` preset in `comfyui_workflow_presets`.

- [ ] **Step 1: Author and export the three workflows**

In the ComfyUI browser on a worker, build each graph and use **Export (API)** — never "Save". Node titles:

| Node | Title | Present in |
|---|---|---|
| `MiniMaxH3EasyLoader` | *(untitled)* | all |
| `MiniMaxH3Easy` | `Video_editable` | all |
| `MiniMaxH3EasyOutput` | *(untitled)* | all |
| `LoadImage` → `media_1` | `Ref Images_editable*` | R2V |
| `LoadVideo` (native) → `media_2` | `Ref Video_editable*` | R2V |
| `LoadAudio` → `media_3` | `Ref Audio_editable*` | R2V |
| `LoadImage` → `media_1` | `First Frame_editable` | I2V |
| `LoadImage` → `media_2` | `Last Frame_editable?` | I2V |
| `SaveVideo` | `Result_output` | all |

Use the **native** `LoadVideo`, not VHS — it returns a `VIDEO` object exposing `get_components()`, which is what the pack's media-type inference keys on.

- [ ] **Step 2: Register the preset**

In the ComfyUI tab's Model dialog, create a multi-workflow preset named `MiniMax H3` with `output_type: video`, `is_multi: true`, and variants `T2V`, `I2V`, `R2V` pointing at the three files.

In the **Exposed parameters** tab, disable `reference_mention_mode` on the `Video_editable` node — it is declared in the pack's `INPUT_TYPES` and consumed nowhere.

Set the preset `note` to:

```
References: type <Picture 1>, <Video 1>, <Audio 1> in the prompt, or use the
@ Reference button. Numbers are the position within each media type.
Speech: wrap dialogue in <d>...</d>.
```

- [ ] **Step 3: Verify the submitted workflow**

Submit one R2V generation with 3 reference images, 1 video and 1 audio. Find the newest `_job_data/<timestamp>_<uuid>/comfyui_workflow_*.json` under `W:/LumaRND/luma_tools/<user>/` and confirm:

```bash
python -c "
import json, io, glob, os
p = max(glob.glob(r'W:/LumaRND/luma_tools/**/_job_data/*/comfyui_workflow_*.json', recursive=True), key=os.path.getmtime)
wf = json.load(io.open(p, encoding='utf-8'))
h3 = [n for n in wf.values() if n.get('class_type') == 'MiniMaxH3Easy'][0]
print({k: v for k, v in h3['inputs'].items() if k.startswith('media')})
print('loaders:', sum(1 for n in wf.values() if n.get('class_type') in ('LoadImage','LoadVideo','LoadAudio')))
"
```

Expected: five `media_N` links plus five `media_type_N` strings (`image`×3, `video`, `audio`), and 5 loader nodes.

- [ ] **Step 4: Confirm the output**

Check the Gallery for a video with audio, `output_type: "video"`, and per-file metadata recording the seed.

- [ ] **Step 5: Document the conventions**

In `python/comfyui/CLAUDE.md`, under **Editable Nodes**, add:

```markdown
**Cardinality markers** (suffix after `_editable`, before any `@if_`):
- `Name_editable` — one value (default)
- `Name_editable?` — optional; the node is removed from the workflow when left empty
- `Name_editable*` — fan-out; one selector holding N files expands at submit time
  into N cloned loader nodes, wired into the consumer's next free numbered inputs
  (`media_1`, `media_2`, …). Every consumer input sharing the template's trailing
  index is duplicated too, so `media_type_N` follows `media_N` automatically.
  Fan-out slots are excluded from per-file Deadline batching.

**API-format workflows** are fully supported: the `_editable` marker is read from
`_meta.title` and values from the `inputs` dict. Required for node packs whose
frontend injects inputs at serialization time (e.g. ComfyUI-MiniMaxH3-Easy) —
those must be exported with **Export (API)**, never "Save".
```

Add `audio` to the widget-type list in the same file.

- [ ] **Step 6: Commit**

```bash
git add python/comfyui/CLAUDE.md
git commit -m "docs(comfyui): document cardinality markers and API-format preset support"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| Phase 0 farm prerequisites | Task 0 |
| Phase 1 API-format editable extraction | Task 3 |
| Phase 1 API-format settings extraction | Task 4 |
| Phase 2 title markers | Task 2 |
| Phase 2 fan-out expansion | Task 7 |
| Phase 2 `_collect_batch_images` guard | Task 8 |
| Phase 2 node_info `optional_input_names` | Task 1 |
| Phase 3 reference insert menu | Task 10 |
| Phase 3 non-blocking tag validation | Task 9 |
| Phase 3 hide `reference_mention_mode` | Task 11 Step 2 |
| Phase 4 audio widget type | Tasks 5, 6 |
| Phase 4 `LoadVideo` input-name fix | Task 5 Step 4 |
| Phase 4 `image_convert` passthrough | Task 5 Step 5 |
| Phase 4 pre-flight availability check | Task 9 |
| Phase 5 preset authoring | Task 11 |
| Optional polish (collapsible group) | Deliberately omitted — fan-out reduces R2V to three selectors, so it is no longer justified. Revisit only if the panel feels crowded. |

**Type consistency:** `EditableNode.cardinality` (Task 2) is read in Tasks 7, 8, 9, 10. `_NodeView` (Task 3) is reused in Task 4. `get_optional_input_names` (Task 1) is called in Task 7. `get_known_class_types` (Task 1) is called in Task 9. `CARDINALITY_MANY` is imported from `comfyui.editable` everywhere it appears.

**Known risk, carried from the spec:** `remove_nodes_from_api_workflow:116` treats a node_info cache miss as "all inputs required", so Task 7's zero-file path would cascade-remove the consumer node if `MiniMaxH3Easy` is not in the cache. Task 0 must complete before Task 7 is verified end-to-end; the unit tests in Task 7 pass regardless because they exercise the workflow dict directly.
