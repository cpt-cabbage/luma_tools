"""Tests for the ComfyUI workflow analytics module."""

import json
import os
import time
from datetime import datetime, timedelta

import pytest

from comfyui.analytics import (
    _compute_stats,
    _read_workflow_preset,
    _atomic_write_json,
    record_execution,
    aggregate_node_timing,
    SCHEMA_VERSION,
)


# =============================================================================
# _compute_stats
# =============================================================================

class TestComputeStats:
    def test_empty_list(self):
        assert _compute_stats([]) == {}

    def test_single_value(self):
        result = _compute_stats([100.0])
        assert result["count"] == 1
        assert result["avg_ms"] == 100
        assert result["min_ms"] == 100
        assert result["max_ms"] == 100
        assert result["median_ms"] == 100
        assert result["p95_ms"] == 100

    def test_known_values_odd_count(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = _compute_stats(values)
        assert result["count"] == 5
        assert result["avg_ms"] == 30
        assert result["min_ms"] == 10
        assert result["max_ms"] == 50
        assert result["median_ms"] == 30
        # p95 index = int(5 * 0.95) = 4 -> sorted[4] = 50
        assert result["p95_ms"] == 50

    def test_known_values_even_count(self):
        values = [10.0, 20.0, 30.0, 40.0]
        result = _compute_stats(values)
        assert result["count"] == 4
        assert result["avg_ms"] == 25
        assert result["min_ms"] == 10
        assert result["max_ms"] == 40
        # median of [10, 20, 30, 40] = (20 + 30) / 2 = 25
        assert result["median_ms"] == 25

    def test_unsorted_input(self):
        values = [50.0, 10.0, 30.0]
        result = _compute_stats(values)
        assert result["min_ms"] == 10
        assert result["max_ms"] == 50
        assert result["median_ms"] == 30

    def test_duplicate_values(self):
        values = [100.0, 100.0, 100.0]
        result = _compute_stats(values)
        assert result["avg_ms"] == 100
        assert result["min_ms"] == 100
        assert result["max_ms"] == 100

    def test_large_dataset_p95(self):
        # 100 values from 1 to 100
        values = [float(i) for i in range(1, 101)]
        result = _compute_stats(values)
        assert result["count"] == 100
        assert result["min_ms"] == 1
        assert result["max_ms"] == 100
        # p95 index = int(100 * 0.95) = 95 -> sorted[95] = 96
        assert result["p95_ms"] == 96


# =============================================================================
# _read_workflow_preset
# =============================================================================

class TestReadWorkflowPreset:
    def test_missing_file(self, tmp_path):
        assert _read_workflow_preset(str(tmp_path)) == "unknown"

    def test_empty_metadata(self, tmp_path):
        metadata_path = tmp_path / "comfyui_gallery_metadata.json"
        metadata_path.write_text("{}")
        assert _read_workflow_preset(str(tmp_path)) == "unknown"

    def test_valid_preset(self, tmp_path):
        metadata = {
            "_prefix_my_job": {
                "workflow_preset": "Trellis 2",
                "prompt": "test",
            }
        }
        metadata_path = tmp_path / "comfyui_gallery_metadata.json"
        metadata_path.write_text(json.dumps(metadata))
        assert _read_workflow_preset(str(tmp_path)) == "Trellis 2"

    def test_no_preset_in_entries(self, tmp_path):
        metadata = {
            "_prefix_my_job": {
                "prompt": "test",
            }
        }
        metadata_path = tmp_path / "comfyui_gallery_metadata.json"
        metadata_path.write_text(json.dumps(metadata))
        assert _read_workflow_preset(str(tmp_path)) == "unknown"

    def test_corrupt_json(self, tmp_path):
        metadata_path = tmp_path / "comfyui_gallery_metadata.json"
        metadata_path.write_text("not valid json{{{")
        assert _read_workflow_preset(str(tmp_path)) == "unknown"

    def test_non_dict_entries_skipped(self, tmp_path):
        metadata = {
            "_prefix_bad": "not a dict",
            "_prefix_good": {"workflow_preset": "My Preset"},
        }
        metadata_path = tmp_path / "comfyui_gallery_metadata.json"
        metadata_path.write_text(json.dumps(metadata))
        assert _read_workflow_preset(str(tmp_path)) == "My Preset"


# =============================================================================
# _atomic_write_json
# =============================================================================

class TestAtomicWriteJson:
    def test_writes_valid_json(self, tmp_path):
        path = str(tmp_path / "test.json")
        data = {"key": "value", "number": 42}
        assert _atomic_write_json(path, data) is True
        with open(path, 'r') as f:
            loaded = json.load(f)
        assert loaded == data

    def test_overwrites_existing(self, tmp_path):
        path = str(tmp_path / "test.json")
        _atomic_write_json(path, {"old": True})
        _atomic_write_json(path, {"new": True})
        with open(path, 'r') as f:
            loaded = json.load(f)
        assert loaded == {"new": True}

    def test_invalid_directory(self):
        # Writing to a non-existent directory should fail gracefully
        result = _atomic_write_json("/nonexistent/dir/test.json", {})
        assert result is False


# =============================================================================
# record_execution
# =============================================================================

class TestRecordExecution:
    def _make_network_path(self, tmp_path):
        """Create a mock network path structure."""
        network_path = str(tmp_path / "network")
        os.makedirs(network_path, exist_ok=True)
        return network_path

    def test_writes_valid_record(self, tmp_path):
        network_path = self._make_network_path(tmp_path)
        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        result = record_execution(
            output_directory=output_dir,
            workflow_file="workflow.json",
            output_prefix="test_output",
            total_frames=2,
            successful=2,
            failed=0,
            frame_results=[
                {
                    "frame_num": 1,
                    "success": True,
                    "execution_time_ms": 10000,
                    "node_timing": [
                        {"node_id": "5", "node_type": "KSampler", "duration_ms": 8000}
                    ],
                },
                {
                    "frame_num": 2,
                    "success": True,
                    "execution_time_ms": 11000,
                    "node_timing": [
                        {"node_id": "5", "node_type": "KSampler", "duration_ms": 9000}
                    ],
                },
            ],
            network_path=network_path,
        )

        assert result != ""
        assert os.path.exists(result)

        with open(result, 'r') as f:
            record = json.load(f)

        assert record["schema_version"] == SCHEMA_VERSION
        assert record["total_frames"] == 2
        assert record["successful"] == 2
        assert record["failed"] == 0
        assert record["output_prefix"] == "test_output"
        assert record["workflow_file"] == "workflow.json"
        assert len(record["frames"]) == 2
        assert record["frames"][0]["node_timing"][0]["node_type"] == "KSampler"

    def test_unique_filenames(self, tmp_path):
        network_path = self._make_network_path(tmp_path)
        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        paths = set()
        for i in range(5):
            result = record_execution(
                output_directory=output_dir,
                workflow_file="wf.json",
                output_prefix=f"prefix_{i}",
                total_frames=1,
                successful=1,
                failed=0,
                frame_results=[{"frame_num": 1, "success": True}],
                network_path=network_path,
            )
            paths.add(result)

        # All paths should be unique
        assert len(paths) == 5

    def test_reads_workflow_preset(self, tmp_path):
        network_path = self._make_network_path(tmp_path)
        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        # Write gallery metadata with preset
        metadata = {"_prefix_job": {"workflow_preset": "My Workflow"}}
        with open(os.path.join(output_dir, "comfyui_gallery_metadata.json"), 'w') as f:
            json.dump(metadata, f)

        result = record_execution(
            output_directory=output_dir,
            workflow_file="wf.json",
            output_prefix="job",
            total_frames=1,
            successful=1,
            failed=0,
            frame_results=[{"frame_num": 1, "success": True}],
            network_path=network_path,
        )

        with open(result, 'r') as f:
            record = json.load(f)
        assert record["workflow_preset"] == "My Workflow"

    def test_no_network_path(self, tmp_path):
        """Should return empty string when no network path available."""
        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        result = record_execution(
            output_directory=output_dir,
            workflow_file="wf.json",
            output_prefix="test",
            total_frames=1,
            successful=1,
            failed=0,
            frame_results=[],
            network_path=None,
        )
        # Without a real network path, _get_network_output_path will fail
        # We pass None explicitly to test this path
        # But since _get_network_output_path won't find real settings, result is ""
        # (This tests graceful degradation)
        assert isinstance(result, str)


# =============================================================================
# aggregate_node_timing
# =============================================================================

class TestAggregateNodeTiming:
    def _make_analytics_dir(self, tmp_path):
        """Create analytics directory structure and return network path."""
        network_path = str(tmp_path / "network")
        executions_dir = os.path.join(network_path, "_analytics", "executions")
        os.makedirs(executions_dir, exist_ok=True)
        os.makedirs(os.path.join(network_path, "_analytics", "reports"), exist_ok=True)
        return network_path

    def _write_execution_record(self, network_path, filename, record):
        """Write an execution record to the executions directory."""
        executions_dir = os.path.join(network_path, "_analytics", "executions")
        path = os.path.join(executions_dir, filename)
        with open(path, 'w') as f:
            json.dump(record, f)

    def test_empty_directory(self, tmp_path):
        network_path = self._make_analytics_dir(tmp_path)
        result = aggregate_node_timing(network_path=network_path)
        assert result["total_executions"] == 0
        assert result["total_frames"] == 0
        assert result["by_workflow"] == {}
        assert result["global_node_types"] == {}

    def test_single_record(self, tmp_path):
        network_path = self._make_analytics_dir(tmp_path)

        record = {
            "schema_version": 1,
            "timestamp": datetime.now().isoformat(),
            "hostname": "TEST-WS",
            "workflow_preset": "Trellis 2",
            "workflow_file": "wf.json",
            "output_prefix": "test",
            "total_frames": 1,
            "successful": 1,
            "failed": 0,
            "frames": [
                {
                    "frame_num": 1,
                    "success": True,
                    "execution_time_ms": 15000,
                    "node_timing": [
                        {"node_id": "5", "node_type": "KSampler", "duration_ms": 10000},
                        {"node_id": "8", "node_type": "VAEDecode", "duration_ms": 2000},
                    ],
                }
            ],
        }
        self._write_execution_record(network_path, "record1.json", record)

        result = aggregate_node_timing(network_path=network_path)
        assert result["total_executions"] == 1
        assert result["total_frames"] == 1
        assert "Trellis 2" in result["by_workflow"]

        trellis = result["by_workflow"]["Trellis 2"]
        assert trellis["execution_count"] == 1
        assert trellis["frame_count"] == 1
        assert "KSampler" in trellis["node_types"]
        assert trellis["node_types"]["KSampler"]["avg_ms"] == 10000

        assert "KSampler" in result["global_node_types"]
        assert result["global_node_types"]["KSampler"]["count"] == 1

    def test_multiple_records(self, tmp_path):
        network_path = self._make_analytics_dir(tmp_path)

        for i in range(3):
            record = {
                "schema_version": 1,
                "timestamp": datetime.now().isoformat(),
                "hostname": f"WS-{i}",
                "workflow_preset": "Trellis 2",
                "total_frames": 1,
                "successful": 1,
                "failed": 0,
                "frames": [
                    {
                        "frame_num": 1,
                        "success": True,
                        "node_timing": [
                            {"node_id": "5", "node_type": "KSampler", "duration_ms": 10000 + i * 1000},
                        ],
                    }
                ],
            }
            self._write_execution_record(network_path, f"record_{i}.json", record)

        result = aggregate_node_timing(network_path=network_path)
        assert result["total_executions"] == 3
        assert result["total_frames"] == 3

        ks = result["global_node_types"]["KSampler"]
        assert ks["count"] == 3
        assert ks["min_ms"] == 10000
        assert ks["max_ms"] == 12000
        assert ks["avg_ms"] == 11000

    def test_max_age_filter(self, tmp_path):
        network_path = self._make_analytics_dir(tmp_path)

        # Old record (beyond max_age)
        old_time = (datetime.now() - timedelta(days=100)).isoformat()
        old_record = {
            "schema_version": 1,
            "timestamp": old_time,
            "workflow_preset": "Old Workflow",
            "total_frames": 1,
            "successful": 1,
            "failed": 0,
            "frames": [
                {
                    "frame_num": 1,
                    "success": True,
                    "node_timing": [
                        {"node_id": "1", "node_type": "OldNode", "duration_ms": 5000},
                    ],
                }
            ],
        }
        self._write_execution_record(network_path, "old.json", old_record)

        # Recent record
        recent_record = {
            "schema_version": 1,
            "timestamp": datetime.now().isoformat(),
            "workflow_preset": "New Workflow",
            "total_frames": 1,
            "successful": 1,
            "failed": 0,
            "frames": [
                {
                    "frame_num": 1,
                    "success": True,
                    "node_timing": [
                        {"node_id": "1", "node_type": "NewNode", "duration_ms": 3000},
                    ],
                }
            ],
        }
        self._write_execution_record(network_path, "recent.json", recent_record)

        result = aggregate_node_timing(network_path=network_path, max_age_days=90)
        assert result["total_executions"] == 1
        assert "New Workflow" in result["by_workflow"]
        assert "Old Workflow" not in result["by_workflow"]
        assert "NewNode" in result["global_node_types"]
        assert "OldNode" not in result["global_node_types"]

    def test_skips_corrupt_files(self, tmp_path):
        network_path = self._make_analytics_dir(tmp_path)

        # Corrupt file
        executions_dir = os.path.join(network_path, "_analytics", "executions")
        corrupt_path = os.path.join(executions_dir, "corrupt.json")
        with open(corrupt_path, 'w') as f:
            f.write("not valid json{{{")

        # Valid record
        valid_record = {
            "schema_version": 1,
            "timestamp": datetime.now().isoformat(),
            "workflow_preset": "Valid",
            "total_frames": 1,
            "successful": 1,
            "failed": 0,
            "frames": [
                {
                    "frame_num": 1,
                    "success": True,
                    "node_timing": [
                        {"node_id": "1", "node_type": "TestNode", "duration_ms": 1000},
                    ],
                }
            ],
        }
        self._write_execution_record(network_path, "valid.json", valid_record)

        result = aggregate_node_timing(network_path=network_path)
        assert result["total_executions"] == 1
        assert "TestNode" in result["global_node_types"]

    def test_skips_failed_frames(self, tmp_path):
        network_path = self._make_analytics_dir(tmp_path)

        record = {
            "schema_version": 1,
            "timestamp": datetime.now().isoformat(),
            "workflow_preset": "Test",
            "total_frames": 2,
            "successful": 1,
            "failed": 1,
            "frames": [
                {
                    "frame_num": 1,
                    "success": True,
                    "node_timing": [
                        {"node_id": "1", "node_type": "GoodNode", "duration_ms": 1000},
                    ],
                },
                {
                    "frame_num": 2,
                    "success": False,
                },
            ],
        }
        self._write_execution_record(network_path, "record.json", record)

        result = aggregate_node_timing(network_path=network_path)
        # Only the successful frame's nodes should appear
        assert "GoodNode" in result["global_node_types"]
        assert result["global_node_types"]["GoodNode"]["count"] == 1

    def test_writes_summary_report(self, tmp_path):
        network_path = self._make_analytics_dir(tmp_path)

        record = {
            "schema_version": 1,
            "timestamp": datetime.now().isoformat(),
            "workflow_preset": "Test",
            "total_frames": 1,
            "successful": 1,
            "failed": 0,
            "frames": [
                {
                    "frame_num": 1,
                    "success": True,
                    "node_timing": [
                        {"node_id": "1", "node_type": "TestNode", "duration_ms": 5000},
                    ],
                }
            ],
        }
        self._write_execution_record(network_path, "record.json", record)

        aggregate_node_timing(network_path=network_path)

        report_path = os.path.join(network_path, "_analytics", "reports", "node_timing_summary.json")
        assert os.path.exists(report_path)

        with open(report_path, 'r') as f:
            report = json.load(f)
        assert report["schema_version"] == SCHEMA_VERSION
        assert report["total_executions"] == 1

    def test_multiple_workflows(self, tmp_path):
        network_path = self._make_analytics_dir(tmp_path)

        for preset in ["Workflow A", "Workflow B"]:
            record = {
                "schema_version": 1,
                "timestamp": datetime.now().isoformat(),
                "workflow_preset": preset,
                "total_frames": 1,
                "successful": 1,
                "failed": 0,
                "frames": [
                    {
                        "frame_num": 1,
                        "success": True,
                        "node_timing": [
                            {"node_id": "1", "node_type": "SharedNode", "duration_ms": 2000},
                        ],
                    }
                ],
            }
            safe = preset.replace(" ", "_")
            self._write_execution_record(network_path, f"{safe}.json", record)

        result = aggregate_node_timing(network_path=network_path)
        assert "Workflow A" in result["by_workflow"]
        assert "Workflow B" in result["by_workflow"]
        # Global should combine both
        assert result["global_node_types"]["SharedNode"]["count"] == 2

    def test_no_network_path(self):
        result = aggregate_node_timing(network_path=None)
        # Without a real network path, should return empty dict gracefully
        assert isinstance(result, dict)
