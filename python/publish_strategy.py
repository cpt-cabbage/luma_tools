"""
Publish Strategy - Strategy pattern for AYON publishing.

This module provides different strategies for publishing renders to AYON
(farm vs local), eliminating code duplication in pass_builder.py.
"""

import os
from abc import ABC, abstractmethod
from typing import Optional, Callable

from utils import normalize_path
from ayon_service import (
    convert_to_ayon_folder_path,
    create_ayon_metadata,
    write_metadata_file,
    submit_ayon_publish_to_deadline,
    publish_to_ayon_local
)

# Try to import Qt for processEvents
try:
    from PySide2.QtWidgets import QApplication
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


# Task type mapping (shared across all strategies)
TASK_TYPE_MAP = {
    "compositing": "Compositing",
    "comp": "Compositing",
    "lighting": "Lighting",
    "lgt": "Lighting",
    "lookdev": "Lookdev",
    "look": "Lookdev",
    "animation": "Animation",
    "anim": "Animation",
}


class PublishStrategy(ABC):
    """Abstract base class for AYON publishing strategies."""

    @abstractmethod
    def publish(
        self,
        project_name: str,
        render_name: str,
        start_frame: int,
        end_frame: int,
        renders_path: str,
        shot: str,
        task: str,
        user: str,
        output_subdirectory: str,
        render_file: str,
        build_job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Publish renders to AYON.

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
            build_job_id: Optional build job ID for dependency
            progress_callback: Optional progress callback

        Returns:
            bool: True if publish successful, False otherwise
        """
        pass


class FarmPublishStrategy(PublishStrategy):
    """Strategy for publishing to AYON via Deadline farm."""

    def publish(
        self,
        project_name: str,
        render_name: str,
        start_frame: int,
        end_frame: int,
        renders_path: str,
        shot: str,
        task: str,
        user: str,
        output_subdirectory: str,
        render_file: str,
        build_job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """Publish to AYON via Deadline farm submission."""
        print(f"Starting AYON farm publish setup for {render_name}")

        # Build paths
        self._report_progress(progress_callback, 78, "Building AYON folder paths...")
        working_dir, folder_path = self._build_paths(renders_path, shot, project_name)

        # Create metadata
        self._report_progress(progress_callback, 82, "Creating AYON metadata...")
        task_type = TASK_TYPE_MAP.get(task.lower(), task.capitalize())

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
            project_code=None,
            task_type=task_type
        )

        # Write metadata file
        self._report_progress(progress_callback, 86, "Writing metadata file...")
        metadata_path = self._write_metadata(
            renders_path,
            output_subdirectory,
            render_file,
            render_name,
            metadata
        )

        if not metadata_path:
            print("Failed to write metadata file, skipping publish")
            return False

        # Submit to Deadline
        self._report_progress(progress_callback, 90, "Submitting publish job to Deadline...")
        publish_job_id = submit_ayon_publish_to_deadline(
            project_name,
            render_name,
            render_file,
            metadata_path,
            folder_path,
            task,
            user,
            build_job_id
        )

        if publish_job_id:
            print(f"AYON publish job submitted: {publish_job_id}")
            return True
        else:
            print("Failed to submit AYON publish job")
            return False

    def _build_paths(self, renders_path, shot, project_name):
        """Build working directory and folder paths."""
        working_dir = renders_path.split("work")[0] + "work"
        if not working_dir.endswith("/"):
            working_dir += "/"

        folder_path_raw = working_dir.partition(shot)[0] + shot
        folder_path = convert_to_ayon_folder_path(folder_path_raw, project_name)

        print(f"Folder Path (AYON hierarchy): {folder_path}")
        print(f"Working Directory: {working_dir}")

        return working_dir, folder_path

    def _write_metadata(self, renders_path, output_subdirectory, render_file, render_name, metadata):
        """Write metadata file to disk."""
        metadata_filename = f"ayon_{render_file}_{render_name.split('.')[0]}.json"
        metadata_path = os.path.join(renders_path, output_subdirectory, metadata_filename)
        metadata_path = normalize_path(metadata_path)

        return write_metadata_file(metadata, metadata_path)

    def _report_progress(self, callback, progress, message):
        """Report progress if callback provided."""
        if callback:
            callback(progress, message)
            if QT_AVAILABLE:
                QApplication.processEvents()


class LocalPublishStrategy(PublishStrategy):
    """Strategy for publishing to AYON locally (not via farm)."""

    def publish(
        self,
        project_name: str,
        render_name: str,
        start_frame: int,
        end_frame: int,
        renders_path: str,
        shot: str,
        task: str,
        user: str,
        output_subdirectory: str,
        render_file: str,
        build_job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """Publish to AYON locally (no Deadline submission)."""
        print(f"Starting AYON local publish for {render_name}")

        # Build paths
        self._report_progress(progress_callback, 92, "Building AYON folder paths...")
        working_dir, folder_path = self._build_paths(renders_path, shot, project_name)

        # Create metadata
        self._report_progress(progress_callback, 94, "Creating AYON metadata...")
        task_type = TASK_TYPE_MAP.get(task.lower(), task.capitalize())

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
            project_code=None,
            task_type=task_type
        )

        # Write metadata file
        self._report_progress(progress_callback, 96, "Writing metadata file...")
        metadata_path = self._write_metadata(
            renders_path,
            output_subdirectory,
            render_file,
            render_name,
            metadata
        )

        if not metadata_path:
            print("Failed to write metadata file, skipping publish")
            return False

        # Execute AYON publish locally
        self._report_progress(progress_callback, 97, "Publishing to AYON...")
        success = publish_to_ayon_local(
            metadata_path,
            project_name,
            folder_path,
            task,
            user
        )

        if success:
            print(f"AYON local publish completed successfully")
            return True
        else:
            print("AYON local publish failed")
            return False

    def _build_paths(self, renders_path, shot, project_name):
        """Build working directory and folder paths."""
        working_dir = renders_path.split("work")[0] + "work"
        if not working_dir.endswith("/"):
            working_dir += "/"

        folder_path_raw = working_dir.partition(shot)[0] + shot
        folder_path = convert_to_ayon_folder_path(folder_path_raw, project_name)

        print(f"Folder Path (AYON hierarchy): {folder_path}")
        print(f"Working Directory: {working_dir}")

        return working_dir, folder_path

    def _write_metadata(self, renders_path, output_subdirectory, render_file, render_name, metadata):
        """Write metadata file to disk."""
        metadata_filename = f"ayon_{render_file}_{render_name.split('.')[0]}.json"
        metadata_path = os.path.join(renders_path, output_subdirectory, metadata_filename)
        metadata_path = normalize_path(metadata_path)

        return write_metadata_file(metadata, metadata_path)

    def _report_progress(self, callback, progress, message):
        """Report progress if callback provided."""
        if callback:
            callback(progress, message)
            if QT_AVAILABLE:
                QApplication.processEvents()
