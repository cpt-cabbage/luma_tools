# Farm Path Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Settings tab state plainly that the ComfyUI paths live on the farm, and add a **Verify on Farm** button that submits a small Deadline job to check them on a worker and reports the result inline.

**Architecture:** The workstation has no network line to the farm — only Deadline and the shared `network_output_path`. So verification is: submit a `Plugin=Python` Deadline job → the worker runs a stdlib-only check script → the script writes `result.json` onto the shared path → the Settings tab polls for that file off the GUI thread and renders it.

**Tech Stack:** Python 3.10, PySide6, Deadline CommandLine/Python plugins, pytest.

**Spec:** `docs/superpowers/specs/2026-08-13-farm-path-check-design.md`

## Global Constraints

- Repo root: `L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools`. Branch: `ui-overhaul`.
- Tests need `PYTHONPATH`, so they run via a `.ps1` script (below), never a bare `pytest`. `pytest-timeout` is NOT installed — never pass `--timeout`.
- `python/comfyui/path_check.py` runs on farm workers. It must import with **no `comfyui` package on `sys.path`**: stdlib only, plus `comfyui_utils` (the farm-copied name for `comfyui/utils.py`). Enforced by `tests/test_farm_isolation.py`.
- **Never** hand-edit `resources/ui/tabs/_compiled/ui_settings.py`. Edit `settings.ui`, then regenerate with `pyside6-uic`.
- Every module uses `logging` (`logger = logging.getLogger(__name__)`). Never `print()` — except in `path_check.py`'s `main()`, where stdout is the Deadline task log.
- Paths embedded in Deadline `job_info`/`plugin_info` must pass through `normalize_path()` (forward slashes; Deadline treats backslashes in quoted arguments as escapes).
- Deadline Python plugin `Version` must name a row configured under *Configure Plugins → Python → Python Executables*: `3.10`.
- Strings written into `settings.ui` stay ASCII-only (no em dashes, no curly quotes) to match the existing file.
- Do not touch `resources/version.json` or `resources/changelog.md` — the user handles version and changelog.

Test runner script, create once at repo root if absent (`_run_tests.ps1` already exists — reuse it):

```powershell
Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe -m pytest tests\ -v
```

To run one file, write a throwaway `_run_one.ps1` with the last line changed, e.g.:

```powershell
python\venv\Scripts\python.exe -m pytest tests\test_path_check.py -v
```

Invoke with: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`

## File Structure

| File | Responsibility |
|---|---|
| `python/comfyui/path_check.py` | **New.** Farm-side checks. Pure logic + a `main()` entry point Deadline executes. Stdlib + `comfyui_utils` only. |
| `python/deadline/path_check.py` | **New.** Builds and submits the Deadline job, reads the result file back, sweeps old check dirs. Workstation-side only. |
| `python/ui/tabs/settings_tab.py` | **Modify.** Button handler, off-thread polling, result rendering. |
| `resources/ui/tabs/settings.ui` | **Modify.** Farm wording, new button + status label. |
| `resources/ui/tabs/_compiled/ui_settings.py` | **Regenerate** via `pyside6-uic`. |
| `tests/test_path_check.py` | **New.** Covers both new modules. |
| `tests/test_farm_isolation.py` | **Modify.** Register `path_check.py` as a farm-copied script. |

The two `path_check.py` modules are deliberately separate: one runs on the farm under a foreign interpreter with no project packages available, the other runs on the workstation and imports freely from `core.*`. Merging them would drag `core.config` onto the farm.

---

### Task 1: Farm-side check script

**Files:**
- Create: `python/comfyui/path_check.py`
- Create: `tests/test_path_check.py`
- Modify: `tests/test_farm_isolation.py:31-38` (FARM_COPIES) and add two tests

**Interfaces:**
- Consumes: `resolve_comfyui_paths(comfyui_path, mode="embedded", python_path=None) -> (python_exe, main_py)` from `comfyui/utils.py:55`. Raises `ValueError` on an invalid mode or a standalone mode with no `python_path`.
- Produces:
  - `RESULT_SCHEMA: int = 1`
  - `run_checks(comfyui_path: str, comfyui_mode: str = "embedded", comfyui_python: str = "", network_path: str = "") -> dict` — the result payload
  - `main(argv: list[str] | None = None) -> int` — CLI entry, returns the process exit code

- [ ] **Step 1: Write the failing tests**

Create `tests/test_path_check.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: collection error — `ModuleNotFoundError: No module named 'comfyui.path_check'`

- [ ] **Step 3: Write the farm-side script**

Create `python/comfyui/path_check.py`:

