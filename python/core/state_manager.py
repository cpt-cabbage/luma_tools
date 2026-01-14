"""
State management for Luma Tools application.

Provides thread-safe global state using a descriptor pattern for property access.
All state access is protected by a reentrant lock to prevent race conditions
when accessed from worker threads and the GUI thread.
"""

import threading


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

            print("Full command: " + str(args))
            print(f"jobname = {self.jobname}")
            print(f"shot = {self.shot}")
            print(f"task = {self.task}")
            print(f"shotpath = {self.shotpath}")
            print(f"user = {self.user}")
            print(f"output_subdirectory = {self.output_subdirectory}")
        else:
            # Standalone mode - no shot context
            self.standalone_mode = True
            import os
            self.user = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
            print("=" * 50)
            print("STANDALONE MODE - No shot context provided")
            print(f"user = {self.user}")
            print("=" * 50)


# Global application state instance
app_state = ApplicationState()


def get_app_state():
    """
    Get the global application state instance.

    Returns:
        ApplicationState: The global state instance
    """
    return app_state
