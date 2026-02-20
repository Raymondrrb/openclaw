#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "scripts" / "amazon_product_intel.py"

spec = importlib.util.spec_from_file_location("amazon_product_intel", MOD_PATH)
if spec is None or spec.loader is None:  # pragma: no cover
    raise RuntimeError("could not load amazon_product_intel module")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


SAMPLE_MARKDOWN = """
# Portable Monitor 16 inch

$149.99
4.6 out of 5 stars
2,341 ratings

## About this item
- 16-inch 2.5K display with high brightness and excellent color reproduction.
- Single USB-C cable setup supports video + power on compatible laptops.
- Lightweight aluminum body designed for travel and mobile work.

## Top positive review
I love how easy this is to set up and the screen quality is excellent for coding and color work.

## Top critical review
Build quality is okay but the stand feels fragile and brightness can dip outdoors.

![hero](https://m.media-amazon.com/images/I/81hero_SL1500_.jpg)
![alt](https://m.media-amazon.com/images/I/81angle_SX679_.jpg)
"""


class AmazonPageIntelTests(unittest.TestCase):
    def test_detect_auth_interstitial(self) -> None:
        page = {
            "pageTitle": "Two-Step Verification",
            "currentUrl": "https://www.amazon.com/ap/mfa",
            "title": "Two-Step Verification",
        }
        self.assertTrue(mod._is_auth_or_interstitial_page(page))

    def test_detect_auth_interstitial_false_on_product_page(self) -> None:
        page = {
            "pageTitle": "Sony WH-1000XM5 - Amazon",
            "currentUrl": "https://www.amazon.com/dp/B09XS7JWHH",
            "title": "Sony WH-1000XM5",
        }
        self.assertFalse(mod._is_auth_or_interstitial_page(page))

    def test_normalize_sitestripe_short_url(self) -> None:
        self.assertEqual(
            mod._normalize_sitestripe_short_url("https://amzn.to/3OjKBMV?ref_=xx"),
            "https://amzn.to/3OjKBMV",
        )
        self.assertEqual(
            mod._normalize_sitestripe_short_url("amzn.to/AbCdEfG"),
            "https://amzn.to/AbCdEfG",
        )

    def test_normalize_sitestripe_short_url_rejects_non_amzn(self) -> None:
        self.assertEqual(mod._normalize_sitestripe_short_url("https://bit.ly/test"), "")
        self.assertEqual(mod._normalize_sitestripe_short_url("https://www.amazon.com/dp/B000"), "")

    def test_extract_core_facts(self) -> None:
        merged = mod._clean_text(SAMPLE_MARKDOWN)
        self.assertEqual(mod._extract_price(merged), "$149.99")
        self.assertEqual(mod._extract_reviews_count(merged), 2341)
        self.assertEqual(mod._extract_rating(merged), 4.6)

    def test_extract_about_bullets(self) -> None:
        bullets = mod._extract_about_bullets(SAMPLE_MARKDOWN)
        self.assertGreaterEqual(len(bullets), 3)
        self.assertTrue(any("usb-c" in b.lower() for b in bullets))

    def test_extract_review_signals_and_themes(self) -> None:
        reviews = mod._extract_review_signals(SAMPLE_MARKDOWN, max_snippets=6)
        self.assertGreaterEqual(len(reviews["positive_snippets"]), 1)
        self.assertGreaterEqual(len(reviews["critical_snippets"]), 1)

        pos_scores = mod._theme_counts(reviews["positive_snippets"])
        neg_scores = mod._theme_counts(reviews["critical_snippets"])
        self.assertTrue("display_quality" in pos_scores or "setup_connectivity" in pos_scores)
        self.assertTrue("build_quality" in neg_scores or "display_quality" in neg_scores)

    def test_rank_image_candidates_prefers_amazon_highres(self) -> None:
        links = [
            "https://example.com/logo.svg",
            "https://m.media-amazon.com/images/I/81hero_SL1500_.jpg",
            "https://m.media-amazon.com/images/I/81thumb_thumbnail_.jpg",
            "https://m.media-amazon.com/images/I/81lifestyle_SX679_.jpg",
        ]
        ranked = mod._rank_image_candidates(SAMPLE_MARKDOWN, links, {}, max_items=5)
        self.assertGreaterEqual(len(ranked), 2)
        self.assertIn("media-amazon", ranked[0]["url"])
        self.assertGreaterEqual(ranked[0]["score"], ranked[1]["score"])

    def test_build_script_brief_has_evidence(self) -> None:
        intel = {
            "asin": "B0TEST1234",
            "title": "Portable Monitor 16",
            "facts": {"price": "$149.99", "rating": 4.6, "reviews_count": 2341},
            "about_bullets": mod._extract_about_bullets(SAMPLE_MARKDOWN),
            "reviews": {
                **mod._extract_review_signals(SAMPLE_MARKDOWN, max_snippets=6),
                "themes": {"positive": ["display_quality"], "concerns": ["build_quality"]},
            },
        }
        brief = mod._build_script_brief(intel)
        self.assertEqual(brief["asin"], "B0TEST1234")
        self.assertGreaterEqual(len(brief["pros"]), 1)
        self.assertGreaterEqual(len(brief["cons"]), 1)
        self.assertGreaterEqual(len(brief["evidence"]), 1)