```python
"""Verify a ComfyUI installation from a Deadline farm worker.

This runs ON THE FARM, not on the workstation (see CLAUDE.md, ComfyUI Farm
Architecture). The workstation cannot reach the worker, so the answer is
written as JSON onto the shared network path and read back from there.

Farm isolation: stdlib only, plus comfyui_utils - the flat name utils.py is
copied under. See tests/test_farm_isolation.py.
"""
import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time

try:
    from comfyui_utils import resolve_comfyui_paths
except ImportError:  # workstation / test import, where the package exists
    from comfyui.utils import resolve_comfyui_paths

RESULT_SCHEMA = 1

# The resolved interpreter lives on a worker that may be paging in a model.
# Sixty seconds is generous for `python -c print(version)` without letting a
# wedged process hold the whole check open.
_PROBE_TIMEOUT_S = 60


def _check(check_id, label, ok, detail):
    """One line of the report."""
    return {"id": check_id, "label": label, "ok": bool(ok), "detail": detail}


def _probe_python(python_exe):
    """Launch the resolved interpreter and read its version back.

    Existing on disk is not the same as being runnable - a truncated copy or a
    missing python3xx.dll only shows up when you start it.

    Returns (version_or_None, detail_string).
    """
    try:
        proc = subprocess.run(
            [python_exe, "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "could not launch: %s" % exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:200]
        return None, "exit code %s: %s" % (proc.returncode, stderr)

    version = proc.stdout.strip()
    return version, "Python %s" % version


def run_checks(comfyui_path, comfyui_mode="embedded", comfyui_python="", network_path=""):
    """Run every farm-side check and return the result payload."""
    checks = []

    dir_ok = os.path.isdir(comfyui_path)
    checks.append(_check(
        "comfyui_dir", "ComfyUI path", dir_ok,
        comfyui_path if dir_ok else "not found: %s" % comfyui_path))

    # embedded/portable put main.py under <path>/ComfyUI/; standalone puts it
    # at the root. Probe both rather than trusting the configured mode.
    nested = os.path.join(comfyui_path, "ComfyUI", "main.py")
    flat = os.path.join(comfyui_path, "main.py")
    main_py = nested if os.path.isfile(nested) else (flat if os.path.isfile(flat) else None)
    checks.append(_check(
        "main_py", "ComfyUI main.py", main_py is not None,
        main_py if main_py else "not found at %s or %s" % (nested, flat)))

    python_exe = None
    resolve_error = None
    try:
        python_exe, _ = resolve_comfyui_paths(comfyui_path, comfyui_mode, comfyui_python or None)
    except ValueError as exc:
        resolve_error = str(exc)

    exe_ok = bool(python_exe) and os.path.isfile(python_exe)
    checks.append(_check(
        "python_exe", "Python executable", exe_ok,
        python_exe if exe_ok else (resolve_error or "not found: %s" % python_exe)))

    if exe_ok:
        version, probe_detail = _probe_python(python_exe)
    else:
        version, probe_detail = None, "skipped - no executable to run"
    checks.append(_check("python_runs", "Python runs", version is not None, probe_detail))

    checks.append(_check(
        "network_path", "Network share", bool(network_path),
        network_path or "no network path given"))

    return {
        "schema": RESULT_SCHEMA,
        "ok": all(check["ok"] for check in checks),
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "comfyui_mode": comfyui_mode,
        "python_version": version,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": checks,
    }


def main(argv=None):
    """Deadline entry point. Writes the result file, prints it to the task log."""
    parser = argparse.ArgumentParser(
        description="Verify the ComfyUI installation on this farm worker")
    parser.add_argument("--comfyui-path", required=True)
    parser.add_argument("--comfyui-mode", default="embedded")
    parser.add_argument("--comfyui-python", default="")
    parser.add_argument("--result-file", required=True)
    args = parser.parse_args(argv)

    result = run_checks(
        args.comfyui_path,
        args.comfyui_mode,
        args.comfyui_python,
        network_path=os.path.dirname(args.result_file),
    )

    # Failed CHECKS exit 0 - the file is the answer, and a red Deadline job
    # would hide the detail. Only an unwritable file is a job failure, because
    # then the workstation would wait for something that can never arrive.
    try:
        directory = os.path.dirname(args.result_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(args.result_file, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
    except OSError as exc:
        sys.stderr.write("Could not write result file %s: %s\n" % (args.result_file, exc))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: 8 passed

- [ ] **Step 5: Register the script with the farm isolation test**

In `tests/test_farm_isolation.py`, add one entry to `FARM_COPIES` (line 31-38) and widen its comment, which currently claims submitter.py is the only copier:

```python
# Files copied to the farm, mapping (source dir, source basename) -> farm basename
# Must stay in sync with deadline/submitter.py and deadline/path_check.py
FARM_COPIES = {
    (_COMFYUI_PKG, "runner.py"): "comfyui_runner.py",
    (_COMFYUI_PKG, "utils.py"): "comfyui_utils.py",
    (_COMFYUI_PKG, "analytics.py"): "comfyui_analytics.py",
    (_COMFYUI_PKG, "node_configs.py"): "comfyui_node_configs.py",
    (_COMFYUI_PKG, "metadata.py"): "comfyui_metadata.py",
    (_COMFYUI_PKG, "path_check.py"): "comfyui_path_check.py",
    (_CORE_PKG, "metadata_file.py"): "comfyui_metadata_file.py",
}
```

Then append this class at the end of the file:

```python
class TestFarmPathCheckWorks:
    """path_check.py is executed by Deadline's Python plugin on the worker.

    Importing is not enough: it reaches resolve_comfyui_paths through
    comfyui_utils, and that indirection is exactly what breaks in isolation.
    """

    def test_path_check_imports(self, farm_env):
        mod = importlib.import_module("comfyui_path_check")
        assert hasattr(mod, "run_checks")
        assert hasattr(mod, "main")

    def test_run_checks_works_in_farm_env(self, farm_env, tmp_path):
        mod = importlib.import_module("comfyui_path_check")

        result = mod.run_checks(str(tmp_path / "nope"), "embedded", "", str(tmp_path))

        assert result["ok"] is False
        assert any(c["id"] == "comfyui_dir" and not c["ok"] for c in result["checks"])
        # Proves resolve_comfyui_paths resolved via comfyui_utils, not the package
        assert any(c["id"] == "python_exe" for c in result["checks"])
