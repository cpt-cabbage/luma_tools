"""Tests for core/utils.py functions not covered by test_utils.py."""

import threading
import pytest
from core.utils import (
    replace_frame_tokens,
    format_duration,
    plural,
)
from core.error_handling import CancellationError, check_cancelled


# ============================================================================
# replace_frame_tokens
# ============================================================================

class TestReplaceFrameTokens:
    def test_basic_4_digit(self):
        assert replace_frame_tokens("render.<STARTFRAME%4>.exr", 42) == "render.0042.exr"

    def test_frame_1001(self):
        assert replace_frame_tokens("file.<STARTFRAME%4>.exr", 1001) == "file.1001.exr"

    def test_padding_1(self):
        assert replace_frame_tokens("<STARTFRAME%1>", 5) == "5"

    def test_padding_8(self):
        assert replace_frame_tokens("<STARTFRAME%8>", 1) == "00000001"

    def test_no_token_passthrough(self):
        assert replace_frame_tokens("no_tokens_here.exr", 42) == "no_tokens_here.exr"

    def test_multiple_tokens(self):
        template = "in.<STARTFRAME%4>.exr -o out.<STARTFRAME%4>.exr"
        result = replace_frame_tokens(template, 100)
        assert result == "in.0100.exr -o out.0100.exr"

    def test_frame_zero(self):
        assert replace_frame_tokens("<STARTFRAME%4>", 0) == "0000"

    def test_large_frame_number(self):
        assert replace_frame_tokens("<STARTFRAME%4>", 99999) == "99999"


# ============================================================================
# format_duration
# ============================================================================

class TestFormatDuration:
    def test_zero(self):
        assert format_duration(0) == "0:00"

    def test_seconds_only(self):
        assert format_duration(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert format_duration(125) == "2:05"

    def test_exactly_one_hour(self):
        assert format_duration(3600) == "1:00:00"

    def test_over_one_hour(self):
        assert format_duration(3725) == "1:02:05"

    def test_negative(self):
        assert format_duration(-1) == "0:00"

    def test_none(self):
        assert format_duration(None) == "0:00"

    def test_float(self):
        assert format_duration(125.9) == "2:05"

    def test_sixty_seconds(self):
        assert format_duration(60) == "1:00"


# ============================================================================
# plural
# ============================================================================

class TestPlural:
    def test_singular(self):
        assert plural(1, "file") == "1 file"

    def test_plural_auto(self):
        assert plural(5, "file") == "5 files"

    def test_zero(self):
        assert plural(0, "item") == "0 items"

    def test_custom_plural(self):
        assert plural(2, "match", "matches") == "2 matches"

    def test_negative(self):
        assert plural(-1, "file") == "-1 files"


# ============================================================================
# CancellationError / check_cancelled
# ============================================================================

class TestCheckCancelled:
    def test_none_event_no_raise(self):
        check_cancelled(None)  # Should not raise

    def test_unset_event_no_raise(self):
        event = threading.Event()
        check_cancelled(event)  # Should not raise

    def test_set_event_raises(self):
        event = threading.Event()
        event.set()
        with pytest.raises(CancellationError):
            check_cancelled(event)

    def test_cancellation_error_is_exception(self):
        assert issubclass(CancellationError, Exception)