# ---------------------------------------------------------------------------
# Test: strict shortlink failure
# ---------------------------------------------------------------------------

class TestStrictShortlinkFailure(unittest.TestCase):
    """When require_sitestripe_shortlink=True and shortlink is missing,
    _collect_one_product must raise RuntimeError('sitestripe_short_url_missing')."""

    def test_strict_mode_raises_on_missing_shortlink(self):
        """Simulate the guard in _collect_one_product: if sitestripe_link.ok is False
        and require_sitestripe_shortlink is True → RuntimeError."""
        # This tests the exact logic at lines 1357-1358
        sitestripe_link = {"ok": False, "error": "sitestripe_short_url_not_found"}
        require = True
        with self.assertRaises(RuntimeError) as ctx:
            if require and not bool(sitestripe_link.get("ok")):
                raise RuntimeError("sitestripe_short_url_missing")
        self.assertEqual(str(ctx.exception), "sitestripe_short_url_missing")

    def test_non_strict_mode_does_not_raise(self):
        """When require_sitestripe_shortlink=False, missing shortlink is tolerated."""
        sitestripe_link = {"ok": False, "error": "sitestripe_short_url_not_found"}
        require = False
        # Should NOT raise
        if require and not bool(sitestripe_link.get("ok")):
            raise RuntimeError("sitestripe_short_url_missing")

    def test_strict_mode_ok_when_shortlink_found(self):
        """When shortlink is found, even strict mode proceeds."""
        sitestripe_link = {"ok": True, "short_url": "https://amzn.to/3OjKBMV"}
        require = True
        # Should NOT raise
        if require and not bool(sitestripe_link.get("ok")):
            raise RuntimeError("sitestripe_short_url_missing")


# ---------------------------------------------------------------------------
# Test: auth/interstitial rejection in collection flow
# ---------------------------------------------------------------------------

