"""Tests for core.settings_manager staleness/locking features.

Covers the mtime-based global-cache invalidation (_GLOBAL_CACHE_TTL),
update_global_settings() cross-process read-modify-write, set_settings()
bulk writes, the non-caching fallback for unreachable custom global paths,
and within-process set_setting concurrency.

All paths (USER_SETTINGS_DIR / USER_SETTINGS_FILE / DEFAULT_GLOBAL_SETTINGS_PATH)
are monkeypatched onto core.settings_manager so nothing touches the real
~/.luma_tools or the network. Note: settings_manager imports these names into
its own namespace at import time, so patching the module attributes (not
core.config) is what the code under test actually reads.
"""

import json
import os
import threading
import time

import pytest

import core.settings_manager as sm


# ============================================================================
# Fixtures / helpers
# ============================================================================

class _Env:
    def __init__(self, user_dir, user_file, global_dir, global_file):
        self.user_dir = user_dir
        self.user_file = user_file
        self.global_dir = global_dir
        self.global_file = global_file


@pytest.fixture()
def env(tmp_path, monkeypatch):
    user_dir = str(tmp_path / "user")
    user_file = os.path.join(user_dir, "settings.json")
    global_dir = str(tmp_path / "global")
    os.makedirs(user_dir)
    os.makedirs(global_dir)

    monkeypatch.setattr(sm, "USER_SETTINGS_DIR", user_dir)
    monkeypatch.setattr(sm, "USER_SETTINGS_FILE", user_file)
    monkeypatch.setattr(sm, "DEFAULT_GLOBAL_SETTINGS_PATH", global_dir)

    sm.clear_settings_cache()
    yield _Env(user_dir, user_file, global_dir,
               os.path.join(global_dir, sm.GLOBAL_SETTINGS_FILENAME))
    sm.clear_settings_cache()


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _bump_mtime(path, seconds=10):
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + seconds))


def _expire_ttl():
    """Force the next load_global_settings() to re-stat the file.

    Pushed a full TTL into the past rather than set to 0.0, so the helper
    does not depend on time.monotonic()'s epoch being far from zero.
    """
    sm._global_settings_last_check = time.monotonic() - (sm._GLOBAL_CACHE_TTL + 10.0)


# ============================================================================
# 1 & 2. mtime-based global cache invalidation / TTL
# ============================================================================

class TestGlobalCacheStaleness:
    def test_external_change_picked_up_after_ttl(self, env):
        _write_json(env.global_file, {"seed": 1})
        first = sm.load_global_settings()
        assert first["seed"] == 1
        assert "added_by_other_machine" not in first

        # Another workstation rewrites the file with a newer mtime
        _write_json(env.global_file, {"seed": 1, "added_by_other_machine": True})
        _bump_mtime(env.global_file, 10)
        _expire_ttl()

        again = sm.load_global_settings()
        assert again["added_by_other_machine"] is True

    def test_within_ttl_external_changes_not_visible(self, env):
        _write_json(env.global_file, {"seed": 1})
        sm.load_global_settings()  # populates cache, stamps last_check = now

        _write_json(env.global_file, {"seed": 1, "hidden_yet": True})
        _bump_mtime(env.global_file, 10)

        # Still inside the 5s TTL window — must serve the cache, no re-stat
        cached = sm.load_global_settings()
        assert "hidden_yet" not in cached
        assert cached["seed"] == 1

    def test_unchanged_mtime_keeps_cache_after_ttl(self, env):
        _write_json(env.global_file, {"seed": 1})
        sm.load_global_settings()

        # TTL expired but the file has not changed: no reload, cache served
        _expire_ttl()
        assert sm.load_global_settings()["seed"] == 1

    def test_get_setting_sees_external_change(self, env):
        """End-user path: a role/preset change from another workstation must
        become visible through get_setting() without an app restart."""
        _write_json(env.global_file, {"comfyui_path": "X:/old"})
        assert sm.get_setting("comfyui_path") == "X:/old"

        _write_json(env.global_file, {"comfyui_path": "X:/new"})
        _bump_mtime(env.global_file, 10)
        _expire_ttl()

        assert sm.get_setting("comfyui_path") == "X:/new"

    def test_missing_file_after_cache_keeps_serving_cache(self, env):
        _write_json(env.global_file, {"seed": 1})
        sm.load_global_settings()

        os.remove(env.global_file)
        _expire_ttl()
        # Network blip / file gone: keep serving the cached settings
        assert sm.load_global_settings()["seed"] == 1


