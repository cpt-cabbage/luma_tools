"""Tests for core.validators — path/data validation utilities."""

import os

import pytest

from core.validators import (
    ValidationError,
    is_valid_path,
    is_valid_file,
    is_valid_directory,
    is_writable,
    is_readable,
    validate_file,
    validate_directory,
    validate_file_for_operation,
    validate_directory_for_operation,
    safe_list_dir,
    safe_file_stat,
    safe_path_join,
    validate_file_exists,
    validate_is_file,
    validate_is_directory,
)


# ============================================================================
# Boolean validators
# ============================================================================

class TestIsValidPath:
    def test_valid_string(self):
        assert is_valid_path("/some/path") is True
        assert is_valid_path("C:\\Windows") is True

    def test_empty_or_none(self):
        assert is_valid_path("") is False
        assert is_valid_path(None) is False

    def test_non_string(self):
        assert is_valid_path(123) is False
        assert is_valid_path([]) is False


class TestIsValidFile:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert is_valid_file(str(f)) is True

    def test_nonexistent(self):
        assert is_valid_file("/nonexistent/file.txt") is False

    def test_directory_returns_false(self, tmp_path):
        assert is_valid_file(str(tmp_path)) is False

    def test_empty(self):
        assert is_valid_file("") is False
        assert is_valid_file(None) is False


class TestIsValidDirectory:
    def test_existing_dir(self, tmp_path):
        assert is_valid_directory(str(tmp_path)) is True

    def test_nonexistent(self):
        assert is_valid_directory("/nonexistent/dir") is False

    def test_file_returns_false(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert is_valid_directory(str(f)) is False

    def test_empty(self):
        assert is_valid_directory("") is False


class TestIsWritable:
    def test_writable_dir(self, tmp_path):
        assert is_writable(str(tmp_path)) is True

    def test_writable_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert is_writable(str(f)) is True

    def test_nonexistent_in_writable_parent(self, tmp_path):
        assert is_writable(str(tmp_path / "newfile.txt")) is True

    def test_empty_path(self):
        assert is_writable("") is False


class TestIsReadable:
    def test_readable_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert is_readable(str(f)) is True

    def test_nonexistent(self):
        assert is_readable("/nonexistent") is False

    def test_empty(self):
        assert is_readable("") is False


# ============================================================================
# Validate-or-raise
# ============================================================================

class TestValidateFile:
    def test_valid_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert validate_file(str(f)) == str(f)

    def test_empty_path_raises(self):
        with pytest.raises(ValidationError, match="empty or None"):
            validate_file("")

    def test_nonexistent_raises(self):
        with pytest.raises(ValidationError, match="not found"):
            validate_file("/nonexistent/file.txt")

    def test_directory_raises(self, tmp_path):
        with pytest.raises(ValidationError, match="not a file"):
            validate_file(str(tmp_path))

    def test_must_exist_false(self):
        # Should not raise even if file doesn't exist
        result = validate_file("/nonexistent/path", must_exist=False)
        assert result == "/nonexistent/path"


class TestValidateDirectory:
    def test_valid_existing_dir(self, tmp_path):
        assert validate_directory(str(tmp_path)) == str(tmp_path)

    def test_empty_raises(self):
        with pytest.raises(ValidationError, match="empty or None"):
            validate_directory("")

    def test_nonexistent_raises(self):
        with pytest.raises(ValidationError, match="not found"):
            validate_directory("/nonexistent/dir")

    def test_file_raises(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with pytest.raises(ValidationError, match="not a directory"):
            validate_directory(str(f))

    def test_create_on_missing(self, tmp_path):
        new_dir = tmp_path / "subdir"
        result = validate_directory(str(new_dir), create=True)
        assert os.path.isdir(result)


class TestValidateFileForOperation:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert validate_file_for_operation(str(f), "read") is True

    def test_empty_path(self):
        assert validate_file_for_operation("", "read") is False

    def test_nonexistent(self):
        assert validate_file_for_operation("/nonexistent", "read") is False


class TestValidateDirectoryForOperation:
    def test_valid_dir(self, tmp_path):
        assert validate_directory_for_operation(str(tmp_path), "scan") is True

    def test_empty_path(self):
        assert validate_directory_for_operation("", "scan") is False

    def test_nonexistent(self):
        assert validate_directory_for_operation("/nonexistent", "scan") is False


# ============================================================================
# Safe operations
# ============================================================================

class TestSafeListDir:
    def test_lists_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.png").write_text("b")
        result = safe_list_dir(str(tmp_path))
        assert sorted(result) == ["a.txt", "b.png"]

    def test_with_pattern(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.png").write_text("b")
        result = safe_list_dir(str(tmp_path), "*.png")
        assert result == ["b.png"]

    def test_invalid_dir(self):
        assert safe_list_dir("/nonexistent") == []

    def test_empty_string(self):
        assert safe_list_dir("") == []


class TestSafeFileStat:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = safe_file_stat(str(f))
        assert result is not None
        assert result.st_size == 5

    def test_nonexistent(self):
        assert safe_file_stat("/nonexistent") is None

    def test_empty(self):
        assert safe_file_stat("") is None


class TestSafePathJoin:
    def test_basic_join(self):
        result = safe_path_join("a", "b", "c")
        assert result == os.path.join("a", "b", "c")

    def test_filters_empty(self):
        result = safe_path_join("a", "", "c", None)
        assert result == os.path.join("a", "c")

    def test_all_empty(self):
        assert safe_path_join("", None) == ""


# ============================================================================
# Compatibility functions
# ============================================================================

class TestValidateFileExists:
    def test_existing(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert validate_file_exists(str(f)) is True

    def test_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            validate_file_exists("/nonexistent")

    def test_missing_no_raise(self):
        assert validate_file_exists("/nonexistent", raise_error=False) is False


class TestValidateIsFile:
    def test_is_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert validate_is_file(str(f)) is True

    def test_is_dir_raises(self, tmp_path):
        with pytest.raises(ValueError):
            validate_is_file(str(tmp_path))

    def test_is_dir_no_raise(self, tmp_path):
        assert validate_is_file(str(tmp_path), raise_error=False) is False


class TestValidateIsDirectory:
    def test_is_dir(self, tmp_path):
        assert validate_is_directory(str(tmp_path)) is True

    def test_is_file_raises(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with pytest.raises(ValueError):
            validate_is_directory(str(f))
