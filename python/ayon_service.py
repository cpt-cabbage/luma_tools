"""
AYON and Deadline integration service for Luma Tools.

Handles AYON publishing, Deadline job submission, and farm integration.
"""

import os
import subprocess
import json
from typing import Optional, Dict, List

from config import (
    DEADLINE_PATH,
    DEADLINE_POOL,
    DEADLINE_GROUP,
    DEADLINE_PRIORITY_BUILD,
    DEADLINE_PRIORITY_PUBLISH,
    DEADLINE_DEPARTMENT,
    DEADLINE_CHUNK_SIZE,
    AYON_PRODUCT_TYPE,
    AYON_FAMILY,
    AYON_COLORSPACE,
    AYON_DISPLAY,
    AYON_VIEW,
    AYON_DEFAULT_FPS,
    AYON_DEFAULT_WIDTH,
    AYON_DEFAULT_HEIGHT,
    get_ocio_config,
    get_ayon_bundle
)

# AYON imports
try:
    from ayon_api import get_project
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

    result = subprocess.run(deadline_command, capture_output=True, text=True)
    result_output = result.stdout.strip()
    print("Deadline submission result: " + result_output)

    # Extract job ID from output
    buildjobid = None
    for line in result_output.split('\n'):
        if 'JobID=' in line:
            buildjobid = line.split('=')[-1].strip()
            break

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
    # Note: Files are already on shared storage, pre-mark as available at studio site
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
        },
        # Pre-populate active sites to prevent SiteAlreadyPresentError
        "site": {
            "name": "studio",
            "provider": "local_drive"
        }
    }]

    # Create instance skeleton data
    instance_skeleton_data = {
        "productName": render_name.split('.')[0],
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
        "productGroup": render_name.split('.')[0],
        "renderlayer": render_name.split('.')[0],
        "resolutionHeight": AYON_DEFAULT_HEIGHT,
        "resolutionWidth": AYON_DEFAULT_WIDTH,
        "reuseLastVersion": False,
        "review": True,
        "stagingDir_persistent": False,
        "useSequenceForReview": True,
        "version": 1,
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
        "version": 1,
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

    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

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
    if not AYON_AVAILABLE:
        print("AYON not available, skipping publish")
        return False

    # Get bundle name
    bundle = get_ayon_bundle()

    # Find AYON console executable
    ayon_console = None

    # Try to find AYON from common locations
    possible_paths = [
        r"L:\tools\_studio_tools\AYON\ayon_console.exe",
        r"C:\Program Files\AYON\ayon_console.exe",
        os.path.join(os.environ.get("AYON_ROOT", ""), "ayon_console.exe")
    ]

    for path in possible_paths:
        if os.path.exists(path):
            ayon_console = path
            break

    if not ayon_console:
        print("ERROR: Could not find ayon_console.exe")
        return False

    # Build AYON console command
    cmd = [ayon_console]
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

    print(f"Executing AYON publish locally: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        print(f"AYON Publish STDOUT: {result.stdout}")
        if result.stderr:
            print(f"AYON Publish STDERR: {result.stderr}")

        if result.returncode == 0:
            print('AYON Publish Local Process Successful')
            return True
        else:
            print(f'AYON Publish Local Process Failed with code {result.returncode}')
            return False

    except Exception as e:
        print(f'AYON Publish Local Process Failed: {e}')
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
    except:
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