```

- [ ] **Step 6: Run the farm isolation suite**

Change the last line of `_run_one.ps1` to target `tests\test_farm_isolation.py`, then run:
`powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: all pass, including `test_path_check_imports`, `test_run_checks_works_in_farm_env`, and the existing `test_all_fallback_imports_have_source_copy` (which now sees `from comfyui_utils import ...` inside `path_check.py` and confirms `comfyui_utils` is in the copy list).

- [ ] **Step 7: Commit**

```bash
git add python/comfyui/path_check.py tests/test_path_check.py tests/test_farm_isolation.py
git commit -m "Add farm-side ComfyUI path check script"
```

---

### Task 2: Deadline submission module

**Files:**
- Create: `python/deadline/path_check.py`
- Modify: `tests/test_path_check.py` (append two classes)

**Interfaces:**
- Consumes: `DEADLINE_PATH`, `DEADLINE_POOL`, `DEADLINE_GROUP_COMFYUI` (`"temp_compute"`), `DEADLINE_PRIORITY_COMFYUI` (`50`), `DEADLINE_DEPARTMENT`, `DEADLINE_JOB_NAME_PREFIX` from `core.config`; `ensure_directory`, `load_json`, `normalize_path` from `core.utils`; `submit_deadline_job(deadline_command: list[str], log_prefix: str = "") -> str | None` from `deadline.utils`.
- Produces:
  - `submit_path_check(comfyui_path: str, comfyui_mode: str = "embedded", comfyui_python: str = "", network_output_path: str = "", pool=None, group=None, priority=None) -> tuple[str | None, str]` — returns `(job_id, result_path)`; raises `ValueError` / `RuntimeError` on bad preconditions
  - `read_path_check_result(result_path: str) -> dict | None`
  - `cleanup_old_path_checks(root: str, keep_days: int = 1) -> int`
  - `build_job_info(job_dir, pool, group, priority) -> str`, `build_plugin_info(script_path, comfyui_path, comfyui_mode, comfyui_python, result_path) -> str`, `build_check_id(user=None, host=None, timestamp=None) -> str`
  - `PATH_CHECK_DIRNAME = "_path_checks"`, `RESULT_FILENAME = "result.json"`, `RESULT_SCHEMA = 1`, `DEADLINE_PYTHON_PLUGIN_VERSION = "3.10"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_path_check.py`:

```python
from deadline.path_check import (
    DEADLINE_PYTHON_PLUGIN_VERSION,
    RESULT_FILENAME,
    build_check_id,
    build_job_info,
    build_plugin_info,
    cleanup_old_path_checks,
    read_path_check_result,
)


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
            r"D:\apps\ComfyUI_windows_portable\\",
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
```

Add `import time` to the imports at the top of `tests/test_path_check.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Point `_run_one.ps1` back at `tests\test_path_check.py` and run it.
Expected: collection error — `ModuleNotFoundError: No module named 'deadline.path_check'`

- [ ] **Step 3: Write the submission module**

Create `python/deadline/path_check.py`:

```python
"""Deadline job that verifies the ComfyUI installation on a farm worker.

The workstation has no direct line to the farm (see CLAUDE.md, ComfyUI Farm
Architecture), so checking whether comfyui_path exists means submitting a tiny
job and reading its answer back off the shared network path.

Plugin=Python is used rather than CommandLine so the check runs under an
interpreter configured centrally in the Deadline repository - independent of
the ComfyUI install being tested. A broken comfyui_python_path then reports as
a specific failed check instead of an opaque job error.
"""
import getpass
import logging
import os
import shutil
import socket
import time
from typing import Any, Dict, Optional, Tuple

from core.config import (
    DEADLINE_PATH,
    DEADLINE_POOL,
    DEADLINE_GROUP_COMFYUI,
    DEADLINE_PRIORITY_COMFYUI,
    DEADLINE_DEPARTMENT,
    DEADLINE_JOB_NAME_PREFIX,
)
from core.utils import ensure_directory, load_json, normalize_path

logger = logging.getLogger(__name__)

