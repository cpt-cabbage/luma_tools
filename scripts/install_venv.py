#!/usr/bin/env python3
"""
Robust Virtual Environment Recreation Script for Luma Tools.

Features:
- Categorizes packages by importance (critical, required, optional)
- Retries failed installations with multiple strategies
- Platform-aware (skips Windows-only packages on other platforms)
- Verifies imports after installation
- Clear progress reporting with colored output
- Self-bootstrapping (runs with system Python, creates venv)

Usage:
    python scripts/install_venv.py [--clean] [--verify-only] [--skip-optional]

Options:
    --clean         Force remove existing venv even if locked
    --verify-only   Only verify imports, don't reinstall
    --skip-optional Skip optional packages (faster install)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


# =============================================================================
# Configuration
# =============================================================================

# Project root is parent of scripts folder
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"


def get_venv_dir(platform_name: str | None = None) -> Path:
    """
    Get the venv directory for a specific platform.

    Args:
        platform_name: "win32", "darwin", "linux", or None for current platform

    Returns:
        Path to the venv directory
    """
    if platform_name is None:
        platform_name = sys.platform

    # Map platform to venv suffix
    platform_suffix = {
        "win32": "venv",  # Windows keeps default name for backwards compatibility
        "darwin": "venv_mac",
        "linux": "venv_linux",
    }

    suffix = platform_suffix.get(platform_name, f"venv_{platform_name}")
    return PROJECT_ROOT / "python" / suffix


# Default to current platform
VENV_DIR = get_venv_dir()

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

# Known problematic packages and their fallback versions
FALLBACK_VERSIONS: dict[str, list[str]] = {
    "open3d": ["0.18.0", "0.17.0"],
    "PyOpenGL-accelerate": ["3.1.7", "3.1.6"],  # Often has build issues
    "pyenchant": ["3.2.2", "3.2.1"],  # May need system libraries
    "usd-core": ["24.11", "24.08"],  # Large package, version-specific
}

# Packages that may need --no-build-isolation
NO_BUILD_ISOLATION_PACKAGES = {"PyOpenGL-accelerate"}

# Packages that benefit from pre-built wheels (Windows)
WHEEL_PREFERRED_PACKAGES = {"open3d", "numpy", "pillow", "PyOpenGL-accelerate"}


class PackageCategory(Enum):
    """Package importance categories for installation order and error handling."""

    CRITICAL = "critical"  # App won't start without these
    REQUIRED = "required"  # Core functionality needs these
    THREED = "3d"  # 3D model support
    OPTIONAL = "optional"  # Nice to have, app works without


@dataclass
class PackageSpec:
    """Specification for a package to install."""

    name: str
    import_name: str  # Name to use for import verification
    category: PackageCategory
    version_spec: str = ""  # e.g., ">=1.0.0" or "==1.2.3"
    platform: str | None = None  # None = all platforms, "win32", "linux", "darwin"
    dependencies: list[str] = field(default_factory=list)  # Install these first
    notes: str = ""
    skip_import_check: bool = False  # Skip import verification (for build tools)

    @property
    def pip_spec(self) -> str:
        """Return the pip install specification."""
        return f"{self.name}{self.version_spec}" if self.version_spec else self.name


# Package definitions with categories and import names
PACKAGES: list[PackageSpec] = [
    # Critical - app won't start
    # Build tools: skip import check (they work but have deprecation warnings on Python 3.10+)
    PackageSpec("pip", "pip", PackageCategory.CRITICAL, notes="Upgrade first", skip_import_check=True),
    PackageSpec("wheel", "wheel", PackageCategory.CRITICAL, notes="For building packages", skip_import_check=True),
    PackageSpec("setuptools", "setuptools", PackageCategory.CRITICAL, notes="Build system", skip_import_check=True),
    PackageSpec("PySide6", "PySide6", PackageCategory.CRITICAL, ">=6.6.0"),
    PackageSpec("numpy", "numpy", PackageCategory.CRITICAL, ">=1.26.4"),
    PackageSpec("pillow", "PIL", PackageCategory.CRITICAL, ">=12.1.0"),
    # Required - core functionality
    PackageSpec("shiboken6", "shiboken6", PackageCategory.REQUIRED, notes="PySide6 runtime"),
    PackageSpec("QDarkStyle", "qdarkstyle", PackageCategory.REQUIRED, "==3.2.3"),
    PackageSpec("QtPy", "qtpy", PackageCategory.REQUIRED, "==2.4.2"),
    PackageSpec("fileseq", "fileseq", PackageCategory.REQUIRED, "==2.1.2"),
    PackageSpec("six", "six", PackageCategory.REQUIRED, ">=1.16.0"),
    PackageSpec("typing_extensions", "typing_extensions", PackageCategory.REQUIRED, ">=4.12.2"),
    PackageSpec("packaging", "packaging", PackageCategory.REQUIRED, ">=24.1"),
    PackageSpec("pywin32", "win32api", PackageCategory.REQUIRED, "==308", platform="win32"),
    # 3D Model Support
    PackageSpec("PyOpenGL", "OpenGL", PackageCategory.THREED, ">=3.1.0"),
    PackageSpec(
        "PyOpenGL-accelerate",
        "OpenGL_accelerate",
        PackageCategory.THREED,
        ">=3.1.10",
        platform="win32",  # Often fails to build on Mac/Linux, not critical
        notes="Windows only - OpenGL still works without it on Mac/Linux",
    ),
    PackageSpec(
        "trimesh", "trimesh", PackageCategory.THREED, ">=4.10.1", dependencies=["networkx", "freetype-py"]
    ),
    PackageSpec("networkx", "networkx", PackageCategory.THREED, ">=3.4.2"),
    PackageSpec("freetype-py", "freetype", PackageCategory.THREED, ">=2.5.1"),
    PackageSpec("open3d", "open3d", PackageCategory.THREED, ">=0.18.0", notes="Large package, may take time"),
    PackageSpec("usd-core", "pxr", PackageCategory.THREED, ">=25.11", notes="USD support"),
    # Optional
    PackageSpec(
        "pyenchant",
        "enchant",
        PackageCategory.OPTIONAL,
        ">=3.3.0",
        notes="Spell checking - macOS: brew install enchant; Linux: apt install libenchant-2-dev",
    ),
    PackageSpec("ayon-python-api", "ayon_api", PackageCategory.OPTIONAL, ">=1.2.4", notes="AYON integration"),
    PackageSpec("pytest", "pytest", PackageCategory.OPTIONAL, notes="Testing framework"),
]


# =============================================================================
# Terminal Colors (cross-platform)
# =============================================================================


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"

    @classmethod
    def enable(cls) -> None:
        """Enable ANSI colors on Windows."""
        if platform.system() == "Windows":
            # Enable ANSI escape codes on Windows 10+
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                # Fallback: disable colors
                cls._disable_colors()

    @classmethod
    def _disable_colors(cls) -> None:
        """Disable all colors (set to empty strings)."""
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith("_"):
                setattr(cls, attr, "")


class Symbols:
    """Unicode/ASCII symbols for terminal output."""

    # Unicode versions
    CHECK = "✓"
    CROSS = "✗"
    WARNING = "⚠"
    INFO = "ℹ"
    BLOCK_FULL = "█"
    BLOCK_EMPTY = "░"

    @classmethod
    def enable(cls) -> None:
        """Test if Unicode works and fall back to ASCII if not."""
        if platform.system() == "Windows":
            # Try to enable UTF-8 mode
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # Try to set console output to UTF-8 (code page 65001)
                kernel32.SetConsoleOutputCP(65001)
            except Exception:
                pass

        # Test if Unicode actually works
        try:
            # Try printing a Unicode character
            test_str = cls.CHECK
            test_str.encode(sys.stdout.encoding or 'utf-8')
        except (UnicodeEncodeError, LookupError):
            # Fall back to ASCII
            cls._use_ascii()

    @classmethod
    def _use_ascii(cls) -> None:
        """Switch to ASCII-safe symbols."""
        cls.CHECK = "+"
        cls.CROSS = "x"
        cls.WARNING = "!"
        cls.INFO = "i"
        cls.BLOCK_FULL = "#"
        cls.BLOCK_EMPTY = "-"


def safe_print(text: str) -> None:
    """Print text, handling encoding errors gracefully."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fall back to ASCII-safe version
        ascii_text = text.encode('ascii', errors='replace').decode('ascii')
        print(ascii_text)


