#!/usr/bin/env python3
"""Tests for rayvault/audio_postcheck.py — result dataclasses and constants."""

from __future__ import annotations

import unittest

from rayvault.audio_postcheck import (
    BalanceResult,
    BreathCheckResult,
    ClippingResult,
    DuckingLintResult,
    LoudnessResult,
    PostcheckResult,
    VADResult,
    VADWindow,
)


# ---------------------------------------------------------------
# LoudnessResult
# ---------------------------------------------------------------

class TestLoudnessResult(unittest.TestCase):

    def test_defaults(self):
        r = LoudnessResult()
        self.assertEqual(r.integrated_lufs, 0.0)
        self.assertEqual(r.true_peak_db, 0.0)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "")

    def test_ok(self):
        r = LoudnessResult(integrated_lufs=-14.0, true_peak_db=-1.5, ok=True)
        self.assertTrue(r.ok)
        self.assertEqual(r.integrated_lufs, -14.0)


# ---------------------------------------------------------------
# BalanceResult
# ---------------------------------------------------------------

class TestBalanceResult(unittest.TestCase):

    def test_defaults(self):
        r = BalanceResult()
        self.assertTrue(r.ok)
        self.assertIsNone(r.vo_dominant_lufs)
        self.assertEqual(r.warning, "")


# ---------------------------------------------------------------
# VADWindow / VADResult
# ---------------------------------------------------------------

class TestVADWindow(unittest.TestCase):

    def test_fields(self):
        w = VADWindow(start_sec=0.0, end_sec=0.5, rms_db=-20.0, has_voice=True)
        self.assertTrue(w.has_voice)
        self.assertEqual(w.start_sec, 0.0)


class TestVADResult(unittest.TestCase):

    def test_defaults(self):
        r = VADResult()
        self.assertTrue(r.ok)
        self.assertEqual(r.windows, [])
        self.assertEqual(r.voice_ratio, 0.0)
        self.assertEqual(r.noise_floor_db, -60.0)


# ---------------------------------------------------------------
# DuckingLintResult
# ---------------------------------------------------------------

class TestDuckingLintResult(unittest.TestCase):

    def test_defaults(self):
        r = DuckingLintResult()
        self.assertTrue(r.ok)
        self.assertIsNone(r.vo_presence_rms_db)
        self.assertEqual(r.warning, "")


# ---------------------------------------------------------------
# BreathCheckResult
# ---------------------------------------------------------------

class TestBreathCheckResult(unittest.TestCase):

    def test_defaults(self):
        r = BreathCheckResult()
        self.assertTrue(r.ok)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, [])


# ---------------------------------------------------------------
# ClippingResult
# ---------------------------------------------------------------

class TestClippingResult(unittest.TestCase):

    def test_defaults(self):
        r = ClippingResult()
        self.assertTrue(r.ok)
        self.assertEqual(r.clipped_regions, [])
        self.assertEqual(r.warning, "")


# ---------------------------------------------------------------
# PostcheckResult
# ---------------------------------------------------------------

class TestPostcheckResult(unittest.TestCase):

    def test_ok_to_dict(self):
        r = PostcheckResult()
        d = r.to_dict()
        self.assertTrue(d["ok"])
        self.assertEqual(d["status"], "OK")
        self.assertEqual(d["exit_code"], 0)
        self.assertEqual(d["errors"], [])
        self.assertEqual(d["warnings"], [])

    def test_errors_set_fail(self):
        r = PostcheckResult(ok=False, errors=["LOUDNESS_OUT_OF_RANGE"])
        d = r.to_dict()
        self.assertEqual(d["status"], "FAIL")
        self.assertEqual(d["exit_code"], 2)

    def test_warnings_set_warn(self):
        r = PostcheckResult(warnings=["LOW_VARIETY"])
        d = r.to_dict()
        self.assertEqual(d["status"], "WARN")
        self.assertEqual(d["exit_code"], 1)

    def test_errors_over_warnings(self):
        r = PostcheckResult(
            ok=False,
            errors=["LOUD"],
            warnings=["VARIETY"],
        )
        d = r.to_dict()
        self.assertEqual(d["status"], "FAIL")
        self.assertEqual(d["exit_code"], 2)

    def test_metrics_included(self):
        r = PostcheckResult(metrics={"lufs": -14.0})
        d = r.to_dict()
        self.assertEqual(d["metrics"]["lufs"], -14.0)


