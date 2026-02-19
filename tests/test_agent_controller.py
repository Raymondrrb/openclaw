#!/usr/bin/env python3
"""Tests for rayvault/agent/controller.py — cluster controller pure functions."""

from __future__ import annotations

import unittest

from rayvault.agent.controller import (
    ClusterNode,
    ControllerError,
    LEGACY_JOB_TYPE_MAP,
    MAC_ONLY_STEPS,
    RayVaultController,
    SubmitResult,
    _build_hmac_candidates,
    _extract_job_record,
    _hmac_token,
    _job_is_success,
    _legacy_job_type,
)


# ---------------------------------------------------------------
# ClusterNode
# ---------------------------------------------------------------

class TestClusterNode(unittest.TestCase):

    def test_base_url(self):
        n = ClusterNode(node_id="w1", host="192.168.1.10", port=8080)
        self.assertEqual(n.base_url, "http://192.168.1.10:8080")

    def test_defaults(self):
        n = ClusterNode(node_id="w1", host="h", port=80)
        self.assertTrue(n.enabled)
        self.assertEqual(n.role, "worker")
        self.assertEqual(n.tags, [])
        self.assertEqual(n.timeout_sec, 15)


# ---------------------------------------------------------------
# SubmitResult
# ---------------------------------------------------------------

class TestSubmitResult(unittest.TestCase):

    def test_to_dict_keys(self):
        r = SubmitResult(
            ok=True, mode="local", run_id="R", job_id="J",
            step_name="S", status="succeeded",
        )
        d = r.to_dict()
        self.assertIn("ok", d)
        self.assertIn("mode", d)
        self.assertIn("run_id", d)
        self.assertIn("status", d)
        self.assertIn("receipt_path", d)

    def test_defaults(self):
        r = SubmitResult(
            ok=True, mode="remote", run_id="R", job_id="J",
            step_name="S", status="succeeded",
        )
        self.assertEqual(r.node_id, "")
        self.assertFalse(r.idempotent)
        self.assertEqual(r.exit_code, 0)


# ---------------------------------------------------------------
# _extract_job_record
# ---------------------------------------------------------------

class TestExtractJobRecord(unittest.TestCase):

    def test_modern_format(self):
        payload = {"job": {"status": "succeeded", "job_id": "J1"}}
        record = _extract_job_record(payload)
        self.assertEqual(record["status"], "succeeded")

    def test_legacy_flat(self):
        payload = {"status": "failed", "job_id": "J1"}
        record = _extract_job_record(payload)
        self.assertEqual(record["status"], "failed")

    def test_empty(self):
        record = _extract_job_record({})
        self.assertEqual(record, {})


# ---------------------------------------------------------------
# _legacy_job_type
# ---------------------------------------------------------------

class TestLegacyJobType(unittest.TestCase):

    def test_known_mapping(self):
        self.assertEqual(_legacy_job_type("TTS_RENDER_CHUNKS"), "tts_render_chunks")
        self.assertEqual(_legacy_job_type("AUDIO_POSTCHECK"), "audio_postcheck")

    def test_unknown_lowercases(self):
        self.assertEqual(_legacy_job_type("CUSTOM_STEP"), "custom_step")


# ---------------------------------------------------------------
# _job_is_success
# ---------------------------------------------------------------

class TestJobIsSuccess(unittest.TestCase):

    def test_succeeded(self):
        self.assertTrue(_job_is_success({"status": "succeeded"}))

    def test_failed(self):
        self.assertFalse(_job_is_success({"status": "failed"}))

    def test_error(self):
        self.assertFalse(_job_is_success({"status": "error"}))

    def test_cancelled(self):
        self.assertFalse(_job_is_success({"status": "cancelled"}))

    def test_completed_no_error(self):
        self.assertTrue(_job_is_success({"status": "completed"}))

    def test_completed_with_error(self):
        self.assertFalse(_job_is_success({"status": "completed", "error": "boom"}))

    def test_completed_result_failed(self):
        self.assertFalse(_job_is_success({
            "status": "completed",
            "result": {"status": "failed"},
        }))

    def test_unknown_status(self):
        self.assertFalse(_job_is_success({"status": "pending"}))


# ---------------------------------------------------------------
# _build_hmac_candidates
# ---------------------------------------------------------------

class TestBuildHmacCandidates(unittest.TestCase):

    def test_full_body(self):
        body = {
            "run_id": "R",
            "job_id": "J",
            "step_name": "S",
            "job_type": "tts_render_chunks",
        }
        candidates = _build_hmac_candidates(body)
        self.assertGreater(len(candidates), 0)
        # Should include job_type as first candidate
        self.assertEqual(candidates[0], "tts_render_chunks")

    def test_auth_token_excluded(self):
        body = {
            "run_id": "R",
            "job_type": "test",
            "auth_token": "should_be_excluded",
        }
        candidates = _build_hmac_candidates(body)
        for c in candidates:
            self.assertNotIn("should_be_excluded", c)

    def test_empty_body(self):
        candidates = _build_hmac_candidates({})
        self.assertEqual(candidates, [])


# ---------------------------------------------------------------
# _hmac_token
# ---------------------------------------------------------------

class TestHmacToken(unittest.TestCase):

    def test_deterministic(self):
        t1 = _hmac_token("secret", "message")
        t2 = _hmac_token("secret", "message")
        self.assertEqual(t1, t2)

    def test_hex_length(self):
        t = _hmac_token("secret", "message")
        self.assertEqual(len(t), 64)

    def test_different_secrets(self):
        t1 = _hmac_token("secret_a", "message")
        t2 = _hmac_token("secret_b", "message")
        self.assertNotEqual(t1, t2)

    def test_different_messages(self):
        t1 = _hmac_token("secret", "msg_a")
        t2 = _hmac_token("secret", "msg_b")
        self.assertNotEqual(t1, t2)


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestControllerConstants(unittest.TestCase):

    def test_mac_only_steps(self):
        self.assertIn("DAVINCI_RENDER_FINAL", MAC_ONLY_STEPS)
        self.assertIn("DAVINCI_RENDER", MAC_ONLY_STEPS)

    def test_legacy_map_nonempty(self):
        self.assertGreater(len(LEGACY_JOB_TYPE_MAP), 0)

    def test_controller_error_is_runtime(self):
        with self.assertRaises(RuntimeError):
            raise ControllerError("test")


class TestRequirementMatching(unittest.TestCase):
    def _make_ctrl_with_caps(self, caps):
        ctrl = RayVaultController.__new__(RayVaultController)
        ctrl._caps_cache = {}
        ctrl._cached_caps = lambda _node: {"capabilities": caps}
        return ctrl

    def test_worker_meets_requirements(self):
        node = ClusterNode(node_id="w1", host="127.0.0.1", port=8787)
        ctrl = self._make_ctrl_with_caps(
            {
                "os": "windows",
                "ram_gb": 16,
                "vram_gb": 8,
                "gpu": True,
                "davinci_available": True,
            }
        )
        ok, reason = ctrl._worker_meets_requirements(
            node,
            {"os_in": ["windows"], "min_ram_gb": 8, "gpu_required": True, "davinci_available": True},
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_worker_rejects_on_ram(self):
        node = ClusterNode(node_id="w1", host="127.0.0.1", port=8787)
        ctrl = self._make_ctrl_with_caps({"os": "windows", "ram_gb": 4, "vram_gb": 0, "gpu": False})
        ok, reason = ctrl._worker_meets_requirements(node, {"min_ram_gb": 8})
        self.assertFalse(ok)
        self.assertIn("min_ram_gb", reason)


if __name__ == "__main__":
    unittest.main()
