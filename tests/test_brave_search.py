#!/usr/bin/env python3
"""Tests for tools/brave_search.py — Brave Search result parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from brave_search import (
    PRODUCT_KEYWORDS,
    compute_mention_score,
    extract_domain,
    parse_results,
)


# ---------------------------------------------------------------
# PRODUCT_KEYWORDS
# ---------------------------------------------------------------

class TestProductKeywords(unittest.TestCase):

    def test_not_empty(self):
        self.assertGreater(len(PRODUCT_KEYWORDS), 10)

    def test_contains_core_terms(self):
        for w in ("best", "top", "review", "comparison", "budget", "premium"):
            self.assertIn(w, PRODUCT_KEYWORDS)

    def test_all_lowercase(self):
        for kw in PRODUCT_KEYWORDS:
            self.assertEqual(kw, kw.lower())


# ---------------------------------------------------------------
# compute_mention_score
# ---------------------------------------------------------------

class TestComputeMentionScore(unittest.TestCase):

    def test_no_keywords(self):
        score = compute_mention_score("Random title", "Some description")
        self.assertEqual(score, 0.0)

    def test_single_keyword_in_title(self):
        score = compute_mention_score("Best earbuds", "")
        self.assertEqual(score, 1.0)

    def test_multiple_keywords(self):
        score = compute_mention_score("Best budget earbuds review", "Top picks comparison")
        self.assertGreaterEqual(score, 4.0)

    def test_case_insensitive(self):
        score = compute_mention_score("BEST REVIEW", "")
        self.assertEqual(score, 2.0)

    def test_keyword_in_description(self):
        score = compute_mention_score("Earbuds", "top premium review")
        self.assertGreaterEqual(score, 3.0)

    def test_hyphenated_keyword(self):
        score = compute_mention_score("must-have gadget", "")
        self.assertEqual(score, 1.0)

    def test_empty_strings(self):
        score = compute_mention_score("", "")
        self.assertEqual(score, 0.0)

    def test_duplicate_keyword_counted_once(self):
        # "best" appears twice but should only score 1 (set-based)
        score = compute_mention_score("best best", "")
        self.assertEqual(score, 1.0)


# ---------------------------------------------------------------
# extract_domain
# ---------------------------------------------------------------

class TestExtractDomain(unittest.TestCase):

    def test_https_url(self):
        self.assertEqual(extract_domain("https://example.com/page"), "example.com")

    def test_http_url(self):
        self.assertEqual(extract_domain("http://www.test.org/path"), "www.test.org")

    def test_url_with_port(self):
        self.assertEqual(extract_domain("https://localhost:8080/api"), "localhost:8080")

    def test_empty_string(self):
        self.assertEqual(extract_domain(""), "")

    def test_no_scheme(self):
        # Without scheme, urlparse treats it as path
        result = extract_domain("example.com/page")
        self.assertEqual(result, "")

    def test_complex_url(self):
        self.assertEqual(
            extract_domain("https://sub.domain.co.uk/path?q=1&a=2#frag"),
            "sub.domain.co.uk",
        )


# ---------------------------------------------------------------
# parse_results
# ---------------------------------------------------------------

class TestParseResults(unittest.TestCase):

    def test_web_results(self):
        raw = {
            "web": {
                "results": [
                    {"title": "Best Earbuds 2026", "description": "Top review", "url": "https://example.com/1", "age": "2d"},
                    {"title": "Random Tech", "description": "No keywords here", "url": "https://other.com/2", "age": "3d"},
                ],
            },
        }
        items = parse_results(raw, "web")
        self.assertEqual(len(items), 2)
        # Sorted by mentionScore desc
        self.assertGreater(items[0]["mentionScore"], items[1]["mentionScore"])

    def test_web_item_structure(self):
        raw = {
            "web": {
                "results": [
                    {"title": "Test", "description": "Desc", "url": "https://example.com/x", "age": "1d"},
                ],
            },
        }
        items = parse_results(raw, "web")
        item = items[0]
        self.assertIn("title", item)
        self.assertIn("url", item)
        self.assertIn("description", item)
        self.assertIn("age", item)
        self.assertIn("domain", item)
        self.assertIn("mentionScore", item)
        self.assertEqual(item["domain"], "example.com")

    def test_news_results(self):
        raw = {
            "results": [
                {"title": "Budget earbuds review", "description": "comparison", "url": "https://news.com/1", "age": "5h"},
            ],
        }
        items = parse_results(raw, "news")
        self.assertEqual(len(items), 1)
        self.assertGreater(items[0]["mentionScore"], 0)

    def test_empty_web(self):
        items = parse_results({"web": {"results": []}}, "web")
        self.assertEqual(items, [])

    def test_empty_news(self):
        items = parse_results({"results": []}, "news")
        self.assertEqual(items, [])

    def test_missing_fields_default(self):
        raw = {"web": {"results": [{}]}}
        items = parse_results(raw, "web")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "")
        self.assertEqual(items[0]["url"], "")

    def test_unknown_type_returns_empty(self):
        raw = {"web": {"results": [{"title": "X", "description": "Y", "url": "", "age": ""}]}}
        items = parse_results(raw, "images")
        self.assertEqual(items, [])

    def test_sorted_by_mention_score_desc(self):
        raw = {
            "web": {
                "results": [
                    {"title": "Random stuff", "description": "nothing", "url": "", "age": ""},
                    {"title": "Best top review comparison budget", "description": "premium deal", "url": "", "age": ""},
                ],
            },
        }
        items = parse_results(raw, "web")
        self.assertGreaterEqual(items[0]["mentionScore"], items[1]["mentionScore"])


# ---------------------------------------------------------------
# compute_mention_score edge cases
# ---------------------------------------------------------------

class TestComputeMentionScoreEdgeCases(unittest.TestCase):

    def test_none_title(self):
        # None title should not crash
        try:
            score = compute_mention_score(None, "description")
            self.assertIsInstance(score, (int, float))
        except (TypeError, AttributeError):
            pass  # Acceptable if it raises

    def test_none_description(self):
        try:
            score = compute_mention_score("title", None)
            self.assertIsInstance(score, (int, float))
        except (TypeError, AttributeError):
            pass

    def test_very_long_text(self):
        title = "best " * 1000
        desc = "review " * 1000
        score = compute_mention_score(title, desc)
        # Score should be finite regardless of text length
        self.assertGreater(score, 0)

    def test_special_characters_ignored(self):
        score = compute_mention_score("best@#$%earbuds!!!", "")
        # "best" should still match
        self.assertGreater(score, 0)


# ---------------------------------------------------------------
# extract_domain edge cases
# ---------------------------------------------------------------

class TestExtractDomainEdgeCases(unittest.TestCase):

    def test_none_input(self):
        try:
            result = extract_domain(None)
            self.assertIsInstance(result, str)
        except (TypeError, AttributeError):
            pass

    def test_ftp_scheme(self):
        result = extract_domain("ftp://files.example.com/data")
        self.assertEqual(result, "files.example.com")

    def test_unicode_domain(self):
        result = extract_domain("https://例え.jp/page")
        self.assertIsInstance(result, str)

    def test_ip_address(self):
        result = extract_domain("https://192.168.1.1/api")
        self.assertEqual(result, "192.168.1.1")


# ---------------------------------------------------------------
# parse_results edge cases
# ---------------------------------------------------------------

class TestParseResultsEdgeCases(unittest.TestCase):

    def test_none_raw(self):
        try:
            items = parse_results(None, "web")
            self.assertEqual(items, [])
        except (TypeError, AttributeError):
            pass

    def test_empty_dict(self):
        items = parse_results({}, "web")
        self.assertEqual(items, [])

    def test_news_with_web_type(self):
        # News data structure queried with "web" type
        raw = {"results": [{"title": "T", "description": "D", "url": "", "age": ""}]}
        items = parse_results(raw, "web")
        # web looks for raw["web"]["results"], not raw["results"]
        self.assertEqual(items, [])

    def test_many_results(self):
        results = [{"title": f"Item {i}", "description": "best review", "url": f"https://ex.com/{i}", "age": "1d"} for i in range(50)]
        raw = {"web": {"results": results}}
        items = parse_results(raw, "web")
        self.assertEqual(len(items), 50)


if __name__ == "__main__":
    unittest.main()
