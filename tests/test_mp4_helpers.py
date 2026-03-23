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
