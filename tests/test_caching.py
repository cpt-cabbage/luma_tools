"""Tests for core/caching.py — TTL cache, ThreadSafeCache, CachedProperty."""

import time
import threading
import pytest
from core.caching import cached_with_ttl, ThreadSafeCache


# ============================================================================
# cached_with_ttl
# ============================================================================

class TestCachedWithTtl:
    def test_caches_result(self):
        call_count = 0

        @cached_with_ttl(seconds=60)
        def expensive():
            nonlocal call_count
            call_count += 1
            return "result"

        assert expensive() == "result"
        assert expensive() == "result"
        assert call_count == 1

    def test_ttl_expires(self):
        call_count = 0

        @cached_with_ttl(seconds=0.1)
        def expiring():
            nonlocal call_count
            call_count += 1
            return call_count

        assert expiring() == 1
        time.sleep(0.15)
        assert expiring() == 2

    def test_different_args_cached_separately(self):
        call_count = 0

        @cached_with_ttl(seconds=60)
        def by_key(key):
            nonlocal call_count
            call_count += 1
            return key.upper()

        assert by_key("a") == "A"
        assert by_key("b") == "B"
        assert by_key("a") == "A"
        assert call_count == 2  # "a" cached, "b" separate


# ============================================================================
# ThreadSafeCache
# ============================================================================

class TestThreadSafeCache:
    def test_get_set(self):
        cache = ThreadSafeCache()
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_get_missing_returns_default(self):
        cache = ThreadSafeCache()
        assert cache.get("missing") is None
        assert cache.get("missing", "fallback") == "fallback"

    def test_ttl_expiry(self):
        cache = ThreadSafeCache()
        cache.set("key", "value", ttl=0.1)
        assert cache.get("key") == "value"
        time.sleep(0.15)
        assert cache.get("key") is None

    def test_max_size_eviction(self):
        cache = ThreadSafeCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # Should evict oldest
        assert cache.get("a") is None
        assert cache.get("d") == 4

    def test_delete(self):
        cache = ThreadSafeCache()
        cache.set("key", "value")
        cache.delete("key")
        assert cache.get("key") is None

    def test_clear(self):
        cache = ThreadSafeCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_stats_hit_rate(self):
        cache = ThreadSafeCache()
        cache.set("key", "val")
        cache.get("key")       # hit
        cache.get("key")       # hit
        cache.get("missing")   # miss
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3)

    def test_stats_empty_cache(self):
        cache = ThreadSafeCache()
        stats = cache.stats()
        assert stats["hit_rate"] == 0.0

    def test_thread_safety(self):
        cache = ThreadSafeCache()
        errors = []

        def writer(prefix):
            try:
                for i in range(100):
                    cache.set(f"{prefix}_{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"t{t}",)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
