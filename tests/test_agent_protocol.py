#!/usr/bin/env python3
"""Tests for rayvault/agent/protocol.py — distributed agent protocol."""

from __future__ import annotations

import datetime as dt
import unittest

from rayvault.agent.protocol import (
    CONTROL_STEPS,
    JOB_STEPS,
    MESSAGE_TYPES,
    REQUIRED_ENVELOPE_FIELDS,
    SUPPORTED_STEPS,
    Envelope,
    ProtocolError,
    build_envelope,
    compute_auth_token,
    compute_inputs_hash,
    envelope_signing_view,
    make_message,
    normalize_step_name,
    parse_timestamp,
    utc_now_iso,
    validate_envelope,
    verify_auth_token,
)


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestProtocolConstants(unittest.TestCase):

    def test_job_steps_nonempty(self):
        self.assertGreater(len(JOB_STEPS), 0)

    def test_control_steps_nonempty(self):
        self.assertGreater(len(CONTROL_STEPS), 0)

    def test_supported_is_union(self):
        self.assertEqual(SUPPORTED_STEPS, JOB_STEPS | CONTROL_STEPS)

    def test_message_types_nonempty(self):
        self.assertGreater(len(MESSAGE_TYPES), 0)

    def test_required_fields(self):
        expected = {"run_id", "job_id", "step_name", "inputs_hash", "timestamp"}
        self.assertEqual(set(REQUIRED_ENVELOPE_FIELDS), expected)


# ---------------------------------------------------------------
# utc_now_iso
# ---------------------------------------------------------------

class TestUtcNowIso(unittest.TestCase):

    def test_returns_string(self):
        ts = utc_now_iso()
        self.assertIsInstance(ts, str)

    def test_ends_with_z(self):
        ts = utc_now_iso()
        self.assertTrue(ts.endswith("Z"))

    def test_parseable(self):
        ts = utc_now_iso()
        # Should parse with fromisoformat
        dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ---------------------------------------------------------------
# compute_inputs_hash
# ---------------------------------------------------------------

class TestComputeInputsHash(unittest.TestCase):

    def test_returns_hex(self):
        h = compute_inputs_hash({"key": "value"})
        self.assertEqual(len(h), 64)
        int(h, 16)

    def test_deterministic(self):
        d = {"a": 1, "b": 2}
        self.assertEqual(compute_inputs_hash(d), compute_inputs_hash(d))

    def test_key_order_independent(self):
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 2, "a": 1}
        self.assertEqual(compute_inputs_hash(d1), compute_inputs_hash(d2))

    def test_different_data(self):
        self.assertNotEqual(
            compute_inputs_hash({"a": 1}),
            compute_inputs_hash({"a": 2}),
        )


# ---------------------------------------------------------------
# normalize_step_name
# ---------------------------------------------------------------

class TestNormalizeStepName(unittest.TestCase):

    def test_uppercase(self):
        self.assertEqual(normalize_step_name("tts_render_chunks"), "TTS_RENDER_CHUNKS")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_step_name("  TTS_RENDER_CHUNKS  "), "TTS_RENDER_CHUNKS")

    def test_empty(self):
        self.assertEqual(normalize_step_name(""), "")

    def test_none_returns_empty(self):
        # None or "" → "" → "".upper() → ""
        self.assertEqual(normalize_step_name(None), "")


# ---------------------------------------------------------------
# envelope_signing_view
# ---------------------------------------------------------------

class TestEnvelopeSigningView(unittest.TestCase):

    def test_extracts_required_fields(self):
        data = {
            "run_id": "RUN_A",
            "job_id": "job_123",
            "step_name": "TTS_RENDER_CHUNKS",
            "inputs_hash": "abc123",
            "timestamp": "2026-02-14T12:00:00Z",
            "extra_field": "ignored",
        }
        view = envelope_signing_view(data)
        self.assertEqual(set(view.keys()), {"run_id", "job_id", "step_name", "inputs_hash", "timestamp"})
        self.assertNotIn("extra_field", view)

    def test_normalizes_step_name(self):
        data = {"step_name": "tts_render_chunks", "run_id": "", "job_id": "",
                "inputs_hash": "", "timestamp": ""}
        view = envelope_signing_view(data)
        self.assertEqual(view["step_name"], "TTS_RENDER_CHUNKS")

    def test_strips_whitespace(self):
        data = {"run_id": "  RUN_A  ", "job_id": " j ", "step_name": "X",
                "inputs_hash": " h ", "timestamp": " t "}
        view = envelope_signing_view(data)
        self.assertEqual(view["run_id"], "RUN_A")
        self.assertEqual(view["job_id"], "j")


# ---------------------------------------------------------------
# compute_auth_token / verify_auth_token
# ---------------------------------------------------------------

