"""Tests for comfyui.modifier — workflow modification, file path detection, node removal."""

import copy

import pytest

from comfyui.modifier import (
    _is_file_path,
    _is_link,
    FILE_EXTENSIONS,
    normalize_file_paths_in_workflow,
    remove_nodes_from_api_workflow,
)


# ============================================================================
# _is_file_path
# ============================================================================

class TestIsFilePath:
    def test_image_extensions(self):
        assert _is_file_path("render.exr") is True
        assert _is_file_path("photo.jpg") is True
        assert _is_file_path("image.png") is True

    def test_video_extensions(self):
        assert _is_file_path("clip.mp4") is True
        assert _is_file_path("movie.mov") is True

    def test_model_extensions(self):
        assert _is_file_path("model.glb") is True
        assert _is_file_path("scene.usd") is True

    def test_non_file(self):
        assert _is_file_path("hello world") is False
        assert _is_file_path("some_text") is False

    def test_non_string(self):
        assert _is_file_path(123) is False
        assert _is_file_path(None) is False
        assert _is_file_path([]) is False

    def test_case_insensitive(self):
        assert _is_file_path("IMAGE.PNG") is True
        assert _is_file_path("Video.MP4") is True


# ============================================================================
# _is_link
# ============================================================================

class TestIsLink:
    def test_valid_link(self):
        assert _is_link(["5", 0]) is True
        assert _is_link([10, 1]) is True

    def test_not_a_link(self):
        assert _is_link("not a link") is False
        assert _is_link([1, 2, 3]) is False  # Wrong length
        assert _is_link([1, "not_int"]) is False  # Slot not int
        assert _is_link([]) is False
        assert _is_link(None) is False


# ============================================================================
# remove_nodes_from_api_workflow
# ============================================================================

class TestRemoveNodesFromApiWorkflow:
    def _sample_workflow(self):
        """Simple linear workflow: node1 -> node2 -> node3"""
        return {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": "test.png"},
            },
            "2": {
                "class_type": "PreviewImage",
                "inputs": {"images": ["1", 0]},
            },
            "3": {
                "class_type": "SaveImage",
                "inputs": {"images": ["2", 0], "filename_prefix": "output"},
            },
        }

    def test_empty_set_no_change(self):
        wf = self._sample_workflow()
        original = copy.deepcopy(wf)
        remove_nodes_from_api_workflow(wf, set())
        assert wf == original

    def test_remove_leaf_node(self):
        wf = self._sample_workflow()
        remove_nodes_from_api_workflow(wf, {"3"})
        assert "3" not in wf
        assert "1" in wf
        assert "2" in wf

    def test_remove_middle_node_reroutes(self):
        wf = self._sample_workflow()
        # Remove node2 — node3 should reroute to node1
        remove_nodes_from_api_workflow(wf, {"2"})
        assert "2" not in wf
        assert "1" in wf
        assert "3" in wf
        # node3.images should now point to node1
        assert wf["3"]["inputs"]["images"] == ["1", 0]

    def test_remove_source_node(self):
        wf = self._sample_workflow()
        # Remove node1 — downstream nodes lose their input
        remove_nodes_from_api_workflow(wf, {"1"})
        assert "1" not in wf

    def test_remove_nonexistent_node(self):
        wf = self._sample_workflow()
        remove_nodes_from_api_workflow(wf, {"999"})
        # Should not crash, workflow unchanged
        assert len(wf) == 3


# ============================================================================
# normalize_file_paths_in_workflow
# ============================================================================

class TestNormalizeFilePathsInWorkflow:
    def test_normalizes_absolute_path(self, tmp_path):
        # Create a real file so the function doesn't skip it
        img = tmp_path / "test.png"
        img.write_text("")
        wf = {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": str(img)},
            }
        }
        files_to_copy = normalize_file_paths_in_workflow(wf)
        assert wf["1"]["inputs"]["image"] == "test.png"
        assert str(img) in files_to_copy

    def test_skips_basenames(self):
        wf = {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": "already_basename.png"},
            }
        }
        files_to_copy = normalize_file_paths_in_workflow(wf)
        assert files_to_copy == {}
        assert wf["1"]["inputs"]["image"] == "already_basename.png"

    def test_skips_non_file_values(self):
        wf = {
            "1": {
                "class_type": "KSampler",
                "inputs": {"seed": 12345, "steps": 20},
            }
        }
        files_to_copy = normalize_file_paths_in_workflow(wf)
        assert files_to_copy == {}

    def test_skips_link_values(self):
        wf = {
            "1": {
                "class_type": "SaveImage",
                "inputs": {"images": ["2", 0]},
            }
        }
        files_to_copy = normalize_file_paths_in_workflow(wf)
        assert files_to_copy == {}


