#!/usr/bin/env python3
"""Tests for rayvault/verify_visibility.py — UPLOADED -> VERIFIED promotion."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rayvault.verify_visibility import (
    DOUBLE_PASS_SPACING_HOURS,
    _check_double_pass,
    _needs_double_pass,
    _parse_utc,
    utc_now_iso,
)


# ---------------------------------------------------------------
# _parse_utc
# ---------------------------------------------------------------

class TestParseUtc(unittest.TestCase):

    def test_valid(self):
        ts = _parse_utc("2026-02-14T12:00:00Z")
        self.assertGreater(ts, 0)

    def test_invalid(self):
        self.assertEqual(_parse_utc("garbage"), 0.0)

    def test_empty(self):
        self.assertEqual(_parse_utc(""), 0.0)


# ---------------------------------------------------------------
# _needs_double_pass
# ---------------------------------------------------------------

class TestNeedsDoublePass(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_no_manifest(self):
        self.assertFalse(_needs_double_pass(Path("/nonexistent")))

    def test_safe_audio(self):
        m = Path(self._tmpdir) / "00_manifest.json"
        m.write_text(json.dumps({
            "audio_proof": {"safe_audio_mode": True}
        }))
        self.assertFalse(_needs_double_pass(m))

    def test_unsafe_audio(self):
        m = Path(self._tmpdir) / "00_manifest.json"
        m.write_text(json.dumps({
            "audio_proof": {"safe_audio_mode": False}
        }))
        self.assertTrue(_needs_double_pass(m))

    def test_no_audio_proof(self):
        m = Path(self._tmpdir) / "00_manifest.json"
        m.write_text(json.dumps({"status": "READY"}))
        self.assertFalse(_needs_double_pass(m))


# ---------------------------------------------------------------
# _check_double_pass
# ---------------------------------------------------------------

class TestCheckDoublePass(unittest.TestCase):

    def test_no_passes(self):
        result = _check_double_pass({})
        self.assertFalse(result["met"])
        self.assertEqual(result["passes"], 0)

    def test_one_pass(self):
        receipt = {"verify_passes": [
            {"at_utc": "2026-02-14T12:00:00Z"},
        ]}
        result = _check_double_pass(receipt)
        self.assertFalse(result["met"])
        self.assertEqual(result["passes"], 1)

    def test_two_passes_insufficient_spacing(self):
        receipt = {"verify_passes": [
            {"at_utc": "2026-02-14T12:00:00Z"},
            {"at_utc": "2026-02-14T13:00:00Z"},  # only 1h
        ]}
        result = _check_double_pass(receipt, spacing_hours=12.0)
        self.assertFalse(result["met"])
        self.assertIsNotNone(result["next_allowed_utc"])

    def test_two_passes_sufficient_spacing(self):
        receipt = {"verify_passes": [
            {"at_utc": "2026-02-14T00:00:00Z"},
            {"at_utc": "2026-02-14T14:00:00Z"},  # 14h
        ]}
        result = _check_double_pass(receipt, spacing_hours=12.0)
        self.assertTrue(result["met"])

    def test_bad_timestamps(self):
        receipt = {"verify_passes": [
            {"at_utc": "garbage"},
            {"at_utc": "garbage2"},
        ]}
        result = _check_double_pass(receipt)
        self.assertFalse(result["met"])


# ---------------------------------------------------------------
# verify (integration with tempdir)
# ---------------------------------------------------------------

class TestVerify(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "RUN_TEST"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_receipt(self, data):
        publish = self.run_dir / "publish"
        publish.mkdir(exist_ok=True)
        (publish / "upload_receipt.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def _write_manifest(self, data):
        (self.run_dir / "00_manifest.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def test_missing_receipt(self):
        from rayvault.verify_visibility import verify
        result = verify(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "missing_receipt")

    def test_already_verified(self):
        from rayvault.verify_visibility import verify
        self._write_receipt({
            "status": "VERIFIED",
            "youtube": {"video_id": "abc123"},
        })
        result = verify(self.run_dir)
        self.assertTrue(result["ok"])
        self.assertTrue(result["already"])

    def test_missing_video_id(self):
        from rayvault.verify_visibility import verify
        self._write_receipt({"status": "UPLOADED", "youtube": {}})
        result = verify(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "missing_video_id")

    def test_manual_verify(self):
        from rayvault.verify_visibility import verify
        self._write_receipt({
            "run_id": "RUN_TEST",
            "status": "UPLOADED",
            "youtube": {"video_id": "abc123"},
            "integrity": {},
        })
        self._write_manifest({"status": "READY_FOR_RENDER"})
        result = verify(self.run_dir, manual=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["method"], "manual")
        # Check receipt was updated
        receipt = json.loads(
            (self.run_dir / "publish" / "upload_receipt.json").read_text()
        )
        self.assertEqual(receipt["status"], "VERIFIED")

    def test_no_verify_cmd(self):
        from rayvault.verify_visibility import verify
        self._write_receipt({
            "status": "UPLOADED",
            "youtube": {"video_id": "abc123"},
        })
        result = verify(self.run_dir, verify_cmd="")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "no_verify_cmd")


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_double_pass_spacing(self):
        self.assertEqual(DOUBLE_PASS_SPACING_HOURS, 12.0)


# ---------------------------------------------------------------
# _parse_utc edge cases
# ---------------------------------------------------------------

class TestParseUtcEdgeCases(unittest.TestCase):

    def test_none_returns_zero(self):
        self.assertEqual(_parse_utc(None), 0.0)

    def test_no_z_suffix(self):
        # Some timestamps may omit 'Z'
        result = _parse_utc("2026-02-14T12:00:00")
        self.assertIsInstance(result, float)

    def test_with_microseconds(self):
        result = _parse_utc("2026-02-14T12:00:00.123456Z")
        self.assertIsInstance(result, float)

    def test_numeric_input(self):
        self.assertEqual(_parse_utc(12345), 0.0)


# ---------------------------------------------------------------
# _check_double_pass edge cases
# ---------------------------------------------------------------

class TestCheckDoublePassEdgeCases(unittest.TestCase):

    def test_single_bad_timestamp(self):
        receipt = {"verify_passes": [{"at_utc": "garbage"}]}
        result = _check_double_pass(receipt)
        self.assertFalse(result["met"])
        self.assertEqual(result["passes"], 1)

    def test_three_passes_sufficient(self):
        receipt = {"verify_passes": [
            {"at_utc": "2026-02-14T00:00:00Z"},
            {"at_utc": "2026-02-14T06:00:00Z"},
            {"at_utc": "2026-02-14T14:00:00Z"},
        ]}
        result = _check_double_pass(receipt, spacing_hours=12.0)
        # Third pass is 14h after first — should meet
        self.assertTrue(result["met"])

    def test_empty_passes_list(self):
        receipt = {"verify_passes": []}
        result = _check_double_pass(receipt)
        self.assertFalse(result["met"])
        self.assertEqual(result["passes"], 0)

    def test_missing_at_utc_field(self):
        receipt = {"verify_passes": [{"status": "ok"}, {"status": "ok"}]}
        result = _check_double_pass(receipt)
        self.assertFalse(result["met"])

    def test_zero_spacing_hours(self):
        receipt = {"verify_passes": [
            {"at_utc": "2026-02-14T12:00:00Z"},
            {"at_utc": "2026-02-14T12:00:01Z"},
        ]}
        result = _check_double_pass(receipt, spacing_hours=0.0)
        self.assertTrue(result["met"])


# ---------------------------------------------------------------
# _needs_double_pass edge cases
# ---------------------------------------------------------------

class TestNeedsDoublePassEdgeCases(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_corrupt_manifest(self):
        m = Path(self._tmpdir) / "00_manifest.json"
        m.write_text("not json at all")
        result = _needs_double_pass(m)
        self.assertFalse(result)

    def test_empty_manifest(self):
        m = Path(self._tmpdir) / "00_manifest.json"
        m.write_text("{}")
        result = _needs_double_pass(m)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
