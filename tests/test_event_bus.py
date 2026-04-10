"""Tests for core.event_bus — JobInfo, GalleryContext, PipelineEventBus job tracking."""

import threading

import pytest

# PipelineEventBus requires PySide6 (QObject + Signal). We test what we can.
try:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    PYSIDE_AVAILABLE = True
except (ImportError, RuntimeError):
    PYSIDE_AVAILABLE = False

from core.event_bus import JobInfo, GalleryContext

# Conditionally import the bus itself
if PYSIDE_AVAILABLE:
    from core.event_bus import PipelineEventBus


# ============================================================================
# JobInfo dataclass
# ============================================================================

class TestJobInfo:
    def test_defaults(self):
        job = JobInfo(job_id="abc123")
        assert job.job_id == "abc123"
        assert job.status == "pending"
        assert job.progress == 0
        assert job.expected_outputs == 0
        assert job.completed_outputs == 0
        assert job.output_paths == []
        assert job.job_prefix == ""
        assert job.workflow_name == ""
        assert job.start_time is None

    def test_full_init(self):
        job = JobInfo(
            job_id="x",
            status="rendering",
            progress=50,
            current_node=3,
            total_nodes=10,
            eta_seconds=120,
            expected_outputs=5,
            completed_outputs=2,
            output_paths=["/a.png", "/b.png"],
            job_prefix="upscale",
            workflow_name="my_wf",
            start_time=1000.0,
        )
        assert job.progress == 50
        assert job.eta_seconds == 120
        assert len(job.output_paths) == 2

    def test_output_paths_independent(self):
        """Each instance should have its own list."""
        j1 = JobInfo(job_id="a")
        j2 = JobInfo(job_id="b")
        j1.output_paths.append("/x.png")
        assert j2.output_paths == []


# ============================================================================
# GalleryContext dataclass
# ============================================================================

class TestGalleryContext:
    def test_defaults(self):
        ctx = GalleryContext()
        assert ctx.selected_paths == []
        assert ctx.selected_count == 0
        assert ctx.active_filter == "all"
        assert ctx.current_user == ""
        assert ctx.visible is False

    def test_custom_values(self):
        ctx = GalleryContext(
            selected_paths=["/a.png"],
            selected_count=1,
            active_filter="liked",
            visible=True,
        )
        assert ctx.selected_count == 1
        assert ctx.active_filter == "liked"


# ============================================================================
# PipelineEventBus (requires PySide6)
# ============================================================================

@pytest.mark.skipif(not PYSIDE_AVAILABLE, reason="PySide6 not available")
class TestPipelineEventBus:
    def setup_method(self):
        self.bus = PipelineEventBus()

    def test_register_job(self):
        job = self.bus.register_job("job1", 5, "prefix", "workflow")
        assert job.job_id == "job1"
        assert job.expected_outputs == 5
        assert job.job_prefix == "prefix"
        assert job.start_time is not None
        assert self.bus.get_job_info("job1") is not None

    def test_update_job_progress(self):
        self.bus.register_job("job1", 5)
        self.bus.update_job_progress("job1", 50, "rendering", 3, 10, 60)
        job = self.bus.get_job_info("job1")
        assert job.progress == 50
        assert job.status == "rendering"
        assert job.current_node == 3

    def test_record_job_output(self):
        self.bus.register_job("job1", 3)
        self.bus.record_job_output("job1", "/output/a.png")
        self.bus.record_job_output("job1", "/output/b.png")
        job = self.bus.get_job_info("job1")
        assert job.completed_outputs == 2
        assert "/output/a.png" in job.output_paths

    def test_record_output_deduplicates(self):
        self.bus.register_job("job1", 3)
        self.bus.record_job_output("job1", "/output/a.png")
        self.bus.record_job_output("job1", "/output/a.png")
        job = self.bus.get_job_info("job1")
        assert job.completed_outputs == 1

    def test_complete_job_success(self):
        self.bus.register_job("job1", 1)
        self.bus.complete_job("job1", success=True)
        job = self.bus.get_job_info("job1")
        assert job.status == "completed"
        assert job.progress == 100

    def test_complete_job_failure(self):
        self.bus.register_job("job1", 1)
        self.bus.complete_job("job1", success=False, error_message="OOM")
        job = self.bus.get_job_info("job1")
        assert job.status == "failed"

    def test_remove_job(self):
        self.bus.register_job("job1", 1)
        self.bus.remove_job("job1")
        assert self.bus.get_job_info("job1") is None

    def test_get_active_jobs(self):
        self.bus.register_job("job1", 1)
        self.bus.register_job("job2", 2)
        jobs = self.bus.get_active_jobs()
        assert len(jobs) == 2

    def test_has_active_jobs(self):
        assert self.bus.has_active_jobs() is False
        self.bus.register_job("job1", 1)
        assert self.bus.has_active_jobs() is True
        self.bus.complete_job("job1")
        assert self.bus.has_active_jobs() is False

    def test_aggregate_progress_empty(self):
        agg = self.bus.get_aggregate_progress()
        assert agg["total_jobs"] == 0
        assert agg["avg_progress"] == 0

    def test_aggregate_progress(self):
        self.bus.register_job("j1", 3)
        self.bus.register_job("j2", 2)
        self.bus.update_job_progress("j1", 60, "rendering")
        self.bus.update_job_progress("j2", 40, "rendering")
        agg = self.bus.get_aggregate_progress()
        assert agg["total_jobs"] == 2
        assert agg["rendering_jobs"] == 2
        assert agg["avg_progress"] == 50

    def test_gallery_context(self):
        self.bus.update_gallery_context(selected_count=3, visible=True)
        ctx = self.bus.get_gallery_context()
        assert ctx.selected_count == 3
        assert ctx.visible is True

    def test_build_progress_story_queued(self):
        self.bus.register_job("j1", 1)
        msg = self.bus._build_progress_story("j1", 0, "queued", 0, 0, None)
        assert "line" in msg.lower() or "preparing" in msg.lower()

    def test_build_progress_story_rendering(self):
        msg = self.bus._build_progress_story("j1", 50, "rendering", 5, 10, 30)
        assert "50%" in msg

    def test_build_progress_story_loading(self):
        msg = self.bus._build_progress_story("j1", 0, "loading_model", 0, 0, None)
        assert "model" in msg.lower()


@pytest.mark.skipif(not PYSIDE_AVAILABLE, reason="PySide6 not available")
class TestEventBusThreadSafety:
    def test_concurrent_job_operations(self):
        bus = PipelineEventBus()
        errors = []

        def worker(i):
            try:
                jid = f"job_{i}"
                bus.register_job(jid, 3)
                bus.update_job_progress(jid, 50, "rendering")
                bus.record_job_output(jid, f"/out/{i}.png")
                bus.complete_job(jid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(bus.get_active_jobs()) == 10
