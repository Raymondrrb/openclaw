#!/usr/bin/env python3
"""Tests for tools/youtube_channel_analyzer.py — channel video aggregation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from youtube_channel_analyzer import analyze_videos


def _make_video(title="Video", views=1000, likes=50, comments=10, duration_min=8.0):
    return {
        "title": title,
        "views": views,
        "likes": likes,
        "comments": comments,
        "duration_min": duration_min,
    }


# ---------------------------------------------------------------
# analyze_videos
# ---------------------------------------------------------------

class TestAnalyzeVideos(unittest.TestCase):

    def test_empty_list(self):
        self.assertEqual(analyze_videos([]), {})

    def test_single_video(self):
        videos = [_make_video(views=1000, duration_min=10.0)]
        result = analyze_videos(videos)
        self.assertEqual(result["total_videos"], 1)
        self.assertEqual(result["avg_views"], 1000)
        self.assertEqual(result["median_views"], 1000)
        self.assertEqual(result["max_views"], 1000)
        self.assertEqual(result["avg_duration_min"], 10.0)

    def test_multiple_videos_avg(self):
        videos = [
            _make_video(views=100),
            _make_video(views=200),
            _make_video(views=300),
        ]
        result = analyze_videos(videos)
        self.assertEqual(result["total_videos"], 3)
        self.assertEqual(result["avg_views"], 200)

    def test_top_performers(self):
        videos = [
            _make_video(views=100),
            _make_video(views=100),
            _make_video(views=500),  # > 2x avg (233)
        ]
        result = analyze_videos(videos)
        self.assertEqual(result["top_performers_count"], 1)

    def test_review_format_detection(self):
        videos = [
            _make_video(title="Top 5 Earbuds"),
            _make_video(title="Best Monitors 2026"),
            _make_video(title="Product Review: Sony XM5"),
            _make_video(title="Random Vlog"),
        ]
        result = analyze_videos(videos)
        self.assertEqual(result["review_format_videos"], 3)

    def test_duration_buckets(self):
        videos = [
            _make_video(duration_min=3.0, views=100),   # short
            _make_video(duration_min=10.0, views=200),   # medium
            _make_video(duration_min=20.0, views=300),   # long
        ]
        result = analyze_videos(videos)
        self.assertEqual(result["short_videos_avg_views"], 100)
        self.assertEqual(result["medium_videos_avg_views"], 200)
        self.assertEqual(result["long_videos_avg_views"], 300)

    def test_engagement_rate(self):
        videos = [_make_video(views=1000, likes=50, comments=10)]
        result = analyze_videos(videos)
        # (50+10)/1000 * 100 = 6.0
        self.assertEqual(result["engagement_rate_avg"], 6.0)

    def test_zero_duration_excluded(self):
        videos = [
            _make_video(duration_min=0),
            _make_video(duration_min=10.0),
        ]
        result = analyze_videos(videos)
        self.assertEqual(result["avg_duration_min"], 10.0)

    def test_max_views(self):
        videos = [
            _make_video(views=100),
            _make_video(views=5000),
            _make_video(views=200),
        ]
        result = analyze_videos(videos)
        self.assertEqual(result["max_views"], 5000)

    def test_review_vs_comparison(self):
        videos = [
            _make_video(title="Sony vs Bose"),
            _make_video(title="Earbuds compared"),
            _make_video(title="Under $50 budget picks"),
        ]
        result = analyze_videos(videos)
        self.assertEqual(result["review_format_videos"], 3)


    def test_median_even_count(self):
        videos = [
            _make_video(views=100),
            _make_video(views=200),
            _make_video(views=300),
            _make_video(views=400),
        ]
        result = analyze_videos(videos)
        # sorted: [100,200,300,400], total//2=2, index 2 → 300
        self.assertEqual(result["median_views"], 300)

    def test_median_two_videos(self):
        videos = [_make_video(views=50), _make_video(views=150)]
        result = analyze_videos(videos)
        # sorted: [50,150], total//2=1, index 1 → 150
        self.assertEqual(result["median_views"], 150)

    def test_zero_views_engagement(self):
        videos = [_make_video(views=0, likes=5, comments=2)]
        result = analyze_videos(videos)
        # max(0,1) = 1, (5+2)/1*100 = 700.0
        self.assertEqual(result["engagement_rate_avg"], 700.0)

    def test_all_zero_duration(self):
        videos = [_make_video(duration_min=0), _make_video(duration_min=0)]
        result = analyze_videos(videos)
        self.assertEqual(result["avg_duration_min"], 0)

    def test_no_top_performers(self):
        videos = [
            _make_video(views=100),
            _make_video(views=100),
            _make_video(views=100),
        ]
        result = analyze_videos(videos)
        self.assertEqual(result["top_performers_count"], 0)

    def test_all_short_videos(self):
        videos = [_make_video(duration_min=2.0), _make_video(duration_min=4.0)]
        result = analyze_videos(videos)
        self.assertGreater(result["short_videos_avg_views"], 0)
        self.assertEqual(result["medium_videos_avg_views"], 0)
        self.assertEqual(result["long_videos_avg_views"], 0)

    def test_duration_boundary_5min(self):
        videos = [_make_video(duration_min=5.0, views=100)]
        result = analyze_videos(videos)
        # 5.0 <= 5 → short
        self.assertEqual(result["short_videos_avg_views"], 100)

    def test_duration_boundary_15min(self):
        videos = [_make_video(duration_min=15.0, views=100)]
        result = analyze_videos(videos)
        # 5 < 15.0 <= 15 → medium
        self.assertEqual(result["medium_videos_avg_views"], 100)

    def test_high_engagement(self):
        videos = [_make_video(views=10, likes=100, comments=50)]
        result = analyze_videos(videos)
        # (100+50)/10*100 = 1500.0
        self.assertEqual(result["engagement_rate_avg"], 1500.0)

    def test_title_case_insensitive_review(self):
        videos = [_make_video(title="BEST Earbuds REVIEW")]
        result = analyze_videos(videos)
        self.assertEqual(result["review_format_videos"], 1)

    def test_top5_title_detected(self):
        videos = [_make_video(title="Top5 Budget Monitors")]
        result = analyze_videos(videos)
        self.assertEqual(result["review_format_videos"], 1)

    def test_under_dollar_detected(self):
        videos = [_make_video(title="Under $30 picks for students")]
        result = analyze_videos(videos)
        self.assertEqual(result["review_format_videos"], 1)


if __name__ == "__main__":
    unittest.main()
