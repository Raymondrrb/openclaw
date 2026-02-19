#!/usr/bin/env python3
"""Tests for tools/market_pulse_from_trends.py — daily market pulse builder."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from market_pulse_from_trends import (
    STOPWORDS,
    detect_source,
    extract_date_from_path,
    extract_keywords,
    find_combined_keywords,
    rank_queries,
)


# ---------------------------------------------------------------
# STOPWORDS
# ---------------------------------------------------------------

class TestStopwords(unittest.TestCase):

    def test_contains_common_words(self):
        for w in ("the", "and", "for", "best", "top", "review"):
            self.assertIn(w, STOPWORDS)

    def test_not_empty(self):
        self.assertGreater(len(STOPWORDS), 10)


# ---------------------------------------------------------------
# extract_date_from_path
# ---------------------------------------------------------------

class TestExtractDateFromPath(unittest.TestCase):

    def test_youtube_trend_file(self):
        self.assertEqual(
            extract_date_from_path("open_ear_2026-02-15.json"),
            "2026-02-15",
        )

    def test_brave_web_file(self):
        self.assertEqual(
            extract_date_from_path("earbuds_2026-02-15_brave_web.json"),
            "2026-02-15",
        )

    def test_brave_news_file(self):
        self.assertEqual(
            extract_date_from_path("earbuds_2026-02-15_brave_news.json"),
            "2026-02-15",
        )

    def test_no_date(self):
        self.assertIsNone(extract_date_from_path("random_file.json"))

    def test_full_path(self):
        self.assertEqual(
            extract_date_from_path("/reports/trends/smart_speakers_2026-01-10.json"),
            "2026-01-10",
        )

    def test_wrong_format(self):
        self.assertIsNone(extract_date_from_path("slug_20260215.json"))


# ---------------------------------------------------------------
# detect_source
# ---------------------------------------------------------------

class TestDetectSource(unittest.TestCase):

    def test_youtube_default(self):
        self.assertEqual(detect_source("trend_2026-02-15.json", {}), "youtube")

    def test_brave_web_by_filename(self):
        self.assertEqual(
            detect_source("earbuds_2026-02-15_brave_web.json", {}),
            "brave_web",
        )

    def test_brave_news_by_filename(self):
        self.assertEqual(
            detect_source("earbuds_2026-02-15_brave_news.json", {}),
            "brave_news",
        )

    def test_brave_web_by_data(self):
        data = {"source": "brave", "searchType": "web"}
        self.assertEqual(detect_source("report.json", data), "brave_web")

    def test_brave_news_by_data(self):
        data = {"source": "brave", "searchType": "news"}
        self.assertEqual(detect_source("report.json", data), "brave_news")


# ---------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------

class TestExtractKeywords(unittest.TestCase):

    def test_empty_datasets(self):
        result = extract_keywords([], 5)
        self.assertEqual(len(result), 0)

    def test_extracts_from_titles(self):
        datasets = [
            {"items": [
                {"title": "Sony WH-1000XM5 Review"},
                {"title": "Best Sony Headphones 2026"},
            ]},
        ]
        kw = extract_keywords(datasets, 5)
        self.assertIn("sony", kw)
        self.assertIn("headphones", kw)

    def test_filters_stopwords(self):
        datasets = [
            {"items": [{"title": "The Best Top Review Amazon"}]},
        ]
        kw = extract_keywords(datasets, 5)
        # All words are stopwords
        self.assertEqual(len(kw), 0)

    def test_filters_digits(self):
        datasets = [
            {"items": [{"title": "123 456 test789"}]},
        ]
        kw = extract_keywords(datasets, 5)
        self.assertNotIn("123", kw)
        self.assertNotIn("456", kw)

    def test_respects_top_items_limit(self):
        datasets = [
            {"items": [
                {"title": "alpha device"},
                {"title": "beta device"},
                {"title": "gamma device"},
            ]},
        ]
        kw = extract_keywords(datasets, 2)
        # Only first 2 items should be processed
        self.assertIn("alpha", kw)
        self.assertIn("beta", kw)
        self.assertNotIn("gamma", kw)

    def test_counts_occurrences(self):
        datasets = [
            {"items": [
                {"title": "wireless earbuds comparison"},
                {"title": "wireless headphones review"},
            ]},
        ]
        kw = extract_keywords(datasets, 5)
        self.assertEqual(kw["wireless"], 2)


# ---------------------------------------------------------------
# rank_queries
# ---------------------------------------------------------------

class TestRankQueries(unittest.TestCase):

    def test_empty_datasets(self):
        yt, brave = rank_queries([])
        self.assertEqual(yt, [])
        self.assertEqual(brave, [])

    def test_youtube_ranked_by_vph(self):
        datasets = [
            {"query": "earbuds", "items": [
                {"viewsPerHour": 500},
                {"viewsPerHour": 200},
            ], "_source": "youtube"},
            {"query": "headphones", "items": [
                {"viewsPerHour": 1000},
            ], "_source": "youtube"},
        ]
        yt, brave = rank_queries(datasets)
        self.assertEqual(len(yt), 2)
        self.assertEqual(yt[0]["query"], "headphones")
        self.assertEqual(yt[0]["bestViewsPerHour"], 1000)
        self.assertEqual(yt[1]["query"], "earbuds")

    def test_brave_ranked_by_mention_score(self):
        datasets = [
            {"query": "q1", "items": [
                {"mentionScore": 10},
                {"mentionScore": 5},
            ], "_source": "brave_web"},
            {"query": "q2", "items": [
                {"mentionScore": 20},
            ], "_source": "brave_web"},
        ]
        yt, brave = rank_queries(datasets)
        self.assertEqual(len(brave), 2)
        self.assertEqual(brave[0]["query"], "q2")
        self.assertEqual(brave[0]["totalMentionScore"], 20)

    def test_normalized_scores(self):
        datasets = [
            {"query": "top", "items": [
                {"viewsPerHour": 1000},
            ], "_source": "youtube"},
            {"query": "low", "items": [
                {"viewsPerHour": 500},
            ], "_source": "youtube"},
        ]
        yt, _ = rank_queries(datasets)
        self.assertEqual(yt[0]["normalizedScore"], 100.0)
        self.assertEqual(yt[1]["normalizedScore"], 50.0)

    def test_mixed_sources_separated(self):
        datasets = [
            {"query": "yt_q", "items": [{"viewsPerHour": 100}], "_source": "youtube"},
            {"query": "br_q", "items": [{"mentionScore": 50}], "_source": "brave_web"},
        ]
        yt, brave = rank_queries(datasets)
        self.assertEqual(len(yt), 1)
        self.assertEqual(len(brave), 1)
        self.assertEqual(yt[0]["query"], "yt_q")
        self.assertEqual(brave[0]["query"], "br_q")

    def test_empty_items(self):
        datasets = [
            {"query": "empty", "items": [], "_source": "youtube"},
        ]
        yt, _ = rank_queries(datasets)
        self.assertEqual(yt[0]["bestViewsPerHour"], 0.0)
        self.assertEqual(yt[0]["count"], 0)


# ---------------------------------------------------------------
# find_combined_keywords
# ---------------------------------------------------------------

class TestFindCombinedKeywords(unittest.TestCase):

    def test_empty_datasets(self):
        result = find_combined_keywords([], 5)
        self.assertEqual(result, [])

    def test_finds_overlapping_keywords(self):
        datasets = [
            {"_source": "youtube", "items": [
                {"title": "sony headphones review", "description": ""},
            ]},
            {"_source": "brave_web", "items": [
                {"title": "sony speakers comparison", "description": ""},
            ]},
        ]
        result = find_combined_keywords(datasets, 5)
        keywords = [w for w, _ in result]
        self.assertIn("sony", keywords)

    def test_no_overlap(self):
        datasets = [
            {"_source": "youtube", "items": [
                {"title": "alpha bravo charlie", "description": ""},
            ]},
            {"_source": "brave_web", "items": [
                {"title": "delta echo foxtrot", "description": ""},
            ]},
        ]
        result = find_combined_keywords(datasets, 5)
        self.assertEqual(result, [])

    def test_sorted_by_combined_count(self):
        datasets = [
            {"_source": "youtube", "items": [
                {"title": "wireless earbuds wireless headphones", "description": ""},
            ]},
            {"_source": "brave_web", "items": [
                {"title": "wireless speakers earbuds comparison", "description": ""},
            ]},
        ]
        result = find_combined_keywords(datasets, 5)
        keywords = [w for w, _ in result]
        # "wireless" appears 3 times total (2 yt + 1 brave), earbuds 2 times
        if "wireless" in keywords and "earbuds" in keywords:
            self.assertLess(keywords.index("wireless"), keywords.index("earbuds"))

    def test_includes_description(self):
        datasets = [
            {"_source": "youtube", "items": [
                {"title": "test", "description": "synergy"},
            ]},
            {"_source": "brave_web", "items": [
                {"title": "other", "description": "synergy"},
            ]},
        ]
        result = find_combined_keywords(datasets, 5)
        keywords = [w for w, _ in result]
        self.assertIn("synergy", keywords)


if __name__ == "__main__":
    unittest.main()