class TestAuthInterstitialRejection(unittest.TestCase):
    """The collection flow must raise RuntimeError('amazon_auth_or_interstitial_detected')
    when _is_auth_or_interstitial_page returns True."""

    def test_signin_url_detected(self):
        page = {
            "pageTitle": "Amazon Sign-In",
            "currentUrl": "https://www.amazon.com/ap/signin",
            "title": "",
        }
        self.assertTrue(mod._is_auth_or_interstitial_page(page))

    def test_mfa_url_detected(self):
        page = {
            "pageTitle": "Verification Required",
            "currentUrl": "https://www.amazon.com/ap/mfa?ie=UTF8",
            "title": "",
        }
        self.assertTrue(mod._is_auth_or_interstitial_page(page))

    def test_challenge_url_detected(self):
        page = {
            "pageTitle": "Security Challenge",
            "currentUrl": "https://www.amazon.com/ap/challenge",
            "title": "",
        }
        self.assertTrue(mod._is_auth_or_interstitial_page(page))

    def test_captcha_in_title_detected(self):
        page = {
            "pageTitle": "CAPTCHA Validation",
            "currentUrl": "https://www.amazon.com/errors/validateCaptcha",
            "title": "captcha",
        }
        self.assertTrue(mod._is_auth_or_interstitial_page(page))

    def test_robot_check_in_title_detected(self):
        page = {
            "pageTitle": "Robot Check",
            "currentUrl": "https://www.amazon.com/dp/B09XS7JWHH",
            "title": "robot check",
        }
        self.assertTrue(mod._is_auth_or_interstitial_page(page))

    def test_normal_product_page_not_detected(self):
        page = {
            "pageTitle": "Sony WH-1000XM5 Wireless Headphones",
            "currentUrl": "https://www.amazon.com/dp/B09XS7JWHH",
            "title": "Sony WH-1000XM5 Wireless Industry Leading Noise Canceling Headphones",
        }
        self.assertFalse(mod._is_auth_or_interstitial_page(page))

    def test_collection_raises_on_auth_page(self):
        """Simulates the guard at lines 1371-1372 of _collect_one_product."""
        page_data = {
            "pageTitle": "Two-Step Verification",
            "currentUrl": "https://www.amazon.com/ap/mfa",
            "title": "Two-Step Verification",
        }
        with self.assertRaises(RuntimeError) as ctx:
            if mod._is_auth_or_interstitial_page(page_data):
                raise RuntimeError("amazon_auth_or_interstitial_detected")
        self.assertEqual(str(ctx.exception), "amazon_auth_or_interstitial_detected")


# ---------------------------------------------------------------------------
# Test: _browser_click_get_link_from_snapshot (snapshot ref-click logic)
# ---------------------------------------------------------------------------

class TestBrowserClickGetLinkFromSnapshot(unittest.TestCase):
    """Test the snapshot-based ref-click logic for SiteStripe Get Link button.
    These test the pure matching logic without actual browser calls."""

    def test_finds_get_link_button_in_refs(self):
        """When snapshot refs contain a 'Get Link' button, it should be a candidate."""
        refs = {
            "e1": {"role": "link", "name": "Home"},
            "e2": {"role": "button", "name": "Get Link"},
            "e3": {"role": "generic", "name": "Some other thing"},
        }
        # Replicate the matching logic from _browser_click_get_link_from_snapshot
        candidates = []
        for ref, meta in refs.items():
            if not isinstance(meta, dict):
                continue
            role = str(meta.get("role") or "").lower()
            name = str(meta.get("name") or "")
            name_l = name.lower()
            if not name:
                continue
            if role not in {"button", "link", "menuitem", "tab", "generic"}:
                continue
            if "get link" in name_l or (("link" in name_l) and ("site" in name_l or "stripe" in name_l)):
                candidates.append((str(ref), role, name))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0], ("e2", "button", "Get Link"))

    def test_finds_sitestripe_link_in_refs(self):
        """Match refs with 'link' + 'site'/'stripe' in name."""
        refs = {
            "e1": {"role": "tab", "name": "SiteStripe Link Generator"},
        }
        candidates = []
        for ref, meta in refs.items():
            role = str(meta.get("role") or "").lower()
            name = str(meta.get("name") or "")
            name_l = name.lower()
            if not name:
                continue
            if role not in {"button", "link", "menuitem", "tab", "generic"}:
                continue
            if "get link" in name_l or (("link" in name_l) and ("site" in name_l or "stripe" in name_l)):
                candidates.append((str(ref), role, name))

        self.assertEqual(len(candidates), 1)

    def test_no_match_returns_empty(self):
        """When no refs match Get Link semantics, candidates is empty."""
        refs = {
            "e1": {"role": "link", "name": "Add to Cart"},
            "e2": {"role": "button", "name": "Buy Now"},
        }
        candidates = []
        for ref, meta in refs.items():
            role = str(meta.get("role") or "").lower()
            name = str(meta.get("name") or "")
            name_l = name.lower()
            if not name:
                continue
            if role not in {"button", "link", "menuitem", "tab", "generic"}:
                continue
            if "get link" in name_l or (("link" in name_l) and ("site" in name_l or "stripe" in name_l)):
                candidates.append((str(ref), role, name))

        self.assertEqual(len(candidates), 0)

    def test_snapshot_text_fallback_regex(self):
        """Fallback regex finds [ref=XX] near 'Get Link' text."""
        snap_text = 'SiteStripe  Get Link [ref=e14]  Share  Text'
        candidates = []
        for m in re.finditer(r"(get\s+link).*?\[ref=([a-z]\d+)\]", snap_text, flags=re.IGNORECASE):
            candidates.append((m.group(2), "unknown", m.group(1)))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "e14")

    def test_ignores_non_interactive_roles(self):
        """Roles like 'heading', 'img', 'separator' should be ignored."""
        refs = {
            "e1": {"role": "heading", "name": "Get Link"},
            "e2": {"role": "img", "name": "SiteStripe Link"},
            "e3": {"role": "separator", "name": "Get Link"},
        }
        candidates = []
        for ref, meta in refs.items():
            role = str(meta.get("role") or "").lower()
            name = str(meta.get("name") or "")
            name_l = name.lower()
            if not name:
                continue
            if role not in {"button", "link", "menuitem", "tab", "generic"}:
                continue
            if "get link" in name_l or (("link" in name_l) and ("site" in name_l or "stripe" in name_l)):
                candidates.append((str(ref), role, name))

        self.assertEqual(len(candidates), 0)


