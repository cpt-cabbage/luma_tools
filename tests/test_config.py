"""Unit tests for config module."""
import sys
import os
import re

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))


class TestUIColors:
    """Tests for UIColors class."""

    def test_background_colors_exist(self):
        """Test background colors exist and are strings."""
        from core.config import UIColors

        assert isinstance(UIColors.BG_DARK, str)
        assert isinstance(UIColors.BG_DARK_ALT, str)
        assert isinstance(UIColors.BG_MEDIUM, str)
        assert isinstance(UIColors.BG_MEDIUM_ALT, str)
        assert isinstance(UIColors.BG_LIGHT, str)
        assert isinstance(UIColors.BG_LIGHT_ALT, str)
        assert isinstance(UIColors.BG_HOVER, str)

    def test_text_colors_exist(self):
        """Test text colors exist and are strings."""
        from core.config import UIColors

        assert isinstance(UIColors.TEXT_WHITE, str)
        assert isinstance(UIColors.TEXT_LIGHT, str)
        assert isinstance(UIColors.TEXT_SECONDARY, str)
        assert isinstance(UIColors.TEXT_MUTED, str)
        assert isinstance(UIColors.TEXT_DARK_MUTED, str)

    def test_accent_colors_exist(self):
        """Test accent colors exist."""
        from core.config import UIColors

        assert isinstance(UIColors.ACCENT_BLUE, str)
        assert isinstance(UIColors.ACCENT_BLUE_HOVER, str)
        assert isinstance(UIColors.ACCENT_BLUE_ALT, str)

    def test_status_colors_exist(self):
        """Test status colors exist."""
        from core.config import UIColors

        assert isinstance(UIColors.SUCCESS, str)
        assert isinstance(UIColors.SUCCESS_HOVER, str)
        assert isinstance(UIColors.ERROR, str)
        assert isinstance(UIColors.ERROR_ALT, str)
        assert isinstance(UIColors.WARNING, str)
        assert isinstance(UIColors.WARNING_DARK, str)

    def test_border_colors_exist(self):
        """Test border colors exist."""
        from core.config import UIColors

        assert isinstance(UIColors.BORDER, str)
        assert isinstance(UIColors.BORDER_FOCUS, str)

    def test_group_colors_exist(self):
        """Test group colors palette exists."""
        from core.config import UIColors

        assert isinstance(UIColors.GROUP_COLORS, list)
        assert len(UIColors.GROUP_COLORS) > 0

    def test_colors_are_valid_hex(self):
        """Test colors are valid hex format."""
        from core.config import UIColors

        hex_pattern = re.compile(r'^#[0-9a-fA-F]{6}$')

        # Test a sample of colors
        colors_to_test = [
            UIColors.BG_DARK, UIColors.BG_MEDIUM, UIColors.BG_LIGHT,
            UIColors.TEXT_WHITE, UIColors.TEXT_LIGHT,
            UIColors.ACCENT_BLUE, UIColors.SUCCESS, UIColors.ERROR, UIColors.WARNING
        ]

        for color in colors_to_test:
            assert hex_pattern.match(color), f"Invalid hex color: {color}"

    def test_group_colors_are_valid_hex(self):
        """Test all group colors are valid hex."""
        from core.config import UIColors

        hex_pattern = re.compile(r'^#[0-9a-fA-F]{6}$')

        for color in UIColors.GROUP_COLORS:
            assert hex_pattern.match(color), f"Invalid group color: {color}"


