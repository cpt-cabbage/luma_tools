"""
AYON and Deadline integration service for Luma Tools.

Handles AYON publishing, Deadline job submission, and farm integration.
Includes publish strategy pattern for farm vs local publishing.
"""

import os
import subprocess
import json
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Callable

from core.utils import normalize_path
from core.config import (
    AYON_COLORSPACE, AYON_CONSOLE, AYON_DEFAULT_FPS, AYON_DEFAULT_HEIGHT,
    AYON_DEFAULT_WIDTH, AYON_DISPLAY, AYON_FAMILY, AYON_PRODUCT_TYPE, AYON_VIEW,
    DEADLINE_CHUNK_SIZE, DEADLINE_DEPARTMENT, DEADLINE_GROUP, DEADLINE_PATH,
    DEADLINE_POOL, DEADLINE_PRIORITY_BUILD, DEADLINE_PRIORITY_PUBLISH
)

# AYON imports
try:
    from ayon_api import (
        get_project,
        get_folder_by_path,
        get_product_by_name,
        get_last_version_by_product_id,
    )
    from ayon_core.pipeline import Anatomy
    from ayon_core.pipeline.version_start import get_versioning_start
    from ayon_core.settings import get_project_settings
    from ayon_core.lib import Logger
    AYON_AVAILABLE = True
except ImportError as e:
    print(f"Warning: AYON imports failed: {e}")
    AYON_AVAILABLE = False

# Deadline imports
try:
    from ayon_deadline import DeadlineAddon
    from ayon_deadline.lib import (
        JobType,
        DeadlineJobInfo,
        get_instance_job_envs,
    )
    DEADLINE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Deadline imports failed: {e}")
    DEADLINE_AVAILABLE = False

# Try to import Qt for processEvents

from PySide6.QtWidgets import QApplication



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


def submit_oiio_to_deadline(
    oiio_path,
    oiio_args,
    job_name,
    render_name,
    start_frame,
    end_frame,
    parent_job_id=None
):
    """
    Submit OIIO pass building job to Deadline.

    Args:
        oiio_path: Path to oiiotool executable
        oiio_args: Arguments for oiiotool
        job_name: Name for the job
        render_name: Render name
        start_frame: Start frame
        end_frame: End frame
        parent_job_id: Optional parent job ID for dependencies

    Returns:
        str: Deadline job ID or None if failed
    """
    deadline_command = []
    deadline_command.append(DEADLINE_PATH)
    deadline_command.append('-SubmitCommandLineJob')
    deadline_command.append('-executable')
    deadline_command.append(f'{oiio_path}')
    deadline_command.append('-arguments')
    deadline_command.append(f'{oiio_args}')
    deadline_command.append('-frames')
    deadline_command.append(f'{start_frame}-{end_frame}step1')
    deadline_command.append('-chunksize')
    deadline_command.append(str(DEADLINE_CHUNK_SIZE))
    deadline_command.append('-pool')
    deadline_command.append(DEADLINE_POOL)
    deadline_command.append('-group')
    deadline_command.append(DEADLINE_GROUP)
    deadline_command.append('-priority')
    deadline_command.append(str(DEADLINE_PRIORITY_BUILD))
    deadline_command.append('-prop')
    deadline_command.append(f'Department={DEADLINE_DEPARTMENT}')
    deadline_command.append('-prop')
    deadline_command.append(f'BatchName={job_name}')
    deadline_command.append('-name')
    deadline_command.append(f'OIIO COMBINE - {render_name}')

    if parent_job_id and parent_job_id != "NONE":
        deadline_command.append('-prop')
        deadline_command.append(f'JobDependencies={parent_job_id}')

    from services.deadline_utils import submit_deadline_job

    buildjobid = submit_deadline_job(deadline_command)
    if buildjobid:
        print(f"Passes Build Deadline Job ID: {buildjobid}")
    return buildjobid


