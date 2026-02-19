#!/usr/bin/env python3
"""Tests for rayvault/affiliate_resolver.py — ASIN to short link mapping."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rayvault.affiliate_resolver import AffiliateResolver
from rayvault.io import sha1_text


# ---------------------------------------------------------------
# sha1_text (now in rayvault.io, used by affiliate_resolver)
# ---------------------------------------------------------------

class TestSha1Text(unittest.TestCase):

    def test_returns_hex(self):
        h = sha1_text("hello")
        self.assertEqual(len(h), 40)
        int(h, 16)

    def test_deterministic(self):
        self.assertEqual(sha1_text("test"), sha1_text("test"))

    def test_different_inputs(self):
        self.assertNotEqual(sha1_text("a"), sha1_text("b"))


# ---------------------------------------------------------------
# AffiliateResolver — missing file
# ---------------------------------------------------------------

class TestResolverMissingFile(unittest.TestCase):

    def test_missing_file_loads_empty(self):
        r = AffiliateResolver(Path("/nonexistent/affiliates.json"))
        self.assertEqual(r.data.get("version"), "0")
        self.assertEqual(r.data.get("items"), {})

    def test_missing_file_resolve_returns_none(self):
        r = AffiliateResolver(Path("/nonexistent/affiliates.json"))
        self.assertIsNone(r.resolve("B0ABC12345"))

    def test_missing_file_stats(self):
        r = AffiliateResolver(Path("/nonexistent/affiliates.json"))
        s = r.stats()
        self.assertFalse(s["file_exists"])
        self.assertIsNone(s["file_hash"])
        self.assertEqual(s["total_mappings"], 0)


# ---------------------------------------------------------------
# AffiliateResolver — with data
# ---------------------------------------------------------------

class TestResolverWithData(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.aff_path = Path(self.tmpdir) / "affiliates.json"
        data = {
            "version": "1",
            "updated_at_utc": "2026-02-14T00:00:00Z",
            "default": {"tag": "rayviews-20", "country": "US"},
            "items": {
                "B0ABC12345": {
                    "short_link": "https://amzn.to/abcdef",
                    "source": "manual",
                    "last_verified_utc": "2026-02-14T00:00:00Z",
                },
                "B0XYZ67890": {
                    "short_link": "https://amzn.to/xyz123",
                    "source": "api",
                    "last_verified_utc": "2026-02-13T00:00:00Z",
                },
                "B0BADLINK1": {
                    "short_link": "not-a-url",
                    "source": "manual",
                },
                "B0NOLINK00": {
                    "short_link": "",
                    "source": "pending",
                },
            },
        }
        self.aff_path.write_text(json.dumps(data), encoding="utf-8")
        self.resolver = AffiliateResolver(self.aff_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_resolve_known_asin(self):
        info = self.resolver.resolve("B0ABC12345")
        self.assertIsNotNone(info)
        self.assertEqual(info["short_link"], "https://amzn.to/abcdef")
        self.assertEqual(info["source"], "manual")
        self.assertEqual(info["asin"], "B0ABC12345")

    def test_resolve_second_asin(self):
        info = self.resolver.resolve("B0XYZ67890")
        self.assertIsNotNone(info)
        self.assertEqual(info["short_link"], "https://amzn.to/xyz123")

    def test_resolve_unknown_asin(self):
        self.assertIsNone(self.resolver.resolve("B0UNKNOWN0"))

    def test_resolve_empty_string(self):
        self.assertIsNone(self.resolver.resolve(""))

    def test_resolve_none_string(self):
        self.assertIsNone(self.resolver.resolve(None))

    def test_resolve_case_insensitive(self):
        info = self.resolver.resolve("b0abc12345")
        self.assertIsNotNone(info)
        self.assertEqual(info["asin"], "B0ABC12345")

    def test_resolve_strips_whitespace(self):
        info = self.resolver.resolve("  B0ABC12345  ")
        self.assertIsNotNone(info)

    def test_resolve_invalid_url_returns_none(self):
        """short_link must start with http."""
        self.assertIsNone(self.resolver.resolve("B0BADLINK1"))

    def test_resolve_empty_link_returns_none(self):
        self.assertIsNone(self.resolver.resolve("B0NOLINK00"))

    def test_provenance_fields(self):
        info = self.resolver.resolve("B0ABC12345")
        self.assertIn("affiliates_file_hash", info)
        self.assertIn("resolver_loaded_at_utc", info)
        self.assertIsNotNone(info["affiliates_file_hash"])
        self.assertIsNotNone(info["last_verified_utc"])

    def test_resolve_batch(self):
        results = self.resolver.resolve_batch(["B0ABC12345", "B0UNKNOWN0", "B0XYZ67890"])
        self.assertIsNotNone(results["B0ABC12345"])
        self.assertIsNone(results["B0UNKNOWN0"])
        self.assertIsNotNone(results["B0XYZ67890"])

    def test_resolve_batch_empty(self):
        results = self.resolver.resolve_batch([])
        self.assertEqual(results, {})

    def test_stats(self):
        s = self.resolver.stats()
        self.assertTrue(s["file_exists"])
        self.assertIsNotNone(s["file_hash"])
        self.assertEqual(s["total_mappings"], 4)
        self.assertEqual(s["version"], "1")

    def test_reload(self):
        # Modify file
        new_data = {"version": "2", "items": {"B0NEW00001": {
            "short_link": "https://amzn.to/new", "source": "api"
        }}}
        self.aff_path.write_text(json.dumps(new_data), encoding="utf-8")
        self.resolver.reload()
        self.assertIsNotNone(self.resolver.resolve("B0NEW00001"))
        self.assertIsNone(self.resolver.resolve("B0ABC12345"))
        self.assertEqual(self.resolver.stats()["version"], "2")


# ---------------------------------------------------------------
# AffiliateResolver — edge cases
# ---------------------------------------------------------------

class TestResolverEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.aff_path = Path(self.tmpdir) / "affiliates.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, data):
        self.aff_path.write_text(json.dumps(data), encoding="utf-8")
        return AffiliateResolver(self.aff_path)

    def test_corrupt_json_loads_empty(self):
        self.aff_path.write_text("{invalid json}", encoding="utf-8")
        r = AffiliateResolver(self.aff_path)
        self.assertIsNone(r.resolve("B0ANY"))

    def test_empty_items_dict(self):
        r = self._write({"version": "1", "items": {}})
        self.assertIsNone(r.resolve("B0ANY"))
        self.assertEqual(r.stats()["total_mappings"], 0)

    def test_resolve_batch_with_duplicates(self):
        r = self._write({
            "version": "1",
            "items": {"B0AAA": {"short_link": "https://amzn.to/aaa", "source": "api"}},
        })
        results = r.resolve_batch(["B0AAA", "B0AAA", "B0AAA"])
        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results["B0AAA"])

    def test_resolve_batch_all_unknown(self):
        r = self._write({"version": "1", "items": {}})
        results = r.resolve_batch(["B0X", "B0Y", "B0Z"])
        self.assertEqual(len(results), 3)
        for v in results.values():
            self.assertIsNone(v)

    def test_stats_file_hash_changes_on_reload(self):
        r = self._write({"version": "1", "items": {"B0A": {"short_link": "https://amzn.to/a", "source": "m"}}})
        hash1 = r.stats()["file_hash"]
        self.aff_path.write_text(json.dumps({"version": "2", "items": {}}), encoding="utf-8")
        r.reload()
        hash2 = r.stats()["file_hash"]
        self.assertNotEqual(hash1, hash2)

    def test_resolve_asin_with_special_chars(self):
        r = self._write({"version": "1", "items": {}})
        self.assertIsNone(r.resolve("B0-SPECIAL/CHARS"))

    def test_large_items_dict(self):
        items = {f"B0{i:08d}": {"short_link": f"https://amzn.to/{i}", "source": "api"} for i in range(100)}
        r = self._write({"version": "1", "items": items})
        self.assertEqual(r.stats()["total_mappings"], 100)
        self.assertIsNotNone(r.resolve("B000000050"))


if __name__ == "__main__":
    unittest.main()