# ============================================================================
# Audio widget type
# ============================================================================

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

    def test_vhs_loadaudioupload_registered(self):
        from comfyui.node_configs import EDITABLE_NODE_CONFIGS
        assert EDITABLE_NODE_CONFIGS["VHS_LoadAudioUpload"] == [("audio", "audio")]

    def test_loadvideo_uses_correct_input_name(self):
        """/object_info reports the native LoadVideo's input as 'file', not 'video'."""
        from comfyui.node_configs import EDITABLE_NODE_CONFIGS
        assert EDITABLE_NODE_CONFIGS["LoadVideo"] == [("file", "video")]


class TestPassthroughFormats:
    def test_audio_and_video_are_passthrough(self):
        from comfyui.image_convert import COMFYUI_PASSTHROUGH_FORMATS
        assert {".wav", ".mp3", ".mp4", ".mov"} <= COMFYUI_PASSTHROUGH_FORMATS

    def test_passthrough_does_not_overlap_native(self):
        from comfyui.image_convert import (COMFYUI_PASSTHROUGH_FORMATS,
                                           COMFYUI_NATIVE_FORMATS)
        assert not (COMFYUI_PASSTHROUGH_FORMATS & COMFYUI_NATIVE_FORMATS)


# ============================================================================
# Fan-out slot expansion
# ============================================================================

class TestSplitIndexedName:
    def test_splits_trailing_int(self):
        from comfyui.modifier import _split_indexed_name
        assert _split_indexed_name("media_1") == ("media_", 1)
        assert _split_indexed_name("media_type_12") == ("media_type_", 12)

    def test_none_without_trailing_int(self):
        from comfyui.modifier import _split_indexed_name
        assert _split_indexed_name("image") is None
        assert _split_indexed_name("") is None


def _fanout_workflow():
    return {
        "41": {"class_type": "LoadImage", "inputs": {"image": "a.png"},
               "_meta": {"title": "Ref Images_editable*"}},
        "50": {"class_type": "MiniMaxH3Easy",
               "inputs": {"prompt": "hi", "media_1": ["41", 0], "media_type_1": "image"},
               "_meta": {"title": "Video_editable"}},
    }


def _fanout_values(files, cardinality=None):
    from comfyui.editable import EditableNode, CARDINALITY_MANY
    node = EditableNode(node_id="41", node_type="LoadImage",
                        title="Ref Images_editable*", display_name="Ref Images",
                        widget_type="image", widget_name="image",
                        cardinality=cardinality or CARDINALITY_MANY)
    return {"41": [{"node": node, "value": files}]}


@pytest.fixture
def h3_slots(monkeypatch):
    """MiniMaxH3Easy declares media_1..media_15 plus media_type_1..15.

    The real ceiling comes from the node_info cache, which only has the class
    once the node pack is installed on the farm, so tests supply it directly.
    """
    import comfyui.node_info as ni
    declared = ([f"media_{i}" for i in range(1, 16)]
                + [f"media_type_{i}" for i in range(1, 16)])
    monkeypatch.setattr(
        ni, "get_optional_input_names",
        lambda class_type: declared if class_type == "MiniMaxH3Easy" else None)
    return declared


