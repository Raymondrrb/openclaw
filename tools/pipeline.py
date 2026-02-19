#!/usr/bin/env python3
"""
RayViewsLab — File-driven E2E video production pipeline.

Each step writes artifacts to pipeline_runs/{run_id}/.
The next step reads them. No agents calling agents.
OpenClaw only triggers commands. Quality > speed.

Usage:
    python3 tools/pipeline.py init-run --category desk_gadgets
    python3 tools/pipeline.py discover-products --run-id RUN_ID
    python3 tools/pipeline.py generate-script --run-id RUN_ID
    python3 tools/pipeline.py approve-gate1 --run-id RUN_ID --reviewer Ray --notes "GO"
    python3 tools/pipeline.py generate-assets --run-id RUN_ID
    python3 tools/pipeline.py generate-voice --run-id RUN_ID
    python3 tools/pipeline.py build-davinci --run-id RUN_ID
    python3 tools/pipeline.py validate-originality --run-id RUN_ID
    python3 tools/pipeline.py validate-compliance --run-id RUN_ID
    python3 tools/pipeline.py approve-gate2 --run-id RUN_ID --reviewer Ray --notes "GO"
    python3 tools/pipeline.py render-and-upload --run-id RUN_ID
    python3 tools/pipeline.py collect-metrics --run-id RUN_ID
    python3 tools/pipeline.py run-e2e --category desk_gadgets
    python3 tools/pipeline.py status --run-id RUN_ID
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
RUNS_DIR = BASE_DIR / "pipeline_runs"
CONFIG_DIR = Path(os.path.expanduser("~/.config/newproject"))

DAILY_CATEGORIES = BASE_DIR / "config" / "daily_categories.json"

CHANNEL_NAME = "RayViewsLab"
DEFAULT_VOICE = "Thomas Louis"
DEFAULT_AFFILIATE_TAG = ""  # Set when tag is configured
SCHEMA_VERSION = "1.0.0"
DISCLOSURE_INTRO_SHORT = "As an Amazon Associate I earn from qualifying purchases."
MINIMAX_ENV = CONFIG_DIR / "minimax.env"
ELEVENLABS_ENV = CONFIG_DIR / "elevenlabs.env"
SCHEMAS_DIR = BASE_DIR / "schemas"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ACTION_REQUIRED = 2

STEP_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "init-run": {
        "inputs": [],
        "outputs": ["run.json"],
    },
    "discover-products": {
        "inputs": ["run.json"],
        "outputs": ["products.json", "products.csv", "discovery_receipt.json"],
    },
    "plan-variations": {
        "inputs": ["run.json", "products.json"],
        "outputs": ["variation_plan.json"],
    },
    "generate-script": {
        "inputs": ["run.json", "products.json"],
        "outputs": ["script.json", "security/input_guard_report.json"],
    },
    "generate-assets": {
        "inputs": ["run.json", "script.json", "products.json"],
        "outputs": ["assets_manifest.json"],
    },
    "generate-voice": {
        "inputs": ["run.json", "script.json"],
        "outputs": ["voice/timestamps.json", "voice/full_narration.txt"],
    },
    "build-davinci": {
        "inputs": ["run.json", "script.json", "assets_manifest.json", "voice/timestamps.json"],
        "outputs": ["davinci/project.json"],
    },
    "convert-to-rayvault": {
        "inputs": ["run.json", "script.json", "products.json"],
        "outputs": ["rayvault/05_render_config.json", "rayvault/00_manifest.json"],
    },
    "validate-originality": {
        "inputs": ["run.json", "script.json", "products.json"],
        "outputs": ["originality_report.json"],
    },
    "validate-compliance": {
        "inputs": ["run.json", "script.json", "products.json", "assets_manifest.json", "rayvault/00_manifest.json"],
        "outputs": ["compliance_report.json", "upload/disclosure_snippets.json", "upload/pinned_comment.txt"],
    },
    "render-and-upload": {
        "inputs": ["run.json", "davinci/render_ready.flag", "davinci/project.json"],
        "outputs": ["upload/youtube_url.txt", "upload/youtube_video_id.txt"],
    },
    "collect-metrics": {
        "inputs": ["run.json", "upload/youtube_video_id.txt"],
        "outputs": ["metrics/metrics.json"],
    },
    "approve-gate1": {
        "inputs": ["run.json"],
        "outputs": ["run.json"],
    },
    "reject-gate1": {
        "inputs": ["run.json"],
        "outputs": ["run.json"],
    },
    "approve-gate2": {
        "inputs": ["run.json"],
        "outputs": ["run.json"],
    },
    "reject-gate2": {
        "inputs": ["run.json"],
        "outputs": ["run.json"],
    },
}

STEP_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    # DaVinci stages are pinned to the Mac controller by policy.
    "build-davinci": {"os_in": ["darwin"], "davinci_available": True},
    "render-and-upload": {"os_in": ["darwin"], "davinci_available": True},
}

# Local imports for script execution from project root.
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Supabase env from shared library
from video_pipeline_lib import supabase_env  # noqa: E402
from lib.contract_runtime import (
    build_receipt,
    collect_file_hashes,
    sha1_json,
    validate_schema,
    write_jsonl,
)  # noqa: E402
from lib.injection_guard import (  # noqa: E402
    sanitize_external_text,
    scan_product_inputs,
    should_block_generation,
)
from lib.ops_tier import decide_ops_tier, decision_to_dict, detect_ops_paused  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logger(run_dir: Path, step_name: str) -> logging.Logger:
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"pipeline.{step_name}")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(log_dir / f"{step_name}.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(sh)
    return logger


# ---------------------------------------------------------------------------
# Atomic file writes
# ---------------------------------------------------------------------------

def atomic_write_json(path: Path, data: Any) -> Path:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def atomic_write_text(path: Path, text: str) -> Path:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Supabase ops events
# ---------------------------------------------------------------------------


# supabase_env() imported from video_pipeline_lib (single source of truth)


def log_ops_event(run_id: str, kind: str, data: Optional[Dict] = None) -> bool:
    sb_url, sb_key = supabase_env()
    if not sb_url or not sb_key:
        return False
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    event_hash = hashlib.sha256(
        f"{run_id}:{kind}:{now_iso}:{uuid.uuid4().hex}".encode("utf-8")
    ).hexdigest()[:48]
    row = {
        "event_hash": event_hash,
        "ts": now_iso,
        "type": kind,
        "message": f"{kind} ({run_id})",
        "data": {
            "run_id": run_id,
            **(data or {}),
        },
    }
    try:
        req = Request(
            f"{sb_url.rstrip('/')}/rest/v1/ops_agent_events",
            method="POST",
            data=json.dumps([row]).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "apikey": sb_key,
                "Authorization": f"Bearer {sb_key}",
                "Prefer": "return=minimal",
            },
        )
        with urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Contract-first runtime helpers
# ---------------------------------------------------------------------------


def _schema_file(name: str) -> Path:
    return SCHEMAS_DIR / name


def _safe_step_name(step_name: str) -> str:
    return re.sub(r"[^a-z0-9_\\-]+", "_", step_name.lower()).strip("_")


def _receipt_path(run_dir: Path, step_name: str) -> Path:
    return run_dir / "receipts" / f"{_safe_step_name(step_name)}.json"


def _jsonl_log_path(run_dir: Path, step_name: str) -> Path:
    return run_dir / "logs" / f"{_safe_step_name(step_name)}.jsonl"


def _redact_sensitive(args_dict: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in args_dict.items():
        k = str(key).lower()
        if any(s in k for s in ("secret", "token", "password", "api_key", "key")):
            out[key] = "***REDACTED***" if value else ""
        else:
            out[key] = value
    return out


def _args_snapshot(args: argparse.Namespace) -> Dict[str, Any]:
    raw = {}
    for key, value in vars(args).items():
        if key == "func":
            continue
        if isinstance(value, Path):
            raw[key] = str(value)
        else:
            raw[key] = value
    return _redact_sensitive(raw)


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_run_file(run_dir: Path, context: str) -> None:
    run_json = run_dir / "run.json"
    if not run_json.exists():
        raise RuntimeError(f"{context}: missing run.json")
    data = _read_json(run_json)
    validate_schema(
        schema_path=_schema_file("run.schema.json"),
        data=data,
        context=f"{context} run.schema.json",
    )


def _required_files_exist(run_dir: Path, required_files: List[str]) -> None:
    missing = [rel for rel in required_files if not (run_dir / rel).exists()]
    if missing:
        raise RuntimeError(f"Missing required input files: {', '.join(missing)}")


def _build_job_contract(
    *,
    run_id: str,
    step_name: str,
    command_name: str,
    args: argparse.Namespace,
    required_files: List[str],
    file_hashes: Dict[str, str],
    requirements: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    job = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "step_name": step_name,
        "command": command_name,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inputs": {
            "args": _args_snapshot(args),
            "required_files": required_files,
            "file_digests": file_hashes,
        },
        "requirements": requirements or {},
        "distributed": {
            "controller_node": os.environ.get("RAYVAULT_CONTROLLER_ID", "mac-controller"),
            "preferred_worker": os.environ.get("RAYVAULT_WORKER_ID", ""),
        },
    }
    validate_schema(
        schema_path=_schema_file("job.schema.json"),
        data=job,
        context=f"{step_name} job.schema.json",
    )
    return job


def _step_requirements(command_name: str, args: argparse.Namespace) -> Dict[str, Any]:
    req = dict(STEP_REQUIREMENTS.get(command_name, {}))
    # Optional CLI/env override for distributed scheduling experiments.
    raw = str(getattr(args, "requirements_json", "") or os.environ.get("PIPELINE_REQUIREMENTS_JSON", "")).strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                req.update(parsed)
        except Exception:
            pass
    return req


def _hash_step_inputs(
    *,
    job: Dict[str, Any],
    tool_versions_hint: Optional[Dict[str, str]] = None,
) -> str:
    payload = {
        "job": job,
        "tool_versions_hint": tool_versions_hint or {"python": sys.version.split()[0]},
    }
    return sha1_json(payload)


def _hash_step_outputs(run_dir: Path, output_files: List[str]) -> Tuple[str, Dict[str, str]]:
    file_hashes, aggregate = collect_file_hashes(run_dir, output_files)
    return aggregate, file_hashes


def _receipt_is_reusable(
    *,
    run_dir: Path,
    step_name: str,
    inputs_hash: str,
    output_files: List[str],
) -> bool:
    receipt_path = _receipt_path(run_dir, step_name)
    if not receipt_path.exists():
        return False
    try:
        receipt = _read_json(receipt_path)
    except Exception:
        return False
    if receipt.get("status") != "OK":
        return False
    if receipt.get("inputs_hash") != inputs_hash:
        return False
    if any(not (run_dir / rel).exists() for rel in output_files):
        return False
    return True


def _artifact_pointers(run_dir: Path, output_files: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rel in output_files:
        p = run_dir / rel
        if p.exists() and p.is_file():
            out.append(
                {
                    "path": rel,
                    "sha1": hashlib.sha1(p.read_bytes()).hexdigest(),
                    "size_bytes": p.stat().st_size,
                }
            )
    return out


def _write_receipt_and_validate(run_dir: Path, step_name: str, receipt: Dict[str, Any]) -> None:
    validate_schema(
        schema_path=_schema_file("receipt.schema.json"),
        data=receipt,
        context=f"{step_name} receipt.schema.json",
    )
    path = _receipt_path(run_dir, step_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, receipt)


def _refresh_run_summary(run_dir: Path) -> None:
    receipts_dir = run_dir / "receipts"
    rows: List[Dict[str, Any]] = []
    if receipts_dir.exists():
        for p in sorted(receipts_dir.glob("*.json")):
            try:
                rows.append(_read_json(p))
            except Exception:
                continue
    summary = {
        "run_id": run_dir.name,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "steps": [
            {
                "step_name": r.get("step_name"),
                "status": r.get("status"),
                "ok": r.get("ok"),
                "exit_code": r.get("exit_code"),
                "duration_ms": ((r.get("timings") or {}).get("duration_ms")),
            }
            for r in rows
        ],
        "totals": {
            "steps": len(rows),
            "ok": sum(1 for r in rows if r.get("status") == "OK"),
            "warn": sum(1 for r in rows if r.get("status") == "WARN"),
            "fail": sum(1 for r in rows if r.get("status") == "FAIL"),
        },
    }
    atomic_write_json(run_dir / "run_summary.json", summary)


def _sb_request(
    *,
    method: str,
    url: str,
    key: str,
    body: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Any:
    payload = None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode("utf-8")
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v})
    req = Request(url, method=method, data=payload, headers=headers)
    with urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text.strip() else None


def _acquire_supabase_step_lock(run_id: str, step_name: str, ttl_sec: int = 1800) -> Optional[Dict[str, str]]:
    sb_url, sb_key = supabase_env()
    if not sb_url or not sb_key:
        return None
    base = sb_url.rstrip("/")
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat()
    expires_iso = (now + dt.timedelta(seconds=max(60, ttl_sec))).isoformat()
    owner = f"{os.uname().nodename}:{os.getpid()}"
    token = uuid.uuid4().hex
    row = {
        "run_id": run_id,
        "step_name": step_name,
        "owner": owner,
        "lock_token": token,
        "locked_at": now_iso,
        "expires_at": expires_iso,
        "heartbeat_at": now_iso,
    }
    run_q = quote(run_id, safe="")
    step_q = quote(step_name, safe="")
    insert_url = f"{base}/rest/v1/ops_step_locks?on_conflict=run_id,step_name"
    try:
        inserted = _sb_request(
            method="POST",
            url=insert_url,
            key=sb_key,
            body=row,
            extra_headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
        ) or []
        if isinstance(inserted, list) and inserted and inserted[0].get("lock_token") == token:
            return {"run_id": run_id, "step_name": step_name, "token": token}
        # Confirm ownership if row already existed but we inserted anyway.
        check_url = (
            f"{base}/rest/v1/ops_step_locks"
            f"?select=run_id,step_name,owner,lock_token,expires_at"
            f"&run_id=eq.{run_q}&step_name=eq.{step_q}&limit=1"
        )
        rows = _sb_request(method="GET", url=check_url, key=sb_key) or []
        if rows and rows[0].get("lock_token") == token:
            return {"run_id": run_id, "step_name": step_name, "token": token}
    except Exception:
        # handled below (stale recovery path)
        rows = []

    # Recovery path: take stale lock
    try:
        patch_url = (
            f"{base}/rest/v1/ops_step_locks"
            f"?run_id=eq.{run_q}&step_name=eq.{step_q}"
            f"&or=(expires_at.lt.{quote(now_iso, safe='')},owner.eq.{quote(owner, safe='')})"
        )
        updated = _sb_request(
            method="PATCH",
            url=patch_url,
            key=sb_key,
            body=row,
            extra_headers={"Prefer": "return=representation"},
        ) or []
        if isinstance(updated, list) and updated and updated[0].get("lock_token") == token:
            return {"run_id": run_id, "step_name": step_name, "token": token}
        check_url = (
            f"{base}/rest/v1/ops_step_locks"
            f"?select=lock_token"
            f"&run_id=eq.{run_q}&step_name=eq.{step_q}&limit=1"
        )
        rows = _sb_request(method="GET", url=check_url, key=sb_key) or []
        if rows and rows[0].get("lock_token") == token:
            return {"run_id": run_id, "step_name": step_name, "token": token}
    except Exception as exc:
        strict = str(os.environ.get("PIPELINE_REQUIRE_DISTRIBUTED_LOCK", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if strict:
            raise RuntimeError(
                "Unable to acquire distributed lock. Ensure Supabase table public.ops_step_locks exists "
                f"(run_id={run_id}, step_name={step_name}): {exc}"
            ) from exc
        print(
            f"[WARN] distributed lock unavailable for {run_id}:{step_name}; continuing without Supabase lock ({exc})",
            file=sys.stderr,
        )
        return None
    raise RuntimeError(
        f"Unable to acquire distributed lock for {run_id}:{step_name} "
        "(active lock held by another worker)"
    )


def _release_supabase_step_lock(lock_ctx: Optional[Dict[str, str]]) -> None:
    if not lock_ctx:
        return
    sb_url, sb_key = supabase_env()
    if not sb_url or not sb_key:
        return
    base = sb_url.rstrip("/")
    run_id = lock_ctx.get("run_id", "")
    step_name = lock_ctx.get("step_name", "")
    token = lock_ctx.get("token", "")
    if not run_id or not step_name or not token:
        return
    url = (
        f"{base}/rest/v1/ops_step_locks"
        f"?run_id=eq.{quote(run_id, safe='')}&step_name=eq.{quote(step_name, safe='')}&lock_token=eq.{quote(token, safe='')}"
    )
    try:
        _sb_request(method="DELETE", url=url, key=sb_key)
    except Exception:
        pass


def _heartbeat_supabase_step_lock(lock_ctx: Optional[Dict[str, str]], ttl_sec: int = 1800) -> None:
    if not lock_ctx:
        return
    sb_url, sb_key = supabase_env()
    if not sb_url or not sb_key:
        return
    run_id = lock_ctx.get("run_id", "")
    step_name = lock_ctx.get("step_name", "")
    token = lock_ctx.get("token", "")
    if not run_id or not step_name or not token:
        return
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "heartbeat_at": now.isoformat(),
        "expires_at": (now + dt.timedelta(seconds=max(60, ttl_sec))).isoformat(),
    }
    base = sb_url.rstrip("/")
    url = (
        f"{base}/rest/v1/ops_step_locks"
        f"?run_id=eq.{quote(run_id, safe='')}"
        f"&step_name=eq.{quote(step_name, safe='')}"
        f"&lock_token=eq.{quote(token, safe='')}"
    )
    try:
        _sb_request(method="PATCH", url=url, key=sb_key, body=payload)
    except Exception:
        # Heartbeat failure should not crash the step; stale lock recovery handles this.
        pass


def _run_with_contract(command_name: str, args: argparse.Namespace, fn) -> None:
    contract = STEP_CONTRACTS.get(command_name)
    if not contract:
        fn(args)
        return

    # Resolve run context.
    if command_name == "init-run":
        if not args.run_id:
            args.run_id = generate_run_id(args.category)
        run_id = args.run_id
        run_dir = get_run_dir(run_id)
    else:
        run_dir, run_id, _ = load_run(args)
        _validate_run_file(run_dir, f"{command_name}:pre")

    required_files = list(contract.get("inputs", []))
    output_files = list(contract.get("outputs", []))
    if required_files:
        _required_files_exist(run_dir, required_files)
    input_file_hashes, _ = collect_file_hashes(run_dir, required_files)
    job = _build_job_contract(
        run_id=run_id,
        step_name=command_name,
        command_name=command_name,
        args=args,
        required_files=required_files,
        file_hashes=input_file_hashes,
        requirements=_step_requirements(command_name, args),
    )
    inputs_hash = _hash_step_inputs(job=job)

    # Idempotent skip by receipt.
    if not args.force and _receipt_is_reusable(
        run_dir=run_dir,
        step_name=command_name,
        inputs_hash=inputs_hash,
        output_files=output_files,
    ):
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        now_mono = time.monotonic()
        receipt = build_receipt(
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            step_name=command_name,
            ok=True,
            status="OK",
            exit_code=0,
            inputs_hash=inputs_hash,
            outputs_hash=sha1_json({"skipped": True}),
            started_monotonic=now_mono,
            finished_monotonic=now_mono,
            started_at=now_iso,
            finished_at=now_iso,
            artifacts=_artifact_pointers(run_dir, output_files),
            idempotent_skip=True,
        )
        _write_receipt_and_validate(run_dir, command_name, receipt)
        write_jsonl(
            _jsonl_log_path(run_dir, command_name),
            {
                "event": "step_skip_idempotent",
                "run_id": run_id,
                "step_name": command_name,
                "inputs_hash": inputs_hash,
            },
        )
        _refresh_run_summary(run_dir)
        log_ops_event(run_id, "step_skip_idempotent", {"step_name": command_name, "inputs_hash": inputs_hash})
        print(f"[SKIP] {command_name} idempotent (inputs_hash unchanged)")
        return

    try:
        lock_ttl = int(os.environ.get("PIPELINE_STEP_LOCK_TTL_SEC", "1800") or 1800)
    except (ValueError, TypeError):
        lock_ttl = 1800
    lock_ctx = _acquire_supabase_step_lock(run_id, command_name, ttl_sec=lock_ttl)
    hb_stop = threading.Event()
    hb_thread: Optional[threading.Thread] = None
    if lock_ctx:
        hb_interval = max(30, min(300, lock_ttl // 3))

        def _heartbeat_loop():
            while not hb_stop.wait(hb_interval):
                _heartbeat_supabase_step_lock(lock_ctx, ttl_sec=lock_ttl)

        hb_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"step-lock-heartbeat:{run_id}:{command_name}",
            daemon=True,
        )
        hb_thread.start()

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    started_monotonic = time.monotonic()
    log_ops_event(run_id, "step_start", {"step_name": command_name, "inputs_hash": inputs_hash})
    write_jsonl(
        _jsonl_log_path(run_dir, command_name),
        {
            "event": "step_start",
            "run_id": run_id,
            "step_name": command_name,
            "inputs_hash": inputs_hash,
            "required_files": required_files,
        },
    )
    try:
        fn(args)
        if output_files:
            _required_files_exist(run_dir, output_files)
        outputs_hash, _ = _hash_step_outputs(run_dir, output_files)
        if (run_dir / "run.json").exists():
            _validate_run_file(run_dir, f"{command_name}:post")
        finished_monotonic = time.monotonic()
        finished_at = dt.datetime.now(dt.timezone.utc).isoformat()
        receipt = build_receipt(
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            step_name=command_name,
            ok=True,
            status="OK",
            exit_code=0,
            inputs_hash=inputs_hash,
            outputs_hash=outputs_hash,
            started_monotonic=started_monotonic,
            finished_monotonic=finished_monotonic,
            started_at=started_at,
            finished_at=finished_at,
            artifacts=_artifact_pointers(run_dir, output_files),
            idempotent_skip=False,
        )
        _write_receipt_and_validate(run_dir, command_name, receipt)
        write_jsonl(
            _jsonl_log_path(run_dir, command_name),
            {
                "event": "step_ok",
                "run_id": run_id,
                "step_name": command_name,
                "outputs_hash": outputs_hash,
                "duration_ms": receipt["timings"]["duration_ms"],
            },
        )
        log_ops_event(
            run_id,
            "step_ok",
            {
                "step_name": command_name,
                "inputs_hash": inputs_hash,
                "outputs_hash": outputs_hash,
                "duration_ms": receipt["timings"]["duration_ms"],
            },
        )
        _refresh_run_summary(run_dir)
    except Exception as exc:
        finished_monotonic = time.monotonic()
        finished_at = dt.datetime.now(dt.timezone.utc).isoformat()
        receipt = build_receipt(
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            step_name=command_name,
            ok=False,
            status="FAIL",
            exit_code=2,
            inputs_hash=inputs_hash,
            outputs_hash=sha1_json({"error": str(exc)}),
            started_monotonic=started_monotonic,
            finished_monotonic=finished_monotonic,
            started_at=started_at,
            finished_at=finished_at,
            artifacts=_artifact_pointers(run_dir, output_files),
            idempotent_skip=False,
            error=exc,
        )
        _write_receipt_and_validate(run_dir, command_name, receipt)
        write_jsonl(
            _jsonl_log_path(run_dir, command_name),
            {
                "event": "step_fail",
                "run_id": run_id,
                "step_name": command_name,
                "error": str(exc),
                "duration_ms": receipt["timings"]["duration_ms"],
            },
        )
        log_ops_event(
            run_id,
            "step_fail",
            {
                "step_name": command_name,
                "inputs_hash": inputs_hash,
                "error": str(exc),
                "duration_ms": receipt["timings"]["duration_ms"],
            },
        )
        _refresh_run_summary(run_dir)
        raise
    finally:
        hb_stop.set()
        if hb_thread:
            hb_thread.join(timeout=2.0)
        _release_supabase_step_lock(lock_ctx)


# ---------------------------------------------------------------------------
# MiniMax API (OpenAI-compatible)
# ---------------------------------------------------------------------------

def minimax_env() -> Dict[str, str]:
    """Load MiniMax config from env file."""
    cfg = {"api_key": "", "model": "MiniMax-M2.5", "base_url": "https://api.minimax.io/v1"}
    for src in [MINIMAX_ENV]:
        if src.exists():
            for line in src.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "MINIMAX_API_KEY":
                    cfg["api_key"] = v
                elif k == "MINIMAX_MODEL":
                    cfg["model"] = v
                elif k == "MINIMAX_BASE_URL":
                    cfg["base_url"] = v
    # Also check env vars (override file)
    cfg["api_key"] = os.environ.get("MINIMAX_API_KEY", cfg["api_key"])
    cfg["model"] = os.environ.get("MINIMAX_MODEL", cfg["model"])
    cfg["base_url"] = os.environ.get("MINIMAX_BASE_URL", cfg["base_url"])
    return cfg


def minimax_chat(
    messages: List[Dict[str, str]],
    *,
    model: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    timeout_sec: int = 120,
    logger: Optional[logging.Logger] = None,
) -> str:
    """Call MiniMax chat completions (OpenAI-compatible). Returns assistant text."""
    cfg = minimax_env()
    if not cfg["api_key"]:
        raise RuntimeError("MINIMAX_API_KEY not configured")
    model = model or cfg["model"]
    base = cfg["base_url"].rstrip("/")

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    req = Request(
        f"{base}/chat/completions",
        method="POST",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
    )
    try:
        with urlopen(req, timeout=int(timeout_sec)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        err_msg = str(e)
        # Try to extract body from HTTPError
        if hasattr(e, "read"):
            err_msg = e.read().decode("utf-8", errors="replace")
        if logger:
            logger.error(f"MiniMax API error: {err_msg}")
        raise RuntimeError(f"MiniMax API error: {err_msg}") from e

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"MiniMax returned no choices: {data}")
    content = choices[0].get("message", {}).get("content", "")
    # Strip <think>...</think> reasoning tags (always present in M2.5)
    content = re.sub(r"<think>[\s\S]*?</think>\s*", "", content).strip()
    usage = data.get("usage", {})
    if logger:
        logger.debug(
            f"MiniMax usage: {usage.get('prompt_tokens', 0)} in / "
            f"{usage.get('completion_tokens', 0)} out"
        )
    return content


# ---------------------------------------------------------------------------
# ElevenLabs TTS API
# ---------------------------------------------------------------------------

def elevenlabs_env() -> Dict[str, str]:
    """Load ElevenLabs config from env file."""
    cfg = {"api_key": "", "voice_id": "", "voice_name": "Thomas Louis"}
    if ELEVENLABS_ENV.exists():
        for line in ELEVENLABS_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k == "ELEVENLABS_API_KEY":
                cfg["api_key"] = v
            elif k == "ELEVENLABS_VOICE_ID":
                cfg["voice_id"] = v
            elif k == "ELEVENLABS_VOICE_NAME":
                cfg["voice_name"] = v
    cfg["api_key"] = os.environ.get("ELEVENLABS_API_KEY", cfg["api_key"])
    cfg["voice_id"] = os.environ.get("ELEVENLABS_VOICE_ID", cfg["voice_id"])
    return cfg


def elevenlabs_tts(
    text: str,
    output_path: Path,
    *,
    voice_id: str = "",
    model_id: str = "eleven_multilingual_v2",
    logger: Optional[logging.Logger] = None,
) -> Path:
    """Generate speech via ElevenLabs TTS API. Returns path to audio file."""
    cfg = elevenlabs_env()
    if not cfg["api_key"]:
        raise RuntimeError("ELEVENLABS_API_KEY not configured")
    voice_id = voice_id or cfg["voice_id"]
    if not voice_id:
        raise RuntimeError("ELEVENLABS_VOICE_ID not configured")

    payload = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }).encode("utf-8")

    req = Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        method="POST",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "xi-api-key": cfg["api_key"],
            "Accept": "audio/mpeg",
        },
    )

    tmp = output_path.with_suffix(".tmp.mp3")
    try:
        with urlopen(req, timeout=300) as resp:
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp, output_path)
        if logger:
            size_kb = output_path.stat().st_size / 1024
            logger.info(f"ElevenLabs TTS: {size_kb:.0f}KB → {output_path.name}")
        return output_path
    except Exception as e:
        tmp.unlink(missing_ok=True)
        err_msg = str(e)
        if hasattr(e, "read"):
            err_msg = e.read().decode("utf-8", errors="replace")
        if logger:
            logger.error(f"ElevenLabs TTS error: {err_msg}")
        raise RuntimeError(f"ElevenLabs TTS error: {err_msg}") from e


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Run lock (prevent concurrent execution on same run_id)
# ---------------------------------------------------------------------------

class RunLock:
    """Simple file-based lock to prevent concurrent pipeline execution."""

    def __init__(self, run_dir: Path):
        self.lock_path = run_dir / "run.lock"
        self.held = False

    def acquire(self) -> bool:
        if self.lock_path.exists():
            try:
                lock_data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                # Corrupt lock file, remove and fall through to create
                self.lock_path.unlink(missing_ok=True)
            else:
                pid = lock_data.get("pid", 0)
                # Check if the holding process is still alive
                try:
                    os.kill(pid, 0)
                    return False  # Process still running
                except OSError:
                    pass  # Stale lock, safe to take over
                self.lock_path.unlink(missing_ok=True)
        # Use O_EXCL for atomic create — prevents TOCTOU race
        lock_data = {
            "pid": os.getpid(),
            "acquired_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        payload = json.dumps(lock_data).encode("utf-8")
        try:
            fd = os.open(str(self.lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.write(fd, payload)
            os.fsync(fd)
            os.close(fd)
        except FileExistsError:
            return False  # Another process won the race
        self.held = True
        return True

    def release(self):
        if self.held and self.lock_path.exists():
            self.lock_path.unlink(missing_ok=True)
            self.held = False

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(
                f"Run is locked by another process. Remove {self.lock_path} if stale."
            )
        return self

    def __exit__(self, *args):
        self.release()


# ---------------------------------------------------------------------------
# Artifact checksums (for audit + replay)
# ---------------------------------------------------------------------------

def file_checksum(path: Path) -> str:
    """SHA256 of a file for audit trail."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_artifact_checksums(run_dir: Path) -> Dict[str, str]:
    """Compute checksums for key pipeline artifacts."""
    artifacts = [
        "products.json", "variation_plan.json", "script.json",
        "assets_manifest.json", "voice/timestamps.json", "voice/voiceover.mp3",
        "davinci/project.json",
    ]
    checksums = {}
    for a in artifacts:
        p = run_dir / a
        if p.exists():
            checksums[a] = file_checksum(p)
    return checksums


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def with_retries(fn, *, max_attempts: int = 3, backoff: Optional[list[float]] = None,
                 label: str = "", logger: Optional[logging.Logger] = None):
    if backoff is None:
        backoff = [5, 15, 45]
    last_err = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if logger:
                logger.warning(f"{label} attempt {attempt+1}/{max_attempts} failed: {e}")
            if attempt < max_attempts - 1:
                wait = backoff[min(attempt, len(backoff)-1)]
                time.sleep(wait)
    raise RuntimeError(f"{label} failed after {max_attempts} attempts: {last_err}")


