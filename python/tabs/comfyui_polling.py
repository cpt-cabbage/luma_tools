"""
ComfyUI polling logic for job status monitoring.

Provides mixin classes for iterate and batch mode polling.
"""
import os
import time
from PySide6.QtCore import QTimer, QThreadPool
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt


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


class PollingMixin:
    """
    Mixin providing job polling functionality for ComfyUI tab.

    Requires the following attributes on the class using this mixin:
    - self.ui: The UI object with ComfyUI widgets
    - self.main_window: Main window reference
    - self.app_state: Application state
    - self.log(): Logging method
    - self._comfyui_dynamic_widgets: Widget dict for editable nodes
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

        # Batch mode state
        self._batch_poll_timer = None
        self._batch_job_ids = []
        self._batch_pending_jobs = set()
        self._batch_failed_jobs = set()
        self._batch_completed_tasks = {}
        self._batch_total_tasks = {}
        self._batch_job_statuses = {}
        self._batch_network_output_dir = ""
        self._batch_poll_count = 0
        self._batch_start_time = None
        self._batch_generation_count = 1
        self._batch_poll_pending_results = 0
        self._batch_poll_results = {}
        self._batch_poll_workers = []

    # =========================================================================
    # ITERATE MODE POLLING
    # =========================================================================

    def _start_iterate_polling(self, job_id, network_output_dir):
        """Start polling for iterate mode job completion."""
        from ui_components import StatusColors

        self.app_state.comfyui_current_job_id = job_id
        self._iterate_network_output_dir = network_output_dir
        self._iterate_poll_count = 0
        self._iterate_completed_tasks = 0
        self._iterate_total_tasks = self.ui.ComfyUIGenerationCount.value()
        self._iterate_start_time = time.time()

        self.log(f"[Iterate] Starting polling for job {job_id}")
        self.log(f"[Iterate] Network output dir: {network_output_dir}")
        self.log(f"[Iterate] Expected frames: {self._iterate_total_tasks}")

        self.main_window.start_status_spinner()

        self.ui.ComfyUIIterateStatus.setText("Job submitted, waiting for Deadline...")
        self.ui.ComfyUIIterateProgress.setValue(0)
        self.ui.ComfyUIUseAsInput.setEnabled(False)

        gen_count = self._iterate_total_tasks
        self.main_window.animator.update_status_animated(
            f"ComfyUI: Submitted {gen_count} frame(s) - Waiting for worker...",
            StatusColors.INFO
        )

        if self._iterate_poll_timer is None:
            self._iterate_poll_timer = QTimer(self.main_window)
            self._iterate_poll_timer.timeout.connect(self._poll_iterate_job)

        self._iterate_poll_timer.start(5000)
        self._update_cancel_button_visibility()
        self._poll_iterate_job()

    def _poll_iterate_job(self):
        """Poll the iterate job status."""
        from ui_components import Worker
        from comfyui.service import poll_deadline_job_status

        job_id = self.app_state.comfyui_current_job_id
        if not job_id:
            self._stop_iterate_polling()
            return

        output_dir = self._iterate_network_output_dir
        # Store worker to prevent garbage collection
        self._iterate_poll_worker = Worker(poll_deadline_job_status, job_id, output_dir)
        self._iterate_poll_worker.signals.result.connect(self._on_iterate_poll_result)
        self._iterate_poll_worker.signals.error.connect(lambda msg, tb: self.log(f"Poll error: {msg}"))
        QThreadPool.globalInstance().start(self._iterate_poll_worker)

    def _on_iterate_poll_result(self, result):
        """Handle iterate poll result."""
        from ui_components import StatusColors

        status = result.get("status", "Unknown")
        progress = result.get("progress", 0)
        completed_tasks = result.get("completed_tasks", 0)
        total_tasks = result.get("total_tasks", 1)
        error_message = result.get("error_message", "")

        display_total = max(total_tasks, self._iterate_total_tasks)

        self.log(f"[Iterate Poll] Status: {status}, Progress: {progress}%, Tasks: {completed_tasks}/{display_total}")

        elapsed = time.time() - self._iterate_start_time if self._iterate_start_time else 0
        elapsed_str = format_elapsed_time(elapsed)

        if completed_tasks > self._iterate_completed_tasks:
            new_frames = completed_tasks - self._iterate_completed_tasks
            self.log(f"[Iterate] {new_frames} new frame(s) rendered! ({completed_tasks}/{display_total})")
            self._iterate_completed_tasks = completed_tasks
            self._refresh_gallery_for_new_frames("[Iterate]")

        self.ui.ComfyUIIterateProgress.setValue(progress)
        self._iterate_poll_count += 1

        if status == "Completed":
            self._stop_iterate_polling()
            self._on_iterate_job_completed()
        elif status == "Failed":
            self._stop_iterate_polling()
            self.ui.ComfyUIIterateStatus.setText(f"Job failed: {error_message}")
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #ef4444;")
            self.main_window.animator.update_status_animated(
                f"ComfyUI Failed: {error_message}",
                StatusColors.ERROR
            )
        else:
            eta_str = estimate_remaining_time(completed_tasks, display_total, elapsed)

            if status in ("Active", "Rendering"):
                status_text = f"Rendering frame {completed_tasks + 1}/{display_total}"
                if completed_tasks > 0:
                    main_status = f"ComfyUI: Frame {completed_tasks}/{display_total} - {elapsed_str} elapsed"
                    if eta_str:
                        main_status += f" - ~{eta_str} remaining"
                else:
                    main_status = f"ComfyUI: Starting render - {display_total} frame(s)"
            elif status in ("Pending", "Queued"):
                status_text = "Queued, waiting for worker..."
                main_status = "ComfyUI: Queued - Waiting for available worker..."
            else:
                status_text = f"{status}: {progress}%"
                main_status = f"ComfyUI: {status} ({progress}%)"

            self.ui.ComfyUIIterateStatus.setText(status_text)
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #4a9eff;")
            self.main_window.animator.update_status_animated(main_status, StatusColors.INFO)

    def _stop_iterate_polling(self):
        """Stop the iterate poll timer."""
        if self._iterate_poll_timer:
            self._iterate_poll_timer.stop()
        self.main_window.stop_status_spinner()
        self._update_cancel_button_visibility()

    def _on_iterate_job_completed(self):
        """Handle iterate job completion - show the generated image."""
        from ui_components import StatusColors
        from comfyui.service import get_job_output_files, cleanup_job_temp_files

        elapsed = time.time() - self._iterate_start_time if self._iterate_start_time else 0
        elapsed_str = format_elapsed_time(elapsed)
        frames = self._iterate_total_tasks

        self.ui.ComfyUIIterateStatus.setText("Completed! Looking for output...")
        self.ui.ComfyUIIterateStatus.setStyleSheet("color: #10b981;")

        self.main_window.animator.update_status_animated(
            f"ComfyUI Complete: {frames} frame(s) in {elapsed_str}",
            StatusColors.SUCCESS
        )

        output_files = []
        network_dir = self._iterate_network_output_dir

        self.log("[Iterate] Looking for output files...")
        self.log(f"[Iterate] Network dir: {network_dir}")

        if network_dir:
            deleted = cleanup_job_temp_files(network_dir)
            if deleted:
                self.log(f"[Iterate] Cleaned up {deleted} temp files from network dir")

        if network_dir:
            output_files = get_job_output_files(network_dir)
            if output_files:
                self.log(f"[Iterate] Found {len(output_files)} files in network dir")

        if output_files:
            latest_image = output_files[0]
            self.app_state.comfyui_last_generated_image = latest_image
            self.log(f"[Iterate] Latest output: {latest_image}")

            self.ui.ComfyUIIterateStatus.setText("Completed!")

            pixmap = QPixmap(latest_image)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.ui.ComfyUIIteratePreview.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.ui.ComfyUIIteratePreview.setPixmap(scaled)

            self.ui.ComfyUIUseAsInput.setEnabled(True)
            self.main_window.animator.show_success("Image generated! Click 'Use as Input' to iterate.")

            gallery_tab = self.main_window.get_tab("comfyui_gallery")
            if gallery_tab:
                self.log("[Iterate] Triggering gallery refresh...")
                gallery_tab._on_refresh()
        else:
            self.log("[Iterate] No output files found in either directory")
            self.ui.ComfyUIIterateStatus.setText("No output files found")
            self.ui.ComfyUIIterateStatus.setStyleSheet("color: #f59e0b;")
            self.main_window.animator.update_status_animated(
                "Deadline: Completed but no output files found",
                StatusColors.WARNING
            )

    def _on_use_as_input_clicked(self):
        """Copy the generated image path to the input image field."""
        last_image = self.app_state.comfyui_last_generated_image
        if not last_image or not os.path.exists(last_image):
            self.main_window.animator.show_error("No generated image available")
            return

        for node_id, container in self._comfyui_dynamic_widgets.items():
            input_widget = getattr(container, 'input_widget', None)
            if input_widget and hasattr(input_widget, 'add_images'):
                input_widget.clear_images()
                input_widget.add_images([last_image])
                self.main_window.animator.show_success("Image set as input for next iteration")
                return

        self.main_window.animator.show_warning("No image input field found in current workflow")

    # =========================================================================
    # BATCH MODE POLLING
    # =========================================================================

    def _start_batch_polling(self, job_ids, network_output_dir):
        """Start polling for batch job completion."""
        from ui_components import StatusColors

        self._batch_job_ids = list(job_ids)
        self._batch_pending_jobs = set(job_ids)
        self._batch_failed_jobs = set()
        self._batch_completed_tasks = {job_id: 0 for job_id in job_ids}
        self._batch_total_tasks = {job_id: self.ui.ComfyUIGenerationCount.value() for job_id in job_ids}
        self._batch_job_statuses = {job_id: "Pending" for job_id in job_ids}
        self._batch_network_output_dir = network_output_dir
        self._batch_poll_count = 0
        self._batch_start_time = time.time()
        self._batch_generation_count = self.ui.ComfyUIGenerationCount.value()
        self._batch_poll_pending_results = 0
        self._batch_poll_results = {}

        total_jobs = len(job_ids)
        total_frames = total_jobs * self._batch_generation_count

        self.log(f"[Batch] Starting polling for {total_jobs} job(s), {total_frames} total frame(s)")

        self.main_window.start_status_spinner()

        self.main_window.animator.update_status_animated(
            f"ComfyUI Batch: {total_jobs} job(s), {total_frames} frame(s) - Waiting for workers...",
            StatusColors.INFO
        )

        if self._batch_poll_timer is None:
            self._batch_poll_timer = QTimer(self.main_window)
            self._batch_poll_timer.timeout.connect(self._poll_batch_jobs)

        self._batch_poll_timer.start(10000)
        self._update_cancel_button_visibility()
        self._poll_batch_jobs()

    def _poll_batch_jobs(self):
        """Poll all pending batch jobs and collect results before updating status."""
        from ui_components import Worker
        from comfyui.service import poll_deadline_job_status

        if not self._batch_pending_jobs:
            self._stop_batch_polling()
            return

        self._batch_poll_pending_results = len(self._batch_pending_jobs)
        self._batch_poll_results = {}

        # Store workers and callbacks to prevent garbage collection
        self._batch_poll_workers = []

        output_dir = self._batch_network_output_dir
        for job_id in list(self._batch_pending_jobs):
            worker = Worker(poll_deadline_job_status, job_id, output_dir)
            # Use bound methods instead of lambdas to avoid GC issues
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
        self.log(f"[Batch] Poll error for {job_id}: {error_msg}")
        self._batch_poll_results[job_id] = {"status": "PollError", "error_message": error_msg}
        self._batch_poll_pending_results -= 1
        if self._batch_poll_pending_results <= 0:
            self._process_collected_poll_results()

    def _on_batch_poll_result_collected(self, job_id, result):
        """Collect a single job's poll result, then process all when complete."""
        self.log(f"[Batch] Poll result collected for {job_id}: {result.get('status', 'Unknown')}, pending={self._batch_poll_pending_results - 1}")
        self._batch_poll_results[job_id] = result
        self._batch_poll_pending_results -= 1

        if self._batch_poll_pending_results <= 0:
            self._process_collected_poll_results()

    def _process_collected_poll_results(self):
        """Process all collected poll results and update status bar once."""
        try:
            from ui_components import StatusColors

            self.log(f"[Batch] Processing {len(self._batch_poll_results)} poll results")
            had_new_frames = False
            total_jobs = len(self._batch_job_ids)

            for job_id, result in self._batch_poll_results.items():
                status = result.get("status", "Unknown")
                completed_tasks = result.get("completed_tasks", 0)
                total_tasks = result.get("total_tasks", 1)

                self._batch_job_statuses[job_id] = status
                if total_tasks > 1:
                    self._batch_total_tasks[job_id] = total_tasks

                prev_completed = self._batch_completed_tasks.get(job_id, 0)
                if completed_tasks > prev_completed:
                    new_frames = completed_tasks - prev_completed
                    self.log(f"[Batch] Job {job_id}: {new_frames} new frame(s) rendered! ({completed_tasks}/{total_tasks})")
                    self._batch_completed_tasks[job_id] = completed_tasks
                    had_new_frames = True

                self.log(f"[Batch Poll] Job {job_id}: {status}, Tasks: {completed_tasks}/{total_tasks}")

                if status == "Completed":
                    self._batch_pending_jobs.discard(job_id)
                    self._batch_completed_tasks[job_id] = self._batch_total_tasks.get(job_id, 1)
                    self.log(f"[Batch] Job {job_id} completed, {len(self._batch_pending_jobs)} remaining")

                elif status == "Failed":
                    self._batch_pending_jobs.discard(job_id)
                    self._batch_failed_jobs.add(job_id)
                    error_msg = result.get("error_message", "Unknown error")
                    self.log(f"[Batch] Job {job_id} FAILED: {error_msg}")

            if had_new_frames:
                self._refresh_gallery_for_new_frames("[Batch]")

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

            if failed_count > 0:
                main_status = f"ComfyUI: {completed_frames_all}/{total_frames_all} frames - {failed_count} failed, {completed_jobs}/{total_jobs} done"
                status_color = StatusColors.WARNING
            elif active_jobs > 0:
                eta_str = estimate_remaining_time(completed_frames_all, total_frames_all, elapsed)
                if completed_frames_all > 0:
                    main_status = f"ComfyUI: {completed_frames_all}/{total_frames_all} frames - {active_jobs} rendering"
                    if queued_jobs > 0:
                        main_status += f", {queued_jobs} queued"
                    main_status += f" - {elapsed_str}"
                    if eta_str:
                        main_status += f" (~{eta_str} left)"
                else:
                    main_status = f"ComfyUI: Starting {total_frames_all} frames - {active_jobs} active, {queued_jobs} queued"
                status_color = StatusColors.INFO
            elif queued_jobs > 0:
                main_status = f"ComfyUI: {queued_jobs} job(s) queued - Waiting for workers..."
                status_color = StatusColors.INFO
            else:
                main_status = f"ComfyUI: {completed_jobs}/{total_jobs} jobs - {elapsed_str}"
                status_color = StatusColors.INFO

            self.main_window.animator.update_status_animated(main_status, status_color)
        except Exception as e:
            import traceback
            self.log(f"[Batch] ERROR in _process_collected_poll_results: {e}")
            self.log(traceback.format_exc())

    def _stop_batch_polling(self):
        """Stop the batch poll timer."""
        if self._batch_poll_timer:
            self._batch_poll_timer.stop()
        self.main_window.stop_status_spinner()
        self._update_cancel_button_visibility()

    def _on_batch_jobs_completed(self, had_failures=False):
        """Handle batch jobs completion - cleanup and refresh gallery."""
        from ui_components import StatusColors
        from comfyui.service import cleanup_job_temp_files

        self._stop_batch_polling()

        network_dir = self._batch_network_output_dir

        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        elapsed_str = format_elapsed_time(elapsed)
        total_frames = sum(self._batch_total_tasks.values())
        completed_frames = sum(self._batch_completed_tasks.values())

        if had_failures:
            self.log("[Batch] Jobs finished with failures!")
        else:
            self.log("[Batch] All jobs completed successfully!")
        self.log(f"[Batch] Network dir: {network_dir}")

        if network_dir:
            deleted = cleanup_job_temp_files(network_dir)
            if deleted:
                self.log(f"[Batch] Cleaned up {deleted} temp files from network dir")

        failed_count = len(self._batch_failed_jobs)
        total_count = len(self._batch_job_ids)
        success_count = total_count - failed_count

        if had_failures:
            self.main_window.animator.show_error(f"ComfyUI: {failed_count}/{total_count} job(s) failed!")
            self.main_window.animator.update_status_animated(
                f"ComfyUI: {failed_count} failed, {success_count} succeeded - {completed_frames} frames in {elapsed_str}",
                StatusColors.ERROR
            )
        else:
            self.main_window.animator.show_success(f"All {total_count} ComfyUI jobs completed!")
            self.main_window.animator.update_status_animated(
                f"ComfyUI Complete: {total_frames} frames in {elapsed_str}",
                StatusColors.SUCCESS
            )

        self._batch_failed_jobs.clear()

        gallery_tab = self.main_window.get_tab("comfyui_gallery")
        if gallery_tab:
            self.log("[Batch] Triggering gallery refresh...")
            gallery_tab._on_refresh()

    # =========================================================================
    # CANCEL JOBS
    # =========================================================================

    def _on_cancel_jobs_clicked(self):
        """Handle cancel jobs button click."""
        from ui_components import Worker, StatusColors
        from comfyui.service import cancel_deadline_jobs

        job_ids = []

        iterate_job_id = self.app_state.comfyui_current_job_id
        if iterate_job_id and self._iterate_poll_timer and self._iterate_poll_timer.isActive():
            job_ids.append(iterate_job_id)

        if self._batch_pending_jobs:
            job_ids.extend(list(self._batch_pending_jobs))

        if not job_ids:
            self.log("[Cancel] No running jobs to cancel")
            self.main_window.animator.show_warning("No running jobs to cancel")
            return

        reply = QMessageBox.question(
            self.main_window,
            "Cancel Jobs",
            f"Are you sure you want to cancel {len(job_ids)} running job(s)?\n\n"
            "This will complete all tasks immediately, triggering auto-deletion.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.log(f"[Cancel] Cancelling {len(job_ids)} jobs...")
        self.ui.ComfyUICancelJobs.setEnabled(False)
        self.ui.ComfyUICancelJobs.setText("Cancelling...")

        worker = Worker(cancel_deadline_jobs, job_ids)
        worker.signals.result.connect(self._on_cancel_complete)
        worker.signals.error.connect(self._on_cancel_error)
        QThreadPool.globalInstance().start(worker)

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
            self.log(f"[Cancel] Cancelled {succeeded} jobs, {failed} failed")
            for err in errors:
                self.log(f"[Cancel] Error: {err}")
            self.main_window.animator.update_status_animated(
                f"Cancelled {succeeded} jobs, {failed} failed",
                StatusColors.WARNING
            )
        else:
            self.log(f"[Cancel] Successfully cancelled {succeeded} jobs")
            self.main_window.animator.update_status_animated(
                f"Cancelled {succeeded} job(s)",
                StatusColors.WARNING
            )

    def _on_cancel_error(self, msg, tb):
        """Handle cancel jobs error."""
        self.log(f"[Cancel] Error: {msg}")
        self.ui.ComfyUICancelJobs.setText("Cancel Jobs")
        self.ui.ComfyUICancelJobs.setEnabled(True)
        self.main_window.animator.show_error(f"Failed to cancel jobs: {msg}")

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
        """Refresh gallery and request attention for new frames."""
        gallery_tab = self.main_window.get_tab("comfyui_gallery")
        if gallery_tab:
            self.log(f"{log_prefix} Triggering gallery refresh and attention for new frames")
            gallery_tab._on_refresh()
            gallery_tab.signals.request_attention.emit()
