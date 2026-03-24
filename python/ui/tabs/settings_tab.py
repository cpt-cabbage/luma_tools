"""
Settings tab module for Luma Tools.

Handles user settings (local) and global settings management.
"""

import os
import logging
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

from .base_tab import BaseTab, TabConfig
from dialog_helpers import confirm_action, show_warning, show_error, show_info
from core.utils import ensure_directory
from core.config import APP_VERSION, get_changelog, get_latest_changelog

logger = logging.getLogger(__name__)

# Widget type constants for settings mapping
_CHECKBOX = "checkbox"
_TEXT = "text"
_SPINBOX = "spinbox"

# Widget type constants for settings mapping (extended)
_COMBOBOX = "combobox"

# Declarative settings mappings: (setting_key, widget_name, widget_type[, load_converter, save_converter])
# Adding a new setting only requires adding one entry here — load and save are automatic.
_USER_SETTINGS_MAP = [
    ("show_tray_notifications", "ShowTrayNotifications", _CHECKBOX),
    ("show_statusbar_log", "ShowStatusbarLog", _CHECKBOX),
    ("viewer_3d_zoom_distance", "Viewer3DZoomSpinBox", _SPINBOX),
    # ComfyUI-Gallery integration settings
    ("comfyui_completion_sound", "ComfyUICompletionSoundCombo", _COMBOBOX),
    ("comfyui_convert_colorspace", "ComfyUIConvertColorspace", _CHECKBOX),
    ("viewer_live_audio_scrub", "ViewerLiveAudioScrub", _CHECKBOX),
]

_seconds_to_minutes = lambda s: s // 60  # noqa: E731
_minutes_to_seconds = lambda m: m * 60   # noqa: E731

_GLOBAL_SETTINGS_MAP = [
    ("comfyui_path", "ComfyUIPathEdit", _TEXT),
    ("comfyui_python_path", "ComfyUIPythonEdit", _TEXT),
    ("network_output_path", "NetworkOutputEdit", _TEXT),
    ("comfyui_fast_mode", "ComfyUIFastMode", _CHECKBOX),
    ("comfyui_lowvram", "ComfyUILowVRAM", _CHECKBOX),
    ("comfyui_highvram", "ComfyUIHighVRAM", _CHECKBOX),
    ("comfyui_normalvram", "ComfyUINormalVRAM", _CHECKBOX),
    ("comfyui_disable_smart_memory", "ComfyUIDisableSmartMemory", _CHECKBOX),
    ("comfyui_timeout", "ComfyUITimeoutSpinBox", _SPINBOX, _seconds_to_minutes, _minutes_to_seconds),
    ("comfyui_server_wait_timeout", "ServerWaitTimeoutSpinBox", _SPINBOX, _seconds_to_minutes, _minutes_to_seconds),
    # Canvas sync settings
    ("canvas_sync_interval", "CanvasSyncIntervalSpinBox", _SPINBOX),
    # Deadline polling settings
    ("deadline_poll_interval", "DeadlinePollIntervalSpinBox", _SPINBOX),
]


