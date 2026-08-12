"""Gallery scalability benchmark.

Populates a real GalleryTab with a synthetic item set of N placeholder images
and measures population, paint, scroll and filter/stacking-switch timings.

Never touches the network share: all data lives in a temp dir created and
removed by this script.

Usage:
    python bench_gallery.py --counts 500,1000,2500,5000 --view grid
"""

import argparse
import ctypes
import gc
import json
import os
import shutil
import statistics
import sys
import tempfile
import time

# --- process memory (no psutil in the venv) --------------------------------


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_psapi = ctypes.WinDLL("psapi.dll")
_psapi.GetProcessMemoryInfo.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
    ctypes.c_ulong,
]
_psapi.GetProcessMemoryInfo.restype = ctypes.c_int
_kernel32 = ctypes.WinDLL("kernel32.dll")
_kernel32.GetCurrentProcess.restype = ctypes.c_void_p


def working_set_mb():
    counters = _PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
    ok = _psapi.GetProcessMemoryInfo(
        _kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    )
    if not ok:
        return float("nan")
    return counters.WorkingSetSize / (1024 * 1024)


# --- synthetic gallery data ------------------------------------------------

JOB_SIZE = 10  # items per job prefix -> N/10 stacks in stacked view


def build_dataset(root, count, job_size=None):
    """Write `count` small PNGs + a comfyui_gallery_metadata.json into root."""
    global JOB_SIZE
    if job_size:
        JOB_SIZE = job_size
    from PIL import Image

    os.makedirs(root, exist_ok=True)

    # A handful of distinct source images, copied to keep generation cheap.
    templates = []
    for i in range(8):
        img = Image.new("RGB", (512, 512), (30 + i * 25, 90, 200 - i * 20))
        tpl = os.path.join(root, f"_tpl_{i}.png")
        img.save(tpl)
        templates.append(tpl)

    metadata = {}
    for i in range(count):
        job = i // JOB_SIZE
        prefix = f"LumaRND_sh0010_luma_tools_bench{job:04d}"
        name = f"{prefix}_gen01_{i:05d}_.png"
        shutil.copyfile(templates[i % len(templates)], os.path.join(root, name))
        key = f"_prefix_{prefix}"
        if key not in metadata:
            metadata[key] = {
                "is_output": True,
                "job_prefix": prefix,
                "source_images": [],
                "workflow_preset": "bench_workflow",
                "timestamp": time.time(),
            }

    for tpl in templates:
        os.remove(tpl)

    with open(os.path.join(root, "comfyui_gallery_metadata.json"), "w") as fh:
        json.dump(metadata, fh)


# --- Qt harness ------------------------------------------------------------


def make_tab(app, main_window, output_dir):
    """Build a fully initialized GalleryTab pointed at output_dir."""
    from ui.tabs.gallery_tab import GalleryTab
    from ui.tabs.gallery.ui_manager import UIManager
    from ui.tabs.gallery.refresh_controller import RefreshController
    from core.state_manager import app_state

    # Keep the harness off the network: no user discovery, no file watcher,
    # no polling timers.
    UIManager.populate_user_selector = lambda self: None
    RefreshController.start_watcher = lambda self, path: None
    RefreshController.start_polling = lambda self, *a, **k: None

    app_state.user = "bench.user"

    tab = GalleryTab(main_window, app_state)
    ui = tab.load_ui(main_window)
    tab.connect_signals()
    tab._get_network_user_path = lambda username=None: output_dir
    tab.initialize()
    tab._selected_user = "bench.user"
    return tab, ui


class PaintSpy:
    """Counts paint events on a widget and records the last paint time."""

    def __init__(self):
        from PySide6.QtCore import QEvent, QObject

        spy = self

        class _Filter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Paint:
                    spy.count += 1
                    spy.last = time.perf_counter()
                    if spy.first is None:
                        spy.first = spy.last
                return False

        self.count = 0
        self.first = None
        self.last = None
        self._filter = _Filter()

    def attach(self, widget):
        widget.installEventFilter(self._filter)

    def reset(self):
        self.count = 0
        self.first = None
        self.last = None


def pump(app, seconds):
    """Run the event loop for `seconds` wall time."""
    from PySide6.QtCore import QEventLoop

    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents(QEventLoop.AllEvents, 5)


def pump_until(app, predicate, timeout):
    from PySide6.QtCore import QEventLoop

    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        if predicate():
            return time.perf_counter() - start
        app.processEvents(QEventLoop.AllEvents, 5)
    return None


def population_done(tab):
    pending = getattr(tab, "_pending_items", None)
    if not pending:
        return True
    return getattr(tab, "_widget_create_index", 0) >= len(pending)