def convert_to_ayon_folder_path(filesystem_path, project_name):
    """
    Convert filesystem path to AYON folder hierarchy path.

    Args:
        filesystem_path: Windows filesystem path
        project_name: AYON project name

    Returns:
        str: AYON folder path (e.g., '/shots/ChiefChickenTest/sh0010')

    Example:
        W:/LumaRND/shots/ChiefChickenTest/sh0010/work
        -> /shots/ChiefChickenTest/sh0010
    """
    # Normalize slashes
    path = filesystem_path.replace("\\", "/")

    # Remove /work suffix if present
    if "/work" in path:
        path = path.split("/work")[0]

    # Convert filesystem path to AYON hierarchy path
    if project_name in path:
        # Remove root and project name, keep only hierarchy
        path = "/" + path.split(f"{project_name}/", 1)[1]

    return path


def get_next_version(project_name: str, folder_path: str, product_name: str) -> int:
    """
    Get the next available version number for a product in AYON.

    Args:
        project_name: Name of the AYON project
        folder_path: AYON folder path (e.g., /shots/seq01/sh0010)
        product_name: Name of the product (e.g., renderMain)

    Returns:
        int: Next version number (starts from 1 if no versions exist)
    """
    if not AYON_AVAILABLE:
        print("[get_next_version] AYON not available, defaulting to version 1")
        return 1

    try:
        # Get the folder entity
        folder = get_folder_by_path(project_name, folder_path)
        if not folder:
            print(f"[get_next_version] Folder not found: {folder_path}, defaulting to version 1")
            return 1

        # Get the product by name within this folder
        product = get_product_by_name(project_name, product_name, folder["id"])
        if not product:
            print(f"[get_next_version] Product '{product_name}' not found in {folder_path}, starting at version 1")
            return 1

        # Get the last version of this product
        last_version = get_last_version_by_product_id(project_name, product["id"])
        if not last_version:
            print(f"[get_next_version] No versions found for '{product_name}', starting at version 1")
            return 1

        next_ver = last_version["version"] + 1
        print(f"[get_next_version] Found version {last_version['version']}, next version will be {next_ver}")
        return next_ver

    except Exception as e:
        print(f"[get_next_version] Error querying versions: {e}, defaulting to version 1")
        return 1


