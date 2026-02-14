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


if __name__ == "__main__":
    unittest.main(verbosity=2)
