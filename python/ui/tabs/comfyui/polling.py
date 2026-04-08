"""
ComfyUI polling logic for job status monitoring.

Provides mixin classes for iterate and batch mode polling.
Emits events through the PipelineEventBus for cross-tab communication.
"""
import os
import time
import logging
import threading
from PySide6.QtCore import QTimer, QThreadPool, Qt
from dialog_helpers import confirm_action

logger = logging.getLogger(__name__)

from core.import_utils import get_event_bus
pipeline_events, EVENT_BUS_AVAILABLE = get_event_bus()


def play_completion_sound():
    """Play a sound notification for job completion if enabled in settings."""
    from core.settings_manager import safe_get_setting

    sound_option = safe_get_setting("comfyui_completion_sound", "none")
    if sound_option == "none":
        return

    try:
        if sound_option == "system":
            # Use system notification sound
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        elif sound_option == "subtle":
            # Use a subtle beep
            import winsound
            winsound.Beep(800, 150)  # 800 Hz for 150ms
        # Future: could add custom sound file support here
    except Exception as e:
        logger.debug(f"Could not play completion sound: {e}")


def format_elapsed_time(seconds):
    """Format elapsed time in a human-readable way."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def pluralize_output_type(output_type: str, count: int = 2) -> str:
    """Convert output type to plural form for notifications.

    Args:
        output_type: Output type ("image", "video", "3d", "audio", "other")
        count: Number of items (for singular vs plural)

    Returns:
        Pluralized string like "images", "videos", "models", etc.
    """
    if count == 1:
        if output_type == "3d":
            return "model"
        elif output_type == "audio":
            return "audio file"
        else:
            return output_type

    # Plural forms
    if output_type == "image":
        return "images"
    elif output_type == "video":
        return "videos"
    elif output_type == "3d":
        return "models"
    elif output_type == "audio":
        return "audio files"
    else:
        return "outputs"


def estimate_remaining_time(completed, total, elapsed_seconds):
    """Estimate remaining time based on progress."""
    if completed <= 0 or elapsed_seconds <= 0:
        return None
    rate = completed / elapsed_seconds
    remaining_tasks = total - completed
    if rate > 0:
        remaining_seconds = remaining_tasks / rate
        return format_elapsed_time(remaining_seconds)
    return None


def _get_poll_interval_ms():
    """Get Deadline poll interval from global settings (in milliseconds)."""
    from core.settings_manager import safe_get_setting
    return safe_get_setting("deadline_poll_interval", 5) * 1000


class PollingMixin:
    """
    Mixin providing job polling functionality for ComfyUI tab.

    Requires the following attributes on the class using this mixin:
    - self.ui: The UI object with ComfyUI widgets
    - self.main_window: Main window reference
    - self.app_state: Application state
    - self.widget_manager: UI manager with dynamic_widgets dict
    - self.animator: Animation controller
    - self.show_status(): Status display method
    """

    def _init_polling_state(self):
        """Initialize polling state variables. Call from __init__."""
        # Iterate mode state
        self._iterate_poll_timer = None
        self._iterate_poll_worker = None
        self._iterate_network_output_dir = ""
        self._iterate_poll_count = 0
        self._iterate_completed_tasks = 0
        self._iterate_total_tasks = 1
        self._iterate_start_time = None
        self._iterate_rendering_start_time = None  # Track when rendering actually started
        self._iterate_output_type = "image"  # Track output type for notifications
        self._iterate_saw_active = False  # True once job has been seen as Active/Rendering

        # Batch mode state
        self._batch_poll_timer = None
        self._batch_job_ids = []
        self._batch_pending_jobs = set()
        self._batch_failed_jobs = set()
        self._batch_completed_tasks = {}
        self._batch_total_tasks = {}
        self._batch_job_statuses = {}
        self._batch_network_output_dir = ""
        self._batch_output_type = "image"  # Track output type for notifications
        self._batch_poll_count = 0
        self._batch_start_time = None
        self._batch_generation_count = 1
        self._batch_poll_pending_results = 0
        self._batch_poll_results = {}
        self._batch_poll_workers = []
        self._batch_poll_lock = threading.RLock()  # Protects pending counter + results dict
        self._batch_recovery_mode = False  # Track if we're recovering from app restart
        self._batch_jobs_seen_active = set()  # Per-job tracking of Active/Rendering

        # Recovery state
        self._recovery_worker = None
        self._recovery_persisted_state = None

    # =========================================================================
    # ITERATE MODE POLLING
    # =========================================================================

    def _start_iterate_polling(self, job_id, network_output_dir, output_type="image"):
        """Start polling for iterate mode job completion.

        Args:
            job_id: The Deadline job ID to poll
            network_output_dir: Path where outputs will be saved
            output_type: Type of output ("image", "video", "3d", "audio", "other")
        """
        from ui_components import StatusColors

        self.app_state.comfyui_current_job_id = job_id
        self._iterate_network_output_dir = network_output_dir
        self._iterate_output_type = output_type
        self._iterate_poll_count = 0
        self._iterate_completed_tasks = 0
        self._iterate_total_tasks = self.ui.ComfyUIGenerationCount.value()
        self._iterate_start_time = time.time()
        self._iterate_rendering_start_time = None  # Reset to avoid stale model-loading detection
        self._iterate_saw_active = False

        logger.info(f"[Iterate] Starting polling for job {job_id}")
        logger.info(f"[Iterate] Network output dir: {network_output_dir}")
        logger.info(f"[Iterate] Expected jobs: {self._iterate_total_tasks}")

        self.main_window.start_status_spinner()

        self.ui.ComfyUIIterateStatus.setText("Job submitted, waiting for Deadline...")
        self.ui.ComfyUIIterateProgress.setValue(0)
        self.ui.ComfyUIUseAsInput.setEnabled(False)

        gen_count = self._iterate_total_tasks
        self.animator.update_status_animated(
            f"ComfyUI: Submitted {gen_count} job(s) - Waiting for worker...",
            StatusColors.INFO
        )

        if self._iterate_poll_timer is None:
            self._iterate_poll_timer = QTimer(self.main_window)
            self._iterate_poll_timer.timeout.connect(self._poll_iterate_job)

        self._iterate_poll_timer.start(_get_poll_interval_ms())
        self._update_cancel_button_visibility()

        # Save job state for recovery on app restart (after timer is started)
        self._save_running_job_state()

        # Emit event for cross-tab awareness
        if EVENT_BUS_AVAILABLE:
            job_prefix = getattr(self, '_current_job_prefix', '')
            workflow_name = getattr(self, '_current_preset_name', '')
            pipeline_events.register_job(
                job_id, gen_count, job_prefix=job_prefix, workflow_name=workflow_name
            )

        self._poll_iterate_job()

    def _poll_iterate_job(self):
        """Poll the iterate job status."""
        from ui_components import Worker
        from deadline.poller import poll_deadline_job_status

        job_id = self.app_state.comfyui_current_job_id
        if not job_id:
            self._stop_iterate_polling()
            return

        output_dir = self._iterate_network_output_dir
        # Store worker to prevent garbage collection
        self._iterate_poll_worker = Worker(poll_deadline_job_status, job_id, output_dir)
        self._iterate_poll_worker.signals.result.connect(self._on_iterate_poll_result)
        self._iterate_poll_worker.signals.error.connect(lambda msg, tb: logger.warning(f"Poll error: {msg}"))
        QThreadPool.globalInstance().start(self._iterate_poll_worker)

    def _on_iterate_poll_result(self, result):
        """Handle iterate poll result."""
        try:
            self._handle_iterate_poll_result(result)
        except Exception as e:
            logger.error(f"ERROR in _on_iterate_poll_result: {e}", exc_info=True)
            self._stop_iterate_polling()

    def _handle_iterate_poll_result(self, result):
        """Process iterate poll result and update UI."""
        from ui_components import StatusColors

        status = result.get("status", "Unknown")
        progress = result.get("progress", 0)
        completed_tasks = result.get("completed_tasks", 0)
        total_tasks = result.get("total_tasks", 1)
        error_message = result.get("error_message", "")
        task_progress = result.get("task_progress")
        is_loading_model = result.get("is_loading_model", False)

        display_total = max(total_tasks, self._iterate_total_tasks)

        # Track when rendering actually starts
        if status in ("Active", "Rendering"):
            self._iterate_saw_active = True
            if self._iterate_rendering_start_time is None:
                self._iterate_rendering_start_time = time.time()
                logger.debug(f"[Iterate Poll] Rendering started at {time.time()}")

        # Infer model loading if rendering but no progress for a while
        # If we've been rendering for >5 seconds with no task progress, assume loading models
        if status in ("Active", "Rendering") and not task_progress and self._iterate_rendering_start_time:
            rendering_elapsed = time.time() - self._iterate_rendering_start_time
            if rendering_elapsed > 5:  # After 5 seconds with no progress, assume loading models
                is_loading_model = True
                logger.debug(f"[Iterate Poll] Inferring model loading (rendering for {int(rendering_elapsed)}s with no progress)")

        # If we got task progress, models are loaded - reset the flag for next job
        if task_progress and task_progress.get('current_node', 0) > 0:
            self._iterate_rendering_start_time = None

        logger.debug(f"[Iterate Poll] Status: {status}, Progress: {progress}%, Tasks: {completed_tasks}/{display_total}")

        elapsed = time.time() - self._iterate_start_time if self._iterate_start_time else 0
        elapsed_str = format_elapsed_time(elapsed)

        if completed_tasks > self._iterate_completed_tasks:
            new_frames = completed_tasks - self._iterate_completed_tasks
            logger.info(f"[Iterate] {new_frames} new job(s) rendered! ({completed_tasks}/{display_total})")
            self._iterate_completed_tasks = completed_tasks
            self._refresh_gallery_for_new_frames("[Iterate]")

            # Emit output ready events for each new frame
            if EVENT_BUS_AVAILABLE:
                job_id = self.app_state.comfyui_current_job_id
                # Note: We don't have individual paths here, but we signal progress
                pipeline_events.update_job_progress(
                    job_id, progress, "rendering",
                    current_node=task_progress.get('current_node', 0) if task_progress else 0,
                    total_nodes=task_progress.get('total_nodes', 0) if task_progress else 0
                )
                # Update app_state for cross-tab awareness
                from core.state_manager import app_state
                app_state.increment_gallery_new_count(new_frames)

        # Blend node-level progress into progress bar for smoother feedback
        # For single-task jobs, progress jumps 0%→100% without this
        display_progress = progress
        if task_progress and completed_tasks < display_total:
            task_pct = task_progress.get('progress_pct', 0)
            # Cap at 99% so 100% only appears on Deadline-confirmed completion
            display_progress = min(99, int((completed_tasks * 100 + task_pct) / display_total))

        self.ui.ComfyUIIterateProgress.setValue(display_progress)
        self._iterate_poll_count += 1

        if status == "Completed":
            self._stop_iterate_polling()
            self._on_iterate_job_completed()
        elif status == "Failed":
            self._stop_iterate_polling()
            self.ui.ComfyUIIterateStatus.setText(f"Job failed: {error_message}")
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #ef4444;")
            self.animator.update_status_animated(
                f"ComfyUI Failed: {error_message}",
                StatusColors.ERROR
            )
        elif status == "Unknown":
            # Job not found in Deadline — could be: (a) not yet registered,
            # (b) completed and auto-deleted, or (c) transient Deadline error.
            if self._iterate_saw_active and completed_tasks >= display_total:
                # Job was running and all tasks completed before it disappeared
                logger.info(f"[Iterate Poll] Job was active with {completed_tasks}/{display_total} tasks done, treating as completed")
                self._stop_iterate_polling()
                self._on_iterate_job_completed()
            elif self._iterate_saw_active:
                # Job was running but disappeared — check for output files
                from comfyui.metadata import get_job_output_files
                output_dir = self._iterate_network_output_dir
                if output_dir:
                    output_files = get_job_output_files(output_dir, min_mtime=self._iterate_start_time)
                    if output_files:
                        logger.info(f"[Iterate Poll] Job disappeared but found {len(output_files)} output file(s), treating as completed")
                        self._stop_iterate_polling()
                        self._on_iterate_job_completed()
                        return
                logger.warning(f"[Iterate Poll] Job was active but disappeared with no output, treating as lost")
                self._stop_iterate_polling()
                self.ui.ComfyUIIterateStatus.setText(f"Job lost: {error_message}")
                self.ui.ComfyUIIterateStatus.setStyleSheet("color: #ef4444;")
                self.animator.update_status_animated(
                    "ComfyUI: Job disappeared from Deadline",
                    StatusColors.ERROR
                )
            elif self._iterate_poll_count <= 6:
                # Never saw the job active, still in grace period for registration
                logger.debug(f"[Iterate Poll] Job not found on poll #{self._iterate_poll_count}, likely still registering")
                self.ui.ComfyUIIterateStatus.setText("Waiting for Deadline to register job...")
                self.ui.ComfyUIIterateStatus.setStyleSheet("color: #4a9eff;")
                self.animator.update_status_animated(
                    "ComfyUI: Waiting for job to appear in Deadline...",
                    StatusColors.INFO
                )
            else:
                logger.warning(f"[Iterate Poll] Job not found after {self._iterate_poll_count} polls, treating as lost")
                self._stop_iterate_polling()
                self.ui.ComfyUIIterateStatus.setText(f"Job lost: {error_message}")
                self.ui.ComfyUIIterateStatus.setStyleSheet("color: #ef4444;")
                self.animator.update_status_animated(
                    "ComfyUI: Job disappeared from Deadline",
                    StatusColors.ERROR
                )
        else:
            eta_str = estimate_remaining_time(completed_tasks, display_total, elapsed)

            if status in ("Active", "Rendering"):
                if is_loading_model:
                    # Model is being loaded - show specific feedback
                    status_text = f"Rendering job {completed_tasks + 1}/{display_total} - Loading model..."
                    main_status = f"ComfyUI: Loading model... (job {completed_tasks + 1}/{display_total}) - {elapsed_str}"
                elif task_progress:
                    tp_pct = task_progress['progress_pct']
                    tp_cur = task_progress['current_node']
                    tp_tot = task_progress['total_nodes']
                    tp_name = task_progress.get('current_node_name')
                    # Show node name if available, otherwise just show node count
                    if tp_name:
                        status_text = f"Rendering job {completed_tasks + 1}/{display_total} - {tp_name} ({tp_pct}%)"
                    else:
                        status_text = f"Rendering job {completed_tasks + 1}/{display_total} - {tp_pct}% ({tp_cur}/{tp_tot} nodes)"
                    if completed_tasks > 0:
                        main_status = f"ComfyUI: Job {completed_tasks + 1}/{display_total} - {tp_pct}% of current job - {elapsed_str}"
                        if eta_str:
                            main_status += f" - ~{eta_str} remaining"
                    else:
                        main_status = f"ComfyUI: Job 1/{display_total} - {tp_pct}% - {elapsed_str}"
                else:
                    status_text = f"Rendering job {completed_tasks + 1}/{display_total} ({progress}%)"
                    if completed_tasks > 0:
                        main_status = f"ComfyUI: Job {completed_tasks}/{display_total} ({progress}%) - {elapsed_str} elapsed"
                        if eta_str:
                            main_status += f" - ~{eta_str} remaining"
                    else:
                        main_status = f"ComfyUI: Starting render - {display_total} job(s)"
            elif status in ("Pending", "Queued"):
                queue_position = result.get("queue_position", 0)
                total_queued = result.get("total_queued", 0)
                jobs_ahead = result.get("jobs_ahead", 0)
                own_jobs_ahead = result.get("own_jobs_ahead", 0)
                other_jobs_ahead = result.get("other_jobs_ahead", 0)

                if queue_position > 0 and total_queued > 0:
                    if jobs_ahead > 0:
                        # Build detailed queue message
                        queue_parts = []
                        if own_jobs_ahead > 0:
                            queue_parts.append(f"{own_jobs_ahead} own")
                        if other_jobs_ahead > 0:
                            queue_parts.append(f"{other_jobs_ahead} others")

                        queue_detail = " + ".join(queue_parts) if queue_parts else "0"
                        status_text = f"Queue position {queue_position}/{total_queued} ({queue_detail} ahead)"
                        main_status = f"ComfyUI: Queued #{queue_position} of {total_queued} - {queue_detail} ahead in queue"
                    else:
                        status_text = f"Queue position {queue_position}/{total_queued} (next up!)"
                        main_status = f"ComfyUI: Queued #{queue_position} of {total_queued} - Next in line!"
                else:
                    status_text = "Queued, waiting for worker..."
                    main_status = "ComfyUI: Queued - Waiting for available worker..."
            else:
                status_text = f"{status}: {progress}%"
                main_status = f"ComfyUI: {status} ({progress}%)"

            self.ui.ComfyUIIterateStatus.setText(status_text)
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #4a9eff;")
            self.animator.update_status_animated(main_status, StatusColors.INFO)

    def _stop_iterate_polling(self):
        """Stop the iterate poll timer."""
        if self._iterate_poll_timer:
            self._iterate_poll_timer.stop()
        self.main_window.stop_status_spinner()
        self._update_cancel_button_visibility()
        # Clear worker reference to allow garbage collection
        self._iterate_poll_worker = None
        # Clear persisted job state since polling stopped
        self._clear_running_job_state()

    def _on_iterate_job_completed(self):
        """Handle iterate job completion - show the generated image."""
        try:
            self._handle_iterate_job_completed()
        except Exception as e:
            logger.error(f"ERROR in _on_iterate_job_completed: {e}", exc_info=True)
            if hasattr(self.ui, 'ComfyUIIterateStatus') and self.ui.ComfyUIIterateStatus:
                self.ui.ComfyUIIterateStatus.setText(f"Error: {e}")
                self.ui.ComfyUIIterateStatus.setStyleSheet("color: #ef4444;")

    def _handle_iterate_job_completed(self):
        """Handle iterate job completion and record timing."""
        from ui_components import StatusColors
        from comfyui.metadata import get_job_output_files, cleanup_job_temp_files

        elapsed = time.time() - self._iterate_start_time if self._iterate_start_time else 0
        elapsed_str = format_elapsed_time(elapsed)
        frames = self._iterate_total_tasks

        # Record per-frame execution time for future estimates
        if frames > 0 and hasattr(self, '_current_preset_name') and self._current_preset_name:
            from core.user_preferences import record_workflow_execution_time
            per_frame_time = elapsed / frames
            record_workflow_execution_time(self._current_preset_name, per_frame_time)
            logger.info(f"[Iterate] Recorded {format_elapsed_time(per_frame_time)} per frame for '{self._current_preset_name}'")

        self.ui.ComfyUIIterateStatus.setText("Completed! Looking for output...")
        self.ui.ComfyUIIterateStatus.setStyleSheet("color: #10b981;")

        self.animator.update_status_animated(
            f"ComfyUI Complete: {frames} job(s) in {elapsed_str}",
            StatusColors.SUCCESS
        )

        # Show system tray notification (if enabled)
        from core.settings_manager import get_setting
        if get_setting("show_tray_notifications") and hasattr(self.main_window, 'show_system_notification'):
            output_type_str = pluralize_output_type(self._iterate_output_type, frames)
            self.main_window.show_system_notification(
                "ComfyUI Complete",
                f"{frames} {output_type_str} generated in {elapsed_str}",
                "success"
            )

        # Play completion sound (if enabled)
        play_completion_sound()

        output_files = []
        network_dir = self._iterate_network_output_dir
        job_start_time = self._iterate_start_time

        logger.debug("[Iterate] Looking for output files...")
        logger.debug(f"[Iterate] Network dir: {network_dir}")
        logger.debug(f"[Iterate] Job start time: {job_start_time}")

        if network_dir:
            deleted = cleanup_job_temp_files(network_dir)
            if deleted:
                logger.debug(f"[Iterate] Cleaned up {deleted} temp files from network dir")

        if network_dir:
            # Filter by modification time to only get files created AFTER this job started
            output_files = get_job_output_files(network_dir, min_mtime=job_start_time)
            if output_files:
                logger.info(f"[Iterate] Found {len(output_files)} files created after job started")

        if output_files:
            latest_image = output_files[0]
            self.app_state.comfyui_last_generated_image = latest_image
            logger.info(f"[Iterate] Latest output: {latest_image}")

            # Emit job completion event and update session stats
            if EVENT_BUS_AVAILABLE:
                job_id = self.app_state.comfyui_current_job_id
                # Record outputs in event bus
                for path in output_files:
                    pipeline_events.record_job_output(job_id, path)
                pipeline_events.complete_job(job_id, success=True)

                # Update app_state with recent outputs and session stats
                from core.state_manager import app_state
                for path in output_files[:10]:  # Keep last 10
                    app_state.add_recent_output(path)
                app_state.update_session_stats(
                    outputs_added=len(output_files),
                    time_seconds=elapsed,
                    job_completed=True
                )

            self.ui.ComfyUIIterateStatus.setText("Completed!")

            from PySide6.QtGui import QPixmap
            pixmap = QPixmap(latest_image)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.ui.ComfyUIIteratePreview.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.ui.ComfyUIIteratePreview.setPixmap(scaled)

            self.ui.ComfyUIUseAsInput.setEnabled(True)
            self.show_status("Image generated! Click 'Use as Input' to iterate.", "success")

            gallery_tab = self.main_window.get_tab("gallery")
            if gallery_tab:
                logger.debug("[Iterate] Triggering gallery refresh...")
                gallery_tab._on_refresh(show_status=False)

            # Update model thumbnail in background
            self._update_model_thumbnail_background()
        else:
            logger.warning("[Iterate] No output files found in either directory")
            self.ui.ComfyUIIterateStatus.setText("No output files found")
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #f59e0b;")
            self.animator.update_status_animated(
                "Deadline: Completed but no output files found",
                StatusColors.WARNING
            )

    def _on_use_as_input_clicked(self):
        """Copy the generated image path to the input image field."""
        last_image = self.app_state.comfyui_last_generated_image
        if not last_image or not os.path.exists(last_image):
            self.show_status("No generated image available", "error")
            return

        for node_id, container in self.widget_manager.dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget and hasattr(input_widget, 'add_images'):
                input_widget.clear_images()
                input_widget.add_images([last_image])
                self.show_status("Image set as input for next iteration", "success")
                return

        self.show_status("No image input field found in current workflow", "warning")

    def _update_model_thumbnail_background(self):
        """Update model thumbnail in background thread after job completion."""
        preset_name = getattr(self, '_current_preset_name', None)
        if not preset_name:
            return

        from ui_components import Worker
        from PySide6.QtCore import QThreadPool
        from comfyui.ratings import update_model_thumbnail

        def do_update():
            try:
                return update_model_thumbnail(preset_name)
            except Exception as e:
                logger.warning(f"[Polling] Background thumbnail update failed: {e}")
                return None

        def on_done(thumb_path):
            if thumb_path:
                logger.info(f"[Polling] Updated thumbnail for '{preset_name}'")

        self._thumbnail_worker = Worker(do_update)
        self._thumbnail_worker.signals.result.connect(on_done)
        QThreadPool.globalInstance().start(self._thumbnail_worker)

    # =========================================================================
    # BATCH MODE POLLING
    # =========================================================================

    def _start_batch_polling(self, job_ids, network_output_dir, output_type="image"):
        """Start polling for batch job completion.

        If a batch poll is already running, merges the new jobs into the
        existing batch instead of resetting all state.

        Args:
            job_ids: List of Deadline job IDs to poll
            network_output_dir: Path where outputs will be saved
            output_type: Type of output ("image", "video", "3d", "audio", "other")
        """
        from ui_components import StatusColors

        gen_count = self.ui.ComfyUIGenerationCount.value()

        # Check if batch polling is already active — merge instead of reset
        already_polling = (
            self._batch_poll_timer is not None
            and self._batch_poll_timer.isActive()
            and self._batch_pending_jobs
        )

        if already_polling:
            # Merge new jobs into existing batch
            self._batch_job_ids.extend(job_ids)
            self._batch_pending_jobs.update(job_ids)
            for job_id in job_ids:
                self._batch_completed_tasks[job_id] = 0
                self._batch_total_tasks[job_id] = gen_count
                self._batch_job_statuses[job_id] = "Pending"
            # Keep using existing network_output_dir, start_time, etc.

            total_jobs = len(self._batch_job_ids)
            total_frames = sum(self._batch_total_tasks.values())
            new_count = len(job_ids)

            logger.info(f"[Batch] Merged {new_count} new job(s) into existing batch, now tracking {total_jobs} job(s), {total_frames} total tasks")

            self.update_status_with_spinner(
                f"ComfyUI Batch: {total_jobs} job(s), {total_frames} tasks - Rendering...",
                StatusColors.INFO
            )
        else:
            # Fresh batch start
            self._batch_job_ids = list(job_ids)
            self._batch_pending_jobs = set(job_ids)
            self._batch_failed_jobs = set()
            self._batch_completed_tasks = {job_id: 0 for job_id in job_ids}
            self._batch_total_tasks = {job_id: gen_count for job_id in job_ids}
            self._batch_job_statuses = {job_id: "Pending" for job_id in job_ids}
            self._batch_network_output_dir = network_output_dir
            self._batch_output_type = output_type
            self._batch_poll_count = 0
            self._batch_start_time = time.time()
            self._batch_generation_count = gen_count
            self._batch_poll_pending_results = 0
            self._batch_poll_results = {}
            self._batch_recovery_mode = False  # New submission, not recovery
            self._batch_jobs_seen_active = set()

            total_jobs = len(job_ids)
            total_frames = total_jobs * gen_count

            logger.info(f"[Batch] Starting polling for {total_jobs} submission(s), {total_frames} total job(s)")

            self.update_status_with_spinner(
                f"ComfyUI Batch: {total_jobs} submission(s), {total_frames} job(s) - Waiting for workers...",
                StatusColors.INFO
            )

            if self._batch_poll_timer is None:
                self._batch_poll_timer = QTimer(self.main_window)
                self._batch_poll_timer.timeout.connect(self._poll_batch_jobs)

            self._batch_poll_timer.start(_get_poll_interval_ms())

        self._update_cancel_button_visibility()

        # Save job state for recovery on app restart (after timer is started)
        self._save_running_job_state()

        # Emit events for cross-tab awareness
        if EVENT_BUS_AVAILABLE:
            job_prefix = getattr(self, '_current_job_prefix', '')
            workflow_name = getattr(self, '_current_preset_name', '')
            for job_id in job_ids:
                pipeline_events.register_job(
                    job_id, self._batch_generation_count,
                    job_prefix=job_prefix, workflow_name=workflow_name
                )

        self._poll_batch_jobs()

    def _poll_batch_jobs(self):
        """Poll all pending batch jobs and collect results before updating status."""
        from ui_components import Worker
        from deadline.poller import poll_deadline_job_status

        if not self._batch_pending_jobs:
            self._stop_batch_polling()
            return

        # Guard: skip if previous poll cycle's workers haven't all reported back
        with self._batch_poll_lock:
            if self._batch_poll_pending_results > 0:
                logger.debug("[Batch] Skipping poll cycle — previous workers still pending")
                return
            self._batch_poll_pending_results = len(self._batch_pending_jobs)
            self._batch_poll_results = {}

        # Store workers and callbacks to prevent garbage collection
        self._batch_poll_workers = []

        output_dir = self._batch_network_output_dir
        for job_id in list(self._batch_pending_jobs):
            worker = Worker(poll_deadline_job_status, job_id, output_dir)
            # Capture job_id by value using default argument to avoid closure bug
            worker.signals.result.connect(
                lambda result, jid=job_id: self._on_batch_poll_result_collected(jid, result)
            )
            worker.signals.error.connect(
                lambda msg, tb, jid=job_id: self._on_batch_poll_error(jid, msg)
            )
            self._batch_poll_workers.append(worker)
            QThreadPool.globalInstance().start(worker)

    def _on_batch_poll_error(self, job_id, error_msg):
        """Handle poll error for a single job."""
        logger.warning(f"[Batch] Poll error for {job_id}: {error_msg}")
        with self._batch_poll_lock:
            self._batch_poll_results[job_id] = {"status": "PollError", "error_message": error_msg}
            self._batch_poll_pending_results -= 1
            should_process = self._batch_poll_pending_results <= 0
        if should_process:
            self._process_collected_poll_results()

    def _on_batch_poll_result_collected(self, job_id, result):
        """Collect a single job's poll result, then process all when complete."""
        try:
            status = result.get('status', 'Unknown') if isinstance(result, dict) else 'InvalidResult'
            with self._batch_poll_lock:
                self._batch_poll_results[job_id] = result
                self._batch_poll_pending_results -= 1
                pending = self._batch_poll_pending_results
                should_process = pending <= 0
                logger.debug(f"[Batch] Poll result collected for {job_id}: {status}, pending={pending}")
            if should_process:
                self._process_collected_poll_results()
        except Exception as e:
            logger.error(f"ERROR in _on_batch_poll_result_collected: {e}", exc_info=True)

    def _process_collected_poll_results(self):
        """Process all collected poll results and update status bar once."""
        import sys
        try:
            # Snapshot results under lock to prevent concurrent modification
            with self._batch_poll_lock:
                poll_results = dict(self._batch_poll_results)
            logger.debug(f"[Batch Poll] Processing {len(poll_results)} results...")

            from ui_components import StatusColors

            logger.debug(f"[Batch] Processing {len(poll_results)} poll results")
            had_new_frames = False
            total_new_frames = 0  # Track total new frames for gallery count
            total_jobs = len(self._batch_job_ids)
            active_job_task_progress = None

            active_job_loading_model = False

            for job_id, result in poll_results.items():
                status = result.get("status", "Unknown")
                completed_tasks = result.get("completed_tasks", 0)
                total_tasks = result.get("total_tasks", 1)
                task_progress = result.get("task_progress")
                is_loading_model = result.get("is_loading_model", False)

                self._batch_job_statuses[job_id] = status
                if total_tasks > 1:
                    self._batch_total_tasks[job_id] = total_tasks

                # Track per-job active state for Unknown handling
                if status in ("Active", "Rendering"):
                    self._batch_jobs_seen_active.add(job_id)

                # Capture task progress from any active job for status display
                if status in ("Active", "Rendering") and task_progress and not active_job_task_progress:
                    active_job_task_progress = task_progress

                # Track if any active job is loading a model
                if status in ("Active", "Rendering") and is_loading_model:
                    active_job_loading_model = True

                prev_completed = self._batch_completed_tasks.get(job_id, 0)
                if completed_tasks > prev_completed:
                    new_frames = completed_tasks - prev_completed
                    logger.info(f"[Batch] Job {job_id}: {new_frames} new job(s) rendered! ({completed_tasks}/{total_tasks})")
                    self._batch_completed_tasks[job_id] = completed_tasks
                    had_new_frames = True
                    total_new_frames += new_frames

                logger.debug(f"[Batch Poll] Job {job_id}: {status}, Tasks: {completed_tasks}/{total_tasks}")

                if status == "Completed":
                    self._batch_pending_jobs.discard(job_id)
                    self._batch_completed_tasks[job_id] = self._batch_total_tasks.get(job_id, 1)
                    logger.info(f"[Batch] Job {job_id} completed, {len(self._batch_pending_jobs)} remaining")

                elif status == "Failed":
                    self._batch_pending_jobs.discard(job_id)
                    self._batch_failed_jobs.add(job_id)
                    error_msg = result.get("error_message", "Unknown error")
                    logger.error(f"[Batch] Job {job_id} FAILED: {error_msg}")

                elif status == "Unknown":
                    # Job not found — could be transient error, not yet registered,
                    # or completed and auto-deleted.
                    was_active = job_id in self._batch_jobs_seen_active
                    job_total = self._batch_total_tasks.get(job_id, 1)
                    job_completed = self._batch_completed_tasks.get(job_id, 0)

                    if was_active and job_completed >= job_total:
                        # Job was running and all tasks completed → auto-deleted
                        logger.info(f"[Batch] Job {job_id} was active with {job_completed}/{job_total} tasks done, treating as completed")
                        self._batch_pending_jobs.discard(job_id)
                        self._batch_completed_tasks[job_id] = job_total
                    elif was_active:
                        # Job was running but disappeared — check for output files
                        from comfyui.metadata import get_job_output_files
                        output_dir = self._batch_network_output_dir
                        if output_dir:
                            output_files = get_job_output_files(output_dir, min_mtime=self._batch_start_time)
                            if output_files:
                                logger.info(f"[Batch] Job {job_id} disappeared but found output file(s), treating as completed")
                                self._batch_pending_jobs.discard(job_id)
                                self._batch_completed_tasks[job_id] = job_total
                            else:
                                logger.warning(f"[Batch] Job {job_id} was active but disappeared with no output, treating as lost")
                                self._batch_pending_jobs.discard(job_id)
                                self._batch_failed_jobs.add(job_id)
                        else:
                            logger.warning(f"[Batch] Job {job_id} was active but disappeared, no output dir to check")
                            self._batch_pending_jobs.discard(job_id)
                            self._batch_failed_jobs.add(job_id)
                    elif self._batch_poll_count <= 6:
                        logger.debug(f"[Batch] Job {job_id} not found on poll #{self._batch_poll_count}, likely still registering")
                    else:
                        logger.warning(f"[Batch] Job {job_id} not found after {self._batch_poll_count} polls, treating as lost")
                        self._batch_pending_jobs.discard(job_id)
                        self._batch_failed_jobs.add(job_id)

            if had_new_frames:
                self._refresh_gallery_for_new_frames("[Batch]")
                # Update app_state for cross-tab awareness
                if EVENT_BUS_AVAILABLE:
                    from core.state_manager import app_state
                    if total_new_frames > 0:
                        app_state.increment_gallery_new_count(total_new_frames)

            self._batch_poll_count += 1

            completed_jobs = total_jobs - len(self._batch_pending_jobs)
            total_frames_all = sum(self._batch_total_tasks.values())
            completed_frames_all = sum(self._batch_completed_tasks.values())
            elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
            elapsed_str = format_elapsed_time(elapsed)

            if not self._batch_pending_jobs:
                self._on_batch_jobs_completed(had_failures=len(self._batch_failed_jobs) > 0)
                return

            active_jobs = sum(1 for s in self._batch_job_statuses.values() if s in ("Active", "Rendering"))
            queued_jobs = len(self._batch_pending_jobs) - active_jobs
            failed_count = len(self._batch_failed_jobs)

            # Calculate TASK-level counts (more meaningful to user than job counts)
            # Each job has multiple tasks (generations), so sum across all jobs
            rendering_tasks_all = sum(
                result.get("rendering_tasks", 0) for result in poll_results.values()
            )
            queued_tasks_all = sum(
                result.get("queued_tasks", 0) for result in poll_results.values()
            )
            # Remaining tasks = total - completed - rendering
            remaining_tasks = total_frames_all - completed_frames_all

            # Get total farm queue info from poll results
            total_farm_queued = 0
            for result in poll_results.values():
                tq = result.get("total_queued", 0)
                if tq > 0:
                    total_farm_queued = tq
                    break

            # Calculate other people's jobs in queue
            others_queued = max(0, total_farm_queued - queued_jobs) if total_farm_queued > 0 else 0

            if failed_count > 0:
                main_status = f"ComfyUI: {completed_frames_all}/{total_frames_all} jobs - {failed_count} failed, {completed_jobs}/{total_jobs} done"
                status_color = StatusColors.WARNING
            elif active_jobs > 0:
                eta_str = estimate_remaining_time(completed_frames_all, total_frames_all, elapsed)
                batch_progress = int((completed_frames_all / max(total_frames_all, 1)) * 100)

                # Show model loading or task-level progress with step counts
                task_progress_str = ""
                if active_job_loading_model:
                    task_progress_str = " - Loading model..."
                elif active_job_task_progress:
                    tp_pct = active_job_task_progress.get('progress_pct', 0)
                    tp_cur = active_job_task_progress.get('current_node', 0)
                    tp_tot = active_job_task_progress.get('total_nodes', 0)
                    if tp_tot > 0:
                        task_progress_str = f" - Step {tp_cur}/{tp_tot} ({tp_pct}%)"
                    else:
                        task_progress_str = f" - {tp_pct}%"

                if completed_frames_all > 0:
                    main_status = f"ComfyUI: {completed_frames_all}/{total_frames_all} ({batch_progress}%){task_progress_str} - {rendering_tasks_all} rendering"
                    if remaining_tasks - rendering_tasks_all > 0:
                        queued_count = remaining_tasks - rendering_tasks_all
                        if others_queued > 0:
                            main_status += f", {queued_count} queued ({others_queued} others in queue)"
                        else:
                            main_status += f", {queued_count} queued"
                    main_status += f" - {elapsed_str}"
                    if eta_str:
                        main_status += f" (~{eta_str} left)"
                else:
                    # Show model loading or task progress when no frames completed yet
                    if active_job_loading_model:
                        main_status = f"ComfyUI: Loading model... - {rendering_tasks_all} rendering"
                    elif active_job_task_progress:
                        tp_cur = active_job_task_progress.get('current_node', 0)
                        tp_tot = active_job_task_progress.get('total_nodes', 0)
                        tp_pct = active_job_task_progress.get('progress_pct', 0)
                        if tp_tot > 0:
                            main_status = f"ComfyUI: Step {tp_cur}/{tp_tot} ({tp_pct}%) - {rendering_tasks_all} rendering"
                        else:
                            main_status = f"ComfyUI: {tp_pct}% - {rendering_tasks_all} rendering"
                    else:
                        main_status = f"ComfyUI: Starting {total_frames_all} tasks - {rendering_tasks_all} rendering"
                    queued_count = remaining_tasks - rendering_tasks_all
                    if queued_count > 0:
                        main_status += f", {queued_count} queued"
                status_color = StatusColors.INFO
            elif queued_jobs > 0:
                # All jobs queued, none rendering yet
                if others_queued > 0:
                    main_status = f"ComfyUI: {total_frames_all} task(s) queued - {others_queued} other job(s) ahead in farm queue"
                else:
                    main_status = f"ComfyUI: {total_frames_all} task(s) queued"
                status_color = StatusColors.INFO
            else:
                main_status = f"ComfyUI: {completed_jobs}/{total_jobs} jobs - {elapsed_str}"
                status_color = StatusColors.INFO

            logger.debug(f"[Batch Poll] Updating status bar...")
            self.animator.update_status_animated(main_status, status_color)
            logger.debug(f"[Batch Poll] Status update complete")
        except Exception as e:
            import traceback
            import sys
            logger.error(f"ERROR in _process_collected_poll_results: {e}", exc_info=True)
            logger.error(f"[Batch] ERROR in _process_collected_poll_results: {e}")
            logger.error(traceback.format_exc())

    def _stop_batch_polling(self):
        """Stop the batch poll timer."""
        if self._batch_poll_timer:
            self._batch_poll_timer.stop()
        self.main_window.stop_status_spinner()
        self._update_cancel_button_visibility()
        # Clear worker references to allow garbage collection
        self._batch_poll_workers.clear()
        # Clear persisted job state since polling stopped
        self._clear_running_job_state()

    def _on_batch_jobs_completed(self, had_failures=False):
        """Handle batch jobs completion - cleanup and refresh gallery."""
        try:
            self._handle_batch_jobs_completed(had_failures)
        except Exception as e:
            logger.error(f"ERROR in _on_batch_jobs_completed: {e}", exc_info=True)

    def _handle_batch_jobs_completed(self, had_failures=False):
        """Handle batch jobs completion and cleanup."""
        from ui_components import StatusColors
        from comfyui.metadata import cleanup_job_temp_files

        was_recovery = getattr(self, '_batch_recovery_mode', False)
        self._batch_recovery_mode = False  # Reset recovery flag

        self._stop_batch_polling()

        network_dir = self._batch_network_output_dir

        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        elapsed_str = format_elapsed_time(elapsed)
        total_frames = sum(self._batch_total_tasks.values())
        completed_frames = sum(self._batch_completed_tasks.values())

        # Record per-frame execution time for future estimates
        if completed_frames > 0 and getattr(self, '_current_preset_name', ''):
            from core.user_preferences import record_workflow_execution_time
            per_frame_time = elapsed / completed_frames
            record_workflow_execution_time(self._current_preset_name, per_frame_time)
            logger.info(f"[Batch] Recorded {format_elapsed_time(per_frame_time)} per frame for '{self._current_preset_name}'")

        if had_failures:
            logger.warning("[Batch] Jobs finished with failures!")
        else:
            logger.info("[Batch] All jobs completed successfully!")
        logger.debug(f"[Batch] Network dir: {network_dir}")

        if network_dir:
            deleted = cleanup_job_temp_files(network_dir)
            if deleted:
                logger.debug(f"[Batch] Cleaned up {deleted} temp files from network dir")

        failed_count = len(self._batch_failed_jobs)
        total_count = len(self._batch_job_ids)
        success_count = total_count - failed_count

        # Special handling for recovery mode - jobs completed while app was closed
        if was_recovery and self._batch_poll_count <= 1:
            logger.info("[Recovery] All batch jobs were already complete")
            self.show_status(f"{total_count} ComfyUI job(s) completed while app was closed", "success")
            self.animator.update_status_animated(
                f"Recovery: {total_count} job(s) already completed",
                StatusColors.SUCCESS
            )
            # Show system tray notification (if enabled)
            from core.settings_manager import get_setting
            if get_setting("show_tray_notifications") and hasattr(self.main_window, 'show_system_notification'):
                self.main_window.show_system_notification(
                    "ComfyUI Complete",
                    f"{total_count} job(s) completed while app was closed",
                    "success"
                )
        elif had_failures:
            self.show_status(f"ComfyUI: {failed_count}/{total_count} submission(s) failed!", "error")
            self.animator.update_status_animated(
                f"ComfyUI: {failed_count} failed, {success_count} succeeded - {completed_frames} jobs in {elapsed_str}",
                StatusColors.ERROR
            )
            # Show system tray notification for failures (if enabled)
            from core.settings_manager import get_setting
            if get_setting("show_tray_notifications") and hasattr(self.main_window, 'show_system_notification'):
                self.main_window.show_system_notification(
                    "ComfyUI Failed",
                    f"{failed_count}/{total_count} job(s) failed. {success_count} succeeded.",
                    "warning"
                )
        else:
            self.show_status(f"All {total_count} ComfyUI submissions completed!", "success")
            self.animator.update_status_animated(
                f"ComfyUI Complete: {total_frames} jobs in {elapsed_str}",
                StatusColors.SUCCESS
            )
            # Show system tray notification for success (if enabled)
            from core.settings_manager import get_setting
            if get_setting("show_tray_notifications") and hasattr(self.main_window, 'show_system_notification'):
                output_type_str = pluralize_output_type(self._batch_output_type, total_frames)
                self.main_window.show_system_notification(
                    "ComfyUI Complete",
                    f"All {total_count} job(s) completed! {total_frames} {output_type_str} generated in {elapsed_str}",
                    "success"
                )
            # Play completion sound (if enabled)
            play_completion_sound()

        # Emit completion events for cross-tab awareness
        if EVENT_BUS_AVAILABLE:
            for job_id in self._batch_job_ids:
                job_failed = job_id in self._batch_failed_jobs
                pipeline_events.complete_job(job_id, success=not job_failed)

            # Update session stats
            from core.state_manager import app_state
            app_state.update_session_stats(
                outputs_added=completed_frames,
                time_seconds=elapsed,
                job_completed=True
            )
            # Add recent outputs (we don't have individual paths, but we can mark completion)

        self._batch_failed_jobs.clear()

        gallery_tab = self.main_window.get_tab("gallery")
        if gallery_tab:
            logger.debug("[Batch] Triggering gallery refresh...")
            gallery_tab._on_refresh(show_status=False)

    # =========================================================================
    # CANCEL JOBS
    # =========================================================================

    def _on_cancel_jobs_clicked(self):
        """Handle cancel jobs button click."""
        from ui_components import Worker, StatusColors
        from deadline.poller import cancel_deadline_jobs

        job_ids = []

        iterate_job_id = self.app_state.comfyui_current_job_id
        if iterate_job_id and self._iterate_poll_timer and self._iterate_poll_timer.isActive():
            job_ids.append(iterate_job_id)

        if self._batch_pending_jobs:
            job_ids.extend(list(self._batch_pending_jobs))

        if not job_ids:
            logger.info("[Cancel] No running jobs to cancel")
            self.show_status("No running jobs to cancel", "warning")
            return

        if not confirm_action(
            "Cancel Jobs",
            f"Are you sure you want to cancel {len(job_ids)} running job(s)?\n\n"
            "This will complete all tasks immediately, triggering auto-deletion.",
            self.main_window
        ):
            return

        logger.info(f"[Cancel] Cancelling {len(job_ids)} jobs...")
        self.ui.ComfyUICancelJobs.setEnabled(False)
        self.ui.ComfyUICancelJobs.setText("Cancelling...")

        # Store as instance attribute to prevent garbage collection
        self._cancel_worker = Worker(cancel_deadline_jobs, job_ids)
        self._cancel_worker.signals.result.connect(self._on_cancel_complete)
        self._cancel_worker.signals.error.connect(self._on_cancel_error)
        QThreadPool.globalInstance().start(self._cancel_worker)

    def _on_cancel_complete(self, result):
        """Handle cancel jobs completion."""
        from ui_components import StatusColors

        succeeded, failed, errors = result

        self._stop_iterate_polling()
        self._stop_batch_polling()

        self.app_state.comfyui_current_job_id = ""
        self._batch_pending_jobs.clear()
        self._batch_job_ids.clear()

        self._update_cancel_button_visibility()
        self.ui.ComfyUICancelJobs.setText("Cancel Jobs")
        self.ui.ComfyUICancelJobs.setEnabled(True)

        self.ui.ComfyUIIterateStatus.setText("Cancelled")
        self.ui.ComfyUIIterateStatus.setStyleSheet("color: #f59e0b;")
        self.ui.ComfyUIIterateProgress.setValue(0)

        if failed > 0:
            logger.warning(f"[Cancel] Cancelled {succeeded} jobs, {failed} failed")
            for err in errors:
                logger.warning(f"[Cancel] Error: {err}")
            self.animator.update_status_animated(
                f"Cancelled {succeeded} jobs, {failed} failed",
                StatusColors.WARNING
            )
        else:
            logger.info(f"[Cancel] Successfully cancelled {succeeded} jobs")
            self.animator.update_status_animated(
                f"Cancelled {succeeded} job(s)",
                StatusColors.WARNING
            )

    def _on_cancel_error(self, msg, tb):
        """Handle cancel jobs error."""
        logger.error(f"[Cancel] Error: {msg}")
        self.ui.ComfyUICancelJobs.setText("Cancel Jobs")
        self.ui.ComfyUICancelJobs.setEnabled(True)
        self.show_status(f"Failed to cancel jobs: {msg}", "error")

    def _update_cancel_button_visibility(self):
        """Update the cancel button visibility based on running jobs."""
        has_iterate_job = (
            self.app_state.comfyui_current_job_id and
            self._iterate_poll_timer and
            self._iterate_poll_timer.isActive()
        )
        has_batch_jobs = bool(self._batch_pending_jobs)

        self.ui.ComfyUICancelJobs.setVisible(has_iterate_job or has_batch_jobs)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _refresh_gallery_for_new_frames(self, log_prefix):
        """Refresh gallery and request attention for new jobs."""
        gallery_tab = self.main_window.get_tab("gallery")
        if gallery_tab:
            logger.debug(f"{log_prefix} Triggering gallery refresh and attention for new jobs")
            # Invalidate cache for current user so new items are detected when switching back
            # This handles the case where user is viewing another user's gallery when renders complete
            current_user = getattr(self.app_state, 'user', None)
            if current_user and hasattr(gallery_tab, '_user_cache') and current_user in gallery_tab._user_cache:
                del gallery_tab._user_cache[current_user]
                logger.debug(f"{log_prefix} Invalidated gallery cache for user: {current_user}")
            gallery_tab._on_refresh(show_status=False)
            gallery_tab.signals.request_attention.emit()

    # =========================================================================
    # JOB STATE PERSISTENCE FOR APP RESTART RECOVERY
    # =========================================================================

    def _save_running_job_state(self):
        """Save current running job state for recovery on app restart."""
        from core.user_preferences import save_comfyui_running_jobs

        # Determine which mode is active
        if self._iterate_poll_timer and self._iterate_poll_timer.isActive():
            # Iterate mode
            job_state = {
                "mode": "iterate",
                "job_id": self.app_state.comfyui_current_job_id,
                "network_output_dir": self._iterate_network_output_dir,
                "total_tasks": self._iterate_total_tasks,
                "generation_count": self._iterate_total_tasks,
                "start_time": self._iterate_start_time,
                "output_type": self._iterate_output_type,
            }
            save_comfyui_running_jobs(job_state)
            logger.info("[Recovery] Saved iterate mode job state for recovery")

        elif self._batch_poll_timer and self._batch_poll_timer.isActive():
            # Batch mode
            job_state = {
                "mode": "batch",
                "job_ids": self._batch_job_ids,
                "network_output_dir": self._batch_network_output_dir,
                "total_tasks": self._batch_total_tasks,
                "generation_count": self._batch_generation_count,
                "start_time": self._batch_start_time,
                "output_type": self._batch_output_type,
            }
            save_comfyui_running_jobs(job_state)
            logger.info("[Recovery] Saved batch mode job state for recovery")

    def _clear_running_job_state(self):
        """Clear persisted running job state."""
        from core.user_preferences import save_comfyui_running_jobs

        save_comfyui_running_jobs(None)
        logger.debug("[Recovery] Cleared persisted job state")

    def _attempt_job_recovery(self):
        """Attempt to recover and resume polling for jobs that were running when app closed.

        This method performs two types of recovery:
        1. Persisted state recovery: Checks settings file for jobs that were running when app closed
        2. Deadline query recovery: Always checks Deadline for any running jobs from the current user

        The Deadline query ensures we catch jobs even if:
        - The settings file was corrupted or deleted
        - Jobs were submitted from another machine/session
        - The app crashed without saving state
        """
        from core.user_preferences import get_comfyui_running_jobs
        from deadline.poller import poll_deadline_job_status

        # First, try to recover from persisted state
        job_state = None
        mode = None
        try:
            job_state = get_comfyui_running_jobs()
            if job_state:
                mode = job_state.get("mode")
                logger.info(f"[Recovery] Found persisted {mode} mode job state from previous session")
        except Exception as e:
            logger.error(f"[Recovery] Error reading persisted job state: {e}")
            logger.error(f"[Recovery] Error reading persisted job state: {e}", exc_info=True)

        # Always check Deadline for running jobs from the current user
        # This catches jobs that may not be in persisted state
        # Use QTimer.singleShot to defer until after window is fully initialized
        # (animator and other components may not exist yet during tab init)
        QTimer.singleShot(100, lambda js=job_state: self._check_deadline_for_user_jobs(js))

    def _check_deadline_for_user_jobs(self, persisted_state):
        """Check Deadline directly for any running jobs from the current user.

        This provides robust recovery by querying Deadline for running jobs,
        regardless of whether we have persisted state.

        Args:
            persisted_state: The persisted job state from settings, or None
        """
        from ui_components import Worker
        from deadline.poller import find_user_running_jobs

        # Get current username
        current_user = getattr(self.app_state, 'user', None)
        if not current_user:
            import os
            current_user = os.environ.get("USERNAME", os.environ.get("USER", ""))

        if not current_user:
            logger.warning("[Recovery] Cannot determine current user, skipping Deadline check")
            # Fall back to persisted state recovery only
            if persisted_state:
                self._recover_from_persisted_state(persisted_state)
            return

        logger.info(f"[Recovery] Checking Deadline for running jobs from user: {current_user}")
        logger.debug("[Recovery] Starting async Deadline query (this runs in background)...")

        # Store persisted state on instance to avoid lambda capture issues
        self._recovery_persisted_state = persisted_state

        # Run the Deadline query in background to avoid blocking UI
        # Store worker to prevent garbage collection
        self._recovery_worker = Worker(find_user_running_jobs, current_user)
        self._recovery_worker.signals.result.connect(self._handle_recovery_result)
        self._recovery_worker.signals.error.connect(self._handle_recovery_error)
        QThreadPool.globalInstance().start(self._recovery_worker)

    def _handle_recovery_result(self, running_jobs):
        """Handle recovery worker result - wrapper that uses stored persisted state."""
        try:
            persisted_state = getattr(self, '_recovery_persisted_state', None)
            self._on_deadline_jobs_found(running_jobs, persisted_state)
        except Exception as e:
            logger.error(f"[Recovery] Error in recovery handler: {e}")
            logger.error(f"[Recovery] Error in recovery handler: {e}", exc_info=True)
        finally:
            # Clean up stored state
            self._recovery_persisted_state = None

    def _handle_recovery_error(self, error_msg, traceback_str):
        """Handle recovery worker error - wrapper that uses stored persisted state."""
        try:
            persisted_state = getattr(self, '_recovery_persisted_state', None)
            self._on_deadline_query_error(error_msg, traceback_str, persisted_state)
        except Exception as e:
            logger.error(f"[Recovery] Error in error handler: {e}")
            logger.error(f"[Recovery] Error in error handler: {e}", exc_info=True)
        finally:
            # Clean up stored state
            self._recovery_persisted_state = None

    def _on_deadline_query_error(self, error_msg, traceback_str, persisted_state):
        """Handle error from Deadline job query."""
        logger.error(f"[Recovery] Error checking Deadline for user jobs: {error_msg}")
        logger.error(traceback_str)

        # Update status
        try:
            if self.animator:
                self.animator.end_activity("job_recovery")
                self.animator.show_warning(f"Could not check Deadline: {error_msg}", show_in_status=True)
        except Exception as e:
            logger.debug(f"[Recovery] Warning: Could not update status: {e}")

        # Fall back to persisted state recovery
        if persisted_state:
            self._recover_from_persisted_state(persisted_state)

    def _on_deadline_jobs_found(self, running_jobs, persisted_state):
        """Handle results from async Deadline job query."""
        # End the recovery activity
        try:
            if self.animator:
                self.animator.end_activity("job_recovery")
        except Exception as e:
            logger.debug(f"[Recovery] Warning: Could not end activity: {e}")

        try:
            running_jobs = running_jobs or []

            # Check if polling is already active in this session — if so, don't
            # override status messages and skip jobs that are already tracked
            polling_active = (
                (self._iterate_poll_timer and self._iterate_poll_timer.isActive()) or
                (self._batch_poll_timer and self._batch_poll_timer.isActive())
            )

            if not running_jobs:
                logger.info("[Recovery] No running jobs found on Deadline for current user")
                # Only update status if no active polling (avoid overriding poll status)
                if not polling_active:
                    try:
                        if self.animator:
                            from ui_components import StatusColors
                            self.animator.update_status_animated(
                                "Ready", StatusColors.INFO
                            )
                    except Exception as e:
                        logger.debug(f"[Recovery] Warning: Could not update status: {e}")

                # If we have persisted state but no running jobs, the job must have completed
                if persisted_state:
                    logger.info("[Recovery] Persisted state exists but no running jobs - clearing state")
                    self._clear_running_job_state()
                    if not polling_active:
                        mode = persisted_state.get("mode") if persisted_state else None
                        if mode == "iterate":
                            self.show_status("Previous ComfyUI job completed while app was closed", "success")
                        elif mode == "batch":
                            self.show_status("Previous ComfyUI batch completed while app was closed", "success")
                        # Reset to "Ready" after showing the completion message briefly
                        from ui_components import StatusColors
                        from shiboken6 import isValid
                        QTimer.singleShot(4000, lambda: (
                            self.animator.update_status_animated("Ready", StatusColors.INFO)
                            if isValid(self) and self.animator else None
                        ))
                return

            logger.info(f"[Recovery] Found {len(running_jobs)} running job(s) on Deadline")
            for job in running_jobs:
                logger.info(f"[Recovery]   - {job['job_id']}: {job['name']} ({job['status']})")

            # Collect job IDs already being polled in this session (in-memory)
            already_polling = set()
            if self._iterate_poll_timer and self._iterate_poll_timer.isActive():
                current_iterate_id = self.app_state.comfyui_current_job_id
                if current_iterate_id:
                    already_polling.add(current_iterate_id)
            if self._batch_poll_timer and self._batch_poll_timer.isActive():
                already_polling.update(self._batch_job_ids)

            # Filter out jobs already being polled
            if already_polling:
                filtered_jobs = [j for j in running_jobs if j["job_id"] not in already_polling]
                if len(filtered_jobs) < len(running_jobs):
                    skipped = len(running_jobs) - len(filtered_jobs)
                    logger.info(f"[Recovery] Skipping {skipped} job(s) already being polled in this session")
                running_jobs = filtered_jobs

            if not running_jobs:
                logger.info("[Recovery] All running jobs are already being polled - no recovery needed")
                return

            # Get job IDs from persisted state for comparison
            persisted_job_ids = set()
            if persisted_state:
                mode = persisted_state.get("mode")
                if mode == "iterate":
                    job_id = persisted_state.get("job_id")
                    if job_id:
                        persisted_job_ids.add(job_id)
                elif mode == "batch":
                    persisted_job_ids.update(persisted_state.get("job_ids", []))

            # Get job IDs found on Deadline
            deadline_job_ids = {job["job_id"] for job in running_jobs}

            # Check if we found jobs that weren't in persisted state
            new_jobs = deadline_job_ids - persisted_job_ids
            if new_jobs:
                logger.info(f"[Recovery] Found {len(new_jobs)} job(s) not in persisted state - recovering from Deadline")

            # Recover using jobs found on Deadline
            self._recover_from_deadline_jobs(running_jobs, persisted_state)

        except Exception as e:
            logger.error(f"[Recovery] Error checking Deadline for user jobs: {e}")
            logger.error(f"[Recovery] Error checking Deadline for user jobs: {e}", exc_info=True)
            # Fall back to persisted state recovery
            if persisted_state:
                self._recover_from_persisted_state(persisted_state)

    def _recover_from_deadline_jobs(self, running_jobs, persisted_state):
        """Recover polling using jobs found on Deadline.

        Args:
            running_jobs: List of job dicts from find_user_running_jobs
            persisted_state: Persisted job state for additional metadata, or None
        """
        from ui_components import StatusColors

        if not running_jobs:
            return

        job_ids = [job["job_id"] for job in running_jobs]

        # Try to get network_output_dir from persisted state or job output_dir
        network_output_dir = ""
        if persisted_state:
            network_output_dir = persisted_state.get("network_output_dir", "")

        # If no persisted output dir, try to get from job properties
        if not network_output_dir:
            for job in running_jobs:
                if job.get("output_dir"):
                    network_output_dir = job["output_dir"]
                    break

        # Get generation count from persisted state or default to 1
        generation_count = 1
        if persisted_state:
            generation_count = persisted_state.get("generation_count", 1)

        if len(job_ids) == 1:
            # Single job - use iterate mode recovery
            job_id = job_ids[0]
            job = running_jobs[0]

            logger.info(f"[Recovery] Recovering single job {job_id} in iterate mode")

            self._iterate_network_output_dir = network_output_dir
            self._iterate_total_tasks = generation_count
            self._iterate_start_time = time.time()
            self._iterate_completed_tasks = 0
            self._iterate_poll_count = 0
            self._iterate_output_type = persisted_state.get("output_type", "image") if persisted_state else "image"
            self._iterate_saw_active = job["status"] in ("Active", "Rendering")
            self.app_state.comfyui_current_job_id = job_id

            if self._iterate_poll_timer is None:
                self._iterate_poll_timer = QTimer(self.main_window)
                self._iterate_poll_timer.timeout.connect(self._poll_iterate_job)

            self._iterate_poll_timer.start(_get_poll_interval_ms())
            self._update_cancel_button_visibility()
            self.main_window.start_status_spinner()

            self.ui.ComfyUIIterateStatus.setText(f"Recovered: {job['status']}")
            self.ui.ComfyUIIterateProgress.setValue(0)
            self.animator.update_status_animated(
                f"ComfyUI: Recovered job ({job['status']})",
                StatusColors.INFO
            )

            # Save state for future recovery
            self._save_running_job_state()

            # Start immediate poll
            self._poll_iterate_job()

            self.show_status("Recovered running ComfyUI job from Deadline", "success")
        else:
            # Multiple jobs - use batch mode recovery
            logger.info(f"[Recovery] Recovering {len(job_ids)} jobs in batch mode")

            # Build total_tasks dict
            total_tasks = {}
            if persisted_state and persisted_state.get("total_tasks"):
                total_tasks = persisted_state.get("total_tasks", {})
            for job_id in job_ids:
                if job_id not in total_tasks:
                    total_tasks[job_id] = generation_count

            self._batch_job_ids = list(job_ids)
            self._batch_pending_jobs = set(job_ids)
            self._batch_failed_jobs = set()
            self._batch_completed_tasks = {job_id: 0 for job_id in job_ids}
            self._batch_total_tasks = total_tasks
            self._batch_job_statuses = {job["job_id"]: job["status"] for job in running_jobs}
            self._batch_network_output_dir = network_output_dir
            self._batch_output_type = persisted_state.get("output_type", "image") if persisted_state else "image"
            self._batch_poll_count = 0
            self._batch_start_time = time.time()
            self._batch_generation_count = generation_count
            self._batch_poll_pending_results = 0
            self._batch_poll_results = {}
            self._batch_recovery_mode = True
            # Pre-populate seen-active from Deadline query results
            self._batch_jobs_seen_active = {
                job["job_id"] for job in running_jobs
                if job["status"] in ("Active", "Rendering")
            }

            if self._batch_poll_timer is None:
                self._batch_poll_timer = QTimer(self.main_window)
                self._batch_poll_timer.timeout.connect(self._poll_batch_jobs)

            self._batch_poll_timer.start(_get_poll_interval_ms())
            self._update_cancel_button_visibility()
            self.main_window.start_status_spinner()

            self.animator.update_status_animated(
                f"ComfyUI: Recovered {len(job_ids)} job(s) from Deadline",
                StatusColors.INFO
            )

            # Save state for future recovery
            self._save_running_job_state()

            # Start immediate poll
            self._poll_batch_jobs()

            self.show_status(f"Recovered {len(job_ids)} running ComfyUI job(s) from Deadline", "success")

    def _recover_from_persisted_state(self, job_state):
        """Recover using persisted state only (fallback when Deadline check fails).

        Uses async worker to check job status without blocking UI.

        Args:
            job_state: The persisted job state dictionary
        """
        from ui_components import Worker
        from deadline.poller import poll_deadline_job_status

        mode = job_state.get("mode")
        if not mode:
            return

        if mode == "iterate":
            job_id = job_state.get("job_id")
            network_output_dir = job_state.get("network_output_dir")

            if not job_id:
                logger.warning("[Recovery] No job ID found, clearing state")
                self._clear_running_job_state()
                return

            # Check job status asynchronously
            logger.info(f"[Recovery] Checking status of iterate job {job_id} (async)")

            def on_status_result(status_result):
                try:
                    self._handle_iterate_recovery_status(job_state, status_result)
                except Exception as e:
                    logger.error(f"[Recovery] Error handling iterate recovery: {e}")
                    logger.error(f"[Recovery] Error handling iterate recovery: {e}", exc_info=True)
                    self._clear_running_job_state()

            def on_status_error(msg, tb):
                logger.error(f"[Recovery] Error checking iterate job status: {msg}")
                self._clear_running_job_state()

            # Store worker to prevent garbage collection
            self._recovery_status_worker = Worker(poll_deadline_job_status, job_id, network_output_dir)
            self._recovery_status_worker.signals.result.connect(on_status_result)
            self._recovery_status_worker.signals.error.connect(on_status_error)
            QThreadPool.globalInstance().start(self._recovery_status_worker)

        elif mode == "batch":
            try:
                job_ids = job_state.get("job_ids", [])
                network_output_dir = job_state.get("network_output_dir")
                total_tasks = job_state.get("total_tasks", {})
                generation_count = job_state.get("generation_count", 1)

                if not job_ids:
                    logger.warning("[Recovery] No job IDs found, clearing state")
                    self._clear_running_job_state()
                    return

                # Fast recovery: Start polling immediately with all job IDs
                # The polling mechanism will discover which jobs are still active/completed
                # This avoids blocking the UI with synchronous status checks for each job
                logger.info(f"[Recovery] Fast-recovering {len(job_ids)} batch job(s), starting async polling...")

                # Show immediate feedback
                from ui_components import StatusColors
                self.animator.update_status_animated(
                    f"Recovering {len(job_ids)} ComfyUI job(s)...",
                    StatusColors.INFO
                )

                # Restore batch mode state with all persisted job IDs
                self._batch_job_ids = list(job_ids)
                self._batch_pending_jobs = set(job_ids)
                self._batch_failed_jobs = set()
                self._batch_completed_tasks = {job_id: 0 for job_id in job_ids}
                self._batch_total_tasks = {job_id: total_tasks.get(job_id, generation_count) for job_id in job_ids}
                self._batch_job_statuses = {job_id: "Recovering" for job_id in job_ids}
                self._batch_network_output_dir = network_output_dir
                self._batch_output_type = job_state.get("output_type", "image")
                self._batch_poll_count = 0
                self._batch_start_time = job_state.get("start_time", time.time())
                self._batch_generation_count = generation_count
                self._batch_poll_pending_results = 0
                self._batch_poll_results = {}
                self._batch_recovery_mode = True  # Flag to track we're in recovery
                self._batch_jobs_seen_active = set()  # Will be populated on first poll

                # Start polling without re-submitting
                if self._batch_poll_timer is None:
                    self._batch_poll_timer = QTimer(self.main_window)
                    self._batch_poll_timer.timeout.connect(self._poll_batch_jobs)

                self._batch_poll_timer.start(_get_poll_interval_ms())
                self._update_cancel_button_visibility()
                self.main_window.start_status_spinner()

                # Start immediate async poll to discover job states
                self._poll_batch_jobs()

                logger.info("[Recovery] Batch mode polling started - job states will be discovered async")
                self.show_status(f"Recovering {len(job_ids)} ComfyUI job(s)...", "success")
            except Exception as e:
                logger.error(f"[Recovery] Error recovering batch jobs: {e}")
                logger.error(f"[Recovery] Error recovering batch jobs: {e}", exc_info=True)
                self._clear_running_job_state()

    def _handle_iterate_recovery_status(self, job_state, status_result):
        """Handle async status result for iterate mode recovery.

        Args:
            job_state: The persisted job state dictionary
            status_result: Result from poll_deadline_job_status
        """
        from ui_components import StatusColors

        job_id = job_state.get("job_id")
        network_output_dir = job_state.get("network_output_dir")
        total_tasks = job_state.get("total_tasks", 1)
        status = status_result.get("status", "Unknown")

        if status in ("Active", "Rendering", "Queued", "Pending"):
            logger.info(f"[Recovery] Job {job_id} is still {status}, resuming polling")

            # Restore iterate mode state and resume polling
            self._iterate_network_output_dir = network_output_dir
            self._iterate_total_tasks = total_tasks
            self._iterate_start_time = job_state.get("start_time", time.time())
            self._iterate_output_type = job_state.get("output_type", "image")
            self._iterate_completed_tasks = 0
            self._iterate_poll_count = 0
            self._iterate_saw_active = status in ("Active", "Rendering")
            self.app_state.comfyui_current_job_id = job_id

            # Start polling without re-submitting
            if self._iterate_poll_timer is None:
                self._iterate_poll_timer = QTimer(self.main_window)
                self._iterate_poll_timer.timeout.connect(self._poll_iterate_job)

            self._iterate_poll_timer.start(_get_poll_interval_ms())
            self._update_cancel_button_visibility()
            self.main_window.start_status_spinner()

            # Update both tab status and main status bar immediately
            self.ui.ComfyUIIterateStatus.setText(f"Recovered: {status}")
            self.ui.ComfyUIIterateProgress.setValue(0)
            self.animator.update_status_animated(
                f"ComfyUI: Recovering job ({status}) - {total_tasks} task(s)",
                StatusColors.INFO
            )

            # Start immediate poll to get current status
            self._poll_iterate_job()

            logger.info("[Recovery] Iterate mode polling resumed successfully")
            self.show_status(f"Recovered running ComfyUI job (status: {status})", "success")
        else:
            logger.info(f"[Recovery] Job {job_id} is {status}, clearing state")
            self._clear_running_job_state()
            if status == "Completed":
                self.show_status("Previous ComfyUI job completed while app was closed", "success")
                # Show system tray notification (if enabled)
                from core.settings_manager import get_setting
                if get_setting("show_tray_notifications") and hasattr(self.main_window, 'show_system_notification'):
                    self.main_window.show_system_notification(
                        "ComfyUI Complete",
                        "Previous job completed while app was closed",
                        "success"
                    )
