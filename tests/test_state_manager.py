"""Tests for core.state_manager — ThreadSafeProperty, ApplicationState, thread safety."""

import threading
from unittest.mock import patch

import pytest

from core.state_manager import ThreadSafeProperty, ApplicationState


# ============================================================================
# ThreadSafeProperty descriptor
# ============================================================================

class TestThreadSafeProperty:
    """Test the descriptor in isolation with a minimal class."""

    def _make_class(self, default=None):
        class Obj:
            _lock = threading.RLock()
            prop = ThreadSafeProperty("prop", default)
        return Obj

    def test_default_value(self):
        Cls = self._make_class(default="hello")
        obj = Cls()
        assert obj.prop == "hello"

    def test_set_and_get(self):
        Cls = self._make_class()
        obj = Cls()
        obj.prop = 42
        assert obj.prop == 42

    def test_class_access_returns_descriptor(self):
        Cls = self._make_class()
        assert isinstance(Cls.prop, ThreadSafeProperty)

    def test_mutable_default_returns_copy(self):
        Cls = self._make_class(default=[1, 2, 3])
        obj = Cls()
        result = obj.prop
        result.append(4)
        # Original default should be unchanged
        assert obj.prop == [1, 2, 3]

    def test_mutable_value_returns_copy(self):
        Cls = self._make_class()
        obj = Cls()
        obj.prop = {"a": 1}
        result = obj.prop
        result["b"] = 2
        assert obj.prop == {"a": 1}

    def test_set_returns_copy(self):
        Cls = self._make_class(default=set())
        obj = Cls()
        obj.prop = {1, 2}
        result = obj.prop
        result.add(3)
        assert obj.prop == {1, 2}


# ============================================================================
# ApplicationState basics
# ============================================================================

class TestApplicationStateDefaults:
    def setup_method(self):
        self.state = ApplicationState()

    def test_string_defaults(self):
        assert self.state.jobname == ""
        assert self.state.shot == ""
        assert self.state.task == ""
        assert self.state.shotpath == ""
        assert self.state.user == ""

    def test_list_defaults(self):
        assert self.state.renders == []
        assert self.state.mp4_renders == []

    def test_dict_defaults(self):
        assert self.state.channels == {}

    def test_int_defaults(self):
        assert self.state.startframe == 0
        assert self.state.endframe == 0

    def test_bool_defaults(self):
        assert self.state.standalone_mode is False
        assert self.state.gallery_visible is False


class TestApplicationStateSetGet:
    def setup_method(self):
        self.state = ApplicationState()

    def test_set_get_string(self):
        self.state.jobname = "TestJob"
        assert self.state.jobname == "TestJob"

    def test_set_get_list(self):
        self.state.renders = ["render1.exr", "render2.exr"]
        assert self.state.renders == ["render1.exr", "render2.exr"]

    def test_set_get_dict(self):
        self.state.channels = {"beauty": True}
        assert self.state.channels == {"beauty": True}


# ============================================================================
# has_shot_context / has_ayon_context
# ============================================================================

class TestContextChecks:
    def setup_method(self):
        self.state = ApplicationState()

    def test_no_context(self):
        assert self.state.has_shot_context() is False
        assert self.state.has_ayon_context() is False

    def test_full_shot_context(self):
        self.state.jobname = "MyJob"
        self.state.shot = "sh0010"
        self.state.shotpath = "/path/to/shot"
        assert self.state.has_shot_context() is True
        assert self.state.has_ayon_context() is True

    def test_ayon_context_without_shot(self):
        # has_ayon_context only needs jobname + shotpath
        self.state.jobname = "MyJob"
        self.state.shotpath = "/path"
        assert self.state.has_shot_context() is False
        assert self.state.has_ayon_context() is True


# ============================================================================
# Role checks (is_admin, is_sup, has_elevated_access)
# ============================================================================

class TestRoleChecks:
    def setup_method(self):
        self.state = ApplicationState()

    def test_no_user_returns_false(self):
        assert self.state.is_admin is False
        assert self.state.is_sup is False
        assert self.state.has_elevated_access is False

    @patch("core.settings_manager.is_user_in_role", return_value=True)
    def test_admin_check(self, mock_role):
        self.state.user = "admin_user"
        assert self.state.is_admin is True

    @patch("core.settings_manager.is_user_in_role", side_effect=lambda u, r: r == "sup")
    def test_sup_check(self, mock_role):
        self.state.user = "sup_user"
        assert self.state.is_sup is True
        assert self.state.has_elevated_access is True

    @patch("core.settings_manager.is_user_in_role", return_value=True)
    def test_role_cache_invalidated_on_user_change(self, mock_role):
        self.state.user = "user1"
        _ = self.state.is_admin  # caches
        self.state.user = "user2"  # should invalidate
        _ = self.state.is_admin
        # Should have been called more than once (cache invalidated)
        assert mock_role.call_count >= 2

    @patch("core.settings_manager.is_user_in_role", return_value=False)
    def test_refresh_admin_status(self, mock_role):
        self.state.user = "someone"
        _ = self.state.is_admin
        count_before = mock_role.call_count
        self.state.refresh_admin_status()
        _ = self.state.is_admin
        assert mock_role.call_count > count_before


