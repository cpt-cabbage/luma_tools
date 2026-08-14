# MiniMax H3 (ComfyUI-MiniMaxH3-Easy) support — design

**Date:** 2026-08-14
**Status:** proposed

## Context

We want artists to run MiniMax H3 video generation from the ComfyUI tab, covering all four
modalities — text-to-video, image-to-video (first / last / first+last frame), reference video and
reference audio — via the [`nkxx188/ComfyUI-MiniMaxH3-Easy`](https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy)
node pack, including multiple references per generation and the `@` reference system.

Four facts drive the design.

**1. The farm already has native H3.** The node_info cache on
`W:\LumaRND\luma_tools\_node_info\comfyui_node_info.json` (2498 nodes) contains
`MiniMaxH3ImageToVideo`, `MiniMaxH3ReferenceToVideo`, `EmptyMiniMaxH3LatentAV` and
`MiniMaxH3SigmaShift`, plus ComfyUI-GGUF, VHS and KJNodes. ComfyUI is therefore ≥ 0.30.0.
The `MiniMaxH3Easy*` classes are absent — the pack itself is not installed.

**2. The Easy pack only survives as an API-format export.** Its frontend wraps
`app.graphToPrompt` and injects `media_1..media_15` / `media_type_1..15` into the **prompt half
only** — never into the saved UI-format graph. Because the wrapper sits on `app.graphToPrompt`
itself, ComfyUI's **Export (API)** produces a correct, self-contained workflow. Converting the
UI-format graph in Python (our `convert_to_api_format`) would silently drop every media link.

**3. API-format presets currently get no UI at all.** `editable.py:443` and `editable.py:673`
detect API format, log a warning, and return `[]`. Everything downstream already copes:
`modifier.modify_workflow:840` passes API-format workflows straight through, and
`submitter.py:428` already guards the UI-workflow-embedding step with `if 'nodes' in workflow`.
`_meta.title` carries the `_editable` marker through export intact — confirmed in our own golden
fixture `tests/fixtures/golden/pipeline__image_qwen_image_edit_2511.json`:

```json
"41": {"class_type": "LoadImage", "inputs": {"image": "..."}, "_meta": {"title": "Image 1_editable"}}
```

**4. The pack's headline features are authoring aids, not runtime machinery.** The `@` mention
popup, the reference editor and the `#` dialogue-block editor all reduce to literal text in the
prompt string (see *Referencing* below). The media multi-link port reduces to numbered optional
inputs that tolerate gaps. Both are reproducible from luma_tools without touching the pack.

The intended outcome: a "MiniMax H3" preset whose T2V / I2V / R2V variants expose prompt,
resolution, aspect ratio, duration, fps and the media slots as ordinary luma_tools controls, with
one selector per modality accepting multiple reference files.

## Design

### Phase 0 — Farm prerequisites (blocking, outside this repo)

`custom_nodes` and model weights are unmanaged by luma_tools; both are worker-local under
`comfyui_path` (`D:\ComfyUI`). On every worker in the ComfyUI group:

- Clone `ComfyUI-MiniMaxH3-Easy` into `D:\ComfyUI\ComfyUI\custom_nodes\`.
- Place weights (~40 GB; INT4 variants are ~11.3 GB each if VRAM is tight):

  | File | Folder | Size |
  |---|---|---|
  | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `models/diffusion_models/` | 19.5 GB |
  | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `models/diffusion_models/` | 19.5 GB |
  | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `models/text_encoders/` | 14.6 GB |
  | `minimax_h3_video_vae_fp16.safetensors` | `models/vae/` | 4.9 GB |
  | `minimax_h3_audio_vae_fp32.safetensors` | `models/vae/` | 0.6 GB |

- Restart the ComfyUI server job from the tab's Start/Stop/Restart controls. `server.py`'s
  `_save_node_info_to_network` (≈ line 935) republishes `/object_info` to the share.
- **Verify:** `MiniMaxH3Easy` appears in the network node_info cache. Phase 2's fan-out depends on
  it (see the cache-miss trap under *Risks*).

### Phase 1 — API-format editable/settings extraction

**File: `python/comfyui/editable.py`** — the only file needing a format branch.

Factor the per-node widget-building ladder out of `extract_editable_nodes` (lines 498–581) and
`extract_settings_nodes` (lines 703–767) into one helper:

```python
_build_widgets_for_node(node_id, node_type, title, ..., get_value, connected_inputs, configs)
```

`get_value(widget_name, widget_idx)` is the only thing that differs between formats. UI format
passes a closure doing the existing `widgets_values[widget_idx]` index lookup; API format passes
`inputs.get(widget_name)` — no index arithmetic at all.

Add an API iterator yielding `(node_id_str, class_type, title, inputs)` from `node["_meta"]["title"]`,
then replace both `is_api_format` bails with a dispatch into it.

API-specific details:

- `connected_inputs = {k for k, v in inputs.items() if _is_node_reference(v)}` — reuse
  `workflow._is_node_reference` (line 1288), which requires `[str, int]` so a genuine `[512, 512]`
  widget value isn't mistaken for a link.
- No mute/bypass handling (ComfyUI strips those at export) and no subgraph handling (already
  expanded). Both branches of the existing ladder simply don't apply.
- Keep `node_id` as the raw API key. `modifier._apply_editable_values:473` already normalises with
  `str(node_id)`, and `ui_manager._get_node_override:58` builds `f"{node_id}:{widget_name}"`, matching
  the `node_overrides` format in global settings (`"92:noise_seed"`).
- Widen the `EditableNode.node_id` / `SettingsNode.node_id` annotations to `Union[int, str]`.

### Phase 2 — Multiple references via slot fan-out

`MiniMaxH3Easy` declares `media_1..media_15` plus `media_type_1..15`, all **optional**. Its
collector tolerates gaps:

```python
for index in range(1, MAX_MEDIA + 1):
    value = kwargs.get(f"media_{index}")
    if value is None:
        continue