def print_header(text: str) -> None:
    """Print a section header."""
    width = 70
    safe_print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * width}")
    safe_print(f" {text}")
    safe_print(f"{'=' * width}{Colors.RESET}\n")


def print_step(step: int, text: str) -> None:
    """Print a step indicator."""
    safe_print(f"\n{Colors.YELLOW}{Colors.BOLD}[Step {step}]{Colors.RESET} {text}")


def print_success(text: str) -> None:
    """Print success message."""
    safe_print(f"  {Colors.GREEN}{Symbols.CHECK}{Colors.RESET} {text}")


def print_warning(text: str) -> None:
    """Print warning message."""
    safe_print(f"  {Colors.YELLOW}{Symbols.WARNING}{Colors.RESET} {text}")


def print_error(text: str) -> None:
    """Print error message."""
    safe_print(f"  {Colors.RED}{Symbols.CROSS}{Colors.RESET} {text}")


def print_info(text: str) -> None:
    """Print info message."""
    safe_print(f"  {Colors.BLUE}{Symbols.INFO}{Colors.RESET} {text}")


def print_progress(current: int, total: int, name: str, status: str = "") -> None:
    """Print progress bar."""
    bar_width = 30
    filled = int(bar_width * current / total)
    bar = Symbols.BLOCK_FULL * filled + Symbols.BLOCK_EMPTY * (bar_width - filled)
    status_text = f" - {status}" if status else ""
    try:
        print(f"\r  [{bar}] {current}/{total} {name}{status_text}".ljust(80), end="", flush=True)
    except UnicodeEncodeError:
        # ASCII fallback
        bar = "#" * filled + "-" * (bar_width - filled)
        print(f"\r  [{bar}] {current}/{total} {name}{status_text}".ljust(80), end="", flush=True)


