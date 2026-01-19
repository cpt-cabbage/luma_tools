"""
Feature requests management for Luma Tools.

Handles feature request submission, retrieval, completion tracking, and notifications.
Each user has their own requests file stored in the ComfyUI network output folder.
"""

import os
import json
from typing import Dict, Any, List
from datetime import datetime
from .settings_manager import (
    get_setting, set_setting,
    load_user_settings, save_user_settings,
    get_global_settings_path
)


# ============================================================================
# FEATURE REQUESTS BASE PATH
# ============================================================================

def get_feature_requests_base_dir() -> str:
    """Get base path for feature requests (ComfyUI network output path)."""
    network_path = get_setting("comfyui_network_output_path")
    if not network_path:
        # Fallback to global settings if network path not configured
        return os.path.join(get_global_settings_path(), "feature_requests")
    return os.path.join(network_path, ".feature_requests")


def get_user_feature_requests_file(username: str) -> str:
    """Get path to user's feature requests file.

    Each user has their own requests file in the ComfyUI network output folder.
    Files are stored in a hidden .feature_requests directory to avoid showing in gallery.

    Args:
        username: Username

    Returns:
        Full path to user's requests file
    """
    base_dir = get_feature_requests_base_dir()
    return os.path.join(base_dir, f"{username}_requests.json")


# ============================================================================
# FEATURE REQUEST MANAGEMENT
# ============================================================================

def append_feature_request(category: str, description: str, username: str) -> bool:
    """Add a feature request to the user's requests file.

    Each user has their own JSON file containing an array of requests.

    Args:
        category: Feature, Bug, Enhancement, or Question
        description: Detailed description of the request
        username: Username of the requester

    Returns:
        True on success, False on failure
    """
    try:
        file_path = get_user_feature_requests_file(username)

        # Ensure the directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Format timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Generate unique ID for request (timestamp + microseconds)
        request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Create new request
        new_request = {
            'id': request_id,
            'timestamp': timestamp,
            'username': username,
            'category': category,
            'description': description,
            'completed': False,
            'completed_by': None,
            'completed_at': None
        }

        # Read existing requests
        requests = []
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    requests = json.load(f)
            except Exception as e:
                print(f"Error reading existing requests: {e}")
                requests = []

        # Append new request
        requests.append(new_request)

        # Write back to file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(requests, f, indent=2, ensure_ascii=False)

        print(f"Feature request created: {category} by {username}")
        return True

    except Exception as e:
        print(f"Error creating feature request: {e}")
        return False