class TestUIStyles:
    """Tests for UIStyles class."""

    def test_label_styles_exist(self):
        """Test label styles exist and are strings."""
        from core.config import UIStyles

        assert isinstance(UIStyles.LABEL_LIGHT, str)
        assert isinstance(UIStyles.LABEL_MUTED, str)
        assert isinstance(UIStyles.LABEL_SECONDARY, str)
        assert isinstance(UIStyles.LABEL_ITALIC_MUTED, str)
        assert isinstance(UIStyles.LABEL_SMALL_MUTED, str)
        assert isinstance(UIStyles.LABEL_PATH, str)

    def test_button_styles_exist(self):
        """Test button styles exist."""
        from core.config import UIStyles

        assert isinstance(UIStyles.BUTTON_PRIMARY, str)
        assert isinstance(UIStyles.BUTTON_SUCCESS, str)
        assert isinstance(UIStyles.BUTTON_SECONDARY, str)
        assert isinstance(UIStyles.BUTTON_DANGER, str)

    def test_button_styles_are_valid_css(self):
        """Test button styles contain valid CSS properties."""
        from core.config import UIStyles

        for style in [UIStyles.BUTTON_PRIMARY, UIStyles.BUTTON_SUCCESS,
                      UIStyles.BUTTON_SECONDARY, UIStyles.BUTTON_DANGER]:
            assert 'QPushButton' in style
            assert 'background-color' in style
            assert 'color' in style

    def test_button_primary_has_hover_states(self):
        """Test button primary has hover and pressed states."""
        from core.config import UIStyles

        assert 'QPushButton:hover' in UIStyles.BUTTON_PRIMARY
        assert 'QPushButton:pressed' in UIStyles.BUTTON_PRIMARY

    def test_scroll_area_style_exists(self):
        """Test scroll area style exists."""
        from core.config import UIStyles

        assert isinstance(UIStyles.SCROLL_AREA, str)
        assert 'QScrollArea' in UIStyles.SCROLL_AREA

    def test_combobox_style_exists(self):
        """Test combobox style exists."""
        from core.config import UIStyles

        assert isinstance(UIStyles.COMBOBOX, str)
        assert 'QComboBox' in UIStyles.COMBOBOX

    def test_dialog_style_exists(self):
        """Test dialog style exists."""
        from core.config import UIStyles

        assert isinstance(UIStyles.DIALOG, str)
        assert 'QDialog' in UIStyles.DIALOG


class TestAppVersion:
    """Tests for APP_VERSION."""

    def test_version_is_string(self):
        """Test APP_VERSION is a string."""
        from core.config import APP_VERSION

        assert isinstance(APP_VERSION, str)

    def test_version_not_empty(self):
        """Test APP_VERSION is not empty."""
        from core.config import APP_VERSION

        assert len(APP_VERSION) > 0


class TestPaths:
    """Tests for path constants."""

    def test_ui_file_path_defined(self):
        """Test UI_FILE_PATH is defined."""
        from core.config import UI_FILE_PATH

        assert isinstance(UI_FILE_PATH, str)
        assert 'main_window.ui' in UI_FILE_PATH

    def test_ui_tabs_dir_defined(self):
        """Test UI_TABS_DIR is defined."""
        from core.config import UI_TABS_DIR

        assert isinstance(UI_TABS_DIR, str)
        assert 'tabs' in UI_TABS_DIR

    def test_icon_path_defined(self):
        """Test ICON_PATH is defined."""
        from core.config import ICON_PATH

        assert isinstance(ICON_PATH, str)
        assert '.png' in ICON_PATH

    def test_user_settings_paths_defined(self):
        """Test user settings paths are defined."""
        from core.config import USER_SETTINGS_DIR, USER_SETTINGS_FILE

        assert isinstance(USER_SETTINGS_DIR, str)
        assert isinstance(USER_SETTINGS_FILE, str)
        assert '.luma_tools' in USER_SETTINGS_DIR
        assert 'settings.json' in USER_SETTINGS_FILE


class TestDeadlineDefaults:
    """Tests for Deadline default settings."""

    def test_deadline_pool(self):
        """Test DEADLINE_POOL is defined."""
        from core.config import DEADLINE_POOL

        assert isinstance(DEADLINE_POOL, str)
        assert len(DEADLINE_POOL) > 0

    def test_deadline_group(self):
        """Test DEADLINE_GROUP is defined."""
        from core.config import DEADLINE_GROUP

        assert isinstance(DEADLINE_GROUP, str)

    def test_deadline_priorities(self):
        """Test DEADLINE_PRIORITY values are integers."""
        from core.config import (
            DEADLINE_PRIORITY_BUILD,
            DEADLINE_PRIORITY_PUBLISH,
            DEADLINE_PRIORITY_COMFYUI
        )

        assert isinstance(DEADLINE_PRIORITY_BUILD, int)
        assert isinstance(DEADLINE_PRIORITY_PUBLISH, int)
        assert isinstance(DEADLINE_PRIORITY_COMFYUI, int)

    def test_deadline_chunk_size(self):
        """Test DEADLINE_CHUNK_SIZE is a positive integer."""
        from core.config import DEADLINE_CHUNK_SIZE

        assert isinstance(DEADLINE_CHUNK_SIZE, int)
        assert DEADLINE_CHUNK_SIZE > 0