def create_ayon_metadata_single_file(
    project_name: str,
    file_path: str,
    product_name: str,
    product_type: str,
    folder_path: str,
    task: str,
    user: str,
    variant: str = "",
    comment: str = "",
    project_code: str = None,
    task_type: str = None
) -> dict:
    """
    Create AYON metadata JSON for publishing a single file (FBX, GLB, image, etc.).

    This is distinct from create_ayon_metadata which handles EXR sequences.

    Args:
        project_name: AYON project name
        file_path: Full path to the file being published
        product_name: Product name (e.g., "myModel")
        product_type: AYON product type (model, image, animation, etc.)
        folder_path: AYON folder path (e.g., "/shots/seq01/sh0010")
        task: Task name
        user: Username
        variant: Optional variant name
        comment: Optional comment
        project_code: Optional project code (defaults to project_name)
        task_type: Optional task type

    Returns:
        dict: Metadata dictionary ready for AYON publish
    """
    logger = Logger.get_logger(__name__) if AYON_AVAILABLE else None

    # Normalize path
    file_path = file_path.replace("\\", "/")
    staging_dir = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower().lstrip(".")

    # Use defaults if not provided
    if project_code is None:
        if AYON_AVAILABLE:
            try:
                project_entity = get_project(project_name)
                project_code = project_entity.get("code", project_name)
            except Exception as e:
                if logger:
                    logger.warning(f"Could not get project code from AYON: {e}")
                project_code = project_name
        else:
            project_code = project_name

    if task_type is None:
        task_type = TASK_TYPE_MAP.get(task.lower(), task.capitalize())

    # Determine families based on product type
    families = [product_type]

    # Add review tag for certain types
    review_types = {"image", "render", "plate", "review"}
    has_review = product_type in review_types

    # Build representation
    representation = {
        "name": ext,
        "ext": ext,
        "files": filename,  # Single file, not a list
        "stagingDir": staging_dir,
    }

    # Add colorspace for image types
    if ext in ["exr", "png", "jpg", "jpeg", "tif", "tiff"]:
        representation["colorspaceData"] = {
            "colorspace": AYON_COLORSPACE,
            "config": {
                "path": get_ocio_config(),
                "template": get_ocio_config()
            },
            "display": AYON_DISPLAY,
            "view": AYON_VIEW
        }
        if has_review:
            representation["tags"] = ["review"]

    # Get next version number
    next_version = get_next_version(project_name, folder_path, product_name)

    # Create instance data
    instance_data = {
        "productName": product_name,
        "productType": product_type,
        "family": product_type,
        "families": families,
        "folderPath": folder_path,
        "task": task,
        "host": "luma_tools",
        "source": file_path,
        "representations": [representation],
        "farm": False,
        "comment": comment,
        "variant": variant,
        "version": next_version,
        "anatomyData": {
            "project": {"name": project_name, "code": project_code},
            "folder": {"name": os.path.basename(folder_path)},
            "task": {"name": task, "type": task_type},
        }
    }

    # Add frame info only for sequences/animations
    if product_type in ["render", "plate", "animation"]:
        instance_data["frameStart"] = 1001
        instance_data["frameEnd"] = 1001
        instance_data["fps"] = AYON_DEFAULT_FPS

    # Create publish job data
    publish_job = {
        "folderPath": folder_path,
        "source": file_path,
        "user": user,
        "intent": None,
        "comment": comment,
        "job": {},
        "version": next_version,
        "instances": [instance_data]
    }

    return publish_job