# ---------------------------------------------------------------------------
# Run ID + folder creation
# ---------------------------------------------------------------------------

def generate_run_id(category: str) -> str:
    now = dt.datetime.now()
    slug = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")[:30]
    return f"{slug}_{now.strftime('%Y-%m-%d_%H%M')}"


def get_run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

GATE_STATUSES = {"pending", "approved", "rejected"}


def _default_gate_state() -> Dict[str, str]:
    return {
        "status": "pending",
        "reviewer": "",
        "notes": "",
        "decided_at": "",
    }


def ensure_quality_gates(run_config: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, str]], bool]:
    """Ensure run.json contains normalized gate states. Returns (gates, changed)."""
    changed = False
    gates = run_config.get("quality_gates")
    if not isinstance(gates, dict):
        gates = {}
        changed = True

    normalized: Dict[str, Dict[str, str]] = {}
    for gate in ("gate1", "gate2"):
        raw = gates.get(gate) if isinstance(gates, dict) else None
        state = _default_gate_state()
        if isinstance(raw, dict):
            status = str(raw.get("status", "pending")).strip().lower()
            state["status"] = status if status in GATE_STATUSES else "pending"
            state["reviewer"] = str(raw.get("reviewer", "")).strip()
            state["notes"] = str(raw.get("notes", "")).strip()
            state["decided_at"] = str(raw.get("decided_at", "")).strip()
        normalized[gate] = state
        if raw != state:
            changed = True

    run_config["quality_gates"] = normalized
    return normalized, changed


