"""Core infrastructure for Luma Tools."""

# Re-export commonly used items for convenience
# NOTE: Wildcard imports are intentional here - this is a re-export convenience module
# that consolidates imports from multiple core modules for easier use throughout the codebase.
from .config import *  # noqa: F403, F401
from .settings_manager import (
    get_setting, set_setting,
    load_user_settings, save_user_settings,
    load_global_settings, save_global_settings,
    get_users_with_role, is_user_in_role, add_user_to_role, remove_user_from_role,
)
from .user_preferences import (
    get_window_state, save_window_state,
    get_tab_order, save_tab_order,
    get_default_passes, set_default_passes, get_all_default_passes,
    get_last_opened_version, set_last_opened_version, is_new_version,
    record_workflow_execution_time, get_workflow_estimated_time_per_frame,
    get_last_browse_directory, set_last_browse_directory,
)
from .feature_requests import (
    append_feature_request, get_feature_requests,
    mark_request_completed, get_user_notifications,
    mark_notifications_read, get_unread_feature_request_count,
    mark_feature_requests_as_read,
)
from .state_manager import app_state
from .utils import *  # noqa: F403, F401
from .import_utils import safe_import, safe_import_multiple
