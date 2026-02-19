#!/usr/bin/env python3
"""Tests for rayvault/final_validator.py — 15 gates before YouTube upload."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rayvault.final_validator import (
    GateResult,
    ValidationVerdict,
    _build_verdict,
    gate_audio_postcheck,
    gate_audio_proof,
    gate_claims_validation,
    gate_core_assets,
    gate_davinci_required,
    gate_final_video,
    gate_identity_confidence,
    gate_manifest_exists,
    gate_manifest_status,
    gate_pacing,
    gate_product_fidelity,
    gate_soundtrack_compliance,
    gate_stability_score,
    gate_visual_qc,
)


class _TmpRunDir:
    """Helper to build a minimal run directory for testing."""

    def __init__(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "RUN_TEST"
        self.run_dir.mkdir()

    def cleanup(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def write_manifest(self, data: dict):
        (self.run_dir / "00_manifest.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def write_render_config(self, data: dict):
        (self.run_dir / "05_render_config.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def create_core_assets(self):
        for name in ("01_script.txt", "02_audio.wav", "03_frame.png"):
            (self.run_dir / name).write_bytes(b"stub")

    def create_video(self, size: int = 2048):
        publish = self.run_dir / "publish"
        publish.mkdir(exist_ok=True)
        (publish / "video_final.mp4").write_bytes(b"\x00" * size)


# ---------------------------------------------------------------
# GateResult / ValidationVerdict
# ---------------------------------------------------------------

class TestGateResult(unittest.TestCase):

    def test_fields(self):
        g = GateResult("test", True, "ok")
        self.assertEqual(g.name, "test")
        self.assertTrue(g.passed)
        self.assertEqual(g.detail, "ok")


class TestValidationVerdict(unittest.TestCase):

    def test_to_dict_keys(self):
        v = ValidationVerdict(
            run_id="R", all_passed=True, gates=[], failed_gates=[]
        )
        d = v.to_dict()
        self.assertIn("run_id", d)
        self.assertIn("all_passed", d)
        self.assertIn("gates", d)
        self.assertIn("checked_at_utc", d)

    def test_patient_zero_none(self):
        v = ValidationVerdict(run_id="R", all_passed=True)
        self.assertIsNone(v.patient_zero)

    def test_to_dict_gates_format(self):
        g = GateResult("g1", True, "ok")
        v = ValidationVerdict(run_id="R", all_passed=True, gates=[g])
        d = v.to_dict()
        self.assertEqual(len(d["gates"]), 1)
        self.assertEqual(d["gates"][0]["name"], "g1")


# ---------------------------------------------------------------
# _build_verdict
# ---------------------------------------------------------------

class TestBuildVerdict(unittest.TestCase):

    def test_all_pass(self):
        gates = [GateResult("a", True, "ok"), GateResult("b", True, "ok")]
        v = _build_verdict("R", gates)
        self.assertTrue(v.all_passed)
        self.assertEqual(v.failed_gates, [])
        self.assertIsNone(v.patient_zero)

    def test_one_fail(self):
        gates = [GateResult("a", True, "ok"), GateResult("b", False, "bad")]
        v = _build_verdict("R", gates)
        self.assertFalse(v.all_passed)
        self.assertEqual(v.failed_gates, ["b"])
        self.assertEqual(v.patient_zero, "b")

    def test_multiple_fail(self):
        gates = [GateResult("a", False, "x"), GateResult("b", False, "y")]
        v = _build_verdict("R", gates)
        self.assertEqual(len(v.failed_gates), 2)
        self.assertEqual(v.patient_zero, "a")


# ---------------------------------------------------------------
# gate_manifest_exists
# ---------------------------------------------------------------

class TestGateManifestExists(unittest.TestCase):

    def setUp(self):
        self.h = _TmpRunDir()

    def tearDown(self):
        self.h.cleanup()

    def test_exists(self):
        self.h.write_manifest({"status": "READY_FOR_RENDER"})
        g = gate_manifest_exists(self.h.run_dir)
        self.assertTrue(g.passed)

    def test_missing(self):
        g = gate_manifest_exists(self.h.run_dir)
        self.assertFalse(g.passed)
        self.assertIn("missing", g.detail)


# ---------------------------------------------------------------
# gate_manifest_status
# ---------------------------------------------------------------

class TestGateManifestStatus(unittest.TestCase):

    def test_ready(self):
        g = gate_manifest_status({"status": "READY_FOR_RENDER"})
        self.assertTrue(g.passed)

    def test_wrong_status(self):
        g = gate_manifest_status({"status": "GENERATING_SCRIPT"})
        self.assertFalse(g.passed)
        self.assertIn("GENERATING_SCRIPT", g.detail)

    def test_missing_status(self):
        g = gate_manifest_status({})
        self.assertFalse(g.passed)
        self.assertIn("UNKNOWN", g.detail)


# ---------------------------------------------------------------
# gate_core_assets
# ---------------------------------------------------------------

class TestGateCoreAssets(unittest.TestCase):

    def setUp(self):
        self.h = _TmpRunDir()

    def tearDown(self):
        self.h.cleanup()

    def test_all_present(self):
        self.h.create_core_assets()
        g = gate_core_assets(self.h.run_dir)
        self.assertTrue(g.passed)

    def test_missing_script(self):
        (self.h.run_dir / "02_audio.wav").write_bytes(b"x")
        (self.h.run_dir / "03_frame.png").write_bytes(b"x")
        g = gate_core_assets(self.h.run_dir)
        self.assertFalse(g.passed)
        self.assertIn("01_script.txt", g.detail)

    def test_all_missing(self):
        g = gate_core_assets(self.h.run_dir)
        self.assertFalse(g.passed)


# ---------------------------------------------------------------
# gate_render_config
# ---------------------------------------------------------------

class TestGateRenderConfig(unittest.TestCase):

    def setUp(self):
        self.h = _TmpRunDir()

    def tearDown(self):
        self.h.cleanup()

    def test_valid(self):
        from rayvault.final_validator import gate_render_config
        self.h.write_render_config({"segments": [{"id": "seg_000"}]})
        g = gate_render_config(self.h.run_dir)
        self.assertTrue(g.passed)
        self.assertIn("1 segments", g.detail)

    def test_missing(self):
        from rayvault.final_validator import gate_render_config
        g = gate_render_config(self.h.run_dir)
        self.assertFalse(g.passed)

    def test_empty_segments(self):
        from rayvault.final_validator import gate_render_config
        self.h.write_render_config({"segments": []})
        g = gate_render_config(self.h.run_dir)
        self.assertFalse(g.passed)
        self.assertIn("no segments", g.detail)


# ---------------------------------------------------------------
# gate_identity_confidence
# ---------------------------------------------------------------

class TestGateIdentityConfidence(unittest.TestCase):

    def test_high(self):
        m = {"metadata": {"identity": {"confidence": "HIGH"}}}
        g = gate_identity_confidence(m)
        self.assertTrue(g.passed)

    def test_medium(self):
        m = {"metadata": {"identity": {"confidence": "MEDIUM"}}}
        g = gate_identity_confidence(m)
        self.assertTrue(g.passed)

    def test_low(self):
        m = {"metadata": {"identity": {"confidence": "LOW"}}}
        g = gate_identity_confidence(m)
        self.assertFalse(g.passed)

    def test_missing(self):
        g = gate_identity_confidence({})
        self.assertFalse(g.passed)
        self.assertIn("UNKNOWN", g.detail)


# ---------------------------------------------------------------
# gate_visual_qc
# ---------------------------------------------------------------

class TestGateVisualQC(unittest.TestCase):

    def test_pass(self):
        m = {"metadata": {"visual_qc_result": "PASS"}}
        g = gate_visual_qc(m)
        self.assertTrue(g.passed)

    def test_fail(self):
        m = {"metadata": {"visual_qc_result": "FAIL"}}
        g = gate_visual_qc(m)
        self.assertFalse(g.passed)

    def test_missing(self):
        g = gate_visual_qc({})
        self.assertFalse(g.passed)


# ---------------------------------------------------------------
# gate_final_video
# ---------------------------------------------------------------

class TestGateFinalVideo(unittest.TestCase):

    def setUp(self):
        self.h = _TmpRunDir()

    def tearDown(self):
        self.h.cleanup()

    def test_present(self):
        self.h.create_video(size=2048)
        g = gate_final_video(self.h.run_dir)
        self.assertTrue(g.passed)
        self.assertIn("MB", g.detail)

    def test_missing_dir(self):
        g = gate_final_video(self.h.run_dir)
        self.assertFalse(g.passed)
        self.assertIn("missing", g.detail)

    def test_too_small(self):
        publish = self.h.run_dir / "publish"
        publish.mkdir()
        (publish / "video_final.mp4").write_bytes(b"\x00" * 100)
        g = gate_final_video(self.h.run_dir)
        self.assertFalse(g.passed)


# ---------------------------------------------------------------
# gate_stability_score
# ---------------------------------------------------------------

class TestGateStabilityScore(unittest.TestCase):

    def test_above_threshold(self):
        m = {"stability": {"stability_score": 80}}
        g = gate_stability_score(m, critical_threshold=40)
        self.assertTrue(g.passed)

    def test_below_threshold(self):
        m = {"stability": {"stability_score": 20}}
        g = gate_stability_score(m, critical_threshold=40)
        self.assertFalse(g.passed)

    def test_at_threshold(self):
        m = {"stability": {"stability_score": 40}}
        g = gate_stability_score(m, critical_threshold=40)
        self.assertTrue(g.passed)

    def test_missing(self):
        g = gate_stability_score({}, critical_threshold=40)
        self.assertFalse(g.passed)


# ---------------------------------------------------------------
# gate_audio_proof
# ---------------------------------------------------------------

class TestGateAudioProof(unittest.TestCase):

    def test_no_proof_skipped(self):
        g = gate_audio_proof({})
        self.assertTrue(g.passed)
        self.assertIn("skipped", g.detail)

    def test_safe_audio(self):
        m = {"audio_proof": {
            "tts_provider": "elevenlabs",
            "has_external_music": False,
            "has_external_sfx": False,
            "script_provenance": "ai_generated",
        }}
        g = gate_audio_proof(m)
        self.assertTrue(g.passed)
        self.assertIn("safe_audio_mode=True", g.detail)
        # Check it writes back
        self.assertTrue(m["audio_proof"]["safe_audio_mode"])

    def test_unsafe_external_music(self):
        m = {"audio_proof": {
            "tts_provider": "elevenlabs",
            "has_external_music": True,
            "has_external_sfx": False,
            "script_provenance": "ai_generated",
        }}
        g = gate_audio_proof(m)
        self.assertTrue(g.passed)  # gate always passes
        self.assertIn("safe_audio_mode=False", g.detail)

    def test_unsafe_no_tts(self):
        m = {"audio_proof": {
            "tts_provider": "",
            "has_external_music": False,
            "has_external_sfx": False,
            "script_provenance": "ai_generated",
        }}
        g = gate_audio_proof(m)
        self.assertIn("safe_audio_mode=False", g.detail)


# ---------------------------------------------------------------
# gate_davinci_required
# ---------------------------------------------------------------

class TestGateDavinciRequired(unittest.TestCase):

    def test_davinci_engine(self):
        m = {"render": {"engine_used": "davinci"}}
        g = gate_davinci_required(m)
        self.assertTrue(g.passed)

    def test_ffmpeg_engine_fails(self):
        m = {"render": {"engine_used": "ffmpeg"}}
        g = gate_davinci_required(m)
        self.assertFalse(g.passed)
        self.assertIn("ffmpeg", g.detail)

    def test_no_engine(self):
        m = {"render": {}}
        g = gate_davinci_required(m)
        self.assertFalse(g.passed)

    def test_policy_disabled(self):
        m = {"render": {"davinci_required": False, "engine_used": "ffmpeg"}}
        g = gate_davinci_required(m)
        self.assertTrue(g.passed)
        self.assertIn("disabled", g.detail)


# ---------------------------------------------------------------
# gate_pacing
# ---------------------------------------------------------------

class TestGatePacing(unittest.TestCase):

    def setUp(self):
        self.h = _TmpRunDir()

    def tearDown(self):
        self.h.cleanup()

    def test_no_config_skip(self):
        g = gate_pacing(self.h.run_dir)
        self.assertTrue(g.passed)

    def test_pacing_ok(self):
        self.h.write_render_config({"pacing": {"ok": True, "warnings": []}})
        g = gate_pacing(self.h.run_dir)
        self.assertTrue(g.passed)

    def test_pacing_fail(self):
        self.h.write_render_config({
            "pacing": {"ok": False, "errors": ["LONG_STATIC_SEG"]}
        })
        g = gate_pacing(self.h.run_dir)
        self.assertFalse(g.passed)
        self.assertIn("LONG_STATIC", g.detail)

    def test_pacing_with_warnings(self):
        self.h.write_render_config({
            "pacing": {"ok": True, "warnings": ["LOW_VARIETY"]}
        })
        g = gate_pacing(self.h.run_dir)
        self.assertTrue(g.passed)
        self.assertIn("LOW_VARIETY", g.detail)


# ---------------------------------------------------------------
# gate_soundtrack_compliance
# ---------------------------------------------------------------

class TestGateSoundtrackCompliance(unittest.TestCase):

    def test_no_soundtrack_skip(self):
        g = gate_soundtrack_compliance({})
        self.assertTrue(g.passed)

    def test_green_auto_ok(self):
        m = {
            "audio": {"soundtrack": {
                "enabled": True, "license_tier": "GREEN", "publish_policy": "AUTO_PUBLISH",
            }},
            "audio_proof": {"has_external_music": True},
        }
        g = gate_soundtrack_compliance(m)
        self.assertTrue(g.passed)

    def test_red_auto_fails(self):
        m = {
            "audio": {"soundtrack": {
                "enabled": True, "license_tier": "RED", "publish_policy": "AUTO_PUBLISH",
            }},
            "audio_proof": {"has_external_music": True},
        }
        g = gate_soundtrack_compliance(m)
        self.assertFalse(g.passed)
        self.assertIn("RED", g.detail)

    def test_amber_not_blocked_fails(self):
        m = {
            "audio": {"soundtrack": {
                "enabled": True, "license_tier": "AMBER", "publish_policy": "AUTO_PUBLISH",
            }},
            "audio_proof": {"has_external_music": True},
        }
        g = gate_soundtrack_compliance(m)
        self.assertFalse(g.passed)

    def test_amber_blocked_ok(self):
        m = {
            "audio": {"soundtrack": {
                "enabled": True, "license_tier": "AMBER", "publish_policy": "BLOCKED_FOR_REVIEW",
            }},
            "audio_proof": {"has_external_music": True},
        }
        g = gate_soundtrack_compliance(m)
        self.assertTrue(g.passed)

    def test_missing_audio_proof(self):
        m = {
            "audio": {"soundtrack": {
                "enabled": True, "license_tier": "GREEN", "publish_policy": "AUTO_PUBLISH",
            }},
        }
        g = gate_soundtrack_compliance(m)
        self.assertFalse(g.passed)
        self.assertIn("has_external_music", g.detail)


# ---------------------------------------------------------------
# gate_audio_postcheck
# ---------------------------------------------------------------

class TestGateAudioPostcheck(unittest.TestCase):

    def test_missing_skip(self):
        g = gate_audio_postcheck({"render": {}})
        self.assertTrue(g.passed)

    def test_passed(self):
        m = {"render": {"audio_postcheck": {"ok": True}}}
        g = gate_audio_postcheck(m)
        self.assertTrue(g.passed)

    def test_failed(self):
        m = {"render": {"audio_postcheck": {"ok": False, "errors": ["CLIPPING"]}}}
        g = gate_audio_postcheck(m)
        self.assertFalse(g.passed)
        self.assertIn("CLIPPING", g.detail)


# ---------------------------------------------------------------
# gate_claims_validation
# ---------------------------------------------------------------

class TestGateClaimsValidation(unittest.TestCase):

    def test_not_run(self):
        g = gate_claims_validation({})
        self.assertTrue(g.passed)

    def test_pass(self):
        m = {"claims_validation": {"status": "PASS"}}
        g = gate_claims_validation(m)
        self.assertTrue(g.passed)

    def test_review_required(self):
        m = {"claims_validation": {"status": "REVIEW_REQUIRED", "violations_count": 3}}
        g = gate_claims_validation(m)
        self.assertFalse(g.passed)
        self.assertIn("3 violations", g.detail)

    def test_unknown_status(self):
        m = {"claims_validation": {"status": "UNKNOWN"}}
        g = gate_claims_validation(m)
        self.assertTrue(g.passed)


# ---------------------------------------------------------------
# gate_product_fidelity
# ---------------------------------------------------------------

class TestGateProductFidelity(unittest.TestCase):

    def setUp(self):
        self.h = _TmpRunDir()

    def tearDown(self):
        self.h.cleanup()

    def test_no_products_dir(self):
        g = gate_product_fidelity(self.h.run_dir)
        self.assertTrue(g.passed)

    def test_via_render_config(self):
        (self.h.run_dir / "products").mkdir()
        self.h.write_render_config({
            "products": {"truth_visuals_used": 5, "expected": 5}
        })
        g = gate_product_fidelity(self.h.run_dir, min_truth=4)
        self.assertTrue(g.passed)

    def test_below_min_truth(self):
        (self.h.run_dir / "products").mkdir()
        self.h.write_render_config({
            "products": {"truth_visuals_used": 2, "expected": 5}
        })
        g = gate_product_fidelity(self.h.run_dir, min_truth=4)
        self.assertFalse(g.passed)


if __name__ == "__main__":
    unittest.main()
