"""Unit tests for core/utils.py module."""
import sys
import os
import tempfile
import json

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))


class TestGetTrailingNumber:
    """Tests for get_trailing_number function."""

    def test_simple_number(self):
        """Test extracting number from simple string."""
        from core.utils import get_trailing_number

        assert get_trailing_number("render_v003") == "003"
        assert get_trailing_number("shot_42") == "42"
        assert get_trailing_number("file123") == "123"

    def test_multiple_numbers(self):
        """Test extracting trailing number when multiple numbers exist."""
        from core.utils import get_trailing_number

        assert get_trailing_number("render_v001_pass_002") == "002"
        assert get_trailing_number("shot_10_v003_final_001") == "001"

    def test_padded_numbers(self):
        """Test extracting padded numbers."""
        from core.utils import get_trailing_number

        assert get_trailing_number("frame_0001") == "0001"
        assert get_trailing_number("render.0042.exr") == "0042"


class TestTruncateAtSuffix:
    """Tests for truncate_at_suffix function."""

    def test_basic_removal(self):
        """Test basic suffix removal."""
        from core.utils import truncate_at_suffix

        assert truncate_at_suffix("/path/to/file_v001/subfolder", "_v001") == "/path/to/file_v001"
        assert truncate_at_suffix("hello world hello", " world") == "hello world"

    def test_suffix_at_end(self):
        """Test when suffix is at the end."""
        from core.utils import truncate_at_suffix

        assert truncate_at_suffix("test_suffix", "_suffix") == "test_suffix"


class TestSubstringAfter:
    """Tests for substring_after function."""

    def test_basic_extraction(self):
        """Test basic substring extraction."""
        from core.utils import substring_after

        assert substring_after("hello:world", ":") == "world"
        assert substring_after("path/to/file", "/to/") == "file"

    def test_no_delimiter(self):
        """Test when delimiter not found."""
        from core.utils import substring_after

        assert substring_after("hello", ":") == ""

    def test_delimiter_at_end(self):
        """Test when delimiter is at end."""
        from core.utils import substring_after

        assert substring_after("hello:", ":") == ""


class TestNormalizePath:
    """Tests for normalize_path function."""

    def test_windows_path(self):
        """Test converting Windows backslashes to forward slashes."""
        from core.utils import normalize_path

        assert normalize_path("C:\\Users\\test\\file.txt") == "C:/Users/test/file.txt"
        assert normalize_path("L:\\tools\\folder") == "L:/tools/folder"

    def test_unix_path(self):
        """Test Unix paths remain unchanged."""
        from core.utils import normalize_path

        assert normalize_path("/home/user/file.txt") == "/home/user/file.txt"

    def test_mixed_path(self):
        """Test mixed slash paths."""
        from core.utils import normalize_path

        assert normalize_path("C:\\Users/test\\file.txt") == "C:/Users/test/file.txt"


class TestEnsureDirectory:
    """Tests for ensure_directory function."""

    def test_create_directory(self):
        """Test creating a new directory."""
        from core.utils import ensure_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "new_folder", "subfolder")
            ensure_directory(new_dir)
            assert os.path.isdir(new_dir)

    def test_existing_directory(self):
        """Test that existing directory doesn't raise error."""
        from core.utils import ensure_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            ensure_directory(tmpdir)  # Should not raise
            assert os.path.isdir(tmpdir)


class TestRemovePrefix:
    """Tests for remove_prefix function."""

    def test_prefix_exists(self):
        """Test removing existing prefix."""
        from core.utils import remove_prefix

        assert remove_prefix("hello_world", "hello_") == "world"
        assert remove_prefix("test_string", "test_") == "string"

    def test_prefix_not_exists(self):
        """Test when prefix doesn't exist."""
        from core.utils import remove_prefix

        assert remove_prefix("hello_world", "foo_") == "hello_world"

    def test_empty_prefix(self):
        """Test with empty prefix."""
        from core.utils import remove_prefix

        assert remove_prefix("hello", "") == "hello"


class TestRemoveSuffix:
    """Tests for remove_suffix function."""

    def test_suffix_exists(self):
        """Test removing existing suffix."""
        from core.utils import remove_suffix

        assert remove_suffix("hello_world", "_world") == "hello"
        assert remove_suffix("test.exr", ".exr") == "test"

    def test_suffix_not_exists(self):
        """Test when suffix doesn't exist."""
        from core.utils import remove_suffix

        assert remove_suffix("hello_world", "_foo") == "hello_world"

    def test_empty_suffix(self):
        """Test with empty suffix."""
        from core.utils import remove_suffix

        assert remove_suffix("hello", "") == "hello"