class TestAyonSettings:
    """Tests for AYON default settings."""

    def test_ayon_product_type(self):
        """Test AYON_PRODUCT_TYPE is defined."""
        from core.config import AYON_PRODUCT_TYPE

        assert isinstance(AYON_PRODUCT_TYPE, str)

    def test_ayon_colorspace(self):
        """Test AYON_COLORSPACE is defined."""
        from core.config import AYON_COLORSPACE

        assert isinstance(AYON_COLORSPACE, str)
        assert 'ACES' in AYON_COLORSPACE

    def test_ayon_default_fps(self):
        """Test AYON_DEFAULT_FPS is a positive number."""
        from core.config import AYON_DEFAULT_FPS

        assert isinstance(AYON_DEFAULT_FPS, float)
        assert AYON_DEFAULT_FPS > 0

    def test_ayon_default_resolution(self):
        """Test default resolution is defined."""
        from core.config import AYON_DEFAULT_WIDTH, AYON_DEFAULT_HEIGHT

        assert isinstance(AYON_DEFAULT_WIDTH, int)
        assert isinstance(AYON_DEFAULT_HEIGHT, int)
        assert AYON_DEFAULT_WIDTH > 0
        assert AYON_DEFAULT_HEIGHT > 0


class TestFilePatterns:
    """Tests for file patterns and extensions."""

    def test_comp_extensions(self):
        """Test COMP_EXTENSIONS is a list."""
        from core.config import COMP_EXTENSIONS

        assert isinstance(COMP_EXTENSIONS, list)
        assert '.nk' in COMP_EXTENSIONS

    def test_exr_extension(self):
        """Test EXR_EXTENSION is defined."""
        from core.config import EXR_EXTENSION

        assert EXR_EXTENSION == '.exr'

    def test_comfyui_supported_extensions(self):
        """Test COMFYUI_SUPPORTED_EXTENSIONS is a list."""
        from core.config import COMFYUI_SUPPORTED_EXTENSIONS

        assert isinstance(COMFYUI_SUPPORTED_EXTENSIONS, list)
        assert '.png' in COMFYUI_SUPPORTED_EXTENSIONS
        assert '.jpg' in COMFYUI_SUPPORTED_EXTENSIONS

    def test_comfyui_output_extensions(self):
        """Test COMFYUI_OUTPUT_EXTENSIONS is a comprehensive list."""
        from core.config import COMFYUI_OUTPUT_EXTENSIONS

        assert isinstance(COMFYUI_OUTPUT_EXTENSIONS, list)
        # Check for image formats
        assert '.png' in COMFYUI_OUTPUT_EXTENSIONS
        assert '.jpg' in COMFYUI_OUTPUT_EXTENSIONS
        # Check for 3D formats
        assert '.fbx' in COMFYUI_OUTPUT_EXTENSIONS
        assert '.obj' in COMFYUI_OUTPUT_EXTENSIONS
        # Check for video formats
        assert '.mp4' in COMFYUI_OUTPUT_EXTENSIONS


class TestExcludedChannels:
    """Tests for channel filtering."""

    def test_excluded_channels_defined(self):
        """Test EXCLUDED_CHANNELS is defined."""
        from core.config import EXCLUDED_CHANNELS

        assert isinstance(EXCLUDED_CHANNELS, list)

    def test_normal_channels_defined(self):
        """Test NORMAL_CHANNELS is defined."""
        from core.config import NORMAL_CHANNELS

        assert isinstance(NORMAL_CHANNELS, list)
        assert len(NORMAL_CHANNELS) == 3  # x, y, z


