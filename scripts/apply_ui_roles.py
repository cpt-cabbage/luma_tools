"""Inject component-contract dynamic properties into the .ui sources.

The stylesheet keys off [role]/[text]/[variant] properties rather than object
names. This script writes those properties into the .ui XML so they are set at
load time, and is idempotent — re-running it updates existing values rather
than duplicating them.

    python scripts/apply_ui_roles.py [--check]

--check reports what would change without writing.

Roles
-----
    primary    the panel's single terminal action
    secondary  ordinary action (default)
    ghost      low-emphasis / icon action
    link       text-only toggle, no chrome
    danger     destructive and hard to undo
    ayon       AYON publish action

Exactly one primary per panel. danger is not "red because it is important",
it is "this deletes things".
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(ROOT, "resources", "ui", "tabs")

# widget name -> {property: value}
ROLES = {
    # ---- cleaner ----------------------------------------------------
    "RescanCleanFiles":         {"role": "secondary"},
    "CleanFiles":               {"role": "danger"},
    "GalleryScanButton":        {"role": "secondary"},
    "GalleryCleanupButton":     {"role": "danger"},

    # ---- comfyui ----------------------------------------------------
    "ComfyUIChoosePreset":      {"role": "ghost"},
    "workflowSettingsBtn":      {"role": "ghost", "iconOnly": "true"},
    "advancedGearBtn":          {"role": "ghost", "iconOnly": "true"},
    "ComfyUIRandomizeSeed":     {"role": "ghost", "iconOnly": "true"},
    "editModelBtn":             {"role": "ghost", "density": "sm"},
    "changeModelBtn":           {"role": "secondary", "density": "sm"},
    "advancedToggleBtn":        {"role": "link"},
    "ComfyUISubmit":            {"role": "primary"},
    "ComfyUICancelJobs":        {"role": "danger"},
    "ComfyUIUseAsInput":        {"role": "secondary"},

    # ---- gallery ----------------------------------------------------
    "GalleryUserButton":        {"role": "secondary"},
    "GallerySortButton":        {"role": "secondary"},
    "GalleryShortcutsButton":   {"role": "ghost", "iconOnly": "true"},
    "GalleryOpenExplorer":      {"role": "secondary"},
    "GalleryRefresh":           {"role": "secondary"},

    # ---- logs -------------------------------------------------------
    "PauseLogButton":           {"role": "secondary"},
    "ClearLogButton":           {"role": "secondary"},

    # ---- mp4 maker --------------------------------------------------
    "MP4SourceButton":          {"role": "secondary"},
    "MP4QualityButton":         {"role": "secondary"},
    "MP4BrowseCustomPath":      {"role": "secondary", "density": "sm"},
    "MP4BrowseOutput":          {"role": "secondary", "density": "sm"},
    "MP4ScanRenders":           {"role": "secondary"},
    "MP4Generate":              {"role": "primary"},

    # ---- pass builder -----------------------------------------------
    "ScanRenders":              {"role": "secondary"},
    "BuildTypeButton":          {"role": "secondary"},
    "BuildPasses":              {"role": "primary"},

    # ---- republish --------------------------------------------------
    "RePublishSourceButton":    {"role": "secondary"},
    "RePublishTaskButton":      {"role": "secondary"},
    "RePublishBrowseCustomPath": {"role": "secondary", "density": "sm"},
    "RePublishScanRenders":     {"role": "secondary"},
    "RePublishPublish":         {"role": "ayon"},

    # ---- settings ---------------------------------------------------
    "showVersionHistoryButton":   {"role": "secondary"},
    "submitFeatureRequestButton": {"role": "secondary"},
    "viewFeatureRequestsButton":  {"role": "secondary"},
    "RegenerateThumbnailsButton": {"role": "secondary"},
    "AddPassButton":              {"role": "secondary", "density": "sm"},
    "RemovePassButton":           {"role": "secondary", "density": "sm"},
    "ResetPassesButton":          {"role": "secondary", "density": "sm"},
    "SaveSettingsButton":         {"role": "primary"},
    "BrowseGlobalSettingsPath":   {"role": "secondary", "density": "sm"},
    "ComfyUIModeButton":          {"role": "secondary"},
    "BrowseComfyUIPath":          {"role": "secondary", "density": "sm"},
    "BrowseComfyUIPython":        {"role": "secondary", "density": "sm"},
    "BrowseNetworkOutput":        {"role": "secondary", "density": "sm"},
    "AddAdminUserButton":         {"role": "secondary", "density": "sm"},
    "RemoveAdminUserButton":      {"role": "secondary", "density": "sm"},
    "AddCategoryButton":          {"role": "secondary", "density": "sm"},
    "RemoveCategoryButton":       {"role": "secondary", "density": "sm"},
    "MoveCategoryUpButton":       {"role": "secondary", "density": "sm"},
    "MoveCategoryDownButton":     {"role": "secondary", "density": "sm"},
    "AddHdriButton":              {"role": "secondary", "density": "sm"},
    "RemoveHdriButton":           {"role": "secondary", "density": "sm"},
    "SaveGlobalSettings":         {"role": "primary"},

    # ---- frames -----------------------------------------------------
    "comfyuiModelFrame":        {"variant": "panel"},
    "comfyuiInputFrame":        {"variant": "panel"},
    "comfyuiSettingsFrame":     {"variant": "panel"},
    "comfyuiSubmitFrame":       {"variant": "panel"},
    "comfyuiIterateFrame":      {"variant": "panel"},
    "noteBanner":               {"variant": "note"},
    "advancedSeparator":        {"variant": "divider"},

    # ---- labels -----------------------------------------------------
    "modelStepTitle":           {"textRole": "title"},
    "inputStepTitle":           {"textRole": "title"},
    "settingsStepTitle":        {"textRole": "title"},
    "submitStepTitle":          {"textRole": "title"},
    "ComfyUIIterateTitle":      {"textRole": "title"},
    "selectedModelName":        {"textRole": "display"},
    "selectedModelBadge":       {"variant": "badge"},
    "selectedModelDesc":        {"textRole": "help"},
    "ComfyUIEtaLabel":          {"textRole": "help"},
    "ComfyUIIterateStatus":     {"textRole": "help"},
    "noteText":                 {"textRole": "help"},
    "ComfyUINetworkPathDisplay": {"textRole": "mono"},
    "label_count_value":        {"textRole": "value"},
    "ComfyUIIteratePreview":    {"variant": "sunken"},
    "ComfyUIIterateProgress":   {"variant": "slim"},
    "RePublishRenderPath":      {"variant": "path"},
    "RePublishCustomPathLabel": {"variant": "path"},
    "LatestUSD":                {"textRole": "label", "state": "success"},

    # NOTE: StatusLabel and LastLogLabel are built in Python
    # (core/luma_tools.py), not in a .ui file, so their properties are set
    # there directly. main_window.ui declares a StatusLabel but that file is
    # never loaded — UI_FILE_PATH is defined in config.py and unused.
}

WIDGET_RE = r'(<widget class="[^"]+" name="{name}"\s*>\n)([ \t]*)'

# Property names this script used to write that collide with real Qt
# properties and must be scrubbed wherever they appear:
#   text  -> QLabel.text          setProperty("text", "help") REPLACES the
#                                 label's displayed text with "help"
#   icon  -> QAbstractButton.icon (QIcon)
#   size  -> QWidget.size         (QSize)
# Only stdset="0" entries are removed; a real <property name="text"> has no
# stdset attribute and must be left alone.
LEGACY_KEYS = ("text", "icon", "size")

LEGACY_RE = re.compile(
    r'[ \t]*<property name="(?:' + "|".join(LEGACY_KEYS) + r')" stdset="0">\s*'
    r'<string>[^<]*</string>\s*</property>\n',
    re.DOTALL,
)


def prop_xml(indent, key, value):
    return (f'{indent}<property name="{key}" stdset="0">\n'
            f'{indent} <string>{value}</string>\n'
            f'{indent}</property>\n')


def existing_prop_re(name, key):
    """Match an existing dynamic property inside the named widget."""
    return re.compile(
        r'(<widget class="[^"]+" name="' + re.escape(name) + r'"\s*>'
        r'(?:(?!</widget>).)*?)'
        r'<property name="' + re.escape(key) + r'" stdset="0">\s*'
        r'<string>[^<]*</string>\s*</property>\n[ \t]*',
        re.DOTALL,
    )


def apply_to_text(text, name, props):
    """Return (text, changed_count) for one widget."""
    changed = 0
    # Drop any properties we manage that are already present, so re-running
    # updates rather than accumulating duplicates.
    for key in props:
        rx = existing_prop_re(name, key)
        new_text, n = rx.subn(lambda m: m.group(1), text)
        if n:
            text = new_text
            changed += n

    m = re.search(WIDGET_RE.format(name=re.escape(name)), text)
    if not m:
        return text, changed, False

    indent = m.group(2)
    block = "".join(prop_xml(indent, k, v) for k, v in sorted(props.items()))
    insert_at = m.end(1)
    text = text[:insert_at] + block + text[insert_at:]
    return text, changed + len(props), True


def main():
    check_only = "--check" in sys.argv
    total_widgets = 0
    not_found = []

    for filename in sorted(os.listdir(UI_DIR)):
        if not filename.endswith(".ui"):
            continue
        path = os.path.join(UI_DIR, filename)
        with open(path, "r", encoding="utf-8") as fh:
            text = original = fh.read()

        text, legacy_n = LEGACY_RE.subn("", text)
        if legacy_n:
            print(f"{filename}: stripped {legacy_n} legacy colliding propert"
                  f"{'y' if legacy_n == 1 else 'ies'}")

        touched = []
        for name, props in ROLES.items():
            if f'name="{name}"' not in text:
                continue
            text, _, ok = apply_to_text(text, name, props)
            if ok:
                touched.append(name)
                total_widgets += 1

        if touched and text != original:
            if not check_only:
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(text)
            print(f"{filename}: {len(touched)} widgets -> {', '.join(sorted(touched))}")

    seen = set()
    for filename in os.listdir(UI_DIR):
        if filename.endswith(".ui"):
            with open(os.path.join(UI_DIR, filename), encoding="utf-8") as fh:
                content = fh.read()
            for name in ROLES:
                if f'name="{name}"' in content:
                    seen.add(name)
    not_found = sorted(set(ROLES) - seen)

    print(f"\ntotal widgets updated: {total_widgets}")
    if not_found:
        print(f"!! not found in any .ui ({len(not_found)}): {', '.join(not_found)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
