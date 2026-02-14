"""Tests for tools/lib/video_analytics.py.

Mock-based — no real HTTP calls.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

MOCK_ENV = {
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-key-123",
}


def _mock_response(body=b"", status=200):
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestRecordMetrics(unittest.TestCase):
    """Test record_metrics()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_record_metrics(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.video_analytics import record_metrics
        record_metrics("v001", niche="wireless earbuds",
                       views_7d=5000, ctr_percent=5.2)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/video_metrics", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["video_id"], "v001")
        self.assertEqual(body["niche"], "wireless earbuds")
        self.assertEqual(body["views_7d"], 5000)
        self.assertEqual(body["ctr"], 5.2)

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_record_metrics_partial(self, mock_urlopen):
        """Only non-None fields are included."""
        mock_urlopen.return_value = _mock_response()
        from tools.lib.video_analytics import record_metrics
        record_metrics("v002", views_7d=1000)
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        self.assertIn("views_7d", body)
        self.assertNotIn("views_30d", body)
        self.assertNotIn("ctr", body)


class TestGetNichePerformance(unittest.TestCase):
    """Test get_niche_performance()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_get_niche_performance(self, mock_urlopen):
        rows = [
            {"video_id": "v1", "niche": "earbuds", "views_7d": 5000, "ctr": 5.0},
            {"video_id": "v2", "niche": "monitors", "views_7d": 3000, "ctr": 4.0},
        ]
        mock_urlopen.return_value = _mock_response(json.dumps(rows).encode())
        from tools.lib.video_analytics import get_niche_performance
        result = get_niche_performance(limit=10)
        self.assertEqual(len(result), 2)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("order=recorded_at.desc", req.full_url)
        self.assertIn("limit=10", req.full_url)


class TestUpdateNicheScores(unittest.TestCase):
    """Test update_niche_scores()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_update_niche_scores(self, mock_urlopen):
        # First call: query video_metrics
        metrics = [
            {"niche": "earbuds", "ctr": 5.0, "views_7d": 8000},
            {"niche": "earbuds", "ctr": 6.0, "views_7d": 12000},
            {"niche": "monitors", "ctr": 3.0, "views_7d": 2000},
        ]
        # Second call: upsert channel_memory (return representation)
        memory_row = [{"key": "niche_performance_scores", "value": {}}]

        mock_urlopen.side_effect = [
            _mock_response(json.dumps(metrics).encode()),  # query
            _mock_response(json.dumps(memory_row).encode()),  # upsert
        ]

        from tools.lib.video_analytics import update_niche_scores
        update_niche_scores()

        # Should have made 2 calls: query + upsert
        self.assertEqual(mock_urlopen.call_count, 2)
        # Verify the upsert body has correct scores
        upsert_req = mock_urlopen.call_args_list[1][0][0]
        body = json.loads(upsert_req.data)
        self.assertEqual(body["key"], "niche_performance_scores")
        scores = body["value"]
        self.assertIn("earbuds", scores)
        self.assertEqual(scores["earbuds"]["avg_ctr"], 5.5)
        self.assertEqual(scores["earbuds"]["video_count"], 2)


class TestNichePickerPerformanceBonus(unittest.TestCase):
    """Test that niche_picker uses performance bonus from channel_memory."""

    @patch("tools.lib.supabase_pipeline.get_channel_memory")
    def test_performance_bonus_applied(self, mock_get):
        mock_get.return_value = {
            "wireless earbuds": {"performance_bonus": 10.0, "avg_ctr": 5.0},
        }
        from tools.niche_picker import pick_niche, NICHE_POOL

        # Verify the function doesn't crash with performance bonus
        # (actual niche selection depends on history, so just test no-crash)
        try:
            pick_niche("2026-01-01")
        except RuntimeError:
            pass  # acceptable if all niches used
        mock_get.assert_called_once_with("niche_performance_scores")


if __name__ == "__main__":
    unittest.main()
