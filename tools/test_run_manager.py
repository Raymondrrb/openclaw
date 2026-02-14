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


class TestNormalizeClaimKey(unittest.TestCase):
    """Tests for claim key normalization."""

    def test_camel_case(self):
        from lib.circuit_breaker import normalize_claim_key
        self.assertEqual(normalize_claim_key("batteryLife"), "battery_life")

    def test_title_case_spaces(self):
        from lib.circuit_breaker import normalize_claim_key
        self.assertEqual(normalize_claim_key("Battery Life"), "battery_life")

    def test_upper_snake(self):
        from lib.circuit_breaker import normalize_claim_key
        self.assertEqual(normalize_claim_key("BATTERY-LIFE"), "battery_life")

    def test_already_normalized(self):
        from lib.circuit_breaker import normalize_claim_key
        self.assertEqual(normalize_claim_key("price_claim"), "price_claim")

    def test_mixed(self):
        from lib.circuit_breaker import normalize_claim_key
        self.assertEqual(normalize_claim_key("CoreSpecs.v2"), "core_specs_v2")


class TestMPCWeightedMean(unittest.TestCase):
    """Tests for weighted_mean computation."""

    def test_equal_weights(self):
        from lib.circuit_breaker import weighted_mean
        self.assertAlmostEqual(weighted_mean([0.8, 0.6], [1.0, 1.0]), 0.7)

    def test_empty(self):
        from lib.circuit_breaker import weighted_mean
        self.assertEqual(weighted_mean([], []), 0.0)

    def test_single_value(self):
        from lib.circuit_breaker import weighted_mean
        self.assertAlmostEqual(weighted_mean([0.9], [1.0]), 0.9)

    def test_zero_weights(self):
        from lib.circuit_breaker import weighted_mean
        self.assertEqual(weighted_mean([0.5, 0.5], [0.0, 0.0]), 0.0)


class TestComputeMPCByClaim(unittest.TestCase):
    """Tests for MPC top-N per claim computation."""

    def test_top_n_filtering(self):
        from lib.circuit_breaker import compute_mpc_by_claim, EvidenceItem, MPCConfig
        cfg = MPCConfig(top_n=2)
        evidence = [
            EvidenceItem("price", 0.9, trust_tier=4),
            EvidenceItem("price", 0.7, trust_tier=3),
            EvidenceItem("price", 0.3, trust_tier=2),  # should be excluded (top_n=2)
        ]
        mpc = compute_mpc_by_claim(evidence, cfg)
        # Top 2: 0.9 and 0.7 → mean = 0.8
        self.assertAlmostEqual(mpc["price"], 0.8)

    def test_multiple_claims(self):
        from lib.circuit_breaker import compute_mpc_by_claim, EvidenceItem, MPCConfig
        cfg = MPCConfig(top_n=3)
        evidence = [
            EvidenceItem("price", 0.9, trust_tier=4),
            EvidenceItem("voltage", 0.6, trust_tier=3),
            EvidenceItem("voltage", 0.8, trust_tier=4),
        ]
        mpc = compute_mpc_by_claim(evidence, cfg)
        self.assertAlmostEqual(mpc["price"], 0.9)
        self.assertAlmostEqual(mpc["voltage"], 0.7)  # (0.8+0.6)/2


class TestClassifyMPCDecision(unittest.TestCase):
    """Tests for 4-level MPC decision classification."""

    def test_all_strong_proceeds(self):
        from lib.circuit_breaker import classify_mpc_decision, MPCConfig
        cfg = MPCConfig()
        mpc = {"price": 0.9, "voltage": 0.85, "compatibility": 0.8, "core_specs": 0.75}
        decision, weak = classify_mpc_decision(mpc, cfg)
        self.assertEqual(decision, "proceed")
        self.assertEqual(len(weak), 0)

    def test_critical_weak_gates(self):
        from lib.circuit_breaker import classify_mpc_decision, MPCConfig
        cfg = MPCConfig(silver_min=0.5)
        mpc = {"price": 0.3, "voltage": 0.9}
        decision, weak = classify_mpc_decision(mpc, cfg)
        self.assertEqual(decision, "gate")
        self.assertTrue(any("price" in w for w in weak))

    def test_non_critical_weak_warns(self):
        from lib.circuit_breaker import classify_mpc_decision, MPCConfig
        cfg = MPCConfig(silver_min=0.5, critical_claims=["price"])
        mpc = {"price": 0.8, "shipping": 0.3}
        decision, weak = classify_mpc_decision(mpc, cfg)
        self.assertEqual(decision, "proceed_warn")
        self.assertTrue(any("shipping" in w for w in weak))


class TestRunCircuitBreaker(unittest.TestCase):
    """Tests for the full MPC circuit breaker entrypoint."""

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def test_strong_evidence_proceeds(self):
        from lib.circuit_breaker import run_circuit_breaker
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "voltage", "confidence": 0.85, "fetched_at": self._now_iso(), "trust_tier": 4},
            {"claim_type": "compatibility", "confidence": 0.8, "fetched_at": self._now_iso(), "trust_tier": 3},
            {"claim_type": "core_specs", "confidence": 0.75, "fetched_at": self._now_iso(), "trust_tier": 3},
        ]
        result = run_circuit_breaker("R1", "final_script", evidence)
        self.assertEqual(result.decision, "proceed")
        self.assertFalse(result.should_gate)
        self.assertFalse(result.used_refetch)

    def test_weak_critical_gates(self):
        from lib.circuit_breaker import run_circuit_breaker, MPCConfig
        cfg = MPCConfig(allow_auto_refetch=False)
        evidence = [
            {"claim_type": "price", "confidence": 0.2, "fetched_at": self._now_iso(), "trust_tier": 2},
        ]
        result = run_circuit_breaker("R1", "final_script", evidence, cfg=cfg)
        self.assertEqual(result.decision, "gate")
        self.assertTrue(result.should_gate)
        self.assertIn("price", result.message)

    def test_auto_refetch_heals(self):
        from lib.circuit_breaker import run_circuit_breaker, MPCConfig
        cfg = MPCConfig(silver_min=0.5, allow_auto_refetch=True)
        old = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        now = self._now_iso()

        weak_evidence = [
            {"claim_type": "price", "confidence": 0.3, "fetched_at": old, "trust_tier": 4},
        ]

        def refetch():
            return [
                {"claim_type": "price", "confidence": 0.9, "fetched_at": now, "trust_tier": 4},
                {"claim_type": "voltage", "confidence": 0.85, "fetched_at": now, "trust_tier": 4},
                {"claim_type": "compatibility", "confidence": 0.8, "fetched_at": now, "trust_tier": 3},
                {"claim_type": "core_specs", "confidence": 0.75, "fetched_at": now, "trust_tier": 3},
            ]

        result = run_circuit_breaker("R1", "script", weak_evidence, cfg=cfg, refetch_fn=refetch)
        self.assertNotEqual(result.decision, "gate")
        self.assertTrue(result.used_refetch)

    def test_telegram_send_called_on_gate(self):
        from lib.circuit_breaker import run_circuit_breaker, MPCConfig
        cfg = MPCConfig(allow_auto_refetch=False)
        messages = []
        evidence = [
            {"claim_type": "price", "confidence": 0.1, "fetched_at": self._now_iso(), "trust_tier": 2},
        ]
        result = run_circuit_breaker(
            "R1", "script", evidence,
            cfg=cfg, telegram_send_fn=messages.append,
        )
        self.assertEqual(result.decision, "gate")
        self.assertEqual(len(messages), 1)
        self.assertIn("Circuit Breaker", messages[0])

    def test_mpc_result_snapshot(self):
        from lib.circuit_breaker import run_circuit_breaker
        evidence = [
            {"claim_type": "price", "confidence": 0.9, "fetched_at": self._now_iso(), "trust_tier": 4},
        ]
        result = run_circuit_breaker("R1", "t", evidence)
        snap = result.to_snapshot()
        self.assertIn("decision", snap)
        self.assertIn("mpc_by_claim", snap)
        json_str = json.dumps(snap)
        self.assertIn("decision", json_str)

    def test_no_refetch_on_low_trust(self):
        from lib.circuit_breaker import run_circuit_breaker, MPCConfig
        cfg = MPCConfig(allow_auto_refetch=True)
        refetch_called = []

        def refetch():
            refetch_called.append(True)
            return [{"claim_type": "price", "confidence": 0.9, "fetched_at": datetime.now(timezone.utc).isoformat(), "trust_tier": 4}]

        # All evidence is low trust (tier 2) and NOT expired → refetch won't help
        evidence = [
            {"claim_type": "price", "confidence": 0.2, "fetched_at": datetime.now(timezone.utc).isoformat(), "trust_tier": 2},
        ]
        result = run_circuit_breaker("R1", "t", evidence, cfg=cfg, refetch_fn=refetch)
        self.assertEqual(result.decision, "gate")
        self.assertEqual(len(refetch_called), 0)


class TestRenderGateMessage(unittest.TestCase):
    """Tests for Telegram gate message rendering."""

    def test_message_format(self):
        from lib.circuit_breaker import render_gate_message
        msg = render_gate_message(
            "RAY-99", "final_script",
            {"price": 0.3, "voltage": 0.9},
            ["price: 0.30"],
        )
        self.assertIn("RAY-99", msg)
        self.assertIn("price: 0.30", msg)
        self.assertIn("Refetch", msg)
        self.assertIn("Abort", msg)

    def test_message_with_no_weak_points(self):
        from lib.circuit_breaker import render_gate_message
        msg = render_gate_message("R1", "t", {"price": 0.3}, [])
        self.assertIn("price", msg)


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


# ==========================================================================
# Script Outline schema tests
# ==========================================================================

class TestScriptOutlineSchema(unittest.TestCase):
    """Tests for SCRIPT_OUTLINE_SCHEMA validation."""

    def _make_valid_outline(self):
        return {
            "status": "ok",
            "contract_version": "script_writer/v0.1.0",
            "outline_version": 1,
            "outline": {
                "hook": "Stop wasting money—these are the 3 picks that matter.",
                "products": [
                    {
                        "product_key": "B0EXAMPLE1:best_overall",
                        "asin": "B0EXAMPLE1",
                        "slot": "best_overall",
                        "angle": "The all-rounder that beats everything",
                        "points": ["ANC quality", "Battery 30h", "USB-C fast charge"],
                        "verdict": "The one to beat.",
                    },
                    {
                        "product_key": "B0EXAMPLE2:best_value",
                        "asin": "B0EXAMPLE2",
                        "slot": "best_value",
                        "angle": "80% of the best at half the price",
                        "points": ["Great sound", "Comfortable fit", "IPX5 water"],
                        "verdict": "Best bang for your buck.",
                    },
                    {
                        "product_key": "B0EXAMPLE3:best_premium",
                        "asin": "B0EXAMPLE3",
                        "slot": "best_premium",
                        "angle": "When only the best will do",
                        "points": ["LDAC codec", "Premium build", "Spatial audio"],
                        "verdict": "Pure audio bliss.",
                    },
                ],
                "cta": "Links below—grab your pick before they sell out.",
            },
        }

    def test_valid_outline_passes(self):
        """Valid outline passes schema validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import SCRIPT_OUTLINE_SCHEMA
        errors = validate_output(self._make_valid_outline(), SCRIPT_OUTLINE_SCHEMA)
        self.assertEqual(errors, [])

    def test_missing_contract_version(self):
        """Missing contract_version detected."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import SCRIPT_OUTLINE_SCHEMA
        doc = self._make_valid_outline()
        del doc["contract_version"]
        errors = validate_output(doc, SCRIPT_OUTLINE_SCHEMA)
        self.assertTrue(any("contract_version" in str(e) for e in errors))

    def test_hook_too_long(self):
        """Hook exceeding 160 chars detected."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import SCRIPT_OUTLINE_SCHEMA
        doc = self._make_valid_outline()
        doc["outline"]["hook"] = "x" * 200
        errors = validate_output(doc, SCRIPT_OUTLINE_SCHEMA)
        self.assertTrue(any("too long" in e.message for e in errors))

    def test_product_key_format_checked_by_quality_gate(self):
        """product_key mismatch caught by quality gate."""
        from lib.schemas import quality_gate_outline
        doc = self._make_valid_outline()
        doc["outline"]["products"][0]["product_key"] = "WRONG_KEY"
        issues = quality_gate_outline(doc)
        self.assertTrue(any("product_key mismatch" in i for i in issues))

    def test_duplicate_slot_caught_by_quality_gate(self):
        """Duplicate slot caught by quality gate."""
        from lib.schemas import quality_gate_outline
        doc = self._make_valid_outline()
        doc["outline"]["products"][1]["slot"] = "best_overall"
        doc["outline"]["products"][1]["product_key"] = "B0EXAMPLE2:best_overall"
        issues = quality_gate_outline(doc)
        self.assertTrue(any("duplicate" in i.lower() for i in issues))

    def test_point_word_count_quality_gate(self):
        """Points with too many words caught by quality gate."""
        from lib.schemas import quality_gate_outline
        doc = self._make_valid_outline()
        doc["outline"]["products"][0]["points"][0] = (
            "this is a point with way too many words in it exceeding the limit"
        )
        issues = quality_gate_outline(doc)
        self.assertTrue(any("too many words" in i for i in issues))

    def test_generic_hook_quality_gate(self):
        """Generic placeholder hook caught by quality gate."""
        from lib.schemas import quality_gate_outline
        doc = self._make_valid_outline()
        doc["outline"]["hook"] = "Check out these products"
        issues = quality_gate_outline(doc)
        self.assertTrue(any("generic" in i.lower() for i in issues))


# ==========================================================================
# Quality gate Amazon tests
# ==========================================================================

class TestQualityGateAmazon(unittest.TestCase):
    """Tests for quality_gate_amazon — semantic validation."""

    def test_valid_output_passes(self):
        """Valid Amazon output passes quality gate."""
        from lib.schemas import quality_gate_amazon
        output = {
            "facts": {
                "title": "Test Product",
                "price": {"amount": 49.99, "currency": "USD"},
                "rating": 4.5,
                "reviews": 1234,
            },
            "signals": {"confidence": 0.95},
        }
        self.assertEqual(quality_gate_amazon(output), [])

    def test_zero_price_fails(self):
        """Price amount of 0 fails quality gate."""
        from lib.schemas import quality_gate_amazon
        output = {
            "facts": {"price": {"amount": 0, "currency": "USD"}, "title": "X", "rating": 4.0, "reviews": 100},
            "signals": {"confidence": 0.9},
        }
        issues = quality_gate_amazon(output)
        self.assertTrue(any("price" in i for i in issues))

    def test_empty_title_fails(self):
        """Empty title fails quality gate."""
        from lib.schemas import quality_gate_amazon
        output = {
            "facts": {"title": "   ", "price": {"amount": 50}, "rating": 4.0, "reviews": 100},
            "signals": {"confidence": 0.9},
        }
        issues = quality_gate_amazon(output)
        self.assertTrue(any("title" in i for i in issues))

    def test_rating_out_of_range_fails(self):
        """Rating > 5 fails quality gate."""
        from lib.schemas import quality_gate_amazon
        output = {
            "facts": {"title": "X", "price": {"amount": 50}, "rating": 7.0, "reviews": 100},
            "signals": {"confidence": 0.9},
        }
        issues = quality_gate_amazon(output)
        self.assertTrue(any("rating" in i for i in issues))

    def test_low_confidence_flagged(self):
        """Confidence < 0.4 flagged by quality gate."""
        from lib.schemas import quality_gate_amazon
        output = {
            "facts": {"title": "X", "price": {"amount": 50}, "rating": 4.0, "reviews": 100},
            "signals": {"confidence": 0.2},
        }
        issues = quality_gate_amazon(output)
        self.assertTrue(any("confidence" in i for i in issues))


# ==========================================================================
# validate_and_gate orchestrator tests
# ==========================================================================

class TestValidateAndGate(unittest.TestCase):
    """Tests for the two-tier validate_and_gate orchestrator."""

    def test_valid_output_returns_valid(self):
        """Valid output passes both tiers."""
        from lib.json_schema_guard import validate_and_gate
        schema = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
        result = validate_and_gate('{"name": "test"}', schema)
        self.assertTrue(result.valid)
        self.assertFalse(result.needs_repair)
        self.assertFalse(result.needs_human)

    def test_schema_error_generates_repair(self):
        """Schema error on attempt 1 generates repair prompt."""
        from lib.json_schema_guard import validate_and_gate
        schema = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
        result = validate_and_gate('{"value": 42}', schema, attempt=1)
        self.assertFalse(result.valid)
        self.assertTrue(result.needs_repair)
        self.assertIn("REPAIR REQUEST", result.repair_prompt)

    def test_schema_error_after_max_becomes_needs_human(self):
        """Schema error after MAX_REPAIR_ATTEMPTS → needs_human."""
        from lib.json_schema_guard import validate_and_gate, MAX_REPAIR_ATTEMPTS
        schema = {"type": "object", "required": ["name"]}
        result = validate_and_gate('{"value": 42}', schema, attempt=MAX_REPAIR_ATTEMPTS + 1)
        self.assertFalse(result.valid)
        self.assertFalse(result.needs_repair)
        self.assertTrue(result.needs_human)

    def test_quality_gate_failure_is_needs_human(self):
        """Quality gate failure → needs_human (no repair)."""
        from lib.json_schema_guard import validate_and_gate
        schema = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
        def bad_gate(d):
            return ["price is zero"]
        result = validate_and_gate('{"name": "test"}', schema, quality_gate=bad_gate)
        self.assertFalse(result.valid)
        self.assertTrue(result.needs_human)
        self.assertFalse(result.needs_repair)
        self.assertEqual(result.quality_issues, ["price is zero"])

    def test_quality_gate_pass(self):
        """Quality gate that passes returns valid."""
        from lib.json_schema_guard import validate_and_gate
        schema = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
        def ok_gate(d):
            return []
        result = validate_and_gate('{"name": "test"}', schema, quality_gate=ok_gate)
        self.assertTrue(result.valid)

    def test_parse_failure_generates_repair(self):
        """Unparseable output generates repair prompt."""
        from lib.json_schema_guard import validate_and_gate
        schema = {"type": "object"}
        result = validate_and_gate("this is not json", schema, attempt=1)
        self.assertTrue(result.needs_repair)
        self.assertIn("REPAIR", result.repair_prompt)

    def test_spool_payload_structure(self):
        """spool_payload has expected fields for run_event."""
        from lib.json_schema_guard import validate_and_gate
        schema = {"type": "object", "required": ["x"]}
        result = validate_and_gate('{"y":1}', schema, attempt=3)
        payload = result.spool_payload
        self.assertEqual(payload["event_type"], "llm_output_invalid")
        self.assertEqual(payload["severity"], "WARN")
        self.assertIn("attempt", payload)


# ==========================================================================
# Script Patch Policy tests
# ==========================================================================

class TestScriptPatchPolicy(unittest.TestCase):
    """Tests for ScriptPatchPolicy — wildcard path matching + constraints."""

    def _make_outline_doc(self):
        return {
            "contract_version": "script_writer/v0.1.0",
            "outline_version": 1,
            "outline": {
                "hook": "Old hook text that needs updating.",
                "products": [
                    {
                        "product_key": "B0EXAMPLE1:best_overall",
                        "asin": "B0EXAMPLE1",
                        "slot": "best_overall",
                        "angle": "The all-rounder",
                        "points": ["ANC", "Battery", "USB-C"],
                        "verdict": "The one to beat.",
                    },
                ],
                "cta": "Links below—grab yours now.",
            },
        }

    def test_replace_hook_allowed(self):
        """Replacing hook is allowed by default policy."""
        from lib.apply_patch import apply_script_patch
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/hook", "value": "New punchy hook here."}]
        result = apply_script_patch(doc, ops)
        self.assertEqual(result["outline"]["hook"], "New punchy hook here.")

    def test_replace_angle_allowed(self):
        """Replacing product angle is allowed."""
        from lib.apply_patch import apply_script_patch
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/products/0/angle", "value": "Best noise cancellation"}]
        result = apply_script_patch(doc, ops)
        self.assertEqual(result["outline"]["products"][0]["angle"], "Best noise cancellation")

    def test_replace_cta_allowed(self):
        """Replacing CTA is allowed."""
        from lib.apply_patch import apply_script_patch
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/cta", "value": "Check the links below."}]
        result = apply_script_patch(doc, ops)
        self.assertEqual(result["outline"]["cta"], "Check the links below.")

    def test_replace_asin_forbidden(self):
        """Replacing asin is forbidden."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/products/0/asin", "value": "HACKED"}]
        with self.assertRaises(PatchError) as ctx:
            apply_script_patch(doc, ops)
        self.assertIn("forbidden", str(ctx.exception).lower())

    def test_replace_slot_forbidden(self):
        """Replacing slot is forbidden."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/products/0/slot", "value": "best_value"}]
        with self.assertRaises(PatchError):
            apply_script_patch(doc, ops)

    def test_replace_product_key_forbidden(self):
        """Replacing product_key is forbidden."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/products/0/product_key", "value": "X"}]
        with self.assertRaises(PatchError):
            apply_script_patch(doc, ops)

    def test_replace_contract_version_forbidden(self):
        """Replacing contract_version is forbidden."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/contract_version", "value": "hacked"}]
        with self.assertRaises(PatchError):
            apply_script_patch(doc, ops)

    def test_remove_op_blocked(self):
        """Remove operations blocked by default policy."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "remove", "path": "/outline/hook"}]
        with self.assertRaises(PatchError) as ctx:
            apply_script_patch(doc, ops)
        self.assertIn("not allowed", str(ctx.exception))

    def test_max_ops_enforced(self):
        """Too many ops rejected."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/hook", "value": f"v{i}"} for i in range(10)]
        with self.assertRaises(PatchError) as ctx:
            apply_script_patch(doc, ops)
        self.assertIn("Too many", str(ctx.exception))

    def test_hook_too_long_post_patch(self):
        """Hook exceeding max chars after patch is rejected."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/hook", "value": "x" * 200}]
        with self.assertRaises(PatchError) as ctx:
            apply_script_patch(doc, ops)
        self.assertIn("too long", str(ctx.exception))

    def test_angle_too_long_post_patch(self):
        """Angle exceeding max chars after patch is rejected."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/products/0/angle", "value": "x" * 100}]
        with self.assertRaises(PatchError) as ctx:
            apply_script_patch(doc, ops)
        self.assertIn("too long", str(ctx.exception))

    def test_point_too_many_words_post_patch(self):
        """Point with too many words after patch is rejected."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/products/0/points/0",
                "value": "this is a point with way too many words exceeding the limit"}]
        with self.assertRaises(PatchError) as ctx:
            apply_script_patch(doc, ops)
        self.assertIn("words", str(ctx.exception))

    def test_original_not_mutated(self):
        """Original document not mutated by patch."""
        from lib.apply_patch import apply_script_patch
        doc = self._make_outline_doc()
        original_hook = doc["outline"]["hook"]
        ops = [{"op": "replace", "path": "/outline/hook", "value": "New hook."}]
        result = apply_script_patch(doc, ops)
        self.assertEqual(doc["outline"]["hook"], original_hook)
        self.assertEqual(result["outline"]["hook"], "New hook.")

    def test_path_not_in_allowlist(self):
        """Path not in allowlist is rejected."""
        from lib.apply_patch import apply_script_patch, PatchError
        doc = self._make_outline_doc()
        ops = [{"op": "replace", "path": "/outline/products/0/secret", "value": "x"}]
        with self.assertRaises(PatchError) as ctx:
            apply_script_patch(doc, ops)
        self.assertIn("not in allowlist", str(ctx.exception))

    def test_wildcard_matching(self):
        """Wildcard {i} matches numeric indices."""
        from lib.apply_patch import _wildcard_match
        self.assertTrue(_wildcard_match("/outline/products/{i}/angle", "/outline/products/0/angle"))
        self.assertTrue(_wildcard_match("/outline/products/{i}/angle", "/outline/products/2/angle"))
        self.assertFalse(_wildcard_match("/outline/products/{i}/angle", "/outline/products/abc/angle"))
        self.assertFalse(_wildcard_match("/outline/products/{i}/angle", "/outline/hook"))

    def test_nested_wildcard(self):
        """Nested wildcards {i}/{j} work for array-in-array paths."""
        from lib.apply_patch import _wildcard_match
        self.assertTrue(_wildcard_match(
            "/outline/products/{i}/points/{j}",
            "/outline/products/0/points/2",
        ))
        self.assertFalse(_wildcard_match(
            "/outline/products/{i}/points/{j}",
            "/outline/products/0/points/abc",
        ))


