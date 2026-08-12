#!/usr/bin/env python
"""
Luma Tools Installer - Deploys to production location.

Source: L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
Target: L:\tools\_studio_tools\luma_tools
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# Configuration
SOURCE = Path(r"L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools")
TARGET = Path(r"L:\tools\_studio_tools\luma_tools")
DEV_PATH = "L:/tools/_studio_tools/AYON/_dev/christophe/la_shot_tools/luma_tools"
PROD_PATH = "L:/tools/_studio_tools/luma_tools"

# Directories to exclude from auto-discovery (venv and libs handled separately)
EXCLUDE_PYTHON_DIRS = {"venv", "__pycache__", "libs", ".pytest_cache"}


def get_input(prompt: str, valid_options: list[str] | None = None) -> str:
    """Get user input with optional validation."""
    while True:
        response = input(prompt).strip().lower()
        if valid_options is None or response in valid_options:
            return response
        print(f"Invalid option. Please enter one of: {', '.join(valid_options)}")


def run_git_command(args: list[str], cwd: Path = SOURCE) -> str:
    """Run a git command and return output."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    return result.stdout.strip()


def increment_version(current: str, update_type: str) -> str:
    """Increment version based on update type."""
    parts = current.split(".")

    if update_type == "b":  # Big update: 0.4 -> 0.5
        return f"{parts[0]}.{int(parts[1]) + 1}"
    elif update_type == "s":  # Small update: 0.4 -> 0.4.1, or 0.4.1 -> 0.4.2
        if len(parts) == 2:
            return f"{parts[0]}.{parts[1]}.1"
        else:
            return f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    elif update_type == "m":  # Minor update: 0.4.1 -> 0.4.1.1, or 0.4.1.1 -> 0.4.1.2
        if len(parts) == 2:
            # 0.5 -> 0.5.0.1
            return f"{parts[0]}.{parts[1]}.0.1"
        elif len(parts) == 3:
            # 0.5.1 -> 0.5.1.1
            return f"{current}.1"
        else:
            # 0.5.1.1 -> 0.5.1.2
            parts[3] = str(int(parts[3]) + 1)
            return ".".join(parts)
    return current


def update_changelog(new_version: str, custom_msg: str | None = None) -> None:
    """Update changelog with git commit message or custom message."""
    if custom_msg:
        commit_msg = custom_msg
    else:
        # Use %B to get full commit body with newlines preserved (not just subject %s)
        commit_msg = run_git_command(["log", "-1", "--pretty=%B"])

    # Format: replace " -" with newline + "-" for custom messages
    # Git messages already have proper newlines, so only apply to custom input
    if custom_msg:
        formatted_msg = commit_msg.replace(" -", "\n-")
    else:
        formatted_msg = commit_msg

    changelog_path = SOURCE / "resources" / "changelog.md"
    content = changelog_path.read_text(encoding="utf-8")

    header = "# Luma Tools Changelog"
    new_entry = f"\n\n## Version {new_version}\n{formatted_msg}"
    content = content.replace(header, header + new_entry)

    changelog_path.write_text(content, encoding="utf-8")
    print("Changelog updated.")


def discover_python_modules() -> list[str]:
    """Auto-discover all Python modules in python/ directory."""
    python_dir = SOURCE / "python"
    if not python_dir.exists():
        return []

    modules = []
    for item in python_dir.iterdir():
        # Skip excluded directories
        if item.name in EXCLUDE_PYTHON_DIRS:
            continue

        # Include if it's a directory with Python files
        if item.is_dir() and list(item.rglob("*.py")):
            modules.append(item.name)

    return sorted(modules)


