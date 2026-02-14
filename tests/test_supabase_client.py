"""Tests for tools/lib/supabase_client.py.

Mock-based — no real HTTP calls. Uses _mock_urlopen() pattern.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.supabase_client import (
    _enabled,
    insert,
    upsert,
    update,
    query,
    upload_file,
    file_sha256,
)

MOCK_ENV = {
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-key-123",
}


def _mock_response(body=b"", status=200):
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestEnabled(unittest.TestCase):
    """Test _enabled() gate."""

    @patch.dict("os.environ", {}, clear=True)
    def test_disabled_when_no_url(self):
        self.assertFalse(_enabled())

    @patch.dict("os.environ", {"SUPABASE_URL": "https://x.supabase.co"}, clear=True)
    def test_disabled_when_no_key(self):
        self.assertFalse(_enabled())

    @patch.dict("os.environ", MOCK_ENV, clear=True)
    def test_enabled_when_both_set(self):
        self.assertTrue(_enabled())

    @patch.dict("os.environ", {"SUPABASE_URL": "  ", "SUPABASE_SERVICE_ROLE_KEY": "k"}, clear=True)
    def test_disabled_when_url_blank(self):
        self.assertFalse(_enabled())


class TestInsert(unittest.TestCase):
    """Test insert()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_insert_basic(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        result = insert("my_table", {"name": "test"})
        self.assertIsNone(result)
        # Verify the request was made
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/my_table", req.full_url)
        self.assertEqual(req.method, "POST")
        body = json.loads(req.data)
        self.assertEqual(body["name"], "test")

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_insert_return_row(self, mock_urlopen):
        row = {"id": "abc-123", "name": "test"}
        mock_urlopen.return_value = _mock_response(json.dumps([row]).encode())
        result = insert("my_table", {"name": "test"}, return_row=True)
        self.assertEqual(result["id"], "abc-123")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("return=representation", req.headers.get("Prefer", ""))

    @patch.dict("os.environ", {}, clear=True)
    def test_insert_silent_when_disabled(self):
        result = insert("my_table", {"name": "test"})
        self.assertIsNone(result)

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_insert_handles_http_error(self, mock_urlopen):
        import urllib.error
        err = urllib.error.HTTPError(
            "http://x", 400, "Bad Request", {}, io.BytesIO(b"error detail")
        )
        mock_urlopen.side_effect = err
        result = insert("my_table", {"name": "test"})
        self.assertIsNone(result)


class TestUpsert(unittest.TestCase):
    """Test upsert()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_upsert_merge_header(self, mock_urlopen):
        row = {"id": "abc", "val": 1}
        mock_urlopen.return_value = _mock_response(json.dumps([row]).encode())
        result = upsert("my_table", row)
        req = mock_urlopen.call_args[0][0]
        prefer = req.headers.get("Prefer", "")
        self.assertIn("resolution=merge-duplicates", prefer)
        self.assertIn("return=representation", prefer)
        self.assertIn("on_conflict=id", req.full_url)

    @patch.dict("os.environ", {}, clear=True)
    def test_upsert_silent_when_disabled(self):
        self.assertIsNone(upsert("t", {"id": "x"}))


class TestUpdate(unittest.TestCase):
    """Test update()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_update_sends_patch(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        result = update("runs", {"id": "abc"}, {"status": "complete"})
        self.assertTrue(result)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.method, "PATCH")
        self.assertIn("id=eq.abc", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["status"], "complete")


class TestQuery(unittest.TestCase):
    """Test query()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_query_basic(self, mock_urlopen):
        rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        mock_urlopen.return_value = _mock_response(json.dumps(rows).encode())
        result = query("my_table")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "a")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("select=*", req.full_url)

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_query_with_filters(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(json.dumps([]).encode())
        query("my_table", filters={"status": "active"})
        req = mock_urlopen.call_args[0][0]
        self.assertIn("status=eq.active", req.full_url)

    @patch.dict("os.environ", {}, clear=True)
    def test_query_empty_when_disabled(self):
        result = query("my_table")
        self.assertEqual(result, [])


class TestUpload(unittest.TestCase):
    """Test upload_file()."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_upload_post(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            f.flush()
            url = upload_file("my-bucket", "images/test.png", f.name)
        self.assertIn("my-bucket/images/test.png", url)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.method, "POST")
        self.assertIn("/storage/v1/object/my-bucket/images/test.png", req.full_url)
        Path(f.name).unlink()

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_upload_upsert_on_409(self, mock_urlopen):
        import urllib.error
        err = urllib.error.HTTPError(
            "http://x", 409, "Conflict", {}, io.BytesIO(b"exists")
        )
        # First call (POST) raises 409, second call (PUT) succeeds
        mock_urlopen.side_effect = [err, _mock_response()]
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            f.flush()
            url = upload_file("my-bucket", "images/test.png", f.name)
        self.assertIn("my-bucket/images/test.png", url)
        self.assertEqual(mock_urlopen.call_count, 2)
        Path(f.name).unlink()

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_upload_returns_public_url(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"data")
            f.flush()
            url = upload_file("rayviewslab-assets", "videos/v1/thumb.png", f.name)
        self.assertEqual(
            url,
            "https://test.supabase.co/storage/v1/object/public/rayviewslab-assets/videos/v1/thumb.png",
        )
        Path(f.name).unlink()

    @patch.dict("os.environ", {}, clear=True)
    def test_upload_empty_when_disabled(self):
        url = upload_file("bucket", "path", "/nonexistent")
        self.assertEqual(url, "")


class TestFileSha256(unittest.TestCase):
    """Test file_sha256()."""

    def test_file_sha256(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            f.flush()
            result = file_sha256(f.name)
        expected = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(result, expected)
        Path(f.name).unlink()


class TestLegacyShim(unittest.TestCase):
    """Test supabase_storage.py shim delegates to supabase_client."""

    @patch.dict("os.environ", MOCK_ENV)
    @patch("tools.lib.supabase_client.urllib.request.urlopen")
    def test_legacy_log_generation(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response()
        from tools.lib.supabase_storage import log_generation
        log_generation(
            asset_type="thumbnail",
            product_name="Test Product",
            style="photorealistic",
            status="success",
            local_path="/tmp/test.png",
        )
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/rest/v1/dzine_generations", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["asset_type"], "thumbnail")
        self.assertEqual(body["product_name"], "Test Product")


if __name__ == "__main__":
    unittest.main()
