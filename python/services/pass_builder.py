"""
Pass Builder for AYON Integration (Refactored with Strategy Pattern).

Builds composite passes from rendered layers and publishes to AYON.
Uses strategy pattern to handle farm vs local publishing without code duplication.
"""

import logging
import os
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Import our modular services
from core.config import OIIO_PATH, FRAME_PADDING, DENOISED_SUBDIRECTORY
from core.utils import normalize_path
from core.progress_utils import report_progress
from services.render_service import build_oiio_command, execute_oiio_local, load_pass_config
from ayon.service import (
    submit_oiio_to_deadline,
    AYON_AVAILABLE,
    DEADLINE_AVAILABLE,
    FarmPublishStrategy,
    LocalPublishStrategy)


class PassBuilder:
    """
    Build and publish render passes for AYON pipeline.
    Uses strategy pattern for flexible publishing (farm vs local).
    """

    def __init__(self):
        """Initialize pass builder with publishing strategies."""
        self.build_job_id = None
        self.render_name = None
        self.farm_strategy = FarmPublishStrategy()
        self.local_strategy = LocalPublishStrategy()

    def build_passes(
        self,
        passes_file: str,
        renders_path: str,
        start_frame: int,
        end_frame: int,
        use_farm: bool,
        project_name: str,
        shot: str,
        parent_job_id: str,
        task: str,
        user: str,
        output_subdirectory: str,
        do_publish: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        product_name: Optional[str] = None,
        cancel_event=None,
    ) -> None:
        """
        Build passes for rendering with optional farm submission and AYON publishing.

        Args:
            passes_file: Path to the passes JSON file
            renders_path: Path to render outputs
            start_frame: Start frame number
            end_frame: End frame number
            use_farm: Whether to use farm rendering
            project_name: AYON project name
            shot: Shot name
            parent_job_id: ID of parent Deadline job
            task: Task name
            user: User name
            output_subdirectory: Subdirectory for output files
            do_publish: Whether to publish to AYON
            progress_callback: Optional callback function(progress, message) for progress updates
        """
        from core.error_handling import check_cancelled

        # Report initial progress
        if progress_callback:
            progress_callback(30, "Validating configuration...")

        # Normalize paths
        renders_path = normalize_path(renders_path)

        # Debug logging
        logger.info(f"Processing render pass building for {passes_file}")
        logger.info(f"Renders path: {renders_path}")
        logger.info(f"Frames: {start_frame}-{end_frame}")
        logger.info(f"Farm: {use_farm}")
        logger.info(f"Project: {project_name}")
        logger.info(f"Shot: {shot}")
        logger.info(f"Task: {task}")

        # Validate passes file
        if not os.path.isfile(passes_file):
            raise FileNotFoundError(f"Passes file not found: {passes_file}")

        # Load pass configuration
        if progress_callback:
            progress_callback(35, "Loading pass configuration...")

        passes = load_pass_config(passes_file)
        if not passes:
            raise ValueError(f"No passes found in {passes_file}")

        # Initialize variables
        self.render_name = os.path.basename(passes_file).rsplit(".", 1)[0]
        render_file = os.path.basename(renders_path)

        # Build paths
        denoised = os.path.join(
            renders_path,
            DENOISED_SUBDIRECTORY,
            f"{os.path.basename(self.render_name)}.<STARTFRAME%{FRAME_PADDING}>.exr"
        )
        renders = os.path.join(
            renders_path,
            f"{os.path.basename(self.render_name)}.<STARTFRAME%{FRAME_PADDING}>.exr"
        )
        output = os.path.join(
            renders_path,
            output_subdirectory,
            f"{os.path.basename(self.render_name)}.<STARTFRAME%{FRAME_PADDING}>.exr"
        )

        # Check cancellation before building command
        check_cancelled(cancel_event)

        # Build OIIO command
        report_progress(progress_callback, 40, "Building OIIO command...")

        oiio_args = build_oiio_command(passes, denoised, renders, output)

        # Handle farm submission or local execution
        if use_farm:
            report_progress(progress_callback, 50, "Submitting OIIO job to Deadline...")

            self.build_job_id = submit_oiio_to_deadline(
                OIIO_PATH,
                " -v " + oiio_args,
                render_file,
                self.render_name,
                start_frame,
                end_frame,
                parent_job_id if parent_job_id != "NONE" else None
            )

            report_progress(progress_callback, 70, f"OIIO job submitted (ID: {self.build_job_id})")

            # Handle publishing using strategy pattern
            if do_publish and AYON_AVAILABLE:
                report_progress(progress_callback, 75, "Preparing AYON publish...")

                success = self.farm_strategy.publish(
                    project_name,
                    self.render_name,
                    start_frame,
                    end_frame,
                    renders_path,
                    shot,
                    task,
                    user,
                    output_subdirectory,
                    render_file,
                    self.build_job_id,
                    progress_callback,
                    product_name=product_name,
                )

                if success and progress_callback:
                    progress_callback(95, "Jobs submitted successfully!")
        else:
            # Local execution
            report_progress(progress_callback, 50, "Executing OIIO locally...")

            # Execute OIIO frame by frame with progress tracking
            success = execute_oiio_local(
                OIIO_PATH,
                oiio_args,
                start_frame,
                end_frame,
                progress_callback,
                cancel_event=cancel_event
            )

            if not success:
                raise RuntimeError("OIIO local execution failed")

            report_progress(progress_callback, 90, "OIIO execution complete!")

            # Check cancellation before publishing
            check_cancelled(cancel_event)

            # Handle publishing locally using strategy pattern
            if do_publish and AYON_AVAILABLE:
                report_progress(progress_callback, 91, "Preparing AYON publish...")

                success = self.local_strategy.publish(
                    project_name,
                    self.render_name,
                    start_frame,
                    end_frame,
                    renders_path,
                    shot,
                    task,
                    user,
                    output_subdirectory,
                    render_file,
                    None,  # No build_job_id for local
                    progress_callback,
                    product_name=product_name,
                )

                if success and progress_callback:
                    progress_callback(100, "Local build and publish complete!")
            else:
                if progress_callback:
                    progress_callback(95, "Local execution complete!")


# Factory function instead of singleton — avoids shared mutable state between concurrent workers
def create_pass_builder():
    """Create a new PassBuilder instance for each build operation."""
    return PassBuilder()

# Keep backward-compatible reference (use create_pass_builder() for thread safety)
pass_builder = PassBuilder()


if __name__ == "__main__":
    logger.info("Pass Builder module loaded successfully")
    if not AYON_AVAILABLE:
        logger.warning("WARNING: AYON modules not available")
    if not DEADLINE_AVAILABLE:
        logger.warning("WARNING: Deadline modules not available")