class TestFanoutSlots:
    def test_single_file_writes_template_only(self):
        from comfyui.modifier import _expand_fanout_slots
        wf, vals = _fanout_workflow(), _fanout_values([r"C:\r\one.png"])
        _expand_fanout_slots(wf, vals)
        assert wf["41"]["inputs"]["image"] == r"C:\r\one.png"
        assert len(wf) == 2
        # The entry stays in editable_values (the submitter reads it for
        # metadata/hashes); _apply_editable_values skips it by cardinality.
        assert "41" in vals

    def test_three_files_create_two_clones(self, h3_slots):
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        _expand_fanout_slots(wf, _fanout_values([r"C:\r\1.png", r"C:\r\2.png", r"C:\r\3.png"]))
        loaders = [n for n in wf.values() if n["class_type"] == "LoadImage"]
        assert len(loaders) == 3
        assert {n["inputs"]["image"] for n in loaders} == {
            r"C:\r\1.png", r"C:\r\2.png", r"C:\r\3.png"}

    def test_clones_wired_to_distinct_free_slots(self, h3_slots):
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        _expand_fanout_slots(wf, _fanout_values([r"C:\r\1.png", r"C:\r\2.png", r"C:\r\3.png"]))
        consumer = wf["50"]["inputs"]
        assert consumer["media_1"] == ["41", 0]
        assert "media_2" in consumer and "media_3" in consumer
        assert len({consumer[k][0] for k in ("media_1", "media_2", "media_3")}) == 3

    def test_sibling_media_type_duplicated(self, h3_slots):
        """media_type_N must follow media_N without the code naming either."""
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        _expand_fanout_slots(wf, _fanout_values([r"C:\r\1.png", r"C:\r\2.png"]))
        assert wf["50"]["inputs"]["media_type_2"] == "image"

    def test_zero_files_removes_template_and_input(self):
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        _expand_fanout_slots(wf, _fanout_values([]))
        assert "41" not in wf
        assert "media_1" not in wf["50"]["inputs"]
        assert "50" in wf  # optional input lost -> no cascade

    def test_single_cardinality_untouched(self):
        from comfyui.modifier import _expand_fanout_slots
        from comfyui.editable import CARDINALITY_SINGLE
        wf = _fanout_workflow()
        vals = _fanout_values([r"C:\r\1.png", r"C:\r\2.png"], CARDINALITY_SINGLE)
        _expand_fanout_slots(wf, vals)
        assert len(wf) == 2
        assert vals != {}  # left for the normal appliers

    def test_clone_preserves_class_type(self, h3_slots):
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        _expand_fanout_slots(wf, _fanout_values([r"C:\r\1.png", r"C:\r\2.png"]))
        new_ids = set(wf) - {"41", "50"}
        assert all(wf[i]["class_type"] == "LoadImage" for i in new_ids)

    def test_full_paths_written_for_later_normalization(self, h3_slots):
        """Paths stay absolute so normalize_file_paths_in_workflow collects them."""
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        _expand_fanout_slots(wf, _fanout_values([r"C:\r\1.png", r"C:\r\2.png"]))
        assert all("\\" in n["inputs"]["image"]
                   for n in wf.values() if n["class_type"] == "LoadImage")


    def test_unknown_consumer_keeps_first_file_and_warns(self, caplog):
        """Without a node_info entry the slot ceiling is unknowable.

        Writing an undeclared input would be dropped by ComfyUI silently, so
        the extra files must be refused loudly rather than fanned out.
        """
        import logging
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        with caplog.at_level(logging.WARNING):
            _expand_fanout_slots(wf, _fanout_values(['C:/r/1.png', 'C:/r/2.png']))
        assert len([n for n in wf.values() if n['class_type'] == 'LoadImage']) == 1
        assert wf['41']['inputs']['image'] == 'C:/r/1.png'
        assert any('cannot allocate slots' in r.message for r in caplog.records)

    def test_zero_files_keeps_consumer_on_cache_miss(self):
        """Regression: the empty path must not cascade into the consumer.

        remove_nodes_from_api_workflow treats a node_info cache miss as
        "all inputs required", which would delete MiniMaxH3Easy itself.
        """
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        _expand_fanout_slots(wf, _fanout_values([]))
        assert '50' in wf
        assert wf['50']['inputs']['prompt'] == 'hi'
        assert 'media_type_1' not in wf['50']['inputs']


class TestFanoutDoesNotMutateEditableValues:
    """submit_comfyui_job reads the same dict after modify_workflow for
    gallery metadata and content hashes — pruning it silently loses every
    fan-out reference file from the job's record."""

    def test_entry_survives_expansion(self):
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        vals = _fanout_values(["C:/r/1.png"])
        _expand_fanout_slots(wf, vals)
        assert "41" in vals
        assert vals["41"][0]["value"] == ["C:/r/1.png"]

    def test_empty_entry_survives_removal(self):
        from comfyui.modifier import _expand_fanout_slots
        wf = _fanout_workflow()
        vals = _fanout_values([])
        _expand_fanout_slots(wf, vals)
        assert "41" in vals