```

So one selector holding N files can expand into N loader nodes wired to N media slots at submit
time. Limits are 9 images / 3 videos / 3 audio in reference mode; image mode takes at most 2.

#### Title markers

Extend `_parse_editable_title` (`editable.py:35`) to return a **cardinality** alongside the existing
flags. The marker sits directly after `_editable`, before any `@if_` / `&if_` condition:

| Title | Meaning |
|---|---|
| `Ref Image_editable` | single value (today's behaviour, unchanged) |
| `Last Frame_editable?` | prunable — node removed when the artist leaves it empty |
| `Ref Images_editable*` | fan-out — one selector, N cloned loader nodes |
| `Ref Images_editable*@if_UseRefs` | fan-out plus the existing conditional |

`_parse_editable_title` currently returns a 3-tuple and is called twice inside
`extract_editable_nodes` (the title map at line 463 and the main loop at line 475); both call sites
need updating. `EditableNode` gains a `cardinality` field.

The `?` marker exists because an empty file value today means "keep the workflow default", and
changing that globally would break existing presets where a `LoadImage` deliberately keeps its
baked-in file.

#### Expansion

New `_expand_fanout_slots(workflow, editable_values)` in `modifier.py`, run inside
`modify_workflow_api_format` **before** `_apply_editable_values`. For each fan-out entry:

1. Locate the template node by id; scan all nodes' inputs for `[template_id, slot]` to find the
   consumer and input name (e.g. `MiniMaxH3Easy` / `media_1`).
2. Split the input name as `^(?P<prefix>.*?)(?P<idx>\d+)$`. No trailing integer ⇒ warn and fall back
   to single-value behaviour.
3. Collect **sibling inputs** — every consumer input whose trailing integer equals the template's.
   For `media_1` that finds `media_type_1` too. This is what makes the mechanism generic: nothing
   in the code names `media` or H3.
4. Allocate free indices from the consumer class's declared inputs (see the node_info change below),
   excluding indices already in use.
5. Apply the files, in selector order:
   - **0 files** → remove the template node via `remove_nodes_from_api_workflow` (`modifier.py:51`).
     `media_N` is optional, so the input is dropped without cascading.
   - **1 file** → write it into the template node. No clones.
   - **N files** → template takes `files[0]`; each subsequent file gets a deep-copied node under a
     fresh id (`max(int(k) for k in workflow if k.isdigit()) + 1`, incrementing) and the next free
     index `k`. Link-valued siblings become `[clone_id, slot]`; plain-valued siblings copy the
     template's value, so `media_type_k` inherits `"image"` automatically.
   - **More files than free indices** → truncate, log, and surface via the validation warning.
6. Drop the entry from `editable_values` so `_apply_editable_values` doesn't write it again.

Write **full paths** into the generated nodes. `normalize_file_paths_in_workflow` (`modifier.py:172`)
already basenames them, handles `.exr → .png` conversion naming, and records them in `files_to_copy`,
which `_stage_input` then copies — so no new staging code. `_stage_input` (`submitter.py:529`)
already iterates list values.

#### One required guard

`_collect_batch_images` (`submitter.py:242`) returns the first file-typed node's list and turns it
into **one Deadline job per file**. It must skip fan-out entries, or five references become five
single-reference jobs. Key off the `cardinality` flag, not the value type — both are lists.
Variation count for R2V presets still comes from the generation-count seeds, as it does today.

#### Supporting change

`node_info.py` — record the declared optional/all input names on `NodeTypeInfo` (a small addition to
`_parse_node_info`, line 248) so free-index allocation knows the slot ceiling. `_load_from_data`
already filters unknown fields (lines 395–400), so an older cache won't break. The pre-flight check
in Phase 4 can use the same data.

### Phase 3 — Referencing

The `@` popup, the reference editor and the `#` dialogue editor are **authoring aids only**. At
execution the pack does a single text substitution:

