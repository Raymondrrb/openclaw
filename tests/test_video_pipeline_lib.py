#!/usr/bin/env python3
"""Tests for video_pipeline_lib.py — shared library for the RayViewsLab video pipeline."""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure tools/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from video_pipeline_lib import (
    Product,
    SEGMENT_TYPES,
    PRODUCT_SEGMENT_TYPES,
    STOPWORDS,
    SUPABASE_ENV_FILE,
    normalize_ws,
    slugify,
    now_date,
    now_iso,
    parse_float,
    parse_price,
    parse_int,
    parse_review_count,
    theme_tokens,
    theme_match_score,
    append_affiliate_tag,
    extract_asin_from_url,
    canonical_amazon_url,
    product_score,
    supabase_env,
    parse_structured_script,
    extract_dzine_scenes,
    extract_voice_segments,
    extract_davinci_segments,
    write_structured_script,
    load_products_json,
    atomic_write_json,
    extract_image_candidates_from_product_html,
    parse_run_date_from_dirname,
    amazon_search_url_with_page,
    build_structured_script_prompt,
    _build_structure_instructions,
)


# ---------------------------------------------------------------------------
# normalize_ws
# ---------------------------------------------------------------------------

class TestNormalizeWs(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(normalize_ws("  hello   world  "), "hello world")

    def test_strips_tabs_newlines(self):
        self.assertEqual(normalize_ws("a\t\nb"), "a b")

    def test_none_returns_empty(self):
        self.assertEqual(normalize_ws(None), "")

    def test_empty_string(self):
        self.assertEqual(normalize_ws(""), "")


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Portable Monitors"), "portable_monitors")

    def test_special_chars(self):
        self.assertEqual(slugify("Best USB-C Hubs!"), "best_usb_c_hubs")

    def test_max_len(self):
        result = slugify("a" * 100, max_len=10)
        self.assertLessEqual(len(result), 10)

    def test_empty_fallback(self):
        self.assertEqual(slugify("---"), "theme")


# ---------------------------------------------------------------------------
# now_date / now_iso
# ---------------------------------------------------------------------------

class TestDateFunctions(unittest.TestCase):
    def test_now_date_format(self):
        import re
        self.assertRegex(now_date(), r"\d{4}-\d{2}-\d{2}")

    def test_now_iso_ends_Z(self):
        result = now_iso()
        self.assertTrue(result.endswith("Z"))


# ---------------------------------------------------------------------------
# parse_float
# ---------------------------------------------------------------------------

class TestParseFloat(unittest.TestCase):
    def test_simple(self):
        self.assertAlmostEqual(parse_float("4.5"), 4.5)

    def test_with_text(self):
        self.assertAlmostEqual(parse_float("Rating: 4.7 out of 5"), 4.7)

    def test_comma_separator(self):
        self.assertAlmostEqual(parse_float("1,234.56"), 1234.56)

    def test_none_on_empty(self):
        self.assertIsNone(parse_float(""))

    def test_none_on_no_number(self):
        self.assertIsNone(parse_float("no numbers here"))


# ---------------------------------------------------------------------------
# parse_price
# ---------------------------------------------------------------------------

class TestParsePrice(unittest.TestCase):
    def test_dollar_sign(self):
        self.assertAlmostEqual(parse_price("$29.99"), 29.99)

    def test_without_dollar(self):
        self.assertAlmostEqual(parse_price("149.95"), 149.95)

    def test_comma_thousands(self):
        self.assertAlmostEqual(parse_price("$1,299.00"), 1299.00)

    def test_none_on_empty(self):
        self.assertIsNone(parse_price(""))

    def test_none_on_no_price(self):
        self.assertIsNone(parse_price("free"))


# ---------------------------------------------------------------------------
# parse_int
# ---------------------------------------------------------------------------

class TestParseInt(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(parse_int("42"), 42)

    def test_with_comma(self):
        self.assertEqual(parse_int("1,234"), 1234)

    def test_none_on_empty(self):
        self.assertIsNone(parse_int(""))


# ---------------------------------------------------------------------------
# parse_review_count
# ---------------------------------------------------------------------------

class TestParseReviewCount(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(parse_review_count("1,234"), 1234)

    def test_k_suffix(self):
        self.assertEqual(parse_review_count("2.5k"), 2500)

    def test_K_suffix(self):
        self.assertEqual(parse_review_count("10K"), 10000)

    def test_m_suffix(self):
        self.assertEqual(parse_review_count("1.2M"), 1200000)

    def test_none_on_empty(self):
        self.assertIsNone(parse_review_count(""))

    def test_none_on_no_number(self):
        self.assertIsNone(parse_review_count("none"))


# ---------------------------------------------------------------------------
# theme_tokens
# ---------------------------------------------------------------------------

class TestThemeTokens(unittest.TestCase):
    def test_filters_stopwords(self):
        tokens = theme_tokens("Top Best Portable Monitors 2026")
        self.assertIn("portable", tokens)
        self.assertIn("monitors", tokens)
        self.assertNotIn("top", tokens)
        self.assertNotIn("best", tokens)
        self.assertNotIn("2026", tokens)

    def test_filters_short_tokens(self):
        tokens = theme_tokens("USB-C to HD Monitors")
        self.assertNotIn("to", tokens)
        self.assertNotIn("hd", tokens)  # len < 3

    def test_empty_string(self):
        self.assertEqual(theme_tokens(""), [])


# ---------------------------------------------------------------------------
# theme_match_score
# ---------------------------------------------------------------------------

class TestThemeMatchScore(unittest.TestCase):
    def test_full_match(self):
        tokens = ["portable", "monitor"]
        score = theme_match_score("Best Portable Monitor for WFH", tokens)
        self.assertAlmostEqual(score, 1.0)

    def test_partial_match(self):
        tokens = ["portable", "monitor", "usb"]
        score = theme_match_score("Portable desk setup", tokens)
        self.assertAlmostEqual(score, 1 / 3)

    def test_no_match(self):
        score = theme_match_score("Something else entirely", ["portable", "monitor"])
        self.assertAlmostEqual(score, 0.0)

    def test_empty_tokens(self):
        score = theme_match_score("anything", [])
        self.assertAlmostEqual(score, 0.0)


# ---------------------------------------------------------------------------
# append_affiliate_tag
# ---------------------------------------------------------------------------

class TestAppendAffiliateTag(unittest.TestCase):
    def test_adds_tag(self):
        result = append_affiliate_tag("https://amazon.com/dp/B123", "ray-20")
        self.assertEqual(result, "https://amazon.com/dp/B123?tag=ray-20")

    def test_adds_tag_with_existing_params(self):
        result = append_affiliate_tag("https://amazon.com/dp/B123?ref=sr", "ray-20")
        self.assertEqual(result, "https://amazon.com/dp/B123?ref=sr&tag=ray-20")

    def test_no_tag_if_empty(self):
        result = append_affiliate_tag("https://amazon.com/dp/B123", "")
        self.assertEqual(result, "https://amazon.com/dp/B123")

    def test_no_duplicate_tag(self):
        result = append_affiliate_tag("https://amazon.com/dp/B123?tag=other-20", "ray-20")
        self.assertEqual(result, "https://amazon.com/dp/B123?tag=other-20")


# ---------------------------------------------------------------------------
# extract_asin_from_url
# ---------------------------------------------------------------------------

class TestExtractAsinFromUrl(unittest.TestCase):
    def test_dp_url(self):
        self.assertEqual(extract_asin_from_url("https://amazon.com/dp/B0ABCDEF12"), "B0ABCDEF12")

    def test_gp_product_url(self):
        self.assertEqual(extract_asin_from_url("https://amazon.com/gp/product/B0ABCDEF12"), "B0ABCDEF12")

    def test_no_asin(self):
        self.assertEqual(extract_asin_from_url("https://example.com"), "")

    def test_empty(self):
        self.assertEqual(extract_asin_from_url(""), "")


# ---------------------------------------------------------------------------
# canonical_amazon_url
# ---------------------------------------------------------------------------

class TestCanonicalAmazonUrl(unittest.TestCase):
    def test_with_asin(self):
        self.assertEqual(canonical_amazon_url("", "B0ABCDEF12"), "https://www.amazon.com/dp/B0ABCDEF12")

    def test_absolute_url_no_asin(self):
        self.assertEqual(canonical_amazon_url("https://amazon.com/some/path", ""), "https://amazon.com/some/path")

    def test_relative_url_no_asin(self):
        result = canonical_amazon_url("/dp/B0ABCDEF12", "")
        self.assertTrue(result.startswith("https://www.amazon.com"))


# ---------------------------------------------------------------------------
# product_score
# ---------------------------------------------------------------------------

class TestProductScore(unittest.TestCase):
    def test_higher_rating_higher_score(self):
        s1 = product_score(4.0, 100, 50.0)
        s2 = product_score(5.0, 100, 50.0)
        self.assertGreater(s2, s1)

    def test_more_reviews_higher_score(self):
        s1 = product_score(4.5, 10, 50.0)
        s2 = product_score(4.5, 10000, 50.0)
        self.assertGreater(s2, s1)

    def test_price_midpoint_bonus(self):
        # Price near $85 gets bonus
        s1 = product_score(4.5, 100, 85.0)
        s2 = product_score(4.5, 100, 500.0)
        self.assertGreater(s1, s2)


# ---------------------------------------------------------------------------
# supabase_env
# ---------------------------------------------------------------------------

class TestSupabaseEnv(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "key123"})
    def test_from_env(self):
        url, key = supabase_env()
        self.assertEqual(url, "https://test.supabase.co")
        self.assertEqual(key, "key123")

    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}, clear=False)
    def test_fallback_to_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("SUPABASE_URL=https://file.supabase.co\n")
            f.write("SUPABASE_SERVICE_ROLE_KEY=filekey\n")
            f.flush()
            tmppath = Path(f.name)
        try:
            import video_pipeline_lib as lib
            orig = lib.SUPABASE_ENV_FILE
            lib.SUPABASE_ENV_FILE = tmppath
            url, key = supabase_env()
            self.assertEqual(url, "https://file.supabase.co")
            self.assertEqual(key, "filekey")
            lib.SUPABASE_ENV_FILE = orig
        finally:
            tmppath.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# parse_structured_script