def clean_python_modules() -> None:
    """Remove all Python modules from target for fresh install.

    Removes ALL directories in TARGET/python/ except venv.
    Cache files are deleted to force fresh bytecode compilation.
    This ensures orphaned modules are cleaned up if they were removed from source.
    """
    print("\nCleaning Python modules from production...")

    python_root = TARGET / "python"
    if not python_root.exists():
        print("  Production python/ directory doesn't exist yet (first deploy)")
        return

    # Only protect venv - everything else gets deleted and re-copied fresh
    protected = {"venv"}

    # Remove all subdirectories except venv
    for item in python_root.iterdir():
        if not item.is_dir():
            continue

        if item.name in protected:
            print(f"  Preserving {item.name}/")
            continue

        # Remove everything else (including __pycache__, libs, all modules)
        print(f"  Removing {item.name}/")
        shutil.rmtree(item)

    # Remove stray .py/.pyc files in python root
    for f in python_root.glob("*.py"):
        print(f"  Removing {f.name}")
        f.unlink()
    for f in python_root.glob("*.pyc"):
        print(f"  Removing {f.name}")
        f.unlink()

    print(f"Python modules cleaned (cache files will be regenerated on first run)")


def copy_python_modules(modules: list[str]) -> None:
    """Copy all Python modules recursively, excluding cache files."""
    print("\nCopying Python modules...")
    print(f"Auto-discovered {len(modules)} modules: {', '.join(modules)}\n")

    # Root-level python/*.py files: clean_python_modules deletes them from
    # production, so they must be re-copied or a future root-level script
    # would silently vanish from every deploy
    for src_file in sorted((SOURCE / "python").glob("*.py")):
        dst_file = TARGET / "python" / src_file.name
        print(f"  Copying {src_file.name}")
        shutil.copy2(src_file, dst_file)

    for module in modules:
        src_module = SOURCE / "python" / module
        dst_module = TARGET / "python" / module

        if not src_module.exists():
            print(f"  WARNING: Source module {module}/ not found, skipping")
            continue

        # Find all .py files recursively, excluding __pycache__ directories
        all_py_files = src_module.rglob("*.py")
        py_files = [f for f in all_py_files if "__pycache__" not in f.parts]

        # Count subdirectories for info
        subdirs = set(f.parent.relative_to(src_module) for f in py_files if f.parent != src_module)
        subdir_info = f" (+{len(subdirs)} subdirs)" if subdirs else ""

        print(f"  Copying {module}/{subdir_info} ({len(py_files)} files)")

        for src_file in py_files:
            # Calculate relative path from module root
            rel_path = src_file.relative_to(src_module)
            dst_file = dst_module / rel_path

            # Create parent directories if needed
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(src_file, dst_file)

    # Copy libs directory (external binaries like Assimp DLL)
    # Exclude __pycache__ if it exists
    src_libs = SOURCE / "python" / "libs"
    if src_libs.exists():
        dst_libs = TARGET / "python" / "libs"
        print(f"  Copying libs/")
        if dst_libs.exists():
            shutil.rmtree(dst_libs)

        # Copy libs but ignore __pycache__ directories
        def ignore_cache(dir, files):
            return ['__pycache__'] if '__pycache__' in files else []

        shutil.copytree(src_libs, dst_libs, ignore=ignore_cache)


