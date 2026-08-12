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


def _clear_thumbnail_caches() -> int:
    """Delete all cached thumbnails (worker function — no Qt access).

    Returns the number of image-thumbnail files removed.
    """
    # Clear model thumbnail cache
    from geo.thumbnail_service import get_model_thumbnail_service
    get_model_thumbnail_service().clear_cache()
    logger.info("Cleared model thumbnail cache")

    # Clear image thumbnail cache (if it exists)
    thumbnail_cache_dir = os.path.join(os.path.expanduser("~"), ".luma_tools", "thumbnails")
    count = 0
    if os.path.exists(thumbnail_cache_dir):
        for filename in os.listdir(thumbnail_cache_dir):
            filepath = os.path.join(thumbnail_cache_dir, filename)
            try:
                os.remove(filepath)
                count += 1
            except OSError as e:
                logger.debug(f"Could not remove cached thumbnail {filepath}: {e}")
    return count


# Widget type constants for settings mapping
_CHECKBOX = "checkbox"
_TEXT = "text"
_SPINBOX = "spinbox"
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
    ("comfyui_disable_smart_memory", "ComfyUIDisableSmartMemory", _CHECKBOX),
    ("comfyui_timeout", "ComfyUITimeoutSpinBox", _SPINBOX, _seconds_to_minutes, _minutes_to_seconds),
    # Deadline polling settings
    ("deadline_poll_interval", "DeadlinePollIntervalSpinBox", _SPINBOX),
]
# NOTE: comfyui_lowvram / comfyui_normalvram / comfyui_highvram are NOT in the
# map above. They used to be three independent checkboxes that could all be
# ticked at once even though --lowvram/--normalvram/--highvram are mutually
# exclusive ComfyUI launch flags. They are now driven by the single
# ComfyUIVRAMMode combo (see _VRAM_MODE_KEYS) and still written as the same
# three booleans for backward compatibility with server.py / runner.py.

