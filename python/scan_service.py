import os
from utils import get_trailing_number, remove_after, get_folder_size
from file_operations import (
    fast_scandir,
    find_renders,
    find_hip_files,
    find_comp_files,
    read_comp_file,
    get_lookdev_directory,
    get_comp_directory
)


class DirectoryScanner:
    """Handles directory scanning and file discovery operations."""

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

    def scan_all(self, progress_callback=None):
        """
        Run a complete scan of all directories.

        Args:
            progress_callback: Optional callback function(progress, message)
        """
        self._update_progress(0, "Scanning Directories", "Initializing scan...")

        # Get lookdev directory
        self.state.lookdev_dir = get_lookdev_directory(self.state.shotpath)
        print(f"lookdev Dir: {self.state.lookdev_dir}")

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
        try:
            dirs = fast_scandir(self.state.lookdev_dir)
        except:
            dirs = ()
            print("No Renders Found")

        render_folders = []
        render_directory = ""

        if len(dirs) > 0:
            for i in dirs:
                if r"lookdev\img\renders" in i:
                    render_folders.append(i)

            try:
                render_directory = render_folders[0]
                render_directory = remove_after(render_directory, r"lookdev\img\renders")
                self.ui.Renderlabel.setText(f'Render Directory Found: {render_directory}')
            except:
                self.ui.RendersList.setEnabled(False)
                print("No Renders Found!")
        else:
            self.ui.Renderlabel.setText('Render Directory Not Found!')
            self.ui.CleanRender.setEnabled(False)
            self.ui.CleanRender.setChecked(False)

        return render_directory

    def scan_usd_directory(self):
        """
        Scan for USD directory.

        Returns:
            str: Path to USD directory, or empty string if not found
        """
        try:
            dirs = fast_scandir(self.state.lookdev_dir)
        except:
            dirs = ()

        usd_folders = []
        usd_directory = ""

        if len(dirs) > 0:
            for i in dirs:
                if r"lookdev\usd_files" in i:
                    usd_folders.append(i)

            try:
                usd_directory = usd_folders[0]
                usd_directory = remove_after(usd_directory, r"lookdev\usd_files")
                self.ui.USDlabel.setText(f'USD Directory Found: {usd_directory}')
            except:
                usd_directory = ""
                print("No USDs Found!")
        else:
            usd_directory = ""
            self.ui.USDlabel.setText('USD Directory Not Found!')
            self.ui.CleanUSD.setEnabled(False)
            self.ui.CleanUSD.setChecked(False)

        return usd_directory

    def scan_hip_files(self):
        """
        Scan for Houdini HIP files.

        Returns:
            str: Base name of HIP file (without version), or empty string if not found
        """
        hipfiles = find_hip_files(self.state.lookdev_dir)
        hipcount = len(hipfiles)
        self.ui.HipNumber.setText(f'Amount of Hipfiles: {hipcount}')

        hip_file = ""
        if hipcount > 0:
            sorted(hipfiles)
            hip_file = hipfiles[0]
            temp = hip_file.rsplit("_", 1)
            hip_file = temp[0]
            self.ui.HIPlabel.setText(f'HIP Found: {hip_file}')
        else:
            self.ui.HIPlabel.setText('HIPS Not Found!')

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
            self.state.working_dir = remove_after(render_directory, "lookdev")
            renderdir = sorted(next(os.walk(render_directory))[1])

            if len(renderdir) < 2:
                self.ui.LatestRender.setText("Latest Render: None")

            for dir_name in renderdir:
                if hip_file in dir_name:
                    found_render_files.append(dir_name)
                    self.ui.RendersClean.addItem(str(dir_name))
                    self.ui.RendersClean.scrollToBottom()

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
                    self.ui.LatestRender.setText(f"Latest Render: {self.state.latestrender}")
                    latestver = get_trailing_number(self.state.latestrender)
                    self.ui.CurrentVer.setRange(0, int(latestver))
                else:
                    # No versions have renders - fall back to latest version
                    self.state.latestrender = found_render_files[-1]
                    found_render_files.pop(-1)
                    self.ui.LatestRender.setText(f"Latest Render: {self.state.latestrender} (empty)")
                    latestver = get_trailing_number(self.state.latestrender)
                    self.ui.CurrentVer.setRange(0, int(latestver))

            # Set render path
            if self.state.latestrender:
                self.state.searchpath = render_directory + "\\" + self.state.latestrender
                self.ui.RenderPath.setText(self.state.searchpath)
                currentver = get_trailing_number(self.state.latestrender)
                self.ui.CurrentVer.setValue(int(currentver))

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
                self.ui.USDSClean.addItem(str(dir_name))
                self.ui.USDSClean.scrollToBottom()

            if len(found_usd_files) > 0:
                latest_usd = found_usd_files[-1]
                found_usd_files.pop(-1)
                self.ui.LatestUSD.setText(f"Latest USD: {latest_usd}")
                self.ui.USDSClean.scrollToBottom()
                self.ui.CleanFiles.setEnabled(True)
            else:
                self.ui.LatestUSD.setText("Latest USD: None")

    def calculate_folder_size(self):
        """Calculate and display total folder size."""
        try:
            total_size = get_folder_size(self.state.lookdev_dir)
            self.ui.FolderSize.setText(f"Total Size: {str(total_size)}")
        except:
            self.ui.FolderSize.setText('Error calculating Size')
            self.ui.StatusLabel.setText('Error calculating Size')

    def scan_comp_files(self, hip_file):
        """
        Scan for comp files and deselect renders in use.

        Args:
            hip_file: Base name of HIP file
        """
        comp_dir = get_comp_directory(self.state.shotpath)

        try:
            dirs = fast_scandir(comp_dir)
        except:
            dirs = ()

        comp_folders = []

        if len(dirs) > 0:
            for i in dirs:
                if r"Compositing" in i:
                    comp_folders.append(i)

            try:
                comp_directory = comp_folders[0]
                comp_directory = remove_after(comp_directory, r"\Compositing" + "\\")
                comps = sorted(find_comp_files(comp_directory))
                latestcomp = comps[-1]
                self.ui.Complabel.setText(f'Latest Comp Found: {comp_directory + latestcomp}')

                # Read comp file and deselect renders in use
                renders_in_comp = read_comp_file(comp_directory + latestcomp, hip_file)
                self._deselect_renders_in_comp(renders_in_comp)
            except:
                print("No Comp Dir Found!")
        else:
            self.ui.Complabel.setText('Comp Directory Not Found!')

    def initialize_mp4_maker(self, render_directory):
        """
        Initialize MP4 Maker tab with render path.

        Args:
            render_directory: Path to render directory
        """
        if render_directory != "" and self.state.latestrender:
            searchpath = render_directory + "\\" + self.state.latestrender
            self.ui.MP4RenderPath.setText(searchpath)
            currentver = get_trailing_number(self.state.latestrender)
            self.ui.MP4CurrentVer.setValue(int(currentver))
            self.ui.MP4CurrentVer.setRange(0, int(currentver))

    def initialize_republish(self, render_directory):
        """
        Initialize rePublish tab with render path.

        Args:
            render_directory: Path to render directory
        """
        if render_directory != "" and self.state.latestrender:
            searchpath = render_directory + "\\" + self.state.latestrender
            self.state.republish_searchpath = searchpath
            self.ui.RePublishRenderPath.setText(searchpath)
            currentver = get_trailing_number(self.state.latestrender)
            self.ui.RePublishCurrentVer.setValue(int(currentver))
            self.ui.RePublishCurrentVer.setRange(0, int(currentver))

            # Set default task to the current task from command line args
            from PySide2.QtCore import Qt
            task_index = self.ui.RePublishTask.findText(self.state.task, Qt.MatchFixedString)
            if task_index >= 0:
                self.ui.RePublishTask.setCurrentIndex(task_index)
            else:
                # If task not found in dropdown, add it and select it
                self.ui.RePublishTask.addItem(self.state.task)
                self.ui.RePublishTask.setCurrentText(self.state.task)

    def _deselect_renders_in_comp(self, renders_in_comp):
        """
        Deselect renders that are in use by comp files.

        Args:
            renders_in_comp: List of render names used in comp
        """
        from PySide2.QtCore import Qt
        self.ui.RendersClean.selectAll()
        self.ui.USDSClean.selectAll()

        if renders_in_comp:
            for render_name in renders_in_comp:
                matching_items = self.ui.RendersClean.findItems(render_name, Qt.MatchContains)
                for item in matching_items:
                    item.setSelected(False)

    def _update_progress(self, progress, main_text, sub_text=""):
        """
        Update progress through animator.

        Args:
            progress: Progress percentage (0-100)
            main_text: Main status text
            sub_text: Sub-status text
        """
        if self.animator:
            if progress == 0:
                self.animator.show_loading(main_text, sub_text, show_progress=True)
            else:
                self.animator.update_loading_message(main_text, sub_text)
                self.animator.update_loading_progress(progress)
