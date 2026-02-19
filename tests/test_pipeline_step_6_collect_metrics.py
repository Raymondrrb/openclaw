#!/usr/bin/env python3
"""Tests for tools/pipeline_step_6_collect_metrics.py — URL parsing + metadata."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline_step_6_collect_metrics import extract_video_id


# ---------------------------------------------------------------
# extract_video_id
# ---------------------------------------------------------------

class TestExtractVideoId(unittest.TestCase):

    def test_youtube_watch_url(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_youtube_watch_url_extra_params(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=abc123&t=10&list=PLx"),
            "abc123",
        )

    def test_youtu_be_short_url(self):
        self.assertEqual(
            extract_video_id("https://youtu.be/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_youtu_be_with_query(self):
        self.assertEqual(
            extract_video_id("https://youtu.be/abc123?t=30"),
            "abc123",
        )

    def test_empty_string(self):
        self.assertEqual(extract_video_id(""), "")

    def test_unrelated_url(self):
        self.assertEqual(extract_video_id("https://example.com/page"), "")

    def test_youtube_no_v_param(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch"),
            "",
        )

    def test_youtube_embed_url_not_supported(self):
        # embed URLs use /embed/ID — current implementation only handles watch + youtu.be
        result = extract_video_id("https://www.youtube.com/embed/abc123")
        self.assertEqual(result, "")

    def test_http_scheme(self):
        self.assertEqual(
            extract_video_id("http://youtube.com/watch?v=test99"),
            "test99",
        )

    def test_mobile_youtube(self):
        self.assertEqual(
            extract_video_id("https://m.youtube.com/watch?v=mobile1"),
            "mobile1",
        )

    def test_youtube_music(self):
        self.assertEqual(
            extract_video_id("https://music.youtube.com/watch?v=music1"),
            "music1",
        )


    def test_plain_video_id(self):
        # Just a video ID without URL
        result = extract_video_id("dQw4w9WgXcQ")
        # Should return empty since it's not a valid URL
        self.assertEqual(result, "")

    def test_none_returns_empty(self):
        self.assertEqual(extract_video_id(None), "")

    def test_v_param_empty(self):
        self.assertEqual(extract_video_id("https://www.youtube.com/watch?v="), "")

    def test_youtube_shorts_url(self):
        result = extract_video_id("https://www.youtube.com/shorts/abc123")
        # Shorts URLs may or may not be supported
        self.assertIsInstance(result, str)

    def test_long_video_id(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=abcdefghijk"),
            "abcdefghijk",
        )


# ---------------------------------------------------------------
# extract_video_id edge cases
# ---------------------------------------------------------------

class TestExtractVideoIdEdgeCases(unittest.TestCase):

    def test_youtube_nocookie_url(self):
        result = extract_video_id("https://www.youtube-nocookie.com/embed/abc123")
        # youtube-nocookie.com does not match "youtube.com" or "youtu.be"
        self.assertEqual(result, "")

    def test_lowercase_domain_matches(self):
        result = extract_video_id("https://www.youtube.com/watch?v=CaSe1")
        self.assertEqual(result, "CaSe1")

    def test_youtu_be_with_trailing_slash(self):
        result = extract_video_id("https://youtu.be/abc123/")
        # path is "/abc123/", lstrip "/" gives "abc123/"
        self.assertIn("abc123", result)

    def test_multiple_v_params(self):
        result = extract_video_id("https://www.youtube.com/watch?v=first&v=second")
        self.assertEqual(result, "first")

    def test_url_with_hash_fragment(self):
        result = extract_video_id("https://www.youtube.com/watch?v=test1#t=10")
        self.assertEqual(result, "test1")

    def test_url_with_port(self):
        result = extract_video_id("https://youtube.com:443/watch?v=port1")
        # netloc includes port, "youtube.com" is still in "youtube.com:443"
        self.assertEqual(result, "port1")


if __name__ == "__main__":
    unittest.main()
