"""
ComfyUI Model Ratings System.

Provides a global rating system for ComfyUI workflow models/presets,
stored on the network for all users to share.

Data file location: <network_output_path>/comfyui_model_ratings.json

Features:
- Per-user ratings (each user can rate once per model)
- Aggregated averages with rating count
- Usage tracking (total uses, last used)
- Thumbnail management (auto from gallery or manual upload)
- Tag-based categorization
- Multiple sort options

Thread-safe via MetadataFile with RLock.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.metadata_file import MetadataFile, get_metadata_file
from core.settings_manager import safe_get_setting

logger = logging.getLogger(__name__)

# Ratings file name (stored in network output path)
RATINGS_FILENAME = "comfyui_model_ratings.json"

# Current data format version
RATINGS_VERSION = 1

# Predefined tags for model categorization
PREDEFINED_TAGS = [
    "Upscaling",
    "Generation",
    "Video",
    "Style Transfer",
    "Inpainting",
    "3D",
    "Animation",
    "Portrait",
    "Landscape",
    "Abstract",
    "Experimental",
]


def _get_ratings_file() -> Optional[MetadataFile]:
    """
    Get the ratings MetadataFile instance.

    Returns:
        MetadataFile instance or None if network path not configured
    """
    network_path = safe_get_setting("network_output_path", "")
    if not network_path:
        logger.warning("[Ratings] Network output path not configured")
        return None
    return get_metadata_file(network_path, RATINGS_FILENAME)


def _get_default_model_data() -> Dict[str, Any]:
    """Get default data structure for a new model."""
    return {
        "ratings": {},  # username -> rating (1-5)
        "average": 0.0,
        "rating_count": 0,
        "total_uses": 0,
        "last_used": None,
        "thumbnail_source": None,  # "auto" | "manual" | None
        "thumbnail_path": None,
        "tags": [],
    }


def _get_default_ratings_data() -> Dict[str, Any]:
    """Get default data structure for ratings file."""
    return {
        "models": {},
        "version": RATINGS_VERSION,
    }


def _recalculate_average(model_data: Dict[str, Any]) -> None:
    """Recalculate average rating from individual ratings."""
    ratings = model_data.get("ratings", {})
    if ratings:
        values = list(ratings.values())
        model_data["average"] = round(sum(values) / len(values), 2)
        model_data["rating_count"] = len(values)
    else:
        model_data["average"] = 0.0
        model_data["rating_count"] = 0


# =============================================================================
# PUBLIC API
# =============================================================================

def get_all_ratings() -> Dict[str, Any]:
    """
    Load entire ratings data structure.

    Returns:
        Dict with models data, or empty structure if unavailable
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return _get_default_ratings_data()
    return ratings_file.load(default=_get_default_ratings_data())


def get_model_rating(model_name: str) -> Dict[str, Any]:
    """
    Get rating data for a specific model.

    Args:
        model_name: Full model/preset name (e.g., "folder/Flux Upscale")

    Returns:
        Dict with ratings, average, total_uses, etc. or default empty structure
    """
    data = get_all_ratings()
    models = data.get("models", {})
    return models.get(model_name, _get_default_model_data())


def get_user_rating(model_name: str, username: str) -> Optional[int]:
    """
    Get a specific user's rating for a model.

    Args:
        model_name: Full model/preset name
        username: User who rated

    Returns:
        Rating value (1-5) or None if user hasn't rated
    """
    model_data = get_model_rating(model_name)
    return model_data.get("ratings", {}).get(username)


def rate_model(model_name: str, username: str, rating: int) -> bool:
    """
    Add or update a user's rating for a model.

    Args:
        model_name: Full model/preset name
        username: User submitting rating
        rating: Rating value (1-5)

    Returns:
        True if saved successfully, False on error
    """
    if not 1 <= rating <= 5:
        logger.error(f"[Ratings] Invalid rating {rating}, must be 1-5")
        return False

    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.setdefault("models", {})

    # Get or create model entry
    if model_name not in models:
        models[model_name] = _get_default_model_data()

    model_data = models[model_name]

    # Update user's rating
    old_rating = model_data.get("ratings", {}).get(username)
    model_data.setdefault("ratings", {})[username] = rating

    # Recalculate average
    _recalculate_average(model_data)

    if ratings_file.save(data):
        action = "updated" if old_rating else "added"
        logger.info(f"[Ratings] User {username} {action} rating for '{model_name}': {rating}")
        return True
    return False


