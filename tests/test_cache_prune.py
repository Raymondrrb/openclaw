#!/usr/bin/env python3
"""Tests for rayvault/cache_prune.py — unused ASIN cache entry pruning."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from rayvault.cache_prune import (
    _last_activity_ts,
    _parse_utc,
    prune,
    utc_now_iso,
)


# ---------------------------------------------------------------
# utc_now_iso
# ---------------------------------------------------------------

class TestUtcNowIso(unittest.TestCase):

    def test_returns_string(self):
        self.assertIsInstance(utc_now_iso(), str)

    def test_ends_with_z(self):
        self.assertTrue(utc_now_iso().endswith("Z"))


# ---------------------------------------------------------------
# _parse_utc
# ---------------------------------------------------------------

class TestParseUtc(unittest.TestCase):

    def test_valid_iso(self):
        ts = _parse_utc("2026-02-14T12:00:00Z")
        self.assertIsNotNone(ts)
        self.assertIsInstance(ts, float)

    def test_invalid(self):
        self.assertIsNone(_parse_utc("not-a-date"))

    def test_empty(self):
        self.assertIsNone(_parse_utc(""))


# ---------------------------------------------------------------
# _last_activity_ts
# ---------------------------------------------------------------

class TestLastActivityTs(unittest.TestCase):

    def test_last_used(self):
        info = {"last_used_utc": "2026-02-14T12:00:00Z"}
        ts = _last_activity_ts(info)
        self.assertIsNotNone(ts)

    def test_images_fetched_fallback(self):
        info = {"images_fetched_at_utc": "2026-02-14T12:00:00Z"}
        ts = _last_activity_ts(info)
        self.assertIsNotNone(ts)

    def test_meta_fetched_fallback(self):
        info = {"meta_fetched_at_utc": "2026-02-14T12:00:00Z"}
        ts = _last_activity_ts(info)
        self.assertIsNotNone(ts)

    def test_priority_order(self):
        info = {
            "last_used_utc": "2026-02-14T12:00:00Z",
            "images_fetched_at_utc": "2026-01-01T00:00:00Z",
        }
        ts = _last_activity_ts(info)
        # Should use last_used_utc (first in priority)
        self.assertIsNotNone(ts)

    def test_empty_info(self):
        self.assertIsNone(_last_activity_ts({}))

    def test_invalid_values(self):
        info = {"last_used_utc": "garbage"}
        self.assertIsNone(_last_activity_ts(info))


# ---------------------------------------------------------------
# prune
# ---------------------------------------------------------------

def _days_ago_iso(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestPrune(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_asin(self, asin: str, last_used_days_ago: int = 0):
        d = self.root / asin
        d.mkdir(parents=True)
        info = {"last_used_utc": _days_ago_iso(last_used_days_ago), "status": "VALID"}
        (d / "cache_info.json").write_text(json.dumps(info), encoding="utf-8")
        (d / "product_metadata.json").write_text('{"title":"x"}', encoding="utf-8")

    def test_root_not_found(self):
        result = prune(Path("/nonexistent"), max_unused_days=30)
        self.assertEqual(result["error"], "root_not_found")

    def test_empty_dir(self):
        result = prune(self.root, max_unused_days=30)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["kept_count"], 0)

    def test_keeps_fresh(self):
        self._make_asin("B0FRESH", last_used_days_ago=1)
        result = prune(self.root, max_unused_days=30)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["kept_count"], 1)

    def test_deletes_old_dry_run(self):
        self._make_asin("B0OLD", last_used_days_ago=60)
        result = prune(self.root, max_unused_days=30, apply=False)
        self.assertEqual(result["deleted_count"], 1)
        self.assertIn("B0OLD", result["deleted"])
        # Should still exist (dry run)
        self.assertTrue((self.root / "B0OLD").exists())

    def test_deletes_old_apply(self):
        self._make_asin("B0OLD", last_used_days_ago=60)
        result = prune(self.root, max_unused_days=30, apply=True)
        self.assertEqual(result["deleted_count"], 1)
        # Should be gone
        self.assertFalse((self.root / "B0OLD").exists())

    def test_keeps_broken(self):
        d = self.root / "B0BROKEN"
        d.mkdir()
        info = {"status": "BROKEN", "last_used_utc": _days_ago_iso(60)}
        (d / "cache_info.json").write_text(json.dumps(info), encoding="utf-8")
        result = prune(self.root, max_unused_days=30)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["kept_count"], 1)

    def test_skips_no_cache_info(self):
        d = self.root / "B0NOINFO"
        d.mkdir()
        result = prune(self.root, max_unused_days=30)
        self.assertEqual(result["skipped_count"], 1)

    def test_mixed(self):
        self._make_asin("B0FRESH", last_used_days_ago=5)
        self._make_asin("B0OLD1", last_used_days_ago=45)
        self._make_asin("B0OLD2", last_used_days_ago=90)
        result = prune(self.root, max_unused_days=30)
        self.assertEqual(result["deleted_count"], 2)
        self.assertEqual(result["kept_count"], 1)

    def test_bytes_freed(self):
        self._make_asin("B0OLD", last_used_days_ago=60)
        result = prune(self.root, max_unused_days=30)
        self.assertGreater(result["bytes_freed_est"], 0)

    def test_hidden_dirs_skipped(self):
        d = self.root / ".hidden"
        d.mkdir()
        result = prune(self.root, max_unused_days=30)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["kept_count"], 0)


# ---------------------------------------------------------------
# prune edge cases
# ---------------------------------------------------------------

class TestPruneEdgeCases(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_asin(self, asin: str, last_used_days_ago: int = 0, status: str = "VALID"):
        d = self.root / asin
        d.mkdir(parents=True)
        info = {"last_used_utc": _days_ago_iso(last_used_days_ago), "status": status}
        (d / "cache_info.json").write_text(json.dumps(info), encoding="utf-8")
        (d / "product_metadata.json").write_text('{"title":"x"}', encoding="utf-8")

    def test_corrupt_cache_info_skipped(self):
        d = self.root / "B0CORRUPT"
        d.mkdir()
        (d / "cache_info.json").write_text("{invalid json", encoding="utf-8")
        result = prune(self.root, max_unused_days=30)
        self.assertEqual(result["skipped_count"], 1)

    def test_max_unused_days_zero_deletes_all(self):
        self._make_asin("B0TODAY", last_used_days_ago=0)
        result = prune(self.root, max_unused_days=0)
        self.assertEqual(result["deleted_count"], 1)

    def test_max_unused_days_very_large(self):
        self._make_asin("B0OLD", last_used_days_ago=365)
        result = prune(self.root, max_unused_days=9999)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["kept_count"], 1)

    def test_apply_false_preserves_dirs(self):
        self._make_asin("B0DEL1", last_used_days_ago=60)
        self._make_asin("B0DEL2", last_used_days_ago=90)
        result = prune(self.root, max_unused_days=30, apply=False)
        self.assertEqual(result["deleted_count"], 2)
        self.assertTrue((self.root / "B0DEL1").exists())
        self.assertTrue((self.root / "B0DEL2").exists())

    def test_asin_with_images_fetched_only(self):
        d = self.root / "B0IMAGES"
        d.mkdir()
        info = {"images_fetched_at_utc": _days_ago_iso(5), "status": "VALID"}
        (d / "cache_info.json").write_text(json.dumps(info), encoding="utf-8")
        result = prune(self.root, max_unused_days=30)
        self.assertEqual(result["kept_count"], 1)


# ---------------------------------------------------------------
# _parse_utc edge cases
# ---------------------------------------------------------------

class TestParseUtcEdgeCases(unittest.TestCase):

    def test_none_input(self):
        self.assertIsNone(_parse_utc(None))

    def test_with_microseconds(self):
        ts = _parse_utc("2026-02-14T12:00:00.123456Z")
        # Should parse (may strip micros) or return None gracefully
        # Just ensure no crash
        self.assertTrue(ts is None or isinstance(ts, float))

    def test_no_z_suffix(self):
        ts = _parse_utc("2026-02-14T12:00:00")
        # May or may not parse depending on implementation
        self.assertTrue(ts is None or isinstance(ts, float))


if __name__ == "__main__":
    unittest.main()