class TestFanoutSiblingWiring:
    """Each sibling input must keep its own output slot and its own source —
    wiring a MASK input to an IMAGE output type-fails on the farm, and an
    input fed by an unrelated node must not be rehomed onto the clone."""

    def test_multi_output_template_keeps_slot_per_sibling(self, h3_slots):
        from comfyui.modifier import _expand_fanout_slots
        wf = {
            "41": {"class_type": "LoadImage", "inputs": {"image": "a.png"},
                   "_meta": {"title": "Refs_editable*"}},
            "50": {"class_type": "MiniMaxH3Easy",
                   "inputs": {"prompt": "hi",
                              "media_1": ["41", 0],
                              "media_type_1": "image",
                              "mask_1": ["41", 1]},
                   "_meta": {"title": "Video_editable"}},
        }
        _expand_fanout_slots(wf, _fanout_values(["C:/r/1.png", "C:/r/2.png"]))
        clone_id = wf["50"]["inputs"]["media_2"][0]
        assert wf["50"]["inputs"]["media_2"] == [clone_id, 0]
        assert wf["50"]["inputs"]["mask_2"] == [clone_id, 1]

    def test_sibling_fed_by_other_node_is_not_rehomed(self, h3_slots):
        from comfyui.modifier import _expand_fanout_slots
        wf = {
            "41": {"class_type": "LoadImage", "inputs": {"image": "a.png"},
                   "_meta": {"title": "Refs_editable*"}},
            "77": {"class_type": "StyleModel", "inputs": {},
                   "_meta": {"title": "Style"}},
            "50": {"class_type": "MiniMaxH3Easy",
                   "inputs": {"prompt": "hi",
                              "media_1": ["41", 0],
                              "media_type_1": "image",
                              "media_style_1": ["77", 0]},
                   "_meta": {"title": "Video_editable"}},
        }
        _expand_fanout_slots(wf, _fanout_values(["C:/r/1.png", "C:/r/2.png"]))
        assert wf["50"]["inputs"]["media_style_2"] == ["77", 0]
        # And the original stays put
        assert wf["50"]["inputs"]["media_style_1"] == ["77", 0]


class TestFanoutSlotFamilies:
    """Unrelated numbered inputs on the same consumer (lora_1 next to
    media_1) are a different slot family: they must not travel with a clone,
    block a free slot, or be deleted when the slot empties."""

    def _workflow(self, extra_inputs):
        inputs = {"prompt": "hi", "media_1": ["41", 0], "media_type_1": "image"}
        inputs.update(extra_inputs)
        return {
            "41": {"class_type": "LoadImage", "inputs": {"image": "a.png"},
                   "_meta": {"title": "Refs_editable*"}},
            "50": {"class_type": "MiniMaxH3Easy", "inputs": inputs,
                   "_meta": {"title": "Video_editable"}},
        }

    def test_unrelated_input_does_not_travel_with_clone(self, h3_slots):
        from comfyui.modifier import _expand_fanout_slots
        wf = self._workflow({"lora_1": "style.safetensors"})
        _expand_fanout_slots(wf, _fanout_values(["C:/r/1.png", "C:/r/2.png"]))
        assert "media_2" in wf["50"]["inputs"]
        assert "lora_2" not in wf["50"]["inputs"]

    def test_unrelated_input_does_not_block_a_free_slot(self, h3_slots):
        from comfyui.modifier import _expand_fanout_slots
        wf = self._workflow({"lora_2": "style.safetensors"})
        _expand_fanout_slots(wf, _fanout_values(["C:/r/1.png", "C:/r/2.png"]))
        # Slot 2 is free for the media family; lora_2 must not push it to 3
        clone_id = wf["50"]["inputs"]["media_2"][0]
        assert wf["50"]["inputs"]["media_2"] == [clone_id, 0]
        assert wf["50"]["inputs"]["lora_2"] == "style.safetensors"

    def test_unrelated_input_survives_empty_slot_removal(self):
        from comfyui.modifier import _expand_fanout_slots
        wf = self._workflow({"lora_1": "style.safetensors"})
        _expand_fanout_slots(wf, _fanout_values([]))
        assert "41" not in wf
        assert "media_1" not in wf["50"]["inputs"]
        assert "media_type_1" not in wf["50"]["inputs"]
        assert wf["50"]["inputs"]["lora_1"] == "style.safetensors"

    def test_empty_slot_with_unindexed_input_does_not_dangle(self):
        """Same guarantee the optional path has: no link left pointing at a
        removed template."""
        from comfyui.modifier import _expand_fanout_slots
        wf = {
            "41": {"class_type": "LoadImage", "inputs": {"image": "a.png"},
                   "_meta": {"title": "Refs_editable*"}},
            "50": {"class_type": "MiniMaxH3Easy",
                   "inputs": {"prompt": "hi", "reference_image": ["41", 0]},
                   "_meta": {"title": "Video_editable"}},
        }
        _expand_fanout_slots(wf, _fanout_values([]))
        assert "41" not in wf
        assert "reference_image" not in wf["50"]["inputs"]


# ============================================================================
# Optional slots: 'Name_editable?' removes the node when left empty
# ============================================================================

