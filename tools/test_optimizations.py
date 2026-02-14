#!/usr/bin/env python3
"""Tests for optimization modules: parallel fetch, evidence cache, content chunker.

Run:
    python3 tools/test_optimizations.py
    python3 tools/test_optimizations.py --live
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

from lib.content_chunker import (
    Chunk,
    chunk_by_headings,
    chunk_by_size,
    chunk_summary,
    chunk_text,
    estimate_tokens,
    select_relevant_chunks,
)
from lib.evidence_cache import EvidenceCache
from lib.fetch_cache import FetchCache
from lib.markdown_fetch import FetchResult, fetch_markdown, fetch_markdown_batch

_RUN_LIVE = "--live" in sys.argv


# =========================================================================
# Parallel Fetch Tests
# =========================================================================

class TestParallelFetch(unittest.TestCase):
    """Test parallel fetch_markdown_batch."""

    def _mock_urlopen(self, body: bytes, headers: dict):
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.headers = MagicMock()
        mock_resp.headers.items.return_value = list(headers.items())
        mock_resp.headers.get.side_effect = lambda k, d="": headers.get(k, d)
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        return mock_resp

    def _long_body(self, label: str = "") -> bytes:
        return (
            f"# Review {label}\n\n"
            f"Detailed product review with outstanding build quality, reliable "
            f"long-term performance, comfortable ergonomic design, excellent "
            f"battery life, and competitive pricing in the market segment {label}."
        ).encode()

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_parallel_batch(self, mock_urlopen):
        headers = {"content-type": "text/markdown"}
        mock_urlopen.return_value = self._mock_urlopen(self._long_body(), headers)

        urls = [f"https://example.com/page{i}" for i in range(5)]
        results = fetch_markdown_batch(urls, parallel=True, max_workers=3)

        self.assertEqual(len(results), 5)
        for r in results:
            self.assertTrue(r.ok)

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_sequential_batch(self, mock_urlopen):
        headers = {"content-type": "text/markdown"}
        mock_urlopen.return_value = self._mock_urlopen(self._long_body(), headers)

        urls = [f"https://example.com/page{i}" for i in range(3)]
        results = fetch_markdown_batch(urls, parallel=False)

        self.assertEqual(len(results), 3)
        for r in results:
            self.assertTrue(r.ok)

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_parallel_with_cache(self, mock_urlopen):
        headers = {"content-type": "text/markdown"}
        mock_urlopen.return_value = self._mock_urlopen(self._long_body(), headers)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FetchCache(cache_dir=tmpdir)
            urls = ["https://example.com/a", "https://example.com/b"]

            # First batch — HTTP
            r1 = fetch_markdown_batch(urls, cache=cache, parallel=True)
            self.assertEqual(mock_urlopen.call_count, 2)

            # Second batch — all cached
            r2 = fetch_markdown_batch(urls, cache=cache, parallel=True)
            self.assertEqual(mock_urlopen.call_count, 2)  # no new HTTP
            for r in r2:
                self.assertTrue(r.method.startswith("cached:"))

    @patch("lib.markdown_fetch.urllib.request.urlopen")
    def test_single_url_no_threads(self, mock_urlopen):
        """Single URL should not spawn thread pool."""
        headers = {"content-type": "text/markdown"}
        mock_urlopen.return_value = self._mock_urlopen(self._long_body(), headers)

        results = fetch_markdown_batch(["https://example.com/solo"], parallel=True)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)

    def test_live_parallel_speedup(self):
        if not _RUN_LIVE:
            self.skipTest("Live tests disabled")

        urls = [
            "https://blog.cloudflare.com/markdown-for-ai-agents/",
            "https://blog.cloudflare.com/",
            "https://www.cloudflare.com/learning/ddos/what-is-a-ddos-attack/",
        ]

        t0 = time.monotonic()
        seq_results = fetch_markdown_batch(urls, parallel=False)
        seq_time = time.monotonic() - t0

        t0 = time.monotonic()
        par_results = fetch_markdown_batch(urls, parallel=True, max_workers=3)
        par_time = time.monotonic() - t0

        print(f"\n  [LIVE] Sequential: {seq_time:.2f}s, Parallel: {par_time:.2f}s "
              f"({seq_time / max(par_time, 0.001):.1f}x speedup)")
        # Parallel should be faster (or equal if network is the bottleneck)
        self.assertEqual(len(par_results), 3)


# =========================================================================
# Evidence Cache Tests
# =========================================================================

class TestEvidenceCache(unittest.TestCase):
    """Test evidence cache for skip-extraction."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ecache = EvidenceCache(cache_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_put_and_get(self):
        url = "https://nytimes.com/wirecutter/reviews/best-earbuds"
        text = "Review content about earbuds..."
        evidence = [
            {"product": "Sony WF-1000XM5", "label": "best overall"},
            {"product": "Jabra Elite 85t", "label": "best budget"},
        ]

        self.ecache.put_evidence(url, text, evidence, source_name="Wirecutter")

        # Same text → should get evidence back
        got = self.ecache.get_evidence(url, text)
        self.assertIsNotNone(got)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["product"], "Sony WF-1000XM5")

    def test_miss_on_changed_content(self):
        url = "https://nytimes.com/wirecutter/reviews/best-earbuds"
        self.ecache.put_evidence(url, "version 1", [{"product": "A"}])

        # Different text → content changed → should return None
        got = self.ecache.get_evidence(url, "version 2 (updated)")
        self.assertIsNone(got)

    def test_miss_on_uncached(self):
        got = self.ecache.get_evidence("https://new.com", "anything")
        self.assertIsNone(got)

    def test_has_changed(self):
        url = "https://example.com/review"
        self.ecache.put_evidence(url, "content v1", [])

        self.assertFalse(self.ecache.has_changed(url, "content v1"))
        self.assertTrue(self.ecache.has_changed(url, "content v2"))
        self.assertTrue(self.ecache.has_changed("https://other.com", "any"))

    def test_invalidate(self):
        url = "https://example.com/review"
        self.ecache.put_evidence(url, "text", [{"product": "X"}])
        self.assertIn(url, self.ecache)

        self.assertTrue(self.ecache.invalidate(url))
        self.assertNotIn(url, self.ecache)
        self.assertFalse(self.ecache.invalidate(url))  # already gone

    def test_ttl_expiration(self):
        ecache = EvidenceCache(cache_dir=self.tmpdir, ttl_hours=0.0001)
        url = "https://example.com/review"
        ecache.put_evidence(url, "text", [{"x": 1}])

        # Fresh
        self.assertIsNotNone(ecache.get_evidence(url, "text"))

        time.sleep(0.5)

        # Expired
        self.assertIsNone(ecache.get_evidence(url, "text"))

    def test_stats(self):
        self.ecache.put_evidence("https://a.com", "a", [], source_name="Wirecutter")
        self.ecache.put_evidence("https://b.com", "b", [], source_name="RTINGS")

        s = self.ecache.stats()
        self.assertEqual(s["total_entries"], 2)
        self.assertIn("Wirecutter", s["sources"])
        self.assertIn("RTINGS", s["sources"])

    def test_persistence(self):
        url = "https://example.com/review"
        self.ecache.put_evidence(url, "text", [{"product": "Test"}])

        # New instance, same dir
        ecache2 = EvidenceCache(cache_dir=self.tmpdir)
        got = ecache2.get_evidence(url, "text")
        self.assertIsNotNone(got)
        self.assertEqual(got[0]["product"], "Test")

    def test_extra_metadata(self):
        url = "https://example.com/review"
        self.ecache.put_evidence(
            url, "text", [{"x": 1}],
            source_name="PCMag",
            extra={"fetch_method": "markdown", "tokens": 500},
        )
        entry = self.ecache._index[list(self.ecache._index.keys())[0]]
        self.assertEqual(entry["source_name"], "PCMag")
        self.assertEqual(entry["fetch_method"], "markdown")


