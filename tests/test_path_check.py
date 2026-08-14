"""Tests for the farm path check - both the farm-side script and the submitter."""
import json
import os
import sys
import time

import pytest

from comfyui.path_check import RESULT_SCHEMA, main, run_checks
from deadline.path_check import (
    DEADLINE_PYTHON_PLUGIN_VERSION,
    RESULT_FILENAME,
    build_check_id,
    build_job_info,
    build_plugin_info,
    cleanup_old_path_checks,
    read_path_check_result,
)


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


class TestJobFiles:
    def test_job_info_targets_the_python_plugin_and_comfyui_group(self):
        text = build_job_info("W:/LumaRND/luma_tools/_path_checks/abc", "luma", "temp_compute", 70)

        assert "Plugin=Python\n" in text
        assert "Pool=luma\n" in text
        assert "Group=temp_compute\n" in text
        assert "Priority=70\n" in text
        assert "Frames=0\n" in text
        assert "MachineLimit=1\n" in text
        assert "OnJobComplete=Delete\n" in text

    def test_plugin_info_names_a_configured_interpreter_version(self):
        text = build_plugin_info(
            "W:/checks/abc/comfyui_path_check.py",
            r"D:\apps\ComfyUI_windows_portable",
            "embedded", "", "W:/checks/abc/result.json")

        assert "Version=%s\n" % DEADLINE_PYTHON_PLUGIN_VERSION in text
        assert "ScriptFile=W:/checks/abc/comfyui_path_check.py\n" in text
        assert "SingleFramesOnly=True\n" in text

    def test_plugin_info_uses_forward_slashes_in_arguments(self):
        # Deadline parses backslashes inside quoted Arguments= as escapes.
        text = build_plugin_info(
            r"W:\checks\abc\comfyui_path_check.py",
            "D:\\apps\\ComfyUI_windows_portable\\",
            "standalone", r"C:\Python310\python.exe", r"W:\checks\abc\result.json")

        arguments = [line for line in text.splitlines() if line.startswith("Arguments=")][0]
        assert "\\" not in arguments
        assert '--comfyui-path "D:/apps/ComfyUI_windows_portable"' in arguments
        assert "--comfyui-mode standalone" in arguments
        assert '--comfyui-python "C:/Python310/python.exe"' in arguments
        assert '--result-file "W:/checks/abc/result.json"' in arguments

    def test_check_id_is_unique_per_user_host_and_time(self):
        assert build_check_id("alice", "WS01", "20260813_140000") == "alice_WS01_20260813_140000"


class TestReadResult:
    def test_missing_file_reads_as_none(self, tmp_path):
        assert read_path_check_result(str(tmp_path / RESULT_FILENAME)) is None

    def test_malformed_json_reads_as_none(self, tmp_path):
        path = tmp_path / RESULT_FILENAME
        path.write_text("{not json", encoding="utf-8")

        assert read_path_check_result(str(path)) is None

    def test_wrong_schema_reads_as_none(self, tmp_path):
        path = tmp_path / RESULT_FILENAME
        path.write_text(json.dumps({"schema": 99, "ok": True}), encoding="utf-8")

        assert read_path_check_result(str(path)) is None

    def test_valid_result_is_returned(self, tmp_path):
        payload = {"schema": 1, "ok": True, "hostname": "RENDER07", "checks": []}
        path = tmp_path / RESULT_FILENAME
        path.write_text(json.dumps(payload), encoding="utf-8")

        assert read_path_check_result(str(path)) == payload


class TestCleanup:
    def test_old_directories_are_removed_and_fresh_ones_kept(self, tmp_path):
        old = tmp_path / "alice_WS01_20200101_000000"
        old.mkdir()
        (old / RESULT_FILENAME).write_text("{}", encoding="utf-8")
        fresh = tmp_path / "alice_WS01_20260813_140000"
        fresh.mkdir()

        two_days_ago = time.time() - 2 * 86400
        os.utime(old, (two_days_ago, two_days_ago))

        removed = cleanup_old_path_checks(str(tmp_path), keep_days=1)

        assert removed == 1
        assert not old.exists()
        assert fresh.exists()

    def test_missing_root_is_not_an_error(self, tmp_path):
        assert cleanup_old_path_checks(str(tmp_path / "never_created")) == 0