class TestOptionalSlots:
    """Documented in python/comfyui/CLAUDE.md: the node is removed from the
    workflow when the slot is left empty; when filled it behaves like a
    normal single slot."""

    def _workflow(self, consumer_input="media_1", extra_inputs=None):
        inputs = {"prompt": "hi", consumer_input: ["41", 0]}
        inputs.update(extra_inputs or {})
        return {
            "41": {"class_type": "LoadImage", "inputs": {"image": "stale.png"},
                   "_meta": {"title": "Last Frame_editable?"}},
            "50": {"class_type": "MiniMaxH3Easy", "inputs": inputs,
                   "_meta": {"title": "Video_editable"}},
        }

    def _values(self, files, widget_type="image"):
        from comfyui.editable import EditableNode, CARDINALITY_OPTIONAL
        node = EditableNode(node_id="41", node_type="LoadImage",
                            title="Last Frame_editable?", display_name="Last Frame",
                            widget_type=widget_type, widget_name="image",
                            cardinality=CARDINALITY_OPTIONAL)
        return {"41": [{"node": node, "value": files}]}

    def test_empty_removes_node_and_indexed_inputs(self):
        from comfyui.modifier import _remove_empty_optional_slots
        wf = self._workflow(extra_inputs={"media_type_1": "image"})
        _remove_empty_optional_slots(wf, self._values([]))
        assert "41" not in wf
        assert "media_1" not in wf["50"]["inputs"]
        assert "media_type_1" not in wf["50"]["inputs"]
        assert wf["50"]["inputs"]["prompt"] == "hi"

    def test_empty_unindexed_input_does_not_dangle(self):
        """A consumer input without a trailing index must still be dropped —
        a link to a removed node fails the whole prompt on the farm."""
        from comfyui.modifier import _remove_empty_optional_slots
        wf = self._workflow(consumer_input="reference_image")
        _remove_empty_optional_slots(wf, self._values([]))
        assert "41" not in wf
        assert "reference_image" not in wf["50"]["inputs"]

    def test_selected_file_keeps_node(self):
        from comfyui.modifier import _remove_empty_optional_slots
        wf = self._workflow()
        _remove_empty_optional_slots(wf, self._values(["C:/r/last.png"]))
        assert "41" in wf
        assert wf["50"]["inputs"]["media_1"] == ["41", 0]

    def test_single_cardinality_slot_is_untouched(self):
        from comfyui.modifier import _remove_empty_optional_slots
        from comfyui.editable import CARDINALITY_SINGLE
        wf = self._workflow()
        values = self._values([])
        values["41"][0]["node"].cardinality = CARDINALITY_SINGLE
        _remove_empty_optional_slots(wf, values)
        assert "41" in wf

    def test_non_file_widget_is_untouched(self):
        """'Empty' is only unambiguous for file slots — a False toggle or
        blank combo must not delete its node."""
        from comfyui.modifier import _remove_empty_optional_slots
        wf = self._workflow()
        _remove_empty_optional_slots(wf, self._values(False, widget_type="toggle"))
        assert "41" in wf


# ============================================================================
# Deadline batching must not split fan-out slots
# ============================================================================

class TestCollectBatchImagesSkipsFanout:
    def _node(self, cardinality):
        from comfyui.editable import EditableNode
        return EditableNode(node_id="41", node_type="LoadImage",
                            title="Refs_editable*", display_name="Refs",
                            widget_type="image", widget_name="image",
                            cardinality=cardinality)

    def _files(self, tmp_path, *names):
        out = []
        for name in names:
            p = tmp_path / name
            p.write_bytes(b"x")
            out.append(str(p))
        return out

    def test_fanout_slot_is_not_batched(self, tmp_path):
        """N references belong to ONE generation, not N jobs."""
        from deadline.submitter import _collect_batch_images
        from comfyui.editable import CARDINALITY_MANY
        files = self._files(tmp_path, "a.png", "b.png")
        paths, node_id = _collect_batch_images(
            {"41": [{"node": self._node(CARDINALITY_MANY), "value": files}]})
        assert paths == []
        assert node_id is None

    def test_normal_slot_still_batches(self, tmp_path):
        from deadline.submitter import _collect_batch_images
        from comfyui.editable import CARDINALITY_SINGLE
        files = self._files(tmp_path, "c.png", "d.png")
        paths, node_id = _collect_batch_images(
            {"41": [{"node": self._node(CARDINALITY_SINGLE), "value": files}]})
        assert paths == files
        assert node_id == "41"

    def test_normal_slot_wins_when_mixed(self, tmp_path):
        """A fan-out slot must not shadow a real batching slot."""
        from deadline.submitter import _collect_batch_images
        from comfyui.editable import (EditableNode, CARDINALITY_MANY,
                                      CARDINALITY_SINGLE)
        refs = self._files(tmp_path, "r1.png", "r2.png")
        batch = self._files(tmp_path, "b1.png")
        single = EditableNode(node_id="42", node_type="LoadImage",
                              title="Input_editable", display_name="Input",
                              widget_type="image", widget_name="image",
                              cardinality=CARDINALITY_SINGLE)
        paths, node_id = _collect_batch_images({
            "41": [{"node": self._node(CARDINALITY_MANY), "value": refs}],
            "42": [{"node": single, "value": batch}],
        })
        assert paths == batch
        assert node_id == "42"