# ============================================================================
# initialize_from_args
# ============================================================================

class TestInitializeFromArgs:
    def test_full_args(self):
        state = ApplicationState()
        args = ["script.py", "JobName", "sh0010", "lighting", "/shot/path", "john", "combined"]
        state.initialize_from_args(args)
        assert state.jobname == "JobName"
        assert state.shot == "sh0010"
        assert state.task == "lighting"
        assert state.shotpath == "/shot/path"
        assert state.user == "john"
        assert state.output_subdirectory == "combined"
        assert state.standalone_mode is False

    def test_standalone_mode(self):
        state = ApplicationState()
        state.initialize_from_args(["script.py"])
        assert state.standalone_mode is True
        assert state.user != ""  # gets from environment


# ============================================================================
# Cross-tab awareness helpers
# ============================================================================

class TestCrossTabHelpers:
    def setup_method(self):
        self.state = ApplicationState()

    def test_add_recent_output(self):
        self.state.add_recent_output("/output/img1.png")
        self.state.add_recent_output("/output/img2.png")
        outputs = self.state.comfyui_recent_outputs
        assert outputs[0] == "/output/img2.png"
        assert outputs[1] == "/output/img1.png"

    def test_add_recent_output_deduplicates(self):
        self.state.add_recent_output("/output/img1.png")
        self.state.add_recent_output("/output/img2.png")
        self.state.add_recent_output("/output/img1.png")
        outputs = self.state.comfyui_recent_outputs
        assert len(outputs) == 2
        assert outputs[0] == "/output/img1.png"

    def test_add_recent_output_trims_to_max(self):
        for i in range(25):
            self.state.add_recent_output(f"/output/img{i}.png")
        assert len(self.state.comfyui_recent_outputs) == 20

    def test_update_session_stats(self):
        self.state.update_session_stats(outputs_added=3, time_seconds=10.5, job_completed=True)
        stats = self.state.get_session_stats()
        assert stats["total_generated"] == 3
        assert stats["total_time_seconds"] == 10.5
        assert stats["jobs_completed"] == 1

    def test_session_stats_accumulate(self):
        self.state.update_session_stats(outputs_added=2, time_seconds=5.0)
        self.state.update_session_stats(outputs_added=3, time_seconds=7.0, job_completed=True)
        stats = self.state.get_session_stats()
        assert stats["total_generated"] == 5
        assert stats["total_time_seconds"] == 12.0

    def test_increment_gallery_new_count(self):
        self.state.increment_gallery_new_count(3)
        self.state.increment_gallery_new_count(2)
        assert self.state.gallery_new_since_view == 5

    def test_reset_gallery_new_count(self):
        self.state.increment_gallery_new_count(5)
        self.state.reset_gallery_new_count()
        assert self.state.gallery_new_since_view == 0

    def test_generation_history(self):
        self.state.add_to_generation_history({"workflow_name": "upscale", "generation_count": 5})
        self.state.add_to_generation_history({"workflow_name": "upscale", "generation_count": 10})
        defaults = self.state.get_workflow_defaults("upscale")
        assert defaults["uses"] == 2

    def test_workflow_defaults_empty(self):
        assert self.state.get_workflow_defaults("nonexistent") == {}


# ============================================================================
# Thread safety
# ============================================================================

class TestThreadSafety:
    def test_concurrent_reads_and_writes(self):
        state = ApplicationState()
        errors = []

        def writer():
            try:
                for i in range(200):
                    state.jobname = f"job_{i}"
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(200):
                    _ = state.jobname
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"

    def test_concurrent_list_mutations(self):
        state = ApplicationState()
        errors = []

        def add_outputs():
            try:
                for i in range(50):
                    state.add_recent_output(f"/output/{threading.current_thread().name}_{i}.png")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_outputs, name=f"t{i}") for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(state.comfyui_recent_outputs) <= 20

    def test_reentrant_lock(self):
        """RLock should allow same thread to acquire multiple times."""
        state = ApplicationState()
        state.jobname = "test"
        # Accessing multiple properties from same thread should not deadlock
        with state._lock:
            _ = state.jobname
            _ = state.shot
            state.task = "lighting"
        assert state.task == "lighting"