class TestAuthToken(unittest.TestCase):

    def _make_data(self):
        return {
            "run_id": "RUN_A",
            "job_id": "job_123",
            "step_name": "TTS_RENDER_CHUNKS",
            "inputs_hash": "abcdef1234567890",
            "timestamp": utc_now_iso(),
        }

    def test_compute_returns_hex(self):
        token = compute_auth_token("my_secret", self._make_data())
        self.assertEqual(len(token), 64)
        int(token, 16)

    def test_deterministic(self):
        data = self._make_data()
        t1 = compute_auth_token("my_secret", data)
        t2 = compute_auth_token("my_secret", data)
        self.assertEqual(t1, t2)

    def test_different_secret_different_token(self):
        data = self._make_data()
        t1 = compute_auth_token("secret_a", data)
        t2 = compute_auth_token("secret_b", data)
        self.assertNotEqual(t1, t2)

    def test_empty_secret_raises(self):
        with self.assertRaises(ProtocolError):
            compute_auth_token("", self._make_data())

    def test_verify_valid(self):
        data = self._make_data()
        token = compute_auth_token("my_secret", data)
        self.assertTrue(verify_auth_token("my_secret", data, token))

    def test_verify_invalid(self):
        data = self._make_data()
        self.assertFalse(verify_auth_token("my_secret", data, "0" * 64))

    def test_verify_empty_token(self):
        data = self._make_data()
        self.assertFalse(verify_auth_token("my_secret", data, ""))


# ---------------------------------------------------------------
# parse_timestamp
# ---------------------------------------------------------------

class TestParseTimestamp(unittest.TestCase):

    def test_valid_iso(self):
        ts = parse_timestamp("2026-02-14T12:00:00Z")
        self.assertIsInstance(ts, dt.datetime)

    def test_empty_raises(self):
        with self.assertRaises(ProtocolError):
            parse_timestamp("")

    def test_invalid_raises(self):
        with self.assertRaises(ProtocolError):
            parse_timestamp("not-a-date")


# ---------------------------------------------------------------
# validate_envelope
# ---------------------------------------------------------------

class TestValidateEnvelope(unittest.TestCase):

    def _make_env(self, **overrides):
        ts = utc_now_iso()
        data = {
            "run_id": "RUN_A",
            "job_id": "job_123",
            "step_name": "TTS_RENDER_CHUNKS",
            "inputs_hash": "abcdef1234567890",
            "timestamp": ts,
        }
        data.update(overrides)
        return data

    def test_valid_returns_envelope(self):
        env = validate_envelope(self._make_env())
        self.assertIsInstance(env, Envelope)
        self.assertEqual(env.run_id, "RUN_A")
        self.assertEqual(env.step_name, "TTS_RENDER_CHUNKS")

    def test_missing_run_id(self):
        with self.assertRaises(ProtocolError):
            validate_envelope(self._make_env(run_id=""))

    def test_missing_job_id(self):
        with self.assertRaises(ProtocolError):
            validate_envelope(self._make_env(job_id=""))

    def test_unsupported_step(self):
        with self.assertRaises(ProtocolError):
            validate_envelope(self._make_env(step_name="INVALID_STEP"))

    def test_custom_allowed_steps(self):
        env = validate_envelope(
            self._make_env(step_name="CUSTOM_STEP"),
            allowed_steps={"CUSTOM_STEP"},
        )
        self.assertEqual(env.step_name, "CUSTOM_STEP")

    def test_timestamp_too_old(self):
        old_ts = "2020-01-01T00:00:00Z"
        with self.assertRaises(ProtocolError):
            validate_envelope(self._make_env(timestamp=old_ts))

    def test_short_inputs_hash(self):
        with self.assertRaises(ProtocolError):
            validate_envelope(self._make_env(inputs_hash="abc"))


# ---------------------------------------------------------------
# build_envelope
# ---------------------------------------------------------------

class TestBuildEnvelope(unittest.TestCase):

    def test_builds_with_auth(self):
        env = build_envelope(
            run_id="RUN_A",
            job_id="job_123",
            step_name="TTS_RENDER_CHUNKS",
            inputs_hash="abcdef1234567890",
            secret="my_secret",
        )
        self.assertIn("auth_token", env)
        self.assertIn("run_id", env)
        self.assertEqual(env["run_id"], "RUN_A")

    def test_auth_verifiable(self):
        env = build_envelope(
            run_id="RUN_A",
            job_id="job_123",
            step_name="TTS_RENDER_CHUNKS",
            inputs_hash="abcdef1234567890",
            secret="my_secret",
        )
        self.assertTrue(verify_auth_token("my_secret", env, env["auth_token"]))

    def test_normalizes_step(self):
        env = build_envelope(
            run_id="RUN_A",
            job_id="job_123",
            step_name="tts_render_chunks",
            inputs_hash="abcdef1234567890",
            secret="my_secret",
        )
        self.assertEqual(env["step_name"], "TTS_RENDER_CHUNKS")


# ---------------------------------------------------------------
# make_message
# ---------------------------------------------------------------

class TestMakeMessage(unittest.TestCase):

    def test_valid_message(self):
        env = {"run_id": "R", "job_id": "J", "step_name": "S"}
        msg = make_message("submit_job", env, {"data": 1})
        self.assertEqual(msg["message_type"], "submit_job")
        self.assertEqual(msg["payload"], {"data": 1})
        self.assertEqual(msg["run_id"], "R")

    def test_invalid_message_type(self):
        with self.assertRaises(ProtocolError):
            make_message("invalid_type", {}, {})


# ---------------------------------------------------------------
# Envelope dataclass
# ---------------------------------------------------------------

class TestEnvelopeDataclass(unittest.TestCase):

    def test_frozen(self):
        env = Envelope(
            run_id="R", job_id="J", step_name="S",
            inputs_hash="h", timestamp="t",
        )
        with self.assertRaises(AttributeError):
            env.run_id = "modified"

    def test_default_auth_token(self):
        env = Envelope(run_id="R", job_id="J", step_name="S",
                       inputs_hash="h", timestamp="t")
        self.assertEqual(env.auth_token, "")


if __name__ == "__main__":
    unittest.main()
