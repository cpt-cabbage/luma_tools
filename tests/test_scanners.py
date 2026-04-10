"""Tests for services.scanners — FileScanner strategy pattern, factory, scan_files."""

from pathlib import Path

import pytest

from services.scanners import (
    FileScanner,
    RenderScanner,
    HIPScanner,
    CompScanner,
    ImageScanner,
    VideoScanner,
    ModelScanner,
    USDScanner,
    get_scanner,
    scan_files,
    _SCANNER_REGISTRY,
)


# ============================================================================
# Scanner extensions
# ============================================================================

class TestScannerExtensions:
    def test_render_extensions(self):
        s = RenderScanner()
        assert ".exr" in s.extensions
        assert ".png" in s.extensions
        assert ".jpg" in s.extensions

    def test_hip_extensions(self):
        s = HIPScanner()
        assert ".hip" in s.extensions
        assert ".hipnc" in s.extensions

    def test_comp_extensions(self):
        s = CompScanner()
        assert ".nk" in s.extensions
        assert ".comp" in s.extensions

    def test_image_extensions(self):
        s = ImageScanner()
        assert ".png" in s.extensions
        assert ".webp" in s.extensions

    def test_video_extensions(self):
        s = VideoScanner()
        assert ".mp4" in s.extensions
        assert ".mov" in s.extensions

    def test_model_extensions(self):
        s = ModelScanner()
        assert ".usd" in s.extensions
        assert ".fbx" in s.extensions
        assert ".glb" in s.extensions

    def test_usd_extensions(self):
        s = USDScanner()
        assert ".usd" in s.extensions
        assert ".usdc" in s.extensions


# ============================================================================
# Scanning
# ============================================================================

class TestRenderScanner:
    def test_scan_empty_dir(self, tmp_path):
        s = RenderScanner()
        assert s.scan(str(tmp_path)) == []

    def test_scan_finds_renders(self, tmp_path):
        (tmp_path / "beauty.0001.exr").write_text("")
        (tmp_path / "beauty.0002.exr").write_text("")
        (tmp_path / "notes.txt").write_text("")
        s = RenderScanner(recursive=False)
        result = s.scan(str(tmp_path))
        assert len(result) == 2
        assert all(p.suffix == ".exr" for p in result)

    def test_scan_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.exr").write_text("")
        (sub / "b.png").write_text("")
        s = RenderScanner(recursive=True)
        result = s.scan(str(tmp_path))
        assert len(result) == 2

    def test_scan_nonexistent_dir(self):
        s = RenderScanner()
        assert s.scan("/nonexistent/path") == []

    def test_scan_none(self):
        s = RenderScanner()
        assert s.scan("") == []

    def test_count(self, tmp_path):
        (tmp_path / "a.exr").write_text("")
        (tmp_path / "b.png").write_text("")
        s = RenderScanner(recursive=False)
        assert s.count(str(tmp_path)) == 2


class TestHIPScanner:
    def test_requires_lookdev(self, tmp_path):
        (tmp_path / "scene_lookdev_v01.hip").write_text("")
        (tmp_path / "scene_lighting_v01.hip").write_text("")
        s = HIPScanner(recursive=False, require_lookdev=True)
        result = s.scan(str(tmp_path))
        assert len(result) == 1
        assert "lookdev" in result[0].name

    def test_no_lookdev_filter(self, tmp_path):
        (tmp_path / "scene_lookdev_v01.hip").write_text("")
        (tmp_path / "scene_lighting_v01.hip").write_text("")
        s = HIPScanner(recursive=False, require_lookdev=False)
        assert len(s.scan(str(tmp_path))) == 2


class TestCompScanner:
    def test_requires_compositing(self, tmp_path):
        (tmp_path / "shot_Compositing_v01.nk").write_text("")
        (tmp_path / "shot_baking_v01.nk").write_text("")
        (tmp_path / "shot_random.nk").write_text("")
        s = CompScanner(recursive=False)
        result = s.scan(str(tmp_path))
        assert len(result) == 1
        assert "Compositing" in result[0].name

    def test_excludes_baking(self, tmp_path):
        (tmp_path / "shot_Compositing_baking.nk").write_text("")
        s = CompScanner(recursive=False)
        assert len(s.scan(str(tmp_path))) == 0


# ============================================================================
# scan_and_filter
# ============================================================================

class TestScanAndFilter:
    def test_name_contains(self, tmp_path):
        (tmp_path / "beauty.exr").write_text("")
        (tmp_path / "diffuse.exr").write_text("")
        s = RenderScanner(recursive=False)
        result = s.scan_and_filter(str(tmp_path), name_contains="beauty")
        assert len(result) == 1

    def test_name_excludes(self, tmp_path):
        (tmp_path / "beauty.exr").write_text("")
        (tmp_path / "thumbnail.exr").write_text("")
        s = RenderScanner(recursive=False)
        result = s.scan_and_filter(str(tmp_path), name_excludes="thumbnail")
        assert len(result) == 1

    def test_predicate(self, tmp_path):
        (tmp_path / "small.exr").write_bytes(b"x" * 10)
        (tmp_path / "big.exr").write_bytes(b"x" * 1000)
        s = RenderScanner(recursive=False)
        result = s.scan_and_filter(str(tmp_path), predicate=lambda p: p.stat().st_size > 100)
        assert len(result) == 1
        assert result[0].name == "big.exr"


# ============================================================================
# Factory
# ============================================================================

class TestGetScanner:
    def test_all_registered_types(self):
        for name in _SCANNER_REGISTRY:
            scanner = get_scanner(name)
            assert isinstance(scanner, FileScanner)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown scanner type"):
            get_scanner("unknown_type")

    def test_kwargs_passed(self):
        scanner = get_scanner("hip", require_lookdev=False)
        assert scanner.require_lookdev is False


class TestScanFiles:
    def test_convenience_function(self, tmp_path):
        (tmp_path / "test.exr").write_text("")
        result = scan_files(str(tmp_path), "render", recursive=False)
        assert len(result) == 1
