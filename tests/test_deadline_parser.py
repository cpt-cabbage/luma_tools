"""Tests for deadline/parser.py — pure string parsing functions."""

import pytest
from deadline.parser import (
    parse_deadline_output,
    parse_job_info,
    extract_job_id,
    is_job_not_found,
    get_task_counts,
    normalize_job_status,
    format_error_message,
)


# ============================================================================
# parse_deadline_output
# ============================================================================

class TestParseDeadlineOutput:
    def test_basic_key_value(self):
        output = "JobID=abc123\nName=My Job\nPriority=50"
        result = parse_deadline_output(output)
        assert result == {"JobID": "abc123", "Name": "My Job", "Priority": "50"}

    def test_empty_string(self):
        assert parse_deadline_output("") == {}

    def test_lines_without_equals(self):
        output = "Some informational line\nJobID=abc123\nAnother line"
        result = parse_deadline_output(output)
        assert result == {"JobID": "abc123"}

    def test_value_contains_equals(self):
        output = "Command=python -c \"x=1\""
        result = parse_deadline_output(output)
        assert result["Command"] == "python -c \"x=1\""

    def test_whitespace_handling(self):
        output = "  Key = Value  \n  Another=Test  "
        result = parse_deadline_output(output)
        assert result["Key"] == "Value"
        assert result["Another"] == "Test"

    def test_windows_line_endings(self):
        output = "Key1=Val1\r\nKey2=Val2\r\n"
        result = parse_deadline_output(output)
        assert result == {"Key1": "Val1", "Key2": "Val2"}

    def test_empty_value(self):
        output = "Key="
        result = parse_deadline_output(output)
        assert result["Key"] == ""


# ============================================================================
# parse_job_info
# ============================================================================

class TestParseJobInfo:
    def test_int_fields_converted(self):
        output = "Priority=50\nCompletedTasks=5\nFailedTasks=1\nTaskCount=10"
        result = parse_job_info(output)
        assert result["Priority"] == 50
        assert result["CompletedTasks"] == 5
        assert result["FailedTasks"] == 1
        assert result["TaskCount"] == 10

    def test_non_int_field_stays_string(self):
        output = "Name=My Job\nStatus=Active"
        result = parse_job_info(output)
        assert result["Name"] == "My Job"
        assert result["Status"] == "Active"

    def test_invalid_int_defaults_to_zero(self):
        output = "Priority=not_a_number\nCompletedTasks="
        result = parse_job_info(output)
        assert result["Priority"] == 0
        assert result["CompletedTasks"] == 0

    def test_chunk_fields_also_converted(self):
        output = "CompletedChunks=3\nChunkCount=8"
        result = parse_job_info(output)
        assert result["CompletedChunks"] == 3
        assert result["ChunkCount"] == 8


# ============================================================================
# extract_job_id
# ============================================================================

class TestExtractJobId:
    def test_found(self):
        output = "Result=Success\nJobID=660a1b2c3d4e5f\nMessage=OK"
        assert extract_job_id(output) == "660a1b2c3d4e5f"

    def test_not_found(self):
        output = "Result=Error\nMessage=Failed"
        assert extract_job_id(output) is None

    def test_empty_output(self):
        assert extract_job_id("") is None


# ============================================================================
# is_job_not_found
# ============================================================================

class TestIsJobNotFound:
    def test_not_found_in_stderr(self):
        assert is_job_not_found(1, "Error: Job not found", "") is True

    def test_does_not_exist_in_stderr(self):
        assert is_job_not_found(1, "Job does not exist", "") is True

    def test_empty_stderr_and_stdout(self):
        assert is_job_not_found(1, "", "") is True

    def test_empty_stderr_but_nonempty_stdout(self):
        assert is_job_not_found(1, "", "Some output here") is False

    def test_returncode_zero_with_status(self):
        assert is_job_not_found(0, "", "Status=Active\nName=Job") is False

    def test_returncode_zero_without_status(self):
        assert is_job_not_found(0, "", "No status here") is True

    def test_returncode_zero_empty_stdout(self):
        assert is_job_not_found(0, "", "") is True

    def test_real_error_not_mistaken_for_not_found(self):
        assert is_job_not_found(1, "Permission denied", "partial output") is False


# ============================================================================
# get_task_counts
# ============================================================================

class TestGetTaskCounts:
    def test_tasks_naming(self):
        info = {"CompletedTasks": 5, "FailedTasks": 1, "TaskCount": 10,
                "QueuedTasks": 3, "RenderingTasks": 1}
        counts = get_task_counts(info)
        assert counts == {"completed": 5, "failed": 1, "total": 10,
                          "queued": 3, "rendering": 1}

    def test_chunks_naming(self):
        info = {"CompletedChunks": 3, "FailedChunks": 0, "ChunkCount": 8,
                "QueuedChunks": 5, "RenderingChunks": 0}
        counts = get_task_counts(info)
        assert counts == {"completed": 3, "failed": 0, "total": 8,
                          "queued": 5, "rendering": 0}

    def test_tasks_takes_priority(self):
        info = {"CompletedTasks": 10, "CompletedChunks": 5}
        counts = get_task_counts(info)
        assert counts["completed"] == 10

    def test_empty_info_defaults(self):
        counts = get_task_counts({})
        assert counts == {"completed": 0, "failed": 0, "total": 1,
                          "queued": 0, "rendering": 0}


# ============================================================================
# normalize_job_status
# ============================================================================

class TestNormalizeJobStatus:
    def test_complete_becomes_completed(self):
        assert normalize_job_status("Complete", {"failed": 0}) == "Completed"

    def test_completed_with_failures_becomes_failed(self):
        assert normalize_job_status("Completed", {"failed": 2}) == "Failed"

    def test_active_rendering(self):
        assert normalize_job_status("Active", {"rendering": 1, "queued": 0, "completed": 0}) == "Rendering"

    def test_active_queued_no_completed(self):
        assert normalize_job_status("Active", {"rendering": 0, "queued": 5, "completed": 0}) == "Queued"

    def test_active_queued_with_completed_stays_active(self):
        assert normalize_job_status("Active", {"rendering": 0, "queued": 2, "completed": 3}) == "Active"

    def test_other_status_passes_through(self):
        assert normalize_job_status("Suspended", {"failed": 0}) == "Suspended"
        assert normalize_job_status("Pending", {}) == "Pending"


# ============================================================================
# format_error_message
# ============================================================================

class TestFormatErrorMessage:
    def test_no_errors(self):
        assert format_error_message({"failed": 0, "total": 10}) == ""

    def test_failures_only(self):
        msg = format_error_message({"failed": 3, "total": 10})
        assert "3/10" in msg
        assert "failed" in msg

    def test_failures_with_reports(self):
        msg = format_error_message({"failed": 2, "total": 5}, error_reports=4)
        assert "2/5" in msg
        assert "4 error report" in msg

    def test_no_failures_but_error_reports(self):
        msg = format_error_message({"failed": 0, "total": 10}, error_reports=2)
        assert "2 error report" in msg
