"""Tests for services/render_service.py pure functions."""

import os
import pytest
from services.render_service import build_oiio_command, get_pass_file_path


# ============================================================================
# build_oiio_command
# ============================================================================

class TestBuildOiioCommand:
    def test_basic_passes(self):
        passes = {
            "diffuse": ["diffuse.R", "diffuse.G", "diffuse.B"],
        }
        result = build_oiio_command(passes, "/path/denoised.exr", "/path/raw.exr", "/path/out.exr")
        assert '"/path/denoised.exr"' in result
        assert '"/path/out.exr"' in result
        assert "diffuse.R,diffuse.G,diffuse.B" in result

    def test_empty_passes(self):
        result = build_oiio_command({}, "/d.exr", "/r.exr", "/o.exr")
        assert '"/d.exr"' in result
        assert "-o" in result
        assert '"/o.exr"' in result

    def test_crypto_materials_only(self):
        passes = {"CryptoMaterials": ["crypto"]}
        result = build_oiio_command(passes, "/d.exr", "/r.exr", "/o.exr")
        assert "CryptoMaterials00.R" in result
        assert '"/r.exr"' in result  # raw render path included for crypto passes

    def test_crypto_primitives_only(self):
        passes = {"CryptoPrimitives": ["crypto"]}
        result = build_oiio_command(passes, "/d.exr", "/r.exr", "/o.exr")
        assert "CryptoPrimitives00.R" in result

    def test_both_crypto(self):
        passes = {"CryptoMaterials": ["m"], "CryptoPrimitives": ["p"]}
        result = build_oiio_command(passes, "/d.exr", "/r.exr", "/o.exr")
        assert "CryptoMaterials00.R" in result
        assert "CryptoPrimitives00.R" in result

    def test_normal_pass(self):
        passes = {"normal": ["normal.x"]}
        result = build_oiio_command(passes, "/d.exr", "/r.exr", "/o.exr")
        assert "normal.x,normal.y,normal.z" in result

    def test_paths_with_spaces_are_quoted(self):
        result = build_oiio_command({}, "/path with spaces/d.exr", "/r.exr", "/o.exr")
        assert '"/path with spaces/d.exr"' in result

    def test_chappend_and_chnames_always_present(self):
        result = build_oiio_command({}, "/d.exr", "/r.exr", "/o.exr")
        assert "--chappend" in result
        assert "--chnames" in result
        assert "R,G,B,A" in result

    def test_not_denoised_uses_raw_path_for_beauty(self):
        """When is_denoised=False, beauty should be read from raw render path."""
        passes = {"diffuse": ["diffuse.R", "diffuse.G", "diffuse.B"]}
        result = build_oiio_command(passes, "/d.exr", "/r.exr", "/o.exr", is_denoised=False)
        # Denoised path should be replaced by raw path
        assert '"/d.exr"' not in result
        assert '"/r.exr"' in result

    def test_denoised_uses_denoised_path(self):
        """When is_denoised=True (default), beauty is read from denoised path."""
        passes = {"diffuse": ["diffuse.R", "diffuse.G", "diffuse.B"]}
        result = build_oiio_command(passes, "/d.exr", "/r.exr", "/o.exr", is_denoised=True)
        assert '"/d.exr"' in result


# ============================================================================
# get_pass_file_path
# ============================================================================

class TestGetPassFilePath:
    def test_standard(self):
        result = get_pass_file_path("/work/lighting", "main")
        expected = os.path.join("/work/lighting", "shot_data", "main.json")
        assert result == expected

    def test_render_name_with_dots(self):
        result = get_pass_file_path("/work", "render.v001")
        assert result.endswith("render.v001.json")
