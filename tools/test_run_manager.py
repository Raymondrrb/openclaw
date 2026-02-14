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
    VALID_TRANSITIONS,
    BLOCKED_STATES,
    ACTIVE_STATES,
    CLAIMABLE_STATUSES,
    DEFAULT_LEASE_MINUTES,
    MIN_LEASE_MINUTES,
    MAX_LEASE_MINUTES,
    MIN_WORKER_ID_LEN,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
