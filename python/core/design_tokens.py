"""Design tokens — the single source of truth for the Luma Tools visual language.

Direction B, "Elevated & calm": panels sit lighter than the page, carry no
border, and lift with a hairline highlight and a soft radius.

Everything visual resolves here. The stylesheet
(``resources/ui/la_shot_tools_styles.qss``) is a template whose double-brace
token placeholders are substituted from :func:`token_map` at load time, and
Python code reads the same constants. ``UIColors`` and ``LoadingStyles`` are aliased
onto these values so existing imports keep working.

Do not hardcode a colour, radius or spacing value anywhere else. If a value is
needed that does not exist here, add it here first.

Note on elevation
-----------------
Qt stylesheets do not support ``box-shadow``. The elevated look is produced by
background contrast (panel lighter than page), a soft radius, and a 1px
top hairline — not by shadows. ``QGraphicsDropShadowEffect`` is deliberately
avoided: it is per-widget, forces a repaint, and composes badly with rounded
QSS backgrounds.
"""


class Color:
    """Every colour in the application."""

    # --- surfaces -------------------------------------------------------
    PAGE = "#16181d"           # window and tab-pane background
    PANEL = "#1d2026"          # raised panel / card surface
    PANEL_ALT = "#232730"      # nested surface inside a panel
    SUNKEN = "#131519"         # inputs, lists, log views, path fields
    HOVER = "#262a32"          # hover on rows, list items, secondary buttons
    SELECTED = "#232b36"       # selected row / checked item
    OVERLAY_SCRIM = "rgba(10, 11, 14, 0.72)"

    # Media review surround. Deliberately darker and more neutral than the
    # app chrome so it does not tint what is being reviewed. This is a design
    # decision, not drift — image and video review needs a neutral ground.
    CANVAS = "#0e0f12"
    CANVAS_CHROME = "rgba(255, 255, 255, 0.08)"   # controls floating on canvas
    CANVAS_CHROME_HOVER = "rgba(255, 255, 255, 0.16)"
    SCRIM = "rgba(0, 0, 0, 0.55)"                 # control bar over media
    SCRIM_SOFT = "rgba(0, 0, 0, 0.30)"            # nav arrows over media
    SCRIM_ACCENT = "rgba(90, 169, 255, 0.45)"     # nav arrow hover

    # --- borders --------------------------------------------------------
    BORDER = "#272b33"         # separators, dividers
    BORDER_STRONG = "#333945"  # input borders where a border is needed
    BORDER_FOCUS = "#5aa9ff"
    HAIRLINE = "rgba(255, 255, 255, 0.04)"   # the panel "lift"

    # --- text -----------------------------------------------------------
    TEXT = "#e8ebf0"
    TEXT_SECONDARY = "#8b94a2"
    TEXT_MUTED = "#6b7280"
    TEXT_ON_ACCENT = "#08192a"
    TEXT_ON_DANGER = "#ffffff"

    # --- accent ---------------------------------------------------------
    ACCENT = "#5aa9ff"
    ACCENT_HOVER = "#74b7ff"
    ACCENT_PRESSED = "#3d90e6"
    ACCENT_SUBTLE = "rgba(90, 169, 255, 0.14)"

    # --- brand ----------------------------------------------------------
    AYON = "#00cea5"
    AYON_HOVER = "#00e6b8"
    AYON_PRESSED = "#00b892"
    AYON_SUBTLE = "rgba(0, 206, 165, 0.14)"

    # --- semantic -------------------------------------------------------
    SUCCESS = "#10b981"
    WARNING = "#f59e0b"
    DANGER = "#ef4444"
    DANGER_HOVER = "#f45f5f"
    DANGER_PRESSED = "#d63b3b"
    INFO = "#5aa9ff"
    SCANNING = "#8b5cf6"

    # --- disabled -------------------------------------------------------
    DISABLED_BG = "#1f2229"
    DISABLED_TEXT = "#565d69"
    DISABLED_BORDER = "#242830"

    # --- data palette ---------------------------------------------------
    # Gallery group tinting. Data, not chrome — deliberately unchanged.
    GROUP_COLORS = [
        "#ef4444",  # Red
        "#f97316",  # Orange
        "#eab308",  # Yellow
        "#22c55e",  # Green
        "#06b6d4",  # Cyan
        "#3b82f6",  # Blue
        "#8b5cf6",  # Purple
        "#ec4899",  # Pink
    ]


class Space:
    """Spacing scale, in pixels. Use these, not arbitrary numbers."""
    XXS = 4
    XS = 6
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    XXL = 24
    XXXL = 32

    PANEL_PADDING = 18      # inside a panel
    PANEL_GAP = 14          # between panels
    PAGE_MARGIN = 16        # tab content inset


class Radius:
    XS = 4      # chips, badges, checkbox indicators
    SM = 7      # inputs, secondary buttons, list rows
    MD = 10     # panels
    LG = 14     # overlays, dialogs
    PILL = 999


class Size:
    CONTROL_SM = 27
    CONTROL = 32          # default control height
    CONTROL_LG = 38       # primary action
    ROW = 34              # list row
    ICON = 16
    ICON_LG = 20
    SCROLLBAR = 10
    TAB_HEIGHT = 40


