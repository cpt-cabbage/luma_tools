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
import traceback

# Deadline runs this as `python.exe -u <this file> <args>`, so sys.path[0] is
# already this file's directory and the comfyui_* copies beside it import
# normally. They must all be present though - see FARM_SCRIPTS in
# deadline/path_check.py.
try:
    from comfyui_utils import resolve_comfyui_paths
except ImportError:  # workstation / test import, where the package exists
    from comfyui.utils import resolve_comfyui_paths

RESULT_SCHEMA = 1

# The resolved interpreter lives on a worker that may be paging in a model.
# Sixty seconds is generous for `python -c print(version)` without letting a
# wedged process hold the whole check open.
_PROBE_TIMEOUT_S = 60

# Breadcrumb log written beside the result file, in the job's own directory.
# The Deadline repository here is behind a connection server, so the
# workstation cannot read task logs - without this, a farm-side failure that
# still manages to reach main() is invisible.
#
# It deliberately does NOT log next to this script: on the workstation that is
# the source tree, and running the tests would litter python/comfyui/.
LOG_FILENAME = "check_log.txt"

_LOG_DIR = None


def _log(message):
    """Append a breadcrumb to the job directory. No-op until it is known."""
    if not _LOG_DIR:
        return
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(_LOG_DIR, LOG_FILENAME), "a", encoding="utf-8") as handle:
            handle.write("%s %s\n" % (stamp, message))
    except Exception:  # a broken log must never break the check
        pass


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


def _payload(checks, comfyui_mode="", version=None):
    """Wrap a list of checks in the envelope the workstation reads."""
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


def crash_result(exc):
    """Turn an unexpected crash into an answer the workstation can display.

    Without this the script exits non-zero with no file written, and the
    Settings tab has nothing to show but a three-minute timeout - the least
    useful possible report of a bug in this script.
    """
    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    return _payload([_check("script_error", "Check script", False, detail)])


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

    return _payload(checks, comfyui_mode, version)


def main(argv=None):
    """Run the checks and write the result file. Returns a process exit code."""
    global _LOG_DIR

    parser = argparse.ArgumentParser(
        description="Verify the ComfyUI installation on this farm worker")
    parser.add_argument("--comfyui-path", required=True)
    parser.add_argument("--comfyui-mode", default="embedded")
    parser.add_argument("--comfyui-python", default="")
    parser.add_argument("--result-file", required=True)
    args = parser.parse_args(argv)

    result_dir = os.path.dirname(os.path.abspath(args.result_file))
    if os.path.isdir(result_dir):
        _LOG_DIR = result_dir
    _log("started on %s with python %s" % (socket.gethostname(), sys.version.split()[0]))

    try:
        result = run_checks(
            args.comfyui_path,
            args.comfyui_mode,
            args.comfyui_python,
            network_path=os.path.dirname(args.result_file),
        )
    except Exception as exc:  # the crash IS the answer - report it, don't hide it
        traceback.print_exc()
        result = crash_result(exc)

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
        _log("FAILED to write %s: %s" % (args.result_file, exc))
        sys.stderr.write("Could not write result file %s: %s\n" % (args.result_file, exc))
        return 1

    _log("wrote %s (ok=%s)" % (args.result_file, result["ok"]))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