# ---------------------------------------------------------------------------

def _make_valid_script(num_segments: int = 12) -> dict:
    """Build a minimal valid structured script."""
    segs = []
    types = ["HOOK", "CREDIBILITY", "CRITERIA"]
    for i in range(num_segments):
        if i < len(types):
            stype = types[i]
        else:
            stype = "PRODUCT_INTRO"
        seg = {"type": stype, "narration": f"Narration for segment {i}"}
        if stype in PRODUCT_SEGMENT_TYPES:
            seg["product_name"] = f"Product {i}"
        segs.append(seg)
    return {
        "video_title": "Test Video",
        "segments": segs,
        "youtube": {"description": "desc", "tags": [], "chapters": []},
    }


class TestParseStructuredScript(unittest.TestCase):
    def test_valid_script(self):
        script = _make_valid_script(12)
        raw = json.dumps(script)
        result = parse_structured_script(raw)
        self.assertEqual(result["video_title"], "Test Video")
        self.assertIn("total_word_count", result)

    def test_strips_markdown_fence(self):
        script = _make_valid_script(12)
        raw = "```json\n" + json.dumps(script) + "\n```"
        result = parse_structured_script(raw)
        self.assertEqual(result["video_title"], "Test Video")

    def test_rejects_too_few_segments(self):
        script = _make_valid_script(5)
        with self.assertRaises(RuntimeError):
            parse_structured_script(json.dumps(script))

    def test_rejects_missing_key(self):
        script = {"video_title": "X", "segments": []}
        with self.assertRaises(RuntimeError):
            parse_structured_script(json.dumps(script))

    def test_rejects_invalid_json(self):
        with self.assertRaises(RuntimeError):
            parse_structured_script("not json at all")

    def test_rejects_product_without_name(self):
        script = _make_valid_script(12)
        # Remove product_name from a PRODUCT_INTRO segment
        for seg in script["segments"]:
            if seg["type"] in PRODUCT_SEGMENT_TYPES:
                del seg["product_name"]
                break
        with self.assertRaises(RuntimeError):
            parse_structured_script(json.dumps(script))