class Font:
    FAMILY = '"Segoe UI", "San Francisco", -apple-system, sans-serif'
    MONO_FAMILY = '"Cascadia Mono", "Consolas", monospace'

    DISPLAY = 18          # overlay and dialog titles
    TITLE = 13            # panel titles (sentence case)
    BODY = 13             # default  (12.5 rounds badly in Qt; use 13)
    LABEL = 12            # field labels, list items
    HELP = 11             # help text under a field
    MICRO = 11            # counters, badges, status (uppercase)

    WEIGHT_NORMAL = 400
    WEIGHT_MEDIUM = 500
    WEIGHT_SEMIBOLD = 600

    MICRO_LETTER_SPACING = "0.09em"


# ---------------------------------------------------------------------------
# QSS template substitution
# ---------------------------------------------------------------------------

_GROUPS = {
    "color": Color,
    "space": Space,
    "radius": Radius,
    "size": Size,
    "font": Font,
}


def token_map():
    """Flat ``{"color.panel": "#1d2026", "space.md": "12", ...}`` mapping.

    Keys are lowercase ``group.attribute``. Numeric values are stringified
    bare (``12``) so a template can write ``{{space.md}}px``.
    """
    out = {}
    for prefix, holder in _GROUPS.items():
        for name in dir(holder):
            if name.startswith("_"):
                continue
            value = getattr(holder, name)
            if isinstance(value, (str, int, float)):
                out[f"{prefix}.{name.lower()}"] = str(value)
    return out


# ---------------------------------------------------------------------------
# Generated icon assets
#
# Qt's CSS-triangle trick (width:0; height:0; border-*) does not render in this
# Qt build — it produces a clipped dash, which is what the combo and spin-box
# arrows have always looked like. Real assets are the only reliable fix, so the
# few chrome glyphs we need are generated as SVG from the tokens at load time.
# Generating rather than shipping them keeps the colours from drifting away
# from the palette.
# ---------------------------------------------------------------------------

_CHEVRON = ('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
            'viewBox="0 0 12 12"><path d="{path}" fill="none" stroke="{color}" '
            'stroke-width="1.6" stroke-linecap="round" '
            'stroke-linejoin="round"/></svg>')

_DOWN = "M2.5 4.5 L6 8 L9.5 4.5"
_UP = "M2.5 7.5 L6 4 L9.5 7.5"

_ICON_SPECS = {
    "chevron_down": (_DOWN, Color.TEXT_SECONDARY),
    "chevron_down_accent": (_DOWN, Color.ACCENT),
    "chevron_down_disabled": (_DOWN, Color.DISABLED_TEXT),
    "chevron_up": (_UP, Color.TEXT_SECONDARY),
    "chevron_up_accent": (_UP, Color.ACCENT),
    "chevron_up_disabled": (_UP, Color.DISABLED_TEXT),
}

_icon_cache = {}


def icon_dir():
    """Directory the generated chrome icons are written to."""
    import os
    return os.path.join(os.path.expanduser("~"), ".luma_tools", "ui_icons")


def ensure_icons():
    """Write the generated SVGs and return ``{name: qss_url_path}``.

    Paths use forward slashes because QSS ``url()`` requires them on Windows.
    Falls back to an empty mapping if the directory cannot be written, so a
    read-only home never stops the app from starting.
    """
    global _icon_cache
    if _icon_cache:
        return _icon_cache

    import os
    target = icon_dir()
    try:
        os.makedirs(target, exist_ok=True)
        out = {}
        for name, (path, color) in _ICON_SPECS.items():
            svg = _CHEVRON.format(path=path, color=color)
            file_path = os.path.join(target, f"{name}.svg")
            # Rewrite only when the content changed, so a palette edit
            # propagates but a normal launch does not touch the disk.
            existing = None
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as fh:
                        existing = fh.read()
                except OSError:
                    existing = None
            if existing != svg:
                with open(file_path, "w", encoding="utf-8") as fh:
                    fh.write(svg)
            out[name] = file_path.replace("\\", "/")
        _icon_cache = out
    except OSError:
        _icon_cache = {}
    return _icon_cache


def render_qss(template):
    """Substitute ``{{token}}`` placeholders in a QSS template.

    Raises:
        KeyError: if the template references a token that does not exist —
            a silent miss would leave a literal ``{{color.typo}}`` in the
            stylesheet, which Qt drops along with the whole rule.
    """
    import re

    tokens = token_map()
    for name, path in ensure_icons().items():
        tokens[f"icon.{name}"] = path
    missing = set()

    def _sub(match):
        key = match.group(1).strip().lower()
        if key not in tokens:
            missing.add(key)
            return match.group(0)
        return tokens[key]

    result = re.sub(r"\{\{([^}]+)\}\}", _sub, template)
    if missing:
        raise KeyError(
            "Unknown design tokens referenced in the stylesheet: "
            + ", ".join(sorted(missing))
        )
    return result


# ---------------------------------------------------------------------------
# Component contract
# ---------------------------------------------------------------------------

def set_role(widget, **props):
    """Set dynamic style properties and force Qt to restyle the widget.

    Qt evaluates property selectors (``QPushButton[role="primary"]``) when a
    widget is polished. Changing a property afterwards does not re-run the
    selector, so the widget keeps its old look until it is unpolished and
    polished again.

    Usage::

        set_role(self.ui.BuildButton, role="primary")
        set_role(self.ui.StatusLabel, textRole="help", state="error")

    Passing ``None`` clears a property.
    """
    for key, value in props.items():
        widget.setProperty(key, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


# Valid values, for reference and for validation in tests.
ROLES = ("primary", "secondary", "ghost", "danger", "ayon")
VARIANTS = ("panel", "subtle", "sunken")
TEXT_ROLES = ("title", "label", "help", "value", "mono", "micro")
STATES = ("success", "warning", "error", "busy")
