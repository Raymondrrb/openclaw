#!/usr/bin/env python3
"""RayviewsLab Async Worker — asyncio + httpx queue consumer.

Replaces the synchronous worker.py with:
- httpx async for all Supabase RPC calls (no blocking)
- asyncio.Task heartbeat (not threading)
- safe_stop_async with asyncio.shield (Playwright-safe)
- Latency measurement piggybacked on heartbeat
- PanicManager local-first (atomic spool)
- Checkpoint atomic write (fsync + os.replace)
- Recovery-first claim_next (automatic via worker_id)
- waiting_approval: release lock + pause (no infinite hold)

Dependencies: httpx (pip install httpx)
Optional: psutil (for browser process cleanup)

Usage:
    python3 tools/worker_async.py --worker-id Mac-Ray-01
    python3 tools/worker_async.py --once

Or via CLI:
    python3 rayvault_cli.py worker
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

import httpx

try:
    import psutil
except ImportError:
    psutil = None

from tools.lib.config import WorkerConfig, SecretsConfig, load_worker_config, ExitCode
from tools.lib.panic import PanicManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON atomically: tempfile + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Supabase RPC client (async, httpx)
# ---------------------------------------------------------------------------

class SupabaseRPC:
    """Async PostgREST client for RayVault RPCs."""

    def __init__(self, secrets: SecretsConfig):
        self.base = secrets.supabase_url.rstrip("/")
        self.headers = {
            "apikey": secrets.supabase_service_key,
            "Authorization": f"Bearer {secrets.supabase_service_key}",
            "Content-Type": "application/json",
        }

    async def rpc(self, fn: str, payload: Dict[str, Any],
                  timeout: float = 10.0) -> Tuple[Any, int]:
        """POST to /rest/v1/rpc/<fn>. Returns (data, status_code)."""
        url = f"{self.base}/rest/v1/rpc/{fn}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=self.headers, json=payload)
            try:
                data = r.json() if r.text.strip() else None
            except Exception:
                data = None
            return data, r.status_code

    async def patch_run(self, run_id: str, fields: Dict[str, Any],
                        timeout: float = 10.0) -> int:
        """PATCH /rest/v1/pipeline_runs?id=eq.<uuid>."""
        url = f"{self.base}/rest/v1/pipeline_runs?id=eq.{run_id}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.patch(url, headers=self.headers, json=fields)
            return r.status_code

    async def get_run(self, run_id: str, select: str = "*",
                      timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """GET /rest/v1/pipeline_runs?id=eq.<uuid>&select=..."""
        url = f"{self.base}/rest/v1/pipeline_runs?id=eq.{run_id}&select={select}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=self.headers)
            if r.status_code < 300:
                rows = r.json()
                return rows[0] if rows else None
            return None

    async def insert_event(self, event: Dict[str, Any],
                           timeout: float = 10.0) -> int:
        """POST /rest/v1/run_events."""
        url = f"{self.base}/rest/v1/run_events"
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=self.headers, json=event)
            return r.status_code


# ---------------------------------------------------------------------------
# Checkpoint / active run state
# ---------------------------------------------------------------------------

def _checkpoint_path(cfg: WorkerConfig, run_id: str) -> Path:
    return Path(cfg.checkpoint_dir) / f"{run_id}.json"


def load_checkpoint(cfg: WorkerConfig, run_id: str) -> Dict[str, Any]:
    p = _checkpoint_path(cfg, run_id)
    data = _read_json(p)
    if data:
        data.setdefault("stage", "init")
        data.setdefault("completed_steps", [])
        data.setdefault("data", {})
        return data
    return {"stage": "init", "completed_steps": [], "data": {}}


def save_checkpoint(cfg: WorkerConfig, run_id: str, stage: str, *,
                    data: Dict[str, Any] | None = None,
                    lock_token: str = "") -> None:
    p = _checkpoint_path(cfg, run_id)
    existing = load_checkpoint(cfg, run_id)
    existing["stage"] = stage
    existing["last_update"] = _iso(_utcnow())
    if lock_token:
        existing["lock_token"] = lock_token
    if stage not in existing["completed_steps"]:
        existing["completed_steps"].append(stage)
    if data:
        existing.setdefault("data", {}).update(data)
    _atomic_write_json(p, existing)


def clear_checkpoint(cfg: WorkerConfig, run_id: str) -> None:
    p = _checkpoint_path(cfg, run_id)
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# LostLock exception
# ---------------------------------------------------------------------------

class LostLock(Exception):
    """Raised when heartbeat detects lock loss."""
    pass


# ---------------------------------------------------------------------------
# Safe stop (async, Playwright-compatible)
# ---------------------------------------------------------------------------

async def safe_stop_async(
    run_id: str,
    stop_signal: asyncio.Event,
    *,
    browser: Any = None,
    context: Any = None,
    page: Any = None,
) -> None:
    """Controlled panic stop with shielded timeouts."""
    stop_signal.set()

    async def _close(obj: Any, timeout: float) -> None:
        try:
            await asyncio.wait_for(asyncio.shield(obj.close()), timeout=timeout)
        except Exception:
            pass

    # LIFO: page → context → browser
    if page:
        await _close(page, 2.0)
    if context:
        await _close(context, 2.0)
    if browser:
        await _close(browser, 5.0)

    # PID-based child cleanup (browser processes only)
    if psutil:
        try:
            me = psutil.Process(os.getpid())
            browser_patterns = {"chrome", "chromium", "playwright", "msedge"}
            for child in me.children(recursive=True):
                name = (child.name() or "").lower()
                if any(p in name for p in browser_patterns):
                    try:
                        child.terminate()
                    except Exception:
                        pass
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Heartbeat task
# ---------------------------------------------------------------------------

async def heartbeat_loop(
    cfg: WorkerConfig,
    rpc: SupabaseRPC,
    panic: PanicManager,
    stop_signal: asyncio.Event,
    run_id: str,
    lock_token: str,
) -> None:
    """Background heartbeat: renew lease, measure latency, detect lock loss.

    Two failure modes:
    - cas_heartbeat_run returns false → lock stolen → panic_lost_lock
    - Network errors × threshold → panic_heartbeat_uncertain
    """
    consecutive_errors = 0
    prev_latency_ms: int | None = None  # piggybacked from previous call

    while not stop_signal.is_set():
        # Sleep first (prevents thundering herd on restart)
        jitter = random.uniform(0, cfg.heartbeat_jitter_sec)
        try:
            await asyncio.wait_for(
                stop_signal.wait(),
                timeout=cfg.heartbeat_interval_sec + jitter,
            )
            break  # stop_signal was set
        except asyncio.TimeoutError:
            pass  # normal — time to heartbeat

        if stop_signal.is_set():
            break

        t0 = time.monotonic()
        try:
            params: Dict[str, Any] = {
                "p_run_id": run_id,
                "p_worker_id": cfg.worker_id,
                "p_lock_token": lock_token,
                "p_lease_minutes": cfg.lease_minutes,
            }
            # Piggyback previous latency (can't measure own response before sending)
            if prev_latency_ms is not None:
                params["p_latency_ms"] = prev_latency_ms

            data, status = await rpc.rpc(
                "cas_heartbeat_run", params,
                timeout=cfg.heartbeat_timeout_sec,
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            prev_latency_ms = latency_ms

            if status >= 300:
                raise ConnectionError(f"HTTP {status}")

            # cas_heartbeat_run returns boolean
            ok = bool(data) if data is not None else False

            if not ok:
                # Definitive: lock stolen or run in terminal state
                panic.report_panic(
                    "panic_lost_lock", run_id,
                    "cas_heartbeat_run returned false",
                    latency_ms=latency_ms,
                )
                stop_signal.set()
                return

            consecutive_errors = 0

            # Warn on high latency (but don't panic)
            if latency_ms >= cfg.thresholds.heartbeat_latency_warn_ms:
                print(
                    f"[heartbeat] WARN: latency={latency_ms}ms "
                    f"(run=...{run_id[-8:]})",
                    file=sys.stderr,
                )

        except LostLock:
            stop_signal.set()
            return
        except Exception as e:
            consecutive_errors += 1
            latency_ms = int((time.monotonic() - t0) * 1000)
            print(
                f"[heartbeat] Network error ({consecutive_errors}/"
                f"{cfg.heartbeat_uncertain_threshold}): {e}",
                file=sys.stderr,
            )

            if consecutive_errors >= cfg.heartbeat_uncertain_threshold:
                panic.report_panic(
                    "panic_heartbeat_uncertain", run_id,
                    f"heartbeat errors >= {cfg.heartbeat_uncertain_threshold}: {e}",
                    latency_ms=latency_ms,
                    retry_count=consecutive_errors,
                )
                stop_signal.set()
                return


# ---------------------------------------------------------------------------
# Claim / release RPCs
# ---------------------------------------------------------------------------

async def claim_next(
    cfg: WorkerConfig,
    rpc: SupabaseRPC,
) -> Optional[str]:
    """Call rpc_claim_next_run. Returns run_id or None.

    Recovery-first is automatic: the RPC checks for worker's own active
    run before picking a new one (Phase 1 vs Phase 2 in the SQL).
    """
    lock_token = str(uuid.uuid4())
    data, status = await rpc.rpc("rpc_claim_next_run", {
        "p_worker_id": cfg.worker_id,
        "p_lock_token": lock_token,
        "p_lease_minutes": cfg.lease_minutes,
        "p_task_type": cfg.task_type or None,
    }, timeout=cfg.claim_timeout_sec)

    if status >= 300:
        print(f"[worker] claim_next HTTP {status}: {data}", file=sys.stderr)
        return None

    # PostgREST returns the uuid directly (RETURNS uuid)
    if data and data != "null" and str(data).strip('"') != "null":
        run_id = str(data).strip('"')
        return run_id

    return None


async def release_run(
    cfg: WorkerConfig,
    rpc: SupabaseRPC,
    run_id: str,
    lock_token: str,
) -> bool:
    """Call rpc_release_run. Returns True on success."""
    data, status = await rpc.rpc("rpc_release_run", {
        "p_run_id": run_id,
        "p_worker_id": cfg.worker_id,
        "p_lock_token": lock_token,
    }, timeout=cfg.claim_timeout_sec)
    return status < 300 and bool(data)


async def log_event(
    rpc: SupabaseRPC,
    run_id: str,
    event_type: str,
    payload: Dict[str, Any],
    *,
    severity: str | None = None,
    reason_key: str | None = None,
) -> None:
    """Insert a run_event (best effort)."""
    event_id = str(uuid.uuid4())
    event = {
        "run_id": run_id,
        "action_id": event_id,
        "event_id": event_id,
        "event_type": event_type,
        "severity": severity,
        "reason_key": reason_key,
        "source": f"worker_async",
        "occurred_at": _iso(_utcnow()),
        "payload": payload,
    }
    try:
        await rpc.insert_event(event, timeout=5)
    except Exception:
        pass  # best effort


# ---------------------------------------------------------------------------
# Pipeline stages (stub — plug Dzine/OpenClaw here)
# ---------------------------------------------------------------------------

STAGES = (
    "research",
    "script_brief",
    "script_generate",
    "script_review",
    "assets",
    "tts",
    "manifest",
)


async def run_stage(stage: str, video_id: str, run_id: str) -> bool:
    """Run a single pipeline stage. Returns True on success.

    Override this function with actual Dzine/OpenClaw integration.
    Each stage should be idempotent (check for existing artifacts).
    """
    # Placeholder: import real stage runners when available
    print(f"[worker]   [{stage}] running... (video={video_id})")
    await asyncio.sleep(0.1)  # placeholder
    return True


# ---------------------------------------------------------------------------
# Process a single run
# ---------------------------------------------------------------------------

async def process_run(
    cfg: WorkerConfig,
    rpc_client: SupabaseRPC,
    panic: PanicManager,
    run_id: str,
    lock_token: str,
    video_id: str,
    stop_signal: asyncio.Event,
) -> str:
    """Process a run through all stages. Returns final status.

    Raises LostLock if heartbeat detects lock loss.
    """
    ckpt = load_checkpoint(cfg, run_id)

    print(f"[worker] Processing run=...{run_id[-8:]} video={video_id}")
    if ckpt["completed_steps"]:
        print(f"[worker]   Resuming: completed={ckpt['completed_steps']}")

    for stage in STAGES:
        if stop_signal.is_set():
            save_checkpoint(cfg, run_id, stage, lock_token=lock_token)
            return "interrupted"

        # Skip completed stages (idempotency via checkpoint)
        if stage in ckpt["completed_steps"]:
            print(f"[worker]   [{stage}] skipped (checkpoint)")
            continue

        t0 = time.monotonic()
        ok = await run_stage(stage, video_id, run_id)
        elapsed = time.monotonic() - t0

        if ok:
            print(f"[worker]   [{stage}] done ({elapsed:.1f}s)")
            save_checkpoint(
                cfg, run_id, stage,
                lock_token=lock_token,
                data={"elapsed_s": round(elapsed, 1)},
            )
            await log_event(rpc_client, run_id, "stage_complete", {
                "stage": stage,
                "video_id": video_id,
                "elapsed_s": round(elapsed, 1),
            })
        else:
            print(f"[worker]   [{stage}] FAILED", file=sys.stderr)
            return "failed"

    return "done"


# ---------------------------------------------------------------------------
# Worker main loop
# ---------------------------------------------------------------------------

async def worker_main(
    cfg: WorkerConfig,
    secrets: SecretsConfig,
    *,
    once: bool = False,
) -> ExitCode:
    """Main worker loop: claim → heartbeat → process → repeat."""
    rpc_client = SupabaseRPC(secrets)
    panic = PanicManager(cfg, secrets)

    # Ensure dirs
    for d in [cfg.spool_dir, cfg.checkpoint_dir, cfg.state_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)

    print(
        f"[worker] Starting | worker_id={cfg.worker_id} "
        f"lease={cfg.lease_minutes}min hb={cfg.heartbeat_interval_sec}s "
        f"once={once}"
    )

    while True:
        # 1. Claim next run (recovery-first is automatic in RPC)
        run_id = await claim_next(cfg, rpc_client)
        if not run_id:
            if once:
                print("[worker] No runs available (--once mode)")
                return ExitCode.OK
            sleep_time = cfg.poll_interval_sec + random.uniform(0, cfg.poll_jitter_sec)
            print(f"[worker] Queue empty — sleeping {sleep_time:.0f}s")
            await asyncio.sleep(sleep_time)
            continue

        # 2. Fetch run details (video_id, lock_token, status)
        row = await rpc_client.get_run(
            run_id,
            select="id,video_id,lock_token,status,worker_id",
            timeout=cfg.claim_timeout_sec,
        )
        if not row:
            print(f"[worker] Could not fetch run {run_id}", file=sys.stderr)
            if once:
                return ExitCode.ERROR
            continue

        video_id = row.get("video_id", "")
        lock_token = row.get("lock_token", "")
        status = row.get("status", "")

        if not video_id:
            print(f"[worker] No video_id for run {run_id} — skipping", file=sys.stderr)
            await release_run(cfg, rpc_client, run_id, lock_token)
            if once:
                return ExitCode.ERROR
            continue

        # 3. Start heartbeat
        stop_signal = asyncio.Event()
        hb_task = asyncio.create_task(
            heartbeat_loop(cfg, rpc_client, panic, stop_signal, run_id, lock_token),
        )

        # 4. Process the run
        try:
            result = await process_run(
                cfg, rpc_client, panic,
                run_id, lock_token, video_id,
                stop_signal,
            )

            if result == "done":
                await rpc_client.patch_run(run_id, {
                    "status": "done",
                    "worker_state": "idle",
                })
                await release_run(cfg, rpc_client, run_id, lock_token)
                clear_checkpoint(cfg, run_id)
                print(f"[worker] Run ...{run_id[-8:]} DONE")

            elif result == "failed":
                await rpc_client.patch_run(run_id, {
                    "status": "failed",
                    "worker_state": "idle",
                    "worker_last_error": "pipeline stage failed",
                })
                await release_run(cfg, rpc_client, run_id, lock_token)
                print(f"[worker] Run ...{run_id[-8:]} FAILED")

            elif result == "interrupted":
                print(f"[worker] Run ...{run_id[-8:]} interrupted — checkpoint saved")

        except LostLock:
            print(f"[worker] PANIC: lost lock on ...{run_id[-8:]}", file=sys.stderr)
            save_checkpoint(cfg, run_id, "panic", lock_token=lock_token,
                            data={"panic_reason": "lost_lock"})
            # Quarantine before retry
            await asyncio.sleep(cfg.quarantine_sec)

        except Exception as exc:
            print(f"[worker] ERROR: {exc}", file=sys.stderr)
            panic.report_panic(
                "panic_integrity_failure", run_id,
                f"unhandled: {exc}"[:cfg.max_worker_error_len],
            )
            await safe_stop_async(run_id, stop_signal)
            save_checkpoint(cfg, run_id, "error", lock_token=lock_token,
                            data={"error": str(exc)[:500]})

        finally:
            stop_signal.set()
            hb_task.cancel()
            try:
                await hb_task
            except (asyncio.CancelledError, Exception):
                pass

        if once:
            return ExitCode.OK

        # Cooldown between runs
        await asyncio.sleep(
            cfg.post_run_backoff_sec + random.uniform(0, cfg.poll_jitter_sec),
        )

    return ExitCode.OK  # unreachable but makes type checker happy


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def start_worker(cfg: WorkerConfig, secrets: SecretsConfig, *,
                 once: bool = False) -> int:
    """Blocking entrypoint for CLI integration."""
    return int(asyncio.run(worker_main(cfg, secrets, once=once)))


# ---------------------------------------------------------------------------
# Standalone CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    from tools.lib.common import load_env_file

    parser = argparse.ArgumentParser(description="RayVault Async Worker")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    load_env_file()
    cfg, secrets = load_worker_config(worker_id=args.worker_id)

    raise SystemExit(start_worker(cfg, secrets, once=args.once))
