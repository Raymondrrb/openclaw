#!/usr/bin/env python3
"""Tests for tools/ops_loop.py — gate_check, daily_count, DEFAULT_STEPS."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import ops_loop


# ---------------------------------------------------------------
# DEFAULT_STEPS
# ---------------------------------------------------------------

class TestDefaultSteps(unittest.TestCase):

    def test_has_10_steps(self):
        self.assertEqual(len(ops_loop.DEFAULT_STEPS), 10)

    def test_starts_with_trend_scan(self):
        self.assertEqual(ops_loop.DEFAULT_STEPS[0], "trend_scan")

    def test_ends_with_upload(self):
        self.assertEqual(ops_loop.DEFAULT_STEPS[-1], "upload")

    def test_no_duplicates(self):
        self.assertEqual(len(ops_loop.DEFAULT_STEPS), len(set(ops_loop.DEFAULT_STEPS)))


# ---------------------------------------------------------------
# daily_count (uses EVENTS file)
# ---------------------------------------------------------------

class TestDailyCount(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_events = ops_loop.EVENTS
        ops_loop.EVENTS = os.path.join(self.tmpdir, "events.jsonl")

    def tearDown(self):
        ops_loop.EVENTS = self._orig_events
        for f in Path(self.tmpdir).iterdir():
            f.unlink()
        os.rmdir(self.tmpdir)

    def test_no_events_file(self):
        self.assertEqual(ops_loop.daily_count("video_published"), 0)

    def test_empty_events_file(self):
        Path(ops_loop.EVENTS).write_text("", encoding="utf-8")
        self.assertEqual(ops_loop.daily_count("video_published"), 0)

    def test_counts_matching_type_today(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            json.dumps({"ts": f"{today}T08:00:00Z", "type": "video_published", "message": "ok"}),
            json.dumps({"ts": f"{today}T09:00:00Z", "type": "video_published", "message": "ok"}),
            json.dumps({"ts": f"{today}T10:00:00Z", "type": "short_published", "message": "ok"}),
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(ops_loop.daily_count("video_published"), 2)
        self.assertEqual(ops_loop.daily_count("short_published"), 1)

    def test_ignores_yesterday(self):
        yesterday = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).date().isoformat()
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            json.dumps({"ts": f"{yesterday}T23:00:00Z", "type": "video_published"}),
            json.dumps({"ts": f"{today}T01:00:00Z", "type": "video_published"}),
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(ops_loop.daily_count("video_published"), 1)

    def test_bad_json_line_skipped(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            "not valid json",
            json.dumps({"ts": f"{today}T10:00:00Z", "type": "video_published"}),
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(ops_loop.daily_count("video_published"), 1)

    def test_unknown_type_returns_zero(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        line = json.dumps({"ts": f"{today}T10:00:00Z", "type": "video_published"})
        Path(ops_loop.EVENTS).write_text(line + "\n", encoding="utf-8")
        self.assertEqual(ops_loop.daily_count("nonexistent_type"), 0)


# ---------------------------------------------------------------
# gate_check
# ---------------------------------------------------------------

class TestGateCheck(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_events = ops_loop.EVENTS
        ops_loop.EVENTS = os.path.join(self.tmpdir, "events.jsonl")

    def tearDown(self):
        ops_loop.EVENTS = self._orig_events
        for f in Path(self.tmpdir).iterdir():
            f.unlink()
        os.rmdir(self.tmpdir)

    def test_under_caps_passes(self):
        # No events → counts are 0 → should pass
        ok, reason = ops_loop.gate_check({"daily_video_cap": 1, "daily_shorts_cap": 3})
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_video_cap_reached(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        line = json.dumps({"ts": f"{today}T10:00:00Z", "type": "video_published"})
        Path(ops_loop.EVENTS).write_text(line + "\n", encoding="utf-8")
        ok, reason = ops_loop.gate_check({"daily_video_cap": 1, "daily_shorts_cap": 3})
        self.assertFalse(ok)
        self.assertIn("daily_video_cap", reason)

    def test_shorts_cap_reached(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            json.dumps({"ts": f"{today}T10:00:00Z", "type": "short_published"}),
            json.dumps({"ts": f"{today}T11:00:00Z", "type": "short_published"}),
            json.dumps({"ts": f"{today}T12:00:00Z", "type": "short_published"}),
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, reason = ops_loop.gate_check({"daily_video_cap": 1, "daily_shorts_cap": 3})
        self.assertFalse(ok)
        self.assertIn("daily_shorts_cap", reason)

    def test_default_caps_when_missing(self):
        # empty policies → defaults to video=1, shorts=3
        ok, reason = ops_loop.gate_check({})
        self.assertTrue(ok)

    def test_both_under_custom_caps(self):
        ok, reason = ops_loop.gate_check({"daily_video_cap": 10, "daily_shorts_cap": 20})
        self.assertTrue(ok)
        self.assertEqual(reason, "")


    def test_video_and_shorts_both_at_cap(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            json.dumps({"ts": f"{today}T08:00:00Z", "type": "video_published"}),
            json.dumps({"ts": f"{today}T09:00:00Z", "type": "short_published"}),
            json.dumps({"ts": f"{today}T10:00:00Z", "type": "short_published"}),
            json.dumps({"ts": f"{today}T11:00:00Z", "type": "short_published"}),
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, reason = ops_loop.gate_check({"daily_video_cap": 1, "daily_shorts_cap": 3})
        self.assertFalse(ok)

    def test_zero_cap_always_blocks(self):
        ok, reason = ops_loop.gate_check({"daily_video_cap": 0, "daily_shorts_cap": 3})
        self.assertFalse(ok)
        self.assertIn("daily_video_cap", reason)


# ---------------------------------------------------------------
# daily_count edge cases
# ---------------------------------------------------------------

class TestDailyCountEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_events = ops_loop.EVENTS
        ops_loop.EVENTS = os.path.join(self.tmpdir, "events.jsonl")

    def tearDown(self):
        ops_loop.EVENTS = self._orig_events
        for f in Path(self.tmpdir).iterdir():
            f.unlink()
        os.rmdir(self.tmpdir)

    def test_blank_lines_skipped(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            "",
            json.dumps({"ts": f"{today}T10:00:00Z", "type": "video_published"}),
            "",
            "",
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(ops_loop.daily_count("video_published"), 1)

    def test_many_events_same_type(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            json.dumps({"ts": f"{today}T{h:02d}:00:00Z", "type": "video_published"})
            for h in range(10)
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(ops_loop.daily_count("video_published"), 10)

    def test_missing_ts_field_skipped(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            json.dumps({"type": "video_published"}),  # no ts
            json.dumps({"ts": f"{today}T10:00:00Z", "type": "video_published"}),
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        # First line has no ts, so the date prefix won't match today
        self.assertEqual(ops_loop.daily_count("video_published"), 1)


# ---------------------------------------------------------------
# gate_check edge cases
# ---------------------------------------------------------------

class TestGateCheckEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_events = ops_loop.EVENTS
        ops_loop.EVENTS = os.path.join(self.tmpdir, "events.jsonl")

    def tearDown(self):
        ops_loop.EVENTS = self._orig_events
        for f in Path(self.tmpdir).iterdir():
            f.unlink()
        os.rmdir(self.tmpdir)

    def test_high_caps_always_pass(self):
        ok, reason = ops_loop.gate_check({"daily_video_cap": 999, "daily_shorts_cap": 999})
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_negative_cap_always_blocks(self):
        ok, reason = ops_loop.gate_check({"daily_video_cap": -1, "daily_shorts_cap": 3})
        self.assertFalse(ok)

    def test_only_shorts_cap_reached(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        lines = [
            json.dumps({"ts": f"{today}T{h:02d}:00:00Z", "type": "short_published"})
            for h in range(5)
        ]
        Path(ops_loop.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, reason = ops_loop.gate_check({"daily_video_cap": 10, "daily_shorts_cap": 3})
        self.assertFalse(ok)
        self.assertIn("daily_shorts_cap", reason)

    def test_video_cap_one_below(self):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        # 0 videos published, cap=1 → should pass
        ok, reason = ops_loop.gate_check({"daily_video_cap": 1, "daily_shorts_cap": 3})
        self.assertTrue(ok)


# ---------------------------------------------------------------
# append_event
# ---------------------------------------------------------------

class TestAppendEvent(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_events = ops_loop.EVENTS
        ops_loop.EVENTS = os.path.join(self.tmpdir, "events.jsonl")

    def tearDown(self):
        ops_loop.EVENTS = self._orig_events
        for f in Path(self.tmpdir).iterdir():
            f.unlink()
        os.rmdir(self.tmpdir)

    def test_creates_file(self):
        ops_loop.append_event("test_event", "hello")
        self.assertTrue(Path(ops_loop.EVENTS).exists())

    def test_appends_valid_jsonl(self):
        ops_loop.append_event("ev1", "first")
        ops_loop.append_event("ev2", "second")
        lines = Path(ops_loop.EVENTS).read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 2)
        ev1 = json.loads(lines[0])
        self.assertEqual(ev1["type"], "ev1")
        self.assertEqual(ev1["message"], "first")

    def test_includes_ts(self):
        ops_loop.append_event("test", "msg")
        line = Path(ops_loop.EVENTS).read_text(encoding="utf-8").strip()
        ev = json.loads(line)
        self.assertIn("ts", ev)
        self.assertTrue(ev["ts"].endswith("Z"))

    def test_includes_data(self):
        ops_loop.append_event("test", "msg", data={"key": "value"})
        line = Path(ops_loop.EVENTS).read_text(encoding="utf-8").strip()
        ev = json.loads(line)
        self.assertEqual(ev["data"]["key"], "value")

    def test_no_data_field_when_none(self):
        ops_loop.append_event("test", "msg")
        line = Path(ops_loop.EVENTS).read_text(encoding="utf-8").strip()
        ev = json.loads(line)
        self.assertNotIn("data", ev)


if __name__ == "__main__":
    unittest.main()