def create_ayon_metadata(
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
    task_type=None
):
    """
    Create AYON metadata JSON for farm publishing.

    Args:
        project_name: AYON project name
        render_name: Render name
        start_frame: Start frame
        end_frame: End frame
        renders_path: Path to renders
        folder_path: AYON folder path
        task: Task name
        user: Username
        output_subdirectory: Output subdirectory
        working_dir: Working directory
        render_file: Render file name
        project_code: Optional project code (defaults to project_name)
        task_type: Optional task type (defaults to "Compositing")

    Returns:
        dict: Metadata dictionary
    """
    logger = Logger.get_logger(__name__) if AYON_AVAILABLE else None

    # Use defaults if not provided
    if project_code is None:
        # Try to get project code from AYON API
        if AYON_AVAILABLE:
            try:
                project_entity = get_project(project_name)
                project_code = project_entity.get("code", project_name)
            except Exception as e:
                if logger:
                    logger.warning(f"Could not get project code from AYON: {e}")
                project_code = project_name
        else:
            project_code = project_name

    if task_type is None:
        # Default to Compositing since this is for render compositing
        task_type = "Compositing"

    # Generate file list
    expected_files = []
    for frame in range(start_frame, end_frame + 1):
        expected_files.append(f"{render_name.split('.')[0]}.{frame:04d}.exr")

    # Build staging directory
    staging_dir_path = os.path.join(renders_path, output_subdirectory)
    staging_dir_path = staging_dir_path.replace("\\", "/")

    # Create representations
    representations = [{
        "name": "exr",
        "ext": "exr",
        "files": expected_files,
        "fps": AYON_DEFAULT_FPS,
        "frameStart": start_frame,
        "frameEnd": end_frame,
        "stagingDir": staging_dir_path,
        "tags": ["review"],
        "colorspaceData": {
            "colorspace": AYON_COLORSPACE,
            "config": {
                "path": get_ocio_config(),
                "template": get_ocio_config()
            },
            "display": AYON_DISPLAY,
            "view": AYON_VIEW
        }
    }]

    # Get next version number
    product_name = render_name.split('.')[0]
    next_version = get_next_version(project_name, folder_path, product_name)

    # Create instance skeleton data
    instance_skeleton_data = {
        "productName": product_name,
        "productType": AYON_PRODUCT_TYPE,
        "family": AYON_FAMILY,
        "families": ["render", "review"],
        "folderPath": folder_path,
        "task": task,
        "host": "houdini",  # Host application - required for review extraction
        "frameStart": start_frame,
        "frameEnd": end_frame,
        "frameStartHandle": start_frame,
        "frameEndHandle": end_frame,
        "handleStart": 0,
        "handleEnd": 0,
        "fps": AYON_DEFAULT_FPS,
        "source": "{root[work]}/" + working_dir.split("work/")[-1] + render_file,
        "representations": representations,
        # Mark this as farm/local publish to help sitesync plugin logic
        "farm": True,
        # Required fields
        "aov": "",
        "colorspace": AYON_COLORSPACE,
        "comment": "",
        "extendFrames": None,
        "hasExplicitFrames": True,
        "inputVersions": [],
        "jobBatchName": "",
        "multipartExr": True,
        "overrideExistingFrame": None,
        "pixelAspect": 1.0,
        "productGroup": product_name,
        "renderlayer": product_name,
        "resolutionHeight": AYON_DEFAULT_HEIGHT,
        "resolutionWidth": AYON_DEFAULT_WIDTH,
        "reuseLastVersion": False,
        "review": True,
        "stagingDir_persistent": False,
        "useSequenceForReview": True,
        "version": next_version,
        "anatomyData": {
            "project": {"name": project_name, "code": project_code},
            "folder": {"name": os.path.basename(folder_path)},
            "task": {"name": task, "type": task_type},
            "root": {"work": renders_path.split("work")[0] + "work"}
        }
    }

    # Create publish job data
    publish_job = {
        "folderPath": folder_path,
        "frameStart": start_frame,
        "frameEnd": end_frame,
        "fps": AYON_DEFAULT_FPS,
        "source": instance_skeleton_data["source"],
        "user": user,
        "intent": None,
        "comment": "",
        "job": {},
        "version": next_version,
        "instances": [instance_skeleton_data]
    }

    return publish_job


def write_metadata_file(metadata_dict, output_path):
    """
    Write AYON metadata to JSON file.

    Args:
        metadata_dict: Metadata dictionary
        output_path: Path to write metadata file

    Returns:
        str: Path to written metadata file
    """
    logger = Logger.get_logger(__name__) if AYON_AVAILABLE else None

    # Validate output_path
    if not output_path or not output_path.strip():
        raise ValueError("Output path cannot be empty")

    # Get directory path
    dir_path = os.path.dirname(output_path)

    # Ensure directory exists (handle case where dirname returns empty string for filename-only paths)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    else:
        # If no directory in path, use current working directory
        output_path = os.path.join(os.getcwd(), output_path)

    # Write metadata
    try:
        with open(output_path, "w") as f:
            json.dump(metadata_dict, f, indent=4, sort_keys=False)

        if logger:
            logger.info(f"Successfully wrote metadata to: {output_path}")

            # Verify required fields
            root_keys = list(metadata_dict.keys())
            required_fields = ["user", "comment", "job", "instances", "version", "folderPath"]
            missing_fields = [f for f in required_fields if f not in root_keys]

            if missing_fields:
                logger.error(f"MISSING REQUIRED FIELDS: {missing_fields}")
            else:
                logger.info(f"All required fields present: {required_fields}")
        else:
            print(f"Successfully wrote metadata to: {output_path}")

        return output_path

    except Exception as e:
        error_msg = f"Failed to write metadata file: {e}"
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)
        return None