# Must name a row configured under Configure Plugins -> Python -> Python
# Executables in the Deadline repository (3.9 / 3.10 / 3.11 are configured in
# this studio). The check script is stdlib-only, so any configured 3.x works.
DEADLINE_PYTHON_PLUGIN_VERSION = "3.10"

PATH_CHECK_DIRNAME = "_path_checks"
RESULT_FILENAME = "result.json"
RESULT_SCHEMA = 1

# (source basename in python/comfyui/, farm basename)
FARM_SCRIPTS = (
    ("path_check.py", "comfyui_path_check.py"),
    ("utils.py", "comfyui_utils.py"),
)


def _check_priority() -> int:
    """A five-second diagnostic should not queue behind a render."""
    return min(99, DEADLINE_PRIORITY_COMFYUI + 20)


def build_check_id(user: Optional[str] = None, host: Optional[str] = None,
                   timestamp: Optional[str] = None) -> str:
    """Directory name for one check: who asked, from where, when."""
    user = user or getpass.getuser()
    host = host or socket.gethostname()
    timestamp = timestamp or time.strftime("%Y%m%d_%H%M%S")
    return f"{user}_{host}_{timestamp}"


def build_job_info(job_dir: str, pool: str, group: str, priority: int) -> str:
    """Deadline job_info for a single-task check job."""
    return (
        "Plugin=Python\n"
        f"Name={DEADLINE_JOB_NAME_PREFIX}ComfyUI Path Check\n"
        f"Department={DEADLINE_DEPARTMENT}\n"
        f"Pool={pool}\n"
        f"Group={group}\n"
        f"Priority={priority}\n"
        "Frames=0\n"
        "ChunkSize=1\n"
        "MachineLimit=1\n"
        f"OutputDirectory0={normalize_path(job_dir)}\n"
        "OnJobComplete=Delete\n"
    )


def build_plugin_info(script_path: str, comfyui_path: str, comfyui_mode: str,
                      comfyui_python: str, result_path: str) -> str:
    """Deadline plugin_info for the Python plugin."""
    clean_path = normalize_path(comfyui_path.rstrip("/\\"))
    clean_python = normalize_path(comfyui_python) if comfyui_python else ""
    arguments = (
        f'--comfyui-path "{clean_path}" '
        f'--comfyui-mode {comfyui_mode} '
        f'--comfyui-python "{clean_python}" '
        f'--result-file "{normalize_path(result_path)}"'
    )
    return (
        f"Version={DEADLINE_PYTHON_PLUGIN_VERSION}\n"
        f"ScriptFile={normalize_path(script_path)}\n"
        f"Arguments={arguments}\n"
        "SingleFramesOnly=True\n"
    )


def cleanup_old_path_checks(root: str, keep_days: int = 1) -> int:
    """Delete check directories older than keep_days. Returns how many went."""
    if not os.path.isdir(root):
        return 0

    cutoff = time.time() - keep_days * 86400
    removed = 0
    for name in os.listdir(root):
        entry = os.path.join(root, name)
        try:
            if os.path.isdir(entry) and os.path.getmtime(entry) < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        except OSError as exc:
            logger.debug(f"Could not clean up {entry}: {exc}")
    return removed


def read_path_check_result(result_path: str) -> Optional[Dict[str, Any]]:
    """Read the worker's answer. None until the farm has written a valid one."""
    if not os.path.isfile(result_path):
        return None

    data = load_json(result_path, default=None)
    if not isinstance(data, dict) or data.get("schema") != RESULT_SCHEMA:
        logger.warning(f"Ignoring malformed path check result at {result_path}")
        return None
    return data


def submit_path_check(comfyui_path: str, comfyui_mode: str = "embedded",
                      comfyui_python: str = "", network_output_path: str = "",
                      pool: Optional[str] = None, group: Optional[str] = None,
                      priority: Optional[int] = None) -> Tuple[Optional[str], str]:
    """Submit the check job. Returns (job_id, result_path).

    Runs in a worker thread - it shells out to deadlinecommand.
    """
    if not comfyui_path.strip():
        raise ValueError("ComfyUI path is empty")
    if not DEADLINE_PATH:
        raise RuntimeError("Deadline is not available on this machine")
    if not network_output_path.strip():
        raise RuntimeError(
            "No network output path is configured - the farm has nowhere to write the result")

    root = os.path.join(network_output_path, PATH_CHECK_DIRNAME)
    cleanup_old_path_checks(root)

    job_dir = os.path.join(root, build_check_id())
    ensure_directory(job_dir)

    # Copy the farm scripts next to the job files, flattened with the
    # comfyui_ prefix the farm imports them under.
    comfyui_pkg = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "comfyui")
    for src_name, dst_name in FARM_SCRIPTS:
        shutil.copy2(os.path.join(comfyui_pkg, src_name), os.path.join(job_dir, dst_name))

    script_path = os.path.join(job_dir, "comfyui_path_check.py")
    result_path = os.path.join(job_dir, RESULT_FILENAME)

    job_info_path = os.path.join(job_dir, "path_check_job_info.txt")
    plugin_info_path = os.path.join(job_dir, "path_check_plugin_info.txt")
    with open(job_info_path, "w", encoding="utf-8") as handle:
        handle.write(build_job_info(
            job_dir,
            pool or DEADLINE_POOL,
            group or DEADLINE_GROUP_COMFYUI,
            _check_priority() if priority is None else priority,
        ))
    with open(plugin_info_path, "w", encoding="utf-8") as handle:
        handle.write(build_plugin_info(
            script_path, comfyui_path, comfyui_mode, comfyui_python, result_path))

    from deadline.utils import submit_deadline_job

    job_id = submit_deadline_job(
        [DEADLINE_PATH, job_info_path, plugin_info_path], log_prefix="[PathCheck]")
    logger.info(f"Path check job {job_id} submitted; result expected at {result_path}")
    return job_id, result_path
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: 18 passed (8 from Task 1, 10 new)

