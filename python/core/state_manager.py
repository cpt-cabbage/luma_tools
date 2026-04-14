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
            try:
                value = getattr(obj, self._attr)
                # Return copies of mutable types to prevent lock-free mutation
                if isinstance(value, (list, dict, set)):
                    return type(value)(value)
                return value
            except AttributeError:
                # Attribute not yet set — return default
                if isinstance(self._default, (list, dict, set)):
                    return type(self._default)(self._default)
                return self._default

    def __set__(self, obj, value):
        with obj._lock:
            setattr(obj, self._attr, value)


class _UserProperty(ThreadSafeProperty):
    """ThreadSafeProperty that invalidates role caches when user changes."""

    def __set__(self, obj, value):
        with obj._lock:
            setattr(obj, self._attr, value)
            # Invalidate cached role status so it's re-evaluated for the new user
            obj._is_admin = None


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
    user = _UserProperty('user', '')
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

    # Standalone mode (running outside AYON context)
    standalone_mode = ThreadSafeProperty('standalone_mode', False)

    def __init__(self):
        """Initialize application state with thread lock."""
        # Thread synchronization lock (reentrant for nested calls)
        self._lock = threading.RLock()

        # Role status (cached) - handled specially, not via descriptor
        self._is_admin = None

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
            # Return False if user not initialized yet
            user = getattr(self, '_user', '') or ''
            if not user:
                return False
            if self._is_admin is None:
                try:
                    from core.settings_manager import is_user_in_role
                    self._is_admin = is_user_in_role(user, "admin")
                except Exception:
                    self._is_admin = False
            return self._is_admin

    @property
    def has_elevated_access(self):
        """
        Check if the current user has elevated access (admin).
        Thread-safe with caching.

        Returns:
            bool: True if current user is an admin
        """
        return self.is_admin

    def refresh_admin_status(self):
        """Force refresh of admin status (call after role list changes)."""
        with self._lock:
            self._is_admin = None

    def has_shot_context(self):
        """Check if shot context is available (job, shot, shotpath)."""
        with self._lock:
            return bool(
                getattr(self, '_jobname', '') and
                getattr(self, '_shot', '') and
                getattr(self, '_shotpath', '')
            )

    def has_ayon_context(self):
        """Check if AYON publish context is available (job + shotpath).

        Less restrictive than has_shot_context() — works for both shots and
        assets since AYON folder path is derived from shotpath + jobname only.
        """
        with self._lock:
            return bool(
                getattr(self, '_jobname', '') and
                getattr(self, '_shotpath', '')
            )

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
        # Hold lock for entire read-modify-write to prevent lost updates
        with self._lock:
            outputs = list(getattr(self, '_comfyui_recent_outputs', None) or [])
            # Add to front, remove duplicates
            if path in outputs:
                outputs.remove(path)
            outputs.insert(0, path)
            # Trim to max
            self._comfyui_recent_outputs = outputs[:max_count]

    def update_session_stats(self, outputs_added: int = 0, time_seconds: float = 0.0,
                             job_completed: bool = False) -> None:
        """
        Update session generation statistics.

        Args:
            outputs_added: Number of new outputs generated
            time_seconds: Time taken for the generation
            job_completed: Whether a job was completed
        """
        # Hold lock for entire read-modify-write to prevent lost updates
        with self._lock:
            stats = dict(getattr(self, '_comfyui_session_stats', None) or {
                'total_generated': 0,
                'total_time_seconds': 0.0,
                'jobs_completed': 0
            })
            stats['total_generated'] = stats.get('total_generated', 0) + outputs_added
            stats['total_time_seconds'] = stats.get('total_time_seconds', 0.0) + time_seconds
            if job_completed:
                stats['jobs_completed'] = stats.get('jobs_completed', 0) + 1
            self._comfyui_session_stats = stats

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
        # Hold lock for entire read-modify-write to prevent lost updates
        with self._lock:
            current = getattr(self, '_gallery_new_since_view', 0) or 0
            self._gallery_new_since_view = current + count

    def reset_gallery_new_count(self) -> None:
        """Reset the new items count (called when gallery becomes visible)."""
        # Use property accessor (not _attr) to go through descriptor
        self.gallery_new_since_view = 0

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