def clear_model_ratings(model_name: str) -> bool:
    """
    Clear all ratings for a model (admin function).

    Args:
        model_name: Full model/preset name

    Returns:
        True if cleared successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.get("models", {})

    if model_name not in models:
        return True  # Nothing to clear

    model_data = models[model_name]
    model_data["ratings"] = {}
    model_data["average"] = 0.0
    model_data["rating_count"] = 0

    if ratings_file.save(data):
        logger.info(f"[Ratings] Cleared all ratings for '{model_name}'")
        return True
    return False


def increment_model_usage(model_name: str) -> bool:
    """
    Increment usage count for a model (called on job submit).

    Args:
        model_name: Full model/preset name

    Returns:
        True if incremented successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.setdefault("models", {})

    # Get or create model entry
    if model_name not in models:
        models[model_name] = _get_default_model_data()

    model_data = models[model_name]
    model_data["total_uses"] = model_data.get("total_uses", 0) + 1
    model_data["last_used"] = datetime.now().isoformat()

    return ratings_file.save(data)


def set_model_thumbnail(
    model_name: str,
    thumbnail_path: Optional[str],
    source: str = "manual"
) -> bool:
    """
    Set the thumbnail for a model.

    Args:
        model_name: Full model/preset name
        thumbnail_path: Path to thumbnail image, or None to clear
        source: "auto" (from gallery) or "manual" (uploaded)

    Returns:
        True if saved successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.setdefault("models", {})

    if model_name not in models:
        models[model_name] = _get_default_model_data()

    model_data = models[model_name]
    model_data["thumbnail_path"] = thumbnail_path
    model_data["thumbnail_source"] = source if thumbnail_path else None

    if ratings_file.save(data):
        logger.info(f"[Ratings] Set thumbnail for '{model_name}': {thumbnail_path} ({source})")
        return True
    return False


def set_model_tags(model_name: str, tags: List[str]) -> bool:
    """
    Set tags for a model.

    Args:
        model_name: Full model/preset name
        tags: List of tag strings

    Returns:
        True if saved successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.setdefault("models", {})

    if model_name not in models:
        models[model_name] = _get_default_model_data()

    model_data = models[model_name]
    model_data["tags"] = list(tags)  # Copy to avoid reference issues

    if ratings_file.save(data):
        logger.info(f"[Ratings] Set tags for '{model_name}': {tags}")
        return True
    return False


def get_sorted_models(
    presets: Dict[str, Any],
    sort_key: str = "recently_used",
    tag_filter: Optional[str] = None,
    search_query: Optional[str] = None,
    username: Optional[str] = None,
) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """
    Get a sorted list of models with their preset and rating data.

    Args:
        presets: Dict of preset_name -> preset_config from presets_manager
        sort_key: One of "name", "highest_rated", "most_used",
                  "recently_added", "recently_used"
        tag_filter: Optional tag to filter by (None = all, "favorites" for user favorites)
        search_query: Optional search string to filter by name
        username: Username for favorites filtering

    Returns:
        List of (model_name, preset_config, rating_data) tuples, sorted
    """
    ratings_data = get_all_ratings()
    models_ratings = ratings_data.get("models", {})

    # Get user favorites if filtering by favorites
    user_favorites = set()
    if tag_filter == "favorites" and username:
        user_favorites = set(get_user_favorites(username))

    result = []

    for preset_name, preset_config in presets.items():
        # Get rating data (or defaults)
        rating_data = models_ratings.get(preset_name, _get_default_model_data())

        # Apply favorites filter first (if active)
        if tag_filter == "favorites":
            if preset_name not in user_favorites:
                continue

        # Apply search filter
        if search_query:
            query_lower = search_query.lower()
            # Search in name and tags
            name_match = query_lower in preset_name.lower()
            tags = rating_data.get("tags", [])
            tag_match = any(query_lower in tag.lower() for tag in tags)
            if not name_match and not tag_match:
                continue

        # Apply tag filter (skip if favorites, already handled)
        if tag_filter and tag_filter not in ("all", "favorites"):
            tags = rating_data.get("tags", [])
            if tag_filter not in tags:
                continue

        result.append((preset_name, preset_config, rating_data))

    # Sort based on sort_key
    if sort_key == "name":
        result.sort(key=lambda x: x[0].lower())

    elif sort_key == "highest_rated":
        # Sort by average rating (descending), then by rating count, then name
        result.sort(key=lambda x: (
            -x[2].get("average", 0),
            -x[2].get("rating_count", 0),
            x[0].lower()
        ))

    elif sort_key == "most_used":
        # Sort by total uses (descending), then name
        result.sort(key=lambda x: (
            -x[2].get("total_uses", 0),
            x[0].lower()
        ))

    elif sort_key == "recently_added":
        # Sort by name for now (could track creation date later)
        # Newer presets typically come last alphabetically in folders
        result.sort(key=lambda x: x[0].lower(), reverse=True)

    elif sort_key == "recently_used":
        # Sort by last_used timestamp (most recent first), then name
        def get_last_used(item):
            last_used = item[2].get("last_used")
            if last_used:
                try:
                    return datetime.fromisoformat(last_used)
                except (ValueError, TypeError):
                    pass
            # Return very old date for never-used models
            return datetime(1970, 1, 1)

        result.sort(key=lambda x: (
            get_last_used(x),
            x[0].lower()
        ), reverse=True)

    return result