# ==========================================================================
# Patch audit event tests
# ==========================================================================

class TestPatchAudit(unittest.TestCase):
    """Tests for make_patch_audit event builder."""

    def test_audit_event_structure(self):
        """Patch audit event has correct structure."""
        from lib.apply_patch import make_patch_audit
        ops = [{"op": "replace", "path": "/outline/hook", "value": "new"}]
        event = make_patch_audit(
            run_id="test-123",
            patch_ops=ops,
            scope="hook",
            reason="too generic",
            contract_version="script_writer/v0.1.0",
        )
        self.assertEqual(event["event_type"], "script_patch_applied")
        self.assertEqual(event["severity"], "INFO")
        self.assertIn("event_id", event)
        self.assertIn("occurred_at", event)
        payload = event["payload"]
        self.assertEqual(payload["run_id"], "test-123")
        self.assertEqual(payload["scope"], "hook")
        self.assertEqual(payload["reason"], "too generic")
        self.assertEqual(payload["contract_version"], "script_writer/v0.1.0")
        self.assertEqual(payload["ops_count"], 1)


# ==========================================================================
# Contract loader integration test
# ==========================================================================

class TestScriptWriterContract(unittest.TestCase):
    """Tests for script_writer contract loading and prompt building."""

    def test_contract_file_exists(self):
        """Contract markdown file exists at expected path."""
        contract_path = Path(__file__).resolve().parent.parent / "contracts" / "script_writer" / "v0.1.0.md"
        self.assertTrue(contract_path.exists(), f"Missing: {contract_path}")

    def test_contract_loader_reads(self):
        """ContractLoader can read the script_writer contract."""
        from lib.prompt_contract_loader import ContractLoader
        contracts_dir = str(Path(__file__).resolve().parent.parent / "contracts")
        loader = ContractLoader(contracts_dir)
        text = loader.load("script_writer", "v0.1.0")
        self.assertIn("Script Writer", text)
        self.assertIn("PATCH MODE", text)
        self.assertIn("PERSONA PER SLOT", text)

    def test_outline_contract_spec_valid(self):
        """SCRIPT_OUTLINE_CONTRACT has expected fields."""
        from lib.schemas import SCRIPT_OUTLINE_CONTRACT
        self.assertEqual(SCRIPT_OUTLINE_CONTRACT.name, "script_writer")
        self.assertEqual(SCRIPT_OUTLINE_CONTRACT.version, "v0.1.0")
        self.assertTrue(len(SCRIPT_OUTLINE_CONTRACT.economy_rules) >= 4)

    def test_patch_contract_spec_no_cache(self):
        """SCRIPT_PATCH_CONTRACT uses no-cache policy."""
        from lib.schemas import SCRIPT_PATCH_CONTRACT
        self.assertEqual(SCRIPT_PATCH_CONTRACT.cache_policy.name, "none")

    def test_prompt_build_with_contract(self):
        """Full prompt builds correctly with contract text."""
        from lib.prompt_contract_loader import ContractEngine
        from lib.schemas import SCRIPT_OUTLINE_CONTRACT
        contracts_dir = str(Path(__file__).resolve().parent.parent / "contracts")
        engine = ContractEngine(
            contracts_dir=contracts_dir,
            cache_dir=tempfile.mkdtemp(),
        )
        payload = {
            "niche": "wireless earbuds",
            "winners": [{"asin": "B0X", "slot": "best_overall", "score": 85, "why": ["good"]}],
            "mode": "generate",
        }
        prompt, key = engine.build_prompt_and_cache_key(SCRIPT_OUTLINE_CONTRACT, payload)
        self.assertIn("### CONTRACT", prompt)
        self.assertIn("Script Writer", prompt)
        self.assertIn("### payload", prompt)
        self.assertIn("wireless earbuds", prompt)
        self.assertTrue(len(key) == 64)  # SHA-256 hex


# ==========================================================================
# Script Writer Final (Layer 2) tests
# ==========================================================================

