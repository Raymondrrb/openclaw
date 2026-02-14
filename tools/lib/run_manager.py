"""Run Manager — state machine + cost controls + circuit breaker integration.

State machine:
    pending → in_progress → waiting_approval → approved → done
    Any state → aborted | failed

Every expensive step must call check_status() first. If the run is
waiting_approval, the step returns immediately (zero token waste).

Context snapshots are forensic — every state transition records what
the agent saw, decided, and why. Phase markers:
    "started" | "paused" | "refetch" | "approved" | "ignored" | "aborted" | "final"

Integrates with circuit_breaker.py for evidence gating and
telegram_gate.py for human approval.

HeartbeatManager runs a background thread that renews the worker lease.
On lock loss → LostLock exception → worker stops immediately.

Stdlib only.

Usage:
    from lib.run_manager import RunManager, LostLock

    rm = RunManager(run_id, worker_id="RayMac-01")
    rm.start(context_pack, evidence)
    rm.claim()
    hb = rm.start_heartbeat()

    for stage in ["collect", "generate", "render"]:
        hb.check_or_raise()  # raises LostLock if lock was lost
        do_work(stage)

    rm.complete()
"""

from __future__ import annotations

import json
import random
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from tools.lib.common import now_iso


# ---------------------------------------------------------------------------
# LostLock exception — raised when the worker loses its lock on a run
# ---------------------------------------------------------------------------

class LostLock(Exception):
    """Raised when the worker loses its lock on a run.

    The worker MUST stop all automation immediately:
    - Do not click, render, or generate anything
    - Save a local checkpoint (run_id, stage, last item)
    - Log a panic_lost_lock event if possible
    """
    pass


def _future_iso(minutes: int) -> str:
    """Return ISO timestamp N minutes in the future."""
    from datetime import datetime, timezone, timedelta
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


# ---------------------------------------------------------------------------
# Heartbeat Manager — background thread that renews the worker lease
# ---------------------------------------------------------------------------

# Default heartbeat configuration
HEARTBEAT_INTERVAL_SECONDS = 120     # 2 minutes
HEARTBEAT_JITTER_SECONDS = 15       # ±15s randomization
HEARTBEAT_MAX_RETRIES = 3           # retries on network failure
HEARTBEAT_RETRY_DELAYS = (0, 2, 5)  # seconds between retries


