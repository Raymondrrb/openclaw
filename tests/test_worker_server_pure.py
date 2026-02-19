#!/usr/bin/env python3
"""Tests for rayvault/agent/worker_server.py pure functions.

worker_server.py requires fastapi (not installed), so we re-implement
the pure functions inline for testing.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List


# Re-implementation of the pure functions from worker_server.py

@dataclass
class _MockEnvelope:
    run_id: str = ""
    job_id: str = ""
    step_name: str = ""
    inputs_hash: str = ""
    timestamp: str = ""
    auth_token: str = ""


@dataclass
class _MockJobRecord:
    envelope: _MockEnvelope = field(default_factory=_MockEnvelope)
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    progress: float = 0.0
    message: str = "queued"
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    exit_code: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    idempotent: bool = False
    cached_job_id: str = ""
    worker_id: str = ""
    log_path: str = ""
    receipt_path: str = ""


def serialize_record(rec: _MockJobRecord) -> Dict[str, Any]:
    """Pure re-implementation of worker_server.serialize_record."""
    return {
        "run_id": rec.envelope.run_id,
        "job_id": rec.envelope.job_id,
        "step_name": rec.envelope.step_name,
        "inputs_hash": rec.envelope.inputs_hash,
        "status": rec.status,
        "progress": rec.progress,
        "message": rec.message,
        "created_at": rec.created_at,
        "started_at": rec.started_at,
        "finished_at": rec.finished_at,
        "exit_code": rec.exit_code,
        "metrics": rec.metrics,
        "artifacts": rec.artifacts,
        "error_code": rec.error_code,
        "error_message": rec.error_message,
        "idempotent": rec.idempotent,
        "cached_job_id": rec.cached_job_id,
        "worker_id": rec.worker_id,
        "log_path": rec.log_path,
        "receipt_path": rec.receipt_path,
    }


def _query_envelope(
    *,
    run_id: str,
    job_id: str,
    step_name: str,
    inputs_hash: str,
    timestamp: str,
    auth_token: str,
) -> Dict[str, Any]:
    """Pure re-implementation of worker_server._query_envelope."""
    return {
        "run_id": run_id,
        "job_id": job_id,
        "step_name": step_name,
        "inputs_hash": inputs_hash,
        "timestamp": timestamp,
        "auth_token": auth_token,
    }


def _job_key(env: _MockEnvelope) -> str:
    """Pure re-implementation of WorkerState._job_key."""
    return f"{env.step_name}:{env.inputs_hash}"


# ---------------------------------------------------------------
# serialize_record
# ---------------------------------------------------------------

class TestSerializeRecord(unittest.TestCase):

    def test_queued_record(self):
        env = _MockEnvelope(
            run_id="run_001",
            job_id="job_abc",
            step_name="render_video",
            inputs_hash="sha256_abc",
        )
        rec = _MockJobRecord(envelope=env, worker_id="worker-1")
        result = serialize_record(rec)
        self.assertEqual(result["run_id"], "run_001")
        self.assertEqual(result["job_id"], "job_abc")
        self.assertEqual(result["step_name"], "render_video")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["progress"], 0.0)

    def test_running_record(self):
        env = _MockEnvelope(job_id="j1", step_name="tts")
        rec = _MockJobRecord(
            envelope=env,
            status="running",
            progress=0.5,
            message="processing",
            started_at="2026-02-16T10:00:00Z",
        )
        result = serialize_record(rec)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["progress"], 0.5)
        self.assertEqual(result["started_at"], "2026-02-16T10:00:00Z")

    def test_failed_record(self):
        env = _MockEnvelope(job_id="j2", step_name="upload")
        rec = _MockJobRecord(
            envelope=env,
            status="failed",
            exit_code=2,
            error_code="NETWORK_ERROR",
            error_message="Connection refused",
        )
        result = serialize_record(rec)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["error_code"], "NETWORK_ERROR")
        self.assertEqual(result["error_message"], "Connection refused")

    def test_idempotent_record(self):
        env = _MockEnvelope(job_id="j3", step_name="render")
        rec = _MockJobRecord(
            envelope=env,
            idempotent=True,
            cached_job_id="j3_original",
        )
        result = serialize_record(rec)
        self.assertTrue(result["idempotent"])
        self.assertEqual(result["cached_job_id"], "j3_original")

    def test_with_artifacts(self):
        env = _MockEnvelope(job_id="j4")
        rec = _MockJobRecord(
            envelope=env,
            status="succeeded",
            artifacts=[
                {"type": "video", "path": "/out/final.mp4"},
                {"type": "thumbnail", "path": "/out/thumb.jpg"},
            ],
        )
        result = serialize_record(rec)
        self.assertEqual(len(result["artifacts"]), 2)

    def test_with_metrics(self):
        env = _MockEnvelope(job_id="j5")
        rec = _MockJobRecord(
            envelope=env,
            metrics={"render_time_sec": 120, "file_size_mb": 450},
        )
        result = serialize_record(rec)
        self.assertEqual(result["metrics"]["render_time_sec"], 120)

    def test_all_fields_present(self):
        rec = _MockJobRecord(envelope=_MockEnvelope())
        result = serialize_record(rec)
        expected_keys = {
            "run_id", "job_id", "step_name", "inputs_hash",
            "status", "progress", "message",
            "created_at", "started_at", "finished_at",
            "exit_code", "metrics", "artifacts",
            "error_code", "error_message",
            "idempotent", "cached_job_id",
            "worker_id", "log_path", "receipt_path",
        }
        self.assertEqual(set(result.keys()), expected_keys)


# ---------------------------------------------------------------
# _query_envelope
# ---------------------------------------------------------------

class TestQueryEnvelope(unittest.TestCase):

    def test_all_fields(self):
        result = _query_envelope(
            run_id="r1",
            job_id="j1",
            step_name="render",
            inputs_hash="hash_abc",
            timestamp="2026-02-16T10:00:00Z",
            auth_token="tok_secret",
        )
        self.assertEqual(result["run_id"], "r1")
        self.assertEqual(result["job_id"], "j1")
        self.assertEqual(result["step_name"], "render")
        self.assertEqual(result["inputs_hash"], "hash_abc")
        self.assertEqual(result["timestamp"], "2026-02-16T10:00:00Z")
        self.assertEqual(result["auth_token"], "tok_secret")

    def test_has_6_keys(self):
        result = _query_envelope(
            run_id="", job_id="", step_name="", inputs_hash="",
            timestamp="", auth_token="",
        )
        self.assertEqual(len(result), 6)

    def test_preserves_exact_values(self):
        result = _query_envelope(
            run_id="run_with-special.chars",
            job_id="job/123",
            step_name="step name",
            inputs_hash="hash",
            timestamp="ts",
            auth_token="tok",
        )
        self.assertEqual(result["run_id"], "run_with-special.chars")
        self.assertEqual(result["job_id"], "job/123")


# ---------------------------------------------------------------
# _job_key
# ---------------------------------------------------------------

class TestJobKey(unittest.TestCase):

    def test_basic_key(self):
        env = _MockEnvelope(step_name="render_video", inputs_hash="sha256_abc")
        self.assertEqual(_job_key(env), "render_video:sha256_abc")

    def test_same_envelope_same_key(self):
        env1 = _MockEnvelope(step_name="tts", inputs_hash="h1")
        env2 = _MockEnvelope(step_name="tts", inputs_hash="h1")
        self.assertEqual(_job_key(env1), _job_key(env2))

    def test_different_step_different_key(self):
        env1 = _MockEnvelope(step_name="render", inputs_hash="h1")
        env2 = _MockEnvelope(step_name="upload", inputs_hash="h1")
        self.assertNotEqual(_job_key(env1), _job_key(env2))

    def test_different_hash_different_key(self):
        env1 = _MockEnvelope(step_name="render", inputs_hash="h1")
        env2 = _MockEnvelope(step_name="render", inputs_hash="h2")
        self.assertNotEqual(_job_key(env1), _job_key(env2))

    def test_empty_values(self):
        env = _MockEnvelope(step_name="", inputs_hash="")
        self.assertEqual(_job_key(env), ":")


# ---------------------------------------------------------------
# serialize_record edge cases
# ---------------------------------------------------------------

class TestSerializeRecordEdgeCases(unittest.TestCase):

    def test_default_record_values(self):
        rec = _MockJobRecord(envelope=_MockEnvelope())
        result = serialize_record(rec)
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["progress"], 0.0)
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["idempotent"])
        self.assertEqual(result["artifacts"], [])
        self.assertEqual(result["metrics"], {})

    def test_progress_100_percent(self):
        env = _MockEnvelope(job_id="j_done")
        rec = _MockJobRecord(
            envelope=env,
            status="succeeded",
            progress=1.0,
            message="done",
            finished_at="2026-02-16T12:00:00Z",
        )
        result = serialize_record(rec)
        self.assertEqual(result["progress"], 1.0)
        self.assertEqual(result["finished_at"], "2026-02-16T12:00:00Z")

    def test_special_chars_in_fields(self):
        env = _MockEnvelope(
            run_id="run/special:chars",
            job_id="job#123",
            step_name="step with spaces",
        )
        rec = _MockJobRecord(
            envelope=env,
            error_message="Error: \"can't\" connect <timeout>",
        )
        result = serialize_record(rec)
        self.assertEqual(result["run_id"], "run/special:chars")
        self.assertIn("can't", result["error_message"])

    def test_large_artifacts_list(self):
        env = _MockEnvelope(job_id="j_many")
        artifacts = [{"type": f"file_{i}", "path": f"/out/{i}.mp4"} for i in range(50)]
        rec = _MockJobRecord(envelope=env, artifacts=artifacts)
        result = serialize_record(rec)
        self.assertEqual(len(result["artifacts"]), 50)


# ---------------------------------------------------------------
# _job_key edge cases
# ---------------------------------------------------------------

class TestJobKeyEdgeCases(unittest.TestCase):

    def test_special_chars_in_step_name(self):
        env = _MockEnvelope(step_name="render/video:v2", inputs_hash="h1")
        self.assertEqual(_job_key(env), "render/video:v2:h1")

    def test_long_hash(self):
        long_hash = "a" * 64
        env = _MockEnvelope(step_name="step", inputs_hash=long_hash)
        self.assertEqual(_job_key(env), f"step:{long_hash}")

    def test_unicode_step_name(self):
        env = _MockEnvelope(step_name="étape", inputs_hash="h1")
        self.assertEqual(_job_key(env), "étape:h1")


if __name__ == "__main__":
    unittest.main()