# ---------------------------------------------------------------------------
# extract_dzine_scenes
# ---------------------------------------------------------------------------

class TestExtractDzineScenes(unittest.TestCase):
    def test_extracts_visual_hints(self):
        script = _make_valid_script(12)
        script["segments"][0]["visual_hint"] = "A clean desk with monitor"
        scenes = extract_dzine_scenes(script)
        self.assertGreater(len(scenes), 0)
        self.assertEqual(scenes[0]["visual_hint"], "A clean desk with monitor")
        self.assertEqual(scenes[0]["segment_type"], "HOOK")

    def test_skips_empty_hints(self):
        script = _make_valid_script(12)
        for seg in script["segments"]:
            seg.pop("visual_hint", None)
        scenes = extract_dzine_scenes(script)
        self.assertEqual(len(scenes), 0)


# ---------------------------------------------------------------------------
# extract_voice_segments
# ---------------------------------------------------------------------------

class TestExtractVoiceSegments(unittest.TestCase):
    def test_extracts_narrations(self):
        script = _make_valid_script(12)
        voice = extract_voice_segments(script)
        self.assertEqual(len(voice), 12)
        self.assertTrue(voice[0]["segment_id"].startswith("seg_00"))
        self.assertGreater(voice[0]["word_count"], 0)

    def test_skips_empty_narration(self):
        script = _make_valid_script(12)
        script["segments"][0]["narration"] = ""
        voice = extract_voice_segments(script)
        self.assertEqual(len(voice), 11)


