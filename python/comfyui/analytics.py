"""
ComfyUI Workflow Analytics Module.

Records per-job execution data and aggregates node timing statistics
across all workflow runs. Designed to run on farm nodes (standard library only).

Storage layout on network path:
    _analytics/
        executions/     Write-once JSON per completed job
        reports/        Aggregated summary report (regenerated after each job)
"""

import os
import json
import time
import socket
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


# =============================================================================
# HELPERS
# =============================================================================

def _get_network_output_path() -> Optional[str]:
    """Get the network output path from farm config or global settings.

    Checks for _farm_config.json (written by submitter alongside this script)
    first, then falls back to the relative global_settings.json path from
    a full installation.

    Returns:
        Network output path string, or None if unavailable.
    """
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        settings_paths = [
            os.path.join(script_dir, '_farm_config.json'),
            os.path.join(script_dir, '..', '..', 'global_settings', 'global_settings.json'),
        ]
        for settings_path in settings_paths:
            norm_path = os.path.normpath(settings_path)
            if os.path.exists(norm_path):
                with open(norm_path, 'r') as f:
                    settings = json.load(f)
                network_path = settings.get('network_output_path', '')
                if network_path and os.path.isdir(network_path):
                    return network_path
    except Exception:
        pass
    return None


def _ensure_analytics_dirs(network_path: str) -> Optional[str]:
    """Ensure analytics directories exist under the network path.

    Args:
        network_path: Root network output path.

    Returns:
        Path to the _analytics directory, or None on failure.
    """
    analytics_dir = os.path.join(network_path, '_analytics')
    try:
        os.makedirs(os.path.join(analytics_dir, 'executions'), exist_ok=True)
        os.makedirs(os.path.join(analytics_dir, 'reports'), exist_ok=True)
        return analytics_dir
    except OSError as e:
        logger.warning(f"[Analytics] Could not create analytics directories: {e}")
        return None


def _atomic_write_json(path: str, data: Any) -> bool:
    """Write JSON atomically using temp file + rename.

    Writes to a .tmp file in the same directory, then uses os.replace()
    for an atomic rename. Safe for concurrent writers.

    Args:
        path: Destination file path.
        data: Data to serialize as JSON.

    Returns:
        True if write succeeded, False otherwise.
    """
    dir_path = os.path.dirname(path)
    try:
        fd, tmp_path = tempfile.mkstemp(suffix='.tmp', dir=dir_path)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
            return True
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.warning(f"[Analytics] Failed to write {path}: {e}")
        return False


def _read_workflow_preset(output_directory: str) -> str:
    """Read the workflow_preset from existing gallery metadata.

    The gallery metadata file is written by the submitter before the job
    runs, so it should already exist when the runner calls this.

    Args:
        output_directory: Job output directory containing gallery metadata.

    Returns:
        Workflow preset name, or "unknown" if not found.
    """
    metadata_path = os.path.join(output_directory, 'comfyui_gallery_metadata.json')
    try:
        if not os.path.exists(metadata_path):
            return "unknown"
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        # Search for workflow_preset in prefix entries
        for key, value in metadata.items():
            if key.startswith("_prefix_") and isinstance(value, dict):
                preset = value.get('workflow_preset')
                if preset is not None and preset != "":
                    return preset
        return "unknown"
    except Exception as e:
        logger.debug(f"[Analytics] Could not read workflow preset: {e}")
        return "unknown"


