"""Tests for core.settings_manager — settings registry, get/set, validators, roles."""

import json
import os
import threading
from unittest.mock import patch, MagicMock

import pytest

from core.settings_manager import (
    SettingDef,
    SETTINGS_REGISTRY,
    get_setting,
    set_setting,
    safe_get_setting,
    safe_set_setting,
    clear_settings_cache,
    is_user_in_role,
    _validate_comfyui_mode,
    _validate_timeout,
    _validate_server_wait_timeout,
    _validate_server_behavior,
    _validate_stacking_mode,
    _validate_deadline_poll_interval,
    _get_role_settings_key,
)


# ============================================================================
# Validators
# ============================================================================

class TestValidateComfyuiMode:
    def test_valid_modes(self):
        for mode in ("embedded", "portable", "standalone"):
            assert _validate_comfyui_mode(mode) == mode

    def test_invalid_returns_default(self):
        assert _validate_comfyui_mode("invalid") == "embedded"
        assert _validate_comfyui_mode("") == "embedded"
        assert _validate_comfyui_mode(None) == "embedded"


class TestValidateTimeout:
    def test_within_range(self):
        assert _validate_timeout(3600) == 3600
        assert _validate_timeout(60) == 60
        assert _validate_timeout(86400) == 86400

    def test_clamps_low(self):
        assert _validate_timeout(1) == 60
        assert _validate_timeout(0) == 60

    def test_clamps_high(self):
        assert _validate_timeout(100000) == 86400

    def test_invalid_type_returns_min(self):
        assert _validate_timeout("bad") == 60
        assert _validate_timeout(None) == 60


class TestValidateServerWaitTimeout:
    def test_within_range(self):
        assert _validate_server_wait_timeout(300) == 300

    def test_clamps(self):
        assert _validate_server_wait_timeout(10) == 30
        assert _validate_server_wait_timeout(5000) == 3600

    def test_invalid(self):
        assert _validate_server_wait_timeout("x") == 30


class TestValidateServerBehavior:
    def test_valid(self):
        assert _validate_server_behavior("fail") == "fail"
        assert _validate_server_behavior("wait") == "wait"

    def test_invalid(self):
        assert _validate_server_behavior("retry") == "fail"


class TestValidateStackingMode:
    def test_valid(self):
        for mode in ("job", "groups", "both", "grid"):
            assert _validate_stacking_mode(mode) == mode

    def test_invalid(self):
        assert _validate_stacking_mode("none") == "job"


class TestValidateDeadlinePollInterval:
    def test_valid(self):
        assert _validate_deadline_poll_interval(5) == 5

    def test_clamps(self):
        assert _validate_deadline_poll_interval(0) == 1
        assert _validate_deadline_poll_interval(100) == 60

    def test_invalid(self):
        assert _validate_deadline_poll_interval(None) == 5


# ============================================================================
# SettingDef
# ============================================================================

class TestSettingDef:
    def test_basic_creation(self):
        s = SettingDef("my_key", "default_val", "user")
        assert s.key == "my_key"
        assert s.default == "default_val"
        assert s.scope == "user"
        assert s.validator is None

    def test_with_validator(self):
        s = SettingDef("key", "embedded", "global", _validate_comfyui_mode)
        assert s.validator is _validate_comfyui_mode

    def test_defaults(self):
        s = SettingDef("key")
        assert s.default is None
        assert s.scope == "global"


# ============================================================================
# Registry coverage
# ============================================================================

class TestSettingsRegistry:
    def test_registry_is_populated(self):
        assert len(SETTINGS_REGISTRY) > 30

    def test_all_entries_are_setting_defs(self):
        for key, defn in SETTINGS_REGISTRY.items():
            assert isinstance(defn, SettingDef), f"{key} is not a SettingDef"
            assert defn.key == key

    def test_scopes_are_valid(self):
        for key, defn in SETTINGS_REGISTRY.items():
            assert defn.scope in ("global", "user"), f"{key} has invalid scope: {defn.scope}"


# ============================================================================
# get_setting / set_setting
# ============================================================================

