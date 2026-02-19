#!/usr/bin/env python3
"""Tests for tools/lib/control_plane.py — control_plane_url, api_get, api_post, send_telegram."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from lib.control_plane import api_get, api_post, control_plane_url, send_telegram


# ---------------------------------------------------------------
# control_plane_url
# ---------------------------------------------------------------

class TestControlPlaneUrl(unittest.TestCase):

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://example.vercel.app"})
    def test_returns_url(self):
        self.assertEqual(control_plane_url(), "https://example.vercel.app")

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://example.vercel.app/"})
    def test_strips_trailing_slash(self):
        self.assertEqual(control_plane_url(), "https://example.vercel.app")

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_returns_empty(self):
        env = dict(os.environ)
        env.pop("CONTROL_PLANE_URL", None)
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(control_plane_url(), "")

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": ""})
    def test_empty_env_returns_empty(self):
        self.assertEqual(control_plane_url(), "")

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://example.vercel.app///"})
    def test_multiple_trailing_slashes(self):
        # rstrip("/") removes all trailing slashes
        self.assertEqual(control_plane_url(), "https://example.vercel.app")

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "  https://example.vercel.app  "})
    def test_whitespace_preserved(self):
        # control_plane_url does NOT strip whitespace, only trailing /
        result = control_plane_url()
        self.assertIn("example.vercel.app", result)


# ---------------------------------------------------------------
# api_get
# ---------------------------------------------------------------

class TestApiGet(unittest.TestCase):

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "", "CP_SECRET": "s"})
    def test_missing_url_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            api_get("/api/status", "CP_SECRET")
        self.assertIn("CONTROL_PLANE_URL", str(ctx.exception))

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://cp.test", "CP_SECRET": ""})
    def test_missing_secret_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            api_get("/api/status", "CP_SECRET")
        self.assertIn("CP_SECRET", str(ctx.exception))

    @patch("lib.control_plane.urlopen")
    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://cp.test", "CP_SECRET": "tok123"})
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = api_get("/api/status", "CP_SECRET")
        self.assertTrue(result["ok"])

    @patch("lib.control_plane.urlopen")
    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://cp.test", "CP_SECRET": "tok"})
    def test_with_params(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": []}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        api_get("/api/runs", "CP_SECRET", params={"limit": "10"})
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        self.assertIn("limit=10", req.full_url)


# ---------------------------------------------------------------
# api_post
# ---------------------------------------------------------------

class TestApiPost(unittest.TestCase):

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "", "CP_SECRET": "s"})
    def test_missing_url_raises(self):
        with self.assertRaises(RuntimeError):
            api_post("/api/action", "CP_SECRET", {"key": "val"})

    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://cp.test", "CP_SECRET": ""})
    def test_missing_secret_raises(self):
        with self.assertRaises(RuntimeError):
            api_post("/api/action", "CP_SECRET", {"key": "val"})

    @patch("lib.control_plane.urlopen")
    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://cp.test", "CP_SECRET": "tok"})
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"created": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = api_post("/api/runs", "CP_SECRET", {"run_id": "r1"})
        self.assertTrue(result["created"])


# ---------------------------------------------------------------
# send_telegram
# ---------------------------------------------------------------

class TestSendTelegram(unittest.TestCase):

    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": ""}, clear=False)
    def test_no_chat_id_returns_false(self):
        result = send_telegram("hello")
        self.assertFalse(result)

    @patch("lib.control_plane.subprocess")
    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "12345"}, clear=False)
    def test_success(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        result = send_telegram("test message")
        self.assertTrue(result)
        mock_subprocess.run.assert_called_once()

    @patch("lib.control_plane.subprocess")
    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "12345"}, clear=False)
    def test_failure_returns_false(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(returncode=1)
        result = send_telegram("test message")
        self.assertFalse(result)

    @patch("lib.control_plane.subprocess")
    def test_explicit_chat_id(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        send_telegram("hi", chat_id="999")
        call_args = mock_subprocess.run.call_args[0][0]
        self.assertIn("999", call_args)


# ---------------------------------------------------------------
# api_get — edge cases
# ---------------------------------------------------------------

class TestApiGetEdgeCases(unittest.TestCase):

    @patch("lib.control_plane.urlopen")
    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://cp.test", "CP_SECRET": "tok"})
    def test_http_error_raises_runtime(self, mock_urlopen):
        from urllib.error import HTTPError
        error = HTTPError(
            url="https://cp.test/api/status",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=BytesIO(b'{"error": "boom"}'),
        )
        mock_urlopen.side_effect = error
        with self.assertRaises(RuntimeError) as ctx:
            api_get("/api/status", "CP_SECRET")
        self.assertIn("500", str(ctx.exception))

    @patch("lib.control_plane.urlopen")
    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://cp.test", "CP_SECRET": "tok"})
    def test_empty_params_no_query_string(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        api_get("/api/status", "CP_SECRET", params={})
        req = mock_urlopen.call_args[0][0]
        # Empty params dict should not add "?" to URL
        self.assertFalse(req.full_url.endswith("?"))

    @patch("lib.control_plane.urlopen")
    @patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://cp.test", "CP_SECRET": "tok"})
    def test_no_params_keyword(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "healthy"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = api_get("/api/health", "CP_SECRET")
        self.assertEqual(result["status"], "healthy")


# ---------------------------------------------------------------
# send_telegram — edge cases
# ---------------------------------------------------------------

class TestSendTelegramEdgeCases(unittest.TestCase):

    @patch("lib.control_plane.subprocess")
    def test_explicit_account(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        send_telegram("hi", chat_id="999", account="tg_backup")
        call_args = mock_subprocess.run.call_args[0][0]
        self.assertIn("tg_backup", call_args)

    @patch("lib.control_plane.subprocess")
    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "12345"}, clear=False)
    def test_message_passed_correctly(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        send_telegram("ALERTA: pipeline com falha")
        call_args = mock_subprocess.run.call_args[0][0]
        self.assertIn("ALERTA: pipeline com falha", call_args)

    @patch.dict(os.environ, {}, clear=False)
    def test_no_env_no_explicit_returns_false(self):
        env = dict(os.environ)
        env.pop("TELEGRAM_CHAT_ID", None)
        with patch.dict(os.environ, env, clear=True):
            result = send_telegram("test")
            self.assertFalse(result)

    @patch("lib.control_plane.urlopen")
    @patch("lib.control_plane.subprocess")
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_CHAT_ID": "12345",
            "TELEGRAM_USE_MINIMAX": "1",
            "MINIMAX_API_KEY": "key",
            "MINIMAX_BASE_URL": "https://api.minimax.io/v1",
            "MINIMAX_MODEL": "MiniMax-M2.5",
        },
        clear=False,
    )
    def test_minimax_rewrite_enabled(self, mock_subprocess, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "Mensagem reescrita"}}]}
        ).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        ok = send_telegram("texto original")
        self.assertTrue(ok)
        cmd = mock_subprocess.run.call_args[0][0]
        self.assertIn("Mensagem reescrita", cmd)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertIn("system", payload["messages"][0]["role"])

    @patch("lib.control_plane.urlopen")
    @patch("lib.control_plane.subprocess")
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_CHAT_ID": "12345",
            "TELEGRAM_USE_MINIMAX": "1",
            "MINIMAX_API_KEY": "key",
        },
        clear=False,
    )
    def test_minimax_failure_falls_back_to_raw(self, mock_subprocess, mock_urlopen):
        mock_urlopen.side_effect = RuntimeError("api fail")
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        ok = send_telegram("mensagem crua")
        self.assertTrue(ok)
        cmd = mock_subprocess.run.call_args[0][0]
        self.assertIn("mensagem crua", cmd)

    @patch("lib.control_plane.urlopen")
    @patch("lib.control_plane.subprocess")
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_CHAT_ID": "12345",
            "TELEGRAM_USE_MINIMAX": "1",
            "MINIMAX_API_KEY": "key",
            "TELEGRAM_MINIMAX_TEMPLATE_GATE": "Template gate custom",
        },
        clear=False,
    )
    def test_minimax_template_by_kind(self, mock_subprocess, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "Mensagem custom"}}]}
        ).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        ok = send_telegram("entrada", message_kind="gate")
        self.assertTrue(ok)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["messages"][0]["content"], "Template gate custom")

    @patch("lib.control_plane.urlopen")
    @patch("lib.control_plane.subprocess")
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_CHAT_ID": "12345",
            "TELEGRAM_USE_MINIMAX": "1",
            "MINIMAX_API_KEY": "key",
        },
        clear=False,
    )
    def test_rewrite_log_written(self, mock_subprocess, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "mensagem final"}}]}
        ).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "telegram_rewrites.jsonl"
            with patch.dict(os.environ, {"TELEGRAM_REWRITE_LOG_PATH": str(log_path)}, clear=False):
                ok = send_telegram("mensagem original", message_kind="summary")
            self.assertTrue(ok)
            self.assertTrue(log_path.exists())
            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["kind"], "summary")
            self.assertTrue(rows[0]["rewrite_applied"])
            self.assertEqual(rows[0]["final_message"], "mensagem final")


if __name__ == "__main__":
    unittest.main()
