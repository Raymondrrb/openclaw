#!/usr/bin/env python3
"""Tests for lib/markdown_fetch.py — Cloudflare "Markdown for Agents" support.

Tests both mocked (unit) and live (integration) scenarios.
Run:
    python tools/test_markdown_fetch.py
    python tools/test_markdown_fetch.py --live   # includes real HTTP tests
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from lib.markdown_fetch import (
    FetchResult,
    _decode_body,
    _is_markdown_response,
    _parse_token_hint,
    _persist_artifact,
    _url_to_slug,
    fetch_markdown,
)

_RUN_LIVE = "--live" in sys.argv


class TestHelpers(unittest.TestCase):
    """Unit tests for internal helper functions."""

    def test_is_markdown_response_true(self):
        self.assertTrue(_is_markdown_response({"content-type": "text/markdown; charset=utf-8"}))
        self.assertTrue(_is_markdown_response({"content-type": "text/markdown"}))
        self.assertTrue(_is_markdown_response({"content-type": "text/x-markdown"}))

    def test_is_markdown_response_false(self):
        self.assertFalse(_is_markdown_response({"content-type": "text/html; charset=utf-8"}))
        self.assertFalse(_is_markdown_response({"content-type": "application/json"}))
        self.assertFalse(_is_markdown_response({}))

    def test_parse_token_hint(self):
        self.assertEqual(_parse_token_hint({"x-markdown-tokens": "1500"}), 1500)
        self.assertEqual(_parse_token_hint({"x-markdown-tokens": "0"}), 0)
        self.assertIsNone(_parse_token_hint({}))
        self.assertIsNone(_parse_token_hint({"x-markdown-tokens": ""}))
        self.assertIsNone(_parse_token_hint({"x-markdown-tokens": "abc"}))

    def test_decode_body_utf8(self):
        headers = {"content-type": "text/markdown; charset=utf-8"}
        self.assertEqual(_decode_body(b"hello world", headers), "hello world")

    def test_decode_body_latin1(self):
        headers = {"content-type": "text/html; charset=iso-8859-1"}
        body = "caf\xe9".encode("iso-8859-1")
        self.assertEqual(_decode_body(body, headers), "caf\xe9")

    def test_decode_body_default_utf8(self):
        headers = {"content-type": "text/markdown"}
        self.assertEqual(_decode_body("test \u2603".encode("utf-8"), headers), "test \u2603")

    def test_url_to_slug(self):
        self.assertEqual(_url_to_slug("https://www.example.com/path/to/page"), "example_com_path_to_page")
        self.assertEqual(_url_to_slug("https://rtings.com/headphones/reviews/best"), "rtings_com_headphones_reviews_best")
        # Long slugs get truncated
        long_url = "https://example.com/" + "a" * 200
        self.assertLessEqual(len(_url_to_slug(long_url)), 80)

    def test_url_to_slug_special_chars(self):
        slug = _url_to_slug("https://example.com/page?q=hello&lang=en#section")
        self.assertNotIn("?", slug)
        self.assertNotIn("&", slug)
        self.assertNotIn("#", slug)


class TestPersistence(unittest.TestCase):
    """Test artifact persistence."""

    def test_persist_creates_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = FetchResult(
                url="https://example.com/test-page",
                text="# Test Page\n\nThis is test content.",
                method="markdown",
                content_type="text/markdown",
                token_estimate=50,
                content_length=35,
                fetched_at="2026-02-13T00:00:00Z",
            )
            md_path = _persist_artifact(result, tmpdir)

            # Check .md file
            self.assertTrue(md_path.exists())
            self.assertEqual(md_path.read_text(), "# Test Page\n\nThis is test content.")

            # Check .json metadata
            json_path = md_path.with_suffix(".json")
            self.assertTrue(json_path.exists())
            meta = json.loads(json_path.read_text())
            self.assertEqual(meta["url"], "https://example.com/test-page")
            self.assertEqual(meta["method"], "markdown")
            self.assertEqual(meta["token_estimate"], 50)
            self.assertEqual(meta["content_type"], "text/markdown")

            # Check artifact_path was set
            self.assertEqual(result.artifact_path, str(md_path))


class TestFetchMarkdownMocked(unittest.TestCase):
    """Test fetch_markdown with mocked HTTP responses."""

    def _mock_urlopen(self, body: bytes, headers: dict, status: int = 200):
        """Create a mock for urllib.request.urlopen."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.headers = MagicMock()
        mock_resp.headers.items.return_value = list(headers.items())
        mock_resp.headers.get.side_effect = lambda k, d="": headers.get(k, d)
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        return mock_resp

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_markdown_response(self, mock_urlopen):
        """Server returns text/markdown — should use it directly."""
        body = (
            b"# Product Review\n\n"
            b"This is a great product with many features. It offers excellent build quality, "
            b"reliable performance, and a comfortable design that makes it perfect for daily use. "
            b"The battery life exceeds expectations and the price point is competitive in its segment."
        )
        headers = {
            "content-type": "text/markdown; charset=utf-8",
            "x-markdown-tokens": "120",
            "vary": "Accept",
        }
        mock_urlopen.return_value = self._mock_urlopen(body, headers)

        result = fetch_markdown("https://example.com/review")

        self.assertTrue(result.ok)
        self.assertEqual(result.method, "markdown")
        self.assertEqual(result.token_estimate, 120)
        self.assertIn("Product Review", result.text)

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_html_fallback(self, mock_urlopen):
        """Server returns text/html — should convert locally."""
        body = (
            b"<html><body><h1>Product Review</h1>"
            b"<p>This is a great product with many features and details about quality. "
            b"It offers excellent build quality, reliable performance, and a comfortable design.</p>"
            b"<p>The battery life exceeds expectations and the price point is competitive in its segment. "
            b"More content here for the review to ensure enough text is extracted.</p>"
            b"</body></html>"
        )
        headers = {"content-type": "text/html; charset=utf-8"}
        mock_urlopen.return_value = self._mock_urlopen(body, headers)

        result = fetch_markdown("https://example.com/review")

        self.assertTrue(result.ok)
        self.assertEqual(result.method, "html")
        self.assertIsNone(result.token_estimate)
        self.assertIn("Product Review", result.text)

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_too_short_content_fails(self, mock_urlopen):
        """Content shorter than min_content_len — should fail."""
        body = b"# Short"
        headers = {"content-type": "text/markdown"}
        mock_urlopen.return_value = self._mock_urlopen(body, headers)

        result = fetch_markdown("https://example.com/short", min_content_len=200)

        self.assertFalse(result.ok)
        self.assertEqual(result.method, "failed")

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_persist_on_success(self, mock_urlopen):
        """Successful fetch with persist_to should write artifacts."""
        body = b"# Review\n\nDetailed product review content that is long enough to pass the minimum content length check for our tests."
        headers = {
            "content-type": "text/markdown",
            "x-markdown-tokens": "200",
        }
        mock_urlopen.return_value = self._mock_urlopen(body, headers)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_markdown(
                "https://example.com/review",
                persist_to=tmpdir,
                min_content_len=50,
            )
            self.assertTrue(result.ok)
            self.assertIsNotNone(result.artifact_path)
            self.assertTrue(Path(result.artifact_path).exists())

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        """HTTP error should return failed result."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com", 403, "Forbidden", {}, None
        )
        result = fetch_markdown("https://example.com/blocked")
        self.assertFalse(result.ok)
        self.assertEqual(result.method, "failed")
        self.assertIn("403", result.error)

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        """Network error should return failed result."""
        mock_urlopen.side_effect = ConnectionError("Connection refused")
        result = fetch_markdown("https://example.com/down")
        self.assertFalse(result.ok)
        self.assertEqual(result.method, "failed")

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_accept_header_sent(self, mock_urlopen):
        """Verify the Accept header includes text/markdown."""
        body = b"# Content\n\nEnough content here to pass minimum length checks for the test."
        headers = {"content-type": "text/markdown"}
        mock_urlopen.return_value = self._mock_urlopen(body, headers)

        fetch_markdown("https://example.com/test", min_content_len=20)

        # Check that Request was created with markdown Accept header
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        accept = request_obj.get_header("Accept")
        self.assertIn("text/markdown", accept)
        self.assertIn("text/html", accept)


class TestFetchResult(unittest.TestCase):
    """Test FetchResult dataclass."""

    def test_ok_property(self):
        self.assertTrue(FetchResult(url="u", text="content", method="markdown").ok)
        self.assertTrue(FetchResult(url="u", text="content", method="html").ok)
        self.assertFalse(FetchResult(url="u", text="", method="failed").ok)
        self.assertFalse(FetchResult(url="u", text="content", method="failed").ok)
        self.assertFalse(FetchResult(url="u", text="", method="markdown").ok)


# ---------------------------------------------------------------------------
# Live integration tests (opt-in with --live)
# ---------------------------------------------------------------------------

class TestLiveIntegration(unittest.TestCase):
    """Live HTTP tests — only run with --live flag."""

    def test_cloudflare_blog(self):
        """Fetch a Cloudflare blog post (likely supports Markdown for Agents)."""
        if not _RUN_LIVE:
            self.skipTest("Live tests disabled (use --live)")
        result = fetch_markdown("https://blog.cloudflare.com/markdown-for-ai-agents/")
        self.assertTrue(result.ok, f"Fetch failed: {result.error}")
        self.assertGreater(len(result.text), 500)
        print(f"\n  [LIVE] Cloudflare blog: method={result.method}, "
              f"tokens={result.token_estimate}, len={len(result.text)}")

    def test_wirecutter_review(self):
        """Fetch a Wirecutter review page."""
        if not _RUN_LIVE:
            self.skipTest("Live tests disabled (use --live)")
        result = fetch_markdown("https://www.nytimes.com/wirecutter/reviews/best-wireless-earbuds/")
        self.assertTrue(result.ok, f"Fetch failed: {result.error}")
        print(f"\n  [LIVE] Wirecutter: method={result.method}, "
              f"tokens={result.token_estimate}, len={len(result.text)}")

    def test_persist_live(self):
        """Fetch with artifact persistence."""
        if not _RUN_LIVE:
            self.skipTest("Live tests disabled (use --live)")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_markdown(
                "https://blog.cloudflare.com/markdown-for-ai-agents/",
                persist_to=tmpdir,
            )
            if result.ok:
                self.assertIsNotNone(result.artifact_path)
                md_path = Path(result.artifact_path)
                self.assertTrue(md_path.exists())
                json_path = md_path.with_suffix(".json")
                self.assertTrue(json_path.exists())
                meta = json.loads(json_path.read_text())
                print(f"\n  [LIVE] Persisted: {md_path.name} ({md_path.stat().st_size} bytes)")
                print(f"         Metadata: {json.dumps(meta, indent=2)}")


if __name__ == "__main__":
    # Remove --live from argv so unittest doesn't choke on it
    if "--live" in sys.argv:
        sys.argv.remove("--live")
    unittest.main(verbosity=2)