# =============================================================================
# Installation Strategies
# =============================================================================


@dataclass
class InstallResult:
    """Result of a package installation attempt."""

    success: bool
    package: str
    strategy: str
    error: str | None = None
    output: str = ""


class InstallStrategy:
    """Base class for installation strategies."""

    name: str = "base"

    def install(self, pip_exe: Path, package_spec: str, **kwargs) -> InstallResult:
        """Attempt to install a package."""
        raise NotImplementedError


class StandardInstall(InstallStrategy):
    """Standard pip install."""

    name = "standard"

    def install(self, pip_exe: Path, package_spec: str, **kwargs) -> InstallResult:
        cmd = [str(pip_exe), "install", package_spec]
        return _run_pip_install(cmd, package_spec, self.name)


class NoCacheInstall(InstallStrategy):
    """Install with --no-cache-dir (for corrupted cache issues)."""

    name = "no-cache"

    def install(self, pip_exe: Path, package_spec: str, **kwargs) -> InstallResult:
        cmd = [str(pip_exe), "install", "--no-cache-dir", package_spec]
        return _run_pip_install(cmd, package_spec, self.name)


class NoDepsInstall(InstallStrategy):
    """Install with --no-deps (for dependency conflicts)."""

    name = "no-deps"

    def install(self, pip_exe: Path, package_spec: str, **kwargs) -> InstallResult:
        cmd = [str(pip_exe), "install", "--no-deps", package_spec]
        return _run_pip_install(cmd, package_spec, self.name)


class FallbackVersionInstall(InstallStrategy):
    """Try installing older known-good versions."""

    name = "fallback-version"

    def install(self, pip_exe: Path, package_spec: str, **kwargs) -> InstallResult:
        # Extract package name (without version spec)
        pkg_name = package_spec.split(">=")[0].split("==")[0].split("<")[0].split(">")[0]

        fallback_versions = kwargs.get("fallback_versions", FALLBACK_VERSIONS.get(pkg_name, []))

        for version in fallback_versions:
            print_info(f"Trying fallback version: {pkg_name}=={version}")
            cmd = [str(pip_exe), "install", f"{pkg_name}=={version}"]
            result = _run_pip_install(cmd, f"{pkg_name}=={version}", self.name)
            if result.success:
                return result

        return InstallResult(
            success=False, package=package_spec, strategy=self.name, error="All fallback versions failed"
        )