def get_all_tags_in_use() -> List[str]:
    """
    Get list of all tags currently in use across all models.

    Returns:
        Sorted list of unique tag strings
    """
    data = get_all_ratings()
    models = data.get("models", {})

    all_tags = set()
    for model_data in models.values():
        tags = model_data.get("tags", [])
        all_tags.update(tags)

    return sorted(all_tags)


def get_predefined_tags() -> List[str]:
    """
    Get the list of predefined tags from global settings.

    Returns:
        List of predefined tag strings (from settings or default fallback)
    """
    from core.settings_manager import safe_get_setting
    return safe_get_setting("comfyui_preset_categories", PREDEFINED_TAGS.copy())


def delete_model_data(model_name: str) -> bool:
    """
    Delete all rating/usage data for a model (when preset is deleted).

    Args:
        model_name: Full model/preset name

    Returns:
        True if deleted successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.get("models", {})

    if model_name in models:
        del models[model_name]
        if ratings_file.save(data):
            logger.info(f"[Ratings] Deleted data for '{model_name}'")
            return True

    return True  # Nothing to delete


def rename_model_data(old_name: str, new_name: str) -> bool:
    """
    Rename a model's rating data (when preset is renamed).

    Args:
        old_name: Current model name
        new_name: New model name

    Returns:
        True if renamed successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.get("models", {})

    if old_name in models:
        models[new_name] = models.pop(old_name)
        if ratings_file.save(data):
            logger.info(f"[Ratings] Renamed data from '{old_name}' to '{new_name}'")
            return True
        return False

    return True  # Nothing to rename


# =============================================================================
# FAVORITES & RECENTS API
# =============================================================================

MAX_RECENTS = 10  # Maximum number of recent models per user


def get_user_favorites(username: str) -> List[str]:
    """
    Get list of user's favorite model names.

    Args:
        username: User to get favorites for

    Returns:
        List of model names that user has favorited
    """
    data = get_all_ratings()
    models = data.get("models", {})

    favorites = []
    for model_name, model_data in models.items():
        is_fav = model_data.get("is_favorite", {}).get(username, False)
        if is_fav:
            favorites.append(model_name)

    return favorites


def get_user_recents(username: str) -> List[str]:
    """
    Get list of user's recently used model names.

    Args:
        username: User to get recents for

    Returns:
        List of model names in order of most recent first
    """
    data = get_all_ratings()
    user_recents = data.get("user_recents", {})
    return user_recents.get(username, [])


def toggle_favorite(model_name: str, username: str) -> bool:
    """
    Toggle favorite status for a model.

    Args:
        model_name: Model to toggle favorite
        username: User toggling favorite

    Returns:
        True if saved successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.setdefault("models", {})

    # Get or create model entry
    if model_name not in models:
        models[model_name] = _get_default_model_data()

    model_data = models[model_name]

    # Toggle favorite
    is_favorite = model_data.setdefault("is_favorite", {})
    current = is_favorite.get(username, False)
    is_favorite[username] = not current

    if ratings_file.save(data):
        action = "unfavorited" if current else "favorited"
        logger.info(f"[Ratings] User {username} {action} '{model_name}'")
        return True
    return False


def set_favorite(model_name: str, username: str, is_favorite: bool) -> bool:
    """
    Set favorite status for a model.

    Args:
        model_name: Model to set favorite
        username: User setting favorite
        is_favorite: Whether to favorite or unfavorite

    Returns:
        True if saved successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    models = data.setdefault("models", {})

    if model_name not in models:
        models[model_name] = _get_default_model_data()

    model_data = models[model_name]
    model_data.setdefault("is_favorite", {})[username] = is_favorite

    return ratings_file.save(data)


def add_to_recents(model_name: str, username: str) -> bool:
    """
    Add a model to user's recent models list.

    Args:
        model_name: Model to add to recents
        username: User to update recents for

    Returns:
        True if saved successfully, False on error
    """
    ratings_file = _get_ratings_file()
    if not ratings_file:
        return False

    data = ratings_file.load(default=_get_default_ratings_data())
    user_recents = data.setdefault("user_recents", {})

    # Get or create user's recents list
    recents = user_recents.setdefault(username, [])

    # Remove if already present (will re-add at front)
    if model_name in recents:
        recents.remove(model_name)

    # Add to front
    recents.insert(0, model_name)

    # Trim to max length
    user_recents[username] = recents[:MAX_RECENTS]

    return ratings_file.save(data)


