"""
Feature requests management for Luma Tools.

Handles feature request submission, retrieval, completion tracking, and notifications.
Each user has their own requests file stored in the ComfyUI network output folder.
"""

import os
import json
import logging
import tempfile
from typing import Dict, Any, List
from datetime import datetime
from .settings_manager import (
    get_setting, set_setting,
    load_user_settings, save_user_settings,
    get_global_settings_path
)
from .error_handling import log_error, handle_errors
from .utils import ensure_directory, load_json, save_json

logger = logging.getLogger(__name__)


def _atomic_json_write(file_path: str, data: Any) -> None:
    """Write JSON data atomically. Delegates to save_json from core.utils."""
    dir_path = os.path.dirname(file_path)
    ensure_directory(dir_path)
    save_json(file_path, data)


# ============================================================================
# FEATURE REQUESTS BASE PATH
# ============================================================================

def get_feature_requests_base_dir() -> str:
    """Get base path for feature requests (network output path)."""
    network_path = get_setting("network_output_path")
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
        ensure_directory(os.path.dirname(file_path))

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

        # Read existing requests — propagate read errors to avoid overwriting
        # the file with just the new entry if the existing file is corrupted
        requests = []
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    requests = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(
                    "Refusing to append to corrupted feature requests file "
                    f"{file_path}: {e}. New request not saved."
                )
                return False

        # Append new request
        requests.append(new_request)

        # Write back to file atomically
        _atomic_json_write(file_path, requests)

        logger.info(f"Feature request created: {category} by {username}")
        return True

    except Exception as e:
        log_error("creating feature request", e)
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
                user_requests = load_json(file_path, [])
                if isinstance(user_requests, list):
                    # Migrate old requests without IDs
                    modified = False
                    for req in user_requests:
                        if 'id' not in req:
                            req['id'] = datetime.strptime(req['timestamp'], "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S_%f")
                            modified = True
                            logger.info(f"Migrated request without ID: {req['timestamp']} by {req.get('username', 'Unknown')}")

                    if modified:
                        _atomic_json_write(file_path, user_requests)
                        logger.info(f"Updated {filename} with missing IDs")

                    all_requests.extend(user_requests)
            except Exception as e:
                log_error("reading feature request file", e, filename)
                continue

        # Sort by timestamp
        all_requests.sort(key=lambda x: x.get('timestamp', ''))

        return all_requests

    except Exception as e:
        log_error("reading feature requests", e)
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
                requests = load_json(file_path, [])

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
                    # Write back to file atomically
                    _atomic_json_write(file_path, requests)
                    logger.info(f"Marked request {request_id} as completed by {admin_username}")
                    # Notify the user who made the request
                    for req in requests:
                        if req.get('id') == request_id:
                            _notify_user_of_completion(req.get('username', ''), req, admin_username)
                            break
                    return True

            except Exception as e:
                log_error("processing file", e, filename)
                continue

        logger.warning(f"Request {request_id} not found")
        return False

    except Exception as e:
        log_error("marking request as completed", e, request_id)
        return False


def reject_request(request_id: str, admin_username: str, reason: str) -> bool:
    """Reject a feature request and notify the user.

    Args:
        request_id: Unique ID of the request
        admin_username: Admin who rejected it
        reason: Reason for rejection

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
                requests = load_json(file_path, [])

                # Find and update the request
                modified = False
                for req in requests:
                    if req.get('id') == request_id:
                        req['rejected'] = True
                        req['rejected_by'] = admin_username
                        req['rejected_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        req['reject_reason'] = reason
                        modified = True
                        break

                if modified:
                    _atomic_json_write(file_path, requests)
                    logger.info(f"Rejected request {request_id} by {admin_username}: {reason}")
                    for req in requests:
                        if req.get('id') == request_id:
                            _notify_user_of_rejection(req.get('username', ''), req, admin_username, reason)
                            break
                    return True

            except Exception as e:
                log_error("processing file", e, filename)
                continue

        logger.warning(f"Request {request_id} not found")
        return False

    except Exception as e:
        log_error("rejecting request", e, request_id)
        return False


def _append_user_notification(username: str, notification: Dict[str, Any]):
    """Append a notification to the user's notification file.

    Shared helper for completion and rejection notifications. Reads existing
    notifications, appends the new one, and writes back atomically.

    Args:
        username: Username to notify
        notification: Notification dict to append (must include 'read': False)
    """
    try:
        base_dir = get_feature_requests_base_dir()
        notification_file = os.path.join(base_dir, f"{username}_notifications.json")

        notifications = load_json(notification_file, [])
        if not isinstance(notifications, list):
            notifications = []

        notifications.append(notification)
        _atomic_json_write(notification_file, notifications)
        logger.info(f"Notification created for {username}: {notification.get('action', 'completed')}")

    except Exception as e:
        log_error("creating notification for", e, username)


def _truncate_description(description: str, max_len: int = 100) -> str:
    """Truncate a description string for notification display."""
    return description[:max_len] + '...' if len(description) > max_len else description


def _notify_user_of_rejection(username: str, request: Dict[str, Any], admin_username: str, reason: str):
    """Create a notification for the user about their rejected request."""
    _append_user_notification(username, {
        'request_id': request['id'],
        'request_category': request['category'],
        'request_description': _truncate_description(request['description']),
        'action': 'rejected',
        'rejected_by': admin_username,
        'rejected_at': request['rejected_at'],
        'reason': reason,
        'read': False
    })


def _notify_user_of_completion(username: str, request: Dict[str, Any], admin_username: str):
    """Create a notification for the user about their completed request."""
    _append_user_notification(username, {
        'request_id': request['id'],
        'request_category': request['category'],
        'request_description': _truncate_description(request['description']),
        'action': 'completed',
        'completed_by': admin_username,
        'completed_at': request['completed_at'],
        'read': False
    })


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

        notifications = load_json(notification_file, [])

        # Return only unread notifications
        return [n for n in notifications if not n.get('read', False)]

    except Exception as e:
        log_error("reading notifications for", e, username)
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

        notifications = load_json(notification_file, [])

        # Mark all as read
        for notification in notifications:
            notification['read'] = True

        # Write back atomically
        _atomic_json_write(notification_file, notifications)

        logger.info(f"Marked all notifications as read for {username}")

    except Exception as e:
        log_error("marking notifications as read", e)


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
        log_error("counting unread feature requests", e)
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
        logger.info(f"Marked feature requests as read for {username} at {timestamp}")

    except Exception as e:
        log_error("marking feature requests as read", e)