class NoBuildIsolationInstall(InstallStrategy):
    """Install with --no-build-isolation (for packages with build issues)."""

    name = "no-build-isolation"

    def install(self, pip_exe: Path, package_spec: str, **kwargs) -> InstallResult:
        cmd = [str(pip_exe), "install", "--no-build-isolation", package_spec]
        return _run_pip_install(cmd, package_spec, self.name)


class PrebuiltWheelInstall(InstallStrategy):
    """Prefer pre-built wheels (--only-binary :all:)."""

    name = "prebuilt-wheel"

    def install(self, pip_exe: Path, package_spec: str, **kwargs) -> InstallResult:
        pkg_name = package_spec.split(">=")[0].split("==")[0].split("<")[0].split(">")[0]
        cmd = [str(pip_exe), "install", "--only-binary", pkg_name, package_spec]
        return _run_pip_install(cmd, package_spec, self.name)


def _run_pip_install(cmd: list[str], package_spec: str, strategy_name: str) -> InstallResult:
    """Run a pip install command and return the result."""
    try:
        # Create startup info to hide console window on Windows
        startupinfo = None
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for large packages
            startupinfo=startupinfo,
        )

        if result.returncode == 0:
            return InstallResult(success=True, package=package_spec, strategy=strategy_name, output=result.stdout)
        else:
            return InstallResult(
                success=False,
                package=package_spec,
                strategy=strategy_name,
                error=result.stderr or result.stdout,
                output=result.stdout,
            )
    except subprocess.TimeoutExpired:
        return InstallResult(
            success=False, package=package_spec, strategy=strategy_name, error="Installation timed out (10 minutes)"
        )
    except Exception as e:
        return InstallResult(success=False, package=package_spec, strategy=strategy_name, error=str(e))


def get_strategies_for_package(pkg: PackageSpec) -> list[InstallStrategy]:
    """Get the ordered list of installation strategies for a package."""
    strategies: list[InstallStrategy] = [StandardInstall()]

    # Add wheel-first strategy for packages that benefit from it
    if pkg.name in WHEEL_PREFERRED_PACKAGES and platform.system() == "Windows":
        strategies.insert(0, PrebuiltWheelInstall())

    # Standard retry strategies
    strategies.extend([NoCacheInstall()])

    # Add fallback versions if available
    if pkg.name in FALLBACK_VERSIONS:
        strategies.append(FallbackVersionInstall())

    # Add no-build-isolation for specific packages
    if pkg.name in NO_BUILD_ISOLATION_PACKAGES:
        strategies.append(NoBuildIsolationInstall())

    # Last resort: no-deps (may break functionality but at least installs)
    if pkg.category in (PackageCategory.OPTIONAL, PackageCategory.THREED):
        strategies.append(NoDepsInstall())

    return strategies


# =============================================================================
# Venv Management
# =============================================================================


def _rmtree_onerror(func: Callable, path: str, exc_info) -> None:
    """Error handler for shutil.rmtree to handle long paths and locked files."""
    import stat

    # Try to handle permission errors by making file writable
    if isinstance(exc_info[1], PermissionError):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
            return
        except Exception:
            pass

    # For FileNotFoundError with long paths, just ignore (already deleted or path issue)
    if isinstance(exc_info[1], FileNotFoundError):
        return

    # For other OSError, try long path prefix on Windows
    if isinstance(exc_info[1], OSError) and platform.system() == "Windows":
        try:
            # Try with long path prefix
            if not path.startswith("\\\\?\\"):
                long_path = "\\\\?\\" + os.path.abspath(path)
                func(long_path)
                return
        except Exception:
            pass

    # Re-raise if we couldn't handle it
    raise exc_info[1]


