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
        assert vals == {}

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
        assert node_id == -1

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


# ============================================================================
# Submit-time validation
# ============================================================================

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
