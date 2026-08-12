# Luma Tools UI Overhaul — Design

**Date:** 2026-08-12
**Status:** Approved
**Scope:** Full visual + information-architecture overhaul of the PySide6 app.

---

## 1. Problem

The UI is inconsistent because there is no design system — only accumulated per-widget
styling. Evidence gathered from the code and from screenshots of all eight tabs:

### 1.1 Three conflicting palettes ship simultaneously

| Source | Page bg | Panel bg | Body text | Secondary text |
|---|---|---|---|---|
| `UIColors` — `python/core/config.py:436` | `#1e1e1e` | `#2a2a2a` | `#e0e0e0` | `#aaaaaa` |
| `la_shot_tools_styles.qss` | `#21252b` | `#282c34` | `#c5cad3` | `#797e89` |
| `LoadingStyles` — `resources/ui/styles.py:14` | `#21252b` | `#2c313a` | `#c5cad3` | `#797e89` |

None of the three agree. Widgets pick whichever their author reached for.

### 1.2 399 inline `setStyleSheet()` calls across 47 files

Heaviest: `media_viewers.py` (43), `prompt_builder_overlay.py` (33), `dialogs.py` (23),
`groups_panel.py` (21), `ui_components.py` (20), `model_dialog.py` (19),
`inline_model_grid.py` (18), `properties_dialog.py` (18), `comfyui/tab.py` (16).

Each embeds its own hex values, radii and paddings. Nothing propagates.

### 1.3 The stylesheet fights a third-party sheet

`load_stylesheet()` (`resources/ui/ui_components.py:1953`) concatenates qdarkstyle's
`darkstyle.qss` (54 KB / 1,816 lines) with the custom sheet (27 KB / 899 lines). To win
that fight the custom sheet uses **84 `!important` declarations**.

### 1.4 Styling is keyed to object names, not roles

`QPushButton#MP4Generate`, `#CleanFiles`, `#ComfyUISubmit`, `#ComfyUICancelJobs`,
`#changeModelBtn`, `#editModelBtn`, `#advancedGearBtn`, `#ComfyUIChoosePreset`,
`#ComfyUIUseAsInput` are each painted separately. A new button inherits nothing, so every
addition drifts further.

### 1.5 Observed symptoms

- **Two competing card idioms on screen at once.** ComfyUI uses flat cards with bold inline
  headers ("Choose Model", "Input", "Settings"); Pass Builder / rePublish / MP4 Maker /
  Settings use `QGroupBox` with a floating title chip.
- **Duplicated headings.** The model picker renders "Choose Model" (card header) directly
  above "Choose a Model" (overlay heading).
- **Settings is a single five-screen scroll** with no sections and no search. Label column
  widths vary between 80 px, 150 px and 240 px inside the same panel. Help text alternates
  between italic-below-field, inline parenthetical, and absent.
- **Scroll inside scroll.** Default Passes, Admin Users, ComfyUI Preset Categories and HDRI
  Environment Maps each embed a scrolling list within the already-scrolling page.
- **Border colour used as semantics** — blue outline = user settings, orange = global.
  Used nowhere else in the app, and unreadable without the legend.
- **Four treatments for the same button rank.** `BUILD` and `GENERATE MP4` read as ghost
  or disabled, `Run Cleaner` is solid red, `Submit to Farm` is a full-width solid blue bar,
  `Publish to AYON` is grey.
- **Unlabelled controls** in the Gallery toolbar and the image-viewer toolbar.
- **Three near-identical tabs.** `MP4MakerTab` and `RePublishTab` both inherit
  `RenderScanMixin(PublishSourceMixin)`; `PassBuilderTab` inherits `PublishSourceMixin`
  and calls `RenderScanMixin._scan_render_directory_worker` directly
  (`pass_builder_tab.py:205`). They are one workflow with three endpoints.

---

## 2. Goals and non-goals

### Goals

1. One source of truth for every colour, space, radius and type size.
2. Visual consistency across all tabs, dialogs, overlays and viewers — "full consistency
   across the board".
3. Fewer, clearer surfaces: three render tabs become one.
4. Settings that can be navigated and scanned rather than scrolled.
5. A styling architecture where a new widget is consistent **by default**, so the app does
   not re-drift after this work.

### Non-goals

- No functional/behavioural change to pass building, MP4 generation, AYON publishing,
  Deadline submission, ComfyUI workflow handling or gallery operations. This is a UI change.
- **Settings and Logs stay where they are** — tabs reached from the corner-widget ⚙ and `>_`
  buttons. No preferences modal, no status-bar log drawer, no `TAB_REGISTRY` relocation.
  (Explicitly descoped by the user.) Their *contents* are still restyled and, for Settings,
  restructured.
