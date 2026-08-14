# ComfyUI Server Control Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start, stop and restart the ComfyUI farm server from the ComfyUI tab, and replace the status that collapses every heartbeat into one "online" with honest per-worker state.

**Architecture:** A Deadline `CommandLine` job runs `server.py` on a whitelisted worker with a task timeout as its lifetime cap. Heartbeat parsing moves out of the tab into a pure, testable module. The tab drives Start/Stop/Restart from that per-worker state.

**Tech Stack:** Python 3.10, PySide6, Deadline CommandLine plugin, pytest.

**Spec:** `docs/superpowers/specs/2026-08-14-comfyui-server-control-design.md`

## Global Constraints

- Repo root: `L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools`. Branch: `ui-overhaul`.
- Tests run via `_run_tests.ps1` (sets `PYTHONPATH`). `pytest-timeout` is NOT installed — never pass `--timeout`.
- Never hand-edit `resources/ui/tabs/_compiled/ui_*.py`. Edit the `.ui`, then regenerate with `pyside6-uic`.
- `logger = logging.getLogger(__name__)` per module. No `print()`.
- Paths embedded in Deadline `job_info`/`plugin_info` must pass through `normalize_path()` — Deadline treats backslashes in quoted arguments as escapes.
- Never call Deadline or read the network share on the GUI thread. Use `self.start_worker(...)`; `on_error` receives `(error_msg, traceback_str)`.
- Attributes used by signal handlers must be initialised in `initialize()` — the project's most common source of runtime `AttributeError`.
- `.ui` strings stay ASCII-only.
- Do not touch `resources/version.json` or `resources/changelog.md`.
- Server job name prefix must be excluded from `is_recoverable_luma_job()`, or every app launch adopts the server as a phantom generation job.

Throwaway single-file runner (create, use, delete at the end):

```powershell
# _run_one.ps1
Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe -m pytest tests\test_server_control.py -v
```