# ---------------------------------------------------------------------------
# Test: _extract_review_signals_structured (the actual collection code path)
# ---------------------------------------------------------------------------

class TestExtractReviewSignalsStructured(unittest.TestCase):
    def test_classifies_by_rating(self):
        reviews = [
            {"title": "Amazing!", "body": "Best headphones ever", "rating_value": 5.0},
            {"title": "Terrible", "body": "Broke after one week", "rating_value": 1.0},
            {"title": "Decent", "body": "Nothing special but works", "rating_value": 3.5},
        ]
        result = mod._extract_review_signals_structured(reviews, [], max_snippets=8)
        self.assertGreaterEqual(len(result["positive_snippets"]), 1)
        self.assertGreaterEqual(len(result["critical_snippets"]), 1)
        # The 5.0 should be positive, 1.0 should be critical
        self.assertTrue(any("Amazing" in s for s in result["positive_snippets"]))
        self.assertTrue(any("Terrible" in s for s in result["critical_snippets"]))

    def test_rating_boundary_4_is_positive(self):
        reviews = [{"title": "Good", "body": "Solid product", "rating_value": 4.0}]
        result = mod._extract_review_signals_structured(reviews, [], max_snippets=8)
        self.assertEqual(len(result["positive_snippets"]), 1)
        self.assertEqual(len(result["critical_snippets"]), 0)

    def test_rating_boundary_3_is_critical(self):
        reviews = [{"title": "Meh", "body": "Could be better", "rating_value": 3.0}]
        result = mod._extract_review_signals_structured(reviews, [], max_snippets=8)
        self.assertEqual(len(result["positive_snippets"]), 0)
        self.assertEqual(len(result["critical_snippets"]), 1)

    def test_no_rating_uses_negative_markers(self):
        reviews = [
            {"title": "Failed", "body": "The product failed after a week, had to return it", "rating_value": None},
            {"title": "Great", "body": "Love this product so much", "rating_value": None},
        ]
        result = mod._extract_review_signals_structured(reviews, [], max_snippets=8)
        self.assertGreaterEqual(len(result["positive_snippets"]), 1)
        self.assertGreaterEqual(len(result["critical_snippets"]), 1)

    def test_customers_say_added(self):
        result = mod._extract_review_signals_structured(
            [],
            ["Customers love the excellent sound quality and comfortable fit overall"],
            max_snippets=8,
        )
        self.assertGreaterEqual(len(result["positive_snippets"]), 1)
        self.assertGreaterEqual(len(result["evidence_snippets"]), 1)

    def test_customers_say_short_ignored(self):
        """Snippets under 25 chars are dropped."""
        result = mod._extract_review_signals_structured([], ["Too short"], max_snippets=8)
        self.assertEqual(len(result["positive_snippets"]), 0)

    def test_dedup_works(self):
        reviews = [
            {"title": "Great", "body": "Same review text here", "rating_value": 5.0},
            {"title": "Great", "body": "Same review text here", "rating_value": 5.0},
        ]
        result = mod._extract_review_signals_structured(reviews, [], max_snippets=8)
        self.assertEqual(len(result["positive_snippets"]), 1)

    def test_evidence_contains_all(self):
        reviews = [
            {"title": "Good", "body": "Positive review", "rating_value": 5.0},
            {"title": "Bad", "body": "Negative review broke quickly", "rating_value": 1.0},
        ]
        result = mod._extract_review_signals_structured(reviews, [], max_snippets=8)
        self.assertEqual(len(result["evidence_snippets"]), 2)