def _compute_stats(values: List[float]) -> Dict[str, Any]:
    """Compute statistics from a list of duration values.

    Calculates count, average, min, max, median, and p95 without numpy.

    Args:
        values: List of numeric duration values (milliseconds).

    Returns:
        Dict with count, avg_ms, min_ms, max_ms, median_ms, p95_ms.
        Returns empty dict if values is empty.
    """
    if not values:
        return {}

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    avg = sum(sorted_vals) / n

    # Median
    if n % 2 == 1:
        median = sorted_vals[n // 2]
    else:
        median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2

    # P95: use nearest-rank method
    p95_index = min(int(n * 0.95), n - 1)
    p95 = sorted_vals[p95_index]

    return {
        "count": n,
        "avg_ms": round(avg),
        "min_ms": round(sorted_vals[0]),
        "max_ms": round(sorted_vals[-1]),
        "median_ms": round(median),
        "p95_ms": round(p95),
    }


# =============================================================================
# RECORD EXECUTION
# =============================================================================

def record_execution(
    output_directory: str,
    workflow_file: str,
    output_prefix: str,
    total_frames: int,
    successful: int,
    failed: int,
    frame_results: List[Dict[str, Any]],
    network_path: Optional[str] = None,
) -> str:
    """Record execution data for a completed job.

    Writes a single JSON file per job to _analytics/executions/ with
    timing data for each frame including per-node breakdowns.

    Filenames use timestamp + hostname + prefix to avoid collisions
    from concurrent jobs on different farm machines.

    Args:
        output_directory: Job output directory (for reading gallery metadata).
        workflow_file: Path to the workflow JSON file used.
        output_prefix: Output prefix used for this job.
        total_frames: Total number of frames in the job.
        successful: Number of successfully completed frames.
        failed: Number of failed frames.
        frame_results: List of per-frame result dicts, each containing:
            - frame_num (int): Frame number
            - success (bool): Whether frame completed successfully
            - execution_time_ms (int, optional): Total frame execution time
            - node_timing (list, optional): List of {node_id, node_type, duration_ms}
        network_path: Override for network output path (auto-detected if None).

    Returns:
        Path to the written execution record, or empty string on failure.
    """
    if network_path is None:
        network_path = _get_network_output_path()
    if not network_path:
        logger.debug("[Analytics] No network path available, skipping execution record")
        return ""

    analytics_dir = _ensure_analytics_dirs(network_path)
    if not analytics_dir:
        return ""

    workflow_preset = _read_workflow_preset(output_directory)
    hostname = socket.gethostname()
    timestamp = datetime.now()
    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")

    # Sanitize prefix for filename
    safe_prefix = "".join(c if c.isalnum() or c in "-_" else "_" for c in output_prefix)

    filename = f"{timestamp_str}_{hostname}_{safe_prefix}.json"
    record_path = os.path.join(analytics_dir, 'executions', filename)

    record = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": timestamp.isoformat(),
        "hostname": hostname,
        "workflow_preset": workflow_preset,
        "workflow_file": os.path.basename(workflow_file) if workflow_file else "",
        "output_prefix": output_prefix,
        "total_frames": total_frames,
        "successful": successful,
        "failed": failed,
        "frames": frame_results,
    }

    if _atomic_write_json(record_path, record):
        logger.info(f"[Analytics] Execution record saved: {filename}")
        return record_path
    return ""


# =============================================================================
# AGGREGATE NODE TIMING
# =============================================================================

