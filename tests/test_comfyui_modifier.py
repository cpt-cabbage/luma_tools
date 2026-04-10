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