- [ ] **Step 5: Commit**

```bash
git add python/deadline/path_check.py tests/test_path_check.py
git commit -m "Add Deadline submission for the ComfyUI farm path check"
```

---

### Task 3: Settings UI wording and verify widgets

**Files:**
- Modify: `resources/ui/tabs/settings.ui` (inside `globalSettingsGroupBox`, lines ~691-801)
- Regenerate: `resources/ui/tabs/_compiled/ui_settings.py`

**Interfaces:**
- Produces (widget object names Task 4 depends on): `comfyuiFarmNoteLabel`, `VerifyComfyUIPathButton`, `comfyuiVerifyStatus`.

- [ ] **Step 1: Add the farm explanation label**

In `resources/ui/tabs/settings.ui`, insert this `<item>` immediately **before** the `<item>` that contains `<layout class="QHBoxLayout" name="comfyuiModeLayout">` (currently line 691):

```xml
          <item>
           <widget class="QLabel" name="comfyuiFarmNoteLabel">
            <property name="textRole" stdset="0">
             <string>help</string>
            </property>
            <property name="text">
             <string>ComfyUI runs on Deadline farm workers, not on your machine. The paths below are resolved on the worker that picks up the job - they do not need to exist on this computer.</string>
            </property>
            <property name="wordWrap">
             <bool>true</bool>
            </property>
           </widget>
          </item>
```

- [ ] **Step 2: Retitle the path labels and rewrite the tooltips**

Make these six string replacements in the same file:

| Widget | Property | New value |
|---|---|---|
| `comfyuiPathLabel` | `text` | `ComfyUI Path (farm):` |
| `ComfyUIPathEdit` | `placeholderText` | `Path to the ComfyUI installation on the farm worker...` |
| `ComfyUIPathEdit` | `toolTip` | `ComfyUI installation directory as seen by the Deadline worker. Resolved on the farm, not on this machine.` |
| `comfyuiPythonLabel` | `text` | `Python Path (farm):` |
| `ComfyUIPythonEdit` | `toolTip` | `Python executable for standalone mode, as seen by the Deadline worker.` |
| `ComfyUIModeButton` | `toolTip` | `Installation type of ComfyUI on the farm worker` |

And three more that reframe the pickers and the share:

| Widget | Property | New value |
|---|---|---|
| `BrowseComfyUIPath` | `toolTip` | `Browse for the directory. Convenience only - the path must be valid on the farm worker, not here.` |
| `BrowseComfyUIPython` | `toolTip` | `Browse for the executable. Convenience only - the path must be valid on the farm worker, not here.` |
| `NetworkOutputEdit` | `toolTip` | `Shared network path for outputs - the only filesystem both your workstation and the farm can see.` |

- [ ] **Step 3: Add the verify button and status label**

Insert these two `<item>` blocks immediately **after** the `<item>` containing `<widget class="QLabel" name="comfyuiCurrentPath">` (currently ends line 801) and **before** the `<item>` containing `networkOutputLayout`:

```xml
          <item>
           <layout class="QHBoxLayout" name="comfyuiVerifyLayout">
            <item>
             <widget class="QPushButton" name="VerifyComfyUIPathButton">
              <property name="density" stdset="0">
               <string>sm</string>
              </property>
              <property name="role" stdset="0">
               <string>secondary</string>
              </property>
              <property name="text">
               <string>Verify on Farm</string>
              </property>
              <property name="toolTip">
               <string>Send a quick Deadline job that checks these paths on a farm worker and reports back</string>
              </property>
             </widget>
            </item>
            <item>
             <spacer name="comfyuiVerifySpacer">
              <property name="orientation">
               <enum>Qt::Horizontal</enum>
              </property>
             </spacer>
            </item>
           </layout>
          </item>
          <item>
           <widget class="QLabel" name="comfyuiVerifyStatus">
            <property name="textRole" stdset="0">
             <string>help</string>
            </property>
            <property name="text">
             <string/>
            </property>
            <property name="wordWrap">
             <bool>true</bool>
            </property>
            <property name="textInteractionFlags">
             <set>Qt::TextSelectableByMouse</set>
            </property>
           </widget>
          </item>
```

- [ ] **Step 4: Recompile the UI**

