"""
Pass Builder for AYON Integration (Refactored with Strategy Pattern).

Builds composite passes from rendered layers and publishes to AYON.
Uses strategy pattern to handle farm vs local publishing without code duplication.
"""

import os
from typing import Optional, Callable

# Import our modular services
from config import OIIO_PATH, FRAME_PADDING
from utils import normalize_path
from render_service import build_oiio_command, execute_oiio_local, load_pass_config
from ayon_service import (
    submit_oiio_to_deadline,
    AYON_AVAILABLE,
    DEADLINE_AVAILABLE,
    FarmPublishStrategy,
    LocalPublishStrategy
)

# Try to import Qt for processEvents
try:
    from PySide2.QtWidgets import QApplication
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


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
        progress_callback: Optional[Callable[[int, str], None]] = None
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
        # Report initial progress
        if progress_callback:
            progress_callback(30, "Validating configuration...")

        # Normalize paths
        renders_path = normalize_path(renders_path)

        # Debug prints
        print(f"Processing render pass building for {passes_file}")
        print(f"Renders path: {renders_path}")
        print(f"Frames: {start_frame}-{end_frame}")
        print(f"Farm: {use_farm}")
        print(f"Project: {project_name}")
        print(f"Shot: {shot}")
        print(f"Task: {task}")

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
            "denoised",
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

        # Build OIIO command
        if progress_callback:
            progress_callback(40, "Building OIIO command...")
            if QT_AVAILABLE:
                QApplication.processEvents()

        oiio_args = build_oiio_command(passes, denoised, renders, output)

        # Handle farm submission or local execution
        if use_farm:
            if progress_callback:
                progress_callback(50, "Submitting OIIO job to Deadline...")
                if QT_AVAILABLE:
                    QApplication.processEvents()

            self.build_job_id = submit_oiio_to_deadline(
                OIIO_PATH,
                " -v " + oiio_args,
                render_file,
                self.render_name,
                start_frame,
                end_frame,
                parent_job_id if parent_job_id != "NONE" else None
            )

            if progress_callback:
                progress_callback(70, f"OIIO job submitted (ID: {self.build_job_id})")
                if QT_AVAILABLE:
                    QApplication.processEvents()

            # Handle publishing using strategy pattern
            if do_publish and AYON_AVAILABLE:
                if progress_callback:
                    progress_callback(75, "Preparing AYON publish...")
                    if QT_AVAILABLE:
                        QApplication.processEvents()

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
                    progress_callback
                )

                if success and progress_callback:
                    progress_callback(95, "Jobs submitted successfully!")
                    if QT_AVAILABLE:
                        QApplication.processEvents()
        else:
            # Local execution
            if progress_callback:
                progress_callback(50, "Executing OIIO locally...")
                if QT_AVAILABLE:
                    QApplication.processEvents()

            # Execute OIIO frame by frame with progress tracking
            success = execute_oiio_local(
                OIIO_PATH,
                oiio_args,
                start_frame,
                end_frame,
                progress_callback
            )

            if not success:
                raise RuntimeError("OIIO local execution failed")

            if progress_callback:
                progress_callback(90, "OIIO execution complete!")
                if QT_AVAILABLE:
                    QApplication.processEvents()

            # Handle publishing locally using strategy pattern
            if do_publish and AYON_AVAILABLE:
                if progress_callback:
                    progress_callback(91, "Preparing AYON publish...")
                    if QT_AVAILABLE:
                        QApplication.processEvents()

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
                    progress_callback
                )

                if success and progress_callback:
                    progress_callback(100, "Local build and publish complete!")
                    if QT_AVAILABLE:
                        QApplication.processEvents()
            else:
                if progress_callback:
                    progress_callback(95, "Local execution complete!")


# Create singleton instance for backward compatibility
pass_builder = PassBuilder()


if __name__ == "__main__":
    print("Pass Builder module loaded successfully")
    if not AYON_AVAILABLE:
        print("WARNING: AYON modules not available")
    if not DEADLINE_AVAILABLE:
        print("WARNING: Deadline modules not available")
