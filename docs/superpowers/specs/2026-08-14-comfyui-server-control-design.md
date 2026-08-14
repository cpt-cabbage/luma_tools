# ComfyUI Server Control — Design (Phase 1)

**Date:** 2026-08-14
**Status:** Approved, ready for implementation planning
**Follow-up:** Phase 2 (pinning) gets its own spec — see "Deferred" below.

## Problem

The ComfyUI server is started by hand: RDP to the farm worker and run

```
"D:\ComfyUI\python_embeded\python.exe" "L:\...\python\comfyui\server.py"
```

Nothing in Luma Tools starts, stops, or restarts it. The app only *reads* the
heartbeat that `server.py` writes every ~20s to
`<network_output_path>/_server_status/heartbeat_<hostname>.json`.

The status the app shows is also weaker than it looks. `comfyui/tab.py`
globs every heartbeat file and collapses them into a single "best" status, so
**any** server anywhere reports "online". With one worker that is harmless.
With several it is misleading: `runner.py` connects to `localhost:8188`, so a
generation job only works on a worker running its own server, and the banner
can read green while the job lands on a worker that has none.

## Scope

**Phase 1 (this spec):** start / stop / restart a server on a chosen worker,
and replace the collapsed status with honest per-worker status.

**Phase 2 (separate spec):** pin ComfyUI generation jobs to workers that have a
live server, so partial coverage stops being a failure mode.

Phase 1 is useful alone — it replaces the RDP workflow — and touches nothing
that already works. Phase 2 modifies `submit_comfyui_to_deadline`, the path all
real work goes through, so it is kept separate to keep any regression there
unambiguous.

Out of scope entirely: auto-start on submit, idle auto-shutdown, one-click
"start servers on the whole group", load balancing across servers.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Control style | Manual Start / Stop / Restart | Replaces the RDP workflow directly; no surprise farm usage. |
| Job lifetime | Manual stop, plus a Deadline task timeout | A forgotten server otherwise holds a GPU box indefinitely. Deadline enforces the cap, so `server.py` needs no changes. |
| Max lifetime | 8 hours, settable, `0` = no cap | Survives a working day; releases the worker if forgotten on a Friday. |
| Already running | Start disabled, Restart offered | Makes a second server on port 8188 impossible by construction. |
| Fleet strategy | Servers on chosen workers; jobs pinned to them (Phase 2) | One warm server serves the queue; the rest of the group stays free for renders. |
| Which code tree | The tree that submitted the job | Matches the manual workflow, and is the only way to test server changes. **Hazard:** a dev submit puts dev `server.py` on the shared worker, and other users' jobs then run against it. Mitigated by showing the tree in the status tooltip and the Deadline job comment. Revisit if more people start servers. |

## Architecture

### 1. `python/comfyui/server_status.py` (new)

Pure functions over the heartbeat directory — no Qt, no Deadline — so the
status logic is testable, which the current inline glob is not.

```python
HEARTBEAT_DIRNAME = "_server_status"

def read_server_heartbeats(network_path: str, stale_seconds: int = 60) -> Dict[str, dict]
def online_workers(heartbeats: Dict[str, dict]) -> List[str]
```

`read_server_heartbeats` returns one entry per heartbeat file, keyed by
lower-cased hostname:

```python
{
  "ls-ws-sim003": {
      "hostname": "ls-ws-sim003",
      "status": "online",          # as written by server.py
      "uptime_seconds": 4210,
      "jobs_completed": 7,
      "age_seconds": 12.4,
      "stale": False,              # age_seconds > stale_seconds
  }
}
```

Stale entries are **returned, not dropped**, so the UI can say "last seen 4
minutes ago" instead of a server silently vanishing. `online_workers` filters
to `status == "online" and not stale`.

Malformed or unparseable files are skipped with a debug log, matching the
current behaviour.

### 2. `python/deadline/server_job.py` (new)

Mirrors `deadline/path_check.py`. No farm script copying is needed:
`server.py` adds its parent directory to `sys.path` itself
(`comfyui/server.py:26-30`), and `L:` is mapped on the workers — the Deadline
task log shows `Skipping L: because it is already mapped`.

```python
def list_group_workers(group: str) -> List[str]
def build_server_job_info(worker, pool, group, priority, max_hours) -> str
def build_server_plugin_info(python_exe, server_script, comfyui_path, mode, python_path, port) -> str
def submit_server_job(worker, ...) -> Optional[str]
def find_server_jobs(username: str) -> Dict[str, str]   # worker -> job_id
def stop_server_job(job_id: str) -> Tuple[bool, str]
```

`job_info`:

```
Plugin=CommandLine
Name=LUMA TOOLS SERVER - <worker>
Comment=Started from <submitting tree path>
Department=<DEADLINE_DEPARTMENT>
Pool=<pool>
Group=<group>
Priority=<priority>
Frames=0
ChunkSize=1
MachineLimit=1
Whitelist=<worker>
TaskTimeoutSeconds=<max_hours * 3600>     # line omitted entirely when max_hours == 0
OnTaskTimeout=Complete
OnJobComplete=Delete
```

`Whitelist` is what makes "start a server on *this* worker" deterministic
rather than "wherever Deadline feels like".

`plugin_info`:

```
Executable=<resolved ComfyUI python>
Arguments="<.../python/comfyui/server.py>" --comfyui-path "<path>" --port <port> --mode <mode> [--python-path "<p>"] [--lowvram|--highvram] [--disable-smart-memory] [--fast]
StartupDirectory=<directory of server.py>
```

Flags come from the existing global settings, using the same resolution
`server.py` already applies to its own defaults. All paths pass through
`normalize_path()`.