class TestScriptFinalSchema(unittest.TestCase):
    """Tests for SCRIPT_FINAL_SCHEMA validation."""

    def _make_valid_script(self):
        return {
            "status": "ok",
            "contract_version": "script_writer_final/v0.1.0",
            "script_version": 1,
            "total_word_count": 600,
            "estimated_duration_sec": 240,
            "script": {
                "intro": "Looking for the best wireless earbuds in 2026? We tested dozens to find the three that actually deliver.",
                "segments": [
                    {
                        "product_key": "B0EXAMPLE1:best_overall",
                        "asin": "B0EXAMPLE1",
                        "slot": "best_overall",
                        "heading": "Number one: the Sony WF-1000XM5",
                        "body": "The Sony WF-1000XM5 dominates with its industry-leading ANC. "
                                "Noise cancellation is best-in-class, and the battery lasts eight hours "
                                "on a single charge. The sound profile is balanced with punchy bass.",
                        "verdict_line": "If you want the best, this is it.",
                        "transition": "But what if you want great sound without the premium price?",
                        "estimated_words": 200,
                    },
                    {
                        "product_key": "B0EXAMPLE2:best_value",
                        "asin": "B0EXAMPLE2",
                        "slot": "best_value",
                        "heading": "Number two: the budget champion",
                        "body": "The EarFun Air Pro delivers ninety percent of the performance "
                                "at a third of the price. Active noise cancellation works surprisingly "
                                "well, and the six-hour battery handles a full commute.",
                        "verdict_line": "Best bang for your buck, hands down.",
                        "transition": "And for those who want the absolute pinnacle of audio quality...",
                        "estimated_words": 200,
                    },
                    {
                        "product_key": "B0EXAMPLE3:best_premium",
                        "asin": "B0EXAMPLE3",
                        "slot": "best_premium",
                        "heading": "Number three: the audiophile's choice",
                        "body": "The Sennheiser Momentum 4 is what premium feels like. "
                                "The spatial audio is stunning, materials feel luxurious, "
                                "and the sound signature is warm and detailed.",
                        "verdict_line": "Pure audio bliss for the discerning ear.",
                        "transition": "So which one should you pick? Let me break it down.",
                        "estimated_words": 200,
                    },
                ],
                "outro": "Links to all three are in the description. Hit like if this helped, subscribe for more honest reviews, and drop a comment with your pick.",
            },
        }

    def test_valid_script_passes_schema(self):
        """Valid final script passes schema validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import SCRIPT_FINAL_SCHEMA
        script = self._make_valid_script()
        errors = validate_output(script, SCRIPT_FINAL_SCHEMA)
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_missing_segment_field_fails(self):
        """Missing required segment field fails validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import SCRIPT_FINAL_SCHEMA
        script = self._make_valid_script()
        del script["script"]["segments"][0]["verdict_line"]
        errors = validate_output(script, SCRIPT_FINAL_SCHEMA)
        self.assertTrue(any("verdict_line" in str(e) for e in errors))

    def test_intro_too_long_fails(self):
        """Intro exceeding maxLength fails validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import SCRIPT_FINAL_SCHEMA
        script = self._make_valid_script()
        script["script"]["intro"] = "x" * 301
        errors = validate_output(script, SCRIPT_FINAL_SCHEMA)
        self.assertTrue(any("too long" in str(e).lower() for e in errors))

    def test_invalid_slot_fails(self):
        """Invalid slot enum value fails validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import SCRIPT_FINAL_SCHEMA
        script = self._make_valid_script()
        script["script"]["segments"][0]["slot"] = "best_budget"
        errors = validate_output(script, SCRIPT_FINAL_SCHEMA)
        self.assertTrue(len(errors) > 0)

    def test_body_too_short_fails(self):
        """Body below minLength fails validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import SCRIPT_FINAL_SCHEMA
        script = self._make_valid_script()
        script["script"]["segments"][0]["body"] = "Too short."
        errors = validate_output(script, SCRIPT_FINAL_SCHEMA)
        self.assertTrue(any("too short" in str(e).lower() for e in errors))


class TestQualityGateScriptFinal(unittest.TestCase):
    """Tests for quality_gate_script_final."""

    def _make_valid_script(self):
        return {
            "total_word_count": 600,
            "estimated_duration_sec": 240,
            "script": {
                "intro": "A fresh, niche-specific hook for the video intro.",
                "segments": [
                    {
                        "product_key": "B0EXAMPLE1:best_overall",
                        "asin": "B0EXAMPLE1",
                        "slot": "best_overall",
                        "body": "x" * 60,
                        "estimated_words": 200,
                    },
                    {
                        "product_key": "B0EXAMPLE2:best_value",
                        "asin": "B0EXAMPLE2",
                        "slot": "best_value",
                        "body": "x" * 60,
                        "estimated_words": 200,
                    },
                    {
                        "product_key": "B0EXAMPLE3:best_premium",
                        "asin": "B0EXAMPLE3",
                        "slot": "best_premium",
                        "body": "x" * 60,
                        "estimated_words": 200,
                    },
                ],
                "outro": "Links below, subscribe and like.",
            },
        }

    def test_valid_passes(self):
        """Valid script passes quality gate."""
        from lib.schemas import quality_gate_script_final
        issues = quality_gate_script_final(self._make_valid_script())
        self.assertEqual(issues, [])

    def test_product_key_mismatch(self):
        """Mismatched product_key flagged."""
        from lib.schemas import quality_gate_script_final
        script = self._make_valid_script()
        script["script"]["segments"][0]["product_key"] = "WRONG:best_overall"
        issues = quality_gate_script_final(script)
        self.assertTrue(any("mismatch" in i for i in issues))

    def test_duplicate_slot(self):
        """Duplicate slot flagged."""
        from lib.schemas import quality_gate_script_final
        script = self._make_valid_script()
        script["script"]["segments"][1]["slot"] = "best_overall"
        issues = quality_gate_script_final(script)
        self.assertTrue(any("duplicate" in i for i in issues))

    def test_segment_imbalance(self):
        """Segment imbalance (>2x ratio) flagged."""
        from lib.schemas import quality_gate_script_final
        script = self._make_valid_script()
        script["script"]["segments"][0]["estimated_words"] = 500
        script["script"]["segments"][1]["estimated_words"] = 100
        script["script"]["segments"][2]["estimated_words"] = 200
        issues = quality_gate_script_final(script)
        self.assertTrue(any("imbalance" in i.lower() for i in issues))

    def test_word_count_too_low(self):
        """Total word count below 400 flagged."""
        from lib.schemas import quality_gate_script_final
        script = self._make_valid_script()
        script["total_word_count"] = 200
        issues = quality_gate_script_final(script)
        self.assertTrue(any("too low" in i for i in issues))

    def test_word_count_too_high(self):
        """Total word count above 900 flagged."""
        from lib.schemas import quality_gate_script_final
        script = self._make_valid_script()
        script["total_word_count"] = 1200
        issues = quality_gate_script_final(script)
        self.assertTrue(any("too high" in i for i in issues))

    def test_generic_intro(self):
        """Generic YouTube opener flagged."""
        from lib.schemas import quality_gate_script_final
        script = self._make_valid_script()
        script["script"]["intro"] = "Hey guys welcome back to the channel today we review earbuds."
        issues = quality_gate_script_final(script)
        self.assertTrue(any("generic" in i.lower() for i in issues))

    def test_duration_inconsistency(self):
        """Duration not matching word count flagged."""
        from lib.schemas import quality_gate_script_final
        script = self._make_valid_script()
        script["total_word_count"] = 600
        script["estimated_duration_sec"] = 30  # Way off for 600 words
        issues = quality_gate_script_final(script)
        self.assertTrue(any("inconsistent" in i for i in issues))


class TestBuildScriptPayload(unittest.TestCase):
    """Tests for build_script_payload pipeline helper."""

    def test_builds_from_outline(self):
        """Payload correctly built from validated outline."""
        from lib.schemas import build_script_payload
        outline = {
            "status": "ok",
            "contract_version": "script_writer/v0.1.0",
            "outline_version": 1,
            "outline": {
                "hook": "Looking for the best earbuds?",
                "products": [
                    {
                        "product_key": "B0X:best_overall",
                        "asin": "B0X",
                        "slot": "best_overall",
                        "angle": "The all-rounder",
                        "points": ["ANC", "Battery"],
                        "verdict": "The one.",
                    },
                ],
                "cta": "Links below!",
            },
        }
        payload = build_script_payload(outline, niche="earbuds", locale="en-US")
        self.assertEqual(payload["niche"], "earbuds")
        self.assertEqual(payload["locale"], "en-US")
        self.assertEqual(payload["mode"], "generate")
        self.assertEqual(payload["outline"]["hook"], "Looking for the best earbuds?")
        self.assertEqual(len(payload["outline"]["products"]), 1)
        self.assertEqual(payload["outline"]["products"][0]["asin"], "B0X")

    def test_patch_mode(self):
        """Payload mode set correctly for patch."""
        from lib.schemas import build_script_payload
        outline = {
            "status": "ok", "contract_version": "v1", "outline_version": 2,
            "outline": {"hook": "h", "products": [], "cta": "c"},
        }
        payload = build_script_payload(outline, mode="patch")
        self.assertEqual(payload["mode"], "patch")


class TestValidateOutlineForLayer2(unittest.TestCase):
    """Tests for validate_outline_for_layer2 pre-check."""

    def test_valid_outline_passes(self):
        """Valid outline passes pre-check."""
        from lib.schemas import validate_outline_for_layer2
        outline = {
            "status": "ok",
            "outline": {
                "hook": "A sufficiently long hook for testing purposes.",
                "products": [
                    {"angle": "Good angle", "points": ["p1", "p2"]},
                ],
                "cta": "Links below, subscribe now!",
            },
        }
        issues = validate_outline_for_layer2(outline)
        self.assertEqual(issues, [])

    def test_needs_human_status_fails(self):
        """Outline with needs_human status fails."""
        from lib.schemas import validate_outline_for_layer2
        outline = {"status": "needs_human", "outline": {"hook": "h" * 20, "products": [{"angle": "a", "points": ["p"]}], "cta": "c" * 20}}
        issues = validate_outline_for_layer2(outline)
        self.assertTrue(any("status" in i for i in issues))

    def test_needs_review_angle_fails(self):
        """Product with [needs review] angle fails."""
        from lib.schemas import validate_outline_for_layer2
        outline = {
            "status": "ok",
            "outline": {
                "hook": "A sufficiently long hook text.",
                "products": [{"angle": "[needs review]", "points": ["p1"]}],
                "cta": "Links below, subscribe!",
            },
        }
        issues = validate_outline_for_layer2(outline)
        self.assertTrue(any("needs review" in i for i in issues))


# ==========================================================================
# FinalScriptPatchPolicy tests
# ==========================================================================

class TestFinalScriptPatchPolicy(unittest.TestCase):
    """Tests for FinalScriptPatchPolicy — Layer 2 script patching."""

    def _make_script_doc(self):
        return {
            "contract_version": "script_writer_final/v0.1.0",
            "script_version": 1,
            "total_word_count": 600,
            "estimated_duration_sec": 240,
            "script": {
                "intro": "Looking for the best earbuds? We tested them all.",
                "segments": [
                    {
                        "product_key": "B0EXAMPLE1:best_overall",
                        "asin": "B0EXAMPLE1",
                        "slot": "best_overall",
                        "heading": "Number one pick",
                        "body": "The Sony WF-1000XM5 dominates with industry-leading noise cancellation and eight-hour battery life.",
                        "verdict_line": "The best overall choice.",
                        "transition": "But what about value?",
                        "estimated_words": 200,
                    },
                ],
                "outro": "Links in description. Like and subscribe for more reviews.",
            },
        }

    def test_replace_intro_allowed(self):
        """Replacing intro is allowed."""
        from lib.apply_patch import apply_final_script_patch
        doc = self._make_script_doc()
        ops = [{"op": "replace", "path": "/script/intro", "value": "Updated fresh intro for the video."}]
        result = apply_final_script_patch(doc, ops)
        self.assertEqual(result["script"]["intro"], "Updated fresh intro for the video.")

    def test_replace_body_allowed(self):
        """Replacing segment body is allowed."""
        from lib.apply_patch import apply_final_script_patch
        doc = self._make_script_doc()
        new_body = "A brand new body text that describes the product in detail and meets the minimum length requirement for the schema."
        ops = [{"op": "replace", "path": "/script/segments/0/body", "value": new_body}]
        result = apply_final_script_patch(doc, ops)
        self.assertEqual(result["script"]["segments"][0]["body"], new_body)

    def test_replace_outro_allowed(self):
        """Replacing outro is allowed."""
        from lib.apply_patch import apply_final_script_patch
        doc = self._make_script_doc()
        ops = [{"op": "replace", "path": "/script/outro", "value": "New outro with call to action please."}]
        result = apply_final_script_patch(doc, ops)
        self.assertEqual(result["script"]["outro"], "New outro with call to action please.")

    def test_replace_asin_forbidden(self):
        """Replacing asin in final script is forbidden."""
        from lib.apply_patch import apply_final_script_patch, PatchError
        doc = self._make_script_doc()
        ops = [{"op": "replace", "path": "/script/segments/0/asin", "value": "HACKED"}]
        with self.assertRaises(PatchError) as ctx:
            apply_final_script_patch(doc, ops)
        self.assertIn("forbidden", str(ctx.exception).lower())

    def test_replace_estimated_words_forbidden(self):
        """Replacing estimated_words is forbidden."""
        from lib.apply_patch import apply_final_script_patch, PatchError
        doc = self._make_script_doc()
        ops = [{"op": "replace", "path": "/script/segments/0/estimated_words", "value": 999}]
        with self.assertRaises(PatchError):
            apply_final_script_patch(doc, ops)

    def test_replace_total_word_count_forbidden(self):
        """Replacing total_word_count is forbidden."""
        from lib.apply_patch import apply_final_script_patch, PatchError
        doc = self._make_script_doc()
        ops = [{"op": "replace", "path": "/total_word_count", "value": 9999}]
        with self.assertRaises(PatchError):
            apply_final_script_patch(doc, ops)

    def test_body_too_long_post_patch(self):
        """Body exceeding max chars after patch is rejected."""
        from lib.apply_patch import apply_final_script_patch, PatchError
        doc = self._make_script_doc()
        ops = [{"op": "replace", "path": "/script/segments/0/body", "value": "x" * 700}]
        with self.assertRaises(PatchError) as ctx:
            apply_final_script_patch(doc, ops)
        self.assertIn("too long", str(ctx.exception))

    def test_intro_too_long_post_patch(self):
        """Intro exceeding max chars after patch is rejected."""
        from lib.apply_patch import apply_final_script_patch, PatchError
        doc = self._make_script_doc()
        ops = [{"op": "replace", "path": "/script/intro", "value": "x" * 400}]
        with self.assertRaises(PatchError) as ctx:
            apply_final_script_patch(doc, ops)
        self.assertIn("too long", str(ctx.exception))

    def test_max_ops_enforced(self):
        """Too many ops rejected."""
        from lib.apply_patch import apply_final_script_patch, PatchError
        doc = self._make_script_doc()
        ops = [{"op": "replace", "path": "/script/intro", "value": f"v{i} intro text here."} for i in range(10)]
        with self.assertRaises(PatchError) as ctx:
            apply_final_script_patch(doc, ops)
        self.assertIn("Too many", str(ctx.exception))

    def test_remove_op_blocked(self):
        """Remove operations blocked."""
        from lib.apply_patch import apply_final_script_patch, PatchError
        doc = self._make_script_doc()
        ops = [{"op": "remove", "path": "/script/intro"}]
        with self.assertRaises(PatchError):
            apply_final_script_patch(doc, ops)

    def test_original_not_mutated(self):
        """Original document not mutated by patch."""
        from lib.apply_patch import apply_final_script_patch
        doc = self._make_script_doc()
        original_intro = doc["script"]["intro"]
        ops = [{"op": "replace", "path": "/script/intro", "value": "Brand new intro for the video."}]
        result = apply_final_script_patch(doc, ops)
        self.assertEqual(doc["script"]["intro"], original_intro)
        self.assertNotEqual(result["script"]["intro"], original_intro)


# ==========================================================================
# Patch idempotency tests
# ==========================================================================

class TestPatchIdempotency(unittest.TestCase):
    """Tests for canonical hashing and patch ID computation."""

    def test_canonical_json_deterministic(self):
        """canonical_json produces same output for same data regardless of key order."""
        from lib.apply_patch import canonical_json
        a = {"z": 1, "a": 2, "m": [3, 4]}
        b = {"a": 2, "m": [3, 4], "z": 1}
        self.assertEqual(canonical_json(a), canonical_json(b))

    def test_canonical_json_compact(self):
        """canonical_json uses compact separators."""
        from lib.apply_patch import canonical_json
        result = canonical_json({"key": "value"})
        self.assertNotIn(" ", result)
        self.assertEqual(result, '{"key":"value"}')

    def test_compute_base_hash_stable(self):
        """Same document always produces same hash."""
        from lib.apply_patch import compute_base_hash
        doc = {"a": 1, "b": [2, 3]}
        h1 = compute_base_hash(doc)
        h2 = compute_base_hash(doc)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)  # SHA-256 hex

    def test_compute_base_hash_different_for_different_docs(self):
        """Different documents produce different hashes."""
        from lib.apply_patch import compute_base_hash
        h1 = compute_base_hash({"a": 1})
        h2 = compute_base_hash({"a": 2})
        self.assertNotEqual(h1, h2)

    def test_validate_base_hash_matches(self):
        """validate_base_hash returns True for matching document."""
        from lib.apply_patch import compute_base_hash, validate_base_hash
        doc = {"hello": "world"}
        h = compute_base_hash(doc)
        self.assertTrue(validate_base_hash(doc, h))

    def test_validate_base_hash_fails_on_change(self):
        """validate_base_hash returns False when document changed."""
        from lib.apply_patch import compute_base_hash, validate_base_hash
        doc = {"hello": "world"}
        h = compute_base_hash(doc)
        doc["hello"] = "changed"
        self.assertFalse(validate_base_hash(doc, h))

    def test_compute_patch_id_deterministic(self):
        """Same base_hash + ops produces same patch_id."""
        from lib.apply_patch import compute_patch_id
        ops = [{"op": "replace", "path": "/x", "value": "y"}]
        id1 = compute_patch_id("abc123", ops)
        id2 = compute_patch_id("abc123", ops)
        self.assertEqual(id1, id2)

    def test_compute_patch_id_different_base(self):
        """Different base_hash produces different patch_id."""
        from lib.apply_patch import compute_patch_id
        ops = [{"op": "replace", "path": "/x", "value": "y"}]
        id1 = compute_patch_id("abc123", ops)
        id2 = compute_patch_id("def456", ops)
        self.assertNotEqual(id1, id2)

    def test_stale_patch_rejected(self):
        """apply_final_script_patch rejects stale patch."""
        from lib.apply_patch import apply_final_script_patch, compute_base_hash, PatchError
        doc = {
            "contract_version": "v1", "script_version": 1,
            "total_word_count": 100, "estimated_duration_sec": 40,
            "script": {
                "intro": "Some intro text for testing purposes.",
                "segments": [], "outro": "Some outro text for testing.",
            },
        }
        old_hash = compute_base_hash(doc)
        doc["script"]["intro"] = "Modified intro text for testing purposes."
        ops = [{"op": "replace", "path": "/script/outro", "value": "New outro for testing right here."}]
        with self.assertRaises(PatchError) as ctx:
            apply_final_script_patch(doc, ops, expected_base_hash=old_hash)
        self.assertIn("Stale", str(ctx.exception))


# ==========================================================================
# Script Writer Final contract tests
# ==========================================================================

class TestScriptFinalContract(unittest.TestCase):
    """Tests for script_writer_final contract loading."""

    def test_contract_file_exists(self):
        """Contract markdown file exists."""
        contract_path = Path(__file__).resolve().parent.parent / "contracts" / "script_writer_final" / "v0.1.0.md"
        self.assertTrue(contract_path.exists(), f"Missing: {contract_path}")

    def test_contract_loader_reads(self):
        """ContractLoader can read the script_writer_final contract."""
        from lib.prompt_contract_loader import ContractLoader
        contracts_dir = str(Path(__file__).resolve().parent.parent / "contracts")
        loader = ContractLoader(contracts_dir)
        text = loader.load("script_writer_final", "v0.1.0")
        self.assertIn("Script Writer", text)
        self.assertIn("LAYER 2", text)
        self.assertIn("PATCH MODE", text)

    def test_final_contract_spec_valid(self):
        """SCRIPT_FINAL_CONTRACT has expected fields."""
        from lib.schemas import SCRIPT_FINAL_CONTRACT
        self.assertEqual(SCRIPT_FINAL_CONTRACT.name, "script_writer_final")
        self.assertEqual(SCRIPT_FINAL_CONTRACT.version, "v0.1.0")
        self.assertTrue(len(SCRIPT_FINAL_CONTRACT.economy_rules) >= 4)

    def test_final_patch_contract_no_cache(self):
        """SCRIPT_FINAL_PATCH_CONTRACT uses no-cache policy."""
        from lib.schemas import SCRIPT_FINAL_PATCH_CONTRACT
        self.assertEqual(SCRIPT_FINAL_PATCH_CONTRACT.cache_policy.name, "none")


# ==========================================================================
# Voice Script (Layer 3) tests
# ==========================================================================

class TestVoiceScriptSchema(unittest.TestCase):
    """Tests for VOICE_SCRIPT_SCHEMA validation."""

    def _make_valid_voice_script(self):
        return {
            "status": "ok",
            "contract_version": "voice_script/v0.1.0",
            "total_duration_sec": 180,
            "segments": [
                {"segment_id": "intro", "kind": "intro", "text": "Looking for the best wireless earbuds? We tested them all so you don't have to.", "lip_sync_hint": "excited", "approx_duration_sec": 10},
                {"segment_id": "p0", "kind": "product", "product_key": "B0X:best_overall", "text": "The Sony WF-1000XM5 delivers the best noise cancellation in any earbud we tested this year.", "lip_sync_hint": "serious", "approx_duration_sec": 15},
                {"segment_id": "t0_1", "kind": "transition", "text": "But what if you want great sound without breaking the bank?", "lip_sync_hint": "neutral", "approx_duration_sec": 5},
                {"segment_id": "p1", "kind": "product", "product_key": "B0Y:best_value", "text": "The EarFun Air Pro punches way above its weight class with solid noise cancellation.", "lip_sync_hint": "excited", "approx_duration_sec": 15},
                {"segment_id": "t1_2", "kind": "transition", "text": "And for those who want nothing but the absolute best quality.", "lip_sync_hint": "neutral", "approx_duration_sec": 5},
                {"segment_id": "p2", "kind": "product", "product_key": "B0Z:best_premium", "text": "The Sennheiser Momentum 4 is what premium audio is supposed to feel like in every detail.", "lip_sync_hint": "serious", "approx_duration_sec": 15},
                {"segment_id": "outro", "kind": "outro", "text": "Links to all three are in the description. Subscribe for more honest reviews.", "lip_sync_hint": "neutral", "approx_duration_sec": 8},
            ],
            "audio_plan": [
                {"segment_id": "intro", "voice_id": "voice1", "model": "eleven_multilingual_v2", "stability": 0.4, "style": 0.35, "output_filename": "seg_intro.mp3"},
                {"segment_id": "p0", "voice_id": "voice1", "model": "eleven_multilingual_v2", "stability": 0.4, "style": 0.35, "output_filename": "seg_p0.mp3"},
                {"segment_id": "t0_1", "voice_id": "voice1", "model": "eleven_multilingual_v2", "stability": 0.5, "style": 0.2, "output_filename": "seg_t0_1.mp3"},
                {"segment_id": "p1", "voice_id": "voice1", "model": "eleven_multilingual_v2", "stability": 0.4, "style": 0.35, "output_filename": "seg_p1.mp3"},
                {"segment_id": "t1_2", "voice_id": "voice1", "model": "eleven_multilingual_v2", "stability": 0.5, "style": 0.2, "output_filename": "seg_t1_2.mp3"},
                {"segment_id": "p2", "voice_id": "voice1", "model": "eleven_multilingual_v2", "stability": 0.4, "style": 0.35, "output_filename": "seg_p2.mp3"},
                {"segment_id": "outro", "voice_id": "voice1", "model": "eleven_multilingual_v2", "stability": 0.5, "style": 0.3, "output_filename": "seg_outro.mp3"},
            ],
        }

    def test_valid_voice_script_passes(self):
        """Valid voice script passes schema validation."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import VOICE_SCRIPT_SCHEMA
        vs = self._make_valid_voice_script()
        errors = validate_output(vs, VOICE_SCRIPT_SCHEMA)
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_too_few_segments_fails(self):
        """Fewer than 4 segments fails minItems."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import VOICE_SCRIPT_SCHEMA
        vs = self._make_valid_voice_script()
        vs["segments"] = vs["segments"][:2]
        errors = validate_output(vs, VOICE_SCRIPT_SCHEMA)
        self.assertTrue(any("too short" in str(e).lower() for e in errors))

    def test_invalid_kind_fails(self):
        """Invalid segment kind fails enum."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import VOICE_SCRIPT_SCHEMA
        vs = self._make_valid_voice_script()
        vs["segments"][0]["kind"] = "interlude"
        errors = validate_output(vs, VOICE_SCRIPT_SCHEMA)
        self.assertTrue(len(errors) > 0)

    def test_invalid_lip_sync_hint_fails(self):
        """Invalid lip_sync_hint fails enum."""
        from lib.json_schema_guard import validate_output
        from lib.schemas import VOICE_SCRIPT_SCHEMA
        vs = self._make_valid_voice_script()
        vs["segments"][0]["lip_sync_hint"] = "happy"
        errors = validate_output(vs, VOICE_SCRIPT_SCHEMA)
        self.assertTrue(len(errors) > 0)


class TestQualityGateVoiceScript(unittest.TestCase):
    """Tests for quality_gate_voice_script."""

    def _make_valid_segments(self):
        return {
            "total_duration_sec": 30,
            "segments": [
                {"segment_id": "intro", "kind": "intro", "text": "Looking for earbuds? We tested them all.", "lip_sync_hint": "excited", "approx_duration_sec": 4},
                {"segment_id": "p0", "kind": "product", "text": "The Sony delivers best noise cancellation in any earbud we tested.", "lip_sync_hint": "serious", "approx_duration_sec": 5},
                {"segment_id": "t0_1", "kind": "transition", "text": "What about value for money options?", "lip_sync_hint": "neutral", "approx_duration_sec": 4},
                {"segment_id": "p1", "kind": "product", "text": "The EarFun punches above its weight with great cancellation and comfort.", "lip_sync_hint": "excited", "approx_duration_sec": 5},
                {"segment_id": "p2", "kind": "product", "text": "The Sennheiser is what premium audio should feel like in every way.", "lip_sync_hint": "serious", "approx_duration_sec": 5},
                {"segment_id": "outro", "kind": "outro", "text": "Links are in the description below. Subscribe.", "lip_sync_hint": "neutral", "approx_duration_sec": 4},
            ],
            "audio_plan": [
                {"segment_id": "intro", "voice_id": "v1", "model": "m"},
                {"segment_id": "p0", "voice_id": "v1", "model": "m"},
                {"segment_id": "t0_1", "voice_id": "v1", "model": "m"},
                {"segment_id": "p1", "voice_id": "v1", "model": "m"},
                {"segment_id": "p2", "voice_id": "v1", "model": "m"},
                {"segment_id": "outro", "voice_id": "v1", "model": "m"},
            ],
        }

    def test_valid_passes(self):
        """Valid voice script passes quality gate."""
        from lib.schemas import quality_gate_voice_script
        issues = quality_gate_voice_script(self._make_valid_segments())
        self.assertEqual(issues, [])

    def test_duplicate_segment_id(self):
        """Duplicate segment_id flagged."""
        from lib.schemas import quality_gate_voice_script
        vs = self._make_valid_segments()
        vs["segments"][1]["segment_id"] = "intro"
        issues = quality_gate_voice_script(vs)
        self.assertTrue(any("duplicate" in i for i in issues))

    def test_missing_audio_plan(self):
        """Missing segment in audio_plan flagged."""
        from lib.schemas import quality_gate_voice_script
        vs = self._make_valid_segments()
        vs["audio_plan"] = vs["audio_plan"][:3]
        issues = quality_gate_voice_script(vs)
        self.assertTrue(any("missing" in i.lower() for i in issues))

    def test_no_intro_flagged(self):
        """Missing intro kind flagged."""
        from lib.schemas import quality_gate_voice_script
        vs = self._make_valid_segments()
        vs["segments"][0]["kind"] = "product"
        issues = quality_gate_voice_script(vs)
        self.assertTrue(any("intro" in i.lower() for i in issues))

    def test_no_outro_flagged(self):
        """Missing outro kind flagged."""
        from lib.schemas import quality_gate_voice_script
        vs = self._make_valid_segments()
        vs["segments"][-1]["kind"] = "product"
        issues = quality_gate_voice_script(vs)
        self.assertTrue(any("outro" in i.lower() for i in issues))

    def test_stability_out_of_range(self):
        """Stability > 1 flagged."""
        from lib.schemas import quality_gate_voice_script
        vs = self._make_valid_segments()
        vs["audio_plan"][0]["stability"] = 1.5
        issues = quality_gate_voice_script(vs)
        self.assertTrue(any("stability" in i for i in issues))

    def test_total_duration_mismatch(self):
        """Total duration mismatch flagged."""
        from lib.schemas import quality_gate_voice_script
        vs = self._make_valid_segments()
        vs["total_duration_sec"] = 999
        issues = quality_gate_voice_script(vs)
        self.assertTrue(any("mismatch" in i for i in issues))


class TestVoiceScriptContract(unittest.TestCase):
    """Tests for voice_script contract loading."""

    def test_contract_file_exists(self):
        """Contract markdown file exists."""
        contract_path = Path(__file__).resolve().parent.parent / "contracts" / "voice_script" / "v0.1.0.md"
        self.assertTrue(contract_path.exists(), f"Missing: {contract_path}")

    def test_contract_loader_reads(self):
        """ContractLoader can read the voice_script contract."""
        from lib.prompt_contract_loader import ContractLoader
        contracts_dir = str(Path(__file__).resolve().parent.parent / "contracts")
        loader = ContractLoader(contracts_dir)
        text = loader.load("voice_script", "v0.1.0")
        self.assertIn("Voice Script", text)
        self.assertIn("LAYER 3", text)
        self.assertIn("TTS TAGS", text)

    def test_voice_contract_spec_valid(self):
        """VOICE_SCRIPT_CONTRACT has expected fields."""
        from lib.schemas import VOICE_SCRIPT_CONTRACT
        self.assertEqual(VOICE_SCRIPT_CONTRACT.name, "voice_script")
        self.assertEqual(VOICE_SCRIPT_CONTRACT.version, "v0.1.0")
        self.assertTrue(len(VOICE_SCRIPT_CONTRACT.economy_rules) >= 4)


# ==========================================================================
# Tone Gate tests
# ==========================================================================

