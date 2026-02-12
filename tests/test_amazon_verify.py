"""Tests for Amazon product verification.

Covers: query normalization, title similarity, VerifiedProduct fields,
serialization. No browser/API calls.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


class TestNormalizeSearchQuery(unittest.TestCase):
    """_normalize_search_query cleans up queries for Amazon search."""

    def test_normalize_basic(self):
        from tools.amazon_verify import _normalize_search_query
        result = _normalize_search_query("Sony", "Sony WH-1000XM5")
        self.assertEqual(result, "Sony WH-1000XM5")

    def test_normalize_strips_parens(self):
        from tools.amazon_verify import _normalize_search_query
        result = _normalize_search_query("Bose", "Bose QC45 (2024 Edition)")
        self.assertEqual(result, "Bose QC45")

    def test_normalize_collapses_whitespace(self):
        from tools.amazon_verify import _normalize_search_query
        result = _normalize_search_query("JBL", "JBL  Flip   6")
        self.assertEqual(result, "JBL Flip 6")

    def test_normalize_empty_brand(self):
        from tools.amazon_verify import _normalize_search_query
        result = _normalize_search_query("", "WH-1000XM5")
        self.assertEqual(result, "WH-1000XM5")

    def test_normalize_brand_prepended_if_missing(self):
        from tools.amazon_verify import _normalize_search_query
        result = _normalize_search_query("Sony", "WH-1000XM5")
        self.assertEqual(result, "Sony WH-1000XM5")

    def test_normalize_removes_special_chars(self):
        from tools.amazon_verify import _normalize_search_query
        result = _normalize_search_query("Away", 'Away The Carry-On "This good-looking"')
        # Quotes removed, parens stripped, clean result
        self.assertNotIn('"', result)
        self.assertIn("Away", result)

    def test_normalize_no_double_brand(self):
        """If product_name already starts with brand, don't prepend again."""
        from tools.amazon_verify import _normalize_search_query
        result = _normalize_search_query("Apple", "Apple AirPods Pro 2")
        self.assertEqual(result.count("Apple"), 1)


class TestTitleSimilarity(unittest.TestCase):
    """_title_similarity score checks."""

    def test_title_similarity_exact(self):
        from tools.amazon_verify import _title_similarity
        score = _title_similarity("Sony WH-1000XM5", "Sony WH-1000XM5")
        self.assertGreater(score, 0.9)

    def test_title_similarity_pdp_extra(self):
        from tools.amazon_verify import _title_similarity
        score = _title_similarity(
            "Sony WH-1000XM5",
            "Sony WH-1000XM5 Wireless Noise Cancelling Headphones (Black)",
        )
        self.assertGreater(score, 0.5)

    def test_title_similarity_mismatch(self):
        from tools.amazon_verify import _title_similarity
        score = _title_similarity(
            "Samsonite Freeform Carry-On",
            "JBL Flip 6 Portable Bluetooth Speaker",
        )
        self.assertLess(score, 0.3)

    def test_title_similarity_empty(self):
        from tools.amazon_verify import _title_similarity
        self.assertEqual(_title_similarity("", "something"), 0.0)
        self.assertEqual(_title_similarity("something", ""), 0.0)


class TestVerifiedProductFields(unittest.TestCase):
    """VerifiedProduct dataclass field checks."""

    def test_verified_product_short_url_field(self):
        from tools.amazon_verify import VerifiedProduct
        vp = VerifiedProduct(product_name="Test")
        self.assertEqual(vp.affiliate_short_url, "")

    def test_verified_product_with_short_url(self):
        from tools.amazon_verify import VerifiedProduct
        vp = VerifiedProduct(
            product_name="Test",
            affiliate_short_url="https://amzn.to/abc123",
        )
        self.assertEqual(vp.affiliate_short_url, "https://amzn.to/abc123")


class TestWriteVerified(unittest.TestCase):
    """Serialization includes all fields."""

    def test_write_verified_includes_short_url(self):
        from tools.amazon_verify import VerifiedProduct, write_verified
        vp = VerifiedProduct(
            product_name="Test Product",
            brand="TestBrand",
            asin="B0TEST1234",
            affiliate_short_url="https://amzn.to/xyz",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verified.json"
            write_verified([vp], path)
            data = json.loads(path.read_text())
        product = data["products"][0]
        self.assertEqual(product["affiliate_short_url"], "https://amzn.to/xyz")
        self.assertEqual(product["product_name"], "Test Product")

    def test_write_verified_includes_error(self):
        from tools.amazon_verify import VerifiedProduct, write_verified
        vp = VerifiedProduct(
            product_name="Test",
            error="ACTION_REQUIRED: SiteStripe not visible",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verified.json"
            write_verified([vp], path)
            data = json.loads(path.read_text())
        self.assertIn("error", data["products"][0])


class TestFindFirstVisible(unittest.TestCase):
    """_find_first_visible helper with mock locators."""

    def test_find_first_visible_returns_first(self):
        from tools.amazon_verify import _find_first_visible

        class MockLocator:
            def __init__(self, visible: bool):
                self._visible = visible
            def is_visible(self, timeout=2000):
                return self._visible

        class MockFirst:
            def __init__(self, loc):
                self._loc = loc
            @property
            def first(self):
                return self._loc

        class MockContext:
            def __init__(self, results: dict):
                self._results = results
            def locator(self, sel):
                return MockFirst(self._results.get(sel, MockLocator(False)))

        ctx = MockContext({
            "#bad": MockLocator(False),
            "#good": MockLocator(True),
        })
        result = _find_first_visible(ctx, ["#bad", "#good"], timeout=100)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_visible())

    def test_find_first_visible_returns_none_when_nothing(self):
        from tools.amazon_verify import _find_first_visible

        class MockLocator:
            def is_visible(self, timeout=2000):
                return False

        class MockFirst:
            @property
            def first(self):
                return MockLocator()

        class MockContext:
            def locator(self, sel):
                return MockFirst()

        result = _find_first_visible(MockContext(), ["#a", "#b"], timeout=100)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