```python
REFERENCE_PLACEHOLDER_RE = re.compile(r"__MINIMAX_H3_REF_(\d+)__")
resolved = REFERENCE_PLACEHOLDER_RE.sub(
    lambda match: tag_by_input.get(int(match.group(1)), ""), source_prompt)
```

…and every token resolves to one of three strings, built per media type:

```python
tag_by_input[item.input_index] = f"<Picture {picture_ordinal}>"   # images
tag_by_input[item.input_index] = f"<Video {video_ordinal}>"       # videos
tag_by_input[item.input_index] = f"<Audio {audio_ordinal}>"       # audio
```

Anything that isn't a token passes through untouched, so **`<Picture 2>` typed literally in the
prompt is equivalent** — and strictly more robust for us: the token number is the media *slot*
index, whereas the ordinal means "the 2nd reference image" regardless of which slot fan-out assigned
it. Dialogue blocks are the same story: `<d>…</d>` has no Python handling at all and reaches the
text encoder verbatim, which is how H3 does speech.

So referencing needs **no submit-time logic**, only a typing aid:

- **Insert menu.** In the `text` branch of `ui_manager._create_editable_node_widget` (line 422), add
  an "@ Reference" button beside the existing Presets button. Build its menu lazily on click from
  the live fan-out selector contents so it always reflects the current files; label each entry with
  the filename and insert the literal tag at the cursor.
- **Non-blocking validation.** In `_validate_dynamic_inputs` (`tab.py:1860`), scan prompt values for
  `<(Picture|Video|Audio) (\d+)>` and warn when an ordinal exceeds the number of files selected for
  that type — H3 substitutes an empty string, which fails silently. Warn only; a prompt may
  legitimately contain angle-bracket text.
- **Hide `reference_mention_mode`.** It is declared in `INPUT_TYPES` and consumed nowhere in the
  pack. Disable it in the preset's exposed-parameters config so artists aren't given a dead control.

### Phase 4 — Audio widget type and pre-flight check

**Audio widget** — the four-step recipe in `python/comfyui/CLAUDE.md`, mirroring `video`:

1. `editable.py` — add `audio` to the `EditableNode.widget_type` docstring.
2. `ui_manager.py` — new branch alongside the `video` case at line 463, using
   `BatchImageSelector(supported_extensions=AUDIO_EXTENSIONS, file_type_label="audio")`
   (`AUDIO_EXTENSIONS` is at `core/config.py:367`).
3. `modifier.py` — `_apply_audio_widget` mirroring `_apply_video_widget` (line 402), writing the
   basename to `inputs['audio']`; register in `_WIDGET_APPLIERS` (line 431).
4. `node_configs.py` — `'LoadAudio': [('audio', 'audio')]` and
   `'VHS_LoadAudioUpload': [('audio', 'audio')]`. Both expose `audio` as a server-side combo, so the
   type override is required exactly as for `LoadImage`.

Two adjacent fixes:

- `node_configs.py:56` maps `'LoadVideo': [('video', 'video')]`, but `/object_info` reports
  `LoadVideo`'s input as `file`. This stops being cosmetic here: video references want the **native**
  `LoadVideo`, which returns a `VIDEO` object exposing `get_components()` — the pack's type inference
  keys on exactly that, whereas VHS returns plain IMAGE frames.
- `image_convert.py:20` — `COMFYUI_NATIVE_FORMATS` is images-only, so every audio and video input
  trips the misleading "may fail to load it" warning at line 191. Add a passthrough set.

Runner-side staging already handles audio — `LoadAudio` is in `utils._FILE_LOADER_TYPES` and `audio`
is in `_FILE_INPUT_NAMES` (line 1347).

**Pre-flight node availability check** — today a workflow referencing an uninstalled pack fails on
the farm minutes after Submit, though `node_info` already holds the full class list.

- `node_info.py` — add `get_known_class_types() -> Set[str]`, returning an empty set on a cache miss
  like every other accessor (lines 602–689).
- `tab.py:_validate_dynamic_inputs` (line 1860) — diff the workflow's `class_type`s against the cache
  and block with the missing names. **Skip entirely when the cache is empty or unavailable**, so a
  cold workstation never blocks a valid submission.