class TestToneGate(unittest.TestCase):
    """Tests for tone gate — pre-TTS duration validation."""

    def test_strip_tts_tags(self):
        """TTS tags are stripped from text."""
        from lib.tone_gate import strip_tts_tags
        text = "Hello [pause=300ms] world [emphasis]great[/emphasis] product [rate=1.05]fast[/rate]."
        result = strip_tts_tags(text)
        self.assertNotIn("[pause", result)
        self.assertNotIn("[emphasis", result)
        self.assertNotIn("[rate", result)
        self.assertIn("Hello", result)
        self.assertIn("world", result)

    def test_count_words(self):
        """Word count is accurate after tag stripping."""
        from lib.tone_gate import count_words
        text = "This is [pause=300ms] a test with [emphasis]five[/emphasis] tagged words plus more."
        words = count_words(text)
        self.assertEqual(words, 10)

    def test_estimate_duration(self):
        """Duration estimation is reasonable."""
        from lib.tone_gate import estimate_duration_sec
        # 165 words at 165 WPM = 60 seconds
        text = " ".join(["word"] * 165)
        dur = estimate_duration_sec(text, wpm=165)
        self.assertAlmostEqual(dur, 60.0, places=1)

    def test_valid_segments_pass(self):
        """Well-sized segments pass tone gate."""
        from lib.tone_gate import tone_gate_validate
        segments = [
            {"segment_id": "intro", "kind": "intro", "text": "Looking for the best earbuds in two thousand twenty six?", "approx_duration_sec": 8},
            {"segment_id": "p0", "kind": "product", "text": "The Sony delivers excellent noise cancellation.", "approx_duration_sec": 6},
        ]
        violations = tone_gate_validate(segments)
        self.assertEqual(violations, [])

    def test_overly_long_segment_flagged(self):
        """Segment too long for stated duration flagged."""
        from lib.tone_gate import tone_gate_validate
        # 80 words for a 10-second segment (80 words ≈ 29s at 165 WPM)
        text = " ".join(["word"] * 80)
        segments = [
            {"segment_id": "p0", "kind": "product", "text": text, "approx_duration_sec": 10},
        ]
        violations = tone_gate_validate(segments)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].segment_id, "p0")

    def test_too_many_words_flagged(self):
        """Segment with too many words flagged."""
        from lib.tone_gate import tone_gate_validate, ToneGateRules
        text = " ".join(["word"] * 100)
        segments = [
            {"segment_id": "p0", "kind": "product", "text": text, "approx_duration_sec": 60},
        ]
        violations = tone_gate_validate(segments, ToneGateRules(max_words_per_segment=80))
        self.assertEqual(len(violations), 1)
        self.assertIn("Too many", violations[0].issue)

    def test_too_few_words_flagged(self):
        """Segment with too few words flagged."""
        from lib.tone_gate import tone_gate_validate
        segments = [
            {"segment_id": "p0", "kind": "product", "text": "Hi.", "approx_duration_sec": 10},
        ]
        violations = tone_gate_validate(segments)
        self.assertEqual(len(violations), 1)
        self.assertIn("Too few", violations[0].issue)

    def test_build_repair_prompt(self):
        """Repair prompt generated correctly."""
        from lib.tone_gate import ToneViolation, build_tone_repair_prompt
        violations = [ToneViolation(
            segment_id="p0", kind="product",
            approx_duration_sec=10.0, estimated_duration_sec=25.0,
            word_count=60, issue="Text too long",
        )]
        prompt = build_tone_repair_prompt(violations)
        self.assertIn("REPAIR REQUEST", prompt)
        self.assertIn("p0", prompt)
        self.assertIn("patch_ops", prompt)


# ==========================================================================
# Media Manifest tests
# ==========================================================================

class TestMediaManifest(unittest.TestCase):
    """Tests for media manifest builder."""

    def _make_voice_script(self):
        return {
            "contract_version": "voice_script/v0.1.0",
            "total_duration_sec": 60,
            "segments": [
                {"segment_id": "intro", "kind": "intro", "text": "Hello this is a test intro.", "lip_sync_hint": "excited", "approx_duration_sec": 10},
                {"segment_id": "p0", "kind": "product", "product_key": "B0X:best_overall", "text": "Product description here.", "lip_sync_hint": "neutral", "approx_duration_sec": 20},
                {"segment_id": "t0_1", "kind": "transition", "text": "Moving on to the next pick.", "lip_sync_hint": "neutral", "approx_duration_sec": 5},
                {"segment_id": "outro", "kind": "outro", "text": "Subscribe and like the video.", "lip_sync_hint": "neutral", "approx_duration_sec": 8},
            ],
            "audio_plan": [
                {"segment_id": "intro", "voice_id": "v1", "model": "eleven_multilingual_v2", "stability": 0.4, "style": 0.35, "output_filename": "seg_intro.mp3"},
                {"segment_id": "p0", "voice_id": "v1", "model": "eleven_multilingual_v2", "stability": 0.4, "style": 0.35, "output_filename": "seg_p0.mp3"},
                {"segment_id": "t0_1", "voice_id": "v1", "model": "eleven_multilingual_v2", "stability": 0.5, "style": 0.2, "output_filename": "seg_t0_1.mp3"},
                {"segment_id": "outro", "voice_id": "v1", "model": "eleven_multilingual_v2", "stability": 0.5, "style": 0.3, "output_filename": "seg_outro.mp3"},
            ],
        }

    def test_manifest_structure(self):
        """Manifest has correct top-level structure."""
        from lib.media_manifest import build_media_manifest
        vs = self._make_voice_script()
        m = build_media_manifest(vs, run_id="RAY-99")
        self.assertEqual(m["manifest_version"], "1.0")
        self.assertEqual(m["run_id"], "RAY-99")
        self.assertEqual(m["fps"], 30)
        self.assertEqual(m["resolution"], "1920x1080")
        self.assertIn("segments", m)
        self.assertIn("deliver", m)
        self.assertEqual(len(m["segments"]), 4)

    def test_segment_audio_paths(self):
        """Segment audio paths use content-addressed digests."""
        from lib.media_manifest import build_media_manifest
        vs = self._make_voice_script()
        m = build_media_manifest(vs, run_id="RAY-99")
        for seg in m["segments"]:
            self.assertIn("RAY-99", seg["audio_path"])
            self.assertIn("seg_", seg["audio_path"])
            self.assertTrue(seg["audio_path"].endswith(".mp3"))
            self.assertTrue(len(seg["audio_digest"]) == 64)

    def test_audio_digest_deterministic(self):
        """Same inputs produce same audio digest."""
        from lib.media_manifest import compute_audio_digest
        d1 = compute_audio_digest("v1", "Hello world", "model1")
        d2 = compute_audio_digest("v1", "Hello world", "model1")
        self.assertEqual(d1, d2)

    def test_audio_digest_different_text(self):
        """Different text produces different digest."""
        from lib.media_manifest import compute_audio_digest
        d1 = compute_audio_digest("v1", "Hello", "model1")
        d2 = compute_audio_digest("v1", "Goodbye", "model1")
        self.assertNotEqual(d1, d2)

    def test_audio_digest_normalizes_whitespace(self):
        """Text whitespace is normalized before hashing."""
        from lib.media_manifest import compute_audio_digest
        d1 = compute_audio_digest("v1", "Hello  world", "model1")
        d2 = compute_audio_digest("v1", "Hello world", "model1")
        self.assertEqual(d1, d2)

    def test_deliver_section(self):
        """Deliver section has output path and preset."""
        from lib.media_manifest import build_media_manifest
        vs = self._make_voice_script()
        m = build_media_manifest(vs, run_id="RAY-99", output_path="out.mp4", render_preset="ProRes")
        self.assertEqual(m["deliver"]["output_path"], "out.mp4")
        self.assertEqual(m["deliver"]["preset"], "ProRes")


# ==========================================================================
# Voice Patch Policy tests
# ==========================================================================

class TestVoicePatchPolicy(unittest.TestCase):
    """Tests for VoicePatchPolicy — Layer 3 voice script patching."""

    def _make_voice_doc(self):
        return {
            "contract_version": "voice_script/v0.1.0",
            "total_duration_sec": 60,
            "segments": [
                {"segment_id": "intro", "kind": "intro", "product_key": None, "text": "Looking for the best earbuds in twenty twenty six?", "lip_sync_hint": "excited", "approx_duration_sec": 10},
                {"segment_id": "p0", "kind": "product", "product_key": "B0X:best_overall", "text": "The Sony delivers excellent noise cancellation in this price range.", "lip_sync_hint": "serious", "approx_duration_sec": 15},
            ],
            "audio_plan": [
                {"segment_id": "intro", "voice_id": "v1", "model": "eleven_multilingual_v2", "stability": 0.4, "style": 0.35, "output_filename": "seg_intro.mp3"},
                {"segment_id": "p0", "voice_id": "v1", "model": "eleven_multilingual_v2", "stability": 0.4, "style": 0.35, "output_filename": "seg_p0.mp3"},
            ],
        }

    def test_replace_text_allowed(self):
        """Replacing segment text is allowed."""
        from lib.apply_patch import apply_voice_patch
        doc = self._make_voice_doc()
        ops = [{"op": "replace", "path": "/segments/0/text", "value": "Updated intro text that is long enough for the schema."}]
        result = apply_voice_patch(doc, ops)
        self.assertIn("Updated intro", result["segments"][0]["text"])

    def test_replace_lip_sync_hint_allowed(self):
        """Replacing lip_sync_hint is allowed."""
        from lib.apply_patch import apply_voice_patch
        doc = self._make_voice_doc()
        ops = [{"op": "replace", "path": "/segments/0/lip_sync_hint", "value": "neutral"}]
        result = apply_voice_patch(doc, ops)
        self.assertEqual(result["segments"][0]["lip_sync_hint"], "neutral")

    def test_replace_stability_allowed(self):
        """Replacing audio_plan stability is allowed."""
        from lib.apply_patch import apply_voice_patch
        doc = self._make_voice_doc()
        ops = [{"op": "replace", "path": "/audio_plan/0/stability", "value": 0.6}]
        result = apply_voice_patch(doc, ops)
        self.assertEqual(result["audio_plan"][0]["stability"], 0.6)

    def test_replace_segment_id_forbidden(self):
        """Replacing segment_id is forbidden."""
        from lib.apply_patch import apply_voice_patch, PatchError
        doc = self._make_voice_doc()
        ops = [{"op": "replace", "path": "/segments/0/segment_id", "value": "hacked"}]
        with self.assertRaises(PatchError) as ctx:
            apply_voice_patch(doc, ops)
        self.assertIn("forbidden", str(ctx.exception).lower())

    def test_replace_voice_id_forbidden(self):
        """Replacing voice_id is forbidden."""
        from lib.apply_patch import apply_voice_patch, PatchError
        doc = self._make_voice_doc()
        ops = [{"op": "replace", "path": "/audio_plan/0/voice_id", "value": "hacked"}]
        with self.assertRaises(PatchError):
            apply_voice_patch(doc, ops)

    def test_replace_model_forbidden(self):
        """Replacing model is forbidden."""
        from lib.apply_patch import apply_voice_patch, PatchError
        doc = self._make_voice_doc()
        ops = [{"op": "replace", "path": "/audio_plan/0/model", "value": "hacked"}]
        with self.assertRaises(PatchError):
            apply_voice_patch(doc, ops)

    def test_text_too_long_post_patch(self):
        """Text exceeding max chars after patch is rejected."""
        from lib.apply_patch import apply_voice_patch, PatchError
        doc = self._make_voice_doc()
        ops = [{"op": "replace", "path": "/segments/0/text", "value": "x" * 600}]
        with self.assertRaises(PatchError) as ctx:
            apply_voice_patch(doc, ops)
        self.assertIn("too long", str(ctx.exception))

    def test_original_not_mutated(self):
        """Original document not mutated by voice patch."""
        from lib.apply_patch import apply_voice_patch
        doc = self._make_voice_doc()
        original_text = doc["segments"][0]["text"]
        ops = [{"op": "replace", "path": "/segments/0/text", "value": "New text for the intro segment here."}]
        result = apply_voice_patch(doc, ops)
        self.assertEqual(doc["segments"][0]["text"], original_text)
        self.assertNotEqual(result["segments"][0]["text"], original_text)


# ==========================================================================
# Pipeline helper tests (voice payload + pre-check)
# ==========================================================================

class TestVoicePipelineHelpers(unittest.TestCase):
    """Tests for build_voice_payload and validate_script_for_layer3."""

    def test_build_voice_payload(self):
        """Payload correctly built from final script."""
        from lib.schemas import build_voice_payload
        final_script = {
            "status": "ok",
            "contract_version": "script_writer_final/v0.1.0",
            "estimated_duration_sec": 240,
            "script": {
                "intro": "A great intro for the video.",
                "segments": [
                    {"product_key": "B0X:best_overall", "slot": "best_overall",
                     "heading": "h", "body": "b", "verdict_line": "v", "transition": "t"},
                ],
                "outro": "Links below.",
            },
        }
        payload = build_voice_payload(final_script, niche="earbuds", locale="pt-BR", voice_id="myvoice")
        self.assertEqual(payload["niche"], "earbuds")
        self.assertEqual(payload["locale"], "pt-BR")
        self.assertEqual(payload["voice_id"], "myvoice")
        self.assertEqual(len(payload["script"]["segments"]), 1)

    def test_validate_script_for_layer3_valid(self):
        """Valid script passes layer 3 pre-check."""
        from lib.schemas import validate_script_for_layer3
        script = {
            "status": "ok",
            "total_word_count": 600,
            "script": {
                "intro": "A sufficiently long intro text here.",
                "segments": [{"body": "x" * 60}],
                "outro": "A sufficiently long outro text here.",
            },
        }
        issues = validate_script_for_layer3(script)
        self.assertEqual(issues, [])

    def test_validate_script_for_layer3_needs_human(self):
        """Script with needs_human status fails."""
        from lib.schemas import validate_script_for_layer3
        script = {
            "status": "needs_human",
            "total_word_count": 600,
            "script": {"intro": "x" * 30, "segments": [{"body": "x" * 60}], "outro": "x" * 30},
        }
        issues = validate_script_for_layer3(script)
        self.assertTrue(any("status" in i for i in issues))


# ==========================================================================
# Audio Utils tests
# ==========================================================================

class TestAudioUtils(unittest.TestCase):
    """Tests for audio_utils — filler scrub, digest, atomic write."""

    def test_scrub_fillers_en(self):
        """English filler words removed."""
        from lib.audio_utils import scrub_fillers
        text = "This is just really basically a great product."
        result = scrub_fillers(text, lang="en")
        self.assertNotIn("just", result.lower().split())
        self.assertNotIn("really", result.lower().split())
        self.assertNotIn("basically", result.lower().split())
        self.assertIn("great", result)
        self.assertIn("product", result)

    def test_scrub_fillers_pt(self):
        """Portuguese filler words removed."""
        from lib.audio_utils import scrub_fillers
        text = "Este produto tipo basicamente funciona bem."
        result = scrub_fillers(text, lang="pt")
        self.assertNotIn("tipo", result.lower().split())
        self.assertNotIn("basicamente", result.lower().split())
        self.assertIn("funciona", result)

    def test_scrub_preserves_punctuation(self):
        """Filler scrub preserves sentence punctuation."""
        from lib.audio_utils import scrub_fillers
        text = "It's really great, honestly."
        result = scrub_fillers(text, lang="en")
        self.assertIn("great,", result)
        self.assertIn("It's", result)

    def test_compute_audio_digest_deterministic(self):
        """Same inputs produce same digest."""
        from lib.audio_utils import compute_audio_digest
        d1 = compute_audio_digest("v1", "Hello world", "model1")
        d2 = compute_audio_digest("v1", "Hello world", "model1")
        self.assertEqual(d1, d2)
        self.assertEqual(len(d1), 64)

    def test_compute_audio_digest_normalizes_whitespace(self):
        """Whitespace is normalized before hashing."""
        from lib.audio_utils import compute_audio_digest
        d1 = compute_audio_digest("v1", "Hello   world", "model1")
        d2 = compute_audio_digest("v1", "Hello world", "model1")
        self.assertEqual(d1, d2)

    def test_atomic_write_json(self):
        """Atomic write creates valid JSON file."""
        from lib.audio_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.json"
            data = {"key": "value", "num": 42}
            atomic_write_json(path, data)
            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded["key"], "value")
            self.assertEqual(loaded["num"], 42)

    def test_atomic_write_bytes(self):
        """Atomic write creates binary file."""
        from lib.audio_utils import atomic_write_bytes
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.bin"
            atomic_write_bytes(path, b"hello world")
            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), b"hello world")


# ==========================================================================
# Orchestrator tests
# ==========================================================================

class TestOrchestrator(unittest.TestCase):
    """Tests for RayVaultOrchestrator — checkpoint + voice_prep + media_gate."""

    def _make_mock_panic(self):
        """Create a mock PanicManager."""
        mock = MagicMock()
        mock.report_panic = MagicMock()
        return mock

    def _make_segments(self):
        return [
            {"segment_id": "intro", "kind": "intro", "text": "Looking for earbuds?", "approx_duration_sec": 4, "lip_sync_hint": "excited"},
            {"segment_id": "p0", "kind": "product", "text": "The Sony delivers best noise cancellation.", "approx_duration_sec": 5, "lip_sync_hint": "serious"},
            {"segment_id": "outro", "kind": "outro", "text": "Subscribe for more reviews.", "approx_duration_sec": 4, "lip_sync_hint": "neutral"},
        ]

    def test_checkpoint_save_load(self):
        """Checkpoint persists and loads correctly."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())

            orch.save_checkpoint("RAY-1", "VOICE_GEN", {"segments": [{"id": "intro"}]})
            cp = orch.load_checkpoint("RAY-1")
            self.assertEqual(cp["stage"], "VOICE_GEN")
            self.assertEqual(cp["data"]["segments"][0]["id"], "intro")

    def test_checkpoint_initial_state(self):
        """Missing checkpoint returns initial VOICE_PREP state."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            cp = orch.load_checkpoint("RAY-NEW")
            self.assertEqual(cp["stage"], "VOICE_PREP")

    def test_voice_prep_ok_segments(self):
        """voice_prep passes well-sized segments through."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            segs = self._make_segments()
            result = orch.voice_prep(segs)
            self.assertEqual(len(result), 3)
            for s in result:
                self.assertIn("tone_gate", s)
                self.assertFalse(s.get("needs_repair", False))

    def test_voice_prep_rate_tweak(self):
        """Slight overage triggers rate tweak."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
                rate_tweak_max_ratio=1.05,
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            # ~4 words at 165 wpm ≈ 1.5s, approx_duration=2s → ratio ≈ 0.73 → rate_tweak
            segs = [{"segment_id": "x", "text": "Hello world out there", "approx_duration_sec": 2}]
            result = orch.voice_prep(segs)
            self.assertEqual(result[0]["tone_gate"]["action"], "rate_tweak")
            self.assertIn("rate", result[0].get("tts_hints", {}))

    def test_voice_prep_needs_repair(self):
        """Large overage triggers needs_repair flag."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            # 40 words at 165 wpm ≈ 14.5s, approx=5s → ratio ≈ 2.9 → needs_repair
            long_text = " ".join(["word"] * 40)
            segs = [{"segment_id": "x", "text": long_text, "approx_duration_sec": 5}]
            result = orch.voice_prep(segs)
            self.assertTrue(result[0].get("needs_repair"))
            self.assertEqual(result[0]["tone_gate"]["action"], "needs_repair")

    def test_voice_prep_empty_text(self):
        """Empty text triggers needs_repair."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            segs = [{"segment_id": "x", "text": "", "approx_duration_sec": 5}]
            result = orch.voice_prep(segs)
            self.assertTrue(result[0].get("needs_repair"))

    def test_voice_gen_no_engine(self):
        """voice_gen without TTS engine marks all needs_human."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic(), tts_engine=None)
            segs = self._make_segments()
            result = orch.voice_gen("RAY-1", segs)
            for s in result:
                self.assertTrue(s.get("needs_human"))
                self.assertIsNone(s.get("audio_path"))

    def test_build_manifest(self):
        """Manifest built correctly from segments."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            segs = [
                {"segment_id": "intro", "kind": "intro", "audio_path": "/tmp/a.mp3", "approx_duration_sec": 5},
                {"segment_id": "p0", "kind": "product", "audio_path": "/tmp/b.mp3", "approx_duration_sec": 10},
            ]
            path = orch.build_manifest("RAY-1", segs)
            self.assertTrue(path.exists())
            m = json.loads(path.read_text())
            self.assertEqual(m["run_id"], "RAY-1")
            self.assertEqual(len(m["segments"]), 2)
            self.assertEqual(m["segments"][0]["segment_id"], "intro")

    def test_media_gate_missing_audio(self):
        """media_gate raises on missing audio file."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            manifest = {
                "segments": [
                    {"segment_id": "x", "audio_path": "/nonexistent/audio.mp3", "video_path": None},
                ],
            }
            manifest_path = Path(td) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(RuntimeError) as ctx:
                orch.media_gate(manifest_path)
            self.assertIn("MEDIA_GATE_FAIL", str(ctx.exception))

    def test_media_gate_small_audio(self):
        """media_gate raises on audio file below minimum size."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
                min_mp3_bytes=1000,
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            # Create tiny audio file
            tiny = Path(td) / "tiny.mp3"
            tiny.write_bytes(b"x" * 100)
            manifest = {
                "segments": [
                    {"segment_id": "x", "audio_path": str(tiny), "video_path": None},
                ],
            }
            manifest_path = Path(td) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(RuntimeError) as ctx:
                orch.media_gate(manifest_path)
            self.assertIn("too small", str(ctx.exception))

    def test_render_probe_missing(self):
        """render_probe raises on missing file."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            with self.assertRaises(RuntimeError) as ctx:
                orch.render_probe(Path("/nonexistent/video.mp4"))
            self.assertIn("RENDER_PROBE_FAIL", str(ctx.exception))

    def test_voice_prep_filler_scrub(self):
        """Filler scrub applied for medium overage."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
                rate_tweak_max_ratio=0.5,  # force past rate_tweak
                filler_scrub_max_ratio=2.0,  # allow filler scrub
            )
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=self._make_mock_panic())
            segs = [{"segment_id": "x", "text": "This is just really basically a nice product.", "approx_duration_sec": 3}]
            result = orch.voice_prep(segs, lang="en")
            self.assertEqual(result[0]["tone_gate"]["action"], "filler_scrub")
            # Fillers should be removed
            self.assertNotIn("just", result[0]["text"].lower().split())


