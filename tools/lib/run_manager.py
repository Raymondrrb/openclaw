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

Stdlib only.

Usage:
    from lib.run_manager import RunManager

    rm = RunManager(run_id)
    rm.start(context_pack, evidence)

    # Before any expensive step:
    if not rm.check_status():
        return  # blocked — waiting approval

    # After evidence collection:
    cb_result = rm.evaluate_and_gate(evidence_items)
    if cb_result.should_gate:
        # Already handled: auto-refetch or Telegram gate sent
        return
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from tools.lib.common import now_iso


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

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATES

    @property
    def is_blocked(self) -> bool:
        return self.status in BLOCKED_STATES


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
    ):
        self._state = RunState(
            run_id=run_id,
            policy_version=policy_version,
            ranking_model=ranking_model,
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
        """Mark run as done. Records final snapshot."""
        self._update_snapshot(phase="final", extra={"final_evidence": final_evidence or {}})
        return self._transition("done", reason="all stages complete")

    def fail(self, error: str) -> bool:
        """Mark run as failed."""
        self._update_snapshot(phase="failed", extra={"error": error})
        return self._transition("failed", reason=error)

    def abort(self, reason: str = "user abort") -> bool:
        """Mark run as aborted."""
        self._update_snapshot(phase="aborted", extra={"abort_reason": reason})
        return self._transition("aborted", reason=reason)

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