```bash
python/venv/Scripts/pyside6-uic.exe resources/ui/tabs/settings.ui -o resources/ui/tabs/_compiled/ui_settings.py -g python
```

- [ ] **Step 5: Verify the widgets landed in the compiled output**

```bash
grep -n "VerifyComfyUIPathButton\|comfyuiVerifyStatus\|comfyuiFarmNoteLabel" resources/ui/tabs/_compiled/ui_settings.py
```

Expected: each name appears (setObjectName plus the retranslate calls). If nothing matches, the `.ui` edit landed outside `globalSettingsGroupBox` — re-check the insertion anchors.

- [ ] **Step 6: Launch the app to confirm the UI still loads**

Write `_run_test.ps1`:

```powershell
Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe python\core\luma_tools.py --tab settings --auto-close 20
```

Run: `powershell -ExecutionPolicy Bypass -File _run_test.ps1`
Then read the log:

```bash
powershell -Command "Get-Content (Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 60"
```

Expected: app starts and closes with no `Traceback` and no `Settings: no main layout` warning. The button is inert at this point — Task 4 wires it.

- [ ] **Step 7: Commit**

```bash
git add resources/ui/tabs/settings.ui resources/ui/tabs/_compiled/ui_settings.py
git commit -m "Settings: state that the ComfyUI paths live on the farm, add verify button"
```

---

### Task 4: Wire the verify button in the Settings tab

**Files:**
- Modify: `python/ui/tabs/settings_tab.py` — imports (line 7-19), `connect_signals` (~line 127), `initialize` (~line 166), plus a new section appended after `_update_comfyui_python_visibility` (ends line 985)

**Interfaces:**
- Consumes: `submit_path_check`, `read_path_check_result` from `deadline.path_check` (Task 2); `poll_deadline_job_status(job_id) -> dict` from `deadline.poller` (returns `{"status", "progress", "error_message", ...}`); widget names from Task 3; `self._comfyui_mode` property (`settings_tab.py:945`); `self.start_worker(func, *args, on_result=…, on_error=…, worker_kwargs=…)` — `on_error` receives `(error_msg, traceback_str)`.
- Produces: no public API; the button is the entry point.

- [ ] **Step 1: Add the module-level poll worker**

`settings_tab.py` already defines `_clear_thumbnail_caches` as a module-level worker function (line 22). Add `import html` next to `import os` at the top of the file, then add this function directly after `_clear_thumbnail_caches`:

```python
def _poll_path_check_once(result_path: str, job_id: str, want_status: bool) -> dict:
    """Worker function - one poll of the farm path check (no Qt access).

    Both halves are network calls: the result file lives on the share, and
    `deadlinecommand GetJob` regularly takes a second or more. Neither may run
    on the GUI thread.
    """
    from deadline.path_check import read_path_check_result

    result = read_path_check_result(result_path)
    if result is not None:
        return {"result": result, "status": None}

    status = None
    if want_status:
        from deadline.poller import poll_deadline_job_status
        status = poll_deadline_job_status(job_id)
    return {"result": None, "status": status}
```

- [ ] **Step 2: Connect the button and initialize its state**

In `connect_signals()`, after the two `textChanged` connections (line 126-127), add:

```python
        if hasattr(self.ui, 'VerifyComfyUIPathButton'):
            self.ui.VerifyComfyUIPathButton.clicked.connect(self._on_verify_comfyui_path)
```

In `initialize()`, next to the other state initialisation (after `self._prompting_unsaved = False`, line 166), add:

```python
        # Farm path check state. Initialized here because initialize() is the
        # setup method for this tab - an uninitialized attribute is the usual
        # source of AttributeError in signal handlers.
        self._path_check = None
        self._path_check_timer = None
```

- [ ] **Step 3: Add the path check section**

Append after `_update_comfyui_python_visibility` (which ends at line 985):

