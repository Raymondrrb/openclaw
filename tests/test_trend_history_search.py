#!/usr/bin/env python3
"""Tests for tools/trend_history_search.py — SQLite FTS5 trend search utilities."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from trend_history_search import (
    detect_source,
    extract_content_from_json,
    extract_content_from_md,
    extract_date,
    extract_slug,
)


# ---------------------------------------------------------------
# extract_date
# ---------------------------------------------------------------

class TestExtractDate(unittest.TestCase):

    def test_youtube_trend_file(self):
        self.assertEqual(extract_date("open_ear_2026-02-15.json"), "2026-02-15")

    def test_brave_web_file(self):
        self.assertEqual(extract_date("earbuds_2026-01-10_brave_web.json"), "2026-01-10")

    def test_brave_news_file(self):
        self.assertEqual(extract_date("earbuds_2026-03-22_brave_news.json"), "2026-03-22")

    def test_no_date(self):
        self.assertEqual(extract_date("random_file.json"), "")

    def test_full_path(self):
        self.assertEqual(
            extract_date("/reports/trends/smart_speakers_2026-01-10.json"),
            "2026-01-10",
        )

    def test_market_pulse_file(self):
        self.assertEqual(extract_date("2026-02-15_market_pulse.json"), "2026-02-15")


# ---------------------------------------------------------------
# detect_source
# ---------------------------------------------------------------

class TestDetectSource(unittest.TestCase):

    def test_youtube_default(self):
        self.assertEqual(detect_source("trend_2026-02-15.json"), "youtube")

    def test_brave_web(self):
        self.assertEqual(detect_source("earbuds_2026-02-15_brave_web.json"), "brave_web")

    def test_brave_news(self):
        self.assertEqual(detect_source("earbuds_2026-02-15_brave_news.json"), "brave_news")

    def test_market_pulse(self):
        self.assertEqual(detect_source("2026-02-15_market_pulse.json"), "market")

    def test_market_delta(self):
        self.assertEqual(detect_source("2026-02-15_market_delta.json"), "market")

    def test_category_of_day(self):
        self.assertEqual(detect_source("category_of_day_2026-02-15.json"), "market")

    def test_full_path(self):
        self.assertEqual(
            detect_source("/reports/trends/earbuds_2026-02-15_brave_web.json"),
            "brave_web",
        )

    def test_plain_json(self):
        self.assertEqual(detect_source("something.json"), "youtube")


# ---------------------------------------------------------------
# extract_slug
# ---------------------------------------------------------------

class TestExtractSlug(unittest.TestCase):

    def test_youtube_slug(self):
        self.assertEqual(extract_slug("open_ear_2026-02-15.json"), "open_ear")

    def test_brave_web_slug(self):
        self.assertEqual(extract_slug("earbuds_2026-02-15_brave_web.json"), "earbuds")

    def test_no_date(self):
        self.assertEqual(extract_slug("random_file.json"), "random_file.json")

    def test_full_path(self):
        self.assertEqual(
            extract_slug("/reports/trends/smart_speakers_2026-01-10.json"),
            "smart_speakers",
        )

    def test_multi_word_slug(self):
        self.assertEqual(
            extract_slug("best_wireless_headphones_2026-03-01.json"),
            "best_wireless_headphones",
        )


# ---------------------------------------------------------------
# extract_content_from_json
# ---------------------------------------------------------------

class TestExtractContentFromJson(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, data):
        p = Path(self.tmpdir) / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)

    def test_extracts_query_as_title(self):
        path = self._write("test.json", {"query": "earbuds", "items": []})
        title, content = extract_content_from_json(path)
        self.assertEqual(title, "earbuds")

    def test_extracts_item_titles(self):
        path = self._write("test.json", {
            "query": "q",
            "items": [
                {"title": "Sony WH-1000XM5", "description": "ANC headphones"},
                {"title": "Bose QC Ultra", "channelTitle": "TechReview"},
            ],
        })
        title, content = extract_content_from_json(path)
        self.assertIn("Sony WH-1000XM5", content)
        self.assertIn("ANC headphones", content)
        self.assertIn("Bose QC Ultra", content)
        self.assertIn("TechReview", content)

    def test_extracts_query_velocity(self):
        path = self._write("pulse.json", {
            "queryVelocity": [
                {"query": "portable monitor"},
                {"query": "wireless earbuds"},
            ],
        })
        _, content = extract_content_from_json(path)
        self.assertIn("portable monitor", content)
        self.assertIn("wireless earbuds", content)

    def test_extracts_top_keywords(self):
        path = self._write("pulse.json", {
            "topKeywords": [["wireless", 5], ["earbuds", 3]],
        })
        _, content = extract_content_from_json(path)
        self.assertIn("wireless", content)
        self.assertIn("earbuds", content)

    def test_missing_file(self):
        title, content = extract_content_from_json("/nonexistent/path.json")
        self.assertEqual(title, "")
        self.assertEqual(content, "")

    def test_invalid_json(self):
        p = Path(self.tmpdir) / "bad.json"
        p.write_text("not json {{{", encoding="utf-8")
        title, content = extract_content_from_json(str(p))
        self.assertEqual(title, "")
        self.assertEqual(content, "")

    def test_fallback_title_to_basename(self):
        path = self._write("myfile.json", {"items": []})
        title, _ = extract_content_from_json(path)
        self.assertIn("myfile.json", title)


# ---------------------------------------------------------------
# extract_content_from_md
# ---------------------------------------------------------------

class TestExtractContentFromMd(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_extracts_title_from_heading(self):
        p = Path(self.tmpdir) / "report.md"
        p.write_text("# Daily Market Pulse\n\nSome content here.", encoding="utf-8")
        title, content = extract_content_from_md(str(p))
        self.assertEqual(title, "Daily Market Pulse")

    def test_content_includes_full_text(self):
        p = Path(self.tmpdir) / "report.md"
        text = "# Title\n\nParagraph one.\n\nParagraph two."
        p.write_text(text, encoding="utf-8")
        _, content = extract_content_from_md(str(p))
        self.assertIn("Paragraph one.", content)
        self.assertIn("Paragraph two.", content)

    def test_missing_file(self):
        title, content = extract_content_from_md("/nonexistent/report.md")
        self.assertEqual(title, "")
        self.assertEqual(content, "")

    def test_empty_file(self):
        p = Path(self.tmpdir) / "empty.md"
        p.write_text("", encoding="utf-8")
        title, _ = extract_content_from_md(str(p))
        # Empty file → first line is "", stripped is ""
        self.assertEqual(title, "")


if __name__ == "__main__":
    unittest.main()