def run_case(app, count, view_mode, workdir, keep_open=0.0, job_size=None):
    from PySide6.QtWidgets import QMainWindow

    data_dir = os.path.join(workdir, f"items_{count}")
    t = time.perf_counter()
    build_dataset(data_dir, count, job_size)
    gen_time = time.perf_counter() - t

    win = QMainWindow()
    win.resize(1600, 1000)
    tab, ui = make_tab(app, win, data_dir)
    win.setCentralWidget(ui)
    win.show()
    pump(app, 0.5)

    from ui.tabs.gallery_loader import GalleryLoader

    t = time.perf_counter()
    items = GalleryLoader.scan_directory(data_dir, load_metadata=True)
    scan_time = time.perf_counter() - t
    items = tab._manager.sort_items(items, "date_desc")

    spy = PaintSpy()
    spy.attach(tab.ui.galleryThumbnailContainer)

    gc.collect()
    mem_before = working_set_mb()

    # --- population ---
    t0 = time.perf_counter()
    tab._manager.display_items(items, view_mode=view_mode, incremental=False)
    sync_return = time.perf_counter() - t0
    populated = pump_until(app, lambda: population_done(tab), timeout=180)

    # let the deferred lazy-thumbnail pass (+150 ms) run and settle
    pump(app, 3.0)
    # first_paint must be read AFTER the settle: the grid path keeps
    # setUpdatesEnabled(False) for the whole batched-creation run, so the
    # first repaint only lands once every widget exists.
    first_paint = (spy.first - t0) if spy.first else None
    gc.collect()
    mem_after = working_set_mb()

    # --- scroll responsiveness ---
    sb = tab.ui.galleryScrollArea.verticalScrollBar()
    step = max(1, tab.ui.galleryScrollArea.viewport().height() // 2)
    frames = []
    sb.setValue(0)
    pump(app, 0.3)
    pos = 0
    for _ in range(30):
        pos = min(sb.maximum(), pos + step)
        spy.reset()
        t = time.perf_counter()
        sb.setValue(pos)
        # one "frame": drive events until the grid repaints (or 500 ms cap)
        pump_until(app, lambda: spy.count > 0, timeout=0.5)
        frames.append((time.perf_counter() - t) * 1000.0)
        if pos >= sb.maximum():
            pos = 0
            sb.setValue(0)
            pump(app, 0.1)

    # --- filter change (widget recycling path: show ~40% of items) ---
    subset = items[: max(1, int(len(items) * 0.4))]
    t = time.perf_counter()
    tab._manager.display_items(subset, view_mode=view_mode, incremental=False)
    pump_until(app, lambda: population_done(tab), timeout=180)
    filter_time = time.perf_counter() - t
    pump(app, 0.5)

    # --- restore full set, then switch stacking/view mode ---
    tab._manager.display_items(items, view_mode=view_mode, incremental=False)
    pump_until(app, lambda: population_done(tab), timeout=180)
    pump(app, 0.5)

    other_mode = "stacked" if view_mode != "stacked" else "grid"
    t = time.perf_counter()
    tab._manager.display_items(items, view_mode=other_mode, incremental=False)
    pump_until(app, lambda: population_done(tab), timeout=180)
    mode_switch = time.perf_counter() - t
    pump(app, 0.5)

    if keep_open:
        pump(app, keep_open)

    result = {
        "count": count,
        "view": view_mode,
        "gen_s": gen_time,
        "scan_s": scan_time,
        "sync_return_s": sync_return,
        "first_paint_s": first_paint,
        "populated_s": populated,
        "mem_before_mb": mem_before,
        "mem_after_mb": mem_after,
        "mem_delta_mb": mem_after - mem_before,
        "scroll_median_ms": statistics.median(frames),
        "scroll_p95_ms": sorted(frames)[int(len(frames) * 0.95) - 1],
        "scroll_max_ms": max(frames),
        "filter_s": filter_time,
        "mode_switch_s": mode_switch,
        "mode_switch_to": other_mode,
    }

    win.close()
    tab.ui.galleryThumbnailContainer.deleteLater()
    del tab
    pump(app, 0.5)
    gc.collect()
    shutil.rmtree(data_dir, ignore_errors=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--counts", default="500,1000,2500,5000")
    parser.add_argument("--view", default="grid", choices=["grid", "stacked"])
    parser.add_argument("--keep-open", type=float, default=0.0)
    parser.add_argument("--job-size", type=int, default=JOB_SIZE)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    import logging

    logging.basicConfig(level=logging.ERROR)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    workdir = tempfile.mkdtemp(prefix="luma_gallery_bench_")
    results = []
    try:
        for count in [int(c) for c in args.counts.split(",") if c.strip()]:
            print(f"=== {count} items ({args.view}, job_size={args.job_size}) ===", flush=True)
            res = run_case(app, count, args.view, workdir, args.keep_open, args.job_size)
            results.append(res)
            print(json.dumps(res, indent=2), flush=True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("\n=== SUMMARY ===")
    header = (
        f"{'items':>6} {'scan':>7} {'1stpaint':>9} {'populate':>9} "
        f"{'mem MB':>8} {'scroll med':>11} {'scroll p95':>11} "
        f"{'filter':>8} {'switch':>8}"
    )
    print(header)
    for r in results:
        fp = f"{r['first_paint_s']:.2f}" if r["first_paint_s"] else "n/a"
        pop = f"{r['populated_s']:.2f}" if r["populated_s"] else "TIMEOUT"
        print(
            f"{r['count']:>6} {r['scan_s']:>6.2f}s {fp:>9} {pop:>9} "
            f"{r['mem_delta_mb']:>7.0f} {r['scroll_median_ms']:>10.0f}ms "
            f"{r['scroll_p95_ms']:>10.0f}ms {r['filter_s']:>7.2f}s "
            f"{r['mode_switch_s']:>7.2f}s"
        )

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(results, fh, indent=2)


if __name__ == "__main__":
    main()
