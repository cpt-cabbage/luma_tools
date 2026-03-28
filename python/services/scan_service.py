import logging
import os
from PySide6.QtCore import QObject, Signal
from core.utils import get_trailing_number, truncate_at_suffix, get_folder_size

logger = logging.getLogger(__name__)
from services.file_operations import (
    fast_scandir,
    find_renders,
    find_hip_files,
    find_comp_files,
    read_comp_file,
    get_lookdev_directory,
    get_comp_directory
)


class DirectoryScannerSignals(QObject):
    """
    Qt signals for thread-safe communication from scanner to GUI.

    All GUI updates from the scanner worker thread must go through these signals
    to ensure thread safety. Signals are automatically queued and executed on the
    main GUI thread.
    """
    # Widget text updates: (widget_name, text)
    set_label_text = Signal(str, str)

    # List widget operations: (list_name, item_text)
    add_list_item = Signal(str, str)
    clear_list = Signal(str)
    scroll_list_to_bottom = Signal(str)
    select_all_items = Signal(str)
    deselect_items_matching = Signal(str, str)  # (list_name, text_to_match)

    # Widget enable/disable: (widget_name, enabled)
    set_widget_enabled = Signal(str, bool)

    # Widget checked state: (widget_name, checked)
    set_widget_checked = Signal(str, bool)

    # Spin box range/value: (widget_name, min, max, value)
    set_spinbox_range = Signal(str, int, int)
    set_spinbox_value = Signal(str, int)

    # Combo box selection: (widget_name, text)
    set_combobox_text = Signal(str, str)


