#!/usr/bin/env python3
"""
Lightweight local worker that reacts to Supabase ops_video_runs state changes.

Purpose:
- Keep local pipeline artifacts in sync with Gate approvals (approve_gate1/approve_gate2).
- Generate Gate 2 package when Gate 1 gets approved.
- Attempt DaVinci auto-cut when a run is moved to status=rendering.

Safety:
- CAS-based claim prevents concurrent processing of the same run.
- Stale claims (>30 min) are released automatically.
- fail_count tracks failures; runs with >= MAX_FAIL_COUNT are skipped.
- Never generates ElevenLabs audio (cost) or uploads to YouTube.
- Never proceeds unless Supabase says the gate is approved.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lib.common import now_iso


BASE_DIR = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
PIPELINE = BASE_DIR / "tools" / "pipeline.py"
DAVINCI_AUTOCUT = BASE_DIR / "tools" / "davinci_top5_autocut.py"

CLAIM_STALE_MINUTES = 30
MAX_FAIL_COUNT = 3


def env_required(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def sb_base() -> str:
    return env_required("SUPABASE_URL").rstrip("/")


def sb_key() -> str:
    return env_required("SUPABASE_SERVICE_ROLE_KEY")


def sb_get_json(url: str) -> Any:
    req = Request(
        url,
        method="GET",
        headers={
            "apikey": sb_key(),
            "Authorization": f"Bearer {sb_key()}",
        },
    )
    with urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def sb_patch_json(url: str, body: Dict[str, Any]) -> Any:
    req = Request(
        url,
        method="PATCH",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "apikey": sb_key(),
            "Authorization": f"Bearer {sb_key()}",
            "Prefer": "return=representation",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
    except HTTPError:
        return None


def sb_insert_event(event_type: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
    url = f"{sb_base()}/rest/v1/ops_agent_events"
    payload: Dict[str, Any] = {
        "event_hash": f"worker_{int(time.time()*1000)}_{os.getpid()}",
        "ts": now_iso(),
        "type": event_type,
        "message": message,
        "data": data or {},
    }
    req = Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "apikey": sb_key(),
            "Authorization": f"Bearer {sb_key()}",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            _ = resp.read()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Claim lifecycle (CAS-based locking)
# ---------------------------------------------------------------------------

def sb_try_claim(run_slug: str, worker_id: str) -> bool:
    """Attempt CAS claim: only succeeds if claimed_by is currently null."""
    from urllib.parse import quote

    url = (
        f"{sb_base()}/rest/v1/ops_video_runs"
        f"?run_slug=eq.{quote(run_slug)}"
        f"&claimed_by=is.null"
    )
    body = {"claimed_by": worker_id, "claimed_at": now_iso()}
    result = sb_patch_json(url, body)
    # Supabase returns a list; non-empty means the patch matched a row
    return bool(result and isinstance(result, list) and len(result) > 0)


def sb_release_claim(run_slug: str) -> None:
    """Release claim (fire-and-forget)."""
    from urllib.parse import quote

    url = f"{sb_base()}/rest/v1/ops_video_runs?run_slug=eq.{quote(run_slug)}"
    try:
        sb_patch_json(url, {"claimed_by": None, "claimed_at": None})
    except Exception:  # noqa: BLE001
        pass


def sb_increment_fail(run_slug: str) -> None:
    """Increment fail_count; mark status='failed' if >= MAX_FAIL_COUNT."""
    from urllib.parse import quote

    url = f"{sb_base()}/rest/v1/ops_video_runs?run_slug=eq.{quote(run_slug)}&select=fail_count"
    rows = sb_get_json(url)
    current = 0
    if rows and isinstance(rows, list) and rows:
        try:
            current = int(rows[0].get("fail_count", 0))
        except (ValueError, TypeError):
            current = 0
    new_count = current + 1
    patch: Dict[str, Any] = {"fail_count": new_count}
    if new_count >= MAX_FAIL_COUNT:
        patch["status"] = "failed"
    patch_url = f"{sb_base()}/rest/v1/ops_video_runs?run_slug=eq.{quote(run_slug)}"
    try:
        sb_patch_json(patch_url, patch)
    except Exception:  # noqa: BLE001
        pass


def sb_release_stale_claims() -> None:
    """Release claims older than CLAIM_STALE_MINUTES."""
    cutoff = datetime.now(timezone.utc).timestamp() - (CLAIM_STALE_MINUTES * 60)
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    url = (
        f"{sb_base()}/rest/v1/ops_video_runs"
        f"?claimed_by=not.is.null"
        f"&claimed_at=lt.{cutoff_iso}"
    )
    try:
        sb_patch_json(url, {"claimed_by": None, "claimed_at": None})
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Run directory and state helpers
# ---------------------------------------------------------------------------

def run_cmd(cmd: List[str], timeout_sec: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)


def out_dir_for_run(run: Dict[str, Any]) -> Path:
    artifacts = run.get("artifacts") or {}
    # Prefer any artifact path as an anchor.
    for k in ("products_json", "script_a", "upload_metadata_json"):
        p = artifacts.get(k)
        if p and isinstance(p, str):
            candidate = Path(p).expanduser()
            if candidate.exists():
                return candidate.parent
    # Fallback to conventional location (new path first, then legacy).
    run_slug = str(run.get("run_slug", "")).strip()
    modern = (BASE_DIR / "pipeline_runs" / run_slug).expanduser()
    if modern.exists():
        return modern
    return (BASE_DIR / "content" / "pipeline_runs" / run_slug).expanduser()


def load_run_json(out_dir: Path) -> Dict[str, Any]:
    """Read run.json (canonical) instead of legacy pipeline_state.json."""
    for name in ("run.json", "pipeline_state.json"):
        p = out_dir / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
    return {}


def manifest_path_from_run(run_data: Dict[str, Any], out_dir: Path) -> Path:
    """Find DaVinci manifest: check davinci/project.json first, legacy fallback."""
    # New canonical location
    project_json = out_dir / "davinci" / "project.json"
    if project_json.exists():
        return project_json
    # Legacy: check artifacts in run data
    artifacts = run_data.get("artifacts") or {}
    m = artifacts.get("davinci_manifest") or str(out_dir / "davinci_manifest.json")
    return Path(m).expanduser()


def should_retry_transient(err: str) -> bool:
    low = (err or "").lower()
    return any(
        s in low
        for s in [
            "keep resolve open",
            "could not connect to davinci resolve api",
            "no active project folder",
        ]
    )


# ---------------------------------------------------------------------------
# Process a single run
# ---------------------------------------------------------------------------

def process_run(run: Dict[str, Any], *, worker_id: str, timeout_sec: int) -> None:
    run_slug = str(run.get("run_slug") or "").strip()
    status = str(run.get("status") or "").strip()
    gate1 = bool(run.get("gate1_approved"))
    gate2 = bool(run.get("gate2_approved"))

    reviewer1 = (run.get("gate1_reviewer") or "Ray").strip()
    notes1 = (run.get("gate1_notes") or "").strip()
    reviewer2 = (run.get("gate2_reviewer") or "Ray").strip()
    notes2 = (run.get("gate2_notes") or "").strip()

    out_dir = out_dir_for_run(run)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_data = load_run_json(out_dir)

    # Gate 1 approved: approve locally, then generate-assets + generate-voice + build-davinci
    if status == "draft_ready_waiting_gate_1" and gate1:
        sb_insert_event(
            "worker_gate1_detected",
            f"[{worker_id}] gate1 approved detected for {run_slug}; running gate2 steps",
            {"run_slug": run_slug},
        )
        # Step 1: approve gate1
        run_cmd(
            [sys.executable, str(PIPELINE), "approve-gate1",
             "--run-id", run_slug, "--reviewer", reviewer1, "--notes", notes1],
            timeout_sec=timeout_sec,
        )
        # Step 2: generate assets
        p = run_cmd(
            [sys.executable, str(PIPELINE), "generate-assets", "--run-id", run_slug],
            timeout_sec=timeout_sec,
        )
        if p.returncode != 0:
            sb_insert_event(
                "worker_generate_assets_failed",
                f"[{worker_id}] generate-assets failed for {run_slug}",
                {"run_slug": run_slug, "stderr": (p.stderr or "")[:400]},
            )
            sb_increment_fail(run_slug)
            return
        # Step 3: generate voice
        p = run_cmd(
            [sys.executable, str(PIPELINE), "generate-voice", "--run-id", run_slug],
            timeout_sec=timeout_sec,
        )
        if p.returncode != 0:
            sb_insert_event(
                "worker_generate_voice_failed",
                f"[{worker_id}] generate-voice failed for {run_slug}",
                {"run_slug": run_slug, "stderr": (p.stderr or "")[:400]},
            )
            sb_increment_fail(run_slug)
            return
        # Step 4: build davinci
        p = run_cmd(
            [sys.executable, str(PIPELINE), "build-davinci", "--run-id", run_slug],
            timeout_sec=timeout_sec,
        )
        if p.returncode != 0:
            sb_insert_event(
                "worker_build_davinci_failed",
                f"[{worker_id}] build-davinci failed for {run_slug}",
                {"run_slug": run_slug, "stderr": (p.stderr or "")[:400]},
            )
            sb_increment_fail(run_slug)
            return
        return

    # Gate 2 approved: reflect decision in local state
    if status == "assets_ready_waiting_gate_2" and gate2:
        sb_insert_event(
            "worker_gate2_detected",
            f"[{worker_id}] gate2 approved detected for {run_slug}; syncing local state",
            {"run_slug": run_slug},
        )
        run_cmd(
            [sys.executable, str(PIPELINE), "approve-gate2",
             "--run-id", run_slug, "--reviewer", reviewer2, "--notes", notes2],
            timeout_sec=timeout_sec,
        )
        return

    # Rendering: attempt Resolve autocut only if Gate 2 artifacts exist.
    if status == "rendering":
        if not gate2:
            sb_insert_event(
                "worker_render_blocked",
                f"[{worker_id}] render blocked (gate2 not approved) for {run_slug}",
                {"run_slug": run_slug},
            )
            return

        if not run_data:
            sb_insert_event(
                "worker_render_missing_state",
                f"[{worker_id}] render requested but run.json missing for {run_slug}",
                {"run_slug": run_slug, "out_dir": str(out_dir)},
            )
            return

        manifest = manifest_path_from_run(run_data, out_dir)
        if not manifest.exists():
            sb_insert_event(
                "worker_render_missing_manifest",
                f"[{worker_id}] render requested but manifest missing for {run_slug}",
                {"run_slug": run_slug, "expected": str(manifest)},
            )
            return

        proc = run_cmd(
            [
                sys.executable,
                str(DAVINCI_AUTOCUT),
                "--manifest",
                str(manifest),
                "--report",
                str(out_dir / "davinci_run_report.json"),
            ],
            timeout_sec=timeout_sec,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            ev = "worker_render_transient" if should_retry_transient(err) else "worker_render_failed"
            sb_insert_event(
                ev,
                f"[{worker_id}] davinci autocut error for {run_slug}",
                {"run_slug": run_slug, "stderr": err[:600]},
            )
            if not should_retry_transient(err):
                sb_increment_fail(run_slug)
            return

        sb_insert_event(
            "worker_render_started",
            f"[{worker_id}] davinci render started for {run_slug}",
            {"run_slug": run_slug, "manifest": str(manifest)},
        )
        return


# ---------------------------------------------------------------------------
# Main: claim lifecycle
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Local worker for ops_video_runs state changes")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--worker-id", default="mac-local-1")
    ap.add_argument("--timeout-sec", type=int, default=900)
    args = ap.parse_args()

    base = sb_base()

    # Step 1: release stale claims
    sb_release_stale_claims()

    # Step 2: fetch only unclaimed, non-exhausted runs
    url = (
        f"{base}/rest/v1/ops_video_runs"
        f"?select=run_slug,status,gate1_approved,gate2_approved,"
        f"gate1_reviewer,gate2_reviewer,gate1_notes,gate2_notes,"
        f"artifacts,meta,updated_at,fail_count"
        f"&claimed_by=is.null"
        f"&fail_count=lt.{MAX_FAIL_COUNT}"
        f"&order=updated_at.desc&limit={int(args.limit)}"
    )
    runs = sb_get_json(url) or []
    if not isinstance(runs, list):
        return 0

    for run in runs:
        if not isinstance(run, dict):
            continue
        status = str(run.get("status") or "")
        if status not in {
            "draft_ready_waiting_gate_1",
            "assets_ready_waiting_gate_2",
            "rendering",
        }:
            continue

        run_slug = str(run.get("run_slug") or "").strip()
        if not run_slug:
            continue

        # Step 3: CAS claim
        if not sb_try_claim(run_slug, args.worker_id):
            continue  # another worker got it

        try:
            process_run(run, worker_id=args.worker_id, timeout_sec=int(args.timeout_sec))
        except Exception as exc:
            try:
                sb_insert_event(
                    "worker_exception",
                    f"[{args.worker_id}] exception while processing run",
                    {"error": str(exc)[:400], "run_slug": run_slug},
                )
                sb_increment_fail(run_slug)
            except Exception:
                pass
        finally:
            # Step 4: always release claim
            sb_release_claim(run_slug)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
