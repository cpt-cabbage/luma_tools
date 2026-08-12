"""Tests for core.metadata_file — MetadataFile caching, locking, mutation.

All I/O happens against pytest tmp_path directories; the network is never
touched. Lockfile behavior is tested against the actual implementation:
- fresh (non-stale) lockfiles make mutate() wait until they disappear
- lockfiles older than _LOCKFILE_STALE_SECONDS are broken and removed
"""

import json
import os
import threading
import time

import pytest

from core.metadata_file import (
    MetadataFile,
    get_metadata_file,
    clear_metadata_file_cache,
)


@pytest.fixture(autouse=True)
def _clean_module_cache():
    """Keep the module-level MetadataFile instance cache isolated per test."""
    clear_metadata_file_cache()
    yield
    clear_metadata_file_cache()


def _read_raw(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_raw(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# ============================================================================
# Basic load/save round-trip
# ============================================================================

class TestRoundTrip:
    def test_save_then_load(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        data = {"name": "shot010", "frames": [1001, 1002], "nested": {"a": 1}}
        assert mf.save(data) is True
        assert mf.exists is True
        assert mf.load() == data

    def test_path_property(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        assert mf.path == os.path.join(str(tmp_path), "meta.json")

    def test_load_missing_file_returns_default(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "does_not_exist.json")
        assert mf.load() == {}
        assert mf.load(default={"fallback": True}) == {"fallback": True}

    def test_load_empty_directory_returns_default(self):
        mf = MetadataFile("", "meta.json")
        assert mf.load(default={"d": 1}) == {"d": 1}

    def test_save_creates_directory(self, tmp_path):
        sub = str(tmp_path / "new" / "deep")
        mf = MetadataFile(sub, "meta.json")
        assert mf.save({"k": "v"}) is True
        assert _read_raw(os.path.join(sub, "meta.json")) == {"k": "v"}

    def test_no_temp_or_lock_files_left_behind(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"k": 1})
        leftovers = [n for n in os.listdir(str(tmp_path)) if n != "meta.json"]
        assert leftovers == []

    def test_delete(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"k": 1})
        assert mf.delete() is True
        assert mf.exists is False
        assert mf.load(default={"gone": True}) == {"gone": True}
        # Deleting a non-existent file is still success
        assert mf.delete() is True


# ============================================================================
# mtime-based caching
# ============================================================================

class TestMtimeCache:
    def test_external_change_with_new_mtime_is_picked_up(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"version": 1})
        assert mf.load()["version"] == 1  # populates cache

        # Simulate another process rewriting the file
        _write_raw(mf.path, {"version": 2})
        st = os.stat(mf.path)
        os.utime(mf.path, (st.st_atime, st.st_mtime + 10))

        assert mf.load()["version"] == 2

    def test_same_mtime_serves_cached_content(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"version": 1})
        assert mf.load()["version"] == 1  # populates cache
        st = os.stat(mf.path)

        # Rewrite content but restore the exact original mtime: the cache
        # cannot detect this, so it must serve the cached (old) content.
        _write_raw(mf.path, {"version": 2})
        os.utime(mf.path, ns=(st.st_atime_ns, st.st_mtime_ns))

        assert mf.load()["version"] == 1
        # Bypassing the cache sees the real file
        assert mf.load(use_cache=False)["version"] == 2

    def test_clear_cache_forces_reread(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"version": 1})
        mf.load()
        st = os.stat(mf.path)
        _write_raw(mf.path, {"version": 3})
        os.utime(mf.path, ns=(st.st_atime_ns, st.st_mtime_ns))

        mf.clear_cache()
        assert mf.load()["version"] == 3

    def test_load_returns_copy_not_cache_reference(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"k": 1})
        first = mf.load()
        first["injected"] = "oops"
        assert "injected" not in mf.load()


# ============================================================================
# mutate() correctness
# ============================================================================

