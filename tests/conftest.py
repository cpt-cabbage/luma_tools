"""Pytest configuration for Luma Tools tests."""
import sys
import os
from pathlib import Path

import pytest

# Set up Python paths for imports
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
python_dir = os.path.join(root_dir, 'python')
ui_dir = os.path.join(root_dir, 'resources', 'ui')

if python_dir not in sys.path:
    sys.path.insert(0, python_dir)
if ui_dir not in sys.path:
    sys.path.insert(0, ui_dir)


# Check if numpy is working
def _numpy_works():
    """Check if numpy can be imported without syntax errors."""
    try:
        import numpy
        return True
    except (ImportError, SyntaxError):
        return False


NUMPY_WORKS = _numpy_works()


@pytest.fixture(autouse=True)
def _isolate_settings_files(monkeypatch):
    """Point every settings path at a throwaway dir for the duration of each test.

    A test that reaches the real settings files can corrupt studio-wide
    configuration: a mocked-save test once wrote "/new/path" into the shared
    global_settings.json because the mock covered an internal save helper the
    write path no longer used. Redirecting the paths themselves means no
    amount of mock drift can escape onto the network share.

    settings_manager imports these names into its own namespace, so they are
    patched there (patching core.config alone would have no effect).
    Individual tests may still monkeypatch these to their own paths; the later
    patch simply wins.

    The directories deliberately live OUTSIDE pytest's ``tmp_path`` — tests
    that list their own tmp_path (fast_scandir, metadata leftovers) must not
    see this fixture's bookkeeping.
    """
    try:
        import core.settings_manager as sm
    except ImportError:
        yield  # settings_manager unavailable (e.g. broken venv) — nothing to guard
        return

    import shutil
    import tempfile

    sandbox = tempfile.mkdtemp(prefix="luma_settings_isolation_")
    settings_dir = os.path.join(sandbox, "user")
    global_dir = os.path.join(sandbox, "global")
    os.makedirs(settings_dir, exist_ok=True)
    os.makedirs(global_dir, exist_ok=True)

    monkeypatch.setattr(sm, "USER_SETTINGS_DIR", settings_dir, raising=False)
    monkeypatch.setattr(sm, "USER_SETTINGS_FILE", os.path.join(settings_dir, "settings.json"), raising=False)
    monkeypatch.setattr(sm, "DEFAULT_GLOBAL_SETTINGS_PATH", global_dir, raising=False)

    sm.clear_settings_cache()
    try:
        yield
    finally:
        sm.clear_settings_cache()
        shutil.rmtree(sandbox, ignore_errors=True)


def pytest_report_header(config):
    """Make a broken numpy LOUD in the run header.

    pytest_ignore_collect drops entire test modules with no skip marker —
    without this banner, a broken venv produced a fully green run while
    silently deleting all geo/loaders and animation coverage.
    """
    if not NUMPY_WORKS:
        return (
            "WARNING: numpy is BROKEN in this venv — test_animation_controller.py "
            "and test_loaders.py were NOT collected (0 tests from those modules). "
            "Fix the venv to restore geo/loaders coverage."
        )
    return None


# Configure pytest collection to skip problematic modules
def pytest_ignore_collect(collection_path: Path, config):
    """Skip collecting tests that require modules with broken dependencies."""
    name = collection_path.name

    # Skip animation controller and loaders tests if numpy is broken
    # (these can be re-enabled when the venv is fixed)
    if not NUMPY_WORKS:
        if 'test_animation' in name or 'test_loaders' in name:
            import warnings
            warnings.warn(
                f"Skipping ALL tests in {name}: numpy is broken in this venv",
                stacklevel=1,
            )
            return True
    return False
