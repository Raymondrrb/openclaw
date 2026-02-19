#!/usr/bin/env python3
"""Tests for rayvault/truth_cache.py — ASIN-keyed product asset cache."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from rayvault.truth_cache import (
    CACHE_BROKEN,
    CACHE_EXPIRED,
    CACHE_VALID,
    CachePolicy,
    TruthCache,
    du_bytes,
    sha1_file,
    sha256_bytes,
    sha256_json,
    utc_now_iso,
)


# ---------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------

class TestUtcNowIso(unittest.TestCase):

    def test_returns_string(self):
        self.assertIsInstance(utc_now_iso(), str)

    def test_ends_with_z(self):
        self.assertTrue(utc_now_iso().endswith("Z"))


class TestSha1File(unittest.TestCase):

    def test_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"hello world")
            p = Path(f.name)
        try:
            h1 = sha1_file(p)
            h2 = sha1_file(p)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 40)
        finally:
            p.unlink()

    def test_different_content(self):
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(b"aaa")
            p1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b"bbb")
            p2 = Path(f2.name)
        try:
            self.assertNotEqual(sha1_file(p1), sha1_file(p2))
        finally:
            p1.unlink()
            p2.unlink()


class TestSha256Bytes(unittest.TestCase):

    def test_deterministic(self):
        self.assertEqual(sha256_bytes(b"hello"), sha256_bytes(b"hello"))

    def test_hex_length(self):
        self.assertEqual(len(sha256_bytes(b"x")), 64)


class TestSha256Json(unittest.TestCase):

    def test_deterministic(self):
        self.assertEqual(sha256_json({"a": 1}), sha256_json({"a": 1}))

    def test_key_order_independent(self):
        self.assertEqual(sha256_json({"a": 1, "b": 2}), sha256_json({"b": 2, "a": 1}))

    def test_different_data(self):
        self.assertNotEqual(sha256_json({"a": 1}), sha256_json({"a": 2}))


class TestDuBytes(unittest.TestCase):

    def test_nonexistent(self):
        self.assertEqual(du_bytes(Path("/nonexistent")), 0)

    def test_single_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello")
            p = Path(f.name)
        try:
            self.assertEqual(du_bytes(p), 5)
        finally:
            p.unlink()

    def test_directory(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_bytes(b"hello")
            (Path(d) / "b.txt").write_bytes(b"world")
            self.assertEqual(du_bytes(Path(d)), 10)


# ---------------------------------------------------------------
# CachePolicy
# ---------------------------------------------------------------

class TestCachePolicy(unittest.TestCase):

    def test_defaults(self):
        p = CachePolicy()
        self.assertEqual(p.ttl_meta_sec, 48 * 3600)
        self.assertEqual(p.max_gallery, 6)
        self.assertEqual(p.copy_mode, "copy")

    def test_custom(self):
        p = CachePolicy(ttl_meta_sec=100, max_gallery=3)
        self.assertEqual(p.ttl_meta_sec, 100)
        self.assertEqual(p.max_gallery, 3)


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestCacheConstants(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(CACHE_VALID, "VALID")

    def test_expired(self):
        self.assertEqual(CACHE_EXPIRED, "EXPIRED")

    def test_broken(self):
        self.assertEqual(CACHE_BROKEN, "BROKEN")


# ---------------------------------------------------------------
# TruthCache — paths
# ---------------------------------------------------------------

class TestTruthCachePaths(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_asin_dir(self):
        d = self.cache.asin_dir("B0TEST")
        self.assertTrue(str(d).endswith("products/B0TEST"))

    def test_cache_info_path(self):
        p = self.cache.cache_info_path("B0TEST")
        self.assertEqual(p.name, "cache_info.json")

    def test_meta_path(self):
        p = self.cache.meta_path("B0TEST")
        self.assertEqual(p.name, "product_metadata.json")

    def test_images_dir(self):
        p = self.cache.images_dir("B0TEST")
        self.assertEqual(p.name, "source_images")


# ---------------------------------------------------------------
# TruthCache — get_cached
# ---------------------------------------------------------------

class TestTruthCacheGetCached(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_miss(self):
        self.assertEqual(self.cache.get_cached("B0MISSING"), {})

    def test_with_meta(self):
        asin = "B0TEST"
        d = self.cache.asin_dir(asin)
        d.mkdir(parents=True)
        meta = {"title": "Test Product", "price": "29.99"}
        self.cache.cache_info_path(asin).write_text(
            json.dumps({"status": "VALID"}), encoding="utf-8"
        )
        self.cache.meta_path(asin).write_text(
            json.dumps(meta), encoding="utf-8"
        )
        result = self.cache.get_cached(asin)
        self.assertEqual(result["meta"]["title"], "Test Product")

    def test_broken_skips_meta(self):
        asin = "B0BROKEN"
        d = self.cache.asin_dir(asin)
        d.mkdir(parents=True)
        self.cache.cache_info_path(asin).write_text(
            json.dumps({"status": "BROKEN"}), encoding="utf-8"
        )
        self.cache.meta_path(asin).write_text(
            json.dumps({"title": "X"}), encoding="utf-8"
        )
        result = self.cache.get_cached(asin)
        self.assertNotIn("meta", result)


# ---------------------------------------------------------------
# TruthCache — put_from_fetch
# ---------------------------------------------------------------

class TestTruthCachePutFromFetch(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))
        self.img_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        shutil.rmtree(str(self.img_dir), ignore_errors=True)

    def test_store_meta_and_images(self):
        asin = "B0PUT"
        img = self.img_dir / "01_main.jpg"
        img.write_bytes(b"\xff\xd8test")
        meta = {"title": "New Product"}
        result = self.cache.put_from_fetch(asin, meta, [img])
        self.assertTrue(result["ok"])
        self.assertIn("01_main.jpg", result["stored_images"])
        # Verify on disk
        cached = self.cache.get_cached(asin)
        self.assertEqual(cached["meta"]["title"], "New Product")
        self.assertTrue(len(cached["images"]) > 0)

    def test_store_clears_broken_state(self):
        asin = "B0FIX"
        self.cache.asin_dir(asin).mkdir(parents=True)
        self.cache.mark_cache_broken(asin, "test_reason")
        # Verify broken
        info = json.loads(self.cache.cache_info_path(asin).read_text())
        self.assertEqual(info["status"], "BROKEN")
        # Put new data
        self.cache.put_from_fetch(asin, {"title": "Fixed"}, [])
        info = json.loads(self.cache.cache_info_path(asin).read_text())
        self.assertEqual(info["status"], "VALID")
        self.assertNotIn("broken_reason", info)

    def test_http_status_recorded(self):
        asin = "B0HTTP"
        self.cache.put_from_fetch(asin, {"title": "X"}, [], http_status=200)
        info = json.loads(self.cache.cache_info_path(asin).read_text())
        self.assertEqual(info["http_status_last"], 200)


# ---------------------------------------------------------------
# TruthCache — mark_cache_broken
# ---------------------------------------------------------------

class TestTruthCacheMarkBroken(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_marks_broken(self):
        asin = "B0BREAK"
        self.cache.asin_dir(asin).mkdir(parents=True)
        self.cache.mark_cache_broken(asin, "sha mismatch")
        info = json.loads(self.cache.cache_info_path(asin).read_text())
        self.assertEqual(info["status"], "BROKEN")
        self.assertEqual(info["broken_reason"], "sha mismatch")
        self.assertIn("broken_at_utc", info)


# ---------------------------------------------------------------
# TruthCache — verify_integrity
# ---------------------------------------------------------------

class TestTruthCacheVerifyIntegrity(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_missing_asin(self):
        result = self.cache.verify_integrity("B0MISSING")
        self.assertFalse(result["ok"])
        self.assertIn("asin_dir_missing", result["issues"])

    def test_valid_complete(self):
        asin = "B0VALID"
        meta = {"title": "Test"}
        imgs = Path(tempfile.mkdtemp())
        (imgs / "01_main.jpg").write_bytes(b"img")
        self.cache.put_from_fetch(asin, meta, [imgs / "01_main.jpg"])
        result = self.cache.verify_integrity(asin)
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])
        import shutil
        shutil.rmtree(str(imgs), ignore_errors=True)

    def test_broken_reports(self):
        asin = "B0BRK"
        self.cache.asin_dir(asin).mkdir(parents=True)
        self.cache.mark_cache_broken(asin, "test")
        result = self.cache.verify_integrity(asin)
        self.assertFalse(result["ok"])
        self.assertTrue(any("marked_broken" in i for i in result["issues"]))


# ---------------------------------------------------------------
# TruthCache — needs_refresh
# ---------------------------------------------------------------

class TestTruthCacheNeedsRefresh(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir), CachePolicy(ttl_meta_sec=3600))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_fresh_data(self):
        asin = "B0FRESH"
        meta = {"title": "Test"}
        imgs = Path(tempfile.mkdtemp())
        (imgs / "01_main.jpg").write_bytes(b"img")
        self.cache.put_from_fetch(asin, meta, [imgs / "01_main.jpg"])
        result = self.cache.needs_refresh(asin)
        self.assertEqual(result["status"], CACHE_VALID)
        self.assertFalse(result["refresh_meta"])
        self.assertFalse(result["refresh_images"])
        import shutil
        shutil.rmtree(str(imgs), ignore_errors=True)


# ---------------------------------------------------------------
# TruthCache — has_main_image
# ---------------------------------------------------------------

class TestTruthCacheHasMainImage(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_no_images_dir(self):
        self.assertFalse(self.cache.has_main_image("B0NOPE"))

    def test_has_main(self):
        asin = "B0MAIN"
        imgs = self.cache.images_dir(asin)
        imgs.mkdir(parents=True)
        (imgs / "01_main.jpg").write_bytes(b"img")
        self.assertTrue(self.cache.has_main_image(asin))

    def test_only_alt(self):
        asin = "B0ALT"
        imgs = self.cache.images_dir(asin)
        imgs.mkdir(parents=True)
        (imgs / "02_alt.jpg").write_bytes(b"img")
        self.assertFalse(self.cache.has_main_image(asin))


# ---------------------------------------------------------------
# TruthCache — materialize_to_run
# ---------------------------------------------------------------

class TestTruthCacheMaterialize(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))
        self.run_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        shutil.rmtree(str(self.run_dir), ignore_errors=True)

    def test_cache_miss(self):
        result = self.cache.materialize_to_run("B0MISS", self.run_dir / "p01")
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "CACHE_MISS")

    def test_copy_mode(self):
        asin = "B0MAT"
        imgs = Path(tempfile.mkdtemp())
        (imgs / "01_main.jpg").write_bytes(b"imgdata")
        self.cache.put_from_fetch(asin, {"title": "X"}, [imgs / "01_main.jpg"])
        dest = self.run_dir / "p01"
        result = self.cache.materialize_to_run(asin, dest)
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "MATERIALIZED")
        self.assertEqual(result["mode"], "copy")
        self.assertTrue((dest / "source_images" / "01_main.jpg").exists())
        self.assertTrue((dest / "product_metadata.json").exists())
        import shutil
        shutil.rmtree(str(imgs), ignore_errors=True)


# ---------------------------------------------------------------
# TruthCache — b-roll
# ---------------------------------------------------------------

class TestTruthCacheBroll(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_no_broll(self):
        self.assertFalse(self.cache.has_approved_broll("B0NOPE"))

    def test_promote_broll(self):
        asin = "B0BROLL"
        src = Path(tempfile.mkdtemp()) / "approved.mp4"
        src.write_bytes(b"\x00" * 100)
        self.assertTrue(self.cache.promote_broll(asin, src))
        self.assertTrue(self.cache.has_approved_broll(asin))
        import shutil
        shutil.rmtree(str(src.parent), ignore_errors=True)

    def test_promote_nonexistent(self):
        self.assertFalse(self.cache.promote_broll("X", Path("/nope.mp4")))


# ---------------------------------------------------------------
# TruthCache — stats
# ---------------------------------------------------------------

class TestTruthCacheStats(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = TruthCache(Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty(self):
        s = self.cache.stats()
        self.assertEqual(s["total_asins"], 0)

    def test_with_data(self):
        self.cache.put_from_fetch("B0A", {"title": "A"}, [])
        self.cache.put_from_fetch("B0B", {"title": "B"}, [])
        s = self.cache.stats()
        self.assertEqual(s["total_asins"], 2)
        self.assertIn("total_mb", s)


if __name__ == "__main__":
    unittest.main()
