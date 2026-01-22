"""Unit tests for the model loader package."""
import sys
import os

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))


def test_get_format_type():
    """Test format detection for various file extensions."""
    from models.loaders.factory import get_format_type

    assert get_format_type("model.glb") == "gltf"
    assert get_format_type("model.gltf") == "gltf"
    assert get_format_type("model.fbx") == "fbx"
    assert get_format_type("model.obj") == "obj"
    assert get_format_type("model.usd") == "usd"
    assert get_format_type("model.usda") == "usd"
    assert get_format_type("model.usdc") == "usd"
    assert get_format_type("model.usdz") == "usd"
    assert get_format_type("model.npz") == "npz"
    assert get_format_type("model.dae") == "collada"
    assert get_format_type("model.xyz") == "other"


def test_is_supported_format():
    """Test format support checking."""
    from models.loaders.factory import is_supported_format

    # Supported formats
    assert is_supported_format("model.glb") is True
    assert is_supported_format("model.gltf") is True
    assert is_supported_format("model.fbx") is True
    assert is_supported_format("model.obj") is True
    assert is_supported_format("model.usd") is True
    assert is_supported_format("model.npz") is True

    # Unsupported formats
    assert is_supported_format("model.xyz") is False
    assert is_supported_format("model.txt") is False
    assert is_supported_format("model.png") is False


def test_loader_availability():
    """Test that loader availability returns a valid dict."""
    from models.loaders.factory import get_loader_availability

    availability = get_loader_availability()

    # Should be a dictionary
    assert isinstance(availability, dict)

    # Should have string keys and bool values
    for key, value in availability.items():
        assert isinstance(key, str)
        assert isinstance(value, bool)


def test_assimp_available_export():
    """Test that ASSIMP_AVAILABLE is properly exported."""
    from models.loader import ASSIMP_AVAILABLE

    # Should be a boolean
    assert isinstance(ASSIMP_AVAILABLE, bool)


def test_supported_extensions():
    """Test that SUPPORTED_EXTENSIONS contains expected formats."""
    from models.loader import SUPPORTED_EXTENSIONS

    assert '.glb' in SUPPORTED_EXTENSIONS
    assert '.fbx' in SUPPORTED_EXTENSIONS
    assert '.obj' in SUPPORTED_EXTENSIONS
    assert '.usd' in SUPPORTED_EXTENSIONS


if __name__ == "__main__":
    test_get_format_type()
    test_is_supported_format()
    test_loader_availability()
    test_assimp_available_export()
    test_supported_extensions()
    print("All loader tests passed!")
