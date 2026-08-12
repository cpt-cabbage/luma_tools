"""Screenshot harness for the Luma Tools UI.

Launches the real application, drives it into a set of UI states and grabs a
PNG of each one. Used to capture before/after sets around UI changes.

Usage
-----
    python scripts/ui_shots.py <output_dir> [scenario[,scenario...]]

With no scenario list every scenario runs. Scenario names are printed at
startup. Run it through ``_shoot_ui.ps1`` so PYTHONPATH is set.

Step vocabulary
---------------
    {"tab": "gallery"}          switch to a tab by restrict_key
    {"wait": 1200}              dwell, milliseconds
    {"shot": "name"}            grab now -> <output_dir>/name.png
    {"click": "regex"}          click the first visible button whose text matches
    {"click_obj": "ObjName"}    click a widget by objectName
    {"dclick_thumb": 0}         double-click the Nth gallery thumbnail
    {"rclick_thumb": 0}         right-click the Nth gallery thumbnail
    {"scroll": 0.5}             scroll the tab's tallest scroll area to a fraction
    {"key": "Escape"}           send a key to the focused widget
    {"close": 1}                dismiss modal / overlay / extra window
    {"zoo": 1}                  build and show the widget zoo

Targets that cannot be found are logged with a '!!' prefix rather than
silently skipped, so gaps in coverage stay visible.
"""
import os
import re
import sys
import traceback

if len(sys.argv) < 2:
    print(__doc__)
    raise SystemExit(2)

OUT_DIR = sys.argv[1]
ONLY = [s for s in (sys.argv[2].split(",") if len(sys.argv) > 2 else []) if s]
os.makedirs(OUT_DIR, exist_ok=True)

# The shot context must be set before the app module is imported, because
# app_state.initialize_from_args() runs at import time.
# Order: jobname, shot, task, shotpath, user, output_subdirectory
SHOT_CONTEXT = [
    "Changan", "sh0040", "lighting",
    r"W:\Changan\shots\sh0040\work", "christophe.leyder", "combined",
]
sys.argv = ["luma_tools.py"] + SHOT_CONTEXT

import core.luma_tools as lt  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

WINDOW_SIZE = (1700, 1020)


_LOG_PATH = os.path.join(OUT_DIR, "_harness.log")


def log(msg):
    """The app redirects stdout into its own tee'd logger, so also write our
    own sink — otherwise harness output is swallowed and failures look silent."""
    line = f"[shots] {msg}"
    print(line, flush=True)
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------- lookup
def main_window():
    return lt._main_window


def current_tab():
    return main_window().tab_widget.currentWidget()


def extra_windows():
    """Visible top-level widgets that are not the main window."""
    mw = main_window()
    out = []
    for w in QtWidgets.QApplication.topLevelWidgets():
        try:
            if w is mw or not w.isVisible():
                continue
            if w.width() < 80 or w.height() < 40:
                continue
            out.append(w)
        except RuntimeError:      # C++ side already deleted
            continue
    return out


def live_overlays():
    """Visible in-tab overlays — anything exposing hide_overlay()."""
    out = []
    for w in QtWidgets.QApplication.allWidgets():
        try:
            if not w.isVisible() or not hasattr(w, "hide_overlay"):
                continue
            if w.width() < 200 or w.height() < 150:
                continue
            out.append(w)
        except RuntimeError:
            continue
    return out


def grab_target():
    # Popups (QMenu, combo drop-downs) are top-level but transient — they must
    # be checked first or they are gone by the time we look at anything else.
    popup = QtWidgets.QApplication.activePopupWidget()
    if popup is not None and popup.isVisible():
        return popup, "popup"
    modal = QtWidgets.QApplication.activeModalWidget()
    if modal is not None and modal.isVisible():
        return modal, "modal"
    extras = extra_windows()
    if extras:
        return extras[-1], "window"
    # In-tab overlays are children of the main window, so grabbing the window
    # captures them in place — which is how the user actually sees them.
    return main_window(), "main"