class TestMutate:
    def test_mutator_receives_current_data_and_result_is_saved(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"count": 5, "keep": "me"})

        seen = {}

        def mutator(data):
            seen.update(data)
            data["count"] = data["count"] + 1

        assert mf.mutate(mutator) is True
        assert seen == {"count": 5, "keep": "me"}
        on_disk = _read_raw(mf.path)
        assert on_disk == {"count": 6, "keep": "me"}
        assert mf.load() == {"count": 6, "keep": "me"}

    def test_mutate_on_missing_file_starts_from_empty(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        assert mf.mutate(lambda d: d.update({"first": True})) is True
        assert _read_raw(mf.path) == {"first": True}

    def test_mutate_raising_returns_false_and_leaves_file(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"count": 1})

        def bad_mutator(data):
            raise RuntimeError("boom")

        assert mf.mutate(bad_mutator) is False
        assert _read_raw(mf.path) == {"count": 1}
        # Lockfile must not be left behind after the failure
        assert not os.path.exists(mf.path + ".lock")

    def test_update_and_get_convenience(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        assert mf.update("status", "done") is True
        assert mf.get("status") == "done"
        assert mf.get("missing", "dflt") == "dflt"
        assert _read_raw(mf.path) == {"status": "done"}


# ============================================================================
# Cross-process lockfile behavior
# ============================================================================

class TestLockfile:
    def test_mutate_waits_for_foreign_lock_then_proceeds(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"count": 0})
        lock_path = mf.path + ".lock"

        # Simulate another process holding the lock (fresh mtime = not stale)
        with open(lock_path, "w") as f:
            f.write("held by another process")

        release_delay = 0.5
        remover = threading.Timer(release_delay, os.remove, args=(lock_path,))
        remover.start()
        try:
            start = time.monotonic()
            assert mf.mutate(lambda d: d.update({"count": d["count"] + 1})) is True
            elapsed = time.monotonic() - start
        finally:
            remover.cancel()

        # It must have actually waited for the lock holder, not barged through
        assert elapsed >= release_delay - 0.1
        assert _read_raw(mf.path) == {"count": 1}
        assert not os.path.exists(lock_path)

    def test_stale_lock_is_broken(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"count": 0})
        lock_path = mf.path + ".lock"

        # Lock left behind by a crashed process 60s ago (> 30s stale threshold)
        with open(lock_path, "w") as f:
            f.write("crashed writer")
        old = time.time() - 60
        os.utime(lock_path, (old, old))

        start = time.monotonic()
        assert mf.mutate(lambda d: d.update({"count": 42})) is True
        elapsed = time.monotonic() - start

        # Broken immediately — well under the 5s acquire timeout, which proves
        # the stale lock was removed rather than waited out
        assert elapsed < 4.0
        assert _read_raw(mf.path) == {"count": 42}
        assert not os.path.exists(lock_path)

    def test_save_removes_its_own_lock(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        assert mf.save({"k": 1}) is True
        assert not os.path.exists(mf.path + ".lock")


# ============================================================================
# Concurrency
# ============================================================================

class TestConcurrency:
    def test_interleaved_mutate_increments_lose_no_updates(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        mf.save({"count": 0})

        errors = []
        iterations = 50

        def increment(data):
            data["count"] = data.get("count", 0) + 1

        def worker():
            try:
                for _ in range(iterations):
                    if not mf.mutate(increment):
                        errors.append("mutate returned False")
            except Exception as e:  # pragma: no cover - diagnostic
                errors.append(repr(e))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
            assert not t.is_alive(), "worker thread deadlocked"

        assert errors == []
        assert _read_raw(mf.path)["count"] == 2 * iterations
        assert not os.path.exists(mf.path + ".lock")

    def test_separate_instances_same_file_lose_no_updates(self, tmp_path):
        """Two independent MetadataFile objects on one path.

        The shared-instance test above is serialized by the per-instance
        RLock, so it never exercises the cross-process lockfile. Separate
        instances have separate RLocks, so the ONLY thing preventing lost
        updates here is the `<path>.lock` sentinel — this is the real
        farm-worker / second-workstation scenario.
        """
        path_dir = str(tmp_path)
        seed = MetadataFile(path_dir, "meta.json")
        seed.save({"count": 0})

        errors = []
        iterations = 50

        def increment(data):
            data["count"] = data.get("count", 0) + 1

        def worker():
            # Each thread gets its own instance == its own RLock and its own
            # lockfile bookkeeping, mimicking two separate processes.
            mine = MetadataFile(path_dir, "meta.json")
            try:
                for _ in range(iterations):
                    if not mine.mutate(increment):
                        errors.append("mutate returned False")
            except Exception as e:  # pragma: no cover - diagnostic
                errors.append(repr(e))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
            assert not t.is_alive(), "worker thread deadlocked"

        assert errors == []
        assert _read_raw(seed.path)["count"] == 2 * iterations
        assert not os.path.exists(seed.path + ".lock")


# ============================================================================
# Corrupt file recovery
# ============================================================================

class TestCorruptFile:
    def test_invalid_json_returns_default(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        with open(mf.path, "w", encoding="utf-8") as f:
            f.write("this is { not valid json !!!")
        assert mf.load() == {}
        assert mf.load(default={"safe": True}) == {"safe": True}

    def test_non_dict_json_returns_default(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        _write_raw(mf.path, [1, 2, 3])
        assert mf.load(default={"safe": True}) == {"safe": True}

    def test_save_recovers_corrupted_file(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        with open(mf.path, "w", encoding="utf-8") as f:
            f.write("garbage%%%")
        assert mf.save({"recovered": True}) is True
        assert mf.load() == {"recovered": True}

    def test_mutate_on_corrupted_file_starts_from_default(self, tmp_path):
        mf = MetadataFile(str(tmp_path), "meta.json")
        with open(mf.path, "w", encoding="utf-8") as f:
            f.write("garbage%%%")
        assert mf.mutate(lambda d: d.update({"fresh": 1})) is True
        assert _read_raw(mf.path) == {"fresh": 1}


# ============================================================================
# get_metadata_file factory
# ============================================================================

class TestFactory:
    def test_same_args_return_same_instance(self, tmp_path):
        a = get_metadata_file(str(tmp_path), "meta.json")
        b = get_metadata_file(str(tmp_path), "meta.json")
        assert a is b

    def test_path_separators_normalized_to_same_instance(self, tmp_path):
        fwd = str(tmp_path).replace("\\", "/")
        a = get_metadata_file(str(tmp_path), "meta.json")
        b = get_metadata_file(fwd, "meta.json")
        assert a is b

    def test_shared_instance_shares_the_mtime_cache(self, tmp_path):
        """The point of the factory: two callers reuse one warm cache."""
        a = get_metadata_file(str(tmp_path), "meta.json")
        a.save({"v": 1})
        a.load()  # warms a's cache

        b = get_metadata_file(str(tmp_path), "meta.json")
        # Rewrite content but keep the mtime — only a shared cache can hide it
        st = os.stat(b.path)
        _write_raw(b.path, {"v": 2})
        os.utime(b.path, ns=(st.st_atime_ns, st.st_mtime_ns))
        assert b.load()["v"] == 1

    def test_different_filename_returns_different_instance(self, tmp_path):
        a = get_metadata_file(str(tmp_path), "a.json")
        b = get_metadata_file(str(tmp_path), "b.json")
        assert a is not b

    def test_clear_specific_entry(self, tmp_path):
        a = get_metadata_file(str(tmp_path), "a.json")
        b = get_metadata_file(str(tmp_path), "b.json")
        clear_metadata_file_cache(str(tmp_path), "a.json")
        assert get_metadata_file(str(tmp_path), "a.json") is not a
        assert get_metadata_file(str(tmp_path), "b.json") is b

    def test_clear_all(self, tmp_path):
        a = get_metadata_file(str(tmp_path), "a.json")
        clear_metadata_file_cache()
        assert get_metadata_file(str(tmp_path), "a.json") is not a