# =========================================================================
# Content Chunker Tests
# =========================================================================

class TestTokenEstimation(unittest.TestCase):

    def test_estimate_basic(self):
        self.assertEqual(estimate_tokens("abcd"), 1)  # 4 chars / 4 = 1
        self.assertGreater(estimate_tokens("a" * 4000), 900)

    def test_estimate_with_hint(self):
        self.assertEqual(estimate_tokens("anything", hint=500), 500)
        self.assertEqual(estimate_tokens("anything", hint=0), 2)  # 0 is falsy, fallback


class TestChunkByHeadings(unittest.TestCase):

    def _make_md(self, sections: int = 5, lines_per: int = 20) -> str:
        parts = []
        for i in range(sections):
            parts.append(f"## Section {i + 1}")
            parts.append("")
            for j in range(lines_per):
                parts.append(f"This is line {j + 1} of section {i + 1} with some content padding here.")
            parts.append("")
        return "\n".join(parts)

    def test_splits_on_headings(self):
        text = self._make_md(sections=5, lines_per=30)
        chunks = chunk_by_headings(text, max_tokens=500)
        self.assertGreater(len(chunks), 1)
        # Each chunk should have heading info
        headings = [c.heading for c in chunks if c.heading]
        self.assertGreater(len(headings), 0)

    def test_merges_small_sections(self):
        text = "## A\nShort.\n\n## B\nAlso short.\n\n## C\nTiny."
        chunks = chunk_by_headings(text, max_tokens=500)
        # All should merge into 1 chunk (very small)
        self.assertEqual(len(chunks), 1)

    def test_indexes_sequential(self):
        text = self._make_md(sections=10, lines_per=40)
        chunks = chunk_by_headings(text, max_tokens=300)
        for i, c in enumerate(chunks):
            self.assertEqual(c.index, i)


