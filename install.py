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

# Python modules to copy (will recursively copy all .py files including subdirectories)
PYTHON_MODULES = [
    "core",
    "ayon",
    "comfyui",
    "models",
    "services",
    "tabs",
    "ui",
]


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
        commit_msg = run_git_command(["log", "-1", "--pretty=%s"])

    # Format: replace " -" with newline + "-"
    formatted_msg = commit_msg.replace(" -", "\n-")

    changelog_path = SOURCE / "changelog.md"
    content = changelog_path.read_text(encoding="utf-8")

    header = "# Luma Tools Changelog"
    new_entry = f"\n\n## Version {new_version}\n{formatted_msg}"
    content = content.replace(header, header + new_entry)

    changelog_path.write_text(content, encoding="utf-8")
    print("Changelog updated.")


def clean_python_modules() -> None:
    """Remove all Python modules from target for fresh install."""
    print("\nCleaning Python modules from production...")

    for module in PYTHON_MODULES:
        module_path = TARGET / "python" / module
        if module_path.exists():
            print(f"  Removing {module}/")
            shutil.rmtree(module_path)

    # Also clean libs directory
    libs_path = TARGET / "python" / "libs"
    if libs_path.exists():
        print("  Removing libs/")
        shutil.rmtree(libs_path)

    # Remove stray files in python root
    python_root = TARGET / "python"
    if python_root.exists():
        for f in python_root.glob("*.py"):
            f.unlink()
        for f in python_root.glob("*.pyc"):
            f.unlink()
        pycache = python_root / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache)

    print("Python modules cleaned.")


def copy_python_modules() -> None:
    """Copy all Python modules recursively."""
    print("\nCopying Python modules...")

    for module in PYTHON_MODULES:
        src_module = SOURCE / "python" / module
        dst_module = TARGET / "python" / module

        if not src_module.exists():
            print(f"  WARNING: Source module {module}/ not found, skipping")
            continue

        # Find all .py files recursively
        py_files = list(src_module.rglob("*.py"))

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
    src_libs = SOURCE / "python" / "libs"
    if src_libs.exists():
        dst_libs = TARGET / "python" / "libs"
        print(f"  Copying libs/")
        if dst_libs.exists():
            shutil.rmtree(dst_libs)
        shutil.copytree(src_libs, dst_libs)


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

    # Three.js viewer
    src_threejs = SOURCE / "resources" / "threejs"
    dst_threejs = TARGET / "resources" / "threejs"
    if src_threejs.exists():
        dst_threejs.mkdir(parents=True, exist_ok=True)
        for f in src_threejs.glob("*.html"):
            shutil.copy2(f, dst_threejs / f.name)
        print("  Copied resources/threejs/")


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


def copy_version_files(new_version: str) -> None:
    """Copy version.json and changelog.md."""
    print("\nCopying version files...")

    shutil.copy2(SOURCE / "version.json", TARGET / "version.json")
    shutil.copy2(SOURCE / "changelog.md", TARGET / "changelog.md")

    print(f"  Copied version.json and changelog.md")


def copy_venv(update: bool) -> None:
    """Optionally copy virtual environment."""
    if not update:
        print("\nSkipping virtual environment update.")
        return

    src_venv = SOURCE / "python" / "venv"
    dst_venv = TARGET / "python" / "venv"

    if not src_venv.exists():
        print(f"WARNING: Source venv not found at {src_venv}")
        return

    print("\nCopying virtual environment (this may take a while)...")

    # Use shutil.copytree with dirs_exist_ok for incremental update
    shutil.copytree(src_venv, dst_venv, dirs_exist_ok=True)

    print("Virtual environment copied.")


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
    version_file = SOURCE / "version.json"
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

        # Show last commit
        commit_msg = run_git_command(["log", "-1", "--pretty=%s"])
        print(f"\nLast git commit: {commit_msg}")

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

    # --- Copy Files ---
    copy_launcher()
    clean_python_modules()
    copy_python_modules()
    copy_venv(update_venv)
    copy_resources()
    copy_global_settings()
    copy_version_files(new_version)

    print("\n" + "=" * 60)
    print(f"Installation complete! Version {new_version} deployed.")
    print("=" * 60)

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
