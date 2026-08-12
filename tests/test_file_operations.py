"""Tests for services.file_operations — directory scanning, file discovery, path helpers."""

import os

import pytest

from services.file_operations import (
    fast_scandir,
    find_hip_files,
    find_comp_files,
    get_task_directory,
    get_working_directory,
    get_comp_directory,
)


# ============================================================================
# fast_scandir
# ============================================================================

class TestFastScandir:
    def test_empty_dir(self, tmp_path):
        assert fast_scandir(str(tmp_path)) == []

    def test_finds_subdirs(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        result = fast_scandir(str(tmp_path))
        names = [os.path.basename(d) for d in result]
        assert "a" in names
        assert "b" in names

    def test_recursive(self, tmp_path):
        (tmp_path / "a" / "b").mkdir(parents=True)
        result = fast_scandir(str(tmp_path))
        assert len(result) == 2  # a and a/b

    def test_max_depth(self, tmp_path):
        deep = tmp_path
        for i in range(5):
            deep = deep / f"d{i}"
            deep.mkdir()
        result = fast_scandir(str(tmp_path), max_depth=2)
        # Should stop at depth 2
        assert len(result) < 5

    def test_nonexistent_dir(self):
        result = fast_scandir("/nonexistent/path")
        assert result == []

    def test_ignores_files(self, tmp_path):
        (tmp_path / "file.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()
        result = fast_scandir(str(tmp_path))
        assert len(result) == 1


# ============================================================================
# find_hip_files
# ============================================================================

class TestFindHipFiles:
    def test_finds_by_task(self, tmp_path):
        (tmp_path / "shot_lighting_v01.hip").write_text("")
        (tmp_path / "shot_lookdev_v01.hip").write_text("")
        result = find_hip_files(str(tmp_path), task="lighting")
        assert len(result) == 1
        assert "lighting" in result[0]

    def test_default_task(self, tmp_path):
        # DEFAULT_TASK is "lookdev"
        (tmp_path / "shot_lookdev_v01.hip").write_text("")
        (tmp_path / "shot_lighting_v01.hip").write_text("")
        result = find_hip_files(str(tmp_path))
        assert len(result) == 1
        assert "lookdev" in result[0]

    def test_case_insensitive(self, tmp_path):
        (tmp_path / "shot_Lighting_v01.hip").write_text("")
        result = find_hip_files(str(tmp_path), task="lighting")
        assert len(result) == 1


# ============================================================================
# find_comp_files
# ============================================================================

class TestFindCompFiles:
    def test_finds_compositing(self, tmp_path):
        (tmp_path / "shot_Compositing_v01.nk").write_text("")
        result = find_comp_files(str(tmp_path))
        assert len(result) == 1

    def test_finds_lowercase_compositing(self, tmp_path):
        # Real shots name comps in lowercase (Cha_sh0040_compositing_v023.nk).
        # Only the capitalised form was ever tested, so a case-sensitive match
        # silently returned nothing for every real shot — which left Shot
        # Cleaner with an empty "renders in use" list and every render
        # pre-selected for deletion.
        (tmp_path / "Cha_sh0040_compositing_v023.nk").write_text("")
        result = find_comp_files(str(tmp_path))
        assert result == ["Cha_sh0040_compositing_v023.nk"]

    def test_finds_mixed_case_compositing(self, tmp_path):
        (tmp_path / "shot_COMPOSITING_v02.nk").write_text("")
        assert len(find_comp_files(str(tmp_path))) == 1

    def test_excludes_baking(self, tmp_path):
        (tmp_path / "shot_Compositing_baking.nk").write_text("")
        result = find_comp_files(str(tmp_path))
        assert len(result) == 0

    def test_excludes_baking_lowercase(self, tmp_path):
        (tmp_path / "shot_compositing_Baking_v01.nk").write_text("")
        assert find_comp_files(str(tmp_path)) == []

    def test_excludes_non_comp(self, tmp_path):
        (tmp_path / "shot_v01.nk").write_text("")  # No "Compositing" in name
        result = find_comp_files(str(tmp_path))
        assert len(result) == 0


# ============================================================================
# Path helpers
# ============================================================================

class TestGetTaskDirectory:
    def test_with_task(self):
        result = get_task_directory("W:/Project/shots/sh0010/work/lighting", "lighting")
        assert result.endswith("lighting")
        assert "work" in result

    def test_default_task(self):
        result = get_task_directory("W:/Project/shots/sh0010/work")
        assert result.endswith("lookdev")  # DEFAULT_TASK


class TestGetWorkingDirectory:
    def test_truncates_at_task(self):
        result = get_working_directory(
            "W:/Project/shots/sh0010/work/lighting/img/renders",
            task="lighting"
        )
        assert result.endswith("lighting")
        assert "img" not in result


class TestGetCompDirectory:
    def test_returns_compositing_dir(self):
        result = get_comp_directory("W:/Project/shots/sh0010/work/lighting")
        assert result.endswith("Compositing")
        assert "work" in result