# ---------------------------------------------------------------
# PostcheckResult.to_dict — additional edge cases
# ---------------------------------------------------------------

class TestPostcheckResultEdgeCases(unittest.TestCase):

    def test_multiple_errors(self):
        r = PostcheckResult(ok=False, errors=["ERR_A", "ERR_B", "ERR_C"])
        d = r.to_dict()
        self.assertEqual(len(d["errors"]), 3)
        self.assertEqual(d["status"], "FAIL")

    def test_multiple_warnings(self):
        r = PostcheckResult(warnings=["WARN_A", "WARN_B"])
        d = r.to_dict()
        self.assertEqual(len(d["warnings"]), 2)
        self.assertEqual(d["status"], "WARN")

    def test_idempotent_to_dict(self):
        r = PostcheckResult(ok=False, errors=["E1"], warnings=["W1"])
        d1 = r.to_dict()
        d2 = r.to_dict()
        self.assertEqual(d1, d2)

    def test_empty_metrics(self):
        r = PostcheckResult(metrics={})
        d = r.to_dict()
        self.assertEqual(d["metrics"], {})

    def test_nested_metrics(self):
        r = PostcheckResult(metrics={"loudness": {"lufs": -14.0, "peak": -1.5}})
        d = r.to_dict()
        self.assertEqual(d["metrics"]["loudness"]["lufs"], -14.0)


# ---------------------------------------------------------------
# Dataclass field edge cases
# ---------------------------------------------------------------

class TestDataclassEdgeCases(unittest.TestCase):

    def test_loudness_negative_values(self):
        r = LoudnessResult(integrated_lufs=-23.0, true_peak_db=-0.1, ok=True)
        self.assertEqual(r.integrated_lufs, -23.0)
        self.assertEqual(r.true_peak_db, -0.1)

    def test_vad_window_duration(self):
        w = VADWindow(start_sec=1.5, end_sec=3.5, rms_db=-25.0, has_voice=True)
        self.assertAlmostEqual(w.end_sec - w.start_sec, 2.0)

    def test_vad_result_with_windows(self):
        windows = [
            VADWindow(start_sec=0.0, end_sec=0.5, rms_db=-20.0, has_voice=True),
            VADWindow(start_sec=0.5, end_sec=1.0, rms_db=-40.0, has_voice=False),
        ]
        r = VADResult(windows=windows, voice_ratio=0.5, noise_floor_db=-50.0)
        self.assertEqual(len(r.windows), 2)
        self.assertAlmostEqual(r.voice_ratio, 0.5)

    def test_clipping_with_regions(self):
        r = ClippingResult(ok=False, clipped_regions=[(0.5, 0.6), (2.0, 2.1)], warning="Clipping detected")
        self.assertFalse(r.ok)
        self.assertEqual(len(r.clipped_regions), 2)

    def test_breath_check_with_errors(self):
        r = BreathCheckResult(ok=False, errors=["breath_at_1.5s"], warnings=["gap_at_3.0s"])
        self.assertFalse(r.ok)
        self.assertEqual(len(r.errors), 1)
        self.assertEqual(len(r.warnings), 1)

    def test_ducking_lint_with_values(self):
        r = DuckingLintResult(ok=False, vo_presence_rms_db=-18.0, warning="Music too loud during VO")
        self.assertFalse(r.ok)
        self.assertEqual(r.vo_presence_rms_db, -18.0)

    def test_balance_with_values(self):
        r = BalanceResult(ok=False, vo_dominant_lufs=-12.0, warning="VO too loud")
        self.assertFalse(r.ok)
        self.assertEqual(r.vo_dominant_lufs, -12.0)


if __name__ == "__main__":
    unittest.main()