# Combo index -> setting key that must be True (index 0 = Auto, none true).
# The order is also the precedence used when legacy settings have more than
# one flag set: low > normal > high.
_VRAM_MODE_KEYS = ("comfyui_lowvram", "comfyui_normalvram", "comfyui_highvram")


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

        # Dirty-tracking state. _loading suppresses dirty marks while widgets
        # are populated from disk (setChecked/setText fire the same signals a
        # user edit does).
        self._loading = True
        self._user_dirty = False
        self._global_dirty = False
        self._is_active = False
        self._save_button_texts = {}
        self._prompting_unsaved = False

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

        # Create programmatic global settings UI widgets
        self._setup_deadline_poll_interval_ui()

        # Initialize completion sound combobox with data values
        if hasattr(self.ui, 'ComfyUICompletionSoundCombo'):
            combo = self.ui.ComfyUICompletionSoundCombo
            combo.clear()
            combo.addItem("None", "none")
            combo.addItem("Subtle", "subtle")
            combo.addItem("System", "system")

        self._load_version_ui()
        self._load_default_passes_ui()
        self._load_user_settings_ui()
        self._load_global_settings_ui()
        self._load_admin_users_ui()
        self._load_hdri_list_ui()
        self._load_categories_ui()

        # Global settings group is admin-only
        if hasattr(self.ui, 'globalSettingsGroupBox'):
            self.ui.globalSettingsGroupBox.setVisible(self.app_state.is_admin)

        # Wire dirty tracking last so the loads above don't mark the tab dirty
        self._loading = False
        self._connect_dirty_tracking()
        self._update_save_button_states()

    # =========================================================================
    # Unsaved-changes tracking
    # =========================================================================

    def _connect_dirty_tracking(self):
        """Wire widget-change signals for the map-driven settings to dirty flags.

        Without this the Save buttons gave no hint that edits were pending, and
        switching tabs silently discarded them.
        """
        signal_by_type = {
            _CHECKBOX: "toggled",
            _TEXT: "textChanged",
            _SPINBOX: "valueChanged",
            _COMBOBOX: "currentIndexChanged",
        }

        for settings_map, scope in (
            (_USER_SETTINGS_MAP, "user"),
            (_GLOBAL_SETTINGS_MAP, "global"),
        ):
            for entry in settings_map:
                widget = getattr(self.ui, entry[1], None)
                signal_name = signal_by_type.get(entry[2])
                if widget is None or not signal_name:
                    continue
                signal = getattr(widget, signal_name, None)
                if signal is None:
                    continue
                # Default arg captures the scope by value (loop closure bug)
                signal.connect(lambda *_a, s=scope: self._mark_dirty(s))

        # Non-map-driven widgets that still belong to a Save button
        if hasattr(self.ui, 'DefaultPassesList'):
            self.ui.DefaultPassesList.itemSelectionChanged.connect(
                lambda: self._mark_dirty("user")
            )
        for widget_name in ("ComfyUIVRAMMode",):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                widget.currentIndexChanged.connect(lambda *_a: self._mark_dirty("global"))
        if hasattr(self.ui, 'GlobalSettingsPathEdit'):
            self.ui.GlobalSettingsPathEdit.textChanged.connect(
                lambda *_a: self._mark_dirty("global")
            )

    def _mark_dirty(self, scope: str):
        """Flag pending unsaved edits for the given scope ('user' or 'global')."""
        # connect_signals() runs eagerly at startup while initialize() (which
        # creates the dirty-tracking state) is deferred to first activation.
        if not self._initialized or getattr(self, "_loading", False):
            return
        # Editing a widget means this tab is on screen. The startup tab is
        # initialized without an on_tab_activated() call, so seed the flag here
        # too or its first switch-away would skip the unsaved prompt.
        self._is_active = True
        if scope == "user":
            if self._user_dirty:
                return
            self._user_dirty = True
        else:
            if self._global_dirty:
                return
            self._global_dirty = True
        self._update_save_button_states()

    def _update_save_button_states(self):
        """Append an asterisk to Save buttons that have pending changes."""
        for button_name, dirty in (
            ("SaveSettingsButton", self._user_dirty),
            ("SaveGlobalSettings", self._global_dirty),
        ):
            button = getattr(self.ui, button_name, None)
            if button is None:
                continue
            base_text, base_tip = self._save_button_texts.setdefault(
                button_name, (button.text(), button.toolTip())
            )
            button.setText(f"{base_text} *" if dirty else base_text)
            button.setToolTip(
                f"{base_tip}\n\nYou have unsaved changes" if dirty else base_tip
            )

    def on_tab_activated(self):
        """Track activation so deactivation can tell a real tab switch apart."""
        self._is_active = True
        self._populate_shot_summary()

    def _populate_shot_summary(self):
        """Fill the shot summary labels (Comp/Render/USD/HIP) on this tab.

        The scan that produces them belongs to the Cleaner tab, so these
        labels used to stay on their "Not Found" placeholders until the user
        happened to visit Cleaner. Ask for the scan here instead; it runs at
        most once per session and reports into these labels via the main
        window's shared widget namespace.
        """
        if not self.app_state.has_shot_context():
            return
        main = getattr(self, 'main_window', None)
        get_tab = getattr(main, 'get_tab', None)
        if not callable(get_tab):
            return
        cleaner = get_tab('cleaner')
        ensure_scanned = getattr(cleaner, 'ensure_scanned', None)
        if callable(ensure_scanned):
            try:
                ensure_scanned()
            except Exception as e:
                logger.debug(f"Could not start shot scan for the summary: {e}")

    def on_tab_deactivated(self):
        """Offer to save pending edits when the user switches away.

        on_tab_deactivated() is called for every non-current tab on each tab
        change, so the _is_active guard keeps the prompt to the single switch
        that actually leaves this tab.
        """
        if not getattr(self, "_is_active", False):
            return
        self._is_active = False

        if not (self._user_dirty or self._global_dirty):
            return
        if self._prompting_unsaved:
            return

        pending = []
        if self._user_dirty:
            pending.append("user settings")
        if self._global_dirty:
            pending.append("global settings")

        self._prompting_unsaved = True
        try:
            if confirm_action(
                "Unsaved Settings",
                f"You have unsaved changes to {' and '.join(pending)}.\n\nSave them now?",
                self.main_window,
                default_yes=True,
            ):
                if self._user_dirty:
                    self._on_save_settings_clicked()
                if self._global_dirty:
                    self._on_save_global_settings()
            else:
                # Discarded — reload from disk so the UI matches what is stored
                self._loading = True
                try:
                    if self._user_dirty:
                        self._load_default_passes_ui()
                        self._load_user_settings_ui()
                    if self._global_dirty:
                        self._load_global_settings_ui()
                finally:
                    self._loading = False
                self._user_dirty = False
                self._global_dirty = False
                self._update_save_button_states()
        finally:
            self._prompting_unsaved = False

    @staticmethod
    def _emit_settings_changed(changed_keys):
        """Notify other tabs that settings changed (no-op for an empty list)."""
        if not changed_keys:
            return
        from core.event_bus import pipeline_events
        pipeline_events.settings_changed.emit(list(changed_keys))

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

        # Insert before adminUsersHeader (so it sits with other global settings)
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
            self.ui.BundleLabel.setProperty("state", "ayon")
        if hasattr(self.ui, 'label_bundle'):
            from icons import get_ayon_icon
            from core.config import UIColors
            self.ui.label_bundle.setProperty("state", "ayon")

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
        """Check if user has notifications about completed or rejected requests.

        The notification store lives on the network share — fetch in a worker
        so a slow share can't freeze the tab during deferred init.
        """
        from core.feature_requests import get_user_notifications

        self.start_worker(
            get_user_notifications,
            self.app_state.user,
            on_result=self._on_user_notifications_loaded,
            on_error=lambda msg, tb="": logger.error(f"Error checking user notifications: {msg}"),
        )

    def _on_user_notifications_loaded(self, notifications):
        """Display fetched notifications (GUI thread via worker signal)."""
        from core.feature_requests import mark_notifications_read

        try:
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

                # Mark as read (network write — keep it off the GUI thread)
                self.start_worker(mark_notifications_read, self.app_state.user)

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
            # Hide the button once the full changelog is on screen. Leaving a
            # disabled button relabelled "Showing Full Changelog" read as a
            # broken control rather than a status line.
            text_edit.setMarkdown(get_changelog())
            full_changelog_btn.setVisible(False)
            dialog.setWindowTitle("Luma Tools - Version History (Full Changelog)")

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
        from core.settings_manager import safe_get_setting

        # Snapshot all values first to avoid partial reads during external changes.
        #
        # Call safe_get_setting WITHOUT an explicit default: passing None
        # overrode the SettingDef default, so any setting the user had never
        # saved read back as None and fell through to whatever the .ui widget
        # happened to ship with — which is not necessarily the declared
        # default (e.g. comfyui_convert_colorspace defaults to True). It also
        # logged a warning per unsaved setting on every visit to this tab.
        values = {}
        for entry in settings_map:
            key = entry[0]
            value = safe_get_setting(key)
            values[key] = value
            if value is None:
                # Registered settings always yield their default, so None here
                # means the key is genuinely unknown — a real wiring mistake.
                logger.warning("Setting '%s' is not in SETTINGS_REGISTRY; using widget default", key)

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

    def _collect_settings_from_map(self, settings_map):
        """Read UI widget values into a ``{setting_key: value}`` dict.

        Each entry in settings_map is a tuple:
            (setting_key, widget_name, widget_type[, load_converter, save_converter])
        Widgets that don't exist in the UI are silently skipped.
        """
        values = {}
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
            values[key] = value
        return values

    def _save_settings_from_map(self, settings_map, extra_values=None):
        """Save UI widget values with ONE file write per scope.

        Previously this looped over set_setting(), and each call did a full
        load-modify-save of the backing JSON — for the global map that meant
        one sequential network write per setting.

        Args:
            settings_map: Declarative settings mapping (see _collect_settings_from_map)
            extra_values: Optional extra ``{setting_key: value}`` written in the
                same batch (e.g. the VRAM booleans derived from the combo)

        Returns:
            list[str]: The setting keys that were written
        """
        from core.settings_manager import set_settings

        values = self._collect_settings_from_map(settings_map)
        if extra_values:
            values.update(extra_values)
        if values:
            set_settings(values)
        return sorted(values.keys())

    # =========================================================================
    # ComfyUI VRAM mode (one combo -> three mutually exclusive boolean settings)
    # =========================================================================

    def _load_vram_mode_ui(self):
        """Set the VRAM combo from the three legacy boolean settings."""
        from core.settings_manager import safe_get_setting

        combo = getattr(self.ui, 'ComfyUIVRAMMode', None)
        if combo is None:
            return

        enabled = [key for key in _VRAM_MODE_KEYS if safe_get_setting(key, False)]
        if len(enabled) > 1:
            logger.warning(
                "Multiple ComfyUI VRAM flags enabled (%s) — these are mutually "
                "exclusive launch flags; using %s (priority low > normal > high)",
                ", ".join(enabled), enabled[0],
            )
        index = _VRAM_MODE_KEYS.index(enabled[0]) + 1 if enabled else 0
        combo.setCurrentIndex(index)

    def _collect_vram_mode_values(self):
        """Return the three boolean VRAM settings derived from the combo."""
        combo = getattr(self.ui, 'ComfyUIVRAMMode', None)
        if combo is None:
            return {}
        index = combo.currentIndex()
        return {
            key: (index == i + 1)
            for i, key in enumerate(_VRAM_MODE_KEYS)
        }

    def _load_user_settings_ui(self):
        """Load user settings into the UI."""
        self._load_settings_from_map(_USER_SETTINGS_MAP)

    def _load_default_passes_ui(self, passes=None):
        """Load default passes into the settings UI.

        Args:
            passes: Optional explicit pass list to preselect. When omitted the
                user's stored default passes are used. Reset-to-defaults passes
                the system defaults here so the change stays pending until the
                user presses Save (same as Add/Remove Pass).
        """
        from core.user_preferences import get_default_passes
        from core.config import REQUIRED_PASSES, DEFAULT_PASSES

        self.ui.DefaultPassesList.clear()

        # Get user's current default passes (or system defaults)
        default_passes = list(passes) if passes is not None else get_default_passes()

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
        from core.settings_manager import get_global_settings_path, safe_get_setting

        # Global settings path (custom display logic)
        global_path = get_global_settings_path()
        self.ui.GlobalSettingsPathEdit.setText(global_path)
        self.ui.globalSettingsCurrentPath.setText(f"Current: {global_path}")

        # ComfyUI mode - set via OptionButtonManager
        self._comfyui_mode_manager.set_value(safe_get_setting("comfyui_mode", "embedded"))

        # Load all mapped settings (paths, checkboxes, spinboxes with converters)
        self._load_settings_from_map(_GLOBAL_SETTINGS_MAP)

        # VRAM mode is derived from three booleans, not map-driven
        self._load_vram_mode_ui()

        self._update_comfyui_python_visibility()

    def _load_admin_users_ui(self):
        """Load admin users list (settings access only)."""
        from core.settings_manager import get_users_with_role

        if not hasattr(self.ui, 'AdminUsersList'):
            return

        self.ui.AdminUsersList.clear()
        for user in get_users_with_role("admin"):
            self.ui.AdminUsersList.addItem(user)

    # Property for backward compatibility
    @property
    def _comfyui_mode(self):
        return self._comfyui_mode_manager.value if hasattr(self, '_comfyui_mode_manager') else "embedded"

    def _on_comfyui_mode_changed(self, value):
        """Handle ComfyUI mode change."""
        self._mark_dirty("global")
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
                self.show_status(f"Pass '{pass_name}' already exists", "warning")
                return

            item = QtWidgets.QListWidgetItem(pass_name)
            item.setToolTip("Select to include this pass by default")
            self.ui.DefaultPassesList.addItem(item)
            item.setSelected(True)
            self._mark_dirty("user")
            logger.info(f"Added custom pass: {pass_name}")

    def _on_remove_pass_clicked(self):
        """Remove selected pass from the default passes list."""
        from core.config import REQUIRED_PASSES

        selected_items = self.ui.DefaultPassesList.selectedItems()
        if not selected_items:
            self.show_status("No passes selected", "warning")
            return

        for item in selected_items:
            pass_name = item.text()
            if pass_name in REQUIRED_PASSES:
                logger.warning(f"Cannot remove required pass: {pass_name}")
                continue

            row = self.ui.DefaultPassesList.row(item)
            self.ui.DefaultPassesList.takeItem(row)
            self._mark_dirty("user")
            logger.info(f"Removed pass: {pass_name}")

    def _on_reset_passes_clicked(self):
        """Reset the default-passes list to system defaults (pending Save).

        Add/Remove Pass only edit the list widget and rely on Save User
        Settings to persist; Reset used to write straight to disk, so the two
        halves of the same panel behaved differently.
        """
        if confirm_action("Reset Default Passes", "Reset to default pass list?", self.main_window):
            from core.config import DEFAULT_PASSES
            self._loading = True
            try:
                self._load_default_passes_ui(DEFAULT_PASSES.copy())
            finally:
                self._loading = False
            self._mark_dirty("user")
            self.show_status("Passes reset - press Save User Settings to apply", "info")
            logger.info("Reset default passes list (pending save)")

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
        logger.info(f"Saved default passes: {selected_passes}")

        # Save all mapped user settings (one file write)
        changed_keys = self._save_settings_from_map(_USER_SETTINGS_MAP)
        changed_keys.append("default_passes")

        # Update status bar log visibility immediately
        if hasattr(self.ui, 'ShowStatusbarLog') and hasattr(self.main_window, 'update_statusbar_log_visibility'):
            self.main_window.update_statusbar_log_visibility(self.ui.ShowStatusbarLog.isChecked())

        self._user_dirty = False
        self._update_save_button_states()
        self._emit_settings_changed(changed_keys)

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
            # Deleting thousands of cached files synchronously froze the UI —
            # run the sweep in a worker and refresh the gallery afterwards
            self.update_status_with_spinner("Clearing thumbnail cache...", self.StatusColors.INFO)
            self.start_worker(
                _clear_thumbnail_caches,
                on_result=self._on_thumbnails_cleared,
                on_error=lambda msg, tb="": self.on_worker_error(msg, tb, "Thumbnails"),
            )

    def _on_thumbnails_cleared(self, count):
        """Handle thumbnail cache sweep completion (GUI thread)."""
        logger.info(f"Cleared {count} cached thumbnail files")

        # Notify gallery tab to refresh via event bus
        from core.event_bus import pipeline_events
        pipeline_events.gallery_refresh_requested.emit(True)  # force=True

        self.update_status_with_spinner("Thumbnail cache cleared", self.StatusColors.SUCCESS, start=False)

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
        from core.settings_manager import set_global_settings_path

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

        # Save all mapped global settings plus the ComfyUI mode and the three
        # VRAM booleans derived from the combo — one batched write, not one
        # network round-trip per key.
        extra = {"comfyui_mode": self._comfyui_mode}
        extra.update(self._collect_vram_mode_values())
        changed_keys = self._save_settings_from_map(_GLOBAL_SETTINGS_MAP, extra_values=extra)

        # Clear cached paths so logging and other modules pick up the new values
        try:
            from core.logging_utils import clear_path_cache
            clear_path_cache()
        except ImportError:
            pass

        # Drop cached deadline poll interval so the new value takes effect
        # without a restart.
        try:
            from ui.tabs.comfyui.polling import _invalidate_poll_interval_cache
            _invalidate_poll_interval_cache()
        except ImportError:
            pass

        self._global_dirty = False
        self._update_save_button_states()
        self._emit_settings_changed(changed_keys)

        self.pulse_button(self.ui.SaveGlobalSettings)
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
            self._emit_settings_changed(["admin_users"])
            self.show_status(f"Added admin user: {username}", "success")
            logger.info(f"Added admin user: {username}")

    def _on_remove_admin_user(self):
        """Remove selected admin user."""
        from core.settings_manager import remove_user_from_role

        selected_items = self.ui.AdminUsersList.selectedItems()
        if not selected_items:
            logger.warning("No admin user selected for removal")
            self.show_status("No admin user selected", "warning")
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
        self._emit_settings_changed(["admin_users"])
        self.show_status(f"Removed admin user: {username}", "success")

    def _load_feature_request_ui(self):
        """Configure feature request buttons based on user role."""
        # Submit button is visible to everyone
        if hasattr(self.ui, 'submitFeatureRequestButton'):
            self.ui.submitFeatureRequestButton.setVisible(True)

        # View button only visible to admins
        if hasattr(self.ui, 'viewFeatureRequestsButton'):
            is_admin = self.app_state.is_admin
            self.ui.viewFeatureRequestsButton.setVisible(is_admin)

            # Check for unread requests (admins only). The request store is
            # on the network share — fetch in a worker so deferred init
            # doesn't block the GUI thread on a slow share.
            if is_admin:
                from core.feature_requests import get_unread_feature_request_count
                self.start_worker(
                    get_unread_feature_request_count,
                    self.app_state.user,
                    on_result=self._on_unread_request_count_loaded,
                    on_error=lambda msg, tb="": logger.error(
                        f"Error checking unread feature requests: {msg}"
                    ),
                )

    def _on_unread_request_count_loaded(self, unread_count):
        """Show the unread-requests badge (GUI thread via worker signal)."""
        if not unread_count or not hasattr(self.ui, 'viewFeatureRequestsButton'):
            return
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

        # Inline validation message — validating after the dialog closed used
        # to throw away everything the user typed.
        from core.config import UIColors
        validation_label = QLabel("Please enter a description before submitting.")
        validation_label.setProperty("state", "warning")
        validation_label.setVisible(False)
        layout.addWidget(validation_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        def _try_accept():
            if description_edit.toPlainText().strip():
                validation_label.setVisible(False)
                dialog.accept()
            else:
                validation_label.setVisible(True)
                description_edit.setFocus()

        button_box.accepted.connect(_try_accept)
        button_box.rejected.connect(dialog.reject)
        description_edit.textChanged.connect(
            lambda: validation_label.setVisible(False)
        )
        layout.addWidget(button_box)

        # Reopen the same dialog on submit failure so the typed text survives
        while dialog.exec() == QDialog.Accepted:
            category = category_combo.currentText()
            description = description_edit.toPlainText().strip()

            username = self.app_state.user
            if append_feature_request(category, description, username):
                show_info(
                    "Request Submitted",
                    "Your feature request has been submitted successfully.\nAdmins will be notified.",
                    self.main_window
                )
                self._notify_admins_of_new_request()
                return

            show_error(
                "Submission Failed",
                "Failed to submit feature request. Your text has been kept — "
                "try again, or cancel and contact an admin.",
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

        # Show dialog (Qt6 spelling — the Accepted branch was a no-op so we
        # don't bother capturing the return value).
        dialog = FeatureRequestDialog(
            parent=self.main_window,
            user=self.app_state.user,
            is_admin=self.app_state.is_admin
        )
        dialog.exec()

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
            self._emit_settings_changed(["hdri_list"])
            self.show_status(f"Added HDRI: {name}", "success")
            logger.info(f"Added HDRI: {name}")
        except Exception as e:
            show_warning("Error", f"Failed to add HDRI: {e}", self.main_window)

    def _on_remove_hdri(self):
        """Remove selected HDRI from the global list."""
        from core.settings_manager import remove_hdri_from_list

        if not hasattr(self.ui, 'HdriListWidget'):
            return

        selected_items = self.ui.HdriListWidget.selectedItems()
        if not selected_items:
            logger.warning("No HDRI selected for removal")
            self.show_status("No HDRI selected", "warning")
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
                    logger.info(f"Removed HDRI: {name}")

            self._load_hdri_list_ui()
            self._emit_settings_changed(["hdri_list"])
            self.show_status(f"Removed {len(hdri_names)} HDRI(s)", "success")
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
        self._emit_settings_changed(["comfyui_preset_categories"])
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
            self.show_status("No category selected", "warning")
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
            self._emit_settings_changed(["comfyui_preset_categories"])
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
        self._emit_settings_changed(["comfyui_preset_categories"])

        # Reload and re-select
        self._load_categories_ui()
        for i in range(self.ui.CategoriesList.count()):
            if self.ui.CategoriesList.item(i).text() == name:
                self.ui.CategoriesList.item(i).setSelected(True)
                self.ui.CategoriesList.setCurrentRow(i)
                break