class SettingsTab(BaseTab):
    """Tab for managing user and global settings."""

    TAB_CONFIG = TabConfig(ui_file="settings.ui", tab_name="Settings", tab_id="settings")

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
        self.ui.BrowseNetworkOutput.clicked.connect(self._on_browse_network_output)
        # ComfyUI mode button connected in initialize() via manager
        self.ui.SaveGlobalSettings.clicked.connect(self._on_save_global_settings)
        # Update Python path display when ComfyUI path or Python path changes
        self.ui.ComfyUIPathEdit.textChanged.connect(self._update_comfyui_python_visibility)
        self.ui.ComfyUIPythonEdit.textChanged.connect(self._update_comfyui_python_visibility)

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

        # HDRI management
        if hasattr(self.ui, 'AddHdriButton'):
            self.ui.AddHdriButton.clicked.connect(self._on_add_hdri)
        if hasattr(self.ui, 'RemoveHdriButton'):
            self.ui.RemoveHdriButton.clicked.connect(self._on_remove_hdri)

        # Category management
        if hasattr(self.ui, 'AddCategoryButton'):
            self.ui.AddCategoryButton.clicked.connect(self._on_add_category)
        if hasattr(self.ui, 'RemoveCategoryButton'):
            self.ui.RemoveCategoryButton.clicked.connect(self._on_remove_category)
        if hasattr(self.ui, 'MoveCategoryUpButton'):
            self.ui.MoveCategoryUpButton.clicked.connect(self._on_move_category_up)
        if hasattr(self.ui, 'MoveCategoryDownButton'):
            self.ui.MoveCategoryDownButton.clicked.connect(self._on_move_category_down)

    def initialize(self):
        """Initialize settings tab."""
        from option_button import OptionButtonManager

        # Initialize optional UI attributes unconditionally
        self._version_badge = None

        # ComfyUI mode option manager
        self._comfyui_mode_manager = OptionButtonManager(
            button=self.ui.ComfyUIModeButton,
            options=[
                ("Embedded (python_embeded)", "embedded"),
                ("Portable (venv)", "portable"),
                ("Standalone", "standalone"),
            ],
            initial_value="embedded",
            on_changed=self._on_comfyui_mode_changed,
            label_prefix="ComfyUI Mode: ",
            parent_window=self.main_window
        )

        # Check if user is supervisor (can see user settings but not global settings)
        is_supervisor = self.app_state.is_sup and not self.app_state.is_admin

        # Create programmatic global settings UI widgets
        self._setup_canvas_sync_interval_ui()
        self._setup_deadline_poll_interval_ui()

        # Initialize completion sound combobox with data values
        if hasattr(self.ui, 'ComfyUICompletionSoundCombo'):
            combo = self.ui.ComfyUICompletionSoundCombo
            combo.clear()
            combo.addItem("None", "none")
            combo.addItem("Subtle", "subtle")
            combo.addItem("System", "system")

        self._load_version_ui()

        # Supervisors can see user settings, admins can see everything
        self._load_default_passes_ui()
        self._load_user_settings_ui()

        # Only load global settings and admin sections for admins
        if not is_supervisor:
            self._load_global_settings_ui()
            self._load_admin_users_ui()
            self._load_sup_users_ui()
            self._load_restricted_tabs_ui()
            self._load_hdri_list_ui()
            self._load_categories_ui()
        else:
            # Hide global settings for supervisors
            self._hide_global_settings_for_supervisor()

    def _hide_global_settings_for_supervisor(self):
        """Hide global settings section for supervisor users (they can still see user settings)."""
        # Hide global settings group box
        if hasattr(self.ui, 'globalSettingsGroupBox'):
            self.ui.globalSettingsGroupBox.hide()

    def _setup_canvas_sync_interval_ui(self):
        """Create and add canvas sync interval spinbox to global settings."""
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QSpacerItem, QSizePolicy

        # Only add if global settings layout exists
        if not hasattr(self.ui, 'globalSettingsLayout'):
            return

        layout = self.ui.globalSettingsLayout

        # Create horizontal layout for the setting
        row_layout = QHBoxLayout()

        # Label
        label = QLabel("Canvas Sync Interval (ms):")
        label.setToolTip("How often the canvas syncs with other users (lower = faster, more network load)")
        row_layout.addWidget(label)

        # Spinbox
        spinbox = QSpinBox()
        spinbox.setMinimum(500)
        spinbox.setMaximum(5000)
        spinbox.setSingleStep(100)
        spinbox.setValue(1000)
        spinbox.setSuffix(" ms")
        spinbox.setToolTip("Sync interval in milliseconds (500-5000ms)")
        row_layout.addWidget(spinbox)

        # Spacer
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        row_layout.addItem(spacer)

        # Insert after the server timeout row (find adminUsersHeader as reference)
        insert_index = -1
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if widget.objectName() == 'adminUsersHeader':
                    insert_index = i
                    break

        if insert_index >= 0:
            layout.insertLayout(insert_index, row_layout)
        else:
            # Fallback: add before the last stretch
            layout.addLayout(row_layout)

        # Store reference so declarative system can find it
        self.ui.CanvasSyncIntervalSpinBox = spinbox

    def _setup_deadline_poll_interval_ui(self):
        """Create and add Deadline poll interval spinbox to global settings."""
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QSpacerItem, QSizePolicy

        if not hasattr(self.ui, 'globalSettingsLayout'):
            return

        layout = self.ui.globalSettingsLayout

        row_layout = QHBoxLayout()

        label = QLabel("Deadline Poll Interval:")
        label.setToolTip("How often to check Deadline for job status updates")
        row_layout.addWidget(label)

        spinbox = QSpinBox()
        spinbox.setMinimum(1)
        spinbox.setMaximum(60)
        spinbox.setSingleStep(1)
        spinbox.setValue(5)
        spinbox.setSuffix(" s")
        spinbox.setToolTip("Poll interval in seconds (1-60s)")
        row_layout.addWidget(spinbox)

        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        row_layout.addItem(spacer)

        # Insert after canvas sync interval (find adminUsersHeader as reference)
        insert_index = -1
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if widget.objectName() == 'adminUsersHeader':
                    insert_index = i
                    break

        if insert_index >= 0:
            layout.insertLayout(insert_index, row_layout)
        else:
            layout.addLayout(row_layout)

        self.ui.DeadlinePollIntervalSpinBox = spinbox

    def _load_version_ui(self):
        """Load version information into the UI."""
        version = APP_VERSION
        if hasattr(self.ui, 'versionValueLabel'):
            self.ui.versionValueLabel.setText(version)

        # Hide the new version label initially
        if hasattr(self.ui, 'newVersionLabel'):
            self.ui.newVersionLabel.setVisible(False)

        # Check if this is a new version and show notification badge on button
        if hasattr(self.ui, 'showVersionHistoryButton'):
            from core.user_preferences import is_new_version
            if is_new_version(version):
                # Create and show notification badge
                from effects import ButtonNotificationBadge
                self._version_badge = ButtonNotificationBadge(
                    self.ui.showVersionHistoryButton
                )
                self._version_badge.show_badge()

        # Show current AYON production bundle with AYON branding
        if hasattr(self.ui, 'BundleLabel'):
            from core.config import get_ayon_bundle, UIColors
            self.ui.BundleLabel.setText(get_ayon_bundle())
            self.ui.BundleLabel.setStyleSheet(f"color: {UIColors.AYON_GREEN};")
        if hasattr(self.ui, 'label_bundle'):
            from icons import get_ayon_icon
            from core.config import UIColors
            self.ui.label_bundle.setStyleSheet(f"color: {UIColors.AYON_GREEN};")

        # Load feature request UI
        self._load_feature_request_ui()

        # Check for user notifications
        self._check_user_notifications()

    def show_new_version_available(self, new_version: str):
        """Show notification that a new version is available in the info area."""
        if hasattr(self.ui, 'newVersionLabel'):
            self.ui.newVersionLabel.setText(
                f"New version available: v{new_version} - Please restart Luma Tools to update."
            )
            self.ui.newVersionLabel.setVisible(True)

        # Request attention for this tab (pulsing glow)
        self.signals.request_attention.emit()

    def _check_user_notifications(self):
        """Check if user has notifications about completed or rejected requests."""
        from core.feature_requests import get_user_notifications, mark_notifications_read

        try:
            notifications = get_user_notifications(self.app_state.user)

            if notifications:
                # Separate completed and rejected notifications
                # Missing 'action' field is treated as "completed" for backwards compatibility
                completed = [n for n in notifications if n.get('action', 'completed') == 'completed']
                rejected = [n for n in notifications if n.get('action') == 'rejected']

                if hasattr(self.main_window, 'show_system_notification'):
                    # Show completed notifications
                    if completed:
                        if len(completed) == 1:
                            notif = completed[0]
                            message = f"[{notif['request_category']}] {notif['request_description']}"
                        else:
                            message = f"{len(completed)} feature requests have been completed"
                        self.main_window.show_system_notification(
                            "Feature Requests Completed",
                            message,
                            "success"
                        )

                    # Show rejected notifications
                    if rejected:
                        if len(rejected) == 1:
                            notif = rejected[0]
                            reason = notif.get('reason', 'No reason provided')
                            message = f"[{notif['request_category']}] {notif['request_description']}\nReason: {reason}"
                        else:
                            message = f"{len(rejected)} feature requests have been rejected"
                        self.main_window.show_system_notification(
                            "Feature Request Update",
                            message,
                            "warning"
                        )

                # Mark as read
                mark_notifications_read(self.app_state.user)

        except Exception as e:
            logger.error(f"Error checking user notifications: {e}")

    def _on_show_version_history(self):
        """Show version history dialog with latest changelog and Full Changelog button."""
        from PySide6.QtWidgets import QHBoxLayout, QPushButton

        # Hide notification badge when clicked
        if hasattr(self, '_version_badge') and self._version_badge is not None:
            self._version_badge.hide_badge()

        # Start with latest changelog only
        latest_changelog = get_latest_changelog()

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Luma Tools - Version History")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setMarkdown(latest_changelog)
        layout.addWidget(text_edit)

        # Button row with Full Changelog and OK
        button_layout = QHBoxLayout()

        full_changelog_btn = QPushButton("Full Changelog")
        full_changelog_btn.setToolTip("Show all version history")

        def show_full_changelog():
            text_edit.setMarkdown(get_changelog())
            full_changelog_btn.setEnabled(False)
            full_changelog_btn.setText("Showing Full Changelog")

        full_changelog_btn.clicked.connect(show_full_changelog)
        button_layout.addWidget(full_changelog_btn)

        button_layout.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)

        dialog.exec()

    def _load_settings_from_map(self, settings_map):
        """Load settings into UI widgets using a declarative mapping.

        Each entry in settings_map is a tuple:
            (setting_key, widget_name, widget_type[, load_converter, save_converter])
        Widgets that don't exist in the UI are silently skipped.
        """
        from core.settings_manager import get_setting

        # Snapshot all values first to avoid partial reads during external changes
        values = {}
        for entry in settings_map:
            key = entry[0]
            try:
                values[key] = get_setting(key)
            except (KeyError, Exception):
                values[key] = None

        for entry in settings_map:
            key, widget_name, widget_type = entry[0], entry[1], entry[2]
            load_converter = entry[3] if len(entry) > 3 else None

            widget = getattr(self.ui, widget_name, None)
            if not widget:
                continue

            value = values[key]
            if value is None:
                continue
            if load_converter:
                value = load_converter(value)

            if widget_type == _CHECKBOX:
                widget.setChecked(value)
            elif widget_type == _TEXT:
                widget.setText(str(value))
            elif widget_type == _SPINBOX:
                widget.setValue(value)
            elif widget_type == _COMBOBOX:
                # Find and select the item with matching data or text
                index = widget.findData(value)
                if index < 0:
                    index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)

    def _save_settings_from_map(self, settings_map):
        """Save UI widget values to settings using a declarative mapping.

        Each entry in settings_map is a tuple:
            (setting_key, widget_name, widget_type[, load_converter, save_converter])
        Widgets that don't exist in the UI are silently skipped.
        """
        from core.settings_manager import set_setting

        for entry in settings_map:
            key, widget_name, widget_type = entry[0], entry[1], entry[2]
            save_converter = entry[4] if len(entry) > 4 else None

            widget = getattr(self.ui, widget_name, None)
            if not widget:
                continue

            if widget_type == _CHECKBOX:
                value = widget.isChecked()
            elif widget_type == _TEXT:
                value = widget.text().strip()
            elif widget_type == _SPINBOX:
                value = widget.value()
            elif widget_type == _COMBOBOX:
                # Get data if available, otherwise get text
                value = widget.currentData()
                if value is None:
                    value = widget.currentText()
            else:
                continue

            if save_converter:
                value = save_converter(value)
            set_setting(key, value)

    def _load_user_settings_ui(self):
        """Load user settings into the UI."""
        self._load_settings_from_map(_USER_SETTINGS_MAP)

    def _load_default_passes_ui(self):
        """Load default passes into the settings UI."""
        from core.user_preferences import get_default_passes
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

    def _load_global_settings_ui(self):
        """Load global settings into the settings UI."""
        from core.settings_manager import get_global_settings_path, get_setting

        # Global settings path (custom display logic)
        global_path = get_global_settings_path()
        self.ui.GlobalSettingsPathEdit.setText(global_path)
        self.ui.globalSettingsCurrentPath.setText(f"Current: {global_path}")

        # ComfyUI mode - set via OptionButtonManager
        self._comfyui_mode_manager.set_value(get_setting("comfyui_mode"))

        # Load all mapped settings (paths, checkboxes, spinboxes with converters)
        self._load_settings_from_map(_GLOBAL_SETTINGS_MAP)

        # Server not found behavior combo (custom bidirectional mapping)
        if hasattr(self.ui, 'ServerNotFoundCombo'):
            behavior = get_setting("comfyui_server_not_found_behavior")
            self.ui.ServerNotFoundCombo.setCurrentIndex(0 if behavior == "fail" else 1)
            self.ui.ServerNotFoundCombo.currentIndexChanged.connect(self._update_server_wait_visibility)

        self._update_comfyui_python_visibility()
        self._update_server_wait_visibility()

    def _load_admin_users_ui(self):
        """Load admin users list (settings access only)."""
        from core.settings_manager import get_users_with_role

        if not hasattr(self.ui, 'AdminUsersList'):
            return

        self.ui.AdminUsersList.clear()
        for user in get_users_with_role("admin"):
            self.ui.AdminUsersList.addItem(user)

    def _load_sup_users_ui(self):
        """Load supervisor users list (full access)."""
        from core.settings_manager import get_users_with_role

        if not hasattr(self.ui, 'SupUsersList'):
            return

        self.ui.SupUsersList.clear()
        for user in get_users_with_role("sup"):
            self.ui.SupUsersList.addItem(user)

    # Property for backward compatibility
    @property
    def _comfyui_mode(self):
        return self._comfyui_mode_manager.value if hasattr(self, '_comfyui_mode_manager') else "embedded"

    def _on_comfyui_mode_changed(self, value):
        """Handle ComfyUI mode change."""
        self._update_comfyui_python_visibility()

    def _update_comfyui_python_visibility(self):
        """Show/hide Python path field and update resolved path display based on selected mode."""
        from comfyui.utils import resolve_comfyui_paths

        is_standalone = self._comfyui_mode == "standalone"
        self.ui.ComfyUIPythonEdit.setEnabled(is_standalone)
        self.ui.BrowseComfyUIPython.setEnabled(is_standalone)

        # Update the "Current:" label to show the resolved Python path
        if hasattr(self.ui, 'comfyuiCurrentPath'):
            comfyui_path = self.ui.ComfyUIPathEdit.text().strip()
            mode = self._comfyui_mode

            if not comfyui_path:
                self.ui.comfyuiCurrentPath.setText("Current: (no ComfyUI path set)")
                return

            if is_standalone:
                # In standalone mode, show the custom Python path from the edit field
                custom_python = self.ui.ComfyUIPythonEdit.text().strip()
                if custom_python:
                    self.ui.comfyuiCurrentPath.setText(f"Current: {custom_python}")
                else:
                    self.ui.comfyuiCurrentPath.setText("Current: (enter Python path above)")
            else:
                # For embedded/portable modes, show the derived path
                try:
                    python_exe, _ = resolve_comfyui_paths(comfyui_path, mode)
                    exists_note = "" if os.path.exists(python_exe) else " (not found)"
                    self.ui.comfyuiCurrentPath.setText(f"Current: {python_exe}{exists_note}")
                except ValueError as e:
                    self.ui.comfyuiCurrentPath.setText(f"Current: (error: {e})")

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
                logging.warning(f"Pass '{pass_name}' already exists in the list")
                return

            item = QtWidgets.QListWidgetItem(pass_name)
            item.setToolTip("Select to include this pass by default")
            item.setSelected(True)
            self.ui.DefaultPassesList.addItem(item)
            logging.info(f"Added custom pass: {pass_name}")

    def _on_remove_pass_clicked(self):
        """Remove selected pass from the default passes list."""
        from core.config import REQUIRED_PASSES

        selected_items = self.ui.DefaultPassesList.selectedItems()
        if not selected_items:
            logging.warning("No passes selected for removal")
            return

        for item in selected_items:
            pass_name = item.text()
            if pass_name in REQUIRED_PASSES:
                logging.warning(f"Cannot remove required pass: {pass_name}")
                continue

            row = self.ui.DefaultPassesList.row(item)
            self.ui.DefaultPassesList.takeItem(row)
            logging.info(f"Removed pass: {pass_name}")

    def _on_reset_passes_clicked(self):
        """Reset default passes to system defaults."""
        if confirm_action("Reset Default Passes", "Reset to default pass list?", self.main_window):
            from core.config import DEFAULT_PASSES
            from core.user_preferences import set_default_passes
            set_default_passes(DEFAULT_PASSES.copy())
            logging.info("Reset to default passes")
            self._load_default_passes_ui()

    def _on_save_settings_clicked(self):
        """Save user settings."""
        from core.config import REQUIRED_PASSES
        from core.user_preferences import set_default_passes

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
        logging.info(f"Saved default passes: {selected_passes}")

        # Save all mapped user settings
        self._save_settings_from_map(_USER_SETTINGS_MAP)

        # Update status bar log visibility immediately
        if hasattr(self.ui, 'ShowStatusbarLog') and hasattr(self.main_window, 'update_statusbar_log_visibility'):
            self.main_window.update_statusbar_log_visibility(self.ui.ShowStatusbarLog.isChecked())

        self.pulse_button(self.ui.SaveSettingsButton)
        self.show_status("User settings saved", "success")

    def _on_regenerate_thumbnails(self):
        """Clear all cached thumbnails and trigger regeneration."""
        if confirm_action(
            "Regenerate Thumbnails",
            "This will clear all cached gallery thumbnails.\n"
            "They will be regenerated when you view the gallery.\n\nContinue?",
            self.main_window
        ):
            try:
                # Clear model thumbnail cache
                from geo.thumbnail_service import get_model_thumbnail_service
                service = get_model_thumbnail_service()
                service.clear_cache()
                logging.info("Cleared model thumbnail cache")

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
                    logging.info(f"Cleared {count} cached thumbnail files")

                # Notify gallery tab to refresh via event bus
                from core.event_bus import pipeline_events
                pipeline_events.gallery_refresh_requested.emit(True)  # force=True

                self.show_status("Thumbnail cache cleared", "success")

            except Exception as e:
                logging.error(f"Error clearing thumbnails: {e}")
                self.show_status(f"Error: {e}", "error")

    def _on_browse_global_settings_path(self):
        """Browse for global settings directory."""
        from file_dialogs import browse_directory_with_memory

        directory = browse_directory_with_memory(
            self.main_window,
            context="global_settings_path",
            title="Select Global Settings Directory",
            fallback_path=self.ui.GlobalSettingsPathEdit.text()
        )
        if directory:
            self.ui.GlobalSettingsPathEdit.setText(directory)

    def _on_browse_comfyui_path(self):
        """Browse for ComfyUI installation directory."""
        from file_dialogs import browse_directory_with_memory

        directory = browse_directory_with_memory(
            self.main_window,
            context="comfyui_path",
            title="Select ComfyUI Installation Directory",
            fallback_path=self.ui.ComfyUIPathEdit.text()
        )
        if directory:
            self.ui.ComfyUIPathEdit.setText(directory)

    def _on_browse_comfyui_python(self):
        """Browse for Python executable."""
        from file_dialogs import browse_file_with_memory

        file_path = browse_file_with_memory(
            self.main_window,
            context="comfyui_python",
            title="Select Python Executable",
            file_filter="Executable (*.exe);;All Files (*)",
            fallback_path=self.ui.ComfyUIPythonEdit.text()
        )
        if file_path:
            self.ui.ComfyUIPythonEdit.setText(file_path)

    def _on_browse_network_output(self):
        """Browse for network output directory."""
        from file_dialogs import browse_directory_with_memory

        directory = browse_directory_with_memory(
            self.main_window,
            context="network_output",
            title="Select Network Output Directory",
            fallback_path=self.ui.NetworkOutputEdit.text()
        )
        if directory:
            self.ui.NetworkOutputEdit.setText(directory)

    def _on_save_global_settings(self):
        """Save all global settings."""
        from core.settings_manager import set_global_settings_path, set_setting

        # Save global settings path (custom directory creation logic)
        new_global_path = self.ui.GlobalSettingsPathEdit.text().strip()
        if new_global_path:
            if not os.path.exists(new_global_path):
                if confirm_action(
                    "Create Directory",
                    f"The directory '{new_global_path}' does not exist. Create it?",
                    self.main_window
                ):
                    try:
                        ensure_directory(new_global_path)
                    except Exception as e:
                        self.show_status(f"Failed to create directory: {e}", "error")
                        return
                else:
                    return

            set_global_settings_path(new_global_path)
            self.ui.globalSettingsCurrentPath.setText(f"Current: {new_global_path}")

        # ComfyUI mode (via OptionButtonManager)
        set_setting("comfyui_mode", self._comfyui_mode)

        # Save all mapped global settings (paths, checkboxes, spinboxes with converters)
        self._save_settings_from_map(_GLOBAL_SETTINGS_MAP)

        # Server not found behavior combo (custom bidirectional mapping)
        if hasattr(self.ui, 'ServerNotFoundCombo'):
            behavior = "fail" if self.ui.ServerNotFoundCombo.currentIndex() == 0 else "wait"
            set_setting("comfyui_server_not_found_behavior", behavior)

        # Save restricted tabs configuration
        self._save_restricted_tabs_settings()

        # Clear cached paths so logging and other modules pick up the new values
        try:
            from core.logging_utils import clear_path_cache
            clear_path_cache()
        except ImportError:
            pass

        self.show_status("Global settings saved", "success")

    def _on_add_admin_user(self):
        """Add an admin user."""
        from core.settings_manager import add_user_to_role

        username, ok = QtWidgets.QInputDialog.getText(
            self.main_window, "Add Admin User", "Enter username:",
            QtWidgets.QLineEdit.Normal
        )
        if ok and username:
            username = username.strip().lower()
            add_user_to_role(username, "admin")
            self._load_admin_users_ui()
            logging.info(f"Added admin user: {username}")

    def _on_remove_admin_user(self):
        """Remove selected admin user."""
        from core.settings_manager import remove_user_from_role

        selected_items = self.ui.AdminUsersList.selectedItems()
        if not selected_items:
            logging.warning("No admin user selected for removal")
            return

        username = selected_items[0].text()

        # Warn if removing self
        if username.lower() == self.app_state.user.lower():
            if not confirm_action(
                "Remove Yourself?",
                "You are about to remove yourself from the admin list.\n"
                "You will lose access to admin features after restarting.\n\nContinue?",
                self.main_window
            ):
                return

        remove_user_from_role(username, "admin")
        self._load_admin_users_ui()
        self.show_status(f"Removed admin user: {username}", "success")

    def _on_add_sup_user(self):
        """Add a supervisor user."""
        from core.settings_manager import add_user_to_role

        username, ok = QtWidgets.QInputDialog.getText(
            self.main_window, "Add Supervisor", "Enter username:",
            QtWidgets.QLineEdit.Normal
        )
        if ok and username:
            username = username.strip().lower()
            add_user_to_role(username, "sup")
            self._load_sup_users_ui()
            logging.info(f"Added supervisor user: {username}")

    def _on_remove_sup_user(self):
        """Remove selected supervisor user."""
        from core.settings_manager import remove_user_from_role

        if not hasattr(self.ui, 'SupUsersList'):
            return

        selected_items = self.ui.SupUsersList.selectedItems()
        if not selected_items:
            logging.warning("No supervisor user selected for removal")
            return

        username = selected_items[0].text()

        # Warn if removing self
        if username.lower() == self.app_state.user.lower():
            if not confirm_action(
                "Remove Yourself?",
                "You are about to remove yourself from the supervisor list.\n"
                "You will lose access to supervisor features after restarting.\n\nContinue?",
                self.main_window
            ):
                return

        remove_user_from_role(username, "sup")
        self._load_sup_users_ui()
        self.show_status(f"Removed supervisor: {username}", "success")

    # =========================================================================
    # RESTRICTED TABS
    # =========================================================================

    def _get_restricted_tab_checkbox_map(self):
        """Get the mapping of tab names to their restriction checkboxes.

        Returns:
            dict: {tab_name: checkbox_widget} (Settings is admin-only, not configurable here)
        """
        return {
            "comfyui": getattr(self.ui, 'RestrictComfyUI', None),
            "gallery": getattr(self.ui, 'RestrictGallery', None),
            "passbuilder": getattr(self.ui, 'RestrictPassBuilder', None),
            "mp4maker": getattr(self.ui, 'RestrictMP4Maker', None),
            "republish": getattr(self.ui, 'RestrictRePublish', None),
            "shotcleaner": getattr(self.ui, 'RestrictShotCleaner', None),
        }

    def _load_restricted_tabs_ui(self):
        """Load restricted tabs settings into the checkboxes."""
        from core.settings_manager import get_setting

        restricted = get_setting("restricted_tabs")
        for tab_name, checkbox in self._get_restricted_tab_checkbox_map().items():
            if checkbox:
                checkbox.setChecked(tab_name in restricted)

    def _save_restricted_tabs_settings(self):
        """Save restricted tabs settings from the checkboxes."""
        from core.settings_manager import set_setting

        restricted = [
            tab_name
            for tab_name, checkbox in self._get_restricted_tab_checkbox_map().items()
            if checkbox and checkbox.isChecked()
        ]

        set_setting("restricted_tabs", restricted, verbose=False)
        logger.info(f"Updated restricted tabs: {restricted}")

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
                from core.feature_requests import get_unread_feature_request_count
                unread_count = get_unread_feature_request_count(self.app_state.user)

                if unread_count > 0:
                    # Add notification indicator with count in text
                    self.ui.viewFeatureRequestsButton.setText(f"View Requests ({unread_count})")
                    # Create and show notification badge
                    from effects import ButtonNotificationBadge
                    self._feature_request_badge = ButtonNotificationBadge(
                        self.ui.viewFeatureRequestsButton
                    )
                    self._feature_request_badge.show_badge()
                    # Request attention (pulsing glow)
                    self.signals.request_attention.emit()

    def _on_submit_feature_request(self):
        """Show feature request submission dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QTextEdit, QLabel, QDialogButtonBox
        from core.feature_requests import append_feature_request

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Luma Tools - Submit Feature Request")
        dialog.setMinimumSize(500, 400)

        layout = QVBoxLayout(dialog)

        # Category dropdown
        category_label = QLabel("Category:")
        layout.addWidget(category_label)

        category_combo = QComboBox()
        category_combo.addItems(["Feature", "Bug", "Enhancement"])
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
            logger.warning(f"Spell checking not available: {e}")

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
                show_warning("Empty Description", "Please enter a description for your request.", self.main_window)
                return

            # Submit request
            username = self.app_state.user
            success = append_feature_request(category, description, username)

            if success:
                show_info(
                    "Request Submitted",
                    "Your feature request has been submitted successfully.\nAdmins will be notified.",
                    self.main_window
                )

                # Notify admins
                self._notify_admins_of_new_request()
            else:
                show_error(
                    "Submission Failed",
                    "Failed to submit feature request. Please try again or contact an admin.",
                    self.main_window
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
            show_warning("Access Denied", "Only administrators can view feature requests.", self.main_window)
            return

        from ui.tabs.dialogs import FeatureRequestDialog

        # Clear notification indicator and badge
        if hasattr(self.ui, 'viewFeatureRequestsButton'):
            self.ui.viewFeatureRequestsButton.setText("View Requests")
        if hasattr(self, '_feature_request_badge'):
            self._feature_request_badge.hide_badge()

        # Show dialog
        dialog = FeatureRequestDialog(
            parent=self.main_window,
            user=self.app_state.user,
            is_admin=self.app_state.is_admin
        )

        # If dialog completes requests, reopen to show updated list
        if dialog.exec_() == QDialog.Accepted:
            # Check if any requests were marked as completed (dialog will close after marking)
            # We can tell by checking if the dialog's method was triggered
            # For simplicity, just reopen if user wants to see updated state
            pass

    def _load_hdri_list_ui(self):
        """Load HDRI list from global settings."""
        from core.settings_manager import get_hdri_list

        if not hasattr(self.ui, 'HdriListWidget'):
            return

        self.ui.HdriListWidget.clear()
        hdri_list = get_hdri_list()

        for hdri in hdri_list:
            name = hdri.get("name", "Unnamed")
            path = hdri.get("path", "")
            item = QtWidgets.QListWidgetItem(f"{name}")
            item.setToolTip(path)
            item.setData(Qt.UserRole, hdri)  # Store full hdri dict
            self.ui.HdriListWidget.addItem(item)

    def _on_add_hdri(self):
        """Add a new HDRI to the global list."""
        from core.settings_manager import add_hdri_to_list
        from PySide6.QtWidgets import QInputDialog
        from file_dialogs import browse_file_with_memory

        # Browse for HDRI file
        file_path = browse_file_with_memory(
            self.main_window,
            context="hdri_files",
            title="Select HDRI File",
            file_filter="HDRI Files (*.hdr *.exr);;All Files (*.*)",
            fallback_path=""
        )

        if not file_path:
            return

        # Get a name for the HDRI
        default_name = os.path.splitext(os.path.basename(file_path))[0]
        name, ok = QInputDialog.getText(
            self.main_window,
            "HDRI Name",
            "Enter a name for this HDRI:",
            QtWidgets.QLineEdit.Normal,
            default_name
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        # Add to global settings
        try:
            add_hdri_to_list(name, file_path)
            self._load_hdri_list_ui()
            logging.info(f"Added HDRI: {name}")
        except Exception as e:
            show_warning("Error", f"Failed to add HDRI: {e}", self.main_window)

    def _on_remove_hdri(self):
        """Remove selected HDRI from the global list."""
        from core.settings_manager import remove_hdri_from_list

        if not hasattr(self.ui, 'HdriListWidget'):
            return

        selected_items = self.ui.HdriListWidget.selectedItems()
        if not selected_items:
            logging.warning("No HDRI selected for removal")
            return

        # Confirm deletion
        hdri_names = [item.text() for item in selected_items]
        if not confirm_action(
            "Remove HDRI",
            f"Remove {len(hdri_names)} HDRI(s)?\n\n" + "\n".join(hdri_names),
            self.main_window
        ):
            return

        # Remove from settings
        try:
            for item in selected_items:
                hdri = item.data(Qt.UserRole)
                name = hdri.get("name", "")
                if name:
                    remove_hdri_from_list(name)
                    logging.info(f"Removed HDRI: {name}")

            self._load_hdri_list_ui()
        except Exception as e:
            show_warning("Error", f"Failed to remove HDRI: {e}", self.main_window)

    # =========================================================================
    # COMFYUI PRESET CATEGORIES
    # =========================================================================

    def _load_categories_ui(self):
        """Load ComfyUI preset categories list from global settings."""
        from core.settings_manager import get_setting

        if not hasattr(self.ui, 'CategoriesList'):
            return

        self.ui.CategoriesList.clear()
        categories = get_setting("comfyui_preset_categories")

        for category in categories:
            self.ui.CategoriesList.addItem(category)

    def _on_add_category(self):
        """Add a new category to the global list."""
        from core.settings_manager import get_setting, set_setting

        name, ok = QtWidgets.QInputDialog.getText(
            self.main_window,
            "Add Category",
            "Enter category name:",
            QtWidgets.QLineEdit.Normal
        )

        if not ok or not name:
            return

        name = name.strip()
        if not name:
            return

        categories = get_setting("comfyui_preset_categories")
        if name in categories:
            show_warning("Duplicate", f"Category '{name}' already exists.", self.main_window)
            return

        categories.append(name)
        set_setting("comfyui_preset_categories", categories)
        self._load_categories_ui()
        self.show_status(f"Added category: {name}", "success")
        logger.info(f"Added ComfyUI category: {name}")

    def _on_remove_category(self):
        """Remove selected category from the global list."""
        from core.settings_manager import get_setting, set_setting

        if not hasattr(self.ui, 'CategoriesList'):
            return

        selected_items = self.ui.CategoriesList.selectedItems()
        if not selected_items:
            logger.warning("No category selected for removal")
            return

        name = selected_items[0].text()

        if not confirm_action(
            "Remove Category",
            f"Remove category '{name}'?",
            self.main_window
        ):
            return

        categories = get_setting("comfyui_preset_categories")
        if name in categories:
            categories.remove(name)
            set_setting("comfyui_preset_categories", categories)
            self._load_categories_ui()
            self.show_status(f"Removed category: {name}", "success")
            logger.info(f"Removed ComfyUI category: {name}")

    def _on_move_category_up(self):
        """Move selected category up in the list."""
        self._move_category(-1)

    def _on_move_category_down(self):
        """Move selected category down in the list."""
        self._move_category(1)

    def _move_category(self, direction: int):
        """Move selected category by direction (-1=up, +1=down)."""
        from core.settings_manager import get_setting, set_setting

        if not hasattr(self.ui, 'CategoriesList'):
            return

        selected_items = self.ui.CategoriesList.selectedItems()
        if not selected_items:
            return

        name = selected_items[0].text()
        categories = get_setting("comfyui_preset_categories")

        if name not in categories:
            return

        idx = categories.index(name)
        new_idx = idx + direction

        if new_idx < 0 or new_idx >= len(categories):
            return

        categories[idx], categories[new_idx] = categories[new_idx], categories[idx]
        set_setting("comfyui_preset_categories", categories)

        # Reload and re-select
        self._load_categories_ui()
        for i in range(self.ui.CategoriesList.count()):
            if self.ui.CategoriesList.item(i).text() == name:
                self.ui.CategoriesList.item(i).setSelected(True)
                self.ui.CategoriesList.setCurrentRow(i)
                break
