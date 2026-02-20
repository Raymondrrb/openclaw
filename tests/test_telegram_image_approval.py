"""Tests for tools/lib/telegram_image_approval.py.

Covers: skip modes, degradation, sendPhoto, sendMediaGroup, approval flows,
rejection with label parsing, timeout, and graceful degradation on errors.
All Telegram API calls are mocked — no network required.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, call, MagicMock

_repo = os.path.join(os.path.dirname(__file__), "..")
if _repo not in sys.path:
    sys.path.insert(0, _repo)

from tools.lib.telegram_image_approval import (
    ImageEntry,
    ImageApprovalResult,
    _bot_token,
    _chat_id,
    _is_configured,
    _openclaw_channel_ready,
    _build_multipart,
    _send_photo,
    _send_media_group,
    _send_approval_buttons,
    _flush_updates,
    _poll_for_callback,
    _poll_for_text_reply,
    _parse_rejected_labels,
    _answer_callback,
    _edit_message_text,
    request_image_approval,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_image(name: str = "test.png", size: int = 1024) -> Path:
    """Create a temporary file simulating an image."""
    tmp = tempfile.NamedTemporaryFile(suffix=f"_{name}", delete=False)
    tmp.write(b"\x89PNG" + b"\x00" * (size - 4))
    tmp.close()
    return Path(tmp.name)


def _make_entries(count: int = 3) -> tuple[list[ImageEntry], list[Path]]:
    """Create test ImageEntry list with temp files."""
    paths = []
    entries = []
    for i in range(count):
        p = _make_temp_image(f"img_{i}.png")
        paths.append(p)
        entries.append(ImageEntry(
            label=f"{i + 1:02d}_hero",
            path=p,
            product_name=f"Product {i + 1}",
            variant="hero",
        ))
    return entries, paths


def _cleanup_paths(paths: list[Path]) -> None:
    for p in paths:
        try:
            p.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Test: Helpers
# ---------------------------------------------------------------------------

class TestHelpers(unittest.TestCase):
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok123", "TELEGRAM_CHAT_ID": "999"})
    def test_configured(self):
        self.assertEqual(_bot_token(), "tok123")
        self.assertEqual(_chat_id(), "999")
        self.assertTrue(_is_configured())

    @patch.dict(os.environ, {}, clear=True)
    def test_not_configured(self):
        self.assertFalse(_is_configured())

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "  ", "TELEGRAM_CHAT_ID": ""})
    def test_whitespace_not_configured(self):
        self.assertFalse(_is_configured())

    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "5853624777"}, clear=True)
    @patch("tools.lib.telegram_image_approval.shutil.which", return_value="/usr/local/bin/openclaw")
    def test_openclaw_channel_ready(self, mock_which):
        self.assertTrue(_openclaw_channel_ready())

    @patch.dict(os.environ, {}, clear=True)
    @patch("tools.lib.telegram_image_approval.shutil.which", return_value="/usr/local/bin/openclaw")
    def test_openclaw_channel_not_ready_without_chat_id(self, mock_which):
        self.assertFalse(_openclaw_channel_ready())


# ---------------------------------------------------------------------------
# Test: ImageApprovalResult
# ---------------------------------------------------------------------------

class TestImageApprovalResult(unittest.TestCase):
    def test_all_approved(self):
        r = ImageApprovalResult(approved=["a", "b"], rejected=[])
        self.assertTrue(r.all_approved)

    def test_not_all_approved(self):
        r = ImageApprovalResult(approved=["a"], rejected=["b"])
        self.assertFalse(r.all_approved)

    def test_empty(self):
        r = ImageApprovalResult()
        self.assertTrue(r.all_approved)
        self.assertEqual(r.approved, [])
        self.assertEqual(r.rejected, [])


# ---------------------------------------------------------------------------
# Test: _build_multipart
# ---------------------------------------------------------------------------

class TestBuildMultipart(unittest.TestCase):
    def test_fields_only(self):
        body, boundary = _build_multipart({"chat_id": "123"}, {})
        self.assertIn(b"chat_id", body)
        self.assertIn(b"123", body)
        self.assertIn(f"--{boundary}--".encode(), body)

    def test_with_file(self):
        body, boundary = _build_multipart(
            {"chat_id": "123"},
            {"photo": ("test.png", b"\x89PNG\x00\x00", "image/png")},
        )
        self.assertIn(b"test.png", body)
        self.assertIn(b"\x89PNG", body)
        self.assertIn(b"image/png", body)


# ---------------------------------------------------------------------------
# Test: _send_photo
# ---------------------------------------------------------------------------

class TestSendPhoto(unittest.TestCase):
    def setUp(self):
        self.img_path = _make_temp_image("photo_test.png")

    def tearDown(self):
        _cleanup_paths([self.img_path])

    @patch("tools.lib.telegram_image_approval._chat_id", return_value="999")
    @patch("tools.lib.telegram_image_approval._bot_token", return_value="tok")
    @patch("tools.lib.telegram_image_approval.urllib.request.urlopen")
    def test_send_success(self, mock_urlopen, mock_token, mock_chat):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "result": {"message_id": 42},
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        mid = _send_photo(self.img_path, caption="Test caption")
        self.assertEqual(mid, 42)

        # Verify the request was made to sendPhoto
        req = mock_urlopen.call_args[0][0]
        self.assertIn("sendPhoto", req.full_url)
        self.assertIn(b"multipart/form-data", req.get_header("Content-type").encode())

    @patch("tools.lib.telegram_image_approval._chat_id", return_value="")
    @patch("tools.lib.telegram_image_approval._bot_token", return_value="tok")
    def test_no_chat_id(self, mock_token, mock_chat):
        mid = _send_photo(self.img_path)
        self.assertIsNone(mid)

    @patch("tools.lib.telegram_image_approval._chat_id", return_value="999")
    @patch("tools.lib.telegram_image_approval._bot_token", return_value="tok")
    def test_file_not_found(self, mock_token, mock_chat):
        mid = _send_photo("/nonexistent/path.png")
        self.assertIsNone(mid)

    @patch("tools.lib.telegram_image_approval._chat_id", return_value="999")
    @patch("tools.lib.telegram_image_approval._bot_token", return_value="tok")
    @patch("tools.lib.telegram_image_approval.urllib.request.urlopen")
    def test_api_error(self, mock_urlopen, mock_token, mock_chat):
        mock_urlopen.side_effect = urllib.error.URLError("fail")
        mid = _send_photo(self.img_path)
        self.assertIsNone(mid)


# ---------------------------------------------------------------------------
# Test: _send_media_group
# ---------------------------------------------------------------------------

class TestSendMediaGroup(unittest.TestCase):
    def setUp(self):
        self.entries, self.paths = _make_entries(3)

    def tearDown(self):
        _cleanup_paths(self.paths)

    @patch("tools.lib.telegram_image_approval._chat_id", return_value="999")
    @patch("tools.lib.telegram_image_approval._bot_token", return_value="tok")
    @patch("tools.lib.telegram_image_approval.urllib.request.urlopen")
    def test_send_album(self, mock_urlopen, mock_token, mock_chat):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "result": [
                {"message_id": 100},
                {"message_id": 101},
                {"message_id": 102},
            ],
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        mid = _send_media_group(self.entries, group_caption="Test album")
        self.assertEqual(mid, 100)

        req = mock_urlopen.call_args[0][0]
        self.assertIn("sendMediaGroup", req.full_url)

    @patch("tools.lib.telegram_image_approval._chat_id", return_value="999")
    @patch("tools.lib.telegram_image_approval._bot_token", return_value="tok")
    @patch("tools.lib.telegram_image_approval.urllib.request.urlopen")
    def test_empty_list(self, mock_urlopen, mock_token, mock_chat):
        mid = _send_media_group([], group_caption="Test")
        self.assertIsNone(mid)
        mock_urlopen.assert_not_called()

    @patch("tools.lib.telegram_image_approval._chat_id", return_value="")
    @patch("tools.lib.telegram_image_approval._bot_token", return_value="tok")
    def test_no_chat_id(self, mock_token, mock_chat):
        mid = _send_media_group(self.entries)
        self.assertIsNone(mid)


# ---------------------------------------------------------------------------
# Test: _send_approval_buttons
# ---------------------------------------------------------------------------

class TestSendApprovalButtons(unittest.TestCase):
    @patch("tools.lib.telegram_image_approval._chat_id", return_value="999")
    @patch("tools.lib.telegram_image_approval._api_call")
    def test_send_success(self, mock_api, _):
        mock_api.return_value = {
            "ok": True,
            "result": {"message_id": 101},
        }
        mid = _send_approval_buttons("Summary", "ia:img:abc:approve", "ia:img:abc:reject")
        self.assertEqual(mid, 101)

        payload = mock_api.call_args[0][1]
        self.assertEqual(payload["chat_id"], "999")
        kb = payload["reply_markup"]["inline_keyboard"]
        self.assertEqual(kb[0][0]["text"], "✅ Aprovar tudo")
        self.assertEqual(kb[0][1]["text"], "❌ Rejeitar")

    @patch("tools.lib.telegram_image_approval._chat_id", return_value="")
    def test_no_chat_id(self, _):
        mid = _send_approval_buttons("Summary", "a", "r")
        self.assertIsNone(mid)


# ---------------------------------------------------------------------------
# Test: _parse_rejected_labels
# ---------------------------------------------------------------------------

class TestParseRejectedLabels(unittest.TestCase):
    def test_space_separated(self):
        valid = {"01_hero", "02_usage1", "03_detail"}
        result = _parse_rejected_labels("01_hero 03_detail", valid)
        self.assertEqual(result, ["01_hero", "03_detail"])

    def test_comma_separated(self):
        valid = {"01_hero", "02_usage1"}
        result = _parse_rejected_labels("01_hero, 02_usage1", valid)
        self.assertEqual(result, ["01_hero", "02_usage1"])

    def test_all_keyword(self):
        valid = {"01_hero", "02_usage1"}
        result = _parse_rejected_labels("all", valid)
        self.assertEqual(result, ["01_hero", "02_usage1"])

    def test_todos_keyword(self):
        valid = {"01_hero", "02_usage1"}
        result = _parse_rejected_labels("todos", valid)
        self.assertEqual(result, ["01_hero", "02_usage1"])

    def test_tudo_keyword(self):
        valid = {"01_hero"}
        result = _parse_rejected_labels("tudo", valid)
        self.assertEqual(result, ["01_hero"])

    def test_case_insensitive(self):
        valid = {"01_Hero"}
        result = _parse_rejected_labels("01_hero", valid)
        self.assertEqual(result, ["01_Hero"])

    def test_invalid_labels_ignored(self):
        valid = {"01_hero", "02_usage1"}
        result = _parse_rejected_labels("01_hero garbage 99_nope", valid)
        self.assertEqual(result, ["01_hero"])

    def test_empty_text(self):
        result = _parse_rejected_labels("", {"01_hero"})
        self.assertEqual(result, [])

    def test_duplicates_removed(self):
        valid = {"01_hero"}
        result = _parse_rejected_labels("01_hero 01_hero", valid)
        self.assertEqual(result, ["01_hero"])


# ---------------------------------------------------------------------------
# Test: Skip modes
# ---------------------------------------------------------------------------

class TestSkipModes(unittest.TestCase):
    def setUp(self):
        self.entries, self.paths = _make_entries(2)

    def tearDown(self):
        _cleanup_paths(self.paths)

    def test_skip_true(self):
        result = request_image_approval(self.entries, skip=True)
        self.assertTrue(result.all_approved)
        self.assertEqual(len(result.approved), 2)
        self.assertEqual(len(result.rejected), 0)

    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": "1"})
    def test_env_skip(self):
        result = request_image_approval(self.entries)
        self.assertTrue(result.all_approved)

    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": "0"})
    def test_env_not_skip_when_zero(self):
        # PIPELINE_NO_APPROVAL=0 should NOT skip — falls through to not-configured
        result = request_image_approval(self.entries)
        self.assertTrue(result.all_approved)  # auto-approve (Telegram not configured)

    def test_empty_images(self):
        result = request_image_approval([])
        self.assertTrue(result.all_approved)
        self.assertEqual(result.approved, [])


# ---------------------------------------------------------------------------
# Test: Not configured
# ---------------------------------------------------------------------------

class TestNotConfigured(unittest.TestCase):
    def setUp(self):
        self.entries, self.paths = _make_entries(2)

    def tearDown(self):
        _cleanup_paths(self.paths)

    @patch.dict(os.environ, {}, clear=True)
    def test_no_token_auto_approves(self):
        result = request_image_approval(self.entries)
        self.assertTrue(result.all_approved)

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": ""})
    def test_no_chat_id_auto_approves(self):
        result = request_image_approval(self.entries)
        self.assertTrue(result.all_approved)

    @patch("tools.lib.telegram_image_approval.send_telegram")
    @patch("tools.lib.telegram_image_approval.send_telegram_media", return_value=True)
    @patch("tools.lib.telegram_image_approval._openclaw_channel_ready", return_value=True)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=False)
    @patch.dict(os.environ, {}, clear=True)
    def test_channel_fallback_sends_images_and_auto_approves(
        self,
        _mock_cfg,
        _mock_channel,
        mock_send_media,
        mock_send_text,
    ):
        result = request_image_approval(self.entries, video_id="v001")
        self.assertTrue(result.all_approved)
        self.assertEqual(mock_send_media.call_count, len(self.entries))
        mock_send_text.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Approve All flow
# ---------------------------------------------------------------------------

class TestApproveAll(unittest.TestCase):
    def setUp(self):
        self.entries, self.paths = _make_entries(3)

    def tearDown(self):
        _cleanup_paths(self.paths)

    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=("approve", 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=100)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_full_approve(self, mock_cfg, mock_flush, mock_group, mock_btn, mock_poll, mock_edit):
        result = request_image_approval(self.entries, video_id="v001")
        self.assertTrue(result.all_approved)
        self.assertEqual(len(result.approved), 3)
        self.assertEqual(len(result.rejected), 0)

        mock_group.assert_called_once()
        mock_btn.assert_called_once()
        mock_poll.assert_called_once()
        edit_text = mock_edit.call_args[0][1]
        self.assertIn("ALL APPROVED", edit_text)


# ---------------------------------------------------------------------------
# Test: Reject Some flow
# ---------------------------------------------------------------------------

class TestRejectSome(unittest.TestCase):
    def setUp(self):
        self.entries, self.paths = _make_entries(3)

    def tearDown(self):
        _cleanup_paths(self.paths)

    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_text_reply", return_value="01_hero 03_hero")
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=("reject", 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=100)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_reject_specific(self, mock_cfg, mock_flush, mock_group, mock_btn, mock_poll_cb, mock_poll_txt, mock_edit):
        result = request_image_approval(self.entries, video_id="v001")
        self.assertFalse(result.all_approved)
        self.assertIn("01_hero", result.rejected)
        self.assertIn("03_hero", result.rejected)
        self.assertIn("02_hero", result.approved)

    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_text_reply", return_value=None)
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=("reject", 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=100)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_reject_no_reply_rejects_all(self, mock_cfg, mock_flush, mock_group, mock_btn, mock_poll_cb, mock_poll_txt, mock_edit):
        """If user clicks Reject but sends no labels → reject all."""
        result = request_image_approval(self.entries, video_id="v001")
        self.assertFalse(result.all_approved)
        self.assertEqual(len(result.rejected), 3)

    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_text_reply", return_value="all")
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=("reject", 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=100)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_reject_all_keyword(self, mock_cfg, mock_flush, mock_group, mock_btn, mock_poll_cb, mock_poll_txt, mock_edit):
        result = request_image_approval(self.entries, video_id="v001")
        self.assertFalse(result.all_approved)
        self.assertEqual(len(result.rejected), 3)

    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_text_reply", return_value="garbage nonsense")
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=("reject", 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=100)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_reject_invalid_labels_rejects_all(self, mock_cfg, mock_flush, mock_group, mock_btn, mock_poll_cb, mock_poll_txt, mock_edit):
        """Invalid labels → reject all (conservative)."""
        result = request_image_approval(self.entries, video_id="v001")
        self.assertFalse(result.all_approved)
        self.assertEqual(len(result.rejected), 3)


# ---------------------------------------------------------------------------
# Test: Timeout
# ---------------------------------------------------------------------------

class TestTimeout(unittest.TestCase):
    def setUp(self):
        self.entries, self.paths = _make_entries(2)

    def tearDown(self):
        _cleanup_paths(self.paths)

    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=(None, 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=100)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_timeout_rejects_all(self, mock_cfg, mock_flush, mock_group, mock_btn, mock_poll, mock_edit):
        result = request_image_approval(self.entries, video_id="v001", timeout_s=1)
        self.assertFalse(result.all_approved)
        self.assertEqual(len(result.rejected), 2)
        edit_text = mock_edit.call_args[0][1]
        self.assertIn("TEMPO ESGOTADO", edit_text)


# ---------------------------------------------------------------------------
# Test: Send failure → graceful degradation
# ---------------------------------------------------------------------------

class TestSendFailure(unittest.TestCase):
    def setUp(self):
        self.entries, self.paths = _make_entries(2)

    def tearDown(self):
        _cleanup_paths(self.paths)

    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=None)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=None)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=None)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_send_failure_auto_approves(self, mock_cfg, mock_flush, mock_group, mock_btn):
        result = request_image_approval(self.entries)
        self.assertTrue(result.all_approved)


# ---------------------------------------------------------------------------
# Test: Callback data format
# ---------------------------------------------------------------------------

class TestCallbackDataFormat(unittest.TestCase):
    def setUp(self):
        self.entries, self.paths = _make_entries(1)

    def tearDown(self):
        _cleanup_paths(self.paths)

    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=("approve", 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=None)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_ia_prefix(self, mock_cfg, mock_flush, mock_group, mock_btn, mock_poll, mock_edit):
        request_image_approval(self.entries)
        # Check callback data passed to _send_approval_buttons
        approve_data = mock_btn.call_args[0][1]
        reject_data = mock_btn.call_args[0][2]
        self.assertTrue(approve_data.startswith("ia:images:"))
        self.assertTrue(approve_data.endswith(":approve"))
        self.assertTrue(reject_data.startswith("ia:images:"))
        self.assertTrue(reject_data.endswith(":reject"))
        # Not pipeline_approval prefix
        self.assertFalse(approve_data.startswith("pa:"))


# ---------------------------------------------------------------------------
# Test: _poll_for_callback
# ---------------------------------------------------------------------------

class TestPollForCallback(unittest.TestCase):
    @patch("tools.lib.telegram_image_approval._answer_callback")
    @patch("tools.lib.telegram_image_approval._api_call")
    def test_approve(self, mock_api, mock_answer):
        mock_api.return_value = {
            "ok": True,
            "result": [{
                "update_id": 100,
                "callback_query": {
                    "id": "cq1",
                    "data": "ia:images:abc:approve",
                    "message": {"message_id": 50},
                },
            }],
        }
        result, offset = _poll_for_callback(50, "ia:images:abc:approve", "ia:images:abc:reject", 99, 10)
        self.assertEqual(result, "approve")
        mock_answer.assert_called_once_with("cq1", "Tudo aprovado ✅")

    @patch("tools.lib.telegram_image_approval._answer_callback")
    @patch("tools.lib.telegram_image_approval._api_call")
    def test_reject(self, mock_api, mock_answer):
        mock_api.return_value = {
            "ok": True,
            "result": [{
                "update_id": 100,
                "callback_query": {
                    "id": "cq2",
                    "data": "ia:images:abc:reject",
                    "message": {"message_id": 50},
                },
            }],
        }
        result, offset = _poll_for_callback(50, "ia:images:abc:approve", "ia:images:abc:reject", 99, 10)
        self.assertEqual(result, "reject")
        mock_answer.assert_called_once_with("cq2", "Envie os labels para rejeitar")

    @patch("tools.lib.telegram_image_approval.time")
    @patch("tools.lib.telegram_image_approval._api_call")
    def test_timeout(self, mock_api, mock_time):
        mock_time.monotonic.side_effect = [0.0, 0.0, 999.0]
        mock_api.return_value = {"ok": True, "result": []}
        result, offset = _poll_for_callback(50, "ia:img:abc:approve", "ia:img:abc:reject", 99, 5)
        self.assertIsNone(result)

    @patch("tools.lib.telegram_image_approval._answer_callback")
    @patch("tools.lib.telegram_image_approval._api_call")
    def test_wrong_message_ignored(self, mock_api, mock_answer):
        call_count = [0]

        def api_side_effect(method, payload):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 100,
                        "callback_query": {
                            "id": "cq_other",
                            "data": "ia:images:abc:approve",
                            "message": {"message_id": 999},
                        },
                    }],
                }
            elif call_count[0] == 2:
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 101,
                        "callback_query": {
                            "id": "cq_ours",
                            "data": "ia:images:abc:approve",
                            "message": {"message_id": 50},
                        },
                    }],
                }
            return {"ok": True, "result": []}

        mock_api.side_effect = api_side_effect
        result, offset = _poll_for_callback(50, "ia:images:abc:approve", "ia:images:abc:reject", 99, 30)
        self.assertEqual(result, "approve")
        mock_answer.assert_called_once_with("cq_ours", "Tudo aprovado ✅")


# ---------------------------------------------------------------------------
# Test: _poll_for_text_reply
# ---------------------------------------------------------------------------

class TestPollForTextReply(unittest.TestCase):
    @patch("tools.lib.telegram_image_approval._api_call")
    def test_receives_text(self, mock_api):
        mock_api.return_value = {
            "ok": True,
            "result": [{
                "update_id": 200,
                "message": {
                    "message_id": 60,
                    "text": "01_hero 03_detail",
                },
            }],
        }
        text = _poll_for_text_reply(199, timeout_s=10)
        self.assertEqual(text, "01_hero 03_detail")

    @patch("tools.lib.telegram_image_approval.time")
    @patch("tools.lib.telegram_image_approval._api_call")
    def test_timeout(self, mock_api, mock_time):
        mock_time.monotonic.side_effect = [0.0, 0.0, 999.0]
        mock_api.return_value = {"ok": True, "result": []}
        text = _poll_for_text_reply(199, timeout_s=5)
        self.assertIsNone(text)


# ---------------------------------------------------------------------------
# Test: Webhook management
# ---------------------------------------------------------------------------

class TestWebhookManagement(unittest.TestCase):
    @patch("tools.lib.telegram_image_approval._restore_webhook")
    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=("approve", 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=100)
    @patch("tools.lib.telegram_image_approval._drop_webhook", return_value="https://old.webhook/url")
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_webhook_restored(self, mock_cfg, mock_drop, mock_flush, mock_group, mock_btn, mock_poll, mock_edit, mock_restore):
        entries, paths = _make_entries(1)
        try:
            request_image_approval(entries, video_id="v001")
            mock_drop.assert_called_once()
            mock_restore.assert_called_once_with("https://old.webhook/url")
        finally:
            _cleanup_paths(paths)

    @patch("tools.lib.telegram_image_approval._restore_webhook")
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=None)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=None)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=None)
    @patch("tools.lib.telegram_image_approval._drop_webhook", return_value="https://old.webhook/url")
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_webhook_restored_on_failure(self, mock_cfg, mock_drop, mock_flush, mock_group, mock_btn, mock_restore):
        """Webhook is restored even when send fails."""
        entries, paths = _make_entries(1)
        try:
            request_image_approval(entries)
            mock_restore.assert_called_once_with("https://old.webhook/url")
        finally:
            _cleanup_paths(paths)


# ---------------------------------------------------------------------------
# Test: Multiple album batches (>10 images)
# ---------------------------------------------------------------------------

class TestMultipleBatches(unittest.TestCase):
    @patch("tools.lib.telegram_image_approval._edit_message_text")
    @patch("tools.lib.telegram_image_approval._poll_for_callback", return_value=("approve", 101))
    @patch("tools.lib.telegram_image_approval._send_approval_buttons", return_value=42)
    @patch("tools.lib.telegram_image_approval._send_media_group", return_value=40)
    @patch("tools.lib.telegram_image_approval._flush_updates", return_value=100)
    @patch("tools.lib.telegram_image_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_12_images_two_batches(self, mock_cfg, mock_flush, mock_group, mock_btn, mock_poll, mock_edit):
        entries, paths = _make_entries(12)
        try:
            result = request_image_approval(entries)
            self.assertTrue(result.all_approved)
            # Should be called twice: 10 + 2
            self.assertEqual(mock_group.call_count, 2)
        finally:
            _cleanup_paths(paths)


# ---------------------------------------------------------------------------
# Test: Flush updates
# ---------------------------------------------------------------------------

class TestFlushUpdates(unittest.TestCase):
    @patch("tools.lib.telegram_image_approval._api_call")
    def test_flush_with_updates(self, mock_api):
        mock_api.return_value = {
            "ok": True,
            "result": [{"update_id": 42, "message": {}}],
        }
        uid = _flush_updates()
        self.assertEqual(uid, 42)

    @patch("tools.lib.telegram_image_approval._api_call")
    def test_flush_empty(self, mock_api):
        mock_api.return_value = {"ok": True, "result": []}
        uid = _flush_updates()
        self.assertIsNone(uid)

    @patch("tools.lib.telegram_image_approval._api_call")
    def test_flush_api_failure(self, mock_api):
        mock_api.return_value = None
        uid = _flush_updates()
        self.assertIsNone(uid)


import urllib.error

if __name__ == "__main__":
    unittest.main()
