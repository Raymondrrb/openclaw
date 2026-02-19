#!/usr/bin/env python3
"""Tests for rayvault/amazon_quarantine.py — cooldown lock after 403/429."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rayvault.amazon_quarantine import (
    _parse_utc,
    clear_quarantine,
    is_quarantined,
    remaining_minutes,
    set_quarantine,
)


# ---------------------------------------------------------------
# _parse_utc
# ---------------------------------------------------------------

class TestParseUtc(unittest.TestCase):

    def test_valid_iso(self):
        ts = _parse_utc("2026-02-14T12:00:00Z")
        self.assertIsNotNone(ts)
        self.assertIsInstance(ts, float)

    def test_valid_iso_with_offset(self):
        ts = _parse_utc("2026-02-14T12:00:00+00:00")
        self.assertIsNotNone(ts)

    def test_invalid_returns_none(self):
        self.assertIsNone(_parse_utc("not-a-date"))

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_utc(""))


# ---------------------------------------------------------------
# is_quarantined
# ---------------------------------------------------------------

class TestIsQuarantined(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.lock = Path(self.tmpdir) / "amazon_quarantine.lock"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_lock_file(self):
        self.assertFalse(is_quarantined(self.lock))

    def test_active_quarantine(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        data = {
            "at_utc": "2026-02-14T12:00:00Z",
            "code": 429,
            "cooldown_until_utc": future.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.lock.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(is_quarantined(self.lock))

    def test_expired_quarantine(self):
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        data = {
            "at_utc": "2026-02-14T12:00:00Z",
            "code": 429,
            "cooldown_until_utc": past.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.lock.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(is_quarantined(self.lock))

    def test_fallback_to_mtime(self):
        """Lock file without cooldown_until_utc falls back to mtime."""
        data = {"at_utc": "2026-02-14T12:00:00Z", "code": 429}
        self.lock.write_text(json.dumps(data), encoding="utf-8")
        # File just created, within 4h default → active
        self.assertTrue(is_quarantined(self.lock))

    def test_corrupted_json_failsafe(self):
        self.lock.write_text("not json at all", encoding="utf-8")
        # Corrupted → fail-safe based on mtime (1h)
        result = is_quarantined(self.lock)
        self.assertTrue(result)  # File just created, within 1h


# ---------------------------------------------------------------
# set_quarantine
# ---------------------------------------------------------------

class TestSetQuarantine(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.lock = Path(self.tmpdir) / "amazon_quarantine.lock"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_lock_file(self):
        set_quarantine(self.lock, code=429)
        self.assertTrue(self.lock.exists())

    def test_lock_is_valid_json(self):
        set_quarantine(self.lock, code=429)
        data = json.loads(self.lock.read_text(encoding="utf-8"))
        self.assertIn("at_utc", data)
        self.assertIn("code", data)
        self.assertIn("cooldown_until_utc", data)

    def test_code_stored(self):
        set_quarantine(self.lock, code=403)
        data = json.loads(self.lock.read_text(encoding="utf-8"))
        self.assertEqual(data["code"], 403)

    def test_cooldown_in_future(self):
        set_quarantine(self.lock, code=429, cooldown_hours=2.0)
        data = json.loads(self.lock.read_text(encoding="utf-8"))
        until_ts = _parse_utc(data["cooldown_until_utc"])
        self.assertIsNotNone(until_ts)
        self.assertGreater(until_ts, time.time())

    def test_is_quarantined_after_set(self):
        set_quarantine(self.lock, code=429, cooldown_hours=1.0)
        self.assertTrue(is_quarantined(self.lock))

    def test_custom_note(self):
        set_quarantine(self.lock, code=429, note="rate limit hit")
        data = json.loads(self.lock.read_text(encoding="utf-8"))
        self.assertEqual(data["note"], "rate limit hit")


# ---------------------------------------------------------------
# remaining_minutes
# ---------------------------------------------------------------

class TestRemainingMinutes(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.lock = Path(self.tmpdir) / "amazon_quarantine.lock"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_lock_returns_0(self):
        self.assertEqual(remaining_minutes(self.lock), 0)

    def test_active_quarantine(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        data = {
            "cooldown_until_utc": future.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.lock.write_text(json.dumps(data), encoding="utf-8")
        mins = remaining_minutes(self.lock)
        self.assertGreater(mins, 100)
        self.assertLessEqual(mins, 120)

    def test_expired_returns_0(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        data = {
            "cooldown_until_utc": past.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.lock.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(remaining_minutes(self.lock), 0)

    def test_no_cooldown_field_returns_0(self):
        data = {"at_utc": "2026-02-14T12:00:00Z"}
        self.lock.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(remaining_minutes(self.lock), 0)


# ---------------------------------------------------------------
# clear_quarantine
# ---------------------------------------------------------------

class TestClearQuarantine(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.lock = Path(self.tmpdir) / "amazon_quarantine.lock"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_clear_existing(self):
        self.lock.write_text("{}", encoding="utf-8")
        result = clear_quarantine(self.lock)
        self.assertTrue(result)
        self.assertFalse(self.lock.exists())

    def test_clear_nonexistent(self):
        result = clear_quarantine(self.lock)
        self.assertFalse(result)

    def test_after_clear_not_quarantined(self):
        set_quarantine(self.lock, code=429)
        clear_quarantine(self.lock)
        self.assertFalse(is_quarantined(self.lock))


if __name__ == "__main__":
    unittest.main()
