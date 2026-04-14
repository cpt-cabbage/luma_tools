"""Unit tests for core/error_handling.py module."""
import sys
import os

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))


class TestSafeOperation:
    """Tests for @safe_operation decorator."""

    def test_successful_operation(self):
        """Test decorator passes through successful operations."""
        from core.error_handling import safe_operation

        @safe_operation("test operation")
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"

    def test_returns_default_on_error(self):
        """Test decorator returns default value on exception."""
        from core.error_handling import safe_operation

        @safe_operation("failing operation", return_on_error="default")
        def failing_func():
            raise ValueError("test error")

        result = failing_func()
        assert result == "default"

    def test_returns_none_by_default(self):
        """Test decorator returns None by default on error."""
        from core.error_handling import safe_operation

        @safe_operation("failing operation")
        def failing_func():
            raise ValueError("test error")

        result = failing_func()
        assert result is None

    def test_returns_custom_type(self):
        """Test decorator returns custom default types."""
        from core.error_handling import safe_operation

        @safe_operation("list operation", return_on_error=[])
        def failing_list():
            raise ValueError("error")

        @safe_operation("dict operation", return_on_error={})
        def failing_dict():
            raise ValueError("error")

        assert failing_list() == []
        assert failing_dict() == {}

    def test_preserves_function_args(self):
        """Test decorator passes arguments to function."""
        from core.error_handling import safe_operation

        @safe_operation("add operation")
        def add(a, b):
            return a + b

        assert add(2, 3) == 5
        assert add(a=5, b=10) == 15

    def test_custom_log_function(self):
        """Test decorator uses custom log function."""
        from core.error_handling import safe_operation

        logged_messages = []

        def custom_log(msg):
            logged_messages.append(msg)

        @safe_operation("test operation", log_func=custom_log)
        def failing_func():
            raise ValueError("test error")

        failing_func()
        assert len(logged_messages) == 1
        assert "test operation" in logged_messages[0]
        assert "test error" in logged_messages[0]


class TestHandleErrors:
    """Tests for handle_errors context manager."""

    def test_successful_block(self):
        """Test context manager passes through successful operations."""
        from core.error_handling import handle_errors

        result = None
        with handle_errors("test operation"):
            result = "success"

        assert result == "success"

    def test_catches_exception(self):
        """Test context manager catches exceptions."""
        from core.error_handling import handle_errors

        logged_messages = []

        def custom_log(msg):
            logged_messages.append(msg)

        with handle_errors("failing operation", log_func=custom_log):
            raise ValueError("test error")

        # Should not raise, should log
        assert len(logged_messages) == 1
        assert "failing operation" in logged_messages[0]

    def test_reraise_option(self):
        """Test context manager can reraise exceptions."""
        from core.error_handling import handle_errors

        with_error = False
        try:
            with handle_errors("failing operation", reraise=True):
                raise ValueError("test error")
        except ValueError:
            with_error = True

        assert with_error is True

    def test_no_reraise_by_default(self):
        """Test context manager doesn't reraise by default."""
        from core.error_handling import handle_errors

        # Should not raise
        with handle_errors("failing operation"):
            raise ValueError("test error")

        # If we got here, no exception was raised


class TestLogError:
    """Tests for log_error function."""

    def test_basic_logging(self):
        """Test basic error logging."""
        from core.error_handling import log_error

        logged_messages = []

        def custom_log(msg):
            logged_messages.append(msg)

        log_error("reading file", "File not found", log_func=custom_log)

        assert len(logged_messages) == 1
        assert "reading file" in logged_messages[0]
        assert "File not found" in logged_messages[0]

    def test_logging_with_variable(self):
        """Test error logging with variable context."""
        from core.error_handling import log_error

        logged_messages = []

        def custom_log(msg):
            logged_messages.append(msg)

        log_error("reading file", "Not found", variable="/path/to/file.txt", log_func=custom_log)

        assert len(logged_messages) == 1
        assert "/path/to/file.txt" in logged_messages[0]

    def test_exception_as_error(self):
        """Test logging with exception object."""
        from core.error_handling import log_error

        logged_messages = []

        def custom_log(msg):
            logged_messages.append(msg)

        try:
            raise ValueError("specific error message")
        except ValueError as e:
            log_error("processing", e, log_func=custom_log)

        assert len(logged_messages) == 1
        assert "specific error message" in logged_messages[0]


class TestIntegration:
    """Integration tests for error handling utilities."""

    def test_decorator_and_context_manager_together(self):
        """Test using decorator and context manager together."""
        from core.error_handling import safe_operation, handle_errors

        @safe_operation("outer operation", return_on_error="fallback")
        def outer_function():
            with handle_errors("inner operation"):
                raise ValueError("inner error")
            return "completed"

        # Inner error is caught by context manager, function continues
        result = outer_function()
        assert result == "completed"

    def test_nested_safe_operations(self):
        """Test nested decorated functions."""
        from core.error_handling import safe_operation

        @safe_operation("inner operation", return_on_error=0)
        def inner():
            raise ValueError("inner error")

        @safe_operation("outer operation", return_on_error=-1)
        def outer():
            return inner() + 10

        # Inner returns 0, outer returns 0 + 10 = 10
        result = outer()
        assert result == 10


# Allow running tests directly
if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
