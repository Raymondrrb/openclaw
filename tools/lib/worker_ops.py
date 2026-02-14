"""Worker operations — safe stop, local checkpoints, event spool.

Three concerns for a production worker:
1. PANIC STOP: shut down Dzine/OpenClaw without leaving zombies.
2. CHECKPOINT: atomic local state so restarts skip completed stages.
3. SPOOL: buffer run_events locally when Supabase is unreachable.

All functions are stdlib-only (psutil is optional for PID cleanup).

Usage:
    from tools.lib.worker_ops import safe_stop, save_checkpoint, load_checkpoint

    # On panic:
    safe_stop(run_id, reason="lost_lock", browser=browser_instance)

    # Before each stage:
    ckpt = load_checkpoint(run_id)
    if "collect_evidence" in ckpt["completed_steps"]:
        skip...

    # After each stage:
    save_checkpoint(run_id, stage="collect_evidence",
                    data={"products": 5},
                    artifacts={"evidence_csv": "/tmp/ev.csv"})
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tools.lib.common import now_iso


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPOOL_DIR = str(_REPO_ROOT / "spool")
CHECKPOINT_DIR = str(_REPO_ROOT / "checkpoints")
CHECKPOINT_VERSION = 1

# Panic idempotency flag — prevents re-entry
_panic_active = False


# ---------------------------------------------------------------------------
# 1. Event spool — buffer events locally when network is down
# ---------------------------------------------------------------------------

def spool_event(run_id: str, event_type: str, payload: dict) -> str:
    """Write a run_event to local spool (filesystem).

    Used when Supabase is unreachable during panic. The replayer
    picks these up later and sends them.

    Returns the spool file path.
    """
    os.makedirs(SPOOL_DIR, exist_ok=True)
    ts = int(time.time())
    fname = f"{run_id}_{ts}_{event_type}.json"
    path = os.path.join(SPOOL_DIR, fname)
    record = {
        "run_id": run_id,
        "event_type": event_type,
        "payload": payload,
        "ts": now_iso(),
    }
    # Atomic write to spool
    fd, tmp_path = tempfile.mkstemp(
        prefix=f"{run_id}_", suffix=".tmp", dir=SPOOL_DIR,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        # If rename failed, clean up temp
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return path


def replay_spool(*, send_fn: Callable[[dict], bool] | None = None) -> dict:
    """Replay spooled events to Supabase. Returns summary.

    Args:
        send_fn: Optional callback(record) → bool. If None, uses
                 default Supabase insert into run_events.

    Returns:
        {"sent": int, "failed": int, "remaining": list[str]}
    """
    if not os.path.isdir(SPOOL_DIR):
        return {"sent": 0, "failed": 0, "remaining": []}

    sent = 0
    failed = 0
    remaining = []

    for fname in sorted(os.listdir(SPOOL_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(SPOOL_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
        except (json.JSONDecodeError, OSError):
            remaining.append(fname)
            failed += 1
            continue

        ok = False
        if send_fn:
            try:
                ok = send_fn(record)
            except Exception:
                ok = False
        else:
            ok = _default_spool_send(record)

        if ok:
            try:
                os.remove(path)
            except OSError:
                pass
            sent += 1
        else:
            remaining.append(fname)
            failed += 1

    return {"sent": sent, "failed": failed, "remaining": remaining}


def _default_spool_send(record: dict) -> bool:
    """Send a spooled event to Supabase run_events.

    Maps the spool timestamp into payload.spool_ts to preserve
    original timing without conflicting with DB-generated created_at.
    """
    try:
        from tools.lib.supabase_client import insert
        import uuid as _uuid
        payload = dict(record.get("payload", {}))
        if "ts" in record:
            payload.setdefault("spool_ts", record["ts"])
        insert("run_events", {
            "run_id": record["run_id"],
            "action_id": str(_uuid.uuid4()),
            "event_type": record["event_type"],
            "payload": payload,
        })
        return True
    except Exception as exc:
        print(f"[spool] Send failed: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# 2. Checkpoint — atomic local state for crash recovery
# ---------------------------------------------------------------------------

def load_checkpoint(run_id: str) -> dict:
    """Load checkpoint from disk. Returns default if not found."""
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    path = os.path.join(CHECKPOINT_DIR, f"{run_id}.json")
    if not os.path.exists(path):
        return _default_checkpoint(run_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            ckpt = json.load(f)
        # Ensure required keys
        ckpt.setdefault("run_id", run_id)
        ckpt.setdefault("version", CHECKPOINT_VERSION)
        ckpt.setdefault("stage", "init")
        ckpt.setdefault("completed_steps", [])
        ckpt.setdefault("data", {})
        ckpt.setdefault("artifacts", {})
        return ckpt
    except (json.JSONDecodeError, OSError):
        return _default_checkpoint(run_id)


def save_checkpoint(
    run_id: str,
    stage: str,
    *,
    data: dict | None = None,
    artifacts: dict | None = None,
    lock_token: str = "",
) -> str:
    """Save checkpoint atomically (tmpfile + os.replace).

    Args:
        run_id: The run being checkpointed.
        stage: Current stage name (e.g., "collect_evidence").
        data: Arbitrary data to merge into checkpoint.
        artifacts: Artifact paths/ids to merge (e.g., {"dzine_job_id": "abc"}).
        lock_token: Current lock token (for reclaim on restart).

    Returns the checkpoint file path.
    """
    ckpt = load_checkpoint(run_id)
    ckpt["stage"] = stage
    ckpt["last_update_utc"] = now_iso()
    if lock_token:
        ckpt["lock_token"] = lock_token

    # Mark stage as completed
    if stage not in ckpt["completed_steps"]:
        ckpt["completed_steps"].append(stage)

    # Merge data and artifacts safely
    if data:
        ckpt.setdefault("data", {})
        ckpt["data"].update(data)
    if artifacts:
        ckpt.setdefault("artifacts", {})
        ckpt["artifacts"].update(artifacts)

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    final_path = os.path.join(CHECKPOINT_DIR, f"{run_id}.json")

    # Atomic write: write to temp, then rename
    fd, tmp_path = tempfile.mkstemp(
        prefix=f"{run_id}_", suffix=".tmp", dir=CHECKPOINT_DIR,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, final_path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return final_path


def clear_checkpoint(run_id: str) -> bool:
    """Remove checkpoint file after successful run completion."""
    path = os.path.join(CHECKPOINT_DIR, f"{run_id}.json")
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def _default_checkpoint(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "version": CHECKPOINT_VERSION,
        "stage": "init",
        "completed_steps": [],
        "data": {},
        "artifacts": {},
    }


# ---------------------------------------------------------------------------
# 3. Safe stop — controlled panic shutdown
# ---------------------------------------------------------------------------

def safe_stop(
    run_id: str,
    reason: str,
    *,
    stop_signal: Any | None = None,
    browser: Any | None = None,
    context: Any | None = None,
    page: Any | None = None,
    worker_pid: int | None = None,
    mark_panic_fn: Callable[[str, str], None] | None = None,
) -> None:
    """Controlled panic stop. Idempotent (re-entry is a no-op).

    Execution order:
    1. Spool event locally (always works, even without network)
    2. Set stop signal (if provided)
    3. Close Playwright in order: page → context → browser
    4. Kill worker child processes by PID (psutil, only known PIDs)
    5. Mark worker panic in Supabase (best-effort)

    Args:
        run_id: The run to stop.
        reason: Why we're stopping.
        stop_signal: threading.Event or similar to signal the main loop.
        browser: Playwright Browser instance.
        context: Playwright BrowserContext instance.
        page: Playwright Page instance.
        worker_pid: PID of the worker process (for child cleanup).
        mark_panic_fn: Callback(run_id, reason) to update Supabase.
    """
    global _panic_active
    if _panic_active:
        return  # Idempotent: already panicking
    _panic_active = True

    print(
        f"[worker_ops] CONTROLLED PANIC: run={run_id} reason={reason}",
        file=sys.stderr,
    )

    # 1. Spool locally FIRST (network may be down)
    try:
        spool_event(run_id, "panic_stop", {
            "reason": reason,
            "worker_pid": worker_pid,
        })
    except Exception as exc:
        print(f"[worker_ops] Spool failed: {exc}", file=sys.stderr)

    # 2. Set stop signal
    if stop_signal is not None:
        try:
            stop_signal.set()
        except Exception:
            pass

    # 3. Close Playwright (page → context → browser)
    for label, obj in [("page", page), ("context", context), ("browser", browser)]:
        if obj is not None:
            try:
                obj.close()
                print(f"[worker_ops] Closed {label}", file=sys.stderr)
            except Exception as exc:
                print(
                    f"[worker_ops] Failed to close {label}: {exc}",
                    file=sys.stderr,
                )

    # 4. Kill child processes by PID (only the ones we launched)
    if worker_pid:
        _kill_worker_children(worker_pid)

    # 5. Mark panic in Supabase (best-effort)
    if mark_panic_fn:
        try:
            mark_panic_fn(run_id, reason)
        except Exception as exc:
            print(
                f"[worker_ops] Supabase panic update failed: {exc}",
                file=sys.stderr,
            )
            # Already spooled locally — replayer will send later


def reset_panic_flag() -> None:
    """Reset the panic idempotency flag. Call after recovery/restart."""
    global _panic_active
    _panic_active = False


def is_panic_active() -> bool:
    """Check if a panic is currently in progress."""
    return _panic_active


def _kill_worker_children(worker_pid: int) -> None:
    """Kill child processes of the worker (chrome, chromium, playwright).

    Uses psutil if available. Only kills children matching known patterns.
    Never uses pkill or broad process matching.
    """
    try:
        import psutil
    except ImportError:
        print(
            "[worker_ops] psutil not installed — skipping PID cleanup",
            file=sys.stderr,
        )
        return

    try:
        proc = psutil.Process(worker_pid)
        children = proc.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return

    # Only kill children matching browser/automation patterns
    browser_patterns = {"chrome", "chromium", "playwright", "chromedriver"}
    targets = []
    for child in children:
        try:
            name = (child.name() or "").lower()
            cmd = " ".join(child.cmdline() or []).lower()
            if any(p in name for p in browser_patterns) or \
               any(p in cmd for p in browser_patterns | {"remote-debugging-port"}):
                targets.append(child)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not targets:
        return

    # Terminate gracefully first
    for t in targets:
        try:
            t.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Wait for graceful exit
    try:
        gone, alive = psutil.wait_procs(targets, timeout=3)
    except Exception:
        alive = targets

    # Force kill survivors
    for t in alive:
        try:
            t.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print(
        f"[worker_ops] PID cleanup: terminated={len(targets)}, "
        f"force_killed={len(alive)}",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# 4. Mark worker panic in Supabase
# ---------------------------------------------------------------------------

def mark_worker_panic(run_id: str, reason: str) -> bool:
    """Update worker_state='panic' and worker_last_error in Supabase.

    Does NOT change run status — only worker health fields.
    """
    try:
        from tools.lib.supabase_client import update
        update("pipeline_runs", {"id": run_id}, {
            "worker_state": "panic",
            "worker_last_error": reason[:200],  # truncate
            "updated_at": now_iso(),
        })
        return True
    except Exception as exc:
        print(f"[worker_ops] mark_panic failed: {exc}", file=sys.stderr)
        return False