class DirectoryScanner:
    """
    Handles directory scanning and file discovery operations.

    Thread-safe: Uses Qt signals for all GUI updates to ensure safe
    cross-thread communication.
    """

    def __init__(self, state, ui, animator):
        """
        Initialize scanner with application state and UI references.

        Args:
            state: ApplicationState instance
            ui: UI widget instance
            animator: UI animator instance
        """
        self.state = state
        self.ui = ui
        self.animator = animator
        self.signals = DirectoryScannerSignals()

    def scan_all(self, progress_callback=None):
        """
        Run a complete scan of all directories.

        Args:
            progress_callback: Optional callback function(progress, message)
        """
        self._update_progress(0, "Scanning Directories", "Initializing scan...")

        # Get task directory (e.g., lighting, lookdev)
        self.state.lookdev_dir = get_lookdev_directory(self.state.shotpath, self.state.task)
        logger.info(f"Task Dir: {self.state.lookdev_dir}")

        # Scan render directory
        self._update_progress(10, "Scanning Render Files", "Searching for render directories...")
        render_directory = self.scan_render_directory()

        # Scan USD directory
        self._update_progress(25, "Scanning USD Files", "Searching for USD directories...")
        usd_directory = self.scan_usd_directory()

        # Scan HIP files
        self._update_progress(34, "Scanning HIP Files", "Searching for Houdini project files...")
        hip_file = self.scan_hip_files()

        # Process render files
        self._update_progress(50, "Processing Render Files", "Organizing render versions...")
        found_render_files = self.process_render_files(render_directory, hip_file)

        # Process USD files
        self._update_progress(66, "Processing USD Files", "Organizing USD versions...")
        self.process_usd_files(usd_directory)

        # Calculate folder size
        self._update_progress(75, "Calculating Size", "Computing total directory size...")
        self.calculate_folder_size()

        # Find comp files
        self._update_progress(85, "Scanning Comp Files", "Searching for composition files...")
        self.scan_comp_files(hip_file)

        # Initialize MP4 Maker tab
        self._update_progress(95, "Initializing MP4 Maker", "Setting up MP4 Maker tab...")
        self.initialize_mp4_maker(render_directory)

        # Initialize rePublish tab
        self._update_progress(97, "Initializing rePublish", "Setting up rePublish tab...")
        self.initialize_republish(render_directory)

        # Final progress
        self._update_progress(100, "Scan Complete", "Initialization complete!")

        return True

    def scan_render_directory(self):
        """
        Scan for render directory.

        Returns:
            str: Path to render directory, or empty string if not found
        """
        from core.config import RENDERS_SUBPATH

        try:
            dirs = fast_scandir(self.state.lookdev_dir)
        except Exception as e:
            dirs = ()
            logger.warning(f"No Renders Found: {e}")

        render_folders = []
        render_directory = ""

        if len(dirs) > 0:
            for i in dirs:
                if RENDERS_SUBPATH in i:
                    render_folders.append(i)

            try:
                render_directory = render_folders[0]
                render_directory = truncate_at_suffix(render_directory, RENDERS_SUBPATH)
                self.signals.set_label_text.emit('Renderlabel', f'Render Directory Found: {render_directory}')
            except (IndexError, Exception) as e:
                self.signals.set_widget_enabled.emit('RendersList', False)
                logger.warning(f"No Renders Found: {e}")
        else:
            self.signals.set_label_text.emit('Renderlabel', 'Render Directory Not Found!')
            self.signals.set_widget_enabled.emit('CleanRender', False)
            self.signals.set_widget_checked.emit('CleanRender', False)

        return render_directory

    def scan_usd_directory(self):
        """
        Scan for USD directory.

        Returns:
            str: Path to USD directory, or empty string if not found
        """
        from core.config import USD_SUBPATH

        try:
            dirs = fast_scandir(self.state.lookdev_dir)
        except Exception as e:
            logger.error(f"Error scanning directory: {e}")
            dirs = ()

        usd_folders = []
        usd_directory = ""

        if len(dirs) > 0:
            for i in dirs:
                if USD_SUBPATH in i:
                    usd_folders.append(i)

            try:
                usd_directory = usd_folders[0]
                usd_directory = truncate_at_suffix(usd_directory, USD_SUBPATH)
                self.signals.set_label_text.emit('USDlabel', f'USD Directory Found: {usd_directory}')
            except (IndexError, Exception) as e:
                usd_directory = ""
                logger.warning(f"No USDs Found: {e}")
        else:
            usd_directory = ""
            self.signals.set_label_text.emit('USDlabel', 'USD Directory Not Found!')
            self.signals.set_widget_enabled.emit('CleanUSD', False)
            self.signals.set_widget_checked.emit('CleanUSD', False)

        return usd_directory

    def scan_hip_files(self):
        """
        Scan for Houdini HIP files.

        Returns:
            str: Base name of HIP file (without version), or empty string if not found
        """
        hipfiles = find_hip_files(self.state.lookdev_dir, self.state.task)
        hipcount = len(hipfiles)
        self.signals.set_label_text.emit('HipNumber', f'Amount of Hipfiles: {hipcount}')

        hip_file = ""
        if hipcount > 0:
            hipfiles = sorted(hipfiles)
            hip_file = hipfiles[0]
            temp = hip_file.rsplit("_", 1)
            hip_file = temp[0]
            self.signals.set_label_text.emit('HIPlabel', f'HIP Found: {hip_file}')
        else:
            self.signals.set_label_text.emit('HIPlabel', 'HIPS Not Found!')

        return hip_file

    def process_render_files(self, render_directory, hip_file):
        """
        Process render files and find latest version.

        Args:
            render_directory: Path to render directory
            hip_file: Base name of HIP file

        Returns:
            list: List of found render files
        """
        found_render_files = []
        self.state.working_dir = ""

        if render_directory != "":
            self.state.working_dir = truncate_at_suffix(render_directory, self.state.task or "lookdev")
            renderdir = sorted(next(os.walk(render_directory))[1])

            if len(renderdir) < 2:
                self.signals.set_label_text.emit('LatestRender', "Latest Render: None")

            for dir_name in renderdir:
                if hip_file in dir_name:
                    found_render_files.append(dir_name)
                    self.signals.add_list_item.emit('RendersClean', str(dir_name))
                    self.signals.scroll_list_to_bottom.emit('RendersClean')

            if found_render_files:
                # Find the latest version that has renders (not empty)
                self.state.latestrender = None
                for render_version in reversed(found_render_files):
                    # Check if this version has renders in the denoised folder
                    version_path = os.path.join(render_directory, render_version)
                    test_renders = find_renders(version_path)
                    if len(test_renders) > 0:
                        self.state.latestrender = render_version
                        break

                # If we found a version with renders, use it
                if self.state.latestrender:
                    found_render_files.remove(self.state.latestrender)
                    self.signals.set_label_text.emit('LatestRender', f"Latest Render: {self.state.latestrender}")
                    latestver = get_trailing_number(self.state.latestrender)
                    self.signals.set_spinbox_range.emit('CurrentVer', 0, int(latestver))
                else:
                    # No versions have renders - fall back to latest version
                    self.state.latestrender = found_render_files[-1]
                    found_render_files.pop(-1)
                    self.signals.set_label_text.emit('LatestRender', f"Latest Render: {self.state.latestrender} (empty)")
                    latestver = get_trailing_number(self.state.latestrender)
                    self.signals.set_spinbox_range.emit('CurrentVer', 0, int(latestver))

            # Set render path
            if self.state.latestrender:
                self.state.searchpath = os.path.join(render_directory, self.state.latestrender)
                self.signals.set_label_text.emit('RenderPath', self.state.searchpath)
                currentver = get_trailing_number(self.state.latestrender)
                self.signals.set_spinbox_value.emit('CurrentVer', int(currentver))

        return found_render_files

    def process_usd_files(self, usd_directory):
        """
        Process USD files and find latest version.

        Args:
            usd_directory: Path to USD directory
        """
        found_usd_files = []
        if usd_directory:
            usddir = sorted(next(os.walk(usd_directory))[1])

            for dir_name in usddir:
                found_usd_files.append(dir_name)
                self.signals.add_list_item.emit('USDSClean', str(dir_name))
                self.signals.scroll_list_to_bottom.emit('USDSClean')

            if len(found_usd_files) > 0:
                latest_usd = found_usd_files[-1]
                found_usd_files.pop(-1)
                self.signals.set_label_text.emit('LatestUSD', f"Latest USD: {latest_usd}")
                self.signals.scroll_list_to_bottom.emit('USDSClean')
                self.signals.set_widget_enabled.emit('CleanFiles', True)
            else:
                self.signals.set_label_text.emit('LatestUSD', "Latest USD: None")

    def calculate_folder_size(self):
        """Calculate and display total folder size."""
        try:
            total_size = get_folder_size(self.state.lookdev_dir)
            self.signals.set_label_text.emit('FolderSize', f"Total Size: {str(total_size)}")
        except Exception as e:
            self.signals.set_label_text.emit('FolderSize', f'Error calculating Size: {e}')
            self.signals.set_label_text.emit('StatusLabel', f'Error calculating Size: {e}')

    def scan_comp_files(self, hip_file):
        """
        Scan for comp files and deselect renders in use.

        Args:
            hip_file: Base name of HIP file
        """
        comp_dir = get_comp_directory(self.state.shotpath)

        try:
            dirs = fast_scandir(comp_dir)
        except Exception as e:
            logger.error(f"Error scanning comp directory: {e}")
            dirs = ()

        comp_folders = []

        if len(dirs) > 0:
            for i in dirs:
                if r"Compositing" in i:
                    comp_folders.append(i)

            try:
                comp_directory = comp_folders[0]
                comp_directory = truncate_at_suffix(comp_directory, r"\Compositing" + "\\")
                comps = sorted(find_comp_files(comp_directory))
                latestcomp = comps[-1]
                self.signals.set_label_text.emit('Complabel', f'Latest Comp Found: {comp_directory + latestcomp}')

                # Read comp file and deselect renders in use
                renders_in_comp = read_comp_file(comp_directory + latestcomp, hip_file)
                self._deselect_renders_in_comp(renders_in_comp)
            except Exception as e:
                logger.warning(f"No Comp Dir Found: {e}")
        else:
            self.signals.set_label_text.emit('Complabel', 'Comp Directory Not Found!')

    def initialize_mp4_maker(self, render_directory):
        """
        Initialize MP4 Maker tab with render path.

        Args:
            render_directory: Path to render directory
        """
        if render_directory != "" and self.state.latestrender:
            searchpath = os.path.join(render_directory, self.state.latestrender)
            self.signals.set_label_text.emit('MP4RenderPath', searchpath)
            currentver = get_trailing_number(self.state.latestrender)
            self.signals.set_spinbox_value.emit('MP4CurrentVer', int(currentver))
            self.signals.set_spinbox_range.emit('MP4CurrentVer', 0, int(currentver))

    def initialize_republish(self, render_directory):
        """
        Initialize rePublish tab with render path.

        Args:
            render_directory: Path to render directory
        """
        if render_directory != "" and self.state.latestrender:
            searchpath = os.path.join(render_directory, self.state.latestrender)
            self.state.republish_searchpath = searchpath
            self.signals.set_label_text.emit('RePublishRenderPath', searchpath)
            currentver = get_trailing_number(self.state.latestrender)
            self.signals.set_spinbox_value.emit('RePublishCurrentVer', int(currentver))
            self.signals.set_spinbox_range.emit('RePublishCurrentVer', 0, int(currentver))

            # Set default task to the current task from command line args
            self.signals.set_combobox_text.emit('RePublishTask', self.state.task)

    def _deselect_renders_in_comp(self, renders_in_comp):
        """
        Deselect renders that are in use by comp files.

        Args:
            renders_in_comp: List of render names used in comp
        """
        self.signals.select_all_items.emit('RendersClean')
        self.signals.select_all_items.emit('USDSClean')

        if renders_in_comp:
            for render_name in renders_in_comp:
                self.signals.deselect_items_matching.emit('RendersClean', render_name)

    def _update_progress(self, progress, main_text, sub_text=""):
        """
        Update progress through animator.

        Args:
            progress: Progress percentage (0-100)
            main_text: Main status text
            sub_text: Sub-status text
        """
        # Progress updates handled via status bar (no overlay)
        if self.animator:
            if hasattr(self.animator, 'update_loading_message'):
                self.animator.update_loading_message(main_text, sub_text)
            if hasattr(self.animator, 'update_loading_progress'):
                self.animator.update_loading_progress(progress)