def remove_venv(venv_path: Path, force: bool = False) -> bool:
    """Remove existing virtual environment."""
    if not venv_path.exists():
        print_info("No existing venv found.")
        return True

    print_info(f"Removing existing venv at {venv_path}...")

    # Platform-specific optimized removal
    if platform.system() == "Windows":
        # On Windows, try using robocopy /MIR trick for stubborn directories
        # This handles long paths and locked files better than shutil
        try:
            with tempfile.TemporaryDirectory() as empty_dir:
                # robocopy /MIR mirrors empty dir to target, effectively deleting everything
                result = subprocess.run(
                    ["robocopy", empty_dir, str(venv_path), "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np"],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )
                # robocopy returns various codes, 0-7 are success
                if result.returncode <= 7:
                    # Now remove the empty directory
                    try:
                        venv_path.rmdir()
                    except Exception:
                        # Try rd /s /q as backup
                        subprocess.run(["cmd", "/c", "rd", "/s", "/q", str(venv_path)], capture_output=True)

                    if not venv_path.exists():
                        print_success("Venv removed successfully (robocopy).")
                        return True
        except Exception as e:
            print_warning(f"Robocopy method failed: {e}, trying shutil...")

    elif platform.system() == "Darwin" or platform.system() == "Linux":
        # On Mac/Linux, try rm -rf first (handles most cases well)
        try:
            result = subprocess.run(
                ["rm", "-rf", str(venv_path)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if not venv_path.exists():
                print_success("Venv removed successfully (rm -rf).")
                return True
        except Exception as e:
            print_warning(f"rm -rf failed: {e}, trying shutil...")

    # Try normal removal with error handler (cross-platform fallback)
    try:
        shutil.rmtree(venv_path, onerror=_rmtree_onerror)
        if not venv_path.exists():
            print_success("Venv removed successfully.")
            return True
    except PermissionError as e:
        if not force:
            print_error(f"Permission denied: {e}")
            print_warning("Close all Python processes using this venv and try again.")
            print_warning("Or use --clean flag to force removal.")
            return False
    except Exception as e:
        print_warning(f"Standard removal failed: {e}")

    # Platform-specific force removal
    if platform.system() == "Windows":
        print_warning("Attempting force removal with rd /s /q...")
        try:
            # Try rd /s /q which handles long paths better
            result = subprocess.run(
                ["cmd", "/c", "rd", "/s", "/q", str(venv_path)],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if not venv_path.exists():
                print_success("Venv removed successfully (rd).")
                return True

            # If still exists, try with retries
            for attempt in range(3):
                time.sleep(2)
                print_info(f"Retry {attempt + 1}/3...")
                subprocess.run(
                    ["cmd", "/c", "rd", "/s", "/q", str(venv_path)],
                    capture_output=True,
                    text=True,
                )
                if not venv_path.exists():
                    print_success("Venv removed successfully (rd retry).")
                    return True

            print_error("Could not remove venv even with force.")
            print_warning("Please manually delete the venv folder and try again.")
            return False
        except Exception as e:
            print_error(f"Force removal failed: {e}")
            return False

    elif platform.system() in ("Darwin", "Linux"):
        # On Mac/Linux, try sudo rm -rf if force is enabled
        if force:
            print_warning("Attempting force removal with sudo...")
            try:
                result = subprocess.run(
                    ["sudo", "rm", "-rf", str(venv_path)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if not venv_path.exists():
                    print_success("Venv removed successfully (sudo rm -rf).")
                    return True
            except Exception as e:
                print_error(f"Force removal failed: {e}")

        print_error("Could not remove venv.")
        print_warning("Try: sudo rm -rf " + str(venv_path))
        return False

    return False


def create_venv(venv_path: Path) -> bool:
    """Create a fresh virtual environment."""
    print_info(f"Creating venv at {venv_path}...")

    try:
        # Use the current Python to create venv
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print_error(f"Failed to create venv: {result.stderr}")
            return False

        print_success("Venv created successfully.")
        return True
    except Exception as e:
        print_error(f"Exception creating venv: {e}")
        return False


def get_pip_exe(venv_path: Path) -> Path:
    """Get the path to pip executable in the venv."""
    if platform.system() == "Windows":
        return venv_path / "Scripts" / "pip.exe"
    else:
        return venv_path / "bin" / "pip"


def get_python_exe(venv_path: Path) -> Path:
    """Get the path to Python executable in the venv."""
    if platform.system() == "Windows":
        return venv_path / "Scripts" / "python.exe"
    else:
        return venv_path / "bin" / "python"


# =============================================================================
# Package Installation
# =============================================================================


def should_install_package(pkg: PackageSpec) -> bool:
    """Check if a package should be installed on this platform."""
    if pkg.platform is None:
        return True
    return sys.platform == pkg.platform


def install_package(pip_exe: Path, pkg: PackageSpec) -> tuple[bool, str]:
    """
    Install a package with retry logic and multiple strategies.

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not should_install_package(pkg):
        return True, f"Skipped (platform: {pkg.platform})"

    strategies = get_strategies_for_package(pkg)

    for attempt, strategy in enumerate(strategies, 1):
        if attempt > 1:
            print_info(f"Retry {attempt}/{len(strategies)} using strategy: {strategy.name}")
            time.sleep(RETRY_DELAY_SECONDS)

        result = strategy.install(pip_exe, pkg.pip_spec, fallback_versions=FALLBACK_VERSIONS.get(pkg.name, []))

        if result.success:
            return True, f"Installed via {result.strategy}"

        # Log the error for debugging
        if result.error:
            # Truncate long error messages
            error_preview = result.error[:200] + "..." if len(result.error) > 200 else result.error
            print_warning(f"Strategy '{strategy.name}' failed: {error_preview}")

    return False, f"All {len(strategies)} strategies failed"


def install_packages(pip_exe: Path, packages: list[PackageSpec], skip_optional: bool = False) -> dict[str, bool]:
    """
    Install all packages with progress tracking.

    Returns:
        Dict mapping package names to success status.
    """
    results: dict[str, bool] = {}

    # Filter by category if skipping optional
    if skip_optional:
        packages = [p for p in packages if p.category != PackageCategory.OPTIONAL]

    # Sort by category priority
    category_order = {
        PackageCategory.CRITICAL: 0,
        PackageCategory.REQUIRED: 1,
        PackageCategory.THREED: 2,
        PackageCategory.OPTIONAL: 3,
    }
    packages = sorted(packages, key=lambda p: category_order[p.category])

    total = len(packages)
    failed_critical = []
    failed_required = []
    failed_optional = []

    for i, pkg in enumerate(packages, 1):
        # Print progress
        print_progress(i, total, pkg.name, "installing...")
        print()  # New line after progress bar

        # Check platform
        if not should_install_package(pkg):
            print_info(f"{pkg.name}: Skipped (not for {sys.platform})")
            results[pkg.name] = True
            continue

        # Show notes if any
        if pkg.notes:
            print_info(f"Note: {pkg.notes}")

        # Install
        success, message = install_package(pip_exe, pkg)
        results[pkg.name] = success

        if success:
            print_success(f"{pkg.name}: {message}")
        else:
            print_error(f"{pkg.name}: {message}")

            # Track failures by category
            if pkg.category == PackageCategory.CRITICAL:
                failed_critical.append(pkg.name)
            elif pkg.category == PackageCategory.REQUIRED:
                failed_required.append(pkg.name)
            else:
                failed_optional.append(pkg.name)

    # Summary
    print()
    if failed_critical:
        print_error(f"CRITICAL failures: {', '.join(failed_critical)}")
        print_error("The application will NOT work without these packages!")
    if failed_required:
        print_warning(f"Required failures: {', '.join(failed_required)}")
        print_warning("Some features may not work.")
    if failed_optional:
        print_info(f"Optional failures: {', '.join(failed_optional)}")
        print_info("These are optional and the app will work without them.")

    return results


# =============================================================================
# Import Verification
# =============================================================================


def verify_imports(python_exe: Path, packages: list[PackageSpec]) -> dict[str, bool]:
    """
    Verify that all packages can be imported.

    Uses a temp file approach for robustness (avoids command-line length limits).

    Returns:
        Dict mapping package names to import success status.
    """
    results: dict[str, bool] = {}

    # Filter packages for this platform, excluding those that skip import check
    packages_to_test = [
        pkg for pkg in packages
        if should_install_package(pkg) and not pkg.skip_import_check
    ]

    if not packages_to_test:
        return results

    # Build verification script
    script_content = '''#!/usr/bin/env python3
"""Import verification script - auto-generated."""
import sys

packages = {packages_dict}

results = {{}}
for pkg_name, import_name in packages.items():
    try:
        __import__(import_name)
        results[pkg_name] = True
        print(f"IMPORT_RESULT:{{pkg_name}}:OK")
    except ImportError as e:
        results[pkg_name] = False
        print(f"IMPORT_RESULT:{{pkg_name}}:FAIL")
        print(f"IMPORT_FAIL:{{pkg_name}}:{{e}}", file=sys.stderr)
    except Exception as e:
        results[pkg_name] = False
        print(f"IMPORT_RESULT:{{pkg_name}}:FAIL")
        print(f"IMPORT_ERROR:{{pkg_name}}:{{e}}", file=sys.stderr)

# Summary
ok_count = sum(1 for v in results.values() if v)
print(f"IMPORT_SUMMARY:{{ok_count}}/{{len(results)}}")
'''.format(packages_dict=repr({pkg.name: pkg.import_name for pkg in packages_to_test}))

    # Write to temp file
    script_file = None
    try:
        # Create temp file in a safe location
        fd, script_path = tempfile.mkstemp(suffix=".py", prefix="verify_imports_")
        script_file = Path(script_path)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(script_content)

        # Set up environment with PYTHONPATH
        env = os.environ.copy()
        pythonpath_parts = [
            str(PROJECT_ROOT / "python"),
            str(PROJECT_ROOT / "resources" / "ui"),
        ]
        existing_path = env.get("PYTHONPATH", "")
        if existing_path:
            pythonpath_parts.append(existing_path)
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

        # Run the verification script
        result = subprocess.run(
            [str(python_exe), str(script_file)],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            cwd=str(PROJECT_ROOT),  # Run from project dir
        )

        # Debug: show any unexpected output
        if result.returncode != 0:
            print_warning(f"Verification script returned code {result.returncode}")

        # Parse results from stdout
        for line in result.stdout.splitlines():
            if line.startswith("IMPORT_RESULT:"):
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    _, name, status = parts
                    results[name] = status == "OK"

        # Log any import failures from stderr
        for line in result.stderr.splitlines():
            if line.startswith("IMPORT_FAIL:") or line.startswith("IMPORT_ERROR:"):
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    _, name, error = parts
                    print_warning(f"Import error for {name}: {error}")
            elif line.strip() and not line.startswith("["):
                # Log other errors (but skip pip notices)
                print_warning(f"Verification stderr: {line}")

    except subprocess.TimeoutExpired:
        print_error("Import verification timed out!")
        return {pkg.name: False for pkg in packages_to_test}
    except Exception as e:
        print_error(f"Import verification failed: {e}")
        import traceback
        print_warning(traceback.format_exc())
        return {pkg.name: False for pkg in packages_to_test}
    finally:
        # Clean up temp file
        if script_file and script_file.exists():
            try:
                script_file.unlink()
            except Exception:
                pass

    return results


def print_verification_results(results: dict[str, bool], packages: list[PackageSpec]) -> None:
    """Print import verification results in a nice format."""
    # Group by category
    by_category: dict[PackageCategory, list[tuple[str, bool, bool]]] = {cat: [] for cat in PackageCategory}

    for pkg in packages:
        if not should_install_package(pkg):
            continue
        if pkg.skip_import_check:
            # Mark as skipped (True success, but show differently)
            by_category[pkg.category].append((pkg.name, True, True))  # name, success, skipped
        elif pkg.name in results:
            by_category[pkg.category].append((pkg.name, results[pkg.name], False))

    category_labels = {
        PackageCategory.CRITICAL: "Critical",
        PackageCategory.REQUIRED: "Required",
        PackageCategory.THREED: "3D Support",
        PackageCategory.OPTIONAL: "Optional",
    }

    for category in PackageCategory:
        items = by_category[category]
        if not items:
            continue

        safe_print(f"\n  {Colors.BOLD}{category_labels[category]}:{Colors.RESET}")
        for name, success, skipped in items:
            if skipped:
                safe_print(f"    {Colors.DIM}-{Colors.RESET} {name} {Colors.DIM}(build tool){Colors.RESET}")
            elif success:
                safe_print(f"    {Colors.GREEN}{Symbols.CHECK}{Colors.RESET} {name}")
            else:
                safe_print(f"    {Colors.RED}{Symbols.CROSS}{Colors.RESET} {name}")


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Main entry point."""
    Colors.enable()
    Symbols.enable()

    parser = argparse.ArgumentParser(
        description="Recreate Luma Tools virtual environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python recreate_venv.py              # Full install for current platform
  python recreate_venv.py --clean      # Force remove locked venv first
  python recreate_venv.py --verify-only    # Just test imports
  python recreate_venv.py --skip-optional  # Faster, skip optional packages

Platform-specific venvs:
  Windows: python/venv/
  macOS:   python/venv_mac/
  Linux:   python/venv_linux/
""",
    )
    parser.add_argument("--clean", action="store_true", help="Force remove existing venv")
    parser.add_argument("--verify-only", action="store_true", help="Only verify imports")
    parser.add_argument("--skip-optional", action="store_true", help="Skip optional packages")
    args = parser.parse_args()

    # Recalculate VENV_DIR based on current platform (already done at module load)
    global VENV_DIR
    VENV_DIR = get_venv_dir()

    print_header("Luma Tools - Virtual Environment Setup")

    print(f"  Python:     {sys.version}")
    print(f"  Executable: {sys.executable}")
    print(f"  Platform:   {platform.system()} {platform.machine()}")
    print(f"  Venv path:  {VENV_DIR}")

    # Verify-only mode
    if args.verify_only:
        print_step(1, "Verifying imports...")

        if not VENV_DIR.exists():
            print_error("Venv does not exist! Run without --verify-only first.")
            return 1

        python_exe = get_python_exe(VENV_DIR)
        results = verify_imports(python_exe, PACKAGES)
        print_verification_results(results, PACKAGES)

        # Critical packages: skipped ones count as OK, others must import successfully
        all_critical_ok = all(
            pkg.skip_import_check or results.get(pkg.name, False)
            for pkg in PACKAGES
            if pkg.category == PackageCategory.CRITICAL and should_install_package(pkg)
        )

        if all_critical_ok:
            print_header("Verification Complete - All Critical Imports OK")
            return 0
        else:
            print_header("Verification Failed - Critical Imports Missing")
            return 1

    # Step 1: Remove existing venv
    step = 1
    print_step(step, "Removing existing virtual environment...")
    if not remove_venv(VENV_DIR, force=args.clean):
        return 1

    # Step 2: Create fresh venv
    step += 1
    print_step(step, "Creating fresh virtual environment...")
    if not create_venv(VENV_DIR):
        return 1

    # Get pip and python executables
    pip_exe = get_pip_exe(VENV_DIR)
    python_exe = get_python_exe(VENV_DIR)

    if not pip_exe.exists():
        print_error(f"pip not found at {pip_exe}")
        return 1

    # Step 3: Install packages
    step += 1
    print_step(step, "Installing packages...")
    install_results = install_packages(pip_exe, PACKAGES, skip_optional=args.skip_optional)

    # Step 4: List installed packages
    step += 1
    print_step(step, "Installed packages:")
    subprocess.run([str(pip_exe), "list"], check=False)

    # Step 5: Verify imports
    step += 1
    print_step(step, "Verifying imports...")
    import_results = verify_imports(python_exe, PACKAGES)
    print_verification_results(import_results, PACKAGES)

    # Final summary
    total_packages = len([p for p in PACKAGES if should_install_package(p)])
    installed_ok = sum(1 for v in install_results.values() if v)

    # Count imports, excluding skipped packages
    tested_packages = [p for p in PACKAGES if should_install_package(p) and not p.skip_import_check]
    skipped_packages = [p for p in PACKAGES if should_install_package(p) and p.skip_import_check]
    imports_ok = sum(1 for v in import_results.values() if v)
    total_tested = len(tested_packages)

    # Critical packages: skipped ones count as OK, others must import successfully
    critical_packages = [p for p in PACKAGES if p.category == PackageCategory.CRITICAL and should_install_package(p)]
    critical_ok = all(
        p.skip_import_check or import_results.get(p.name, False)
        for p in critical_packages
    )

    print_header("Summary")
    safe_print(f"  Packages:        {installed_ok}/{total_packages} installed")
    if skipped_packages:
        safe_print(f"  Imports:         {imports_ok}/{total_tested} verified ({len(skipped_packages)} build tools skipped)")
    else:
        safe_print(f"  Imports:         {imports_ok}/{total_tested} verified")

    if critical_ok:
        safe_print(f"\n  {Colors.GREEN}{Colors.BOLD}{Symbols.CHECK} All critical packages OK - Luma Tools should work!{Colors.RESET}")
        print_header("Setup Complete!")
        return 0
    else:
        safe_print(f"\n  {Colors.RED}{Colors.BOLD}{Symbols.CROSS} Critical packages missing - Luma Tools will NOT work!{Colors.RESET}")
        print_warning("Please check the errors above and try again.")
        print_header("Setup Failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