### Phase 5 — Author and register the presets

Authored in the ComfyUI browser on a worker, then **Export (API)**, saved to
`L:/tools/_studio_tools/luma_tools/comfyui/workflows/`.

- Title the `MiniMaxH3Easy` node `Video_editable`. Generic auto-discovery surfaces every widget —
  `mode`, `prompt`, `resolution`, `aspect_ratio`, `width`, `height`, `seconds`, `fps`,
  `keyframe_role`, `ref_image_size` — with no node-specific code. Hide `reference_mention_mode` and
  anything else artists shouldn't touch via the Model dialog's **Exposed parameters** tab
  (`model_dialog.py:545`), which writes `node_overrides`.
- One loader per modality, marked fan-out: `Ref Images_editable*` (LoadImage),
  `Ref Video_editable*` (native LoadVideo), `Ref Audio_editable*` (LoadAudio). Wire each to
  `media_1`, `media_2`, `media_3`; fan-out allocates the rest.
- For I2V, mark the last-frame slot `Last Frame_editable?` so leaving it empty gives first-frame-only.
- Title the save node `Result_output` using `SaveVideo` — already in `EXPORT_NODE_TYPES` with
  `filename_prefix`. (`VHS_VideoCombine` is **not** registered; if a workflow needs it, add it to
  `EXPORT_NODE_TYPES` → `filename_prefix` in the same pass.)
- Register as one multi-workflow preset (`is_multi: true`, `output_type: "video"`) with variants
  `T2V`, `I2V`, `R2V`, matching the existing Trellis 2 SingleView/MultiViews pattern. Variants now
  distinguish *mode*, not reference count.
- Use the preset `note` field to document `<Picture n>` / `<d>…</d>` syntax.

### Optional polish

A collapsible group for the main editable panel. Fan-out reduces R2V to three selectors, so this is
no longer load-bearing — but `MiniMaxH3Easy` still exposes ~11 widgets. Only worth doing if the
panel feels crowded in practice.

## Verification

1. **Unit** — extend `tests/test_workflow.py`; add editable-extraction cases proving an API-format
   fixture with `_meta.title` markers yields the same `EditableNode` set as the equivalent UI-format
   fixture, including `connected_inputs` suppression. Add fan-out cases: 0 / 1 / N files, N beyond
   the slot ceiling, and correct `media_type_k` inheritance. Run
   `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`.
2. **Farm isolation** — `tests/test_farm_isolation.py` must still pass; `node_configs.py` is copied to
   the farm as `comfyui_node_configs.py`, so the audio entries must not introduce imports.
3. **Regression** — submit existing UI-format presets (LTX2 Video, Qwen image edit) and confirm the
   dynamic UI, batching and outputs are unchanged. This is the main risk of the Phase 1 refactor and
   the `_collect_batch_images` change.
4. **App run** — `python\core\luma_tools.py --tab comfyui --auto-close 60`, then read the latest log
   under `W:\LumaRND\luma_tools\_logs\users\`. Confirm the API-format H3 preset builds controls and
   logs no "is in API format" warning.
5. **End-to-end** — one generation per variant; for R2V use 3 images + 1 video + 1 audio and a prompt
   referencing `<Picture 2>` and `<Audio 1>`. Inspect the submitted API workflow in `_job_data/` to
   confirm the generated loader nodes and `media_N` / `media_type_N` wiring, then confirm
   video-with-audio lands in the Gallery with `output_type: "video"`.
6. **Pre-flight** — rename a class in a test workflow, confirm Submit blocks naming it, and confirm an
   empty node_info cache does not block.

## Risks

- **Phase 1 refactor touches the shared ladder** used by every existing preset. Mitigated by keeping
  `get_value` the only variable and regression-testing UI-format presets before shipping.
- **Fan-out and pruning depend on a fresh node_info cache.** `remove_nodes_from_api_workflow:116`
  falls back to "assume all inputs are required" on a cache miss, which would cascade-remove the
  `MiniMaxH3Easy` node itself. Correct once the pack is installed and `/object_info` republished; the
  Phase 4 pre-flight check catches the window before that.
- **Re-export discipline.** An API-format preset can't be round-tripped through luma_tools; graph
  changes mean re-exporting from the browser. The dangerous case is exporting *UI* format by mistake —
  it loads, shows controls, submits, and silently produces garbage because the media links only exist
  in the API export. The pre-flight check won't catch it; warn when a UI-format workflow contains
  `MiniMaxH3Easy`.
- **Reference ordinals follow selector order.** Reordering files in a selector shifts what
  `<Picture 2>` means. The insert menu is built live and the selector numbers its files, so this is
  visible — but it is the one place an artist can silently get a wrong result.
