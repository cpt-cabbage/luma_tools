"""
Gallery Pre-warming Service for Luma Tools.

Pre-loads gallery data during splash screen to improve initial load times.
Scans directories, pre-generates GLB thumbnails, and caches results.
"""

import os
import sys
import logging
import re
import threading
from typing import Optional, List, Dict, Callable

logger = logging.getLogger(__name__)


# ============================================================================
# GALLERY PRE-WARMING
# ============================================================================

def validate_username(username: str) -> bool:
    """Backwards-compat wrapper around core.utils.is_valid_username with logging."""
    from core.utils import is_valid_username
    ok = is_valid_username(username)
    if not ok:
        logger.error(f"[PreWarm] Invalid username characters: {username}")
    return ok


def get_gallery_output_path() -> Optional[str]:
    """
    Get the gallery output path for the current user.

    Returns:
        Path to the user's gallery folder, or None if not configured.
    """
    try:
        from core.settings_manager import get_setting
        from core.state_manager import app_state

        # Validate network_output_path setting
        network_path = get_setting("network_output_path")
        if not network_path or not isinstance(network_path, str):
            logger.error("[PreWarm] network_output_path not configured or invalid")
            return None

        # Strip whitespace from network path
        network_path = network_path.strip()
        if not network_path:
            logger.error("[PreWarm] network_output_path is empty")
            return None

        # Verify it's an absolute path
        if not os.path.isabs(network_path):
            logger.error(f"[PreWarm] network_output_path must be absolute: {network_path}")
            return None

        # Get username (already set by app_state.initialize_from_args)
        # Don't fall back to os.environ - app_state.user is set in both shot and standalone modes
        username = app_state.user

        # Normalize username: strip whitespace, treat empty as None
        username = username.strip() if username else None

        # SECURITY: Reject empty username - don't fall back to base path
        # This prevents showing all users' files when username is missing
        if not username:
            logger.error("[PreWarm] Cannot create user gallery path without username")
            return None

        # SECURITY: Validate username to prevent path traversal attacks
        if not validate_username(username):
            logger.error(f"[PreWarm] Username validation failed: {username}")
            return None

        # Add user subfolder
        user_path = os.path.join(network_path, username)

        # Create user's gallery folder if it doesn't exist
        if not os.path.isdir(user_path):
            try:
                from core.utils import ensure_directory
                ensure_directory(user_path)
                logger.info(f"[PreWarm] Created gallery directory: {user_path}")
            except Exception as e:
                # SECURITY: Don't fall back to base path - this breaks user isolation
                logger.error(f"[PreWarm] Could not create gallery directory for user '{username}': {e}")
                return None

        return user_path
    except Exception as e:
        logger.error(f"[PreWarm] Error getting gallery path: {e}")
        return None


def scan_gallery_items(output_dir: str) -> List[Dict]:
    """
    Scan directory for gallery items (images, 3D models, video, and audio).

    Args:
        output_dir: Directory to scan

    Returns:
        List of item dicts with keys: path, mtime, type, name
    """
    from core.config import (
        GALLERY_MODEL_EXTENSIONS, GALLERY_VIDEO_EXTENSIONS,
        GALLERY_AUDIO_EXTENSIONS, GALLERY_SUPPORTED_EXTENSIONS,
    )
    items = []

    try:
        for root, dirs, files in os.walk(output_dir):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in GALLERY_SUPPORTED_EXTENSIONS:
                    full_path = os.path.normpath(os.path.join(root, filename))
                    try:
                        mtime = os.path.getmtime(full_path)
                    except OSError:
                        mtime = 0

                    # Determine file type
                    if ext in GALLERY_MODEL_EXTENSIONS:
                        file_type = 'model'
                    elif ext in GALLERY_VIDEO_EXTENSIONS:
                        file_type = 'video'
                    elif ext in GALLERY_AUDIO_EXTENSIONS:
                        file_type = 'audio'
                    else:
                        file_type = 'image'

                    items.append({
                        'path': full_path,
                        'mtime': mtime,
                        'type': file_type,
                        'name': filename.lower()
                    })
    except Exception as e:
        logger.error(f"[PreWarm] Error scanning directory: {e}")

    return items