def search_roots():
    roots = []
    for getter in (QtWidgets.QApplication.activePopupWidget,
                   QtWidgets.QApplication.activeModalWidget):
        w = getter()
        if w is not None:
            roots.append(w)
    roots.extend(reversed(extra_windows()))
    roots.extend(live_overlays())
    mw = main_window()
    if mw is not None:
        roots.append(mw)
    return roots


def find_by_class(class_name, index=0):
    """Nth visible widget whose class name matches, in layout order."""
    found = []
    for root in search_roots():
        for w in root.findChildren(QtWidgets.QWidget):
            try:
                if type(w).__name__ == class_name and w.isVisible() and w.width() > 40:
                    found.append(w)
            except RuntimeError:
                continue
        if found:
            break
    found.sort(key=lambda w: (w.mapToGlobal(QtCore.QPoint(0, 0)).y(),
                              w.mapToGlobal(QtCore.QPoint(0, 0)).x()))
    return found[index] if index < len(found) else None


def find_subtab(text):
    """(QTabWidget, index) for a nested tab whose label matches."""
    rx = re.compile(text, re.I)
    for tw in current_tab().findChildren(QtWidgets.QTabWidget):
        if not tw.isVisible():
            continue
        for i in range(tw.count()):
            if rx.search(tw.tabText(i) or ""):
                return tw, i
    return None, -1


def find_button(pattern):
    rx = re.compile(pattern, re.I)
    for root in search_roots():
        for b in root.findChildren(QtWidgets.QAbstractButton):
            try:
                if b.isVisible() and b.isEnabled() and rx.search(b.text() or ""):
                    return b
            except RuntimeError:
                continue
    return None


def find_by_objname(name):
    for root in search_roots():
        try:
            w = root.findChild(QtWidgets.QWidget, name)
        except RuntimeError:
            continue
        if w is not None and w.isVisible():
            return w
    return None


def thumbnails():
    tab = current_tab()
    found = []
    for w in tab.findChildren(QtWidgets.QWidget):
        try:
            if "Thumbnail" in type(w).__name__ and w.isVisible() and w.width() > 60:
                found.append(w)
        except RuntimeError:
            continue
    found.sort(key=lambda w: (w.mapTo(tab, QtCore.QPoint(0, 0)).y(),
                              w.mapTo(tab, QtCore.QPoint(0, 0)).x()))
    return found


# --------------------------------------------------------------------- actions
def _mouse(widget, etypes, button=QtCore.Qt.LeftButton):
    pos = widget.rect().center()
    glob = widget.mapToGlobal(pos)
    for etype in etypes:
        ev = QtGui.QMouseEvent(etype, QtCore.QPointF(pos), QtCore.QPointF(glob),
                               button, button, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(widget, ev)


def click(widget):
    """Click, deferred through the event loop.

    A synchronous widget.click() runs the handler inline, so a handler that
    calls QDialog.exec() blocks this function until the dialog is dismissed —
    which stalls the whole step chain and forces a human to close it by hand.
    Posting the click means exec() spins its nested loop while our timers keep
    firing, and close_top()/the watchdog can dismiss it.
    """
    def _do():
        try:
            widget.setFocus()
            if isinstance(widget, QtWidgets.QAbstractButton):
                widget.click()
            else:
                _mouse(widget, [QtCore.QEvent.MouseButtonPress,
                                QtCore.QEvent.MouseButtonRelease])
        except RuntimeError:
            pass
    QtCore.QTimer.singleShot(0, _do)


def double_click(widget):
    _mouse(widget, [QtCore.QEvent.MouseButtonPress,
                    QtCore.QEvent.MouseButtonRelease,
                    QtCore.QEvent.MouseButtonDblClick,
                    QtCore.QEvent.MouseButtonRelease])


def right_click(widget):
    """Right-click, deferred — contextMenuEvent handlers call QMenu.exec(),
    which blocks exactly like QDialog.exec() does. See click()."""
    def _do():
        try:
            _mouse(widget, [QtCore.QEvent.MouseButtonPress,
                            QtCore.QEvent.MouseButtonRelease],
                   button=QtCore.Qt.RightButton)
            ev = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse,
                                         widget.rect().center(),
                                         widget.mapToGlobal(widget.rect().center()))
            QtWidgets.QApplication.sendEvent(widget, ev)
        except RuntimeError:
            pass
    QtCore.QTimer.singleShot(0, _do)