# ---------------------------------------------------------------------------
# extract_davinci_segments
# ---------------------------------------------------------------------------

class TestExtractDavinciSegments(unittest.TestCase):
    def test_extracts_timeline(self):
        script = _make_valid_script(12)
        script["segments"][0]["visual_hint"] = "Something visual"
        timeline = extract_davinci_segments(script)
        self.assertEqual(len(timeline), 12)
        self.assertTrue(timeline[0]["has_visual"])
        self.assertGreater(timeline[0]["estimated_seconds"], 0)

    def test_no_visual_marker(self):
        script = _make_valid_script(12)
        timeline = extract_davinci_segments(script)
        self.assertFalse(timeline[0]["has_visual"])


# ---------------------------------------------------------------------------
# write_structured_script / load_products_json
# ---------------------------------------------------------------------------

class TestWriteStructuredScript(unittest.TestCase):
    def test_roundtrip(self):
        script = _make_valid_script(12)
        with tempfile.TemporaryDirectory() as td:
            path = write_structured_script(script, Path(td))
            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded["video_title"], "Test Video")


class TestLoadProductsJson(unittest.TestCase):
    def test_loads_products(self):
        products = [
            {
                "product_title": "Test Monitor",
                "asin": "B0ABCDEF12",
                "current_price_usd": 199.99,
                "rating": 4.5,
                "review_count": 1234,
                "feature_bullets": ["Feature 1"],
                "amazon_url": "https://amazon.com/dp/B0ABCDEF12",
                "affiliate_url": "https://amazon.com/dp/B0ABCDEF12?tag=ray-20",
            }
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(products, f)
            f.flush()
            tmppath = Path(f.name)
        try:
            loaded = load_products_json(tmppath)
            self.assertEqual(len(loaded), 1)
            self.assertIsInstance(loaded[0], Product)
            self.assertEqual(loaded[0].asin, "B0ABCDEF12")
            self.assertAlmostEqual(loaded[0].current_price_usd, 199.99)
        finally:
            tmppath.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Product dataclass
# ---------------------------------------------------------------------------

class TestProduct(unittest.TestCase):
    def test_defaults(self):
        p = Product(
            product_title="X", asin="B0ABC", current_price_usd=10.0,
            rating=4.0, review_count=100, feature_bullets=[],
            amazon_url="url", affiliate_url="aff",
        )
        self.assertTrue(p.available)
        self.assertAlmostEqual(p.ranking_score, 0.0)


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    def test_segment_types_not_empty(self):
        self.assertGreater(len(SEGMENT_TYPES), 5)

    def test_product_segment_types_subset(self):
        for t in PRODUCT_SEGMENT_TYPES:
            self.assertIn(t, SEGMENT_TYPES)

    def test_stopwords_contains_common(self):
        self.assertIn("the", STOPWORDS)
        self.assertIn("best", STOPWORDS)


# ---------------------------------------------------------------------------
# atomic_write_json
# ---------------------------------------------------------------------------

class TestAtomicWriteJson(unittest.TestCase):
    def test_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.json"
            data = {"key": "value", "number": 42}
            result = atomic_write_json(path, data)
            self.assertEqual(result, path)
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded, data)

    def test_no_tmp_file_left(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "out.json"
            atomic_write_json(path, [1, 2, 3])
            files = list(Path(td).iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, "out.json")

    def test_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "data.json"
            atomic_write_json(path, {"v": 1})
            atomic_write_json(path, {"v": 2})
            self.assertEqual(json.loads(path.read_text())["v"], 2)

    def test_handles_unicode(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "unicode.json"
            data = {"text": "caf\u00e9 \u2014 r\u00e9sum\u00e9"}
            atomic_write_json(path, data)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["text"], "caf\u00e9 \u2014 r\u00e9sum\u00e9")


# ---------------------------------------------------------------------------
# extract_image_candidates_from_product_html
# ---------------------------------------------------------------------------

class TestExtractImageCandidates(unittest.TestCase):
    # Domain filter requires ".m.media-amazon.com" substring (with leading dot)
    # or "images-na.ssl-images-amazon.com", so use full subdomain pattern.
    AMAZON_IMG = "https://images-eu.m.media-amazon.com/images/I"

    def test_og_image_meta(self):
        html = f'<meta property="og:image" content="{self.AMAZON_IMG}/71abc.jpg">'
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 1)
        self.assertIn("71abc.jpg", urls[0])

    def test_hires_json(self):
        html = f'"hiRes":"{self.AMAZON_IMG}/81xyz.jpg"'
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 1)
        self.assertIn("81xyz.jpg", urls[0])

    def test_large_json(self):
        html = f'"large" : "{self.AMAZON_IMG}/large123.png"'
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 1)

    def test_mainurl_json(self):
        html = f'"mainUrl":"{self.AMAZON_IMG}/main.webp"'
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 1)

    def test_deduplicates(self):
        url = f"{self.AMAZON_IMG}/dup.jpg"
        html = f'"hiRes":"{url}" "large":"{url}"'
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 1)

    def test_generic_url_scan(self):
        html = f'src="{self.AMAZON_IMG}/fallback.jpg" alt="product"'
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 1)

    def test_filters_non_amazon(self):
        html = '<meta property="og:image" content="https://example.com/image.jpg">'
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 0)

    def test_empty_html(self):
        self.assertEqual(extract_image_candidates_from_product_html(""), [])

    def test_max_24(self):
        lines = []
        for i in range(30):
            lines.append(f'"hiRes":"{self.AMAZON_IMG}/img{i:03d}.jpg"')
        html = "\n".join(lines)
        urls = extract_image_candidates_from_product_html(html)
        self.assertLessEqual(len(urls), 24)

    def test_ssl_images_domain(self):
        html = '"hiRes":"https://images-na.ssl-images-amazon.com/images/I/71prod.jpg"'
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 1)

    def test_escaped_slashes(self):
        html = f'"hiRes":"{self.AMAZON_IMG}/escaped.jpg"'.replace("/", "\\/")
        urls = extract_image_candidates_from_product_html(html)
        self.assertEqual(len(urls), 1)
        self.assertNotIn("\\/", urls[0])


