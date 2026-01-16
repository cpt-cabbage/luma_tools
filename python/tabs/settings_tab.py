"""
Settings tab module for Luma Tools.

Handles user settings (local) and global settings management.
"""

import os
import json
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

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

        # Feature request buttons
        if hasattr(self.ui, 'submitFeatureRequestButton'):
            self.ui.submitFeatureRequestButton.clicked.connect(self._on_submit_feature_request)

        if hasattr(self.ui, 'viewFeatureRequestsButton'):
            self.ui.viewFeatureRequestsButton.clicked.connect(self._on_view_feature_requests)

        # User settings
        self.ui.AddPassButton.clicked.connect(self._on_add_pass_clicked)
        self.ui.RemovePassButton.clicked.connect(self._on_remove_pass_clicked)
        self.ui.ResetPassesButton.clicked.connect(self._on_reset_passes_clicked)
        self.ui.SaveSettingsButton.clicked.connect(self._on_save_settings_clicked)

        # Regenerate thumbnails button
        if hasattr(self.ui, 'RegenerateThumbnailsButton'):
            self.ui.RegenerateThumbnailsButton.clicked.connect(self._on_regenerate_thumbnails)

        # Global settings
        self.ui.BrowseGlobalSettingsPath.clicked.connect(self._on_browse_global_settings_path)
        self.ui.BrowseComfyUIPath.clicked.connect(self._on_browse_comfyui_path)
        self.ui.BrowseComfyUIPython.clicked.connect(self._on_browse_comfyui_python)
        self.ui.BrowseComfyUINetworkOutput.clicked.connect(self._on_browse_comfyui_network_output)
        self.ui.ComfyUIModeButton.clicked.connect(self._on_comfyui_mode_button_clicked)
        self.ui.SaveGlobalSettings.clicked.connect(self._on_save_global_settings)

        # Admin user management
        if hasattr(self.ui, 'AddAdminUserButton'):
            self.ui.AddAdminUserButton.clicked.connect(self._on_add_admin_user)
        if hasattr(self.ui, 'RemoveAdminUserButton'):
            self.ui.RemoveAdminUserButton.clicked.connect(self._on_remove_admin_user)

        # Supervisor user management
        if hasattr(self.ui, 'AddSupUserButton'):
            self.ui.AddSupUserButton.clicked.connect(self._on_add_sup_user)
        if hasattr(self.ui, 'RemoveSupUserButton'):
            self.ui.RemoveSupUserButton.clicked.connect(self._on_remove_sup_user)

    def initialize(self):
        """Initialize settings tab."""
        # ComfyUI mode options
        self._comfyui_mode = "embedded"  # Default
        self._comfyui_mode_options = [
            ("Embedded (python_embeded)", "embedded"),
            ("Portable (venv)", "portable"),
            ("Standalone", "standalone"),
        ]

        # Check if user is supervisor (read-only access)
        is_supervisor = self.app_state.is_sup and not self.app_state.is_admin

        if is_supervisor:
            # Supervisors can only see the info section
            self._hide_settings_for_supervisor()

        self._load_version_ui()

        # Only load settings UI for admins
        if not is_supervisor:
            self._load_default_passes_ui()
            self._load_user_settings_ui()
            self._load_global_settings_ui()
            self._load_admin_users_ui()
            self._load_sup_users_ui()
            self._load_restricted_tabs_ui()

    def _hide_settings_for_supervisor(self):
        """Hide all settings sections except info for supervisor users."""
        # Hide user settings group box
        if hasattr(self.ui, 'userSettingsGroupBox'):
            self.ui.userSettingsGroupBox.hide()

        # Hide global settings group box
        if hasattr(self.ui, 'globalSettingsGroupBox'):
            self.ui.globalSettingsGroupBox.hide()

    def _load_version_ui(self):
        """Load version information into the UI."""
        version = get_version()
        if hasattr(self.ui, 'versionValueLabel'):
            self.ui.versionValueLabel.setText(version)

        # Check if this is a new version and show notification on button
        if hasattr(self.ui, 'showVersionHistoryButton'):
            from core.settings_manager import is_new_version
            if is_new_version(version):
                # Add notification indicator to button text
                current_text = self.ui.showVersionHistoryButton.text()
                if not current_text.endswith(" •"):
                    self.ui.showVersionHistoryButton.setText(f"{current_text} •")
                # Optionally change button style to highlight it
                self.ui.showVersionHistoryButton.setStyleSheet("""
                    QPushButton {
                        background-color: #d97706;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #f59e0b;
                    }
                """)

        # Load feature request UI
        self._load_feature_request_ui()

    def _on_show_version_history(self):
        """Show version history dialog."""
        # Clear notification from button when clicked
        if hasattr(self.ui, 'showVersionHistoryButton'):
            button_text = self.ui.showVersionHistoryButton.text()
            if button_text.endswith(" •"):
                self.ui.showVersionHistoryButton.setText(button_text.replace(" •", ""))
            # Reset button style
            self.ui.showVersionHistoryButton.setStyleSheet("")

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

        dialog.exec()

    def _load_user_settings_ui(self):
        """Load user settings into the UI."""
        from core.settings_manager import get_auto_extract_textures, get_generate_3d_thumbnails, get_setting

        # Auto-extract textures checkbox
        if hasattr(self.ui, 'AutoExtractTextures'):
            self.ui.AutoExtractTextures.setChecked(get_auto_extract_textures())

        # Generate 3D thumbnails checkbox
        if hasattr(self.ui, 'Generate3DThumbnails'):
            self.ui.Generate3DThumbnails.setChecked(get_generate_3d_thumbnails())

        # 3D Viewer zoom distance
        if hasattr(self.ui, 'Viewer3DZoomSpinBox'):
            self.ui.Viewer3DZoomSpinBox.setValue(get_setting("viewer_3d_zoom_distance"))

    def _load_default_passes_ui(self):
        """Load default passes into the settings UI."""
        from core.settings_manager import get_default_passes
        from core.config import REQUIRED_PASSES, DEFAULT_PASSES

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
        from core.settings_manager import (
            get_global_settings_path, get_comfyui_mode, get_comfyui_path,
            get_comfyui_python_path, get_comfyui_network_output_path,
            get_comfyui_fast_mode, get_comfyui_fp16_accumulation, get_comfyui_timeout,
            get_comfyui_server_not_found_behavior, get_comfyui_server_wait_timeout
        )

        # Global settings path
        global_path = get_global_settings_path()
        self.ui.GlobalSettingsPathEdit.setText(global_path)
        self.ui.globalSettingsCurrentPath.setText(f"Current: {global_path}")

        # ComfyUI mode
        self._comfyui_mode = get_comfyui_mode()
        self._update_comfyui_mode_button_text()

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

        # Server not found behavior setting
        if hasattr(self.ui, 'ServerNotFoundCombo'):
            behavior = get_comfyui_server_not_found_behavior()
            # Index 0 = "Fail Immediately" (fail), Index 1 = "Wait for Server" (wait)
            self.ui.ServerNotFoundCombo.setCurrentIndex(0 if behavior == "fail" else 1)
            # Connect signal to update wait timeout visibility
            self.ui.ServerNotFoundCombo.currentIndexChanged.connect(self._update_server_wait_visibility)

        # Server wait timeout setting
        if hasattr(self.ui, 'ServerWaitTimeoutSpinBox'):
            timeout_seconds = get_comfyui_server_wait_timeout()
            # Convert to minutes for UI display
            self.ui.ServerWaitTimeoutSpinBox.setValue(timeout_seconds // 60)

        self._update_comfyui_python_visibility()
        self._update_server_wait_visibility()

    def _load_admin_users_ui(self):
        """Load admin users list (settings access only)."""
        from core.settings_manager import get_admin_users

        if not hasattr(self.ui, 'AdminUsersList'):
            return

        self.ui.AdminUsersList.clear()
        for user in get_admin_users():
            self.ui.AdminUsersList.addItem(user)

    def _load_sup_users_ui(self):
        """Load supervisor users list (full access)."""
        from core.settings_manager import get_sup_users

        if not hasattr(self.ui, 'SupUsersList'):
            return

        self.ui.SupUsersList.clear()
        for user in get_sup_users():
            self.ui.SupUsersList.addItem(user)

    def _update_comfyui_mode_button_text(self):
        """Update the ComfyUI mode button text to show current selection."""
        for label, mode in self._comfyui_mode_options:
            if mode == self._comfyui_mode:
                self.ui.ComfyUIModeButton.setText(f"ComfyUI Mode: {label}")
                break

    def _on_comfyui_mode_button_clicked(self):
        """Show popup menu with ComfyUI mode options."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self.main_window)

        for label, mode in self._comfyui_mode_options:
            action = menu.addAction(label)
            action.setData(mode)
            if mode == self._comfyui_mode:
                action.setCheckable(True)
                action.setChecked(True)

        # Show menu below the button
        action = menu.exec_(self.ui.ComfyUIModeButton.mapToGlobal(
            self.ui.ComfyUIModeButton.rect().bottomLeft()
        ))

        if action and action.data():
            self._comfyui_mode = action.data()
            self._update_comfyui_mode_button_text()
            self._update_comfyui_python_visibility()

    def _update_comfyui_python_visibility(self):
        """Show/hide Python path field based on selected mode."""
        is_standalone = self._comfyui_mode == "standalone"
        self.ui.ComfyUIPythonEdit.setEnabled(is_standalone)
        self.ui.BrowseComfyUIPython.setEnabled(is_standalone)

    def _update_server_wait_visibility(self):
        """Show/hide server wait timeout based on selected behavior."""
        if hasattr(self.ui, 'ServerNotFoundCombo') and hasattr(self.ui, 'ServerWaitTimeoutSpinBox'):
            is_wait = self.ui.ServerNotFoundCombo.currentIndex() == 1
            self.ui.ServerWaitTimeoutSpinBox.setEnabled(is_wait)
            if hasattr(self.ui, 'serverWaitTimeoutLabel'):
                self.ui.serverWaitTimeoutLabel.setEnabled(is_wait)

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
        from core.config import REQUIRED_PASSES

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
            from core.config import DEFAULT_PASSES
            from core.settings_manager import set_default_passes
            set_default_passes(DEFAULT_PASSES.copy())
            self.log("Reset to default passes")
            self._load_default_passes_ui()

    def _on_save_settings_clicked(self):
        """Save user settings."""
        from core.config import REQUIRED_PASSES
        from core.settings_manager import set_default_passes, set_auto_extract_textures, set_generate_3d_thumbnails, set_setting

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

        # Save auto-extract textures setting
        if hasattr(self.ui, 'AutoExtractTextures'):
            set_auto_extract_textures(self.ui.AutoExtractTextures.isChecked())

        # Save generate 3D thumbnails setting
        if hasattr(self.ui, 'Generate3DThumbnails'):
            set_generate_3d_thumbnails(self.ui.Generate3DThumbnails.isChecked())

        # Save 3D viewer zoom setting
        if hasattr(self.ui, 'Viewer3DZoomSpinBox'):
            set_setting("viewer_3d_zoom_distance", self.ui.Viewer3DZoomSpinBox.value())

        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.pulse_button(self.ui.SaveSettingsButton)
            self.main_window.animator.show_success("User settings saved")

    def _on_regenerate_thumbnails(self):
        """Clear all cached thumbnails and trigger regeneration."""
        reply = QMessageBox.question(
            self.main_window, "Regenerate Thumbnails",
            "This will clear all cached gallery thumbnails.\n"
            "They will be regenerated when you view the gallery.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Clear model thumbnail cache
                from models.thumbnail_service import get_model_thumbnail_service
                service = get_model_thumbnail_service()
                service.clear_cache()
                self.log("Cleared model thumbnail cache")

                # Clear image thumbnail cache (if it exists)
                thumbnail_cache_dir = os.path.join(os.path.expanduser("~"), ".luma_tools", "thumbnails")
                if os.path.exists(thumbnail_cache_dir):
                    import shutil
                    count = 0
                    for filename in os.listdir(thumbnail_cache_dir):
                        filepath = os.path.join(thumbnail_cache_dir, filename)
                        try:
                            os.remove(filepath)
                            count += 1
                        except Exception:
                            pass
                    self.log(f"Cleared {count} cached thumbnail files")

                # Notify gallery tab to refresh
                gallery_tab = self.main_window.get_tab("comfyui_gallery")
                if gallery_tab:
                    # Clear widget cache to force thumbnail reload
                    if hasattr(gallery_tab, '_widget_cache'):
                        gallery_tab._widget_cache = {}
                    gallery_tab._on_refresh()

                if hasattr(self.main_window, 'animator'):
                    self.main_window.animator.show_success("Thumbnail cache cleared")

            except Exception as e:
                self.log(f"Error clearing thumbnails: {e}")
                if hasattr(self.main_window, 'animator'):
                    self.main_window.animator.show_error(f"Error: {e}")

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
        from core.settings_manager import (
            set_global_settings_path, set_comfyui_mode, set_comfyui_path,
            set_comfyui_python_path, set_comfyui_network_output_path,
            set_comfyui_fast_mode, set_comfyui_fp16_accumulation,
            set_comfyui_timeout, set_comfyui_server_not_found_behavior,
            set_comfyui_server_wait_timeout
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
        set_comfyui_mode(self._comfyui_mode)
        set_comfyui_path(self.ui.ComfyUIPathEdit.text().strip())
        set_comfyui_python_path(self.ui.ComfyUIPythonEdit.text().strip())
        set_comfyui_network_output_path(self.ui.ComfyUINetworkOutputEdit.text().strip())
        set_comfyui_fast_mode(self.ui.ComfyUIFastMode.isChecked())
        set_comfyui_fp16_accumulation(self.ui.ComfyUIFP16Accumulation.isChecked())

        # Save ComfyUI timeout setting
        if hasattr(self.ui, 'ComfyUITimeoutSpinBox'):
            timeout_minutes = self.ui.ComfyUITimeoutSpinBox.value()
            set_comfyui_timeout(timeout_minutes * 60)  # Convert to seconds

        # Save server not found behavior setting
        if hasattr(self.ui, 'ServerNotFoundCombo'):
            behavior = "fail" if self.ui.ServerNotFoundCombo.currentIndex() == 0 else "wait"
            set_comfyui_server_not_found_behavior(behavior)

        # Save server wait timeout setting
        if hasattr(self.ui, 'ServerWaitTimeoutSpinBox'):
            timeout_minutes = self.ui.ServerWaitTimeoutSpinBox.value()
            set_comfyui_server_wait_timeout(timeout_minutes * 60)  # Convert to seconds

        # Save restricted tabs configuration
        self._save_restricted_tabs_settings()

        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.show_success("Global settings saved")

    def _on_add_admin_user(self):
        """Add an admin user."""
        from core.settings_manager import add_admin_user

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
        from core.settings_manager import remove_admin_user
        from PySide6.QtWidgets import QMessageBox

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

    def _on_add_sup_user(self):
        """Add a supervisor user."""
        from core.settings_manager import add_sup_user

        username, ok = QtWidgets.QInputDialog.getText(
            self.main_window, "Add Supervisor", "Enter username:",
            QtWidgets.QLineEdit.Normal
        )
        if ok and username:
            username = username.strip().lower()
            add_sup_user(username)
            self._load_sup_users_ui()
            self.log(f"Added supervisor user: {username}")

    def _on_remove_sup_user(self):
        """Remove selected supervisor user."""
        from core.settings_manager import remove_sup_user
        from PySide6.QtWidgets import QMessageBox

        if not hasattr(self.ui, 'SupUsersList'):
            return

        selected_items = self.ui.SupUsersList.selectedItems()
        if not selected_items:
            self.log("No supervisor user selected for removal")
            return

        username = selected_items[0].text()

        # Warn if removing self
        if username.lower() == self.app_state.user.lower():
            reply = QMessageBox.warning(
                self.main_window,
                "Remove Yourself?",
                "You are about to remove yourself from the supervisor list.\n"
                "You will lose access to supervisor features after restarting.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        remove_sup_user(username)
        self._load_sup_users_ui()
        if hasattr(self.main_window, 'animator'):
            self.main_window.animator.show_success(f"Removed supervisor: {username}")

    # =========================================================================
    # RESTRICTED TABS
    # =========================================================================

    def _load_restricted_tabs_ui(self):
        """Load restricted tabs settings into the checkboxes."""
        from core.settings_manager import get_restricted_tabs

        restricted = get_restricted_tabs()

        # Map tab names to checkboxes (Settings is admin-only, not configurable here)
        checkbox_map = {
            "comfyui": getattr(self.ui, 'RestrictComfyUI', None),
            "comfyui_gallery": getattr(self.ui, 'RestrictComfyUIGallery', None),
            "passbuilder": getattr(self.ui, 'RestrictPassBuilder', None),
            "mp4maker": getattr(self.ui, 'RestrictMP4Maker', None),
            "republish": getattr(self.ui, 'RestrictRePublish', None),
            "shotcleaner": getattr(self.ui, 'RestrictShotCleaner', None),
        }

        for tab_name, checkbox in checkbox_map.items():
            if checkbox:
                checkbox.setChecked(tab_name in restricted)

    def _save_restricted_tabs_settings(self):
        """Save restricted tabs settings from the checkboxes."""
        from core.settings_manager import set_restricted_tabs

        restricted = []

        # Map checkboxes to tab names (Settings is admin-only, not configurable here)
        checkbox_map = {
            "comfyui": getattr(self.ui, 'RestrictComfyUI', None),
            "comfyui_gallery": getattr(self.ui, 'RestrictComfyUIGallery', None),
            "passbuilder": getattr(self.ui, 'RestrictPassBuilder', None),
            "mp4maker": getattr(self.ui, 'RestrictMP4Maker', None),
            "republish": getattr(self.ui, 'RestrictRePublish', None),
            "shotcleaner": getattr(self.ui, 'RestrictShotCleaner', None),
        }

        for tab_name, checkbox in checkbox_map.items():
            if checkbox and checkbox.isChecked():
                restricted.append(tab_name)

        set_restricted_tabs(restricted)

    def _load_feature_request_ui(self):
        """Configure feature request buttons based on user role."""
        # Submit button is visible to everyone
        if hasattr(self.ui, 'submitFeatureRequestButton'):
            self.ui.submitFeatureRequestButton.setVisible(True)

        # View button only visible to admins
        if hasattr(self.ui, 'viewFeatureRequestsButton'):
            is_admin = self.app_state.is_admin
            self.ui.viewFeatureRequestsButton.setVisible(is_admin)

            # Check for unread requests (admins only)
            if is_admin:
                from core.settings_manager import get_unread_feature_request_count
                unread_count = get_unread_feature_request_count(self.app_state.user)

                if unread_count > 0:
                    # Add notification indicator
                    self.ui.viewFeatureRequestsButton.setText(f"View Requests ({unread_count})")
                    # Add orange styling like version history
                    self.ui.viewFeatureRequestsButton.setStyleSheet("""
                        QPushButton {
                            background-color: #d97706;
                            color: white;
                        }
                        QPushButton:hover {
                            background-color: #f59e0b;
                        }
                    """)
                    # Request attention (pulsing glow)
                    self.signals.request_attention.emit()

    def _on_submit_feature_request(self):
        """Show feature request submission dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QTextEdit, QLabel, QDialogButtonBox, QMessageBox
        from core.settings_manager import append_feature_request

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Luma Tools - Submit Feature Request")
        dialog.setMinimumSize(500, 400)

        layout = QVBoxLayout(dialog)

        # Category dropdown
        category_label = QLabel("Category:")
        layout.addWidget(category_label)

        category_combo = QComboBox()
        category_combo.addItems(["Feature", "Bug", "Enhancement", "Question"])
        layout.addWidget(category_combo)

        # Description text area with spell checking
        description_label = QLabel("Description:")
        layout.addWidget(description_label)

        description_edit = QTextEdit()
        description_edit.setPlaceholderText("Describe your request or issue in detail...")

        # Add spell checking if available
        try:
            from ui.spell_checker import add_spell_checking
            add_spell_checking(description_edit)
        except Exception as e:
            print(f"Spell checking not available: {e}")

        layout.addWidget(description_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        if dialog.exec() == QDialog.Accepted:
            category = category_combo.currentText()
            description = description_edit.toPlainText().strip()

            if not description:
                QMessageBox.warning(
                    self.main_window,
                    "Empty Description",
                    "Please enter a description for your request."
                )
                return

            # Submit request
            username = self.app_state.user
            success = append_feature_request(category, description, username)

            if success:
                QMessageBox.information(
                    self.main_window,
                    "Request Submitted",
                    "Your feature request has been submitted successfully.\nAdmins will be notified."
                )

                # Notify admins
                self._notify_admins_of_new_request()
            else:
                QMessageBox.critical(
                    self.main_window,
                    "Submission Failed",
                    "Failed to submit feature request. Please try again or contact an admin."
                )

    def _notify_admins_of_new_request(self):
        """Notify all admins of new feature request via system tray."""
        # Use main window's notification system
        if hasattr(self.main_window, 'show_system_notification'):
            self.main_window.show_system_notification(
                "New Feature Request",
                "A new feature request has been submitted. Check the Settings tab to view.",
                "info"
            )

    def _on_view_feature_requests(self):
        """Show all feature requests dialog (admin only)."""
        if not self.app_state.is_admin:
            QMessageBox.warning(
                self.main_window,
                "Access Denied",
                "Only administrators can view feature requests."
            )
            return

        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox, QLabel
        from core.settings_manager import get_feature_requests, mark_feature_requests_as_read

        # Clear notification indicator
        if hasattr(self.ui, 'viewFeatureRequestsButton'):
            self.ui.viewFeatureRequestsButton.setText("View Requests")
            self.ui.viewFeatureRequestsButton.setStyleSheet("")

        # Mark as read
        mark_feature_requests_as_read(self.app_state.user)

        # Get requests
        requests = get_feature_requests()

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Luma Tools - Feature Requests")
        dialog.setMinimumSize(700, 500)

        layout = QVBoxLayout(dialog)

        # Info label
        info_label = QLabel(f"Total Requests: {len(requests)}")
        info_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(info_label)

        # Text display
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)

        # Format requests
        if requests:
            formatted_text = ""
            for i, req in enumerate(requests, 1):
                formatted_text += f"{'='*70}\n"
                formatted_text += f"Request #{i}\n"
                formatted_text += f"Date: {req['timestamp']}\n"
                formatted_text += f"User: {req['username']}\n"
                formatted_text += f"Category: {req['category']}\n"
                formatted_text += f"{'-'*70}\n"
                formatted_text += f"{req['description']}\n\n"

            text_edit.setPlainText(formatted_text)
        else:
            text_edit.setPlainText("No feature requests yet.")

        layout.addWidget(text_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.exec()
