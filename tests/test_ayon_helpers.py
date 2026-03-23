"""Tests for ayon/service.py pure helper functions (no AYON dependency needed)."""

import pytest
from ayon.service import (
    _resolve_task_type,
    build_ayon_metadata_filename,
    convert_to_ayon_folder_path,
    TASK_TYPE_MAP,
)


# ============================================================================
# _resolve_task_type
# ============================================================================

class TestResolveTaskType:
    def test_explicit_task_type_returned(self):
        assert _resolve_task_type("lighting", "CustomType") == "CustomType"

    def test_known_task_compositing(self):
        assert _resolve_task_type("compositing") == "Compositing"

    def test_known_alias_comp(self):
        assert _resolve_task_type("comp") == "Compositing"

    def test_known_task_lighting(self):
        assert _resolve_task_type("lighting") == "Lighting"

    def test_known_alias_lgt(self):
        assert _resolve_task_type("lgt") == "Lighting"

    def test_known_task_lookdev(self):
        assert _resolve_task_type("lookdev") == "Lookdev"

    def test_known_task_animation(self):
        assert _resolve_task_type("animation") == "Animation"

    def test_unknown_task_capitalized(self):
        assert _resolve_task_type("texturing") == "Texturing"

    def test_none_task_returns_compositing(self):
        assert _resolve_task_type(None) == "Compositing"

    def test_empty_string_returns_compositing(self):
        assert _resolve_task_type("") == "Compositing"

    def test_case_insensitive(self):
        assert _resolve_task_type("LIGHTING") == "Lighting"
        assert _resolve_task_type("Compositing") == "Compositing"


# ============================================================================
# build_ayon_metadata_filename
# ============================================================================

class TestBuildAyonMetadataFilename:
    def test_no_prefix(self):
        assert build_ayon_metadata_filename("renderMain") == "ayon_renderMain.json"

    def test_with_prefix(self):
        assert build_ayon_metadata_filename("renderMain", "mp4") == "ayon_mp4_renderMain.json"

    def test_comfyui_prefix(self):
        assert build_ayon_metadata_filename("myProduct", "comfyui") == "ayon_comfyui_myProduct.json"

    def test_empty_prefix_treated_as_no_prefix(self):
        assert build_ayon_metadata_filename("test", "") == "ayon_test.json"


# ============================================================================
# convert_to_ayon_folder_path
# ============================================================================

class TestConvertToAyonFolderPath:
    def test_standard_path_with_work(self):
        result = convert_to_ayon_folder_path(
            "W:/LumaRND/shots/ChiefChickenTest/sh0010/work",
            "LumaRND"
        )
        assert result == "/shots/ChiefChickenTest/sh0010"

    def test_path_with_backslashes(self):
        result = convert_to_ayon_folder_path(
            "W:\\LumaRND\\shots\\ChiefChickenTest\\sh0010\\work",
            "LumaRND"
        )
        assert result == "/shots/ChiefChickenTest/sh0010"

    def test_path_without_work(self):
        result = convert_to_ayon_folder_path(
            "W:/LumaRND/shots/ChiefChickenTest/sh0010",
            "LumaRND"
        )
        assert result == "/shots/ChiefChickenTest/sh0010"

    def test_project_name_not_in_path(self):
        result = convert_to_ayon_folder_path(
            "W:/OtherProject/shots/sh0010/work",
            "LumaRND"
        )
        # Should return the path as-is (with work removed) since project not found
        assert "sh0010" in result

    def test_path_with_work_in_middle(self):
        result = convert_to_ayon_folder_path(
            "W:/LumaRND/shots/TestShot/sh0010/work/lighting/renders",
            "LumaRND"
        )
        assert result == "/shots/TestShot/sh0010"
