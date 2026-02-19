"""Tests for tools/lib/pipeline_approval.py.

Covers: skip modes, degradation, flush, send, poll, full integration.
All Telegram API calls are mocked — no network required.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch, call

_repo = os.path.join(os.path.dirname(__file__), "..")
if _repo not in sys.path:
    sys.path.insert(0, _repo)

from tools.lib.pipeline_approval import (
    _bot_token,
    _chat_id,
    _is_configured,
    _flush_updates,
    _send_approval_message,
    _poll_for_response,
    _answer_callback,
    _edit_message_text,
    request_approval,
)


class TestHelpers(unittest.TestCase):
    """Test _bot_token, _chat_id, _is_configured."""

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


class TestApprovalSkip(unittest.TestCase):
    """Skip modes: skip=True and PIPELINE_NO_APPROVAL=1."""

    def test_skip_true(self):
        result = request_approval("test", "summary", ["detail"], skip=True)
        self.assertTrue(result)

    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": "1"})
    def test_env_skip(self):
        result = request_approval("test", "summary", ["detail"])
        self.assertTrue(result)

    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": "0"})
    def test_env_not_skip_when_zero(self):
        # PIPELINE_NO_APPROVAL=0 should NOT skip — needs Telegram config
        # Without config → auto-approve via "not configured" path
        result = request_approval("test", "summary", ["detail"])
        self.assertTrue(result)  # auto-approve because Telegram not configured


class TestApprovalNotConfigured(unittest.TestCase):
    """Without Telegram credentials, auto-approve with warning."""

    @patch.dict(os.environ, {}, clear=True)
    def test_no_token_auto_approves(self):
        result = request_approval("test", "summary", ["detail"])
        self.assertTrue(result)

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": ""})
    def test_no_chat_id_auto_approves(self):
        result = request_approval("test", "summary", ["detail"])
        self.assertTrue(result)


class TestFlushUpdates(unittest.TestCase):
    """Test _flush_updates."""

    @patch("tools.lib.pipeline_approval._api_call")
    def test_flush_with_updates(self, mock_api):
        mock_api.return_value = {
            "ok": True,
            "result": [{"update_id": 42, "message": {}}],
        }
        uid = _flush_updates()
        self.assertEqual(uid, 42)
        mock_api.assert_called_once_with("getUpdates", {"offset": -1, "limit": 1, "timeout": 0})

    @patch("tools.lib.pipeline_approval._api_call")
    def test_flush_empty(self, mock_api):
        mock_api.return_value = {"ok": True, "result": []}
        uid = _flush_updates()
        self.assertIsNone(uid)

    @patch("tools.lib.pipeline_approval._api_call")
    def test_flush_api_failure(self, mock_api):
        mock_api.return_value = None
        uid = _flush_updates()
        self.assertIsNone(uid)


class TestSendApprovalMessage(unittest.TestCase):
    """Test _send_approval_message."""

    @patch("tools.lib.pipeline_approval._chat_id", return_value="999")
    @patch("tools.lib.pipeline_approval._api_call")
    def test_send_success(self, mock_api, _):
        mock_api.return_value = {
            "ok": True,
            "result": {"message_id": 101, "text": "hi"},
        }
        mid = _send_approval_message("Hello", "pa:t:abc:approve", "pa:t:abc:reject")
        self.assertEqual(mid, 101)

        # Verify payload structure
        args = mock_api.call_args
        payload = args[0][1]
        self.assertEqual(payload["chat_id"], "999")
        self.assertEqual(payload["text"], "Hello")
        kb = payload["reply_markup"]["inline_keyboard"]
        self.assertEqual(len(kb), 1)
        self.assertEqual(len(kb[0]), 2)
        self.assertEqual(kb[0][0]["text"], "Approve")
        self.assertEqual(kb[0][0]["callback_data"], "pa:t:abc:approve")
        self.assertEqual(kb[0][1]["text"], "Reject")

    @patch("tools.lib.pipeline_approval._chat_id", return_value="999")
    @patch("tools.lib.pipeline_approval._api_call", return_value=None)
    def test_send_failure(self, mock_api, _):
        mid = _send_approval_message("Hello", "pa:t:abc:approve", "pa:t:abc:reject")
        self.assertIsNone(mid)

    @patch("tools.lib.pipeline_approval._chat_id", return_value="")
    def test_send_no_chat_id(self, _):
        mid = _send_approval_message("Hello", "pa:t:abc:approve", "pa:t:abc:reject")
        self.assertIsNone(mid)


class TestPollForResponse(unittest.TestCase):
    """Test _poll_for_response with various scenarios."""

    @patch("tools.lib.pipeline_approval._answer_callback")
    @patch("tools.lib.pipeline_approval._api_call")
    def test_approve(self, mock_api, mock_answer):
        mock_api.return_value = {
            "ok": True,
            "result": [{
                "update_id": 100,
                "callback_query": {
                    "id": "cq1",
                    "data": "pa:test:abc:approve",
                    "message": {"message_id": 50},
                },
            }],
        }
        result = _poll_for_response(50, "pa:test:abc:approve", "pa:test:abc:reject", 99, 10)
        self.assertEqual(result, "approve")
        mock_answer.assert_called_once_with("cq1", "Approved!")

    @patch("tools.lib.pipeline_approval._answer_callback")
    @patch("tools.lib.pipeline_approval._api_call")
    def test_reject(self, mock_api, mock_answer):
        mock_api.return_value = {
            "ok": True,
            "result": [{
                "update_id": 100,
                "callback_query": {
                    "id": "cq2",
                    "data": "pa:test:abc:reject",
                    "message": {"message_id": 50},
                },
            }],
        }
        result = _poll_for_response(50, "pa:test:abc:approve", "pa:test:abc:reject", 99, 10)
        self.assertEqual(result, "reject")
        mock_answer.assert_called_once_with("cq2", "Rejected")

    @patch("tools.lib.pipeline_approval.time")
    @patch("tools.lib.pipeline_approval._api_call")
    def test_timeout(self, mock_api, mock_time):
        # Simulate time running out after first poll
        mock_time.monotonic.side_effect = [0.0, 0.0, 999.0]
        mock_api.return_value = {"ok": True, "result": []}
        result = _poll_for_response(50, "pa:test:abc:approve", "pa:test:abc:reject", 99, 5)
        self.assertIsNone(result)

    @patch("tools.lib.pipeline_approval._answer_callback")
    @patch("tools.lib.pipeline_approval._api_call")
    def test_wrong_message_id_ignored(self, mock_api, mock_answer):
        """Updates for a different message_id are consumed but ignored."""
        call_count = [0]

        def api_side_effect(method, payload):
            call_count[0] += 1
            if call_count[0] == 1:
                # First poll: wrong message_id
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 100,
                        "callback_query": {
                            "id": "cq_other",
                            "data": "pa:test:abc:approve",
                            "message": {"message_id": 999},
                        },
                    }],
                }
            elif call_count[0] == 2:
                # Second poll: correct message_id
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 101,
                        "callback_query": {
                            "id": "cq_ours",
                            "data": "pa:test:abc:approve",
                            "message": {"message_id": 50},
                        },
                    }],
                }
            return {"ok": True, "result": []}

        mock_api.side_effect = api_side_effect
        result = _poll_for_response(50, "pa:test:abc:approve", "pa:test:abc:reject", 99, 30)
        self.assertEqual(result, "approve")
        # Only the correct callback should be answered
        mock_answer.assert_called_once_with("cq_ours", "Approved!")

    @patch("tools.lib.pipeline_approval.time")
    @patch("tools.lib.pipeline_approval._answer_callback")
    @patch("tools.lib.pipeline_approval._api_call")
    def test_network_error_retries(self, mock_api, mock_answer, mock_time):
        """Network error triggers retry with backoff, then succeeds."""
        # time.monotonic: always within deadline; time.sleep: no-op
        mock_time.monotonic.return_value = 0.0
        mock_time.sleep = lambda x: None

        call_count = [0]

        def api_side_effect(method, payload):
            call_count[0] += 1
            if call_count[0] <= 2:
                return None  # network error
            if call_count[0] == 3:
                # Success
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 100,
                        "callback_query": {
                            "id": "cq1",
                            "data": "pa:test:abc:approve",
                            "message": {"message_id": 50},
                        },
                    }],
                }
            return {"ok": True, "result": []}

        mock_api.side_effect = api_side_effect
        # Need to stop eventually — mock time to expire after success
        times = iter([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 999.0])
        mock_time.monotonic.side_effect = times

        result = _poll_for_response(50, "pa:test:abc:approve", "pa:test:abc:reject", 99, 60)
        self.assertEqual(result, "approve")


class TestEditMessageText(unittest.TestCase):
    @patch("tools.lib.pipeline_approval._chat_id", return_value="999")
    @patch("tools.lib.pipeline_approval._api_call")
    def test_edit(self, mock_api, _):
        _edit_message_text(101, "Updated text")
        mock_api.assert_called_once_with("editMessageText", {
            "chat_id": "999",
            "message_id": 101,
            "text": "Updated text",
        })

    @patch("tools.lib.pipeline_approval._chat_id", return_value="")
    @patch("tools.lib.pipeline_approval._api_call")
    def test_edit_no_chat_id(self, mock_api, _):
        _edit_message_text(101, "Updated text")
        mock_api.assert_not_called()


class TestAnswerCallback(unittest.TestCase):
    @patch("tools.lib.pipeline_approval._api_call")
    def test_answer(self, mock_api):
        _answer_callback("cq123", "Done")
        mock_api.assert_called_once_with("answerCallbackQuery", {
            "callback_query_id": "cq123",
            "text": "Done",
        })


class TestRequestApprovalIntegration(unittest.TestCase):
    """Full flow mocked end-to-end."""

    @patch("tools.lib.pipeline_approval._edit_message_text")
    @patch("tools.lib.pipeline_approval._poll_for_response", return_value="approve")
    @patch("tools.lib.pipeline_approval._send_approval_message", return_value=42)
    @patch("tools.lib.pipeline_approval._flush_updates", return_value=100)
    @patch("tools.lib.pipeline_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_full_approve(self, mock_cfg, mock_flush, mock_send, mock_poll, mock_edit):
        result = request_approval(
            "products", "Top 5 for 'speakers'", ["#1 Speaker A"],
            video_id="v001",
        )
        self.assertTrue(result)
        mock_flush.assert_called_once()
        mock_send.assert_called_once()
        mock_poll.assert_called_once()
        # Edit with APPROVED
        mock_edit.assert_called_once()
        edit_text = mock_edit.call_args[0][1]
        self.assertIn("APPROVED", edit_text)

    @patch("tools.lib.pipeline_approval._edit_message_text")
    @patch("tools.lib.pipeline_approval._poll_for_response", return_value="reject")
    @patch("tools.lib.pipeline_approval._send_approval_message", return_value=42)
    @patch("tools.lib.pipeline_approval._flush_updates", return_value=100)
    @patch("tools.lib.pipeline_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_full_reject(self, mock_cfg, mock_flush, mock_send, mock_poll, mock_edit):
        result = request_approval(
            "products", "Top 5 for 'speakers'", ["#1 Speaker A"],
            video_id="v001",
        )
        self.assertFalse(result)
        edit_text = mock_edit.call_args[0][1]
        self.assertIn("REJECTED", edit_text)

    @patch("tools.lib.pipeline_approval._edit_message_text")
    @patch("tools.lib.pipeline_approval._poll_for_response", return_value=None)
    @patch("tools.lib.pipeline_approval._send_approval_message", return_value=42)
    @patch("tools.lib.pipeline_approval._flush_updates", return_value=100)
    @patch("tools.lib.pipeline_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_full_timeout(self, mock_cfg, mock_flush, mock_send, mock_poll, mock_edit):
        result = request_approval(
            "products", "Top 5 for 'speakers'", ["#1 Speaker A"],
            video_id="v001", timeout_s=1,
        )
        self.assertFalse(result)
        edit_text = mock_edit.call_args[0][1]
        self.assertIn("TIMED OUT", edit_text)

    @patch("tools.lib.pipeline_approval._send_approval_message", return_value=None)
    @patch("tools.lib.pipeline_approval._flush_updates", return_value=None)
    @patch("tools.lib.pipeline_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_send_failure_auto_approves(self, mock_cfg, mock_flush, mock_send):
        result = request_approval("products", "Top 5", ["detail"])
        self.assertTrue(result)

    def test_details_as_string(self):
        """details can be a plain string instead of a list."""
        result = request_approval("test", "summary", "single detail line", skip=True)
        self.assertTrue(result)

    @patch("tools.lib.pipeline_approval._edit_message_text")
    @patch("tools.lib.pipeline_approval._poll_for_response", return_value="approve")
    @patch("tools.lib.pipeline_approval._send_approval_message", return_value=42)
    @patch("tools.lib.pipeline_approval._flush_updates", return_value=None)
    @patch("tools.lib.pipeline_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_no_video_id(self, mock_cfg, mock_flush, mock_send, mock_poll, mock_edit):
        """Works without video_id."""
        result = request_approval("test", "summary", ["detail"])
        self.assertTrue(result)
        # Verify the message text doesn't contain "Video:"
        send_text = mock_send.call_args[0][0]
        self.assertNotIn("Video:", send_text)

    @patch("tools.lib.pipeline_approval._edit_message_text")
    @patch("tools.lib.pipeline_approval._poll_for_response", return_value="approve")
    @patch("tools.lib.pipeline_approval._send_approval_message", return_value=42)
    @patch("tools.lib.pipeline_approval._flush_updates", return_value=None)
    @patch("tools.lib.pipeline_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_with_video_id(self, mock_cfg, mock_flush, mock_send, mock_poll, mock_edit):
        """Video ID is included in message header."""
        result = request_approval("test", "summary", ["detail"], video_id="v001")
        self.assertTrue(result)
        send_text = mock_send.call_args[0][0]
        self.assertIn("Video: v001", send_text)


class TestCallbackDataFormat(unittest.TestCase):
    """Verify callback data prefix doesn't conflict with circuit breaker."""

    @patch("tools.lib.pipeline_approval._edit_message_text")
    @patch("tools.lib.pipeline_approval._poll_for_response", return_value="approve")
    @patch("tools.lib.pipeline_approval._send_approval_message", return_value=42)
    @patch("tools.lib.pipeline_approval._flush_updates", return_value=None)
    @patch("tools.lib.pipeline_approval._is_configured", return_value=True)
    @patch.dict(os.environ, {"PIPELINE_NO_APPROVAL": ""})
    def test_callback_data_uses_pa_prefix(self, mock_cfg, mock_flush, mock_send, mock_poll, mock_edit):
        request_approval("products", "summary", ["detail"])
        approve_data = mock_send.call_args[0][1]
        reject_data = mock_send.call_args[0][2]
        self.assertTrue(approve_data.startswith("pa:products:"))
        self.assertTrue(approve_data.endswith(":approve"))
        self.assertTrue(reject_data.startswith("pa:products:"))
        self.assertTrue(reject_data.endswith(":reject"))
        # Does NOT start with circuit breaker prefixes
        for prefix in ("refetch:", "ignore:", "abort:"):
            self.assertFalse(approve_data.startswith(prefix))
            self.assertFalse(reject_data.startswith(prefix))


if __name__ == "__main__":
    unittest.main()