# ============================================================================
# 3, 4 & 5. update_global_settings
# ============================================================================

class TestUpdateGlobalSettings:
    def test_merges_against_disk_not_cache(self, env):
        _write_json(env.global_file, {"base": 0})
        sm.load_global_settings()  # cache now holds {"base": 0}

        # Another machine adds a key; our cache is now stale
        _write_json(env.global_file, {"base": 0, "other_machine": 1})

        result = sm.update_global_settings(lambda s: {**s, "mine": 2})

        assert result is not None
        on_disk = _read_json(env.global_file)
        assert on_disk["other_machine"] == 1, "stale cache overwrote another machine's key"
        assert on_disk["mine"] == 2
        assert on_disk["base"] == 0
        # In-process cache reflects the merged result too
        assert sm.load_global_settings()["other_machine"] == 1
        assert not os.path.exists(env.global_file + ".lock")

    def test_mutator_returning_none_leaves_file_unchanged(self, env):
        _write_json(env.global_file, {"base": 0})
        st_before = os.stat(env.global_file)

        assert sm.update_global_settings(lambda s: None) is None

        assert _read_json(env.global_file) == {"base": 0}
        assert os.stat(env.global_file).st_mtime_ns == st_before.st_mtime_ns

    def test_missing_file_starts_from_defaults(self, env):
        assert not os.path.exists(env.global_file)
        result = sm.update_global_settings(lambda s: {**s, "k": 1})
        assert result is not None
        on_disk = _read_json(env.global_file)
        assert on_disk["k"] == 1
        # Defaults were the starting point
        assert "admin_users" in on_disk

    def test_lockfile_held_during_mutator_and_removed_after(self, env):
        _write_json(env.global_file, {"base": 0})
        lock_path = env.global_file + ".lock"
        seen = {}

        def mutator(s):
            seen["lock_during_mutate"] = os.path.exists(lock_path)
            s["k"] = 1
            return s

        sm.update_global_settings(mutator)

        assert seen["lock_during_mutate"] is True
        assert not os.path.exists(lock_path)

    def test_waits_for_fresh_foreign_lock(self, env):
        _write_json(env.global_file, {"base": 0})
        lock_path = env.global_file + ".lock"
        with open(lock_path, "w") as f:
            f.write("held elsewhere")

        release_delay = 0.5
        remover = threading.Timer(release_delay, os.remove, args=(lock_path,))
        remover.start()
        try:
            start = time.monotonic()
            result = sm.update_global_settings(lambda s: {**s, "k": 1})
            elapsed = time.monotonic() - start
        finally:
            remover.cancel()

        assert result is not None
        assert elapsed >= release_delay - 0.1
        assert not os.path.exists(lock_path)

    def test_stale_lock_is_broken(self, env):
        _write_json(env.global_file, {"base": 0})
        lock_path = env.global_file + ".lock"
        with open(lock_path, "w") as f:
            f.write("crashed writer")
        old = time.time() - 60  # well past the 10s stale age
        os.utime(lock_path, (old, old))

        start = time.monotonic()
        result = sm.update_global_settings(lambda s: {**s, "k": 1})
        elapsed = time.monotonic() - start

        assert result is not None
        # Under the 5s lock timeout — proves the stale lock was broken,
        # not waited out
        assert elapsed < 4.0
        assert _read_json(env.global_file)["k"] == 1
        assert not os.path.exists(lock_path)


# ============================================================================
# 6. set_settings bulk writes
# ============================================================================

