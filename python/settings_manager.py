"""
Settings manager for Luma Tools.

Handles saving and loading user preferences.
"""

import os
import json
from config import USER_SETTINGS_DIR, USER_SETTINGS_FILE, DEFAULT_PASSES, REQUIRED_PASSES


def ensure_settings_dir():
    """Ensure settings directory exists."""
    if not os.path.exists(USER_SETTINGS_DIR):
        os.makedirs(USER_SETTINGS_DIR)
        print(f"Created settings directory: {USER_SETTINGS_DIR}")


def load_user_settings():
    """
    Load user settings from file.

    Returns:
        dict: User settings dictionary with default values if file doesn't exist
    """
    default_settings = {
        "default_passes": DEFAULT_PASSES.copy()
    }

    if not os.path.exists(USER_SETTINGS_FILE):
        print("No user settings file found, using defaults")
        return default_settings

    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            print(f"Loaded user settings from: {USER_SETTINGS_FILE}")

            # Ensure default_passes key exists
            if "default_passes" not in settings:
                settings["default_passes"] = DEFAULT_PASSES.copy()

            return settings
    except Exception as e:
        print(f"Error loading user settings: {e}")
        return default_settings


def save_user_settings(settings):
    """
    Save user settings to file.

    Args:
        settings: Dictionary containing user settings
    """
    ensure_settings_dir()

    try:
        with open(USER_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
            print(f"Saved user settings to: {USER_SETTINGS_FILE}")
    except Exception as e:
        print(f"Error saving user settings: {e}")


def get_default_passes():
    """
    Get the user's configured default passes.

    Returns:
        list: List of default pass names (excludes REQUIRED_PASSES)
    """
    settings = load_user_settings()
    return settings.get("default_passes", DEFAULT_PASSES.copy())


def get_all_default_passes():
    """
    Get all passes that should be selected by default.

    Returns:
        list: List of all default passes including REQUIRED_PASSES
    """
    user_passes = get_default_passes()
    # Combine required passes and user's default passes (avoid duplicates)
    all_passes = REQUIRED_PASSES.copy()
    for pass_name in user_passes:
        if pass_name not in all_passes:
            all_passes.append(pass_name)
    return all_passes


def set_default_passes(passes_list):
    """
    Set the user's default passes.

    Args:
        passes_list: List of pass names to set as defaults
    """
    settings = load_user_settings()
    settings["default_passes"] = passes_list
    save_user_settings(settings)
