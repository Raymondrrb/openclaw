"""RayVault distributed agent protocol (Mac controller <-> Windows worker).

Contract goals:
- Deterministic JSON envelopes
- HMAC auth per request
- Idempotent job identity via inputs_hash

Every authenticated request must include:
  run_id, job_id, step_name, inputs_hash, timestamp, auth_token
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Dict, List

from rayvault.io import utc_now_iso

MESSAGE_TYPES = {
    "register_caps",
    "submit_job",
    "job_status",
    "job_logs",
    "job_artifacts",
}

JOB_STEPS = {
    "TTS_RENDER_CHUNKS",
    "AUDIO_POSTCHECK",
    "FFMPEG_PROBE",
    "FRAME_SAMPLING",
    "OPENCLAW_TASK",
}

CONTROL_STEPS = {
    "REGISTER_CAPS",
    "JOB_STATUS",
    "JOB_LOGS",
    "JOB_ARTIFACTS",
}

SUPPORTED_STEPS = JOB_STEPS | CONTROL_STEPS

REQUIRED_ENVELOPE_FIELDS = (
    "run_id",
    "job_id",
    "step_name",
    "inputs_hash",
    "timestamp",
)


class ProtocolError(ValueError):
    """Raised on malformed protocol payloads."""


@dataclass(frozen=True)
class Envelope:
    run_id: str
    job_id: str
    step_name: str
    inputs_hash: str
    timestamp: str
    auth_token: str = ""


@dataclass(frozen=True)
class JobArtifact:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class JobReceipt:
    run_id: str
    job_id: str
    step_name: str
    inputs_hash: str
    status: str
    exit_code: int
    started_at: str
    finished_at: str
    duration_ms: int
    worker_id: str
    artifacts: List[JobArtifact]


def _canonical_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_inputs_hash(payload: Dict[str, Any]) -> str:
    """Stable hash for idempotence checks."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def normalize_step_name(step_name: str) -> str:
    step = str(step_name or "").strip().upper()
    return step


def envelope_signing_view(data: Dict[str, Any]) -> Dict[str, Any]:
    """Select and normalize fields used for HMAC signing."""
    view = {
        "run_id": str(data.get("run_id", "")).strip(),
        "job_id": str(data.get("job_id", "")).strip(),
        "step_name": normalize_step_name(data.get("step_name", "")),
        "inputs_hash": str(data.get("inputs_hash", "")).strip(),
        "timestamp": str(data.get("timestamp", "")).strip(),
    }
    return view


def compute_auth_token(secret: str, data: Dict[str, Any]) -> str:
    if not secret:
        raise ProtocolError("Missing shared secret for auth token")
    view = envelope_signing_view(data)
    raw = _canonical_json(view).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def verify_auth_token(secret: str, data: Dict[str, Any], token: str) -> bool:
    expected = compute_auth_token(secret, data)
    got = str(token or "").strip().lower()
    if not got:
        return False
    return hmac.compare_digest(expected.lower(), got)


def parse_timestamp(ts: str) -> dt.datetime:
    v = str(ts or "").strip()
    if not v:
        raise ProtocolError("timestamp is required")
    try:
        return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError(f"invalid timestamp: {v!r}") from exc


def validate_envelope(
    data: Dict[str, Any],
    *,
    now_skew_sec: int = 300,
    allowed_steps: set[str] | None = None,
) -> Envelope:
    missing = [k for k in REQUIRED_ENVELOPE_FIELDS if not str(data.get(k, "")).strip()]
    if missing:
        raise ProtocolError(f"Missing envelope fields: {', '.join(missing)}")

    step = normalize_step_name(data["step_name"])
    valid_steps = allowed_steps or SUPPORTED_STEPS
    if step not in valid_steps:
        raise ProtocolError(
            f"Unsupported step_name={step!r}. Supported: {', '.join(sorted(valid_steps))}"
        )

    ts = parse_timestamp(str(data["timestamp"]))
    now = dt.datetime.now(dt.timezone.utc)
    delta = abs((now - ts).total_seconds())
    if delta > now_skew_sec:
        raise ProtocolError(
            f"timestamp outside allowed skew ({delta:.0f}s > {now_skew_sec}s)"
        )

    inputs_hash = str(data["inputs_hash"]).strip().lower()
    if len(inputs_hash) < 16:
        raise ProtocolError("inputs_hash too short")

    return Envelope(
        run_id=str(data["run_id"]).strip(),
        job_id=str(data["job_id"]).strip(),
        step_name=step,
        inputs_hash=inputs_hash,
        timestamp=str(data["timestamp"]).strip(),
        auth_token=str(data.get("auth_token", "")).strip(),
    )


def require_valid_auth(
    secret: str,
    data: Dict[str, Any],
    *,
    allowed_steps: set[str] | None = None,
) -> Envelope:
    env = validate_envelope(data, allowed_steps=allowed_steps)
    if not verify_auth_token(secret, data, data.get("auth_token", "")):
        raise ProtocolError("auth_token invalid")
    return env


def build_envelope(
    *,
    run_id: str,
    job_id: str,
    step_name: str,
    inputs_hash: str,
    secret: str,
    timestamp: str = "",
) -> Dict[str, str]:
    payload = {
        "run_id": run_id,
        "job_id": job_id,
        "step_name": normalize_step_name(step_name),
        "inputs_hash": inputs_hash,
        "timestamp": timestamp or utc_now_iso(),
    }
    payload["auth_token"] = compute_auth_token(secret, payload)
    return payload


def make_message(msg_type: str, envelope: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    if msg_type not in MESSAGE_TYPES:
        raise ProtocolError(f"Unsupported message type: {msg_type}")
    out = dict(envelope)
    out["message_type"] = msg_type
    out["payload"] = payload
    return out
