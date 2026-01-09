"""
Settings tab module for Luma Tools.

Handles user settings (local) and global settings management.
"""

import os
import json
from PySide2 import QtWidgets, QtCore
from PySide2.QtCore import Qt
from PySide2.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

from .base_tab import BaseTab


def get_version():
    """Get the current version from version.json."""
    config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_dir = os.path.dirname(config_dir)
    version_file = os.path.join(root_dir, "version.json")

    if os.path.exists(version_file):
        try:
            with open(version_file, 'r') as f:
                data = json.load(f)
                return data.get("version", "0.1")
        except Exception:
            pass
    return "0.1"


def get_changelog():
    """Get the changelog content from changelog.md."""
    config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_dir = os.path.dirname(config_dir)
    changelog_file = os.path.join(root_dir, "changelog.md")

    if os.path.exists(changelog_file):
        try:
            with open(changelog_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            pass
    return "No changelog available."


class SettingsTab(BaseTab):
    """Tab for managing user and global settings."""

    @property
    def ui_file(self) -> str:
        return "settings.ui"

    @property
    def tab_name(self) -> str:
        return "Settings"

    @property
    def tab_id(self) -> str:
        return "settings"

    def connect_signals(self):
        """Connect settings tab signals."""
        # Version history button
        if hasattr(self.ui, 'showVersionHistoryButton'):
            self.ui.showVersionHistoryButton.clicked.connect(self._on_show_version_history)

        # User settings
        self.ui.AddPassButton.clicked.connect(self._on_add_pass_clicked)
        self.ui.RemovePassButton.clicked.connect(self._on_remove_pass_clicked)
        self.ui.ResetPassesButton.clicked.connect(self._on_reset_passes_clicked)
        self.ui.SaveSettingsButton.clicked.connect(self._on_save_settings_clicked)

        # Global settings
        self.ui.BrowseGlobalSettingsPath.clicked.connect(self._on_browse_global_settings_path)
        self.ui.BrowseComfyUIPath.clicked.connect(self._on_browse_comfyui_path)
        self.ui.BrowseComfyUIPython.clicked.connect(self._on_browse_comfyui_python)
        self.ui.BrowseComfyUINetworkOutput.clicked.connect(self._on_browse_comfyui_network_output)
        self.ui.ComfyUIModeCombo.currentIndexChanged.connect(self._on_comfyui_mode_changed)
        self.ui.SaveGlobalSettings.clicked.connect(self._on_save_global_settings)

        # Admin user management
        if hasattr(self.ui, 'AddAdminUserButton'):
            self.ui.AddAdminUserButton.clicked.connect(self._on_add_admin_user)
        if hasattr(self.ui, 'RemoveAdminUserButton'):
            self.ui.RemoveAdminUserButton.clicked.connect(self._on_remove_admin_user)

    def initialize(self):
        """Initialize settings tab."""
        self._load_version_ui()
        self._load_default_passes_ui()
        self._load_user_settings_ui()
        self._load_global_settings_ui()
        self._load_admin_users_ui()
        self._load_restricted_tabs_ui()

    def _load_version_ui(self):
        """Load version information into the UI."""
        version = get_version()
        if hasattr(self.ui, 'versionValueLabel'):
            self.ui.versionValueLabel.setText(version)

    def _on_show_version_history(self):
        """Show version history dialog."""
        changelog = get_changelog()

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Luma Tools - Version History")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setMarkdown(changelog)
        layout.addWidget(text_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.exec_()

    def _load_user_settings_ui(self):
        """Load user settings into the UI."""
        from settings_manager import get_tab_flashing_enabled

        # Load tab flashing setting
        if hasattr(self.ui, 'TabFlashingEnabled'):
            self.ui.TabFlashingEnabled.setChecked(get_tab_flashing_enabled())

    def _load_default_passes_ui(self):
        """Load default passes into the settings UI."""
        from settings_manager import get_default_passes
        from config import REQUIRED_PASSES, DEFAULT_PASSES

        self.ui.DefaultPassesList.clear()

        # Get user's current default passes (or system defaults)
        default_passes = get_default_passes()

        # Populate the list with all available passes
        all_available_passes = list(set(REQUIRED_PASSES + DEFAULT_PASSES + default_passes))

        for pass_name in sorted(all_available_passes):
            item = QtWidgets.QListWidgetItem(pass_name)

            # Mark required passes as disabled (can't be removed)
            if pass_name in REQUIRED_PASSES:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setToolTip("This pass is always included and cannot be removed")
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            else:
                item.setToolTip("Select to include this pass by default")

            self.ui.DefaultPassesList.addItem(item)

            # Select the item if it's in the user's default passes or is required
            if pass_name in default_passes or pass_name in REQUIRED_PASSES:
                item.setSelected(True)

        self.log(f"Loaded default passes UI with {len(all_available_passes)} passes")

    def _load_global_settings_ui(self):
        """Load global settings into the settings UI."""
        from settings_manager import (
            get_global_settings_path, get_comfyui_mode, get_comfyui_path,
            get_comfyui_python_path, get_comfyui_network_output_path,
            get_comfyui_fast_mode, get_comfyui_fp16_accumulation, get_comfyui_timeout
        )

        # Global settings path
        global_path = get_global_settings_path()
        self.ui.GlobalSettingsPathEdit.setText(global_path)
        self.ui.globalSettingsCurrentPath.setText(f"Current: {global_path}")

        # ComfyUI mode
        mode = get_comfyui_mode()
        mode_index = {"embedded": 0, "portable": 1, "standalone": 2}.get(mode, 0)
        self.ui.ComfyUIModeCombo.setCurrentIndex(mode_index)

        # ComfyUI paths
        self.ui.ComfyUIPathEdit.setText(get_comfyui_path())
        self.ui.ComfyUIPythonEdit.setText(get_comfyui_python_path())
        self.ui.ComfyUINetworkOutputEdit.setText(get_comfyui_network_output_path())

        # ComfyUI performance settings
        self.ui.ComfyUIFastMode.setChecked(get_comfyui_fast_mode())
        self.ui.ComfyUIFP16Accumulation.setChecked(get_comfyui_fp16_accumulation())

        # ComfyUI timeout setting
        if hasattr(self.ui, 'ComfyUITimeoutSpinBox'):
            timeout_seconds = get_comfyui_timeout()
            # Convert to minutes for UI display
            self.ui.ComfyUITimeoutSpinBox.setValue(timeout_seconds // 60)

        self._update_comfyui_python_visibility()

    def _load_admin_users_ui(self):
        """Load admin users list."""
        from settings_manager import get_admin_users

        self.ui.AdminUsersList.clear()
        for user in get_admin_users():
            self.ui.AdminUsersList.addItem(user)

    def _update_comfyui_python_visibility(self):
        """Show/hide Python path field based on selected mode."""
        is_standalone = self.ui.ComfyUIModeCombo.currentIndex() == 2
        self.ui.ComfyUIPythonEdit.setEnabled(is_standalone)
        self.ui.BrowseComfyUIPython.setEnabled(is_standalone)

    def _on_add_pass_clicked(self):
        """Add a custom pass to the default passes list."""
        pass_name, ok = QtWidgets.QInputDialog.getText(
            self.main_window, "Add Pass", "Enter pass name:",
            QtWidgets.QLineEdit.Normal
        )

        if ok and pass_name:
            pass_name = pass_name.strip()
            existing_items = self.ui.DefaultPassesList.findItems(pass_name, Qt.MatchExactly)
            if existing_items:
                self.log(f"Pass '{pass_name}' already exists in the list")
                return

            item = QtWidgets.QListWidgetItem(pass_name)
            item.setToolTip("Select to include this pass by default")
            item.setSelected(True)
            self.ui.DefaultPassesList.addItem(item)
            self.log(f"Added custom pass: {pass_name}")

    def _on_remove_pass_clicked(self):
        """Remove selected pass from the default passes list."""
        from config import REQUIRED_PASSES

        selected_items = self.ui.DefaultPassesList.selectedItems()
        if not selected_items:
            self.log("No passes selected for removal")
            return

        for item in selected_items:
            pass_name = item.text()
            if pass_name in REQUIRED_PASSES:
                self.log(f"Cannot remove required pass: {pass_name}")
                continue

            row = self.ui.DefaultPassesList.row(item)
            self.ui.DefaultPassesList.takeItem(row)
            self.log(f"Removed pass: {pass_name}")

    def _on_reset_passes_clicked(self):
        """Reset default passes to system defaults."""
        reply = QMessageBox.question(
            self.main_window, "Reset Default Passes",
            "Reset to default pass list?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            from config import DEFAULT_PASSES
            from settings_manager import set_default_passes
            set_default_passes(DEFAULT_PASSES.copy())
            self.log("Reset to default passes")
            self._load_default_passes_ui()

    def _on_save_settings_clicked(self):
        """Save user settings."""
        from config import REQUIRED_PASSES
        from settings_manager import set_default_passes, set_tab_flashing_enabled

        # Collect selected passes
        selected_passes = []
        for i in range(self.ui.DefaultPassesList.count()):
            item = self.ui.DefaultPassesList.item(i)
            pass_name = item.text()
            if pass_name in REQUIRED_PASSES:
                continue
            if item.isSelected():
                selected_passes.append(pass_name)

        set_default_passes(selected_passes)
        self.log(f"Saved default passes: {selected_passes}")

        # Save tab flashing setting
        if hasattr(self.ui, 'TabFlashingEnabled'):
            set_tab_flashing_enabled(self.ui.TabFlashingEnabled.isChecked())
            self.log(f"Saved tab flashing enabled: {self.ui.TabFlashingEnabled.isChecked()}")

        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.pulse_button(self.ui.SaveSettingsButton)
            self.main_window.animator.show_success("User settings saved")

    def _on_comfyui_mode_changed(self, index):
        """Handle ComfyUI mode combo change."""
        self._update_comfyui_python_visibility()

    def _on_browse_global_settings_path(self):
        """Browse for global settings directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Global Settings Directory",
            self.ui.GlobalSettingsPathEdit.text()
        )
        if directory:
            self.ui.GlobalSettingsPathEdit.setText(directory)

    def _on_browse_comfyui_path(self):
        """Browse for ComfyUI installation directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select ComfyUI Installation Directory",
            self.ui.ComfyUIPathEdit.text()
        )
        if directory:
            self.ui.ComfyUIPathEdit.setText(directory)

    def _on_browse_comfyui_python(self):
        """Browse for Python executable."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.main_window, "Select Python Executable",
            self.ui.ComfyUIPythonEdit.text(),
            "Executable (*.exe);;All Files (*)"
        )
        if file_path:
            self.ui.ComfyUIPythonEdit.setText(file_path)

    def _on_browse_comfyui_network_output(self):
        """Browse for ComfyUI network output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Network Output Directory",
            self.ui.ComfyUINetworkOutputEdit.text()
        )
        if directory:
            self.ui.ComfyUINetworkOutputEdit.setText(directory)

    def _on_save_global_settings(self):
        """Save all global settings."""
        from settings_manager import (
            set_global_settings_path, set_comfyui_mode, set_comfyui_path,
            set_comfyui_python_path, set_comfyui_network_output_path,
            set_comfyui_fast_mode, set_comfyui_fp16_accumulation,
            set_comfyui_timeout
        )

        # Save global settings path
        new_global_path = self.ui.GlobalSettingsPathEdit.text().strip()
        if new_global_path:
            if not os.path.exists(new_global_path):
                reply = QMessageBox.question(
                    self.main_window, "Create Directory",
                    f"The directory '{new_global_path}' does not exist. Create it?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    try:
                        os.makedirs(new_global_path)
                    except Exception as e:
                        if hasattr(self.main_window, 'animator'):
                            self.main_window.animator.show_error(f"Failed to create directory: {e}")
                        return
                else:
                    return

            set_global_settings_path(new_global_path)
            self.ui.globalSettingsCurrentPath.setText(f"Current: {new_global_path}")

        # Save ComfyUI settings
        mode_map = {0: "embedded", 1: "portable", 2: "standalone"}
        set_comfyui_mode(mode_map.get(self.ui.ComfyUIModeCombo.currentIndex(), "embedded"))
        set_comfyui_path(self.ui.ComfyUIPathEdit.text().strip())
        set_comfyui_python_path(self.ui.ComfyUIPythonEdit.text().strip())
        set_comfyui_network_output_path(self.ui.ComfyUINetworkOutputEdit.text().strip())
        set_comfyui_fast_mode(self.ui.ComfyUIFastMode.isChecked())
        set_comfyui_fp16_accumulation(self.ui.ComfyUIFP16Accumulation.isChecked())

        # Save ComfyUI timeout setting
        if hasattr(self.ui, 'ComfyUITimeoutSpinBox'):
            timeout_minutes = self.ui.ComfyUITimeoutSpinBox.value()
            set_comfyui_timeout(timeout_minutes * 60)  # Convert to seconds

        # Save restricted tabs configuration
        self._save_restricted_tabs_settings()

        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.show_success("Global settings saved")

    def _on_add_admin_user(self):
        """Add an admin user."""
        from settings_manager import add_admin_user

        username, ok = QtWidgets.QInputDialog.getText(
            self.main_window, "Add Admin User", "Enter username:",
            QtWidgets.QLineEdit.Normal
        )
        if ok and username:
            username = username.strip().lower()
            add_admin_user(username)
            self._load_admin_users_ui()
            self.log(f"Added admin user: {username}")

    def _on_remove_admin_user(self):
        """Remove selected admin user."""
        from settings_manager import remove_admin_user
        from PySide2.QtWidgets import QMessageBox

        selected_items = self.ui.AdminUsersList.selectedItems()
        if not selected_items:
            self.log("No admin user selected for removal")
            return

        username = selected_items[0].text()

        # Warn if removing self
        if username.lower() == self.app_state.user.lower():
            reply = QMessageBox.warning(
                self.main_window,
                "Remove Yourself?",
                "You are about to remove yourself from the admin list.\n"
                "You will lose access to admin features after restarting.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        remove_admin_user(username)
        self._load_admin_users_ui()
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.show_success(f"Removed admin user: {username}")

    # =========================================================================
    # RESTRICTED TABS
    # =========================================================================

    def _load_restricted_tabs_ui(self):
        """Load restricted tabs settings into the checkboxes."""
        from settings_manager import get_restricted_tabs

        restricted = get_restricted_tabs()

        # Map tab names to checkboxes
        checkbox_map = {
            "comfyui": getattr(self.ui, 'RestrictComfyUI', None),
            "comfyui_gallery": getattr(self.ui, 'RestrictComfyUIGallery', None),
            "settings": getattr(self.ui, 'RestrictSettings', None),
            "passbuilder": getattr(self.ui, 'RestrictPassBuilder', None),
            "mp4maker": getattr(self.ui, 'RestrictMP4Maker', None),
            "republish": getattr(self.ui, 'RestrictRePublish', None),
            "shotcleaner": getattr(self.ui, 'RestrictShotCleaner', None),
        }

        for tab_name, checkbox in checkbox_map.items():
            if checkbox:
                checkbox.setChecked(tab_name in restricted)

        self.log(f"Loaded restricted tabs settings: {restricted}")

    def _save_restricted_tabs_settings(self):
        """Save restricted tabs settings from the checkboxes."""
        from settings_manager import set_restricted_tabs

        restricted = []

        # Map checkboxes to tab names
        checkbox_map = {
            "comfyui": getattr(self.ui, 'RestrictComfyUI', None),
            "comfyui_gallery": getattr(self.ui, 'RestrictComfyUIGallery', None),
            "settings": getattr(self.ui, 'RestrictSettings', None),
            "passbuilder": getattr(self.ui, 'RestrictPassBuilder', None),
            "mp4maker": getattr(self.ui, 'RestrictMP4Maker', None),
            "republish": getattr(self.ui, 'RestrictRePublish', None),
            "shotcleaner": getattr(self.ui, 'RestrictShotCleaner', None),
        }

        for tab_name, checkbox in checkbox_map.items():
            if checkbox and checkbox.isChecked():
                restricted.append(tab_name)

        set_restricted_tabs(restricted)