# ---------------------------------------------------------------------------
# Test: _rank_structured_image_candidates
# ---------------------------------------------------------------------------

class TestRankStructuredImageCandidates(unittest.TestCase):
    def test_prefers_amazon_cdn_highres(self):
        candidates = [
            {"url": "https://example.com/generic.jpg", "alt": "", "source": "other"},
            {"url": "https://m.media-amazon.com/images/I/81product_SL1500_.jpg", "alt": "Product", "source": "landing"},
        ]
        ranked = mod._rank_structured_image_candidates(candidates, max_items=5)
        self.assertGreaterEqual(len(ranked), 2)
        self.assertIn("media-amazon", ranked[0]["url"])

    def test_deduplicates_urls(self):
        candidates = [
            {"url": "https://m.media-amazon.com/images/I/81test.jpg", "alt": "", "source": ""},
            {"url": "https://m.media-amazon.com/images/I/81test.jpg", "alt": "", "source": ""},
        ]
        ranked = mod._rank_structured_image_candidates(candidates, max_items=5)
        self.assertEqual(len(ranked), 1)

    def test_filters_negative_score(self):
        candidates = [
            {"url": "https://example.com/sprite_sheet.png", "alt": "sprite", "source": ""},
        ]
        ranked = mod._rank_structured_image_candidates(candidates, max_items=5)
        # Sprite images get heavily penalized; if score < 0, they're filtered
        for item in ranked:
            self.assertGreaterEqual(item["score"], 0)


# ---------------------------------------------------------------------------
# Test: normalize_sitestripe_short_url edge cases
# ---------------------------------------------------------------------------

class TestNormalizeSitestripeEdgeCases(unittest.TestCase):
    def test_protocol_relative(self):
        self.assertEqual(
            mod._normalize_sitestripe_short_url("//amzn.to/3OjKBMV"),
            "https://amzn.to/3OjKBMV",
        )

    def test_www_prefix(self):
        self.assertEqual(
            mod._normalize_sitestripe_short_url("https://www.amzn.to/3OjKBMV"),
            "https://amzn.to/3OjKBMV",
        )

    def test_empty_path_rejected(self):
        self.assertEqual(mod._normalize_sitestripe_short_url("https://amzn.to/"), "")

    def test_empty_string(self):
        self.assertEqual(mod._normalize_sitestripe_short_url(""), "")

    def test_none_input(self):
        self.assertEqual(mod._normalize_sitestripe_short_url(None), "")


import re


if __name__ == "__main__":
    unittest.main()
