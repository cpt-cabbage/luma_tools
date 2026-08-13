# Farm Path Check — Design

**Date:** 2026-08-13
**Status:** Approved, ready for implementation planning

## Problem

The Settings tab presents `comfyui_path` and `comfyui_python_path` as ordinary
paths with a local `Browse...` picker. They are neither. ComfyUI runs on a
Deadline farm worker; these values are only ever resolved there
(`deadline/submitter.py:114` → `resolve_comfyui_paths` → embedded into
`plugin_info.txt`). Nothing in the UI says so, and nothing tells the user
whether the values they typed are valid on the machines that will use them. A
wrong path surfaces much later as an opaque Deadline job failure.

Two changes address this:

1. Say plainly, in the UI, that these paths live on the farm.
2. Add a **Verify on Farm** button that submits a small Deadline job to check
   them where they matter and reports the result inline.

## Scope

In scope: wording in `settings.ui`, a farm-side check script, a Deadline
submission module for it, Settings tab wiring, tests.

Out of scope (deliberate, YAGNI): sweeping every worker in the group,
auto-checking on tab open, a settings key for the poll timeout, persisting the
last result across sessions.

## 1. Wording (`resources/ui/tabs/settings.ui`)

Inside `globalSettingsGroupBox`, above the `comfyuiModeLayout` row, add a
wrapped help label (`comfyuiFarmNoteLabel`):

> ComfyUI runs on Deadline farm workers, not on your machine. These paths are
> resolved on the worker that picks up the job — they don't need to exist
> locally.

Label and tooltip changes:

| Widget | Change |
|---|---|
| `comfyuiPathLabel` | "ComfyUI Path:" → "ComfyUI Path (farm):" |
| `comfyuiPythonLabel` | "Python Path:" → "Python Path (farm):" |
| `ComfyUIPathEdit` | placeholder → "Path to ComfyUI installation on the farm worker…"; tooltip states the path is resolved on the worker |
| `ComfyUIPythonEdit` | placeholder and tooltip likewise |
| `BrowseComfyUIPath`, `BrowseComfyUIPython` | tooltip: browsing is a convenience — the path must be valid on the worker |
| `ComfyUIModeButton` | tooltip: installation type *on the farm worker* |
| `NetworkOutputEdit` | tooltip gains "the only shared filesystem between your workstation and the farm" |

The `Browse...` pickers stay. The farm path is often reachable from the
workstation under the same UNC or mapped path, so browsing still helps; the
reframing removes the false implication that local existence is what matters.

Recompile after editing:

```
python/venv/Scripts/pyside6-uic.exe resources/ui/tabs/settings.ui \
  -o resources/ui/tabs/_compiled/ui_settings.py -g python
```

## 2. Farm-side script — `python/comfyui/path_check.py`

Runs on the worker. Must import with no `comfyui` package on `sys.path` (see
`tests/test_farm_isolation.py`), so: stdlib only, plus `import comfyui_utils`
for `resolve_comfyui_paths` — the same pattern `runner.py` uses.
`comfyui/utils.py` is stdlib-only, so this is safe.

CLI: `--comfyui-path`, `--comfyui-mode`, `--comfyui-python`, `--result-file`.

Checks, each reported independently:

| id | verifies |
|---|---|
| `comfyui_dir` | path exists and is a directory |
| `main_py` | `<path>/ComfyUI/main.py`, falling back to `<path>/main.py`; detail records which layout matched |
| `python_exe` | interpreter resolved from `comfyui_mode` exists on disk |
| `python_runs` | launches it with `-c "import sys; print(sys.version)"` and captures the version |
| `network_path` | the share just written to, proving worker → share reachability |

Result written to `--result-file` as JSON:

```json
{
  "schema": 1,
  "ok": false,
  "hostname": "RENDER07",
  "os": "Windows-10-...",
  "python_version": "3.12.4 (tags/...)",
  "timestamp": "2026-08-13T10:04:11Z",
  "checks": [
    {"id": "comfyui_dir", "label": "ComfyUI path", "ok": true,  "detail": "W:/apps/ComfyUI_windows_portable"},
    {"id": "python_exe",  "label": "Python executable", "ok": false, "detail": "not found: .../python_embeded/python.exe"}
  ]
}
```

The script exits 0 after writing the file even when checks fail — a failed
*check* must not look like a failed *job*. Only an unwritable result file exits
non-zero.

## 3. Submission — `python/deadline/path_check.py`

A new module rather than an addition to `submitter.py`, which is 592 lines and
entirely about workflow submission.

- `submit_path_check(comfyui_path, comfyui_mode, comfyui_python, network_output_path) -> (job_id, result_path)`
- Job directory: `<network_output_path>/_path_checks/<user>_<host>_<timestamp>/`
- Copies `path_check.py` → `comfyui_path_check.py` and `utils.py` →
  `comfyui_utils.py` into that directory
