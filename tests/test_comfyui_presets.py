"""Tests for comfyui.presets_manager — workflow directory, path checking, unique filenames."""

import os

import pytest

from comfyui.presets_manager import (
    _is_path_under_directory,
    _generate_unique_filename,
)


# ============================================================================
# _is_path_under_directory
# ============================================================================

class TestIsPathUnderDirectory:
    def test_file_in_dir(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text("{}")
        assert _is_path_under_directory(str(f), str(tmp_path)) is True

    def test_file_in_subdir(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        f = sub / "test.json"
        f.write_text("{}")
        assert _is_path_under_directory(str(f), str(tmp_path)) is True

    def test_file_outside_dir(self, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        f = other / "test.json"
        f.write_text("{}")
        target = tmp_path / "target"
        target.mkdir()
        assert _is_path_under_directory(str(f), str(target)) is False

    def test_dir_equals_itself(self, tmp_path):
        assert _is_path_under_directory(str(tmp_path), str(tmp_path)) is True

    def test_prevents_prefix_matching(self, tmp_path):
        # "dir_extra" should NOT match "dir"
        dir_a = tmp_path / "workflows"
        dir_a.mkdir()
        dir_b = tmp_path / "workflows_backup"
        dir_b.mkdir()
        f = dir_b / "test.json"
        f.write_text("{}")
        assert _is_path_under_directory(str(f), str(dir_a)) is False


# ============================================================================
# _generate_unique_filename
# ============================================================================

class TestGenerateUniqueFilename:
    def test_no_conflict(self, tmp_path):
        result = _generate_unique_filename(str(tmp_path), "workflow.json")
        assert result == "workflow.json"

    def test_with_conflict(self, tmp_path):
        (tmp_path / "workflow.json").write_text("{}")
        result = _generate_unique_filename(str(tmp_path), "workflow.json")
        assert result == "workflow_v001.json"

    def test_multiple_conflicts(self, tmp_path):
        (tmp_path / "workflow.json").write_text("{}")
        (tmp_path / "workflow_v001.json").write_text("{}")
        result = _generate_unique_filename(str(tmp_path), "workflow.json")
        assert result == "workflow_v002.json"

    def test_preserves_extension(self, tmp_path):
        (tmp_path / "my_file.txt").write_text("")
        result = _generate_unique_filename(str(tmp_path), "my_file.txt")
        assert result.endswith(".txt")
