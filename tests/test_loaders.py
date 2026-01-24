"""Unit tests for the model loader package."""
import sys
import os
import tempfile

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'python'))


class TestGetFormatType:
    """Tests for get_format_type function."""

    def test_gltf_formats(self):
        """Test GLTF/GLB format detection."""
        from models.loaders.factory import get_format_type

        assert get_format_type("model.glb") == "gltf"
        assert get_format_type("model.gltf") == "gltf"
        assert get_format_type("MODEL.GLB") == "gltf"  # Case insensitive
        assert get_format_type("/path/to/model.glb") == "gltf"

    def test_usd_formats(self):
        """Test USD format detection."""
        from models.loaders.factory import get_format_type

        assert get_format_type("model.usd") == "usd"
        assert get_format_type("model.usda") == "usd"
        assert get_format_type("model.usdc") == "usd"
        assert get_format_type("model.usdz") == "usd"

    def test_other_formats(self):
        """Test other format detection."""
        from models.loaders.factory import get_format_type

        assert get_format_type("model.fbx") == "fbx"
        assert get_format_type("model.obj") == "obj"
        assert get_format_type("model.dae") == "collada"
        assert get_format_type("model.npz") == "npz"

    def test_unknown_formats(self):
        """Test unknown format returns 'other'."""
        from models.loaders.factory import get_format_type

        assert get_format_type("model.xyz") == "other"
        assert get_format_type("model.txt") == "other"
        assert get_format_type("model.abc") == "other"


class TestIsSupportedFormat:
    """Tests for is_supported_format function."""

    def test_supported_mesh_formats(self):
        """Test mesh formats are supported."""
        from models.loaders.factory import is_supported_format

        assert is_supported_format("model.glb") is True
        assert is_supported_format("model.gltf") is True
        assert is_supported_format("model.fbx") is True
        assert is_supported_format("model.obj") is True
        assert is_supported_format("model.stl") is True
        assert is_supported_format("model.ply") is True

    def test_supported_usd_formats(self):
        """Test USD formats are supported."""
        from models.loaders.factory import is_supported_format

        assert is_supported_format("model.usd") is True
        assert is_supported_format("model.usda") is True
        assert is_supported_format("model.usdc") is True
        assert is_supported_format("model.usdz") is True

    def test_supported_other_formats(self):
        """Test other supported formats."""
        from models.loaders.factory import is_supported_format

        assert is_supported_format("model.dae") is True
        assert is_supported_format("model.3ds") is True
        assert is_supported_format("model.blend") is True
        assert is_supported_format("model.npz") is True

    def test_unsupported_formats(self):
        """Test unsupported formats."""
        from models.loaders.factory import is_supported_format

        assert is_supported_format("model.xyz") is False
        assert is_supported_format("model.txt") is False
        assert is_supported_format("model.png") is False
        assert is_supported_format("model.jpg") is False
        assert is_supported_format("model.mp4") is False

    def test_case_insensitive(self):
        """Test format checking is case insensitive."""
        from models.loaders.factory import is_supported_format

        assert is_supported_format("model.GLB") is True
        assert is_supported_format("model.FBX") is True
        assert is_supported_format("model.OBJ") is True


class TestLoaderAvailability:
    """Tests for get_loader_availability function."""

    def test_returns_dict(self):
        """Test that loader availability returns a valid dict."""
        from models.loaders.factory import get_loader_availability

        availability = get_loader_availability()
        assert isinstance(availability, dict)

    def test_has_string_keys(self):
        """Test dictionary has string keys."""
        from models.loaders.factory import get_loader_availability

        availability = get_loader_availability()
        for key in availability.keys():
            assert isinstance(key, str)

    def test_has_bool_values(self):
        """Test dictionary has boolean values."""
        from models.loaders.factory import get_loader_availability

        availability = get_loader_availability()
        for value in availability.values():
            assert isinstance(value, bool)

    def test_expected_loaders_present(self):
        """Test expected loaders are in availability dict."""
        from models.loaders.factory import get_loader_availability

        availability = get_loader_availability()
        # Check for expected loader names (lowercase)
        expected_loaders = ['usd', 'trimesh', 'assimp', 'open3d', 'smpl']
        for loader in expected_loaders:
            assert loader in availability