- No light theme. Dark only, as today.

---

## 3. Design tokens — Direction B ("Elevated & calm")

New module: **`python/core/design_tokens.py`**. Single source of truth.

### 3.1 Colour

| Token | Value | Use |
|---|---|---|
| `bg.page` | `#16181d` | Window and tab-pane background |
| `bg.panel` | `#1d2026` | Raised panel / card surface |
| `bg.panel_alt` | `#232730` | Nested surface inside a panel |
| `bg.sunken` | `#131519` | Inputs, lists, log views, path fields |
| `bg.hover` | `#262a32` | Hover on rows, list items, secondary buttons |
| `bg.selected` | `#232b36` | Selected row / checked item |
| `border.subtle` | `#272b33` | Separators, dividers |
| `border.strong` | `#333945` | Input borders where a border is needed |
| `border.focus` | `#5aa9ff` | Focus ring |
| `text.primary` | `#e8ebf0` | Body and titles |
| `text.secondary` | `#8b94a2` | Labels, captions, inactive tabs |
| `text.muted` | `#6b7280` | Help text, placeholders, disabled |
| `text.on_accent` | `#08192a` | Text on an accent-filled surface |
| `accent` | `#5aa9ff` | Primary action, focus, selection |
| `accent.hover` | `#74b7ff` | |
| `accent.press` | `#3d90e6` | |
| `ayon` | `#00cea5` | AYON publish actions only |
| `ayon.hover` | `#00e6b8` | |
| `success` | `#10b981` | |
| `warning` | `#f59e0b` | |
| `danger` | `#ef4444` | Destructive actions only (Run Cleaner, Delete) |
| `danger.hover` | `#f45f5f` | |
| `scanning` | `#8b5cf6` | In-progress scan state |

`GROUP_COLORS` (gallery group tinting) is retained as-is — it is data-driven, not chrome.

### 3.2 Space, radius, size

- **Space scale:** `4, 6, 8, 12, 16, 20, 24, 32`. Panel padding `16`/`18`. Gap between
  panels `14`.
- **Radius:** `xs 4` (chips, badges) · `sm 7` (inputs, secondary buttons, list rows) ·
  `md 10` (panels) · `lg 14` (overlays, dialogs) · `pill 999`.
- **Control heights:** `sm 27` · `md 32` (default) · `lg 38` (primary action).
- **List row height:** `34`.

### 3.3 Type

Family `Segoe UI`; mono `Cascadia Mono, Consolas, monospace`.

| Token | Size / weight | Use |
|---|---|---|
| `display` | 18 px / 600 | Overlay and dialog titles |
| `title` | 13 px / 600 | Panel titles (sentence case) |
| `body` | 12.5 px / 400 | Default |
| `label` | 11.5 px / 500 | Field labels, list items |
| `help` | 11 px / 400, `text.muted` | Help text under a field |
| `micro` | 10.5 px / 600, uppercase, ls `.09em` | Counters, badges, status |
| `mono` | 11.5 px | Paths, logs, frame ranges |

### 3.4 Elevation — a Qt constraint, stated explicitly

**Qt stylesheets do not support `box-shadow`.** Direction B's "elevated" quality is
therefore expressed without shadows:

- panel background is **lighter** than the page (`#1d2026` on `#16181d`),
- panels carry **no border**,
- a 1 px top hairline `rgba(255,255,255,0.04)` gives the lift,
- `border-radius: 10px`.

`QGraphicsDropShadowEffect` is deliberately **not** used: it is per-widget, costs a repaint,
and composes badly with rounded QSS backgrounds. Contrast plus radius carries the look.

---

## 4. Stylesheet architecture

### 4.1 Drop qdarkstyle

`load_stylesheet()` stops concatenating `darkstyle.qss`. We own the full sheet. All 84
`!important` declarations are removed — nothing is competing anymore.

`QDARKSTYLE_PATH` is removed from `core/config.py`.

### 4.2 Template + substitution

`resources/ui/la_shot_tools_styles.qss` becomes a template containing `{{color.panel}}`,
`{{space.4}}`, `{{radius.md}}` placeholders. `load_stylesheet()` reads it and substitutes
from `design_tokens.py` before handing it to `app.setStyleSheet()`.

Plain `str.replace` over a flat token dict — no templating dependency, and the file stays
valid-ish CSS for editor highlighting.

### 4.3 Back-compatibility for existing imports

`UIColors` (config.py) and `LoadingStyles` (styles.py) keep their attribute names but their
values become aliases into `design_tokens`. Existing `from core.config import UIColors`
imports keep working through the transition; call sites migrate in L3 and the aliases are
kept as a deprecation shim, not deleted, so any missed reference still yields a correct
colour rather than an `AttributeError`.

