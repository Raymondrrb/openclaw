#!/usr/bin/env python3
"""Tests for lib/fetch_cache.py — disk-backed URL fetch cache with TTL.

Run:
    python3 tools/test_fetch_cache.py
    python3 tools/test_fetch_cache.py --live   # includes real HTTP + cache tests
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from lib.fetch_cache import CacheEntry, FetchCache, _content_hash, _url_key
from lib.markdown_fetch import FetchResult, fetch_markdown

_RUN_LIVE = "--live" in sys.argv


class TestHelpers(unittest.TestCase):
    """Test cache helper functions."""

    def test_url_key_deterministic(self):
        k1 = _url_key("https://example.com/page")
        k2 = _url_key("https://example.com/page")
        self.assertEqual(k1, k2)

    def test_url_key_different_urls(self):
        k1 = _url_key("https://example.com/a")
        k2 = _url_key("https://example.com/b")
        self.assertNotEqual(k1, k2)

    def test_url_key_length(self):
        k = _url_key("https://example.com/very/long/path/to/something")
        self.assertEqual(len(k), 16)

    def test_content_hash_deterministic(self):
        h1 = _content_hash("hello world")
        h2 = _content_hash("hello world")
        self.assertEqual(h1, h2)

    def test_content_hash_changes(self):
        h1 = _content_hash("version 1")
        h2 = _content_hash("version 2")
        self.assertNotEqual(h1, h2)


class TestCacheEntry(unittest.TestCase):
    """Test CacheEntry properties."""

    def _make_entry(self, ttl_hours=24.0, age_minutes=0):
        from datetime import datetime, timezone, timedelta
        cached_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        return CacheEntry(
            url="https://example.com/test",
            url_key="abc123",
            content_hash="def456",
            method="markdown",
            content_type="text/markdown",
            token_estimate=100,
            content_length=500,
            fetched_at=cached_at.isoformat(),
            cached_at=cached_at.isoformat(),
            ttl_hours=ttl_hours,
            text_file="content/abc123.md",
        )

    def test_not_expired_fresh(self):
        entry = self._make_entry(ttl_hours=24.0, age_minutes=0)
        self.assertFalse(entry.is_expired)

    def test_expired(self):
        entry = self._make_entry(ttl_hours=1.0, age_minutes=120)  # 2 hours old, 1h TTL
        self.assertTrue(entry.is_expired)

    def test_age_hours(self):
        entry = self._make_entry(ttl_hours=24.0, age_minutes=60)
        self.assertAlmostEqual(entry.age_hours, 1.0, delta=0.05)


class TestFetchCache(unittest.TestCase):
    """Test FetchCache operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = FetchCache(cache_dir=self.tmpdir, ttl_hours=24.0)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_put_and_get(self):
        url = "https://example.com/review"
        text = "# Great Product\n\nThis is a detailed review with enough content."

        entry = self.cache.put(url, text, method="markdown", content_type="text/markdown")
        self.assertEqual(entry.url, url)
        self.assertEqual(entry.method, "markdown")

        # Get should return the entry
        got = self.cache.get(url)
        self.assertIsNotNone(got)
        self.assertEqual(got.url, url)
        self.assertEqual(got.method, "markdown")

    def test_get_text(self):
        url = "https://example.com/review"
        text = "# Great Product\n\nDetailed review content here."
        self.cache.put(url, text)

        cached_text = self.cache.get_text(url)
        self.assertEqual(cached_text, text)

    def test_cache_miss(self):
        self.assertIsNone(self.cache.get("https://example.com/not-cached"))

    def test_get_text_miss(self):
        self.assertIsNone(self.cache.get_text("https://example.com/not-cached"))

    def test_ttl_expiration(self):
        # Create cache with very short TTL
        cache = FetchCache(cache_dir=self.tmpdir, ttl_hours=0.0001)  # ~0.36 seconds
        url = "https://example.com/expires"
        cache.put(url, "This content will expire soon")

        # Should be present immediately
        self.assertIsNotNone(cache.get(url))

        # Wait for expiration
        time.sleep(0.5)
        self.assertIsNone(cache.get(url))

    def test_contains(self):
        url = "https://example.com/review"
        self.assertNotIn(url, self.cache)
        self.cache.put(url, "content")
        self.assertIn(url, self.cache)

    def test_len(self):
        self.assertEqual(len(self.cache), 0)
        self.cache.put("https://example.com/a", "content a")
        self.assertEqual(len(self.cache), 1)
        self.cache.put("https://example.com/b", "content b")
        self.assertEqual(len(self.cache), 2)

    def test_invalidate(self):
        url = "https://example.com/review"
        self.cache.put(url, "content")
        self.assertIn(url, self.cache)

        removed = self.cache.invalidate(url)
        self.assertTrue(removed)
        self.assertNotIn(url, self.cache)

        # Double invalidate returns False
        self.assertFalse(self.cache.invalidate(url))

    def test_invalidate_removes_file(self):
        url = "https://example.com/review"
        entry = self.cache.put(url, "content to delete")
        content_path = Path(self.tmpdir) / entry.text_file
        self.assertTrue(content_path.exists())

        self.cache.invalidate(url)
        self.assertFalse(content_path.exists())

    def test_has_changed(self):
        url = "https://example.com/review"
        self.cache.put(url, "version 1 of the content")

        # Same content = not changed
        self.assertFalse(self.cache.has_changed(url, "version 1 of the content"))

        # Different content = changed
        self.assertTrue(self.cache.has_changed(url, "version 2 of the content"))

        # Not cached = changed (needs fetch)
        self.assertTrue(self.cache.has_changed("https://other.com/new", "anything"))

    def test_evict_expired(self):
        cache = FetchCache(cache_dir=self.tmpdir, ttl_hours=0.0001)
        cache.put("https://example.com/a", "content a")
        cache.put("https://example.com/b", "content b")
        time.sleep(0.5)

        # Add a fresh entry
        cache_fresh = FetchCache(cache_dir=self.tmpdir, ttl_hours=24.0)
        cache_fresh.put("https://example.com/c", "content c")

        # Reload and evict
        cache2 = FetchCache(cache_dir=self.tmpdir, ttl_hours=24.0)
        evicted = cache2.evict_expired()
        self.assertEqual(evicted, 2)
        self.assertEqual(len(cache2), 1)
        self.assertIn("https://example.com/c", cache2)

    def test_clear(self):
        self.cache.put("https://example.com/a", "content a")
        self.cache.put("https://example.com/b", "content b")
        self.assertEqual(len(self.cache), 2)

        cleared = self.cache.clear()
        self.assertEqual(cleared, 2)
        self.assertEqual(len(self.cache), 0)

    def test_stats(self):
        self.cache.put("https://example.com/a", "content a")
        self.cache.put("https://example.com/b", "content b")

        s = self.cache.stats()
        self.assertEqual(s["total_entries"], 2)
        self.assertEqual(s["active_entries"], 2)
        self.assertEqual(s["expired_entries"], 0)
        self.assertGreater(s["total_bytes"], 0)

    def test_put_result(self):
        result = FetchResult(
            url="https://example.com/test",
            text="# Markdown content\n\nWith enough text to be meaningful.",
            method="markdown",
            content_type="text/markdown",
            token_estimate=50,
            fetched_at="2026-02-14T00:00:00Z",
        )
        entry = self.cache.put_result(result)
        self.assertEqual(entry.method, "markdown")
        self.assertEqual(entry.token_estimate, 50)

        # Verify retrievable
        cached = self.cache.get_text("https://example.com/test")
        self.assertEqual(cached, result.text)

    def test_update_overwrites(self):
        url = "https://example.com/review"
        self.cache.put(url, "version 1")
        self.cache.put(url, "version 2")

        text = self.cache.get_text(url)
        self.assertEqual(text, "version 2")
        self.assertEqual(len(self.cache), 1)

    def test_persistence_across_instances(self):
        url = "https://example.com/review"
        self.cache.put(url, "persistent content", method="markdown")

        # Create new cache instance pointing to same dir
        cache2 = FetchCache(cache_dir=self.tmpdir, ttl_hours=24.0)
        entry = cache2.get(url)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.method, "markdown")
        self.assertEqual(cache2.get_text(url), "persistent content")

    def test_stale_index_entry_cleaned(self):
        """If content file is missing but index has entry, get() cleans up."""
        url = "https://example.com/review"
        entry = self.cache.put(url, "content")

        # Delete the content file directly
        content_path = Path(self.tmpdir) / entry.text_file
        content_path.unlink()

        # get() should detect and clean up
        got = self.cache.get(url)
        self.assertIsNone(got)
        self.assertEqual(len(self.cache), 0)

    def test_custom_ttl_per_entry(self):
        url = "https://example.com/review"
        self.cache.put(url, "content", ttl_hours=0.0001)

        # Fresh — should be present
        self.assertIsNotNone(self.cache.get(url))

        time.sleep(0.5)
        # Expired — should be gone
        self.assertIsNone(self.cache.get(url))


