"""Unit tests for animation controller."""
import sys
import os

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))

# Skip if Qt is not available (CI environments)
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


def test_controller_initialization():
    """Test AnimationController initializes with correct defaults."""
    if not QT_AVAILABLE:
        print("Skipping test_controller_initialization - Qt not available")
        return

    from models.animation_controller import AnimationController

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

    from models.animation_controller import AnimationController

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

    from models.animation_controller import AnimationController

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

    from models.animation_controller import AnimationController

    controller = AnimationController()
    assert controller.animation_names == []


def test_play_pause_without_animation():
    """Test play/pause does nothing without animation."""
    if not QT_AVAILABLE:
        print("Skipping test_play_pause_without_animation - Qt not available")
        return

    from models.animation_controller import AnimationController

    controller = AnimationController()

    # Should not crash, just do nothing
    controller.play()
    assert controller.is_playing is False

    controller.pause()
    assert controller.is_playing is False


if __name__ == "__main__":
    test_controller_initialization()
    test_speed_bounds()
    test_loop_property()
    test_animation_names_empty()
    test_play_pause_without_animation()
    print("All animation controller tests passed!")
