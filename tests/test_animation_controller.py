"""Unit tests for animation controller."""
import sys
import os

import pytest

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))

# Skip if Qt is not available (CI environments)
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

# Pytest marker for tests requiring Qt
requires_qt = pytest.mark.skipif(not QT_AVAILABLE, reason="Qt not available")


@requires_qt
class TestAnimationControllerInit:
    """Tests for AnimationController initialization."""

    def test_default_values(self):
        """Test AnimationController initializes with correct defaults."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()

        assert controller.current_time == 0.0
        assert controller.is_playing is False
        assert controller.loop is True
        assert controller.speed == 1.0
        assert controller.duration == 0.0
        assert controller.current_animation is None

    def test_animation_names_empty(self):
        """Test animation_names returns empty list when no animations."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        assert controller.animation_names == []

    def test_speed_options_defined(self):
        """Test SPEED_OPTIONS are defined."""
        from geo.animation_controller import AnimationController

        assert hasattr(AnimationController, 'SPEED_OPTIONS')
        assert len(AnimationController.SPEED_OPTIONS) > 0
        assert 1.0 in AnimationController.SPEED_OPTIONS


@requires_qt
class TestSpeedProperty:
    """Tests for speed property."""

    def test_minimum_bound(self):
        """Test speed is bounded at minimum 0.1."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.speed = 0.05  # Below minimum
        assert controller.speed >= 0.1

    def test_maximum_bound(self):
        """Test speed is bounded at maximum 10.0."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.speed = 20.0  # Above maximum
        assert controller.speed <= 10.0

    def test_valid_speed(self):
        """Test valid speed values are set correctly."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.speed = 2.0
        assert controller.speed == 2.0

        controller.speed = 0.5
        assert controller.speed == 0.5

    def test_boundary_values(self):
        """Test boundary values are accepted."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.speed = 0.1
        assert controller.speed == 0.1

        controller.speed = 10.0
        assert controller.speed == 10.0


@requires_qt
class TestLoopProperty:
    """Tests for loop property."""

    def test_default_loop_enabled(self):
        """Test loop is enabled by default."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        assert controller.loop is True

    def test_set_loop_false(self):
        """Test setting loop to false."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.loop = False
        assert controller.loop is False

    def test_toggle_loop(self):
        """Test toggling loop on and off."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.loop = False
        assert controller.loop is False
        controller.loop = True
        assert controller.loop is True


@requires_qt
class TestPlaybackWithoutAnimation:
    """Tests for playback without animation loaded."""

    def test_play_without_animation(self):
        """Test play does nothing without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.play()
        assert controller.is_playing is False

    def test_pause_without_animation(self):
        """Test pause without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.pause()
        assert controller.is_playing is False

    def test_toggle_play_without_animation(self):
        """Test toggle_play without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.toggle_play()
        # Should do nothing, remain not playing
        assert controller.is_playing is False

    def test_stop_without_animation(self):
        """Test stop without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.stop()
        assert controller.is_playing is False
        assert controller.current_time == 0.0

    def test_seek_without_animation(self):
        """Test seek does nothing without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.seek(5.0)
        # Should remain at 0
        assert controller.current_time == 0.0

    def test_step_forward_without_animation(self):
        """Test step_forward without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.step_forward()
        # Should do nothing
        assert controller.current_time == 0.0

    def test_step_backward_without_animation(self):
        """Test step_backward without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.step_backward()
        # Should do nothing
        assert controller.current_time == 0.0


@requires_qt
class TestSetAnimations:
    """Tests for set_animations method."""

    def test_set_empty_animations(self):
        """Test setting empty animation list."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.set_animations([])
        assert controller.current_animation is None
        assert controller.animation_names == []

    def test_duration_without_animation(self):
        """Test duration is 0 without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        assert controller.duration == 0.0


@requires_qt
class TestGetBoneTransforms:
    """Tests for get_bone_transforms method."""

    def test_empty_transforms_without_animation(self):
        """Test get_bone_transforms returns empty dict without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        transforms = controller.get_bone_transforms()
        assert transforms == {}


@requires_qt
class TestSeekNormalized:
    """Tests for seek_normalized method."""

    def test_seek_normalized_without_animation(self):
        """Test seek_normalized does nothing without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.seek_normalized(0.5)
        # Should do nothing
        assert controller.current_time == 0.0


@requires_qt
class TestNavigationMethods:
    """Tests for go_to_start and go_to_end methods."""

    def test_go_to_start_without_animation(self):
        """Test go_to_start without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.go_to_start()
        assert controller.current_time == 0.0

    def test_go_to_end_without_animation(self):
        """Test go_to_end without animation."""
        from geo.animation_controller import AnimationController

        controller = AnimationController()
        controller.go_to_end()
        # Should do nothing
        assert controller.current_time == 0.0


# Backward compatibility - original test functions
def test_controller_initialization():
    """Test AnimationController initializes with correct defaults."""
    if not QT_AVAILABLE:
        print("Skipping test_controller_initialization - Qt not available")
        return

    from geo.animation_controller import AnimationController

    controller = AnimationController()

    assert controller.current_time == 0.0
    assert controller.is_playing is False
    assert controller.loop is True
    assert controller.speed == 1.0
    assert controller.duration == 0.0
    assert controller.current_animation is None


def test_speed_bounds():
    """Test that speed is bounded correctly."""
    if not QT_AVAILABLE:
        print("Skipping test_speed_bounds - Qt not available")
        return

    from geo.animation_controller import AnimationController

    controller = AnimationController()

    # Test minimum bound
    controller.speed = 0.05  # Below minimum
    assert controller.speed >= 0.1

    # Test maximum bound
    controller.speed = 20.0  # Above maximum
    assert controller.speed <= 10.0

    # Test valid values
    controller.speed = 2.0
    assert controller.speed == 2.0


def test_loop_property():
    """Test loop property get/set."""
    if not QT_AVAILABLE:
        print("Skipping test_loop_property - Qt not available")
        return

    from geo.animation_controller import AnimationController

    controller = AnimationController()

    assert controller.loop is True
    controller.loop = False
    assert controller.loop is False
    controller.loop = True
    assert controller.loop is True


def test_animation_names_empty():
    """Test animation_names returns empty list when no animations."""
    if not QT_AVAILABLE:
        print("Skipping test_animation_names_empty - Qt not available")
        return

    from geo.animation_controller import AnimationController

    controller = AnimationController()
    assert controller.animation_names == []


def test_play_pause_without_animation():
    """Test play/pause does nothing without animation."""
    if not QT_AVAILABLE:
        print("Skipping test_play_pause_without_animation - Qt not available")
        return

    from geo.animation_controller import AnimationController

    controller = AnimationController()

    # Should not crash, just do nothing
    controller.play()
    assert controller.is_playing is False

    controller.pause()
    assert controller.is_playing is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
