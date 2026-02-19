#!/usr/bin/env python3
"""Tests for tools/notify_gate1_ready.py — Gate 1 notification utilities."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from notify_gate1_ready import extract_category, find_latest_gate1_for_date


# ---------------------------------------------------------------
# extract_category
# ---------------------------------------------------------------

class TestExtractCategory(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, content: str) -> Path:
        p = Path(self.tmpdir) / "gate1_review.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_extracts_category(self):
        p = self._write("# Gate 1 Review\n\n- Category: `Smart rings`\n- Date: 2026-02-15\n")
        self.assertEqual(extract_category(p), "Smart rings")

    def test_extracts_without_backticks(self):
        p = self._write("- Category: Wireless earbuds\n")
        self.assertEqual(extract_category(p), "Wireless earbuds")

    def test_case_insensitive_prefix(self):
        p = self._write("- category: Headphones\n")
        self.assertEqual(extract_category(p), "Headphones")

    def test_no_category_line(self):
        p = self._write("# Review\n\nSome content without category.\n")
        self.assertEqual(extract_category(p), "")

    def test_empty_file(self):
        p = self._write("")
        self.assertEqual(extract_category(p), "")

    def test_missing_file(self):
        result = extract_category(Path("/nonexistent/gate1_review.md"))
        self.assertEqual(result, "")

    def test_multiple_lines_returns_first(self):
        p = self._write(
            "- Category: `First`\n"
            "- Category: `Second`\n"
        )
        self.assertEqual(extract_category(p), "First")

    def test_strips_whitespace(self):
        p = self._write("- Category:   Open ear headphones  \n")
        self.assertEqual(extract_category(p), "Open ear headphones")


    def test_special_chars_in_category(self):
        p = self._write("- Category: `USB-C/Thunderbolt Hubs`\n")
        self.assertEqual(extract_category(p), "USB-C/Thunderbolt Hubs")

    def test_colon_variations(self):
        p = self._write("- Category:Smart rings\n")
        self.assertEqual(extract_category(p), "Smart rings")

    def test_backtick_with_spaces(self):
        p = self._write("- Category: `  Spaced  Category  `\n")
        result = extract_category(p)
        self.assertIn("Category", result)


# ---------------------------------------------------------------
# find_latest_gate1_for_date
# ---------------------------------------------------------------

class TestFindLatestGate1ForDate(unittest.TestCase):

    def setUp(self):
        import shutil
        self.tmpdir = tempfile.mkdtemp()
        import notify_gate1_ready
        self._orig_runs = notify_gate1_ready.RUNS_DIR
        notify_gate1_ready.RUNS_DIR = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        import notify_gate1_ready
        notify_gate1_ready.RUNS_DIR = self._orig_runs
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_run(self, slug: str, gate1_content: str = "- Category: `Test`\n"):
        d = Path(self.tmpdir) / slug
        d.mkdir(parents=True, exist_ok=True)
        g = d / "gate1_review.md"
        g.write_text(gate1_content, encoding="utf-8")
        return d

    def test_no_runs_dir(self):
        import notify_gate1_ready
        notify_gate1_ready.RUNS_DIR = Path("/nonexistent/runs")
        result = find_latest_gate1_for_date("2026-02-16")
        self.assertIsNone(result)

    def test_empty_runs_dir(self):
        result = find_latest_gate1_for_date("2026-02-16")
        self.assertIsNone(result)

    def test_finds_matching_run(self):
        self._make_run("earbuds_2026-02-16")
        result = find_latest_gate1_for_date("2026-02-16")
        self.assertIsNotNone(result)
        slug, path = result
        self.assertEqual(slug, "earbuds_2026-02-16")
        self.assertTrue(path.exists())

    def test_ignores_different_date(self):
        self._make_run("earbuds_2026-02-15")
        result = find_latest_gate1_for_date("2026-02-16")
        self.assertIsNone(result)

    def test_ignores_empty_gate1(self):
        d = Path(self.tmpdir) / "earbuds_2026-02-16"
        d.mkdir()
        (d / "gate1_review.md").write_text("", encoding="utf-8")
        result = find_latest_gate1_for_date("2026-02-16")
        self.assertIsNone(result)

    def test_ignores_no_gate1_file(self):
        d = Path(self.tmpdir) / "earbuds_2026-02-16"
        d.mkdir()
        result = find_latest_gate1_for_date("2026-02-16")
        self.assertIsNone(result)

    def test_multiple_runs_returns_latest(self):
        import time
        self._make_run("earbuds_2026-02-16")
        time.sleep(0.05)
        self._make_run("headphones_2026-02-16")
        result = find_latest_gate1_for_date("2026-02-16")
        self.assertIsNotNone(result)
        slug, _ = result
        self.assertEqual(slug, "headphones_2026-02-16")

    def test_non_dir_entry_ignored(self):
        # Create a file (not dir) matching the glob pattern
        f = Path(self.tmpdir) / "notadir_2026-02-16"
        f.write_text("x", encoding="utf-8")
        result = find_latest_gate1_for_date("2026-02-16")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