# =============================================================================
# AUTO-THUMBNAIL API
# =============================================================================

def update_model_thumbnail(model_name: str) -> Optional[str]:
    """
    Auto-generate thumbnail from gallery outputs.

    Finds the highest-rated or most recent output with this workflow_preset
    and creates a thumbnail.

    Args:
        model_name: Model to update thumbnail for

    Returns:
        Path to generated thumbnail, or None if no outputs found
    """
    import glob
    from PIL import Image

    from core.utils import ensure_directory, load_json

    network_path = safe_get_setting("network_output_path", "")
    if not network_path:
        return None

    # Find gallery metadata files
    from comfyui.metadata import GALLERY_METADATA_FILE
    try:
        metadata_files = glob.glob(
            os.path.join(network_path, "**", GALLERY_METADATA_FILE),
            recursive=True
        )
    except Exception as e:
        logger.warning(f"[Ratings] Error searching for metadata: {e}")
        return None

    # Find outputs matching this model. Schema uses `_prefix_<job_prefix>`
    # entries (one per job) plus optional `_file_<basename>` per-file entries.
    # A file belongs to a job if its basename starts with the prefix.
    candidates = []
    for meta_file in metadata_files:
        try:
            metadata = load_json(meta_file, {})
            base_dir = os.path.dirname(meta_file)
            if not os.path.isdir(base_dir):
                continue

            # Collect (prefix, prefix_data) for prefixes matching this model
            matching_prefixes = []
            for key, value in metadata.items():
                if not isinstance(key, str) or not key.startswith("_prefix_"):
                    continue
                if not isinstance(value, dict):
                    continue
                if value.get("workflow_preset") != model_name:
                    continue
                matching_prefixes.append((key[8:], value))  # strip "_prefix_"

            if not matching_prefixes:
                continue

            try:
                dir_files = os.listdir(base_dir)
            except OSError:
                continue

            for prefix, prefix_data in matching_prefixes:
                if not prefix:
                    continue
                for filename in dir_files:
                    if not filename.startswith(prefix):
                        continue
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                        continue
                    file_path = os.path.join(base_dir, filename)
                    if not os.path.exists(file_path):
                        continue
                    # Per-file metadata may carry rating/like; fall back to job
                    file_meta = metadata.get(f"_file_{filename}", {}) or {}
                    candidates.append({
                        "path": file_path,
                        "rating": file_meta.get("user_rating", 0),
                        "timestamp": file_meta.get("timestamp", prefix_data.get("timestamp", 0)),
                        "is_liked": file_meta.get("is_liked", False),
                    })
        except Exception:
            continue

    if not candidates:
        return None

    # Sort by: liked first, then rating, then timestamp
    candidates.sort(key=lambda x: (
        -int(x.get("is_liked", False)),
        -x.get("rating", 0),
        -x.get("timestamp", 0)
    ))

    best = candidates[0]["path"]

    # Create thumbnail
    thumb_dir = os.path.join(network_path, "_model_thumbnails")
    ensure_directory(thumb_dir)

    # Sanitize model name for filename
    safe_name = model_name.replace("/", "_").replace("\\", "_")
    thumb_path = os.path.join(thumb_dir, f"{safe_name}.jpg")

    try:
        with Image.open(best) as img:
            # Convert to RGB if necessary
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Resize to thumbnail size (300x200)
            img.thumbnail((300, 200), Image.Resampling.LANCZOS)
            img.save(thumb_path, "JPEG", quality=85)

        # Update rating data with thumbnail path
        set_model_thumbnail(model_name, thumb_path, source="auto")
        logger.info(f"[Ratings] Generated thumbnail for '{model_name}' from {best}")
        return thumb_path

    except Exception as e:
        logger.warning(f"[Ratings] Failed to create thumbnail: {e}")
        return None


def refresh_all_thumbnails() -> int:
    """
    Refresh thumbnails for all models that don't have one.

    Returns:
        Number of thumbnails updated
    """
    from comfyui.presets_manager import get_comfyui_workflow_presets

    presets = get_comfyui_workflow_presets()
    data = get_all_ratings()
    models = data.get("models", {})

    updated = 0
    for preset_name in presets:
        model_data = models.get(preset_name, {})
        thumb_path = model_data.get("thumbnail_path")

        # Skip if already has manual thumbnail
        if model_data.get("thumbnail_source") == "manual":
            continue

        # Skip if auto thumbnail exists and is valid
        if thumb_path and os.path.exists(thumb_path):
            continue

        # Try to generate
        if update_model_thumbnail(preset_name):
            updated += 1

    logger.info(f"[Ratings] Refreshed {updated} model thumbnails")
    return updated