---

## 5. Component contract

Styling keys off **Qt dynamic properties**, not object names — extending the
`QPushButton[utility="true"]` pattern already in the sheet.

| Property | Values | Applies to |
|---|---|---|
| `role` | `primary`, `secondary`, `ghost`, `danger`, `ayon` | buttons |
| `variant` | `panel`, `subtle`, `sunken` | frames / containers |
| `text` | `title`, `label`, `help`, `value`, `mono`, `micro` | labels |
| `state` | `success`, `warning`, `error`, `busy` | status labels, banners |

**Rules:**

- Exactly **one** `role="primary"` per panel — the panel's terminal action.
- `danger` is reserved for destructive, irreversible actions (Run Cleaner, Delete).
- `ayon` is reserved for AYON publish actions.
- Everything else is `secondary` or `ghost`.

All `#objectName` button rules in the QSS are deleted and replaced by these selectors.

**Helper required.** Qt does not re-evaluate property selectors after a property changes on
a polished widget. `design_tokens.py` ships:

```python
def set_role(widget, **props):
    """Set dynamic style properties and force a restyle."""
    for k, v in props.items():
        widget.setProperty(k, v)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
```

`.ui` files set these statically where possible; Python uses `set_role()` when switching at
runtime (e.g. a button that becomes destructive in a given mode).

---

## 6. Information architecture

### 6.1 Tab bar

`ComfyUI · Gallery · Renders · Cleaner` + corner widget `⚙ >_` (unchanged position).

Default order puts ComfyUI and Renders first — the two heaviest-use surfaces.

### 6.2 The Renders merge

`PassBuilderTab`, `RePublishTab` and `MP4MakerTab` collapse into one `RendersTab`.

**Shared shell (scanned once):**
- Source panel: path display, `Source` selector, `Version` selector, `Rescan`.
- Renders panel: the render list with an `n of m selected` counter.

**Destination switch** in the right column — `Build passes` / `Make MP4` / `Publish to AYON`
— swapping a `QStackedWidget` of destination options and one primary action button whose
label follows the destination.

**Consequences to handle:**
- `app_state` keeps `renders`/`searchpath` and retires `mp4_renders`/`mp4_searchpath` and
  `republish_renders` (grep and migrate all references).
- Three `restrict_key`s (`passbuilder`, `republish`, `mp4maker`) collapse to `renders`.
  Any per-tab restriction in `global_settings.json` must be migrated.
- `_TAB_ALIASES` keeps `pass`, `passbuilder`, `mp4`, `mp4maker`, `republish` as aliases
  resolving to `renders`, so existing `--tab` invocations and shortcuts keep working.
- `RenderScanMixin` / `PublishSourceMixin` fold into `RendersTab` directly; the mixins are
  removed only if no other tab uses them.

### 6.3 Settings, restructured in place

Still `SettingsTab`, still reached from the corner ⚙. Internally:

- **Left section nav** — Info · General · ComfyUI · Viewer · Passes · Global · Advanced.
  Selecting a section swaps a `QStackedWidget`; each section fits without scrolling where
  possible, and scrolls independently where it cannot.
- **One aligned label column** per section (single `QFormLayout`, consistent width).
- **No scroll-inside-scroll.** Default Passes, Admin Users, Preset Categories and HDRI Maps
  become full-height list panels within their own section, not nested scrollers.
- **One help-text treatment** — `text="help"` beneath the field it describes. The italic /
  parenthetical / absent variants all go.
- **Filter box** that filters settings by label across sections.
- **User vs Global** is communicated by section grouping and a `micro` badge, not by blue
  and orange borders. The destructive-scope warning on Global stays, as text.
- Save buttons stay where they are functionally (per-scope), restyled to `role="primary"`.

---

## 7. Screenshot harness

Two scripts, already prototyped and kept in the repo root alongside the other `_*.ps1`
helpers:

- `_shoot_ui.ps1` — launches the real app, walks the tab bar, grabs each tab.
- `_shoot_deep.ps1` — data-driven scenario runner: clicks buttons by text regex, scrolls
  scroll areas, double-clicks gallery thumbnails, grabs modals / overlays / the main window.

**Hardening required in L0** (known gaps from the prototype run):
- overlay dismissal — inline overlays such as the ComfyUI model picker are neither modal nor
  top-level, so `close_top()` misses them; needs an overlay-aware close.
- add coverage for: 3D model viewer, comparison viewer, properties dialog, prompt builder,
  batch selector, gallery context menus, group editor, feature-request dialogs, empty states,
  and error/spinner states.
- add a **widget zoo** screen instantiating every styled control type on one page, so
  missing selectors after the qdarkstyle removal are obvious.