```python
    # =========================================================================
    # Farm path check
    # =========================================================================
    # comfyui_path is resolved on a Deadline worker, never here, so the only
    # honest way to check it is to ask the farm: submit a tiny job, let the
    # worker write its answer to the shared path, and poll for that file.

    _PATH_CHECK_POLL_MS = 2000
    _PATH_CHECK_TIMEOUT_S = 180
    # The Deadline query is far more expensive than an isfile() on the share
    # and only drives the wording, so ask for it every Nth tick.
    _PATH_CHECK_STATUS_EVERY = 3

    def _on_verify_comfyui_path(self):
        """Submit a Deadline job that checks the ComfyUI paths on a worker."""
        from core.config import DEADLINE_PATH
        from core.settings_manager import safe_get_setting
        from deadline.path_check import submit_path_check

        if self._path_check is not None:
            return  # a check is already in flight

        comfyui_path = self.ui.ComfyUIPathEdit.text().strip()
        if not comfyui_path:
            self._set_verify_status("Enter a ComfyUI path first.", "warning")
            return
        if not DEADLINE_PATH:
            self._set_verify_status("Deadline is not available on this machine.", "error")
            return

        network_path = (self.ui.NetworkOutputEdit.text().strip()
                        or safe_get_setting("network_output_path", ""))
        if not network_path:
            self._set_verify_status(
                "No network output path is set - the farm has nowhere to write the result.",
                "error")
            return

        self.ui.VerifyComfyUIPathButton.setEnabled(False)
        self._set_verify_status(
            "Submitting a check job for the values currently in these fields "
            "(not the saved settings)...", "info")

        self.start_worker(
            submit_path_check,
            worker_kwargs={
                "comfyui_path": comfyui_path,
                "comfyui_mode": self._comfyui_mode,
                "comfyui_python": self.ui.ComfyUIPythonEdit.text().strip(),
                "network_output_path": network_path,
            },
            on_result=self._on_path_check_submitted,
            on_error=self._on_path_check_submit_error,
        )

    def _on_path_check_submitted(self, submit_result):
        """Start polling for the worker's answer (GUI thread)."""
        from PySide6.QtCore import QTimer

        job_id, result_path = submit_result
        if not job_id:
            self._finish_path_check(
                "Deadline did not return a job id - the submission failed.", "error")
            return

        self._path_check = {
            "job_id": job_id,
            "result_path": result_path,
            "ticks": 0,
            "in_flight": False,
            "saw_running": False,
        }
        self._set_verify_status(f"Queued on the farm (job {job_id})...", "info")

        self._path_check_timer = QTimer(self.main_window)
        self._path_check_timer.timeout.connect(self._poll_path_check)
        self._path_check_timer.start(self._PATH_CHECK_POLL_MS)
        logger.info(f"Path check job {job_id} submitted; polling {result_path}")

    def _on_path_check_submit_error(self, error_msg, traceback_str=""):
        """The submission itself raised in the worker thread."""
        logger.error(f"Path check submission failed: {error_msg}")
        self._finish_path_check(f"Could not submit the check job: {error_msg}", "error")

    def _poll_path_check(self):
        """Timer tick - hand the actual network work to a worker."""
        check = self._path_check
        if not check or check["in_flight"]:
            return

        check["ticks"] += 1
        elapsed = check["ticks"] * self._PATH_CHECK_POLL_MS / 1000.0
        if elapsed > self._PATH_CHECK_TIMEOUT_S:
            self._finish_path_check(
                "No answer from the farm after 3 minutes - the check job may still be queued.",
                "warning")
            return

        check["in_flight"] = True
        self.start_worker(
            _poll_path_check_once,
            check["result_path"],
            check["job_id"],
            check["ticks"] % self._PATH_CHECK_STATUS_EVERY == 0,
            on_result=self._on_path_check_polled,
            on_error=self._on_path_check_poll_error,
        )

    def _on_path_check_polled(self, payload):
        """A poll came back: either the answer, or a job status for the wording."""
        check = self._path_check
        if not check:
            return  # finished or cancelled while the poll was in flight
        check["in_flight"] = False

        result = payload.get("result")
        if result is not None:
            self._render_path_check_result(result)
            return

        status_info = payload.get("status")
        if not status_info:
            return

        status = status_info.get("status", "Unknown")
        if status == "Failed":
            message = status_info.get("error_message") or "the job errored on the farm"
            self._finish_path_check(f"The check job failed: {message}", "error")
        elif status in ("Rendering", "Active"):
            check["saw_running"] = True
            self._set_verify_status("Running on a farm worker...", "info")
        elif not check["saw_running"]:
            self._set_verify_status(f"Queued on the farm (job {check['job_id']})...", "info")

    def _on_path_check_poll_error(self, error_msg, traceback_str=""):
        """A poll failed. Keep waiting - the share or Deadline may just be busy."""
        logger.debug(f"Path check poll failed (will retry): {error_msg}")
        if self._path_check:
            self._path_check["in_flight"] = False

    def _render_path_check_result(self, result):
        """Show one line per check, plus which worker answered."""
        from core.config import UIColors

        lines = []
        for check in result.get("checks", []):
            ok = bool(check.get("ok"))
            colour = UIColors.SUCCESS if ok else UIColors.ERROR
            mark = "\u2713" if ok else "\u2717"
            label = html.escape(str(check.get("label", check.get("id", "check"))))
            detail = html.escape(str(check.get("detail", "")))
            lines.append(f'<span style="color:{colour};">{mark}</span> {label}: {detail}')

        footer = f"Answered by {html.escape(str(result.get('hostname', 'an unknown worker')))}"
        version = result.get("python_version")
        if version:
            footer += f" - Python {html.escape(str(version))}"
        lines.append(footer)

        ok = bool(result.get("ok"))
        headline_colour = UIColors.SUCCESS if ok else UIColors.ERROR
        headline = ("ComfyUI is reachable from the farm" if ok
                    else "Problems found on the farm worker")
        self.ui.comfyuiVerifyStatus.setText(
            f'<b style="color:{headline_colour};">{headline}</b><br>' + "<br>".join(lines))

        logger.info(
            f"Path check result from {result.get('hostname')}: ok={ok}")
        self._end_path_check()

    def _set_verify_status(self, message, level="info"):
        """Set the one-line status under the ComfyUI path fields."""
        from core.config import UIColors

        colours = {
            "info": UIColors.TEXT_MUTED,
            "success": UIColors.SUCCESS,
            "warning": UIColors.WARNING,
            "error": UIColors.ERROR,
        }
        colour = colours.get(level, UIColors.TEXT_MUTED)
        self.ui.comfyuiVerifyStatus.setText(
            f'<span style="color:{colour};">{html.escape(message)}</span>')

    def _finish_path_check(self, message, level):
        """Stop polling and leave a final message on the status line."""
        self._end_path_check()
        self._set_verify_status(message, level)

    def _end_path_check(self):
        """Tear down the timer and state, and re-enable the button."""
        timer = self._path_check_timer
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        self._path_check_timer = None
        self._path_check = None
        if hasattr(self.ui, 'VerifyComfyUIPathButton'):
            self.ui.VerifyComfyUIPathButton.setEnabled(True)
```

