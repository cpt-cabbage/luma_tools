"""
Caching utilities for luma_tools.

Provides reusable caching patterns:
- cached_with_ttl: Decorator for time-based cache invalidation
- ThreadSafeCache: Thread-safe dictionary cache with optional max size
- cached_property_with_ttl: Property descriptor with time-based invalidation

Usage:
    @cached_with_ttl(seconds=300)
    def get_expensive_data():
        ...

    cache = ThreadSafeCache(max_size=100)
    cache.set("key", value)
    result = cache.get("key")
"""

import functools
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


def cached_with_ttl(seconds: int, maxsize: int = 128):
    """
    Decorator for time-based cache invalidation.

    Caches function results for a specified duration. Thread-safe.

    Args:
        seconds: Cache TTL in seconds
        maxsize: Maximum number of cached results (default: 128)

    Returns:
        Decorated function with caching

    Example:
        @cached_with_ttl(seconds=300)
        def get_user_data(user_id: str):
            # Expensive database call
            return db.fetch_user(user_id)

        # First call fetches from DB
        data = get_user_data("123")

        # Subsequent calls within 5 minutes return cached result
        data = get_user_data("123")

        # Clear cache manually if needed
        get_user_data.clear_cache()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: Dict[tuple, tuple] = {}  # key -> (result, timestamp)
        lock = threading.RLock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Create cache key from arguments
            try:
                key = (args, tuple(sorted(kwargs.items())))
            except TypeError:
                # Unhashable arguments - don't cache
                return func(*args, **kwargs)

            current_time = time.time()

            with lock:
                # Check if cached and not expired
                if key in cache:
                    result, timestamp = cache[key]
                    if current_time - timestamp < seconds:
                        return result

                # Cache miss or expired - call function
                result = func(*args, **kwargs)

                # Evict oldest entries if at capacity
                if len(cache) >= maxsize:
                    # Remove oldest entry
                    oldest_key = min(cache.keys(), key=lambda k: cache[k][1])
                    del cache[oldest_key]

                cache[key] = (result, current_time)
                return result

        def clear_cache() -> None:
            """Clear all cached results."""
            with lock:
                cache.clear()

        def cache_info() -> Dict[str, Any]:
            """Return cache statistics."""
            with lock:
                return {
                    "size": len(cache),
                    "maxsize": maxsize,
                    "ttl_seconds": seconds,
                }

        wrapper.clear_cache = clear_cache
        wrapper.cache_info = cache_info
        return wrapper

    return decorator


class ThreadSafeCache:
    """
    Thread-safe dictionary cache with optional max size.

    Features:
    - Thread-safe access via RLock
    - Optional max size with FIFO eviction
    - TTL support per entry

    Example:
        cache = ThreadSafeCache(max_size=100)

        # Basic usage
        cache.set("key", value)
        result = cache.get("key", default="not found")

        # With TTL
        cache.set("temp_key", value, ttl=60)  # Expires in 60 seconds

        # Check and delete
        if cache.has("key"):
            cache.delete("key")

        # Get stats
        print(cache.stats())  # {"size": 1, "max_size": 100, ...}
    """

    def __init__(self, max_size: Optional[int] = None):
        """
        Initialize thread-safe cache.

        Args:
            max_size: Maximum number of entries (None = unlimited)
        """
        self._cache: Dict[str, tuple] = {}  # key -> (value, timestamp, ttl)
        self._lock = threading.RLock()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from cache.

        Args:
            key: Cache key
            default: Value to return if key not found or expired

        Returns:
            Cached value or default
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return default

            value, timestamp, ttl = self._cache[key]

            # Check TTL if set
            if ttl is not None and time.time() - timestamp > ttl:
                del self._cache[key]
                self._misses += 1
                return default

            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL in seconds (None = no expiration)
        """
        with self._lock:
            # Evict oldest if at capacity
            if self._max_size and len(self._cache) >= self._max_size:
                if key not in self._cache:  # Only evict if adding new key
                    oldest_key = min(
                        self._cache.keys(),
                        key=lambda k: self._cache[k][1]
                    )
                    del self._cache[oldest_key]

            self._cache[key] = (value, time.time(), ttl)

    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._lock:
            if key not in self._cache:
                return False

            _, timestamp, ttl = self._cache[key]
            if ttl is not None and time.time() - timestamp > ttl:
                del self._cache[key]
                return False

            return True

    def delete(self, key: str) -> bool:
        """
        Delete a key from cache.

        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with size, max_size, hits, misses, hit_rate
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }

    def keys(self) -> list:
        """Get all cache keys (excludes expired entries)."""
        with self._lock:
            current_time = time.time()
            valid_keys = []
            for key, (_, timestamp, ttl) in list(self._cache.items()):
                if ttl is None or current_time - timestamp <= ttl:
                    valid_keys.append(key)
                else:
                    # Clean up expired entry
                    del self._cache[key]
            return valid_keys


class CachedProperty:
    """
    Property descriptor with optional TTL.

    Like @property but caches the result. Optionally expires after TTL.

    Example:
        class MyClass:
            @CachedProperty(ttl=60)
            def expensive_calculation(self):
                return compute_something()

            # Access like normal property
            result = obj.expensive_calculation

            # Clear cache
            del obj.expensive_calculation  # or obj.__class__.expensive_calculation.clear(obj)
    """

    def __init__(self, func: Callable = None, ttl: Optional[int] = None):
        """
        Initialize cached property.

        Args:
            func: The property getter function
            ttl: Optional TTL in seconds (None = cache forever)
        """
        self.func = func
        self.ttl = ttl
        self.attr_name = None
        self.__doc__ = func.__doc__ if func else None

    def __set_name__(self, owner, name):
        self.attr_name = f"_cached_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self

        cache_attr = self.attr_name
        cached = getattr(obj, cache_attr, None)

        if cached is not None:
            value, timestamp = cached
            if self.ttl is None or time.time() - timestamp < self.ttl:
                return value

        # Compute and cache
        value = self.func(obj)
        setattr(obj, cache_attr, (value, time.time()))
        return value

    def __delete__(self, obj):
        """Clear the cached value."""
        try:
            delattr(obj, self.attr_name)
        except AttributeError:
            pass

    def clear(self, obj) -> None:
        """Clear the cached value (alternative to del)."""
        self.__delete__(obj)


def cached_property(ttl: int = None):
    """
    Decorator factory for cached properties.

    Args:
        ttl: Optional TTL in seconds

    Example:
        class MyClass:
            @cached_property(ttl=60)
            def data(self):
                return expensive_fetch()
    """
    def decorator(func):
        return CachedProperty(func, ttl=ttl)
    return decorator
