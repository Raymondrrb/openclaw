#!/usr/bin/env python3
"""Tests for rayvault/handoff_run.py — run folder + manifest creation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rayvault.handoff_run import (
    MANIFEST_SCHEMA_VERSION,
    RUN_ID_RE,
    VALID_CONFIDENCES,
    VALID_STATUSES,
    compute_stability_score,
    decide_status,
    sha1_file,
    sha1_text,
)


# ---------------------------------------------------------------
# RUN_ID_RE
# ---------------------------------------------------------------

class TestRunIdRegex(unittest.TestCase):

    def test_valid_ids(self):
        valid = [
            "RUN_2026_02_14_A",
            "RUN-test-123",
            "simple",
            "a",
            "A_B_C",
            "run-2026-02-14",
        ]
        for rid in valid:
            self.assertIsNotNone(RUN_ID_RE.match(rid), f"{rid!r} should be valid")

    def test_invalid_ids(self):
        invalid = [
            "",
            "has spaces",
            "has.dot",
            "has/slash",
            "has@at",
            "has$dollar",
        ]
        for rid in invalid:
            self.assertIsNone(RUN_ID_RE.match(rid), f"{rid!r} should be invalid")


# ---------------------------------------------------------------
# sha1_file / sha1_text
# ---------------------------------------------------------------

class TestHashing(unittest.TestCase):

    def test_sha1_file_returns_hex(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello world")
            f.flush()
            p = Path(f.name)
        try:
            h = sha1_file(p)
            self.assertEqual(len(h), 40)
            int(h, 16)
        finally:
            p.unlink()

    def test_sha1_file_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test")
            f.flush()
            p = Path(f.name)
        try:
            self.assertEqual(sha1_file(p), sha1_file(p))
        finally:
            p.unlink()

    def test_sha1_text_returns_40_hex(self):
        h = sha1_text("hello")
        self.assertEqual(len(h), 40)
        int(h, 16)

    def test_sha1_text_deterministic(self):
        self.assertEqual(sha1_text("hello"), sha1_text("hello"))


# ---------------------------------------------------------------
# compute_stability_score
# ---------------------------------------------------------------

class TestComputeStabilityScore(unittest.TestCase):

    def test_perfect_score(self):
        self.assertEqual(compute_stability_score(0, 1), 100)

    def test_fallback_1(self):
        self.assertEqual(compute_stability_score(1, 1), 75)

    def test_fallback_2(self):
        self.assertEqual(compute_stability_score(2, 1), 50)

    def test_fallback_3_is_zero(self):
        self.assertEqual(compute_stability_score(3, 1), 0)

    def test_fallback_4_is_zero(self):
        self.assertEqual(compute_stability_score(4, 1), 0)

    def test_attempts_penalty(self):
        self.assertEqual(compute_stability_score(0, 2), 92)  # 100 - 8

    def test_attempts_3(self):
        self.assertEqual(compute_stability_score(0, 3), 84)  # 100 - 16

    def test_combined(self):
        self.assertEqual(compute_stability_score(1, 2), 67)  # 100 - 25 - 8

    def test_never_negative(self):
        self.assertEqual(compute_stability_score(2, 20), 0)

    def test_never_above_100(self):
        self.assertLessEqual(compute_stability_score(0, 1), 100)


# ---------------------------------------------------------------
# decide_status
# ---------------------------------------------------------------

class TestDecideStatus(unittest.TestCase):

    def _ready_kwargs(self):
        return dict(
            visual_qc="PASS",
            identity_confidence="HIGH",
            has_script=True,
            has_audio=True,
            has_frame=True,
            has_render_config=False,
            has_products=False,
        )

    def test_ready_for_render(self):
        self.assertEqual(decide_status(**self._ready_kwargs()), "READY_FOR_RENDER")

    def test_no_script_incomplete(self):
        kw = self._ready_kwargs()
        kw["has_script"] = False
        self.assertEqual(decide_status(**kw), "INCOMPLETE")

    def test_identity_none_blocked(self):
        kw = self._ready_kwargs()
        kw["identity_confidence"] = "NONE"
        self.assertEqual(decide_status(**kw), "BLOCKED")

    def test_visual_qc_fail_blocked(self):
        kw = self._ready_kwargs()
        kw["visual_qc"] = "FAIL"
        self.assertEqual(decide_status(**kw), "BLOCKED")

    def test_products_fidelity_blocked(self):
        kw = self._ready_kwargs()
        kw["products_fidelity"] = "BLOCKED"
        self.assertEqual(decide_status(**kw), "BLOCKED")

    def test_no_audio_waiting(self):
        kw = self._ready_kwargs()
        kw["has_audio"] = False
        self.assertEqual(decide_status(**kw), "WAITING_ASSETS")

    def test_no_frame_waiting(self):
        kw = self._ready_kwargs()
        kw["has_frame"] = False
        self.assertEqual(decide_status(**kw), "WAITING_ASSETS")

    def test_visual_qc_unknown_incomplete(self):
        kw = self._ready_kwargs()
        kw["visual_qc"] = "UNKNOWN"
        self.assertEqual(decide_status(**kw), "INCOMPLETE")

    def test_products_need_render_config(self):
        kw = self._ready_kwargs()
        kw["has_products"] = True
        kw["has_render_config"] = False
        kw["products_visual_count"] = (5, 5, None)
        self.assertEqual(decide_status(**kw), "WAITING_ASSETS")

    def test_products_with_render_config_ready(self):
        kw = self._ready_kwargs()
        kw["has_products"] = True
        kw["has_render_config"] = True
        kw["products_visual_count"] = (5, 5, None)
        self.assertEqual(decide_status(**kw), "READY_FOR_RENDER")

    def test_products_insufficient_visuals(self):
        kw = self._ready_kwargs()
        kw["has_products"] = True
        kw["has_render_config"] = True
        kw["products_visual_count"] = (5, 2, "p03 no 01_main.*")
        self.assertEqual(decide_status(**kw), "WAITING_ASSETS")

    def test_products_4_of_5_ok(self):
        kw = self._ready_kwargs()
        kw["has_products"] = True
        kw["has_render_config"] = True
        kw["products_visual_count"] = (5, 4, None)
        self.assertEqual(decide_status(**kw), "READY_FOR_RENDER")


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestHandoffConstants(unittest.TestCase):

    def test_valid_statuses_nonempty(self):
        self.assertGreater(len(VALID_STATUSES), 0)
        self.assertIn("READY_FOR_RENDER", VALID_STATUSES)
        self.assertIn("BLOCKED", VALID_STATUSES)
        self.assertIn("UPLOADED", VALID_STATUSES)

    def test_valid_confidences(self):
        self.assertEqual(VALID_CONFIDENCES, {"HIGH", "MEDIUM", "LOW", "NONE"})

    def test_manifest_version(self):
        self.assertIsInstance(MANIFEST_SCHEMA_VERSION, str)
        self.assertTrue(len(MANIFEST_SCHEMA_VERSION) > 0)


if __name__ == "__main__":
    unittest.main()
