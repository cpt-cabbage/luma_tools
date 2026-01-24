"""Pytest configuration for Luma Tools tests."""
import sys
import os
from pathlib import Path

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


# Configure pytest collection to skip problematic modules
def pytest_ignore_collect(collection_path: Path, config):
    """Skip collecting tests that require modules with broken dependencies."""
    name = collection_path.name

    # Skip animation controller and loaders tests if numpy is broken
    # (these can be re-enabled when the venv is fixed)
    if not NUMPY_WORKS:
        if 'test_animation' in name or 'test_loaders' in name:
            return True
    return False