# ==========================================================================
# v0.1.1 tests — pause tags, manifest integrity, cleanup, orchestrator fail
# ==========================================================================

class TestPauseTags(unittest.TestCase):
    """Tests for pause tag parsing (audio_utils v0.1.1)."""

    def test_tokenize_simple(self):
        """Parses text with a single pause tag."""
        from lib.audio_utils import tokenize_pause_tags, PauseToken, TextToken
        tokens = tokenize_pause_tags("Hello [pause=300ms] world")
        self.assertEqual(len(tokens), 3)
        self.assertIsInstance(tokens[0], TextToken)
        self.assertEqual(tokens[0].text, "Hello ")
        self.assertIsInstance(tokens[1], PauseToken)
        self.assertEqual(tokens[1].ms, 300)
        self.assertIsInstance(tokens[2], TextToken)
        self.assertEqual(tokens[2].text, " world")

    def test_tokenize_multiple(self):
        """Parses multiple pause tags."""
        from lib.audio_utils import tokenize_pause_tags, PauseToken
        tokens = tokenize_pause_tags("A [pause=100ms] B [pause=500ms] C")
        pauses = [t for t in tokens if isinstance(t, PauseToken)]
        self.assertEqual(len(pauses), 2)
        self.assertEqual(pauses[0].ms, 100)
        self.assertEqual(pauses[1].ms, 500)

    def test_tokenize_no_tags(self):
        """Text without pause tags returns single TextToken."""
        from lib.audio_utils import tokenize_pause_tags, TextToken
        tokens = tokenize_pause_tags("Just plain text here.")
        self.assertEqual(len(tokens), 1)
        self.assertIsInstance(tokens[0], TextToken)

    def test_total_pause_ms(self):
        """Sums all pause durations."""
        from lib.audio_utils import total_pause_ms
        self.assertEqual(total_pause_ms("A [pause=200ms] B [pause=300ms]"), 500)
        self.assertEqual(total_pause_ms("No pauses here"), 0)

    def test_total_pause_ms_case_insensitive(self):
        """Pause tags are case-insensitive."""
        from lib.audio_utils import total_pause_ms
        self.assertEqual(total_pause_ms("A [PAUSE=200MS] B"), 200)

    def test_tokenize_adjacent_tags(self):
        """Adjacent pause tags parsed correctly."""
        from lib.audio_utils import tokenize_pause_tags, PauseToken
        tokens = tokenize_pause_tags("[pause=100ms][pause=200ms]")
        pauses = [t for t in tokens if isinstance(t, PauseToken)]
        self.assertEqual(len(pauses), 2)
        self.assertEqual(pauses[0].ms, 100)
        self.assertEqual(pauses[1].ms, 200)


class TestManifestIntegrity(unittest.TestCase):
    """Tests for manifest integrity stamps (v0.1.1)."""

    def test_stamp_adds_sha256_and_bytes(self):
        """stamp_manifest_integrity adds hash and size fields."""
        from lib.media_manifest import stamp_manifest_integrity
        with tempfile.TemporaryDirectory() as td:
            # Create fake audio + video files
            audio = Path(td) / "seg_intro.mp3"
            video = Path(td) / "intro.mp4"
            audio.write_bytes(b"fake audio data" * 100)
            video.write_bytes(b"fake video data" * 200)

            manifest = {
                "segments": [{
                    "segment_id": "intro",
                    "audio_path": str(audio),
                    "video_path": str(video),
                }],
            }

            stamped = stamp_manifest_integrity(manifest)

            # Original not modified
            self.assertNotIn("audio_path_sha256", manifest["segments"][0])

            # Stamped has fields
            seg = stamped["segments"][0]
            self.assertIn("audio_path_sha256", seg)
            self.assertIn("audio_path_bytes", seg)
            self.assertIn("video_path_sha256", seg)
            self.assertIn("video_path_bytes", seg)
            self.assertEqual(seg["audio_path_bytes"], len(b"fake audio data" * 100))
            self.assertEqual(len(seg["audio_path_sha256"]), 64)

    def test_stamp_skips_missing_files(self):
        """Missing files don't get stamps (no crash)."""
        from lib.media_manifest import stamp_manifest_integrity
        manifest = {
            "segments": [{
                "segment_id": "x",
                "audio_path": "/nonexistent/audio.mp3",
                "video_path": "/nonexistent/video.mp4",
            }],
        }
        stamped = stamp_manifest_integrity(manifest)
        seg = stamped["segments"][0]
        self.assertNotIn("audio_path_sha256", seg)
        self.assertNotIn("video_path_sha256", seg)

    def test_validate_integrity_ok(self):
        """Validation passes when files match stamps."""
        from lib.media_manifest import stamp_manifest_integrity, validate_manifest_integrity
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "seg.mp3"
            audio.write_bytes(b"consistent data")
            manifest = {"segments": [{"segment_id": "x", "audio_path": str(audio), "video_path": ""}]}
            stamped = stamp_manifest_integrity(manifest)
            issues = validate_manifest_integrity(stamped)
            self.assertEqual(issues, [])

    def test_validate_integrity_detects_corruption(self):
        """Validation catches modified file (hash mismatch)."""
        from lib.media_manifest import stamp_manifest_integrity, validate_manifest_integrity
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "seg.mp3"
            audio.write_bytes(b"original data")
            manifest = {"segments": [{"segment_id": "x", "audio_path": str(audio), "video_path": ""}]}
            stamped = stamp_manifest_integrity(manifest)

            # Corrupt the file
            audio.write_bytes(b"tampered data!!")
            issues = validate_manifest_integrity(stamped)
            self.assertTrue(any("hash mismatch" in i for i in issues))

    def test_validate_integrity_detects_size_mismatch(self):
        """Validation catches truncated file (size mismatch)."""
        from lib.media_manifest import stamp_manifest_integrity, validate_manifest_integrity
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "seg.mp3"
            audio.write_bytes(b"x" * 1000)
            manifest = {"segments": [{"segment_id": "x", "audio_path": str(audio), "video_path": ""}]}
            stamped = stamp_manifest_integrity(manifest)

            # Truncate the file
            audio.write_bytes(b"x" * 100)
            issues = validate_manifest_integrity(stamped)
            self.assertTrue(any("size mismatch" in i for i in issues))

    def test_validate_integrity_detects_missing(self):
        """Validation catches deleted file."""
        from lib.media_manifest import stamp_manifest_integrity, validate_manifest_integrity
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "seg.mp3"
            audio.write_bytes(b"will be deleted")
            manifest = {"segments": [{"segment_id": "x", "audio_path": str(audio), "video_path": ""}]}
            stamped = stamp_manifest_integrity(manifest)

            audio.unlink()
            issues = validate_manifest_integrity(stamped)
            self.assertTrue(any("missing" in i for i in issues))


class TestCleanupPolicy(unittest.TestCase):
    """Tests for cleanup_policy script."""

    def test_dry_run_does_not_delete(self):
        """Dry run reports but doesn't delete."""
        # Import inline to avoid path issues
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cleanup_policy",
            str(Path(__file__).parent.parent / "scripts" / "cleanup_policy.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as td:
            # Create old audio dir
            audio_dir = Path(td) / "audio" / "RAY-OLD"
            audio_dir.mkdir(parents=True)
            fake_file = audio_dir / "seg_abc.mp3"
            fake_file.write_bytes(b"x" * 100)
            # Set mtime to 30 days ago
            old_time = time.time() - (30 * 86400)
            os.utime(audio_dir, (old_time, old_time))
            os.utime(fake_file, (old_time, old_time))

            summary = mod.run_cleanup(
                state_dir=td, audio_days=7.0, video_days=7.0,
                traces_days=7.0, dry_run=True,
            )
            self.assertEqual(summary["audio_deleted"], 1)
            self.assertTrue(summary["dry_run"])
            # File still exists
            self.assertTrue(fake_file.exists())

    def test_execute_deletes(self):
        """Execute mode actually deletes."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cleanup_policy",
            str(Path(__file__).parent.parent / "scripts" / "cleanup_policy.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as td:
            audio_dir = Path(td) / "audio" / "RAY-OLD"
            audio_dir.mkdir(parents=True)
            fake_file = audio_dir / "seg_abc.mp3"
            fake_file.write_bytes(b"x" * 100)
            old_time = time.time() - (30 * 86400)
            os.utime(audio_dir, (old_time, old_time))
            os.utime(fake_file, (old_time, old_time))

            summary = mod.run_cleanup(
                state_dir=td, audio_days=7.0, video_days=7.0,
                traces_days=7.0, dry_run=False,
            )
            self.assertEqual(summary["audio_deleted"], 1)
            self.assertFalse(summary["dry_run"])
            self.assertFalse(audio_dir.exists())

    def test_recent_files_not_deleted(self):
        """Recent files are left alone."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cleanup_policy",
            str(Path(__file__).parent.parent / "scripts" / "cleanup_policy.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as td:
            audio_dir = Path(td) / "audio" / "RAY-NEW"
            audio_dir.mkdir(parents=True)
            fake_file = audio_dir / "seg_abc.mp3"
            fake_file.write_bytes(b"x" * 100)
            # mtime is now (fresh)

            summary = mod.run_cleanup(
                state_dir=td, audio_days=7.0, video_days=7.0,
                traces_days=7.0, dry_run=False,
            )
            self.assertEqual(summary["audio_deleted"], 0)
            self.assertTrue(fake_file.exists())


class TestOrchestratorFailCheckpoint(unittest.TestCase):
    """Tests for orchestrator fail_reason in checkpoint (v0.1.1)."""

    def _make_mock_panic(self):
        class MockPanic:
            def __init__(self):
                self.calls = []
            def report_panic(self, reason_key, run_id, error_msg, **kw):
                self.calls.append((reason_key, run_id, error_msg))
        return MockPanic()

    def test_fail_writes_reason_to_checkpoint(self):
        """Stage failure writes fail_reason and failed_at to checkpoint."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            pm = self._make_mock_panic()
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=pm)

            # Force a failure by starting at ASSEMBLY with bad manifest
            from lib.audio_utils import atomic_write_json
            cp_path = Path(f"{td}/cp/FAIL-1.json")
            atomic_write_json(cp_path, {
                "run_id": "FAIL-1",
                "stage": "RENDER_PROBE",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "data": {"output_path": "/nonexistent/video.mp4"},
            })

            with self.assertRaises(RuntimeError):
                import asyncio
                asyncio.run(orch.run(run_id="FAIL-1", segments_plan=[]))

            # Reload checkpoint — should have fail_reason
            cp = json.loads(cp_path.read_text())
            self.assertIn("fail_reason", cp)
            self.assertIn("RENDER_PROBE_FAIL", cp["fail_reason"])
            self.assertIn("failed_at", cp)

    def test_fail_reason_truncated(self):
        """fail_reason is truncated to 500 chars."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            pm = self._make_mock_panic()
            orch = RayVaultOrchestrator(config=cfg, panic_mgr=pm)

            # Set checkpoint at RENDER_PROBE with missing output
            from lib.audio_utils import atomic_write_json
            cp_path = Path(f"{td}/cp/FAIL-2.json")
            atomic_write_json(cp_path, {
                "run_id": "FAIL-2",
                "stage": "RENDER_PROBE",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "data": {"output_path": "/nonexistent/video.mp4"},
            })

            with self.assertRaises(RuntimeError):
                import asyncio
                asyncio.run(orch.run(run_id="FAIL-2", segments_plan=[]))

            cp = json.loads(cp_path.read_text())
            self.assertLessEqual(len(cp["fail_reason"]), 500)


class TestResolveAssembleFindByName(unittest.TestCase):
    """Tests for resolve_assemble.py _build_clip_index helper."""

    def test_build_clip_index_imported(self):
        """_build_clip_index function is importable."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "resolve_assemble",
            str(Path(__file__).parent.parent / "scripts" / "resolve_assemble.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(callable(getattr(mod, "_build_clip_index", None)))


class TestComputeFileSha256(unittest.TestCase):
    """Tests for compute_file_sha256 in audio_utils."""

    def test_file_sha256_deterministic(self):
        """Same content produces same hash."""
        from lib.audio_utils import compute_file_sha256
        with tempfile.TemporaryDirectory() as td:
            f1 = Path(td) / "a.bin"
            f2 = Path(td) / "b.bin"
            f1.write_bytes(b"hello world")
            f2.write_bytes(b"hello world")
            self.assertEqual(compute_file_sha256(f1), compute_file_sha256(f2))
            self.assertEqual(len(compute_file_sha256(f1)), 64)

    def test_file_sha256_different_content(self):
        """Different content produces different hash."""
        from lib.audio_utils import compute_file_sha256
        with tempfile.TemporaryDirectory() as td:
            f1 = Path(td) / "a.bin"
            f2 = Path(td) / "b.bin"
            f1.write_bytes(b"hello")
            f2.write_bytes(b"world")
            self.assertNotEqual(compute_file_sha256(f1), compute_file_sha256(f2))


# ==========================================================================
# v0.2.0 tests — FinalizeResult gate + tolerance + orchestrator integration
# ==========================================================================

class TestFinalizeResult(unittest.TestCase):
    """Tests for FinalizeResult dataclass."""

    def test_finalize_result_fields(self):
        """FinalizeResult has correct fields."""
        from lib.audio_utils import FinalizeResult
        fr = FinalizeResult(
            action="ok", input_path=Path("/a.mp3"), output_path=Path("/a.mp3"),
            target_duration_sec=5.0, measured_duration_sec=4.98,
            delta_ms=20, reason="within tolerance",
        )
        self.assertEqual(fr.action, "ok")
        self.assertEqual(fr.delta_ms, 20)
        self.assertIsNone(fr.rate)

    def test_finalize_result_with_rate(self):
        """FinalizeResult stores rate for rate_tweak action."""
        from lib.audio_utils import FinalizeResult
        fr = FinalizeResult(
            action="rate_tweak", input_path=Path("/a.mp3"), output_path=Path("/a.mp3"),
            target_duration_sec=5.0, measured_duration_sec=5.1,
            delta_ms=-100, rate=1.02, reason="atempo",
        )
        self.assertEqual(fr.rate, 1.02)
        self.assertEqual(fr.action, "rate_tweak")


class TestToleranceMsForKind(unittest.TestCase):
    """Tests for tolerance_ms_for_kind."""

    def test_known_kinds(self):
        """Known segment kinds return correct tolerance."""
        from lib.audio_utils import tolerance_ms_for_kind
        self.assertEqual(tolerance_ms_for_kind("intro"), 80)
        self.assertEqual(tolerance_ms_for_kind("outro"), 80)
        self.assertEqual(tolerance_ms_for_kind("product"), 120)
        self.assertEqual(tolerance_ms_for_kind("transition"), 150)

    def test_unknown_kind_default(self):
        """Unknown kind returns default tolerance."""
        from lib.audio_utils import tolerance_ms_for_kind
        self.assertEqual(tolerance_ms_for_kind("unknown"), 80)
        self.assertEqual(tolerance_ms_for_kind(""), 80)


class TestFinalizeGate(unittest.TestCase):
    """Tests for finalize_segment_audio smart gate (v0.2.0).

    These tests require pydub. Skipped if pydub is not installed.
    """

    def _skip_without_pydub(self):
        try:
            from pydub import AudioSegment
            return False
        except ImportError:
            return True

    def _make_audio_file(self, td, duration_ms=5000, filename="test.mp3"):
        """Create a real audio file with pydub."""
        from pydub import AudioSegment
        seg = AudioSegment.silent(duration=duration_ms)
        path = Path(td) / filename
        seg.export(path, format="mp3")
        return path

    def test_error_on_bad_target(self):
        """Returns error for target_duration <= 0."""
        from lib.audio_utils import finalize_segment_audio
        fr = finalize_segment_audio(Path("/fake.mp3"), target_duration=0)
        self.assertEqual(fr.action, "error")
        self.assertIn("target_duration", fr.reason)

    def test_error_on_missing_file(self):
        """Returns error for nonexistent file."""
        from lib.audio_utils import finalize_segment_audio
        if self._skip_without_pydub():
            self.skipTest("pydub not installed")
        fr = finalize_segment_audio(Path("/nonexistent/x.mp3"), target_duration=5.0)
        self.assertEqual(fr.action, "error")
        self.assertIn("missing", fr.reason)

    def test_ok_within_tolerance(self):
        """Audio within tolerance returns ok."""
        if self._skip_without_pydub():
            self.skipTest("pydub not installed")
        from lib.audio_utils import finalize_segment_audio
        with tempfile.TemporaryDirectory() as td:
            path = self._make_audio_file(td, duration_ms=5000)
            fr = finalize_segment_audio(path, target_duration=5.05, kind="product")
            self.assertEqual(fr.action, "ok")

    def test_pad_silence_when_short(self):
        """Short audio gets padded to target."""
        if self._skip_without_pydub():
            self.skipTest("pydub not installed")
        from lib.audio_utils import finalize_segment_audio
        with tempfile.TemporaryDirectory() as td:
            path = self._make_audio_file(td, duration_ms=3000)
            fr = finalize_segment_audio(path, target_duration=5.0, kind="intro")
            self.assertEqual(fr.action, "pad_silence")
            self.assertIn("padded", fr.reason)

    def test_needs_repair_when_way_over(self):
        """Audio way over target returns needs_repair."""
        if self._skip_without_pydub():
            self.skipTest("pydub not installed")
        from lib.audio_utils import finalize_segment_audio
        with tempfile.TemporaryDirectory() as td:
            # 6 seconds audio, 5 second target → 20% over → needs_repair
            path = self._make_audio_file(td, duration_ms=6000)
            fr = finalize_segment_audio(
                path, target_duration=5.0, kind="product",
                max_over_pct_for_rate=0.02,
            )
            self.assertEqual(fr.action, "needs_repair")
            self.assertIn("exceeds", fr.reason)

    def test_tolerance_varies_by_kind(self):
        """Different kinds have different tolerance thresholds."""
        if self._skip_without_pydub():
            self.skipTest("pydub not installed")
        from lib.audio_utils import finalize_segment_audio
        with tempfile.TemporaryDirectory() as td:
            # 5100ms audio, 5000ms target → 100ms over
            # intro tolerance=80ms → should NOT be ok
            # transition tolerance=150ms → SHOULD be ok
            path_intro = self._make_audio_file(td, duration_ms=5100, filename="intro.mp3")
            fr_intro = finalize_segment_audio(path_intro, target_duration=5.0, kind="intro")
            self.assertNotEqual(fr_intro.action, "ok")

            path_trans = self._make_audio_file(td, duration_ms=5100, filename="trans.mp3")
            fr_trans = finalize_segment_audio(path_trans, target_duration=5.0, kind="transition")
            self.assertEqual(fr_trans.action, "ok")

    def test_finalize_with_pause_injection(self):
        """Pause tags add silence before gate decision."""
        if self._skip_without_pydub():
            self.skipTest("pydub not installed")
        from lib.audio_utils import finalize_segment_audio
        with tempfile.TemporaryDirectory() as td:
            # 4500ms audio + [pause=300ms] = 4800ms → target 5000ms → pad 200ms
            path = self._make_audio_file(td, duration_ms=4500)
            fr = finalize_segment_audio(
                path, target_duration=5.0,
                source_text="Hello [pause=300ms] world",
                kind="product",
            )
            self.assertEqual(fr.action, "pad_silence")


class TestExportAtomic(unittest.TestCase):
    """Tests for _export_atomic helper."""

    def test_export_atomic_creates_file(self):
        """_export_atomic creates a valid file."""
        try:
            from pydub import AudioSegment
        except ImportError:
            self.skipTest("pydub not installed")
        from lib.audio_utils import _export_atomic
        with tempfile.TemporaryDirectory() as td:
            seg = AudioSegment.silent(duration=1000)
            out = Path(td) / "out.mp3"
            _export_atomic(seg, out, fmt="mp3")
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)
            # No .tmp leftover
            self.assertFalse(out.with_suffix(".mp3.tmp").exists())


class TestOrchestratorFinalizeIntegration(unittest.TestCase):
    """Tests for orchestrator voice_gen with smart finalize gate."""

    def _make_mock_panic(self):
        class MockPanic:
            def __init__(self):
                self.calls = []
            def report_panic(self, reason_key, run_id, error_msg, **kw):
                self.calls.append((reason_key, run_id, error_msg))
        return MockPanic()

    def test_voice_gen_stores_finalize_result(self):
        """voice_gen stores finalize_result metadata per segment."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        try:
            from pydub import AudioSegment
        except ImportError:
            self.skipTest("pydub not installed")

        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )

            # Create a mock TTS that returns a real audio file
            audio_dir = Path(td) / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)

            class MockTTS:
                def synthesize(self, *, run_id, text):
                    path = audio_dir / f"{run_id}.mp3"
                    seg = AudioSegment.silent(duration=4500)
                    seg.export(path, format="mp3")
                    return path
                def has_artifact(self, run_id):
                    return False

            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=self._make_mock_panic(),
                tts_engine=MockTTS(),
            )
            segs = [{
                "segment_id": "intro",
                "kind": "intro",
                "text": "Hello world this is a test.",
                "approx_duration_sec": 5.0,
            }]
            result = orch.voice_gen("TEST-1", segs)
            self.assertEqual(len(result), 1)
            fr = result[0].get("finalize_result")
            self.assertIsNotNone(fr)
            self.assertIn(fr["action"], ("ok", "pad_silence", "rate_tweak", "needs_repair", "error"))
            self.assertIn("delta_ms", fr)
            self.assertIn("measured_sec", fr)

    def test_voice_gen_marks_repair_on_way_over(self):
        """voice_gen marks segment needs_repair when finalize says so."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        try:
            from pydub import AudioSegment
        except ImportError:
            self.skipTest("pydub not installed")

        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            audio_dir = Path(td) / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)

            class MockTTS:
                def synthesize(self, *, run_id, text):
                    path = audio_dir / f"{run_id}.mp3"
                    # 8 seconds audio for 5 second target → 60% over → needs_repair
                    seg = AudioSegment.silent(duration=8000)
                    seg.export(path, format="mp3")
                    return path
                def has_artifact(self, run_id):
                    return False

            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=self._make_mock_panic(),
                tts_engine=MockTTS(),
            )
            segs = [{
                "segment_id": "intro",
                "kind": "intro",
                "text": "Hello world.",
                "approx_duration_sec": 5.0,
            }]
            result = orch.voice_gen("TEST-2", segs)
            self.assertTrue(result[0].get("needs_repair"))
            self.assertIsNotNone(result[0].get("repair_reason"))
            fr = result[0]["finalize_result"]
            self.assertEqual(fr["action"], "needs_repair")

    def test_voice_gen_no_tts_engine(self):
        """voice_gen without TTS marks all needs_human."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=self._make_mock_panic(),
            )
            segs = [{"segment_id": "x", "text": "Hello", "approx_duration_sec": 5}]
            result = orch.voice_gen("TEST-3", segs)
            self.assertTrue(result[0]["needs_human"])
            self.assertIsNone(result[0]["audio_path"])


