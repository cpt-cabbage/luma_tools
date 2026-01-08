"""
Gallery Pre-warming Service for Luma Tools.

Pre-loads gallery data during splash screen to improve initial load times.
Scans directories, pre-generates GLB thumbnails, and caches results.
"""

import os
import sys
import subprocess
from typing import Optional, List, Dict, Callable


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
        from settings_manager import get_comfyui_network_output_path
        from state_manager import app_state

        network_path = get_comfyui_network_output_path()
        if not network_path:
            return None

        # Add user subfolder
        username = app_state.user or os.environ.get('USERNAME', 'unknown')
        user_path = os.path.join(network_path, username)

        if os.path.isdir(user_path):
            return user_path
        elif os.path.isdir(network_path):
            return network_path

        return None
    except Exception as e:
        print(f"[PreWarm] Error getting gallery path: {e}")
        return None


def scan_gallery_items(output_dir: str) -> List[Dict]:
    """
    Scan directory for gallery items (images and 3D models).

    Args:
        output_dir: Directory to scan

    Returns:
        List of item dicts with keys: path, mtime, type, name
    """
    items = []
    image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.exr'}
    model_extensions = {'.glb', '.gltf'}
    supported_extensions = image_extensions | model_extensions

    try:
        for root, dirs, files in os.walk(output_dir):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in supported_extensions:
                    full_path = os.path.join(root, filename)
                    try:
                        mtime = os.path.getmtime(full_path)
                    except OSError:
                        mtime = 0
                    file_type = 'model' if ext in model_extensions else 'image'

                    items.append({
                        'path': full_path,
                        'mtime': mtime,
                        'type': file_type,
                        'name': filename.lower()
                    })
    except Exception as e:
        print(f"[PreWarm] Error scanning directory: {e}")

    return items


def prewarm_glb_thumbnails(items: List[Dict],
                           progress_callback: Optional[Callable] = None,
                           max_items: int = 20) -> int:
    """
    Pre-generate thumbnails for GLB models that aren't cached.

    Uses subprocess to avoid OpenGL conflicts. Limits to max_items to prevent
    long delays on first launch with many new models.

    Args:
        items: List of item dicts from scan_gallery_items
        progress_callback: Optional callback(progress, message) for updates
        max_items: Maximum number of thumbnails to generate (default 20)

    Returns:
        Number of thumbnails generated
    """
    try:
        from glb_thumbnail_service import get_glb_thumbnail_service
        service = get_glb_thumbnail_service()
    except ImportError:
        print("[PreWarm] GLB thumbnail service not available")
        return 0

    # Filter to just models
    models = [item for item in items if item['type'] == 'model']
    print(f"[PreWarm] Found {len(models)} 3D models total")

    # Check which ones are already cached
    cached_count = 0
    uncached = []
    for m in models:
        if service.is_cached(m['path']):
            cached_count += 1
        else:
            uncached.append(m)

    print(f"[PreWarm] {cached_count} already cached, {len(uncached)} need thumbnails")

    if not uncached:
        if progress_callback:
            progress_callback(100, f"All {cached_count} thumbnails cached")
        return 0

    # Limit to max_items
    to_generate = uncached[:max_items]
    total = len(to_generate)
    generated = 0

    print(f"[PreWarm] Generating {total} GLB thumbnails (limiting to {max_items})")

    for i, item in enumerate(to_generate):
        if progress_callback:
            pct = int((i / total) * 100)
            progress_callback(pct, f"Generating thumbnail {i+1}/{total}")

        try:
            result = service.generate_thumbnail_sync(item['path'])
            if result:
                generated += 1
        except Exception as e:
            print(f"[PreWarm] Error generating thumbnail for {item['path']}: {e}")

    if progress_callback:
        progress_callback(100, f"Generated {generated} thumbnails")

    return generated


def prewarm_gallery(progress_callback: Optional[Callable] = None) -> Dict:
    """
    Pre-warm the gallery by scanning and generating thumbnails.

    This is the main entry point for gallery pre-warming during startup.

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
        progress_callback(10, "Finding gallery folder...")

    output_dir = get_gallery_output_path()
    if not output_dir:
        print("[PreWarm] No gallery path configured, skipping pre-warm")
        if progress_callback:
            progress_callback(100, "No gallery configured")
        return result

    result['output_dir'] = output_dir
    print(f"[PreWarm] Gallery path: {output_dir}")

    # Step 2: Scan directory
    if progress_callback:
        progress_callback(30, "Scanning gallery...")

    items = scan_gallery_items(output_dir)
    result['items'] = items

    image_count = sum(1 for i in items if i['type'] == 'image')
    model_count = sum(1 for i in items if i['type'] == 'model')
    print(f"[PreWarm] Found {image_count} images, {model_count} 3D models")

    if progress_callback:
        progress_callback(50, f"Found {len(items)} items")

    # Step 3: Pre-generate GLB thumbnails (only for uncached models)
    if model_count > 0:
        def thumb_progress(pct, msg):
            # Map 0-100 to 50-95 range
            overall_pct = 50 + int(pct * 0.45)
            if progress_callback:
                progress_callback(overall_pct, msg)

        generated = prewarm_glb_thumbnails(items, thumb_progress, max_items=15)
        result['thumbnails_generated'] = generated

        if generated == 0:
            # All were cached, skip to end quickly
            if progress_callback:
                progress_callback(95, f"{model_count} models cached")

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
