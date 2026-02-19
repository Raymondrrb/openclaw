#!/usr/bin/env python3
"""Comprehensive tests for pure functions in tools/market_auto_dispatch.py."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from market_auto_dispatch import (
    confidence_to_score,
    extract_asin_from_url,
    infer_category_of_day,
    match_tokens,
    parse_ranked_products_from_research_text,
    product_key,
    product_key_for_item,
    slugify,
    split_products_by_novelty,
)


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------
class TestSlugify(unittest.TestCase):
    def test_normal_text(self):
        self.assertEqual(slugify("Hello World"), "hello_world")

    def test_special_characters(self):
        self.assertEqual(slugify("Top 5! Best@TVs#2026"), "top_5_best_tvs_2026")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "opportunity")

    def test_whitespace_only(self):
        self.assertEqual(slugify("   "), "opportunity")

    def test_long_text_truncated(self):
        long_input = "a" * 100
        result = slugify(long_input)
        self.assertLessEqual(len(result), 48)

    def test_custom_max_len(self):
        result = slugify("hello world testing max length", max_len=10)
        self.assertLessEqual(len(result), 10)

    def test_collapses_underscores(self):
        self.assertEqual(slugify("foo---bar___baz"), "foo_bar_baz")

    def test_strips_leading_trailing_underscores(self):
        self.assertEqual(slugify("---hello---"), "hello")

    def test_preserves_numbers(self):
        self.assertEqual(slugify("top5 picks 2026"), "top5_picks_2026")

    def test_truncation_strips_trailing_underscore(self):
        # If truncation lands right after an underscore, it should be stripped.
        result = slugify("ab cd ef gh ij kl", max_len=5)
        self.assertFalse(result.endswith("_"))
        self.assertLessEqual(len(result), 5)


# ---------------------------------------------------------------------------
# confidence_to_score
# ---------------------------------------------------------------------------
class TestConfidenceToScore(unittest.TestCase):
    def test_high(self):
        self.assertEqual(confidence_to_score("high"), 4.6)

    def test_medium(self):
        self.assertEqual(confidence_to_score("medium"), 3.9)

    def test_low(self):
        self.assertEqual(confidence_to_score("low"), 3.2)

    def test_unknown_value(self):
        self.assertEqual(confidence_to_score("extreme"), 0.0)

    def test_none(self):
        self.assertEqual(confidence_to_score(None), 0.0)

    def test_whitespace_padding(self):
        self.assertEqual(confidence_to_score("  high  "), 4.6)

    def test_case_insensitive(self):
        self.assertEqual(confidence_to_score("HIGH"), 4.6)
        self.assertEqual(confidence_to_score("Medium"), 3.9)
        self.assertEqual(confidence_to_score("LOW"), 3.2)

    def test_empty_string(self):
        self.assertEqual(confidence_to_score(""), 0.0)


# ---------------------------------------------------------------------------
# product_key
# ---------------------------------------------------------------------------
class TestProductKey(unittest.TestCase):
    def test_normal_product(self):
        result = product_key("Apple AirPods Pro")
        self.assertEqual(result, "apple airpods pro")

    def test_with_stopwords(self):
        # "amazon", "new", "latest", "model", "version" are stopwords.
        result = product_key("Amazon Echo Show New Version")
        self.assertEqual(result, "echo show")

    def test_all_stopwords(self):
        # If all tokens are stopwords, fallback returns the original tokens joined.
        result = product_key("Amazon New Latest")
        self.assertEqual(result, "amazon new latest")

    def test_empty_string(self):
        self.assertEqual(product_key(""), "")

    def test_none(self):
        self.assertEqual(product_key(None), "")

    def test_mixed_case(self):
        result = product_key("SONY WH-1000XM5")
        self.assertIn("sony", result)
        self.assertIn("1000xm5", result)

    def test_strips_special_chars(self):
        # re.findall(r"[a-z0-9]+", ...) only captures alphanumeric tokens.
        result = product_key("Ring Video Doorbell (4th Gen)")
        self.assertEqual(result, "ring video doorbell 4th gen")


# ---------------------------------------------------------------------------
# extract_asin_from_url
# ---------------------------------------------------------------------------
class TestExtractAsinFromUrl(unittest.TestCase):
    def test_dp_url(self):
        url = "https://www.amazon.com/dp/B09V3KXJPB?tag=foo"
        self.assertEqual(extract_asin_from_url(url), "B09V3KXJPB")

    def test_gp_product_url(self):
        url = "https://www.amazon.com/gp/product/b09v3kxjpb/ref=something"
        self.assertEqual(extract_asin_from_url(url), "B09V3KXJPB")

    def test_no_asin(self):
        url = "https://www.amazon.com/s?k=headphones"
        self.assertEqual(extract_asin_from_url(url), "")

    def test_empty_string(self):
        self.assertEqual(extract_asin_from_url(""), "")

    def test_none(self):
        self.assertEqual(extract_asin_from_url(None), "")

    def test_asin_at_end_of_url(self):
        url = "https://www.amazon.com/dp/B0DCJT4Q4H"
        self.assertEqual(extract_asin_from_url(url), "B0DCJT4Q4H")

    def test_non_amazon_url(self):
        url = "https://www.example.com/dp/B09V3KXJPB"
        # The regex does not check domain, so it should still match.
        self.assertEqual(extract_asin_from_url(url), "B09V3KXJPB")

    def test_short_asin_rejected(self):
        url = "https://www.amazon.com/dp/B09V3"
        self.assertEqual(extract_asin_from_url(url), "")


# ---------------------------------------------------------------------------
# product_key_for_item
# ---------------------------------------------------------------------------
class TestProductKeyForItem(unittest.TestCase):
    def test_with_asin_source(self):
        item = {
            "name": "Echo Show 15",
            "sources": ["https://www.amazon.com/dp/B0BFZVFG6N?ref=x"],
        }
        self.assertEqual(product_key_for_item(item), "asin:B0BFZVFG6N")

    def test_without_sources(self):
        item = {"name": "Apple AirPods Pro"}
        result = product_key_for_item(item)
        self.assertEqual(result, "apple airpods pro")

    def test_with_non_amazon_sources(self):
        item = {
            "name": "Sony WH-1000XM5",
            "sources": ["https://www.bestbuy.com/product/12345"],
        }
        result = product_key_for_item(item)
        # No ASIN found, falls back to name-based key.
        self.assertIn("sony", result)

    def test_sources_is_none(self):
        item = {"name": "Samsung Galaxy Tab", "sources": None}
        result = product_key_for_item(item)
        self.assertIn("samsung", result)

    def test_multiple_sources_first_amazon_wins(self):
        item = {
            "name": "Echo Dot",
            "sources": [
                "https://www.bestbuy.com/some-product",
                "https://www.amazon.com/dp/B0BFZVFG6N",
            ],
        }
        self.assertEqual(product_key_for_item(item), "asin:B0BFZVFG6N")

    def test_empty_name_no_sources(self):
        item = {"name": ""}
        self.assertEqual(product_key_for_item(item), "")

    def test_missing_name_key(self):
        item = {}
        self.assertEqual(product_key_for_item(item), "")


# ---------------------------------------------------------------------------
# match_tokens
# ---------------------------------------------------------------------------
class TestMatchTokens(unittest.TestCase):
    def test_normal_text(self):
        result = match_tokens("Apple AirPods Pro 2026")
        self.assertIn("apple", result)
        self.assertIn("airpods", result)
        self.assertIn("pro", result)
        # "2026" is in IDEA_MATCH_STOPWORDS
        self.assertNotIn("2026", result)

    def test_all_stopwords(self):
        result = match_tokens("best buy top reviews for the home")
        self.assertEqual(result, [])

    def test_empty_string(self):
        self.assertEqual(match_tokens(""), [])

    def test_none(self):
        self.assertEqual(match_tokens(None), [])

    def test_filters_common_stopwords(self):
        result = match_tokens("best vs top guide comparison")
        # All of these are stopwords.
        self.assertEqual(result, [])

    def test_preserves_product_terms(self):
        result = match_tokens("echo show 15 smart display")
        self.assertIn("echo", result)
        self.assertIn("show", result)
        self.assertIn("15", result)
        self.assertIn("smart", result)
        self.assertIn("display", result)


# ---------------------------------------------------------------------------
# parse_ranked_products_from_research_text
# ---------------------------------------------------------------------------
class TestParseRankedProducts(unittest.TestCase):
    def test_numbered_bold_list(self):
        text = (
            "1. **Apple AirPods Max** - Premium headphones\n"
            "2. **Sony WH-1000XM5** - Active noise canceling\n"
            "3. **Bose QC Ultra** - Comfortable design\n"
        )
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], "Apple AirPods Max")
        self.assertEqual(result[1], "Sony WH-1000XM5")
        self.assertEqual(result[2], "Bose QC Ultra")

    def test_numbered_plain_list(self):
        text = (
            "1. Apple AirPods Max | $549\n"
            "2. Sony WH-1000XM5 | $349\n"
        )
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "Apple AirPods Max")
        self.assertEqual(result[1], "Sony WH-1000XM5")

    def test_explicit_product_marker(self):
        text = (
            "- **Product:** Apple AirPods Max\n"
            "- **Product:** Sony WH-1000XM5\n"
        )
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "Apple AirPods Max")

    def test_heading_style(self):
        text = (
            "## 1) Apple AirPods Max\n"
            "## 2) Sony WH-1000XM5\n"
        )
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "Apple AirPods Max")

    def test_table_format(self):
        text = (
            "| Apple AirPods Max | https://amazon.com/dp/B123456789 | $549 | 4.5 |\n"
            "| Sony WH-1000XM5 | https://amazon.com/dp/B987654321 | $349 | 4.7 |\n"
        )
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "Apple AirPods Max")

    def test_deduplication(self):
        text = (
            "1. **Apple AirPods Max** - Premium headphones\n"
            "2. **Apple AirPods Max** - Duplicate entry\n"
            "3. **Sony WH-1000XM5** - ANC headphones\n"
        )
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(len(result), 2)

    def test_limit(self):
        lines = [f"{i}. **Product {i} Model X** - Description" for i in range(1, 20)]
        text = "\n".join(lines)
        result = parse_ranked_products_from_research_text(text, limit=3)
        self.assertEqual(len(result), 3)

    def test_empty_text(self):
        result = parse_ranked_products_from_research_text("")
        self.assertEqual(result, [])

    def test_skips_product_keyword(self):
        text = "1. **Product** - This should be skipped\n"
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(result, [])

    def test_skips_na(self):
        text = "1. **N/A** - Not applicable\n"
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(result, [])

    def test_skips_single_word_names(self):
        text = "1. **Headphones** - Just one word\n"
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(result, [])

    def test_skips_prose_bullets(self):
        text = (
            "1. **Sony WH-1000XM5** - Great product\n"
            "2. **Price: $349** - Not a product\n"
            "3. **Pros and cons** - Not a product\n"
        )
        result = parse_ranked_products_from_research_text(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "Sony WH-1000XM5")


# ---------------------------------------------------------------------------
# split_products_by_novelty
# ---------------------------------------------------------------------------
class TestSplitProductsByNovelty(unittest.TestCase):
    def test_all_fresh(self):
        products = [
            {"name": "Apple AirPods Pro"},
            {"name": "Sony WH-1000XM5"},
        ]
        fresh, repeated = split_products_by_novelty(products, set())
        self.assertEqual(len(fresh), 2)
        self.assertEqual(len(repeated), 0)

    def test_all_blocked(self):
        products = [
            {"name": "Apple AirPods Pro"},
            {"name": "Sony WH-1000XM5"},
        ]
        blocked = {
            product_key("Apple AirPods Pro"),
            product_key("Sony WH-1000XM5"),
        }
        fresh, repeated = split_products_by_novelty(products, blocked)
        self.assertEqual(len(fresh), 0)
        self.assertEqual(len(repeated), 2)

    def test_mixed(self):
        products = [
            {"name": "Apple AirPods Pro"},
            {"name": "Sony WH-1000XM5"},
            {"name": "Bose QC Ultra Earbuds"},
        ]
        blocked = {product_key("Sony WH-1000XM5")}
        fresh, repeated = split_products_by_novelty(products, blocked)
        self.assertEqual(len(fresh), 2)
        self.assertEqual(len(repeated), 1)
        self.assertEqual(repeated[0]["name"], "Sony WH-1000XM5")

    def test_empty_list(self):
        fresh, repeated = split_products_by_novelty([], set())
        self.assertEqual(fresh, [])
        self.assertEqual(repeated, [])

    def test_asin_based_blocking(self):
        products = [
            {"name": "Echo Show 15", "sources": ["https://www.amazon.com/dp/B0BFZVFG6N"]},
        ]
        blocked = {"asin:B0BFZVFG6N"}
        fresh, repeated = split_products_by_novelty(products, blocked)
        self.assertEqual(len(fresh), 0)
        self.assertEqual(len(repeated), 1)


# ---------------------------------------------------------------------------
# infer_category_of_day
# ---------------------------------------------------------------------------
class TestInferCategoryOfDay(unittest.TestCase):
    def test_product_heuristic_echo_show(self):
        report = {}
        cat, reason = infer_category_of_day(report, "Echo Show 15", "Top Smart Home Gadgets")
        self.assertEqual(cat, "Smart displays")
        self.assertIn("product-first", reason)

    def test_product_heuristic_airpods(self):
        report = {}
        cat, reason = infer_category_of_day(report, "AirPods Pro 2nd Gen", "Best Earbuds")
        self.assertEqual(cat, "Open-ear / premium earbuds and headphones")
        self.assertIn("product-first", reason)

    def test_product_heuristic_ipad(self):
        report = {}
        cat, reason = infer_category_of_day(report, "iPad Air M2", "Best Tablets")
        self.assertEqual(cat, "Tablets")

    def test_product_heuristic_doorbell(self):
        report = {}
        cat, reason = infer_category_of_day(report, "Ring Doorbell Pro", "Home Security")
        self.assertEqual(cat, "Home security doorbells")

    def test_product_heuristic_smart_speaker(self):
        report = {}
        cat, reason = infer_category_of_day(report, "Echo Studio", "Best Speakers")
        self.assertEqual(cat, "Smart speakers")

    def test_product_heuristic_tv(self):
        report = {}
        cat, reason = infer_category_of_day(report, "Fire TV Stick 4K", "Streaming Devices")
        self.assertEqual(cat, "Budget-to-mid premium TVs")

    def test_rising_categories_fallback(self):
        report = {
            "risingCategories": [
                {
                    "category": "Smart displays",
                    "confidence": "high",
                    "observedFact": "Echo Show trending",
                },
            ],
        }
        cat, reason = infer_category_of_day(report, "Generic Product XY", "General Idea")
        self.assertEqual(cat, "Smart displays")
        self.assertEqual(reason, "Echo Show trending")

    def test_rising_categories_blended_label(self):
        report = {
            "risingCategories": [
                {
                    "category": "Smart displays / Smart speakers",
                    "confidence": "high",
                    "observedFact": "Trending",
                },
            ],
        }
        cat, reason = infer_category_of_day(report, "Generic Product XY", "General Idea")
        # Blended label should be converted to "Smart displays".
        self.assertEqual(cat, "Smart displays")

    def test_idea_heuristic_fallback(self):
        report = {"risingCategories": []}
        cat, reason = infer_category_of_day(report, "Generic Product XY", "Best earbuds under 100")
        self.assertEqual(cat, "Open-ear / premium earbuds and headphones")
        self.assertIn("fallback heuristic", reason)

    def test_default_fallback(self):
        report = {}
        cat, reason = infer_category_of_day(report, "Generic Product XY", "Some Random Title")
        self.assertEqual(cat, "Consumer Electronics (Amazon US)")
        self.assertEqual(reason, "fallback default category")

    def test_empty_report_and_inputs(self):
        cat, reason = infer_category_of_day({}, "", "")
        self.assertEqual(cat, "Consumer Electronics (Amazon US)")
        self.assertEqual(reason, "fallback default category")

    def test_rising_category_with_overlap(self):
        # The rising category that has token overlap with product/idea should win.
        report = {
            "risingCategories": [
                {
                    "category": "Kitchen Appliances",
                    "confidence": "low",
                },
                {
                    "category": "Noise Canceling Headphones",
                    "confidence": "high",
                    "observedFact": "ANC sales surge",
                },
            ],
        }
        cat, reason = infer_category_of_day(
            report, "Noise Canceling Headset Pro", "Headphones Review"
        )
        self.assertEqual(cat, "Noise Canceling Headphones")
        self.assertEqual(reason, "ANC sales surge")


# ---------------------------------------------------------------------------
# slugify None-safety and edge cases
# ---------------------------------------------------------------------------
class TestSlugifyNoneSafety(unittest.TestCase):
    def test_none_returns_opportunity(self):
        self.assertEqual(slugify(None), "opportunity")

    def test_none_with_max_len(self):
        self.assertEqual(slugify(None, max_len=5), "opportunity")

    def test_unicode_chars(self):
        result = slugify("Café & Résumé")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_max_len_1(self):
        result = slugify("hello", max_len=1)
        self.assertLessEqual(len(result), 1)

    def test_numeric_only(self):
        self.assertEqual(slugify("12345"), "12345")


# ---------------------------------------------------------------------------
# infer_category_of_day edge cases
# ---------------------------------------------------------------------------
class TestInferCategoryEdgeCases(unittest.TestCase):
    def test_none_product_and_idea(self):
        cat, reason = infer_category_of_day({}, None, None)
        self.assertEqual(cat, "Consumer Electronics (Amazon US)")

    def test_rising_categories_low_confidence_skipped(self):
        report = {
            "risingCategories": [
                {"category": "Kitchen Appliances", "confidence": "low"},
            ],
        }
        cat, reason = infer_category_of_day(report, "", "")
        # Low confidence with no overlap should still match if it's the only one
        self.assertIsInstance(cat, str)

    def test_multiple_rising_best_match(self):
        report = {
            "risingCategories": [
                {"category": "Random Category", "confidence": "medium"},
                {"category": "Tablets", "confidence": "high", "observedFact": "iPad trending"},
            ],
        }
        cat, reason = infer_category_of_day(report, "iPad Pro M4", "Best Tablets 2026")
        self.assertEqual(cat, "Tablets")


if __name__ == "__main__":
    unittest.main()