class TestGetSetting:
    """Test get_setting with mocked file I/O.

    Note: SettingsAccessor captures load_* function refs at import time,
    so we patch the accessor's _load_fn directly via patch.object.
    """

    def test_returns_stored_value(self):
        import core.settings_manager as sm
        clear_settings_cache()
        with patch.object(sm._global_settings, "_load_fn", return_value={"comfyui_path": "/mock/path"}):
            assert get_setting("comfyui_path") == "/mock/path"

    def test_returns_default_when_not_in_file(self):
        import core.settings_manager as sm
        clear_settings_cache()
        with patch.object(sm._global_settings, "_load_fn", return_value={}):
            assert get_setting("comfyui_path") == ""

    def test_raises_for_unknown_key(self):
        with pytest.raises(KeyError, match="Unknown setting"):
            get_setting("this_setting_does_not_exist")

    def test_unknown_key_with_default_does_not_raise(self):
        result = get_setting("this_setting_does_not_exist", default="fallback")
        assert result == "fallback"


class TestSetSetting:
    """Test set_setting with mocked file I/O."""

    def test_set_known_setting(self):
        import core.settings_manager as sm
        clear_settings_cache()
        mock_save = MagicMock()
        with patch.object(sm._global_settings, "_load_fn", return_value={}), \
             patch("core.settings_manager._save_settings_unlocked", mock_save):
            set_setting("comfyui_path", "/new/path", verbose=False)
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][1]  # (settings_type, settings)
            assert saved["comfyui_path"] == "/new/path"

    def test_raises_for_unknown_key(self):
        with pytest.raises(KeyError):
            set_setting("unknown_setting_xyz", "value")

    def test_validator_applied(self):
        import core.settings_manager as sm
        clear_settings_cache()
        mock_save = MagicMock()
        with patch.object(sm._global_settings, "_load_fn", return_value={}), \
             patch("core.settings_manager._save_settings_unlocked", mock_save):
            set_setting("comfyui_mode", "INVALID", verbose=False)
            saved = mock_save.call_args[0][1]  # (settings_type, settings)
            assert saved["comfyui_mode"] == "embedded"  # validator returned default


# ============================================================================
# safe_get_setting / safe_set_setting
# ============================================================================

class TestSafeGetSetting:
    def test_unknown_key_returns_explicit_default(self):
        assert safe_get_setting("nonexistent_key_xyz", False) is False

    def test_unknown_key_no_default_returns_none(self):
        assert safe_get_setting("nonexistent_key_xyz") is None

    def test_returns_stored_value(self):
        import core.settings_manager as sm
        clear_settings_cache()
        with patch.object(sm._user_settings, "_load_fn", return_value={"show_tray_notifications": False}):
            assert safe_get_setting("show_tray_notifications") is False


class TestSafeSetSetting:
    def test_returns_true_on_success(self):
        import core.settings_manager as sm
        clear_settings_cache()
        mock_save = MagicMock()
        with patch.object(sm._user_settings, "_load_fn", return_value={}), \
             patch.object(sm._user_settings, "_save_fn", mock_save):
            assert safe_set_setting("show_tray_notifications", False) is True

    def test_returns_false_for_unknown_key(self):
        assert safe_set_setting("nonexistent_key", "val") is False


# ============================================================================
# Role helpers
# ============================================================================

class TestGetRoleSettingsKey:
    def test_admin(self):
        assert _get_role_settings_key("admin") == "admin_users"

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Unknown role"):
            _get_role_settings_key("viewer")


class TestIsUserInRole:
    def test_case_insensitive_match(self):
        import core.settings_manager as sm
        clear_settings_cache()
        with patch.object(sm._global_settings, "_load_fn",
                          return_value={"admin_users": ["Alice", "Bob"]}):
            assert is_user_in_role("alice", "admin") is True
            assert is_user_in_role("ALICE", "admin") is True

    def test_not_in_role(self):
        import core.settings_manager as sm
        clear_settings_cache()
        with patch.object(sm._global_settings, "_load_fn",
                          return_value={"admin_users": ["Alice"]}):
            assert is_user_in_role("Charlie", "admin") is False

    def test_empty_username(self):
        assert is_user_in_role("", "admin") is False
        assert is_user_in_role(None, "admin") is False


# ============================================================================
# Cache behaviour
# ============================================================================

class TestClearSettingsCache:
    def test_cache_cleared(self):
        import core.settings_manager as sm
        mock_global = MagicMock(return_value={})
        mock_user = MagicMock(return_value={})
        clear_settings_cache()
        with patch.object(sm._global_settings, "_load_fn", mock_global), \
             patch.object(sm._user_settings, "_load_fn", mock_user):
            safe_get_setting("comfyui_path")
            safe_get_setting("show_tray_notifications")
            assert mock_global.call_count >= 1
            assert mock_user.call_count >= 1
