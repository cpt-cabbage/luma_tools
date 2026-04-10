"""Tests for deadline.poller — job status polling, log parsing, queue info."""

import re
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest

from deadline.poller import (
    poll_deadline_job_status,
    extract_task_progress,
    get_task_log,
    complete_deadline_job,
    cancel_deadline_jobs,
)


def _mock_result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


# ============================================================================
# poll_deadline_job_status
# ============================================================================

class TestPollDeadlineJobStatus:
    def test_invalid_job_id(self):
        result = poll_deadline_job_status("")
        assert result["status"] == "Unknown"

    def test_invalid_format(self):
        result = poll_deadline_job_status("not-a-hex-id")
        assert result["status"] == "Unknown"

    def test_valid_hex_id_format(self):
        # 24 hex chars
        valid_id = "a" * 24
        with patch("deadline.poller.DEADLINE_PATH", ""):
            result = poll_deadline_job_status(valid_id)
            assert result["status"] == "Unknown"

    @patch("deadline.poller.run_command")
    @patch("deadline.poller.DEADLINE_PATH", "/path/to/deadline")
    def test_completed_job(self, mock_run):
        mock_run.return_value = _mock_result(
            stdout="Name=TestJob\nStatus=Completed\nTaskCount=5\n"
                   "CompletedChunks=5\nQueuedChunks=0\nRenderingChunks=0\n"
                   "FailedChunks=0\nSuspendedChunks=0\nPendingChunks=0\nErrorReports=0",
        )
        result = poll_deadline_job_status("a" * 24)
        assert result["status"] == "Completed"
        assert result["progress"] == 100

    @patch("deadline.poller.run_command")
    @patch("deadline.poller.DEADLINE_PATH", "/path/to/deadline")
    def test_rendering_job(self, mock_run):
        mock_run.return_value = _mock_result(
            stdout="Name=TestJob\nStatus=Active\nTaskCount=10\n"
                   "CompletedChunks=5\nQueuedChunks=0\nRenderingChunks=5\n"
                   "FailedChunks=0\nSuspendedChunks=0\nPendingChunks=0\nErrorReports=0",
        )
        result = poll_deadline_job_status("a" * 24)
        assert result["progress"] == 50

    @patch("deadline.poller.run_command")
    @patch("deadline.poller.DEADLINE_PATH", "/path/to/deadline")
    def test_job_not_found(self, mock_run):
        mock_run.return_value = _mock_result(
            stdout="", stderr="Error: Job with ID aaaa not found", returncode=1
        )
        result = poll_deadline_job_status("a" * 24)
        assert result["status"] == "Unknown"


# ============================================================================
# extract_task_progress
# ============================================================================

class TestExtractTaskProgress:
    def test_none_input(self):
        assert extract_task_progress(None) is None

    def test_empty_string(self):
        assert extract_task_progress("") is None

    def test_runner_format(self):
        log = "Some preamble\nProgress: 42% (5/12) (15s)\nMore stuff"
        result = extract_task_progress(log)
        assert result["progress_pct"] == 42
        assert result["current_node"] == 5
        assert result["total_nodes"] == 12
        assert result["elapsed_seconds"] == 15

    def test_runner_format_no_time(self):
        log = "Progress: 80% (8/10)"
        result = extract_task_progress(log)
        assert result["progress_pct"] == 80
        assert result["elapsed_seconds"] is None

    def test_tqdm_format(self):
        log = " 12%|█▎        | 1/8 [00:03<00:24,  3.46s/it]"
        result = extract_task_progress(log)
        assert result["progress_pct"] == 12
        assert result["current_node"] == 1
        assert result["total_nodes"] == 8

    def test_latest_progress_used(self):
        log = "Progress: 10% (1/10)\nProgress: 50% (5/10)\nProgress: 90% (9/10)"
        result = extract_task_progress(log)
        assert result["progress_pct"] == 90

    def test_model_loading_detection(self):
        log = "Loading model from checkpoint...\nLoading CLIP..."
        result = extract_task_progress(log)
        assert result is not None
        assert result["is_loading_model"] is True

    def test_model_loaded_with_progress(self):
        log = "Loading model from checkpoint...\nProgress: 50% (5/10)"
        result = extract_task_progress(log)
        assert result["progress_pct"] == 50
        # Model is loaded once progress starts (current_node > 0)
        assert result["is_loading_model"] is False

    def test_execution_started_no_progress(self):
        log = "Execution started for workflow abc123"
        result = extract_task_progress(log)
        assert result is not None
        assert result["progress_pct"] == 0
        assert result["is_loading_model"] is True

    def test_node_name_extraction(self):
        log = "Executing node 5, title: KSampler\nProgress: 50% (5/10)"
        result = extract_task_progress(log)
        assert result["current_node_name"] is not None


# ============================================================================
# complete_deadline_job
# ============================================================================

class TestCompleteDeadlineJob:
    @patch("deadline.poller.DEADLINE_PATH", "")
    def test_no_deadline(self):
        success, msg = complete_deadline_job("abc")
        assert success is False

    @patch("deadline.poller.run_command")
    @patch("deadline.poller.DEADLINE_PATH", "/path/to/deadline")
    def test_success(self, mock_run):
        mock_run.return_value = _mock_result(stdout="Job completed")
        success, msg = complete_deadline_job("abc")
        assert success is True

    @patch("deadline.poller.run_command")
    @patch("deadline.poller.DEADLINE_PATH", "/path/to/deadline")
    def test_already_deleted(self, mock_run):
        mock_run.return_value = _mock_result(stdout="", stderr="Job not found", returncode=1)
        success, msg = complete_deadline_job("abc")
        assert success is True  # Already gone is treated as success


# ============================================================================
# cancel_deadline_jobs
# ============================================================================

class TestCancelDeadlineJobs:
    @patch("deadline.poller.complete_deadline_job", return_value=(True, "done"))
    def test_all_succeed(self, mock_complete):
        succeeded, failed, errors = cancel_deadline_jobs(["j1", "j2", "j3"])
        assert succeeded == 3
        assert failed == 0
        assert errors == []

    @patch("deadline.poller.complete_deadline_job", side_effect=[(True, "ok"), (False, "error")])
    def test_partial_failure(self, mock_complete):
        succeeded, failed, errors = cancel_deadline_jobs(["j1", "j2"])
        assert succeeded == 1
        assert failed == 1
        assert len(errors) == 1