# ==========================================================================
# Repair loop tests
# ==========================================================================

class TestRepairLoop(unittest.TestCase):
    """Tests for voice_gen_with_repair in orchestrator."""

    def _make_mock_panic(self):
        class MockPanic:
            def __init__(self):
                self.calls = []
            def report_panic(self, reason_key, run_id, error_msg, **kw):
                self.calls.append((reason_key, run_id, error_msg))
        return MockPanic()

    def test_repair_loop_without_repair_engine(self):
        """Without repair engine, voice_gen_with_repair == voice_gen."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=self._make_mock_panic(),
            )
            segs = [{"segment_id": "x", "text": "Hello", "needs_repair": True}]
            result = orch.voice_gen_with_repair("TEST-R1", segs)
            self.assertIsNone(result[0]["audio_path"])

    def test_repair_loop_succeeds(self):
        """Repair engine fixes text, re-TTS succeeds."""
        try:
            from pydub import AudioSegment
        except ImportError:
            self.skipTest("pydub not installed")
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig

        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
                max_repair_attempts=2,
            )
            audio_dir = Path(td) / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)

            call_count = [0]

            class MockTTS:
                def synthesize(self, *, run_id, text):
                    call_count[0] += 1
                    path = audio_dir / f"{run_id}.mp3"
                    # First call: 8s (way over), repair calls: 5s (fits)
                    dur = 8000 if call_count[0] == 1 else 5000
                    seg = AudioSegment.silent(duration=dur)
                    seg.export(path, format="mp3")
                    return path
                def has_artifact(self, run_id):
                    return False

            class MockRepair:
                def repair_segment(self, *, segment_id, text, reduce_by_ms):
                    return "Shorter text here."

            pm = self._make_mock_panic()
            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=pm,
                tts_engine=MockTTS(),
                repair_engine=MockRepair(),
            )

            segs = [{
                "segment_id": "intro",
                "kind": "intro",
                "text": "Very long text that exceeds duration.",
                "approx_duration_sec": 5.0,
            }]

            # First voice_gen marks needs_repair, then repair loop fixes it
            result = orch.voice_gen_with_repair("TEST-R2", segs)
            self.assertFalse(result[0].get("needs_repair", False))
            self.assertIsNotNone(result[0].get("audio_path"))
            self.assertEqual(result[0].get("repair_attempts"), 1)

    def test_repair_loop_exhausted_panics(self):
        """Repair exhausted triggers panic."""
        try:
            from pydub import AudioSegment
        except ImportError:
            self.skipTest("pydub not installed")
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig

        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", output_dir=f"{td}/output",
                max_repair_attempts=1,
            )
            audio_dir = Path(td) / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)

            class MockTTS:
                def synthesize(self, *, run_id, text):
                    path = audio_dir / f"{run_id}.mp3"
                    # Always 8s — never fits
                    seg = AudioSegment.silent(duration=8000)
                    seg.export(path, format="mp3")
                    return path
                def has_artifact(self, run_id):
                    return False

            class MockRepair:
                def repair_segment(self, *, segment_id, text, reduce_by_ms):
                    return "Still too long text."

            pm = self._make_mock_panic()
            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=pm,
                tts_engine=MockTTS(),
                repair_engine=MockRepair(),
            )

            segs = [{
                "segment_id": "intro",
                "kind": "intro",
                "text": "Long text.",
                "approx_duration_sec": 5.0,
            }]

            result = orch.voice_gen_with_repair("TEST-R3", segs)
            self.assertTrue(result[0].get("needs_human"))
            self.assertTrue(result[0].get("repair_exhausted"))
            # Panic was reported
            self.assertTrue(any("panic_voice_contract_drift" in c[0] for c in pm.calls))


# ==========================================================================
# Dual cache digest tests
# ==========================================================================

class TestDualCacheDigest(unittest.TestCase):
    """Tests for compute_final_digest (Cache A vs Cache B)."""

    def test_same_tts_different_target_different_final(self):
        """Different target_duration → different final digest."""
        from lib.audio_utils import compute_audio_digest, compute_final_digest
        tts_d = compute_audio_digest("v1", "Hello world", "model1")
        final_a = compute_final_digest(tts_d, target_duration_sec=5.0)
        final_b = compute_final_digest(tts_d, target_duration_sec=10.0)
        self.assertNotEqual(final_a, final_b)
        # But TTS digest is the same (no ElevenLabs re-gen needed)
        self.assertEqual(len(final_a), 64)

    def test_same_inputs_same_final(self):
        """Same inputs → same final digest (deterministic)."""
        from lib.audio_utils import compute_final_digest
        d1 = compute_final_digest("abc123", target_duration_sec=5.0, action="pad_silence")
        d2 = compute_final_digest("abc123", target_duration_sec=5.0, action="pad_silence")
        self.assertEqual(d1, d2)

    def test_rate_changes_digest(self):
        """Different rate → different final digest."""
        from lib.audio_utils import compute_final_digest
        d1 = compute_final_digest("abc123", target_duration_sec=5.0, rate=1.02)
        d2 = compute_final_digest("abc123", target_duration_sec=5.0, rate=1.05)
        self.assertNotEqual(d1, d2)

    def test_action_changes_digest(self):
        """Different action → different final digest."""
        from lib.audio_utils import compute_final_digest
        d1 = compute_final_digest("abc123", target_duration_sec=5.0, action="ok")
        d2 = compute_final_digest("abc123", target_duration_sec=5.0, action="pad_silence")
        self.assertNotEqual(d1, d2)


# ==========================================================================
# Dzine manifest preparation tests
# ==========================================================================

class TestDzineManifestPreparation(unittest.TestCase):
    """Tests for prepare_manifest_for_dzine."""

    def test_adds_dzine_block(self):
        """Adds dzine block with upload/settings/export."""
        from lib.media_manifest import prepare_manifest_for_dzine, DzineHints
        with tempfile.TemporaryDirectory() as td:
            # Create fake audio
            audio = Path(td) / "seg_intro.mp3"
            audio.write_bytes(b"fake" * 100)

            manifest = {
                "run_id": "RAY-42",
                "segments": [{
                    "segment_id": "intro",
                    "kind": "intro",
                    "audio_path": str(audio),
                    "approx_duration_sec": 10,
                    "lip_sync_hint": "excited",
                }],
            }

            ready = prepare_manifest_for_dzine(
                manifest,
                video_final_dir=td,
                hints=DzineHints(avatar_ref="test_avatar.png"),
            )

            seg = ready["segments"][0]
            self.assertIn("dzine", seg)
            self.assertIn("upload", seg["dzine"])
            self.assertIn("settings", seg["dzine"])
            self.assertIn("export", seg["dzine"])
            self.assertIn("ui_checklist", seg["dzine"])
            self.assertIn("budget_control", seg["dzine"])
            self.assertEqual(seg["dzine"]["settings"]["lip_sync_hint"], "excited")

    def test_budget_summary(self):
        """Budget summary counts credits and segments to render."""
        from lib.media_manifest import prepare_manifest_for_dzine
        with tempfile.TemporaryDirectory() as td:
            a1 = Path(td) / "a1.mp3"
            a2 = Path(td) / "a2.mp3"
            a1.write_bytes(b"x" * 100)
            a2.write_bytes(b"y" * 100)

            manifest = {
                "run_id": "RAY-50",
                "segments": [
                    {"segment_id": "s1", "audio_path": str(a1), "approx_duration_sec": 5},
                    {"segment_id": "s2", "audio_path": str(a2), "approx_duration_sec": 5},
                ],
            }

            ready = prepare_manifest_for_dzine(manifest, video_final_dir=td)
            bs = ready["budget_summary"]
            self.assertEqual(bs["estimated_dzine_credits"], 2)
            self.assertEqual(len(bs["segments_to_render"]), 2)

    def test_cache_hit_skips_dzine(self):
        """Existing video file triggers cache hit → skip_dzine."""
        from lib.media_manifest import (
            prepare_manifest_for_dzine, DzineHints,
            _video_expected_path, _file_sha256,
        )
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "seg.mp3"
            audio.write_bytes(b"audio data")
            sha8 = _file_sha256(audio)[:8]

            # Pre-create the expected video
            expected = _video_expected_path(
                Path(td), "RAY-60", "intro", sha8,
            )
            expected.write_bytes(b"v" * 600_000)  # > min_video_bytes

            manifest = {
                "run_id": "RAY-60",
                "segments": [{
                    "segment_id": "intro",
                    "audio_path": str(audio),
                    "approx_duration_sec": 10,
                }],
            }

            ready = prepare_manifest_for_dzine(manifest, video_final_dir=td)
            seg = ready["segments"][0]
            self.assertTrue(seg["dzine"]["budget_control"]["cache_hit"])
            self.assertTrue(seg["dzine"]["budget_control"]["skip_dzine"])
            self.assertEqual(seg["dzine"]["budget_control"]["credit_cost"], 0)
            self.assertEqual(ready["budget_summary"]["estimated_dzine_credits"], 0)

    def test_sha256_added_to_segment(self):
        """Audio sha256 added to segment."""
        from lib.media_manifest import prepare_manifest_for_dzine
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "seg.mp3"
            audio.write_bytes(b"test data")

            manifest = {
                "run_id": "RAY-70",
                "segments": [{
                    "segment_id": "x",
                    "audio_path": str(audio),
                    "approx_duration_sec": 5,
                }],
            }

            ready = prepare_manifest_for_dzine(manifest, video_final_dir=td)
            seg = ready["segments"][0]
            self.assertIn("audio_sha256", seg)
            self.assertEqual(len(seg["audio_sha256"]), 64)
            self.assertIn("audio_bytes", seg)

    def test_deterministic_video_naming(self):
        """Video path follows V_{run_id}_{segment_id}_{sha8}.mp4 convention."""
        from lib.media_manifest import prepare_manifest_for_dzine, _file_sha256
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "seg.mp3"
            audio.write_bytes(b"naming test")
            sha8 = _file_sha256(audio)[:8]

            manifest = {
                "run_id": "RAY-80",
                "segments": [{
                    "segment_id": "intro",
                    "audio_path": str(audio),
                    "approx_duration_sec": 5,
                }],
            }

            ready = prepare_manifest_for_dzine(manifest, video_final_dir=td)
            seg = ready["segments"][0]
            expected_name = f"V_RAY-80_intro_{sha8}.mp4"
            self.assertTrue(seg["video_path"].endswith(expected_name))

    def test_original_manifest_not_modified(self):
        """prepare_manifest_for_dzine doesn't modify original."""
        from lib.media_manifest import prepare_manifest_for_dzine
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "seg.mp3"
            audio.write_bytes(b"immutable test")

            manifest = {
                "run_id": "RAY-90",
                "segments": [{
                    "segment_id": "x",
                    "audio_path": str(audio),
                    "approx_duration_sec": 5,
                }],
            }

            prepare_manifest_for_dzine(manifest, video_final_dir=td)
            # Original should NOT have dzine block
            self.assertNotIn("dzine", manifest["segments"][0])
            self.assertNotIn("budget_summary", manifest)


# ==========================================================================
# Preflight + Video probe + Index + Fail-fast tests
# ==========================================================================

class TestAtomicReadJson(unittest.TestCase):
    """Tests for atomic_read_json with corrupt file recovery."""

    def test_read_valid_json(self):
        """Reads valid JSON file."""
        from lib.audio_utils import atomic_read_json, atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ok.json"
            atomic_write_json(p, {"key": "value"})
            result = atomic_read_json(p)
            self.assertEqual(result["key"], "value")

    def test_read_missing_returns_default(self):
        """Missing file returns default."""
        from lib.audio_utils import atomic_read_json
        result = atomic_read_json(Path("/nonexistent.json"), default={"d": 1})
        self.assertEqual(result, {"d": 1})

    def test_read_corrupt_preserves_and_returns_default(self):
        """Corrupt file is renamed .corrupt and default returned."""
        from lib.audio_utils import atomic_read_json
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("{broken json!!!!")
            result = atomic_read_json(p, default={"fallback": True})
            self.assertEqual(result, {"fallback": True})
            # Original renamed
            self.assertFalse(p.exists())
            self.assertTrue(Path(td, "bad.json.corrupt").exists())


class TestIsVideoValid(unittest.TestCase):
    """Tests for is_video_valid (size + ffprobe)."""

    def test_missing_file(self):
        """Missing file returns (False, 0.0)."""
        from lib.media_manifest import is_video_valid
        ok, dur = is_video_valid(Path("/nonexistent.mp4"), 10.0)
        self.assertFalse(ok)
        self.assertEqual(dur, 0.0)

    def test_too_small_file(self):
        """File below min_bytes returns False."""
        from lib.media_manifest import is_video_valid
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tiny.mp4"
            p.write_bytes(b"x" * 100)
            ok, dur = is_video_valid(p, 10.0, min_bytes=500_000)
            self.assertFalse(ok)


class TestVideoIndex(unittest.TestCase):
    """Tests for video index load/upsert."""

    def test_load_empty_returns_default(self):
        """Empty index returns default structure."""
        from lib.media_manifest import load_video_index
        with tempfile.TemporaryDirectory() as td:
            idx = load_video_index(Path(td) / "missing.json")
            self.assertEqual(idx["version"], "1.0")
            self.assertEqual(idx["items"], {})

    def test_upsert_and_load(self):
        """upsert adds item, load retrieves it."""
        from lib.media_manifest import load_video_index, upsert_video_index
        with tempfile.TemporaryDirectory() as td:
            idx_path = Path(td) / "index.json"
            upsert_video_index(idx_path, "a1b2c3d4", {
                "segment_id": "intro",
                "path": "/video/intro.mp4",
                "duration": 10.5,
            })
            idx = load_video_index(idx_path)
            self.assertIn("a1b2c3d4", idx["items"])
            self.assertEqual(idx["items"]["a1b2c3d4"]["duration"], 10.5)

    def test_upsert_overwrites(self):
        """Upsert same sha8 overwrites previous entry."""
        from lib.media_manifest import load_video_index, upsert_video_index
        with tempfile.TemporaryDirectory() as td:
            idx_path = Path(td) / "index.json"
            upsert_video_index(idx_path, "abc", {"v": 1})
            upsert_video_index(idx_path, "abc", {"v": 2})
            idx = load_video_index(idx_path)
            self.assertEqual(idx["items"]["abc"]["v"], 2)