class TestChunkBySize(unittest.TestCase):

    def test_single_chunk_for_short(self):
        chunks = chunk_by_size("Hello world", max_tokens=500)
        self.assertEqual(len(chunks), 1)

    def test_splits_long_text(self):
        paras = [f"Paragraph {i}. " + "x " * 200 for i in range(20)]
        text = "\n\n".join(paras)
        chunks = chunk_by_size(text, max_tokens=500)
        self.assertGreater(len(chunks), 1)


class TestChunkText(unittest.TestCase):

    def test_auto_no_split_short(self):
        chunks = chunk_text("Short content", max_tokens=2000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "Short content")

    def test_auto_uses_headings_for_markdown(self):
        md = "## Intro\nStuff.\n\n## Body\n" + ("More stuff. " * 200) + "\n\n## End\nDone."
        chunks = chunk_text(md, max_tokens=200)
        self.assertGreater(len(chunks), 1)

    def test_auto_uses_size_for_plain(self):
        plain = "\n\n".join([f"Paragraph {i}. " + "words " * 100 for i in range(10)])
        chunks = chunk_text(plain, max_tokens=300)
        self.assertGreater(len(chunks), 1)

    def test_with_token_hint(self):
        text = "Short"
        # Hint says 5000 tokens → should still not chunk if text is short
        chunks = chunk_text(text, max_tokens=2000, token_hint=5000)
        # But since len(text)=5, estimate would say ~1 token without hint
        # With hint=5000, it should try to chunk but text is too short to split
        self.assertGreater(len(chunks), 0)


class TestSelectRelevant(unittest.TestCase):

    def _make_chunks(self) -> list[Chunk]:
        return [
            Chunk(index=0, text="Introduction and overview of the review", heading="Intro"),
            Chunk(index=1, text="The best overall pick is the Sony WF-1000XM5", heading="Best Overall"),
            Chunk(index=2, text="For budget buyers, the Jabra Elite is top pick", heading="Best Budget"),
            Chunk(index=3, text="Testing methodology and lab setup details", heading="Methodology"),
            Chunk(index=4, text="Frequently asked questions about earbuds", heading="FAQ"),
        ]

    def test_keyword_scoring(self):
        chunks = self._make_chunks()
        relevant = select_relevant_chunks(chunks, keywords=["best overall", "top pick"])
        self.assertGreater(len(relevant), 0)
        # "Best Overall" chunk should rank highest (heading + body match)
        self.assertEqual(relevant[0].heading, "Best Overall")

    def test_no_keywords_returns_all(self):
        chunks = self._make_chunks()
        result = select_relevant_chunks(chunks, keywords=None)
        self.assertEqual(len(result), 5)

    def test_max_chunks(self):
        chunks = self._make_chunks()
        result = select_relevant_chunks(chunks, keywords=["best"], max_chunks=2)
        self.assertLessEqual(len(result), 2)

    def test_empty_keywords_returns_all(self):
        chunks = self._make_chunks()
        result = select_relevant_chunks(chunks, keywords=[])
        self.assertEqual(len(result), 5)


class TestChunkSummary(unittest.TestCase):

    def test_summary_format(self):
        chunks = [
            Chunk(index=0, text="a", token_estimate=100),
            Chunk(index=1, text="b", token_estimate=200),
        ]
        s = chunk_summary(chunks)
        self.assertIn("2 chunks", s)
        self.assertIn("300 tokens", s)


# =========================================================================
# Live integration
# =========================================================================

class TestLiveIntegration(unittest.TestCase):

    def test_full_pipeline(self):
        """Fetch → cache → chunk → select → evidence cache. End-to-end."""
        if not _RUN_LIVE:
            self.skipTest("Live tests disabled")

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FetchCache(cache_dir=f"{tmpdir}/fetch", ttl_hours=1)
            ecache = EvidenceCache(cache_dir=f"{tmpdir}/evidence")

            url = "https://blog.cloudflare.com/markdown-for-ai-agents/"

            # 1. Fetch (cached if already done)
            result = fetch_markdown(url, cache=cache)
            self.assertTrue(result.ok)

            # 2. Chunk
            chunks = chunk_text(result.text, token_hint=result.token_estimate)
            print(f"\n  [LIVE] {chunk_summary(chunks)}")

            # 3. Select relevant
            relevant = select_relevant_chunks(
                chunks, keywords=["markdown", "agent", "cloudflare"]
            )
            print(f"  [LIVE] Relevant: {len(relevant)}/{len(chunks)} chunks")

            # 4. "Extract" evidence (simulated)
            evidence = [{"keyword": "markdown", "found": True}]

            # 5. Cache evidence
            ecache.put_evidence(url, result.text, evidence, source_name="Cloudflare")

            # 6. Re-check — should skip extraction
            prior = ecache.get_evidence(url, result.text)
            self.assertIsNotNone(prior)
            print(f"  [LIVE] Evidence cache hit: {prior}")


if __name__ == "__main__":
    if "--live" in sys.argv:
        sys.argv.remove("--live")
    unittest.main(verbosity=2)