def send_key(name):
    key = getattr(QtCore.Qt, f"Key_{name}")
    target = QtWidgets.QApplication.focusWidget() or current_tab()
    for etype in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
        QtWidgets.QApplication.sendEvent(
            target, QtGui.QKeyEvent(etype, key, QtCore.Qt.NoModifier))


def scroll_to(fraction):
    areas = [a for a in current_tab().findChildren(QtWidgets.QScrollArea)
             if a.isVisible()]
    if not areas:
        log("!! no scroll area in this tab")
        return
    bar = max(areas, key=lambda a: a.height()).verticalScrollBar()
    bar.setValue(int(bar.maximum() * fraction))


def close_top():
    """Dismiss whatever is on top: popup, modal, in-tab overlay, or window."""
    popup = QtWidgets.QApplication.activePopupWidget()
    if popup is not None:
        # QMenu.exec() runs a nested loop; close() is what unwinds it. Left
        # open, a stale menu keeps stealing activePopupWidget from later steps.
        popup.close()
        return "popup"
    modal = QtWidgets.QApplication.activeModalWidget()
    if modal is not None:
        modal.close()
        return "modal"
    overlays = live_overlays()
    if overlays:
        for ov in overlays:
            try:
                ov.hide_overlay()
            except Exception as e:
                log(f"!! hide_overlay failed on {type(ov).__name__}: {e}")
                ov.hide()
        return "overlay"
    extras = extra_windows()
    if extras:
        extras[-1].close()
        return "window"
    send_key("Escape")
    return "escape"


_watch = {}
_SEEN_PROP = "_ui_ayon_first_seen"


def watchdog():
    """Force-close anything modal that has been open too long.

    The harness must never leave a dialog sitting on the user's screen waiting
    to be dismissed by hand.

    The first-seen timestamp is stored as a Qt dynamic property on the widget
    rather than in a dict keyed by id(). CPython reuses freed addresses, so an
    id()-keyed table hands a brand-new QMenu the timestamp of a dead one and
    the watchdog kills it the instant it opens.
    """
    import time
    now = time.time()
    for w in ([QtWidgets.QApplication.activeModalWidget()] + extra_windows()):
        if w is None:
            continue
        # Only dialogs can strand the user. Menus and other popups close on the
        # next click anywhere, and the harness dismisses them explicitly — the
        # watchdog racing them just destroys states we are trying to capture.
        if not isinstance(w, QtWidgets.QDialog):
            continue
        try:
            first = w.property(_SEEN_PROP)
            if first is None:
                w.setProperty(_SEEN_PROP, now)
                continue
            if now - float(first) > 20:
                log(f"!! watchdog closing stuck {type(w).__name__}")
                w.close()
        except (RuntimeError, TypeError, ValueError):
            continue


def close_everything():
    """Tear down any leftover windows so the app can actually quit."""
    for _ in range(6):
        if (QtWidgets.QApplication.activeModalWidget() is None
                and not extra_windows() and not live_overlays()):
            return
        close_top()
        QtWidgets.QApplication.processEvents()


def do_shot_popup(name, timeout_ms=3000):
    """Grab a transient popup, polling synchronously until it appears.

    Context menus are shown from inside an event handler, so they are not
    necessarily up when the step runs. This must block the step chain — an
    async retry lets the following 'close' step fire first and dismiss the very
    popup we are waiting for.
    """
    import time
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is not None and popup.isVisible():
            do_shot(name)
            return
        QtWidgets.QApplication.processEvents(
            QtCore.QEventLoop.ExcludeUserInputEvents, 50)
    log(f"!! no popup appeared for {name}")