# ---------------------------------------------------------------------------
# parse_run_date_from_dirname
# ---------------------------------------------------------------------------

class TestParseRunDateFromDirname(unittest.TestCase):
    def test_standard_format(self):
        import datetime as dt
        result = parse_run_date_from_dirname("products_2026-02-17")
        self.assertEqual(result, dt.date(2026, 2, 17))

    def test_run_prefix(self):
        import datetime as dt
        result = parse_run_date_from_dirname("run_earbuds_2026-01-15")
        self.assertEqual(result, dt.date(2026, 1, 15))

    def test_date_only(self):
        import datetime as dt
        result = parse_run_date_from_dirname("2026-03-01")
        self.assertEqual(result, dt.date(2026, 3, 1))

    def test_no_date(self):
        self.assertIsNone(parse_run_date_from_dirname("no_date_here"))

    def test_empty(self):
        self.assertIsNone(parse_run_date_from_dirname(""))

    def test_none(self):
        self.assertIsNone(parse_run_date_from_dirname(None))

    def test_invalid_date(self):
        self.assertIsNone(parse_run_date_from_dirname("run_2026-13-99"))

    def test_date_not_at_end(self):
        self.assertIsNone(parse_run_date_from_dirname("2026-01-01_suffix"))


# ---------------------------------------------------------------------------
# amazon_search_url_with_page
# ---------------------------------------------------------------------------

