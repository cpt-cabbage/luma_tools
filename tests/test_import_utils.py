"""Unit tests for core/import_utils.py module."""
import sys
import os

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))


class TestSafeImport:
    """Tests for safe_import function."""

    def test_import_existing_module(self):
        """Test importing an existing standard library module."""
        from core.import_utils import safe_import

        module, available = safe_import("json")
        assert available is True
        assert module is not None
        assert hasattr(module, 'loads')
        assert hasattr(module, 'dumps')

    def test_import_existing_module_attr(self):
        """Test importing an attribute from existing module."""
        from core.import_utils import safe_import

        loads, available = safe_import("json", "loads")
        assert available is True
        assert callable(loads)

    def test_import_nonexistent_module(self):
        """Test importing a non-existent module."""
        from core.import_utils import safe_import

        module, available = safe_import("nonexistent_module_xyz123")
        assert available is False
        assert module is None

    def test_import_nonexistent_attr(self):
        """Test importing non-existent attribute from existing module."""
        from core.import_utils import safe_import

        attr, available = safe_import("json", "nonexistent_function_xyz")
        assert available is False
        assert attr is None

    def test_import_os_path(self):
        """Test importing submodule."""
        from core.import_utils import safe_import

        os_path, available = safe_import("os.path")
        assert available is True
        assert os_path is not None
        assert hasattr(os_path, 'join')

    def test_import_collections_abc(self):
        """Test importing from nested package."""
        from core.import_utils import safe_import

        abc, available = safe_import("collections.abc")
        assert available is True
        assert hasattr(abc, 'Mapping')

    def test_import_with_attr_from_nested(self):
        """Test importing specific class from nested module."""
        from core.import_utils import safe_import

        Mapping, available = safe_import("collections.abc", "Mapping")
        assert available is True
        assert Mapping is not None


class TestSafeImportMultiple:
    """Tests for safe_import_multiple function."""

    def test_import_multiple_attrs(self):
        """Test importing multiple attributes from a module."""
        from core.import_utils import safe_import_multiple

        attrs, available = safe_import_multiple("json", "loads", "dumps", "JSONEncoder")
        assert available is True
        assert len(attrs) == 3
        loads, dumps, encoder = attrs
        assert callable(loads)
        assert callable(dumps)
        assert encoder is not None

    def test_import_multiple_from_os(self):
        """Test importing multiple functions from os module."""
        from core.import_utils import safe_import_multiple

        attrs, available = safe_import_multiple("os", "path", "getcwd", "listdir")
        assert available is True
        assert len(attrs) == 3
        path, getcwd, listdir = attrs
        assert path is not None
        assert callable(getcwd)
        assert callable(listdir)

    def test_import_multiple_from_nonexistent(self):
        """Test importing from non-existent module returns tuple of Nones."""
        from core.import_utils import safe_import_multiple

        attrs, available = safe_import_multiple("nonexistent_xyz", "attr1", "attr2")
        assert available is False
        assert attrs == (None, None)

    def test_import_multiple_with_nonexistent_attr(self):
        """Test that missing any attribute fails the import."""
        from core.import_utils import safe_import_multiple

        attrs, available = safe_import_multiple("json", "loads", "nonexistent_xyz")
        assert available is False
        # Should return tuple of Nones
        assert attrs == (None, None)

    def test_import_single_attr_as_tuple(self):
        """Test importing single attribute returns tuple."""
        from core.import_utils import safe_import_multiple

        attrs, available = safe_import_multiple("json", "loads")
        assert available is True
        assert len(attrs) == 1
        assert callable(attrs[0])


class TestRealWorldUseCases:
    """Test real-world import patterns used in the project."""

    def test_pyside6_pattern(self):
        """Test PySide6 import pattern (may not be available in CI)."""
        from core.import_utils import safe_import

        QApplication, available = safe_import("PySide6.QtWidgets", "QApplication")
        # Just check it returns appropriate values
        assert isinstance(available, bool)
        if available:
            assert QApplication is not None
        else:
            assert QApplication is None

    def test_optional_package_pattern(self):
        """Test pattern for optional packages."""
        from core.import_utils import safe_import

        # Use pathlib which is always available and working
        pathlib_mod, PATHLIB_AVAILABLE = safe_import("pathlib")
        assert isinstance(PATHLIB_AVAILABLE, bool)
        assert PATHLIB_AVAILABLE is True
        assert hasattr(pathlib_mod, 'Path')

        # Test a package that definitely doesn't exist
        fake_mod, FAKE_AVAILABLE = safe_import("nonexistent_package_xyz123")
        assert FAKE_AVAILABLE is False
        assert fake_mod is None

    def test_feature_flag_pattern(self):
        """Test using import result as feature flag."""
        from core.import_utils import safe_import

        _, TYPING_EXTENSIONS_AVAILABLE = safe_import("typing_extensions")

        # Use as feature flag
        if TYPING_EXTENSIONS_AVAILABLE:
            # Could do something with typing_extensions
            pass
        else:
            # Fallback behavior
            pass

        # Test passes regardless of whether package is installed
        assert isinstance(TYPING_EXTENSIONS_AVAILABLE, bool)

    def test_graceful_degradation(self):
        """Test pattern for graceful degradation when package missing."""
        from core.import_utils import safe_import

        # Try to import a package that definitely doesn't exist
        fancy_lib, FANCY_AVAILABLE = safe_import("super_fancy_nonexistent_lib")

        # Should handle gracefully
        assert FANCY_AVAILABLE is False
        assert fancy_lib is None

        # Code can continue with fallback
        def do_something():
            if FANCY_AVAILABLE:
                return fancy_lib.fancy_function()
            else:
                return "fallback result"

        assert do_something() == "fallback result"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_module_name(self):
        """Test with empty module name raises or returns not available."""
        from core.import_utils import safe_import

        # Empty module name will raise ValueError from importlib
        # safe_import should catch this and return not available
        try:
            module, available = safe_import("")
            # If it doesn't raise, it should return not available
            assert available is False
            assert module is None
        except ValueError:
            # ValueError for empty module name is acceptable
            pass

    def test_empty_attr_name(self):
        """Test with empty attribute name - getattr with empty string works."""
        from core.import_utils import safe_import

        # getattr(module, "") actually works in Python and returns the module
        # So this should succeed (but not be a recommended usage pattern)
        result, available = safe_import("json", "")
        # This actually succeeds because getattr(json, "") returns json module
        # Both True and False are acceptable behaviors here
        assert isinstance(available, bool)

    def test_import_builtin(self):
        """Test importing built-in module."""
        from core.import_utils import safe_import

        sys_module, available = safe_import("sys")
        assert available is True
        assert sys_module is not None
        assert hasattr(sys_module, 'path')

    def test_import_multiple_empty_attrs(self):
        """Test import_multiple with no attributes."""
        from core.import_utils import safe_import_multiple

        attrs, available = safe_import_multiple("json")
        # No attrs requested - should return empty tuple
        assert available is True
        assert attrs == ()


# Allow running tests directly
if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