def prewarm_model_thumbnails(items: List[Dict],
                              progress_callback: Optional[Callable] = None,
                              max_items: int = 15) -> int:
    """
    Pre-generate thumbnails for 3D models that aren't cached.

    Uses subprocess to avoid OpenGL conflicts. Limits to max_items to prevent
    long delays on first launch with many new models.

    Args:
        items: List of item dicts from scan_gallery_items
        progress_callback: Optional callback(progress, message) for updates
        max_items: Maximum number of thumbnails to generate (default 15)

    Returns:
        Number of thumbnails generated
    """
    try:
        from geo.thumbnail_service import get_model_thumbnail_service
        service = get_model_thumbnail_service()
    except ImportError:
        logger.warning("[PreWarm] Model thumbnail service not available")
        return 0

    # Filter to just models
    models = [item for item in items if item['type'] == 'model']
    total_models = len(models)

    if total_models == 0:
        return 0

    logger.info(f"[PreWarm] Found {total_models} 3D models total")

    if progress_callback:
        progress_callback(0, f"Checking {total_models} model thumbnails...")

    # Check which ones are already cached
    cached_count = 0
    uncached = []
    for m in models:
        if service.is_cached(m['path']):
            cached_count += 1
        else:
            uncached.append(m)

    logger.info(f"[PreWarm] {cached_count} already cached, {len(uncached)} need thumbnails")

    if not uncached:
        if progress_callback:
            progress_callback(100, f"{cached_count} model thumbnails ready")
        return 0

    # Limit to max_items
    to_generate = uncached[:max_items]
    total = len(to_generate)
    generated = 0
    skipped = len(uncached) - total

    logger.info(f"[PreWarm] Generating {total} model thumbnails (max {max_items})")

    for i, item in enumerate(to_generate):
        filename = os.path.basename(item['path'])
        # Truncate long filenames for display
        display_name = filename[:25] + "..." if len(filename) > 28 else filename

        if progress_callback:
            pct = int((i / total) * 100)
            progress_callback(pct, f"Generating thumbnail {i+1}/{total}: {display_name}")

        try:
            result = service.generate_thumbnail_sync(item['path'])
            if result:
                generated += 1
        except Exception as e:
            logger.error(f"[PreWarm] Error generating thumbnail for {item['path']}: {e}")

    # Final message
    if progress_callback:
        if skipped > 0:
            progress_callback(100, f"Generated {generated} thumbnails ({skipped} queued)")
        else:
            progress_callback(100, f"Generated {generated} model thumbnails")

    return generated


def prewarm_gallery(progress_callback: Optional[Callable] = None) -> Dict:
    """
    Pre-warm the gallery by scanning the directory.

    This is the main entry point for gallery pre-warming during startup.
    Only scans files - thumbnails are generated lazily when visible.

    Args:
        progress_callback: Optional callback(progress, message) for updates

    Returns:
        Dict with results: {
            'output_dir': str or None,
            'username': str or None,  # Username this cache is for
            'items': list of item dicts,
            'thumbnails_generated': int
        }
    """
    result = {
        'output_dir': None,
        'username': None,
        'items': [],
        'thumbnails_generated': 0
    }

    # Step 1: Get gallery path and username
    if progress_callback:
        progress_callback(10, "Locating gallery folder...")

    # Get the username that will be used for this scan
    # (matches the logic in get_gallery_output_path)
    from core.state_manager import app_state
    raw_username = app_state.user
    # Normalize username: strip whitespace, treat empty as None
    username = raw_username.strip() if raw_username else None
    result['username'] = username

    output_dir = get_gallery_output_path()
    if not output_dir:
        logger.info("[PreWarm] No gallery path configured, skipping pre-warm")
        if progress_callback:
            progress_callback(100, "No gallery configured")
        return result

    result['output_dir'] = output_dir
    if username:
        logger.info(f"[PreWarm] Gallery path for user '{username}': {output_dir}")
    else:
        logger.info(f"[PreWarm] Gallery path (no user): {output_dir}")

    # Step 2: Scan directory
    if progress_callback:
        progress_callback(30, "Scanning gallery folder...")

    items = scan_gallery_items(output_dir)
    result['items'] = items

    image_count = sum(1 for i in items if i['type'] == 'image')
    model_count = sum(1 for i in items if i['type'] == 'model')
    logger.info(f"[PreWarm] Found {image_count} images, {model_count} 3D models")

    # 3D model thumbnails are generated lazily when visible in gallery
    if progress_callback:
        progress_callback(100, "Gallery ready")

    return result


# ============================================================================
# PREWARM CACHE (for sharing results with gallery tab)
# ============================================================================

_prewarm_cache: Optional[Dict] = None
_prewarm_cache_lock = threading.RLock()


def get_prewarm_cache() -> Optional[Dict]:
    """Get the cached pre-warm results, if available. Thread-safe."""
    with _prewarm_cache_lock:
        return _prewarm_cache


def set_prewarm_cache(cache: Dict):
    """Store pre-warm results for later use by gallery tab. Thread-safe."""
    global _prewarm_cache
    with _prewarm_cache_lock:
        _prewarm_cache = cache


def clear_prewarm_cache():
    """Clear the pre-warm cache. Thread-safe."""
    global _prewarm_cache
    with _prewarm_cache_lock:
        _prewarm_cache = None