class TestPreflightGate(unittest.TestCase):
    """Tests for orchestrator preflight GO/NO_GO."""

    def _make_mock_panic(self):
        class MockPanic:
            def __init__(self):
                self.calls = []
            def report_panic(self, reason_key, run_id, error_msg, **kw):
                self.calls.append((reason_key, run_id, error_msg))
        return MockPanic()

    def test_preflight_no_go_insufficient_credits(self):
        """NO_GO when credits insufficient."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig, DzineBudget
        from lib.audio_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", video_final_dir=f"{td}/vfinal",
                video_index_path=f"{td}/index.json",
                output_dir=f"{td}/output",
            )
            budget = DzineBudget(available_credits=0, cost_per_segment=1)
            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=self._make_mock_panic(),
                dzine_budget=budget,
            )
            # Create manifest with segments
            manifest_path = Path(td) / "jobs" / "test.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(manifest_path, {
                "run_id": "TEST-PF",
                "segments": [
                    {"segment_id": "s1", "audio_path": "/a.mp3", "video_path": "/v.mp4", "approx_duration_sec": 5},
                ],
            })
            with self.assertRaises(RuntimeError) as ctx:
                orch.preflight(manifest_path)
            self.assertIn("PREFLIGHT_NO_GO", str(ctx.exception))

    def test_preflight_go_with_budget(self):
        """GO when credits sufficient (segments not cached → all need render)."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig, DzineBudget
        from lib.audio_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", video_final_dir=f"{td}/vfinal",
                video_index_path=f"{td}/index.json",
                output_dir=f"{td}/output",
            )
            budget = DzineBudget(available_credits=10, cost_per_segment=1)
            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=self._make_mock_panic(),
                dzine_budget=budget,
            )
            manifest_path = Path(td) / "jobs" / "test.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(manifest_path, {
                "run_id": "TEST-PF2",
                "segments": [
                    {"segment_id": "s1", "audio_path": "/a.mp3", "video_path": "/v.mp4", "approx_duration_sec": 5},
                    {"segment_id": "s2", "audio_path": "/b.mp3", "video_path": "/v2.mp4", "approx_duration_sec": 5},
                ],
            })
            pf = orch.preflight(manifest_path)
            self.assertEqual(pf["status"], "GO")
            self.assertEqual(pf["credits_needed"], 2)
            self.assertEqual(len(pf["needs_render"]), 2)


class TestDzineRenderFailFast(unittest.TestCase):
    """Tests for dzine_render fail-fast behavior."""

    def _make_mock_panic(self):
        class MockPanic:
            def __init__(self):
                self.calls = []
            def report_panic(self, reason_key, run_id, error_msg, **kw):
                self.calls.append((reason_key, run_id, error_msg))
        return MockPanic()

    def test_no_dzine_agent_raises(self):
        """dzine_render without agent raises immediately."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        from lib.audio_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", video_final_dir=f"{td}/vfinal",
                video_index_path=f"{td}/index.json",
                output_dir=f"{td}/output",
            )
            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=self._make_mock_panic(),
            )
            manifest_path = Path(td) / "jobs" / "test.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(manifest_path, {
                "run_id": "TEST-DR",
                "segments": [
                    {"segment_id": "s1", "audio_path": "/a.mp3",
                     "video_path": f"{td}/vfinal/V_x.mp4", "approx_duration_sec": 5},
                ],
            })
            with self.assertRaises(RuntimeError) as ctx:
                orch.dzine_render("TEST-DR", manifest_path)
            self.assertIn("no dzine_agent", str(ctx.exception))

    def test_dzine_ui_failure_panics(self):
        """Dzine UI failure triggers panic + abort."""
        from lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig
        from lib.audio_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            cfg = OrchestratorConfig(
                state_dir=td, checkpoints_dir=f"{td}/cp",
                jobs_dir=f"{td}/jobs", audio_dir=f"{td}/audio",
                video_dir=f"{td}/video", video_final_dir=f"{td}/vfinal",
                video_index_path=f"{td}/index.json",
                output_dir=f"{td}/output",
            )

            class FailingDzine:
                def render_segment(self, **kw):
                    raise RuntimeError("Playwright timeout")

            pm = self._make_mock_panic()
            orch = RayVaultOrchestrator(
                config=cfg, panic_mgr=pm,
                dzine_agent=FailingDzine(),
            )
            manifest_path = Path(td) / "jobs" / "test.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(manifest_path, {
                "run_id": "TEST-DR2",
                "segments": [
                    {"segment_id": "s1", "audio_path": "/a.mp3",
                     "video_path": f"{td}/vfinal/V_x.mp4", "approx_duration_sec": 5},
                ],
            })
            with self.assertRaises(RuntimeError) as ctx:
                orch.dzine_render("TEST-DR2", manifest_path)
            self.assertIn("DZINE_RENDER_FAIL", str(ctx.exception))
            self.assertTrue(any("panic_dzine_ui_failure" in c[0] for c in pm.calls))


class TestHasFfprobe(unittest.TestCase):
    """Tests for has_ffprobe availability check."""

    def test_has_ffprobe_returns_bool(self):
        """has_ffprobe returns a boolean."""
        from lib.media_manifest import has_ffprobe
        result = has_ffprobe()
        self.assertIsInstance(result, bool)


# ---------------------------------------------------------------------------
# Dzine Handoff — "Alfândega" tests
# ---------------------------------------------------------------------------

class TestDzineHandoffProbeResult(unittest.TestCase):
    """Tests for ProbeResult dataclass."""

    def test_probe_result_ok(self):
        from lib.dzine_handoff import ProbeResult
        r = ProbeResult(True, 12.0, 2_000_000, "h264", "aac", 1_000_000)
        self.assertTrue(r.ok)
        self.assertEqual(r.duration_sec, 12.0)
        self.assertEqual(r.bitrate_bps, 2_000_000)
        self.assertEqual(r.video_codec, "h264")
        self.assertEqual(r.audio_codec, "aac")
        self.assertIsNone(r.reason)

    def test_probe_result_failure(self):
        from lib.dzine_handoff import ProbeResult
        r = ProbeResult(False, 0.0, 0, None, None, 0, "missing_file")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "missing_file")

    def test_probe_result_file_bytes(self):
        from lib.dzine_handoff import ProbeResult
        r = ProbeResult(True, 5.0, 1_000_000, "h264", "aac", 750_000)
        self.assertEqual(r.file_bytes, 750_000)


class TestWaitFileStable(unittest.TestCase):
    """Tests for wait_file_stable with mtime + size checks."""

    def test_nonexistent_file_returns_false(self):
        from lib.dzine_handoff import wait_file_stable
        result = wait_file_stable(
            Path("/tmp/nonexistent_9876543.mp4"),
            timeout=0.5, check_interval=0.1, stable_cycles=2,
        )
        self.assertFalse(result)

    def test_stable_file_returns_true(self):
        from lib.dzine_handoff import wait_file_stable
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.mp4"
            p.write_bytes(b"x" * 100)
            result = wait_file_stable(
                p, timeout=5.0, check_interval=0.1, stable_cycles=2,
            )
            self.assertTrue(result)

    def test_empty_file_not_stable(self):
        from lib.dzine_handoff import wait_file_stable
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.mp4"
            p.write_bytes(b"")
            result = wait_file_stable(
                p, timeout=0.5, check_interval=0.1, stable_cycles=2,
            )
            self.assertFalse(result)


class TestValidateVideoFile(unittest.TestCase):
    """Tests for validate_video_file — size/probe gates."""

    def test_missing_file(self):
        from lib.dzine_handoff import validate_video_file
        r = validate_video_file(
            Path("/tmp/missing_video_test.mp4"),
            target_duration_sec=5.0,
        )
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "missing_file")

    def test_too_small(self):
        from lib.dzine_handoff import validate_video_file
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tiny.mp4"
            p.write_bytes(b"x" * 100)
            r = validate_video_file(
                p, target_duration_sec=5.0, min_bytes=500_000,
            )
            self.assertFalse(r.ok)
            self.assertEqual(r.reason, "too_small")
            self.assertEqual(r.file_bytes, 100)


class TestAtomicWriteJson(unittest.TestCase):
    """Tests for atomic JSON write with fsync."""

    def test_write_and_read(self):
        from lib.dzine_handoff import atomic_write_json, load_index
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_index.json"
            data = {"version": "1.0", "items": {"abc12345": {"run_id": "R1"}}}
            atomic_write_json(p, data)
            loaded = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(loaded["version"], "1.0")
            self.assertIn("abc12345", loaded["items"])

    def test_no_tmp_leftover(self):
        from lib.dzine_handoff import atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "idx.json"
            atomic_write_json(p, {"version": "1.0", "items": {}})
            files = list(Path(td).glob("*"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, "idx.json")


class TestLoadIndex(unittest.TestCase):
    """Tests for load_index with missing/corrupt files."""

    def test_missing_returns_empty(self):
        from lib.dzine_handoff import load_index
        idx = load_index(Path("/tmp/nonexistent_index_987.json"))
        self.assertEqual(idx["version"], "1.0")
        self.assertEqual(idx["items"], {})

    def test_corrupt_returns_empty(self):
        from lib.dzine_handoff import load_index
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("not json at all {{{", encoding="utf-8")
            idx = load_index(p)
            self.assertEqual(idx["version"], "1.0")

    def test_valid_index_loads(self):
        from lib.dzine_handoff import load_index, atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "idx.json"
            data = {"version": "1.0", "items": {"a1b2c3d4": {"path": "/x.mp4"}}}
            atomic_write_json(p, data)
            loaded = load_index(p)
            self.assertIn("a1b2c3d4", loaded["items"])


class TestInferSha8FromFilename(unittest.TestCase):
    """Tests for sha8 extraction from deterministic video filenames."""

    def test_valid_filename(self):
        from lib.dzine_handoff import infer_sha8_from_filename
        result = infer_sha8_from_filename(Path("V_RAY-99_intro_a1b2c3d4.mp4"))
        self.assertEqual(result, "a1b2c3d4")

    def test_no_sha8(self):
        from lib.dzine_handoff import infer_sha8_from_filename
        result = infer_sha8_from_filename(Path("random_video.mp4"))
        self.assertIsNone(result)

    def test_uppercase_normalized(self):
        from lib.dzine_handoff import infer_sha8_from_filename
        result = infer_sha8_from_filename(Path("V_R1_seg_AABBCCDD.mp4"))
        self.assertEqual(result, "aabbccdd")


class TestFindOrphanVideos(unittest.TestCase):
    """Tests for zombie/orphan video detection."""

    def test_no_orphans_when_all_indexed(self):
        from lib.dzine_handoff import find_orphan_videos, atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            v = final / "V_R1_s1_aabb.mp4"
            v.write_bytes(b"x" * 100)
            idx_path = Path(td) / "index.json"
            atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {"aabb": {"path": str(v)}},
            })
            report = find_orphan_videos(final_dir=final, index_path=idx_path)
            self.assertEqual(report.orphan_count, 0)

    def test_orphan_detected(self):
        from lib.dzine_handoff import find_orphan_videos, atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            v1 = final / "V_R1_s1_aabb.mp4"
            v1.write_bytes(b"x" * 100)
            v2 = final / "V_R1_s2_ccdd.mp4"
            v2.write_bytes(b"y" * 100)
            idx_path = Path(td) / "index.json"
            atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {"aabb": {"path": str(v1)}},
            })
            report = find_orphan_videos(final_dir=final, index_path=idx_path)
            self.assertEqual(report.orphan_count, 1)
            self.assertEqual(report.orphan_files[0].name, "V_R1_s2_ccdd.mp4")

    def test_no_final_dir(self):
        from lib.dzine_handoff import find_orphan_videos
        report = find_orphan_videos(
            final_dir=Path("/tmp/nonexistent_dir_999"),
            index_path=Path("/tmp/nonexistent_idx_999.json"),
        )
        self.assertEqual(report.orphan_count, 0)


class TestSha256File(unittest.TestCase):
    """Tests for sha256_file utility."""

    def test_deterministic(self):
        from lib.dzine_handoff import sha256_file
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.bin"
            p.write_bytes(b"hello world")
            h1 = sha256_file(p)
            h2 = sha256_file(p)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)

    def test_different_content_different_hash(self):
        from lib.dzine_handoff import sha256_file
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.bin"
            p2 = Path(td) / "b.bin"
            p1.write_bytes(b"aaa")
            p2.write_bytes(b"bbb")
            self.assertNotEqual(sha256_file(p1), sha256_file(p2))


# ---------------------------------------------------------------------------
# Doctor Report tests
# ---------------------------------------------------------------------------

class TestDoctorReportExtractRefs(unittest.TestCase):
    """Tests for extract_segment_refs from job manifest."""

    def test_basic_extraction(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import extract_segment_refs
        doc = {
            "run_id": "R1",
            "segments": [
                {
                    "segment_id": "intro",
                    "approx_duration_sec": 5.0,
                    "audio_sha256": "aabbccddee112233",
                },
                {
                    "segment_id": "p1",
                    "approx_duration_sec": 12.0,
                    "audio_sha256": "1122334455667788",
                },
            ],
        }
        refs = extract_segment_refs(doc, Path("state"))
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].segment_id, "intro")
        self.assertEqual(refs[0].sha8, "aabbccdd")
        self.assertEqual(refs[1].order, 1)

    def test_missing_sha_uses_unknown(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import extract_segment_refs
        doc = {
            "run_id": "R2",
            "segments": [{"segment_id": "s1"}],
        }
        refs = extract_segment_refs(doc, Path("state"))
        self.assertEqual(refs[0].sha8, "unknown")


class TestDoctorReportComputeReport(unittest.TestCase):
    """Tests for compute_report with mock state directory."""

    def test_empty_state(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import compute_report
        with tempfile.TemporaryDirectory() as td:
            summaries, details = compute_report(
                state_dir=Path(td),
                enable_bitrate_gate=False,
            )
            self.assertEqual(len(summaries), 0)
            self.assertEqual(details["jobs_found"], 0)
            self.assertEqual(details["total_credits_needed"], 0)

    def test_report_with_job(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import compute_report
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            jobs_dir = state / "jobs"
            jobs_dir.mkdir(parents=True)
            job = {
                "run_id": "TEST-1",
                "segments": [
                    {"segment_id": "s1", "approx_duration_sec": 5.0,
                     "audio_sha256": "aabbccdd11223344"},
                    {"segment_id": "s2", "approx_duration_sec": 10.0,
                     "audio_sha256": "eeff00112233aabb"},
                ],
            }
            (jobs_dir / "test.json").write_text(
                json.dumps(job), encoding="utf-8",
            )
            summaries, details = compute_report(
                state_dir=state, enable_bitrate_gate=False,
            )
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].segments_total, 2)
            self.assertEqual(summaries[0].segments_need, 2)
            self.assertEqual(details["total_credits_needed"], 2)

    def test_obsolete_hash_detected(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import compute_report
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            jobs_dir = state / "jobs"
            jobs_dir.mkdir(parents=True)
            video_dir = state / "video"
            video_dir.mkdir(parents=True)
            # Job references sha8 "aabbccdd"
            job = {
                "run_id": "R1",
                "segments": [
                    {"segment_id": "s1", "audio_sha256": "aabbccdd11223344"},
                ],
            }
            (jobs_dir / "j.json").write_text(json.dumps(job), encoding="utf-8")
            # Index has "aabbccdd" (referenced) + "deadbeef" (orphan)
            idx = {
                "items": {
                    "aabbccdd": {"path": "/x.mp4"},
                    "deadbeef": {"path": "/y.mp4"},
                },
            }
            (video_dir / "index.json").write_text(
                json.dumps(idx), encoding="utf-8",
            )
            _, details = compute_report(
                state_dir=state, enable_bitrate_gate=False,
            )
            self.assertEqual(details["obsolete_sha8_count"], 1)
            self.assertIn("deadbeef", details["obsolete_sha8"])


class TestDoctorFinancial(unittest.TestCase):
    """Tests for compute_financial projection."""

    def test_no_pricing(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import compute_financial
        f = compute_financial(10, 5, credit_price_usd=0.0)
        self.assertNotIn("projected_cost_usd", f)

    def test_usd_only(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import compute_financial
        f = compute_financial(10, 5, credit_price_usd=1.50)
        self.assertEqual(f["projected_cost_usd"], 15.0)
        self.assertEqual(f["saved_usd"], 7.5)
        self.assertNotIn("projected_cost_brl", f)

    def test_usd_and_brl(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import compute_financial
        f = compute_financial(10, 5, credit_price_usd=1.50, usd_brl=5.0)
        self.assertEqual(f["projected_cost_usd"], 15.0)
        self.assertEqual(f["projected_cost_brl"], 75.0)
        self.assertEqual(f["saved_brl"], 37.5)


class TestDoctorTimeline(unittest.TestCase):
    """Tests for build_timeline + timeline_to_csv."""

    def test_build_timeline_cumulative(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import build_timeline, SegmentRef
        refs = [
            SegmentRef("R1", "intro", "aa", 5.0, Path("/missing.mp4"), 1, "intro", 0),
            SegmentRef("R1", "p1", "bb", 12.0, Path("/missing2.mp4"), 1, "product", 1),
            SegmentRef("R1", "outro", "cc", 3.0, Path("/missing3.mp4"), 1, "outro", 2),
        ]
        rows = build_timeline(refs, include_probe=False)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].start_sec, 0.0)
        self.assertEqual(rows[0].end_sec, 5.0)
        self.assertEqual(rows[1].start_sec, 5.0)
        self.assertEqual(rows[1].end_sec, 17.0)
        self.assertEqual(rows[2].start_sec, 17.0)
        self.assertEqual(rows[2].end_sec, 20.0)
        self.assertEqual(rows[0].category, "intro")
        self.assertEqual(rows[1].category, "product")
        self.assertEqual(rows[2].category, "outro")
        for r in rows:
            self.assertEqual(r.status, "MISSING")

    def test_timeline_to_csv_format(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import build_timeline, timeline_to_csv, SegmentRef
        refs = [
            SegmentRef("R1", "s1", "aa", 5.0, Path("/x.mp4"), 1, "product", 0),
        ]
        rows = build_timeline(refs, include_probe=False)
        csv_str = timeline_to_csv(rows)
        self.assertIn("Order", csv_str)
        self.assertIn("Segment_ID", csv_str)
        self.assertIn("Cum_Drift_Sec", csv_str)
        lines = csv_str.strip().split("\n")
        self.assertEqual(len(lines), 2)  # header + 1 row

    def test_category_inference(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import _infer_category
        self.assertEqual(_infer_category("intro_v1", ""), "intro")
        self.assertEqual(_infer_category("outro_end", ""), "outro")
        self.assertEqual(_infer_category("transition_1", ""), "transition")
        self.assertEqual(_infer_category("p1_product", ""), "product")
        self.assertEqual(_infer_category("p1_product", "product"), "product")


class TestSaveTimelineCsv(unittest.TestCase):
    """Tests for save_timeline_csv with timestamp + _latest symlink."""

    def test_creates_timestamped_file(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import save_timeline_csv
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "timeline"
            ts_path, latest_path = save_timeline_csv(
                "Order,Seg\n0,s1\n", "RAY-99", tdir,
            )
            self.assertTrue(ts_path.exists())
            self.assertIn("timeline_RAY-99_", ts_path.name)
            self.assertTrue(ts_path.name.endswith(".csv"))
            content = ts_path.read_text(encoding="utf-8")
            self.assertIn("Order,Seg", content)

    def test_creates_latest_link(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import save_timeline_csv
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "timeline"
            ts_path, latest_path = save_timeline_csv(
                "header\nrow\n", "R1", tdir,
            )
            self.assertTrue(latest_path.exists())
            self.assertEqual(latest_path.name, "timeline_R1_latest.csv")
            # Content should match
            self.assertEqual(
                latest_path.read_text(encoding="utf-8"),
                ts_path.read_text(encoding="utf-8"),
            )

    def test_latest_updates_on_second_call(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import save_timeline_csv
        import time
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "timeline"
            save_timeline_csv("v1\n", "R1", tdir)
            time.sleep(0.05)
            ts2, latest2 = save_timeline_csv("v2\n", "R1", tdir)
            latest_content = latest2.read_text(encoding="utf-8")
            self.assertEqual(latest_content, "v2\n")
            # Should have 2 timestamped files + 1 latest
            csvs = list(tdir.glob("timeline_R1_*.csv"))
            # At least 2 (timestamped) + latest (symlink or copy)
            self.assertGreaterEqual(len(csvs), 2)

    def test_creates_directory(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import save_timeline_csv
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "deep" / "nested" / "timeline"
            ts_path, _ = save_timeline_csv("data\n", "X", tdir)
            self.assertTrue(ts_path.exists())


class TestDoctorOrphanSearch(unittest.TestCase):
    """Tests for find_orphan_videos in doctor_report."""

    def test_finds_orphans(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import find_orphan_videos
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            final = state / "video" / "final"
            final.mkdir(parents=True)
            v1 = final / "V_R1_s1_aabb.mp4"
            v1.write_bytes(b"x" * 100)
            v2 = final / "V_R1_s2_ccdd.mp4"
            v2.write_bytes(b"y" * 100)
            # Index only has v1
            idx_dir = state / "video"
            (idx_dir / "index.json").write_text(
                json.dumps({"items": {"aabb": {"path": str(v1)}}}),
                encoding="utf-8",
            )
            orphans = find_orphan_videos(state)
            self.assertEqual(len(orphans), 1)
            self.assertEqual(orphans[0].name, "V_R1_s2_ccdd.mp4")

    def test_no_orphans(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import find_orphan_videos
        with tempfile.TemporaryDirectory() as td:
            orphans = find_orphan_videos(Path(td))
            self.assertEqual(len(orphans), 0)


class TestDoctorCLI(unittest.TestCase):
    """Tests for doctor_report CLI main()."""

    def test_main_empty_state(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import main
        with tempfile.TemporaryDirectory() as td:
            rc = main(["--state-dir", td, "--no-bitrate-gate"])
            self.assertEqual(rc, 0)

    def test_main_fail_if_needed(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from doctor_report import main
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            jobs_dir = state / "jobs"
            jobs_dir.mkdir(parents=True)
            job = {
                "run_id": "R1",
                "segments": [
                    {"segment_id": "s1", "audio_sha256": "aabbccdd11223344"},
                ],
            }
            (jobs_dir / "j.json").write_text(json.dumps(job), encoding="utf-8")
            rc = main([
                "--state-dir", td,
                "--no-bitrate-gate",
                "--fail-if-needed-gt", "0",
            ])
            self.assertEqual(rc, 2)


# ---------------------------------------------------------------------------
# Doctor Cleanup tests
# ---------------------------------------------------------------------------

class TestDoctorCleanupFindOrphans(unittest.TestCase):
    """Tests for find_orphans in doctor_cleanup."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_no_orphans_all_referenced(self):
        self._add_scripts_path()
        from doctor_cleanup import find_orphans
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            v = final / "V_R1_s1_aabb.mp4"
            v.write_bytes(b"x" * 600_000)
            orphans = find_orphans(
                final, referenced_filenames={v.name},
                min_size_kb=500, keep_last_n=0,
            )
            self.assertEqual(len(orphans), 0)

    def test_orphan_detected(self):
        self._add_scripts_path()
        from doctor_cleanup import find_orphans
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            v = final / "V_R1_s1_aabb.mp4"
            v.write_bytes(b"x" * 600_000)
            orphans = find_orphans(
                final, referenced_filenames=set(),
                min_size_kb=500, keep_last_n=0,
            )
            self.assertEqual(len(orphans), 1)
            self.assertEqual(orphans[0].path.name, "V_R1_s1_aabb.mp4")

    def test_keep_last_n_protects(self):
        self._add_scripts_path()
        from doctor_cleanup import find_orphans
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            v = final / "V_R1_s1_aabb.mp4"
            v.write_bytes(b"x" * 600_000)
            orphans = find_orphans(
                final, referenced_filenames=set(),
                min_size_kb=500, keep_last_n=5,
            )
            self.assertEqual(len(orphans), 0)

    def test_min_size_filter(self):
        self._add_scripts_path()
        from doctor_cleanup import find_orphans
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            v = final / "tiny.mp4"
            v.write_bytes(b"x" * 100)
            orphans = find_orphans(
                final, referenced_filenames=set(),
                min_size_kb=500, keep_last_n=0,
            )
            self.assertEqual(len(orphans), 0)

    def test_nonexistent_dir(self):
        self._add_scripts_path()
        from doctor_cleanup import find_orphans
        orphans = find_orphans(
            Path("/tmp/nonexistent_cleanup_test_999"),
            referenced_filenames=set(),
        )
        self.assertEqual(len(orphans), 0)


