"""Tests for tools/lib/notify.py — Telegram notification formatting.

Covers: [Rayviews] prefix, Next: action presence.
No actual Telegram calls — tests formatting only.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.notify import (
    TYPE_START,
    TYPE_PROGRESS,
    TYPE_ACTION_REQUIRED,
    TYPE_ERROR,
    TYPE_HEARTBEAT,
    TYPE_SUMMARY,
    TYPE_RATE_LIMITED,
    _format_message,
)


class TestRayviewsPrefix(unittest.TestCase):
    """Every message type starts with '[Rayviews Lab]'."""

    def _assert_prefix(self, msg_type, stage="", milestone=""):
        msg = _format_message(
            msg_type, "test-001", stage, milestone,
            next_action="Do something",
        )
        self.assertTrue(
            msg.startswith("[Rayviews Lab]"),
            f"{msg_type} message doesn't start with [Rayviews Lab]: {msg[:80]}",
        )

    def test_start_prefix(self):
        self._assert_prefix(TYPE_START)

    def test_progress_prefix(self):
        self._assert_prefix(TYPE_PROGRESS, stage="research", milestone="shortlist_ready")

    def test_action_required_prefix(self):
        self._assert_prefix(TYPE_ACTION_REQUIRED, stage="verify", milestone="login needed")

    def test_error_prefix(self):
        self._assert_prefix(TYPE_ERROR, stage="rank", milestone="scoring failed")

    def test_heartbeat_prefix(self):
        self._assert_prefix(TYPE_HEARTBEAT, stage="tts")

    def test_summary_prefix(self):
        self._assert_prefix(TYPE_SUMMARY, milestone="All stages complete")

    def test_rate_limited_prefix(self):
        self._assert_prefix(TYPE_RATE_LIMITED, stage="research", milestone="Rate limited")


class TestNextActionPresent(unittest.TestCase):
    """Non-heartbeat messages include 'Next:' line."""

    def test_start_has_next(self):
        msg = _format_message(TYPE_START, "v1", "", "", next_action="Pipeline running")
        self.assertIn("Next:", msg)

    def test_progress_has_next(self):
        msg = _format_message(TYPE_PROGRESS, "v1", "research", "done", next_action="Run verify")
        self.assertIn("Next:", msg)

    def test_error_has_next(self):
        msg = _format_message(TYPE_ERROR, "v1", "verify", "fail", next_action="Retry")
        self.assertIn("Next:", msg)

    def test_summary_has_next(self):
        msg = _format_message(TYPE_SUMMARY, "v1", "", "complete", next_action="Upload")
        self.assertIn("Next:", msg)


if __name__ == "__main__":
    unittest.main()