class TestAmazonSearchUrlWithPage(unittest.TestCase):
    def test_basic_url(self):
        result = amazon_search_url_with_page(
            "https://www.amazon.com/s?k=monitors",
            theme_fallback="monitors",
            page=2,
        )
        self.assertIn("page=2", result)
        self.assertIn("k=monitors", result)

    def test_empty_base_url_uses_fallback(self):
        result = amazon_search_url_with_page(
            "",
            theme_fallback="wireless earbuds",
            page=1,
        )
        self.assertIn("amazon.com", result)
        self.assertIn("wireless+earbuds", result)
        self.assertIn("page=1", result)

    def test_removes_existing_page(self):
        result = amazon_search_url_with_page(
            "https://www.amazon.com/s?k=headphones&page=5",
            theme_fallback="headphones",
            page=3,
        )
        self.assertIn("page=3", result)
        self.assertNotIn("page=5", result)

    def test_adds_theme_fallback_if_no_k(self):
        result = amazon_search_url_with_page(
            "https://www.amazon.com/s?ref=sr_pg_1",
            theme_fallback="USB hubs",
            page=1,
        )
        self.assertIn("k=USB+hubs", result)

    def test_preserves_other_params(self):
        result = amazon_search_url_with_page(
            "https://www.amazon.com/s?k=mice&ref=sr_1&qid=123",
            theme_fallback="mice",
            page=4,
        )
        self.assertIn("ref=sr_1", result)
        self.assertIn("qid=123", result)
        self.assertIn("page=4", result)

    def test_page_1(self):
        result = amazon_search_url_with_page(
            "https://www.amazon.com/s?k=keyboards",
            theme_fallback="keyboards",
            page=1,
        )
        self.assertIn("page=1", result)


# ---------------------------------------------------------------------------
# _build_structure_instructions
# ---------------------------------------------------------------------------

class TestBuildStructureInstructions(unittest.TestCase):
    def test_default_without_plan(self):
        lines = _build_structure_instructions(None)
        self.assertIsInstance(lines, list)
        text = "\n".join(lines)
        self.assertIn("REQUIRED STRUCTURE:", text)
        self.assertIn("HOOK", text)
        self.assertIn("PRODUCT_INTRO", text)
        self.assertIn("ENDING_DECISION", text)

    def test_with_variation_plan(self):
        plan = {
            "selections": {
                "structure_template": "problem_solution",
                "product_block_pattern": "demo_first",
                "opener_style": "confrontation",
            },
            "prompt_instructions": {
                "structure_description": "Problem-based flow",
                "structure_flow": "problem -> solution -> ranking",
                "segments_per_product": ["PRODUCT_DEMO", "PRODUCT_REVIEW"],
                "product_order": "descending_rank",
                "opener_description": "Confrontational opener",
                "visual_description": "Cinematic close-ups",
                "voice_description": "Calm narrator",
                "voice_wpm_target": 140,
                "cta_line": "Check links below",
                "disclosure_text": "This contains affiliate links",
            },
        }
        lines = _build_structure_instructions(plan)
        text = "\n".join(lines)
        self.assertIn("problem_solution", text)
        self.assertIn("demo_first", text)
        self.assertIn("confrontation", text)
        self.assertIn("140 wpm", text)

    def test_with_marketing_angle(self):
        plan = {
            "selections": {},
            "prompt_instructions": {
                "marketing_angle": "budget_champion",
                "marketing_angle_prompt": "Frame everything through value-for-money lens",
            },
        }
        lines = _build_structure_instructions(plan)
        text = "\n".join(lines)
        self.assertIn("MARKETING ANGLE", text)
        self.assertIn("budget_champion", text)
        self.assertIn("value-for-money", text)

    def test_with_category_context(self):
        plan = {
            "selections": {},
            "prompt_instructions": {
                "offer_context": "Earbuds market is saturated with options under $50",
                "customer_avatar": "Young professionals commuting daily",
            },
        }
        lines = _build_structure_instructions(plan)
        text = "\n".join(lines)
        self.assertIn("CATEGORY CONTEXT", text)
        self.assertIn("saturated", text)
        self.assertIn("commuting", text)

    def test_with_category_fallback(self):
        plan = {
            "selections": {},
            "prompt_instructions": {
                "category_context_fallback": "No deep category data available",
            },
        }
        lines = _build_structure_instructions(plan)
        text = "\n".join(lines)
        self.assertIn("CATEGORY CONTEXT NOTE", text)

    def test_with_opener_template(self):
        plan = {
            "selections": {"opener_style": "data_bomb"},
            "prompt_instructions": {
                "opener_template": "80 percent of buyers regret their first purchase",
            },
        }
        lines = _build_structure_instructions(plan)
        text = "\n".join(lines)
        self.assertIn("Opener template example:", text)
        self.assertIn("80 percent", text)