- [ ] **Step 4: Check the guard paths without a farm round-trip**

Launch with `_run_test.ps1` (from Task 3, Step 6), and while it is open click **Verify on Farm** with the ComfyUI path field cleared. Expected: the status line reads "Enter a ComfyUI path first." and the button stays enabled. No submission happens.

Then read the log for exceptions:

```bash
powershell -Command "Get-Content (Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 80"
```

Expected: no `AttributeError`, no `Traceback`.

- [ ] **Step 5: Run a real check against the farm**

Relaunch, restore the real ComfyUI path, and click **Verify on Farm**. Expected sequence on the status line: submitting → `Queued on the farm (job …)` → optionally `Running on a farm worker...` → a per-check report ending with the worker hostname and Python version. The GUI must stay responsive throughout (drag the window while it polls).

Confirm the artifacts on the share:

```bash
powershell -Command "Get-ChildItem 'W:\LumaRND\luma_tools\_path_checks\' -Recurse | Select-Object FullName, LastWriteTime"
```

Expected: one check directory containing `comfyui_path_check.py`, `comfyui_utils.py`, both `.txt` job files, and `result.json`.

If the job errors with an unknown Python version, the Deadline repository does not have `3.10` configured — change `DEADLINE_PYTHON_PLUGIN_VERSION` in `python/deadline/path_check.py` to a version that is listed under *Configure Plugins → Python → Python Executables*.

- [ ] **Step 6: Commit**

```bash
git add python/ui/tabs/settings_tab.py
git commit -m "Settings: verify the ComfyUI farm paths via a Deadline check job"
```

---

### Task 5: Full-suite verification

**Files:** none modified unless a regression turns up.

- [ ] **Step 1: Run the whole test suite**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: no new failures against the pre-change baseline. If a test fails, first check whether the failing path was touched by this work (`git diff --stat main...HEAD`); pre-existing failures should be reported to the user, not fixed here.

- [ ] **Step 2: Stability check**

Run: `powershell -ExecutionPolicy Bypass -File _check_logs.ps1`
Expected: 10 launches complete with no tracebacks. (This script launches the app repeatedly with `--auto-close`; the name is misleading — it generates logs rather than reading them.)

- [ ] **Step 3: Remove the throwaway runner**

```bash
rm -f _run_one.ps1 _run_test.ps1
```

- [ ] **Step 4: Report to the user**

State plainly: which tests pass, what the real farm check returned (hostname and per-check results), and any pre-existing failures found but not fixed.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 Wording | Task 3, Steps 1-2 |
| §2 Farm-side script (5 checks, JSON payload, exit codes) | Task 1, Step 3 |
| §3 Submission module (job/plugin info, cleanup, read) | Task 2, Step 3 |
| §4 Settings tab wiring (unsaved values, guards, polling, timeout, rendering) | Task 4, Steps 2-3 |
| §5 Error handling table | Task 4, Step 3 (`_on_path_check_submit_error`, `_on_path_check_poll_error`, `Failed` branch, timeout branch); Task 2 (`read_path_check_result` schema guard) |
| §6 Tests | Tasks 1 and 2 |

**Deviation from the spec, resolved:** §4 said the timer is stopped "on tab cleanup". `BaseTab` has no cleanup hook, so the timer is instead parented to `self.main_window` (dying with the window, matching `comfyui/tab.py`'s `_server_check_timer`) and stopped on resolve, failure, and timeout. Polling is bounded by the 180s timeout either way.

**Addition beyond the spec, deliberate:** the poll runs in a worker rather than directly in the timer callback. `poll_deadline_job_status` shells out with a 30s timeout, which would freeze the GUI on every third tick.

**Type consistency:** `submit_path_check` returns `(job_id, result_path)` and Task 4 unpacks exactly that. `read_path_check_result` returns `dict | None`, and `_poll_path_check_once` wraps it as `{"result": …, "status": …}`, which `_on_path_check_polled` reads by those two keys. Check dicts use `id`/`label`/`ok`/`detail` in `path_check._check`, in the tests' `_checks_by_id`, and in `_render_path_check_result`. `RESULT_SCHEMA = 1` is defined in both modules and asserted equal by `TestReadResult`.
