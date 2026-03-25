"""Tests for Pass Builder tab helper functions and AYON product matching logic."""

import pytest
from unittest.mock import patch


# ============================================================================
# PassBuilderTab._parse_render_product  (static method)
# ============================================================================

class TestParseRenderProduct:
    """Test CamelCase parsing of AYON render product names."""

    @staticmethod
    def _parse(name):
        from ui.tabs.pass_builder_tab import PassBuilderTab
        return PassBuilderTab._parse_render_product(name)

    def test_standard_product(self):
        assert self._parse("renderLightingMain") == ("lighting", "Main")

    def test_lookdev(self):
        assert self._parse("renderLookdevBeauty") == ("lookdev", "Beauty")

    def test_animation(self):
        assert self._parse("renderAnimationGirrafe") == ("animation", "Girrafe")

    def test_compositing(self):
        assert self._parse("renderCompositingFinal") == ("compositing", "Final")

    def test_multi_word_variant(self):
        """Variant with multiple capital-initial words."""
        assert self._parse("renderLightingMainExtra") == ("lighting", "MainExtra")

    def test_variant_with_digits(self):
        """Task or variant containing digits after lowercase."""
        task, variant = self._parse("renderLookdev2dMain")
        assert task == "lookdev2d"
        assert variant == "Main"

    def test_empty_string(self):
        assert self._parse("") == ("", "")

    def test_none(self):
        assert self._parse(None) == ("", "")

    def test_not_render_prefix(self):
        assert self._parse("reviewLightingMain") == ("", "")

    def test_just_render(self):
        assert self._parse("render") == ("", "")

    def test_render_with_one_part(self):
        """Only task, no variant — not enough parts."""
        assert self._parse("renderLighting") == ("", "")

    def test_lowercase_after_render(self):
        """No uppercase after 'render' — regex finds no parts."""
        assert self._parse("renderlightingmain") == ("", "")

    def test_single_char_task_and_variant(self):
        task, variant = self._parse("renderAB")
        assert task == "a"
        assert variant == "B"


# ============================================================================
# find_product_for_render  (product matching with pre-supplied products list)
# ============================================================================

class TestFindProductForRender:
    """Test the 4-step product matching strategy.

    Uses the `products` parameter to supply a mock product list,
    avoiding any AYON API calls. Patches AYON_AVAILABLE so the
    matching logic runs even without the ayon_api package.
    """

    @staticmethod
    def _find(render_name, products):
        with patch("ayon.service.AYON_AVAILABLE", True):
            from ayon.service import find_product_for_render
            return find_product_for_render(
                "TestProject", "/shots/sh0010", render_name, products=products
            )

    @pytest.fixture
    def products(self):
        return [
            {"name": "renderLightingMain", "productType": "render"},
            {"name": "renderLightingGirrafe", "productType": "render"},
            {"name": "renderLookdevBeauty", "productType": "render"},
            {"name": "reviewMain", "productType": "review"},
        ]

    def test_exact_match(self, products):
        assert self._find("renderLightingMain", products) == "renderLightingMain"

    def test_case_insensitive_match(self, products):
        assert self._find("renderlightingmain", products) == "renderLightingMain"

    def test_suffix_match_main(self, products):
        """File 'Main' matches product 'renderLightingMain' via suffix."""
        assert self._find("Main", products) == "renderLightingMain"

    def test_suffix_match_girrafe(self, products):
        assert self._find("Girrafe", products) == "renderLightingGirrafe"

    def test_suffix_match_case_insensitive(self, products):
        assert self._find("main", products) == "renderLightingMain"

    def test_suffix_prefers_render_type(self):
        """When both render and non-render products match, prefer render type."""
        products = [
            {"name": "renderLightingMain", "productType": "render"},
            {"name": "plateMain", "productType": "plate"},
        ]
        assert self._find("Main", products) == "renderLightingMain"

    def test_suffix_prefers_shortest(self):
        """When multiple suffix matches, prefer shortest (most specific)."""
        products = [
            {"name": "renderLightingMain", "productType": "render"},
            {"name": "renderLightingExtraMain", "productType": "render"},
        ]
        assert self._find("Main", products) == "renderLightingMain"

    def test_prefix_match(self, products):
        """Render name starts with a product name."""
        assert self._find("renderLightingMain_v2", products) == "renderLightingMain"

    def test_prefix_longest_match(self):
        """When multiple prefix matches, prefer longest."""
        products = [
            {"name": "render", "productType": "render"},
            {"name": "renderLighting", "productType": "render"},
            {"name": "renderLightingMain", "productType": "render"},
        ]
        assert self._find("renderLightingMain_v2", products) == "renderLightingMain"

    def test_no_match_returns_original(self, products):
        assert self._find("nonexistent", products) == "nonexistent"

    def test_empty_render_name(self, products):
        """Empty string suffix-matches all products; shortest render product wins."""
        result = self._find("", products)
        assert result in [p["name"] for p in products if p["productType"] == "render"]

    def test_empty_products(self):
        assert self._find("Main", products=[]) == "Main"

    def test_suffix_match_beauty(self, products):
        """Cross-task match: 'Beauty' matches renderLookdevBeauty."""
        assert self._find("Beauty", products) == "renderLookdevBeauty"
