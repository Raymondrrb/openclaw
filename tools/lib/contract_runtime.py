"""Contract runtime helpers for pipeline contract-first execution.

Provides:
- JSON Schema validation (draft 2020-12) with optional jsonschema package.
- Stable hashing for inputs/outputs.
- Receipt writing/validation.
- Structured JSONL step logging.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    jsonschema = None


def _json_dumps_stable(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def sha1_json(data: Any) -> str:
    return sha1_text(_json_dumps_stable(data))


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_tool_versions() -> Dict[str, str]:
    def _cmd_ver(cmd: List[str], fallback: str = "unknown") -> str:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            out = (proc.stdout or proc.stderr or "").strip().splitlines()
            if out:
                return out[0].strip()
            return fallback
        except Exception:
            return fallback

    return {
        "python": sys.version.split()[0],
        "node": _cmd_ver(["node", "-v"]),
        "ffmpeg": _cmd_ver(["ffmpeg", "-version"]),
    }


def host_fingerprint() -> Dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "pid": os.getpid(),
        "python_impl": platform.python_implementation(),
        "machine": platform.machine(),
    }


def validate_schema(
    *,
    schema_path: Path,
    data: Any,
    context: str,
) -> None:
    """Validate data against schema.

    If `jsonschema` is installed, perform full draft-2020-12 validation.
    Otherwise perform a minimal structural fallback (required + top-level type)
    so runtime stays functional even in constrained environments.
    """

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{context}: failed to load schema {schema_path}: {exc}") from exc

    if jsonschema is not None:
        try:
            jsonschema.validate(instance=data, schema=schema)
            return
        except Exception as exc:
            raise RuntimeError(f"{context}: schema validation failed: {exc}") from exc

    # Minimal fallback validator
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(data, dict):
        raise RuntimeError(f"{context}: expected object")
    if expected_type == "array" and not isinstance(data, list):
        raise RuntimeError(f"{context}: expected array")
    required = schema.get("required", [])
    if isinstance(required, list) and isinstance(data, dict):
        missing = [k for k in required if k not in data]
        if missing:
            raise RuntimeError(f"{context}: missing required keys: {', '.join(missing)}")


def collect_file_hashes(base_dir: Path, rel_paths: Iterable[str]) -> Tuple[Dict[str, str], str]:
    hashes: Dict[str, str] = {}
    for rel in rel_paths:
        p = (base_dir / rel).resolve()
        if p.exists() and p.is_file():
            hashes[rel] = sha1_file(p)
    aggregate = sha1_json(hashes)
    return hashes, aggregate


def write_jsonl(log_path: Path, event: Dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(event)
    row.setdefault("ts", dt.datetime.now(dt.timezone.utc).isoformat())
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(_json_dumps_stable(row))
        f.write("\n")


def build_receipt(
    *,
    schema_version: str,
    run_id: str,
    step_name: str,
    ok: bool,
    status: str,
    exit_code: int,
    inputs_hash: str,
    outputs_hash: str,
    started_monotonic: float,
    finished_monotonic: float,
    started_at: str,
    finished_at: str,
    artifacts: List[Dict[str, Any]],
    idempotent_skip: bool = False,
    error: Optional[BaseException] = None,
) -> Dict[str, Any]:
    receipt: Dict[str, Any] = {
        "schema_version": schema_version,
        "run_id": run_id,
        "step_name": step_name,
        "ok": ok,
        "status": status,
        "exit_code": int(exit_code),
        "idempotent_skip": bool(idempotent_skip),
        "inputs_hash": inputs_hash,
        "outputs_hash": outputs_hash,
        "timings": {
            "started_monotonic": started_monotonic,
            "finished_monotonic": finished_monotonic,
            "duration_ms": int(max(0, round((finished_monotonic - started_monotonic) * 1000))),
        },
        "tool_versions": detect_tool_versions(),
        "host": host_fingerprint(),
        "artifacts": artifacts,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    if error is not None:
        receipt["error"] = {
            "type": error.__class__.__name__,
            "message": str(error),
            "traceback_tail": traceback.format_exc().strip().splitlines()[-3:],
        }
    return receipt

