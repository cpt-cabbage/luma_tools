"""
Canvas metadata management for multi-canvas support.

Provides:
- CanvasScope enum (JOB/SHOT)
- CanvasDef dataclass for canvas definitions
- CanvasMetadataManager for CRUD operations on canvases

Storage structure:
    {network_path}/_canvas/{jobname}/           # Job-wide canvases
        _index.json
        canvas_{name}.json
        presence/
        {shot}/                                  # Shot-specific canvases
            _index.json
            canvas_{name}.json
            presence/
"""

import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from core.metadata_file import MetadataFile
from core.utils import ensure_directory

logger = logging.getLogger(__name__)


class CanvasScope(Enum):
    """Scope of a canvas - job-wide or shot-specific."""
    JOB = "job"
    SHOT = "shot"


@dataclass
class CanvasDef:
    """Definition for a canvas."""
    id: str
    name: str
    filename: str
    scope: str  # "job" or "shot" - stored as string for JSON serialization
    created: str
    created_by: str
    modified: str
    modified_by: str
    item_count: int = 0

    @property
    def scope_enum(self) -> CanvasScope:
        """Get scope as enum."""
        return CanvasScope(self.scope)

    @classmethod
    def from_dict(cls, data: Dict) -> "CanvasDef":
        """Create CanvasDef from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            filename=data.get("filename", ""),
            scope=data.get("scope", "job"),
            created=data.get("created", ""),
            created_by=data.get("created_by", ""),
            modified=data.get("modified", ""),
            modified_by=data.get("modified_by", ""),
            item_count=data.get("item_count", 0),
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class CanvasMetadataManager:
    """
    Manages canvas metadata for both job and shot scopes.

    Handles:
    - Listing, creating, renaming, deleting canvases
    - Tracking canvas metadata (created/modified dates, item counts)
    - Migration from legacy single-canvas format
    """

    INDEX_FILENAME = "_index.json"
    INDEX_VERSION = "1.0"

    def __init__(self, base_dir: str, jobname: str, shot: str, username: str):
        """
        Initialize the canvas metadata manager.

        Args:
            base_dir: Base directory for canvas storage (network path)
            jobname: AYON job/project name
            shot: AYON shot name (can be empty for no shot context)
            username: Current user's name
        """
        self._base_dir = base_dir
        self._jobname = jobname or "default"
        self._shot = shot or ""
        self._username = username or "unknown"

        # Setup metadata files for each scope
        self._job_index = MetadataFile(self.job_canvas_dir, self.INDEX_FILENAME)
        if self._shot:
            self._shot_index = MetadataFile(self.shot_canvas_dir, self.INDEX_FILENAME)
        else:
            self._shot_index = None

        # Run migration on init
        self._ensure_migrated()

    @property
    def job_canvas_dir(self) -> str:
        """Get directory for job-wide canvases."""
        return os.path.join(self._base_dir, "_canvas", self._jobname)

    @property
    def shot_canvas_dir(self) -> str:
        """Get directory for shot-specific canvases."""
        if not self._shot:
            return ""
        return os.path.join(self._base_dir, "_canvas", self._jobname, self._shot)

    def _get_index_for_scope(self, scope: CanvasScope) -> Optional[MetadataFile]:
        """Get the appropriate index file for a scope."""
        if scope == CanvasScope.JOB:
            return self._job_index
        elif scope == CanvasScope.SHOT:
            return self._shot_index
        return None

    def _get_dir_for_scope(self, scope: CanvasScope) -> str:
        """Get the directory for a scope."""
        if scope == CanvasScope.JOB:
            return self.job_canvas_dir
        elif scope == CanvasScope.SHOT:
            return self.shot_canvas_dir
        return ""

    def _sanitize_filename(self, name: str) -> str:
        """Convert canvas name to safe filename."""
        # Replace spaces and special chars with underscores
        safe = re.sub(r'[^\w\-]', '_', name.lower())
        # Remove consecutive underscores
        safe = re.sub(r'_+', '_', safe)
        # Remove leading/trailing underscores
        safe = safe.strip('_')
        return f"canvas_{safe}.json" if safe else "canvas_untitled.json"

    def _load_index(self, scope: CanvasScope) -> Dict:
        """Load index for a scope, creating default if needed."""
        index_file = self._get_index_for_scope(scope)
        if not index_file:
            return {"version": self.INDEX_VERSION, "canvases": {}}

        data = index_file.load(default={"version": self.INDEX_VERSION, "canvases": {}})
        if "canvases" not in data:
            data["canvases"] = {}
        return data

    def _save_index(self, scope: CanvasScope, data: Dict) -> bool:
        """Save index for a scope."""
        index_file = self._get_index_for_scope(scope)
        if not index_file:
            return False

        # Ensure directory exists
        canvas_dir = self._get_dir_for_scope(scope)
        ensure_directory(canvas_dir)

        return index_file.save(data)

    def list_canvases(self, scope: Optional[CanvasScope] = None) -> List[CanvasDef]:
        """
        List all canvases, optionally filtered by scope.

        Args:
            scope: Optional scope filter. None returns all canvases.

        Returns:
            List of CanvasDef objects, job canvases first, then shot canvases.
        """
        canvases = []

        # Get job canvases
        if scope is None or scope == CanvasScope.JOB:
            job_data = self._load_index(CanvasScope.JOB)
            for canvas_dict in job_data.get("canvases", {}).values():
                canvases.append(CanvasDef.from_dict(canvas_dict))

        # Get shot canvases (if shot context exists)
        if self._shot and (scope is None or scope == CanvasScope.SHOT):
            shot_data = self._load_index(CanvasScope.SHOT)
            for canvas_dict in shot_data.get("canvases", {}).values():
                canvases.append(CanvasDef.from_dict(canvas_dict))

        # Sort by modified date descending (most recent first)
        canvases.sort(key=lambda c: c.modified, reverse=True)

        return canvases

    def create_canvas(self, name: str, scope: CanvasScope) -> Optional[CanvasDef]:
        """
        Create a new canvas.

        Args:
            name: Display name for the canvas
            scope: Scope (JOB or SHOT)

        Returns:
            CanvasDef for the created canvas, or None on error.
        """
        if scope == CanvasScope.SHOT and not self._shot:
            logger.error("Cannot create shot canvas without shot context")
            return None

        canvas_dir = self._get_dir_for_scope(scope)
        if not canvas_dir:
            logger.error(f"Invalid scope for canvas creation: {scope}")
            return None

        # Generate unique ID and filename
        canvas_id = str(uuid.uuid4())[:8]
        filename = self._sanitize_filename(name)

        # Ensure unique filename
        base_filename = filename
        counter = 1
        while os.path.exists(os.path.join(canvas_dir, filename)):
            name_part = base_filename.replace("canvas_", "").replace(".json", "")
            filename = f"canvas_{name_part}_{counter}.json"
            counter += 1

        now = datetime.now().isoformat()
        canvas_def = CanvasDef(
            id=canvas_id,
            name=name,
            filename=filename,
            scope=scope.value,
            created=now,
            created_by=self._username,
            modified=now,
            modified_by=self._username,
            item_count=0,
        )

        # Add to index
        index_data = self._load_index(scope)
        index_data["canvases"][canvas_id] = canvas_def.to_dict()

        if not self._save_index(scope, index_data):
            logger.error(f"Failed to save index after creating canvas: {name}")
            return None

        # Create empty canvas file
        canvas_path = os.path.join(canvas_dir, filename)
        ensure_directory(canvas_dir)
        try:
            with open(canvas_path, 'w', encoding='utf-8') as f:
                f.write('{}')
        except Exception as e:
            logger.error(f"Failed to create canvas file {canvas_path}: {e}")
            return None

        logger.info(f"Created canvas: {name} ({scope.value}) at {canvas_path}")
        return canvas_def

    def get_canvas(self, canvas_id: str) -> Optional[CanvasDef]:
        """
        Get a canvas by ID.

        Args:
            canvas_id: Canvas ID to look up

        Returns:
            CanvasDef if found, None otherwise.
        """
        # Check job canvases
        job_data = self._load_index(CanvasScope.JOB)
        if canvas_id in job_data.get("canvases", {}):
            return CanvasDef.from_dict(job_data["canvases"][canvas_id])

        # Check shot canvases
        if self._shot:
            shot_data = self._load_index(CanvasScope.SHOT)
            if canvas_id in shot_data.get("canvases", {}):
                return CanvasDef.from_dict(shot_data["canvases"][canvas_id])

        return None

    def get_canvas_path(self, canvas_id: str) -> str:
        """
        Get the full file path for a canvas.

        Args:
            canvas_id: Canvas ID

        Returns:
            Full path to the canvas JSON file, or empty string if not found.
        """
        canvas = self.get_canvas(canvas_id)
        if not canvas:
            return ""

        scope = canvas.scope_enum
        canvas_dir = self._get_dir_for_scope(scope)
        return os.path.join(canvas_dir, canvas.filename)

    def get_canvas_scope(self, canvas_id: str) -> Optional[CanvasScope]:
        """
        Get the scope of a canvas by ID.

        Args:
            canvas_id: Canvas ID

        Returns:
            CanvasScope if found, None otherwise.
        """
        canvas = self.get_canvas(canvas_id)
        return canvas.scope_enum if canvas else None

    def get_presence_dir(self, canvas_id: str) -> str:
        """
        Get the presence directory for a canvas.

        Args:
            canvas_id: Canvas ID

        Returns:
            Full path to the presence directory for the canvas.
        """
        canvas = self.get_canvas(canvas_id)
        if not canvas:
            return ""

        scope = canvas.scope_enum
        canvas_dir = self._get_dir_for_scope(scope)
        return os.path.join(canvas_dir, "presence")

    def rename_canvas(self, canvas_id: str, new_name: str) -> bool:
        """
        Rename a canvas.

        Args:
            canvas_id: Canvas ID to rename
            new_name: New display name

        Returns:
            True if successful, False otherwise.
        """
        canvas = self.get_canvas(canvas_id)
        if not canvas:
            logger.error(f"Canvas not found for rename: {canvas_id}")
            return False

        scope = canvas.scope_enum
        index_data = self._load_index(scope)

        if canvas_id not in index_data.get("canvases", {}):
            return False

        # Update name in index (keep same filename)
        index_data["canvases"][canvas_id]["name"] = new_name
        index_data["canvases"][canvas_id]["modified"] = datetime.now().isoformat()
        index_data["canvases"][canvas_id]["modified_by"] = self._username

        if not self._save_index(scope, index_data):
            return False

        logger.info(f"Renamed canvas {canvas_id} to: {new_name}")
        return True

    def delete_canvas(self, canvas_id: str) -> bool:
        """
        Delete a canvas.

        Args:
            canvas_id: Canvas ID to delete

        Returns:
            True if successful, False otherwise.
        """
        canvas = self.get_canvas(canvas_id)
        if not canvas:
            logger.error(f"Canvas not found for delete: {canvas_id}")
            return False

        scope = canvas.scope_enum
        canvas_dir = self._get_dir_for_scope(scope)
        index_data = self._load_index(scope)

        # Check if this is the last canvas in scope
        if len(index_data.get("canvases", {})) <= 1:
            logger.warning(f"Cannot delete last canvas in {scope.value} scope")
            return False

        # Remove from index
        if canvas_id in index_data.get("canvases", {}):
            del index_data["canvases"][canvas_id]

        if not self._save_index(scope, index_data):
            return False

        # Delete the file
        canvas_path = os.path.join(canvas_dir, canvas.filename)
        try:
            if os.path.exists(canvas_path):
                os.remove(canvas_path)
        except Exception as e:
            logger.error(f"Failed to delete canvas file {canvas_path}: {e}")
            # Index is already updated, so continue

        logger.info(f"Deleted canvas: {canvas.name} ({canvas_id})")
        return True

    def duplicate_canvas(
        self, canvas_id: str, new_name: str, scope: Optional[CanvasScope] = None
    ) -> Optional[CanvasDef]:
        """
        Duplicate a canvas.

        Args:
            canvas_id: Canvas ID to duplicate
            new_name: Name for the new canvas
            scope: Optional scope for the duplicate. Defaults to same scope as original.

        Returns:
            CanvasDef for the new canvas, or None on error.
        """
        original = self.get_canvas(canvas_id)
        if not original:
            logger.error(f"Canvas not found for duplicate: {canvas_id}")
            return None

        # Default to same scope
        target_scope = scope or original.scope_enum

        # Create new canvas
        new_canvas = self.create_canvas(new_name, target_scope)
        if not new_canvas:
            return None

        # Copy content from original
        original_path = self.get_canvas_path(canvas_id)
        new_path = self.get_canvas_path(new_canvas.id)

        try:
            if os.path.exists(original_path):
                shutil.copy2(original_path, new_path)
        except Exception as e:
            logger.error(f"Failed to copy canvas content: {e}")
            # Canvas entry created, just content copy failed

        logger.info(f"Duplicated canvas {original.name} as {new_name}")
        return new_canvas

    def update_canvas_metadata(self, canvas_id: str, **kwargs) -> bool:
        """
        Update canvas metadata fields.

        Args:
            canvas_id: Canvas ID to update
            **kwargs: Fields to update (modified, modified_by, item_count)

        Returns:
            True if successful, False otherwise.
        """
        canvas = self.get_canvas(canvas_id)
        if not canvas:
            return False

        scope = canvas.scope_enum
        index_data = self._load_index(scope)

        if canvas_id not in index_data.get("canvases", {}):
            return False

        # Update allowed fields
        allowed_fields = {"modified", "modified_by", "item_count"}
        for key, value in kwargs.items():
            if key in allowed_fields:
                index_data["canvases"][canvas_id][key] = value

        return self._save_index(scope, index_data)

    def _ensure_migrated(self):
        """Migrate legacy single-canvas format to multi-canvas structure."""
        # Legacy path: {network_path}/{user}/_canvas/canvas_{jobname}.json
        # This was per-user, now we migrate to shared per-job

        old_user_canvas_dir = os.path.join(self._base_dir, self._username, "_canvas")
        old_canvas_file = os.path.join(old_user_canvas_dir, f"canvas_{self._jobname}.json")

        if not os.path.exists(old_canvas_file):
            return  # No legacy canvas for this user

        # Check if we already have canvases in the new location
        if self._job_index.exists:
            job_data = self._job_index.load()
            if job_data.get("canvases"):
                return  # Already have canvases, don't migrate

        logger.info(f"Migrating legacy canvas from {old_canvas_file}")

        # Create new structure
        ensure_directory(self.job_canvas_dir)

        # Copy legacy file (keep original for safety)
        canvas_id = str(uuid.uuid4())[:8]
        new_filename = f"canvas_{self._username}_migrated.json"
        new_path = os.path.join(self.job_canvas_dir, new_filename)

        try:
            shutil.copy2(old_canvas_file, new_path)
        except Exception as e:
            logger.error(f"Failed to copy legacy canvas: {e}")
            return

        # Create index entry
        now = datetime.now().isoformat()
        canvas_def = CanvasDef(
            id=canvas_id,
            name=f"Main ({self._username})",
            filename=new_filename,
            scope=CanvasScope.JOB.value,
            created=now,
            created_by=self._username,
            modified=now,
            modified_by=self._username,
            item_count=0,
        )

        index_data = {
            "version": self.INDEX_VERSION,
            "canvases": {canvas_id: canvas_def.to_dict()},
        }

        if self._job_index.save(index_data):
            logger.info(f"Migrated legacy canvas to: {canvas_id} ({new_filename})")
        else:
            logger.error("Failed to save migrated canvas index")