- `job_info.txt`: `Plugin=Python`, `Frames=0`, `ChunkSize=1`, `MachineLimit=1`,
  `OnJobComplete=Delete`, pool `DEADLINE_POOL`, group `DEADLINE_GROUP_COMFYUI`,
  priority `min(99, DEADLINE_PRIORITY_COMFYUI + 20)` so a quick diagnostic does
  not queue behind renders
- `plugin_info.txt`: `ScriptFile=<job dir>/comfyui_path_check.py`,
  `Version=3.10`,
  `Arguments=--comfyui-path "…" --comfyui-mode … --comfyui-python "…" --result-file "…"`
  — the version must name a row configured under *Configure Plugins → Python →
  Python Executables* in the Deadline repository (3.9 / 3.10 / 3.11 are
  configured in this studio). Defined as a module constant
  `DEADLINE_PYTHON_PLUGIN_VERSION = "3.10"` with a comment pointing at that
  dialog. The check script is stdlib-only and version-tolerant, so any
  configured 3.x works.
- All embedded paths pass through `normalize_path` (forward slashes; Deadline's
  parser treats backslashes in quoted arguments as escapes)
- `read_path_check_result(path) -> dict | None`
- `cleanup_old_path_checks(root, keep_days=1)`, called on each submit

**Why `Plugin=Python`:** it runs under an interpreter configured centrally in
the Deadline repository, entirely independent of the ComfyUI install being
tested. A missing or broken `comfyui_python_path` therefore reports as a clear
per-item ✗ rather than an opaque job error, and "no result file" means the farm
never picked the job up.

The residual dependency is that the worker actually has the configured
interpreter installed (e.g. `C:\Program Files\Python310\python.exe`). If it does
not, Deadline errors the job and the UI surfaces that error message — which is
itself actionable, and distinct from a ComfyUI path problem.

## 4. Settings tab wiring (`python/ui/tabs/settings_tab.py`)

New widgets in a row beneath the Python path row: `VerifyComfyUIPathButton`
("Verify on Farm") and `comfyuiVerifyStatus` (wrapped label).

**Values checked:** whatever is currently typed in `ComfyUIPathEdit`,
`ComfyUIPythonEdit`, and the mode button — *not* the saved global setting. This
lets an admin test a change before committing it to everyone. The status line
states that it is checking unsaved field values.

Flow:

1. Guard: empty `comfyui_path` → inline warning, no submit. `DEADLINE_PATH`
   unset → inline "Deadline not available", no submit.
2. `start_worker(submit_path_check, worker_kwargs={...}, on_result=…, on_error=…)`
   — submission shells out to `deadlinecommand` and must not block the GUI.
3. On job id: disable the button, store `self._path_check`, start a 2s `QTimer`.
   Each tick reads `result.json`; every third tick also calls
   `poll_deadline_job_status(job_id)` to drive the status text
   (Queued on farm… → Running… → result).
4. Result: render one ✓/✗ line per check using `UIColors` success/error, ending
   with the worker hostname and the reported Python version.
5. Deadline reports `Failed`: surface the error message inline, stop polling
   early.
6. Timeout at 180s: "No answer from the farm after 3 minutes — the check job may
   still be queued." Button re-enabled.

State (`self._path_check = None`, `self._path_check_timer = None`) is
initialized in `initialize()`, per the project rule that uninitialized
attributes are the primary source of runtime `AttributeError`s. The timer is
stopped on resolve, on timeout, and on tab cleanup. Polling is bounded by the
180s timeout, so the tab never leaves an unbounded network poll running.

Signal connection follows the file's existing style:

```python
if hasattr(self.ui, 'VerifyComfyUIPathButton'):
    self.ui.VerifyComfyUIPathButton.clicked.connect(self._on_verify_comfyui_path)
```

## 5. Error handling

| Failure | Behaviour |
|---|---|
| Submission returns no job id | Inline ✗ "Could not submit check job to Deadline", `logger.error` |
| `result.json` missing at timeout | Inline "no answer from the farm" |
| `result.json` unparseable or wrong `schema` | Treated as no answer; parse error logged |
| Deadline job status `Failed` | Inline Deadline error message, polling stops |

## 6. Tests — `tests/test_path_check.py`

- `run_checks()` against tmp-dir fixtures: all pass; missing directory; missing
  `main.py`; python executable missing
- Result JSON shape: required keys present, `ok` is the conjunction of check
  results
- `job_info` / `plugin_info` text generation with no Deadline call — asserts
  `Plugin=Python`, `ScriptFile`, pool, group, and forward-slash paths
- `tests/test_farm_isolation.py`: add `comfyui_path_check.py` to the list of
  farm scripts that must import in isolation

## Files touched

| File | Change |
|---|---|
| `resources/ui/tabs/settings.ui` | wording, new help label, verify button + status label |
| `resources/ui/tabs/_compiled/ui_settings.py` | regenerated via `pyside6-uic` |
| `python/comfyui/path_check.py` | new — farm-side checks |
| `python/deadline/path_check.py` | new — job submission, result read, cleanup |
| `python/ui/tabs/settings_tab.py` | button handler, polling timer, result rendering |
| `tests/test_path_check.py` | new |
| `tests/test_farm_isolation.py` | register the new farm script |