class TestSetSettingsBulk:
    @pytest.fixture()
    def save_counter(self, monkeypatch):
        """Count save_json calls (per target path) while still writing."""
        import core.utils as cu
        real_save = cu.save_json
        calls = []

        def counting_save(path, data, pretty=True):
            calls.append(os.path.normpath(str(path)))
            return real_save(path, data, pretty)

        monkeypatch.setattr(cu, "save_json", counting_save)
        return calls

    def test_three_user_keys_single_write(self, env, save_counter):
        sm.set_settings({
            "show_tray_notifications": False,
            "show_verbose_logs": True,
            "mp4_maker_quality_index": 99,  # validator clamps to 10
        })

        user_writes = [c for c in save_counter
                       if c == os.path.normpath(env.user_file)]
        assert len(user_writes) == 1, f"expected 1 user write, saw {len(user_writes)}"

        on_disk = _read_json(env.user_file)
        assert on_disk["show_tray_notifications"] is False
        assert on_disk["show_verbose_logs"] is True
        assert on_disk["mp4_maker_quality_index"] == 10  # validator applied

    def test_mixed_scopes_one_write_each(self, env, save_counter):
        sm.set_settings({
            "comfyui_path": "X:/mock/comfy",       # global scope
            "show_verbose_logs": True,              # user scope
        })

        user_writes = [c for c in save_counter
                       if c == os.path.normpath(env.user_file)]
        global_writes = [c for c in save_counter
                         if c == os.path.normpath(env.global_file)]
        assert len(user_writes) == 1
        assert len(global_writes) == 1
        assert _read_json(env.global_file)["comfyui_path"] == "X:/mock/comfy"
        assert _read_json(env.user_file)["show_verbose_logs"] is True

    def test_unknown_key_raises_and_writes_nothing(self, env, save_counter):
        with pytest.raises(KeyError, match="Unknown setting"):
            sm.set_settings({
                "show_verbose_logs": True,
                "totally_unknown_key_xyz": 1,
            })

        assert save_counter == [], "KeyError path must not write any file"
        assert not os.path.exists(env.user_file)
        assert not os.path.exists(env.global_file)


# ============================================================================
# 7. Within-process concurrency on global set_setting
# ============================================================================

class TestSetSettingConcurrency:
    def test_two_threads_different_global_keys_no_lost_updates(self, env):
        errors = []
        iterations = 25

        def worker(key, prefix):
            try:
                for i in range(iterations):
                    sm.set_setting(key, f"{prefix}_{i}", verbose=False)
            except Exception as e:  # pragma: no cover - diagnostic
                errors.append(repr(e))

        t1 = threading.Thread(target=worker, args=("comfyui_path", "a"))
        t2 = threading.Thread(target=worker, args=("comfyui_python_path", "b"))
        t1.start()
        t2.start()
        for t in (t1, t2):
            t.join(timeout=60)
            assert not t.is_alive(), "worker thread deadlocked"

        assert errors == []
        on_disk = _read_json(env.global_file)
        assert on_disk["comfyui_path"] == f"a_{iterations - 1}"
        assert on_disk["comfyui_python_path"] == f"b_{iterations - 1}"
        assert not os.path.exists(env.global_file + ".lock")


# ============================================================================
# Non-caching fallback for unreachable custom global paths
# ============================================================================

class TestGlobalPathFallback:
    def test_unreachable_custom_path_falls_back_without_caching(self, env, tmp_path):
        missing = str(tmp_path / "unreachable_share")
        sm.set_global_settings_path(missing)

        # Custom path does not exist → default served as a temporary fallback
        assert sm.get_global_settings_path() == env.global_dir
        # Crucially the fallback is NOT cached for the session
        assert sm._global_settings_path_cache is None

        # Share comes back and the retry TTL elapses → custom path is used
        os.makedirs(missing)
        sm._global_settings_path_fallback_until = 0.0
        assert sm.get_global_settings_path() == missing

    def test_fallback_window_skips_reprobe(self, env, tmp_path):
        missing = str(tmp_path / "unreachable_share2")
        sm.set_global_settings_path(missing)
        assert sm.get_global_settings_path() == env.global_dir

        # Directory now exists, but we're still inside the retry window —
        # the fallback keeps being served without re-probing the share
        os.makedirs(missing)
        assert sm._global_settings_path_fallback_until > 0.0
        assert sm.get_global_settings_path() == env.global_dir