class TestLoadJson:
    """Tests for load_json function."""

    def test_load_valid_json(self):
        """Test loading valid JSON file."""
        from core.utils import load_json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "value", "number": 42}, f)
            temp_path = f.name

        try:
            result = load_json(temp_path)
            assert result == {"key": "value", "number": 42}
        finally:
            os.unlink(temp_path)

    def test_load_nonexistent_file(self):
        """Test loading non-existent file returns default."""
        from core.utils import load_json

        result = load_json("/nonexistent/path/file.json")
        assert result == {}

        result = load_json("/nonexistent/path/file.json", default={"default": True})
        assert result == {"default": True}

    def test_load_invalid_json(self):
        """Test loading invalid JSON returns default."""
        from core.utils import load_json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json {{{")
            temp_path = f.name

        try:
            result = load_json(temp_path, default={"error": True})
            assert result == {"error": True}
        finally:
            os.unlink(temp_path)


class TestSaveJson:
    """Tests for save_json function."""

    def test_save_json(self):
        """Test saving JSON file."""
        from core.utils import save_json, load_json

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            data = {"key": "value", "list": [1, 2, 3]}

            result = save_json(path, data)
            assert result is True
            assert os.path.exists(path)

            loaded = load_json(path)
            assert loaded == data

    def test_save_creates_directory(self):
        """Test that save_json creates parent directories."""
        from core.utils import save_json

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "new", "folder", "test.json")

            result = save_json(path, {"data": True})
            assert result is True
            assert os.path.exists(path)

    def test_save_without_pretty(self):
        """Test saving JSON without pretty formatting."""
        from core.utils import save_json

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")

            save_json(path, {"key": "value"}, pretty=False)

            with open(path, 'r') as f:
                content = f.read()
            # Not pretty printed should not have newlines
            assert '\n' not in content


class TestByteSize:
    """Tests for ByteSize class."""

    def test_bytes(self):
        """Test byte values."""
        from core.utils import ByteSize

        size = ByteSize(500)
        assert size.B == 500
        assert size.bytes == 500

    def test_kilobytes(self):
        """Test kilobyte conversion."""
        from core.utils import ByteSize

        size = ByteSize(1024)
        assert size.KB == 1.0
        assert size.kilobytes == 1.0

    def test_megabytes(self):
        """Test megabyte conversion."""
        from core.utils import ByteSize

        size = ByteSize(1024 * 1024)
        assert size.MB == 1.0
        assert size.megabytes == 1.0

    def test_gigabytes(self):
        """Test gigabyte conversion."""
        from core.utils import ByteSize

        size = ByteSize(1024 * 1024 * 1024)
        assert size.GB == 1.0
        assert size.gigabytes == 1.0

    def test_string_formatting(self):
        """Test string representation."""
        from core.utils import ByteSize

        size = ByteSize(1024 * 500)  # 500 KB
        str_repr = str(size)
        assert "KB" in str_repr

    def test_arithmetic(self):
        """Test arithmetic operations work (returns int, not ByteSize).

        ByteSize intentionally does not override arithmetic operators.
        The class is used for display formatting, not arithmetic chaining.
        """
        from core.utils import ByteSize

        a = ByteSize(1024)
        b = ByteSize(1024)

        # Arithmetic works but returns int (not ByteSize)
        assert a + b == 2048
        assert a - b == 0
        assert a * 2 == 2048


class TestPadFrameNumber:
    """Tests for pad_frame_number function."""

    def test_default_padding(self):
        """Test default 4-digit padding."""
        from core.utils import pad_frame_number

        assert pad_frame_number(1) == "0001"
        assert pad_frame_number(42) == "0042"
        assert pad_frame_number(999) == "0999"
        assert pad_frame_number(1000) == "1000"

    def test_custom_padding(self):
        """Test custom padding values."""
        from core.utils import pad_frame_number

        assert pad_frame_number(1, 2) == "01"
        assert pad_frame_number(1, 6) == "000001"
        assert pad_frame_number(42, 3) == "042"


class TestUpdatePathVersion:
    """Tests for update_path_version function."""

    def test_simple_version_update(self):
        """Test updating version in path."""
        from core.utils import update_path_version

        assert update_path_version("/render/shot_v001/file.exr", 5) == "/render/shot_v005/file.exr"
        assert update_path_version("/path_v003/to/file_v003.exr", 10) == "/path_v010/to/file_v010.exr"

    def test_no_version(self):
        """Test path without version remains unchanged."""
        from core.utils import update_path_version

        path = "/render/shot/file.exr"
        assert update_path_version(path, 5) == path


class TestExtractRenderName:
    """Tests for extract_render_name function."""

    def test_simple_extraction(self):
        """Test simple render name extraction."""
        from core.utils import extract_render_name

        assert extract_render_name("beauty_v001.0042.exr") == "beauty_v001"
        assert extract_render_name("render.0001.exr") == "render"

    def test_with_frame_padding(self):
        """Test extraction with frame padding markers."""
        from core.utils import extract_render_name

        assert extract_render_name("beauty_v001.####.exr", strip_frame_padding=True) == "beauty_v001"
        assert extract_render_name("render.####.exr", strip_frame_padding=True) == "render"

    def test_no_extension(self):
        """Test extraction without extension."""
        from core.utils import extract_render_name

        assert extract_render_name("render_name") == "render_name"


# Allow running tests directly
if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
