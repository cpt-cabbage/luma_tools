"""
State Manager - Centralized application state.

This module centralizes all global state that was previously scattered
across luma_tools.py, providing a clean interface for state management.
"""


class ApplicationState:
    """Central state management for the application."""

    def __init__(self):
        """Initialize application state."""
        # Command line arguments
        self.jobname = ""
        self.shot = ""
        self.task = ""
        self.shotpath = ""
        self.user = ""
        self.output_subdirectory = ""

        # Pass Builder state
        self.renders = []
        self.channels = {}
        self.working_dir = ""
        self.currentrender = ""
        self.passesfile = ""
        self.lookdev_dir = ""
        self.latestrender = ""
        self.searchpath = ""
        self.startframe = 0
        self.endframe = 0

        # MP4 Maker state
        self.mp4_renders = []
        self.mp4_searchpath = ""
        self.mp4_custom_path = ""
        self.mp4_startframe = 0
        self.mp4_endframe = 0
        self.mp4_output_path = ""

        # rePublish state
        self.republish_renders = []
        self.republish_searchpath = ""
        self.republish_custom_path = ""
        self.republish_startframe = 0
        self.republish_endframe = 0
        self.republish_selected_render = None

    def initialize_from_args(self, args):
        """
        Initialize state from command line arguments.

        Args:
            args: List of command line arguments (sys.argv)
        """
        if len(args) >= 7:
            self.jobname = args[1]
            self.shot = args[2]
            self.task = args[3]
            self.shotpath = args[4]
            self.user = args[5]
            self.output_subdirectory = args[6]

            print("Full command: " + str(args))
            print(f"jobname = {self.jobname}")
            print(f"shot = {self.shot}")
            print(f"task = {self.task}")
            print(f"shotpath = {self.shotpath}")
            print(f"user = {self.user}")
            print(f"output_subdirectory = {self.output_subdirectory}")


# Global application state instance
app_state = ApplicationState()