class TestLoadModelErrors:
    """Tests for load_model error handling."""

    def test_file_not_found(self):
        """Test FileNotFoundError for missing file."""
        from models.loaders.factory import load_model
        import pytest

        with pytest.raises(FileNotFoundError):
            load_model("/nonexistent/path/model.glb")

    def test_unsupported_format(self):
        """Test ValueError for unsupported format."""
        from models.loaders.factory import load_model
        import pytest

        # Create a temp file with unsupported extension
        with tempfile.NamedTemporaryFile(suffix='.xyz', delete=False) as f:
            temp_path = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                load_model(temp_path)
            assert "Unsupported format" in str(exc_info.value)
        finally:
            os.unlink(temp_path)


class TestSupportedExtensions:
    """Tests for SUPPORTED_EXTENSIONS constant."""

    def test_contains_common_formats(self):
        """Test that SUPPORTED_EXTENSIONS contains expected formats."""
        from models.loaders.factory import SUPPORTED_EXTENSIONS

        assert '.glb' in SUPPORTED_EXTENSIONS
        assert '.gltf' in SUPPORTED_EXTENSIONS
        assert '.fbx' in SUPPORTED_EXTENSIONS
        assert '.obj' in SUPPORTED_EXTENSIONS
        assert '.usd' in SUPPORTED_EXTENSIONS

    def test_contains_usd_variants(self):
        """Test USD variants are supported."""
        from models.loaders.factory import SUPPORTED_EXTENSIONS

        assert '.usda' in SUPPORTED_EXTENSIONS
        assert '.usdc' in SUPPORTED_EXTENSIONS
        assert '.usdz' in SUPPORTED_EXTENSIONS

    def test_contains_mesh_formats(self):
        """Test mesh-only formats are supported."""
        from models.loaders.factory import SUPPORTED_EXTENSIONS

        assert '.stl' in SUPPORTED_EXTENSIONS
        assert '.ply' in SUPPORTED_EXTENSIONS

    def test_contains_npz(self):
        """Test NPZ format for SMPL data is supported."""
        from models.loaders.factory import SUPPORTED_EXTENSIONS

        assert '.npz' in SUPPORTED_EXTENSIONS


class TestAssimpAvailable:
    """Tests for ASSIMP_AVAILABLE export."""

    def test_is_boolean(self):
        """Test that ASSIMP_AVAILABLE is properly exported."""
        from models.loader import ASSIMP_AVAILABLE

        assert isinstance(ASSIMP_AVAILABLE, bool)


class TestLoaderPriority:
    """Tests for _get_loader_priority function."""

    def test_usd_priority(self):
        """Test USD format has USD loader first."""
        from models.loaders.factory import _get_loaders, _get_loader_priority

        loaders = _get_loaders()
        priority = _get_loader_priority('usd', loaders)

        # USD loader should be first if available
        if priority:
            assert priority[0].name == 'USD'

    def test_gltf_priority(self):
        """Test GLTF format has Trimesh loader first."""
        from models.loaders.factory import _get_loaders, _get_loader_priority

        loaders = _get_loaders()
        priority = _get_loader_priority('gltf', loaders)

        # Trimesh should be first for GLTF
        if priority:
            assert priority[0].name == 'Trimesh'

    def test_fbx_priority(self):
        """Test FBX format has Assimp loader first."""
        from models.loaders.factory import _get_loaders, _get_loader_priority

        loaders = _get_loaders()
        priority = _get_loader_priority('fbx', loaders)

        # Assimp should be first for FBX
        if priority:
            assert priority[0].name == 'Assimp'

    def test_npz_priority(self):
        """Test NPZ format has SMPL loader."""
        from models.loaders.factory import _get_loaders, _get_loader_priority

        loaders = _get_loaders()
        priority = _get_loader_priority('npz', loaders)

        # SMPL should be first for NPZ
        if priority:
            assert priority[0].name == 'SMPL'


# Backward compatibility tests (original test functions)
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
    import pytest
    pytest.main([__file__, "-v"])