def publish_to_ayon_local(
    metadata_path,
    project_name,
    folder_path,
    task,
    user
):
    """
    Execute AYON publish locally (not on farm).

    Args:
        metadata_path: Path to metadata JSON
        project_name: AYON project name
        folder_path: AYON folder path
        task: Task name
        user: Username

    Returns:
        bool: True if successful, False otherwise
    """
    import threading
    import queue

    if not AYON_AVAILABLE:
        print("AYON not available, skipping publish")
        return False

    # Get bundle name
    bundle = get_ayon_bundle()

    # Build AYON console command
    cmd = [AYON_CONSOLE]
    cmd.extend(["--headless", "publish", metadata_path])

    # Add bundle arguments
    if bundle == "staging":
        cmd.append("--use-staging")
    elif bundle != "production":
        cmd.extend(["--bundle", bundle])

    # Set environment variables for the process
    env = os.environ.copy()
    env["AYON_PROJECT_NAME"] = project_name
    env["AYON_FOLDER_PATH"] = folder_path
    env["AYON_TASK_NAME"] = task
    env["AYON_BUNDLE_NAME"] = bundle
    env["AYON_USERNAME"] = user
    # CRITICAL: Force Python subprocess to use unbuffered output
    # Without this, the subprocess buffers stdout and readline() blocks
    env["PYTHONUNBUFFERED"] = "1"
    # Disable SiteSync for local publishes - files are already on shared storage
    # This prevents SiteAlreadyPresentError from blocking the publish
    env["AYON_SITESYNC_ENABLED"] = "0"

    print(f"Executing AYON publish locally: {' '.join(cmd)}")

    def stream_reader(pipe, output_queue, prefix):
        """Read lines from pipe and put them in queue."""
        try:
            for line in iter(pipe.readline, ''):
                if line:
                    output_queue.put((prefix, line.rstrip()))
            pipe.close()
        except Exception as e:
            output_queue.put((prefix, f"[Reader error: {e}]"))

    try:
        # Use Popen for real-time output streaming
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        # Use threads to read stdout and stderr concurrently to avoid deadlocks
        output_queue = queue.Queue()

        stdout_thread = threading.Thread(
            target=stream_reader,
            args=(process.stdout, output_queue, "AYON")
        )
        stderr_thread = threading.Thread(
            target=stream_reader,
            args=(process.stderr, output_queue, "AYON STDERR")
        )

        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()

        # Collect output while process runs
        stdout_lines = []
        stderr_lines = []

        while process.poll() is None or not output_queue.empty():
            try:
                prefix, line = output_queue.get(timeout=0.1)
                if line:
                    print(f"{prefix}: {line}")
                    if prefix == "AYON":
                        stdout_lines.append(line)
                    else:
                        stderr_lines.append(line)

                    # Detect key progress stages for better feedback
                    if "ExtractReview" in line and "Processing" in line:
                        print("  -> Extracting review files...")
                    elif "IntegrateAsset" in line:
                        print("  -> Integrating assets into AYON...")
                    elif "Successfully" in line or "success" in line.lower():
                        print("  [OK] Operation successful")
                    elif "Failed" in line or "ERROR" in line:
                        print(f"  [ERROR] Error detected: {line}")
            except queue.Empty:
                continue

        # Wait for threads to finish
        stdout_thread.join(timeout=2.0)
        stderr_thread.join(timeout=2.0)

        # Drain any remaining output
        while not output_queue.empty():
            try:
                prefix, line = output_queue.get_nowait()
                if line:
                    print(f"{prefix}: {line}")
                    if prefix == "AYON":
                        stdout_lines.append(line)
                    else:
                        stderr_lines.append(line)
            except queue.Empty:
                break

        # Check return code
        if process.returncode == 0:
            print('AYON Publish Local Process Successful')
            return True
        else:
            # Check for SiteAlreadyPresentError - this error occurs AFTER successful integration
            # The IntegrateAsset plugin completes before IntegrateSiteSync fails
            all_output = "\n".join(stdout_lines + stderr_lines)
            if "SiteAlreadyPresentError" in all_output and "IntegrateAsset" in all_output:
                print('AYON Publish completed successfully')
                return True

            print(f'AYON Publish Local Process Failed with code {process.returncode}')
            # Print last few lines for debugging
            if stdout_lines:
                print("Last stdout lines:")
                for line in stdout_lines[-10:]:
                    print(f"  {line}")
            if stderr_lines:
                print("Last stderr lines:")
                for line in stderr_lines[-10:]:
                    print(f"  {line}")
            return False

    except Exception as e:
        print(f'AYON Publish Local Process Failed: {e}')
        import traceback
        traceback.print_exc()
        return False


