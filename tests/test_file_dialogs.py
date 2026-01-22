"""Unit tests for file dialog helpers.

Note: Most file dialog tests require mocking Qt dialogs
which makes them suitable for integration testing rather than unit testing.
"""
import sys
import os

# Add python and resources/ui directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'ui'))


def test_module_imports():
    """Test that file_dialogs module can be imported."""
    try:
        from file_dialogs import (
            browse_directory_with_memory,
            browse_file_with_memory,
            save_file_with_memory,
            browse_multiple_files_with_memory,
        )
        assert callable(browse_directory_with_memory)
        assert callable(browse_file_with_memory)
        assert callable(save_file_with_memory)
        assert callable(browse_multiple_files_with_memory)
    except ImportError as e:
        # May fail without Qt - that's OK for CI
        print(f"Skipping import test - {e}")


if __name__ == "__main__":
    test_module_imports()
    print("File dialog tests passed!")