def aggregate_node_timing(
    network_path: Optional[str] = None,
    max_age_days: int = 90,
) -> Dict[str, Any]:
    """Aggregate node timing data from all execution records.

    Scans execution records in _analytics/executions/, computes per-workflow
    and global per-node-type statistics, and writes a summary report.

    Args:
        network_path: Override for network output path (auto-detected if None).
        max_age_days: Maximum age of records to include (default 90 days).

    Returns:
        The generated summary dict, or empty dict on failure.
    """
    if network_path is None:
        network_path = _get_network_output_path()
    if not network_path:
        logger.debug("[Analytics] No network path available, skipping aggregation")
        return {}

    analytics_dir = _ensure_analytics_dirs(network_path)
    if not analytics_dir:
        return {}

    executions_dir = os.path.join(analytics_dir, 'executions')
    cutoff = datetime.now() - timedelta(days=max_age_days)

    # Collect timing data: workflow -> node_type -> [durations]
    by_workflow: Dict[str, Dict[str, List[float]]] = {}
    # Also track per-workflow frame counts and execution counts
    workflow_stats: Dict[str, Dict[str, int]] = {}
    global_node_types: Dict[str, List[float]] = {}
    total_executions = 0
    total_frames = 0

    try:
        entries = os.listdir(executions_dir)
    except OSError:
        entries = []

    for entry_name in entries:
        if not entry_name.endswith('.json'):
            continue

        record_path = os.path.join(executions_dir, entry_name)
        try:
            with open(record_path, 'r', encoding='utf-8') as f:
                record = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            logger.debug(f"[Analytics] Skipping corrupt record {entry_name}: {e}")
            continue

        if not isinstance(record, dict):
            continue

        # Check age
        try:
            record_time = datetime.fromisoformat(record.get('timestamp', ''))
            if record_time < cutoff:
                continue
        except (ValueError, TypeError):
            continue  # Skip records with invalid timestamps

        workflow = record.get('workflow_preset', 'unknown')
        total_executions += 1
        frame_count = record.get('successful', 0)
        total_frames += frame_count

        # Track per-workflow stats
        if workflow not in workflow_stats:
            workflow_stats[workflow] = {"execution_count": 0, "frame_count": 0}
        workflow_stats[workflow]["execution_count"] += 1
        workflow_stats[workflow]["frame_count"] += frame_count

        if workflow not in by_workflow:
            by_workflow[workflow] = {}

        # Process frame timing data
        frames = record.get('frames', [])
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            if not frame.get('success', False):
                continue

            node_timing = frame.get('node_timing', [])
            for node_entry in node_timing:
                if not isinstance(node_entry, dict):
                    continue
                node_type = node_entry.get('node_type', '')
                duration = node_entry.get('duration_ms')
                if not node_type or duration is None:
                    continue

                try:
                    duration = float(duration)
                except (ValueError, TypeError):
                    continue

                # Per-workflow
                if node_type not in by_workflow[workflow]:
                    by_workflow[workflow][node_type] = []
                by_workflow[workflow][node_type].append(duration)

                # Global
                if node_type not in global_node_types:
                    global_node_types[node_type] = []
                global_node_types[node_type].append(duration)

    # Build summary
    summary_by_workflow = {}
    for workflow, node_types in by_workflow.items():
        stats = workflow_stats.get(workflow, {})
        node_type_stats = {}
        for node_type, durations in node_types.items():
            node_type_stats[node_type] = _compute_stats(durations)
        summary_by_workflow[workflow] = {
            "execution_count": stats.get("execution_count", 0),
            "frame_count": stats.get("frame_count", 0),
            "node_types": node_type_stats,
        }

    global_stats = {}
    for node_type, durations in global_node_types.items():
        global_stats[node_type] = _compute_stats(durations)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(),
        "total_executions": total_executions,
        "total_frames": total_frames,
        "by_workflow": summary_by_workflow,
        "global_node_types": global_stats,
    }

    # Write summary report
    report_path = os.path.join(analytics_dir, 'reports', 'node_timing_summary.json')
    if _atomic_write_json(report_path, summary):
        logger.info(
            f"[Analytics] Summary report updated: {total_executions} executions, "
            f"{total_frames} frames, {len(global_stats)} node types"
        )

    return summary


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI entry point for manual report generation."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    import argparse
    parser = argparse.ArgumentParser(description='ComfyUI Workflow Analytics')
    parser.add_argument('--network-path', help='Override network output path')
    parser.add_argument('--max-age-days', type=int, default=90, help='Max age of records in days')
    args = parser.parse_args()

    summary = aggregate_node_timing(
        network_path=args.network_path,
        max_age_days=args.max_age_days,
    )

    if summary:
        print(f"\nTotal executions: {summary.get('total_executions', 0)}")
        print(f"Total frames: {summary.get('total_frames', 0)}")
        print(f"Workflows: {len(summary.get('by_workflow', {}))}")
        print(f"Node types: {len(summary.get('global_node_types', {}))}")

        # Print top node types by average time
        global_nodes = summary.get('global_node_types', {})
        if global_nodes:
            print("\nTop node types by average duration:")
            sorted_nodes = sorted(
                global_nodes.items(),
                key=lambda x: x[1].get('avg_ms', 0),
                reverse=True,
            )
            for node_type, stats in sorted_nodes[:15]:
                print(
                    f"  {node_type:40s}  avg={stats['avg_ms']:>8}ms  "
                    f"p95={stats['p95_ms']:>8}ms  n={stats['count']}"
                )
    else:
        print("No analytics data found or network path unavailable.")


if __name__ == '__main__':
    main()
