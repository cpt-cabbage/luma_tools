"""
Gallery Pre-warming Service for Luma Tools.

Pre-loads gallery data during splash screen to improve initial load times.
Scans directories, pre-generates GLB thumbnails, and caches results.
"""

import os
import sys
import logging
from typing import Optional, List, Dict, Callable

logger = logging.getLogger(__name__)


# ============================================================================
# GALLERY PRE-WARMING
# ============================================================================

def get_gallery_output_path() -> Optional[str]:
    """
    Get the gallery output path for the current user.

    Returns:
        Path to the user's gallery folder, or None if not configured.
    """
    try:
        from core.settings_manager import get_setting
        from core.state_manager import app_state

        network_path = get_setting("comfyui_network_output_path")
        if not network_path:
            return None

        # Add user subfolder
        username = app_state.user or os.environ.get('USERNAME', 'unknown')
        user_path = os.path.join(network_path, username)

        # Create user's gallery folder if it doesn't exist
        if not os.path.isdir(user_path):
            try:
                from core.utils import ensure_directory
                ensure_directory(user_path)
                logger.info(f"[PreWarm] Created gallery directory: {user_path}")
            except Exception as e:
                logger.warning(f"[PreWarm] Could not create gallery directory: {user_path} - {e}")
                # Fall back to network_path if user folder creation failed
                if os.path.isdir(network_path):
                    return network_path
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
            'items': list of item dicts,
            'thumbnails_generated': int
        }
    """
    result = {
        'output_dir': None,
        'items': [],
        'thumbnails_generated': 0
    }

    # Step 1: Get gallery path
    if progress_callback:
        progress_callback(10, "Locating gallery folder...")

    output_dir = get_gallery_output_path()
    if not output_dir:
        logger.info("[PreWarm] No gallery path configured, skipping pre-warm")
        if progress_callback:
            progress_callback(100, "No gallery configured")
        return result

    result['output_dir'] = output_dir
    logger.info(f"[PreWarm] Gallery path: {output_dir}")

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


def get_prewarm_cache() -> Optional[Dict]:
    """Get the cached pre-warm results, if available."""
    return _prewarm_cache


def set_prewarm_cache(cache: Dict):
    """Store pre-warm results for later use by gallery tab."""
    global _prewarm_cache
    _prewarm_cache = cache


def clear_prewarm_cache():
    """Clear the pre-warm cache."""
    global _prewarm_cache
    _prewarm_cache = None