class TestFileWidgetAppliersHonorWidgetName:
    """Native LoadVideo's input is 'file' (node_configs maps ('file', 'video')).
    The applier must write the configured input name, not a hardcoded one —
    an undeclared input is silently dropped by ComfyUI."""

    def test_video_applier_writes_configured_input(self):
        from comfyui.modifier import _apply_video_widget
        inputs = {'file': 'stale.mp4'}
        _apply_video_widget(inputs, ['C:/refs/clip.mp4'], 'file', '9', 'LoadVideo')
        assert inputs['file'] == 'clip.mp4'
        assert 'video' not in inputs

    def test_video_applier_falls_back_to_video(self):
        from comfyui.modifier import _apply_video_widget
        inputs = {'video': 'stale.mp4'}
        _apply_video_widget(inputs, ['C:/refs/clip.mp4'], '', '9', 'VHS_LoadVideo')
        assert inputs['video'] == 'clip.mp4'

    def test_model_applier_writes_configured_input(self):
        from comfyui.modifier import _apply_model_widget
        inputs = {'mesh': 'stale.glb'}
        _apply_model_widget(inputs, ['C:/refs/head.glb'], 'mesh', '9', 'LoadMesh')
        assert inputs['mesh'] == 'head.glb'
        assert 'model_file' not in inputs

    def test_model_applier_falls_back_to_model_file(self):
        from comfyui.modifier import _apply_model_widget
        inputs = {'model_file': 'stale.glb'}
        _apply_model_widget(inputs, ['C:/refs/head.glb'], '', '9', 'Load3D')
        assert inputs['model_file'] == 'head.glb'


class TestCollectFilesToStage:
    """Every file-typed editable slot — audio included — must be staged to the
    farm working dir; the farm has no access to workstation paths."""

    def _entry(self, widget_type, value, node_id="7"):
        from comfyui.editable import EditableNode
        node = EditableNode(node_id=node_id, node_type="X",
                            title="X_editable", display_name="X",
                            widget_type=widget_type, widget_name=widget_type)
        return {node_id: [{"node": node, "value": value}]}

    def test_audio_file_is_staged(self, tmp_path):
        from deadline.submitter import _collect_files_to_stage
        wav = tmp_path / "voice.wav"
        wav.write_bytes(b"x")
        files = _collect_files_to_stage(self._entry("audio", [str(wav)]))
        assert [f for f, _ in files] == [str(wav)]

    def test_image_string_value_is_staged(self, tmp_path):
        from deadline.submitter import _collect_files_to_stage
        png = tmp_path / "a.png"
        png.write_bytes(b"x")
        files = _collect_files_to_stage(self._entry("image", str(png)))
        assert [f for f, _ in files] == [str(png)]

    def test_primary_input_is_excluded(self, tmp_path):
        from deadline.submitter import _collect_files_to_stage
        png = tmp_path / "a.png"
        png.write_bytes(b"x")
        files = _collect_files_to_stage(self._entry("image", [str(png)]),
                                        exclude=str(png))
        assert files == []

    def test_missing_and_non_file_slots_are_skipped(self, tmp_path):
        from deadline.submitter import _collect_files_to_stage
        values = self._entry("audio", [str(tmp_path / "gone.wav")])
        values.update(self._entry("text", "a prompt", node_id="8"))
        assert _collect_files_to_stage(values) == []


class TestApplyBatchFileToValues:
    """API-format extraction keys nodes by JSON dict key, so node_id is a
    string — the per-file override must handle that, not just legacy ints."""

    def _values(self, node_id):
        from comfyui.editable import EditableNode, CARDINALITY_SINGLE
        node = EditableNode(node_id=node_id, node_type="LoadImage",
                            title="Input_editable", display_name="Input",
                            widget_type="image", widget_name="image",
                            cardinality=CARDINALITY_SINGLE)
        return {node_id: [{"node": node, "value": ["old.png"]}]}

    def test_string_node_id_gets_current_file(self):
        from deadline.submitter import _apply_batch_file_to_values
        values = self._values("43")
        _apply_batch_file_to_values(values, "43", "C:/batch/new.png")
        assert values["43"][0]["value"] == "C:/batch/new.png"

    def test_int_node_id_still_works(self):
        from deadline.submitter import _apply_batch_file_to_values
        values = self._values(43)
        _apply_batch_file_to_values(values, 43, "C:/batch/new.png")
        assert values[43][0]["value"] == "C:/batch/new.png"

    def test_no_batch_slot_is_a_no_op(self):
        from deadline.submitter import _apply_batch_file_to_values, _collect_batch_images
        _, sentinel = _collect_batch_images(None)
        values = self._values("43")
        _apply_batch_file_to_values(values, sentinel, "C:/batch/new.png")
        assert values["43"][0]["value"] == ["old.png"]


