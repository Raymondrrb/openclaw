"""Tests for tools/lib/supabase_pipeline.py.

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


class TestCreateRun(unittest.TestCase):
    """Test create_run()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_create_run(self, mock_urlopen):
        row = [{"id": "uuid-abc-123", "video_id": "v1"}]
        mock_urlopen.return_value = _mock_response(json.dumps(row).encode())
        from tools.lib.supabase_pipeline import create_run
        run_id = create_run("v1", "wireless earbuds", config={"dry_run": False})
        self.assertEqual(run_id, "uuid-abc-123")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/pipeline_runs", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["video_id"], "v1")
        self.assertEqual(body["status"], "running")

    @patch.dict("os.environ", {}, clear=True)
    def test_create_run_disabled(self):
        from tools.lib.supabase_pipeline import create_run
        run_id = create_run("v1", "earbuds")
        self.assertEqual(run_id, "")


class TestCompleteRun(unittest.TestCase):
    """Test complete_run()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_complete_run(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import complete_run
        complete_run("uuid-abc", "complete", ["niche", "research"], [])
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.method, "PATCH")
        body = json.loads(req.data)
        self.assertEqual(body["status"], "complete")


class TestSaveNiche(unittest.TestCase):
    """Test save_niche()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_niche(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import save_niche
        save_niche("uuid-run", "v1", cluster="audio", subcategory="earbuds")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/niches", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["run_id"], "uuid-run")
        self.assertEqual(body["cluster"], "audio")


class TestSaveResearchSource(unittest.TestCase):
    """Test save_research_source()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_research_source(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import save_research_source
        save_research_source("uuid-run", source_domain="nytimes.com",
                             source_url="https://nytimes.com/wirecutter/test")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/research_sources", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["source_domain"], "nytimes.com")


class TestSaveShortlistItem(unittest.TestCase):
    """Test save_shortlist_item()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_shortlist_item(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import save_shortlist_item
        save_shortlist_item("uuid-run", product_name_clean="Sony WF-1000XM5",
                            candidate_rank=1)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/shortlist_items", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["product_name_clean"], "Sony WF-1000XM5")
        self.assertEqual(body["candidate_rank"], 1)


class TestSaveAmazonProduct(unittest.TestCase):
    """Test save_amazon_product()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_amazon_product(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import save_amazon_product
        save_amazon_product("uuid-run", asin="B0123", amazon_title="Test Product")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/amazon_products", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["asin"], "B0123")


class TestSaveTop5Product(unittest.TestCase):
    """Test save_top5_product()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_top5_product(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import save_top5_product
        save_top5_product("uuid-run", rank=1, asin="B0123",
                          role_label="Best Overall", benefits=["good", "great"])
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/top5", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["rank"], 1)
        self.assertEqual(body["role_label"], "Best Overall")


class TestEnsureRunId(unittest.TestCase):
    """Test ensure_run_id()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_ensure_run_id(self, mock_urlopen):
        # First call: query returns existing row
        mock_urlopen.return_value = _mock_response(
            json.dumps([{"id": "existing-uuid"}]).encode()
        )
        from tools.lib.supabase_pipeline import ensure_run_id
        rid = ensure_run_id("v1", "research")
        self.assertEqual(rid, "existing-uuid")

    @patch.dict("os.environ", {}, clear=True)
    def test_ensure_run_id_failure(self):
        from tools.lib.supabase_pipeline import ensure_run_id
        rid = ensure_run_id("v1", "research")
        self.assertEqual(rid, "")


class TestSaveScript(unittest.TestCase):
    """Test save_script()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_script(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import save_script
        save_script("uuid-run", "brief", text="Brief content here", word_count=150)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/scripts", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["status"], "brief")
        self.assertEqual(body["brief_text"], "Brief content here")


class TestSaveAsset(unittest.TestCase):
    """Test save_asset()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_asset(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import save_asset
        save_asset("uuid-run", asset_type="thumbnail", label="thumb",
                   storage_url="https://x.co/thumb.png")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/assets", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["asset_type"], "thumbnail")


class TestSaveTTSChunk(unittest.TestCase):
    """Test save_tts_chunk()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_tts_chunk(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import save_tts_chunk
        save_tts_chunk("uuid-run", chunk_index=0, text="Hello world",
                       duration_seconds=5.5)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/tts_audio", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["chunk_index"], 0)
        self.assertEqual(body["duration_seconds"], 5.5)


class TestUploadVideoFile(unittest.TestCase):
    """Test upload_video_file()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_upload_video_file_path_convention(self, mock_urlopen):
        import tempfile
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_pipeline import upload_video_file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"data")
            f.flush()
            url = upload_video_file("v001", "rayviewslab-assets", f.name, "thumb.png")
        self.assertIn("videos/v001/thumb.png", url)
        Path(f.name).unlink()


class TestSaveLesson(unittest.TestCase):
    """Test save_lesson()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_save_lesson(self, mock_urlopen):
        row = [{"scope": "research", "trigger": "empty shortlist"}]
        mock_urlopen.return_value = _mock_response(json.dumps(row).encode())
        from tools.lib.supabase_pipeline import save_lesson
        save_lesson("research", "empty shortlist", "Check sources first")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/lessons", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["scope"], "research")
        self.assertEqual(body["rule"], "Check sources first")


class TestGetActiveLessons(unittest.TestCase):
    """Test get_active_lessons()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_get_active_lessons(self, mock_urlopen):
        lessons = [{"scope": "qa", "trigger": "drift", "rule": "reject"}]
        mock_urlopen.return_value = _mock_response(json.dumps(lessons).encode())
        from tools.lib.supabase_pipeline import get_active_lessons
        result = get_active_lessons("qa")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["scope"], "qa")


class TestChannelMemory(unittest.TestCase):
    """Test channel memory functions."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_set_channel_memory(self, mock_urlopen):
        row = [{"key": "test_key", "value": {"data": 1}}]
        mock_urlopen.return_value = _mock_response(json.dumps(row).encode())
        from tools.lib.supabase_pipeline import set_channel_memory
        set_channel_memory("test_key", {"data": 1})
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/channel_memory", req.full_url)

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_get_channel_memory(self, mock_urlopen):
        rows = [{"key": "niche_scores", "value": {"earbuds": 85}}]
        mock_urlopen.return_value = _mock_response(json.dumps(rows).encode())
        from tools.lib.supabase_pipeline import get_channel_memory
        result = get_channel_memory("niche_scores")
        self.assertEqual(result, {"earbuds": 85})

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_get_channel_memory_missing(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(json.dumps([]).encode())
        from tools.lib.supabase_pipeline import get_channel_memory
        result = get_channel_memory("nonexistent")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
