#!/usr/bin/env python3
"""Tests for youtube_trends.py — video item parsing and engagement metrics.

These are inline pure functions extracted from youtube_trends.py main() logic.
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from lib.common import iso8601_duration_to_seconds


def parse_video_item(item: dict, now: dt.datetime) -> dict | None:
    """Extract and calculate metrics from a YouTube API video item.

    Pure re-implementation of the transform logic in youtube_trends.py lines 82-114.
    """
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})
    published_at = snippet.get("publishedAt")
    if not published_at:
        return None

    published_dt = dt.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    age_hours = max(
        (now.replace(tzinfo=dt.timezone.utc) - published_dt).total_seconds() / 3600,
        0.1,
    )

    view_count = int(stats.get("viewCount", 0))
    like_count = int(stats.get("likeCount", 0)) if "likeCount" in stats else None
    comment_count = int(stats.get("commentCount", 0)) if "commentCount" in stats else None

    duration_sec = iso8601_duration_to_seconds(content.get("duration", "PT0S"))
    views_per_hour = view_count / age_hours
    like_rate = (like_count / view_count) if like_count and view_count else None

    return {
        "videoId": item.get("id"),
        "title": snippet.get("title"),
        "channelTitle": snippet.get("channelTitle"),
        "publishedAt": published_at,
        "url": f"https://www.youtube.com/watch?v={item.get('id')}",
        "viewCount": view_count,
        "likeCount": like_count,
        "commentCount": comment_count,
        "durationSec": duration_sec,
        "viewsPerHour": round(views_per_hour, 2),
        "likeRate": round(like_rate, 4) if like_rate is not None else None,
    }


# ---------------------------------------------------------------
# parse_video_item
# ---------------------------------------------------------------

class TestParseVideoItem(unittest.TestCase):

    def setUp(self):
        self.now = dt.datetime(2026, 2, 16, 12, 0, 0, tzinfo=dt.timezone.utc)

    def _item(self, **overrides):
        base = {
            "id": "vid123",
            "snippet": {
                "title": "Test Video",
                "channelTitle": "TestChannel",
                "publishedAt": "2026-02-16T00:00:00Z",
            },
            "statistics": {
                "viewCount": "10000",
                "likeCount": "500",
                "commentCount": "50",
            },
            "contentDetails": {
                "duration": "PT10M30S",
            },
        }
        for k, v in overrides.items():
            if k in base:
                if isinstance(base[k], dict) and isinstance(v, dict):
                    base[k].update(v)
                else:
                    base[k] = v
            else:
                base[k] = v
        return base

    def test_basic_parsing(self):
        result = parse_video_item(self._item(), self.now)
        self.assertIsNotNone(result)
        self.assertEqual(result["videoId"], "vid123")
        self.assertEqual(result["title"], "Test Video")
        self.assertEqual(result["viewCount"], 10000)
        self.assertEqual(result["likeCount"], 500)
        self.assertEqual(result["commentCount"], 50)

    def test_views_per_hour(self):
        result = parse_video_item(self._item(), self.now)
        # Published 12 hours ago, 10000 views → ~833.33 views/hour
        self.assertAlmostEqual(result["viewsPerHour"], 833.33, places=1)

    def test_like_rate(self):
        result = parse_video_item(self._item(), self.now)
        # 500 likes / 10000 views = 0.05
        self.assertAlmostEqual(result["likeRate"], 0.05, places=4)

    def test_duration_parsed(self):
        result = parse_video_item(self._item(), self.now)
        self.assertEqual(result["durationSec"], 630.0)  # 10m30s

    def test_url_format(self):
        result = parse_video_item(self._item(), self.now)
        self.assertEqual(result["url"], "https://www.youtube.com/watch?v=vid123")

    def test_missing_published_at(self):
        item = self._item()
        item["snippet"]["publishedAt"] = None
        result = parse_video_item(item, self.now)
        self.assertIsNone(result)

    def test_no_published_at_key(self):
        item = self._item()
        del item["snippet"]["publishedAt"]
        result = parse_video_item(item, self.now)
        self.assertIsNone(result)

    def test_zero_views(self):
        item = self._item(statistics={"viewCount": "0", "likeCount": "0"})
        result = parse_video_item(item, self.now)
        self.assertEqual(result["viewCount"], 0)
        self.assertIsNone(result["likeRate"])  # 0/0 → None

    def test_missing_like_count(self):
        item = self._item()
        del item["statistics"]["likeCount"]
        result = parse_video_item(item, self.now)
        self.assertIsNone(result["likeCount"])
        self.assertIsNone(result["likeRate"])

    def test_missing_comment_count(self):
        item = self._item()
        del item["statistics"]["commentCount"]
        result = parse_video_item(item, self.now)
        self.assertIsNone(result["commentCount"])

    def test_age_hours_minimum(self):
        # Published in the future (just now) → age_hours clamped to 0.1
        item = self._item()
        item["snippet"]["publishedAt"] = "2026-02-16T12:00:00Z"
        result = parse_video_item(item, self.now)
        self.assertGreater(result["viewsPerHour"], 0)

    def test_very_old_video(self):
        item = self._item()
        item["snippet"]["publishedAt"] = "2026-02-14T00:00:00Z"
        result = parse_video_item(item, self.now)
        # 60 hours old, 10000 views → ~166.67
        self.assertAlmostEqual(result["viewsPerHour"], 166.67, places=1)


# ---------------------------------------------------------------
# Sorting behavior
# ---------------------------------------------------------------

class TestVideoSorting(unittest.TestCase):

    def test_sort_by_views_per_hour(self):
        rows = [
            {"viewsPerHour": 100, "title": "slow"},
            {"viewsPerHour": 5000, "title": "viral"},
            {"viewsPerHour": 500, "title": "normal"},
        ]
        rows.sort(key=lambda r: r["viewsPerHour"], reverse=True)
        self.assertEqual(rows[0]["title"], "viral")
        self.assertEqual(rows[1]["title"], "normal")
        self.assertEqual(rows[2]["title"], "slow")


# ---------------------------------------------------------------
# parse_video_item edge cases
# ---------------------------------------------------------------

class TestParseVideoItemEdgeCases(unittest.TestCase):

    def setUp(self):
        self.now = dt.datetime(2026, 2, 16, 12, 0, 0, tzinfo=dt.timezone.utc)

    def test_empty_item(self):
        result = parse_video_item({}, self.now)
        self.assertIsNone(result)

    def test_empty_snippet(self):
        item = {"snippet": {}, "statistics": {}, "contentDetails": {}}
        result = parse_video_item(item, self.now)
        self.assertIsNone(result)

    def test_no_statistics(self):
        item = {
            "id": "v1",
            "snippet": {"publishedAt": "2026-02-16T00:00:00Z", "title": "T"},
            "contentDetails": {"duration": "PT5M"},
        }
        result = parse_video_item(item, self.now)
        self.assertIsNotNone(result)
        self.assertEqual(result["viewCount"], 0)
        self.assertIsNone(result["likeCount"])

    def test_no_content_details(self):
        item = {
            "id": "v2",
            "snippet": {"publishedAt": "2026-02-16T00:00:00Z"},
            "statistics": {"viewCount": "100"},
        }
        result = parse_video_item(item, self.now)
        self.assertIsNotNone(result)
        self.assertEqual(result["durationSec"], 0)

    def test_very_high_views(self):
        item = {
            "id": "v3",
            "snippet": {"publishedAt": "2026-02-16T10:00:00Z"},
            "statistics": {"viewCount": "50000000", "likeCount": "2000000"},
            "contentDetails": {"duration": "PT1H"},
        }
        result = parse_video_item(item, self.now)
        self.assertEqual(result["viewCount"], 50_000_000)
        self.assertAlmostEqual(result["likeRate"], 0.04, places=4)

    def test_future_video_clamps_age(self):
        item = {
            "id": "v4",
            "snippet": {"publishedAt": "2026-02-16T13:00:00Z"},
            "statistics": {"viewCount": "100"},
            "contentDetails": {"duration": "PT1M"},
        }
        result = parse_video_item(item, self.now)
        # Published 1 hour in future => age_hours clamped to 0.1
        self.assertAlmostEqual(result["viewsPerHour"], 1000.0, places=0)

    def test_like_rate_zero_views(self):
        item = {
            "id": "v5",
            "snippet": {"publishedAt": "2026-02-16T00:00:00Z"},
            "statistics": {"viewCount": "0", "likeCount": "5"},
            "contentDetails": {},
        }
        result = parse_video_item(item, self.now)
        # likeCount is 5 but viewCount is 0, so like_rate condition fails
        self.assertIsNone(result["likeRate"])


# ---------------------------------------------------------------
# Sorting edge cases
# ---------------------------------------------------------------

class TestVideoSortingEdgeCases(unittest.TestCase):

    def test_sort_stable_for_equal_values(self):
        rows = [
            {"viewsPerHour": 100, "title": "first"},
            {"viewsPerHour": 100, "title": "second"},
        ]
        rows.sort(key=lambda r: r["viewsPerHour"], reverse=True)
        # Python sort is stable, so original order preserved
        self.assertEqual(rows[0]["title"], "first")

    def test_sort_with_none_views(self):
        rows = [
            {"viewsPerHour": 100, "title": "a"},
            {"viewsPerHour": 0, "title": "b"},
        ]
        rows.sort(key=lambda r: r["viewsPerHour"], reverse=True)
        self.assertEqual(rows[0]["title"], "a")


if __name__ == "__main__":
    unittest.main()
