"""
Pipeline Event Bus for cross-tab communication.

Provides a central signal hub for decoupled communication between tabs,
enabling ComfyUI and Gallery to know what each other is doing without
tight coupling through direct method calls.

Usage:
    from core.event_bus import pipeline_events

    # Emit an event
    pipeline_events.job_submitted.emit("job123", 5)

    # Listen to an event
    pipeline_events.job_completed.connect(self._on_job_completed)
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


@dataclass
class JobInfo:
    """Information about an active ComfyUI job."""
    job_id: str
    status: str = "pending"  # pending, queued, rendering, completed, failed
    progress: int = 0  # 0-100
    current_node: int = 0
    total_nodes: int = 0
    eta_seconds: Optional[int] = None
    expected_outputs: int = 0
    completed_outputs: int = 0
    output_paths: List[str] = field(default_factory=list)
    job_prefix: str = ""
    workflow_name: str = ""
    start_time: Optional[float] = None


@dataclass
class GalleryContext:
    """Context information from the Gallery tab."""
    selected_paths: List[str] = field(default_factory=list)
    selected_count: int = 0
    active_filter: str = "all"
    current_user: str = ""
    visible: bool = False


class PipelineEventBus(QObject):
    """
    Central event bus for cross-tab communication.

    Signals are organized by direction:
    - ComfyUI -> Gallery: Job status updates
    - Gallery -> ComfyUI: Image selection and settings transfer
    - Bidirectional: Context changes and suggestions
    """

    # =========================================================================
    # ComfyUI -> Gallery Events
    # =========================================================================

    # Emitted periodically during job execution
    # Args: job_id (str), progress_percent (int), status_message (str)
    job_progress = Signal(str, int, str)

    # Emitted when all outputs from a job are complete
    # Args: job_id (str), output_paths (list of str)
    job_completed = Signal(str, list)

    # Emitted when all active jobs are done (batch completion)
    # Args: total_outputs (int), elapsed_seconds (float)
    all_jobs_completed = Signal(int, float)

    # =========================================================================
    # Gallery -> ComfyUI Events
    # =========================================================================

    # Emitted when user wants to use gallery images as ComfyUI inputs
    # Args: paths (list of str)
    use_as_input = Signal(list)

    # Emitted when user wants to copy settings from a gallery item
    # Args: metadata (dict)
    copy_settings = Signal(dict)

    # =========================================================================
    # Gallery Events
    # =========================================================================

    # Emitted to request gallery refresh (e.g., after settings change)
    # Args: force (bool) - if True, forces full refresh ignoring cache
    gallery_refresh_requested = Signal(bool)

    # =========================================================================
    # Viewer Events (for image viewers to request gallery actions)
    # =========================================================================

    # Emitted to view the input/source image for an output
    # Args: input_path (str)
    view_input_image = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_jobs: Dict[str, JobInfo] = {}
        self._jobs_lock = threading.RLock()  # Thread safety for job tracking
        self._gallery_context = GalleryContext()
        self._gallery_context_lock = threading.RLock()
        logger.debug("PipelineEventBus initialized")

    # =========================================================================
    # Job Tracking Methods
    # =========================================================================

    def register_job(self, job_id: str, expected_outputs: int, job_prefix: str = "",
                     workflow_name: str = "") -> JobInfo:
        """
        Register a new job for tracking.

        Thread-safe: Uses lock for job dictionary access.

        Args:
            job_id: Deadline job ID
            expected_outputs: Number of expected output files
            job_prefix: Prefix for grouping in gallery
            workflow_name: Name of the workflow preset

        Returns:
            JobInfo object for the registered job
        """
        import time
        job_info = JobInfo(
            job_id=job_id,
            expected_outputs=expected_outputs,
            job_prefix=job_prefix,
            workflow_name=workflow_name,
            start_time=time.time()
        )
        with self._jobs_lock:
            self._active_jobs[job_id] = job_info
        logger.info(f"Registered job {job_id}: {expected_outputs} outputs expected")
        return job_info

    def update_job_progress(self, job_id: str, progress: int, status: str,
                            current_node: int = 0, total_nodes: int = 0,
                            eta_seconds: Optional[int] = None) -> None:
        """
        Update progress for a tracked job.

        Thread-safe: Uses lock for job dictionary access.

        Args:
            job_id: Deadline job ID
            progress: Progress percentage (0-100)
            status: Status string (e.g., "rendering", "queued")
            current_node: Current node being processed
            total_nodes: Total nodes in workflow
            eta_seconds: Estimated time remaining
        """
        completed_outputs = 0
        with self._jobs_lock:
            job = self._active_jobs.get(job_id)
            if job:
                job.progress = progress
                job.status = status
                job.current_node = current_node
                job.total_nodes = total_nodes
                job.eta_seconds = eta_seconds
                completed_outputs = job.completed_outputs

        # Build storytelling message (outside lock - no mutation, uses captured values)
        message = self._build_progress_story(job_id, progress, status,
                                             current_node, total_nodes, eta_seconds,
                                             completed_outputs)
        self.job_progress.emit(job_id, progress, message)

    def record_job_output(self, job_id: str, output_path: str) -> None:
        """
        Record that an output file is ready.

        Thread-safe: Uses lock for job dictionary access.

        Args:
            job_id: Deadline job ID
            output_path: Path to the completed output file
        """
        with self._jobs_lock:
            if job_id in self._active_jobs:
                job = self._active_jobs[job_id]
                if output_path not in job.output_paths:
                    job.output_paths.append(output_path)
                    job.completed_outputs = len(job.output_paths)

        logger.debug(f"Job {job_id} output ready: {output_path}")

    def complete_job(self, job_id: str, success: bool = True,
                     error_message: str = "") -> None:
        """
        Mark a job as completed.

        Thread-safe: Uses lock for job dictionary access.

        Args:
            job_id: Deadline job ID
            success: Whether the job completed successfully
            error_message: Error message if failed
        """
        output_paths = []
        job_found = False
        with self._jobs_lock:
            if job_id in self._active_jobs:
                job_found = True
                job = self._active_jobs[job_id]
                job.status = "completed" if success else "failed"
                job.progress = 100 if success else job.progress
                output_paths = list(job.output_paths)

        # Emit signals outside lock to avoid deadlock
        if job_found:
            if success:
                self.job_completed.emit(job_id, output_paths)
                logger.info(f"Job {job_id} completed: {len(output_paths)} outputs")
            else:
                # job_failed signal was removed (no listeners). Failures are
                # surfaced via per-tab status bars, not the bus.
                logger.warning(f"Job {job_id} failed: {error_message}")

            # Check if all jobs are done; clean up completed jobs afterward
            self._check_all_jobs_completed()

    def remove_job(self, job_id: str) -> None:
        """Remove a job from tracking. Thread-safe."""
        with self._jobs_lock:
            if job_id in self._active_jobs:
                del self._active_jobs[job_id]
                logger.debug(f"Removed job {job_id} from tracking")

    def get_active_jobs(self) -> Dict[str, JobInfo]:
        """Get all currently tracked jobs. Thread-safe."""
        with self._jobs_lock:
            return self._active_jobs.copy()

    def get_job_info(self, job_id: str) -> Optional[JobInfo]:
        """Get info for a specific job. Thread-safe."""
        with self._jobs_lock:
            return self._active_jobs.get(job_id)

    def has_active_jobs(self) -> bool:
        """Check if there are any active (non-completed) jobs. Thread-safe."""
        with self._jobs_lock:
            return any(
                job.status not in ("completed", "failed")
                for job in self._active_jobs.values()
            )

    def get_aggregate_progress(self) -> Dict[str, Any]:
        """
        Get aggregate progress across all active jobs.

        Thread-safe: Uses lock for job dictionary access.

        Returns:
            Dict with keys: total_jobs, completed_jobs, rendering_jobs,
            queued_jobs, total_expected, total_completed, avg_progress
        """
        with self._jobs_lock:
            jobs = list(self._active_jobs.values())
        if not jobs:
            return {
                "total_jobs": 0,
                "completed_jobs": 0,
                "rendering_jobs": 0,
                "queued_jobs": 0,
                "failed_jobs": 0,
                "total_expected": 0,
                "total_completed": 0,
                "avg_progress": 0
            }

        completed = sum(1 for j in jobs if j.status == "completed")
        rendering = sum(1 for j in jobs if j.status == "rendering")
        queued = sum(1 for j in jobs if j.status in ("pending", "queued"))
        failed = sum(1 for j in jobs if j.status == "failed")

        total_expected = sum(j.expected_outputs for j in jobs)
        total_completed = sum(j.completed_outputs for j in jobs)

        active_jobs = [j for j in jobs if j.status not in ("completed", "failed")]
        avg_progress = (
            sum(j.progress for j in active_jobs) // len(active_jobs)
            if active_jobs else 100
        )

        return {
            "total_jobs": len(jobs),
            "completed_jobs": completed,
            "rendering_jobs": rendering,
            "queued_jobs": queued,
            "failed_jobs": failed,
            "total_expected": total_expected,
            "total_completed": total_completed,
            "avg_progress": avg_progress
        }

    # =========================================================================
    # Gallery Context Methods
    # =========================================================================

    def update_gallery_context(self, **kwargs) -> None:
        """
        Update gallery context information.

        Args:
            selected_paths: List of selected image paths
            selected_count: Number of selected items
            active_filter: Current filter (all, liked, etc.)
            current_user: User whose gallery is being viewed
            visible: Whether gallery tab is visible
        """
        with self._gallery_context_lock:
            for key, value in kwargs.items():
                if hasattr(self._gallery_context, key):
                    setattr(self._gallery_context, key, value)

    def get_gallery_context(self) -> GalleryContext:
        """Get a snapshot of the current gallery context.

        Returns a copy — handing out the shared mutable dataclass let
        callers read fields outside the lock while update_gallery_context()
        mutated the same object (every other accessor here returns copies).
        """
        import copy
        with self._gallery_context_lock:
            return copy.copy(self._gallery_context)

    # =========================================================================
    # Storytelling / Message Helpers
    # =========================================================================

    def _build_progress_story(self, job_id: str, progress: int, status: str,
                              current_node: int, total_nodes: int,
                              eta_seconds: Optional[int],
                              completed_outputs: int = 0) -> str:
        """
        Build an engaging progress message instead of bare percentages.

        Returns a contextual, human-friendly progress message.
        """
        if status == "queued" or status == "pending":
            # Count jobs ahead (thread-safe)
            with self._jobs_lock:
                jobs = list(self._active_jobs.values())
            position = next(
                (i + 1 for i, j in enumerate(jobs)
                 if j.job_id == job_id and j.status in ("queued", "pending")),
                None
            )
            if position and position > 1:
                return f"In line... {position - 1} job(s) ahead"
            return "Next in line, preparing..."

        elif status == "loading_model":
            return "Warming up the AI model..."

        elif status == "rendering":
            # Build engaging render message
            node_info = ""
            if total_nodes > 0:
                node_info = f" (node {current_node}/{total_nodes})"

            eta_info = ""
            if eta_seconds is not None and eta_seconds > 0:
                if eta_seconds < 60:
                    eta_info = f" ~{eta_seconds}s left"
                else:
                    minutes = eta_seconds // 60
                    eta_info = f" ~{minutes}m left"

            if progress < 25:
                return f"Starting generation... {progress}%{node_info}"
            elif progress < 75:
                return f"Creating magic... {progress}%{node_info}{eta_info}"
            else:
                return f"Almost there! {progress}%{node_info}{eta_info}"

        elif status == "completed":
            if completed_outputs > 0:
                return f"Done! {completed_outputs} new image(s) ready"
            return "Complete!"

        elif status == "failed":
            return "Generation failed"

        return f"{status}: {progress}%"

    def _check_all_jobs_completed(self) -> None:
        """Check if all tracked jobs are done and emit signal if so. Thread-safe.

        Cleans up completed/failed jobs after emitting all_jobs_completed
        to prevent unbounded memory growth and duplicate signal emissions.

        The entire check-and-cleanup runs under a single lock hold to prevent
        a race where register_job() sneaks in between the check and cleanup.
        """
        import time
        with self._jobs_lock:
            jobs = list(self._active_jobs.values())
            if not jobs:
                return

            if not all(j.status in ("completed", "failed") for j in jobs):
                return

            total_outputs = sum(j.completed_outputs for j in jobs)

            # Calculate elapsed time from earliest job
            start_times = [j.start_time for j in jobs if j.start_time]
            elapsed = time.time() - min(start_times) if start_times else 0.0

            # Clean up finished jobs under the same lock hold
            for j in jobs:
                self._active_jobs.pop(j.job_id, None)

        # Emit outside lock to avoid deadlock with signal handlers
        self.all_jobs_completed.emit(total_outputs, elapsed)
        logger.info(f"All jobs completed: {total_outputs} outputs in {elapsed:.1f}s")


# Lazy singleton — instantiated on first access so a QApplication doesn't need
# to exist at import time (fixes test environments and top-level imports).
_pipeline_events: Optional[PipelineEventBus] = None
_pipeline_events_lock = threading.RLock()


def get_pipeline_events() -> PipelineEventBus:
    """
    Get the global pipeline event bus instance (created lazily on first call).

    Thread-safe via double-checked locking pattern.

    Returns:
        PipelineEventBus: The global event bus
    """
    global _pipeline_events
    if _pipeline_events is None:
        with _pipeline_events_lock:
            if _pipeline_events is None:
                _pipeline_events = PipelineEventBus()
    return _pipeline_events


# Backward-compatible module-level alias.
# NOTE: Code that accesses ``pipeline_events`` at *import time* (e.g. at module
# scope) should use ``get_pipeline_events()`` instead so instantiation is deferred
# until a QApplication exists.
class _LazyProxy:
    """Transparent proxy that defers PipelineEventBus creation until first attribute access."""
    def __getattr__(self, name):
        return getattr(get_pipeline_events(), name)

pipeline_events: PipelineEventBus = _LazyProxy()  # type: ignore[assignment]
