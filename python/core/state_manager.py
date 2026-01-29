"""
State management for Luma Tools application.

Provides thread-safe global state using a descriptor pattern for property access.
All state access is protected by a reentrant lock to prevent race conditions
when accessed from worker threads and the GUI thread.
"""

import logging
import threading

logger = logging.getLogger(__name__)


class ThreadSafeProperty:
    """
    Descriptor for thread-safe property access.

    Automatically wraps get/set operations with the owner's _lock.
    Reduces boilerplate from 10 lines per property to 1 line.

    Usage:
        class MyClass:
            _lock = threading.RLock()
            my_property = ThreadSafeProperty('my_property', default='')
    """

    def __init__(self, name, default=None):
        """
        Initialize thread-safe property descriptor.

        Args:
            name: Property name (used for internal storage as _{name})
            default: Default value for the property
        """
        self._attr = f"_{name}"
        self._default = default

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        with obj._lock:
            return getattr(obj, self._attr, self._default)

    def __set__(self, obj, value):
        with obj._lock:
            setattr(obj, self._attr, value)


class ApplicationState:
    """
    Central state management for the application.

    Thread-safe: All state access is protected by a reentrant lock to prevent
    race conditions when accessed from worker threads and the GUI thread.
    """

    # Command line arguments
    jobname = ThreadSafeProperty('jobname', '')
    shot = ThreadSafeProperty('shot', '')
    task = ThreadSafeProperty('task', '')
    shotpath = ThreadSafeProperty('shotpath', '')
    user = ThreadSafeProperty('user', '')
    output_subdirectory = ThreadSafeProperty('output_subdirectory', '')

    # Pass Builder state
    renders = ThreadSafeProperty('renders', [])
    channels = ThreadSafeProperty('channels', {})
    working_dir = ThreadSafeProperty('working_dir', '')
    currentrender = ThreadSafeProperty('currentrender', '')
    passesfile = ThreadSafeProperty('passesfile', '')
    lookdev_dir = ThreadSafeProperty('lookdev_dir', '')
    latestrender = ThreadSafeProperty('latestrender', '')
    searchpath = ThreadSafeProperty('searchpath', '')
    startframe = ThreadSafeProperty('startframe', 0)
    endframe = ThreadSafeProperty('endframe', 0)

    # MP4 Maker state
    mp4_renders = ThreadSafeProperty('mp4_renders', [])
    mp4_searchpath = ThreadSafeProperty('mp4_searchpath', '')
    mp4_custom_path = ThreadSafeProperty('mp4_custom_path', '')
    mp4_startframe = ThreadSafeProperty('mp4_startframe', 0)
    mp4_endframe = ThreadSafeProperty('mp4_endframe', 0)
    mp4_output_path = ThreadSafeProperty('mp4_output_path', '')

    # rePublish state
    republish_renders = ThreadSafeProperty('republish_renders', [])
    republish_searchpath = ThreadSafeProperty('republish_searchpath', '')
    republish_custom_path = ThreadSafeProperty('republish_custom_path', '')
    republish_startframe = ThreadSafeProperty('republish_startframe', 0)
    republish_endframe = ThreadSafeProperty('republish_endframe', 0)
    republish_selected_render = ThreadSafeProperty('republish_selected_render', None)

    # ComfyUI state
    comfyui_workflow_path = ThreadSafeProperty('comfyui_workflow_path', '')
    comfyui_iterate_mode = ThreadSafeProperty('comfyui_iterate_mode', False)
    comfyui_current_job_id = ThreadSafeProperty('comfyui_current_job_id', '')
    comfyui_last_generated_image = ThreadSafeProperty('comfyui_last_generated_image', '')

    # Cross-tab awareness: Active job tracking
    # List of job_ids currently being tracked (for persistence/recovery)
    comfyui_active_job_ids = ThreadSafeProperty('comfyui_active_job_ids', [])
    # Total outputs expected across all active jobs
    comfyui_pending_output_count = ThreadSafeProperty('comfyui_pending_output_count', 0)
    # Recent output paths (last N for quick access in ComfyUI tab)
    comfyui_recent_outputs = ThreadSafeProperty('comfyui_recent_outputs', [])
    # Generation stats for the current session
    comfyui_session_stats = ThreadSafeProperty('comfyui_session_stats', {
        'total_generated': 0,
        'total_time_seconds': 0.0,
        'jobs_completed': 0
    })

    # Cross-tab awareness: Gallery state
    # Count of items added since user last viewed gallery
    gallery_new_since_view = ThreadSafeProperty('gallery_new_since_view', 0)
    # Currently selected paths in gallery
    gallery_selected_paths = ThreadSafeProperty('gallery_selected_paths', [])
    # Whether gallery tab is currently visible
    gallery_visible = ThreadSafeProperty('gallery_visible', False)

    # Cross-tab awareness: Workflow context
    # Most recent input images used (for suggestions)
    workflow_last_used_inputs = ThreadSafeProperty('workflow_last_used_inputs', [])
    # Recent generation history for smart defaults
    workflow_generation_history = ThreadSafeProperty('workflow_generation_history', [])

    # Standalone mode (running outside AYON context)
    standalone_mode = ThreadSafeProperty('standalone_mode', False)

    def __init__(self):
        """Initialize application state with thread lock."""
        # Thread synchronization lock (reentrant for nested calls)
        self._lock = threading.RLock()

        # Role status (cached) - handled specially, not via descriptor
        self._is_admin = None
        self._is_sup = None

    @property
    def is_admin(self):
        """
        Check if the current user is an admin.
        Admins have full access to all tabs including Settings.
        Thread-safe with caching to avoid repeated file reads.

        Returns:
            bool: True if current user is an admin
        """
        with self._lock:
            if self._is_admin is None:
                from core.settings_manager import is_admin_user
                self._is_admin = is_admin_user(self._user)
            return self._is_admin

    @property
    def is_sup(self):
        """
        Check if the current user is a supervisor.
        Supervisors can see ComfyUI and Gallery tabs (but not Settings).
        Thread-safe with caching to avoid repeated file reads.

        Returns:
            bool: True if current user is a supervisor
        """
        with self._lock:
            if self._is_sup is None:
                from core.settings_manager import is_sup_user
                self._is_sup = is_sup_user(self._user)
            return self._is_sup

    @property
    def has_elevated_access(self):
        """
        Check if the current user has any elevated access (admin or sup).
        Thread-safe with caching.

        Returns:
            bool: True if current user is an admin or supervisor
        """
        return self.is_admin or self.is_sup

    def refresh_admin_status(self):
        """Force refresh of admin and supervisor status (call after role list changes)."""
        with self._lock:
            self._is_admin = None
            self._is_sup = None

    def has_shot_context(self):
        """Check if shot context is available (job, shot, shotpath)."""
        with self._lock:
            return bool(self._jobname and self._shot and self._shotpath)

    # =========================================================================
    # Cross-Tab Awareness Helpers
    # =========================================================================

    def add_recent_output(self, path: str, max_count: int = 20) -> None:
        """
        Add a path to recent outputs list (for ComfyUI tab preview).

        Args:
            path: Path to the output file
            max_count: Maximum number of recent outputs to keep
        """
        # Use property accessor (not _attr) to go through descriptor
        outputs = list(self.comfyui_recent_outputs or [])
        # Add to front, remove duplicates
        if path in outputs:
            outputs.remove(path)
        outputs.insert(0, path)
        # Trim to max
        self.comfyui_recent_outputs = outputs[:max_count]

    def update_session_stats(self, outputs_added: int = 0, time_seconds: float = 0.0,
                             job_completed: bool = False) -> None:
        """
        Update session generation statistics.

        Args:
            outputs_added: Number of new outputs generated
            time_seconds: Time taken for the generation
            job_completed: Whether a job was completed
        """
        # Use property accessor (not _attr) to go through descriptor
        stats = dict(self.comfyui_session_stats or {
            'total_generated': 0,
            'total_time_seconds': 0.0,
            'jobs_completed': 0
        })
        stats['total_generated'] = stats.get('total_generated', 0) + outputs_added
        stats['total_time_seconds'] = stats.get('total_time_seconds', 0.0) + time_seconds
        if job_completed:
            stats['jobs_completed'] = stats.get('jobs_completed', 0) + 1
        self.comfyui_session_stats = stats

    def get_session_stats(self) -> dict:
        """Get session generation statistics."""
        # Use property accessor (not _attr) to go through descriptor
        return dict(self.comfyui_session_stats or {
            'total_generated': 0,
            'total_time_seconds': 0.0,
            'jobs_completed': 0
        })

    def increment_gallery_new_count(self, count: int = 1) -> None:
        """Increment the count of new items since gallery was last viewed."""
        # Use property accessor (not _attr) to go through descriptor
        current = self.gallery_new_since_view or 0
        self.gallery_new_since_view = current + count

    def reset_gallery_new_count(self) -> None:
        """Reset the new items count (called when gallery becomes visible)."""
        # Use property accessor (not _attr) to go through descriptor
        self.gallery_new_since_view = 0

    def add_to_generation_history(self, entry: dict, max_count: int = 50) -> None:
        """
        Add an entry to generation history for smart defaults.

        Args:
            entry: Dict with workflow_name, generation_count, seed, prompt, etc.
            max_count: Maximum history entries to keep
        """
        # Use property accessor (not _attr) to go through descriptor
        history = list(self.workflow_generation_history or [])
        history.insert(0, entry)
        self.workflow_generation_history = history[:max_count]

    def get_workflow_defaults(self, workflow_name: str) -> dict:
        """
        Get smart defaults for a workflow based on history.

        Args:
            workflow_name: Name of the workflow preset

        Returns:
            Dict with suggested defaults (generation_count, etc.)
        """
        # Use property accessor (not _attr) to go through descriptor
        history = self.workflow_generation_history or []
        # Find recent entries for this workflow
        workflow_entries = [
            e for e in history
            if e.get('workflow_name') == workflow_name
        ][:10]  # Last 10 uses

        if not workflow_entries:
            return {}

        # Calculate mode for generation count
        gen_counts = [e.get('generation_count', 5) for e in workflow_entries]
        if gen_counts:
            suggested_count = max(set(gen_counts), key=gen_counts.count)
        else:
            suggested_count = 5

        return {
            'generation_count': suggested_count,
            'uses': len(workflow_entries)
        }

    def initialize_from_args(self, args):
        """
        Initialize state from command line arguments.

        Args:
            args: List of command line arguments (sys.argv)

        If insufficient arguments are provided, enters standalone mode
        with current user from environment.
        """
        if len(args) >= 7:
            self.jobname = args[1]
            self.shot = args[2]
            self.task = args[3]
            self.shotpath = args[4]
            self.user = args[5]
            self.output_subdirectory = args[6]
            self.standalone_mode = False

            logger.info("Full command: " + str(args))
            logger.info(f"jobname = {self.jobname}")
            logger.info(f"shot = {self.shot}")
            logger.info(f"task = {self.task}")
            logger.info(f"shotpath = {self.shotpath}")
            logger.info(f"user = {self.user}")
            logger.info(f"output_subdirectory = {self.output_subdirectory}")
        else:
            # Standalone mode - no shot context
            self.standalone_mode = True
            import os
            self.user = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
            logger.info("=" * 50)
            logger.info("STANDALONE MODE - No shot context provided")
            logger.info(f"user = {self.user}")
            logger.info("=" * 50)


# Global application state instance
app_state = ApplicationState()


def get_app_state():
    """
    Get the global application state instance.

    Returns:
        ApplicationState: The global state instance
    """
    return app_state