def do_shot(name):
    target, kind = grab_target()
    pix = target.grab()
    path = os.path.join(OUT_DIR, f"{name}.png")
    pix.save(path)
    log(f"shot {name}  <- {kind}:{type(target).__name__}  {pix.width()}x{pix.height()}")


# ------------------------------------------------------------------ widget zoo
_zoo = {"w": None}


def build_zoo():
    """Every styled control type on one page.

    After qdarkstyle is dropped, anything we forgot to write a selector for
    falls back to native Windows chrome and is obvious here rather than
    lurking in a rarely-opened dialog.
    """
    win = QtWidgets.QWidget(main_window(), QtCore.Qt.Window)
    win.setWindowTitle("Widget Zoo")
    win.resize(1180, 900)
    outer = QtWidgets.QVBoxLayout(win)
    outer.setContentsMargins(16, 16, 16, 16)
    outer.setSpacing(12)

    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    host = QtWidgets.QWidget()
    grid = QtWidgets.QGridLayout(host)
    grid.setContentsMargins(12, 12, 12, 12)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(14)
    scroll.setWidget(host)
    outer.addWidget(scroll)

    col = {"r": 0}

    def section(title, widgets):
        box = QtWidgets.QGroupBox(title)
        lay = QtWidgets.QVBoxLayout(box)
        lay.setSpacing(8)
        for w in widgets:
            lay.addWidget(w)
        grid.addWidget(box, col["r"] // 2, col["r"] % 2)
        col["r"] += 1

    # buttons
    b_norm = QtWidgets.QPushButton("Normal")
    b_dis = QtWidgets.QPushButton("Disabled"); b_dis.setEnabled(False)
    b_def = QtWidgets.QPushButton("Default"); b_def.setDefault(True)
    b_chk = QtWidgets.QPushButton("Checked"); b_chk.setCheckable(True); b_chk.setChecked(True)
    b_flat = QtWidgets.QPushButton("Flat"); b_flat.setFlat(True)
    t_btn = QtWidgets.QToolButton(); t_btn.setText("QToolButton")
    section("QPushButton / QToolButton",
            [b_norm, b_dis, b_def, b_chk, b_flat, t_btn])

    # text entry
    le = QtWidgets.QLineEdit("QLineEdit")
    le_ph = QtWidgets.QLineEdit(); le_ph.setPlaceholderText("placeholder text")
    le_ro = QtWidgets.QLineEdit("read only"); le_ro.setReadOnly(True)
    te = QtWidgets.QTextEdit("QTextEdit"); te.setFixedHeight(60)
    pte = QtWidgets.QPlainTextEdit("QPlainTextEdit"); pte.setFixedHeight(60)
    section("Text entry", [le, le_ph, le_ro, te, pte])

    # numeric / choice
    sb = QtWidgets.QSpinBox(); sb.setValue(42)
    dsb = QtWidgets.QDoubleSpinBox(); dsb.setValue(3.50)
    cb = QtWidgets.QComboBox(); cb.addItems(["QComboBox", "second", "third"])
    cb_ed = QtWidgets.QComboBox(); cb_ed.setEditable(True); cb_ed.addItems(["editable"])
    sl = QtWidgets.QSlider(QtCore.Qt.Horizontal); sl.setValue(60)
    # QDial is deliberately excluded: Qt cannot meaningfully style it through
    # QSS, and the app does not use one. Including it would leave a permanent
    # "unstyled widget" false alarm in every zoo capture.
    section("Numeric / choice", [sb, dsb, cb, cb_ed, sl])

    # toggles
    c_on = QtWidgets.QCheckBox("Checked"); c_on.setChecked(True)
    c_off = QtWidgets.QCheckBox("Unchecked")
    c_tri = QtWidgets.QCheckBox("Partially"); c_tri.setTristate(True)
    c_tri.setCheckState(QtCore.Qt.PartiallyChecked)
    c_dis = QtWidgets.QCheckBox("Disabled"); c_dis.setEnabled(False)
    r_on = QtWidgets.QRadioButton("Radio on"); r_on.setChecked(True)
    r_off = QtWidgets.QRadioButton("Radio off")
    section("Toggles", [c_on, c_off, c_tri, c_dis, r_on, r_off])

    # labels
    labels = []
    for txt in ("Default label", "Secondary", "Muted help text", "Value 128"):
        labels.append(QtWidgets.QLabel(txt))
    mono = QtWidgets.QLabel("W:/LumaRND/sh0010/render/v012")
    mono.setFont(QtGui.QFont("Consolas", 9))
    labels.append(mono)
    section("QLabel", labels)

    # progress / status
    pb = QtWidgets.QProgressBar(); pb.setValue(45)
    pb_ind = QtWidgets.QProgressBar(); pb_ind.setRange(0, 0)
    section("Progress", [pb, pb_ind])

    # item views
    lw = QtWidgets.QListWidget()
    for i in range(4):
        lw.addItem(f"QListWidget item {i}")
    lw.setCurrentRow(1)
    lw.setFixedHeight(110)
    tw = QtWidgets.QTreeWidget(); tw.setHeaderLabels(["Name", "Value"])
    for i in range(3):
        QtWidgets.QTreeWidgetItem(tw, [f"node {i}", str(i * 10)])
    tw.setFixedHeight(110)
    tbl = QtWidgets.QTableWidget(3, 3)
    tbl.setHorizontalHeaderLabels(["A", "B", "C"])
    tbl.setFixedHeight(110)
    section("Item views", [lw, tw, tbl])

    # containers
    inner_tabs = QtWidgets.QTabWidget()
    for n in ("First", "Second", "Third"):
        inner_tabs.addTab(QtWidgets.QLabel(f"  {n} page  "), n)
    inner_tabs.setFixedHeight(110)
    split = QtWidgets.QSplitter()
    split.addWidget(QtWidgets.QLabel("  left  "))
    split.addWidget(QtWidgets.QLabel("  right  "))
    frame = QtWidgets.QFrame()
    frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
    QtWidgets.QVBoxLayout(frame).addWidget(QtWidgets.QLabel("QFrame StyledPanel"))
    section("Containers", [inner_tabs, split, frame])

    _zoo["w"] = win
    win.show()
    win.raise_()
    return win


# -------------------------------------------------------------------- scenarios
SCENARIOS = {
    "tabs": [
        {"tab": "comfyui"}, {"wait": 2500}, {"shot": "tab_comfyui"},
        {"tab": "gallery"}, {"wait": 3500}, {"shot": "tab_gallery"},
        {"tab": "passbuilder"}, {"wait": 2000}, {"shot": "tab_passbuilder"},
        {"tab": "republish"}, {"wait": 2000}, {"shot": "tab_republish"},
        {"tab": "mp4maker"}, {"wait": 2000}, {"shot": "tab_mp4maker"},
        {"tab": "cleaner"}, {"wait": 2000}, {"shot": "tab_cleaner"},
        {"tab": "settings"}, {"wait": 2500}, {"shot": "tab_settings"},
        {"tab": "logs"}, {"wait": 1500}, {"shot": "tab_logs"},
    ],
    "zoo": [
        {"zoo": 1}, {"wait": 1200}, {"shot": "zoo_widgets"},
        {"close": 1}, {"wait": 500},
    ],
    "settings": [
        {"tab": "settings"}, {"wait": 2500},
        {"scroll": 0.0}, {"wait": 400}, {"shot": "settings_scroll_0"},
        {"scroll": 0.25}, {"wait": 400}, {"shot": "settings_scroll_1"},
        {"scroll": 0.50}, {"wait": 400}, {"shot": "settings_scroll_2"},
        {"scroll": 0.75}, {"wait": 400}, {"shot": "settings_scroll_3"},
        {"scroll": 1.0}, {"wait": 400}, {"shot": "settings_scroll_4"},
        {"scroll": 0.0}, {"wait": 600},
        {"click": r"^Version History$"}, {"wait": 1800}, {"shot": "settings_version_history"},
        {"close": 1}, {"wait": 800},
        {"click": r"^Submit Request$"}, {"wait": 1800}, {"shot": "settings_submit_request"},
        {"close": 1}, {"wait": 800},
        {"click": r"^View Requests"}, {"wait": 1800}, {"shot": "settings_view_requests"},
        {"close": 1}, {"wait": 800},
    ],
    # ComfyUI's "Change" is not a dialog — _on_change_model_clicked() calls
    # _show_model_grid(), a state machine that hides selectedModelHeader and
    # shows modelGridContainer. There is no close; you return to the selected
    # state by picking a model card. Edit/Presets only exist in that state, so
    # the selected-state shots must come first and the grid must be exited by
    # clicking a ModelCard rather than by close_top().
    "comfyui": [
        {"tab": "comfyui"}, {"wait": 2500},
        {"click": r"^Presets$"}, {"wait": 2500}, {"shot": "comfy_prompt_builder"},
        {"close": 1}, {"wait": 1500},
        {"click": r"^Edit$"}, {"wait": 2500}, {"shot": "comfy_model_edit"},
        {"close": 1}, {"wait": 1500},
        # "Add Images..." opens a native OS file dialog. Qt cannot grab those,
        # so it is deliberately not captured rather than yielding a 192-byte
        # stub that looks like a passing shot.
        {"click": r"^Change$"}, {"wait": 2500}, {"shot": "comfy_model_grid"},
        {"click_class": ["_InlineModelCard", 2]}, {"wait": 3000},
        {"shot": "comfy_selected"},
    ],
    "gallery": [
        {"tab": "gallery"}, {"wait": 3500},
        {"click": r"^Filters$"}, {"wait": 1500}, {"shot": "gallery_filters"},
        {"close": 1}, {"wait": 1000},
        {"click": r"^Stacks$"}, {"wait": 1500}, {"shot": "gallery_stacks"},
        {"close": 1}, {"wait": 1000},
        {"click": r"New Group"}, {"wait": 2000}, {"shot": "gallery_group_editor"},
        {"close": 1}, {"wait": 1200},
        # Only StackedThumbnailWidget implements contextMenuEvent; a plain
        # ThumbnailWidget right-click is a no-op.
        {"rclick_class": ["StackedThumbnailWidget", 0]},
        {"shot_popup": "gallery_context_menu"},
        {"close": 1}, {"wait": 1500},
        {"dclick_thumb": 2}, {"wait": 3500}, {"shot": "gallery_viewer_image"},
        {"close": 1}, {"wait": 3000},
        {"dclick_thumb": 0}, {"wait": 4000}, {"shot": "gallery_viewer_video"},
        {"close": 1}, {"wait": 3000},
        {"dclick_thumb": 3}, {"wait": 5000}, {"shot": "gallery_viewer_3d"},
        {"close": 1}, {"wait": 3000},
    ],
    "cleaner": [
        {"tab": "cleaner"}, {"wait": 2000}, {"shot": "cleaner_shot"},
        {"subtab": r"Gallery Cleanup"}, {"wait": 2000}, {"shot": "cleaner_gallery"},
        {"subtab": r"Shot Cleanup"}, {"wait": 1000},
    ],
    "renders": [
        {"tab": "passbuilder"}, {"wait": 2000},
        {"click": r"^Rescan$"}, {"wait": 3000}, {"shot": "renders_passbuilder_scanned"},
        {"tab": "mp4maker"}, {"wait": 2000},
        {"click": r"^Rescan$"}, {"wait": 3000}, {"shot": "renders_mp4_scanned"},
    ],
}

ORDER = ["tabs", "zoo", "settings", "comfyui", "gallery", "cleaner", "renders"]
chosen = ONLY or ORDER
unknown = [s for s in chosen if s not in SCENARIOS]
if unknown:
    log(f"!! unknown scenarios: {', '.join(unknown)}")
    chosen = [s for s in chosen if s in SCENARIOS]

QUEUE = []
for name in chosen:
    QUEUE.append({"_scenario": name})
    QUEUE.extend(SCENARIOS[name])

log(f"scenarios: {', '.join(chosen)}  ({len(QUEUE)} steps)")

_i = {"n": 0, "waits": 0}


def run_next():
    if _i["n"] >= len(QUEUE):
        log("done")
        close_everything()
        QtCore.QTimer.singleShot(600, lt.app.quit)
        return
    step = QUEUE[_i["n"]]
    _i["n"] += 1
    delay = 350
    try:
        if "_scenario" in step:
            log(f"===== scenario: {step['_scenario']}")
        elif "tab" in step:
            log(f"--- tab {step['tab']}")
            main_window().select_tab_by_name(step["tab"])
        elif "wait" in step:
            delay = step["wait"]
        elif "shot" in step:
            do_shot(step["shot"])
        elif "shot_popup" in step:
            do_shot_popup(step["shot_popup"])
            delay = 900
        elif "close" in step:
            log(f"close -> {close_top()}")
            delay = 700
        elif "key" in step:
            send_key(step["key"])
            delay = 500
        elif "scroll" in step:
            scroll_to(step["scroll"])
        elif "zoo" in step:
            build_zoo()
            delay = 800
        elif "click" in step:
            b = find_button(step["click"])
            if b is None:
                log(f"!! no button matching {step['click']!r}")
            else:
                log(f"click {b.text()!r}")
                click(b)
            delay = 600
        elif "click_obj" in step:
            w = find_by_objname(step["click_obj"])
            if w is None:
                log(f"!! no widget named {step['click_obj']!r}")
            else:
                click(w)
            delay = 600
        elif "click_class" in step:
            cls, idx = step["click_class"]
            w = find_by_class(cls, idx)
            if w is None:
                log(f"!! no visible {cls} at index {idx}")
            else:
                log(f"click {cls}[{idx}]")
                click(w)
            delay = 800
        elif "subtab" in step:
            tw, idx = find_subtab(step["subtab"])
            if tw is None:
                log(f"!! no sub-tab matching {step['subtab']!r}")
            else:
                log(f"subtab {tw.tabText(idx)!r}")
                tw.setCurrentIndex(idx)
            delay = 700
        elif "rclick_class" in step:
            cls, idx = step["rclick_class"]
            w = find_by_class(cls, idx)
            if w is None:
                log(f"!! no visible {cls} at index {idx}")
            else:
                log(f"right-click {cls}[{idx}]")
                right_click(w)
            delay = 400
        elif "dclick_thumb" in step or "rclick_thumb" in step:
            rc = "rclick_thumb" in step
            idx = step["rclick_thumb"] if rc else step["dclick_thumb"]
            th = thumbnails()
            if idx < len(th):
                log(f"{'right' if rc else 'double'}-click thumb {idx}/{len(th)}"
                    f" ({type(th[idx]).__name__})")
                (right_click if rc else double_click)(th[idx])
            else:
                log(f"!! thumbnail {idx} out of range ({len(th)} found)")
            delay = 700
    except Exception:
        log("step failed:\n" + traceback.format_exc())
    QtCore.QTimer.singleShot(delay, run_next)


def bootstrap():
    if main_window() is None:
        _i["waits"] += 1
        if _i["waits"] > 80:
            log("!! main window never appeared")
            lt.app.quit()
            return
        QtCore.QTimer.singleShot(500, bootstrap)
        return
    main_window().resize(*WINDOW_SIZE)
    _watch["timer"] = QtCore.QTimer()
    _watch["timer"].timeout.connect(watchdog)
    _watch["timer"].start(2000)
    QtCore.QTimer.singleShot(2500, run_next)


QtCore.QTimer.singleShot(2000, bootstrap)

try:
    lt.main()
except SystemExit:
    pass
