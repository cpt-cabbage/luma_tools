import threading


class ApplicationState:
    """
    Central state management for the application.

    Thread-safe: All state access is protected by a reentrant lock to prevent
    race conditions when accessed from worker threads and the GUI thread.
    """

    def __init__(self):
        """Initialize application state."""
        # Thread synchronization lock (reentrant for nested calls)
        self._lock = threading.RLock()

        # Command line arguments
        self._jobname = ""
        self._shot = ""
        self._task = ""
        self._shotpath = ""
        self._user = ""
        self._output_subdirectory = ""

        # Pass Builder state
        self._renders = []
        self._channels = {}
        self._working_dir = ""
        self._currentrender = ""
        self._passesfile = ""
        self._lookdev_dir = ""
        self._latestrender = ""
        self._searchpath = ""
        self._startframe = 0
        self._endframe = 0

        # MP4 Maker state
        self._mp4_renders = []
        self._mp4_searchpath = ""
        self._mp4_custom_path = ""
        self._mp4_startframe = 0
        self._mp4_endframe = 0
        self._mp4_output_path = ""

        # rePublish state
        self._republish_renders = []
        self._republish_searchpath = ""
        self._republish_custom_path = ""
        self._republish_startframe = 0
        self._republish_endframe = 0
        self._republish_selected_render = None

        # ComfyUI state
        self._comfyui_workflow_path = ""
        self._comfyui_iterate_mode = False
        self._comfyui_current_job_id = ""
        self._comfyui_last_generated_image = ""

        # Admin status (cached)
        self._is_admin = None

        # Standalone mode (running outside AYON context)
        self._standalone_mode = False

    # Thread-safe property accessors
    @property
    def jobname(self):
        with self._lock:
            return self._jobname

    @jobname.setter
    def jobname(self, value):
        with self._lock:
            self._jobname = value

    @property
    def shot(self):
        with self._lock:
            return self._shot

    @shot.setter
    def shot(self, value):
        with self._lock:
            self._shot = value

    @property
    def task(self):
        with self._lock:
            return self._task

    @task.setter
    def task(self, value):
        with self._lock:
            self._task = value

    @property
    def shotpath(self):
        with self._lock:
            return self._shotpath

    @shotpath.setter
    def shotpath(self, value):
        with self._lock:
            self._shotpath = value

    @property
    def user(self):
        with self._lock:
            return self._user

    @user.setter
    def user(self, value):
        with self._lock:
            self._user = value

    @property
    def output_subdirectory(self):
        with self._lock:
            return self._output_subdirectory

    @output_subdirectory.setter
    def output_subdirectory(self, value):
        with self._lock:
            self._output_subdirectory = value

    @property
    def renders(self):
        with self._lock:
            return self._renders

    @renders.setter
    def renders(self, value):
        with self._lock:
            self._renders = value

    @property
    def channels(self):
        with self._lock:
            return self._channels

    @channels.setter
    def channels(self, value):
        with self._lock:
            self._channels = value

    @property
    def working_dir(self):
        with self._lock:
            return self._working_dir

    @working_dir.setter
    def working_dir(self, value):
        with self._lock:
            self._working_dir = value

    @property
    def currentrender(self):
        with self._lock:
            return self._currentrender

    @currentrender.setter
    def currentrender(self, value):
        with self._lock:
            self._currentrender = value

    @property
    def passesfile(self):
        with self._lock:
            return self._passesfile

    @passesfile.setter
    def passesfile(self, value):
        with self._lock:
            self._passesfile = value

    @property
    def lookdev_dir(self):
        with self._lock:
            return self._lookdev_dir

    @lookdev_dir.setter
    def lookdev_dir(self, value):
        with self._lock:
            self._lookdev_dir = value

    @property
    def latestrender(self):
        with self._lock:
            return self._latestrender

    @latestrender.setter
    def latestrender(self, value):
        with self._lock:
            self._latestrender = value

    @property
    def searchpath(self):
        with self._lock:
            return self._searchpath

    @searchpath.setter
    def searchpath(self, value):
        with self._lock:
            self._searchpath = value

    @property
    def startframe(self):
        with self._lock:
            return self._startframe

    @startframe.setter
    def startframe(self, value):
        with self._lock:
            self._startframe = value

    @property
    def endframe(self):
        with self._lock:
            return self._endframe

    @endframe.setter
    def endframe(self, value):
        with self._lock:
            self._endframe = value

    @property
    def mp4_renders(self):
        with self._lock:
            return self._mp4_renders

    @mp4_renders.setter
    def mp4_renders(self, value):
        with self._lock:
            self._mp4_renders = value

    @property
    def mp4_searchpath(self):
        with self._lock:
            return self._mp4_searchpath

    @mp4_searchpath.setter
    def mp4_searchpath(self, value):
        with self._lock:
            self._mp4_searchpath = value

    @property
    def mp4_custom_path(self):
        with self._lock:
            return self._mp4_custom_path

    @mp4_custom_path.setter
    def mp4_custom_path(self, value):
        with self._lock:
            self._mp4_custom_path = value

    @property
    def mp4_startframe(self):
        with self._lock:
            return self._mp4_startframe

    @mp4_startframe.setter
    def mp4_startframe(self, value):
        with self._lock:
            self._mp4_startframe = value

    @property
    def mp4_endframe(self):
        with self._lock:
            return self._mp4_endframe

    @mp4_endframe.setter
    def mp4_endframe(self, value):
        with self._lock:
            self._mp4_endframe = value

    @property
    def mp4_output_path(self):
        with self._lock:
            return self._mp4_output_path

    @mp4_output_path.setter
    def mp4_output_path(self, value):
        with self._lock:
            self._mp4_output_path = value

    @property
    def republish_renders(self):
        with self._lock:
            return self._republish_renders

    @republish_renders.setter
    def republish_renders(self, value):
        with self._lock:
            self._republish_renders = value

    @property
    def republish_searchpath(self):
        with self._lock:
            return self._republish_searchpath

    @republish_searchpath.setter
    def republish_searchpath(self, value):
        with self._lock:
            self._republish_searchpath = value

    @property
    def republish_custom_path(self):
        with self._lock:
            return self._republish_custom_path

    @republish_custom_path.setter
    def republish_custom_path(self, value):
        with self._lock:
            self._republish_custom_path = value

    @property
    def republish_startframe(self):
        with self._lock:
            return self._republish_startframe

    @republish_startframe.setter
    def republish_startframe(self, value):
        with self._lock:
            self._republish_startframe = value

    @property
    def republish_endframe(self):
        with self._lock:
            return self._republish_endframe

    @republish_endframe.setter
    def republish_endframe(self, value):
        with self._lock:
            self._republish_endframe = value

    @property
    def republish_selected_render(self):
        with self._lock:
            return self._republish_selected_render

    @republish_selected_render.setter
    def republish_selected_render(self, value):
        with self._lock:
            self._republish_selected_render = value

    @property
    def comfyui_workflow_path(self):
        with self._lock:
            return self._comfyui_workflow_path

    @comfyui_workflow_path.setter
    def comfyui_workflow_path(self, value):
        with self._lock:
            self._comfyui_workflow_path = value

    @property
    def comfyui_iterate_mode(self):
        with self._lock:
            return self._comfyui_iterate_mode

    @comfyui_iterate_mode.setter
    def comfyui_iterate_mode(self, value):
        with self._lock:
            self._comfyui_iterate_mode = value

    @property
    def comfyui_current_job_id(self):
        with self._lock:
            return self._comfyui_current_job_id

    @comfyui_current_job_id.setter
    def comfyui_current_job_id(self, value):
        with self._lock:
            self._comfyui_current_job_id = value

    @property
    def comfyui_last_generated_image(self):
        with self._lock:
            return self._comfyui_last_generated_image

    @comfyui_last_generated_image.setter
    def comfyui_last_generated_image(self, value):
        with self._lock:
            self._comfyui_last_generated_image = value

    @property
    def is_admin(self):
        """
        Check if the current user is an admin.
        Thread-safe with caching to avoid repeated file reads.

        Returns:
            bool: True if current user is an admin
        """
        with self._lock:
            if self._is_admin is None:
                from settings_manager import is_admin_user
                self._is_admin = is_admin_user(self._user)
            return self._is_admin

    def refresh_admin_status(self):
        """Force refresh of admin status (call after admin list changes)."""
        with self._lock:
            self._is_admin = None

    @property
    def standalone_mode(self):
        """Check if running in standalone mode (without AYON context)."""
        with self._lock:
            return self._standalone_mode

    @standalone_mode.setter
    def standalone_mode(self, value):
        with self._lock:
            self._standalone_mode = value

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