Run with: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`

## File Structure

| File | Responsibility |
|---|---|
| `python/comfyui/server_status.py` | **New.** Parse heartbeat files into per-worker state. Pure functions, no Qt, no Deadline. |
| `python/deadline/server_job.py` | **New.** Build/submit/find/stop the server Deadline job. |
| `python/core/config.py` | Server job name prefix. |
| `python/deadline/poller.py` | Exclude the server prefix from crash recovery. |
| `python/core/settings_manager.py` | `comfyui_server_max_hours`. |
| `resources/ui/tabs/settings.ui` | Max-lifetime spin box. |
| `python/ui/tabs/comfyui/tab.py` | Controls, per-worker status, fast poll. |
| `tests/test_server_control.py` | **New.** Covers both new modules. |

**Deviation from the spec, deliberate:** the spec listed `resources/ui/tabs/comfyui.ui` as needing new widgets. It does not. `serverStatusBanner` contains an empty `serverStatusLayout` that `_setup_server_status_banner` (`tab.py:255-266`) fills programmatically, so the buttons are added the same way as the existing status label. Only `settings.ui` needs a real edit.

---

### Task 1: Heartbeat parsing

**Files:**
- Create: `python/comfyui/server_status.py`
- Create: `tests/test_server_control.py`

**Interfaces:**
- Consumes: `load_json(path, default)` from `core.utils`.
- Produces:
  - `HEARTBEAT_DIRNAME = "_server_status"`, `DEFAULT_STALE_SECONDS = 60`
  - `read_server_heartbeats(network_path: str, stale_seconds: int = 60) -> Dict[str, dict]` — keyed by lower-cased hostname; each value has `hostname`, `status`, `uptime_seconds`, `jobs_completed`, `age_seconds`, `stale`
  - `online_workers(heartbeats: Dict[str, dict]) -> List[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_server_control.py`:

```python
"""Tests for ComfyUI server control - heartbeat status and the Deadline job."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from comfyui.server_status import (
    HEARTBEAT_DIRNAME,
    online_workers,
    read_server_heartbeats,
)


def _write_heartbeat(network_path, hostname, status="online", age_seconds=0,
                     uptime_seconds=120, jobs_completed=3, timestamp=None):
    """Write one heartbeat file the way server.py does."""
    directory = os.path.join(str(network_path), HEARTBEAT_DIRNAME)
    os.makedirs(directory, exist_ok=True)
    if timestamp is None:
        stamp = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        timestamp = stamp.isoformat()
    payload = {
        "hostname": hostname,
        "status": status,
        "uptime_seconds": uptime_seconds,
        "jobs_completed": jobs_completed,
        "timestamp": timestamp,
    }
    path = os.path.join(directory, f"heartbeat_{hostname}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


class TestReadHeartbeats:
    def test_no_network_path_is_empty(self):
        assert read_server_heartbeats("") == {}

    def test_missing_directory_is_empty(self, tmp_path):
        assert read_server_heartbeats(str(tmp_path)) == {}

    def test_fresh_heartbeat_is_reported_online(self, tmp_path):
        _write_heartbeat(tmp_path, "ls-ws-sim003", age_seconds=5)

        servers = read_server_heartbeats(str(tmp_path))

        assert set(servers) == {"ls-ws-sim003"}
        entry = servers["ls-ws-sim003"]
        assert entry["hostname"] == "ls-ws-sim003"
        assert entry["status"] == "online"
        assert entry["stale"] is False
        assert entry["jobs_completed"] == 3
        assert entry["age_seconds"] < 60

    def test_stale_heartbeat_is_kept_and_flagged(self, tmp_path):
        # Kept, not dropped: the UI must be able to say "last seen 4 minutes
        # ago" rather than have a server silently vanish.
        _write_heartbeat(tmp_path, "ls-ws-sim003", age_seconds=600)

        entry = read_server_heartbeats(str(tmp_path))["ls-ws-sim003"]

        assert entry["stale"] is True
        assert entry["age_seconds"] > 500

    def test_several_workers_are_reported_separately(self, tmp_path):
        # The bug this replaces: the old code collapsed every worker into one
        # "best" status, so any server anywhere read as online.
        _write_heartbeat(tmp_path, "worker-a", status="online", age_seconds=2)
        _write_heartbeat(tmp_path, "worker-b", status="offline", age_seconds=2)

        servers = read_server_heartbeats(str(tmp_path))

        assert servers["worker-a"]["status"] == "online"
        assert servers["worker-b"]["status"] == "offline"

    def test_malformed_files_are_skipped(self, tmp_path):
        directory = tmp_path / HEARTBEAT_DIRNAME
        directory.mkdir()
        (directory / "heartbeat_broken.json").write_text("{not json", encoding="utf-8")
        (directory / "heartbeat_nots.json").write_text('{"hostname": "x"}', encoding="utf-8")
        _write_heartbeat(tmp_path, "good", age_seconds=1)

        assert set(read_server_heartbeats(str(tmp_path))) == {"good"}

    def test_naive_timestamps_are_treated_as_utc(self, tmp_path):
        # Older servers wrote naive local time; mixing aware and naive
        # datetimes raises TypeError on subtraction.
        naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        _write_heartbeat(tmp_path, "legacy", timestamp=naive)

        entry = read_server_heartbeats(str(tmp_path))["legacy"]

        assert entry["stale"] is False

    def test_hostname_falls_back_to_the_filename(self, tmp_path):
        directory = tmp_path / HEARTBEAT_DIRNAME
        directory.mkdir()
        stamp = datetime.now(timezone.utc).isoformat()
        (directory / "heartbeat_nohost.json").write_text(
            json.dumps({"status": "online", "timestamp": stamp}), encoding="utf-8")

        assert read_server_heartbeats(str(tmp_path))["nohost"]["hostname"] == "nohost"


class TestOnlineWorkers:
    def test_only_fresh_online_servers_count(self, tmp_path):
        _write_heartbeat(tmp_path, "fresh-online", status="online", age_seconds=1)
        _write_heartbeat(tmp_path, "stale-online", status="online", age_seconds=900)
        _write_heartbeat(tmp_path, "fresh-starting", status="starting", age_seconds=1)

        assert online_workers(read_server_heartbeats(str(tmp_path))) == ["fresh-online"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: collection error — `ModuleNotFoundError: No module named 'comfyui.server_status'`

- [ ] **Step 3: Write the module**

Create `python/comfyui/server_status.py`:

```python
"""Read ComfyUI server heartbeats from the shared network path.

server.py writes <network_output_path>/_server_status/heartbeat_<hostname>.json
every ~20s. The workstation cannot reach the farm directly (see CLAUDE.md,
ComfyUI Farm Architecture), so these files are its only view of which workers
have a live server.

Pure functions over files - no Qt, no Deadline - so the logic driving the
status banner can actually be tested. It previously lived inline in the
ComfyUI tab and collapsed every worker into a single "best" status, which
reads "online" even when the worker your job lands on has no server.
"""
import glob
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List

from core.utils import load_json

logger = logging.getLogger(__name__)

HEARTBEAT_DIRNAME = "_server_status"
DEFAULT_STALE_SECONDS = 60


def _hostname_from_filename(path: str) -> str:
    """heartbeat_<host>.json -> <host>, for files with no hostname field."""
    base = os.path.basename(path)
    if base.startswith("heartbeat_") and base.endswith(".json"):
        return base[len("heartbeat_"):-len(".json")]
    return base


def read_server_heartbeats(network_path: str,
                           stale_seconds: int = DEFAULT_STALE_SECONDS) -> Dict[str, dict]:
    """Return {lower-cased hostname: info} for every heartbeat file found.

    Stale entries are returned with stale=True rather than dropped, so the UI
    can report "last seen 4 minutes ago" instead of a server silently
    disappearing from the list.
    """
    if not network_path:
        return {}

    heartbeat_dir = os.path.join(network_path, HEARTBEAT_DIRNAME)
    if not os.path.isdir(heartbeat_dir):
        return {}

    now = datetime.now(timezone.utc)
    servers: Dict[str, dict] = {}

    for path in glob.glob(os.path.join(heartbeat_dir, "heartbeat_*.json")):
        data = load_json(path, {})
        if not isinstance(data, dict) or "timestamp" not in data:
            logger.debug(f"Skipping malformed heartbeat {path}")
            continue

        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (ValueError, TypeError):
            logger.debug(f"Skipping heartbeat with unreadable timestamp {path}")
            continue

        # Older servers wrote naive local time; assume UTC when naive so the
        # subtraction below never mixes aware and naive datetimes.
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age_seconds = (now - timestamp).total_seconds()

        hostname = str(data.get("hostname") or _hostname_from_filename(path))
        servers[hostname.lower()] = {
            "hostname": hostname,
            "status": data.get("status", "offline"),
            "uptime_seconds": data.get("uptime_seconds", 0),
            "jobs_completed": data.get("jobs_completed", 0),
            "age_seconds": age_seconds,
            "stale": age_seconds > stale_seconds,
        }

    return servers


def online_workers(heartbeats: Dict[str, dict]) -> List[str]:
    """Hostnames with a fresh 'online' heartbeat, sorted for stable display."""
    return sorted(
        info["hostname"] for info in heartbeats.values()
        if info["status"] == "online" and not info["stale"]
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add python/comfyui/server_status.py tests/test_server_control.py
git commit -m "Add per-worker ComfyUI server heartbeat parsing"
```

---

### Task 2: Job identity, recovery exclusion, and the lifetime setting

**Files:**
- Modify: `python/core/config.py` (beside `DEADLINE_JOB_NAME_PREFIX_DIAGNOSTIC`)
- Modify: `python/deadline/poller.py` (`is_recoverable_luma_job`)
- Modify: `python/core/settings_manager.py` (validator + registry)
- Modify: `resources/ui/tabs/settings.ui`; regenerate `_compiled/ui_settings.py`
- Modify: `python/ui/tabs/settings_tab.py` (`_GLOBAL_SETTINGS_MAP`)
- Modify: `tests/test_server_control.py`

**Interfaces:**
- Produces: `DEADLINE_JOB_NAME_PREFIX_SERVER = "LUMA TOOLS SERVER - "`; setting `comfyui_server_max_hours` (default 8, 0–168, 0 = no cap).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server_control.py`:

```python
class TestServerJobIsNotAGenerationJob:
    """A server job must never be adopted by ComfyUI crash recovery.

    Regression shape: the farm path check shipped with the plain
    "LUMA TOOLS - " prefix, so every app launch recovered the probe as a
    running generation job and announced phantom completions.
    """

    def test_server_prefix_is_excluded_from_recovery(self):
        from core.config import DEADLINE_JOB_NAME_PREFIX_SERVER
        from deadline.poller import is_recoverable_luma_job

        assert not is_recoverable_luma_job(f"{DEADLINE_JOB_NAME_PREFIX_SERVER}ls-ws-sim003")

    def test_real_generation_jobs_are_still_recovered(self):
        from deadline.poller import is_recoverable_luma_job

        assert is_recoverable_luma_job("LUMA TOOLS - my_render")


class TestMaxHoursSetting:
    def test_defaults_to_eight_hours(self):
        from core.settings_manager import SETTINGS_REGISTRY

        assert SETTINGS_REGISTRY["comfyui_server_max_hours"].default == 8

    def test_out_of_range_values_are_clamped(self):
        from core.settings_manager import SETTINGS_REGISTRY

        validate = SETTINGS_REGISTRY["comfyui_server_max_hours"].validator
        assert validate(-5) == 0        # 0 means "no cap"
        assert validate(9999) == 168
        assert validate("not a number") == 8
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: `ImportError: cannot import name 'DEADLINE_JOB_NAME_PREFIX_SERVER'` and `KeyError: 'comfyui_server_max_hours'`

- [ ] **Step 3: Add the prefix and the recovery exclusion**

In `python/core/config.py`, directly after `DEADLINE_JOB_NAME_PREFIX_DIAGNOSTIC`:

```python
# The persistent ComfyUI server runs as a long-lived Deadline job. Like the
# diagnostic prefix above it must stay out of crash recovery - a server is not
# a generation job and never produces renders.
DEADLINE_JOB_NAME_PREFIX_SERVER = "LUMA TOOLS SERVER - "
```

In `python/deadline/poller.py`, extend the import and the guard:

```python
from core.config import (
    DEADLINE_PATH,
    DEADLINE_JOB_NAME_PREFIX,
    DEADLINE_JOB_NAME_PREFIX_DIAGNOSTIC,
    DEADLINE_JOB_NAME_PREFIX_SERVER,
)
```

```python
    if not job_name or job_name.startswith(
        (DEADLINE_JOB_NAME_PREFIX_DIAGNOSTIC, DEADLINE_JOB_NAME_PREFIX_SERVER)
    ):
        return False
```

Update that function's docstring so it names both exclusions:

```python
    """Is this a luma_tools job worth recovering as a running generation job?

    Diagnostic and server jobs are excluded. They carry their own prefixes
    precisely so crash recovery skips them: a farm path check is a 13-second
    probe and a ComfyUI server is a long-lived service, and neither produces
    renders. Adopting either makes the ComfyUI tab report phantom submissions
    and glow the Gallery for outputs that never arrive.
    """
```

- [ ] **Step 4: Add the setting**

In `python/core/settings_manager.py`, next to `_validate_deadline_priority`:

```python
def _validate_server_max_hours(v):
    """0 means no cap; 168 (one week) is the ceiling."""
    try:
        return max(0, min(168, int(v)))
    except (ValueError, TypeError):
        return 8
```

And in `SETTINGS_REGISTRY`, beside the other ComfyUI Deadline settings:

```python
    "comfyui_server_max_hours": SettingDef(
        "comfyui_server_max_hours", 8, "global", _validate_server_max_hours
    ),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: 15 passed

- [ ] **Step 6: Add the Settings field**

In `resources/ui/tabs/settings.ui`, inside `deadlineTargetLayout`, after the
`ComfyUIDeadlinePrioritySpinBox` item:

```xml
            <item>
             <widget class="QLabel" name="serverMaxHoursLabel">
              <property name="text">
               <string>Server max hours:</string>
              </property>
             </widget>
            </item>
            <item>
             <widget class="QSpinBox" name="ComfyUIServerMaxHoursSpinBox">
              <property name="minimum">
               <number>0</number>
              </property>
              <property name="maximum">
               <number>168</number>
              </property>
              <property name="value">
               <number>8</number>
              </property>
              <property name="toolTip">
               <string>A server started from Luma Tools is stopped by Deadline after this many hours, so one forgotten on a Friday does not hold a GPU worker all weekend. 0 means no limit.</string>
              </property>
             </widget>
            </item>
```

In `python/ui/tabs/settings_tab.py`, add to `_GLOBAL_SETTINGS_MAP` after the
priority entry:

```python
    ("comfyui_server_max_hours", "ComfyUIServerMaxHoursSpinBox", _SPINBOX),
```

Recompile:

```bash
python/venv/Scripts/pyside6-uic.exe resources/ui/tabs/settings.ui -o resources/ui/tabs/_compiled/ui_settings.py -g python
```

- [ ] **Step 7: Verify the app still loads Settings**

Write `_run_test.ps1` (delete it at the end of Task 5 — do NOT overwrite the
existing tracked `_run_test.ps1`; name this one `_launch.ps1`):

```powershell
Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe python\core\luma_tools.py --tab settings --auto-close 18
```

Run it, then:

```bash
powershell -Command "Get-Content (Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 40"
```

Expected: no `Traceback`, no `AttributeError`, `Settings deferred init` present.

- [ ] **Step 8: Commit**

```bash
git add python/core/config.py python/deadline/poller.py python/core/settings_manager.py python/ui/tabs/settings_tab.py resources/ui/tabs/settings.ui resources/ui/tabs/_compiled/ui_settings.py tests/test_server_control.py
git commit -m "Add the server job prefix, recovery exclusion and lifetime cap setting"
```

---

### Task 3: The server Deadline job

**Files:**
- Create: `python/deadline/server_job.py`
- Modify: `tests/test_server_control.py`

**Interfaces:**
- Consumes: `resolve_comfyui_targeting(pool=None, group=None, priority=None) -> (pool, group, priority)` from `deadline.utils`; `complete_deadline_job(job_id) -> (bool, str)` and `parse_job_info(stdout) -> dict` from `deadline.poller` / `deadline.parser`; `resolve_comfyui_paths(comfyui_path, mode, python_path) -> (python_exe, main_py)` from `comfyui.utils`; `run_command`, `normalize_path`, `safe_get_setting`.
- Produces:
  - `SERVER_SCRIPT_RELPATH = "comfyui/server.py"`
  - `list_group_workers(group: str) -> List[str]`
  - `server_script_path() -> str`
  - `worker_from_job_name(job_name: str) -> Optional[str]`
  - `build_server_job_info(worker, pool, group, priority, max_hours, comment) -> str`
  - `build_server_plugin_info(python_exe, server_script, comfyui_path, mode, python_path, port, flags) -> str`
  - `submit_server_job(worker: str, ...) -> Optional[str]`
  - `find_server_jobs(username: Optional[str] = None) -> Dict[str, str]` — lower-cased worker -> job id
  - `stop_server_job(job_id: str) -> Tuple[bool, str]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server_control.py`:

```python
class TestServerJobFiles:
    def test_job_info_whitelists_the_chosen_worker(self):
        from deadline.server_job import build_server_job_info

        text = build_server_job_info("ls-ws-sim003", "luma", "temp_compute", 50, 8, "tree")

        assert "Plugin=CommandLine\n" in text
        assert "Name=LUMA TOOLS SERVER - ls-ws-sim003\n" in text
        assert "Whitelist=ls-ws-sim003\n" in text
        assert "MachineLimit=1\n" in text
        assert "Pool=luma\n" in text
        assert "Group=temp_compute\n" in text

    def test_max_hours_becomes_a_task_timeout(self):
        from deadline.server_job import build_server_job_info

        text = build_server_job_info("w1", "luma", "temp_compute", 50, 8, "tree")

        assert "TaskTimeoutSeconds=28800\n" in text
        assert "OnTaskTimeout=Complete\n" in text

    def test_zero_hours_writes_no_timeout_at_all(self):
        # 0 means "no cap" - a TaskTimeoutSeconds=0 line would be read by
        # Deadline as an immediate timeout.
        from deadline.server_job import build_server_job_info

        text = build_server_job_info("w1", "luma", "temp_compute", 50, 0, "tree")

        assert "TaskTimeoutSeconds" not in text
        assert "OnTaskTimeout" not in text

    def test_the_comment_records_which_tree_submitted_it(self):
        # A dev submit puts dev server.py on a shared worker; that must never
        # be a silent surprise.
        from deadline.server_job import build_server_job_info

        text = build_server_job_info("w1", "luma", "temp_compute", 50, 8,
                                     "L:/tools/dev/luma_tools")

        assert "Comment=Started from L:/tools/dev/luma_tools\n" in text

    def test_plugin_info_uses_forward_slashes(self):
        from deadline.server_job import build_server_plugin_info

        text = build_server_plugin_info(
            r"D:\ComfyUI\python_embeded\python.exe",
            r"L:\tools\luma_tools\python\comfyui\server.py",
            r"D:\ComfyUI", "embedded", "", 8188, ["--lowvram"])

        arguments = [ln for ln in text.splitlines() if ln.startswith("Arguments=")][0]
        assert "\\" not in arguments
        assert "Executable=D:/ComfyUI/python_embeded/python.exe\n" in text
        assert '"L:/tools/luma_tools/python/comfyui/server.py"' in arguments
        assert '--comfyui-path "D:/ComfyUI"' in arguments
        assert "--port 8188" in arguments
        assert "--mode embedded" in arguments
        assert "--lowvram" in arguments

    def test_python_path_only_travels_in_standalone_mode(self):
        from deadline.server_job import build_server_plugin_info

        embedded = build_server_plugin_info(
            "py.exe", "s.py", "C:/ComfyUI", "embedded", "C:/py/python.exe", 8188, [])
        standalone = build_server_plugin_info(
            "py.exe", "s.py", "C:/ComfyUI", "standalone", "C:/py/python.exe", 8188, [])

        assert "--python-path" not in embedded
        assert '--python-path "C:/py/python.exe"' in standalone


class TestWorkerNameRoundTrip:
    def test_the_worker_survives_the_job_name(self):
        from deadline.server_job import build_server_job_info, worker_from_job_name

        text = build_server_job_info("ls-ws-sim003", "luma", "temp_compute", 50, 8, "t")
        name = [ln for ln in text.splitlines() if ln.startswith("Name=")][0][len("Name="):]

        assert worker_from_job_name(name) == "ls-ws-sim003"

    def test_unrelated_job_names_yield_nothing(self):
        from deadline.server_job import worker_from_job_name

        assert worker_from_job_name("LUMA TOOLS - my_render") is None
        assert worker_from_job_name("") is None


class TestServerScriptPath:
    def test_points_at_this_checkout(self):
        # The job runs server.py from whichever tree submitted it.
        from deadline.server_job import server_script_path

        path = server_script_path()

        assert path.endswith("comfyui/server.py")
        assert os.path.isfile(path), path
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: `ModuleNotFoundError: No module named 'deadline.server_job'`

- [ ] **Step 3: Write the module**

Create `python/deadline/server_job.py`:

```python
"""Run the persistent ComfyUI server as a Deadline job.

The server used to be started by hand over RDP. This submits the same command
as a long-lived CommandLine job pinned to one worker.

No farm script copying is needed, unlike the path check: server.py adds its own
parent directory to sys.path (comfyui/server.py:26-30) and L: is mapped on the
workers - the Deadline task log shows "Skipping L: because it is already
mapped". The job therefore runs server.py from whichever tree submitted it,
which is recorded in the job's Comment so a dev-submitted server is visible.
"""
import getpass
import logging
import os
from typing import Dict, List, Optional, Tuple

from core.config import (
    DEADLINE_PATH,
    DEADLINE_DEPARTMENT,
    DEADLINE_JOB_NAME_PREFIX_SERVER,
)
from core.settings_manager import safe_get_setting
from core.subprocess_utils import run_command
from core.utils import ensure_directory, normalize_path

logger = logging.getLogger(__name__)

SERVER_SCRIPT_RELPATH = "comfyui/server.py"


def server_script_path() -> str:
    """Absolute path to server.py in the tree this code is running from."""
    python_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(python_root, "comfyui", "server.py")


def submitting_tree() -> str:
    """Repo root of the submitting checkout, for the job Comment."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def list_group_workers(group: str) -> List[str]:
    """Deadline worker names in a group. Empty list if Deadline can't answer."""
    if not DEADLINE_PATH or not group:
        return []
    try:
        result = run_command([DEADLINE_PATH, "GetSlaveNamesInGroup", group], timeout=30)
    except Exception as exc:
        logger.warning(f"Could not list workers in group {group}: {exc}")
        return []
    if result.returncode != 0:
        logger.warning(f"GetSlaveNamesInGroup failed: {result.stderr.strip()}")
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def worker_from_job_name(job_name: str) -> Optional[str]:
    """Recover the worker a server job was started for, or None."""
    if not job_name or not job_name.startswith(DEADLINE_JOB_NAME_PREFIX_SERVER):
        return None
    worker = job_name[len(DEADLINE_JOB_NAME_PREFIX_SERVER):].strip()
    return worker or None


def build_server_job_info(worker: str, pool: str, group: str, priority: int,
                          max_hours: int, comment: str) -> str:
    """Deadline job_info for a server pinned to one worker."""
    lines = [
        "Plugin=CommandLine",
        f"Name={DEADLINE_JOB_NAME_PREFIX_SERVER}{worker}",
        f"Comment=Started from {comment}",
        f"Department={DEADLINE_DEPARTMENT}",
        f"Pool={pool}",
        f"Group={group}",
        f"Priority={priority}",
        "Frames=0",
        "ChunkSize=1",
        "MachineLimit=1",
        # Whitelist is what makes "start a server on THIS worker" deterministic
        # rather than "wherever Deadline feels like putting it".
        f"Whitelist={worker}",
    ]
    if max_hours:
        # 0 means no cap - and a TaskTimeoutSeconds=0 line would read as an
        # immediate timeout, so the keys are omitted entirely instead.
        lines.append(f"TaskTimeoutSeconds={int(max_hours) * 3600}")
        lines.append("OnTaskTimeout=Complete")
    lines.append("OnJobComplete=Delete")
    return "\n".join(lines) + "\n"


def build_server_plugin_info(python_exe: str, server_script: str, comfyui_path: str,
                             mode: str, python_path: str, port: int,
                             flags: List[str]) -> str:
    """Deadline plugin_info running server.py under the ComfyUI interpreter."""
    script = normalize_path(server_script)
    arguments = (
        f'"{script}" '
        f'--comfyui-path "{normalize_path(comfyui_path.rstrip("/" + chr(92)))}" '
        f'--port {port} '
        f'--mode {mode}'
    )
    if mode == "standalone" and python_path:
        arguments += f' --python-path "{normalize_path(python_path)}"'
    for flag in flags:
        arguments += f" {flag}"

    return (
        f"Executable={normalize_path(python_exe)}\n"
        f"Arguments={arguments}\n"
        f"StartupDirectory={normalize_path(os.path.dirname(script))}\n"
    )


def _server_flags() -> List[str]:
    """Launch flags from global settings, matching server.py's own defaults.

    --normalvram is deliberately absent: ComfyUI removed it and passing it
    aborts startup.
    """
    flags = []
    if safe_get_setting("comfyui_lowvram", False):
        flags.append("--lowvram")
    elif safe_get_setting("comfyui_highvram", False):
        flags.append("--highvram")
    if safe_get_setting("comfyui_disable_smart_memory", False):
        flags.append("--disable-smart-memory")
    if safe_get_setting("comfyui_fast_mode", False):
        flags.append("--fast")
    return flags


def submit_server_job(worker: str, pool: Optional[str] = None,
                      group: Optional[str] = None,
                      priority: Optional[int] = None) -> Optional[str]:
    """Submit a ComfyUI server job pinned to `worker`. Returns the job id.

    Runs in a worker thread - it shells out to deadlinecommand.
    """
    if not worker:
        raise ValueError("No worker given for the server job")
    if not DEADLINE_PATH:
        raise RuntimeError("Deadline is not available on this machine")

    comfyui_path = safe_get_setting("comfyui_path", "")
    if not comfyui_path:
        raise RuntimeError("No ComfyUI path is configured")

    network_path = safe_get_setting("network_output_path", "")
    if not network_path:
        raise RuntimeError("No network output path is configured")

    from comfyui.utils import resolve_comfyui_paths
    from deadline.utils import resolve_comfyui_targeting

    mode = safe_get_setting("comfyui_mode", "embedded")
    python_path = safe_get_setting("comfyui_python_path", "")
    python_exe, _ = resolve_comfyui_paths(comfyui_path, mode, python_path or None)

    resolved_pool, resolved_group, resolved_priority = resolve_comfyui_targeting(
        pool, group, priority)
    max_hours = safe_get_setting("comfyui_server_max_hours", 8)
    port = safe_get_setting("comfyui_port", 8188)

    job_dir = os.path.join(network_path, "_server_jobs", worker)
    ensure_directory(job_dir)
    job_info_path = os.path.join(job_dir, "server_job_info.txt")
    plugin_info_path = os.path.join(job_dir, "server_plugin_info.txt")

    with open(job_info_path, "w", encoding="utf-8") as handle:
        handle.write(build_server_job_info(
            worker, resolved_pool, resolved_group, resolved_priority,
            max_hours, submitting_tree()))
    with open(plugin_info_path, "w", encoding="utf-8") as handle:
        handle.write(build_server_plugin_info(
            python_exe, server_script_path(), comfyui_path, mode,
            python_path, port, _server_flags()))

    from deadline.utils import submit_deadline_job

    job_id = submit_deadline_job(
        [DEADLINE_PATH, job_info_path, plugin_info_path], log_prefix="[ComfyUIServer]")
    logger.info(f"ComfyUI server job {job_id} submitted for {worker}")
    return job_id


def find_server_jobs(username: Optional[str] = None) -> Dict[str, str]:
    """Return {lower-cased worker: job_id} for this user's live server jobs."""
    from deadline.parser import parse_job_info

    if not DEADLINE_PATH:
        return {}
    username = username or getpass.getuser()

    jobs: Dict[str, str] = {}
    for status_filter in ("Active", "Pending"):
        try:
            result = run_command(
                [DEADLINE_PATH, "GetJobIdsFilter",
                 f"Status={status_filter}", f"UserName={username}"],
                timeout=20,
            )
        except Exception as exc:
            logger.warning(f"Could not list {status_filter} jobs: {exc}")
            continue
        if result.returncode != 0:
            continue

        for job_id in [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]:
            try:
                job_result = run_command([DEADLINE_PATH, "GetJob", job_id], timeout=15)
            except Exception:
                continue
            if job_result.returncode != 0:
                continue
            worker = worker_from_job_name(parse_job_info(job_result.stdout).get("Name", ""))
            if worker:
                jobs[worker.lower()] = job_id

    return jobs


def stop_server_job(job_id: str) -> Tuple[bool, str]:
    """Complete the server job, which terminates the process on the worker."""
    from deadline.poller import complete_deadline_job

    return complete_deadline_job(job_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `powershell -ExecutionPolicy Bypass -File _run_one.ps1`
Expected: 24 passed

- [ ] **Step 5: Commit**

```bash
git add python/deadline/server_job.py tests/test_server_control.py
git commit -m "Add the ComfyUI server Deadline job"
```

---

### Task 4: Server controls in the ComfyUI tab

**Files:**
- Modify: `python/ui/tabs/comfyui/tab.py` — module-level worker functions, `initialize()`, `_setup_server_status_banner`, `_read_heartbeat_status`, `_on_heartbeat_result`

**Interfaces:**
- Consumes: everything produced by Tasks 1 and 3; `self.start_worker(...)`; `confirm_action(title, message, parent)` from `dialog_helpers`; `set_role(widget, ...)` already imported by `tab.py`.
- Produces: no public API.

- [ ] **Step 1: Add the module-level worker functions**

At module level in `python/ui/tabs/comfyui/tab.py`, after the imports:

```python
def _list_comfyui_workers():
    """Worker function - the Deadline workers that run ComfyUI (no Qt access)."""
    from deadline.server_job import list_group_workers
    from deadline.utils import resolve_comfyui_targeting

    _pool, group, _priority = resolve_comfyui_targeting()
    return list_group_workers(group)


def _read_server_state():
    """Worker function - per-worker heartbeat state (no Qt access)."""
    from comfyui.server_status import read_server_heartbeats
    from core.settings_manager import safe_get_setting

    network_path = safe_get_setting("network_output_path", "")
    if not network_path:
        return {"servers": {}, "error": "Network output path not configured"}
    return {
        "servers": read_server_heartbeats(
            network_path, ComfyUITab._HEARTBEAT_STALE_SECONDS),
        "error": "",
    }


def _start_server_worker(worker):
    """Worker function - submit a server job (no Qt access)."""
    from deadline.server_job import submit_server_job

    return submit_server_job(worker)


def _stop_server_worker(worker):
    """Worker function - stop the server job for a worker (no Qt access).

    Returns (ok, message). ok=False with message="no-job" means a server is
    running that Luma Tools did not start - typically one launched by hand.
    """
    from deadline.server_job import find_server_jobs, stop_server_job

    job_id = find_server_jobs().get(worker.lower())
    if not job_id:
        return (False, "no-job")
    return stop_server_job(job_id)
```

- [ ] **Step 2: Replace the heartbeat reader and add control state**

Replace the whole `_read_heartbeat_status` static method (`tab.py:284-349`) —
its per-worker logic now lives in `comfyui/server_status.py` — and rewrite
`_on_heartbeat_result` to derive the banner text from per-worker data:

```python
    def _on_heartbeat_result(self, result):
        """Handle heartbeat check result on the main thread."""
        self._heartbeat_pending = False
        if not hasattr(self, '_server_status_label') or not self._server_status_label:
            return

        servers = result.get("servers", {})
        self._server_states = servers
        status, info = self._summarise_servers(servers, result.get("error", ""))
        self._update_server_indicator(status, info)
        self._update_server_controls()

    def _summarise_servers(self, servers, error):
        """Turn per-worker heartbeats into (status, detail) for the banner.

        The old code collapsed every worker into one "best" status, so any
        server anywhere read as online even when the worker a job lands on has
        none. The count is now explicit.
        """
        if error:
            return ("unknown", error)

        total = len(self._server_workers) or len(servers)
        online = [i for i in servers.values() if i["status"] == "online" and not i["stale"]]
        starting = [i for i in servers.values() if i["status"] == "starting" and not i["stale"]]

        lines = []
        for info in sorted(servers.values(), key=lambda i: i["hostname"]):
            age = int(info["age_seconds"])
            uptime_min = int(info["uptime_seconds"]) // 60
            state = info["status"] if not info["stale"] else f"stale ({age}s)"
            lines.append(
                f"{info['hostname']}: {state} | up {uptime_min}m | "
                f"jobs {info['jobs_completed']}"
            )
        if not lines:
            lines.append("No server heartbeats found")
        detail = "\n".join(lines)

        if online:
            names = ", ".join(sorted(i["hostname"] for i in online))
            return ("online", f"{len(online)} of {total} workers online - {names}\n\n{detail}")
        if starting:
            return ("starting", detail)
        return ("offline", detail)
```

- [ ] **Step 3: Add the control buttons**

Extend `_setup_server_status_banner` (`tab.py:251-266`), after the existing
`addStretch()`:

```python
        # Buttons live here rather than in comfyui.ui because this banner's
        # layout is populated programmatically (the status label above is too).
        from PySide6.QtWidgets import QPushButton

        self._server_start_button = QPushButton("Start Server")
        self._server_start_button.clicked.connect(self._on_start_server)
        self._server_stop_button = QPushButton("Stop")
        self._server_stop_button.clicked.connect(self._on_stop_server)
        self._server_restart_button = QPushButton("Restart")
        self._server_restart_button.clicked.connect(self._on_restart_server)

        for button in (self._server_start_button, self._server_stop_button,
                       self._server_restart_button):
            button.setProperty("density", "sm")
            button.setProperty("role", "secondary")
            button.setEnabled(False)
            self.ui.serverStatusLayout.addWidget(button)

        # Which workers exist is a Deadline query - keep it off the GUI thread.
        self.start_worker(
            _list_comfyui_workers,
            on_result=self._on_workers_listed,
            on_error=lambda msg, tb="": logger.debug(f"Worker list unavailable: {msg}"),
        )
```

And add the control methods:

```python
    # =========================================================================
    # SERVER CONTROL (start / stop / restart the farm server)
    # =========================================================================

    _SERVER_FAST_POLL_MS = 5000
    _SERVER_NORMAL_POLL_MS = 30000
    _SERVER_ACTION_TIMEOUT_S = 300

    def _on_workers_listed(self, workers):
        """Remember the ComfyUI group's workers (GUI thread)."""
        self._server_workers = workers or []
        if not self._selected_worker and self._server_workers:
            self._selected_worker = self._server_workers[0]
        self._update_server_controls()

    def _target_worker(self):
        """The worker the buttons act on.

        With one worker in the group there is nothing to choose. With several,
        prefer the one already running a server so Stop and Restart act on
        what the banner is reporting.
        """
        if self._selected_worker:
            return self._selected_worker
        for host, info in self._server_states.items():
            if info["status"] == "online" and not info["stale"]:
                return info["hostname"]
        return ""

    def _update_server_controls(self):
        """Drive button enablement from the heartbeat state."""
        if not hasattr(self, '_server_start_button'):
            return

        from core.config import DEADLINE_PATH

        worker = self._target_worker()
        info = self._server_states.get(worker.lower(), {}) if worker else {}
        is_online = bool(info) and info.get("status") == "online" and not info.get("stale")
        busy = self._server_action is not None

        if not DEADLINE_PATH:
            for button in (self._server_start_button, self._server_stop_button,
                           self._server_restart_button):
                button.setEnabled(False)
                button.setToolTip("Deadline is not available on this machine")
            return

        self._server_start_button.setEnabled(bool(worker) and not is_online and not busy)
        self._server_stop_button.setEnabled(is_online and not busy)
        self._server_restart_button.setEnabled(is_online and not busy)
        tip = f"Target worker: {worker}" if worker else "No ComfyUI workers found"
        for button in (self._server_start_button, self._server_stop_button,
                       self._server_restart_button):
            button.setToolTip(tip)

    def _set_server_poll(self, fast):
        """Poll the heartbeat faster while waiting for a state change."""
        timer = getattr(self, '_server_check_timer', None)
        if timer:
            timer.start(self._SERVER_FAST_POLL_MS if fast else self._SERVER_NORMAL_POLL_MS)

    def _on_start_server(self):
        worker = self._target_worker()
        if not worker:
            self.show_status("No ComfyUI workers found on Deadline", "warning")
            return
        self._server_action = "start"
        self._update_server_controls()
        self.show_status(f"Submitting ComfyUI server job for {worker}...", "info")
        self.start_worker(
            _start_server_worker, worker,
            on_result=self._on_server_started,
            on_error=self._on_server_action_error,
        )

    def _on_server_started(self, job_id):
        if not job_id:
            self._server_action = None
            self._update_server_controls()
            self.show_status("Deadline did not accept the server job", "error")
            return
        logger.info(f"ComfyUI server job submitted: {job_id}")
        self.show_status("Server job queued - waiting for it to come online...", "info")
        self._server_action_started = time.monotonic()
        self._set_server_poll(True)
        self._check_server_status()

    def _on_stop_server(self):
        worker = self._target_worker()
        if not worker:
            return
        if not confirm_action(
            "Stop ComfyUI Server",
            f"Stop the ComfyUI server on {worker}?\n\n"
            "Models loaded into VRAM will be discarded, and any ComfyUI job "
            "currently rendering on that worker will fail.",
            self.main_window,
        ):
            return
        self._server_action = "stop"
        self._update_server_controls()
        self.show_status(f"Stopping the server on {worker}...", "info")
        self.start_worker(
            _stop_server_worker, worker,
            on_result=self._on_server_stopped,
            on_error=self._on_server_action_error,
        )

    def _on_server_stopped(self, result):
        ok, message = result
        if not ok and message == "no-job":
            # The heartbeat is real but Luma Tools did not start it - almost
            # always a server launched by hand on the worker itself.
            self._server_action = None
            self._update_server_controls()
            self.show_status(
                "That server was not started from Luma Tools, so it must be "
                "stopped on the worker itself", "warning")
            return
        if not ok:
            self._server_action = None
            self._update_server_controls()
            self.show_status(f"Could not stop the server: {message}", "error")
            return
        self.show_status("Server job completed - waiting for it to go offline...", "info")
        self._server_action_started = time.monotonic()
        self._set_server_poll(True)
        self._check_server_status()

    def _on_restart_server(self):
        """Stop, then start once the heartbeat has gone."""
        self._server_restart_pending = True
        self._on_stop_server()
        if self._server_action is None:
            self._server_restart_pending = False

    def _on_server_action_error(self, error_msg, traceback_str=""):
        logger.error(f"Server control failed: {error_msg}")
        self._server_action = None
        self._server_restart_pending = False
        self._set_server_poll(False)
        self._update_server_controls()
        self.show_status(f"Server control failed: {error_msg}", "error")

    def _settle_server_action(self):
        """Resolve an in-flight start/stop against the latest heartbeat."""
        if self._server_action is None:
            return

        worker = self._target_worker()
        info = self._server_states.get(worker.lower(), {}) if worker else {}
        is_online = bool(info) and info.get("status") == "online" and not info.get("stale")
        elapsed = time.monotonic() - self._server_action_started

        if self._server_action == "start" and is_online:
            self._server_action = None
            self._set_server_poll(False)
            self.show_status(f"ComfyUI server online on {worker}", "success")
        elif self._server_action == "stop" and not is_online:
            self._server_action = None
            self._set_server_poll(False)
            if self._server_restart_pending:
                self._server_restart_pending = False
                self._on_start_server()
            else:
                self.show_status("ComfyUI server stopped", "success")
        elif elapsed > self._SERVER_ACTION_TIMEOUT_S:
            action = self._server_action
            self._server_action = None
            self._server_restart_pending = False
            self._set_server_poll(False)
            self.show_status(
                f"Server {action} did not settle within 5 minutes - check Deadline",
                "warning")
        self._update_server_controls()
```

Call `_settle_server_action()` at the end of `_on_heartbeat_result`, after
`_update_server_controls()`.

Add `import time` at the top of `tab.py` if it is not already imported, and
`from dialog_helpers import confirm_action` if absent.

- [ ] **Step 4: Initialise the state**

In `initialize()`, beside the other server state (near `self._heartbeat_pending = False`):

```python
        # Server control state. Initialised here because signal handlers read
        # it - an uninitialised attribute is this codebase's most common
        # source of runtime AttributeError.
        self._server_states = {}
        self._server_workers = []
        self._selected_worker = ""
        self._server_action = None
        self._server_action_started = 0.0
        self._server_restart_pending = False
```

- [ ] **Step 5: Verify the tab loads and the buttons render**

Run `_launch.ps1` from Task 2 Step 7 with `--tab comfyui --auto-close 25`, then
read the log:

```bash
powershell -Command "Get-Content (Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 60"
```

Expected: no `Traceback`, no `AttributeError`, `ComfyUI deferred init` present.
The banner shows a per-worker line such as `1 of 1 workers online - ls-ws-sim003`
when a server is up, or `No server heartbeats found` when not.

- [ ] **Step 6: Run the full suite**

Run: `powershell -ExecutionPolicy Bypass -File _run_tests.ps1`
Expected: no new failures against the pre-change baseline.

- [ ] **Step 7: Commit**

```bash
git add python/ui/tabs/comfyui/tab.py
git commit -m "Add Start/Stop/Restart controls and per-worker server status"
```

---

### Task 5: Live farm verification

**Files:** none modified unless a defect turns up.

- [ ] **Step 1: Confirm no server is running**

```bash
powershell -Command "Get-ChildItem 'W:\LumaRND\luma_tools\_server_status\' | Select-Object Name, LastWriteTime"
```

If a heartbeat is fresh, a server is already up — stop it on the worker before
testing Start, or test Stop first.

- [ ] **Step 2: Start a server from the UI**

Launch with `--tab comfyui` (no `--auto-close`), click **Start Server**, and
watch the banner go queued → online. Confirm on Deadline:

```bash
"C:/Program Files/Thinkbox/Deadline10/bin/deadlinecommand.exe" GetJobIdsFilter "Status=Active" "UserName=christophe.leyder"
```

Expected: a job named `LUMA TOOLS SERVER - <worker>` with `Whitelist` set to
that worker, and a fresh heartbeat within ~60s.

- [ ] **Step 3: Confirm it is not adopted as a generation job**

Relaunch the app while the server job is running and read the log:

```bash
powershell -Command "Get-Content (Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName | Select-String -Pattern 'Recovered .* running ComfyUI'"
```

Expected: **no match.** A match means the recovery exclusion from Task 2 is not
working and the server is being reported as a phantom generation job.

- [ ] **Step 4: Stop it from the UI**

Click **Stop**, accept the confirmation, and watch the banner go offline within
~60s. Confirm the Deadline job is gone.

- [ ] **Step 5: Verify the manual-server path**

Start a server by hand on the worker (the RDP command), then click **Stop** in
the UI. Expected: "That server was not started from Luma Tools, so it must be
stopped on the worker itself" — not a silent failure.

- [ ] **Step 6: Clean up and report**

```bash
rm -f _run_one.ps1 _launch.ps1
```

Report: which tests pass, what the live start/stop did, and any pre-existing
failures found but not fixed.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 `server_status.py` | Task 1 |
| §2 `server_job.py` | Task 3 |
| §3 config prefix | Task 2 |
| §4 poller exclusion | Task 2 (+ live check in Task 5 Step 3) |
| §5 `comfyui_server_max_hours` | Task 2 |
| §6 UI, button-state table, fast poll | Task 4 |
| Data flow (start/stop/restart) | Task 4 Step 3 |
| Error handling table | Task 4 (`_on_server_action_error`, `no-job` branch, timeout branch, `DEADLINE_PATH` guard); Task 3 (`submit_server_job` preconditions, `list_group_workers` fallback) |
| Testing | Tasks 1–3, live in Task 5 |

**Deviations from the spec, deliberate:**

1. **No `comfyui.ui` edit.** `serverStatusBanner`'s layout is filled
   programmatically, so buttons are added the same way as the existing status
   label. Recorded in File Structure.
2. **Stop stays enabled for a manually-started server** and explains on click,
   rather than being disabled up front as the spec's table said. Knowing
   whether a job exists requires a Deadline query; doing that every 30s in the
   passive poll costs several `deadlinecommand` invocations per user for
   information needed only when the button is pressed. The message appears
   exactly when it is relevant.
3. **No standalone worker-picker widget.** `_target_worker()` picks the single
   group worker, or the one already online. A picker earns its place only when
   the group actually has several workers *and* more than one runs a server;
   adding it now would be building for a farm that does not exist yet. The
   selection already routes through `_selected_worker`, so a picker drops in
   without restructuring.

**Type consistency:** `read_server_heartbeats` returns `{lower host: info}` and
every consumer looks up with `.lower()`. `find_server_jobs` is keyed the same
way. `_stop_server_worker` returns `(bool, str)`, matching `stop_server_job` and
`complete_deadline_job`. `worker_from_job_name` returns `Optional[str]` and both
call sites test for falsiness. `build_server_job_info(worker, pool, group,
priority, max_hours, comment)` has the same argument order in every test and
call.