Before/after captures run at every layer boundary.

---

## 8. Layer plan

Per `CLAUDE.md` multi-file discipline — data/config, then logic, then wiring, then UI.

| Layer | Work | Verify |
|---|---|---|
| **L0** | Harden harness; capture full baseline | Baseline set complete |
| **L1** | `design_tokens.py`; QSS template + substitution; drop qdarkstyle; alias `UIColors` / `LoadingStyles` | Every tab renders; **no widget falls back to native grey**; widget zoo clean |
| **L2** | Component contract; delete `#objectName` rules; `set_role()` helper; apply roles in `.ui` + Python | Button ranks, hover / press / disabled, focus rings |
| **L3** | Remove all 399 inline `setStyleSheet` across 47 files | Viewers, overlays, prompt builder, thumbnails, dialogs, empty states |
| **L4** | `.ui` relayout — one card idiom, aligned label columns, button placement; recompile via `pyside6-uic` | All tabs at small **and** large window sizes |
| **L5** | Renders merge; `app_state` migration; alias + `restrict_key` migration | Scan, version, source, build passes, MP4, AYON publish, `--tab` aliases |
| **L6** | Settings section nav, form alignment, nested-scroller removal, filter | Every setting still reads and writes; global vs user scope respected |
| **L7** | Full screenshot sweep; `pytest tests/`; check-code | Green |

---

## 8a. Outcome and the L5 deferral

L0–L4, L6 and L7 landed. **L5 (the Renders merge) is deferred to its own
session** by user decision on 2026-08-12.

Reason: mapping the three tabs showed they share only the scan shell. Pass
Builder carries a whole second source mode (AYON product fetch, work-render
path resolution from version IDs, product filtering, pass detection); rePublish
carries task discovery and a farm/local publish worker; MP4 Maker carries
quality, frame-range override, burn-in, gallery copy and a *separate* AYON
publish path for the MP4. The merge is ~2,000 lines across exactly the three
behaviours §2 says must not change — and it cannot be verified without
submitting real Deadline jobs and AYON publishes, which is not something to do
unprompted. The screenshot harness proves the UI renders; it cannot prove a
publish lands.

Because the three tabs remain, L4 unified their layout rather than skipping it.

**When resumed**, stage it: MP4 Maker first (simplest), then rePublish, then
Pass Builder (the AYON-source mode makes it the hairiest). One commit per
stage, each with a targeted manual test list, so a regression is attributable
to one tab's worth of change and revertible on its own.

### Measured result

| | Before | After |
|---|---|---|
| Inline `setStyleSheet` calls | 400 | 26 (all deliberate) |
| `styleSheet` properties in `.ui` | 18 | 0 |
| `!important` declarations | 84 | 0 |
| Distinct hex literals | 121 | 88 |
| Uses of the old accent `#4a9eff` | 89 | 3 |
| Palettes in the codebase | 5 disagreeing | 1 |
| Settings | one 5-screen scroll | 5 navigable sections + filter |
| Tests | 823 pass | 823 pass |

The 26 remaining inline calls are per-instance colours (gallery group tints,
model type badges, thumbnail selection borders), `QPropertyAnimation` targets
(QSS cannot animate), caller-chosen sizes, and `apply_stylesheet` itself.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Dropping qdarkstyle leaves widget classes unstyled** — they fall back to native Windows grey, possibly in a rarely-opened dialog | Widget-zoo screen in L0 + full screenshot sweep at L1; qdarkstyle's selector list is enumerated and diffed against ours |
| **Renders merge breaks a workflow** | Merge is L5, after styling is stable, so a regression is unambiguously attributable; `app_state` attribute migration is grepped exhaustively before removal |
| **`restrict_key` collapse changes who can see what** | Migrate `global_settings.json` restrictions explicitly; a user restricted from any of the three old tabs is restricted from `renders` |
| **Recompiled `.ui` files diverge from hand edits** | `.ui` sources only; `_compiled/ui_*.py` regenerated via `pyside6-uic`, never hand-edited (per CLAUDE.md) |
| **Dynamic properties don't restyle at runtime** | `set_role()` unpolish/polish helper; any runtime role change goes through it |
| **Inline-style removal changes behaviour, not just looks** — some inline calls encode state (e.g. error red) | Those become `state="error"` properties rather than deletions; each removal is checked for whether it was conveying state |

---

## 10. Out of scope

- Settings → preferences modal; Logs → status-bar drawer. Descoped by the user.
- Light theme.
- Any change to pass building, MP4 generation, AYON publish, Deadline submission, ComfyUI
  workflow handling, or gallery data operations.
- Changing `GROUP_COLORS` semantics.
- Touching `resources/ui/tabs/_compiled/` by hand.