def copy_resources() -> None:
    """Copy UI resources, icons, and other assets."""
    print("\nCopying resources...")

    # UI resources (root level)
    src_ui = SOURCE / "resources" / "ui"
    dst_ui = TARGET / "resources" / "ui"
    dst_ui.mkdir(parents=True, exist_ok=True)

    for ext in ["*.ui", "*.qss", "*.py"]:
        for f in src_ui.glob(ext):
            if f.is_file():
                shutil.copy2(f, dst_ui / f.name)
    print("  Copied resources/ui/")

    # Tab UI files
    src_tabs_ui = SOURCE / "resources" / "ui" / "tabs"
    dst_tabs_ui = TARGET / "resources" / "ui" / "tabs"
    if src_tabs_ui.exists():
        dst_tabs_ui.mkdir(parents=True, exist_ok=True)
        for f in src_tabs_ui.glob("*.ui"):
            shutil.copy2(f, dst_tabs_ui / f.name)
        print("  Copied resources/ui/tabs/")

    # Clean stale compiled UI files (will be regenerated by compile_ui_files())
    dst_compiled = dst_tabs_ui / "_compiled"
    if dst_compiled.exists():
        shutil.rmtree(dst_compiled)
        print("  Cleaned stale _compiled/ (will regenerate)")

    # Icons
    src_icons = SOURCE / "resources" / "icons"
    dst_icons = TARGET / "resources" / "icons"
    if src_icons.exists():
        dst_icons.mkdir(parents=True, exist_ok=True)
        for f in src_icons.glob("*.svg"):
            shutil.copy2(f, dst_icons / f.name)
        print("  Copied resources/icons/")

    # Root images (logo, etc.)
    src_resources = SOURCE / "resources"
    dst_resources = TARGET / "resources"
    for f in src_resources.glob("*.png"):
        shutil.copy2(f, dst_resources / f.name)
    print("  Copied resources/*.png")

    # Three.js viewer — copy the whole tree, not just *.html. viewer.html
    # imports three.js from the vendor/ subdirectory next to it; copying only
    # the HTML leaves those imports dangling in production, and the viewer then
    # fails silently (no 3D thumbnails, 10s timeout per model).
    src_threejs = SOURCE / "resources" / "threejs"
    dst_threejs = TARGET / "resources" / "threejs"
    if src_threejs.exists():
        if dst_threejs.exists():
            shutil.rmtree(dst_threejs)
        shutil.copytree(
            src_threejs, dst_threejs,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        file_count = sum(1 for _ in dst_threejs.rglob("*") if _.is_file())
        print(f"  Copied resources/threejs/ ({file_count} files incl. vendored three.js)")


def copy_launcher() -> None:
    """Copy and modify launcher batch file."""
    print("\nCopying launcher...")

    src_launcher = SOURCE / "luma_tools_standalone.bat"
    dst_launcher = TARGET / "luma_tools_standalone.bat"

    # Read, remove 'pause' lines, write
    content = src_launcher.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line.strip() != "pause"]
    dst_launcher.write_text("\n".join(lines), encoding="utf-8")

    print("  Copied luma_tools_standalone.bat (removed pause)")


def copy_global_settings() -> None:
    """Copy and update global settings with production paths."""
    print("\nCopying global settings...")

    src_settings = SOURCE / "global_settings"
    dst_settings = TARGET / "global_settings"
    dst_settings.mkdir(parents=True, exist_ok=True)

    for f in src_settings.glob("*.json"):
        content = f.read_text(encoding="utf-8")
        # Replace dev paths with production paths
        content = content.replace(DEV_PATH, PROD_PATH)
        (dst_settings / f.name).write_text(content, encoding="utf-8")

    print("  Copied and updated paths in global_settings/")


