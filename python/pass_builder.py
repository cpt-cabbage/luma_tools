"""
Pass Builder for AYON Integration (Refactored).

Builds composite passes from rendered layers and publishes to AYON via Deadline farm.
"""

import os
from typing import Optional, Callable

# Import our modular services
from config import OIIO_PATH, FRAME_PADDING
from utils import normalize_path
from render_service import build_oiio_command, execute_oiio_local, load_pass_config
from ayon_service import (
    submit_oiio_to_deadline,
    convert_to_ayon_folder_path,
    create_ayon_metadata,
    write_metadata_file,
    submit_ayon_publish_to_deadline,
    AYON_AVAILABLE,
    DEADLINE_AVAILABLE
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
    """

    def __init__(self):
        """Initialize pass builder."""
        self.build_job_id = None
        self.render_name = None

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

            # Handle publishing
            if do_publish and AYON_AVAILABLE:
                if progress_callback:
                    progress_callback(75, "Preparing AYON publish...")
                    if QT_AVAILABLE:
                        QApplication.processEvents()

                self._publish_to_ayon(
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
                    progress_callback
                )

                if progress_callback:
                    progress_callback(95, "Jobs submitted successfully!")
                    if QT_AVAILABLE:
                        QApplication.processEvents()
        else:
            # Local execution
            if progress_callback:
                progress_callback(50, "Executing OIIO locally...")

            execute_oiio_local(OIIO_PATH, oiio_args)

            if progress_callback:
                progress_callback(95, "Local execution complete!")

    def _publish_to_ayon(
        self,
        project_name,
        render_name,
        start_frame,
        end_frame,
        renders_path,
        shot,
        task,
        user,
        output_subdirectory,
        render_file,
        progress_callback=None
    ):
        """
        Internal method to handle AYON publishing.

        Args:
            project_name: AYON project name
            render_name: Render name
            start_frame: Start frame
            end_frame: End frame
            renders_path: Path to renders
            shot: Shot name
            task: Task name
            user: Username
            output_subdirectory: Output subdirectory
            render_file: Render file name
            progress_callback: Optional progress callback
        """
        print(f"Starting AYON publish setup for {render_name}")

        if progress_callback:
            progress_callback(78, "Building AYON folder paths...")
            if QT_AVAILABLE:
                QApplication.processEvents()

        # Build working directory path
        working_dir = renders_path.split("work")[0] + "work"
        if not working_dir.endswith("/"):
            working_dir += "/"

        # Build folder path (AYON folder path, not file system path)
        folder_path_raw = working_dir.partition(shot)[0] + shot
        folder_path = convert_to_ayon_folder_path(folder_path_raw, project_name)

        print(f"Folder Path (AYON hierarchy): {folder_path}")
        print(f"Working Directory: {working_dir}")

        # Create AYON metadata
        if progress_callback:
            progress_callback(82, "Creating AYON metadata...")
            if QT_AVAILABLE:
                QApplication.processEvents()

        # Get task type mapping (task name -> task type)
        # Common task types: Compositing, Lighting, Animation, etc.
        task_type_map = {
            "compositing": "Compositing",
            "comp": "Compositing",
            "lighting": "Lighting",
            "lgt": "Lighting",
            "lookdev": "Lookdev",
            "look": "Lookdev",
            "animation": "Animation",
            "anim": "Animation",
        }
        # Get task type from mapping, default to capitalize the task name
        task_type = task_type_map.get(task.lower(), task.capitalize())

        metadata = create_ayon_metadata(
            project_name,
            render_name,
            start_frame,
            end_frame,
            renders_path,
            folder_path,
            task,
            user,
            output_subdirectory,
            working_dir,
            render_file,
            project_code=None,  # Will auto-fetch from AYON
            task_type=task_type
        )

        # Write metadata file
        if progress_callback:
            progress_callback(86, "Writing metadata file...")
            if QT_AVAILABLE:
                QApplication.processEvents()

        metadata_filename = f"ayon_{render_file}_{render_name.split('.')[0]}.json"
        metadata_path = os.path.join(renders_path, output_subdirectory, metadata_filename)
        metadata_path = normalize_path(metadata_path)

        written_path = write_metadata_file(metadata, metadata_path)

        if not written_path:
            print("Failed to write metadata file, skipping publish")
            return

        # Submit publish job to Deadline
        if progress_callback:
            progress_callback(90, "Submitting publish job to Deadline...")
            if QT_AVAILABLE:
                QApplication.processEvents()

        publish_job_id = submit_ayon_publish_to_deadline(
            project_name,
            render_name,
            render_file,
            metadata_path,
            folder_path,
            task,
            user,
            self.build_job_id
        )

        if publish_job_id:
            print(f"AYON publish job submitted: {publish_job_id}")
        else:
            print("Failed to submit AYON publish job")


# Create singleton instance for backward compatibility
pass_builder = PassBuilder()


print("=" * 60)
print("LOADING: pass_builder.py (NEW REFACTORED VERSION)")
print("=" * 60)

if __name__ == "__main__":
    print("Pass Builder module loaded successfully")
    if not AYON_AVAILABLE:
        print("WARNING: AYON modules not available")
    if not DEADLINE_AVAILABLE:
        print("WARNING: Deadline modules not available")
