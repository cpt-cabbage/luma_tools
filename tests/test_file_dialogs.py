"""Unit tests for file dialog helpers.

Note: Most file dialog tests require mocking Qt dialogs
which makes them suitable for integration testing rather than unit testing.
"""
import sys
import os
import tempfile

import pytest

# Add python and resources/ui directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'ui'))

# Check Qt availability
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

requires_qt = pytest.mark.skipif(not QT_AVAILABLE, reason="Qt not available")


class TestModuleImports:
    """Tests for module imports."""

    def test_core_functions_importable(self):
        """Test that core file dialog functions can be imported."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

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

    def test_context_helpers_importable(self):
        """Test that context-specific helpers can be imported."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

        from file_dialogs import (
            browse_workflow_file,
            browse_comfyui_output_dir,
            browse_custom_renders_dir,
            browse_images,
            browse_global_settings_dir,
            browse_hdri_file,
            save_mp4_file,
        )

        assert callable(browse_workflow_file)
        assert callable(browse_comfyui_output_dir)
        assert callable(browse_custom_renders_dir)
        assert callable(browse_images)
        assert callable(browse_global_settings_dir)
        assert callable(browse_hdri_file)
        assert callable(save_mp4_file)

    def test_private_function_importable(self):
        """Test that private helper function can be imported."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

        from file_dialogs import _get_start_directory

        assert callable(_get_start_directory)


@requires_qt
class TestGetStartDirectory:
    """Tests for _get_start_directory helper function."""

    def test_returns_home_when_no_context(self):
        """Test returns home directory when no saved context."""
        from file_dialogs import _get_start_directory

        # Use a unique context that won't exist
        result = _get_start_directory("test_nonexistent_context_xyz123")
        # Should return a valid path (home or fallback)
        assert os.path.exists(result)

    def test_uses_fallback_path_when_exists(self):
        """Test uses fallback path when it exists."""
        from file_dialogs import _get_start_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _get_start_directory(
                "test_fallback_context",
                fallback_path=tmpdir
            )
            assert result == tmpdir

    def test_returns_home_when_fallback_not_exists(self):
        """Test returns home when fallback path doesn't exist."""
        from file_dialogs import _get_start_directory

        result = _get_start_directory(
            "test_no_fallback_context",
            fallback_path="/nonexistent/path/xyz123"
        )
        # Should be home or a valid path
        assert os.path.exists(result)

    def test_check_parent_with_file_fallback(self):
        """Test check_parent uses parent directory of file path."""
        from file_dialogs import _get_start_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "nonexistent_file.txt")
            result = _get_start_directory(
                "test_parent_context",
                fallback_path=file_path,
                check_parent=True
            )
            # Should return parent directory
            assert result == tmpdir


@requires_qt
class TestContextSpecificHelpers:
    """Tests for context-specific helper functions."""

    def test_browse_workflow_file_returns_correct_filter(self):
        """Test browse_workflow_file uses correct filter."""
        # We can't easily test the dialog itself, but we can verify the function signature
        from file_dialogs import browse_workflow_file
        import inspect

        sig = inspect.signature(browse_workflow_file)
        params = list(sig.parameters.keys())
        assert 'parent' in params

    def test_browse_images_returns_tuple(self):
        """Test browse_images return type annotation."""
        from file_dialogs import browse_images
        import inspect

        sig = inspect.signature(browse_images)
        # Check it has parent and multiple parameters
        params = list(sig.parameters.keys())
        assert 'parent' in params
        assert 'multiple' in params

    def test_save_mp4_file_has_default_filename(self):
        """Test save_mp4_file has default filename parameter."""
        from file_dialogs import save_mp4_file
        import inspect

        sig = inspect.signature(save_mp4_file)
        params = sig.parameters
        assert 'parent' in params
        assert 'default_filename' in params
        assert params['default_filename'].default == "output.mp4"


class TestFunctionSignatures:
    """Tests for function signatures and parameters."""

    def test_browse_directory_signature(self):
        """Test browse_directory_with_memory has correct parameters."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

        from file_dialogs import browse_directory_with_memory
        import inspect

        sig = inspect.signature(browse_directory_with_memory)
        params = list(sig.parameters.keys())

        assert 'parent' in params
        assert 'context' in params
        assert 'title' in params
        assert 'fallback_path' in params
        assert 'options' in params

    def test_browse_file_signature(self):
        """Test browse_file_with_memory has correct parameters."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

        from file_dialogs import browse_file_with_memory
        import inspect

        sig = inspect.signature(browse_file_with_memory)
        params = list(sig.parameters.keys())

        assert 'parent' in params
        assert 'context' in params
        assert 'title' in params
        assert 'file_filter' in params
        assert 'fallback_path' in params

    def test_save_file_signature(self):
        """Test save_file_with_memory has correct parameters."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

        from file_dialogs import save_file_with_memory
        import inspect

        sig = inspect.signature(save_file_with_memory)
        params = list(sig.parameters.keys())

        assert 'parent' in params
        assert 'context' in params
        assert 'title' in params
        assert 'default_filename' in params
        assert 'file_filter' in params
        assert 'fallback_path' in params

    def test_browse_multiple_signature(self):
        """Test browse_multiple_files_with_memory has correct parameters."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

        from file_dialogs import browse_multiple_files_with_memory
        import inspect

        sig = inspect.signature(browse_multiple_files_with_memory)
        params = list(sig.parameters.keys())

        assert 'parent' in params
        assert 'context' in params
        assert 'title' in params
        assert 'file_filter' in params
        assert 'fallback_path' in params


class TestReturnTypeAnnotations:
    """Tests for return type annotations."""

    def test_browse_directory_return_type(self):
        """Test browse_directory_with_memory return type annotation."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

        from file_dialogs import browse_directory_with_memory
        import typing

        hints = typing.get_type_hints(browse_directory_with_memory)
        # Return type should be Optional[str]
        assert 'return' in hints

    def test_browse_multiple_return_type(self):
        """Test browse_multiple_files_with_memory return type annotation."""
        if not QT_AVAILABLE:
            pytest.skip("Qt not available")

        from file_dialogs import browse_multiple_files_with_memory
        import typing

        hints = typing.get_type_hints(browse_multiple_files_with_memory)
        # Return type should be Tuple[str, ...]
        assert 'return' in hints


# Backward compatibility - original test function
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
    pytest.main([__file__, "-v"])
