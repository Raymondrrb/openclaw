#!/usr/bin/env python3
"""Tests for run manager infrastructure: circuit breaker, run manager,
telegram gate, context builder.

Run:
    python3 tools/test_run_manager.py

Covers:
    - Circuit breaker tier-based gating (Tier A gates, Tier B alerts, Tier C ignored)
    - Conflict detection (high-trust sources disagreeing)
    - SKU fingerprint computation and change detection
    - Token-aware refresh logic
    - Run manager state machine transitions
    - CAS (Compare-And-Set) status updates
    - Idempotent gate handler
    - Context builder validation and selection
    - Telegram gate callback parsing
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from lib.circuit_breaker import (
    TIER_A, TIER_B, TIER_C,
    GATE_ONLY_CLAIMS,
    EvidenceItem,
    ClaimScore,
    CBResult,
    evaluate_evidence,
    should_auto_refetch,
    needs_refresh,
    detect_conflicts,
    compute_fingerprint,
    build_hedge_annotations,
)
from lib.context_builder import (
    ContextPack,
    NoteRef,
    build_context_pack,
    load_vault_index,
    load_canonicals,
    _validate_no_alias_collisions,
    _parse_simple_yaml,
)
from lib.run_manager import (
    RunManager,
    RunState,
    HeartbeatManager,
    LostLock,
    VALID_TRANSITIONS,
    BLOCKED_STATES,
    ACTIVE_STATES,
    CLAIMABLE_STATUSES,
    DEFAULT_LEASE_MINUTES,
    MIN_LEASE_MINUTES,
    MAX_LEASE_MINUTES,
    MIN_WORKER_ID_LEN,
    HEARTBEAT_INTERVAL_SECONDS,
)
from lib.telegram_gate import (
    parse_callback_data,
    handle_gate_callback,
    send_gate_message,
)


# =========================================================================
# Circuit Breaker Tests
# =========================================================================

class TestCircuitBreakerTiers(unittest.TestCase):
    """Tier A gates, Tier B alerts, Tier C ignored."""

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def test_tier_a_weak_gates(self):
        """A weak Tier A claim (price) should gate the pipeline."""
        evidence = [
            {"claim_type": "price", "confidence": 0.3, "fetched_at": self._now_iso(), "trust_tier": 3},
        ]
        result = evaluate_evidence(evidence)
        self.assertTrue(result.should_gate)
        self.assertIn("price", result.gate_reason)

    def test_tier_a_strong_passes(self):
        """A strong Tier A claim should pass."""
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": self._now_iso(), "trust_tier": 5},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": self._now_iso(), "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.85, "fetched_at": self._now_iso(), "trust_tier": 4},
        ]
        result = evaluate_evidence(evidence)
        self.assertFalse(result.should_gate)

    def test_tier_b_weak_alerts_no_gate(self):
        """A weak Tier B claim should alert but NOT gate."""
        evidence = [
            # Tier A all strong
            {"claim_type": "price", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": self._now_iso(), "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": self._now_iso(), "trust_tier": 3},
            # Tier B weak
            {"claim_type": "availability", "confidence": 0.2, "fetched_at": self._now_iso(), "trust_tier": 2},
        ]
        result = evaluate_evidence(evidence)
        self.assertFalse(result.should_gate)
        self.assertGreater(len(result.alerts), 0)

    def test_tier_c_never_blocks(self):
        """Tier C claims should never cause gates or alerts."""
        evidence = [
            # Tier A strong
            {"claim_type": "price", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": self._now_iso(), "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": self._now_iso(), "trust_tier": 3},
            # Tier C weak — should not appear in alerts
            {"claim_type": "material", "confidence": 0.1, "fetched_at": self._now_iso(), "trust_tier": 1},
            {"claim_type": "color", "confidence": 0.0, "fetched_at": self._now_iso(), "trust_tier": 1},
        ]
        result = evaluate_evidence(evidence)
        self.assertFalse(result.should_gate)
        # Tier C claims should NOT appear in alerts
        for alert in result.alerts:
            self.assertNotIn("material", alert)
            self.assertNotIn("color", alert)

    def test_missing_critical_claim_gates(self):
        """Missing a critical claim entirely should gate."""
        evidence = [
            # Only price — voltage, compatibility, core_specs missing
            {"claim_type": "price", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
        ]
        result = evaluate_evidence(evidence)
        self.assertTrue(result.should_gate)

    def test_expired_evidence_gates(self):
        """Expired Tier A evidence should gate."""
        old = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": old, "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "core_specs", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
        ]
        result = evaluate_evidence(evidence)
        # Price TTL is 12h, evidence is 24h old → expired → weak
        self.assertTrue(result.should_gate)

    def test_empty_evidence_gates(self):
        """No evidence at all should gate."""
        result = evaluate_evidence([])
        self.assertTrue(result.should_gate)


class TestAutoRefetch(unittest.TestCase):

    def test_auto_refetch_on_expired(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": old, "trust_tier": 4},
        ]
        result = evaluate_evidence(evidence)
        self.assertTrue(should_auto_refetch(result, refetch_attempted=False))

    def test_no_auto_refetch_on_low_trust(self):
        evidence = [
            {"claim_type": "price", "confidence": 0.3, "fetched_at": datetime.now(timezone.utc).isoformat(), "trust_tier": 2},
        ]
        result = evaluate_evidence(evidence)
        # Low trust → structural → can't auto-refetch
        self.assertFalse(should_auto_refetch(result, refetch_attempted=False))

    def test_no_double_refetch(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": old, "trust_tier": 4},
        ]
        result = evaluate_evidence(evidence)
        # First attempt OK
        self.assertTrue(should_auto_refetch(result, refetch_attempted=False))
        # Second attempt blocked (max_auto_refetch=1)
        self.assertFalse(should_auto_refetch(result, refetch_attempted=True))


class TestConflictDetection(unittest.TestCase):
    """Two high-trust sources disagreeing on same claim."""

    def test_detects_voltage_conflict(self):
        evidence = [
            {"claim_type": "voltage", "confidence": 0.95, "trust_tier": 5,
             "source_name": "Official", "value": "127V"},
            {"claim_type": "voltage", "confidence": 0.85, "trust_tier": 4,
             "source_name": "Marketplace", "value": "220V"},
        ]
        conflicts = detect_conflicts(evidence, min_trust_tier=4)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["claim_type"], "voltage")
        self.assertEqual(conflicts[0]["severity"], "critical")
        self.assertEqual(len(conflicts[0]["values"]), 2)

    def test_no_conflict_same_value(self):
        evidence = [
            {"claim_type": "voltage", "confidence": 0.95, "trust_tier": 5,
             "source_name": "Official", "value": "127V"},
            {"claim_type": "voltage", "confidence": 0.85, "trust_tier": 4,
             "source_name": "Retailer", "value": "127V"},
        ]
        conflicts = detect_conflicts(evidence, min_trust_tier=4)
        self.assertEqual(len(conflicts), 0)

    def test_ignores_low_trust_conflict(self):
        evidence = [
            {"claim_type": "voltage", "confidence": 0.95, "trust_tier": 5,
             "source_name": "Official", "value": "127V"},
            {"claim_type": "voltage", "confidence": 0.85, "trust_tier": 2,
             "source_name": "Random Blog", "value": "220V"},
        ]
        # Random Blog trust_tier=2 < min_trust_tier=4 → ignored
        conflicts = detect_conflicts(evidence, min_trust_tier=4)
        self.assertEqual(len(conflicts), 0)

    def test_tier_b_conflict_is_warning(self):
        evidence = [
            {"claim_type": "availability", "confidence": 0.9, "trust_tier": 5,
             "source_name": "Amazon", "value": True},
            {"claim_type": "availability", "confidence": 0.8, "trust_tier": 4,
             "source_name": "BestBuy", "value": False},
        ]
        conflicts = detect_conflicts(evidence, min_trust_tier=4)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["severity"], "warning")


class TestSKUFingerprint(unittest.TestCase):

    def test_same_inputs_same_hash(self):
        h1 = compute_fingerprint("B0TEST1", brand="Sony", model_number="WF-1000XM5")
        h2 = compute_fingerprint("B0TEST1", brand="Sony", model_number="WF-1000XM5")
        self.assertEqual(h1, h2)

    def test_model_change_changes_hash(self):
        h1 = compute_fingerprint("B0TEST1", brand="Sony", model_number="WF-1000XM5")
        h2 = compute_fingerprint("B0TEST1", brand="Sony", model_number="WF-1000XM6")
        self.assertNotEqual(h1, h2)

    def test_variant_change_changes_hash(self):
        h1 = compute_fingerprint("B0TEST1", variant_attrs={"color": "black"})
        h2 = compute_fingerprint("B0TEST1", variant_attrs={"color": "silver"})
        self.assertNotEqual(h1, h2)

    def test_fingerprint_triggers_refresh(self):
        """Fingerprint change forces refresh for specs claims."""
        self.assertTrue(needs_refresh("core_specs", fingerprint_changed=True))
        self.assertTrue(needs_refresh("voltage", fingerprint_changed=True))
        self.assertTrue(needs_refresh("compatibility", fingerprint_changed=True))


class TestNeedsRefresh(unittest.TestCase):

    def _hours_ago(self, hours: float) -> str:
        return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    def test_price_expired(self):
        self.assertTrue(needs_refresh("price", last_fetched_at=self._hours_ago(13)))

    def test_price_fresh(self):
        self.assertFalse(needs_refresh("price", last_fetched_at=self._hours_ago(6)))

    def test_specs_hash_change(self):
        self.assertTrue(needs_refresh("core_specs", content_hash_changed=True))

    def test_reviews_new_product(self):
        self.assertTrue(needs_refresh("review_sentiment", is_new_product=True))

    def test_tier_c_rarely_refreshes(self):
        # material TTL = 365 days, only 30 days old → no refresh
        self.assertFalse(needs_refresh("material", last_fetched_at=self._hours_ago(720)))


class TestHedgeAnnotations(unittest.TestCase):
    """Editorial hedging based on CB evaluation."""

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def test_strong_evidence_all_firm(self):
        """All claims above threshold → all 'firm'."""
        now = self._now_iso()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
        ]
        result = evaluate_evidence(evidence)
        annotations = build_hedge_annotations(result)
        for ann in annotations:
            if ann["claim_type"] in ("price", "voltage", "compatibility", "core_specs"):
                self.assertEqual(ann["hedge_level"], "firm")
                self.assertEqual(ann["template"], "")

    def test_expired_tier_a_hedged(self):
        """Expired Tier A → 'hedged' with qualifying template."""
        old = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        now = self._now_iso()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": old, "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
        ]
        result = evaluate_evidence(evidence)
        annotations = build_hedge_annotations(result)
        price_ann = [a for a in annotations if a["claim_type"] == "price"][0]
        self.assertEqual(price_ann["hedge_level"], "hedged")
        self.assertEqual(price_ann["weakness_reason"], "expired")
        self.assertIn("{claim}", price_ann["template"])

    def test_low_confidence_tier_a_hedged(self):
        """Low confidence Tier A → 'hedged'."""
        now = self._now_iso()
        evidence = [
            {"claim_type": "price", "confidence": 0.3, "fetched_at": now, "trust_tier": 3},
        ]
        result = evaluate_evidence(evidence)
        annotations = build_hedge_annotations(result)
        price_ann = [a for a in annotations if a["claim_type"] == "price"][0]
        self.assertEqual(price_ann["hedge_level"], "hedged")
        self.assertEqual(price_ann["weakness_reason"], "low_confidence")

    def test_missing_tier_b_omit(self):
        """Missing Tier B → 'omit' (empty template)."""
        now = self._now_iso()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            # availability is Tier B — not provided, so "missing"
        ]
        result = evaluate_evidence(evidence)
        annotations = build_hedge_annotations(result)
        # availability should NOT appear (it's Tier B missing → only alert, no score unless in evidence)
        # But if it appears, it should be omit
        avail = [a for a in annotations if a["claim_type"] == "availability"]
        if avail:
            self.assertEqual(avail[0]["hedge_level"], "omit")

    def test_missing_safety_claim_gate_only(self):
        """Missing voltage/compat/specs → 'gate_only', never hedged."""
        now = self._now_iso()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
        ]
        result = evaluate_evidence(evidence)
        annotations = build_hedge_annotations(result)

        for claim in ("voltage", "compatibility", "core_specs"):
            ann = [a for a in annotations if a["claim_type"] == claim][0]
            self.assertEqual(ann["hedge_level"], "gate_only",
                             f"{claim} should be gate_only, not hedged")
            self.assertEqual(ann["template"], "",
                             f"{claim} should have no template")

    def test_missing_price_hedged(self):
        """Missing price (non-safety Tier A) → 'hedged' with template."""
        now = self._now_iso()
        evidence = [
            {"claim_type": "voltage", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            # price missing
        ]
        result = evaluate_evidence(evidence)
        annotations = build_hedge_annotations(result)
        price_ann = [a for a in annotations if a["claim_type"] == "price"][0]
        self.assertEqual(price_ann["hedge_level"], "hedged")
        self.assertIn("fabricante", price_ann["template"])

    def test_support_line_with_evidence(self):
        """support_line generated from best evidence source."""
        now = self._now_iso()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": now,
             "trust_tier": 4, "source_name": "Amazon"},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": now,
             "trust_tier": 5, "source_name": "Manual do fabricante"},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
        ]
        result = evaluate_evidence(evidence)
        annotations = build_hedge_annotations(result, evidence=evidence)

        price_ann = [a for a in annotations if a["claim_type"] == "price"][0]
        self.assertIn("Amazon", price_ann["support_line"])
        self.assertIn("verificado em", price_ann["support_line"])

        voltage_ann = [a for a in annotations if a["claim_type"] == "voltage"][0]
        self.assertIn("Manual do fabricante", voltage_ann["support_line"])

    def test_support_line_empty_without_evidence(self):
        """Without evidence arg, support_line is empty."""
        now = self._now_iso()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
        ]
        result = evaluate_evidence(evidence)
        annotations = build_hedge_annotations(result)  # no evidence arg
        for ann in annotations:
            self.assertEqual(ann["support_line"], "")

    def test_snapshot_includes_hedge_annotations(self):
        """to_snapshot() includes hedge_annotations field."""
        now = self._now_iso()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
        ]
        result = evaluate_evidence(evidence)
        snapshot = result.to_snapshot()
        self.assertIn("hedge_annotations", snapshot)
        self.assertIsInstance(snapshot["hedge_annotations"], list)
        # All firm
        for ann in snapshot["hedge_annotations"]:
            if ann["claim_type"] in ("price", "voltage", "compatibility", "core_specs"):
                self.assertEqual(ann["hedge_level"], "firm")


class TestCBResultSnapshot(unittest.TestCase):

    def test_snapshot_serializable(self):
        now = datetime.now(timezone.utc).isoformat()
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
        ]
        result = evaluate_evidence(evidence)
        snapshot = result.to_snapshot()
        # Must be JSON-serializable
        json_str = json.dumps(snapshot)
        self.assertIn("should_gate", json_str)
        self.assertIn("scores", json_str)
        self.assertIn("hedge_annotations", json_str)


# =========================================================================
# Run Manager Tests
# =========================================================================

class TestRunManagerStateMachine(unittest.TestCase):
    """State machine transitions."""

    def _make_rm(self, run_id: str = "test-run-1") -> RunManager:
        return RunManager(run_id, use_supabase=False)

    def test_start_transitions_to_in_progress(self):
        rm = self._make_rm()
        self.assertEqual(rm.status, "pending")
        ok = rm.start()
        self.assertTrue(ok)
        self.assertEqual(rm.status, "in_progress")

    def test_complete(self):
        rm = self._make_rm()
        rm.start()
        ok = rm.complete()
        self.assertTrue(ok)
        self.assertEqual(rm.status, "done")

    def test_fail(self):
        rm = self._make_rm()
        rm.start()
        ok = rm.fail("something broke")
        self.assertTrue(ok)
        self.assertEqual(rm.status, "failed")

    def test_abort(self):
        rm = self._make_rm()
        rm.start()
        ok = rm.abort("user cancelled")
        self.assertTrue(ok)
        self.assertEqual(rm.status, "aborted")

    def test_invalid_transition_rejected(self):
        rm = self._make_rm()
        rm.start()
        rm.complete()
        # done → in_progress is not allowed
        ok = rm.start()
        self.assertFalse(ok)
        self.assertEqual(rm.status, "done")

    def test_blocked_states(self):
        rm = self._make_rm()
        rm.start()
        rm.complete()
        self.assertFalse(rm.check_status())  # done is blocked


class TestRunManagerCheckStatus(unittest.TestCase):
    """check_status() must return False when blocked."""

    def test_active_states_pass(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        self.assertTrue(rm.check_status())

    def test_waiting_approval_blocked(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        # Force into waiting_approval
        rm._state.status = "waiting_approval"
        self.assertFalse(rm.check_status())

    def test_require_active_raises(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        rm._state.status = "waiting_approval"
        with self.assertRaises(RuntimeError):
            rm.require_active()


class TestRunManagerApproval(unittest.TestCase):
    """CAS approval flow."""

    def test_approve_with_correct_nonce(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        # Simulate gate
        rm._state.status = "waiting_approval"
        rm._state.approval_nonce = "test-nonce-123"

        ok = rm.approve("test-nonce-123", "action-001")
        self.assertTrue(ok)
        self.assertEqual(rm.status, "in_progress")

    def test_approve_with_wrong_nonce_rejected(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        rm._state.status = "waiting_approval"
        rm._state.approval_nonce = "test-nonce-123"

        ok = rm.approve("wrong-nonce", "action-001")
        self.assertFalse(ok)
        self.assertEqual(rm.status, "waiting_approval")

    def test_approve_wrong_state_rejected(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        # in_progress, not waiting_approval
        ok = rm.approve("any-nonce", "action-001")
        self.assertFalse(ok)

    def test_ignore_weakness(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        rm._state.status = "waiting_approval"
        rm._state.approval_nonce = "nonce-456"

        ok = rm.ignore_weakness("nonce-456", "action-002")
        self.assertTrue(ok)
        self.assertEqual(rm.status, "in_progress")
        # Snapshot should have override flag
        self.assertTrue(rm.get_snapshot().get("override_ignore_low_confidence"))

    def test_abort_by_user(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        rm._state.status = "waiting_approval"
        rm._state.approval_nonce = "nonce-789"

        ok = rm.abort_by_user("nonce-789", "action-003", "no longer needed")
        self.assertTrue(ok)
        self.assertEqual(rm.status, "aborted")


class TestRunManagerCBIntegration(unittest.TestCase):
    """Circuit breaker integration via evaluate_and_gate()."""

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def test_strong_evidence_passes(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()

        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": self._now_iso(), "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": self._now_iso(), "trust_tier": 3},
        ]
        result = rm.evaluate_and_gate(evidence)
        self.assertFalse(result.should_gate)
        self.assertEqual(rm.status, "in_progress")

    def test_weak_evidence_gates(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()

        evidence = [
            {"claim_type": "price", "confidence": 0.3, "fetched_at": self._now_iso(), "trust_tier": 2},
        ]
        result = rm.evaluate_and_gate(evidence)
        self.assertTrue(result.should_gate)
        self.assertEqual(rm.status, "waiting_approval")
        self.assertNotEqual(rm._state.approval_nonce, "")

    def test_auto_refetch_heals(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()

        old = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        weak_evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": old, "trust_tier": 4},
        ]

        now = self._now_iso()
        strong_evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.8, "fetched_at": now, "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.7, "fetched_at": now, "trust_tier": 3},
        ]

        def refetch():
            return strong_evidence

        result = rm.evaluate_and_gate(weak_evidence, refetch_fn=refetch)
        # Should have auto-refetched and healed
        self.assertFalse(result.should_gate)
        self.assertEqual(rm.status, "in_progress")


class TestRunManagerSnapshotIntegrity(unittest.TestCase):
    """Context snapshots are forensic — phase markers, timestamps."""

    def test_snapshot_has_phase_markers(self):
        rm = RunManager("test-run", use_supabase=False, policy_version="v1.0")
        rm.start(context_pack={"notes": ["sop_research"]})

        snapshot = rm.get_snapshot()
        self.assertEqual(snapshot["phase"], "started")
        self.assertIn("policy_version", snapshot)
        self.assertIn("started_at", snapshot)
        self.assertIn("context_pack", snapshot)

    def test_events_logged(self):
        rm = RunManager("test-run", use_supabase=False)
        rm.start()
        rm.complete()

        events = rm.get_events()
        types = [e["event_type"] for e in events]
        self.assertIn("status_change", types)


# =========================================================================
# Worker Lease Tests
# =========================================================================

class TestWorkerLeaseClaim(unittest.TestCase):
    """Worker claim/heartbeat/release lifecycle."""

    def test_claim_success(self):
        """Worker can claim a run in claimable status."""
        rm = RunManager("lease-run-1", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        self.assertTrue(rm.claim())
        self.assertTrue(rm.is_claimed)
        self.assertNotEqual(rm.lock_token, "")

    def test_claim_without_worker_id_fails(self):
        """Cannot claim without a worker_id."""
        rm = RunManager("lease-run-2", use_supabase=False)
        rm.start()
        self.assertFalse(rm.claim())

    def test_claim_pending_fails(self):
        """Cannot claim a run in pending status."""
        rm = RunManager("lease-run-3", use_supabase=False, worker_id="RayMac-01")
        # Don't start — status is still 'pending'
        self.assertFalse(rm.claim())

    def test_claim_done_fails(self):
        """Cannot claim a run that's already done."""
        rm = RunManager("lease-run-4", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.complete()
        self.assertFalse(rm.claim())

    def test_heartbeat_renews_lease(self):
        """Heartbeat extends the lock_expires_at."""
        rm = RunManager("lease-run-5", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim(lease_minutes=1)
        old_expires = rm._state.lock_expires_at
        # Small sleep to get different timestamp
        rm.heartbeat(lease_minutes=10)
        new_expires = rm._state.lock_expires_at
        self.assertNotEqual(old_expires, new_expires)

    def test_heartbeat_without_claim_fails(self):
        """Heartbeat without an active claim returns False."""
        rm = RunManager("lease-run-6", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        self.assertFalse(rm.heartbeat())

    def test_release_clears_lock(self):
        """Release clears the lock token and expires_at."""
        rm = RunManager("lease-run-7", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim()
        self.assertTrue(rm.is_claimed)
        rm.release_lock()
        self.assertEqual(rm._state.lock_token, "")
        self.assertEqual(rm._state.lock_expires_at, "")

    def test_complete_auto_releases(self):
        """Completing a run automatically releases the lock."""
        rm = RunManager("lease-run-8", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim()
        self.assertTrue(rm.is_claimed)
        rm.complete()
        self.assertEqual(rm._state.lock_token, "")

    def test_fail_auto_releases(self):
        """Failing a run automatically releases the lock."""
        rm = RunManager("lease-run-9", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim()
        rm.fail("something broke")
        self.assertEqual(rm._state.lock_token, "")

    def test_abort_auto_releases(self):
        """Aborting a run automatically releases the lock."""
        rm = RunManager("lease-run-10", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim()
        rm.abort("cancelled")
        self.assertEqual(rm._state.lock_token, "")

    def test_reclaim_with_existing_token(self):
        """Worker can reclaim using a previously persisted token."""
        rm = RunManager("lease-run-11", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim()
        saved_token = rm.lock_token

        # Simulate restart: new RunManager with same worker_id
        rm2 = RunManager("lease-run-11", use_supabase=False, worker_id="RayMac-01")
        rm2._state.status = "in_progress"
        rm2._state.lock_token = saved_token
        rm2._state.lock_expires_at = rm._state.lock_expires_at
        # Reclaim using saved token
        ok = rm2.claim(existing_token=saved_token)
        self.assertTrue(ok)

    def test_events_logged_on_claim(self):
        """Claim and release events are logged."""
        rm = RunManager("lease-run-12", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim()
        rm.release_lock()

        event_types = [e["event_type"] for e in rm.get_events()]
        self.assertIn("worker_claim", event_types)
        self.assertIn("worker_release", event_types)

    # --- SRE guardrail tests ---

    def test_short_worker_id_rejected(self):
        """Worker_id shorter than 3 chars is rejected."""
        rm = RunManager("lease-guard-1", use_supabase=False, worker_id="AB")
        rm.start()
        self.assertFalse(rm.claim())

    def test_whitespace_worker_id_rejected(self):
        """Worker_id that's all whitespace is rejected."""
        rm = RunManager("lease-guard-2", use_supabase=False, worker_id="   ")
        rm.start()
        self.assertFalse(rm.claim())

    def test_lease_clamp_low(self):
        """Lease below 1 minute is clamped to 1."""
        rm = RunManager("lease-guard-3", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim(lease_minutes=0)
        # Should succeed (clamped to 1) and the lock should be valid
        self.assertTrue(rm.is_claimed)

    def test_lease_clamp_high(self):
        """Lease above 30 minutes is clamped to 30."""
        rm = RunManager("lease-guard-4", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim(lease_minutes=999)
        self.assertTrue(rm.is_claimed)
        # Verify the clamped expiry is ~30 min, not ~999 min
        from datetime import datetime, timezone
        expires = datetime.fromisoformat(rm._state.lock_expires_at)
        now = datetime.now(timezone.utc)
        delta = (expires - now).total_seconds() / 60.0
        self.assertLessEqual(delta, 31)  # within 31 min (1 min buffer)

    def test_heartbeat_lease_clamped(self):
        """Heartbeat also clamps lease values."""
        rm = RunManager("lease-guard-5", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim()
        rm.heartbeat(lease_minutes=200)
        from datetime import datetime, timezone
        expires = datetime.fromisoformat(rm._state.lock_expires_at)
        now = datetime.now(timezone.utc)
        delta = (expires - now).total_seconds() / 60.0
        self.assertLessEqual(delta, 31)


class TestClaimNextAndForceUnlock(unittest.TestCase):
    """Tests for claim_next (local returns None) and force_unlock."""

    def test_claim_next_local_returns_none(self):
        """claim_next in local mode returns None (no queue)."""
        result = RunManager.claim_next(
            worker_id="RayMac-01",
            use_supabase=False,
        )
        self.assertIsNone(result)

    def test_claim_next_short_worker_id_returns_none(self):
        """claim_next with short worker_id returns None."""
        result = RunManager.claim_next(
            worker_id="AB",
            use_supabase=False,
        )
        self.assertIsNone(result)

    def test_force_unlock_local_returns_false(self):
        """force_unlock in local mode returns False."""
        result = RunManager.force_unlock(
            "some-run-id",
            operator_id="Ray",
            reason="test",
            use_supabase=False,
        )
        self.assertFalse(result)

    def test_force_unlock_short_operator_returns_false(self):
        """force_unlock with short operator_id returns False."""
        result = RunManager.force_unlock(
            "some-run-id",
            operator_id="AB",
            reason="test",
            use_supabase=False,
        )
        self.assertFalse(result)

    def test_clamp_lease_static(self):
        """_clamp_lease works correctly."""
        self.assertEqual(RunManager._clamp_lease(0), MIN_LEASE_MINUTES)
        self.assertEqual(RunManager._clamp_lease(-5), MIN_LEASE_MINUTES)
        self.assertEqual(RunManager._clamp_lease(10), 10)
        self.assertEqual(RunManager._clamp_lease(999), MAX_LEASE_MINUTES)


class TestHeartbeatManager(unittest.TestCase):
    """HeartbeatManager panic protocol tests."""

    def _make_running_rm(self) -> RunManager:
        rm = RunManager("hb-run-1", use_supabase=False, worker_id="RayMac-01")
        rm.start()
        rm.claim()
        return rm

    def test_check_or_raise_when_healthy(self):
        """check_or_raise does nothing when lock is held."""
        rm = self._make_running_rm()
        hb = HeartbeatManager(rm, interval_seconds=9999)
        # Don't start thread — just test check_or_raise
        hb.check_or_raise()  # should not raise

    def test_check_or_raise_when_lost(self):
        """check_or_raise raises LostLock after lock loss."""
        rm = self._make_running_rm()
        hb = HeartbeatManager(rm, interval_seconds=9999)
        # Simulate lock loss
        hb._lost_event.set()
        hb._panic_reason = "test: lock stolen"
        with self.assertRaises(LostLock) as ctx:
            hb.check_or_raise()
        self.assertIn("lock stolen", str(ctx.exception))

    def test_lost_lock_property(self):
        """lost_lock property reflects internal state."""
        rm = self._make_running_rm()
        hb = HeartbeatManager(rm, interval_seconds=9999)
        self.assertFalse(hb.lost_lock)
        hb._lost_event.set()
        self.assertTrue(hb.lost_lock)

    def test_heartbeat_success(self):
        """Successful heartbeat returns True in _heartbeat_with_retries."""
        rm = self._make_running_rm()
        hb = HeartbeatManager(rm, interval_seconds=9999)
        # In local mode, heartbeat() returns True (has a token)
        result = hb._heartbeat_with_retries()
        self.assertTrue(result)

    def test_heartbeat_explicit_false_no_retry(self):
        """Explicit False from heartbeat → immediate PANIC, no retry."""
        rm = self._make_running_rm()
        hb = HeartbeatManager(rm, interval_seconds=9999)
        # Mock heartbeat to return False (lock stolen)
        call_count = 0
        original_hb = rm.heartbeat
        def mock_heartbeat(**kwargs):
            nonlocal call_count
            call_count += 1
            return False
        rm.heartbeat = mock_heartbeat
        result = hb._heartbeat_with_retries()
        self.assertFalse(result)
        self.assertEqual(call_count, 1)  # no retry on explicit False
        self.assertEqual(hb._panic_type, "panic_lost_lock")
        rm.heartbeat = original_hb

    def test_heartbeat_network_failure_retries(self):
        """Network failure retries 3 times then PANICs."""
        rm = self._make_running_rm()
        hb = HeartbeatManager(rm, interval_seconds=9999, max_retries=3)
        call_count = 0
        original_hb = rm.heartbeat
        def mock_heartbeat(**kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("network down")
        rm.heartbeat = mock_heartbeat
        result = hb._heartbeat_with_retries()
        self.assertFalse(result)
        self.assertEqual(call_count, 3)  # retried 3 times
        self.assertEqual(hb._panic_type, "panic_heartbeat_uncertain")
        rm.heartbeat = original_hb

    def test_enter_panic_logs_event(self):
        """_enter_panic logs a forensic event."""
        rm = self._make_running_rm()
        hb = HeartbeatManager(rm, interval_seconds=9999)
        hb._panic_type = "panic_lost_lock"
        hb._panic_reason = "test panic"
        hb._enter_panic()
        event_types = [e["event_type"] for e in rm.get_events()]
        self.assertIn("panic_lost_lock", event_types)

    def test_enter_panic_calls_on_panic_hook(self):
        """on_panic callback is called with run_id and reason."""
        rm = self._make_running_rm()
        hook_calls = []
        def on_panic(run_id, reason):
            hook_calls.append((run_id, reason))
        hb = HeartbeatManager(rm, interval_seconds=9999, on_panic=on_panic)
        hb._panic_type = "panic_lost_lock"
        hb._panic_reason = "test hook"
        hb._enter_panic()
        self.assertEqual(len(hook_calls), 1)
        self.assertEqual(hook_calls[0][0], "hb-run-1")
        self.assertIn("test hook", hook_calls[0][1])

    def test_start_heartbeat_integration(self):
        """RunManager.start_heartbeat returns a HeartbeatManager."""
        rm = self._make_running_rm()
        hb = rm.start_heartbeat(interval_seconds=9999)
        self.assertIsInstance(hb, HeartbeatManager)
        self.assertFalse(hb.lost_lock)
        rm.stop_heartbeat()

    def test_stop_heartbeat_integration(self):
        """RunManager.stop_heartbeat stops the thread."""
        rm = self._make_running_rm()
        hb = rm.start_heartbeat(interval_seconds=9999)
        rm.stop_heartbeat()
        self.assertIsNone(rm._heartbeat_manager)

    def test_complete_stops_heartbeat(self):
        """complete() auto-stops the heartbeat thread."""
        rm = self._make_running_rm()
        hb = rm.start_heartbeat(interval_seconds=9999)
        rm.complete()
        self.assertIsNone(rm._heartbeat_manager)

    def test_panic_distinct_types(self):
        """Lost lock and network uncertainty produce different event types."""
        rm1 = RunManager("hb-panic-1", use_supabase=False, worker_id="Worker-A")
        rm1.start(); rm1.claim()
        hb1 = HeartbeatManager(rm1, interval_seconds=9999)
        hb1._panic_type = "panic_lost_lock"
        hb1._panic_reason = "lock stolen"
        hb1._enter_panic()

        rm2 = RunManager("hb-panic-2", use_supabase=False, worker_id="Worker-B")
        rm2.start(); rm2.claim()
        hb2 = HeartbeatManager(rm2, interval_seconds=9999)
        hb2._panic_type = "panic_heartbeat_uncertain"
        hb2._panic_reason = "network failure"
        hb2._enter_panic()

        types1 = [e["event_type"] for e in rm1.get_events()]
        types2 = [e["event_type"] for e in rm2.get_events()]
        self.assertIn("panic_lost_lock", types1)
        self.assertNotIn("panic_heartbeat_uncertain", types1)
        self.assertIn("panic_heartbeat_uncertain", types2)
        self.assertNotIn("panic_lost_lock", types2)


# =========================================================================
# Telegram Gate Tests
# =========================================================================

class TestTelegramCallbackParsing(unittest.TestCase):

    def test_valid_refetch(self):
        data = "refetch:run-123:nonce-abc:action-xyz"
        parsed = parse_callback_data(data)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["action"], "refetch")
        self.assertEqual(parsed["run_id"], "run-123")
        self.assertEqual(parsed["nonce"], "nonce-abc")
        self.assertEqual(parsed["action_id"], "action-xyz")

    def test_valid_ignore(self):
        parsed = parse_callback_data("ignore:r1:n1:a1")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["action"], "ignore")

    def test_valid_abort(self):
        parsed = parse_callback_data("abort:r1:n1:a1")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["action"], "abort")

    def test_invalid_action(self):
        parsed = parse_callback_data("delete:r1:n1:a1")
        self.assertIsNone(parsed)

    def test_wrong_format(self):
        self.assertIsNone(parse_callback_data("refetch:only-two"))
        self.assertIsNone(parse_callback_data(""))
        self.assertIsNone(parse_callback_data("a:b:c:d:e"))


class TestTelegramGateHandler(unittest.TestCase):
    """Idempotent handler tests."""

    def _make_gated_rm(self) -> tuple:
        rm = RunManager("run-123", use_supabase=False)
        rm.start()
        rm._state.status = "waiting_approval"
        rm._state.approval_nonce = "nonce-abc"
        return rm

    def test_ignore_handler(self):
        rm = self._make_gated_rm()
        result = handle_gate_callback(
            "ignore:run-123:nonce-abc:action-001",
            rm,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "ignore")
        self.assertEqual(rm.status, "in_progress")

    def test_abort_handler(self):
        rm = self._make_gated_rm()
        result = handle_gate_callback(
            "abort:run-123:nonce-abc:action-002",
            rm,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "abort")
        self.assertEqual(rm.status, "aborted")

    def test_stale_nonce_rejected(self):
        rm = self._make_gated_rm()
        result = handle_gate_callback(
            "ignore:run-123:wrong-nonce:action-003",
            rm,
        )
        self.assertFalse(result["ok"])
        self.assertIn("CAS failed", result["message"])

    def test_wrong_run_id_rejected(self):
        rm = self._make_gated_rm()
        result = handle_gate_callback(
            "ignore:wrong-run:nonce-abc:action-004",
            rm,
        )
        self.assertFalse(result["ok"])
        self.assertIn("mismatch", result["message"])

    def test_refetch_without_fn(self):
        rm = self._make_gated_rm()
        result = handle_gate_callback(
            "refetch:run-123:nonce-abc:action-005",
            rm,
        )
        self.assertFalse(result["ok"])
        self.assertIn("No refetch_fn", result["message"])


# =========================================================================
# Context Builder Tests
# =========================================================================

class TestContextBuilderValidation(unittest.TestCase):

    def test_alias_collision_detected(self):
        index = {
            "note_a": {"aliases": ["earbuds", "wireless"]},
            "note_b": {"aliases": ["earbuds", "bluetooth"]},
        }
        errors = _validate_no_alias_collisions(index)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("earbuds" in e for e in errors))

    def test_no_collision_clean(self):
        index = {
            "note_a": {"aliases": ["earbuds"]},
            "note_b": {"aliases": ["headphones"]},
        }
        errors = _validate_no_alias_collisions(index)
        self.assertEqual(len(errors), 0)


class TestContextBuilderSelection(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create vault index
        self.index = {
            "sop_research": {
                "path": "sops/research.md",
                "type": "sop",
                "priority": "red",
                "authority_score": 10.0,
                "version": 3,
                "last_verified": datetime.now(timezone.utc).isoformat(),
                "content_hash": "abc123",
                "token_estimate": 500,
                "aliases": [],
            },
            "skill_pricing": {
                "path": "skills/pricing.md",
                "type": "skill",
                "priority": "yellow",
                "authority_score": 8.0,
                "version": 2,
                "token_estimate": 300,
                "aliases": ["price_check"],
            },
            "lesson_trust": {
                "path": "lessons/trust_signals.md",
                "type": "lesson",
                "priority": "green",
                "authority_score": 5.0,
                "version": 1,
                "token_estimate": 200,
                "aliases": [],
            },
        }
        self.index_path = Path(self.tmpdir) / "vault_notes.json"
        self.index_path.write_text(json.dumps(self.index))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_selects_by_priority_order(self):
        pack = build_context_pack(
            "research",
            vault_index_path=self.index_path,
            canonicals_path=Path(self.tmpdir) / "nonexistent.yml",
            max_notes=3,
            use_supabase=False,
        )
        self.assertFalse(pack.blocked)
        self.assertEqual(len(pack.notes), 3)
        # Red priority should be first
        self.assertEqual(pack.notes[0]["priority"], "red")

    def test_respects_max_notes_budget(self):
        pack = build_context_pack(
            "research",
            vault_index_path=self.index_path,
            canonicals_path=Path(self.tmpdir) / "nonexistent.yml",
            max_notes=2,
            use_supabase=False,
        )
        self.assertEqual(len(pack.notes), 2)

    def test_blocked_on_alias_collision(self):
        # Add collision
        self.index["note_extra"] = {
            "path": "extra.md",
            "aliases": ["sop_research"],  # collides with note ID
        }
        self.index_path.write_text(json.dumps(self.index))

        pack = build_context_pack(
            "research",
            vault_index_path=self.index_path,
            canonicals_path=Path(self.tmpdir) / "nonexistent.yml",
            use_supabase=False,
        )
        self.assertTrue(pack.blocked)
        self.assertIn("collision", pack.block_reason.lower())

    def test_empty_index_returns_empty_pack(self):
        empty_path = Path(self.tmpdir) / "empty.json"
        empty_path.write_text("{}")

        pack = build_context_pack(
            "research",
            vault_index_path=empty_path,
            use_supabase=False,
        )
        self.assertFalse(pack.blocked)
        self.assertEqual(len(pack.notes), 0)

    def test_snapshot_serializable(self):
        pack = build_context_pack(
            "research",
            vault_index_path=self.index_path,
            canonicals_path=Path(self.tmpdir) / "nonexistent.yml",
            use_supabase=False,
        )
        snapshot = pack.to_snapshot()
        json_str = json.dumps(snapshot)
        self.assertIn("task_type", json_str)
        self.assertIn("notes", json_str)


class TestSimpleYAMLParser(unittest.TestCase):

    def test_simple_format(self):
        yaml = "research: sop_research\nscript: sop_script\n"
        result = _parse_simple_yaml(yaml)
        self.assertEqual(result["research"], "sop_research")
        self.assertEqual(result["script"], "sop_script")

    def test_nested_format(self):
        yaml = """research:
  id: sop_research
  min_confidence: high
  variant: v2
"""
        result = _parse_simple_yaml(yaml)
        self.assertIsInstance(result["research"], dict)
        self.assertEqual(result["research"]["id"], "sop_research")
        self.assertEqual(result["research"]["min_confidence"], "high")

    def test_comments_ignored(self):
        yaml = "# This is a comment\nresearch: sop_research\n"
        result = _parse_simple_yaml(yaml)
        self.assertEqual(result["research"], "sop_research")


# =========================================================================
# Integration: CB → RunManager → TelegramGate
# =========================================================================

class TestFullGateFlow(unittest.TestCase):
    """End-to-end: evidence weak → gate → Telegram callback → resume."""

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def test_gate_ignore_resume_flow(self):
        """Weak evidence → gate → user ignores → run resumes."""
        rm = RunManager("flow-run-1", use_supabase=False)
        rm.start()

        # 1. Weak evidence triggers gate
        evidence = [
            {"claim_type": "price", "confidence": 0.3, "fetched_at": self._now_iso(), "trust_tier": 2},
        ]
        result = rm.evaluate_and_gate(evidence)
        self.assertTrue(result.should_gate)
        self.assertEqual(rm.status, "waiting_approval")
        nonce = rm._state.approval_nonce

        # 2. User presses "Ignore" via Telegram
        action_id = "action-flow-001"
        callback = f"ignore:{rm.run_id}:{nonce}:{action_id}"
        gate_result = handle_gate_callback(callback, rm)

        self.assertTrue(gate_result["ok"])
        self.assertEqual(rm.status, "in_progress")

        # 3. Run can continue
        self.assertTrue(rm.check_status())

    def test_gate_abort_flow(self):
        """Weak evidence → gate → user aborts."""
        rm = RunManager("flow-run-2", use_supabase=False)
        rm.start()

        evidence = [
            {"claim_type": "price", "confidence": 0.3, "fetched_at": self._now_iso(), "trust_tier": 2},
        ]
        rm.evaluate_and_gate(evidence)
        nonce = rm._state.approval_nonce

        callback = f"abort:{rm.run_id}:{nonce}:action-flow-002"
        gate_result = handle_gate_callback(callback, rm)

        self.assertTrue(gate_result["ok"])
        self.assertEqual(rm.status, "aborted")
        self.assertFalse(rm.check_status())


# =========================================================================
# Worker Ops Tests (safe_stop, checkpoint, spool)
# =========================================================================

class TestWorkerOpsCheckpoint(unittest.TestCase):
    """Checkpoint load/save with atomic writes."""

    def setUp(self):
        import shutil
        self._orig_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix="test_ckpt_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        # Restore original dir if patched
        if self._orig_dir is not None:
            from lib import worker_ops
            worker_ops.CHECKPOINT_DIR = self._orig_dir

    def _patch_dir(self):
        from lib import worker_ops
        self._orig_dir = worker_ops.CHECKPOINT_DIR
        worker_ops.CHECKPOINT_DIR = self.tmpdir

    def test_load_missing_returns_default(self):
        """load_checkpoint returns default dict if file doesn't exist."""
        self._patch_dir()
        from lib.worker_ops import load_checkpoint
        ckpt = load_checkpoint("nonexistent-run")
        self.assertEqual(ckpt["run_id"], "nonexistent-run")
        self.assertEqual(ckpt["stage"], "init")
        self.assertEqual(ckpt["completed_steps"], [])
        self.assertIn("version", ckpt)

    def test_save_and_load_roundtrip(self):
        """save_checkpoint then load_checkpoint preserves data."""
        self._patch_dir()
        from lib.worker_ops import save_checkpoint, load_checkpoint
        save_checkpoint(
            "rt-run-1", "collect_evidence",
            data={"products": 5},
            artifacts={"csv": "/tmp/ev.csv"},
            lock_token="tok-123",
        )
        ckpt = load_checkpoint("rt-run-1")
        self.assertEqual(ckpt["stage"], "collect_evidence")
        self.assertIn("collect_evidence", ckpt["completed_steps"])
        self.assertEqual(ckpt["data"]["products"], 5)
        self.assertEqual(ckpt["artifacts"]["csv"], "/tmp/ev.csv")
        self.assertEqual(ckpt["lock_token"], "tok-123")
        self.assertIn("last_update_utc", ckpt)

    def test_save_merges_data(self):
        """Multiple saves merge data and artifacts."""
        self._patch_dir()
        from lib.worker_ops import save_checkpoint, load_checkpoint
        save_checkpoint("merge-1", "step1", data={"a": 1})
        save_checkpoint("merge-1", "step2", data={"b": 2})
        ckpt = load_checkpoint("merge-1")
        self.assertEqual(ckpt["data"]["a"], 1)
        self.assertEqual(ckpt["data"]["b"], 2)
        self.assertIn("step1", ckpt["completed_steps"])
        self.assertIn("step2", ckpt["completed_steps"])

    def test_clear_checkpoint(self):
        """clear_checkpoint removes the file."""
        self._patch_dir()
        from lib.worker_ops import save_checkpoint, clear_checkpoint, load_checkpoint
        save_checkpoint("clear-1", "done")
        self.assertTrue(clear_checkpoint("clear-1"))
        ckpt = load_checkpoint("clear-1")
        self.assertEqual(ckpt["stage"], "init")  # back to default

    def test_save_none_data_safe(self):
        """save_checkpoint with data=None doesn't crash."""
        self._patch_dir()
        from lib.worker_ops import save_checkpoint, load_checkpoint
        save_checkpoint("none-1", "step1", data=None, artifacts=None)
        ckpt = load_checkpoint("none-1")
        self.assertEqual(ckpt["stage"], "step1")


class TestWorkerOpsSpool(unittest.TestCase):
    """Event spool write and replay."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_spool_")
        self._orig_dir = None

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        if self._orig_dir is not None:
            from lib import worker_ops
            worker_ops.SPOOL_DIR = self._orig_dir

    def _patch_dir(self):
        from lib import worker_ops
        self._orig_dir = worker_ops.SPOOL_DIR
        worker_ops.SPOOL_DIR = self.tmpdir

    def test_spool_event_writes_file(self):
        """spool_event creates a JSON file."""
        self._patch_dir()
        from lib.worker_ops import spool_event
        path = spool_event("spool-run-1", "panic_stop", {"reason": "test"})
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data["run_id"], "spool-run-1")
        self.assertEqual(data["event_type"], "panic_stop")
        self.assertEqual(data["payload"]["reason"], "test")

    def test_replay_with_send_fn(self):
        """replay_spool calls send_fn and removes files on success."""
        self._patch_dir()
        from lib.worker_ops import spool_event, replay_spool
        spool_event("replay-1", "test_event", {"k": "v"})

        sent_records = []
        def send_fn(record):
            sent_records.append(record)
            return True

        result = replay_spool(send_fn=send_fn)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(sent_records), 1)
        # File should be removed
        self.assertEqual(len(os.listdir(self.tmpdir)), 0)

    def test_replay_keeps_failed(self):
        """replay_spool keeps files when send_fn returns False."""
        self._patch_dir()
        from lib.worker_ops import spool_event, replay_spool
        spool_event("replay-2", "test_event", {"k": "v"})

        result = replay_spool(send_fn=lambda r: False)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 1)
        # File should still exist
        files = [f for f in os.listdir(self.tmpdir) if f.endswith(".json")]
        self.assertEqual(len(files), 1)

    def test_replay_empty_dir(self):
        """replay_spool on empty dir returns zeros."""
        self._patch_dir()
        from lib.worker_ops import replay_spool
        result = replay_spool()
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 0)


class TestWorkerOpsSafeStop(unittest.TestCase):
    """Safe stop idempotency and cleanup."""

    def setUp(self):
        from lib.worker_ops import reset_panic_flag
        reset_panic_flag()
        self._orig_spool = None

    def tearDown(self):
        from lib.worker_ops import reset_panic_flag
        reset_panic_flag()
        if self._orig_spool is not None:
            from lib import worker_ops
            worker_ops.SPOOL_DIR = self._orig_spool

    def _patch_spool(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_ss_")
        from lib import worker_ops
        self._orig_spool = worker_ops.SPOOL_DIR
        worker_ops.SPOOL_DIR = self.tmpdir

    def test_safe_stop_sets_panic_flag(self):
        """safe_stop sets the global panic flag."""
        self._patch_spool()
        from lib.worker_ops import safe_stop, is_panic_active
        self.assertFalse(is_panic_active())
        safe_stop("ss-run-1", "test")
        self.assertTrue(is_panic_active())

    def test_safe_stop_idempotent(self):
        """Calling safe_stop twice is a no-op on second call."""
        self._patch_spool()
        from lib.worker_ops import safe_stop, is_panic_active
        hook_calls = []
        safe_stop("ss-run-2", "first", mark_panic_fn=lambda r, reason: hook_calls.append(1))
        safe_stop("ss-run-2", "second", mark_panic_fn=lambda r, reason: hook_calls.append(2))
        self.assertEqual(len(hook_calls), 1)  # only first call runs

    def test_safe_stop_sets_stop_signal(self):
        """safe_stop calls stop_signal.set()."""
        self._patch_spool()
        import threading
        from lib.worker_ops import safe_stop
        sig = threading.Event()
        safe_stop("ss-run-3", "test", stop_signal=sig)
        self.assertTrue(sig.is_set())

    def test_safe_stop_spools_event(self):
        """safe_stop writes a spool file."""
        self._patch_spool()
        from lib.worker_ops import safe_stop
        safe_stop("ss-run-4", "test_spool")
        files = [f for f in os.listdir(self.tmpdir) if f.endswith(".json")]
        self.assertGreaterEqual(len(files), 1)

    def test_reset_panic_flag(self):
        """reset_panic_flag clears the flag for restart."""
        self._patch_spool()
        from lib.worker_ops import safe_stop, is_panic_active, reset_panic_flag
        safe_stop("ss-run-5", "test")
        self.assertTrue(is_panic_active())
        reset_panic_flag()
        self.assertFalse(is_panic_active())


class TestHeartbeatLatency(unittest.TestCase):
    """Heartbeat latency measurement and piggybacking."""

    def _make_rm(self, run_id="lat-001", worker_id="LatencyWorker"):
        from lib.run_manager import RunManager
        rm = RunManager(run_id, use_supabase=False, worker_id=worker_id)
        rm._state.status = "in_progress"
        rm._state.lock_token = "tok-lat-001"
        return rm

    def test_heartbeat_records_latency_ms(self):
        """heartbeat() measures round-trip time and stores _last_heartbeat_latency_ms."""
        rm = self._make_rm()
        ok = rm.heartbeat()
        self.assertTrue(ok)
        # In local mode (no supabase), latency is not measured via RPC
        # but the attribute should not exist without supabase
        self.assertFalse(hasattr(rm, "_last_heartbeat_latency_ms"))

    def test_heartbeat_latency_attribute_set_on_supabase_mode(self):
        """In supabase mode, heartbeat sets _last_heartbeat_latency_ms on success."""
        from lib.run_manager import RunManager
        rm = RunManager("lat-002", use_supabase=True, worker_id="LatWorker")
        rm._state.status = "in_progress"
        rm._state.lock_token = "tok-lat-002"

        # Mock the RPC to succeed
        with patch("lib.run_manager.RunManager._supabase_heartbeat", return_value=True):
            ok = rm.heartbeat()
        self.assertTrue(ok)
        # Latency should be measured (>= 0ms)
        self.assertTrue(hasattr(rm, "_last_heartbeat_latency_ms"))
        self.assertGreaterEqual(rm._last_heartbeat_latency_ms, 0)

    def test_heartbeat_latency_logged_on_lock_lost(self):
        """When heartbeat fails, latency_ms is included in the lock_lost event."""
        from lib.run_manager import RunManager
        rm = RunManager("lat-003", use_supabase=True, worker_id="LatWorker")
        rm._state.status = "in_progress"
        rm._state.lock_token = "tok-lat-003"

        with patch("lib.run_manager.RunManager._supabase_heartbeat", return_value=False):
            ok = rm.heartbeat()
        self.assertFalse(ok)
        # Check that a lock_lost event was logged with latency_ms
        lock_lost_events = [e for e in rm._events if e["event_type"] == "lock_lost"]
        self.assertEqual(len(lock_lost_events), 1)
        self.assertIn("latency_ms", lock_lost_events[0]["payload"])


class TestForceUnlockGuards(unittest.TestCase):
    """Force unlock: status guard, run-not-found, prev snapshot."""

    def test_force_unlock_short_operator(self):
        """force_unlock rejects operator_id < 3 chars."""
        from lib.run_manager import RunManager
        ok = RunManager.force_unlock(
            "run-xyz", operator_id="ab", reason="test", use_supabase=False,
        )
        self.assertFalse(ok)

    def test_force_unlock_requires_supabase(self):
        """force_unlock in local mode returns False with message."""
        from lib.run_manager import RunManager
        ok = RunManager.force_unlock(
            "run-xyz", operator_id="operator-1", reason="test", use_supabase=False,
        )
        self.assertFalse(ok)

    def test_rpc_release_run_name_in_release(self):
        """_supabase_release calls rpc_release_run (not cas_release_run)."""
        from lib.run_manager import RunManager
        rm = RunManager("rel-001", use_supabase=True, worker_id="RelWorker")
        rm._state.lock_token = "tok-rel-001"

        with patch("tools.lib.supabase_client.rpc", create=True) as mock_rpc:
            mock_rpc.return_value = True
            rm._supabase_release()
            mock_rpc.assert_called_once()
            call_args = mock_rpc.call_args
            self.assertEqual(call_args[0][0], "rpc_release_run")

    def test_heartbeat_passes_latency_to_rpc(self):
        """_supabase_heartbeat includes p_latency_ms when available."""
        from lib.run_manager import RunManager
        rm = RunManager("hblat-001", use_supabase=True, worker_id="HBLatWorker")
        rm._state.status = "in_progress"
        rm._state.lock_token = "tok-hblat-001"
        rm._last_heartbeat_latency_ms = 42

        with patch("tools.lib.supabase_client.rpc", create=True) as mock_rpc:
            mock_rpc.return_value = True
            rm._supabase_heartbeat(10)
            call_args = mock_rpc.call_args
            params = call_args[0][1]
            self.assertEqual(params.get("p_latency_ms"), 42)

    def test_heartbeat_no_latency_on_first_call(self):
        """First heartbeat doesn't send p_latency_ms (not yet measured)."""
        from lib.run_manager import RunManager
        rm = RunManager("hblat-002", use_supabase=True, worker_id="HBLatWorker")
        rm._state.status = "in_progress"
        rm._state.lock_token = "tok-hblat-002"

        with patch("tools.lib.supabase_client.rpc", create=True) as mock_rpc:
            mock_rpc.return_value = True
            rm._supabase_heartbeat(10)
            call_args = mock_rpc.call_args
            params = call_args[0][1]
            self.assertNotIn("p_latency_ms", params)


class TestPanicTaxonomy(unittest.TestCase):
    """Panic taxonomy: controlled string constants."""

    VALID_PANICS = {
        "panic_lost_lock",
        "panic_heartbeat_uncertain",
        "panic_browser_frozen",
        "panic_integrity_failure",
    }

    def test_heartbeat_panic_types_are_valid(self):
        """HeartbeatManager only emits valid panic type strings."""
        from lib.run_manager import HeartbeatManager, RunManager
        rm = RunManager("tax-001", use_supabase=False, worker_id="TaxWorker")
        rm._state.status = "in_progress"
        rm._state.lock_token = "tok-tax-001"
        hb = HeartbeatManager(rm, interval_seconds=1, jitter_seconds=0)
        # Simulate lost lock panic
        hb._panic_type = "panic_lost_lock"
        self.assertIn(hb.panic_type, self.VALID_PANICS)
        # Simulate uncertain panic
        hb._panic_type = "panic_heartbeat_uncertain"
        self.assertIn(hb.panic_type, self.VALID_PANICS)

    def test_worker_ops_safe_stop_spools_panic_stop(self):
        """safe_stop spools event_type='panic_stop' which maps to taxonomy."""
        tmpdir = tempfile.mkdtemp(prefix="test_tax_")
        from lib import worker_ops
        orig = worker_ops.SPOOL_DIR
        worker_ops.SPOOL_DIR = tmpdir
        worker_ops.reset_panic_flag()
        try:
            worker_ops.safe_stop("tax-run-1", "panic_lost_lock")
            files = [f for f in os.listdir(tmpdir) if f.endswith(".json")]
            self.assertGreaterEqual(len(files), 1)
            with open(os.path.join(tmpdir, files[0])) as f:
                data = json.load(f)
            self.assertEqual(data["event_type"], "panic_stop")
            self.assertEqual(data["payload"]["reason"], "panic_lost_lock")
        finally:
            worker_ops.SPOOL_DIR = orig
            worker_ops.reset_panic_flag()


class TestClaimNextRecoveryLocal(unittest.TestCase):
    """Local tests for claim_next recovery and exclusivity logic."""

    def test_claim_next_local_returns_none(self):
        """claim_next in local mode (no supabase) returns None."""
        from lib.run_manager import RunManager
        result = RunManager.claim_next(
            worker_id="LocalWorker",
            use_supabase=False,
        )
        self.assertIsNone(result)

    def test_claim_next_short_worker_returns_none(self):
        """claim_next rejects worker_id < 3 chars."""
        from lib.run_manager import RunManager
        result = RunManager.claim_next(worker_id="ab", use_supabase=False)
        self.assertIsNone(result)

    def test_claim_next_whitespace_worker_returns_none(self):
        """claim_next rejects whitespace-only worker_id."""
        from lib.run_manager import RunManager
        result = RunManager.claim_next(worker_id="  ", use_supabase=False)
        self.assertIsNone(result)

    def test_claim_lease_clamped(self):
        """claim_next clamps lease to [1,30]."""
        from lib.run_manager import RunManager
        # This calls the static _clamp_lease or the internal clamp.
        # We test via claim() with local mode.
        rm = RunManager("clamp-test", use_supabase=False, worker_id="ClampWorker")
        rm._state.status = "in_progress"
        # Claiming with absurd lease should clamp
        ok = rm.claim(lease_minutes=999)
        self.assertTrue(ok)
        # Verify expiry is ~30min (not 999min)
        from datetime import datetime, timezone
        exp = datetime.fromisoformat(rm._state.lock_expires_at)
        now = datetime.now(timezone.utc)
        delta_min = (exp - now).total_seconds() / 60
        self.assertLessEqual(delta_min, 31)
        self.assertGreaterEqual(delta_min, 28)

    def test_heartbeat_rejects_empty_token(self):
        """heartbeat() returns False when lock_token is empty."""
        from lib.run_manager import RunManager
        rm = RunManager("hb-empty", use_supabase=False, worker_id="HBWorker")
        rm._state.status = "in_progress"
        rm._state.lock_token = ""
        self.assertFalse(rm.heartbeat())

    def test_heartbeat_succeeds_with_valid_token_local(self):
        """heartbeat() succeeds in local mode with valid token."""
        from lib.run_manager import RunManager
        rm = RunManager("hb-valid", use_supabase=False, worker_id="HBWorker")
        rm._state.status = "in_progress"
        rm._state.lock_token = "tok-valid"
        self.assertTrue(rm.heartbeat())

    def test_lost_lock_exception_on_panic(self):
        """HeartbeatManager raises LostLock after panic."""
        from lib.run_manager import HeartbeatManager, RunManager, LostLock
        rm = RunManager("ll-test", use_supabase=False, worker_id="LLWorker")
        rm._state.status = "in_progress"
        rm._state.lock_token = "tok-ll"
        hb = HeartbeatManager(rm, interval_seconds=999)
        # Simulate panic
        hb._lost_event.set()
        hb._panic_reason = "test panic"
        with self.assertRaises(LostLock) as ctx:
            hb.check_or_raise()
        self.assertIn("test panic", str(ctx.exception))

    def test_claim_next_supabase_mock_returns_rm(self):
        """claim_next with mocked RPC returns a RunManager."""
        from lib.run_manager import RunManager
        fake_id = "12345678-1234-1234-1234-123456789abc"
        with patch.object(RunManager, "_supabase_claim_next", return_value=fake_id):
            rm = RunManager.claim_next(
                worker_id="MockWorker",
                use_supabase=True,
            )
        self.assertIsNotNone(rm)
        self.assertEqual(rm.run_id, fake_id)
        self.assertEqual(rm._state.worker_id, "MockWorker")
        self.assertTrue(rm._state.lock_token)  # should have a token


# ==========================================================================
# Config module tests
# ==========================================================================

class TestConfig(unittest.TestCase):
    """Tests for tools/lib/config.py."""

    def test_format_dual_time(self):
        """format_dual_time produces UTC and BRT."""
        from lib.config import format_dual_time
        dt = datetime(2025, 6, 15, 18, 30, 0, tzinfo=timezone.utc)
        result = format_dual_time(dt)
        self.assertIn("18:30 UTC", result)
        self.assertIn("15:30 BRT", result)
        self.assertIn("2025-06-15", result)

    def test_panic_reasons_taxonomy(self):
        """All PANIC_REASONS have required fields."""
        from lib.config import PANIC_REASONS
        required_keys = {"label", "emoji", "severity", "action"}
        for key, info in PANIC_REASONS.items():
            self.assertTrue(key.startswith("panic_"), f"{key} must start with panic_")
            for rk in required_keys:
                self.assertIn(rk, info, f"{key} missing {rk}")
            self.assertIn(info["severity"], ("WARN", "CRITICAL", "UNKNOWN"),
                          f"{key} has invalid severity: {info['severity']}")

    def test_panic_template_contains_severity(self):
        """panic_template includes severity label."""
        from lib.config import panic_template
        dt = datetime(2025, 6, 15, 18, 0, 0, tzinfo=timezone.utc)
        text = panic_template("panic_lost_lock", "abc12345-6789-0000-0000-000000000000",
                              dt, latency_ms=150, retry_count=2)
        self.assertIn("[CRITICAL]", text)
        self.assertIn("Lock Lost", text)
        self.assertIn("150ms", text)
        self.assertIn("Retries: 2", text)

    def test_panic_template_unknown_reason(self):
        """panic_template handles unknown reason keys gracefully."""
        from lib.config import panic_template
        dt = datetime(2025, 6, 15, 18, 0, 0, tzinfo=timezone.utc)
        text = panic_template("panic_alien_invasion", "abc12345-run", dt)
        self.assertIn("panic_alien_invasion", text)

    def test_load_worker_config_defaults(self):
        """load_worker_config returns valid defaults."""
        from lib.config import load_worker_config
        cfg, secrets = load_worker_config(worker_id="TestMac")
        self.assertEqual(cfg.worker_id, "TestMac")
        self.assertEqual(cfg.lease_minutes, 15)
        self.assertEqual(cfg.heartbeat_interval_sec, 120)
        self.assertTrue(cfg.spool_dir)
        self.assertTrue(cfg.checkpoint_dir)
        # Thresholds
        self.assertEqual(cfg.thresholds.heartbeat_latency_crit_ms, 8000)
        self.assertEqual(cfg.thresholds.stale_worker_minutes, 30)
        self.assertEqual(cfg.thresholds.spool_max_retries, 3)

    def test_load_worker_config_from_env(self):
        """load_worker_config reads env vars."""
        from lib.config import load_worker_config
        with patch.dict(os.environ, {"LEASE_MINUTES": "20", "WORKER_ID": "EnvWorker"}):
            cfg, _ = load_worker_config()
        self.assertEqual(cfg.lease_minutes, 20)
        self.assertEqual(cfg.worker_id, "EnvWorker")

    def test_health_thresholds_frozen(self):
        """HealthThresholds is immutable."""
        from lib.config import HealthThresholds
        t = HealthThresholds()
        with self.assertRaises(AttributeError):
            t.heartbeat_latency_warn_ms = 9999


# ==========================================================================
# Panic module tests
# ==========================================================================

class TestPanicManager(unittest.TestCase):
    """Tests for tools/lib/panic.py."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_panic_")
        from lib.config import WorkerConfig, SecretsConfig
        self.cfg = WorkerConfig(
            worker_id="TestWorker",
            spool_dir=self.tmpdir,
            rpc_timeout_sec=2,
        )
        self.secrets = SecretsConfig(
            supabase_url="",  # no DB for unit tests
            supabase_service_key="",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_report_panic_creates_spool_file(self):
        """report_panic creates an atomic spool file."""
        from lib.panic import PanicManager
        pm = PanicManager(self.cfg, self.secrets)
        spool_name = pm.report_panic(
            "panic_lost_lock", "run-123", "lock stolen",
        )
        self.assertIn("panic_lost_lock", spool_name)
        spool_path = Path(self.tmpdir) / spool_name
        self.assertTrue(spool_path.exists())

        # Verify content
        with open(spool_path) as f:
            data = json.load(f)
        self.assertEqual(data["run_id"], "run-123")
        self.assertEqual(data["reason_key"], "panic_lost_lock")
        self.assertEqual(data["worker_id"], "TestWorker")
        self.assertIn("event_id", data)
        self.assertIn("timestamp", data)

    def test_spool_filename_collision_free(self):
        """Two rapid panics produce different spool files."""
        from lib.panic import PanicManager
        pm = PanicManager(self.cfg, self.secrets)
        name1 = pm.report_panic("panic_lost_lock", "run-1", "err1")
        name2 = pm.report_panic("panic_lost_lock", "run-2", "err2")
        self.assertNotEqual(name1, name2)

    def test_error_msg_truncated(self):
        """Error message is truncated to max_worker_error_len."""
        from lib.panic import PanicManager
        self.cfg.max_worker_error_len = 50
        pm = PanicManager(self.cfg, self.secrets)
        spool_name = pm.report_panic(
            "panic_browser_frozen", "run-999", "A" * 1000,
        )
        spool_path = Path(self.tmpdir) / spool_name
        with open(spool_path) as f:
            data = json.load(f)
        self.assertEqual(len(data["error_msg"]), 50)

    def test_event_id_is_uuid(self):
        """event_id in spool file is a valid UUID."""
        import uuid
        from lib.panic import PanicManager
        pm = PanicManager(self.cfg, self.secrets)
        spool_name = pm.report_panic("panic_heartbeat_uncertain", "run-x", "net")
        spool_path = Path(self.tmpdir) / spool_name
        with open(spool_path) as f:
            data = json.load(f)
        # Should not raise
        uuid.UUID(data["event_id"])

    def test_atomic_write_json_no_corruption(self):
        """_atomic_write_json produces valid JSON even if called rapidly."""
        from lib.panic import _atomic_write_json
        p = Path(self.tmpdir) / "test.json"
        for i in range(10):
            _atomic_write_json(p, {"i": i, "data": "x" * 100})
        with open(p) as f:
            data = json.load(f)
        self.assertEqual(data["i"], 9)

    def test_no_db_call_without_url(self):
        """With empty supabase_url, DB update is skipped (no error)."""
        from lib.panic import PanicManager
        pm = PanicManager(self.cfg, self.secrets)
        # Should not raise even without DB
        spool = pm.report_panic("panic_lost_lock", "run-safe", "no db")
        self.assertTrue(spool)

    def test_no_telegram_without_token(self):
        """With empty telegram_bot_token, Telegram is skipped."""
        from lib.panic import PanicManager
        pm = PanicManager(self.cfg, self.secrets)
        # Should not raise
        spool = pm.report_panic("panic_lost_lock", "run-safe", "no tg")
        self.assertTrue(spool)


# ==========================================================================
# Doctor module tests
# ==========================================================================

class TestDoctor(unittest.TestCase):
    """Tests for tools/lib/doctor.py."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_doctor_spool_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_spool(self, name: str, data: dict) -> Path:
        p = Path(self.tmpdir) / name
        with open(p, "w") as f:
            json.dump(data, f)
        return p

    def test_replay_spool_empty_dir(self):
        """replay_spool on empty dir returns zeros."""
        from lib.doctor import replay_spool
        s, f, r = replay_spool(self.tmpdir, "http://fake", "key")
        self.assertEqual((s, f, r), (0, 0, 0))

    def test_replay_spool_corrupted_quarantine(self):
        """Corrupted JSON files are moved to bad/."""
        from lib.doctor import replay_spool
        # Write corrupt file
        bad_file = Path(self.tmpdir) / "corrupt.json"
        bad_file.write_text("{invalid json")
        s, f, r = replay_spool(self.tmpdir, "http://fake", "key")
        self.assertEqual(f, 1)
        self.assertTrue((Path(self.tmpdir) / "bad" / "corrupt.json").exists())

    def test_replay_spool_no_run_id_quarantine(self):
        """Files without run_id are moved to bad/."""
        from lib.doctor import replay_spool
        self._write_spool("no_runid.json", {"event_type": "test"})
        s, f, r = replay_spool(self.tmpdir, "http://fake", "key")
        self.assertEqual(f, 1)
        self.assertTrue((Path(self.tmpdir) / "bad" / "no_runid.json").exists())

    def test_replay_spool_retry_count_increment(self):
        """Failed replay increments _replay_retries in the file."""
        from lib.doctor import replay_spool
        self._write_spool("event.json", {
            "run_id": "r1", "event_id": "e1", "event_type": "panic",
        })
        with patch("lib.doctor._http_post", return_value=(500, "error")):
            s, f, r = replay_spool(self.tmpdir, "http://fake", "key")
        self.assertEqual(f, 1)
        # File should still exist with retry count
        with open(Path(self.tmpdir) / "event.json") as fh:
            data = json.load(fh)
        self.assertEqual(data["_replay_retries"], 1)

    def test_replay_spool_quarantine_after_max_retries(self):
        """After max_retries failures, file moves to quarantine/ with reason in name."""
        from lib.doctor import replay_spool
        self._write_spool("event.json", {
            "run_id": "r1", "event_id": "e1",
            "reason_key": "panic_lost_lock",
            "_replay_retries": 2,  # already failed twice
        })
        with patch("lib.doctor._http_post", return_value=(500, "error")):
            s, f, r = replay_spool(self.tmpdir, "http://fake", "key", max_retries=3)
        self.assertEqual(f, 1)
        # File is renamed with timestamp_reason_original pattern
        q_dir = Path(self.tmpdir) / "quarantine"
        self.assertTrue(q_dir.exists())
        q_files = list(q_dir.iterdir())
        self.assertEqual(len(q_files), 1)
        q_name = q_files[0].name
        self.assertIn("panic_lost_lock", q_name)
        self.assertIn("event.json", q_name)

    def test_health_check_stale_worker(self):
        """health_check detects stale workers."""
        from lib.doctor import health_check
        from lib.config import HealthThresholds

        old_hb = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        active_runs = [
            {
                "id": "aaaa-bbbb-cccc-dddd",
                "worker_state": "active",
                "worker_id": "Mac-Ray-01",
                "last_heartbeat_at": old_hb,
                "last_heartbeat_latency_ms": 200,
            }
        ]

        def mock_get(url, headers, timeout=15):
            if "waiting_approval" in url:
                return 200, []
            return 200, active_runs

        with patch("lib.doctor._http_get", side_effect=mock_get):
            results = health_check(
                "http://fake", "key",
                HealthThresholds(stale_worker_minutes=30),
            )
        self.assertEqual(results["counts"]["stale_workers"], 1)
        self.assertEqual(results["stale_workers"][0]["worker_id"], "Mac-Ray-01")

    def test_health_check_no_stale_fresh_worker(self):
        """health_check does NOT flag fresh workers as stale."""
        from lib.doctor import health_check
        from lib.config import HealthThresholds

        fresh_hb = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        active_runs = [
            {
                "id": "aaaa-bbbb-cccc-dddd",
                "worker_state": "active",
                "worker_id": "Mac-Ray-01",
                "last_heartbeat_at": fresh_hb,
                "last_heartbeat_latency_ms": 100,
            }
        ]

        def mock_get(url, headers, timeout=15):
            if "waiting_approval" in url:
                return 200, []
            return 200, active_runs

        with patch("lib.doctor._http_get", side_effect=mock_get):
            results = health_check(
                "http://fake", "key",
                HealthThresholds(stale_worker_minutes=30),
            )
        self.assertEqual(results["counts"]["stale_workers"], 0)

    def test_health_check_latency_thresholds(self):
        """health_check correctly classifies latency levels."""
        from lib.doctor import health_check
        from lib.config import HealthThresholds

        active_runs = [
            {"id": "run-low", "worker_state": "active", "worker_id": "w1",
             "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
             "last_heartbeat_latency_ms": 100},
            {"id": "run-warn", "worker_state": "active", "worker_id": "w2",
             "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
             "last_heartbeat_latency_ms": 4000},
            {"id": "run-crit", "worker_state": "active", "worker_id": "w3",
             "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
             "last_heartbeat_latency_ms": 9000},
        ]

        def mock_get(url, headers, timeout=15):
            if "waiting_approval" in url:
                return 200, []
            return 200, active_runs

        with patch("lib.doctor._http_get", side_effect=mock_get):
            results = health_check(
                "http://fake", "key",
                HealthThresholds(),
            )
        self.assertEqual(results["counts"]["lat_warn"], 1)
        self.assertEqual(results["counts"]["lat_crit"], 1)


# ==========================================================================
# PID file tests
# ==========================================================================

class TestPidFile(unittest.TestCase):
    """Tests for PID file management in worker.py."""

    def setUp(self):
        from tools.worker import _RUNTIME_DIR, _PID_FILE
        self._orig_runtime = _RUNTIME_DIR
        self._orig_pid = _PID_FILE
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test_pid_"))
        # Monkey-patch PID paths for testing
        import tools.worker as _w
        _w._RUNTIME_DIR = self.tmpdir
        _w._PID_FILE = self.tmpdir / "worker.pid"

    def tearDown(self):
        import shutil
        import tools.worker as _w
        _w._RUNTIME_DIR = self._orig_runtime
        _w._PID_FILE = self._orig_pid
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_and_read_pid(self):
        """write_pid creates file, read_pid returns current PID."""
        from tools.worker import write_pid, read_pid
        write_pid()
        pid = read_pid()
        self.assertEqual(pid, os.getpid())

    def test_remove_pid(self):
        """remove_pid deletes the PID file."""
        from tools.worker import write_pid, read_pid, remove_pid
        write_pid()
        remove_pid()
        self.assertIsNone(read_pid())

    def test_read_pid_no_file(self):
        """read_pid returns None when no file exists."""
        from tools.worker import read_pid
        self.assertIsNone(read_pid())


# ==========================================================================
# CLI arg parsing tests
# ==========================================================================

class TestCliParsing(unittest.TestCase):
    """Tests for rayvault_cli.py argument parsing."""

    def test_doctor_default_flags(self):
        """doctor with no flags does all (spool + health + contract)."""
        # Add repo root to path
        _repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(_repo_root))
        from rayvault_cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["doctor"])
        self.assertEqual(args.cmd, "doctor")
        # No specific flags = will do all
        self.assertFalse(getattr(args, "do_spool_flag", False))
        self.assertFalse(getattr(args, "do_health_flag", False))
        self.assertFalse(getattr(args, "do_contract_flag", False))

    def test_doctor_specific_flags(self):
        """doctor --health only sets health flag."""
        _repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(_repo_root))
        from rayvault_cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["doctor", "--health"])
        self.assertTrue(args.do_health_flag)
        self.assertFalse(args.do_spool_flag)

    def test_unlock_requires_run(self):
        """unlock without --run should fail."""
        _repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(_repo_root))
        from rayvault_cli import build_parser
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["unlock"])

    def test_stop_force_flag(self):
        """stop --force sets force=True."""
        _repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(_repo_root))
        from rayvault_cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["stop", "--force"])
        self.assertTrue(args.force)


# ==========================================================================
# Contract check tests
# ==========================================================================

class TestContractCheck(unittest.TestCase):
    """Tests for RPC contract verification."""

    def test_contract_all_pass(self):
        """check_rpc_contract with all 200 returns all passed."""
        from lib.doctor import check_rpc_contract

        def mock_post(url, data, headers, timeout=15):
            return 200, "null"

        with patch("lib.doctor._http_post", side_effect=mock_post):
            passed, failed = check_rpc_contract("http://fake", "key")
        self.assertEqual(len(passed), 4)
        self.assertEqual(len(failed), 0)

    def test_contract_400_is_pass(self):
        """400 (bad params) still means function exists = pass."""
        from lib.doctor import check_rpc_contract

        def mock_post(url, data, headers, timeout=15):
            return 400, '{"message":"invalid input"}'

        with patch("lib.doctor._http_post", side_effect=mock_post):
            passed, failed = check_rpc_contract("http://fake", "key")
        self.assertEqual(len(passed), 4)

    def test_contract_404_is_fail(self):
        """404 (function not found) = fail."""
        from lib.doctor import check_rpc_contract

        def mock_post(url, data, headers, timeout=15):
            if "rpc_claim_next_run" in url:
                return 404, "not found"
            return 200, "null"

        with patch("lib.doctor._http_post", side_effect=mock_post):
            passed, failed = check_rpc_contract("http://fake", "key")
        self.assertEqual(len(failed), 1)
        self.assertIn("rpc_claim_next_run", failed)
        self.assertEqual(len(passed), 3)

    def test_contract_403_is_fail(self):
        """403 (permission denied) = fail."""
        from lib.doctor import check_rpc_contract

        def mock_post(url, data, headers, timeout=15):
            return 403, "permission denied"

        with patch("lib.doctor._http_post", side_effect=mock_post):
            passed, failed = check_rpc_contract("http://fake", "key")
        self.assertEqual(len(failed), 4)


# ==========================================================================
# WorkerConfig sanity validation tests
# ==========================================================================

class TestConfigSanity(unittest.TestCase):
    """Tests for WorkerConfig __post_init__ sanity checks."""

    def test_heartbeat_too_high_raises(self):
        """heartbeat_interval_sec >= lease/2 raises ValueError."""
        from lib.config import WorkerConfig
        with self.assertRaises(ValueError) as ctx:
            WorkerConfig(
                worker_id="test",
                lease_minutes=10,           # 600s → /2 = 300s
                heartbeat_interval_sec=300,  # 300 >= 300 → fail
            )
        self.assertIn("heartbeat_interval_sec", str(ctx.exception))

    def test_heartbeat_ok(self):
        """heartbeat_interval_sec < lease/2 works fine."""
        from lib.config import WorkerConfig
        cfg = WorkerConfig(
            worker_id="test",
            lease_minutes=10,            # 600s → /2 = 300s
            heartbeat_interval_sec=120,  # 120 < 300 → ok
        )
        self.assertEqual(cfg.heartbeat_interval_sec, 120)

    def test_timeout_too_high_raises(self):
        """heartbeat_timeout_sec >= heartbeat_interval_sec raises ValueError."""
        from lib.config import WorkerConfig
        with self.assertRaises(ValueError) as ctx:
            WorkerConfig(
                worker_id="test",
                lease_minutes=15,
                heartbeat_interval_sec=120,
                heartbeat_timeout_sec=120,  # 120 >= 120 → fail
            )
        self.assertIn("heartbeat_timeout_sec", str(ctx.exception))

    def test_timeout_ok(self):
        """heartbeat_timeout_sec < heartbeat_interval_sec works fine."""
        from lib.config import WorkerConfig
        cfg = WorkerConfig(
            worker_id="test",
            lease_minutes=15,
            heartbeat_interval_sec=120,
            heartbeat_timeout_sec=10,
        )
        self.assertEqual(cfg.heartbeat_timeout_sec, 10)


# ==========================================================================
# SecretsConfig validate_secrets tests
# ==========================================================================

class TestValidateSecrets(unittest.TestCase):
    """Tests for validate_secrets utility."""

    def test_valid_secrets_pass(self):
        """validate_secrets does not raise when all required fields present."""
        from lib.config import SecretsConfig, validate_secrets
        s = SecretsConfig(
            supabase_url="https://example.supabase.co",
            supabase_service_key="secret123",
        )
        validate_secrets(s)  # should not raise

    def test_missing_url_raises(self):
        """validate_secrets raises when supabase_url is empty."""
        from lib.config import SecretsConfig, validate_secrets
        s = SecretsConfig(supabase_url="", supabase_service_key="key")
        with self.assertRaises(ValueError) as ctx:
            validate_secrets(s)
        self.assertIn("SUPABASE_URL", str(ctx.exception))

    def test_missing_key_raises(self):
        """validate_secrets raises when supabase_service_key is empty."""
        from lib.config import SecretsConfig, validate_secrets
        s = SecretsConfig(supabase_url="https://x.co", supabase_service_key="")
        with self.assertRaises(ValueError) as ctx:
            validate_secrets(s)
        self.assertIn("SUPABASE_SERVICE_KEY", str(ctx.exception))

    def test_both_missing_raises(self):
        """validate_secrets lists all missing vars."""
        from lib.config import SecretsConfig, validate_secrets
        s = SecretsConfig()
        with self.assertRaises(ValueError) as ctx:
            validate_secrets(s)
        msg = str(ctx.exception)
        self.assertIn("SUPABASE_URL", msg)
        self.assertIn("SUPABASE_SERVICE_KEY", msg)


# ==========================================================================
# PID guardrail tests
# ==========================================================================

class TestPidGuardrail(unittest.TestCase):
    """Tests for _is_pid_alive and _pid_is_rayvault."""

    def test_dead_pid(self):
        """_is_pid_alive returns False for non-existent PID."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from rayvault_cli import _is_pid_alive
        self.assertFalse(_is_pid_alive(99999999))

    def test_pid_is_rayvault_dead_pid(self):
        """_pid_is_rayvault returns False for dead PID."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from rayvault_cli import _pid_is_rayvault
        self.assertFalse(_pid_is_rayvault(99999999))


# ==========================================================================
# BrowserContextManager tests (unit, no Playwright)
# ==========================================================================

class TestBrowserContextManager(unittest.TestCase):
    """Unit tests for BrowserContextManager (no real Playwright)."""

    def test_default_viewport(self):
        """BrowserContextManager uses default viewport."""
        from lib.browser import BrowserContextManager, DEFAULT_VIEWPORT
        from lib.config import WorkerConfig
        cfg = WorkerConfig(worker_id="test")
        bcm = BrowserContextManager(cfg)
        self.assertEqual(bcm.viewport, DEFAULT_VIEWPORT)

    def test_custom_viewport(self):
        """BrowserContextManager accepts custom viewport."""
        from lib.browser import BrowserContextManager
        from lib.config import WorkerConfig
        cfg = WorkerConfig(worker_id="test")
        custom = {"width": 1920, "height": 1080}
        bcm = BrowserContextManager(cfg, viewport=custom)
        self.assertEqual(bcm.viewport, custom)

    def test_paths_set(self):
        """BrowserSession sets profile and trace paths."""
        from lib.browser import BrowserSession
        from lib.config import WorkerConfig
        cfg = WorkerConfig(worker_id="test")
        bcm = BrowserSession(cfg)
        self.assertIn("default.json", str(bcm._storage_path("default")))
        self.assertIn("traces", str(bcm._traces_dir))

    def test_no_context_before_enter(self):
        """BrowserContextManager has no context before __aenter__."""
        from lib.browser import BrowserContextManager
        from lib.config import WorkerConfig
        cfg = WorkerConfig(worker_id="test")
        bcm = BrowserContextManager(cfg)
        self.assertIsNone(bcm.browser)
        self.assertIsNone(bcm.context)


# ==========================================================================
# Async worker unit tests (no network)
# ==========================================================================

try:
    import httpx as _httpx_check  # noqa: F401
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


@unittest.skipUnless(_HAS_HTTPX, "httpx not installed")
class TestAsyncWorkerHelpers(unittest.TestCase):
    """Unit tests for worker_async.py helpers."""

    def test_atomic_write_json(self):
        """_atomic_write_json creates file atomically."""
        from worker_async import _atomic_write_json, _read_json
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "sub" / "test.json"
            _atomic_write_json(p, {"key": "value"})
            data = _read_json(p)
            self.assertEqual(data["key"], "value")

    def test_read_json_missing(self):
        """_read_json returns None for missing file."""
        from worker_async import _read_json
        data = _read_json(Path("/nonexistent/file.json"))
        self.assertIsNone(data)

    def test_checkpoint_roundtrip(self):
        """save_checkpoint + load_checkpoint preserves data."""
        from worker_async import save_checkpoint, load_checkpoint, clear_checkpoint
        from lib.config import WorkerConfig
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(worker_id="test", checkpoint_dir=tmpdir)
            run_id = "test-run-123"

            save_checkpoint(cfg, run_id, "research", data={"elapsed_s": 1.5})
            ckpt = load_checkpoint(cfg, run_id)
            self.assertEqual(ckpt["stage"], "research")
            self.assertIn("research", ckpt["completed_steps"])
            self.assertEqual(ckpt["data"]["elapsed_s"], 1.5)

            clear_checkpoint(cfg, run_id)
            ckpt2 = load_checkpoint(cfg, run_id)
            self.assertEqual(ckpt2["stage"], "init")  # back to default

    def test_checkpoint_idempotent_stages(self):
        """Saving same stage twice doesn't duplicate in completed_steps."""
        from worker_async import save_checkpoint, load_checkpoint
        from lib.config import WorkerConfig
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(worker_id="test", checkpoint_dir=tmpdir)
            run_id = "test-run-456"

            save_checkpoint(cfg, run_id, "research")
            save_checkpoint(cfg, run_id, "research")
            ckpt = load_checkpoint(cfg, run_id)
            self.assertEqual(ckpt["completed_steps"].count("research"), 1)


@unittest.skipUnless(_HAS_HTTPX, "httpx not installed")
class TestDisciplineContract(unittest.TestCase):
    """Tests for the pipeline discipline contract scaffold."""

    def test_stage_enum_defined(self):
        """Stage enum has expected members."""
        from lib.config import Stage, STAGE_ORDER
        self.assertIn(Stage.FETCH_PRODUCTS, Stage)
        self.assertIn(Stage.DZINE_GENERATE, Stage)
        self.assertIn(Stage.DONE, Stage)
        self.assertIsInstance(STAGE_ORDER, tuple)
        self.assertGreater(len(STAGE_ORDER), 0)

    def test_browser_stages_subset_of_stage_order(self):
        """BROWSER_STAGES is a subset of STAGE_ORDER."""
        from lib.config import STAGE_ORDER, BROWSER_STAGES
        for s in BROWSER_STAGES:
            self.assertIn(s, STAGE_ORDER)

    def test_expensive_stages_subset_of_stage_order(self):
        """EXPENSIVE_STAGES is a subset of STAGE_ORDER."""
        from lib.config import STAGE_ORDER, EXPENSIVE_STAGES
        for s in EXPENSIVE_STAGES:
            self.assertIn(s, STAGE_ORDER)

    def test_artifact_path_convention(self):
        """_artifact_path returns state/artifacts/{run_id}/{stage}.json."""
        from worker_async import _artifact_path
        from lib.config import WorkerConfig, Stage
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(worker_id="test", state_dir=tmpdir)
            p = _artifact_path(cfg, "run-abc", Stage.FETCH_PRODUCTS)
            self.assertTrue(str(p).endswith("artifacts/run-abc/fetch_products.json"))

    def test_stage_has_artifact_false_when_missing(self):
        """_stage_has_artifact returns False when no artifact file."""
        from worker_async import _stage_has_artifact
        from lib.config import WorkerConfig, Stage
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(worker_id="test", state_dir=tmpdir)
            self.assertFalse(_stage_has_artifact(cfg, "run-abc", Stage.FETCH_PRODUCTS))

    def test_stage_has_artifact_true_when_exists(self):
        """_stage_has_artifact returns True when artifact file exists."""
        from worker_async import _stage_has_artifact, _artifact_path, _atomic_write_json
        from lib.config import WorkerConfig, Stage
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(worker_id="test", state_dir=tmpdir)
            p = _artifact_path(cfg, "run-abc", Stage.FETCH_PRODUCTS)
            _atomic_write_json(p, {"result": "test"})
            self.assertTrue(_stage_has_artifact(cfg, "run-abc", Stage.FETCH_PRODUCTS))

    def test_process_run_stop_signal_immediate(self):
        """process_run returns 'interrupted' immediately if stop_signal is set."""
        import asyncio
        from worker_async import process_run
        from lib.config import WorkerConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(
                worker_id="test",
                checkpoint_dir=tmpdir,
                state_dir=tmpdir,
            )
            rpc = MagicMock()
            rpc.insert_event = MagicMock(return_value=asyncio.coroutine(lambda *a, **k: 200)())
            panic = MagicMock()

            stop = asyncio.Event()
            stop.set()  # Already stopped

            result = asyncio.get_event_loop().run_until_complete(
                process_run(cfg, rpc, panic, "run-123", "tok", "vid",
                            stop, page=None)
            )
            self.assertEqual(result, "interrupted")

    def test_process_run_skips_completed_stages(self):
        """process_run skips stages already in checkpoint."""
        import asyncio
        from worker_async import process_run, save_checkpoint
        from lib.config import WorkerConfig, STAGE_ORDER

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(
                worker_id="test",
                checkpoint_dir=tmpdir,
                state_dir=tmpdir,
            )
            # Pre-fill checkpoint with all stages completed
            for stage in STAGE_ORDER:
                save_checkpoint(cfg, "run-skip", stage.value)

            rpc = MagicMock()
            rpc.insert_event = MagicMock(return_value=asyncio.coroutine(lambda *a, **k: 200)())
            panic = MagicMock()
            stop = asyncio.Event()

            result = asyncio.get_event_loop().run_until_complete(
                process_run(cfg, rpc, panic, "run-skip", "tok", "vid",
                            stop, page=None)
            )
            self.assertEqual(result, "done")

    def test_execute_stage_placeholder_returns_true(self):
        """Placeholder execute_stage returns True (success)."""
        import asyncio
        from worker_async import execute_stage
        from lib.config import Stage

        result = asyncio.get_event_loop().run_until_complete(
            execute_stage(Stage.FETCH_PRODUCTS, "run-1", "vid-1")
        )
        self.assertTrue(result)

    def test_budget_guard_allows_when_under_limit(self):
        """check_budget returns True when under daily limit."""
        from worker_async import check_budget
        from lib.config import WorkerConfig, Stage
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(
                worker_id="test", state_dir=tmpdir,
                budget_daily_limit=10,
            )
            allowed, count = check_budget(cfg, Stage.DZINE_GENERATE)
            self.assertTrue(allowed)
            self.assertEqual(count, 0)

    def test_budget_guard_blocks_when_over_limit(self):
        """check_budget returns False when at daily limit."""
        from worker_async import check_budget, _increment_budget
        from lib.config import WorkerConfig, Stage
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(
                worker_id="test", state_dir=tmpdir,
                budget_daily_limit=2,
            )
            _increment_budget(cfg)
            _increment_budget(cfg)
            allowed, count = check_budget(cfg, Stage.DZINE_GENERATE)
            self.assertFalse(allowed)
            self.assertEqual(count, 2)

    def test_budget_guard_skips_non_expensive(self):
        """check_budget always allows non-expensive stages."""
        from worker_async import check_budget
        from lib.config import WorkerConfig, Stage
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(
                worker_id="test", state_dir=tmpdir,
                budget_daily_limit=0,  # 0 = unlimited
            )
            allowed, count = check_budget(cfg, Stage.WRITE_SCRIPT)
            self.assertTrue(allowed)

    def test_checkpoint_enhanced_schema(self):
        """Enhanced checkpoint includes attempt, artifacts, flags."""
        from worker_async import save_checkpoint, load_checkpoint
        from lib.config import WorkerConfig
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(worker_id="test", checkpoint_dir=tmpdir)
            save_checkpoint(cfg, "run-enh", "fetch_products",
                            artifacts={"image_path": "/tmp/img.png"},
                            data={"elapsed_s": 2.5})
            ckpt = load_checkpoint(cfg, "run-enh")
            self.assertEqual(ckpt["run_id"], "run-enh")
            self.assertIn("fetch_products", ckpt["completed_steps"])
            self.assertEqual(ckpt["artifacts"]["image_path"], "/tmp/img.png")
            self.assertEqual(ckpt["attempt"], 1)
            self.assertIsInstance(ckpt["flags"], dict)

    def test_checkpoint_increment_attempt(self):
        """increment_attempt bumps attempt counter."""
        from worker_async import save_checkpoint, load_checkpoint
        from lib.config import WorkerConfig
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = WorkerConfig(worker_id="test", checkpoint_dir=tmpdir)
            save_checkpoint(cfg, "run-retry", "fetch_products")
            save_checkpoint(cfg, "run-retry", "fetch_products", increment_attempt=True)
            ckpt = load_checkpoint(cfg, "run-retry")
            self.assertEqual(ckpt["attempt"], 2)


# ==========================================================================
# Stage enum tests
# ==========================================================================

class TestStageEnum(unittest.TestCase):
    """Tests for Stage enum and metadata."""

    def test_stage_values_are_strings(self):
        """Stage enum values are strings."""
        from lib.config import Stage
        for s in Stage:
            self.assertIsInstance(s.value, str)

    def test_stage_order_no_init_or_done(self):
        """STAGE_ORDER excludes INIT and DONE markers."""
        from lib.config import Stage, STAGE_ORDER
        self.assertNotIn(Stage.INIT, STAGE_ORDER)
        self.assertNotIn(Stage.DONE, STAGE_ORDER)

    def test_stage_string_comparison(self):
        """Stage enum works in string comparisons."""
        from lib.config import Stage
        self.assertEqual(Stage.FETCH_PRODUCTS, "fetch_products")
        self.assertEqual(Stage.DZINE_GENERATE.value, "dzine_generate")

    def test_expensive_stages_frozenset(self):
        """EXPENSIVE_STAGES is immutable frozenset."""
        from lib.config import EXPENSIVE_STAGES
        self.assertIsInstance(EXPENSIVE_STAGES, frozenset)


# ==========================================================================
# Quarantine with reason filename tests
# ==========================================================================

class TestQuarantineReason(unittest.TestCase):
    """Tests for quarantine file naming with reason."""

    def test_quarantine_includes_reason_in_name(self):
        """Quarantine files include sanitized reason_key."""
        import re
        reason = "panic_lost_lock"
        safe_reason = re.sub(r"[^a-zA-Z0-9_-]", "-", reason)[:48]
        self.assertEqual(safe_reason, "panic_lost_lock")

    def test_quarantine_sanitizes_special_chars(self):
        """Special characters in reason are replaced with hyphens."""
        import re
        reason = "some/weird:reason key!"
        safe_reason = re.sub(r"[^a-zA-Z0-9_-]", "-", reason)[:48]
        self.assertNotIn("/", safe_reason)
        self.assertNotIn(":", safe_reason)
        self.assertNotIn("!", safe_reason)


# ==========================================================================
# Config env prefix tests
# ==========================================================================

class TestConfigEnvPrefix(unittest.TestCase):
    """Tests for RAYVAULT_* env var prefix support."""

    def test_rayvault_prefix_takes_priority(self):
        """RAYVAULT_WORKER_ID overrides WORKER_ID."""
        from lib.config import _env
        with patch.dict(os.environ, {
            "RAYVAULT_WORKER_ID": "prefixed",
            "WORKER_ID": "unprefixed",
        }):
            val = _env("RAYVAULT_WORKER_ID", "WORKER_ID")
        self.assertEqual(val, "prefixed")

    def test_fallback_to_unprefixed(self):
        """Falls back to unprefixed when RAYVAULT_* not set."""
        from lib.config import _env
        env = {"WORKER_ID": "fallback"}
        with patch.dict(os.environ, env, clear=False):
            # Remove prefixed if present
            os.environ.pop("RAYVAULT_WORKER_ID", None)
            val = _env("RAYVAULT_WORKER_ID", "WORKER_ID")
        self.assertEqual(val, "fallback")

    def test_default_when_neither_set(self):
        """Returns default when neither prefix nor fallback is set."""
        from lib.config import _env
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RAYVAULT_WORKER_ID", None)
            os.environ.pop("WORKER_ID", None)
            val = _env("RAYVAULT_WORKER_ID", "WORKER_ID", "default-val")
        self.assertEqual(val, "default-val")

    def test_env_int_parses(self):
        """_env_int returns int from env var."""
        from lib.config import _env_int
        with patch.dict(os.environ, {"RAYVAULT_LEASE_MINUTES": "20"}):
            val = _env_int("RAYVAULT_LEASE_MINUTES", "LEASE_MINUTES", "15")
        self.assertEqual(val, 20)


# ==========================================================================
# BrowserContextManager env config tests
# ==========================================================================

class TestBrowserEnvConfig(unittest.TestCase):
    """Tests for load_browser_config from env vars."""

    def test_default_headless_true(self):
        """load_browser_config defaults to headless=True."""
        from lib.browser import load_browser_config
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BROWSER_HEADLESS", None)
            opts = load_browser_config()
        self.assertTrue(opts["headless"])

    def test_headless_false(self):
        """BROWSER_HEADLESS=false sets headless=False."""
        from lib.browser import load_browser_config
        with patch.dict(os.environ, {"BROWSER_HEADLESS": "false"}):
            opts = load_browser_config()
        self.assertFalse(opts["headless"])

    def test_proxy_from_env(self):
        """BROWSER_PROXY_SERVER sets proxy dict."""
        from lib.browser import load_browser_config
        with patch.dict(os.environ, {"BROWSER_PROXY_SERVER": "http://localhost:8080"}):
            opts = load_browser_config()
        self.assertEqual(opts["proxy"], {"server": "http://localhost:8080"})

    def test_no_proxy_when_empty(self):
        """Empty BROWSER_PROXY_SERVER does not set proxy."""
        from lib.browser import load_browser_config
        with patch.dict(os.environ, {"BROWSER_PROXY_SERVER": ""}):
            opts = load_browser_config()
        self.assertNotIn("proxy", opts)


# ==========================================================================
# Smoke test helper tests
# ==========================================================================

class TestSmokeTestHelpers(unittest.TestCase):
    """Tests for smoke_test_observability.py helpers (no network)."""

    def test_smoke_result_all_passed(self):
        """SmokeResult.all_passed when all steps pass."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from smoke_test_observability import SmokeResult
        r = SmokeResult()
        r.record("step1", True, "ok")
        r.record("step2", True, "ok")
        self.assertTrue(r.all_passed)

    def test_smoke_result_partial_fail(self):
        """SmokeResult.all_passed is False when any step fails."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from smoke_test_observability import SmokeResult
        r = SmokeResult()
        r.record("step1", True, "ok")
        r.record("step2", False, "failed")
        self.assertFalse(r.all_passed)

    def test_smoke_result_summary_format(self):
        """SmokeResult.summary shows N/M format."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from smoke_test_observability import SmokeResult
        r = SmokeResult()
        r.record("a", True)
        r.record("b", False)
        r.record("c", True)
        self.assertEqual(r.summary, "2/3 checks passed")

    def test_supabase_headers(self):
        """_supabase_headers includes apikey and Authorization."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from smoke_test_observability import _supabase_headers
        h = _supabase_headers("test-key-123")
        self.assertEqual(h["apikey"], "test-key-123")
        self.assertEqual(h["Authorization"], "Bearer test-key-123")
        self.assertEqual(h["Content-Type"], "application/json")


# ==========================================================================
# JSON Patch tests
# ==========================================================================

class TestApplyPatch(unittest.TestCase):
    """Tests for apply_patch.py — JSON Patch operations + guardrails."""

    def test_replace_basic(self):
        """Replace a top-level key."""
        from lib.apply_patch import apply_patch
        base = {"name": "old", "value": 1}
        ops = [{"op": "replace", "path": "/name", "value": "new"}]
        result = apply_patch(base, ops)
        self.assertEqual(result["name"], "new")
        self.assertEqual(result["value"], 1)
        # Original not mutated
        self.assertEqual(base["name"], "old")

    def test_replace_nested(self):
        """Replace a nested key."""
        from lib.apply_patch import apply_patch
        base = {"script": {"hook": "old hook", "cta": "Buy now"}}
        ops = [{"op": "replace", "path": "/script/hook", "value": "This changed everything"}]
        result = apply_patch(base, ops)
        self.assertEqual(result["script"]["hook"], "This changed everything")
        self.assertEqual(result["script"]["cta"], "Buy now")

    def test_add_new_key(self):
        """Add a new key to an object."""
        from lib.apply_patch import apply_patch
        base = {"a": 1}
        ops = [{"op": "add", "path": "/b", "value": 2}]
        result = apply_patch(base, ops)
        self.assertEqual(result["b"], 2)

    def test_remove_key(self):
        """Remove a key from an object."""
        from lib.apply_patch import apply_patch
        base = {"a": 1, "b": 2}
        ops = [{"op": "remove", "path": "/b"}]
        result = apply_patch(base, ops)
        self.assertNotIn("b", result)
        self.assertEqual(result["a"], 1)

    def test_multiple_ops(self):
        """Apply multiple operations in sequence."""
        from lib.apply_patch import apply_patch
        base = {"facts": {"price": 99, "rating": 4.5}}
        ops = [
            {"op": "replace", "path": "/facts/price", "value": 199},
            {"op": "replace", "path": "/facts/rating", "value": 4.8},
        ]
        result = apply_patch(base, ops)
        self.assertEqual(result["facts"]["price"], 199)
        self.assertEqual(result["facts"]["rating"], 4.8)

    def test_strict_mode_raises(self):
        """Strict mode raises PatchError on invalid op."""
        from lib.apply_patch import apply_patch, PatchError
        base = {"a": 1}
        ops = [{"op": "replace", "path": "/missing", "value": 2}]
        with self.assertRaises(PatchError):
            apply_patch(base, ops, strict=True)

    def test_non_strict_collects_errors(self):
        """Non-strict mode collects errors in _patch_errors."""
        from lib.apply_patch import apply_patch
        base = {"a": 1}
        ops = [{"op": "replace", "path": "/missing", "value": 2}]
        result = apply_patch(base, ops, strict=False)
        self.assertIn("_patch_errors", result)
        self.assertEqual(len(result["_patch_errors"]), 1)

    def test_allowed_prefixes_blocks(self):
        """Path allowlist blocks unauthorized paths."""
        from lib.apply_patch import apply_patch, PatchError
        base = {"script": {"hook": "x"}, "secret": "y"}
        ops = [{"op": "replace", "path": "/secret", "value": "hacked"}]
        with self.assertRaises(PatchError):
            apply_patch(base, ops, allowed_prefixes=("/script", "/facts"))

    def test_allowed_prefixes_allows(self):
        """Path allowlist permits authorized paths."""
        from lib.apply_patch import apply_patch
        base = {"script": {"hook": "x"}, "facts": {"price": 99}}
        ops = [{"op": "replace", "path": "/script/hook", "value": "new"}]
        result = apply_patch(base, ops, allowed_prefixes=("/script", "/facts"))
        self.assertEqual(result["script"]["hook"], "new")

    def test_disallowed_ops_blocks_remove(self):
        """Disallowed ops blocks remove operations."""
        from lib.apply_patch import apply_patch, PatchError
        base = {"a": 1, "b": 2}
        ops = [{"op": "remove", "path": "/b"}]
        with self.assertRaises(PatchError):
            apply_patch(base, ops, disallowed_ops=frozenset({"remove"}))

    def test_max_ops_limit(self):
        """Max ops limit prevents oversized patches."""
        from lib.apply_patch import apply_patch, PatchError
        base = {"a": 1}
        ops = [{"op": "replace", "path": "/a", "value": i} for i in range(25)]
        with self.assertRaises(PatchError):
            apply_patch(base, ops, max_ops=20)

    def test_extract_patch_ops(self):
        """Extract patch_ops from LLM response."""
        from lib.apply_patch import extract_patch_ops
        resp = {"status": "ok", "patch_ops": [{"op": "replace", "path": "/a", "value": 1}]}
        ops = extract_patch_ops(resp)
        self.assertEqual(len(ops), 1)

    def test_extract_patch_ops_missing(self):
        """Extract returns empty list if no patch_ops."""
        from lib.apply_patch import extract_patch_ops
        self.assertEqual(extract_patch_ops({}), [])
        self.assertEqual(extract_patch_ops("not a dict"), [])


# ==========================================================================
# Coercion tests
# ==========================================================================

class TestCoercion(unittest.TestCase):
    """Tests for coercion helpers — cheap fixes before LLM repair."""

    def test_coerce_price_usd(self):
        from lib.apply_patch import coerce_price
        self.assertAlmostEqual(coerce_price("$199.99"), 199.99)

    def test_coerce_price_brl(self):
        from lib.apply_patch import coerce_price
        self.assertAlmostEqual(coerce_price("R$ 1.299,90"), 1299.90)

    def test_coerce_price_plain(self):
        from lib.apply_patch import coerce_price
        self.assertAlmostEqual(coerce_price("199"), 199.0)

    def test_coerce_price_empty(self):
        from lib.apply_patch import coerce_price
        self.assertIsNone(coerce_price(""))

    def test_coerce_rating_out_of_5(self):
        from lib.apply_patch import coerce_rating
        self.assertAlmostEqual(coerce_rating("4.7 out of 5"), 4.7)

    def test_coerce_rating_slash(self):
        from lib.apply_patch import coerce_rating
        self.assertAlmostEqual(coerce_rating("4.7/5"), 4.7)

    def test_coerce_rating_plain(self):
        from lib.apply_patch import coerce_rating
        self.assertAlmostEqual(coerce_rating("4.7"), 4.7)

    def test_coerce_reviews_with_comma(self):
        from lib.apply_patch import coerce_reviews
        self.assertEqual(coerce_reviews("1,234 ratings"), 1234)

    def test_coerce_reviews_k_suffix(self):
        from lib.apply_patch import coerce_reviews
        self.assertEqual(coerce_reviews("12K"), 12000)

    def test_coerce_reviews_plain(self):
        from lib.apply_patch import coerce_reviews
        self.assertEqual(coerce_reviews("567"), 567)


# ==========================================================================
# JSON Schema Guard tests
# ==========================================================================

class TestSchemaGuard(unittest.TestCase):
    """Tests for json_schema_guard.py — LLM output validation + repair prompts."""

    def test_valid_output(self):
        """Valid output passes validation."""
        from lib.json_schema_guard import validate_output
        schema = {
            "type": "object",
            "required": ["name", "value"],
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "integer"},
            },
        }
        errors = validate_output({"name": "test", "value": 42}, schema)
        self.assertEqual(errors, [])

    def test_missing_required_field(self):
        """Missing required field detected."""
        from lib.json_schema_guard import validate_output
        schema = {
            "type": "object",
            "required": ["name", "value"],
            "properties": {},
        }
        errors = validate_output({"name": "test"}, schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("value", errors[0].path)

    def test_wrong_type(self):
        """Wrong type detected."""
        from lib.json_schema_guard import validate_output
        schema = {"type": "string"}
        errors = validate_output(42, schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("string", errors[0].message)

    def test_string_too_long(self):
        """String exceeding maxLength detected."""
        from lib.json_schema_guard import validate_output
        schema = {"type": "string", "maxLength": 5}
        errors = validate_output("toolong", schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("too long", errors[0].message)

    def test_array_too_short(self):
        """Array below minItems detected."""
        from lib.json_schema_guard import validate_output
        schema = {"type": "array", "minItems": 3}
        errors = validate_output([1, 2], schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("too short", errors[0].message)

    def test_enum_violation(self):
        """Enum violation detected."""
        from lib.json_schema_guard import validate_output
        schema = {"type": "string", "enum": ["ok", "needs_human"]}
        errors = validate_output("invalid", schema)
        self.assertEqual(len(errors), 1)

    def test_nested_validation(self):
        """Nested object validation works."""
        from lib.json_schema_guard import validate_output
        schema = {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "object",
                    "required": ["price"],
                    "properties": {"price": {"type": "number"}},
                },
            },
        }
        errors = validate_output({"facts": {"price": "not_a_number"}}, schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("facts.price", errors[0].path)

    def test_multiple_errors_returned(self):
        """Multiple errors detected in one pass."""
        from lib.json_schema_guard import validate_output
        schema = {
            "type": "object",
            "required": ["a", "b", "c"],
        }
        errors = validate_output({}, schema)
        self.assertEqual(len(errors), 3)

    def test_build_repair_prompt(self):
        """Repair prompt generated correctly."""
        from lib.json_schema_guard import validate_output, build_repair_prompt, SchemaValidationError
        errors = [SchemaValidationError("$.name", "Required field missing")]
        schema = {"type": "object", "required": ["name"]}
        prompt = build_repair_prompt({"value": 42}, schema, errors)
        self.assertIn("REPAIR REQUEST", prompt)
        self.assertIn("$.name", prompt)
        self.assertIn("Required field missing", prompt)

    def test_parse_llm_json_clean(self):
        """Parse clean JSON from LLM."""
        from lib.json_schema_guard import parse_llm_json
        obj, errors = parse_llm_json('{"status": "ok"}')
        self.assertIsNotNone(obj)
        self.assertEqual(obj["status"], "ok")
        self.assertEqual(errors, [])

    def test_parse_llm_json_with_markdown(self):
        """Parse JSON wrapped in markdown code fences."""
        from lib.json_schema_guard import parse_llm_json
        raw = '```json\n{"status": "ok"}\n```'
        obj, errors = parse_llm_json(raw)
        self.assertIsNotNone(obj)
        self.assertEqual(obj["status"], "ok")

    def test_parse_llm_json_with_preamble(self):
        """Parse JSON with text before it."""
        from lib.json_schema_guard import parse_llm_json
        raw = 'Here is the result:\n{"status": "ok", "value": 42}'
        obj, errors = parse_llm_json(raw)
        self.assertIsNotNone(obj)
        self.assertEqual(obj["status"], "ok")


# ==========================================================================
# Prompt contract loader tests
# ==========================================================================

class TestPromptContractLoader(unittest.TestCase):
    """Tests for prompt_contract_loader.py."""

    def test_strip_volatile(self):
        """Volatile keys are stripped for cache stability."""
        from lib.prompt_contract_loader import strip_volatile
        payload = {
            "topic": "earbuds",
            "timestamp": "2024-01-01",
            "retry_count": 3,
            "nested": {"trace_id": "abc", "data": 42},
        }
        result = strip_volatile(payload)
        self.assertIn("topic", result)
        self.assertNotIn("timestamp", result)
        self.assertNotIn("retry_count", result)
        self.assertNotIn("trace_id", result["nested"])
        self.assertEqual(result["nested"]["data"], 42)

    def test_compute_cache_key_deterministic(self):
        """Same inputs produce same cache key."""
        from lib.prompt_contract_loader import compute_cache_key, ContractSpec, CACHE_POLICIES
        spec = ContractSpec(name="test", version="v1", cache_policy=CACHE_POLICIES["daily"])
        payload = {"topic": "earbuds"}
        k1 = compute_cache_key(spec, payload)
        k2 = compute_cache_key(spec, payload)
        self.assertEqual(k1, k2)

    def test_compute_cache_key_ignores_volatile(self):
        """Cache key is stable despite volatile field changes."""
        from lib.prompt_contract_loader import compute_cache_key, ContractSpec, CACHE_POLICIES
        spec = ContractSpec(name="test", version="v1", cache_policy=CACHE_POLICIES["daily"])
        p1 = {"topic": "earbuds", "timestamp": "2024-01-01"}
        p2 = {"topic": "earbuds", "timestamp": "2024-12-31"}
        self.assertEqual(compute_cache_key(spec, p1), compute_cache_key(spec, p2))

    def test_cache_set_and_get(self):
        """Cache round-trip works."""
        from lib.prompt_contract_loader import LLMCache
        with tempfile.TemporaryDirectory() as td:
            cache = LLMCache(td)
            cache.set("k1", {"answer": 42}, ttl_sec=3600, meta={"contract": "test"})
            hit = cache.get("k1")
            self.assertIsNotNone(hit)
            self.assertEqual(hit["value"]["answer"], 42)

    def test_cache_ttl_expiry(self):
        """Expired cache entries return None."""
        from lib.prompt_contract_loader import LLMCache
        with tempfile.TemporaryDirectory() as td:
            cache = LLMCache(td)
            cache.set("k1", {"answer": 42}, ttl_sec=1, meta={})
            # Manually backdate
            p = cache._path("k1")
            data = json.loads(p.read_text())
            data["_meta"]["created_at"] = time.time() - 100
            p.write_text(json.dumps(data))
            self.assertIsNone(cache.get("k1"))

    def test_cache_invalidate(self):
        """Cache invalidation removes entry."""
        from lib.prompt_contract_loader import LLMCache
        with tempfile.TemporaryDirectory() as td:
            cache = LLMCache(td)
            cache.set("k1", {"x": 1}, ttl_sec=3600, meta={})
            self.assertTrue(cache.invalidate("k1"))
            self.assertIsNone(cache.get("k1"))
            self.assertFalse(cache.invalidate("k1"))  # already gone

    def test_prompt_builder(self):
        """PromptBuilder produces structured prompt."""
        from lib.prompt_contract_loader import PromptBuilder, ContractLoader, ContractSpec, CACHE_POLICIES
        with tempfile.TemporaryDirectory() as td:
            loader = ContractLoader(td)
            builder = PromptBuilder(loader)
            spec = ContractSpec(
                name="test", version="v1",
                cache_policy=CACHE_POLICIES["daily"],
                schema={"type": "object", "required": ["name"]},
            )
            prompt = builder.build(
                spec, {"topic": "earbuds"},
                contract_text_override="You are a test contract.",
            )
            self.assertIn("### CONTRACT", prompt)
            self.assertIn("### ECONOMY RULES", prompt)
            self.assertIn("### OUTPUT SCHEMA", prompt)
            self.assertIn("### payload", prompt)

    def test_prompt_builder_patch_mode(self):
        """PromptBuilder includes patch mode section."""
        from lib.prompt_contract_loader import PromptBuilder, ContractLoader, ContractSpec, CACHE_POLICIES
        with tempfile.TemporaryDirectory() as td:
            loader = ContractLoader(td)
            builder = PromptBuilder(loader)
            spec = ContractSpec(
                name="test", version="v1",
                cache_policy=CACHE_POLICIES["daily"],
                schema={"type": "object"},
            )
            prompt = builder.build(
                spec, {"topic": "earbuds"},
                contract_text_override="test",
                patch_against={"old": "data"},
            )
            self.assertIn("### PATCH MODE", prompt)
            self.assertIn("### base", prompt)

    def test_contract_engine_roundtrip(self):
        """ContractEngine build + cache + retrieve."""
        from lib.prompt_contract_loader import ContractEngine, ContractSpec, CACHE_POLICIES
        with tempfile.TemporaryDirectory() as td:
            engine = ContractEngine(contracts_dir=td, cache_dir=os.path.join(td, "cache"))
            spec = ContractSpec(
                name="test", version="v1",
                cache_policy=CACHE_POLICIES["daily"],
                schema={"type": "object"},
            )
            payload = {"topic": "earbuds"}
            prompt, key = engine.build_prompt_and_cache_key(spec, payload)
            self.assertIsNone(engine.try_cache(key))
            engine.save_cache(key, {"result": "ok"}, spec, payload)
            cached = engine.try_cache(key)
            self.assertIsNotNone(cached)
            self.assertEqual(cached["result"], "ok")


# ==========================================================================
# Schemas + prefilter tests
# ==========================================================================

class TestSchemas(unittest.TestCase):
    """Tests for schemas.py — Amazon extract + ranker schemas + prefilter."""

    def test_amazon_schema_valid(self):
        """Valid Amazon extract output passes schema validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import AMAZON_EXTRACT_SCHEMA
        valid_output = {
            "status": "ok",
            "asin": "B0EXAMPLE1",
            "facts": {
                "title": "Test Product",
                "price": {"amount": 49.99, "currency": "USD"},
                "rating": 4.5,
                "reviews": 1234,
                "availability": "In Stock",
                "brand": "TestBrand",
                "top_features": ["Feature 1", "Feature 2"],
            },
            "signals": {
                "confidence": 0.95,
                "needs_refetch": False,
                "suspected_layout_change": False,
            },
            "issues": [],
        }
        errors = validate_output(valid_output, AMAZON_EXTRACT_SCHEMA)
        self.assertEqual(errors, [])

    def test_amazon_schema_missing_facts(self):
        """Missing facts detected by schema validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import AMAZON_EXTRACT_SCHEMA
        bad = {"status": "ok", "asin": "B0EXAMPLE1"}
        errors = validate_output(bad, AMAZON_EXTRACT_SCHEMA)
        self.assertTrue(len(errors) > 0)

    def test_ranker_schema_valid(self):
        """Valid ranker output passes validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import RANKER_SCHEMA
        valid = {
            "status": "ok",
            "winners": [
                {
                    "asin": "B0EXAMPLE1",
                    "slot": "best_overall",
                    "score": 85,
                    "why": ["Great rating", "Good price"],
                },
            ],
            "rejected": [
                {"asin": "B0BADONE01", "reason_code": "rating_too_low"},
            ],
            "notes": {"decision_trace": ["Applied hard rules first"]},
        }
        errors = validate_output(valid, RANKER_SCHEMA)
        self.assertEqual(errors, [])

    def test_prefilter_removes_needs_human(self):
        """Prefilter rejects candidates with status=needs_human."""
        from lib.schemas import prefilter_candidates
        candidates = [
            {"asin": "B0OK000001", "status": "ok", "facts": {"title": "X", "price": {"amount": 50, "currency": "USD"}, "rating": 4.5, "reviews": 500, "brand": "Y"}},
            {"asin": "B0BAD00001", "status": "needs_human"},
        ]
        passed, rejected = prefilter_candidates(candidates, budget_max=100)
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0]["asin"], "B0OK000001")
        self.assertEqual(rejected[0]["reason_code"], "needs_human_upstream")

    def test_prefilter_budget_check(self):
        """Prefilter rejects candidates outside budget."""
        from lib.schemas import prefilter_candidates
        candidates = [
            {"asin": "B0CHEAP001", "status": "ok", "facts": {"title": "X", "price": {"amount": 30, "currency": "USD"}, "rating": 4.5, "reviews": 500, "brand": "Y"}},
            {"asin": "B0PRICEY01", "status": "ok", "facts": {"title": "X", "price": {"amount": 500, "currency": "USD"}, "rating": 4.5, "reviews": 500, "brand": "Y"}},
        ]
        passed, rejected = prefilter_candidates(candidates, budget_max=100)
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0]["asin"], "B0CHEAP001")

    def test_prefilter_rating_threshold(self):
        """Prefilter rejects low-rated candidates."""
        from lib.schemas import prefilter_candidates
        candidates = [
            {"asin": "B0GOOD0001", "status": "ok", "facts": {"title": "X", "price": {"amount": 50, "currency": "USD"}, "rating": 4.5, "reviews": 500, "brand": "Y"}},
            {"asin": "B0LOW00001", "status": "ok", "facts": {"title": "X", "price": {"amount": 50, "currency": "USD"}, "rating": 3.0, "reviews": 500, "brand": "Y"}},
        ]
        passed, rejected = prefilter_candidates(candidates, min_rating=4.0)
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0]["asin"], "B0GOOD0001")

    def test_prefilter_max_candidates(self):
        """Prefilter limits output to max_candidates."""
        from lib.schemas import prefilter_candidates
        candidates = [
            {"asin": f"B0TEST{i:05d}", "status": "ok",
             "facts": {"title": f"P{i}", "price": {"amount": 50, "currency": "USD"}, "rating": 4.0 + i * 0.01, "reviews": 100 + i, "brand": "Y"},
             "signals": {"confidence": 0.9}}
            for i in range(20)
        ]
        passed, rejected = prefilter_candidates(candidates, max_candidates=5)
        self.assertEqual(len(passed), 5)

    def test_prefilter_brand_exclusion(self):
        """Prefilter rejects excluded brands."""
        from lib.schemas import prefilter_candidates
        candidates = [
            {"asin": "B0GOOD0001", "status": "ok", "facts": {"title": "X", "price": {"amount": 50, "currency": "USD"}, "rating": 4.5, "reviews": 500, "brand": "GoodBrand"}},
            {"asin": "B0BAD00001", "status": "ok", "facts": {"title": "X", "price": {"amount": 50, "currency": "USD"}, "rating": 4.5, "reviews": 500, "brand": "BadBrand"}},
        ]
        passed, rejected = prefilter_candidates(candidates, exclude_brands=["BadBrand"])
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0]["asin"], "B0GOOD0001")


# ==========================================================================
# BrowserSession tests
# ==========================================================================

class TestBrowserSession(unittest.TestCase):
    """Tests for browser.py — BrowserSession profile paths + config."""

    def test_storage_path_per_profile(self):
        """Each profile gets its own storage_state path."""
        from lib.browser import BrowserSession
        from lib.config import WorkerConfig
        cfg = WorkerConfig(
            state_dir=tempfile.mkdtemp(),
            heartbeat_interval_sec=30,
            lease_minutes=15,
        )
        session = BrowserSession(cfg)
        dzine = session._storage_path("dzine")
        chatgpt = session._storage_path("chatgpt")
        default = session._storage_path("default")
        self.assertNotEqual(dzine, chatgpt)
        self.assertNotEqual(chatgpt, default)
        self.assertTrue(str(dzine).endswith("dzine.json"))
        self.assertTrue(str(chatgpt).endswith("chatgpt.json"))

    def test_backward_compat_alias(self):
        """BrowserContextManager alias exists for backward compatibility."""
        from lib.browser import BrowserContextManager, BrowserSession
        self.assertIs(BrowserContextManager, BrowserSession)

    def test_load_browser_config_defaults(self):
        """load_browser_config returns defaults when no env vars set."""
        from lib.browser import load_browser_config
        # Clear relevant env vars
        for key in ["BROWSER_HEADLESS", "BROWSER_USER_AGENT", "BROWSER_PROXY_SERVER"]:
            os.environ.pop(key, None)
        opts = load_browser_config()
        self.assertTrue(opts["headless"])

    def test_load_browser_config_headless_false(self):
        """load_browser_config respects BROWSER_HEADLESS=false."""
        from lib.browser import load_browser_config
        os.environ["BROWSER_HEADLESS"] = "false"
        try:
            opts = load_browser_config()
            self.assertFalse(opts["headless"])
        finally:
            os.environ.pop("BROWSER_HEADLESS", None)

    def test_known_profiles(self):
        """KNOWN_PROFILES includes expected services."""
        from lib.browser import KNOWN_PROFILES
        self.assertIn("dzine", KNOWN_PROFILES)
        self.assertIn("chatgpt", KNOWN_PROFILES)
        self.assertIn("claude", KNOWN_PROFILES)
        self.assertIn("default", KNOWN_PROFILES)


# ==========================================================================
# Media probe tests
# ==========================================================================

class TestMediaProbe(unittest.TestCase):
    """Tests for media_probe.py — ffprobe validation (no ffprobe dependency)."""

    def test_render_validation_error_missing_file(self):
        """RenderValidationError raised for missing file."""
        from lib.media_probe import validate_render, RenderValidationError
        with self.assertRaises(RenderValidationError) as ctx:
            validate_render(Path("/nonexistent/video.mp4"))
        self.assertIn("missing", str(ctx.exception).lower())

    def test_get_duration_returns_zero_on_error(self):
        """get_duration returns 0.0 when file doesn't exist."""
        from lib.media_probe import get_duration
        self.assertEqual(get_duration(Path("/nonexistent/video.mp4")), 0.0)

    def test_get_video_info_returns_empty_on_error(self):
        """get_video_info returns {} when file doesn't exist."""
        from lib.media_probe import get_video_info
        self.assertEqual(get_video_info(Path("/nonexistent/video.mp4")), {})


# ==========================================================================
# ElevenLabs TTS tests
# ==========================================================================

class TestElevenLabsTTS(unittest.TestCase):
    """Tests for elevenlabs_tts.py — config + validation (no API calls)."""

    def test_config_defaults(self):
        """ElevenLabsConfig has sensible defaults."""
        from agents.elevenlabs_tts import ElevenLabsConfig
        cfg = ElevenLabsConfig(api_key="test", voice_id="voice123")
        self.assertEqual(cfg.model_id, "eleven_multilingual_v2")
        self.assertEqual(cfg.min_output_bytes, 50_000)
        self.assertEqual(cfg.max_text_chars, 5000)

    def test_validation_error_empty_text(self):
        """TTSValidationError raised for empty text."""
        from agents.elevenlabs_tts import ElevenLabsTTS, ElevenLabsConfig, TTSValidationError
        cfg = ElevenLabsConfig(
            api_key="test", voice_id="voice123",
            output_dir=tempfile.mkdtemp(),
        )
        tts = ElevenLabsTTS(cfg)
        with self.assertRaises(TTSValidationError):
            tts.synthesize(run_id="test", text="")

    def test_validation_error_text_too_long(self):
        """TTSValidationError raised for text exceeding limit."""
        from agents.elevenlabs_tts import ElevenLabsTTS, ElevenLabsConfig, TTSValidationError
        cfg = ElevenLabsConfig(
            api_key="test", voice_id="voice123",
            output_dir=tempfile.mkdtemp(),
            max_text_chars=10,
        )
        tts = ElevenLabsTTS(cfg)
        with self.assertRaises(TTSValidationError):
            tts.synthesize(run_id="test", text="x" * 20)

    def test_has_artifact_false(self):
        """has_artifact returns False when no file exists."""
        from agents.elevenlabs_tts import ElevenLabsTTS, ElevenLabsConfig
        cfg = ElevenLabsConfig(
            api_key="test", voice_id="voice123",
            output_dir=tempfile.mkdtemp(),
        )
        tts = ElevenLabsTTS(cfg)
        self.assertFalse(tts.has_artifact("nonexistent"))


# ==========================================================================
# WebChatAgent tests
# ==========================================================================

class TestWebChatAgent(unittest.TestCase):
    """Tests for webchat_agent.py — config + target setup (no browser)."""

    def test_target_configs_exist(self):
        """TARGET_CONFIGS has entries for both services."""
        from agents.webchat_agent import TARGET_CONFIGS, WebChatTarget
        self.assertIn(WebChatTarget.CHATGPT, TARGET_CONFIGS)
        self.assertIn(WebChatTarget.CLAUDE, TARGET_CONFIGS)

    def test_chatgpt_config(self):
        """ChatGPT config has correct URL and profile."""
        from agents.webchat_agent import TARGET_CONFIGS, WebChatTarget
        cfg = TARGET_CONFIGS[WebChatTarget.CHATGPT]
        self.assertEqual(cfg.profile, "chatgpt")
        self.assertIn("chatgpt.com", cfg.url)

    def test_claude_config(self):
        """Claude config has correct URL and profile."""
        from agents.webchat_agent import TARGET_CONFIGS, WebChatTarget
        cfg = TARGET_CONFIGS[WebChatTarget.CLAUDE]
        self.assertEqual(cfg.profile, "claude")
        self.assertIn("claude.ai", cfg.url)

    def test_agent_init(self):
        """WebChatAgent initializes with target config."""
        from agents.webchat_agent import WebChatAgent, WebChatTarget
        agent = WebChatAgent(WebChatTarget.CHATGPT)
        self.assertEqual(agent.config.name, "ChatGPT")

    def test_webchat_result_fields(self):
        """WebChatResult has expected fields."""
        from agents.webchat_agent import WebChatResult
        r = WebChatResult(text="Hello", success=True)
        self.assertEqual(r.text, "Hello")
        self.assertTrue(r.success)
        self.assertFalse(r.needs_login)
        self.assertEqual(r.stable_ticks, 0)


# ==========================================================================
# Execute stage wiring tests
# ==========================================================================

try:
    import httpx as _httpx_check
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


@unittest.skipUnless(_HAS_HTTPX, "httpx not installed")
class TestExecuteStageWiring(unittest.TestCase):
    """Tests for execute_stage dispatch to real agents."""

    def test_execute_stage_placeholder_returns_true(self):
        """Placeholder stages return True."""
        import asyncio
        from worker_async import execute_stage
        from lib.config import Stage
        result = asyncio.run(execute_stage(Stage.UPLOAD, "run-1", "vid-1"))
        self.assertTrue(result)

    def test_execute_stage_write_script(self):
        """WRITE_SCRIPT stage executes without error."""
        import asyncio
        from worker_async import execute_stage
        from lib.config import Stage
        result = asyncio.run(execute_stage(Stage.WRITE_SCRIPT, "run-1", "vid-1"))
        self.assertTrue(result)

    def test_execute_stage_render_no_file(self):
        """RENDER stage passes when no MP4 file exists (placeholder)."""
        import asyncio
        from worker_async import execute_stage
        from lib.config import Stage, WorkerConfig
        cfg = WorkerConfig(
            state_dir=tempfile.mkdtemp(),
            heartbeat_interval_sec=30,
            lease_minutes=15,
        )
        result = asyncio.run(execute_stage(Stage.RENDER, "run-1", "vid-1", cfg=cfg))
        self.assertTrue(result)

    def test_execute_stage_fetch_products_with_page(self):
        """FETCH_PRODUCTS stage accepts page parameter."""
        import asyncio
        from worker_async import execute_stage
        from lib.config import Stage
        result = asyncio.run(execute_stage(
            Stage.FETCH_PRODUCTS, "run-1", "vid-1", page=None,
        ))
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