# ============================================================================
# Submit-time validation
# ============================================================================

class TestMissingNodeTypesUIFormat:
    """The UI-format branch must mirror what actually executes: muted nodes
    are dropped before submission, while subgraph definitions are inlined
    into real class types."""

    _SG_A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"
    _SG_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0002"

    def test_muted_node_of_unknown_type_is_not_missing(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"nodes": [{"type": "LoadImage", "mode": 0},
                        {"type": "ExperimentalNode", "mode": 2}]}
        assert collect_missing_node_types(wf, {"LoadImage"}) == []

    def test_bypassed_node_of_unknown_type_is_not_missing(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"nodes": [{"type": "LoadImage", "mode": 0},
                        {"type": "ExperimentalNode", "mode": 4}]}
        assert collect_missing_node_types(wf, {"LoadImage"}) == []

    def test_unknown_type_inside_used_subgraph_is_missing(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {
            "nodes": [{"type": self._SG_A, "mode": 0}],
            "definitions": {"subgraphs": [
                {"id": self._SG_A,
                 "nodes": [{"type": "MiniMaxH3Easy", "mode": 0}]},
            ]},
        }
        assert collect_missing_node_types(wf, {"LoadImage"}) == ["MiniMaxH3Easy"]

    def test_unknown_type_inside_unused_subgraph_is_not_missing(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {
            "nodes": [{"type": "LoadImage", "mode": 0}],
            "definitions": {"subgraphs": [
                {"id": self._SG_A,
                 "nodes": [{"type": "MiniMaxH3Easy", "mode": 0}]},
            ]},
        }
        assert collect_missing_node_types(wf, {"LoadImage"}) == []

    def test_nested_subgraphs_are_walked(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {
            "nodes": [{"type": self._SG_A, "mode": 0}],
            "definitions": {"subgraphs": [
                {"id": self._SG_A, "nodes": [{"type": self._SG_B, "mode": 0}]},
                {"id": self._SG_B,
                 "nodes": [{"type": "MiniMaxH3Easy", "mode": 0}]},
            ]},
        }
        assert collect_missing_node_types(wf, {"LoadImage"}) == ["MiniMaxH3Easy"]

    def test_muted_subgraph_instance_is_not_descended(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {
            "nodes": [{"type": "LoadImage", "mode": 0},
                      {"type": self._SG_A, "mode": 2}],
            "definitions": {"subgraphs": [
                {"id": self._SG_A,
                 "nodes": [{"type": "MiniMaxH3Easy", "mode": 0}]},
            ]},
        }
        assert collect_missing_node_types(wf, {"LoadImage"}) == []


class TestMissingNodeTypes:
    def test_reports_missing(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"1": {"class_type": "LoadImage", "inputs": {}},
              "2": {"class_type": "MiniMaxH3Easy", "inputs": {}}}
        assert collect_missing_node_types(wf, {"LoadImage"}) == ["MiniMaxH3Easy"]

    def test_empty_cache_reports_nothing(self):
        """A cold workstation must never block a valid submission."""
        from comfyui.workflow import collect_missing_node_types
        wf = {"1": {"class_type": "Whatever", "inputs": {}}}
        assert collect_missing_node_types(wf, set()) == []

    def test_all_known_is_clean(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"1": {"class_type": "LoadImage", "inputs": {}}}
        assert collect_missing_node_types(wf, {"LoadImage", "SaveImage"}) == []

    def test_ui_format_supported(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"nodes": [{"id": 1, "type": "LoadImage"}, {"id": 2, "type": "Nope"}]}
        assert collect_missing_node_types(wf, {"LoadImage"}) == ["Nope"]

    def test_uuid_subgraph_nodes_ignored(self):
        """Subgraph instances are expanded later; they are not class types."""
        from comfyui.workflow import collect_missing_node_types
        wf = {"nodes": [{"id": 1, "type": "0f8c1e2a-3b4d-5e6f-7a8b-9c0d1e2f3a4b"}]}
        assert collect_missing_node_types(wf, {"LoadImage"}) == []

    def test_result_is_sorted(self):
        from comfyui.workflow import collect_missing_node_types
        wf = {"1": {"class_type": "Zeta", "inputs": {}},
              "2": {"class_type": "Alpha", "inputs": {}}}
        assert collect_missing_node_types(wf, {"LoadImage"}) == ["Alpha", "Zeta"]


class TestReferenceTagValidation:
    def test_out_of_range_picture(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "a <Picture 3> b", {"image": 2, "video": 0, "audio": 0}) == ["<Picture 3>"]

    def test_in_range_is_clean(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "<Picture 1> and <Picture 2>", {"image": 2, "video": 0, "audio": 0}) == []

    def test_types_counted_separately(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "<Video 1> <Audio 2>", {"image": 9, "video": 1, "audio": 1}) == ["<Audio 2>"]

    def test_dialogue_tags_ignored(self):
        """<d>...</d> is speech markup, not a reference."""
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "<d>hello there</d>", {"image": 0, "video": 0, "audio": 0}) == []

    def test_empty_prompt_is_clean(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags("", {"image": 0}) == []
        assert find_out_of_range_reference_tags(None, {"image": 0}) == []

    def test_zero_ordinal_flagged(self):
        from comfyui.editable import find_out_of_range_reference_tags
        assert find_out_of_range_reference_tags(
            "<Picture 0>", {"image": 2, "video": 0, "audio": 0}) == ["<Picture 0>"]

    def test_frontend_only_nodes_are_not_missing(self):
        """MarkdownNote/PrimitiveNode never appear in /object_info.

        They are canvas-only and are dropped during conversion, so counting
        them as missing would block most existing presets.
        """
        from comfyui.workflow import collect_missing_node_types
        wf = {"nodes": [{"id": 1, "type": "MarkdownNote"},
                        {"id": 2, "type": "PrimitiveNode"},
                        {"id": 3, "type": "Reroute"},
                        {"id": 4, "type": "LoadImage"}]}
        assert collect_missing_node_types(wf, {"LoadImage"}) == []


# ============================================================================
# End-to-end: fan-out through the full modify_workflow pipeline
# ============================================================================

class TestFanoutEndToEnd:
    def test_fanout_survives_modify_workflow(self, tmp_path, monkeypatch):
        """Fan-out, path normalization and file collection must compose.

        Fan-out writes absolute paths on purpose so that
        normalize_file_paths_in_workflow basenames them and collects them for
        staging. If either half regressed, the farm would get paths it cannot
        resolve, or the files would never be copied.
        """
        import comfyui.node_info as ni
        from comfyui.modifier import modify_workflow
        from comfyui.editable import EditableNode, CARDINALITY_MANY

        declared = ([f"media_{i}" for i in range(1, 16)]
                    + [f"media_type_{i}" for i in range(1, 16)])
        monkeypatch.setattr(
            ni, "get_optional_input_names",
            lambda class_type: declared if class_type == "MiniMaxH3Easy" else None)

        refs = []
        for name in ("r1.png", "r2.png", "r3.png"):
            p = tmp_path / name
            p.write_bytes(b"x")
            refs.append(str(p))

        workflow = {
            "41": {"class_type": "LoadImage", "inputs": {"image": "old.png"},
                   "_meta": {"title": "Ref Images_editable*"}},
            "50": {"class_type": "MiniMaxH3Easy",
                   "inputs": {"prompt": "a cat", "media_1": ["41", 0],
                              "media_type_1": "image"},
                   "_meta": {"title": "Video_editable"}},
            "60": {"class_type": "SaveVideo",
                   "inputs": {"filename_prefix": "out", "video": ["50", 0]},
                   "_meta": {"title": "Result_output"}},
        }
        node = EditableNode(node_id="41", node_type="LoadImage",
                            title="Ref Images_editable*", display_name="Ref Images",
                            widget_type="image", widget_name="image",
                            cardinality=CARDINALITY_MANY)

        modified, _found, files_to_copy = modify_workflow(
            workflow, None, None, "job_prefix", seed=1,
            editable_values={"41": [{"node": node, "value": refs}]})

        loaders = [n for n in modified.values() if n["class_type"] == "LoadImage"]
        assert len(loaders) == 3, "one loader node per reference file"

        # Every reference reached the farm as a bare basename...
        assert {n["inputs"]["image"] for n in loaders} == {"r1.png", "r2.png", "r3.png"}
        # ...and every source file was collected for staging.
        assert set(files_to_copy) == set(refs)

        consumer = modified["50"]["inputs"]
        wired = [consumer[f"media_{i}"][0] for i in (1, 2, 3)]
        assert len(set(wired)) == 3, "each slot wired to a distinct loader"
        assert all(consumer[f"media_type_{i}"] == "image" for i in (1, 2, 3))
