"""Tests for the farm path check - both the farm-side script and the submitter."""
import json
import os
import sys

import pytest

from comfyui.path_check import RESULT_SCHEMA, main, run_checks


def _checks_by_id(result):
    """Index a result payload's checks by their id for easy assertions."""
    return {check["id"]: check for check in result["checks"]}


def _make_install(root, nested_main=True):
    """Build a fake ComfyUI tree. nested_main mirrors the embedded/portable
    layout (<root>/ComfyUI/main.py); otherwise the standalone one."""
    if nested_main:
        os.makedirs(os.path.join(root, "ComfyUI"), exist_ok=True)
        open(os.path.join(root, "ComfyUI", "main.py"), "w").close()
    else:
        os.makedirs(root, exist_ok=True)
        open(os.path.join(root, "main.py"), "w").close()
    return root


class TestRunChecks:
    def test_valid_standalone_install_passes_every_check(self, tmp_path):
        # standalone mode lets us point at the real interpreter, so the
        # python_runs probe can actually succeed in a test.
        root = _make_install(str(tmp_path / "comfy"), nested_main=False)

        result = run_checks(root, "standalone", sys.executable, str(tmp_path))

        assert result["ok"] is True, result["checks"]
        assert all(check["ok"] for check in result["checks"])
        assert result["python_version"].startswith("3.")

    def test_missing_directory_fails_the_directory_check(self, tmp_path):
        result = run_checks(str(tmp_path / "does_not_exist"), "embedded", "", str(tmp_path))

        checks = _checks_by_id(result)
        assert result["ok"] is False
        assert checks["comfyui_dir"]["ok"] is False
        assert "not found" in checks["comfyui_dir"]["detail"]

    def test_missing_main_py_is_reported_separately(self, tmp_path):
        root = str(tmp_path / "comfy")
        os.makedirs(root)

        result = run_checks(root, "embedded", "", str(tmp_path))

        checks = _checks_by_id(result)
        assert checks["comfyui_dir"]["ok"] is True
        assert checks["main_py"]["ok"] is False

    def test_missing_python_exe_skips_the_probe(self, tmp_path):
        root = _make_install(str(tmp_path / "comfy"))

        result = run_checks(root, "embedded", "", str(tmp_path))

        checks = _checks_by_id(result)
        assert checks["main_py"]["ok"] is True
        assert checks["python_exe"]["ok"] is False
        assert checks["python_runs"]["ok"] is False
        assert "skipped" in checks["python_runs"]["detail"]

    def test_invalid_mode_reports_the_resolver_error(self, tmp_path):
        root = _make_install(str(tmp_path / "comfy"))

        result = run_checks(root, "bogus_mode", "", str(tmp_path))

        checks = _checks_by_id(result)
        assert checks["python_exe"]["ok"] is False
        assert "Invalid ComfyUI mode" in checks["python_exe"]["detail"]

    def test_payload_shape(self, tmp_path):
        result = run_checks(str(tmp_path), "embedded", "", str(tmp_path))

        for key in ("schema", "ok", "hostname", "os", "timestamp", "checks"):
            assert key in result
        assert result["schema"] == RESULT_SCHEMA
        assert result["ok"] == all(check["ok"] for check in result["checks"])


class TestMain:
    def test_failed_checks_still_exit_zero_and_write_the_file(self, tmp_path):
        # A failed CHECK must not look like a failed JOB - the workstation
        # reads the file, not the exit code.
        result_file = str(tmp_path / "out" / "result.json")

        code = main([
            "--comfyui-path", str(tmp_path / "nope"),
            "--comfyui-mode", "embedded",
            "--result-file", result_file,
        ])

        assert code == 0
        with open(result_file, encoding="utf-8") as handle:
            written = json.load(handle)
        assert written["ok"] is False
        assert written["schema"] == RESULT_SCHEMA

    def test_unwritable_result_file_exits_nonzero(self, tmp_path):
        # A file where a directory should be - the workstation would otherwise
        # wait forever for a result that can never be written.
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")

        code = main([
            "--comfyui-path", str(tmp_path),
            "--result-file", str(blocker / "result.json"),
        ])

        assert code == 1