# ---------------------------------------------------------------------------
# build_structured_script_prompt
# ---------------------------------------------------------------------------

class TestBuildStructuredScriptPrompt(unittest.TestCase):

    def _make_products(self, n=5):
        prods = []
        for i in range(n):
            prods.append(Product(
                product_title=f"Product {i+1}",
                asin=f"B00TEST{i:04d}",
                current_price_usd=20.0 + i * 10,
                rating=4.0 + i * 0.2,
                review_count=100 * (i + 1),
                feature_bullets=[f"Feature A{i}", f"Feature B{i}"],
                amazon_url=f"https://amazon.com/dp/B00TEST{i:04d}",
                affiliate_url=f"https://amazon.com/dp/B00TEST{i:04d}?tag=ray-20",
                ranking_score=float(i),
            ))
        return prods

    def test_returns_string(self):
        prompt = build_structured_script_prompt(
            self._make_products(), "portable monitors", "RayViews"
        )
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 500)

    def test_contains_channel_name(self):
        prompt = build_structured_script_prompt(
            self._make_products(), "earbuds", "TestChannel"
        )
        self.assertIn("TestChannel", prompt)

    def test_contains_product_names(self):
        prompt = build_structured_script_prompt(
            self._make_products(), "monitors", "RayViews"
        )
        for i in range(5):
            self.assertIn(f"Product {i+1}", prompt)

    def test_contains_segment_types(self):
        prompt = build_structured_script_prompt(
            self._make_products(), "monitors", "RayViews"
        )
        self.assertIn("HOOK", prompt)
        self.assertIn("PRODUCT_INTRO", prompt)
        self.assertIn("ENDING_DECISION", prompt)

    def test_contains_anti_ai_rules(self):
        prompt = build_structured_script_prompt(
            self._make_products(), "monitors", "RayViews"
        )
        self.assertIn("ANTI-AI RULES", prompt)
        self.assertIn("game-changer", prompt)

    def test_contains_json_format(self):
        prompt = build_structured_script_prompt(
            self._make_products(), "monitors", "RayViews"
        )
        self.assertIn("video_title", prompt)
        self.assertIn("segments", prompt)
        self.assertIn("youtube", prompt)

    def test_with_variation_plan(self):
        plan = {
            "selections": {"structure_template": "problem_solution"},
            "prompt_instructions": {
                "structure_description": "Problem-solution flow",
                "structure_flow": "pain -> solution",
                "voice_wpm_target": 160,
            },
        }
        prompt = build_structured_script_prompt(
            self._make_products(), "earbuds", "RayViews", variation_plan=plan,
        )
        self.assertIn("problem_solution", prompt)

    def test_products_ordered_ascending(self):
        prods = self._make_products()
        prompt = build_structured_script_prompt(prods, "monitors", "RayViews")
        # Product with lowest score shown first (#5), highest last (#1)
        rank5_pos = prompt.find('"rank": 5')
        rank1_pos = prompt.find('"rank": 1')
        if rank5_pos != -1 and rank1_pos != -1:
            self.assertLess(rank5_pos, rank1_pos)

    def test_affiliate_urls_included(self):
        prompt = build_structured_script_prompt(
            self._make_products(), "monitors", "RayViews"
        )
        self.assertIn("tag=ray-20", prompt)

    def test_word_count_target(self):
        prompt = build_structured_script_prompt(
            self._make_products(), "monitors", "RayViews"
        )
        self.assertIn("1100-1800", prompt)


# ---------------------------------------------------------------------------
# product_score edge cases
# ---------------------------------------------------------------------------

class TestProductScoreEdgeCases(unittest.TestCase):
    def test_zero_reviews(self):
        score = product_score(4.5, 0, 50.0)
        self.assertIsInstance(score, float)

    def test_zero_rating(self):
        score = product_score(0.0, 100, 50.0)
        self.assertLess(score, product_score(5.0, 100, 50.0))

    def test_very_high_price(self):
        score = product_score(4.5, 100, 9999.0)
        self.assertIsInstance(score, float)

    def test_very_low_price(self):
        s1 = product_score(4.5, 100, 1.0)
        s2 = product_score(4.5, 100, 85.0)
        # $85 should get price bonus
        self.assertLess(s1, s2)

    def test_one_review(self):
        score = product_score(5.0, 1, 50.0)
        self.assertIsInstance(score, float)
        self.assertGreater(score, 0)

    def test_massive_reviews(self):
        s_few = product_score(4.5, 10, 50.0)
        s_many = product_score(4.5, 1000000, 50.0)
        self.assertGreater(s_many, s_few)