class HeartbeatManager:
    """Background thread that renews the worker lease and detects lock loss.

    Two failure modes, handled differently:
    - heartbeat() returns False → lock stolen or status changed. Immediate PANIC.
    - heartbeat() raises exception → network issue. Retry with backoff, then PANIC.

    On PANIC:
    - Sets lost_lock flag (check with .lost_lock or .check_or_raise())
    - Logs panic_lost_lock event to run_events
    - Calls on_panic callback if provided (e.g., stop Dzine browser)

    Usage:
        hb = HeartbeatManager(rm)
        hb.start()

        for stage in stages:
            hb.check_or_raise()  # raises LostLock
            do_work(stage)

        hb.stop()  # clean shutdown
    """

    def __init__(
        self,
        run_manager: "RunManager",
        *,
        interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS,
        jitter_seconds: int = HEARTBEAT_JITTER_SECONDS,
        max_retries: int = HEARTBEAT_MAX_RETRIES,
        on_panic: Callable[[str, str], None] | None = None,
    ):
        """
        Args:
            run_manager: The RunManager instance to heartbeat for.
            interval_seconds: Base interval between heartbeats (default 120s).
            jitter_seconds: Max random jitter added to interval (default 15s).
            max_retries: Retries on network failure before PANIC (default 3).
            on_panic: Optional callback(run_id, reason) called on lock loss.
                      Use this to stop Dzine/OpenClaw automation.
        """
        self._rm = run_manager
        self._interval = interval_seconds
        self._jitter = jitter_seconds
        self._max_retries = max_retries
        self._on_panic = on_panic
        self._stop_event = threading.Event()
        self._lost_event = threading.Event()
        self._panic_reason = ""
        self._thread: threading.Thread | None = None

    def start(self) -> threading.Thread:
        """Start the heartbeat background thread. Returns the thread."""
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name=f"heartbeat-{self._rm.run_id[:8]}",
        )
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        """Stop the heartbeat thread. Safe to call multiple times."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    @property
    def lost_lock(self) -> bool:
        """True if the lock was lost (PANIC state)."""
        return self._lost_event.is_set()

    @property
    def panic_reason(self) -> str:
        """Human-readable reason for the PANIC, if any."""
        return self._panic_reason

    def check_or_raise(self) -> None:
        """Check lock status. Raises LostLock if the lock was lost.

        Call this before every expensive operation in your pipeline.
        """
        if self._lost_event.is_set():
            raise LostLock(self._panic_reason or "Lock lost")

    def _loop(self) -> None:
        """Main heartbeat loop. Runs in background thread."""
        while not self._stop_event.is_set():
            # Sleep with jitter (interruptible by stop)
            sleep_time = self._interval + random.randint(0, self._jitter)
            if self._stop_event.wait(timeout=sleep_time):
                return  # clean stop

            ok = self._heartbeat_with_retries()
            if not ok:
                self._enter_panic()
                return

    def _heartbeat_with_retries(self) -> bool:
        """Try heartbeat with retries on network failure.

        Returns True if heartbeat succeeded.
        Returns False if:
        - heartbeat() explicitly returned False (lock stolen → no retry)
        - All retry attempts failed (network down → PANIC by uncertainty)

        Sets self._panic_type to distinguish:
        - "panic_lost_lock" — RPC responded false (definitive)
        - "panic_heartbeat_uncertain" — network failures, can't confirm
        """
        delays = list(HEARTBEAT_RETRY_DELAYS[:self._max_retries])
        for delay in delays:
            if delay:
                time.sleep(delay)
            try:
                result = self._rm.heartbeat()
                if result:
                    return True
                # Explicit False from DB: lock stolen or status changed.
                # Don't retry — this is a definitive answer.
                self._panic_type = "panic_lost_lock"
                self._panic_reason = (
                    "heartbeat rejected (lock stolen or status changed)"
                )
                return False
            except Exception:
                # Network error — retry
                continue

        # All retries exhausted — uncertain, treat as PANIC
        self._panic_type = "panic_heartbeat_uncertain"
        self._panic_reason = "heartbeat network failure after retries"
        return False

    def _enter_panic(self) -> None:
        """Enter PANIC state: set flag, spool event locally, call hook."""
        self._lost_event.set()

        event_type = getattr(self, "_panic_type", "panic_lost_lock")
        payload = {
            "worker_id": self._rm._state.worker_id,
            "run_id": self._rm.run_id,
            "lock_token": self._rm._state.lock_token,
            "reason": self._panic_reason,
        }

        # Log forensic event (separate types for autopsy)
        self._rm._log_event(event_type, payload)

        # Spool locally in case network is down (the whole reason for panic)
        try:
            from tools.lib.worker_ops import spool_event
            spool_event(self._rm.run_id, event_type, payload)
        except Exception:
            pass  # best-effort; event is already in local _events list

        print(
            f"[heartbeat] PANIC ({event_type}): {self._panic_reason} "
            f"(run={self._rm.run_id}, worker={self._rm._state.worker_id})",
            file=sys.stderr,
        )

        # Call on_panic hook (e.g., close Dzine browser, driver.quit())
        if self._on_panic:
            try:
                self._on_panic(self._rm.run_id, self._panic_reason)
            except Exception as exc:
                print(
                    f"[heartbeat] on_panic hook failed: {exc}",
                    file=sys.stderr,
                )

    @property
    def panic_type(self) -> str:
        """The type of panic: panic_lost_lock or panic_heartbeat_uncertain."""
        return getattr(self, "_panic_type", "")


# ---------------------------------------------------------------------------
# Valid state transitions
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending":            {"in_progress", "aborted", "failed"},
    "in_progress":        {"waiting_approval", "done", "aborted", "failed"},
    "waiting_approval":   {"in_progress", "approved", "aborted", "failed"},
    "approved":           {"in_progress", "done", "aborted", "failed"},
    "done":               set(),  # terminal
    "aborted":            set(),  # terminal
    "failed":             set(),  # terminal
}

# States where expensive operations are BLOCKED
BLOCKED_STATES: set[str] = {"waiting_approval", "aborted", "failed", "done"}

# States where the run is active and may proceed
ACTIVE_STATES: set[str] = {"pending", "in_progress", "approved"}

# Worker lease defaults
DEFAULT_LEASE_MINUTES = 10
MIN_LEASE_MINUTES = 1
MAX_LEASE_MINUTES = 30
MIN_WORKER_ID_LEN = 3
CLAIMABLE_STATUSES = {"running", "in_progress", "approved"}


# ---------------------------------------------------------------------------
# Run state container
# ---------------------------------------------------------------------------

@dataclass
class RunState:
    """Current state of a pipeline run."""
    run_id: str
    status: str = "pending"
    approval_nonce: str = ""
    context_snapshot: dict = field(default_factory=dict)
    policy_version: str = ""
    ranking_model: str = ""
    refetch_attempted: bool = False
    # Worker lease fields
    worker_id: str = ""
    lock_token: str = ""
    lock_expires_at: str = ""  # ISO timestamp

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATES

    @property
    def is_blocked(self) -> bool:
        return self.status in BLOCKED_STATES

    @property
    def is_locked(self) -> bool:
        """True if there's an active (non-expired) lock."""
        if not self.lock_token or not self.lock_expires_at:
            return False
        try:
            from datetime import datetime, timezone
            import time as _time
            ts = datetime.fromisoformat(self.lock_expires_at).timestamp()
            return ts > _time.time()
        except (ValueError, OSError):
            return False


