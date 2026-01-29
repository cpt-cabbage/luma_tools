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

    # Emitted when a job is submitted to Deadline
    # Args: job_id (str), expected_output_count (int), job_prefix (str)
    job_submitted = Signal(str, int, str)

    # Emitted periodically during job execution
    # Args: job_id (str), progress_percent (int), status_message (str)
    job_progress = Signal(str, int, str)

    # Emitted when a single output file is ready
    # Args: job_id (str), output_path (str)
    job_output_ready = Signal(str, str)

    # Emitted when all outputs from a job are complete
    # Args: job_id (str), output_paths (list of str)
    job_completed = Signal(str, list)

    # Emitted when a job fails
    # Args: job_id (str), error_message (str)
    job_failed = Signal(str, str)

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

    # Emitted when gallery selection changes
    # Args: selected_paths (list of str), selected_count (int)
    selection_changed = Signal(list, int)

    # =========================================================================
    # Bidirectional / Context Events
    # =========================================================================

    # Emitted when either tab's context changes significantly
    # Args: source (str: "comfyui" or "gallery"), context_data (dict)
    context_changed = Signal(str, dict)

    # Emitted to show a user hint/suggestion
    # Args: hint_type (str), message (str), action_data (dict or None)
    show_hint = Signal(str, str, object)

    # Emitted when user reaches a milestone
    # Args: milestone_type (str), count (int)
    milestone_reached = Signal(str, int)

    # Emitted to request tab switch
    # Args: tab_name (str), context (dict or None)
    request_tab_switch = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_jobs: Dict[str, JobInfo] = {}
        self._gallery_context = GalleryContext()
        logger.debug("PipelineEventBus initialized")

    # =========================================================================
    # Job Tracking Methods
    # =========================================================================

    def register_job(self, job_id: str, expected_outputs: int, job_prefix: str = "",
                     workflow_name: str = "") -> JobInfo:
        """
        Register a new job for tracking.

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
        self._active_jobs[job_id] = job_info
        logger.info(f"Registered job {job_id}: {expected_outputs} outputs expected")
        self.job_submitted.emit(job_id, expected_outputs, job_prefix)
        return job_info

    def update_job_progress(self, job_id: str, progress: int, status: str,
                            current_node: int = 0, total_nodes: int = 0,
                            eta_seconds: Optional[int] = None) -> None:
        """
        Update progress for a tracked job.

        Args:
            job_id: Deadline job ID
            progress: Progress percentage (0-100)
            status: Status string (e.g., "rendering", "queued")
            current_node: Current node being processed
            total_nodes: Total nodes in workflow
            eta_seconds: Estimated time remaining
        """
        if job_id in self._active_jobs:
            job = self._active_jobs[job_id]
            job.progress = progress
            job.status = status
            job.current_node = current_node
            job.total_nodes = total_nodes
            job.eta_seconds = eta_seconds

        # Build storytelling message
        message = self._build_progress_story(job_id, progress, status,
                                             current_node, total_nodes, eta_seconds)
        self.job_progress.emit(job_id, progress, message)

    def record_job_output(self, job_id: str, output_path: str) -> None:
        """
        Record that an output file is ready.

        Args:
            job_id: Deadline job ID
            output_path: Path to the completed output file
        """
        if job_id in self._active_jobs:
            job = self._active_jobs[job_id]
            if output_path not in job.output_paths:
                job.output_paths.append(output_path)
                job.completed_outputs = len(job.output_paths)

        self.job_output_ready.emit(job_id, output_path)
        logger.debug(f"Job {job_id} output ready: {output_path}")

    def complete_job(self, job_id: str, success: bool = True,
                     error_message: str = "") -> None:
        """
        Mark a job as completed.

        Args:
            job_id: Deadline job ID
            success: Whether the job completed successfully
            error_message: Error message if failed
        """
        if job_id in self._active_jobs:
            job = self._active_jobs[job_id]
            job.status = "completed" if success else "failed"
            job.progress = 100 if success else job.progress

            if success:
                self.job_completed.emit(job_id, job.output_paths)
                logger.info(f"Job {job_id} completed: {len(job.output_paths)} outputs")
            else:
                self.job_failed.emit(job_id, error_message)
                logger.warning(f"Job {job_id} failed: {error_message}")

            # Check if all jobs are done
            self._check_all_jobs_completed()

    def remove_job(self, job_id: str) -> None:
        """Remove a job from tracking."""
        if job_id in self._active_jobs:
            del self._active_jobs[job_id]
            logger.debug(f"Removed job {job_id} from tracking")

    def get_active_jobs(self) -> Dict[str, JobInfo]:
        """Get all currently tracked jobs."""
        return self._active_jobs.copy()

    def get_job_info(self, job_id: str) -> Optional[JobInfo]:
        """Get info for a specific job."""
        return self._active_jobs.get(job_id)

    def has_active_jobs(self) -> bool:
        """Check if there are any active (non-completed) jobs."""
        return any(
            job.status not in ("completed", "failed")
            for job in self._active_jobs.values()
        )

    def get_aggregate_progress(self) -> Dict[str, Any]:
        """
        Get aggregate progress across all active jobs.

        Returns:
            Dict with keys: total_jobs, completed_jobs, rendering_jobs,
            queued_jobs, total_expected, total_completed, avg_progress
        """
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
        for key, value in kwargs.items():
            if hasattr(self._gallery_context, key):
                setattr(self._gallery_context, key, value)

        self.context_changed.emit("gallery", {
            "selected_paths": self._gallery_context.selected_paths,
            "selected_count": self._gallery_context.selected_count,
            "active_filter": self._gallery_context.active_filter,
            "current_user": self._gallery_context.current_user,
            "visible": self._gallery_context.visible
        })

    def get_gallery_context(self) -> GalleryContext:
        """Get current gallery context."""
        return self._gallery_context

    # =========================================================================
    # Storytelling / Message Helpers
    # =========================================================================

    def _build_progress_story(self, job_id: str, progress: int, status: str,
                              current_node: int, total_nodes: int,
                              eta_seconds: Optional[int]) -> str:
        """
        Build an engaging progress message instead of bare percentages.

        Returns a contextual, human-friendly progress message.
        """
        if status == "queued" or status == "pending":
            # Count jobs ahead
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
            job = self._active_jobs.get(job_id)
            if job:
                return f"Done! {job.completed_outputs} new image(s) ready"
            return "Complete!"

        elif status == "failed":
            return "Generation failed"

        return f"{status}: {progress}%"

    def _check_all_jobs_completed(self) -> None:
        """Check if all tracked jobs are done and emit signal if so."""
        jobs = list(self._active_jobs.values())
        if not jobs:
            return

        all_done = all(j.status in ("completed", "failed") for j in jobs)
        if all_done:
            import time
            total_outputs = sum(j.completed_outputs for j in jobs)

            # Calculate elapsed time from earliest job
            start_times = [j.start_time for j in jobs if j.start_time]
            if start_times:
                elapsed = time.time() - min(start_times)
            else:
                elapsed = 0.0

            self.all_jobs_completed.emit(total_outputs, elapsed)
            logger.info(f"All jobs completed: {total_outputs} outputs in {elapsed:.1f}s")


# Global event bus instance
pipeline_events = PipelineEventBus()


def get_pipeline_events() -> PipelineEventBus:
    """
    Get the global pipeline event bus instance.

    Returns:
        PipelineEventBus: The global event bus
    """
    return pipeline_events
