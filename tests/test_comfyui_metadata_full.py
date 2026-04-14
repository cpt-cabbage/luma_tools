"""Tests for comfyui.metadata — output file management, gallery metadata."""

import os
import json
import time

import pytest

from comfyui.metadata import (
    get_job_output_files,
    _validate_output_dir,
)


# ============================================================================
# get_job_output_files
# ============================================================================

class TestGetJobOutputFiles:
    def test_empty_dir(self, tmp_path):
        result = get_job_output_files(str(tmp_path))
        assert result == []

    def test_finds_supported_files(self, tmp_path):
        (tmp_path / "output.png").write_text("")
        (tmp_path / "output.jpg").write_text("")
        (tmp_path / "output.txt").write_text("")  # Not supported
        result = get_job_output_files(str(tmp_path))
        assert len(result) == 2

    def test_filter_by_prefix(self, tmp_path):
        (tmp_path / "job1_output.png").write_text("")
        (tmp_path / "job2_output.png").write_text("")
        result = get_job_output_files(str(tmp_path), job_prefix="job1")
        assert len(result) == 1
        assert "job1" in os.path.basename(result[0])

    def test_filter_by_mtime(self, tmp_path):
        old_file = tmp_path / "old.png"
        old_file.write_text("")
        # Set mtime to 1 hour ago
        old_mtime = time.time() - 3600
        os.utime(str(old_file), (old_mtime, old_mtime))

        new_file = tmp_path / "new.png"
        new_file.write_text("")

        result = get_job_output_files(str(tmp_path), min_mtime=time.time() - 60)
        assert len(result) == 1
        assert "new" in os.path.basename(result[0])

    def test_sorted_newest_first(self, tmp_path):
        for i, name in enumerate(["a.png", "b.png", "c.png"]):
            f = tmp_path / name
            f.write_text("")
            # Stagger mtimes
            os.utime(str(f), (time.time() + i, time.time() + i))
        result = get_job_output_files(str(tmp_path))
        assert os.path.basename(result[0]) == "c.png"

    def test_invalid_dir(self):
        assert get_job_output_files("/nonexistent") == []

    def test_empty_string(self):
        assert get_job_output_files("") == []


# ============================================================================
# _validate_output_dir
# ============================================================================

class TestValidateOutputDir:
    def test_valid_string(self):
        assert _validate_output_dir("/some/path") is True

    def test_invalid_type(self):
        assert _validate_output_dir(123) is False
        assert _validate_output_dir(None) is False
