"""Functional verification that the gallery layout guards are correct.

Run with tests/benchmarks/run_gallery_bench.ps1 -Script verify_gallery_layout.py

Checks, after a normal grid population:
  * every widget has a real, distinct geometry (layout actually ran)
  * the container grew to the expected multi-row height
  * the scroll area has a usable range
  * visible thumbnails loaded, off-screen ones did not (lazy loading intact)
  * placeholder pixmaps are shared (same cacheKey) but real thumbnails are not
  * filter (recycle), reorder and stacked rebuild still position widgets
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench_gallery import build_dataset, make_tab, pump, pump_until, population_done  # noqa: E402


def main():
    import logging
    logging.basicConfig(level=logging.ERROR)
    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    workdir = tempfile.mkdtemp(prefix="luma_verify_")
    data_dir = os.path.join(workdir, "items")
    build_dataset(data_dir, 200)

    win = QMainWindow()
    win.resize(1400, 900)
    tab, ui = make_tab(app, win, data_dir)
    win.setCentralWidget(ui)
    win.show()
    pump(app, 0.5)

    from ui.tabs.gallery_loader import GalleryLoader
    items = GalleryLoader.scan_directory(data_dir, load_metadata=True)
    items = tab._manager.sort_items(items, "date_desc")

    failures = []

    def check(name, cond, detail=""):
        print(f"{'PASS' if cond else 'FAIL'}  {name} {detail}")
        if not cond:
            failures.append(name)

    # --- grid population ---
    tab._manager.display_items(items, view_mode="grid", incremental=False)
    pump_until(app, lambda: population_done(tab), timeout=120)
    pump(app, 3.0)

    widgets = list(tab.get_widget_cache_copy().values())
    check("all widgets created", len(widgets) == len(items), f"({len(widgets)}/{len(items)})")

    geoms = [w.geometry() for w in widgets]
    zero = [g for g in geoms if g.width() == 0 or g.height() == 0]
    check("no zero-size widgets", not zero, f"({len(zero)} zero)")

    positions = {(g.x(), g.y()) for g in geoms}
    check("distinct positions", len(positions) == len(widgets),
          f"({len(positions)} unique / {len(widgets)})")

    check("layout is enabled again", tab._flow_layout.isEnabled())
    check("container updates enabled", tab.ui.galleryThumbnailContainer.updatesEnabled())

    max_y = max(g.bottom() for g in geoms)
    check("container tall enough for many rows", max_y > 1000, f"(max_y={max_y})")

    sb = tab.ui.galleryScrollArea.verticalScrollBar()
    check("scrollbar has range", sb.maximum() > 0, f"(max={sb.maximum()})")

    loaded = [w for w in widgets if getattr(w, "_thumbnail_loaded", False)]
    check("some thumbnails loaded", len(loaded) > 0, f"({len(loaded)} loaded)")
    check("lazy loading still lazy", len(loaded) < len(widgets),
          f"({len(loaded)}/{len(widgets)})")

    # --- placeholder sharing ---
    unloaded = [w for w in widgets if not getattr(w, "_thumbnail_loaded", False)]
    if len(unloaded) >= 2:
        keys = {w.thumbnail_label.pixmap().cacheKey() for w in unloaded[:20]}
        check("placeholder pixmaps shared", len(keys) == 1, f"({len(keys)} distinct)")
    if len(loaded) >= 2:
        keys = {w.thumbnail_label.pixmap().cacheKey() for w in loaded[:10]}
        check("real thumbnails not shared", len(keys) > 1, f"({len(keys)} distinct)")

    # --- filter (widget recycling) ---
    subset = items[:80]
    tab._manager.display_items(subset, view_mode="grid", incremental=False)
    pump(app, 1.0)
    visible = [w for w in tab.get_widget_cache_copy().values() if w.isVisible()]
    check("filter shows only subset", len(visible) == len(subset),
          f"({len(visible)}/{len(subset)})")

    # --- restore + reorder ---
    tab._manager.display_items(items, view_mode="grid", incremental=False)
    pump(app, 1.0)
    tab._manager.reorder_widgets(list(reversed(items)))
    pump(app, 1.0)
    first = tab.get_cached_widget(items[-1]["path"])
    check("reorder puts last item first", first is not None and first.geometry().y() < 60,
          f"(y={first.geometry().y() if first else 'n/a'})")

    # --- stacked rebuild ---
    tab._manager.display_items(items, view_mode="stacked", incremental=False)
    pump(app, 2.0)
    stacks = tab._manager._stack_widgets
    check("stacks created", len(stacks) == len(items) // 10, f"({len(stacks)} stacks)")
    stack_geoms = [s.geometry() for s in stacks.values()]
    check("stacks positioned", all(g.width() > 0 for g in stack_geoms))
    check("stack positions distinct",
          len({(g.x(), g.y()) for g in stack_geoms}) == len(stack_geoms))

    # --- stacked: expand a stack, rebuild, expect it restored ---
    target_id = sorted(stacks.keys())[0]
    stacks[target_id].expand()
    pump(app, 1.5)
    check("stack expands", stacks[target_id].is_expanded())
    check("tab tracks expanded stack", tab._expanded_stack_id == target_id)
    tab._manager.display_items(items, view_mode="stacked", incremental=False)
    pump(app, 2.5)
    restored = tab._manager._stack_widgets.get(target_id)
    check("expanded stack restored after rebuild",
          restored is not None and restored.is_expanded())
    restored.collapse(animated=False)
    pump(app, 0.5)

    # --- stacked: incremental add ---
    extra = [dict(it, path=it["path"] + ".copy.png") for it in items[:5]]
    tab._manager.display_items(items, view_mode="stacked", incremental=False)
    pump(app, 1.5)
    before_stacks = len(tab._manager._stack_widgets)
    tab._manager.display_items(items[:-10], view_mode="stacked", incremental=True)
    pump(app, 1.5)
    check("incremental stacked update runs",
          len(tab._manager._stack_widgets) <= before_stacks,
          f"({before_stacks} -> {len(tab._manager._stack_widgets)})")
    stack_geoms = [s.geometry() for s in tab._manager._stack_widgets.values()]
    check("stacks still positioned after incremental",
          all(g.width() > 0 and g.height() > 0 for g in stack_geoms))

    # --- back to grid, then incremental add ---
    tab._manager.display_items(items, view_mode="grid", incremental=False)
    pump_until(app, lambda: population_done(tab), timeout=120)
    pump(app, 1.5)
    check("grid restored after stacked",
          len(tab.get_widget_cache_copy()) == len(items),
          f"({len(tab.get_widget_cache_copy())})")

    win.close()
    pump(app, 0.3)
    shutil.rmtree(workdir, ignore_errors=True)

    print("\n" + ("ALL CHECKS PASSED" if not failures else f"FAILURES: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
