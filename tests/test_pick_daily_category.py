#!/usr/bin/env python3
"""Tests for tools/pick_daily_category.py — category-of-the-day rotation logic."""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pick_daily_category import pick_category


# ---------------------------------------------------------------
# pick_category
# ---------------------------------------------------------------

class TestPickCategory(unittest.TestCase):

    def test_deterministic(self):
        cats = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
        d = dt.date(2026, 2, 15)
        result1 = pick_category(d, cats)
        result2 = pick_category(d, cats)
        self.assertEqual(result1, result2)

    def test_different_days_different_picks(self):
        cats = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
        picks = set()
        for day in range(1, 4):
            result = pick_category(dt.date(2026, 1, day), cats)
            picks.add(result["slug"])
        # With 3 consecutive days and 3 categories, all should be picked
        self.assertEqual(len(picks), 3)

    def test_single_category(self):
        cats = [{"slug": "only"}]
        result = pick_category(dt.date(2026, 6, 1), cats)
        self.assertEqual(result["slug"], "only")

    def test_empty_categories_raises(self):
        with self.assertRaises(ValueError):
            pick_category(dt.date(2026, 1, 1), [])

    def test_rotation_wraps_around(self):
        cats = [{"slug": "a"}, {"slug": "b"}]
        # Over 4 consecutive days, we should see each category twice
        results = [pick_category(dt.date(2026, 1, d), cats)["slug"] for d in range(1, 5)]
        self.assertEqual(results.count("a"), 2)
        self.assertEqual(results.count("b"), 2)

    def test_ordinal_based(self):
        cats = [{"slug": "x"}, {"slug": "y"}, {"slug": "z"}]
        d = dt.date(2026, 2, 15)
        expected_idx = d.toordinal() % 3
        result = pick_category(d, cats)
        self.assertEqual(result, cats[expected_idx])

    def test_returns_full_dict(self):
        cats = [{"slug": "earbuds", "label": "Earbuds", "amazon": {"url": "..."}}]
        result = pick_category(dt.date(2026, 1, 1), cats)
        self.assertEqual(result["label"], "Earbuds")
        self.assertIn("amazon", result)


# ---------------------------------------------------------------
# pick_category edge cases
# ---------------------------------------------------------------

class TestPickCategoryEdgeCases(unittest.TestCase):

    def test_large_category_list(self):
        cats = [{"slug": f"cat_{i}"} for i in range(100)]
        result = pick_category(dt.date(2026, 6, 15), cats)
        self.assertIn(result, cats)

    def test_leap_year_date(self):
        cats = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
        result = pick_category(dt.date(2028, 2, 29), cats)
        self.assertIn(result["slug"], {"a", "b", "c"})

    def test_far_future_date(self):
        cats = [{"slug": "x"}, {"slug": "y"}]
        result = pick_category(dt.date(2050, 12, 31), cats)
        self.assertIn(result["slug"], {"x", "y"})

    def test_same_day_different_year(self):
        cats = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
        r2026 = pick_category(dt.date(2026, 1, 1), cats)
        r2027 = pick_category(dt.date(2027, 1, 1), cats)
        # Different years same day should pick different categories (365 % 3 != 0)
        # Not guaranteed to be different with all sizes, so just check validity
        self.assertIn(r2026, cats)
        self.assertIn(r2027, cats)

    def test_category_with_extra_fields(self):
        cats = [
            {"slug": "earbuds", "label": "Earbuds", "priority": 1, "amazon": {"url": "..."}},
            {"slug": "tvs", "label": "TVs", "priority": 2},
        ]
        result = pick_category(dt.date(2026, 3, 1), cats)
        self.assertIn("slug", result)
        self.assertIn("label", result)

    def test_two_categories_alternate(self):
        cats = [{"slug": "a"}, {"slug": "b"}]
        d1 = pick_category(dt.date(2026, 1, 1), cats)
        d2 = pick_category(dt.date(2026, 1, 2), cats)
        self.assertNotEqual(d1["slug"], d2["slug"])

    def test_none_categories_raises(self):
        with self.assertRaises((ValueError, TypeError)):
            pick_category(dt.date(2026, 1, 1), None)


# ---------------------------------------------------------------
# load_config
# ---------------------------------------------------------------

class TestLoadConfig(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_config(self, data) -> str:
        import json
        p = os.path.join(self._tmpdir, "cfg.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_loads_valid_config(self):
        from pick_daily_category import load_config
        p = self._write_config({"categories": [{"slug": "earbuds"}]})
        cfg = load_config(p)
        self.assertEqual(len(cfg["categories"]), 1)

    def test_empty_categories_list(self):
        from pick_daily_category import load_config
        p = self._write_config({"categories": []})
        cfg = load_config(p)
        self.assertEqual(cfg["categories"], [])

    def test_missing_file_raises(self):
        from pick_daily_category import load_config
        with self.assertRaises(FileNotFoundError):
            load_config("/nonexistent/config.json")

    def test_invalid_json_raises(self):
        from pick_daily_category import load_config
        p = os.path.join(self._tmpdir, "bad.json")
        with open(p, "w") as f:
            f.write("{invalid")
        with self.assertRaises(Exception):
            load_config(p)

    def test_config_with_policy(self):
        from pick_daily_category import load_config
        p = self._write_config({
            "categories": [{"slug": "a"}],
            "policy": {"min_price": 100, "max_price": 500},
        })
        cfg = load_config(p)
        self.assertEqual(cfg["policy"]["min_price"], 100)


# ---------------------------------------------------------------
# pick_category + load_config integration
# ---------------------------------------------------------------

class TestPickCategoryConsecutiveDays(unittest.TestCase):

    def test_full_rotation_cycle(self):
        """Every category appears exactly once in a full rotation cycle."""
        cats = [{"slug": f"cat_{i}"} for i in range(7)]
        seen = set()
        for day in range(7):
            result = pick_category(dt.date(2026, 3, 1 + day), cats)
            seen.add(result["slug"])
        self.assertEqual(len(seen), 7)

    def test_two_is_minimum_for_alternation(self):
        cats = [{"slug": "a"}, {"slug": "b"}]
        results = [pick_category(dt.date(2026, 1, d), cats)["slug"] for d in range(1, 11)]
        self.assertEqual(results.count("a"), 5)
        self.assertEqual(results.count("b"), 5)


if __name__ == "__main__":
    unittest.main()
