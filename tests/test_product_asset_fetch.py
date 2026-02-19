#!/usr/bin/env python3
"""Tests for rayvault/product_asset_fetch.py — product image download and caching."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rayvault.product_asset_fetch import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    MIN_IMAGE_BYTES,
    MIN_PRODUCT_IMAGE_BYTES,
    PLACEHOLDER_DIMS,
    FetchResult,
    _build_product_meta,
    compute_stability_score,
    pick_urls,
    safe_ext_from_url,
    validate_downloaded_image,
)


# ---------------------------------------------------------------
# safe_ext_from_url
# ---------------------------------------------------------------

class TestSafeExtFromUrl(unittest.TestCase):

    def test_jpg(self):
        self.assertEqual(safe_ext_from_url("https://images.amazon.com/img.jpg"), ".jpg")

    def test_jpeg_normalizes(self):
        self.assertEqual(safe_ext_from_url("https://images.amazon.com/img.jpeg"), ".jpg")

    def test_png(self):
        self.assertEqual(safe_ext_from_url("https://images.amazon.com/img.png"), ".png")

    def test_webp(self):
        self.assertEqual(safe_ext_from_url("https://images.amazon.com/img.webp"), ".webp")

    def test_unknown_ext_default(self):
        self.assertEqual(safe_ext_from_url("https://images.amazon.com/img.gif"), ".jpg")

    def test_no_ext(self):
        self.assertEqual(safe_ext_from_url("https://images.amazon.com/img"), ".jpg")

    def test_empty(self):
        self.assertEqual(safe_ext_from_url(""), ".jpg")

    def test_custom_default(self):
        self.assertEqual(safe_ext_from_url("https://x.com/f", default=".png"), ".png")

    def test_query_string_ignored(self):
        self.assertEqual(
            safe_ext_from_url("https://images.amazon.com/img.png?resize=300"),
            ".png",
        )


# ---------------------------------------------------------------
# validate_downloaded_image
# ---------------------------------------------------------------

class TestValidateDownloadedImage(unittest.TestCase):

    def test_missing_file(self):
        self.assertEqual(validate_downloaded_image(Path("/nonexistent")), "file_missing")

    def test_too_small(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            f.write(b"\xff\xd8" + b"\x00" * 100)
            p = Path(f.name)
        try:
            result = validate_downloaded_image(p)
            self.assertIsNotNone(result)
            self.assertIn("too_small", result)
        finally:
            p.unlink()

    def test_large_enough(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            f.write(b"\xff\xd8" + b"\x00" * MIN_PRODUCT_IMAGE_BYTES)
            p = Path(f.name)
        try:
            result = validate_downloaded_image(p)
            self.assertIsNone(result)
        finally:
            p.unlink()


# ---------------------------------------------------------------
# pick_urls
# ---------------------------------------------------------------

class TestPickUrls(unittest.TestCase):

    def test_hires_preferred(self):
        item = {
            "hires_image_urls": ["https://hires.com/1.jpg"],
            "image_urls": ["https://normal.com/1.jpg"],
        }
        urls = pick_urls(item)
        self.assertEqual(urls[0], "https://hires.com/1.jpg")

    def test_dedupes(self):
        item = {
            "hires_image_urls": ["https://x.com/1.jpg"],
            "image_urls": ["https://x.com/1.jpg", "https://x.com/2.jpg"],
        }
        urls = pick_urls(item)
        self.assertEqual(len(urls), 2)

    def test_empty(self):
        self.assertEqual(pick_urls({}), [])

    def test_filters_non_http(self):
        item = {"image_urls": ["not-a-url", "https://x.com/1.jpg"]}
        urls = pick_urls(item)
        self.assertEqual(len(urls), 1)

    def test_non_string_ignored(self):
        item = {"image_urls": [123, None, "https://x.com/1.jpg"]}
        urls = pick_urls(item)
        self.assertEqual(len(urls), 1)


# ---------------------------------------------------------------
# compute_stability_score
# ---------------------------------------------------------------

class TestComputeStabilityScore(unittest.TestCase):

    def test_perfect(self):
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=0,
            cache_misses=0, total_products=5, missing_images=0,
        )
        self.assertEqual(score, 100)

    def test_survival_mode(self):
        score = compute_stability_score(
            survival_mode=True, amazon_blocks=0,
            cache_misses=0, total_products=5, missing_images=0,
        )
        self.assertEqual(score, 80)

    def test_amazon_blocks(self):
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=2,
            cache_misses=0, total_products=5, missing_images=0,
        )
        self.assertEqual(score, 70)

    def test_missing_images(self):
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=0,
            cache_misses=0, total_products=5, missing_images=3,
        )
        self.assertEqual(score, 70)

    def test_all_penalties(self):
        score = compute_stability_score(
            survival_mode=True, amazon_blocks=1,
            cache_misses=5, total_products=5, missing_images=5,
        )
        self.assertEqual(score, 0)

    def test_clamped_at_zero(self):
        score = compute_stability_score(
            survival_mode=True, amazon_blocks=5,
            cache_misses=10, total_products=5, missing_images=10,
        )
        self.assertEqual(score, 0)


# ---------------------------------------------------------------
# _build_product_meta
# ---------------------------------------------------------------

class TestBuildProductMeta(unittest.TestCase):

    def test_basic_fields(self):
        item = {
            "asin": "B0TEST",
            "title": "  Great Product  ",
            "price_text": "$29.99",
            "brand": "TestBrand",
        }
        meta = _build_product_meta(item, rank=1)
        self.assertEqual(meta["rank"], 1)
        self.assertEqual(meta["asin"], "B0TEST")
        self.assertEqual(meta["title"], "Great Product")
        self.assertEqual(meta["brand"], "TestBrand")

    def test_missing_fields(self):
        meta = _build_product_meta({}, rank=2)
        self.assertEqual(meta["rank"], 2)
        self.assertEqual(meta["asin"], "")
        self.assertEqual(meta["title"], "")
        self.assertEqual(meta["bullets"], [])

    def test_bullets_fallback(self):
        item = {"bullet_points": ["a", "b"]}
        meta = _build_product_meta(item, rank=1)
        self.assertEqual(meta["bullets"], ["a", "b"])


# ---------------------------------------------------------------
# FetchResult
# ---------------------------------------------------------------

class TestFetchResult(unittest.TestCase):

    def test_defaults(self):
        r = FetchResult(ok=True, downloaded=3, skipped=1, errors=0)
        self.assertTrue(r.ok)
        self.assertEqual(r.cache_hits, 0)
        self.assertFalse(r.survival_mode)
        self.assertEqual(r.notes, [])


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_allowed_content_types(self):
        self.assertIn("image/jpeg", ALLOWED_IMAGE_CONTENT_TYPES)
        self.assertIn("image/png", ALLOWED_IMAGE_CONTENT_TYPES)

    def test_min_image_bytes(self):
        self.assertGreater(MIN_IMAGE_BYTES, 0)

    def test_placeholder_dims(self):
        self.assertIn((1, 1), PLACEHOLDER_DIMS)
        self.assertIn((120, 120), PLACEHOLDER_DIMS)


# ---------------------------------------------------------------
# safe_ext_from_url edge cases
# ---------------------------------------------------------------

class TestSafeExtFromUrlEdgeCases(unittest.TestCase):

    def test_uppercase_ext(self):
        self.assertEqual(safe_ext_from_url("https://x.com/IMG.JPG"), ".jpg")

    def test_mixed_case_ext(self):
        self.assertEqual(safe_ext_from_url("https://x.com/img.Png"), ".png")

    def test_fragment_ignored(self):
        self.assertEqual(safe_ext_from_url("https://x.com/img.png#top"), ".png")

    def test_double_ext(self):
        # Only last extension matters
        result = safe_ext_from_url("https://x.com/img.backup.webp")
        self.assertEqual(result, ".webp")

    def test_very_long_url(self):
        url = "https://images-na.ssl-images-amazon.com/" + "a" * 500 + "/image.jpg"
        self.assertEqual(safe_ext_from_url(url), ".jpg")


# ---------------------------------------------------------------
# pick_urls edge cases
# ---------------------------------------------------------------

class TestPickUrlsEdgeCases(unittest.TestCase):

    def test_only_hires(self):
        item = {"hires_image_urls": ["https://x.com/1.jpg", "https://x.com/2.jpg"]}
        urls = pick_urls(item)
        self.assertEqual(len(urls), 2)

    def test_only_normal(self):
        item = {"image_urls": ["https://x.com/1.jpg"]}
        urls = pick_urls(item)
        self.assertEqual(len(urls), 1)

    def test_all_non_http_filtered(self):
        item = {"image_urls": ["ftp://x.com/1.jpg", "data:image/png;base64,abc"]}
        urls = pick_urls(item)
        self.assertEqual(len(urls), 0)

    def test_mixed_valid_invalid(self):
        item = {"image_urls": ["not-url", "https://x.com/1.jpg", "", None, "https://x.com/2.jpg"]}
        urls = pick_urls(item)
        self.assertEqual(len(urls), 2)


# ---------------------------------------------------------------
# compute_stability_score edge cases
# ---------------------------------------------------------------

class TestComputeStabilityScoreEdgeCases(unittest.TestCase):

    def test_zero_products(self):
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=0,
            cache_misses=0, total_products=0, missing_images=0,
        )
        self.assertGreaterEqual(score, 0)

    def test_single_product_perfect(self):
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=0,
            cache_misses=0, total_products=1, missing_images=0,
        )
        self.assertEqual(score, 100)

    def test_cache_misses_no_crash(self):
        # cache_misses is tracked but may not reduce score alone
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=0,
            cache_misses=3, total_products=5, missing_images=0,
        )
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


# ---------------------------------------------------------------
# validate_downloaded_image edge cases
# ---------------------------------------------------------------

class TestValidateDownloadedImageEdgeCases(unittest.TestCase):

    def test_exact_threshold_passes(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            f.write(b"\xff\xd8" + b"\x00" * (MIN_PRODUCT_IMAGE_BYTES - 2))
            p = Path(f.name)
        try:
            result = validate_downloaded_image(p)
            self.assertIsNone(result)
        finally:
            p.unlink()

    def test_one_byte_below_threshold(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            f.write(b"\xff\xd8" + b"\x00" * (MIN_PRODUCT_IMAGE_BYTES - 3))
            p = Path(f.name)
        try:
            result = validate_downloaded_image(p)
            self.assertIsNotNone(result)
            self.assertIn("too_small", result)
        finally:
            p.unlink()

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            p = Path(f.name)
        try:
            result = validate_downloaded_image(p)
            self.assertIsNotNone(result)
            self.assertIn("too_small", result)
        finally:
            p.unlink()


# ---------------------------------------------------------------
# _build_product_meta edge cases
# ---------------------------------------------------------------

class TestBuildProductMetaEdgeCases(unittest.TestCase):

    def test_title_whitespace_stripped(self):
        meta = _build_product_meta({"title": "  lots  of  spaces  "}, rank=1)
        self.assertEqual(meta["title"], "lots  of  spaces")

    def test_rank_preserved(self):
        for r in (0, 1, 5, 99):
            meta = _build_product_meta({}, rank=r)
            self.assertEqual(meta["rank"], r)

    def test_bullets_preferred_over_bullet_points(self):
        item = {"bullets": ["a", "b"], "bullet_points": ["c", "d"]}
        meta = _build_product_meta(item, rank=1)
        self.assertEqual(meta["bullets"], ["a", "b"])

    def test_price_text_preserved(self):
        item = {"price_text": "$49.99"}
        meta = _build_product_meta(item, rank=1)
        self.assertEqual(meta["price_text"], "$49.99")


if __name__ == "__main__":
    unittest.main()
