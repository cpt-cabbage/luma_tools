"""Tests for services/mp4_maker.py pure helper functions."""

import pytest
from services.mp4_maker import (
    get_crf_value,
    get_output_filename,
    get_quality_description,
)


class TestGetCrfValue:
    def test_high_quality(self):
        assert get_crf_value(0) == 18

    def test_medium_quality(self):
        assert get_crf_value(1) == 23

    def test_low_quality(self):
        assert get_crf_value(2) == 28

    def test_invalid_index_defaults_to_medium(self):
        assert get_crf_value(99) == 23
        assert get_crf_value(-1) == 23


class TestGetOutputFilename:
    def test_standard(self):
        assert get_output_filename("main", "sh0010") == "sh0010_main.mp4"

    def test_empty_shot(self):
        assert get_output_filename("render", "") == "_render.mp4"

    def test_empty_render(self):
        assert get_output_filename("", "sh0010") == "sh0010_.mp4"


class TestGetQualityDescription:
    def test_high(self):
        assert get_quality_description(0) == "High (CRF 18)"

    def test_medium(self):
        assert get_quality_description(1) == "Medium (CRF 23)"

    def test_low(self):
        assert get_quality_description(2) == "Low (CRF 28)"

    def test_invalid_defaults_to_medium(self):
        assert get_quality_description(99) == "Medium (CRF 23)"


class TestCopyMp4ToGallery:
    def _copy(self, tmp_path, monkeypatch, user):
        """Run copy_mp4_to_gallery against a temp gallery base."""
        import services.mp4_maker as mp4_mod

        gallery_base = tmp_path / "gallery"
        gallery_base.mkdir()
        monkeypatch.setattr(
            "core.settings_manager.get_setting",
            lambda key: str(gallery_base) if key == "network_output_path" else None,
        )

        mp4_path = tmp_path / "sh0010_main.mp4"
        mp4_path.write_bytes(b"fake mp4")

        success, result = mp4_mod.copy_mp4_to_gallery(
            mp4_path=str(mp4_path),
            user=user,
            shot="sh0010",
            source_path="X:/renders/main.%04d.exr",
            frame_range=(1001, 1050),
            quality_index=0,
            burn_in_timecode=False,
        )
        return success, result, gallery_base

    def test_dotted_username_keeps_dot(self, tmp_path, monkeypatch):
        """Regression: 'christophe.leyder' MP4s landed in 'christophe_leyder'
        — a folder the gallery (which allows dots in usernames) never shows,
        while the log still reported success."""
        success, result, gallery_base = self._copy(tmp_path, monkeypatch, "christophe.leyder")
        assert success, result
        assert (gallery_base / "christophe.leyder" / "sh0010_main.mp4").is_file()
        assert not (gallery_base / "christophe_leyder").exists()

    def test_unsafe_username_is_sanitized(self, tmp_path, monkeypatch):
        """Traversal-style names still get sanitized to a safe folder."""
        success, result, gallery_base = self._copy(tmp_path, monkeypatch, "../evil")
        assert success, result
        # Must NOT escape the gallery base
        assert not (tmp_path / "evil").exists()
        assert (gallery_base / ".._evil" / "sh0010_main.mp4").is_file()

    def test_empty_username_uses_standalone(self, tmp_path, monkeypatch):
        success, result, gallery_base = self._copy(tmp_path, monkeypatch, "")
        assert success, result
        assert (gallery_base / "standalone" / "sh0010_main.mp4").is_file()