def compile_ui_files() -> None:
    """Precompile .ui files to Python for fast startup (avoids QUiLoader penalty).

    Uses pyside6-uic to convert Qt Designer .ui files into Python classes.
    These are loaded by BaseTab.load_ui() instead of QUiLoader, eliminating
    the ~5s first-load initialization penalty from Qt's UiTools module.
    """
    print("\nCompiling UI files...")

    src_tabs_ui = TARGET / "resources" / "ui" / "tabs"
    compiled_dir = src_tabs_ui / "_compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    # Find pyside6-uic in the target venv
    uic_exe = TARGET / "python" / "venv" / "Scripts" / "pyside6-uic.exe"
    if not uic_exe.exists():
        # Fallback to source venv
        uic_exe = SOURCE / "python" / "venv" / "Scripts" / "pyside6-uic.exe"
    if not uic_exe.exists():
        print("  WARNING: pyside6-uic not found, skipping UI precompilation")
        print("  (App will fall back to QUiLoader at runtime — slower first startup)")
        return

    ui_files = list(src_tabs_ui.glob("*.ui"))
    compiled_count = 0
    for ui_file in ui_files:
        base_name = ui_file.stem
        output_file = compiled_dir / f"ui_{base_name}.py"
        try:
            result = subprocess.run(
                [str(uic_exe), str(ui_file), "-o", str(output_file), "-g", "python"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                compiled_count += 1
            else:
                print(f"  WARNING: Failed to compile {ui_file.name}: {result.stderr}")
        except Exception as e:
            print(f"  WARNING: Error compiling {ui_file.name}: {e}")

    print(f"  Compiled {compiled_count}/{len(ui_files)} .ui files to _compiled/")


def copy_version_files(new_version: str) -> None:
    """Copy version.json and changelog.md from resources."""
    print("\nCopying version files...")

    shutil.copy2(SOURCE / "resources" / "version.json", TARGET / "resources" / "version.json")
    shutil.copy2(SOURCE / "resources" / "changelog.md", TARGET / "resources" / "changelog.md")

    print(f"  Copied resources/version.json and resources/changelog.md")


def copy_venv(update: bool) -> None:
    """Optionally copy virtual environment with progress indication."""
    if not update:
        print("\nSkipping virtual environment update.")
        return

    src_venv = SOURCE / "python" / "venv"
    dst_venv = TARGET / "python" / "venv"

    if not src_venv.exists():
        print(f"WARNING: Source venv not found at {src_venv}")
        return

    print("\nCopying virtual environment...")

    # Remove existing venv for clean install
    if dst_venv.exists():
        print("  Removing existing venv for clean install...")
        shutil.rmtree(dst_venv)

    # Count total files for progress tracking
    print("  Scanning files...")
    all_files = list(src_venv.rglob("*"))
    total_files = len([f for f in all_files if f.is_file()])
    print(f"  Found {total_files} files to copy")

    # Copy with progress
    copied = 0
    last_percent = -1

    for src_path in all_files:
        dst_path = dst_venv / src_path.relative_to(src_venv)

        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            copied += 1

            # Show progress every 5% (guard: total_files can be 0)
            percent = int((copied / total_files) * 100) if total_files else 100
            if percent != last_percent and percent % 5 == 0:
                print(f"  Progress: {percent}% ({copied}/{total_files} files)")
                last_percent = percent

    print(f"  Virtual environment copied ({copied} files)")


def main():
    print("=" * 60)
    print("Luma Tools Installer")
    print("=" * 60)
    print(f"\nSource: {SOURCE}")
    print(f"Target: {TARGET}")

    # Verify source exists
    if not SOURCE.exists():
        print(f"\nERROR: Source directory not found: {SOURCE}")
        sys.exit(1)

    # Create target if needed
    TARGET.mkdir(parents=True, exist_ok=True)

    # --- Version and Changelog ---
    version_file = SOURCE / "resources" / "version.json"
    with open(version_file) as f:
        current_version = json.load(f)["version"]

    print(f"\nCurrent version: {current_version}")
    print("\nUpdate types:")
    print("  b = Big update    (0.4 -> 0.5)")
    print("  s = Small update  (0.4 -> 0.4.1, or 0.4.1 -> 0.4.2)")
    print("  m = Minor update  (0.4.1 -> 0.4.1.1)")
    print("  n = No version change")

    update_type = get_input("\nUpdate type (b/s/m/n): ", ["b", "s", "m", "n"])

    if update_type == "n":
        new_version = current_version
        print("Skipping version increment and changelog update.")
    else:
        new_version = increment_version(current_version, update_type)
        print(f"New version: {new_version}")

        # Update version.json
        with open(version_file, "w") as f:
            json.dump({"version": new_version}, f, indent=4)

        # Show last commit (full body with newlines)
        commit_msg = run_git_command(["log", "-1", "--pretty=%B"])
        print(f"\nLast git commit:\n{commit_msg}")

        print("\nChangelog options:")
        print("  g = Use git commit message")
        print("  c = Custom message")
        print("  n = No changelog update")
        response = get_input("Changelog (g/c/n): ", ["g", "c", "n"])
        if response == "g":
            update_changelog(new_version)
        elif response == "c":
            print("Enter changelog message (use ' -' to separate bullet points):")
            custom_msg = input("> ").strip()
            update_changelog(new_version, custom_msg)

    # Ask about venv upfront
    update_venv = get_input("\nUpdate virtual environment? (y/n): ", ["y", "n"]) == "y"

    # Auto-discover Python modules
    print("\nDiscovering Python modules...")
    modules = discover_python_modules()
    if not modules:
        print("ERROR: No Python modules found to deploy!")
        sys.exit(1)

    # --- Copy Files ---
    copy_launcher()
    clean_python_modules()
    copy_python_modules(modules)
    copy_venv(update_venv)
    copy_resources()
    compile_ui_files()
    copy_global_settings()
    copy_version_files(new_version)

    print("\n" + "=" * 60)
    print(f"Installation complete! Version {new_version} deployed.")
    print("=" * 60)

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