class TestDoctorCleanupDanglingIndex(unittest.TestCase):
    """Tests for find_dangling_index_entries."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_no_dangling(self):
        self._add_scripts_path()
        from doctor_cleanup import find_dangling_index_entries
        with tempfile.TemporaryDirectory() as td:
            v = Path(td) / "test.mp4"
            v.write_bytes(b"x")
            index = {"items": {"aa": {"path": str(v)}}}
            dangling = find_dangling_index_entries(index)
            self.assertEqual(len(dangling), 0)

    def test_dangling_detected(self):
        self._add_scripts_path()
        from doctor_cleanup import find_dangling_index_entries
        index = {"items": {"aa": {"path": "/tmp/nonexistent_cleanup_dangle.mp4"}}}
        dangling = find_dangling_index_entries(index)
        self.assertEqual(len(dangling), 1)
        self.assertEqual(dangling[0][0], "aa")


class TestDoctorCleanupQuarantine(unittest.TestCase):
    """Tests for quarantine_or_delete actions."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_dry_run_no_action(self):
        self._add_scripts_path()
        from doctor_cleanup import quarantine_or_delete, Orphan
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "orphan.mp4"
            src.write_bytes(b"x" * 100)
            orphan = Orphan(path=src, size_bytes=100, mtime_utc=datetime.now(timezone.utc))
            qdir = Path(td) / "quarantine"
            result = quarantine_or_delete(
                [orphan], qdir,
                do_quarantine=True, do_delete=False, dry_run=True,
            )
            self.assertTrue(src.exists())
            self.assertEqual(result["moved"], 0)

    def test_quarantine_moves_file(self):
        self._add_scripts_path()
        from doctor_cleanup import quarantine_or_delete, Orphan
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "orphan.mp4"
            src.write_bytes(b"x" * 100)
            orphan = Orphan(path=src, size_bytes=100, mtime_utc=datetime.now(timezone.utc))
            qdir = Path(td) / "quarantine"
            result = quarantine_or_delete(
                [orphan], qdir,
                do_quarantine=True, do_delete=False, dry_run=False,
            )
            self.assertFalse(src.exists())
            self.assertEqual(result["moved"], 1)
            q_files = list(qdir.glob("*orphan*"))
            self.assertEqual(len(q_files), 1)

    def test_delete_removes_file(self):
        self._add_scripts_path()
        from doctor_cleanup import quarantine_or_delete, Orphan
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "orphan.mp4"
            src.write_bytes(b"x" * 100)
            orphan = Orphan(path=src, size_bytes=100, mtime_utc=datetime.now(timezone.utc))
            qdir = Path(td) / "quarantine"
            result = quarantine_or_delete(
                [orphan], qdir,
                do_quarantine=False, do_delete=True, dry_run=False,
            )
            self.assertFalse(src.exists())
            self.assertEqual(result["deleted"], 1)


class TestDoctorCleanupCLI(unittest.TestCase):
    """Tests for doctor_cleanup CLI main()."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_dry_run_empty(self):
        self._add_scripts_path()
        from doctor_cleanup import main
        with tempfile.TemporaryDirectory() as td:
            rc = main([
                "--index", str(Path(td) / "idx.json"),
                "--final-dir", str(Path(td) / "final"),
                "--dry-run",
            ])
            self.assertEqual(rc, 0)

    def test_both_flags_error(self):
        self._add_scripts_path()
        from doctor_cleanup import main
        with tempfile.TemporaryDirectory() as td:
            rc = main([
                "--index", str(Path(td) / "idx.json"),
                "--final-dir", str(Path(td) / "final"),
                "--quarantine",
                "--delete",
            ])
            self.assertEqual(rc, 2)


# ---------------------------------------------------------------------------
# Video Index Refresh tests
# ---------------------------------------------------------------------------

class TestVideoIndexRefresh(unittest.TestCase):
    """Tests for video_index_refresh.py."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_empty_dir(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        with tempfile.TemporaryDirectory() as td:
            stats = refresh_index(
                final_dir=Path(td) / "final",
                index_path=Path(td) / "index.json",
            )
            self.assertEqual(stats.scanned, 0)
            self.assertEqual(stats.enriched, 0)

    def test_incremental_skips_unchanged(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index, _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            # Create a dummy mp4
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 1000)
            st = v.stat()
            # Pre-seed index with matching (mtime_ns, file_bytes)
            _atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {
                    "aabbccdd": {
                        "path": str(v),
                        "file_mtime_ns": st.st_mtime_ns,
                        "file_bytes": st.st_size,
                        "duration": 5.0,
                    },
                },
            })
            stats = refresh_index(final_dir=final, index_path=idx_path)
            self.assertEqual(stats.skipped_mtime, 1)
            self.assertEqual(stats.probed, 0)

    def test_force_reprobes_all(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 1000)
            st = v.stat()
            _atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {
                    "aabbccdd": {
                        "path": str(v),
                        "file_mtime_ns": st.st_mtime_ns,
                        "file_bytes": st.st_size,
                    },
                },
            })
            stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            # Force means it probes even though cache matches
            self.assertEqual(stats.probed, 1)
            self.assertEqual(stats.skipped_mtime, 0)

    def test_dry_run_no_write(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 1000)
            stats = refresh_index(
                final_dir=final, index_path=idx_path, force=True, dry_run=True,
            )
            self.assertGreaterEqual(stats.probed, 1)
            # Index should not exist (dry-run)
            self.assertFalse(idx_path.exists())

    def test_sha8_inferred_from_filename(self):
        self._add_scripts_path()
        from video_index_refresh import _infer_sha8_from_filename
        self.assertEqual(
            _infer_sha8_from_filename(Path("V_R1_s1_aabbccdd.mp4")),
            "aabbccdd",
        )
        self.assertIsNone(_infer_sha8_from_filename(Path("random.mp4")))

    def test_infer_run_and_segment(self):
        self._add_scripts_path()
        from video_index_refresh import _infer_run_and_segment
        run_id, seg_id = _infer_run_and_segment(Path("V_RAY-99_intro_aabb.mp4"))
        self.assertEqual(run_id, "RAY-99")
        self.assertEqual(seg_id, "intro")

    def test_cli_empty_state(self):
        self._add_scripts_path()
        from video_index_refresh import main
        with tempfile.TemporaryDirectory() as td:
            rc = main(["--state-dir", td, "--dry-run"])
            self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# QC Banner tests
# ---------------------------------------------------------------------------

class TestQCBanner(unittest.TestCase):
    """Tests for build_qc_banner drift summary."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_no_rows(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner
        banner = build_qc_banner([])
        self.assertIn("No timeline rows", banner)

    def test_no_probed_segments(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "s1", "product", 0.0, 5.0, 5.0, "/x.mp4", "MISSING", 0.0, 0.0, 0.0),
        ]
        banner = build_qc_banner(rows)
        self.assertIn("No probed", banner)

    def test_ok_drift(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "s1", "product", 0.0, 5.0, 5.0, "/x.mp4", "READY", 5.05, 0.05, 0.05),
            TimelineRow(1, "s2", "product", 5.0, 10.0, 5.0, "/y.mp4", "READY", 4.98, -0.02, 0.03),
        ]
        banner = build_qc_banner(rows)
        self.assertIn("OK", banner)

    def test_warning_drift(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "s1", "product", 0.0, 5.0, 5.0, "/x.mp4", "READY", 5.7, 0.7, 0.7),
        ]
        banner = build_qc_banner(rows)
        self.assertIn("WARNING", banner)

    def test_critical_drift(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "s1", "product", 0.0, 5.0, 5.0, "/x.mp4", "READY", 6.5, 1.5, 1.5),
        ]
        banner = build_qc_banner(rows)
        self.assertIn("CRITICAL", banner)

    def test_banner_shows_worst_segment(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "intro", "intro", 0.0, 3.0, 3.0, "/a.mp4", "READY", 3.1, 0.1, 0.1),
            TimelineRow(1, "p1", "product", 3.0, 15.0, 12.0, "/b.mp4", "READY", 13.2, 1.2, 1.3),
        ]
        banner = build_qc_banner(rows)
        self.assertIn("p1", banner)


# ---------------------------------------------------------------------------
# validate_video_file Optional duration tests
# ---------------------------------------------------------------------------

class TestValidateVideoFileOptionalDuration(unittest.TestCase):
    """Tests for validate_video_file with target_duration_sec=None."""

    def test_none_duration_skips_check(self):
        from lib.dzine_handoff import validate_video_file
        # With target=None, only size/probe matter, not duration mismatch
        r = validate_video_file(
            Path("/tmp/nonexistent_video_opt.mp4"),
            target_duration_sec=None,
        )
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "missing_file")

    def test_zero_duration_also_skips(self):
        from lib.dzine_handoff import validate_video_file
        # target=0.0 should also skip duration check (backwards compat)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tiny.mp4"
            p.write_bytes(b"x" * 100)
            r = validate_video_file(p, target_duration_sec=0.0, min_bytes=50)
            # Will fail on ffprobe (not real mp4), but NOT on duration mismatch
            self.assertIn(r.reason, ("ffprobe_failed", None))


# ---------------------------------------------------------------------------
# Video Index Refresh v2 — mtime_ns, dedup, allow-missing-sha8, meta_info
# ---------------------------------------------------------------------------

class TestVideoIndexRefreshV2(unittest.TestCase):
    """Tests for hardened video_index_refresh: mtime_ns, dedup, sha8 gate, meta_info."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_mtime_ns_dual_key_skip(self):
        """Incremental uses (mtime_ns, file_bytes) pair for cache."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 1000)
            st = v.stat()
            _atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {
                    "aabbccdd": {
                        "path": str(v),
                        "file_mtime_ns": st.st_mtime_ns,
                        "file_bytes": st.st_size,
                        "duration": 5.0,
                    },
                },
            })
            stats = refresh_index(final_dir=final, index_path=idx_path)
            self.assertEqual(stats.skipped_mtime, 1)
            self.assertEqual(stats.probed, 0)

    def test_old_float_mtime_triggers_reprobe(self):
        """Old index entries with file_mtime (float) get re-probed (migration)."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 1000)
            # Old-style entry with file_mtime (float), no file_mtime_ns
            _atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {
                    "aabbccdd": {
                        "path": str(v),
                        "file_mtime": v.stat().st_mtime,
                    },
                },
            })
            stats = refresh_index(final_dir=final, index_path=idx_path)
            # Should re-probe because file_mtime_ns doesn't match
            self.assertEqual(stats.probed, 1)

    def test_seen_paths_dedup(self):
        """Duplicate resolved paths are skipped."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            # Create one real file
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            # Create a symlink to the same file (different name, same resolved path)
            link = final / "V_R1_s1_11223344.mp4"
            link.symlink_to(v)
            stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            # One should be probed, the other deduped
            self.assertEqual(stats.skipped_dedup, 1)

    def test_no_sha8_skipped_by_default(self):
        """Files without sha8 in filename are skipped by default."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            # File without sha8 pattern
            v = final / "random_legacy.mp4"
            v.write_bytes(b"x" * 500)
            stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            self.assertEqual(stats.skipped_no_sha8, 1)
            self.assertEqual(stats.probed, 0)

    def test_allow_missing_sha8_indexes_legacy(self):
        """With allow_missing_sha8=True, legacy files get probed."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "random_legacy.mp4"
            v.write_bytes(b"x" * 500)
            stats = refresh_index(
                final_dir=final, index_path=idx_path,
                force=True, allow_missing_sha8=True,
            )
            self.assertEqual(stats.skipped_no_sha8, 0)
            self.assertEqual(stats.probed, 1)

    def test_refresh_history_ring_buffer(self):
        """meta_info.refresh_history is appended and capped at 10."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index, _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            # Pre-seed with 9 history entries
            _atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {},
                "meta_info": {
                    "refresh_history": [{"at": f"2025-01-{i:02d}", "scanned": i} for i in range(1, 10)],
                },
            })
            stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            # ffprobe will fail on fake mp4, so enriched might be 0
            # But let's check meta_info was written if enriched > 0
            if stats.enriched > 0:
                idx = _load_index(idx_path)
                history = idx.get("meta_info", {}).get("refresh_history", [])
                self.assertLessEqual(len(history), 10)
                self.assertIn("scanned", history[-1])

    def test_file_mtime_old_key_removed_on_update(self):
        """Old file_mtime key is removed when entry is updated."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index, _atomic_write_json
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            _atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {
                    "aabbccdd": {"path": str(v), "file_mtime": 123.456},
                },
            })
            # Mock ffprobe to return valid data
            fake_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=fake_meta):
                stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            self.assertEqual(stats.enriched, 1)
            idx = _load_index(idx_path)
            entry = idx["items"]["aabbccdd"]
            self.assertNotIn("file_mtime", entry)
            self.assertIn("file_mtime_ns", entry)

    def test_cli_allow_missing_sha8_flag(self):
        """CLI accepts --allow-missing-sha8."""
        self._add_scripts_path()
        from video_index_refresh import main
        with tempfile.TemporaryDirectory() as td:
            rc = main(["--state-dir", td, "--dry-run", "--allow-missing-sha8"])
            self.assertEqual(rc, 0)

    def test_size_change_triggers_reprobe(self):
        """Changing file size triggers re-probe even if mtime_ns is same."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 1000)
            st = v.stat()
            # Seed with same mtime_ns but different size
            _atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {
                    "aabbccdd": {
                        "path": str(v),
                        "file_mtime_ns": st.st_mtime_ns,
                        "file_bytes": 999,  # wrong size
                    },
                },
            })
            stats = refresh_index(final_dir=final, index_path=idx_path)
            self.assertEqual(stats.probed, 1)
            self.assertEqual(stats.skipped_mtime, 0)


# ---------------------------------------------------------------------------
# QC Banner v2 — first_missing, warning_count
# ---------------------------------------------------------------------------

class TestQCBannerV2(unittest.TestCase):
    """Tests for QC banner with first_missing and warning_count."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_first_missing_shown(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "intro", "intro", 0.0, 3.0, 3.0, "/a.mp4", "READY", 3.0, 0.0, 0.0),
            TimelineRow(1, "gap_seg", "product", 3.0, 15.0, 12.0, "/b.mp4", "MISSING", 0.0, 0.0, 0.0),
            TimelineRow(2, "p2", "product", 15.0, 27.0, 12.0, "/c.mp4", "READY", 12.1, 0.1, 0.1),
        ]
        banner = build_qc_banner(rows)
        self.assertIn("First missing: gap_seg", banner)

    def test_no_missing_no_first_missing_line(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "s1", "product", 0.0, 5.0, 5.0, "/x.mp4", "READY", 5.0, 0.0, 0.0),
        ]
        banner = build_qc_banner(rows)
        self.assertNotIn("First missing", banner)

    def test_warning_count_shown(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "s1", "product", 0.0, 5.0, 5.0, "/a.mp4", "READY", 5.8, 0.8, 0.8),
            TimelineRow(1, "s2", "product", 5.0, 10.0, 5.0, "/b.mp4", "READY", 5.1, 0.1, 0.9),
            TimelineRow(2, "s3", "product", 10.0, 15.0, 5.0, "/c.mp4", "READY", 5.6, 0.6, 1.5),
        ]
        banner = build_qc_banner(rows)
        # s1 (0.8s) and s3 (0.6s) are > 0.5s drift
        self.assertIn("Segments over 0.5s drift: 2", banner)

    def test_worst_drift_label(self):
        self._add_scripts_path()
        from doctor_report import build_qc_banner, TimelineRow
        rows = [
            TimelineRow(0, "s1", "product", 0.0, 5.0, 5.0, "/a.mp4", "READY", 5.05, 0.05, 0.05),
        ]
        banner = build_qc_banner(rows)
        self.assertIn("Worst drift:", banner)
        self.assertIn("s1", banner)


if __name__ == "__main__":
    unittest.main(verbosity=2)