class TestRequiredPasses:
    """Tests for pass configuration."""

    def test_required_passes(self):
        """Test REQUIRED_PASSES is defined."""
        from core.config import REQUIRED_PASSES

        assert isinstance(REQUIRED_PASSES, list)
        assert 'Beauty' in REQUIRED_PASSES

    def test_default_passes(self):
        """Test DEFAULT_PASSES is defined."""
        from core.config import DEFAULT_PASSES

        assert isinstance(DEFAULT_PASSES, list)
        assert len(DEFAULT_PASSES) > 0


class TestEnvironmentFlags:
    """Tests for environment availability flags."""

    def test_ayon_env_available_is_boolean(self):
        """Test AYON_ENV_AVAILABLE is a boolean."""
        from core.config import AYON_ENV_AVAILABLE

        assert isinstance(AYON_ENV_AVAILABLE, bool)


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_ocio_config_returns_string_or_none(self):
        """Test get_ocio_config returns string or None."""
        from core.config import get_ocio_config

        result = get_ocio_config()
        assert result is None or isinstance(result, str)

    def test_get_ayon_bundle_returns_string(self):
        """Test get_ayon_bundle returns a string."""
        from core.config import get_ayon_bundle

        result = get_ayon_bundle()
        assert isinstance(result, str)


# Backward compatibility - original test functions
def test_ui_colors():
    """Test UIColors class has expected attributes."""
    from core.config import UIColors

    # Test background colors exist and are strings
    assert isinstance(UIColors.BG_DARK, str)
    assert isinstance(UIColors.BG_MEDIUM, str)
    assert isinstance(UIColors.BG_LIGHT, str)
    assert isinstance(UIColors.BG_HOVER, str)

    # Test text colors
    assert isinstance(UIColors.TEXT_WHITE, str)
    assert isinstance(UIColors.TEXT_LIGHT, str)
    assert isinstance(UIColors.TEXT_SECONDARY, str)
    assert isinstance(UIColors.TEXT_MUTED, str)

    # Test accent colors
    assert isinstance(UIColors.ACCENT_BLUE, str)

    # Test status colors
    assert isinstance(UIColors.SUCCESS, str)
    assert isinstance(UIColors.ERROR, str)
    assert isinstance(UIColors.WARNING, str)

    # Test they are valid hex colors
    assert UIColors.BG_DARK.startswith('#')
    assert UIColors.ACCENT_BLUE.startswith('#')


def test_ui_styles():
    """Test UIStyles class has expected attributes."""
    from core.config import UIStyles

    # Test label styles
    assert isinstance(UIStyles.LABEL_LIGHT, str)
    assert isinstance(UIStyles.LABEL_MUTED, str)

    # Test button styles are valid stylesheet strings
    assert isinstance(UIStyles.BUTTON_PRIMARY, str)
    assert isinstance(UIStyles.BUTTON_SUCCESS, str)
    assert isinstance(UIStyles.BUTTON_SECONDARY, str)
    assert isinstance(UIStyles.BUTTON_DANGER, str)

    # Test they contain expected CSS
    assert 'background-color' in UIStyles.BUTTON_PRIMARY
    assert 'QPushButton' in UIStyles.BUTTON_PRIMARY


def test_app_version():
    """Test APP_VERSION is loaded."""
    from core.config import APP_VERSION

    assert isinstance(APP_VERSION, str)
    # Should not be "unknown" if version.json exists
    # (may be unknown in CI without the file)


def test_paths_defined():
    """Test that path constants are defined."""
    from core.config import (
        UI_FILE_PATH,
        UI_TABS_DIR,
        ICON_PATH,
        USER_SETTINGS_DIR,
        USER_SETTINGS_FILE,
    )

    assert isinstance(UI_FILE_PATH, str)
    assert isinstance(UI_TABS_DIR, str)
    assert isinstance(ICON_PATH, str)
    assert isinstance(USER_SETTINGS_DIR, str)
    assert isinstance(USER_SETTINGS_FILE, str)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