Pool, group and priority resolve through `resolve_comfyui_targeting()` so the
server lands where ComfyUI work lands.

`find_server_jobs` queries the user's Active/Pending jobs and parses the worker
back out of `Name`, giving the UI a `{worker: job_id}` map without any extra
state file.

### 3. `python/core/config.py`

```python
DEADLINE_JOB_NAME_PREFIX_SERVER = "LUMA TOOLS SERVER - "
```

### 4. `python/deadline/poller.py`

`is_recoverable_luma_job()` must exclude the server prefix as it already
excludes the diagnostic prefix. **This is not optional:** a server job carrying
the plain `LUMA TOOLS - ` prefix would be adopted by ComfyUI crash recovery on
every app launch and reported as a running generation job — exactly the bug the
farm path check hit.

### 5. Settings

```python
"comfyui_server_max_hours": SettingDef(
    "comfyui_server_max_hours", 8, "global", _validate_server_max_hours
),
```

Validator clamps to 0–168 (0 = no cap). Exposed as a spin box in the ComfyUI
section of Settings, beside the pool/group fields.

### 6. UI — ComfyUI tab

The existing `serverStatusBanner` frame gains:

- A per-worker status line: `Servers: 1 of 3 online — ls-ws-sim003`, with the
  full per-worker detail (uptime, jobs completed, age, submitting tree) in the
  tooltip.
- **Start**, **Stop**, **Restart** buttons.
- A worker selector, shown only when the group has more than one worker, built
  with the existing `OptionButtonManager` pattern.

Button state is driven by the heartbeat data the banner already polls:

| Heartbeat for the selected worker | Start | Stop | Restart |
|---|---|---|---|
| online, job found | disabled | enabled | enabled |
| online, no matching job (started by hand) | disabled | disabled + explanation | disabled |
| offline / stale | enabled | disabled | disabled |
| start submitted, no heartbeat yet | disabled | enabled | disabled |

While a start or stop is in flight the poll interval drops from 30s to 5s and
reverts once the state settles or the wait times out (5 minutes).

Stop asks for confirmation — it kills a warm server with models loaded,
possibly out from under someone else's running job.

All Deadline calls and heartbeat reads run through `start_worker`; neither may
touch the GUI thread.

## Data flow

**Start:** resolve worker → `submit_server_job` → status "Server job queued on
`<worker>`…" → fast-poll heartbeats → online, revert to 30s.

**Stop:** confirm → `find_server_jobs` → `stop_server_job` → fast-poll until the
heartbeat goes stale → offline.

**Restart:** Stop, wait for stale, then Start. If the stop never takes effect
within the timeout, report it and leave Start enabled rather than stacking a
second server.

## Error handling

| Situation | Behaviour |
|---|---|
| `DEADLINE_PATH` unset | Controls disabled, tooltip explains why |
| `comfyui_path` blank | Start refused inline, suggests Verify on Farm |
| Submit returns no job id | Inline error, controls re-enabled |
| Heartbeat never appears within 5 min | "Server job submitted but no heartbeat yet — check Deadline"; Stop stays enabled so the job can be cleared |
| Server job fails on the farm | Surfaced from the job status poll, suggests Verify on Farm |
| Heartbeat online, no matching job | Stop disabled: "a server is running on `<worker>` but was not started from here" |
| `GetSlaveNamesInGroup` fails or returns nothing | Fall back to the hostnames seen in heartbeats; if none, disable the controls with an explanation |

Deadline worker names and hostnames match in this studio (`ls-ws-sim003`).
Matching is case-insensitive, and a heartbeat whose host is not in the group is
still displayed rather than hidden — an unexpected server is exactly what an
operator needs to see.

## Testing

`tests/test_server_control.py`:

- `read_server_heartbeats` over fixture files: fresh, stale, malformed,
  missing directory, several hosts at once
- `online_workers` filtering
- `build_server_job_info`: whitelist present, timeout present, timeout line
  absent when `max_hours == 0`, server prefix used
- `build_server_plugin_info`: forward slashes throughout, flags derived from
  settings, `--python-path` only in standalone mode
- Round-trip: `find_server_jobs` parses back the worker that
  `build_server_job_info` wrote
- `is_recoverable_luma_job()` rejects the server prefix and still accepts
  `LUMA TOOLS - my_render`

Then live farm verification: start, confirm the heartbeat goes online and the
banner updates, stop, confirm it goes stale.

## Files touched

| File | Change |
|---|---|
| `python/comfyui/server_status.py` | **New** — heartbeat parsing |
| `python/deadline/server_job.py` | **New** — submit / find / stop |
| `python/core/config.py` | Server job name prefix |
| `python/core/settings_manager.py` | `comfyui_server_max_hours` |
| `python/deadline/poller.py` | Exclude the server prefix from recovery |
| `python/ui/tabs/comfyui/tab.py` | Controls, per-worker status, fast-poll |
| `resources/ui/tabs/comfyui.ui` | Buttons and status widgets |
| `resources/ui/tabs/settings.ui` | Max-lifetime spin box |
| `resources/ui/tabs/_compiled/ui_*.py` | Regenerated via `pyside6-uic` |
| `tests/test_server_control.py` | **New** |

## Deferred — Phase 2 (pinning)

`submit_comfyui_to_deadline` gains `Whitelist=<workers with fresh heartbeats>`
behind a `comfyui_pin_jobs_to_servers` global setting (default on), so one warm
server can serve the whole queue while the rest of the group stays free. With
no server online, no whitelist is written — today's behaviour and the existing
`--server-not-found` handling stand — and the UI warns before submitting.

This gets its own spec, plan and live verification.
