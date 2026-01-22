"""Unit tests for config module."""
import sys
import os

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))


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
    test_ui_colors()
    test_ui_styles()
    test_app_version()
    test_paths_defined()
    print("All config tests passed!")