def submit_ayon_publish_to_deadline(
    project_name,
    render_name,
    render_file,
    metadata_path,
    folder_path,
    task,
    user,
    build_job_id=None
):
    """
    Submit AYON publish job to Deadline.

    Args:
        project_name: AYON project name
        render_name: Render name
        render_file: Render file name
        metadata_path: Path to metadata JSON
        folder_path: AYON folder path
        task: Task name
        user: Username
        build_job_id: Optional build job ID for dependency

    Returns:
        str: Publish job ID or None if failed
    """
    if not AYON_AVAILABLE or not DEADLINE_AVAILABLE:
        print("AYON or Deadline not available, skipping publish")
        return None

    logger = Logger.get_logger(__name__)

    try:
        # Get project settings and create Deadline addon
        project_settings = get_project_settings(project_name)
        deadline_addon = DeadlineAddon(project_name, project_settings)
    except Exception as e:
        logger.error(f"Failed to initialize AYON/Deadline: {e}")
        return None

    # Get bundle name
    bundle = get_ayon_bundle()

    # Build AYON console arguments
    args = [
        "--headless",
        "publish",
        metadata_path,
        "--targets", "deadline",
        "--targets", "farm",
    ]

    # Add bundle arguments
    if bundle == "staging":
        args.append("--use-staging")
    elif bundle != "production":
        args.extend(["--bundle", bundle])

    # Create Deadline job info
    job_info = DeadlineJobInfo(Plugin="Ayon")
    job_info.Name = f"Publish - {render_name}"
    job_info.BatchName = render_file
    job_info.Department = task
    job_info.Priority = DEADLINE_PRIORITY_PUBLISH
    job_info.Group = DEADLINE_GROUP
    job_info.Pool = DEADLINE_POOL
    job_info.UserName = user
    job_info.Comment = f"AYON publish for {render_name}"

    # Set environment variables
    job_info.EnvironmentKeyValue = {
        "AYON_PROJECT_NAME": project_name,
        "AYON_FOLDER_PATH": folder_path,
        "AYON_TASK_NAME": task,
        "AYON_BUNDLE_NAME": bundle,
        "AYON_USERNAME": user,
    }

    # Add dependency on build job
    if build_job_id:
        job_info.JobDependencies = build_job_id

    # Get Deadline server name
    try:
        deadline_settings = project_settings.get("deadline", {})
        server_name = deadline_settings.get("deadline_server", "default")
    except (KeyError, AttributeError, Exception) as e:
        logger.warning(f"Could not get Deadline server from settings: {e}")
        server_name = "default"

    # Submit the job
    try:
        logger.info(f"Submitting publish job to Deadline server: {server_name}")
        logger.info(f"AYON console args: {' '.join(args)}")

        response = deadline_addon.submit_ayon_plugin_job(
            server_name,
            args,
            job_info
        )

        # Extract job ID
        publish_job_id = response.get("response", {}).get("_id")

        if publish_job_id:
            logger.info(f"Publisher Submission Successful - Job ID: {publish_job_id}")
        else:
            logger.warning("Could not extract publish job ID from response")

        return publish_job_id

    except Exception as e:
        logger.error(f"Failed to submit publish job: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


# ============================================================================
# Publish Strategy Pattern
# ============================================================================

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
            QApplication.processEvents()


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