def save_run_config(run_dir: Path, run_config: Dict[str, Any]) -> None:
    run_config["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    atomic_write_json(run_dir / "run.json", run_config)


def gate_is_approved(run_config: Dict[str, Any], gate_name: str) -> bool:
    gates, _ = ensure_quality_gates(run_config)
    return gates.get(gate_name, {}).get("status") == "approved"


def require_gate_approved(
    run_dir: Path,
    run_config: Dict[str, Any],
    gate_name: str,
    step_name: str,
    log: logging.Logger,
) -> None:
    gates, changed = ensure_quality_gates(run_config)
    if changed:
        save_run_config(run_dir, run_config)

    gate_state = gates.get(gate_name, _default_gate_state())
    if gate_state["status"] != "approved":
        msg = (
            f"{step_name} blocked: {gate_name} is {gate_state['status']}. "
            f"Approve with: python3 tools/pipeline.py approve-{gate_name} --run-id {run_config.get('run_id', '<run_id>')}"
        )
        log.error(msg)
        raise RuntimeError(msg)


def set_gate_decision(
    run_dir: Path,
    run_config: Dict[str, Any],
    gate_name: str,
    decision: str,
    reviewer: str,
    notes: str,
) -> None:
    gates, _ = ensure_quality_gates(run_config)
    if gate_name not in gates:
        raise RuntimeError(f"Unknown gate: {gate_name}")
    if decision not in {"approved", "rejected"}:
        raise RuntimeError(f"Invalid gate decision: {decision}")

    gates[gate_name] = {
        "status": decision,
        "reviewer": reviewer.strip(),
        "notes": notes.strip(),
        "decided_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    step_status = run_config.get("step_status", {})
    step_status[f"approve-{gate_name}"] = "done" if decision == "approved" else "rejected"
    run_config["step_status"] = step_status
    run_config["quality_gates"] = gates
    run_config["status"] = f"{gate_name}_{decision}"
    save_run_config(run_dir, run_config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _hostname(url: str) -> str:
    try:
        host = urlparse(str(url or "")).netloc.strip().lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_amzn_short_url(url: str) -> bool:
    return _hostname(url) == "amzn.to"


def append_affiliate_tag(url: str, tag: str) -> str:
    if _is_amzn_short_url(url):
        # SiteStripe short links already encapsulate tracking.
        return url
    if not tag:
        return url
    parsed = urlparse(url)
    params = list(parse_qsl(parsed.query, keep_blank_values=True))
    params = [(k, v) for (k, v) in params if k != "tag"]
    params.append(("tag", tag))
    query = urlencode(params)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def validate_affiliate_url(url: str, tag: str) -> bool:
    if _is_amzn_short_url(url):
        # amzn.to is a first-party Amazon short domain accepted by Associates.
        return True
    if not tag:
        return True
    return f"tag={tag}" in url and url.count(f"tag=") == 1


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

SEGMENT_TYPES = {
    "NARRATION", "PRODUCT_BLOCK",
}

# Granular segment types used by LLM-generated scripts (via video_pipeline_lib)
SEGMENT_TYPES_GRANULAR = {
    "HOOK", "CREDIBILITY", "CRITERIA",
    "PRODUCT_INTRO", "PRODUCT_DEMO", "PRODUCT_REVIEW", "PRODUCT_RANK",
    "FORWARD_HOOK", "WINNER_REINFORCEMENT", "ENDING_DECISION",
    "COMPARISON", "TIER_BREAK", "SURPRISE_PICK", "MYTH_BUST", "WINNER_TEASE",
}

# Types that count as "hook/narration" in either schema
_HOOK_TYPES = {"NARRATION", "HOOK", "CREDIBILITY"}

# Types that count as "product content" in either schema
_PRODUCT_TYPES = {"PRODUCT_BLOCK", "PRODUCT_INTRO", "PRODUCT_DEMO", "PRODUCT_REVIEW", "PRODUCT_RANK"}

SEGMENT_KINDS = {
    "AVATAR_TALK", "PRODUCT_GLAM", "BROLL", "NARRATION",
}


def validate_products_json(data: Dict) -> List[str]:
    errors = []
    if "products" not in data:
        errors.append("Missing 'products' array")
        return errors
    products = data["products"]
    if not isinstance(products, list) or len(products) < 5:
        errors.append(f"Need at least 5 products, got {len(products) if isinstance(products, list) else 0}")
    for i, p in enumerate(products):
        if not p.get("asin"):
            errors.append(f"Product {i}: missing asin")
        if not p.get("title"):
            errors.append(f"Product {i}: missing title")
        price = p.get("price", 0)
        if price < 1:
            errors.append(f"Product {i}: invalid price {price}")
    return errors


def validate_script_json(data: Dict) -> List[str]:
    """Validate script JSON supporting both mock schema (NARRATION/PRODUCT_BLOCK)
    and granular LLM schema (HOOK/CREDIBILITY/PRODUCT_INTRO/etc.)."""
    errors = []
    if "structure" not in data:
        errors.append("Missing 'structure' array")
        return errors

    structure = data["structure"]
    has_hook = False
    product_segments = 0
    total_words = 0

    for seg in structure:
        seg_type = seg.get("type", "")

        # Count words from direct voice_text
        voice = seg.get("voice_text", "")
        total_words += len(voice.split())

        # Count words from nested segments (PRODUCT_BLOCK schema)
        for sub in seg.get("segments", []):
            sub_voice = sub.get("voice_text", "")
            total_words += len(sub_voice.split())

        # Detect hook/opener in either schema
        if seg_type in _HOOK_TYPES:
            has_hook = True

        # Count product content in either schema
        if seg_type == "PRODUCT_BLOCK":
            product_segments += 1
        elif seg_type in _PRODUCT_TYPES:
            product_segments += 1

    # For granular schema, count unique products (by product_rank or segment grouping)
    if product_segments > 5:
        # Granular schema: multiple segments per product, count unique products
        product_ranks = set()
        for seg in structure:
            rank = seg.get("product_rank")
            if rank is not None:
                product_ranks.add(rank)
        if product_ranks:
            product_count = len(product_ranks)
        else:
            # Fallback: estimate from PRODUCT_INTRO count
            product_count = sum(1 for s in structure if s.get("type") == "PRODUCT_INTRO")
    else:
        product_count = product_segments

    if not has_hook:
        errors.append("Missing hook/opener segment (NARRATION or HOOK)")
    if product_count < 5:
        errors.append(f"Need 5 products represented, got {product_count}")
    if total_words < 1100:
        errors.append(f"Total words {total_words} below minimum 1100")
    if total_words > 1900:
        errors.append(f"Total words {total_words} above maximum 1900")

    return errors


# ---------------------------------------------------------------------------
# Discovery policy helpers
# ---------------------------------------------------------------------------

def _parse_iso(value: str) -> Optional[dt.datetime]:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def recent_asins_from_history(current_run_id: str, lookback_days: int) -> set[str]:
    """Collect ASINs from runs created in the last N days (local history)."""
    if lookback_days <= 0:
        return set()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
    out: set[str] = set()
    for run_path in RUNS_DIR.iterdir() if RUNS_DIR.exists() else []:
        if not run_path.is_dir():
            continue
        if run_path.name == current_run_id:
            continue
        run_json = run_path / "run.json"
        products_json = run_path / "products.json"
        if not run_json.exists() or not products_json.exists():
            continue
        try:
            run_data = json.loads(run_json.read_text(encoding="utf-8"))
            created_at = _parse_iso(run_data.get("created_at", ""))
            if not created_at or created_at < cutoff:
                continue
            pdata = json.loads(products_json.read_text(encoding="utf-8"))
            for p in pdata.get("products", []):
                asin = str(p.get("asin", "")).strip().upper()
                if asin:
                    out.add(asin)
        except Exception:
            continue
    return out


def enforce_product_policy(
    products: List[Dict[str, Any]],
    *,
    min_rating: float,
    min_reviews: int,
    min_price: float,
    max_price: float,
    excluded_asins: set[str],
    affiliate_tag: str,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for p in products:
        asin = str(p.get("asin", "")).strip().upper()
        if not asin:
            continue
        if asin in excluded_asins:
            logger.info(f"Excluded by 15-day history: {asin}")
            continue

        try:
            price = float(p.get("price", 0))
            rating = float(p.get("rating", 0))
            reviews = int(p.get("reviews", 0))
        except Exception:
            continue

        if price < min_price or price > max_price:
            continue
        if rating < min_rating:
            continue
        if reviews < min_reviews:
            continue

        product_url = str(p.get("product_url", "")).strip() or f"https://www.amazon.com/dp/{asin}"
        source_aff_url = str(p.get("affiliate_url", "")).strip()
        aff_url = source_aff_url or append_affiliate_tag(product_url, affiliate_tag)
        # Keep first-party amzn.to links intact; otherwise enforce configured tag.
        if affiliate_tag and aff_url and not _is_amzn_short_url(aff_url):
            aff_url = append_affiliate_tag(aff_url, affiliate_tag)
        if not validate_affiliate_url(aff_url, affiliate_tag):
            logger.warning(f"Invalid affiliate URL for {asin}; fixing")
            aff_url = append_affiliate_tag(product_url.split("?")[0], affiliate_tag)

        clean = dict(p)
        clean["asin"] = asin
        clean["price"] = round(price, 2)
        clean["rating"] = round(rating, 2)
        clean["reviews"] = reviews
        clean["product_url"] = product_url
        clean["affiliate_url"] = aff_url
        filtered.append(clean)

    filtered = filtered[:5]
    for i, p in enumerate(filtered, 1):
        p["rank"] = i
    return filtered


# ===================================================================
# STEP 0: init-run
# ===================================================================

def cmd_init_run(args):
    category = args.category
    run_id = args.run_id or generate_run_id(category)
    run_dir = get_run_dir(run_id)
    run_json_path = run_dir / "run.json"

    # _run_with_contract may create run_dir for logs/receipts before init executes.
    # Skip only when a completed run.json already exists.
    if run_json_path.exists() and not args.force:
        print(f"[SKIP] Run already exists: {run_dir}")
        return

    # Create folder structure
    for subdir in [
        "assets/product_1", "assets/product_2", "assets/product_3",
        "assets/product_4", "assets/product_5", "assets/thumbnail",
        "voice", "davinci", "upload", "metrics", "logs", "receipts", "security", "ops",
    ]:
        (run_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Write run.json
    run_config = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "category": category,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "channel": CHANNEL_NAME,
        "config": {
            "target_duration_minutes": args.duration,
            "voice": args.voice,
            "affiliate_tag": args.affiliate_tag,
            "tracking_id_override": getattr(args, "tracking_id_override", "") or "",
            "min_rating": args.min_rating,
            "min_reviews": args.min_reviews,
            "min_price": args.min_price,
            "max_price": args.max_price,
            "exclude_last_days": args.exclude_last_days,
            "resolution": args.resolution,
            "fps": 30,
            "daily_budget_usd": args.daily_budget_usd,
            "spent_usd": args.spent_usd,
            "critical_failures": args.critical_failures,
        },
        "status": "initialized",
        "step_status": {
            "init": "done",
            "discover-products": "pending",
            "plan-variations": "pending",
            "generate-script": "pending",
            "approve-gate1": "pending",
            "generate-assets": "pending",
            "generate-voice": "pending",
            "build-davinci": "pending",
            "convert-to-rayvault": "pending",
            "validate-originality": "pending",
            "validate-compliance": "pending",
            "approve-gate2": "pending",
            "render-and-upload": "pending",
            "collect-metrics": "pending",
        },
        "quality_gates": {
            "gate1": _default_gate_state(),
            "gate2": _default_gate_state(),
        },
        "steps_completed": [],
        "artifact_checksums": {},
    }
    atomic_write_json(run_dir / "run.json", run_config)

    log = setup_logger(run_dir, "00_init")
    log.info(f"Run initialized: {run_id}")
    log.info(f"Category: {category}")
    log.info(f"Duration target: {args.duration} min")
    log.info(f"Folder: {run_dir}")

    log_ops_event(run_id, "run_init", {"category": category})
    print(f"[OK] Run initialized: {run_id}")
    print(f"     Folder: {run_dir}")


# ===================================================================
# STEP 1: discover-products
# ===================================================================

def cmd_discover_products(args):
    run_dir, run_id, run_config = load_run(args)
    _run_learning_gate(run_id, "research")
    log = setup_logger(run_dir, "01_discovery")
    products_json_path = run_dir / "products.json"
    products_csv_path = run_dir / "products.csv"
    discovery_receipt_path = run_dir / "discovery_receipt.json"

    if products_json_path.exists() and not args.force:
        log.info("products.json already exists, skipping")
        print(f"[SKIP] products.json exists at {products_json_path}")
        return

    config = run_config.get("config", {})
    category = run_config["category"]
    tag = config.get("affiliate_tag", "")

    log.info(f"Discovering products for: {category}")

    discovery_receipt: Dict[str, Any] = {
        "run_id": run_id,
        "category": category,
        "requested_source": args.source,
        "strategy": "api_first_scraping_fallback",
        "attempts": [],
    }
    if args.source == "mock":
        products = generate_mock_products(category, tag)
        discovery_receipt["selected_source"] = "mock"
        discovery_receipt["status"] = "OK"
        discovery_receipt["attempts"].append(
            {
                "source": "mock",
                "status": "ok",
                "count": len(products),
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        log.info(f"Mock mode: {len(products)} products generated")
    else:
        log.info("API-first discovery: scrape with retry, fallback to mock on ban/rate-limit")
        scrape_attempt_counter = {"n": 0}

        def _classify_discovery_error(err: Exception) -> str:
            msg = str(err).lower()
            if any(t in msg for t in ("429", "rate limit", "too many requests")):
                return "RATE_LIMIT"
            if any(t in msg for t in ("captcha", "robot", "bot detection", "forbidden", "403")):
                return "BAN_OR_BOT_CHALLENGE"
            return "SCRAPE_ERROR"

        def _attempt_scrape():
            scrape_attempt_counter["n"] += 1
            attempt_id = scrape_attempt_counter["n"]
            ts = dt.datetime.now(dt.timezone.utc).isoformat()
            try:
                out = scrape_amazon_products(
                    category=category,
                    affiliate_tag=tag,
                    min_rating=config.get("min_rating", 4.2),
                    min_reviews=config.get("min_reviews", 500),
                    min_price=config.get("min_price", 100),
                    max_price=config.get("max_price", 500),
                    exclude_last_days=config.get("exclude_last_days", 15),
                    logger=log,
                )
                discovery_receipt["attempts"].append(
                    {
                        "source": "scrape",
                        "attempt": attempt_id,
                        "status": "ok",
                        "count": len(out),
                        "ts": ts,
                    }
                )
                return out
            except Exception as exc:
                discovery_receipt["attempts"].append(
                    {
                        "source": "scrape",
                        "attempt": attempt_id,
                        "status": "failed",
                        "reason_code": _classify_discovery_error(exc),
                        "error": str(exc),
                        "ts": ts,
                    }
                )
                raise

        try:
            products = with_retries(
                _attempt_scrape,
                max_attempts=3,
                backoff=[5, 15, 45],
                label="discover-products:scrape",
                logger=log,
            )
            discovery_receipt["selected_source"] = "scrape"
            discovery_receipt["status"] = "OK"
        except Exception as exc:
            log.warning(f"Scrape unavailable ({exc}); fallback to mock for this run")
            products = generate_mock_products(category, tag)
            discovery_receipt["selected_source"] = "mock_fallback"
            discovery_receipt["status"] = "WARN"
            discovery_receipt["fallback_reason"] = str(exc)

    try:
        _lookback = int(config.get("exclude_last_days", 15))
    except (ValueError, TypeError):
        _lookback = 15
    excluded_asins = recent_asins_from_history(
        current_run_id=run_id,
        lookback_days=_lookback,
    )
    if excluded_asins:
        log.info(f"Loaded {len(excluded_asins)} ASINs from local {config.get('exclude_last_days', 15)}-day history")

    selected_source = str(discovery_receipt.get("selected_source", "")).lower()
    if selected_source.startswith("mock"):
        # If scraping is unavailable, fallback mock data must still survive 15-day ASIN exclusion.
        needed_pool = max(25, len(excluded_asins) + 5)
        batch_count = (needed_pool + 4) // 5
        expanded: List[Dict[str, Any]] = []
        for batch in range(batch_count):
            start_index = batch * 5 + 1
            expanded.extend(generate_mock_products(category, tag, start_index=start_index))
        products = expanded
        log.info(
            f"Expanded mock candidate pool to {len(products)} products "
            f"(history={len(excluded_asins)}, lookback={_lookback}d)"
        )

    try:
        _min_rating = float(config.get("min_rating", 4.2))
    except (ValueError, TypeError):
        _min_rating = 4.2
    try:
        _min_reviews = int(config.get("min_reviews", 500))
    except (ValueError, TypeError):
        _min_reviews = 500
    try:
        _min_price = float(config.get("min_price", 100))
    except (ValueError, TypeError):
        _min_price = 100.0
    try:
        _max_price = float(config.get("max_price", 500))
    except (ValueError, TypeError):
        _max_price = 500.0
    products = enforce_product_policy(
        products,
        min_rating=_min_rating,
        min_reviews=_min_reviews,
        min_price=_min_price,
        max_price=_max_price,
        excluded_asins=excluded_asins,
        affiliate_tag=tag,
        logger=log,
    )

    if len(products) < 5:
        raise RuntimeError(
            f"Policy filters left only {len(products)} products. "
            "Broaden search/category or relax thresholds."
        )

    # Build products.json in user's exact schema
    products_data = {
        "category": category,
        "currency": "USD",
        "marketplace": "amazon.com",
        "affiliate": {
            "tag": tag,
            "link_style": "asin_tag",
        },
        "products": products,
    }

    errors = validate_products_json(products_data)
    if errors:
        for e in errors:
            log.error(f"Validation: {e}")
        raise RuntimeError(f"products.json validation failed: {errors}")

    atomic_write_json(products_json_path, products_data)
    log.info(f"products.json written: {len(products)} products")
    discovery_receipt["final_count"] = len(products)
    atomic_write_json(discovery_receipt_path, discovery_receipt)
    log.info("discovery_receipt.json written")

    # Write CSV
    write_products_csv(products, products_csv_path)
    log.info(f"products.csv written")

    mark_step_complete(run_dir, "discover-products")
    log_ops_event(run_id, "products_discovered", {"count": len(products), "category": category})
    print(f"[OK] {len(products)} products discovered → {products_json_path}")


def generate_mock_products(category: str, tag: str, start_index: int = 1) -> List[Dict]:
    if start_index < 1:
        start_index = 1
    cat_hash = re.sub(r"[^A-Z0-9]", "", category.upper())[:4].ljust(4, "X")
    seed = [
        ("Smart LED Desk Lamp with Wireless Charger", 109.99, 4.6, 12430),
        ("Programmable Mini Macro Keypad", 119.99, 4.5, 6830),
        ("USB-C Docking Station Triple Display", 129.99, 4.4, 2190),
        ("Ergonomic Vertical Mouse Pro", 139.99, 4.4, 9320),
        ("Noise-Cancelling Desktop Fan", 149.99, 4.3, 5010),
    ]
    products = []
    for offset, (title, price, rating, reviews) in enumerate(seed):
        rank = offset + 1
        asin_serial = start_index + offset
        asin = f"B0{cat_hash}{asin_serial:04d}"
        base_url = f"https://www.amazon.com/dp/{asin}"
        aff_url = append_affiliate_tag(base_url, tag)
        products.append({
            "rank": rank,
            "asin": asin,
            "title": f"{title} ({category.replace('_', ' ').title()})",
            "price": price,
            "rating": rating,
            "reviews": reviews,
            "image_url": f"https://m.media-amazon.com/images/I/{asin}.jpg",
            "product_url": base_url,
            "affiliate_url": aff_url,
        })
    return products


def scrape_amazon_products(
    category: str, affiliate_tag: str,
    min_rating: float, min_reviews: int, min_price: float, max_price: float,
    exclude_last_days: int, logger: logging.Logger,
) -> List[Dict]:
    """Scrape Amazon search results using shared scraper (strict mode: raises on failure)."""
    sys.path.insert(0, str(BASE_DIR / "tools"))
    from video_pipeline_lib import (
        discover_products_scrape,
        resolve_amazon_search_url_for_category,
    )

    search_url = resolve_amazon_search_url_for_category(category)
    raw_products = discover_products_scrape(
        theme=category,
        affiliate_tag=affiliate_tag,
        top_n=5,
        min_rating=min_rating,
        min_reviews=min_reviews,
        min_price=min_price,
        max_price=max_price,
        max_pages=3,
        excluded_asins=set(),
        min_theme_match=0.3,
        search_url=search_url,
    )
    products = []
    for rank, p in enumerate(raw_products, 1):
        products.append({
            "rank": rank,
            "asin": p.asin,
            "title": p.product_title,
            "price": p.current_price_usd,
            "rating": p.rating,
            "reviews": p.review_count,
            "image_url": f"https://m.media-amazon.com/images/I/{p.asin}.jpg",
            "product_url": p.amazon_url,
            "affiliate_url": p.affiliate_url,
        })
    if not products:
        raise RuntimeError("scrape returned zero products")
    return products


def write_products_csv(products: List[Dict], path: Path):
    if not products:
        return
    fields = ["rank", "asin", "title", "price", "rating", "reviews", "product_url", "affiliate_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(products)


# ===================================================================
# STEP 1.5: plan-variations
# ===================================================================

def cmd_plan_variations(args):
    run_dir, run_id, run_config = load_run(args)
    log = setup_logger(run_dir, "01b_variations")
    vp_path = run_dir / "variation_plan.json"

    if vp_path.exists() and not args.force:
        log.info("variation_plan.json already exists, skipping")
        print(f"[SKIP] variation_plan.json exists")
        return

    products_path = run_dir / "products.json"
    if not products_path.exists():
        log.error("products.json not found — run discover-products first")
        raise RuntimeError("products.json not found")

    products_data = json.loads(products_path.read_text(encoding="utf-8"))
    products = products_data["products"]
    category = products_data["category"]

    log.info(f"Planning variations for: {category}, {len(products)} products")

    from variation_planner import plan_variations
    plan = plan_variations(run_id, category, products)

    atomic_write_json(vp_path, plan)
    score = plan.get("variation_score", 0)
    template = plan.get("selections", {}).get("structure_template", "?")
    log.info(f"variation_plan.json written: score={score:.2f}, template={template}")

    mark_step_complete(run_dir, "plan-variations")
    log_ops_event(run_id, "variation_planned", {
        "score": score,
        "selections": plan.get("selections", {}),
    })
    print(f"[OK] variation_plan.json: score={score:.2f}, template={template} → {vp_path}")


# ===================================================================
# STEP 2: generate-script
# ===================================================================

def cmd_generate_script(args):
    run_dir, run_id, run_config = load_run(args)
    _run_learning_gate(run_id, "script")
    log = setup_logger(run_dir, "02_script")
    script_path = run_dir / "script.json"
    security_dir = run_dir / "security"
    security_dir.mkdir(parents=True, exist_ok=True)
    guard_report_path = security_dir / "input_guard_report.json"

    if script_path.exists() and not args.force:
        if not guard_report_path.exists():
            products_path = run_dir / "products.json"
            if products_path.exists():
                products_data = json.loads(products_path.read_text(encoding="utf-8"))
                guard_report = scan_product_inputs(products_data.get("products", []))
                atomic_write_json(guard_report_path, guard_report)
                log.info("Backfilled missing security/input_guard_report.json for existing script")
        log.info("script.json already exists, skipping")
        print(f"[SKIP] script.json exists")
        return

    products_path = run_dir / "products.json"
    if not products_path.exists():
        log.error("products.json not found — run discover-products first")
        raise RuntimeError("products.json not found")

    products_data = json.loads(products_path.read_text(encoding="utf-8"))
    products = products_data["products"]
    category = products_data["category"]
    config = run_config.get("config", {})
    duration = config.get("target_duration_minutes", 8)

    guard_report = scan_product_inputs(products)
    atomic_write_json(guard_report_path, guard_report)
    blocked, reason = should_block_generation(guard_report)
    if blocked:
        raise RuntimeError(
            "generate-script blocked by input guard: "
            f"{reason}. Review {guard_report_path} and clean product inputs."
        )
    if str(guard_report.get("status", "")).strip().upper() == "WARN":
        warn_codes = guard_report.get("warn_reason_codes", []) if isinstance(guard_report, dict) else []
        warn_s = ", ".join(str(x) for x in warn_codes if str(x).strip()) or "unspecified"
        log.warning(
            "Input guard returned WARN (telemetry-only; not blocking). "
            f"warn_reason_codes=[{warn_s}]"
        )

    # Load variation_plan.json if it exists
    variation_plan = None
    vp_path = run_dir / "variation_plan.json"
    if vp_path.exists():
        variation_plan = json.loads(vp_path.read_text(encoding="utf-8"))
        log.info(f"Loaded variation_plan: template={variation_plan.get('selections', {}).get('structure_template', '?')}")

    log.info(f"Generating script: {category}, {duration} min, {len(products)} products")

    if args.source == "mock":
        script_data = generate_mock_script(run_id, category, products, duration, variation_plan)
    elif args.source in {"openclaw", "chatgpt_ui"}:
        # Policy: scripts must be generated via the user's ChatGPT UI session (no LLM API keys).
        script_data = generate_script_chatgpt_ui(run_dir, run_id, category, products, duration, log, variation_plan)
    elif args.source == "minimax":
        raise RuntimeError(
            "Script generation via MiniMax is disabled by policy. "
            "Use --source openclaw (ChatGPT UI via OpenClaw browser)."
        )
    else:
        script_data = generate_mock_script(run_id, category, products, duration, variation_plan)

    _ensure_intro_disclosure(script_data, log)

    # Validate
    errors = validate_script_json(script_data)
    if errors:
        log.warning(f"Script validation issues: {errors}")
        if args.source != "mock":
            for e in errors:
                log.error(f"  {e}")
            raise RuntimeError(
                "script.json validation failed in production mode. "
                "Fix prompt/source and re-run generate-script."
            )

    atomic_write_json(script_path, script_data)
    total_words = count_script_words(script_data)
    log.info(f"script.json written: {total_words} words")

    mark_step_complete(run_dir, "generate-script")
    log_ops_event(
        run_id,
        "script_generated",
        {
            "words": total_words,
            "source": args.source,
            "input_guard_status": guard_report.get("status", "unknown"),
            "input_guard_fail_codes": guard_report.get("fail_reason_codes", []),
            "input_guard_warn_codes": guard_report.get("warn_reason_codes", []),
        },
    )
    print(f"[OK] script.json: {total_words} words → {script_path}")


def count_script_words(data: Dict) -> int:
    total = 0
    for seg in data.get("structure", []):
        total += len(seg.get("voice_text", "").split())
        for sub in seg.get("segments", []):
            total += len(sub.get("voice_text", "").split())
    return total


def _sanitize_prompt_field(raw: str, source: str, log: logging.Logger) -> str:
    raw_s = str(raw or "")
    mode = "url" if raw_s.strip().lower().startswith(("http://", "https://")) else "generic"
    scan = sanitize_external_text(raw_s, source=source, mode=mode)
    status = str(scan.get("status", "OK")).strip().upper()
    if status == "FAIL":
        codes = scan.get("fail_reason_codes", []) if isinstance(scan, dict) else []
        codes_s = ", ".join(str(x) for x in codes if str(x).strip()) or "UNKNOWN"
        log.warning(f"Prompt field sanitized due to FAIL ({codes_s}) ({source})")
        return "[sanitized_external_field]"
    # WARN is telemetry-only; keep content to preserve product specificity.
    return raw_s.replace("\x00", "").strip()


def _ensure_intro_disclosure(script_data: Dict[str, Any], log: logging.Logger) -> None:
    """Ensure required affiliate disclosure is present in intro segments."""
    structure = script_data.get("structure", [])
    if not isinstance(structure, list) or not structure:
        return
    intro_text = " ".join(
        str(seg.get("voice_text", "")).strip()
        for seg in structure[:2]
        if isinstance(seg, dict)
    ).lower()
    if "as an amazon associate i earn from qualifying purchases" in intro_text:
        return
    first = structure[0]
    if not isinstance(first, dict):
        return
    existing = str(first.get("voice_text", "")).strip()
    if existing:
        first["voice_text"] = f"{DISCLOSURE_INTRO_SHORT} {existing}"
    else:
        first["voice_text"] = DISCLOSURE_INTRO_SHORT
    log.info("Injected affiliate disclosure into intro segment")


def _normalize_script_payload(
    *,
    payload: Any,
    run_id: str,
    category: str,
    products: List[Dict[str, Any]],
    duration: int,
) -> Dict[str, Any]:
    """Normalize provider output into the pipeline script contract."""
    # Already in canonical shape.
    if isinstance(payload, dict) and isinstance(payload.get("structure"), list):
        out = dict(payload)
        out["run_id"] = run_id
        out["category"] = category
        out.setdefault("target_duration_minutes", duration)
        out.setdefault(
            "style",
            {
                "channel": CHANNEL_NAME,
                "host": "Ray",
                "tone": "fast, clear, credible, not salesy",
                "language": "en-US",
            },
        )
        out.setdefault("chapters", [])
        return out

    # Common nesting from some models: {"script": {...}}
    if isinstance(payload, dict):
        for k in ("script", "result", "data", "output"):
            candidate = payload.get(k)
            if isinstance(candidate, dict) and (
                isinstance(candidate.get("structure"), list)
                or isinstance(candidate.get("segments"), list)
            ):
                return _normalize_script_payload(
                    payload=candidate,
                    run_id=run_id,
                    category=category,
                    products=products,
                    duration=duration,
                )

    # Legacy shape: {"segments":[{"type":"HOOK","narration":"..."}]}
    if isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        raw_segments = payload.get("segments", [])
        structure: List[Dict[str, Any]] = []
        product_rank = 0
        current_product_rank = 0

        def _voice(seg: Dict[str, Any]) -> str:
            for key in ("voice_text", "narration", "text", "script"):
                value = str(seg.get(key, "") or "").strip()
                if value:
                    return value
            return ""

        for idx, raw in enumerate(raw_segments, 1):
            if not isinstance(raw, dict):
                continue
            s_type = str(raw.get("type", "NARRATION") or "NARRATION").strip().upper()
            voice = _voice(raw)
            if not voice:
                continue
            allowed_types = SEGMENT_TYPES.union(SEGMENT_TYPES_GRANULAR)
            if s_type not in allowed_types:
                s_type = "NARRATION"
            entry: Dict[str, Any] = {
                "id": f"s{idx:02d}",
                "type": s_type,
                "voice_text": voice,
                "visual_hint": str(raw.get("visual_hint", "") or "").strip(),
                "on_screen": [],
            }
            if s_type.startswith("PRODUCT_"):
                if s_type == "PRODUCT_INTRO":
                    product_rank = min(len(products), product_rank + 1)
                    current_product_rank = max(1, product_rank)
                elif current_product_rank == 0:
                    current_product_rank = 1
                suffix = s_type.replace("PRODUCT_", "").lower()
                entry["id"] = f"p{current_product_rank}_{suffix}"
                entry["product_rank"] = current_product_rank
                if s_type in {"PRODUCT_REVIEW", "PRODUCT_RANK"}:
                    entry["role"] = "evidence"
                    low = voice.lower()
                    if "in my test" not in low and "in my opinion" not in low:
                        voice = f"In my test, {voice[0].lower() + voice[1:] if len(voice) > 1 else voice}"
                    contra_markers = (
                        "not for",
                        "skip if",
                        "if you don't",
                        "if you do not",
                        "who should not buy",
                        "avoid this if",
                    )
                    if not any(m in low for m in contra_markers):
                        contra_templates = [
                            "Skip if you don't need these extra features.",
                            "Avoid this if portability is your top priority.",
                            "Who should not buy this: anyone who wants a simple plug-and-play setup.",
                            "Not for buyers on a strict budget looking only for basics.",
                            "If you do not need premium build quality, this can be overkill.",
                        ]
                        pick = contra_templates[(current_product_rank - 1) % len(contra_templates)]
                        voice = f"{voice} {pick}"
                    entry["voice_text"] = voice
            elif s_type in {"HOOK", "CREDIBILITY", "CRITERIA"}:
                entry["id"] = s_type.lower()
            structure.append(entry)

        # Derive simple chapters by product intro points when present.
        chapters: List[Dict[str, str]] = [{"timecode": "00:00", "title": "Intro"}]
        ms = 0
        for seg in structure:
            words = len(str(seg.get("voice_text", "")).split())
            dur_ms = int((words / 155.0) * 60 * 1000)
            seg_id = str(seg.get("id", ""))
            m = re.match(r"p(\d+)_intro$", seg_id)
            if m:
                rank = int(m.group(1))
                title = ""
                if 1 <= rank <= len(products):
                    title = str(products[rank - 1].get("title", "") or "")
                mm, ss = divmod(ms // 1000, 60)
                chapters.append(
                    {
                        "timecode": f"{mm:02d}:{ss:02d}",
                        "title": f"#{rank} {title[:40]}".strip(),
                    }
                )
            ms += max(1000, dur_ms)

        return {
            "run_id": run_id,
            "category": category,
            "target_duration_minutes": int(payload.get("estimated_duration_minutes") or duration),
            "style": {
                "channel": CHANNEL_NAME,
                "host": "Ray",
                "tone": "fast, clear, credible, not salesy",
                "language": "en-US",
            },
            "structure": structure,
            "chapters": chapters,
        }

    raise RuntimeError("Unsupported script payload shape; missing 'structure' or convertible 'segments'")


def generate_mock_script(run_id: str, category: str, products: List[Dict], duration: int,
                         variation_plan: Optional[Dict] = None) -> Dict:
    """Generate a deterministic structured script for testing."""
    structure = []
    cat_display = category.replace("_", " ")

    # Use variation_plan for opener/CTA/disclosure if available
    vp_pi = (variation_plan or {}).get("prompt_instructions", {})
    vp_sel = (variation_plan or {}).get("selections", {})
    opener_style = vp_sel.get("opener_style", "overwhelm")
    editorial_format = vp_sel.get("editorial_format", "classic_top5")
    cta_line = vp_pi.get("cta_line", "")
    disclosure_text = vp_pi.get("disclosure_text", "")

    # Hook — vary based on opener_style
    hook_lines = {
        "overwhelm": (
            f"{cat_display.title()} in 2026 is more confusing than ever. "
            f"Tons of options, tons of jargon. So which one is actually worth your money? "
            f"I tested the top five and ranked them. Here's what I found."
        ),
        "mystery": (
            f"One of these five {cat_display} destroyed the competition. "
            f"The other four? Not even close. I tested all of them so you don't have to."
        ),
        "anti_shill": (
            f"Most {cat_display} reviews are paid ads disguised as opinions. "
            f"I bought these five with my own money and I'm going to tell you what they won't."
        ),
        "price_shock": (
            f"The cheapest {cat_display.rstrip('s')} here costs way less than you'd think. "
            f"The most expensive? Way more. But the best one isn't the most expensive."
        ),
        "personal_fail": (
            f"I wasted money on a terrible {cat_display.rstrip('s')} last year. "
            f"So this time I tested five of them properly. Here's what actually works."
        ),
    }
    hook_text = hook_lines.get(opener_style, hook_lines["overwhelm"])
    if editorial_format == "buy_skip_upgrade":
        hook_text += " And I’ll give each product a straight verdict: buy, skip, or upgrade."
    elif editorial_format == "persona_top3":
        hook_text += " I’ll also map each pick to the person it fits best."
    elif editorial_format == "one_winner_two_alts":
        hook_text += " You’ll leave with one winner and two realistic alternatives."
    elif editorial_format == "budget_vs_premium":
        hook_text += " And we’ll separate budget-safe picks from premium picks."

    structure.append({
        "id": "hook",
        "type": "NARRATION",
        "voice_text": hook_text,
        "on_screen": [f"Top 5 {cat_display.title()} 2026", "Which one wins?"],
        "visual_hint": "abstract b-roll / channel identity with product montage",
    })

    # Credibility
    structure.append({
        "id": "credibility",
        "type": "NARRATION",
        "voice_text": (
            f"I've been testing {cat_display} for the past two weeks. Real daily use, not just unboxing. "
            "I ranked these based on three things: performance, build quality, and value for money."
        ),
        "on_screen": ["2 weeks testing", "3 ranking criteria"],
        "visual_hint": "desk setup with multiple products being tested side by side",
    })

    # Product blocks
    for p in products:
        rank = p["rank"]
        title = p["title"]
        price = p["price"]
        rating = p["rating"]
        reviews = p["reviews"]

        block = {
            "id": f"p{rank}_intro",
            "type": "PRODUCT_BLOCK",
            "product_rank": rank,
            "segments": [
                {
                    "kind": "AVATAR_TALK",
                    "voice_text": (
                        f"Number {6-rank}. The {title}. "
                        f"At ${price:.2f} with a {rating} star rating from {reviews:,} reviews, "
                        "this one caught my attention right away."
                    ),
                    "visual_hint": f"Ray holding {title}, clean studio, confident expression",
                },
                {
                    "kind": "PRODUCT_GLAM",
                    "voice_text": (
                        f"The build quality is solid. It feels premium in hand. "
                        f"But here's the thing — it's not perfect. "
                        f"The setup took longer than I expected, and the instructions could be better."
                    ),
                    "visual_hint": f"product hero shot of {title}, clean 16:9, leave space for DaVinci price overlay",
                },
                {
                    "kind": "BROLL",
                    "voice_text": (
                        f"If you work from home and want something reliable, this is a solid pick. "
                        f"If you need something portable, skip this one."
                    ),
                    "visual_hint": f"use-case scene: person using {title} at a home office desk",
                },
            ],
            "cta": {
                "affiliate_disclaimer_short": "Links may earn a commission.",
                "on_screen_price_note": "Price may change.",
            },
        }
        verdict_map = {
            1: "BUY",
            2: "BUY",
            3: "UPGRADE",
            4: "SKIP",
            5: "SKIP",
        }
        if editorial_format == "buy_skip_upgrade":
            block["segments"].append(
                {
                    "kind": "NARRATION",
                    "role": "evidence",
                    "voice_text": (
                        f"Verdict for {title}: {verdict_map.get(rank, 'SKIP')}. "
                        f"I'm basing this on real-world trade-offs, not just specs."
                    ),
                    "visual_hint": "simple verdict card, large text BUY/SKIP/UPGRADE",
                }
            )
        elif editorial_format == "persona_top3":
            persona = ["remote worker", "student", "casual creator", "power user", "first-time buyer"][rank - 1]
            block["segments"].append(
                {
                    "kind": "NARRATION",
                    "role": "evidence",
                    "voice_text": (
                        f"Best persona fit: {persona}. "
                        f"If you're not that user profile, this might not be your best choice."
                    ),
                    "visual_hint": "persona label card with icon and short rationale",
                }
            )
        elif editorial_format == "one_winner_two_alts":
            alt_note = "alternative" if rank in (2, 3) else "not an alternative pick"
            block["segments"].append(
                {
                    "kind": "NARRATION",
                    "role": "evidence",
                    "voice_text": (
                        f"In the final decision, this is {alt_note}. "
                        f"The trade-off comes down to value versus convenience."
                    ),
                    "visual_hint": "winner-versus-alternatives comparison card",
                }
            )
        elif editorial_format == "budget_vs_premium":
            lane = "budget lane" if price < 150 else "premium lane"
            block["segments"].append(
                {
                    "kind": "NARRATION",
                    "role": "evidence",
                    "voice_text": (
                        f"This sits in the {lane}. "
                        f"If you're price-sensitive, compare it directly against the best budget pick."
                    ),
                    "visual_hint": "budget vs premium lane split graphic",
                }
            )
        structure.append(block)

    # Winner reinforcement
    winner = products[0]["title"]
    structure.append({
        "id": "winner",
        "type": "NARRATION",
        "voice_text": (
            f"So who wins? If you only buy one thing from this list, get the {winner}. "
            f"It's not the cheapest, but it's the best overall value. "
            f"Check the links below for current pricing."
        ),
        "on_screen": [f"Winner: {winner}", "Links in description"],
        "visual_hint": "side-by-side comparison of top 3 products, winner highlighted",
    })

    # Outro — use CTA and disclosure from variation_plan if available
    outro_cta = cta_line or "If this helped, subscribe for more."
    outro_disclosure = disclosure_text or "Disclosure: this video contains affiliate links and was produced with AI assistance."
    structure.append({
        "id": "outro",
        "type": "NARRATION",
        "voice_text": (
            f"That's the top five {cat_display} for 2026. "
            "There's no single perfect product for everyone — the right pick depends on your setup and budget. "
            f"{outro_cta} "
            f"{outro_disclosure}"
        ),
        "on_screen": ["Subscribe", "AI + affiliate disclosure"],
        "visual_hint": "channel outro card with subscribe button",
    })

    # Build chapters
    chapters = [{"timecode": "00:00", "title": "Intro"}]
    est_sec = 25  # after hook
    for p in products:
        rank = p["rank"]
        mm = est_sec // 60
        ss = est_sec % 60
        title_prefix = f"#{6-rank}"
        if editorial_format == "buy_skip_upgrade":
            title_prefix = f"{title_prefix} Buy/Skip"
        elif editorial_format == "persona_top3":
            title_prefix = f"{title_prefix} Persona Fit"
        elif editorial_format == "one_winner_two_alts":
            title_prefix = f"{title_prefix} Winner Lens"
        elif editorial_format == "budget_vs_premium":
            title_prefix = f"{title_prefix} Budget vs Premium"
        chapters.append({"timecode": f"{mm:02d}:{ss:02d}", "title": f"{title_prefix} {p['title'][:34]}"})
        est_sec += 90  # ~90s per product

    mm = est_sec // 60
    ss = est_sec % 60
    chapters.append({"timecode": f"{mm:02d}:{ss:02d}", "title": "Final Verdict"})

    return {
        "run_id": run_id,
        "category": category,
        "target_duration_minutes": duration,
        "style": {
            "channel": CHANNEL_NAME,
            "host": "Ray",
            "tone": "fast, clear, credible, not salesy",
            "language": "en-US",
        },
        "structure": structure,
        "chapters": chapters,
    }


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _count_openclaw_processes() -> int:
    """Count running openclaw/openclaw-channels processes (best-effort)."""
    try:
        res = subprocess.run(
            ["ps", "-axo", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return 0
    if res.returncode != 0:
        return 0
    count = 0
    for line in (res.stdout or "").splitlines():
        text = line.strip()
        if not text or "openclaw_recover.sh" in text:
            continue
        if re.search(r"(^|\s)openclaw(\s|$)", text) or re.search(r"(^|\s)openclaw-channels(\s|$)", text):
            count += 1
    return count


def _guard_openclaw_process_pressure(log: logging.Logger) -> None:
    """Warn/block if local OpenClaw process count indicates likely process storm."""
    guard_raw = os.environ.get("RAYVIEWS_OPENCLAW_PROC_GUARD", "1").strip().lower()
    if guard_raw in {"0", "false", "off", "no"}:
        return

    warn_threshold = _env_int("RAYVIEWS_OPENCLAW_PROC_WARN", 35)
    block_threshold = _env_int("RAYVIEWS_OPENCLAW_PROC_BLOCK", 120)
    if block_threshold < warn_threshold:
        block_threshold = warn_threshold

    count = _count_openclaw_processes()
    if count >= block_threshold:
        raise RuntimeError(
            "OpenClaw process pressure too high "
            f"({count} >= {block_threshold}). "
            "Run: tools/openclaw_recover.sh --apply --restart-browser"
        )
    if count >= warn_threshold:
        log.warning(
            "OpenClaw process pressure elevated (%d >= %d). "
            "If run gets slow, execute tools/openclaw_recover.sh",
            count,
            warn_threshold,
        )


def generate_script_chatgpt_ui(
    run_dir: Path,
    run_id: str,
    category: str,
    products: List[Dict],
    duration: int,
    log: logging.Logger,
    variation_plan: Optional[Dict] = None,
) -> Dict:
    """Generate script via ChatGPT web UI, automated by OpenClaw browser.

    This intentionally avoids any LLM API usage. It relies on the user being logged into
    chatgpt.com inside the OpenClaw browser profile.
    """
    from video_pipeline_lib import build_structured_script_prompt, Product
    from chatgpt_ui import ChatGPTUIError, extract_json_object, send_prompt_and_wait_for_assistant

    _guard_openclaw_process_pressure(log)

    product_objs = []
    for p in products:
        safe_title = _sanitize_prompt_field(
            p.get("title", ""),
            source=f"products.title:{p.get('asin', '')}",
            log=log,
        )
        safe_product_url = _sanitize_prompt_field(
            p.get("product_url", ""),
            source=f"products.product_url:{p.get('asin', '')}",
            log=log,
        )
        safe_affiliate_url = _sanitize_prompt_field(
            p.get("affiliate_url", ""),
            source=f"products.affiliate_url:{p.get('asin', '')}",
            log=log,
        )
        product_objs.append(
            Product(
                product_title=safe_title,
                asin=p["asin"],
                current_price_usd=p["price"],
                rating=p["rating"],
                review_count=p["reviews"],
                feature_bullets=[],
                amazon_url=safe_product_url,
                affiliate_url=safe_affiliate_url,
                ranking_score=p["rank"],
            )
        )

    prompt = build_structured_script_prompt(product_objs, category, CHANNEL_NAME, variation_plan)
    src_dir = run_dir / "security"
    src_dir.mkdir(parents=True, exist_ok=True)
    conv_path = src_dir / "chatgpt_conversation_url.txt"

    def try_generate() -> Dict[str, Any]:
        out = send_prompt_and_wait_for_assistant(
            prompt,
            timeout_sec=300,
            poll_sec=2.5,
            timeout_ms=30000,
        )
        conv_url = str(out.get("conversation_url", "") or "").strip()
        if conv_url:
            atomic_write_text(conv_path, conv_url + "\n")
        raw_text = str(out.get("assistant_text", "") or "")
        try:
            payload = extract_json_object(raw_text)
        except ChatGPTUIError as e:
            raise RuntimeError(str(e)) from None

        return _normalize_script_payload(
            payload=payload,
            run_id=run_id,
            category=category,
            products=products,
            duration=duration,
        )

    return with_retries(try_generate, max_attempts=3, label="script_generation:chatgpt_ui", logger=log)


def generate_script_minimax(run_id: str, category: str, products: List[Dict],
                             duration: int, log: logging.Logger,
                             variation_plan: Optional[Dict] = None) -> Dict:
    """Generate script via MiniMax API (OpenAI-compatible chat completions)."""
    from video_pipeline_lib import build_structured_script_prompt, Product

    product_objs = []
    for p in products:
        safe_title = _sanitize_prompt_field(
            p.get("title", ""),
            source=f"products.title:{p.get('asin', '')}",
            log=log,
        )
        safe_product_url = _sanitize_prompt_field(
            p.get("product_url", ""),
            source=f"products.product_url:{p.get('asin', '')}",
            log=log,
        )
        safe_affiliate_url = _sanitize_prompt_field(
            p.get("affiliate_url", ""),
            source=f"products.affiliate_url:{p.get('asin', '')}",
            log=log,
        )
        product_objs.append(Product(
            product_title=safe_title,
            asin=p["asin"],
            current_price_usd=p["price"],
            rating=p["rating"],
            review_count=p["reviews"],
            feature_bullets=[],
            amazon_url=safe_product_url,
            affiliate_url=safe_affiliate_url,
            ranking_score=p["rank"],
        ))

    prompt = build_structured_script_prompt(product_objs, category, CHANNEL_NAME, variation_plan)
    messages = [
        {"role": "system", "content": "You are a YouTube script generator. Return ONLY valid JSON, no markdown fences."},
        {"role": "user", "content": prompt},
    ]

    def _call_minimax(messages_in: List[Dict[str, str]], *, label: str, timeout_sec: int) -> str:
        def _do():
            return minimax_chat(
                messages_in,
                max_tokens=8192,
                temperature=0.7,
                timeout_sec=timeout_sec,
                logger=log,
            )
        return with_retries(_do, max_attempts=3, backoff=[10, 30, 60], label=label, logger=log)

    def try_generate():
        raw = _call_minimax(messages, label="minimax_chat", timeout_sec=180)
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return _normalize_script_payload(
            payload=json.loads(text),
            run_id=run_id,
            category=category,
            products=products,
            duration=duration,
        )

    script_data = with_retries(try_generate, max_attempts=3, label="minimax_script", logger=log)

    # Length hardening: if model returns short script, request an expansion pass.
    min_words = 1100
    current_words = count_script_words(script_data)
    if current_words < min_words:
        log.warning(
            f"MiniMax script below target words ({current_words} < {min_words}); requesting expansion pass"
        )
        for attempt in range(2):
            expansion_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a YouTube script editor. Expand the provided JSON script to 1200-1600 words. "
                        "Keep JSON schema unchanged, maintain product order and ids, keep tone human and credible. "
                        "Return ONLY valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Category: {category}\n"
                        f"Target duration: {duration} minutes\n"
                        f"Current word count: {current_words}\n\n"
                        f"CURRENT_SCRIPT_JSON:\n{json.dumps(script_data, ensure_ascii=False)}"
                    ),
                },
            ]
            try:
                raw = _call_minimax(expansion_messages, label=f"minimax_expand_{attempt+1}", timeout_sec=240)
                text = raw.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```$", "", text)
                expanded = _normalize_script_payload(
                    payload=json.loads(text),
                    run_id=run_id,
                    category=category,
                    products=products,
                    duration=duration,
                )
                expanded_words = count_script_words(expanded)
                if expanded_words >= min_words:
                    script_data = expanded
                    current_words = expanded_words
                    log.info(f"Expansion pass succeeded: {expanded_words} words")
                    break
                script_data = expanded
                current_words = expanded_words
                log.warning(
                    f"Expansion pass {attempt + 1} still short ({expanded_words} words)"
                )
            except Exception as exc:
                log.warning(f"Expansion pass {attempt + 1} failed: {exc}")

    # Repair pass: if script still violates hard schema requirements, ask MiniMax to fix specific issues.
    hard_errors = validate_script_json(script_data)
    if hard_errors:
        log.warning(f"MiniMax script still failing validation; attempting repair: {hard_errors}")
        for attempt in range(2):
            repair_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a structured script fixer. Fix the provided JSON so it passes these checks:\n"
                        "- Must represent exactly 5 products (include PRODUCT_INTRO/DEMO/REVIEW/RANK for each)\n"
                        "- Must be 1100-1900 words total\n"
                        "- Must remain valid JSON with the SAME schema as the input (do not change keys)\n"
                        "Return ONLY valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Category: {category}\n"
                        f"Target duration: {duration} minutes\n"
                        f"VALIDATION_ERRORS:\n- " + "\n- ".join(hard_errors) + "\n\n"
                        f"INPUT_PRODUCTS:\n{json.dumps([{'rank': p['rank'], 'asin': p['asin'], 'title': p['title'], 'price': p['price'], 'rating': p['rating'], 'reviews': p['reviews']} for p in products], ensure_ascii=False)}\n\n"
                        f"CURRENT_SCRIPT_JSON:\n{json.dumps(script_data, ensure_ascii=False)}"
                    ),
                },
            ]
            try:
                raw = _call_minimax(repair_messages, label=f"minimax_repair_{attempt+1}", timeout_sec=240)
                text = raw.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```$", "", text)
                repaired = _normalize_script_payload(
                    payload=json.loads(text),
                    run_id=run_id,
                    category=category,
                    products=products,
                    duration=duration,
                )
                errs = validate_script_json(repaired)
                if not errs:
                    script_data = repaired
                    log.info("Repair pass succeeded")
                    break
                hard_errors = errs
                log.warning(f"Repair pass {attempt + 1} still failing: {errs}")
            except Exception as exc:
                log.warning(f"Repair pass {attempt + 1} failed: {exc}")

    return script_data


# ===================================================================
# STEP 3: generate-assets
# ===================================================================

def cmd_generate_assets(args):
    run_dir, run_id, run_config = load_run(args)
    _run_learning_gate(run_id, "assets")
    log = setup_logger(run_dir, "03_assets")
    manifest_path = run_dir / "assets_manifest.json"

    require_gate_approved(run_dir, run_config, "gate1", "generate-assets", log)
    _require_expensive_steps_allowed(run_dir, run_config, "generate-assets", log)

    if manifest_path.exists() and not args.force:
        log.info("assets_manifest.json already exists, skipping")
        print(f"[SKIP] assets_manifest.json exists")
        return

    script_path = run_dir / "script.json"
    products_path = run_dir / "products.json"
    if not script_path.exists():
        raise RuntimeError("script.json not found — run generate-script first")
    if not products_path.exists():
        raise RuntimeError("products.json not found — run discover-products first")

    products_data = json.loads(products_path.read_text(encoding="utf-8"))
    products = products_data["products"]

    log.info(f"Generating asset prompts for {len(products)} products")

    assets = []
    for p in products:
        rank = p["rank"]
        asin = p["asin"]
        title = p["title"]
        product_dir = run_dir / "assets" / f"product_{rank}"
        product_dir.mkdir(parents=True, exist_ok=True)

        # Best-effort: download an Amazon reference image for Dzine anchoring.
        # This is not a hard requirement (manual fallback is allowed).
        ref_path = product_dir / "ref_amazon.jpg"
        if not ref_path.exists() or args.force:
            img_url = str(p.get("image_url", "") or "").strip()
            if img_url:
                try:
                    req = Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urlopen(req, timeout=25) as resp:
                        blob = resp.read()
                    if len(blob) < 30_000:
                        raise RuntimeError(f"download too small ({len(blob)} bytes)")
                    tmp = ref_path.with_suffix(ref_path.suffix + ".tmp")
                    with open(tmp, "wb") as f:
                        f.write(blob)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, ref_path)
                    log.info(f"Downloaded ref image: {ref_path.name} ({len(blob)} bytes) for {asin}")
                except Exception as exc:
                    log.warning(f"Ref image download failed for {asin}: {exc}")
            else:
                log.warning(f"No image_url for {asin}; cannot download ref image")

        asset_entry = {
            "product_rank": rank,
            "asin": asin,
            "title": title,
            "required": {
                "dzine_variants": 3,
                "thumbnail_variants": 2,
            },
            "files": {
                "product_ref_image": f"assets/product_{rank}/ref_amazon.jpg",
                "dzine_images": [
                    f"assets/product_{rank}/variant_01.png",
                    f"assets/product_{rank}/variant_02.png",
                    f"assets/product_{rank}/variant_03.png",
                ],
                "avatar_lipsync_stills": [
                    f"assets/product_{rank}/ray_talk_01.png",
                ],
                "thumbnail_candidates": [
                    "assets/thumbnail/option_01.png",
                    "assets/thumbnail/option_02.png",
                ],
            },
            "dzine_prompts": {
                "hero_shot": (
                    f"Model: NanoBanana Pro. Character: Ray, confident reviewer. "
                    f"Hero clean shot: Ray presenting {title} in a clean modern set, "
                    f"medium shot, realistic lighting, 16:9. "
                    f"No text in image, no price in image, leave negative space for DaVinci price overlay. "
                    f"RayViewsLab brand style."
                ),
                "use_case": (
                    f"Model: NanoBanana Pro. In-use scene: person using {title} "
                    f"naturally in a home office/lifestyle setup, high detail, 16:9."
                ),
                "close_up": (
                    f"Model: NanoBanana Pro. Close-up feature shot of {title}: "
                    f"emphasize one practical benefit visually, product clearly visible, 16:9."
                ),
            },
            "status": "pending",
        }

        # Check which files already exist — all categories must be complete
        all_ready = True
        for key in ["dzine_images", "thumbnail_candidates", "avatar_lipsync_stills"]:
            files = asset_entry["files"][key]
            existing = [f for f in files if (run_dir / f).exists()]
            if len(existing) < len(files):
                all_ready = False
                break
        if all_ready:
            asset_entry["status"] = "ready"

        assets.append(asset_entry)

    manifest = {
        "run_id": run_id,
        "assets": assets,
    }

    atomic_write_json(manifest_path, manifest)
    ready = sum(1 for a in assets if a["status"] == "ready")
    log.info(f"Assets manifest: {ready}/{len(assets)} products ready")

    mark_step_complete(run_dir, "generate-assets")
    log_ops_event(run_id, "assets_manifest_created", {"products": len(assets), "ready": ready})
    print(f"[OK] assets_manifest.json: {ready}/{len(assets)} ready → {manifest_path}")

    if ready < len(assets):
        print(f"[ACTION] Generate images in Dzine using prompts in assets_manifest.json")


# ===================================================================
# STEP 4: generate-voice
# ===================================================================

def cmd_generate_voice(args):
    run_dir, run_id, run_config = load_run(args)
    _run_learning_gate(run_id, "tts")
    log = setup_logger(run_dir, "04_voice")
    voice_dir = run_dir / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    timestamps_path = voice_dir / "timestamps.json"

    require_gate_approved(run_dir, run_config, "gate1", "generate-voice", log)
    _require_expensive_steps_allowed(run_dir, run_config, "generate-voice", log)

    if timestamps_path.exists() and not args.force:
        log.info("timestamps.json already exists, skipping")
        print(f"[SKIP] voice/timestamps.json exists")
        return

    script_path = run_dir / "script.json"
    if not script_path.exists():
        raise RuntimeError("script.json not found — run generate-script first")

    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    config = run_config.get("config", {})
    voice = config.get("voice", DEFAULT_VOICE)

    log.info(f"Processing voice segments for: {voice}")

    # Extract all narration in order
    segments = []
    total_chars = 0
    cumulative_ms = 0

    for seg in script_data.get("structure", []):
        seg_id = seg.get("id", "unknown")
        voice_text = seg.get("voice_text", "")

        if voice_text:
            words = len(voice_text.split())
            est_ms = int(words / 155 * 60 * 1000)  # ~155 wpm
            segments.append({
                "script_id": seg_id,
                "start_ms": cumulative_ms,
                "end_ms": cumulative_ms + est_ms,
            })
            cumulative_ms += est_ms
            total_chars += len(voice_text)

        # Sub-segments in PRODUCT_BLOCK
        for sub in seg.get("segments", []):
            sub_voice = sub.get("voice_text", "")
            if sub_voice:
                words = len(sub_voice.split())
                est_ms = int(words / 155 * 60 * 1000)
                segments.append({
                    "script_id": f"{seg_id}_{sub.get('kind', 'seg')}",
                    "start_ms": cumulative_ms,
                    "end_ms": cumulative_ms + est_ms,
                })
                cumulative_ms += est_ms
                total_chars += len(sub_voice)

    timestamps = {
        "run_id": run_id,
        "voice_model": f"elevenlabs:{voice}",
        "segments": segments,
        "total_chars": total_chars,
        "estimated_duration_ms": cumulative_ms,
    }

    # Write full narration text for ElevenLabs
    all_text = extract_full_narration(script_data)
    atomic_write_text(voice_dir / "full_narration.txt", all_text)

    atomic_write_json(timestamps_path, timestamps)

    est_min = round(cumulative_ms / 60000, 1)
    log.info(f"Voice plan: {len(segments)} segments, {total_chars} chars, ~{est_min} min")

    mark_step_complete(run_dir, "generate-voice")
    log_ops_event(run_id, "voice_planned", {"segments": len(segments), "chars": total_chars})
    print(f"[OK] voice/timestamps.json: {len(segments)} segments, ~{est_min} min")

    wav_path = voice_dir / "voiceover.mp3"
    if not wav_path.exists():
        if _voice_source_requests_tts(getattr(args, "source", "mock")):
            log.info("Calling ElevenLabs TTS API...")
            narration = extract_full_narration(script_data)
            def do_tts():
                return elevenlabs_tts(narration, wav_path, logger=log)
            with_retries(do_tts, max_attempts=2, backoff=[10, 30], label="elevenlabs_tts", logger=log)
            print(f"[OK] voiceover.mp3 generated ({wav_path.stat().st_size / 1024:.0f}KB)")
        else:
            print(f"[ACTION] Generate voiceover using ElevenLabs ({voice})")
            print(f"         Full narration text: {voice_dir / 'full_narration.txt'}")
            print(f"         Or run: python3 tools/pipeline.py generate-voice --run-id {run_id} --source elevenlabs")


def extract_full_narration(script_data: Dict) -> str:
    parts = []
    for seg in script_data.get("structure", []):
        voice = seg.get("voice_text", "")
        if voice:
            parts.append(voice)
        for sub in seg.get("segments", []):
            sv = sub.get("voice_text", "")
            if sv:
                parts.append(sv)
    return "\n\n".join(parts)


def _voice_source_requests_tts(source: str) -> bool:
    mode = str(source or "").strip().lower()
    return mode in {"elevenlabs", "minimax", "openclaw"}


# ===================================================================
# STEP 5: build-davinci
# ===================================================================

def cmd_build_davinci(args):
    run_dir, run_id, run_config = load_run(args)
    _run_learning_gate(run_id, "manifest")
    log = setup_logger(run_dir, "05_davinci")
    davinci_dir = run_dir / "davinci"
    davinci_dir.mkdir(parents=True, exist_ok=True)
    project_path = davinci_dir / "project.json"

    require_gate_approved(run_dir, run_config, "gate1", "build-davinci", log)
    _require_expensive_steps_allowed(run_dir, run_config, "build-davinci", log)

    if project_path.exists() and not args.force:
        log.info("davinci/project.json already exists, skipping")
        print(f"[SKIP] davinci/project.json exists")
        return

    # Check prerequisites (gate2)
    missing = []
    script_path = run_dir / "script.json"
    manifest_path = run_dir / "assets_manifest.json"
    timestamps_path = run_dir / "voice" / "timestamps.json"
    wav_path = run_dir / "voice" / "voiceover.mp3"

    if not script_path.exists(): missing.append("script.json")
    if not manifest_path.exists(): missing.append("assets_manifest.json")
    if not timestamps_path.exists(): missing.append("voice/timestamps.json")

    if missing:
        log.error(f"build-davinci prerequisites missing: {missing}")
        raise RuntimeError(f"build-davinci failed — missing prerequisites: {', '.join(missing)}")

    # Load data
    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timestamps = json.loads(timestamps_path.read_text(encoding="utf-8"))

    log.info("Building DaVinci edit plan")

    # Build edit plan from timestamps + assets
    edit_plan = []
    asset_map = {}
    for a in manifest.get("assets", []):
        rank = a["product_rank"]
        images = a.get("files", {}).get("dzine_images", [])
        asset_map[rank] = images

    for seg in timestamps.get("segments", []):
        script_id = seg["script_id"]
        start = seg["start_ms"]
        end = seg["end_ms"]

        # Match product rank from script_id
        rank_match = re.search(r"p(\d+)", script_id)
        if rank_match:
            rank = int(rank_match.group(1))
            images = asset_map.get(rank, [])
            if images:
                duration_per = (end - start) // max(len(images), 1)
                for i, img in enumerate(images):
                    edit_plan.append({
                        "type": "IMAGE",
                        "path": img,
                        "start_ms": start + i * duration_per,
                        "end_ms": start + (i + 1) * duration_per,
                    })
                continue

        # Non-product segments get a placeholder
        edit_plan.append({
            "type": "PLACEHOLDER",
            "label": script_id,
            "start_ms": start,
            "end_ms": end,
        })

    config = run_config.get("config", {})
    resolution = config.get("resolution", "1920x1080")

    project = {
        "run_id": run_id,
        "timeline": {
            "resolution": resolution,
            "fps": config.get("fps", 30),
        },
        "audio": "voice/voiceover.mp3",
        "edit_plan": edit_plan,
        "captions": {"enabled": True, "style_preset": "clean"},
        "music": {"enabled": True, "duck_db": -12},
    }

    atomic_write_json(project_path, project)
    log.info(f"DaVinci project: {len(edit_plan)} edit items")

    # Check if we can set render_ready
    has_audio = wav_path.exists()
    has_all_images = all(
        (run_dir / img).exists()
        for a in manifest.get("assets", [])
        for img in a.get("files", {}).get("dzine_images", [])
    )

    if has_audio and has_all_images:
        flag = davinci_dir / "render_ready.flag"
        flag.write_text("ready", encoding="utf-8")
        log.info("render_ready.flag set")
        print(f"[OK] Gate2 PASS — render ready")
    else:
        blockers = []
        if not has_audio:
            blockers.append("voice/voiceover.mp3 missing")
        if not has_all_images:
            blockers.append("some dzine images missing")
        log.warning(f"Gate2 partial: {blockers}")
        print(f"[WARN] Gate2 not ready: {', '.join(blockers)}")

    mark_step_complete(run_dir, "build-davinci")
    log_ops_event(run_id, "davinci_built", {"edit_items": len(edit_plan), "render_ready": has_audio and has_all_images})
    print(f"[OK] davinci/project.json: {len(edit_plan)} items → {project_path}")


# ===================================================================
# STEP 5.5: convert-to-rayvault
# ===================================================================

def _notify_rayvault_conversion(
    run_id: str,
    run_config: Dict,
    result: Dict,
    log: logging.Logger,
) -> None:
    """Send Telegram notification with conversion results."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from lib.control_plane import send_telegram
    except ImportError:
        log.debug("control_plane not available, skipping Telegram")
        return

    status = result["status"]
    segments = result["segments"]
    fidelity = result["fidelity_score"]
    duration = result.get("audio_duration_sec", 0)
    category = run_config.get("category", "?").replace("_", " ").title()
    warnings = result.get("warnings", [])

    icon = "OK" if status == "READY_FOR_RENDER" else "AGUARDANDO"
    lines = [
        f"[{icon}] convert-to-rayvault",
        f"Run: {run_id}",
        f"Categoria: {category}",
        f"Status: {status}",
        f"Segments: {segments} | Fidelity: {fidelity}/100 | Duration: {duration:.0f}s",
    ]

    if warnings:
        lines.append("")
        for w in warnings[:5]:
            lines.append(f"  WARN: {w}")

    if status == "READY_FOR_RENDER":
        lines.append("")
        lines.append("Proximo: render no DaVinci ou shadow render.")
    elif status == "WAITING_ASSETS":
        lines.append("")
        lines.append("Acao necessaria: gerar voiceover + imagens Dzine.")

    msg = "\n".join(lines)
    ok = send_telegram(msg)
    if ok:
        log.info("Telegram notification sent")
    else:
        log.warning("Telegram notification failed (check TELEGRAM_CHAT_ID)")


def cmd_convert_to_rayvault(args):
    run_dir, run_id, run_config = load_run(args)
    log = setup_logger(run_dir, "05b_rayvault")
    rayvault_dir = run_dir / "rayvault"
    config_path = rayvault_dir / "05_render_config.json"

    require_gate_approved(run_dir, run_config, "gate1", "convert-to-rayvault", log)

    if config_path.exists() and not args.force:
        log.info("rayvault/05_render_config.json already exists, skipping")
        print(f"[SKIP] rayvault/05_render_config.json exists")
        return

    from markdown_to_render_config import convert

    log.info("Converting Rayviews run → RayVault format")
    result = convert(
        run_id=run_id,
        frame_path=getattr(args, "frame_path", None),
        force=args.force,
        dry_run=getattr(args, "dry_run", False),
        no_overlays=getattr(args, "no_overlays", False),
    )

    if result.get("status") == "DRY_RUN":
        log.info(f"Dry run: {result['segments_planned']} segments planned")
        print(f"[DRY RUN] {result['segments_planned']} segments")
        return

    log.info(f"RayVault conversion: {result['status']} | "
             f"segments={result['segments']} | fidelity={result['fidelity_score']}/100")

    for w in result.get("warnings", []):
        log.warning(w)

    mark_step_complete(run_dir, "convert-to-rayvault")
    log_ops_event(run_id, "rayvault_converted", {
        "status": result["status"],
        "segments": result["segments"],
        "fidelity_score": result["fidelity_score"],
    })
    print(f"[OK] convert-to-rayvault: {result['status']} | "
          f"segments={result['segments']} | fidelity={result['fidelity_score']}/100")
    print(f"     output: {result['rayvault_dir']}")

    # Telegram notification
    _notify_rayvault_conversion(run_id, run_config, result, log)


# ===================================================================
# STEP 5.6: validate-originality
# ===================================================================

def cmd_validate_originality(args):
    run_dir, run_id, _ = load_run(args)
    log = setup_logger(run_dir, "05c_originality")
    report_path = run_dir / "originality_report.json"

    if report_path.exists() and not args.force:
        log.info("originality_report.json already exists, skipping")
        print(f"[SKIP] originality_report.json exists")
        return

    from rayvault.originality_validator import run_validation, write_report

    policy_json = str(getattr(args, "policy_json", "") or "").strip()
    policy = {}
    if policy_json:
        try:
            parsed = json.loads(policy_json)
            if isinstance(parsed, dict):
                policy = parsed
        except Exception as exc:
            raise RuntimeError(f"Invalid --policy-json: {exc}") from exc

    report = run_validation(run_dir, policy or None)
    write_report(run_dir, report)

    status = str(report.get("status", "FAIL")).upper()
    exit_code = int(report.get("exit_code", 2))
    reasons = report.get("reasons", [])
    log.info(f"Originality report: status={status} exit_code={exit_code}")
    for r in reasons:
        log.warning(f"Originality: {r}")

    mark_step_complete(run_dir, "validate-originality")
    log_ops_event(
        run_id,
        "originality_validated",
        {
            "status": status,
            "exit_code": exit_code,
            "reasons": reasons[:10],
        },
    )
    print(f"[OK] originality_report.json: {status} → {report_path}")


# ===================================================================
# STEP 5.7: validate-compliance
# ===================================================================

def cmd_validate_compliance(args):
    run_dir, run_id, _ = load_run(args)
    log = setup_logger(run_dir, "05d_compliance")
    report_path = run_dir / "compliance_report.json"

    if report_path.exists() and not args.force:
        log.info("compliance_report.json already exists, skipping")
        print(f"[SKIP] compliance_report.json exists")
        return

    from rayvault.compliance_contract import run_contract

    report = run_contract(run_dir)
    status = str(report.get("status", "FAIL")).upper()
    exit_code = int(report.get("exit_code", 2))
    reasons = report.get("reasons", [])
    log.info(f"Compliance report: status={status} exit_code={exit_code}")
    for r in reasons:
        log.warning(f"Compliance: {r}")

    mark_step_complete(run_dir, "validate-compliance")
    log_ops_event(
        run_id,
        "compliance_validated",
        {
            "status": status,
            "exit_code": exit_code,
            "reasons": reasons[:10],
        },
    )
    print(f"[OK] compliance_report.json: {status} → {report_path}")


# ===================================================================
# STEP 6: render-and-upload
# ===================================================================

def _retry_backoff(base_sec: int, attempts: int) -> List[float]:
    out = []
    for i in range(max(0, attempts - 1)):
        out.append(float(base_sec * (3 ** i)))
    return out or [5.0]


def _run_cmd_checked(cmd: List[str], *, cwd: Optional[Path], label: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"{label} failed ({proc.returncode}): {stderr[:500]}")
    return proc


def cmd_render_and_upload(args):
    run_dir, run_id, run_config = load_run(args)
    log = setup_logger(run_dir, "06_upload")
    upload_dir = run_dir / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    url_path = upload_dir / "youtube_url.txt"
    video_id_path = upload_dir / "youtube_video_id.txt"

    if url_path.exists() and not args.force:
        log.info("youtube_url.txt already exists, skipping")
        print(f"[SKIP] Already uploaded: {url_path.read_text(encoding='utf-8').strip()}")
        return

    require_gate_approved(run_dir, run_config, "gate2", "render-and-upload", log)
    _require_expensive_steps_allowed(run_dir, run_config, "render-and-upload", log)
    auto_checks = _pre_gate2_auto_checks(run_dir)
    if not auto_checks.get("ok_for_gate2", False):
        raise RuntimeError(
            "render-and-upload blocked: automatic pre-Gate2 contracts failed/missing "
            f"({', '.join(auto_checks.get('fail_items', []))})"
        )

    flag = run_dir / "davinci" / "render_ready.flag"
    if not flag.exists():
        log.error("render_ready.flag not found — build-davinci not complete or gate2 blocked")
        raise RuntimeError("render_ready.flag not found")

    retries = max(1, int(getattr(args, "step_retries", 3)))
    backoff = _retry_backoff(int(getattr(args, "step_backoff_sec", 8)), retries)
    log.info(f"Render + upload step (retries={retries}, backoff={backoff})")

    # Ensure upload payload exists
    script_path = run_dir / "script.json"
    upload_payload_path = upload_dir / "upload_payload.json"
    if script_path.exists():
        script = json.loads(script_path.read_text(encoding="utf-8"))
        if not upload_payload_path.exists() or args.force:
            tracking_override = str(
                getattr(args, "tracking_id_override", "")
                or run_config.get("config", {}).get("tracking_id_override", "")
                or ""
            ).strip()
            payload = {
                "run_id": run_id,
                "video_file": "davinci/render.mp4",
                "title": f"Top 5 Best {run_config['category'].replace('_', ' ').title()} 2026",
                "description": build_youtube_description(
                    script,
                    run_config,
                    tracking_id_override=tracking_override,
                ),
                "tags": [run_config["category"].replace("_", " "), "top 5", "best 2026", "review"],
                "category_id": "28",
                "privacy_status": getattr(args, "privacy_status", "private"),
                "chapters": script.get("chapters", []),
            }
            if tracking_override:
                payload["tracking_id_override"] = tracking_override
            atomic_write_json(upload_payload_path, payload)
            log.info("Upload payload written")
    if not upload_payload_path.exists():
        raise RuntimeError("upload/upload_payload.json not found and script.json missing")

    # Render (RayVault ffmpeg engine)
    rayvault_run_dir = run_dir / "rayvault"
    render_cfg = rayvault_run_dir / "05_render_config.json"
    if not render_cfg.exists():
        raise RuntimeError(
            "rayvault/05_render_config.json not found. Run convert-to-rayvault first."
        )

    final_render = rayvault_run_dir / "publish" / "video_final.mp4"
    davinci_render = run_dir / "davinci" / "render.mp4"

    if not final_render.exists() or args.force:
        def do_render() -> Path:
            cmd = [
                sys.executable,
                "-m",
                "rayvault.ffmpeg_render",
                "--run-dir",
                str(rayvault_run_dir),
                "--apply",
            ]
            _run_cmd_checked(cmd, cwd=BASE_DIR, label="rayvault_render")
            if not final_render.exists():
                raise RuntimeError("rayvault_render completed without publish/video_final.mp4")
            return final_render

        with_retries(
            do_render,
            max_attempts=retries,
            backoff=backoff,
            label="rayvault_render",
            logger=log,
        )
        log.info(f"Render created: {final_render}")
    else:
        log.info(f"Render already exists, reusing: {final_render}")

    # Keep a canonical path in run_dir/davinci/render.mp4 for downstream tooling.
    if final_render.exists():
        davinci_render.parent.mkdir(parents=True, exist_ok=True)
        if args.force or not davinci_render.exists():
            tmp = davinci_render.with_suffix(".tmp")
            with open(final_render, "rb") as src, open(tmp, "wb") as dst:
                while True:
                    chunk = src.read(8 * 1024 * 1024)  # 8MB chunks
                    if not chunk:
                        break
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(tmp, davinci_render)

    # Save artifact checksums for audit trail
    checksums = compute_artifact_checksums(run_dir)
    atomic_write_json(upload_dir / "artifact_checksums.json", checksums)
    log.info(f"Artifact checksums saved: {len(checksums)} files")

    client_secrets = str(getattr(args, "youtube_client_secrets", "") or "").strip()
    if not client_secrets:
        raise RuntimeError(
            "Missing --youtube-client-secrets. Render completed; upload blocked by policy."
        )

    input_video = str(getattr(args, "video_file", "") or "").strip()
    video_file = Path(input_video).expanduser() if input_video else davinci_render
    if not video_file.exists():
        raise RuntimeError(f"Video file for upload not found: {video_file}")

    upload_report = upload_payload_path.with_name("youtube_upload_report.json")

    def do_upload() -> Dict[str, Any]:
        if upload_report.exists() and not args.force:
            cached = json.loads(upload_report.read_text(encoding="utf-8"))
            if cached.get("ok") and cached.get("video_id"):
                return cached

        cmd = [
            sys.executable,
            str(BASE_DIR / "tools" / "youtube_upload_api.py"),
            "--client-secrets",
            client_secrets,
            "--video-file",
            str(video_file),
            "--metadata-json",
            str(upload_payload_path),
            "--privacy-status",
            getattr(args, "privacy_status", "private"),
        ]

        token_file = str(getattr(args, "youtube_token_file", "") or "").strip()
        if token_file:
            cmd.extend(["--token-file", token_file])

        thumb = str(getattr(args, "thumbnail", "") or "").strip()
        if thumb:
            cmd.extend(["--thumbnail", thumb])
        else:
            auto_thumb = run_dir / "assets" / "thumbnail" / "option_01.png"
            if auto_thumb.exists():
                cmd.extend(["--thumbnail", str(auto_thumb)])

        _run_cmd_checked(cmd, cwd=BASE_DIR, label="youtube_upload")
        if not upload_report.exists():
            raise RuntimeError("youtube_upload_report.json missing after upload")
        report = json.loads(upload_report.read_text(encoding="utf-8"))
        if not report.get("ok"):
            raise RuntimeError(f"YouTube upload failed: {report}")
        return report

    report = with_retries(
        do_upload,
        max_attempts=retries,
        backoff=backoff,
        label="youtube_upload",
        logger=log,
    )

    youtube_url = str(report.get("url", "")).strip()
    video_id = str(report.get("video_id", "")).strip()
    if not youtube_url or not video_id:
        raise RuntimeError(f"Upload report missing url/video_id: {report}")

    atomic_write_text(url_path, youtube_url + "\n")
    atomic_write_text(video_id_path, video_id + "\n")

    mark_step_complete(run_dir, "render-and-upload")
    log_ops_event(run_id, "upload_done", {"video_id": video_id, "url": youtube_url})
    print(f"[OK] Uploaded: {youtube_url}")


def _description_product_link(product: Dict[str, Any], tracking_id_override: str = "") -> str:
    aff = str(product.get("affiliate_url", "")).strip()
    prod = str(product.get("product_url", "")).strip()
    if tracking_id_override:
        # Per-video tracking: force direct Amazon URL with override when possible.
        if prod:
            return append_affiliate_tag(prod, tracking_id_override)
        if aff and not _is_amzn_short_url(aff):
            return append_affiliate_tag(aff, tracking_id_override)
    return aff or prod


def build_youtube_description(
    script: Dict,
    run_config: Dict,
    tracking_id_override: str = "",
) -> str:
    disclosure_en = "As an Amazon Associate I earn from qualifying purchases."
    disclosure_pt = "Como Associado da Amazon, eu ganho com compras qualificadas."

    lines: List[str] = []
    category = run_config.get("category", "").replace("_", " ").title()
    lines.append(f"Top 5 Best {category} in 2026 — tested and ranked.")
    lines.append(disclosure_en)
    lines.append(disclosure_pt)
    lines.append("")

    # Chapters
    for ch in script.get("chapters", []):
        lines.append(f"{ch['timecode']} {ch['title']}")
    lines.append("")

    # Products with affiliate links
    lines.append("Affiliate Links (Amazon):")
    products_path = get_run_dir(run_config.get("run_id", script.get("run_id", ""))) / "products.json"
    if products_path.exists():
        pd = json.loads(products_path.read_text(encoding="utf-8"))
        for p in pd.get("products", []):
            rank = p.get("rank", "?")
            title = p.get("title", "?")
            price = p.get("price")
            link = _description_product_link(p, tracking_id_override=tracking_id_override)
            price_label = f"${float(price):.2f}" if isinstance(price, (int, float)) else ""
            lines.append(f"Product {rank} — {title} {price_label}".strip())
            lines.append(link)
            lines.append("")

    lines.append(disclosure_en)
    lines.append("Prices may change. Check the links for current price and availability.")
    lines.append("This video was produced with AI assistance.")
    return "\n".join(lines).strip()


# ===================================================================
# STEP 7: collect-metrics
# ===================================================================

def cmd_collect_metrics(args):
    run_dir, run_id, run_config = load_run(args)
    log = setup_logger(run_dir, "07_metrics")
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = metrics_dir / "metrics.json"

    if metrics_path.exists() and not args.force:
        log.info("metrics.json already exists, skipping")
        print(f"[SKIP] metrics.json exists")
        return

    url_path = run_dir / "upload" / "youtube_url.txt"
    vid_path = run_dir / "upload" / "youtube_video_id.txt"

    video_id = ""
    if vid_path.exists():
        video_id = vid_path.read_text(encoding="utf-8").strip()
    elif url_path.exists():
        url = url_path.read_text(encoding="utf-8").strip()
        parsed = urlparse(url)
        video_id = parse_qs(parsed.query).get("v", [""])[0]

    if not video_id:
        log.error("No video ID found — upload step not complete")
        raise RuntimeError("No youtube_video_id.txt or youtube_url.txt")

    log.info(f"Collecting metrics for video: {video_id}")

    # Fetch from YouTube API
    yt_env = CONFIG_DIR / "youtube.env"
    api_key = ""
    if yt_env.exists():
        for line in yt_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("YOUTUBE_API_KEY="):
                api_key = line.split("=", 1)[1].strip()

    if not api_key:
        log.error("YouTube API key not configured")
        raise RuntimeError("YouTube API key not found")

    def fetch_stats():
        url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=statistics,contentDetails"
            f"&id={video_id}&key={api_key}"
        )
        req = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            # Redact API key from error messages to prevent leaking in tracebacks
            sanitized = str(exc).replace(api_key, "***")
            raise RuntimeError(f"YouTube API call failed: {sanitized}") from None
        items = data.get("items", [])
        if not items:
            raise RuntimeError(f"No video found for ID {video_id}")
        return items[0]

    item = with_retries(fetch_stats, max_attempts=3, label="youtube_stats", logger=log)
    stats = item.get("statistics", {})

    metrics = {
        "run_id": run_id,
        "video_id": video_id,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "view_count": int(stats.get("viewCount", 0)),
        "like_count": int(stats.get("likeCount", 0)),
        "comment_count": int(stats.get("commentCount", 0)),
        "duration": item.get("contentDetails", {}).get("duration", ""),
    }

    atomic_write_json(metrics_path, metrics)
    log.info(f"Metrics: {metrics['view_count']:,} views, {metrics['like_count']:,} likes")

    mark_step_complete(run_dir, "collect-metrics")
    log_ops_event(run_id, "metrics_collected", metrics)
    print(f"[OK] metrics.json: {metrics['view_count']:,} views → {metrics_path}")


# ===================================================================
# STATUS
# ===================================================================

def cmd_status(args):
    run_dir, run_id, run_config = load_run(args)
    gates, changed = ensure_quality_gates(run_config)
    if changed:
        save_run_config(run_dir, run_config)
    steps = [
        ("init", "run.json"),
        ("discover-products", "products.json"),
        ("generate-script", "script.json"),
        ("approve-gate1", "quality_gates.gate1"),
        ("generate-assets", "assets_manifest.json"),
        ("generate-voice", "voice/timestamps.json"),
        ("build-davinci", "davinci/project.json"),
        ("convert-to-rayvault", "rayvault/05_render_config.json"),
        ("validate-originality", "originality_report.json"),
        ("validate-compliance", "compliance_report.json"),
        ("approve-gate2", "quality_gates.gate2"),
        ("render-and-upload", "upload/youtube_url.txt"),
        ("collect-metrics", "metrics/metrics.json"),
    ]

    print(f"\nPipeline Status: {run_id}")
    print(f"Category: {run_config.get('category', '?')}")
    print(f"Channel: {run_config.get('channel', CHANNEL_NAME)}")
    print("=" * 60)

    for i, (name, output_file) in enumerate(steps):
        if output_file.startswith("quality_gates."):
            gate_name = output_file.split(".")[-1]
            exists = gates.get(gate_name, {}).get("status") == "approved"
        else:
            exists = (run_dir / output_file).exists()
        icon = "OK" if exists else "--"
        print(f"  [{icon}] Step {i}: {name}")

    print("\nQuality Gates:")
    for gate_name in ("gate1", "gate2"):
        gate = gates.get(gate_name, _default_gate_state())
        reviewer = gate.get("reviewer", "") or "-"
        decided = gate.get("decided_at", "") or "-"
        print(f"  - {gate_name}: {gate.get('status', 'pending')} (reviewer: {reviewer}, decided_at: {decided})")

    tier_report = (
        _read_json_if_exists(_ops_tier_report_path(run_dir))
        or _read_json_if_exists(run_dir / "ops_tier_report.json")
        or _ops_tier_report(
        run_dir,
        run_config,
        persist=False,
        )
    )
    print(
        f"\nOperational Tier: {tier_report.get('tier', 'unknown')} "
        f"({tier_report.get('reason', 'n/a')})"
    )

    # Show files
    print(f"\nFiles:")
    for f in sorted(run_dir.rglob("*")):
        if f.is_file() and "logs" not in f.parts:
            rel = f.relative_to(run_dir)
            size = f.stat().st_size
            print(f"  {rel} ({size:,}b)")


def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ops_tier_report_path(run_dir: Path) -> Path:
    return run_dir / "ops" / "ops_tier_report.json"


def _ops_tier_report(run_dir: Path, run_config: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
    cfg = run_config.get("config", {})
    try:
        daily_budget = float(cfg.get("daily_budget_usd", 30) or 30)
    except (TypeError, ValueError):
        daily_budget = 30.0
    try:
        spent_usd = float(cfg.get("spent_usd", 0) or 0)
    except (TypeError, ValueError):
        spent_usd = 0.0
    try:
        critical_failures = int(cfg.get("critical_failures", 0) or 0)
    except (TypeError, ValueError):
        critical_failures = 0

    # ------------------------------------------------------------------
    # Objective signals (cheap first; avoid expensive checks unless needed)
    # ------------------------------------------------------------------
    paused, paused_reasons = detect_ops_paused(project_root=BASE_DIR)

    # Disk health (GB free)
    disk_free_gb: Optional[float] = None
    try:
        du = shutil.disk_usage(str(BASE_DIR))
        disk_free_gb = du.free / (1024**3)
    except Exception:
        disk_free_gb = None

    # Consecutive failures (most recent receipts)
    consecutive_failures = 0
    try:
        receipts: List[Dict[str, Any]] = []
        for p in (run_dir / "receipts").glob("*.json"):
            try:
                r = _read_json(p)
            except Exception:
                continue
            finished_at = str(r.get("finished_at", "") or "")
            receipts.append({"status": r.get("status"), "finished_at": finished_at})
        receipts.sort(key=lambda x: x.get("finished_at") or "")
        for r in reversed(receipts):
            if str(r.get("status", "")).upper() == "FAIL":
                consecutive_failures += 1
            else:
                break
    except Exception:
        consecutive_failures = 0

    # External credit signals (optional; set by ops when providers report low balance)
    low_credit_reasons: List[str] = []
    for env_name, code in (
        ("ELEVENLABS_LOW_CREDIT", "ELEVENLABS_LOW_CREDIT"),
        ("DZINE_LOW_CREDIT", "DZINE_LOW_CREDIT"),
        ("OPS_LOW_CREDIT", "OPS_LOW_CREDIT"),
    ):
        if str(os.environ.get(env_name, "") or "").strip().lower() in {"1", "true", "yes", "on"}:
            low_credit_reasons.append(code)

    # Economy window (optional; opt-in via OPS_LOW_COMPUTE_HOURS="0-6" etc.)
    economy_window = False
    hours = str(os.environ.get("OPS_LOW_COMPUTE_HOURS", "") or "").strip()
    if hours:
        m = re.match(r"^\\s*(\\d{1,2})\\s*[-:]\\s*(\\d{1,2})\\s*$", hours)
        if m:
            start_h = int(m.group(1))
            end_h = int(m.group(2))
            now_h = dt.datetime.now().hour
            if start_h <= end_h:
                economy_window = start_h <= now_h < end_h
            else:
                economy_window = now_h >= start_h or now_h < end_h

    # Worker health (optional; only if cluster nodes.json exists and has enabled workers)
    worker_healthy: Optional[bool] = None
    try:
        nodes_file = BASE_DIR / "state" / "cluster" / "nodes.json"
        if nodes_file.exists():
            cfg_nodes = _read_json(nodes_file)
            nodes = cfg_nodes.get("nodes", []) if isinstance(cfg_nodes, dict) else []
            enabled_workers = [
                n
                for n in nodes
                if isinstance(n, dict)
                and bool(n.get("enabled", True))
                and str(n.get("role", "worker") or "worker").strip().lower() == "worker"
            ]
            if enabled_workers:
                ok_any = False
                for n in enabled_workers:
                    host = str(n.get("host", "") or "").strip()
                    port = int(n.get("port", 0) or 0)
                    if not host or port <= 0:
                        continue
                    url = f"http://{host}:{port}/health"
                    try:
                        req = Request(url, method="GET", headers={"Accept": "application/json"})
                        with urlopen(req, timeout=3) as resp:
                            raw = resp.read().decode("utf-8", errors="replace")
                        payload = json.loads(raw) if raw.strip() else {}
                        ok = bool(payload.get("ok", False))
                        if ok:
                            ok_any = True
                            break
                    except Exception:
                        continue
                worker_healthy = ok_any
            else:
                worker_healthy = None
    except Exception:
        worker_healthy = None

    summary = _read_json_if_exists(run_dir / "run_summary.json")
    totals = summary.get("totals", {}) if isinstance(summary, dict) else {}
    fail_count = int(totals.get("fail", 0) or 0)
    step_count = int(totals.get("steps", 0) or 0)
    runs = max(1, step_count)

    decision = decide_ops_tier(
        daily_budget_usd=daily_budget,
        spent_usd=spent_usd,
        failures=fail_count,
        runs=runs,
        critical_failures=critical_failures,
        paused=paused,
        paused_reasons=paused_reasons,
        worker_healthy=worker_healthy,
        disk_free_gb=disk_free_gb,
        consecutive_failures=consecutive_failures,
        consecutive_failure_threshold=int(cfg.get("consecutive_failure_threshold", 3) or 3),
        low_credit_reasons=low_credit_reasons,
        economy_window=economy_window,
        budget_near_limit_ratio=float(cfg.get("budget_near_limit_ratio", 0.85) or 0.85),
    )
    report = {
        "run_id": run_config.get("run_id", run_dir.name),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        **decision_to_dict(decision),
    }
    if persist:
        p = _ops_tier_report_path(run_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(p, report)
    return report


def _require_expensive_steps_allowed(run_dir: Path, run_config: Dict[str, Any], step_name: str, log: logging.Logger) -> Dict[str, Any]:
    report = _ops_tier_report(run_dir, run_config, persist=True)
    allowed = bool((report.get("directives") or {}).get("allow_expensive_steps", False))
    if allowed:
        return report
    tier = report.get("tier", "unknown")
    reason = report.get("reason", "no reason")
    reasons = report.get("reasons", []) if isinstance(report, dict) else []
    reasons_s = ", ".join(str(x) for x in reasons if str(x).strip()) or ""
    report_path = _ops_tier_report_path(run_dir)
    msg = (
        f"{step_name} blocked by operational tier '{tier}': {reason}"
        + (f" (reasons=[{reasons_s}])" if reasons_s else "")
        + f". See {report_path}."
    )
    log.error(msg)
    raise RuntimeError(msg)


def _pre_gate1_auto_checks(run_dir: Path) -> Dict[str, Any]:
    guard = _read_json_if_exists(run_dir / "security" / "input_guard_report.json")
    checks = {
        "input_guard": {
            "exists": bool(guard),
            "status": "MISSING",
            "fail_reason_codes": [],
            "warn_reason_codes": [],
            "blocked_count": 0,
        }
    }
    if guard:
        status = str(guard.get("status", "") or "").strip().upper()
        if status not in {"OK", "WARN", "FAIL"}:
            # Back-compat
            highest = str(guard.get("highest_threat_level", "low")).lower()
            blocked_count = int(guard.get("blocked_count", 0) or 0)
            if highest == "critical" or blocked_count > 0:
                status = "FAIL"
            elif highest == "high":
                status = "WARN"
            else:
                status = "OK"
        blocked_count = int(guard.get("blocked_count", 0) or 0)
        checks["input_guard"] = {
            "exists": True,
            "status": status,
            "fail_reason_codes": guard.get("fail_reason_codes", []) if isinstance(guard, dict) else [],
            "warn_reason_codes": guard.get("warn_reason_codes", []) if isinstance(guard, dict) else [],
            "blocked_count": blocked_count,
        }
    fail_items = [k for k, v in checks.items() if v["status"] == "FAIL" or not v["exists"]]
    warn_items = [k for k, v in checks.items() if v["status"] == "WARN"]
    checks["ok_for_gate1"] = len(fail_items) == 0
    checks["has_warn"] = len(warn_items) > 0
    checks["fail_items"] = fail_items
    checks["warn_items"] = warn_items
    return checks


def _pre_gate2_auto_checks(run_dir: Path) -> Dict[str, Any]:
    originality = _read_json_if_exists(run_dir / "originality_report.json")
    compliance = _read_json_if_exists(run_dir / "compliance_report.json")
    ops_tier = _read_json_if_exists(_ops_tier_report_path(run_dir)) or _read_json_if_exists(run_dir / "ops_tier_report.json")
    assets_manifest = _read_json_if_exists(run_dir / "assets_manifest.json")
    voice_file = run_dir / "voice" / "voiceover.mp3"
    render_ready_flag = run_dir / "davinci" / "render_ready.flag"
    tier_status = "MISSING"
    if ops_tier:
        tier = str(ops_tier.get("tier", "")).lower()
        if tier in {"critical", "paused"}:
            tier_status = "FAIL"
        elif tier == "low_compute":
            tier_status = "WARN"
        elif tier == "normal":
            tier_status = "OK"
        else:
            tier_status = "WARN"
    checks = {
        "originality": {
            "exists": bool(originality),
            "status": str(originality.get("status", "MISSING")).upper() if originality else "MISSING",
            "exit_code": int(originality.get("exit_code", 2)) if originality else 2,
            "reasons": originality.get("reasons", []) if isinstance(originality, dict) else [],
        },
        "compliance": {
            "exists": bool(compliance),
            "status": str(compliance.get("status", "MISSING")).upper() if compliance else "MISSING",
            "exit_code": int(compliance.get("exit_code", 2)) if compliance else 2,
            "reasons": compliance.get("reasons", []) if isinstance(compliance, dict) else [],
        },
        "ops_tier": {
            "exists": bool(ops_tier),
            "status": tier_status,
            "tier": str(ops_tier.get("tier", "unknown")) if isinstance(ops_tier, dict) else "unknown",
            "reason": str(ops_tier.get("reason", "")) if isinstance(ops_tier, dict) else "",
        },
        "render_inputs": {
            "exists": True,
            "status": "OK",
            "voiceover_exists": voice_file.exists(),
            "render_ready_flag_exists": render_ready_flag.exists(),
            "assets_complete": False,
            "ready_products": 0,
            "total_products": 0,
        },
    }

    assets = assets_manifest.get("assets", []) if isinstance(assets_manifest, dict) else []
    total_products = len(assets)
    ready_products = 0
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        files = asset.get("files", {}) if isinstance(asset.get("files"), dict) else {}
        dzine_images = files.get("dzine_images", [])
        if not isinstance(dzine_images, list):
            dzine_images = []
        existing = sum(1 for rel in dzine_images if (run_dir / str(rel)).exists())
        required = max(1, len(dzine_images))
        if existing >= required:
            ready_products += 1
    assets_complete = total_products > 0 and ready_products >= total_products
    checks["render_inputs"]["assets_complete"] = assets_complete
    checks["render_inputs"]["ready_products"] = ready_products
    checks["render_inputs"]["total_products"] = total_products

    if not voice_file.exists() or not render_ready_flag.exists() or not assets_complete:
        checks["render_inputs"]["status"] = "FAIL"

    fail_items = [k for k, v in checks.items() if v["status"] == "FAIL" or not v["exists"]]
    warn_items = [k for k, v in checks.items() if v["status"] == "WARN"]
    checks["ok_for_gate2"] = len(fail_items) == 0
    checks["has_warn"] = len(warn_items) > 0
    checks["fail_items"] = fail_items
    checks["warn_items"] = warn_items
    return checks


def _cmd_gate_decision(args, gate_name: str, approved: bool):
    run_dir, run_id, run_config = load_run(args)
    reviewer = str(getattr(args, "reviewer", "") or "Ray").strip() or "Ray"
    notes = str(getattr(args, "notes", "") or "").strip()
    decision = "approved" if approved else "rejected"
    log = setup_logger(run_dir, f"{gate_name}_decision")

    if gate_name == "gate1" and approved:
        checks = _pre_gate1_auto_checks(run_dir)
        if not checks["ok_for_gate1"]:
            details = ", ".join(
                f"{k}:{checks[k]['status']}" for k in checks["fail_items"]
            ) or "missing pre-gate1 reports"
            raise RuntimeError(
                "Cannot approve gate1: automatic input contracts failed/missing "
                f"({details}). Run generate-script to produce input guard report."
            )

    if gate_name == "gate2" and approved:
        _ops_tier_report(run_dir, run_config, persist=True)
        checks = _pre_gate2_auto_checks(run_dir)
        if not checks["ok_for_gate2"]:
            details = ", ".join(
                f"{k}:{checks[k]['status']}" for k in checks["fail_items"]
            ) or "missing pre-gate2 reports"
            guidance = "Run validate-originality and validate-compliance first."
            if "render_inputs" in checks["fail_items"]:
                ri = checks.get("render_inputs", {})
                guidance = (
                    "Complete render inputs first (voice/voiceover.mp3, all Dzine images, "
                    "and davinci/render_ready.flag)."
                )
            raise RuntimeError(
                "Cannot approve gate2: automatic quality contracts failed/missing "
                f"({details}). {guidance}"
            )

    set_gate_decision(
        run_dir=run_dir,
        run_config=run_config,
        gate_name=gate_name,
        decision=decision,
        reviewer=reviewer,
        notes=notes,
    )

    log_ops_event(
        run_id,
        "quality_gate_decision",
        {
            "gate": gate_name,
            "decision": decision,
            "reviewer": reviewer,
            "notes": notes,
            "pre_gate1_checks": _pre_gate1_auto_checks(run_dir) if gate_name == "gate1" else {},
            "pre_gate2_checks": _pre_gate2_auto_checks(run_dir) if gate_name == "gate2" else {},
        },
    )
    log.info(f"{gate_name} {decision} by {reviewer}")
    print(f"[OK] {gate_name} set to {decision} by {reviewer}")


def cmd_approve_gate1(args):
    _cmd_gate_decision(args, "gate1", True)


def cmd_reject_gate1(args):
    _cmd_gate_decision(args, "gate1", False)


def cmd_approve_gate2(args):
    _cmd_gate_decision(args, "gate2", True)


def cmd_reject_gate2(args):
    _cmd_gate_decision(args, "gate2", False)


# ===================================================================
# LEARNING GATE
# ===================================================================


def _run_learning_gate(video_id: str, stage: str) -> None:
    """Run the learning gate check. Raises RuntimeError if blocked."""
    try:
        from tools.learning_gate import learning_gate
        result = learning_gate(video_id, stage)
        if result.blocked:
            raise RuntimeError(f"Learning gate blocked: {result.reason}")
    except ImportError:
        pass  # Learning system not installed yet


# ===================================================================
# RUNS
# ===================================================================


def cmd_runs(args):
    """Display pipeline run log."""
    from tools.lib.run_log import format_runs_text, get_daily_summary

    if getattr(args, "summary", False):
        summary = get_daily_summary()
        print(f"Date: {summary['date']}")
        print(f"Total runs: {summary['total_runs']}")
        print(f"Videos: {', '.join(summary['videos_touched']) or 'none'}")
        for cmd, stats in summary.get("by_command", {}).items():
            print(f"  {cmd}: {stats['count']} runs ({stats['ok']} ok, {stats['failed']} failed)")
        return 0

    text = format_runs_text(
        video_id=getattr(args, "video_id", "") or "",
        command=getattr(args, "filter_command", "") or "",
    )
    print(text)
    return 0


# ===================================================================
# SCRIPT BRIEF / REVIEW
# ===================================================================


def cmd_script_brief(args):
    """Generate a manual script brief from products + niche."""
    from tools.lib.script_brief import generate_brief
    from tools.lib.video_paths import VideoPaths

    video_id = args.video_id
    paths = VideoPaths(video_id)

    if not paths.products_json.is_file():
        print(f"Missing products.json for {video_id}")
        return EXIT_ACTION_REQUIRED

    products = json.loads(paths.products_json.read_text(encoding="utf-8"))
    niche = paths.niche_txt.read_text(encoding="utf-8").strip() if paths.niche_txt.is_file() else ""
    seo = json.loads(paths.seo_json.read_text(encoding="utf-8")) if paths.seo_json.is_file() else {}

    brief = generate_brief(niche, products, seo)
    paths.manual_brief.parent.mkdir(parents=True, exist_ok=True)
    paths.manual_brief.write_text(brief, encoding="utf-8")
    print(f"Brief written: {paths.manual_brief}")
    return EXIT_OK


def cmd_script_review(args):
    """Review a raw script and produce notes + final version."""
    from tools.lib.script_brief import review_script, apply_light_fixes, format_review_notes
    from tools.lib.video_paths import VideoPaths

    video_id = args.video_id
    paths = VideoPaths(video_id)

    if not paths.script_raw.is_file():
        print(f"Missing script_raw for {video_id}")
        return EXIT_ACTION_REQUIRED

    script_text = paths.script_raw.read_text(encoding="utf-8")
    products = json.loads(paths.products_json.read_text(encoding="utf-8")) if paths.products_json.is_file() else {}

    result = review_script(script_text, products)

    # Write review notes
    notes = format_review_notes(result, video_id)
    paths.script_review_notes.parent.mkdir(parents=True, exist_ok=True)
    paths.script_review_notes.write_text(notes, encoding="utf-8")

    # Apply light fixes and write final
    fixed_text, _changes = apply_light_fixes(script_text)
    paths.script_final.parent.mkdir(parents=True, exist_ok=True)
    paths.script_final.write_text(fixed_text, encoding="utf-8")

    if not result.passed:
        error_count = sum(1 for i in result.issues if i.severity == "error")
        print(f"Script review found {error_count} errors")
        return EXIT_ACTION_REQUIRED

    print(f"Script reviewed: {len(result.issues)} issues, final written")
    return EXIT_OK


# ===================================================================
# DAY (research + script in one shot)
# ===================================================================


def cmd_day(args):
    """Run research + script + brief generation for a video."""
    from tools.lib.video_paths import VideoPaths
    from tools.lib.script_brief import generate_brief

    video_id = getattr(args, "video_id", "")
    if not video_id:
        return EXIT_ERROR

    paths = VideoPaths(video_id)
    paths.ensure_dirs()

    # Run research
    rc = cmd_research(args)
    if rc != 0:
        return rc

    # Run script
    rc = cmd_script(args)
    if rc != 0:
        return rc

    # Write niche.txt if not present (from args)
    niche = getattr(args, "niche", "") or ""
    if niche and not paths.niche_txt.is_file():
        paths.niche_txt.parent.mkdir(parents=True, exist_ok=True)
        paths.niche_txt.write_text(niche + "\n", encoding="utf-8")

    # Auto-generate brief from products
    if paths.products_json.is_file():
        products = json.loads(paths.products_json.read_text(encoding="utf-8"))
        brief_niche = paths.niche_txt.read_text(encoding="utf-8").strip() if paths.niche_txt.is_file() else niche
        seo = json.loads(paths.seo_json.read_text(encoding="utf-8")) if paths.seo_json.is_file() else {}
        brief = generate_brief(brief_niche or products.get("keyword", "product"), products, seo)
        paths.manual_brief.parent.mkdir(parents=True, exist_ok=True)
        paths.manual_brief.write_text(brief, encoding="utf-8")

    return EXIT_OK


def cmd_research(args):
    """Placeholder for research command — must be mocked in tests."""
    return EXIT_ERROR


def cmd_script(args):
    """Placeholder for script command — must be mocked in tests."""
    return EXIT_ERROR


# ===================================================================
# ERRORS
# ===================================================================


def _log_error(video_id: str, stage: str, error: str, **kwargs) -> None:
    """Log a pipeline error (fire-and-forget wrapper)."""
    try:
        from tools.lib.error_log import log_error
        log_error(video_id, stage, error, **kwargs)
    except Exception:
        pass


def cmd_errors(args):
    """Display cross-video error log."""
    from tools.lib.error_log import format_log_text, get_patterns

    if getattr(args, "patterns", False):
        patterns = get_patterns(min_count=2)
        if not patterns:
            print("No recurring patterns found.")
        else:
            for p in patterns:
                print(
                    f"[{p['count']}x] {p['stage']} | {p['pattern']} "
                    f"({p['unresolved']} open)"
                )
        return 0

    text = format_log_text(
        stage=getattr(args, "stage", "") or "",
        video_id=getattr(args, "video_id", "") or "",
        show_resolved=getattr(args, "show_resolved", False),
        limit=getattr(args, "limit", 20),
    )
    print(text)
    return 0


# ===================================================================
# RUN-E2E
# ===================================================================

def cmd_run_e2e(args):
    # Ensure a stable run_id for this invocation.
    if not args.run_id:
        args.run_id = generate_run_id(args.category)
    run_id = args.run_id

    # Init (idempotent + contract receipt)
    _run_with_contract("init-run", args, cmd_init_run)
    run_dir = get_run_dir(run_id)

    gate1_package_steps = [
        ("discover-products", cmd_discover_products),
        ("plan-variations", cmd_plan_variations),
        ("generate-script", cmd_generate_script),
    ]
    gate2_package_steps = [
        ("generate-assets", cmd_generate_assets),
        ("generate-voice", cmd_generate_voice),
        ("build-davinci", cmd_build_davinci),
        ("convert-to-rayvault", cmd_convert_to_rayvault),
        ("validate-originality", cmd_validate_originality),
        ("validate-compliance", cmd_validate_compliance),
    ]

    with RunLock(run_dir):
        for name, fn in gate1_package_steps:
            print(f"\n{'='*60}")
            print(f"STEP: {name}")
            print(f"{'='*60}")
            try:
                _run_with_contract(name, args, fn)
            except Exception as e:
                print(f"\n[FAIL] {name}: {e}")
                log_ops_event(run_id, "pipeline_failed", {"step": name, "error": str(e)})
                print(f"\nPipeline stopped at {name}. Fix and re-run from this step:")
                print(f"  python3 tools/pipeline.py {name} --run-id {run_id}")
                sys.exit(1)

        # Gate 1 is mandatory.
        run_config = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        gates, changed = ensure_quality_gates(run_config)
        if changed:
            save_run_config(run_dir, run_config)
        gate1_checks = _pre_gate1_auto_checks(run_dir)
        if not gate1_checks.get("ok_for_gate1", False):
            print(f"\n{'='*60}")
            print("GATE 1 AUTO-CHECK FAILED")
            print(f"{'='*60}")
            row = gate1_checks.get("input_guard", {})
            fail_codes = row.get("fail_reason_codes", []) if isinstance(row, dict) else []
            warn_codes = row.get("warn_reason_codes", []) if isinstance(row, dict) else []
            fail_s = ", ".join(str(x) for x in fail_codes if str(x).strip()) or "-"
            warn_s = ", ".join(str(x) for x in warn_codes if str(x).strip()) or "-"
            print(
                f"- input_guard: {row.get('status')} "
                f"(blocked={row.get('blocked_count')}, fail_codes=[{fail_s}], warn_codes=[{warn_s}])"
            )
            print("Fix report and re-run:")
            print(f"  python3 tools/pipeline.py generate-script --run-id {run_id} --force")
            return
        if gate1_checks.get("has_warn", False):
            print(
                f"\n[WARN] Pre-Gate1 contracts returned WARN for: "
                f"{', '.join(gate1_checks.get('warn_items', []))}. "
                "WARN is telemetry-only (approval allowed). Review security/input_guard_report.json."
            )
        if gates["gate1"]["status"] != "approved":
            print(f"\n{'='*60}")
            print("WAITING FOR GATE 1 APPROVAL")
            print(f"{'='*60}")
            print(f"Run: {run_id}")
            print(f"Approve: python3 tools/pipeline.py approve-gate1 --run-id {run_id} --reviewer Ray --notes \"GO\"")
            print(f"Reject : python3 tools/pipeline.py reject-gate1 --run-id {run_id} --reviewer Ray --notes \"Needs rewrite\"")
            return

        for name, fn in gate2_package_steps:
            print(f"\n{'='*60}")
            print(f"STEP: {name}")
            print(f"{'='*60}")
            try:
                _run_with_contract(name, args, fn)
            except Exception as e:
                print(f"\n[FAIL] {name}: {e}")
                log_ops_event(run_id, "pipeline_failed", {"step": name, "error": str(e)})
                print(f"\nPipeline stopped at {name}. Fix and re-run from this step:")
                print(f"  python3 tools/pipeline.py {name} --run-id {run_id}")
                sys.exit(1)

        run_config = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        _ops_tier_report(run_dir, run_config, persist=True)
        auto_checks = _pre_gate2_auto_checks(run_dir)
        if not auto_checks.get("ok_for_gate2", False):
            print(f"\n{'='*60}")
            print("GATE 2 AUTO-CHECK FAILED")
            print(f"{'='*60}")
            for key in ("originality", "compliance"):
                row = auto_checks.get(key, {})
                print(f"- {key}: {row.get('status')} (report exists: {row.get('exists')})")
            print("Fix reports and re-run:")
            print(f"  python3 tools/pipeline.py validate-originality --run-id {run_id} --force")
            print(f"  python3 tools/pipeline.py validate-compliance --run-id {run_id} --force")
            return
        if auto_checks.get("has_warn", False):
            print(f"\n[WARN] Pre-Gate2 contracts returned WARN for: {', '.join(auto_checks.get('warn_items', []))}")
            print("WARN is telemetry-only (approval allowed). Review the reports before rendering/uploading.")

        # Gate 2 is mandatory before render/upload.
        run_config = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        gates, changed = ensure_quality_gates(run_config)
        if changed:
            save_run_config(run_dir, run_config)
        if gates["gate2"]["status"] != "approved":
            print(f"\n{'='*60}")
            print("WAITING FOR GATE 2 APPROVAL")
            print(f"{'='*60}")
            print(f"Run: {run_id}")
            print(f"Approve: python3 tools/pipeline.py approve-gate2 --run-id {run_id} --reviewer Ray --notes \"GO\"")
            print(f"Reject : python3 tools/pipeline.py reject-gate2 --run-id {run_id} --reviewer Ray --notes \"Regenerate assets\"")
            return

        if not str(getattr(args, "youtube_client_secrets", "") or "").strip():
            print(f"\n{'='*60}")
            print("GATE 2 APPROVED — READY TO RENDER/UPLOAD")
            print(f"{'='*60}")
            print(
                "Run render/upload with:\n"
                f"  python3 tools/pipeline.py render-and-upload --run-id {run_id} "
                "--youtube-client-secrets /abs/path/client_secret.json"
            )
            return

        try:
            _run_with_contract("render-and-upload", args, cmd_render_and_upload)
        except Exception as e:
            print(f"\n[FAIL] render-and-upload: {e}")
            log_ops_event(run_id, "pipeline_failed", {"step": "render-and-upload", "error": str(e)})
            print(f"\nRender/upload blocked. Re-run with:")
            print(f"  python3 tools/pipeline.py render-and-upload --run-id {run_id} --youtube-client-secrets /abs/path/client_secret.json")
            sys.exit(1)

        print(f"\n{'='*60}")
        print("PIPELINE COMPLETE")
        print(f"{'='*60}")
        print(f"Run: {run_id}")
        print(f"Dir: {run_dir}")


# ===================================================================
# Helpers
# ===================================================================

def load_run(args) -> Tuple[Path, str, Dict]:
    run_id = args.run_id
    if not run_id:
        raise RuntimeError("--run-id is required")
    # Prevent path traversal (e.g. --run-id "../../etc/passwd")
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise RuntimeError(f"Invalid run-id: {run_id!r} (must not contain path separators or ..)")
    run_dir = get_run_dir(run_id)
    config_path = run_dir / "run.json"
    if not config_path.exists():
        raise RuntimeError(f"Run not found: {run_dir}. Run init-run first.")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return run_dir, run_id, config


def mark_step_complete(run_dir: Path, step: str):
    config_path = run_dir / "run.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    completed = config.get("steps_completed", [])
    if step not in completed:
        completed.append(step)
    config["steps_completed"] = completed
    config["status"] = step
    config["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    # Update step_status
    step_status = config.get("step_status", {})
    step_status[step] = "done"
    config["step_status"] = step_status
    # Update artifact checksums
    config["artifact_checksums"] = compute_artifact_checksums(run_dir)
    atomic_write_json(config_path, config)


# ===================================================================
# CLI
# ===================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="RayViewsLab — File-driven E2E video production pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Shared args
    def add_common(p):
        p.add_argument("--run-id", default="")
        p.add_argument("--force", action="store_true", help="Force re-run even if outputs exist")

    def add_all_config(p):
        add_common(p)
        p.add_argument("--category", default="desk_gadgets")
        p.add_argument("--duration", type=int, default=8)
        p.add_argument("--voice", default=DEFAULT_VOICE)
        p.add_argument("--affiliate-tag", default=DEFAULT_AFFILIATE_TAG)
        p.add_argument("--tracking-id-override", default="", help="Optional per-video Associates tracking ID")
        p.add_argument("--min-rating", type=float, default=4.2)
        p.add_argument("--min-reviews", type=int, default=500)
        p.add_argument("--min-price", type=float, default=100)
        p.add_argument("--max-price", type=float, default=500)
        p.add_argument("--exclude-last-days", type=int, default=15)
        p.add_argument(
            "--source",
            choices=["mock", "scrape", "openclaw", "chatgpt_ui", "minimax"],
            default="openclaw",
            help="Script/discovery source. Policy: scripts must use openclaw/chatgpt_ui (ChatGPT UI).",
        )
        p.add_argument("--resolution", choices=["1920x1080", "3840x2160"], default="1920x1080")
        p.add_argument("--daily-budget-usd", type=float, default=30.0)
        p.add_argument("--spent-usd", type=float, default=0.0)
        p.add_argument("--critical-failures", type=int, default=0)

    # init-run
    p = sub.add_parser("init-run", help="Create run folder + run.json")
    add_all_config(p)
    p.set_defaults(func=cmd_init_run)

    # discover-products
    p = sub.add_parser("discover-products", help="Find products from Amazon")
    add_all_config(p)
    p.set_defaults(func=cmd_discover_products)

    # plan-variations
    p = sub.add_parser("plan-variations", help="Generate variation_plan.json for format diversity")
    add_common(p)
    p.set_defaults(func=cmd_plan_variations)

    # generate-script
    p = sub.add_parser("generate-script", help="Generate structured script.json")
    add_all_config(p)
    p.set_defaults(func=cmd_generate_script)

    # generate-assets
    p = sub.add_parser("generate-assets", help="Generate Dzine image prompts + manifest")
    add_common(p)
    p.set_defaults(func=cmd_generate_assets)

    # generate-voice
    p = sub.add_parser("generate-voice", help="Generate voice timestamps + narration text")
    add_common(p)
    p.add_argument("--source", choices=["mock", "elevenlabs"], default="mock",
                   help="mock = timestamps only; elevenlabs = timestamps + actual TTS audio")
    p.set_defaults(func=cmd_generate_voice)

    # build-davinci
    p = sub.add_parser("build-davinci", help="Build DaVinci project.json")
    add_common(p)
    p.set_defaults(func=cmd_build_davinci)

    # convert-to-rayvault
    p = sub.add_parser("convert-to-rayvault", help="Convert pipeline output → RayVault format")
    add_common(p)
    p.add_argument("--frame-path", default=None, help="Path to 03_frame.png")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    p.add_argument("--no-overlays", action="store_true", help="Skip overlays_index.json")
    p.set_defaults(func=cmd_convert_to_rayvault)

    # validate-originality
    p = sub.add_parser("validate-originality", help="Run originality budget checks before Gate 2")
    add_common(p)
    p.add_argument("--policy-json", default="", help="Optional JSON thresholds override")
    p.set_defaults(func=cmd_validate_originality)

    # validate-compliance
    p = sub.add_parser("validate-compliance", help="Run compliance contract checks before Gate 2")
    add_common(p)
    p.set_defaults(func=cmd_validate_compliance)

    # gate decisions (mandatory human approvals)
    for cmd_name, fn, label in [
        ("approve-gate1", cmd_approve_gate1, "Approve Gate 1 (products + script)"),
        ("reject-gate1", cmd_reject_gate1, "Reject Gate 1"),
        ("approve-gate2", cmd_approve_gate2, "Approve Gate 2 (assets + audio)"),
        ("reject-gate2", cmd_reject_gate2, "Reject Gate 2"),
    ]:
        p = sub.add_parser(cmd_name, help=label)
        add_common(p)
        p.add_argument("--reviewer", default="Ray")
        p.add_argument("--notes", default="")
        p.set_defaults(func=fn)

    # render-and-upload
    p = sub.add_parser("render-and-upload", help="Render video + upload to YouTube")
    add_common(p)
    p.add_argument("--youtube-client-secrets", default="", help="Path to YouTube OAuth client secrets JSON")
    p.add_argument("--youtube-token-file", default="", help="Path to cached YouTube OAuth token JSON")
    p.add_argument("--video-file", default="", help="Optional override for rendered video path")
    p.add_argument("--thumbnail", default="", help="Optional thumbnail image")
    p.add_argument("--privacy-status", choices=["private", "public", "unlisted"], default="private")
    p.add_argument("--tracking-id-override", default="", help="Optional per-video Associates tracking ID")
    p.add_argument("--step-retries", type=int, default=3, help="Retries for render/upload external calls")
    p.add_argument("--step-backoff-sec", type=int, default=8, help="Base backoff seconds (x1, x3, x9)")
    p.set_defaults(func=cmd_render_and_upload)

    # collect-metrics
    p = sub.add_parser("collect-metrics", help="Collect YouTube metrics (24h after upload)")
    add_common(p)
    p.set_defaults(func=cmd_collect_metrics)

    # run-e2e
    p = sub.add_parser("run-e2e", help="Run full pipeline end-to-end")
    add_all_config(p)
    p.add_argument("--youtube-client-secrets", default="", help="Optional: if set and gate2 approved, upload runs automatically")
    p.add_argument("--youtube-token-file", default="", help="Optional cached token for YouTube upload")
    p.add_argument("--video-file", default="", help="Optional override for rendered video path")
    p.add_argument("--thumbnail", default="", help="Optional thumbnail image")
    p.add_argument("--privacy-status", choices=["private", "public", "unlisted"], default="private")
    p.add_argument("--step-retries", type=int, default=3)
    p.add_argument("--step-backoff-sec", type=int, default=8)
    p.set_defaults(func=cmd_run_e2e)

    # status
    p = sub.add_parser("status", help="Show pipeline run status")
    add_common(p)
    p.set_defaults(func=cmd_status)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        _run_with_contract(args.command, args, args.func)
    except RuntimeError as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