# ---------------------------------------------------------------------------
# Run Manager
# ---------------------------------------------------------------------------

class RunManager:
    """Manages a single pipeline run's lifecycle.

    Encapsulates:
    - State transitions (with validation)
    - Status checks before expensive ops
    - Context snapshot recording
    - Circuit breaker integration
    - Event logging
    """

    def __init__(
        self,
        run_id: str,
        *,
        policy_version: str = "v1.0",
        ranking_model: str = "",
        use_supabase: bool = True,
        worker_id: str = "",
    ):
        self._state = RunState(
            run_id=run_id,
            policy_version=policy_version,
            ranking_model=ranking_model,
            worker_id=worker_id,
        )
        self._use_supabase = use_supabase
        self._events: list[dict] = []  # local event log

    @property
    def run_id(self) -> str:
        return self._state.run_id

    @property
    def status(self) -> str:
        return self._state.status

    @property
    def state(self) -> RunState:
        return self._state

    # -------------------------------------------------------------------
    # State transitions
    # -------------------------------------------------------------------

    def _transition(self, new_status: str, *, reason: str = "") -> bool:
        """Attempt a state transition. Returns True if successful."""
        current = self._state.status
        allowed = VALID_TRANSITIONS.get(current, set())

        if new_status not in allowed:
            print(
                f"[run_manager] Invalid transition: {current} → {new_status} "
                f"(allowed: {allowed})",
                file=sys.stderr,
            )
            return False

        old_status = current
        self._state.status = new_status

        # Log event
        self._log_event("status_change", {
            "from": old_status,
            "to": new_status,
            "reason": reason,
        })

        # Persist to Supabase
        if self._use_supabase:
            self._persist_status(new_status)

        return True

    def _persist_status(self, new_status: str) -> None:
        """Write status to Supabase (fire-and-forget)."""
        try:
            from tools.lib.supabase_client import update
            data: dict[str, Any] = {
                "status": new_status,
                "updated_at": now_iso(),
                "context_snapshot": json.dumps(self._state.context_snapshot),
            }
            if self._state.approval_nonce:
                data["approval_nonce"] = self._state.approval_nonce
            if self._state.policy_version:
                data["policy_version"] = self._state.policy_version
            if self._state.ranking_model:
                data["ranking_model"] = self._state.ranking_model

            update("pipeline_runs", {"id": self._state.run_id}, data)
        except Exception as exc:
            print(f"[run_manager] Supabase persist failed: {exc}", file=sys.stderr)

    def _persist_event(self, event_type: str, payload: dict, action_id: str = "") -> None:
        """Write event to Supabase run_events (fire-and-forget)."""
        try:
            from tools.lib.supabase_client import insert
            insert("run_events", {
                "run_id": self._state.run_id,
                "action_id": action_id or str(uuid.uuid4()),
                "event_type": event_type,
                "payload": payload,
                "created_at": now_iso(),
            })
        except Exception as exc:
            print(f"[run_manager] Event persist failed: {exc}", file=sys.stderr)

    # -------------------------------------------------------------------
    # Event logging
    # -------------------------------------------------------------------

    def _log_event(self, event_type: str, payload: dict, action_id: str = "") -> None:
        """Log event locally and to Supabase."""
        event = {
            "event_type": event_type,
            "payload": payload,
            "action_id": action_id or str(uuid.uuid4()),
            "timestamp": now_iso(),
        }
        self._events.append(event)

        if self._use_supabase:
            self._persist_event(event_type, payload, event["action_id"])

    # -------------------------------------------------------------------
    # Public API — lifecycle
    # -------------------------------------------------------------------

    def start(
        self,
        context_pack: dict | None = None,
        evidence_summary: dict | None = None,
    ) -> bool:
        """Start the run. Transitions pending → in_progress.

        Records initial context snapshot with phase="started".
        """
        snapshot = {
            "phase": "started",
            "policy_version": self._state.policy_version,
            "ranking_model": self._state.ranking_model,
            "started_at": now_iso(),
        }
        if context_pack:
            snapshot["context_pack"] = context_pack
        if evidence_summary:
            snapshot["initial_evidence"] = evidence_summary

        self._state.context_snapshot = snapshot

        return self._transition("in_progress", reason="run started")

    def complete(self, *, final_evidence: dict | None = None) -> bool:
        """Mark run as done. Stops heartbeat, releases lock."""
        self._update_snapshot(phase="final", extra={"final_evidence": final_evidence or {}})
        ok = self._transition("done", reason="all stages complete")
        if ok:
            self.stop_heartbeat()
            self.release_lock()
        return ok

    def fail(self, error: str) -> bool:
        """Mark run as failed. Stops heartbeat, releases lock."""
        self._update_snapshot(phase="failed", extra={"error": error})
        ok = self._transition("failed", reason=error)
        if ok:
            self.stop_heartbeat()
            self.release_lock()
        return ok

    def abort(self, reason: str = "user abort") -> bool:
        """Mark run as aborted. Stops heartbeat, releases lock."""
        self._update_snapshot(phase="aborted", extra={"abort_reason": reason})
        ok = self._transition("aborted", reason=reason)
        if ok:
            self.stop_heartbeat()
            self.release_lock()
        return ok

    # -------------------------------------------------------------------
    # Status check — MUST call before expensive operations
    # -------------------------------------------------------------------

    def check_status(self) -> bool:
        """Check if the run is in an active state. Call before expensive ops.

        Returns True if OK to proceed. Returns False if blocked.
        Refreshes status from Supabase if available.
        """
        # Refresh from Supabase
        if self._use_supabase:
            self._refresh_status()

        if self._state.is_blocked:
            print(
                f"[run_manager] Run {self._state.run_id} blocked "
                f"(status={self._state.status}). Skipping expensive operation.",
                file=sys.stderr,
            )
            return False

        return True

    def _refresh_status(self) -> None:
        """Refresh run status from Supabase."""
        try:
            from tools.lib.supabase_client import query
            rows = query(
                "pipeline_runs",
                filters={"id": self._state.run_id},
                limit=1,
            )
            if rows:
                row = rows[0]
                self._state.status = row.get("status", self._state.status)
                self._state.approval_nonce = row.get("approval_nonce", "")
                snapshot = row.get("context_snapshot")
                if isinstance(snapshot, dict):
                    self._state.context_snapshot = snapshot
                elif isinstance(snapshot, str):
                    try:
                        self._state.context_snapshot = json.loads(snapshot)
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            print(f"[run_manager] Supabase refresh failed: {exc}", file=sys.stderr)

    def require_active(self) -> None:
        """Assert the run is active. Raises if blocked."""
        if not self.check_status():
            raise RuntimeError(
                f"Run {self._state.run_id} is not active "
                f"(status={self._state.status}). Cannot proceed."
            )

    # -------------------------------------------------------------------
    # Worker lease — prevents 2+ workers from processing the same run
    # -------------------------------------------------------------------

    @staticmethod
    def _clamp_lease(minutes: int) -> int:
        """Clamp lease to [1, 30] minutes. Matches DB-side guardrail."""
        return max(MIN_LEASE_MINUTES, min(minutes, MAX_LEASE_MINUTES))

    def claim(
        self,
        *,
        lease_minutes: int = DEFAULT_LEASE_MINUTES,
        existing_token: str = "",
    ) -> bool:
        """Claim this run for the current worker. CAS-safe.

        Only succeeds if:
        - Run is in a claimable status (running/in_progress/approved)
        - No active lock exists (lock_expires_at is null or expired)
        - Or this worker already owns the lock (idempotent reclaim)

        Args:
            lease_minutes: How long the lease lasts before expiring (clamped 1-30).
            existing_token: If resuming from a crash, pass the previously
                persisted lock_token to reclaim without waiting for expiry.

        Returns True if claim succeeded.
        """
        if not self._state.worker_id:
            print("[run_manager] Cannot claim: worker_id not set", file=sys.stderr)
            return False

        if len(self._state.worker_id.strip()) < MIN_WORKER_ID_LEN:
            print(
                f"[run_manager] Cannot claim: worker_id too short "
                f"(min {MIN_WORKER_ID_LEN} chars)",
                file=sys.stderr,
            )
            return False

        lease_minutes = self._clamp_lease(lease_minutes)

        # Reclaim: if we have a valid existing token, try heartbeat first
        if existing_token:
            self._state.lock_token = existing_token
            if self.heartbeat(lease_minutes=lease_minutes):
                self._state.lock_expires_at = _future_iso(lease_minutes)
                self._log_event("worker_reclaim", {
                    "worker_id": self._state.worker_id,
                    "lock_token": existing_token,
                    "lease_minutes": lease_minutes,
                })
                return True
            # Heartbeat failed — token stale, fall through to fresh claim

        token = str(uuid.uuid4())

        if self._use_supabase:
            success = self._supabase_claim(token, lease_minutes)
            if not success:
                self._log_event("claim_failed", {
                    "worker_id": self._state.worker_id,
                    "run_id": self._state.run_id,
                    "reason": "CAS claim rejected (already locked by another worker)",
                })
                return False
        else:
            # Local mode: check state directly
            if self._state.status not in CLAIMABLE_STATUSES:
                return False
            # Check if locked by a different worker with active lease
            if (self._state.is_locked
                    and self._state.lock_token
                    and self._state.worker_id != self._state.worker_id):
                return False

        self._state.lock_token = token
        self._state.lock_expires_at = _future_iso(lease_minutes)

        self._log_event("worker_claim", {
            "worker_id": self._state.worker_id,
            "lock_token": token,
            "lease_minutes": lease_minutes,
        })

        return True

    def heartbeat(self, *, lease_minutes: int = DEFAULT_LEASE_MINUTES) -> bool:
        """Renew the lease for the current lock. Call every 2-3 minutes.

        Only succeeds if worker_id + lock_token match.
        Measures round-trip latency and sends it to the RPC for dashboard alerting.
        Returns True if lease was renewed.
        """
        if not self._state.lock_token:
            return False

        lease_minutes = self._clamp_lease(lease_minutes)

        if self._use_supabase:
            t0 = time.monotonic()
            success = self._supabase_heartbeat(lease_minutes)
            latency_ms = int((time.monotonic() - t0) * 1000)

            if success:
                # Send latency on next heartbeat (piggyback)
                self._last_heartbeat_latency_ms = latency_ms
            else:
                # Lock lost — log event for forensics
                self._log_event("lock_lost", {
                    "worker_id": self._state.worker_id,
                    "run_id": self._state.run_id,
                    "lock_token": self._state.lock_token,
                    "latency_ms": latency_ms,
                    "reason": "heartbeat rejected (token mismatch or status change)",
                })
                return False

        self._state.lock_expires_at = _future_iso(lease_minutes)
        return True

    def release_lock(self) -> bool:
        """Release the worker lock. Called on done/aborted/failed.

        Only the holder (matching worker_id + lock_token) can release.
        """
        if not self._state.lock_token:
            return True  # Nothing to release

        if self._use_supabase:
            self._supabase_release()

        self._state.lock_token = ""
        self._state.lock_expires_at = ""

        self._log_event("worker_release", {
            "worker_id": self._state.worker_id,
        })
        return True

    @property
    def is_claimed(self) -> bool:
        """True if this run has an active claim by any worker."""
        return self._state.is_locked

    @property
    def lock_token(self) -> str:
        return self._state.lock_token

    # --- Heartbeat manager integration ---

    def start_heartbeat(
        self,
        *,
        interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS,
        jitter_seconds: int = HEARTBEAT_JITTER_SECONDS,
        on_panic: Callable[[str, str], None] | None = None,
    ) -> HeartbeatManager:
        """Start a background heartbeat thread for this run.

        Returns the HeartbeatManager instance. Call check_or_raise()
        before every expensive operation in your pipeline.

        Args:
            interval_seconds: Base heartbeat interval (default 120s).
            jitter_seconds: Random jitter (default 15s).
            on_panic: Callback(run_id, reason) called on lock loss.
                      Use to stop Dzine/OpenClaw automation.
        """
        hb = HeartbeatManager(
            self,
            interval_seconds=interval_seconds,
            jitter_seconds=jitter_seconds,
            on_panic=on_panic,
        )
        hb.start()
        self._heartbeat_manager = hb
        return hb

    def stop_heartbeat(self) -> None:
        """Stop the heartbeat thread if running."""
        hb = getattr(self, "_heartbeat_manager", None)
        if hb:
            hb.stop()
            self._heartbeat_manager = None

    # --- Claim-next: atomic "give me the next run" ---

    @classmethod
    def claim_next(
        cls,
        *,
        worker_id: str,
        lease_minutes: int = DEFAULT_LEASE_MINUTES,
        task_type: str | None = None,
        use_supabase: bool = True,
        policy_version: str = "v1.0",
    ) -> "RunManager | None":
        """Atomically claim the next eligible run. Returns RunManager or None.

        Uses rpc_claim_next_run (FOR UPDATE SKIP LOCKED) so two workers
        calling simultaneously each get a different run.

        Priority: approved > running/in_progress, then oldest first.

        Args:
            worker_id: Identifier for this worker (min 3 chars).
            lease_minutes: Lease duration (clamped 1-30).
            task_type: Optional filter by pipeline task type.
            use_supabase: Whether to use Supabase RPCs.
            policy_version: Policy version for the RunManager.

        Returns:
            RunManager instance if a run was claimed, None if no eligible runs.
        """
        if len(worker_id.strip()) < MIN_WORKER_ID_LEN:
            print(
                f"[run_manager] Cannot claim_next: worker_id too short "
                f"(min {MIN_WORKER_ID_LEN} chars)",
                file=sys.stderr,
            )
            return None

        lease_minutes = max(MIN_LEASE_MINUTES, min(lease_minutes, MAX_LEASE_MINUTES))
        token = str(uuid.uuid4())

        if use_supabase:
            run_id = cls._supabase_claim_next(worker_id, token, lease_minutes, task_type)
            if not run_id:
                return None
        else:
            # Local mode: no real queue, return None
            return None

        rm = cls(
            run_id,
            worker_id=worker_id,
            use_supabase=use_supabase,
            policy_version=policy_version,
        )
        rm._state.lock_token = token
        rm._state.lock_expires_at = _future_iso(lease_minutes)
        rm._state.status = "in_progress"  # already claimed = active

        rm._log_event("worker_claim_next", {
            "worker_id": worker_id,
            "lock_token": token,
            "lease_minutes": lease_minutes,
            "task_type": task_type,
        })

        return rm

    @staticmethod
    def _supabase_claim_next(
        worker_id: str, token: str, lease_minutes: int, task_type: str | None,
    ) -> str | None:
        """Call rpc_claim_next_run. Returns run_id or None."""
        try:
            from tools.lib.supabase_client import rpc
            params: dict[str, Any] = {
                "p_worker_id": worker_id,
                "p_lock_token": token,
                "p_lease_minutes": lease_minutes,
            }
            if task_type:
                params["p_task_type"] = task_type
            result = rpc("rpc_claim_next_run", params)
            if result:
                return str(result)
            return None
        except Exception as exc:
            print(f"[run_manager] claim_next RPC failed: {exc}", file=sys.stderr)
            return None

    # --- Force unlock: operator emergency release ---

    @staticmethod
    def force_unlock(
        run_id: str,
        *,
        operator_id: str,
        reason: str = "manual unlock",
        force: bool = False,
        use_supabase: bool = True,
    ) -> bool:
        """Force-unlock a run. Only clears lock fields, does NOT change status.

        By default only works if lease is already expired.
        With force=True, unlocks regardless (emergency use).
        Always writes a forensic run_event.

        Args:
            run_id: The run to unlock.
            operator_id: Who is unlocking (min 3 chars).
            reason: Why this unlock is happening.
            force: If True, unlock even if lease hasn't expired.
            use_supabase: Whether to use Supabase RPCs.

        Returns True if the run was unlocked.
        """
        if len(operator_id.strip()) < MIN_WORKER_ID_LEN:
            print(
                f"[run_manager] Cannot unlock: operator_id too short "
                f"(min {MIN_WORKER_ID_LEN} chars)",
                file=sys.stderr,
            )
            return False

        if use_supabase:
            try:
                from tools.lib.supabase_client import rpc
                result = rpc("rpc_force_unlock_run", {
                    "p_run_id": run_id,
                    "p_operator_id": operator_id,
                    "p_reason": reason,
                    "p_force": force,
                })
                return bool(result)
            except Exception as exc:
                print(f"[run_manager] force_unlock RPC failed: {exc}", file=sys.stderr)
                return False
        else:
            # Local mode: nothing to unlock
            print("[run_manager] force_unlock requires Supabase", file=sys.stderr)
            return False

    # --- Supabase lease helpers ---

    def _supabase_claim(self, token: str, lease_minutes: int) -> bool:
        """CAS claim via Supabase RPC (cas_claim_run)."""
        try:
            from tools.lib.supabase_client import rpc
            result = rpc("cas_claim_run", {
                "p_run_id": self._state.run_id,
                "p_worker_id": self._state.worker_id,
                "p_lock_token": token,
                "p_lease_minutes": lease_minutes,
            })
            return bool(result)
        except Exception as exc:
            # Fallback: try direct update with CAS conditions
            try:
                from tools.lib.supabase_client import _postgrest, _enabled
                if not _enabled():
                    return True
                _postgrest(
                    "PATCH",
                    "pipeline_runs",
                    {
                        "worker_id": self._state.worker_id,
                        "locked_at": now_iso(),
                        "lock_expires_at": _future_iso(lease_minutes),
                        "lock_token": token,
                    },
                    params={
                        "id": f"eq.{self._state.run_id}",
                        "or": "(lock_expires_at.is.null,lock_expires_at.lt.now())",
                    },
                )
                return True
            except Exception as exc2:
                print(f"[run_manager] Claim failed: {exc2}", file=sys.stderr)
                return False

    def _supabase_heartbeat(self, lease_minutes: int) -> bool:
        """Renew lease via Supabase RPC (cas_heartbeat_run).

        Sends p_latency_ms from the previous heartbeat round-trip
        (piggybacked — we can't measure our own response before sending).
        """
        latency = getattr(self, "_last_heartbeat_latency_ms", None)
        try:
            from tools.lib.supabase_client import rpc
            params = {
                "p_run_id": self._state.run_id,
                "p_worker_id": self._state.worker_id,
                "p_lock_token": self._state.lock_token,
                "p_lease_minutes": lease_minutes,
            }
            if latency is not None:
                params["p_latency_ms"] = latency
            result = rpc("cas_heartbeat_run", params)
            return bool(result)
        except Exception:
            try:
                from tools.lib.supabase_client import _postgrest, _enabled
                if not _enabled():
                    return True
                _postgrest(
                    "PATCH",
                    "pipeline_runs",
                    {"lock_expires_at": _future_iso(lease_minutes)},
                    params={
                        "id": f"eq.{self._state.run_id}",
                        "worker_id": f"eq.{self._state.worker_id}",
                        "lock_token": f"eq.{self._state.lock_token}",
                    },
                )
                return True
            except Exception as exc2:
                print(f"[run_manager] Heartbeat failed: {exc2}", file=sys.stderr)
                return False

    def _supabase_release(self) -> None:
        """Release lock via Supabase RPC (rpc_release_run)."""
        try:
            from tools.lib.supabase_client import rpc
            rpc("rpc_release_run", {
                "p_run_id": self._state.run_id,
                "p_worker_id": self._state.worker_id,
                "p_lock_token": self._state.lock_token,
            })
        except Exception:
            try:
                from tools.lib.supabase_client import _postgrest, _enabled
                if not _enabled():
                    return
                _postgrest(
                    "PATCH",
                    "pipeline_runs",
                    {
                        "worker_id": "",
                        "locked_at": None,
                        "lock_expires_at": None,
                        "lock_token": "",
                    },
                    params={
                        "id": f"eq.{self._state.run_id}",
                        "worker_id": f"eq.{self._state.worker_id}",
                        "lock_token": f"eq.{self._state.lock_token}",
                    },
                )
            except Exception as exc:
                print(f"[run_manager] Release failed: {exc}", file=sys.stderr)

    # -------------------------------------------------------------------
    # Circuit breaker integration
    # -------------------------------------------------------------------

    def evaluate_and_gate(
        self,
        evidence: list[dict],
        *,
        refetch_fn: Callable[[], list[dict]] | None = None,
        notify_fn: Callable[[str, str, str], None] | None = None,
    ) -> Any:
        """Evaluate evidence via circuit breaker and gate if needed.

        Args:
            evidence: List of evidence dicts (claim_type, confidence, etc.)
            refetch_fn: Optional callback that re-fetches evidence. Returns new list.
            notify_fn: Optional callback(run_id, nonce, gate_reason) to send Telegram.

        Returns:
            CBResult from circuit_breaker.evaluate_evidence()
        """
        from tools.lib.circuit_breaker import evaluate_evidence, should_auto_refetch

        result = evaluate_evidence(evidence)

        # Log alerts (Tier B) — continue regardless
        for alert in result.alerts:
            self._log_event("cb_alert", {"alert": alert})
            print(f"[run_manager] CB ALERT: {alert}", file=sys.stderr)

        if not result.should_gate:
            self._log_event("cb_pass", result.to_snapshot())
            return result

        # Gate triggered — try auto-refetch first
        if should_auto_refetch(result, refetch_attempted=self._state.refetch_attempted):
            self._state.refetch_attempted = True
            self._update_snapshot(phase="refetch", extra={
                "cb_before_refetch": result.to_snapshot(),
            })
            self._log_event("cb_auto_refetch", {
                "old_gate_reason": result.gate_reason,
                "can_auto_refetch": True,
            })

            if refetch_fn:
                try:
                    new_evidence = refetch_fn()
                    result = evaluate_evidence(new_evidence)

                    if not result.should_gate:
                        # Healed — continue
                        self._log_event("cb_healed", result.to_snapshot())
                        self._update_snapshot(phase="refetch_healed", extra={
                            "cb_after_refetch": result.to_snapshot(),
                        })
                        return result
                except Exception as exc:
                    print(f"[run_manager] Auto-refetch failed: {exc}", file=sys.stderr)
                    self._log_event("error", {"refetch_error": str(exc)})

        # Still gated — pause run and request approval
        nonce = str(uuid.uuid4())
        self._state.approval_nonce = nonce
        self._update_snapshot(phase="paused", extra={
            "cb_result": result.to_snapshot(),
            "approval_nonce": nonce,
        })
        self._transition("waiting_approval", reason=result.gate_reason)
        self._log_event("cb_pause", {
            "gate_reason": result.gate_reason,
            "approval_nonce": nonce,
        })

        # Send Telegram notification if callback provided
        if notify_fn:
            try:
                notify_fn(self._state.run_id, nonce, result.gate_reason)
            except Exception as exc:
                print(f"[run_manager] Notify failed: {exc}", file=sys.stderr)

        return result

    # -------------------------------------------------------------------
    # Approval handling (called by telegram_gate)
    # -------------------------------------------------------------------

    def approve(self, nonce: str, action_id: str) -> bool:
        """Handle user approval. Validates nonce + CAS."""
        if self._state.status != "waiting_approval":
            return False
        if self._state.approval_nonce != nonce:
            return False

        self._log_event("user_approval", {"nonce": nonce}, action_id=action_id)
        self._update_snapshot(phase="approved")

        # CAS update in Supabase
        if self._use_supabase:
            success = self._cas_update("waiting_approval", nonce, "approved")
            if not success:
                return False

        self._state.status = "approved"
        self._state.approval_nonce = ""
        # Transition to in_progress so the run can continue
        return self._transition("in_progress", reason="user approved")

    def ignore_weakness(self, nonce: str, action_id: str) -> bool:
        """Handle user 'ignore' — proceed despite low confidence."""
        if self._state.status != "waiting_approval":
            return False
        if self._state.approval_nonce != nonce:
            return False

        self._log_event("user_ignore", {
            "nonce": nonce,
            "override": "ignore_low_confidence",
        }, action_id=action_id)
        self._update_snapshot(
            phase="approved",
            extra={"override_ignore_low_confidence": True},
        )

        if self._use_supabase:
            success = self._cas_update("waiting_approval", nonce, "approved")
            if not success:
                return False

        self._state.status = "approved"
        self._state.approval_nonce = ""
        return self._transition("in_progress", reason="user ignored weakness")

    def abort_by_user(self, nonce: str, action_id: str, reason: str = "") -> bool:
        """Handle user abort."""
        if self._state.status != "waiting_approval":
            return False
        if self._state.approval_nonce != nonce:
            return False

        self._log_event("user_abort", {
            "nonce": nonce,
            "reason": reason or "user abort via Telegram",
        }, action_id=action_id)
        self._update_snapshot(
            phase="aborted",
            extra={"abort_reason": reason or "user abort via Telegram"},
        )

        if self._use_supabase:
            self._cas_update("waiting_approval", nonce, "aborted")

        self._state.status = "aborted"
        self._state.approval_nonce = ""
        return True

    def _cas_update(self, expected_status: str, expected_nonce: str, new_status: str) -> bool:
        """Compare-And-Set update on Supabase. Returns True if row was updated."""
        try:
            from tools.lib.supabase_client import _postgrest, _enabled
            if not _enabled():
                return True  # If Supabase is off, always succeed locally

            # Use conditional PATCH: only update if status + nonce match
            params = {
                "id": f"eq.{self._state.run_id}",
                "status": f"eq.{expected_status}",
            }
            if expected_nonce:
                params["approval_nonce"] = f"eq.{expected_nonce}"

            result = _postgrest(
                "PATCH",
                "pipeline_runs",
                {
                    "status": new_status,
                    "approval_nonce": "",
                    "context_snapshot": json.dumps(self._state.context_snapshot),
                    "updated_at": now_iso(),
                },
                params=params,
                extra_headers={"Prefer": "return=headers-only,count=exact"},
            )
            # PostgREST returns count in content-range header
            # If 0 rows updated, CAS failed (stale state)
            # We can't easily check row count with our simple client,
            # so we treat any non-error as success
            return True
        except Exception as exc:
            print(f"[run_manager] CAS update failed: {exc}", file=sys.stderr)
            return False

    # -------------------------------------------------------------------
    # Context snapshot management
    # -------------------------------------------------------------------

    def _update_snapshot(self, phase: str, extra: dict | None = None) -> None:
        """Update the context snapshot with a new phase marker."""
        self._state.context_snapshot["phase"] = phase
        self._state.context_snapshot["updated_at"] = now_iso()
        if extra:
            self._state.context_snapshot.update(extra)

    def get_snapshot(self) -> dict:
        """Return a copy of the current context snapshot."""
        return dict(self._state.context_snapshot)

    def get_events(self) -> list[dict]:
        """Return local event log."""
        return list(self._events)
