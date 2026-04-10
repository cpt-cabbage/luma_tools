"""Tests for deadline.utils — run_deadline_command, submit_deadline_job."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from deadline.utils import run_deadline_command, submit_deadline_job


def _mock_result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


class TestRunDeadlineCommand:
    @patch("deadline.utils.run_command")
    def test_success(self, mock_run):
        mock_run.return_value = _mock_result(stdout="JobID=abc123\n")
        success, output, error = run_deadline_command(["deadline", "submit"])
        assert success is True
        assert "abc123" in output
        assert error == ""

    @patch("deadline.utils.run_command")
    def test_failure(self, mock_run):
        mock_run.return_value = _mock_result(stderr="Connection refused", returncode=1)
        success, output, error = run_deadline_command(["deadline", "submit"])
        assert success is False
        assert "Connection refused" in error

    @patch("deadline.utils.run_command", side_effect=Exception("timeout"))
    def test_exception(self, mock_run):
        success, output, error = run_deadline_command(["deadline", "submit"])
        assert success is False
        assert "timeout" in error

    @patch("deadline.utils.run_command")
    def test_log_prefix(self, mock_run):
        mock_run.return_value = _mock_result(stdout="OK")
        success, _, _ = run_deadline_command(["cmd"], log_prefix="[OIIO]")
        assert success is True


class TestSubmitDeadlineJob:
    @patch("deadline.utils.run_deadline_command", return_value=(True, "JobID=abc123def456\n", ""))
    def test_returns_job_id(self, mock_run):
        result = submit_deadline_job(["deadline", "submit"])
        assert result == "abc123def456"

    @patch("deadline.utils.run_deadline_command", return_value=(False, "", "error"))
    def test_returns_none_on_failure(self, mock_run):
        result = submit_deadline_job(["deadline", "submit"])
        assert result is None