class TestCacheIntegrationWithFetch(unittest.TestCase):
    """Test cache integration with fetch_markdown()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = FetchCache(cache_dir=self.tmpdir, ttl_hours=24.0)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _mock_urlopen(self, body: bytes, headers: dict):
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.headers = MagicMock()
        mock_resp.headers.items.return_value = list(headers.items())
        mock_resp.headers.get.side_effect = lambda k, d="": headers.get(k, d)
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        return mock_resp

    def _long_md_body(self) -> bytes:
        return (
            b"# Product Review\n\n"
            b"This is a detailed review of an excellent product. It offers outstanding "
            b"build quality, reliable long-term performance, and a comfortable ergonomic "
            b"design that makes it perfect for daily use over extended periods. The battery "
            b"life exceeds all expectations and the price point is very competitive in its "
            b"market segment compared to all alternatives tested."
        )

    def _long_html_body(self) -> bytes:
        return (
            b"<html><body><h1>Product Review</h1>"
            b"<p>This is a detailed review of an excellent product. It offers outstanding "
            b"build quality, reliable long-term performance, and a comfortable ergonomic "
            b"design that makes it perfect for daily use over extended periods.</p>"
            b"<p>The battery life exceeds all expectations and the price point is very "
            b"competitive in its market segment compared to all alternatives tested.</p>"
            b"</body></html>"
        )

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_first_fetch_populates_cache(self, mock_urlopen):
        headers = {"content-type": "text/markdown", "x-markdown-tokens": "80"}
        mock_urlopen.return_value = self._mock_urlopen(self._long_md_body(), headers)

        result = fetch_markdown("https://example.com/review", cache=self.cache)
        self.assertTrue(result.ok)
        self.assertEqual(result.method, "markdown")

        # Cache should now have the entry
        self.assertIn("https://example.com/review", self.cache)
        self.assertEqual(len(self.cache), 1)

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_second_fetch_uses_cache(self, mock_urlopen):
        headers = {"content-type": "text/markdown", "x-markdown-tokens": "80"}
        mock_urlopen.return_value = self._mock_urlopen(self._long_md_body(), headers)

        # First fetch — hits HTTP
        r1 = fetch_markdown("https://example.com/review", cache=self.cache)
        self.assertEqual(r1.method, "markdown")
        self.assertEqual(mock_urlopen.call_count, 1)

        # Second fetch — should use cache (no HTTP)
        r2 = fetch_markdown("https://example.com/review", cache=self.cache)
        self.assertEqual(r2.method, "cached:markdown")
        self.assertEqual(mock_urlopen.call_count, 1)  # still 1 — no new HTTP call
        self.assertEqual(r2.text, r1.text)

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_expired_cache_refetches(self, mock_urlopen):
        headers = {"content-type": "text/markdown"}
        mock_urlopen.return_value = self._mock_urlopen(self._long_md_body(), headers)

        # Use very short TTL
        cache = FetchCache(cache_dir=self.tmpdir, ttl_hours=0.0001)

        # First fetch
        r1 = fetch_markdown("https://example.com/review", cache=cache)
        self.assertEqual(r1.method, "markdown")
        self.assertEqual(mock_urlopen.call_count, 1)

        # Wait for expiration
        time.sleep(0.5)

        # Second fetch — cache expired, should re-fetch
        r2 = fetch_markdown("https://example.com/review", cache=cache)
        self.assertEqual(r2.method, "markdown")  # fresh fetch, not "cached:*"
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_cache_with_html_fallback(self, mock_urlopen):
        headers = {"content-type": "text/html; charset=utf-8"}
        mock_urlopen.return_value = self._mock_urlopen(self._long_html_body(), headers)

        r1 = fetch_markdown("https://example.com/html-page", cache=self.cache)
        self.assertEqual(r1.method, "html")
        self.assertEqual(mock_urlopen.call_count, 1)

        # Second fetch — cache hit
        r2 = fetch_markdown("https://example.com/html-page", cache=self.cache)
        self.assertEqual(r2.method, "cached:html")
        self.assertEqual(mock_urlopen.call_count, 1)


class TestLiveCacheIntegration(unittest.TestCase):
    """Live tests with real HTTP + cache."""

    def test_real_fetch_then_cache(self):
        if not _RUN_LIVE:
            self.skipTest("Live tests disabled (use --live)")

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FetchCache(cache_dir=tmpdir, ttl_hours=1.0)

            # First fetch — real HTTP
            t0 = time.monotonic()
            r1 = fetch_markdown(
                "https://blog.cloudflare.com/markdown-for-ai-agents/",
                cache=cache,
            )
            t1 = time.monotonic()
            self.assertTrue(r1.ok)
            http_time = t1 - t0

            # Second fetch — should be instant from cache
            t2 = time.monotonic()
            r2 = fetch_markdown(
                "https://blog.cloudflare.com/markdown-for-ai-agents/",
                cache=cache,
            )
            t3 = time.monotonic()
            cache_time = t3 - t2

            self.assertTrue(r2.ok)
            self.assertTrue(r2.method.startswith("cached:"))
            self.assertEqual(r2.text, r1.text)

            print(f"\n  [LIVE CACHE] HTTP: {http_time:.3f}s, Cache: {cache_time:.3f}s "
                  f"({http_time / max(cache_time, 0.0001):.0f}x faster)")
            print(f"  [LIVE CACHE] Stats: {json.dumps(cache.stats(), indent=2)}")


if __name__ == "__main__":
    if "--live" in sys.argv:
        sys.argv.remove("--live")
    unittest.main(verbosity=2)