def get_feature_requests() -> List[Dict[str, str]]:
    """Read and parse all feature requests from all user files.

    Returns:
        List of dicts with keys: timestamp, username, category, description
        Sorted by timestamp (oldest first)
    """
    try:
        base_dir = get_feature_requests_base_dir()

        # Check if directory exists
        if not os.path.exists(base_dir):
            return []

        # Read all user request files
        all_requests = []
        for filename in os.listdir(base_dir):
            if not filename.endswith('_requests.json'):
                continue

            file_path = os.path.join(base_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    user_requests = json.load(f)
                    if isinstance(user_requests, list):
                        all_requests.extend(user_requests)
            except Exception as e:
                print(f"Error reading feature request file {filename}: {e}")
                continue

        # Sort by timestamp
        all_requests.sort(key=lambda x: x.get('timestamp', ''))

        return all_requests

    except Exception as e:
        print(f"Error reading feature requests: {e}")
        return []


def mark_request_completed(request_id: str, admin_username: str) -> bool:
    """Mark a feature request as completed and notify the user.

    Args:
        request_id: Unique ID of the request
        admin_username: Admin who marked it complete

    Returns:
        True on success, False on failure
    """
    try:
        base_dir = get_feature_requests_base_dir()

        if not os.path.exists(base_dir):
            return False

        # Find the request in user files
        for filename in os.listdir(base_dir):
            if not filename.endswith('_requests.json'):
                continue

            file_path = os.path.join(base_dir, filename)
            try:
                # Read user's requests
                with open(file_path, 'r', encoding='utf-8') as f:
                    requests = json.load(f)

                # Find and update the request
                modified = False
                for req in requests:
                    if req.get('id') == request_id:
                        req['completed'] = True
                        req['completed_by'] = admin_username
                        req['completed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        modified = True
                        break

                if modified:
                    # Write back to file
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(requests, f, indent=2, ensure_ascii=False)
                    print(f"Marked request {request_id} as completed by {admin_username}")
                    return True

            except Exception as e:
                print(f"Error processing file {filename}: {e}")
                continue

        print(f"Request {request_id} not found")
        return False

    except Exception as e:
        print(f"Error marking request as completed: {e}")
        return False


def _notify_user_of_completion(username: str, request: Dict[str, Any], admin_username: str):
    """Create a notification file for the user about their completed request.

    Args:
        username: Username to notify
        request: The completed request data
        admin_username: Admin who completed it
    """
    try:
        base_dir = get_feature_requests_base_dir()
        notification_file = os.path.join(base_dir, f"{username}_notifications.json")

        # Read existing notifications
        notifications = []
        if os.path.exists(notification_file):
            try:
                with open(notification_file, 'r', encoding='utf-8') as f:
                    notifications = json.load(f)
            except Exception:
                notifications = []

        # Add new notification
        notification = {
            'request_id': request['id'],
            'request_category': request['category'],
            'request_description': request['description'][:100] + '...' if len(request['description']) > 100 else request['description'],
            'completed_by': admin_username,
            'completed_at': request['completed_at'],
            'read': False
        }
        notifications.append(notification)

        # Write notifications
        with open(notification_file, 'w', encoding='utf-8') as f:
            json.dump(notifications, f, indent=2, ensure_ascii=False)

        print(f"Notification created for {username}")

    except Exception as e:
        print(f"Error creating notification for {username}: {e}")


# ============================================================================
# USER NOTIFICATIONS
# ============================================================================

def get_user_notifications(username: str) -> List[Dict[str, Any]]:
    """Get unread notifications for a user.

    Args:
        username: Username

    Returns:
        List of unread notification dicts
    """
    try:
        base_dir = get_feature_requests_base_dir()
        notification_file = os.path.join(base_dir, f"{username}_notifications.json")

        if not os.path.exists(notification_file):
            return []

        with open(notification_file, 'r', encoding='utf-8') as f:
            notifications = json.load(f)

        # Return only unread notifications
        return [n for n in notifications if not n.get('read', False)]

    except Exception as e:
        print(f"Error reading notifications for {username}: {e}")
        return []


def mark_notifications_read(username: str):
    """Mark all notifications as read for a user.

    Args:
        username: Username
    """
    try:
        base_dir = get_feature_requests_base_dir()
        notification_file = os.path.join(base_dir, f"{username}_notifications.json")

        if not os.path.exists(notification_file):
            return

        # Read notifications
        with open(notification_file, 'r', encoding='utf-8') as f:
            notifications = json.load(f)

        # Mark all as read
        for notification in notifications:
            notification['read'] = True

        # Write back
        with open(notification_file, 'w', encoding='utf-8') as f:
            json.dump(notifications, f, indent=2, ensure_ascii=False)

        print(f"Marked all notifications as read for {username}")

    except Exception as e:
        print(f"Error marking notifications as read: {e}")


# ============================================================================
# UNREAD TRACKING FOR ADMINS
# ============================================================================

def get_unread_feature_request_count(username: str) -> int:
    """Get count of unread feature requests for admin users.

    Uses user settings to track last read timestamp.

    Args:
        username: Admin username

    Returns:
        Count of unread requests
    """
    try:
        # Get user's last read timestamp
        settings = load_user_settings()
        last_read_str = settings.get("feature_requests_last_read", "")

        # Parse timestamp
        if last_read_str:
            try:
                last_read = datetime.strptime(last_read_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                last_read = None
        else:
            last_read = None

        # Get all requests
        requests = get_feature_requests()

        # Count requests newer than last read
        if last_read is None:
            # Never read before, all are unread
            return len(requests)

        unread_count = 0
        for req in requests:
            try:
                req_time = datetime.strptime(req['timestamp'], "%Y-%m-%d %H:%M:%S")
                if req_time > last_read:
                    unread_count += 1
            except ValueError:
                # If can't parse, assume unread
                unread_count += 1

        return unread_count

    except Exception as e:
        print(f"Error counting unread feature requests: {e}")
        return 0


def mark_feature_requests_as_read(username: str):
    """Mark all current feature requests as read for this admin user.

    Saves current timestamp to user settings.

    Args:
        username: Admin username
    """
    try:
        # Save current timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        set_setting("feature_requests_last_read", timestamp, verbose=False)
        print(f"Marked feature requests as read for {username} at {timestamp}")

    except Exception as e:
        print(f"Error marking feature requests as read: {e}")