# ---------------------------------------------------------------------------
# slugify edge cases
# ---------------------------------------------------------------------------

class TestSlugifyEdgeCases(unittest.TestCase):
    def test_unicode(self):
        result = slugify("Café Résumé")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_numbers_only(self):
        result = slugify("2026")
        self.assertEqual(result, "2026")

    def test_multiple_underscores(self):
        result = slugify("a - b - c")
        self.assertNotIn("__", result)

    def test_trailing_underscore(self):
        result = slugify("Hello World!")
        self.assertFalse(result.endswith("_"))


# ---------------------------------------------------------------------------
# parse_review_count edge cases
# ---------------------------------------------------------------------------

class TestParseReviewCountEdgeCases(unittest.TestCase):
    def test_zero_k(self):
        result = parse_review_count("0K")
        self.assertEqual(result, 0)

    def test_decimal_k(self):
        result = parse_review_count("3.7K")
        self.assertEqual(result, 3700)

    def test_plain_large_number(self):
        result = parse_review_count("123456")
        self.assertEqual(result, 123456)

    def test_with_ratings_text(self):
        result = parse_review_count("2,345 ratings")
        self.assertEqual(result, 2345)


# ---------------------------------------------------------------------------
# parse_float edge cases
# ---------------------------------------------------------------------------

class TestParseFloatEdgeCases(unittest.TestCase):
    def test_negative_extracts_number(self):
        # parse_float extracts the numeric part without sign
        result = parse_float("-3.5")
        self.assertAlmostEqual(result, 3.5)

    def test_integer_only(self):
        result = parse_float("42")
        self.assertAlmostEqual(result, 42.0)

    def test_multiple_numbers_first(self):
        result = parse_float("4.5 out of 5.0 stars")
        self.assertAlmostEqual(result, 4.5)


# ---------------------------------------------------------------------------
# theme_match_score edge cases
# ---------------------------------------------------------------------------

class TestThemeMatchScoreEdgeCases(unittest.TestCase):
    def test_case_insensitive(self):
        score = theme_match_score("PORTABLE MONITOR", ["portable", "monitor"])
        self.assertAlmostEqual(score, 1.0)

    def test_partial_word_no_match(self):
        # "port" should not match "portable"
        score = theme_match_score("port device", ["portable"])
        self.assertAlmostEqual(score, 0.0)

    def test_single_token_match(self):
        score = theme_match_score("Great Monitor Stand", ["monitor"])
        self.assertAlmostEqual(score, 1.0)


# ---------------------------------------------------------------------------
# extract_asin_from_url edge cases
# ---------------------------------------------------------------------------

class TestExtractAsinEdgeCases(unittest.TestCase):
    def test_with_query_params(self):
        result = extract_asin_from_url("https://amazon.com/dp/B0ABCDEF12?ref=sr_1")
        self.assertEqual(result, "B0ABCDEF12")

    def test_with_trailing_path(self):
        result = extract_asin_from_url("https://amazon.com/dp/B0ABCDEF12/ref=sr_1_1")
        self.assertEqual(result, "B0ABCDEF12")

    def test_none_input(self):
        result = extract_asin_from_url(None)
        self.assertEqual(result, "")

    def test_short_asin_no_match(self):
        result = extract_asin_from_url("https://amazon.com/dp/B0ABC")
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# append_affiliate_tag edge cases
# ---------------------------------------------------------------------------

class TestAppendAffiliateTagEdgeCases(unittest.TestCase):
    def test_none_tag(self):
        result = append_affiliate_tag("https://amazon.com/dp/B123", None)
        self.assertEqual(result, "https://amazon.com/dp/B123")

    def test_preserves_fragment(self):
        result = append_affiliate_tag("https://amazon.com/dp/B123#reviews", "ray-20")
        self.assertIn("tag=ray-20", result)


if __name__ == "__main__":
    unittest.main()
